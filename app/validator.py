def validate_geometry(p: dict) -> list:
    errors = []
    shape = p.get("shape")

    if p.get("missing_fields"):
        for f in p["missing_fields"]:
            errors.append(f"Missing value: '{f}' — please specify this dimension.")

    for k, v in p.items():
        if "mm" in k and isinstance(v, (int, float)) and v <= 0 and k != "emboss_depth_mm":
            # emboss_depth_mm can be negative for engraving
            errors.append(f"'{k}' must be greater than 0. You gave: {v}")

    # Geometry bounds checking for base shapes
    dims = [p.get(k) for k in ["width_mm", "height_mm", "depth_mm", "diameter_mm", "outer_diameter_mm"] if p.get(k)]
    min_dim = min(dims) if dims else 999

    # Edge Treatment Validation
    if p.get("edge_treatment") and p.get("edge_radius_mm"):
        radius = p["edge_radius_mm"]
        if radius >= min_dim / 2:
            errors.append(f"The {p['edge_treatment']} radius ({radius}mm) is too large for an object with a minimum dimension of {min_dim}mm. It must be less than half the smallest side.")

    if shape == "hollow_cylinder":
        od = p.get("outer_diameter_mm", 0)
        id_ = p.get("inner_diameter_mm", 0)
        if id_ >= od:
            errors.append(f"Inner diameter ({id_}mm) must be less than outer diameter ({od}mm).")
        elif (od - id_) / 2 < 0.5:
            errors.append(f"Wall thickness is only {(od-id_)/2}mm — too thin.")

    if shape == "box_with_hole":
        hole = p.get("hole_diameter_mm", 0)
        hole_depth = p.get("hole_depth_mm", 0)
        w, d = p.get("width_mm", 999), p.get("depth_mm", 999)
        h = p.get("height_mm", 999)
        if hole >= min(w, d):
            errors.append(f"Hole diameter ({hole}mm) is too large for the box face ({min(w,d)}mm).")
        if hole_depth > h:
            errors.append(f"Hole depth ({hole_depth}mm) is deeper than the box height ({h}mm).")

    if shape == "box_with_square_hole":
        side = p.get("hole_side_mm", 0)
        hole_depth = p.get("hole_depth_mm", 0)
        w, d = p.get("width_mm", 999), p.get("depth_mm", 999)
        h = p.get("height_mm", 999)
        if side >= min(w, d):
            errors.append(f"Hole side ({side}mm) is too large for the box face ({min(w,d)}mm).")
        if hole_depth > h:
            errors.append(f"Hole depth ({hole_depth}mm) is deeper than box height ({h}mm).")

    if shape == "cone":
        if p.get("top_diameter_mm", 0) >= p.get("base_diameter_mm", 999):
            errors.append("Cone top diameter must be smaller than base diameter.")

    return errors