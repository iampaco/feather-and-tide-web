"""Produce the opaque ribbon mesh library and verify its serialized GLBs in Blender."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import random
import runpy
import sys

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
BASE = runpy.run_path(str(LIB / "ENV-001/v001/ENV-001_generate.py"))
MAT1 = LIB / "MAT-001/v001"
ENV2 = LIB / "ENV-002/v001/ENV-002_wetland.blend"
check, obj, group = (BASE[k] for k in ("check","obj","collection"))
hash_file, write = BASE["file_hash"], BASE["write_json"]
REEDS = {f"Reed_{letter}_Height_{size}": (letter, height)
         for letter, pair in {"A": (.54,.77), "B": (.70,1.01), "C": (.82,1.16)}.items()
         for size,height in zip(("S","M"),pair)}
GRASS = {"Grass_A": ("A",.205),"Grass_B": ("B",.282),"Grass_C": ("C",.245)}
PAPER = {"FogLeaf":"FFFFFF", "SedgeLeaf":"D3D6A0", "DrySedge":"E9BC83", "SeedHead":"D4A274"}


class PlantMesh:
    def __init__(self):
        self.vertices, self.uv, self.faces, self.slots = [], [], [], []

    def point(self, point, u, v):
        self.vertices.append(tuple(point))
        self.uv.append((u,v))
        return len(self.vertices)-1

    def triangle(self, indices, slot):
        self.faces.append(tuple(indices))
        self.slots.append(slot)

    def ribbon(self, root, yaw, reach, height, width, slot):
        direction = Vector((math.cos(yaw), math.sin(yaw), 0))
        side = Vector((-direction.y, direction.x, 0))
        rings = []
        for t, shape in ((0,.42),(.28,1),(.62,.69),(.87,.29)):
            center = Vector(root) + direction * (reach * t ** 1.48)
            center.z += height * (t + .36*t*(1-t))
            ridge = Vector((0, 0, width * shape * .20))
            radius = side * (width * shape)
            rings.append((self.point(center - radius, .08, t), self.point(center + ridge, .5, t),
                          self.point(center + radius, .94, t)))
        tip = self.point(Vector(root) + direction * reach + Vector((0,0,height)), .52, 1)
        for first, second in zip(rings,rings[1:]):
            for i in range(2):
                a,b,c,d = first[i],first[i+1],second[i+1],second[i]
                self.triangle((a,b,c),slot)
                self.triangle((a,c,d),slot)
        for i in range(2): self.triangle((rings[-1][i],rings[-1][i+1],tip),slot)

    def spindle(self, start, delta, profiles, slot, sides):
        previous = []
        axis = Vector(delta).normalized()
        axis_u = axis.cross(Vector((0,1,0))).normalized()
        axis_v = axis.cross(axis_u)
        for j,(t,radius) in enumerate(profiles):
            center = Vector(start) + Vector(delta) * t
            ring = [self.point(center + radius*(axis_u*math.cos(i*math.tau/sides) +
                     axis_v*math.sin(i*math.tau/sides)), (i+.25)/sides,t) for i in range(sides)]
            if previous:
                for i in range(sides):
                    k=(i+1)%sides
                    self.triangle((previous[i],previous[k],ring[k]),slot)
                    self.triangle((previous[i],ring[k],ring[i]),slot)
            previous=ring
        end = self.point(Vector(start)+Vector(delta)*1.018,.5,1)
        for i in range(sides): self.triangle((previous[i],previous[(i+1)%sides],end),slot)

    def object(self, parent, name, materials):
        mesh = bpy.data.meshes.new(name + "_mesh")
        mesh.from_pydata(self.vertices,[],self.faces)
        mesh.update()
        for mat in materials.values(): mesh.materials.append(mat)
        uv = mesh.uv_layers.new(name="PlantUV")
        for p,slot in zip(mesh.polygons,self.slots):
            p.material_index=slot
            for index in p.loop_indices: uv.data[index].uv=self.uv[mesh.loops[index].vertex_index]
        item=obj(parent,name,mesh)
        ground=min(v.co.z for v in mesh.vertices)
        for v in mesh.vertices: v.co.z -= ground
        item.asset_mark()
        item["plant_root"] = "0,0,0; Blender +Z up; local root remains planted under wind"
        return item


def generate(name, letter, h, parent, mats, grass):
    b=PlantMesh()
    rng=random.Random(381 + ord(letter)*27)
    if grass:
        count={"A":7,"B":9,"C":8}[letter]
        for i in range(count):
            yaw=i*math.tau/count+rng.uniform(-.55,.55)
            central=i%3==0
            z=h * (1 if i==0 else rng.uniform(.50,.96))
            xy=.045 if central else rng.uniform(.09,.22)
            slot={"A":0,"B":1,"C":2}[letter] if rng.random() < .79 else 0
            b.ribbon((.018*math.cos(yaw),.018*math.sin(yaw),0),yaw,xy,z,rng.uniform(.018,.037),slot)
    else:
        count={"A":4,"B":6,"C":5}[letter]
        yaw=.38 + rng.uniform(-.20,.20)
        b.spindle((0,0,0),(.095*h,.064*h,h*(.85 if letter=="C" else .93)),
                  ((0,.016),(.42,.014),(1,.009)),0,4)
        for i in range(count):
            heading=i*2.34+rng.uniform(-.39,.39)
            z0=h * (.04 + i*.056)
            z=h*(.89 if i==count-1 else rng.uniform(.47,.85))-z0
            reach=h*rng.uniform(.16,.34)
            b.ribbon((.095*z0,.064*z0,z0),heading,reach,z,h*rng.uniform(.021,.038),i%4==2)
        if letter=="C":
            for i in range(2):
                start = Vector((.088*h,.054*h,.81*h)) + Vector((-.054*i,.066*i,-.07*i))*h
                b.spindle(start,(.055*h,-.029*i*h,.19*h),((0,.011*h),(.18,.026*h),(.47,.036*h),(.78,.026*h),(1,.011*h)),3,6)
        elif letter=="B":
            b.ribbon((.045*h,.02*h,.44*h), yaw,.18*h,.53*h,.026*h,0)
    item=b.object(parent,name,mats)
    item["reference_height_BU"] = h
    return item


def set_gray(group, variants, grass):
    mats={name:BASE["paint"]("Graybox | "+name,shade)
          for name,shade in zip(PAPER,("A4AEA4","A5AEA4","A9ABA6","999B95"))}
    return {name:generate(name,kind,height,group,mats,grass) for name,(kind,height) in variants.items()}


def load_mats():
    path=MAT1/"MAT-001_watercolor_master.blend"
    manifest=json.loads((MAT1/"asset_manifest.json").read_text())
    with bpy.data.libraries.load(str(path),link=False) as (_, target):
        target.materials=["PlantOpaque","DryGround"]
    plant,dry=target.materials
    mapped={}
    for name,tint in PAPER.items():
        # DryGround's warm paper texture carries seed and dry-sedge hue; PlantOpaque carries the leaves.
        source=dry if name in ("DrySedge","SeedHead") else plant
        mat=source.copy()
        mat.name=name
        mat.use_backface_culling=False
        mat.diffuse_color=BASE["color"](tint if name!="FogLeaf" else "809581")
        nodes=mat.node_tree.nodes
        shader=next(n for n in nodes if n.type=="BSDF_PRINCIPLED")
        image=next(n for n in nodes if n.type=="TEX_IMAGE")
        data=manifest["textures"][source.name]
        relative=data["path"]
        checksum=hash_file(MAT1/relative)
        check(BASE["sha256"](image.image.packed_file.data).hexdigest()==checksum==manifest["files"][relative],name)
        image.image.filepath="//../../MAT-001/v001/"+relative
        # glTF's factor is authored through a multiply node with an unlinked color input.
        if name not in ("FogLeaf","SeedHead"):
            tint_node=nodes.new("ShaderNodeMix")
            tint_node.data_type="RGBA"
            tint_node.blend_type="MULTIPLY"
            tint_node.inputs[0].default_value=1
            tint_node.inputs[7].default_value=BASE["color"](tint)
            mat.node_tree.links.new(image.outputs["Color"],tint_node.inputs[6])
            mat.node_tree.links.new(tint_node.outputs[2],shader.inputs["Base Color"])
        mapped[name]=(mat, {"path_relative_to_candidate":"../../MAT-001/v001/"+relative,
                            "sha256":checksum,"sRGB_tint":tint if name not in ("FogLeaf","SeedHead") else "FFFFFF"})
    return mapped


def asset_metrics(tile):
    mesh=tile.data
    check(all(len(p.vertices)==3 and p.area>1e-9 for p in mesh.polygons),tile.name)
    coordinates=[v.co for v in mesh.vertices]
    check(abs(min(p.z for p in coordinates))<1e-6 and max(p.z for p in coordinates)<1.25,tile.name)
    return {"triangles":len(mesh.polygons), "vertices":len(mesh.vertices),
            "bounds_BU":[[min(p[k] for p in coordinates),max(p[k] for p in coordinates)] for k in range(3)],
            "height_BU":max(p.z for p in coordinates),
            "max_horizontal_radius_BU":max(p.xy.length for p in coordinates)}


def mesh_signal(item):
    mesh=item.data
    mesh.calc_loop_triangles()
    uv=mesh.uv_layers.active.data
    result=Counter()
    normals={}
    for t in mesh.loop_triangles:
        values=[]
        for i in t.loops:
            p=mesh.vertices[mesh.loops[i].vertex_index].co
            values.append(tuple(round(v,5) for v in (*p,*uv[i].uv)))
        pivot=min(range(3),key=lambda i:values[i])
        key=(mesh.materials[t.material_index].name.split(".")[0],*values[pivot:],*values[:pivot])
        result[key]+=1
        normals[key]=tuple(mesh.corner_normals[i].vector.copy() for i in (*t.loops[pivot:],*t.loops[:pivot]))
    return result,normals


def export(directory, prefix, items):
    for name,tile in items.items():
        bpy.ops.object.select_all(action="DESELECT")
        tile.select_set(True)
        bpy.context.view_layer.objects.active=tile
        result=bpy.ops.export_scene.gltf(filepath=str(directory/f"{prefix}_{name}.glb"),export_format="GLB",
              use_selection=True,export_yup=True,export_animations=False,export_extras=True)
        check(result=={"FINISHED"},name)


def readback(output,prefix,items,mapping):
    returned,stats={},{}
    for name,source in items.items():
        path=output/f"{prefix}_{name}.glb"
        doc,blob=BASE["glb_chunks"](path)
        root,=doc["nodes"]
        check(root["name"]==name and not doc.get("animations") and not root.get("translation")
              and root.get("scale",[1,1,1])==[1,1,1],root)
        textures={}
        for material in doc["materials"]:
            label=material["name"]
            check(material.get("doubleSided") is True and material.get("alphaMode","OPAQUE")=="OPAQUE",material)
            tex=doc["textures"][material["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
            image=doc["images"][tex["source"]]
            view=doc["bufferViews"][image["bufferView"]]
            start=view.get("byteOffset",0)
            hash=BASE["sha256"](blob[start:start+view["byteLength"]]).hexdigest()
            check(hash==mapping[label]["sha256"],(name,label,hash))
            tint=mapping[label]["sRGB_tint"]
            actual=material["pbrMetallicRoughness"].get("baseColorFactor",[1,1,1,1])
            check(max(abs(a-b) for a,b in zip(actual,BASE["color"](tint)))<1e-5,(label,actual,tint))
            textures[label]=hash
        old=set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(path),merge_vertices=False,import_pack_images=True)
        item,=set(bpy.data.objects)-old
        first,n1=mesh_signal(source)
        second,n2=mesh_signal(item)
        check(first==second and item.type=="MESH" and item.location.length==0 and list(item.scale)==[1,1,1],name)
        max_angle=max(BASE["angle"](a,b) for key in n1 for a,b in zip(n1[key],n2[key]))
        check(max_angle<.05,(name,max_angle))
        summary=asset_metrics(item)
        positions=[doc["accessors"][p["attributes"]["POSITION"]] for p in doc["meshes"][0]["primitives"]]
        bounds=[[min(a["min"][i] for a in positions),max(a["max"][i] for a in positions)] for i in range(3)]
        x,y,z=summary["bounds_BU"]
        expected=[x,z,[-y[1],-y[0]]]
        check(max(abs(a-b) for a,b in zip(sum(bounds,[]),sum(expected,[])))<1e-5,(name,bounds))
        stats[name]=dict(summary,max_normal_error_deg=max_angle,embedded_png_sha256=textures, double_sided_opaque=True)
        returned[name]=item
    return returned,stats


def lineup(scene,items,output,filename,grass):
    plants=group("Selectable silhouettes",scene.collection)
    for i,(name,tile) in enumerate(items.items()):
        col=i//2 if not grass else i
        row=i%2 if not grass else 0
        obj(plants,name+" lineup",tile.data,((col-1)*1.38,(row-.5)*1.65 if not grass else 0,0))
    studio=BASE["studio"](scene,scene.collection)
    floor=BASE["paint"]("Review neutral wash","C5CEC4")
    BASE["rectangle"](plants,"Review floor",-15,15,-15,15,-.012,floor)
    cam=BASE["camera"](studio,"Plant library | close silhouettes",(3.5,-7,4.3),(0,0,.30 if not grass else .09),
                       4.1 if not grass else 4.0)
    BASE["render"](scene,cam,output,filename,(1090,730 if not grass else 465),20)
    return cam


def environmental_stage(scene,items,output,grass):
    rng=random.Random(20116 if grass else 20114)
    group_geo=group("Scale and variation review",scene.collection)
    with bpy.data.libraries.load(str(ENV2),link=False) as (_, target):
        target.objects=["Flat","Shore"]
    flat,shore=target.objects
    for j in range(-2,8):
        for i in range(-6,3):
            if i<=0:
                obj(group_geo,f"Terrain {i},{j}",flat.data,(i*10,j*10,0))
            elif i==1:
                obj(group_geo,f"Shore {j}",shore.data,(i*10,j*10,0))
    water=BASE["paint"]("Distant wetland wash","8AAEAB")
    BASE["rectangle"](group_geo,"Water plane for scale only",8.4,175,-70,195,-.18,water)
    BASE["rectangle"](group_geo,"Backdrop under terrain",-200,200,-60,240,-.8,BASE["paint"]("Surround","BCC9BF"))
    variants=list(items.values())
    plants=group("Staggered plant placements",scene.collection)
    positions=[]
    if grass:
        bands=((-4.0,-2.4,-1.8,23,66),(2.7,4.5,-1.8,23,60),(5.1,7.2,0.3,23,39))
    else:
        bands=((5.0,8.0,-3.5,26,58),(-5,-2.5,-2.4,21,34))
    for a,b,c,d,count in bands:
        for j in range(count):
            x=rng.uniform(a,b)
            y=rng.uniform(c,d)
            radii=.18 if grass else .31
            if any((x-px)**2+(y-py)**2<radii**2 for px,py in positions): continue
            sample=variants[rng.randrange(len(variants))]
            z=BASE["height"]("Shore",x-10,y-10*round(y/10)) if x>5 else 0
            if z<-.12:continue
            place=obj(plants,f"{sample.name} review {len(positions):03}",sample.data,(x,y,z))
            yaw=rng.uniform(-math.pi,math.pi)
            k=rng.uniform(.82,1.15)
            # Tilt the entire plant around its ground pivot; +X is downwind in this shot.
            tilt=math.radians((3.5 if grass else 7) + (2.3 if grass else 3)*math.sin(j*1.87))
            place.rotation_euler=(Matrix.Rotation(tilt,3,"Y") @ Matrix.Rotation(yaw,3,"Z")).to_euler()
            place.scale=(k,k,k)
            positions.append((x,y))
    proof={}
    heading=Vector((0,1))
    camera_group=BASE["studio"](scene,scene.collection)
    cam=BASE["camera"](camera_group,"Gameplay | fixed rear",(0,0,1),(0,1,0))
    leader=(.0,0.0) if grass else (1.65,.0)
    BASE["follow"](cam,leader,heading)
    bird=BASE["add_goose"](group_geo)
    bird.location=(*leader,8/BASE["SCALE"])
    if grass:
        # These neutral pegs and a line mark a sample hazard limit in the clear corridor.
        ink=BASE["paint"]("Review | boundary muted amber","CEAD74",emission=True)
        for i in range(26):
            x,y=1.3,1.0+i*.54
            BASE["rectangle"](group_geo,f"Boundary overlay {i}",x-.066,x+.066,y-.11,y+.11,.036,ink)
        radius=max(asset_metrics(tile)["max_horizontal_radius_BU"] for tile in variants)*1.15
        clearance=min(abs(x-1.3)-radius for x,y in positions)
        check(clearance>.3,clearance)
        proof["prototype_boundary_horizontal_clearance_BU"]=clearance
    BASE["render"](scene,cam,output,"preview_fixed_rear",BASE["GAME_SIZE"],24)
    BASE["set_preview_workspace"](scene,cam)
    scene.render.filepath="//review.png"
    proof.update(review_plant_count=len(positions), unique_prototype_count=len({p.data.name for p in plants.objects}),
                 horizontal_placement_extent_BU=[min(x for x,y in positions),max(x for x,y in positions)])
    return proof


def main(prefix="ENV-004",argv=None):
    is_grass=prefix=="ENV-006"
    variants=GRASS if is_grass else REEDS
    stem=prefix+("_grass" if is_grass else "_reeds")
    parser=argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if argv is None else argv)
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    check(not any(output.iterdir()),"Use an empty temporary output directory.")
    if args.verify:
        p=args.verify.resolve()
        bpy.ops.wm.open_mainfile(filepath=str(p/f"{stem}.blend"))
        manifest=json.loads((p/"asset_manifest.json").read_text())
        source={name:bpy.data.objects[name] for name in variants}
        BASE["fresh_scene"]("Independent recheck")
        _,report=readback(p,prefix,source,manifest["textures"])
        expected=json.loads((p/"qa.json").read_text())["roundtrip"]
        check(report==expected,"independent roundtrip metrics")
        write(output/"recheck.json",{"result":"pass","modules":report})
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    scene=bpy.context.scene
    scene.name=prefix+" | Selectable source meshes"
    assets=group(prefix+" | Asset instances at root",scene.collection)
    items=set_gray(assets,variants,is_grass)
    graybox={name:asset_metrics(tile) for name,tile in items.items()}
    for key,metric in graybox.items():
        check(metric["triangles"] <= (300 if not is_grass else 150), (key,metric))
    gray=BASE["fresh_scene"]("Graybox")
    lineup(gray,items,output,"graybox_lineup",is_grass)
    bpy.data.scenes.remove(gray)
    mats=load_mats()
    for tile in items.values():
        for i,(mat,_) in enumerate(mats.values()): tile.data.materials[i]=mat
    mapping={name:data for name,(_,data) in mats.items()}
    bpy.context.window.scene=scene
    export(output,prefix,items)
    close=BASE["fresh_scene"](prefix+" | Material lineup")
    lineup(close,items,output,"preview_lineup",is_grass)
    review=BASE["fresh_scene"](prefix+" | Fixed camera review")
    measure=environmental_stage(review,items,output,is_grass)
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{stem}.blend"))
    final=BASE["fresh_scene"](prefix+" | GLB reimport")
    imported,check_glbs=readback(output,prefix,items,mapping)
    for item in imported.values(): item.hide_render=True
    lineup(final,imported,output,"preview_glb_roundtrip",is_grass)
    write(output/"qa.json",{"id":prefix,"status":"needs_review","graybox":graybox,
         "roundtrip":check_glbs,"fixed_camera":measure,
         "pending":["Owner art review and actual engine-side wind, visibility, and device tests."]})
    write(output/"asset_manifest.json",{"id":prefix,"version":"v001","status":"needs_review",
        "execution_order_1_based":50 if is_grass else 18,"depends":["MAT-001/v001"],"variants":list(variants),
        "root_blender_BU":[0,0,0],"blender_xyz_to_gltf":["x","z","-y"],"textures":mapping,
        "source_library_sha256":hash_file(MAT1/"MAT-001_watercolor_master.blend"),
        "rights":"Project-original geometry with project-owned MAT-001 PlantOpaque and DryGround.", "geometry":graybox})


if __name__=="__main__":
    main()
