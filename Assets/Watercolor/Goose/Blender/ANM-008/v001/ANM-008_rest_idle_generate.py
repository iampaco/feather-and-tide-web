"""Build the planted-foot Rest_Idle cycle from the two landing endpoints."""
import math
import runpy
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

HERE = Path(__file__).resolve().parent
LAND = HERE.parents[1]/"ANM-007"/"v001"
SHARED = LAND/"ANM-007_landing_generate.py"
M = runpy.run_path(str(SHARED))
REF, FPS, REAR, TOP, DETAIL, SIDE, WIDE = (M[k] for k in ("REF","FPS","REAR","TOP","DETAIL","SIDE","WIDE_TOP"))
LAND_BLEND = LAND/"ANM-007_landing.blend"
STEM, CLIP = "ANM-008_rest_idle","Rest_Idle"
PERIOD = 144
OFFSETS = [7,19,31,43,55,67,79,91,103,115,127]


def rest_action(rig,base):
    neck = rig.pose.bones["Neck"]
    head = rig.pose.bones["Head"]
    neck_basis = neck.bone.matrix_local.to_3x3()
    head_basis = head.bone.matrix_local.to_3x3()
    neck_turn = (neck_basis@Vector((0,1,0))).rotation_difference(Vector((.76,.03,.66)))
    neck_target = neck_basis.inverted()@neck_turn.to_matrix()@neck_basis
    head_target = head_basis.inverted()@neck_turn.inverted().to_matrix()@Vector((.25,-1,-.24)).to_track_quat("Y","Z").to_matrix()

    def pose(frame):
        phase = ((frame-1)%PERIOD)/PERIOD
        edge = M["weight"](min((frame-1)%PERIOD,PERIOD-(frame-1)%PERIOD)/12)
        breath = math.sin(math.tau*2*phase)*edge
        groom = M["weight"]((phase-.28)/.20)*M["weight"]((.76-phase)/.18)
        feather_nod = .04*math.sin(math.tau*3*phase)*groom
        values = dict(base)
        # Quaternion interpolation distributes the backward glance over the
        # neck and head before the bill dips in the direction of the shoulder.
        for bone,target in ((neck,neck_target),(head,head_target)):
            path = bone.path_from_id("rotation_euler")
            rotation = Quaternion((1,0,0),base.get((path,0),0.))
            rest = rotation.slerp(target.to_quaternion(),(.43 if bone==head else .60)*groom)
            rest @= Quaternion((1,0,0),math.radians(.7*breath)+(feather_nod if bone==head else 0.))
            values.update({(path,i):v for i,v in enumerate(rest.to_euler("XYZ"))})
        for side in "LR":
            root = rig.pose.bones[f"WingRoot.{side}"].path_from_id("rotation_euler")
            M["rotate"](rig,values,f"WingRoot.{side}",math.degrees(base[root,0])+.42*breath)
        return values

    action = M["ACTION"](rig,CLIP,pose,list(range(1,PERIOD+2,4)),cyclic=True)
    M["decorate"](action,"Planted-foot breathing and a quiet feather-tending gesture.",
                  [(1,"Stand / seam"),(43,"Head turns"),(77,"Tend feathers"),(115,"Face forward"),(145,"Seam sample")])
    return action


def main(args):
    output = args.output
    dependency = M["checked"](LAND_BLEND,("needs_review","done"))
    scene,rig,mesh,manifest,scale = M["open_rig"]("ANM-008 | Editable Rest_Idle")
    mud = M["append"](LAND_BLEND,M["MUD"])
    water = M["append"](LAND_BLEND,M["WATER"])
    idle = rest_action(rig,M["SAMPLE"](mud,81))
    clips = {CLIP:idle}
    motion,qa = M["scan"](scene,mesh,rig,idle,ground=True)
    feet = M["geometry"](mesh)[2]
    rest = motion[1.]
    floor = float(min(rest[idx,2].min() for idx in feet.values()))
    planted = {s:max(M["distance"](pose[indices],rest[indices]) for pose in motion.values())
               for s,indices in feet.items()}
    clearance = min(float(pose[:,2].min()-floor) for pose in motion.values())*scale
    assert max(planted.values()) < 1e-6 and clearance > -.0001,(planted,clearance)
    qa["planted_feet"] = {"vertex_travel_BU_each":planted,"flat_reference_min_clearance_game_units":clearance}
    qa["landing_handoffs"] = {a.name:M["join_error"](scene,mesh,rig,a,81,idle,1) for a in (mud,water)}
    assert all(v["position_BU"] < 1e-6 and v["velocity_delta_BU_per_s"] < .005 for v in qa["landing_handoffs"].values())
    path = output/f"{STEM}.glb"
    report = {"idle":qa,"glb":M["export"](scene,mesh,rig,clips,path)}
    report["roundtrip"] = M["reimport"](scene,mesh,rig,clips,{CLIP:motion},path,not args.checks)
    review = M["review_scene"](scene,"Review | Wetland rest",scale,-8/scale,"A6A28B")
    bpy.context.window.scene = review
    review.frame_end = PERIOD
    group = REF["collection"](review,"Review | Resting companions")
    birds = []
    for i,offset in enumerate([0,*OFFSETS]):
        # A separate review-only strip samples the same rest loop at an offset.
        carrier,bird = M["actor"](review,group if i else review.collection,mesh,rig,idle,i)
        strip = bird.parent.animation_data.nla_tracks[0].strips[0]
        strip.repeat = 3
        strip.frame_start = 1-offset-PERIOD
        strip.frame_end = strip.frame_start+3*PERIOD
        x,y = M["SLOTS"][i-1] if i else (0,0)
        s = .8 if i else 1.
        carrier.location = (x/scale,y/scale,-8/scale-s*floor)
        birds.append(bird)
    report["flock"] = M["check_group"](review,birds,PERIOD,scale,-8/scale)
    for f,label in ((1,"Neutral"),(43,"Head turns"),(77,"Feather tending"),(115,"Return")):
        review.timeline_markers.new(label,frame=f)
    review.frame_set(77)
    M["save"](scene,rig,idle,output/f"{STEM}.blend",77)
    if not args.checks:
        bpy.context.window.scene = review
        group.hide_render = True
        still = M["still"]
        still(review,REAR,1,output,"rear_1x_stand")
        still(review,REAR,77,output,"rear_1x_tend")
        still(review,TOP,77,output,"top_1x_tend",(920,518))
        still(review,SIDE,77,output,"feet_contact_side",(920,518))
        carrier = birds[0].parent.parent
        carrier.scale = (.5,)*3
        carrier.location.z = -8/scale-.5*floor
        still(review,REAR,77,output,"rear_half_tend")
        still(review,TOP,77,output,"top_half_tend",(920,518))
        carrier.scale = (1.,)*3
        carrier.location.z = -8/scale-floor
        M["video"](review,DETAIL,PERIOD,output,"rest_detail",(832,468))
        group.hide_render = False
        still(review,REAR,77,output,"rear_flock_12")
        still(review,WIDE,77,output,"top_flock_12",(920,518))
        M["video"](review,REAR,PERIOD,output,"rest_flock_12")
    M["write_records"](output,Path(__file__),manifest,clips,
                       {"CHR-001/v001":"done","ANM-007/v001":dependency["status"]},(LAND_BLEND,SHARED),report,
                       {"surface":"flat wetland reference plane","follower_phase_offsets_frames":OFFSETS,
                        "landed_pose_frame":81,"seam_frame":145})


if __name__ == "__main__":
    main(M["options"]())
