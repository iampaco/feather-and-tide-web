"""Render the S2 fork evidence using the delivered lake and pass at checkpoint A."""
import argparse
from pathlib import Path
import runpy
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree


HERE=Path(__file__).resolve().parent
P=runpy.run_path(str(HERE/"ENV-010_generate.py"))
B=P["BASE"]
LIB=HERE.parents[1]
LAKE=LIB/"ENV-008/v001"
ENV3=LIB/"ENV-003/v001/ENV-003_wetland_water.blend"
CHECKPOINT=(0.,0.)


def uv_xy(item):
    uv=item.data.uv_layers.new(name="TerrainUV")
    for loop in item.data.loops:
        p=item.data.vertices[loop.vertex_index].co
        uv.data[loop.index].uv=((p.x+5)/10,(p.y+5)/10)


def ray_tree(items):
    v,f=[],[]
    for item in items:
        first=len(v)
        v.extend(item.matrix_world @ p.co for p in item.data.vertices)
        f.extend(tuple(first+i for i in p.vertices) for p in item.data.polygons)
    return BVHTree.FromPolygons(v,f,all_triangles=False)


def lay_right_bank(parent, lake, material):
    # Extend the lake's outer eastern edge rather than co-planar overlaying the shore.
    eastern={}
    for vertex in lake.data.vertices:
        x,y,z=vertex.co
        if y not in eastern or x>eastern[y][0]:
            eastern[y]=(x,y,z)
    strip=sorted(eastern.values(),key=lambda p:p[1])
    geoms=[]
    for a,b in zip(strip,strip[1:]):
        verts=(a,(175,a[1],0),(175,b[1],0),b)
        extension=B["simple_mesh"](parent,"Review far bank",verts,[(0,1,2,3)],material)
        uv_xy(extension)
        geoms.append(extension)
    return geoms


def viewport(scene,cam,targets,occluders):
    tree=ray_tree(occluders)
    size=list(B["GAME_SIZE"])
    reports={}
    for name,points in targets.items():
        projections=[]
        for pos in points:
            endpoint=Vector(pos)
            co=world_to_camera_view(scene,cam,endpoint)
            unit=endpoint-cam.location
            hit,*_=tree.ray_cast(cam.location,unit.normalized(),unit.length-.002)
            projections.append((0 < co.x < 1 and 0 < co.y < 1 and co.z > 0 and hit is None,co.x))
        visible=[x for state,x in projections if state]
        P["check"](len(visible)>=7,(name,len(visible),projections))
        reports[name]={"visible_targets":len(visible),"targets":len(points),"x_pixels":[min(visible)*size[0],
                                                                                       max(visible)*size[0]]}
    left,right=reports["pass_opening"]["x_pixels"],reports["lake_forebay"]["x_pixels"]
    P["check"](left[1]<size[0]/2<right[0],(left,right))
    return reports


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("output",type=Path)
    p.add_argument("--lake-source",type=Path,default=LAKE/"ENV-008_long_lake.blend")
    args=p.parse_args(sys.argv[sys.argv.index("--")+1:])
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    P["check"](not any(output.iterdir()),"Use an empty temporary folder.")
    lake_file=args.lake_source.resolve()
    pass_file=HERE/"ENV-010_short_pass.blend"
    bpy.ops.wm.open_mainfile(filepath=str(pass_file))
    scene=bpy.data.scenes["ENV-010 | Fixed rear and corridor"]
    bpy.context.window.scene=scene
    additions=P["group"]("ENV-008 lake and connected review apron",scene.collection)
    lake=P["append"](lake_file,("LakeWide","LakeShore"))
    for item in lake.values(): additions.objects.link(item)
    camera=scene.camera
    bird=scene.objects["Review | CHR-001 neutral pose"]
    B["pose_at"](camera,bird,CHECKPOINT,Vector((0,1)))
    ground=next(m for m in bpy.data.materials if m.name=="GrassFlat")
    flats=[item for item in scene.objects if item.name.startswith("Flat | ")]
    for item in flats:
        if item.location.x > -1.5: item.hide_render=True
    # The proof scene shares the ground material and phase across the apron.
    # Adjust only review copies, so the production UV connectors are left intact.
    copied=next(it.data for it in flats if not it.hide_render).copy()
    for loop in copied.loops:
        uv=copied.uv_layers.active.data[loop.index].uv
        uv.x+=.35
        uv.y+=.5
    for it in flats:
        it.data=copied
    for it in scene.objects:
        if " assembly" in it.name:
            mesh=it.data.copy()
            for entry in mesh.uv_layers.active.data:
                entry.uv.x+=.35
                entry.uv.y+=.5
            it.data=mesh
    bridge=B["rectangle"](additions,"Review connector strip", -1.5,-1,-25,125,0,ground)
    fore=B["rectangle"](additions,"Review foreground apron", -1,175,-25,-7.5,0,ground)
    back=B["rectangle"](additions,"Review horizon apron", -1,175,63,125,0,ground)
    uv_xy(bridge)
    uv_xy(fore)
    uv_xy(back)
    land=[*lay_right_bank(additions,lake["LakeShore"],ground),bridge,fore,back]
    pools=P["append"](ENV3,("ShallowPool_RestPatch",))["ShallowPool_RestPatch"]
    additions.objects.link(pools)
    pools.location=(4,10,0)
    scene.camera=camera
    scene.render.resolution_x,scene.render.resolution_y=B["GAME_SIZE"]
    bpy.context.view_layer.update()
    y=21.5
    gate=[(P["center"](y)-2.6+i*5.2/12,y,.09) for i in range(13)]
    # Targets lie on surfaces in each option at the same checkpoint pose.
    lake_targets=[(x, y, -.14) for y in (11,12,13) for x in (11,13,14)]
    lake_tree=ray_tree([lake["LakeWide"]])
    for p in lake_targets:
        hit,*_=lake_tree.ray_cast(Vector((p[0],p[1],1)),Vector((0,0,-1)),2)
        P["check"](hit is not None,("lake target does not sit above actual lake mesh",p))
    rest=[(x,y,.035) for y in (7.4,8.55,10.1) for x in (2.8,3.8,4.9)]
    review_terrain=[item for item in scene.objects if " assembly" in item.name]
    visible=viewport(scene,camera,{"pass_opening":gate,"lake_forebay":lake_targets,"rest_patch":rest},
                     [*review_terrain, *[it for it in flats if not it.hide_render],lake["LakeShore"],*land])
    B["render"](scene,camera,output,"preview_checkpoint_a_fork",B["GAME_SIZE"],32)
    P["write_json"](output/"fork_evidence.json",{"result":"pass","fixed_camera":list(CHECKPOINT),
        "source_blends_sha256":{path.name:P["file_hash"](path) for path in (lake_file,pass_file)},
        "visibility":visible,"preview_only":True,"notes":"World origin checkpoint A, with actual mesh assets. Technical S2 joint study."})


if __name__=="__main__":
    main()
