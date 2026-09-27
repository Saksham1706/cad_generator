import os
import re
import json
import time
import hashlib
from groq import Groq
from dotenv import load_dotenv

from typing import Optional

from app.compounds import (
    COMPOUND_BUILDERS,
    COMPOUND_DEFAULTS,
    apply_compound_defaults,
    match_compound_keyword,
)

_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(_ENV_PATH)
load_dotenv()

_api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=_api_key) if _api_key else None

# Keep default in sync with .env — override only via GROQ_MODEL
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# In-process prompt → params cache (same prompt within a session is instant)
_PARAM_CACHE: dict[str, dict] = {}
_CACHE_MAX = 64


def llm_status() -> dict:
    """Public status for /health — never exposes the API key."""
    return {
        "provider": "groq",
        "model": MODEL,
        "configured": bool(_api_key),
        "cache_size": len(_PARAM_CACHE),
    }


_COMPOUND_LIST = ", ".join(sorted(COMPOUND_BUILDERS.keys()))

# Single-shot prompt: replaces the old normalize → extract double call
FAST_EXTRACT_PROMPT = f"""
You are a fast CAD parameter extractor. Return ONLY valid JSON (no markdown).

Map the user request to one shape id and dimensions in mm.

Primitives: box, cylinder, hollow_cylinder, sphere, hemisphere, cone, torus, prism, pyramid, star
Compounds: {_COMPOUND_LIST}

Aliases:
pipe/tube→hollow_cylinder; cube/block/plate→box; ball→sphere; dome→hemisphere;
bottle→water_bottle; coffee mug→mug; desk→table; bookcase→bookshelf; photo frame→picture_frame

Units: 1cm=10mm, 1m=1000mm, 1in=25.4mm. Always output mm.

Text rules:
- "engrave/etch X" → text_features:[{{"text":"X","face":"top","depth_mm":-1.5,"fontsize":10,"mode":"engrave"}}]
- "emboss/raise X" → depth_mm positive, mode "emboss"
- Keep engraved text ≤ 24 chars.

Holes: polar pattern = circ_hole_pattern {{"type":"polar","count":N,"radius_mm":R}}
Grid: {{"type":"linear","count_x":N,"count_y":M,"spacing_x_mm":S,"spacing_y_mm":S}}
Shell: shell_thickness_mm + shell_open_face
Edges: edge_treatment "fillet"|"chamfer" + edge_radius_mm

Required dims:
box: width_mm,height_mm,depth_mm | cylinder: diameter_mm,height_mm
hollow_cylinder: outer_diameter_mm,inner_diameter_mm,height_mm
sphere/hemisphere: diameter_mm | cone: base_diameter_mm,top_diameter_mm,height_mm
torus: torus_diameter_mm,tube_diameter_mm | prism: sides,width_mm,height_mm
pyramid: base_width_mm,base_depth_mm,height_mm | star: points,outer_diameter_mm,inner_diameter_mm,height_mm
Compounds: omit unspecified dims (defaults fill). Do NOT use missing_fields for compounds.
Primitives: missing required dims → missing_fields list.

JSON shape:
{{"shape":"...","...dims...","text_features":[],"missing_fields":[],"_clarified_as":"short rewrite"}}
"""

ALIAS_FIX = {
    "bottle": "water_bottle",
    "waterbottle": "water_bottle",
    "coffee_mug": "mug",
    "coffee_cup": "mug",
    "wine_glass": "goblet",
    "bookcase": "bookshelf",
    "desk": "table",
    "phone_holder": "phone_stand",
    "photo_frame": "picture_frame",
}

_PRIMITIVES = {
    "box", "cylinder", "hollow_cylinder", "sphere", "hemisphere",
    "cone", "torus", "prism", "pyramid", "star",
}

_PRIMITIVE_WORD = re.compile(
    r"\b(box|cube|block|cuboid|brick|cylinder|rod|dowel|pillar|sphere|ball|globe|"
    r"cone|torus|prism|pyramid|star|hemisphere|dome|pipe|tube)\b"
)


def _cache_key(prompt: str) -> str:
    return hashlib.sha1(prompt.strip().lower().encode("utf-8")).hexdigest()


def _cache_get(prompt: str) -> Optional[dict]:
    return _PARAM_CACHE.get(_cache_key(prompt))


def _cache_put(prompt: str, params: dict) -> dict:
    if len(_PARAM_CACHE) >= _CACHE_MAX:
        # drop oldest insertion
        try:
            _PARAM_CACHE.pop(next(iter(_PARAM_CACHE)))
        except StopIteration:
            pass
    _PARAM_CACHE[_cache_key(prompt)] = params
    return params


def _chat(system_prompt: str, user_content: str, temperature: float = 0.0,
          max_tokens: int = 700) -> str:
    if client is None:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to a .env file, or use the /generate_manual "
            "endpoint to submit CAD parameters directly without natural-language parsing."
        )

    last_err = None
    for attempt in range(2):  # one retry is enough; was 3
        try:
            kwargs = dict(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # Groq JSON mode when available — fewer parse failures, slightly faster
            try:
                kwargs["response_format"] = {"type": "json_object"}
                response = client.chat.completions.create(**kwargs)
            except Exception:
                kwargs.pop("response_format", None)
                response = client.chat.completions.create(**kwargs)
            raw = response.choices[0].message.content.strip()
            return raw.replace("```json", "").replace("```", "").strip()
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(0.25 * (attempt + 1))
    raise RuntimeError(f"The language model request failed after retries: {last_err}")


def _mm_from_match(num: str, unit: str = "mm") -> float:
    v = float(num)
    u = (unit or "mm").lower()
    if u.startswith("cm"):
        return v * 10
    if u in ("m", "meter", "meters"):
        return v * 1000
    if u in ("in", "inch", "inches", '"'):
        return v * 25.4
    return v


def _labeled_mm(low: str, words: tuple) -> Optional[float]:
    alt = "|".join(words)
    m = re.search(rf"(\d+(?:\.\d+)?)\s*(mm|cm|m|in|inch|inches)?\s*(?:{alt})\b", low)
    if not m:
        return None
    return _mm_from_match(m.group(1), m.group(2) or "mm")


def _apply_compound_counts(params: dict, low: str, compound: str) -> dict:
    """Pull '4 shelves' / '3 legs' out of a prompt the heuristic would otherwise ignore."""
    shelves = re.search(r"(\d+)\s*shel(?:f|ves)\b", low)
    if shelves and compound == "bookshelf":
        params["shelf_count"] = int(shelves.group(1))
    legs = re.search(r"(\d+)\s*legs?\b", low)
    if legs and compound == "stool":
        params["leg_count"] = int(legs.group(1))
    return params


def _box_from_text(low: str) -> Optional[dict]:
    w = _labeled_mm(low, ("wide", "width"))
    h = _labeled_mm(low, ("tall", "high", "height"))
    d = _labeled_mm(low, ("deep", "depth"))
    if w is None and h is None and d is None:
        dims = re.findall(r"(\d+(?:\.\d+)?)\s*(mm|cm|m|in|inch|inches)?", low)
        if len(dims) < 3:
            return None
        # Unlabeled triples are width × depth × height.
        w = _mm_from_match(dims[0][0], dims[0][1] or "mm")
        d = _mm_from_match(dims[1][0], dims[1][1] or "mm")
        h = _mm_from_match(dims[2][0], dims[2][1] or "mm")
    elif w is None or h is None or d is None:
        return None
    return {
        "shape": "box",
        "width_mm": w, "height_mm": h, "depth_mm": d,
        "_understood_as": "box", "_confidence": "high",
        "_clarified_as": f"box {w}×{d}×{h}mm (W×D×H, heuristic)",
        "_pipeline": "heuristic",
    }


def _heuristic_params(user_prompt: str) -> Optional[dict]:
    """
    Zero-LLM path for common, well-structured prompts.
    Returns params or None if the prompt is too complex / ambiguous.
    """
    text = user_prompt.strip()
    low = text.lower()

    # Skip heuristics when complex features need the model
    complex_markers = (
        "hole", "bolt", "fillet", "chamfer", "shell", "hollow", "engrave",
        "emboss", "grid", "pattern", "text", "logo", "name",
    )
    # Allow simple compounds without those markers.
    # An explicit primitive word ("box", "cylinder", …) wins over a substring alias.
    compound = None if _PRIMITIVE_WORD.search(low) else match_compound_keyword(low)
    if compound and not any(m in low for m in complex_markers):
        params = {"shape": compound, **COMPOUND_DEFAULTS.get(compound, {})}
        # Pull a leading height/diameter if present: "water bottle 220mm tall"
        m = re.search(r"(\d+(?:\.\d+)?)\s*(mm|cm|m|in|inch)?\s*(tall|high|height)", low)
        if m and "height_mm" in COMPOUND_DEFAULTS.get(compound, {}):
            params["height_mm"] = _mm_from_match(m.group(1), m.group(2) or "mm")
        m = re.search(r"(\d+(?:\.\d+)?)\s*(mm|cm|m|in)?\s*(wide|width)", low)
        if m and "width_mm" in COMPOUND_DEFAULTS.get(compound, {}):
            params["width_mm"] = _mm_from_match(m.group(1), m.group(2) or "mm")
        params = _apply_compound_counts(params, low, compound)
        params = apply_compound_defaults(params)
        params["_understood_as"] = compound
        params["_confidence"] = "high"
        params["_clarified_as"] = f"{compound.replace('_', ' ')} from prompt (heuristic)"
        params["_pipeline"] = "heuristic"
        return params

    if any(m in low for m in complex_markers):
        return None

    # box 50x30x20 (W×D×H) or "box 50mm wide, 60mm deep, 40mm tall"
    if re.search(r"\b(box|cube|block|cuboid|brick)\b", low):
        boxed = _box_from_text(low)
        if boxed:
            return boxed

    if re.search(r"\b(cylinder|rod|dowel|pillar)\b", low):
        dia = re.search(
            r"(\d+(?:\.\d+)?)\s*(mm|cm|m|in|inch|inches)?\s*(?:diameter|ø|dia)\b", low
        )
        ht = re.search(
            r"(\d+(?:\.\d+)?)\s*(mm|cm|m|in|inch|inches)?\s*(?:tall|high|height|long)\b", low
        )
        nums = re.findall(r"(\d+(?:\.\d+)?)\s*(mm|cm|m|in|inch|inches)?", low)
        if dia and ht:
            return {
                "shape": "cylinder",
                "diameter_mm": _mm_from_match(dia.group(1), dia.group(2) or "mm"),
                "height_mm": _mm_from_match(ht.group(1), ht.group(2) or "mm"),
                "_understood_as": "cylinder", "_confidence": "high",
                "_clarified_as": "cylinder (heuristic)", "_pipeline": "heuristic",
            }
        if dia is None and ht is None and len(nums) >= 2:
            return {
                "shape": "cylinder",
                "diameter_mm": _mm_from_match(nums[0][0], nums[0][1] or "mm"),
                "height_mm": _mm_from_match(nums[1][0], nums[1][1] or "mm"),
                "_understood_as": "cylinder", "_confidence": "high",
                "_clarified_as": "cylinder (heuristic)", "_pipeline": "heuristic",
            }

    if re.search(r"\b(sphere|ball|globe)\b", low):
        nums = re.findall(r"(\d+(?:\.\d+)?)\s*(mm|cm|m|in)?", low)
        if nums:
            return {
                "shape": "sphere",
                "diameter_mm": _mm_from_match(nums[0][0], nums[0][1] or "mm"),
                "_understood_as": "sphere", "_confidence": "high",
                "_clarified_as": "sphere (heuristic)", "_pipeline": "heuristic",
            }

    return None


def _offline_compound_params(user_prompt: str) -> Optional[dict]:
    """Build compound params without the LLM when keywords clearly match."""
    key = match_compound_keyword(user_prompt)
    if not key:
        return None
    params = {"shape": key, **COMPOUND_DEFAULTS.get(key, {})}
    params = _apply_compound_counts(params, (user_prompt or "").lower(), key)
    params["_understood_as"] = key
    params["_confidence"] = "medium"
    params["_clarified_as"] = f"{key.replace('_', ' ')} (default proportions from prompt: {user_prompt})"
    params["_pipeline"] = "offline_compound"
    return apply_compound_defaults(params)


def _finalize(params: dict, user_prompt: str) -> dict:
    shape = (params.get("shape") or "").strip().lower().replace(" ", "_")
    shape = ALIAS_FIX.get(shape, shape)
    params["shape"] = shape

    if shape in COMPOUND_BUILDERS:
        params.pop("missing_fields", None)
        params = apply_compound_defaults(params)
    elif shape not in _PRIMITIVES:
        # Only fill in a compound when the model did not already pick a real primitive.
        kw = match_compound_keyword(user_prompt)
        if kw:
            params["shape"] = kw
            params.pop("missing_fields", None)
            params = apply_compound_defaults(params)
            shape = kw

    # Normalize text_features modes for the CAD fast path
    feats = params.get("text_features")
    if isinstance(feats, list):
        low = user_prompt.lower()
        fixed = []
        for f in feats:
            if not isinstance(f, dict):
                continue
            nf = dict(f)
            txt = str(nf.get("text", "")).strip()
            if len(txt) > 24:
                nf["text"] = txt[:24]
            mode = (nf.get("mode") or "").lower()
            if not mode:
                if "engrave" in low or "etch" in low:
                    nf["mode"] = "engrave"
                elif "emboss" in low:
                    nf["mode"] = "emboss"
            if nf.get("mode") == "engrave":
                try:
                    nf["depth_mm"] = -abs(float(nf.get("depth_mm") or 1.5))
                except (TypeError, ValueError):
                    nf["depth_mm"] = -1.5
            fixed.append(nf)
        if fixed:
            params["text_features"] = fixed

    params.setdefault("_understood_as", shape)
    params.setdefault("_confidence", "medium")
    params.setdefault("_clarified_as", params.get("_clarified_as") or user_prompt)
    return params


def extract_params(user_prompt: str) -> dict:
    cached = _cache_get(user_prompt)
    if cached:
        out = dict(cached)
        out["_pipeline"] = "cache"
        return out

    # 1) Local heuristic — no network
    heuristic = _heuristic_params(user_prompt)
    if heuristic:
        return _cache_put(user_prompt, heuristic)

    if client is None:
        offline = _offline_compound_params(user_prompt)
        if offline:
            return _cache_put(user_prompt, offline)
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to a .env file, or use JSON Mode / "
            "/generate_manual. Everyday objects (bottle, chair, bed, …) also work "
            "offline by name when the API key is missing."
        )

    # 2) Single LLM call (was: normalize + extract = 2 round-trips)
    try:
        raw = _chat(FAST_EXTRACT_PROMPT, user_prompt, temperature=0.0, max_tokens=700)
        params = json.loads(raw)
    except (json.JSONDecodeError, RuntimeError) as e:
        offline = _offline_compound_params(user_prompt)
        if offline:
            return _cache_put(user_prompt, offline)
        return {
            "shape": "unknown",
            "missing_fields": [],
            "_error": "I couldn't parse a response for that description.",
            "_suggestion": "Try rephrasing with clearer shape and dimensions, or name an object like 'water bottle' or 'chair'.",
            "_pipeline": f"llm_error:{type(e).__name__}",
        }

    if not params.get("shape"):
        offline = _offline_compound_params(user_prompt)
        if offline:
            return _cache_put(user_prompt, offline)
        return {
            "shape": "unknown",
            "missing_fields": [],
            "_error": "I could not identify a 3D shape from your description.",
            "_suggestion": "Try a primitive (box, cylinder, …) or an everyday object.",
            "_pipeline": "unknown_shape",
        }

    params = _finalize(params, user_prompt)
    params["_pipeline"] = "llm_single"
    return _cache_put(user_prompt, params)


def edit_params(previous: dict, edit: str) -> dict:
    clean_prev = {k: v for k, v in previous.items() if not k.startswith("_")}
    shape = clean_prev.get("shape")

    # Tiny local edits — avoid LLM for obvious dimension tweaks
    local = _local_edit(clean_prev, edit)
    if local is not None:
        from app.params_utils import sanitize_params
        return sanitize_params(local)

    prompt = f"""
Previous CAD JSON: {json.dumps(clean_prev, separators=(',', ':'))}
Edit request: "{edit}"
Return the FULL updated JSON. Change only what the edit implies.
Keep compound shape ({_COMPOUND_LIST}) unless the object type changes.
Chair/backrest hole → circ_hole_face="back". Engrave text → text_features with mode "engrave" and negative depth_mm.
"""
    raw = _chat(FAST_EXTRACT_PROMPT, prompt, temperature=0.0, max_tokens=800)

    if not raw:
        return clean_prev

    try:
        params = json.loads(raw)
    except json.JSONDecodeError:
        return clean_prev

    if params.get("shape") in COMPOUND_BUILDERS or shape in COMPOUND_BUILDERS:
        if shape in COMPOUND_BUILDERS and params.get("shape") not in COMPOUND_BUILDERS:
            params["shape"] = shape
        params = apply_compound_defaults(params)

    edit_l = edit.lower()
    if params.get("shape") == "chair" and params.get("circ_hole_dia_mm"):
        if any(w in edit_l for w in ("backrest", "back rest", "back of the chair", "in the back")):
            params["circ_hole_face"] = "back"

    params = _finalize(params, edit)
    params["_pipeline"] = "llm_edit"

    from app.params_utils import sanitize_params
    return sanitize_params(params)


def _local_edit(prev: dict, edit: str) -> Optional[dict]:
    """Handle 'make it 10mm taller', 'scale width to 80mm' without LLM."""
    low = edit.lower().strip()
    out = dict(prev)

    m = re.search(r"(?:make (?:it )?|add )?(\d+(?:\.\d+)?)\s*mm\s*taller", low)
    if m and "height_mm" in out:
        out["height_mm"] = float(out["height_mm"]) + float(m.group(1))
        out["_clarified_as"] = f"height +{m.group(1)}mm (local edit)"
        out["_pipeline"] = "local_edit"
        return out

    m = re.search(r"(?:make (?:it )?|add )?(\d+(?:\.\d+)?)\s*mm\s*(?:shorter|smaller height)", low)
    if m and "height_mm" in out:
        out["height_mm"] = max(float(out["height_mm"]) - float(m.group(1)), 0.5)
        out["_clarified_as"] = f"height -{m.group(1)}mm (local edit)"
        out["_pipeline"] = "local_edit"
        return out

    m = re.search(r"(?:make (?:it )?|add )?(\d+(?:\.\d+)?)\s*mm\s*wider", low)
    if m and "width_mm" in out:
        out["width_mm"] = float(out["width_mm"]) + float(m.group(1))
        out["_clarified_as"] = f"width +{m.group(1)}mm (local edit)"
        out["_pipeline"] = "local_edit"
        return out

    m = re.search(r"(?:make (?:it )?|add )?(\d+(?:\.\d+)?)\s*mm\s*(?:narrower|less wide)", low)
    if m and "width_mm" in out:
        out["width_mm"] = max(float(out["width_mm"]) - float(m.group(1)), 0.5)
        out["_clarified_as"] = f"width -{m.group(1)}mm (local edit)"
        out["_pipeline"] = "local_edit"
        return out

    m = re.search(r"(?:make (?:it )?|add )?(\d+(?:\.\d+)?)\s*mm\s*deeper", low)
    if m and "depth_mm" in out:
        out["depth_mm"] = float(out["depth_mm"]) + float(m.group(1))
        out["_clarified_as"] = f"depth +{m.group(1)}mm (local edit)"
        out["_pipeline"] = "local_edit"
        return out

    m = re.search(r"(?:make (?:it )?|add )?(\d+(?:\.\d+)?)\s*mm\s*(?:shallower|less deep)", low)
    if m and "depth_mm" in out:
        out["depth_mm"] = max(float(out["depth_mm"]) - float(m.group(1)), 0.5)
        out["_clarified_as"] = f"depth -{m.group(1)}mm (local edit)"
        out["_pipeline"] = "local_edit"
        return out

    m = re.search(r"(?:set |make )?width\s*(?:to |= )?(\d+(?:\.\d+)?)\s*mm", low)
    if m and "width_mm" in out:
        out["width_mm"] = float(m.group(1))
        out["_pipeline"] = "local_edit"
        return out

    m = re.search(r"(?:set |make )?height\s*(?:to |= )?(\d+(?:\.\d+)?)\s*mm", low)
    if m and "height_mm" in out:
        out["height_mm"] = float(m.group(1))
        out["_pipeline"] = "local_edit"
        return out

    m = re.search(r"(?:set |make )?diameter\s*(?:to |= )?(\d+(?:\.\d+)?)\s*mm", low)
    if m and "diameter_mm" in out:
        out["diameter_mm"] = float(m.group(1))
        out["_pipeline"] = "local_edit"
        return out

    m = re.search(r"(?:set |make )?depth\s*(?:to |= )?(\d+(?:\.\d+)?)\s*mm", low)
    if m and "depth_mm" in out:
        out["depth_mm"] = float(m.group(1))
        out["_clarified_as"] = f"depth = {m.group(1)}mm (local edit)"
        out["_pipeline"] = "local_edit"
        return out

    if low in ("remove the hole", "remove hole", "no hole", "delete hole"):
        for k in list(out.keys()):
            if "hole" in k:
                out.pop(k, None)
        out["_pipeline"] = "local_edit"
        return out

    return None
