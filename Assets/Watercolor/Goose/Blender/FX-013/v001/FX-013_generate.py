"""Build FeatherMotes and independently verify the final candidates."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zlib

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np


HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
ASSET = "FX-013"
BLEND = "FX-013_FeatherMotes.blend"
GLB = "FX-013_FeatherMotes.glb"
VIDEO = "preview_fixed_rear.mp4"
REVIEW = "FX-013 | S6 landing and feather drift"
ORIGINAL = "ENV-017 | S6 landing and leader hold"
CAMERA = "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift"
ENV = "ENV-017/v001"
ANM = "ANM-007/v001"
ENV_MASTER = "ENV-017_landing_basin.blend"
ANM_MASTER = "ANM-007_landing.blend"
BU = .9900 / 27.5
SOURCE_SIZE = (852, 393)
SOURCE_FPS = 48
VIDEO_STEP = 4
VIDEO_FRAMES = tuple(range(4, 245, VIDEO_STEP))
KEY = 113
CONTROLS = "FeatherMotes | review controls"
FX_GROUP = "FX-013 | Review only particles"
EXPORT_SCENE = "FX-013 | Reusable GLB source"
SPECS = {
    "FeatherMotes_Feather": {"size": (96, 192), "card": (.125, .40), "alpha": .47,
                             "tex": "textures/ft_goose_fx_feather_motes_feather_rgba.png"},
    "FeatherMotes_Mote": {"size": (96, 96), "card": (.135, .135), "alpha": .42,
                          "tex": "textures/ft_goose_fx_feather_motes_mote_rgba.png"},
}
# Kind, X, Y, initial Z, start delay, base fall speed, and initial roll.
PARTICLES = (
    ("Feather", -3.74, -.36, 1.10, .34, .34, -.35),
    ("Feather",  3.21, -.36, .92, .39, .30, .47),
    ("Feather", -3.86,  1.34, 1.32, .53, .37, .10),
    ("Feather",  3.68,  2.28, 1.22, .70, .35, -.24),
    ("Mote", -3.64, -.18, .60, .23, .24, .0),
    ("Mote",  3.59, .01, .77, .34, .25, .0),
    ("Mote", -3.80,  .64, 1.19, .32, .25, .0),
    ("Mote",  3.61,  1.16, 1.28, .22, .21, .0),
    ("Mote", -3.54,  2.08, 1.24, .59, .24, .0),
    ("Mote",  3.20,  2.76, .77, .67, .24, .0),
    ("Mote", -4.22,  2.89, .91, .48, .25, .0),
    ("Mote",  4.04,  3.93, 1.17, .63, .22, .0),
)


def require(condition, detail):
    if not condition:
        raise ValueError(str(detail))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sources(library):
    dependencies = {}
    for asset, filenames in [(ENV, (ENV_MASTER, "ENV-017_LandingBasin.glb")),
                             (ANM, (ANM_MASTER, "ANM-007_landing.glb"))]:
        path = library / asset
        index = load(path / "asset_manifest.json")
        qa = load(path / "qa.json")
        hashes = index.get("files", index.get("files_sha256"))
        files = {}
        for filename in filenames:
            actual = digest(path / filename)
            require(actual == hashes[filename], filename)
            files[filename] = actual
        dependencies[asset] = {"status": qa["status"], "files": files}
    env_qa = load(library / ENV / "qa.json")
    anm_manifest = load(library / ANM / "asset_manifest.json")
    require(anm_manifest["clips"]["Land_Mudflat"]["frames"] == [1.0, 81.0]
            and anm_manifest["clips"]["Land_Mudflat"]["fps"] == SOURCE_FPS, "ANM-007")
    root = library.parents[3]
    camera_source = (root / CAMERA).read_text()
    require("distance: 180, pitch: 0.48, fieldOfViewDegrees: 50" in camera_source and
            "Float(6 + lift)" in camera_source, CAMERA)
    return dependencies, env_qa["landing_48fps_source"]["contact_delay_frames"], digest(root / CAMERA)


def pixels(image):
    data = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(data)
    return data.reshape(image.size[1], image.size[0], 4)


def write_rgba(path, image):
    def chunk(kind, value):
        return (struct.pack(">I", len(value)) + kind + value
                + struct.pack(">I", zlib.crc32(kind + value)))
    rows = b"".join(b"\0" + row.tobytes() for row in image[::-1])
    h, w, _ = image.shape
    path.write_bytes(b"\x89PNG\r\n\x1a\n" +
                     chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
                     chunk(b"sRGB", b"\0") + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def smooth(a, b, n):
    t = np.clip((n - a) / (b - a), 0, 1)
    return t*t*(3-2*t)


def paint_texture(folder, name, spec):
    w, h = spec["size"]
    u = (np.arange(w)[None, :] + .5) / w
    v = (np.arange(h)[:, None] + .5) / h
    rgba = np.empty((h, w, 4), dtype=np.uint8)
    if name.endswith("_Feather"):
        # One curved rachis, asymmetric vanes, and small, soft interruptions along the barbs.
        axial = .42 + .13*v + .076*np.sin(math.pi*v)
        t = np.clip((v-.15)/.82, 0, 1)
        edge = .30*np.sin(math.pi*t)**.83*(1-.35*t)
        proportion = np.where(u < axial, .94, .73)
        ratio = abs(u-axial)/np.maximum(.001, edge*proportion)
        ripples = .045*np.sin(83*v + 15*u) + .025*np.sin(173*v - 31*u)
        vein = np.exp(-((u-axial)/.021)**2)*smooth(.04,.16,v)*(1-smooth(.88,.98,v))
        vanes = (1-smooth(.66,.98,ratio+ripples))*smooth(.12,.18,v)*(1-smooth(.91,.98,v))
        grain = .96 + .10*np.sin(63*u+177*v)*np.sin(95*u-41*v)
        alpha = np.clip(.85*vanes*grain+.22*vein, 0, 1)
        col = (242, 230, 194)
        variation = 11*vein + 4*np.sin(v*18 + u*6)*vanes
    else:
        dist = np.hypot(u-.5, v-.5)
        alpha = .58*np.exp(-(dist/.18)**2) + .42*np.exp(-(dist/.085)**2)
        alpha *= 1 - smooth(.31,.48,dist)
        col = (251, 228, 160)
        variation = 9*np.exp(-(dist/.1)**2)
    rgba[:, :, :3] = np.clip(np.asarray(col) + variation[:, :, None], 0, 255)
    rgba[:, :, 3] = np.rint(255 * spec["alpha"] * alpha)
    rgba[:, (0, -1), 3] = 0
    rgba[(0, -1), :, 3] = 0
    path = folder / spec["tex"]
    write_rgba(path, rgba)
    image = bpy.data.images.load(str(path), check_existing=False)
    image.alpha_mode = "STRAIGHT"
    image.pack()
    image.filepath = "//" + spec["tex"]
    return image


def group(scene, name):
    out = bpy.data.collections.new(name)
    scene.collection.children.link(out)
    return out


def object_in(collection, name, data=None):
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    return obj


def shader(name, image=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_backface_culling = False
    mat.use_transparent_shadow = False
    mat.surface_render_method = "BLENDED" if image else "DITHERED"
    nodes = mat.node_tree.nodes
    nodes.clear()
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (320, 20)
    mat.node_tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 1
    bsdf.inputs["Specular IOR Level"].default_value = 0
    bsdf.inputs["Emission Strength"].default_value = 1
    if not image:
        bsdf.inputs["Base Color"].default_value = (.72,.74,.75,1)
        bsdf.inputs["Emission Color"].default_value = (.42,.44,.45,1)
        return mat
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.extension = "EXTEND"
    tex.location = (-320, 0)
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    mat.node_tree.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    return mat


def make_card(collection, name, spec, material):
    w, h = spec["card"]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-w/2,-h/2,0),(w/2,-h/2,0),(w/2,h/2,0),(-w/2,h/2,0)],
                     [], [(0,1,2), (0,2,3)])
    mesh.update()
    uv = mesh.uv_layers.new(name="CardUV")
    points = [(0,0),(1,0),(1,1),(0,1)]
    for loop in mesh.loops:
        uv.data[loop.index].uv = points[loop.vertex_index]
    mesh.materials.append(material)
    obj = object_in(collection, name, mesh)
    obj["card_BU"] = [w,h]
    obj.asset_mark()
    return obj


def prop(obj, name, value, low, high, desc):
    obj[name] = value
    obj.id_properties_ui(name).update(min=low, max=high, description=desc)


def drive(item, prop_path, expression, variables, index=None):
    curve = item.driver_add(prop_path) if index is None else item.driver_add(prop_path, index)
    d = curve.driver
    d.type = "SCRIPTED"
    d.expression = expression
    for name, obj, path in variables:
        inp = d.variables.new()
        inp.name = name
        inp.type = "SINGLE_PROP"
        inp.targets[0].id = obj
        inp.targets[0].data_path = path


def control_var(name, obj, prop_key=None):
    return name, obj, '["' + (prop_key or name) + '"]'


def alpha_override(prototype, ctrl, slot, phase):
    mat = prototype.copy()
    mat.name = "Review only | tint " + str(slot)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    tex = next(n for n in nodes if n.type == "TEX_IMAGE")
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    amp = nodes.new("ShaderNodeMath")
    amp.operation = "MULTIPLY"
    amp.location = (-110,-118)
    links.new(tex.outputs["Alpha"], amp.inputs[0])
    links.new(amp.outputs[0], bsdf.inputs["Alpha"])
    life = 2.28 if slot <= 4 else 2.62
    t = f"((frame-start)/48-{phase})"
    drive(amp.inputs[1], "default_value",
          f"enabled*intensity*min(1,max(0,{t}/.43))*min(1,max(0,({life}-{t})/.90))",
          [control_var("enabled", ctrl), control_var("intensity", ctrl),
           control_var("start", ctrl, "allLandingStartFrame")])
    return mat


def make_instances(collection, camera, ctrl, prototypes, gray):
    controls = [control_var("start", ctrl, "allLandingStartFrame"),
                control_var("wind", ctrl, "sideDriftBUPerSecond"),
                control_var("fall", ctrl, "fallSpeedMultiplier")]
    instances = []
    for i, (kind,x,y,z,delay,speed,roll) in enumerate(PARTICLES, 1):
        name = "FeatherMotes_" + kind
        parent = object_in(collection, f"Air path {i:02}")
        parent.empty_display_size = .015
        orientation = parent.constraints.new("COPY_ROTATION")
        orientation.target = camera
        obj = object_in(collection, f"FeatherMotes review {i:02}", prototypes[name].data)
        obj.parent = parent
        obj["variant"] = name
        obj["spawn_delay_s"] = delay
        obj["review_speed_BU_s"] = speed
        life = 2.28 if kind == "Feather" else 2.62
        age = f"((frame-start)/48-{delay})"
        for hidden in ("hide_render", "hide_viewport"):
            drive(obj, hidden, f"enabled < .5 or {age} <= 0 or {age} >= {life}",
                  [control_var("enabled", ctrl), control_var("start", ctrl, "allLandingStartFrame")])
        obj.material_slots[0].link = "OBJECT"
        obj.material_slots[0].material = gray or alpha_override(prototypes[name].data.materials[0],
                                                              ctrl, i, delay)
        t = f"max(0,(frame-start)/48-{delay})"
        drive(parent, "location", f"{x}+wind*{t}+.09*sin({i} + {t}*1.42)", controls, 0)
        drive(parent, "location", f"{y}+.03*{t}+.055*sin({i}+{t}*1.1)", controls, 1)
        drive(parent, "location", f"max(.13,{z}-{speed}*fall*{t})", controls, 2)
        if kind == "Feather":
            drive(obj, "rotation_euler", f"{roll}+.42*sin({i}+{t}*1.30)", controls, 2)
        instances.append(obj)
    return instances


def review_scene(library, expected_delays):
    bpy.ops.wm.open_mainfile(filepath=str(library / ENV / ENV_MASTER))
    scene = bpy.data.scenes[ORIGINAL]
    bpy.context.window.scene = scene
    bpy.context.preferences.filepaths.save_version = 0
    scene.name = REVIEW
    scene.frame_end = 244
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 24
    scene.render.resolution_percentage = 100
    scene.render.fps = SOURCE_FPS
    leader = next(obj for obj in scene.objects if obj.name.startswith("Landing carrier 01"))
    rigs = sorted((obj for obj in scene.objects if obj.name.startswith("Landing rig ")),
                  key=lambda obj: obj.name)
    starts = tuple(int(obj.animation_data.nla_tracks[0].strips[0].frame_start) for obj in rigs)
    require(starts == tuple(1 + delay for delay in expected_delays), starts)
    require(all(obj.animation_data.nla_tracks[0].strips[0].action.name.startswith("Land_Mudflat")
                for obj in rigs), "ANM-007 action mismatch")
    camera = scene.camera
    for index, expression in enumerate((
            "position",
            f"position-{180 * BU * math.cos(.48)}",
            f"position+{180 * BU * math.sin(.48) - .288}")):
        drive(camera, "location", expression, [("position", leader, f"location[{index}]")], index)
    eye = Vector((0, -180 * BU * math.cos(.48), 180 * BU * math.sin(.48)))
    camera.rotation_euler = (Vector((0,0,6*BU)) - eye).to_track_quat("-Z","Y").to_euler()
    camera.data.sensor_fit = "VERTICAL"
    camera.data.lens = camera.data.sensor_height * .5 / math.tan(math.radians(25))
    top = next(obj for obj in scene.objects if obj.type == "CAMERA" and obj != camera)
    top.location = (0, .7, 17)
    top.rotation_euler = (0, 0, 0)
    top.data.ortho_scale = 10.8
    gui = group(scene, "FX-013 | Editable review settings")
    ctrl = object_in(gui, CONTROLS)
    prop(ctrl, "enabled", 1, 0, 1, "Set to zero to disable visual-only effects.")
    prop(ctrl, "intensity", 1., 0, 1, "Multiply the per-particle straight alpha.")
    prop(ctrl, "allLandingStartFrame", max(starts), 1, 244, "Review starts only after all 12 landing clips begin.")
    prop(ctrl, "sideDriftBUPerSecond", .13, -.5, .5, "Horizontal settling drift.")
    prop(ctrl, "fallSpeedMultiplier", 1., .4, 1.4, "Visual fall rate multiplier.")
    scene.timeline_markers.new("Last participant begins landing | FX armed", frame=max(starts))
    return scene, camera, top, ctrl, starts


def render(scene, camera, path, size=SOURCE_SIZE):
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.filepath = str(path)
    bpy.context.view_layer.update()
    require(bpy.ops.render.render(write_still=True) == {"FINISHED"}, path)


def rgb_diff(first, second):
    def read(path):
        img = bpy.data.images.load(str(path), check_existing=False)
        rgb = pixels(img)[:, :, :3] * 255
        bpy.data.images.remove(img)
        return rgb
    diff = np.max(abs(read(first) - read(second)), axis=2)
    return {"mean_max_channel_delta_rgb8": float(diff.mean()),
            "max_channel_delta_rgb8": float(diff.max()),
            "pixels_changed_3_rgb8": int(np.count_nonzero(diff >= 3))}


def video_probe(path):
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True)
    report = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames",
        "-show_entries", "stream=codec_name,codec_type,width,height,nb_read_frames,duration",
        "-of", "json", str(path)]))["streams"]
    require(len(report) == 1, report)
    stream = report[0]
    require(stream["codec_name"] == "h264" and stream["codec_type"] == "video" and
            (stream["width"],stream["height"]) == (852, 394) and
            int(stream["nb_read_frames"]) == len(VIDEO_FRAMES), stream)
    return {"status": "pass", **stream, "audio_streams": 0, "source_size": SOURCE_SIZE}


def make_video(scene, cam, out):
    folder = out / "_frames"
    folder.mkdir()
    scene.eevee.taa_render_samples = 12
    for i, frame in enumerate(VIDEO_FRAMES):
        scene.frame_set(frame)
        render(scene, cam, folder / f"{i:03}.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(SOURCE_FPS // VIDEO_STEP),
        "-i", str(folder / "%03d.png"), "-vf", "pad=852:394:0:0", "-c:v", "libx264",
        "-crf", "17", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(out / VIDEO)],
        check=True)
    shutil.rmtree(folder)
    return video_probe(out / VIDEO)


def saved_instances(scene):
    return sorted((obj for obj in scene.objects if obj.name.startswith("FeatherMotes review ")),
                  key=lambda obj: obj.name)


def visibility(obj, depsgraph):
    material = obj.material_slots[0].material
    material = material.evaluated_get(depsgraph)
    mod = next(n for n in material.node_tree.nodes if n.type == "MATH")
    return mod.inputs[1].default_value


def boxes(scene, cam, obj, evaluated):
    world = evaluated.matrix_world
    screen = [world_to_camera_view(scene, cam, world @ Vector(p)) for p in evaluated.bound_box]
    require(min(p.z for p in screen) > 0, obj.name)
    return (min(p.x for p in screen)*SOURCE_SIZE[0], max(p.x for p in screen)*SOURCE_SIZE[0],
            min(p.y for p in screen)*SOURCE_SIZE[1], max(p.y for p in screen)*SOURCE_SIZE[1])


def playback_evidence(scene, cam, ctrl, instances, starts):
    birds = [obj for obj in scene.objects if obj.name.startswith("Landing goose ")]
    require(len(birds) == len(instances) == 12, (len(birds), len(instances)))
    frame_samples = list(range(1, 245))
    seen = {obj.name: [] for obj in instances}
    max_particles, min_gap, min_screen_margin = 0, math.inf, math.inf
    worst_camera_equation = 0.
    details = {}
    leader = next(obj for obj in scene.objects if obj.name.startswith("Landing carrier 01"))
    for frame in frame_samples:
        scene.frame_set(frame)
        deps = bpy.context.evaluated_depsgraph_get()
        camera_eval = cam.evaluated_get(deps)
        leader_location = leader.evaluated_get(deps).matrix_world.translation
        expected_eye = leader_location + Vector((0, -180*BU*math.cos(.48),
                                                  180*BU*math.sin(.48)-.288))
        error = (camera_eval.matrix_world.translation - expected_eye).length
        worst_camera_equation = max(worst_camera_equation, error)
        active = [obj for obj in instances if visibility(obj,deps) > .001]
        max_particles = max(max_particles, len(active))
        if frame <= max(starts):
            require(not active, (frame, "early particles", active))
        if not active:
            continue
        bird_bounds = [boxes(scene, cam, obj, obj.evaluated_get(deps)) for obj in birds]
        for obj in active:
            evaluated = obj.evaluated_get(deps)
            z = evaluated.matrix_world.translation.z
            seen[obj.name].append((frame,z))
            x0,x1,y0,y1 = boxes(scene, cam, obj, evaluated)
            margin = min(x0, SOURCE_SIZE[0]-x1, y0,SOURCE_SIZE[1]-y1)
            min_screen_margin = min(min_screen_margin, margin)
            gap = min(max(max(box[0]-x1,x0-box[1]), max(box[2]-y1,y0-box[3]))
                      for box in bird_bounds)
            min_gap = min(min_gap, gap)
            if obj.name not in details or min(gap,margin) < min(details[obj.name][1:]):
                details[obj.name] = (frame, gap, margin)
    require(worst_camera_equation < 1e-5 and abs(cam.data.angle_y - math.radians(50)) < 1e-6,
            worst_camera_equation)
    require(min_gap > 0 and min_screen_margin > 0, (min_gap, min_screen_margin, details))
    require(all(series for series in seen.values()), seen.keys())
    measured = {}
    for name, pos in seen.items():
        require(pos[0][1] - pos[-1][1] > .30 and
                max(b[1]-a[1] for a,b in zip(pos,pos[1:])) < 1e-6, (name,pos[0],pos[-1]))
        measured[name] = {"first_visible": pos[0][0], "last_visible": pos[-1][0],
                          "fall_BU": pos[0][1]-pos[-1][1]}
    require(max(p["last_visible"] for p in measured.values()) < 244, measured)
    ctrl["enabled"] = 0
    ctrl.update_tag()
    disabled_samples = [max(starts)+20, KEY, 136, 168]
    before = []
    for frame in disabled_samples:
        scene.frame_set(frame)
        deps = bpy.context.evaluated_depsgraph_get()
        require(all(visibility(obj,deps) == 0 for obj in instances), frame)
        before.append([tuple(obj.evaluated_get(deps).matrix_world.translation) for obj in birds])
    ctrl["enabled"] = 1
    ctrl.update_tag()
    for frame, state in zip(disabled_samples,before):
        scene.frame_set(frame)
        deps = bpy.context.evaluated_depsgraph_get()
        require(state == [tuple(obj.evaluated_get(deps).matrix_world.translation) for obj in birds],
                (frame, "landing carriers depend on visual enable"))
    return {"status":"pass","source_frames_checked":len(frame_samples),
            "source_landing_starts_48fps":starts,"all_started_frame":max(starts),
            "measured_trajectories":measured,"peak_nonzero_alpha_instances":max_particles,
            "minimum_particle_to_bird_bbox_gap_px":min_gap,"minimum_particle_frame_margin_px":min_screen_margin,
            "max_fixed_camera_equation_error_BU":worst_camera_equation,"switch_off_samples":disabled_samples,
            "sampled_landing_positions_equal_with_switch_off":True}


def activate(scene):
    bpy.context.window.scene = scene
    bpy.context.view_layer.update()


def build(folder, library, quick):
    source_files, delays, camera_sha = sources(library)
    scene, cam, top, ctrl, starts = review_scene(library, delays)
    prototypes = {}
    export_scene = bpy.data.scenes.new(EXPORT_SCENE)
    source_group = group(export_scene, "Original editable card meshes")
    root = object_in(source_group, "FeatherMotes")
    root["asset_role"] = "local visual cards, instantiated by engine"
    root["blender_normal"] = "+Z"
    root["engine_normal"] = "+Y"
    gray = shader("Graybox | camera facing silhouettes")
    for name,spec in SPECS.items():
        prototypes[name] = make_card(source_group, name, spec, gray)
        prototypes[name].parent = root
    assets = group(scene, FX_GROUP)
    instances = make_instances(assets, cam, ctrl, prototypes, gray)
    scene.frame_set(KEY)
    render(scene,cam,folder/"graybox_fixed_rear.png")
    render(scene,top,folder/"graybox_top.png",(920,920))
    (folder/"textures").mkdir()
    for name,spec in SPECS.items():
        texture = paint_texture(folder,name,spec)
        material = shader(name+" | straight alpha",texture)
        material.asset_mark()
        prototypes[name].data.materials[0]=material
    for i,(obj,row) in enumerate(zip(instances,PARTICLES),1):
        obj.material_slots[0].material = alpha_override(prototypes[obj["variant"]].data.materials[0],
                                                        ctrl,i,row[4])
    activate(export_scene)
    require(bpy.ops.export_scene.gltf(filepath=str(folder/GLB), export_yup=True,
        export_format="GLB", export_extras=True, use_active_scene=True,
        export_animations=False, export_skins=False) == {"FINISHED"}, GLB)
    activate(scene)
    timing = playback_evidence(scene, cam, ctrl, instances, starts)
    for frame,label in ((max(starts),"pre"),(KEY,"peak"),(158,"settling"),(244,"clear")):
        scene.frame_set(frame)
        render(scene,cam,folder/f"preview_fixed_rear_{label}.png")
    scene.frame_set(KEY)
    render(scene,top,folder/"preview_top.png",(920,920))
    ctrl["enabled"] = 0
    ctrl.update_tag()
    scene.frame_set(KEY)
    render(scene,cam,folder/"preview_disabled.png")
    assets.hide_render = True
    render(scene,cam,folder/"comparison_no_instances.png")
    off = rgb_diff(folder/"preview_disabled.png",folder/"comparison_no_instances.png")
    on = rgb_diff(folder/"preview_fixed_rear_peak.png",folder/"preview_disabled.png")
    require(off["max_channel_delta_rgb8"] < .1 and on["pixels_changed_3_rgb8"] > 110 and
            on["max_channel_delta_rgb8"] > 10, (off,on))
    ctrl["enabled"] = 1
    ctrl.update_tag()
    assets.hide_render = False
    scene.frame_set(KEY)
    scene.render.filepath = "//"
    scene.camera = cam
    bpy.ops.object.select_all(action="DESELECT")
    ctrl.select_set(True)
    bpy.context.view_layer.objects.active = ctrl
    bpy.ops.file.pack_all()
    require(bpy.ops.wm.save_as_mainfile(filepath=str(folder/BLEND),compress=True)
            == {"FINISHED"}, BLEND)
    video = {"status":"not_run"} if quick else make_video(scene,cam,folder)
    dump(folder/"qa.json",{
      "id": ASSET, "version":"v001","status":"needs_review","playback_evidence":timing,
      "image_comparisons":{"enabled_vs_disabled":on,"disabled_vs_instances_removed":off},
      "video":video,"pending":["负责人审阅夕岸的透光与节奏","USDZ 与 RealityKit / App 接入",
      "引擎落脚会话、重试、偏好开关和正式 Zone","iPhone / iPad 真机"]})
    dump(folder/"asset_manifest.json",{
      "id":ASSET,"version":"v001","status":"needs_review","variant":"FeatherMotes","priority":"P2","level":"S6",
      "source_specification_pages":[16,17],"blender":bpy.app.version_string,
      "dependencies":source_files,"camera_source": {CAMERA:camera_sha},"source_size":SOURCE_SIZE,
      "camera":{"distance_game_units":180,"pitch_rad":.48,"vertical_fov_deg":50,
                "target_height_game_units":6,"source_scale_BU_per_game_unit":BU},
      "art_origin":"Production-original procedural card silhouettes, built for this workspace.",
      "rights":"Project original FX; review scene reuses project-owned ENV-017 and ANM-007 candidates.",
      "export":{"file":GLB,"transform":"Blender (x,y,z) -> GLB (x,z,-y)",
                "includes":"FeatherMotes root and two centered static local cards, no terrain, animation or camera",
                "primitives":{name:{**spec,"triangles":2,"alphaMode":"BLEND","doubleSided":True}
                              for name,spec in SPECS.items()}},
      "runtime_inputs":{
        "landingSessionID":"Stable ID per landing attempt. A new session clears effect state.",
        "expectedParticipantIDs":"Non-empty frozen participant set for one attempt (12 in review).",
        "landingStartedParticipantIDs":"Animation entry events; once expected participants all started, emit one batch.",
        "landingAnchorWorld":"World pose or basin center from game. Rotate/translate the sparse emit locations around it.",
        "elapsedSinceAllStartedSeconds":"Monotonic controller time; late opt-in may skip effect or evaluate only remaining tails.",
        "enabled":"False stops spawning and immediately hides existing cards. Skip effect allocation while false.",
        "intensity":"0–1, multiplicative straight alpha. Default 1 within texture alpha limits.",
        "driftVector":"Optional world-horizontal visual drift; sample .13 BU/s side motion.",
        "fallSpeedMultiplier":".4–1.4 in review; scale base .21–.37 BU/s, fade before any ground interaction.",
        "cameraOrientation":"Optional billboard orientation. GLB local +Y is card normal, local -Z is card up.",
        "behavior":"One-shot presentation cue. Does not feed any collision, movement, completion or save state.",
        "preview_counts":{"Feather":4,"Mote":8},"preview_duration_s":"3.32 maximum after last start",
      }})
    shutil.copy2(__file__,folder/Path(__file__).name)


def parse_glb(path):
    data=path.read_bytes()
    magic,ver,length,json_size,json_format=struct.unpack_from("<5I",data)
    require((magic,ver,length,json_format)==(0x46546c67,2,len(data),0x4e4f534a),path)
    bin_size,bin_type=struct.unpack_from("<2I",data,20+json_size)
    require(bin_type==0x004e4942 and len(data)==28+json_size+bin_size,path)
    return json.loads(data[20:20+json_size]),data[28+json_size:]


def verify_card(original, imported, name, spec):
    def coords(obj):
        return sorted(tuple(round(float(n),6) for n in v.co) for v in obj.data.vertices)
    require(coords(original)==coords(imported),name)
    require(tuple(imported.scale)==(1,1,1) and tuple(imported.location)==(0,0,0),name)
    mesh=imported.data
    mesh.calc_loop_triangles()
    require(len(mesh.loop_triangles)==2 and all(t.area>1e-6 and t.normal.z>.99
            for t in mesh.loop_triangles),name)
    actual=sorted(set(tuple(v.uv) for v in mesh.uv_layers.active.data))
    require(actual==[(0,0),(0,1),(1,0),(1,1)],(name,actual))
    images={n.image for n in mesh.materials[0].node_tree.nodes if n.type=="TEX_IMAGE"}
    require(len(images)==1 and tuple(next(iter(images)).size)==tuple(spec["size"]),name)
    alpha=pixels(next(iter(images)))[:,:,3]
    require(.20 < alpha.max() <= spec["alpha"]+1/255 and np.all(alpha[[0,-1],:]==0)
            and np.all(alpha[:,[0,-1]]==0), (name,alpha.max()))
    return {"status":"pass","triangles":len(mesh.loop_triangles),"peak_alpha":float(alpha.max()),
            "uv_corners":actual,"all_texture_edges_zero":True}


def verify(folder, delivery, library):
    _, deltas, _ = sources(library)
    bpy.ops.wm.open_mainfile(filepath=str(delivery/BLEND))
    scene=bpy.data.scenes[REVIEW]
    activate(scene)
    ctrl=scene.objects[CONTROLS]
    cam=scene.camera
    instances=saved_instances(scene)
    timing=playback_evidence(scene,cam,ctrl,instances,[d+1 for d in deltas])
    scene.frame_set(KEY)
    render(scene,cam,folder/"reopened_fixed_rear.png")
    native=rgb_diff(folder/"reopened_fixed_rear.png",delivery/"preview_fixed_rear_peak.png")
    require(native["mean_max_channel_delta_rgb8"] < .3,native)
    doc, binary=parse_glb(delivery/GLB)
    require(len(doc["nodes"])==3 and len(doc["images"])==2 and len(doc["meshes"])==2 and
            not doc.get("animations") and not doc.get("cameras"),doc.keys())
    root=next(node for node in doc["nodes"] if node["name"]=="FeatherMotes")
    require(len(root["children"])==2,root)
    old=set(bpy.data.objects)
    require(bpy.ops.import_scene.gltf(filepath=str(delivery/GLB))=={"FINISHED"},GLB)
    incoming=set(bpy.data.objects)-old
    require(len(incoming)==3,incoming)
    result={}
    for name,spec in SPECS.items():
        original=bpy.data.scenes[EXPORT_SCENE].objects[name]
        obj=next(item for item in incoming if item.name.split(".")[0]==name)
        result[name]=verify_card(original,obj,name,spec)
        node=next(n for n in doc["nodes"] if n["name"]==name)
        prim=doc["meshes"][node["mesh"]]["primitives"][0]
        coordinate=doc["accessors"][prim["attributes"]["POSITION"]]
        require(abs(coordinate["min"][2]+spec["card"][1]/2)<1e-6 and
                abs(coordinate["max"][1])<1e-6,coordinate)
        mat=doc["materials"][prim["material"]]
        base=doc["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
        emission=doc["textures"][mat["emissiveTexture"]["index"]]
        samp=doc["samplers"][base["sampler"]]
        require(mat["alphaMode"]=="BLEND" and mat["doubleSided"] and base==emission and
                samp["wrapS"]==samp["wrapT"]==33071,mat)
        img=doc["images"][base["source"]]
        view=doc["bufferViews"][img["bufferView"]]
        start=view.get("byteOffset",0)
        embedded=binary[start:start+view["byteLength"]]
        require(embedded==(delivery/spec["tex"]).read_bytes(),name)
        result[name]["embedded_sha256"]=sha256(embedded).hexdigest()
        for instance in instances:
            if instance["variant"]==name:
                mat_override=instance.material_slots[0].material
                instance.data=obj.data
                instance.material_slots[0].link="OBJECT"
                instance.material_slots[0].material=mat_override
        obj.hide_render=True
        obj.hide_set(True)
    render(scene,cam,folder/"roundtrip_fixed_rear.png")
    roundtrip=rgb_diff(folder/"roundtrip_fixed_rear.png",delivery/"preview_fixed_rear_peak.png")
    require(roundtrip["mean_max_channel_delta_rgb8"] < .3,roundtrip)
    video=video_probe(delivery/VIDEO)
    dump(folder/"independent_recheck.json",{"status":"pass","reopened":BLEND,"reimported":GLB,
         "checks":result,"playback_evidence":timing,"reopened_rgb_diff":native,
         "roundtrip_rgb_diff":roundtrip,"video":video})


def finalize(folder, checks):
    result=load(checks/"independent_recheck.json")
    require(result["status"]=="pass",result)
    shutil.copy2(checks/"roundtrip_fixed_rear.png",folder/"roundtrip_fixed_rear.png")
    qa=load(folder/"qa.json")
    qa["independent_delivered_directory_recheck"]=result
    qa["visual_observation"]="已目视固定机位关键帧、静音视频与技术顶视。暖白落羽缓降，微粒稀疏，雁体持续可辨。"
    qa["redlines"]="对照项目红线清单。效果仅为落脚后可关闭的静音视觉层。"
    qa["app_baseline"]="引用已有 iOS 27.2 模拟器基线及 340 项通过；本轮未运行 App。"
    dump(folder/"qa.json",qa)
    manifest=load(folder/"asset_manifest.json")
    manifest["files"]={path.relative_to(folder).as_posix():digest(path)
            for path in sorted(folder.rglob("*")) if path.is_file() and path.name!="asset_manifest.json"}
    dump(folder/"asset_manifest.json",manifest)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--library",type=Path,default=LIBRARY)
    parser.add_argument("--quick",action="store_true")
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--finalize",type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    out=args.output.resolve()
    if args.finalize:
        finalize(out,args.finalize.resolve())
        return
    out.mkdir(parents=True,exist_ok=True)
    require(not any(out.iterdir()),"Use a new empty output directory.")
    if args.verify:
        verify(out,args.verify.resolve(),args.library.resolve())
    else:
        build(out,args.library.resolve(),args.quick)


if __name__=="__main__":
    main()
