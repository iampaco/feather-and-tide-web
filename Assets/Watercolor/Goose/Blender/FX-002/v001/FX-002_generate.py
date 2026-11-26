"""Build and independently audit the FX-002 crosswind candidate with Blender 5.2."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import numpy as np

ASSET = "FX-002"
VERSION = "v001"
STATUS = "needs_review"
BLEND = "FX-002_Crosswind.blend"
SCENE = "FX-002 | S3 downstream preview"
ASSET_SCENE = "FX-002 | Export modules"
VIDEO = "preview_fixed_rear_silent.mp4"
MAPPING = "runtime_mapping.json"
BANDS = {"WarnBand": "Short", "CrownSweep": "Short", "GustBand": "Long"}
PARTS = {"CrosswindWarn": ("WarnBand", "CrownSweep"), "Gust": ("GustBand", "Leaf")}
TEXTURES = {name: f"textures/ft_goose_fx_crosswind_{name}_rgba.png"
            for name in ("warn", "crown", "gust", "leaf")}
PART_TEXTURES = dict(zip((*BANDS, "Leaf"), TEXTURES.values()))
PIGMENTS = {"WarnBand": (188, 217, 217), "CrownSweep": (184, 217, 208),
            "GustBand": (172, 206, 209), "Leaf": (149, 173, 146)}
ALPHA = {"WarnBand": .55, "CrownSweep": .50, "GustBand": .62, "Leaf": .72}
SIZE = (852, 393)
BU = .9900 / 27.5
FPS, VIDEO_FPS, END = 24, 8, 108
DIRECTION = Vector((-.98, .20, 0)).normalized()
BEARING = math.atan2(-DIRECTION.x, DIRECTION.y)
ANCHOR = (3.72, 10.75, .19)
KEYS = {"treeEnvelope": ((0, 0), (.25, 0), (.58, .69), (1.36, .96), (2.2, 1),
                         (2.8, .55), (3.8, 0)),
        "warnEnvelope": ((0, 0), (.60, 0), (.85, .88), (1.25, 1), (1.55, .42),
                         (1.9, 0)),
        "gustEnvelope": ((0, 0), (1.26, 0), (1.48, .76), (1.87, 1), (2.5, .82),
                         (3.13, .28), (3.62, 0))}
EVENT = 47
EARLY, PEAK = 25, 49
INPUTS = {
    "FX-001": ("FX-001_WindTail.blend", "FX-001_generate.py",
               "FX-001_WindTail_Short.glb", "FX-001_WindTail_Long.glb",
               "textures/ft_goose_fx_wind_tail_short_rgba.png",
               "textures/ft_goose_fx_wind_tail_long_rgba.png"),
    "ENV-012": ("ENV-012_wind_trees.blend", "ENV-012_RiverTree_A.glb",
                "ENV-012_RiverTree_B.glb", "ENV-012_LeaningTree.glb"),
    "FX-007": ("wind_interface.json",),
    "FX-009": ("FX-009_RescueBeacon.glb", "runtime_mapping.json"),
}
INDEPENDENT = {"FX-001": ("independent_artifact_directory_reopen", "status"),
               "ENV-012": ("independent_reopen", "result"),
               "FX-009": ("glb_reimport", "status")}
CAMERA_PATH = "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift"
PLAYFIELD_PATH = "Sources/FeatherTide/Rendering/PlayfieldView.swift"


def expect(ok, message):
    if not ok:
        raise RuntimeError(str(message))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sources(lib):
    results = {}
    for asset, names in INPUTS.items():
        folder = lib / asset / VERSION
        manifest, qa = read(folder / "asset_manifest.json"), read(folder / "qa.json")
        expect((folder / "README.md").is_file(), asset)
        expect(manifest["status"] in ("needs_review", "done"), asset)
        if asset == "FX-007":
            expect(qa["blender_reopen"] == "pass",asset)
        if asset in INDEPENDENT:
            first, second = INDEPENDENT[asset]
            expect(qa[first][second] in ("pass", "passed"), (asset, qa[first].get(second)))
        files = {}
        for name in (*names, "qa.json", "README.md"):
            actual = digest(folder / name)
            expected = manifest["files"].get(name)
            if expected is not None:
                if isinstance(expected, dict):
                    expected = expected["sha256"]
                expect(actual == expected, (asset, name, actual, expected))
            files[name] = actual
        results[asset] = {"version": VERSION, "status": manifest["status"], "files": files,
                          "manifest_sha256": digest(folder / "asset_manifest.json")}
    repo = lib.parents[3]
    swift = (repo/CAMERA_PATH).read_text(encoding="utf-8")
    playfield = (repo/PLAYFIELD_PATH).read_text(encoding="utf-8")
    expect("distance: 180, pitch: 0.48, fieldOfViewDegrees: 50" in swift and
           "Float(6 + lift)" in swift and "altitude: CGFloat(sample.depthLift)" in playfield and
           "(body.leader ? 8 : 6)" in playfield, "Swift camera or body heights changed")
    return results,{path:digest(repo/path) for path in (CAMERA_PATH,PLAYFIELD_PATH)}


def group(scene, name):
    collection = bpy.data.collections.new(name)
    scene.collection.children.link(collection)
    return collection


def move(obj, collection):
    for current in tuple(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def empty(collection, name):
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    return obj


def driver(entity, key, index, expression, variables):
    if index is None:
        curve = entity.driver_add(key)
    else:
        curve = entity.driver_add(key, index)
    drv = curve.driver
    drv.type = "SCRIPTED"
    for name, obj, prop in variables:
        var = drv.variables.new()
        var.name = name
        var.type = "SINGLE_PROP"
        var.targets[0].id = obj
        var.targets[0].data_path = f'["{prop}"]'
    drv.expression = expression


def set_control(obj, key, value, low, high, text):
    obj[key] = value
    obj.id_properties_ui(key).update(min=low, max=high, description=text)


def create_sources(lib, scene, helper):
    folder = lib / "FX-001" / VERSION
    with bpy.data.libraries.load(str(folder / "FX-001_WindTail.blend")) as (src, dst):
        dst.objects = ["WindTail_Short", "WindTail_Long"]
    inherited = {obj.name.rsplit("_", 1)[-1]: obj for obj in dst.objects}
    result = {}
    for variant, parts in PARTS.items():
        collection = group(scene, variant)
        root = empty(collection, variant)
        root["axis_forward"] = "+Y"
        root["axis_up"] = "+Z"
        root["uv_contract"] = "U=0 upstream, U=1 downstream"
        root["placement"] = "Each child may be instanced independently at a world anchor."
        for name in parts:
            if name == "Leaf":
                verts = ((0, 0, 0), (-.035, .095, .021), (-.024, .173, .017),
                         (.009, .24, .043), (.035, .156, .005), (.029, .078, -.004),
                         (.001, .126, .021))
                faces = tuple((i, (i + 1) % 6, 6) for i in range(6))
                uvs = tuple((y / .24, .5 + x/.095) for x, y, _ in verts)
                obj = helper["basic_mesh"](collection, name, verts, faces, uvs)
            else:
                source = inherited[BANDS[name]]
                obj = bpy.data.objects.new(name, source.data.copy())
                collection.objects.link(obj)
                obj.data.materials.clear()
                axes = {"WarnBand": (1.7, 1.20), "CrownSweep": (1.95, .80),
                        "GustBand": (1.45, 1.0)}
                xscale, yscale = axes[name]
                for vertex in obj.data.vertices:
                    vertex.co.x *= xscale
                    vertex.co.y *= yscale
            obj.parent = root
            obj["module"] = name
            obj["pivot"] = "Upstream center"
            result[name] = obj
    return result


def create_textures(lib, output, parts, helper):
    (output / "textures").mkdir(exist_ok=True)
    for name, obj in parts.items():
        path = output / PART_TEXTURES[name]
        peak = ALPHA[name]
        if name in BANDS:
            length = BANDS[name].lower()
            old_path = (lib / "FX-001/v001/textures" /
                        f"ft_goose_fx_wind_tail_{length}_rgba.png")
            old_image = bpy.data.images.load(str(old_path), check_existing=False)
            source = helper["image_rows"](old_image)
            a = source[:, :, 3]
            noise = (source[:, :, :3].mean(axis=2) - source[:, :, :3].mean()) * 255
            alpha = a / a.max() * peak
            bpy.data.images.remove(old_image)
        else:
            u, v = np.meshgrid((np.arange(128) + .5) / 128, (np.arange(64) + .5) / 64)
            noise = 1.5*np.sin(117*u+37*v) + 2.0*np.sin(26*u+16*v)
            alpha = peak * helper["smooth"](.015, .12, u) * (1-helper["smooth"](.89, .995, u))
            alpha *= 1-helper["smooth"](.75, 1, abs(v-.50)/.44)
        rgba = np.empty((*alpha.shape, 4), dtype=np.uint8)
        rgba[:, :, :3] = np.rint(np.clip(np.asarray(PIGMENTS[name])+noise[:, :, None], 0, 255))
        rgba[:, :, 3] = np.rint(alpha*255).astype(np.uint8)
        rgba[:, (0, -1), 3] = 0
        rgba[(0, -1), :, 3] = 0
        helper["write_rgba"](path, rgba)
        img = bpy.data.images.load(str(path), check_existing=False)
        img.alpha_mode = "STRAIGHT"
        img.pack()
        img.filepath = "//"+PART_TEXTURES[name]
        material = helper["ribbon_material"](f"FX-002 | {name} watercolor", img)
        obj.data.materials.append(material)


def export(scene, directory, children):
    bpy.context.window.scene = scene
    scene.frame_set(1)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in children:
        obj.hide_set(False)
        obj.select_set(True)
    expect(bpy.ops.export_scene.gltf(filepath=str(directory), use_selection=True,
           use_active_scene=True, export_animations=False, export_yup=True,
           export_extras=True) == {"FINISHED"}, directory)


def bake_keys(control, key, keys):
    for t, value in keys:
        control[key] = value
        control.keyframe_insert(data_path=f'["{key}"]', frame=1+round(t*FPS), group="Cue envelopes")


def setup(lib, asset_scene, source, helper):
    scene = bpy.data.scenes["ENV-012 | River wind study"]
    scene.name = SCENE
    bpy.context.window.scene = scene
    for other in tuple(bpy.data.scenes):
        if other not in (scene, asset_scene):
            bpy.data.scenes.remove(other)
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_x, scene.render.resolution_y = SIZE
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.render.fps_base = 1
    scene.frame_start, scene.frame_end = 1, END
    for marker in tuple(scene.timeline_markers):
        scene.timeline_markers.remove(marker)
    for frame, label in ((1, "Quiet river"), (8, "Tree response begins"),
                         (16, "Warning starts"), (32, "Gust starts"),
                         (EVENT, "Host separation event example"), (92, "Recovery")):
        scene.timeline_markers.new(label, frame=frame)
    bg = scene.world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (.29, .42, .42, 1)
        bg.inputs[1].default_value = .68
    scene.view_settings.view_transform = "AgX"
    group_ctrl = group(scene, "Wind field and fixed camera review")
    control = empty(group_ctrl, "FX-002 | Edit shared wind inputs")
    set_control(control, "windBearingRad", BEARING, -math.pi, math.pi,
                "FX-001 yaw from +Y to normalized downwind; trees and ribbons share it.")
    set_control(control, "strength", .90, 0, 1, "Peak normalized gust intensity.")
    set_control(control, "motionScale", 1., 0, 1, "0 stops advection, leaves and bend; retains softened bands.")
    set_control(control, "reviewFlightBUPerSecond", .26, 0, 1., "Review leader speed. Camera follows in lockstep.")
    set_control(control, "windSpeedBUPerSecond", 1.95, 0, 6, "Strong-gust review advection speed.")
    for key in KEYS:
        set_control(control, key, 0., 0, 1, "Edit keyframes in Cue envelopes.")
        bake_keys(control, key, KEYS[key])
    for group_old in scene.collection.children:
        for obj in group_old.objects:
            if obj.name.startswith("Review | CHR-001"):
                lead = obj
    travel = empty(group_ctrl, "Lead and fixed third-person camera travel")
    driver(travel, "location", 1, f"v*(frame-1)/{FPS}", [("v", control, "reviewFlightBUPerSecond")])
    lead.parent = travel
    scene.camera.parent = travel
    scene.camera.name = "Gameplay | Swift fixed rear"
    # PlayfieldView puts the lead body at 8 + depthLift. The camera uses depthLift only.
    lift = lead.location.z - 8*BU
    eye_offset = Vector((0,-180*BU*math.cos(.48),180*BU*math.sin(.48)))
    scene.camera.location = Vector((lead.location.x,lead.location.y,lift)) + eye_offset
    scene.camera.rotation_euler = (Vector((0,0,6*BU))-eye_offset).to_track_quat("-Z","Y").to_euler()
    scene.camera.data.sensor_fit = "VERTICAL"
    scene.camera.data.sensor_height = 24
    scene.camera.data.lens = 12/math.tan(math.radians(25))
    if not any(obj.type == "LIGHT" and obj.data.type == "AREA" for obj in scene.objects):
        helper["light"](group_ctrl)
    fill = bpy.data.lights.new("Soft north sky", "SUN")
    fill.energy = 1.25
    sun = bpy.data.objects.new("Soft north sky", fill)
    group_ctrl.objects.link(sun)
    sun.rotation_euler = (.31,.18,-.31)
    top = helper["camera"](group_ctrl, "Technical | wind and clear rescue area",
                            (1.6,8.6,24), (1.6,8.6,0), 18)
    top.rotation_euler = (0, 0, 0)

    for tree in [o for o in scene.objects if o.type == "ARMATURE"]:
        tree.animation_data_clear()
        # World-axis bending is stable across all instance yaws.
        yaw = tree.rotation_euler.z
        for bone_name, angle, index in (("Stem", 8, 0), ("Crown", 18, 1)):
            bone = tree.pose.bones[bone_name]
            bone.rotation_mode = "QUATERNION"
            local = bone.bone.matrix_local.to_3x3().inverted()
            rx, ry = local @ Vector((-1,0,0)), local @ Vector((0,-1,0))
            half_angle = math.radians(angle)/2
            en = f"{half_angle:.12f}*s*m*e*(.87+.13*sin((frame-1)*.149-{index*.43}))"
            inputs = [("s", control, "strength"), ("m", control, "motionScale"),
                      ("e", control, "treeEnvelope")]
            driver(bone, "rotation_quaternion", 0, f"cos({en})", inputs)
            for component in range(3):
                axis = (f"({rx[component]:.12f}*cos(a-{yaw:.12f})+"
                        f"{ry[component]:.12f}*sin(a-{yaw:.12f}))")
                driver(bone, "rotation_quaternion", component+1, f"{axis}*sin({en})",
                       inputs+[("a", control, "windBearingRad")])

    group_fx = group(scene, "Crosswind lanes and leaf paths")
    # Wide world lanes leave the beacon and leading bird some screen space.
    layouts = {
        "WarnBand": ((.16, 6.3, .86), (1.22, 8.95, 1.62), (1.34, 12.5, 1.25),
                     (3.6, 15.3, .95)),
        "CrownSweep": ((-2.15, 6.36, 1.62), (-2.58, 10.16, 1.98),
                       (-2.56, 15.33, 1.34)),
        "GustBand": ((.72, 6.73, .82), (1.03, 8.72, 1.63), (1.48, 11.73, .98),
                     (2.34, 14.25, 1.52), (4.55, 16.6, 1.22)),
        "Leaf": ((.30, 6.33, 1.12), (-.07, 8.36, 1.39), (1.0, 9.88, .95),
                 (-.37, 12.0, 1.19), (2.02, 13.1, 1.78)),
    }
    for name, placements in layouts.items():
        for i, point in enumerate(placements):
            node = bpy.data.objects.new(f"Review {name} {i+1:02d}", source[name].data.copy())
            group_fx.objects.link(node)
            node["module"] = name
            node["baseline"] = point
            node.rotation_mode = "XYZ"
            asset_rig(node, point, i, name, control)
    beacon_group = group(scene, "FX-009 | rescue keepout reference only")
    old = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(lib / "FX-009/v001/FX-009_RescueBeacon.glb"))
    imported = set(bpy.data.objects)-old
    parent = next(obj for obj in imported if obj.type == "EMPTY")
    parent.location = ANCHOR
    parent["review_anchor_role"] = "Actual rescue assets retained for material and visibility evaluation."
    for obj in imported:
        move(obj, beacon_group)
        if obj.name.endswith("SoftPoint"):
            obj.rotation_euler.z = math.atan2(-(scene.camera.location.x-ANCHOR[0]),
                                             scene.camera.location.y-ANCHOR[1])-math.pi
    bpy.context.view_layer.update()
    return scene, control, top


def end_for(name):
    return .60 if name in PARTS["CrosswindWarn"] else 1.26


def asset_rig(node, point, index, name, control):
    common = [("a", control, "windBearingRad"), ("m", control, "motionScale"),
              ("v", control, "windSpeedBUPerSecond"), ("s", control, "strength")]
    speed = {"WarnBand": .50, "CrownSweep": .60, "GustBand": 1.0, "Leaf": .79}[name]
    # Keep the review placements at a fixed world station. Each short travel ends before recycling.
    span = f"min(1.60,max(0,(frame-1)/{FPS}-{end_for(name)}))*m*v*s*{speed}"
    driver(node, "location", 0, f"{point[0]}-sin(a)*{span}", common)
    driver(node, "location", 1, f"{point[1]}+cos(a)*{span}", common)
    if name == "Leaf":
        driver(node, "location", 2, f"{point[2]} + .11*m*sin((frame-1)*.30+{index})", common)
        driver(node, "rotation_euler", 0, f".6*m*sin((frame-1)*.21+{index})", common)
        driver(node, "rotation_euler", 1, f".5*m*sin((frame-1)*.22+{index})", common)
    else:
        node.location.z = point[2]
        node.rotation_euler.x = math.radians(14 if name != "CrownSweep" else 6)
    driver(node, "rotation_euler", 2, "a", common)


def review_material(name, image, window, rating, control, helper):
    material = helper["ribbon_material"](f"FX-002 | {name} editable review envelope", image)
    nodes, links = material.node_tree.nodes, material.node_tree.links
    shader = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    image_node = next(n for n in nodes if n.type == "TEX_IMAGE")
    multiply = nodes.new("ShaderNodeMath")
    multiply.operation = "MULTIPLY"
    multiply.name = "World wind envelope times source alpha"
    multiply.location = (-30, -75)
    expr = f"{rating}*e*s*m" if name == "Leaf" else f"{rating}*e*s*(.48+.52*m)"
    driver(multiply.inputs[1], "default_value", None, expr,
           [("e", control, window), ("s", control, "strength"), ("m", control, "motionScale")])
    links.new(image_node.outputs["Alpha"], multiply.inputs[0])
    links.new(multiply.outputs[0], shader.inputs["Alpha"])
    return material


def render(scene, frame, path, camera=None, samples=16):
    old = scene.camera
    scene.camera = camera or old
    scene.eevee.taa_render_samples = samples
    scene.frame_set(frame)
    scene.render.filepath = str(path)
    expect(bpy.ops.render.render(write_still=True) == {"FINISHED"}, path)
    scene.camera = old


def binary(name):
    return shutil.which(name) or str(Path("/opt/homebrew/bin")/name)


def video(scene, out):
    with TemporaryDirectory(prefix="fx002-frames-", dir=out) as temporary:
        frames = Path(temporary)
        for index, frame in enumerate(range(1, END+1, FPS//VIDEO_FPS)):
            render(scene, frame, frames / f"{index:03d}.png", samples=8)
        subprocess.run([binary("ffmpeg"), "-v", "error", "-y", "-framerate", str(VIDEO_FPS),
                        "-i", str(frames/"%03d.png"), "-vf", "pad=852:394:0:0",
                        "-c:v", "libx264", "-threads", "2", "-pix_fmt", "yuv420p",
                        "-crf", "16", "-movflags", "+faststart", str(out/VIDEO)], check=True)


def mapping():
    return {
        "id": ASSET, "version": VERSION, "status": STATUS, "coordinates": {
            "blender_up": "+Z", "blender_forward": "+Y", "gltf_conversion": "(x,z,-y)",
            "bu_per_game_unit": BU, "reference": "CHR-001 bill-to-tail .9900 BU = 27.5 game units"},
        "pivot_and_uv": "Each module uses upstream center and U=0 upstream to U=1 downstream. Local +Y is downwind. V crosses ribbon width. Root and child basis transforms are identity.",
        "prefabs": {v: {"file": f"{ASSET}_{v}.glb", "mesh_nodes": parts} for v, parts in PARTS.items()},
        "inputs": {
            "direction": "Shared FX-007 normalized horizontal world downwind. Blender (dx,dy,0), RealityKit (dx,0,-dy). For zero direction set strength=0. Yaw is atan2(-dx,dy) about Blender +Z.",
            "strength": "Normalized 0–1 signal shared by FX-002 bands and ENV-012 tree rigs. Strength drives vegetation angle and visual opacity.",
            "clockSeconds": "Common elapsed time. Mesh downstream drift = speed times elapsed phase, aligned to direction. Fade at field ends before reusing.",
            "motionScale": "0–1; zero freezes advection and neutralizes the tree bend, hides leaves, and retains softly fading low-opacity fixed bands.",
            "windSpeedBUPerSecond": "Nonnegative magnitude, multiply the game-unit speed by 0.036. Default offline sample 1.95 BU/s.",
            "phaseRad": "Optional per-tree stable phase (see FX-007 shared joint basis). Crown lags Stem by .43 rad.",
            "treeEnvelope": "Start wind indicator before all wind ribbons. Bend Stem/Crown about inverse-rest (up cross downwind), preserve Root. Offline max 8/18 degrees before normalized strength.",
            "warnEnvelope": "Drive low alpha on WarnBand and CrownSweep. CrownSweep is a short independent mask placed on exposed treetop edges.",
            "gustEnvelope": "Drive GustBand plus optional Leaf instances. Leaves can tumble locally and fade. Transform all from one wind field.",
            "rescueAnchorWorld": "Host supplies reachable anchor. Leave enough world and projected screen room to keep the beacon and separated goose visible.",
            "zoneEvent": "Game owns all activation, movement, loss/rejoin, and timing. No collisions, event geometry or rescue logic in the export.",
        },
        "review": {"direction": list(DIRECTION.xy), "source_fx007_S3": [-.98,.20],
                   "fixed_S3_world_anchor_BU": list(ANCHOR),
                   "tree_starts_seconds": .25, "warn_starts_seconds": .60,
                   "gust_starts_seconds": 1.26, "example_separation_seconds": (EVENT-1)/FPS,
                   "strength": .90, "preset_intensity_curves": KEYS,
                   "camera": {"viewport_px": SIZE,"distance_game_units": 180,
                              "pitch_rad": .48,"vertical_fov_deg": 50,"target_lift_game_units": 6}},
    }


def stage(lib, out, helper):
    bpy.ops.wm.open_mainfile(filepath=str(lib/"ENV-012/v001/ENV-012_wind_trees.blend"))
    asset_scene = bpy.data.scenes.new(ASSET_SCENE)
    parts = create_sources(lib, asset_scene, helper)
    gray = helper["flat_material"]("Crosswind modules | graybox", (.62,.79,.79))
    for obj in parts.values():
        obj.data.materials.append(gray)
    scene, control, top = setup(lib, asset_scene, parts, helper)
    # Limit clay to the effect modules, retaining the existing terrain as a placement reference.
    targets = [o for o in scene.objects if o.get("module")]
    original_gray_mats = {o.name: o.data.materials[0] for o in targets}
    for target in targets:
        target.data.materials[0] = gray
        if target["module"] == "CrownSweep":
            target.hide_render = True
    render(scene, PEAK, out/"graybox_fixed_rear.png")
    render(scene, PEAK, out/"graybox_top.png", top)
    for target in targets:
        target.data.materials[0] = original_gray_mats[target.name]
        target.hide_render = False
    for obj in parts.values():
        obj.data.materials.clear()
    create_textures(lib, out, parts, helper)
    for target in targets:
        name = target["module"]
        src_image = next(n.image for n in parts[name].data.materials[0].node_tree.nodes
                         if n.type == "TEX_IMAGE")
        key = "warnEnvelope" if name in PARTS["CrosswindWarn"] else "gustEnvelope"
        target.data.materials[0] = review_material(name, src_image, key,
                                                   .83 if name == "Leaf" else 1., control, helper)
    for variant, names in PARTS.items():
        export(asset_scene, out/f"{ASSET}_{variant}.glb",
               [bpy.data.objects[variant], *[parts[n] for n in names]])
    bpy.context.window.scene = scene
    render(scene, 1, out/"comparison_before_wind.png")
    for frame, token in ((EARLY, "warning"), (PEAK, "gust")):
        render(scene, frame, out/f"preview_fixed_rear_{token}.png")
        for target in targets:
            target.hide_render=True
        render(scene, frame, out/f"comparison_{token}_tree_only.png")
        for target in targets:
            target.hide_render=False
    render(scene, PEAK, out/"preview_top.png", top)
    control["motionScale"] = 0.
    control.update_tag()
    render(scene, PEAK, out/"preview_fixed_rear_reduced.png")
    control["motionScale"] = 1.
    control.update_tag()
    scene.frame_set(PEAK)
    scene.camera = bpy.data.objects["Gameplay | Swift fixed rear"]
    scene.render.filepath = "//"
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
    bpy.ops.object.select_all(action="DESELECT")
    control.select_set(True)
    bpy.context.view_layer.objects.active = control
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/BLEND), compress=True)
    write(out/MAPPING, mapping())
    video(scene, out)


def vertices(obj, graph):
    evaluated = obj.evaluated_get(graph)
    return [evaluated.matrix_world @ v.co for v in evaluated.data.vertices]


def box_for(scene, cam, points):
    projected = [world_to_camera_view(scene, cam, p) for p in points]
    xy = [(v.x*SIZE[0], v.y*SIZE[1]) for v in projected]
    x, y = zip(*xy)
    return min(x), min(y), max(x), max(y)


def gap(a, b):
    return max(b[0]-a[2], a[0]-b[2], b[1]-a[3], a[1]-b[3])


def visible_area(b):
    return max(0,min(b[2],SIZE[0])-max(b[0],0))*max(0,min(b[3],SIZE[1])-max(b[1],0))


def audit_motion(scene):
    controller = scene.objects["FX-002 | Edit shared wind inputs"]
    camera = scene.camera
    leaf = scene.objects["Review Leaf 01"]
    warn = scene.objects["Review WarnBand 01"]
    gust = scene.objects["Review GustBand 01"]
    lead = next(o for o in scene.objects if o.name.startswith("Review | CHR-001"))
    beacon = [o for o in scene.objects if o.name.startswith("RescueBeacon") and o.type=="MESH"]
    bird = next(o for o in scene.objects if o.name.startswith("Rescue target"))
    trees = [o for o in scene.objects if o.type=="ARMATURE"]
    fx = [o for o in scene.objects if o.get("module")]
    expect(len(beacon)==2 and len(trees)==6 and len(fx)==17, (len(beacon),len(trees),len(fx)))
    scene.frame_set(1)
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    tree_meshes = [t.children[0] for t in trees]
    tips = {o.name: max(range(len(o.data.vertices)), key=lambda i: o.data.vertices[i].co.z)
            for o in tree_meshes}
    rest = [vertices(o, graph)[tips[o.name]] for o in tree_meshes]
    zeros = [min(range(len(o.data.vertices)),key=lambda i:o.data.vertices[i].co.z) for o in tree_meshes]
    bases = [vertices(o,graph)[i] for o,i in zip(tree_meshes,zeros,strict=True)]
    camera_offset = camera.matrix_world.translation-lead.matrix_world.translation
    restore = [o.location.copy() for o in (warn,gust,leaf)]
    first = {"tree": None,"warning": None,"gust": None}
    min_rescue, min_tree, min_lead = (10000.,)*3
    travel_min, max_bend, min_dot, max_base = 10000., 0., 1., 0.
    visible = {"WarnBand": 0,"GustBand": 0,"Leaf": 0,"CrownSweep": 0}
    max_active = 0
    stage_offset = Vector((0,-180*BU*math.cos(.48),(180*math.sin(.48)-8)*BU))
    look_at = Vector((0,0,(6-8)*BU))-stage_offset
    real_view = camera.matrix_world.to_quaternion()@Vector((0,0,-1))
    fov = math.degrees(2*math.atan(camera.data.sensor_height/(2*camera.data.lens)))
    expect((stage_offset-camera_offset).length<.00001 and
           real_view.dot(look_at.normalized())>.99999 and abs(fov-50)<.0001,
           (camera_offset, stage_offset, real_view, fov))
    observer = {"size_px":list(SIZE),"camera_translation_from_lead_BU":list(camera_offset),
                "swift_distance_parameter_game_units":180,"swift_pitch_parameter_rad":.48,
                "measured_vertical_fov_deg":fov,"swift_target_height_parameter_BU":6*BU}
    rescue_terrain_paths = [o for o in scene.objects if o.type=="MESH" and
                            any(c.name.startswith("Review terrain") for c in o.users_collection)
                            and "Water" not in o.name and not o.hide_render]
    vs, fs = [], []
    for o in rescue_terrain_paths:
        offset = len(vs)
        vs.extend(vertices(o,graph))
        fs.extend(tuple(offset+k for k in poly.vertices) for poly in o.data.polygons)
    terrain = BVHTree.FromPolygons(vs,fs,all_triangles=False)
    terrain_rescue_rays = 0
    for sample in range(1,END*2):
        f = .5+.5*sample
        scene.frame_set(int(f),subframe=f%1)
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        tip_now = [vertices(o,graph)[tips[o.name]] for o in tree_meshes]
        disp = [after-before for after,before in zip(tip_now,rest,strict=True)]
        down = [d.dot(DIRECTION) for d in disp]
        max_bend = max(max_bend, max(down))
        if min(down)>.04 and first["tree"] is None:
            first["tree"] = f
        for current in (Vector((d.x,d.y,0)) for d in disp if d.length>.06):
            min_dot = min(min_dot,current.normalized().dot(DIRECTION))
        for o,i,base in zip(tree_meshes,zeros,bases,strict=True):
            max_base=max(max_base,(vertices(o,graph)[i]-base).length)
        cue_points = sum([vertices(o,graph) for o in beacon], [])
        cue_box = box_for(scene, camera, cue_points)
        bird_box = box_for(scene, camera, vertices(bird,graph))
        lead_box = box_for(scene, camera, vertices(lead,graph))
        tree_boxes = [box_for(scene,camera,vertices(o,graph)) for o in tree_meshes]
        min_tree = min(min_tree,*(gap(box, cue_box) for box in tree_boxes))
        expect(gap(cue_box,bird_box) > 0, ("marker and target",f,cue_box,bird_box))
        expect(2 < cue_box[0] and cue_box[2] < SIZE[0]-2 and
               2 < cue_box[1] and cue_box[3] < SIZE[1]-2, ("cue offscreen",f,cue_box))
        eye = camera.matrix_world.translation
        for point in cue_points[::max(1,len(cue_points)//20)]:
            delta = point-eye
            dist = delta.length
            hit, normal, index, along = terrain.ray_cast(eye,delta.normalized(),dist-.019)
            terrain_rescue_rays += 1
            expect(hit is None, ("terrain occluded beacon",f,point,hit))
        active = 0
        for o in fx:
            n = o["module"]
            is_warn = n in PARTS["CrosswindWarn"]
            alpha = controller["warnEnvelope" if is_warn else "gustEnvelope"]
            if alpha <= .015:
                continue
            points = vertices(o,graph)
            box = box_for(scene,camera,points)
            min_rescue = min(min_rescue,gap(cue_box,box),gap(bird_box,box))
            min_lead = min(min_lead,gap(lead_box,box))
            if visible_area(box)>4:
                active += 1
                visible[n] += 1
                cue = "warning" if is_warn else "gust"
                if alpha>.12 and first[cue] is None:
                    first[cue] = f
            # The leaf tumbles on its own axes, while its translation remains downwind.
            if n != "Leaf":
                axis = o.matrix_world.to_quaternion() @ Vector((0,1,0))
                axis.z = 0
                expect(axis.normalized().dot(DIRECTION)>.9999, (o.name,tuple(axis), tuple(DIRECTION)))
        max_active=max(max_active,active)
        expect((camera.matrix_world.translation-lead.matrix_world.translation-camera_offset).length
               < .00001, ("camera tracking",f))
    scene.frame_set(PEAK)
    bpy.context.view_layer.update()
    for obj, baseline in zip((warn,gust,leaf),restore,strict=True):
        travel = obj.location-baseline
        travel.z = 0
        travel_min = min(travel_min,travel.dot(DIRECTION))
        expect(travel.normalized().dot(DIRECTION)>.9999,(travel,DIRECTION))
    expect(min_rescue>0 and min_tree>0 and min_lead>0,(min_rescue,min_tree,min_lead))
    expect(all(visible.values()),visible)
    expect(first["tree"]<first["warning"]<first["gust"]<EVENT, first)
    expect(max_base < 1e-5 and min_dot > .95 and max_bend > .18 and travel_min > .10,
           (max_base,min_dot,max_bend,travel_min))
    # Reduce motion keeps the laid-out pattern without translation, moving leaves or tree tilt.
    controller["motionScale"]=0.
    controller.update_tag()
    scene.frame_set(PEAK)
    bpy.context.view_layer.update()
    graph=bpy.context.evaluated_depsgraph_get()
    reduced_tip=max((vertices(o,graph)[tips[o.name]]-p).length
                    for o,p in zip(tree_meshes,rest,strict=True))
    reduced_drift=max((o.location-Vector(o["baseline"])).length for o in fx)
    leaf_material=leaf.data.materials[0]
    leaf_alpha=leaf_material.evaluated_get(graph).node_tree.nodes[
        "World wind envelope times source alpha"].inputs[1].default_value
    expect(max(reduced_tip,reduced_drift,abs(leaf_alpha))<.00002,
           (reduced_tip,reduced_drift,leaf_alpha))
    controller["motionScale"]=1.
    controller["windBearingRad"]=BEARING-math.pi
    controller.update_tag()
    scene.frame_set(PEAK)
    bpy.context.view_layer.update()
    graph=bpy.context.evaluated_depsgraph_get()
    reverse_tip= min((vertices(o,graph)[tips[o.name]]-p).dot(-DIRECTION)
                     for o,p in zip(tree_meshes,rest,strict=True))
    reverse_band= min((o.location-Vector(o["baseline"])).dot(-DIRECTION)
                      for o in fx if o["module"]=="GustBand")
    expect(reverse_tip>.12 and reverse_band>.1, (reverse_tip, reverse_band))
    controller["windBearingRad"]=BEARING
    controller.update_tag()
    scene.frame_set(PEAK)
    bpy.context.view_layer.update()
    return {"status":"pass","half_frame_samples":END*2-1,
            "same_input_reversed_downwind_test":{"minimum_tree_tip_BU":reverse_tip,
                                                  "minimum_gust_band_travel_BU":reverse_band},
            "first_readable_frames":first,"example_host_event_frame":EVENT,
            "tree_warning_lead_seconds":round((first["warning"]-first["tree"])/FPS,5),
            "warning_before_example_event_seconds":round((EVENT-first["warning"])/FPS,5),
            "maximum_tree_tip_downwind_BU":max_bend,"minimum_tree_tip_direction_dot":min_dot,
            "tree_root_max_displacement_BU":max_base,"minimum_peak_effect_advection_BU":travel_min,
            "minimum_projected_fx_clearance_to_beacon_or_goose_px":min_rescue,
            "minimum_projected_tree_to_beacon_clearance_px":min_tree,
            "minimum_projected_fx_clearance_to_leader_px":min_lead,
            "terrain_unobstructed_beacon_rays":terrain_rescue_rays,
            "measured_visible_module_counts_by_half_frame":visible,
            "maximum_simultaneous_fx_objects_in_view":max_active,
            "reduced_motion":{"maximum_tree_tip_delta_BU":reduced_tip,
                              "maximum_drift_BU":reduced_drift,"leaf_alpha_multiplier":leaf_alpha},
            "camera":observer}


def reimport(scene, actual, helper):
    old_nodes = [o for o in scene.objects if o.get("module")]
    validated = {}
    textures = {}
    for variant, names in PARTS.items():
        path = actual / f"{ASSET}_{variant}.glb"
        doc, data = helper["read_glb"](path)
        expect(not doc.get("animations") and len(doc["meshes"])==2,path)
        expect(all(m["alphaMode"]=="BLEND" and m["doubleSided"] for m in doc["materials"]),path)
        for name in names:
            mesh = next(n["mesh"] for n in doc["nodes"] if n.get("name")==name)
            material = doc["meshes"][mesh]["primitives"][0]["material"]
            tex = doc["materials"][material]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
            image = doc["images"][doc["textures"][tex]["source"]]
            view = doc["bufferViews"][image["bufferView"]]
            pos = view.get("byteOffset",0)
            payload = data[pos:pos+view["byteLength"]]
            expect(payload==(actual/PART_TEXTURES[name]).read_bytes(),name)
            textures[name]=sha256(payload).hexdigest()
        old = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(path))
        spawned = set(bpy.data.objects)-old
        imported = {o.get("module"): o for o in spawned if o.type=="MESH"}
        expect(set(imported)==set(names),(variant,imported))
        asset_scene = bpy.data.scenes[ASSET_SCENE]
        export_checks = {}
        for name, new in imported.items():
            old_obj=asset_scene.objects[name]
            def tokens(obj):
                coords = obj.data.uv_layers.active.uv
                return {tuple(round(float(x),5) for x in (*obj.data.vertices[loop.vertex_index].co,
                         *coords[loop.index].vector)) for loop in obj.data.loops}
            expect(tokens(old_obj)==tokens(new),(variant,name))
            def triangles(obj):
                obj.data.calc_loop_triangles()
                return len(obj.data.loop_triangles)
            expect(triangles(old_obj)==triangles(new),name)
            # GLB import restores the local pivot and orientation, so review drivers remain valid.
            identity=np.eye(4)
            expect(np.max(np.abs(np.asarray(new.matrix_world)-identity))<1e-5,name)
            export_checks[name]={"triangle_count":triangles(new),"position_uv_pairs":len(tokens(new)),
                                 "pivot_axis_and_uv":"pass","embedded_png_sha256":textures[name]}
            for node in [o for o in old_nodes if o["module"]==name]:
                material=node.data.materials[0]
                node.data=new.data.copy()
                node.data.materials[0]=material
        for obj in spawned:
            bpy.data.objects.remove(obj,do_unlink=True)
        validated[variant]=export_checks
    return validated


def probe(path):
    subprocess.run([binary("ffmpeg"),"-v","error","-xerror","-i",str(path),"-f","null","-"],check=True)
    spec=json.loads(subprocess.check_output([binary("ffprobe"),"-v","error","-count_frames",
        "-show_entries","stream=codec_name,codec_type,width,height,nb_read_frames,duration",
        "-of","json",str(path)]))["streams"]
    expect(len(spec)==1 and spec[0]["codec_type"]=="video" and spec[0]["codec_name"]=="h264" and
           (spec[0]["width"],spec[0]["height"])==(852,394) and int(spec[0]["nb_read_frames"])==36,spec)
    return {"full_decode":"pass","source_frame_px":list(SIZE),"audio_streams":0,**spec[0]}


def verify(out, actual, helper):
    bpy.ops.wm.open_mainfile(filepath=str(actual/BLEND))
    scene=bpy.data.scenes[SCENE]
    bpy.context.window.scene=scene
    source_motion=audit_motion(scene)
    render(scene, PEAK, out/"reopened_fixed_rear.png")
    exports=reimport(scene,actual,helper)
    roundtrip_motion=audit_motion(scene)
    for name in ("minimum_projected_fx_clearance_to_beacon_or_goose_px",
                 "minimum_projected_fx_clearance_to_leader_px",
                 "minimum_peak_effect_advection_BU"):
        expect(abs(source_motion[name]-roundtrip_motion[name])<.01,name)
    picture=out/"roundtrip_fixed_rear.png"
    render(scene, PEAK, picture)
    difference=helper["image_diff"](out/"reopened_fixed_rear.png",picture)
    expect(difference["mean_abs_rgb8"] < .03,difference)
    expect(helper["image_diff"](actual/"preview_fixed_rear_gust.png",
                                 out/"reopened_fixed_rear.png")["mean_abs_rgb8"] < .03,
           "Material evidence differs after reopen")
    visual_deltas={}
    for token in ("warning","gust"):
        delta=helper["image_diff"](actual/f"preview_fixed_rear_{token}.png",
                                   actual/f"comparison_{token}_tree_only.png")
        expect(delta["pixels_at_least_threshold"]>=40, (token,delta))
        visual_deltas[token]=delta
    result={"id":ASSET,"version":VERSION,"status":STATUS,
            "fixed_rear_material_vs_tree_only":visual_deltas,
            "blender":bpy.app.version_string,"independent_artifact_directory_reopen":{
                "status":"pass","master":BLEND,"files":list(exports),
                "reopened_motion":source_motion,"roundtrip_motion":roundtrip_motion,
                "glb":exports,"render_rgb8_difference":difference},
            "video":probe(actual/VIDEO),
            "redline_review":"Project checklist reviewed against the offline visuals. Content is visual environmental response.",
            "pending":["Owner review of wind readability and watercolor at handheld size",
                       "Game wind inputs, zone triggers, rescue traversability, and transparency sorting",
                       "USDZ conversion and RealityKit/App integration",
                       "iPhone and iPad verification"]}
    write(out/"qa.json",result)


def manifest(folder, lib):
    dep, camera = sources(lib)
    files = {p.relative_to(folder).as_posix():digest(p)
             for p in sorted(folder.rglob("*")) if p.is_file() and p.name!="asset_manifest.json"}
    write(folder/"asset_manifest.json",{"id":ASSET,"version":VERSION,"status":STATUS,
        "execution_order_1_based":31,"pdf_page":14,"blender":"5.2.2 LTS","dependencies":dep,
        "camera_swift_sha256":camera,"runtime_mapping":MAPPING,
        "authoring":"FX-001 exact topology/UV derived with positive dimension transforms. Recolored existing alpha stroke; original low-poly accents and review timeline.",
        "rights":"Project-owned prior candidates and original procedural additions. Review-only rescue/vegetation source retained in the blend.",
        "files":files})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out",type=Path)
    parser.add_argument("--library",type=Path,
                        default=Path(__file__).resolve().parent.parents[1])
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--manifest-only",action="store_true")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    out=args.out.resolve()
    lib=args.library.resolve()
    if args.manifest_only:
        manifest(out,lib)
        return
    out.mkdir(exist_ok=True)
    expect(not list(out.iterdir()), "Use a fresh temporary output directory")
    sources(lib)
    helper=runpy.run_path(str(lib/"FX-001/v001/FX-001_generate.py"))
    if args.verify:
        verify(out,args.verify.resolve(),helper)
    else:
        stage(lib,out,helper)
        shutil.copyfile(Path(__file__).resolve(),out/Path(__file__).name)


if __name__=="__main__":
    main()
