"""Build and independently verify WindSwayPreset with Blender 5.2.2 LTS."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import runpy
import shutil
import struct
import subprocess
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Quaternion, Vector


STEM = "FX-007_WindSwayPreset"
CAMERA_SIZE = (852, 393)
GAME_UNITS_PER_BU = 27.5 / .9900
REEDS = tuple(f"Reed_{letter}_Height_{size}" for letter in "ABC" for size in "SM")
TREES = ("RiverTree_A", "RiverTree_B", "LeaningTree")
FPS = 24
END = 49
GUST_FRAME = 28
FORWARD = Vector((0, 1, 0))
EPS = 2e-5
STAGES = {
    "S1": {"direction": (0.96, 0.27), "strength": .24, "review": "Light wind"},
    "S3": {"direction": (-.98, .20), "strength": .84, "review": "Early gust cue"},
    "S5": {"direction": (.42, -.91), "strength": .94, "review": "Headwind"},
}
SOURCE_FILES = {
    "ENV-004": "ENV-004_reeds.blend",
    "ENV-012": "ENV-012_wind_trees.blend",
    "ENV-002": "ENV-002_wetland.blend",
    "CHR-001": "CHR-001_goose_rig.blend",
}


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_path(root, asset):
    return root / asset / "v001" / SOURCE_FILES[asset]


def verify_source(root, asset):
    path = source_path(root, asset)
    manifest = json.loads((path.parent / "asset_manifest.json").read_text())
    actual = digest(path)
    require(actual == manifest["files"][path.name], (asset, "source hash"))
    return path, actual


def append_objects(path, names):
    with bpy.data.libraries.load(str(path), link=False) as (source, dest):
        require(set(names) <= set(source.objects), (path, names))
        dest.objects = list(names)
    return dict(zip(names, dest.objects, strict=True))


def scene_setup(name):
    scene = bpy.data.scenes.new(name)
    bpy.context.window.scene = scene
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = END
    scene.render.resolution_x, scene.render.resolution_y = CAMERA_SIZE
    scene.render.resolution_percentage = 100
    return scene


def clear_pose(rig):
    if rig.animation_data:
        rig.animation_data_clear()
    for bone in rig.pose.bones:
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion = (1, 0, 0, 0)
        bone.location = (0, 0, 0)
        bone.scale = (1, 1, 1)
    rig.data.pose_position = "POSE"


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def attach_reed(studio, collection, mesh):
    height = max(v.co.z for v in mesh.data.vertices)
    armature = bpy.data.armatures.new(f"{mesh.name} | Rooted reed bones")
    rig = studio["obj"](collection, f"{mesh.name}_Rig", armature)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    previous = None
    for name, low, high in (("Root", 0, .14), ("Stem", .14, .54), ("Tip", .54, .98)):
        bone = armature.edit_bones.new(name)
        bone.head = (0, 0, low * height)
        bone.tail = (0, 0, high * height)
        if previous:
            bone.parent = previous
            bone.use_connect = True
        previous = bone
    bpy.ops.object.mode_set(mode="OBJECT")
    root, stem, tip = (mesh.vertex_groups.new(name=name) for name in ("Root", "Stem", "Tip"))
    for vertex in mesh.data.vertices:
        relative = vertex.co.z / height
        bend = smooth((relative - .14) / .48)
        tip_share = smooth((relative - .52) / .42)
        weights = (1 - bend, bend * (1 - tip_share), bend * tip_share)
        for group, weight in zip((root, stem, tip), weights, strict=True):
            if weight > 0:
                group.add([vertex.index], weight, "REPLACE")
    modifier = mesh.modifiers.new("WindSway | Root, Stem, Tip", "ARMATURE")
    modifier.object = rig
    mesh.parent = rig
    clear_pose(rig)
    return rig


def load_prototypes(source_paths, studio, scene):
    group = studio["collection"]("WindSwayPreset | reusable neutral plant rigs", scene.collection)
    reeds = append_objects(source_paths["ENV-004"], list(REEDS))
    trees = append_objects(source_paths["ENV-012"], [n for base in TREES for n in (base, f"{base}_Rig")])
    prototypes = {}
    for name in REEDS + TREES:
        item = reeds[name] if name in reeds else trees[name]
        group.objects.link(item)
        if name in reeds:
            rig = attach_reed(studio, group, item)
        else:
            rig = trees[f"{name}_Rig"]
            group.objects.link(rig)
            clear_pose(rig)
            for modifier in item.modifiers:
                if modifier.type == "ARMATURE":
                    modifier.use_deform_preserve_volume = False
        item["source_asset"] = "ENV-004/v001" if name in reeds else "ENV-012/v001"
        item["wind_preset"] = "WindSwayPreset"
        rig["runtime_tip_joint"] = "Tip" if name in reeds else "Crown"
        rig["runtime_joint_max_degrees"] = [14.0, 20.0] if name in reeds else [7.0, 13.0]
        prototypes[name] = (item, rig)
    bpy.context.view_layer.update()
    return prototypes


def simple_property(obj, name, value, minimum, maximum, description):
    obj[name] = value
    obj.id_properties_ui(name).update(min=minimum, max=maximum, description=description)


def cue_control(studio, stage, scn, group):
    controller = studio["obj"](group, f"WindSwayPreset | {stage} shared control", None)
    controller.empty_display_type = "ARROWS"
    controller.empty_display_size = .7
    controller.location = (0, 0, .04)
    cfg = STAGES[stage]
    simple_property(controller, "windAngleRad", math.atan2(cfg["direction"][1], cfg["direction"][0]),
                    -math.pi, math.pi, "Blender XY downwind angle from +X (toward +Y)")
    simple_property(controller, "windStrength", cfg["strength"], 0.0, 1.0, "Normalized bend input")
    simple_property(controller, "motionScale", 1.0, 0.0, 1.0, "Zero selects neutral pose")
    simple_property(controller, "periodSeconds", 1.75, .35, 8.0, "Oscillation period in seconds")
    simple_property(controller, "clockFps", float(FPS), 1.0, 120.0, "Match review scene FPS")
    if stage == "S3":
        for frame, strength in ((1, .035), (6, .035), (21, cfg["strength"]), (27, .77),
                                (40, .58), (END, .46)):
            controller["windStrength"] = strength
            controller.keyframe_insert(data_path='["windStrength"]', frame=frame)
        scn.timeline_markers.new("Illustrative wind field onset", frame=GUST_FRAME)
    return controller


def add_wind_drivers(rig, control):
    # Drive each pose basis from the horizontal axis Z × downwind, rotated into joint rest space.
    for index, name in enumerate(("Stem", rig["runtime_tip_joint"])):
        joint = rig.pose.bones[name]
        inverse_rest_rotate = joint.bone.matrix_local.to_quaternion().inverted()
        axis_sin = inverse_rest_rotate @ Vector((-1, 0, 0))
        axis_cos = inverse_rest_rotate @ Vector((0, 1, 0))
        half_peak = math.radians(rig["runtime_joint_max_degrees"][index]) / 2
        oscillation = f"(.71+.29*sin((frame-1)*6.283185307/(fps*period)+phase-{index*.43:.2f}))"
        half_angle = f"({half_peak:.10f}*s*scale*response*{oscillation})"
        for component in range(4):
            curve = joint.driver_add("rotation_quaternion", component)
            driver = curve.driver
            driver.type = "SCRIPTED"
            properties = (
                ("wind", control, "windAngleRad"),
                ("s", control, "windStrength"),
                ("scale", control, "motionScale"),
                ("period", control, "periodSeconds"),
                ("fps", control, "clockFps"),
                ("phase", rig, "phaseRad"),
                ("response", rig, "response"),
                ("yaw", rig, "instanceYawRad"),
            )
            for variable_name, obj, prop in properties:
                v = driver.variables.new()
                v.name = variable_name
                v.type = "SINGLE_PROP"
                v.targets[0].id = obj
                v.targets[0].data_path = f'["{prop}"]'
            if component == 0:
                driver.expression = f"cos{half_angle}"
            else:
                i = component - 1
                driver.expression = (
                    f"(({axis_sin[i]:.7f})*sin(wind-yaw)+"
                    f"({axis_cos[i]:.7f})*cos(wind-yaw))*sin{half_angle}"
                )
            require(driver.is_simple_expression, name)


def instance(source, group, position, yaw, scale, index, controller, rng):
    template, base_rig = source
    rig = base_rig.copy()
    rig.name = f"{template.name} | wind rig {index:03}"
    group.objects.link(rig)
    item = template.copy()
    item.name = f"{template.name} | {index:03}"
    group.objects.link(item)
    item.parent = rig
    for modifier in item.modifiers:
        if modifier.type == "ARMATURE":
            modifier.object = rig
    rig.location = position
    rig.rotation_euler = (0, 0, yaw)
    rig.scale = (scale,) * 3
    simple_property(rig, "phaseRad", rng.uniform(0, math.tau), 0.0, math.tau, "Per-instance phase")
    simple_property(rig, "response", rng.uniform(.86, 1.0), 0.0, 1.0, "Per-instance compliance")
    simple_property(rig, "instanceYawRad", yaw, -math.pi, math.pi, "Match instance Z rotation at setup")
    add_wind_drivers(rig, controller)
    return item


def review_context(studio, group, wetland, bird, stage):
    flat, shore = wetland["Flat"], wetland["Shore"]
    for i in range(-3, 2):
        for j in range(-1, 7):
            model = flat if i < 1 else shore
            studio["obj"](group, f"Terrain | {i},{j}", model.data, (i * 10, j * 10, 0))
    ink = studio["paint"]
    water = ink("Review | muted river water", "829FA3" if stage == "S3" else "95ADAB")
    studio["rectangle"](group, "Water outside shore", 7.4, 160, -50, 210, -.21, water)
    studio["rectangle"](group, "Background under terrain", -160, 160, -50, 210, -.82,
                         ink("Review | distant bank", "B9C2AF"))
    mesh = studio["obj"](group, "CHR-001 | fixed camera scale reference", bird.data,
                          (0, 0, 8 / GAME_UNITS_PER_BU))
    mesh["authoring_body_length_BU"] = .9900


def make_stage(stage, studio, prototypes, wetland, bird):
    scene = scene_setup(f"FX-007 | {stage} {STAGES[stage]['review']}")
    group = studio["collection"]("01 | Wind preset controls and placed instances", scene.collection)
    context = studio["collection"]("02 | Scale reference and review terrain", scene.collection)
    controller = cue_control(studio, stage, scene, group)
    review_context(studio, context, wetland, bird, stage)
    rng = random.Random(704 + int(stage[-1]))
    plants = []
    # A clear center corridor gives a stable scale reference and separates the silhouette from the banks.
    for x_bounds in ((-4.1, -2.15), (2.1, 5.0)):
        for row in range(13):
            for j in range(3):
                x = rng.uniform(*x_bounds)
                y = -.85 + row*1.10 + rng.uniform(-.30, .30)
                name = REEDS[(row + j*2 + len(plants) % 4) % len(REEDS)]
                plants.append(instance(prototypes[name], group, (x, y, 0), rng.uniform(-math.pi, math.pi),
                                       rng.uniform(.84, 1.15), len(plants), controller, rng))
    for i, (x, y) in enumerate(((-3.7, 2.2), (4.55, 4.75), (-5.25, 7.2), (4.97, 10.1),
                                 (-3.82, 12.5), (4.7, 14.6), (-4.7, 16.9), (5.4, 19.2))):
        plants.append(instance(prototypes[TREES[i % 3]], group, (x, y, 0),
                               rng.uniform(-math.pi, math.pi), rng.uniform(.86, 1.13),
                               len(plants), controller, rng))
    lighting = studio["studio"](scene, scene.collection)
    cam = studio["camera"](lighting, "Fixed rear | 180 GU, 0.48 rad, vertical 50°", (0, 0, 1), (0, 1, 0))
    studio["follow"](cam, (0, 0), FORWARD.xy)
    top = studio["camera"](lighting, "Top | wind response diagnostics", (0, 8, 34), (0, 8, 0), 23.5)
    scene.camera = cam
    scene.frame_set(1)
    return scene, controller, plants, cam, top


def make_lineup(studio, prototypes):
    scene = scene_setup("FX-007 | Individual reed and tree")
    group = studio["collection"]("01 | Single plants", scene.collection)
    lights = studio["studio"](scene, scene.collection)
    control = cue_control(studio, "S3", scene, group)
    rng = random.Random(20)
    for i, (name, x, y) in enumerate((("Reed_A_Height_M", -1.93, 0), ("Reed_C_Height_M", -.85, 0),
                                      ("RiverTree_A", .64, 0), ("LeaningTree", 2.43, 0))):
        instance(prototypes[name], group, (x, y, 0), .18 * i, 1.0, i, control, rng)
    studio["rectangle"](group, "Material neutral sample plane", -9, 9, -9, 9, -.015,
                         studio["paint"]("Material sample plane", "BCC5B5"))
    cam = studio["camera"](lights, "Oblique | individual plants", (3, -8, 3), (0, 0, 1), 6.8)
    scene.camera = cam
    return scene, cam


def place_scene(scene):
    bpy.context.window.scene = scene
    bpy.context.view_layer.update()


def render(studio, scene, cam, folder, name, frame, samples=12):
    place_scene(scene)
    scene.frame_set(frame)
    studio["render"](scene, cam, folder, name, CAMERA_SIZE, samples)


def measure_motion(stage, payload):
    scene, ctrl, plants, cam, _ = payload
    place_scene(scene)
    ctrl["motionScale"] = 0.0
    ctrl.update_tag()
    scene.frame_set(21)
    graph = bpy.context.evaluated_depsgraph_get()
    references, roots, tops, tips = {}, {}, {}, {}
    for obj in plants:
        eval_obj = obj.evaluated_get(graph)
        positions = [eval_obj.matrix_world @ v.co for v in eval_obj.data.vertices]
        references[obj.name] = positions
        root_index = obj.vertex_groups["Root"].index
        roots[obj.name] = [v.index for v in obj.data.vertices
                           if any(g.group == root_index and g.weight > .999999 for g in v.groups)]
        tops[obj.name] = max(obj.data.vertices, key=lambda v: v.co.z).index
        require(roots[obj.name], (obj.name, "missing locked base"))
        tips[obj.name] = []
    rest_error = max(
        (obj.matrix_world @ v.co - references[obj.name][v.index]).length
        for obj in plants for v in obj.data.vertices
    )
    require(rest_error < EPS, (stage, "motionScale=0 vs rest mesh", rest_error))
    off_error = 0.0
    for frame in (1, 12, 21, 28, 40, 49):
        scene.frame_set(frame)
        graph = bpy.context.evaluated_depsgraph_get()
        for obj in plants:
            actual = obj.evaluated_get(graph)
            error = max((actual.matrix_world @ v.co - references[obj.name][v.index]).length
                        for v in actual.data.vertices)
            off_error = max(error, off_error)
    ctrl["motionScale"] = 1.0
    ctrl.update_tag()
    direction = Vector((math.cos(ctrl["windAngleRad"]), math.sin(ctrl["windAngleRad"]), 0))
    root_error = 0.0
    min_direction = 1.0
    max_stretch = 0.0
    max_tip = 0.0
    cue_px = {"reed": [], "tree": []}
    pose_reference_px = {}
    for obj in plants:
        reference = world_to_camera_view(scene, cam, references[obj.name][tops[obj.name]])
        pose_reference_px[obj.name] = (reference.x * CAMERA_SIZE[0], reference.y * CAMERA_SIZE[1])
    for frame in range(1, END+1):
        scene.frame_set(frame)
        graph = bpy.context.evaluated_depsgraph_get()
        for obj in plants:
            actual = obj.evaluated_get(graph)
            moved = [actual.matrix_world @ v.co for v in actual.data.vertices]
            reference = references[obj.name]
            top_index = tops[obj.name]
            tip = moved[top_index] - reference[top_index]
            distance = tip.dot(direction)
            tips[obj.name].append(distance)
            require(distance >= -EPS, (stage, obj.name, frame, "upwind", distance))
            if tip.xy.length > .025:
                min_direction = min(min_direction, tip.xy.normalized().dot(direction.xy))
            max_tip = max(max_tip, distance)
            root_error = max(root_error, *((moved[i] - reference[i]).length for i in roots[obj.name]))
            if frame in (12, 21, 27, 33, 42, 49):
                for e in obj.data.edges:
                    a, b = e.vertices
                    before = (reference[a] - reference[b]).length
                    if before > .01:
                        max_stretch = max(max_stretch, abs((moved[a]-moved[b]).length / before - 1))
            if frame == 27:
                on_camera = world_to_camera_view(scene, cam, moved[top_index])
                a, b = pose_reference_px[obj.name]
                if .02 < on_camera.x < .98 and .02 < on_camera.y < .98 and on_camera.z > 0:
                    family = "reed" if obj.name.startswith("Reed") else "tree"
                    cue_px[family].append(math.hypot(on_camera.x * CAMERA_SIZE[0] - a,
                                                     on_camera.y * CAMERA_SIZE[1] - b))
    peak_frames = sorted({max(range(END), key=lambda i: item[i]) + 1 for item in tips.values()})
    require(root_error < EPS and off_error < EPS, (stage, root_error, off_error))
    require(min_direction > .98 and len(peak_frames) >= 8, (stage, min_direction, peak_frames))
    require(max_stretch < .50, (stage, "visible edge stretch", max_stretch))
    require(all(values for values in cue_px.values()), (stage, cue_px))
    if stage == "S3":
        require(max(cue_px["tree"]) > 4 and max(cue_px["reed"]) > 3, (stage, cue_px))
    require(all(curve.driver.is_valid for obj in plants for curve in obj.parent.animation_data.drivers),
            (stage, "driver errors"))
    scene.frame_set(27)
    return {
        "status": "pass",
        "evaluated_frames": END,
        "instance_count": len(plants),
        "skinned_reeds": len(plants)-8,
        "skinned_trees": 8,
        "root_max_delta_BU": root_error,
        "reduced_motion_max_delta_BU_across_6_frames": off_error,
        "reduced_motion_max_delta_BU_from_neutral_geometry": rest_error,
        "minimum_horizontal_downwind_dot_for_tips_over_0_025_BU": min_direction,
        "largest_downwind_tip_delta_BU": max_tip,
        "unique_peak_frames": peak_frames,
        "largest_sampled_edge_length_change_fraction_for_edges_gt_0_01_BU": max_stretch,
        "fixed_screen_tip_delta_px_at_frame_27": {
            k: {"visible_instances": len(v), "minimum": min(v), "maximum": max(v)}
            for k, v in cue_px.items()
        },
        "cue_reference": {"frame": 27, "field_onset_frame": GUST_FRAME, "fps": FPS}
        if stage == "S3" else None,
    }


def write_exports(prototypes, folder):
    for name, (mesh, rig) in prototypes.items():
        bpy.ops.object.select_all(action="DESELECT")
        rig.select_set(True)
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = rig
        path = folder / f"FX-007_{name}.glb"
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                                  use_active_scene=True, export_yup=True, export_animations=False, export_extras=True,
                                  export_leaf_bone=False)


def neutralize(scene, neutral):
    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            slot.link = "OBJECT"
            slot.material = neutral


def locate(stage):
    scene = next(s for s in bpy.data.scenes if s.name.startswith(f"FX-007 | {stage} "))
    ctrl = next(o for o in scene.objects if o.name.startswith(f"WindSwayPreset | {stage}"))
    plants = [o for o in scene.objects if o.type == "MESH" and o.parent and " | wind rig " in o.parent.name]
    top = next(o for o in scene.objects if o.name.startswith("Top |"))
    return scene, ctrl, plants, scene.camera, top


def render_proofs(studio, stages, lineup, folder, work, skip_video):
    scene, cam = lineup
    render(studio, scene, cam, folder, "preview_individual", 21)
    for stage, (scene, _, _, cam, top) in stages.items():
        render(studio, scene, cam, folder, f"preview_{stage.lower()}_fixed", 21)
        if stage == "S3":
            render(studio, scene, top, folder, "preview_s3_top", 21)
            _, ctrl, *_ = stages["S3"]
            ctrl["motionScale"] = 0.0
            ctrl.update_tag()
            render(studio, scene, cam, folder, "preview_s3_reduced", 21)
            ctrl["motionScale"] = 1.0
            ctrl.update_tag()
    if not skip_video:
        video = work / "video-frames"
        video.mkdir()
        i = 0
        for scene, _, _, cam, _ in stages.values():
            for frame in range(1, 49, 3):
                i += 1
                render(studio, scene, cam, video, f"frame{i:03}", frame, samples=6)
        subprocess.run([binary("ffmpeg"), "-v", "error", "-framerate", "8",
                        "-i", str(video / "frame%03d.png"), "-c:v", "libx264", "-preset", "fast",
                        "-crf", "18", "-pix_fmt", "yuv444p", "-movflags", "+faststart",
                        str(folder / "preview_fixed_rear.mp4")], check=True)


def prototypes_in(scene):
    return {o.name: (o, o.parent) for o in scene.objects if o.type == "MESH" and o.name in REEDS + TREES}


def verify_rig(mesh, rig, variant):
    require(rig and rig.type == "ARMATURE", variant)
    names = ("Root", "Stem", "Tip" if variant in REEDS else "Crown")
    bones = rig.data.bones
    require(set(bones.keys()) == set(names), list(bones.keys()))
    require(bones["Root"].head_local.length < EPS, variant)
    for a, b in zip(names, names[1:]):
        require(bones[b].parent == bones[a], (variant, b))
    require(all(abs(sum(g.weight for g in v.groups)-1) < EPS for v in mesh.data.vertices), variant)


def package_data(root):
    return {
        "source_scene_inputs": {asset: {"blend": str(path.relative_to(root)), "sha256": checksum}
                                for asset in SOURCE_FILES
                                for path, checksum in (verify_source(root, asset),)},
        "wind": {
            "direction": "Normalized horizontal world downwind vector. In Blender (dx,dy,0); "
                         "in RealityKit (dx,0,-dy). Map a zero vector to strength=0.",
            "strength": [0, 1],
            "motionScale": [0, 1],
            "reduceMotion": "Set motionScale=0 for a still neutral pose.",
            "periodSeconds_default": 1.75,
            "periodSeconds_range": [.35, 8.0],
            "clockSeconds": "Elapsed effect time in seconds, continuous across sample calls.",
            "phaseRad": "Stable per-instance value in [0,2pi), e.g. stable seeded random.",
            "response": "Optional per-instance amplitude in [0,1], default 1.",
            "yaw": "Inverse instance rotation transforms world downwind into plant space.",
            "root": "Root remains identity. Stem and distal joint rotate in local rest coordinates.",
            "local_bend_axis": "normalize(upLocal cross downwindLocal), then inverse joint "
                               "rest basis rotates the axis into bone-local coordinates.",
            "angleRadians": "radians(maxAngleDegrees[j]) * strength * motionScale * response * "
                            "(0.71 + 0.29*sin(2*pi*clockSeconds/periodSeconds + phaseRad - j*0.43))",
            "reed_joint_degrees": {"Stem": 14, "Tip": 20},
            "tree_joint_degrees": {"Stem": 7, "Crown": 13},
            "cueTiming": "Supply an early visual strength ramp from the runtime if needed. "
                         "The S3 preview marker at local frame 28 represents a demonstration.",
        },
        "review_defaults": STAGES,
        "fixed_camera": {"pixels": CAMERA_SIZE, "distance_game_units": 180, "pitch_rad": .48,
                         "vertical_fov_deg": 50, "target_height_game_units": 6,
                         "game_units_per_BU": GAME_UNITS_PER_BU, "beak_to_tail_BU": .9900},
    }


def binary(name):
    path = shutil.which(name)
    if not path:
        path = next((p for p in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}")
                     if Path(p).is_file()), None)
    require(path is not None, f"{name} required")
    return path


def build(root, folder, work, smoke, skip_video):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    studio = runpy.run_path(str(root / "ENV-001/v001/ENV-001_generate.py"))
    paths = {asset: verify_source(root, asset)[0] for asset in SOURCE_FILES}
    prototypes_scene = bpy.context.scene
    prototypes_scene.name = "FX-007 | Nine neutral runtime rigs"
    prototypes_scene.render.fps = FPS
    prototypes = load_prototypes(paths, studio, prototypes_scene)
    wetland = append_objects(paths["ENV-002"], ["Flat", "Shore"])
    bird = append_objects(paths["CHR-001"], ["Goose_LOD0"])["Goose_LOD0"]
    stages = {name: make_stage(name, studio, prototypes, wetland, bird) for name in STAGES}
    for stage, payload in stages.items():
        print("FX-007 measured", stage, json.dumps(measure_motion(stage, payload)), flush=True)
    if smoke:
        return
    source_scene, _, _, _, _ = stages["S3"]
    gray, _, _, gray_cam, gray_top = make_stage("S3", studio, prototypes, wetland, bird)
    gray.name = "FX-007 | Graybox controls and silhouettes"
    neutral = studio["paint"]("Graybox | mineral clay", "9AACA3")
    neutralize(gray, neutral)
    render(studio, gray, gray_cam, folder, "graybox_fixed_rear", 21, samples=10)
    render(studio, gray, gray_top, folder, "graybox_top", 21, samples=10)

    place_scene(prototypes_scene)
    write_exports(prototypes, folder)
    lineup = make_lineup(studio, prototypes)
    render_proofs(studio, stages, lineup, folder, work, skip_video)
    for scene, _, _, cam, _ in stages.values():
        place_scene(scene)
        scene.camera = cam
        scene.frame_set(21)
        scene.render.filepath = "//review.png"
        studio["set_preview_workspace"](scene, cam)
    place_scene(source_scene)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / f"{STEM}.blend"), compress=True)
    interface = package_data(root)
    save_json(folder / "wind_interface.json", interface)


def glb_data(file):
    raw = file.read_bytes()
    magic, version, total, chunk_length, chunk_type = struct.unpack_from("<4sIII4s", raw)
    require((magic, version, total, chunk_type) == (b"glTF", 2, len(raw), b"JSON"), file)
    document = json.loads(raw[20:20+chunk_length])
    blob_start = chunk_length + 20
    bin_length, bin_magic = struct.unpack_from("<I4s", raw, blob_start)
    require(bin_length + blob_start + 8 == len(raw) and bin_magic == b"BIN\x00", file)
    blob = raw[blob_start+8:]
    return document, blob


def texture_hashes(mesh):
    found = {}
    used_slots = {face.material_index for face in mesh.data.polygons}
    for index in used_slots:
        mat = mesh.data.materials[index]
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None and node.image.packed_file:
                payload = node.image.packed_file.data
                found[node.image.name] = hashlib.sha256(payload).hexdigest()
    return found


def triangle_samples(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    normals = mesh.corner_normals
    uv = mesh.uv_layers.active.data
    indices = {}
    for triangle in mesh.loop_triangles:
        records = []
        for i in triangle.loops:
            vertex = mesh.vertices[mesh.loops[i].vertex_index]
            weights = tuple(sorted((obj.vertex_groups[g.group].name, round(g.weight, 5))
                                   for g in vertex.groups if g.weight > 1e-5))
            # glTF import may split vertices at UV seams and permute whole triangles.
            co = tuple(round(x, 4) for x in obj.matrix_world @ vertex.co)
            texture_co = tuple(round(x, 4) for x in uv[i].uv)
            records.append((co, texture_co, weights, normals[i].vector.copy()))
        keys = tuple(r[:3] for r in records)
        start = min(range(3), key=lambda i: keys[i])
        order = tuple((start+i) % 3 for i in range(3))
        mat = mesh.materials[triangle.material_index].name.split(".")[0]
        key = (mat, tuple(keys[i] for i in order))
        indices.setdefault(key, []).append(tuple(records[i][-1] for i in order))
    return indices


def assert_texture_embedded(doc, blob, expected, variant):
    actual = set()
    for image in doc.get("images", []):
        view = doc["bufferViews"][image["bufferView"]]
        i = view.get("byteOffset", 0)
        actual.add(hashlib.sha256(blob[i:i+view["byteLength"]]).hexdigest())
    require(actual == set(expected.values()), (variant, "embedded PNG hashes", actual, expected))


def verify_export(folder, variant, source):
    source_mesh, source_rig = source
    verify_rig(*source, variant)
    place_scene(next(s for s in bpy.data.scenes if s.name.endswith("neutral runtime rigs")))
    topology = triangle_samples(source_mesh)
    textures = texture_hashes(source_mesh)
    require(textures, (variant, "packed source texture"))
    glb_path = folder / f"FX-007_{variant}.glb"
    doc, blob = glb_data(glb_path)
    require(len(doc["meshes"]) == 1 and len(doc["skins"]) == 1 and not doc.get("animations"),
            (variant, "neutral prototype export contents"))
    require(all({"POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"} <= set(p["attributes"])
                for p in doc["meshes"][0]["primitives"]), variant)
    require(all(mat.get("doubleSided", False) == (variant in REEDS)
                and mat.get("alphaMode", "OPAQUE") == "OPAQUE" for mat in doc["materials"]), variant)
    assert_texture_embedded(doc, blob, textures, variant)
    root_scene = bpy.context.scene
    scene = scene_setup(f"Round trip | {variant}")
    result = bpy.ops.import_scene.gltf(filepath=str(glb_path), merge_vertices=False)
    require(result == {"FINISHED"}, glb_path)
    bpy.context.view_layer.update()
    imported = next(o for o in scene.objects if o.type == "MESH")
    rig = next(o for o in scene.objects if o.type == "ARMATURE")
    verify_rig(imported, rig, variant)
    comparison = triangle_samples(imported)
    require(Counter({k: len(v) for k, v in topology.items()}) ==
            Counter({k: len(v) for k, v in comparison.items()}),
            (variant, "triangle, UV and weight identity", len(set(topology) - set(comparison)),
             len(set(comparison) - set(topology))))
    local_normals_diff = max(1 - a.dot(b) for k in topology
                             for group_a, group_b in zip(topology[k], comparison[k], strict=True)
                             for a, b in zip(group_a, group_b, strict=True))
    require(local_normals_diff < 1e-5, (variant, "normal", local_normals_diff))
    distal = source_rig["runtime_tip_joint"]
    for target in (rig, source_rig):
        target.pose.bones[distal].rotation_mode = "QUATERNION"
        axis = target.pose.bones[distal].bone.matrix_local.to_quaternion().inverted() @ Vector((0, 1, 0))
        target.pose.bones[distal].rotation_quaternion = Quaternion(axis, .13)
    scene.frame_set(1)
    graph = bpy.context.evaluated_depsgraph_get()
    posed = imported.evaluated_get(graph)
    moved = max((v.co - imported.data.vertices[v.index].co).length for v in posed.data.vertices)
    require(moved > .015, (variant, "physical driven deformation", moved))
    source_rig.pose.bones[distal].rotation_quaternion = Quaternion((1, 0, 0, 0))
    place_scene(root_scene)
    bpy.data.scenes.remove(scene)
    return {"status": "pass", "triangles": sum(map(len, topology.values())),
            "max_one_minus_normal_dot": local_normals_diff,
            "imported_max_delta_under_distal_joint_rotation_BU": moved,
            "embedded_source_textures": textures}


def check_video(folder):
    path = folder / "preview_fixed_rear.mp4"
    require(path.is_file(), path)
    args = [binary("ffprobe"), "-v", "error", "-show_streams", "-count_frames", "-of", "json", str(path)]
    streams = json.loads(subprocess.check_output(args))["streams"]
    require(len(streams) == 1 and streams[0]["codec_type"] == "video", path)
    v = streams[0]
    require((v["codec_name"], v["width"], v["height"], int(v["nb_read_frames"])) ==
            ("h264", *CAMERA_SIZE, 48), v)
    subprocess.run([binary("ffmpeg"), "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True)
    return {"status": "pass", "codec": v["codec_name"], "pixel_format": v["pix_fmt"],
            "width": v["width"], "height": v["height"], "decoded_frames": int(v["nb_read_frames"]),
            "fps": v["avg_frame_rate"], "duration_seconds": float(v["duration"]), "audio_streams": 0}


def verify_camera(payload):
    scene, _, _, cam, _ = payload
    place_scene(scene)
    desired_eye = Vector((0, -180 * math.cos(.48), 180 * math.sin(.48))) / GAME_UNITS_PER_BU
    desired_aim = (Vector((0, 0, 6 / GAME_UNITS_PER_BU)) - desired_eye).normalized()
    expected = (scene.render.resolution_x, scene.render.resolution_y)
    require(expected == CAMERA_SIZE and scene.render.resolution_percentage == 100, expected)
    require(cam.data.sensor_fit == "VERTICAL" and cam.data.type == "PERSP", cam.name)
    vertical_fov = math.degrees(2 * math.atan(cam.data.sensor_height / (2 * cam.data.lens)))
    require(abs(vertical_fov - 50) < EPS and not cam.animation_data, cam.name)
    require((cam.location - desired_eye).length < EPS, cam.name)
    actual_aim = cam.rotation_euler.to_quaternion() @ Vector((0, 0, -1))
    require((actual_aim - desired_aim).length < EPS, cam.name)


def verify(folder, work):
    require(bpy.ops.wm.open_mainfile(filepath=str(folder / f"{STEM}.blend"),
                                    use_scripts=False) == {"FINISHED"}, folder)
    require(not [x for x in bpy.data.libraries if x.filepath], "master uses external linked libraries")
    source_scene = next(s for s in bpy.data.scenes if s.name.endswith("neutral runtime rigs"))
    prototypes = prototypes_in(source_scene)
    require(set(prototypes) == set(REEDS + TREES), list(prototypes))
    stages = {stage: locate(stage) for stage in STAGES}
    for payload in stages.values():
        verify_camera(payload)
    motion = {stage: measure_motion(stage, payload) for stage, payload in stages.items()}
    require(motion["S1"]["largest_downwind_tip_delta_BU"] < motion["S5"]["largest_downwind_tip_delta_BU"] * .35,
            "headwind versus light breeze")
    roundtrip = {name: verify_export(folder, name, sample) for name, sample in prototypes.items()}
    pending = [
        "Owner art review of reed and crown elasticity in the fixed rear image",
        "USDZ export and RealityKit skin, direction and phase integration",
        "Per-zone runtime wind timing and Reduce Motion integration",
        "iPhone and iPad visual, accessibility and performance verification",
    ]
    for file in ("graybox_fixed_rear.png", "graybox_top.png", "preview_individual.png",
                 "preview_s1_fixed.png", "preview_s3_fixed.png", "preview_s5_fixed.png",
                 "preview_s3_top.png", "preview_s3_reduced.png"):
        data = (folder / file).read_bytes()
        require(data.startswith(b"\x89PNG\r\n\x1a\n") and struct.unpack_from(">II", data, 16) == CAMERA_SIZE,
                file)
    qa = {"id": "FX-007", "version": "v001", "status": "needs_review",
          "blender": bpy.app.version_string, "verification_origin": f"Independent Blender re-opened {folder}",
          "blender_reopen": "pass", "source_camera_held": "pass", "motion": motion,
          "glb_roundtrip": roundtrip, "video_decode": check_video(folder), "still_dimensions": "pass",
          "app_baseline": "Existing iPhone 18 Pro (iOS 27.2) simulator builds and 340 tests per active plan",
          "design_redline_check": "Candidate uses material and geometry response only. No status UI, audio, "
                                   "urgent flash, red warning design or device performance claims.",
          "pending": pending}
    save_json(work / "qa.json", qa)


def main():
    argv = sys.argv[sys.argv.index("--")+1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="empty output folder for generation or verification JSON")
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--work", type=Path, help="independent scratch output directory")
    parser.add_argument("--verify", type=Path, help="directory containing the delivered asset")
    parser.add_argument("--export-only", type=Path, help="re-export the nine neutral rigs from an existing master")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--skip-video", action="store_true")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    require(not list(output.iterdir()), f"Choose an empty directory: {output}")
    if args.verify:
        verify(args.verify.resolve(), output)
    elif args.export_only:
        bpy.ops.wm.open_mainfile(filepath=str(args.export_only.resolve()), use_scripts=False)
        source_scene = next(s for s in bpy.data.scenes if s.name.endswith("neutral runtime rigs"))
        place_scene(source_scene)
        write_exports(prototypes_in(source_scene), output)
    else:
        scratch = args.work.resolve() if args.work else output.with_name(output.name + "-scratch")
        scratch.mkdir(exist_ok=True)
        build(args.source_root.resolve(), output, scratch, args.smoke, args.skip_video)


if __name__ == "__main__":
    main()
