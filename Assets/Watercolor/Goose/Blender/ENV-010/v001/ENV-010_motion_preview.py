"""Render the delivered mountain pass with a fixed rear follow camera and moving mist."""
import argparse
from pathlib import Path
import runpy
import subprocess
import sys

import bpy
from mathutils import Vector


HERE=Path(__file__).resolve().parent
WORKFLOW=runpy.run_path(str(HERE/"ENV-010_generate.py"))
B=WORKFLOW["BASE"]


def trail(t):
    points=[(-4.5,5.6),(-7.0,8.7),(-9.4,12.3),(-11.56,19.2),(-11.96,25.2),(-11.27,31.3),
            (-10.89,36.5)]
    x=t*(len(points)-1)
    span=min(int(x),len(points)-2)
    offset=x-span
    a,b,c,d=[Vector(points[min(max(0,index),len(points)-1)]) for index in range(span-1,span+3)]
    return .5*((2*b)+(c-a)*offset+(2*a-5*b+4*c-d)*offset**2+(-a+3*b-3*c+d)*offset**3)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--frames",type=int,default=36)
    parser.add_argument("--ffmpeg",default="/opt/homebrew/bin/ffmpeg")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()) or args.frames < 15:raise ValueError("Use an empty folder and at least 15 frames.")
    bpy.ops.wm.open_mainfile(filepath=str(HERE/"ENV-010_short_pass.blend"))
    scene=bpy.data.scenes["ENV-010 | Fixed rear and corridor"]
    bpy.context.window.scene=scene
    cam=scene.camera
    bird=scene.objects["Review | CHR-001 neutral pose"]
    mist=scene.objects["Ridge streamers | atmospheric review"]
    frames=out/"frames"
    frames.mkdir()
    for i in range(args.frames):
        t=i/(args.frames-1)
        spot=trail(t)
        heading=(trail(min(1,t+.02))-trail(max(0,t-.02))).normalized()
        B["pose_at"](cam,bird,spot,heading)
        mist.location.x=4.6*t
        B["render"](scene,cam,frames,f"{i:04}",B["GAME_SIZE"],10)
    video=out/"preview_pass_motion.mp4"
    subprocess.run([args.ffmpeg,"-hide_banner","-loglevel","error","-framerate","12","-i",str(frames/"%04d.png"),
                    "-vf","pad=852:394:0:0,fps=24","-c:v","libx264","-pix_fmt","yuv420p","-crf","18","-an",
                    "-movflags","+faststart",str(video)],check=True)
    subprocess.run([args.ffmpeg,"-hide_banner","-loglevel","error","-xerror","-i",str(video),
                    "-f","null","-"],check=True)
    B["write_json"](out/"motion_check.json",{"result":"pass","rendered_frames":args.frames,
        "source_size_px":list(B["GAME_SIZE"]),"mist_shift_BU":4.6,"leader_path_Y_range_BU":[5.6,36.5],
        "blender_preview_only":True,"video_decode":"pass"})


if __name__=="__main__":
    main()
