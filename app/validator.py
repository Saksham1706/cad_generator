def validate_geometry(p: dict) -> list:
    errors = []
    shape = p.get("shape")

    if p.get("missing_fields"):
        for f in p["missing_fields"]:
            errors.append(f"Missing value: '{f}' — please specify this dimension.")

    for k, v in p.items():
        if "mm" in k and isinstance(v, (int, float)) and v <= 0:
            errors.append(f"'{k}' must be greater than 0. You gave: {v}")

    if shape == "hollow_cylinder":
        od, id_ = p.get("outer_diameter_mm", 0), p.get("inner_diameter_mm", 0)
        if id_ >= od:
            errors.append(f"Inner diameter ({id_}mm) must be less than outer diameter ({od}mm).")
        elif (od - id_) / 2 < 0.5:
            errors.append(f"Wall thickness is only {(od-id_)/2}mm — too thin. Increase outer or decrease inner diameter.")

    if shape == "box_with_hole":
        hole = p.get("hole_diameter_mm", 0)
        w, d = p.get("width_mm", 999), p.get("depth_mm", 999)
        if hole >= min(w, d):
            errors.append(f"Hole ({hole}mm) is too large for the box face ({min(w,d)}mm). Reduce hole size.")

    if shape == "cone":
        if p.get("top_diameter_mm", 0) >= p.get("base_diameter_mm", 999):
            errors.append("Cone top diameter must be smaller than base diameter.")

    return errors