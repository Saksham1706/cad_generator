# Density in g/cm^3 and approximate raw-material cost in USD/kg (rough market reference, not a quote).
MATERIALS = {
    "pla":       {"label": "PLA Plastic",        "density_g_cm3": 1.24, "cost_per_kg": 20.0},
    "abs":       {"label": "ABS Plastic",        "density_g_cm3": 1.04, "cost_per_kg": 18.0},
    "petg":      {"label": "PETG Plastic",       "density_g_cm3": 1.27, "cost_per_kg": 22.0},
    "nylon":     {"label": "Nylon",              "density_g_cm3": 1.15, "cost_per_kg": 30.0},
    "resin":     {"label": "SLA Resin",          "density_g_cm3": 1.10, "cost_per_kg": 45.0},
    "aluminum":  {"label": "Aluminum",           "density_g_cm3": 2.70, "cost_per_kg": 2.5},
    "steel":     {"label": "Steel",              "density_g_cm3": 7.85, "cost_per_kg": 0.8},
    "stainless": {"label": "Stainless Steel",    "density_g_cm3": 8.00, "cost_per_kg": 3.5},
    "brass":     {"label": "Brass",              "density_g_cm3": 8.50, "cost_per_kg": 6.0},
    "titanium":  {"label": "Titanium",           "density_g_cm3": 4.51, "cost_per_kg": 20.0},
    "copper":    {"label": "Copper",              "density_g_cm3": 8.96, "cost_per_kg": 8.5},
    "oak":       {"label": "Oak Wood",           "density_g_cm3": 0.75, "cost_per_kg": 3.0},
    "acrylic":   {"label": "Acrylic",            "density_g_cm3": 1.18, "cost_per_kg": 4.0},
}

DEFAULT_MATERIAL = "pla"

def list_materials() -> list:
    return [{"id": k, **v} for k, v in MATERIALS.items()]

def weight_grams(volume_mm3: float, material: str) -> float:
    mat = MATERIALS.get(material, MATERIALS[DEFAULT_MATERIAL])
    volume_cm3 = volume_mm3 / 1000.0
    return round(volume_cm3 * mat["density_g_cm3"], 2)


def material_cost(volume_mm3: float, material: str) -> float:
    mat = MATERIALS.get(material, MATERIALS[DEFAULT_MATERIAL])
    weight_kg = weight_grams(volume_mm3, material) / 1000.0
    return round(weight_kg * mat["cost_per_kg"], 2)
