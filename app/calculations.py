import math
from app.engineering_materials import STRUCTURAL_MATERIALS, recommend_material

GRAVITY = 9.81  # m/s^2


def rectangular_section_properties(width_mm: float, height_mm: float) -> dict:
    """Second moment of area for a solid rectangular cross-section, bending about the horizontal axis."""
    I = width_mm * height_mm ** 3 / 12
    c = height_mm / 2  # distance from neutral axis to outer fiber
    return {"I_mm4": I, "c_mm": c}


def circular_section_properties(diameter_mm: float) -> dict:
    I = math.pi * diameter_mm ** 4 / 64
    c = diameter_mm / 2
    return {"I_mm4": I, "c_mm": c}


def analyze_beam(
    span_mm: float,
    load_kg: float,
    width_mm: float = None,
    height_mm: float = None,
    diameter_mm: float = None,
    support: str = "simply_supported",   # "simply_supported" or "cantilever"
    load_type: str = "point_center",     # "point_center" or "udl" (uniformly distributed)
    material: str = None,
    min_fos: float = 1.5,
) -> dict:
    """
    Deterministic beam bending/deflection calculation. Pure engineering formulas —
    no LLM reasoning involved anywhere in this function.
    """
    if diameter_mm:
        section = circular_section_properties(diameter_mm)
        section_desc = f"circular, {diameter_mm}mm diameter"
    elif width_mm and height_mm:
        section = rectangular_section_properties(width_mm, height_mm)
        section_desc = f"rectangular, {width_mm}x{height_mm}mm"
    else:
        raise ValueError("Provide either diameter_mm, or both width_mm and height_mm.")

    I = section["I_mm4"]
    c = section["c_mm"]
    P = load_kg * GRAVITY  # Newtons
    L = span_mm

    # ---- bending moment & deflection formulas ----
    if support == "simply_supported" and load_type == "point_center":
        M_max = P * L / 4
        defl_formula = "PL^3 / (48EI)"
    elif support == "simply_supported" and load_type == "udl":
        w = P / L  # N/mm, load spread evenly across the span
        M_max = w * L ** 2 / 8
        defl_formula = "5wL^4 / (384EI)"
    elif support == "cantilever" and load_type == "point_center":
        M_max = P * L
        defl_formula = "PL^3 / (3EI)"
    elif support == "cantilever" and load_type == "udl":
        w = P / L
        M_max = w * L ** 2 / 2
        defl_formula = "wL^4 / (8EI)"
    else:
        raise ValueError(f"Unsupported combination: support={support}, load_type={load_type}")

    sigma_max = M_max * c / I  # MPa (N/mm^2)

    def deflection_for(E_mpa: float) -> float:
        if support == "simply_supported" and load_type == "point_center":
            return P * L ** 3 / (48 * E_mpa * I)
        if support == "simply_supported" and load_type == "udl":
            w = P / L
            return 5 * w * L ** 4 / (384 * E_mpa * I)
        if support == "cantilever" and load_type == "point_center":
            return P * L ** 3 / (3 * E_mpa * I)
        if support == "cantilever" and load_type == "udl":
            w = P / L
            return w * L ** 4 / (8 * E_mpa * I)

    result = {
        "inputs": {
            "span_mm": L, "load_kg": load_kg, "support": support,
            "load_type": load_type, "section": section_desc,
        },
        "section_properties": {"I_mm4": round(I, 1), "c_mm": round(c, 2)},
        "max_bending_moment_Nmm": round(M_max, 1),
        "max_bending_stress_mpa": round(sigma_max, 2),
        "deflection_formula": defl_formula,
    }

    if material:
        mat = STRUCTURAL_MATERIALS.get(material)
        if not mat:
            raise ValueError(f"Unknown material '{material}'. Options: {list(STRUCTURAL_MATERIALS)}")
        fos = mat["yield_strength_mpa"] / sigma_max if sigma_max > 0 else float("inf")
        result["material"] = {
            "id": material, "label": mat["label"],
            "yield_strength_mpa": mat["yield_strength_mpa"],
            "factor_of_safety": round(fos, 2),
            "passes_min_fos": fos >= min_fos,
            "deflection_mm": round(deflection_for(mat["E_mpa"]), 3),
        }
    else:
        recs = recommend_material(sigma_max, min_fos=min_fos)
        result["recommended_materials"] = [
            {
                "id": r["id"], "label": r["label"], "fos": r["fos"],
                "cost_per_kg": r["cost_per_kg"],
                "deflection_mm": round(deflection_for(r["E_mpa"]), 3),
            }
            for r in recs
        ]
        if not recs:
            result["warning"] = (
                f"No standard material in the library reaches FOS {min_fos} at "
                f"{round(sigma_max, 1)} MPa bending stress with this cross-section. "
                f"Increase the section size or reduce the span/load."
            )

    return result
