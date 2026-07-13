# Density values in g/cm^3, used to estimate print/part weight from volume.
MATERIALS = {
    "pla":       {"label": "PLA Plastic",        "density_g_cm3": 1.24},
    "abs":       {"label": "ABS Plastic",        "density_g_cm3": 1.04},
    "petg":      {"label": "PETG Plastic",       "density_g_cm3": 1.27},
    "nylon":     {"label": "Nylon",              "density_g_cm3": 1.15},
    "resin":     {"label": "SLA Resin",          "density_g_cm3": 1.10},
    "aluminum":  {"label": "Aluminum",           "density_g_cm3": 2.70},
    "steel":     {"label": "Steel",              "density_g_cm3": 7.85},
    "stainless": {"label": "Stainless Steel",    "density_g_cm3": 8.00},
    "brass":     {"label": "Brass",              "density_g_cm3": 8.50},
    "titanium":  {"label": "Titanium",           "density_g_cm3": 4.51},
    "copper":    {"label": "Copper",             "density_g_cm3": 8.96},
    "oak":       {"label": "Oak Wood",           "density_g_cm3": 0.75},
    "acrylic":   {"label": "Acrylic",            "density_g_cm3": 1.18},
}

DEFAULT_MATERIAL = "pla"

def list_materials() -> list:
    return [{"id": k, **v} for k, v in MATERIALS.items()]

def weight_grams(volume_mm3: float, material: str) -> float:
    mat = MATERIALS.get(material, MATERIALS[DEFAULT_MATERIAL])
    volume_cm3 = volume_mm3 / 1000.0
    return round(volume_cm3 * mat["density_g_cm3"], 2)
