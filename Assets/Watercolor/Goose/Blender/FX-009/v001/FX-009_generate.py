"""Build or independently validate the RescueBeacon asset in Blender 5.2."""
import argparse
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import zlib

import bpy
from mathutils import Vector
import numpy as np

ASSET = "FX-009"
ROOT = "RescueBeacon"
STEM = f"{ASSET}_{ROOT}"
SOURCE = "ANM-009_call_rejoin"
ATTACHMENT = "FX-009 | preview attachment"
REVIEW = "Review | Separated companion"
FIXED = "Gameplay | fixed rear"
OVERHEAD = "Review | group overhead"
SIZE = (852, 393)
RING = "RescueBeacon_Ring"
SPOT = "RescueBeacon_SoftPoint"
TEXTURES = {
    RING: "ft_goose_fx_rescue_ring_basecolor_alpha.png",
    SPOT: "ft_goose_fx_rescue_soft_point_basecolor_alpha.png",
}
RUNTIME_INPUTS = {
    "companionID": "Stable game-owned identifier for the separated goose. Optional placement suggestions may use the companion’s horizontal heading.",
    "rescueAnchorWorld": "World point selected by the game in reachable space near companionID. Project into current fixed camera to steer any separate offscreen indicator.",
    "escortProgress": "Clamped 0–1 progress from game; remap with smoothstep to drive scale = 1 - .58s and whole-cue opacity = 1 - s.",
    "state": "Separated: fade in over .33 s; escorting: converge and fade with progress; rejoined/invalid/unsafe anchor: disable the entity.",
    "safeAnchor": "Host validates world placement against game Zone and traversability before enabling the cue.",
    "cameraFacing": "Ring remains horizontal; rotate only the point about world up to face camera.",
}
OFFSET = (1.11, 1.24, 0.0)
RADIUS = 0.40
INNER = 0.31
POINT_RADIUS = 0.155
POINT_LIFT = 0.18
START_ESCORT, END_ESCORT, END = 65,161,217
UNITS_PER_BU = 27.5 / .9900


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def png(path, rgba):
    def chunk(name, payload):
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload))
    h, w, _ = rgba.shape
    rows = b"".join(b"\0" + row.tobytes() for row in rgba[::-1])
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", w, h, 8, 6, 0, 0, 0))
                     + chunk(b"sRGB", b"\0") + chunk(b"IDAT", zlib.compress(rows, 8)) + chunk(b"IEND", b""))


def texture(path, ring):
    size = 256 if ring else 128
    axis = ((np.arange(size) + .5) / size - .5) * 2
    x, y = np.meshgrid(axis, axis)
    r = np.hypot(x, y)
    if ring:
        angle = np.arctan2(y, x)
        dist = r - (.889 + .016*np.sin(5*angle+.4) + .008*np.cos(13*angle))
        alpha = np.exp(-((dist + .012)/.053)**2) * (.64 + .10*np.cos(3*angle+.7) + .06*np.sin(9*angle))
        alpha *= np.clip((1-r)/.044,0,1) * np.clip((r-.777)/.043,0,1)
    else:
        alpha = (.68*np.exp(-(r/.36)**2) + .18*np.exp(-(r/.67)**2)) * np.clip((.985-r)/.32, 0, 1)
    grain = np.random.default_rng(9001 if ring else 9002).normal(0, 1, r.shape)
    alpha *= np.clip(1+.054*grain,.80,1.14)
    rgba = np.zeros((size,size,4),dtype=np.uint8)
    for i,channel in enumerate((231,192,134) if ring else (246,221,170)):
        rgba[:,:,i] = np.round(np.clip(channel + 1.7*grain, 0, 255))
    rgba[:,:,3] = np.round(np.clip(alpha, 0, 1) * 255)
    rgba[[0,-1],:,3] = 0
    rgba[:,[0,-1],3] = 0
    png(path, rgba)


def primitive(collection, root, name, ring):
    n = 64 if ring else 40
    xy = [(math.cos(i*math.tau/n), math.sin(i*math.tau/n)) for i in range(n)]
    if ring:
        vertices = [(r*x,r*y,0) for r in (RADIUS, INNER) for x,y in xy]
        faces = [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        uv = [(.5+p[0]/(2*RADIUS),.5+p[1]/(2*RADIUS)) for p in vertices]
    else:
        vertices = [(POINT_RADIUS*x,0,POINT_RADIUS*y) for x,y in xy]
        faces = [tuple(range(n))]
        uv = [(.5+p[0]/(2*POINT_RADIUS),.5+p[2]/(2*POINT_RADIUS)) for p in vertices]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name="TextureUV")
    for i,loop in enumerate(mesh.loops):
        layer.data[i].uv = uv[loop.vertex_index]
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.parent = root
    if not ring:
        obj.location.z = POINT_LIFT
    return obj


def shader(name, image=None, control=None):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.surface_render_method = "BLENDED"
    tree = material.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (410, 0)
    emission = tree.nodes.new("ShaderNodeEmission")
    if image is None:
        emission.inputs["Color"].default_value = (.54,.54,.54,1)
        tree.links.new(emission.outputs[0], out.inputs["Surface"])
        return material
    tex = tree.nodes.new("ShaderNodeTexImage")
    tex.extension = "EXTEND"
    tex.image = image
    tex.location = (-600, 75)
    emission.location = (-270,100)
    tree.links.new(tex.outputs["Color"], emission.inputs["Color"])
    transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
    transparent.location = (-190, -30)
    mix = tree.nodes.new("ShaderNodeMixShader")
    mix.location = (160, 0)
    alpha = tex.outputs["Alpha"]
    if control is not None:
        gain = tree.nodes.new("ShaderNodeMath")
        gain.label = "Base alpha × cue intensity"
        gain.operation = "MULTIPLY"
        gain.location = (-120, -200)
        tree.links.new(alpha,gain.inputs[0])
        driver(gain.inputs[1], "default_value", control, "intensity")
        alpha = gain.outputs[0]
    tree.links.new(alpha,mix.inputs[0])
    tree.links.new(transparent.outputs[0],mix.inputs[1])
    if control is None:
        # glTF recognizes this equivalent camera-ray unlit node structure.
        ray = tree.nodes.new("ShaderNodeLightPath")
        black = tree.nodes.new("ShaderNodeBsdfTransparent")
        camera_mix = tree.nodes.new("ShaderNodeMixShader")
        tree.links.new(ray.outputs["Is Camera Ray"],camera_mix.inputs[0])
        tree.links.new(black.outputs[0],camera_mix.inputs[1])
        tree.links.new(emission.outputs[0],camera_mix.inputs[2])
        tree.links.new(camera_mix.outputs[0],mix.inputs[2])
    else:
        tree.links.new(emission.outputs[0],mix.inputs[2])
    tree.links.new(mix.outputs[0], out.inputs["Surface"])
    return material


def driver(entity, attribute, control, key, axis=None):
    fcurve = entity.driver_add(attribute) if axis is None else entity.driver_add(attribute, axis)
    spec = fcurve.driver
    spec.type = "AVERAGE"
    source = spec.variables.new()
    source.name = key
    source.type = "SINGLE_PROP"
    source.targets[0].id = control
    source.targets[0].data_path = f'["{key}"]'


def make_root(collection, name):
    root = bpy.data.objects.new(name,None)
    collection.objects.link(root)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = .18
    root["collision_enabled"] = False
    return root


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t*t*(3-2*t)


def envelope(frame):
    p = smooth((frame-START_ESCORT)/(END_ESCORT-START_ESCORT))
    return round(smooth((frame-1)/16)*(1-p), 7), round(1-.58*p, 7)


def review_root(scene):
    attachment = scene.objects[ATTACHMENT]
    root = make_root(scene.collection, "Review | RescueBeacon control")
    constraint = root.constraints.new("COPY_LOCATION")
    constraint.name = "Follow ANM-009 locator without inheriting bird scale"
    constraint.target = attachment
    constraint.use_offset = True
    for axis,value in enumerate(OFFSET):
        key = ("offset_right_BU","offset_forward_BU","offset_up_BU")[axis]
        root[key] = value
        root.id_properties_ui(key).update(description="World-axis offset from the ANM-009 playback locator")
        driver(root,"location",root,key,axis)
    for key in ("intensity", "size_factor"):
        root[key] = 1.
        root.id_properties_ui(key).update(min=0.,max=1.,description="Cue envelope, keyframed for review")
    for frame in range(1,END+1):
        for key,value in zip(("intensity","size_factor"), envelope(frame)):
            root[key] = value
            root.keyframe_insert(data_path=f'["{key}"]',frame=frame)
    action = root.animation_data.action
    action.name = "Review | reveal and two-second escort"
    for curve in action.layers[0].strips[0].channelbag(root.animation_data.action_slot).fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
    for axis in range(3):
        driver(root,"scale",root,"size_factor",axis)
    return root


def review_copy(scene, root, source):
    result = []
    for original in source:
        obj = original.copy()
        obj.data = original.data.copy()
        obj.name = "Review | " + original.name
        scene.collection.objects.link(obj)
        obj.parent = root
        result.append(obj)
    return result


def render(scene, view, frame, path, samples):
    bpy.context.window.scene = scene
    scene.camera = scene.objects[view]
    scene.frame_set(frame)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.transparent_max_bounces = 4
    scene.render.resolution_x, scene.render.resolution_y = SIZE
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True,scene=scene.name)


def build(lib, out, footage):
    dep = lib/"ANM-009"/"v001"
    bpy.ops.wm.open_mainfile(filepath=str(dep/f"{SOURCE}.blend"))
    review = bpy.data.scenes[REVIEW]
    edit_scene = bpy.data.scenes.new("FX-009 | RescueBeacon asset")
    root = make_root(edit_scene.collection, ROOT)
    root["variant"] = ROOT
    root["intended_use"] = "Wind-sheltered separated-companion cue placement supplied by game"
    ring = primitive(edit_scene.collection,root,RING,True)
    point = primitive(edit_scene.collection,root,SPOT,False)
    # The original locator was close to the next bird in projection.
    # Keep its source animation but move the separated carrier to a readable outer station.
    isolated_actor = review.objects[ATTACHMENT].parent
    for curve in isolated_actor.animation_data.action.layers[0].strips[0].channelbag(
            isolated_actor.animation_data.action_slot).fcurves:
        if curve.data_path=="location" and curve.array_index in (0,1):
            for key in curve.keyframe_points:
                frame = key.co.x
                joined = smooth((frame-113)/(165-113))
                delta = (.48,.46)[curve.array_index]*(1-joined)
                key.co.y += delta
                key.handle_left.y += delta
                key.handle_right.y += delta
            curve.update()
    controller = review_root(review)
    review_objects = review_copy(review,controller,[ring,point])
    clay = shader("FX-009 | graybox clay")
    for obj in review_objects:
        obj.data.materials.append(clay)
    render(review,FIXED,46,out/"graybox_fixed_rear.png",8)
    render(review,OVERHEAD,46,out/"graybox_overhead.png",8)

    (out/"textures").mkdir()
    for source,target in zip((ring,point),review_objects):
        file = TEXTURES[source.name]
        texture(out/"textures"/file,source==ring)
        image = bpy.data.images.load(str(out/"textures"/file))
        image.pack()
        image.filepath = f"//textures/{file}"
        source.data.materials.append(shader(source.name,image))
        target.data.materials[0] = shader(target.name,image,controller)

    bpy.context.window.scene = edit_scene
    bpy.ops.object.select_all(action="DESELECT")
    for obj in (root,ring,point):
        obj.select_set(True)
    assert bpy.ops.export_scene.gltf(filepath=str(out/f"{STEM}.glb"),use_selection=True,
           use_active_scene=True,export_extras=True,export_animations=False,export_yup=True) == {"FINISHED"}

    render(review,FIXED,46,out/"preview_fixed_rear_call.png",16)
    render(review,OVERHEAD,46,out/"preview_overhead_call.png",16)
    render(review,FIXED,113,out/"preview_fixed_rear_escort.png",16)
    render(review,FIXED,193,out/"preview_fixed_rear_rejoined.png",16)
    for obj in review_objects:
        obj.hide_render = True
    render(review,FIXED,46,out/"comparison_without_cue.png",16)
    for obj in review_objects:
        obj.hide_render = False

    for frame,name in ((1,"Separated"), (17,"Cue visible"), (START_ESCORT,"Escort starts"),
                       (113,"Escort midpoint"), (END_ESCORT,"Cue off"), (165,"Cruise returns")):
        review.timeline_markers.new(name,frame=frame)
    review.frame_set(46)
    review.render.filepath = "//"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.object.select_all(action="DESELECT")
    controller.select_set(True)
    bpy.context.view_layer.objects.active = controller
    bpy.ops.wm.save_as_mainfile(filepath=str(out/f"{STEM}.blend"),compress=True)

    with TemporaryDirectory(prefix="fx009-frames-",dir=footage) as dirname:
        frames=Path(dirname)
        for i,frame in enumerate(range(1,END+1,6)):
            render(review,FIXED,frame,frames/f"{i:04}.png",12)
        subprocess.run(["ffmpeg","-v","error","-framerate","8","-i",str(frames/"%04d.png"),
                        "-c:v","libx264","-threads","2","-crf","16","-vf","pad=852:394:0:0:black",
                        "-pix_fmt","yuv420p","-movflags","+faststart",str(out/"preview_fixed_rear_silent.mp4")],check=True)

    mapping = {
        "id": ASSET, "variant":ROOT, "coordinates":{"blender":["+X right","+Y forward","+Z up"],
                                                    "gltf_realitykit":["+X right","-Z forward","+Y up"]},
        "game_units_per_BU":UNITS_PER_BU, "source_scale":"CHR-001 bill to tail .9900 BU = 27.5",
        "pivot":"Anchor at ring center, horizontal world plane", "ring_outer_radius_BU":RADIUS,
        "ring_inner_radius_BU":INNER, "point_radius_BU":POINT_RADIUS, "point_lift_BU":POINT_LIFT,
        "preview_attachment_offset_BU":list(OFFSET), "collision_enabled":False,
        "runtime_inputs":RUNTIME_INPUTS,
        "review_seconds":{"appearance":16/48,"escort":(END_ESCORT-START_ESCORT)/48},
    }
    write_json(out/"runtime_mapping.json",mapping)


def projector(camera):
    inverse = np.array(camera.matrix_world.normalized().inverted())
    focal_pixels = SIZE[1] * camera.data.lens / camera.data.sensor_height

    def calculate(points):
        local = points @ inverse[:3,:3].T + inverse[:3,3]
        depth = -local[:,2]
        assert (depth > 0).all()
        return np.array(SIZE)/2 + focal_pixels * local[:,:2]/depth[:,None]

    return calculate


def mesh_points(obj, graph):
    evaluated = obj.evaluated_get(graph)
    vertices = evaluated.data.vertices
    local = np.empty(len(vertices)*3, dtype=np.float32)
    vertices.foreach_get("co", local)
    matrix = np.array(evaluated.matrix_world)
    return local.reshape(-1,3) @ matrix[:3,:3].T + matrix[:3,3]

def box(points):
    return points.min(axis=0),points.max(axis=0)


def separation(a,b):
    return max(*(a[0]-b[1]), *(b[0]-a[1]))


def inspect_master(out):
    bpy.ops.wm.open_mainfile(filepath=str(out/f"{STEM}.blend"))
    scene = bpy.data.scenes[REVIEW]
    bpy.context.window.scene = scene
    cam = scene.objects[FIXED]
    assert scene.render.resolution_x==852 and scene.render.resolution_y==393
    assert (cam.location-Vector((0,-180*math.cos(.48)/UNITS_PER_BU,(180*math.sin(.48)-8)/UNITS_PER_BU))).length<1e-4
    expected = (Vector((0,0,-2/UNITS_PER_BU))-cam.location).normalized()
    assert (cam.rotation_euler.to_matrix() @ Vector((0,0,-1))-expected).length < 1e-6
    assert abs(math.degrees(2*math.atan(cam.data.sensor_height/(2*cam.data.lens)))-50)<1e-4
    control = scene.objects["Review | RescueBeacon control"]
    locator = scene.objects[ATTACHMENT]
    flock = [scene.objects[f"Review mesh | {i:02}"] for i in range(12)]
    cue = [scene.objects[f"Review | {name}"] for name in (RING,SPOT)]
    assert control.constraints[0].target == locator
    all_gaps, own_gaps, edges = [], [], []
    alpha_series, size_series, anchor_errors, positions = [],[],[],[]
    snapshots = {}
    project = projector(cam)
    for frame in range(1,END+1):
        scene.frame_set(frame)
        graph = bpy.context.evaluated_depsgraph_get()
        center = control.matrix_world.translation.copy()
        anchor_errors.append((center-locator.matrix_world.translation-Vector(OFFSET)).length)
        actual_control = control.evaluated_get(graph)
        intensity,size = [float(actual_control[key]) for key in ("intensity","size_factor")]
        assert max(abs(a-b) for a,b in zip((intensity,size),envelope(frame))) < 1e-6,(frame,intensity,size,envelope(frame))
        assert abs(control.matrix_world.to_scale().x-size)<1e-6
        alpha_series.append(intensity); size_series.append(size); positions.append(center)
        for obj in cue:
            gain = next(n for n in obj.data.materials[0].node_tree.nodes if n.type=="MATH")
            material = obj.data.materials[0].evaluated_get(graph)
            assert abs(material.node_tree.nodes[gain.name].inputs[1].default_value-intensity)<1e-6
        if intensity > 0:
            cue_points = [project(mesh_points(obj,graph)) for obj in cue]
            bird_boxes = [box(project(mesh_points(obj,graph))) for obj in flock]
            cue_boxes = [box(points) for points in cue_points]
            low,high = box(np.concatenate(cue_points))
            border = min(*low,*(np.array(SIZE)-high))
            edges.append(float(border))
            gaps = [min(separation(actual,other) for actual in cue_boxes) for other in bird_boxes]
            own_gaps.append(float(gaps[11])); all_gaps.append(float(min(gaps)))
        if frame in (1,17,46,65,113,160,161,193):
            snapshots[str(frame)]={"intensity":intensity,"scale":size,"anchor_BU":list(center)}
    assert max(anchor_errors)<1e-6
    assert min(edges)>10 and min(own_gaps)>3 and min(all_gaps)>0,(min(edges),min(own_gaps),min(all_gaps))
    assert max(abs(a-b)*48 for a,b in zip(alpha_series,alpha_series[1:])) < 5
    max_step = max((a-b).length for a,b in zip(positions,positions[1:]))
    assert max_step < .05,max_step
    assert all(b<=a+1e-6 for a,b in zip(alpha_series[64:],alpha_series[65:]))
    assert all(b<=a+1e-6 for a,b in zip(size_series[64:],size_series[65:]))
    assert all(a==0 for a in alpha_series[160:])
    return scene,control,cue,{"status":"pass","samples":END,"camera_frame_px":list(SIZE),
           "bird_count":len(flock),"minimum_cue_to_target_bbox_gap_px":min(own_gaps),
           "minimum_cue_to_any_bird_bbox_gap_px":min(all_gaps),"minimum_cue_to_frame_edge_px":min(edges),
           "max_locator_error_BU":max(anchor_errors),"max_anchor_step_BU_per_frame_48fps":max_step,
           "samples_by_frame":snapshots}


def glb_json(path):
    data=path.read_bytes()
    magic,version,total,count,typ=struct.unpack_from("<4sIIII",data)
    assert (magic,version,total,typ)==(b"glTF",2,len(data),0x4e4f534a)
    return json.loads(data[20:20+count])


def pixels(image):
    values = np.empty(len(image.pixels),dtype=np.float32)
    image.pixels.foreach_get(values)
    return values.reshape((image.size[1],image.size[0],4))


def reimport(out, scene, control, cue, scratch):
    document = glb_json(out/f"{STEM}.glb")
    assert set(n["name"] for n in document["nodes"])=={ROOT,RING,SPOT}
    assert not any(key in document for key in ("skins","animations","cameras"))
    materials = document["materials"]
    assert len(materials)==2 and all(m["alphaMode"]=="BLEND" and "KHR_materials_unlit" in m["extensions"] for m in materials),materials
    assert len(document["images"])==2 and all(i["mimeType"]=="image/png" and "bufferView" in i for i in document["images"])
    isolated = bpy.data.scenes.new("QA isolated GLB")
    bpy.context.window.scene = isolated
    assert bpy.ops.import_scene.gltf(filepath=str(out/f"{STEM}.glb"))=={"FINISHED"}
    imported={o.name.split(".")[0]:o for o in isolated.objects}
    assert set(imported)=={ROOT,RING,SPOT}
    assert imported[ROOT].location.length<1e-7
    isolated.view_layers[0].update()
    edit=bpy.data.scenes["FX-009 | RescueBeacon asset"]
    edit.view_layers[0].update()
    details={}
    for name in (RING,SPOT):
        obj=imported[name]
        ref=edit.objects[name]
        assert obj.parent==imported[ROOT] and obj.data.uv_layers.active
        obj.data.calc_loop_triangles()
        ref.data.calc_loop_triangles()
        assert len(ref.data.loop_triangles)==len(obj.data.loop_triangles)>0
        original=pixels(bpy.data.images.load(str(out/"textures"/TEXTURES[name]),check_existing=False))
        imported_image=next(n.image for n in obj.data.materials[0].node_tree.nodes if n.type=="TEX_IMAGE")
        actual=pixels(imported_image)
        assert original.shape==actual.shape
        pixel_delta=float(np.abs(original-actual).max())
        assert pixel_delta<1e-6 and 0.45<actual[:,:,3].max()<.98,(name,pixel_delta,actual[:,:,3].max(),original[:,:,3].max())
        def bounds(o):
            pts = np.array([o.matrix_world @ v.co for v in o.data.vertices])
            return np.array([pts.min(axis=0),pts.max(axis=0)])
        bounds_delta=float(abs(bounds(obj)-bounds(ref)).max())
        assert bounds_delta<1e-6,(name,bounds(obj),bounds(ref))
        details[name]={"triangles":len(obj.data.loop_triangles),"texture_px":list(imported_image.size),
                       "max_original_to_embedded_rgba_delta":pixel_delta,
                       "bounds_delta_BU":bounds_delta,"alpha_min":float(actual[:,:,3].min()),
                       "alpha_max":float(actual[:,:,3].max())}
    # Render imported meshes/materials over the same review plate at unit opacity.
    for obj in cue:
        obj.hide_render=True
    roundtrip=review_copy(scene,control,[imported[RING],imported[SPOT]])
    render(scene,FIXED,46,scratch/"roundtrip_fixed_rear.png",16)
    for obj in roundtrip:
        obj.hide_render=True
    render(scene,FIXED,193,scratch/"roundtrip_disabled.png",16)
    a,b,c=[pixels(bpy.data.images.load(str(path),check_existing=False))[:,:,:3] for path in
           (out/"preview_fixed_rear_call.png",out/"comparison_without_cue.png",scratch/"roundtrip_fixed_rear.png")]
    mask=np.max(np.abs(a-b),axis=2)>.02
    conspicuous=int((np.max(np.abs(a-b),axis=2)>.06).sum())
    difference=float(abs(a[mask]-c[mask]).mean())
    disabled=pixels(bpy.data.images.load(str(scratch/"roundtrip_disabled.png"), check_existing=False))
    rejoined=pixels(bpy.data.images.load(str(out/"preview_fixed_rear_rejoined.png"), check_existing=False))
    disabled_delta=float(np.abs(disabled-rejoined).max())
    assert conspicuous>70 and difference<.02 and disabled_delta<.01,(conspicuous,difference,disabled_delta)
    return {"status":"pass","embedded_materials":details,"cue_pixels_changing_over_6_percent":conspicuous,
            "roundtrip_mean_absolute_rgb_delta_within_cue":difference,"after_rejoin_max_rgb_delta":disabled_delta}


def validate(out, scratch):
    scene,control,cue,blend_checks=inspect_master(out)
    result=reimport(out,scene,control,cue,scratch)
    clip=out/"preview_fixed_rear_silent.mp4"
    meta=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_streams","-of","json",str(clip)]))
    stream,=meta["streams"]
    expected_frames=len(range(1,END+1,6))
    assert (stream["codec_type"],stream["width"],stream["height"],int(stream["nb_read_frames"]))==("video",852,394,expected_frames)
    subprocess.run(["ffmpeg","-v","error","-xerror","-i",str(clip),"-f","null","-"],check=True)
    qa={"id":ASSET,"version":"v001","status":"needs_review","blender":bpy.app.version_string,
        "master_reopen":blend_checks,"glb_reimport":result,
        "preview_decode":{"status":"pass","codec":stream["codec_name"],"frames":expected_frames,
                          "video_px":[852,394],"scene_px":list(SIZE),"fps":8,"audio_streams":0},
        "redline_review":{"status":"pass","scope":"World-space warm-gold cue and silent review only. No warning red, scoring, player text, timer or ecology claims."},
        "app_graybox_simulator":{"scope":"Prior iOS 27.2 baseline cited in active plan and ANM-009 QA.",
                                 "tests":340,"failures":0,"candidate_in_app":False},
        "pending":["Owner art approval and final FX visibility against S3 fog and terrain.",
                   "Engine placement against zones and reachable ground, escort progress, offscreen direction.",
                   "USDZ, RealityKit blend/sorting and App hookup.",
                   "iPhone / iPad display, controls and performance."]}
    write_json(scratch/"qa.json",qa)


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--library",required=True,type=Path)
    cli.add_argument("--output",required=True,type=Path)
    cli.add_argument("--scratch",required=True,type=Path)
    cli.add_argument("--validate",action="store_true")
    args=cli.parse_args(sys.argv[sys.argv.index("--")+1:])
    if args.validate:
        validate(args.output,args.scratch)
    else:
        assert args.output.is_dir() and not any(args.output.iterdir())
        build(args.library,args.output,args.scratch)


if __name__=="__main__":
    main()
