import cadquery as cq
import trimesh
import os
import math

from app.materials import weight_grams, DEFAULT_MATERIAL

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
    tool = None
    for (x, y) in centers:
        c = wp.center(x, y).circle(dia / 2).extrude(-abs(depth), combine=False)
        tool = c.val() if tool is None else tool.fuse(c.val())
        wp = wp.center(-x, -y)  # reset workplane origin
    return tool


def _cut_rects_at(wp, centers, side, depth):
    tool = None
    for (x, y) in centers:
        c = wp.center(x, y).rect(side, side).extrude(-abs(depth), combine=False)
        tool = c.val() if tool is None else tool.fuse(c.val())
        wp = wp.center(-x, -y)
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


def generate_model(p: dict, session_id: str, material: str = None) -> dict:
    raw_shape = p.get("shape", p.get("_understood_as", "box"))
    shape = raw_shape.replace("_with_hole", "").replace("_with_square_hole", "")
    if shape not in SHAPE_BUILDERS:
        shape = "box"

    builder = SHAPE_BUILDERS[shape]
    base = builder(p)
    final_model = base

    # ---- circular holes (single value or pattern) ----
    circ_dia = p.get("circ_hole_dia_mm", p.get("hole_diameter_mm"))
    if circ_dia:
        depth = p.get("circ_hole_depth_mm", p.get("hole_depth_mm", 999))
        face = p.get("circ_hole_face", p.get("hole_face", "top"))
        pattern = p.get("circ_hole_pattern")
        wp = _get_wp(base, shape, face, p)
        centers = _pattern_centers(pattern)
        tool = _cut_circles_at(wp, centers, circ_dia, depth)
        if tool:
            final_model = final_model.cut(tool)

    # ---- square holes (single value or pattern) ----
    sq_side = p.get("sq_hole_side_mm", p.get("hole_side_mm"))
    if sq_side:
        depth = p.get("sq_hole_depth_mm", p.get("hole_depth_mm", 999))
        face = p.get("sq_hole_face", p.get("hole_face", "top"))
        pattern = p.get("sq_hole_pattern")
        wp = _get_wp(base, shape, face, p)
        centers = _pattern_centers(pattern)
        tool = _cut_rects_at(wp, centers, sq_side, depth)
        if tool:
            final_model = final_model.cut(tool)

    # ---- text features: supports a list, or the legacy single-text fields ----
    text_features = p.get("text_features")
    if not text_features and p.get("emboss_text"):
        text_features = [{
            "text": p["emboss_text"],
            "face": p.get("emboss_face", "top"),
            "depth_mm": p.get("emboss_depth_mm", 2.0),
            "fontsize": p.get("emboss_fontsize", 10.0),
        }]

    for feat in (text_features or []):
        txt = str(feat.get("text", "")).strip()
        if not txt:
            continue
        face_name = feat.get("face", "top")
        depth = float(feat.get("depth_mm", 2.0))

        w = p.get("width_mm", p.get("base_width_mm", 50))
        d = p.get("depth_mm", p.get("base_depth_mm", 50))
        available_width = max(min(w, d) - 5, 10)
        max_safe_fontsize = available_width / (max(len(txt), 1) * 0.6)
        fontsize = max(min(float(feat.get("fontsize", 10.0)), max_safe_fontsize), 3.0)

        try:
            wp = _get_wp(base, shape, face_name, p)
            if depth < 0:
                tool = wp.text(txt, fontsize, -abs(depth), combine=False)
                if tool.val():
                    final_model = final_model.cut(tool.val())
            else:
                tool = wp.text(txt, fontsize, abs(depth), combine=False)
                if tool.val():
                    final_model = final_model.union(tool.val())
        except Exception as e:
            print(f"TEXT ERROR ({face_name} '{txt}'): {e}")

    # ---- shell / hollow-out ----
    if p.get("shell_thickness_mm"):
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

    # ---- edge treatment (last, so edges stay sharp for earlier booleans) ----
    if p.get("edge_treatment") in ("fillet", "chamfer") and p.get("edge_radius_mm"):
        radius = p["edge_radius_mm"]
        try:
            if p["edge_treatment"] == "fillet":
                final_model = final_model.edges().fillet(radius)
            else:
                final_model = final_model.edges().chamfer(radius)
        except Exception as e:
            print(f"Skipping edge treatment: {e}")

    # ---- mass properties (must run BEFORE export; see note above) ----
    solid = final_model.val()
    volume_mm3 = solid.Volume()
    bbox = solid.BoundingBox()

    # ---- export: STL, GLB, STEP ----
    stl_path = f"outputs/{session_id}.stl"
    glb_path = f"outputs/{session_id}.glb"
    step_path = f"outputs/{session_id}.step"

    cq.exporters.export(final_model, stl_path)
    stl_to_glb(stl_path, glb_path)
    cq.exporters.export(final_model, step_path)
    mat = material or p.get("material") or DEFAULT_MATERIAL
    weight = weight_grams(volume_mm3, mat)

    return {
        "stl": stl_path,
        "glb": glb_path,
        "step": step_path,
        "properties": {
            "volume_mm3": round(volume_mm3, 2),
            "volume_cm3": round(volume_mm3 / 1000.0, 3),
            "bounding_box_mm": {
                "x": round(bbox.xlen, 2),
                "y": round(bbox.ylen, 2),
                "z": round(bbox.zlen, 2),
            },
            "material": mat,
            "weight_g": weight,
        }
    }
