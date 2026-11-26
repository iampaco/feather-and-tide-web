"""Reopen delivered .blend, reimport delivered .glb, and fully decode the preview."""

import argparse
import hashlib
import json
import math
import runpy
import struct
import subprocess
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np


ROOT = Path(__file__).resolve().parent
G = runpy.run_path(str(ROOT / "FX-008_generate.py"))
SIZE = G["GAME"]
PENDING = {
    "art": "Owner art review, and legibility over final backgrounds and any combined adjacent effects.",
    "runtime": "RealityKit visibility, texture/shader transparency and ordering, actual flock anchors, timing and route.",
    "usdz_app": "USDZ and App integration.",
    "hardware": "iPhone and iPad visual read, controls, frame rate, thermal behavior, and memory.",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dependency_identity(directory, filename):
    manifest_path = directory / "asset_manifest.json"
    qa_path = directory / "qa.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] in ("done", "needs_review")
    summary = {}
    for name in (filename, filename.replace(".blend", ".glb"), "README.md", "asset_manifest.json", "qa.json"):
        value = digest((directory / name).read_bytes())
        declared = manifest.get("files", {}).get(name)
        if isinstance(declared, dict):
            declared = declared.get("sha256")
        if declared:
            assert value == declared, (directory, name, value, declared)
        summary[name] = value
    return {
        "status": manifest["status"],
        "qa_status": json.loads(qa_path.read_text())["status"],
        "sha256": summary,
    }


def decoded_glb(path, texture):
    blob = path.read_bytes()
    magic, version, length, json_size, json_type = struct.unpack_from("<4sIII4s", blob)
    assert (magic, version, length, json_type) == (b"glTF", 2, len(blob), b"JSON")
    contents = json.loads(blob[20 : 20 + json_size])
    for kind in ("scenes", "nodes", "meshes", "textures", "images", "materials"):
        assert len(contents[kind]) == 1, (kind, len(contents[kind]))
    assert not any(kind in contents for kind in ("animations", "skins", "cameras"))
    assert contents["nodes"][0]["name"] == G["VARIANT"]
    material = contents["materials"][0]
    assert material["alphaMode"] == "BLEND" and material["doubleSided"]
    assert "KHR_materials_unlit" in material["extensions"]
    primitive, = contents["meshes"][0]["primitives"]
    assert set(primitive["attributes"]) == {"NORMAL", "POSITION", "TEXCOORD_0"}
    assert contents["accessors"][primitive["indices"]]["count"] == 30
    accessor = contents["accessors"][primitive["attributes"]["POSITION"]]
    assert math.isclose(accessor["min"][2], -.32, abs_tol=1e-6)
    assert math.isclose(accessor["max"][2], .32, abs_tol=1e-6)
    assert abs(accessor["min"][1]) < 1e-7 and abs(accessor["max"][1]) < 1e-7
    image = contents["images"][0]
    assert image["mimeType"] == "image/png"
    view = contents["bufferViews"][image["bufferView"]]
    start = 28 + json_size + view.get("byteOffset", 0)
    embedded = blob[start : start + view["byteLength"]]
    assert embedded == texture.read_bytes()
    return {
        "nodes": 1, "mesh_primitives": 1, "triangles": 10, "review_objects_exported": 0,
        "texture_embedded_byte_match": True, "material_alpha": "BLEND",
        "material_extension": "KHR_materials_unlit", "double_sided": True,
        "positions_min_gltf": accessor["min"], "positions_max_gltf": accessor["max"],
    }


def triangle_uv_signature(mesh):
    mesh.calc_loop_triangles()
    signature = set()
    for tri in mesh.loop_triangles:
        coords = []
        for loop_idx in tri.loops:
            vertex = mesh.vertices[mesh.loops[loop_idx].vertex_index]
            point = tuple(round(x, 5) for x in vertex.co)
            uv = tuple(round(t, 5) for t in mesh.uv_layers.active.data[loop_idx].uv)
            coords.append((point, uv))
        signature.add(tuple(sorted(coords)))
    return signature


def image_pixels(path):
    img = bpy.data.images.load(str(path), check_existing=False)
    w, h = img.size
    pixels = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(pixels)
    bpy.data.images.remove(img)
    return pixels.reshape(h, w, 4), (w, h)


def difference(before, after):
    a, size = image_pixels(before)
    b, b_size = image_pixels(after)
    assert size == b_size == SIZE, (size, b_size)
    delta = np.max(abs(a[:, :, :3] - b[:, :, :3]), axis=2)
    mask = delta >= 6 / 255
    cut = size[0] // 2
    return {
        "peak_8bit_delta": float(255 * delta.max()),
        "mean_8bit_delta": float(255 * delta.mean()),
        "pixels_delta_at_least_6_of_255": int(mask.sum()),
        "left_pixels_delta_at_least_6_of_255": int(mask[:, :cut].sum()),
        "right_pixels_delta_at_least_6_of_255": int(mask[:, cut:].sum()),
    }


def scene_checks(scene):
    assert scene.camera.name == G["REAR"] and scene.render.resolution_x == SIZE[0]
    assert scene.render.resolution_y == SIZE[1] and scene.render.fps == 24
    cam = scene.camera
    correct_fov = 2 * math.atan(cam.data.sensor_height / (2 * cam.data.lens))
    assert math.isclose(math.degrees(correct_fov), 50, abs_tol=1e-5)
    props = scene.objects[G["CONTROL_NAME"]]
    assert all(math.isclose(props[key], val, rel_tol=1e-7) for key, val in G["DEFAULTS"].items())
    birds = [scene.objects[f"Review mesh | {i:02}"] for i in range(12)]
    assert all(len(o.parent.data.bones) == 15 for o in birds) and len({ob.data for ob in birds}) == 1
    assert len(bpy.data.actions["Formation_Blend"].slots) == 1
    assert len(bpy.data.actions["Cruise_Flap_Loop"].slots) == 1
    review_group = bpy.data.collections["FX-008 | review ribbons and controls"]
    dabs = [ob for ob in review_group.objects if ob.type == "MESH"]
    assert len(dabs) == 9 and [sum(ob["side"] == side for ob in dabs) for side in (-1, 1)] == [5, 4]
    visible_pixel_margin = math.inf
    fixed_pose_max_error = 0.
    opacity_max_error = 0.
    interpolation_error = 0.
    sampled_motion = {}
    signed_dash_separation = math.inf
    for sample in range(2, G["FINAL_FRAME"] * 2 + 1):
        frame, subframe = divmod(sample, 2)
        scene.frame_set(frame, subframe=.5 * subframe)
        time = frame + subframe * .5
        expected_opacity = G["guide_weight"](time)
        opacity = props["opacity"]
        rendered_material = dabs[0].material_slots[0].material.evaluated_get(bpy.context.evaluated_depsgraph_get())
        opacity_input = rendered_material.node_tree.nodes["Review opacity"].inputs[1]
        key_sample = expected_opacity if not subframe else (
            .5 * (G["guide_weight"](frame) + G["guide_weight"](frame + 1))
        )
        opacity_max_error = max(opacity_max_error, abs(opacity_input.default_value - key_sample))
        interpolation_error = max(interpolation_error, abs(key_sample - expected_opacity))
        local_cam = cam.parent.matrix_world.inverted() @ cam.matrix_world
        correct_eye = Vector((0, -180 * math.cos(.48) / G["GAME_PER_BU"],
                              (180 * math.sin(.48) - 8) / G["GAME_PER_BU"]))
        fixed_pose_max_error = max(fixed_pose_max_error, (local_cam.translation - correct_eye).length)
        target = Vector((0, 0, -2 / G["GAME_PER_BU"]))
        expected_direction = (target - correct_eye).normalized()
        assert (local_cam.to_3x3() @ Vector((0, 0, -1)) - expected_direction).length < 2e-6
        if opacity > .05:
            for dash in dabs:
                a = scene.objects[f"Preview carrier | {dash['a']:02}"].location
                b = scene.objects[f"Preview carrier | {dash['b']:02}"].location
                side = dash["side"]
                signed_dash_separation = min(signed_dash_separation, side * (dash.location.x - (a.x + b.x) / 2))
                assert (dash.rotation_euler.to_matrix() @ Vector((0, 1, 0))).dot((a - b).normalized()) > .999
                assert dash.location.z > -.26
                for vertex in dash.data.vertices:
                    u, v, depth = world_to_camera_view(scene, cam, dash.matrix_world @ vertex.co)
                    assert depth > 0
                    margin = min(u * SIZE[0], (1 - u) * SIZE[0], v * SIZE[1], (1 - v) * SIZE[1])
                    visible_pixel_margin = min(visible_pixel_margin, margin)
        if not subframe and frame in (1, 13, 37, 61, 73, 85, 97, 103, 151, 163, 167, 169, 192):
            sampled_motion[str(frame)] = round(float(opacity), 6)
    assert opacity_max_error < 1e-4 and fixed_pose_max_error < 3e-6, (opacity_max_error, fixed_pose_max_error)
    assert interpolation_error < .07, interpolation_error
    assert signed_dash_separation > .90 and visible_pixel_margin > 0
    assert [sampled_motion[str(f)] for f in (1, 13, 37, 61, 73, 85, 97, 151, 163, 167, 169, 192)] == [
        0., 0., .5, 1., 1., .5, 0., 1., 1., 0., 0., 0.,
    ]
    return {
        "visible_ribbons_L_and_R": [5, 4],
        "flock": 12, "triangle_mesh_instances": 1,
        "sampled_half_frames": G["FINAL_FRAME"] * 2 - 1,
        "min_source_frame_margin_px_for_visible_guides": visible_pixel_margin,
        "min_ribbon_outward_spacing_BU": signed_dash_separation,
        "max_fixed_rig_position_delta_BU": fixed_pose_max_error,
        "max_shader_driver_error_vs_linear_keys": opacity_max_error,
        "max_baked_half_frame_delta_vs_continuous_envelope": interpolation_error,
        "sample_opacity_by_frame_24fps": sampled_motion,
    }


def codec(path):
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-show_entries",
        "stream=codec_name,codec_type,width,height,pix_fmt,r_frame_rate,nb_read_frames,duration",
        "-of", "json", str(path),
    ], text=True))
    stream, = probe["streams"]
    assert stream["codec_type"] == "video" and stream["codec_name"] == "prores"
    assert (stream["width"], stream["height"]) == SIZE
    assert stream["r_frame_rate"] == "12/1" and stream["nb_read_frames"] == "96"
    assert math.isclose(float(stream["duration"]), 8)
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True)
    return stream


def roundtrip(scene, imported, trace_group, output):
    bpy.context.window.scene = scene
    replacements = []
    # Reapply the preview-only layer to the imported mesh and embedded image.
    image = next(n.image for n in imported.data.materials[0].node_tree.nodes if n.type == "TEX_IMAGE")
    mat = G["material"]("Round-trip opacity preview", image, review=True)
    for old in list(trace_group.objects):
        if old.type != "MESH":
            continue
        replacement = old.copy()
        replacement.data = imported.data
        replacement.name = f"Returned {old.name}"
        trace_group.objects.link(replacement)
        replacement.material_slots[0].link = "OBJECT"
        replacement.material_slots[0].material = mat
        old.hide_render = True
        replacements.append(replacement)
    assert len(replacements) == 9
    G["render"](scene, output / "roundtrip_fixed_rear.png", 63)


def verify(directory, output):
    package = G["LIBRARY"]
    dependencies = {
        ident: dependency_identity(package / ident / "v001", filename)
        for ident, filename in (("CHR-001", "CHR-001_goose_rig.blend"), ("ANM-006", "ANM-006_formation_blend.blend"))
    }
    master = directory / G["SOURCE_BASENAME"]
    glb = directory / G["GLB_BASENAME"]
    texture = directory / "textures" / G["TEXTURE"]
    glb_info = decoded_glb(glb, texture)
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    review = bpy.data.scenes[G["REVIEW_NAME"]]
    bpy.context.window.scene = review
    scene_info = scene_checks(review)
    source = bpy.data.scenes["FX-008 | portable ribbon"].objects[G["VARIANT"]]
    uv_before = triangle_uv_signature(source.data)
    assert len(uv_before) == 10 and list(source.location) == [0, 0, 0] and list(source.scale) == [1, 1, 1]
    image = next(n.image for n in source.data.materials[0].node_tree.nodes if n.type == "TEX_IMAGE")
    assert image.packed_file and image.packed_file.data == texture.read_bytes()
    texels, dims = image_pixels(texture)
    alpha = texels[:, :, 3]
    assert dims == (256, 64) and .31 < alpha.max() < .47
    assert not np.count_nonzero(alpha[[0, -1], :]) and not np.count_nonzero(alpha[:, [0, -1]])
    import_scene = bpy.data.scenes.new("Clean GLB reimport")
    bpy.context.window.scene = import_scene
    bpy.ops.import_scene.gltf(filepath=str(glb))
    imported, = import_scene.objects
    assert imported.type == "MESH" and imported.name.startswith(G["VARIANT"])
    assert triangle_uv_signature(imported.data) == uv_before, "UV/material topology did not round trip"
    assert (imported.location).length == 0 and (imported.scale - Vector((1, 1, 1))).length == 0
    assert all(poly.normal.z > .999 for poly in imported.data.polygons)
    for side, a, b in ((-1, (0., 1.3, .3), (-1.5, -1.4, .3)), (1, (1., -.2, .09), (1.7, -3.5, .06))):
        middle, yaw, scale = G["gap_pose"](Vector(a), Vector(b), side, .01, G["DEFAULTS"])
        assert middle.z >= .01 + G["DEFAULTS"]["ground_clearance_BU"] - 1e-7 and abs(yaw) > .1
        assert math.isclose(scale[1] * G["BASE_LENGTH"], math.dist(a[:2], b[:2]) * .67, rel_tol=1e-6)
    group = bpy.data.collections["FX-008 | review ribbons and controls"]
    roundtrip(review, imported, group, output)
    comparisons = {}
    for key in ("formed", "broken", "released"):
        comparisons[key] = difference(directory / f"preview_{key}.png",
                                      directory / f"comparison_{key}_without_trace.png")
    assert min(comparisons["formed"][p] for p in ("left_pixels_delta_at_least_6_of_255",
                                                 "right_pixels_delta_at_least_6_of_255")) >= 35
    assert comparisons["broken"]["pixels_delta_at_least_6_of_255"] < 4
    assert comparisons["released"]["pixels_delta_at_least_6_of_255"] < 4
    returned = difference(directory / "preview_formed.png", output / "roundtrip_fixed_rear.png")
    assert returned["mean_8bit_delta"] < .32, returned
    video = codec(directory / G["VIDEO_BASENAME"])
    report = {
        "id": "FX-008", "version": "v001", "status": "needs_review",
        "independent_delivery_recheck": {
            "status": "pass",
            "blender": bpy.app.version_string,
            "verified_directory": "Assets/Watercolor/Goose/Blender/FX-008/v001",
            "input_sha256": {master.name: digest(master.read_bytes()), glb.name: digest(glb.read_bytes()),
                             texture.name: digest(texture.read_bytes())},
            "dependency_evidence": dependencies,
            "master_camera_flock_and_timing": scene_info,
            "portable_GLTF": glb_info,
            "texture": {"dimensions_px": dims, "alpha_peak_8bit": round(float(alpha.max()) * 255),
                        "zero_alpha_outer_border": True},
            "GLB_reimport_UV_positions_and_normals": "pass",
            "alternate_slot_positions_and_ground_clamp": "pass",
            "formed_cancelled_comparison": comparisons,
            "roundtrip_same_scene_error": returned,
            "silent_video_full_decode": video,
        },
        "redline_review": "Reviewed plans/_templates/redline-checklist.md. The sample introduces only a muted silent visual guide.",
        "app_baseline": "Existing iPhone 18 Pro (iOS 27.2) simulator baseline in the active plan, 340 tests. This asset's checks ran offline.",
        "pending": PENDING,
    }
    (output / "qa.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report["independent_delivery_recheck"], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verification_output", type=Path)
    parser.add_argument("--candidate", type=Path, default=ROOT, help="Default is the delivered asset directory.")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    verify(args.candidate.resolve(), args.verification_output.resolve())


if __name__ == "__main__":
    main()
