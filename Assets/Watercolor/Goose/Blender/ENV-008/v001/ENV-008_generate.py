"""Build the LakeWide and LakeShore asset pair, render and verify their exact GLBs."""
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
from mathutils.bvhtree import BVHTree
import numpy as np


HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
BASE = runpy.run_path(str(LIBRARY / "ENV-001/v001/ENV-001_generate.py"))
ENV2 = LIBRARY / "ENV-002/v001/ENV-002_wetland.blend"
ENV3 = LIBRARY / "ENV-003/v001/ENV-003_wetland_water.blend"
MAT4 = LIBRARY / "MAT-004/v001"
MAT3 = LIBRARY / "MAT-003/v001"
CHR = LIBRARY / "CHR-001/v001/CHR-001_goose_rig.blend"
SPEC = HERE.parents[5] / "完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json"
SOURCE_NAMES = ("LakeWide", "LakeShore")
STEM = "ENV-008_long_lake"
WATER = BASE["WATER"]
FLOOR = BASE["FLOOR"]
PAD = Vector((4, 10, 0))
PATCH_LOW, PATCH_HIGH = 5, 15
PATCH_WEST, PATCH_EAST = -1, 9
PATCH_STEP = .625
FRAME = BASE["GAME_SIZE"]
SCALE = BASE["SCALE"]
SIZE = 1024
RGBA_FILE = "textures/ft_goose_env_long_lake_basecolor_alpha.png"
LENGTH = 58
WATER_START = 4.0
HEIGHT_TOL = 1e-6
UV_TOL = 1e-6
ROW_Y = [-7.5, -3, 0, 2.3, 3.4, WATER_START] + [5 + .625*i for i in range(17)] + [
    16.25, 18.5, 21, 24, 27.5, 31, 34.5, 38, 41.5, 45, 48.5, 51.5, 53.5, 55.5,
    57, LENGTH, 59.2, 61, 63]
SHAPE = (
    (-7.5, 10.5, .52), (WATER_START, 10.5, .64), (5, 10.8, 1.6), (6.875, 12.7, 4.8),
    (10, 15.8, 8.15), (13.125, 19.4, 11.05), (18.5, 21.5, 12.35), (24, 21.25, 12.15),
    (31, 22.55, 11.8), (38, 23.65, 11.2), (45, 23.6, 9.6), (51.5, 22.75, 7.15),
    (55.5, 21.9, 4.2), (LENGTH, 21.5, .62), (63, 21.5, .52),
)
CHANNEL_U = (0, .045, .10, .20, .32, .46, .60, .74, .85, .93, .974, 1)
check, obj, group, digest = (BASE[n] for n in ("check", "obj", "collection", "file_hash"))


def smooth(value):
    value = max(0, min(1, value))
    return value * value * (3 - 2 * value)


def shape(y):
    for first, second in zip(SHAPE, SHAPE[1:]):
        if first[0] <= y <= second[0]:
            w = (y-first[0])/(second[0]-first[0])
            # The narrow inlet opens gradually. Linear interpolation keeps each row's edge measurable.
            return tuple(first[i] + (second[i]-first[i])*w for i in (1,2))
    raise ValueError(y)


def depth(u, y):
    _, half_width = shape(y)
    edge = min(u, 1-u) * 2 * half_width
    end = min(y-WATER_START, LENGTH-y)
    return (WATER - FLOOR) * smooth(edge / 2.6) * smooth(end / 2.1)


def mix(a,b,w):
    return a + (b-a)*w


def shoreline_x(y):
    center, half = shape(y)
    return center-half+1.6, center+half+1.6


def row_points(y):
    lo, hi = shoreline_x(y)
    outside_water = not WATER_START <= y <= LENGTH
    outer_height = WATER if not outside_water else min(0, WATER + .13*min(abs(y-WATER_START), abs(y-LENGTH)))
    # The west edge of the lake is separate from the 10 BU patch's flat connector.
    # (0,0) remains on the open checkpoint forecourt, with the inlet on the right.
    near = min(.56, (lo-PATCH_EAST)*.28)
    east = .65 + .26*math.sin(.17*y+.2)
    prefix = [(PATCH_WEST + PATCH_STEP*i, y, 0) for i in range(17)]
    prefix.extend(((min(lo-.02, max(PATCH_EAST+.03, lo-near)), y, mix(0,outer_height,.63)),))
    middle = [(mix(lo,hi,u), y, outer_height if outside_water else WATER - depth(u,y)) for u in CHANNEL_U]
    tail = [(hi+east,y,mix(outer_height,0,.54)), (hi+2.05+east,y,0),
            (hi+4.4+east,y,.09+smooth((y-17)/36)*.12)]
    return prefix + middle + tail


class Builder:
    def __init__(self):
        self.vertices, self.faces, self.uvs, self.materials = [], [], [], []
        self.indices = {}

    def vertex(self, p):
        key = tuple(round(x, 6) for x in p)
        if key not in self.indices:
            self.indices[key] = len(self.vertices)
            self.vertices.append(tuple(p))
        return self.indices[key]

    def triangle(self, points, uv, material):
        ids = tuple(self.vertex(p) for p in points)
        check(len(set(ids))==3, (material, points))
        self.faces.append(ids)
        self.uvs.append(uv)
        self.materials.append(material)

    def make(self, parent, name, mats):
        mesh = bpy.data.meshes.new(name + " | geometry")
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        used = [k for k in mats if k in self.materials]
        for label in used:
            mesh.materials.append(mats[label])
        slots = {label: i for i,label in enumerate(used)}
        uvs = mesh.uv_layers.new(name="UVMap")
        for poly,label,coords in zip(mesh.polygons,self.materials,self.uvs,strict=True):
            check(poly.area > 1e-8 and poly.normal.z > 0, (name, poly.index))
            poly.material_index = slots[label]
            poly.use_smooth = True
            for index,coord in zip(poly.loop_indices,coords,strict=True):
                uvs.data[index].uv = coord
        tile=obj(parent,name,mesh)
        tile.asset_mark()
        return tile


def ground_uv(pt):
    x,y,_ = pt
    return (x+5)/10, (y+5)/10


def terrain_slot(points, column, water_columns):
    h = sum(p[2] for p in points)/3
    y = sum(p[1] for p in points)/3
    if column <= 16:
        return "GrassFlat"
    if h < WATER-.20 and column in water_columns:
        return "ShallowMargin"
    if h < -.063:
        return "MudBank"
    if h > .035 and y > 35 and math.sin(y*.84) > .2:
        return "MossStone"
    return "GrassFlat"


def quad_rows(builder, rows):
    cols = len(rows[0])
    water_columns = set(range(18,18 + len(CHANNEL_U)-1))
    for j,(low,high) in enumerate(zip(rows,rows[1:])):
        for i in range(cols-1):
            if PATCH_LOW <= low[0][1] < PATCH_HIGH and i < 16:
                continue
            quad = low[i], low[i+1], high[i+1], high[i]
            pairs = ((0,1,2),(0,2,3)) if (i+j)%2==0 else ((0,1,3),(1,2,3))
            for choice in pairs:
                points = [quad[k] for k in choice]
                builder.triangle(points,[ground_uv(p) for p in points],terrain_slot(points,i,water_columns))


def patch_source():
    with bpy.data.libraries.load(str(ENV2), link=False) as (_,target):
        target.objects=["RestPatch"]
    return target.objects[0]


def insert_patch(builder, source):
    uv = source.data.uv_layers.active.data
    for p in source.data.polygons:
        material = source.data.materials[p.material_index].name.split(".")[0]
        verts = [tuple(source.data.vertices[i].co+PAD) for i in p.vertices]
        coords = [tuple(uv[i].uv) for i in p.loop_indices]
        builder.triangle(verts,coords,material)


def water_builder():
    b=Builder()
    rows=[y for y in ROW_Y if WATER_START <= y <= LENGTH]
    for j,(lo,hi) in enumerate(zip(rows,rows[1:])):
        for a,c in zip(CHANNEL_U,CHANNEL_U[1:]):
            values=[(a,lo),(c,lo),(c,hi),(a,hi)]
            for choice in ((0,1,2),(0,2,3)):
                coords=[values[i] for i in choice]
                points=[(mix(*shoreline_x(y),u),y,WATER) for u,y in coords]
                uvs=[(u,(y-WATER_START)/(LENGTH-WATER_START)) for u,y in coords]
                b.triangle(points,uvs,"Lake watercolor")
    return b


def gray_materials():
    return {label: BASE["paint"]("Geometry | " + label, value) for label,value in {
        "GrassFlat":"A6B1A1", "MudBank":"AA9F91", "MossStone":"8E9F96", "ShallowMargin":"92ACAA",
        "Lake watercolor":"8FA9AB"}.items()}


def paint_lake(output):
    manifest=json.loads((MAT4/"asset_manifest.json").read_text())
    rel=manifest["materials"]["Water_Lake"]["file"]
    original=MAT4/rel
    source_hash=digest(original)
    check(source_hash==manifest["files"][rel], "MAT-004 lake PNG hash")
    original_image=bpy.data.images.load(str(original),check_existing=False)
    original_image.colorspace_settings.name="Non-Color"
    w,h=original_image.size[:]
    pixels=np.empty(w*h*4,dtype=np.float32)
    original_image.pixels.foreach_get(pixels)
    colors=pixels.reshape(h,w,4)[..., :3]
    indices=np.rint(np.linspace(110,w-111,SIZE)).astype(int)
    colors=colors[np.ix_(indices,indices)]
    bpy.data.images.remove(original_image)
    axis=np.linspace(0,1,SIZE)
    rows=np.linspace(WATER_START,LENGTH,SIZE)
    distances=np.array([[depth(u,y) for u in axis] for y in rows])
    opacity=np.clip(distances/.225,0,1)
    opacity=opacity*opacity*(3-2*opacity)*.89
    edge=(1-np.clip(distances/.46,0,1))[...,None]
    near=np.array((.64,.75,.70))
    cool=np.array((.61,.72,.77))
    color=.73*colors+.27*(cool+(near-cool)*edge)
    array=np.clip(np.rint(255*np.dstack((color,opacity))),0,255).astype(np.uint8)
    border=np.concatenate((array[0,:,3],array[-1,:,3],array[:,0,3],array[:,-1,3]))
    check(not np.any(border) and int(array[...,3].max())==227,"alpha edges")
    relative=Path(RGBA_FILE)
    path=output/relative
    path.parent.mkdir()
    def chunk(name,data):
        return struct.pack(">I",len(data))+name+data+struct.pack(">I",zlib.crc32(name+data))
    filtered=b"".join(b"\x00"+row.tobytes() for row in array[::-1])
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">2I5B",SIZE,SIZE,8,6,0,0,0))
                     +chunk(b"IDAT",zlib.compress(filtered,9))+chunk(b"IEND",b""))
    name="Water_Lake"
    with bpy.data.libraries.load(str(MAT4/"MAT-004_water_surfaces.blend"),link=False) as (_,target):
        target.materials=[name]
    mat,=target.materials
    mat.name="Lake watercolor"
    mat.node_tree.nodes.clear()
    shader=mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value=manifest["materials"][name]["roughness"]
    shader.inputs["Specular IOR Level"].default_value=.28
    output_node=mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
    tex=mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image=bpy.data.images.load(str(path),check_existing=False)
    tex.image.alpha_mode="STRAIGHT"
    tex.image.pack()
    tex.image.filepath="//"+RGBA_FILE
    tex.extension="EXTEND"
    tex.location=(-380,30)
    output_node.location=(270,50)
    mat.node_tree.links.new(tex.outputs["Color"],shader.inputs["Base Color"])
    mat.node_tree.links.new(tex.outputs["Alpha"],shader.inputs["Alpha"])
    mat.node_tree.links.new(shader.outputs[0],output_node.inputs["Surface"])
    mat.use_backface_culling=True
    stats={"path":RGBA_FILE,"sha256":digest(path),"source_png":"../../MAT-004/v001/"+rel,
           "source_png_sha256":source_hash,"size_px":[SIZE,SIZE],"max_alpha_255":227,
           "partial_alpha_pixels":int(np.count_nonzero((array[...,3]>0)&(array[...,3]<227))),
           "edge_max_alpha_255":int(border.max()),"fade_full_at_depth_BU":.225,
           "source_blend_sha256":digest(MAT4/"MAT-004_water_surfaces.blend"),
           "source_blend_manifest_sha256":manifest["files"]["MAT-004_water_surfaces.blend"]}
    return mat,stats


def make_motion(static):
    """Blender review uses a slow periodic tonal drift while keeping the shoreline alpha and geometry."""
    mat=static.copy()
    mat.name="Review | slow lake reflections"
    n=mat.node_tree.nodes
    links=mat.node_tree.links
    shader=next(x for x in n if x.type=="BSDF_PRINCIPLED")
    tex=next(x for x in n if x.type=="TEX_IMAGE")
    uv=n.new("ShaderNodeTexCoord")
    stretch=n.new("ShaderNodeVectorMath")
    stretch.operation="MULTIPLY"
    stretch.inputs[1].default_value=(2.8,16,1)
    links.new(uv.outputs["UV"],stretch.inputs[0])
    noise=n.new("ShaderNodeTexNoise")
    noise.noise_dimensions="4D"
    noise.inputs["Scale"].default_value=1.4
    noise.inputs["Detail"].default_value=1.5
    noise.inputs["Roughness"].default_value=.54
    links.new(stretch.outputs[0],noise.inputs["Vector"])
    for frame,value in ((1,0),(49,.24),(97,0)):
        noise.inputs["W"].default_value=value
        noise.inputs["W"].keyframe_insert(data_path="default_value",frame=frame)
    ramp=n.new("ShaderNodeMapRange")
    ramp.inputs["To Min"].default_value=.80
    ramp.inputs["To Max"].default_value=1.15
    links.new(noise.outputs["Fac"],ramp.inputs[0])
    multiplier=n.new("ShaderNodeMixRGB")
    multiplier.blend_type="MULTIPLY"
    multiplier.inputs[0].default_value=.40
    links.new(tex.outputs["Color"],multiplier.inputs[1])
    links.new(ramp.outputs[0],multiplier.inputs[2])
    links.new(multiplier.outputs[0],shader.inputs["Base Color"])
    uv.location=(-940,-180)
    stretch.location=(-730,-180)
    noise.location=(-510,-220)
    ramp.location=(-300,-200)
    multiplier.location=(-80,-175)
    return mat


def rebuild_materials(item,mats):
    for i,material in enumerate(item.data.materials):
        label=material.name.split(" | ")[-1]
        item.data.materials[i]=mats[label]


def load_context(path,names):
    with bpy.data.libraries.load(str(path),link=False) as (_,target):
        target.objects=list(names)
    return dict(zip(names,target.objects))


def patch_water(parent):
    if not ENV3.is_file():
        return
    pool=load_context(ENV3,["ShallowPool_RestPatch"])["ShallowPool_RestPatch"]
    obj(parent,"Review | ENV-003 RestPatch water",pool.data,PAD)


def bed_tree(item):
    return BVHTree.FromPolygons([v.co for v in item.data.vertices],[tuple(p.vertices) for p in item.data.polygons],
                                all_triangles=True)


def measure(water, land, patch):
    bvh=bed_tree(land)
    wave=water.data
    check(all(p.normal.z > .99999 for p in wave.polygons),"water normals")
    counts=Counter()
    for p in wave.polygons:
        counts.update(tuple(sorted((a,b))) for a,b in zip(p.vertices,(*p.vertices[1:],p.vertices[0])))
    check(max(counts.values())==2,"overlapping water edges")
    boundary={j for i,edge in counts.items() if edge==1 for j in i}
    # Uniform topology despite the shape shifting along the route.
    perimeter=[wave.vertices[i].co for i in boundary]
    # The two objects intentionally share the exact edge coordinates, including the lake tips.
    bank_coords={(round(v.co.x,6),round(v.co.y,6)):v.co.z for v in land.data.vertices}
    perimeter_hits=[abs(bank_coords[(round(v.x,6),round(v.y,6))]-v.z) for v in perimeter]
    max_rim=max(perimeter_hits)
    check(max_rim < 2e-6,("shoreline gap",max_rim))
    count, min_cover, max_dry = 0, math.inf,0.0
    for poly in wave.polygons:
        mt=[wave.vertices[i].co for i in poly.vertices]
        for a,b,c in ((1/3,1/3,1/3),(.16,.42,.42),(.42,.16,.42),(.42,.42,.16)):
            pt=mt[0]*a+mt[1]*b+mt[2]*c
            hit,*_=bvh.ray_cast(Vector((pt.x,pt.y,2)),Vector((0,0,-1)),4)
            check(hit is not None,("exposed bed",pt))
            min_cover=min(min_cover,WATER-hit.z)
            max_dry=max(max_dry,hit.z-WATER)
            count+=1
    check(max_dry < 2e-6,("water covers dry terrain",max_dry))
    approx=sum(p.area for p in wave.polygons)
    y_values=[y for y in ROW_Y if WATER_START<=y<=LENGTH]
    expected=sum((shape(a)[1]+shape(b)[1])*(b-a) for a,b in zip(y_values,y_values[1:]))
    check(abs(approx-expected) < .0005, ("water area",approx,expected))
    seam=[]
    rest=[]
    coords={(round(v.co.x,6),round(v.co.y,6)):v.co.z for v in land.data.vertices}
    for v in patch.data.vertices:
        p=v.co+PAD
        diff=abs(coords[(round(p.x,6),round(p.y,6))]-p.z)
        rest.append(diff)
        if max(abs(v.co.x),abs(v.co.y))>4.999:
            seam.append(diff)
    check(len(seam)==64 and max(seam)<=HEIGHT_TOL and max(rest)<=HEIGHT_TOL,max(rest))
    # Ascend the lake from checkpoint A and keep the central corridor open through the inlet.
    fly=[]
    clearance=math.inf
    for index in range(109):
        y=WATER_START+.5*index
        center,half=shape(y)
        center+=1.6
        available=2*half
        if 10.5<=y<=48.5:
            fly.append(available)
        for x in (center-.41*half,center,center+.41*half):
            hit,*_=bvh.ray_cast(Vector((x,y,2)),Vector((0,0,-1)),4)
            check(hit is not None,("route bed",x,y))
            clearance=min(clearance, 8/SCALE-hit.z)
    check(min(fly)>15 and clearance>.44,("route",min(fly),clearance))
    approach=[]
    for x in np.linspace(3.0,shoreline_x(9)[0]-.70,20):
        hit,*_=bvh.ray_cast(Vector((float(x),9,2)),Vector((0,0,-1)),4)
        check(hit is not None and hit.z>WATER+.05,("dry land approach",x,hit))
        approach.append(hit.z-WATER)
    full_span=[2*shape(y)[1] for y in y_values]
    return {
        "water_triangles":len(wave.polygons),"shore_triangles":len(land.data.polygons),
        "assembled_length_BU":LENGTH-WATER_START,
        "maximum_water_width_BU":max(full_span),
        "projected_water_area_BU2":approx,"area_error_BU2":abs(approx-expected),
        "matched_rim_vertex_count":len(perimeter),"max_rim_height_match_error_BU":max_rim,
        "wet_interior_rays":count,"maximum_dry_intrusion_BU":max_dry,
        "minimum_water_depth_under_interior_probes_BU":min_cover,
        "rest_patch_reused_vertices":len(rest),"rest_patch_rim_vertices":len(seam),
        "rest_patch_max_rim_step_BU":max(seam),"rest_patch_max_geometry_delta_BU":max(rest),
        "dry_approach_probe_count":20,"dry_approach_smallest_height_above_water_BU":min(approach),
        "central_y_10_5_to_48_5_min_water_width_BU":min(fly),
        "traverse_cross_section_count":109,"traverse_altitude_BU":8/SCALE,
        "minimum_vertical_traverse_clearance_BU":clearance,
    }


def tex_metadata(water_mat, lake, terrain):
    mat3=json.loads((MAT3/"asset_manifest.json").read_text())
    files={}
    for mat in terrain.data.materials:
        node=next(n for n in mat.node_tree.nodes if n.type=="TEX_IMAGE")
        rel=mat3["materials"][mat.name]["file"]
        check(node.image.packed_file is not None,mat.name)
        hash_value=sha256(node.image.packed_file.data).hexdigest()
        check(hash_value==digest(MAT3/rel)==mat3["files"][rel],mat.name)
        files[mat.name]={"sha256":hash_value,"path_relative_to_candidate":"../../MAT-003/v001/"+rel,
                         "size_px":list(node.image.size),"wrap":"repeat U/V"}
    files[water_mat.name]=lake
    return files


def export_one(path,item):
    bpy.ops.object.select_all(action="DESELECT")
    item.select_set(True)
    bpy.context.view_layer.objects.active=item
    result=bpy.ops.export_scene.gltf(filepath=str(path),export_format="GLB",use_selection=True,
                                    export_yup=True,export_animations=False,export_extras=True)
    check(result=={"FINISHED"},(path,result))


def signature(f):
    mesh=f.data
    mesh.calc_loop_triangles()
    uv=mesh.uv_layers.active.data
    items={}
    for t in mesh.loop_triangles:
        vs=[]
        ns=[]
        for i in t.loops:
            p=mesh.vertices[mesh.loops[i].vertex_index].co
            vs.append(tuple(round(v,5) for v in (*p,*uv[i].uv)))
            ns.append(mesh.corner_normals[i].vector.copy())
        pivot=min(range(3),key=lambda i:vs[i])
        label=mesh.materials[t.material_index].name.split(".")[0]
        key=(label,*vs[pivot:],*vs[:pivot])
        check(key not in items,(f.name,"duplicate face",key))
        items[key]=ns[pivot:]+ns[:pivot]
    return items


def reimport(folder, originals, textures):
    imported,result={},{}
    for name, item in originals.items():
        path=folder/f"ENV-008_{name}.glb"
        doc,blob=BASE["glb_chunks"](path)
        node,=doc["nodes"]
        check(node["name"]==name and node.get("translation",[0]*3)==[0]*3
              and node.get("rotation",[0,0,0,1])==[0,0,0,1] and node.get("scale",[1]*3)==[1]*3 and
              not doc.get("animations"),node)
        accessor=[doc["accessors"][p["attributes"]["POSITION"]] for p in doc["meshes"][0]["primitives"]]
        positions=[v.co for v in item.data.vertices]
        xyz=[[min(p[i] for p in positions),max(p[i] for p in positions)] for i in range(3)]
        x,y,z=xyz
        expected=[x,z,[-y[1],-y[0]]]
        bounds=[[min(p["min"][i] for p in accessor),max(p["max"][i] for p in accessor)] for i in range(3)]
        check(max(abs(v-w) for v,w in zip(sum(bounds,[]),sum(expected,[]),strict=True))<HEIGHT_TOL,(name,bounds))
        if name=="LakeWide":
            mat,=doc["materials"]
            check(mat["alphaMode"]=="BLEND" and mat.get("doubleSided",False)==False,mat)
        embeds={}
        for mat in doc["materials"]:
            label=mat["name"]
            tex=doc["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
            image=doc["images"][tex["source"]]
            buff=doc["bufferViews"][image["bufferView"]]
            start=buff.get("byteOffset",0)
            checksum=sha256(blob[start:start+buff["byteLength"]]).hexdigest()
            check(image["mimeType"]=="image/png" and checksum==textures[label]["sha256"],(label,checksum))
            if name=="LakeWide":
                sampler=doc["samplers"][tex["sampler"]]
                check(sampler["wrapS"]==sampler["wrapT"]==33071,sampler)
            embeds[label]=checksum
        old=set(bpy.data.objects)
        status=bpy.ops.import_scene.gltf(filepath=str(path),merge_vertices=False,import_pack_images=True)
        check(status=={"FINISHED"},(name,status))
        recovered,=set(bpy.data.objects)-old
        signs=signature(item)
        new_signs=signature(recovered)
        check(new_signs.keys()==signs.keys(),(name,"mesh face/winding/material/UV signature mismatch"))
        angle=max(BASE["angle"](a,b) for key in signs for a,b in zip(signs[key],new_signs[key],strict=True))
        check(angle<.075,(name,angle))
        check(recovered.location.length==0 and tuple(recovered.scale)==(1,1,1),name)
        imported[name]=recovered
        result[name]={"triangles":len(new_signs),"max_normal_angle_degrees":angle,
                      "glTF_bounds_XYZ_BU":bounds,"embedded_PNG_SHA256":embeds}
    return imported,result


def stage(scene,items,materials,output,mode):
    geo=group("Lake asset pair and checkpoint",scene.collection)
    for name,item in items.items():
        prop=obj(geo,"View | "+name,item.data)
        if name=="LakeWide" and materials.get("motion"):
            slot=prop.material_slots[0]
            slot.link="OBJECT"
            slot.material=materials["motion"]
    if mode!="graybox":
        patch_water(geo)
    # The exported module's west edge is x = -1. Review context begins at that exact edge.
    # Give the view a subdued plateau that preserves the silhouette of the lake.
    context=materials["GrassFlat"]
    rest=BASE["rectangle"](geo,"Review only | overlook west", -185,PATCH_WEST,-7.5,80,0,context)
    fore=BASE["rectangle"](geo,"Review only | checkpoint approach", -185,185,-30,-7.5,0,context)
    # Neutral higher foothill wash is kept outside the wing corridor.
    backing=materials["horizon"]
    BASE["rectangle"](geo,"Review only | far foothill floor",-190,180,-12,230,-.74,backing)
    for item in (rest,fore):
        uv=item.data.uv_layers.new(name="UVMap")
        for loop in item.data.loops:
            uv.data[loop.index].uv=ground_uv(item.data.vertices[loop.vertex_index].co)
    studio=BASE["studio"](scene,scene.collection)
    key=next(o for o in studio.objects if o.type=="LIGHT")
    key.data.energy=1.3
    background=scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value=(.72,.76,.79,1)
    background.inputs["Strength"].default_value=.65
    cam=BASE["camera"](studio,"Checkpoint A | fixed gameplay rear",(0,-7,3),(0,0,0))
    bird=BASE["add_goose"](geo)
    BASE["pose_at"](cam,bird,(0,0),Vector((0,1)))
    scene.render.resolution_x,scene.render.resolution_y=FRAME
    report=check_view(scene,cam,items["LakeShore"])
    if mode in ("graybox","preview"):
        BASE["render"](scene,cam,output,mode+"_checkpoint_A",FRAME,24 if mode=="preview" else 14)
        bird.hide_render=True
        rest.hide_render=fore.hide_render=True
        top=BASE["camera"](studio,"Survey | entire lake",(16,27.75,95),(16,27.75,0),74)
        BASE["render"](scene,top,output,mode+"_top",(1040,1040),18 if mode=="preview" else 9)
        bird.hide_render=False
        rest.hide_render=fore.hide_render=False
    if mode=="preview":
        BASE["pose_at"](cam,bird,(0,0),Vector((.48,.8772684879)).normalized())
        BASE["render"](scene,cam,output,"preview_lake_route_heading",FRAME,24)
        BASE["pose_at"](cam,bird,(13.6,12.2),Vector((.23,.9731906288)).normalized())
        BASE["render"](scene,cam,output,"preview_approach",FRAME,24)
        BASE["pose_at"](cam,bird,(0,0),Vector((0,1)))
    if mode=="roundtrip":
        BASE["render"](scene,cam,output,"preview_glb_roundtrip",FRAME,24)
    BASE["set_preview_workspace"](scene,cam)
    scene.render.filepath="//review.png"
    return report


def check_view(scene,cam,ground):
    bvh=bed_tree(ground)
    bpy.context.view_layer.update()
    probes={"lake_near_bank":[(shoreline_x(y)[0]+.85,y,WATER) for y in (8,18)],
            "lake_opposite_bank":[(shoreline_x(y)[1]-.6,y,WATER) for y in (36,47)],
            "lake_visible_far_tip":[(shape(57)[0]+1.6,57,WATER)],
            "rest_patch_surface":[(2.4,8.8,.005),(5.5,10,.005),(3.1,12.2,.005)]}
    lo=[[],[]]
    item={}
    for label,points in probes.items():
        markers=[]
        for p in points:
            v=Vector(p)
            projected=world_to_camera_view(scene,cam,v)
            check(0<projected.x<1 and 0<projected.y<1 and projected.z>0,(label,tuple(projected)))
            d=v-cam.location
            hit,*_=bvh.ray_cast(cam.location,d.normalized(),d.length-.018)
            if hit is not None:
                continue
            if label.startswith("lake"):
                lo[0].append(projected.x)
                lo[1].append(projected.y)
            markers.append([round(projected.x*FRAME[0],3),round((1-projected.y)*FRAME[1],3)])
        check(markers,(label,points))
        item[label]=markers
    return {"frame_px":list(FRAME),"checkpoint_A_BU":[0,0,0],"heading_XY":[0,1],
            "normalized_camera_geometry":{"distance_game_units":180,"pitch_parameter_rad":.48,"vertical_FOV_degrees":50,
                                          "target_height_game_units":6,"flight_height_game_units":8},
            "see_both_banks_and_rest_probe_pixels_from_top_left":item,
            "lake_sample_projection_extent_px":[(max(v)-min(v))*FRAME[i] for i,v in enumerate(lo)]}


def render_motion(scene,out,frames):
    if frames<2:
        return
    folder=out/"wind_frames"
    folder.mkdir()
    cam=scene.camera
    original=scene.frame_current
    for n in range(frames):
        scene.frame_set(1 + round(n*96/frames))
        BASE["render"](scene,cam,folder,f"{n:04d}",FRAME,10)
    scene.frame_set(original)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--video-frames",type=int,default=0)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    check(not any(output.iterdir()),"Empty output required")
    if args.verify:
        p=args.verify.resolve()
        bpy.ops.wm.open_mainfile(filepath=str(p/(STEM+".blend")))
        original={n:bpy.data.objects[n] for n in SOURCE_NAMES}
        source=patch_source()
        meta=json.loads((p/"asset_manifest.json").read_text())
        BASE["fresh_scene"]("Independent GLB reimport ENV-008")
        imported,glb=reimport(p,original,meta["textures"])
        measurements=measure(*[imported[n] for n in SOURCE_NAMES],source)
        expected=json.loads((p/"qa.json").read_text())
        check(glb==expected["glb_reimport"],"independent GLB metrics")
        check(measurements==expected["roundtrip_assembly"],"independent reassembly metrics")
        BASE["write_json"](output/"recheck.json",{"result":"pass","glb_reimport":glb,"roundtrip_assembly":measurements})
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    library=bpy.context.scene
    library.name="ENV-008 | Asset pair"
    library.unit_settings.system="NONE"
    lib_group=group("LakeWide + LakeShore at shared origin",library.collection)
    mats=gray_materials()
    patch=patch_source()
    ground=Builder()
    quad_rows(ground,[row_points(y) for y in ROW_Y])
    insert_patch(ground,patch)
    lake=water_builder()
    items={"LakeWide":lake.make(lib_group,"LakeWide",mats),"LakeShore":ground.make(lib_group,"LakeShore",mats)}
    items["LakeWide"]["z_reference_BU"]=WATER
    items["LakeShore"]["embedded_patch_center_xyz_BU"]=tuple(PAD)
    items["LakeWide"]["checkpoint_A_xyz_BU"]=(0,0,0)
    pre=measure(items["LakeWide"],items["LakeShore"],patch)
    scene=BASE["fresh_scene"]("Gray assembly")
    stage(scene,items,dict(mats,horizon=BASE["paint"]("Gray studio surroundings","CBD0C5")),output,"graybox")
    bpy.data.scenes.remove(scene)
    bpy.data.objects.remove(patch,do_unlink=True)
    bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=False,do_recursive=True)
    sources,_=BASE["load_materials"]()
    patch=patch_source()
    for label,material in sources.items():
        existing=bpy.data.materials.get(label)
        if existing is not None and existing!=material:
            existing.name="Source patch material | "+label
        material.name=label
    water,atlas=paint_lake(output)
    mats=dict(sources,**{"Lake watercolor":water})
    for n,item in items.items(): rebuild_materials(item,mats)
    textures=tex_metadata(water,atlas,items["LakeShore"])
    bpy.context.window.scene=library
    for name,item in items.items(): export_one(output/f"ENV-008_{name}.glb",item)
    scene=BASE["fresh_scene"]("ENV-008 | Checkpoint A and lake")
    mats["horizon"]=BASE["paint"]("Pale far bank","BBC9C5")
    visible=stage(scene,items,mats,output,"preview")
    anim=BASE["fresh_scene"]("ENV-008 | Review-only slow water")
    look=dict(mats,motion=make_motion(water))
    stage(anim,items,look,output,"motion")
    anim.render.fps=24
    anim.frame_start,anim.frame_end=1,97
    anim.frame_set(1)
    animated_bird=next(o for o in anim.objects if o.name.startswith("Review | CHR-001 neutral pose"))
    BASE["pose_at"](anim.camera,animated_bird,(13.6,12.2),Vector((.23,.9731906288)).normalized())
    render_motion(anim,output,args.video_frames)
    bpy.context.window.scene=scene
    bpy.ops.wm.save_as_mainfile(filepath=str(output/(STEM+".blend")))
    after=BASE["fresh_scene"]("ENV-008 | Reassembly from independently reimported GLBs")
    imported,roundtrip=reimport(output,items,textures)
    post=measure(imported["LakeWide"],imported["LakeShore"],patch)
    for mesh in imported.values():
        mesh.hide_render=True
    stage(after,imported,mats,output,"roundtrip")
    spec=json.loads(SPEC.read_text())
    source_hashes={
        "ENV-001_geometry_and_review_utilities":digest(LIBRARY/"ENV-001/v001/ENV-001_generate.py"),
        "ENV-002_patch_blend":digest(ENV2),
        "ENV-003_preview_only_pool_blend":digest(ENV3),
        "MAT-004_blend":digest(MAT4/"MAT-004_water_surfaces.blend"),
        "CHR-001_review_only_blend":digest(CHR),
    }
    BASE["write_json"](output/"asset_manifest.json",{
        "id":"ENV-008","version":"v001","status":"needs_review",
        "execution_order_1_based":spec["execution_order"].index("ENV-008")+1,
        "depends":["ENV-001/v001","ENV-002/v001","MAT-004/v001"],
        "additional_inputs":{"MAT-003/v001":"shore textures","ENV-003/v001":"review-only pools",
                             "CHR-001/v001":"review-only scale reference"},
        "source_SHA256":source_hashes,"blender":bpy.app.version_string,
        "blender_file":STEM+".blend","variants":{n:f"ENV-008_{n}.glb" for n in SOURCE_NAMES},
        "placement":{"assembly_BU":[0,0,0],"heading":[0,1],"rotation_degrees":0,
                     "recommended_checkpoint_A_BU":[0,0,0],"shore_west_edge_x_BU":PATCH_WEST,
                     "rest_patch_center_xyz_BU":list(PAD),"water_surface_Z_BU":WATER,
                     "axes":{"from_BLENDER":"[x,y,z]","to_glTF":"[x,z,-y]"}},
        "textures":textures,
        "rights":"Original project geometry; reuse of project-owned source artwork by dependency.",
        "preview_camera":visible,
    })
    BASE["write_json"](output/"qa.json",{
        "id":"ENV-008","version":"v001","status":"needs_review",
        "graybox_assembly":pre,"roundtrip_assembly":post,"glb_reimport":roundtrip,"checkpoint_A_review":visible,
        "tolerances":{"position_BU":HEIGHT_TOL,"shoreline_height_BU":2e-6,"area_BU2":.0005,
                       "corner_normal_roundtrip_degrees":.075,"roundtrip_signature_coordinates_and_UVs_decimals":5},
        "app_baseline":{"source":"plans/active/goose-preview-model-cleanup.md","iOS_simulator":"27.2",
                        "prior_test_count":340,"same_build_rerun_in_this_task":False},
        "pending":["Owner art review of actual fork proportions and visual comparison to mountain pass",
                   "Engine fork choice, replenishment, collision and clearances, USDZ and iPhone/iPad review",
                   "Runtime transparent sorting and slow water/cloud shading via FX-006"],
    })


if __name__=="__main__":
    main()
