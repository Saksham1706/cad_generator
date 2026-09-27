"""
Design-for-Manufacturability (DFM) / printability checks.
Runs on top of validated geometry params — advisory warnings, not hard failures.
"""

from app.materials import MATERIALS, DEFAULT_MATERIAL

MIN_PRINT_WALL_MM = 0.8
MIN_HOLE_DIA_MM = 1.5
MIN_EDGE_CLEARANCE_MM = 2.0
MAX_OVERHANG_HINT_DEG = 45  # informational for FDM


def _face_span(params: dict, face: str = "top") -> tuple:
    """Return (width, depth) of the given face in mm for clearance estimates."""
    shape = params.get("shape")
    if shape == "box":
        if face in ("top", "bottom"):
            return params.get("width_mm", 0), params.get("depth_mm", 0)
        if face in ("front", "back"):
            return params.get("width_mm", 0), params.get("height_mm", 0)
        return params.get("depth_mm", 0), params.get("height_mm", 0)
    if shape in ("cylinder", "hollow_cylinder", "sphere", "hemisphere", "cone"):
        d = (
            params.get("diameter_mm")
            or params.get("outer_diameter_mm")
            or params.get("base_diameter_mm")
            or 0
        )
        return d, d
    if shape == "prism":
        return params.get("width_mm", 0), params.get("width_mm", 0)
    if shape == "pyramid":
        return params.get("base_width_mm", 0), params.get("base_depth_mm", 0)
    if shape == "star":
        return params.get("outer_diameter_mm", 0), params.get("outer_diameter_mm", 0)
    if shape == "torus":
        return params.get("torus_diameter_mm", 0), params.get("torus_diameter_mm", 0)
    if shape == "table":
        return params.get("width_mm", 0), params.get("depth_mm", 0)
    if shape == "chair":
        return params.get("seat_width_mm", 0), params.get("seat_depth_mm", 0)
    if shape in ("bookshelf", "phone_stand", "picture_frame"):
        return params.get("width_mm", 0), params.get("depth_mm", params.get("height_mm", 0))
    if shape == "bed":
        return params.get("width_mm", 0), params.get("length_mm", 0)
    return 0, 0


# Hole diameters and edge radii are not the part's cross-section.
_MIN_DIM_SKIP = {
    "edge_radius_mm", "emboss_depth_mm", "shell_thickness_mm",
    "wall_mm", "thickness_mm", "border_mm", "rim_mm",
}


def _min_dim(params: dict) -> float:
    vals = []
    for k, v in params.items():
        if not (k.endswith("_mm") and isinstance(v, (int, float)) and v > 0):
            continue
        if "hole" in k or k in _MIN_DIM_SKIP:
            continue
        vals.append(v)
    return min(vals) if vals else 0


def analyze_dfm(params: dict) -> dict:
    """
    Return {score 0-100, grade A-F, checks: [{level, code, message}], summary}.
    level: ok | warn | fail
    """
    checks = []
    material = params.get("material", DEFAULT_MATERIAL)
    mat = MATERIALS.get(material, MATERIALS[DEFAULT_MATERIAL])
    is_plastic = material in ("pla", "abs", "petg", "nylon", "resin", "acrylic")

    # --- wall / shell ---
    shell = params.get("shell_thickness_mm")
    if shell is not None:
        if shell < MIN_PRINT_WALL_MM:
            checks.append({
                "level": "fail",
                "code": "thin_wall",
                "message": f"Wall thickness {shell}mm is below the recommended {MIN_PRINT_WALL_MM}mm for reliable printing.",
            })
        elif shell < 1.2:
            checks.append({
                "level": "warn",
                "code": "thin_wall",
                "message": f"Wall thickness {shell}mm is marginal — 1.2mm+ is safer for FDM.",
            })
        else:
            checks.append({
                "level": "ok",
                "code": "thin_wall",
                "message": f"Wall thickness {shell}mm looks good.",
            })

    if params.get("shape") == "hollow_cylinder":
        od = params.get("outer_diameter_mm", 0)
        id_ = params.get("inner_diameter_mm", 0)
        wall = (od - id_) / 2 if od and id_ else 0
        if wall and wall < MIN_PRINT_WALL_MM:
            checks.append({
                "level": "fail",
                "code": "pipe_wall",
                "message": f"Pipe wall {(wall):.2f}mm is too thin (min {MIN_PRINT_WALL_MM}mm).",
            })
        elif wall:
            checks.append({
                "level": "ok",
                "code": "pipe_wall",
                "message": f"Pipe wall {wall:.2f}mm is acceptable.",
            })

    # --- holes ---
    circ = params.get("circ_hole_dia_mm")
    if circ:
        if circ < MIN_HOLE_DIA_MM:
            checks.append({
                "level": "fail",
                "code": "tiny_hole",
                "message": f"Circular hole {circ}mm is too small to print cleanly (min ~{MIN_HOLE_DIA_MM}mm).",
            })
        elif circ < 2.5:
            checks.append({
                "level": "warn",
                "code": "tiny_hole",
                "message": f"Hole {circ}mm may need reaming or a drill pass after printing.",
            })
        else:
            checks.append({
                "level": "ok",
                "code": "tiny_hole",
                "message": f"Hole diameter {circ}mm is printable.",
            })

        face = params.get("circ_hole_face", "top")
        fw, fd = _face_span(params, face)
        pattern = params.get("circ_hole_pattern") or {}
        if not isinstance(pattern, dict):
            pattern = {}
        if pattern.get("type") == "polar" and pattern.get("radius_mm") and min(fw, fd) > 0:
            r = pattern["radius_mm"]
            edge_clear = min(fw, fd) / 2 - r - circ / 2
            if edge_clear < MIN_EDGE_CLEARANCE_MM:
                checks.append({
                    "level": "warn",
                    "code": "edge_clearance",
                    "message": f"Bolt circle leaves only ~{edge_clear:.1f}mm to the edge (prefer ≥{MIN_EDGE_CLEARANCE_MM}mm).",
                })
            else:
                checks.append({
                    "level": "ok",
                    "code": "edge_clearance",
                    "message": f"Hole-to-edge clearance ~{edge_clear:.1f}mm looks fine.",
                })

    sq = params.get("sq_hole_side_mm") or params.get("square_hole_size_mm")
    if sq:
        if sq < MIN_HOLE_DIA_MM:
            checks.append({
                "level": "fail",
                "code": "tiny_square",
                "message": f"Square hole {sq}mm is too small for clean fabrication.",
            })
        elif sq < 2.5:
            checks.append({
                "level": "warn",
                "code": "tiny_square",
                "message": f"Square hole {sq}mm is marginal for a clean print.",
            })
        else:
            checks.append({
                "level": "ok",
                "code": "tiny_square",
                "message": f"Square hole {sq}mm is a practical size.",
            })

    # --- fillets help printability ---
    if params.get("edge_treatment") == "fillet" and params.get("edge_radius_mm"):
        checks.append({
            "level": "ok",
            "code": "fillet",
            "message": "Fillets reduce stress concentrations and print better than sharp corners.",
        })
    elif params.get("edge_treatment") is None and params.get("shape") == "box" and is_plastic:
        checks.append({
            "level": "warn",
            "code": "sharp_corners",
            "message": "Consider a small fillet (0.5–1mm) — sharp corners can warp or stress-crack in plastic.",
        })

    # --- aspect ratio / tall thin parts ---
    min_d = _min_dim(params)
    h = params.get("height_mm") or params.get("base_depth_mm") or 0
    if h and min_d and h / min_d > 8:
        checks.append({
            "level": "warn",
            "code": "aspect_ratio",
            "message": f"Part is very tall relative to its cross-section (ratio {h/min_d:.1f}:1) — may tip during printing; add a brim/raft.",
        })

    # --- text depth ---
    for feat in params.get("text_features") or []:
        depth = abs(feat.get("depth_mm") or 0)
        if 0 < depth < 0.4:
            checks.append({
                "level": "warn",
                "code": "shallow_text",
                "message": f"Text '{feat.get('text', '')}' depth {depth}mm may not show clearly after printing.",
            })
        elif depth >= 0.4:
            checks.append({
                "level": "ok",
                "code": "text_depth",
                "message": f"Text '{feat.get('text', '')}' depth looks readable.",
            })

    # --- material note ---
    checks.append({
        "level": "ok",
        "code": "material",
        "message": f"Material set to {mat['label']} ({mat['density_g_cm3']} g/cm³).",
    })

    if is_plastic and params.get("shape") in ("torus",):
        checks.append({
            "level": "warn",
            "code": "supports",
            "message": "Torus / ring shapes usually need support material when printed flat or on-edge.",
        })

    fails = sum(1 for c in checks if c["level"] == "fail")
    warns = sum(1 for c in checks if c["level"] == "warn")
    oks = sum(1 for c in checks if c["level"] == "ok")

    score = max(0, min(100, 100 - fails * 25 - warns * 8))
    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    summary = f"{oks} passed, {warns} warnings, {fails} critical"
    return {
        "score": score,
        "grade": grade,
        "summary": summary,
        "checks": checks,
        "printable": fails == 0,
    }
