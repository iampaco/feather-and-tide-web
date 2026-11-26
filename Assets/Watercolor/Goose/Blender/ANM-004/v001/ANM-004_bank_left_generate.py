"""Build Bank_L and its Blender review scenes in a new output directory."""
import argparse
import json
import math
import runpy
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
CHR = LIBRARY / "CHR-001" / "v001"
ANM = LIBRARY / "ANM-001" / "v001"
CHR_BLEND = CHR / "CHR-001_goose_rig.blend"
CHR_GLB = CHR / "CHR-001_goose_rig.glb"
CRUISE_BLEND = ANM / "ANM-001_cruise_flap.blend"
SUPPORT = LIBRARY / "ANM-003" / "v001" / "ANM-003_glide_circle_generate.py"
HELPERS = runpy.run_path(str(SUPPORT))
TOOLS, REF = HELPERS["TOOLS"], HELPERS["REF"]
TIME, EVAL, DIGEST, DUMP = (TOOLS[k] for k in ("time_set", "evaluated", "digest", "dump"))
curves, make_action, set_action, sample_action, smoothstep = (
    HELPERS[k] for k in ("curves", "make_action", "set_action", "sample_action", "smoothstep")
)

STEM, CLIP = "ANM-004_bank_left", "Bank_L"
FPS, END, BANK_DEG = 48, 25, 12
CRUISE_FRAME = 49
ENTER, HOLD, EXIT = 24, 28, 28
ENGAGE = CRUISE_FRAME
RELEASE = ENGAGE + ENTER + HOLD
RESUME = RELEASE + EXIT
REVIEW_END = 176
DELAYS = [3, 9, 5, 16, 7, 20, 12, 22, 14, 4, 18]
FLOCK_XY = TOOLS["FLOCK_POSITIONS"]
GAME_SIZE = (852, 393)
REAR, TOP = HELPERS["REAR"], HELPERS["TOP"]
DETAIL = "Review | rear bank detail"


def clamp(t):
    return min(1., max(0., t))


def authored_pose(rig, frame):
    # Wings start responding before the torso and the outer primaries settle last.
    phase = (frame - 1) / (END - 1)
    roll = -BANK_DEG * smoothstep(clamp(phase))
    channels = {}
    for name, multiplier in (("Body", 1), ("Neck", -.36), ("Head", -.64)):
        bone = rig.pose.bones[name]
        rotation = HELPERS["roll_in_bone"](bone, roll * multiplier)
        channels.update({(bone.path_from_id("rotation_euler"), i): v for i, v in enumerate(rotation)})
    for side, poses in (
        ("L", (("WingRoot", (.5, 0, 0), 0), ("Elbow", (-2, 0, 0), .06),
               ("Wrist", (1.4, -2.0, 5.5), .14), ("Tip", (2.5, 0, 0), .26))),
        ("R", (("WingRoot", (4.0, 0, 0), 0), ("Elbow", (1.0, 0, 0), .06),
               ("Wrist", (-1.2, 1.0, -.8), .14), ("Tip", (-2.0, 0, 0), .26))),
    ):
        for segment, angles, lag in poses:
            onset = smoothstep(clamp((phase - lag) / (1 - lag)))
            bone = rig.pose.bones[f"{segment}.{side}"]
            path = bone.path_from_id("rotation_euler")
            channels.update({(path, i): math.radians(v) * onset for i, v in enumerate(angles) if v})
    return channels


def soft_edges(t):
    # Match the linear middle with zero velocity at the start and hold.
    edge = .2
    if t < edge:
        x = t / edge
        return edge * x * x * (2 - x)
    if t > 1 - edge:
        return 1 - soft_edges(1 - t)
    return t


def phase_at(frame, strength=1.):
    if frame < RELEASE:
        return strength * soft_edges(clamp((frame - ENGAGE) / ENTER))
    return strength * soft_edges(1 - clamp((frame - RELEASE) / EXIT))


def review_pose(cruise, bank, keys, frame, strength=1.):
    if frame < ENGAGE:
        cruise_frame, influence = frame, 0.
    elif frame < RELEASE:
        d = min(6, frame - ENGAGE)
        cruise_frame = CRUISE_FRAME + d * (1 - d / 12)
        influence = smoothstep(clamp((frame - ENGAGE) / 18))
    else:
        d = max(0., frame - RESUME)
        # Accelerate the resumed flap from zero phase speed.
        cruise_frame = 52 + (d * d / 12 if d < 6 else d - 3)
        influence = smoothstep(clamp((RESUME - frame) / 16))
    base = sample_action(cruise, cruise_frame)
    target = sample_action(bank, 1 + (END - 1) * phase_at(frame, strength))
    return {k: (1 - influence) * base.get(k, 0.) + influence * target.get(k, 0.) for k in keys}


def author(rig, cruise):
    bank = make_action(rig, CLIP, lambda f: authored_pose(rig, f), [1, 5, 9, 13, 17, 21, 25])
    bank.asset_mark()
    bank.asset_data.description = "ANM-004 | neutral to left bank, sample frames 1–25 with turn strength"
    for f, label in [(1, "Neutral"), (13, "Half strength"), (25, "Full left bank")]:
        bank.pose_markers.new(label).frame = f
    keys = set(sample_action(cruise, 1)) | set(sample_action(bank, 1))
    frames = list(range(1, REVIEW_END + 1))
    review = make_action(rig, "Review | Cruise and left bank",
                         lambda f: review_pose(cruise, bank, keys, f), frames)
    half = make_action(rig, "Review | Half left and release",
                       lambda f: review_pose(cruise, bank, keys, f, .5), frames)
    return bank, review, half


def scan(scene, mesh, rig, action, first, last, scale):
    set_action(rig, action)
    parts = TOOLS["mesh_parts"](mesh.data)
    flight = [n for n in parts if n.startswith(("Outer primary", "Flight feather 7", "Flight feather 8", "Flight feather 9"))]
    pairs = [("Body and crown", n) for n in flight]
    pairs += [("Wing.L", "Wing.R"), ("Foot.L", "Foot.R")]
    pairs += [(part, f"Wing.{s}") for s in "LR" for part in ("Bill", f"Foot.{s}")]
    tips = {side: np.unique([i for n in flight if n.endswith("." + side)
                             for tri in parts[n] for i in tri]) for side in "LR"}
    edges = np.array([tuple(e.vertices) for e in mesh.data.edges])
    rest = np.array([tuple(v.co) for v in mesh.data.vertices])
    baseline = np.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
    body, head = (rig.pose.bones[name] for name in ("Body", "Head"))
    right = body.bone.matrix_local.to_3x3().inverted() @ Vector((1, 0, 0))
    forward = head.bone.matrix_local.to_3x3().inverted() @ Vector((0, 1, 0))
    motion, roll = {}, []
    low = {"mesh": math.inf, "left_tip": math.inf, "right_tip": math.inf}
    ratio = [1., 1.]
    head_angle = 0.
    for index in range(first * 2, last * 2 + 1):
        frame = index / 2
        TIME(scene, frame)
        assert rig.matrix_world.is_identity and mesh.matrix_world.is_identity
        root = rig.pose.bones["Root"]
        assert root.matrix_basis.is_identity and root.head.length < 1e-8
        points = EVAL(mesh)
        motion[frame] = points
        assert np.isfinite(points).all()
        vertices = [tuple(v) for v in points]
        trees = {part: BVHTree.FromPolygons(vertices, faces, all_triangles=True)
                 for part, faces in parts.items()}
        assert all(trees["Body and crown"].overlap(trees[f"Wing.{s}"]) for s in "LR"), (action.name, frame)
        intersections = [(a, b) for a, b in pairs if trees[a].overlap(trees[b])]
        assert not intersections, (action.name, frame, intersections)
        stretch = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1) / baseline
        ratio = [min(ratio[0], float(stretch.min())), max(ratio[1], float(stretch.max()))]
        low["mesh"] = min(low["mesh"], float(points[:, 2].min()))
        for side, name in (("L", "left_tip"), ("R", "right_tip")):
            low[name] = min(low[name], float(points[tips[side], 2].min()))
        wing_axis = body.matrix.to_3x3() @ right
        roll.append(math.degrees(math.atan2(wing_axis.z, wing_axis.x)))
        look = (head.matrix.to_3x3() @ forward).normalized()
        head_angle = max(head_angle, math.degrees(look.angle(Vector((0, 1, 0)))))
    clearance = {part: {"leader": 8 + scale * z, "follower": 6 + .8 * scale * z} for part, z in low.items()}
    assert .58 < ratio[0] and ratio[1] < 1.45, (action.name, ratio)
    assert min(clearance["mesh"].values()) > 0 and head_angle < .5, (action.name, clearance, head_angle)
    return motion, roll, {
        "samples": len(motion), "sample_step_frames": .5, "frames": [first, last],
        "root_and_armature_fixed": "pass", "shoulder_attachment": "pass",
        "specified_intersections": "pass", "checked_pairs": pairs,
        "edge_ratio_range": ratio, "head_forward_max_deviation_deg": head_angle,
        "body_left_bank_range_deg": [min(roll), max(roll)],
        "min_clearance_game_units": clearance,
    }


def validate_motion(scene, mesh, rig, bank, review, half, cruise, scale):
    motion, rolls, report = scan(scene, mesh, rig, bank, 1, END, scale)
    assert abs(rolls[0]) < 1e-4 and abs(rolls[-1] - BANK_DEG) < 1e-4
    assert min(np.diff(rolls)) > -1e-4
    rest = np.array([tuple(v.co) for v in mesh.data.vertices])
    neutral = float(np.linalg.norm(motion[1] - rest, axis=1).max())
    assert neutral < 1e-6
    report["neutral_mesh_error_BU"] = neutral
    report["strength_samples_left_bank_deg"] = {str(w): rolls[int(w * 2 * (END - 1))]
                                              for w in (0., .25, .5, .75, 1.)}
    # The endpoints are a neutral pose and a held turn. Check their speed
    # against a stationary pose at either end of the action.
    step = .02
    speeds = {}
    set_action(rig, bank)
    for frame, nearby in ((1, 1 + step), (END, END - step)):
        TIME(scene, nearby)
        speeds[str(frame)] = float(np.linalg.norm(EVAL(mesh) - motion[frame], axis=1).max() * FPS / step)
    assert max(speeds.values()) < .004, speeds
    report["endpoint_speed_BU_per_s"] = speeds

    reviews = {}
    for strength, action in ((1., review), (.5, half)):
        poses, angles, stats = scan(scene, mesh, rig, action, 1, REVIEW_END, scale)
        at = lambda frame: angles[int(2 * (frame - 1))]
        assert abs(at(ENGAGE)) < .01 and abs(at(RESUME)) < .01
        expected_bank = BANK_DEG * smoothstep(strength)
        assert abs(at(ENGAGE + ENTER) - expected_bank) < .002
        assert abs(at(RELEASE) - expected_bank) < .002
        rising = np.diff(angles[2 * (ENGAGE - 1):2 * (ENGAGE + ENTER - 1) + 1])
        falling = np.diff(angles[2 * (RELEASE - 1):2 * (RESUME - 1) + 1])
        assert rising.min() > -.002 and falling.max() < .002, (rising.min(), falling.max())
        stats["hold_bank_deg"] = at(RELEASE)
        stats["peak_entry_and_exit_roll_deg_per_s"] = [float(rising.max() * 2 * FPS),
                                                      float(-falling.min() * 2 * FPS)]
        joins = {}
        for frame in (ENGAGE, ENGAGE + ENTER, RELEASE, RESUME):
            TIME(scene, frame - step)
            before = EVAL(mesh)
            TIME(scene, frame + step)
            after = EVAL(mesh)
            jump = float(np.linalg.norm(before + after - 2 * poses[frame], axis=1).max() * FPS / step)
            assert jump < .008, (frame, jump)
            joins[str(frame)] = {"velocity_difference_BU_per_s": jump}
        set_action(rig, cruise)
        for frame, phase in ((ENGAGE, 49), (RESUME, 52)):
            TIME(scene, phase)
            distance = float(np.linalg.norm(poses[frame] - EVAL(mesh), axis=1).max())
            assert distance < 1e-6, (frame, distance)
            joins[str(frame)]["cruise_pose_error_BU"] = distance
        stats["joins"] = joins
        reviews[str(strength)] = stats
    return motion, {"bank": report, "parameterized_review": reviews}


def export_bank(scene, mesh, rig, bank, output):
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = rig
    set_action(rig, bank)
    scene.frame_set(1)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB", use_selection=True,
                              export_yup=True, export_animation_mode="ACTIONS",
                              export_anim_single_armature=False, export_force_sampling=True,
                              export_anim_slide_to_zero=True)
    doc, binary = REF["load_glb"](output)
    base, original = REF["load_glb"](CHR_GLB)
    for field in ("nodes", "meshes", "materials", "extensions"):
        assert doc[field] == base[field], field
    assert len(doc["meshes"]) == len(doc["skins"]) == 1
    assert not doc.get("cameras")
    skin, = doc["skins"]
    original_skin, = base["skins"]
    assert skin["joints"] == original_skin["joints"] and len(skin["joints"]) == 15

    def buffer_for(document, blob, i):
        return TOOLS["packed_accessor"](document, blob, document["accessors"][i])

    for primitive in doc["meshes"][0]["primitives"]:
        for i in [*primitive["attributes"].values(), primitive["indices"]]:
            assert buffer_for(doc, binary, i) == buffer_for(base, original, i)
    assert buffer_for(doc, binary, skin["inverseBindMatrices"]) == buffer_for(
        base, original, original_skin["inverseBindMatrices"])
    assert len(doc["images"]) == len(base["images"]) == 4
    assert [REF["bin_data"](doc, binary, i["bufferView"]) for i in doc["images"]] == [
        REF["bin_data"](base, original, i["bufferView"]) for i in base["images"]]

    clip, = doc["animations"]
    assert clip["name"] == CLIP
    active, targets = [], []
    for channel in clip["channels"]:
        node = doc["nodes"][channel["target"]["node"]]
        prop = channel["target"]["path"]
        sampler = clip["samplers"][channel["sampler"]]
        values = TOOLS["accessor"](doc, binary, sampler["output"])
        default = {"rotation": [0, 0, 0, 1], "translation": [0, 0, 0], "scale": [1, 1, 1]}[prop]
        rest = node.get(prop, default)
        distance = np.linalg.norm(values - rest, axis=1)
        if prop == "rotation":
            distance = np.minimum(distance, np.linalg.norm(values + rest, axis=1))
        # Remove redundant bind-pose tracks emitted during baking.
        if distance.max() < 1e-6:
            continue
        assert node["name"] in rig.pose.bones and node["name"] != "Root" and prop == "rotation"
        assert distance[0] < 1e-6
        times = TOOLS["accessor"](doc, binary, sampler["input"]).ravel()
        assert abs(times[0]) < 1e-7 and abs(times[-1] - (END - 1) / FPS) < 1e-6
        active.append(channel)
        targets.append(node["name"])
    assert set(targets) == {c.data_path.split('"')[1] for c in curves(bank)}
    used = sorted({c["sampler"] for c in active})
    for channel in active:
        channel["sampler"] = used.index(channel["sampler"])
    clip["channels"] = active
    clip["samplers"] = [clip["samplers"][i] for i in used]
    TOOLS["write_glb"](output, doc, binary)
    return {"clip": CLIP, "duration_s": (END - 1) / FPS, "rotation_targets": sorted(targets),
            "root_and_object_channels": 0, "base_mesh_uv_skin_bind_transforms_variants": "pass",
            "packed_texture_bytes_match_CHR": "pass"}


def reimport(source, source_mesh, source_rig, bank, motion, path, render):
    scene = bpy.data.scenes.new("GLB verification")
    window = bpy.context.window
    window.scene = scene
    scene.render.fps = FPS
    bank.name = "Source | Bank_L"
    blocks = (bpy.data.objects, bpy.data.meshes, bpy.data.armatures, bpy.data.materials,
              bpy.data.images, bpy.data.actions)
    before = [set(items) for items in blocks]
    bpy.ops.import_scene.gltf(filepath=str(path), bone_heuristic="BLENDER", disable_bone_shape=True)
    imported = set(bpy.data.objects) - before[0]
    mesh, = [obj for obj in imported if obj.type == "MESH"]
    rig, = [obj for obj in imported if obj.type == "ARMATURE"]
    assert len(imported) == 2 and mesh.matrix_world.is_identity and rig.matrix_world.is_identity
    mesh.data.calc_loop_triangles()
    assert len(mesh.data.loop_triangles) == 3940 and mesh.data.uv_layers.active
    assert mesh.modifiers[0].object == rig and len(mesh.data.materials) == len(source_mesh.data.materials)
    assert len({n.image for mat in mesh.data.materials for n in mat.node_tree.nodes
                if n.type == "TEX_IMAGE" and n.image}) == 4
    assert set(rig.data.bones.keys()) == set(source_rig.data.bones.keys())
    for bone in source_rig.data.bones:
        new = rig.data.bones[bone.name]
        assert (bone.parent and bone.parent.name) == (new.parent and new.parent.name)
        np.testing.assert_allclose(np.asarray(new.matrix_local), np.asarray(bone.matrix_local), atol=1e-5)

    lookup = KDTree(len(source_mesh.data.vertices))
    for vertex in source_mesh.data.vertices:
        lookup.insert(vertex.co, vertex.index)
    lookup.balance()
    indices = []
    for vertex in mesh.data.vertices:
        _, index, distance = lookup.find(vertex.co)
        assert distance < 1e-5
        indices.append(index)
    assert len(set(indices)) == len(source_mesh.data.vertices)
    track, = rig.animation_data.nla_tracks
    strip, = track.strips
    assert strip.action.name == CLIP
    action = strip.action
    rig.animation_data.nla_tracks.remove(track)
    set_action(rig, action)
    start, end = action.frame_range
    assert abs(end - start - (END - 1)) < 1e-4
    assert all('"Root"' not in c.data_path and c.data_path.endswith("rotation_quaternion") for c in curves(action))
    errors = [0., 0.]
    for frame, expected in motion.items():
        TIME(scene, start + frame - 1)
        root = rig.pose.bones["Root"]
        np.testing.assert_allclose(np.asarray(root.matrix_basis), np.eye(4), atol=1e-6)
        index = int(not frame.is_integer())
        errors[index] = max(errors[index], float(np.linalg.norm(EVAL(mesh) - expected[indices], axis=1).max()))
    assert errors[0] < 3e-4 and errors[1] < .002, errors
    if render:
        scene.collection.children.link(bpy.data.collections["Review cameras and lights"])
        scene.world = source.world
        TIME(scene, end)
        REF["render"](scene, scene.objects[DETAIL], path.parent, "glb_full_bank", (1040, 600), 22)
    window.scene = source
    bpy.data.scenes.remove(scene)
    bpy.data.batch_remove(ids=set().union(*(set(items) - old for items, old in zip(blocks, before))))
    bank.name = CLIP
    return {"clip": CLIP, "duration_s": float((end - start) / FPS), "samples": len(motion),
            "max_key_vertex_error_BU": errors[0], "max_half_frame_vertex_error_BU": errors[1],
            "skin_uv_plumage_rest_axes_pivot_scale_and_orientation": "pass", "root_fixed": "pass"}


def copy_camera(scene, camera, parent):
    obj = camera.copy()
    scene.collection.objects.link(obj)
    obj.parent = parent
    return obj


def review_studio(source, mesh, rig, action, scale):
    scene = bpy.data.scenes.new("Review | Cruise to left turn")
    scene.world = source.world
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, REVIEW_END
    group = REF["collection"](scene, "Review followers")
    path = bpy.data.objects.new("Preview trajectory | turn carrier", None)
    scene.collection.objects.link(path)
    for obj in (source.objects["Neutral key"], source.objects["Review Ground"]):
        scene.collection.objects.link(obj)
    cameras = {name: copy_camera(scene, source.objects[name], path) for name in (REAR, DETAIL, TOP)}
    cameras["overhead"] = REF["camera"](
        scene.collection, "Review | flock overhead", (0, -1.2, 8), (0, -1.2, 0), ortho=8.8)
    cameras["overhead"].parent = path
    scene.camera = cameras[REAR]

    # Preview translation/yaw lives entirely on an Empty. The formation
    # follows this frame with fixed offsets for consistent screen comparisons.
    yaw = x = y = 0.
    dt = 1 / FPS
    route = []
    for f in range(1, REVIEW_END + 1):
        route.append((x, y))
        path.location = (x, y, 0.)
        path.rotation_euler.z = yaw
        path.keyframe_insert("location", frame=f)
        path.keyframe_insert("rotation_euler", index=2, frame=f)
        rate = .60 * smoothstep(phase_at(f + .5))
        mid = yaw + rate * dt / 2
        x -= math.sin(mid) * 30 / scale * dt
        y += math.cos(mid) * 30 / scale * dt
        yaw += rate * dt
    for c in curves(path.animation_data.action):
        for point in c.keyframe_points:
            point.interpolation = "LINEAR"

    birds = []
    for i in range(12):
        collection = group if i else scene.collection
        actor = rig.copy()
        actor.name = "Review rig | leader" if not i else f"Review rig | follower {i:02}"
        collection.objects.link(actor)
        actor.parent = path
        actor.animation_data_clear()
        delay = DELAYS[i - 1] if i else 0
        track = actor.animation_data_create().nla_tracks.new()
        strip = track.strips.new("Preview pose", 1 + delay, action)
        strip.action_slot = action.slots[0]
        strip.extrapolation = "HOLD"
        bird = mesh.copy()
        bird.name = "Review mesh | leader" if not i else f"Review mesh | follower {i:02}"
        collection.objects.link(bird)
        bird.parent = actor
        bird.modifiers["GooseSkin"].object = actor
        if i:
            x, y = FLOCK_XY[i - 1]
            actor.location = (x / scale, y / scale, -2 / scale)
            actor.scale = (.8,) * 3
            bird.material_slots[0].link = "OBJECT"
            bird.material_slots[0].material = bpy.data.materials[f"Body_Follower_{'ABC'[(i - 1) % 3]}"]
        birds.append(bird)
    for frame, label in (
        (1, "Cruise"), (ENGAGE, "Blend in"), (ENGAGE + ENTER, "Full left"),
        (RELEASE, "Release"), (RESUME, "Cruise resumes"),
    ):
        scene.timeline_markers.new(label, frame=frame)
    return scene, group, birds, cameras, path, route


def render_route(scene, route, output):
    # The trail is temporary review geometry on the reference ground.
    floor_z = scene.objects["Review Ground"].location.z
    trail = bpy.data.curves.new("Preview track", "CURVE")
    trail.dimensions = "3D"
    trail.bevel_depth = .017
    trail.bevel_resolution = 3
    trail.materials.append(REF["plain"]("Preview track | muted jade", "42675F"))
    spline = trail.splines.new("POLY")
    spline.points.add(len(route) - 1)
    for point, (x, y) in zip(spline.points, route):
        point.co = (x, y, floor_z + .027, 1.)
    line = bpy.data.objects.new("Preview track", trail)
    scene.collection.objects.link(line)
    scene.frame_set(REVIEW_END)
    center = (route[-1][0] * .45, route[-1][1] * .49)
    camera = REF["camera"](scene.collection, "Review | world overhead",
                           (*center, 8), (*center, 0), ortho=8.1)
    REF["render"](scene, camera, output, "top_world_trajectory", (960, 660), 22)


def check_flock(scene, birds, cameras, path, scale):
    margin = clearance = math.inf
    floor = scene.objects["Review Ground"].location.z
    assert len(birds) == 12 and len({b.data for b in birds}) == 1
    for frame in range(1, REVIEW_END + 1):
        scene.frame_set(frame)
        for bird in birds:
            points = EVAL(bird)
            bounds = TOOLS["frame_points"](cameras[REAR], bird, points)
            x0, y0, x1, y1 = bounds
            margin = min(margin, x0, y0, GAME_SIZE[0] - x1, GAME_SIZE[1] - y1)
            world = bird.matrix_world
            z = points[:, 2].min() * world.to_scale().z + world.translation.z
            clearance = min(clearance, float((z - floor) * scale))
    assert margin > 0 and clearance > 0, (margin, clearance)
    return {"frames": REVIEW_END, "birds": 12, "shared_mesh_datablocks": 1, "delays_frames": DELAYS,
            "formation_xy_game_units": FLOCK_XY, "min_screen_margin_px": margin,
            "min_clearance_game_units": clearance, "preview_heading_change_deg": math.degrees(path.rotation_euler.z),
            "preview_carrier_position_final_game_xy": [float(v) * scale for v in path.location[:2]]}


def stills(scene, group, birds, cameras, output):
    render = REF["render"]
    group.hide_render = True
    for label, frame in (("cruise", ENGAGE), ("entry", ENGAGE + ENTER // 2), ("full_bank", RELEASE - 2),
                         ("release", RELEASE + EXIT // 2)):
        scene.frame_set(frame)
        render(scene, cameras[REAR], output, f"rear_1x_{label}", GAME_SIZE, 24)
    scene.frame_set(RELEASE - 2)
    render(scene, cameras[TOP], output, "top_full_bank", (1040, 600), 24)
    leader = birds[0].parent
    leader.scale = (.5,) * 3
    bpy.context.view_layer.update()
    render(scene, cameras[REAR], output, "rear_half_full_bank", GAME_SIZE, 28)
    render(scene, cameras[TOP], output, "top_half_full_bank", (1040, 600), 24)
    leader.scale = (1.,) * 3
    group.hide_render = False
    bpy.context.view_layer.update()
    render(scene, cameras[REAR], output, "rear_flock_12", GAME_SIZE, 24)
    render(scene, cameras["overhead"], output, "top_flock_12", (1040, 600), 24)


def video(scene, camera, size, output):
    REF["render_settings"](scene, size, 8)
    scene.render.use_persistent_data = True
    scene.camera = camera
    with TemporaryDirectory(prefix="ft-anm004-") as directory:
        temp = Path(directory)
        for i, frame in enumerate(range(1, REVIEW_END + 1, 2)):
            scene.frame_set(frame)
            scene.render.filepath = str(temp / f"{i:03}.png")
            bpy.ops.render.render(write_still=True, scene=scene.name)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-framerate", "24", "-i",
                        str(temp / "%03d.png"), "-c:v", "libx264", "-crf", "16", "-vf",
                        "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=black", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(output)], check=True)


def main(output, mode):
    output.mkdir(parents=True, exist_ok=True)
    assert not any(output.iterdir()), "Choose a new, empty output directory."
    chr_manifest = json.loads((CHR / "asset_manifest.json").read_text())
    cruise_manifest = json.loads((ANM / "asset_manifest.json").read_text())
    for manifest, files in ((chr_manifest, (CHR_BLEND, CHR_GLB)), (cruise_manifest, (CRUISE_BLEND,))):
        assert manifest["status"] == "done"
        for file in files:
            assert DIGEST(file) == manifest["files"][file.name], file
    bpy.context.preferences.addons["io_scene_gltf2"].preferences.KHR_materials_variants_ui = True
    bpy.ops.wm.open_mainfile(filepath=str(CHR_BLEND))
    scene = bpy.context.scene
    scene.name = "ANM-004 | Editable Bank_L"
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, END
    scale = chr_manifest["camera"]["preview_game_units_per_BU"]
    rig, mesh = scene.objects["GooseRig"], scene.objects["Goose_LOD0"]
    assert len(rig.pose.bones) == 15 and len([i for i in bpy.data.images if i.packed_file]) == 4
    with bpy.data.libraries.load(str(CRUISE_BLEND), link=False) as (available, imported):
        assert "Cruise_Flap_Loop" in available.actions
        imported.actions = ["Cruise_Flap_Loop"]
    cruise, = imported.actions
    assert tuple(cruise.frame_range) == (1, 53)
    bank, preview, half = author(rig, cruise)
    scene.objects[HELPERS["DETAIL"]].name = DETAIL
    detail = scene.objects[DETAIL]
    detail.location = (0, -1.65, .96)
    detail.rotation_euler = (Vector((0, .06, .09)) - detail.location).to_track_quat("-Z", "Y").to_euler()
    qa = {}
    if mode != "draft":
        motion, qa = validate_motion(scene, mesh, rig, bank, preview, half, cruise, scale)
        glb = output / f"{STEM}.glb"
        qa["glb"] = export_bank(scene, mesh, rig, bank, glb)
        qa["blender_reimport"] = reimport(scene, mesh, rig, bank, motion, glb, mode == "full")
    review, group, birds, cameras, path, route = review_studio(scene, mesh, rig, preview, scale)
    window = bpy.context.window
    window.scene = review
    qa["flock"] = check_flock(review, birds, cameras, path, scale)
    if mode == "draft":
        stills(review, group, birds, cameras, output)
        return

    review.frame_set(RELEASE - 2)
    REF["render_settings"](review, GAME_SIZE, 24)
    review.render.filepath = "//"
    window.scene = scene
    set_action(rig, bank)
    scene.frame_set(END)
    scene.camera = detail
    REF["render_settings"](scene, (1040, 600), 24)
    scene.render.filepath = "//"
    scene["Playback"] = "Bank_L: sample frames 1–25 from neutral to 12 degrees left; preview scene shows entry and exit."
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.region_3d.view_perspective = "CAMERA"
                space.overlay.show_overlays = False
                space.shading.color_type = "TEXTURE"
    bpy.ops.wm.save_as_mainfile(filepath=str(output / f"{STEM}.blend"), compress=True)
    if mode == "full":
        window.scene = review
        stills(review, group, birds, cameras, output)
        group.hide_render = True
        video(review, cameras[DETAIL], (864, 480), output / "preview_rear_detail.mp4")
        group.hide_render = False
        video(review, cameras[REAR], GAME_SIZE, output / "preview_rear_flock_12.mp4")
        group.hide_render = True
        render_route(review, route, output)
    DUMP(output / "qa.json", {"id": "ANM-004", "version": "v001", "status": "needs_review", "blender": qa})
    DUMP(output / "asset_manifest.json", {
        "id": "ANM-004", "version": "v001", "status": "needs_review", "blender": bpy.app.version_string,
        "dependencies": {"CHR-001/v001": "done"}, "review_reference": "ANM-001/v001",
        "source_hashes": {str(p.relative_to(LIBRARY)): DIGEST(p) for p in (
            CHR_BLEND, CHR_GLB, CRUISE_BLEND, SUPPORT, ANM / "ANM-001_cruise_flap_generate.py",
            CHR / "CHR-001_goose_rig_generate.py",
        )},
        "source": "Original keyframed turn response on accepted CHR-001 mesh and armature.",
        "rights": "Project-original animation, reuses project CHR-001 packed plumage.",
        "clip": {"name": CLIP, "frames": [1, END], "fps": FPS, "duration_s": (END - 1) / FPS,
                 "loop": False, "sampling": "t=0.5s × normalized left-turn strength, hold sample",
                 "bank_left_deg": BANK_DEG, "root_motion": False},
        "review": {"cruise_entry_frame": CRUISE_FRAME, "cruise_entry_phase": (CRUISE_FRAME - 1) / 52,
                   "cruise_exit_frame": 52, "entry_s": ENTER / FPS, "hold_s": HOLD / FPS, "exit_s": EXIT / FPS,
                   "base_pose_blend_in_s": 18 / FPS, "base_pose_blend_out_s": 16 / FPS,
                   "camera": chr_manifest["camera"], "follower_scale": .8},
        "character": {"triangles_lod0": 3940, "bones": 15, "pivot_BU": [0, 0, 0], "scale": [1, 1, 1],
                      "axes_blender": chr_manifest["axes_blender"], "axes_gltf": chr_manifest["axes_gltf"]},
        "variants": chr_manifest["variants"], "texture_mapping": chr_manifest["texture_mapping"],
        "files": {p.name: DIGEST(p) for p in [Path(__file__), *sorted(output.iterdir())]},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=["draft", "checks", "full"], default="full")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    main(args.output.resolve(), args.mode)
