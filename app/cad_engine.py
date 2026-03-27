import cadquery as cq
import trimesh
import os

os.makedirs("outputs", exist_ok=True)

def get_face_selector(params: dict) -> str:
    face = params.get("hole_face", "top")
    
    if face == "top":      return ">Z"
    if face == "bottom":   return "<Z"
    if face == "front":    return ">Y"
    if face == "back":     return "<Y"
    if face == "left":     return "<X"
    if face == "right":    return ">X"
    
    if face == "smallest":
        w = params.get("width_mm", 1)
        h = params.get("height_mm", 1)
        d = params.get("depth_mm", 1)
        areas = {
            ">Z": w * d, "<Z": w * d,
            ">Y": w * h, "<Y": w * h,
            ">X": h * d, "<X": h * d
        }
        return min(areas, key=areas.get)
    
    if face == "largest":
        w = params.get("width_mm", 1)
        h = params.get("height_mm", 1)
        d = params.get("depth_mm", 1)
        areas = {
            ">Z": w * d, "<Z": w * d,
            ">Y": w * h, "<Y": w * h,
            ">X": h * d, "<X": h * d
        }
        return max(areas, key=areas.get)
    
    return ">Z"


def stl_to_glb(stl_path: str, glb_path: str):
    loaded = trimesh.load(stl_path, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        meshes = [g for g in loaded.geometry.values()
                  if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise ValueError("No valid mesh found in STL file.")
        mesh = trimesh.util.concatenate(meshes)
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        raise ValueError(f"Unexpected trimesh type: {type(loaded)}")
    mesh.fix_normals()
    mesh.export(glb_path, file_type="glb")


def generate_model(p: dict, session_id: str) -> dict:
    shape = p["shape"]

    if shape == "box":
        model = cq.Workplane("XY").box(
            p["width_mm"], p["depth_mm"], p["height_mm"]
        )

    elif shape == "cylinder":
        model = cq.Workplane("XY").cylinder(
            p["height_mm"], p["diameter_mm"] / 2
        )

    elif shape == "hollow_cylinder":
        model = (cq.Workplane("XY")
            .cylinder(p["height_mm"], p["outer_diameter_mm"] / 2)
            .faces(">Z").workplane()
            .circle(p["inner_diameter_mm"] / 2).cutThruAll())

    elif shape == "sphere":
        model = cq.Workplane("XY").sphere(p["diameter_mm"] / 2)

    elif shape == "cone":
        model = cq.Workplane("XY").add(
            cq.Solid.makeCone(
                p["base_diameter_mm"] / 2,
                p["top_diameter_mm"] / 2,
                p["height_mm"]
            )
        )

    elif shape == "box_with_hole":
        face_sel = get_face_selector(p)
        hole_depth = p.get("hole_depth_mm", p["height_mm"])
        model = (cq.Workplane("XY")
            .box(p["width_mm"], p["depth_mm"], p["height_mm"])
            .faces(face_sel).workplane()
            .circle(p["hole_diameter_mm"] / 2)
            .cutBlind(-hole_depth))

    elif shape == "box_with_square_hole":
        face_sel = get_face_selector(p)
        hole_depth = p.get("hole_depth_mm", p["height_mm"])
        side = p["hole_side_mm"]
        model = (cq.Workplane("XY")
            .box(p["width_mm"], p["depth_mm"], p["height_mm"])
            .faces(face_sel).workplane()
            .rect(side, side)
            .cutBlind(-hole_depth))

    else:
        raise ValueError(f"Unknown shape: {shape}")

    stl_path = f"outputs/{session_id}.stl"
    glb_path = f"outputs/{session_id}.glb"

    cq.exporters.export(model, stl_path)
    stl_to_glb(stl_path, glb_path)

    return {"stl": stl_path, "glb": glb_path}