"""Encode, decode, and inventory the actual FX-004 delivery after independent Blender verification."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from PIL import Image


SIZE = 852,393
FRAME_RATE = 12
FRAMES = 48
VIDEO = "preview_fixed_rear.mp4"


def run(*args):
    return subprocess.run(args, capture_output=True, check=True, text=True).stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_save(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")


def read_rgb(path):
    with Image.open(path) as image:
        reference = np.asarray(image.convert("RGB")).astype(np.int16)
    assert reference.shape==(SIZE[1],SIZE[0],3), (path,reference.shape)
    return reference


def compare(first, second):
    diff = np.abs(first-second)
    return {"maximum_channel_delta_8bit":int(diff.max()),
            "mean_absolute_channel_delta_8bit":float(diff.mean()),
            "pixels_channel_delta_at_least_5":int(np.count_nonzero(diff.max(axis=2)>=5))}


def encode(directory, verify):
    frames = list((verify/"frames").glob("fog_*.png"))
    assert len(frames)==FRAMES
    first,last = read_rgb(verify/"frames"/"fog_0001.png"),read_rgb(verify/"frames"/f"fog_{FRAMES:04}.png")
    movement = compare(first,last)
    assert movement["pixels_channel_delta_at_least_5"]>200, movement
    path = directory/VIDEO
    if path.exists():
        raise FileExistsError(path)
    # H.264 yuv420p needs even dimensions. Extend the last row to preserve the original framing.
    run("ffmpeg","-hide_banner","-loglevel","error","-n","-framerate",str(FRAME_RATE),
        "-i",str(verify/"frames/fog_%04d.png"),"-vf","pad=852:394:0:0,fillborders=bottom=1:mode=smear",
        "-c:v","libx264","-crf","17","-preset","fast","-threads","2","-pix_fmt","yuv420p",
        "-an","-movflags","+faststart",str(path))
    run("ffmpeg","-hide_banner","-v","error","-xerror","-threads","2","-i",str(path),"-f","null","-")
    streams = json.loads(run("ffprobe","-v","error","-count_frames","-show_streams","-of","json",str(path)))["streams"]
    assert len(streams)==1
    video, = streams
    assert (video["codec_name"],video["width"],video["height"])==("h264",852,394)
    assert int(video["nb_read_frames"])==FRAMES and video["avg_frame_rate"]=="12/1"
    return {"file":VIDEO,"codec":"h264","render_source_size_px":SIZE,"encoded_size_px":[852,394],
            "padded_bottom_rows":1,"fps":FRAME_RATE,"frames_decoded":int(video["nb_read_frames"]),
            "duration_seconds":float(video["duration"]),"audio_streams":0,"source_first_vs_last":movement}


def visual_metrics(output, verify):
    source = read_rgb(verify/"roundtrip_native_reference.png")
    reimported = read_rgb(verify/"preview_glb_roundtrip.png")
    roundtrip = compare(source,reimported)
    significant_fraction = roundtrip["pixels_channel_delta_at_least_5"] / (SIZE[0]*SIZE[1])
    roundtrip["fraction_of_pixels_with_channel_delta_at_least_5"] = significant_fraction
    assert roundtrip["mean_absolute_channel_delta_8bit"]<.20 and significant_fraction<.004, roundtrip
    off = read_rgb(output/"preview_fixed_rear_off.png")
    full = read_rgb(output/"preview_fixed_rear_default.png")
    weak = read_rgb(output/"preview_fixed_rear_reduced.png")
    contrast = {name:compare(image,off) for name,image in [("default_vs_off",full),("reduced_vs_off",weak)]}
    summary = contrast["default_vs_off"]
    reduced = contrast["reduced_vs_off"]
    assert summary["pixels_channel_delta_at_least_5"] > 500, summary
    assert summary["mean_absolute_channel_delta_8bit"]>reduced["mean_absolute_channel_delta_8bit"]>0
    luma = full @ np.array([.2126,.7152,.0722])
    center, side = luma[42:91,398:454], np.concatenate([luma[42:91,204:277],luma[42:91,585:658]],axis=1)
    contrast["takeoff_opening"] = {"center_box_xyxy":[398,42,454,91],
        "flank_boxes_xyxy":[[204,42,277,91],[585,42,658,91]],
        "average_luma_center_8bit":float(center.mean()),"average_luma_flanks_8bit":float(side.mean()),
        "difference_8bit":float(center.mean()-side.mean())}
    assert contrast["takeoff_opening"]["difference_8bit"]>5, contrast
    return roundtrip,contrast


def finish(delivery, build, verify):
    built = json.loads((build/"build_report.json").read_text())
    checked = json.loads((verify/"recheck.json").read_text())
    for name,h in checked["source_files_sha256"].items():
        assert sha(delivery/name)==h==sha(build/name), name
    assert built["glb"]==checked["raw_glb"]
    roundtrip,contrast = visual_metrics(delivery,verify)
    for name in ("preview_glb_roundtrip.png","roundtrip_native_reference.png"):
        assert not (delivery/name).exists()
        shutil.copyfile(verify/name,delivery/name)
    video = encode(delivery,verify)
    pending = {
        "art_approval_and_new_player_readability":"pending",
        "USDZ_and_RealityKit_import_compositing_and_depth":"pending",
        "S0_final_layout_runtime_safety_accessibility_and_stick_composition":"pending",
        "iPhone_iPad_visual_touch_performance":"pending",
        "asset_index_ledgers_task_json_active_plan":"pending",
    }
    qa = {
        "id":"FX-004","version":"v001","status":"needs_review","blender":built["blender"],
        "checked_from_delivery":checked["source_files_sha256"],
        "scene_controls":checked["material_motion_controls"],
        "verification_kind":"Independent Blender reopen, full GLB import, render comparison and MP4 full decode",
        "visibility":checked["visibility"],"raw_glb":checked["raw_glb"],
        "glb_roundtrip_render":roundtrip,"pixel_comparisons":contrast,"video":video,
        "pending":pending,"simulator_baseline":{"os":"iOS 27.2","tests_passed":340,
            "source":"plans/active/goose-preview-model-cleanup.md","new_app_run":False},
        "redline_self_check":{"review_context_only":True,"source":"plans/_templates/redline-checklist.md",
            "gameplay_UI_audio_changes":False},
    }
    json_save(delivery/"qa.json",qa)
    manifest = {
        "id":"FX-004","version":"v001","status":"needs_review","variant":"Fog_Start",
        "priority":"P0","task_execution_order_1_based":33,"levels":["S0"],
        "delivery_style":"render-only static cards with engine-driven presentation controls",
        "dependency":{"asset":"ENV-018/v001","upstream_status":"needs_review",
            "reference_placements_review_only":[
                {"name":"CloudPatch","translation_BU":[-24,55,3.3],"scale":[2.12,1,1]},
                {"name":"CloudStreak","translation_BU":[35,74,2.10],"scale":[1.64,1,1.28]}],
            "reference_assets_and_packed_masks_sha256":built["upstream_hashes"]},
        "mother_file":"FX-004_Fog_Start.blend","glb":"FX-004_Fog_Start.glb","qa":"qa.json",
        "textures":built["textures"],"rights":"Project-original programmatic masks using packed project ENV-018 textures",
        "scene_names":{"main":"FX-004 | S0 fixed rear review","component":"Fog_Start | editable runtime cards"},
        "axis_contract":{"Blender":"+X right, +Y forward, +Z up","GLB":"(x,z,-y), +Y up, -Z forward",
            "unit_scale":1,"reference_BU_to_game_units":27.5/.9900,"origin_BU":[0,0,0]},
        "camera":{"source_hashes":built["camera_sources"],"distance_game_units":180,"pitch_parameter_radians":.48,
            "vertical_fov_degrees":50,"target_height_game_units":6,"review_leader_height_game_units":8,
            "review_frame_px":SIZE},
        "runtime_interface":{"owner":"S0 scene presentation","root_node":"Fog_Start",
            "placement":"World-space transform at S0 takeoff origin; local +Y forward (Blender).",
            "inputs":{"elapsedSeconds":"Engine monotonic scene time","opacityStrength":"0...1; straight alpha multiplier",
                "motionStrength":"0...1; horizontal drift amplitude multiplier",
                "periodSeconds":"1...60; smooth drift loop duration, default 12",
                "phaseTurns":"Normalized offset 0...1, default 0"},
            "drift_formula":"base_x_BU + amplitude_BU * motionStrength * sin(2*pi * (elapsedSeconds/periodSeconds + phaseTurns + card.phase_turns))",
            "presets":{"default":{"opacityStrength":1,"motionStrength":1},
                "reduced":{"opacityStrength":.35,"motionStrength":.35},"off":{"opacityStrength":0,"motionStrength":0}},
            "card_fields_from_GLTF_extras":["base_x_BU","amplitude_BU","phase_turns"],
            "collision_enabled":False,"render_mode":"KHR_materials_unlit / double-sided / BLEND / clamp",
            "total_triangles":96,"geometry":built["glb"]},
        "previews":sorted(p.name for p in delivery.glob("*.png"))+[VIDEO],
        "scripts":["FX-004_generate.py","FX-004_finalize.py"],
        "pending":pending,
        "files":{p.relative_to(delivery).as_posix():sha(p) for p in sorted(delivery.rglob("*"))
                 if p.is_file() and p.name!="asset_manifest.json"},
    }
    json_save(delivery/"asset_manifest.json",manifest)
    for rel,h in manifest["files"].items():
        assert sha(delivery/rel)==h, rel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery",type=Path)
    parser.add_argument("build",type=Path)
    parser.add_argument("verify",type=Path)
    args = parser.parse_args()
    finish(args.delivery.resolve(),args.build.resolve(),args.verify.resolve())


if __name__=="__main__":
    main()
