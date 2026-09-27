"""
Normalize LLM / user CAD params so downstream code never crashes on
slightly-wrong types (e.g. circ_hole_pattern: "single").
"""

from app.compounds import COMPOUND_BUILDERS, apply_compound_defaults


_FACE_ALIASES = {
    "backrest": "back",
    "back rest": "back",
    "back-rest": "back",
    "rear": "back",
    "seat": "top",
    "seat top": "top",
    "cushion": "top",
    "headboard": "back",
}


def _normalize_pattern(pattern):
    """Coerce pattern to a dict or None. Strings like 'single' / 'center' → None."""
    if pattern is None or pattern is False:
        return None
    if isinstance(pattern, dict):
        ptype = (pattern.get("type") or "single").lower()
        if ptype in ("single", "center", "none", ""):
            return None
        out = dict(pattern)
        out["type"] = ptype
        for ck in ("count", "count_x", "count_y"):
            if ck in out and out[ck] is not None:
                try:
                    out[ck] = int(float(out[ck]))
                except (TypeError, ValueError):
                    pass
        for pk, pv in list(out.items()):
            if pk.endswith("_mm") or pk.endswith("_mm4"):
                try:
                    out[pk] = float(pv)
                except (TypeError, ValueError):
                    pass
        return out
    if isinstance(pattern, str):
        low = pattern.strip().lower()
        if low in ("single", "center", "none", "one", ""):
            return None
        # Sometimes the model returns JSON as a string
        if low.startswith("{"):
            try:
                import json
                return _normalize_pattern(json.loads(pattern))
            except Exception:
                return None
        return None
    return None


def _normalize_face(face) -> str:
    if not face:
        return "top"
    key = str(face).strip().lower()
    return _FACE_ALIASES.get(key, key)


def sanitize_params(params: dict) -> dict:
    """Return a cleaned copy safe for validate / build / DFM."""
    if not isinstance(params, dict):
        return {}
    out = dict(params)

    if out.get("shape") in COMPOUND_BUILDERS:
        out = apply_compound_defaults(out)

    for key in ("circ_hole_pattern", "sq_hole_pattern", "square_hole_pattern"):
        if key in out:
            out[key] = _normalize_pattern(out.get(key))
            if out[key] is None:
                out.pop(key, None)

    # Engine and validator read sq_hole_pattern; LLM/JSON often says square_hole_pattern.
    if out.get("square_hole_pattern") and not out.get("sq_hole_pattern"):
        out["sq_hole_pattern"] = out["square_hole_pattern"]
    out.pop("square_hole_pattern", None)

    if "circ_hole_face" in out:
        out["circ_hole_face"] = _normalize_face(out.get("circ_hole_face"))
    if "sq_hole_face" in out:
        out["sq_hole_face"] = _normalize_face(out.get("sq_hole_face"))
    if "hole_face" in out:
        out["hole_face"] = _normalize_face(out.get("hole_face"))

    # Alias square hole keys
    if out.get("square_hole_size_mm") and not out.get("sq_hole_side_mm"):
        out["sq_hole_side_mm"] = out["square_hole_size_mm"]

    # Numeric coercion for common hole fields
    for key in (
        "circ_hole_dia_mm", "circ_hole_depth_mm", "sq_hole_side_mm", "sq_hole_depth_mm",
        "hole_diameter_mm", "hole_depth_mm", "hole_side_mm", "square_hole_size_mm",
    ):
        if key in out and out[key] is not None:
            try:
                out[key] = float(out[key])
            except (TypeError, ValueError):
                out.pop(key, None)

    for key in ("sides", "points", "shelf_count", "leg_count"):
        if key in out and out[key] is not None:
            try:
                out[key] = int(float(out[key]))
            except (TypeError, ValueError):
                pass

    # Chair / furniture: if user asked for a backrest hole, prefer face=back
    clarified = (out.get("_clarified_as") or "").lower()
    if out.get("shape") == "chair" and out.get("circ_hole_dia_mm"):
        face = out.get("circ_hole_face", "top")
        if any(w in clarified for w in ("backrest", "back rest", "back of")):
            out["circ_hole_face"] = "back"
        elif face == "top" and "back" in clarified:
            out["circ_hole_face"] = "back"

    return out
