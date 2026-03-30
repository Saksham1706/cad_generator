import cadquery as cq
import trimesh
import os

os.makedirs("outputs", exist_ok=True)

def get_face_selector(face: str, p: dict) -> str:
    if face == "top":      return ">Z"
    if face == "bottom":   return "<Z"
    if face == "front":    return "<Y"
    if face == "back":     return ">Y"
    if face == "left":     return "<X"
    if face == "right":    return ">X"

    if face == "smallest" or face == "largest":
        w = p.get("width_mm", 1)
        h = p.get("height_mm", 1)
        d = p.get("depth_mm", 1)
        areas = {
            ">Z": w*d, "<Z": w*d,
            ">Y": w*h, "<Y": w*h,
            ">X": h*d, "<X": h*d
        }
        if face == "smallest": return min(areas, key=areas.get)
        if face == "largest":  return max(areas, key=areas.get)

    return ">Z"

def stl_to_glb(stl_path: str, glb_path: str):
    loaded = trimesh.load(stl_path, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes: raise ValueError("No valid mesh found in STL file.")
        mesh = trimesh.util.concatenate(meshes)
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        raise ValueError(f"Unexpected trimesh type: {type(loaded)}")
    mesh.fix_normals()
    mesh.export(glb_path, file_type="glb")

def generate_model(p: dict, session_id: str) -> dict:
    raw_shape = p.get("shape", p.get("_understood_as", "box"))
    shape = raw_shape.replace("_with_hole", "").replace("_with_square_hole", "")

    # 1. GENERATE PRISTINE BASE SHAPE
    # We keep this model completely untouched so its face centers never shift!
    if shape == "box":
        base = cq.Workplane("XY").box(p["width_mm"], p["depth_mm"], p["height_mm"])
    elif shape == "cylinder":
        base = cq.Workplane("XY").cylinder(p["height_mm"], p["diameter_mm"] / 2)
    elif shape == "hollow_cylinder":
        base = (cq.Workplane("XY")
            .cylinder(p["height_mm"], p["outer_diameter_mm"] / 2)
            .faces(">Z").workplane()
            .circle(p["inner_diameter_mm"] / 2).cutThruAll())
    elif shape == "sphere":
        base = cq.Workplane("XY").sphere(p["diameter_mm"] / 2)
    elif shape == "cone":
        base = cq.Workplane("XY").add(
            cq.Solid.makeCone(p["base_diameter_mm"] / 2, p["top_diameter_mm"] / 2, p["height_mm"]))
    else:
        base = cq.Workplane("XY").box(50, 50, 50)

    final_model = base

    # Helper: Get a perfectly centered workplane from the untouched base model
    def get_wp(face_name):
        sel = get_face_selector(face_name, p)
        if shape in ["cylinder", "hollow_cylinder", "cone"] and sel not in [">Z", "<Z"]:
            sel = ">Z" # Force text/holes to flat faces for curved objects
        return base.faces(sel).workplane()

    # 2. APPLY CIRCULAR HOLE
    circ_dia = p.get("circ_hole_dia_mm", p.get("hole_diameter_mm"))
    if circ_dia:
        depth = p.get("circ_hole_depth_mm", p.get("hole_depth_mm", 999))
        wp = get_wp(p.get("circ_hole_face", p.get("hole_face", "top")))
        # combine=False creates an isolated 3D "tool" we can subtract mathematically
        tool = wp.circle(circ_dia / 2).extrude(-abs(depth), combine=False)
        if tool.val(): final_model = final_model.cut(tool.val())

    # 3. APPLY SQUARE HOLE
    sq_side = p.get("sq_hole_side_mm", p.get("hole_side_mm"))
    if sq_side:
        depth = p.get("sq_hole_depth_mm", p.get("hole_depth_mm", 999))
        wp = get_wp(p.get("sq_hole_face", p.get("hole_face", "top")))
        tool = wp.rect(sq_side, sq_side).extrude(-abs(depth), combine=False)
        if tool.val(): final_model = final_model.cut(tool.val())

    # 4. APPLY TEXT / EMBOSSING
    if p.get("emboss_text"):
        txt = str(p["emboss_text"])
        face_name = p.get("emboss_face", "top")
        depth = float(p.get("emboss_depth_mm", 2.0))
        
        w, d = p.get("width_mm", 50), p.get("depth_mm", 50)
        available_width = max(min(w, d) - 5, 10)
        max_safe_fontsize = available_width / (max(len(txt), 1) * 0.6)
        fontsize = max(min(float(p.get("emboss_fontsize", 10.0)), max_safe_fontsize), 3.0)

        try:
            wp = get_wp(face_name)
            if depth < 0:
                tool = wp.text(txt, fontsize, -abs(depth), combine=False)
                if tool.val(): final_model = final_model.cut(tool.val())
            else:
                tool = wp.text(txt, fontsize, abs(depth), combine=False)
                if tool.val(): final_model = final_model.union(tool.val())
        except Exception as e:
            print(f"🚨 TEXT ERROR: {e}")

    # 5. APPLY EDGE TREATMENTS (Always do this last so edges stay sharp for booleans!)
    if p.get("edge_treatment") in ["fillet", "chamfer"] and p.get("edge_radius_mm"):
        radius = p["edge_radius_mm"]
        try:
            if p["edge_treatment"] == "fillet":
                final_model = final_model.edges().fillet(radius)
            elif p["edge_treatment"] == "chamfer":
                final_model = final_model.edges().chamfer(radius)
        except Exception as e:
            print(f"Skipping edge treatment: {e}")

    # 6. EXPORT
    stl_path = f"outputs/{session_id}.stl"
    glb_path = f"outputs/{session_id}.glb"
    cq.exporters.export(final_model, stl_path)
    stl_to_glb(stl_path, glb_path)

    return {"stl": stl_path, "glb": glb_path}