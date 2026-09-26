"""Build the rover and lander 3D models (.glb) used by the mission-control view.

Run inside Blender (tested with 5.1):

    /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
        --python scripts/build_vehicle_models.py

Writes web/public/models/rover.glb and lander.glb, plus preview renders in
review/screenshots/. The models are built from code so they can be regenerated and
reviewed rather than trusted as opaque binaries.

Both vehicles are *generic research platforms*, deliberately not replicas of
any real spacecraft, and carry no mission names or insignia. They are built in
metres at a plausible scale:

  rover   six 0.50 m wheels on a rocker-bogie, 1.64 m wide x 1.80 m long,
          solar deck, mast-mounted stereo navigation camera at 1.66 m
  lander  four legs on a 4.3 m footprint, deck at 2.0 m, twin solar wings,
          deployment ramp

The simulator models neither vehicle's geometry: it moves a point robot
between grid cells. The models are illustration, and the interface says so.

Conventions: Blender is Z-up and the glTF exporter converts to Y-up, so a
model built facing Blender -Y faces glTF/three.js +Z. Wheel objects have their
origin on the axle so the viewer can spin them; an empty named "navcam" marks
the navigation camera's optical centre.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "web" / "public" / "models"
PHOTOS = ROOT / "review" / "screenshots"


# --------------------------------------------------------------------------
# scene and materials
# --------------------------------------------------------------------------


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name, color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def palette() -> dict:
    return {
        "paint": material("paint_white", (0.78, 0.78, 0.76), 0.0, 0.55),
        "alu": material("aluminium", (0.62, 0.63, 0.65), 1.0, 0.36),
        "wheel": material("wheel_aluminium", (0.56, 0.56, 0.57), 0.9, 0.46),
        "dark": material("anodized_dark", (0.045, 0.045, 0.05), 0.4, 0.45),
        "cells": material("solar_cells", (0.03, 0.045, 0.1), 0.35, 0.2),
        "gold": material("mli_gold", (0.8, 0.57, 0.22), 1.0, 0.32),
        "silver": material("mli_silver", (0.78, 0.78, 0.8), 1.0, 0.26),
        "glass": material("lens_glass", (0.02, 0.02, 0.03), 0.0, 0.05),
        "titanium": material("titanium", (0.52, 0.52, 0.55), 1.0, 0.34),
        "nozzle": material("nozzle", (0.13, 0.12, 0.11), 0.85, 0.55),
    }


# --------------------------------------------------------------------------
# geometry helpers (bmesh, so nothing depends on UI context)
# --------------------------------------------------------------------------


def to_object(name, bm, mats, parent=None, smooth=False, sharp_angle=40.0):
    mesh = bpy.data.meshes.new(name)
    if smooth:
        for face in bm.faces:
            face.smooth = True
    bm.to_mesh(mesh)
    bm.free()
    if smooth and hasattr(mesh, "set_sharp_from_angle"):
        mesh.set_sharp_from_angle(angle=math.radians(sharp_angle))
    for mat in mats if isinstance(mats, list) else [mats]:
        mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def _faces_of(verts):
    return {f for v in verts for f in v.link_faces}


def add_box(bm, size, center=(0, 0, 0), bevel=0.0, rot=None, mat_index=0):
    m = Matrix.Translation(center)
    if rot is not None:
        m = m @ rot
    m = m @ Matrix.Diagonal((*size, 1.0))
    made = bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    faces = _faces_of(made["verts"])
    for f in faces:
        f.material_index = mat_index
    if bevel > 0:
        edges = list({e for f in faces for e in f.edges})
        bmesh.ops.bevel(
            bm,
            geom=edges,
            offset=bevel,
            segments=2,
            affect="EDGES",
            profile=0.5,
            clamp_overlap=True,
        )
    return made


def add_cyl(bm, radius, depth, center=(0, 0, 0), rot=None, segments=24, mat_index=0, r2=None):
    m = Matrix.Translation(center)
    if rot is not None:
        m = m @ rot
    made = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius if r2 is None else r2,
        depth=depth,
        matrix=m,
    )
    for f in _faces_of(made["verts"]):
        f.material_index = mat_index
    return made


def add_sphere(bm, radius, center=(0, 0, 0), mat_index=0, segs=(24, 14)):
    made = bmesh.ops.create_uvsphere(
        bm, u_segments=segs[0], v_segments=segs[1], radius=radius, matrix=Matrix.Translation(center)
    )
    for f in _faces_of(made["verts"]):
        f.material_index = mat_index
    return made


def rot_to(direction) -> Matrix:
    """Rotation taking +Z onto `direction`."""
    return Vector(direction).normalized().to_track_quat("Z", "Y").to_matrix().to_4x4()


def add_tube(bm, a, b, radius, mat_index=0, segments=12):
    a, b = Vector(a), Vector(b)
    add_cyl(
        bm,
        radius,
        (b - a).length,
        center=(a + b) / 2,
        rot=rot_to(b - a),
        segments=segments,
        mat_index=mat_index,
    )


ROT_X90 = Matrix.Rotation(math.radians(90), 4, "X")
ROT_Y90 = Matrix.Rotation(math.radians(90), 4, "Y")


def empty(name, location, parent=None):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = 0.1
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


# --------------------------------------------------------------------------
# rover
# --------------------------------------------------------------------------

WHEEL_R = 0.25
WHEEL_W = 0.2
TRACK = 0.72  # wheel centre, |x|
WHEEL_Y = {"F": -0.70, "M": 0.05, "R": 0.66}
ARM_X = 0.58  # plane of the rocker-bogie tubes, |x|


def build_wheel(name, center, mats, parent):
    """Aluminium wheel with grousers, spokes and a dark hub; origin on the axle."""
    bm = bmesh.new()
    # tread band: an open drum, so the spokes read from the side
    band = bmesh.ops.create_cone(
        bm,
        cap_ends=False,
        segments=40,
        radius1=WHEEL_R - 0.012,
        radius2=WHEEL_R - 0.012,
        depth=WHEEL_W,
        matrix=ROT_Y90,
    )
    bmesh.ops.solidify(bm, geom=list(_faces_of(band["verts"])), thickness=-0.012)
    # grousers: 20 cleats across the tread
    for k in range(20):
        a = 2 * math.pi * k / 20
        rot = Matrix.Rotation(a, 4, "X")
        c = rot @ Vector((0, 0, WHEEL_R - 0.004))
        add_box(bm, (WHEEL_W * 0.96, 0.018, 0.022), center=c, rot=rot)
    # six flat spokes and a hub, on the outer face
    for k in range(6):
        a = 2 * math.pi * k / 6 + 0.26
        rot = Matrix.Rotation(a, 4, "X")
        c = rot @ Vector((0.03, 0, WHEEL_R * 0.52))
        add_box(bm, (0.012, 0.03, WHEEL_R * 0.86), center=c, rot=rot)
    add_cyl(bm, 0.055, 0.09, center=(0.03, 0, 0), rot=ROT_Y90, segments=20, mat_index=1)
    wheel = to_object(name, bm, [mats["wheel"], mats["dark"]], parent=parent, smooth=True)
    wheel.location = center
    return wheel


def build_rover(mats):
    root = empty("rover", (0, 0, 0))

    # warm electronics box: white paint, gold MLI side panels
    bm = bmesh.new()
    add_box(bm, (0.95, 1.25, 0.38), center=(0, 0, 0.72), bevel=0.025)
    to_object("chassis", bm, mats["paint"], parent=root)
    bm = bmesh.new()
    for side in (-1, 1):
        add_box(bm, (0.012, 0.95, 0.24), center=(side * 0.478, 0.05, 0.72), bevel=0.004)
    to_object("chassis_mli", bm, mats["gold"], parent=root)

    # solar deck: frame and 8 x 8 cell tiles
    bm = bmesh.new()
    add_box(bm, (1.36, 1.46, 0.035), center=(0, 0.02, 0.935), bevel=0.008)
    to_object("solar_frame", bm, mats["alu"], parent=root)
    bm = bmesh.new()
    n_x, n_y, pitch_x, pitch_y = 8, 8, 1.30 / 8, 1.40 / 8
    for i in range(n_x):
        for j in range(n_y):
            x = -0.65 + pitch_x * (i + 0.5)
            y = -0.68 + pitch_y * (j + 0.5)
            add_box(bm, (pitch_x - 0.012, pitch_y - 0.012, 0.01), center=(x, y + 0.02, 0.955))
    to_object("solar_cells", bm, mats["cells"], parent=root)

    # rocker-bogie, both sides
    bm = bmesh.new()
    for side in (-1, 1):
        x = side * ARM_X
        pivot = (x, -0.12, 0.74)
        front = (x, WHEEL_Y["F"], 0.50)
        bogie = (x, 0.36, 0.56)
        mid = (x, WHEEL_Y["M"], 0.45)
        rear = (x, WHEEL_Y["R"], 0.45)
        add_tube(bm, pivot, front, 0.03)
        add_tube(bm, pivot, bogie, 0.03)
        add_tube(bm, bogie, mid, 0.026)
        add_tube(bm, bogie, rear, 0.026)
        add_cyl(bm, 0.05, 0.12, center=(side * 0.53, -0.12, 0.74), rot=ROT_Y90, segments=18)
        add_cyl(bm, 0.04, 0.08, center=bogie, rot=ROT_Y90, segments=16)
        for key, top in (("F", front), ("M", mid), ("R", rear)):
            hub = (x, WHEEL_Y[key], WHEEL_R)
            add_tube(bm, top, hub, 0.024)
            # axle stub into the wheel's inner face
            add_cyl(
                bm,
                0.03,
                0.08,
                center=(side * (TRACK - WHEEL_W / 2 - 0.03), WHEEL_Y[key], WHEEL_R),
                rot=ROT_Y90,
                segments=14,
            )
            if key in ("F", "R"):  # steering actuators on the corner wheels
                add_cyl(bm, 0.045, 0.1, center=(x, WHEEL_Y[key], top[2] - 0.02), segments=18)
    to_object("suspension", bm, mats["alu"], parent=root, smooth=True)

    for side_name, side in (("L", -1), ("R", 1)):
        for key in ("F", "M", "R"):
            build_wheel(
                f"wheel_{side_name}{key}", (side * TRACK, WHEEL_Y[key], WHEEL_R), mats, root
            )

    # mast, pan-tilt head, stereo navigation camera
    mast_x, mast_y = 0.34, -0.46
    bm = bmesh.new()
    add_cyl(bm, 0.045, 0.06, center=(mast_x, mast_y, 0.98), segments=20)
    add_cyl(bm, 0.032, 0.58, center=(mast_x, mast_y, 1.27), segments=16)
    add_cyl(bm, 0.05, 0.08, center=(mast_x, mast_y, 1.57), segments=20)
    to_object("mast", bm, mats["alu"], parent=root, smooth=True)
    bm = bmesh.new()
    add_box(bm, (0.36, 0.1, 0.1), center=(mast_x, mast_y - 0.02, 1.66), bevel=0.012)
    to_object("camera_bar", bm, mats["paint"], parent=root)
    bm = bmesh.new()
    for dx in (-0.11, 0.11):
        add_cyl(
            bm, 0.026, 0.03, center=(mast_x + dx, mast_y - 0.08, 1.66), rot=ROT_X90, segments=20
        )
    to_object("navcam_lenses", bm, mats["glass"], parent=root, smooth=True)
    empty("navcam", (mast_x, mast_y - 0.1, 1.66), parent=root)

    # high-gain antenna on a gimbal post, low-gain whip
    bm = bmesh.new()
    add_cyl(bm, 0.03, 0.16, center=(-0.36, 0.38, 1.03), segments=14)
    add_tube(bm, (-0.46, 0.66, 0.95), (-0.46, 0.66, 1.3), 0.008, segments=8)
    add_sphere(bm, 0.018, center=(-0.46, 0.66, 1.31), segs=(10, 6))
    to_object("antenna_posts", bm, mats["alu"], parent=root, smooth=True)
    bm = bmesh.new()
    dish = bmesh.ops.create_cone(
        bm,
        cap_ends=False,
        segments=32,
        radius1=0.2,
        radius2=0.03,
        depth=0.07,
        matrix=Matrix.Translation((-0.36, 0.38, 1.16))
        @ Matrix.Rotation(math.radians(-25), 4, "X")
        @ Matrix.Rotation(math.radians(180), 4, "X"),
    )
    bmesh.ops.solidify(bm, geom=list(_faces_of(dish["verts"])), thickness=0.01)
    to_object("hga_dish", bm, mats["paint"], parent=root, smooth=True)

    # front hazard cameras and a stowed two-link arm
    bm = bmesh.new()
    add_box(bm, (0.34, 0.06, 0.07), center=(0, -0.645, 0.6), bevel=0.01)
    add_tube(bm, (0.36, -0.66, 0.7), (-0.2, -0.66, 0.7), 0.028)
    add_tube(bm, (-0.2, -0.66, 0.7), (0.12, -0.7, 0.66), 0.024)
    add_box(bm, (0.14, 0.1, 0.12), center=(0.14, -0.72, 0.62), bevel=0.012)
    to_object("front_equipment", bm, mats["paint"], parent=root, smooth=True)
    bm = bmesh.new()
    for dx in (-0.1, 0.1):
        add_cyl(bm, 0.02, 0.02, center=(dx, -0.678, 0.6), rot=ROT_X90, segments=16)
    to_object("hazcam_lenses", bm, mats["glass"], parent=root, smooth=True)
    return root


# --------------------------------------------------------------------------
# lander
# --------------------------------------------------------------------------


def octagon_prism(bm, radius, height, z, mat_index=0):
    add_cyl(
        bm,
        radius,
        height,
        center=(0, 0, z),
        segments=8,
        mat_index=mat_index,
        rot=Matrix.Rotation(math.pi / 8, 4, "Z"),
    )


def build_lander(mats):
    root = empty("lander", (0, 0, 0))

    bm = bmesh.new()
    octagon_prism(bm, 1.1, 0.86, 1.55)
    to_object("body_mli", bm, mats["gold"], parent=root)
    bm = bmesh.new()
    octagon_prism(bm, 1.16, 0.07, 2.02)
    octagon_prism(bm, 1.04, 0.05, 1.1)
    add_cyl(bm, 0.05, 0.9, center=(0.55, 0.3, 2.45), segments=12)
    to_object("decks", bm, mats["paint"], parent=root)

    # propellant tanks under the deck, descent engine
    bm = bmesh.new()
    for x in (-0.48, 0.48):
        add_sphere(bm, 0.36, center=(x, 0.0, 0.92))
    to_object("tanks", bm, mats["silver"], parent=root, smooth=True)
    bm = bmesh.new()
    add_cyl(bm, 0.14, 0.2, center=(0, 0, 1.0), segments=24)
    bell = bmesh.ops.create_cone(
        bm,
        cap_ends=False,
        segments=32,
        radius1=0.34,
        radius2=0.14,
        depth=0.5,
        matrix=Matrix.Translation((0, 0, 0.65)),
    )
    bmesh.ops.solidify(bm, geom=list(_faces_of(bell["verts"])), thickness=0.012)
    for k in range(4):  # attitude-control thruster pods
        a = math.pi / 4 + k * math.pi / 2
        add_box(
            bm, (0.1, 0.1, 0.1), center=(1.08 * math.cos(a), 1.08 * math.sin(a), 1.95), bevel=0.01
        )
        add_cyl(
            bm,
            0.025,
            0.08,
            center=(1.14 * math.cos(a), 1.14 * math.sin(a), 1.95),
            rot=rot_to((math.cos(a), math.sin(a), 0)),
            r2=0.012,
            segments=12,
        )
    to_object("propulsion", bm, mats["nozzle"], parent=root, smooth=True)

    # four legs: primary strut, two secondary struts, footpad
    bm = bmesh.new()
    pads = bmesh.new()
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        c, s = math.cos(a), math.sin(a)
        top = Vector((1.0 * c, 1.0 * s, 1.35))
        foot = Vector((2.05 * c, 2.05 * s, 0.14))
        knee = top.lerp(foot, 0.55)
        add_tube(bm, top, foot, 0.045)
        tangent = Vector((-s, c, 0))
        for sign in (-1, 1):
            anchor = Vector((0.95 * c, 0.95 * s, 1.12)) + sign * 0.42 * tangent
            add_tube(bm, anchor, knee, 0.028)
        add_cyl(pads, 0.24, 0.05, center=(2.1 * c, 2.1 * s, 0.035), r2=0.2, segments=24)
        add_sphere(pads, 0.06, center=tuple(foot), segs=(12, 8))
    to_object("legs", bm, mats["titanium"], parent=root, smooth=True)
    to_object("footpads", pads, mats["alu"], parent=root, smooth=True)

    # solar wings on booms
    bm = bmesh.new()
    cells = bmesh.new()
    for side in (-1, 1):
        add_tube(bm, (side * 1.12, 0, 2.0), (side * 1.32, 0, 2.05), 0.03)
        add_box(bm, (1.7, 0.94, 0.03), center=(side * 2.2, 0, 2.08), bevel=0.006)
        for i in range(8):
            for j in range(4):
                x = side * (1.4 + 0.2 * (i + 0.5))
                y = -0.44 + 0.22 * (j + 0.5)
                add_box(cells, (0.19, 0.21, 0.01), center=(x, y, 2.1))
    to_object("wing_frames", bm, mats["alu"], parent=root, smooth=True)
    to_object("wing_cells", cells, mats["cells"], parent=root)

    # antenna dish on the deck
    bm = bmesh.new()
    dish = bmesh.ops.create_cone(
        bm,
        cap_ends=False,
        segments=32,
        radius1=0.42,
        radius2=0.05,
        depth=0.12,
        matrix=Matrix.Translation((0.55, 0.3, 2.95)) @ Matrix.Rotation(math.radians(160), 4, "X"),
    )
    bmesh.ops.solidify(bm, geom=list(_faces_of(dish["verts"])), thickness=0.012)
    to_object("dish", bm, mats["paint"], parent=root, smooth=True)

    # deployment ramp down the -Y side (faces +Z in the viewer)
    bm = bmesh.new()
    start = Vector((0, -1.05, 1.08))
    end = Vector((0, -3.15, 0.03))
    direction = end - start
    rot = rot_to(direction)
    for dx in (-0.45, 0.45):
        add_tube(bm, start + Vector((dx, 0, 0)), end + Vector((dx, 0, 0)), 0.035)
    to_object("ramp_rails", bm, mats["alu"], parent=root, smooth=True)
    bm = bmesh.new()
    add_box(
        bm,
        (0.86, 0.02, direction.length),
        center=(start + end) / 2 + Vector((0, 0, -0.02)),
        rot=rot,
        bevel=0.004,
    )
    to_object("ramp_deck", bm, mats["dark"], parent=root)
    return root


# --------------------------------------------------------------------------
# export and preview
# --------------------------------------------------------------------------


def export(root, path: Path) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in [root, *root.children_recursive]:
        obj.select_set(True)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
    )


def preview(path: Path, target=(0, 0, 0.8), distance=4.2, height=2.2) -> None:
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x, scene.render.resolution_y = 1200, 800
    world = bpy.data.worlds.new("world") if not scene.world else scene.world
    scene.world = world
    world.color = (0.02, 0.02, 0.025)
    ground = bmesh.new()
    add_box(ground, (40, 40, 0.02), center=(0, 0, -0.01))
    to_object("ground", ground, material("ground", (0.42, 0.26, 0.17), 0.0, 0.95))
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    cam.location = Vector(target) + Vector((distance * 0.8, -distance, height))
    direction = Vector(target) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.filepath = str(path)
    PHOTOS.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    reset_scene()
    mats = palette()
    rover = build_rover(mats)
    export(rover, MODELS / "rover.glb")
    if "--no-preview" not in sys.argv:
        preview(PHOTOS / "model_rover.png")

    reset_scene()
    mats = palette()
    lander = build_lander(mats)
    export(lander, MODELS / "lander.glb")
    if "--no-preview" not in sys.argv:
        preview(PHOTOS / "model_lander.png", target=(0, 0, 1.3), distance=8.5, height=4.0)
    print("wrote", MODELS / "rover.glb", MODELS / "lander.glb")


if __name__ == "__main__":
    main()
