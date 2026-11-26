"""Build contour-fitted wetland water from the delivered ENV-002 terrain."""
import argparse
from collections import Counter
import json
from pathlib import Path
import runpy
import struct
import sys
import zlib

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import numpy as np

HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
ENV2 = LIB / "ENV-002/v001/ENV-002_wetland.blend"
MAT4 = LIB / "MAT-004/v001"
BASE = runpy.run_path(str(LIB / "ENV-001/v001/ENV-001_generate.py"))
WATER = BASE["WATER"]
N = 512
FADE_DEPTH = .165
NAMES = {"ShallowPool_StartMudflat": "StartMudflat", "ShallowPool_RestPatch": "RestPatch", "Channel": "ReedIslet"}
STEM = "ENV-003_wetland_water"
check, obj, group, digest = (BASE[n] for n in ("check", "obj", "collection", "file_hash"))


def append_meshes(path, names):
    with bpy.data.libraries.load(str(path), link=False) as (_, destination):
        destination.objects = list(names)
    return dict(zip(names, destination.objects))


def source_materials():
    path = MAT4 / "MAT-004_water_surfaces.blend"
    names = ["Water_Shallow", "Water_River"]
    with bpy.data.libraries.load(str(path), link=False) as (_, destination):
        destination.materials = list(names)
    current = json.loads((MAT4 / "asset_manifest.json").read_text())
    result = {}
    for name, mat in zip(names, destination.materials):
        tex = next(n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE")
        info = current["materials"][name]
        path = MAT4 / info["file"]
        check(digest(path) == current["files"][info["file"]], name)
        # Load the verified disk PNG so a saved Blender session cannot silently replace the source.
        image = bpy.data.images.load(str(path), check_existing=False)
        pixels = np.empty(1024 * 1024 * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        bpy.data.images.remove(image)
        result[name] = (mat, pixels.reshape(1024, 1024, 4)[..., :3], info)
    return result


def wet_polygons(terrain):
    polygons = []
    for tri in terrain.data.polygons:
        corners = [terrain.data.vertices[i].co for i in tri.vertices]
        wet = []
        for a, b in zip(corners, corners[1:] + corners[:1]):
            if a.z < WATER:
                wet.append(a)
            if (a.z < WATER) != (b.z < WATER):
                wet.append(a.lerp(b, (WATER - a.z) / (b.z - a.z)))
        if len(wet) >= 3:
            polygons.append(wet)
    return polygons


def build_water(folder, name, terrain, material):
    vertices, faces, indices = [], [], {}
    for polygon in wet_polygons(terrain):
        ring = []
        for x, y, _ in polygon:
            key = (round(x, 6), round(y, 6))
            if key not in indices:
                indices[key] = len(vertices)
                vertices.append((x, y, WATER))
            ring.append(indices[key])
        faces.extend((ring[0], ring[i], ring[i + 1]) for i in range(1, len(ring) - 1))
    item = BASE["simple_mesh"](folder, name, vertices, faces, material)
    uv = item.data.uv_layers.new(name="WaterUV")
    for loop in item.data.loops:
        x, y, _ = vertices[loop.vertex_index]
        uv.data[loop.index].uv = ((x + 5) / 10, (y + 5) / 10)
    item["alignment"] = terrain.name
    item["reference_Z_BU"] = WATER
    item.asset_mark()
    return item


def depth_map(terrain):
    axis = np.linspace(-5, 5, N)
    height = np.full((N, N), np.nan, dtype=np.float64)
    for face in terrain.data.polygons:
        p = np.array([list(terrain.data.vertices[i].co) for i in face.vertices])
        x = np.flatnonzero((axis >= min(p[:,0])) & (axis <= max(p[:,0])))
        y = np.flatnonzero((axis >= min(p[:,1])) & (axis <= max(p[:,1])))
        xx, yy = np.meshgrid(axis[x], axis[y])
        e, f = p[1] - p[0], p[2] - p[0]
        dx, dy = xx - p[0,0], yy - p[0,1]
        det = e[0] * f[1] - e[1] * f[0]
        a = (dx * f[1] - dy * f[0]) / det
        b = (e[0] * dy - e[1] * dx) / det
        take = (a >= -1e-8) & (b >= -1e-8) & (a + b <= 1 + 1e-8)
        sub = height[np.ix_(y,x)]
        sub[take] = (p[0,2] + a * e[2] + b * f[2])[take]
        height[np.ix_(y,x)] = sub
    check(np.isfinite(height).all(), "uncovered depth atlas")
    return WATER - height


def png(path, rgba):
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))
    filtered = b"".join(b"\x00" + row.tobytes() for row in rgba[::-1])
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", N, N, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(filtered, 9)) + chunk(b"IEND", b""))


def shade(name, item, terrain, sources, output):
    channel = name == "Channel"
    template, rgb, info = sources["Water_River" if channel else "Water_Shallow"]
    depth = depth_map(terrain)
    gradient = np.clip(depth / FADE_DEPTH, 0, 1)
    alpha = (.69 if channel else .65) * gradient ** 2 * (3 - 2 * gradient)
    x = np.rint(np.linspace(180, 860, N)).astype(int)
    y = np.rint(np.linspace(0 if channel else 140, 1023 if channel else 880, N)).astype(int)
    colors = rgb[np.ix_(y, x)].copy()
    if channel:
        # Exact repeat of the rendered seam row; feather the correction over 24 texels.
        for i in range(24):
            w = (1 - i / 24) * .5
            a, b = colors[i].copy(), colors[-1 - i].copy()
            colors[i] = a * (1 - w) + b * w
            colors[-1 - i] = b * (1 - w) + a * w
    # MAT-004 supplies paper grain and tonal variation. A depth tint carries the wetland color.
    near = np.array((.63, .75, .69))
    far = np.array((.45, .59, .63))
    gradient_tint = np.clip(depth / .48, 0, 1)[..., None]
    colors = .72 * colors + .28 * (near + (far - near) * gradient_tint)
    rgba = np.rint(np.dstack((colors, alpha)) * 255).clip(0, 255).astype(np.uint8)
    stem = {"Channel": "channel", "ShallowPool_StartMudflat": "start_mudflat",
            "ShallowPool_RestPatch": "rest_patch"}[name]
    relative = Path("textures") / f"ft_goose_env_water_{stem}_basecolor_alpha.png"
    path = output / relative
    png(path, rgba)
    image = bpy.data.images.load(str(path), check_existing=False)
    image.alpha_mode = "STRAIGHT"
    image.pack()
    image.filepath = "//" + relative.as_posix()
    mat = template.copy()
    mat.name = "ENV003_" + name
    tex = next(n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE")
    tex.image, tex.extension = image, "EXTEND"
    shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    mat.node_tree.links.new(tex.outputs["Color"], shader.inputs["Base Color"])
    mat.node_tree.links.new(tex.outputs["Alpha"], shader.inputs["Alpha"])
    item.data.materials[0] = mat
    edge_diff = int(np.max(np.abs(rgba[0].astype(int) - rgba[-1].astype(int)))) if channel else None
    check(edge_diff in (None, 0), (name, edge_diff))
    check(not np.any(rgba[...,3][depth <= 0]), name)
    return {"path": relative.as_posix(), "sha256": digest(path), "mat004_source": info["file"],
            "mat004_png_sha256": digest(MAT4 / info["file"]), "pixels": [N, N],
            "alpha_min_max_rgb8": [int(rgba[...,3].min()), int(rgba[...,3].max())],
            "partial_alpha_pixels": int(((rgba[...,3] > 0) & (rgba[...,3] < rgba[...,3].max())).sum()),
            "channel_NS_full_RGBA8_max_delta": edge_diff, "dry_pixels_with_nonzero_alpha": 0}


def terrain_check(water, terrain):
    bvh = BVHTree.FromPolygons([v.co for v in terrain.data.vertices], [list(p.vertices) for p in terrain.data.polygons])
    edge_counts = Counter()
    area, max_z, max_dry = 0., 0., 0.
    for p in water.data.polygons:
        check(p.normal.z > .999, (water.name, p.index))
        area += p.area
        points = [water.data.vertices[i].co for i in p.vertices]
        for point in points + [p.center]:
            x,y = [max(-4.9999995,min(4.9999995,v)) for v in point.xy]
            hit, *_ = bvh.ray_cast(Vector((x, y, 1)), Vector((0, 0, -1)), 3)
            check(hit is not None, (water.name, point))
            max_z = max(max_z, abs(point.z - WATER))
            max_dry = max(max_dry, hit.z - WATER)
        for a, b in zip(p.vertices, tuple(p.vertices[1:]) + (p.vertices[0],)):
            edge_counts[tuple(sorted((a, b)))] += 1
    check(max(edge_counts.values()) <= 2, water.name)
    expected = sum(abs(sum(a.x * b.y - a.y * b.x for a,b in zip(p,p[1:]+p[:1]))) / 2
                   for p in wet_polygons(terrain))
    check(max_z < 1e-6 and max_dry < 1e-6 and abs(area - expected) < 1e-5, (water.name, area, expected, max_dry))
    if water.name.split(".")[0] == "Channel":
        border = [sorted(round(v.co.x, 5) for v in water.data.vertices if abs(v.co.y - y) < 1e-6)
                  for y in (-5, 5)]
        check(border[0] == border[1], border)
    else:
        check(all(max(abs(v.co.x),abs(v.co.y)) < 5 for v in water.data.vertices), water.name)
    return {"triangles": len(water.data.polygons), "vertices": len(water.data.vertices),
            "wet_area_BU2": area, "max_plane_error_BU": max_z, "max_dry_intrusion_BU": max_dry,
            "projected_area_error_BU2": abs(area - expected)}


def signature(item):
    item.data.calc_loop_triangles()
    uv = item.data.uv_layers.active.data
    corners = Counter()
    for triangle in item.data.loop_triangles:
        values = []
        for i in triangle.loops:
            p = item.data.vertices[item.data.loops[i].vertex_index].co
            values.append(tuple(round(v, 5) for v in (*p, *uv[i].uv)))
        a = min(range(3), key=lambda i: values[i])
        corners[tuple(values[a:] + values[:a])] += 1
    return corners


def roundtrip(output, tiles, terrain, tex):
    report, returned = {}, {}
    for name, source in tiles.items():
        path = output / f"ENV-003_{name}.glb"
        doc, blob = BASE["glb_chunks"](path)
        node, = doc["nodes"]
        check(node["name"] == name and node.get("translation", [0]*3) == [0]*3
              and node.get("scale", [1]*3) == [1]*3 and not doc.get("animations"), name)
        material, = doc["materials"]
        check(material["alphaMode"] == "BLEND", material)
        image, = doc["images"]
        view = doc["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        check(BASE["sha256"](blob[start:start+view["byteLength"]]).hexdigest() == tex[name]["sha256"], name)
        check(all(abs(doc["accessors"][primitive["attributes"]["POSITION"]]["min"][1] - WATER) < 1e-6
                  and abs(doc["accessors"][primitive["attributes"]["POSITION"]]["max"][1] - WATER) < 1e-6
                  for primitive in doc["meshes"][0]["primitives"]), name)
        existing = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(path), import_pack_images=True, merge_vertices=False)
        item, = set(bpy.data.objects) - existing
        check(item.type == "MESH" and signature(item) == signature(source)
              and item.location.length == 0 and tuple(item.scale) == (1, 1, 1), name)
        report[name] = dict(terrain_check(item, terrain[NAMES[name]]), alpha_mode="BLEND", embedded_rgba_exact=True)
        returned[name] = item
    return returned, report


def stage(scene, tiles, terrain, directory, prefix, gray=False):
    top_group = group("Aligned wetland meshes", scene.collection)
    offsets = {"ShallowPool_StartMudflat": (0, -10, 0), "ShallowPool_RestPatch": (0, 10, 0), "Channel": (10,0,0)}
    for n, offset in offsets.items():
        obj(top_group, NAMES[n] + " backdrop", terrain[NAMES[n]].data, offset)
        obj(top_group, n + " aligned", tiles[n].data, offset)
    obj(top_group, "Flat between ponds", terrain["Flat"].data, (0, 0, 0))
    for row in (-1, 1):
        obj(top_group, "Shore between ponds", terrain["Shore"].data, (10,row*10,0))
    channel_mat = tiles["Channel"].data.materials[0]
    shore_sheet = build_water(top_group,"Review | outside Channel shore sheet",terrain["Shore"],channel_mat)
    shore_sheet.hide_render = True
    uv = shore_sheet.data.uv_layers.active.data
    for corner in uv:
        corner.uv.y = 0
    for row in (-1,1):
        obj(top_group,f"Review | surface over Shore {row}",shore_sheet.data,(10,row*10,0))
    BASE["rectangle"](top_group, "Review backdrop", -250, 250, -100, 340, -.74, BASE["paint"]("Studio wash", "B4C1B7"))
    lighting = BASE["studio"](scene, scene.collection)
    top = BASE["camera"](lighting, "Wetland | top", (4,0,40), (4,0,0), 34)
    BASE["render"](scene, top, directory, prefix + "_top", (1024, 1024), 16)
    if gray:
        return
    detail = BASE["camera"](lighting, "Bank | alpha fade", (6.3,-14.4,4.5), (2.2,-8.55,-.18), 4.2)
    BASE["render"](scene, detail, directory, prefix + "_shore_detail", (1080, 630), 20)
    for row in range(-3, 11):
        for col in range(-7, 5):
            if col == 0 and -1 <= row <= 1 or col == 1 and row == 0:
                continue
            if col >= 1:
                continue
            obj(top_group, f"Ground {col},{row}", terrain["Flat"].data, (col*10,row*10,0))
    ground = terrain["Shore"]
    for row in range(-3, 11):
        if row not in (-1,0,1):
            obj(top_group, f"Shore backdrop {row}", ground.data, (10,row*10,0))
            obj(top_group, f"Surface backdrop {row}", shore_sheet.data, (10,row*10,0))
    bottom_mat = next(m for m in ground.data.materials if m.name.split(".")[0]=="ShallowMargin")
    floor = BASE["rectangle"](top_group,"Review | extending submerged floor",15,170,-35,105,BASE["FLOOR"],bottom_mat)
    uv = floor.data.uv_layers.new(name="TerrainUV")
    for loop in floor.data.loops:
        x,y,_ = floor.data.vertices[loop.vertex_index].co
        uv.data[loop.index].uv=((x+5)/10,(y+5)/10)
    mat = tiles["Channel"].data.materials[0]
    for row in range(-3, 11):
        geom = BASE["rectangle"](top_group, f"Review water surround {row}", 15, 170, row*10-5, row*10+5, WATER, mat)
        uv = geom.data.uv_layers.new(name="WaterUV")
        for index,val in enumerate(((1,0),(1,0),(1,1),(1,1))): uv.data[index].uv=val
    broad = BASE["camera"](lighting, "Fixed rear | shallow water", (0,0,1),(0,1,0))
    BASE["follow"](broad, (1.6,-12.4), Vector((.1,.994987437)))
    bird_group = group("Scale reference", scene.collection)
    bird = BASE["add_goose"](bird_group)
    bird.location = (1.6,-12.4,8 / BASE["SCALE"])
    bird.rotation_euler.z = -.1
    BASE["render"](scene, broad, directory, prefix + "_fixed_rear", BASE["GAME_SIZE"], 24)
    BASE["set_preview_workspace"](scene, broad)
    scene.render.filepath = "//review.png"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    check(not any(output.iterdir()), "Use an empty temporary output directory.")
    if args.verify:
        location = args.verify.resolve()
        bpy.ops.wm.open_mainfile(filepath=str(location / f"{STEM}.blend"))
        source = {name: bpy.data.objects[name] for name in NAMES}
        terrain = {name: bpy.data.objects[name] for name in NAMES.values()}
        m = json.loads((location/"asset_manifest.json").read_text())
        BASE["fresh_scene"]("Independent recheck")
        _, qa = roundtrip(location, source, terrain, m["textures"])
        expected = json.loads((location/"qa.json").read_text())["roundtrip"]
        check(qa == expected, "independent roundtrip metrics")
        BASE["write_json"](output/"recheck.json", {"result":"pass", "roundtrip":qa})
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    root = bpy.context.scene
    root.name = "ENV-003 | Water library"
    source_group = group("Water meshes at origin", root.collection)
    terrain = append_meshes(ENV2, (*NAMES.values(), "Flat", "Shore"))
    # Keep original terrain objects available for independent geometric verification.
    references = group("Terrain references", root.collection)
    for item in terrain.values(): references.objects.link(item)
    gray = BASE["paint"]("Graybox water", "91AFAC")
    tiles = {name:build_water(source_group,name,terrain[parent],gray) for name,parent in NAMES.items()}
    bpy.context.view_layer.update()
    geometry = {n:terrain_check(item,terrain[NAMES[n]]) for n,item in tiles.items()}
    patch_area = json.loads((ENV2.parent/"qa.json").read_text())["graybox"]["modules"]
    for name,data in geometry.items():
        check(abs(data["wet_area_BU2"] - patch_area[NAMES[name]]["area_below_review_water_BU2"])<1e-5,name)
    gray_slots = {}
    for name,item in terrain.items():
        gray_slots[name] = list(item.data.materials)
        for i,_ in enumerate(gray_slots[name]):
            item.data.materials[i] = BASE["paint"](f"Graybox terrain {i}","9EA59A" if i==0 else "A49887")
    gray_scene = BASE["fresh_scene"]("Graybox")
    stage(gray_scene,tiles,terrain,output,"graybox",gray=True)
    bpy.data.scenes.remove(gray_scene)
    for name,item in terrain.items():
        for i,mat in enumerate(gray_slots[name]): item.data.materials[i]=mat
    bpy.context.window.scene = root
    (output/"textures").mkdir()
    mats = source_materials()
    tex = {name:shade(name,item,terrain[NAMES[name]],mats,output) for name,item in tiles.items()}
    for name,item in tiles.items():
        bpy.ops.object.select_all(action="DESELECT")
        item.select_set(True)
        bpy.context.view_layer.objects.active=item
        bpy.ops.export_scene.gltf(filepath=str(output/f"ENV-003_{name}.glb"),export_format="GLB",use_selection=True,
                                  export_yup=True, export_animations=False)
    for item in terrain.values(): item.hide_set(True)
    scene = BASE["fresh_scene"]("ENV-003 | Water and banks")
    stage(scene,tiles,terrain,output,"preview")
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{STEM}.blend"))
    final = BASE["fresh_scene"]("ENV-003 | GLB reassembly")
    imported, result = roundtrip(output,tiles,terrain,tex)
    for n,item in imported.items(): item.hide_render = True
    stage(final,imported,terrain,output,"preview_glb_roundtrip",gray=True)
    BASE["write_json"](output/"qa.json", {"status":"needs_review", "graybox":geometry,"roundtrip":result,
        "fade_depth_BU":FADE_DEPTH,"tolerances":{"height_BU":1e-6,"area_BU2":1e-5},
        "pending":["Art review; transparent sorting and water shaders in RealityKit; iPhone / iPad; FX-006."]})
    BASE["write_json"](output/"asset_manifest.json", {"id":"ENV-003","version":"v001","status":"needs_review",
        "execution_order_1_based":17, "depends":["ENV-002/v001","MAT-004/v001"], "water_z_BU":WATER,
        "blender_xyz_to_gltf":["x","z","-y"],"pivot_BU":[0,0,0], "variants":dict(NAMES),
        "source_hashes":{"ENV-002.blend":digest(ENV2),"MAT-004.blend":digest(MAT4/"MAT-004_water_surfaces.blend")},
        "rights":"Project-original contour and alpha bake from existing project textures.",
        "textures":tex})


if __name__ == "__main__":
    main()
