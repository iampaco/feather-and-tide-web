"""Build the in-place lake rest patch, then verify the exact GLB against the editable scene."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import runpy
import sys

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
CHECKPOINT = runpy.run_path(str(LIB / "ENV-014/v001/ENV-014_generate.py"))
LAKE = runpy.run_path(str(LIB / "ENV-008/v001/ENV-008_generate.py"))
B, R, W, F, P = (CHECKPOINT[key] for key in ("B", "R", "W", "F", "P"))
check, obj, group, write, digest = (B[k] for k in ("check","obj","collection","write_json","file_hash"))

STEM = "ENV-015_lakeside_rest"
ROOT = "LakesideRest"
NODES = ("LakesideRest_Ground", "LakesideRest_Water", "LakesideRest_Reeds")
GLB = "ENV-015_LakesideRest.glb"
GROUND_PNG = "ft_goose_env_lakeside_rest_ground_basecolor.png"
TEX_BASENAME = "ft_goose_env_lakeside_rest_basecolor_alpha.png"
WATER, STEP, SIZE = B["WATER"], B["STEP"], B["GAME_SIZE"]
ORIGIN = Vector((4, 10, 0))
SOURCES = {
    "ENV-002": LIB / "ENV-002/v001/ENV-002_wetland.blend",
    "ENV-003": LIB / "ENV-003/v001/ENV-003_wetland_water.blend",
    "ENV-005": LIB / "ENV-005/v001/ENV-005_reed_distribution.blend",
    "ENV-008": LIB / "ENV-008/v001/ENV-008_long_lake.blend",
    "ENV-010": LIB / "ENV-010/v001/ENV-010_short_pass.blend",
    "ANM-007": LIB / "ANM-007/v001/ANM-007_landing.blend",
    "CHR-001": LIB / "CHR-001/v001/CHR-001_goose_rig.blend",
    "MAT-003": LIB / "MAT-003/v001/MAT-003_wetland_rock.blend",
}
SEED = 15026
PAD = (-.52, .03, 2.18, 2.78)
KEEP_OUT = (PAD, (2.35, -2.63, 3.35, 2.48), (2.6, 2.55, 2.85, 2.50))
ROUTE = {
    "entry": ((12.1,5.85),(9.2,6.9),(6.25,7.9),(4.2,9.2),(3.5,9.98)),
    "exit": ((3.5,9.98),(4.6,11.35),(7.15,12.1),(10.2,13.3),(14.2,15.0)),
}


def append(key, names):
    return P["append"](SOURCES[key], names)


def terrain_profile(x, y, source_z):
    u = x + .46 - .31 * math.sin(.88 * y + .28)
    v = y + .17 + .22 * math.sin(.96*x)
    r = (abs(u/3.84)**2.6 + abs(v/3.72)**2.6)**(1/2.6)
    # Keep the source landing saddle at its original height, surrounded by a shallow crescent.
    inset = B["smooth"]((r-.795)/.21)
    border = B["smooth"]((4.80 - max(abs(x), abs(y))) / .59)
    shore = B["smooth"]((1.32-r)/.27)
    asymmetry = .78+.22 * math.sin(.87*y+x*.4+1.4)
    depression = .528 * inset * shore * border * asymmetry
    return min(0, source_z*.12*inset-depression)


def build_terrain(parent, source, shore):
    mats, _ = B["load_materials"]()
    names = ("GrassFlat","MudBank","ShallowMargin","MossStone")
    verts = [(v.co.x,v.co.y,terrain_profile(*v.co)) for v in source.data.vertices]
    faces, uvs, slots = [],[],[]
    for poly in source.data.polygons:
        ids = tuple(poly.vertices)
        x,y,z = [sum(verts[i][axis] for i in ids)/len(ids) for axis in range(3)]
        # Subdued bank bands curve with the lower channel and leave the crown mottled but open.
        radius = ((x+.42)/3.7)**2 + ((y+.12)/3.62)**2
        if z < -.205: mat = 2
        elif z < -.027 or (.42<radius<1.12 and math.sin(.9*y+.64*x)>.00): mat = 1
        elif .28<radius<.65 and math.sin(1.94*x+.85*y)>.69: mat = 3
        else: mat = 0
        faces.append(ids)
        slots.append(mat)
        uvs.append([LAKE["ground_uv"](Vector(verts[i])+ORIGIN) for i in ids])
    terrain=CHECKPOINT["make_tri"](parent,NODES[0],verts,faces,[mats[name] for name in names],slots,uvs,[True]*len(faces))
    donor_normals = {}
    for loop in shore.data.loops:
        p=shore.data.vertices[loop.vertex_index].co
        on_y_edge=p.y in {5,15} and -1<=p.x<=9
        on_east_edge=p.x==9 and 5<=p.y<=15
        if on_y_edge or on_east_edge:
            donor_normals[(p.x,p.y)] = shore.data.corner_normals[loop.index].vector.copy()
    normals=[]
    for v in terrain.data.vertices:
        edge=abs(v.co.x)==5 or abs(v.co.y)==5
        normals.append(donor_normals.get(tuple((v.co+ORIGIN).xy),(0,0,1)) if edge else (0,0,0))
    terrain.data.normals_split_custom_set_from_vertices(normals)
    terrain["replacement_for"]="ENV-008 placeholder RestPatch at (4,10,0)"
    return terrain


def check_engine_seam(item, shore):
    local_edges = ((0,-5),(0,5),(1,-5),(1,5))
    labels = ("west","east","south","north")
    origin = tuple(ORIGIN)
    result = {}
    for (axis,coord), name in zip(local_edges,labels):
        # Both the old placeholder and its surroundings contain edge points at these coordinates.
        edge_world = ORIGIN[axis]+coord
        along = ORIGIN[1-axis]
        local = P["outline"](item.data,axis,edge_world,origin)
        lake={}
        lo,hi=along-5,along+5
        for p in shore.data.polygons:
            if not (p.center.x<-1 or p.center.x>9 or p.center.y<5 or p.center.y>15):
                continue
            for j in p.loop_indices:
                loop=shore.data.loops[j]
                point=shore.data.vertices[loop.vertex_index].co
                if abs(point[axis]-edge_world)<1e-5 and lo<=point[1-axis]<=hi:
                    lake.setdefault(round(point[1-axis],5),[]).append((
                        point.copy(),shore.data.corner_normals[j].vector.copy(),shore.data.uv_layers.active.data[j].uv.copy()))
        if name=="west":
            # LakeShore ends here. The adjacent review forecourt has the same reference plane and UV phase.
            lake={key:[(Vector((edge_world,key,0)),Vector((0,0,1)),Vector(LAKE["ground_uv"]((edge_world,key,0))))]
                  for key in local}
        result[name]=P["compare_edges"](local,lake,"LakesideRest "+name+" → "+("review forecourt" if name=="west" else "ENV-008"))
    return result


def carve_lake_apron(parent, source):
    # Remove the exact placeholder area from the bundled review copy, retaining its outer seam.
    lo_x,lo_y,_ = ORIGIN-Vector((5,5,0))
    hi_x,hi_y,_ = ORIGIN+Vector((5,5,0))
    deleted = 0

    def outside(item,tri):
        nonlocal deleted
        verts=[item.data.vertices[i].co for i in tri.vertices]
        x,y=[sum(v[k] for v in verts)/len(verts) for k in (0,1)]
        if lo_x<x<hi_x and lo_y<y<hi_y:
            check(all(lo_x-1e-5<=v.x<=hi_x+1e-5 and lo_y-1e-5<=v.y<=hi_y+1e-5 for v in verts),tri.index)
            deleted+=1
            return False
        return True

    result=CHECKPOINT["bake"]([source],parent,"Review | ENV-008 shore outside exact module",retain=outside)
    check(deleted==512,("unexpected ENV-008 placeholder topology",deleted))
    return result,deleted


def add_reeds(parent, terrain):
    stems=group("Live shoreline distribution and ENV-005 variants",parent)
    prototypes=append("ENV-005", R["PLANTS"]["REEDS"])
    for reed in prototypes.values():
        stems.objects.link(reed)
        reed.hide_set(True)
        reed.hide_render=True
    support=terrain.data.copy()
    weights = support.attributes.new(R["ATTR_DENSITY"],"FLOAT","POINT")
    edge=R["contour"](support,(0,0,0))
    values=[]
    for v in support.vertices:
        p=v.co
        shoreline=math.exp(-(R["distance_to_segments"](p.xy,edge)/.61)**2)
        # North and southwest flanks carry the silhouette. The central island and lake-side openings stay dry and open.
        bank = B["smooth"]((p.y-1.75)/2.8)
        bank += B["smooth"]((-p.y-.9)/2.38)*B["smooth"]((-p.x-.38)/2.2)
        bank += .58*B["smooth"]((-p.x-1.85)/1.95)
        values.append(min(1,shoreline * max(.12,bank)))
    weights.data.foreach_set("value",values)
    bed=obj(stems,"LakesideRest | editable shoreline density",support)
    make_graph=R["make_graph"]
    make_graph.__globals__["KEEP_OUT"]=KEEP_OUT
    graph=make_graph(prototypes)
    graph.name="LakesideRest | ENV-005 sparse shore"
    mod=R["modify"](bed,graph,"ShoreEdge")
    for name,value in (("Seed",SEED),("Density per BU²",4.65),("Interior fraction",.022),
                       ("Wind angle radians",.018)):
        R["set_input"](mod,name,value)
    points=R["extract"](bed)
    check(points==R["extract"](bed),"same seed changed points")
    mesh=R["freeze"](bed)
    mesh.name="LakesideRest | Frozen reeds"
    expected=sum(len(list(prototypes.values())[p[3]].data.polygons) for p in points)
    mesh.calc_loop_triangles()
    margin=min(max(abs(v.co.x-cx)-rx,abs(v.co.y-cy)-ry) for v in mesh.vertices for cx,cy,rx,ry in KEEP_OUT)
    min_z=min(p[2] for p in points)-WATER
    check(12<=len(points)<=60 and margin>.08 and min_z>=.02099 and len(mesh.loop_triangles)==expected,
          (len(points),margin,min_z,len(mesh.loop_triangles),expected))
    bed.hide_render=True
    bed.hide_set(True)
    counts=Counter(list(prototypes)[p[3]] for p in points)
    return mesh,{"seed":SEED,"instances":len(points),"per_variant":dict(counts),"triangles":expected,
                 "min_reed_margin_to_clear_zones_BU":margin,"min_root_height_above_water_BU":min_z,
                 "same_seed_equal":True,"no_plant_rectangles_xy_center_half_dimensions_BU":KEEP_OUT}


def topology(terrain, waters, floor):
    data=CHECKPOINT["verify_water"](waters,[terrain])
    local=F["land_mesh"](terrain.data)
    area=sum(poly.area for water in waters for poly in water.data.polygons)
    wet_counts=[]
    dry_min=math.inf
    # Prove that a wet ring separates the dry landing crown from the edge: one wet point on each direction ray.
    for i in range(36):
        theta=math.tau*i/36
        hits=[]
        for r_step in range(40):
            r=.12*r_step
            x=-.53+math.cos(theta)*r
            y=math.sin(theta)*r
            if max(abs(x),abs(y))>=4.84: break
            h=F["terrain_at"](local,x,y)
            if h is not None and h < WATER-.015: hits.append(h)
        wet_counts.append(len(hits))
    x0,y0,hx,hy=PAD
    for fx in (-.82,-.5,0,.45,.78):
        for fy in (-.8,-.5,0,.5,.8):
            h=F["terrain_at"](local,x0+hx*fx,y0+hy*fy)
            dry_min=min(dry_min,h)
    check(min(wet_counts)>0 and dry_min>WATER+.042,(wet_counts,dry_min))
    return {"water":data,"water_total_area_BU2":area,"radial_samples_with_wet_segment":len(wet_counts),
            "minimum_underwater_hits_per_ray":min(wet_counts),"pad_min_height_above_water_BU":dry_min-WATER,
            "perimeter":check_engine_seam(terrain,floor)}


def populate(parent, terrain, offset=ORIGIN):
    birds,report=CHECKPOINT["populate_flock"](parent,terrain)
    for bird in birds: bird.location += offset
    report["worst_sole_probe_gap_BU"]=max(foot["max_sole_probe_gap_BU"] for slot in report["slots"] for foot in slot["feet"])
    report["minimum_ground_above_water_at_feet_BU"]=min(foot["min_ground_above_water_BU"] for slot in report["slots"] for foot in slot["feet"])
    return birds,report


def transects(land_tree, reeds_tree, flight_z, width):
    count, min_ground = 0, math.inf
    for phase, track in ROUTE.items():
        for a,b in zip(track,track[1:]):
            a,b=Vector(a),Vector(b)
            side=Vector((b.y-a.y,a.x-b.x)).normalized()
            for i in range(25):
                p=a.lerp(b,i/24)
                for offset in (-1.15,0,1.15):
                    for wing in (-width/2,0,width/2):
                        x,y=p+(offset+wing)*side
                        hit,*_=land_tree.ray_cast(Vector((x,y,4)),Vector((0,0,-1)),8)
                        check(hit is not None,("flight leaves terrain",phase,x,y))
                        min_ground=min(min_ground,flight_z-hit.z)
                        block,*_=reeds_tree.ray_cast(Vector((x,y,WATER-.01)),Vector((0,0,1)),2.1)
                        check(block is None,("reed projected across entry/exit envelope",phase,x,y))
                        count+=1
    check(min_ground>.09,(min_ground,count))
    return {"transect_sample_count":count,"min_CHR001_neutral_lower_edge_clearance_BU":min_ground,
            "main_lane_half_width_BU":1.15,"wing_width_BU":width,"lane_route_world_xy_BU":ROUTE,
            "projection_reed_hit_count":0,"lower_edge_height_BU":flight_z}


def patch_material(water, terrain, output):
    (output/"textures").mkdir()
    recipe=W["shade"]("ShallowPool_RestPatch",water,terrain,W["source_materials"](),output)
    generated=output/recipe["path"]
    renamed=generated.with_name(TEX_BASENAME)
    recipe_material=water.data.materials[0]
    prototype=append("ENV-003",("ShallowPool_RestPatch",))["ShallowPool_RestPatch"]
    mat=prototype.data.materials[0].copy()
    template_image=next(node.image for node in mat.node_tree.nodes if node.type=="TEX_IMAGE")
    recipe["ENV003_reference_packed_png_sha256"]=sha256(template_image.packed_file.data).hexdigest()
    baked_image=next(node.image for node in recipe_material.node_tree.nodes if node.type=="TEX_IMAGE")
    water.data.materials[0]=mat
    mat.name="LakesideRest_ShallowWater"
    for node in mat.node_tree.nodes:
        if node.type=="TEX_IMAGE":
            node.image=baked_image
            node.image.filepath="//textures/"+TEX_BASENAME
            node.image.name=TEX_BASENAME
    generated.rename(renamed)
    recipe["path"]="textures/"+TEX_BASENAME
    return recipe


def landscape_texture(ground, output):
    """Bake soft MAT-003 transitions into the existing world-phase UV atlas."""
    width=1024
    # MAT-003 source pixels are loaded from packed, verified materials and sampled at the exact original period.
    library={material.name.split(".")[0]:material for material in ground.data.materials}
    sampled={}
    for name,material in library.items():
        image=next(node.image for node in material.node_tree.nodes if node.type=="TEX_IMAGE")
        flat=np.empty(width*width*4,dtype=np.float32)
        image.pixels.foreach_get(flat)
        sampled[name]=flat.reshape(width,width,4)[...,:3]
    axis=(np.arange(width)+.5)/width
    row, col = np.meshgrid(axis, axis, indexing="ij")
    x=10*((col-.4)%1)-5
    y=10*row-5
    levels=WATER-W["depth_map"](ground)
    ix=(x+5)/10*(W["N"]-1)
    iy=(y+5)/10*(W["N"]-1)
    lower_x,lower_y=ix.astype(int),iy.astype(int)
    fx,fy=ix-lower_x,iy-lower_y
    values=(levels[lower_y,lower_x]*(1-fx)+levels[lower_y,lower_x+1]*fx)*(1-fy)
    values+=(levels[lower_y+1,lower_x]*(1-fx)+levels[lower_y+1,lower_x+1]*fx)*fy
    wet=WATER-values

    def ramp(value):
        clipped=np.clip(value,0,1)
        return clipped*clipped*(3-2*clipped)

    transition=ramp((-values-.006+.025*np.sin(2.22*x+1.14*y))/ .12)
    edge=ramp((4.75-np.maximum(np.abs(x),np.abs(y)))/.55)
    mud=(transition*edge)[...,None]
    shallow=(ramp((wet+.012)/.16)*edge)[...,None]
    stone=(edge*.20*ramp((np.sin(2.2*x-.67*y)+.21)/1.2)*transition)[...,None]
    grass_rgb=sampled["GrassFlat"]
    rgb=grass_rgb*(1-mud)+sampled["MudBank"]*mud
    rgb=rgb*(1-stone)+sampled["MossStone"]*stone
    rgb=rgb*(1-shallow)+sampled["ShallowMargin"]*shallow
    rgba=np.ones((width,width,4),dtype=np.float32)
    rgba[...,:3]=np.clip(rgb,0,1)
    image=bpy.data.images.new(GROUND_PNG,width,height=width,alpha=False)
    image.pixels.foreach_set(rgba.ravel())
    image.filepath_raw=str(output/"textures"/GROUND_PNG)
    image.file_format="PNG"
    image.save()
    image.pack()
    image.filepath="//textures/"+GROUND_PNG
    mat=library["GrassFlat"].copy()
    mat.name="LakesideRest_GroundPaint"
    shader_texture=next(node for node in mat.node_tree.nodes if node.type=="TEX_IMAGE")
    shader_texture.image=image
    ground.data.materials.clear()
    ground.data.materials.append(mat)
    for poly in ground.data.polygons: poly.material_index=0
    return {"path":"textures/"+GROUND_PNG,"sha256":digest(output/"textures"/GROUND_PNG),
            "source_textures":{name:sha256(next(node.image for node in material.node_tree.nodes
              if node.type=="TEX_IMAGE").packed_file.data).hexdigest() for name,material in library.items()},
            "uv_period_BU":10,"edge_paint_borrowed_from":"MAT-003/v001 GrassFlat"}

def local_wiring():
    # The checkpoint transport audit is shared by the three-layer wetland assemblies.
    transport=CHECKPOINT["transport"]
    transport.__globals__.update(ROOT=ROOT,NODES=NODES,GLB=GLB)
    textures_in=CHECKPOINT["textures_in"]
    textures_in.__globals__["NODES"]=NODES
    choose_export=CHECKPOINT["choose_export"]
    choose_export.__globals__["GLB"]=GLB


def texture_records(layers, generated):
    result=CHECKPOINT["textures_in"](layers)
    lookup={}
    for tag in ("MAT-001","MAT-003"):
        for p in (LIB/tag/"v001/textures").glob("*.png"):
            lookup[digest(p)]=p.relative_to(LIB).as_posix()
    for label,fields in result.items():
        if label in generated:
            bake=generated[label]
            check(fields["sha256"]==bake["sha256"],fields)
            fields["generated_path"]=bake["path"]
        else:
            fields["repo_relative_from_Blender"] = lookup[fields["sha256"]]
    return result


def fixed_cameras(parent):
    return {key:B["camera"](parent,label,(0,-6,3),(0,0,0)) for key,label in (
        ("fork","Fixed rear | before fork"),("entry","Fixed rear | lake exit to rest"),
        ("exit","Fixed rear | rest to main lake"))}


def add_context(parent, donor, lake_water, gray=False):
    apron,deleted=carve_lake_apron(parent,donor)
    lake=obj(parent,"Review | ENV-008 LakeWide",lake_water.data.copy())
    grass=next(material for material in donor.data.materials if material.name.split(".")[0]=="GrassFlat")
    floor=B["paint"]("Far soft shore","B8C3AD")
    if gray:
        gray_ground=B["paint"]("Graybox | surrounding ground","B7B8B2")
        gray_water=B["paint"]("Graybox | surrounding water","8AA6A8")
        for j in range(len(apron.data.materials)): apron.data.materials[j]=gray_ground
        for j in range(len(lake.data.materials)): lake.data.materials[j]=gray_water
        grass=gray_ground
        floor=gray_ground
    west_bounds=[(-240,-1,-7.5,150)]
    if not gray:
        west_bounds=[(-240,-21.5,-7.5,150),(-1.5,-1,-7.5,150),(-21.5,-1.5,-7.5,10),(-21.5,-1.5,50,150)]
        for name,shape in append("ENV-010",P["NAMES"]).items():
            obj(parent,"Review | ENV-010 "+name,shape.data,shape.location)
    surrounds=[B["rectangle"](parent,f"Review | west forecourt {i}",*bounds,0,grass)
               for i,bounds in enumerate(west_bounds)]
    surrounds.append(B["rectangle"](parent,"Review | south forecourt",-240,220,-32,-7.5,0,grass))
    surrounds.append(B["rectangle"](parent,"Review | north forecourt",-1,220,63,185,0,grass))
    points=[]
    for row_y in LAKE["ROW_Y"]:
        edge_point=LAKE["row_points"](row_y)[-1]
        points.extend((edge_point,(220,row_y,0)))
    quads=[(i,i+1,i+3,i+2) for i in range(0,len(points)-2,2)]
    surrounds.append(B["simple_mesh"](parent,"Review | east foreshore extension",points,quads,grass))
    B["rectangle"](parent,"Review | far colored floor",-240,220,-58,185,-.88,floor)
    for item in surrounds:
        uv=item.data.uv_layers.new(name="UVMap")
        for loop in item.data.loops:
            uv.data[loop.index].uv=LAKE["ground_uv"](item.data.vertices[loop.vertex_index].co)
    return apron,deleted


def visible_pad(scene, camera, floor, occluders):
    scene.camera = camera
    bpy.context.view_layer.update()
    focus = []
    visible=0
    for dx in (-1.75,-.875,0,.875,1.75):
        for dy in (-2.15,-1.075,0,1.075,2.15):
            x,y=ORIGIN.x+PAD[0]+dx,ORIGIN.y+PAD[1]+dy
            point=Vector((x,y,CHECKPOINT["ground_at"](floor,x,y)+.028))
            projected=world_to_camera_view(scene,camera,point)
            vector=point-camera.location
            hit,*_=occluders.ray_cast(camera.location,vector.normalized(),vector.length-.01)
            if projected.z>0 and .01<projected.x<.99 and .01<projected.y<.99 and hit is None:
                visible+=1
                focus.append((projected.x*SIZE[0],(1-projected.y)*SIZE[1]))
    check(visible>=18,("pre-fork visibility",visible))
    return {"visible_dry_pad_probes":visible,"dry_pad_probes_total":25,
            "dry_pad_pixel_box_at_852x393":[[min(v[i] for v in focus),max(v[i] for v in focus)] for i in (0,1)]}


def assemble_preview(scene, local, donor, lake_water, output, phase, wing):
    geo=group("LakesideRest in the long lake",scene.collection)
    placed={name:obj(geo,name+" | lake placement",item.data,ORIGIN) for name,item in local.items()}
    if phase=="roundtrip":
        # Blender imported the source layers into this scene at module-local zero.
        # Only the translated review instances belong in the assembled lake.
        for item in local.values():
            item.hide_render=True
            item.hide_set(True)
    flag=phase=="graybox"
    for name, color in zip(NODES,("A3ADA4","819FA4","677C75")):
        if flag:
            body=placed[name]
            body.data=body.data.copy()
            mat=B["paint"]("Graybox | "+name,color)
            for i in range(len(body.data.materials)): body.data.materials[i]=mat
    apron,deleted=add_context(group("Environment reference | ENV-008",geo),donor,lake_water,flag)
    land=CHECKPOINT["ray_tree"]([placed[NODES[0]],apron])
    reeds=CHECKPOINT["ray_tree"]([placed[NODES[2]]])
    routes=transects(land,reeds,*wing)
    studio=B["studio"](scene,scene.collection)
    cameras=fixed_cameras(studio)
    bird=B["add_goose"](geo)
    bird.name="Review | flight reference CHR-001"
    poses={"fork":((0,0),(.24,.97077)),"entry":((12.1,5.85),(-.94,.342)),
           "exit":((4.6,11.35),(.963,.268))}
    for key,(xy,forward) in poses.items():
        B["pose_at"](cameras[key],bird,xy,Vector(forward).normalized())
    scene.render.resolution_x,scene.render.resolution_y=SIZE
    view=visible_pad(scene,cameras["fork"],land,CHECKPOINT["ray_tree"]([placed[NODES[0]],apron,placed[NODES[2]]]))
    B["pose_at"](cameras["fork"],bird,poses["fork"][0],Vector(poses["fork"][1]).normalized())
    if output:
        B["render"](scene,cameras["fork"],output,phase+"_before_fork",SIZE,14 if flag else 24)
    if phase!="roundtrip":
        bird.hide_render=True
        flock,resting=populate(geo,local[NODES[0]])
        top=B["camera"](studio,"Survey | linked lake patch",(8.7,10.5,35),(8.7,10.5,0),23)
        if output:
            B["render"](scene,top,output,phase+"_top",(1000,740),16 if flag else 23)
        bird.hide_render=False
        for goose in flock: goose.hide_render=True
        if not flag and output:
            for key in ("entry","exit"):
                xy,heading=poses[key]
                B["pose_at"](cameras[key],bird,xy,Vector(heading).normalized())
                B["render"](scene,cameras[key],output,phase+"_"+key,SIZE,22)
            bird.hide_render=True
            for goose in flock: goose.hide_render=False
            bath=B["camera"](studio,"Survey | landing and wet edge",(9.0,3.3,5.4),(3.4,9.8,-.06))
            B["render"](scene,bath,output,phase+"_shore_detail",(1000,600),22)
            for goose in flock: goose.hide_render=True
            bird.hide_render=False
    else:
        flock,resting=populate(geo,local[NODES[0]])
        for goose in flock: goose.hide_render=True
    B["pose_at"](cameras["fork"],bird,poses["fork"][0],Vector(poses["fork"][1]).normalized())
    B["set_preview_workspace"](scene,cameras["fork"])
    scene.render.filepath="//review_before_fork.png"
    return {"apron_removed_triangles":deleted,"flight":routes,"before_fork":view,"stationary_flock":resting}


def wings_from_neutral():
    scene=B["fresh_scene"]("Temporary reference dimensions")
    item=B["add_goose"](scene.collection)
    xs=[v.co.x for v in item.data.vertices]
    zs=[v.co.z for v in item.data.vertices]
    wing=(8/B["SCALE"]+min(zs),max(xs)-min(xs))
    bpy.data.scenes.remove(scene)
    return wing


def parse():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--gray-only",action="store_true")
    return parser.parse_args(sys.argv[sys.argv.index("--")+1:])


def json_comparable(report):
    """Normalize sequence types and insignificant variation in independent float probes."""
    if isinstance(report,dict):
        return {key:json_comparable(value) for key,value in report.items()}
    if isinstance(report,(list,tuple)):
        return [json_comparable(value) for value in report]
    if isinstance(report,float):
        return round(report,6)
    return report


def verify_camera_source():
    source=LIB.parents[3]/"Sources/FeatherTide"
    camera=next(source.rglob("ThirdPersonRig.swift"))
    view=next(source.rglob("PlayfieldView.swift"))
    return {path.relative_to(LIB.parents[3]).as_posix():digest(path) for path in (camera,view)}

def main():
    args=parse()
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    check(not any(out.iterdir()),"Use a new output directory")
    local_wiring()
    if args.verify:
        candidate=args.verify.resolve()
        manifest=json.loads((candidate/"asset_manifest.json").read_text())
        qa=json.loads((candidate/"qa.json").read_text())
        for name,expected in manifest["files_sha256"].items():
            check(digest(candidate/name)==expected,name)
        bpy.ops.wm.open_mainfile(filepath=str(candidate/f"{STEM}.blend"))
        layers={name:bpy.data.objects[name] for name in NODES}
        scene=B["fresh_scene"]("ENV-015 | independent exact GLB reimport")
        returned, transport=CHECKPOINT["transport"](candidate,layers,manifest["textures"])
        lake=append("ENV-008",("LakeWide","LakeShore"))
        transport["topology"]=topology(returned[NODES[0]],[returned[NODES[1]]],lake["LakeShore"])
        transport["reassembled_lake"]=assemble_preview(scene,returned,lake["LakeShore"],lake["LakeWide"],out,"roundtrip",qa["CHR001_lower_edge_and_wingspan_BU"])
        observed, expected = json_comparable(transport), json_comparable(qa["roundtrip"])
        different=[key for key in observed if observed[key]!=expected[key]]
        if different:
            write(out/"difference.json",{"observed":observed,"expected":expected})
        check(not different,("independent measurements changed",different))
        write(out/"recheck.json",{"id":"ENV-015","result":"pass","transport":transport})
        return

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    gray_scene=bpy.context.scene
    gray_scene.name="ENV-015 | Graybox lake and flock"
    base=group("Asset source and live scatter",gray_scene.collection)
    source=append("ENV-002",("RestPatch",))["RestPatch"]
    lake=append("ENV-008",("LakeWide","LakeShore"))
    ground=build_terrain(base,source,lake["LakeShore"])
    neutral=B["paint"]("Graybox | contour water","819FA4")
    water=W["build_water"](base,NODES[1],ground,neutral)
    reed_mesh,scatter=add_reeds(base,ground)
    reeds=obj(base,NODES[2],reed_mesh)
    layers=dict(zip(NODES,(ground,water,reeds)))
    wing=wings_from_neutral()
    bpy.context.window.scene=gray_scene
    source_audit=topology(ground,[water],lake["LakeShore"])
    base.hide_render=True
    gray=assemble_preview(gray_scene,layers,lake["LakeShore"],lake["LakeWide"],out,"graybox",wing)
    if args.gray_only:
        write(out/"graybox_qa.json",{"topology":source_audit,"graybox":gray,"reed_scatter":scatter})
        return

    texture=patch_material(water,ground,out)
    ground_texture=landscape_texture(ground,out)
    CHECKPOINT["restore_mat_names"]([*layers.values()])
    export=B["fresh_scene"]("ENV-015 | Export LakesideRest")
    export_group=group("LakesideRest | independent terrain, shallows and reeds",export.collection)
    root=obj(export_group,ROOT,None)
    root["asset_id"]="ENV-015"
    root["lake_world_translation_BU"]=list(ORIGIN)
    root["water_level_BU"]=WATER
    root["forward_positive_y"]=True
    for item in layers.values():
        export_group.objects.link(item)
        item.parent=root
    textures=texture_records(layers,{"LakesideRest_ShallowWater":texture,"LakesideRest_GroundPaint":ground_texture})
    CHECKPOINT["choose_export"](root,layers,out)

    review=B["fresh_scene"]("ENV-015 | Material review in long lake")
    material=assemble_preview(review,layers,lake["LakeShore"],lake["LakeWide"],out,"review",wing)
    check(material["flight"]==gray["flight"],"phase changed route")
    for item in layers.values():base.objects.unlink(item)
    gray_scene.collection.children.unlink(base)
    # Keep the editable density and GN graph beside the three export layers.
    export.collection.children.link(base)
    bpy.context.window.scene=review
    bpy.ops.wm.save_as_mainfile(filepath=str(out/f"{STEM}.blend"))

    imported=B["fresh_scene"]("ENV-015 | Final GLB reimport")
    returned,reimport=CHECKPOINT["transport"](out,layers,textures)
    reimport["topology"]=topology(returned[NODES[0]],[returned[NODES[1]]],lake["LakeShore"])
    reimport["reassembled_lake"]=assemble_preview(imported,returned,lake["LakeShore"],lake["LakeWide"],out,"roundtrip",wing)
    check(json_comparable(reimport["reassembled_lake"]["stationary_flock"])==json_comparable(
        material["stationary_flock"]),"GLB changed stationary flock measurements")
    write(out/"qa.json",{"asset_id":"ENV-015","version":"v001","status":"needs_review",
        "graybox":gray,"topology":source_audit,"reed_scatter":scatter,"material_review":material,"roundtrip":reimport,
        "water_texture_bake":texture,"ground_texture_bake":ground_texture,"CHR001_lower_edge_and_wingspan_BU":wing,
        "pending":["S2 BeforeFork recognition and landing/rejoin in the active iOS build",
                   "Flock gameplay reachability, rest trigger, time and persistence, alpha sorting in RealityKit",
                   "USDZ, device readability and performance (iPhone / iPad)", "MAT-003 integration review"]})
    write(out/"asset_manifest.json",{"asset_id":"ENV-015","version":"v001","status":"needs_review",
        "chapter":"S2","priority":"P0","execution_order_1_based":26,"depends":["ENV-002/v001","ENV-003/v001","ENV-005/v001"],
        "context":["ENV-008/v001","ENV-010/v001","ANM-007/v001","CHR-001/v001"],
        "source_blends_sha256":{key:digest(src) for key,src in SOURCES.items()},
        "blend":f"{STEM}.blend","glb":GLB,"root":ROOT,"layers":NODES,"root_local_BU":[0,0,0],
        "placement_in_ENV008_BU":list(ORIGIN),"size_xy_BU":[10,10],"land_edge_vertex_pitch_BU":STEP,
        "land_edge_base_BU":0,"reference_water_BU":WATER,"axis_GLTF_from_Blender":["x","z","-y"],
        "camera_source_sha256":verify_camera_source(),
        "camera":{"distance_game_units":180,"pitch_parameter_rad":.48,"vertical_FOV_degrees":50,
                  "look_target_height_game_units":6,"goose_root_height_game_units":8,"frame_px":SIZE,
                  "review_scale_0_9900_BU_in_game_units":27.5},
        "draw_triangles":{name:len(item.data.polygons) for name,item in layers.items()},
        "edge_bindings":{"west":"reference forecourt","east":"ENV-008","north":"ENV-008","south":"ENV-008"},
        "textures":textures,"water_bake":texture,"ground_bake":ground_texture,
        "files_sha256":{p.relative_to(out).as_posix():digest(p) for p in sorted(out.rglob("*")) if p.is_file()},
        "rights":"Original project-authored geometry with internal assets and candidate materials."})


if __name__=="__main__":
    main()
