"""Build or independently verify FX-006 with Blender 5.2, ffmpeg and ffprobe."""
import argparse
import hashlib
import json
import math
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

ID = "FX-006"
VERSION = "v001"
BLEND = "FX-006_ripples.blend"
GLB = "FX-006_ripples.glb"
IDLE, LANDING = "Ripple_Idle", "Ripple_Landing"
TEXTURES = {
    IDLE: "textures/ft_goose_vfx_ripple_idle_basecolor_alpha.png",
    LANDING: "textures/ft_goose_vfx_ripple_landing_basecolor_alpha.png",
}
TILE = (3.2, 2.4)
LANDING_SIZE = 2.20
LANDING_SECONDS = 1.8
WATER_OFFSET = 0.009
STRESS_OFFSET_STEP = 0.001
SIZE = (852, 393)
FPS = 48
CONTACT = 51
FIRST, LAST = -23, 216
UV_PERIOD = 16.0
IDLE_GAIN = 2.4
SLOTS = [
    (0, 0), (-1.50, .61), (1.54, .59), (-3.27, 1.59), (3.36, 1.48),
    (-4.8, 3.36), (4.59, 3.40), (-2.25, 3.12), (2.10, 3.61),
    (.27, 2.57), (-1.13, 4.65), (1.59, 5.10),
]
SCENE = "FX-006 | Water landing review"
EXPORT_SCENE = "FX-006 | Portable cards"
CAMERA = "Gameplay | source fixed rear"
WATER_MATERIALS = ("Water_Shallow", "Water_Lake", "Water_River")
# Seconds, uniform card scale, linear opacity. Values are art controls.
ENVELOPE = [(0, .19, 0), (.10, .36, .73), (.32, .55, 1),
            (.65, .76, .72), (1.10, .93, .31), (LANDING_SECONDS, 1.12, 0)]
PENDING = [
    "负责人美术审阅。",
    "USDZ 或等效 RealityKit 材质、App 接入和真实 Land 事件／接触点／岸线。",
    "RealityKit 小屏透明排序、12 实例并发性能与 iPhone／iPad 真机验证。",
]


def digest(blob_or_path):
    return hashlib.sha256(
        blob_or_path.read_bytes() if isinstance(blob_or_path, Path) else blob_or_path
    ).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def read_json(path):
    return json.loads(path.read_text())


def glb_contents(path):
    raw = path.read_bytes()
    assert struct.unpack_from("<4sII", raw) == (b"glTF", 2, len(raw))
    length, chunk_type = struct.unpack_from("<I4s", raw, 12)
    assert chunk_type == b"JSON"
    binary_length, chunk_type = struct.unpack_from("<I4s", raw, 20 + length)
    assert chunk_type == b"BIN\x00"
    return json.loads(raw[20:20 + length]), raw[28 + length:28 + length + binary_length]


def glb_images(doc, binary):
    for image in doc["images"]:
        assert image["mimeType"] == "image/png"
        view = doc["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        yield binary[start:start + view["byteLength"]]


def parse_args():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("output", type=Path)
    args.add_argument("--library", type=Path, default=Path(__file__).resolve().parents[2])
    args.add_argument("--verify", type=Path)
    args.add_argument("--stills-only", action="store_true", help="Diagnostic build without the video")
    args.add_argument("--skip-video-check", action="store_true", help="Diagnostic verification for stills-only builds")
    values = args.parse_args(sys.argv[sys.argv.index("--") + 1:])
    values.output = values.output.resolve()
    values.library = values.library.resolve()
    values.output.mkdir(parents=True, exist_ok=True)
    assert not any(values.output.iterdir()), "Supply a new or empty output directory"
    return values


def load_inputs(library):
    water = library / "MAT-004/v001"
    master, glb = (water / ("MAT-004_water_surfaces." + ext) for ext in ("blend", "glb"))
    manifest = read_json(water / "asset_manifest.json")
    water_qa = read_json(water / "qa.json")
    assert water_qa["checks"]["glb_import_geometry_uv_material_alpha"] == "pass"
    assert digest(glb) == manifest["files"][glb.name]
    expected_pngs = {}
    for name in WATER_MATERIALS:
        rel = manifest["materials"][name]["file"]
        expected_pngs[name] = water / rel
        assert digest(water / rel) == manifest["files"][rel]
    water_doc, water_bin = glb_contents(glb)
    assert {digest(i) for i in glb_images(water_doc, water_bin)} == {
        digest(file) for file in expected_pngs.values()
    }
    with bpy.data.libraries.load(str(master), link=False) as (available, imported):
        assert set(WATER_MATERIALS) <= set(available.materials)
        imported.materials = list(WATER_MATERIALS)
    mats = dict(zip(WATER_MATERIALS, imported.materials))
    packed = {}
    for name, mat in mats.items():
        image = mat.node_tree.nodes["Image Texture"].image
        packed[name] = digest(bytes(image.packed_file.data))
        assert packed[name] == digest(expected_pngs[name])
        image.filepath = "//../../MAT-004/v001/textures/" + expected_pngs[name].name
    animation = library / "ANM-007/v001"
    anim_master = animation / "ANM-007_landing.blend"
    anim_manifest = read_json(animation / "asset_manifest.json")
    anim_qa = read_json(animation / "qa.json")
    assert digest(anim_master) == anim_manifest["files"][anim_master.name]
    assert anim_manifest["review"]["contact_frames"]["Land_ShallowWater"] == CONTACT
    assert anim_manifest["clips"]["Land_ShallowWater"]["fps"] == FPS
    assert anim_qa["id"] == "ANM-007"
    with bpy.data.libraries.load(str(anim_master), link=False) as (available, imported):
        label = "Review | Land_ShallowWater"
        assert label in available.scenes
        imported.scenes = [label]
    reference, = imported.scenes
    scale = read_json(library / "CHR-001/v001/asset_manifest.json")["camera"]["preview_game_units_per_BU"]
    return mats, reference, scale, {
        "MAT-004/v001": {
            "role": "正式制作依赖，追加母版可编辑水面材质。浅水用于预览。",
            "review_state": water_qa["status"],
            "master_sha256_actual": digest(master),
            "master_sha256_declared": manifest["files"][master.name],
            "master_hash_matches_manifest": digest(master) == manifest["files"][master.name],
            "portable_glb_sha256": digest(glb),
            "three_packed_material_images_match_declared_PNG_and_GLB_bytes": packed,
        },
        "ANM-007/v001": {
            "role": "仅用于预览。实际引擎以独立落水接触事件触发。",
            "master_sha256": digest(anim_master),
            "clip": "Land_ShallowWater",
            "review_contact_frame": CONTACT,
        },
    }


def linear(hex_color):
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb)


def material(name, hex_color, roughness=.88):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    color = (*linear(hex_color), 1)
    mat.diffuse_color = color
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Specular IOR Level"].default_value = .12
    return mat


def mesh_object(collection, name, vertices, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def card(collection, name, dimensions, mat, repeat=(1, 1)):
    x, y = (length / 2 for length in dimensions)
    obj = mesh_object(collection, name, [(-x, -y, 0), (x, -y, 0), (x, y, 0), (-x, y, 0)],
                      [(0, 1, 2, 3)])
    uv = obj.data.uv_layers.new(name="UVMap")
    u, v = repeat
    for loop, xy in zip(uv.data, [(0, 0), (u, 0), (u, v), (0, v)]):
        loop.uv = xy
    if mat:
        obj.data.materials.append(mat)
    return obj


def set_scene(scene):
    bpy.context.window.scene = scene


def configure_render(scene):
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 16
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = FIRST, LAST
    scene.render.resolution_x, scene.render.resolution_y = SIZE
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"


def still(scene, output, name, frame, camera=None):
    set_scene(scene)
    original = scene.camera
    if camera:
        scene.camera = camera
    scene.frame_set(frame)
    scene.render.filepath = str(output / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    scene.camera = original


def camera(scene, name, eye, target):
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = eye
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    data.clip_start, data.clip_end = .055, 360
    return obj


def light(scene, name, rotation, energy, color):
    data = bpy.data.lights.new(name, "SUN")
    data.energy, data.angle, data.color = energy, .22, color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.rotation_euler = rotation


def actors(scene, reference):
    source_rig, = [obj for obj in reference.objects if obj.type == "ARMATURE"]
    source_mesh, = [obj for obj in reference.objects if obj.type == "MESH" and obj.parent]
    source_carrier = source_rig.parent
    water_plane, = [obj for obj in reference.objects if obj.name.endswith("reference plane")]
    birds, carriers = [], []
    for index, (x, y) in enumerate(SLOTS):
        suffix = f"{index + 1:02d}"
        spawn = bpy.data.objects.new("Review slot " + suffix, None)
        scene.collection.objects.link(spawn)
        scale = 1.0 if index == 0 else .8
        spawn.location = (x, y, -water_plane.location.z * scale)
        spawn.scale = (scale,) * 3
        carrier = source_carrier.copy()
        carrier.name = "ANM-007 path " + suffix
        scene.collection.objects.link(carrier)
        carrier.parent = spawn
        rig = source_rig.copy()
        rig.name = "ANM-007 pose " + suffix
        scene.collection.objects.link(rig)
        rig.parent = carrier
        bird = source_mesh.copy()
        bird.name = "Review goose " + suffix
        scene.collection.objects.link(bird)
        bird.parent = rig
        bird.modifiers["GooseSkin"].object = rig
        if index:
            tint = bpy.data.materials.get(f"Body_Follower_{'ABC'[(index - 1) % 3]}")
            if tint:
                bird.material_slots[0].link = "OBJECT"
                bird.material_slots[0].material = tint
        carriers.append(carrier)
        birds.append(bird)
    return birds, carriers


def surface_style(scene, ground, water, water_mat):
    ground.data.materials.clear()
    silt = material("Review | Watercolor silt", "aaa791")
    node = silt.node_tree.nodes
    links = silt.node_tree.links
    tex = node.new("ShaderNodeTexCoord")
    noise = node.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = .34
    noise.inputs["Detail"].default_value = 3.4
    links.new(tex.outputs["Object"], noise.inputs["Vector"])
    wash = node.new("ShaderNodeValToRGB")
    wash.color_ramp.elements[0].position = .15
    wash.color_ramp.elements[0].color = (*linear("7b8777"), 1)
    wash.color_ramp.elements[1].position = .84
    wash.color_ramp.elements[1].color = (*linear("c6b69a"), 1)
    links.new(noise.outputs["Fac"], wash.inputs[0])
    links.new(wash.outputs[0], node["Principled BSDF"].inputs["Base Color"])
    ground.data.materials.append(silt)
    water.data.materials.clear()
    water.data.materials.append(water_mat)

    reeds = [material("Review | Reed " + str(i), color) for i, color in enumerate(
        ("686043", "777d57", "8b9470", "aca27a"))]
    rng = np.random.default_rng(6186)
    vertices, faces, colors = [], [], []
    # Sparse banks leave the central landing group legible.
    for x0, y0, count, spread in [(-7.8, -2.8, 53, 1.22), (7.8, -2.3, 58, 1.16),
                                  (-9.5, 5.8, 89, 2), (10.0, 7.3, 90, 2),
                                  (-6.6, 12.0, 60, 1.5), (8.5, 13.3, 62, 1.5),
                                  (0, 15, 119, 5.5)]:
        for _ in range(count):
            x, y = x0 + rng.normal(0, spread), y0 + rng.normal(0, spread * .53)
            height, width = rng.uniform(.16, .62), rng.uniform(.025, .105)
            dx, dy = rng.uniform(-.18, .18, size=2)
            turn = rng.uniform(0, math.tau)
            ox, oy = width * math.cos(turn), width * math.sin(turn)
            i = len(vertices)
            vertices.extend([(x - ox / 2, y - oy / 2, -.046),
                             (x + ox / 2, y + oy / 2, -.046),
                             (x + dx / 3 + ox / 3, y + dy / 3 + oy / 3, height * .56),
                             (x + dx / 3 - ox / 3, y + dy / 3 - oy / 3, height * .56),
                             (x + dx, y + dy, height)])
            faces.extend([(i, i + 1, i + 2, i + 3), (i + 3, i + 2, i + 4)])
            colors.extend([int(rng.integers(0, len(reeds)))] * 2)
    leaves = mesh_object(scene.collection, "Review | Far reed banks", vertices, faces)
    for mat in reeds:
        leaves.data.materials.append(mat)
    for polygon, color in zip(leaves.data.polygons, colors):
        polygon.material_index = color


def write_rgba_png(path, rgba):
    def chunk(label, pixels):
        return struct.pack(">I", len(pixels)) + label + pixels + struct.pack(
            ">I", zlib.crc32(label + pixels))
    height, width, channels = rgba.shape
    assert channels == 4
    scanlines = b"".join(b"\0" + row.tobytes() for row in rgba)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" +
        chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0)) +
        chunk(b"sRGB", b"\0") + chunk(b"IDAT", zlib.compress(scanlines, 8)) +
        chunk(b"IEND", b""))


def paint(path, name):
    size = 512
    coord = np.linspace(0, 1, size, dtype=np.float64)
    u, v = np.meshgrid(coord, 1 - coord)
    cool = np.array([184, 204, 209], dtype=float)
    gold = np.array([236, 224, 190], dtype=float)
    if name == IDLE:
        # Arc centres are on a torus so the soft wash wraps in both directions.
        alpha, warm = np.zeros_like(u), np.zeros_like(u)
        for x, y, r, stretch, phase, weight in [
            (.055, .19, .16, .54, .19, .90), (.36, .37, .18, .41, 2.1, .95),
            (.76, .61, .28, .36, 3.3, .83), (.19, .83, .16, .50, 4.6, .83),
            (.90, .93, .105, .46, .9, .71), (.60, .15, .17, .34, 5.1, .78),
        ]:
            x_local = (u - x + .5) % 1 - .5
            y_local = ((v - y + .5) % 1 - .5) / stretch
            angle = np.arctan2(y_local, x_local)
            radius = np.hypot(x_local, y_local)
            edge = r * (1 + .045 * np.sin(3 * angle + phase))
            stroke = np.exp(-((radius - edge) / (.0087 + .002 * np.cos(angle + phase))) ** 2)
            arc = .22 + .78 * np.clip(np.cos(angle * 2 + phase), 0, 1) ** 2
            alpha = np.maximum(alpha, stroke * arc * weight)
            warm = np.maximum(warm, stroke * (.5 + .5 * np.sin(angle + phase)))
        alpha *= .37
    else:
        x, y = u - .5, (v - .5) * 1.025
        angle = np.arctan2(y, x)
        radius = np.hypot(x, y)
        outer = .36 + .006 * np.sin(3 * angle + .65) + .004 * np.cos(5 * angle)
        inner = .224 + .005 * np.sin(2 * angle - .88)
        fray = .5 + .5 * np.sin(3 * angle - .55)
        arc = .33 + .67 * (.5 + .5 * np.cos(2 * angle + .28)) ** 1.36
        warm = .62 + .38 * np.cos(angle - .56)
        a = np.exp(-((radius - outer) / (.013 + .003 * fray)) ** 2) * arc
        b = np.exp(-((radius - inner) / (.014 + .004 * fray)) ** 2) * (1 - .45 * arc)
        a_halo = .13 * np.exp(-((radius - outer) / .028) ** 2) * arc
        alpha = (.51 * a + .30 * b + a_halo) * np.clip((.475 - radius) / .047, 0, 1)
    paper = .92 + .035 * np.sin(math.tau * (19 * u + 11 * v)) + .045 * np.sin(
        math.tau * (31 * u - 39 * v + .09 * np.cos(math.tau * 12 * u)))
    rgb = cool + (gold - cool) * warm[..., None]
    rgba = np.round(np.concatenate([rgb, (255 * alpha * paper)[..., None]], axis=2)).astype(np.uint8)
    if name == IDLE:
        assert np.max(np.abs(rgba[0].astype(int) - rgba[-1])) <= 1
        assert np.max(np.abs(rgba[:, 0].astype(int) - rgba[:, -1])) <= 1
    else:
        assert not np.any(rgba[[0, -1], :, 3]) and not np.any(rgba[:, [0, -1], 3])
    write_rgba_png(path, rgba)
    return {"resolution": [size, size], "alpha_max_8bit": int(rgba[..., 3].max()),
            "alpha_soft_pixels": int(np.count_nonzero(rgba[..., 3])),
            "wrap_RGBA_error_8bit": [int(np.max(np.abs(rgba[0].astype(int) - rgba[-1]))),
                                      int(np.max(np.abs(rgba[:, 0].astype(int) - rgba[:, -1])))]
                                      if name == IDLE else None}


def fx_material(name, image):
    mat = material(name, "cbd7ce")
    mat.surface_render_method = "BLENDED"
    mat.use_backface_culling = True
    mat.use_transparent_shadow = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes["Principled BSDF"]
    shader.inputs["Specular IOR Level"].default_value = 0
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.name = "Ripple | packed RGBA"
    image_node.label = "sRGB pigment with straight linear alpha"
    image_node.image = image
    image_node.extension = "REPEAT" if name == IDLE else "EXTEND"
    image_node.location = (-400, 90)
    links.new(image_node.outputs["Color"], shader.inputs["Base Color"])
    links.new(image_node.outputs["Alpha"], shader.inputs["Alpha"])
    return mat


def vector_uv(mat, water_image, ripple_image):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    wave = nodes.new("ShaderNodeTexImage")
    wave.name, wave.image = "Ripple | packed RGBA", ripple_image
    wave.extension = "REPEAT"
    wave.location = (-250, 210)
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map, uv.location = "UVMap", (-720, 170)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.name, mapping.label = "Continuous UV drift", "Tile drifts +1 U every 16 seconds"
    mapping.location = (-520, 190)
    links.new(uv.outputs[0], mapping.inputs["Vector"])
    links.new(mapping.outputs[0], wave.inputs[0])
    for frame, value in [(1, 0), (1 + FPS * UV_PERIOD, 1)]:
        mapping.inputs["Location"].default_value.x = value
        mapping.inputs["Location"].keyframe_insert("default_value", index=0, frame=frame)
    node_animation_linear(mat.node_tree)
    curve, = action_curves(mat.node_tree)
    curve.modifiers.new(type="CYCLES")

    shore_uv = nodes.new("ShaderNodeUVMap")
    shore_uv.uv_map, shore_uv.location = "WaterUV", (-710, -230)
    shore_layer = nodes.new("ShaderNodeTexImage")
    shore_layer.name, shore_layer.image = "MAT-004 shore mask", water_image
    shore_layer.location = (-400, -190)
    shore_layer.extension = "CLIP"
    links.new(shore_uv.outputs[0], shore_layer.inputs[0])
    blend = nodes.new("ShaderNodeMath")
    blend.operation = "MULTIPLY"
    blend.location = (120, 60)
    links.new(wave.outputs["Alpha"], blend.inputs[0])
    links.new(shore_layer.outputs["Alpha"], blend.inputs[1])
    surface = nodes["Principled BSDF"]
    color = nodes.new("ShaderNodeMixRGB")
    color.label = "Pigment over MAT-004"
    color.location = (0, 260)
    strength = nodes.new("ShaderNodeMath")
    strength.operation, strength.label = "MULTIPLY", "Idle pigment gain"
    strength.location = (115, 195)
    strength.inputs[1].default_value = IDLE_GAIN
    strength.use_clamp = True
    links.new(blend.outputs[0], strength.inputs[0])
    links.new(strength.outputs[0], color.inputs[0])
    links.new(shore_layer.outputs["Color"], color.inputs[1])
    links.new(wave.outputs["Color"], color.inputs[2])
    links.new(color.outputs[0], surface.inputs["Base Color"])
    links.new(shore_layer.outputs["Alpha"], surface.inputs["Alpha"])


def action_curves(owner):
    action = owner.animation_data.action
    return action.layers[0].strips[0].channelbag(owner.animation_data.action_slot).fcurves


def node_animation_linear(owner):
    for curve in action_curves(owner):
        for key in curve.keyframe_points:
            key.interpolation = "LINEAR"


def landing_shader(mat):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    wave = nodes["Ripple | packed RGBA"]
    actor = nodes.new("ShaderNodeObjectInfo")
    actor.location = (-420, -240)
    opacity = nodes.new("ShaderNodeMath")
    opacity.operation, opacity.location = "MULTIPLY", (50, 90)
    links.new(wave.outputs["Alpha"], opacity.inputs[0])
    links.new(actor.outputs["Alpha"], opacity.inputs[1])
    links.new(opacity.outputs[0], nodes["Principled BSDF"].inputs["Alpha"])


def foot_indices(bird):
    groups = {g.index for g in bird.vertex_groups if g.name in {"Foot.L", "Foot.R"}}
    assert len(groups) == 2
    return [v.index for v in bird.data.vertices if any(g.group in groups for g in v.groups)]


def lowest_foot(bird, depsgraph, feet):
    posed = bird.evaluated_get(depsgraph)
    return min((posed.matrix_world @ posed.data.vertices[i].co for i in feet), key=lambda p: p.z)


def export_cards(output, scene):
    set_scene(scene)
    for obj in scene.objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(output / GLB), export_format="GLB",
        use_active_scene=True, use_selection=True, export_extras=True, export_animations=False,
        export_image_format="AUTO", export_cameras=False, export_lights=False)


def animate_landing(obj):
    obj["preview_contact_frame"] = CONTACT
    for seconds, scale, opacity in ENVELOPE:
        frame = CONTACT + FPS * seconds
        obj.scale = (scale,) * 3
        obj.color = (1, 1, 1, opacity)
        obj.keyframe_insert("scale", frame=frame)
        obj.keyframe_insert("color", index=3, frame=frame)
    for curve in action_curves(obj):
        for key in curve.keyframe_points:
            key.interpolation = "BEZIER"
            key.handle_left_type = key.handle_right_type = "AUTO_CLAMPED"


def build_stage(reference, scale):
    source_scene = bpy.context.scene
    scene = bpy.data.scenes.new(SCENE)
    set_scene(scene)
    configure_render(scene)
    world = bpy.data.worlds.new("Review | Cool morning")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (*linear("b7c8ca"), 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = .8
    scene.world = world
    light(scene, "Review | Soft morning sun", (.60, -.34, -.58), 2.15, (1, .94, .85))
    light(scene, "Review | Broad sky fill", (.42, .64, .41), .72, (.75, .87, 1))
    birds, carriers = actors(scene, reference)
    eye = (0, -180 * math.cos(.48) / scale, 180 * math.sin(.48) / scale)
    target = (0, 0, 6 / scale)
    cam = camera(scene, CAMERA, eye, target)
    cam.data.sensor_fit = "VERTICAL"
    cam.data.lens = cam.data.sensor_height / (2 * math.tan(math.radians(50) / 2))
    follow = cam.constraints.new("COPY_LOCATION")
    follow.use_offset = True
    follow.target = carriers[0]
    scene.camera = cam
    top = camera(scene, "Technical | Top", (0, 2.65, 15), (0, 2.65, 0))
    top.data.type, top.data.ortho_scale = "ORTHO", 14.8
    detail = camera(scene, "Technical | Water material detail", (2.6, -2.6, 2.2), (0, .64, 0))
    detail.data.type, detail.data.ortho_scale = "ORTHO", 5.5
    ground = card(scene.collection, "Review | Basin substrate", (270, 360),
        material("Graybox | Basin", "807b74"))
    ground.location = (0, 88, -.055)
    water = card(scene.collection, "Review | MAT-004 shallow water", (23.5, 29.8),
        material("Graybox | Water plane", "707d82"))
    water.location = (0, 5.6, 0)
    group = bpy.data.collections.new("FX-006 | Runtime instances in review")
    scene.collection.children.link(group)
    marker = material("Graybox | Ripple footprint", "aeb5b5")
    scene.frame_set(CONTACT)
    graph = bpy.context.evaluated_depsgraph_get()
    anchors, rings = [], []
    for i, bird in enumerate(birds):
        point = lowest_foot(bird, graph, foot_indices(bird))
        assert abs(point.z) < 5e-6, (i, point)
        anchors.append((float(point.x), float(point.y), float(point.z)))
        count = 56
        vertices = [(r * math.cos(math.tau * j / count), r * math.sin(math.tau * j / count), 0)
                    for r in (.77, .808) for j in range(count)]
        faces = [(j, count + j, count + (j + 1) % count, (j + 1) % count) for j in range(count)]
        ring = mesh_object(group, f"Graybox | Contact {i + 1:02d}", vertices, faces)
        ring.location = (point.x, point.y, WATER_OFFSET + i * STRESS_OFFSET_STEP)
        ring.data.materials.append(marker)
        rings.append(ring)
    return scene, ground, water, birds, anchors, rings, group, top, detail, source_scene


def review_build(output, stage, mats):
    scene, ground, water, birds, anchors, rings, group, top, detail, source_scene = stage
    still(scene, output, "graybox_fixed_rear", CONTACT + 26)
    still(scene, output, "graybox_top", CONTACT + 26, top)
    for ring in rings:
        bpy.data.objects.remove(ring, do_unlink=True)
    surface_style(scene, ground, water, mats["Water_Shallow"])
    portable = bpy.data.scenes.new(EXPORT_SCENE)
    set_scene(portable)
    configure_render(portable)
    (output / "textures").mkdir()
    cards, statistics = {}, {}
    for name, dims in [(IDLE, TILE), (LANDING, (LANDING_SIZE, LANDING_SIZE))]:
        rel = TEXTURES[name]
        statistics[name] = paint(output / rel, name)
        img = bpy.data.images.load(str(output / rel))
        img.alpha_mode = "STRAIGHT"
        img.pack()
        img.filepath = "//" + rel
        cards[name] = card(portable.collection, name, dims, fx_material(name, img))
        cards[name]["variant"] = name
        cards[name]["role"] = "runtime_geometry_sample"
    export_cards(output, portable)
    set_scene(scene)
    # Pigment rides in the existing water pass to keep the shoreline alpha and the
    # diffuse ripples from fighting for two independently sorted transparent layers.
    water.name = "Review | Ripple_Idle drift and shore mask"
    water.data.uv_layers["UVMap"].name = "WaterUV"
    wave_uv = water.data.uv_layers.new(name="UVMap")
    u, v = 23.5 / TILE[0], 29.8 / TILE[1]
    for loop, uv in zip(wave_uv.data, [(0, 0), (u, 0), (u, v), (0, v)]):
        loop.uv = uv
    water.data.materials[0] = mats["Water_Shallow"].copy()
    water.data.materials[0].name = "Review | MAT-004 + Ripple_Idle"
    water_image = mats["Water_Shallow"].node_tree.nodes["Image Texture"].image
    ripple_image = cards[IDLE].data.materials[0].node_tree.nodes["Ripple | packed RGBA"].image
    vector_uv(water.data.materials[0], water_image, ripple_image)
    land_mesh = cards[LANDING].data.copy()
    land_mesh.name = "Ripple_Landing | Shared review mesh"
    land_mat = land_mesh.materials[0].copy()
    land_mesh.materials[0] = land_mat
    landing_shader(land_mat)
    for i, (x, y, _) in enumerate(anchors):
        obj = bpy.data.objects.new(f"Review impact {i + 1:02d}", land_mesh)
        group.objects.link(obj)
        obj.location = (x, y, WATER_OFFSET + i * STRESS_OFFSET_STEP)
        animate_landing(obj)
    for label, frame in [("Approach | idle only", 5), ("12 shallow-water contacts", CONTACT),
                         ("Landing ripples grow", 76), ("Idle resumes", CONTACT + math.ceil(FPS * LANDING_SECONDS))]:
        scene.timeline_markers.new(label, frame=frame)
    bpy.data.scenes.remove(source_scene)
    bpy.data.scenes.remove(next(s for s in bpy.data.scenes if s.name.startswith("Review | Land_ShallowWater")))
    for window in bpy.context.window_manager.windows:
        window.scene = scene
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
    scene.frame_set(76)
    scene.render.filepath = "//"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output / BLEND), compress=True)
    still(scene, output, "preview_idle_fixed_rear", 51)
    still(scene, output, "preview_landing_fixed_rear", 76)
    still(scene, output, "preview_landing_top", 76, top)
    still(scene, output, "preview_landing_detail", 76, detail)
    return statistics


def timeline_video(scene, output):
    # Preserve the unusual 393-pixel height in the source renders. H.264 4:2:0 needs
    # pairs of rows; one neutral bottom row gives broad hardware decoder support.
    with TemporaryDirectory(prefix="fx006-frames-", dir=output.parent) as directory:
        frames = Path(directory)
        for i, f in enumerate(range(FIRST, LAST + 1, 3)):
            still(scene, frames, f"{i:04d}", f)
        subprocess.run(["ffmpeg", "-v", "error", "-threads", "2", "-y", "-framerate", str(FPS // 3),
            "-i", str(frames / "%04d.png"), "-vf", "pad=852:394:0:0:color=0x989d88",
            "-an", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(output / "preview_fixed_rear.mp4")], check=True)


def mapping(scale, anchors):
    return {
        "axes_blender": "+X right, +Y forward, +Z up",
        "axes_gltf_and_ground": "Blender (x,y,z) -> (x,z,-y)",
        "game_units_per_BU": scale,
        "scale_reference": "CHR-001/v001 actual 0.9900 BU bill-to-tail maps to 27.5 game units",
        "camera": {"viewport_px": list(SIZE), "distance_game_units": 180, "pitch_parameter_rad": .48,
                   "vertical_fov_deg": 50, "aim_height_game_units": 6,
                   "source": "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift"},
        IDLE: {
            "inputs": ["positionOnWaterPlaneBU", "timeSeconds", "driftDirectionXZ", "waterAlpha", "strength"],
            "placement": "Use existing MAT-004 water coverage; combine into water shader where possible",
            "texture": TEXTURES[IDLE],
            "tile_dimensions_BU": list(TILE),
            "tile_dimensions_game_units": [d * scale for d in TILE],
            "default_uv_velocity_tiles_per_sec": [1 / UV_PERIOD, 0],
            "uv": "Repeat; project a common world origin across adjoining patches, then add wrapped time offset",
            "default_pigment_gain": IDLE_GAIN,
            "pigment_mix_weight": "clamp(textureAlpha * waterAlpha * strength, 0, 1); preserve the water pass alpha",
        },
        LANDING: {
            "inputs": ["gooseID", "waterContactPositionWorld", "eventTimestampSeconds", "contactStrength"],
            "trigger": "Fire once per actual shallow-water Land contact; allocate an independent pooled instance for each goose.",
            "texture": TEXTURES[LANDING],
            "pivot": "Bottom-centred in the water plane. Apply world position using the real contact point.",
            "card_width_BU": LANDING_SIZE,
            "min_above_water_BU": WATER_OFFSET,
            "seconds": LANDING_SECONDS,
            "envelope": [{"ageSeconds": s, "scale": scale_value, "opacity": opacity}
                         for s, scale_value, opacity in ENVELOPE],
            "interpolation": "Monotone, eased curves in Blender; smooth interpolation through the same envelope",
            "opacity": "textureAlpha * waterBoundsMask * clamp(contactStrength, 0, 1) * envelopeOpacity",
            "reset": "At age >= 1.8 seconds set alpha to zero and release the instance",
            "pool_preview_capacity": 12,
        },
        "review": {"contact_frame_48fps": CONTACT, "contact_points_blender_BU": anchors,
                   "stress_pairwise_layer_step_BU": STRESS_OFFSET_STEP},
    }


def inspect_video(path):
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-threads", "2", "-i", str(path),
                    "-f", "null", "-"], check=True)
    value = subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
                                   "-show_format", "-of", "json", str(path)])
    report = json.loads(value)
    streams = report["streams"]
    assert len(streams) == 1 and streams[0]["codec_type"] == "video"
    video, = streams
    assert [video["width"], video["height"]] == [852, 394]
    assert int(video["nb_read_frames"]) == len(range(FIRST, LAST + 1, 3))
    assert video["codec_name"] == "h264" and video["avg_frame_rate"] == "16/1"
    return {"source_frames_px": list(SIZE), "encoded_px": [852, 394], "padded_rows": 1,
            "decoded_frames": int(video["nb_read_frames"]), "codec": "h264",
            "preview_fps": 16, "duration_seconds": float(report["format"]["duration"]), "audio_tracks": 0}


def frame_at(scene, value):
    scene.frame_set(int(math.floor(value)), subframe=value % 1.0)


def png_pixels(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    pixels = np.empty(image.size[0] * image.size[1] * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    result = pixels.reshape((image.size[1], image.size[0], 4))
    bpy.data.images.remove(image)
    return result


def verify(args):
    delivery, output = args.verify.resolve(), args.output
    manifest = read_json(delivery / "asset_manifest.json")
    assert manifest["status"] == "needs_review"
    for file, expected in manifest["files"].items():
        assert digest(delivery / file) == expected, file
    bpy.ops.wm.open_mainfile(filepath=str(delivery / BLEND))
    assert Path(bpy.data.filepath).resolve() == delivery / BLEND
    scene = bpy.data.scenes[SCENE]
    set_scene(scene)
    assert not bpy.data.libraries and scene.camera.name == CAMERA
    assert [scene.render.resolution_x, scene.render.resolution_y] == list(SIZE)
    controls = read_json(delivery / "ripple_controls.json")
    scale = controls["game_units_per_BU"]
    camera_pos = scene.camera.location
    np.testing.assert_allclose(camera_pos,
        (0, -180 * math.cos(.48) / scale, 180 * math.sin(.48) / scale), atol=1e-6)
    assert abs(2 * math.atan(scene.camera.data.sensor_height / (2 * scene.camera.data.lens)) -
               math.radians(50)) < 1e-6
    assert scene.camera.constraints[0].type == "COPY_LOCATION"
    assert math.degrees(scene.camera.rotation_euler.y) == 0

    review_landing = sorted((o for o in scene.objects if o.name.startswith("Review impact ")),
                            key=lambda o: o.name)
    birds = sorted((o for o in scene.objects if o.name.startswith("Review goose ")), key=lambda o: o.name)
    assert len(birds) == len(review_landing) == 12 and len({o.data for o in review_landing}) == 1
    assert len({bird.data for bird in birds}) == 1
    scene.frame_set(CONTACT)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    errors, frames_in = [], []
    for i, (obj, bird) in enumerate(zip(review_landing, birds)):
        foot = lowest_foot(bird, depsgraph, foot_indices(bird))
        center = obj.matrix_world.translation
        assert abs(foot.z) < 5e-6 and center.z > foot.z
        errors.append(math.hypot(foot.x - center.x, foot.y - center.y))
        assert errors[-1] < 1e-6
        p = world_to_camera_view(scene, scene.camera, center)
        assert p.z > 0 and .02 < p.x < .98 and .02 < p.y < .98, (i, p)
    previous_scale = 0
    samples = np.arange(CONTACT - 1, CONTACT + FPS * LANDING_SECONDS + 1, .5)
    for frame in samples:
        frame_at(scene, frame)
        alpha = [o.color[3] for o in review_landing]
        scales = [o.scale[0] for o in review_landing]
        assert max(alpha) - min(alpha) < 1e-8
        assert max(scales) - min(scales) < 1e-8
        assert 0 <= max(alpha) <= 1 and scales[0] >= previous_scale - 5e-7
        if frame <= CONTACT or frame >= CONTACT + FPS * LANDING_SECONDS:
            assert max(alpha) < 1e-8, frame
        if min(alpha) >= .15:
            frames_in.append(float(frame))
        previous_scale = scales[0]
    assert len(frames_in) > 75
    # The late, fading pigment can overlap its neighbors. Separate test planes
    # carry a subpixel height offset so overlaps are evaluated without coplanar depth.
    sites = np.array([o.location.xy for o in review_landing])
    deltas = np.linalg.norm(sites[:, None] - sites[None, :], axis=2)
    spacing = float(deltas[np.triu_indices(len(sites), k=1)].min())
    effective_diameter = 2 * .42 * max(item[1] for item in ENVELOPE) * LANDING_SIZE
    assert spacing > 1.5 and spacing < effective_diameter
    delta_z = np.diff([o.location.z for o in review_landing])
    np.testing.assert_allclose(delta_z, STRESS_OFFSET_STEP, atol=2e-9)
    drift = scene.objects["Review | Ripple_Idle drift and shore mask"]
    u_socket = drift.data.materials[0].node_tree.nodes["Continuous UV drift"].inputs["Location"]
    frame_at(scene, 1)
    first = u_socket.default_value.x
    frame_at(scene, 1 + FPS * UV_PERIOD)
    assert abs(u_socket.default_value.x - first - 1) < 1e-6
    frame_at(scene, 1 + FPS * UV_PERIOD * 1.5)
    assert abs(u_socket.default_value.x % 1 - .5) < 1e-6
    still(scene, output, "roundtrip_idle_drift", CONTACT + 24)
    mask_node = next(node for node in drift.data.materials[0].node_tree.nodes
                     if node.label == "Pigment over MAT-004")
    shader_links = drift.data.materials[0].node_tree.links
    blend_output = mask_node.inputs[0].links[0].from_socket
    shader_links.remove(mask_node.inputs[0].links[0])
    mask_node.inputs[0].default_value = 0
    still(scene, output, "comparison_without_idle", CONTACT + 24)
    shader_links.new(blend_output, mask_node.inputs[0])
    drifted = png_pixels(output / "roundtrip_idle_drift.png")
    undrifted = png_pixels(output / "comparison_without_idle.png")
    idle_visible = int(np.count_nonzero(np.rint(255 * np.max(
        np.abs(drifted[..., :3] - undrifted[..., :3]), axis=2)) >= 3))
    assert idle_visible >= 200, idle_visible
    for key, rel in TEXTURES.items():
        pic = bpy.data.scenes[EXPORT_SCENE].objects[key].data.materials[0].node_tree.nodes[
            "Ripple | packed RGBA"].image
        assert bytes(pic.packed_file.data) == (delivery / rel).read_bytes()
        pixels = png_pixels(delivery / rel)
        alpha = pixels[..., 3]
        assert np.any((alpha > 0) & (alpha < .75)) and alpha.max() <= .65
        if key == IDLE:
            assert np.max(np.abs(pixels[0] - pixels[-1])) <= .01
            assert np.max(np.abs(pixels[:, 0] - pixels[:, -1])) <= .01
        else:
            assert not alpha[[0, -1]].any() and not alpha[:, [0, -1]].any()

    doc, binary = glb_contents(delivery / GLB)
    assert {node["name"] for node in doc["nodes"]} == {IDLE, LANDING}
    assert len(doc["nodes"]) == len(doc["meshes"]) == len(doc["materials"]) == 2
    assert all(m.get("alphaMode") == "BLEND" for m in doc["materials"])
    assert not doc.get("cameras") and not doc.get("animations")
    assert {digest(b) for b in glb_images(doc, binary)} == {
        digest(delivery / rel) for rel in TEXTURES.values()
    }
    clean = bpy.data.scenes.new("Independent GLB import")
    set_scene(clean)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(delivery / GLB))
    imported = {key: next(o for o in set(bpy.data.objects) - before
                          if o.name == key or o.name.startswith(key + ".")) for key in TEXTURES}
    triangle_counts = {}
    for key, obj in imported.items():
        expected_size = TILE if key == IDLE else (LANDING_SIZE, LANDING_SIZE)
        assert obj.type == "MESH" and obj.matrix_world.is_identity
        obj.data.calc_loop_triangles()
        triangle_counts[key] = len(obj.data.loop_triangles)
        assert triangle_counts[key] == 2 and len(obj.data.vertices) == 4
        assert obj.data.uv_layers.active and all(v.normal.z > .999 for v in obj.data.vertices)
        np.testing.assert_allclose([obj.dimensions.x, obj.dimensions.y, obj.dimensions.z],
                                   [*expected_size, 0], atol=1e-6)
        mat = obj.data.materials[0]
        assert mat.surface_render_method == "BLENDED"
        pic, = [n.image for n in mat.node_tree.nodes if n.type == "TEX_IMAGE"]
        assert bytes(pic.packed_file.data) == (delivery / TEXTURES[key]).read_bytes()

    # Replace the review mesh with geometry obtained from the exported GLB.
    set_scene(scene)
    original = review_landing[0].data
    imported_mesh = imported[LANDING].data
    imported_mesh.materials[0] = original.materials[0]
    for obj in review_landing:
        obj.data = imported_mesh
    still(scene, output, "roundtrip_landing_fixed_rear", 76)
    base = png_pixels(delivery / "preview_landing_fixed_rear.png")
    comparison = png_pixels(output / "roundtrip_landing_fixed_rear.png")
    delta = np.max(np.abs(base[..., :3] - comparison[..., :3]), axis=2)
    assert np.mean(delta) <= .012 and np.quantile(delta, .99) <= .05
    count = len(review_landing)
    for obj in review_landing:
        obj.hide_render = True
    still(scene, output, "comparison_without_landing", 76)
    no_fx = png_pixels(output / "comparison_without_landing.png")
    diff = np.max(np.abs(comparison[..., :3] - no_fx[..., :3]), axis=2)
    visible = int(np.count_nonzero(diff >= (4 / 255)))
    assert visible >= 350, visible
    video = None if args.skip_video_check else inspect_video(delivery / "preview_fixed_rear.mp4")
    verification = {
        "independent_reopen_from_delivery": "pass",
        "manifest_file_sha256_matches": "pass",
        "fixed_swift_rig_translation_fov_and_frame": "pass",
        "land_trigger_and_anchor_checks": {
            "status": "pass", "count": count, "half_frame_samples": len(samples),
            "max_xy_error_at_contact_BU": max(errors),
            "first_and_last_all_opacity_ge_015_frames": [frames_in[0], frames_in[-1]],
            "all_contact_centers_on_screen": "pass",
            "shared_landing_meshes": 1,
            "min_contact_spacing_BU": spacing,
            "max_visible_ring_diameter_BU": effective_diameter,
        },
        "idle_world_uv_cycle_and_rgba_wrap": "pass",
        "visible_idle_pigment_pixels_rgb_delta_ge_3_255": idle_visible,
        "glb_import_meshes_materials_axes_uvs_and_packed_PNG": {
            "status": "pass", "triangles": triangle_counts,
            "land_12_geometry_triangle_estimate": triangle_counts[LANDING] * 12,
            "note": "Offline geometry count, no mobile draw-call or performance measurement.",
        },
        "visible_landing_vs_idle_pixels_rgb_delta_ge_4_255": visible,
        "glb_render_max_channel_absolute_delta_mean_and_p99": [
            float(np.mean(delta)), float(np.quantile(delta, .99)),
        ],
        "video_decode": video,
    }
    write_json(output / "independent_verification.json", verification)


def build(args):
    output = args.output
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats, reference, scale, deps = load_inputs(args.library)
    stage = build_stage(reference, scale)
    scene, _, _, _, anchors, *_ = stage
    texture_statistics = review_build(output, stage, mats)
    controls = mapping(scale, anchors)
    write_json(output / "ripple_controls.json", controls)
    if not args.stills_only:
        timeline_video(scene, output)
    shutil.copyfile(Path(__file__).resolve(), output / Path(__file__).name)
    files = {str(path.relative_to(output)): digest(path) for path in sorted(output.rglob("*")) if path.is_file()}
    write_json(output / "asset_manifest.json", {
        "id": ID, "version": VERSION, "status": "needs_review", "blender": bpy.app.version_string,
        "source": "Project-original procedural ripples. MAT-004 and ANM-007 project context for offline review.",
        "rights": "项目原创程序化资产和项目内依赖，未引入外部素材。",
        "dependencies": deps, "axes_blender": controls["axes_blender"],
        "axes_gltf": controls["axes_gltf_and_ground"], "camera": controls["camera"],
        "master": BLEND, "export": GLB, "controls": "ripple_controls.json",
        "settings": {"GLB": "Two standalone textured cards with static pivots, no animation payload",
            "preview": "Editable rigs and shaders in the .blend, no hard-coded game state."},
        "textures": {name: {"file": rel, "color_space": "sRGB pigment + straight linear alpha",
                            "sample_mode": "repeat" if name == IDLE else "clamp",
                            **texture_statistics[name]} for name, rel in TEXTURES.items()},
        "files": files,
    })
    write_json(output / "qa.json", {"id": ID, "version": VERSION, "status": "needs_review",
       "offline_verification_status": "awaiting_independent_reopen",
       "pending": PENDING})


if __name__ == "__main__":
    arguments = parse_args()
    if arguments.verify:
        verify(arguments)
    else:
        build(arguments)
