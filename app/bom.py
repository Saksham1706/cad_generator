def build_bom(items: list) -> dict:
    """
    items: list of {"part_number": str, "description": str, "properties": dict (from
    generate_model output), "quantity": int}
    Returns a structured BOM with per-line and total cost/weight.
    """
    lines = []
    total_cost = 0.0
    total_weight_g = 0.0

    for i, item in enumerate(items, start=1):
        qty = item.get("quantity", 1)
        props = item.get("properties", {})
        unit_weight = props.get("weight_g", 0)
        unit_cost = props.get("cost_usd", 0)
        line_weight = round(unit_weight * qty, 2)
        line_cost = round(unit_cost * qty, 2)

        lines.append({
            "part_number": item.get("part_number", f"P-{i:03d}"),
            "description": item.get("description", "Unnamed part"),
            "material": props.get("material", "unspecified"),
            "quantity": qty,
            "unit_weight_g": unit_weight,
            "line_weight_g": line_weight,
            "unit_cost_usd": unit_cost,
            "line_cost_usd": line_cost,
        })
        total_cost += line_cost
        total_weight_g += line_weight

    return {
        "lines": lines,
        "totals": {
            "total_weight_g": round(total_weight_g, 2),
            "total_weight_kg": round(total_weight_g / 1000.0, 3),
            "total_cost_usd": round(total_cost, 2),
            "part_count": len(lines),
        },
    }
