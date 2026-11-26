"""Build Bank_R, verify it against the Bank_L source, and render review evidence."""
import argparse
import json
import math
import runpy
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

HERE = Path(__file__).resolve().parent
LEFT = HERE.parents[1] / "ANM-004" / "v001"
LEFT_SCRIPT = LEFT / "ANM-004_bank_left_generate.py"
LEFT_BLEND = LEFT / "ANM-004_bank_left.blend"
L = runpy.run_path(str(LEFT_SCRIPT))
REF, TOOLS = L["REF"], L["TOOLS"]
CHR, CHR_BLEND, CHR_GLB, CRUISE_BLEND = (L[k] for k in ("CHR", "CHR_BLEND", "CHR_GLB", "CRUISE_BLEND"))
TIME, EVAL, DIGEST, DUMP = (L[k] for k in ("TIME", "EVAL", "DIGEST", "DUMP"))
curves, make_action, set_action, sample_action = (L[k] for k in ("curves", "make_action", "set_action", "sample_action"))
FPS, END, ENTER, ENGAGE, RELEASE, RESUME = (L[k] for k in ("FPS", "END", "ENTER", "ENGAGE", "RELEASE", "RESUME"))
REVIEW_END, REAR, DETAIL, TOP, GAME_SIZE = (L[k] for k in ("REVIEW_END", "REAR", "DETAIL", "TOP", "GAME_SIZE"))
CLIP, STEM = "Bank_R", "ANM-005_bank_right"
SWAP_END = 129
SWAP_MARKERS = [(1, "Left hold"), (13, "Release left"), (37, "Neutral"),
                (61, "Right hold"), (69, "Release right"), (93, "Neutral"),
                (117, "Left hold"), (SWAP_END, "End")]


def append_action(path, name):
    with bpy.data.libraries.load(str(path), link=False) as (available, imported):
        assert name in available.actions
        imported.actions = [name]
    action, = imported.actions
    return action


def pose_mirror(rig, left, frame, variation=True):
    # Reflect in the character's sagittal plane, then express the reflected
    # delta in the destination bone's original CHR-001 basis.
    reflection = Matrix.Diagonal((-1., 1., 1.))
    values = sample_action(left, frame)
    result = {}
    u = L["clamp"]((frame - 1) / (END - 1))
    for bone in rig.pose.bones:
        name = bone.name
        counterpart = name[:-1] + ("R" if name[-1] == "L" else "L") if name.endswith((".L", ".R")) else name
        original = rig.pose.bones[counterpart]
        src = original.path_from_id("rotation_euler")
        if not any((src, i) in values for i in range(3)):
            continue
        basis = bone.bone.matrix_local.to_3x3()
        old_basis = original.bone.matrix_local.to_3x3()
        rotation = Euler(tuple(values.get((src, i), 0.) for i in range(3)), "XYZ").to_matrix()
        world = reflection @ old_basis @ rotation @ old_basis.transposed() @ reflection
        local = basis.transposed() @ world @ basis
        if variation:
            # The inside wrist eases a little more; the trailing tip variation
            # resolves by the hold. Neither changes torso bank or head direction.
            if name == "Wrist.R":
                local @= Matrix.Rotation(math.radians(.65 * L["smoothstep"](u)), 3, "Y")
            if name == "Tip.R":
                local @= Matrix.Rotation(math.radians(-1.1 * math.sin(math.pi * u)**2), 3, "X")
        dst = bone.path_from_id("rotation_euler")
        result.update({(dst, i): v for i, v in enumerate(local.to_euler("XYZ"))})
    return result


def swap_strength(frame):
    for (a, _), (b, _), start, end in zip(SWAP_MARKERS, SWAP_MARKERS[1:],
                                            (-1, -1, 0, 1, 1, 0, -1), (-1, 0, 1, 1, 0, -1, -1)):
        if frame <= b:
            return start + (end - start) * L["smoothstep"](L["clamp"]((frame - a) / (b - a)))
    return -1.


def make_swap(rig, left, right):
    keys = set(sample_action(left, 1)) | set(sample_action(right, 1))

    def pose(frame):
        w = swap_strength(frame)
        values = sample_action(left if w < 0 else right, 1 + (END - 1) * abs(w))
        return {key: values.get(key, 0.) for key in keys}

    return make_action(rig, "Review | Bank_L to Bank_R and back", pose, list(range(1, SWAP_END + 1)))


def author(rig, left, cruise):
    bank = make_action(rig, CLIP, lambda frame: pose_mirror(rig, left, frame), [1, 5, 9, 13, 17, 21, 25])
    bank.asset_mark()
    bank.asset_data.description = "ANM-005 | right bank mirrored from Bank_L, with wrist and tip accents"
    for frame, name in ((1, "Neutral"), (13, "Half strength"), (25, "Full right bank")):
        bank.pose_markers.new(name).frame = frame
    keys = set(sample_action(cruise, 1)) | set(sample_action(bank, 1))
    review = {
        strength: make_action(rig, name,
                              lambda frame: L["review_pose"](cruise, bank, keys, frame, strength),
                              list(range(1, REVIEW_END + 1)))
        for strength, name in ((1., "Review | Cruise and right bank"), (.5, "Review | Half right and release"))
    }
    return bank, review, make_swap(rig, left, bank)


def validate(scene, mesh, rig, left, bank, review, swap, cruise, scale):
    scan = L["scan"]
    motion, left_signed, metrics = scan(scene, mesh, rig, bank, 1, END, scale)
    angles = -np.array(left_signed)
    metrics.pop("body_left_bank_range_deg")
    assert abs(angles[0]) < 1e-5 and abs(angles[-1] - 12) < 1e-5 and np.diff(angles).min() > -1e-4
    metrics["right_bank_deg_by_strength"] = {str(w): float(angles[int(w * 48)]) for w in (0, .25, .5, .75, 1)}
    set_action(rig, left)
    right_vector = rig.data.bones["Body"].matrix_local.to_3x3().inverted() @ Vector((1, 0, 0))
    mirror_error = 0.
    for frame, angle in zip(motion, angles):
        TIME(scene, frame)
        direction = rig.pose.bones["Body"].matrix.to_3x3() @ right_vector
        left_angle = math.degrees(math.atan2(direction.z, direction.x))
        mirror_error = max(mirror_error, abs(angle - left_angle))
    assert mirror_error < .001, mirror_error
    metrics["max_body_bank_mirror_error_deg"] = float(mirror_error)

    # Compare actual skinned vertices against the exact mirrored left action,
    # whose bone bases are reconstructed independently of the Euler curves.
    from mathutils.kdtree import KDTree
    lookup = KDTree(len(mesh.data.vertices))
    for vertex in mesh.data.vertices:
        lookup.insert(vertex.co, vertex.index)
    lookup.balance()
    mirror_indices = []
    for vertex in mesh.data.vertices:
        _, index, distance = lookup.find((-vertex.co.x, vertex.co.y, vertex.co.z))
        assert distance < 1e-6
        mirror_indices.append(index)
    geometric_delta = 0.
    for frame, expected in motion.items():
        TIME(scene, frame)
        reflected = EVAL(mesh)[mirror_indices] * [-1, 1, 1]
        geometric_delta = max(geometric_delta, float(np.linalg.norm(expected - reflected, axis=1).max()))
    assert .0001 < geometric_delta < .012, geometric_delta
    metrics["max_vertex_delta_from_exact_mirror_BU"] = geometric_delta

    def joins(poses, frames):
        report = {}
        for f in frames:
            step = .02
            TIME(scene, f - step)
            before = EVAL(mesh)
            TIME(scene, f + step)
            after = EVAL(mesh)
            speed = float(np.linalg.norm(before + after - 2 * poses[f], axis=1).max() * FPS / step)
            assert speed < .008, (f, speed)
            report[str(f)] = {"velocity_difference_BU_per_s": speed}
        return report

    reports = {}
    for strength, action in review.items():
        poses, left_signed, data = scan(scene, mesh, rig, action, 1, REVIEW_END, scale)
        data.pop("body_left_bank_range_deg")
        held = -left_signed[2 * (RELEASE - 1)]
        assert abs(held - 12 * L["smoothstep"](strength)) < .001
        data["held_right_bank_deg"] = held
        data["joins"] = joins(poses, (ENGAGE, ENGAGE + ENTER, RELEASE, RESUME))
        set_action(rig, cruise)
        for f, phase in ((ENGAGE, 49), (RESUME, 52)):
            TIME(scene, phase)
            error = float(np.linalg.norm(poses[f] - EVAL(mesh), axis=1).max())
            assert error < 1e-6
            data["joins"][str(f)]["cruise_pose_error_BU"] = error
        reports[str(strength)] = data

    poses, left_signed, data = scan(scene, mesh, rig, swap, 1, SWAP_END, scale)
    signed = -np.array(left_signed)
    data.pop("body_left_bank_range_deg")
    for f, expected in ((13, -12), (37, 0), (61, 12), (69, 12), (93, 0), (117, -12)):
        assert abs(signed[2 * (f - 1)] - expected) < .001
    assert np.diff(signed[24:121]).min() > -1e-4 and np.diff(signed[136:233]).max() < 1e-4
    neutral = float(np.linalg.norm(poses[37] - motion[1], axis=1).max())
    assert neutral < 1e-6 and np.linalg.norm(poses[93] - motion[1], axis=1).max() < 1e-6
    data["neutral_pose_error_BU"] = neutral
    data["right_positive_bank_by_marker_deg"] = {str(f): float(signed[2 * (f - 1)]) for f, _ in SWAP_MARKERS}
    data["joins"] = joins(poses, [f for f, _ in SWAP_MARKERS[1:-1]])
    return motion, {"bank": metrics, "cruise_transitions": reports, "bidirectional_switch": data}


def reverse_preview_trajectory(scene, path, route):
    # Mirror only the staging Empty. The camera follows its heading and the
    # character poses stay on their own action slots.
    for curve in curves(path.animation_data.action):
        if (curve.data_path, curve.array_index) in {("location", 0), ("rotation_euler", 2)}:
            for key in curve.keyframe_points:
                key.co.y *= -1
            curve.update()
    scene.frame_set(1)
    return [(-x, y) for x, y in route]


def swap_studio(source, mesh, rig, action):
    scene = bpy.data.scenes.new("Review | Left and right transitions")
    scene.world = source.world
    scene.collection.children.link(bpy.data.collections["Review cameras and lights"])
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, SWAP_END
    scene.camera = source.objects[DETAIL]
    actor = rig.copy()
    scene.collection.objects.link(actor)
    actor.name = "Switch review rig"
    actor.animation_data_clear()
    actor.animation_data_create()
    set_action(actor, action)
    bird = mesh.copy()
    scene.collection.objects.link(bird)
    bird.name = "Switch review mesh"
    bird.parent = actor
    bird.modifiers["GooseSkin"].object = actor
    for frame, label in SWAP_MARKERS:
        scene.timeline_markers.new(label, frame=frame)
    scene.frame_set(37)
    return scene


def save_source(scene, review, switching, rig, bank, output):
    bpy.context.window.scene = scene
    set_action(rig, bank)
    scene.frame_set(END)
    scene.camera = scene.objects[DETAIL]
    scene["Playback"] = "Bank_R: neutral to 12 degrees right. Switch review scenes for cruise or left/right transitions."
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    for current, size in ((scene, (1040, 600)), (review, GAME_SIZE), (switching, (864, 480))):
        REF["render_settings"](current, size, 24)
        current.render.filepath = "//"
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.region_3d.view_perspective = "CAMERA"
                space.overlay.show_overlays = False
                space.shading.color_type = "TEXTURE"
    bpy.ops.wm.save_as_mainfile(filepath=str(output), compress=True)


def reuse(name, **settings):
    # Use the same export and render paths as Bank_L with the clip-specific
    # constants injected into a separate function namespace.
    from types import FunctionType
    original = L[name]
    context = {**original.__globals__, **settings}
    return FunctionType(original.__code__, context, name, original.__defaults__, original.__closure__)


def main(output, mode):
    output.mkdir(parents=True, exist_ok=True)
    assert not any(output.iterdir()), "Choose an empty output directory."
    chr_manifest = json.loads((CHR / "asset_manifest.json").read_text())
    left_manifest = json.loads((LEFT / "asset_manifest.json").read_text())
    cruise_manifest = json.loads((CRUISE_BLEND.parent / "asset_manifest.json").read_text())
    assert chr_manifest["status"] == cruise_manifest["status"] == "done"
    assert left_manifest["status"] in ("needs_review", "done")
    for manifest, paths in ((chr_manifest, (CHR_BLEND, CHR_GLB)),
                            (left_manifest, (LEFT_BLEND, LEFT_SCRIPT)), (cruise_manifest, (CRUISE_BLEND,))):
        for path in paths:
            assert DIGEST(path) == manifest["files"][path.name], path

    bpy.context.preferences.addons["io_scene_gltf2"].preferences.KHR_materials_variants_ui = True
    bpy.ops.wm.open_mainfile(filepath=str(CHR_BLEND))
    scene = bpy.context.scene
    scene.name = "ANM-005 | Editable Bank_R"
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, END
    rig, mesh = scene.objects["GooseRig"], scene.objects["Goose_LOD0"]
    scale = chr_manifest["camera"]["preview_game_units_per_BU"]
    assert len(rig.pose.bones) == 15 and len([img for img in bpy.data.images if img.packed_file]) == 4
    left = append_action(LEFT_BLEND, "Bank_L")
    left.use_fake_user = True
    cruise = append_action(CRUISE_BLEND, "Cruise_Flap_Loop")
    assert tuple(left.frame_range) == (1, END) and tuple(cruise.frame_range) == (1, 53)
    bank, actions, swap = author(rig, left, cruise)
    scene.objects[L["HELPERS"]["DETAIL"]].name = DETAIL
    detail = scene.objects[DETAIL]
    detail.location = (0, -1.65, .96)
    detail.rotation_euler = (Vector((0, .06, .09)) - detail.location).to_track_quat("-Z", "Y").to_euler()
    qa = {}
    if mode != "draft":
        motion, qa = validate(scene, mesh, rig, left, bank, actions, swap, cruise, scale)
        glb = output / f"{STEM}.glb"
        qa["glb"] = reuse("export_bank", CLIP=CLIP)(scene, mesh, rig, bank, glb)
        qa["blender_reimport"] = reuse("reimport", CLIP=CLIP)(scene, mesh, rig, bank, motion, glb, mode == "full")

    review, followers, birds, cameras, carrier, route = L["review_studio"](scene, mesh, rig, actions[1.], scale)
    review.name = "Review | Cruise to right turn"
    for marker in review.timeline_markers:
        if marker.name == "Full left":
            marker.name = "Full right"
    window = bpy.context.window
    window.scene = review
    route = reverse_preview_trajectory(review, carrier, route)
    qa["flock"] = L["check_flock"](review, birds, cameras, carrier, scale)
    assert qa["flock"]["preview_heading_change_deg"] < 0
    review.frame_set(RELEASE - 2)
    switching = swap_studio(scene, mesh, rig, swap)
    if mode != "draft":
        save_source(scene, review, switching, rig, bank, output / f"{STEM}.blend")
    if mode in ("draft", "full"):
        window.scene = review
        L["stills"](review, followers, birds, cameras, output)
        if mode == "full":
            followers.hide_render = True
            L["video"](review, cameras[DETAIL], (864, 480), output / "preview_rear_detail.mp4")
            followers.hide_render = False
            L["video"](review, cameras[REAR], GAME_SIZE, output / "preview_rear_flock_12.mp4")
            followers.hide_render = True
            L["render_route"](review, route, output)
        window.scene = switching
        for label, frame in (("left", 13), ("neutral", 37), ("right", 61)):
            switching.frame_set(frame)
            REF["render"](switching, detail, output, f"switch_{label}", (864, 480), 24)
        if mode == "full":
            reuse("video", REVIEW_END=SWAP_END)(switching, detail, (864, 480),
                                              output / "preview_switch_both_directions.mp4")

    if mode == "draft":
        return
    DUMP(output / "qa.json", {"id": "ANM-005", "version": "v001", "status": "needs_review", "blender": qa})
    DUMP(output / "asset_manifest.json", {
        "id": "ANM-005", "version": "v001", "status": "needs_review", "blender": bpy.app.version_string,
        "dependencies": {"CHR-001/v001": "done", "ANM-004/v001": left_manifest["status"]},
        "review_reference": "ANM-001/v001",
        "source": "Bank_L source curves reflected across the character sagittal plane, with wrist and tip variations.",
        "rights": "Project-original animation and CHR-001 packed plumage.",
        "source_hashes": {str(path.relative_to(HERE.parents[1])): DIGEST(path)
                          for path in (CHR_BLEND, CHR_GLB, LEFT_BLEND, LEFT_SCRIPT, CRUISE_BLEND, L["SUPPORT"],
                                       CRUISE_BLEND.parent / "ANM-001_cruise_flap_generate.py",
                                       CHR / "CHR-001_goose_rig_generate.py")},
        "clip": {"name": CLIP, "frames": [1, END], "fps": FPS, "duration_s": (END - 1) / FPS,
                 "sampling": "t=0.5s × normalized right-turn strength, hold sample",
                 "bank_right_deg": 12, "root_motion": False, "loop": False,
                 "inside_wrist_variation_deg": .65, "inside_tip_variation_peak_deg": 1.1},
        "review": {"cruise_entry_frame": ENGAGE, "cruise_entry_phase": (ENGAGE - 1) / 52,
                   "cruise_exit_frame": 52, "entry_s": ENTER / FPS,
                   "hold_s": (RELEASE - ENGAGE - ENTER) / FPS, "exit_s": (RESUME - RELEASE) / FPS,
                   "switch_markers": dict(SWAP_MARKERS), "opposite_hold_to_hold_s": 1.,
                   "camera": chr_manifest["camera"], "follower_scale": .8},
        "character": {"triangles_lod0": 3940, "bones": 15, "pivot_BU": [0, 0, 0], "scale": [1, 1, 1],
                      "axes_blender": chr_manifest["axes_blender"], "axes_gltf": chr_manifest["axes_gltf"]},
        "variants": chr_manifest["variants"], "texture_mapping": chr_manifest["texture_mapping"],
        "files": {path.name: DIGEST(path) for path in [Path(__file__), *sorted(output.iterdir())]},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=["draft", "checks", "full"], default="full")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    main(args.output.resolve(), args.mode)
