"""
Compound / everyday-object solid builders.

These are parametric assemblies of CadQuery primitives (union / cut) so a
prompt like "a water bottle" or "a simple chair" can produce a recognizable
model without exposing each one as a UI template button.
"""

from typing import Optional

import math
import cadquery as cq


def _box_at(w, d, h, x=0, y=0, z=0):
    """Axis-aligned box centered at (x,y,z)."""
    return cq.Workplane("XY").transformed(offset=(x, y, z)).box(w, d, h)


def _cyl_at(h, r, x=0, y=0, z=0):
    """Cylinder of height h and radius r, center of cylinder at (x,y,z)."""
    return cq.Workplane("XY").transformed(offset=(x, y, z)).cylinder(h, r)


def _cone_at(r1, r2, h, z0=0):
    """Frustum/cone sitting on XY with base at z=z0, height h along +Z."""
    solid = cq.Solid.makeCone(r1, r2, h)
    if z0:
        solid = solid.move(cq.Location(cq.Vector(0, 0, z0)))
    return cq.Workplane("XY").newObject([solid])


def _as_solid(obj):
    if obj is None:
        return None
    if hasattr(obj, "val"):
        return obj.val()
    return obj


def _fuse(parts):
    solid = None
    for p in parts:
        val = _as_solid(p)
        if val is None:
            continue
        solid = val if solid is None else solid.fuse(val)
    if solid is None:
        raise ValueError("No solids to fuse")
    return cq.Workplane("XY").newObject([solid])


# ---------------------------------------------------------------------------
# Individual compounds
# ---------------------------------------------------------------------------

def build_water_bottle(p: dict):
    """Classic bottle: body + shoulder taper + neck (+ optional cap)."""
    H = p.get("height_mm", 220)
    body_d = p.get("body_diameter_mm", p.get("diameter_mm", 70))
    neck_d = p.get("neck_diameter_mm", max(22, body_d * 0.35))
    neck_h = p.get("neck_height_mm", max(25, H * 0.15))
    cap_h = p.get("cap_height_mm", 12)
    shoulder_h = min(20, H * 0.08)
    body_h = max(H - neck_h - shoulder_h - (cap_h if cap_h else 0), H * 0.55)

    body = _cyl_at(body_h, body_d / 2, z=body_h / 2)
    shoulder = _cone_at(body_d / 2, neck_d / 2, shoulder_h, z0=body_h)
    neck = _cyl_at(neck_h, neck_d / 2, z=body_h + shoulder_h + neck_h / 2)
    parts = [body, shoulder, neck]
    if cap_h and cap_h > 0:
        cap_d = neck_d * 1.15
        cap = _cyl_at(cap_h, cap_d / 2, z=body_h + shoulder_h + neck_h + cap_h / 2)
        parts.append(cap)
    model = _fuse(parts)

    wall = p.get("wall_mm", p.get("shell_thickness_mm"))
    if wall and wall > 0:
        try:
            model = model.faces(">Z").shell(-abs(wall))
        except Exception as e:
            print(f"bottle shell skipped: {e}")
    return model


def build_mug(p: dict):
    """Cylinder cup + simple handle. Open top via shell."""
    dia = p.get("diameter_mm", 80)
    h = p.get("height_mm", 95)
    wall = p.get("wall_mm", p.get("shell_thickness_mm", 3))
    handle_t = p.get("handle_thickness_mm", 8)
    handle_w = p.get("handle_width_mm", 35)

    cup = cq.Workplane("XY").cylinder(h, dia / 2)
    try:
        cup = cup.faces(">Z").shell(-abs(wall))
    except Exception as e:
        print(f"mug shell skipped: {e}")

    # Rectangular C-handle (reliable across CadQuery versions)
    hx = dia / 2 + handle_w / 2
    outer = _box_at(handle_w, handle_t, h * 0.5, x=hx, z=h * 0.5)
    inner = _box_at(handle_w - handle_t * 1.5, handle_t * 1.2, h * 0.5 - handle_t * 2,
                    x=hx - handle_t * 0.25, z=h * 0.5)
    try:
        handle = outer.cut(inner.val())
        return cup.union(handle.val())
    except Exception as e:
        print(f"mug handle fallback: {e}")
        handle = _box_at(handle_w, handle_t, h * 0.45, x=hx, z=h * 0.5)
        return _fuse([cup, handle])


def build_chair(p: dict):
    """4-leg chair with seat and backrest. Supports circular holes in seat or backrest."""
    sw = p.get("seat_width_mm", p.get("width_mm", 420))
    sd = p.get("seat_depth_mm", p.get("depth_mm", 400))
    sh = p.get("seat_height_mm", 450)
    bh = p.get("back_height_mm", 400)
    thick = p.get("leg_thickness_mm", p.get("thickness_mm", 35))
    seat_t = p.get("seat_thickness_mm", 25)
    back_t = p.get("back_thickness_mm", 20)

    seat = _box_at(sw, sd, seat_t, z=sh)
    back_y = -(sd / 2 - back_t / 2)
    back_z = sh + seat_t / 2 + bh / 2
    back = _box_at(sw, back_t, bh, y=back_y, z=back_z)

    # Feature holes — cut on the correct board before fusing (precise placement)
    dia = p.get("circ_hole_dia_mm") or p.get("hole_diameter_mm")
    face = (p.get("circ_hole_face") or p.get("hole_face") or "top").lower()
    if dia and dia > 0:
        if face in ("back", "backrest", "rear"):
            max_d = min(sw, bh) * 0.8
            d = min(float(dia), max_d)
            # Through-hole along Y (through backrest thickness), centered on backrest
            cutter = (cq.Workplane("XY")
                      .transformed(offset=(0, back_y, back_z), rotate=(90, 0, 0))
                      .cylinder(back_t * 4, d / 2))
            try:
                back = back.cut(cutter.val())
            except Exception as e:
                print(f"chair backrest hole skipped: {e}")
        elif face in ("top", "seat"):
            max_d = min(sw, sd) * 0.8
            d = min(float(dia), max_d)
            depth = p.get("circ_hole_depth_mm") or p.get("hole_depth_mm") or seat_t
            depth = min(float(depth), seat_t * 1.05)
            cutter = (cq.Workplane("XY")
                      .transformed(offset=(0, 0, sh + seat_t / 2))
                      .cylinder(depth * 2 + 2, d / 2))
            try:
                seat = seat.cut(cutter.val())
            except Exception as e:
                print(f"chair seat hole skipped: {e}")

    inset = thick * 0.6
    legs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            lx = sx * (sw / 2 - inset)
            ly = sy * (sd / 2 - inset)
            legs.append(_box_at(thick, thick, sh, x=lx, y=ly, z=sh / 2))

    return _fuse([seat, back] + legs)


def build_table(p: dict):
    """Rectangular table top + 4 legs. Supports a circular hole in the top."""
    w = p.get("width_mm", 1200)
    d = p.get("depth_mm", 700)
    h = p.get("height_mm", 750)
    top_t = p.get("top_thickness_mm", 30)
    leg = p.get("leg_thickness_mm", 50)

    top = _box_at(w, d, top_t, z=h - top_t / 2)
    dia = p.get("circ_hole_dia_mm") or p.get("hole_diameter_mm")
    face = (p.get("circ_hole_face") or "top").lower()
    if dia and face in ("top", "seat"):
        max_d = min(w, d) * 0.7
        hole_d = min(float(dia), max_d)
        cutter = (cq.Workplane("XY")
                  .transformed(offset=(0, 0, h - top_t / 2))
                  .cylinder(top_t * 3, hole_d / 2))
        try:
            top = top.cut(cutter.val())
        except Exception as e:
            print(f"table hole skipped: {e}")

    inset = leg
    legs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            legs.append(_box_at(leg, leg, h - top_t,
                                x=sx * (w / 2 - inset),
                                y=sy * (d / 2 - inset),
                                z=(h - top_t) / 2))
    return _fuse([top] + legs)


def build_bed(p: dict):
    """Simple bed frame: mattress platform, 4 legs, headboard. Supports headboard hole."""
    w = p.get("width_mm", 1400)
    length = p.get("length_mm", p.get("depth_mm", 2000))
    h = p.get("height_mm", 400)
    platform_t = p.get("platform_thickness_mm", 40)
    head_h = p.get("headboard_height_mm", 600)
    head_t = p.get("headboard_thickness_mm", 30)
    leg = p.get("leg_thickness_mm", 60)

    platform = _box_at(w, length, platform_t, z=h)
    head_y = -(length / 2 - head_t / 2)
    head_z = h + platform_t / 2 + head_h / 2
    headboard = _box_at(w, head_t, head_h, y=head_y, z=head_z)

    dia = p.get("circ_hole_dia_mm") or p.get("hole_diameter_mm")
    face = (p.get("circ_hole_face") or "top").lower()
    if dia and face in ("back", "backrest", "headboard", "rear"):
        max_d = min(w, head_h) * 0.7
        hole_d = min(float(dia), max_d)
        cutter = (cq.Workplane("XY")
                  .transformed(offset=(0, head_y, head_z), rotate=(90, 0, 0))
                  .cylinder(head_t * 4, hole_d / 2))
        try:
            headboard = headboard.cut(cutter.val())
        except Exception as e:
            print(f"bed headboard hole skipped: {e}")

    inset = leg * 0.8
    legs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            legs.append(_box_at(leg, leg, h,
                                x=sx * (w / 2 - inset),
                                y=sy * (length / 2 - inset),
                                z=h / 2))
    return _fuse([platform, headboard] + legs)


def build_stool(p: dict):
    """Round top stool with 3 or 4 legs."""
    dia = p.get("diameter_mm", p.get("width_mm", 320))
    h = p.get("height_mm", 450)
    top_t = p.get("top_thickness_mm", 25)
    leg = p.get("leg_thickness_mm", 30)
    n = int(p.get("leg_count", 4))
    n = max(3, min(n, 6))

    top = _cyl_at(top_t, dia / 2, z=h)
    radius = dia / 2 - leg
    legs = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        lx = radius * math.cos(ang)
        ly = radius * math.sin(ang)
        legs.append(_box_at(leg, leg, h, x=lx, y=ly, z=h / 2))
    return _fuse([top] + legs)


def build_vase(p: dict):
    """Tapered vase body (frustum) optionally shelled open at top."""
    base_d = p.get("base_diameter_mm", p.get("diameter_mm", 80))
    top_d = p.get("top_diameter_mm", base_d * 0.7)
    h = p.get("height_mm", 180)
    wall = p.get("wall_mm", p.get("shell_thickness_mm", 3))

    body = _cone_at(base_d / 2, top_d / 2, h, z0=0)
    if wall and wall > 0:
        try:
            body = body.faces(">Z").shell(-abs(wall))
        except Exception as e:
            print(f"vase shell skipped: {e}")
    return body


def build_bowl(p: dict):
    """Open bowl: sphere cut by a plane, then shelled."""
    dia = p.get("diameter_mm", 160)
    wall = p.get("wall_mm", p.get("shell_thickness_mm", 4))
    r = dia / 2
    # Keep lower hemisphere by cutting with a box above Z=0
    sphere = cq.Workplane("XY").sphere(r)
    cutter = cq.Workplane("XY").transformed(offset=(0, 0, r)).box(dia * 1.2, dia * 1.2, dia)
    bowl = sphere.cut(cutter.val())
    if wall and wall > 0 and wall < r * 0.4:
        try:
            bowl = bowl.faces(">Z").shell(-abs(wall))
        except Exception as e:
            print(f"bowl shell skipped: {e}")
    return bowl


def build_bookshelf(p: dict):
    """Open bookshelf: sides, top, bottom, N shelves."""
    w = p.get("width_mm", 800)
    d = p.get("depth_mm", 300)
    h = p.get("height_mm", 1200)
    thick = p.get("thickness_mm", 18)
    shelves = int(p.get("shelf_count", 3))
    shelves = max(1, min(shelves, 8))

    left = _box_at(thick, d, h, x=-(w / 2 - thick / 2), z=h / 2)
    right = _box_at(thick, d, h, x=(w / 2 - thick / 2), z=h / 2)
    bottom = _box_at(w, d, thick, z=thick / 2)
    top = _box_at(w, d, thick, z=h - thick / 2)
    parts = [left, right, bottom, top]

    inner_h = h - 2 * thick
    for i in range(1, shelves + 1):
        z = thick + (inner_h * i / (shelves + 1))
        parts.append(_box_at(w - 2 * thick, d, thick, z=z))
    return _fuse(parts)


def build_phone_stand(p: dict):
    """Angled phone stand with a slot."""
    w = p.get("width_mm", 80)
    d = p.get("depth_mm", 90)
    h = p.get("height_mm", 70)
    slot_w = p.get("slot_width_mm", 12)
    slot_d = p.get("slot_depth_mm", 20)

    base = _box_at(w, d, h)
    cutter = (cq.Workplane("XY")
              .transformed(offset=(0, d * 0.15, h * 0.55))
              .box(w * 1.2, slot_d, slot_w * 3))
    try:
        return base.cut(cutter.val())
    except Exception:
        return base


def build_lamp(p: dict):
    """Simple lamp: round base + stem + shade (frustum)."""
    base_d = p.get("base_diameter_mm", p.get("diameter_mm", 120))
    base_h = p.get("base_height_mm", 20)
    stem_d = p.get("stem_diameter_mm", 18)
    stem_h = p.get("stem_height_mm", p.get("height_mm", 350) - 100)
    shade_bottom = p.get("shade_bottom_diameter_mm", 160)
    shade_top = p.get("shade_top_diameter_mm", 60)
    shade_h = p.get("shade_height_mm", 80)

    base = _cyl_at(base_h, base_d / 2, z=base_h / 2)
    stem = _cyl_at(stem_h, stem_d / 2, z=base_h + stem_h / 2)
    shade = _cone_at(shade_bottom / 2, shade_top / 2, shade_h, z0=base_h + stem_h)
    return _fuse([base, stem, shade])


def build_goblet(p: dict):
    """Wine-glass-like: foot + stem + bowl."""
    foot_d = p.get("foot_diameter_mm", 70)
    foot_h = p.get("foot_height_mm", 8)
    stem_d = p.get("stem_diameter_mm", 10)
    stem_h = p.get("stem_height_mm", 80)
    bowl_d = p.get("bowl_diameter_mm", p.get("diameter_mm", 75))
    bowl_h = p.get("bowl_height_mm", 70)
    wall = p.get("wall_mm", 2.5)

    foot = _cyl_at(foot_h, foot_d / 2, z=foot_h / 2)
    stem = _cyl_at(stem_h, stem_d / 2, z=foot_h + stem_h / 2)
    bowl = _cone_at(bowl_d * 0.2, bowl_d / 2, bowl_h, z0=foot_h + stem_h)
    model = _fuse([foot, stem, bowl])
    if wall:
        try:
            model = model.faces(">Z").shell(-abs(wall))
        except Exception as e:
            print(f"goblet shell skipped: {e}")
    return model


def build_dumbbell(p: dict):
    """Two weight discs + bar along X."""
    bar_d = p.get("bar_diameter_mm", 25)
    bar_l = p.get("bar_length_mm", p.get("width_mm", 300))
    weight_d = p.get("weight_diameter_mm", p.get("diameter_mm", 120))
    weight_h = p.get("weight_thickness_mm", 40)

    bar = (cq.Workplane("XY")
           .transformed(offset=(0, 0, 0), rotate=(0, 90, 0))
           .cylinder(bar_l, bar_d / 2))
    left = (cq.Workplane("XY")
            .transformed(offset=(-(bar_l / 2 - weight_h / 2), 0, 0), rotate=(0, 90, 0))
            .cylinder(weight_h, weight_d / 2))
    right = (cq.Workplane("XY")
             .transformed(offset=(bar_l / 2 - weight_h / 2, 0, 0), rotate=(0, 90, 0))
             .cylinder(weight_h, weight_d / 2))
    return _fuse([bar, left, right])


def build_picture_frame(p: dict):
    """Rectangular picture frame with open center."""
    w = p.get("width_mm", 300)
    h = p.get("height_mm", 400)
    depth = p.get("depth_mm", 25)
    border = p.get("border_mm", 30)

    outer = _box_at(w, depth, h)
    inner_w = max(w - 2 * border, 10)
    inner_h = max(h - 2 * border, 10)
    cutter = _box_at(inner_w, depth * 1.2, inner_h)
    return outer.cut(cutter.val())


def build_coaster(p: dict):
    """Flat round coaster with optional slight edge fillet via chamfer-ready solid."""
    dia = p.get("diameter_mm", 90)
    h = p.get("height_mm", p.get("thickness_mm", 5))
    return _cyl_at(h, dia / 2, z=h / 2)


def build_plate(p: dict):
    """Shallow dinner plate: disc with a recessed center."""
    dia = p.get("diameter_mm", 220)
    h = p.get("height_mm", 18)
    wall = p.get("wall_mm", 4)
    rim = p.get("rim_mm", 18)
    body = _cyl_at(h, dia / 2, z=h / 2)
    inner_d = max(dia - 2 * rim, dia * 0.55)
    recess_h = max(h - wall, h * 0.4)
    cutter = _cyl_at(recess_h, inner_d / 2, z=h - recess_h / 2 + 0.5)
    try:
        return body.cut(cutter.val())
    except Exception as e:
        print(f"plate recess skipped: {e}")
        return body


# ---------------------------------------------------------------------------
# Registry + defaults
# ---------------------------------------------------------------------------

COMPOUND_BUILDERS = {
    "water_bottle": build_water_bottle,
    "mug": build_mug,
    "chair": build_chair,
    "table": build_table,
    "bed": build_bed,
    "stool": build_stool,
    "vase": build_vase,
    "bowl": build_bowl,
    "bookshelf": build_bookshelf,
    "phone_stand": build_phone_stand,
    "lamp": build_lamp,
    "goblet": build_goblet,
    "dumbbell": build_dumbbell,
    "picture_frame": build_picture_frame,
    "coaster": build_coaster,
    "plate": build_plate,
}

# Sensible defaults so "a water bottle" / "a chair" works without every dim.
COMPOUND_DEFAULTS = {
    "water_bottle": {
        "height_mm": 220, "body_diameter_mm": 70, "neck_diameter_mm": 28,
        "neck_height_mm": 35, "cap_height_mm": 12,
    },
    "mug": {"diameter_mm": 80, "height_mm": 95, "wall_mm": 3, "handle_thickness_mm": 8, "handle_width_mm": 35},
    "chair": {
        "seat_width_mm": 420, "seat_depth_mm": 400, "seat_height_mm": 450,
        "back_height_mm": 400, "leg_thickness_mm": 35, "seat_thickness_mm": 25,
    },
    "table": {"width_mm": 1200, "depth_mm": 700, "height_mm": 750, "top_thickness_mm": 30, "leg_thickness_mm": 50},
    "bed": {
        "width_mm": 1400, "length_mm": 2000, "height_mm": 400,
        "headboard_height_mm": 600, "leg_thickness_mm": 60, "platform_thickness_mm": 40,
    },
    "stool": {"diameter_mm": 320, "height_mm": 450, "top_thickness_mm": 25, "leg_thickness_mm": 30, "leg_count": 4},
    "vase": {"base_diameter_mm": 80, "top_diameter_mm": 55, "height_mm": 180, "wall_mm": 3},
    "bowl": {"diameter_mm": 160, "wall_mm": 4},
    "bookshelf": {"width_mm": 800, "depth_mm": 300, "height_mm": 1200, "thickness_mm": 18, "shelf_count": 3},
    "phone_stand": {"width_mm": 80, "depth_mm": 90, "height_mm": 70, "slot_width_mm": 12, "slot_depth_mm": 20},
    "lamp": {
        "base_diameter_mm": 120, "base_height_mm": 20, "stem_diameter_mm": 18,
        "stem_height_mm": 280, "shade_bottom_diameter_mm": 160, "shade_top_diameter_mm": 60, "shade_height_mm": 80,
    },
    "goblet": {
        "foot_diameter_mm": 70, "foot_height_mm": 8, "stem_diameter_mm": 10,
        "stem_height_mm": 80, "bowl_diameter_mm": 75, "bowl_height_mm": 70, "wall_mm": 2.5,
    },
    "dumbbell": {
        "bar_diameter_mm": 25, "bar_length_mm": 300,
        "weight_diameter_mm": 120, "weight_thickness_mm": 40,
    },
    "picture_frame": {"width_mm": 300, "height_mm": 400, "depth_mm": 25, "thickness_mm": 20, "border_mm": 30},
    "coaster": {"diameter_mm": 90, "height_mm": 5},
    "plate": {"diameter_mm": 220, "height_mm": 18, "wall_mm": 4, "rim_mm": 18},
}

# Aliases the LLM / keyword fallback can resolve to a registry key.
COMPOUND_ALIASES = {
    "water_bottle": ["water bottle", "bottle", "flask", "sports bottle", "drink bottle"],
    "mug": ["mug", "coffee mug", "coffee cup", "tea cup", "cup with handle"],
    "chair": ["chair", "dining chair", "office chair", "seat"],
    "table": ["table", "desk", "dining table", "coffee table", "work table"],
    "bed": ["bed", "twin bed", "single bed", "bed frame", "mattress frame"],
    "stool": ["stool", "bar stool", "ottoman"],
    "vase": ["vase", "flower vase", "urn"],
    "bowl": ["bowl", "mixing bowl", "soup bowl"],
    "bookshelf": ["bookshelf", "bookcase", "shelf unit", "shelving unit", "shelves"],
    "phone_stand": ["phone stand", "phone holder", "phone dock", "tablet stand"],
    "lamp": ["lamp", "desk lamp", "table lamp", "lamp base"],
    "goblet": ["goblet", "wine glass", "chalice"],
    "dumbbell": ["dumbbell", "hand weight", "barbell weight"],
    "picture_frame": ["picture frame", "photo frame", "frame"],
    "coaster": ["coaster", "drink coaster", "cup coaster"],
    "plate": ["plate", "dinner plate", "dish plate"],
}


def list_compounds() -> list:
    out = []
    for key, aliases in COMPOUND_ALIASES.items():
        out.append({
            "id": key,
            "aliases": aliases,
            "defaults": COMPOUND_DEFAULTS.get(key, {}),
        })
    return out


def apply_compound_defaults(params: dict) -> dict:
    """Fill missing fields for a compound shape from COMPOUND_DEFAULTS."""
    shape = params.get("shape")
    if shape not in COMPOUND_DEFAULTS:
        return params
    out = dict(params)
    for k, v in COMPOUND_DEFAULTS[shape].items():
        if out.get(k) is None:
            out[k] = v
    return out


def match_compound_keyword(prompt: str) -> Optional[str]:
    """Cheap offline fallback: detect a compound name in free text."""
    text = (prompt or "").lower()
    # longer aliases first to prefer "water bottle" over "bottle" alone if both present
    ranked = []
    for key, aliases in COMPOUND_ALIASES.items():
        for a in aliases:
            ranked.append((len(a), a, key))
    ranked.sort(reverse=True)
    for _, alias, key in ranked:
        if alias in text:
            return key
    return None
