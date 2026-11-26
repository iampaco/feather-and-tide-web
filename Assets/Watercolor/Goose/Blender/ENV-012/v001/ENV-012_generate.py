"""Build three skinned wind-cue trees, audit wind timing/visibility, and verify the GLBs."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import runpy
import struct
import subprocess
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Quaternion, Vector
from mathutils.bvhtree import BVHTree


HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
MAT = LIB / "MAT-001/v001"
ENV7 = LIB / "ENV-007/v001/ENV-007_river_valley.blend"
ENV10 = LIB / "ENV-010/v001/ENV-010_short_pass.blend"
B = runpy.run_path(str(LIB / "ENV-001/v001/ENV-001_generate.py"))
check, obj, collection = (B[n] for n in ("check", "obj", "collection"))
STEM = "ENV-012_wind_trees"
NAMES = ("RiverTree_A", "RiverTree_B", "LeaningTree")
HEIGHTS = (1.84, 1.63, 2.05)
LEAN = (-.045, .08, -.31)
BONES = ("Root", "Stem", "Crown")
MATERIALS = {
    "TreeBark": ("DryGround", "BCBBB4", .92),
    "CanopyShade": ("PlantOpaque", "9DA7A0", .91),
    "CanopyLeaf": ("PlantOpaque", "BAC6BB", .87),
    "CanopyLight": ("PlantOpaque", "D1D3C0", .87),
}
CLIP = "WindCue"
FPS = 24
FRAMES = (1, 9, 15, 22, 27, 34, 43, 49)
STEM_KEYS = (0, 0, 1.6, 4.2, 5.8, 4.7, 1.5, 0)
TOP_KEYS = (0, 0, 6.5, 13.2, 18.5, 15.0, 5.0, 0)
WIND_FRAME = 22
CUE_THRESHOLD = .06
STATIONARY_FRAME = 27
RESCUE_BOX = (1.72, 4.55, 7.28, 12.72)
TARGET = (2.83, 10.35)
WIND_AXIS = Vector((0, -1, 0))
CORRIDOR = {
    "pass": {
        "lead": (-8.7, 10.2),
        "yaw": (-.20, 1.0),
        "trees": ((-4.1, 13.6, .85, .32), (-14.35, 15.7, 1, -.19), (-5.45, 17.5, .94, .46),
                  (-16.25, 20.0, .98, .29), (-6.25, 23.0, .81, -.48), (-16.1, 25.5, .86, .25)),
    },
    "river": {
        "lead": (2.74, 3.75),
        "yaw": (0, 1),
        "trees": ((-3.6, 6.3, .86, -.37), (5.78, 7.7, .90, .41), (-3.6, 10.05, 1, .26),
                  (5.56, 13.65, .83, -.31), (-3.5, 15.4, .76, .43), (5.83, 16.15, .88, .23)),
    },
}


def lerp(a, b, t):
    return a+(b-a)*t


class TreeBuilder:
    def __init__(self):
        self.verts, self.faces, self.uv, self.slots = [], [], [], []

    def vertex(self, p, uv):
        i = len(self.verts)
        self.verts.append(tuple(p))
        self.uv.append(uv)
        return i

    def face(self, points, slot):
        self.faces.append(tuple(points))
        self.slots.append(int(slot))

    def connect(self, rings, slot):
        n = len(rings[0])
        for low, high in zip(rings, rings[1:]):
            for i in range(n):
                j = (i+1) % n
                self.face((low[i], low[j], high[j]), slot)
                self.face((low[i], high[j], high[i]), slot)
        a, b = rings[0], rings[-1]
        for i in range(1, n-1):
            self.face((a[0], a[i+1], a[i]), slot)
            self.face((b[0], b[i], b[i+1]), slot)

    def trunk(self, path, radii, sides, phase=0., flared=False):
        rings = []
        for j, (c, radius) in enumerate(zip(path, radii, strict=True)):
            ring = []
            for i in range(sides):
                t = i * math.tau / sides + phase
                r = radius * (1 + .13 * math.sin(3*t + .40*j))
                if flared and j == 0 and i%2 == 0:
                    r *= 1.65
                ring.append(self.vertex((c.x+r*math.cos(t), c.y+r*math.sin(t), c.z),
                                        (.10+.8*i/sides, .05+.9*j/(len(path)-1))))
            rings.append(ring)
        self.connect(rings, 0)

    def mass(self, center, size, slot, phase, seed):
        """Rounded foliage volumes have gentle irregularity and large clean tonal planes."""
        rng = random.Random(seed)
        rings = []
        n = 10
        cx, cy, cz = center
        rx, ry, rz = size
        for j, theta in enumerate((-1.32, -.98, -.56, -.14, .28, .66, 1, 1.31)):
            layer = []
            for i in range(n):
                azimuth = math.tau * i/n + phase + (j%2)*.095
                r = 1 + .05*math.sin(i*.75+phase) + rng.uniform(-.05,.05)
                taper = math.cos(theta)*r
                z = math.sin(theta)*rz
                x = cx + rx*math.cos(azimuth)*taper + .095*z
                y = cy + ry*math.sin(azimuth)*taper
                layer.append(self.vertex((x,y,cz+z), (.52+.41*math.cos(azimuth)*taper,
                                                      .47+.39*math.sin(azimuth)*taper)))
            rings.append(layer)
        self.connect(rings, slot)

    def build(self, parent, name, mats):
        data = bpy.data.meshes.new(name+"_Skin")
        data.from_pydata(self.verts, [], self.faces)
        data.update()
        check(all(p.area > 1e-9 for p in data.polygons), name)
        uv = data.uv_layers.new(name="TreeUV")
        for mat in mats.values():
            data.materials.append(mat)
        for polygon, slot in zip(data.polygons, self.slots, strict=True):
            polygon.material_index = slot
            polygon.use_smooth = True
            for loop in polygon.loop_indices:
                uv.data[loop].uv = self.uv[data.loops[loop].vertex_index]
        return obj(parent, name, data)


def branch_shape(tree, i):
    h, bend = HEIGHTS[i], LEAN[i]
    a = Vector((bend*.52, -.02, .58*h))
    trunk = [Vector((bend*t**1.41, .027*math.sin(t*math.pi), t*h)) for t in (0,.10,.25,.42,.58,.72,.86)]
    tree.trunk(trunk, (.118,.095,.080,.068,.057,.043,.029), 8, .17, flared=True)
    crown = (
        ((-.22,.018,.768),(.39,.32,.254),1),
        ((.22,.07,.817),(.38,.31,.273),2),
        ((-.055,-.13,.93),(.39,.32,.245),3),
        ((.07,.16,.938),(.32,.28,.218),2),
        ((-.30,-.09,.879),(.28,.26,.20),2),
    ) if i == 0 else (
        ((-.25,.03,.747),(.36,.37,.228),1),
        ((.21,.05,.784),(.41,.37,.238),2),
        ((-.18,-.16,.884),(.34,.32,.229),3),
        ((.19,-.10,.923),(.28,.30,.225),2),
    ) if i == 1 else (
        ((.24,.09,.75),(.33,.33,.204),1),
        ((-.12,.06,.820),(.38,.34,.249),2),
        ((-.32,-.04,.910),(.42,.31,.260),2),
        ((-.56,-.09,.891),(.32,.30,.218),2),
        ((-.38,.13,.959),(.37,.30,.217),3),
    )
    for j, (position, axes, tone) in enumerate(crown):
        c = Vector((position[0]+bend*.8, position[1], position[2]*h))
        tree.mass(c, axes, tone, phase=j*1.62, seed=i*419+j)
        if j < 3:
            e = c - Vector((0,0,axes[2]*.50))
            start = a.lerp(trunk[3], .24*j)
            tree.trunk([start,start.lerp(e,.56),e], (.047,.034,.016), 6, .37*j)


def attach(mesh, parent, i):
    name, h = NAMES[i], HEIGHTS[i]
    data = bpy.data.armatures.new(name+"_Bones")
    rig = obj(parent, name+"_Rig", data)
    rig.show_in_front = True
    data.display_type = "STICK"
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    previous = None
    for bone_name, z0, z1 in zip(BONES, (0,.32,h*.56), (.32,h*.56,h*.91), strict=True):
        bone = data.edit_bones.new(bone_name)
        bone.head = (0,0,z0)
        bone.tail = (0,0,z1)
        if previous:
            bone.parent = previous
            bone.use_connect = True
        previous = bone
    bpy.ops.object.mode_set(mode="OBJECT")
    rig.select_set(False)
    mesh.parent = rig
    mod = mesh.modifiers.new("Rooted tree deformation", "ARMATURE")
    mod.object = rig
    groups = [mesh.vertex_groups.new(name=n) for n in BONES]
    for vertex in mesh.data.vertices:
        root_mix = B["smooth"]((vertex.co.z-.16)/.42)
        crown_mix = B["smooth"]((vertex.co.z-.61*h)/(.22*h))
        amounts = (1-root_mix, root_mix*(1-crown_mix), root_mix*crown_mix)
        for target, amount in zip(groups, amounts, strict=True):
            if amount > 1e-8:
                target.add([vertex.index], amount, "REPLACE")
    for group in rig.pose.bones:
        group.rotation_mode = "QUATERNION"
    rig["wind_axis_Blender_XYZ"] = [-1.0,0.0,0.0]
    rig["windcue_demo_field_frame"] = WIND_FRAME
    mesh["tree_origin_note"] = "Rooted at ground (0,0,0), native +Z up, camera forward +Y"
    mesh.asset_mark()
    mesh.asset_data.description = "Wind direction tree with Root / Stem / Crown deformation"
    return rig


def bend(rig, frame, strength=1, wind_axis=WIND_AXIS):
    # Transform the wind bend axis into bone rest space. Root stays fixed.
    for index, angles in enumerate((STEM_KEYS, TOP_KEYS)):
        channel = rig.pose.bones[BONES[index+1]]
        angle = math.radians(key_value(frame, angles)*strength)
        rest_axis = channel.bone.matrix_local.to_quaternion().inverted() @ wind_axis
        channel.rotation_quaternion = Quaternion(rest_axis, angle)


def key_value(frame, values):
    if frame <= FRAMES[0]:
        return values[0]
    if frame >= FRAMES[-1]:
        return values[-1]
    for i, (a,b) in enumerate(zip(FRAMES, FRAMES[1:])):
        if a <= frame <= b:
            return lerp(values[i],values[i+1],B["smooth"]((frame-a)/(b-a)))
    raise ValueError(frame)


def action(rig):
    for frame in range(FRAMES[0], FRAMES[-1]+1):
        bend(rig, frame)
        for name in BONES[1:]:
            rig.pose.bones[name].keyframe_insert("rotation_quaternion", frame=frame, group=name)
    act = rig.animation_data.action
    act.name = f"{rig.name.removesuffix('_Rig')}_{CLIP}"
    act.use_fake_user = True
    bend(rig, FRAMES[0])
    return act


def material_mapping():
    doc = json.loads((MAT/"asset_manifest.json").read_text())
    source_blend = MAT/"MAT-001_watercolor_master.blend"
    with bpy.data.libraries.load(str(source_blend),link=False) as (_, target):
        target.materials = ["DryGround","PlantOpaque"]
    originals = {m.name:m for m in target.materials}
    results, refs = {}, {}
    for label, (source, tone, roughness) in MATERIALS.items():
        mat = originals[source].copy()
        mat.name = label
        nodes = mat.node_tree.nodes
        shader = next(n for n in nodes if n.type=="BSDF_PRINCIPLED")
        image = next(n for n in nodes if n.type=="TEX_IMAGE")
        mix_color = nodes.new("ShaderNodeMix")
        mix_color.data_type = "RGBA"
        mix_color.blend_type = "MULTIPLY"
        mix_color.inputs[0].default_value = 1.
        mix_color.inputs[7].default_value = B["color"](tone)
        mat.node_tree.links.new(image.outputs["Color"],mix_color.inputs[6])
        mat.node_tree.links.new(mix_color.outputs[2],shader.inputs["Base Color"])
        shader.inputs["Roughness"].default_value = roughness
        mat.use_backface_culling = True
        path = doc["textures"][source]["path"]
        digest = B["file_hash"](MAT/path)
        check(digest==doc["files"][path] and hashlib.sha256(image.image.packed_file.data).hexdigest()==digest,label)
        results[label] = mat
        refs[label] = {"material_template":source,"image_path_relative":"../../MAT-001/v001/"+path,"embedded_png_sha256":digest,
                       "color_factor_srgb":tone,"roughness":roughness}
    return results, refs


def stage_groups(scene):
    root=collection("Tree lineup",scene.collection)
    camrig=B["studio"](scene,scene.collection)
    cam=B["camera"](camrig,"Tree forms | oblique",(3.5,-8.3,3.8),(.0,0,.92),7.)
    base=B["paint"]("Tree study ground","ADB6A9")
    B["rectangle"](root,"Review floor",-20,20,-20,20,-.001,base)
    return root, cam


def copy_instance(group, mesh, rig, point, scale=1., yaw=0.):
    newrig=rig.copy()
    newrig.animation_data_clear()
    group.objects.link(newrig)
    newrig.hide_render = False
    newrig.location = point
    newrig.rotation_euler.z = yaw
    newrig.scale = (scale,)*3
    top=mesh.copy()
    group.objects.link(top)
    top.hide_render = False
    top.parent=newrig
    top.modifiers[0].object=newrig
    for p in newrig.pose.bones:
        p.rotation_quaternion=Quaternion()
    return top,newrig


def animate_preview(scene, pair, index, phase, strength):
    _, rig=pair
    inv=rig.rotation_euler.to_quaternion().inverted()
    for f in range(1,50):
        bend(rig,f-phase,strength,inv@WIND_AXIS)
        for name in BONES[1:]:
            rig.pose.bones[name].keyframe_insert("rotation_quaternion", frame=f, group=name)
    rig.animation_data.action.name=f"ReviewWind_{scene.name}_{index}"
    scene.frame_set(1)


def lineup(variants, folder, name, gust=False):
    scene=B["fresh_scene"](name)
    scene.render.fps=FPS
    root, cam=stage_groups(scene)
    for i, (_,mesh,rig) in enumerate(variants):
        pair=copy_instance(root,mesh,rig,((i-1)*2.12,0,0),yaw=(.31,-.06,.14)[i])
        if gust:
            bend(pair[1],STATIONARY_FRAME,1.,pair[1].rotation_euler.to_quaternion().inverted()@WIND_AXIS)
    B["render"](scene,cam,folder,name,(1050,610),19)
    B["set_preview_workspace"](scene,cam)
    return scene


def append_meshes(path, names, parent):
    with bpy.data.libraries.load(str(path),link=False) as (source,target):
        check(set(names)<=set(source.objects),(path,names))
        target.objects=list(names)
    for item in target.objects:
        parent.objects.link(item)
    return target.objects


def ground_extension(root, name, bounds, material, phase):
    plane=B["rectangle"](root,name,*bounds,0,material)
    layer=plane.data.uv_layers.new(name="TerrainUV")
    for loop in plane.data.loops:
        p=plane.data.vertices[loop.vertex_index].co
        layer.data[loop.index].uv=((p.x+phase[0])/10,(p.y+phase[1])/10)
    return plane


def terrain(scene, where, art):
    root=collection("Review terrain only",scene.collection)
    if where=="pass":
        name=("Pass_Left","Pass_Right","Mouth")
        pile=append_meshes(ENV10,name,root)
        grass=next(mat for mat in pile[0].data.materials if mat.name.split(".")[0]=="GrassFlat")
        i_min,i_max=-21.5,-1.5
        for left,right,back,front in ((-135,135,-45,10),(-135,i_min,10,50),(i_max,135,10,50),
                                        (-135,135,50,160)):
            pile.append(ground_extension(root,"Terrain extension",(left,right,back,front),grass,(21.5,0)))
    else:
        components=("Straight_Bed","Straight_Water","Bend_Bed","Bend_Water","OpenBank_Bed","OpenBank_Water")
        meshes=append_meshes(ENV7,components,root)
        lookup={name:item for name,item in zip(components,meshes,strict=True)}
        for item in meshes:
            item.location=(0,0,-125)
            item.hide_render=True
            item.hide_set(True)
        pile=[]
        for i in range(-3,13):
            name={0:"Bend",1:"OpenBank",3:"Bend"}.get(i,"Straight")
            items=[obj(root,f"{name}_{suffix} | {i}",lookup[f"{name}_{suffix}"].data,(0,10*i,0))
                   for suffix in ("Bed","Water")]
            pile.append(items[0])
        grass=next(mat for mat in lookup["OpenBank_Bed"].data.materials if mat.name.split(".")[0]=="GrassFlat")
        pile.extend(ground_extension(root,"Outside river module",(left,right,-35,125),grass,(5,5))
                    for left,right in ((-135,-5),(5,135)))
    if not art:
        clay=B["paint"]("Context graybox","8A9A99")
        river_gray=B["paint"]("Water graybox","8AA8AB")
        for item in root.objects:
            if item.type=="MESH":
                item.data=item.data.copy()
                mat=river_gray if "Water" in item.name else clay
                for i in range(len(item.data.materials)):
                    item.data.materials[i]=mat
    bpy.context.view_layer.update()
    return pile


def raw_tree(items):
    verts, polys = [], []
    for item in items:
        offset=len(verts)
        verts += [item.matrix_world@v.co for v in item.data.vertices]
        polys += [tuple(offset+i for i in f.vertices) for f in item.data.polygons]
    return BVHTree.FromPolygons(verts,polys,all_triangles=False)


def rendered_points(item):
    mesh=item.evaluated_get(bpy.context.evaluated_depsgraph_get())
    m=mesh.matrix_world
    return [m @ v.co for v in mesh.data.vertices]


def active_tree(items):
    verts,polys=[],[]
    for item in items:
        offset=len(verts)
        verts += rendered_points(item)
        polys += [tuple(offset+i for i in f.vertices) for f in item.data.polygons]
    return BVHTree.FromPolygons(verts,polys,all_triangles=True)


def at_ground(tree,x,y):
    hit,*_=tree.ray_cast(Vector((x,y,30)),Vector((0,0,-1)),60)
    check(hit is not None,(x,y))
    return hit.z


def target_bird(parent, where, art):
    if where!="river":
        return None
    solver=runpy.run_path(str(LIB/"ENV-002/v001/ENV-002_generate.py"))
    data, points, sole=solver["load_standing_mesh"](parent)
    # Retain the ENV-007 actual beached-bank solver and target placement, in its OpenBank module.
    review=collection("Temporary support geometry",parent)
    bed,=append_meshes(ENV7,("OpenBank_Bed",),review)
    _, result=solver["place"](BVHTree.FromPolygons([v.co for v in bed.data.vertices],
                           [tuple(p.vertices) for p in bed.data.polygons]),points,sole,
                           (TARGET[0],TARGET[1]-10),-.27,.80)
    bpy.data.objects.remove(bed,do_unlink=True)
    bpy.data.collections.remove(review)
    bird=obj(parent,"Rescue target | already-delivered standing pose",data,(TARGET[0],TARGET[1],result["root_z_BU"]))
    bird.rotation_euler.z=-.27
    bird.scale=(.8,)*3
    if not art:
        clay=B["paint"]("Goose graybox","DFD4C4")
        for i in range(len(bird.data.materials)):
            bird.data.materials[i]=clay
    return bird


def review_scene(variants, where, art):
    scene=B["fresh_scene"](f"ENV-012 | {where.title()} wind study" if art else "Graybox "+where)
    scene.render.fps=FPS
    scene.render.resolution_x,scene.render.resolution_y=B["GAME_SIZE"]
    scene.frame_start,scene.frame_end=1,49
    context=CORRIDOR[where]
    pieces=terrain(scene,where,art)
    surface=raw_tree(pieces)
    group=collection("Wind trees attached at measured ground",scene.collection)
    instances=[]
    for j,(x,y,scale,yaw) in enumerate(context["trees"]):
        _,mesh,rig=variants[j%len(variants)]
        z=at_ground(surface,x,y)
        pair=copy_instance(group,mesh,rig,(x,y,z),scale,yaw)
        animate_preview(scene,pair,j,(j%3)*.70,.89+.043*j)
        instances.append(pair)
    refs=collection("Non-exported goose reference",scene.collection)
    leader=B["add_goose"](refs)
    bird=target_bird(refs,where,art)
    rig=B["studio"](scene,scene.collection)
    cam=B["camera"](rig,"Source fixed rear",(0,0,1),(0,1,0))
    heading=Vector(context["yaw"]).normalized()
    B["pose_at"](cam,leader,context["lead"],heading)
    B["set_preview_workspace"](scene,cam)
    scene.render.filepath="//review.png"
    bpy.context.view_layer.update()
    return scene,cam,instances,bird,surface


def verify_screen(scene, cam, trees, bird, terrain_tree, where):
    scene.frame_set(1)
    bpy.context.view_layer.update()
    top_rest=[]
    for mesh,_ in trees:
        points=rendered_points(mesh)
        idx=max(range(len(points)),key=lambda i:points[i].z)
        top_rest.append((idx,points[idx]))
    if bird:
        targets=rendered_points(bird)
        xmin,xmax=min(p.x for p in targets),max(p.x for p in targets)
        ymin,ymax=min(p.y for p in targets),max(p.y for p in targets)
        samples = sorted(range(len(targets)),key=lambda i: targets[i].z)[::31]
        rays=[targets[i] for i in samples]
        # These probes sit inside the measured accessible bank including both final wings.
        check(RESCUE_BOX[0]<xmin<xmax<RESCUE_BOX[1] and RESCUE_BOX[2]<ymin<ymax<RESCUE_BOX[3],
              (xmin,xmax,ymin,ymax,RESCUE_BOX))
        bird_proj=[world_to_camera_view(scene,cam,v) for v in targets]
        check(all(0<v.x<1 and 0<v.y<1 for v in bird_proj),where)
        bird_bbox=[[min(p.x for p in bird_proj)*852,max(p.x for p in bird_proj)*852],
                   [min(p.y for p in bird_proj)*393,max(p.y for p in bird_proj)*393]]
    else:
        rays=[]
        bird_bbox=None

    hit_count=0
    box_min=math.inf
    screen_early=[]
    screen_peak=[]
    for frame in range(1,50):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        if frame in (WIND_FRAME-1,STATIONARY_FRAME):
            projected=[]
            for (mesh,_),(idx,original) in zip(trees,top_rest,strict=True):
                current=rendered_points(mesh)[idx]
                position=world_to_camera_view(scene,cam,current)
                if 0<position.x<1 and 0<position.y<1:
                    initial=world_to_camera_view(scene,cam,original)
                    projected.append((initial.x-position.x)*852)
            if frame==WIND_FRAME-1:screen_early=projected
            else:screen_peak=projected
        if bird:
            moving=[mesh for mesh,_ in trees]
            canopy=active_tree(moving)
            for p in rays:
                v=p-cam.location
                max_d=v.length-.002
                check(canopy.ray_cast(cam.location,v.normalized(),max_d)[0] is None,("tree obscures",frame,p))
                check(terrain_tree.ray_cast(cam.location,v.normalized(),max_d)[0] is None,("bank obscures",frame,p))
                hit_count+=1
            for mesh in moving:
                values=rendered_points(mesh)
                gap=min(max(RESCUE_BOX[0]-p.x, p.x-RESCUE_BOX[1], RESCUE_BOX[2]-p.y,p.y-RESCUE_BOX[3])
                        for p in values)
                box_min=min(box_min,gap)
    check(len(screen_early)>=3 and len(screen_peak)>=3 and min(screen_early)>1.4 and min(screen_peak)>2.5,
          (where,screen_early,screen_peak))
    if bird:check(box_min>.2,(where,box_min))
    return {"cue_before_wind_screen_tip_movement_left_px":screen_early,"peak_screen_tip_movement_left_px":screen_peak,
            "frame_before_review_wind_field":WIND_FRAME-1,"review_wind_field_frame":WIND_FRAME,
            "tree_count":len(trees),"rescue_visibility_frames":49 if bird else 0,
            "rescue_total_terrain_and_tree_rays_each":hit_count,
            "rescue_projected_bbox_px":bird_bbox,"rescue_clear_box_min_tree_vertex_gap_BU":box_min if bird else None}


def geometry(variants, scene):
    result={}
    for name,mesh,rig in variants:
        points=[v.co for v in mesh.data.vertices]
        totals=[sum(g.weight for g in v.groups) for v in mesh.data.vertices]
        check(max(abs(t-1) for t in totals) < 2e-7,name)
        used=[sum(any(g.group==i and g.weight>0 for g in v.groups) for v in mesh.data.vertices) for i in range(3)]
        check(all(used),name)
        low=[v.index for v in mesh.data.vertices if v.co.z<.16]
        crown=max(range(len(points)),key=lambda i: points[i].z)
        scene.frame_set(1)
        rest=rendered_points(mesh)
        early=None
        minimum,max_drift,max_shift=math.inf,0.,0.
        for f in range(1,50):
            scene.frame_set(f)
            pose=rendered_points(mesh)
            dx=rest[crown].x-pose[crown].x
            if dx>CUE_THRESHOLD and early is None:early=f
            max_shift=max(max_shift,dx)
            max_drift=max(max_drift,max((pose[i]-rest[i]).length for i in low))
            minimum=min(minimum, min(p.z for p in pose))
            check(dx>-.0001,(name,"opposite cue",f,dx))
        check(early is not None and early < WIND_FRAME,(name,early))
        check(max_drift < 1e-6 and abs(minimum)<1e-6 and max_shift>.20,(name,max_drift,minimum,max_shift))
        check(max((a-b).length for a,b in zip(rest,pose,strict=True))<1e-6,name)
        scene.frame_set(1)
        result[name]={"triangles":len(mesh.data.polygons),"vertices":len(points),"height_BU":max(p.z for p in points),
                      "base_bounds_XY_BU":[[min(points[i][axis] for i in low),max(points[i][axis] for i in low)]
                                           for axis in (0,1)],
                      "bone_vertex_counts":dict(zip(BONES,used,strict=True)),"weight_sum_max_error":max(abs(t-1) for t in totals),
                      "vertex_root_shift_max_BU":max_drift,"crown_tip_peak_left_displacement_BU":max_shift,
                      "cue_first_frame_above_0_06_BU":early,"lead_time_to_review_wind_field_seconds":(WIND_FRAME-early)/FPS,
                      "pose_samples":49}
    return result


def write_export(scene, variants, output):
    for name,mesh,rig in variants:
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True)
        rig.select_set(True)
        bpy.context.view_layer.objects.active=rig
        scene.frame_set(1)
        bpy.ops.export_scene.gltf(filepath=str(output/f"ENV-012_{name}.glb"), export_format="GLB",
                                  use_selection=True,export_yup=True,export_animations=True,
                                  export_force_sampling=True,export_animation_mode="ACTIVE_ACTIONS",
                                  export_anim_single_armature=False,export_anim_slide_to_zero=True,
                                  export_nla_strips_merged_animation_name=name+"_"+CLIP)


def read_data(doc, blob, i):
    a=doc["accessors"][i]
    view=doc["bufferViews"][a["bufferView"]]
    dims={"SCALAR":1,"VEC2":2,"VEC3":3,"VEC4":4,"MAT4":16}[a["type"]]
    dtype={5121:"B",5123:"H",5125:"I",5126:"f"}[a["componentType"]]
    unpack=struct.Struct("<"+dtype*dims)
    start=view.get("byteOffset",0)+a.get("byteOffset",0)
    return [unpack.unpack_from(blob,start+k*view.get("byteStride",unpack.size)) for k in range(a["count"])]


def verify_raw(file, name, refs, mesh):
    document, blob=B["glb_chunks"](file)
    nodes=document["nodes"]
    byname={node["name"]:i for i,node in enumerate(nodes)}
    check(set(BONES) <= byname.keys() and name in byname and name+"_Rig" in byname,byname)
    check(nodes[byname["Stem"]]["children"]==[byname["Crown"]] and nodes[byname["Root"]]["children"]==[byname["Stem"]],name)
    skin,=document["skins"]
    check([nodes[k]["name"] for k in skin["joints"]]==list(BONES),name)
    mesh_node=nodes[byname[name]]
    check(mesh_node.get("skin")==0 and not mesh_node.get("weights"),name)
    inverse=read_data(document,blob,skin["inverseBindMatrices"])
    check(len(inverse)==3 and all(abs(m[15]-1)<1e-7 for m in inverse),name)
    primitives=document["meshes"][mesh_node["mesh"]]["primitives"]
    texture_map={}
    count=0
    observed=[]
    max_weight_error=0.
    for primitive in primitives:
        attrs=primitive["attributes"]
        check({"POSITION","NORMAL","TEXCOORD_0","JOINTS_0","WEIGHTS_0"}<=set(attrs),name)
        count+=len(read_data(document,blob,primitive["indices"]))//3
        observed.extend(read_data(document,blob,attrs["POSITION"]))
        joints=read_data(document,blob,attrs["JOINTS_0"])
        weights=read_data(document,blob,attrs["WEIGHTS_0"])
        check(all(max(r)<3 for r in joints),name)
        max_weight_error=max(max_weight_error,max(abs(sum(w)-1) for w in weights))
        mat=document["materials"][primitive["material"]]
        reference=refs[mat["name"]]
        pbr=mat["pbrMetallicRoughness"]
        check(not mat.get("doubleSided") and mat.get("alphaMode","OPAQUE")=="OPAQUE",name)
        check(abs(pbr["roughnessFactor"]-reference["roughness"])<1e-6,name)
        check(max(abs(float(a)-b) for a,b in zip(pbr["baseColorFactor"],B["color"](reference["color_factor_srgb"]),strict=True))<1e-6,name)
        texture=document["textures"][pbr["baseColorTexture"]["index"]]
        image=document["images"][texture["source"]]
        view=document["bufferViews"][image["bufferView"]]
        i=view["byteOffset"]
        h=hashlib.sha256(blob[i:i+view["byteLength"]]).hexdigest()
        check(image["mimeType"]=="image/png" and h==reference["embedded_png_sha256"],name)
        texture_map[mat["name"]]=h
    check(count==len(mesh.data.polygons) and set(texture_map)==set(refs) and max_weight_error<2e-6,name)
    native=[(v.co.x,v.co.z,-v.co.y) for v in mesh.data.vertices]
    quant=lambda p:tuple(round(x,5) for x in p)
    check(set(map(quant,observed))==set(map(quant,native)),name)
    clip,=document["animations"]
    check(clip["name"]==name+"_"+CLIP,(name,clip["name"]))
    active={}
    for channel in clip["channels"]:
        sampler=clip["samplers"][channel["sampler"]]
        target=channel["target"]
        values=read_data(document,blob,sampler["output"])
        if max(abs(a-b) for r in values for a,b in zip(r,values[0],strict=True))<=1e-6:
            continue
        time=read_data(document,blob,sampler["input"])
        check(target["path"]=="rotation" and sampler["interpolation"] in ("LINEAR","STEP"),(name,target,sampler))
        check(abs(time[0][0])<1e-7 and abs(time[-1][0]-2)<1e-6,(name,time))
        active[nodes[target["node"]]["name"]]=len(time)
    check(set(active)==set(BONES[1:]),(name,active))
    return {"triangles":count,"raw_weight_sum_max_error":max_weight_error,"animated_joint_sample_counts":active,
            "texture_hashes":texture_map,"axis_verified":"x,z,-y"}


def signature(mesh):
    uv=mesh.uv_layers.active.data
    mesh.calc_loop_triangles()
    values={}
    for tri in mesh.loop_triangles:
        loops=list(tri.loops)
        positions=[mesh.vertices[mesh.loops[i].vertex_index].co for i in loops]
        pivot=min(range(3),key=lambda i:tuple(round(v,5) for v in positions[i]))
        order=loops[pivot:]+loops[:pivot]
        key=tuple(tuple(round(x,5) for x in mesh.vertices[mesh.loops[i].vertex_index].co) for i in order)
        check(key not in values, ("duplicate tri",mesh.name,key))
        mat=mesh.materials[tri.material_index].name.split(".")[0]
        values[key]=(mat,[(uv[k].uv.copy(),mesh.corner_normals[k].vector.copy()) for k in order])
    return values


def geometry_tokens(item, poses=None):
    """Map ordered deformation back to bind geometry, independent of UV split and export index order."""
    bas=[tuple(round(x,5) for x in v.co) for v in item.data.vertices]
    points=bas if poses is None else poses
    out={}
    for key,p in zip(bas,points,strict=True):
        if key not in out:
            out[key]=p
        else:
            check((Vector(out[key])-Vector(p)).length<2e-6,(item.name,key))
    return out


def import_checks(folder, name, source_mesh, source_poses, scene, source_refs):
    before={item.as_pointer() for item in bpy.data.objects}
    file=folder/f"ENV-012_{name}.glb"
    info=verify_raw(file,name,source_refs,source_mesh)
    bpy.ops.import_scene.gltf(filepath=str(file),merge_vertices=False)
    new=[item for item in bpy.data.objects if item.as_pointer() not in before]
    rig,=[n for n in new if n.type=="ARMATURE"]
    mesh,=[n for n in new if n.type=="MESH" and n.parent==rig]
    check(mesh.parent==rig and set(b.name for b in rig.data.bones)==set(BONES),name)
    check(max(abs(x-1) for x in mesh.scale)<1e-6 and rig.location.length<1e-6,name)
    check(all(n.type in ("ARMATURE","MESH","EMPTY") for n in new),name)
    source=signature(source_mesh.data)
    back=signature(mesh.data)
    check(set(source)==set(back),(name,len(source),len(back)))
    max_uv,max_angle=0.,0.
    for key,(mat,first) in source.items():
        other,second=back[key]
        check(mat==other,(name,mat,other))
        for (uv1,n1),(uv2,n2) in zip(first,second,strict=True):
            max_uv=max(max_uv,(uv1-uv2).length)
            max_angle=max(max_angle,B["angle"](n1,n2))
    animation=rig.animation_data
    if animation.action is None:
        pairs=[(strip.action,strip.action_slot) for track in animation.nla_tracks for strip in track.strips]
        clip,slot=pairs[0]
        for track in animation.nla_tracks:
            track.mute=True
        animation.action=clip
        animation.action_slot=slot
    check(animation.action is not None,name)
    f0=animation.action.frame_range[0]
    f1=animation.action.frame_range[1]
    check(abs(f1-f0-48)<1e-5,(name,f0,f1))
    error=0.
    for f,expected in source_poses.items():
        scene.frame_set(round(f0+f-1))
        actual=geometry_tokens(mesh,rendered_points(mesh))
        check(set(actual)==set(expected),name)
        error=max(error,max((p-actual[k]).length for k,p in expected.items()))
    check(error<4e-5 and max_uv<2e-6 and max_angle<.04,(name,error,max_uv,max_angle))
    scene.frame_set(round(f0))
    return (name,mesh,rig),dict(info,per_pose_max_deformed_vertex_delta_BU=error,vertex_comparison_sample_frames=list(source_poses),max_uv_delta=max_uv,
                               max_normal_angle_degrees=max_angle,roundtrip_split_vertex_count=len(mesh.data.vertices))


def source_motion(scene, variants):
    return {name:{frame:geometry_tokens(mesh,rendered_at(scene,mesh,frame)) for frame in range(1,50)} for name,mesh,_ in variants}


def rendered_at(scene, mesh, frame):
    if bpy.context.window.scene!=scene:
        bpy.context.window.scene=scene
    scene.frame_set(frame)
    return rendered_points(mesh)


def video(folder, areas, ffmpeg):
    directory=folder/"_video_frames"
    directory.mkdir()
    idx=0
    for scene,cam in areas:
        bpy.context.window.scene=scene
        for frame in (1,4,7,10,13,16,19,22,25,28,31,34,37,40,43,46,49):
            scene.frame_set(frame)
            B["render"](scene,cam,directory,f"{idx:04d}",B["GAME_SIZE"],9)
            idx+=1
    file=folder/"preview_WindCue.mp4"
    subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-framerate","8","-i",str(directory/"%04d.png"),
                    "-vf","pad=852:394:0:0,fps=24","-an","-pix_fmt","yuv420p","-c:v","libx264","-crf","18",
                    "-movflags","+faststart",str(file)],check=True)
    subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-xerror","-i",str(file),"-f","null","-"],check=True)
    return {"result":"pass","Blender_rendered_frames":idx,"frame_width_before_codec_padding":852,
            "frame_height_before_codec_padding":393,"scene_order":["S2 pass","S3 open bank"],
            "sampled_frames_per_scene":17}


def audit_imports(library, variants, folder, refs, renders, render_output=None):
    bpy.context.window.scene=library
    poses=source_motion(library,variants)
    scene=B["fresh_scene"]("Independent GLB review")
    scene.render.fps=FPS
    checks={}
    imported=[]
    for name,mesh,_ in variants:
        recovered,checks[name]=import_checks(folder,name,mesh,poses[name],scene,refs)
        imported.append(recovered)
        for item in recovered[1:]:
            item.hide_render=True
    if renders:
        source_world=scene
        scene=B["fresh_scene"]("Imported WindCue peak review")
        scene.render.fps=FPS
        root,cam=stage_groups(scene)
        for i,(_,mesh,rig) in enumerate(imported):
            first=rig.animation_data.action.frame_range[0]
            bpy.context.window.scene=source_world
            source_world.frame_set(round(first)+STATIONARY_FRAME-1)
            assessed=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
            frozen=bpy.data.meshes.new_from_object(assessed)
            bpy.context.window.scene=scene
            render_mesh=obj(root,mesh.name+" | imported actual peak",frozen,((i-1)*2.12,0,0))
            render_mesh.rotation_euler.z=(.31,-.06,.14)[i]
        B["render"](scene,cam,render_output or folder,"preview_glb_roundtrip",(1050,610),19)
    return checks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--render-roundtrip",action="store_true",help="Render the independently reimported wind pose.")
    parser.add_argument("--video",action="store_true")
    parser.add_argument("--quick",action="store_true",help="Skip nonessential renders while testing scene QA.")
    parser.add_argument("--ffmpeg",default="/opt/homebrew/bin/ffmpeg")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    check(not any(out.iterdir()),"Use empty output.")
    if args.verify:
        source=args.verify.resolve()
        bpy.ops.wm.open_mainfile(filepath=str(source/f"{STEM}.blend"))
        scene=bpy.data.scenes["ENV-012 | Tree assets at origin"]
        manifest=json.loads((source/"asset_manifest.json").read_text())
        expected=json.loads((source/"qa.json").read_text())
        variants=[(name,bpy.data.objects[name],bpy.data.objects[name+"_Rig"]) for name in NAMES]
        measurements=audit_imports(scene,variants,source,manifest["materials"],args.render_roundtrip,out)
        check(measurements==expected["glb_roundtrip"],"Independent GLB metrics differ.")
        B["write_json"](out/"recheck.json",{"result":"pass","glb_roundtrip":measurements})
        return

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    library=bpy.context.scene
    library.name="ENV-012 | Tree assets at origin"
    library.render.fps=FPS
    library.frame_start,library.frame_end=1,49
    gray={name:B["paint"]("Graybox "+name, color) for name,color in zip(MATERIALS,("927F72","738685","869795","A5AD9E"),strict=True)}
    variants=[]
    for i,name in enumerate(NAMES):
        parent=collection(name+" | Source rig and mesh",library.collection)
        geo=TreeBuilder()
        branch_shape(geo,i)
        mesh=geo.build(parent,name,gray)
        rig=attach(mesh,parent,i)
        action(rig)
        variants.append((name,mesh,rig))
    gray_values=geometry(variants,library)
    if not args.quick:
        lineup_scene=lineup(variants,out,"graybox_lineup")
        bpy.data.scenes.remove(lineup_scene)
    reports={}
    for area in CORRIDOR:
        gray_scene, cam, trees, bird, ground=review_scene(variants,area,False)
        reports[area]=verify_screen(gray_scene,cam,trees,bird,ground,area)
        gray_scene.frame_set(WIND_FRAME-1)
        if not args.quick:B["render"](gray_scene,cam,out,"graybox_"+area,B["GAME_SIZE"],14)
        bpy.data.scenes.remove(gray_scene)
    mats,refs=material_mapping()
    for _, mesh, _ in variants:
        for i,mat in enumerate(mats.values()):
            mesh.data.materials[i]=mat
    bpy.context.window.scene=library
    write_export(library,variants,out)
    if not args.quick:
        lineup(variants,out,"preview_lineup")
        lineup(variants,out,"preview_wind",gust=True)
    comparisons={}
    art_areas=[]
    for area in CORRIDOR:
        s,cam,tree,bird,ground=review_scene(variants,area,True)
        comparisons[area]=verify_screen(s,cam,tree,bird,ground,area)
        check(comparisons[area]==reports[area],(area,"material changed measurement"))
        art_areas.append((s,cam))
        for key,frame in ("before",1),("early",WIND_FRAME-1),("crest",STATIONARY_FRAME):
            s.frame_set(frame)
            if not args.quick:B["render"](s,cam,out,"preview_"+area+"_"+key,B["GAME_SIZE"],22)
    preferred,cam=art_areas[-1]
    bpy.context.window.scene=preferred
    preferred.frame_set(WIND_FRAME-1)
    B["set_preview_workspace"](preferred,cam)
    for s in bpy.data.scenes:
        s.render.filepath="//review.png"
    bpy.ops.wm.save_as_mainfile(filepath=str(out/f"{STEM}.blend"))
    movie=video(out,art_areas,args.ffmpeg) if args.video else None
    measured=audit_imports(library,variants,out,refs,not args.quick)
    filehash=B["file_hash"]
    manifest={"id":"ENV-012","status":"needs_review","version":"v001","execution_order_1_based":24,
         "depends":["MAT-001/v001"],"review_scene_only":["ENV-007/v001","ENV-010/v001","CHR-001/v001","ANM-007/v001"],
         "scene_inputs_sha256":{p.name:filehash(p) for p in (ENV7,ENV10,MAT/"MAT-001_watercolor_master.blend")},
         "materials":refs,"axis_map_Blender_to_glTF":["x","z","-y"],
         "local_root_BU":[0,0,0],"variant_names":list(NAMES),"wind_clip_names":[n+"_"+CLIP for n in NAMES],
         "neutral_pose_frame":1,"recommended_runtime_bend_joints":["Stem","Crown"],
         "controller_reference":{"demo_downwind_Blender_XYZ":[-1,0,0],"demo_downwind_glTF_XYZ":[-1,0,0],
            "sources":"local quaternion pose rotations, per-instance world-aligned preview; runtime direction separate",
            "preview_crosswind_frame":WIND_FRAME,"duration_seconds":2},
         "rights":"Original geometry and actions with project-owned MAT-001 images."}
    B["write_json"](out/"qa.json",{"id":"ENV-012","status":"needs_review","blender":bpy.app.version_string,
         "authoring_order":"graybox geometric and rig audits precede material assignment",
         "source_motion":gray_values,"graybox_visibility":reports,"fixed_rear_visibility":comparisons,
         "glb_roundtrip":measured,"video":movie,
         "pending":["Runtime wind event lead time and directions; visibility across real player headings/screen layout; USDZ / RealityKit and iPhone/iPad."]})
    B["write_json"](out/"asset_manifest.json",manifest)


if __name__=="__main__":
    main()
