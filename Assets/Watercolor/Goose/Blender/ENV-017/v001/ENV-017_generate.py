"""Construct and validate the S6 LandingBasin environment and twelve-goose review."""
import argparse
from hashlib import sha256
from itertools import combinations, product
import json
import math
from pathlib import Path
import runpy
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import numpy as np


HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
C = runpy.run_path(str(LIB / "ENV-014/v001/ENV-014_generate.py"))
B,F,W,R = (C[key] for key in ("B","F","W","R"))
STEM = "ENV-017_landing_basin"
ROOT = "LandingBasin"
GLB = "ENV-017_LandingBasin.glb"
NODES = ("LandingBasin_Ground", "LandingBasin_Water", "LandingBasin_Reeds")
WATER, STEP, FRAME = B["WATER"], B["STEP"], B["GAME_SIZE"]
check, obj, group, write, hash_file = (B[key] for key in ("check","obj","collection","write_json","file_hash"))
SOURCES = {
    "ENV-001": LIB / "ENV-001/v001/ENV-001_terrain.blend",
    "ENV-002": LIB / "ENV-002/v001/ENV-002_wetland.blend",
    "ENV-003": LIB / "ENV-003/v001/ENV-003_wetland_water.blend",
    "ENV-005": LIB / "ENV-005/v001/ENV-005_reed_distribution.blend",
    "ANM-007": LIB / "ANM-007/v001/ANM-007_landing.blend",
    "ANM-008": LIB / "ANM-008/v001/ANM-008_rest_idle.blend",
    "MAT-003": LIB / "MAT-003/v001/MAT-003_wetland_rock.blend",
    "MAT-004": LIB / "MAT-004/v001/MAT-004_water_surfaces.blend",
}
SLOTS = ((0,-2.61),(-2.16,-2.35),(2.16,-2.41),(-2.40,-.06),(-.33,-.09),(1.99,-.03),
         (-2.10,2.03),(.09,2.05),(2.35,2.09),(-2.43,4.12),(-.22,4.29),(1.97,4.20))
DELAYS = tuple(i * 5 for i in range(len(SLOTS)))
FINISH = 81 + DELAYS[-1]
REST_END = FINISH + 72
TARGET = (-3.35,3.35,-3.65,4.97)
CORRIDOR = (0,-7.4,3.50,12)
SEED = 17027
UI = C["transport"].__globals__
UI.update(ROOT=ROOT, GLB=GLB, NODES=NODES)


def unpack(key, names):
    return C["P"]["append"](SOURCES[key], names)


def basin_height(x, y):
    a=(x+.62*math.sin(y*.64))/9.20
    b=(y-1.85-.36*math.sin(x*.63))/7.15
    oval=(abs(a)**2.6+abs(b)**2.45)**(1/2.6)
    rim=B["smooth"]((1.05-oval)/.38)
    border=B["smooth"]((9.95-max(abs(x),abs(y)))/.94)
    # The main bowl curls around a dry, nearly level tongue. It opens towards +Y.
    dy=(y+5)-4.7-.35*math.sin(x*.77)
    dry=B["smooth"]((5.45-abs(x+.18*math.sin(y)))/1.66) * B["smooth"]((6.88-dy)/1.3)
    grain=.024*math.sin(x*.77+y*.54)*math.cos(y*.89)
    return -(0.60+grain)*rim*border*(1-dry)


def build_basin(parent, mats, gray_water):
    count=32
    coords=[i*STEP-10 for i in range(count+1)]
    points=[(x,y,basin_height(x,y)) for y in coords for x in coords]
    faces=[]
    for i,j in product(range(count),repeat=2):
        a=j*(count+1)+i
        b,c,d=a+1,a+count+2,a+count+1
        faces.extend(((a,b,c),(a,c,d)) if (i+j)%2 else ((a,b,d),(b,c,d)))
    slots=[]
    for face in faces:
        x,y,z=(sum(points[i][axis] for i in face)/3 for axis in range(3))
        bank=abs(x+.51*math.sin(y*.8))<3.84 and -8.2<y<.11+.36*math.sin(x)
        slots.append(2 if z<-.227 else 1 if z<-.028 or bank else 0)
    uv=[tuple((points[i][0]/10,(points[i][1]+5)/10) for i in f) for f in faces]
    land=C["make_tri"](parent,"Central bent landing basin",points,faces,mats,slots,uv,[True]*len(faces))
    land.location.y=5
    land.data.normals_split_custom_set_from_vertices([(0,0,1) if max(abs(p[0]),abs(p[1]))==10 else (0,0,0)
                                                      for p in points])
    water_group=group("Water source | level -0.18 BU",parent)
    proxy=land.copy()
    proxy.data=land.data.copy()
    for v in proxy.data.vertices:
        v.co.x*=.5
        v.co.y*=.5
    proxy.data.update()
    water=W["build_water"](water_group,"Main bowl | water",proxy,gray_water)
    for v in water.data.vertices:
        v.co.x*=2
        v.co.y*=2
    water.location.y=5
    water.data.update()
    return land,water,proxy


def compose(parent, mats, neutral):
    land=group("Terrain | fitted ENV-001 and ENV-002 connectors",parent)
    pools=group("ENV-003 pools | matching original contour",parent)
    assets=unpack("ENV-002",("Flat","RestPatch","StartMudflat"))
    wet_assets=unpack("ENV-003",("ShallowPool_RestPatch","ShallowPool_StartMudflat"))
    main,water,proxy=build_basin(land,mats,neutral["water"])
    tiles={}
    waters=[water]
    for x,y in product((-15,-5,5,15),(-15,-5,5,15)):
        if x in (-5,5) and y >= -5: continue
        if (x,y)==(-15,-5):
            name="StartMudflat"
        elif (x,y)==(15,5):
            name="RestPatch"
        else:
            name="Flat"
        tiles[x,y]=obj(land,f"{name} | {x},{y}",assets[name].data,(x,y,0))
        if name!="Flat":
            pool=wet_assets["ShallowPool_"+name]
            waters.append(obj(pools,pool.name+" placement",pool.data,(x,y,0)))
    # A half tile fills each 5 BU collar between the bowl and the module boundary.
    import bmesh
    for x,y in product((-5,5),(-10,20)):
        donor=assets["Flat"]
        is_south=y<0
        tile=C["bake"]([donor],land,f"Entry collar | {x},{y}",
                        retain=lambda item,p: min(item.data.vertices[i].co.y for i in p.vertices)>=0
                        if is_south else max(item.data.vertices[i].co.y for i in p.vertices)<=0)
        edit=bmesh.new()
        edit.from_mesh(tile.data)
        bmesh.ops.delete(edit,geom=[v for v in edit.verts if not v.link_faces],context="VERTS")
        edit.to_mesh(tile.data)
        edit.free()
        # A half-tile is translated 5 BU relative to its source repeat phase.
        uv=tile.data.uv_layers.active
        for corner in uv.data:
            corner.uv.y+=.5
        tile.location=(x,y,0)
        tiles[x,y]=tile
    return assets, [*tiles.values(),main], waters, proxy


def grid_joins(items):
    # Compare every positive-length shared edge even when it covers only part of a module.
    pairs=[]
    for a,b in combinations(items,2):
        ba=np.array(B["tile_box"](a.data))+np.array(a.location)[:,None]
        bb=np.array(B["tile_box"](b.data))+np.array(b.location)[:,None]
        for axis in (0,1):
            t=1-axis
            common_lo,common_hi=max(ba[t,0],bb[t,0]),min(ba[t,1],bb[t,1])
            if common_hi-common_lo<STEP:continue
            c=ba[axis,1]
            if abs(c-bb[axis,0])>1e-6:
                c=ba[axis,0]
                if abs(c-bb[axis,1])>1e-6:continue
            line=C["P"]["outline"]
            first={k:v for k,v in line(a.data,axis,c,a.location).items() if common_lo<=k<=common_hi}
            other={k:v for k,v in line(b.data,axis,c,b.location).items() if common_lo<=k<=common_hi}
            # Trimmed tile rephasing follows the same 10 BU repeat phase as its neighbors.
            check(first and len(first)==round((common_hi-common_lo)/STEP)+1,(a.name,b.name,axis))
            pairs.append(C["P"]["compare_edges"](first,other,f"{a.name} -> {b.name}"))
    check(len(pairs)>=12,len(pairs))
    return pairs


def reeds(parent, terrains):
    sub=group("Low wind reed beds | editable ENV-005 scatter",parent)
    props=unpack("ENV-005", R["PLANTS"]["REEDS"].keys())
    for source in props.values():
        sub.objects.link(source)
        source.hide_set(True)
        source.hide_render=True
    points, faces, contour=[],[],[]
    for tile in terrains:
        if max(abs(tile.location.x),abs(tile.location.y))>16:continue
        mesh=tile.data
        offset=len(points)
        points.extend(v.co+tile.location for v in mesh.vertices)
        faces.extend(tuple(offset+i for i in f.vertices) for f in mesh.polygons)
        contour.extend(R["contour"](mesh,tile.location))
    bed=bpy.data.meshes.new("Landing basin shore-paint weight")
    bed.from_pydata(points,[],faces)
    bed.update()
    mask=bed.attributes.new(R["ATTR_DENSITY"],"FLOAT","POINT")
    d_max=[]
    for v in points:
        d=R["distance_to_segments"](v.xy,contour)
        d_max.append(math.exp(-((d-.48)/1.18)**2) * (.72+.24*math.sin(v.x*.58-v.y*.66)))
    mask.data.foreach_set("value",d_max)
    live=obj(sub,"Landing basin | Live reed field",bed)
    protected=(CORRIDOR,(0,.50,3.57,4.55),(0,5.42,4.0,1.0))
    graph_builder=R["make_graph"]
    graph_builder.__globals__["KEEP_OUT"]=protected
    graph=graph_builder(props)
    graph.name="Landing basin | ENV-005 low wind adapt"
    mod=R["modify"](live,graph,"ShoreEdge")
    for key,value in (("Seed",SEED),("Density per BU²",1.81),("Interior fraction",.027),("Wind angle radians",.025)):
        R["set_input"](mod,key,value)
    pts=R["extract"](live)
    check(pts==R["extract"](live) and len(pts)>80,len(pts))
    mesh=R["freeze"](live)
    mesh.name="Landing basin | Frozen field"
    expected=sum(len(list(props.values())[p[3]].data.polygons) for p in pts)
    mesh.calc_loop_triangles()
    gap=min(max(abs(v.co.x-x)-a,abs(v.co.y-y)-b) for v in mesh.vertices for x,y,a,b in protected)
    check(len(mesh.loop_triangles)==expected and gap>.10,(gap,expected))
    live.hide_set(True)
    live.hide_render=True
    return mesh,{"seed":SEED,"reed_count":len(pts),"leaf_triangles":expected,"min_exclusion_gap_BU":gap,
                 "shoreline_seed_reproduced":True,"wind_angle_rad":.025,"restricted_regions_xy_hwidth_BU":protected}


def textured_water(pool, proxy, output):
    # Reuse ENV-003's depth bake. Only the basin is remapped to its own RGBA atlas.
    (output/"textures").mkdir()
    maps=W["source_materials"]()
    record=W["shade"]("ShallowPool_StartMudflat",pool,proxy,maps,output)
    old=output/record["path"]
    new=old.with_name("ft_goose_env_water_landing_basin_basecolor_alpha.png")
    old.rename(new)
    material=pool.data.materials[0]
    material.name="LandingBasinWater"
    for node in material.node_tree.nodes:
        if node.type=="TEX_IMAGE" and node.image and node.image.name.endswith("start_mudflat_basecolor_alpha.png"):
            node.image.filepath="//textures/"+new.name
            node.image.name=new.name
    return {"path":new.relative_to(output).as_posix(),"MAT-004_png":record["mat004_source"]}


def water_proof(ground, waters):
    return C["verify_water"](waters,ground)


def supported_paths(ground, planted, span, belly):
    floor=C["ray_tree"]([ground])
    brush=C["ray_tree"]([planted])
    margins=[]
    for path in (-2.3,0,2.3):
        for i in range(101):
            y=-16+i*.20
            for x in (path-span/2,path,path+span/2):
                z=C["ground_at"](floor,x,y)
                margins.append(belly-z)
                hit,*_=brush.ray_cast(Vector((x,y,-.19)),Vector((0,0,1)),2.3)
                check(hit is None,("approach crossed a reed",x,y))
    check(min(margins)>.10,min(margins))
    return {"flight_clearance_rays":len(margins),"lanes":3,"min_lower_bound_clearance_BU":float(min(margins)),
            "span_BU":span,"neutral_belly_Z_BU":belly}


def get_bird_action(parent):
    with bpy.data.libraries.load(str(SOURCES["ANM-007"]),link=False) as (src,dst):
        names=["Goose_LOD0","GooseRig"]
        check(set(names)<=set(src.objects),src.objects)
        dst.objects=names
        dst.actions=["Land_Mudflat"]
    bird,rig=dst.objects
    action=dst.actions[0]
    for item in (bird,rig):parent.objects.link(item)
    rig.animation_data_clear()
    rig.animation_data_create().action=action
    rig.animation_data.action_slot=action.slots[0]
    return bird,rig,action


def pose_vertices(mesh):
    dep=bpy.context.evaluated_depsgraph_get()
    vertices=mesh.evaluated_get(dep).data.vertices
    data=np.empty(len(vertices)*3,dtype=np.float32)
    vertices.foreach_get("co",data)
    return data.reshape(-1,3)


def carriers(scene, parent):
    bird,rig,action=get_bird_action(parent)
    with bpy.data.libraries.load(str(SOURCES["ANM-008"]),link=False) as (src,dst):
        check("Rest_Idle" in src.actions,"Rest_Idle")
        dst.actions=["Rest_Idle"]
    rest=dst.actions[0]
    vertices=bird.data.vertices
    feet=[]
    for side in ("Foot.L","Foot.R"):
        weight=bird.vertex_groups[side].index
        feet.append([v.index for v in vertices if any(x.group==weight and x.weight>.99 for x in v.groups)])
    all_feet=np.array(feet[0]+feet[1])
    frames={}
    for f in range(1,82):
        scene.frame_set(f)
        frames[f]=pose_vertices(bird)
    at_land=frames[47]
    heel=all_feet[int(np.argmin(at_land[all_feet,2]))]
    end_y=float(frames[81][heel,1])
    start_sole=float(frames[1][all_feet,2].min())
    motion={}
    for f,pose in frames.items():
        t=min(1.,(f-1)/46)
        sole=float(pose[all_feet,2].min())
        if f<47:
            z=-sole+(.288+start_sole)*(1-t)**2
            y=-1.36*(1-t)**2+end_y-float(at_land[heel,1])
        else:
            y=end_y-float(pose[heel,1])
            z=-sole
        motion[f]=(0,y,z)
    actor_list=[]
    for i,((x,y),delay) in enumerate(zip(SLOTS,DELAYS,strict=True)):
        root=obj(parent,f"Landing carrier {i+1:02}",None)
        body=rig.copy()
        body.name=f"Landing rig {i+1:02}"
        parent.objects.link(body)
        body.parent=root
        body.animation_data_clear()
        track=body.animation_data_create().nla_tracks.new()
        strip=track.strips.new(action.name,1+delay,action)
        strip.action_slot=action.slots[0]
        strip.extrapolation="HOLD"
        settle_time=FINISH+1+i*2
        # A second strip on the same track prevents additive pose changes.
        resting=track.strips.new(rest.name,settle_time,rest)
        resting.action_slot=rest.slots[0]
        resting.extrapolation="HOLD_FORWARD"
        member=bird.copy()
        member.name=f"Landing goose {i+1:02}"
        parent.objects.link(member)
        member.parent=body
        member.modifiers["GooseSkin"].object=body
        for f,p in motion.items():
            root.location=Vector((x,y,0))+Vector(p)
            root.keyframe_insert("location",frame=f+delay)
        actor_list.append((root,member))
    bpy.data.objects.remove(bird,do_unlink=True)
    bpy.data.objects.remove(rig,do_unlink=True)
    scene.render.fps=48
    scene.frame_start=1
    scene.frame_end=REST_END
    for f,title in ((1,"First flare"),(47,"Leader contact"),(47+DELAYS[-1],"Twelfth contact"),(FINISH,"All landed"),(FINISH+1,"Rest_Idle onset")):
        scene.timeline_markers.new(title,frame=f)
    bird=actor_list[0][1]
    bird.data.calc_loop_triangles()
    return actor_list,feet,[tuple(t.vertices) for t in bird.data.loop_triangles]


def flight_camera(camera, carrier):
    x,y,z=carrier.location
    B["follow"](camera,(x,y),Vector((0,1)))
    # ThirdPersonRig adds the same vertical displacement to eye and target.
    camera.location.z+=z-.288


def raster_silhouette(coords,tris):
    """Return the two-dimensional pixel coverage for one evaluated bird mesh."""
    width,height=FRAME
    position=np.asarray([(v.x*width,v.y*height) for v in coords])
    mask=np.zeros((height,width),dtype=bool)
    for i,j,k in tris:
        a,b,c=position[[i,j,k]]
        x0,y0=np.maximum(0,np.floor(np.minimum(np.minimum(a,b),c)).astype(int))
        x1,y1=np.minimum((width,height),1+np.floor(np.maximum(np.maximum(a,b),c)).astype(int))
        if x0>=x1 or y0>=y1:
            continue
        yy,xx=np.ogrid[y0+.5:y1+.5,x0+.5:x1+.5]
        edges=[(q[0]-p[0])*(yy-p[1])-(q[1]-p[1])*(xx-p[0]) for p,q in ((a,b),(b,c),(c,a))]
        mask[y0:y1,x0:x1]|=((edges[0]>=0)&(edges[1]>=0)&(edges[2]>=0))|((edges[0]<=0)&(edges[1]<=0)&(edges[2]<=0))
    return mask


def dynamics(scene,camera,actors,ground,planted,feet,tris):
    bush=C["ray_tree"]([planted])
    earth=C["ray_tree"]([ground])
    most_gap=0.
    terrain_clear=math.inf
    leader_wait_range=[]
    min_pair=math.inf
    narrow_phase_checks=0
    inside=0
    for frame in range(1,REST_END+1):
        scene.frame_set(frame)
        go=[]
        boxes=[]
        for index,(root,bird) in enumerate(actors):
            points=pose_vertices(bird)+np.array(root.location,dtype=np.float32)
            go.append(points)
            boxes.append((points.min(axis=0),points.max(axis=0)))
            if frame>=47+DELAYS[index]:
                for side in feet:
                    low=min(points[i,2]-C["ground_at"](earth,*points[i,:2]) for i in side)
                    most_gap=max(most_gap,low)
            local=[points[int(np.argmin(points[:,2]))],points[int(np.argmin(points[:,0]))],
                   points[int(np.argmax(points[:,0]))]]
            for x,y,z in local:
                floor=C["ground_at"](earth,x,y)
                terrain_clear=min(terrain_clear,z-floor)
                hit,*_=bush.ray_cast(Vector((x,y,-.20)),Vector((0,0,1)),2.3)
                check(hit is None,("landing reed clearance",frame,index))
        if frame>=81:leader_wait_range.append(tuple(actors[0][0].location))
        for i,j in combinations(range(len(go)),2):
            a,b=boxes[i],boxes[j]
            overlap=not (np.any(a[1]<b[0]) or np.any(b[1]<a[0]))
            if overlap:
                narrow_phase_checks+=1
                first=BVHTree.FromPolygons(go[i].tolist(),tris,all_triangles=True)
                second=BVHTree.FromPolygons(go[j].tolist(),tris,all_triangles=True)
                check(not first.overlap(second),("landing overlap",frame,i,j))
            offsets=np.maximum(a[0]-b[1],b[0]-a[1])
            min_pair=min(min_pair,float(np.max(offsets)))
        if frame==FINISH:
            inside=int(sum(TARGET[0]<=a[0][0] and a[1][0]<=TARGET[1] and
                       TARGET[2]<=a[0][1] and a[1][1]<=TARGET[3] for a in boxes))
    check(inside==12 and terrain_clear>=-.003 and most_gap<=.009,
          (inside,terrain_clear,most_gap,min_pair))
    linger=max((Vector(p)-Vector(leader_wait_range[0])).length for p in leader_wait_range)
    check(linger<1e-6,linger)
    scene.frame_set(FINISH)
    flight_camera(camera,actors[0][0])
    bpy.context.view_layer.update()
    margins=[]
    widths=[]
    masks=[]
    for root,bird in actors:
        coords=[world_to_camera_view(scene,camera,Vector(p)) for p in
                (pose_vertices(bird)+np.array(root.location,dtype=np.float32))]
        xs,ys=[v.x for v in coords],[v.y for v in coords]
        check(all(v.z>0 for v in coords),bird.name)
        margins.append(min(min(xs)*FRAME[0],(1-max(xs))*FRAME[0],min(ys)*FRAME[1],(1-max(ys))*FRAME[1]))
        widths.append((max(xs)-min(xs))*FRAME[0])
        masks.append(raster_silhouette(coords,tris))
    occupied=np.sum(masks,axis=0)>1
    obscured=[np.count_nonzero(mask & occupied)/np.count_nonzero(mask) for mask in masks]
    check(max(obscured)<.12,("final small-screen silhouette overlap",obscured))
    check(min(margins)>0 and min(widths)>14,(margins,widths))
    return {"landing_frames_checked":FINISH,"rest_frames_checked":REST_END-FINISH,"pair_tests":66*REST_END,"reed_hits":0,"contact_delay_frames":list(DELAYS),
            "geese_inside_envelope":inside,"tightest_AABB_axis_gap_BU":min_pair,"mesh_overlap_tests":narrow_phase_checks,
            "min_mesh_probe_clearance_BU":float(terrain_clear),"max_landed_foot_gap_BU":float(most_gap),
            "leader_stationary_BU":linger,"leader_wait_seconds":(FINISH-81)/48,
            "max_final_screen_overlap_fraction_upper_bound":max(obscured),
            "min_final_screen_silhouette_px":min(int(np.count_nonzero(mask)) for mask in masks),"min_final_screen_margin_px":min(margins),
            "min_final_goose_width_px":min(widths)}


def setup_camera(scene, flat, backdrop=True):
    apron=group("Review | horizon ground",scene.collection)
    if backdrop:
        for x,y in product(range(-85,86,10),range(-35,136,10)):
            if -15<=x<=15 and -15<=y<=15:continue
            obj(apron,f"Flat {x},{y}",flat.data,(x,y,0))
    keys=B["studio"](scene,scene.collection)
    sun=next(x for x in keys.objects if x.type=="LIGHT")
    sun.data.color=(1,.82,.57)
    sun.data.energy=1.68
    sun.data.angle=.29
    sun.rotation_euler=Vector((.89,.37,-.62)).to_track_quat("-Z","Y").to_euler()
    sky=scene.world.node_tree.nodes.get("Background")
    sky.inputs["Color"].default_value=(.70,.74,.77,1)
    sky.inputs["Strength"].default_value=.64
    camera=B["camera"](keys,"Finale | ThirdPersonRig fixed rear",(0,-5,3),(0,0,0))
    overhead=B["camera"](keys,"Finale | orthographic overview",(0,0,72),(0,0,0),46)
    scene.render.resolution_x,scene.render.resolution_y=FRAME
    return camera,overhead


def review_ripples(water):
    """Make low-amplitude animated ripple normals for the Blender review scene."""
    water.data=water.data.copy()
    for i,original in enumerate(water.data.materials):
        material=original.copy()
        material.name=original.name+" | Review ripples"
        water.data.materials[i]=material
        graph=material.node_tree
        shader=next(n for n in graph.nodes if n.type=="BSDF_PRINCIPLED")
        wave=graph.nodes.new("ShaderNodeTexWave")
        wave.label="Weak surface movement"
        wave.wave_type="BANDS"
        wave.bands_direction="DIAGONAL"
        wave.inputs["Scale"].default_value=2.9
        wave.inputs["Distortion"].default_value=.52
        wave.inputs["Detail Scale"].default_value=.7
        wave.inputs["Phase Offset"].driver_add("default_value").driver.expression="frame*.024"
        coords=graph.nodes.new("ShaderNodeTexCoord")
        bump=graph.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value=.14
        bump.inputs["Distance"].default_value=.019
        graph.links.new(coords.outputs["Object"],wave.inputs["Vector"])
        graph.links.new(wave.outputs["Fac"],bump.inputs["Height"])
        graph.links.new(bump.outputs["Normal"],shader.inputs["Normal"])


def color_preview(scene, flat, layers, output, report=True):
    camera,top=setup_camera(scene,flat)
    flock=group("Review only | Animated twelve-goose landing",scene.collection)
    actors,feet,tris=carriers(scene,flock)
    result=dynamics(scene,camera,actors,layers[NODES[0]],layers[NODES[2]],feet,tris) if report else None
    scene.frame_set(FINISH)
    flight_camera(camera,actors[0][0])
    B["render"](scene,camera,output,"preview_fixed_rear_final" if report else "roundtrip_fixed_rear_final",FRAME,23)
    if report:
        B["render"](scene,top,output,"preview_top_final",(1000,1000),18)
        scene.frame_set(82)
        flight_camera(camera,actors[0][0])
        B["render"](scene,camera,output,"preview_leader_wait",FRAME,21)
        early=group("Review only | Approach",scene.collection)
        neutral=B["add_goose"](early)
        B["pose_at"](camera,neutral,(0,-11.2),Vector((0,1)))
        flock.hide_render=True
        B["render"](scene,camera,output,"preview_fixed_rear_approach",FRAME,24)
        neutral.hide_render=True
        neutral.hide_set(True)
        flock.hide_render=False
        scene.frame_set(FINISH)
        flight_camera(camera,actors[0][0])
    B["set_preview_workspace"](scene,camera)
    scene.render.filepath="//landing_basin.png"
    return result


def scale_inputs(scene):
    evidence=group("Graybox wingspan reference",scene.collection)
    bird=B["add_goose"](evidence)
    span=max(v.co.x for v in bird.data.vertices)-min(v.co.x for v in bird.data.vertices)
    z=.288+min(v.co.z for v in bird.data.vertices)
    bpy.data.objects.remove(bird,do_unlink=True)
    return span,z


def names_and_materials(terrain,waters,plants):
    C["restore_mat_names"]([*terrain,*waters,plants])


def copy_to_review(scene, layers):
    holder=group("Ground, water and reeds at shared origin",scene.collection)
    return {name:obj(holder,name+" | review",item.data) for name,item in layers.items()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    p.add_argument("--verify",type=Path)
    p.add_argument("--fast",action="store_true")
    args=p.parse_args(sys.argv[sys.argv.index("--")+1:])
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    check(not any(output.iterdir()),"Output must be empty.")
    if args.verify:
        d=args.verify.resolve()
        bpy.ops.wm.open_mainfile(filepath=str(d/(STEM+".blend")))
        layers={n:bpy.data.objects[n] for n in NODES}
        source=json.loads((d/"asset_manifest.json").read_text())
        expected=json.loads((d/"qa.json").read_text())["roundtrip"]
        B["fresh_scene"]("Independent delivered GLB check")
        incoming, result=C["transport"](d,layers,source["texture_layers"])
        result["water"]=water_proof([incoming[NODES[0]]],[incoming[NODES[1]]])
        inputs=expected["approach"]
        result["approach"]=supported_paths(incoming[NODES[0]],incoming[NODES[2]],inputs["span_BU"],inputs["neutral_belly_Z_BU"])
        check(result==expected,(result.keys(),expected.keys()))
        write(output/"recheck.json",{"result":"pass","roundtrip":result})
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    layout=bpy.context.scene
    layout.name="ENV-017 | Editable layout and live reeds"
    production=group("Original wetland modules and custom bowl",layout.collection)
    neutral={k:B["paint"]("Graybox "+k,h) for k,h in (("water","879EA4"),("ground","9FA29A"),("reeds","6D827A"))}
    mats,_=B["load_materials"]()
    assets,terrain,waters,proxy=compose(production,[mats[n] for n in ("GrassFlat","MudBank","ShallowMargin")],neutral)
    joins=grid_joins(terrain)
    water=water_proof(terrain,waters)
    plant_mesh,plant_proof=reeds(production,terrain)
    gray=B["fresh_scene"]("ENV-017 | Graybox evidence")
    evidence=group("Graybox three layers",gray.collection)
    ground=C["bake"](terrain,evidence,NODES[0]+" gray")
    water_mesh=C["bake"](waters,evidence,NODES[1]+" gray")
    gray_plant=obj(evidence,NODES[2]+" gray",plant_mesh.copy())
    for item,key in ((ground,"ground"),(water_mesh,"water"),(gray_plant,"reeds")):
        for i in range(len(item.data.materials)):item.data.materials[i]=neutral[key]
    box_flat=obj(evidence,"Graybox floor extension donor",assets["Flat"].data.copy())
    for i in range(len(box_flat.data.materials)):box_flat.data.materials[i]=neutral["ground"]
    box_flat.hide_render=True
    cam,top=setup_camera(gray,box_flat)
    span,belly=scale_inputs(gray)
    approach=supported_paths(ground,gray_plant,span,belly)
    all_birds=group("Graybox | landing animation",gray.collection)
    actors,feet,tris=carriers(gray,all_birds)
    validation=dynamics(gray,cam,actors,ground,gray_plant,feet,tris)
    gray.frame_set(FINISH)
    if not args.fast:
        flight_camera(cam,actors[0][0])
        B["render"](gray,cam,output,"graybox_fixed_rear_final",FRAME,13)
        B["render"](gray,top,output,"graybox_top_final",(900,900),12)

    bpy.context.window.scene=layout
    atlas=textured_water(waters[0],proxy,output)
    plants=obj(production,"Frozen reed geometry | review and export",plant_mesh)
    names_and_materials(terrain,waters,plants)
    export_scene=B["fresh_scene"]("ENV-017 | LandingBasin export layers")
    node_group=group("Three baked layers",export_scene.collection)
    root=obj(node_group,ROOT,None)
    root["role"]="S6 visual geometry, separately created game interactions"
    root["root_forward_positive_y"]=True
    layers={NODES[0]:C["bake"](terrain,node_group,NODES[0]),
            NODES[1]:C["bake"](waters,node_group,NODES[1]), NODES[2]:obj(node_group,NODES[2],plant_mesh)}
    for item in layers.values():item.parent=root
    texture_layers=C["textures_in"](layers)
    check(bpy.ops.export_scene.gltf(filepath=str(output/GLB),export_format="GLB",use_active_scene=True,
                                    export_yup=True,export_animations=False,export_skins=False,
                                    export_extras=True)=={"FINISHED"},GLB)

    if not args.fast:
        review=B["fresh_scene"]("ENV-017 | S6 landing and leader hold")
        review_layers=copy_to_review(review,layers)
        review_ripples(review_layers[NODES[1]])
        actual=color_preview(review,assets["Flat"],review_layers,output)
        check(actual==validation,"Pose or camera measurements changed")
    bpy.ops.wm.save_as_mainfile(filepath=str(output/(STEM+".blend")))
    final=B["fresh_scene"]("ENV-017 | Roundtrip landed")
    returned, result=C["transport"](output,layers,texture_layers)
    result["water"]=water_proof([returned[NODES[0]]],[returned[NODES[1]]])
    result["approach"]=supported_paths(returned[NODES[0]],returned[NODES[2]],span,belly)
    check(approach==result["approach"],"Flight lanes changed on export")
    if not args.fast:color_preview(final,assets["Flat"],returned,output,report=False)
    write(output/"qa.json",{"id":"ENV-017","version":"v001","status":"needs_review","graybox_tile_joins":joins,
         "graybox_water_cover":water,"reed_scatter":plant_proof,"flight_paths":approach,
         "landing_48fps_source":validation,"reference_target_bounds_xy_BU":TARGET,"roundtrip":result,
         "pending":["Actual S6 all-bird arrival gate, retry and runtime landing/rest handoff.",
                    "Shallow ripple FX and actual protected-state timing.",
                    "RealityKit transparency, USDZ/runtime integration and iPhone/iPad."]})
    generated=texture_layers.pop("LandingBasinWater")
    named=C["named_source_map"](texture_layers)
    named["LandingBasinWater"]=dict(generated, generated_path=atlas["path"],filename=Path(atlas["path"]).name)
    write(output/"asset_manifest.json",{"id":"ENV-017","version":"v001","status":"needs_review",
         "depends":["ENV-002/v001","ENV-003/v001","ENV-005/v001","ANM-007/v001"],
         "blender_file":STEM+".blend","glb_file":GLB,"asset_root":ROOT,"layers":list(NODES),
         "axis_glb_from_blender_xyz":["x","z","-y"],"preview_camera_swift":"ThirdPersonRig.graybox",
         "local_origin_BU":[0,0,0],"shore_water_height_BU":WATER,"assembly_bounds_xy_BU":[[-20,20],[-20,20]],
         "basin_atlas":atlas,"texture_layers":named,"source_blend_SHA256":{k:hash_file(path) for k,path in SOURCES.items()},
         "rights":"Original project geometry and project-owned wetland sources.",
         "engine_finish_gate":"Separate runtime work. Animated flock on review scene only."})


if __name__=="__main__":
    main()
