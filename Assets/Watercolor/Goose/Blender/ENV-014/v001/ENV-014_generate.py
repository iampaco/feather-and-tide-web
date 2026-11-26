"""Assemble a dry twelve-goose pad around a low-wind checkpoint basin in Blender."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path
import runpy
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
STEM = "ENV-014_checkpoint_a"
B = runpy.run_path(str(LIB/"ENV-001/v001/ENV-001_generate.py"))
F = runpy.run_path(str(LIB/"ENV-002/v001/ENV-002_generate.py"))
W = runpy.run_path(str(LIB/"ENV-003/v001/ENV-003_generate.py"))
R = runpy.run_path(str(LIB/"ENV-005/v001/ENV-005_generate.py"))
P = runpy.run_path(str(LIB/"ENV-010/v001/ENV-010_generate.py"))
GLB = "ENV-014_CheckpointA_Visual.glb"
ROOT = "CheckpointA_Visual"
NODES = ("CheckpointA_Ground","CheckpointA_Water","CheckpointA_Reeds")
SOURCES = {
    "ENV-001": LIB/"ENV-001/v001/ENV-001_terrain.blend",
    "ENV-002": LIB/"ENV-002/v001/ENV-002_wetland.blend",
    "ENV-003": LIB/"ENV-003/v001/ENV-003_wetland_water.blend",
    "ENV-005": LIB/"ENV-005/v001/ENV-005_reed_distribution.blend",
    "ENV-008": LIB/"ENV-008/v001/ENV-008_long_lake.blend",
    "ENV-009": LIB/"ENV-009/v001/ENV-009_far_ridges.blend",
    "ENV-010": LIB/"ENV-010/v001/ENV-010_short_pass.blend",
    "ANM-007": LIB/"ANM-007/v001/ANM-007_landing.blend",
}
check, obj, group, write, hash_file = (B[k] for k in ("check","obj","collection","write_json","file_hash"))
WATER, STEP, SIZE = B["WATER"], B["STEP"], B["GAME_SIZE"]
TOL = 1e-5
SEED = 14025
PAD = (-.65, -.04, 2.2, 3.2)
KEEP_OUT = (PAD, (-1.55,-12.5,4.15,10), (-.4,1.25,3.0,3.95))
COLS, ROWS = (-20,-10,0,10), (-20,-10,0)


def xy_bounds(item):
    return [[min(v.co[i] for v in item.data.vertices),max(v.co[i] for v in item.data.vertices)] for i in range(2)]


def label(mat):
    return mat.name.split(".")[0]


def source_meshes(key, names):
    return P["append"](SOURCES[key], names)


def make_tri(grouped, name, points, faces, mats, slots, uv, smooth=None):
    mesh = bpy.data.meshes.new(name + " | mesh")
    mesh.from_pydata(points,[],faces)
    mesh.update()
    for material in mats: mesh.materials.append(material)
    layer=mesh.uv_layers.new(name="UVMap")
    smooth=[False]*len(faces) if smooth is None else smooth
    for polygon,coords,material,is_smooth in zip(mesh.polygons,uv,slots,smooth,strict=True):
        polygon.use_smooth=is_smooth
        polygon.material_index=material
        for loop,coord in zip(polygon.loop_indices,coords,strict=True):
            layer.data[loop].uv=coord
    return obj(grouped,name,mesh)


def bake(items, parent, name, retain=None):
    """Combine the editable source objects into a single glTF mesh with per-corner attributes."""
    points,faces,slots,uvs,smooth,normals,mats=[],[],[],[],[],[],[]
    for tile in items:
        mesh=tile.data
        uv=mesh.uv_layers.active.data
        shift=len(points)
        points.extend(v.co+tile.location for v in mesh.vertices)
        mesh.calc_loop_triangles()
        for p in mesh.loop_triangles:
            if retain is not None and not retain(tile,p):
                continue
            mat=mesh.materials[p.material_index]
            if mat not in mats: mats.append(mat)
            slots.append(mats.index(mat))
            faces.append(tuple(shift+i for i in p.vertices))
            uvs.append([uv[i].uv.copy() for i in p.loops])
            smooth.append(mesh.polygons[p.polygon_index].use_smooth)
            normals.extend(mesh.corner_normals[i].vector.copy() for i in p.loops)
    item=make_tri(parent,name,points,faces,mats,slots,uvs,smooth)
    item.data.normals_split_custom_set(normals)
    return item


def merge_duplicate_materials(items):
    """Make identical named materials share one data block even when appended from two libraries."""
    names={}
    for item in items:
        for idx,mat in enumerate(item.data.materials):
            key=label(mat)
            texture=next((n.image for n in mat.node_tree.nodes if n.type=="TEX_IMAGE"),None)
            hash=sha256(texture.packed_file.data).hexdigest() if texture and texture.packed_file else None
            if key in names:
                old, digest=names[key]
                check(digest==hash,key)
                item.data.materials[idx]=old
            else:
                names[key]=(mat,hash)


def basin_height(x,y):
    # Irregular low banks taper back to the ENV-001 L connector before reaching the 10 BU border.
    shifted_x=x+.48*math.sin(.96*y)
    shifted_y=y-.34-.25*math.sin(.78*x)
    r=(abs(shifted_x/4.55)**2.75 + abs(shifted_y/4.14)**2.75)**(1/2.75)
    x_collar=B["smooth"]((4.73-abs(x))/.86)
    y_collar=B["smooth"]((4.73-abs(y))/.86)
    slope=B["smooth"]((1.09-r)/.46)
    silt=.03*math.sin(.93*x+1.13*y)*math.sin(1.2*y)
    return (-(.62+silt)*slope)*x_collar*y_collar


def basin(parent, mats):
    coords=[i*STEP-5 for i in range(17)]
    vertices=[(x,y,basin_height(x,y)) for y in coords for x in coords]
    faces=[]
    for y in range(16):
        for x in range(16):
            a=y*17+x
            b,c,d=a+1,a+18,a+17
            faces.extend(((a,b,c),(a,c,d)) if (x+y)%2 else ((a,b,d),(b,c,d)))
    uv=[tuple(((vertices[i][0]+5)/10,(vertices[i][1]+5)/10) for i in face) for face in faces]
    material_id=[]
    for face in faces:
        z=sum(vertices[i][2] for i in face)/3
        material_id.append(2 if z < -.23 else 1 if z < -.033 else 0)
    item=make_tri(parent,"CentralBasin",vertices,faces,mats,material_id,uv,[True]*len(faces))
    item.location=(-10,-10,0)
    item.data.normals_split_custom_set_from_vertices([(0,0,1) if max(abs(v[0]),abs(v[1]))==5 else (0,0,0)
                                                      for v in vertices])
    return item


def compose(parent, ground_mat, neutral):
    land=group("01 | ENV-001 Flat, ENV-002 and new central basin",parent)
    wet=group("02 | ENV-003 and the basin water sheet",parent)
    tile_refs=source_meshes("ENV-002",("StartMudflat","RestPatch","Flat"))
    water_refs=source_meshes("ENV-003",("ShallowPool_StartMudflat","ShallowPool_RestPatch"))
    land_tiles={}
    for x in COLS:
        for y in ROWS:
            if (x,y)==(-10,-10):continue
            kind = "StartMudflat" if (x,y)==(0,-10) else "RestPatch" if (x,y)==(0,0) else "Flat"
            land_tiles[x,y]=obj(land,f"{kind} tile {x},{y}",tile_refs[kind].data,(x,y,0))
    shore=basin(land,ground_mat)
    land_tiles[-10,-10]=shore
    pool=W["build_water"](wet,"Basin_Water",shore,neutral["water"])
    pool.location=shore.location
    waters=[pool]
    for name,y in (("StartMudflat",-10),("RestPatch",0)):
        water_name="ShallowPool_"+name
        waters.append(obj(wet,water_name+" | placement",water_refs[water_name].data,(0,y,0)))
    records={name:item for name,item in tile_refs.items()}
    return land_tiles,waters,records


def outline(item, axis, coord):
    return P["outline"](item.data,axis,coord,item.location)


def measure_joins(tiles):
    result=[]
    for (x,y),item in tiles.items():
        for (dx,dy),axis in (((10,0),0),((0,10),1)):
            peer=tiles.get((x+dx,y+dy))
            if peer:
                edge=(x if axis==0 else y)+5
                result.append(P["compare_edges"](outline(item,axis,edge),outline(peer,axis,edge),
                                                   f"{item.name} → {peer.name}"))
    check(len(result)==17, len(result))
    return result


def add_reeds(root, items):
    sub=group("03 | Reeds (live Geometry Nodes and prototype library)",root)
    source_reeds=R["PLANTS"]["REEDS"]
    prototypes=source_meshes("ENV-005",source_reeds)
    for name,reed in prototypes.items():
        sub.objects.link(reed)
        reed.hide_set(True)
        reed.hide_render=True
    active=[tile for (x,y),tile in items.items() if (x,y) in [(-20,-10),(-10,-10),(-10,0),
                                                              (0,-10),(0,0),(10,0),(-10,-20)]]
    points, faces, edges=[],[],[]
    for tile in active:
        mesh=tile.data
        start=len(points)
        points.extend(v.co+tile.location for v in mesh.vertices)
        faces.extend(tuple(start+i for i in p.vertices) for p in mesh.polygons)
        edges.extend(R["contour"](mesh,tile.location))
    bed=bpy.data.meshes.new("Editable shoreline weights")
    bed.from_pydata(points,[],faces)
    bed.update()
    weight=bed.attributes.new(R["ATTR_DENSITY"],"FLOAT","POINT")
    values=[]
    for p in points:
        d=R["distance_to_segments"](p.xy,edges)
        taper=B["smooth"]((3.8-p.y)/1.8)
        values.append(math.exp(-(d/1.22)**2)*taper)
    weight.data.foreach_set("value",values)
    carrier=obj(sub,"CheckpointA | Editable reed bed",bed)
    local_graph=R["make_graph"]
    local_graph.__globals__["KEEP_OUT"]=KEEP_OUT
    graph=local_graph(prototypes)
    graph.name="CheckpointA | ENV-005 shoreline scatter"
    mod=R["modify"](carrier,graph,"ShoreEdge")
    for name,data in (("Seed",SEED),("Density per BU²",1.97),("Interior fraction",.055),("Wind angle radians",.034)):
        R["set_input"](mod,name,data)
    positions=R["extract"](carrier)
    check(positions==R["extract"](carrier),"identical seed")
    mesh=R["freeze"](carrier)
    mesh.name="CheckpointA | Frozen shoreline"
    mesh.calc_loop_triangles()
    expected=sum(len(list(prototypes.values())[p[3]].data.polygons) for p in positions)
    separation=min(max(abs(v.co.x-cx)-rx,abs(v.co.y-cy)-ry)
                        for v in mesh.vertices for cx,cy,rx,ry in KEEP_OUT)
    check(separation>=.08 and len(mesh.loop_triangles)==expected,(separation,len(mesh.loop_triangles),expected))
    check(min(p[2] for p in positions) >= WATER+.02099,"Reeds in water")
    counts=Counter(list(prototypes)[p[3]] for p in positions)
    check(len(counts)==6,counts)
    carrier.hide_render=True
    carrier.hide_set(True)
    return mesh, {"instances":len(positions),"prototypes":dict(counts),"triangles":expected,"seed":SEED,
                  "min_mesh_vertex_buffer_to_exclusion_BU":separation,"min_root_height_above_water_BU":
                  min(p[2] for p in positions)-WATER,"exclusion_boxes_center_xy_half_extents_BU":KEEP_OUT}


def ray_tree(items):
    vertices, faces=[],[]
    for item in items:
        start=len(vertices)
        vertices.extend(v.co+item.location for v in item.data.vertices)
        faces.extend(tuple(start+i for i in p.vertices) for p in item.data.polygons)
    return BVHTree.FromPolygons(vertices,faces,all_triangles=False)


def ground_at(tree,x,y):
    point,*_=tree.ray_cast(Vector((x,y,4)),Vector((0,0,-1)),6)
    check(point is not None,(x,y))
    return point.z


def verify_water(items, land):
    ground=ray_tree(land)
    out={}
    for water in items:
        area=0.
        penetration=0.
        for triangle in water.data.polygons:
            check(triangle.area>0 and triangle.normal.z>.999,water.name)
            area+=triangle.area
            for p in [triangle.center]+[water.data.vertices[i].co for i in triangle.vertices]:
                v=p+water.location
                check(abs(v.z-WATER)<1e-6,v)
                penetration=max(penetration,ground_at(ground,v.x,v.y)-WATER)
        check(penetration<1e-6,(water.name,penetration))
        out[water.name]={"triangles":len(water.data.polygons),"wet_area_BU2":area,"max_dry_penetration_BU":penetration}
    return out


def traverse(ground, reeds, span, height):
    floor=ray_tree(ground)
    obstructions=ray_tree([reeds])
    min_clear=math.inf
    count=0
    for direction in (-1,1):
        # Test three separated paths through the staggered landing rows.
        for center in (-1.48, 0.,1.48):
            for row in range(83):
                y=(-22.0+row*.25) if direction==-1 else (-3.0+row*.09375)
                if y>4.69:continue
                offset=-2.4*(1-B["smooth"]((y+21)/18)) if direction==-1 else 0.
                for side in (-1,0,1):
                    x=center+offset+side*span/2
                    floor_z=ground_at(floor,x,y)
                    min_clear=min(min_clear,height-floor_z)
                    hit,*_=obstructions.ray_cast(Vector((x,y,-.19)),Vector((0,0,1)),1.7)
                    check(hit is None,("plant in aircraft corridor",x,y))
                    count+=1
    check(min_clear>.08,(min_clear,count))
    return {"positions_checked":count,"min_CHR001_neutral_lower_bound_clearance_BU":min_clear,
            "root_lane_x_BU":[-1.48,0.,1.48],"wing_span_BU":span,"measured_tip_height_BU":height,
            "method":"Downward land and upward reed BVH rays for 3 lateral paths, their center and both wingtips."}


def populate_flock(parent, terrain):
    mesh, points, soles = F["load_standing_mesh"](parent)
    source = json.loads((SOURCES["ENV-002"].parent/"qa.json").read_text())
    slots=source["graybox"]["modules"]["RestPatch"]["flock_all_1x"]["birds"]
    tree=F["land_mesh"](terrain.data)
    bounds, result, birds=[],[],[]
    for i,slot in enumerate(slots):
        xy=slot["xy_BU"]
        yaw=math.radians(slot["yaw_degrees"])
        hull, report=F["place"](tree,points,soles,xy,yaw,1)
        goose=obj(parent,f"Review resting goose {i+1:02}",mesh,(*xy,report["root_z_BU"]))
        goose.rotation_euler.z=yaw
        birds.append(goose)
        bounds.append(hull)
        result.append(report)
    gap=min(F["interval_separation"](first,second) for first,second in combinations(bounds,2))
    check(len(birds)==12 and gap>.03,gap)
    report={"goose_count":len(birds),"pair_count":66,"min_hull_gap_BU":gap,"slots":result,
            "worst_foot_contact_gap_BU":max(foot["contact_gap_BU"] for measurement in result for foot in measurement["feet"]),
            "root_units":"BU", "pose":"ANM-007 Land_Mudflat frame 81, 12 birds at 1x"}
    return birds, report


def camera_pack(scene):
    studio=B["studio"](scene,scene.collection)
    key=next(o for o in studio.objects if o.type=="LIGHT")
    key.data.color=(1.,.86,.65)
    key.data.energy=1.40
    key.rotation_euler=Vector((-.51,.48,-1)).to_track_quat("-Z","Y").to_euler()
    scene.world.node_tree.nodes.get("Background").inputs["Color"].default_value=(.63,.70,.72,1)
    sky=B["paint"]("Review horizon | mist blue","B0C2C9",emission=True)
    B["simple_mesh"](studio,"Warm horizon backdrop",[(-220,180,-3),(220,180,-3),(220,180,80),(-220,180,80)],
                     [(0,1,2,3)],sky)
    top=B["camera"](studio,"Checkpoint map | top",(-5,-10,72),(-5,-10,0),45)
    approach=B["camera"](studio,"Current rig | incoming flock",(0,0,1),(0,1,0))
    B["follow"](approach,(-7.1,-16.1),Vector((.13,.991514)).normalized())
    rest=B["camera"](studio,"Current rig | rest bank",(0,0,1),(0,1,0))
    B["follow"](rest,(-.46,-3.1),Vector((0,1)))
    checkpoint=B["camera"](studio,"Current rig | checkpoint A",(0,0,1),(0,1,0))
    B["follow"](checkpoint,(0,0),Vector((0,1)))
    return top,approach,rest,checkpoint


def layout_review(scene, flat):
    # A review apron continues the four edge rows; the three actual GLB layer meshes stay independent.
    extra=group("Review frame continuation",scene.collection)
    for y in range(-30,101,10):
        for x in range(-70,71,10):
            if x in COLS and y in ROWS:continue
            obj(extra,f"Flat apron {x},{y}",flat.data,(x,y,0))
    return extra


def flock_pixels(scene,camera,birds):
    scene.render.resolution_x,scene.render.resolution_y=SIZE
    bpy.context.view_layer.update()
    boxes=[]
    for goose in birds:
        coordinates=[world_to_camera_view(scene,camera,goose.matrix_world @ v.co) for v in goose.data.vertices]
        check(all(p.z>0 and 0<p.x<1 and 0<p.y<1 for p in coordinates),goose.name)
        boxes.append({"pixel_width":(max(p.x for p in coordinates)-min(p.x for p in coordinates))*SIZE[0],
                  "pixel_height":(max(p.y for p in coordinates)-min(p.y for p in coordinates))*SIZE[1]})
    return boxes


def water_source():
    return W["source_materials"]()


def textures_in(layers):
    result={}
    for item in layers.values():
        for material in item.data.materials:
            tex=[n.image for n in material.node_tree.nodes if n.type=="TEX_IMAGE"
                 and n.image and n.image.packed_file]
            check(len(tex)>=1,(item.name,material.name))
            hash=sha256(tex[0].packed_file.data).hexdigest()
            check(all(sha256(value.packed_file.data).hexdigest()==hash for value in tex),material.name)
            path=bpy.path.basename(tex[0].filepath)
            result[label(material)]={"filename":path,"sha256":hash,
                "dimensions":list(tex[0].size),
                "alpha":"BLEND" if item.name==NODES[1] else "OPAQUE"}
    return result


def choose_export(root, layers, output):
    bpy.ops.object.select_all(action="DESELECT")
    root.select_set(True)
    for tile in layers.values():tile.select_set(True)
    bpy.context.view_layer.objects.active=root
    status=bpy.ops.export_scene.gltf(filepath=str(output/GLB),export_format="GLB",use_selection=True,export_yup=True,
                                      export_animations=False,export_extras=True)
    check(status=={"FINISHED"},status)


def signature(mesh):
    mesh.calc_loop_triangles()
    uv=mesh.uv_layers.active.data
    result=defaultdict(list)
    for p in mesh.loop_triangles:
        corners=[]
        for i in p.loops:
            pt=mesh.vertices[mesh.loops[i].vertex_index].co
            corners.append((tuple(round(v,5) for v in pt),tuple(round(v,5) for v in uv[i].uv),
                            mesh.corner_normals[i].vector.copy()))
        start=min(range(3), key=lambda i: corners[i][:2])
        corners=corners[start:]+corners[:start]
        key=(label(mesh.materials[p.material_index]),tuple((r[0],r[1]) for r in corners))
        result[key].append([r[2] for r in corners])
    return result


def transport(output, layers, original_textures):
    doc,blob=B["glb_chunks"](output/GLB)
    gltf_nodes={n["name"]:n for n in doc["nodes"]}
    check(set(gltf_nodes)=={ROOT,*NODES},list(gltf_nodes))
    check(set(gltf_nodes[ROOT]["children"])=={i for i,n in enumerate(doc["nodes"]) if n["name"] in NODES},gltf_nodes[ROOT])
    for n in gltf_nodes.values():
        check(n.get("translation",[0]*3)==[0]*3 and n.get("scale",[1]*3)==[1]*3 and
              n.get("rotation",[0,0,0,1])==[0,0,0,1],n)
    payload={}
    for mat in doc["materials"]:
        n=mat["name"].split(".")[0]
        tex=doc["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
        image=doc["images"][tex["source"]]
        v=doc["bufferViews"][image["bufferView"]]
        start=v.get("byteOffset",0)
        digest=sha256(blob[start:start+v["byteLength"]]).hexdigest()
        spec=original_textures[n]
        check(digest==spec["sha256"] and mat.get("alphaMode","OPAQUE")==spec["alpha"],(mat,digest,spec))
        payload[n]=digest
    old=set(bpy.data.objects)
    check(bpy.ops.import_scene.gltf(filepath=str(output/GLB),merge_vertices=False,import_pack_images=True)=={"FINISHED"},GLB)
    loaded={o.name.split(".")[0]:o for o in set(bpy.data.objects)-old}
    check(set(loaded)=={ROOT,*NODES},list(loaded))
    record={}
    for name in NODES:
        a,b=layers[name],loaded[name]
        check(b.parent is loaded[ROOT] and b.location.length<TOL and tuple(b.scale)==(1,1,1),name)
        before,after=signature(a.data),signature(b.data)
        check(before.keys()==after.keys(),(name,len(before),len(after)))
        normal=0.
        for key,v in before.items():
            peers=after[key]
            check(len(v)==len(peers),(name,key))
            normal=max(normal,*(min(max(B["angle"](x,y) for x,y in zip(first,second)) for second in peers) for first in v))
        check(normal<.12,(name,normal))
        acc=[doc["accessors"][p["attributes"]["POSITION"]] for p in doc["meshes"][gltf_nodes[name]["mesh"]]["primitives"]]
        raw=[[min(p["min"][i] for p in acc),max(p["max"][i] for p in acc)] for i in range(3)]
        x,y,z=B["tile_box"](a.data)
        want=[x,z,[-y[1],-y[0]]]
        check(max(abs(a-b) for a,b in zip(sum(want,[]),sum(raw,[])))<TOL,(name,want,raw))
        record[name]={"triangles":len(b.data.polygons),"max_normal_delta_deg":normal,
                      "axis_checked_gltf_xyz_bounds_BU":raw}
    return {name:loaded[name] for name in NODES},{"layer_geometry":record,"identical_GLTF_embedded_PNG_SHA256":payload}


def mark_hints(parent):
    markers={}
    for name,p in (("Checkpoint_A",(0,0,0)),("Dry_Pad",(-.65,-.04,0)),
                   ("Pass_Exit",(-9.15,12,0)),("Lake_Exit",(11.5,12,-.18))):
        item=obj(parent,name,None,p)
        item.empty_display_type="PLAIN_AXES"
        item.empty_display_size=.65
        markers[name]=list(p)
    return markers


def show_fork(scene, root, camera, bird, ground_layer, reed_layer, flat, output):
    """Context uses the real sibling route meshes and review apron clipped away from the checkpoint."""
    extra=group("Review | S2 routes at shared checkpoint origin",root)
    pass_parts=source_meshes("ENV-010",P["NAMES"])
    lake=source_meshes("ENV-008",("LakeWide","LakeShore"))
    for item in (*pass_parts.values(),*lake.values()):extra.objects.link(item)
    guide=source_meshes("ENV-010",["Review | path at source game-plane height"])
    for item in guide.values():extra.objects.link(item)
    mountains=P["far_ridges"](extra,SOURCES["ENV-009"])
    for mountain in mountains.values():
        mountain.location.z-=.4
    # Cover only unoccupied snap cells. Build the connector strips on the lake phase.
    for yi in range(-30,201,10):
        for x in range(-80,-20,10):
            obj(extra,f"West apron {x},{yi}",flat.data,(x,yi,0))
    grass=next(m for m in flat.data.materials if label(m)=="GrassFlat")
    pre=[(-25,-1.5,5,10),(-1.5,-1,5,200),
         (-25,-21.5,10,50),(-25,-1.5,50,200),(-1,160,63,200),
         (15,160,-30,4.9999)]
    for i,(xl,xr,yl,yr) in enumerate(pre):
        item=B["rectangle"](extra,"Review connecting apron "+str(i),xl,xr,yl,yr,0,grass)
        uv=item.data.uv_layers.new(name="TerrainUV")
        for corner in item.data.loops:
            x,y,_=item.data.vertices[corner.vertex_index].co
            uv.data[corner.index].uv=((x+5)/10,(y+5)/10)
    lake_shore=lake["LakeShore"]
    # Clip the dry lake apron behind Y = 5, leaving the checkpoint export intact.
    vertices,faces,slots,uvs=[],[],[],[]
    uv=lake_shore.data.uv_layers.active
    for p in lake_shore.data.polygons:
        v=[lake_shore.data.vertices[i].co for i in p.vertices]
        if max(q.y for q in v)<=5:continue
        # Input ENV-008 has an exact y=5 row. Reject any interior crossing rather than overlap.
        check(min(q.y for q in v)>=5-1e-6,("lake review border",p.index))
        a=len(vertices)
        vertices.extend(v)
        faces.append(tuple(range(a,a+len(v))))
        slots.append(p.material_index)
        uvs.append([uv.data[i].uv.copy() for i in p.loop_indices])
    lake_shore.hide_render=True
    lake_shore.hide_set(True)
    clipped=make_tri(extra,"LakeShore beyond checkpoint",vertices,faces,list(lake_shore.data.materials),slots,uvs)
    # Retain the actual inlet water where it falls above the clipped lake terrain.
    lake_wide=lake["LakeWide"]
    pts,fs,used_uv=[],[],[]
    for t in lake_wide.data.polygons:
        coords=[lake_wide.data.vertices[i].co.copy() for i in t.vertices]
        if max(v.y for v in coords)<=5:continue
        check(min(v.y for v in coords)>=5-1e-6,("lake water cut",t.index))
        a=len(pts)
        pts.extend(coords)
        fs.append(tuple(range(a,a+len(coords))))
        used_uv.append([lake_wide.data.uv_layers.active.data[i].uv.copy() for i in t.loop_indices])
    lake_wide.hide_render=True
    lake_wide.hide_set(True)
    make_tri(extra,"LakeWide beyond checkpoint",pts,fs,list(lake_wide.data.materials),[0]*len(fs),used_uv)
    small=source_meshes("ENV-003",("ShallowPool_RestPatch",))["ShallowPool_RestPatch"]
    extra.objects.link(small)
    small.location=(4,10,0)
    # Upper frame visibility uses the locked rig with no pullback.
    B["pose_at"](camera,bird,(0,0),Vector((0,1)))
    scene.render.resolution_x,scene.render.resolution_y=SIZE
    bpy.context.view_layer.update()
    check(ground_layer.name.startswith("CheckpointA_Ground"),ground_layer.name)
    visibility_meshes=[ground_layer,*pass_parts.values(),clipped,reed_layer]
    tree=ray_tree(visibility_meshes)
    y=21.5
    targets={"pass_opening":[(P["center"](y)+i*5.2/12-2.6,y,.09) for i in range(13)],
             "lake_forebay":[(x,y,-.14) for y in (11,12,13) for x in (11,13,14)],
             "dry_lake_rest":[(x,y,.045) for y in (7.4,8.55,10.1) for x in (2.8,3.8,4.9)]}
    report={}
    for name,points in targets.items():
        xs=[]
        for p in points:
            endpoint=Vector(p)
            co=world_to_camera_view(scene,camera,endpoint)
            d=endpoint-camera.location
            hit,*_=tree.ray_cast(camera.location,d.normalized(),d.length-.002)
            if hit is None and co.z>0 and 0<co.x<1 and 0<co.y<1:xs.append(co.x*SIZE[0])
        check(len(xs)==len(points),(name,len(xs),len(points)))
        report[name]={"unoccluded":len(xs),"sampled":len(points),"x_px":[min(xs),max(xs)]}
    B["render"](scene,camera,output,"preview_fixed_rear_fork",SIZE,28)
    return report,extra


def restore_mat_names(items):
    # Canonical glTF labels keep packed texture provenance readable.
    merge_duplicate_materials(items)
    first={}
    for asset in items:
        for material in asset.data.materials:
            first.setdefault(label(material),material)
    for name,wanted in first.items():
        old=bpy.data.materials.get(name)
        if old and old!=wanted:
            old.user_remap(wanted)
            bpy.data.materials.remove(old,do_unlink=True)
        wanted.name=name


def stage_lights(scene, flat, ground, layers, assets, out, phase):
    top,approach,rest,checkpoint=camera_pack(scene)
    aprons=layout_review(scene, flat)
    route=group("Review scale markers and flock",scene.collection)
    neutral=B["add_goose"](route)
    points=neutral.data.vertices
    span=max(v.co.x for v in points)-min(v.co.x for v in points)
    tip_height=8/B["SCALE"]+min(v.co.z for v in points)
    birds,flock=populate_flock(route,assets["RestPatch"])
    for bird in birds:bird.hide_render=True
    x,y=-7.1,-16.1
    B["pose_at"](approach,neutral,(x,y),Vector((.13,.991514)).normalized())
    if phase!="roundtrip":
        B["render"](scene,approach,out,phase+"_fixed_rear_incoming",SIZE,19)
    neutral.hide_render=True
    for bird in birds:bird.hide_render=False
    B["render"](scene,top,out,phase+"_top",(1100,1100),18)
    B["render"](scene,rest,out,phase+"_fixed_rear_rest",SIZE,22)
    flock["fixed_rear_projection_per_bird"]=flock_pixels(scene,rest,birds)
    for bird in birds:bird.hide_render=True
    neutral.hide_render=False
    fork=None
    if phase=="preview":
        for item in aprons.objects:
            item.hide_render=True
            item.hide_set(True)
        fork,overlays=show_fork(scene,scene.collection,checkpoint,neutral,ground,layers[NODES[2]],flat,out)
    B["set_preview_workspace"](scene,checkpoint if phase=="preview" else rest)
    scene.render.filepath="//checkpoint_a.png"
    return {"flight":traverse([ground],layers[NODES[2]],span,tip_height),"flock":flock,"fork":fork}


def named_source_map(textures):
    take={}
    for asset,path in SOURCES.items():
        for p in (path.parent/"textures").glob("*.png"):
            take.setdefault(hash_file(p),[]).append(p.relative_to(LIB).as_posix())
    for tag in ("MAT-001","MAT-003","MAT-004"):
        for p in (LIB/tag/"v001/textures").glob("*.png"):
            take.setdefault(hash_file(p),[]).append(p.relative_to(LIB).as_posix())
    for name,v in textures.items():
        digest=v["sha256"]
        v["repo_relative_from_Blender"] = take.get(digest,[])
        if v["filename"].startswith("ft_goose_env_water_rest_patch_basecolor_alpha"):
            check(v["repo_relative_from_Blender"],v)
        if name=="CheckpointBasinWater":
            v["filename"]="ft_goose_env_water_central_basin_basecolor_alpha.png"
            v["generated_path"]="textures/"+v["filename"]
        else:
            check(v["repo_relative_from_Blender"],(name,v))
    return textures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    check(not any(output.iterdir()),"Use a clean temporary directory.")
    if args.verify:
        target=args.verify.resolve()
        bpy.ops.wm.open_mainfile(filepath=str(target/f"{STEM}.blend"))
        m=json.loads((target/"asset_manifest.json").read_text())
        qa=json.loads((target/"qa.json").read_text())
        layers={key:bpy.data.objects[key] for key in NODES}
        B["fresh_scene"]("Independent reimport")
        returned,results=transport(target,layers,m["textures"])
        results["water"]=verify_water([returned[NODES[1]]],[returned[NODES[0]]])
        parameters=qa["material_review"]["flight"]
        results["flight"]=traverse([returned[NODES[0]]],returned[NODES[2]],parameters["wing_span_BU"],
                                   parameters["measured_tip_height_BU"])
        check(results==qa["roundtrip"],(results.keys(),qa["roundtrip"].keys()))
        write(output/"recheck.json",{"result":"pass",**results})
        return

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    assembly=bpy.context.scene
    assembly.name="ENV-014 | Tile layout and live reeds"
    base=group("CheckpointA | Editable source groups",assembly.collection)
    neutral={"water":B["paint"]("Graybox water","879FA2"),
             "ground":B["paint"]("Graybox plateau","A3ADA4"),
             "reed":B["paint"]("Graybox silhouettes","718181")}
    ground_mats,_=B["load_materials"]()
    items,waters,assets=compose(base,[ground_mats[n] for n in ("GrassFlat","MudBank","ShallowMargin")],neutral)
    joins=measure_joins(items)
    water=verify_water(waters,list(items.values()))
    reed_mesh,scatter=add_reeds(base,items)
    preview_scene=B["fresh_scene"]("ENV-014 | Graybox measurements")
    gray_group=group("Graybox renderable parts",preview_scene.collection)
    for name,sources,mat in ((NODES[0],items.values(),neutral["ground"]),(NODES[1],waters,neutral["water"])):
        tile=bake(sources,gray_group,name+" gray")
        for i in range(len(tile.data.materials)):tile.data.materials[i]=mat
    gray_reeds=obj(gray_group,NODES[2]+" gray",reed_mesh.copy())
    for i in range(len(gray_reeds.data.materials)):gray_reeds.data.materials[i]=neutral["reed"]
    gray_ground=gray_group.objects[NODES[0]+" gray"]
    gray_layers={key:gray_group.objects[key+" gray"] for key in NODES}
    gray_flat=obj(gray_group,"Gray flat donor",assets["Flat"].data.copy())
    for idx in range(len(gray_flat.data.materials)):gray_flat.data.materials[idx]=neutral["ground"]
    gray_flat.hide_render=True
    gray=stage_lights(preview_scene,gray_flat,gray_ground,gray_layers,assets,output,"graybox")
    bpy.data.scenes.remove(preview_scene)

    bpy.context.window.scene=assembly
    (output/"textures").mkdir()
    # Generate a depth-baked alpha map using the same contour recipe as ENV-003.
    new_mats=water_source()
    basin_bake=W["shade"]("ShallowPool_StartMudflat",waters[0],items[-10,-10],new_mats,output)
    old=output/basin_bake["path"]
    new=old.with_name("ft_goose_env_water_central_basin_basecolor_alpha.png")
    old.rename(new)
    basin_mat=waters[0].data.materials[0]
    basin_mat.name="CheckpointBasinWater"
    for n in basin_mat.node_tree.nodes:
        if n.type=="TEX_IMAGE" and n.image:
            if n.image.name.endswith("start_mudflat_basecolor_alpha.png"):
                n.image.filepath="//textures/"+new.name
                n.image.name=new.name
    restore_mat_names([*items.values(),*waters])
    baked=B["fresh_scene"]("ENV-014 | Baked CheckpointA_Visual")
    drawn=group("Three independent draw layers",baked.collection)
    root=obj(drawn,ROOT,None)
    root["asset_role"]="Visual geometry only"
    root["heading_positive_y"]=True
    layers={NODES[0]:bake(items.values(),drawn,NODES[0]),NODES[1]:bake(waters,drawn,NODES[1]),
            NODES[2]:obj(drawn,NODES[2],reed_mesh)}
    for item in layers.values():item.parent=root
    original_textures=textures_in(layers)
    choose_export(root,layers,output)
    review=B["fresh_scene"]("ENV-014 | Fixed rear and route context")
    review_geometry=group("Checkpoint A surfaces for review",review.collection)
    shown={name:obj(review_geometry,name+" | review",item.data) for name,item in layers.items()}
    marks=mark_hints(group("Review landmarks",review.collection))
    matured=stage_lights(review,assets["Flat"],shown[NODES[0]],shown,assets,output,"preview")
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{STEM}.blend"))

    final=B["fresh_scene"]("ENV-014 | Reimport checkpoint")
    restored,after=transport(output,layers,original_textures)
    after["water"]=verify_water([restored[NODES[1]]],[restored[NODES[0]]])
    verification=stage_lights(final,assets["Flat"],restored[NODES[0]],restored,assets,output,"roundtrip")
    after["flight"]=verification["flight"]
    check(verification["flight"]==matured["flight"],"route clearance changed")
    write(output/"qa.json",{"id":"ENV-014","version":"v001","status":"needs_review","graybox":gray,
         "snapped_tile_joins":joins,"layer_water_proof":water,"reed_scatter":scatter,
         "material_review":matured,"roundtrip":after,"checkpoint_review_anchors_BU":marks,
         "main_pool_area_BU2":next(row["wet_area_BU2"] for name,row in water.items() if name=="Basin_Water"),
         "pending":["S1/S2 runtime landing, resource replenishment, persistence and retry, choice of both paths.",
                    "Transparency sorting, integration of motion, USDZ / RealityKit and iPhone/iPad."]})
    write(output/"asset_manifest.json",{"id":"ENV-014","version":"v001","status":"needs_review",
        "execution_order_1_based":25,"depends":["ENV-002/v001","ENV-003/v001","ENV-005/v001"],
        "source_blends_sha256":{name:hash_file(p) for name,p in SOURCES.items()},
        "glb":GLB,"blender":f"{STEM}.blend","root":ROOT,"root_blender_BU":[0,0,0],"forward_blender":[0,1,0],
        "glb_xyz_from_blender":["x","z","-y"],"glb_layers":list(NODES),"reference_water_BU":WATER,
        "geometry_review_extent_xy_BU":[[-25,15],[-25,5]],"geometry_node_seed":SEED,
        "textures":named_source_map(original_textures),"basin_texture_source":basin_bake["mat004_source"],
        "rights":"Project-authored geometry and selected reuse of internal wetland assets. No third-party inputs."})


if __name__=="__main__":
    main()
