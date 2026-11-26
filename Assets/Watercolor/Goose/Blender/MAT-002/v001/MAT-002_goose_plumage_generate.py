"""Build the MAT-002 plumage study using Blender 5.2 and MAT-001/v001.

Use: blender --background --factory-startup --python this_file.py -- /empty/output
"""
from hashlib import sha256
import json
import math
from pathlib import Path
import runpy
import struct
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np


HERE = Path(__file__).resolve().parent
MASTER = HERE.parents[1] / "MAT-001" / "v001"
MASTER_BLEND = MASTER / "MAT-001_watercolor_master.blend"
MASTER_SCRIPT = MASTER / "MAT-001_watercolor_master_generate.py"
recipe = runpy.run_path(str(MASTER_SCRIPT))
SIZE = 1024
STEM = "MAT-002_goose_plumage"
PALETTES = {
    "Head": ("cfc1a7", "e3dac4", "f1e9d7"),
    "Body": ("87817b", "a79e91", "c5baaa"),
    "FlightFeather": ("393635", "55504d", "736c64"),
    "BillFeet": ("935735", "bd7e4b", "d59b63"),
}
ROUGHNESS = {"Head": 0.88, "Body": 0.90, "FlightFeather": 0.91, "BillFeet": 0.80}
LEADER_TINT = (1.0, 0.976, 0.925, 1.0)
BAR_CENTERS = (0.598, 0.827)
BAR_WIDTHS = (0.037, 0.037)
HEAD_CENTER = (0, 0.323, 0.224)
HEAD_RADII = (0.108, 0.132, 0.135)
# This temporary proxy is mapped to the existing leader marker for camera review.
FLIGHT_LENGTH = 0.937
GAME_SCALE = (22.0 * 1.25) / FLIGHT_LENGTH
GAME_WIDTH, GAME_HEIGHT = 852, 393


def wash_texture(part, seed, path):
    rng = np.random.default_rng(seed)
    axis = (np.arange(SIZE) + 0.5) / SIZE
    u, v = np.meshgrid(axis, axis)
    noise, smooth = recipe["value_noise"], recipe["smooth"]
    broad = noise(rng, u, v, 5, 5)
    cloud = noise(rng, u, v, 9, 11)
    edge = noise(rng, u, v, 23, 29)
    tooth = noise(rng, u, v, 115, 137)
    grain = rng.random(u.shape)
    pool = smooth((cloud + 0.18 * edge - 0.47) * 4.3)
    rim = np.exp(-((cloud + 0.10 * edge - 0.57) / 0.038) ** 2)
    tone = 0.16 + 0.57 * broad + 0.21 * pool - 0.055 * rim
    if part == "FlightFeather":
        tone += (noise(rng, u, v, 19, 5) - 0.5) * 0.20
    dark, mid, light = map(recipe["rgb"], PALETTES[part])
    color = mid + (mid - dark) * np.minimum(2 * tone - 1, 0)[..., None]
    color += (light - mid) * np.maximum(2 * tone - 1, 0)[..., None]
    if part == "Head":
        crown = np.cos(2 * np.pi * u)
        spans = (0.0, -0.14)
        for center, width, span in zip(BAR_CENTERS, BAR_WIDTHS, spans):
            curve = center - (0.036 + 0.06 * (center - 0.60)) * (1 - crown)
            soft_edge = (edge - 0.5) * 0.008
            band = 1 - smooth((np.abs(v - curve + soft_edge) - width) / 0.012)
            band *= smooth((crown - span + (edge - 0.5) * 0.05) / 0.21)
            pigment = recipe["rgb"]("393632") + (cloud - 0.50)[..., None] * 0.074
            color = color * (1 - band[..., None]) + pigment * band[..., None]
    # Match the approved MAT-001 tooth and fine-grain amplitudes.
    color += ((tooth - 0.5) * 0.021 + (grain - 0.5) * 0.014)[..., None]
    recipe["write_png"](path, np.rint(np.clip(color, 0, 1) * 255).astype(np.uint8))


def make_material(template, name, part, image):
    material = template.copy()
    material.name = name
    material.asset_clear()
    material.asset_mark()
    material.asset_data.description = f"Feather & Tide / MAT-002 / {part}, from MAT-001 v001"
    for tag in ("Feather & Tide", "Watercolor", "MAT-002"):
        material.asset_data.tags.new(tag)
    material.diffuse_color = recipe["linear_rgba"](PALETTES[part][1])
    material.use_backface_culling = True
    shader = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    shader.inputs["Roughness"].default_value = ROUGHNESS[part]
    texture = next(n for n in material.node_tree.nodes if n.type == "TEX_IMAGE")
    texture.image = image
    texture.label = "Plumage watercolor · baked sRGB"
    return material


def materials(output):
    with bpy.data.libraries.load(str(MASTER_BLEND), link=False) as (source, target):
        assert "DryGround" in source.materials
        target.materials = ["DryGround"]
    template, = target.materials
    texture_dir = output / "textures"
    texture_dir.mkdir()
    files, result = {}, {}
    names = {"Head": "Head", "Body": "Body_Follower", "FlightFeather": "FlightFeather", "BillFeet": "BillFeet"}
    for index, part in enumerate(PALETTES):
        file = texture_dir / f"ft_goose_mat_{part.lower()}_basecolor.png"
        wash_texture(part, 20261114 + index, file)
        image = bpy.data.images.load(str(file), check_existing=False)
        image.colorspace_settings.name = "sRGB"
        image.pack()
        image.filepath = f"//textures/{file.name}"
        files[part] = file
        result[part] = make_material(template, names[part], part, image)
    leader = make_material(template, "Body_Leader", "Body", next(
        node.image for node in result["Body"].node_tree.nodes if node.type == "TEX_IMAGE"
    ))
    tree = leader.node_tree
    texture = next(n for n in tree.nodes if n.type == "TEX_IMAGE")
    shader = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    mix = tree.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.label = "Leader tint · glTF Base Color Factor"
    mix.location = (-105, 60)
    mix.inputs[0].default_value = 1
    mix.inputs[7].default_value = LEADER_TINT
    tree.links.new(texture.outputs["Color"], mix.inputs[6])
    tree.links.new(mix.outputs[2], shader.inputs["Base Color"])
    shader.location.x = 140
    next(n for n in tree.nodes if n.type == "OUTPUT_MATERIAL").location.x = 440
    result["Leader"] = leader
    result["FlightFeather"].use_backface_culling = False
    bpy.data.materials.remove(template, do_unlink=True)
    return result, files


def mesh(group, name, material, vertices, faces, uv_faces):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    uv = data.uv_layers.new(name="UVMap")
    for polygon, coords in zip(data.polygons, uv_faces):
        polygon.use_smooth = True
        for index, coord in zip(polygon.loop_indices, coords):
            uv.uv[index].vector = coord
    obj = bpy.data.objects.new(name, data)
    group.objects.link(obj)
    data.materials.append(material)
    return obj


def tube(group, name, material, rings, segments):
    """Lay out UV seam at the crown, with U wrapping and V along the flight axis."""
    vertices, faces, uvs = [], [], []
    for y, z, half_width, half_height in rings:
        for side in range(segments):
            a = 2 * math.pi * side / segments
            vertices.append((half_width * math.sin(a), y, z + half_height * math.cos(a)))
    for row in range(len(rings) - 1):
        v0, v1 = row / (len(rings) - 1), (row + 1) / (len(rings) - 1)
        for side in range(segments):
            s = (side + 1) % segments
            a = row * segments
            faces.append((a + side, a + s, a + s + segments, a + side + segments))
            u0, u1 = side / segments, (side + 1) / segments
            uvs.append(((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
    for row, reverse in ((0, True), (len(rings) - 1, False)):
        sides = list(range(segments))
        if reverse:
            sides.reverse()
        faces.append(tuple(row * segments + side for side in sides))
        uvs.append(tuple((side / segments, row / (len(rings) - 1)) for side in sides))
    return mesh(group, name, material, vertices, faces, uvs)


def ellipsoid(group, name, material, center, radii, segments, layers):
    x, y, z = center
    a, b, c = radii
    latitudes = np.linspace(math.pi - 0.027, 0.027, layers)
    rings = [(y + b * math.cos(t), z, a * math.sin(t), c * math.sin(t)) for t in latitudes]
    obj = tube(group, name, material, rings, segments)
    obj.location.x = x
    return obj


def feather_fan(group, material):
    vertices, faces, uvs = [], [], []
    for side in (-1, 1):
        for feather in range(8):
            progress = feather / 7
            start = Vector((side * (0.22 + 0.38 * progress), -0.037 - 0.04 * progress, 0.011))
            end = Vector((side * (0.31 + 0.50 * progress), -0.255 + 0.015 * progress, 0.007 + 0.057 * progress))
            along = (end - start).normalized()
            cross = Vector((-along.y, along.x, 0))
            start_index = len(vertices)
            for index in range(7):
                t = index / 6
                point = start.lerp(end, t)
                span = (0.005 + 0.033 * math.sin(math.pi * t ** 0.7))
                vertices.extend((point - cross * span, point + cross * span))
            for index in range(6):
                offset = start_index + index * 2
                a, b = index / 6, (index + 1) / 6
                faces.append((offset, offset + 2, offset + 3, offset + 1))
                u = 0.1 + feather * 0.10
                uvs.append(((u, a), (u, b), (u + 0.07, b), (u + 0.07, a)))
    obj = mesh(group, "FlightFeather_WingTips", material, vertices, faces, uvs)
    return obj


def proxy(group, mats):
    body = ellipsoid(group, "Body_Proxy", mats["Leader"], (0, -0.081, 0), (0.147, 0.291, 0.093), 24, 17)
    head = ellipsoid(group, "Head_Proxy", mats["Head"], HEAD_CENTER, HEAD_RADII, 40, 33)
    tube(group, "Neck_Proxy", mats["Leader"], [
        (0.00, 0.01, 0.106, 0.070),
        (0.07, 0.04, 0.096, 0.065),
        (0.13, 0.083, 0.074, 0.059),
        (0.18, 0.129, 0.063, 0.053),
        (0.22, 0.175, 0.061, 0.049),
        (0.27, 0.210, 0.066, 0.045),
        (0.31, 0.224, 0.065, 0.041),
    ], 20)
    tube(group, "Bill_Proxy", mats["BillFeet"], [
        (0.406, 0.206, 0.053, 0.034), (0.445, 0.201, 0.051, 0.030),
        (0.50, 0.192, 0.037, 0.023), (0.531, 0.185, 0.017, 0.013),
        (0.537, 0.184, 0.005, 0.004),
    ], 16)
    tube(group, "Tail_Proxy", mats["FlightFeather"], [
        (-0.400, -0.018, 0.031, 0.010), (-0.366, -0.018, 0.065, 0.018),
        (-0.295, -0.011, 0.075, 0.028), (-0.251, -0.003, 0.078, 0.028),
    ], 18)
    for side, label in [(-1, "L"), (1, "R")]:
        eye = ellipsoid(group, f"Eye_{label}", mats["FlightFeather"],
                        (side * 0.095, 0.365, 0.249), (0.010, 0.014, 0.012), 12, 9)
        foot = ellipsoid(group, f"Foot_{label}", mats["BillFeet"],
                         (side * 0.070, -0.238, -0.071), (0.029, 0.056, 0.016), 14, 9)
        wing = ellipsoid(group, f"Body_Wing{label}", mats["Leader"],
                         (side * 0.225, -0.064, 0.022), (0.233, 0.111, 0.033), 22, 15)
        wing.rotation_euler.z = side * -0.26
        eye["purpose"] = "Color proxy"
        foot["purpose"] = "Color proxy"
    feather_fan(group, mats["FlightFeather"])
    return body, head


def aimed_camera(group, name, eye, target, field):
    data = bpy.data.cameras.new(name)
    data.sensor_fit = "VERTICAL"
    data.sensor_height = 24
    data.lens = 12 / math.tan(math.radians(field) / 2)
    data.clip_end = 1500
    obj = bpy.data.objects.new(name, data)
    group.objects.link(obj)
    obj.location = eye
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def setup_studio(scene):
    group = recipe["collection"](scene, "Preview cameras and lights")
    scene.world = bpy.data.worlds.new("Neutral plumage studio")
    scene.world.node_tree.nodes.get("Background").inputs["Color"].default_value = (0.37, 0.37, 0.37, 1)
    scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.70
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = "AgX"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    sun = bpy.data.lights.new("Neutral key", "SUN")
    sun.energy = 1.65
    sun.angle = 0.29
    key = bpy.data.objects.new(sun.name, sun)
    group.objects.link(key)
    key.rotation_euler = Vector((0.58, 0.72, -1.0)).to_track_quat("-Z", "Y").to_euler()
    ground = recipe["plain_material"]("Wetland gray-green backdrop", "93a99c")
    recipe["mesh_object"](group, "Review Ground", ground,
                          [(-600, -600, 0), (600, -600, 0), (600, 600, 0), (-600, 600, 0)],
                          [(0, 1, 2, 3)], lambda i: (0, 0))
    return group, key


def resize(scene, width, height):
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100


def game_cameras(group):
    eye = (0, -180 * math.cos(0.48), 180 * math.sin(0.48))
    aim = (0, 0, 6)
    game = aimed_camera(group, "Gameplay | graybox perspective", eye, aim, 50)
    close = aimed_camera(group, "Review | rear detail", (0, -52, 38), (0, -0.5, 11), 39)
    top = aimed_camera(group, "Review | crown top", (0, 0, 60), (0, 0, 8), 43)
    top.rotation_euler = (0, 0, 0)
    return game, close, top


def apply_proxy_scale(objects, scale, elevation):
    # Scale mesh coordinates once so the saved and exported objects use unit scale.
    for obj in objects:
        for vert in obj.data.vertices:
            vert.co *= scale
        obj.data.update()
        obj.location = (obj.location.x * scale, 0, elevation)


def export_proxy(objects, output):
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    glb = output / f"{STEM}.glb"
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True, export_yup=True)
    document = recipe["read_glb"](glb)
    materials = {item["name"]: item["pbrMetallicRoughness"] for item in document["materials"]}
    assert set(materials) == {"Head", "Body_Leader", "FlightFeather", "BillFeet"}, sorted(materials)
    assert len(document["images"]) == 4 and len(document["meshes"]) == len(objects)
    assert not document.get("extensionsRequired") and not document.get("cameras")
    assert all(image.get("mimeType") == "image/png" and "bufferView" in image for image in document["images"])
    assert all("baseColorTexture" in pbr and pbr["metallicFactor"] == 0 for pbr in materials.values())
    assert np.allclose(materials["Body_Leader"]["baseColorFactor"], LEADER_TINT)
    for obj in objects:
        obj.select_set(False)
    return glb


def project_head(scene, camera, scale):
    def sample(t):
        angle = math.pi * t
        return Vector((0, (HEAD_CENTER[1] + HEAD_RADII[1] * math.cos(angle)) * scale,
                       8 + (HEAD_CENTER[2] + HEAD_RADII[2] * math.sin(angle)) * scale))

    def pixel(t):
        p = world_to_camera_view(scene, camera, sample(t))
        return round(p.x * GAME_WIDTH - 0.5, 2), round((1 - p.y) * GAME_HEIGHT - 0.5, 2)

    return {label: pixel(t) for label, t in {
        "front_white": 0.52, "bar_1": BAR_CENTERS[0], "white_gap": 0.715,
        "bar_2": BAR_CENTERS[1], "rear_white": 0.905,
    }.items()}


def check_import(glb, objects, group, world, camera, output):
    scene = bpy.context.scene
    window = bpy.context.window
    imported_scene = bpy.data.scenes.new("MAT-002 GLB roundtrip")
    window.scene = imported_scene
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    assert len(imported) == len(objects)
    originals = {obj.name: obj for obj in objects}
    error = 0.0
    for obj in imported:
        original = originals[obj.name.rsplit(".", 1)[0]]
        assert obj.data.uv_layers.active
        assert obj.data.materials[0].name.rsplit(".", 1)[0] == original.data.materials[0].name
        for axis in range(3):
            source = [(original.matrix_world @ v.co)[axis] for v in original.data.vertices]
            target = [(obj.matrix_world @ v.co)[axis] for v in obj.data.vertices]
            error = max(error, abs(min(source) - min(target)), abs(max(source) - max(target)))
    assert error < 1e-4
    imported_scene.collection.children.link(group)
    imported_scene.world = world
    imported_scene.render.engine = "CYCLES"
    imported_scene.cycles.device = "CPU"
    imported_scene.cycles.samples = scene.cycles.samples
    imported_scene.cycles.use_denoising = True
    imported_scene.view_settings.view_transform = scene.view_settings.view_transform
    imported_scene.render.image_settings.color_mode = "RGB"
    resize(imported_scene, 1440, 960)
    recipe["render"](imported_scene, camera, output / "preview_glb_roundtrip.png")
    window.scene = scene
    bpy.data.scenes.remove(imported_scene)
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    return round(error, 7)


def main(output):
    window = bpy.context.window
    initial = window.scene
    assert not bpy.data.filepath and set(initial.objects.keys()) <= {"Camera", "Cube", "Light"}, (
        "Use a fresh General scene."
    )
    output.mkdir(parents=True, exist_ok=True)
    assert not (output / "textures").exists() and not (output / f"{STEM}.blend").exists()
    scene = bpy.data.scenes.new("MAT-002 | Goose plumage")
    window.scene = scene
    bpy.data.scenes.remove(initial)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
    group = recipe["collection"](scene, "MAT-002 | Simplified goose sample")
    mats, texture_files = materials(output)
    body, head = proxy(group, mats)
    objects = list(group.objects)
    apply_proxy_scale(objects, GAME_SCALE, 8.0)
    studio, key = setup_studio(scene)
    game, close, top = game_cameras(studio)
    bpy.context.view_layer.update()
    counts = recipe["triangle_counts"](objects)
    glb = export_proxy(objects, output)
    scene["asset_id"] = "MAT-002"
    scene["dependency"] = "MAT-001/v001"
    scene["proxy_units"] = "Temporary graybox game scale, not final model dimensions"
    body["material_alternative"] = "Body_Follower (same PNG, no tint)"
    head["uv_note"] = "Crown seam at U=0/1; V runs from rear to front. See asset_manifest.json."
    scene.camera = close
    resize(scene, 1440, 960)
    scene.render.filepath = "//"
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.region_3d.view_perspective = "CAMERA"
                space.region_3d.view_camera_zoom = 16
                space.overlay.show_overlays = False
                space.shading.type = "MATERIAL"
    source = output / f"{STEM}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(source), compress=True)

    recipe["render"](scene, close, output / "preview_rear_detail.png")
    recipe["render"](scene, top, output / "preview_top.png")
    error = check_import(glb, objects, studio, scene.world, close, output)
    resize(scene, GAME_WIDTH, GAME_HEIGHT)
    projected = {"1x": project_head(scene, game, GAME_SCALE), "0.5x": project_head(scene, game, GAME_SCALE / 2)}
    recipe["render"](scene, game, output / "preview_gameplay_1x.png")
    key.data.color = (0.79, 0.88, 1.0)
    key.data.energy = 1.08
    recipe["render"](scene, game, output / "preview_gameplay_cool.png")
    key.data.color = (1, 1, 1)
    key.data.energy = 1.65
    for obj in objects:
        obj.scale = (0.5, 0.5, 0.5)
        obj.location.x *= 0.5
    recipe["render"](scene, game, output / "preview_gameplay_half.png")
    for obj in objects:
        obj.scale = (1, 1, 1)
        obj.location.x *= 2

    files = [source, glb, *sorted(output.glob("preview_*.png")), *texture_files.values()]
    sha = lambda path: sha256(path.read_bytes()).hexdigest()
    recipe["write_json"](output / "asset_manifest.json", {
        "id": "MAT-002", "version": "v001", "depends": ["MAT-001/v001"], "blender": bpy.app.version_string,
        "source": "原创程序化羽色、简化雁形和布光。复用 MAT-001/v001 的 DryGround 节点与水彩噪声工具。",
        "dependency_hashes": {MASTER_BLEND.name: sha(MASTER_BLEND), MASTER_SCRIPT.name: sha(MASTER_SCRIPT)},
        "materials": {part: {"png": file.relative_to(output).as_posix(), "size": [SIZE, SIZE], "color_space": "sRGB",
                             "palette_srgb": [f"#{c.upper()}" for c in PALETTES[part]],
                             "roughness": ROUGHNESS[part], "metallic": 0}
                      for part, file in texture_files.items()},
        "variants": {"Leader": {"body": "Body_Leader", "linear_tint": LEADER_TINT},
                     "Follower": {"body": "Body_Follower", "linear_tint": [1, 1, 1, 1]}},
        "objects": counts,
        "gameplay_review": {
            "reference": "ThirdPersonRig.graybox / PlayfieldView leader marker",
            "camera_distance_game_units": 180, "camera_pitch_radians": 0.48, "vertical_fov_degrees": 50,
            "target_height": 6, "leader_height": 8, "leader_proxy_length_game_units": 27.5,
            "canvas_px": [GAME_WIDTH, GAME_HEIGHT], "projected_band_samples_px": projected,
        },
        "files": {**{file.relative_to(output).as_posix(): sha(file) for file in files}, Path(__file__).name: sha(Path(__file__))},
    })
    recipe["write_json"](output / "qa.json", {
        "id": "MAT-002", "version": "v001", "status": "needs_review",
        "checks": {"source_uv_non_degenerate_unit_scale": "pass", "pbr_glb_four_embedded_textures": "pass",
                   "glb_roundtrip_max_bounds_error": error, "leader_tint_exported": "pass"},
        "visual_review": "待复核渲染",
    })


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(Path(args[0]).resolve() if args else HERE)
