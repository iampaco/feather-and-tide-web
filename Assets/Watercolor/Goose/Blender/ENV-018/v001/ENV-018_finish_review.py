"""Encode the fixed-camera drift samples and record delivery evidence."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageChops, ImageStat


def run(*args):
    return subprocess.check_output(args, text=True)


def compare(directory, first, second):
    with Image.open(directory / f"{first}.png") as a, Image.open(directory / f"{second}.png") as b:
        delta = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
        return {
            "size": list(delta.size),
            "max_channel_delta_rgb8": max(high for _, high in delta.getextrema()),
            "mean_abs_delta_rgb8": sum(ImageStat.Stat(delta).mean) / 3,
            "pixels_with_channel_delta_at_least_5": sum(
                max(channels) >= 5 for channels in delta.get_flattened_data()
            ),
        }


def encode(directory, first, second):
    count = 24
    for scene in (first, second):
        assert len(list(scene.glob("motion_*.png"))) == count, scene
        with Image.open(scene / "motion_000.png") as a, Image.open(scene / "motion_023.png") as b:
            assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox(), scene
    path = directory / "preview_atmosphere_motion.mp4"
    run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", "12", "-i", str(first / "motion_%03d.png"),
        "-framerate", "12", "-i", str(second / "motion_%03d.png"),
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,pad=852:394:0:0[v]",
        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "17", "-movflags", "+faststart", str(path))
    run("ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-")
    info = json.loads(run("ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,nb_read_frames,duration",
        "-of", "json", str(path)))["streams"][0]
    assert int(info["nb_read_frames"]) == 2 * count and info["codec_name"] == "h264", info
    assert (info["width"], info["height"]) == (852, 394), info
    return {"file": path.name, "rendered_frames": 2 * count, "sequence": ["S3", "S2"], **info}


def put_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Contains the generated PNGs, QA and manifest.")
    parser.add_argument("s3_frames", type=Path)
    parser.add_argument("s2_frames", type=Path)
    parser.add_argument("--recheck", type=Path, help="Optional independent Blender recheck JSON.")
    args = parser.parse_args()
    directory = args.output.resolve()
    scripts = Path(__file__).resolve().parent
    root = scripts.parents[5]
    camera = root / "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift"
    source = camera.read_text()
    assert "distance: 180, pitch: 0.48, fieldOfViewDegrees: 50" in source
    assert "Float(6 + lift)" in source
    qa = json.loads((directory / "qa.json").read_text())
    stats = compare(directory, "preview_lineup", "preview_glb_roundtrip")
    assert stats["max_channel_delta_rgb8"] <= 5 and stats["mean_abs_delta_rgb8"] < .1, stats
    qa["roundtrip_render_comparison"] = stats
    qa["accessibility_render_comparison"] = {}
    for stage in ("s3", "s4"):
        full = compare(directory, f"preview_{stage}_default", f"preview_{stage}_off")
        reduced = compare(directory, f"preview_{stage}_reduced", f"preview_{stage}_off")
        assert 0 < reduced["mean_abs_delta_rgb8"] < full["mean_abs_delta_rgb8"], (stage, reduced, full)
        qa["accessibility_render_comparison"][stage] = {"default_vs_off": full, "reduced_vs_off": reduced}
    qa["camera_source"] = {
        "path": camera.relative_to(root).as_posix(),
        "sha256": sha256(camera.read_bytes()).hexdigest(),
        "distance_game_units": 180,
        "pitch_rad": .48,
        "vertical_fov_deg": 50,
        "target_height_game_units": 6,
        "goose_preview_height_game_units": 8,
        "render_source_size": [852, 393],
    }
    qa["video"] = encode(directory, args.s3_frames, args.s2_frames)
    if args.recheck:
        recheck = json.loads(args.recheck.read_text())
        assert recheck["result"] == "pass" and recheck["roundtrip"] == qa["roundtrip"]
        qa["independent_blender_reopen"] = {"result": "pass", "saved_drift": recheck["drift"]}
    qa["project_app_rerun"] = False
    qa["exporter_note"] = ("Blender emitted a sampler warning when gathering color and alpha from the same "
                           "RGBA texture. Raw GLB recheck confirms a single image, BLEND, matching PNG "
                           "bytes and identical CLAMP_TO_EDGE on both UV axes for each variant.")
    put_json(directory / "qa.json", qa)
    path = directory / "asset_manifest.json"
    manifest = json.loads(path.read_text())
    library = scripts.parents[1]
    for asset in ("ENV-001/v001/ENV-001_terrain.blend", "ANM-007/v001/ANM-007_landing.blend"):
        manifest["review_only_sources"][asset] = sha256((library / asset).read_bytes()).hexdigest()
    manifest["previews"] = sorted(p.name for p in directory.glob("*.png")) + [qa["video"]["file"]]
    manifest["files"] = {
        p.relative_to(directory).as_posix(): sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*")) if p.is_file() and p != path
    }
    put_json(path, manifest)


if __name__ == "__main__":
    main()
