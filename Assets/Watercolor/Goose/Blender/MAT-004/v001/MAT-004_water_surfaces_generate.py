"""Generate and verify MAT-004 with Blender 5.2.

blender --background --factory-startup --python this_file.py -- /empty/output
"""
from hashlib import sha256
import math
from pathlib import Path
import runpy
import sys

import bpy
import numpy as np


HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
MASTER = LIBRARY / "MAT-001" / "v001"
MASTER_BLEND = MASTER / "MAT-001_watercolor_master.blend"
MASTER_SCRIPT = MASTER / "MAT-001_watercolor_master_generate.py"
recipe = runpy.run_path(str(MASTER_SCRIPT))
BED_TEXTURE = LIBRARY / "MAT-003/v001/textures/ft_goose_mat_mud_bank_basecolor.png"
SIZE = 1024
STEM = "MAT-004_water_surfaces"
VARIANTS = {
    "Water_Shallow": ("Shallow water", ("789e93", "9ebbb0", "c3cbb3"), 0.83, 0.73),
    "Water_Lake": ("Lake surface", ("667f93", "8298a9", "adb9c1"), 0.79, 0.96),
    "Water_River": ("River surface", ("708e94", "91acb0", "b5c6c2"), 0.81, 0.90),
}


def paint_water(name, palette, max_alpha, seed, file):
    rng = np.random.default_rng(seed)
    noise, smooth, rgb = (recipe[k] for k in ("value_noise", "smooth", "rgb"))
    axis = (np.arange(SIZE) + 0.5) / SIZE
    u, v = np.meshgrid(axis, axis)
    broad = noise(rng, u, v, 5, 7)
    cloud = noise(rng, u, v, 11, 15)
    edge = noise(rng, u, v, 26, 27)
    is_river = name == "Water_River"
    if is_river:
        bands = noise(rng, u + 0.08 * (broad - 0.5), v, 23, 5)
        detail = noise(rng, u + 0.05 * (cloud - 0.5), v, 49, 11)
        drift = 0.024 * np.sin(2 * np.pi * v * 3 + 0.9) + 0.02 * (cloud - 0.5)
        shore = 0.456 - np.abs(u - 0.5 + drift)
    else:
        bands = noise(rng, u, v + 0.13 * (broad - 0.5), 5, 26)
        detail = noise(rng, u, v + 0.07 * (cloud - 0.5), 13, 54)
        x, y = (u - 0.5) / 0.461, (v - 0.5) / 0.432
        theta = np.arctan2(y, x)
        outline = 1 + 0.045 * np.sin(3 * theta + 1.2) + 0.032 * np.cos(5 * theta - 0.4)
        shore = (outline - np.hypot(x, y)) * 0.44 + 0.021 * (edge - 0.5)

    feather_width = {"Water_Shallow": 0.074, "Water_Lake": 0.052, "Water_River": 0.082}[name]
    feather = smooth(shore / feather_width)
    depth = smooth(shore / (0.27 if name == "Water_Shallow" else 0.20))
    tone = 0.29 + 0.39 * broad + 0.24 * smooth((bands - 0.45) * 3.4)
    tone += (detail - 0.5) * (0.15 if is_river else 0.105)
    tone += (1 - depth) * 0.19
    dark, mid, light = map(rgb, palette)
    color = mid + (mid - dark) * np.minimum(2 * tone - 1, 0)[..., None]
    color += (light - mid) * np.maximum(2 * tone - 1, 0)[..., None]

    # Isolated warm pigment streaks stay in Base Color for all viewing angles.
    ribbon = np.exp(-((detail + 0.09 * bands - 0.73) / 0.036) ** 2)
    broken = smooth((cloud - 0.57) * 3.4) * smooth((bands - 0.40) * 3.0)
    warm = (0.36 if name == "Water_Lake" else 0.23) * ribbon * broken * depth
    color = color * (1 - warm[..., None]) + rgb("d6bc92") * warm[..., None]
    tooth = noise(rng, u, v, 115, 137)
    grain = rng.random(u.shape)
    color += ((tooth - 0.5) * 0.021 + (grain - 0.5) * 0.014)[..., None]

    min_water = {"Water_Shallow": 0.36, "Water_Lake": 0.57, "Water_River": 0.50}[name]
    alpha = feather * (min_water + (max_alpha - min_water) * depth)
    rgba = np.rint(np.clip(np.dstack((color, alpha)), 0, 1) * 255).astype(np.uint8)
    a = rgba[..., 3]
    assert np.all(a[:, [0, -1]] == 0)
    if not is_river:
        assert np.all(a[[0, -1], :] == 0)
    else:
        assert np.max(np.abs(a[0].astype(int) - a[-1].astype(int))) <= 2
    assert int(a.max()) == round(max_alpha * 255) and np.any((a > 8) & (a < 64))
    recipe["write_png"](file, rgba)
    return {"alpha_range_rgb8": [int(a.min()), int(a.max())],
            "shore_partial_alpha_pixels": int(np.count_nonzero((a > 0) & (a < 96)))}


def materials(output):
    with bpy.data.libraries.load(str(MASTER_BLEND), link=False) as (source, target):
        assert "PlantAlpha" in source.materials
        target.materials = ["PlantAlpha"]
    template, = target.materials
    folder = output / "textures"
    folder.mkdir()
    mats, files, stats = {}, {}, {}
    for i, (name, (label, palette, roughness, opacity)) in enumerate(VARIANTS.items()):
        file = folder / f"ft_goose_mat_{name.lower()}_basecolor_alpha.png"
        stats[name] = paint_water(name, palette, opacity, 11681 + i * 233, file)
        mat = template.copy()
        mat.name = name
        mat.asset_clear()
        mat.asset_mark()
        mat.asset_data.description = f"Feather & Tide / MAT-004 / {label} / Static watercolor RGBA"
        for tag in ("Feather & Tide", "Watercolor", "MAT-004", "Water"):
            mat.asset_data.tags.new(tag)
        mat.diffuse_color = recipe["linear_rgba"](palette[1])
        mat.use_backface_culling = True
        tex = next(n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE")
        tex.image = bpy.data.images.load(str(file), check_existing=False)
        tex.image.colorspace_settings.name = "sRGB"
        tex.image.alpha_mode = "STRAIGHT"
        tex.image.pack()
        tex.image.filepath = f"//textures/{file.name}"
        tex.label = "Static watercolor · RGB + shoreline alpha"
        tex.extension = "REPEAT" if name == "Water_River" else "EXTEND"
        shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Transmission Weight"].default_value = 0.0
        mats[name], files[name] = mat, file
    bpy.data.materials.remove(template, do_unlink=True)
    return mats, files, stats


def quad(group, name, mat, cx, cy, width, height, z, uv_size=1.0):
    x, y = width / 2, height / 2
    verts = [(cx - x, cy - y, z), (cx + x, cy - y, z),
             (cx + x, cy + y, z), (cx - x, cy + y, z)]
    uv = [(0, 0), (uv_size, 0), (uv_size, uv_size), (0, uv_size)]
    return recipe["mesh_object"](group, name, mat, verts, [(0, 1, 2, 3)], uv.__getitem__)


def river(group, material, x, y):
    """Use U across the channel and V along it, with V repeating twice."""
    vertices, uvs, faces = [], [], []
    segments = 40
    for i in range(segments + 1):
        v = i / segments
        center = x + 0.58 * math.sin(2 * math.pi * v + 0.25) + 0.34 * (v - 0.5)
        width = 0.78 + 0.19 * math.sin(2 * math.pi * v + 1.15)
        for u, s in ((0, -1), (1, 1)):
            vertices.append((center + s * width, y - 1.34 + 2.68 * v, 0.045))
            uvs.append((u, 2 * v))
        if i:
            a = 2 * (i - 1)
            faces.append((a, a + 1, a + 3, a + 2))
    return recipe["mesh_object"](group, "River ribbon / export", material, vertices, faces, uvs.__getitem__)


def card_geometry(group, name, material, x, y):
    """Give each material the same ground context under the transparent edge."""
    n = 8
    radius = 0.10
    points = []
    for dx, dy, start in ((1.56, 1.24, 0), (-1.56, 1.24, 90),
                           (-1.56, -1.24, 180), (1.56, -1.24, 270)):
        for angle in np.linspace(start, start + 90, n, endpoint=True):
            radians = math.radians(angle)
            points.append((x + dx + radius * math.cos(radians),
                           y + dy + radius * math.sin(radians), 0))
    uvs = [((px - x) / 1.98 + 0.5, (py - y) / 1.98 + 0.5) for px, py, _ in points]
    return recipe["mesh_object"](group, name, material, points, [tuple(range(len(points)))], uvs.__getitem__)


def pebble(group, material, name, x, y, size):
    obj = recipe["stone"](group, material, x, y, size, size * 0.62, size * 0.44, name)
    obj.name = f"Preview pebble {name}"
    return obj


def setup(scene, mats):
    preview = recipe["collection"](scene, "Studio context · preview only")
    waters = recipe["collection"](scene, "MAT-004 · independent water surfaces")
    paper = recipe["plain_material"]("Warm studio paper", "eae4d6")
    ink = recipe["plain_material"]("Water study ink", "33433e")
    secondary = recipe["plain_material"]("Water study soft ink", "53675f")
    stone = recipe["plain_material"]("Muted shoal stones", "9b9b83")
    bed = recipe["watercolor_material"]("Preview silt from MAT-003", BED_TEXTURE, ("95806b", "ac967e", "c4ac8d"), 0.95)
    bed.asset_clear()
    bed.node_tree.nodes.get("Image Texture").image.filepath = f"//../../MAT-003/v001/textures/{BED_TEXTURE.name}"
    quad(preview, "Preview background", paper, 0, 0, 100, 100, -0.11)

    xs = (-3.56, 0, 3.56)
    for x, name in zip(xs, VARIANTS):
        card_geometry(preview, f"{name} / preview substrate", bed, x, 0.13)
    quad(waters, "Shallow pool / export", mats["Water_Shallow"], xs[0], 0.13, 3.17, 2.42, 0.045)
    quad(waters, "Lake patch / export", mats["Water_Lake"], xs[1], 0.13, 3.17, 2.43, 0.045)
    river(waters, mats["Water_River"], xs[2], 0.13)
    for x, y, s, seed in [
        (-4.55, -0.22, 0.12, 11), (-4.35, -0.58, 0.085, 12), (-3.88, -0.70, 0.10, 13),
        (-3.20, 0.53, 0.08, 14), (-1.19, -0.33, 0.11, 22), (-1.07, -0.55, 0.075, 23),
        (0.96, 0.45, 0.13, 24), (2.64, -0.45, 0.09, 31), (3.03, -0.61, 0.082, 32),
        (4.32, 0.42, 0.12, 33), (4.55, 0.60, 0.077, 34),
    ]:
        pebble(preview, stone, seed, x, y, s)

    for label, x, y, size, mat in [
        ("FEATHER & TIDE   /   MATERIAL LIBRARY", -5.20, 2.58, 0.15, secondary),
        ("Lake and shallow water", -5.20, 2.12, 0.37, ink),
        ("MAT-004  /  V001", 4.00, 2.53, 0.14, secondary),
        ("Shallow water", -5.20, -1.60, 0.235, ink),
        ("Sage wash, visible silt", -5.20, -1.94, 0.150, secondary),
        ("Lake surface", -1.64, -1.60, 0.235, ink),
        ("Blue-grey wash, deeper centre", -1.64, -1.94, 0.150, secondary),
        ("River surface", 1.92, -1.60, 0.235, ink),
        ("Longitudinal bands, soft banks", 1.92, -1.94, 0.150, secondary),
    ]:
        recipe["text_object"](preview, mat, label, x, y, size, "LEFT")
    quad(preview, "Header rule", secondary, 0, 1.76, 10.40, 0.014, 0.003)
    recipe["area_light"](preview, "Neutral key", (-3.5, -4, 8), 1150, 6)
    recipe["area_light"](preview, "Neutral fill", (4, 3, 7), 650, 6)
    top = recipe["camera"](preview, "Preview / overhead", (0, 0.24, 14), (0, 0.24, 0), 11.55)
    top.rotation_euler = (0, 0, 0)
    iso = recipe["camera"](preview, "Preview / oblique", (0, -8.2, 9.4), (0, 0.36, 0.0), 11.55)

    scene.world = bpy.data.worlds.new("Water study neutral studio")
    world = scene.world.node_tree.nodes.get("Background")
    world.inputs["Color"].default_value = (0.42, 0.42, 0.42, 1)
    world.inputs["Strength"].default_value = 0.68
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.cycles.transparent_max_bounces = 8
    scene.view_settings.view_transform = "AgX"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.resolution_x = 1440
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    return preview, list(waters.objects), top, iso


def check_glb(scene, objects, path, preview, output):
    data = recipe["read_glb"](path)
    assert len(data["images"]) == 3 and len(data["meshes"]) == len(objects) == 3
    assert not data.get("cameras") and not data.get("extensionsRequired")
    assert not data.get("animations")
    assert set(m["name"] for m in data["materials"]) == set(VARIANTS)
    for material in data["materials"]:
        assert material["alphaMode"] == "BLEND"
        pbr = material["pbrMetallicRoughness"]
        assert pbr["metallicFactor"] == 0
        assert abs(pbr["roughnessFactor"] - VARIANTS[material["name"]][2]) < 1e-5
        texture = data["textures"][pbr["baseColorTexture"]["index"]]
        assert data["images"][texture["source"]]["mimeType"] == "image/png"
        sampler = data["samplers"][texture["sampler"]] if "sampler" in texture else {}
        wrap = 10497 if material["name"] == "Water_River" else 33071
        assert sampler.get("wrapT", 10497) == sampler.get("wrapS", 10497) == wrap

    window = bpy.context.window
    copy = bpy.data.scenes.new("MAT-004 GLB check")
    window.scene = copy
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    assert len(imported) == len(objects)
    originals = {o.name: o for o in objects}

    def world_uv(obj):
        values = set()
        uv = obj.data.uv_layers.active
        for i, loop in enumerate(obj.data.loops):
            position = obj.matrix_world @ obj.data.vertices[loop.vertex_index].co
            values.add(tuple(round(float(value), 5) for value in (*position, *uv.uv[i].vector)))
        return values

    for obj in imported:
        original = originals[obj.name.rsplit(".", 1)[0]]
        material = obj.data.materials[0]
        shader = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        assert shader.inputs["Alpha"].is_linked
        assert material.name.rsplit(".", 1)[0] == original.data.materials[0].name
        assert world_uv(obj) == world_uv(original), obj.name
    copy.collection.children.link(preview)
    copy.world = scene.world
    copy.render.engine = scene.render.engine
    copy.cycles.device = "CPU"
    copy.cycles.samples = scene.cycles.samples
    copy.cycles.use_denoising = True
    copy.cycles.transparent_max_bounces = 8
    copy.view_settings.view_transform = scene.view_settings.view_transform
    copy.render.resolution_x = scene.render.resolution_x
    copy.render.resolution_y = scene.render.resolution_y
    copy.render.resolution_percentage = 100
    copy.render.image_settings.color_mode = "RGB"
    recipe["render"](copy, scene.camera, output / "preview_glb_roundtrip.png")
    window.scene = scene
    bpy.data.scenes.remove(copy)
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)


def main(output):
    window = bpy.context.window
    original = window.scene
    assert not bpy.data.filepath and set(original.objects.keys()) <= {"Camera", "Cube", "Light"}
    output.mkdir(parents=True, exist_ok=True)
    assert not (output / "textures").exists() and not (output / f"{STEM}.blend").exists()
    scene = bpy.data.scenes.new("MAT-004 | Lake and shallow water")
    window.scene = scene
    bpy.data.scenes.remove(original)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
    mats, files, alpha = materials(output)
    preview, objects, top, iso = setup(scene, mats)
    bpy.context.view_layer.update()
    counts = recipe["triangle_counts"](objects)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    glb = output / f"{STEM}.glb"
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True, export_yup=True)
    for obj in objects:
        obj.select_set(False)
    scene.camera = top
    scene.render.filepath = "//"
    scene["asset_id"] = "MAT-004"
    scene["water_uv"] = "Static RGBA. Lake and shallow patches clamp; river U across, V along."
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.region_3d.view_perspective = "CAMERA"
                space.region_3d.view_camera_zoom = 13
                space.overlay.show_overlays = False
                space.shading.type = "MATERIAL"
    blend = output / f"{STEM}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=True)
    recipe["render"](scene, top, output / "preview_top.png")
    recipe["render"](scene, iso, output / "preview_oblique.png")
    check_glb(scene, objects, glb, preview, output)

    sha = lambda p: sha256(p.read_bytes()).hexdigest()
    deliverables = [blend, glb, *files.values(), *sorted(output.glob("preview_*.png"))]
    recipe["write_json"](output / "asset_manifest.json", {
        "id": "MAT-004", "version": "v001", "depends": ["MAT-001/v001"], "blender": bpy.app.version_string,
        "source": "原创程序化水彩色带与岸缘 Alpha，复用 MAT-001 节点、周期噪声和纸纹强度。",
        "dependency_hashes": {p.name: sha(p) for p in (MASTER_BLEND, MASTER_SCRIPT)},
        "preview_only": {"bed_texture": BED_TEXTURE.name, "asset": "MAT-003/v001", "sha256": sha(BED_TEXTURE)},
        "materials": {
            name: {"file": file.relative_to(output).as_posix(), "size": [SIZE, SIZE],
                   "channels": "sRGB Base Color + straight linear alpha", "alpha_mode": "BLEND",
                   "roughness": VARIANTS[name][2], "max_alpha": VARIANTS[name][3], "metallic": 0,
                   "uv": "U across stream, V repeats along stream" if name == "Water_River"
                         else "One patch; transparent perimeter; clamp both axes"}
            for name, file in files.items()
        },
        "object_triangle_counts": counts,
        "files": {**{p.relative_to(output).as_posix(): sha(p) for p in deliverables},
                  Path(__file__).name: sha(Path(__file__))},
    })
    recipe["write_json"](output / "qa.json", {
        "id": "MAT-004", "version": "v001", "status": "needs_review",
        "checks": {"shore_alpha": alpha, "river_v_edge_wrap": "pass",
                   "three_independent_glb_surfaces_and_blend_alpha": "pass",
                   "glb_import_geometry_uv_material_alpha": "pass"},
        "visual_review": "待核对顶视、斜视与 GLB 回导渲染",
    })


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(Path(args[0]).resolve() if args else HERE)
