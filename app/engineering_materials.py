# Structural material properties for engineering calculations.
# yield_strength_mpa: MPa. cost_per_kg: approximate USD/kg (rough market reference, not a quote).
# E_mpa: Young's modulus in MPa, used for deflection calculations.

STRUCTURAL_MATERIALS = {
    "mild_steel": {
        "label": "Mild Steel (A36)", "density_g_cm3": 7.85,
        "yield_strength_mpa": 250, "E_mpa": 200000, "cost_per_kg": 0.8,
    },
    "structural_steel": {
        "label": "Structural Steel (A572-50)", "density_g_cm3": 7.85,
        "yield_strength_mpa": 345, "E_mpa": 200000, "cost_per_kg": 1.0,
    },
    "stainless_304": {
        "label": "Stainless Steel 304", "density_g_cm3": 8.00,
        "yield_strength_mpa": 215, "E_mpa": 193000, "cost_per_kg": 3.5,
    },
    "aluminum_6061": {
        "label": "Aluminum 6061-T6", "density_g_cm3": 2.70,
        "yield_strength_mpa": 276, "E_mpa": 69000, "cost_per_kg": 2.5,
    },
    "cast_iron": {
        "label": "Cast Iron (Grey)", "density_g_cm3": 7.20,
        "yield_strength_mpa": 130, "E_mpa": 110000, "cost_per_kg": 0.6,
    },
    "titanium": {
        "label": "Titanium Grade 5", "density_g_cm3": 4.43,
        "yield_strength_mpa": 828, "E_mpa": 114000, "cost_per_kg": 20.0,
    },
}


def list_structural_materials() -> list:
    return [{"id": k, **v} for k, v in STRUCTURAL_MATERIALS.items()]


def recommend_material(required_stress_mpa: float, min_fos: float = 1.5, sort_by: str = "cost_per_kg") -> list:
    """
    Return every structural material whose yield strength gives at least
    `min_fos` factor of safety against `required_stress_mpa`, cheapest first.
    """
    candidates = []
    for mat_id, props in STRUCTURAL_MATERIALS.items():
        fos = props["yield_strength_mpa"] / required_stress_mpa if required_stress_mpa > 0 else float("inf")
        if fos >= min_fos:
            candidates.append({"id": mat_id, **props, "fos": round(fos, 2)})
    candidates.sort(key=lambda m: m[sort_by])
    return candidates
