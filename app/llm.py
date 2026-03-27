import os, json
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

NORMALIZER_PROMPT = """
You are a CAD assistant. Understand what 3D shape the user wants.

Shape mapping:
- pipe / tube / hollow cylinder → hollow_cylinder
- can / cup / drum / rod / pillar → cylinder
- cube / cuboid / brick / block → box
- ball / globe → sphere
- funnel / cone → cone
- box/cube WITH circular hole → box_with_hole
- box/cube WITH square/rectangular hole → box_with_square_hole

UNIT CONVERSION — always convert to mm:
- 1 cm = 10 mm, 1 m = 1000 mm, 1 inch = 25.4 mm

HOLE RULES — very important:
- "blind hole" or "hole of depth X" → use exact depth, NOT through
- "through hole" or "drill through" → cut all the way through
- No depth mentioned → add hole_depth_mm to missing_fields
- "square hole side X" → hole_side_mm = X, shape = box_with_square_hole
- "circular hole diameter X" → hole_diameter_mm = X, shape = box_with_hole

FACE SELECTION RULES:
- "top face" → face = "top"
- "bottom face" → face = "bottom"  
- "front face" → face = "front"
- "smallest face / smallest surface" → face = "smallest"
- "largest face / biggest surface" → face = "largest"
- If no face mentioned → face = "top" (default)

Return JSON only:
{
  "understood_as": "<shape_name>",
  "clarified_prompt": "<clear English rewrite with all dims in mm>",
  "confidence": "high/medium/low",
  "reason": "<why you chose this shape>"
}
"""

EXTRACTOR_PROMPT = """
You are a CAD parameter extractor. Return ONLY valid JSON.
Supported shapes: box, cylinder, hollow_cylinder, sphere, cone, 
                  box_with_hole, box_with_square_hole

Required fields:
- box: width_mm, height_mm, depth_mm
- cylinder: diameter_mm, height_mm
- hollow_cylinder: outer_diameter_mm, inner_diameter_mm, height_mm
- sphere: diameter_mm
- cone: base_diameter_mm, top_diameter_mm, height_mm
- box_with_hole: width_mm, height_mm, depth_mm, 
                 hole_diameter_mm, hole_depth_mm, hole_face
- box_with_square_hole: width_mm, height_mm, depth_mm,
                        hole_side_mm, hole_depth_mm, hole_face

hole_face options: "top", "bottom", "front", "back", "left", "right", "smallest", "largest"
If hole depth not specified → null in missing_fields

Examples:
{"shape":"box_with_hole","width_mm":100,"height_mm":50,"depth_mm":30,
 "hole_diameter_mm":10,"hole_depth_mm":10,"hole_face":"smallest","missing_fields":[]}

{"shape":"box_with_square_hole","width_mm":100,"height_mm":50,"depth_mm":30,
 "hole_side_mm":10,"hole_depth_mm":10,"hole_face":"top","missing_fields":[]}
"""

def normalize_prompt(user_prompt: str) -> dict:
    """Stage 1 — understand what the user wants"""
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
    """Full pipeline — normalize then extract"""
    
    # Stage 1: understand intent
    normalized = normalize_prompt(user_prompt)
    
    # If LLM has no idea what shape this is
    if normalized.get("understood_as") == "unknown":
        return {
            "shape": "unknown",
            "missing_fields": [],
            "_error": "I could not identify a 3D shape from your description.",
            "_suggestion": "Try describing it as: box, cylinder, sphere, cone, pipe/tube, or box with hole"
        }
    
    # Stage 2: extract strict parameters from the clarified prompt
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
    
    # Attach debug info
    params["_understood_as"] = normalized["understood_as"]
    params["_confidence"] = normalized["confidence"]
    params["_clarified_as"] = clarified
    
    return params

def edit_params(previous: dict, edit: str) -> dict:
    # Clean previous params (remove debug keys)
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
    print("EDIT RAW RESPONSE:", repr(raw))  # debug
    
    # Strip markdown fences
    raw = raw.replace("```json", "").replace("```", "").strip()
    
    # If empty response, return previous params unchanged
    if not raw:
        print("WARNING: Empty response from LLM, returning previous params")
        return clean_prev
    
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}, raw was: {repr(raw)}")
        # Return previous params if parse fails
        return clean_prev