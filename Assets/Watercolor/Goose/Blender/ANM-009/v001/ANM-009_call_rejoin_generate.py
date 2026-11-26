"""Build an in-place call and a phase-matched return to normal flight."""
import math
import runpy
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
SHARED = HERE.parents[1]/"ANM-007"/"v001"/"ANM-007_landing_generate.py"
M = runpy.run_path(str(SHARED))
REF,FPS,REAR,TOP,DETAIL,WIDE = (M[k] for k in ("REF","FPS","REAR","TOP","DETAIL","WIDE_TOP"))
STEM,CALL,REJOIN = "ANM-009_call_rejoin","Call_Loop","Rejoin"
PERIOD,REJOIN_END = 56,53
SWITCH,RESUME,END = 113,165,217
DETACHED_SLOT = (63,-43)
RETURN_SLOT = (43,-38)
SLOTS = [(-45,-18),(45,-18),(0,-37),(-75,-39),(-40,-46),(-75,-67),
         (0,-72),(37,-70),(-36,-83),(67,-61)]


def call_action(rig):
    def pose(frame):
        phase = (frame-1)/PERIOD
        pulse = math.sin(math.pi*phase)**2
        flutter = math.sin(math.tau*phase)*pulse
        values = {}
        for name,angle in (("Body",1.1*pulse),("Neck",5*pulse),("Head",4.5*pulse),("Tail",-1.5*pulse)):
            M["rotate"](rig,values,name,angle)
        for side,sign in (("L",-1),("R",1)):
            for name,angle in (("WingRoot",5+18*flutter),("Elbow",2+5*flutter),
                               ("Wrist",-2-8*flutter),("Tip",-1-4*flutter)):
                M["rotate"](rig,values,f"{name}.{side}",angle)
            M["rotate"](rig,values,f"Wrist.{side}",sign*2*pulse,1)
        return values
    action = M["ACTION"](rig,CALL,pose,list(range(1,PERIOD+2,4)),cyclic=True)
    M["decorate"](action,"Brief in-place wing cue and raised head for a separated companion.",
                  [(1,"Neutral call / seam"),(17,"Short wingbeat"),(29,"Head lift"),(57,"Seam sample")])
    return action


def rejoin_action(rig,call,cruise):
    def pose(frame):
        a,b = M["SAMPLE"](call,frame),M["SAMPLE"](cruise,1+frame-REJOIN_END)
        w = M["weight"]((frame-1)/(REJOIN_END-1))
        return {key:(1-w)*a.get(key,0.)+w*b.get(key,0.) for key in a.keys()|b.keys()}
    action = M["ACTION"](rig,REJOIN,pose,list(range(1,REJOIN_END+1,2)))
    M["decorate"](action,"Release the call gesture into the first recovery phase of Cruise_Flap_Loop.",
                  [(1,"Call phase zero"),(27,"Settle wingbeat"),(53,"Cruise recovery")])
    return action


def combined_action(rig,call,rejoin,cruise):
    keys = set().union(*(M["SAMPLE"](a,1) for a in (call,rejoin,cruise)))
    def pose(frame):
        if frame < SWITCH:
            a,t = call,1+(frame-1)%PERIOD
        elif frame <= RESUME:
            a,t = rejoin,1+frame-SWITCH
        else:
            a,t = cruise,1+(frame-RESUME)%52
        values = M["SAMPLE"](a,t)
        return {key:values.get(key,0.) for key in keys}
    return M["ACTION"](rig,"Review | Call to rejoin to cruise",pose,list(range(1,END+1)))


def add_locator(scene,carrier):
    # Non-rendering locator for later FX-009 attachment; production GLB stays clean.
    marker = bpy.data.objects.new("FX-009 | preview attachment",None)
    scene.collection.objects.link(marker)
    marker.parent = carrier
    marker.empty_display_type = "SPHERE"
    marker.empty_display_size = .09
    marker.location.z = .38
    marker["Purpose"] = "Preview attachment anchor above separated goose; locator and range come from the game."


def main(args):
    output = args.output
    scene,rig,mesh,manifest,scale = M["open_rig"]("ANM-009 | Editable call and rejoin")
    cruise = M["cruise_reference"]()
    call = call_action(rig)
    rejoin = rejoin_action(rig,call,cruise)
    clips = {CALL:call,REJOIN:rejoin}
    motions,qa = {},{"clips":{}}
    for name,action in clips.items():
        motions[name],qa["clips"][name] = M["scan"](scene,mesh,rig,action)
        low = float(min(p[:,2].min() for p in motions[name].values()))
        qa["clips"][name]["leader_and_follower_min_clearance_game_units"] = [8+scale*low,6+.8*scale*low]
        assert 6+.8*scale*low > 0
    qa["joins"] = {"call_to_rejoin":M["join_error"](scene,mesh,rig,call,57,rejoin,1),
                   "rejoin_to_cruise":M["join_error"](scene,mesh,rig,rejoin,53,cruise,1)}
    assert all(v["position_BU"] < 1e-6 and v["velocity_delta_BU_per_s"] < .025 for v in qa["joins"].values()),qa["joins"]
    path = output/f"{STEM}.glb"
    qa["glb"] = M["export"](scene,mesh,rig,clips,path)
    qa["roundtrip"] = M["reimport"](scene,mesh,rig,clips,motions,path,not args.checks)
    review_action = combined_action(rig,call,rejoin,cruise)
    review = M["review_scene"](scene,"Review | Separated companion",scale,-8/scale)
    bpy.context.window.scene = review
    review.frame_end = END
    group = REF["collection"](review,"Review | Flock")
    birds = []
    for i in range(11):
        carrier,bird = M["actor"](review,group,mesh,rig,cruise,i)
        strip = bird.parent.animation_data.nla_tracks[0].strips[0]
        strip.repeat = 7
        strip.frame_start = 1-i*4-52
        strip.frame_end = strip.frame_start+7*52
        x,y = SLOTS[i-1] if i else (0,0)
        carrier.location = (x/scale,y/scale,-2/scale if i else 0.)
        birds.append(bird)
    carrier,bird = M["actor"](review,review.collection,mesh,rig,review_action,11)
    birds.append(bird)
    M["key_carrier"](carrier,[(f,tuple((a+(b-a)*M["weight"]((f-SWITCH)/(RESUME-SWITCH)))/scale
                                      for a,b in zip((*DETACHED_SLOT,-2),(*RETURN_SLOT,-2))))
                              for f in range(1,END+1)])
    add_locator(review,carrier)
    qa["flock"] = M["check_group"](review,birds,END,scale,-8/scale)
    for f,label in ((1,"Separated | Call"),(SWITCH,"Return starts"),(RESUME,"Cruise phase 1"),(END,"End")):
        review.timeline_markers.new(label,frame=f)
    qa["preview_motion"] = {"separated_xy_game":DETACHED_SLOT,"final_xy_game":RETURN_SLOT,
                            "travel_only_on_preview_carrier":True,"fx009_preview_anchor":"FX-009 | preview attachment"}
    review.frame_set(29)
    M["save"](scene,rig,call,output/f"{STEM}.blend",29)
    if not args.checks:
        bpy.context.window.scene = review
        still = M["still"]
        still(review,REAR,29,output,"rear_flock_call")
        still(review,WIDE,29,output,"top_flock_call",(920,518))
        still(review,WIDE,139,output,"top_flock_rejoining",(920,518))
        still(review,WIDE,181,output,"top_flock_rejoined",(920,518))
        M["video"](review,REAR,END,output,"call_rejoin_flock_12")
        group.hide_render = True
        # A close camera follows the detached goose only in this diagnostic scene.
        focus = REF["camera"](review.collection,"Review | call close",(.65,-1.5,1.1),(0,.07,.08),ortho=1.85)
        focus.parent = carrier
        still(review,"Review | call close",29,output,"rear_1x_call",(864,486))
        still(review,"Review | call close",139,output,"rear_1x_rejoining",(864,486))
        # Restore the stationary call pose and use a separate centered scene
        # for same-camera 1x and 0.5x silhouette evidence.
        single = M["review_scene"](scene,"Diagnostic | Call scale",scale,-8/scale)
        bpy.context.window.scene = single
        scale_carrier,_ = M["actor"](single,single.collection,mesh,rig,call,0)
        still(single,REAR,29,output,"fixed_1x_call")
        still(single,TOP,29,output,"top_1x_call",(920,518))
        scale_carrier.scale = (.5,)*3
        still(single,REAR,29,output,"fixed_half_call")
        still(single,TOP,29,output,"top_half_call",(920,518))
        bpy.context.window.scene = review
        M["video"](review,"Review | call close",END,output,"call_rejoin_detail",(832,468))
    M["write_records"](output,Path(__file__),manifest,clips,{"CHR-001/v001":"done"},(SHARED,),qa,
                       {"call_seam_frame":57,"rejoin_cruise_exit_frame":1,"review_rejoin_start":SWITCH,
                        "review_cruise_start":RESUME,"fx009":"preview anchor only; follow character world position"})


if __name__ == "__main__":
    main(M["options"]())
