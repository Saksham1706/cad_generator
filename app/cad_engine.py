import cadquery as cq
import trimesh
import numpy as np
import os

os.makedirs("outputs", exist_ok=True)

def generate_model(p: dict, session_id: str) -> dict:
    shape = p["shape"]

    if shape == "box":
        model = cq.Workplane("XY").box(p["width_mm"], p["depth_mm"], p["height_mm"])

    elif shape == "cylinder":
        model = cq.Workplane("XY").cylinder(p["height_mm"], p["diameter_mm"] / 2)

    elif shape == "hollow_cylinder":
        model = (cq.Workplane("XY")
            .cylinder(p["height_mm"], p["outer_diameter_mm"] / 2)
            .faces(">Z").workplane()
            .circle(p["inner_diameter_mm"] / 2).cutThruAll())

    elif shape == "sphere":
        model = cq.Workplane("XY").sphere(p["diameter_mm"] / 2)

    elif shape == "cone":
        model = cq.Workplane("XY").add(
            cq.Solid.makeCone(p["base_diameter_mm"]/2, p["top_diameter_mm"]/2, p["height_mm"]))

    elif shape == "box_with_hole":
        model = (cq.Workplane("XY")
            .box(p["width_mm"], p["depth_mm"], p["height_mm"])
            .faces(">Z").workplane()
            .circle(p["hole_diameter_mm"] / 2).cutThruAll())

    # Export STL first (intermediate)
    stl_path = f"outputs/{session_id}.stl"
    glb_path = f"outputs/{session_id}.glb"

    cq.exporters.export(model, stl_path)

    # Convert STL → GLB using trimesh
    mesh = trimesh.load(stl_path)
    mesh.export(glb_path)

    return {"stl": stl_path, "glb": glb_path}