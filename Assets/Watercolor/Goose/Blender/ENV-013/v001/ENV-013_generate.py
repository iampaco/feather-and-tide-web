"""Build two closed low shrubs and test OpenBank rescue visibility in Blender."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import random
import runpy
import struct
import sys
import zlib

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
import numpy as np

HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
ENV1 = LIB / "ENV-001/v001"
ENV7 = LIB / "ENV-007/v001"
MAT = LIB / "MAT-001/v001"
BASE = runpy.run_path(str(ENV1 / "ENV-001_generate.py"))
BANK = runpy.run_path(str(ENV7 / "ENV-007_generate.py"))
check, obj, group = (BASE[key] for key in ("check", "obj", "collection"))
digest, write = BASE["file_hash"], BASE["write_json"]
VARIANTS = ("Shrub_A", "Shrub_B")
STEM = "ENV-013_riparian_shrubs"
SCALE = BASE["SCALE"]
GAME_SIZE = BASE["GAME_SIZE"]
SWAY = "Wind_sway_X"
CLIP = "Breeze_loop"
FORECOURT = (1.72, 4.55, 7.28, 12.72)
CORRIDOR = (2.21, 4.68, -6., 17.5)
CAMERA_POSES = ((3.40, 0.5, .030), (3.42, 3.6, .019), (3.86, 5.7, -.075))
SEEDS = (14013, 14031, 14053, 14071, 14107, 14143, 14159, 14177, 14197, 14221, 14243, 14263)
ART_SEED = SEEDS[0]
PALETTES = {
    "Shrub_A": ("46584D", "708474", "9CAA8A"),
    "Shrub_B": ("526044", "849066", "AFB180"),
    "Stem": ("554D44", "716356", "968471"),
}


class Plant:
    def __init__(self):
        self.vertices, self.faces, self.slots = [], [], []

    def add(self, point):
        self.vertices.append(tuple(point))
        return len(self.vertices) - 1

    def face(self, indices, slot):
        self.faces.append(tuple(indices))
        self.slots.append(slot)

    def rings(self, rings, bottom, top, slot):
        for i in range(len(rings[0])):
            j = (i+1) % len(rings[0])
            self.face((bottom, rings[0][j], rings[0][i]), slot)
            for a, b in zip(rings, rings[1:]):
                self.face((a[i], a[j], b[j]), slot)
                self.face((a[i], b[j], b[i]), slot)
            self.face((top, rings[-1][i], rings[-1][j]), slot)

    def foliage(self, center, radii, yaw, phase):
        group_center = Vector(center)
        rotate = Matrix.Rotation(yaw, 3, "Z")
        rings = []
        sides = 8
        # A broad shoulder and three irregular scallops keep the mass distinct from a ball.
        for r, (z, fullness) in enumerate(((-.70,.61),(-.26,.94),(.23,1.),(.67,.72))):
            ids=[]
            for i in range(sides):
                phi = math.tau*i/sides + .10*(r % 2)
                waviness = 1+.10*math.sin(phi*3+phase)+.045*math.cos(phi*5-phase+r*.37)
                point = Vector((math.cos(phi)*radii[0]*fullness*waviness+.11*z*radii[0],
                                math.sin(phi)*radii[1]*fullness*waviness,
                                (z+.085*math.sin(2*phi+phase))*radii[2]))
                ids.append(self.add(group_center + rotate @ point))
            rings.append(ids)
        bottom = self.add(group_center+rotate@Vector((-.10*radii[0],0,-.91*radii[2])))
        top = self.add(group_center+rotate@Vector((.09*radii[0],-.07*radii[1],.95*radii[2])))
        self.rings(rings, bottom, top, 0)

    def stem(self, start, middle, end, radii):
        centers = [Vector(point) for point in (start, middle, end)]
        rings=[]
        axis = (centers[-1]-centers[0]).normalized()
        u = axis.cross(Vector((0,1,0))).normalized()
        v = axis.cross(u)
        for c, radius in zip(centers, radii):
            positions=[c+radius*(u*math.cos(math.tau*i/5)+v*math.sin(math.tau*i/5)) for i in range(5)]
            if c.z==0:
                for p in positions:p.z=0.
            rings.append([self.add(point) for point in positions])
        # Center caps make the volume closed. The upright root sits precisely at Z=0.
        self.rings(rings,self.add(centers[0]),self.add(centers[-1]),1)


def build_plant(parent, name, materials):
    b=Plant()
    if name=="Shrub_A":
        b.stem((0,0,0),(.02,0,.23),(.04,.01,.47),(.053,.039,.019))
        b.stem((.02,0,.14),(-.24,-.11,.24),(-.40,-.16,.36),(.038,.026,.013))
        b.stem((.025,0,.16),(.26,.09,.25),(.44,.16,.37),(.037,.024,.011))
        lobes=(
            ((-.37,-.11,.31),(.36,.31,.23),-.38),
            ((.36,.03,.32),(.38,.31,.23),.46),
            ((-.08,.24,.39),(.34,.32,.24),.77),
            ((.07,-.13,.50),(.34,.32,.27),-.34),
            ((-.36,.15,.49),(.26,.23,.20),.48),
            ((.32,.23,.53),(.23,.26,.19),.14),
        )
    else:
        b.stem((0,0,0),(.055,-.017,.49),(.13,-.015,.89),(.068,.052,.020))
        b.stem((.042,-.02,.31),(-.22,-.05,.48),(-.35,-.12,.65),(.034,.025,.012))
        b.stem((.078,-.02,.46),(.28,.14,.65),(.44,.19,.84),(.037,.021,.012))
        b.stem((.097,-.01,.61),(-.05,.22,.82),(-.14,.28,1.),(.031,.021,.011))
        lobes=(
            ((-.34,-.15,.63),(.35,.26,.26),-.50),
            ((.34,.06,.75),(.38,.30,.27),.27),
            ((-.16,.25,.87),(.29,.26,.27),.7),
            ((.08,-.11,.99),(.38,.31,.32),-.27),
            ((.31,.26,1.06),(.24,.23,.24),.55),
        )
    for i,(center, radii, yaw) in enumerate(lobes):
        b.foliage(center,radii,yaw,1.31*i+.17)
    mesh=bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(b.vertices,[],b.faces)
    mesh.update()
    for mat in materials:
        mesh.materials.append(mat)
    top=max(p[2] for p in b.vertices)
    uv=mesh.uv_layers.new(name="PaperUV")
    for face,slot in zip(mesh.polygons,b.slots,strict=True):
        face.material_index=slot
        face.use_smooth=(slot==0)
        for i in face.loop_indices:
            x,y,z=b.vertices[mesh.loops[i].vertex_index]
            uv.data[i].uv=(.5+ .40*x+.25*y, z/top)
    plant=obj(parent,name,mesh)
    plant.asset_mark()
    plant.asset_data.description="ENV-013 v001 · rooted riverbank shrub · mesh breeze sample"
    plant["root_socket"]=[0.,0.,0.]
    plant["breeze_morph"]=SWAY
    plant["yaw_about_ground_axis_degrees"]=0.
    basis=plant.shape_key_add(name="Basis")
    shape=plant.shape_key_add(name=SWAY)
    shape.slider_min,shape.slider_max=0,1
    amp=.100 if name.endswith("_A") else .139
    for a,v in zip(basis.data,shape.data,strict=True):
        f=(max(0,a.co.z)/top)**2
        v.co=a.co+Vector((amp*f,.024*f,-.011*f))
    keys=mesh.shape_keys
    for frame,value in ((1,0),(22,1),(46,0),(61,.49),(81,0)):
        shape.value=value
        shape.keyframe_insert(data_path="value",frame=frame)
    keys.animation_data.action.name=name+"_"+CLIP
    shape.value=0
    return plant


def read_image(source):
    image=bpy.data.images.load(str(source),check_existing=False)
    width,height=image.size
    data=np.empty(width*height*4,dtype=np.float32)
    image.pixels.foreach_get(data)
    data=data.reshape(height,width,4)
    bpy.data.images.remove(image)
    return data[:,:,:3]


def write_png(path, rgb):
    h,w,_=rgb.shape
    def chunk(name,data):
        payload=name+data
        return struct.pack(">I",len(data))+payload+struct.pack(">I",zlib.crc32(payload))
    rows=b"".join(b"\x00"+row.tobytes() for row in rgb[::-1])
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,2,0,0,0))+
                     chunk(b"IDAT",zlib.compress(rows,9))+chunk(b"IEND",b""))


def materials(output):
    source=MAT/"MAT-001_watercolor_master.blend"
    manifest=json.loads((MAT/"asset_manifest.json").read_text())
    with bpy.data.libraries.load(str(source),link=False) as (_,dst):
        dst.materials=["PlantOpaque","DryGround"]
    plant,ground=dst.materials
    mats,meta={},{}
    for label,palette in PALETTES.items():
        template=ground if label=="Stem" else plant
        info=manifest["textures"][template.name.split(".")[0]]
        src=MAT/info["path"]
        expected=manifest["files"][info["path"]]
        containing=next(node for node in template.node_tree.nodes if node.type=="TEX_IMAGE")
        check(digest(src)==sha256(containing.image.packed_file.data).hexdigest()==expected,src)
        paper=read_image(src)[::2,::2,:].mean(axis=2)
        sample_y=np.linspace(0,1,256)[:,None]
        stops=np.array([[int(rgb[i:i+2],16) for i in range(0,6,2)] for rgb in palette])/255
        rgb=np.stack([np.interp(sample_y,(0,.47,1),stops[:,ch]) + (paper-paper.mean())*.17 for ch in range(3)],axis=2)
        relative=Path("textures")/f"ft_goose_vegetation_{label.lower()}_basecolor.png"
        write_png(output/relative,np.rint(np.clip(rgb,0,1)*255).astype(np.uint8))
        packed=bpy.data.images.load(str(output/relative),check_existing=False)
        packed.colorspace_settings.name="sRGB"
        packed.pack()
        packed.filepath="//"+relative.as_posix()
        mat=template.copy()
        mat.name="ENV013_"+label
        mat.diffuse_color=BASE["color"](palette[1])
        mat.use_backface_culling=True
        node=next(n for n in mat.node_tree.nodes if n.type=="TEX_IMAGE")
        node.image,node.extension=packed,"EXTEND"
        mats[label]=mat
        meta[label]={"texture":relative.as_posix(),"sha256":digest(output/relative),"palette_srgb":palette,
                     "source_project_png":info["path"],"source_png_sha256":expected,
                     "derived_from_material":template.name.split(".")[0], "size":[256,256]}
    return mats,meta


def metrics(plant):
    data=plant.data
    data.calc_loop_triangles()
    coordinates=[p.co for p in data.vertices]
    box=[[min(v[k] for v in coordinates),max(v[k] for v in coordinates)] for k in range(3)]
    edges=Counter()
    for face in data.polygons:
        check(face.area>2e-8,(plant.name,face.index))
        edges.update(face.edge_keys)
    check(set(edges.values())=={2} and abs(box[2][0])<1e-6 and plant.location.length==0,(plant.name,box,Counter(edges.values())))
    basis,shape=data.shape_keys.key_blocks
    offsets=[b.co-a.co for a,b in zip(basis.data,shape.data,strict=True)]
    root_move=max(offsets[v.index].length for v in data.vertices if v.co.z<.005)
    check(root_move<.0002 and .09<max(v.length for v in offsets)<.15,(plant.name,root_move))
    root_group=plant.vertex_groups.get("Wind_weight")
    if root_group is None:
        root_group=plant.vertex_groups.new(name="Wind_weight")
        for v in data.vertices:
            root_group.add([v.index],(v.co.z/box[2][1])**2,"REPLACE")
    return {"triangles":len(data.loop_triangles),"vertices_source":len(coordinates),"bounds_BU":box,
            "fully_closed":True,"max_wind_delta_BU":max(d.length for d in offsets),"max_low_root_wind_delta_BU":root_move}


def static_copy(parent, asset, name, location, scale=1., yaw=0., weight=None):
    # Shared data unless a private wind pose is needed in the gallery.
    data=asset.data
    if weight is not None:
        data=data.copy()
        data.shape_keys.animation_data_clear()
        data.shape_keys.key_blocks[1].value=weight
    instance=obj(parent,name,data,location)
    instance.rotation_euler.z=yaw
    instance.scale=(scale,)*3
    return instance


def library_inputs(parent, gray):
    with bpy.data.libraries.load(str(ENV7/"ENV-007_river_valley.blend"),link=False) as (_,target):
        target.objects=[f"{name}_{suffix}" for name in ("Straight","Bend","OpenBank") for suffix in ("Bed","Water")]
    bank_assets={node.name.split(".")[0]:node for node in target.objects}
    with bpy.data.libraries.load(str(ENV1/"ENV-001_terrain.blend"),link=False) as (_,target):
        target.objects=["Flat"]
    flat,=target.objects
    for item in list(bank_assets.values())+[flat]:
        parent.objects.link(item)
        item.hide_render=True
        item.hide_set(True)
    active={}
    for name in ("Straight","Bend","OpenBank"):
        bed,water=(bank_assets[f"{name}_{suffix}"] for suffix in ("Bed","Water"))
        active[name]=(bed,water)
        if gray:
            for item,hue in ((bed,"A2A69D"),(water,"689198")):
                gray_mat=BASE["paint"]("Graybox bank "+item.name,hue)
                for idx in range(len(item.data.materials)):item.data.materials[idx]=gray_mat
    if gray:
        gray_mat=BASE["paint"]("Graybox land","A2A69D")
        for idx in range(len(flat.data.materials)):flat.data.materials[idx]=gray_mat
    return active,flat


def signed_clearance(point,zone):
    x0,x1,y0,y1=zone
    return max(x0-point.x,point.x-x1,y0-point.y,point.y-y1)


def plant_positions(seed, bed):
    rng=random.Random(seed)
    # The edge is sampled as staggered patches, with gaps instead of cross-channel rows.
    targets=((0,[-9.8,-7.8,-5.5,-1.8,.4,3.7,5.9,8.2,10.2,14.,16.4,20.4,23.6]),
             (1,[-8.4,-6.3,-4.2,-2.,1.4,4.8,6.3,8.5,10.8,13.8,16.0,19.,22.3,24.8]))
    bank_bvhs={key:BANK["bvh"](surface) for key,surface in bed.items()}
    positions=[]
    for side,samples in targets:
        for base_y in samples:
            name=VARIANTS[rng.randrange(2)]
            y=base_y+rng.uniform(-.37,.37)
            x=rng.uniform(-4.68,-3.05) if side==0 else rng.uniform(5.52,7.08)
            tile=round(y/10)
            if side==0:
                source_name={-1:"Straight",0:"Bend",1:"OpenBank",2:"Straight"}.get(tile,"Straight")
                z=BANK["bed_height"](bank_bvhs[source_name],x,y-10*tile)[0]
                if z<-.08:
                    continue
            else:
                z=0.
            level=rng.uniform(.74,1.05)
            yaw=rng.uniform(-math.pi,math.pi)
            phase=rng.randrange(81)
            positions.append((name,(x,y,z-.009),level,yaw,phase))
    check(len(positions)>=18 and {p[0] for p in positions}==set(VARIANTS),seed)
    return positions


def cloud(vertices, faces):
    return BVHTree.FromPolygons(vertices,faces,all_triangles=False)


def visibility_tree(scene_items):
    vertices,faces=[],[]
    for item in scene_items:
        matrix=item.matrix_world
        off=len(vertices)
        vertices.extend(matrix @ v.co for v in item.data.vertices)
        faces.extend(tuple(off+i for i in f.vertices) for f in item.data.polygons)
    return cloud(vertices,faces)


def shrub_tree(variants, positions, time):
    vertices,faces=[],[]
    clearance=math.inf
    for name,loc,scale,yaw,phase in positions:
        basis,shape=variants[name].data.shape_keys.key_blocks
        value=.5+.5*math.sin((phase/80+time)*math.tau)
        matrix=Matrix.Translation(Vector(loc)) @ Matrix.Rotation(yaw,4,"Z") @ Matrix.Scale(scale,4)
        local=[matrix@a.co.lerp(b.co,value) for a,b in zip(basis.data,shape.data,strict=True)]
        clearance=min(clearance,*(signed_clearance(v,z) for v in local for z in (FORECOURT,CORRIDOR)))
        off=len(vertices)
        vertices.extend(local)
        faces.extend(tuple(off+i for i in p.vertices) for p in variants[name].data.polygons)
    check(clearance>.035,("plant intrudes into refuge/flight strip",clearance))
    return cloud(vertices,faces),clearance


def endpoints(tail):
    return [tail.matrix_world@Vector(offset) for offset in ((0,0,.13),(-.09,-.05,.15),(.09,-.05,.15),
                (0,.25,.23),(0,.37,.27),(-.17,-.10,.08),(.17,-.10,.08))]+[
                Vector((x,y,.028)) for x in (1.91,3.16,4.39) for y in (7.65,10.,12.35)]


def occlusion_audit(scene, cam, bed_items, tail, originals, bed_sources):
    terrain=visibility_tree(bed_items)
    results=[]
    targets=endpoints(tail)
    unit_frame=[]
    for x,y,heading in CAMERA_POSES:
        forward=Vector((heading,1)).normalized()
        BASE["follow"](cam,(x,y),forward)
        bpy.context.view_layer.update()
        ndcs=[world_to_camera_view(scene,cam,p) for p in targets]
        check(all(v.z>0 and 0<v.x<1 and 0<v.y<1 for v in ndcs),(x,y,ndcs))
        unit_frame.append([min(v.x for v in ndcs),max(v.x for v in ndcs),min(v.y for v in ndcs),max(v.y for v in ndcs)])
        for origin in targets:
            delta=origin-cam.location
            hit,*_=terrain.ray_cast(cam.location,delta.normalized(),delta.length-.004)
            check(hit is None,("terrain occlusion", origin, hit))
    min_clearance=math.inf
    rays=0
    for seed in SEEDS:
        positions=plant_positions(seed,bed_sources)
        check(positions==plant_positions(seed,bed_sources),("seed not reproducible",seed))
        results.append(len(positions))
        for t in (0.,.25,.5,.75):
            tree,gap=shrub_tree(originals,positions,t)
            min_clearance=min(min_clearance,gap)
            for x,y,heading in CAMERA_POSES:
                BASE["follow"](cam,(x,y),Vector((heading,1)).normalized())
                bpy.context.view_layer.update()
                for target in targets:
                    delta=target-cam.location
                    hit,*_=tree.ray_cast(cam.location,delta.normalized(),delta.length-.004)
                    check(hit is None,(seed,t,target,"shrub hides rescue target",hit))
                    rays+=1
    return {"fixed_rear_poses":CAMERA_POSES,"seeds":list(SEEDS),"expected_breeze_phases":4,
            "targets_per_view":len(targets),"total_shrub_visibility_rays":rays, "occluded_rays":0,
            "terrain_visibility_rays":len(targets)*len(CAMERA_POSES),"projected_target_bounds_xy":unit_frame,
            "seeded_counts":results,"minimum_mesh_clearance_outside_reserved_rectangles_BU":min_clearance,
            "open_corridor_xy_BU":CORRIDOR,"reserved_rescue_xy_BU":FORECOURT}


def set_lineup(scene, items):
    assets=group("Shrub family | 1:1 scale",scene.collection)
    for index,name in enumerate(VARIANTS):
        static_copy(assets,items[name],name+" portrait",((index-.5)*2.22,0,0),yaw=.18 if index else -.25,weight=0.)
    rigs=BASE["studio"](scene,scene.collection)
    floor=BASE["paint"]("Review lineup clay","B2BAB5")
    BASE["rectangle"](assets,"Lineup floor",-70,70,-60,60,-.003,floor)
    camera=BASE["camera"](rigs,"Lineup | same scale",(3.1,-8.6,3.5),(0,0,.60),4.75)
    return camera


def support(scene, assets, gray):
    bpy.context.window.scene=scene
    source=group("Linked-in river references",scene.collection)
    modules,flat=library_inputs(source,gray)
    _,beds=BANK["scene_geometry"](scene,modules,flat,gray,extended=True)
    overlay=group("Review • Rescue and approach",scene.collection)
    leader=BASE["add_goose"](overlay)
    tail,tail_contact=BANK["support_bird"](overlay,modules["OpenBank"][0],show_color=not gray)
    if gray:
        neutral=BASE["paint"]("Flock • Graybox","9F9A93")
        for i in range(len(leader.data.materials)):leader.data.materials[i]=neutral
    probes=group("Advisory route markers",overlay)
    BANK["route_overlay"](probes)
    bed_sources={key:objects[0] for key,objects in modules.items()}
    placements=plant_positions(ART_SEED,bed_sources)
    plants=group("Deterministic side plantings",scene.collection)
    items=[]
    for i,(name,loc,level,yaw,phase) in enumerate(placements):
        item=static_copy(plants,assets[name],f"{name} | bank {i:02}",loc,level,yaw,.5+.5*math.sin(phase/80*math.tau))
        item["wind_phase_fraction"]=phase/80
        items.append(item)
    rigs=BASE["studio"](scene,scene.collection)
    sun=next(o for o in rigs.objects if o.type=="LIGHT")
    sun.rotation_euler=Vector((.28,.39,-1)).to_track_quat("-Z","Y").to_euler()
    cam=BASE["camera"](rigs,"Fixed rear 180 / 0.48 / 50",(0,0,1),(0,1,0))
    top=BASE["camera"](rigs,"Rescue strip and planted banks",(1.4,7.,41),(1.4,7.,0),17.7)
    x,y,a=CAMERA_POSES[1]
    BASE["pose_at"](cam,leader,(x,y),Vector((a,1)).normalized())
    scene.render.resolution_x,scene.render.resolution_y=GAME_SIZE
    scene.camera=cam
    bpy.context.view_layer.update()
    return modules,beds,bed_sources,cam,top,leader,tail,tail_contact,items


def glb_export(folder, scene, originals):
    bpy.context.window.scene=scene
    scene.frame_set(1)
    for name,item in originals.items():
        bpy.ops.object.select_all(action="DESELECT")
        item.select_set(True)
        bpy.context.view_layer.objects.active=item
        status=bpy.ops.export_scene.gltf(filepath=str(folder/f"ENV-013_{name}.glb"),export_format="GLB",
                use_selection=True,export_yup=True,export_extras=True,export_animations=True,
                export_morph=True,export_morph_animation=True,export_animation_mode="ACTIONS",
                export_morph_normal=True)
        check(status=={"FINISHED"},(name,status))


def signal(item):
    mesh=item.data
    mesh.calc_loop_triangles()
    uv=mesh.uv_layers.active.data
    basis,shape=mesh.shape_keys.key_blocks
    result={}
    for p in mesh.loop_triangles:
        ids=list(p.loops)
        def tuple_at(idx):
            vertex=mesh.loops[idx].vertex_index
            coord=basis.data[vertex].co
            return tuple(round(x,5) for x in coord)
        rotate=min(range(3),key=lambda index:tuple_at(ids[index]))
        ids=ids[rotate:]+ids[:rotate]
        key=(mesh.materials[p.material_index].name.split(".")[0],*(tuple_at(i) for i in ids))
        details=[]
        for i in ids:
            vertex=mesh.loops[i].vertex_index
            details.append((mesh.corner_normals[i].vector.copy(),uv[i].uv.copy(),
                            (shape.data[vertex].co-basis.data[vertex].co).copy()))
        check(key not in result,key)
        result[key]=details
    return result


def check_animation(scene, source, obj):
    p=source.data.shape_keys
    q=obj.data.shape_keys
    check([k.name for k in q.key_blocks]==["Basis",SWAY],q.key_blocks.keys())
    check(q.animation_data is not None and q.animation_data.action is not None, obj.name)
    incoming=q.animation_data.action
    original=p.animation_data.action
    original_start,original_end=original.frame_range
    imported_start,imported_end=incoming.frame_range
    check(abs((imported_end-imported_start)-(original_end-original_start))<.001,
          (original.frame_range,incoming.frame_range))
    error=0.
    for offset in range(81):
        first=original_start+offset
        second=imported_start+offset
        scene.frame_set(round(first))
        source_value=source.data.shape_keys.key_blocks[1].value
        scene.frame_set(round(second))
        new_value=obj.data.shape_keys.key_blocks[1].value
        error=max(error,abs(source_value-new_value))
    check(error<.001,(obj.name,error))
    scene.frame_set(round(imported_start))
    start=obj.data.shape_keys.key_blocks[1].value
    scene.frame_set(round(imported_end))
    end=obj.data.shape_keys.key_blocks[1].value
    check(abs(start-end)<1e-6,(start,end))
    scene.frame_set(round(imported_start))
    return {"duration_s":(imported_end-imported_start)/scene.render.fps,"baked_frames":81,
            "max_channel_match_error":error,"loop_boundary_error":abs(start-end)}


def roundtrip(scene, folder, originals, mapping):
    results,returned={},{}
    scene.render.fps=24
    for name,source in originals.items():
        path=folder/f"ENV-013_{name}.glb"
        doc,blob=BASE["glb_chunks"](path)
        node,=doc["nodes"]
        check(node["name"]==name and "matrix" not in node and node.get("translation",[0,0,0])==[0,0,0]
              and node.get("rotation",[0,0,0,1])==[0,0,0,1] and node.get("scale",[1,1,1])==[1,1,1],node)
        materials_by_name={"ENV013_"+label:data for label,data in mapping.items()}
        embedded={}
        for mat in doc["materials"]:
            label=mat["name"]
            check(mat.get("alphaMode","OPAQUE")=="OPAQUE" and mat.get("doubleSided",False)==False,mat)
            tex=doc["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
            image=doc["images"][tex["source"]]
            view=doc["bufferViews"][image["bufferView"]]
            idx=view.get("byteOffset",0)
            checksum=sha256(blob[idx:idx+view["byteLength"]]).hexdigest()
            check(checksum==materials_by_name[label]["sha256"],(label,checksum))
            embedded[label]=checksum
        source_points={tuple(round(x,5) for x in (v.co.x,v.co.z,-v.co.y)) for v in source.data.vertices}
        glb_points=set()
        count=0
        mesh,=doc["meshes"]
        check(mesh.get("extras",{}).get("targetNames")==[SWAY],mesh.get("extras"))
        for primitive in mesh["primitives"]:
            check(len(primitive["targets"])==1 and "POSITION" in primitive["targets"][0],name)
            access=doc["accessors"][primitive["attributes"]["POSITION"]]
            v=doc["bufferViews"][access["bufferView"]]
            idx=v.get("byteOffset",0)+access.get("byteOffset",0)
            stride=v.get("byteStride",12)
            for i in range(access["count"]):
                glb_points.add(tuple(round(f,5) for f in struct.unpack_from("<3f",blob,idx+i*stride)))
            count+=doc["accessors"][primitive["indices"]]["count"]//3
        check(glb_points==source_points and count==len(source.data.polygons),(name,count))
        clip,=doc["animations"]
        check({(ch["target"]["path"],ch["target"]["node"]) for ch in clip["channels"]}=={("weights",0)},clip)
        old=set(bpy.data.objects)
        status=bpy.ops.import_scene.gltf(filepath=str(path),merge_vertices=False,import_pack_images=True)
        check(status=={"FINISHED"},name)
        item,=set(bpy.data.objects)-old
        src,after=signal(source),signal(item)
        check(src.keys()==after.keys() and item.type=="MESH" and item.location.length==0
              and list(item.scale)==[1,1,1],name)
        norms=uv=morph=0.
        for k,s in src.items():
            for (n,t,d),(a,b,c) in zip(s,after[k],strict=True):
                norms=max(norms,BASE["angle"](n,a))
                uv=max(uv,(t-b).length)
                morph=max(morph,(d-c).length)
        check(norms<.06 and uv<1e-5 and morph<1e-5,(name,norms,uv,morph))
        # Link a neutral-pose reference only while reading the original animation data.
        animation_linked=source.name not in scene.objects
        if animation_linked:
            scene.collection.objects.link(source)
        motion=check_animation(scene,source,item)
        if animation_linked:
            scene.collection.objects.unlink(source)
        results[name]={"embedded_PNG_verified":embedded,"triangles":count,"orientation_and_pivot_match":True,
                       "position_error_at_1e_5_precision":0,"max_normal_error_degrees":norms,
                       "max_uv_error":uv,"max_morph_vector_error_BU":morph,"verified_animation":motion}
        item.hide_render=True
        item.hide_set(True)
        returned[name]=item
    return returned,results


def build(output, gray_only):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    library=bpy.context.scene
    library.name="ENV-013 | Source meshes and Breeze_loop"
    library.render.fps=24
    library.frame_start,library.frame_end=1,81
    assets_group=group("Shrub_A and Shrub_B | shared grounded origin",library.collection)
    clays=[BASE["paint"]("Graybox foliage","AAB3A8"),BASE["paint"]("Graybox stems","868980")]
    originals={name:build_plant(assets_group,name,clays) for name in VARIANTS}
    shape_report={name:metrics(asset) for name,asset in originals.items()}
    gallery=BASE["fresh_scene"]("ENV-013 | Graybox")
    _,beds,bed_sources,cam,_,leader,tail,_,_=support(gallery,originals,True)
    proof=occlusion_audit(gallery,cam,beds,tail,originals,bed_sources)
    x,y,a=CAMERA_POSES[1]
    BASE["pose_at"](cam,leader,(x,y),Vector((a,1)).normalized())
    BASE["render"](gallery,cam,output,"graybox_fixed_rear",GAME_SIZE,13)
    cl=BASE["fresh_scene"]("ENV-013 | Graybox lineup")
    cam_line=set_lineup(cl,originals)
    BASE["render"](cl,cam_line,output,"graybox_lineup",(980,520),13)
    write(output/"graybox_qa.json",{"assets":shape_report,"open_bank":proof})
    if gray_only:
        return
    # Remove graybox stage objects and their copies before appending final source data at clean names.
    bpy.context.window.scene=library
    keep=set(library.objects)
    for item in list(bpy.data.objects):
        if item not in keep:
            bpy.data.objects.remove(item,do_unlink=True)
    bpy.data.scenes.remove(gallery)
    bpy.data.scenes.remove(cl)
    (output/"textures").mkdir()
    mats,meta=materials(output)
    for name,asset in originals.items():
        asset.data.materials[0]=mats[name]
        asset.data.materials[1]=mats["Stem"]
    glb_export(output,library,originals)
    final=BASE["fresh_scene"]("ENV-013 | GLB roundtrip")
    incoming,report=roundtrip(final,output,originals,meta)
    cam_line=set_lineup(final,incoming)
    BASE["render"](final,cam_line,output,"preview_glb_roundtrip",(980,520),20)
    portraits=BASE["fresh_scene"]("ENV-013 | Plant lineup")
    cam_line=set_lineup(portraits,originals)
    BASE["render"](portraits,cam_line,output,"preview_lineup",(980,520),20)
    BASE["set_preview_workspace"](portraits,cam_line)
    review=BASE["fresh_scene"]("ENV-013 | OpenBank gameplay review")
    _,beds,bed_sources,cam,top,leader,tail,tail_report,_=support(review,originals,False)
    v2=occlusion_audit(review,cam,beds,tail,originals,bed_sources)
    v3=occlusion_audit(review,cam,beds,tail,incoming,bed_sources)
    check(proof==v2 and v3["occluded_rays"]==v2["occluded_rays"]==0,(proof,v2,v3))
    for idx,(x,y,a) in enumerate(CAMERA_POSES):
        BASE["pose_at"](cam,leader,(x,y),Vector((a,1)).normalized())
        BASE["render"](review,cam,output,["preview_fixed_rear_entry","preview_fixed_rear","preview_fixed_rear_rescue"][idx],
                       GAME_SIZE,20)
    BASE["render"](review,top,output,"preview_open_bank_overhead",(700,1020),16)
    proof_path=output/"graybox_qa.json"
    proof_path.unlink()
    x,y,a=CAMERA_POSES[1]
    BASE["pose_at"](cam,leader,(x,y),Vector((a,1)).normalized())
    BASE["set_preview_workspace"](review,cam)
    review.render.filepath="//review.png"
    review.render.resolution_x,review.render.resolution_y=GAME_SIZE
    for item in incoming.values():bpy.data.objects.remove(item,do_unlink=True)
    bpy.data.scenes.remove(final)
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{STEM}.blend"))
    write(output/"qa.json",{"id":"ENV-013","version":"v001","status":"needs_review","geometry":shape_report,
        "graybox_open_bank":proof,"material_open_bank":v2,"roundtrip_reassembly_open_bank":v3,
        "glb_roundtrip":report,"target_ANM007_contact":tail_report,
        "pending":["Art review, runtime placement/route and dynamic rescue occlusion, RealityKit morph and wind, and iPhone/iPad."]})
    src_blend=MAT/"MAT-001_watercolor_master.blend"
    write(output/"asset_manifest.json",{"id":"ENV-013","version":"v001","status":"needs_review",
        "execution_order_1_based":52,"depends":["MAT-001/v001"],"variants":list(VARIANTS),
        "blender_file":f"{STEM}.blend","glb_files":[f"ENV-013_{n}.glb" for n in VARIANTS],
        "preview_uses":["ENV-001/v001","ENV-007/v001","CHR-001/v001","ANM-007/v001"],
        "camera_source":{"distance_game_units":180,"pitch_radians":.48,"vertical_fov_degrees":50,
                        "look_height_game_units":6,"leader_height_game_units":8,
                        "game_units_per_BU_preview":SCALE,"size_px":GAME_SIZE},
        "source_hashes":{"MAT-001.blend":digest(src_blend),
                         "ENV-007.blend":digest(ENV7/"ENV-007_river_valley.blend")},
        "textures":meta,"pivot_BU":[0,0,0],"blender_to_gltf_xyz":["x","z","-y"],
        "breeze":{"shape":SWAY,"basis":"zero at origin and at ground contact","seconds":80/24},
        "rights":"Project-original shrub mesh and baked palette, derived from project-owned MAT-001 washes."})


def verify(candidate,output):
    bpy.ops.wm.open_mainfile(filepath=str(candidate/f"{STEM}.blend"))
    lib=bpy.data.scenes["ENV-013 | Source meshes and Breeze_loop"]
    originals={n:lib.objects[n] for n in VARIANTS}
    scene=BASE["fresh_scene"]("ENV-013 | Independent delivered assets")
    m=json.loads((candidate/"asset_manifest.json").read_text())
    q=json.loads((candidate/"qa.json").read_text())
    incoming,actual=roundtrip(scene,candidate,originals,m["textures"])
    check(actual==q["glb_roundtrip"],(actual,q["glb_roundtrip"]))
    _,beds,source,cam,_,_,tail,_,_=support(scene,originals,False)
    frame=occlusion_audit(scene,cam,beds,tail,incoming,source)
    check(json.loads(json.dumps(frame))==q["roundtrip_reassembly_open_bank"],
          "independent OpenBank reassembly measures differ")
    write(output/"recheck.json",{"result":"pass","glb_roundtrip":actual,"open_bank_reassembly":frame})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--gray-only",action="store_true")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    path=args.output.resolve()
    path.mkdir(parents=True,exist_ok=True)
    check(not any(path.iterdir()),"Use an empty output directory.")
    if args.verify:
        verify(args.verify.resolve(),path)
    else:
        build(path,args.gray_only)


if __name__=="__main__":
    main()
