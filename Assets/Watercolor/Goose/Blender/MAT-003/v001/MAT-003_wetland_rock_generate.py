"""Make the MAT-003 seamless terrain material library in Blender 5.2.

blender --background --factory-startup --python this_file.py -- /empty/output
"""
from hashlib import sha256
import math
from pathlib import Path
import runpy
import sys

import bpy
from mathutils import Vector
import numpy as np


HERE = Path(__file__).resolve().parent
MASTER = HERE.parents[1] / "MAT-001" / "v001"
MASTER_BLEND = MASTER / "MAT-001_watercolor_master.blend"
MASTER_SCRIPT = MASTER / "MAT-001_watercolor_master_generate.py"
recipe = runpy.run_path(str(MASTER_SCRIPT))
SIZE = 1024
STEM = "MAT-003_wetland_rock"
SURFACES = {
    "GrassFlat": ("Sage grass flat", ("879478", "a4ad8b", "c0c29e"), 0.94),
    "MudBank": ("Silt bank", ("95806b", "ac967e", "c4ac8d"), 0.95),
    "MossStone": ("Moss stone", ("7d8b80", "9da69b", "bdc2af"), 0.94),
    "MountainRock": ("Mountain rock", ("7b8d95", "9baab0", "bdc6c5"), 0.96),
    "ShallowMargin": ("Shallow margin", ("91aaa1", "a8bbb0", "c4cbbb"), 0.89),
}


def wash(part, colors, path, seed):
    """Sample periodic pigment pools in a warped UV domain."""
    noise, smooth, rgb = (recipe[name] for name in ("value_noise", "smooth", "rgb"))
    rng = np.random.default_rng(seed)
    axis = (np.arange(SIZE) + 0.5) / SIZE
    u, v = np.meshgrid(axis, axis)
    bend_u = noise(rng, u, v, 4, 5) - 0.5
    bend_v = noise(rng, u, v, 5, 4) - 0.5
    s, t = u + 0.14 * bend_u, v + 0.14 * bend_v
    broad = noise(rng, s, t, 7, 8)
    cloud = noise(rng, s, t, 14, 15)
    edge = noise(rng, u, v, 29, 31)
    pool = smooth((cloud + 0.14 * edge - 0.45) * 3.7)
    rim = np.exp(-((cloud + 0.12 * edge - 0.57) / 0.047) ** 2)
    tone = 0.20 + 0.45 * broad + 0.30 * pool - 0.058 * rim

    if part == "GrassFlat":
        sprigs = noise(rng, s, t, 61, 35)
        patches = smooth((noise(rng, s, t, 17, 19) - 0.36) * 3.2)
        tone -= 0.21 * smooth((sprigs - 0.70) * 4.4) * patches
    elif part == "MudBank":
        sediment = noise(rng, s, t + 0.04 * bend_u, 11, 41)
        tone += 0.16 * (sediment - 0.5) - 0.10 * smooth((edge - 0.63) * 4)
    elif part == "MountainRock":
        bedding = noise(rng, s + 0.15 * bend_v, t + u + 0.23 * bend_u, 12, 34)
        breakup = noise(rng, s, t, 17, 18)
        strata = smooth((0.72 * bedding + 0.28 * breakup - 0.45) * 3.4)
        line = np.exp(-((0.72 * bedding + 0.28 * breakup - 0.51) / 0.041) ** 2)
        tone = 0.74 * tone + 0.22 * strata - 0.045 * line
    elif part == "ShallowMargin":
        streak = noise(rng, s, t + 0.05 * bend_u, 6, 31)
        tone = 0.67 * tone + 0.31 * smooth((streak - 0.28) * 2.0)

    dark, middle, light = map(rgb, colors)
    pixels = middle + (middle - dark) * np.minimum(2 * tone - 1, 0)[..., None]
    pixels += (light - middle) * np.maximum(2 * tone - 1, 0)[..., None]
    if part == "MossStone":
        moss_field = noise(rng, s, t, 13, 15) + (cloud - 0.5) * 0.38
        moss = smooth((moss_field + (edge - 0.5) * 0.15 - 0.47) * 3.7)
        pigment = rgb("889475") + (tone - 0.5)[..., None] * 0.11
        pixels = pixels * (1 - 0.71 * moss[..., None]) + pigment * (0.71 * moss[..., None])
    if part == "ShallowMargin":
        silt = noise(rng, s, t + 0.05 * bend_u, 8, 17)
        coverage = 0.72 * smooth((silt + 0.22 * cloud - 0.52) * 3.25)
        wash_color = rgb("c1b498") + (tone - 0.5)[..., None] * 0.13
        pixels = pixels * (1 - coverage[..., None]) + wash_color * coverage[..., None]

    tooth = noise(rng, u, v, 115, 137)
    grain = rng.random(u.shape)
    pixels += ((tooth - 0.5) * 0.021 + (grain - 0.5) * 0.014)[..., None]
    rgb8 = np.rint(np.clip(pixels, 0, 1) * 255).astype(np.uint8)
    recipe["write_png"](path, rgb8)
    return rgb8


def seam_stats(pixels):
    """Compare the wrapping edge to ordinary neighboring texels in both axes."""
    data = pixels.astype(np.int16)
    result = {}
    for axis, name in ((1, "u"), (0, "v")):
        internal = np.abs(np.diff(data, axis=axis))
        wrap = np.abs(np.take(data, 0, axis=axis) - np.take(data, -1, axis=axis))
        edge_p95, interior_p95 = float(np.quantile(wrap, 0.95)), float(np.quantile(internal, 0.95))
        assert edge_p95 <= interior_p95 + 1, (name, edge_p95, interior_p95)
        result[name] = {"wrap_p95_rgb8": edge_p95, "interior_p95_rgb8": interior_p95}
    return result


def library(output):
    with bpy.data.libraries.load(str(MASTER_BLEND), link=False) as (source, target):
        assert "DryGround" in source.materials
        target.materials = ["DryGround"]
    template, = target.materials
    folder = output / "textures"
    folder.mkdir()
    materials, files, seams = {}, {}, {}
    for i, (name, (_, palette, roughness)) in enumerate(SURFACES.items()):
        slug = {"GrassFlat": "grass_flat", "MudBank": "mud_bank", "MossStone": "moss_stone",
                "MountainRock": "mountain_rock", "ShallowMargin": "shallow_margin"}[name]
        file = folder / f"ft_goose_mat_{slug}_basecolor.png"
        seams[name] = seam_stats(wash(name, palette, file, 63191 + i * 173))
        material = template.copy()
        material.name = name
        material.asset_clear()
        material.asset_mark()
        material.asset_data.description = f"MAT-003 / {SURFACES[name][0]} / Seamless UV watercolor"
        for tag in ("Feather & Tide", "Watercolor", "MAT-003", "Terrain"):
            material.asset_data.tags.new(tag)
        material.diffuse_color = recipe["linear_rgba"](palette[1])
        texture = next(node for node in material.node_tree.nodes if node.type == "TEX_IMAGE")
        texture.image = bpy.data.images.load(str(file), check_existing=False)
        texture.image.colorspace_settings.name = "sRGB"
        texture.image.pack()
        texture.image.filepath = f"//textures/{file.name}"
        texture.label = "Periodic watercolor · sRGB Base Color"
        texture.extension = "REPEAT"
        shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        shader.inputs["Roughness"].default_value = roughness
        materials[name], files[name] = material, file
    bpy.data.materials.remove(template, do_unlink=True)
    return materials, files, seams


def uv_mesh(group, name, material, vertices, faces, coords, smooth=False):
    return recipe["mesh_object"](group, name, material, vertices, faces, coords.__getitem__, smooth)


def rectangle(group, name, material, x, y, width, height, repeat_x, repeat_y, z=0.0, uv_offset=(0, 0)):
    points = [(x, y, z), (x + width, y, z), (x + width, y + height, z), (x, y + height, z)]
    u, v = uv_offset
    coords = [(u, v), (u + repeat_x, v), (u + repeat_x, v + repeat_y), (u, v + repeat_y)]
    return uv_mesh(group, name, material, points, [(0, 1, 2, 3)], coords)


def folded_strip(group, name, material, x, width, profile, uv_scale):
    """Unfold successive slope lengths into one V axis, then build separate modules."""
    modules = []
    length = 0.0
    for index, ((near_y, near_z), (far_y, far_z)) in enumerate(zip(profile, profile[1:])):
        v0 = length / uv_scale
        length += math.hypot(far_y - near_y, far_z - near_z)
        v1 = length / uv_scale
        vertices = [(x, near_y, near_z), (x + width, near_y, near_z),
                    (x + width, far_y, far_z), (x, far_y, far_z)]
        coords = [(0, v0), (width / uv_scale, v0), (width / uv_scale, v1), (0, v1)]
        modules.append(uv_mesh(group, f"{name}_{index + 1}", material, vertices, [(0, 1, 2, 3)], coords))
    for first, second in zip(modules, modules[1:]):
        for a, b in ((2, 1), (3, 0)):
            assert first.data.vertices[a].co == second.data.vertices[b].co
            assert first.data.uv_layers.active.uv[a].vector == second.data.uv_layers.active.uv[b].vector
    return modules


def world(scene):
    scene.world = bpy.data.worlds.new("Neutral terrain studio")
    node = scene.world.node_tree.nodes.get("Background")
    node.inputs["Color"].default_value = (0.40, 0.40, 0.40, 1)
    node.inputs["Strength"].default_value = 0.67
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 20
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = "AgX"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"


def backdrop(group, bounds=50):
    paper = recipe["plain_material"]("Preview warm paper", "e9e1d0")
    rectangle(group, "Preview backdrop", paper, -bounds, -bounds, 2 * bounds, 2 * bounds, 1, 1, z=-0.20)
    return paper


def text(group, ink, label, x, y, size):
    recipe["text_object"](group, ink, label, x, y, size, "LEFT")


def neutral_lights(group):
    recipe["area_light"](group, "Neutral key", (-4, -3, 8), 1250, 7)
    recipe["area_light"](group, "Neutral fill", (4, 3, 7), 650, 6)


def review_board(scene, materials):
    world(scene)
    group = recipe["collection"](scene, "Texture plates · preview only")
    backdrop(group)
    neutral_lights(group)
    ink = recipe["plain_material"]("Preview dark ink", "34453d")
    muted = recipe["plain_material"]("Preview muted ink", "5b6b62")
    rule = recipe["plain_material"]("Preview rule", "8a9988")
    text(group, muted, "FEATHER & TIDE   /   MATERIAL LIBRARY", -5.22, 3.50, 0.152)
    text(group, ink, "Wetland and mountain surfaces", -5.22, 3.04, 0.365)
    text(group, muted, "MAT-003  /  V001", 3.98, 3.48, 0.132)
    rectangle(group, "Header rule", rule, -5.22, 2.76, 10.44, 0.012, 1, 1)
    for i, (name, (label, _, _)) in enumerate(SURFACES.items()):
        x, y = ([(-5.22, 0.48), (-1.70, 0.48), (1.82, 0.48), (-5.22, -2.47), (-1.70, -2.47)])[i]
        material = materials[name]
        rectangle(group, f"{name} / 1×", material, x, y, 1.61, 1.61, 1, 1)
        rectangle(group, f"{name} / 4×", material, x + 1.73, y, 1.61, 1.61, 4, 4)
        text(group, ink, label, x, y - 0.30, 0.195)
        text(group, muted, "1 tile", x, y - 0.53, 0.125)
        text(group, muted, "4 × 4 tiles", x + 1.73, y - 0.53, 0.125)
    text(group, ink, "Surface library", 1.82, -0.79, 0.255)
    text(group, muted, "1024 px sRGB Base Color", 1.82, -1.23, 0.158)
    text(group, muted, "Seamless UV repeat", 1.82, -1.54, 0.158)
    text(group, muted, "Neutral studio light", 1.82, -1.85, 0.158)
    camera = recipe["camera"](group, "Preview / overhead", (0, 0.28, 14), (0, 0.28, 0), 11.65)
    camera.rotation_euler = (0, 0, 0)
    scene.camera = camera


def corner_stage(scene, materials):
    world(scene)
    preview = recipe["collection"](scene, "Corner studio · excluded from GLB")
    backdrop(preview)
    neutral_lights(preview)
    samples = recipe["collection"](scene, "MAT-003 · GLB surface modules")
    folded_strip(samples, "GrassFlat", materials["GrassFlat"], -4.92, 1.85,
                 [(-1.32, 0), (-0.18, 0), (0.94, 0.05), (1.63, 0.34)], 0.86)
    folded_strip(samples, "MudBank", materials["MudBank"], -2.87, 1.85,
                 [(-1.32, 0), (-0.18, 0), (0.94, 0.03), (1.63, 0.22)], 0.87)
    folded_strip(samples, "ShallowMargin", materials["ShallowMargin"], -0.82, 1.85,
                 [(-1.32, 0), (-0.18, 0), (0.94, 0.03), (1.63, 0.12)], 0.87)
    folded_strip(samples, "MossStone", materials["MossStone"], 1.24, 1.72,
                 [(-1.32, 0), (-0.58, 0), (0.20, 0.33), (0.86, 0.53), (1.63, 0.56)], 0.86)
    folded_strip(samples, "MountainRock", materials["MountainRock"], 3.17, 1.75,
                 [(-1.32, 0), (-0.72, 0.02), (0.12, 0.68), (0.66, 0.97), (1.63, 1.0)], 0.86)
    ink = recipe["plain_material"]("Corner studio ink", "405147")
    for x, label in zip((-4.92, -2.87, -0.82, 1.24, 3.17),
                        ("Grass", "Silt", "Shallow", "Moss", "Rock")):
        text(preview, ink, label, x, -1.80, 0.205)
    text(preview, ink, "MAT-003   /   UV continuity across separate modules", -4.92, 2.66, 0.28)
    camera = recipe["camera"](preview, "Preview / ground turns", (0, -9.4, 7.9), (0, 0.30, 0.21), 11.2)
    scene.camera = camera
    return list(samples.objects), preview


def size(scene, width, height):
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100


def export_and_check(objects, path):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_yup=True)
    for obj in objects:
        obj.select_set(False)
    gltf = recipe["read_glb"](path)
    assert len(gltf["images"]) == 5 and len(gltf["meshes"]) == len(objects)
    assert not gltf.get("cameras") and not gltf.get("extensionsRequired")
    for material in gltf["materials"]:
        name = material["name"]
        pbr = material["pbrMetallicRoughness"]
        assert pbr["metallicFactor"] == 0 and abs(pbr["roughnessFactor"] - SURFACES[name][2]) < 1e-5
        tex = gltf["textures"][pbr["baseColorTexture"]["index"]]
        image = gltf["images"][tex["source"]]
        assert image["mimeType"] == "image/png" and "bufferView" in image
        sampler = gltf["samplers"][tex["sampler"]] if "sampler" in tex else {}
        assert sampler.get("wrapS", 10497) == sampler.get("wrapT", 10497) == 10497


def check_import(scene, objects, path, studio, output):
    window = bpy.context.window
    imported_scene = bpy.data.scenes.new("MAT-003 GLB check")
    window.scene = imported_scene
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    assert len(imported) == len(objects)
    by_name = {obj.name: obj for obj in objects}

    def corner_values(obj):
        uv = obj.data.uv_layers.active
        values = set()
        for i, loop in enumerate(obj.data.loops):
            point = obj.matrix_world @ obj.data.vertices[loop.vertex_index].co
            values.add(tuple(round(float(value), 5) for value in (*point, *uv.uv[i].vector)))
        return values

    for obj in imported:
        source = by_name[obj.name.rsplit(".", 1)[0]]
        assert obj.data.materials[0].name.rsplit(".", 1)[0] == source.data.materials[0].name
        assert corner_values(source) == corner_values(obj), obj.name
    imported_scene.collection.children.link(studio)
    imported_scene.world = scene.world
    imported_scene.render.engine = "CYCLES"
    imported_scene.cycles.device = "CPU"
    imported_scene.cycles.samples = scene.cycles.samples
    imported_scene.cycles.use_denoising = True
    imported_scene.view_settings.view_transform = scene.view_settings.view_transform
    imported_scene.render.image_settings.color_mode = "RGB"
    size(imported_scene, scene.render.resolution_x, scene.render.resolution_y)
    recipe["render"](imported_scene, scene.camera, output / "preview_glb_roundtrip.png")
    window.scene = scene
    bpy.data.scenes.remove(imported_scene)
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)


def main(output):
    window = bpy.context.window
    original = window.scene
    assert not bpy.data.filepath and set(original.objects.keys()) <= {"Camera", "Cube", "Light"}
    output.mkdir(parents=True, exist_ok=True)
    assert not (output / "textures").exists() and not (output / f"{STEM}.blend").exists()
    board = bpy.data.scenes.new("MAT-003 | Terrain texture plates")
    window.scene = board
    bpy.data.scenes.remove(original)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
    mats, files, seams = library(output)
    review_board(board, mats)
    size(board, 1536, 1080)
    stage = bpy.data.scenes.new("MAT-003 | Ground and rock turns")
    window.scene = stage
    objects, studio = corner_stage(stage, mats)
    size(stage, 1440, 900)
    bpy.context.view_layer.update()
    counts = recipe["triangle_counts"](objects)
    glb = output / f"{STEM}.glb"
    export_and_check(objects, glb)
    window.scene = board
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.region_3d.view_perspective = "CAMERA"
                space.region_3d.view_camera_zoom = 14
                space.overlay.show_overlays = False
                space.shading.type = "MATERIAL"
    board.render.filepath = stage.render.filepath = "//"
    blend = output / f"{STEM}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=True)
    recipe["render"](board, board.camera, output / "preview_top.png")
    size(board, 852, 599)
    recipe["render"](board, board.camera, output / "preview_repeat_small.png")
    window.scene = stage
    recipe["render"](stage, stage.camera, output / "preview_corner.png")
    check_import(stage, objects, glb, studio, output)

    sha = lambda p: sha256(p.read_bytes()).hexdigest()
    deliverables = [blend, glb, *files.values(), *sorted(output.glob("preview_*.png"))]
    recipe["write_json"](output / "asset_manifest.json", {
        "id": "MAT-003", "version": "v001", "depends": ["MAT-001/v001"],
        "blender": bpy.app.version_string,
        "source": "程序生成原创纹理。使用 MAT-001/v001 材质节点、周期噪声与相同纸纹振幅。",
        "dependency_hashes": {p.name: sha(p) for p in (MASTER_BLEND, MASTER_SCRIPT)},
        "materials": {name: {"file": file.relative_to(output).as_posix(), "color_space": "sRGB",
                             "size": [SIZE, SIZE], "wrap": "repeat U/V", "roughness": SURFACES[name][2],
                             "palette": [f"#{c.upper()}" for c in SURFACES[name][1]]}
                      for name, file in files.items()},
        "object_triangle_counts": counts,
        "files": {**{p.relative_to(output).as_posix(): sha(p) for p in deliverables},
                  Path(__file__).name: sha(Path(__file__))},
    })
    recipe["write_json"](output / "qa.json", {
        "id": "MAT-003", "version": "v001", "status": "needs_review",
        "checks": {"wrap_delta_vs_interior": seams, "separate_modules_share_edge_uvs": "pass",
                   "five_glb_textures_repeat_uv": "pass", "glb_import_world_vertices_uvs_materials": "pass"},
        "visual_review": "待核对重复铺设与转角预览",
    })


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(Path(args[0]).resolve() if args else HERE)
