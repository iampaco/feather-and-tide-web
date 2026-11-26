"""Build Formation_Blend and a separate animated formation review scene."""
import argparse
import json
import math
import runpy
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import FunctionType

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
CHR = LIBRARY / "CHR-001" / "v001"
ANM = LIBRARY / "ANM-001" / "v001"
CHR_BLEND = CHR / "CHR-001_goose_rig.blend"
CHR_GLB = CHR / "CHR-001_goose_rig.glb"
CRUISE_BLEND = ANM / "ANM-001_cruise_flap.blend"
CRUISE_SCRIPT = ANM / "ANM-001_cruise_flap_generate.py"
TOOLS = runpy.run_path(str(CRUISE_SCRIPT))
REF = TOOLS["REFERENCE"]
BLEND_SCRIPT = LIBRARY / "ANM-003" / "v001" / "ANM-003_glide_circle_generate.py"
BLEND = runpy.run_path(str(BLEND_SCRIPT))
TIME, EVAL, DIGEST, DUMP = (TOOLS[key] for key in ("time_set", "evaluated", "digest", "dump"))
curves, make_action, set_action, sample_action, smoothstep = (
    BLEND[key] for key in ("curves", "make_action", "set_action", "sample_action", "smoothstep")
)

STEM, CLIP = "ANM-006_formation_blend", "Formation_Blend"
FPS, PERIOD = 48, 52
START, LOCK, REVIEW_END = 53, 149, 201
GAME = (852, 393)
REAR, TOP, DETAIL = BLEND["REAR"], BLEND["TOP"], BLEND["DETAIL"]
OVERHEAD = "Review | formation overhead"
FOLLOWER_PHASES = [9, 20, 5, 31, 15, 37, 13, 45, 24, 43, 29]
LOOSE_SLOTS = [(-34,-10), (34,-11), (-41,-25), (41,-27), (-48,-42), (47,-44),
               (-54,-56), (53,-60), (-60,-70), (59,-74), (-66,-83)]
V_SLOTS = [(((-1) ** (i + 1)) * (26 + 6 * (i // 2)), -13 * (i // 2 + 1)) for i in range(11)]


def scaled_action(cruise):
    action = cruise.copy()
    action.name = CLIP
    action.asset_mark()
    action.asset_data.description = "ANM-006 | phase-aligned, quieter flap for sustained formation"
    factors = {"WingRoot": .74, "Elbow": .72, "Wrist": .67, "Tip": .68,
               "Body": .44, "Neck": .44, "Head": .44, "Tail": .55}
    for curve in curves(action):
        part = curve.data_path.split('"')[1].split(".")[0]
        scale = .42 if curve.data_path.endswith(".location") else factors[part]
        for key in curve.keyframe_points:
            # Scale values and tangents together to preserve timing and the
            # original spline through the recovery seam.
            left, value, right = key.handle_left.y, key.co.y, key.handle_right.y
            key.co.y = value * scale
            key.handle_left.y, key.handle_right.y = left * scale, right * scale
        curve.update()
    return action


def phase(frame, offset):
    return 1 + (frame - 1 + offset) % PERIOD


def weight(frame):
    return smoothstep(max(0., min(1., (frame - START) / (LOCK - START))))


def preview_action(rig, cruise, formation, offset):
    def pose(frame):
        at = phase(frame, offset)
        a, b = sample_action(cruise, at), sample_action(formation, at)
        w = weight(frame)
        return {key: a[key] * (1 - w) + b[key] * w for key in a}

    return make_action(rig, f"Review blend | phase +{offset:02}f", pose,
                       list(range(1, REVIEW_END + 1)))


def check_amplitudes(scene, rig, cruise, formation):
    def ranges(action):
        set_action(rig, action)
        samples = []
        for i in range(2, 2 * (PERIOD + 1) + 1):
            TIME(scene, i / 2)
            b = rig.pose.bones
            samples.append([math.degrees(b["WingRoot.R"].rotation_euler.x),
                            math.degrees(b["Wrist.R"].rotation_euler.x),
                            math.degrees(b["Body"].rotation_euler.x), float(b["Body"].head.z),
                            float(b["Neck"].head.z)])
        return dict(zip(("wing_root_deg", "wrist_deg", "body_pitch_deg", "body_lift_BU", "neck_base_z_BU"),
                        map(float, np.ptp(np.array(samples), axis=0))))
    before, after = ranges(cruise), ranges(formation)
    assert all(after[key] < before[key] for key in before)
    assert abs(after["wing_root_deg"] / before["wing_root_deg"] - .74) < 1e-5
    return {"cruise_peak_to_peak": before, "formation_peak_to_peak": after}


def check_blends(scene, mesh, rig, cruise, formation, scale):
    parts = TOOLS["mesh_parts"](mesh.data)
    flight = [part for part in parts if part.startswith(("Outer primary", "Flight feather 7", "Flight feather 8", "Flight feather 9"))]
    pairs = [("Body and crown", part) for part in flight]
    pairs += [("Wing.L", "Wing.R"), ("Foot.L", "Foot.R")]
    pairs += [(part, f"Wing.{s}") for s in "LR" for part in ("Bill", f"Foot.{s}")]
    tip_indices = np.unique([i for part in flight for tri in parts[part] for i in tri])
    edges = np.array([tuple(edge.vertices) for edge in mesh.data.edges])
    rest = np.array([tuple(v.co) for v in mesh.data.vertices])
    edge_rest = np.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
    head = rig.pose.bones["Head"]
    forward = head.bone.matrix_local.to_3x3().inverted() @ Vector((0, 1, 0))
    reports = {}
    for offset in (0, 13, 26, 39):
        action = preview_action(rig, cruise, formation, offset)
        set_action(rig, action)
        boundary, low, low_tip = {}, math.inf, math.inf
        edge_range, head_error = [1., 1.], 0.
        for index in range(2 * START, 2 * LOCK + 1):
            f = index / 2
            TIME(scene, f)
            root = rig.pose.bones["Root"]
            assert rig.matrix_world.is_identity and root.matrix_basis.is_identity and root.head.length < 1e-8
            points = EVAL(mesh)
            assert np.isfinite(points).all()
            if f in (START, LOCK):
                boundary[f] = points
            low = min(low, float(points[:, 2].min()))
            low_tip = min(low_tip, float(points[tip_indices, 2].min()))
            stretch = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1) / edge_rest
            edge_range = [min(edge_range[0], float(stretch.min())), max(edge_range[1], float(stretch.max()))]
            head_error = max(head_error, math.degrees((head.matrix.to_3x3() @ forward).angle(
                Vector((0, 1, 0)))))
            vertices = [tuple(v) for v in points]
            trees = {part: BVHTree.FromPolygons(vertices, faces, all_triangles=True) for part, faces in parts.items()}
            assert all(trees["Body and crown"].overlap(trees[f"Wing.{side}"]) for side in "LR"), (offset, f)
            assert not [(a, b) for a, b in pairs if trees[a].overlap(trees[b])], (offset, f)
        assert .58 < edge_range[0] and edge_range[1] < 1.45 and head_error < .05
        assert 6 + .8 * scale * low > 0
        joins = {}
        for f, target in ((START, cruise), (LOCK, formation)):
            set_action(rig, target)
            TIME(scene, phase(f, offset))
            position_error = float(np.linalg.norm(EVAL(mesh) - boundary[f], axis=1).max())
            set_action(rig, action)
            step = .02
            TIME(scene, f - step)
            before = EVAL(mesh)
            TIME(scene, f + step)
            after = EVAL(mesh)
            velocity_delta = float(np.linalg.norm(before + after - 2 * boundary[f], axis=1).max() * FPS / step)
            assert position_error < 1e-6 and velocity_delta < .025, (offset, f, position_error, velocity_delta)
            joins[str(f)] = {"phase_frame": phase(f, offset), "position_BU": position_error,
                             "velocity_delta_BU_per_s": velocity_delta}
        reports[str(offset)] = {"samples": 2 * (LOCK - START) + 1, "joins": joins,
                                "edge_ratio_range": edge_range, "head_forward_max_deg": head_error,
                                "min_mesh_clearance_game_units": [8 + scale * low, 6 + .8 * scale * low],
                                "min_tip_clearance_game_units": [8 + scale * low_tip, 6 + .8 * scale * low_tip]}
        rig.animation_data.action = None
        bpy.data.actions.remove(action)
    return {"phase_offsets_frames": reports, "step_frames": .5,
            "shoulders_root_and_specified_intersections": "pass", "specified_pairs": pairs}


def cruise_helper(name, **settings):
    # Keep the accepted single-clip export and import code, with this clip's
    # name and validation settings in an isolated namespace.
    original = TOOLS[name]
    context = {**original.__globals__, **settings}
    return FunctionType(original.__code__, context, name, original.__defaults__, original.__closure__)


def export_and_reimport(scene, mesh, rig, formation, motion, output, render):
    set_action(rig, formation)
    path = output / f"{STEM}.glb"
    export = cruise_helper("export_glb", CLIP=CLIP)(scene, mesh, rig, path)
    doc, binary = REF["load_glb"](path)
    original, original_binary = REF["load_glb"](CHR_GLB)
    skin, = doc["skins"]
    base_skin, = original["skins"]
    assert len(doc["nodes"]) == len(original["nodes"]) == 17
    assert skin["joints"] == base_skin["joints"]
    assert TOOLS["packed_accessor"](doc, binary, doc["accessors"][skin["inverseBindMatrices"]]) == (
        TOOLS["packed_accessor"](original, original_binary, original["accessors"][base_skin["inverseBindMatrices"]]))
    assert doc["materials"] == original["materials"] and doc["meshes"] == original["meshes"]
    assert not doc.get("cameras") and len(doc["scenes"]) == 1 and len(doc["animations"]) == 1
    export["one_character_no_review_carriers"] = "pass"
    export["same_inverse_bind_matrices_and_materials"] = "pass"

    formation.name = "Source | Formation_Blend"
    blocks = (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.images, bpy.data.actions)
    existing = [set(block) for block in blocks]
    result = cruise_helper("roundtrip", CLIP=CLIP)(scene, mesh, rig, path, output, motion, render)
    bpy.data.batch_remove(ids=set().union(*(set(block) - before for block, before in zip(blocks, existing))))
    formation.name = CLIP
    return export, result


def make_review(source, mesh, rig, cruise, formation, scale):
    scene = bpy.data.scenes.new("Review | Loose flock to V")
    scene.world = source.world
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, REVIEW_END - 1
    scene.collection.children.link(bpy.data.collections["Review cameras and lights"])
    scene.camera = scene.objects[REAR]
    REF["camera"](scene.collection, OVERHEAD, (0, -1.3, 8), (0, -1.3, 0), ortho=8.3)
    followers = REF["collection"](scene, "Review | 11 followers")
    birds = []
    for i, offset in enumerate([0, *FOLLOWER_PHASES]):
        group = followers if i else scene.collection
        carrier = bpy.data.objects.new(f"Preview carrier | {i:02}", None)
        group.objects.link(carrier)
        actor = rig.copy()
        actor.name = f"Review rig | {i:02}"
        group.objects.link(actor)
        actor.parent = carrier
        actor.animation_data_clear()
        actor.animation_data_create()
        set_action(actor, preview_action(rig, cruise, formation, offset))
        bird = mesh.copy()
        bird.name = f"Review mesh | {i:02}"
        group.objects.link(bird)
        bird.parent = actor
        bird.modifiers["GooseSkin"].object = actor
        birds.append(bird)
        if i:
            x0, y0 = LOOSE_SLOTS[i - 1]
            x1, y1 = V_SLOTS[i - 1]
            for frame in (START, LOCK):
                x, y = (x0, y0) if frame == START else (x1, y1)
                carrier.location = (x / scale, y / scale, -2 / scale)
                carrier.keyframe_insert("location", frame=frame)
            for c in curves(carrier.animation_data.action):
                for key in c.keyframe_points:
                    key.handle_left_type = key.handle_right_type = "AUTO_CLAMPED"
            carrier.scale = (.8,) * 3
            bird.material_slots[0].link = "OBJECT"
            bird.material_slots[0].material = bpy.data.materials[f"Body_Follower_{'ABC'[(i - 1) % 3]}"]
    for frame, name in ((1, "Cruise"), (START, "Form-up begins"), (101, "One second"),
                        (LOCK, "Formed | quiet flap"), (REVIEW_END, "Loop boundary sample")):
        scene.timeline_markers.new(name, frame=frame)
    return scene, followers, birds


def check_flock(scene, birds, cruise, formation, scale):
    assert len(birds) == 12 and len({b.data for b in birds}) == 1
    camera = scene.objects[REAR]
    floor = scene.objects["Review Ground"].location.z
    margin, clearance, gap, pose_error = math.inf, math.inf, math.inf, 0.
    # Review carriages are spaced independently of the per-bird animation.
    # Check body placement and wing mesh intersections for near neighbors.
    mesh = birds[0].data
    mesh.calc_loop_triangles()
    triangles = [tuple(tri.vertices) for tri in mesh.loop_triangles]
    intersections = {}
    clipped = {}
    for f in range(1, REVIEW_END + 1):
        scene.frame_set(f)
        world_meshes, bounds, centers = [], [], []
        for index, bird in enumerate(birds):
            pose = EVAL(bird)
            t = bird.matrix_world
            box = TOOLS["frame_points"](camera, bird, pose)
            padding = min(box[0], box[1], GAME[0] - box[2], GAME[1] - box[3])
            if padding <= 0:
                clipped[index] = min(clipped.get(index, 0), padding)
            margin = min(margin, padding)
            p = pose @ np.array(t.to_3x3()).T + np.array(t.translation)
            clearance = min(clearance, float((p[:, 2].min() - floor) * scale))
            world_meshes.append(p)
            bounds.append((p.min(axis=0), p.max(axis=0)))
            centers.append(np.array(t.translation))
            offset = 0 if not index else FOLLOWER_PHASES[index - 1]
            a = sample_action(cruise, phase(f, offset))
            b = sample_action(formation, phase(f, offset))
            review = sample_action(bird.parent.animation_data.action, f)
            w = weight(f)
            pose_error = max(pose_error, max(abs(review[k] - (a[k] * (1 - w) + b[k] * w)) for k in a))
        trees = {}
        for a in range(len(birds)):
            for b in range(a + 1, len(birds)):
                gap = min(gap, float(np.linalg.norm(centers[a] - centers[b]) * scale))
                if np.any(bounds[a][1] < bounds[b][0]) or np.any(bounds[b][1] < bounds[a][0]):
                    continue
                for index in (a, b):
                    if index not in trees:
                        trees[index] = BVHTree.FromPolygons([tuple(v) for v in world_meshes[index]],
                                                            triangles, all_triangles=True)
                if trees[a].overlap(trees[b]):
                    intersections.setdefault((a,b), []).append(f)
    assert margin > 0 and clearance > 0 and pose_error < 1e-6 and not intersections, (
        margin, clearance, pose_error, clipped, {k:(min(v),max(v),len(v)) for k,v in intersections.items()})
    return {"samples_integer_frames": REVIEW_END, "birds": 12, "shared_mesh_datablocks": 1,
            "phase_offsets_frames": [0, *FOLLOWER_PHASES], "min_screen_margin_px": margin,
            "min_mesh_clearance_game_units": clearance, "min_carrier_spacing_game_units": gap,
            "interbird_mesh_intersections": sum(map(len, intersections.values())), "max_pose_channel_error": pose_error,
            "v_slot_offsets_game_xy": V_SLOTS, "loose_slot_offsets_game_xy": LOOSE_SLOTS}


def render_stills(scene, followers, birds, output):
    render = REF["render"]
    followers.hide_render = True
    for label, frame in (("cruise", 11), ("formed", LOCK + 18), ("formed_downstroke", LOCK + 37)):
        scene.frame_set(frame)
        render(scene, scene.objects[REAR], output, f"rear_1x_{label}", GAME, 24)
    scene.frame_set(LOCK + 18)
    render(scene, scene.objects[TOP], output, "top_1x_formed", (1040, 600), 24)
    carrier = birds[0].parent.parent
    carrier.scale = (.5,) * 3
    bpy.context.view_layer.update()
    render(scene, scene.objects[REAR], output, "rear_half_formed", GAME, 28)
    render(scene, scene.objects[TOP], output, "top_half_formed", (1040, 600), 24)
    carrier.scale = (1.,) * 3
    followers.hide_render = False
    for label, frame in (("loose", START), ("forming", 101), ("formed", LOCK + 18)):
        scene.frame_set(frame)
        render(scene, scene.objects[OVERHEAD], output, f"top_flock_{label}", (1040, 600), 24)
    render(scene, scene.objects[REAR], output, "rear_flock_12", GAME, 24)


def video(scene, camera, size, stride, output):
    REF["render_settings"](scene, size, 8)
    scene.render.use_persistent_data = True
    scene.camera = scene.objects[camera]
    with TemporaryDirectory(prefix="ft-anm006-") as directory:
        temp = Path(directory)
        for i, frame in enumerate(range(1, REVIEW_END, stride)):
            scene.frame_set(frame)
            scene.render.filepath = str(temp / f"{i:03}.png")
            bpy.ops.render.render(write_still=True, scene=scene.name)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-framerate", str(FPS // stride),
            "-i", str(temp / "%03d.png"), "-c:v", "libx264", "-crf", "16",
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=black", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(output),
        ], check=True)


def save_source(scene, review, rig, formation, output):
    review.frame_set(LOCK + 18)
    bpy.context.window.scene = scene
    set_action(rig, formation)
    scene.frame_set(11)
    scene.camera = scene.objects[DETAIL]
    scene["Playback"] = "Formation_Blend, 1–53 at 48 fps. Use frames 1–52 for repeating playback."
    scene["Review"] = "Switch to Review | Loose flock to V for two-second phase-aligned mixing and staged placement."
    scene.use_preview_range = True
    scene.frame_preview_start, scene.frame_preview_end = 1, PERIOD
    for item, size in ((scene, (1040, 600)), (review, GAME)):
        REF["render_settings"](item, size, 24)
        item.render.filepath = "//"
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
    assert not any(output.iterdir()), "Choose a new, empty output directory."
    chr_manifest = json.loads((CHR / "asset_manifest.json").read_text())
    cruise_manifest = json.loads((ANM / "asset_manifest.json").read_text())
    for manifest, paths in ((chr_manifest, (CHR_BLEND, CHR_GLB)), (cruise_manifest, (CRUISE_BLEND, CRUISE_SCRIPT))):
        assert manifest["status"] == "done"
        for path in paths:
            assert DIGEST(path) == manifest["files"][path.name], path
    scale = chr_manifest["camera"]["preview_game_units_per_BU"]
    bpy.context.preferences.addons["io_scene_gltf2"].preferences.KHR_materials_variants_ui = True
    bpy.ops.wm.open_mainfile(filepath=str(CHR_BLEND))
    scene = bpy.context.scene
    scene.name = "ANM-006 | Editable Formation_Blend"
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, PERIOD + 1
    rig, mesh = scene.objects["GooseRig"], scene.objects["Goose_LOD0"]
    assert len(rig.pose.bones) == 15 and len([image for image in bpy.data.images if image.packed_file]) == 4
    with bpy.data.libraries.load(str(CRUISE_BLEND), link=False) as (available, imported):
        assert "Cruise_Flap_Loop" in available.actions
        imported.actions = ["Cruise_Flap_Loop"]
    cruise, = imported.actions
    assert tuple(cruise.frame_range) == (1, PERIOD + 1) and cruise.use_cyclic
    cruise.use_fake_user = True
    formation = scaled_action(cruise)
    for marker in formation.pose_markers:
        scene.timeline_markers.new(marker.name, frame=marker.frame)
    qa = {}
    if mode != "draft":
        qa["amplitude"] = check_amplitudes(scene, rig, cruise, formation)
        set_action(rig, formation)
        qa["loop"], motion = TOOLS["check_cycle"](scene, mesh, rig, scene.objects[REAR], scale)
        qa["two_second_phase_matched_blends"] = check_blends(scene, mesh, rig, cruise, formation, scale)
        qa["glb"], qa["reimport"] = export_and_reimport(scene, mesh, rig, formation, motion, output, mode == "full")

    review, followers, birds = make_review(scene, mesh, rig, cruise, formation, scale)
    bpy.context.window.scene = review
    qa["flock"] = check_flock(review, birds, cruise, formation, scale)
    if mode == "draft":
        render_stills(review, followers, birds, output)
        return
    save_source(scene, review, rig, formation, output / f"{STEM}.blend")
    if mode == "full":
        bpy.context.window.scene = review
        render_stills(review, followers, birds, output)
        video(review, REAR, GAME, 2, output / "preview_rear_flock_12.mp4")
        video(review, OVERHEAD, (896, 504), 4, output / "preview_top_formation.mp4")
        followers.hide_render = True
        video(review, DETAIL, (864, 480), 4, output / "preview_rear_detail.mp4")
    DUMP(output / "qa.json", {"id": "ANM-006", "version": "v001", "status": "needs_review", "blender": qa})
    DUMP(output / "asset_manifest.json", {
        "id": "ANM-006", "version": "v001", "status": "needs_review", "blender": bpy.app.version_string,
        "dependencies": {"CHR-001/v001": "done", "ANM-001/v001": "done"},
        "source_hashes": {str(path.relative_to(LIBRARY)): DIGEST(path) for path in (
            CHR_BLEND, CHR_GLB, CRUISE_BLEND, CRUISE_SCRIPT, BLEND_SCRIPT, CHR / "CHR-001_goose_rig_generate.py")},
        "source": "Phase-aligned reduced-amplitude flap derived from the accepted Cruise_Flap_Loop source curves.",
        "rights": "Project-original animation and existing CHR-001 packed plumage.",
        "clip": {"name": CLIP, "frames": [1, PERIOD + 1], "fps": FPS, "duration_s": PERIOD / FPS,
                 "seam_frame": PERIOD + 1, "loop": True, "root_motion": False,
                 "local_body_lift": True, "same_phase_as": "Cruise_Flap_Loop"},
        "review": {"formation_start_frame": START, "fully_formed_frame": LOCK,
                   "phase_blend_seconds": (LOCK - START) / FPS, "weight_curve": "quintic smootherstep",
                   "lead_entry_cruise_frame": phase(START, 0), "lead_exit_formation_frame": phase(LOCK, 0),
                   "camera": chr_manifest["camera"], "follower_scale": .8,
                   "placement": "Review-only animated Empty carriers, 26 lateral at first rank, then 6 lateral and 13 trailing game units per V rank."},
        "character": {"triangles_lod0": 3940, "bones": 15, "pivot_BU": [0, 0, 0], "scale": [1, 1, 1],
                      "axes_blender": chr_manifest["axes_blender"], "axes_gltf": chr_manifest["axes_gltf"]},
        "variants": chr_manifest["variants"], "texture_mapping": chr_manifest["texture_mapping"],
        "files": {path.name: DIGEST(path) for path in [Path(__file__), *sorted(output.iterdir())]},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=["draft", "checks", "full"], default="full")
    options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    main(options.output.resolve(), options.mode)
