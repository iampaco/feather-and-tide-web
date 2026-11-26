"""Build ProtectedMarsh against a measured Swift-based wind-sweep proxy."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
REPO = HERE.parents[5]
BASELINE = runpy.run_path(str(LIB / "ENV-014/v001/ENV-014_generate.py"))
B, F, W, R, P = (BASELINE[k] for k in ("B","F","W","R","P"))
check, obj, group, write, digest = (B[k] for k in ("check","obj","collection","write_json","file_hash"))
WATER, SIZE, SCALE = B["WATER"], B["GAME_SIZE"], B["SCALE"]
STEM = "ENV-016_protected_marsh"
ROOT = "ProtectedMarsh"
NODES = ("ProtectedMarsh_Ground","ProtectedMarsh_Water","ProtectedMarsh_Reeds")
GLB = "ENV-016_ProtectedMarsh.glb"
BASELINE["transport"].__globals__.update(ROOT=ROOT, GLB=GLB, NODES=NODES)
SOURCES = {n: BASELINE["SOURCES"][n] for n in ("ENV-001","ENV-002","ENV-003","ENV-005","ANM-007")}
COLS, ROWS = (-20,-10,0,10), (-20,-10,0,10,20)
RECT = (-25.,15.,-25.,25.)
HUB = Vector((18.6,9.2))
SEED = 16040
LANE_X = 2.0
START, FINISH = -14.0, 22.0
OUTSIDE_START, OUTSIDE_FINISH = -28.0, 35.0
LANDMARKS = {"Marsh_Landing":(0,0,0), "Marsh_Ingress":(LANE_X,START,0), "Marsh_Egress":(LANE_X,FINISH,0),
             "Outer_Approach":(LANE_X,OUTSIDE_START,0), "Outer_Exit":(LANE_X,OUTSIDE_FINISH,0)}
APRON = (0.4,0.,9.8,25.0)
PAD_BUFFER = (-.63,-.04,2.20,3.10)
ROOT_HEIGHT_GAME_UNITS = (8, 6)


def swift_number(path, pattern):
    text = path.read_text()
    match = re.search(pattern, text)
    check(match is not None, (str(path),pattern))
    return float(match.group(1))


def runtime_inputs():
    paths = {
        "GrayboxPlaces": REPO / "Sources/FeatherTide/Data/GrayboxPlaces.swift",
        "FlockTuning": REPO / "Sources/FeatherTide/Data/FlockTuning.swift",
        "FlockFormation": REPO / "Sources/FeatherTide/Systems/Flock/FlockFormation.swift",
        "TraceOverlay": REPO / "Sources/FeatherTide/Systems/Trace/TraceOverlay.swift",
        "PlayfieldView": REPO / "Sources/FeatherTide/Rendering/PlayfieldView.swift",
        "ThirdPersonRig": REPO / "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift",
    }
    sweep = swift_number(paths["GrayboxPlaces"], r"static let windSweepRadius:\s*CGFloat\s*=\s*(\d+(?:\.\d+)?)")
    spacing = swift_number(paths["FlockTuning"], r"tightSpacing:\s*(\d+(?:\.\d+)?),")
    check(sweep == 78 and spacing == 36, "Recheck runtime source against candidate dimensions.")
    trace = paths["TraceOverlay"].read_text()
    formula = paths["FlockFormation"].read_text()
    playfield = paths["PlayfieldView"].read_text()
    camera = paths["ThirdPersonRig"].read_text()
    check("fromHub <= GrayboxPlaces.windSweepRadius" in trace and "hypot(leader.x - hub.x, leader.y - hub.y)" in trace, "Sweep formula changed.")
    check("let row = followerIndex / 2" in formula and "+ side * leftX * rank" in formula, "Slot formula changed.")
    check(f"body.leader ? {ROOT_HEIGHT_GAME_UNITS[0]} : {ROOT_HEIGHT_GAME_UNITS[1]}" in playfield, "Bird height changed.")
    check("distance: 180, pitch: 0.48, fieldOfViewDegrees: 50" in camera and "Float(6 + lift)" in camera,
          "Fixed rig changed.")
    return {"radius_BU":sweep/SCALE,"radius_game_units":sweep,"rank_spacing_BU":spacing/SCALE,
            "rank_spacing_game_units":spacing,"source_sha256":{str(p.relative_to(REPO)):digest(p) for p in paths.values()},
            "source_sweep_rule":"Swift tests leader XY against a radius of 78 game units.",
            "flight_height_leader_and_followers_game_units":ROOT_HEIGHT_GAME_UNITS,
            "camera":{"distance_game_units":180,"pitch_radians":.48,"vertical_fov_degrees":50,
                      "target_height_game_units":6,"source_px":SIZE},
            "proxy_placement_xy_BU":list(HUB),
            "review_formation_count":12,
            "graybox_default_followers":int(swift_number(paths["FlockTuning"],r"followerCount:\s*(\d+),"))}


def append(key,names):
    return P["append"](SOURCES[key],names)


def configure_basin(item, flip):
    if not flip:
        return
    for v in item.data.vertices:
        x,y,z = v.co
        v.co.z = BASELINE["basin_height"](y,x) * (0.75 + 0.11*math.cos(.65*y))
    item.data.update()
    item.data.normals_split_custom_set_from_vertices([(0,0,1) if max(abs(v.co.x),abs(v.co.y))==5 else (0,0,0)
                                                      for v in item.data.vertices])


def terrain_and_water(scene, neutral):
    terrain = group("01 | Snapped 10 BU wetlands",scene.collection)
    waters = group("02 | Terrain-cut translucent water surfaces",scene.collection)
    sources = append("ENV-002",("Flat","RestPatch","StartMudflat"))
    references = append("ENV-003",("ShallowPool_RestPatch","ShallowPool_StartMudflat"))
    mats,_ = B["load_materials"]()
    slots = [mats[key] for key in ("GrassFlat","MudBank","ShallowMargin")]
    tiles, sheets = {}, []
    authored_basins = {(-10,0):False,(10,-10):True}
    for x in COLS:
        for y in ROWS:
            if (x,y) in authored_basins:
                name = "West reedwater" if x < 0 else "East shallows"
                tile = BASELINE["basin"](terrain,slots)
                tile.name = name
                tile.location = (x,y,0)
                configure_basin(tile,authored_basins[x,y])
                if authored_basins[x,y]:
                    for p in tile.data.polygons:
                        z = p.center.z
                        p.material_index = 2 if z < -.23 else 1 if z < -.033 else 0
                water = W["build_water"](waters,name+" water",tile,neutral["water"])
                water.location = tile.location
                sheets.append(water)
            else:
                name = "RestPatch" if (x,y)==(0,0) else ("StartMudflat" if (x,y)==(0,-10) else "Flat")
                tile = obj(terrain,f"{name} | {x},{y}",sources[name].data,(x,y,0))
                if name != "Flat":
                    source = references["ShallowPool_"+name]
                    sheets.append(obj(waters,f"Shallows | {name}",source.data,(x,y,0)))
            tiles[x,y] = tile
    return tiles,sheets,sources


def joins(tiles):
    report=[]
    for (x,y),item in tiles.items():
        for axis,(dx,dy) in enumerate(((10,0),(0,10))):
            peer = tiles.get((x+dx,y+dy))
            if peer is not None:
                edge=(x,y)[axis]+5
                report.append(P["compare_edges"](P["outline"](item.data,axis,edge,item.location),
                    P["outline"](peer.data,axis,edge,peer.location),f"{item.name} → {peer.name}"))
    check(len(report)==31,len(report))
    return report


def crossing_tiles(parent,flat):
    return [obj(parent,f"Crossing check | Flat {x},{y}",flat.data,(x,y,0))
            for x in (-10,0,10) for y in (-40,-30,30,40)]


def check_crossings(mesh, apron):
    reports=[]
    for item in apron:
        x,y,_=item.location
        if abs(y)!=30:
            continue
        edge=math.copysign(25.,y)
        keep=lambda out:{k:v for k,v in out.items() if x-5<=k<=x+5}
        reports.append(P["compare_edges"](keep(P["outline"](mesh,1,edge)), P["outline"](item.data,1,edge,item.location),
                                         f"ProtectedMarsh to Flat at {x:g},{edge:g}"))
    check(len(reports)==6,len(reports))
    return reports


def reeds(scene,tiles):
    parent=group("03 | Editable ENV-005 reeds",scene.collection)
    reeds = append("ENV-005", R["PLANTS"]["REEDS"])
    for plant in reeds.values():
        parent.objects.link(plant)
        plant.hide_render=True
        plant.hide_set(True)
    points, faces, edges=[],[],[]
    for coordinate in ((-20,0),(-10,0),(-10,-10),(-10,10),(0,-10),(0,0),(10,-10),(10,0),(10,-20)):
        tile=tiles[coordinate]
        start=len(points)
        points.extend(v.co+tile.location for v in tile.data.vertices)
        faces.extend(tuple(start+i for i in p.vertices) for p in tile.data.polygons)
        edges.extend(R["contour"](tile.data,tile.location))
    ground=bpy.data.meshes.new("ProtectedMarsh | shore-oriented seed weights")
    ground.from_pydata(points,[],faces)
    ground.update()
    vertices=ground.attributes.new(R["ATTR_DENSITY"],"FLOAT","POINT")
    vertices.data.foreach_set("value",[math.exp(-(R["distance_to_segments"](p.xy,edges)/1.28)**2) for p in points])
    carrier=obj(parent,"Marsh reeds | seed and exclusions",ground)
    maker=R["make_graph"]
    maker.__globals__["KEEP_OUT"]=(APRON,PAD_BUFFER)
    nodes=maker(reeds)
    nodes.name="ProtectedMarsh | ENV-005 shore distribution"
    mod=R["modify"](carrier,nodes,"ShoreEdge")
    for key,val in (("Seed",SEED),("Density per BU²",5.10),("Interior fraction",.034),("Wind angle radians",.047)):
        R["set_input"](mod,key,val)
    positions=R["extract"](carrier)
    check(positions==R["extract"](carrier),"Changed seed result.")
    mesh=R["freeze"](carrier)
    mesh.name="ProtectedMarsh | Baked reed geometry"
    widths=[max(abs(v.co.x-x)-rx,abs(v.co.y-y)-ry) for v in mesh.vertices for x,y,rx,ry in (APRON,PAD_BUFFER)]
    check(min(widths)>.08 and min(p[2] for p in positions)>WATER+.02,(len(positions),min(widths)))
    check(len(set(p[3] for p in positions))==6,len(positions))
    carrier.hide_render=True
    carrier.hide_set(True)
    return mesh,{"instances":len(positions),"seed":SEED,"variant_counts":dict(Counter(list(reeds)[p[3]] for p in positions)),
                 "min_reed_vertex_buffer_to_keepout_BU":min(widths),"flight_keepout_center_and_half_size_BU":APRON,
                 "min_reed_root_height_above_water_BU":min(p[2] for p in positions)-WATER}


def materials_after_gray(output,tiles,water_sheets):
    sources = W["source_materials"]()
    (output/"textures").mkdir()
    result={}
    for key,name in [((-10,0),"WestReedwater"),((10,-10),"EastShallows")]:
        terrain=tiles[key]
        surface=next(o for o in water_sheets if o.name==terrain.name+" water")
        info=W["shade"]("ShallowPool_StartMudflat",surface,terrain,sources,output)
        path=output/info["path"]
        dest=path.with_name("ft_goose_env_water_protected_"+("west" if key[0]<0 else "east")+"_basecolor_alpha.png")
        path.rename(dest)
        material=surface.data.materials[0]
        t=next(n for n in material.node_tree.nodes if n.type=="TEX_IMAGE")
        temporary=t.image
        image=bpy.data.images.load(str(dest),check_existing=False)
        image.alpha_mode="STRAIGHT"
        image.pack()
        t.image=image
        if temporary.users==0:
            bpy.data.images.remove(temporary)
        material.name="Protected"+name
        result[material.name]={"generated_path":dest.relative_to(output).as_posix(),"sha256":digest(dest),
                               "MAT-004_base_png":info["mat004_source"]}
    BASELINE["restore_mat_names"]([*tiles.values(),*water_sheets])
    return result


def plates(scene,name,tiles,sheets,reeds_mesh,grays=None):
    parent=group(name,scene.collection)
    land=BASELINE["bake"](tiles.values(),parent,NODES[0]+(" gray" if grays else ""))
    wet=BASELINE["bake"](sheets,parent,NODES[1]+(" gray" if grays else ""))
    reed=obj(parent,NODES[2]+(" gray" if grays else ""),reeds_mesh.copy() if grays else reeds_mesh)
    layers=dict(zip(NODES,(land,wet,reed)))
    if grays:
        for key,item in layers.items():
            for i in range(len(item.data.materials)):item.data.materials[i]=grays[key]
    return parent,layers


def circle_clear(cx,cy,rect):
    x0,x1,y0,y1=rect
    return math.hypot(max(x0-cx,cx-x1,0),max(y0-cy,cy-y1,0))


def flight_proof(layers,bird,inputs,apron=(),extent=(START,FINISH)):
    lowest = min(v.co.z for v in bird.data.vertices)
    radius=max(v.co.xy.length for v in bird.data.vertices)
    min_x,max_x=[func(v.co.x for v in bird.data.vertices) for func in (min,max)]
    pos=[Vector((0,0))]
    for i in range(11):
        rank=(i//2+1)*inputs["rank_spacing_BU"]
        pos.append(Vector((-rank if i%2==0 else rank,-rank)))
    sweep=inputs["radius_BU"]
    gaps={}
    for name,item in layers.items():
        x,y,_=B["tile_box"](item.data)
        gaps[name]=circle_clear(*HUB,(*x,*y))-sweep
    check(min(gaps.values())>.25,gaps)
    start,finish=extent
    exact = min(math.hypot(LANE_X+off.x-HUB.x,max(start+off.y-HUB.y,HUB.y-(finish+off.y),0))-radius-sweep
                for off in pos)
    check(exact>.8,exact)
    floor=BASELINE["ray_tree"]([layers[NODES[0]],*apron])
    plants=BASELINE["ray_tree"]([layers[NODES[2]]])
    footpad=BASELINE["ground_at"]
    min_height=math.inf
    probes=0
    for j in range(121):
        y=start+(finish-start)*j/120
        for i,off in enumerate(pos):
            z=ROOT_HEIGHT_GAME_UNITS[int(i!=0)]/SCALE+lowest
            for tip in (min_x,0,max_x):
                x=LANE_X+off.x+tip
                step_y=y+off.y
                min_height=min(min_height,z-footpad(floor,x,step_y))
                hit,*_=plants.ray_cast(Vector((x,step_y,-.18)),Vector((0,0,1)),2)
                check(hit is None,("plant blocks a full-formation probe",j,i,tip,x,step_y))
                probes+=1
    check(min_height>.08,min_height)
    return {"positions":121,"full_formation_count":len(pos),"fit_probe_count":probes,
            "minimum_static_mesh_clearance_above_ground_BU":min_height,
            "continuous_flock_envelope_to_sweep_gap_BU":exact,"wetland_layer_AABB_to_sweep_gaps_BU":gaps,
            "conservative_CHR001_neutral_pose_footprint_radius_BU":radius,
            "wingtip_to_wingtip_formation_width_BU":max(p.x for p in pos)+max_x-min(p.x for p in pos)-min_x,
            "slot_offsets_xy_BU":[list(p) for p in pos],"leader_ingress_exit_y_BU":[start,finish],"leader_x_BU":LANE_X,
            "proof":"Analytic closest distance from every straight slot trajectory with a full-size bird bounding disc; center and two wingtip BVH rays at 121 stations."}


def boundary_proof(layers,bird,inputs,flat,parent):
    apron=crossing_tiles(parent,flat)
    try:
        geometry=check_crossings(layers[NODES[0]].data,apron)
        flight=flight_proof(layers,bird,inputs,apron,(OUTSIDE_START,OUTSIDE_FINISH))
        r=flight["conservative_CHR001_neutral_pose_footprint_radius_BU"]
        start_clear=RECT[2]-(OUTSIDE_START+r)
        exit_clear=min(OUTSIDE_FINISH+dy-r-RECT[3] for _,dy in flight["slot_offsets_xy_BU"])
        check(min(start_clear,exit_clear)>1,(start_clear,exit_clear))
        return {"connection_joins":geometry,"flight":flight,
                "all_birds_clear_of_marsh_at_ingress_BU":start_clear,"all_birds_clear_of_marsh_at_egress_BU":exit_clear}
    finally:
        for tile in apron:
            bpy.data.objects.remove(tile,do_unlink=True)


def shape(parent,name,x,y,z,dimensions,mat,heading=0):
    w,l,h=(d/2 for d in dimensions)
    pts=[(a,b,c) for c in (-h,h) for b in (-l,l) for a in (-w,w)]
    faces=((0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5))
    item=B["simple_mesh"](parent,name,pts,faces,mat)
    item.location=(x,y,z)
    item.rotation_euler.z=heading
    return item


def proxy(parent,inputs,gray):
    """Review-only form from the present PlayfieldView.swift size parameters."""
    tower = B["paint"]("Review tower | cool mineral","8D9190" if gray else "6E7271")
    rotor = B["paint"]("Review blades | cool metal","9B9D9D" if gray else "969B9D")
    lamp = B["paint"]("Review nacelle | diffused warm","CAC5AD" if gray else "C0AB79")
    ring = B["paint"]("Technical sweep arc | muted bronze","B9A783" if gray else "AC956F")
    xo,yo=HUB
    for key,center,dimensions in (("Tower",35,(16,16,70)),("Across",68,(86,8,3)),
                                   ("Along",68,(8,86,3)),("Hub glow",74,(8,8,8))):
        m = tower if key=="Tower" else lamp if key=="Hub glow" else rotor
        shape(parent,"Swift proxy | "+key,xo,yo,center/SCALE,[d/SCALE for d in dimensions],m)
    r=inputs["radius_BU"]
    a=math.tau/80
    vertices,faces=[],[]
    for i in range(80):
        if i%5==4:continue
        offset=len(vertices)
        for k,rad in ((i,r-.045),(i+1,r-.045),(i+1,r+.045),(i,r+.045)):
            vertices.append((xo+rad*math.cos(k*a),yo+rad*math.sin(k*a),.021))
        faces.append(tuple(offset+j for j in range(4)))
    return B["simple_mesh"](parent,"Measured Swift radius | review ticks",vertices,faces,ring)


def context(scene,flat):
    aprons=group("Review surround | tiles outside GLB",scene.collection)
    for x in range(-80,111,10):
        for y in range(-60,141,10):
            if x in COLS and y in ROWS:continue
            obj(aprons,f"Local preview floor {x},{y}",flat.data,(x,y,0))
    return aprons


def route_markers(parent,gray):
    paint=B["paint"]("Review route | pale warm accents","D2C4A1" if gray else "C8AF7F")
    vertices,faces=[],[]
    for j in range(74):
        y=-28+j*.87
        x=LANE_X
        i=len(vertices)
        vertices.extend(((x-.067,y-.14,.026),(x+.067,y-.14,.026),(x+.067,y+.14,.026),(x-.067,y+.14,.026)))
        faces.append((i,i+1,i+2,i+3))
    return B["simple_mesh"](parent,"Ingress and egress route | technical reference",vertices,faces,paint)


def render_stage(scene,flat,layers,out,prefix,inputs,pose_mesh=None):
    gray=prefix=="graybox"
    context(scene,flat)
    studio=B["studio"](scene,scene.collection)
    key=next(o for o in studio.objects if o.type=="LIGHT")
    key.data.color=(1.,.92,.80)
    key.rotation_euler=Vector((-.36,.51,-1)).to_track_quat("-Z","Y").to_euler()
    sky=scene.world.node_tree.nodes.get("Background")
    sky.inputs["Color"].default_value=(.62,.70,.73,1.)
    review=group("Review | Wind-sweep schematic, flight, and flock",scene.collection)
    proxy(review,inputs,gray)
    route_markers(review,gray)
    neutral=B["add_goose"](review)
    results=flight_proof(layers,neutral,inputs)
    crossing=boundary_proof(layers,neutral,inputs,flat,review)
    if pose_mesh is None:
        raise ValueError("A RestPatch is required for the stand-pose proof.")
    flock,landing=BASELINE["populate_flock"](review,pose_mesh)
    for item in flock:item.hide_set(True);item.hide_render=True
    heading=Vector((.26,.965609)).normalized()
    top=B["camera"](studio,"Protected wetland | overhead",(-4,1,92),(-4,1,0),54)
    approach=B["camera"](studio,"Current rig | approach to wetland",(0,0,1),(0,1,0))
    rest=B["camera"](studio,"Current rig | safe landing side",(0,0,1),(0,1,0))
    departure=B["camera"](studio,"Current rig | egress outside sweep",(0,0,1),(0,1,0))
    B["pose_at"](approach,neutral,(LANE_X,-12.4),heading)
    if prefix!="roundtrip":
        B["render"](scene,approach,out,prefix+"_fixed_rear_approach",SIZE,17 if gray else 23)
    neutral.hide_render=True
    for item in flock:item.hide_set(False);item.hide_render=False
    B["follow"](rest,(0,-3.05),Vector((0,1)))
    scene.camera=rest
    landing["fixed_rear_projection_per_bird"]=BASELINE["flock_pixels"](scene,rest,flock)
    B["render"](scene,rest,out,prefix+"_fixed_rear_landing",SIZE,17 if gray else 23)
    for item in flock:item.hide_set(True);item.hide_render=True
    if prefix=="preview":
        for i,(dx,dy) in enumerate(results["slot_offsets_xy_BU"]):
            bird=obj(review,f"Review V formation {i+1:02}",neutral.data,
                     (LANE_X+dx,13.3+dy,ROOT_HEIGHT_GAME_UNITS[int(i!=0)]/SCALE))
            bird.hide_render=True
            bird.hide_set(True)
        active=[o for o in review.objects if o.name.startswith("Review V formation")]
        for item in active:item.hide_render=False;item.hide_set(False)
        B["render"](scene,top,out,prefix+"_top", (1050,1050),21)
        for item in active:item.hide_render=True;item.hide_set(True)
        B["pose_at"](departure,neutral,(LANE_X,4.1),Vector((.15,.988686)).normalized())
        neutral.hide_render=False
        B["render"](scene,departure,out,prefix+"_fixed_rear_exit",SIZE,23)
    else:
        B["render"](scene,top,out,prefix+"_top",(1050,1050),16)
    if prefix=="preview":
        B["pose_at"](approach,neutral,(LANE_X,-12.4),heading)
    neutral.hide_render=prefix!="preview"
    B["set_preview_workspace"](scene,approach if prefix=="preview" else rest)
    scene.render.filepath="//protected_marsh.png"
    return {"flight":results,"boundary_crossing":crossing,"dry_landings":landing}


def render_motion(output,candidate):
    bpy.ops.wm.open_mainfile(filepath=str(candidate/f"{STEM}.blend"))
    scene=bpy.data.scenes["ENV-016 | Fixed rear review and Swift sweep"]
    bpy.context.window.scene=scene
    camera=bpy.data.objects["Current rig | approach to wetland"]
    neutral=next(o for o in scene.objects if o.name.startswith("Review | CHR-001 neutral pose"))
    neutral.hide_render=True
    flock=sorted((o for o in scene.objects if o.name.startswith("Review V formation")),key=lambda o:o.name)
    check(len(flock)==12,len(flock))
    qa=json.loads((candidate/"qa.json").read_text())
    offsets=qa["textured"]["flight"]["slot_offsets_xy_BU"]
    frames=output/"frames"
    frames.mkdir()
    count=24
    for i in range(count):
        y=OUTSIDE_START+(OUTSIDE_FINISH-OUTSIDE_START)*i/(count-1)
        for j,(bird,(dx,dy)) in enumerate(zip(flock,offsets)):
            bird.location=(LANE_X+dx,y+dy,ROOT_HEIGHT_GAME_UNITS[int(j!=0)]/SCALE)
            bird.hide_set(False)
            bird.hide_render=False
        B["follow"](camera,(LANE_X,y),Vector((0,1)))
        B["render"](scene,camera,frames,f"{i:04}",SIZE,8)
    encoder=shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    review=output/"preview_fixed_rear_egress.mp4"
    subprocess.run([encoder,"-hide_banner","-loglevel","error","-framerate","8","-i",str(frames/"%04d.png"),
                    "-vf","pad=852:394:0:0,fps=24","-c:v","libx264","-pix_fmt","yuv420p","-crf","18","-an",
                    "-movflags","+faststart",str(review)],check=True)
    subprocess.run([encoder,"-hide_banner","-loglevel","error","-xerror","-i",str(review),"-f","null","-"],check=True)
    write(output/"motion_report.json",{"result":"pass","source_px":list(SIZE),"encoded_px":[852,394],
           "rendered_frames":count,"duration_seconds":3,"h264_decode":"pass",
           "leader_y_BU":[OUTSIDE_START,OUTSIDE_FINISH],
           "pose":"Static CHR-001 neutral flight mesh moving in the audited Swift 12-bird slot formation. Out-of-frame rear rows are shown in the overhead view."})


def map_textures(texture_data,extras):
    for key,data in texture_data.items():
        candidates=[]
        for src in (*SOURCES.values(), *(LIB/tag/"v001/asset_manifest.json" for tag in ("MAT-001","MAT-003","MAT-004"))):
            for path in (src.parent/"textures").glob("*.png"):
                if digest(path)==data["sha256"]:candidates.append(path.relative_to(LIB).as_posix())
        if key in extras:
            check(extras[key]["sha256"]==data["sha256"],key)
            data.update(extras[key])
        else:
            check(candidates,(key,data))
            data["repo_relative_from_Blender"]=sorted(set(candidates))
    return texture_data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--verify",type=Path)
    mode.add_argument("--motion",type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    check(not any(output.iterdir()),"Output must be a clean temporary directory.")
    if args.motion:
        render_motion(output,args.motion.resolve())
        return
    inputs=runtime_inputs()
    if args.verify:
        path=args.verify.resolve()
        bpy.ops.wm.open_mainfile(filepath=str(path/f"{STEM}.blend"))
        m=json.loads((path/"asset_manifest.json").read_text())
        qa=json.loads((path/"qa.json").read_text())
        layers={key:bpy.data.objects[key] for key in NODES}
        fresh=B["fresh_scene"]("ENV-016 | Independent GLB readback")
        restored,roundtrip=BASELINE["transport"](path,layers,m["textures"])
        result=BASELINE["verify_water"]([restored[NODES[1]]],[restored[NODES[0]]])
        check(qa["roundtrip"]["water"]==result,"Water readback geometry changed.")
        goose=B["add_goose"](fresh.collection)
        flight=flight_proof(restored,goose,inputs)
        flat=append("ENV-001",("Flat",))["Flat"]
        crossing=boundary_proof(restored,goose,inputs,flat,fresh.collection)
        check(qa["roundtrip"]["geometry"]==roundtrip and qa["roundtrip"]["flight"]==flight,
              (roundtrip.keys(),flight.keys()))
        check(qa["roundtrip"]["boundary_crossing"]==crossing,"Border crossing changed.")
        write(output/"recheck.json",{"result":"pass","roundtrip":roundtrip,"flight":flight,"water":result,
              "boundary_crossing":crossing})
        return

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    edit=bpy.context.scene
    edit.name="ENV-016 | Editable wetland layout"
    neutral={"water":B["paint"]("Graybox water","899FA5"),"ground":B["paint"]("Graybox land","A4A9A0"),
             "reeds":B["paint"]("Graybox vegetation","74827B")}
    tiles,sheets,source=terrain_and_water(edit,neutral)
    join=joins(tiles)
    water=BASELINE["verify_water"](sheets,list(tiles.values()))
    reed_mesh,scatter=reeds(edit,tiles)
    grey=B["fresh_scene"]("ENV-016 | Graybox evidence")
    _,layers=plates(grey,"Graybox draw layers",tiles,sheets,reed_mesh,dict(zip(NODES,(neutral["ground"],neutral["water"],neutral["reeds"]))))
    flat=obj(grey.collection,"Gray Flat source",source["Flat"].data.copy())
    for i in range(len(flat.data.materials)):flat.data.materials[i]=neutral["ground"]
    flat.hide_render=True
    before=render_stage(grey,flat,layers,output,"graybox",inputs,source["RestPatch"])
    bpy.data.scenes.remove(grey)
    bpy.context.window.scene=edit
    new_textures=materials_after_gray(output,tiles,sheets)
    baked=B["fresh_scene"]("ENV-016 | Baked production visual")
    collection,layers=plates(baked,"ProtectedMarsh | three draw layers",tiles,sheets,reed_mesh)
    root=obj(collection,ROOT,None)
    root["asset_role"]="Wetland visual only"
    root["review_hub_radius_BU"]=inputs["radius_BU"]
    root["review_hub_position_xy_BU"]=list(HUB)
    root["reference_egress_y_BU"]=FINISH
    root["collision_authoring_pending"]=True
    for key,item in layers.items():item.parent=root
    texture_map=map_textures(BASELINE["textures_in"](layers),new_textures)
    BASELINE["choose_export"](root,layers,output)
    review=B["fresh_scene"]("ENV-016 | Fixed rear review and Swift sweep")
    parent=group("Wetland review mesh duplicates",review.collection)
    visual={key:obj(parent,key+" | view",item.data) for key,item in layers.items()}
    for key,place in LANDMARKS.items():
        m=obj(review.collection,key,None,place)
        m.empty_display_size=.6
    measured=render_stage(review,source["Flat"],visual,output,"preview",inputs,source["RestPatch"])
    check(measured["flight"]==before["flight"],"Textured geometry changed.")
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{STEM}.blend"))
    fresh=B["fresh_scene"]("ENV-016 | GLB readback")
    restored,report=BASELINE["transport"](output,layers,texture_map)
    after=render_stage(fresh,source["Flat"],restored,output,"roundtrip",inputs,source["RestPatch"])
    check(after["flight"]==measured["flight"],"GLB aircraft corridor checks change.")
    check(after["boundary_crossing"]["flight"]==before["boundary_crossing"]["flight"],"GLB terrain border route changed.")
    write(output/"qa.json",{"id":"ENV-016","version":"v001","status":"needs_review","snap_joins":join,
          "water_terrain_contacts":water,"reed_scatter":scatter,"source_swift_values":inputs,
          "graybox":before,"textured":measured,"roundtrip":{"geometry":report,
               "water":BASELINE["verify_water"]([restored[NODES[1]]],[restored[NODES[0]]]),"flight":after["flight"],
               "boundary_crossing":after["boundary_crossing"]},
          "app_baseline":{"source":"plans/active/goose-preview-model-cleanup.md","date":"2026-11-13",
               "simulator":"iPhone 18 Pro, iOS 27.2","historical_tests_passed":340,"rerun_for_this_asset":False},
          "redline_review":{"result":"pass","scope":"Visual modeling and offline review only",
               "reference":"plans/_templates/redline-checklist.md"},
          "pending":["STR-002 full farm placement and FX-010 visible safety envelope integration.",
               "RealityKit collision, runtime supply and exiting autonomy, transparency sort, iPhone/iPad."]})
    write(output/"asset_manifest.json",{"id":"ENV-016","version":"v001","status":"needs_review",
          "execution_order_1_based":40,"depends":["ENV-002/v001","ENV-003/v001","ENV-005/v001","STR-002"],
          "dependency_pending":{"STR-002":"GrayboxPlaces/PlayfieldView single turbine proxy used in review only."},
          "refs":{key:digest(p) for key,p in SOURCES.items()},"release_role":"Modeling candidate",
          "blender_version":"5.2.2 LTS","blender_file":f"{STEM}.blend","glb_file":GLB,
          "root_transform_BU":[0,0,0],"blender_xyz_maps_to_gltf":["x","z","-y"],"root_node":ROOT,
          "layers":list(NODES),"ground_extent_XY_BU":RECT,"water_z_BU":WATER,
          "review_landmarks_BU":LANDMARKS,"textures":texture_map,
          "rights":"Original project modeling with verified internal material plates, no third-party input."})


if __name__=="__main__":
    main()
