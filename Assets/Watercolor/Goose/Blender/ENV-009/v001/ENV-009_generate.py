"""Build the three standalone FarRidge mesh assets and their fixed-camera review."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import runpy
import struct
import sys
import zlib

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np

HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
MAT = LIBRARY / "MAT-003/v001"
BASE = runpy.run_path(str(LIBRARY / "ENV-001/v001/ENV-001_generate.py"))
check, group, add = (BASE[key] for key in ("check", "collection", "obj"))
file_hash, write = BASE["file_hash"], BASE["write_json"]
STEM = "ENV-009_far_ridges"
FOLD = 42
SIZE = (852, 393)
DATA = {
    "FarRidge_A": {"size": (37., 2.20, 1.72), "tone": ("9DABB9", "BCC4CF"),
                   "knots": (.09,.35,.30,.71,.91,.67,.58,.38,.32,.51,.79,.70,.44,.52,.33,.08)},
    "FarRidge_B": {"size": (53., 2.65, 2.72), "tone": ("ABB7C7", "C3CAD9"),
                   "knots": (.07,.26,.48,.36,.67,.53,.45,.50,.72,.86,.75,.62,.85,.98,.66,.09)},
    "FarRidge_C": {"size": (78., 3.20, 4.10), "tone": ("B6B6CB", "D4D3E0"),
                   "knots": (.06,.33,.49,.72,.64,.86,.98,.81,.58,.66,.89,.75,.55,.48,.35,.08)},
}
PLACEMENTS = (
    ("A left", "FarRidge_A", (-25.0,38.0,0.), (1.12,1.0,.85)),
    ("A right", "FarRidge_A", (25.0,43.0,0.), (1.10,.95,.79)),
    ("B middle", "FarRidge_B", (1.0,49.0,0.), (1.32,1.0,.61)),
    ("C far", "FarRidge_C", (4.0,62.0,0.), (1.60,1.0,.445)),
)
VIEWS = ((-1.1,-.7,-.055), (0.1,3.5,.012), (.75,7.5,.083))
FLIGHT_END_Y = 21.6


def smooth_profile(knots, u):
    x = u * (len(knots)-1)
    j = min(int(x), len(knots)-2)
    t = x-j
    a,b,c,d = [knots[min(max(i,0),len(knots)-1)] for i in (j-1,j,j+1,j+2)]
    return .5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t)


def make_ridge(parent, name, material):
    definition = DATA[name]
    width, half_depth, height = definition["size"]
    knots = definition["knots"]
    vertices, uvs, polygons = [], [], []
    # Stagger the lower ledges so the face catches quiet broad tones and has no vertical card edges.
    ring_spec = ((-.99,-.09),(-.76,.20),(-.43,.57), (0.,1.),(.45,.57),(.83,.17),(.98,-.09))
    for col in range(FOLD + 1):
        u = col / FOLD
        x = (u - .5) * width
        z = height * smooth_profile(knots,u)
        bend = half_depth * (.09*math.sin(u*math.tau + .7)+.12*math.sin(u*8.1))
        for i,(y_percent,z_percent) in enumerate(ring_spec):
            wobble = math.sin(u*12.9+i*1.74) * math.sin(math.pi*u)
            y = bend + half_depth*(y_percent + .09*wobble)
            floor = -.16
            ceiling = z*z_percent if z_percent>0 else floor
            level = ceiling + .056 * wobble*height if i in (1,2,4,5) else ceiling
            vertices.append((x,y,level))
            v = .06 + .86 * max(0,level)/height
            uvs.append((.02+.96*u,v))
    stride = len(ring_spec)
    for i in range(FOLD):
        for j in range(stride):
            a = i*stride+j
            b = i*stride+(j+1)%stride
            c,d = b+stride,a+stride
            polygons.extend(((a,d,c),(a,c,b)) if (i+j)%2 else ((a,d,b),(d,c,b)))
    for r in (0,FOLD):
        offset=r*stride
        for j in range(1,stride-1):
            face=(offset,offset+j,offset+j+1)
            polygons.append(face if r==0 else face[::-1])
    tile=BASE["simple_mesh"](parent,name,vertices,polygons,material)
    uv=tile.data.uv_layers.new(name="RidgeWash")
    # Smooth broad faces while keeping a softened, geometrically closed crest.
    for polygon in tile.data.polygons:
        polygon.use_smooth=True
        for corner in polygon.loop_indices:
            uv.data[corner].uv=uvs[tile.data.loops[corner].vertex_index]
    tile["layer"]="backdrop"
    tile["pivot"]="center at ground datum"
    tile["runtime_collision"]="none; backdrop placement outside flight bounds"
    tile.asset_mark()
    tile.asset_data.description="Muted geological backdrop | non-playable distant ridge"
    return tile


def audit(tile):
    mesh=tile.data
    check(tile.type=="MESH" and tile.parent is None and tile.location.length<1e-6
          and tuple(tile.scale)==(1,1,1),tile.name)
    counts=Counter()
    for p in mesh.polygons:
        check(len(p.vertices)==3 and p.area>.00001,(tile.name,p.index))
        for pair in p.edge_keys: counts[tuple(sorted(pair))]+=1
    coordinates=[v.co for v in mesh.vertices]
    volume=0.
    for p in mesh.polygons:
        a,b,c=[mesh.vertices[i].co for i in p.vertices]
        volume+=a.dot(b.cross(c))/6
    # A closed silhouette has neither transparent cutouts nor stray terrain polygons.
    check(set(counts.values())=={2} and volume>0,(tile.name,volume,Counter(counts.values())))
    return {"triangles":len(mesh.polygons),"vertices":len(coordinates),
            "bounds_BU":[[min(p[k] for p in coordinates),max(p[k] for p in coordinates)] for k in range(3)],
            "enclosed_volume_BU3":volume}


def palette_maps(output):
    source=MAT/"textures/ft_goose_mat_mountain_rock_basecolor.png"
    manifest=json.loads((MAT/"asset_manifest.json").read_text())
    expected=manifest["files"]["textures/"+source.name]
    check(file_hash(source)==expected,source)
    source_image=bpy.data.images.load(str(source),check_existing=False)
    src=np.empty(1024*1024*4,dtype=np.float32)
    source_image.pixels.foreach_get(src)
    bpy.data.images.remove(source_image)
    pixels=src.reshape((1024,1024,4))[96:864:2,96:864:2,:3]
    check(pixels.shape==(384,384,3),pixels.shape)
    graytones=pixels @ np.array((.2126,.7152,.0722))
    grain=(graytones-graytones.mean())*.30
    y,x=np.meshgrid(np.linspace(0.,1.,384),np.linspace(0.,1.,384),indexing="ij")
    output.joinpath("textures").mkdir()
    materials={}
    for key,definition in DATA.items():
        a,b=[np.array([int(tone[i:i+2],16)/255 for i in (0,2,4)]) for tone in definition["tone"]]
        lift=np.clip(.29+.53*y+.09*np.sin(x*13 + y*6)+.04*np.sin(x*34-y*26),0,1)
        channels=(a[None,None,:]+(b-a)[None,None,:]*lift[:,:,None]+grain[:,:,None])
        raw=np.rint(channels*255).clip(0,255).astype(np.uint8)
        rel=Path("textures")/f'ft_goose_env_far_ridge_{key[-1].lower()}_basecolor.png'
        path=output/rel
        def chunk(tag,data):
            return struct.pack(">I",len(data))+tag+data+struct.pack(">I",zlib.crc32(tag+data))
        rows=b"".join(b"\x00"+row.tobytes() for row in raw[::-1])
        path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">2I5B",384,384,8,2,0,0,0))
                         +chunk(b"IDAT",zlib.compress(rows,9))+chunk(b"IEND",b""))
        mat=BASE["paint"]("Distant_"+key,definition["tone"][1])
        material=mat.node_tree.nodes.get("Principled BSDF")
        material.inputs["Specular IOR Level"].default_value=.17
        material.inputs["Roughness"].default_value=.96
        texture=mat.node_tree.nodes.new("ShaderNodeTexImage")
        texture.image=bpy.data.images.load(str(path),check_existing=False)
        texture.image.pack()
        texture.image.filepath="//"+rel.as_posix()
        texture.extension="EXTEND"
        mat.node_tree.links.new(texture.outputs["Color"],material.inputs["Base Color"])
        materials[key]=(mat,{"path":rel.as_posix(),"sha256":file_hash(path),"size":[384,384],
                               "MAT-003_input":str(source.relative_to(LIBRARY)),
                               "MAT-003_input_sha256":expected,"tint_base_top_srgb":definition["tone"]})
    return materials


def export(output,items):
    for name,item in items.items():
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active=item
        item.select_set(True)
        action=bpy.ops.export_scene.gltf(filepath=str(output/f"ENV-009_{name}.glb"),export_format="GLB",
                                        use_selection=True,export_yup=True,export_animations=False,export_extras=True)
        check(action=={"FINISHED"},name)


def reimport(output,items,textures):
    result, returned = {}, {}
    for name,source in items.items():
        path=output/f"ENV-009_{name}.glb"
        doc,blob=BASE["glb_chunks"](path)
        node,=doc["nodes"]
        check(node["name"]==name and node.get("translation",[0]*3)==[0]*3 and not node.get("matrix")
              and node.get("scale",[1]*3)==[1]*3 and not doc.get("animations"),node)
        mat,=doc["materials"]
        image,=doc["images"]
        view=doc["bufferViews"][image["bufferView"]]
        start=view.get("byteOffset",0)
        checksum=sha256(blob[start:start+view["byteLength"]]).hexdigest()
        check(mat.get("alphaMode","OPAQUE")=="OPAQUE" and checksum==textures[name]["sha256"],name)
        attrs=doc["meshes"][0]["primitives"][0]["attributes"]
        access=doc["accessors"][attrs["POSITION"]]
        view=doc["bufferViews"][access["bufferView"]]
        offset=view.get("byteOffset",0)+access.get("byteOffset",0)
        want={tuple(round(v,5) for v in (p.co.x,p.co.z,-p.co.y)) for p in source.data.vertices}
        actual={tuple(round(v,5) for v in struct.unpack_from("<3f",blob,offset+i*view.get("byteStride",12)))
                for i in range(access["count"])}
        check(actual==want,(name,"raw glTF axes/size"))
        known=set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(path),import_pack_images=True,merge_vertices=True)
        tile,=set(bpy.data.objects)-known
        check(tile.name.split(".")[0]==name,name)
        sig0,sig1=BASE["signature"](source.data),BASE["signature"](tile.data)
        check(sig0.keys()==sig1.keys(),name)
        errors=[0.,0.,0.]
        for key,(mat, corners) in sig0.items():
            match,other=sig1[key]
            check(mat==match,(mat,match))
            for (p,n,u),(q,m,v) in zip(corners,other):
                for i,value in enumerate(((p-q).length,BASE["angle"](n,m),(u-v).length)):
                    errors[i]=max(errors[i],value)
        check(errors[0]<1e-5 and errors[1]<.16 and errors[2]<1e-6,(name,errors))
        statistics=audit(tile)
        result[name]=dict(statistics,embedded_png_sha256=checksum,max_delta_BU=errors[0],
                          max_normal_error_degrees=errors[1],max_uv_error=errors[2])
        returned[name]=tile
    return returned,result


def make_route(parent):
    mat=BASE["paint"]("Review route warm brush","DBB981",emission=True)
    vertices,faces=[],[]
    for i in range(49):
        y=-2.4+i*.5
        x=.84*math.sin(y*.31)-.083*y
        j=len(vertices)
        z=1/BASE["SCALE"]
        vertices.extend(((x-.09,y-.07,z),(x+.09,y-.07,z),(x+.07,y+.08,z),(x-.08,y+.08,z)))
        faces.append((j,j+1,j+2,j+3))
    return BASE["simple_mesh"](parent,"Review only | route fades before mountains",vertices,faces,mat)


def stage(scene,items):
    content=group("Four separated background placements",scene.collection)
    modules={}
    for label,name,pos,scale in PLACEMENTS:
        tile=add(content,label,items[name].data,pos)
        tile.scale=scale
        modules[label]=tile
    cameras=BASE["studio"](scene,scene.collection)
    background=scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value=(.64,.72,.77,1)
    background.inputs["Strength"].default_value=.78
    mats,_=BASE["load_materials"]()
    floor=BASE["rectangle"](scene.collection,"Review wetland bed",-140,140,-22,265,-.15,mats["GrassFlat"])
    uv=floor.data.uv_layers.new(name="Review terrain UV")
    for loop in floor.data.loops:
        x,y,_=floor.data.vertices[loop.vertex_index].co
        uv.data[loop.index].uv=((x+5)/18,(y+5)/18)
    water=BASE["paint"]("Review wetland water","91ACA6")
    # Keep the water on one side to avoid suggesting a distant runway.
    coast=[(5.4+2.95*math.sin(j*.2)+.63*math.sin(j*.67),j*1.62-13,-.112)
           for j in range(83)]
    verts=[v for x,y,z in coast for v in ((x,y,z),(145,y,z))]
    faces=[(2*j,2*j+1,2*j+3,2*j+2) for j in range(len(coast)-1)]
    BASE["simple_mesh"](scene.collection,"Review wetland shore",verts,faces,water)
    route=make_route(scene.collection)
    bird=BASE["add_goose"](scene.collection)
    cam=BASE["camera"](cameras,"Source rig | 180 · .48 · 50°",(0,0,3),(0,2,0))
    return modules,route,bird,cam


def view_pose(cam,bird,args):
    x,y,direction=args
    BASE["pose_at"](cam,bird,(x,y),Vector((math.sin(direction),math.cos(direction))))


def sample_view(scene,cam,route,bird,modules):
    bpy.context.view_layer.update()
    q={name:[world_to_camera_view(scene,cam,o.matrix_world@v.co) for v in o.data.vertices]
       for name,o in modules.items()}
    points=[p for points in q.values() for p in points if p.z>0]
    lowest=min(float(p.y) for p in points)
    # Every ridge remains in the upper band, and no usable route sample shares that band.
    marker_pixels=[world_to_camera_view(scene,cam,route.matrix_world@p.co) for p in route.data.vertices]
    visible=[p.y for p in marker_pixels if 0<p.x<1 and 0<p.y<1 and p.z>0]
    separation=(lowest-max(visible))*SIZE[1]
    alone={name:{"highest_y_from_top_px":(1-max(p.y for p in values))*SIZE[1],
                 "lowest_y_from_top_px":(1-min(p.y for p in values))*SIZE[1]} for name,values in q.items()}
    p=world_to_camera_view(scene,cam,bird.location)
    world_margin=min(o.matrix_world.translation.y + min(v.co.y for v in o.data.vertices)*o.scale.y
                     for o in modules.values())-FLIGHT_END_Y
    check((1-lowest)<.19 and separation>7 and world_margin>12 and .40<p.y<.60,
          (lowest,separation,world_margin,p))
    return {"max_background_band_fraction":1-lowest,"min_route_to_background_gap_px":separation,
            "world_buffer_to_demo_flight_y_BU":world_margin,"individual_ridge_projections":alone}


def render_lineup(items,folder):
    studio=BASE["fresh_scene"]("ENV-009 | Silhouette compare")
    cams=BASE["studio"](studio,studio.collection)
    wash=BASE["paint"]("Neutral studio wash","C6CCCD")
    BASE["rectangle"](studio.collection,"Backdrop comparison floor",-190,190,-110,100,-.17,wash)
    for i,(name,source) in enumerate(items.items()):
        size=DATA[name]["size"][0]
        tile=add(studio.collection,name+" comparison",source.data,((i-1)*34,0,0))
        tile.scale=(30/size,2.,2.25)
    cam=BASE["camera"](cams,"Oblique silhouette comparison",(14,-91,28),(0,0,.7),105)
    BASE["render"](studio,cam,folder,"preview_lineup",(1260,464),24)


def review_assets(output,items):
    scene=BASE["fresh_scene"]("ENV-009 | Fixed follow backdrop")
    modules,route,bird,cam=stage(scene,items)
    view_pose(cam,bird,VIEWS[0])
    BASE["render"](scene,cam,output,"graybox_fixed_rear",SIZE,14)
    return scene,modules,route,bird,cam


def verify(candidate,output):
    bpy.ops.wm.open_mainfile(filepath=str(candidate/f"{STEM}.blend"))
    source={name:bpy.data.objects[name] for name in DATA}
    m=json.loads((candidate/"asset_manifest.json").read_text())
    report=json.loads((candidate/"qa.json").read_text())
    BASE["fresh_scene"]("ENV-009 | Independent GLB recheck")
    _, recheck=reimport(candidate,source,m["textures"])
    check(recheck==report["roundtrip"],"independent roundtrip results differ")
    write(output/"recheck.json",{"result":"pass","roundtrip":recheck})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    check(not any(output.iterdir()),"use an empty temporary output")
    if args.verify:
        verify(args.verify,output)
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    scene=bpy.context.scene
    scene.name="ENV-009 | Standalone asset meshes at origin"
    collection=group("ENV-009 | Three backdrop assets",scene.collection)
    gray=BASE["paint"]("Graybox blue charcoal","ADB6BF")
    items={name:make_ridge(collection,name,gray) for name in DATA}
    geometric={name:audit(tile) for name,tile in items.items()}
    review,placed,route,bird,cam=review_assets(output,items)
    textures=palette_maps(output)
    for name, tile in items.items(): tile.data.materials[0]=textures[name][0]
    mapping={name:info for name, (_,info) in textures.items()}
    bpy.context.window.scene=scene
    export(output,items)
    bpy.context.window.scene=review
    BASE["set_preview_workspace"](review,cam)
    review.render.filepath="//review.png"
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{STEM}.blend"))
    camera_report={}
    for i,pose in enumerate(VIEWS):
        view_pose(cam,bird,pose)
        BASE["render"](review,cam,output,f"preview_fixed_rear_{i+1}",SIZE,24)
        camera_report[str(i+1)]=sample_view(review,cam,route,bird,placed)
    render_lineup(items,output)
    after=BASE["fresh_scene"]("ENV-009 | Final GLB reassembly")
    returned,reimported=reimport(output,items,mapping)
    for tile in returned.values(): tile.hide_render=True
    other, markers, goose, camera=stage(after,returned)
    view_pose(camera,goose,VIEWS[0])
    BASE["render"](after,camera,output,"preview_glb_roundtrip",SIZE,24)
    reassembled=sample_view(after,camera,markers,goose,other)
    check(reassembled==camera_report["1"],"reassembled fixed render metrics differ")
    write(output/"qa.json",{"id":"ENV-009","version":"v001","status":"needs_review",
          "graybox":geometric,"fixed_rear_852x393":camera_report,"roundtrip":reimported,
          "roundtrip_sample_camera":reassembled,"normal_tolerance_degrees":.16,
          "pending":["Paco art review, USDZ/RealityKit, real flight bounds, and iPhone/iPad validation."]})
    write(output/"asset_manifest.json",{"id":"ENV-009","version":"v001","status":"needs_review",
          "blender":bpy.app.version_string,"execution_order_1_based":22,"depends":["MAT-003/v001"],
          "source_and_rights":"Project-original thin volumes and derived washes from project MAT-003.",
          "axis_map_gltf":["x","z","-y"],"root_blender_BU":[0,0,0],"textures":mapping,
          "variants":geometric,"review_camera_placements":PLACEMENTS,"camera_sources":{
              "ThirdPersonRig.graybox":[180,.48,50],"target_height_game_units":6,"leader_height_game_units":8,
              "game_units_per_BU":BASE["SCALE"],"review_flight_end_y_BU":FLIGHT_END_Y}})
    

if __name__=="__main__":
    main()
