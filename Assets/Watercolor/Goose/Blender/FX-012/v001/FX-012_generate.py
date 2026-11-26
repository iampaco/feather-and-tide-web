"""Generate and recheck the Feather & Tide RestCue candidate with Blender 5.2.2."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import numpy as np


STEM = "FX-012_RestCue"
BASE = (852,393)
SCALE = 27.5 / .9900
FPS = 24
STAGES = {
    "S1": {
        "asset": "ENV-014", "blend": "ENV-014_checkpoint_a.blend", "module": "CheckpointA",
        "scene": "ENV-014 | Fixed rear and route context", "leader": (-.46,-3.10), "origin": (0,0,0),
        "water_washes": [(2.79,-2.77,.68,.64),(2.87,.96,.74,1.27),(-3.25,1.92,.56,.88)],
        "reed_washes": [(4.03,-1.64,1.55,.46), (4.41,1.32,1.48,.48),(-4.54,1.14,.88,.40)],
    },
    "S2": {
        "asset": "ENV-015", "blend": "ENV-015_lakeside_rest.blend", "module": "LakesideRest",
        "scene": "ENV-015 | Material review in long lake", "leader": (3.54,6.90), "origin": (4,10,0),
        "water_washes": [(-3.99,-2.65,.55,1.04),(-3.95,1.15,.67,1.25),(3.16,-2.17,.60,1.31),
                         (2.82,2.83,.85,.63)],
        "reed_washes": [(-4.27,-2.0,1.26,.44),(-4.39,.91,1.27,.48),(-2.99,4.03,1.21,.47)],
    },
    "S4": {
        "asset": "ENV-016", "blend": "ENV-016_protected_marsh.blend", "module": "ProtectedMarsh",
        "scene": "ENV-016 | Fixed rear review and Swift sweep", "leader": (0,-3.05), "origin": (0,0,0),
        "water_washes": [(2.79,-2.77,.68,.64),(2.87,.96,.74,1.27),(-3.25,1.92,.56,.88),
                         (-6.28,1.32,.92,1.28)],
        "reed_washes": [(-11.0,4.42,2.05,.51),(-11.7,5.15,1.81,.43),(-12.55,10.98,1.48,.47)],
    },
}
MASKS = {
    "water": ("ft_goose_fx_rest_cue_water.png", "EEE1C1", .57),
    "reed": ("ft_goose_fx_rest_cue_reeds.png", "E9DBB8", .25),
}
REVIEW_SCHEDULE = (
    (1, 1, 0), (6, 1, 0), (15, 1, 1), (56, 1, 1), (57, 1, 0),
    (90, 1, 0), (91, 1, 1), (111, 1, 1), (112, 0, 1),
    (130, 0, 1), (131, 0, 0), (148, 0, 1),
)
FEATHER_STRENGTH = .095
WATER_LIFT = .009
AVAILABLE_IDLE = .27


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")


def binary(name):
    resolved = shutil.which(name)
    if not resolved:
        resolved = next((str(p) for p in (Path("/opt/homebrew/bin")/name, Path("/usr/local/bin")/name)
                         if p.is_file()), None)
    require(resolved, name)
    return resolved


def source_file(root, config):
    folder = root/config["asset"]/"v001"
    manifest = json.loads((folder/"asset_manifest.json").read_text())
    records = manifest.get("files",manifest.get("files_sha256"))
    path = folder/config["blend"]
    require(sha(path) == records[path.name], (path,"source manifest hash"))
    return path


def append_scene(root, config):
    path = source_file(root, config)
    with bpy.data.libraries.load(str(path),link=False) as (source, target):
        require(config["scene"] in source.scenes, config["scene"])
        target.scenes = [config["scene"]]
    return target.scenes[0]


def switch(scene):
    bpy.context.window.scene = scene
    bpy.context.view_layer.update()


def paint_mask(base, kind, folder):
    name, color, amplitude = MASKS[kind]
    resolution = 192
    image = bpy.data.images.new(name, resolution, resolution, alpha=True, float_buffer=False)
    values = np.empty((resolution,resolution,4),dtype=np.float32)
    for i in range(3):
        values[:,:,i] = base["color"](color)[i]
    for j in range(resolution):
        v = j/(resolution-1) * 2-1
        for i in range(resolution):
            u = i/(resolution-1) * 2-1
            grain = .93 + .032 * math.sin(102*u+13*v) * math.sin(93*v-2*u)
            if kind == "water":
                curve = v-.13*math.sin(1.9*u+.6)
                band = (.82+.18*math.cos(18*curve+2*u))
                envelope = max(0,1-(u*u+curve*curve))**1.68 * band
            else:
                envelope = max(0,1-u*u)**2.65 * max(0,1-v*v)**2.12
            edge = min(i,j,resolution-1-i,resolution-1-j)
            values[j,i,3] = amplitude*envelope*grain*min(1,edge/8)
    image.pixels.foreach_set(values.ravel())
    image.filepath_raw = str(folder/name)
    image.file_format = "PNG"
    image.save()
    image.pack()
    return image


def transparent_surface(kind, image, controller=None):
    mat = bpy.data.materials.new("RestCue | " + ("Warm shallow water" if kind=="water" else "Reed-edge light"))
    mat.use_nodes = True
    mat.surface_render_method = "BLENDED"
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    transmission = nodes.new("ShaderNodeBsdfTransparent")
    mask = nodes.new("ShaderNodeTexImage")
    mask.image = image
    mask.extension = "EXTEND"
    blend = nodes.new("ShaderNodeMixShader")
    # Color feeds the camera-ray shader directly as an unlit surface, with no scene-wide lighting.
    lighting = nodes.new("ShaderNodeMixShader")
    path = nodes.new("ShaderNodeLightPath")
    links.new(path.outputs["Is Camera Ray"],lighting.inputs[0])
    links.new(transmission.outputs[0],lighting.inputs[1])
    links.new(mask.outputs["Color"],lighting.inputs[2])
    links.new(transmission.outputs[0],blend.inputs[1])
    links.new(lighting.outputs[0],blend.inputs[2])
    alpha = mask.outputs["Alpha"]
    if controller is not None:
        multiply = nodes.new("ShaderNodeMath")
        multiply.operation = "MULTIPLY"
        links.new(alpha,multiply.inputs[0])
        drive(multiply.inputs[1],controller)
        alpha = multiply.outputs[0]
    links.new(alpha,blend.inputs[0])
    links.new(blend.outputs[0],output.inputs["Surface"])
    return mat


def drive(socket, controller, factor=1.0, prop="displayIntensity"):
    curve = socket.driver_add("default_value")
    entry = curve.driver.variables.new()
    entry.name = "amplitude"
    entry.type = "SINGLE_PROP"
    entry.targets[0].id = controller
    entry.targets[0].data_path = f'["{prop}"]'
    curve.driver.expression = f"amplitude*{factor}"
    require(curve.driver.is_simple_expression, "driver expression")


def script_cue():
    # State and capacity are fed from one authoritative site record. This function only returns a visual signal.
    envelope = 0.0
    values = []
    for frame in range(1,149):
        index = max(index for index,row in enumerate(REVIEW_SCHEDULE) if row[0] <= frame)
        _,capacity_available,all_settled = REVIEW_SCHEDULE[index]
        target = float(capacity_available and all_settled)
        tau = .68 if target > envelope else .39
        envelope += (target-envelope)*(1-math.exp(-1/(FPS*tau)))
        display = AVAILABLE_IDLE + (1 - AVAILABLE_IDLE) * envelope if capacity_available else 0.0
        values.append((capacity_available, all_settled, display, envelope if capacity_available else 0.0))
    return values


def control(base, group, stage, origin):
    ctrl = base["obj"](group,f"RestCue | {stage} review controls",None,origin)
    names = ("capacityAvailable","allSettled","displayIntensity","featherIntensity")
    for name,title in (
        ("capacityAvailable","Runtime site capacity is available"),
        ("allSettled","All active members are settled at this site"),
        ("displayIntensity","Preview alpha above the available idle baseline. See runtime interface."),
        ("featherIntensity","Recovery envelope for the feather tint only."),
    ):
        ctrl[name] = 0.0
        ctrl.id_properties_ui(name).update(min=0.0,max=1.0,description=title)
    for frame,data in enumerate(script_cue(),1):
        for name,value in zip(names,data,strict=True):
            if name in names[:2] and frame not in [row[0] for row in REVIEW_SCHEDULE]:
                continue
            ctrl[name] = float(value)
            ctrl.keyframe_insert(data_path=f'["{name}"]',frame=frame)
    slot = ctrl.animation_data.action_slot
    action = ctrl.animation_data.action
    for layer in action.layers:
        for strip in layer.strips:
            bag = strip.channelbag(slot)
            for curve in bag.fcurves:
                for key in curve.keyframe_points:
                    key.interpolation = "LINEAR" if "Intensity" in curve.data_path else "CONSTANT"
    return ctrl


def clip_to_rectangle(poly, box):
    cx,cy,rx,ry = box
    for coordinate, bound, inward in ((0,cx-rx,1),(0,cx+rx,-1),(1,cy-ry,1),(1,cy+ry,-1)):
        if not poly:
            break
        result = []
        prev = poly[-1]
        for point in poly:
            was_in = inward*(prev[coordinate]-bound) >= 0
            is_in = inward*(point[coordinate]-bound) >= 0
            if was_in != is_in:
                t = (bound-prev[coordinate])/(point[coordinate]-prev[coordinate])
                result.append(prev.lerp(point,t))
            if is_in:
                result.append(point)
            prev = point
        poly = result
    return poly


def compile_mesh(name, polygons, uv_polygons, mat):
    points, faces = [], []
    for poly in polygons:
        faces.append(tuple(range(len(points),len(points)+len(poly))))
        points.extend(poly)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points,[],faces)
    mesh.update()
    uvs = mesh.uv_layers.new(name="RestCueMask")
    for face, params in zip(mesh.polygons,uv_polygons,strict=True):
        for li, uv in zip(face.loop_indices,params,strict=True):
            uvs.data[li].uv = uv
    mesh.materials.append(mat)
    return mesh


def water_wash(stage, water, config, mat):
    polygons, coords = [], []
    water.data.calc_loop_triangles()
    for box in config["water_washes"]:
        cx,cy,rx,ry = box
        for tri in water.data.loop_triangles:
            clipped = clip_to_rectangle([water.data.vertices[i].co.copy() for i in tri.vertices],box)
            if len(clipped)<3:
                continue
            if (clipped[1]-clipped[0]).cross(clipped[-1]-clipped[0]).length < 1e-9:
                continue
            if (clipped[1]-clipped[0]).cross(clipped[-1]-clipped[0]).z < 0:
                clipped.reverse()
            polygons.append([Vector((p.x,p.y,p.z+WATER_LIFT)) for p in clipped])
            coords.append([(.5+.5*((p.x-cx)/rx),.5+.5*((p.y-cy)/ry)) for p in clipped])
    return compile_mesh(f"RestCue_{stage}_ShallowLight",polygons,coords,mat)


def reed_wash(stage, config, mat):
    polygons = []
    for x,y,w,h in config["reed_washes"]:
        # A planted veil with a small lean gives a rim on the actual reed layer.
        polygons.append([(x-w/2,y,.035),(x+w/2,y,.035),(x+w*.56,y+.16,.035+h),(x-w*.44,y+.16,.035+h)])
    uv = [(0,0),(1,0),(1,1),(0,1)]
    return compile_mesh(f"RestCue_{stage}_ReedHalo",polygons,[uv]*len(polygons),mat)


def tint_flock(scene, birds, ctrl, base, stage):
    materials = {}
    for bird in birds:
        bird.hide_render = False
        bird.hide_set(False)
        for slot in bird.material_slots:
            original = slot.material
            if not original or not original.use_nodes:
                continue
            if "bill" in original.name.lower() or "foot" in original.name.lower():
                continue
            if original not in materials:
                mat = original.copy()
                mat.name = f"RestCue | {stage} feather tint | {original.name}"
                shader = next((node for node in mat.node_tree.nodes if node.type=="BSDF_PRINCIPLED"),None)
                if shader is None:
                    continue
                color_input = shader.inputs["Base Color"]
                prior = color_input.links[0].from_socket if color_input.is_linked else None
                mix = mat.node_tree.nodes.new("ShaderNodeMixRGB")
                mix.blend_type = "MULTIPLY"
                mix.inputs[1].default_value = color_input.default_value
                mix.inputs[2].default_value = (1.28,1.05,.79,1.0)
                if prior is not None:
                    mat.node_tree.links.new(prior,mix.inputs[1])
                mat.node_tree.links.new(mix.outputs[0],color_input)
                drive(mix.inputs[0],ctrl,FEATHER_STRENGTH,prop="featherIntensity")
                materials[original] = mat
            slot.link = "OBJECT"
            slot.material = materials[original]
    return len(materials)


def source_layers(scene, token):
    return {kind:next(o for o in scene.objects if o.name.startswith(f"{token}_{kind}"))
            for kind in ("Ground","Water","Reeds")}


def plain(scene, group, meshes, base):
    context = {"Ground":"A5AA9E","Water":"9DAFB0","Reeds":"819284"}
    for kind, src in meshes.items():
        item = base["obj"](group,f"Graybox source {kind}",src.data,src.location)
        mat = base["paint"](f"Graybox source {kind}",context[kind])
        for slot in item.material_slots:
            slot.link = "OBJECT"
            slot.material = mat
    return [o for o in group.objects]


def new_rear(base, scene, group, config):
    cam = base["camera"](group, "Fixed rear | RestCue reference", (0,0,1), (0,1,0))
    base["follow"](cam,config["leader"],Vector((0,1)))
    scene.render.resolution_x, scene.render.resolution_y = BASE
    scene.camera = cam
    return cam


def stage_scene(root, stage, base, gray):
    config = STAGES[stage]
    reference = append_scene(root,config)
    meshes = source_layers(reference,config["module"])
    if gray:
        scene = bpy.data.scenes.new(f"RestCue | {stage} graybox")
    else:
        scene = reference
        scene.name = f"RestCue | {stage} actual wetland"
    switch(scene)
    group = base["collection"]("FX-012 | RestCue review and layer control",scene.collection)
    if gray:
        lighting = base["studio"](scene,scene.collection)
        plain(scene,group,meshes,base)
    else:
        lighting = group
        for obj in scene.objects:
            if obj.name.startswith(("Review | CHR-001 neutral pose","Review neutral goose",
                                    "Review | flight reference","CHR-001 | neutral graybox")):
                obj.hide_render = True
            if obj.name.startswith(("Review | path at source game-plane height",
                                    "Ingress and egress route | technical reference",
                                    "Measured Swift radius | review ticks")):
                obj.hide_render = True
    camera = new_rear(base,scene,lighting,config)
    ctrl = None if gray else control(base,group,stage,config["origin"])
    if gray:
        materials = [base["paint"]("Graybox | water coverage","C0C6BD"),
                     base["paint"]("Graybox | reed plane","C5C9BF")]
    else:
        materials = [transparent_surface(kind, bpy.data.images[MASKS[kind][0]], ctrl) for kind in MASKS]
    water = base["obj"](group,f"RestCue_{stage}_ShallowLight",
                        water_wash(stage,meshes["Water"],config,materials[0]),config["origin"])
    reed = base["obj"](group,f"RestCue_{stage}_ReedHalo",reed_wash(stage,config,materials[1]),config["origin"])
    birds = [o for o in reference.objects if o.name.startswith("Review resting goose")]
    require(len(birds)==12,(stage,len(birds)))
    if gray:
        for bird in birds:
            clone = base["obj"](group,f"Graybox | {bird.name}",bird.data,bird.location)
            clone.rotation_euler=bird.rotation_euler
            neutral = base["paint"]("Graybox | neutral goose","D1D1C6")
            for mesh_slot in clone.material_slots:
                mesh_slot.link = "OBJECT"
                mesh_slot.material = neutral
    else:
        require(tint_flock(scene,birds,ctrl,base,stage)>0,(stage,"feather shader bindings"))
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1,148
    return scene,camera,ctrl,water,reed,meshes,birds


def layers_by_name(scene, stage):
    water = next(o for o in scene.objects if o.name.startswith(f"RestCue_{stage}_ShallowLight"))
    reed = next(o for o in scene.objects if o.name.startswith(f"RestCue_{stage}_ReedHalo"))
    return water,reed


def make_export(stage, payload, folder, base):
    src = payload[3:5]
    scene = bpy.data.scenes.new(f"RestCue | {stage} export at module origin")
    switch(scene)
    group = base["collection"]("FX-012 | two runtime draw layers",scene.collection)
    root = base["obj"](group,f"RestCue_{stage}",None)
    root["asset_id"] = "FX-012"
    root["module_fit"] = STAGES[stage]["asset"]
    root["runtime_state"] = "Client must apply visual amplitude to authored alpha"
    for kind,item in zip(MASKS,src,strict=True):
        name = f"RestCue_{stage}_" + ("ShallowLight" if kind=="water" else "ReedHalo")
        mesh = item.data.copy()
        previous = bpy.data.objects.get(name)
        if previous is not None:
            previous.name = f"{name} | review"
        export = base["obj"](group,name,mesh)
        mesh.materials[0] = transparent_surface(kind,bpy.data.images[MASKS[kind][0]])
        export.parent = root
        export["surface"] = kind
        export["sortRole"] = "above source water" if kind=="water" else "translucent foliage edge"
        export.select_set(True)
    root.select_set(True)
    bpy.context.view_layer.objects.active = root
    path = folder/f"{STEM}_{stage}.glb"
    result = bpy.ops.export_scene.gltf(filepath=str(path), use_selection=True, use_active_scene=True,
                                        export_yup=True, export_animations=False, export_extras=True)
    require(result=={"FINISHED"},path)


def interface(root):
    records = {}
    for stage,config in STAGES.items():
        path = source_file(root,config)
        records[stage] = {
            "asset": f"{config['asset']}/v001", "blender_source": path.relative_to(root).as_posix(),
            "sha256": sha(path), "glb": f"{STEM}_{stage}.glb",
            "origin_relative_to_module_BU": [0,0,0], "review_module_placement_BU": config["origin"],
            "water_mesh": f"RestCue_{stage}_ShallowLight", "reed_mesh": f"RestCue_{stage}_ReedHalo",
            "water_mask_windows_module_xy_half_extents_BU": config["water_washes"],
            "reed_veil_module_xy_width_height_BU": config["reed_washes"],
        }
    return {
        "asset_id":"FX-012", "variant":"RestCue", "stage_fits":records,
        "axes":{"Blender":"+Z up, +Y forward","glTF_to_RealityKit":"Y up, -Z forward (x,z,-y)"},
        "camera":{"resolution":BASE,"distance_game_units":180,"pitch_rad":.48,"vertical_fov_degrees":50,
                  "target_height_game_units":6,"goose_beak_to_tail_BU":.9900,"game_units_per_BU":SCALE},
        "read_only_inputs":{
            "siteID":"Stable engine ID associated with the same capacity record across re-entry and restart.",
            "capacityAvailable":"Game-authoritative bool evaluated per site.",
            "allActiveFlockSettled":"True if the active flock is settled inside this site's rest zone.",
            "dtSeconds":"Non-negative visual update interval in seconds.",
            "restingBirdIDs":"Optional roster supplied by the game's flock state for feather tint at this site.",
        },
        "algorithm":{
            "initialVisualAmplitude":0,
            "target":"capacityAvailable && allActiveFlockSettled ? 1.0 : 0.0",
            "smoothing":"v += (target-v)*(1-exp(-dtSeconds/tau)); choose tau=0.68s rising, 0.39s falling.",
            "capacity_gate":"If capacityAvailable is false, force visual output to 0 immediately.",
            "available_idle_alpha_scale":AVAILABLE_IDLE,
            "visualDisplay":"When available, alpha scale is 0.27 + 0.73*v; the released cue approaches 0.27. "
                            "If exhausted, alpha scale is 0.",
            "waterAndReeds":"Use draw opacity = authored texture alpha * visual output. GLBs carry max masks for inspection.",
            "featherTone":"For settled members and feather slots only, lerp baseColor to "
                          "baseColor*(1.28, 1.05, 0.79) in linear RGB with t = v*0.095, gated off when exhausted.",
        },
        "texture_layers":{kind:{"path":f"textures/{record[0]}","sRGB_hex":record[1],"max_alpha_before_grain":record[2]}
                          for kind,record in MASKS.items()},
        "water_lift_BU":WATER_LIFT,
        "transparency":"Two unlit alpha-blended layers. Draw shallow wash over source water. On-site sorting "
                       "with water and foliage to be checked in RealityKit.",
        "capacity_ownership":"The engine owns the site state, capacity, save/retry rules and Zone membership. "
                             "The preview controller persists its explicit exhausted flag across the reentry demonstration.",
    }


def render(base,payload,output,name,frame,samples=12):
    scene,cam,*unused = payload
    switch(scene)
    scene.frame_set(frame)
    base["render"](scene,cam,output,name,BASE,samples)


def video(base,stages,output):
    frames = output.with_name(output.name+"-frames")
    frames.mkdir()
    s4=stages["S4"]
    cursor=0
    for frame in range(1,149,4):
        cursor+=1
        render(base,s4,frames,f"frame{cursor:03}",frame,6)
    subprocess.run([binary("ffmpeg"),"-v","error","-framerate","6","-i",str(frames/"frame%03d.png"),
                    "-c:v","libx264","-preset","fast","-crf","18","-pix_fmt","yuv444p",
                    "-movflags","+faststart","-an",str(output/"preview_fixed_rear.mp4")],check=True)


def build(root,output,quick):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    base=runpy.run_path(str(root/"ENV-001/v001/ENV-001_generate.py"))
    gray=stage_scene(root,"S4",base,True)
    render(base,gray,output,"graybox_s4_fixed",1,8)
    texdir=output/"textures"
    texdir.mkdir()
    for kind in MASKS:
        paint_mask(base,kind,texdir)
    stages = {}
    for stage in STAGES:
        payload=stage_scene(root,stage,base,False)
        stages[stage]=payload
        make_export(stage,payload,output,base)
        render(base,payload,output,f"preview_{stage.lower()}_restoring",50,15)
    render(base,stages["S4"],output,"preview_s4_available_idle",6,15)
    render(base,stages["S4"],output,"preview_s4_release",75,15)
    render(base,stages["S4"],output,"preview_s4_exhausted_reentry",145,15)
    if not quick:
        video(base,stages,output)
    for payload in stages.values():
        scene,cam,*_ = payload
        switch(scene)
        scene.frame_set(50)
        scene.render.filepath="//review.png"
        base["set_preview_workspace"](scene,cam)
    switch(stages["S4"][0])
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{STEM}.blend"),compress=True)
    write_json(output/"rest_cue_interface.json",interface(root))


def glb_content(path):
    data=path.read_bytes()
    magic,version,size,length,typ=struct.unpack_from("<4sIIII",data)
    require((magic,version,size,typ)==(b"glTF",2,len(data),0x4E4F534A),path)
    doc=json.loads(data[20:20+length])
    offset=20+length
    payload_length,typ=struct.unpack_from("<II",data,offset)
    require(typ==0x004E4942 and payload_length+offset+8==len(data),path)
    return doc,data[offset+8:]


def raw_bvh(mesh):
    return BVHTree.FromPolygons([v.co for v in mesh.vertices],[p.vertices[:] for p in mesh.polygons])


def source_coverage(config, water, reed, meshes):
    ground_at=raw_bvh(meshes["Ground"].data)
    water_at=raw_bvh(meshes["Water"].data)
    longest=0
    count=0
    water.data.calc_loop_triangles()
    for tri in water.data.loop_triangles:
        points=[water.data.vertices[i].co for i in tri.vertices]
        for local in [tri.center]+points:
            hit=water_at.ray_cast(Vector((local.x,local.y,2)),Vector((0,0,-1)))[0]
            dry=ground_at.ray_cast(Vector((local.x,local.y,2)),Vector((0,0,-1)))[0]
            # Shared-edge floating-point jitter can push a UV corner just outside the original mesh.
            if hit is None:
                xy=local.lerp(tri.center,.0002)
                hit=water_at.ray_cast(Vector((xy.x,xy.y,2)),Vector((0,0,-1)))[0]
            require(hit is not None,(config["asset"],local,"outside source water"))
            longest=max(longest,abs(local.z-hit.z-WATER_LIFT))
            require(dry is None or dry.z <= local.z+1e-5,(config["asset"],local,"above bank"))
            count+=1
    require(count>40 and longest<1e-5,(config["asset"],count,longest))
    reeds_at=raw_bvh(meshes["Reeds"].data)
    nearest=[]
    for x,y,w,h in config["reed_washes"]:
        anchors=[Vector((x+side*w*.30,y+.08,.035+h*.5)) for side in (-1,0,1)]
        distance=min(reeds_at.find_nearest(anchor)[3] for anchor in anchors)
        require(distance < .52,(config["asset"],anchors,distance,"reed proximity"))
        nearest.append(distance)
    return {"water_samples":count,"max_water_lift_error_BU":longest,"nearest_reed_BU_per_veil":nearest}


def render_projection(scene,cam,stage,water,reed,birds):
    x,y = STAGES[stage]["leader"]
    expected=Vector((x,y-180*math.cos(.48)/SCALE,180*math.sin(.48)/SCALE))
    aim=(Vector((x,y,6/SCALE))-expected).normalized()
    require((cam.location-expected).length<1e-5,(stage,cam.location,expected))
    require((cam.rotation_euler.to_quaternion()@Vector((0,0,-1))-aim).length<1e-5,stage)
    fov=math.degrees(2*math.atan(cam.data.sensor_height/(2*cam.data.lens)))
    require(abs(fov-50)<1e-5 and cam.data.sensor_fit=="VERTICAL",fov)
    reach={}
    for name,obj in (("shallow_water",water),("reed_veil",reed)):
        a=[world_to_camera_view(scene,cam,obj.matrix_world@v.co) for v in obj.data.vertices]
        n=sum(.02<q.x<.98 and .02<q.y<.98 and q.z>0 for q in a)
        require(n>4,(stage,name,n))
        reach[name]=n
    reach["landed_bird_centers"]=sum(
        0<q.x<1 and 0<q.y<1 and q.z>0 for q in
        (world_to_camera_view(scene,cam,bird.location) for bird in birds)
    )
    require(reach["landed_bird_centers"] == 12,(stage,reach))
    return reach


def animation_checks(scene, ctrl, water, reed, birds):
    observed=[]
    shading_drivers = [o.data.materials[0].node_tree.animation_data.drivers[0] for o in (water,reed)]
    for frame, reference in enumerate(script_cue(),1):
        scene.frame_set(frame)
        result=tuple(float(ctrl[k]) for k in ("capacityAvailable","allSettled","displayIntensity","featherIntensity"))
        require(max(abs(a-b) for a,b in zip(result,reference,strict=True))<2e-6,(scene.name,frame,result,reference))
        observed.append(result[2])
        for obj in (water,reed):
            tree=obj.data.materials[0].node_tree
            multiplier=next(n for n in tree.nodes if n.type=="MATH")
            require(abs(multiplier.inputs[1].default_value-result[2])<2e-6,(obj.name,frame,"driver value"))
    require(all(curve.driver.is_valid for curve in shading_drivers),scene.name)
    require(all(a<=b for a,b in zip(observed[15:55],observed[16:56],strict=True)),scene.name)
    require(all(a>=b for a,b in zip(observed[57:88],observed[58:89],strict=True)),scene.name)
    require(all(v==0 for v in observed[111:]),scene.name)
    require(.265 < observed[5] < .275 and observed[49]>.85 and observed[88]<.31,observed[88])
    scene.frame_set(50)
    feather_drives=0
    for name in set(slot.material.name for bird in birds for slot in bird.material_slots if slot.material):
        if ' feather tint | ' not in name:
            continue
        node=next(n for n in bpy.data.materials[name].node_tree.nodes if n.type=="MIX_RGB" and n.blend_type=="MULTIPLY"
                  and n.inputs[0].default_value < .10)
        require(abs(node.inputs[0].default_value-script_cue()[49][3]*FEATHER_STRENGTH)<2e-6,(name,"feather tint"))
        feather_drives+=1
    require(feather_drives>0,scene.name)
    return {"status":"pass","evaluated_frames":len(observed),"available_idle_sample":observed[5],
            "restoring_sample_frame_50":observed[49],"exit_sample_frame_75":observed[74],
            "exit_sample_frame_89":observed[88],"exhausted_reentry_frame_145":observed[144],
            "feather_materials_driven":feather_drives}


def triangles(item):
    data=item.data
    data.calc_loop_triangles()
    uv=data.uv_layers.active.data
    return Counter(tuple(sorted(
        tuple(round(x,4) for x in (*tuple(item.matrix_world@data.vertices[data.loops[l].vertex_index].co),*tuple(uv[l].uv)))
        for l in tri.loops
    )) for tri in data.loop_triangles)


def verify_glb(folder,stage,source_objects):
    path=folder/f"{STEM}_{stage}.glb"
    doc,blob=glb_content(path)
    require(len(doc["scenes"])==1 and len(doc["meshes"])==2 and len(doc["nodes"])==3,path)
    require(doc["nodes"][doc["scenes"][0]["nodes"][0]]["name"]==f"RestCue_{stage}",path)
    require({node["name"] for node in doc["nodes"]}=={
        f"RestCue_{stage}",f"RestCue_{stage}_ShallowLight",f"RestCue_{stage}_ReedHalo"
    },(stage,doc["nodes"]))
    require(all(mat.get("alphaMode")=="BLEND" and "KHR_materials_unlit" in mat.get("extensions",{})
                for mat in doc["materials"]),(path,doc["materials"]))
    expected={sha(folder/"textures"/entry[0]) for entry in MASKS.values()}
    found=set()
    for image in doc["images"]:
        view=doc["bufferViews"][image["bufferView"]]
        i=view.get("byteOffset",0)
        found.add(hashlib.sha256(blob[i:i+view["byteLength"]]).hexdigest())
    require(expected==found,(stage,"embedded source PNG hashes",expected,found))
    src_signature={item.name.split(".")[0]:triangles(item) for item in source_objects}
    scene=bpy.data.scenes.new(f"Independent GLB import {stage}")
    switch(scene)
    result=bpy.ops.import_scene.gltf(filepath=str(path),merge_vertices=False)
    require(result=={"FINISHED"},path)
    bpy.context.view_layer.update()
    mapped={item.name.split(".")[0]:triangles(item) for item in scene.objects if item.type=="MESH"}
    require(mapped==src_signature,(stage,"triangles, axis and UV",set(src_signature),set(mapped)))
    out={name:sum(counter.values()) for name,counter in mapped.items()}
    bpy.data.scenes.remove(scene)
    return {"status":"pass","triangles_by_draw_layer":out,"exact_embedded_png_sha256":sorted(found),
            "alpha_mode":"BLEND","extension":"KHR_materials_unlit"}


def decode(folder):
    src=folder/"preview_fixed_rear.mp4"
    records=json.loads(subprocess.check_output([binary("ffprobe"),"-v","error","-show_streams","-count_frames",
                                               "-of","json",str(src)]))["streams"]
    video=records[0]
    require(len(records)==1 and (video["codec_name"],video["width"],video["height"],int(video["nb_read_frames"]))
            == ("h264",*BASE,37),video)
    subprocess.run([binary("ffmpeg"),"-v","error","-xerror","-i",str(src),"-f","null","-"],check=True)
    return {"status":"pass","codec":video["codec_name"],"resolution":BASE,"decoded_frames":37,
            "duration_seconds":float(video["duration"]),"audio_streams":0}


def load_pixels(path):
    image=bpy.data.images.load(str(path))
    require(tuple(image.size)==BASE,path)
    pixels=np.empty(math.prod(BASE)*4,dtype=np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return pixels.reshape((BASE[1],BASE[0],4))[:,:,:3]


def check_state_pixels(folder):
    exhausted=load_pixels(folder/"preview_s4_exhausted_reentry.png")
    available=load_pixels(folder/"preview_s4_available_idle.png")
    restoring=load_pixels(folder/"preview_s4_restoring.png")
    fade=load_pixels(folder/"preview_s4_release.png")
    fields={}
    for name,image in (("available_idle",available),("restoring",restoring),("release",fade)):
        delta=np.max(np.abs(image-exhausted),axis=2)
        fields[name]=int(np.count_nonzero(delta>8/255))
    require(fields["restoring"]>400 and fields["available_idle"]>20 and
            fields["available_idle"]<fields["release"]<fields["restoring"],fields)
    return {"status":"pass","compared_to_exhausted_reentry":fields,"threshold":"max of channel differences > 8/255"}


def verify(folder,work):
    master=folder/f"{STEM}.blend"
    require(bpy.ops.wm.open_mainfile(filepath=str(master),use_scripts=False)=={"FINISHED"},master)
    require(not list(bpy.data.libraries),"master should contain local stage data")
    reports={}
    for stage,config in STAGES.items():
        scene=bpy.data.scenes[f"RestCue | {stage} actual wetland"]
        switch(scene)
        water,reed=layers_by_name(scene,stage)
        birds=[o for o in scene.objects if o.name.startswith("Review resting goose")]
        ctrl=next(o for o in scene.objects if o.name.startswith(f"RestCue | {stage} review controls"))
        fit=source_coverage(config,water,reed,source_layers(scene,config["module"]))
        screen=render_projection(scene,scene.camera,stage,water,reed,birds)
        anim=animation_checks(scene,ctrl,water,reed,birds)
        export_scene=bpy.data.scenes[f"RestCue | {stage} export at module origin"]
        switch(export_scene)
        roundtrip=verify_glb(folder,stage,layers_by_name(export_scene,stage))
        reports[stage]={"status":"pass","overlay_fit":fit,"fixed_rear_in_frame":screen,
                        "state_response":anim,"glb_roundtrip":roundtrip}
    qa={"asset_id":"FX-012","version":"v001","status":"needs_review","blender":bpy.app.version_string,
        "independent_master_reopen":"pass","verified_from":str(folder),"per_stage":reports,
        "states_pixel_comparison":check_state_pixels(folder),"video":decode(folder),
        "pending":["Owner art review", "USDZ and RealityKit transparency ordering", "App capacity, flock and Zone binding",
                   "iPhone and iPad readability and performance"],
        "app_baseline":"Existing iPhone 18 Pro / iOS 27.2 build and 340 tests from active plan",
        "redline_review":"No UI, scoring, alarms, coins, or capacity change; warm low-saturation recovery rendering only."}
    write_json(work/"qa.json",qa)


def main():
    args=sys.argv[sys.argv.index("--")+1:]
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output",type=Path)
    cli.add_argument("--verify",type=Path)
    cli.add_argument("--source-root",type=Path,default=Path(__file__).resolve().parents[2])
    cli.add_argument("--quick",action="store_true")
    parsed=cli.parse_args(args)
    out=parsed.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    require(not list(out.iterdir()),("Use empty temporary output",out))
    if parsed.verify:
        verify(parsed.verify.resolve(),out)
    else:
        build(parsed.source_root.resolve(),out,parsed.quick)


if __name__=="__main__":
    main()
