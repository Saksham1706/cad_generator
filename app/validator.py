MAX_DIMENSION_MM = 2000   # sanity ceiling so someone doesn't accidentally ask for a 5km box
MIN_WALL_MM = 0.4         # thinnest wall most printers/machines can realistically produce

from app.compounds import COMPOUND_BUILDERS, apply_compound_defaults
from app.params_utils import sanitize_params


def _dims_for(shape: str, p: dict) -> list:
    keys_by_shape = {
        "box": ["width_mm", "height_mm", "depth_mm"],
        "cylinder": ["diameter_mm", "height_mm"],
        "hollow_cylinder": ["outer_diameter_mm", "height_mm"],
        "sphere": ["diameter_mm"],
        "hemisphere": ["diameter_mm"],
        "cone": ["base_diameter_mm", "height_mm"],
        "torus": ["torus_diameter_mm", "tube_diameter_mm"],
        "prism": ["width_mm", "height_mm"],
        "pyramid": ["base_width_mm", "base_depth_mm", "height_mm"],
        "star": ["outer_diameter_mm", "height_mm"],
        "water_bottle": ["height_mm", "body_diameter_mm"],
        "mug": ["diameter_mm", "height_mm"],
        "chair": ["seat_width_mm", "seat_depth_mm", "seat_height_mm"],
        "table": ["width_mm", "depth_mm", "height_mm"],
        "bed": ["width_mm", "length_mm", "height_mm"],
        "stool": ["diameter_mm", "height_mm"],
        "vase": ["base_diameter_mm", "height_mm"],
        "bowl": ["diameter_mm"],
        "bookshelf": ["width_mm", "depth_mm", "height_mm"],
        "phone_stand": ["width_mm", "depth_mm", "height_mm"],
        "lamp": ["base_diameter_mm", "stem_height_mm"],
        "goblet": ["bowl_diameter_mm", "stem_height_mm"],
        "dumbbell": ["bar_length_mm", "weight_diameter_mm"],
        "picture_frame": ["width_mm", "height_mm"],
        "coaster": ["diameter_mm", "height_mm"],
        "plate": ["diameter_mm"],
    }
    keys = keys_by_shape.get(shape, [])
    return [p[k] for k in keys if p.get(k)]


# Apex / frustum tops may be exactly 0 (a point). Every other mm field must be > 0.
_ZERO_OK_MM = {"top_diameter_mm", "top_width_mm", "top_depth_mm"}


def _as_int(value, default=None):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _face_size(shape: str, p: dict, face: str) -> tuple:
    """In-plane width and height of the face a hole is cut into."""
    face = (face or "top").lower()
    if shape in ("cylinder", "hollow_cylinder", "sphere", "hemisphere"):
        d = p.get("diameter_mm") or p.get("outer_diameter_mm") or 0
        return d, d
    if shape == "cone":
        d = p.get("top_diameter_mm") if face == "top" else p.get("base_diameter_mm")
        d = d or p.get("base_diameter_mm") or 0
        return d, d
    if shape == "star":
        d = p.get("outer_diameter_mm") or 0
        return d, d
    if shape == "torus":
        d = p.get("torus_diameter_mm") or 0
        return d, d
    if shape == "prism":
        w = p.get("width_mm") or 0
        return w, w
    if shape == "pyramid":
        return p.get("base_width_mm") or 0, p.get("base_depth_mm") or 0
    if face in ("front", "back"):
        return p.get("width_mm") or 0, p.get("height_mm") or 0
    if face in ("left", "right"):
        return p.get("depth_mm") or 0, p.get("height_mm") or 0
    return p.get("width_mm") or p.get("base_width_mm") or 0, p.get("depth_mm") or p.get("base_depth_mm") or 0


def _axis_thickness(shape: str, p: dict, face: str) -> float:
    """Material thickness along the hole axis for this face."""
    face = (face or "top").lower()
    if shape in ("cylinder", "hollow_cylinder", "sphere", "hemisphere", "cone", "star", "torus", "prism"):
        return p.get("height_mm") or p.get("diameter_mm") or p.get("base_diameter_mm") or 0
    if face in ("front", "back"):
        return p.get("depth_mm") or 0
    if face in ("left", "right"):
        return p.get("width_mm") or 0
    return p.get("height_mm") or 0


def validate_geometry(p: dict) -> list:
    errors = []
    p = sanitize_params(p)
    if p.get("shape") in COMPOUND_BUILDERS:
        p = apply_compound_defaults(p)

    shape = p.get("shape")

    if p.get("missing_fields") and shape not in COMPOUND_BUILDERS:
        for f in p["missing_fields"]:
            errors.append(f"Missing value: '{f}' — please specify this dimension.")
        return errors

    for k, v in p.items():
        if k.endswith("_mm") and isinstance(v, (int, float)):
            if k == "emboss_depth_mm":
                continue
            if v < 0 or (v == 0 and k not in _ZERO_OK_MM):
                errors.append(f"'{k}' must be greater than 0. You gave: {v}")
            elif shape in COMPOUND_BUILDERS:
                if v > 4000:
                    errors.append(f"'{k}' of {v}mm is unreasonably large (max 4000mm for furniture).")
            elif v > MAX_DIMENSION_MM:
                errors.append(f"'{k}' of {v}mm is unreasonably large (max supported: {MAX_DIMENSION_MM}mm).")

    for feat in (p.get("text_features") or []):
        d = feat.get("depth_mm")
        if isinstance(d, (int, float)) and d == 0:
            errors.append("A text feature has a depth of 0mm — it won't be visible.")

    dims = _dims_for(shape, p)
    min_dim = min(dims) if dims else 999

    if p.get("edge_treatment") and p.get("edge_radius_mm"):
        radius = p["edge_radius_mm"]
        if radius >= min_dim / 2 and shape not in COMPOUND_BUILDERS:
            errors.append(
                f"The {p['edge_treatment']} radius ({radius}mm) is too large for an object with a "
                f"minimum dimension of {min_dim}mm. It must be less than half the smallest side."
            )

    if p.get("shell_thickness_mm") and shape not in COMPOUND_BUILDERS:
        thickness = p["shell_thickness_mm"]
        if thickness < MIN_WALL_MM:
            errors.append(f"Shell thickness ({thickness}mm) is thinner than the practical minimum ({MIN_WALL_MM}mm).")
        if thickness >= min_dim / 2:
            errors.append(f"Shell thickness ({thickness}mm) is too large — it would consume the entire part.")

    if shape in COMPOUND_BUILDERS:
        if shape == "water_bottle":
            body = p.get("body_diameter_mm", 0)
            neck = p.get("neck_diameter_mm", 0)
            if neck and body and neck >= body:
                errors.append("Bottle neck diameter must be smaller than the body diameter.")
        if shape == "stool":
            n = _as_int(p.get("leg_count", 4))
            if n is None or not (3 <= n <= 6):
                errors.append("Stool leg_count must be a whole number between 3 and 6.")
        if shape == "bookshelf":
            n = _as_int(p.get("shelf_count", 3))
            if n is None or not (1 <= n <= 8):
                errors.append("Bookshelf shelf_count must be a whole number between 1 and 8.")
        # Hole size vs furniture boards
        dia = p.get("circ_hole_dia_mm")
        if dia and shape == "chair":
            face = (p.get("circ_hole_face") or "top").lower()
            if face in ("back", "backrest"):
                limit = min(p.get("seat_width_mm", 999), p.get("back_height_mm", 999)) * 0.9
            else:
                limit = min(p.get("seat_width_mm", 999), p.get("seat_depth_mm", 999)) * 0.9
            if dia >= limit:
                errors.append(
                    f"Hole diameter ({dia}mm) is too large for the chair {face} "
                    f"(max ~{limit:.0f}mm)."
                )
        return errors

    if shape == "hollow_cylinder":
        od = p.get("outer_diameter_mm", 0)
        id_ = p.get("inner_diameter_mm", 0)
        if id_ >= od:
            errors.append(f"Inner diameter ({id_}mm) must be less than outer diameter ({od}mm).")
        elif (od - id_) / 2 < MIN_WALL_MM:
            errors.append(f"Wall thickness is only {(od - id_) / 2}mm — too thin.")

    if shape == "torus":
        major = p.get("torus_diameter_mm", 0)
        tube = p.get("tube_diameter_mm", 0)
        if tube >= major:
            errors.append(f"Tube diameter ({tube}mm) must be smaller than the overall torus diameter ({major}mm).")

    if shape == "cone":
        top = p.get("top_diameter_mm", 0) or 0
        base = p.get("base_diameter_mm", 0) or 0
        if base and top >= base:
            errors.append("Cone top diameter must be smaller than base diameter.")

    if shape == "pyramid":
        tw, td = p.get("top_width_mm", 0), p.get("top_depth_mm", 0)
        if (tw and not td) or (td and not tw):
            errors.append("For a frustum (flat-top pyramid) specify both top_width_mm and top_depth_mm.")

    if shape == "prism":
        sides = _as_int(p.get("sides", 6))
        if sides is None or not (3 <= sides <= 20):
            errors.append(f"Prism sides ({p.get('sides')}) must be a whole number between 3 and 20.")

    if shape == "star":
        points = _as_int(p.get("points", 5))
        if points is None or not (3 <= points <= 16):
            errors.append(f"Star points ({p.get('points')}) must be a whole number between 3 and 16.")
        outer, inner = p.get("outer_diameter_mm", 0), p.get("inner_diameter_mm", 0)
        if inner >= outer:
            errors.append(f"Star inner diameter ({inner}mm) must be less than outer diameter ({outer}mm).")

    circ_face = p.get("circ_hole_face", p.get("hole_face", "top"))
    sq_face = p.get("sq_hole_face", p.get("hole_face", "top"))
    circ_fw, circ_fd = _face_size(shape, p, circ_face)
    sq_fw, sq_fd = _face_size(shape, p, sq_face)

    circ_dia = p.get("circ_hole_dia_mm", p.get("hole_diameter_mm"))
    if circ_dia:
        depth = p.get("circ_hole_depth_mm", p.get("hole_depth_mm", 0)) or 0
        face_span = min(circ_fw, circ_fd) if circ_fw and circ_fd else 0
        if face_span and circ_dia >= face_span:
            errors.append(f"Circular hole diameter ({circ_dia}mm) is too large for the face ({face_span}mm).")
        thick = _axis_thickness(shape, p, circ_face)
        if depth and thick and depth > thick:
            errors.append(
                f"Circular hole depth ({depth}mm) is deeper than the {circ_face} face thickness ({thick}mm)."
            )

    sq_side = p.get("sq_hole_side_mm", p.get("hole_side_mm"))
    if sq_side:
        depth = p.get("sq_hole_depth_mm", p.get("hole_depth_mm", 0)) or 0
        face_span = min(sq_fw, sq_fd) if sq_fw and sq_fd else 0
        if face_span and sq_side >= face_span:
            errors.append(f"Square hole side ({sq_side}mm) is too large for the face ({face_span}mm).")
        thick = _axis_thickness(shape, p, sq_face)
        if depth and thick and depth > thick:
            errors.append(
                f"Square hole depth ({depth}mm) is deeper than the {sq_face} face thickness ({thick}mm)."
            )

    for pattern_key, size_key, fw, fd in (
        ("circ_hole_pattern", "circ_hole_dia_mm", circ_fw, circ_fd),
        ("sq_hole_pattern", "sq_hole_side_mm", sq_fw, sq_fd),
    ):
        pattern = p.get(pattern_key)
        size = p.get(size_key, 0)
        if not isinstance(pattern, dict) or not size or not fw or not fd:
            continue
        if pattern.get("type") == "linear":
            sx = pattern.get("spacing_x_mm", 10)
            sy = pattern.get("spacing_y_mm", 10)
            cols = _as_int(pattern.get("count_x", 1))
            rows = _as_int(pattern.get("count_y", 1))
            if cols is None or rows is None:
                errors.append("Hole pattern counts must be whole numbers.")
                continue
            if sx < size or sy < size:
                errors.append("Hole pattern spacing is smaller than the hole size — the holes would overlap.")
            span_x = (cols - 1) * sx + size
            span_y = (rows - 1) * sy + size
            if span_x > fw or span_y > fd:
                errors.append(f"The hole pattern ({span_x:.0f}x{span_y:.0f}mm) doesn't fit on the face ({fw}x{fd}mm).")
        elif pattern.get("type") == "polar":
            radius = pattern.get("radius_mm", 10)
            if radius * 2 + size > min(fw, fd):
                errors.append("The bolt-circle pattern is too large to fit on the face.")

    return errors
