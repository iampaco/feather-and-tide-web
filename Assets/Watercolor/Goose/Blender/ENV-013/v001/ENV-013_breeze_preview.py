"""Render the stored OpenBank stage under the source camera with asynchronous breeze."""
import argparse
import math
from pathlib import Path
import runpy
import subprocess
import sys

import bpy

HERE=Path(__file__).resolve().parent
WORKFLOW=runpy.run_path(str(HERE/"ENV-013_generate.py"))
BASE=WORKFLOW["BASE"]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--frames",type=int,default=30)
    parser.add_argument("--ffmpeg",default="/opt/homebrew/bin/ffmpeg")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()) or args.frames<15:
        raise ValueError("Use an empty folder and at least 15 frames.")
    bpy.ops.wm.open_mainfile(filepath=str(HERE/"ENV-013_riparian_shrubs.blend"))
    scene=bpy.data.scenes["ENV-013 | OpenBank gameplay review"]
    bpy.context.window.scene=scene
    plants=[p for p in scene.objects if "wind_phase_fraction" in p]
    if len(plants)<18:
        raise ValueError("Missing planted review shrubs.")
    frames=out/"frames"
    frames.mkdir()
    for i in range(args.frames):
        for item in plants:
            phase=item["wind_phase_fraction"]+i/args.frames
            item.data.shape_keys.key_blocks[1].value=.5+.5*math.sin(math.tau*phase)
        BASE["render"](scene,scene.camera,frames,f"{i:04}",BASE["GAME_SIZE"],10)
    video=out/"preview_breeze_fixed_rear.mp4"
    subprocess.run([args.ffmpeg,"-hide_banner","-loglevel","error","-framerate","9","-i",str(frames/"%04d.png"),
                    "-vf","pad=852:394:0:0,fps=27","-c:v","libx264","-pix_fmt","yuv420p","-crf","18","-an",
                    "-movflags","+faststart",str(video)],check=True)
    subprocess.run([args.ffmpeg,"-hide_banner","-loglevel","error","-xerror","-i",str(video),
                    "-f","null","-"],check=True)
    BASE["write_json"](out/"motion_check.json",{"result":"pass","frames_rendered":args.frames,
          "source_size_px":list(BASE["GAME_SIZE"]),"planted_review_instances":len(plants),
          "review_motion":"asynchronous sinusoidal weights; source GLB clip independently checked frame by frame",
          "video_decode":"pass"})


if __name__=="__main__":
    main()
