"""Assemble S4 from four v001 masters and curated ENV-001 joins, and verify the delivered files."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import sys

import bpy
from mathutils import Vector
import numpy as np


BLEND = "LVL-S4_S4_WindFarm.blend"
GLB = "LVL-S4_S4_WindFarm.glb"
LAYOUT = "s4_layout.json"
ROOT = "S4_WindFarm"
CAMERA = "Current Swift rig | fixed rear"
FRAME = (852, 393)
TOP = (945, 1050)
FRAME_RATE = 24
VIDEO_RATE = 8
WARNING_START = 180
LANDING_FRAME = 156
RUN_LENGTH = 144
SOURCE_PARTS = {
    "STR-002": ("STR-002_CurvedFarm_Layout.blend", "STR-002_CurvedFarm_Layout.glb",
                "CurvedFarm_Layout | shared STR-001 meshes", "CurvedFarm_Layout"),
    "ENV-016": ("ENV-016_protected_marsh.blend", "ENV-016_ProtectedMarsh.glb",
                "ProtectedMarsh | three draw layers", "ProtectedMarsh"),
    "FX-010": ("FX-010_RotorFootprint.blend", "FX-010_RotorFootprint.glb",
               "FX-010 | RotorFootprint", "RotorFootprint"),
    "FX-011": ("FX-011_TurbineWarn.blend", "FX-011_TurbineWarn.glb",
               "FX-011 | TurbineWarn", "TurbineWarn"),
}
SHEET = "preview_fixed_rear_bypass.mp4"
PROBE = "preview_fixed_rear_silent_warning.mp4"
ACTION_NAME = "STR-002 | S4 farm and marsh review"
FINAL_NAMES = {ACTION_NAME: "Farm_Rotor_Loop"}


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def read(path):
    return json.loads(path.read_text())


def check(condition, detail):
    if not condition:
        raise ValueError(detail)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metadata(path):
    return {"sha256": digest(path), "bytes": path.stat().st_size}


def asset_dir(library, asset):
    return library / asset / "v001"


def dependency_inputs(library):
    result = {}
    for asset, (master, export, _, _) in SOURCE_PARTS.items():
        folder = asset_dir(library, asset)
        manifest = read(folder / "asset_manifest.json")
        paths = [master, export, "README.md", "asset_manifest.json", "qa.json"]
        paths += {"STR-002": ["farm_layout.json"], "FX-011": ["warning_review.json"]}.get(asset, [])
        for name in paths:
            path = folder / name
            stored = manifest.get("files", {}).get(name)
            actual = metadata(path)
            if stored:
                expected = stored if isinstance(stored, str) else stored["sha256"]
                check(actual["sha256"] == expected, ("Dependency hash", asset, name, expected, actual))
            result[str(path.relative_to(library))] = actual
    for asset, names in {
        "STR-001": ["STR-001_generate.py"],
        "STR-002": ["STR-002_generate.py"],
        "ENV-001": ["ENV-001_terrain.blend", "asset_manifest.json", "ENV-001_generate.py"],
        "ENV-002": ["qa.json", "ENV-002_generate.py"],
        "ENV-003": ["ENV-003_generate.py"],
        "ENV-004": ["ENV-004_generate.py"],
        "ENV-005": ["ENV-005_generate.py"],
        "ENV-007": ["ENV-007_generate.py"],
        "ENV-010": ["ENV-010_generate.py"],
        "ENV-014": ["ENV-014_generate.py"],
        "ENV-016": ["ENV-016_generate.py"],
        "ENV-018": ["ENV-018_atmosphere_cards.blend", "ENV-018_generate.py"],
        "FX-010": ["FX-010_generate.py"],
        "FX-011": ["FX-011_generate.py"],
        "CHR-001": ["CHR-001_goose_rig.blend"],
        "ANM-007": ["ANM-007_landing.blend"],
    }.items():
        for name in names:
            path = asset_dir(library, asset) / name
            result[str(path.relative_to(library))] = metadata(path)
    return result


def load_glb(path):
    blob = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", blob)
    check((magic, version, length) == (b"glTF", 2, len(blob)), path)
    json_size, tag = struct.unpack_from("<I4s", blob, 12)
    check(tag == b"JSON", path)
    doc = json.loads(blob[20:20 + json_size])
    bin_size, tag = struct.unpack_from("<I4s", blob, 20 + json_size)
    binary = blob[28 + json_size:]
    check(tag == b"BIN\0" and len(binary) == bin_size, path)
    return doc, binary


def save_glb(path, doc, binary):
    js = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    binary = bytes(binary) + b"\0" * (-len(binary) % 4)
    path.write_bytes(struct.pack("<4sIII4s", b"glTF", 2, 28 + len(js) + len(binary), len(js), b"JSON")
                     + js + struct.pack("<I4s", len(binary), b"BIN\0") + binary)


def names_of_roots(document):
    scene = document["scenes"][document.get("scene", 0)]
    return [document["nodes"][idx]["name"] for idx in scene.get("nodes", [])]


def imported_textures(doc, data):
    result = Counter()
    for image in doc.get("images", []):
        view = doc["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        result[hashlib.sha256(data[start:start + view["byteLength"]]).hexdigest()] += 1
    return result


def merge_glbs(parts, output):
    """Copy packed buffers and remap only the known index references of these v001 exports."""
    arrays = ("nodes", "meshes", "materials", "textures", "images", "samplers", "accessors", "bufferViews")
    merged = {key: [] for key in arrays}
    merged.update(asset={"version": "2.0", "generator": "Feather & Tide S4 Blender asset assembly"},
                  scene=0, animations=[], scenes=[{"name": ROOT, "nodes": [0]}])
    root_node = {"name": ROOT, "children": [], "extras": {"asset_id": "LVL-S4", "collision_enabled": False,
                 "zone_authority": "Game Zone", "visuals_only": True}}
    merged["nodes"].append(root_node)
    buffer = bytearray()
    extensions = set()
    for path in parts:
        source, data = load_glb(path)
        check(len(source["buffers"]) == 1 and "uri" not in source["buffers"][0], path)
        supported = set(arrays) | {"asset", "scene", "scenes", "buffers", "animations", "extensionsUsed"}
        check(set(source).issubset(supported), ("Unsupported GLB field", path, set(source) - supported))
        extensions.update(source.get("extensionsUsed", []))
        check(extensions.issubset({"KHR_materials_specular"}), extensions)
        offsets = {key: len(merged[key]) for key in arrays}
        doc = deepcopy(source)

        def ref(node, prop, key):
            if prop in node:
                node[prop] += offsets[key]

        src_scene = doc["scenes"][doc.get("scene", 0)]
        root_node["children"].extend(index + offsets["nodes"] for index in src_scene.get("nodes", []))
        for node in doc["nodes"]:
            ref(node, "mesh", "meshes")
            if "children" in node:
                node["children"] = [i + offsets["nodes"] for i in node["children"]]
        for mesh in doc["meshes"]:
            for primitive in mesh["primitives"]:
                ref(primitive, "indices", "accessors")
                ref(primitive, "material", "materials")
                for attributes in (primitive["attributes"], *primitive.get("targets", [])):
                    for attr in attributes:
                        ref(attributes, attr, "accessors")
        for material in doc["materials"]:
            for section in (material, material.get("pbrMetallicRoughness", {}), *material.get("extensions", {}).values()):
                for label, section_part in section.items():
                    if label.lower().endswith("texture"):
                        ref(section_part, "index", "textures")
        for texture in doc.get("textures", []):
            ref(texture, "source", "images")
            ref(texture, "sampler", "samplers")
        for image in doc.get("images", []):
            ref(image, "bufferView", "bufferViews")
        for accessor in doc["accessors"]:
            ref(accessor, "bufferView", "bufferViews")
            if "sparse" in accessor:
                ref(accessor["sparse"]["indices"], "bufferView", "bufferViews")
                ref(accessor["sparse"]["values"], "bufferView", "bufferViews")
        for view in doc["bufferViews"]:
            check(view["buffer"] == 0, path)
            view["byteOffset"] = len(buffer) + view.get("byteOffset", 0)
        buffer.extend(data)
        buffer.extend(b"\0" * (-len(buffer) % 4))
        for clip in doc.get("animations", []):
            clip["name"] = FINAL_NAMES.get(clip["name"], clip["name"])
            for channel in clip["channels"]:
                ref(channel["target"], "node", "nodes")
            for sampler in clip["samplers"]:
                ref(sampler, "input", "accessors")
                ref(sampler, "output", "accessors")
            merged["animations"].append(clip)
        for key in arrays:
            merged[key].extend(doc.get(key, []))
    merged["extensionsUsed"] = sorted(extensions)
    merged["buffers"] = [{"byteLength": len(buffer)}]
    save_glb(output, merged, buffer)


def append_group(scene, filename, collection):
    with bpy.data.libraries.load(str(filename), link=False) as (source, target):
        check(collection in source.collections, (filename, collection))
        target.collections = [collection]
    group, = target.collections
    scene.collection.children.link(group)
    group.hide_render = False
    group.hide_viewport = False
    return group


def initialize(library):
    helper = runpy.run_path(str(asset_dir(library, "FX-011") / "FX-011_generate.py"))
    bundle = helper["initialize"](library, asset_dir(library, "FX-011") / "warning_review.json")
    return helper, bundle


def disk_placement(layout, warning, proof):
    route = deepcopy(layout["review_route"])
    return {
        "id": "LVL-S4", "version": "v001", "variant": ROOT, "status": "needs_review",
        "coordinate_system": {"Blender": "+X right, +Y travel, +Z up", "glTF": "(x,z,-y)",
                              "BU_per_game_unit": layout["BU_per_game_unit"],
                              "alignment": "0.9900 BU CHR-001 beak-to-tail = 27.5 game units"},
        "alignment_to_graybox": layout["anchor"], "static_scene_origin_BU": [0, 0, 0],
        "sweep_geometry_source": "../../STR-002/v001/farm_layout.json",
        "offline_sweep_candidate": {"rule": "Union of inclusive discs traced by FX-010",
                                    "radius_BU": layout["sweep"]["radius_game_units"] * layout["BU_per_game_unit"],
                                    "instances": layout["instances"], "accepted_tolerance_BU": .005},
        "outer_lane_and_marsh": {**route, "rest_pose_by_slot": proof["slots"]},
        "game_inputs": {
            "zone_authority": "Game Zone",
            "warning": "Feed position, heading, authored approach event, contact point on exposed Zone boundary and reset.",
            "placement": warning["engine_contract"],
            "playable_section_target_seconds": 50,
            "wetland": "Game Zone controls accessibility, touchdown, replenish effect, stay duration and egress.",
            "no_authored_runtime_colliders": True,
        },
        "review_timeline": {"fps": 24, "bypass": [0, RUN_LENGTH], "rest": LANDING_FRAME,
                            "warning_start_offset": WARNING_START, "warning": warning["review_only_timing"],
                            "camera": "A fixed trailing 180 game units, pitch input 0.48 rad; vertical FOV 50°, look 6 above lift",
                            "bypass_camera_note": "The tight follow frame progressively crops the wide V; the map shows the whole formation."},
    }


def context_with_apron(scene, library, helper_data, parts):
    single, farm, env, fog, layout, discs, *_ = helper_data
    base = env["B"]
    group = single["collection_in"](scene, "Review | CHR-001 formation and ANM-007 landing")
    ground = single["collection_in"](scene, "Review | ENV-001 scenery continuation")
    flat = farm["load_objects"](asset_dir(library, "ENV-001") / "ENV-001_terrain.blend",
                                ["Flat"], ground)["Flat"]
    actual_stitches = {tuple(round(v) for v in o.location.xy) for o in bpy.data.objects
                       if o.parent and o.parent.name == "MarshStitch"}
    for x in range(-90, 111, 10):
        for y in range(-70, 181, 10):
            if (x in env["COLS"] and y in env["ROWS"]) or (x, y) in actual_stitches:
                continue
            base["obj"](ground, f"Terrain {x},{y}", flat.data, (x, y, 0))
    bpy.data.objects.remove(flat, do_unlink=True)

    layers = [bpy.data.objects[n] for n in farm["WET"][1:]]
    check(all(o.parent == parts["ENV-016"][0] for o in layers), "Actual marsh layers")
    bird = base["add_goose"](group)
    bird.hide_render = True
    bird.hide_set(True)
    flight = [base["obj"](group, f"V flight | {i + 1:02}", bird.data) for i in range(12)]
    resting, landing = env["BASELINE"]["populate_flock"](group, layers[0])
    studio = base["studio"](scene, scene.collection)
    sky = scene.world.node_tree.nodes.get("Background")
    sky.inputs["Color"].default_value = (.68, .74, .75, 1)
    sky.inputs["Strength"].default_value = .59
    markers = farm["route_geometry"](scene, base, env, layout, layers)
    atmosphere = single["collection_in"](scene, "Review | ENV-018 atmosphere")
    cards = farm["load_objects"](asset_dir(library, "ENV-018") / "ENV-018_atmosphere_cards.blend",
                                 fog["NAMES"], atmosphere)
    fog_rows = fog["stage_cards"](atmosphere, cards, layout["review_atmosphere"]["cards"])
    for obj in cards.values():
        bpy.data.objects.remove(obj, do_unlink=True)
    masks = {}
    for kind, item, _, _ in fog_rows:
        image = next(n.image for n in item.data.materials[0].node_tree.nodes if n.type == "TEX_IMAGE")
        pixels = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(pixels)
        masks[kind] = pixels.reshape(image.size[1], image.size[0], 4)[:, :, 3]
    cam = base["camera"](studio, CAMERA, (0, 0, 1), (0, 1, 0))
    x0, x1, y0, y1 = layout["review_route"]["top_camera_bounds_BU"]
    center = ((x0 + x1) / 2, (y0 + y1) / 2)
    top = base["camera"](studio, "Technical plan | full formation",
                         (*center, 110), (*center, 0), x1 - x0)
    return {"pads": (group, ground), "layers": layers, "bird": bird, "flight": flight,
            "resting": resting, "landing": landing, "cam": cam, "top": top,
            "fog_rows": fog_rows, "masks": masks, "studio": studio, "markers": markers}


def adopt_import_groups(scene, glb_path=None, library=None):
    parts = {}
    if glb_path:
        bpy.ops.import_scene.gltf(filepath=str(glb_path))
        for identifier, (_, _, _, root_name) in SOURCE_PARTS.items():
            root_obj = bpy.data.objects[root_name]
            parts[identifier] = [root_obj, *root_obj.children_recursive]
        return parts

    for identifier, (filename, _, collection, root_name) in SOURCE_PARTS.items():
        group = append_group(scene, asset_dir(library, identifier) / filename, collection)
        root_obj = group.objects[root_name]
        parts[identifier] = [root_obj, *root_obj.children_recursive]
        check(set(parts[identifier]) == set(group.all_objects), (identifier, "Unexpected master group membership"))
    return parts


def turn_on_master_motion(objects):
    for obj in objects:
        if not obj.animation_data:
            continue
        for track in obj.animation_data.nla_tracks:
            track.mute = True


def set_asset_links(scene, parts):
    root = bpy.data.objects.new(ROOT, None)
    scene.collection.objects.link(root)
    root["asset_id"] = "LVL-S4"
    root["asset_version"] = "v001"
    root["zone_authority"] = "Game Zone"
    root["collision_enabled"] = False
    for identifier, (obj, *_) in parts.items():
        check(obj.parent is None, (obj.name, "unexpected master parent"))
        obj.parent = root
        obj["source_asset"] = identifier + "/v001"
        obj["collision_enabled"] = False
    marsh = parts["ENV-016"][0]
    marsh["rest_patch"] = "Terrain and standing review slots aligned at the protected marsh root."
    bpy.context.view_layer.update()
    return root


def merge_stitch_tiles(scene, stage, output, assembly):
    """Retain the matched approach and exit rows and eastern turbine-bank joins."""
    group = bpy.data.collections.new("LVL-S4 | Exported ENV-001 seam continuations")
    scene.collection.children.link(group)
    root = bpy.data.objects.new("MarshStitch", None)
    group.objects.link(root)
    root["source_asset"] = "ENV-001/v001 Flat"
    root["collision_enabled"] = False
    chosen = []
    for tile in list(stage["pads"][1].objects):
        x, y = (int(round(c)) for c in tile.location.xy)
        is_gate = x in (-20, -10, 0, 10) and y in (-40, -30, 30, 40)
        is_farm = x == 20 and y in (-20, -10, 0, 10, 20, 30)
        if is_gate or is_farm:
            group.objects.link(tile)
            stage["pads"][1].objects.unlink(tile)
            tile.parent = root
            chosen.append(tile)
    check(len(chosen) == 22, [tile.name for tile in chosen])
    bpy.ops.object.select_all(action="DESELECT")
    for obj in (root, *chosen):
        obj.select_set(True)
    result = bpy.ops.export_scene.gltf(filepath=str(output), use_selection=True,
                                        export_extras=True, export_yup=True, export_animations=False)
    check(result == {"FINISHED"}, result)
    root.parent = assembly
    bpy.context.view_layer.update()
    return group


def bind_warning(warn, scene, offset):
    helper, _, _, data = warn
    limits = data["review_only_timing"]
    for name, clip, role in (("ApproachEdge", "ApproachCue", "approach_event_frame"),
                             ("ContactPressure", "BoundaryContact", "edge_contact_event_frame")):
        obj = bpy.data.objects[name]
        anim = helper["imported_anim"](obj, clip)
        helper["place_in_timeline"](anim, clip, offset + limits[role])
    scene.frame_set(0)


def initialize_reused_loops(parts, library, imported):
    fx = runpy.run_path(str(asset_dir(library, "FX-010") / "FX-010_generate.py"))
    for asset in ("STR-002", "FX-010"):
        for item in parts[asset]:
            if imported:
                fx["use_imported_actions"](item)
            else:
                turn_on_master_motion([item])


def exact_follow(base, camera, leader, heading, lift):
    base["follow"](camera, leader, heading)
    camera.location.z += lift


def state_for(scene_frame, stage, warn):
    helper, _, upstream, warning = warn
    _, farm, _, _, layout, *_ = upstream
    route = layout["review_route"]
    begin, end = route["extent_y_BU"]
    neutral = farm["slot_offsets"](36 * layout["BU_per_game_unit"])
    scale = layout["BU_per_game_unit"]
    overflight_lift = route["overflight_lift_game_units"]
    warning_mode = scene_frame >= WARNING_START
    standing_mode = LANDING_FRAME <= scene_frame < WARNING_START
    if warning_mode:
        touch, *_ = helper["placement"](upstream, warning)
        timings = warning["review_only_timing"]
        p = scene_frame - WARNING_START
        x = touch.x
        y = touch.y + (p - timings["edge_contact_event_frame"]) * timings["review_ground_speed_BU_per_second"] / FRAME_RATE
        heading = Vector((0, 1))
        lift = overflight_lift
    elif standing_mode:
        x, y = tuple(stage["resting"][0].location.xy)
        heading = Vector((0, 1))
        lift = 0.
    else:
        p = min(scene_frame / RUN_LENGTH, 1.)
        x, y = route["leader_x_BU"], begin + p * (end - begin)
        yaw = .28 * max(0.0, 1.0 - p * 5.0)
        heading = Vector((math.sin(yaw), math.cos(yaw)))
        # The route descends after the establishing view and climbs clear of the far gate.
        lift = overflight_lift * max(0., 1. - p * 3., (p - .68) / .32)
    return {"x": x, "y": y, "heading": heading, "lift_BU": lift * scale, "scale": scale,
            "offsets": neutral, "rest": standing_mode, "warning": warning_mode}


def apply_state(scene, stage, warn, frame, fog_amount=1.0, add_keys=False, top_pose=None):
    _, _, upstream, _ = warn
    _, _, env, fog, layout, *_ = upstream
    base = env["B"]
    scene.frame_set(int(frame), subframe=frame % 1)
    info = state_for(frame, stage, warn)
    if top_pose is not None:
        info.update(x=layout["review_route"]["leader_x_BU"], y=top_pose, lift_BU=0, rest=False, warning=False)
    exact_follow(base, stage["cam"], (info["x"], info["y"]), info["heading"], info["lift_BU"])
    for i, (bird, off) in enumerate(zip(stage["flight"], info["offsets"])):
        bird.location = (info["x"] + off.x, info["y"] + off.y,
                         (8 if i == 0 else 6) * info["scale"] + info["lift_BU"])
        bird.hide_render = info["rest"] or (i > 0 and info["warning"])
        if add_keys:
            bird.keyframe_insert("location", frame=frame)
            bird.keyframe_insert("hide_render", frame=frame)
    for bird in stage["resting"]:
        bird.hide_render = not info["rest"]
        if add_keys:
            bird.keyframe_insert("hide_render", frame=frame)
    phase = frame / (FRAME_RATE * layout["review_atmosphere"]["drift_period_seconds"])
    fog["accessibility"](stage["fog_rows"], fog_amount)
    fog["position_cards"](stage["fog_rows"], phase, fog_amount)
    if add_keys:
        for prop in ("location", "rotation_euler"):
            stage["cam"].keyframe_insert(prop, frame=frame)
        for _, item, _, _ in stage["fog_rows"]:
            item.keyframe_insert("location", frame=frame)
    bpy.context.view_layer.update()
    return info


def terrain_and_sweep(scene, warn, stage):
    _, fx, upstream, _ = warn
    single, farm, env, _fog, layout, _discs, _arcs, _points, _, swift = upstream
    actual = {spec["id"]: bpy.data.objects[spec["id"]].matrix_world.translation
              for spec in layout["instances"]}
    placement_error = max((actual[row["id"]] - Vector(row["center_BU"])).length for row in layout["instances"])
    check(placement_error < 3e-6, placement_error)
    discs = farm["circles"](layout, actual)
    arcs = farm["exposed_arcs"](discs)
    poles, join_delta = farm["polygon_from_arcs"](
        arcs, math.radians(layout["sweep"]["render_subdivision_max_angle_degrees"]))
    mesh = bpy.data.objects["SweepSurface"]
    shape = fx["surface_checks"](mesh, poles, arcs, discs, layout, single)
    route = farm["layout_proof"](layout, discs, stage["bird"], stage["layers"], stage["resting"], swift, check)
    terrain = farm["foliage_and_flight"](stage, stage["markers"], env, swift)
    leaves = [o for o in bpy.data.objects if o.parent and o.parent.name == "MarshStitch" and o.type == "MESH"]
    exposed_tiles = {tuple(round(v) for v in o.location.xy) for o in leaves}
    required_tiles = {(x, y) for x in (-20, -10, 0, 10) for y in (-40, -30, 30, 40)}
    check(len(leaves) == 22 and exposed_tiles.issuperset(required_tiles), exposed_tiles)
    check(len({o.data for o in leaves}) == 1, "Stitch tiles must share the Flat mesh")
    joins = env["check_crossings"](stage["layers"][0].data,
                                 [tile for tile in leaves if round(tile.location.x) in (-10, 0, 10)])
    terrain["filed_join_geometry"] = joins
    return {"max_review_instance_center_error_BU": placement_error, "continuous_FX010_surface": shape,
            "outer_boundary_chain_max_join_gap_BU": join_delta, "formation_and_wetland": route,
            "ground_clearance_egress_and_landing": terrain, "seam_tile_mesh_instances": len(leaves)}


def camera_proof(scene, stage, warn, frames, check_keyframes=False):
    cam = stage["cam"]
    check(cam.data.type == "PERSP" and cam.data.sensor_fit == "VERTICAL", cam.name)
    fov = math.degrees(2 * math.atan(cam.data.sensor_height / (2 * cam.data.lens)))
    check(abs(fov - 50.) < 1e-5, fov)
    if check_keyframes:
        check(scene.camera == cam and len([o for o in scene.objects if o.type == "CAMERA"]) == 2 and
              not any(m.camera for m in scene.timeline_markers), "Camera follows without cuts to technical top")
    max_error = 0.
    min_direction_dot = 1.
    for frame in frames:
        if check_keyframes:
            scene.frame_set(frame)
            info = state_for(frame, stage, warn)
        else:
            info = apply_state(scene, stage, warn, frame)
        factor = info["scale"]
        heading = info["heading"]
        back = 180 * math.cos(.48) * factor
        expected = Vector((info["x"] - heading.x * back, info["y"] - heading.y * back,
                           180 * math.sin(.48) * factor + info["lift_BU"]))
        target = Vector((info["x"], info["y"], 6 * factor + info["lift_BU"]))
        direction = cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))
        max_error = max(max_error, (cam.location - expected).length)
        min_direction_dot = min(min_direction_dot, direction.dot((target - expected).normalized()))
    check(max_error < 1e-5 and min_direction_dot > .99999, (max_error, min_direction_dot))
    return {"verified_source_samples": len(frames), "max_camera_position_error_BU": max_error,
            "minimum_direction_dot_to_Swift_target": min_direction_dot, "field_of_view_degrees": fov,
            "camera_distance_input_game_units": 180, "pitch_input_radians": .48,
            "target_height_above_lift_game_units": 6, "technical_top_is_separate_review": True}


def warning_proof(scene, warn, offset):
    helper, fx, upstream, warning = warn
    edge, wave = (bpy.data.objects[n] for n in ("ApproachEdge", "ContactPressure"))
    times = warning["review_only_timing"]
    _, _, _, _, layout, discs, arcs, *_ = upstream
    touch, *_ = helper["placement"](upstream, warning)
    check(all(ob.parent.name == "TurbineWarn" and ob["collision_enabled"] is False for ob in (edge, wave)),
          "Warning transforms and physics ownership")
    measurements = {edge.name: [], wave.name: []}
    inside_count = []
    maximum_outside = float("-inf")
    axis_error = 0.0
    frames = np.linspace(0, times["review_end_frame_exclusive"], 2 * times["review_end_frame_exclusive"] + 1)
    for frame in frames:
        scene.frame_set(offset + int(frame), subframe=frame % 1)
        y = touch.y + (frame - times["edge_contact_event_frame"]) * times["review_ground_speed_BU_per_second"] / FRAME_RATE
        inside_count.append(any(math.hypot(touch.x - center.x, y - center.y) <= r + 2e-6 for _, center, r in discs))
        for obj in (edge, wave):
            points = helper["vertices_of"](obj)
            area = helper["area_of_band"](obj, points)
            measurements[obj.name].append(area)
            maximum_outside = max(maximum_outside, max(min(math.hypot(v.x - c.x, v.y - c.y) - r
                                                       for _, c, r in discs) for v in points))
            if frame == 28 and obj == edge:
                boundary = helper["edge_vertices"](obj, points)
                axis_error = float(max(fx["arc_distance"](np.array([p.x for p in boundary]),
                                                          np.array([p.y for p in boundary]), arcs)))
    contact = times["edge_contact_event_frame"]
    approach = times["approach_event_frame"]
    check(not any(inside_count[:contact * 2]) and all(inside_count[contact * 2:]), "Analytic first contact")
    check((contact - approach) / FRAME_RATE == 3.0, (approach, contact))
    visible = {}
    for obj, start, end in ((edge, approach, contact), (wave, contact, contact + 26)):
        values = measurements[obj.name]
        runs = sum(value > 1e-5 and (i == 0 or values[i-1] <= 1e-5) for i, value in enumerate(values))
        transmitted = [float(f) for f, v in zip(frames, values) if v > 1e-5]
        check(runs == 1 and min(transmitted) > start and max(transmitted) < end, (obj.name, runs, transmitted))
        visible[obj.name] = {"positive_area_intervals": runs, "first_last_frames": [min(transmitted), max(transmitted)],
                             "peak_planar_area_BU2": max(values)}
    check(maximum_outside < .005 and axis_error < .0002, (maximum_outside, axis_error))
    for frame in (0, 72, 143, LANDING_FRAME):
        if offset == WARNING_START:
            scene.frame_set(frame)
            check(all(helper["area_of_band"](obj, helper["vertices_of"](obj)) < 1e-5
                      for obj in (edge, wave)), "Cue must be closed in exterior and at rest")
    return {"samples_at_half_frames": len(frames), "authored_lead_seconds": float((contact - approach) / FRAME_RATE),
            "candidate_first_contact_relative_frame": float(frames[inside_count.index(True)]),
            "approach_edge_axis_error_BU": axis_error, "maximum_warning_point_outside_union_BU": max(0., maximum_outside),
            "one_shot_morphs": visible, "candidate_only": True}


def pack_and_save(scene, stage, warn, destination):
    frames = [*range(0, RUN_LENGTH + 1), LANDING_FRAME - 1, *range(LANDING_FRAME, WARNING_START + 120)]
    for frame in frames:
        apply_state(scene, stage, warn, frame, add_keys=True)
    for obj in (stage["cam"], *stage["flight"], *stage["resting"], *(o for _, o, _, _ in stage["fog_rows"])):
        anim = obj.animation_data
        for curve in anim.action.layers[0].strips[0].channelbag(anim.action_slot).fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "CONSTANT" if curve.data_path == "hide_render" else "LINEAR"
    for frame, label in ((0, "Exterior approach"), (32, "Wetland entry"),
                         (114, "Wetland exit"), (LANDING_FRAME, "Standing landing check"),
                         (WARNING_START, "Independent warning probe"),
                         (WARNING_START + 12, "Edge cue"),
                         (WARNING_START + 84, "Candidate contact"),
                         (WARNING_START + 110, "Cue reset")):
        scene.timeline_markers.new(label, frame=frame)
    scene["review_camera"] = "Fixed trailing Swift rig across offline review poses"
    scene["app_integration"] = "Pending; runtime collisions and triggers use Game Zone"
    scene.frame_set(0)
    scene.camera = stage["cam"]
    scene.render.resolution_x, scene.render.resolution_y = FRAME
    scene.render.filepath = "//preview_fixed_rear_approach.png"
    scene.frame_start, scene.frame_end = 0, WARNING_START + 119
    stage["top"].hide_set(True)
    warn[2][2]["B"]["set_preview_workspace"](scene, stage["cam"])
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(destination))


def compare_rgb(path_a, path_b, fetch_rgb, minimum_delta):
    source = fetch_rgb(path_a)
    target = fetch_rgb(path_b)
    difference = np.max(abs(source - target), axis=2)
    return {"pixels_at_least_delta": int(np.count_nonzero(difference >= minimum_delta / 255)),
            "difference_threshold_8bit": minimum_delta,
            "mean_absolute_RGB_8bit": float(np.abs(source - target).mean() * 255)}


def render_proofs(scene, stage, warn, output, mode):
    _, fx, upstream, warning = warn
    single, farm, env, fog, layout, discs, *_ = upstream
    base = env["B"]
    quick = mode == "quick"
    quality = 8 if quick else 13
    edge = bpy.data.objects["ApproachEdge"]
    surface = bpy.data.objects["SweepSurface"]
    if mode == "source" or quick:
        groups = [bpy.data.collections[SOURCE_PARTS[a][2]] for a in ("STR-002", "ENV-016")]
        stitch = bpy.data.collections["LVL-S4 | Exported ENV-001 seam continuations"]
        swaps = farm["gray_layers"]([*groups, *stage["pads"], stitch], base)
        gray = base["paint"]("Graybox | continuous soft violet", "7A737F")
        gray.diffuse_color[3] = .5
        gray.node_tree.nodes.get("Principled BSDF").inputs["Alpha"].default_value = .5
        original = surface.data.materials[0]
        surface.data.materials[0] = gray
        pressure = [o for o in surface.parent.children if o != surface]
        for ob in pressure:
            ob.hide_render = True
        apply_state(scene, stage, warn, 10, fog_amount=0.)
        base["render"](scene, stage["cam"], output, "graybox_fixed_rear", FRAME, 8)
        apply_state(scene, stage, warn, 74, fog_amount=0., top_pose=11.)
        base["render"](scene, stage["top"], output, "graybox_top", TOP, 8)
        apply_state(scene, stage, warn, LANDING_FRAME, fog_amount=0.)
        base["render"](scene, stage["cam"], output, "graybox_wetland_landing", FRAME, 8)
        for item, old in swaps:
            item.data = old
        surface.data.materials[0] = original
        for ob in pressure:
            ob.hide_render = False
    prefix = "roundtrip_" if mode == "verify" else "preview_"
    apply_state(scene, stage, warn, 10)
    base["render"](scene, stage["cam"], output, prefix + "fixed_rear_approach", FRAME, quality)
    apply_state(scene, stage, warn, 74, top_pose=11.)
    base["render"](scene, stage["top"], output, prefix + "full_v_top", TOP, quality)
    apply_state(scene, stage, warn, LANDING_FRAME)
    base["render"](scene, stage["cam"], output, prefix + "wetland_landing", FRAME, quality)
    apply_state(scene, stage, warn, WARNING_START + 28)
    base["render"](scene, stage["cam"], output, prefix + "warning_edge", FRAME, quality)
    apply_state(scene, stage, warn, WARNING_START + 98)
    base["render"](scene, stage["cam"], output, prefix + "contact_wave", FRAME, quality)
    if mode == "verify":
        return {}
    apply_state(scene, stage, warn, 130)
    base["render"](scene, stage["cam"], output, "preview_fixed_rear_egress", FRAME, quality)
    apply_state(scene, stage, warn, WARNING_START + 28)
    edge.hide_render = True
    base["render"](scene, stage["cam"], output, "comparison_warning_idle", FRAME, quality)
    edge.hide_render = False
    comparison = compare_rgb(output / "preview_warning_edge.png", output / "comparison_warning_idle.png",
                             fx["image_rgb"], 12)
    check(comparison["pixels_at_least_delta"] > 80, comparison)
    return comparison


def rotor_phase_checks(scene, warn):
    _, fx, upstream, _ = warn
    single, _, _, _, layout, discs, *_ = upstream
    period = round(single["PERIOD"] * single["FPS"])
    rotors = {row["id"]: bpy.data.objects[row["id"] + "_Rotor"] for row in layout["instances"]}
    samples = {name: [] for name in rotors}
    reference = Vector((0, 0, 1))
    blade_margin = {}
    for row in layout["instances"]:
        tag = row["id"]
        rotor = rotors[tag]
        local_radius = max(math.hypot(math.hypot((blade.matrix_basis @ v.co).x, (blade.matrix_basis @ v.co).z),
                                      rotor.location.y + (blade.matrix_basis @ v.co).y) * row["scale"]
                           for blade in rotor.children if "_Blade_" in blade.name for v in blade.data.vertices)
        blade_margin[tag] = discs[0][2] - local_radius
    check(min(blade_margin.values()) > .005, blade_margin)
    phase_error = 0.0
    for step in range(0, period * 2 + 1):
        frame = step * .5
        scene.frame_set(int(frame), subframe=frame % 1)
        for row in layout["instances"]:
            name = row["id"]
            position = rotors[name].matrix_basis.to_quaternion() @ reference
            theta = math.atan2(position.x, position.z)
            phase = math.radians(row["rotor_phase_deg"]) + frame * math.tau / period
            phase_error = max(phase_error, abs(math.remainder(theta - phase, math.tau)))
            samples[name].append(position)
    seam = max((v[0] - v[-1]).length for v in samples.values())
    step = min(math.atan2(a.cross(b).y, a.dot(b)) for row in samples.values() for a, b in zip(row, row[1:]))
    check(phase_error < .0003 and seam < 1e-5 and step > 0, (phase_error, seam, step))
    pressure = fx["motion_checks"](scene, layout, discs, single)
    return {"rotor_count": len(rotors), "rotor_period_seconds": single["PERIOD"],
            "half_frame_samples_per_rotor": period * 2 + 1, "worst_rotor_phase_error_radians": phase_error,
            "largest_loop_end_delta": seam, "minimum_blade_to_candidate_sweep_margin_BU": min(blade_margin.values()),
            "FX010_pressure_phase": pressure}


def readback_transport(library, glb_path):
    expected = Counter()
    for asset, (_, name, _, _) in SOURCE_PARTS.items():
        doc, blob = load_glb(asset_dir(library, asset) / name)
        expected.update(imported_textures(doc, blob))
    doc, binary = load_glb(glb_path)
    actual = imported_textures(doc, binary)
    stitches = actual - expected
    check(not (expected - actual) and sum(stitches.values()) == 1, ("Packed PNG bytes changed", stitches))
    flat = next(n for n in doc["nodes"] if n["name"] == "Terrain -20,-30")
    flat_material = doc["materials"][doc["meshes"][flat["mesh"]]["primitives"][0]["material"]]
    flat_texture = doc["textures"][flat_material["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
    flat_image = doc["images"][flat_texture["source"]]
    flat_view = doc["bufferViews"][flat_image["bufferView"]]
    start = flat_view.get("byteOffset", 0)
    flat_hash = hashlib.sha256(binary[start:start + flat_view["byteLength"]]).hexdigest()
    env_manifest = read(asset_dir(library, "ENV-001") / "asset_manifest.json")
    expected_stitch_hash = env_manifest["textures"]["GrassFlat"]["sha256"]
    check(flat_hash in stitches and flat_hash == expected_stitch_hash, ("ENV-001 stitch texture binding", flat_hash))
    check(names_of_roots(doc) == [ROOT], "GLB scene root")
    nodes = doc["nodes"]
    root = next(n for n in nodes if n["name"] == ROOT)
    roots = {nodes[idx]["name"] for idx in root["children"]}
    check(roots == {entry[3] for entry in SOURCE_PARTS.values()} | {"MarshStitch"}, roots)
    check(not doc.get("cameras") and not doc.get("skins"), "Review witnesses entered the export")
    check(not any(n["name"].startswith(("Review", "V flight")) for n in nodes), "Review witnesses entered GLB")
    contract = {
        "Farm_Rotor_Loop": ("rotation", 9., {f"T{i:02}_Rotor" for i in range(1, 8)}),
        "RotorPressureLoop": ("translation", 9., {f"Pressure_T{i:02}" for i in range(1, 8)}),
        "ApproachCue": ("weights", 3., {"ApproachEdge"}),
        "BoundaryContact": ("weights", 26 / 24, {"ContactPressure"}),
    }
    check({a["name"] for a in doc["animations"]} == set(contract), "GLB clip set")
    for clip in doc["animations"]:
        path, duration, names = contract[clip["name"]]
        targets = [c["target"] for c in clip["channels"]]
        check(len(targets) == len(names) and {nodes[t["node"]]["name"] for t in targets} == names and
              all(t["path"] == path for t in targets), (clip["name"], targets))
        for channel in clip["channels"]:
            timeline = doc["accessors"][clip["samplers"][channel["sampler"]]["input"]]
            check(timeline["min"][0] == 0 and abs(timeline["max"][0] - duration) < 1e-6, (clip["name"], timeline))
    alpha_materials = {}
    for obj in ("SweepSurface", "ApproachEdge", "ContactPressure"):
        node = next(n for n in nodes if n["name"] == obj)
        mode = doc["materials"][doc["meshes"][node["mesh"]]["primitives"][0]["material"]].get("alphaMode")
        check(mode == "BLEND", (obj, mode))
        alpha_materials[obj] = mode
    return {"node_count": len(nodes), "unique_mesh_count": len(doc["meshes"]),
            "embedded_source_image_count": sum(expected.values()), "embedded_source_PNG_sha256": dict(expected),
            "embedded_ENV001_stitch_PNG_sha256": list(stitches),
            "clip_target_counts": {key: len(entry[2]) for key, entry in contract.items()},
            "alpha_mode_by_effect": alpha_materials, "visual_root_children": sorted(roots)}


def silent_video(path, frame_count):
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True)
    streams = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
        "stream=codec_type,codec_name,width,height,nb_read_frames,duration,r_frame_rate",
        "-of", "json", str(path)]))["streams"]
    video, = streams
    check(video["codec_type"] == "video" and video["codec_name"] == "h264" and
          int(video["nb_read_frames"]) == frame_count and (video["width"], video["height"]) == (852, 394) and
          abs(float(video["duration"]) - frame_count / VIDEO_RATE) < 1e-6, (path, video))
    return {**video, "source_frame_pixels": list(FRAME), "audio_tracks": 0, "all_frames_decoded": True}


def build(library, output, warn, quick):
    _, fx, upstream, warning = warn
    single, _, env, _, layout, *_ = upstream
    scene = single["reset"]()
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    scene.name = "LVL-S4 | Wind farm and protected marsh"
    parts = adopt_import_groups(scene, library=library)
    root = set_asset_links(scene, parts)
    initialize_reused_loops(parts, library, imported=False)
    stage = context_with_apron(scene, library, upstream, parts)
    temp_glb = output / "stitch_for_merge.glb"
    merge_stitch_tiles(scene, stage, temp_glb, root)
    exports = [asset_dir(library, asset) / names[1] for asset, names in SOURCE_PARTS.items()]
    merge_glbs([*exports, temp_glb], output / GLB)
    temp_glb.unlink()
    transport = readback_transport(library, output / GLB)
    bind_warning(warn, scene, WARNING_START)
    package = disk_placement(layout, warning, stage["landing"])
    write(output / LAYOUT, package)
    proof = terrain_and_sweep(scene, warn, stage)
    cue = warning_proof(scene, warn, WARNING_START)
    phase = rotor_phase_checks(scene, warn)
    angles = camera_proof(scene, stage, warn, (0, 10, 48, 90, 130, 144, LANDING_FRAME, WARNING_START + 28))
    view = render_proofs(scene, stage, warn, output, "quick" if quick else "source")
    pack_and_save(scene, stage, warn, output / BLEND)
    if not quick:
        base = env["B"]
        scene.camera = stage["cam"]
        for name, frames in ((SHEET, range(0, RUN_LENGTH, 3)), (PROBE, range(WARNING_START, WARNING_START + 120, 3))):
            folder = output / Path(name).stem
            folder.mkdir()
            for i, frame in enumerate(frames):
                apply_state(scene, stage, warn, frame)
                base["render"](scene, stage["cam"], folder, f"{i:04d}", FRAME, 5)
            single["encode"](folder, output / name, VIDEO_RATE)
            shutil.rmtree(folder)
    write(output / "source_checks.json", {"measured_geometry": proof, "warning": cue, "loops": phase, "camera": angles,
                                         "warning_render_difference": view, "transport_structure": transport})


def stage_from_saved(scene, warn):
    collection = bpy.data.collections["Review | CHR-001 formation and ANM-007 landing"]
    pads = bpy.data.collections["Review | ENV-001 scenery continuation"]
    markers = bpy.data.collections["Review only | Outer lane and wetland gates"]
    flight = sorted((o for o in collection.objects if o.name.startswith("V flight |")), key=lambda o: o.name)
    resting = sorted((o for o in collection.objects if o.name.startswith("Review resting goose")), key=lambda o: o.name)
    check(len(flight) == len(resting) == 12, "Review count after reopening")
    _, _, upstream, _ = warn
    _, farm, env, *_ = upstream
    layers = [bpy.data.objects[n] for n in farm["WET"][1:]]
    check(len({o.data for o in flight}) == 1 and len({o.data for o in resting}) == 1, "Shared review meshes")
    repro = bpy.data.collections.new("Temporary | Standing pose contact witnesses")
    scene.collection.children.link(repro)
    check_positions, landing = env["BASELINE"]["populate_flock"](repro, layers[0])
    max_difference = max((ob.location - ref.location).length for ob, ref in zip(resting, check_positions))
    check(max_difference < 1e-6, ("Filed landing coordinates changed", max_difference))
    for obj in check_positions:
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(repro)
    return {"pads": (collection, pads), "markers": markers,
            "flight": flight, "resting": resting, "landing": landing, "bird": flight[0], "layers": layers,
            "cam": bpy.data.objects[CAMERA]}


def verify(library, delivery, output, warn, quick):
    _, fx, upstream, warning = warn
    single, _, env, _, layout, *_ = upstream
    bpy.ops.wm.open_mainfile(filepath=str(delivery / BLEND))
    source_scene = bpy.context.scene
    root = bpy.data.objects[ROOT]
    check(len(root.children) == 5 and root.location.length < 1e-7 and root["collision_enabled"] is False, "Master assembly root")
    check((source_scene.render.resolution_x, source_scene.render.resolution_y) == FRAME, "Saved 852 × 393 review frame")
    source_stage = stage_from_saved(source_scene, warn)
    source_cam = camera_proof(source_scene, source_stage, warn, (0, 10, 48, 90, 130, 144, LANDING_FRAME, WARNING_START + 28),
                              check_keyframes=True)
    source_geo = terrain_and_sweep(source_scene, warn, source_stage)
    source_warn = warning_proof(source_scene, warn, WARNING_START)
    source_motion = rotor_phase_checks(source_scene, warn)

    scene = single["reset"]()
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    parts = adopt_import_groups(scene, glb_path=delivery / GLB)
    initialize_reused_loops(parts, library, imported=True)
    stage = context_with_apron(scene, library, upstream, parts)
    bind_warning(warn, scene, WARNING_START)
    ret_geo = terrain_and_sweep(scene, warn, stage)
    ret_warn = warning_proof(scene, warn, WARNING_START)
    ret_motion = rotor_phase_checks(scene, warn)
    fields = ("minimum_reserved_lane_width_BU", "V_formation_width_BU", "whole_track_min_gap_BU",
              "conservative_landing_AABB_gap_BU")
    deltas = {key: abs(source_geo["formation_and_wetland"][key] - ret_geo["formation_and_wetland"][key]) for key in fields}
    check(max(deltas.values()) < 1e-5, deltas)
    compare_values = [abs(source_warn["one_shot_morphs"][name]["peak_planar_area_BU2"] -
                          detail["peak_planar_area_BU2"]) for name, detail in ret_warn["one_shot_morphs"].items()]
    check(max(compare_values) < 1e-5, compare_values)
    readback = readback_transport(library, delivery / GLB)
    render_proofs(scene, stage, warn, output, "verify")
    frame_compare = {}
    for evidence in ("fixed_rear_approach", "warning_edge", "contact_wave", "wetland_landing"):
        difference = compare_rgb(delivery / f"preview_{evidence}.png", output / f"roundtrip_{evidence}.png",
                                 fx["image_rgb"], 12)
        check(difference["mean_absolute_RGB_8bit"] < 5, (evidence, difference))
        frame_compare[evidence] = difference
    video = None if quick else {name: silent_video(delivery / name, count) for name, count in ((SHEET, 48), (PROBE, 40))}
    write(output / "recheck.json", {"status": "pass", "reopened_blend_camera": source_cam,
        "reopened_blend_geometry": source_geo, "reopened_blend_warning": source_warn,
        "reopened_blend_loops": source_motion, "GLB_transport": readback, "GLB_geometry": ret_geo,
        "GLB_warning": ret_warn, "GLB_loops": ret_motion, "GLB_roundtrip_critical_clearance_delta_BU": deltas,
        "warning_peak_area_delta_BU2": max(compare_values), "evidence_render_comparisons": frame_compare,
        "silent_video_full_decode": video})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--library", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--verify", type=Path, help="Reopen .blend, import .glb and decode both videos from this directory")
    parser.add_argument("--quick", action="store_true", help="Generate stills and geometry without rendering the videos")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output, library = args.output.resolve(), args.library.resolve()
    output.mkdir(parents=True, exist_ok=True)
    check(not any(output.iterdir()), "Output must be a new empty directory")
    sources = dependency_inputs(library)
    if args.verify and (args.verify.resolve() / "asset_manifest.json").is_file():
        manifest = read(args.verify.resolve() / "asset_manifest.json")
        check(sources == manifest["source_files_relative_to_Blender_library"], "Pinned source files changed")
    helper, (fx, upstream, warning) = initialize(library)
    warn = helper, fx, upstream, warning
    if args.verify:
        verify(library, args.verify.resolve(), output, warn, args.quick)
    else:
        build(library, output, warn, args.quick)


if __name__ == "__main__":
    main()
