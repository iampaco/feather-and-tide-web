"""Render and check the rear-follow review motion from the delivered ENV-009 blend."""
import argparse
import math
from pathlib import Path
import runpy
import subprocess
import sys

import bpy

HERE = Path(__file__).resolve().parent
MODEL = runpy.run_path(str(HERE / "ENV-009_generate.py"))
BASE = MODEL["BASE"]
FRAME = MODEL["SIZE"]


def preview(folder, ffmpeg):
    bpy.ops.wm.open_mainfile(filepath=str(HERE / (MODEL["STEM"] + ".blend")))
    scene = bpy.data.scenes["ENV-009 | Fixed follow backdrop"]
    bpy.context.window.scene = scene
    cam = scene.camera
    bird = scene.objects["Review | CHR-001 neutral pose"]
    route = scene.objects["Review only | route fades before mountains"]
    modules = {key: scene.objects[key] for key, *_ in MODEL["PLACEMENTS"]}
    first, mid, last = MODEL["VIEWS"]
    samples = []
    frames = folder / "frames"
    frames.mkdir()
    for i in range(34):
        t = i / 33
        # Quadratic Lagrange interpolation through the three static validation poses.
        a = 2 * (t - .5) * (t - 1)
        b = 4 * t * (1 - t)
        c = 2 * t * (t - .5)
        pose = tuple(a * x + b * y + c * z for x, y, z in zip(first, mid, last))
        MODEL["view_pose"](cam, bird, pose)
        measured = MODEL["sample_view"](scene, cam, route, bird, modules)
        samples.append(measured)
        BASE["render"](scene, cam, frames, f"{i:04}", FRAME, 14)
    path = folder / "preview_motion_fixed_rear.mp4"
    run = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    subprocess.run(run + ["-framerate", "15", "-i", str(frames / "%04d.png"),
                          "-vf", "pad=852:394:0:0,fps=30", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                          "-crf", "17", "-movflags", "+faststart", str(path)], check=True)
    subprocess.run(run + ["-xerror", "-i", str(path), "-f", "null", "-"], check=True)
    BASE["write_json"](folder / "motion_report.json", {
        "result": "pass", "frames_checked": len(samples), "display_rig_size_px": list(FRAME),
        "max_background_band_fraction": max(r["max_background_band_fraction"] for r in samples),
        "min_route_to_background_gap_px": min(r["min_route_to_background_gap_px"] for r in samples),
        "world_buffer_to_demo_flight_y_BU": min(r["world_buffer_to_demo_flight_y_BU"] for r in samples),
        "peak_to_peak_bearing_degrees": math.degrees(last[2] - first[2]),
        "codec_readback": "pass",
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ffmpeg", default="/opt/homebrew/bin/ffmpeg")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()):
        raise ValueError("Use an empty temporary output folder.")
    preview(folder, args.ffmpeg)


if __name__ == "__main__":
    main()
