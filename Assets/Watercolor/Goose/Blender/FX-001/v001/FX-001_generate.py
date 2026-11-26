"""Build and independently verify FX-001 with Blender 5.2 and FFmpeg."""

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
ASSET = "FX-001"
BLEND = "FX-001_WindTail.blend"
SOURCE = "FX-001_generate.py"
VIDEO = "preview_fixed_rear.mp4"
MAT = "MAT-001/v001"
MAT_BLEND = f"{MAT}/MAT-001_watercolor_master.blend"
PAPER = "textures/ft_goose_mat_soft_stone_basecolor.png"
WATER = "textures/ft_goose_mat_water_fallback_basecolor.png"
CHR = "CHR-001/v001/CHR-001_goose_rig.glb"
CRUISE = "ANM-001/v001/ANM-001_cruise_flap.glb"
CAMERA = "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift"
PLAYFIELD = "Sources/FeatherTide/Rendering/PlayfieldView.swift"
BU = .9900 / 27.5
SIZE = (852, 393)
FPS = 12
FRAMES = 60
SPECS = {
    "WindTail_Long": {"length": 2.8, "width": .18, "bend": .19, "segments": 36,
                     "color": (235, 218, 163), "alpha": .37, "size": (512, 64)},
    "WindTail_Short": {"length": 1.4, "width": .13, "bend": .105, "segments": 24,
                      "color": (239, 231, 194), "alpha": .34, "size": (256, 64)},
}
REAR = "Gameplay | fixed rear"
TOP = "Technical | overhead"
NEUTRAL = "Review Ground"
# A center gap lets the wind pass around the flock without filling the screen.
LANES = [
    ("WindTail_Long", -3.69, -1.30, .10, .13, .18),
    ("WindTail_Short", -4.15, .80, .22, -.11, -.17),
    ("WindTail_Long", -3.82, 2.32, .63, .15, .15),
    ("WindTail_Short", -5.03, -.25, .41, -.18, -.17),
    ("WindTail_Long", 3.78, -.88, .25, -.20, -.17),
    ("WindTail_Short", 4.05, 1.19, .30, .11, .14),
    ("WindTail_Long", 3.91, 2.95, .57, -.14, -.14),
    ("WindTail_Short", 5.16, -.21, .78, .12, .17),
]


def require(condition, evidence):
    if not condition:
        raise ValueError(str(evidence))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_sources(library):
    root = library.parents[3]
    camera = (root / CAMERA).read_text()
    playfield = (root / PLAYFIELD).read_text()
    require("distance: 180, pitch: 0.48, fieldOfViewDegrees: 50" in camera and
            "Float(6 + lift)" in camera and "(body.leader ? 8 : 6)" in playfield,
            "Fixed camera or flight heights changed")
    upstream = json.loads((library / MAT / "asset_manifest.json").read_text())
    require(json.loads((library / MAT / "qa.json").read_text())["status"] == "done", "MAT-001 QA")
    for path in (Path(MAT_BLEND).name, PAPER, WATER):
        require(digest(library / MAT / path) == upstream["files"][path], path)
    return {"camera": digest(root / CAMERA), "playfield": digest(root / PLAYFIELD)}


def image_rows(img):
    pixels = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(pixels)
    return pixels.reshape(img.size[1], img.size[0], 4)


def write_rgba(path, pixels):
    """Use sRGB byte values and straight alpha without a second image dependency."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))
    height, width, _ = pixels.shape
    rows = b"".join(b"\0" + row.tobytes() for row in pixels[::-1])
    path.write_bytes(b"\x89PNG\r\n\x1a\n" +
                     chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
                     chunk(b"sRGB", b"\0") + chunk(b"IDAT", zlib.compress(rows, 8)) +
                     chunk(b"IEND", b""))


def smooth(a, b, value):
    t = np.clip((value - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def texture_path(name):
    return "textures/ft_goose_fx_" + name.replace("WindTail_", "wind_tail_").lower() + "_rgba.png"


def master_materials(library):
    # Verify both packed master images against MAT-001's actual tracked PNGs.
    with bpy.data.libraries.load(str(library / MAT_BLEND), link=False) as (source, dest):
        require({"SoftStone", "WaterFallback"} <= set(source.materials), source.materials)
        dest.materials = ["SoftStone", "WaterFallback"]
    images = {}
    for material_name, rel in (("SoftStone", PAPER), ("WaterFallback", WATER)):
        mat = bpy.data.materials[material_name]
        image = next(node.image for node in mat.node_tree.nodes if node.type == "TEX_IMAGE")
        require(image.packed_file.data == (library / MAT / rel).read_bytes(), rel)
        images[material_name] = image
    return images


def make_texture(output, name, spec, paper):
    width, height = spec["size"]
    u = (np.arange(width)[None, :] + .5) / width
    v = (np.arange(height)[:, None] + .5) / height
    # A soft, long tail feeds a denser leading stroke. Both tile edges are clear.
    along = smooth(.01, .43, u) * (1 - smooth(.78, .998, u))
    center = .50 + .055 * np.sin(u * math.tau + .7) + .025 * np.sin(u * math.tau * 3)
    radius = .30 * (.45 + .55 * smooth(.08, .65, u))
    brush = (1 - smooth(.10, 1.0, abs(v - center) / radius)) ** 1.22
    pigment = np.clip(paper[np.ix_((np.arange(height) * 3 + 147) % 512,
                                  (np.arange(width) + 17) % 512)], -2.5, 2.5)
    opacity = along * brush * (1 + .035 * pigment)
    rgba = np.empty((height, width, 4), dtype=np.uint8)
    rgba[:, :, :3] = np.clip(np.asarray(spec["color"]) + 2.8 * pigment[:, :, None], 0, 255)
    rgba[:, :, 3] = np.rint(255 * np.minimum(spec["alpha"], spec["alpha"] * opacity))
    rgba[:, (0, -1), 3] = 0
    rgba[(0, -1), :, 3] = 0
    path = output / texture_path(name)
    write_rgba(path, rgba)
    image = bpy.data.images.load(str(path), check_existing=False)
    image.alpha_mode = "STRAIGHT"
    image.pack()
    image.filepath = "//" + texture_path(name)
    return image


def new_material(name, rgba):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = rgba
    material.node_tree.nodes.clear()
    return material


def flat_material(name, rgb):
    material = new_material(name, (*rgb, 1))
    nodes = material.node_tree.nodes
    surface = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (*rgb, 1)
    material.node_tree.links.new(emission.outputs[0], surface.inputs["Surface"])
    return material


def ribbon_material(name, image):
    material = new_material(name, (.82, .69, .39, .35))
    material.surface_render_method = "BLENDED"
    material.use_backface_culling = False
    material.use_transparent_shadow = False
    nodes, links = material.node_tree.nodes, material.node_tree.links
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (60, 80)
    tex = nodes.new("ShaderNodeTexImage")
    tex.location = (-290, 110)
    tex.image = image
    tex.extension = "EXTEND"
    shader.inputs["Roughness"].default_value = 1
    shader.inputs["Specular IOR Level"].default_value = 0
    shader.inputs["Emission Strength"].default_value = .87
    links.new(tex.outputs["Color"], shader.inputs["Base Color"])
    links.new(tex.outputs["Color"], shader.inputs["Emission Color"])
    links.new(tex.outputs["Alpha"], shader.inputs["Alpha"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def collection(scene, name):
    group = bpy.data.collections.new(name)
    scene.collection.children.link(group)
    return group


def basic_mesh(group, name, verts, faces, uvs, material=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    uv = mesh.uv_layers.new(name="StrokeUV")
    for loop in mesh.loops:
        uv.data[loop.index].uv = uvs[loop.vertex_index]
    obj = bpy.data.objects.new(name, mesh)
    group.objects.link(obj)
    if material:
        mesh.materials.append(material)
    return obj


def make_ribbon(group, name, spec, material):
    vertices, faces, uvs = [], [], []
    for index in range(spec["segments"] + 1):
        u = index / spec["segments"]
        # Tangents return to +Y at both ends for translation tiling.
        center = spec["bend"] * math.sin(math.pi * u) ** 2 * math.sin(math.pi * (u + .17))
        width = spec["width"] * (.62 + .38 * math.sin(math.pi * u) ** 2)
        for v in (0, 1):
            vertices.append((center + (v - .5) * width, spec["length"] * u, 0))
            uvs.append((u, v))
        if index:
            i = index * 2 - 2
            faces.extend(((i, i + 1, i + 3), (i, i + 3, i + 2)))
    obj = basic_mesh(group, name, vertices, faces, uvs, material)
    obj["axis_forward"] = "+Y"
    obj["axis_up"] = "+Z"
    obj["length_BU"] = spec["length"]
    obj["width_BU"] = spec["width"]
    obj["uv_contract"] = "U upstream 0 to downstream 1; V left 0 to right 1"
    obj.asset_mark()
    obj.asset_data.description = "FX-001 reusable wind stroke; orient to the local wind vector."
    return obj


def camera(group, name, eye, target, ortho=None):
    data = bpy.data.cameras.new(name)
    data.sensor_fit = "VERTICAL"
    data.sensor_height = 24
    data.lens = 12 / math.tan(math.radians(50) / 2)
    data.clip_start, data.clip_end = .015, 220
    if ortho:
        data.type = "ORTHO"
        data.ortho_scale = ortho
    obj = bpy.data.objects.new(name, data)
    group.objects.link(obj)
    obj.location = eye
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def set_float(obj, name, value, low, high, description):
    obj[name] = value
    obj.id_properties_ui(name).update(min=low, max=high, description=description)


def make_controls(group, scene):
    control = bpy.data.objects.new("Wind | editable preview controls", None)
    group.objects.link(control)
    control.empty_display_size = .18
    set_float(control, "windBearingRad", 0., -math.pi, math.pi, "Positive yaw turns +Y toward -X.")
    set_float(control, "windSpeedBUPerSecond", 1.32, 0, 8, "Shared downstream advection speed.")
    set_float(control, "formationWeight", 0., 0, 1, "External visual weight, follows the 2 s review ease.")
    set_float(control, "reviewFlightBUPerSecond", .53, 0, 3, "Reviewer-only camera / flock travel.")
    set_float(control, "opacityMultiplier", 1., 0, 1, "Multiply base straight alpha.")
    for frame, weight in ((1, 0), (17, 0), (41, 1), (FRAMES, 1)):
        control["formationWeight"] = float(weight)
        control.keyframe_insert(data_path='["formationWeight"]', frame=frame)
    strip = control.animation_data.action.layers[0].strips[0]
    channelbag = strip.channelbag(control.animation_data.action_slot)
    for key in channelbag.fcurves[0].keyframe_points:
        key.handle_left_type = key.handle_right_type = "AUTO_CLAMPED"
    for frame, label in ((1, "Loose"), (17, "Formation begins"), (29, "Formation forming"),
                         (41, "Aligned")):
        scene.timeline_markers.new(label, frame=frame)
    return control


def driver(obj, prop, index, expression, variables):
    curve = obj.driver_add(prop, index) if index is not None else obj.driver_add(prop)
    drv = curve.driver
    drv.type = "SCRIPTED"
    drv.expression = expression
    for name, owner, key in variables:
        var = drv.variables.new()
        var.name = name
        var.type = "SINGLE_PROP"
        var.targets[0].id = owner
        var.targets[0].data_path = '["' + key + '"]'
    return curve


def move_preview(group, variants, ctrl, materials):
    rows = []
    for i, (variant, x, y, phase, yaw, sway) in enumerate(LANES, 1):
        x += math.copysign(.15, x)
        y += 2.0
        obj = bpy.data.objects.new(f"Review Stroke {i:02}", variants[variant].data)
        group.objects.link(obj)
        obj.material_slots[0].link = "OBJECT"
        obj.material_slots[0].material = materials[variant]
        obj["phaseOffsetBU"] = phase
        obj["looseYawRad"] = yaw
        obj["looseSwayBU"] = sway
        obj["variant"] = variant
        bearing = ("bearing", ctrl, "windBearingRad")
        speed = ("speed", ctrl, "windSpeedBUPerSecond")
        formation = ("formation", ctrl, "formationWeight")
        offset = ("offset", obj, "phaseOffsetBU")
        sway_var = ("sway", obj, "looseSwayBU")
        yaw_var = ("yaw", obj, "looseYawRad")
        travel = f"(offset + speed * (frame - 1) / {FPS})"
        obj.location.z = .085 + .002 * i
        driver(obj, "location", 0,
               f"{x} - sin(bearing) * {travel} + sway * (1 - formation) * sin(.27 * frame + offset)",
               [bearing, speed, offset, formation, sway_var])
        driver(obj, "location", 1, f"{y} + cos(bearing) * {travel}",
               [bearing, speed, offset])
        driver(obj, "rotation_euler", 2, "bearing + yaw * (1 - formation)",
               [bearing, yaw_var, formation])
        rows.append(obj)
    return rows


def review_material(src, ctrl):
    material = src.copy()
    material.name = "Review only | " + src.name
    nodes, links = material.node_tree.nodes, material.node_tree.links
    shader = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    tex = next(node for node in nodes if node.type == "TEX_IMAGE")
    amp = nodes.new("ShaderNodeMath")
    amp.operation = "MULTIPLY"
    amp.location = (-100, -170)
    amp.inputs[1].default_value = 1
    links.new(tex.outputs["Alpha"], amp.inputs[0])
    links.new(amp.outputs[0], shader.inputs["Alpha"])
    driver(amp.inputs[1], "default_value", None, "gain", [("gain", ctrl, "opacityMultiplier")])
    return material


def build_ground(group, water_image=None):
    ground = basic_mesh(group, NEUTRAL, [(-820, -60, 0), (820, -60, 0),
                        (820, 1300, 0), (-820, 1300, 0)], [(0, 1, 2, 3)],
                        [(0, 0), (1, 0), (1, 1), (0, 1)])
    if water_image is None:
        ground.data.materials.append(flat_material("Graybox | river", (.23, .26, .26)))
        return
    mat = flat_material("Review only | shallows on MAT-001 wash", (.20, .34, .32))
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    geo = nodes.new("ShaderNodeNewGeometry")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = .28
    noise.inputs["Detail"].default_value = 1.8
    links.new(geo.outputs["Position"], noise.inputs["Vector"])
    ramps = nodes.new("ShaderNodeValToRGB")
    colors = ramps.color_ramp
    colors.elements.remove(colors.elements[1])
    for i, (at, rgb) in enumerate((
        (.12, (.13, .23, .218)), (.35, (.19, .302, .284)),
        (.62, (.265, .365, .315)), (.79, (.364, .409, .30)),
        (.91, (.43, .425, .295)),
    )):
        element = colors.elements[0] if i == 0 else colors.elements.new(at)
        element.position = at
        element.color = (*rgb, 1)
    links.new(noise.outputs["Fac"], ramps.inputs[0])
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = (.14, .11, .0)
    links.new(geo.outputs["Position"], scale.inputs[0])
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = water_image
    links.new(scale.outputs[0], tex.inputs["Vector"])
    mix = nodes.new("ShaderNodeMixRGB")
    mix.inputs[0].default_value = .17
    links.new(ramps.outputs[0], mix.inputs[1])
    links.new(tex.outputs["Color"], mix.inputs[2])
    emission = next(node for node in nodes if node.type == "EMISSION")
    links.new(mix.outputs[0], emission.inputs[0])
    ground.data.materials.append(mat)


def light(group):
    data = bpy.data.lights.new("Review only | soft daylight", "AREA")
    data.shape = "DISK"
    data.energy = 1450
    data.size = 12
    obj = bpy.data.objects.new(data.name, data)
    group.objects.link(obj)
    obj.location = (1.5, -5, 15)
    obj.rotation_euler = (Vector((0, 1, 0)) - obj.location).to_track_quat("-Z", "Y").to_euler()


def from_glb(path):
    old = set(bpy.data.objects)
    result = bpy.ops.import_scene.gltf(filepath=str(path))
    require(result == {"FINISHED"}, path)
    return set(bpy.data.objects) - old


def preview_birds(scene, group, library, ctrl):
    imported = from_glb(library / CRUISE)
    meshes = [obj for obj in imported if obj.type == "MESH" and obj.name.startswith("Goose_LOD0")]
    rigs = [obj for obj in imported if obj.type == "ARMATURE"]
    require(len(meshes) == len(rigs) == 1, {obj.name: obj.type for obj in imported})
    mesh, rig = meshes[0], rigs[0]
    animation = rig.animation_data
    track = animation.nla_tracks[0]
    strip = track.strips[0]
    animation.action = None
    track.mute = False
    strip.blend_type = "REPLACE"
    strip.repeat = 5
    scene.frame_set(8)
    reference = bpy.data.meshes.new_from_object(mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    birds = []
    travel = ("travel", ctrl, "reviewFlightBUPerSecond")
    formation = ("formation", ctrl, "formationWeight")
    flight = bpy.data.objects.new("Review only | flight anchor", None)
    group.objects.link(flight)
    driver(flight, "location", 1, f"travel * (frame - 1) / {FPS}", [travel])
    # Keep the original animated lead bird and use the same evaluated cruise pose for followers.
    for obj in (mesh, rig):
        for old in tuple(obj.users_collection):
            old.objects.unlink(obj)
        group.objects.link(obj)
    rig.name = "Review only | lead armature"
    rig.parent = flight
    rig.location = (0, 0, 8 * BU)
    mesh.name = "Review Bird 00"
    birds.append(mesh)
    for i in range(11):
        side = -1 if i % 2 == 0 else 1
        row = 1 + i // 2
        obj = bpy.data.objects.new(f"Review Bird {i+1:02}", reference)
        group.objects.link(obj)
        obj.parent = flight
        obj.location = (0, 0, 6 * BU)
        obj.scale = (.8, .8, .8)
        loose_x = side * (29 + 7 * row) * BU + .14 * math.sin(1.91 * i)
        loose_y = (-(13.4 + (i % 2) * 1.3) * row) * BU
        locked_x = side * (26 + 6 * (row - 1)) * BU
        locked_y = -13 * row * BU
        driver(obj, "location", 0, f"{loose_x} * (1-formation) + {locked_x} * formation",
               [formation])
        driver(obj, "location", 1, f"{loose_y} * (1-formation) + {locked_y} * formation",
               [formation])
        birds.append(obj)
    return flight, birds


def change_camera(scene, angle, resolution=SIZE):
    scene.camera = bpy.data.objects[angle]
    scene.render.resolution_x, scene.render.resolution_y = resolution
    bpy.context.view_layer.update()


def setup(scene):
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 20
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = FRAMES
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.world = bpy.data.worlds.new("Review only | mist green")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (.18, .28, .29, 1)
    bg.inputs[1].default_value = .5


def render(scene, path):
    scene.render.filepath = str(path)
    require(bpy.ops.render.render(write_still=True) == {"FINISHED"}, path)


def export(scene, output, obj):
    scene.frame_set(1)
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_set(False)
    obj.hide_viewport = False
    obj.hide_render = False
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path = output / f"FX-001_{obj.name}.glb"
    result = bpy.ops.export_scene.gltf(filepath=str(path), use_selection=True, use_active_scene=True,
        export_extras=True, export_yup=True, export_animations=False,
        export_apply=False, export_image_format="AUTO")
    require(result == {"FINISHED"}, path)
    obj.hide_set(True)
    obj.hide_render = True


def scene_check(scene, strokes, birds, ctrl):
    checks = []
    spans = {}
    frame_yaws = []
    last = None
    minimum_screen_gap = SIZE[0]
    minimum_lead_margin = SIZE[0]
    change_camera(scene, REAR)
    for sample in range(2, FRAMES * 2 + 1):
        frame, half = divmod(sample, 2)
        scene.frame_set(frame, subframe=.5 * half)
        deps = bpy.context.evaluated_depsgraph_get()
        positions = []
        yaws = []
        evaluated_birds = [obj.evaluated_get(deps) for obj in birds]
        def bounds(obj):
            points = [world_to_camera_view(scene, scene.camera, obj.matrix_world @ Vector(v))
                      for v in obj.bound_box]
            require(min(p.z for p in points) > 0, (sample, obj.name, "behind camera"))
            return (min(p.x for p in points) * SIZE[0], max(p.x for p in points) * SIZE[0],
                    min(p.y for p in points) * SIZE[1], max(p.y for p in points) * SIZE[1])
        bird_boxes = [bounds(obj) for obj in evaluated_birds]
        for bird_box in bird_boxes:
            require(0 <= bird_box[0] < bird_box[1] <= SIZE[0] and
                    0 <= bird_box[2] < bird_box[3] <= SIZE[1], (sample, bird_box))
        for stroke in strokes:
            obj = stroke.evaluated_get(deps)
            positions.append(obj.matrix_world.translation.y)
            yaws.append(abs(obj.rotation_euler.z))
            bounds_stroke = bounds(obj)
            for index, box in enumerate(bird_boxes):
                horizontal = max(box[0] - bounds_stroke[1], bounds_stroke[0] - box[1])
                vertical = max(box[2] - bounds_stroke[3], bounds_stroke[2] - box[3])
                margin = max(horizontal, vertical)
                minimum_screen_gap = min(minimum_screen_gap, margin)
                if index == 0:
                    minimum_lead_margin = min(minimum_lead_margin, margin)
                require(margin > 0, (sample, stroke.name, index, bounds_stroke, box))
        if last:
            checks.extend((np.array(positions) - np.array(last)).tolist())
        if sample in (2, 60, 82, FRAMES * 2):
            frame_yaws.append({"frame": sample / 2, "max_abs_radians": max(yaws),
                               "formation_weight": ctrl.evaluated_get(deps)["formationWeight"]})
        last = positions
    require(min(checks) > 0 and frame_yaws[-1]["max_abs_radians"] < 1e-5, frame_yaws)
    camera_position = bpy.data.objects[REAR].matrix_local.translation
    target = Vector((0, 0, 6 * BU))
    expected = Vector((0, -180 * BU * math.cos(.48), 180 * BU * math.sin(.48)))
    require((camera_position - expected).length < 1e-5, camera_position)
    cam = bpy.data.objects[REAR]
    require((cam.rotation_euler.to_quaternion() @ Vector((0, 0, -1)) -
             (target - expected).normalized()).length < 1e-5, "camera aim")
    require(abs(cam.data.angle_y - math.radians(50)) < 1e-6, cam.data.angle_y)
    for frame in (12, 51):
        scene.frame_set(frame)
        deps = bpy.context.evaluated_depsgraph_get()
        # Re-express motion in camera pixels to distinguish wind drift from camera travel.
        cells = []
        for stroke in strokes:
            relative = stroke.evaluated_get(deps).matrix_world @                 Vector((0, SPECS[stroke["variant"]]["length"] * .63, 0))
            point = world_to_camera_view(scene, cam, relative)
            cells.append((point.x * SIZE[0], point.y * SIZE[1]))
        spans[frame] = cells
    projected = [end[1] - start[1] for start, end in zip(spans[12], spans[51])]
    require(min(projected) > 0, projected)
    return {"status": "pass", "half_frame_samples": FRAMES * 2 - 1,
            "world_downstream_advances_BU": [min(checks), max(checks)],
            "screen_downstream_center_travel_frames_12_to_51_px": projected,
            "formation_samples": frame_yaws,
            "minimum_stroke_to_leader_bbox_gap_px": minimum_lead_margin,
            "minimum_stroke_to_all_bird_bboxes_gap_px": minimum_screen_gap,
            "visible_birds_each_sample": len(birds)}


def read_glb(path):
    data = path.read_bytes()
    header, version, length, json_len, json_type = struct.unpack_from("<5I", data)
    require((header, version, length, json_type) == (0x46546C67, 2, len(data), 0x4E4F534A), path)
    bin_len, bin_type = struct.unpack_from("<2I", data, 20 + json_len)
    require(bin_type == 0x004E4942 and len(data) == 28 + json_len + bin_len, path)
    return json.loads(data[20:20 + json_len]), data[28 + json_len:]


def geometry_check(obj, name, spec):
    obj.data.calc_loop_triangles()
    vs = np.array([tuple(v.co) for v in obj.data.vertices])
    tris = obj.data.loop_triangles
    uvs = obj.data.uv_layers.active
    require(np.abs(vs[:, 2]).max() < 1e-5 and np.min(vs[:, 1]) == 0 and
            abs(np.max(vs[:, 1]) - spec["length"]) < 1e-5, (name, obj.dimensions))
    require(len(tris) == 2 * spec["segments"] and all(tri.area > 1e-7 and tri.normal.z > .999
            for tri in tris), name)
    max_v_error, max_u_error = 0, 0
    for loop in obj.data.loops:
        vtx = vs[loop.vertex_index]
        uv = uvs.data[loop.index].uv
        max_u_error = max(max_u_error, abs(uv.x - vtx[1] / spec["length"]))
        max_v_error = max(max_v_error, min(abs(uv.y), abs(uv.y - 1)))
    require(max(max_v_error, max_u_error) < 1e-5 and tuple(obj.scale) == (1., 1., 1.),
            (name, max_v_error, max_u_error, tuple(obj.scale)))
    first = vs[np.isclose(vs[:, 1], 0)][:, 0]
    last = vs[np.isclose(vs[:, 1], spec["length"])][:, 0]
    require(np.ptp(first) > 0 and np.allclose(sorted(first), sorted(last), atol=1e-6),
            (name, first, last))
    return {"vertices": len(vs), "triangles": len(tris), "length_BU": float(vs[:, 1].max()),
            "uv_u_max_error": max_u_error, "tile_endpoint_max_delta_BU":
            float(np.max(np.abs(sorted(first) - np.asarray(sorted(last)))))}


def verify_export(folder, name, spec):
    path = folder / f"FX-001_{name}.glb"
    doc, binary = read_glb(path)
    require(len(doc["nodes"]) == len(doc["meshes"]) == len(doc["materials"]) ==
            len(doc["images"]) == 1 and not doc.get("animations") and
            not doc.get("cameras"), name)
    root = doc["nodes"][0]
    require(root["name"] == name and "translation" not in root and "scale" not in root
            and "rotation" not in root, root)
    prim = doc["meshes"][0]["primitives"][0]
    coords = doc["accessors"][prim["attributes"]["POSITION"]]
    require(abs(coords["min"][2] + spec["length"]) < 1e-5 and coords["max"][2] < 1e-5 and
            max(abs(coords["min"][1]), abs(coords["max"][1])) < 1e-5, coords)
    mat = doc["materials"][0]
    base = doc["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
    emission = doc["textures"][mat["emissiveTexture"]["index"]]
    require(mat["alphaMode"] == "BLEND" and mat["doubleSided"] and base == emission, mat)
    require(doc["samplers"][0]["wrapS"] == doc["samplers"][0]["wrapT"] == 33071, doc["samplers"])
    view = doc["bufferViews"][doc["images"][0]["bufferView"]]
    embedded = binary[view.get("byteOffset", 0):view.get("byteOffset", 0)+view["byteLength"]]
    texture = folder / texture_path(name)
    require(embedded == texture.read_bytes(), (name, "embedded PNG mismatch"))
    img = bpy.data.images.load(str(texture), check_existing=False)
    alpha = image_rows(img)[:, :, 3]
    bpy.data.images.remove(img)
    require(alpha.max() <= spec["alpha"] + 1/255 and alpha.max() >= spec["alpha"] - .01 and
            not np.any(alpha[[0,-1], :]) and not np.any(alpha[:, [0,-1]]) and
            np.count_nonzero((alpha > .02) & (alpha < spec["alpha"] * .8)) > int(alpha.size * .13),
            (name, alpha.min(), alpha.max()))
    return {"status": "pass", "embedded_png_sha256": sha256(embedded).hexdigest(),
            "peak_alpha": float(alpha.max()), "all_texture_edges_alpha": 0,
            "alpha_mode": "BLEND", "double_sided": True, "static": True}


def probe_video(path):
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                   check=True)
    spec = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames",
       "-show_entries", "stream=codec_name,codec_type,width,height,nb_read_frames,duration",
       "-of", "json", str(path)]))["streams"]
    expected = {"codec_name": "h264", "codec_type": "video", "width": 852, "height": 394,
                "duration": "5.000000", "nb_read_frames": str(FRAMES)}
    require(spec == [expected], spec)
    return {"status": "pass", "source_size": list(SIZE), **spec[0], "audio_streams": 0}


def make_video(scene, output):
    frames = output / "_frames"
    frames.mkdir()
    for index in range(1, FRAMES + 1):
        scene.frame_set(index)
        render(scene, frames / f"frame_{index:03}.png")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS),
        "-i", str(frames / "frame_%03d.png"), "-vf", "pad=852:394:0:0", "-c:v", "libx264",
        "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output / VIDEO)],
        check=True)
    shutil.rmtree(frames)
    return probe_video(output / VIDEO)


def image_diff(a, b, threshold=4):
    def pixels(path):
        image = bpy.data.images.load(str(path), check_existing=False)
        array = image_rows(image)[:, :, :3] * 255
        bpy.data.images.remove(image)
        return array
    delta = np.abs(pixels(a) - pixels(b))
    return {"mean_abs_rgb8": float(np.mean(delta)), "max_abs_rgb8": float(delta.max()),
            "pixels_at_least_threshold": int(np.sum(delta.max(axis=2) >= threshold)),
            "threshold_rgb8": threshold}


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.context.preferences.filepaths.save_version = 0
    scene.name = "FX-001 | Tailwind review"
    setup(scene)
    return scene


def build(output, library, quick):
    source_sha = check_sources(library)
    scene = reset_scene()
    export_group = collection(scene, "Delivery | reusable editable meshes")
    background_group = collection(scene, "Review only | watercolor shallows")
    flock_group = collection(scene, "Review only | 12 geese")
    stroke_group = collection(scene, "Review only | wind ribbon instances")
    camera_group = collection(scene, "Review only | cameras and controls")
    light(camera_group)
    eye = (0, -180 * BU * math.cos(.48), 180 * BU * math.sin(.48))
    rear = camera(camera_group, REAR, eye, (0, 0, 6 * BU))
    camera(camera_group, TOP, (0, 5.1, 25), (0, 5.1, 0), ortho=18.5)
    ctrl = make_controls(camera_group, scene)
    variants = {name: make_ribbon(export_group, name, spec, None) for name, spec in SPECS.items()}
    flight, birds = preview_birds(scene, flock_group, library, ctrl)
    rear.parent = flight
    gray = flat_material("Graybox | neutral strips", (.62, .65, .65))
    preview_gray = {}
    for name, old in variants.items():
        old.data.materials.append(gray)
        old.hide_set(True)
        old.hide_render = True
        preview_gray[name] = gray
    strokes = move_preview(stroke_group, variants, ctrl, preview_gray)
    build_ground(background_group)
    scene.frame_set(17)
    change_camera(scene, REAR)
    render(scene, output / "graybox_fixed_rear.png")
    change_camera(scene, TOP, (1040, 930))
    render(scene, output / "graybox_top.png")
    for obj in list(background_group.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    output.joinpath("textures").mkdir()
    mat = master_materials(library)
    paper = image_rows(mat["SoftStone"])[:, :, :3].mean(axis=2)
    residual = paper - (np.roll(paper, 1, 0) + np.roll(paper, -1, 0) +
                        np.roll(paper, 1, 1) + np.roll(paper, -1, 1)) / 4
    residual = (residual - residual.mean()) / max(residual.std(), .001)
    build_ground(background_group, mat["WaterFallback"])
    runtime_materials = {}
    for name, obj in variants.items():
        tex = make_texture(output, name, SPECS[name], residual)
        runtime = ribbon_material(name + " | straight alpha watercolor", tex)
        runtime.asset_mark()
        runtime_materials[name] = review_material(runtime, ctrl)
        obj.data.materials.clear()
        obj.data.materials.append(runtime)
        obj.material_slots[0].link = "DATA"
        export(scene, output, obj)
    for obj in strokes:
        if not obj.material_slots:
            raise ValueError(obj.name)
        obj.material_slots[0].link = "OBJECT"
        obj.material_slots[0].material = runtime_materials[obj["variant"]]
    motion = scene_check(scene, strokes, birds, ctrl)
    for frame, label in ((17, "loose"), (29, "forming"), (51, "aligned")):
        scene.frame_set(frame)
        change_camera(scene, REAR)
        render(scene, output / f"preview_fixed_rear_{label}.png")
    stroke_group.hide_render = True
    render(scene, output / "comparison_without_fx.png")
    stroke_group.hide_render = False
    ctrl["opacityMultiplier"] = .4
    ctrl.update_tag()
    scene.frame_set(51)
    render(scene, output / "preview_fixed_rear_reduced.png")
    ctrl["opacityMultiplier"] = 1.
    ctrl.update_tag()
    scene.frame_set(51)
    visibility = image_diff(output / "preview_fixed_rear_aligned.png",
                            output / "comparison_without_fx.png")
    reduced = image_diff(output / "preview_fixed_rear_reduced.png",
                         output / "comparison_without_fx.png")
    require(0 < reduced["mean_abs_rgb8"] < visibility["mean_abs_rgb8"], reduced)
    require(visibility["pixels_at_least_threshold"] > 120 and visibility["max_abs_rgb8"] > 12,
            visibility)
    change_camera(scene, TOP, (1040, 930))
    render(scene, output / "preview_top.png")
    change_camera(scene, REAR)
    bpy.ops.object.select_all(action="DESELECT")
    ctrl.select_set(True)
    bpy.context.view_layer.objects.active = ctrl
    scene.render.filepath = "//"
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / BLEND), compress=True)
    if not quick:
        scene.eevee.taa_render_samples = 12
        video = make_video(scene, output)
    else:
        video = {"status": "not_run", "reason": "--quick"}
    dump(output / "qa.json", {"id": ASSET, "version": "v001", "status": "needs_review",
         "motion_preview": motion, "fixed_view_contrast": {"default": visibility, "reduced": reduced},
         "video": video,
         "pending": ["负责人确认水彩观感与静音风向可读性", "USDZ、RealityKit 与 App 接入",
                     "真实风向、队形、透明排序与剔除", "iPhone / iPad 真机验证"]})
    dump(output / "asset_manifest.json", {"id": ASSET, "version": "v001", "status": "needs_review",
         "name": "顺风流线", "priority": "P0", "level": "S1", "specification_pdf_page": 14,
         "blender": bpy.app.version_string, "upstream": {"MAT-001": {
             "status": "done", "files": {path: digest(library / path) for path in
                  (MAT_BLEND, f"{MAT}/{PAPER}", f"{MAT}/{WATER}")}}},
         "review_only_sources": {CHR: digest(library / CHR), CRUISE: digest(library / CRUISE)},
         "source_camera_sha256": {CAMERA: source_sha["camera"], PLAYFIELD: source_sha["playfield"]},
         "source": "程序化原创带状网格，项目内 MAT-001 SoftStone 纸纹抽样与浅金／乳白着色。",
         "license": "Feather & Tide 项目内原创与既有项目自有候选，无新增外部素材或署名。",
         "scale": {"beak_to_tail_BU": .9900, "game_units": 27.5, "BU_per_game_unit": BU},
         "camera": {"distance_game_units": 180, "pitch_rad": .48, "vertical_fov_deg": 50,
                    "target_height_game_units": 6, "lead_height_game_units": 8,
                    "follower_height_game_units": 6, "frame_size": SIZE},
         "variants": {name: {**spec, "mesh_triangles": 2 * spec["segments"],
           "texture": texture_path(name), "file": f"FX-001_{name}.glb"} for name, spec in SPECS.items()},
         "runtime_inputs": {
             "worldPosition": "Ground-space stroke anchor. Convert from game units by multiplying 0.036.",
             "worldWindDirection": "Finite nonzero horizontal unit vector. Align local forward to it.",
             "windSpeedBUPerSecond": "Nonnegative drift along wind direction. Omit stroke if wind is calm.",
             "elapsedSeconds": "Monotonic controller time.",
             "phaseOffsetBU": "Independent stroke/slot phase as downstream distance.",
             "formationWeight": "0–1. Ease local heading/sway variation into wind alignment. Game supplies it.",
             "opacityMultiplier": "Multiply source straight alpha. Feather on release or recycle.",
             "side_clearance": "Keep transparent geometry outside projected goose silhouettes.",
             "tiling": "Repeat upstream pivot at n × variant length along wind. Clear alpha at both edges.",
             "reverse": "Rotate the instance 180° about up for opposite wind. Preserve mesh/UV and positive scale.",
             "coordinates": "Blender +Y forward/+Z up → GLB -Z forward/+Y up, X unchanged.",
             "uv": "U=0 upstream, U=1 downstream. V across, left 0 to right 1.",
             "export_animation": "None. Blender controls and animation are review only.",
         }})
    shutil.copy2(__file__, output / SOURCE)


def verify(output, folder, library):
    check_sources(library)
    bpy.ops.wm.open_mainfile(filepath=str(folder / BLEND))
    scene = bpy.context.scene
    variants = {name: scene.objects[name] for name in SPECS}
    strokes = sorted((obj for obj in scene.objects if obj.name.startswith("Review Stroke ")),
                     key=lambda obj: obj.name)
    birds = sorted((obj for obj in scene.objects if obj.name.startswith("Review Bird ")),
                   key=lambda obj: obj.name)
    ctrl = scene.objects["Wind | editable preview controls"]
    require(len(strokes) == 8 and len(birds) == 12, (len(strokes), len(birds)))
    motion = scene_check(scene, strokes, birds, ctrl)
    scene.frame_set(51)
    change_camera(scene, REAR)
    render(scene, output / "reopened_fixed_rear.png")
    reopened = image_diff(folder / "preview_fixed_rear_aligned.png",
                          output / "reopened_fixed_rear.png")
    require(reopened["mean_abs_rgb8"] < .4, reopened)
    ctrl["windBearingRad"] = math.pi
    ctrl.update_tag()
    reversed_positions = []
    for frame in (50, 51):
        scene.frame_set(frame)
        deps = bpy.context.evaluated_depsgraph_get()
        positions = []
        for stroke in strokes:
            pose = stroke.evaluated_get(deps)
            rotated = pose.matrix_world.to_3x3() @ Vector((0, 1, 0))
            require((rotated - Vector((0, -1, 0))).length < 1e-5, rotated)
            require(tuple(pose.scale) == (1., 1., 1.), pose.scale)
            positions.append(pose.matrix_world.translation.y)
        reversed_positions.append(np.array(positions))
    reverse_delta = reversed_positions[1] - reversed_positions[0]
    require(np.all(reverse_delta < 0), reverse_delta)
    ctrl["windBearingRad"] = 0.
    ctrl.update_tag()
    scene.frame_set(51)
    results = {}
    for name, original in variants.items():
        spec = SPECS[name]
        raw = verify_export(folder, name, spec)
        before = geometry_check(original, name, spec)
        imported = from_glb(folder / f"FX-001_{name}.glb")
        require(len(imported) == 1, imported)
        imported_obj = next(iter(imported))
        require(imported_obj.type == "MESH", imported_obj)
        after = geometry_check(imported_obj, name, spec)
        require(before["triangles"] == after["triangles"], (before, after))
        original_vertices = sorted(tuple(round(value, 5) for value in v.co)
                                   for v in original.data.vertices)
        imported_vertices = sorted(set(tuple(round(value, 5) for value in v.co)
                                       for v in imported_obj.data.vertices))
        require(original_vertices == imported_vertices, name)
        images = {node.image for node in imported_obj.data.materials[0].node_tree.nodes
                  if node.type == "TEX_IMAGE"}
        require(len(images) == 1 and next(iter(images)).packed_file.data ==
                (folder / texture_path(name)).read_bytes(), name)
        for stroke in strokes:
            if stroke["variant"] == name:
                stroke.data = imported_obj.data
                stroke.material_slots[0].link = "DATA"
        imported_obj.hide_render = True
        imported_obj.hide_set(True)
        results[name] = {"source_geometry": before, "reimported_geometry": after, **raw}
    render(scene, output / "roundtrip_fixed_rear.png")
    roundtrip = image_diff(folder / "preview_fixed_rear_aligned.png",
                           output / "roundtrip_fixed_rear.png")
    require(roundtrip["mean_abs_rgb8"] < .7, roundtrip)
    video = probe_video(folder / VIDEO)
    dump(output / "independent_recheck.json", {"status": "pass",
        "reopened_file": BLEND, "variant_results": results, "reopened_motion": motion,
                "reversed_wind_forward_axis_and_positive_scale": "pass",
        "reversed_wind_frame_displacement_BU": reverse_delta.tolist(),
        "reopened_render": reopened, "roundtrip_render": roundtrip, "video": video})


def finalize(folder, recheck, review_complete):
    recheck = recheck.resolve()
    evidence = json.loads((recheck / "independent_recheck.json").read_text())
    require(evidence["status"] == "pass", evidence)
    qa = json.loads((folder / "qa.json").read_text())
    shutil.copy2(recheck / "roundtrip_fixed_rear.png", folder / "roundtrip_fixed_rear.png")
    qa["independent_artifact_directory_reopen"] = evidence
    qa["review"] = {
        "scope": "离线候选；运行时、App、iPhone / iPad 待验",
        "baseline": "iOS 27.2 模拟器现有灰盒构建及 340 项通过记录，本次未重跑。",
        "redlines": "对照 plans/_templates/redline-checklist.md；仅添加静音项目内候选特效、使用浅金与乳白。"
    }
    if review_complete:
        qa["review"]["visual_observation"] = (
            "对照固定机位片段、三个状态关键帧、顶视与无特效静帧，确认浅金／乳白笔触顺航向平移。"
            "结阵后行迹并行，主雁轮廓持续可辨；人因风向辨识待负责人审阅。")
    dump(folder / "qa.json", qa)
    manifest = json.loads((folder / "asset_manifest.json").read_text())
    manifest["files"] = {p.relative_to(folder).as_posix(): digest(p)
        for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "asset_manifest.json"}
    dump(folder / "asset_manifest.json", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--library", type=Path, default=HERE.parents[1])
    parser.add_argument("--verify", type=Path, metavar="DELIVERY")
    parser.add_argument("--quick", action="store_true", help="Develop without encoding the final video.")
    parser.add_argument("--finalize", type=Path, metavar="RECHECK")
    parser.add_argument("--review-complete", action="store_true")
    options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    output = options.output.resolve()
    library = options.library.resolve()
    if options.finalize:
        finalize(output, options.finalize, options.review_complete)
        return
    output.mkdir(parents=True, exist_ok=True)
    require(not any(output.iterdir()), f"Use an empty output directory: {output}")
    if options.verify:
        verify(output, options.verify.resolve(), library)
    else:
        build(output, library, options.quick)


if __name__ == "__main__":
    main()
