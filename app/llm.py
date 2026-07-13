import os
import json
import time
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

_api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=_api_key) if _api_key else None

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

NORMALIZER_PROMPT = """
You are a CAD assistant. Understand what 3D shape the user wants.

Shape mapping:
- pipe / tube / hollow cylinder / ring / grommet → hollow_cylinder
- can / cup / drum / rod / pillar / dowel → cylinder
- cube / cuboid / brick / block / plate / panel → box
- ball / globe / bead / marble → sphere
- dome / half sphere / bowl (inverted) → hemisphere
- funnel / pointed / cone-like / spike → cone
- donut / torus / o-ring → torus
- hex nut shape / hexagonal bar / n-sided prism / hex prism → prism
- pyramid / obelisk (pointed) → pyramid
- frustum / truncated pyramid (flat top) → pyramid (with a top width/depth)
- star / star-shaped plaque / badge → star
- box/cube WITH circular hole → box_with_hole
- box/cube WITH square/rectangular hole → box_with_square_hole

UNIT CONVERSION — always convert to mm:
- 1 cm = 10 mm, 1 m = 1000 mm, 1 inch = 25.4 mm

HOLE RULES:
- "blind hole" or "hole of depth X" → use exact depth, NOT through
- "through hole" or "drill through" → cut all the way through
- "N holes in a circle/bolt circle/bolt pattern" → a polar hole pattern
- "grid of holes" / "NxM holes" → a linear hole pattern

EDGE TREATMENTS (Optional):
- "rounded edges", "fillet" → recognize as fillet
- "beveled edges", "chamfer" → recognize as chamfer

TEXT / EMBOSSING (Optional, can appear more than once, on different faces):
- "emboss", "engrave", "write", "text", "stamp" → recognize text addition

SHELLING (Optional):
- "hollow out", "shell", "make it hollow with X mm walls" → recognize a shell/hollow feature

MATERIAL (Optional):
- if a material is mentioned (plastic, PLA, ABS, aluminum, steel, brass, titanium, wood, etc.)
  capture it so weight can be estimated

Return JSON only:
{
  "understood_as": "<shape_name>",
  "clarified_prompt": "<clear English rewrite with all dims in mm, including every feature mentioned>",
  "confidence": "high/medium/low",
  "reason": "<why you chose this shape>"
}
"""

EXTRACTOR_PROMPT = """
You are a CAD parameter extractor. Return ONLY valid JSON, no explanation, no markdown fences.

You MUST include a "shape" key. Supported base shapes:
box, cylinder, hollow_cylinder, sphere, hemisphere, cone, torus, prism, pyramid, star

Required base shape fields:
- box: width_mm, height_mm, depth_mm
- cylinder: diameter_mm, height_mm
- hollow_cylinder: outer_diameter_mm, inner_diameter_mm, height_mm
- sphere: diameter_mm
- hemisphere: diameter_mm
- cone: base_diameter_mm, top_diameter_mm, height_mm
- torus: torus_diameter_mm (overall diameter), tube_diameter_mm (thickness of the tube)
- prism: sides (integer 3-20), width_mm (distance across), height_mm
- pyramid: base_width_mm, base_depth_mm, height_mm (add top_width_mm + top_depth_mm together only for a flat-top frustum)
- star: points (integer 3-16), outer_diameter_mm, inner_diameter_mm, height_mm

OPTIONAL FEATURES (add to ANY shape if requested, otherwise omit entirely):
- circ_hole_dia_mm (number), circ_hole_depth_mm (number), circ_hole_face (string)
- circ_hole_pattern (object): either
    {"type": "linear", "count_x": int, "count_y": int, "spacing_x_mm": number, "spacing_y_mm": number}
  or
    {"type": "polar", "count": int, "radius_mm": number}
- sq_hole_side_mm (number), sq_hole_depth_mm (number), sq_hole_face (string), sq_hole_pattern (same shape as circ_hole_pattern)
- edge_treatment ("fillet" or "chamfer"), edge_radius_mm (number)
- text_features (list of objects), each: {"text": string, "face": string, "depth_mm": number (negative = engrave, positive = emboss), "fontsize": number}
- shell_thickness_mm (number) — hollows the part out; optionally shell_open_face (string) to leave one face open
- material (string, one of: pla, abs, petg, nylon, resin, aluminum, steel, stainless, brass, titanium, copper, oak, acrylic)

Face options for any *_face field: "top", "bottom", "front", "back", "left", "right", "smallest", "largest"

If any required dimension for the base shape is missing → add it to a missing_fields list.
"""


def _chat(system_prompt: str, user_content: str, temperature: float = 0.0) -> str:
    if client is None:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to a .env file, or use the /generate_manual "
            "endpoint to submit CAD parameters directly without natural-language parsing."
        )

    last_err = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=temperature,
            )
            raw = response.choices[0].message.content.strip()
            return raw.replace("```json", "").replace("```", "").strip()
        except Exception as e:  # noqa: BLE001 — surface a clean error to the API layer
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"The language model request failed after 3 attempts: {last_err}")


def normalize_prompt(user_prompt: str) -> dict:
    raw = _chat(NORMALIZER_PROMPT, user_prompt, temperature=0.1)
    return json.loads(raw)


def extract_params(user_prompt: str) -> dict:
    try:
        normalized = normalize_prompt(user_prompt)
    except json.JSONDecodeError:
        return {
            "shape": "unknown",
            "missing_fields": [],
            "_error": "I couldn't parse a response for that description.",
            "_suggestion": "Try rephrasing with clearer shape and dimensions.",
        }

    if normalized.get("understood_as") == "unknown":
        return {
            "shape": "unknown",
            "missing_fields": [],
            "_error": "I could not identify a 3D shape from your description.",
            "_suggestion": "Try describing it as: box, cylinder, sphere, cone, torus, prism, pyramid, star, pipe/tube, or box with hole",
        }

    clarified = normalized["clarified_prompt"]
    raw = _chat(EXTRACTOR_PROMPT, clarified, temperature=0.0)

    try:
        params = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "shape": "unknown",
            "missing_fields": [],
            "_error": "I understood the shape but couldn't extract clean dimensions.",
            "_suggestion": "Try giving explicit numbers with units, e.g. '50mm wide'.",
        }

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
Keep all other fields exactly the same unless the request implies removing one
(e.g. "remove the hole" should drop the hole fields entirely).
"""
    raw = _chat(EXTRACTOR_PROMPT, prompt, temperature=0.0)

    if not raw:
        return clean_prev

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return clean_prev
