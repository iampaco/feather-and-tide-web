"""Render the fork, entry and exit of the lake rest patch with the same follow camera."""
import argparse
from pathlib import Path
import runpy
import subprocess
import sys

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
LIB = runpy.run_path(str(HERE/"ENV-015_generate.py"))
BASE = LIB["B"]
CHAPTERS = (
    ("See the lake branch", ((-.4,-3.8),(0,0),(.9,3.07))),
    ("Move in from lake", LIB["ROUTE"]["entry"]),
    ("Return to main lake", LIB["ROUTE"]["exit"]),
)


def interpolate(points, t):
    track = tuple(Vector(point) for point in points)
    u = (len(track)-1)*t
    i = min(int(u),len(track)-2)
    q = u-i
    a,b,c,d=track[max(i-1,0)],track[i],track[i+1],track[min(i+2,len(track)-1)]
    return .5*(2*b+(c-a)*q+(2*a-5*b+4*c-d)*q*q+(-a+3*b-3*c+d)*q*q*q)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--ffmpeg",default="/opt/homebrew/bin/ffmpeg")
    parser.add_argument("--per-shot",type=int,default=12)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    target=args.output.resolve()
    target.mkdir(parents=True,exist_ok=True)
    LIB["check"](not any(target.iterdir()) and args.per_shot>=8, "Use an empty output directory and at least 8 frames per shot.")
    bpy.ops.wm.open_mainfile(filepath=str(args.candidate.resolve()/f"{LIB['STEM']}.blend"))
    scene=bpy.data.scenes["ENV-015 | Material review in long lake"]
    bpy.context.window.scene=scene
    camera=scene.camera
    bird=next(obj for obj in scene.objects if obj.name.startswith("Review | flight reference CHR-001"))
    frames=target/"frames"
    frames.mkdir()
    for shot,(_,points) in enumerate(CHAPTERS):
        for i in range(args.per_shot):
            t=i/(args.per_shot-1)
            xy=interpolate(points,t)
            direction=(interpolate(points,min(t+.01,1))-interpolate(points,max(t-.01,0))).normalized()
            BASE["pose_at"](camera,bird,xy,direction)
            BASE["render"](scene,camera,frames,f"{shot*args.per_shot+i:04d}",LIB["SIZE"],9)
    output=target/"review_lake_route.mp4"
    subprocess.run([args.ffmpeg,"-hide_banner","-loglevel","error","-framerate","10",
                    "-i",str(frames/"%04d.png"),"-vf","pad=852:394:0:0,fps=20","-c:v","libx264",
                    "-pix_fmt","yuv420p","-crf","18","-movflags","+faststart","-an",str(output)],check=True)
    subprocess.run([args.ffmpeg,"-hide_banner","-loglevel","error","-xerror","-i",str(output),"-f","null","-"],check=True)
    LIB["write"](target/"motion_report.json",{"result":"pass","section_order":[step[0] for step in CHAPTERS],
                 "source_frame_size":LIB["SIZE"],"video_frame_size":[852,394],"source_frame_count":len(CHAPTERS)*args.per_shot,
                 "output_fps":20,"h264_decode":"pass","fps_is_review_video_only":True})


if __name__=="__main__":
    main()
