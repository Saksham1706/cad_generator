import os
import re
import tempfile
import cadquery as cq
from datetime import date

SHEET_W = 900
SHEET_H = 650
TILE_W = 260
TILE_H = 220
MARGIN = 30
TITLEBLOCK_H = 110


def _xml_text(value) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _export_view_svg(model, projection_dir: tuple, tmp_path: str) -> tuple:
    """Export one orthographic view and return (inner_svg_content, width, height)."""
    cq.exporters.export(model, tmp_path, opt={"projectionDir": projection_dir, "showAxes": False})
    with open(tmp_path, "r", encoding="utf-8") as f:
        raw = f.read()

    width_m = re.search(r'width="([\d.]+)"', raw)
    height_m = re.search(r'height="([\d.]+)"', raw)
    width = float(width_m.group(1)) if width_m else 400.0
    height = float(height_m.group(1)) if height_m else 300.0

    # Strip the outer <?xml ...?> and <svg ...> / </svg> wrapper, keep only the inner drawing content.
    inner = re.sub(r'^.*?<svg[^>]*>', '', raw, flags=re.DOTALL)
    inner = re.sub(r'</svg>\s*$', '', inner, flags=re.DOTALL)
    return inner, width, height


def _tile(inner_svg: str, src_w: float, src_h: float, x: int, y: int, w: int, h: int, label: str) -> str:
    scale = min(w / src_w, h / src_h) * 0.9
    dx = (w - src_w * scale) / 2
    dy = (h - src_h * scale) / 2
    return f'''
    <g transform="translate({x},{y})">
      <rect x="0" y="0" width="{w}" height="{h}" fill="white" stroke="black" stroke-width="1.5"/>
      <svg x="{dx}" y="{dy}" width="{src_w * scale}" height="{src_h * scale}" viewBox="0 0 {src_w} {src_h}">
        {inner_svg}
      </svg>
      <text x="{w/2}" y="{h - 8}" font-size="12" font-family="monospace" text-anchor="middle" fill="black">{label}</text>
    </g>'''


def _title_block(part_number: str, description: str, material: str, properties: dict, scale_note: str) -> str:
    bbox = properties.get("bounding_box_mm", {})
    dims = f'{bbox.get("x","?")} x {bbox.get("y","?")} x {bbox.get("z","?")} mm'
    weight = properties.get("weight_g", "?")
    today = date.today().isoformat()

    rows = [
        ("PART NO.", part_number),
        ("DESCRIPTION", description),
        ("MATERIAL", material),
        ("OVERALL DIMENSIONS", dims),
        ("WEIGHT (g)", str(weight)),
        ("SCALE", scale_note),
        ("DATE", today),
    ]
    y = 20
    cells = ""
    for label, value in rows:
        cells += f'<text x="10" y="{y}" font-size="11" font-family="monospace" fill="black">' \
                 f'<tspan font-weight="bold">{_xml_text(label)}:</tspan> {_xml_text(value)}</text>\n'
        y += 14
    return cells


def generate_drawing(model, session_id: str, part_number: str, description: str,
                      material: str, properties: dict) -> dict:
    """
    Produces a basic 3-view (front/top/side) orthographic technical drawing with a
    title block, saved as both SVG and PDF. This is a deterministic export from the
    real CAD geometry — no LLM is involved in producing the drawing itself.
    """
    tmp_dir = tempfile.mkdtemp(prefix=f"cad_draw_{session_id}_")
    try:
        front_svg, fw, fh = _export_view_svg(model, (0, -1, 0), os.path.join(tmp_dir, "front.svg"))
        top_svg, tw, th = _export_view_svg(model, (0, 0, 1), os.path.join(tmp_dir, "top.svg"))
        side_svg, sw, sh = _export_view_svg(model, (1, 0, 0), os.path.join(tmp_dir, "side.svg"))
    finally:
        for name in ("front.svg", "top.svg", "side.svg"):
            try:
                os.remove(os.path.join(tmp_dir, name))
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass

    tiles = ""
    tiles += _tile(front_svg, fw, fh, MARGIN, MARGIN, TILE_W, TILE_H, "FRONT VIEW")
    tiles += _tile(top_svg, tw, th, MARGIN + TILE_W + 20, MARGIN, TILE_W, TILE_H, "TOP VIEW")
    tiles += _tile(side_svg, sw, sh, MARGIN + 2 * (TILE_W + 20), MARGIN, TILE_W, TILE_H, "SIDE VIEW")

    title_block = _title_block(part_number, description, material, properties, "NOT TO SCALE")

    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{SHEET_W}" height="{SHEET_H}" viewBox="0 0 {SHEET_W} {SHEET_H}">
  <rect x="0" y="0" width="{SHEET_W}" height="{SHEET_H}" fill="white" stroke="black" stroke-width="2"/>
  {tiles}
  <g transform="translate({MARGIN},{MARGIN + TILE_H + 30})">
    <rect x="0" y="0" width="{SHEET_W - 2*MARGIN}" height="{TITLEBLOCK_H}" fill="white" stroke="black" stroke-width="1.5"/>
    <g transform="translate(0,0)">{title_block}</g>
  </g>
</svg>'''

    svg_path = f"outputs/{session_id}_drawing.svg"
    pdf_path = f"outputs/{session_id}_drawing.pdf"
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(sheet)

    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPDF
        drawing = svg2rlg(svg_path)
        renderPDF.drawToFile(drawing, pdf_path)
        pdf_ok = True
    except Exception as e:  # noqa: BLE001 — PDF is a nice-to-have; SVG always succeeds
        print(f"PDF conversion skipped: {e}")
        pdf_ok = False

    return {"svg": svg_path, "pdf": pdf_path if pdf_ok else None}
