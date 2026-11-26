"""Render a fixed-camera Geometry Nodes wind loop from the delivered editable preset."""
import argparse
import math
from pathlib import Path
import runpy
import subprocess
import sys

import bpy
from mathutils import Vector


HERE = Path(__file__).resolve().parent
WORKFLOW = runpy.run_path(str(HERE / "ENV-005_generate.py"))
BASE = WORKFLOW["BASE"]


def sample_geometry(live):
    frozen = WORKFLOW["freeze"](live)
    values = [vertex.co.copy() for vertex in frozen.vertices]
    bpy.data.meshes.remove(frozen)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--frames", type=int, default=36)
    parser.add_argument("--ffmpeg", default="/opt/homebrew/bin/ffmpeg")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()) or args.frames < 12:
        raise ValueError("Use an empty output directory and at least 12 frames.")
    bpy.ops.wm.open_mainfile(filepath=str(HERE / "ENV-005_reed_distribution.blend"))
    review = bpy.data.scenes["ENV-005 | Preset comparison"]
    bpy.context.window.scene = review
    blender_camera = next(o for o in review.objects if o.name == "Source rig | fixed rear")
    for node in review.objects:
        if node.name in {f"Review | {name}" for name in WORKFLOW["PRESETS"]}:
            node.hide_render = True
    source = bpy.data.objects["ShoreEdge"]
    live = source.copy()
    live.name = "ShoreEdge | live wind sample"
    review.collection.objects.link(live)
    live.hide_set(False)
    live.hide_render = False
    live.hide_viewport = False

    # Place the same code camera nearer the bank, with its horizontal heading kept fixed.
    leader = next(o for o in review.objects if o.name == "Review | CHR-001 neutral pose")
    leader.location.x, leader.location.y = 4.15, -5.6
    heading = Vector((.11, .993931587))
    leader.rotation_euler.z = -math.atan2(heading.x, heading.y)
    BASE["follow"](blender_camera, leader.location.xy, heading)
    modifier = live.modifiers[0]
    set_input = WORKFLOW["set_input"]
    first = sample_geometry(live)
    set_input(modifier, "Motion phase radians", math.pi)
    second = sample_geometry(live)
    BASE["check"](len(first) == len(second), "Changing phase changed topology")
    offsets = [(a - b).length for a, b in zip(first, second)]
    BASE["check"](max(offsets) > .035 and sum(d > .005 for d in offsets) > 100, "No wind displacement")
    set_input(modifier, "Motion phase radians", math.tau)
    loop = sample_geometry(live)
    end_error = max((a - b).length for a, b in zip(first, loop, strict=True))
    BASE["check"](end_error < 1e-5, ("Loop closure", end_error))

    frames = output / "frames"
    frames.mkdir()
    for i in range(args.frames):
        set_input(modifier, "Motion phase radians", math.tau * i / args.frames)
        BASE["render"](review, blender_camera, frames, f"{i:04}", BASE["GAME_SIZE"], 10)
    video = output / "preview_wind_fixed_rear.mp4"
    subprocess.run([args.ffmpeg, "-hide_banner", "-loglevel", "error", "-framerate", "15", "-i",
                    str(frames / "%04d.png"), "-vf", "pad=852:394:0:0,fps=30", "-an", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "17", "-movflags", "+faststart", str(video)], check=True)
    subprocess.run([args.ffmpeg, "-hide_banner", "-loglevel", "error", "-xerror", "-i",
                    str(video), "-f", "null", "-"], check=True)
    BASE["write_json"](output / "wind_report.json", {"result": "pass", "preset": "ShoreEdge",
              "phase_sample_radians": math.pi, "max_vertex_displacement_BU": max(offsets),
              "vertices_moved_more_than_0_005_BU": sum(d > .005 for d in offsets),
              "loop_vertex_error_BU": end_error, "rendered_frames": args.frames,
              "source_size_px": list(BASE["GAME_SIZE"]), "video_readback": "pass"})


if __name__ == "__main__":
    main()
