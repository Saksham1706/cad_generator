import os, json
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

NORMALIZER_PROMPT = """
You are a CAD assistant. Understand what 3D shape the user wants.

Shape mapping:
- pipe / tube / hollow cylinder / ring → hollow_cylinder
- can / cup / drum / rod / pillar → cylinder
- cube / cuboid / brick / block → box
- ball / globe / bead → sphere
- funnel / pointed / cone-like → cone
- box/cube WITH circular hole → box_with_hole
- box/cube WITH square/rectangular hole → box_with_square_hole

UNIT CONVERSION — always convert to mm:
- 1 cm = 10 mm, 1 m = 1000 mm, 1 inch = 25.4 mm

HOLE RULES:
- "blind hole" or "hole of depth X" → use exact depth, NOT through
- "through hole" or "drill through" → cut all the way through

EDGE TREATMENTS (Optional):
- "rounded edges", "fillet" → recognize as fillet
- "beveled edges", "chamfer" → recognize as chamfer

TEXT / EMBOSSING (Optional):
- "emboss", "engrave", "write", "text" → recognize text addition

Return JSON only:
{
  "understood_as": "<shape_name>",
  "clarified_prompt": "<clear English rewrite with all dims in mm, including edge and text details>",
  "confidence": "high/medium/low",
  "reason": "<why you chose this shape>"
}
"""

EXTRACTOR_PROMPT = """
You are a CAD parameter extractor. Return ONLY valid JSON, no explanation.

You MUST include a "shape" key. Supported base shapes: box, cylinder, hollow_cylinder, sphere, cone

Required base shape fields:
- box: width_mm, height_mm, depth_mm
- cylinder: diameter_mm, height_mm
- hollow_cylinder: outer_diameter_mm, inner_diameter_mm, height_mm
- cone: base_diameter_mm, top_diameter_mm, height_mm
- sphere: diameter_mm

OPTIONAL FEATURES (Add these to ANY shape if requested, otherwise omit):
- circ_hole_dia_mm (number), circ_hole_depth_mm (number), circ_hole_face (string)
- sq_hole_side_mm (number), sq_hole_depth_mm (number), sq_hole_face (string)
- edge_treatment ("fillet" or "chamfer"), edge_radius_mm (number)
- emboss_text (string), emboss_depth_mm (number, negative for cut), emboss_face (string), emboss_fontsize (number)

Face options: "top", "bottom", "front", "back", "left", "right", "smallest", "largest"

If any required dimension for the base shape is missing → add to missing_fields list.
"""

def normalize_prompt(user_prompt: str) -> dict:
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": NORMALIZER_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

def extract_params(user_prompt: str) -> dict:
    normalized = normalize_prompt(user_prompt)

    if normalized.get("understood_as") == "unknown":
        return {
            "shape": "unknown",
            "missing_fields": [],
            "_error": "I could not identify a 3D shape from your description.",
            "_suggestion": "Try describing it as: box, cylinder, sphere, cone, pipe/tube, or box with hole"
        }

    clarified = normalized["clarified_prompt"]

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": EXTRACTOR_PROMPT},
            {"role": "user", "content": clarified}
        ],
        temperature=0
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    params = json.loads(raw)

    params["_understood_as"] = normalized["understood_as"]
    params["_confidence"] = normalized["confidence"]
    params["_clarified_as"] = clarified

    return params

def edit_params(previous: dict, edit: str) -> dict:
    clean_prev = {k: v for k, v in previous.items() if not k.startswith("_")}

    prompt = f"""
Previous CAD model JSON: {json.dumps(clean_prev)}
User wants to change: "{edit}"
Return the complete updated JSON with only the changed fields modified.
Keep all other fields exactly the same.
"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": EXTRACTOR_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    if not raw:
        return clean_prev

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return clean_prev