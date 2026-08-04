"""
Common metric fastener / hole standards for one-click bolt patterns.
Clearance diameters are close-fit values suitable for CAD hole features.
"""

METRIC_FASTENERS = {
    "M2":   {"nominal_mm": 2.0,  "clearance_mm": 2.4,  "tap_mm": 1.6,  "head_clear_mm": 4.0},
    "M2.5": {"nominal_mm": 2.5,  "clearance_mm": 2.9,  "tap_mm": 2.05, "head_clear_mm": 5.0},
    "M3":   {"nominal_mm": 3.0,  "clearance_mm": 3.4,  "tap_mm": 2.5,  "head_clear_mm": 6.0},
    "M4":   {"nominal_mm": 4.0,  "clearance_mm": 4.5,  "tap_mm": 3.3,  "head_clear_mm": 8.0},
    "M5":   {"nominal_mm": 5.0,  "clearance_mm": 5.5,  "tap_mm": 4.2,  "head_clear_mm": 10.0},
    "M6":   {"nominal_mm": 6.0,  "clearance_mm": 6.6,  "tap_mm": 5.0,  "head_clear_mm": 12.0},
    "M8":   {"nominal_mm": 8.0,  "clearance_mm": 9.0,  "tap_mm": 6.8,  "head_clear_mm": 16.0},
    "M10":  {"nominal_mm": 10.0, "clearance_mm": 11.0, "tap_mm": 8.5,  "head_clear_mm": 20.0},
    "M12":  {"nominal_mm": 12.0, "clearance_mm": 13.5, "tap_mm": 10.2, "head_clear_mm": 24.0},
}


def list_fasteners() -> list:
    return [{"id": k, **v} for k, v in METRIC_FASTENERS.items()]


def bolt_circle_params(
    fastener: str,
    count: int = 6,
    pitch_diameter_mm: float = None,
    hole_type: str = "clearance",  # clearance | tap
    face: str = "top",
) -> dict:
    """
    Return CAD params fragment for a metric bolt circle.
    pitch_diameter_mm defaults to a sensible multiple of the fastener size.
    """
    key = fastener.upper().replace(" ", "")
    if key not in METRIC_FASTENERS:
        raise ValueError(f"Unknown fastener '{fastener}'. Known: {', '.join(METRIC_FASTENERS)}")

    spec = METRIC_FASTENERS[key]
    dia = spec["clearance_mm"] if hole_type == "clearance" else spec["tap_mm"]
    if pitch_diameter_mm is None:
        pitch_diameter_mm = spec["nominal_mm"] * 8  # e.g. M4 → 32mm PCD

    return {
        "circ_hole_dia_mm": dia,
        "circ_hole_face": face,
        "circ_hole_pattern": {
            "type": "polar",
            "count": int(count),
            "radius_mm": round(pitch_diameter_mm / 2, 2),
        },
        "_fastener": key,
        "_hole_type": hole_type,
    }
