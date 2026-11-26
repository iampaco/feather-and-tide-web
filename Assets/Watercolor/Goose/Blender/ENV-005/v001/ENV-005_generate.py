"""Reusable Geometry Nodes reed preset, three baked meshes, and instance audit."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import runpy
import sys

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
REED_BLEND = LIB / "ENV-004/v001/ENV-004_reeds.blend"
ENV2 = LIB / "ENV-002/v001"
ENV3 = LIB / "ENV-003/v001"
PLANTS = runpy.run_path(str(LIB / "ENV-004/v001/ENV-004_generate.py"))
BASE = PLANTS["BASE"]
check, obj, group, sha, write = (BASE[k] for k in ("check","obj","collection","file_hash","write_json"))
PRESETS = {"Sparse": (.34,.68,24011), "Dense": (1.24,.82,24011), "ShoreEdge": (1.82,.20,24011)}
STEM = "ENV-005_reed_distribution"
BEDS = {
    "StartMudflat":(0,-10,0), "RestPatch":(0,10,0), "ReedIslet":(10,0,0),
    "Shore_S":(10,-10,0), "Shore_N":(10,10,0), "Meadow":(0,0,0),
}
ATTR_DENSITY = "reed_shore_weight"
# A padded region encloses every full-size ENV-002 bird footprint.
# The central rescue space is a review location until a level is authored.
def protected_regions():
    qa = json.loads((ENV2 / "qa.json").read_text())
    clearance = .62  # Covers the projected extent of a full-size folded goose, plus margin.
    result = []
    for name in ("StartMudflat", "RestPatch", "ReedIslet"):
        records = qa["graybox"]["modules"][name]["flock_all_1x"]["birds"]
        anchors = [record["xy_BU"] for record in records]
        (lx, hx), (ly, hy) = [(min(row[i] for row in anchors), max(row[i] for row in anchors)) for i in range(2)]
        dx, dy, _ = BEDS[name]
        result.append((dx + (lx + hx) / 2, dy + (ly + hy) / 2,
                       (hx - lx) / 2 + clearance, (hy - ly) / 2 + clearance))
    result.append((.85, 0., 2.35, 2.25))
    return tuple(result)


KEEP_OUT = protected_regions()
PROFILE_RADIUS = .66
MIN_ROOT_Z = BASE["WATER"] + .021


def load(path,names):
    with bpy.data.libraries.load(str(path),link=False) as (_, target):
        target.objects=list(names)
    return dict(zip(names,target.objects))


def contour(mesh, offset):
    segments=[]
    for p in mesh.polygons:
        pts=[mesh.vertices[i].co + Vector(offset) for i in p.vertices]
        hit=[a.lerp(b,(BASE["WATER"]-a.z)/(b.z-a.z)).xy for a,b in zip(pts,pts[1:]+pts[:1])
             if (a.z<BASE["WATER"]) != (b.z<BASE["WATER"])]
        if hit and (hit[0]-hit[1]).length>1e-7: segments.append(hit)
    return segments


def distance_to_segments(v,segments):
    distances=[]
    for a,b in segments:
        d=b-a
        t=min(1,max(0,(v-a).dot(d)/d.length_squared))
        distances.append((v-a-t*d).length)
    return min(distances)


def grow_surface(refs, terrain):
    placed=[]
    edges=[]
    for name,offset in BEDS.items():
        source=terrain["Shore" if name.startswith("Shore_") else "Flat" if name=="Meadow" else name]
        placed.append((source.data,offset))
        edges.extend(contour(source.data,offset))
    vertices,faces=[],[]
    for mesh,offset in placed:
        start=len(vertices)
        vertices.extend([v.co+Vector(offset) for v in mesh.vertices])
        faces.extend(tuple(start+i for i in p.vertices) for p in mesh.polygons)
    bed=bpy.data.meshes.new("Wetland review surface with editable shore weights")
    bed.from_pydata(vertices,[],faces)
    bed.update()
    carrier=obj(refs,"Source terrain density mesh",bed)
    attr=bed.attributes.new(ATTR_DENSITY,"FLOAT","POINT")
    values=[math.exp(-(distance_to_segments(p.xy,edges)/1.06)**2) for p in vertices]
    attr.data.foreach_set("value",values)
    return carrier,edges


def make_graph(reeds):
    tree=bpy.data.node_groups.new("ENV-005 | Wetland reed distribution","GeometryNodeTree")
    tree.description="Use the reed_shore_weight float point attribute and edit the four exclusion rectangles for a new site."
    tree.is_modifier=True
    tree.asset_mark()

    def socket(name,kind,default=None,direction="INPUT"):
        s=tree.interface.new_socket(name=name,in_out=direction,socket_type=kind)
        if default is not None: s.default_value=default
        return s

    socket("Geometry","NodeSocketGeometry")
    socket("Seed","NodeSocketInt",24011)
    socket("Density per BU²","NodeSocketFloat",.34).min_value=0
    socket("Interior fraction","NodeSocketFloat",.68).min_value=0
    wind_socket=socket("Wind angle radians","NodeSocketFloat",.135)
    wind_socket.min_value=0
    wind_socket.max_value=.135
    socket("Wind direction (XY) radians","NodeSocketFloat",0)
    socket("Motion phase radians","NodeSocketFloat",0)
    socket("Realize for export","NodeSocketBool",False)
    socket("Audit points","NodeSocketBool",False)
    socket("Geometry","NodeSocketGeometry",direction="OUTPUT")
    inp=tree.nodes.new("NodeGroupInput")
    out=tree.nodes.new("NodeGroupOutput")
    counter=Counter()

    def new(kind,label,stage):
        node=tree.nodes.new(kind)
        node.label=label
        node.location=(stage*245,-counter[stage]*180)
        counter[stage]+=1
        return node

    def put(target,value):
        if isinstance(value,bpy.types.NodeSocket):
            tree.links.new(value,target)
        else:
            target.default_value=value

    def calc(op,name,a,b=None,stage=1):
        node=new("ShaderNodeMath",name,stage)
        node.operation=op
        put(node.inputs[0],a)
        if b is not None: put(node.inputs[1],b)
        return node.outputs[0]

    def vec(label,components,stage):
        node=new("ShaderNodeCombineXYZ",label,stage)
        for i,v in enumerate(components): put(node.inputs[i],v)
        return node.outputs[0]

    field=inp.outputs
    inp.location=(-300,100)
    attr=new("GeometryNodeInputNamedAttribute","Painted shoreline weight",0)
    attr.data_type="FLOAT"
    attr.inputs["Name"].default_value=ATTR_DENSITY
    shore=attr.outputs["Attribute"]
    base=calc("SUBTRACT","Outside bank influence",1,shore,1)
    interior=calc("MULTIPLY","Thin the interior",base,field["Interior fraction"],1)
    factor=calc("ADD","Keep the shore dense",shore,interior,2)
    density=calc("MULTIPLY","Preset density",factor,field["Density per BU²"],3)
    dist=new("GeometryNodeDistributePointsOnFaces","Seeded placements on the actual triangles",4)
    dist.distribute_method="RANDOM"
    put(dist.inputs["Mesh"],field["Geometry"])
    put(dist.inputs["Density"],density)
    put(dist.inputs["Seed"],field["Seed"])
    position=new("GeometryNodeInputPosition","Use each root position",4)
    xyz=new("ShaderNodeSeparateXYZ","XY and support elevation",5)
    put(xyz.inputs[0],position.outputs[0])
    x,y,z=xyz.outputs
    reject=calc("LESS_THAN","Keep open water clear",z,MIN_ROOT_Z,7)
    for i,(cx,cy,rx,ry) in enumerate(KEEP_OUT):
        dx=calc("ABSOLUTE",f"Keep-out {i+1} | X distance",calc("SUBTRACT","X from centre",x,cx,6),stage=7)
        dy=calc("ABSOLUTE",f"Keep-out {i+1} | Y distance",calc("SUBTRACT","Y from centre",y,cy,6),stage=7)
        in_x=calc("LESS_THAN","Within padded X",dx,rx+PROFILE_RADIUS,8)
        in_y=calc("LESS_THAN","Within padded Y",dy,ry+PROFILE_RADIUS,8)
        inside=calc("MULTIPLY","Protected dry space",in_x,in_y,9)
        reject=calc("MAXIMUM","Add exclusion",inside,reject,10)
    delete=new("GeometryNodeDeleteGeometry","Exclude wet ground and protected rectangles",11)
    delete.domain="POINT"
    put(delete.inputs["Geometry"],dist.outputs["Points"])
    put(delete.inputs["Selection"],reject)
    points=delete.outputs[0]

    def random_value(label,kind,lo,hi,seed_offset):
        r=new("FunctionNodeRandomValue",label,12)
        r.data_type=kind
        put(r.inputs["Min"],lo)
        put(r.inputs["Max"],hi)
        put(r.inputs["Seed"],calc("ADD",label+" offset",field["Seed"],seed_offset,11))
        return r.outputs["Value"]

    proto=random_value("Six silhouettes","INT",0,len(reeds)-1,7)
    yaw=random_value("Individual azimuth","FLOAT",-math.pi,math.pi,11)
    size=random_value("Individual scale","FLOAT",.73,1.18,31)
    phase=random_value("Individual phase","FLOAT",0,math.tau,53)
    mixed=calc("ADD","Time and local phase",phase,field["Motion phase radians"],13)
    wave=calc("SINE","Gust envelope",mixed,stage=13)
    gain=calc("MULTIPLY_ADD","Phase-dependent weight",wave,.34,stage=14)
    gain.node.inputs[2].default_value=.66
    lean=calc("MULTIPLY","Tilt around planted root",gain,field["Wind angle radians"],14)
    axis_x=calc("MULTIPLY","Wind axis X",calc("SINE","Direction Y",field["Wind direction (XY) radians"],stage=13),-1,14)
    axis_y=calc("COSINE","Wind axis Y",field["Wind direction (XY) radians"],stage=13)
    axis=new("FunctionNodeAxisAngleToRotation","Downwind tilt",15)
    put(axis.inputs["Axis"],vec("Horizontal bend axis",(axis_x,axis_y,0),15))
    put(axis.inputs["Angle"],lean)
    euler=new("FunctionNodeEulerToRotation","Yaw variety",15)
    put(euler.inputs[0],vec("Yaw around base",(0,0,yaw),15))
    rotation=new("FunctionNodeRotateRotation","Yaw first, then wind in object space",16)
    rotation.rotation_space="GLOBAL"
    put(rotation.inputs["Rotation"],euler.outputs[0])
    put(rotation.inputs["Rotate By"],axis.outputs[0])
    for name,typ,value in (("reed_variant","INT",proto),("reed_radius_scale","FLOAT",size),
                           ("reed_phase","FLOAT",phase),("reed_lean","FLOAT",lean)):
        save=new("GeometryNodeStoreNamedAttribute",name,17)
        save.data_type=typ
        save.domain="POINT"
        put(save.inputs["Geometry"],points)
        put(save.inputs["Name"],name)
        put(save.inputs["Value"],value)
        points=save.outputs[0]

    realized_group=new("GeometryNodeJoinGeometry","Six explicitly matched prototype streams",20)
    variant=new("GeometryNodeInputNamedAttribute","Read the variant used by the audit",18)
    variant.data_type="INT"
    variant.inputs["Name"].default_value="reed_variant"
    scale=new("GeometryNodeInputNamedAttribute","Read the plant scale",18)
    scale.data_type="FLOAT"
    scale.inputs["Name"].default_value="reed_radius_scale"
    for i,(name,reed) in enumerate(reeds.items()):
        source=new("GeometryNodeObjectInfo",name,17)
        source.transform_space="ORIGINAL"
        source.inputs["Object"].default_value=reed
        selected=new("FunctionNodeCompare",name+" selector",18)
        selected.data_type="INT"
        selected.operation="EQUAL"
        put(next(s for s in selected.inputs if s.enabled and s.name=="A"),variant.outputs["Attribute"])
        put(next(s for s in selected.inputs if s.enabled and s.name=="B"),i)
        instance=new("GeometryNodeInstanceOnPoints","Place "+name,19)
        put(instance.inputs["Points"],points)
        put(instance.inputs["Selection"],selected.outputs[0])
        put(instance.inputs["Instance"],source.outputs["Geometry"])
        put(instance.inputs["Scale"],scale.outputs["Attribute"])
        put(instance.inputs["Rotation"],rotation.outputs[0])
        tree.links.new(instance.outputs[0],realized_group.inputs[0])
    realize=new("GeometryNodeRealizeInstances","Freeze the current instance transforms",20)
    put(realize.inputs[0],realized_group.outputs[0])
    frozen=new("GeometryNodeSwitch","Instances / realized mesh",21)
    frozen.input_type="GEOMETRY"
    put(frozen.inputs["Switch"],field["Realize for export"])
    put(frozen.inputs["False"],realized_group.outputs[0])
    put(frozen.inputs["True"],realize.outputs[0])
    diagnostic=new("GeometryNodePointsToVertices","Audit point IDs and weights",20)
    put(diagnostic.inputs["Points"],points)
    switch=new("GeometryNodeSwitch","Audit mode",22)
    switch.input_type="GEOMETRY"
    put(switch.inputs["Switch"],field["Audit points"])
    put(switch.inputs["False"],frozen.outputs[0])
    put(switch.inputs["True"],diagnostic.outputs[0])
    put(out.inputs[0],switch.outputs[0])
    out.location=(23*245,100)
    return tree


def modify(item, tree, preset):
    mod=item.modifiers.new("Wetland | " + preset,"NODES")
    mod.node_group=tree
    density, interior, seed=PRESETS[preset]
    for name,value in (("Density per BU²",density),("Interior fraction",interior),("Seed",seed)):
        set_input(mod,name,value)
    return mod


def set_input(mod,label,value):
    socket=next(x for x in mod.node_group.interface.items_tree if x.item_type=="SOCKET" and
                x.in_out=="INPUT" and x.name==label)
    mod.properties.inputs[socket.identifier]["value"]=value
    mod.id_data.update_tag()


def evaluate(item):
    bpy.context.view_layer.update()
    depsgraph=bpy.context.evaluated_depsgraph_get()
    return bpy.data.meshes.new_from_object(item.evaluated_get(depsgraph))


def extract(item):
    mod=item.modifiers[0]
    set_input(mod,"Audit points",True)
    mesh=evaluate(item)
    values=[]
    for v in mesh.vertices:
        i=v.index
        data=[mesh.attributes[name].data[i].value for name in ("reed_variant","reed_radius_scale","reed_phase","reed_lean")]
        values.append((*tuple(v.co),*data))
    bpy.data.meshes.remove(mesh)
    set_input(mod,"Audit points",False)
    check(values,(item.name,"no points"))
    return values


def freeze(item):
    set_input(item.modifiers[0],"Realize for export",True)
    mesh=evaluate(item)
    set_input(item.modifiers[0],"Realize for export",False)
    return mesh


def audit(item,edges,reeds):
    positions=extract(item)
    check(positions==extract(item),(item.name,"seed mismatch"))
    mod=item.modifiers[0]
    preset=item.name
    set_input(mod,"Seed",PRESETS[preset][2]+1)
    check(positions!=extract(item),preset)
    set_input(mod,"Seed",PRESETS[preset][2])
    set_input(mod,"Motion phase radians",1.65)
    updated=extract(item)
    set_input(mod,"Motion phase radians",0)
    check([p[:-1] for p in positions]==[p[:-1] for p in updated],preset)
    delta=max(abs(a[-1]-b[-1]) for a,b in zip(positions,updated))
    check(delta>.04,preset)
    counts=Counter(p[3] for p in positions)
    check(len(counts)==6 and len(set(round(p[5],5) for p in positions))>12,preset)
    zmin=min(p[2] for p in positions)
    keepout_margin=min(max(abs(x-cx)-rx,abs(y-cy)-ry)-PROFILE_RADIUS
                       for x,y,*_ in positions for cx,cy,rx,ry in KEEP_OUT)
    check(zmin>=MIN_ROOT_Z-1e-5 and keepout_margin>=-1e-5,(preset,zmin,keepout_margin))
    mesh=freeze(item)
    mesh.calc_loop_triangles()
    # Ensure the realized scene really contains one copy of the selected reed per root.
    required=sum(len(list(reeds.values())[p[3]].data.polygons) for p in positions)
    check(len(mesh.loop_triangles)==required,(preset,len(mesh.loop_triangles),required))
    onshore=sum(distance_to_segments(Vector((p[0],p[1])),edges)<1.0 for p in positions)
    guards=[max(abs(v.co.x-cx)-rx,abs(v.co.y-cy)-ry)
            for v in mesh.vertices for cx,cy,rx,ry in KEEP_OUT]
    check(min(guards)>=-1e-5,(preset,min(guards)))
    stats={"count":len(positions),"min_realized_vertex_margin_to_keepout_BU":min(guards),"prototype_counts":{list(reeds)[k]:v for k,v in sorted(counts.items())},
           "min_root_above_water_BU":zmin-BASE["WATER"], "min_root_margin_beyond_padded_keepout_BU":keepout_margin,
           "observed_max_lean_change_degrees":math.degrees(delta),
           "shore_distance_under_1_BU_fraction":onshore/len(positions),"realized_triangles":required,
           "repeat_same_seed_exact":True,"changed_seed_changes_roots":True}
    return mesh,stats


def surface_context(scene,terrain, water):
    geo=group("Wetland context",scene.collection)
    for row in range(-2,9):
        for col in range(-6,2):
            name="Shore" if col==1 else "Flat"
            if row==-1 and col==0:name="StartMudflat"
            if row==1 and col==0:name="RestPatch"
            if row==0 and col==1:name="ReedIslet"
            obj(geo,f"{name} | {col},{row}",terrain[name].data,(col*10,row*10,0))
    if water:
        for name,point in (("ShallowPool_StartMudflat",(0,-10,0)),("ShallowPool_RestPatch",(0,10,0)),
                           ("Channel",(10,0,0))):
            obj(geo,name,water[name].data,point)
    else:
        BASE["rectangle"](geo,"Wetland reference plane",-35,100,-20,100,-.18,BASE["paint"]("Reference","7EAAA9"))
    if water:
        mat=water["Channel"].data.materials[0]
        water_builder=runpy.run_path(str(ENV3/"ENV-003_generate.py"))["build_water"]
        shore_sheet=water_builder(geo,"Review offshore shore source",terrain["Shore"],mat)
        shore_sheet.hide_render=True
        for corner in shore_sheet.data.uv_layers.active.data: corner.uv.y=0
        for row in range(-2,9):
            if row!=0: obj(geo,f"Review water above Shore {row}",shore_sheet.data,(10,row*10,0))
        for row in range(-2,12):
            sheet=BASE["rectangle"](geo,f"Review offshore water {row}",15,190,row*10-5,row*10+5,-.18,mat)
            uv=sheet.data.uv_layers.new(name="WaterUV")
            for i,value in enumerate(((1,0),(1,0),(1,1),(1,1))): uv.data[i].uv=value
        bottom=next(m for m in terrain["Shore"].data.materials if m.name.split(".")[0]=="ShallowMargin")
        floor=BASE["rectangle"](geo,"Review offshore bed",15,190,-25,115,-.65,bottom)
        uv=floor.data.uv_layers.new(name="TerrainUV")
        for loop in floor.data.loops:
            x,y,_=floor.data.vertices[loop.vertex_index].co
            uv.data[loop.index].uv=((x+5)/10,(y+5)/10)
    else:
        BASE["rectangle"](geo,"Distant water wash",9.95,190,-42,160,-.188,BASE["paint"]("Review horizon","82A5A7"))
    BASE["rectangle"](geo,"Review surroundings",-200,200,-40,220,-.8,BASE["paint"]("Review ground","C5D2C7"))
    return geo


def prepare_view(scene,terrain,water):
    geo=surface_context(scene,terrain,water)
    cameras=BASE["studio"](scene,scene.collection)
    top=BASE["camera"](cameras,"Density and clearing | top",(4,0,45),(4,0,0),34)
    cam=BASE["camera"](cameras,"Source rig | fixed rear",(0,0,1),(0,1,0))
    bird=BASE["add_goose"](geo)
    bird.location=(1.5,-3.0,8/BASE["SCALE"])
    BASE["follow"](cam,bird.location.xy,Vector((.15,.988686)))
    return top,cam


def write_report(output, reports, transport):
    write(output/"qa.json",{"id":"ENV-005","status":"needs_review","presets":reports,"roundtrip":transport,
        "keep_out_rectangles_center_xy_half_extents_BU":KEEP_OUT,"root_clearance_padding_BU":PROFILE_RADIUS,
        "pending":["Art review, actual rescue visibility, runtime placement/LOD/wind and iPhone/iPad performance."]})


def mesh_compare(a,b):
    p,n=PLANTS["mesh_signal"](a)
    q,m=PLANTS["mesh_signal"](b)
    check(p==q,(a.name,len(p),len(q)))
    theta=max(BASE["angle"](v,w) for key in n for v,w in zip(n[key],m[key]))
    check(theta<.06,(a.name,theta))
    return theta


def transfer(output,baked):
    result,returned={},{}
    for name,item in baked.items():
        path=output/f"ENV-005_{name}.glb"
        gltf,blob=BASE["glb_chunks"](path)
        node,=gltf["nodes"]
        check(node["name"]==name and node.get("translation",[0]*3)==[0]*3 and
              node.get("scale",[1]*3)==[1]*3 and not gltf.get("animations"),node)
        embeds=[]
        for image in gltf["images"]:
            view=gltf["bufferViews"][image["bufferView"]]
            start=view.get("byteOffset",0)
            embeds.append(BASE["sha256"](blob[start:start+view["byteLength"]]).hexdigest())
        texture_manifest=json.loads((LIB/"ENV-004/v001/asset_manifest.json").read_text())["textures"]
        check(set(embeds)=={v["sha256"] for v in texture_manifest.values()} and
              all(m.get("doubleSided") and m.get("alphaMode","OPAQUE")=="OPAQUE" for m in gltf["materials"]),name)
        before=set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(path),merge_vertices=False)
        incoming,=set(bpy.data.objects)-before
        check(incoming.type=="MESH",name)
        max_error=mesh_compare(item,incoming)
        result[name]={"triangles":len(incoming.data.polygons),"max_normal_error_degrees":max_error,
                      "embedded_original_png_sha256":sorted(embeds)}
        returned[name]=incoming
    return result,returned


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    check(not any(output.iterdir()),"Use an empty output folder.")
    if args.verify:
        path=args.verify.resolve()
        bpy.ops.wm.open_mainfile(filepath=str(path/f"{STEM}.blend"))
        scene=bpy.data.scenes["ENV-005 | Reusable distribution"]
        bpy.context.window.scene=scene
        presets={name:bpy.data.objects[name] for name in PRESETS}
        data={name:bpy.data.objects[name+" | frozen"] for name in PRESETS}
        expected=json.loads((path/"qa.json").read_text())
        reeds={name:bpy.data.objects[name] for name in PLANTS["REEDS"]}
        terrain={name:bpy.data.objects[name] for name in ("StartMudflat","ReedIslet","RestPatch","Flat","Shore")}
        _,edges=grow_surface(group("Independent contour geometry",scene.collection),terrain)
        for name,item in presets.items():
            item.hide_set(False)
            mesh,stats=audit(item,edges,reeds)
            check(stats==expected["presets"][name],(name,stats))
            temporary=obj(scene.collection,name+" re-freeze",mesh)
            mesh_compare(data[name],temporary)
        BASE["fresh_scene"]("Independent GLB reimport")
        stats,_=transfer(path,data)
        check(stats==expected["roundtrip"],"GLB roundtrip changed")
        write(output/"recheck.json",{"result":"pass","presets":expected["presets"],"roundtrip":stats})
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    scene=bpy.context.scene
    scene.name="ENV-005 | Reusable distribution"
    refs=group("Read-only asset inputs",scene.collection)
    terrain=load(ENV2/"ENV-002_wetland.blend",("StartMudflat","ReedIslet","RestPatch","Flat","Shore"))
    reeds=load(REED_BLEND,PLANTS["REEDS"])
    for item in (*terrain.values(),*reeds.values()):
        refs.objects.link(item)
        item.hide_render=True
        item.hide_set(True)
    carrier,edges=grow_surface(refs,terrain)
    carrier.hide_render=True
    carrier.hide_set(True)
    instances=group("Editable presets | choose one visible",scene.collection)
    graph=make_graph(reeds)
    cases={name:obj(instances,name,carrier.data) for name in PRESETS}
    report,baked={},{}
    for name,item in cases.items():
        modify(item,graph,name)
        mesh,report[name]=audit(item,edges,reeds)
        baked[name]=mesh
    max_reed=max(PLANTS["asset_metrics"](item)["max_horizontal_radius_BU"] for item in reeds.values())
    max_height=max(PLANTS["asset_metrics"](item)["height_BU"] for item in reeds.values())
    check(1.18*(max_reed + max_height*math.sin(.135))<=PROFILE_RADIUS,(max_reed,max_height))
    check(report["Sparse"]["count"]<report["Dense"]["count"] and
          report["ShoreEdge"]["shore_distance_under_1_BU_fraction"]>report["Dense"]["shore_distance_under_1_BU_fraction"],report)
    exports=BASE["fresh_scene"]("ENV-005 | Frozen GLB exports")
    items={name:obj(exports.collection,name+" | frozen",mesh) for name,mesh in baked.items()}
    for name,item in items.items():
        # The live preset owns the plain object name; set it as the glTF node label for the export.
        original=cases[name]
        original.name=name+" | live"
        item.name=name
        PLANTS["export"](output,"ENV-005",{name:item})
        item.name=name+" | frozen"
        original.name=name
    water_path=ENV3/"ENV-003_wetland_water.blend"
    water=load(water_path,("ShallowPool_StartMudflat","ShallowPool_RestPatch","Channel")) if water_path.exists() else {}
    review=BASE["fresh_scene"]("ENV-005 | Preset comparison")
    top,cam=prepare_view(review,terrain,water)
    objects={name:obj(review.collection,"Review | "+name,mesh) for name,mesh in baked.items()}
    # The graybox freezes identical GN placements with a neutral material.
    gray_mat=BASE["paint"]("Graybox | neutral reeds","7E8981")
    gray_mesh=baked["Dense"].copy()
    for i in range(len(gray_mesh.materials)):gray_mesh.materials[i]=gray_mat
    gray=obj(review.collection,"Graybox instance proof",gray_mesh)
    for item in objects.values():item.hide_render=True
    BASE["render"](review,top,output,"graybox_top",(960,960),14)
    bpy.data.objects.remove(gray,do_unlink=True)
    for name,item in objects.items():
        for other,sample in objects.items():
            sample.hide_render=sample.hide_viewport=other!=name
        BASE["render"](review,top,output,"preview_top_"+name,(960,960),18)
        BASE["render"](review,cam,output,"preview_fixed_rear_"+name,BASE["GAME_SIZE"],20)
    BASE["set_preview_workspace"](review,cam)
    review.render.filepath="//review.png"
    for name,item in cases.items():
        item.hide_set(name!="ShoreEdge",view_layer=scene.view_layers[0])
        item.hide_render=name!="ShoreEdge"
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{STEM}.blend"))
    final=BASE["fresh_scene"]("ENV-005 | Roundtrip verification")
    transport,incoming=transfer(output,items)
    top,_=prepare_view(final,terrain,water)
    for name,item in incoming.items(): item.hide_render=name!="ShoreEdge"
    BASE["render"](final,top,output,"preview_glb_roundtrip",(960,960),18)
    write_report(output,report,transport)
    manifest={"id":"ENV-005","version":"v001","status":"needs_review","execution_order_1_based":19,
      "depends":["ENV-004/v001","ENV-002/v001"],"review_water": "ENV-003/v001" if water else "reference plane",
      "source_hashes":{"ENV-004.blend":sha(REED_BLEND),"ENV-002.blend":sha(ENV2/"ENV-002_wetland.blend")},
      "presets":{k:{"density_per_BU2":v[0],"interior_fraction":v[1],"seed":v[2]} for k,v in PRESETS.items()},
      "geometry_nodes":"ENV-005 | Wetland reed distribution","blender_xyz_to_gltf":["x","z","-y"],
      "density_attribute":ATTR_DENSITY,"rights":"Project-original Geometry Nodes and previously authored project inputs."}
    write(output/"asset_manifest.json",manifest)


if __name__=="__main__":
    main()
