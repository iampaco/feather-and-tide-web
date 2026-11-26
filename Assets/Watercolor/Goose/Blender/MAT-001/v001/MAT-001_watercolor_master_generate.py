"""Build MAT-001 in a fresh Blender General file.

Run in Blender's Python Console (or with blender --background --python):
    import runpy; runpy.run_path(r"/absolute/path/to/this_file.py", run_name="__main__")
The script writes beside itself, or into the empty directory after CLI '--'.
"""
from hashlib import sha256
from pathlib import Path
import json
import math
import struct
import sys
import zlib

import bpy
from mathutils import Vector
import numpy as np


SIZE = 512
VERSION = "v001"
STEM = "MAT-001_watercolor_master"
VARIANTS = {
    "DryGround": ("dry_ground", ("aa8970", "c7aa82", "e2cfab"), 0.91),
    "PlantOpaque": ("plant_opaque", ("687d6b", "a4b6a3", "c6c49e"), 0.84),
    "PlantAlpha": ("plant_alpha", ("6f866e", "a3b293", "c4c8a0"), 0.86),
    "SoftStone": ("soft_stone", ("758781", "a0ada7", "c0c9bd"), 0.93),
    "WaterFallback": ("water_fallback", ("7d9fa2", "a8c4bc", "cddad0"), 0.74),
}


def rgb(hex_value):
    return np.array([int(hex_value[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def linear_rgba(hex_value):
    channels = rgb(hex_value)
    linear = np.where(channels <= 0.04045, channels / 12.92, ((channels + 0.055) / 1.055) ** 2.4)
    return (*linear, 1.0)


def smooth(value):
    value = np.clip(value, 0, 1)
    return value * value * (3 - 2 * value)


def value_noise(rng, u, v, columns, rows):
    """Periodic value noise keeps the base washes repeatable across UV tiles."""
    grid = rng.random((rows, columns))
    x, y = u * columns, v * rows
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    tx, ty = smooth(x - ix), smooth(y - iy)
    low = grid[iy % rows, ix % columns] * (1 - tx) + grid[iy % rows, (ix + 1) % columns] * tx
    high = grid[(iy + 1) % rows, ix % columns] * (1 - tx) + grid[(iy + 1) % rows, (ix + 1) % columns] * tx
    return low * (1 - ty) + high * ty


def leaf_alpha(u, v, warp):
    """Paint curved leaf silhouettes with an antialiased straight-alpha edge."""
    stems = [
        ((0.48, 0.93), (0.45, 0.38), (0.31, 0.08), 0.033),
        ((0.51, 0.94), (0.49, 0.33), (0.65, 0.06), 0.036),
        ((0.49, 0.92), (0.39, 0.46), (0.12, 0.33), 0.029),
        ((0.54, 0.92), (0.65, 0.47), (0.87, 0.31), 0.027),
        ((0.47, 0.94), (0.34, 0.64), (0.13, 0.61), 0.021),
        ((0.56, 0.94), (0.71, 0.64), (0.89, 0.57), 0.020),
        ((0.50, 0.94), (0.55, 0.45), (0.51, 0.17), 0.024),
    ]
    edge_distance = np.full(u.shape, np.inf)
    for foot, bend, tip, width in stems:
        t = np.linspace(0, 1, 41)[:, None]
        curve = (1 - t) ** 2 * foot + 2 * (1 - t) * t * bend + t ** 2 * tip
        for i, (start, end) in enumerate(zip(curve, curve[1:])):
            dx, dy = end - start
            along = np.clip(((u - start[0]) * dx + (v - start[1]) * dy) / (dx * dx + dy * dy), 0, 1)
            progress = (i + along) / (len(curve) - 1)
            radius = width * np.sin(np.pi * progress) ** 0.75 + 0.009 * (1 - progress)
            distance = np.hypot(u - start[0] - along * dx, v - start[1] - along * dy) - radius
            edge_distance = np.minimum(edge_distance, distance)
    return 1 - smooth((edge_distance + (warp - 0.5) * 0.007 + 0.0035) / 0.007)


def write_png(path, pixels):
    height, width, channels = pixels.shape

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    header = struct.pack(">IIBBBBB", width, height, 8, {3: 2, 4: 6}[channels], 0, 0, 0)
    rows = b"".join(b"\0" + row.tobytes() for row in pixels)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"sRGB", b"\0")
        + chunk(b"IDAT", zlib.compress(rows, 8)) + chunk(b"IEND", b"")
    )


def make_texture(name, colors, seed, path):
    rng = np.random.default_rng(seed)
    axis = (np.arange(SIZE) + 0.5) / SIZE
    u, v = np.meshgrid(axis, axis)
    wash = value_noise(rng, u, v, 5, 5)
    cloud = value_noise(rng, u, v, 9, 11)
    edge = value_noise(rng, u, v, 23, 29)
    tooth = value_noise(rng, u, v, 115, 137)
    grain = rng.random(u.shape)
    pool = smooth((cloud + 0.18 * edge - 0.47) * 4.3)
    rim = np.exp(-((cloud + 0.10 * edge - 0.57) / 0.038) ** 2)
    tone = 0.16 + 0.57 * wash + 0.21 * pool - 0.055 * rim
    if name == "WaterFallback":
        stroke = value_noise(rng, u + (cloud - 0.5) * 0.10, v, 4, 28)
        broad = value_noise(rng, u, v, 3, 9)
        tone = 0.18 + 0.47 * broad + 0.19 * wash + 0.23 * smooth((stroke - 0.52) * 4.5)
    elif name == "SoftStone":
        grain_ridge = value_noise(rng, u, v + u * 2 + (wash - 0.5) * 0.12, 5, 13)
        tone += (grain_ridge - 0.5) * 0.16
    elif name == "DryGround":
        tone += (value_noise(rng, u, v, 38, 35) - 0.5) * 0.09
    dark, middle, light = map(rgb, colors)
    color = (
        middle
        + (middle - dark) * np.minimum(2 * tone - 1, 0)[..., None]
        + (light - middle) * np.maximum(2 * tone - 1, 0)[..., None]
    )
    color += ((tooth - 0.5) * 0.021 + (grain - 0.5) * 0.014)[..., None]
    if name == "PlantAlpha":
        alpha = leaf_alpha(u, v, edge)
        color = np.dstack([color, alpha])
    write_png(path, np.rint(np.clip(color, 0, 1) * 255).astype(np.uint8))


def watercolor_material(name, texture, palette, roughness):
    material = bpy.data.materials.new(name)
    material.diffuse_color = linear_rgba(palette[1])
    material.use_backface_culling = name != "PlantAlpha"
    material.surface_render_method = "BLENDED" if name == "PlantAlpha" else "DITHERED"
    nodes = material.node_tree.nodes
    nodes.clear()
    uv = nodes.new("ShaderNodeTexCoord")
    uv.location = (-610, 20)
    image = nodes.new("ShaderNodeTexImage")
    image.label = "Baked watercolor · sRGB"
    image.location = (-375, 20)
    image.image = bpy.data.images.load(str(texture), check_existing=False)
    image.image.name = texture.name
    image.image.colorspace_settings.name = "sRGB"
    image.image.alpha_mode = "STRAIGHT"
    image.image.pack()
    image.image.filepath = f"//textures/{texture.name}"
    image.extension = "EXTEND" if name == "PlantAlpha" else "REPEAT"
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (-55, 20)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = 0
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (250, 20)
    links = material.node_tree.links
    links.new(uv.outputs["UV"], image.inputs["Vector"])
    links.new(image.outputs["Color"], shader.inputs["Base Color"])
    if name == "PlantAlpha":
        links.new(image.outputs["Alpha"], shader.inputs["Alpha"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material.asset_mark()
    material.asset_data.description = "Feather & Tide / MAT-001 / Baked watercolor, glTF PBR"
    for tag in ("Feather & Tide", "Watercolor", "MAT-001"):
        material.asset_data.tags.new(tag)
    return material


def mesh_object(collection, name, material, vertices, faces, uv_for_vertex, smooth_shading=False):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        polygon.use_smooth = smooth_shading
        for loop_index in polygon.loop_indices:
            uv.data[loop_index].uv = uv_for_vertex(mesh.loops[loop_index].vertex_index)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    mesh.materials.append(material)
    return obj


def tile(collection, name, material, x, y, rx, ry, depth, seed, z=0.0):
    """Soft irregular slab with a closed bevel and planar UVs."""
    n = 56
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    radius = 1 + 0.05 * np.sin(3 * angles + seed) + 0.038 * np.cos(5 * angles + seed)
    outline = list(zip(rx * radius * np.cos(angles), ry * radius * np.sin(angles)))
    rings = [(0.91, 0), (1, depth * 0.20), (1, depth * 0.74), (0.92, depth)]
    points = [(dx * scale, dy * scale, z + height) for scale, height in rings for dx, dy in outline]
    faces = [tuple(reversed(range(n)))]
    for layer in range(len(rings) - 1):
        for i in range(n):
            j = (i + 1) % n
            faces.append((layer * n + i, layer * n + j, (layer + 1) * n + j, (layer + 1) * n + i))
    faces.append(tuple(range(3 * n, 4 * n)))
    obj = mesh_object(
        collection, name, material, points, faces,
        lambda i: (0.5 + 0.45 * points[i][0] / rx, 0.5 + 0.45 * points[i][1] / ry),
    )
    obj.location = (x, y, 0)
    return obj


def opaque_reeds(collection, material, x, y):
    rng = np.random.default_rng(387)
    vertices, faces, uv = [], [], []
    for blade in range(27):
        angle = blade * 2.39996
        radius = rng.uniform(0.01, 0.40)
        base = Vector((math.cos(angle) * radius, math.sin(angle) * radius, 0.035))
        direction = Vector((math.cos(angle), math.sin(angle), 0))
        across = Vector((-direction.y, direction.x, 0))
        height = rng.uniform(0.40, 0.84)
        lean = rng.uniform(0.18, 0.40)
        width = rng.uniform(0.037, 0.079)
        start = len(vertices)
        for i in range(8):
            t = i / 7
            point = base + direction * (lean * t ** 1.8) + Vector((0, 0, height * t))
            spread = width * (0.12 + 0.88 * math.sin(math.pi * t ** 0.7))
            for side in (-1, 0, 1):
                p = point + across * (side * spread)
                if side == 0:
                    p += direction * (spread * 0.39)
                vertices.append(p)
                uv.append((0.24 + 0.19 * (blade % 4) + side * 0.10, 0.05 + 0.9 * t))
            if i:
                b = start + (i - 1) * 3
                for side in (0, 1):
                    faces.append((b + side, b + side + 1, b + side + 4, b + side + 3))
    obj = mesh_object(collection, "PlantOpaque_Reeds", material, vertices, faces, uv.__getitem__, True)
    obj.location = (x, y, 0)
    return obj


def alpha_cards(collection, material, x, y):
    vertices, faces, uv = [], [], []
    for angle, ox, oy, size in [(-0.34, -0.31, 0.10, 0.87), (0.34, 0.29, 0.12, 0.95), (-0.12, 0, -0.12, 1.06)]:
        # Tilt toward the studio camera so both review angles expose the cutout.
        along = Vector((math.cos(angle), math.sin(angle), 0))
        rise = Vector((-math.sin(angle) * 0.48, math.cos(angle) * 0.48, 0.88))
        start = len(vertices)
        for u, v in [(0, 0), (1, 0), (1, 1), (0, 1)]:
            vertices.append(Vector((ox, oy, 0.02)) + along * ((u - 0.5) * size) + rise * (v * size))
            uv.append((u, v))
        faces.append(tuple(range(start, start + 4)))
    obj = mesh_object(collection, "PlantAlpha_LeafCards", material, vertices, faces, uv.__getitem__)
    obj.location = (x, y, 0)
    return obj


def stone(collection, material, x, y, width, length, height, seed):
    rng = np.random.default_rng(seed)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=(x, y, height * 0.35))
    obj = bpy.context.object
    obj.name = f"SoftStone_Pebble{seed}"
    for linked in list(obj.users_collection):
        linked.objects.unlink(obj)
    collection.objects.link(obj)
    for vertex in obj.data.vertices:
        a, b, c = vertex.co
        variation = 1 + 0.085 * math.sin(5 * a + 4 * b + seed) + 0.045 * math.sin(5 * c + b)
        vertex.co = (a * width * variation, b * length * variation, max(-0.34, c) * height * variation)
    obj.rotation_euler.z = rng.uniform(-0.8, 0.8)
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def collection(scene, name):
    result = bpy.data.collections.new(name)
    scene.collection.children.link(result)
    return result


def plain_material(name, color):
    material = bpy.data.materials.new(name)
    material.diffuse_color = linear_rgba(color)
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = material.diffuse_color
    shader.inputs["Roughness"].default_value = 0.94
    return material


def text_object(group, material, label, x, y, size, align="CENTER"):
    curve = bpy.data.curves.new(label, "FONT")
    curve.body = label
    curve.size = size
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.materials.append(material)
    obj = bpy.data.objects.new(label, curve)
    group.objects.link(obj)
    obj.location = (x, y, 0.003)
    return obj


def camera(group, name, position, target, scale):
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, data)
    group.objects.link(obj)
    obj.location = position
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    data.type = "ORTHO"
    data.ortho_scale = scale
    return obj


def area_light(group, name, position, energy, size):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    group.objects.link(obj)
    obj.location = position
    obj.rotation_euler = (-obj.location).to_track_quat("-Z", "Y").to_euler()


def studio(scene):
    group = collection(scene, "Preview studio · excluded from GLB")
    paper = plain_material("Studio_Paper", "e8e3d7")
    ink = plain_material("Studio_Ink", "344740")
    secondary = plain_material("Studio_SecondaryInk", "65736b")
    plane = [(-200, -200, -0.025), (200, -200, -0.025), (200, 200, -0.025), (-200, 200, -0.025)]
    mesh_object(group, "Studio_Backdrop", paper, plane, [(0, 1, 2, 3)], lambda i: (0, 0))
    text_object(group, secondary, "FEATHER & TIDE    /    MATERIAL LIBRARY", -3.65, 3.21, 0.125, "LEFT")
    text_object(group, ink, "Watercolor surfaces", -3.65, 2.81, 0.34, "LEFT")
    text_object(group, secondary, "MAT-001  /  V001", 3.65, 3.17, 0.123, "RIGHT")
    mesh_object(
        group, "Studio_Rule", secondary,
        [(-3.65, 2.55, 0.001), (3.65, 2.55, 0.001), (3.65, 2.563, 0.001), (-3.65, 2.563, 0.001)],
        [(0, 1, 2, 3)], lambda i: (0, 0),
    )
    for title, sub, x, y in [
        ("Dry ground", "Warm earth", -2.45, 0.28),
        ("Opaque plant", "Reed geometry", 0, 0.28),
        ("Alpha plant", "Leaf cards", 2.45, 0.28),
        ("Soft stone", "Cool mineral wash", -1.22, -2.02),
        ("Water fallback", "Matte shallow water", 1.22, -2.19),
    ]:
        text_object(group, ink, title, x, y, 0.20)
        text_object(group, secondary, sub, x, y - 0.25, 0.128)

    area_light(group, "Neutral key", (-3, -4, 7), 880, 5.5)
    area_light(group, "Neutral fill", (4, 2, 6), 415, 5.0)
    iso = camera(group, "Preview / oblique", (0, -6.7, 10.0), (0, 0.45, 0.08), 8.8)
    top = camera(group, "Preview / top", (0, 0.48, 10), (0, 0.48, 0), 8.8)
    top.rotation_euler = (0, 0, 0)
    scene.camera = iso

    scene.world = bpy.data.worlds.new("Neutral studio")
    scene.world.node_tree.nodes.get("Background").inputs["Color"].default_value = (0.55, 0.55, 0.55, 1)
    scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.40
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 20
    scene.cycles.use_denoising = True
    scene.cycles.transparent_max_bounces = 8
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = 1440
    scene.render.resolution_y = 984
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    return iso, top


def read_glb(path):
    payload = path.read_bytes()
    signature, version, length = struct.unpack_from("<4sII", payload)
    assert (signature, version, length) == (b"glTF", 2, len(payload)), "Invalid GLB header"
    json_length, chunk_type = struct.unpack_from("<I4s", payload, 12)
    assert chunk_type == b"JSON", "Missing GLB JSON chunk"
    return json.loads(payload[20:20 + json_length])


def triangle_counts(objects):
    counts = {}
    for obj in objects:
        obj.data.calc_loop_triangles()
        counts[obj.name] = len(obj.data.loop_triangles)
        assert obj.data.uv_layers.active
        assert all(abs(value - 1) < 1e-5 for value in obj.scale)
        for triangle in obj.data.loop_triangles:
            a, b, c = (obj.data.vertices[index].co for index in triangle.vertices)
            assert (b - a).cross(c - a).length > 1e-8, f"Degenerate triangle in {obj.name}"
    return counts


def verify_glb(path, objects):
    document = read_glb(path)
    materials = {material["name"]: material for material in document["materials"]}
    assert set(materials) == set(VARIANTS)
    assert len(document["images"]) == len(VARIANTS)
    assert all(image["mimeType"] == "image/png" and "bufferView" in image for image in document["images"])
    assert not document.get("extensionsRequired") and not document.get("animations")
    assert len(document["meshes"]) == len(objects) and not document.get("cameras")
    for name, material in materials.items():
        pbr = material["pbrMetallicRoughness"]
        assert "baseColorTexture" in pbr and pbr.get("metallicFactor") == 0
        assert abs(pbr["roughnessFactor"] - VARIANTS[name][2]) < 1e-5
        assert material.get("alphaMode", "OPAQUE") == ("BLEND" if name == "PlantAlpha" else "OPAQUE")
        assert material.get("doubleSided", False) == (name in {"PlantAlpha", "PlantOpaque"})
    return document


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render(scene, camera_obj, path):
    scene.camera = camera_obj
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True, scene=scene.name)


def round_trip(scene, path, original_objects, camera_obj, output):
    window = bpy.context.window
    imported_scene = bpy.data.scenes.new("MAT-001 round-trip")
    window.scene = imported_scene
    # Reuse the exact neutral studio so the comparison isolates export/import.
    preview_group = next(group for group in scene.collection.children if group.name.startswith("Preview studio"))
    imported_scene.collection.children.link(preview_group)
    imported_scene.world = scene.world
    imported_scene.render.engine = scene.render.engine
    imported_scene.cycles.device = "CPU"
    imported_scene.cycles.samples = scene.cycles.samples
    imported_scene.cycles.use_denoising = True
    imported_scene.cycles.transparent_max_bounces = 8
    imported_scene.view_settings.view_transform = scene.view_settings.view_transform
    imported_scene.render.resolution_x = scene.render.resolution_x
    imported_scene.render.resolution_y = scene.render.resolution_y
    imported_scene.render.resolution_percentage = 100
    imported_scene.render.image_settings.file_format = "PNG"
    imported_scene.render.image_settings.color_mode = "RGB"
    existing = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj not in existing and obj.type == "MESH"]
    assert len(imported) == len(original_objects)
    originals = {obj.name: obj for obj in original_objects}
    bounds_error = 0.0
    for obj in imported:
        base_name = obj.name.rsplit(".", 1)[0]
        original = originals[base_name]
        assert obj.data.uv_layers.active and obj.data.materials[0]
        assert obj.data.materials[0].name.rsplit(".", 1)[0] == original.data.materials[0].name
        for axis in range(3):
            # A glTF importer can bake object rotation into the vertices; compare world bounds.
            actual_vertices = [(obj.matrix_world @ v.co)[axis] for v in obj.data.vertices]
            expected_vertices = [(original.matrix_world @ v.co)[axis] for v in original.data.vertices]
            bounds_error = max(bounds_error, abs(min(actual_vertices) - min(expected_vertices)),
                               abs(max(actual_vertices) - max(expected_vertices)))
    assert bounds_error < 1e-4
    alpha = next(obj for obj in imported if obj.name.startswith("PlantAlpha")).data.materials[0]
    shader = next(node for node in alpha.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    assert shader.inputs["Alpha"].is_linked
    render(imported_scene, camera_obj, output)
    window.scene = scene
    bpy.data.scenes.remove(imported_scene)
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
    return round(bounds_error, 7)


def main(output):
    window = bpy.context.window
    initial_scene = window.scene
    fresh = not bpy.data.filepath and set(initial_scene.objects.keys()) <= {"Camera", "Cube", "Light"}
    previous_mat = initial_scene.get("asset_id") == "MAT-001" and Path(bpy.data.filepath).name == f"{STEM}.blend"
    assert len(bpy.data.scenes) == 1 and (fresh or previous_mat), (
        "Start with a fresh General file or a saved MAT-001 source."
    )
    output.mkdir(parents=True, exist_ok=True)
    texture_dir = output / "textures"
    assert not texture_dir.exists() and not (output / f"{STEM}.blend").exists(), "Use a fresh version directory."
    texture_dir.mkdir()
    scene = bpy.data.scenes.new("MAT-001 | Watercolor surfaces")
    window.scene = scene
    bpy.data.scenes.remove(initial_scene)
    for material in list(bpy.data.materials):
        if material.asset_data and any(tag.name == "MAT-001" for tag in material.asset_data.tags):
            bpy.data.materials.remove(material, do_unlink=True)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
    scene.name = "MAT-001 | Watercolor surfaces"
    scene["asset_id"] = "MAT-001"
    scene["asset_version"] = VERSION

    samples = collection(scene, "MAT-001 samples · export")
    materials = {}
    texture_files = {}
    for i, (name, (slug, palette, roughness)) in enumerate(VARIANTS.items()):
        file = texture_dir / f"ft_goose_mat_{slug}_basecolor.png"
        make_texture(name, palette, 20261113 + i, file)
        materials[name] = watercolor_material(name, file, palette, roughness)
        texture_files[name] = file
    materials["PlantOpaque"].use_backface_culling = False

    tile(samples, "DryGround_Tile", materials["DryGround"], -2.45, 1.28, 0.90, 0.65, 0.16, 4)
    opaque_reeds(samples, materials["PlantOpaque"], 0, 1.28)
    alpha_cards(samples, materials["PlantAlpha"], 2.45, 1.28)
    for x, y, w, l, h, seed in [
        (-1.43, -1.05, 0.55, 0.40, 0.43, 12),
        (-0.93, -1.36, 0.34, 0.28, 0.23, 17),
        (-1.78, -1.50, 0.20, 0.17, 0.14, 23),
    ]:
        stone(samples, materials["SoftStone"], x, y, w, l, h, seed)
    tile(samples, "WaterFallback_Pool", materials["WaterFallback"], 1.22, -1.19, 0.97, 0.66, 0.071, 7)

    iso, top = studio(scene)
    objects = list(samples.objects)
    bpy.context.view_layer.update()
    counts = triangle_counts(objects)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]

    glb = output / f"{STEM}.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(glb), export_format="GLB", use_selection=True,
        export_yup=True, export_materials="EXPORT",
    )
    gltf = verify_glb(glb, objects)
    bpy.ops.object.select_all(action="DESELECT")
    source = output / f"{STEM}.blend"
    scene.render.filepath = "//"
    scene.camera = iso
    scene["units"] = "Blender units; preview geometry has no runtime scale contract"
    readme = bpy.data.texts.new("MAT-001 usage")
    readme.write(
        "Append any of the five marked material assets into your .blend.\n"
        "Assign the material to a UV-mapped mesh. PlantAlpha uses straight RGBA; all other maps are RGB.\n"
        "To recolor, replace the sRGB Base Color image or regenerate the palette with the bundled script.\n"
        "Render cameras: Preview / oblique and Preview / top. The studio is excluded from the GLB.\n"
    )
    if bpy.context.area and bpy.context.area.type == "CONSOLE":
        bpy.context.area.type = "VIEW_3D"
    # Open the saved library at the sample board with alpha and textures visible.
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.region_3d.view_perspective = "CAMERA"
                    space.overlay.show_overlays = False
                    space.shading.type = "MATERIAL"

    # Save before rendering so the editable source exists independently of render completion.
    bpy.ops.wm.save_as_mainfile(filepath=str(source), compress=True)
    render(scene, iso, output / "preview_iso.png")
    render(scene, top, output / "preview_top.png")
    roundtrip_preview = output / "preview_glb_roundtrip.png"
    error = round_trip(scene, glb, objects, iso, roundtrip_preview)
    scene.camera = iso
    scene.render.filepath = "//"

    files = [
        source, glb, Path(__file__), output / "preview_iso.png", output / "preview_top.png",
        roundtrip_preview, *texture_files.values(),
    ]
    write_json(output / "asset_manifest.json", {
        "id": "MAT-001", "name": "通用水彩材质母版", "version": VERSION,
        "depends": [], "blender": bpy.app.version_string,
        "source": "程序化原创贴图和几何，依据 Blender 制作规格书 v1.0 第 5 页；未使用外部图片或扩展。",
        "export": {"format": "glTF 2.0 binary", "coordinate_system": "Y up; Blender +Y maps to glTF -Z",
                   "geometry": "仅材质样块", "normals": "网格顶点法线", "normal_map": None, "orm_map": None},
        "textures": {
            name: {"path": file.relative_to(output).as_posix(), "size": [SIZE, SIZE],
                   "color_space": "sRGB", "alpha": "straight" if name == "PlantAlpha" else None,
                   "palette_srgb": [f"#{value.upper()}" for value in VARIANTS[name][1]],
                   "roughness": VARIANTS[name][2], "metallic": 0}
            for name, file in texture_files.items()
        },
        "objects": counts, "triangles_total": sum(counts.values()),
        "actions": [],
        "files": {file.name if file == Path(__file__) else file.relative_to(output).as_posix():
                  sha256(file.read_bytes()).hexdigest() for file in files},
    })
    write_json(output / "qa.json", {
        "id": "MAT-001", "version": VERSION, "status": "technical_pass_visual_review_pending",
        "automated_checks": {
            "five_asset_materials": "pass", "nondegenerate_triangles_uvs_unit_scale": "pass",
            "pbr_parameters_embedded_png_alpha_modes": "pass",
            "glb_import_objects_materials_alpha_socket": "pass",
            "glb_import_max_world_bounds_error_bu": error,
            "embedded_pngs": len(gltf["images"]),
        },
        "visual_checks_pending": ["中性光下水彩色阶、纸纹与透明边缘", "两视角及 GLB 回导渲染对照"],
        "runtime": "Blender 素材样板，尚待项目美术确认；RealityKit / iPhone / iPad 未验证。",
    })
    print(f"MAT-001 complete: {output}", flush=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(Path(args[0]).resolve() if args else Path(__file__).resolve().parent)
