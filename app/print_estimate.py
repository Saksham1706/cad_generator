"""
Rough FDM print-time / filament estimates from solid volume.
Heuristic only — useful for planning, not a slicer substitute.
"""

from app.materials import MATERIALS, DEFAULT_MATERIAL

# Typical FDM defaults
DEFAULT_LAYER_MM = 0.2
DEFAULT_NOZZLE_MM = 0.4
DEFAULT_INFILL = 0.2  # 20%
DEFAULT_PRINT_SPEED_MM_S = 50
DEFAULT_WALLS = 2


def estimate_print(volume_mm3: float, bbox: dict, material: str = None) -> dict:
    """
    Estimate filament length/weight and print time from volume + bounding box.

    Assumptions:
    - Outer shell ≈ walls * perimeter of bbox footprint * height / layer
    - Interior ≈ volume * infill
    - Time ≈ extruded length / speed + 15% overhead
    """
    mat_id = material or DEFAULT_MATERIAL
    mat = MATERIALS.get(mat_id, MATERIALS[DEFAULT_MATERIAL])
    is_fdm = mat_id in ("pla", "abs", "petg", "nylon", "acrylic")

    vol = max(float(volume_mm3 or 0), 0)
    bx = float(bbox.get("x") or 0)
    by = float(bbox.get("y") or 0)
    bz = float(bbox.get("z") or 0)

    layer = DEFAULT_LAYER_MM
    infill = DEFAULT_INFILL
    speed = DEFAULT_PRINT_SPEED_MM_S
    walls = DEFAULT_WALLS
    nozzle = DEFAULT_NOZZLE_MM

    # Effective solid volume for FDM (shell + sparse fill)
    shell_frac = min(0.55, 0.15 + walls * 0.08)
    effective_mm3 = vol * (shell_frac + (1 - shell_frac) * infill) if is_fdm else vol

    density = mat["density_g_cm3"]
    filament_g = round((effective_mm3 / 1000.0) * density, 2)

    # 1.75mm filament cross-section
    filament_area_mm2 = 3.14159 * (1.75 / 2) ** 2
    filament_m = round((effective_mm3 / filament_area_mm2) / 1000.0, 2) if filament_area_mm2 else 0

    # Extruded path length ≈ volume / (nozzle width * layer)
    bead_area = max(nozzle * layer, 0.01)
    path_mm = effective_mm3 / bead_area
    seconds = path_mm / max(speed, 1) * 1.15  # overhead for travel/retract
    # Tall thin parts take longer (more layers)
    layers = max(bz / layer, 1) if bz else 1
    seconds *= 1.0 + min(layers / 800.0, 0.4)

    minutes = round(seconds / 60.0, 1)
    hours = round(seconds / 3600.0, 2)

    return {
        "applicable": is_fdm,
        "layer_height_mm": layer,
        "infill_pct": int(infill * 100),
        "nozzle_mm": nozzle,
        "filament_g": filament_g,
        "filament_m": filament_m,
        "est_minutes": minutes,
        "est_hours": hours,
        "note": (
            "Rough FDM estimate (not a slicer). "
            if is_fdm
            else "Print estimate applies to FDM plastics; this material is typically CNC/cast."
        ),
        "bbox_mm": {"x": bx, "y": by, "z": bz},
    }
