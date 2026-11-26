"""Generate and recheck the Feather & Tide ground cloud-shadow candidate."""
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import zlib

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get("FT_GOOSE_ASSET_ROOT", HERE.parents[1])).resolve()
FRAME = (852,393)
S = .9900 / 27.5
FX = "FX-005_CloudShadow"
FPS = 24
TEX_SIDE = 512
LAYER_SPECS = {
    "CoolShadow": {"size_BU": (32.0, 24.0), "relative_position_BU": (-8.,9.5,.012),
                   "alpha_cap": .145, "filename": "ft_goose_vfx_cloud_shadow_alpha.png"},
    "DiffuseLight": {"size_BU": (37.0,27.5), "relative_position_BU": (10.,11.5,.024),
                     "alpha_cap": .115, "filename": "ft_goose_vfx_cloud_light_alpha.png"},
}
SOURCES = {
    "cloud": "ENV-018/v001/textures/ft_shared_atmosphere_cloudpatch_basecolor_alpha.png",
    "paper": "MAT-001/v001/textures/ft_goose_mat_soft_stone_basecolor.png",
    "goose": "CHR-001/v001/CHR-001_goose_rig.blend",
}
SOURCE_DOCUMENTS = ("asset_manifest.json","qa.json","README.md")


def save_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")


def hash_file(path):
    return sha256(path.read_bytes()).hexdigest()


def dependency_check():
    result = {}
    for key, rel in SOURCES.items():
        path = BASE/rel
        asset = BASE/Path(rel).parts[0]/"v001"
        manifest = json.loads((asset/"asset_manifest.json").read_text())
        qa = json.loads((asset/"qa.json").read_text())
        assert qa["status"] in ("done","needs_review"), path
        sha = hash_file(path)
        assert manifest["files"][str(path.relative_to(asset))] == sha, path
        result[key] = {"asset":str(Path(rel).parts[0]), "path":rel, "sha256":sha,
                       "candidate_status":qa["status"],
                       "review_files":{f:hash_file(asset/f) for f in SOURCE_DOCUMENTS}}
        if key in ("paper","cloud"):
            stem = {"paper":"MAT-001_watercolor_master","cloud":"ENV-018_atmosphere_cards"}[key]
            blend = asset/(stem+".blend")
            assert manifest["files"][blend.name]==hash_file(blend)
            result[key]["blend_path"] = str(blend.relative_to(BASE))
            result[key]["blend_sha256"] = hash_file(blend)
            image_name = path.name
            with bpy.data.libraries.load(str(blend),link=False) as (src,dst):
                assert image_name in src.images, (image_name,src.images)
                dst.images = [image_name]
            image, = dst.images
            assert sha256(image.packed_file.data).hexdigest()==sha
    return result


def make_collection(parent,name):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def new_object(group,name,data,location=(0.,0.,0.)):
    obj = bpy.data.objects.new(name,data)
    group.objects.link(obj)
    obj.location = location
    return obj


def mesh(group,name,vertices,faces,material,uv=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices,[],faces)
    data.update()
    if material:
        data.materials.append(material)
    if uv:
        uv_layer = data.uv_layers.new(name="MaskUV")
        for corner in data.loops:
            uv_layer.data[corner.index].uv = uv[corner.vertex_index]
    return new_object(group,name,data)


def rgba_png(path,array):
    def chunk(kind,value):
        return struct.pack(">I",len(value))+kind+value+struct.pack(">I",zlib.crc32(kind+value))
    pixels = b"".join(b"\0"+row.tobytes() for row in array[::-1])
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+
                     chunk(b"IHDR",struct.pack(">2I5B",array.shape[1],array.shape[0],8,6,0,0,0))+
                     chunk(b"IDAT",zlib.compress(pixels,9))+chunk(b"IEND",b""))


def image_pixels(image):
    arr = np.empty(image.size[0]*image.size[1]*4,dtype=np.float32)
    image.pixels.foreach_get(arr)
    return arr.reshape(image.size[1],image.size[0],4)


def loose_paper(color,paper_name):
    material = bpy.data.materials.new("Review terrain wash")
    material.use_nodes = True
    graph = material.node_tree
    graph.nodes.clear()
    tex = graph.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images[paper_name]
    tex.location = (-600,0)
    tex.extension = "REPEAT"
    multiply = graph.nodes.new("ShaderNodeMixRGB")
    multiply.blend_type = "MULTIPLY"
    multiply.inputs[0].default_value = .16
    multiply.inputs[1].default_value = (*color,1.)
    multiply.location = (-310,0)
    diffuse = graph.nodes.new("ShaderNodeEmission")
    diffuse.location = (-60,0)
    out = graph.nodes.new("ShaderNodeOutputMaterial")
    out.location = (160,0)
    graph.links.new(tex.outputs["Color"],multiply.inputs[2])
    graph.links.new(multiply.outputs[0],diffuse.inputs[0])
    graph.links.new(diffuse.outputs[0],out.inputs[0])
    return material


def flat(name,hexcode):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    shader = nodes.new("ShaderNodeEmission")
    parts = [int(hexcode[i:i+2],16)/255. for i in (0,2,4)]
    linear = tuple(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in parts)
    shader.inputs["Color"].default_value = (*linear,1.)
    mat.diffuse_color = (*linear,1.)
    mat.node_tree.links.new(shader.outputs[0],nodes.new("ShaderNodeOutputMaterial").inputs[0])
    return mat


def mask_material(name, image, preview=False):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.surface_render_method = "BLENDED"
    mat.use_backface_culling = True
    tree = mat.node_tree
    nodes = tree.nodes
    nodes.clear()
    texture = nodes.new("ShaderNodeTexImage")
    texture.location = (-550,30)
    texture.image = image
    texture.extension = "EXTEND"
    alpha = texture.outputs["Alpha"]
    if preview:
        gain = nodes.new("ShaderNodeMath")
        gain.name = "Review strength"
        gain.label = "Review strength 0–1"
        gain.operation = "MULTIPLY"
        gain.inputs[1].default_value = 1.
        gain.location = (-280,40)
        tree.links.new(alpha,gain.inputs[0])
        alpha = gain.outputs[0]
    lamp = nodes.new("ShaderNodeEmission")
    lamp.location = (-220,-210)
    tree.links.new(texture.outputs["Color"],lamp.inputs["Color"])
    light_path = nodes.new("ShaderNodeLightPath")
    light_path.location = (-225,-430)
    visible = nodes.new("ShaderNodeMixShader")
    visible.location = (25,-205)
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    transparent.location = (-220,260)
    tree.links.new(light_path.outputs["Is Camera Ray"],visible.inputs[0])
    tree.links.new(transparent.outputs[0],visible.inputs[1])
    tree.links.new(lamp.outputs[0],visible.inputs[2])
    mix = nodes.new("ShaderNodeMixShader")
    mix.location = (225,50)
    tree.links.new(alpha,mix.inputs[0])
    tree.links.new(transparent.outputs[0],mix.inputs[1])
    tree.links.new(visible.outputs[0],mix.inputs[2])
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (445,50)
    tree.links.new(mix.outputs[0],out.inputs["Surface"])
    return mat


def smoother(t):
    t = np.clip(t,0.,1.)
    return t*t*t*(t*(6*t-15)+10)


def blur_grid(s,sigma=13):
    taps = np.arange(-math.ceil(sigma*4),math.ceil(sigma*4)+1)
    coeffs = np.exp(-.5*(taps/sigma)**2)
    coeffs /= coeffs.sum()
    for axis in (0,1):
        s = np.apply_along_axis(lambda row: np.convolve(row,coeffs,mode="same"),axis,s)
    return s


def build_masks(out):
    u,v = np.meshgrid(np.linspace(0,1,TEX_SIDE),np.linspace(0,1,TEX_SIDE))
    base = image_pixels(bpy.data.images[Path(SOURCES["cloud"]).name])[:,:,3]
    paper = image_pixels(bpy.data.images[Path(SOURCES["paper"]).name])[...,:3].mean(2)
    paper -= np.median(paper)
    paper = np.clip(paper/max(.01,np.quantile(np.abs(paper),.90)),-1,1)
    edge = smoother(np.minimum.reduce((u,v,1-u,1-v))/.24)
    base = blur_grid(base,24)
    quality = {}
    images = {}
    for name,spec in LAYER_SPECS.items():
        if name=="CoolShadow":
            matte = np.power(base/base.max(),.75)*edge
            rgb = np.array([103.,117.,132.])
        else:
            # A broad warm wash follows a separate downwind lobe.
            x = u-.48+.09*np.sin(v*4)
            y = v-.51
            diffuse = np.exp(-3.4*((x/.55)**2+(y/.62)**2))
            borrowed_cloud = np.flip(base,axis=1)/base.max()
            matte = (.82*diffuse+.18*borrowed_cloud)*edge
            rgb = np.array([244.,226.,176.])
        alpha = matte / matte.max()*spec["alpha_cap"]
        rgb = (rgb[None,None,:]+paper[...,None]*2.05)
        rgba = np.rint(np.dstack((rgb,alpha*255))).clip(0,255).astype(np.uint8)
        path = out/"textures"/spec["filename"]
        rgba_png(path,rgba)
        image = bpy.data.images.load(str(path),check_existing=False)
        image.alpha_mode = "STRAIGHT"
        image.pack()
        image.filepath = f"//textures/{path.name}"
        images[name] = image
        a = rgba[...,3].astype(int)
        edge_samples = np.concatenate((a[0],a[-1],a[:,0],a[:,-1]))
        grad = max(np.abs(np.diff(a,axis=0)).max(),np.abs(np.diff(a,axis=1)).max())
        assert a.max()<=math.ceil(spec["alpha_cap"]*255) and edge_samples.max()==0 and grad<=1
        quality[name] = {"file":str(path.relative_to(out)), "sha256":hash_file(path),
                         "max_alpha_8bit":int(a.max()),"max_adjacent_alpha_step_8bit":int(grad),
                         "alpha_at_texture_edge_8bit":int(edge_samples.max()),"resolution":list(image.size)}
    return images,quality


def carrier(group):
    root = new_object(group,"CloudShadow",None)
    root.empty_display_type = "PLAIN_AXES"
    root["asset_id"] = "FX-005"
    root["collision_enabled"] = False
    root["purpose"] = "visual_only_ground_wash"
    root["default_alpha_gain"] = 1.0
    root["reduced_alpha_gain"] = .35
    root["off_alpha_gain"] = 0.
    root["default_drift_BU_per_second"] = .78
    root["mountain_pass_drift_BU_per_second"] = 1.28
    root["review_start_frame"] = 1
    root["review_seconds"] = 4.
    root["physics_and_triggers"] = "none"
    objects = {}
    for name,spec in LAYER_SPECS.items():
        w,h = spec["size_BU"]
        vertices = [(-w/2,-h/2,0),(w/2,-h/2,0),(w/2,h/2,0),(-w/2,h/2,0)]
        ob = mesh(group,name,vertices,[(0,1,2,3)],None,[(0,0),(1,0),(1,1),(0,1)])
        ob.parent = root
        ob.location = spec["relative_position_BU"]
        ob["collision_enabled"] = False
        ob["role"] = "horizontal_receiver_coverage"
        objects[name] = ob
    return root,objects


def stage_camera(group):
    cam = bpy.data.cameras.new("Gameplay | fixed rear")
    cam.sensor_fit = "VERTICAL"
    cam.sensor_height = 24
    cam.lens = 12/math.tan(math.radians(50)/2)
    cam.clip_start,cam.clip_end = .015,2400.
    obj = new_object(group,cam.name,cam,(0,-180*math.cos(.48)*S,180*math.sin(.48)*S))
    target = Vector((0,0,6*S))
    obj.rotation_euler = (target-obj.location).to_track_quat("-Z","Y").to_euler()
    return obj


def route_shape(y):
    return 1.35*math.sin((y+2)*.21)+.069*y


def backdrop(scene, group, camera):
    scene.world = bpy.data.worlds.new("Soft wetland daylight")
    scene.world.use_nodes = True
    node = scene.world.node_tree.nodes.get("Background")
    node.inputs["Color"].default_value = (.50,.56,.59,1)
    node.inputs["Strength"].default_value = .85
    terrain = loose_paper((.389,.442,.358),Path(SOURCES["paper"]).name)
    plane = [(-140,-120,0),(140,-120,0),(140,300,0),(-140,300,0)]
    mesh(group,"Wetland ground",plane,[(0,1,2,3)],terrain,[(0,0),(6,0),(6,9),(0,9)])

    river_materials = [flat("Damp margin","96A892"),flat("Shore wash","A2B5A2"),
                       flat("Quiet water","A6B9AE"),flat("Silver water","ADBFBC")]
    ys = np.linspace(-12,78,108)
    for i,(width,offset) in enumerate([(3.88,0.),(3.65,0.),(3.36,0.),(1.93,.31)]):
        verts = []
        for y in ys:
            x = route_shape(y)
            w = width + .45*math.sin(y*.21)
            verts += [(x+offset-w,y,.001+i*.001),(x+offset+w,y,.001+i*.001)]
        quads = [(i,i+1,i+3,i+2) for i in range(0,len(verts)-2,2)]
        mesh(group,f"River wash {i+1}",verts,quads,river_materials[i])

    # All these path-mark footprints are above the projection sheets.
    route_material = flat("Source-like faded route gold","B19A68")
    markers = []
    for i,y in enumerate(np.arange(-4.4,14.,.56)):
        x = route_shape(y)
        center = (x,y,1.6*S)
        r = 2.5*S
        vertices = [(-r,-r,0),(r,-r,0),(r,r,0),(-r,r,0)]
        item = mesh(group,f"Path review dot {i+1:02}",vertices,[(0,1,2,3)],route_material)
        item.location = center
        markers.append(item)

    crease = flat("Subtle shore pigment","929F8E")
    rng = np.random.default_rng(23573)
    water_ripples = []
    for i in range(44):
        y = rng.uniform(-5,35)
        x = route_shape(y)+rng.uniform(-3.2,3.2)
        w = rng.uniform(.18,.71)
        water_ripples += [(x-w/2,y,.006),(x+w/2,y,.006),(x+w/2,y+.018,.006),(x-w/2,y+.02,.006)]
    mesh(group,"Shallow horizontal pigment strokes",water_ripples,
         [(i,i+1,i+2,i+3) for i in range(0,len(water_ripples),4)],crease)

    with bpy.data.libraries.load(str(BASE/SOURCES["goose"]),link=False) as (src,dst):
        assert "Goose_LOD0" in src.meshes
        dst.meshes = ["Goose_LOD0"]
    bird_mesh, = dst.meshes
    for i,(x,y,z,scale) in enumerate([(0,0,8,1),(-45,-25,6,.8),(45,-25,6,.8),
                                      (-76,-48,6,.8),(76,-48,6,.8),(0,-38,6,.8)]):
        goose = new_object(group,f"CHR-001 review bird {i+1:02}",bird_mesh,(x*S,y*S,z*S))
        goose.scale = (scale,)*3
        markers.append(goose)
    sun_data = bpy.data.lights.new("Soft daylight","SUN")
    sun_data.energy = 1.7
    sun_data.angle = .58
    sun = new_object(group,sun_data.name,sun_data)
    sun.rotation_euler = Vector((.28,.29,-1)).to_track_quat("-Z","Y").to_euler()
    return markers


def setup_render(scene):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 6
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.max_bounces = 4
    scene.cycles.transparent_max_bounces = 8
    scene.render.resolution_x,scene.render.resolution_y = FRAME
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"


def render(scene,path,samples=12):
    scene.cycles.samples = samples
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True,scene=scene.name)


def save_source(scene,out):
    scene.render.filepath = "//"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(out/f"{FX}.blend"),relative_remap=False)


def export_glb(root,objects,out):
    bpy.ops.object.select_all(action="DESELECT")
    for item in [root,*objects.values()]:
        item.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.gltf(filepath=str(out/f"{FX}.glb"),export_format="GLB",use_selection=True,
                              export_yup=True,export_animations=False,export_extras=True)


def set_strength(mat, amount):
    mat.node_tree.nodes["Review strength"].inputs[1].default_value = amount


def animate(scene,root):
    scene.frame_start,scene.frame_end = 1,97
    root.location = (-1.56,0,0)
    root.keyframe_insert("location",index=0,frame=1)
    root.location = (1.56,0,0)
    root.keyframe_insert("location",index=0,frame=97)
    action = root.animation_data.action
    action.name = "CloudShadow_Drift_Review"
    strip = action.layers[0].strips[0]
    channelbag = strip.channelbag(root.animation_data.action_slot)
    for fcurve in channelbag.fcurves:
        for key in fcurve.keyframe_points:
            key.interpolation = "LINEAR"
    scene.frame_set(49)


def render_video(scene,out):
    with TemporaryDirectory(prefix="fx-005-frames-") as temp:
        folder = Path(temp)
        for index in range(48):
            scene.frame_set(1+index*2)
            render(scene,folder/f"{index:03d}.png",4)
        subprocess.run(["ffmpeg","-v","error","-xerror","-framerate","12",
                        "-i",str(folder/"%03d.png"),"-an","-c:v","libx264","-crf","15",
                        "-pix_fmt","yuv420p","-vf","pad=852:394:0:0:color=0x999F8A",
                        "-movflags","+faststart",str(out/"preview_fixed_rear.mp4")],check=True)


def main(out):
    out.mkdir(parents=True,exist_ok=True)
    assert not any(out.iterdir()),out
    (out/"textures").mkdir()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    setup = dependency_check()
    scene = bpy.context.scene
    scene.name = "FX-005 | Fixed rear cloud shadow study"
    asset = make_collection(scene.collection,"FX-005 | CloudShadow")
    review = make_collection(scene.collection,"Review | wetland and route")
    camera = stage_camera(review)
    scene.camera = camera
    backdrop(scene,review,camera)
    setup_render(scene)
    root,objects = carrier(asset)
    for name,item in objects.items():
        item.data.materials.append(flat(f"Graybox test {name}","777C7C" if name=="CoolShadow" else "ADB0AA"))
    render(scene,out/"graybox_fixed_planes.png",8)
    images,map_stats = build_masks(out)
    for name,item in objects.items():
        item.data.materials[0] = mask_material(name+"_RGBA",images[name])
    export_glb(root,objects,out)
    for name,item in objects.items():
        item.data.materials[0] = mask_material(name+"_Review",images[name],preview=True)
    animate(scene,root)
    for name, strength in [("off",0.),("reduced",.35),("default",1.)]:
        for item in objects.values():
            set_strength(item.data.materials[0],strength)
        render(scene,out/f"preview_fixed_{name}.png",16)
    # Isolate each lobe using the same geometry and camera as the combined plate.
    for name,item in objects.items():
        item.hide_render = True
    for name,item in objects.items():
        item.hide_render = False
        render(scene,out/f"preview_fixed_{name.lower()}.png",14)
        item.hide_render = True
    for item in objects.values():
        item.hide_render = False
    bpy.context.view_layer.objects.active = root
    for area in [area for screen in bpy.data.screens for area in screen.areas if area.type=="VIEW_3D"]:
        area.spaces.active.region_3d.view_perspective = "CAMERA"
    save_source(scene,out)
    render_video(scene,out)
    save_json(out/"generation_evidence.json",{"dependencies":setup,"masks":map_stats,
              "camera": {"Blender_location_BU":list(camera.location),"distance_game_units":180,
              "pitch_parameter_rad":.48,"vertical_fov_deg":50,"aim_height_game_units":6,
              "scale_BU_per_game_unit":S,"resolution_px":FRAME},
              "video_source_frames":48,"review_strength_levels":{"off":0.,"reduced":.35,"default":1.}})


if __name__=="__main__":
    main(Path(sys.argv[sys.argv.index("--")+1]).resolve())
