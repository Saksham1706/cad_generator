import cadquery as cq
import trimesh
import os
import math
from concurrent.futures import ThreadPoolExecutor

from app.materials import weight_grams, material_cost, DEFAULT_MATERIAL, MATERIALS
from app.compounds import COMPOUND_BUILDERS, apply_compound_defaults
from app.params_utils import sanitize_params
from app.print_estimate import estimate_print

os.makedirs("outputs", exist_ok=True)


# ---------------------------------------------------------------------------
# Face / placement helpers
# ---------------------------------------------------------------------------

def get_face_selector(face: str, p: dict) -> str:
    if face == "top":      return ">Z"
    if face == "bottom":   return "<Z"
    if face == "front":    return "<Y"
    if face == "back":     return ">Y"
    if face == "left":     return "<X"
    if face == "right":    return ">X"

    if face in ("smallest", "largest"):
        w = p.get("width_mm", p.get("base_width_mm", 1))
        h = p.get("height_mm", 1)
        d = p.get("depth_mm", p.get("base_depth_mm", 1))
        areas = {
            ">Z": w * d, "<Z": w * d,
            ">Y": w * h, "<Y": w * h,
            ">X": h * d, "<X": h * d
        }
        if face == "smallest":
            return min(areas, key=areas.get)
        return max(areas, key=areas.get)

    return ">Z"


CURVED_SHAPES = {"cylinder", "hollow_cylinder", "cone", "sphere", "hemisphere", "torus"}


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def stl_to_glb(stl_path: str, glb_path: str):
    loaded = trimesh.load(stl_path, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise ValueError("No valid mesh found in STL file.")
        mesh = trimesh.util.concatenate(meshes)
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        raise ValueError(f"Unexpected trimesh type: {type(loaded)}")
    mesh.fix_normals()
    mesh.export(glb_path, file_type="glb")


# ---------------------------------------------------------------------------
# Base shape builders. Each returns a cq.Workplane solid, untouched, so face
# centers/normals stay predictable for the feature steps that follow.
# ---------------------------------------------------------------------------

def _build_box(p):
    return cq.Workplane("XY").box(p["width_mm"], p["depth_mm"], p["height_mm"])


def _build_cylinder(p):
    return cq.Workplane("XY").cylinder(p["height_mm"], p["diameter_mm"] / 2)


def _build_hollow_cylinder(p):
    return (cq.Workplane("XY")
            .cylinder(p["height_mm"], p["outer_diameter_mm"] / 2)
            .faces(">Z").workplane()
            .circle(p["inner_diameter_mm"] / 2).cutThruAll())


def _build_sphere(p):
    return cq.Workplane("XY").sphere(p["diameter_mm"] / 2)


def _build_hemisphere(p):
    return cq.Workplane("XY").sphere(p["diameter_mm"] / 2).split(keepTop=True)


def _build_cone(p):
    return cq.Workplane("XY").add(
        cq.Solid.makeCone(p["base_diameter_mm"] / 2, p["top_diameter_mm"] / 2, p["height_mm"]))


def _build_torus(p):
    major = p["torus_diameter_mm"] / 2
    minor = p["tube_diameter_mm"] / 2
    return cq.Workplane("XY").add(cq.Solid.makeTorus(major, minor))


def _build_prism(p):
    sides = int(p.get("sides", 6))
    sides = max(3, min(sides, 20))
    radius = p["width_mm"] / 2
    return cq.Workplane("XY").polygon(sides, radius * 2).extrude(p["height_mm"])


def _build_pyramid(p):
    bw, bd, h = p["base_width_mm"], p["base_depth_mm"], p["height_mm"]
    tw = p.get("top_width_mm", 0)
    td = p.get("top_depth_mm", 0)
    wp = cq.Workplane("XY").rect(bw, bd)
    if tw > 0 and td > 0:
        wp = wp.workplane(offset=h).rect(tw, td)
    else:
        # true apex point — loft to a vanishingly small rectangle so the loft succeeds
        wp = wp.workplane(offset=h).rect(0.01, 0.01)
    return wp.loft(ruled=True)


def _build_star(p):
    points = int(p.get("points", 5))
    points = max(3, min(points, 16))
    outer_r = p["outer_diameter_mm"] / 2
    inner_r = p["inner_diameter_mm"] / 2
    pts = []
    for i in range(points * 2):
        r = outer_r if i % 2 == 0 else inner_r
        angle = math.pi * i / points
        pts.append((r * math.cos(angle), r * math.sin(angle)))
    return cq.Workplane("XY").polyline(pts).close().extrude(p["height_mm"])


SHAPE_BUILDERS = {
    "box": _build_box,
    "cylinder": _build_cylinder,
    "hollow_cylinder": _build_hollow_cylinder,
    "sphere": _build_sphere,
    "hemisphere": _build_hemisphere,
    "cone": _build_cone,
    "torus": _build_torus,
    "prism": _build_prism,
    "pyramid": _build_pyramid,
    "star": _build_star,
    **COMPOUND_BUILDERS,
}

REQUIRED_FIELDS = {
    "box": ["width_mm", "height_mm", "depth_mm"],
    "cylinder": ["diameter_mm", "height_mm"],
    "hollow_cylinder": ["outer_diameter_mm", "inner_diameter_mm", "height_mm"],
    "sphere": ["diameter_mm"],
    "hemisphere": ["diameter_mm"],
    "cone": ["base_diameter_mm", "top_diameter_mm", "height_mm"],
    "torus": ["torus_diameter_mm", "tube_diameter_mm"],
    "prism": ["sides", "width_mm", "height_mm"],
    "pyramid": ["base_width_mm", "base_depth_mm", "height_mm"],
    "star": ["points", "outer_diameter_mm", "inner_diameter_mm", "height_mm"],
    # Compounds fill from defaults — no hard required fields
    **{k: [] for k in COMPOUND_BUILDERS},
}


# ---------------------------------------------------------------------------
# Feature application: holes (single + patterns), text, shell, edge treatment
# ---------------------------------------------------------------------------

def _get_wp(base, shape, face_name, p):
    sel = get_face_selector(face_name, p)
    if shape in CURVED_SHAPES and sel not in (">Z", "<Z"):
        sel = ">Z"  # force flat-face features onto curved solids
    return base.faces(sel).workplane()


def _cut_circles_at(wp, centers, dia, depth):
    """Cut circles at face-center offsets.

    Workplane.center() returns a new plane and does not move `wp`. Re-centering
    by the inverse offset was shifting every hole after the first.
    """
    tool = None
    for (x, y) in centers:
        c = wp.center(x, y).circle(dia / 2).extrude(-abs(depth), combine=False)
        tool = c.val() if tool is None else tool.fuse(c.val())
    return tool


def _cut_rects_at(wp, centers, side, depth):
    tool = None
    for (x, y) in centers:
        c = wp.center(x, y).rect(side, side).extrude(-abs(depth), combine=False)
        tool = c.val() if tool is None else tool.fuse(c.val())
    return tool


def _pattern_centers(pattern: dict) -> list:
    """Return a list of (x, y) offsets from the face center for a hole pattern."""
    if not pattern:
        return [(0, 0)]

    ptype = pattern.get("type", "single")
    if ptype == "linear":
        cols = max(1, int(pattern.get("count_x", 1)))
        rows = max(1, int(pattern.get("count_y", 1)))
        sx = pattern.get("spacing_x_mm", 10)
        sy = pattern.get("spacing_y_mm", 10)
        centers = []
        x0 = -(cols - 1) * sx / 2
        y0 = -(rows - 1) * sy / 2
        for r in range(rows):
            for c in range(cols):
                centers.append((x0 + c * sx, y0 + r * sy))
        return centers

    if ptype == "polar":
        count = max(1, int(pattern.get("count", 4)))
        radius = pattern.get("radius_mm", 10)
        centers = []
        for i in range(count):
            angle = 2 * math.pi * i / count
            centers.append((radius * math.cos(angle), radius * math.sin(angle)))
        return centers

    return [(0, 0)]


def build_final_model(p: dict):
    """
    Build the final cq.Workplane solid from CAD parameters — shape + holes + text +
    shell + edge treatment — without exporting or computing mass properties. Reused
    by both generate_model() and the drawing generator (which needs the raw solid,
    not files on disk).
    """
    p = sanitize_params(p)
    raw_shape = p.get("shape", p.get("_understood_as", "box"))
    shape = raw_shape.replace("_with_hole", "").replace("_with_square_hole", "")
    if shape in COMPOUND_BUILDERS:
        p = apply_compound_defaults(p)
        shape = p.get("shape", shape)
    if shape not in SHAPE_BUILDERS:
        shape = "box"

    builder = SHAPE_BUILDERS[shape]
    base = builder(p)
    final_model = base

    # Compounds that cut holes themselves (chair backrest, bed headboard, …)
    COMPOUND_OWN_HOLES = {"chair", "bed", "table"}
    is_compound = shape in COMPOUND_BUILDERS
    skip_generic_holes = is_compound and shape in COMPOUND_OWN_HOLES

    # ---- circular holes (single value or pattern) ----
    circ_dia = p.get("circ_hole_dia_mm", p.get("hole_diameter_mm"))
    if circ_dia and not skip_generic_holes:
        # On other compounds, try a generic cut — failures are non-fatal
        try:
            depth = p.get("circ_hole_depth_mm", p.get("hole_depth_mm", 999))
            face = p.get("circ_hole_face", p.get("hole_face", "top"))
            pattern = p.get("circ_hole_pattern")
            wp = _get_wp(base, shape if not is_compound else "box", face, p)
            centers = _pattern_centers(pattern if isinstance(pattern, dict) else None)
            tool = _cut_circles_at(wp, centers, circ_dia, depth)
            if tool:
                final_model = final_model.cut(tool)
        except Exception as e:
            print(f"Circular hole skipped: {e}")

    # ---- square holes (single value or pattern) ----
    sq_side = p.get("sq_hole_side_mm", p.get("hole_side_mm"))
    if sq_side and not skip_generic_holes:
        try:
            depth = p.get("sq_hole_depth_mm", p.get("hole_depth_mm", 999))
            face = p.get("sq_hole_face", p.get("hole_face", "top"))
            pattern = p.get("sq_hole_pattern")
            wp = _get_wp(base, shape if not is_compound else "box", face, p)
            centers = _pattern_centers(pattern if isinstance(pattern, dict) else None)
            tool = _cut_rects_at(wp, centers, sq_side, depth)
            if tool:
                final_model = final_model.cut(tool)
        except Exception as e:
            print(f"Square hole skipped: {e}")

    # ---- shell / hollow-out (before fillet + text — cheaper, cleaner topology) ----
    if p.get("shell_thickness_mm") and not is_compound:
        thickness = abs(p["shell_thickness_mm"])
        open_face = p.get("shell_open_face")
        try:
            if open_face:
                sel = get_face_selector(open_face, p)
                final_model = final_model.faces(sel).shell(-thickness)
            else:
                final_model = final_model.shell(-thickness)
        except Exception as e:
            print(f"Skipping shell: {e}")

    # ---- edge treatment BEFORE text ----
    # Filleting after engraved glyphs tries to round every letter edge and is
    # extremely slow (often fails). Fillet the body first, then cut/emboss text.
    text_features = p.get("text_features")
    if not text_features and p.get("emboss_text"):
        text_features = [{
            "text": p["emboss_text"],
            "face": p.get("emboss_face", "top"),
            "depth_mm": p.get("emboss_depth_mm", 2.0),
            "fontsize": p.get("emboss_fontsize", 10.0),
        }]

    if p.get("edge_treatment") in ("fillet", "chamfer") and p.get("edge_radius_mm"):
        radius = p["edge_radius_mm"]
        try:
            if p["edge_treatment"] == "fillet":
                final_model = final_model.edges().fillet(radius)
            else:
                final_model = final_model.edges().chamfer(radius)
        except Exception as e:
            print(f"Skipping edge treatment: {e}")

    # ---- text last (fast path: clean=False, cut in-place, short strings) ----
    for feat in (text_features or []):
        final_model = _apply_text_feature(final_model, shape, feat, p)

    return final_model


# Max characters for OCCT font → BRep (longer strings explode tessellation time)
_MAX_TEXT_CHARS = 24


def _apply_text_feature(final_model, shape: str, feat: dict, p: dict):
    """
    Engrave/emboss text quickly.

    CadQuery's default text(..., clean=True) is slow; fillet-after-text is worse.
    Prefer direct combine='cut'/'a' with clean=False on the current solid.
    """
    txt = str(feat.get("text", "")).strip()
    if not txt:
        return final_model
    if len(txt) > _MAX_TEXT_CHARS:
        txt = txt[:_MAX_TEXT_CHARS]
        print(f"Text truncated to {_MAX_TEXT_CHARS} chars for speed")

    face_name = feat.get("face", "top")
    try:
        raw_depth = float(feat.get("depth_mm", -1.5))
    except (TypeError, ValueError):
        raw_depth = -1.5

    clarified = (p.get("_clarified_as") or "").lower()
    mode = (feat.get("mode") or "").lower()
    if mode in ("engrave", "cut", "etch") or "engrave" in clarified or "etch" in clarified:
        depth = -abs(raw_depth if raw_depth != 0 else 1.5)
    elif mode in ("emboss", "raise") or "emboss" in clarified:
        depth = abs(raw_depth if raw_depth != 0 else 1.5)
    else:
        # Preserve sign from extractor: negative = cut, positive = emboss
        depth = raw_depth if raw_depth != 0 else -1.5

    w = p.get("width_mm", p.get("base_width_mm", p.get("body_diameter_mm", p.get("diameter_mm", 50))))
    d = p.get("depth_mm", p.get("base_depth_mm", p.get("body_diameter_mm", p.get("diameter_mm", 50))))
    available_width = max(min(float(w or 50), float(d or 50)) - 5, 10)
    max_safe_fontsize = available_width / (max(len(txt), 1) * 0.55)
    try:
        req_fs = float(feat.get("fontsize", 10.0))
    except (TypeError, ValueError):
        req_fs = 10.0
    fontsize = max(min(req_fs, max_safe_fontsize), 3.0)

    max_depth = max(min(float(p.get("height_mm") or 20) * 0.4, 4.0), 0.4)
    if abs(depth) > max_depth:
        depth = math.copysign(max_depth, depth)

    try:
        wp = _get_wp(final_model, shape, face_name, p)
        # clean=False is ~10× faster; combine cut/add avoids a second boolean
        if depth < 0:
            return wp.text(
                txt, fontsize, -abs(depth),
                combine="cut", clean=False,
                font="Arial", kind="regular",
            )
        return wp.text(
            txt, fontsize, abs(depth),
            combine="a", clean=False,
            font="Arial", kind="regular",
        )
    except Exception as e:
        print(f"TEXT ERROR ({face_name} '{txt}'): {e}")
        try:
            wp = _get_wp(final_model, shape, face_name, p)
            tool = wp.text(txt, fontsize, abs(depth), combine=False, clean=False)
            if tool.val():
                if depth < 0:
                    return final_model.cut(tool.val())
                return final_model.union(tool.val())
        except Exception as e2:
            print(f"TEXT FALLBACK ERROR: {e2}")
        return final_model


def generate_model(p: dict, session_id: str, material: str = None) -> dict:
    final_model = build_final_model(p)

    # ---- mass properties (must run BEFORE export; see note above) ----
    solid = final_model.val()
    volume_mm3 = solid.Volume()
    bbox = solid.BoundingBox()

    # ---- export: STL→GLB then STEP in parallel with GLB conversion ----
    stl_path = f"outputs/{session_id}.stl"
    glb_path = f"outputs/{session_id}.glb"
    step_path = f"outputs/{session_id}.step"

    # STL first (needed for GLB); STEP can run alongside GLB conversion
    cq.exporters.export(final_model, stl_path)

    def _export_step():
        cq.exporters.export(final_model, step_path)

    def _export_glb():
        stl_to_glb(stl_path, glb_path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_step = pool.submit(_export_step)
        f_glb = pool.submit(_export_glb)
        f_step.result()
        f_glb.result()

    mat = material or p.get("material") or DEFAULT_MATERIAL
    weight = weight_grams(volume_mm3, mat)
    cost = material_cost(volume_mm3, mat)
    bbox_mm = {
        "x": round(bbox.xlen, 2),
        "y": round(bbox.ylen, 2),
        "z": round(bbox.zlen, 2),
    }
    print_est = estimate_print(volume_mm3, bbox_mm, mat)

    # Quick cost comparison across plastics / metals for the same volume
    cost_compare = []
    for mid in ("pla", "abs", "petg", "aluminum", "steel", "oak"):
        if mid not in MATERIALS:
            continue
        cost_compare.append({
            "id": mid,
            "label": MATERIALS[mid]["label"],
            "cost_usd": material_cost(volume_mm3, mid),
            "weight_g": weight_grams(volume_mm3, mid),
            "selected": mid == mat,
        })

    return {
        "stl": stl_path,
        "glb": glb_path,
        "step": step_path,
        "properties": {
            "volume_mm3": round(volume_mm3, 2),
            "volume_cm3": round(volume_mm3 / 1000.0, 3),
            "bounding_box_mm": bbox_mm,
            "material": mat,
            "weight_g": weight,
            "cost_usd": cost,
            "print_estimate": print_est,
            "cost_compare": cost_compare,
        }
    }
