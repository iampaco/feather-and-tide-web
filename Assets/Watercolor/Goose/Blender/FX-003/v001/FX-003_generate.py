"""Derive FX-003 from FX-001; build, independently verify, and seal a delivery."""

import argparse
from hashlib import sha256
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np

ID = "FX-003"
BLEND = "FX-003_Headwind.blend"
GLB = "FX-003_Headwind.glb"
VIDEO = "preview_fixed_rear_comparison.mp4"
TEXTURE = "textures/ft_goose_fx_headwind_rgba.png"
SOURCE = Path(__file__).resolve()
UP = "FX-001"
UP_SCRIPT = "FX-001_generate.py"
LONG = "FX-001_WindTail_Long.glb"
SHORT = "FX-001_WindTail_Short.glb"
TAIL_TEXTURE = "textures/ft_goose_fx_wind_tail_long_rgba.png"
CRUISE = "ANM-001_cruise_flap.glb"
BU = .036
FPS = 12
COMPARE_FRAMES = 36
SIZE = (852, 393)
UPSTREAM_LENGTH = 2.8
PERIOD = 16.0
MIN_Y = -1.3
LEADER_LIFT = 8 * BU
LEAD_SPEED = .53
# X, starting upstream Y, and altitude. Off-axis lanes leave the center opening clear.
PLACEMENTS = ((-3.60, 1.3, .17), (3.72, 2.5, .15), (-4.40, 5.2, .10), (4.65, 7.1, .12),
              (-3.86, 9.1, .16), (3.66, 11.2, .17), (-5.65, 13.1, .09), (5.35, .18, .09),
              (-5.25, 6.8, .11), (5.30, 10.4, .10), (-4.65, 14.2, .12), (4.20, 5.05, .14))
PRESETS = {"Headwind": (math.pi, 2.55, 12), "WindTail": (0., 1.32, 8)}
CONTROL = "Wind | editable preview controls"
EXIT = "Review | clear wetland opening"
PENDING = [
    "负责人以静音盲看复核约 3 秒内的正反风向辨识、冷灰金风线、水彩观感和终点引导。",
    "USDZ、RealityKit 和 App 接入，包括真实引擎风场、结阵、透明排序、减弱选项以及终点与雁投影遮挡测试。",
    "能耗、补给、安全补救和通关条件由运行时判定。iPhone / iPad 真机待验。"
]


def require(condition, evidence):
    if not condition:
        raise ValueError(str(evidence))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read(path):
    return json.loads(path.read_text())


def upstream_module(library):
    fx_folder = library / UP / "v001"
    manifest = read(fx_folder / "asset_manifest.json")
    qa = read(fx_folder / "qa.json")
    require(manifest["status"] == qa["status"] == "needs_review" and
            qa["independent_artifact_directory_reopen"]["status"] == "pass", "FX-001 QA")
    inputs = (UP_SCRIPT, LONG, SHORT, TAIL_TEXTURE,
              "textures/ft_goose_fx_wind_tail_short_rgba.png")
    for relative in ("README.md", "qa.json", "FX-001_WindTail.blend", *inputs):
        require(digest(fx_folder / relative) == manifest["files"][relative], relative)
    cruise_folder = library / "ANM-001" / "v001"
    cruise = read(cruise_folder / "asset_manifest.json")
    require(read(cruise_folder / "qa.json")["status"] == cruise["status"] == "done" and
            digest(cruise_folder / CRUISE) == cruise["files"][CRUISE], "ANM-001 QA")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("fx001_generator", fx_folder / UP_SCRIPT)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    camera = core.check_sources(library)
    snapshots = {f"{UP}/v001/{relative}": digest(fx_folder / relative) for relative in
                 (*inputs, "README.md", "asset_manifest.json", "qa.json", "FX-001_WindTail.blend")}
    snapshots.update({f"ANM-001/v001/{CRUISE}": digest(cruise_folder / CRUISE),
                      f"{core.MAT}/{core.WATER}": digest(library / core.MAT / core.WATER)})
    return core, snapshots, camera


def mesh_signature(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    uv = mesh.uv_layers.active
    return sorted(
        tuple(sorted(tuple(round(n, 6) for n in (*mesh.vertices[mesh.loops[i].vertex_index].co,
                                                  *uv.data[i].uv)) for i in tri.loops))
        for tri in mesh.loop_triangles
    )


def import_one(core, path):
    objects = core.from_glb(path)
    require(len(objects) == 1, [(obj.name, obj.type) for obj in objects])
    obj = objects.pop()
    require(obj.type == "MESH", obj.name)
    return obj


def make_headwind(core, output, export_group, long):
    source_image = next(node.image for node in long.data.materials[0].node_tree.nodes
                        if node.type == "TEX_IMAGE")
    source = core.image_rows(source_image)
    # Keep FX-001's longitudinal fade, paper grain and downstream opacity peak.
    pigment = (source[:, :, 1] - np.median(source[:, :, 1])) * 255
    rgba = np.empty(source.shape, dtype=np.uint8)
    rgba[:, :, :3] = np.rint(np.clip(np.array([214, 212, 189]) + pigment[:, :, None], 0, 255))
    rgba[:, :, 3] = np.rint(source[:, :, 3] * 255 * .93)
    path = output / TEXTURE
    path.parent.mkdir()
    core.write_rgba(path, rgba)
    image = bpy.data.images.load(str(path), check_existing=False)
    image.alpha_mode = "STRAIGHT"
    image.pack()
    image.filepath = "//" + TEXTURE
    material = core.ribbon_material("Headwind | cold gray gold paper", image)
    material.asset_mark()
    mesh = long.data.copy()
    mesh.name = "Headwind | inherited WindTail_Long geometry"
    mesh.materials.clear()
    mesh.materials.append(material)
    obj = bpy.data.objects.new("Headwind", mesh)
    export_group.objects.link(obj)
    for name in ("axis_forward", "axis_up", "length_BU", "width_BU", "uv_contract"):
        obj[name] = long[name]
    obj["reverse_axis_turn_rad"] = math.pi
    obj["wind_controller"] = "FX-001 compatible"
    obj.asset_mark()
    obj.asset_data.description = "FX-003; align +Y to world wind and keep source U increasing downstream."
    require(mesh_signature(obj) == mesh_signature(long), "inherited geometry and UV signature")
    return obj


def scene_presets(scene, preset):
    ctrl = scene.objects[CONTROL]
    bearing, speed, density = PRESETS[preset]
    ctrl["windBearingRad"] = bearing
    ctrl["windSpeedBUPerSecond"] = speed
    ctrl["opacityMultiplier"] = 1.
    ctrl.update_tag()
    bpy.data.collections["Review | headwind instance lanes"].hide_render = preset != "Headwind"
    bpy.data.collections["Review | S1 tailwind control lanes"].hide_render = preset != "WindTail"
    scene.frame_set(scene.frame_current)
    return density


def lanes(core, group, objs, control, headwind):
    count = PRESETS["Headwind" if headwind else "WindTail"][2]
    rows = []
    for i, (x, y, z) in enumerate(PLACEMENTS[:count]):
        source = objs[0] if headwind or i % 2 == 0 else objs[1]
        obj = bpy.data.objects.new(f'{"Headwind" if headwind else "WindTail"} Stroke {i+1:02}', source.data)
        group.objects.link(obj)
        obj["phaseOffsetBU"] = 0.
        obj["length_BU"] = source["length_BU"]
        obj["worldAnchorBU"] = (x, y, z)
        direction = ("bearing", control, "windBearingRad")
        speed = ("speed", control, "windSpeedBUPerSecond")
        offset = ("offset", obj, "phaseOffsetBU")
        core.driver(obj, "rotation_euler", 2, "bearing", [direction])
        travel = f"(offset+speed*(frame-1)/{FPS})"
        core.driver(obj, "location", 0, f"{x}-sin(bearing)*{travel}", [direction, speed, offset])
        core.driver(obj, "location", 1,
                    f"{MIN_Y}+(({y - MIN_Y}+cos(bearing)*{travel})%{PERIOD})",
                    [direction, speed, offset])
        obj.location.z = z
        obj.material_slots[0].link = "OBJECT"
        review = core.review_material(source.data.materials[0], control)
        review.name += f" | {i+1:02}"
        node = next(node for node in review.node_tree.nodes if node.type == "MATH")
        control_location_driver(node, obj, control, MIN_Y)
        obj.material_slots[0].material = review
        rows.append(obj)
    return rows


def control_location_driver(node, obj, control, min_y):
    pin = node.inputs[1]
    pin.driver_remove("default_value")
    driver = pin.driver_add("default_value").driver
    for name, target, path in (("y", obj, "location.y"),
                               ("opacity", control, '["opacityMultiplier"]')):
        variable = driver.variables.new()
        variable.name = name
        variable.targets[0].id = target
        variable.targets[0].data_path = path
    driver.expression = (f"opacity*min(1,max(0,(y-{min_y})/0.9),"
                         f"max(0,({min_y + PERIOD}-y)/0.9))")
    return driver


def new_landmark(core, group, material):
    # Low silhouettes frame an outlet made of the shallow-water wash.
    for side in (-1, 1):
        vertices = [(side * x, y, z) for x, y, z in (
            (1.88, 13.5, .02), (4.5, 11.3, .02), (11, 16, .02), (12, 24, .02),
            (1.95, 22, .02), (4.95, 17.2, .71), (8, 19.2, 1.37))]
        faces = [(0, 1, 5), (1, 2, 5), (2, 6, 5), (2, 3, 6), (3, 4, 6), (4, 0, 5), (4, 5, 6)]
        lowland = core.basic_mesh(group, f"Review | {'west' if side < 0 else 'east'} shoulder",
                                 vertices, faces, [(0, 0)] * len(vertices), material)
        lowland["purpose"] = "review-only terminal silhouette"
    points = [(.88 * math.cos(i * math.tau / 40), 16.5 + 1.3 * math.sin(i * math.tau / 40), .014)
              for i in range(40)]
    marker = core.basic_mesh(group, EXIT, points, [list(range(40))], [(0, 0)] * 40,
                             core.flat_material("Review | clear green-gray water", (.53, .65, .49)))
    marker["purpose"] = "terminal visibility witness only; use LVL-S5 layout for game"


def export(core, scene, output, obj):
    scene.frame_set(1)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    result = bpy.ops.export_scene.gltf(filepath=str(output / GLB), use_selection=True,
        use_active_scene=True, export_extras=True, export_yup=True, export_animations=False,
        export_apply=False, export_image_format="AUTO")
    require(result == {"FINISHED"}, GLB)
    obj.hide_set(True)
    obj.hide_render = True


def set_frame(scene, frame):
    whole = math.floor(frame)
    scene.frame_set(whole, subframe=frame - whole)


def projection(scene, obj, points):
    values = [world_to_camera_view(scene, scene.camera, obj.matrix_world @ point)
              for point in points]
    return np.array([(v.x, v.y, v.z) for v in values])


def box(values):
    return np.min(values[:, :2], axis=0), np.max(values[:, :2], axis=0)


def box_gap(a, b):
    low, high = a
    low_b, high_b = b
    gap = np.maximum(np.maximum(low - high_b, low_b - high), 0)
    return float(np.linalg.norm(gap * SIZE))


def measure(scene, core):
    summary = {}
    for preset in PRESETS:
        count = scene_presets(scene, preset)
        strokes = sorted([obj for obj in scene.objects if obj.name.startswith(f"{preset} Stroke ")],
                         key=lambda obj: obj.name)
        require(len(strokes) == count, (preset, len(strokes)))
        birds = sorted([obj for obj in scene.objects if obj.name.startswith("Review Bird ")],
                       key=lambda obj: obj.name)
        require(len(birds) == 12, "Review flock")
        signed_speed = PRESETS[preset][1] * (1 if preset == "WindTail" else -1)
        gap_lead = gap_exit = math.inf
        old = old_screen = None
        screen_delta = []
        velocity_error = 0.
        projected_shares = []
        for half in range(2 * COMPARE_FRAMES - 1):
            frame = 1 + half / 2
            set_frame(scene, frame)
            deps = bpy.context.evaluated_depsgraph_get()
            camera = scene.camera.evaluated_get(deps)
            rig = birds[0].parent.evaluated_get(deps)
            lift = rig.matrix_world.translation.z
            target = Vector((0, rig.matrix_world.translation.y, lift + 6 * BU))
            eye = target + Vector((0, -180 * BU * math.cos(.48), (180 * math.sin(.48) - 6) * BU))
            require((camera.matrix_world.translation - eye).length < 1e-5, (frame, camera.location, eye))
            require(((camera.matrix_world.to_3x3() @ Vector((0, 0, -1))) -
                     (target - eye).normalized()).length < 1e-5, frame)
            require(abs(2 * math.atan(camera.data.sensor_height / (2 * camera.data.lens)) -
                        math.radians(50)) < 1e-6, frame)
            exit_object = scene.objects[EXIT].evaluated_get(deps)
            exit_verts = projection(scene, exit_object, [vertex.co for vertex in exit_object.data.vertices])
            require(np.all((exit_verts[:, :2] > 0) & (exit_verts[:, :2] < 1)), ("exit", frame))
            lead = birds[0].evaluated_get(deps)
            lead_box = box(projection(scene, lead, [Vector(point) for point in lead.bound_box]))
            lead_low, lead_high = lead_box
            require(np.all(lead_low > 0) and np.all(lead_high < 1), ("lead", frame))
            positions = []
            screen_positions = []
            visible = []
            for stroke in strokes:
                evaluated = stroke.evaluated_get(deps)
                pose = evaluated.matrix_world
                forward = pose.to_3x3() @ Vector((0, 1, 0))
                require((forward - Vector((0, math.copysign(1, signed_speed), 0))).length < 1e-5 and
                        tuple(evaluated.scale) == (1., 1., 1.), (stroke.name, forward))
                points = projection(scene, evaluated, [vertex.co for vertex in evaluated.data.vertices])
                stroke_box = box(points)
                gap_lead = min(gap_lead, box_gap(lead_box, stroke_box))
                gap_exit = min(gap_exit, box_gap(box(exit_verts), stroke_box))
                positions.append(pose.translation.y)
                marker = projection(scene, evaluated, [Vector((0, .65 * stroke["length_BU"], 0))])[0]
                screen_positions.append(marker[1] * SIZE[1])
                visible.append(bool(np.all((0 < marker[:2]) & (marker[:2] < 1))))
            positions = np.array(positions)
            screen_positions = np.array(screen_positions)
            projected_shares.append(sum(visible))
            if old is not None:
                delta = positions - old
                normal = np.abs(delta) < PERIOD / 2
                velocity_error = max(velocity_error, float(np.max(np.abs(delta[normal] * 2 * FPS -
                                                                         signed_speed))))
                screen_delta.extend((screen_positions - old_screen)[normal & visible].tolist())
            old, old_screen = positions, screen_positions
        require(velocity_error < .001 and gap_lead > 10 and gap_exit > 10 and min(projected_shares) >= 3,
                (preset, velocity_error, gap_lead, gap_exit, min(projected_shares)))
        require(screen_delta and np.median(screen_delta) * signed_speed > 0,
                (preset, float(np.median(screen_delta))))
        summary[preset] = {"half_frames": 2 * COMPARE_FRAMES - 1, "lanes": count,
            "min_in_frame_downstream_witnesses": min(projected_shares),
            "signed_world_velocity_BU_s": signed_speed, "max_world_velocity_error_BU_s": velocity_error,
            "median_screen_y_bottom_up_px_per_half_frame": float(np.median(screen_delta)),
            "min_leader_projected_box_gap_px": gap_lead, "min_exit_projected_box_gap_px": gap_exit}
    scene_presets(scene, "Headwind")
    return summary


def materials_for(core, scene, group, library):
    water = core.master_materials(library)["WaterFallback"]
    for obj in tuple(group.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    core.build_ground(group, water)
    new_landmark(core, group, core.flat_material("Review | muted slate banks", (.145, .252, .239)))


def video_check(path):
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True)
    spec = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames",
        "-show_entries", "stream=width,height,duration,codec_name,codec_type,nb_read_frames",
        "-of", "json", str(path)]))["streams"]
    require(spec == [{"codec_name": "h264", "codec_type": "video", "width": 852, "height": 394,
                     "duration": "6.000000", "nb_read_frames": "72"}], spec)
    return {"status": "pass", "decoded_frames": 72, "audio_streams": 0,
            "source_size": SIZE, "encoded_size": [852, 394], "fps": FPS,
            "tailwind_seconds": [0, 3], "headwind_seconds": [3, 6]}


def make_video(core, scene, output):
    sequence = output / "sequence"
    sequence.mkdir()
    scene.eevee.taa_render_samples = 8
    core.change_camera(scene, core.REAR)
    for i, preset in enumerate(("WindTail", "Headwind")):
        scene_presets(scene, preset)
        for j in range(COMPARE_FRAMES):
            scene.frame_set(j + 1)
            core.render(scene, sequence / f"frame_{i * COMPARE_FRAMES + j:03}.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-start_number", "0",
        "-i", str(sequence / "frame_%03d.png"), "-vf", "pad=852:394:0:0", "-c:v", "libx264",
        "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output / VIDEO)], check=True)
    shutil.rmtree(sequence)
    return video_check(output / VIDEO)


def build(output, library, quick):
    core, snapshots, camera = upstream_module(library)
    scene = core.reset_scene()
    scene.name = "FX-003 | Same fixed camera, opposite wind"
    scene.frame_end = COMPARE_FRAMES
    group = core.collection(scene, "Delivery | reusable Headwind")
    ground = core.collection(scene, "Review | paired valley and terminal")
    cameras = core.collection(scene, "Review | cameras and controls")
    flock = core.collection(scene, "Review | 12 geese")
    head_lanes = core.collection(scene, "Review | headwind instance lanes")
    tail_lanes = core.collection(scene, "Review | S1 tailwind control lanes")
    core.light(cameras)
    rear = core.camera(cameras, core.REAR, (0, -180 * BU * math.cos(.48), LEADER_LIFT + 180 * BU * math.sin(.48)),
                       (0, 0, LEADER_LIFT + 6 * BU))
    core.camera(cameras, core.TOP, (0, 7, 26), (0, 7, 0), ortho=22)
    ctrl = core.make_controls(cameras, scene)
    ctrl.animation_data_clear()
    ctrl["formationWeight"] = 1.
    ctrl["reviewFlightBUPerSecond"] = LEAD_SPEED
    ctrl["flowDescription"] = "Positive bearing around +Z rotates +Y toward -X. Presets are in wind_interface.json."
    scene.timeline_markers.clear()
    for frame, label in ((1, "First paired frame"), (13, "1 sec"), (25, "2 sec"), (36, "End of paired sample")):
        scene.timeline_markers.new(label, frame=frame)
    flight, _ = core.preview_birds(scene, flock, library, ctrl)
    rear.parent = flight
    core.build_ground(ground)
    new_landmark(core, ground, core.flat_material("Graybox | low valley walls", (.21, .24, .24)))
    fx_folder = library / UP / "v001"
    source_long = import_one(core, fx_folder / LONG)
    source_short = import_one(core, fx_folder / SHORT)
    head = make_headwind(core, output, group, source_long)
    head_strokes = lanes(core, head_lanes, (head,), ctrl, True)
    lanes(core, tail_lanes, (source_long, source_short), ctrl, False)
    gray_mat = core.flat_material("Graybox | wind strip envelope", (.61, .64, .63))
    head_materials = [obj.material_slots[0].material for obj in head_strokes]
    for obj in head_strokes:
        obj.material_slots[0].material = gray_mat
    for obj in (source_long, source_short, head):
        obj.hide_set(True)
        obj.hide_render = True
    scene_presets(scene, "Headwind")
    frame = 13
    scene.frame_set(frame)
    core.change_camera(scene, core.REAR)
    core.render(scene, output / "graybox_fixed_rear.png")
    core.change_camera(scene, core.TOP, (900, 940))
    core.render(scene, output / "graybox_top.png")
    for obj, material in zip(head_strokes, head_materials):
        obj.material_slots[0].material = material
    materials_for(core, scene, ground, library)
    head.hide_set(False)
    head.hide_render = False
    export(core, scene, output, head)
    core.change_camera(scene, core.REAR)
    motion = measure(scene, core)
    for preset, file in (("Headwind", "preview_fixed_rear_headwind.png"), ("WindTail", "comparison_s1_tailwind.png")):
        scene_presets(scene, preset)
        scene.frame_set(frame)
        core.render(scene, output / file)
    scene_presets(scene, "Headwind")
    scene.frame_set(frame)
    ctrl["opacityMultiplier"] = .38
    ctrl.update_tag()
    scene.frame_set(frame)
    core.render(scene, output / "preview_fixed_rear_reduced.png")
    bpy.data.collections["Review | headwind instance lanes"].hide_render = True
    core.render(scene, output / "comparison_without_fx.png")
    scene_presets(scene, "Headwind")
    contrast = {}
    for name in ("preview_fixed_rear_headwind.png", "comparison_s1_tailwind.png", "preview_fixed_rear_reduced.png"):
        contrast[name] = core.image_diff(output / name, output / "comparison_without_fx.png")
    require(contrast["preview_fixed_rear_headwind.png"]["pixels_at_least_threshold"] > 150 and
            contrast["comparison_s1_tailwind.png"]["pixels_at_least_threshold"] > 120 and
            0 < contrast["preview_fixed_rear_reduced.png"]["mean_abs_rgb8"] <
            contrast["preview_fixed_rear_headwind.png"]["mean_abs_rgb8"], contrast)
    core.change_camera(scene, core.TOP, (900, 940))
    core.render(scene, output / "preview_top.png")
    core.change_camera(scene, core.REAR)
    bpy.ops.object.select_all(action="DESELECT")
    ctrl.select_set(True)
    bpy.context.view_layer.objects.active = ctrl
    scene.render.filepath = "//"
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / BLEND), compress=True)
    video = {"status": "not_run"} if quick else make_video(core, scene, output)
    interface = {"id": ID, "version": "v001", "status": "needs_review",
        "variant": "Headwind", "coordinates": {"blender": "+Y forward, +Z up", "glb": "-Z forward, +Y up",
          "conversion": "(x,z,-y)", "BU_per_game_unit": BU},
        "geometry": {"file": GLB, "origin": "upstream center", "length_BU": UPSTREAM_LENGTH,
                     "nominal_width_BU": .18, "uv": "U=0 upstream, U=1 downstream; V=0 left, V=1 right",
                     "triangles": 72, "node": "Headwind", "local_transform": "identity"},
        "runtime_inputs": {
          "worldPosition": "World-space upstream placement in BU.",
          "worldWindDirection": "Normalized finite horizontal vector pointing downstream. Use no instances at zero wind.",
          "windSpeedBUPerSecond": "Nonnegative. Use runtime wind magnitude, independent from gameplay consumption.",
          "elapsedSeconds": "Monotonic seconds.",
          "phaseOffsetBU": "Per-instance downstream phase distance in BU.",
          "formationWeight": "0…1 optional inherited FX-001 alignment. Review uses 1, i.e. parallel wind.",
          "opacityMultiplier": "0…1 applied to straight alpha. Feather edges or recycle.",
          "windBearingRad": "Blender preview yaw of the wind, rad. Common practice: π to reverse around the up axis.",
          "alignment": "Rotate local forward toward world wind; for S5 flying +Y, yaw π about Blender +Z (GLB +Y) for -Y wind. Keep unit positive scale and unchanged UV.",
          "travel": "worldPosition + worldWindDirection * (windSpeedBUPerSecond * elapsedSeconds + phaseOffsetBU)",
          "tile_and_visibility": "Tile with 2.8 BU repetition along wind, at transparent endpoints. Fade instances at the review strip's recycle bounds or supply a runtime envelope. Reserve the central terminal and projected bird silhouette.",
          "export_animation": "Static GLB. Mother file supplies a Blender review timeline, and the engine supplies final advection."},
        "comparison": {"same_camera": True, "camera_distance_game_units": 180, "camera_pitch_rad": .48,
            "vertical_FOV_deg": 50, "targetHeightAboveLeader_game_units": 6, "leader_height_game_units": 8,
            "S1_reference": {"bearing_rad": 0, "speed_BU_s": 1.32, "lanes": 8},
            "S5_review": {"bearing_rad": math.pi, "speed_BU_s": 2.55, "lanes": 12},
            "flight_speed_BU_s": LEAD_SPEED, "source_frame_px": SIZE}}
    dump(output / "wind_interface.json", interface)
    dump(output / "qa.json", {"id": ID, "version": "v001", "status": "needs_review",
        "preview_motion": motion, "fixed_view_effect_vs_off": contrast, "video_build": video,
        "redline_check": "参照项目清单。灰金风纹与可见清水开口，静音。无计分、警报、伤亡、强推文本或现实生态数字。",
        "pending": PENDING,
        "app_baseline_reference": "goose-preview-model-cleanup active 计划中的 iOS 27.2 模拟器构建和 340 项测试；本次为 Blender 资产制作。"})
    dump(output / "asset_manifest.json", {"id": ID, "version": "v001", "status": "needs_review",
        "variant": "Headwind", "specification_pdf_page": 14, "execution_order_1_based": 32,
        "blender": bpy.app.version_string, "dependencies": {"FX-001": "v001 needs_review, independently rechecked"},
        "review_only_dependencies": {"ANM-001": "v001 done", "MAT-001": "v001 done"},
        "source_files_relative_to_Blender_library": snapshots,
        "camera_sources": {core.CAMERA: camera["camera"], core.PLAYFIELD: camera["playfield"]},
        "runtime_export": {"blend": BLEND, "glb": GLB, "texture": TEXTURE, "inputs": "wind_interface.json"},
        "sources_and_rights": "本项目 FX-001/v001 原创流线与授权纸纹派生，ANM-001 巡航与 MAT-001 水样仅供审阅。无新增外部来源或署名。",
        "pending": PENDING})
    shutil.copy2(SOURCE, output / SOURCE.name)


def verify(output, folder, library, quick):
    core, snapshots, _ = upstream_module(library)
    manifest = read(folder / "asset_manifest.json")
    require(manifest["source_files_relative_to_Blender_library"] == snapshots, "dependency hashes")
    for name, expected in manifest.get("files", {}).items():
        require(digest(folder / name) == expected, name)
    bpy.ops.wm.open_mainfile(filepath=str(folder / BLEND))
    scene = bpy.context.scene
    head = scene.objects["Headwind"]
    require(tuple(head.location) == (0., 0., 0.) and tuple(head.rotation_euler) == (0., 0., 0.) and
            tuple(head.scale) == (1., 1., 1.), "local pivot and orientation")
    core.geometry_check(head, "Headwind", core.SPECS["WindTail_Long"])
    signature = mesh_signature(head)
    original = next(obj for obj in scene.objects if obj.name == "WindTail_Long")
    source_alpha_image = next(node.image for node in original.data.materials[0].node_tree.nodes
                              if node.type == "TEX_IMAGE")
    source_alpha = core.image_rows(source_alpha_image)[:, :, 3].copy()
    require(signature == mesh_signature(original), "identical mesh and UV")
    motion = measure(scene, core)
    core.change_camera(scene, core.REAR)
    scene.frame_set(13)
    core.render(scene, output / "reopened_fixed_rear.png")
    reopened = core.image_diff(folder / "preview_fixed_rear_headwind.png", output / "reopened_fixed_rear.png")
    require(reopened["mean_abs_rgb8"] < .4, reopened)
    doc, binary = core.read_glb(folder / GLB)
    require(len(doc["meshes"]) == len(doc["nodes"]) == len(doc["images"]) == len(doc["materials"]) == 1 and
            not doc.get("cameras") and not doc.get("animations"), doc.keys())
    node = doc["nodes"][0]
    require(node["name"] == "Headwind" and not node.keys() & {"rotation", "translation", "scale", "matrix"}, node)
    attrs = doc["meshes"][0]["primitives"][0]["attributes"]
    xyz = doc["accessors"][attrs["POSITION"]]
    require(abs(xyz["min"][2] + UPSTREAM_LENGTH) < 1e-5 and xyz["max"][2] < 1e-5 and
            max(abs(xyz["min"][1]), abs(xyz["max"][1])) < 1e-5, xyz)
    mat = doc["materials"][0]
    require(mat["alphaMode"] == "BLEND" and mat["doubleSided"], mat)
    require(all(s["wrapS"] == s["wrapT"] == 33071 for s in doc["samplers"]), doc["samplers"])
    uv = doc["accessors"][attrs["TEXCOORD_0"]]
    require(uv["count"] == xyz["count"], uv)
    view = doc["bufferViews"][doc["images"][0]["bufferView"]]
    offset = view.get("byteOffset", 0)
    packed = binary[offset:offset + view["byteLength"]]
    require(packed == (folder / TEXTURE).read_bytes(), "lossless embedded cold-gray gold texture")
    # Swap all review lanes to the clean GLB import, retaining independent runtime drivers.
    for obj in [obj for obj in scene.objects if obj.name.startswith("Headwind Stroke ")]:
        obj.material_slots[0].link = "DATA"
    bpy.data.objects.remove(head, do_unlink=True)
    imported = import_one(core, folder / GLB)
    geo = core.geometry_check(imported, "Headwind", core.SPECS["WindTail_Long"])
    require(mesh_signature(imported) == signature, "roundtrip geometry+UV signature")
    image = next(node.image for node in imported.data.materials[0].node_tree.nodes if node.type == "TEX_IMAGE")
    alpha = core.image_rows(image)[:, :, 3]
    error = float(np.max(np.abs(alpha - source_alpha * .93)))
    require(error <= .51 / 255 and not np.any(alpha[[0, -1], :]) and
            not np.any(alpha[:, [0, -1]]) and (0 < alpha.max() < .38), error)
    for obj in [obj for obj in scene.objects if obj.name.startswith("Headwind Stroke ")]:
        obj.data = imported.data
        obj.material_slots[0].link = "OBJECT"
        ctrl = scene.objects[CONTROL]
        review = core.review_material(imported.data.materials[0], ctrl)
        m = next(n for n in review.node_tree.nodes if n.type == "MATH")
        control_location_driver(m, obj, ctrl, MIN_Y)
        obj.material_slots[0].material = review
    imported.hide_render = True
    imported.hide_set(True)
    roundtrip_motion = measure(scene, core)
    scene.frame_set(13)
    core.render(scene, output / "roundtrip_fixed_rear.png")
    render_diff = core.image_diff(output / "reopened_fixed_rear.png", output / "roundtrip_fixed_rear.png")
    require(render_diff["mean_abs_rgb8"] < .7, render_diff)
    video = {"status": "not_run"} if quick else video_check(folder / VIDEO)
    dump(output / "independent_recheck.json", {"status": "pass" if not quick else "development_only",
        "mother_file": BLEND, "roundtrip_source": GLB, "rest_geometry": geo,
        "original_FX001_geometry_uv_exact": True, "axes": {"Blender": "+Y", "GLB": "-Z"},
        "signed_wind_check_reopened": motion, "signed_wind_check_roundtrip": roundtrip_motion,
        "texture": {"embedded_PNG_sha256": sha256(packed).hexdigest(), "peak_straight_alpha": float(alpha.max()),
                    "all_four_edges_alpha": 0, "alpha_error_vs_source_times_0_93": error,
                    "clamped_2_sided_blend": True},
        "fixed_camera_reopened_rgb8_diff": reopened, "fixed_camera_roundtrip_rgb8_diff": render_diff,
        "video_independent_decode": video})


def seal(folder, recheck):
    qa = read(folder / "qa.json")
    evidence = read(recheck / "independent_recheck.json")
    require(evidence["status"] == "pass", evidence["status"])
    qa["independent_artifact_directory_reopen"] = evidence
    shutil.copy2(recheck / "roundtrip_fixed_rear.png", folder / "roundtrip_fixed_rear.png")
    dump(folder / "qa.json", qa)
    manifest = read(folder / "asset_manifest.json")
    manifest["files"] = {p.relative_to(folder).as_posix(): digest(p) for p in sorted(folder.rglob("*"))
                         if p.is_file() and p.name not in {"asset_manifest.json", ".DS_Store"}}
    dump(folder / "asset_manifest.json", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--library", type=Path, default=SOURCE.parents[2])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", type=Path)
    mode.add_argument("--seal", type=Path)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.seal:
        seal(args.out.resolve(), args.seal.resolve())
        return
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    require(not any(out.iterdir()), f"Use an empty output directory: {out}")
    if args.verify:
        verify(out, args.verify.resolve(), args.library.resolve(), args.quick)
    else:
        build(out, args.library.resolve(), args.quick)


if __name__ == "__main__":
    main()
