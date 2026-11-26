"""Run in Blender background mode. Pass a new output directory after --."""
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
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
CHR = LIBRARY / "CHR-001" / "v001"
ANM = LIBRARY / "ANM-001" / "v001"
CHR_BLEND = CHR / "CHR-001_goose_rig.blend"
CHR_GLB = CHR / "CHR-001_goose_rig.glb"
CRUISE_BLEND = ANM / "ANM-001_cruise_flap.blend"
TOOLS = runpy.run_path(str(ANM / "ANM-001_cruise_flap_generate.py"))
REF = TOOLS["REFERENCE"]
BIND, EVAL, TIME = (TOOLS[k] for k in ("bind_action", "evaluated", "time_set"))
DIGEST, DUMP = TOOLS["digest"], TOOLS["dump"]
FPS = 48
GLIDE, CIRCLE = "Glide_Loop", "Circle_Loop"
PERIODS = {GLIDE: 72, CIRCLE: 96}
CRUISE_FRAME = 49
ENTER_GLIDE, HOLD_GLIDE, ENTER_CIRCLE = 16, 48, 24
CUT_1 = CRUISE_FRAME - 1
GLIDE_IN = CUT_1 + ENTER_GLIDE
CUT_2 = GLIDE_IN + HOLD_GLIDE
CIRCLE_IN = CUT_2 + ENTER_CIRCLE
REVIEW_END = CIRCLE_IN + 96
GAME_SIZE = (852, 393)
FOLLOWER_SCALE = .8
FOLLOWER_OFFSETS = [3, 9, 5, 16, 7, 20, 12, 22, 14, 4, 18]
FLOCK_POSITIONS = TOOLS["FLOCK_POSITIONS"]
REAR = "Gameplay | fixed rear"
DETAIL = "Review | rear detail"
TOP = "Review | top"
FLOCK_TOP = "Review | flock overhead"


def curves(action):
    return action.layers[0].strips[0].channelbag(action.slots[0]).fcurves


def key(bone, prop, axis):
    return bone.path_from_id(prop), axis


def roll_in_bone(bone, angle):
    # Rotate around the character's longitudinal axis through the bone pivot.
    # Body's rest +Y is pitched, so a direct Body Euler Y would introduce yaw.
    axis = bone.bone.matrix_local.to_3x3().inverted() @ Vector((0, 1, 0))
    return Quaternion(axis, math.radians(angle)).to_euler("XYZ")


def pose_channels(rig, name, offset):
    bones = rig.pose.bones
    phase = math.tau * offset / PERIODS[name]
    circling = name == CIRCLE
    channels = {}
    for side in ("L", "R"):
        inner = side == "L"
        mirror = -1 if inner else 1
        # Lag increases toward the tip. The inner wing yields at the elbow,
        # while the outer hand stays extended into the turn.
        root = (1.1 if inner else 4.5) if circling else 2.6
        elbow = (-.8 if inner else .9) if circling else .5
        wrist = (.6 if inner else -.5) if circling else -.4
        for segment, bend in (
            ("WingRoot", root + .38 * math.sin(phase)),
            ("Elbow", elbow + .27 * math.sin(phase - .36)),
            ("Wrist", wrist + 1.15 * math.sin(phase - .88)),
            ("Tip", -.7 + 1.55 * math.sin(phase - 1.44)),
        ):
            bone = bones[f"{segment}.{side}"]
            channels[key(bone, "rotation_euler", 0)] = math.radians(bend)
        wrist_bone = bones[f"Wrist.{side}"]
        twist = (.6 if inner else -.4) if circling else 0
        channels[key(wrist_bone, "rotation_euler", 1)] = mirror * math.radians(
            twist + .75 * math.sin(phase - 1.05)
        )
        if circling:
            # Positive local sweep on the left draws its wrist gently aft.
            channels[key(wrist_bone, "rotation_euler", 2)] = math.radians(
                (2.7 if inner else .45) + mirror * .26 * math.sin(phase - .88)
            )
    if circling:
        bank = -7.5 + .75 * math.sin(phase)
        for name, factor in (("Body", 1), ("Neck", -.38), ("Head", -.56)):
            bone = bones[name]
            for axis, angle in enumerate(roll_in_bone(bone, factor * bank)):
                channels[key(bone, "rotation_euler", axis)] = angle
    return channels


def make_action(rig, name, evaluate, knots, cyclic=False):
    # Hermite tangents preserve both sides of the loop and the blend joins.
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    action.use_frame_range = True
    action.frame_start, action.frame_end = knots[0], knots[-1]
    action.use_cyclic = cyclic
    slot = action.slots.new(id_type="OBJECT", name=rig.name)
    strip = action.layers.new("Pose").strips.new(type="KEYFRAME")
    bag = strip.channelbag(slot, ensure=True)
    epsilon = .01
    samples = [(evaluate(f), evaluate(f - epsilon), evaluate(f + epsilon)) for f in knots]
    for path, axis in sorted(samples[0][0]):
        bone_name = path.split('"')[1]
        curve = bag.fcurves.new(path, index=axis, group_name=bone_name)
        curve.keyframe_points.add(len(knots))
        for index, (point, frame, (pose, before, after)) in enumerate(zip(curve.keyframe_points, knots, samples)):
            value = pose[path, axis]
            tangent = (after[path, axis] - before[path, axis]) / (2 * epsilon)
            left = (frame - knots[index - 1]) / 3 if index else (knots[1] - frame) / 3
            right = (knots[index + 1] - frame) / 3 if index + 1 < len(knots) else left
            point.co = (frame, value)
            point.interpolation = "BEZIER"
            point.handle_left_type = point.handle_right_type = "FREE"
            point.handle_left = (frame - left, value - tangent * left)
            point.handle_right = (frame + right, value + tangent * right)
        if cyclic:
            curve.modifiers.new("CYCLES")
        curve.update()
    return action


def set_action(rig, action):
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    BIND(rig, action)


def author_loops(rig):
    loops = {}
    for name, period in PERIODS.items():
        action = make_action(
            rig, name, lambda frame: pose_channels(rig, name, frame - 1),
            list(range(1, period + 2, period // 8)), cyclic=True,
        )
        action.asset_mark()
        action.asset_data.description = (
            "ANM-003 · in-place extended glide" if name == GLIDE else
            "ANM-003 · in-place left bank; game supplies heading and trajectory"
        )
        action.pose_markers.new("Loop in").frame = 1
        action.pose_markers.new("Seam sample").frame = period + 1
        loops[name] = action
    return loops


def sample_action(action, frame):
    return {(c.data_path, c.array_index): c.evaluate(frame) for c in curves(action)}


def smoothstep(u):
    return u**3 * (10 + u * (-15 + 6 * u))


def build_review(rig, cruise, loops, label="Review | Cruise to Glide to Circle"):
    all_keys = set().union(*(sample_action(a, 1) for a in (cruise, *loops.values())))

    def evaluate(frame):
        t = frame - 1
        if t < CUT_1:
            a, b, weight = sample_action(cruise, frame), {}, 0
        elif t < GLIDE_IN:
            elapsed = t - CUT_1
            # Brake the cruise phase for six frames, advancing just three
            # source frames in total so it never starts another upstroke.
            decel = min(6, elapsed)
            phase = CRUISE_FRAME + decel * (1 - decel / 12)
            a = sample_action(cruise, phase)
            b = sample_action(loops[GLIDE], 1 + t - GLIDE_IN)
            weight = smoothstep(elapsed / ENTER_GLIDE)
        elif t < CUT_2:
            a, b, weight = sample_action(loops[GLIDE], 1 + t - GLIDE_IN), {}, 0
        elif t < CIRCLE_IN:
            a = sample_action(loops[GLIDE], 1 + t - GLIDE_IN)
            b = sample_action(loops[CIRCLE], 1 + t - CIRCLE_IN)
            weight = smoothstep((t - CUT_2) / ENTER_CIRCLE)
        else:
            a, b, weight = sample_action(loops[CIRCLE], 1 + t - CIRCLE_IN), {}, 0
        return {channel: (1 - weight) * a.get(channel, 0) + weight * b.get(channel, 0)
                for channel in all_keys}

    return make_action(rig, label, evaluate, list(range(1, REVIEW_END + 2)))


def seam_report(start, end, sample, step=.02):
    first, last = sample(start), sample(end)
    before, after = sample(end - step), sample(start + step)
    pose = float(np.linalg.norm(first - last, axis=1).max())
    velocity = float(np.linalg.norm((after - first) - (last - before), axis=1).max() * FPS / step)
    return {"position_BU": pose, "velocity_delta_BU_per_s": velocity, "step_frames": step}


def measure(scene, mesh, rig, actions, cruise, review, scale):
    parts = TOOLS["mesh_parts"](mesh.data)
    flight = [n for n in parts if n.startswith(("Outer primary", "Flight feather 7", "Flight feather 8", "Flight feather 9"))]
    pairs = [("Body and crown", part) for part in flight]
    pairs.extend([("Wing.L", "Wing.R"), ("Foot.L", "Foot.R")])
    pairs.extend((part, f"Wing.{side}") for side in "LR" for part in ("Bill", f"Foot.{side}"))
    tips = {s: np.unique([i for n in flight if n.endswith("." + s) for tri in parts[n] for i in tri])
            for s in "LR"}
    assert all(indices.size for indices in tips.values()), list(parts)
    edges = np.array([tuple(e.vertices) for e in mesh.data.edges])
    rest = np.array([tuple(v.co) for v in mesh.data.vertices])
    rest_lengths = np.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
    forward = rig.data.bones["Head"].matrix_local.to_3x3().inverted() @ Vector((0, 1, 0))
    body_right = rig.data.bones["Body"].matrix_local.to_3x3().inverted() @ Vector((1, 0, 0))

    def sample(frame):
        TIME(scene, frame)
        return EVAL(mesh)

    def scan(action, end, start=1):
        set_action(rig, action)
        motions = {}
        minima = {"all": math.inf, "L": math.inf, "R": math.inf}
        ratio = [1., 1.]
        head_deg, bank = 0., []
        max_step = 0.
        previous = None
        for i in range(2 * start, 2 * end + 1):
            frame = i / 2
            coords = sample(frame)
            assert np.isfinite(coords).all()
            root = rig.pose.bones["Root"]
            assert root.matrix_basis.is_identity and root.head.length < 1e-8
            assert rig.matrix_world.is_identity and mesh.matrix_world.is_identity
            verts = [tuple(p) for p in coords]
            trees = {n: BVHTree.FromPolygons(verts, triangles, all_triangles=True)
                     for n, triangles in parts.items()}
            assert all(trees["Body and crown"].overlap(trees[f"Wing.{s}"]) for s in "LR"), frame
            overlaps = [(a, b) for a, b in pairs if trees[a].overlap(trees[b])]
            assert not overlaps, (action.name, frame, overlaps)
            stretch = np.linalg.norm(coords[edges[:, 0]] - coords[edges[:, 1]], axis=1) / rest_lengths
            ratio = [min(ratio[0], float(stretch.min())), max(ratio[1], float(stretch.max()))]
            minima["all"] = min(minima["all"], float(coords[:, 2].min()))
            for side, indices in tips.items():
                minima[side] = min(minima[side], float(coords[indices, 2].min()))
            head = (rig.pose.bones["Head"].matrix.to_3x3() @ forward).normalized()
            head_deg = max(head_deg, math.degrees(head.angle(Vector((0, 1, 0)))))
            right = rig.pose.bones["Body"].matrix.to_3x3() @ body_right
            bank.append(math.degrees(math.atan2(-right.z, right.x)))
            if previous is not None:
                max_step = max(max_step, float(np.linalg.norm(coords - previous, axis=1).max()))
            previous = coords
            motions[frame] = coords
        assert ratio[0] > .58 and ratio[1] < 1.45, (action.name, ratio)
        assert head_deg < .5, (action.name, head_deg)
        clearance = {part: {"leader": 8 + scale * z, "follower": 6 + FOLLOWER_SCALE * scale * z}
                     for part, z in minima.items()}
        assert all(min(c.values()) > 0 for c in clearance.values()), (action.name, clearance)
        return motions, {
            "frames": [start, end], "samples": len(motions), "step_frames": .5,
            "root_object_and_heading": "pass", "shoulder_attachment": "pass",
            "specified_intersections": "pass", "nonadjacent_pairs": pairs,
            "edge_length_ratio_range": ratio, "head_forward_deviation_max_deg": head_deg,
            "body_bank_range_deg_positive_right_down": [min(bank), max(bank)],
            "min_clearance_game_units_by_part": clearance,
            "max_half_frame_vertex_travel_BU": max_step,
        }

    results, motion = {}, {}
    for name, action in actions.items():
        end = 1 + PERIODS[name]
        motion[name], results[name] = scan(action, end)
        seam = seam_report(1, end, sample)
        assert seam["position_BU"] < 1e-6 and seam["velocity_delta_BU_per_s"] < .004, (name, seam)
        results[name]["loop_seam"] = seam
    _, transition = scan(review, CIRCLE_IN + 1, CUT_1 + 1)
    joins = {}
    for t in (CUT_1, GLIDE_IN, CUT_2, CIRCLE_IN):
        joins[str(t + 1)] = seam_report(t + 1, t + 1, sample)
        assert joins[str(t + 1)]["velocity_delta_BU_per_s"] < .025, joins
    transition["joins"] = joins
    set_action(rig, review)
    bank_samples = []
    for step in range(2 * (CUT_2 + 1), 2 * (CIRCLE_IN + 1) + 1):
        TIME(scene, step / 2)
        right = rig.pose.bones["Body"].matrix.to_3x3() @ body_right
        bank_samples.append(math.degrees(math.atan2(-right.z, right.x)))
    peak_roll_speed = float(np.max(np.abs(np.diff(bank_samples))) * 2 * FPS)
    assert peak_roll_speed < 32, peak_roll_speed
    transition["circle_entry_bank_start_end_deg"] = [bank_samples[0], bank_samples[-1]]
    transition["circle_entry_peak_roll_deg_per_s"] = peak_roll_speed
    # Check each boundary against the actual adjacent action, including the
    # glide loop endpoint reached as the circle blend finishes.
    for elapsed, action, phase in (
        (CUT_1, cruise, CRUISE_FRAME), (GLIDE_IN, actions[GLIDE], 1),
        (CUT_2, actions[GLIDE], HOLD_GLIDE + 1), (CIRCLE_IN, actions[CIRCLE], 1),
    ):
        set_action(rig, review)
        handoff = sample(elapsed + 1)
        set_action(rig, action)
        expected = sample(phase)
        error = float(np.linalg.norm(handoff - expected, axis=1).max())
        assert error < 1e-6, (elapsed, action.name, error)
        joins[str(elapsed + 1)]["adjacent_action_pose_error_BU"] = error
    return {"loops": results, "transitions": transition}, motion


def export_loops(scene, mesh, rig, loops, output):
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    set_action(rig, loops[GLIDE])
    track = rig.animation_data.nla_tracks.new()
    track.name = CIRCLE
    track.strips.new(CIRCLE, 1, loops[CIRCLE]).action_slot = loops[CIRCLE].slots[0]
    scene.frame_set(1)
    bpy.ops.export_scene.gltf(
        filepath=str(output), export_format="GLB", use_selection=True,
        export_yup=True, export_animation_mode="ACTIONS", export_anim_single_armature=False,
        export_force_sampling=True, export_anim_slide_to_zero=True,
    )
    rig.animation_data.nla_tracks.remove(track)
    doc, binary = REF["load_glb"](output)
    base, original = REF["load_glb"](CHR_GLB)
    for name in ("nodes", "meshes", "materials", "extensions"):
        assert doc[name] == base[name], name
    assert not doc.get("cameras") and not doc.get("extensionsRequired")
    skin, = doc["skins"]
    assert skin["joints"] == base["skins"][0]["joints"] and len(skin["joints"]) == 15

    def accessor_bytes(asset, blob, index):
        return TOOLS["packed_accessor"](asset, blob, asset["accessors"][index])

    for primitive in doc["meshes"][0]["primitives"]:
        for index in [*primitive["attributes"].values(), primitive["indices"]]:
            assert accessor_bytes(doc, binary, index) == accessor_bytes(base, original, index)
    assert accessor_bytes(doc, binary, skin["inverseBindMatrices"]) == accessor_bytes(
        base, original, base["skins"][0]["inverseBindMatrices"]
    )
    assert len(doc["images"]) == len(base["images"]) == 4
    assert [REF["bin_data"](doc, binary, i["bufferView"]) for i in doc["images"]] == [
        REF["bin_data"](base, original, i["bufferView"]) for i in base["images"]
    ]
    assert {c["name"] for c in doc["animations"]} == set(loops) and len(doc["animations"]) == 2
    report = {}
    for clip in doc["animations"]:
        name = clip["name"]
        active, targets = [], []
        seam = 0.
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
            # Strip only channels whose entire sampled pose equals bind pose.
            if float(distance.max()) < 1e-6:
                continue
            assert node["name"] in rig.pose.bones and node["name"] != "Root" and prop == "rotation"
            times = TOOLS["accessor"](doc, binary, sampler["input"]).ravel()
            assert abs(times[0]) < 1e-7 and abs(times[-1] - PERIODS[name] / FPS) < 1e-6
            seam = max(seam, float(min(np.linalg.norm(values[-1] - values[0]),
                                      np.linalg.norm(values[-1] + values[0]))))
            active.append(channel)
            targets.append(node["name"])
        assert seam < 1e-6
        used = sorted({channel["sampler"] for channel in active})
        for channel in active:
            channel["sampler"] = used.index(channel["sampler"])
        clip["channels"] = active
        clip["samplers"] = [clip["samplers"][i] for i in used]
        expected = {c.data_path.split('"')[1] for c in curves(loops[name])}
        assert set(targets) == expected and len(targets) == len(expected)
        report[name] = {"duration_s": PERIODS[name] / FPS, "rotation_targets": sorted(targets),
                        "root_and_object_channels": 0, "quaternion_seam_error": seam}
    TOOLS["write_glb"](output, doc, binary)
    return {"clips": report, "same_base_mesh_uv_weights_bind_axes_and_variants": "pass",
            "four_embedded_textures_match_CHR_bytes": "pass"}


def verify_roundtrip(source_scene, source_mesh, source_rig, loops, output, motion, render_stills):
    scene = bpy.data.scenes.new("Verification | GLB import")
    window = bpy.context.window
    window.scene = scene
    scene.render.fps = FPS
    datablocks = (bpy.data.objects, bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.images)
    before = [set(blocks) for blocks in datablocks]
    for name, action in loops.items():
        action.name = "Source | " + name
    bpy.ops.import_scene.gltf(
        filepath=str(output), bone_heuristic="BLENDER", disable_bone_shape=True,
    )
    imported = set(bpy.data.objects) - before[0]
    temporary = set().union(*(set(blocks) - existing for blocks, existing in zip(datablocks, before)))
    mesh, = [obj for obj in imported if obj.type == "MESH"]
    rig, = [obj for obj in imported if obj.type == "ARMATURE"]
    assert len(imported) == 2
    assert rig.matrix_world.is_identity and mesh.matrix_world.is_identity
    assert mesh.data.uv_layers.active and len(mesh.data.materials) == len(source_mesh.data.materials)
    mesh.data.calc_loop_triangles()
    assert len(mesh.data.loop_triangles) == 3940
    assert {b.name for b in rig.data.bones} == {b.name for b in source_rig.data.bones}
    for bone in source_rig.data.bones:
        new = rig.data.bones[bone.name]
        assert (bone.parent and bone.parent.name) == (new.parent and new.parent.name)
        np.testing.assert_allclose(np.array(bone.matrix_local), np.array(new.matrix_local), atol=1e-5)
    assert len({node.image for mat in mesh.data.materials for node in mat.node_tree.nodes
                if node.type == "TEX_IMAGE" and node.image}) == 4
    assert rig.pose.bones["Root"].head.length < 1e-6

    lookup = KDTree(len(source_mesh.data.vertices))
    for vertex in source_mesh.data.vertices:
        lookup.insert(vertex.co, vertex.index)
    lookup.balance()
    indices = []
    for vertex in mesh.data.vertices:
        _, i, distance = lookup.find(vertex.co)
        assert distance < 1e-5, distance
        indices.append(i)
    assert len(set(indices)) == len(source_mesh.data.vertices)
    actions = {track.name: strip.action for track in rig.animation_data.nla_tracks for strip in track.strips}
    assert set(actions) == set(motion), list(actions)
    for track in list(rig.animation_data.nla_tracks):
        rig.animation_data.nla_tracks.remove(track)
    report = {}
    for name, action in actions.items():
        assert action.name == name, action.name
        set_action(rig, action)
        start, end = action.frame_range
        assert abs(end - start - PERIODS[name]) < 1e-4
        assert all('"Root"' not in c.data_path and c.data_path.startswith("pose.bones[") for c in curves(action))

        def sample(frame):
            TIME(scene, frame)
            return EVAL(mesh)

        errors = [0., 0.]
        for frame, expected in motion[name].items():
            actual = sample(start + frame - 1)
            root = rig.pose.bones["Root"]
            np.testing.assert_allclose(np.asarray(root.matrix_basis), np.eye(4), atol=1e-6)
            index = int(not frame.is_integer())
            errors[index] = max(errors[index], float(np.linalg.norm(actual - expected[indices], axis=1).max()))
        seam = seam_report(start, end, sample, step=1)
        assert seam["position_BU"] < 1e-5 and seam["velocity_delta_BU_per_s"] < .02, (name, seam)
        assert errors[0] < 3e-4 and errors[1] < .002, (name, errors)
        report[name] = {
            "action_name_in_blender": action.name, "duration_s": float((end - start) / FPS),
            "samples": len(motion[name]), "max_integer_vertex_error_BU": errors[0],
            "max_half_frame_vertex_error_BU": errors[1], "loop_seam": seam, "root_fixed": "pass",
        }
    if render_stills:
        scene.collection.children.link(bpy.data.collections["Review cameras and lights"])
        scene.world = source_scene.world
        for name, action in actions.items():
            set_action(rig, action)
            TIME(scene, action.frame_range[0] + PERIODS[name] / 4)
            REF["render"](scene, scene.objects[DETAIL], output.parent,
                          f"glb_{name.split('_')[0].lower()}", (1040, 600), 22)
    window.scene = source_scene
    bpy.data.scenes.remove(scene)
    bpy.data.batch_remove(ids=temporary | set(actions.values()))
    for name, action in loops.items():
        action.name = name
    return {"clips": report, "blender_mesh_skin_uv_materials_axes_scale_and_pivot": "pass"}


def mark_timeline(scene):
    for label, time in (
        ("Cruise", 0), ("Recovery f49 / blend", CUT_1), ("Glide / hold", GLIDE_IN),
        ("Enter circle / blend", CUT_2), ("Circle / loop", CIRCLE_IN),
    ):
        scene.timeline_markers.new(label, frame=time + 1)


def review_scene(source, mesh, rig, review, scale):
    scene = bpy.data.scenes.new("Review | Glide and left circle")
    scene.world = source.world
    scene.collection.children.link(bpy.data.collections["Review cameras and lights"])
    scene.camera = scene.objects[REAR]
    REF["camera"](scene.collection, FLOCK_TOP, (0, -1.2, 8), (0, -1.2, 0), ortho=8.8)
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, REVIEW_END
    mark_timeline(scene)
    group = REF["collection"](scene, "Flock review | 11 followers")
    carriers = []
    birds = []
    for i in range(12):
        collection = scene.collection if i == 0 else group
        parent = bpy.data.objects.new("Leader | preview carrier" if i == 0 else f"Follower {i:02} | preview carrier", None)
        collection.objects.link(parent)
        carriers.append(parent)
        actor = rig.copy()
        actor.name = "Review rig | leader" if i == 0 else f"Review rig | follower {i:02}"
        collection.objects.link(actor)
        actor.parent = parent
        actor.animation_data_clear()
        animation = actor.animation_data_create()
        delay = 0 if i == 0 else FOLLOWER_OFFSETS[i - 1]
        strip = animation.nla_tracks.new().strips.new("Review choreography", 1 + delay, review)
        strip.action_slot = review.slots[0]
        strip.extrapolation = "HOLD"
        bird = mesh.copy()
        bird.name = "Review mesh | leader" if i == 0 else f"Review mesh | follower {i:02}"
        collection.objects.link(bird)
        bird.parent = actor
        bird.modifiers["GooseSkin"].object = actor
        if i:
            x, y = FLOCK_POSITIONS[i - 1]
            parent.location = (x / scale, y / scale, -2 / scale)
            parent.scale = (FOLLOWER_SCALE,) * 3
            bird.material_slots[0].link = "OBJECT"
            bird.material_slots[0].material = bpy.data.materials[f"Body_Follower_{'ABC'[(i - 1) % 3]}"]
        birds.append(bird)
    assert len({bird.data for bird in birds}) == 1
    return scene, group, birds, carriers[0]


def check_flock(scene, birds, scale):
    min_margin, min_clearance = math.inf, math.inf
    camera = scene.objects[REAR]
    floor = scene.objects["Review Ground"].location.z
    for frame in range(1, REVIEW_END + 1):
        scene.frame_set(frame)
        for bird in birds:
            points = EVAL(bird)
            bounds = TOOLS["frame_points"](camera, bird, points)
            margin = min(bounds[0], bounds[1], GAME_SIZE[0] - bounds[2], GAME_SIZE[1] - bounds[3])
            transform = bird.matrix_world
            clearance = scale * (float(points[:, 2].min()) * transform.to_scale().z
                                 + transform.translation.z - floor)
            assert margin > 0 and clearance > 0, (frame, bird.name, margin, clearance)
            min_margin, min_clearance = min(min_margin, margin), min(min_clearance, clearance)
    return {"frames": REVIEW_END, "birds": 12, "mesh_datablocks": 1,
            "follower_delays_frames": FOLLOWER_OFFSETS, "follower_xy_game_units": FLOCK_POSITIONS,
            "minimum_screen_margin_px": min_margin, "minimum_ground_clearance_game_units": min_clearance}


def preview_stills(scene, flock, carrier, output, draft=False):
    render = REF["render"]
    frames = {"recovery": CUT_1 + 1, "glide": GLIDE_IN + 19, "circle": CIRCLE_IN + 73}
    flock.hide_render = True
    for name, frame in frames.items():
        scene.frame_set(frame)
        render(scene, scene.objects[REAR], output, f"rear_1x_{name}", GAME_SIZE, 24)
        if name != "recovery":
            render(scene, scene.objects[TOP], output, f"top_{name}", (1040, 600), 24)
            if not draft:
                carrier.scale = (.5,) * 3
                bpy.context.view_layer.update()
                render(scene, scene.objects[REAR], output, f"rear_half_{name}", GAME_SIZE, 32)
                render(scene, scene.objects[TOP], output, f"top_half_{name}", (1040, 600), 24)
                carrier.scale = (1,) * 3
                bpy.context.view_layer.update()
    flock.hide_render = False
    scene.frame_set(frames["circle"])
    render(scene, scene.objects[REAR], output, "rear_flock_12", GAME_SIZE, 24)
    if not draft:
        render(scene, scene.objects[FLOCK_TOP], output, "top_flock_12", (1040, 600), 24)


def preview_video(scene, flock, view, size, output):
    flock.hide_render = view != REAR
    REF["render_settings"](scene, size, 8)
    scene.render.use_persistent_data = True
    scene.camera = scene.objects[view]
    with TemporaryDirectory(prefix="ft-anm003-frames-") as temporary:
        frames = Path(temporary)
        for i, frame in enumerate(range(1, REVIEW_END + 1, 2)):
            scene.frame_set(frame)
            scene.render.filepath = str(frames / f"{i:03}.png")
            bpy.ops.render.render(write_still=True, scene=scene.name)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-framerate", "24", "-i", str(frames / "%03d.png"),
            "-c:v", "libx264", "-crf", "16", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=black",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
        ], check=True)


def save_source(scene, review, rig, loops, output):
    bpy.context.window.scene = scene
    scene.camera = scene.objects[DETAIL]
    scene.frame_start, scene.frame_end = 1, PERIODS[GLIDE] + 1
    scene.use_preview_range = True
    scene.frame_preview_start, scene.frame_preview_end = 1, PERIODS[GLIDE]
    scene.render.filepath = "//"
    review.render.filepath = "//"
    REF["render_settings"](scene, (1040, 600), 24)
    REF["render_settings"](review, GAME_SIZE, 24)
    set_action(rig, loops[GLIDE])
    scene.frame_set(1)
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
    bpy.ops.wm.save_as_mainfile(filepath=str(output), compress=True)


def main(output, mode):
    output.mkdir(parents=True, exist_ok=True)
    assert not any(output.iterdir()), "Use an empty output directory to preserve existing versions."
    chr_manifest = json.loads((CHR / "asset_manifest.json").read_text())
    anm_manifest = json.loads((ANM / "asset_manifest.json").read_text())
    for manifest, paths in ((chr_manifest, (CHR_BLEND, CHR_GLB)), (anm_manifest, (CRUISE_BLEND,))):
        assert manifest["status"] == "done"
        for path in paths:
            assert DIGEST(path) == manifest["files"][path.name], path
    scale = chr_manifest["camera"]["preview_game_units_per_BU"]
    bpy.context.preferences.addons["io_scene_gltf2"].preferences.KHR_materials_variants_ui = True
    bpy.ops.wm.open_mainfile(filepath=str(CHR_BLEND))
    scene = bpy.context.scene
    scene.name = "ANM-003 | Editable loops"
    scene.render.fps = FPS
    rig, mesh = scene.objects["GooseRig"], scene.objects["Goose_LOD0"]
    assert len(rig.pose.bones) == 15 and rig.matrix_world.is_identity and mesh.matrix_world.is_identity
    assert len([i for i in bpy.data.images if i.packed_file]) == 4
    with bpy.data.libraries.load(str(CRUISE_BLEND), link=False) as (available, imported):
        assert "Cruise_Flap_Loop" in available.actions
        imported.actions = ["Cruise_Flap_Loop"]
    cruise, = imported.actions
    assert tuple(cruise.frame_range) == (1, 53) and cruise.use_cyclic
    loops = author_loops(rig)
    review = build_review(rig, cruise, loops)
    scene["Actions"] = "Glide_Loop 1–73 | Circle_Loop 1–97 | 48 fps"
    scene["Source"] = "CHR-001/v001 mesh, skin and packed plumage"
    scene["Review"] = "Switch scenes to Review | Glide and left circle for the staged handoff"
    if mode == "draft":
        review_copy, flock, _, carrier = review_scene(scene, mesh, rig, review, scale)
        bpy.context.window.scene = review_copy
        preview_stills(review_copy, flock, carrier, output, draft=True)
        return

    qa, motion = measure(scene, mesh, rig, loops, cruise, review, scale)
    asset = output / "ANM-003_glide_circle.glb"
    qa["glb"] = export_loops(scene, mesh, rig, loops, asset)
    qa["glb_roundtrip"] = verify_roundtrip(scene, mesh, rig, loops, asset, motion, mode == "full")
    review_copy, flock, birds, carrier = review_scene(scene, mesh, rig, review, scale)
    bpy.context.window.scene = review_copy
    qa["flock"] = check_flock(review_copy, birds, scale)
    review_copy.frame_set(1)
    save_source(scene, review_copy, rig, loops, output / "ANM-003_glide_circle.blend")
    DUMP(output / "qa.json", {"id": "ANM-003", "version": "v001", "status": "needs_review", "blender": qa})
    if mode == "full":
        bpy.context.window.scene = review_copy
        preview_stills(review_copy, flock, carrier, output)
        preview_video(review_copy, flock, DETAIL, (864, 480), output / "preview_rear_detail.mp4")
        preview_video(review_copy, flock, REAR, GAME_SIZE, output / "preview_rear_flock_12.mp4")
    DUMP(output / "asset_manifest.json", {
        "id": "ANM-003", "version": "v001", "status": "needs_review", "blender": bpy.app.version_string,
        "dependencies": {"CHR-001/v001": "done", "ANM-001/v001": "done"},
        "source_hashes": {str(p.relative_to(LIBRARY)): DIGEST(p) for p in (
            CHR_BLEND, CHR_GLB, CRUISE_BLEND, ANM / "ANM-001_cruise_flap_generate.py",
            CHR / "CHR-001_goose_rig_generate.py",
        )},
        "source": "Original in-place Blender actions on approved CHR-001/v001. Uses ANM-001 source curves for review transition.",
        "rights": "Project-original animation with existing CHR-001 packed plumage. No external assets or attribution.",
        "clips": {n: {"frames": [1, p + 1], "fps": FPS, "seconds": p / FPS, "seam_frame": p + 1,
                      "cyclic_bezier": True, "root_motion": False} for n, p in PERIODS.items()},
        "review": {"cruise_source_frame": CRUISE_FRAME, "cruise_phase": (CRUISE_FRAME - 1) / 52,
                   "transition_to_glide_frames": ENTER_GLIDE, "unblended_glide_hold_frames": HOLD_GLIDE,
                   "transition_to_circle_frames": ENTER_CIRCLE, "bank_direction": "left wing down",
                   "blend_curve": "smootherstep; outgoing cruise phase brakes over six frames to f52",
                   "camera": chr_manifest["camera"], "follower_scale": FOLLOWER_SCALE},
        "character": {"triangles_lod0": 3940, "bones": 15, "pivot_BU": [0, 0, 0], "scale": [1, 1, 1],
                      "axes_blender": chr_manifest["axes_blender"], "axes_gltf": chr_manifest["axes_gltf"]},
        "variants": chr_manifest["variants"], "texture_mapping": chr_manifest["texture_mapping"],
        "files": {p.name: DIGEST(p) for p in [Path(__file__), *sorted(output.iterdir())] if p.name != "qa.json"},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=["draft", "checks", "full"], default="full")
    options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    main(options.output.resolve(), options.mode)
