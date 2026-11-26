"""Build the S4 one-shot edge cue, and re-import its GLB in a clean process."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np

ID="FX-011"
ROOT="TurbineWarn"
BLEND="FX-011_TurbineWarn.blend"
GLB="FX-011_TurbineWarn.glb"
FX="FX-010/v001"
FARM="STR-002/v001"
EDGE="ApproachEdge"
WAVE="ContactPressure"
EDGE_CLIP="ApproachCue"
WAVE_CLIP="BoundaryContact"
EDGE_TEX="ft_goose_fx_turbine_warn_edge_basecolor_alpha.png"
WAVE_TEX="ft_goose_fx_turbine_warn_pressure_basecolor_alpha.png"
FRAME=(852,393)
FPS=24
PEAK_FRAME=28
VIDEO_FPS=8
PLACE="warning_review.json"


def initialize(lib, source):
    helper=runpy.run_path(str(lib/FX/"FX-010_generate.py"))
    upstream=helper["initialize"](lib)
    single,farm,env,fog,layout,discs,arcs,points,joins,swift=upstream
    inputs=json.loads(source.read_text())
    assert inputs["review_only_timing"]["fps"]==FPS
    assert inputs["engine_contract"]["collision_enabled"] is False
    return helper,upstream,inputs


def closed_samples(points):
    lengths=[0.]
    for a,b in zip(points,points[1:]+points[:1]):
        lengths.append(lengths[-1]+(b-a).length)
    return np.asarray(lengths)


def resample(points, distances, at):
    total=distances[-1]
    t=at%total
    i=int(np.searchsorted(distances,t,side="right"))-1
    f=(t-distances[i])/(distances[i+1]-distances[i])
    return points[i].lerp(points[(i+1)%len(points)],f)


def placement(upstream, inputs):
    layout,discs,_,points,_,_=upstream[4:]
    spec=inputs["placement"]
    _,center,radius=next(item for item in discs if item[0]==spec["instance"])
    lateral=spec["probe_path_x_offset_from_base_BU"]
    line_x=center.x+lateral
    touch=Vector((line_x,center.y-math.sqrt(radius**2-lateral**2)))
    distances=closed_samples(points)
    # Project to the approved discretized FX-010 edge, preserving the exact same polyline.
    best=None
    for i,(a,b) in enumerate(zip(points,points[1:]+points[:1])):
        segment=b-a
        f=min(1,max(0,(touch-a).dot(segment)/segment.length_squared))
        hit=a+segment*f
        candidate=((touch-hit).length,distances[i]+segment.length*f)
        if best is None or candidate[0]<best[0]:
            best=candidate
    assert best[0] < layout["sweep"]["geometric_tolerance_BU"],best
    return touch,distances,best[1],best[0]


def materials(helper, lib, out):
    folder=out/"textures"
    folder.mkdir()
    grain_img=bpy.data.images.load(str(lib/helper["PAPER"]))
    raw=helper["image_pixels"](grain_img)[:,:,:3].mean(axis=2)
    bpy.data.images.remove(grain_img)
    grain=raw[np.arange(128)[:,None]*3,np.arange(512)[None,:]]
    grain=(grain-grain.mean())/max(.01,grain.std())
    u=(np.arange(512)[None,:]+.5)/512
    v=(np.arange(128)[:,None]+.5)/128
    smooth=helper["smoothstep"]
    ends=smooth(0,.23,u)*(1-smooth(.77,1,u))
    for file,base,rim,alpha in (
            (EDGE_TEX,(203,164,98),(247,225,164),.88),
            (WAVE_TEX,(116,109,134),(182,168,183),.57)):
        core=np.exp(-((v-.28)/.36)**2)
        opacity=alpha*ends*core*smooth(0,.105,v)*(1-smooth(.43,1,v))
        rgba=np.empty((128,512,4),dtype=np.uint8)
        for i,(a,b) in enumerate(zip(base,rim)):
            rgba[:,:,i]=np.rint(np.clip(a+(b-a)*core+2.2*grain,0,255))
        rgba[:,:,3]=np.rint(np.clip(opacity*(1+.035*grain),0,1)*255)
        rgba[[0,-1],:,3]=0
        rgba[:,[0,-1],3]=0
        helper["png"](folder/file,rgba)
    return [helper["material"](out,file,name) for file,name in (
        (EDGE_TEX,"Muted amber | approach edge"),(WAVE_TEX,"Grey violet | contact pressure"))]


def band_positions(pairs, shift, thickness):
    points=[]
    for b,direction in pairs:
        for distance in (shift,shift+thickness):
            p=b+direction*distance
            points.append((p.x,p.y,0.))
    return points


def make_band(helper,single,group,root,name,material,points,distances,anchor,span,width,z):
    count=97
    stations=np.linspace(anchor-span/2,anchor+span/2,count)
    origin=resample(points,distances,anchor)
    pairs=[]
    for at in stations:
        here=resample(points,distances,at)
        tangent=(resample(points,distances,at+.02)-resample(points,distances,at-.02)).normalized()
        pairs.append((here-origin,Vector((-tangent.y,tangent.x))))
    uv=[(i/(count-1),j) for i in range(count) for j in (0,1)]
    faces=[(2*i,2*i+2,2*i+3,2*i+1) for i in range(count-1)]
    mesh=helper["mesh"](single,group,root,name,band_positions(pairs,0,width),faces,material,uv,
                         location=(*origin,z))
    mesh["collision_enabled"]=False
    mesh["pivot_role"]="Anchor on the candidate boundary"
    return mesh,pairs


def shape(obj, name, positions):
    if not obj.data.shape_keys:
        obj.shape_key_add(name="Basis")
    key=obj.shape_key_add(name=name,from_mix=False)
    for vertex,co in zip(key.data,positions):
        vertex.co=co
    return key


def animate(obj,name,samples):
    for f,values in samples:
        for key,value in values.items():
            block=obj.data.shape_keys.key_blocks[key]
            block.value=value
            block.keyframe_insert(data_path="value",frame=f)
    anim=obj.data.shape_keys.animation_data
    anim.action.name=name
    for curve in anim.action.layers[0].strips[0].channelbag(anim.action_slot).fcurves:
        for k in curve.keyframe_points:
            k.interpolation="LINEAR"
    return anim


def create(scene,lib,out,bundle):
    helper,upstream,inputs=bundle
    single,*_=upstream
    points=upstream[7]
    spec=inputs["placement"]
    touch,distances,anchor,delta=placement(upstream,inputs)
    group=single["collection_in"](scene,"FX-011 | TurbineWarn")
    root=single["object_in"](group,ROOT)
    root["collision_enabled"]=False
    root["playback"]="Two independent one-shot clips; host game controls playback"
    root["boundary_source"]="FX-010 RotorFootprint from STR-002/v001/farm_layout.json"
    root["review_sample"]=spec["instance"]
    amber,violet=materials(helper,lib,out)
    edge,pairs=make_band(helper,single,group,root,EDGE,amber,points,distances,anchor,
        spec["edge_span_length_BU"],spec["edge_max_inward_width_BU"],spec["edge_height_BU"])
    shape(edge,"Closed",band_positions(pairs,0,0))
    edge_anim=animate(edge,EDGE_CLIP,[(f,{"Closed":closed}) for f,closed in (
        (0,1),(4,.85),(10,.28),(16,0),(23,.06),(32,.23),(42,.40),(54,.62),(66,.81),(72,1))])
    wave,pairs=make_band(helper,single,group,root,WAVE,violet,points,distances,anchor,
        spec["wave_span_length_BU"],spec["wave_max_width_BU"],spec["wave_height_BU"])
    travel=spec["wave_max_inward_travel_BU"]
    shape(wave,"ClosedAtEdge",band_positions(pairs,0,0))
    shape(wave,"ClosedInside",band_positions(pairs,travel,0))
    shape(wave,"OpenInside",band_positions(pairs,travel,spec["wave_max_width_BU"]))
    wave_anim=animate(wave,WAVE_CLIP,[(f,dict(zip(("ClosedAtEdge","ClosedInside","OpenInside"),v)))
        for f,v in ((0,(1,0,0)),(3,(.76,.05,0)),(7,(.20,.21,.15)),(11,(0,.30,.38)),
                    (16,(0,.59,.39)),(21,(0,.83,.16)),(26,(0,1,0)))])
    scene.frame_set(0)
    bpy.context.view_layer.update()
    return group,root,edge,wave,edge_anim,wave_anim


def export(scene,group,path):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in group.objects:
        obj.select_set(True)
    scene.frame_start,scene.frame_end=0,72
    scene.frame_set(0)
    status=bpy.ops.export_scene.gltf(filepath=str(path),use_selection=True,
        export_extras=True,export_yup=True,export_animations=True,export_animation_mode="ACTIONS",
        export_frame_range=False,export_force_sampling=False,export_anim_single_armature=False,
        export_optimize_animation_size=False)
    assert status=={"FINISHED"},status


def place_in_timeline(anim, label, frame):
    action,slot=anim.action,anim.action_slot
    anim.action=None
    nla=anim.nla_tracks.new()
    nla.name=label
    strip=nla.strips.new(label,frame,action)
    strip.action_slot=slot
    strip.extrapolation="HOLD"
    return strip


def imported_anim(obj, name):
    anim=obj.data.shape_keys.animation_data
    if anim.action is None:
        match=next((t.strips[0] for t in anim.nla_tracks if name in t.name or name in t.strips[0].action.name),
                   None)
        assert match is not None,(obj.name,[(t.name,t.strips[0].action.name) for t in anim.nla_tracks])
        anim.action=match.action
        anim.action_slot=match.action_slot
    for track in list(anim.nla_tracks):
        anim.nla_tracks.remove(track)
    return anim


def set_timeline(scene,inputs,edge_anim,wave_anim):
    times=inputs["review_only_timing"]
    scene.frame_start=0
    scene.frame_end=times["review_end_frame_exclusive"]-1
    place_in_timeline(edge_anim,EDGE_CLIP,times["approach_event_frame"])
    place_in_timeline(wave_anim,WAVE_CLIP,times["edge_contact_event_frame"])


def context(scene,lib,bundle,imported=True):
    helper,upstream,inputs=bundle
    _,rotors,stage=helper["build_context"](scene,lib,upstream,imported=imported)
    for tag,rotor in rotors.items():
        if imported:
            helper["use_imported_actions"](rotor)
    bpy.ops.import_scene.gltf(filepath=str(lib/FX/"FX-010_RotorFootprint.glb"))
    footprint=bpy.data.objects[helper["ASSET"]]
    for obj in footprint.children:
        helper["use_imported_actions"](obj)
    return stage


def pose(scene,bundle,stage,frame,amount=1,route=False):
    helper,upstream,inputs=bundle
    single,farm,env,fog,layout,discs,arcs,points,*_=upstream
    scene.frame_set(frame)
    times=inputs["review_only_timing"]
    if route:
        x,y=layout["review_route"]["leader_x_BU"],-23.
        heading=Vector((math.sin(.28),math.cos(.28)))
    else:
        touch,*_=placement(upstream,inputs)
        x=touch.x
        y=touch.y+(frame-times["edge_contact_event_frame"])*times["review_ground_speed_BU_per_second"]/FPS
        heading=Vector((0,1))
    base=env["B"]
    lift=layout["review_route"]["overflight_lift_game_units"]
    base["follow"](stage["cam"],(x,y),heading)
    stage["cam"].location.z+=lift*layout["BU_per_game_unit"]
    for i,(bird,offset) in enumerate(zip(stage["flight"],farm["slot_offsets"](36*layout["BU_per_game_unit"]))):
        bird.location=(x+offset.x,y+offset.y,(lift+(8 if i==0 else 6))*layout["BU_per_game_unit"])
        bird.hide_render=not route and i!=0
    for bird in stage["resting"]:
        bird.hide_render=True
    fog["accessibility"](stage["fog_rows"],amount)
    fog["position_cards"](stage["fog_rows"],frame/(FPS*layout["review_atmosphere"]["drift_period_seconds"]),amount)
    bpy.context.view_layer.update()


def vertices_of(obj):
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return [evaluated.matrix_world@v.co for v in evaluated.data.vertices]


def area_of_band(obj, vertices):
    obj.data.calc_loop_triangles()
    return sum((vertices[b]-vertices[a]).cross(vertices[c]-vertices[a]).length*.5
               for a,b,c in (tuple(t.vertices) for t in obj.data.loop_triangles))


def edge_vertices(obj, vertices):
    uv=obj.data.uv_layers.active.data
    return [vertices[i] for i in {loop.vertex_index for loop in obj.data.loops if uv[loop.index].uv.y<.01}]


def physical_checks(scene,edge,wave,bundle):
    helper,upstream,inputs=bundle
    single,farm,env,fog,layout,discs,arcs,points,*_=upstream
    check=single["check"]
    placement_data=inputs["placement"]
    times=inputs["review_only_timing"]
    touch,distances,anchor,delta=placement(upstream,inputs)
    y0=touch.y
    probe=np.linspace(0,times["review_end_frame_exclusive"],times["review_end_frame_exclusive"]*2+1)
    states=[]
    maximum_outside=0
    edge_axis_error=0
    widths={EDGE:[],WAVE:[]}
    for f in probe:
        scene.frame_set(int(f),subframe=f%1)
        vy=y0+(f-times["edge_contact_event_frame"])*times["review_ground_speed_BU_per_second"]/FPS
        states.append(any(math.hypot(touch.x-c.x,vy-c.y)<=r+2e-6 for _,c,r in discs))
        for ob in (edge,wave):
            vertices=vertices_of(ob)
            widths[ob.name].append(area_of_band(ob,vertices))
            maximum_outside=max(maximum_outside,max(min(math.hypot(v.x-c.x,v.y-c.y)-r for _,c,r in discs)
                                                     for v in vertices))
            check(max(abs(v.z-placement_data["edge_height_BU" if ob==edge else "wave_height_BU"])
                      for v in vertices)<1e-5,(f,ob.name))
        if f==PEAK_FRAME:
            vertices=edge_vertices(edge,vertices_of(edge))
            approx=helper["arc_distance"](np.asarray([p.x for p in vertices]),
                                           np.asarray([p.y for p in vertices]),arcs)
            edge_axis_error=float(max(approx))
    generation=[]
    for label,start,duration in ((EDGE,times["approach_event_frame"],72),
                                 (WAVE,times["edge_contact_event_frame"],26)):
        end=start+duration
        active=[i/2 for i,w in enumerate(widths[label]) if w>1e-5]
        check(active and min(active)>start and max(active)<end,(label,min(active),max(active)))
        spans=sum(w>1e-5 and (i==0 or widths[label][i-1]<=1e-5) for i,w in enumerate(widths[label]))
        check(spans==1,(label,spans))
        generation.append({"mesh":label,"positive_width_start_end_frames":[min(active),max(active)],
                           "nonzero_intervals":spans,"max_planar_area_BU2":max(widths[label])})
    check(not any(states[:times["edge_contact_event_frame"]*2]) and
          all(states[times["edge_contact_event_frame"]*2:]),"Review approach entry geometry")
    check(maximum_outside<layout["sweep"]["geometric_tolerance_BU"] and edge_axis_error<.0002,
          (maximum_outside,edge_axis_error))
    edge_to_event=(times["edge_contact_event_frame"]-times["approach_event_frame"])/FPS
    return {"boundary_anchor_xy_BU":list(touch),"analytic_contact_to_FX010_Boundary_delta_BU":delta,
            "max_animated_vertex_outside_union_BU":maximum_outside,
            "max_approach_edge_axis_error_BU":edge_axis_error,
            "authored_prewarning_seconds":edge_to_event,"sampled_half_frames":len(probe),
            "review_first_analytic_entry_frame":probe[states.index(True)],"independent_single_playbacks":generation,
            "note":"Offline programmed crossing. Collision, timing and rearming use game Zone."}


def projected_checks(scene, output, stage, edge, bundle):
    helper,upstream,inputs=bundle
    single,_,env,fog,layout,*_=upstream
    cam=stage["cam"]
    ref=helper["image_rgb"](output/"comparison_idle_default.png")
    showed=helper["image_rgb"](output/"preview_fog_default.png")
    diff=np.max(np.abs(ref-showed),axis=2)
    pixels=int((diff>=12/255).sum())
    assert pixels>80, pixels
    amount_metrics={}
    for label,amount in layout["review_atmosphere"]["levels"].items():
        pose(scene,bundle,stage,PEAK_FRAME,amount)
        vertices=vertices_of(edge)
        samples=[]
        transmittance=[]
        for v in vertices[len(vertices)//5:4*len(vertices)//5:2]:
            location=world_to_camera_view(scene,cam,v)
            if location.z>0 and .01<location.x<.99 and .01<location.y<.99:
                j,i=int(location.x*FRAME[0]),int(location.y*FRAME[1])
                samples.append(float(diff[i-2:i+3,j-2:j+3].max()))
                transmittance.append(fog["blocked_alpha"](cam,v,stage["fog_rows"],stage["masks"],amount))
        assert len(samples)>30 and np.median(samples)>=12/255,(label,len(samples),np.median(samples))
        assert max(transmittance)<=layout["review_atmosphere"]["candidate_alpha_caps"][label],(label,transmittance)
        amount_metrics[label]={"visible_projected_samples":len(samples),
                               "max_fog_alpha_at_warn_vertices":max(transmittance)}
    return {"pixels_changed_by_at_least_12_vs_idle":pixels,
            "median_default_local_rgb_delta_8bit":float(np.median(samples))*255,
            "fog_at_warn_samples":amount_metrics}


def video_info(path):
    subprocess.run(["ffmpeg","-v","error","-xerror","-i",str(path),"-f","null","-"],check=True)
    info=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_entries",
        "stream=codec_type,codec_name,width,height,nb_read_frames,duration,r_frame_rate","-of","json",str(path)]))
    video,=info["streams"]
    assert video["codec_type"]=="video" and video["codec_name"]=="h264"
    assert (video["width"],video["height"])==(852,394) and int(video["nb_read_frames"])==40
    assert float(video["duration"])==5.0
    return video


def build(lib,out,bundle):
    helper,upstream,inputs=bundle
    single,farm,env,fog,layout,discs,arcs,points,*_=upstream
    base=env["B"]
    scene=single["reset"]()
    scene.name="FX-011 | S4 approach and contact review"
    group,root,edge,wave,ea,wa=create(scene,lib,out,bundle)
    export(scene,group,out/GLB)
    set_timeline(scene,inputs,ea,wa)
    annotations=physical_checks(scene,edge,wave,bundle)
    for name,frame in (("Approach cue",12),("Boundary contact",84),("Quiet",110)):
        scene.timeline_markers.new(name,frame=frame)
    stage=context(scene,lib,bundle)
    proof=farm["layout_proof"](layout,discs,stage["bird"],stage["layers"],
                               stage["resting"],upstream[-1],single["check"])
    pose(scene,bundle,stage,PEAK_FRAME,0)
    originals=[edge.data.materials[0],wave.data.materials[0]]
    gray=base["paint"]("Neutral review | edge geometry","B4AFAB")
    for item in (edge,wave):
        item.data.materials[0]=gray
    base["render"](scene,stage["cam"],out,"graybox_fixed_rear",FRAME,8)
    pose(scene,bundle,stage,PEAK_FRAME,0,route=True)
    base["render"](scene,stage["top"],out,"graybox_top",(880,960),8)
    for item,mat in zip((edge,wave),originals):
        item.data.materials[0]=mat
    for label,amount in layout["review_atmosphere"]["levels"].items():
        pose(scene,bundle,stage,PEAK_FRAME,amount)
        base["render"](scene,stage["cam"],out,"preview_fog_"+label,FRAME,14)
    pose(scene,bundle,stage,PEAK_FRAME)
    group.hide_render=True
    base["render"](scene,stage["cam"],out,"comparison_idle_default",FRAME,14)
    group.hide_render=False
    visibility=projected_checks(scene,out,stage,edge,bundle)
    pose(scene,bundle,stage,98)
    base["render"](scene,stage["cam"],out,"preview_contact",FRAME,14)
    pose(scene,bundle,stage,PEAK_FRAME,route=True)
    base["render"](scene,stage["top"],out,"preview_route_top",(880,960),12)
    close_top=base["camera"](stage["studio"],"Technical detail | exposed edge",
                            (20,-5,18),(20,-5,0),11)
    base["render"](scene,close_top,out,"preview_warning_detail",(760,700),14)
    for frame,name in ((0,"Idle"),(12,"Approach"),(84,"Contact"),(110,"Clear")):
        if name not in scene.timeline_markers:
            scene.timeline_markers.new(name,frame=frame)
    pose(scene,bundle,stage,PEAK_FRAME)
    base["set_preview_workspace"](scene,stage["cam"])
    scene.render.resolution_x,scene.render.resolution_y=FRAME
    scene.render.filepath="//preview_fog_default.png"
    bpy.ops.wm.save_as_mainfile(filepath=str(out/BLEND))
    frames=out/"frames"
    frames.mkdir()
    for i,frame in enumerate(range(0,120,3)):
        pose(scene,bundle,stage,frame)
        base["render"](scene,stage["cam"],frames,f"{i:04d}",FRAME,5)
    single["encode"](frames,out/"preview_fixed_rear_silent.mp4",VIDEO_FPS)
    single["write"](out/"measurements.json",{"geometry_and_timing":annotations,
        "visibility":visibility,"wetland_and_formation":proof,"source_graybox":upstream[-1]})


def geometry_signature(obj):
    obj.data.calc_loop_triangles()
    uv=obj.data.uv_layers.active.data
    result=[]
    for t in obj.data.loop_triangles:
        assert t.normal.z>.95,(obj.name,t.normal)
        corners=[tuple(round(a,4) for a in (*obj.data.vertices[obj.data.loops[i].vertex_index].co,*uv[i].uv))
                 for i in t.loops]
        result.append(tuple(sorted(corners)))
    return Counter(result)


def verify(lib,delivery,out,bundle):
    helper,upstream,inputs=bundle
    single,farm,env,fog,layout,discs,*_=upstream
    check=single["check"]
    base=env["B"]
    bpy.ops.wm.open_mainfile(filepath=str(delivery/BLEND))
    scene=bpy.context.scene
    root=bpy.data.objects[ROOT]
    edge,wave=(bpy.data.objects[n] for n in (EDGE,WAVE))
    check(scene.camera.name.startswith("Current Swift rig") and
          (scene.render.resolution_x,scene.render.resolution_y)==FRAME,"Saved camera")
    signatures={o.name:geometry_signature(o) for o in (edge,wave)}
    transforms={o.name:tuple(o.location) for o in (edge,wave)}
    source=physical_checks(scene,edge,wave,bundle)
    single["reset"]()
    scene=bpy.context.scene
    gltf,_=single["glb_parts"](delivery/GLB)
    check({n["name"] for n in gltf["nodes"]}=={ROOT,EDGE,WAVE},"GLB nodes")
    check(all(n.get("extras",{}).get("collision_enabled") is False for n in gltf["nodes"]),"Collision metadata")
    check(len(gltf["meshes"])==len(gltf["materials"])==2 and
          all(m["alphaMode"]=="BLEND" for m in gltf["materials"]),"GLB mesh materials")
    check(single["image_hashes_glb"](delivery/GLB)==
          {single["digest"](delivery/"textures"/p) for p in (EDGE_TEX,WAVE_TEX)},"GLB embedded PNG")
    clip_roles={EDGE_CLIP:(EDGE,3.),WAVE_CLIP:(WAVE,26/24)}
    check({a["name"] for a in gltf["animations"]}==set(clip_roles),
          [a["name"] for a in gltf["animations"]])
    for a in gltf["animations"]:
        target,seconds=clip_roles[a["name"]]
        channel,=a["channels"]
        times=gltf["accessors"][a["samplers"][channel["sampler"]]["input"]]
        check(channel["target"]["path"]=="weights" and
              gltf["nodes"][channel["target"]["node"]]["name"]==target and
              abs(times["max"][0]-seconds)<1e-6 and times["min"][0]==0,(target,times))
    bpy.ops.import_scene.gltf(filepath=str(delivery/GLB))
    edge,wave=(bpy.data.objects[n] for n in (EDGE,WAVE))
    for ob in (edge,wave):
        check(ob.parent.name==ROOT and ob.parent.location.length<1e-7,ob.name)
        check((Vector(transforms[ob.name])-ob.location).length<2e-6,ob.name)
        check(geometry_signature(ob)==signatures[ob.name],(ob.name,"triangle UV"))
    set_timeline(scene,inputs,imported_anim(edge,EDGE_CLIP),imported_anim(wave,WAVE_CLIP))
    returned=physical_checks(scene,edge,wave,bundle)
    geometry_delta=max(abs(a["max_planar_area_BU2"]-b["max_planar_area_BU2"])
                       for a,b in zip(source["independent_single_playbacks"],returned["independent_single_playbacks"]))
    check(geometry_delta<1e-5,geometry_delta)
    stage=context(scene,lib,bundle)
    measured=farm["layout_proof"](layout,discs,stage["bird"],stage["layers"],
                                  stage["resting"],upstream[-1],check)
    original=json.loads((lib/FX/"qa.json").read_text())["source"]["formation_and_marsh"]
    fields=("minimum_reserved_lane_width_BU","whole_track_min_gap_BU","conservative_landing_AABB_gap_BU")
    deltas={k:abs(original[k]-measured[k]) for k in fields}
    check(max(deltas.values())<1e-5,deltas)
    pose(scene,bundle,stage,PEAK_FRAME)
    base["render"](scene,stage["cam"],out,"roundtrip_fixed_rear",FRAME,14)
    pose(scene,bundle,stage,98)
    base["render"](scene,stage["cam"],out,"roundtrip_contact",FRAME,14)
    source_pixels=helper["image_rgb"](delivery/"preview_fog_default.png")
    frame_error=float(np.abs(source_pixels-helper["image_rgb"](out/"roundtrip_fixed_rear.png")).mean()*255)
    check(frame_error<5,frame_error)
    single["write"](out/"recheck.json",{
        "status":"pass","blender":bpy.app.version_string,"two_animation_tracks_and_embedded_PNGs":"pass",
        "triangles_uv_normals_and_transforms":"pass","source_checks":source,"glb_checks":returned,
        "max_source_GLTF_animated_area_delta_BU2":geometry_delta,"FX010_marsh_and_flock_distances_delta_BU":deltas,
        "same_shot_default_preview_mean_error_8bit":frame_error,
        "video_silent_full_decode":video_info(delivery/"preview_fixed_rear_silent.mp4")})


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output",type=Path)
    cli.add_argument("--library",type=Path,default=Path(__file__).resolve().parents[2])
    cli.add_argument("--placement",type=Path,default=Path(__file__).with_name(PLACE))
    cli.add_argument("--verify",type=Path)
    args=cli.parse_args(sys.argv[sys.argv.index("--")+1:])
    lib=args.library.resolve()
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Use a new dedicated output directory.")
    bundle=initialize(lib,args.placement.resolve())
    if args.verify:
        verify(lib,args.verify.resolve(),out,bundle)
    else:
        build(lib,out,bundle)
