"""Render the ANM-007 twelve-goose landing and held pose from the editable source."""
import argparse
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import bpy


HERE = Path(__file__).resolve().parent
BUILD = runpy.run_path(str(HERE / "ENV-017_generate.py"))
B = BUILD["B"]
FRAME = BUILD["FRAME"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    p.add_argument("--source", type=Path, default=HERE)
    p.add_argument("--step", type=int, choices=(2, 4), default=4)
    p.add_argument("--ffmpeg", default="ffmpeg")
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use an empty output folder.")
    ffmpeg = shutil.which(args.ffmpeg) or args.ffmpeg
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve() / (BUILD["STEM"] + ".blend")))
    scene = bpy.data.scenes["ENV-017 | S6 landing and leader hold"]
    bpy.context.window.scene = scene
    camera = scene.camera
    leader = next(obj for obj in scene.objects if obj.name.startswith("Landing carrier 01"))
    frames = output / "frames"
    frames.mkdir()
    sequence = list(range(args.step, BUILD["REST_END"] + 1, args.step))
    for i, frame in enumerate(sequence):
        scene.frame_set(frame)
        BUILD["flight_camera"](camera, leader)
        B["render"](scene, camera, frames, f"{i:04}", FRAME, 8)
    shutil.copyfile(frames / f"{len(sequence) - 1:04}.png", output / "preview_rest_idle.png")
    rate = 48 // args.step
    video = output / "preview_landing_motion.mp4"
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-framerate", str(rate),
                    "-i", str(frames / "%04d.png"), "-vf", "pad=852:394:0:0,tpad=stop_mode=clone:stop_duration=0.65,fps=24",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-an", "-movflags", "+faststart", str(video)], check=True)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-xerror", "-i", str(video), "-f", "null", "-"], check=True)
    BUILD["write"](output / "motion_report.json", {"result": "pass", "source_px": list(FRAME),
                   "output_px": [852, 394], "source_fps": 48, "sample_fps": rate, "output_fps": 24,
                   "source_frames": sequence, "final_hold_s": .65, "h264_decode": "pass"})


if __name__ == "__main__":
    main()
