"""Assemble and independently recheck the S6 reed-basin candidate."""
import argparse
from hashlib import sha256
from itertools import combinations, product
import json
import math
from pathlib import Path
import re
import runpy
import struct
import subprocess
import sys

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import numpy as np


HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
ASSET = "LVL-S6"
STEM = "LVL-S6_S6_Landing"
SOURCE_SCENE = "ENV-017 | Editable layout and live reeds"
EXPORT_SCENE = "S6 | Assembly export"
REVIEW_SCENE = "S6 | Approach, landing and rest"
RETURN_SCENE = "S6 | Independent GLB reassembly"
AXES = ["x", "z", "-y"]
VIEW = (852, 393)
FPS = 48
PREVIEW_RATE = 12
END = 360
FIRST_LAND = 105
DIST = 180 * .036
PITCH = .48
AIM = 6 * .036
BASE_BODY = 8 * .036
WATER_Z = -.18
BASIN_SHIFT = 20
SHALLOW_BED = -.221
TARGET_RECT = (-6.75, 6.75, 16.55, 25.65)
SLOT_DATA = (
    (0, 17.39, "mudflat"), (-2.16, 17.65, "mudflat"), (2.16, 17.59, "mudflat"),
    (-2.40, 19.94, "mudflat"), (-.33, 19.91, "mudflat"), (1.99, 19.97, "mudflat"),
    (-2.10, 22.03, "mudflat"), (.09, 22.05, "mudflat"), (2.35, 22.09, "mudflat"),
    (-5.67, 24.60, "water"), (-.22, 24.29, "mudflat"), (5.69, 24.63, "water"),
)
LAND_FILES = ("ANM-007_landing.blend", "ANM-007_landing.glb")
REST_FILES = ("ANM-008_rest_idle.blend", "ANM-008_rest_idle.glb")
ENV_FILES = ("ENV-017_landing_basin.blend", "ENV-017_LandingBasin.glb")
RIPPLE_FILES = ("FX-006_ripples.blend", "FX-006_ripples.glb", "ripple_controls.json")
FEATHER_FILES = ("FX-013_FeatherMotes.blend", "FX-013_FeatherMotes.glb", "FX-013_generate.py")
DEPENDENCIES = {
    "ENV-017": ENV_FILES, "ANM-007": LAND_FILES, "ANM-008": REST_FILES,
    "FX-006": RIPPLE_FILES, "FX-013": FEATHER_FILES,
}
PENDING = [
    "负责人复核终场暖光、芦苇框景、两种落脚节奏、水纹与落羽疏密。",
    "App 联验 S5→S6 流送与碰撞、动态槽位、触地事件、相位与水面透明排序。",
    "App 记录仅领队时仍等候、11/12 仍等候、12/12 全部入区并落脚后才结算、结算锁输入及重试重置。",
    "RealityKit / USDZ、App 接入、iPhone 和 iPad 真机画幅、触控、镜头及性能待验。",
]


def need(condition, detail):
    if not condition:
        raise ValueError(str(detail))


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def asset(id_, file=None):
    directory = LIB / id_ / "v001"
    return directory / file if file else directory


def deps():
    result = {}
    for id_, requested in DEPENDENCIES.items():
        index = read(asset(id_, "asset_manifest.json"))
        qa_file = asset(id_, "qa.json")
        qa = read(qa_file)
        files = index.get("files", index.get("files_sha256"))
        need(qa["status"] == index["status"] == "needs_review", id_)
        checks = {}
        for name, claimed in files.items():
            if isinstance(claimed, dict):
                claimed = claimed["sha256"]
            actual = digest(asset(id_, name))
            need(actual == claimed, (id_, name, actual, claimed))
            if name in requested:
                checks[name] = actual
        need(set(checks) == set(requested), (id_, checks))
        qa_key = {
            "ENV-017": "independent_delivery_reopen", "ANM-007": "blender", "ANM-008": "blender",
            "FX-006": "offline_verification_status", "FX-013": "independent_delivered_directory_recheck",
        }[id_]
        verification = qa[qa_key]
        if id_.startswith("ANM-"):
            verification = {"editable_source_reopen": verification["editable_source_reopen"],
                            "roundtrip_keys": list(verification["roundtrip"])}
        elif isinstance(verification, dict):
            verification = {k: v for k, v in verification.items() if k in ("status", "result")}
            need(verification, (id_, qa_key))
        result[id_] = {
            "version": "v001", "candidate_status": "needs_review",
            "location_relative_to_Blender_library": f"{id_}/v001",
            "verified_sha256": checks,
            "manifest_sha256": digest(asset(id_, "asset_manifest.json")),
            "qa_sha256": digest(qa_file), "reported_offline_QA": verification,
            "files_compared_with_manifest": len(files),
        }
    return result


def texture_bytes(path):
    raw = path.read_bytes()
    need(raw[:4] == b"glTF", path)
    doc_length = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20:20 + doc_length])
    binary = raw[28 + doc_length:]
    hashes = []
    for item in doc.get("images", ()):
        view = doc["bufferViews"][item["bufferView"]]
        offset = view.get("byteOffset", 0)
        hashes.append(sha256(binary[offset:offset + view["byteLength"]]).hexdigest())
    return sorted(hashes), doc


def collection(parent, name):
    result = bpy.data.collections.new(name)
    parent.children.link(result)
    return result


def object_in(group, name, data=None):
    result = bpy.data.objects.new(name, data)
    group.objects.link(result)
    return result


def active(scene):
    bpy.context.window.scene = scene
    bpy.context.view_layer.update()


def tree(obj, depsgraph=None):
    evaluated = obj.evaluated_get(depsgraph) if depsgraph else obj
    return BVHTree.FromPolygons(
        [obj.matrix_world @ v.co for v in evaluated.data.vertices],
        [tuple(face.vertices) for face in evaluated.data.polygons],
    )


def height_at(surface, x, y):
    point = surface.ray_cast((x, y, 6), (0, 0, -1), 12)[0]
    return None if point is None else point.z


def corners(obj):
    return np.asarray([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])


def terrain(scene):
    return {part: scene.objects[f"LandingBasin_{part}"] for part in ("Ground", "Water", "Reeds")}


def make_shoals(ground):
    ground.data = ground.data.copy()
    centers = [(x, y - BASIN_SHIFT) for x, y, surface in SLOT_DATA if surface == "water"]
    counts = [0, 0]
    for vertex in ground.data.vertices:
        x, y, native_z = vertex.co
        for index, (cx, cy) in enumerate(centers):
            radius = math.hypot(x - cx, (y - cy) / 1.10)
            amount = 1 - min(1, max(0, (radius - .74) / .85))
            amount = amount * amount * (3 - 2 * amount)
            if amount > 0 and native_z < SHALLOW_BED:
                vertex.co.z = native_z + amount * (SHALLOW_BED - native_z)
                counts[index] += 1
    need(min(counts) > 5, counts)
    ground.data.update()
    return counts


def clear_gate_reeds(reeds):
    reeds.data = reeds.data.copy()
    mesh = bmesh.new()
    mesh.from_mesh(reeds.data)
    removed = {v for v in mesh.verts if abs(v.co.x) <= 12.25 and v.co.y + BASIN_SHIFT < 2.25}
    queue = list(removed)
    while queue:
        vertex = queue.pop()
        for edge in vertex.link_edges:
            other = edge.other_vert(vertex)
            if other not in removed:
                removed.add(other)
                queue.append(other)
    count = len(removed)
    bmesh.ops.delete(mesh, geom=list(removed), context="VERTS")
    mesh.to_mesh(reeds.data)
    mesh.free()
    return count


def anchors(scene):
    group = collection(scene.collection, "S6 | Section and landing anchor nodes")
    rows = [
        ("S6_Entry", (0., 0., 0.), "entry seam"),
        ("S6_Terminal", (0., 21., 0.), "terminal basin focus"),
        ("S6_BasinOrigin", (0., 20., 0.), "ENV-017 local origin"),
    ]
    rows.extend((f"S6_LandingSlot_{i:02}", (x, y, WATER_Z if surface == "water" else 0.), surface)
                for i, (x, y, surface) in enumerate(SLOT_DATA, 1))
    result = []
    for name, xyz, role in rows:
        obj = object_in(group, name)
        obj.location = xyz
        obj.empty_display_type = "ARROWS"
        obj.empty_display_size = .33
        obj["role"] = role
        obj["forward_axis"] = "+Y"
        if role == "water":
            obj["bed_z_BU"] = SHALLOW_BED
        result.append({"name": name, "role": role, "blender_BU": list(xyz),
                       "glb_BU": [xyz[0], xyz[2], -xyz[1]], "forward_blender": [0, 1, 0]})
    return result


def placement():
    bpy.ops.wm.open_mainfile(filepath=str(asset("ENV-017", ENV_FILES[0])))
    bpy.context.preferences.filepaths.save_version = 0
    scene = bpy.data.scenes["ENV-017 | LandingBasin export layers"]
    active(scene)
    for other in list(bpy.data.scenes):
        if other not in (scene, bpy.data.scenes[SOURCE_SCENE]):
            bpy.data.scenes.remove(other)
    scene.name = EXPORT_SCENE
    scene.render.fps = FPS
    origin = scene.objects["LandingBasin"]
    origin.location.y = BASIN_SHIFT
    origin["role"] = "S6 terrain, water and reeds"
    layers = terrain(scene)
    changed = {"shoals": make_shoals(layers["Ground"]), "seam_reed_vertices_removed": clear_gate_reeds(layers["Reeds"])}
    points = anchors(scene)
    active(scene)
    return scene, points, changed


def append_native(name, names, keep):
    with bpy.data.libraries.load(str(name), link=False) as (source, out):
        for field, requested in names.items():
            need(set(requested) <= set(getattr(source, field)), (name, requested))
            setattr(out, field, list(requested))
    result = {field: dict(zip(requested, getattr(out, field), strict=True))
              for field, requested in names.items()}
    for obj in result.get("objects", {}).values():
        keep.objects.link(obj)
    return result


def imported(path):
    existing = set(bpy.context.scene.objects)
    need(bpy.ops.import_scene.gltf(filepath=str(path)) == {"FINISHED"}, path)
    return {obj.name: obj for obj in set(bpy.context.scene.objects) - existing}


def portable_prototypes(scene, id_, filename, names):
    out = imported(asset(id_, filename))
    result = {}
    for name in names:
        candidates = [obj for obj in out.values() if obj.type == "MESH" and
                      (obj.name == name or re.fullmatch(re.escape(name) + r"\.\d{3}", obj.name))]
        need(len(candidates) == 1, (name, out.keys()))
        result[name] = candidates[0]
    hidden = collection(scene.collection, f"{id_} | Delivered prototype geometry")
    for obj in out.values():
        for parent in tuple(obj.users_collection):
            parent.objects.unlink(obj)
        hidden.objects.link(obj)
        obj.hide_render = True
        obj.hide_set(True)
    return result


def world_pose(bird, depsgraph):
    evaluated = bird.evaluated_get(depsgraph)
    xyz = np.empty(len(evaluated.data.vertices) * 3, np.float32)
    evaluated.data.vertices.foreach_get("co", xyz)
    mat = np.asarray(evaluated.matrix_world, dtype=np.float32)
    return xyz.reshape(-1, 3) @ mat[:3, :3].T + mat[:3, 3]


def feet(bird):
    result = []
    for side in ("Foot.L", "Foot.R"):
        weight = bird.vertex_groups[side].index
        found = [v.index for v in bird.data.vertices if any(g.group == weight and g.weight > .99 for g in v.groups)]
        need(found, (bird.name, side))
        result.append(np.array(found, int))
    return result


def action_map(scene, native):
    group = collection(scene.collection, "Review actor source | CHR-001 skin and locomotion")
    if native:
        landing = append_native(asset("ANM-007", LAND_FILES[0]),
                                {"objects": ("Goose_LOD0", "GooseRig"),
                                 "actions": ("Land_Mudflat", "Land_ShallowWater")}, group)
        bird = landing["objects"]["Goose_LOD0"]
        rig = landing["objects"]["GooseRig"]
        actions = landing["actions"]
        actions.update(append_native(asset("ANM-008", REST_FILES[0]),
                                     {"actions": ("Rest_Idle",)}, group)["actions"])
    else:
        def pull(id_, name, required):
            was = set(bpy.data.actions)
            objects = imported(asset(id_, name))
            new = set(bpy.data.actions) - was
            actions = {label: next(a for a in new if a.name.split(".")[0] == label) for label in required}
            return objects, actions
        landing, actions = pull("ANM-007", LAND_FILES[1], ("Land_Mudflat", "Land_ShallowWater"))
        rig = next(o for o in landing.values() if o.type == "ARMATURE")
        bird = next(o for o in landing.values() if o.type == "MESH" and o.parent == rig)
        idle, rest = pull("ANM-008", REST_FILES[1], ("Rest_Idle",))
        actions.update(rest)
        for obj in set(idle.values()) | (set(landing.values()) - {bird, rig}):
            bpy.data.objects.remove(obj, do_unlink=True)
    return bird, rig, actions


def sample_poses(scene, bird, rig, actions):
    indices = feet(bird)
    both = np.concatenate(indices)
    cache = {}
    for label, action in actions.items():
        rig.animation_data_clear()
        rig.animation_data_create().action = action
        rig.animation_data.action_slot = action.slots[0]
        frame_start, frame_end = (round(x) for x in action.frame_range)
        expected_span = 144 if label == "Rest_Idle" else 80
        need(frame_end - frame_start == expected_span, (label, frame_start, frame_end))
        poses = []
        for f in range(frame_start, frame_end + 1):
            scene.frame_set(f)
            poses.append(world_pose(bird, bpy.context.evaluated_depsgraph_get()))
        cache[label] = poses
    for clip in ("Land_Mudflat", "Land_ShallowWater"):
        need(np.max(np.abs(cache[clip][-1] - cache["Rest_Idle"][0])) < .0001, clip)
    rig.animation_data_clear()
    return cache, indices, both


def curves(item, path=None):
    animation = item.animation_data
    result = animation.action.layers[0].strips[0].channelbag(animation.action_slot).fcurves
    return [curve for curve in result if path is None or curve.data_path == path]


def carrier_motion(poses, both, contact, x, y, support, start):
    heel = both[int(np.argmin(poses[contact][both, 2]))]
    end_y = float(poses[-1][heel, 1])
    anchor_y = end_y - float(poses[contact][heel, 1])
    start_y = y + anchor_y - 1.42
    start_height = .56
    keys = {1: (x, start_y - 17.3, start_height),
            47: (x, start_y - 8.9, start_height),
            FIRST_LAND: (x, start_y - (start - FIRST_LAND) * .0025, start_height),
            start: (x, start_y, start_height)}
    for j, pos in enumerate(poses):
        sole = float(pos[both, 2].min())
        if j < contact:
            t = j / contact
            base = support - sole
            xy = y + anchor_y - 1.42 * (1 - t) ** 2
            z = base + (start_height - support + float(poses[0][both, 2].min())) * (1 - t) ** 2
        else:
            xy = y + end_y - float(pos[heel, 1])
            z = support - sole
        keys[start+j] = (x, xy, z)
    return keys


def build_actors(scene, native):
    scene.render.fps = FPS
    bird, rig, actions = action_map(scene, native)
    poses, _, both = sample_poses(scene, bird, rig, actions)
    actors = []
    group = collection(scene.collection, "S6 | Twelve editable review carriers")
    for i, (x, y, surface) in enumerate(SLOT_DATA, 1):
        label = "Land_ShallowWater" if surface == "water" else "Land_Mudflat"
        support = WATER_Z if surface == "water" else 0.
        start = FIRST_LAND + (i - 1) * 6
        contact = 50 if surface == "water" else 46
        rest_start = start + 81
        root = object_in(group, f"S6_Carrier_{i:02}")
        root.empty_display_size = .16
        root["slot"] = f"S6_LandingSlot_{i:02}"
        root["action_start"] = start
        root["contact_frame"] = start + contact
        root["rest_start"] = rest_start
        root["substrate"] = surface
        root["surface_z_BU"] = support
        armature = rig.copy()
        armature.name = f"S6_Rig_{i:02}"
        group.objects.link(armature)
        armature.parent = root
        if native:
            armature.matrix_parent_inverse.identity()
        armature.animation_data_clear()
        track = armature.animation_data_create().nla_tracks.new()
        track.name = "S6 | landing then rest"
        action = actions[label]
        land_strip = track.strips.new(label, start, action)
        land_strip.action_slot = action.slots[0]
        land_strip.extrapolation = "HOLD"
        rest = actions["Rest_Idle"]
        rest_strip = track.strips.new(rest.name, rest_start, rest)
        rest_strip.action_slot = rest.slots[0]
        rest_strip.extrapolation = "HOLD_FORWARD"
        rest_strip.repeat = 3
        member = bird.copy()
        member.name = f"S6_Goose_{i:02}"
        group.objects.link(member)
        member.parent = armature
        next(m for m in member.modifiers if m.type == "ARMATURE").object = armature
        for frame, xyz in carrier_motion(poses[label], both, contact, x, y, support, start).items():
            root.location = xyz
            root.keyframe_insert("location", frame=frame)
        for curve in curves(root):
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"
        actors.append((root, member))
    bpy.data.objects.remove(bird, do_unlink=True)
    bpy.data.objects.remove(rig, do_unlink=True)
    return actors


def recovered_actors(scene):
    return [(scene.objects[f"S6_Carrier_{i:02}"], scene.objects[f"S6_Goose_{i:02}"]) for i in range(1, 13)]


def source_floor():
    edit = bpy.data.scenes.get(SOURCE_SCENE)
    if edit is not None:
        return next(obj.data for obj in edit.objects if obj.type == "MESH" and obj.name.startswith("Flat |"))
    with bpy.data.libraries.load(str(asset("ENV-017", ENV_FILES[0])), link=False) as (source, target):
        names = [name for name in source.objects if name.startswith("Flat |")]
        need(names, str(asset("ENV-017")))
        target.objects = [names[0]]
    floor, = target.objects
    data = floor.data
    bpy.data.objects.remove(floor, do_unlink=True)
    return data


def backdrop(scene):
    material = source_floor()
    group = collection(scene.collection, "Review only | Terrain beyond S6")
    for x, y in product(range(-75, 76, 10), range(-25, 116, 10)):
        if -20 < x < 20 and 0 < y < 40:
            continue
        obj = object_in(group, f"Closure plate {x} {y}", material)
        obj.location = (x, y, 0)


def camera_controls(scene, leader):
    group = collection(scene.collection, "Review only | Fixed rear camera, technical overhead and lights")
    camera = object_in(group, "S6_ThirdPersonRig", bpy.data.cameras.new("S6 | focal 50 degrees vertical"))
    camera.data.sensor_fit = "VERTICAL"
    camera.data.lens = camera.data.sensor_height * .5 / math.tan(math.radians(25))
    camera.data.clip_start, camera.data.clip_end = .05, 200
    eye = Vector((0, -DIST * math.cos(PITCH), DIST * math.sin(PITCH)))
    camera.rotation_euler = (Vector((0, 0, AIM)) - eye).to_track_quat("-Z", "Y").to_euler()
    for axis in range(3):
        driver = camera.driver_add("location", axis).driver
        v = driver.variables.new()
        v.name = "leader"
        v.type = "TRANSFORMS"
        v.targets[0].id = leader
        v.targets[0].transform_space = "WORLD_SPACE"
        v.targets[0].transform_type = ("LOC_X", "LOC_Y", "LOC_Z")[axis]
        offset = eye[axis] - (BASE_BODY if axis == 2 else 0)
        driver.expression = f"leader+({offset})"
    camera["swift_source"] = "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift"
    camera["distance_game_units"] = 180
    camera["pitch_rad"] = PITCH
    camera["vertical_fov_deg"] = 50
    camera["aim_height_game_units"] = 6
    overhead = object_in(group, "S6_TechnicalOverview", bpy.data.cameras.new("S6 | top view"))
    overhead.data.type = "ORTHO"
    overhead.data.ortho_scale = 19.7
    overhead.location = (0., 22.45, 17.)
    scene.camera = camera
    return group, camera, overhead


def lighting(scene, group):
    scene.world = bpy.data.worlds.new("S6 | soft pale morning")
    scene.world.use_nodes = True
    shade = scene.world.node_tree.nodes["Background"]
    shade.inputs["Color"].default_value = (.56, .67, .74, 1.)
    shade.inputs["Strength"].default_value = .48
    sun = object_in(group, "Warm low sun", bpy.data.lights.new("Warm low sun", "SUN"))
    sun.rotation_euler = Vector((.58, -.67, -.56)).to_track_quat("-Z", "Y").to_euler()
    sun.data.energy, sun.data.angle = 2.18, .23
    sun.data.color = (1., .82, .58)
    sky = object_in(group, "Diffuse skylight", bpy.data.lights.new("Diffuse skylight", "SUN"))
    sky.rotation_euler = Vector((-.25, .33, -1.)).to_track_quat("-Z", "Y").to_euler()
    sky.data.energy, sky.data.angle = 1.08, .48
    sky.data.color = (.78, .90, 1.)
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = .28
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 12
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"


def ripple_image(obj):
    return next(node.image for node in obj.data.materials[0].node_tree.nodes if node.type == "TEX_IMAGE")


def idle_ripples(water, proto, controls):
    water.data = water.data.copy()
    for i, mat in enumerate(water.data.materials):
        water.data.materials[i] = mat.copy()
        graph = water.data.materials[i].node_tree
        nodes, links = graph.nodes, graph.links
        shader = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
        source = shader.inputs["Base Color"].links[0].from_socket
        pos = nodes.new("ShaderNodeNewGeometry")
        scale = nodes.new("ShaderNodeVectorMath")
        scale.operation = "MULTIPLY"
        scale.inputs[1].default_value = (1/3.2, 1/2.4, 0.)
        links.new(pos.outputs["Position"], scale.inputs[0])
        shift = nodes.new("ShaderNodeVectorMath")
        shift.operation = "ADD"
        shift.name = "S6 | Continuous UV drift"
        v = shift.inputs[1].driver_add("default_value", 0).driver
        v.expression = "(frame-1)*.0625/48"
        links.new(scale.outputs[0], shift.inputs[0])
        image = nodes.new("ShaderNodeTexImage")
        image.name = "S6 | FX-006 shared idle pigment"
        image.image, image.extension = ripple_image(proto), "REPEAT"
        links.new(shift.outputs[0], image.inputs[0])
        blend = nodes.new("ShaderNodeMath")
        blend.operation = "MULTIPLY"
        blend.inputs[1].default_value = controls[RIPPLE_FILES[2]]["Ripple_Idle"]["default_pigment_gain"] * .40
        blend.use_clamp = True
        links.new(image.outputs["Alpha"], blend.inputs[0])
        mix = nodes.new("ShaderNodeMixRGB")
        links.new(blend.outputs[0], mix.inputs[0])
        links.new(source, mix.inputs[1])
        links.new(image.outputs["Color"], mix.inputs[2])
        links.new(mix.outputs[0], shader.inputs["Base Color"])


def contact_points(actor, depsgraph, indices):
    pose = world_pose(actor, depsgraph)
    return np.asarray([pose[one][int(np.argmin(pose[one, 2]))] for one in indices])


def animate_ripples(scene, actors, proto, control):
    group = collection(scene.collection, "FX-006 | Independent water contact ripples")
    objects = []
    for i, (root, bird) in enumerate(actors, 1):
        if root["substrate"] != "water":
            continue
        contact = root["contact_frame"]
        scene.frame_set(contact)
        points = contact_points(bird, bpy.context.evaluated_depsgraph_get(), feet(bird))
        center = points.mean(axis=0)
        obj = object_in(group, f"S6_Ripple_{i:02}", proto.data)
        obj["goose_index_1_based"] = i
        obj["contact_frame"] = contact
        obj.location = (float(center[0]), float(center[1]), WATER_Z + .01)
        obj.material_slots[0].link = "OBJECT"
        mat = proto.data.materials[0].copy()
        mat.surface_render_method = "DITHERED"
        obj.material_slots[0].material = mat
        graph = mat.node_tree
        img = next(n for n in graph.nodes if n.type == "TEX_IMAGE")
        shader = next(n for n in graph.nodes if n.type == "BSDF_PRINCIPLED")
        opacity = graph.nodes.new("ShaderNodeMath")
        opacity.operation = "MULTIPLY"
        actor = graph.nodes.new("ShaderNodeObjectInfo")
        graph.links.new(img.outputs["Color"], shader.inputs["Emission Color"])
        shader.inputs["Emission Strength"].default_value = .42
        graph.links.new(img.outputs["Alpha"], opacity.inputs[0])
        graph.links.new(actor.outputs["Alpha"], opacity.inputs[1])
        graph.links.new(opacity.outputs[0], shader.inputs["Alpha"])
        for sample in control["envelope"]:
            f = contact + sample["ageSeconds"] * FPS
            obj.scale = (sample["scale"], sample["scale"], 1.)
            obj.keyframe_insert("scale", frame=f)
            obj.color[3] = sample["opacity"]
            obj.keyframe_insert("color", frame=f, index=3)
        for curve in curves(obj):
            for key in curve.keyframe_points:
                key.handle_left_type = key.handle_right_type = "AUTO_CLAMPED"
        objects.append(obj)
    return objects


def feather_scene(scene, camera, starts, prototypes):
    fx = runpy.run_path(str(asset("FX-013", FEATHER_FILES[2])))
    group = collection(scene.collection, "FX-013 | Optional feather and mote visual")
    ctrl = object_in(group, "S6_FeatherMotes_Controls")
    for name, value, low, high, text in (
        ("enabled", 1, 0, 1, "Switch this optional visual on or off."),
        ("intensity", .72, 0, 1, "Straight alpha multiplier."),
        ("allLandingStartFrame", max(starts), 1, END, "Preview event when all assigned members have begun landing."),
        ("sideDriftBUPerSecond", .13, -.5, .5, "Lateral drift in Blender units per second."),
        ("fallSpeedMultiplier", 1., .4, 1.4, "Visual fall rate."),
    ):
        fx["prop"](ctrl, name, value, low, high, text)
    # Keep the FX-013 particle layout in the ENV-017 local frame.
    mount = object_in(group, "S6 | Feather origin at ENV-017 pivot")
    mount.location.y = BASIN_SHIFT
    result = fx["make_instances"](group, camera, ctrl, prototypes, None)
    for item in result:
        item.parent.parent = mount
    return ctrl, result


def review(scene, layers, native):
    active(scene)
    system = read(asset("FX-006", RIPPLE_FILES[2]))
    backdrop(scene)
    actors = build_actors(scene, native)
    group, camera, overview = camera_controls(scene, actors[0][0])
    lighting(scene, group)
    ripple_cards = portable_prototypes(scene, "FX-006", RIPPLE_FILES[1], ("Ripple_Idle", "Ripple_Landing"))
    idle_ripples(layers["Water"], ripple_cards["Ripple_Idle"], {RIPPLE_FILES[2]: system})
    ripples = animate_ripples(scene, actors, ripple_cards["Ripple_Landing"], system["Ripple_Landing"])
    particle_cards = portable_prototypes(scene, "FX-013", FEATHER_FILES[1],
                                         ("FeatherMotes_Feather", "FeatherMotes_Mote"))
    starts = [root["action_start"] for root, _ in actors]
    ctrl, particles = feather_scene(scene, camera, starts, particle_cards)
    scene.frame_start, scene.frame_end, scene.render.fps = 1, END, FPS
    last = actors[-1][0]
    for frame, label in (
        (1, "Approach at the S5 / S6 boundary"), (starts[0], "Leader landing start"),
        (actors[0][0]["contact_frame"], "Leader contact"), (max(starts), "All landing clips started"),
        (last["contact_frame"], "Twelfth water contact"), (last["rest_start"], "All in rest clips"),
    ):
        scene.timeline_markers.new(label, frame=frame)
    return {"actors": actors, "layers": layers, "camera": camera, "overview": overview, "ripples": ripples,
            "feather_control": ctrl, "particles": particles}


def seam(scene, layers):
    active(scene)
    grass = tree(layers["Ground"])
    water = tree(layers["Water"])
    reeds = tree(layers["Reeds"])
    probes = [(-12 + .25 * i, .05 + .20 * j) for i in range(97) for j in range(11)]
    ground = [height_at(grass, x, y) for x, y in probes]
    need(all(z is not None for z in ground), "S6 entry strip has holes")
    maximum = max(abs(z) for z in ground)
    need(maximum < .00002, ("terrain gate is not flat", maximum))
    # Inspect plane exactly on the row of source mesh vertices and ray sample the
    # strip interior separately, as rays directly on shared edges are ambiguous.
    extent = []
    for part in layers.values():
        coords = corners(part)
        gate_vertices = coords[np.abs(coords[:, 0]) <= 12.00001]
        extent.append(float(gate_vertices[:, 1].min()))
    need(abs(extent[0]) < .00002 and min(extent[1:]) > 2.05, extent)
    need(all(height_at(water, x, y) is None and height_at(reeds, x, y) is None for x, y in probes),
         "the dry protected entry strip contains water or reeds")
    entry = scene.objects["S6_Entry"]
    need(entry.type == "EMPTY" and entry.matrix_world.translation.length < .00001, entry.name)
    angle = (entry.matrix_world.to_3x3() @ Vector((0, 1, 0))).angle(Vector((0, 1, 0)))
    need(angle < .00001, angle)
    return {"flat_strip_probes": len(probes), "protected_strip_x_BU": [-12, 12],
            "interior_sample_y_BU": [.05, 2.05], "max_ground_height_error_BU": maximum,
            "closest_terrain_water_reeds_Y_BU_within_strip": extent,
            "reeds_and_water_hits_in_strip": 0, "anchor": entry.name, "yaw_error_radians": angle}


def roundtrip_mask(scene, camera, actor):
    pose = world_pose(actor, bpy.context.evaluated_depsgraph_get())
    actor.data.calc_loop_triangles()
    project = [world_to_camera_view(scene, camera, Vector(p)) for p in pose]
    need(all(p.z > 0 for p in project), actor.name)
    xx = [p.x * VIEW[0] for p in project]
    yy = [p.y * VIEW[1] for p in project]
    margin = min(min(xx), VIEW[0]-max(xx), min(yy), VIEW[1]-max(yy))
    bounds_width = max(xx) - min(xx)
    idx = [tuple(t.vertices) for t in actor.data.loop_triangles]
    masks = runpy.run_path(str(asset("ENV-017", "ENV-017_generate.py")))["raster_silhouette"]
    return masks(project, idx), margin, bounds_width


def camera_error(scene, camera, leader):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eye = camera.evaluated_get(depsgraph).matrix_world
    lead = leader.evaluated_get(depsgraph).matrix_world.translation
    expected = Vector((0., -DIST * math.cos(PITCH), DIST * math.sin(PITCH)))
    forward = eye.to_3x3() @ Vector((0., 0., -1.))
    look = Vector((0., 0., AIM)) - expected
    vertical_fov = 2 * math.degrees(math.atan(camera.data.sensor_height * .5 / camera.data.lens))
    offset = expected - Vector((0., 0., BASE_BODY))
    result = ((eye.translation-lead-offset).length, forward.angle(look), abs(50 - vertical_fov))
    need(result[0] < .00001 and result[1] < .0004 and result[2] < .00001, result)
    return result


def projected_proof(scene, state, reed_bvh, frame):
    scene.frame_set(frame)
    camera = state["camera"]
    stage = bpy.context.evaluated_depsgraph_get()
    eye = camera.evaluated_get(stage).matrix_world.translation
    casts = 0
    masks, margins, widths = [], [], []
    for _, bird in state["actors"]:
        mask, margin, width = roundtrip_mask(scene, camera, bird)
        need(margin > 0 and width > 14, (bird.name, frame, margin, width))
        masks.append(mask)
        margins.append(margin)
        widths.append(width)
        pose = world_pose(bird, stage)
        for v in pose[::9]:
            delta = Vector(v) - eye
            hit = reed_bvh.ray_cast(eye, delta.normalized(), delta.length-.005)[0]
            casts += 1
            need(hit is None, ("reed blocks bird in fixed camera", bird.name, frame, list(hit) if hit else None))
    combined = np.sum(masks, axis=0) > 1
    overlap = [float(np.count_nonzero(mask & combined) / np.count_nonzero(mask)) for mask in masks]
    need(max(overlap) < .15, (frame, overlap))
    return {"frame": frame, "minimum_horizontal_bird_width_px": min(widths),
            "minimum_frame_edge_margin_px": min(margins), "maximum_bird_overlap_fraction": max(overlap),
            "reed_occlusion_sample_rays": casts, "reed_occlusion_hits": 0}


def limb_probes(pose, weighted):
    points = []
    for one in weighted:
        foot = pose[one]
        order = foot[:, 2].argsort()
        points.append(foot[order[:8]])
    return points


def stage_proof(scene, state):
    active(scene)
    actors = state["actors"]
    layers = state["layers"]
    ground, water, reeds = (tree(layers[key]) for key in ("Ground", "Water", "Reeds"))
    weighted = [feet(bird) for _, bird in actors]
    catch = [root["contact_frame"] for root, _ in actors]
    first_rest = [root["rest_start"] for root, _ in actors]
    marked = [catch[0], catch[-2], catch[-1], max(first_rest)+44, END]
    sample = sorted(set(range(1, END + 1, 2)) | set(marked) | set(catch) | set(first_rest))
    anchors_by_i = [None for _ in actors]
    metrics = {
        "max_absolute_gap_of_either_landed_foot_BU": 0.,
        "minimum_pose_probe_clearance_to_ground_BU": math.inf,
        "minimum_wet_contact_depth_BU": math.inf,
        "maximum_wet_contact_depth_BU": -math.inf,
        "smallest_interbird_AABB_axis_gap_BU": math.inf,
        "leader_stationary_drift_after_landing_clip_BU": 0.,
        "camera_eye_error_BU": 0.,
        "camera_aim_error_radians": 0.,
        "camera_fov_error_degrees": 0.,
        "world_reed_probe_count": 0,
        "world_reed_hits": 0,
        "travel_reed_overflight_probes": 0,
        "min_overflown_reed_vertical_clearance_BU": math.inf,
    }
    samples = {}
    snapshot = {}
    leader_reference = None
    for f in sample:
        scene.frame_set(f)
        stage = bpy.context.evaluated_depsgraph_get()
        camera_errors = camera_error(scene, state["camera"], actors[0][0])
        for key, val in zip(("camera_eye_error_BU", "camera_aim_error_radians", "camera_fov_error_degrees"), camera_errors, strict=True):
            metrics[key] = max(metrics[key], val)
        boxes = []
        contacts = []
        true_in_zone = 0
        landed = 0
        for i, (root, bird) in enumerate(actors):
            pose = world_pose(bird, stage)
            low, high = pose.min(axis=0), pose.max(axis=0)
            boxes.append((low, high))
            probes = [pose[j] for j in (
                pose[:, 0].argmin(), pose[:, 0].argmax(), pose[:, 1].argmin(),
                pose[:, 1].argmax(), pose[:, 2].argmin(),
            )]
            for point in probes:
                x, y, z = (float(x) for x in point)
                hit = reeds.ray_cast((x, y, 3.), (0., 0., -1.), 4.)[0]
                metrics["world_reed_probe_count"] += 1
                if hit is not None:
                    clearance = z - hit.z
                    need(clearance > .01, ("reed clearance", f, i + 1, list(point), list(hit), clearance))
                    metrics["travel_reed_overflight_probes"] += 1
                    metrics["min_overflown_reed_vertical_clearance_BU"] = min(
                        metrics["min_overflown_reed_vertical_clearance_BU"], clearance)
                floor = height_at(ground, x, y)
                if floor is not None:
                    metrics["minimum_pose_probe_clearance_to_ground_BU"] = min(
                        metrics["minimum_pose_probe_clearance_to_ground_BU"], z - floor)
                    need(z - floor > -.003, ("terrain penetration", f, i+1, list(point), floor))
            if f >= catch[i]:
                landed += 1
                band = limb_probes(pose, weighted[i])
                wet = root["substrate"] == "water"
                gaps = []
                for group in band:
                    foot_gaps = []
                    for x, y, z in group:
                        surface = height_at(water if wet else ground, float(x), float(y))
                        need(surface is not None, (f, i+1, "missing supporting surface"))
                        foot_gaps.append(float(z - surface))
                        if wet:
                            bed = height_at(ground, float(x), float(y))
                            depth = surface - bed
                            need(.031 < depth < .082, ("shallow foot depth", f, i+1, depth))
                            metrics["minimum_wet_contact_depth_BU"] = min(metrics["minimum_wet_contact_depth_BU"], depth)
                            metrics["maximum_wet_contact_depth_BU"] = max(metrics["maximum_wet_contact_depth_BU"], depth)
                    gaps.append(min(foot_gaps))
                max_gap = max(abs(gap) for gap in gaps)
                need(max_gap < .009, ("foot contact", f, i+1, gaps))
                metrics["max_absolute_gap_of_either_landed_foot_BU"] = max(
                    metrics["max_absolute_gap_of_either_landed_foot_BU"], max_gap)
                if f == catch[i]:
                    hit = np.mean([points[0].tolist() for points in band], axis=0)
                    anchors_by_i[i] = list(hit)
                if TARGET_RECT[0] <= low[0] and high[0] <= TARGET_RECT[1] and TARGET_RECT[2] <= low[1] and high[1] <= TARGET_RECT[3]:
                    true_in_zone += 1
                contacts.append(gaps)
            else:
                contacts.append(None)
        for i, j in combinations(range(12), 2):
            a, b = boxes[i], boxes[j]
            separation = float(np.max(np.maximum(a[0] - b[1], b[0] - a[1])))
            metrics["smallest_interbird_AABB_axis_gap_BU"] = min(
                metrics["smallest_interbird_AABB_axis_gap_BU"], separation)
            need(separation > 0, ("crowding", f, i + 1, j + 1, separation))
        if f >= first_rest[0]:
            point = actors[0][0].matrix_world.translation.copy()
            if leader_reference is None:
                leader_reference = point
            drift = (point - leader_reference).length
            metrics["leader_stationary_drift_after_landing_clip_BU"] = max(
                metrics["leader_stationary_drift_after_landing_clip_BU"], drift)
            need(drift < .00001, (f, drift))
        if f in marked:
            snapshot[str(f)] = {"landed_geese": landed, "landed_inside_target": true_in_zone,
                                "review_prediction_only": "all_12_contact" if true_in_zone == 12 else "waiting"}
            samples[str(f)] = [[lo.tolist(), hi.tolist()] for lo, hi in boxes]
    need([snapshot[str(frame)]["landed_inside_target"] for frame in marked[:3]] == [1, 11, 12], snapshot)
    px = [projected_proof(scene, state, reeds, frame) for frame in (max(first_rest)+44, END)]
    return {"result": "pass", "frames_sampled": len(sample), "frame_span": [1, END],
            "actor_pairs_tested": len(sample) * 66, "metrics": metrics, "key_frames": snapshot,
            "fixed_camera_projection": px, "contact_positions_BU": anchors_by_i,
            "leader_wait_between_contact_events_seconds": (catch[-1] - catch[0]) / FPS,
            "pose_box_samples": samples}


def ripple_proof(scene, state, dynamics):
    water = tree(state["layers"]["Water"])
    group = state["ripples"]
    need(len(group) == 2, len(group))
    results = []
    for obj in group:
        i = int(obj["goose_index_1_based"]) - 1
        contact = int(obj["contact_frame"])
        center = dynamics["contact_positions_BU"][i]
        offset = math.hypot(obj.location.x - center[0], obj.location.y - center[1])
        need(offset < .00005, (obj.name, offset))
        actual = ripple_image(obj)
        pixel_values = np.empty(actual.size[0] * actual.size[1] * 4, dtype=np.float32)
        actual.pixels.foreach_get(pixel_values)
        alpha = pixel_values.reshape(actual.size[1], actual.size[0], 4)[:, :, 3]
        ys, xs = np.where(alpha > .035)
        stride = max(1, len(xs) // 700)
        card_span = 2.2 * 1.12
        for xx, yy in zip(xs[::stride], ys[::stride], strict=True):
            x = obj.location.x + card_span * (xx / (actual.size[0]-1) - .5)
            y = obj.location.y + card_span * (yy / (actual.size[1]-1) - .5)
            hit = height_at(water, x, y)
            need(hit is not None and abs(hit-WATER_Z) < .00001, (obj.name, x, y, "visible ripple strays off water"))
        opacity = []
        sizes = []
        for at in (contact - 1, contact, contact + 15, contact + 31, contact + 53, contact + 87):
            scene.frame_set(at)
            opacity.append(float(obj.color[3]))
            sizes.append(obj.scale.x)
        need(opacity[0] == opacity[1] == opacity[-1] == 0 and opacity[2] > .97 and
             all(a <= b for a, b in zip(sizes, sizes[1:])), (obj.name, sizes, opacity))
        results.append({"slot": i+1, "center_error_BU": offset, "visible_footprint_water_samples": len(xs[::stride]),
                        "surface_offset_BU": obj.location.z-WATER_Z, "opacity_samples": opacity, "contact_frame": contact})
    return {"result": "pass", "single_trigger_per_water_slot": True, "dry_slots_with_landing_ripples": 0,
            "per_instance": results}


def render(scene, camera, destination, size=VIEW, samples=14):
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.eevee.taa_render_samples = samples
    scene.render.filepath = str(destination)
    need(bpy.ops.render.render(write_still=True) == {"FINISHED"}, destination)


def still(scene, state, output, name, frame, top=False, samples=16):
    scene.frame_set(frame)
    render(scene, state["overview"] if top else state["camera"], output / f"{name}.png",
           (880, 760) if top else VIEW, samples)


def graybox(scene, state, output):
    colors = {"Ground": (.34, .37, .33, 1), "Water": (.24, .31, .37, 1),
              "Reeds": (.17, .23, .17, 1), "Actors": (.58, .57, .54, 1)}
    gray_mats = {}
    for group, color in colors.items():
        mat = bpy.data.materials.new(f"Graybox | {group}")
        mat.use_nodes = True
        mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = color
        gray_mats[group] = mat
    candidates = dict(state["layers"])
    candidates["Actors"] = state["actors"][0][1]
    saved = []
    for key, obj in candidates.items():
        for i, mat in enumerate(obj.data.materials):
            saved.append((obj, i, mat))
            obj.data.materials[i] = gray_mats[key]
    backdrop_data = next(obj.data for obj in scene.objects if obj.name.startswith("Closure plate "))
    for i, mat in enumerate(backdrop_data.materials):
        saved.append((backdrop_data, i, mat))
        backdrop_data.materials[i] = gray_mats["Ground"]
    osc = state["feather_control"]
    osc["enabled"] = 0
    osc.update_tag()
    for obj in state["ripples"]:
        obj.hide_render = True
    try:
        still(scene, state, output, "graybox_fixed_rear", 300)
        still(scene, state, output, "graybox_top", 300, top=True)
    finally:
        for obj, i, mat in saved:
            (obj.data if isinstance(obj, bpy.types.Object) else obj).materials[i] = mat
        for obj in state["ripples"]:
            obj.hide_render = False
        osc["enabled"] = 1
        osc.update_tag()


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def encode(scene, state, output):
    frames = output / ".frames"
    frames.mkdir()
    step = FPS // PREVIEW_RATE
    for i, frame in enumerate(range(1, END + 1, step)):
        scene.frame_set(frame)
        render(scene, state["camera"], frames / f"{i:04d}.png", samples=8)
    run("ffmpeg", "-hide_banner", "-loglevel", "error", "-framerate", str(PREVIEW_RATE),
        "-i", str(frames / "%04d.png"), "-vf", "pad=852:394:0:0", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-crf", "18", "-an", "-movflags", "+faststart", str(output / "preview_fixed_rear.mp4"))
    for frame in frames.glob("*.png"):
        frame.unlink()
    frames.rmdir()


def rgb_difference(first, second, threshold=3):
    def pixels(path):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo",
                              "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
        return np.frombuffer(raw, dtype=np.uint8).astype(np.int16).reshape(VIEW[1], VIEW[0], 3)
    delta = np.max(np.abs(pixels(first) - pixels(second)), axis=2)
    return {"threshold_rgb_out_of_255": threshold, "changed_pixels": int(np.count_nonzero(delta >= threshold)),
            "maximum_channel_delta": int(delta.max())}


def render_ripple_comparison(scene, state, output, prefix):
    frame = 237
    name = f"{prefix}fixed_rear_water_ripples"
    off_name = f"{prefix}comparison_water_ripples_disabled"
    still(scene, state, output, name, frame)
    for obj in state["ripples"]:
        obj.hide_render = True
    try:
        still(scene, state, output, off_name, frame)
    finally:
        for obj in state["ripples"]:
            obj.hide_render = False
    evidence = rgb_difference(output / f"{name}.png", output / f"{off_name}.png")
    need(evidence["changed_pixels"] > 20, evidence)
    return evidence


def decode(path):
    run("ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-i", str(path), "-f", "null", "-")
    evidence = json.loads(run("ffprobe", "-v", "error", "-count_frames", "-show_streams",
                              "-show_format", "-of", "json", str(path)))
    need(len(evidence["streams"]) == 1, "S6 preview is silent")
    stream = evidence["streams"][0]
    frames = int(stream["nb_read_frames"])
    need((stream["codec_name"], stream["width"], stream["height"], frames) ==
         ("h264", 852, 394, END // (FPS // PREVIEW_RATE)), stream)
    return {"result": "pass_full_ffmpeg_decode", "silent": True, "review_source_px": list(VIEW),
            "encoded_px": [852, 394], "decoded_frames": frames,
            "seconds": float(evidence["format"]["duration"]), "sampling_fps": PREVIEW_RATE}


def save_layout(output, points, changed, state, dynamics):
    feather = state["feather_control"]
    write(output / "s6_layout.json", {
        "id": ASSET, "variant": "S6_Landing", "version": "v001", "status": "needs_review",
        "axes_blender": "+Y forward, +Z up", "gltf_conversion": AXES, "BU_per_game_unit": .036,
        "entry": points[0], "terminal": points[1],
        "reference_ground_z_BU": 0, "reference_water_z_BU": WATER_Z,
        "export_terrain_bounds_xy_BU": [[-20, 20], [0, 40]],
        "entry_open_strip_BU": {"x": [-12, 12], "inside_y": [0, 2], "water_at_boundary": False},
        "module_placement": {"id": "ENV-017", "version": "v001", "translation_BU": points[2]["blender_BU"],
                             "local_shoal_vertex_edits": changed["shoals"],
                             "seam_reed_vertices_removed": changed["seam_reed_vertices_removed"], "world_yaw_degrees": 0},
        "landing_zone_candidate_rect_xy_BU": list(TARGET_RECT),
        "anchors": points,
        "landing_slots": [dict(points[i+3], goose_index=i+1, visual_actor_name=bird.name,
                               animation="Land_ShallowWater" if root["substrate"] == "water" else "Land_Mudflat",
                               start_frame=root["action_start"], contact_frame=root["contact_frame"],
                               rest_frame=root["rest_start"],
                               measured_support_touch_BU=dynamics["contact_positions_BU"][i])
                          for i, (root, bird) in enumerate(state["actors"])],
        "review": {"frames": [1, END], "fps": FPS, "fixed_third_person_source": VIEW, "window": 7.5,
                   "runtime_design_target_seconds": 20,
                   "camera": {"distance_game_units": 180, "pitch_rad": PITCH, "vertical_fov_deg": 50,
                              "look_height_game_units": 6, "leader_body_base_height_game_units": 8, "follows": "goose 1 placed carrier; +Y"},
                   "events_are_preview_only": True},
        "runtime_inputs": {
            "landing": {"animation": {"ANM-007": LAND_FILES[1], "ANM-008": REST_FILES[1]},
                        "controls": ["sessionID", "assignedGooseIDs", "slotInWorld", "substrate",
                                     "approachHeading", "contactSurfaceHeight", "contactEventTimestamp",
                                     "phase", "hasSettled", "actorInCompletionZone"],
                        "responsibilities": ["collision and slot assignment", "participant eligibility and retry",
                                             "landed-only-and-in-zone completion", "input locking after approach commit"]},
            "water": {"asset": f"FX-006/v001/{RIPPLE_FILES[1]}", "control": f"FX-006/v001/{RIPPLE_FILES[2]}",
                      "parameters": ["worldWaterPlane", "waterCoverage", "timeSeconds", "gooseID",
                                     "waterContactPositionWorld", "contactStrength", "contactEventTimestamp"],
                      "default_idle_pigment_gain_multiplier": .40,
                      "contact_reference_plane_Z_BU": WATER_Z, "review_contact_slots": [10,12]},
            "feather_motes": {"asset": f"FX-013/v001/{FEATHER_FILES[1]}", "optional": True,
                              "parameters": ["enabled", "intensity", "allLandingStartFrame",
                                             "sideDriftBUPerSecond", "fallSpeedMultiplier"],
                              "review_all_started_frame": feather["allLandingStartFrame"],
                              "runtime_event": "emit once when all designated geese have begun landing for session",
                              "world_anchor": "S6_BasinOrigin"},
        },
        "texture_mapping": {
            "transport_texture_layers": f"ENV-017/v001/asset_manifest.json#/texture_layers",
            "ripple_textures": f"FX-006/v001/asset_manifest.json#/textures",
            "feather_textures": f"FX-013/v001/asset_manifest.json#/export",
            "goose_skin": "ANM-007/v001/asset_manifest.json#/texture_mapping",
        },
    })


def verify_feather(scene, state, output, prefix):
    control = state["feather_control"]
    starts = int(control["allLandingStartFrame"])
    frame = starts + 40
    # Visibility drivers and per-particle alpha are evaluated in the delivered
    # scene with the upstream effect on, then with the exposed toggle off.
    def visible(f):
        scene.frame_set(f)
        d = bpy.context.evaluated_depsgraph_get()
        return [item for item in state["particles"] if not item.evaluated_get(d).hide_render]
    need(not visible(starts), "particles shown before all have begun landing")
    peak = len(visible(frame))
    need(peak == len(state["particles"]), ("insufficient particle coverage", peak))
    still(scene, state, output, f"{prefix}fixed_rear_feather_motes", frame)
    control["enabled"] = 0
    control.update_tag()
    need(not visible(frame), "optional feather toggle left particles enabled")
    still(scene, state, output, f"{prefix}comparison_feather_disabled", frame)
    control["enabled"] = 1
    control.update_tag()
    need(not visible(starts + 170), "particles remain after the optional cue ends")
    visual = rgb_difference(output / f"{prefix}fixed_rear_feather_motes.png",
                            output / f"{prefix}comparison_feather_disabled.png")
    need(visual["changed_pixels"] > 20, visual)
    return {"result": "pass", "all_participants_have_started_frame": starts,
            "fixed_camera_image_comparison": visual,
            "compared_frame": frame, "peak_visible_cards": peak,
            "visible_with_toggle_off": 0, "visible_before_release_and_after_decay": 0}


def build(output, smoke):
    dependencies = deps()
    export, points, changed = placement()
    layers = terrain(export)
    proof = seam(export, layers)
    need(bpy.ops.export_scene.gltf(filepath=str(output / f"{STEM}.glb"), export_format="GLB",
                                   use_active_scene=True, export_yup=True, export_animations=False,
                                   export_skins=False, export_extras=True) == {"FINISHED"}, "S6 export")
    scene = bpy.data.scenes.new(REVIEW_SCENE)
    base = collection(scene.collection, "S6 | Working layers")
    review_layers = {}
    for key, item in layers.items():
        copy = object_in(base, f"S6_Review_{key}", item.data)
        copy.matrix_world = item.matrix_world.copy()
        review_layers[key] = copy
    state = review(scene, review_layers, native=True)
    graybox(scene, state, output)
    dynamics = stage_proof(scene, state)
    ripples = ripple_proof(scene, state, dynamics)
    still(scene, state, output, "preview_fixed_rear_approach", 51)
    still(scene, state, output, "preview_fixed_rear_leader_wait", 157)
    still(scene, state, output, "preview_fixed_rear_eleven_landed", 211)
    ripples["fixed_camera_image_comparison"] = render_ripple_comparison(scene, state, output, "preview_")
    still(scene, state, output, "preview_fixed_rear_all_landed", 295)
    still(scene, state, output, "preview_fixed_rear_rest", END)
    still(scene, state, output, "preview_top_landing_basin", 295, top=True, samples=24)
    feather = verify_feather(scene, state, output, "preview_")
    save_layout(output, points, changed, state, dynamics)
    scene.camera = state["camera"]
    scene.frame_set(295)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / f"{STEM}.blend"))
    if not smoke:
        encode(scene, state, output)
    write(output / "build_checks.json", {"dependencies": dependencies, "seam": proof,
                                          "simulation": dynamics, "ripple": ripples, "feather": feather})


def same_static(source_doc, level_doc, expected):
    original_images = source_doc[0]
    images, document = level_doc
    need(original_images == images, ("embedded textures differ from ENV-017", original_images, images))
    nodes = {n["name"]: n for n in document["nodes"]}
    for row in expected["anchors"]:
        node = nodes[row["name"]]
        need("mesh" not in node, node)
        need(np.max(np.abs(np.asarray(node.get("translation",[0,0,0])) - row["glb_BU"])) < .00001, row)
    meshes = [node for node in nodes.values() if "mesh" in node]
    need({node["name"] for node in meshes} == {"LandingBasin_Ground", "LandingBasin_Water", "LandingBasin_Reeds"}, meshes)
    needs_blend = {m["name"] for m in source_doc[1]["materials"] if m.get("alphaMode") == "BLEND"}
    actual_blend = {m["name"] for m in document["materials"] if m.get("alphaMode") == "BLEND"}
    need(needs_blend == actual_blend != set(), (needs_blend, actual_blend))
    need(not document.get("animations") and not document.get("skins"), "S6 environment export must leave goose instances to runtime")
    return {"result": "pass", "embedded_textures_sha256": images, "preserved_alpha_blend_materials": sorted(actual_blend),
            "anchor_count": len(expected["anchors"]), "mesh_count": len(meshes)}


def verify(delivery, output, smoke):
    deps()
    glb = delivery / f"{STEM}.glb"
    layout = read(delivery / "s6_layout.json")
    source_doc = texture_bytes(asset("ENV-017", ENV_FILES[1]))
    transport = same_static(source_doc, texture_bytes(glb), layout)
    bpy.ops.wm.open_mainfile(filepath=str(delivery / f"{STEM}.blend"))
    scene = bpy.data.scenes[REVIEW_SCENE]
    active(scene)
    src_layers = {key: scene.objects[f"S6_Review_{key}"] for key in ("Ground", "Water", "Reeds")}
    state = {
        "actors": recovered_actors(scene), "layers": src_layers, "camera": scene.objects["S6_ThirdPersonRig"],
        "overview": scene.objects["S6_TechnicalOverview"],
        "ripples": [scene.objects[n] for n in ("S6_Ripple_10", "S6_Ripple_12")],
        "feather_control": scene.objects["S6_FeatherMotes_Controls"],
        "particles": [o for o in scene.objects if o.name.startswith("FeatherMotes review ")],
    }
    source = stage_proof(scene, state)
    reopened = {"simulation": source, "ripple": ripple_proof(scene, state, source),
                "feather": verify_feather(scene, state, output, "reopen_")}
    reopened["ripple"]["fixed_camera_image_comparison"] = render_ripple_comparison(scene, state, output, "reopen_")
    exported_source_scene = bpy.data.scenes[EXPORT_SCENE]
    reopened["seam"] = seam(exported_source_scene, terrain(exported_source_scene))
    # A blank file prevents any review mesh, material or action from substituting for
    # the actual output GLB or the published upstream GLB clips on the second pass.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = RETURN_SCENE
    scene.render.fps = FPS
    imported(glb)
    returned = terrain(scene)
    seam_cert = seam(scene, returned)
    round_stage = review(scene, returned, native=False)
    after = stage_proof(scene, round_stage)
    revived_ripples = ripple_proof(scene, round_stage, after)
    revived_ripples["fixed_camera_image_comparison"] = render_ripple_comparison(scene, round_stage, output, "roundtrip_")
    deltas = [np.max(np.abs(np.asarray(before) - np.asarray(after["pose_box_samples"][f])))
              for f, before in source["pose_box_samples"].items()]
    need(max(deltas) < .001, ("roundtrip motion pose sample delta", deltas))
    for name, f in (("roundtrip_fixed_rear", 295), ("roundtrip_water_contact", 237), ("roundtrip_fixed_rear_rest", END)):
        still(scene, round_stage, output, name, f)
    still(scene, round_stage, output, "roundtrip_top", 295, top=True)
    video = None if smoke else decode(delivery / "preview_fixed_rear.mp4")
    write(output / "qa.json", {"id": ASSET, "version": "v001", "status": "needs_review",
        "offline_result": "pass" if video else "smoke_without_video",
        "independent_reopened_master": reopened,
        "independent_reimported_glb": {"transport": transport, "seam": seam_cert, "simulation": after,
                                       "ripple": revived_ripples, "pose_sample_aabb_delta_BU": max(deltas),
                                       "source_clips_reimported": ["Land_Mudflat", "Land_ShallowWater", "Rest_Idle"]},
        "video": video, "pending": PENDING,
        "redline_check": {
            "new_scene_ui_or_moral_feedback": False, "red_alert_color": False,
            "biology_claims_added": False, "retention_pressure": False, "new_audio": False,
            "hardware_performance": "待 iPhone / iPad 真机验证",
        },
        "app_graybox_baseline": "goose-preview-model-cleanup.md, iPhone 18 Pro (iOS 27.2), 340 tests, not rerun in asset-only cut",
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--smoke", action="store_true", help="Run asset QA with stills and no full video encode")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    args.output.mkdir(parents=True, exist_ok=True)
    need(not any(args.output.iterdir()), f"Output must be empty: {args.output}")
    if args.verify:
        verify(args.verify.resolve(), args.output.resolve(), args.smoke)
    else:
        build(args.output.resolve(), args.smoke)


if __name__ == "__main__":
    main()
