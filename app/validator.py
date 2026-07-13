MAX_DIMENSION_MM = 2000   # sanity ceiling so someone doesn't accidentally ask for a 5km box
MIN_WALL_MM = 0.4         # thinnest wall most printers/machines can realistically produce


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
    }
    keys = keys_by_shape.get(shape, [])
    return [p[k] for k in keys if p.get(k)]


def validate_geometry(p: dict) -> list:
    errors = []
    shape = p.get("shape")

    if p.get("missing_fields"):
        for f in p["missing_fields"]:
            errors.append(f"Missing value: '{f}' — please specify this dimension.")
        return errors  # no point validating further until the basics are filled in

    # Every *_mm field must be positive (emboss depth is allowed negative for engraving)
    for k, v in p.items():
        if k.endswith("_mm") and isinstance(v, (int, float)):
            if k == "emboss_depth_mm":
                continue
            if v <= 0:
                errors.append(f"'{k}' must be greater than 0. You gave: {v}")
            elif v > MAX_DIMENSION_MM:
                errors.append(f"'{k}' of {v}mm is unreasonably large (max supported: {MAX_DIMENSION_MM}mm).")

    for feat in (p.get("text_features") or []):
        d = feat.get("depth_mm")
        if isinstance(d, (int, float)) and d == 0:
            errors.append("A text feature has a depth of 0mm — it won't be visible.")

    dims = _dims_for(shape, p)
    min_dim = min(dims) if dims else 999

    # ---- edge treatment ----
    if p.get("edge_treatment") and p.get("edge_radius_mm"):
        radius = p["edge_radius_mm"]
        if radius >= min_dim / 2:
            errors.append(
                f"The {p['edge_treatment']} radius ({radius}mm) is too large for an object with a "
                f"minimum dimension of {min_dim}mm. It must be less than half the smallest side."
            )

    # ---- shell ----
    if p.get("shell_thickness_mm"):
        thickness = p["shell_thickness_mm"]
        if thickness < MIN_WALL_MM:
            errors.append(f"Shell thickness ({thickness}mm) is thinner than the practical minimum ({MIN_WALL_MM}mm).")
        if thickness >= min_dim / 2:
            errors.append(f"Shell thickness ({thickness}mm) is too large — it would consume the entire part.")

    # ---- shape-specific checks ----
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
        if p.get("top_diameter_mm", 0) >= p.get("base_diameter_mm", 999):
            errors.append("Cone top diameter must be smaller than base diameter.")

    if shape == "pyramid":
        tw, td = p.get("top_width_mm", 0), p.get("top_depth_mm", 0)
        if (tw and not td) or (td and not tw):
            errors.append("For a frustum (flat-top pyramid) specify both top_width_mm and top_depth_mm.")

    if shape == "prism":
        sides = p.get("sides", 6)
        if not (3 <= sides <= 20):
            errors.append(f"Prism sides ({sides}) must be between 3 and 20.")

    if shape == "star":
        points = p.get("points", 5)
        if not (3 <= points <= 16):
            errors.append(f"Star points ({points}) must be between 3 and 16.")
        outer, inner = p.get("outer_diameter_mm", 0), p.get("inner_diameter_mm", 0)
        if inner >= outer:
            errors.append(f"Star inner diameter ({inner}mm) must be less than outer diameter ({outer}mm).")

    # ---- hole / feature checks against the face they sit on ----
    face_w = p.get("width_mm", p.get("base_width_mm", 999))
    face_d = p.get("depth_mm", p.get("base_depth_mm", 999))
    height = p.get("height_mm", 999)

    circ_dia = p.get("circ_hole_dia_mm", p.get("hole_diameter_mm"))
    if circ_dia:
        depth = p.get("circ_hole_depth_mm", p.get("hole_depth_mm", 0))
        if circ_dia >= min(face_w, face_d):
            errors.append(f"Circular hole diameter ({circ_dia}mm) is too large for the face ({min(face_w, face_d)}mm).")
        if depth and depth > height:
            errors.append(f"Circular hole depth ({depth}mm) is deeper than the part height ({height}mm).")

    sq_side = p.get("sq_hole_side_mm", p.get("hole_side_mm"))
    if sq_side:
        depth = p.get("sq_hole_depth_mm", p.get("hole_depth_mm", 0))
        if sq_side >= min(face_w, face_d):
            errors.append(f"Square hole side ({sq_side}mm) is too large for the face ({min(face_w, face_d)}mm).")
        if depth and depth > height:
            errors.append(f"Square hole depth ({depth}mm) is deeper than the part height ({height}mm).")

    # ---- pattern sanity (won't fit / overlapping holes) ----
    for pattern_key, size_key in (("circ_hole_pattern", "circ_hole_dia_mm"), ("sq_hole_pattern", "sq_hole_side_mm")):
        pattern = p.get(pattern_key)
        size = p.get(size_key, 0)
        if not pattern or not size:
            continue
        if pattern.get("type") == "linear":
            sx = pattern.get("spacing_x_mm", 10)
            sy = pattern.get("spacing_y_mm", 10)
            if sx < size or sy < size:
                errors.append("Hole pattern spacing is smaller than the hole size — the holes would overlap.")
            cols, rows = pattern.get("count_x", 1), pattern.get("count_y", 1)
            span_x = (cols - 1) * sx + size
            span_y = (rows - 1) * sy + size
            if span_x > face_w or span_y > face_d:
                errors.append(f"The hole pattern ({span_x:.0f}x{span_y:.0f}mm) doesn't fit on the face ({face_w}x{face_d}mm).")
        elif pattern.get("type") == "polar":
            radius = pattern.get("radius_mm", 10)
            if radius * 2 + size > min(face_w, face_d):
                errors.append("The bolt-circle pattern is too large to fit on the face.")

    return errors
