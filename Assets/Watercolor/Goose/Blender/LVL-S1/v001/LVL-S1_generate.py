"""Assemble and independently verify the S1 tailwind approach in Blender 5.2."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import runpy
import struct
import subprocess
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
import numpy as np

HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
BLEND = "LVL-S1_S1_Tailwind.blend"
GLB = "LVL-S1_S1_Tailwind.glb"
VIDEO = "preview_fixed_rear.mp4"
LAYOUT = "s1_layout.json"
EXPORT = "S1 | Ground, checkpoint and seam anchors"
REVIEW = "S1 | Wind, fork and fixed camera review"
GAME_CAMERA = "Gameplay | fixed rear"
TOP_CAMERA = "Review | formation overhead"
CONTROL = "Formation Guide | Review Controls"
SCALE = 0.9900 / 27.5
GAME = (852, 393)
TOP = (800, 960)
FPS = 24
CLIP_FPS = 8
FRAMES = 240
FORM_START = 25
FORM_END = FORM_START + FPS * 2
REFILL = (-.65, 49.96, .045)
REVIEW_ALTITUDE = .93
SOURCES = {
    "ENV-001": ["ENV-001_Flat.glb", "ENV-001_GentleSlope.glb", "ENV-001_Ridge.glb"],
    "ENV-014": ["ENV-014_CheckpointA_Visual.glb"],
    "FX-001": ["FX-001_WindTail_Long.glb", "FX-001_WindTail_Short.glb"],
    "FX-008": ["FX-008_FormationGuide.blend", "FX-008_FormationGuide.glb", "runtime_mapping.json",
               "FX-008_generate.py","textures/ft_goose_fx_formation_guide_basecolor_alpha.png"],
    "ANM-006": ["ANM-006_formation_blend.blend", "ANM-006_formation_blend.glb"],
    "ENV-005": ["ENV-005_Sparse.glb"],
    "ENV-008": ["ENV-008_LakeWide.glb"],
    "ENV-009": ["ENV-009_FarRidge_A.glb", "ENV-009_FarRidge_B.glb", "ENV-009_FarRidge_C.glb"],
    "ENV-010": ["ENV-010_Mouth.glb"],
}
DIRECT = ["ENV-001", "ENV-014", "FX-001", "FX-008", "ANM-006"]

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def read(path):
    return json.loads(path.read_text())

def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

def metadata(path):
    return {"sha256": sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}

def upstream(asset, name):
    return LIBRARY / asset / "v001" / name

def source_records():
    records = {}
    for asset, names in SOURCES.items():
        manifest_path = upstream(asset, "asset_manifest.json")
        manifest = read(manifest_path)
        qa_path = upstream(asset, "qa.json")
        qa = read(qa_path)
        require(manifest["status"] in {"needs_review", "done"}, (asset, manifest["status"]))
        require(qa["status"] in {"needs_review", "done"}, (asset, qa["status"]))
        files = {}
        for name in (*names, "README.md", "qa.json", "asset_manifest.json"):
            path = upstream(asset, name)
            require(path.stat().st_size > 0, path)
            actual = metadata(path)
            expected = manifest.get("files", manifest.get("file_sha256", {})).get(name)
            if isinstance(expected, dict):
                expected = expected.get("sha256")
            if expected:
                require(actual["sha256"] == expected, ("upstream SHA-256", asset, name))
            actual["matches_manifest"] = True if expected else None
            files[name] = actual
        records[asset] = {"version": "v001", "status": manifest["status"], "files": files,
                          "relative_dir": f"../../{asset}/v001"}
    return records

def group(scene, name):
    items = bpy.data.collections.new(name)
    scene.collection.children.link(items)
    return items

def empty(collection, name, xyz, parent=None, **props):
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    obj.parent = parent
    obj.location = xyz
    obj.empty_display_type = "ARROWS"
    obj.empty_display_size = .35
    for key, value in props.items():
        obj[key] = value
    return obj

def import_glb(scene, collection, source):
    existing = set(scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(source))
    imported = sorted(set(scene.objects) - existing, key=lambda item: item.name)
    for obj in imported:
        for old in list(obj.users_collection):
            old.objects.unlink(obj)
        collection.objects.link(obj)
    require(bool(imported), source)
    return imported

def import_asset(scene, collection, asset, name):
    return import_glb(scene, collection, upstream(asset, f"{asset}_{name}.glb"))

def place_roots(objects, location, parent=None):
    roots = [obj for obj in objects if obj.parent is None]
    for obj in roots:
        obj.parent = parent
        obj.location += Vector(location)
    return roots

def duplicate(obj, collection, name, xyz, parent=None):
    item = bpy.data.objects.new(name, obj.data)
    collection.objects.link(item)
    item.parent = parent
    item.location = xyz
    return item

def hex_color(code):
    srgb = [int(code[i:i+2], 16)/255 for i in (0, 2, 4)]
    return tuple(v/12.92 if v < .04045 else ((v+.055)/1.055)**2.4 for v in srgb) + (1.,)

def ink(name, color, emission=False):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = hex_color(color)
    if emission:
        nodes = mat.node_tree.nodes
        nodes.clear()
        glow = nodes.new("ShaderNodeEmission")
        glow.inputs["Color"].default_value = mat.diffuse_color
        out = nodes.new("ShaderNodeOutputMaterial")
        mat.node_tree.links.new(glow.outputs[0], out.inputs["Surface"])
    else:
        shader = mat.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = mat.diffuse_color
        shader.inputs["Roughness"].default_value = .9
    return mat

def mesh_object(collection, name, points, faces, material, parent=None):
    mesh = bpy.data.meshes.new(f"{name} surface")
    mesh.from_pydata(points, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.parent = parent
    obj.data.materials.append(material)
    return obj

def clipped_tile(source, collection, name, x, y, upper_half, parent):
    """Keep an exact half of the 0.625 BU tiling grid to meet the 25 and 55 joins."""
    vertices, polygons, corners = [], [], []
    mesh = source.data
    mesh.calc_loop_triangles()
    for tri in mesh.loop_triangles:
        pts = [mesh.vertices[i].co.copy() for i in tri.vertices]
        if (min(p.y for p in pts) >= -1e-6 if upper_half else max(p.y for p in pts) <= 1e-6):
            start = len(vertices)
            vertices.extend(pts)
            polygons.append(tuple(range(start, start + 3)))
            corners.extend(mesh.uv_layers.active.data[i].uv.copy() for i in tri.loops)
    obj = mesh_object(collection, name, vertices, polygons, mesh.materials[0], parent)
    uv = obj.data.uv_layers.new(name="Grid UV")
    for i, point in enumerate(corners):
        uv.data[i].uv = point
    obj.location = (x, y, 0)
    return obj

def rest_sheen(collection, parent):
    glint = ink("Checkpoint A | dry cream-sage brush", "D0D7A4", emission=True)
    points, faces = [], []
    for offset, radius, turn in ((-.15, .43, -.1), (.04, .56, .16), (.23, .36, -.04)):
        start = len(points)
        samples = 11
        for i in range(samples):
            u = i / (samples - 1)
            x = (u*2-1) * radius
            y = offset + .075*math.sin(math.pi*u) + turn*x
            width = .012 + .039 * math.sin(math.pi*u)**.8
            points.extend([(REFILL[0]+x, REFILL[1]+y-width, REFILL[2]),
                           (REFILL[0]+x, REFILL[1]+y+width, REFILL[2])])
        for i in range(samples-1):
            j = start + 2*i
            faces.append((j, j+2, j+3, j+1))
    return mesh_object(collection, "Rest_Pad_Sheen", points, faces, glint, parent)

def level_geometry(scene):
    col = group(scene, EXPORT)
    root = empty(col, "S1_Tailwind", (0, 0, 0), asset_id="LVL-S1", version="v001",
                 collision_authority="runtime", units_BU_per_game_unit=SCALE)
    terrain_group = empty(col, "Tailwind_Approach_Tiles", (0, 0, 0), root, role="terrain mesh prototypes")
    types = {}
    for variant in ("Flat", "GentleSlope", "Ridge"):
        [item] = import_asset(scene, col, "ENV-001", variant)
        types[variant] = item
    for y in (5, 15):
        for x in (-20, -10, 0, 10, 20):
            variant = "Flat" if y == 5 or abs(x) < 18 else ("GentleSlope" if x < 0 else "Ridge")
            duplicate(types[variant], col, f"Approach_{x:+03}_{y:02}", (x, y, 0), terrain_group)
    for x in (-20, -10, 0, 10, 20):
        clipped_tile(types["Flat"], col, f"Transition_{x:+03}", x, 20, True, terrain_group)
        clipped_tile(types["Flat"], col, f"Exit_Apron_{x:+03}", x, 60, False, terrain_group)
    for y in (30, 40, 50):
        duplicate(types["Flat"], col, f"East_Bank_{y:02}", (20, y, 0), terrain_group)
    reeds = import_asset(scene, col, "ENV-005", "Sparse")
    [layer] = place_roots(reeds, (0, 0, 0), terrain_group)
    bounds = world_bounds(layer)
    center_x = (bounds[0][1]+bounds[0][0])/2
    center_y = (bounds[1][1]+bounds[1][0])/2
    sx = 4.6/(bounds[0][1]-bounds[0][0])
    sy = 12.8/(bounds[1][1]-bounds[1][0])
    for i, (x,y) in enumerate([(-6.5,10.5),(7.4,16.7),(-7.8,21.5)]):
        patch = duplicate(layer, col, f"Peripheral_Reeds_{i+1:02d}",
                          (x-center_x*sx, y-center_y*sy, -.04), terrain_group)
        patch.scale = (sx,sy,.52)
    bpy.data.objects.remove(layer, do_unlink=True)
    placed = import_asset(scene, col, "ENV-014", "CheckpointA_Visual")
    [checkpoint] = place_roots(placed, (0, 50, 0), root)
    checkpoint["source"] = "ENV-014/v001"
    anchors = empty(col, "S1_Anchors", (0, 0, 0), root)
    empty(col, "Entry", (0, 0, 0), anchors, heading_BU=[0.,1.,0.])
    empty(col, "Checkpoint_A", (0, 60, 0), anchors, heading_BU=[0.,1.,0.], role="S1 exit and S2 entrance")
    empty(col, "Rest_Pad_A", (REFILL[0], REFILL[1], 0), anchors,
          role="runtime refill and retry pose candidate; ENV-014 dry pad")
    empty(col, "Wind_Centerline_Start", (0, 0, REVIEW_ALTITUDE), anchors, windDirection=[0.,1.,0.])
    empty(col, "Wind_Centerline_End", (0, 46, REVIEW_ALTITUDE), anchors, windDirection=[0.,1.,0.])
    rest_sheen(col, root)
    tile_data = types["Flat"].data
    for item in types.values():
        bpy.data.objects.remove(item, do_unlink=True)
    return col, tile_data

def fork_context(scene, tile_data):
    col=group(scene, REVIEW)
    stage = empty(col, "Fork silhouettes | review only", (0, 0, 0))
    for x in (-20, -10, 0, 10, 20):
        for y in (-25, -15, -5, 65, 75, 85, 95):
            if x >= 10 and y >= 75:
                continue
            apron = bpy.data.objects.new(f"ContextApron_{x}_{y}", tile_data)
            col.objects.link(apron)
            apron.parent = stage
            apron.location = (x, y, 0)
    surround = ink("Far meadow | washed willow", "8A9B92")
    mesh_object(col, "Context meadow", [(-210,-75,-.52),(230,-75,-.52),(230,282,-.52),(-210,282,-.52)],
                [(0,1,2,3)], surround, stage)
    lake = import_asset(scene, col, "ENV-008", "LakeWide")
    [lake_mesh] = place_roots(lake, (0, 61, 0), stage)
    lake_base = duplicate(lake_mesh, col, "Context lake backing with source outline", (0,61,-.035), stage)
    lake_base.data = lake_mesh.data.copy()
    lake_base.data.materials[0] = ink("Context lake | blue water backing", "759CA3")
    pass_mouth = import_asset(scene, col, "ENV-010", "Mouth")
    place_roots(pass_mouth, (-.8, 59.0, -.02), stage)
    for name, xyz in [
        ("FarRidge_A", (-28, 113, -.10)),
        ("FarRidge_B", (17, 137, -.1)),
        ("FarRidge_C", (0, 169, 0)),
    ]:
        items = import_asset(scene, col, "ENV-009", name)
        place_roots(items, xyz, stage)
    return col

def rewind_fcurves(obj):
    animation = obj.animation_data
    if animation and animation.action:
        for layer in animation.action.layers:
            for strip in layer.strips:
                for curve in strip.channelbag(animation.action_slot).fcurves:
                    for key in curve.keyframe_points:
                        key.interpolation = "LINEAR"

def set_keys(obj, frame, *names):
    for name in names:
        obj.keyframe_insert(data_path=name, frame=frame)

def input_controls(control):
    defaults = {
        "begin_frame": FORM_START,
        "form_seconds": 2.,
        "windBearingRad": 0.,
        "windSpeedBUPerSecond": 8.6,
        "windOpacity": .90,
        "guideOpacity": 1.,
        "outside_offset_BU": .91,
        "vertical_offset_BU": -.12,
        "ground_clearance_BU": .025,
        "dash_fill_ratio": .67,
        "width_BU": .155,
        "review_start_BU": -1.5,
        "review_end_BU": 59.94,
        "review_altitude_BU": REVIEW_ALTITUDE,
    }
    for field, value in defaults.items():
        control[field] = value
        control.id_properties_ui(field).update(description="S1 review input. Re-key via --rebuild-controls.")

def flight_y(frame, control):
    """Hold take-in, then fly to the seam with a gentle deceleration at the pad."""
    time = (frame - 1) / (FRAMES - 1)
    eased = time + .105 * math.sin(math.pi * time) - .022 * math.sin(2 * math.pi * time)
    return control["review_start_BU"] + (control["review_end_BU"]-control["review_start_BU"])*eased

def cut_nodes_to_feather(mat, fx, prop, source=None):
    """Per-instance gain is authored around the source brush alpha without modifying its PNG."""
    if source is None:
        source = next(n.image for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image is not None)
    review_mat = fx["material"](mat.name + " | S1 blend", source, True)
    nodes, links = review_mat.node_tree.nodes, review_mat.node_tree.links
    image = next(node for node in nodes if node.type == "TEX_IMAGE")
    mix = next(node for node in nodes if node.type == "MIX_SHADER")
    pigment = nodes.new("ShaderNodeEmission")
    pigment.name = "Pale ink under review lighting"
    pigment.inputs["Strength"].default_value = 1.9 if prop == "guide_alpha" else 1.7
    links.new(image.outputs["Color"], pigment.inputs["Color"])
    links.new(pigment.outputs[0], mix.inputs[2])
    return review_mat

def study_layers(scene, col, fx, motion):
    for obj in list(scene.objects):
        if obj.name.startswith("FormationGuide_"):
            bpy.data.objects.remove(obj, do_unlink=True)
    [proto] = import_asset(scene, col, "FX-008", "FormationGuide")
    image = bpy.data.images.load(str(upstream("FX-008","textures/ft_goose_fx_formation_guide_basecolor_alpha.png")))
    image.alpha_mode = "STRAIGHT"
    mat = cut_nodes_to_feather(proto.data.materials[0], fx, "guide_alpha", image)
    proto.data.materials[0] = mat
    for label, indices, sign in (("L",(1,3,5,7,9,11),-1),("R",(2,4,6,8,10),1)):
        for i, (a, b) in enumerate(zip(indices, indices[1:]), 1):
            guide = duplicate(proto, col, f"FormationGuide_{label}_{i:02}", (0,0,0), motion)
            guide.visible_shadow = False
            guide["a"], guide["b"], guide["side"] = a, b, sign
    bpy.data.objects.remove(proto, do_unlink=True)
    for variant in ("WindTail_Long", "WindTail_Short"):
        [proto] = import_asset(scene, col, "FX-001", variant)
        proto.data.materials[0] = cut_nodes_to_feather(proto.data.materials[0], fx, "wind_alpha")
        is_long = variant.endswith("Long")
        for sign in (-1,1):
            for i in range(4):
                number = i + 4*int(is_long)
                wind = duplicate(proto, col, f"{variant}_{sign:+d}_{i}", (0,0,0), motion)
                wind.visible_shadow = False
                wind["side"], wind["row"] = sign, number
                wind["phase_BU"] = (number*3.073 + (1.1 if sign==1 else 0.))
        bpy.data.objects.remove(proto, do_unlink=True)

def review_controls(scene, fx):
    motion = scene.objects["Review flight path"]
    control = scene.objects[CONTROL]
    guide_nodes = [obj for obj in scene.objects if obj.type == "MESH" and "a" in obj and "b" in obj]
    wind_nodes = [obj for obj in scene.objects if obj.type == "MESH" and "phase_BU" in obj]
    carriers = [scene.objects[f"Preview carrier | {i:02}"] for i in range(12)]
    rigs = [scene.objects[f"Review rig | {i:02}"] for i in range(12)]
    for obj in [motion, control, *guide_nodes, *wind_nodes, *carriers, *rigs]:
        obj.animation_data_clear()
    for obj in (scene.objects[GAME_CAMERA], scene.objects[TOP_CAMERA]):
        obj.hide_set(False)
    for obj in (motion, *carriers, *guide_nodes, *wind_nodes):
        obj.matrix_parent_inverse = Matrix.Identity(4)
    act = [bpy.data.actions[name] for name in ("S1 | Cruise_Flap_Loop source", "S1 | Formation_Blend source")]
    before, after = [{(c.data_path,c.array_index):c for c in fx["action_curves"](a)} for a in act]
    require(before.keys() == after.keys(), "Cruise and formation curves must address the same rig properties")
    for obj in rigs:
        obj.animation_data_create()
    cam = scene.objects[GAME_CAMERA]
    cam.matrix_parent_inverse = Matrix.Identity(4)
    cam.location = (0, -180*math.cos(.48)*SCALE, (180*math.sin(.48)-8)*SCALE)
    cam.rotation_euler = (Vector((0,0,-2*SCALE))-cam.location).to_track_quat("-Z","Y").to_euler()
    cam.data.sensor_fit = "VERTICAL"
    cam.data.lens = cam.data.sensor_height/(2*math.tan(math.radians(25)))
    cam.data.clip_end = 300
    guide_mats = {guide.data.materials[0] for guide in guide_nodes}
    wind_mats = {wind.data.materials[0] for wind in wind_nodes}
    for material in guide_mats | wind_mats:
        material.node_tree.animation_data_clear()
    bearing = control["windBearingRad"]
    along = Vector((-math.sin(bearing), math.cos(bearing)))
    across = Vector((along.y, -along.x))
    for i, frame in enumerate(range(1, FRAMES+1)):
        t = i/FPS
        completion = min(1., max(0., (frame-control["begin_frame"])/(FPS*control["form_seconds"])))
        weight = fx["smootherstep"](completion)
        control["completion"] = completion
        control["guide_alpha"] = weight*control["guideOpacity"]
        motion.location = (0, flight_y(frame, control), control["review_altitude_BU"])
        checkpoint_fade = 1-fx["smootherstep"]((motion.location.y-43)/7)
        control["wind_alpha"] = control["windOpacity"]*checkpoint_fade
        for materials, multiplier, weight_field in [
            (guide_mats, 1.85, "guide_alpha"), (wind_mats, 1.3, "wind_alpha")
        ]:
            for material in materials:
                gain = material.node_tree.nodes["Review opacity"].inputs[1]
                gain.default_value = control[weight_field]*multiplier
                gain.keyframe_insert("default_value", frame=frame)
        set_keys(motion, frame, "location")
        set_keys(control, frame, '["completion"]','["guide_alpha"]','["wind_alpha"]')
        for index, (carrier, rig) in enumerate(zip(carriers, rigs, strict=True)):
            if index:
                xy = Vector(fx["LOOSE"][index-1]).lerp(Vector(fx["COMPACT_V"][index-1]), weight)*SCALE
                carrier.location = (*xy, -2*SCALE)
            else:
                carrier.location = (0,0,0)
            set_keys(carrier, frame, "location")
            # Both actions advance together while their local bone channels blend.
            cycle_frame = 1 + (2*i + fx["PHASE_OFFSETS"][index]) % 52
            for path, component in before:
                a = before[path,component].evaluate(cycle_frame)
                b = after[path,component].evaluate(cycle_frame)
                rig.path_resolve(path)[component] = a + weight*(b-a)
                rig.keyframe_insert(path, index=component, frame=frame)
        for guide in guide_nodes:
            a, b = carriers[guide["a"]].location, carriers[guide["b"]].location
            center, yaw, scale = fx["gap_pose"](a, b, guide["side"], -motion.location.z, control)
            guide.location, guide.rotation_euler.z, guide.scale = center, yaw, scale
            set_keys(guide, frame, "location", "rotation_euler", "scale")
        for wind in wind_nodes:
            sign, row = wind["side"], wind["row"]
            phase = ((control["windSpeedBUPerSecond"]*t-motion.location.xy.dot(along)+wind["phase_BU"])%24)-4.5
            sway = (1-weight)*.31*math.sin(.91*row+1.4*t)
            drift_xy = along*phase + across*(sign*(2.85 + .41*(row%4)) + sway)
            wind.location = (*drift_xy, -.16 + .13*(row%3))
            wind.rotation_euler.z = control["windBearingRad"] + (1-weight)*sign*.09
            wire_scale = .88 + .06*(row%4)
            wind.scale = (wire_scale, wire_scale, wire_scale)
            # Fade a recycling stroke outside the visible approach without altering its U orientation.
            wind.hide_render = motion.location.y + phase > 54 or motion.location.y + phase < -12
            set_keys(wind, frame, "location", "rotation_euler", "scale", "hide_render")
    for obj in [motion, control, *guide_nodes, *wind_nodes, *carriers, *rigs]:
        rewind_fcurves(obj)
    for material in guide_mats | wind_mats:
        rewind_fcurves(material.node_tree)
    for index, rig in enumerate(rigs):
        rig.animation_data.action.name = f"S1 | phase-blended carrier {index:02d}"
    for item in list(scene.timeline_markers):
        scene.timeline_markers.remove(item)
    for frame, label in [(1,"Entry, loose flock"),(FORM_START,"Begin formation"),(FORM_END,"V formation established"),
                         (168,"Approach reed island"),(222,"Rest pad in view"),(FRAMES,"Checkpoint A to S2")]:
        scene.timeline_markers.new(label,frame=frame)
    scene.frame_set(FORM_END)

def animation_inputs(scene, fx, col):
    source = upstream("ANM-006", "ANM-006_formation_blend.blend")
    with bpy.data.libraries.load(str(source), link=False) as (before, after):
        before_names = ("Cruise_Flap_Loop", "Formation_Blend")
        require(all(name in before.actions for name in before_names), before.actions)
        after.actions = list(before_names)
    for expected, action in zip(before_names, after.actions, strict=True):
        action.name = f"S1 | {expected} source"
        action.use_fake_user = True
    for name in ("Review Ground", "Review | rear detail", "Review | top", "Review | side"):
        bpy.data.objects.remove(scene.objects[name], do_unlink=True)
    motion = scene.objects["Review flight path"]
    control = scene.objects[CONTROL]
    input_controls(control)
    study_layers(scene, col, fx, motion)
    review_controls(scene, fx)
    top = scene.objects[TOP_CAMERA]
    top.parent = None
    top.location = (0, 28, 85)
    top.rotation_euler = (0, 0, 0)
    top.data.type = "ORTHO"
    top.data.ortho_scale = 72
    top.data.clip_end = 150
    scene.frame_start, scene.frame_end = 1, FRAMES
    scene.render.fps = FPS
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = hex_color("B8CDD3")
    background.inputs["Strength"].default_value = .49
    light = scene.objects["Neutral key"]
    light.rotation_euler = (.43, -.47, -.35)
    if light.data.type == "SUN":
        light.data.energy = 1.75
        light.data.angle = .25
    light.data.color = (1.0, .935, .85)
    scene.view_settings.view_transform = "AgX"

def render(scene, output, name, frame, *, top=False, clay=False, samples=7):
    # Only technical stills may select the orthographic camera.
    scene.frame_set(frame)
    scene.camera = scene.objects[TOP_CAMERA if top else GAME_CAMERA]
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.transparent_max_bounces = 8
    scene.render.resolution_percentage = 100
    scene.render.resolution_x, scene.render.resolution_y = TOP if top else GAME
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(output / (name + ".png"))
    if clay and not bpy.data.materials.get("Graybox | neutral clay"):
        ink("Graybox | neutral clay", "999F9B")
    bpy.context.view_layer.material_override = bpy.data.materials["Graybox | neutral clay"] if clay else None
    # Clip and gameplay stills always use the native fixed camera.
    bpy.ops.render.render(write_still=True)
    bpy.context.view_layer.material_override = None

def ffmpeg(name):
    for parent in [Path("/opt/homebrew/bin"), Path("/usr/local/bin")]:
        if (parent/name).exists():
            return str(parent/name)
    return name

def video(scene, output):
    scratch = output / "frames_tmp"
    scratch.mkdir()
    for index, frame in enumerate(range(1,FRAMES+1,FPS//CLIP_FPS)):
        render(scene, scratch, f"{index:03d}", frame, samples=4)
    subprocess.run([ffmpeg("ffmpeg"), "-v", "error", "-y", "-framerate", str(CLIP_FPS), "-i",
                    str(scratch/"%03d.png"), "-vf", "pad=852:394:0:0", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "19", "-movflags", "+faststart", "-an",
                    str(output / VIDEO)], check=True)

def select_and_export(col, destination):
    bpy.ops.object.select_all(action="DESELECT")
    for item in col.objects:
        item.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(destination), export_format="GLB", export_extras=True,
                              use_selection=True, export_animations=False, export_cameras=False,
                              export_lights=False, export_yup=True)
    bpy.ops.object.select_all(action="DESELECT")

def build_layout():
    return {
        "id":"LVL-S1", "version":"v001", "status":"needs_review", "variant":"S1_Tailwind",
        "axes":{"Blender":"+Y forward, +Z up", "GLB":"(x,z,-y)", "BU_per_game_unit":SCALE},
        "entry":{"node":"Entry","location_BU":[0,0,0],"forward_BU":[0,1,0]},
        "exit":{"node":"Checkpoint_A","location_BU":[0,60,0],"forward_BU":[0,1,0],"next":"LVL-S2 Entry"},
        "seam":{"dry_ground_Z_BU":0,"water_reference_Z_BU":-.18,"flat_gate_x_BU":[-12,12],
                "exported_ground_y_BU":[0,60],"water_crosses_gate":False},
        "anchors":{
            "Checkpoint_A":{"node":"Checkpoint_A","location_BU":[0,60,0],"role":"route handoff and runtime checkpoint ID"},
            "Rest_Pad_A":{"node":"Rest_Pad_A","location_BU":[REFILL[0],REFILL[1],0],
                          "role":"physical refill area and retry-candidate position"},
            "Wind_Centerline_Start":{"node":"Wind_Centerline_Start","location_BU":[0,0,REVIEW_ALTITUDE]},
            "Wind_Centerline_End":{"node":"Wind_Centerline_End","location_BU":[0,46,REVIEW_ALTITUDE]},
        },
        "placements":{
            "ENV-014/v001":{"root":"CheckpointA_Visual","translation_BU":[0,50,0],"scale":[1,1,1]},
            "ENV-001/v001":{"meshes":"10 BU tiles in free approach, East bank and 5 BU transition/exits",
                           "flat_plane":"full width 50 BU at entry and exit"},
            "review_context":{"ENV-008/v001 LakeWide":[0,61,0],"ENV-010/v001 Mouth":[-.8,59.,-.02],
                              "GLB_omits_context":True},
        },
        "camera":{"distance_game_units":180,"pitch_rad":.48,"vertical_fov_degrees":50,
                  "target_height_game_units":6,"frame_source_px":[852,393],
                  "review_leader_root_height_BU":REVIEW_ALTITUDE,"cuts":False},
        "formation":{
            "seconds":2,"actions":["Cruise_Flap_Loop","Formation_Blend"],"asset":"ANM-006/v001",
            "guide":"FX-008/v001/FX-008_FormationGuide.glb","guide_mapping":"FX-008/v001/runtime_mapping.json",
            "parameters":{"outsideOffset_BU":.91,"verticalOffset_BU":-.12,"fillRatio":.67,
                          "minimumTerrainClearance_BU":.025,"peakOpacity":1},
            "input":["formationCompletion","heading","slotsBySide with actual positions and valid ranks","terrainHeight","effectsOpacity"],
            "placement":"Pair consecutive occupied anchors per wing; skip missing ranks and degenerate pairs. Set +Y toward near bird, center at midpoint plus right-by-heading lateral offset, clamp height to terrain+clearance.",
            "weight":"u^3*(10+u*(-15+6*u)) on clamped formationCompletion",
        },
        "tailwind":{"assets":["FX-001_WindTail_Long.glb","FX-001_WindTail_Short.glb"],"asset_version":"FX-001/v001",
                    "direction_XYZ":[0,1,0],"windBearingRad":0,"review_speed_BU_per_second":8.6,
                    "inputs":["windDirection","windSpeed","worldAnchor","time","phaseOffset","formationCompletion","effectsOpacity"],
                    "pivot":"upwind, +Y toward downstream, U grows along flow"},
        "styles":{"ENV-005/v001":"three peripheral sparse reed clusters, outside the authored compact flock"},
        "runtime_owned":["hold/toggle gesture mapping","formation speed and turning",
                         "energy cost and recovery","checkpoint activation and repeat/retry",
                         "collisions and wetland contact","dynamic flock and trigger bounds"],
    }

def save_master(scene, output):
    bpy.context.preferences.filepaths.save_version = 0
    scene.camera = scene.objects[GAME_CAMERA]
    scene.frame_set(FORM_END)
    scene.render.resolution_x, scene.render.resolution_y = GAME
    scene.render.filepath = "//preview_fixed_rear_formed.png"
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
    bpy.ops.object.select_all(action="DESELECT")
    control = scene.objects[CONTROL]
    control.select_set(True)
    bpy.context.view_layer.objects.active = control
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / BLEND))

def world_bounds(obj):
    corners = [obj.matrix_world @ Vector(p) for p in obj.bound_box]
    return [[min(v[i] for v in corners), max(v[i] for v in corners)] for i in range(3)]

def tree_for(objects):
    vertices, faces = [], []
    for item in objects:
        offset = len(vertices)
        vertices.extend(item.matrix_world @ v.co for v in item.data.vertices)
        item.data.calc_loop_triangles()
        faces.extend(tuple(offset+i for i in tri.vertices) for tri in item.data.loop_triangles)
    return BVHTree.FromPolygons(vertices, faces, all_triangles=True)

def terrain_meshes(col):
    return [o for o in col.objects if o.type=="MESH" and o.name != "Rest_Pad_Sheen"]

def geometry_checks(scene, col):
    bpy.context.view_layer.update()
    mesh = terrain_meshes(col)
    planar = [o for o in mesh if o.name.startswith(("Approach_","Transition_","Exit_Apron_","East_Bank_")) or o.name=="CheckpointA_Ground"]
    terrain = tree_for(planar)
    obstacles = tree_for(mesh)
    water = scene.objects["CheckpointA_Water"]
    water_bounds = world_bounds(water)
    require(abs(water_bounds[2][0]+.18) < 1e-5 and abs(water_bounds[2][1]+.18) < 1e-5, water_bounds)
    require(2 < water_bounds[1][0] < water_bounds[1][1] < 58, water_bounds)
    seams = {}
    for y, inward, name in [(0,1,"Entry"),(60,-1,"Checkpoint_A")]:
        z_errors = []
        for delta in (.0001,.625,1.25,1.875,2.):
            for x in np.linspace(-12, 12, 97):
                root, *_ = obstacles.ray_cast(Vector((x,y+delta*inward,10)),Vector((0,0,-1)),14)
                require(root is not None, (name,x,delta))
                z_errors.append(abs(root.z))
        require(max(z_errors) < 1e-5, (name,max(z_errors)))
        crossing = any(obstacles.ray_cast(Vector((x,y-.001*inward,5)),Vector((0,0,-1)),8)[0]
                       is not None for x in np.linspace(-12,12,97))
        require(not crossing, ("outside seam", y))
        node = scene.objects[name]
        require((node.matrix_world.translation-Vector((0,y,0))).length < 1e-5, name)
        require(tuple(node["heading_BU"])==(0,1,0), ("node heading", name))
        seams[name] = {"x_range_BU":[-12,12], "dry_gate_width_BU":24,
                       "samples":len(z_errors),"max_surface_height_error_BU":max(z_errors),
                       "outside_gate_empty_samples":97,"gate_location_BU":[0,y,0]}
    transitions = {}
    for y in (10.,20.,25.,55.):
        probes = [terrain.ray_cast(Vector((x,y+d,2)),Vector((0,0,-1)),4)[0]
                  for x in np.linspace(-11,11,49) for d in (-.001,0,.001)]
        require(all(point is not None for point in probes), ("missing terrain coverage", y))
        gaps = [max(p.z for p in probes[i:i+3])-min(p.z for p in probes[i:i+3]) for i in range(0,len(probes),3)]
        require(max(gaps)<.03, ("height jump", y,max(gaps)))
        transitions[str(y)] = {"height_difference_max_BU":max(gaps),"samples":len(probes)}
    focal = scene.objects["Rest_Pad_A"].matrix_world.translation
    pad = terrain.ray_cast(focal+Vector((0,0,3)),Vector((0,0,-1)),6)[0]
    require(pad is not None and abs(pad.z) < .002, ("dry pad", pad))
    return {"seams":seams,"water_bounds_BU":water_bounds,"tileJoins":transitions,"dry_pad_Z_BU":pad.z}, obstacles

def frame_coverage(projection):
    return projection.z > 0 and 0 <= projection.x <= 1 and 0 <= projection.y <= 1

def behavior(scene, obstacles, fx):
    control = scene.objects[CONTROL]
    camera = scene.objects[GAME_CAMERA]
    angle = 2 * math.degrees(math.atan(camera.data.sensor_height/(2*camera.data.lens)))
    require(abs(angle-50) < 1e-5 and camera.data.sensor_fit == "VERTICAL", angle)
    require(not any(marker.camera for marker in scene.timeline_markers), "Review cuts")
    guides = [o for o in scene.objects if o.name.startswith("FormationGuide_")]
    winds = [o for o in scene.objects if "phase_BU" in o]
    carriers = [scene.objects[f"Preview carrier | {i:02}"] for i in range(12)]
    birds = [scene.objects[f"Review mesh | {i:02}"] for i in range(12)]
    require(len(guides)==9 and len(winds)==16 and len(birds)==12, "review populations")
    for frame, weight in [(1,0.),(FORM_START,0.),(FORM_START+FPS,.5),(FORM_END,1.),(FRAMES,1.)]:
        scene.frame_set(frame)
        require(abs(control["guide_alpha"]-weight) < 1e-6, ("formation timer", frame, control["guide_alpha"]))
    guide_error, guide_angle_error, camera_error, nearest, width = 0., 0., 0., math.inf, 0.
    count = 0
    frames = sorted(set(range(1,FRAMES+1,5)) | {FORM_START, FORM_START+FPS, FORM_END, 184, 199, 220, FRAMES})
    v_fit = {}
    measured_gap = []
    wind_advance = []
    camera_forward_dot = 1.
    height = control["review_altitude_BU"]
    scene.render.resolution_x, scene.render.resolution_y = GAME
    for frame in frames:
        scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        leader = carriers[0].matrix_world.translation
        local_floor = -leader.z
        eye = leader + Vector((0,-180*math.cos(.48)*SCALE,180*math.sin(.48)*SCALE-8*SCALE))
        look_at = leader - Vector((0,0,2*SCALE))
        cam_ray = camera.matrix_world.to_quaternion() @ Vector((0,0,-1))
        camera_error = max(camera_error, (camera.matrix_world.translation-eye).length)
        camera_forward_dot = min(camera_forward_dot, cam_ray.dot((look_at-eye).normalized()))
        for dash in guides:
            a = carriers[dash["a"]].location
            b = carriers[dash["b"]].location
            pos, yaw, scale = fx["gap_pose"](a,b,dash["side"],local_floor,control)
            guide_error = max(guide_error, (dash.location-pos).length, (dash.scale-Vector(scale)).length)
            guide_angle_error = max(guide_angle_error, abs(dash.rotation_euler.z-yaw))
        x_min, x_max = math.inf, -math.inf
        visible_centers = 0
        for carrier, item in zip(carriers, birds, strict=True):
            cur = item.evaluated_get(depsgraph)
            matrix = cur.matrix_world.copy()
            coords = [matrix @ vertex.co for vertex in cur.data.vertices]
            x_min = min(x_min, *(v.x for v in coords))
            x_max = max(x_max, *(v.x for v in coords))
            center_view = world_to_camera_view(scene,camera,carrier.matrix_world.translation)
            visible_centers += int(frame_coverage(center_view))
            for v in coords:
                if not 1e-5 <= v.y <= 60.-1e-5:
                    continue
                found, *_ = obstacles.ray_cast(Vector((v.x,v.y,6)),Vector((0,0,-1)),9)
                require(found is not None, ("Missing flight surface", frame, item.name, list(v)))
                nearest = min(nearest,v.z-found.z)
                count += 1
        width = max(width, x_max-x_min)
        if frame in (1, FORM_START+FPS, FORM_END, 220, FRAMES):
            target = [Vector((0,0))] + [Vector(spot)*SCALE for spot in fx["COMPACT_V"]]
            error = [((carriers[i].location.xy-target[i]).length) for i in range(12)]
            rms = math.sqrt(sum(v*v for v in error)/len(error))
            v_fit[str(frame)] = {"V_target_RMS_BU":rms, "projected_centers_in_frame":visible_centers,
                                 "span_including_wingtips_BU":x_max-x_min}
        require(abs(x_min)<12 and abs(x_max)<12, ("review flock outside gate",x_min,x_max))
        if 40 < frame < 135:
            next_frame = frame+1
            prior = [w.matrix_world.translation.y for w in winds]
            camera_y = camera.matrix_world.translation.y
            scene.frame_set(next_frame)
            step = camera.matrix_world.translation.y-camera_y
            deltas = [w.matrix_world.translation.y-y for w,y in zip(winds,prior,strict=True)]
            wind_advance.extend(delta-step for delta in deltas if abs(delta) < 12)
        if frame >= 132:
            scene.frame_set(frame)
            lead_y = carriers[0].matrix_world.translation.y
            if REFILL[1]-9 < lead_y <= REFILL[1]+.35:
                cam_pos = camera.matrix_world.translation.copy()
                ref = Vector(REFILL)
                for dx,dy in [(0,0),(-.22,0),(.22,0),(0,-.12),(0,.12)]:
                    spot=ref+Vector((dx,dy,0))
                    v=spot-cam_pos
                    found,*_ = obstacles.ray_cast(cam_pos,v.normalized(),v.length-.005)
                    measured_gap.append((frame, frame_coverage(world_to_camera_view(scene,camera,spot)), found is None))
    require(camera_error < 1e-5 and camera_forward_dot > .99999, (camera_error,camera_forward_dot))
    require(guide_error < 1e-5 and guide_angle_error<1e-5, (guide_error,guide_angle_error))
    require(nearest > .015, ("Measured flight clearance",nearest,count))
    require(v_fit[str(FORM_END)]["V_target_RMS_BU"] < 1e-5, v_fit)
    require(v_fit["1"]["V_target_RMS_BU"] > .32, v_fit)
    require(v_fit[str(FORM_END)]["projected_centers_in_frame"]>=10, v_fit)
    require(wind_advance and min(wind_advance)>0, ("Wind must advance along path versus camera",wind_advance))
    clear = [row for row in measured_gap if row[1] and row[2]]
    require(len(clear)>=5, ("Rest pad not clearly approached",measured_gap))
    return {
        "samples_with_evaluated_mesh":len(frames), "clearance_vertex_rays":count,
        "minimum_vertical_clearance_BU":nearest, "max_width_including_wingtips_BU":width,
        "measured_gate_to_flock_width_ratio":24./width,
        "formation_seconds":(FORM_END-FORM_START)/FPS,"formation_comparison":v_fit,
        "guide_segments":len(guides),"maximum_dynamic_anchor_transform_error_BU":guide_error,
        "maximum_dynamic_anchor_orientation_error_rad":guide_angle_error,
        "camera":{"fov_deg":angle,"source_size_px":list(GAME),"max_eye_error_BU":camera_error,
                  "min_forward_dot":camera_forward_dot,"lead_authoring_height_BU":height},
        "wind":{"instances":len(winds),"consecutive_samples_after_wrap_excluded":len(wind_advance),
                "min_forward_motion_over_camera_BU_per_frame":min(wind_advance)},
        "refill":{"clear_in_view_rays":len(clear),"tested_rays":len(measured_gap),
                  "clear_frames":sorted(set(row[0] for row in clear))},
    }

def glb_structure(path):
    blob = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", blob)
    require((magic,version,length)==(b"glTF",2,len(blob)), path)
    njson, tag = struct.unpack_from("<I4s",blob,12)
    require(tag==b"JSON", path)
    doc=json.loads(blob[20:20+njson])
    nbin, tag=struct.unpack_from("<I4s", blob,20+njson)
    bin_data=blob[28+njson:]
    require(tag==b"BIN\0" and nbin==len(bin_data),path)
    return doc, bin_data

def texture_hashes(path):
    doc, binary = glb_structure(path)
    result = Counter()
    for image in doc.get("images", []):
        view = doc["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset",0)
        data = binary[start:start+view["byteLength"]]
        result[sha256(data).hexdigest()]+=1
    return result

def glb_proof(path):
    doc, _ = glb_structure(path)
    gltf_scene = doc["scenes"][doc.get("scene",0)]
    named = {node["name"]:node for node in doc["nodes"]}
    require([doc["nodes"][i]["name"] for i in gltf_scene["nodes"]]==["S1_Tailwind"], gltf_scene)
    require(not {"cameras","skins","animations"} & doc.keys(), "Export excludes review-only objects")
    require(all(n in named for n in ("Entry","Checkpoint_A","Rest_Pad_A","Wind_Centerline_Start",
                                      "Wind_Centerline_End","CheckpointA_Water","Rest_Pad_Sheen")), named.keys())
    require(named["Checkpoint_A"]["translation"]==[0,0,-60], named["Checkpoint_A"])
    require(all(not any(word in key for word in ("Ribbon","Review","FarRidge","Context")) for key in named), named.keys())
    expected = set().union(*(texture_hashes(upstream(id,name)) for id, name in
                             [("ENV-001", "ENV-001_Flat.glb"), ("ENV-001","ENV-001_GentleSlope.glb"),
                              ("ENV-001","ENV-001_Ridge.glb"),("ENV-005","ENV-005_Sparse.glb"),
                              ("ENV-014", "ENV-014_CheckpointA_Visual.glb")]))
    actual = texture_hashes(path)
    missing = sorted(expected-actual.keys())
    # Blender may re-encode an imported image. Return both byte checks and dimensions for the review.
    return {"node_count":len(named),"mesh_count":len(doc["meshes"]),
            "gltf_checkpoint_translation":named["Checkpoint_A"]["translation"],
            "embedded_image_count":sum(actual.values()), "expected_upstream_unique_image_count":len(expected),
            "exact_image_sha256_matches": len(expected & actual.keys()),"missing_exact_png_hashes":missing,
            "embedded_image_sha256_counts":dict(actual),
            "alpha_modes":Counter(item.get("alphaMode","OPAQUE") for item in doc["materials"])}

def read_render(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        values = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(values)
        return values.reshape(image.size[1], image.size[0], 4)[:, :, :3].copy()
    finally:
        bpy.data.images.remove(image)


def render_difference(source, compare):
    delta = np.abs(read_render(source) - read_render(compare))
    return {"mean_RGB_difference_per_255":float(delta.mean()*255),
            "pixels_with_channel_difference_at_least_5_per_255":int(np.count_nonzero(delta.max(axis=2)>5/255))}


def video_proof(path):
    command = [ffmpeg("ffmpeg"), "-hide_banner", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    capture = subprocess.check_output([ffmpeg("ffprobe"), "-v", "error", "-count_frames", "-show_streams",
                                       "-show_format", "-of", "json", str(path)])
    media = json.loads(capture)
    [stream] = media["streams"]
    require(stream["codec_type"]=="video" and (stream["width"],stream["height"])==(852,394), stream)
    require(int(stream["nb_read_frames"])==FRAMES*CLIP_FPS//FPS, stream)
    return {"decoded_all_frames":int(stream["nb_read_frames"]),"source_px":list(GAME),
            "encoded_px":[stream["width"],stream["height"]],"codec":stream["codec_name"],
            "audio_tracks":0,"seconds":float(media["format"]["duration"]),"fps":CLIP_FPS}

def generate(output, quick):
    source_records()
    fx = runpy.run_path(str(upstream("FX-008", "FX-008_generate.py")))
    bpy.ops.wm.open_mainfile(filepath=str(upstream("FX-008","FX-008_FormationGuide.blend")))
    scene = bpy.context.scene
    scene.name = "LVL-S1 | Fixed-rear field review"
    for unused in list(bpy.data.scenes):
        if unused != scene:
            bpy.data.scenes.remove(unused)
    export, tile_data = level_geometry(scene)
    review = fork_context(scene, tile_data)
    animation_inputs(scene, fx, review)
    geo, obs = geometry_checks(scene, export)
    motion = behavior(scene, obs, fx)
    print("S1_OFFLINE_GEOMETRY", json.dumps({"geometry":geo,"motion":motion}, indent=2), flush=True)
    write(output / LAYOUT, build_layout())
    select_and_export(export, output / GLB)
    print("S1_GLB", json.dumps(glb_proof(output / GLB), indent=2), flush=True)
    render(scene,output,"graybox_fixed_rear",FORM_END,clay=True)
    render(scene,output,"graybox_top",FORM_END,top=True,clay=True)
    for title, frame in [("loose",17),("forming",FORM_START+FPS),("formed",FORM_END),("checkpoint",154),("fork",236)]:
        render(scene,output,f"preview_fixed_rear_{title}",frame)
    guides = [obj for obj in scene.objects if obj.name.startswith("FormationGuide_")]
    for guide in guides:
        guide.hide_render = True
    render(scene,output,"comparison_without_formation_guide",FORM_END)
    for guide in guides:
        guide.hide_render = False
    render(scene,output,"preview_top_full_v",FORM_END,top=True)
    save_master(scene,output)
    if not quick:
        video(scene,output)

def verify(delivery, output):
    dependencies = source_records()
    layout = read(delivery / LAYOUT)
    require(layout["exit"]["location_BU"]==[0,60,0] and layout["seam"]["flat_gate_x_BU"]==[-12,12], layout)
    fx = runpy.run_path(str(upstream("FX-008", "FX-008_generate.py")))
    bpy.ops.wm.open_mainfile(filepath=str(delivery / BLEND))
    scene = bpy.context.scene
    source_group = bpy.data.collections[EXPORT]
    source_geo, obstacles = geometry_checks(scene,source_group)
    source_motion = behavior(scene,obstacles,fx)
    require(not any(img.source == "FILE" and not img.packed_file
                    for img in bpy.data.images if img.users and img.size[0]), "Packed material/input image")
    for obj in list(source_group.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    bpy.data.collections.remove(source_group)
    imported = group(scene,"S1 | Imported delivery GLB")
    import_glb(scene,imported,delivery / GLB)
    geo, imported_obs = geometry_checks(scene,imported)
    motion = behavior(scene,imported_obs,fx)
    require(motion["clearance_vertex_rays"]==source_motion["clearance_vertex_rays"], motion)
    for key in ("minimum_vertical_clearance_BU","max_width_including_wingtips_BU"):
        require(abs(motion[key]-source_motion[key])<1e-5, (key,source_motion[key],motion[key]))
    render(scene,output,"roundtrip_fixed_rear_formed",FORM_END)
    render(scene,output,"roundtrip_fixed_rear_checkpoint",154)
    print("S1 GLB reopened and restored. Running video decode.",flush=True)
    glb = glb_proof(delivery / GLB)
    video_info = video_proof(delivery / VIDEO)
    image_proofs = {}
    for phase in ("formed","checkpoint"):
        capture = f"fixed_rear_{phase}.png"
        image_proofs[phase] = render_difference(delivery/("preview_"+capture), output/("roundtrip_"+capture))
    guide_comparison = render_difference(delivery/"preview_fixed_rear_formed.png",
                                         delivery/"comparison_without_formation_guide.png")
    require(guide_comparison["pixels_with_channel_difference_at_least_5_per_255"]>30,
            ("The review guide produced no meaningful visible pixel change",guide_comparison))
    proof = {
        "id":"LVL-S1","status":"needs_review","version":"v001","blender":bpy.app.version_string,
        "independent_delivery_directory":{"reopened_blend":BLEND,"clean_scene_static_reimport":GLB,
            "import_strategy":"removed all authored export geometry before glTF import; kept fixed review rig to measure the exact same phase samples",
            "mode":"separate Blender background process","source_geometry":source_geo,"source_behavior":source_motion,
            "roundtrip_geometry":geo,"roundtrip_behavior":motion,"gltf_inspection":glb},
        "dependencies":{"direct_spec_required":DIRECT,"records_in_manifest":len(dependencies)},
        "image_comparison":{"roundtrip":image_proofs,"formed_with_and_without_guide":guide_comparison},
        "video":video_info,
        "app_baseline":{"reference":"plans/active/goose-preview-model-cleanup.md",
                        "recorded_before_this_work":"iPhone 18 Pro simulator iOS 27.2 build, 340 tests passed"},
        "pending":["负责人美术审阅：约三秒内读懂顺风、灰盒相机与地表可读性",
                   "Swift/RealityKit：结阵触发和取消、持阵能耗与转向、动态队形锚点、透明排序与检查点补给和重试",
                   "S2 实际路线提示与接缝、USDZ、App 集成以及 iPhone / iPad 真机"],
        "redline":"对照 plans/_templates/redline-checklist.md；审阅只含静音自然景物和低饱和引导。",
    }
    write(output / "qa.json",proof)

def file_manifest(delivery):
    files = {str(path.relative_to(delivery)):metadata(path) for path in sorted(delivery.rglob("*"))
             if path.is_file() and not path.name.startswith(".") and path.name!="asset_manifest.json" and "__pycache__" not in path.parts}
    write(delivery / "asset_manifest.json", {
        "id":"LVL-S1","version":"v001","variant":"S1_Tailwind","status":"needs_review",
        "tool":bpy.app.version_string,"execution_order_1_based":43,"PDF_page":17,
        "dependencies":source_records(),"direct_dependencies":DIRECT,
        "source_and_rights":"在项目已有 v001 候选许可下组装。程序创建少量审阅与补给位置笔触；未取用外部图像或声音。",
        "files":files,"layout":LAYOUT,
        "runtime_export":{"geometry":GLB,"source":BLEND,"tiling":"ENV-001 validated modular seams",
                          "visual_only":True,"dynamics":"see s1_layout.json and upstream asset mappings"},
    })

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--quick",action="store_true")
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--manifest-only",action="store_true")
    parser.add_argument("--rebuild-controls",type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    output = args.output.resolve()
    if args.manifest_only:
        file_manifest(output)
        return
    output.mkdir(parents=True, exist_ok=True)
    require(not any(output.iterdir()), f"Output directory must be empty: {output}")
    if args.verify:
        verify(args.verify.resolve(), output)
    elif args.rebuild_controls:
        bpy.ops.wm.open_mainfile(filepath=str(args.rebuild_controls.resolve()))
        fx = runpy.run_path(str(upstream("FX-008","FX-008_generate.py")))
        review_controls(bpy.context.scene,fx)
        save_master(bpy.context.scene,output)
    else:
        generate(output,args.quick)

if __name__=="__main__":
    main()
