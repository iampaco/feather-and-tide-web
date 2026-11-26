"""Build the S0 candidate or verify its delivered Blender and GLB files in a fresh process."""
import argparse
import hashlib
import json
import math
import shutil
import struct
import subprocess
from pathlib import Path

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ID = "LVL-S0"
STEM = "LVL-S0_S0_StartWetland"
SCENE = STEM + ".glb"
FLOCK = STEM + "_ReviewFlock.glb"
BACKDROP = STEM + "_Backdrop.glb"
VIDEO = "preview_fixed_rear.mp4"
BU = .9900 / 27.5
SIZE = (852, 393)
FPS = 24
VIDEO_FPS = 12
LAST = 337
WATER = -.18
EXIT = 36.
ENTRY_NAME = "S0_Entry"
EXIT_NAME = "S0_Exit_to_S1"
FOG_LINE = 33.
START_SLOTS = ((0., 0.), (-3.30, -.18), (-1.66, -.15), (1.66, -.15), (3.30, -.18),
               (-2.54, -1.20), (-.88, -1.25), (.88, -1.25), (2.54, -1.20),
               (-1.80, -2.30), (0., -2.35), (1.80, -2.30))
DELAYS = (0., .065, .10, .04, .12, .105, .146, .056, .155, .079, .117, .09)
KEY_FRAMES = {"takeoff": 25, "glide": 103, "circle": 169, "fog_exit": 313}
SOURCES = {
    "CHR-001": ["CHR-001_goose_rig.blend", "CHR-001_goose_rig.glb"],
    "ANM-002": ["ANM-002_takeoff_climb.blend", "ANM-002_takeoff_climb.glb"],
    "ANM-003": ["ANM-003_glide_circle.blend", "ANM-003_glide_circle.glb"],
    "ENV-002": ["ENV-002_StartMudflat.glb"],
    "ENV-003": ["ENV-003_ShallowPool_StartMudflat.glb"],
    "ENV-005": ["ENV-005_Sparse.glb", "ENV-005_ShoreEdge.glb"],
    "FX-004": ["FX-004_Fog_Start.glb"],
    "ENV-009": ["ENV-009_FarRidge_A.glb", "ENV-009_FarRidge_B.glb", "ENV-009_FarRidge_C.glb"],
}
PENDING = [
    "负责人美术复核与首次试玩的前方开口辨识",
    "USDZ 导出、RealityKit / App 合成与透明排序",
    "运行时地形、碰撞、起飞事件、滑翔 / 盘旋控制、雾退场和全队通过判定",
    "iPhone / iPad 真机显示、触控、相机和性能",
]


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, detail):
    if not condition:
        raise RuntimeError(detail)


def libroot():
    for path in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        for parent in (path, *path.parents):
            if (parent / "AGENTS.md").is_file() and (parent / "Assets").is_dir():
                return parent / "Assets/Watercolor/Goose/Blender"
    raise FileNotFoundError("Run from the project or its S0 candidate directory")


LIB = libroot()


def source_files():
    result = {}
    for id_, names in SOURCES.items():
        folder = LIB / id_ / "v001"
        manifest = read(folder / "asset_manifest.json")
        require(manifest["status"] in ("done", "needs_review"), id_)
        files = {}
        for name in [*names, "README.md", "qa.json", "asset_manifest.json"]:
            path = folder / name
            actual = sha(path)
            entry = manifest["files"].get(name)
            expected = entry.get("sha256") if isinstance(entry, dict) else entry
            require(not expected or actual == expected, f"Dependency hash mismatch: {path}")
            files[name] = actual
        result[id_] = {"version": "v001", "status": manifest["status"], "files": files}
    return result


def group(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def item(col, name, data=None, parent=None, pos=(0., 0., 0.)):
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    obj.parent = parent
    obj.location = pos
    return obj


def import_glb(path, col=None):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    objects = sorted(set(bpy.context.scene.objects) - before, key=lambda obj: obj.name)
    if col:
        for obj in objects:
            for old in list(obj.users_collection):
                old.objects.unlink(obj)
            col.objects.link(obj)
    return objects


def load_geo(id_, name, col, parent, pos=(0.,0.,0.), scale=(1.,1.,1.), label=None, role=None):
    objects = import_glb(LIB / id_ / "v001" / name, col)
    root, = [obj for obj in objects if not obj.parent]
    if label:
        root.name = label
    if role:
        root["s0_role"] = role
    root.parent = parent
    root.location += Vector(pos)
    root.scale = scale
    root["source_asset"] = id_ + "/v001/" + name
    return root, objects


def mesh(col, name, verts, faces, parent=None, materials=(), uv=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    for material in materials:
        data.materials.append(material)
    if uv:
        layer = data.uv_layers.new(name="UVMap")
        for loop in data.loops:
            layer.data[loop.index].uv = uv[loop.vertex_index]
    return item(col, name, data, parent)


def color(hex_value):
    def channel(value):
        s = int(value, 16) / 255
        return s / 12.92 if s < .04045 else ((s+.055) / 1.055)**2.4
    return (*[channel(hex_value[i:i+2]) for i in (0,2,4)], 1.)


def matte(name, tone, roughness=1.):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = color(tone)
    shader = material.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = material.diffuse_color
    shader.inputs["Roughness"].default_value = roughness
    return material


def smooth(x):
    t = min(1., max(0., x))
    return t*t*(3-2*t)


def bank_width(y, side):
    if y <= .15:
        delta = 1.2 * smooth((-y-.15)/4)
        return 12.85 - delta
    if y <= 7.5:
        return 12.85 - 8.25 * smooth((y-.15)/7.35)
    if y < 27.:
        return 4.6 + .65 * math.sin(.48*(y-7.5)+(.15 if side==1 else .95)) * smooth((y-7.5)/2.)
    return 4.6 + 8.25 * smooth((y-27.)/7.)


def bank_uv(x,y):
    return x/10+.5, y/10+.4*smooth((y-22.)/12.)


def terrain_wash(tile, verts):
    material = matte("S0 Bank | grass texture with painted wash", "BFBB97", .94)
    material.use_backface_culling=True
    nodes,links=material.node_tree.nodes,material.node_tree.links
    tex=nodes.new("ShaderNodeTexImage")
    tex.image=next(n.image for n in tile.data.materials[0].node_tree.nodes if n.type=="TEX_IMAGE")
    vertex=nodes.new("ShaderNodeVertexColor")
    vertex.layer_name="BankWash"
    mixed=nodes.new("ShaderNodeMix")
    mixed.data_type="RGBA"
    mixed.blend_type="MULTIPLY"
    mixed.inputs[0].default_value=1.
    links.new(tex.outputs["Color"],mixed.inputs[6])
    links.new(vertex.outputs["Color"],mixed.inputs[7])
    links.new(mixed.outputs[2],nodes["Principled BSDF"].inputs["Base Color"])
    gold=np.array((1.,.94,.79))
    sage=np.array((.63,.73,.73))
    wet=np.array((.75,.62,.53))
    washes=[]
    for x,y,_ in verts:
        width=bank_width(y,1 if x>=0 else -1)
        inner_band=math.exp(-(x/3.15)**2)*smooth((y-3.5)/9.)
        coast=math.exp(-((abs(x)-width)/1.65)**2) * smooth((y-2.)/4.)
        tint=sage+(gold-sage)*inner_band
        pigment=tint+(wet-tint)*.67*coast
        transition=max(1.-smooth(abs(y)/2.),smooth((y-30.)/6.))
        washes.append((*(pigment+(1.-pigment)*transition),1.))
    return material,washes


def make_surround(col, land_root, water_root, tile):
    # The 17-point join at each imported tile edge uses its original 0.625 BU lattice.
    xs = sorted({-26., -23., -20., -18., -16., -14., -13., -12., -10., -9., -8., -7., -6.,
                 6., 7., 8., 9., 10., 12., 13., 14., 16., 18., 20., 23., 26.,
                 *[col_*.625 for col_ in range(-8, 9)]})
    ys = [-13., -12., -11., *[row*.625 for row in range(-16, 1)], *range(1, 37)]
    verts = []
    for y in ys:
        for x in xs:
            if abs(x) <= 5. and -10. <= y <= 0.:
                z = 0.
            else:
                d = abs(x) - bank_width(y, 1 if x >= 0 else -1)
                outer_land = smooth((abs(x)-13.)/3.6)
                z = -.52 * smooth(d/1.7) + .60 * outer_land
                if abs(x) <= 5. and y < 0:
                    z = 0.
            verts.append((x,y,z))
    land_faces = []
    for j,(lo,hi) in enumerate(zip(ys, ys[1:])):
        for i,(left,right) in enumerate(zip(xs, xs[1:])):
            if lo >= -10. and hi <= 0. and left >= -5. and right <= 5.:
                continue
            a = j*len(xs)+i
            land_faces.append((a,a+1,a+1+len(xs),a+len(xs)))
    wash,shades=terrain_wash(tile,verts)
    continuation = mesh(col, "S0_Contact_Continued", verts, land_faces, land_root,
                        [wash], [bank_uv(x,y) for x,y,_ in verts])
    continuation["s0_role"] = "contact"
    attr=continuation.data.color_attributes.new(name="BankWash",type="FLOAT_COLOR",domain="POINT")
    for index, shade in enumerate(shades):
        attr.data[index].color = shade
    water = matte("S0 Water | cool reflection", "B3C2BC", .70)
    shader = water.node_tree.nodes["Principled BSDF"]
    shade = water.node_tree.nodes.new("ShaderNodeVertexColor")
    shade.layer_name = "WaterWash"
    water.node_tree.links.new(shade.outputs["Color"], shader.inputs["Base Color"])
    dark, warm, light = [np.asarray(color(tone))[:3] for tone in ("536F79", "9CB1A7", "C6B997")]
    result = []
    for side, name in [(-1, "West"), (1,"East")]:
        water_verts, washes = [], []
        for y in np.arange(3.7, 34.301, .25):
            inner = min(15.0, bank_width(y,side)+.62)
            outer_max = 15.2+.4*math.sin(y*.37+side*.24)+.18*math.sin(y*.91)
            channel = smooth((y-3.7)/4.5)*smooth((34.3-y)/5.)
            outer = inner+(max(inner+.12,outer_max)-inner)*channel+.025
            for i in range(9):
                frac = i/8
                x = side*(inner+(outer-inner)*frac)
                water_verts.append((x,y,WATER))
                ripple = .09*math.sin(x*.8+y*6.2) + .05*math.sin(y*15.2+x*.24)
                gleam = .28 * math.exp(-((abs(x)-6.)/3.3)**2) * math.exp(-((y-11.)/11.)**2)
                tint = np.clip(.43+.21*math.cos(frac*math.tau)+ripple,0,1)
                washes.append((*((1-gleam)*((1-tint)*dark+tint*warm)+gleam*light),1.))
        faces = [(a,a+1,a+10,a+9) for a in range(len(water_verts)-9) if a%9 != 8]
        if side < 0:
            faces = [face[::-1] for face in faces]
        surface = mesh(col,"S0_Wash_"+name,water_verts,faces,water_root,[water])
        surface["s0_role"] = "water"
        attr = surface.data.color_attributes.new(name="WaterWash", type="FLOAT_COLOR", domain="POINT")
        surface.data.color_attributes.active_color_index = 0
        for index, value in enumerate(washes):
            attr.data[index].color = value
        result.append(surface)
    return [tile,continuation], result


def setup_rigs(col):
    source = LIB / "CHR-001/v001/CHR-001_goose_rig.blend"
    with bpy.data.libraries.load(str(source)) as (files, loaded):
        loaded.objects = ["GooseRig", "Goose_LOD0"]
    rig, bird = loaded.objects
    require(rig and bird and bird.parent == rig, "CHR-001 rig/mesh")
    for obj in (rig,bird):
        col.objects.link(obj)
    rig.animation_data_clear()
    bird.animation_data_clear()
    rig.data.pose_position = "POSE"
    rigs = [rig]
    birds = [bird]
    for i in range(1,12):
        follow = rig.copy()
        col.objects.link(follow)
        other = bird.copy()
        col.objects.link(other)
        other.parent = follow
        for mod in other.modifiers:
            if mod.type == "ARMATURE":
                mod.object = follow
        rigs.append(follow)
        birds.append(other)
    for i, (armature,body) in enumerate(zip(rigs,birds),1):
        armature.name = f"S0_Goose_{i:02d}_Rig"
        body.name = f"S0_Goose_{i:02d}_Mesh"
        armature["s0_role"] = "review_flock"
        armature["goose_slot"] = i
        body["goose_slot"] = i
    return rigs,birds


def source_actions():
    choices = (
        ("ANM-002", "ANM-002_takeoff_climb.blend", ["Takeoff_Climb","Cruise_Flap_Loop"]),
        ("ANM-003", "ANM-003_glide_circle.blend", ["Glide_Loop","Circle_Loop"]),
    )
    clips = {}
    for id_,name,actions in choices:
        with bpy.data.libraries.load(str(LIB/id_/"v001"/name)) as (files,loaded):
            loaded.actions = list(actions)
        for name_, clip in zip(actions,loaded.actions):
            require(clip is not None, name_)
            clip.use_fake_user = True
            curves = clip.layers[0].strips[0].channelbag(clip.slots[0]).fcurves
            clips[name_] = {(curve.data_path,curve.array_index):curve for curve in curves}
    return clips


def point(t):
    # A northward straight, one smooth near-full left turn, then a northward exit.
    if t < 1.66:
        return 0.,0.,0.
    if t < 4.6:
        u = (t-1.66)/(4.6-1.66)
        return 0.,10.1*u*u*(2.-u),0.
    if t < 9.8:
        u = (t-4.6)/5.2
        angle = math.tau*u
        return -3.05+3.05*math.cos(angle),10.1+3.05*math.sin(angle),angle
    u = (t-9.8)/(14.-9.8)
    return 0.,10.1+(37.4-10.1)*u*u*(3.-2.*u),math.tau


def timelines(age):
    if age < 1.667:
        return [("Takeoff_Climb",1+48*max(0.,age),1.)]
    flap = 1+(48*(age-1.667))%52
    glide = 1+(48*max(0.,age-2.85))%72
    turn = 1+(48*max(0.,age-4.6))%96
    if age < 3.183:
        weight = smooth((age-2.85)/.333)
        return [("Cruise_Flap_Loop",flap,1.-weight),("Glide_Loop",glide,weight)]
    if age < 4.6:
        return [("Glide_Loop",glide,1.)]
    if age < 5.1:
        weight = smooth((age-4.6)/.5)
        return [("Glide_Loop",glide,1.-weight),("Circle_Loop",turn,weight)]
    if age < 9.35:
        return [("Circle_Loop",turn,1.)]
    if age < 9.85:
        weight = smooth((age-9.35)/.5)
        return [("Circle_Loop",turn,1.-weight),("Glide_Loop",glide,weight)]
    return [("Glide_Loop",glide,1.)]


def carrier(manifest, age):
    if age >= 1.667:
        return .5720001631 * (1.-smooth((age-1.667)/.9)), .29+.79*smooth((age-1.667)/1.3)
    s = min(81.,1.+max(0.,age)*48)
    lo,hi = math.floor(s*2)/2,math.ceil(s*2)/2
    a,b = (manifest[str(i)] for i in (lo,hi))
    return tuple(x+(y-x)*(s-lo)*2 for x,y in zip(a,b))


def make_choreo(scene, rigs, cam):
    table = read(LIB/"ANM-002/v001/asset_manifest.json")["preview_carrier"]["positions_forward_height_BU"]
    clips = source_actions()
    keys = set().union(*(curves.keys() for curves in clips.values()))
    for frame in range(1,LAST+1):
        t = (frame-1)/FPS
        x,y,yaw = point(t)
        for index,rig in enumerate(rigs):
            age = t-DELAYS[index]
            offset_x,offset_y = START_SLOTS[index]
            push,lift = carrier(table,age)
            rig.location = (x+offset_x*math.cos(yaw)-offset_y*math.sin(yaw),
                            y+offset_x*math.sin(yaw)+offset_y*math.cos(yaw)+push,lift+.003)
            rig.rotation_euler = (0,0,yaw)
            for prop in ("location","rotation_euler"):
                rig.keyframe_insert(prop,frame=frame)
            samplers = [(clips[clip],source_time,weight) for clip,source_time,weight in timelines(age)]
            for path, axis in keys:
                bone_name, prop = path.split('"].')
                pose = rig.pose.bones[bone_name.split('["')[1]]
                val = sum(weight*(curves[path,axis].evaluate(source_time) if (path,axis) in curves else 0.)
                          for curves,source_time,weight in samplers)
                getattr(pose,prop)[axis] = val
                pose.keyframe_insert(prop,index=axis,frame=frame,group=pose.name)
        leader = rigs[0].location - Vector((0,0,8*BU))
        forward = Vector((-math.sin(yaw), math.cos(yaw),0))
        offset = 180.*BU
        cam.location = leader - offset*math.cos(.48)*forward + Vector((0,0,offset*math.sin(.48)))
        aimed = leader+Vector((0,0,6.*BU))
        cam.rotation_euler = (aimed-cam.location).to_track_quat("-Z","Y").to_euler("XYZ",cam.rotation_euler)
        for prop in ("location","rotation_euler"):
            cam.keyframe_insert(prop,frame=frame)
    for idx, obj in enumerate([*rigs,cam]):
        anim = obj.animation_data
        anim.action.name = "S0_Review_FixedRearCamera" if obj is cam else f"S0_Review_Goose_{idx+1:02d}"
        for curve in anim.action.layers[0].strips[0].channelbag(anim.action_slot).fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"
    for name,frame in (("Start on mudflat",1),("Synchronized lift with short staggering",13),
                       ("Glide",82),("Left circle",112),("Northward final glide",239),
                       ("All twelve beyond fog",LAST)):
        scene.timeline_markers.new(name,frame=frame)


def camera(col,name,ortho=None):
    data = bpy.data.cameras.new(name)
    cam = item(col,name,data)
    data.sensor_fit = "VERTICAL"
    data.sensor_height = 24
    data.lens = 12/math.tan(math.radians(25))
    data.clip_start,data.clip_end=.02,250.
    if ortho:
        data.type = "ORTHO"
        data.sensor_fit = "HORIZONTAL"
        data.ortho_scale = ortho
    return cam


def studio(scene,col):
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 6
    scene.eevee.use_shadows = True
    scene.render.fps = FPS
    scene.render.resolution_x,scene.render.resolution_y=SIZE
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.image_settings.color_mode="RGB"
    scene.render.film_transparent=False
    scene.view_settings.view_transform="AgX"
    scene.view_settings.look="AgX - Medium High Contrast"
    scene.frame_start,scene.frame_end=1,LAST
    scene.world = bpy.data.worlds.new("Pale wetland morning")
    scene.world.use_nodes=True
    world = scene.world.node_tree.nodes["Background"]
    world.inputs["Color"].default_value=(.73,.79,.81,1)
    world.inputs["Strength"].default_value=.8
    dawn = bpy.data.lights.new("Low dawn fill","SUN")
    dawn.energy,dawn.angle,dawn.color=1.75,.24,(1.,.83,.62)
    sun = item(col,dawn.name,dawn)
    sun.rotation_euler = Vector((-.37,-.86,-.55)).to_track_quat("-Z","Y").to_euler()
    soft = bpy.data.lights.new("Soft blue sky fill","SUN")
    soft.energy,soft.angle,soft.color=.69,.5,(.72,.86,1.)
    fill = item(col,soft.name,soft)
    fill.rotation_euler = Vector((.45,.1,-1.)).to_track_quat("-Z","Y").to_euler()


def fog_controls(items):
    # Keep the source FX-004 inputs and unlit images, even though the master plays a 24 fps timeline.
    root = bpy.data.objects["Fog_Start"]
    root["s0_role"]="fog"
    defaults={"opacity_strength":1.,"motion_strength":1.,"period_seconds":12.,"phase_turns":0.}
    for k,v in defaults.items():
        root[k]=v
        root.id_properties_ui(k).update(min=1. if k=="period_seconds" else 0.,
                                        max=60. if k=="period_seconds" else 1.)
    materials=set()
    for card in items:
        if card.type!="MESH":
            continue
        card["s0_role"]="fog"
        card["base_x_BU"]=card.location.x
        require("amplitude_BU" in card and "phase_turns" in card, card.name)
        drv=card.driver_add("location",0).driver
        drv.expression=f"base + amp*motion*sin(6.283185307179586*(phase+global_phase+(frame-1)/({FPS}*max(1,period))))"
        for name,target,key in (
            ("base",card,"base_x_BU"),("amp",card,"amplitude_BU"),("phase",card,"phase_turns"),
            ("motion",root,"motion_strength"),("global_phase",root,"phase_turns"),("period",root,"period_seconds")):
            variable=drv.variables.new()
            variable.name=name
            variable.type="SINGLE_PROP"
            variable.targets[0].id=target
            variable.targets[0].data_path=f'["{key}"]'
        materials.add(card.data.materials[0])
    for mat in materials:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        out = next(n for n in nodes if n.type == "OUTPUT_MATERIAL")
        texture = next(n for n in nodes if n.type == "TEX_IMAGE")
        tex_image = texture.image
        nodes.clear()
        out = nodes.new("ShaderNodeOutputMaterial")
        out.location=(400,0)
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = tex_image
        tex.extension = "EXTEND"
        tex.location=(-500,0)
        mix = nodes.new("ShaderNodeMixShader")
        mix.location=(190,0)
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        transparent.location=(-40,-120)
        gain = nodes.new("ShaderNodeMath")
        gain.name="Fog opacity control"
        gain.operation="MULTIPLY"
        gain.location=(-40,170)
        gain.inputs[1].default_value=1.
        links.new(tex.outputs["Alpha"], gain.inputs[0])
        links.new(gain.outputs[0], mix.inputs[0])
        links.new(transparent.outputs[0], mix.inputs[1])
        links.new(tex.outputs["Color"], mix.inputs[2])
        links.new(mix.outputs[0], out.inputs[0])
        drv=gain.inputs[1].driver_add("default_value").driver
        variable=drv.variables.new()
        variable.name="opacity"
        variable.type="SINGLE_PROP"
        variable.targets[0].id=root
        variable.targets[0].data_path='["opacity_strength"]'
        drv.expression="opacity"
    return root


def assemble():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "S0 | Morning wetland fixed third person"
    runtime = group("01 | Exported wetland and anchors")
    bird_col = group("02 | Review choreography • 12 CHR-001 rigs")
    rig_col = group("03 | Review lighting and cameras")
    backdrop_col = group("04 | Optional distant terrain backdrop GLB")
    far_root = item(backdrop_col,"S0_DistantRidgeView")
    far_root["collision_enabled"]=False
    far_root["runtime_scope"]="standalone view backdrop; keep out of concatenated tile collision and geometry"
    root = item(runtime,"S0_StartWetland")
    root["variant"]="S0_StartWetland"
    for name,p in ((ENTRY_NAME,(0.,0.,0.)),(EXIT_NAME,(0.,EXIT,0.))):
        marker = item(runtime,name,parent=root,pos=p)
        marker.empty_display_size=.85
        marker["heading_blender"]=(0.,1.,0.)
        marker["heading_glTF"]=(0.,0.,-1.)
        marker["ground_z_BU"]=0.
        marker["reference_water_z_BU"]=WATER
    land,water,reed,ridge = [item(runtime,name,parent=root) for name in (
        "S0_ContactGround","S0_ShallowWater","S0_DecorativeReeds","S0_FarRidges")]
    tile,_=load_geo("ENV-002","ENV-002_StartMudflat.glb",runtime,land,pos=(0,-5,0),role="contact")
    pool,_=load_geo("ENV-003","ENV-003_ShallowPool_StartMudflat.glb",runtime,water,pos=(0,-5,0),role="water")
    contact_surfaces,_ = make_surround(runtime,land,water,tile)
    _,fog_items=load_geo("FX-004","FX-004_Fog_Start.glb",runtime,root)
    for obj in fog_items:
        obj["s0_role"]="fog"
    for j,(x,y,side,preset) in enumerate((
        (-7.45,3.9,-1,"Sparse"),(7.35,5.1,1,"Sparse"),(-7.45,10.5,-1,"ShoreEdge"),
        (7.4,13.3,1,"ShoreEdge"),(-7.4,21.,-1,"ShoreEdge"),
        (8.25,22.7,1,"Sparse"),(-8.6,26.2,-1,"Sparse"),(8.3,28.,1,"ShoreEdge"))):
        # Keep the assembled contact shelf separate from lateral prop groups.
        ob,_=load_geo("ENV-005",f"ENV-005_{preset}.glb",runtime,reed,(x,y,-.08),(.31,.28,.67),
                       f"S0_Reeds_{j+1:02d}_{preset}", "reed")
        ob.rotation_euler.z = .08 if side>0 else math.pi+.08
    for i,(variant,x,y,sc,sz) in enumerate((
        ("A",-28.,31.5,.82,.86),("A",28.,32.7,.82,.98),("B",-15.,54.,1.10,1.03),
        ("B",21.,57.,1.02,1.15),("C",0.,73.,1.23,1.31))):
        far = variant in {"B","C"}
        load_geo("ENV-009",f"ENV-009_FarRidge_{variant}.glb",backdrop_col if far else runtime,
                 far_root if far else ridge,(x,y,-.24),(sc,.94,sz),
                 f"S0_Ridge_{i+1:02d}_{variant}","backdrop")
    for obj in [*runtime.objects,*backdrop_col.objects]:
        if obj.get("s0_role") in {"water","reed","backdrop"}:
            obj["collision_enabled"]=False
    bpy.context.view_layer.update()
    rigs,birds=setup_rigs(bird_col)
    studio(scene,rig_col)
    cam=camera(rig_col,"S0_ThirdPersonRig_FixedRear")
    top=camera(rig_col,"S0_Technical_Overhead",39.)
    top.location=(0.,13.,53.)
    top.rotation_euler=(0.,0.,0.)
    scene.camera=cam
    review_context(rig_col,contact_surfaces[1])
    make_choreo(scene,rigs,cam)
    scene.frame_set(1)
    return scene,runtime,backdrop_col,bird_col,fog_items,cam,top


def review_context(col, continuation):
    # Stretch the distant bed behind the exported strip; its near edge matches Y=36 exactly.
    skirt=matte("Distant air wash","A7B0B2")
    mesh(col,"Review_AtmosphericDistance",[(-180,-180,-.61),(180,-180,-.61),
         (180,180,-.61),(-180,180,-.61)],[(0,1,2,3)],materials=[skirt])
    for name,verts in (
        ("North",[(-26,36,0.),(26,36,0.),(43,49,-.10),(55,73,-.38),
                  (-55,73,-.38),(-43,49,-.10)]),
        ("South",[(-26,-13,0.),(-43,-26,-.10),(-52,-49,-.38),
                  (52,-49,-.38),(43,-26,-.10),(26,-13,0.)]),
    ):
        field=mesh(col,"Review_GrassBeyond_"+name,verts,[tuple(range(len(verts)))],
                   materials=[continuation.data.materials[0]],uv=[bank_uv(x,y) for x,y,_ in verts])
        color_attr=field.data.color_attributes.new(name="BankWash",type="FLOAT_COLOR",domain="POINT")
        for idx,(_,y,_) in enumerate(verts):
            color_attr.data[idx].color=(1.,1.,1.,1.) if y==36. else (.79,.83,.81,1.)

def export_selection(scene,objects,path,animate=False):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    scene.frame_set(1)
    options={"filepath":str(path),"export_format":"GLB","use_selection":True,"export_extras":True,
             "export_yup":True,"export_animations":animate,"export_image_format":"AUTO"}
    if animate:
        options.update(export_animation_mode="SCENE", export_frame_range=True,
                       export_anim_slide_to_zero=True)
    bpy.ops.export_scene.gltf(**options)
    if animate:
        combine_review_tracks(path)
    bpy.ops.object.select_all(action="DESELECT")


def combine_review_tracks(path):
    # The exporter emits a scene track per armature, all synchronized to zero.
    # One glTF animation allows a reviewer to play every bird on the same clock.
    raw=path.read_bytes()
    json_length=struct.unpack_from("<I",raw,12)[0]
    doc=json.loads(raw[20:20+json_length])
    tracks=doc["animations"]
    require(len(tracks)==12, f"Expected twelve staging tracks, got {len(tracks)}")
    clip={"name":"S0_Review_Takeoff_Glide_Circle","samplers":[],"channels":[]}
    for track in tracks:
        offset=len(clip["samplers"])
        clip["samplers"].extend(track["samplers"])
        for channel in track["channels"]:
            clip["channels"].append({**channel,"sampler":channel["sampler"]+offset})
    doc["animations"]=[clip]
    part=json.dumps(doc,separators=(",",":")).encode()
    part+=b" "*(-len(part)%4)
    tail=raw[20+json_length:]
    path.write_bytes(struct.pack("<4sII",b"glTF",2,20+len(part)+len(tail))+
                     struct.pack("<I4s",len(part),b"JSON")+part+tail)


def render(scene,cam,path,size=SIZE,samples=6):
    scene.camera=cam
    scene.render.resolution_x,scene.render.resolution_y=size
    scene.eevee.taa_render_samples=samples
    scene.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)


def graybox(scene,cam,top,out):
    roles={"contact":"949282","water":"60747F","reed":"526357","backdrop":"708295"}
    grays={role:matte("Graybox | "+role,tone) for role,tone in roles.items()}
    grays["bird"]=matte("Graybox | flock","DAD5C9")
    swaps=[]
    hidden=[]
    for obj in scene.objects:
        if obj.type!="MESH":
            continue
        if obj.get("s0_role")=="fog":
            obj.hide_render=True
            hidden.append(obj)
            continue
        gray=grays["bird"] if obj.get("goose_slot") else grays.get(obj.get("s0_role"))
        if gray:
            for slot in obj.material_slots:
                swaps.append((slot,slot.link,slot.material))
                slot.link="OBJECT"
                slot.material=gray
    scene.frame_set(1)
    render(scene,cam,out/"graybox_fixed_rear.png")
    render(scene,top,out/"graybox_top.png",(876,1024))
    for slot,link,material in swaps:
        slot.material=material
        slot.link=link
    for obj in hidden:
        obj.hide_render=False


def video(scene,cam,out):
    frames=out/"frames"
    frames.mkdir(exist_ok=True)
    for index,frame in enumerate(range(1,LAST,2)):
        scene.frame_set(frame)
        render(scene,cam,frames/f"{index:04d}.png",samples=3)
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-framerate",str(VIDEO_FPS),
                    "-i",str(frames/"%04d.png"),"-vf","pad=iw:ih+1:0:0:color=black",
                    "-c:v","libx264","-preset","fast","-crf","18","-pix_fmt","yuv420p",
                    "-movflags","+faststart","-an",str(out/VIDEO)],check=True)
    shutil.rmtree(frames)


def ffverify(path):
    subprocess.run(["ffmpeg","-v","error","-xerror","-threads","1","-i",str(path),"-f","null","-"],
                   check=True)
    data=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_streams","-count_frames",
                                            "-of","json",str(path)]))["streams"]
    clip,=data
    require((clip["codec_type"],clip["width"],clip["height"],int(clip["nb_read_frames"]))==
            ("video",852,394,(LAST-1)//2), clip)
    return {"frames_decoded":int(clip["nb_read_frames"]),"sources_pixels":SIZE,"encoded_pixels":[852,394],
            "fps":clip["avg_frame_rate"],"duration_seconds":float(clip["duration"]),"audio_tracks":0}


def layout():
    return {"id":ID,"version":"v001","status":"needs_review","variant":"S0_StartWetland",
            "units":{"BU_per_game_unit":BU,"blender_forward":"+Y","blender_up":"+Z","glTF":"(x,z,-y)"},
            "local_origin_BU":[0.,0.,0.],"entry":{"node":ENTRY_NAME,"position_BU":[0.,0.,0.],
            "position_glTF":[0.,0.,0.],"heading_BU":[0.,1.,0.],"ground_z_BU":0.,"water_z_BU":WATER},
            "exit":{"node":EXIT_NAME,"position_BU":[0.,EXIT,0.],"position_glTF":[0.,0.,-EXIT],
                    "heading_BU":[0.,1.,0.],"ground_z_BU":0.,"water_z_BU":WATER,
                    "cross_section_x_BU":[-12.,12.],"dry_flat_approach_y_BU":[34.,36.],
                    "material":{"GrassFlat_shared_tile":True,"seam_V_wrap":0.0,
                                "wash_feathers_to_neutral_y_BU":[30.,36.]}},
            "anchor_notes":{"spawn_slots_xy_BU_at_frame_1":START_SLOTS,"launch_delays_seconds":DELAYS,
                            "fog_line_y_BU":FOG_LINE,"shallow_pool_origin_BU":[0.,-5.,0.],
                            "ridge_and_reed_transforms":"Editable object transforms and GLB nodes"},
            "fixed_camera":{"distance_game_units":180,"pitch_parameter_rad":.48,
                            "vertical_fov_degrees":50,"target_base_above_ground_game_units":6,
                            "depth_lift_from_animated_leader_Z_minus_8_game_units":True,
                            "source_pixels":SIZE,"follow_heading_and_lift":True},
            "runtime":{"Fog_Start":{"placement_BLENDER":[0.,0.,0.],"opacityStrength":1.,"motionStrength":1.,
                       "periodSeconds":12.,"phaseTurns":0.,"elapsedSeconds":"scene monotonic clock"},
                       "contact_surfaces":["StartMudflat","S0_Contact_Continued"],
                       "decorative_only":["S0_ShallowWater","S0_DecorativeReeds","S0_FarRidges","Fog_Start"],
                       "engine_owned":["takeoff/glide/circle states","collision","all-flock passage"],
                       "optional_far_backdrop_glb":BACKDROP,
                       "optional_far_backdrop_use":"Visual backdrop for standalone S0. Keep outside paired S0-S1 world geometry.",
                       "review_flock":FLOCK,"target_gameplay_seconds":30},
            "review":{"timeline_sample_rate":FPS,"length_seconds":(LAST-1)/FPS,
                      "last_frame":LAST,"material_keyframes":KEY_FRAMES}}


def build(out,quick=False):
    dependencies=source_files()
    scene,runtime,backdrop_col,bird_col,fog_items,cam,top=assemble()
    graybox(scene,cam,top,out)
    export_selection(scene,runtime.objects,out/SCENE)
    export_selection(scene,backdrop_col.objects,out/BACKDROP)
    export_selection(scene,bird_col.objects,out/FLOCK,True)
    fog_controls(fog_items)
    for name,frame in KEY_FRAMES.items():
        scene.frame_set(frame)
        render(scene,cam,out/f"preview_fixed_rear_{name}.png")
    scene.frame_set(313)
    render(scene,top,out/"preview_top_flock.png",(876,1024))
    scene.frame_set(1)
    scene.camera=cam
    scene.render.resolution_x,scene.render.resolution_y=SIZE
    scene.render.filepath="//preview_fixed_rear_takeoff.png"
    scene["runtime_inputs"]="See s0_layout.json; flock and cameras are editable review evidence."
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=="VIEW_3D":
                area.spaces.active.region_3d.view_perspective="CAMERA"
                area.spaces.active.clip_end=250.
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(out/(STEM+".blend")))
    write(out/"s0_layout.json",layout())
    write(out/"dependencies.json",dependencies)
    if not quick:
        video(scene,cam,out)


def tree(objects):
    vertices = []
    triangles = []
    for obj in objects:
        require(obj.type=="MESH",obj.name)
        offset=len(vertices)
        vertices.extend(obj.matrix_world@v.co for v in obj.data.vertices)
        obj.data.calc_loop_triangles()
        triangles.extend(tuple(offset+i for i in tri.vertices) for tri in obj.data.loop_triangles)
    return BVHTree.FromPolygons(vertices,triangles,all_triangles=True)


def ground_contact(terrain,x,y):
    point,*_=terrain.ray_cast(Vector((x,y,4.)),Vector((0,0,-1)),8.)
    return None if point is None else point.z


def bxs(objects):
    return ([min(co[i] for obj in objects for co in (obj.matrix_world@Vector(p) for p in obj.bound_box))
             for i in range(3)],
            [max(co[i] for obj in objects for co in (obj.matrix_world@Vector(p) for p in obj.bound_box))
             for i in range(3)])


def fog_card_images(objects):
    data={}
    for card in objects:
        if card.type=="MESH" and card.get("s0_role")=="fog":
            img=next(n.image for n in card.data.materials[0].node_tree.nodes if n.type=="TEX_IMAGE")
            w,h=img.size
            rgba=np.empty(w*h*4,dtype=np.float32)
            img.pixels.foreach_get(rgba)
            low,high=bxs([card])
            data[card.name]={"image":img.name,"alpha":rgba.reshape(h,w,4)[:,:,3],"dims":(high[0]-low[0],high[2]-low[2])}
    require(len(data)==6,"expected six Fog_Start cards")
    return data


def trace_fog(scene,eye,target,image_data):
    ray=target-eye
    value=1.
    if abs(ray.y)<1e-8:
        return 0.
    for name,data in image_data.items():
        center=scene.objects[name].matrix_world.translation
        width,height=data["dims"]
        t=(center.y-eye.y)/ray.y
        if not 0.<t<1.:
            continue
        delta=eye+t*ray-center
        u,v=delta.x/width+.5,delta.z/height+.5
        if 0.<=u<1. and 0.<=v<1.:
            alpha=data["alpha"]
            h,w=alpha.shape
            value *= 1-float(alpha[int(v*h),int(u*w)])
    return 1.-value


def seam(scene,terrain):
    probes=0
    max_error=0.
    for label,y_values in [(ENTRY_NAME,(0.,)),(EXIT_NAME,(34.,34.5,35.5,35.9999))]:
        obj=scene.objects[label]
        require((obj.matrix_world.translation-Vector((0,0 if label==ENTRY_NAME else EXIT,0))).length<1e-5,label)
        require(list(obj["heading_blender"])==[0,1,0] and abs(obj["reference_water_z_BU"]-WATER)<1e-5,label)
        for y in y_values:
            for x in np.linspace(-12,12,49):
                z=ground_contact(terrain,float(x),y)
                require(z is not None,(x,y,label))
                max_error=max(max_error,abs(z))
                probes+=1
    require(max_error<2e-5,max_error)
    structures=[obj for obj in scene.objects if obj.get("s0_role") in {"reed","backdrop"}]
    blockers=tree(structures)
    blocker_probes=0
    for y in np.linspace(34.,36.,21):
        for x in np.linspace(-12.,12.,49):
            hit,*_=blockers.ray_cast(Vector((x,y,3.)),Vector((0,0,-1)),3.)
            require(hit is None,("Gate blocked by decorative geometry",float(x),float(y),hit))
            blocker_probes+=1
    require(ground_contact(terrain,0.,36.002) is None,"terrain overlaps neighbor")
    submerged=[obj for obj in scene.objects if obj.get("s0_role")=="water"]
    result={}
    for obj in submerged:
        low,high=bxs([obj])
        require(abs(low[2]-WATER)<1e-5 and abs(high[2]-WATER)<1e-5 and (low[1]>0 or high[1]<0) and high[1]<35.,obj.name)
        result[obj.name]={"y_extent_BU":[low[1],high[1]],"z_BU":low[2]}
    require(len(result)==3,"ENV-003 isolated pool and two lateral branch washes expected")
    terminal=scene.objects["S0_Contact_Continued"].data
    uv_layer=terminal.uv_layers.active.data
    wash=terminal.color_attributes[0]
    end_samples=0
    for loop in terminal.loops:
        co=terminal.vertices[loop.vertex_index].co
        if abs(co.y-EXIT)<2e-5 and abs(co.x)<=12.00001:
            _,phase=uv_layer[loop.index].uv
            shade=wash.data[loop.vertex_index if wash.domain=="POINT" else loop.index].color
            require(abs(phase-round(phase))<2e-5 and all(abs(channel-1.)<2e-5 for channel in shade),
                    ("Terminal GrassFlat wrap and neutral wash",co,phase,tuple(shade)))
            end_samples+=1
    require(end_samples>=30,end_samples)
    return {"dry_flat_probes":probes,"maximum_plane_error_BU":max_error,"decorative_gate_ray_probes":blocker_probes,
            "terminal_GrassFlat_modulo_V0_and_white_wash_corner_samples":end_samples,
            "terrain_beyond_Y36_at_X0":False,"water_surfaces":result}


def pack_world(obj,deps):
    evaluated=obj.evaluated_get(deps)
    coords=np.empty(len(evaluated.data.vertices)*3,dtype=np.float32)
    evaluated.data.vertices.foreach_get("co",coords)
    matrix=np.array(evaluated.matrix_world)
    return coords.reshape(-1,3)@matrix[:3,:3].T+matrix[:3,3]


def target_pixel(scene,cam,vec):
    uv=world_to_camera_view(scene,cam,Vector(vec))
    return (uv.x*SIZE[0],(1-uv.y)*SIZE[1],uv.z)


def sample(scene, roundtrip=False, baseline=None):
    scene.frame_set(1)
    bpy.context.view_layer.update()
    terrain=tree([ob for ob in scene.objects if ob.get("s0_role")=="contact"])
    reeds=[ob for ob in scene.objects if ob.get("s0_role")=="reed"]
    vegetation=tree(reeds)
    require(len(reeds)==8,"expected eight assembled reed groups")
    sea=seam(scene,terrain)
    cam=scene.objects["S0_ThirdPersonRig_FixedRear"]
    rigs=sorted((obj for obj in scene.objects if obj.type=="ARMATURE" and obj.get("goose_slot")),
                key=lambda o:o["goose_slot"])
    birds=sorted((obj for obj in scene.objects if obj.type=="MESH" and obj.get("goose_slot")),
                 key=lambda o:o["goose_slot"])
    require(len(birds)==len(rigs)==12,(len(birds),len(rigs)))
    alphas=fog_card_images(scene.objects)
    route_opening_opacity=0.
    clearance=math.inf
    min_post=math.inf
    spawn_margin=math.inf
    spawn_body_boxes=[]
    min_reed_gap_count=0
    tested_rays=0
    largest_pose_vertex_difference=0.
    greatest_camera_delta=0.
    camera_margins=math.inf
    flock_cloud={i:[] for i in range(1,13)}
    measured={}
    sample_frames=sorted(set(range(1,49)) | set(range(49,LAST,4)) | set(KEY_FRAMES.values()) | {LAST})
    pairs=0
    # Use per-bird evaluated skin vertices, preserving imported triangle topology.
    for bird in birds:
        bird.data.calc_loop_triangles()
    triangles=[[tuple(tri.vertices) for tri in bird.data.loop_triangles] for bird in birds]
    for frame in sample_frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        deps=bpy.context.evaluated_depsgraph_get()
        lead=rigs[0].matrix_world.translation
        direction=rigs[0].matrix_world.to_3x3()@Vector((0.,1.,0.))
        direction.z=0.
        direction.normalize()
        trajectory=lead-Vector((0,0,8*BU))
        expected=trajectory-180.*BU*math.cos(.48)*direction+Vector((0,0,180.*BU*math.sin(.48)))
        axis=cam.matrix_world.to_quaternion()@Vector((0,0,-1))
        aim=(trajectory+Vector((0,0,6*BU))-expected).normalized()
        greatest_camera_delta=max(greatest_camera_delta,(expected-cam.location).length, (aim-axis).length)
        eye=cam.matrix_world.translation
        body_vertices=[pack_world(bird,deps) for bird in birds]
        body_bounds=[(vs.min(axis=0),vs.max(axis=0)) for vs in body_vertices]
        for index,(vertices,(low,high),tris) in enumerate(zip(body_vertices,body_bounds,triangles),1):
            age=(frame-1)/FPS-DELAYS[index-1]
            flock_cloud[index].append((frame,float(low[1]),float(high[1]),float(low[2])))
            if age < .64 or low[2] < .02:
                gaps=[]
                for x,y,z in vertices[vertices[:,2]<.09]:
                    probe=ground_contact(terrain,float(x),float(y))
                    if probe is not None:
                        gaps.append(float(z)-probe)
                if gaps:
                    clearance=min(clearance,min(gaps))
            elif low[2]>=.02 and 0.<=high[1]<=36. and low[0]>=-12 and high[0]<=12:
                # The measured central terrain remains at or below the common datum.
                min_post=min(min_post,float(low[2]))
            bird_tree = BVHTree.FromPolygons(vertices.tolist(),tris,all_triangles=True)
            overlap=vegetation.overlap(bird_tree)
            require(not overlap,("Reed intersection",frame,index,len(overlap)))
            min_reed_gap_count+=1
            if frame in (1,5,9,13):
                center=(low+high)/2
                box_corners=[(x,y,z) for x in (low[0],high[0]) for y in (low[1],high[1])
                             for z in (low[2],high[2])]
                pixels=[target_pixel(scene,cam,co) for co in box_corners]
                camera_margins=min(camera_margins,*(min(x,SIZE[0]-x,y,SIZE[1]-y) for x,y,z in pixels))
                if frame==1:
                    spawn_body_boxes.append({"slot":index,
                                             "pixel_bounds":[min(p[0] for p in pixels),min(p[1] for p in pixels),
                                                             max(p[0] for p in pixels),max(p[1] for p in pixels)]})
                for aimpoint in (center,np.array((center[0],high[1]-.04,high[2]-.04)),*box_corners):
                    delta=Vector(aimpoint)-eye
                    hit,*_=vegetation.ray_cast(eye,delta.normalized(),delta.length)
                    require(hit is None,("Spawn sightline blocked",frame,index,aimpoint))
                    tested_rays+=1
                    opacity=trace_fog(scene,eye,Vector(aimpoint),alphas)
                    require(opacity<.075,("Fog masks launch goose",frame,index,opacity))
                spawn_margin=min(spawn_margin,float(low[0]+12),float(12-high[0]))
            if frame in (1,13,25,103,169,313,LAST):
                # Compare the whole realized world-space vertex cloud here without depending on GLB topology order.
                anchor=np.array((17.13,41.29,5.73))
                projection=np.sort(np.unique(np.round(np.linalg.norm(vertices-anchor,axis=1),5)))
                columns=np.concatenate((low,high,np.quantile(projection, np.linspace(0,1,101))))
                key=f"{frame}/{index}"
                if baseline:
                    largest_pose_vertex_difference=max(largest_pose_vertex_difference,
                                                        float(np.max(np.abs(columns-baseline[key]))))
                measured[key]=columns.tolist()
        # Inter-bird tests use disjoint AABBs as the strong fast path, then an actual mesh intersection test.
        for i,(low,high) in enumerate(body_bounds):
            for j in range(i+1,12):
                low_j,high_j=body_bounds[j]
                if not (np.any(high<low_j) or np.any(high_j<low)):
                    a=BVHTree.FromPolygons(body_vertices[i].tolist(),triangles[i],all_triangles=True)
                    b=BVHTree.FromPolygons(body_vertices[j].tolist(),triangles[j],all_triangles=True)
                    require(not a.overlap(b),("Bird intersection",frame,i+1,j+1))
                pairs+=1
        if frame in (1,5,9,13,25,35,49):
            for x in (-.85,0.,.85):
                for goal_y in (6.0,10.5,16.0,22.,31.,34.):
                    dst=Vector((x,goal_y,1.0))
                    delta=dst-eye
                    hit,*_=vegetation.ray_cast(eye,delta.normalized(),delta.length)
                    require(hit is None,("Opening covered by vegetation",frame,x,goal_y))
                    route_opening_opacity=max(route_opening_opacity,trace_fog(scene,eye,dst,alphas))
    last_all=min(path[-1][1] for path in flock_cloud.values())
    last_lower=min(path[-1][3] for path in flock_cloud.values())
    all_crossed={}
    for slot,records in flock_cloud.items():
        frame,lower_y,_,bottom=next(row for row in records if row[1]>FOG_LINE and row[3]>.32)
        all_crossed[str(slot)]={"first_sample_all_vertices_above_line_frame":frame,
                                "minimum_Y_BU":lower_y,"minimum_Z_BU":bottom}
    require(last_all>FOG_LINE and last_lower>.3,(last_all,last_lower))
    require(clearance>=-.009,("Sonde ground penetration",clearance))
    require(greatest_camera_delta<1.5e-4,greatest_camera_delta)
    require(camera_margins>0.,camera_margins)
    require(route_opening_opacity<.06,route_opening_opacity)
    if baseline:
        require(largest_pose_vertex_difference<.014,("Imported world pose mismatch",largest_pose_vertex_difference))
    return {"sample_frames":len(sample_frames),"bird_samples":len(sample_frames)*12,"count":12,
            "all_twelve_crossed_by_frame":max(v["first_sample_all_vertices_above_line_frame"] for v in all_crossed.values()),
            "fog_line_y_BU":FOG_LINE,"final_lowest_vertex_y_BU":last_all,"final_lowest_vertex_z_BU":last_lower,
            "launch_min_ground_clearance_BU":clearance,"central_airborne_min_vertex_above_datum_BU":min_post,
            "substrate_contract":sea,"max_camera_pose_error_BU_or_unit_vector":greatest_camera_delta,
            "spawn_sightline_rays":tested_rays,"spawn_worst_conservative_screen_margin_px":camera_margins,
            "spawn_projected_bird_boxes_px":spawn_body_boxes,"opening_peak_Fog_Start_alpha":route_opening_opacity,
            "bird_pair_terrain_independent_probes":pairs,"bird_reed_mesh_probes":min_reed_gap_count,
            "last_fog_line_pass_by_slot":all_crossed,"packed_world_pose_quantiles":measured,
            "GLB_pose_quantile_peak_error_BU":largest_pose_vertex_difference if roundtrip else None}


def glb_info(path):
    raw=path.read_bytes()
    magic,ver,n=struct.unpack_from("<4sII",raw)
    require((magic,ver,n)==(b"glTF",2,len(raw)),path)
    length,tag=struct.unpack_from("<I4s",raw,12)
    require(tag==b"JSON",path)
    doc=json.loads(raw[20:20+length])
    data=raw[28+length:]
    images=[]
    for image in doc.get("images",[]):
        view=doc["bufferViews"][image["bufferView"]]
        begin=view.get("byteOffset",0)
        images.append({"name":image.get("name"),"mime":image.get("mimeType"),
                       "sha256":hashlib.sha256(data[begin:begin+view["byteLength"]]).hexdigest()})
    return doc,images


def inspect_transport(delivery):
    sc,images=glb_info(delivery/SCENE)
    birds,bird_images=glb_info(delivery/FLOCK)
    backdrop,backdrop_images=glb_info(delivery/BACKDROP)
    backdrop_names=[node["name"] for node in backdrop["nodes"]]
    names={node["name"]:node for node in sc["nodes"]}
    require(len(backdrop_names)==4 and all(name not in names for name in backdrop_names),backdrop_names)
    require(names[EXIT_NAME]["translation"]==[0,0,-36],names[EXIT_NAME])
    require(len(birds["skins"])==12 and len(birds.get("animations",[]))==1,
            (len(birds["skins"]),len(birds.get("animations",[]))))
    clip=birds["animations"][0]
    last_time=max(birds["accessors"][smp["input"]]["max"][0] for smp in clip["samplers"])
    require(abs(last_time-14.)<.005,last_time)
    fog=[mat for mat in sc["materials"] if mat["name"].startswith("Fog_Start_")]
    land=names["S0_Contact_Continued"]
    primitive,=sc["meshes"][land["mesh"]]["primitives"]
    require(primitive["attributes"].get("COLOR_0") is not None,"Missing terrain wash")
    accessor=sc["accessors"][primitive["attributes"]["COLOR_0"]]
    require(accessor["componentType"]!=5121,("Terrain wash unexpectedly in glTF COLOR_1",accessor))
    require(len(fog)==3 and all(mat.get("doubleSided") and mat.get("alphaMode")=="BLEND" and
                "KHR_materials_unlit" in mat.get("extensions",{}) for mat in fog),fog)
    fog_source,_=glb_info(LIB/"FX-004/v001/FX-004_Fog_Start.glb")
    src_by_name={n["name"]:n for n in fog_source["nodes"]}
    for name,item in src_by_name.items():
        if name.startswith("Fog_") and name!="Fog_Start":
            for prop in ("base_x_BU","amplitude_BU","phase_turns"):
                require(abs(item["extras"][prop]-names[name]["extras"][prop])<1e-5,(name,prop))
    return {"nodes":len(names),"fog_unlit_alpha_blends":len(fog),"runtime_images":images,"optional_backdrop_nodes":backdrop_names,
            "optional_backdrop_images":backdrop_images,
            "flock_images":bird_images,"flock_skins":len(birds["skins"]),
            "flock_clip":clip["name"],"flock_clip_seconds_from_accessor":last_time,
            "flock_clip_channel_count":len(clip["channels"])}


def relative_luminance(path):
    image=bpy.data.images.load(str(path),check_existing=False)
    width,height=image.size
    raw=np.empty(width*height*4,dtype=np.float32)
    image.pixels.foreach_get(raw)
    bpy.data.images.remove(image)
    rgba=raw.reshape(height,width,4)[::-1]
    luma=rgba[:,:,:3]@np.array([.2126,.7152,.0722])
    center=luma[42:126,359:493]
    sides=np.hstack((luma[42:126,156:302],luma[42:126,550:696]))
    return {"center_patch_mean":float(np.mean(center)),"flank_patches_mean":float(np.mean(sides)),
            "center_patch_yx_px":[42,126,359,493],"flank_patches_yx_px":[[42,126,156,302],[42,126,550,696]]}


def verify_fog_control(scene):
    ctrl=scene.objects["Fog_Start"]
    cards=[obj for obj in ctrl.children if obj.type=="MESH"]
    measured={}
    for strength in (1.,.35,0.):
        ctrl["opacity_strength"]=strength
        ctrl["motion_strength"]=strength
        ctrl.update_tag()
        maximum=error=alpha_error=0.
        for frame in range(1,290,18):
            scene.frame_set(frame)
            deps=bpy.context.evaluated_depsgraph_get()
            for obj in cards:
                basex=obj["base_x_BU"]
                x=obj.evaluated_get(deps).location.x
                expected=basex+obj["amplitude_BU"]*strength*math.sin(
                    math.tau*(obj["phase_turns"]+(frame-1)/(FPS*ctrl["period_seconds"])))
                maximum=max(maximum,abs(x-basex))
                error=max(error,abs(x-expected))
                material=obj.data.materials[0]
                opacity=material.node_tree.nodes["Fog opacity control"].inputs[1].default_value
                alpha_error=max(alpha_error,abs(opacity-strength))
        require(error<.00001 and alpha_error<.00001,(strength,error,alpha_error))
        measured[str(strength)]={"samples":17*len(cards),"max_abs_drift_BU":maximum,
                                 "formula_error_BU":error,"alpha_control_error":alpha_error}
    ctrl["opacity_strength"]=1.
    ctrl["motion_strength"]=1.
    return measured


def verify(delivery,out):
    dependencies=source_files()
    expected=read(delivery/"dependencies.json")
    require(dependencies==expected,"source dependency fingerprint changed")
    bpy.ops.wm.open_mainfile(filepath=str(delivery/(STEM+".blend")))
    scene=bpy.context.scene
    native=sample(scene)
    native["Fog_Start_control_reopen"]=verify_fog_control(scene)
    transport=inspect_transport(delivery)
    camera_file=delivery/(STEM+".blend")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    import_glb(delivery/SCENE)
    import_glb(delivery/BACKDROP)
    # The timeline's source frame 1 maps to second zero in the GLB. glTF importer uses scene FPS at import.
    scene.render.fps=FPS
    import_glb(delivery/FLOCK)
    for obj in scene.objects:
        if obj.animation_data and obj.animation_data.nla_tracks:
            tracks=obj.animation_data.nla_tracks
            for track in tracks:
                track.mute=True
            strip=tracks[0].strips[0]
            obj.animation_data.action=strip.action
            obj.animation_data.action_slot=strip.action_slot
            # Blender's importer offsets animations to frame 1 unless configured otherwise.
            if abs(strip.action.frame_range[0])<1e-6:
                action = strip.action
                for curve in action.layers[0].strips[0].channelbag(strip.action_slot).fcurves:
                    for key in curve.keyframe_points:
                        key.co.x+=1
                        key.handle_left.x+=1
                        key.handle_right.x+=1
                    curve.update()
    review=group("Independent review")
    studio(scene,review)
    review_context(review,scene.objects["S0_Contact_Continued"])
    with bpy.data.libraries.load(str(camera_file)) as (available,loaded):
        loaded.objects=["S0_ThirdPersonRig_FixedRear","S0_Technical_Overhead"]
    cam,top=loaded.objects
    review.objects.link(cam)
    review.objects.link(top)
    imported=sample(scene,True,native.pop("packed_world_pose_quantiles"))
    imported.pop("packed_world_pose_quantiles")
    for label,frame in (("takeoff",25),("glide",103),("fog_exit",313)):
        scene.frame_set(frame)
        render(scene,cam,out/f"roundtrip_fixed_rear_{label}.png")
    scene.frame_set(313)
    render(scene,top,out/"roundtrip_top_flock.png",(876,1024))
    brightness=relative_luminance(delivery/"preview_fixed_rear_takeoff.png")
    require(brightness["center_patch_mean"]>brightness["flank_patches_mean"]+.007,brightness)
    write(out/"qa.json",{"id":ID,"version":"v001","status":"needs_review","result":"offline_pass",
                          "mother_reopened":native,"GLB_reimport":imported,"GLB_transport":transport,
                          "center_opening_pixel_context":brightness,
                          "video":ffverify(delivery/VIDEO),"pending":PENDING,
                          "iOS_reference":"Existing iPhone 18 Pro simulator iOS 27.2, build and 340 tests (not rerun for Blender-only asset).",
                          "redline_check":"Checked project checklist. Candidate relies on soft mist and natural terrain. Runtime / device pending."})


def args():
    parser=argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("--quick",action="store_true")
    parser.add_argument("--verify",type=Path)
    return parser.parse_args(__import__("sys").argv[__import__("sys").argv.index("--")+1:])


if __name__=="__main__":
    opts=args()
    opts.output.mkdir(parents=True,exist_ok=True)
    if opts.verify:
        verify(opts.verify,opts.output)
    else:
        build(opts.output,opts.quick)
