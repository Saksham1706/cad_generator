import os, json
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

NORMALIZER_PROMPT = """
You are a CAD assistant. Your job is to understand what 3D shape the user wants, 
even if they describe it vaguely, in another language, or using everyday objects as reference.

Mapping rules:
- pipe / tube / hollow cylinder / ring / donut cross-section → hollow_cylinder
- can / cup / drum / rod / pillar / pole → cylinder  
- cube / cuboid / brick / block / rectangular box → box
- ball / globe / bead / round → sphere
- funnel / pointed / pyramid-like / ice cream cone → cone
- box with hole / box with dent / box with cavity / box with opening → box_with_hole

Your job:
1. Identify which of these 6 shapes best matches the user's description
2. Extract all dimensions mentioned (convert any unit to mm: 1cm=10mm, 1m=1000mm, 1inch=25.4mm)
3. Rewrite the request as a clear, specific English sentence

Return JSON only:
{
  "understood_as": "<shape_name>",
  "clarified_prompt": "<clear English rewrite>",
  "confidence": "high/medium/low",
  "reason": "<why you chose this shape>"
}

If the request has nothing to do with a 3D shape, set understood_as to "unknown".
"""

EXTRACTOR_PROMPT = """
You are a CAD parameter extractor. Return ONLY valid JSON, no explanation.
Supported shapes: box, cylinder, hollow_cylinder, sphere, cone, box_with_hole

STRICT RULES:
- All dimensions in mm
- If any dimension is missing set it to null and add to missing_fields list
- Never guess or assume dimensions — mark them null
- Always use exact field names with _mm suffix

Required fields per shape:
- box: width_mm, height_mm, depth_mm
- cylinder: diameter_mm, height_mm
- hollow_cylinder: outer_diameter_mm, inner_diameter_mm, height_mm
- cone: base_diameter_mm, top_diameter_mm, height_mm
- sphere: diameter_mm
- box_with_hole: width_mm, height_mm, depth_mm, hole_diameter_mm, hole_depth_mm

Examples:
{"shape":"box","width_mm":50,"height_mm":30,"depth_mm":20,"missing_fields":[]}
{"shape":"hollow_cylinder","outer_diameter_mm":30,"inner_diameter_mm":20,"height_mm":50,"missing_fields":[]}
{"shape":"box_with_hole","width_mm":60,"height_mm":60,"depth_mm":60,"hole_diameter_mm":10,"hole_depth_mm":10,"missing_fields":[]}
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
    """Edit existing model params based on user instruction"""
    
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
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)