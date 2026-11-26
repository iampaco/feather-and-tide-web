"""Generate and recheck RotorFootprint with Blender 5.2 and ffmpeg."""
import argparse
import hashlib
from collections import Counter
import json
import math
from pathlib import Path
import runpy
import struct
import sys
import zlib

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import tessellate_polygon

ASSET = "RotorFootprint"
COLLECTION = "FX-010 | RotorFootprint"
BLEND = "FX-010_RotorFootprint.blend"
GLB = "FX-010_RotorFootprint.glb"
FARM = "STR-002/v001"
PAPER = "MAT-001/v001/textures/ft_goose_mat_soft_stone_basecolor.png"
SURFACE = "ft_goose_fx_rotor_footprint_basecolor_alpha.png"
FLOW = "ft_goose_fx_rotor_pressure_flow_basecolor_alpha.png"
SURFACE_Z = .021
FLOW_Z = .034
EXPOSURE_Y = -23.0
EXPOSURE_YAW = .28
FRAME = (852,393)
CLIP = "RotorPressureLoop"


def initialize(library):
    single = runpy.run_path(str(library/"STR-001/v001/STR-001_generate.py"))
    farm = runpy.run_path(str(library/FARM/"STR-002_generate.py"))
    wetland = runpy.run_path(str(library/"ENV-016/v001/ENV-016_generate.py"))
    fog = runpy.run_path(str(library/"ENV-018/v001/ENV-018_generate.py"))
    layout = json.loads((library/FARM/"farm_layout.json").read_text())
    swift = wetland["runtime_inputs"]()
    discs = farm["circles"](layout)
    single["check"](abs(swift["radius_BU"]-discs[0][2])<1e-7, "Sweep baseline changed")
    arcs = farm["exposed_arcs"](discs)
    points, joins = farm["polygon_from_arcs"](
        arcs,math.radians(layout["sweep"]["render_subdivision_max_angle_degrees"]))
    return single, farm, wetland, fog, layout, discs, arcs, points, joins, swift


def png(path, pixels):
    """Write straight sRGB RGBA without importing a second image library."""
    def chunk(kind, data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data))
    h,w,_ = pixels.shape
    scanlines = b"".join(b"\0"+row.tobytes() for row in pixels[::-1])
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+
        chunk(b"IHDR",struct.pack(">2I5B",w,h,8,6,0,0,0))+
        chunk(b"sRGB",b"\0")+chunk(b"IDAT",zlib.compress(scanlines,7))+chunk(b"IEND",b""))


def image_pixels(image):
    a = np.empty(len(image.pixels),dtype=np.float32)
    image.pixels.foreach_get(a)
    return a.reshape(image.size[1],image.size[0],4)


def smoothstep(lo, hi, value):
    t=np.clip((value-lo)/(hi-lo),0,1)
    return t*t*(3-2*t)


def arc_distance(x, y, arcs):
    """Distance to the exposed boundary, including concave circle joins."""
    result = np.full(np.broadcast(x,y).shape,np.inf,dtype=np.float32)
    for c,r,start,end in arcs:
        xx,yy=x-c.x,y-c.y
        angle=np.arctan2(yy,xx)%math.tau
        on_arc=(angle>=start)&(angle<=end)
        da=np.hypot(xx-r*math.cos(start),yy-r*math.sin(start))
        db=np.hypot(xx-r*math.cos(end),yy-r*math.sin(end))
        result=np.minimum(result,np.where(on_arc,abs(np.hypot(xx,yy)-r),np.minimum(da,db)))
    return result


def bounds(points):
    return (min(p.x for p in points)-.08, max(p.x for p in points)+.08,
            min(p.y for p in points)-.08, max(p.y for p in points)+.08)


def make_textures(library, out, discs, arcs, box, edge_width):
    dest=out/"textures"
    dest.mkdir()
    x0,x1,y0,y1=box
    w,h=768,2048
    x = x0+(np.arange(w)[None,:]+.5)*(x1-x0)/w
    y = y0+(np.arange(h)[:,None]+.5)*(y1-y0)/h
    inside = np.logical_or.reduce([np.hypot(x-c.x,y-c.y)<=r for _,c,r in discs])
    d = arc_distance(x,y,arcs)
    ref = bpy.data.images.load(str(library/PAPER))
    paper = image_pixels(ref)[:,:,:3].mean(axis=2)
    bpy.data.images.remove(ref)
    ix=np.arange(w)[None,:]*2 % paper.shape[1]
    iy=np.arange(h)[:,None] % paper.shape[0]
    grain=paper[iy,ix]
    grain=(grain-grain.mean())/max(grain.std(),.01)
    furrows=(.6*np.sin(3.1*x-.52*y+.9*np.sin(.61*y))+
             .4*np.sin(5.7*x+.38*y+1.4*np.sin(.25*y)))
    outer=smoothstep(-.035,.035,np.where(inside,d,-d))
    edge=smoothstep(-.045,.015,np.where(inside,d,-d))*(1-smoothstep(.045,edge_width*1.85,d))
    rgba=np.empty((h,w,4),dtype=np.uint8)
    for i,(core,rim) in enumerate(zip((134,125,145),(78,71,94))):
        rgba[:,:,i]=np.clip(core+(rim-core)*edge+2.7*grain+2.5*furrows,0,255)
    # Color reaches the mathematical edge; geometry clips the texture to the approved union.
    rgba[:,:,3]=np.rint(255*np.clip(outer*(.25+.49*edge+.025*furrows+.009*grain),0,.8))
    png(dest/SURFACE,rgba)
    u=(np.arange(512)[None,:]+.5)/512
    v=(np.arange(128)[:,None]+.5)/128
    length=(smoothstep(0,.20,u)*(1-smoothstep(.76,1,u)))**1.8
    across=np.exp(-((v-.50)/.185)**2)*(1-smoothstep(.34,.49,abs(v-.50)))
    flow=np.empty((128,512,4),dtype=np.uint8)
    flow[:,:,:3]=(173,165,183)
    flow[:,:,3]=np.rint(255*.26*length*across)
    png(dest/FLOW,flow)
    return {"surface_dimensions":[w,h],"flow_dimensions":[512,128],
            "surface_alpha_max":int(rgba[:,:,3].max()),"flow_alpha_max":int(flow[:,:,3].max())}


def material(out, filename, name):
    image=bpy.data.images.load(str(out/"textures"/filename))
    image.pack()
    image.filepath="//textures/"+filename
    mat=bpy.data.materials.new(name)
    mat.use_nodes=True
    mat.diffuse_color=(.27,.23,.30,.55)
    mat.use_backface_culling=True
    nodes=mat.node_tree.nodes
    shader=nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value=1
    shader.inputs["Specular IOR Level"].default_value=0
    tex=nodes.new("ShaderNodeTexImage")
    tex.image=image
    tex.extension="EXTEND"
    tex.location=(-320,100)
    mat.node_tree.links.new(tex.outputs["Color"],shader.inputs["Base Color"])
    mat.node_tree.links.new(tex.outputs["Alpha"],shader.inputs["Alpha"])
    return mat


def mesh(single, group, root, name, points, faces, mat, uv, location=(0,0,0)):
    geo=bpy.data.meshes.new(name+" geometry")
    geo.from_pydata(points,[],faces)
    geo.update()
    uv_layer=geo.uv_layers.new(name="TextureUV")
    for i,loop in enumerate(geo.loops):
        uv_layer.data[i].uv=uv[loop.vertex_index]
    geo.materials.append(mat)
    result=single["object_in"](group,name,geo,root,location)
    result.visible_shadow=False
    return result


def patch_geometry():
    points, faces, uv = [], [], []
    for length,dx,dy,width in ((2.14,-.16,.43,.115),(1.55,.23,-.27,.10),(1.10,.41,-.74,.085)):
        start=len(points)
        for i in range(19):
            u=i/18
            x=dx+(u-.5)*length
            center=dy+.24*math.sin((u-.1)*math.pi)+.12*(u-.5)
            points.extend(((x,center-width,0),(x,center+width,0)))
            uv.extend(((u,0),(u,1)))
            if i:
                a=start+2*(i-1)
                faces.append((a,a+2,a+3,a+1))
    return points,faces,uv


def pressure_vector(yaw, phase):
    """Slow ground-parallel displacement, phase-locked to the matching rotor."""
    direction=Vector((math.cos(yaw),math.sin(yaw)))
    perpendicular=Vector((-direction.y,direction.x))
    return .24*math.sin(phase)*direction + .075*math.cos(phase)*perpendicular


def create_fx(scene, single, layout, points, box, out):
    group=single["collection_in"](scene,COLLECTION)
    root=single["object_in"](group,ASSET)
    root["geometry_source"]="STR-002/v001/farm_layout.json"
    root["collision_enabled"]=False
    root["ground_axis"]="Blender XY, Z up; glTF XZ, Y up"
    root["layout_variant"]=layout["variant"]
    root["cycle_seconds"]=single["PERIOD"]
    root["review_role"]="Sweep visual; runtime Zone controls collision and triggering"
    x0,x1,y0,y1=box
    verts=[Vector((p.x,p.y,SURFACE_Z)) for p in points]
    tris=tessellate_polygon([verts])
    if isinstance(tris[0][0],int):
        faces=[tuple(t) for t in tris]
    else:
        index={tuple(p):i for i,p in enumerate(verts)}
        faces=[tuple(index[tuple(p)] for p in t) for t in tris]
    surface_mat=material(out,SURFACE,"Rotor footprint | gray violet")
    area=mesh(single,group,root,"SweepSurface",verts,faces,surface_mat,
              [((p.x-x0)/(x1-x0),(p.y-y0)/(y1-y0)) for p in points])
    area["projection_offset_BU"]=SURFACE_Z
    flow_mat=material(out,FLOW,"Rotor pressure | feathered streaks")
    strip_points,strip_faces,strip_uv=patch_geometry()
    first=None
    for row in layout["instances"]:
        angle=math.radians(row["yaw_deg"])
        phase=math.radians(row["rotor_phase_deg"])
        center=Vector(row["center_BU"]).xy
        name="Pressure_"+row["id"]
        if first is None:
            first=mesh(single,group,root,name,strip_points,strip_faces,flow_mat,strip_uv)
            patch=first
        else:
            patch=single["object_in"](group,name,first.data,root)
            patch.visible_shadow=False
        patch.rotation_euler.z=angle
        patch["phase_source_degrees"]=row["rotor_phase_deg"]
        patch["cosmetic_only"]=True
        frame_count=round(single["PERIOD"]*single["FPS"])
        for step in range(25):
            offset=pressure_vector(angle,phase+math.tau*step/24)
            patch.location=(*(center+offset),FLOW_Z)
            patch.keyframe_insert(data_path="location",frame=step*frame_count/24)
        anim=patch.animation_data
        anim.action.name=name+"_Loop"
        for curve in anim.action.layers[0].strips[0].channelbag(anim.action_slot).fcurves:
            for key in curve.keyframe_points:
                key.interpolation="LINEAR"
            curve.modifiers.new("CYCLES")
    scene.frame_set(0)
    bpy.context.view_layer.update()
    return group,root,area


def surface_checks(area, points, arcs, discs, layout, single):
    """Certify disk-union topology and sample the mesh from both sides of the boundary."""
    check=single["check"]
    tolerance=layout["sweep"]["geometric_tolerance_BU"]
    vertices=[area.matrix_world @ v.co for v in area.data.vertices]
    # Importers may split indices; a positional weld keeps topology checks portable.
    ids={}
    faces=[]
    unique=[]
    for p in area.data.polygons:
        face=[]
        for i in p.vertices:
            v=vertices[i]
            token=tuple(round(x,5) for x in v)
            if token not in ids:
                ids[token]=len(unique)
                unique.append(v)
            face.append(ids[token])
        faces.append(tuple(face))
    check(len(unique)==len(points) and len(faces)==len(points)-2,
          (len(unique),len(points),len(faces)))
    edges=Counter(tuple(sorted((i,j))) for face in faces for i,j in zip(face,face[1:]+face[:1]))
    boundary_adjacency={}
    for (i,j),amount in edges.items():
        check(amount in (1,2),"Non-manifold sweep surface")
        if amount==1:
            boundary_adjacency.setdefault(i,set()).add(j)
            boundary_adjacency.setdefault(j,set()).add(i)
    check(len(boundary_adjacency)==len(points) and all(len(n)==2 for n in boundary_adjacency.values()),
          "Outer boundary does not form degree-two contour")
    visited=set()
    queue=[next(iter(boundary_adjacency))]
    while queue:
        here=queue.pop()
        if here not in visited:
            visited.add(here)
            queue.extend(boundary_adjacency[here]-visited)
    check(len(visited)==len(points),"Multiple boundary loops")
    bvh=BVHTree.FromPolygons(unique,faces,all_triangles=True)
    def hit(x,y):
        return bvh.ray_cast(Vector((x,y,1)),Vector((0,0,-1)),2)[0] is not None
    pos=np.asarray([(v.x,v.y) for v in unique])
    test=np.asarray([(v.x,v.y) for v in points])
    max_vertex_delta=max(float(np.min(np.hypot(pos[:,0]-px,pos[:,1]-py))) for px,py in test)
    check(max_vertex_delta<1e-5,max_vertex_delta)
    mid=np.asarray([((unique[i].x+unique[j].x)/2,(unique[i].y+unique[j].y)/2)
                    for (i,j),amount in edges.items() if amount==1])
    chord_error=float(np.max(arc_distance(mid[:,0],mid[:,1],arcs)))
    check(chord_error<tolerance,chord_error)
    def inside(x,y):
        return any(math.hypot(x-c.x,y-c.y)<=r for _,c,r in discs)
    rays=0
    for c,r,a,b in arcs:
        for angle in np.linspace(a,b,101)[1:-1]:
            for distance in (-tolerance,tolerance,-.04,.04):
                x=c.x+(r+distance)*math.cos(angle)
                y=c.y+(r+distance)*math.sin(angle)
                check(hit(x,y)==inside(x,y),(x,y,distance))
                rays+=1
    grid=0
    x0,x1,y0,y1=bounds(points)
    for y in np.linspace(y0,y1,307):
        xs=np.linspace(x0,x1,93)
        distances=arc_distance(xs,y,arcs)
        for x,d in zip(xs,distances):
            if d>tolerance:
                check(hit(x,y)==inside(x,y),(x,y))
                grid+=1
    bridges=[]
    for (a,c,r),(b,d,s) in zip(discs,discs[1:]):
        axial=r+s-(c-d).length
        check(axial>layout["sweep"]["minimum_nearest_overlap_BU"]+tolerance and
              hit(*((c+d)/2)),(a,b,axial))
        bridges.append({"pair":[a,b],"axial_overlap_BU":axial})
    return {"closed_boundary_count":1,"boundary_vertices":len(visited),"triangles":len(faces),
        "analytic_to_mesh_max_vertex_delta_BU":max_vertex_delta,"chord_midpoint_max_error_BU":chord_error,
        "comparison_tolerance_BU":tolerance,"paired_arc_BVH_probes":rays,
        "off_boundary_grid_BVH_probes":grid,"mismatched_probes":0,"bridges":bridges,
        "surface_xy_Bounds_BU":[float(min(v.x for v in unique)),float(max(v.x for v in unique)),
                                float(min(v.y for v in unique)),float(max(v.y for v in unique))]}


def motion_checks(scene, layout, discs, single):
    check=single["check"]
    rows={row["id"]:row for row in layout["instances"]}
    patches={tag:bpy.data.objects["Pressure_"+tag] for tag in rows}
    centers={tag:c for tag,c,_ in discs}
    radius=discs[0][2]
    frames=round(single["FPS"]*single["PERIOD"])
    max_dev=max_envelope=0
    initial={}
    for i in range(2*frames+1):
        f=i/2
        scene.frame_set(int(f),subframe=f%1)
        for tag,obj in patches.items():
            row=rows[tag]
            yaw=math.radians(row["yaw_deg"])
            phase=math.radians(row["rotor_phase_deg"])+math.tau*f/frames
            expected=pressure_vector(yaw,phase)
            delta=obj.location.xy-centers[tag]
            max_dev=max(max_dev,(delta-expected).length)
            if i==0:
                initial[tag]=obj.location.copy()
            if i%18==0:
                max_envelope=max(max_envelope,max(((obj.matrix_world@v.co).xy-centers[tag]).length
                                                 for v in obj.data.vertices))
    seam=max((p.location-initial[tag]).length for tag,p in patches.items())
    continuous_envelope=max(v.co.xy.length for v in next(iter(patches.values())).data.vertices)+.24
    check(max_dev<.003 and seam<1e-5 and continuous_envelope<radius-.50,
          (max_dev,seam,continuous_envelope,radius))
    scene.frame_set(0)
    return {"samples_per_pressure_patch":2*frames+1,"patch_count":len(patches),"period_seconds":single["PERIOD"],
            "shared_rotor_phases_degrees":{tag:r["rotor_phase_deg"] for tag,r in rows.items()},
            "max_key_interpolation_location_error_BU":max_dev,"loop_seam_max_delta_BU":seam,
            "sampled_max_radius_BU":max_envelope,"continuous_min_distance_to_own_disc_edge_BU":radius-continuous_envelope}


def build_context(scene, lib, bundle, imported=False):
    single,farm,env,fog,layout,discs,*_=bundle
    base=env["B"]
    if imported:
        bpy.ops.import_scene.gltf(filepath=str(lib/FARM/"STR-002_CurvedFarm_Layout.glb"))
        group=bpy.data.objects[farm["ROOT"]].users_collection[0]
        rotors={row["id"]:bpy.data.objects[row["id"]+"_Rotor"] for row in layout["instances"]}
    else:
        group,_,rotors=farm["build_array"](scene,single,lib/"STR-001/v001"/single["BLEND"],layout)
    stage=farm["composition"](scene,base,single,env,fog,lib,layout,discs,imported=imported)
    return group,rotors,stage


def set_pose(scene,bundle,stage,y,frame=42,amount=1.,yaw=EXPOSURE_YAW,lift=None):
    single,farm,env,fog,layout,*_=bundle
    scene.frame_set(frame)
    if lift is None:
        lift=layout["review_route"]["overflight_lift_game_units"]
    farm["flight_pose"](scene,stage,env["B"],layout,y,yaw=yaw,lift=lift)
    fog["accessibility"](stage["fog_rows"],amount)
    fog["position_cards"](stage["fog_rows"],frame/(single["FPS"]*
                          layout["review_atmosphere"]["drift_period_seconds"]),amount)


def export_fx(scene, group, output):
    label=scene.name
    scene.name=CLIP
    scene.frame_set(0)
    bpy.ops.object.select_all(action="DESELECT")
    for item in group.objects:
        item.select_set(True)
    status=bpy.ops.export_scene.gltf(filepath=str(output/GLB),use_selection=True,export_extras=True,
        export_yup=True,export_animation_mode="SCENE",export_anim_scene_split_object=False,
        export_frame_step=1,export_animations=True)
    scene.name=label
    if status!={"FINISHED"}:
        raise ValueError(status)


def set_flags(group, hide):
    group.hide_render=hide
    bpy.context.view_layer.update()


def image_rgb(path):
    im=bpy.data.images.load(str(path))
    data=image_pixels(im)[:,:,:3]
    bpy.data.images.remove(im)
    return data


def visibility_from_render(output, scene, stage, points, bridge_points, single):
    full=image_rgb(output/"preview_fog_default.png")
    baseline=image_rgb(output/"comparison_without_fx.png")
    delta=np.max(np.abs(full-baseline),axis=2)
    cam=stage["cam"]
    height,width=delta.shape
    edge_contrast=[]
    route_contrast=[]
    for p in points[::6]:
        view=world_to_camera_view(scene,cam,Vector((p.x,p.y,SURFACE_Z)))
        i,j=int(view.y*height),int(view.x*width)
        if i>2 and i<height-3 and j>2 and j<width-3 and view.z>0:
            edge_contrast.append(float(delta[i-2:i+3,j-2:j+3].max()))
    for x,y in bridge_points:
        q=world_to_camera_view(scene,cam,Vector((x,y,SURFACE_Z)))
        i,j=int(q.y*height),int(q.x*width)
        if i>2 and i<height-3 and j>2 and j<width-3 and q.z>0:
            route_contrast.append(float(delta[i-1:i+2,j-1:j+2].max()))
    single["check"](len(edge_contrast)>50 and np.median(edge_contrast)>8/255 and
                    len(route_contrast)>=4 and min(route_contrast)>3/255,
                    (len(edge_contrast),np.median(edge_contrast),route_contrast))
    fog_pixels={n:int((np.max(abs(image_rgb(output/f"preview_fog_{n}.png")-
                      image_rgb(output/"preview_fog_off.png")),axis=2)>=5/255).sum())
                for n in ("default","reduced")}
    single["check"](fog_pixels["default"]>fog_pixels["reduced"]>0,fog_pixels)
    return {"edge_projection_samples":len(edge_contrast),
        "edge_median_local_max_RGB_difference_8bit":float(np.median(edge_contrast))*255,
        "visible_bridge_centers":len(route_contrast),"minimum_bridge_RGB_difference_8bit":min(route_contrast)*255,
        "fog_pixels_delta_5_vs_off":fog_pixels}


def build(library,out,bundle):
    single,farm,env,fog,layout,discs,arcs,points,joins,swift=bundle
    base=env["B"]
    scene=single["reset"]()
    scene.name="FX-010 | RotorFootprint and S4 review"
    box=bounds(points)
    texture_stats=make_textures(library,out,discs,arcs,box,layout["sweep"]["outline_width_BU"])
    group,root,area=create_fx(scene,single,layout,points,box,out)
    geometry=surface_checks(area,points,arcs,discs,layout,single)
    motion=motion_checks(scene,layout,discs,single)
    farm_group,rotors,stage=build_context(scene,library,bundle)
    landing=farm["layout_proof"](layout,discs,stage["bird"],stage["layers"],
                                 stage["resting"],swift,single["check"])

    materials=farm["gray_layers"]([farm_group,*stage["pads"]],base)
    neutral=base["paint"]("Graybox | continuous footprint","7A737F")
    neutral.diffuse_color[3]=.50
    neutral.node_tree.nodes.get("Principled BSDF").inputs["Alpha"].default_value=.50
    original=area.data.materials[0]
    area.data.materials[0]=neutral
    set_pose(scene,bundle,stage,EXPOSURE_Y,amount=0)
    for item in root.children:
        item.hide_render=item!=area
    base["render"](scene,stage["cam"],out,"graybox_fixed_rear",FRAME,12)
    set_pose(scene,bundle,stage,11,amount=0,yaw=0,lift=0)
    base["render"](scene,stage["top"],out,"graybox_top",(960,1050),12)
    area.data.materials[0]=original
    for item in root.children:
        item.hide_render=False
    for item,old in materials:
        item.data=old
    export_fx(scene,group,out)

    measured=farm["visibility"](scene,stage,base,fog,layout,discs,rotors,points,single)
    for name,value in layout["review_atmosphere"]["levels"].items():
        set_pose(scene,bundle,stage,EXPOSURE_Y,amount=value)
        base["render"](scene,stage["cam"],out,f"preview_fog_{name}",FRAME,24)
    set_pose(scene,bundle,stage,EXPOSURE_Y)
    set_flags(group,True)
    base["render"](scene,stage["cam"],out,"comparison_without_fx",FRAME,24)
    set_flags(group,False)
    bridge_points=[(c+d)/2 for (_,c,_),(_,d,_) in zip(discs,discs[1:])]
    contrast=visibility_from_render(out,scene,stage,points,bridge_points,single)
    set_pose(scene,bundle,stage,11,amount=0,yaw=0,lift=0)
    base["render"](scene,stage["top"],out,"preview_top",(960,1050),20)
    detail=base["camera"](stage["studio"],"Technical closeup | six union joins",
        (19.3,9.4,48),(19.3,9.4,0),25)
    base["render"](scene,detail,out,"preview_boundary_detail",(780,1080),20)
    set_pose(scene,bundle,stage,EXPOSURE_Y)
    base["set_preview_workspace"](scene,stage["cam"])
    scene.render.resolution_x,scene.render.resolution_y=FRAME
    scene.render.filepath="//preview_fog_default.png"
    bpy.ops.wm.save_as_mainfile(filepath=str(out/BLEND))

    frames=out/"frames"
    frames.mkdir()
    # Keep +Y on the approved route. The strip and turbines share the same timeline.
    length=48
    begin,end=layout["review_route"]["fixed_rear_motion_extent_y_BU"]
    for i,y in enumerate(np.linspace(begin,end,length)):
        set_pose(scene,bundle,stage,float(y),frame=i*3,yaw=0)
        base["render"](scene,stage["cam"],frames,f"{i:04d}",FRAME,8)
    single["encode"](frames,out/"preview_fixed_rear.mp4",8)
    single["write"](out/"measurements.json",{"geometry":geometry,"arc_join_error_BU":joins,
        "pressure_motion":motion,"formation_and_marsh":landing,"fog_visibility":measured,
        "rendered_contrast":contrast,"texture_generation":texture_stats,
        "graybox_source":swift})


def object_signature(item,single):
    check=single["check"]
    check(item.data.uv_layers.active is not None,item.name)
    verts = item.data.vertices
    loops = item.data.loops
    uv = item.data.uv_layers.active.data
    material = item.data.materials[0]
    img = next(n.image for n in material.node_tree.nodes if n.type=="TEX_IMAGE")
    check(img.packed_file is not None,(item.name,img.name))
    mat_hash=hashlib.sha256(img.packed_file.data).hexdigest()
    faces=[]
    item.data.calc_loop_triangles()
    for tri in item.data.loop_triangles:
        check(tri.normal.z>.95,(item.name,tri.normal.z))
        corners=[tuple(round(x,4) for x in (*verts[loops[i].vertex_index].co,*uv[i].uv))
                 for i in tri.loops]
        faces.append(tuple(sorted(corners)))
    return {"texture_sha256":mat_hash,"triangles":Counter(faces),
            "location":tuple(item.location),"scale":tuple(item.scale),
            "rotation":tuple(item.matrix_basis.to_quaternion()),"parent":item.parent.name}


def use_imported_actions(root):
    anim=root.animation_data
    if not anim:
        return
    for track in anim.nla_tracks:
        if anim.action is None:
            strip=track.strips[0]
            anim.action=strip.action
            if strip.action_slot:
                anim.action_slot=strip.action_slot
        track.mute=True


def verify(library,delivery,out,bundle):
    single,farm,env,fog,layout,discs,arcs,points,_,swift=bundle
    check=single["check"]
    base=env["B"]
    bpy.ops.wm.open_mainfile(filepath=str(delivery/BLEND))
    scene=bpy.context.scene
    scene.frame_set(0)
    root=bpy.data.objects[ASSET]
    check(not root["collision_enabled"] and root.location.length<1e-7 and
          len(root.children)==1+len(discs),"Master root / role")
    check(scene.camera and scene.camera.name.startswith("Current Swift rig") and
          tuple((scene.render.resolution_x,scene.render.resolution_y))==FRAME,"Master camera")
    source={item.name:object_signature(item,single) for item in root.children}
    original_motion=motion_checks(scene,layout,discs,single)
    single["reset"]()
    scene=bpy.context.scene
    document,_=single["glb_parts"](delivery/GLB)
    names={n["name"] for n in document["nodes"]}
    check(names==set(source)|{ASSET} and len(document["meshes"])==2 and
          len(document["materials"])==2,"GLB tree or shared mesh count")
    check(all(m.get("alphaMode")=="BLEND" and not m.get("doubleSided", False)
              for m in document["materials"]),
          [m.get("alphaMode") for m in document["materials"]])
    check(single["image_hashes_glb"](delivery/GLB)==
          {single["digest"](delivery/"textures"/name) for name in (SURFACE,FLOW)},
          "GLB embedded texture hash differs")
    animation,=document["animations"]
    channels=animation["channels"]
    check(animation["name"]==CLIP and
          {document["nodes"][c["target"]["node"]]["name"] for c in channels}==set(source)-{"SweepSurface"} and
          len(channels)==len(discs) and {c["target"]["path"] for c in channels}=={"translation"},
          animation)
    for sampler in animation["samplers"]:
        times=document["accessors"][sampler["input"]]
        check(times["min"][0]==0 and abs(times["max"][0]-single["PERIOD"])<1e-6,times)
    bpy.ops.import_scene.gltf(filepath=str(delivery/GLB))
    root=bpy.data.objects[ASSET]
    for item in root.children:
        use_imported_actions(item)
    scene.frame_set(0)
    bpy.context.view_layer.update()
    check(not root["collision_enabled"] and root.location.length<1e-7 and root.parent is None,
          "GLB root / role")
    for item in root.children:
        before=source[item.name]
        after=object_signature(item,single)
        for key in ("texture_sha256","triangles","parent"):
            check(before[key]==after[key],(item.name,key))
        for key in ("location","scale","rotation"):
            check(max(abs(a-b) for a,b in zip(before[key],after[key]))<3e-6,(item.name,key))
    geometry=surface_checks(bpy.data.objects["SweepSurface"],points,arcs,discs,layout,single)
    imported_motion=motion_checks(scene,layout,discs,single)
    _,rotors,stage=build_context(scene,library,bundle,imported=True)
    for tag,rotor in rotors.items():
        use_imported_actions(rotor)
        phase=next(row["rotor_phase_deg"] for row in layout["instances"] if row["id"]==tag)
        single["check_animation"](scene,rotor,phase)
    landing=farm["layout_proof"](layout,discs,stage["bird"],stage["layers"],
                                 stage["resting"],swift,check)
    approved=json.loads((library/FARM/"qa.json").read_text())["source"]["layout"]
    comparisons={}
    for name in ("minimum_reserved_lane_width_BU","V_formation_width_BU","whole_track_min_gap_BU",
                 "conservative_landing_AABB_gap_BU"):
        comparisons[name]=abs(landing[name]-approved[name])
        check(comparisons[name]<layout["sweep"]["geometric_tolerance_BU"],(name,comparisons[name]))
    # Source and GLB share the same camera pose and context inputs for the A/B render.
    set_pose(scene,bundle,stage,EXPOSURE_Y)
    base["render"](scene,stage["cam"],out,"roundtrip_fixed_rear",FRAME,24)
    set_pose(scene,bundle,stage,11,amount=0,yaw=0,lift=0)
    base["render"](scene,stage["top"],out,"roundtrip_top",(960,1050),16)
    single["write"](out/"recheck.json",{"status":"pass","Blender":bpy.app.version_string,
        "root_transform_hierarchy_axis_and_mesh_UV_materials":"pass",
        "GLB_meshes":len(document["meshes"]),"embedded_RGBA_PNG_sha256":"match",
        "both_glTF_materials_alpha_mode":"BLEND","GLB_clip":animation["name"],
        "source_phase_motion":original_motion,"GLB_phase_motion":imported_motion,
        "GLB_geometry":geometry,"GLB_array_and_marsh":landing,
        "critical_distances_delta_BU_against_approved_STR002":comparisons})


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output",type=Path)
    cli.add_argument("--library",type=Path,default=Path(__file__).resolve().parents[2])
    cli.add_argument("--verify",type=Path)
    options=cli.parse_args(sys.argv[sys.argv.index("--")+1:])
    lib=options.library.resolve()
    result_dir=options.output.resolve()
    result_dir.mkdir(parents=True,exist_ok=True)
    if any(result_dir.iterdir()):
        raise ValueError("Use a separate empty output directory.")
    bundle=initialize(lib)
    if options.verify:
        verify(lib,options.verify.resolve(),result_dir,bundle)
        movie=bundle[0]["decoded"](options.verify.resolve()/"preview_fixed_rear.mp4",(852,394),48)
        report_path=result_dir/"recheck.json"
        report=json.loads(report_path.read_text())
        report["video_full_decode"]=movie
        bundle[0]["write"](report_path,report)
    else:
        build(lib,result_dir,bundle)
