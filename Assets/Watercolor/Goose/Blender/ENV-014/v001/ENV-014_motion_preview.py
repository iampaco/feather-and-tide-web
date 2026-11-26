"""Render a fixed-follow wetland approach and a checkpoint A view from the editable mother."""
import argparse
import math
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import bpy
from mathutils import Vector


HERE=Path(__file__).resolve().parent
BUILD=runpy.run_path(str(HERE/"ENV-014_generate.py"))
B=BUILD["B"]


def route(t):
    if t < .55:
        a=t/.55
        return Vector((-6.4+3.9*a,-16.8+8.2*a))
    a=(t-.55)/.45
    return Vector((-2.5+2.5*B["smooth"](a),-8.6+8.6*a))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--frames",type=int,default=36)
    parser.add_argument("--ffmpeg",default="/opt/homebrew/bin/ffmpeg")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()) or args.frames<15:raise ValueError("Use an empty folder and at least 15 frames.")
    bpy.ops.wm.open_mainfile(filepath=str(HERE/f"{BUILD['STEM']}.blend"))
    scene=bpy.data.scenes["ENV-014 | Fixed rear and route context"]
    bpy.context.window.scene=scene
    cam=scene.camera
    bird=next(o for o in scene.objects if o.name.startswith("Review | CHR-001 neutral pose"))
    frames=output/"frames"
    frames.mkdir()
    for i in range(args.frames):
        time=i/(args.frames-1)
        point=route(time)
        heading=(route(min(1,time+.012))-route(max(0,time-.012))).normalized()
        B["pose_at"](cam,bird,point,heading)
        B["render"](scene,cam,frames,f"{i:04}",BUILD["SIZE"],11)
    video=output/"preview_checkpoint_motion.mp4"
    ffmpeg=shutil.which(args.ffmpeg) or args.ffmpeg
    subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-framerate","12","-i",str(frames/"%04d.png"),
                    "-vf","pad=852:394:0:0,fps=24","-c:v","libx264","-pix_fmt","yuv420p","-crf","18","-an",
                    "-movflags","+faststart",str(video)],check=True)
    subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-xerror","-i",str(video),"-f","null","-"],check=True)
    BUILD["write"](output/"motion_report.json",{"result":"pass","source_px":list(BUILD["SIZE"]),
                   "frames":args.frames,"preview_only":True,"heading_changes_only_as_leader_turns":True,
                   "h264_decode":"pass"})


if __name__=="__main__":
    main()
