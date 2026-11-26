"""Build the ENV-001 asset library, generate review evidence and verify its GLBs in Blender."""
import argparse
from collections import defaultdict
from hashlib import sha256
from itertools import product
import json
import math
from pathlib import Path
import struct
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
MAT = LIBRARY / "MAT-003/v001"
CHR = LIBRARY / "CHR-001/v001"
STEM = "ENV-001_terrain"
NAMES = ("Flat", "GentleSlope", "Shore", "Ridge")
SURFACES = ("GrassFlat", "MudBank", "MossStone", "MountainRock", "ShallowMargin")
SIDE = 10.0
HALF = SIDE / 2
CELLS = 16
STEP = SIDE / CELLS
WATER = -.18
FLOOR = -.65
SCALE = 27.5 / .9900
GAME_SIZE = (852, 393)
POSITION_TOL = 1e-5
NORMAL_TOL = .03
UV_TOL = 1e-6
EDGES = {
    "Flat": dict(W="L", E="L", S="L", N="L"),
    "GentleSlope": dict(W="L", E="L", S="L", N="L"),
    "Shore": dict(W="L", E="W", S="C", N="C"),
    "Ridge": dict(W="L", E="L", S="L", N="L"),
}
# Every row shares the same coastal profile at its two joins.
ROWS = (
    ("Ridge", "GentleSlope", "Flat", "Shore"),
    ("GentleSlope", "Ridge", "Flat", "Shore"),
    ("GentleSlope", "Flat", "Flat", "Shore"),
    ("Flat", "GentleSlope", "Flat", "Shore"),
)
ROUTE = ((-2.7, -10), (-1.9, -6), (-.5, -2), (1.9, 3), (3.1, 6),
         (3.45, 10), (3.05, 14), (2.85, 17), (3.7, 21), (4.25, 24))


def check(condition, detail):
    if not condition:
        raise ValueError(detail)


def file_hash(path):
    return sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collection(name, parent):
    group = bpy.data.collections.new(name)
    parent.children.link(group)
    return group


def obj(group, name, data, location=(0, 0, 0)):
    item = bpy.data.objects.new(name, data)
    group.objects.link(item)
    item.location = location
    return item


def linear(value):
    value /= 255
    return value / 12.92 if value < .04045 else ((value + .055) / 1.055) ** 2.4


def color(hex_code):
    return tuple(linear(int(hex_code[i:i + 2], 16)) for i in (0, 2, 4)) + (1,)


def paint(name, hex_code, emission=False):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color(hex_code)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    if emission:
        ink = nodes.new("ShaderNodeEmission")
        ink.inputs["Color"].default_value = mat.diffuse_color
        mat.node_tree.links.new(ink.outputs[0], nodes.get("Material Output").inputs["Surface"])
    else:
        shader = nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = mat.diffuse_color
        shader.inputs["Roughness"].default_value = .94
    return mat


def smooth(value):
    value = max(0, min(1, value))
    return value * value * (3 - 2 * value)


def collar(x, y, span):
    return smooth((HALF - STEP - max(abs(x), abs(y))) / span)


def coast_x(x, y):
    blend = smooth((HALF - STEP - abs(y)) / 2.65)
    return x - blend * (.68 * math.sin(.75 * y + .3) + .20 * math.sin(1.47 * y - .3))


def shore_profile(x):
    return FLOOR * smooth((x + 2.2) / 6.25)


def height(name, x, y):
    if name == "Shore":
        return shore_profile(coast_x(x, y))
    if name == "GentleSlope":
        return .19 * collar(x, y, 2.55) * smooth((y + .42 * x + 3.2) / 5.3)
    if name == "Ridge":
        offset = x - .72 * math.sin(.53 * y) + .18 * y
        return .235 * collar(x, y, 1.95) * math.exp(-.50 * offset * offset)
    return 0.0


def surface(name, x, y):
    if name == "Shore":
        cross = coast_x(x, y)
        if cross > .62:
            return "ShallowMargin"
        if cross > -2.55 + .19 * math.cos(1.1 * y):
            return "MudBank"
    if name == "Ridge":
        offset = x - .72 * math.sin(.53 * y) + .18 * y
        if abs(y) < 2.8 and abs(offset) < .68 + .13 * math.sin(2.4 * y):
            return "MountainRock"
        if abs(y) < 3.5 and abs(offset) < 1.30 + .18 * math.sin(1.5 * y):
            return "MossStone"
    return "GrassFlat"


def build_module(name, group, materials):
    coords = [index * STEP - HALF for index in range(CELLS + 1)]
    verts = [(x, y, height(name, x, y)) for y in coords for x in coords]
    faces = []
    stride = CELLS + 1
    for j, i in product(range(CELLS), repeat=2):
        a = j * stride + i
        b, c, d = a + 1, a + 1 + stride, a + stride
        faces.extend(((a, b, c), (a, c, d)) if (i + j) % 2 == 0 else ((a, b, d), (b, c, d)))
    mesh = bpy.data.meshes.new(name + "_surface")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    uvs = mesh.uv_layers.new(name="TerrainUV")
    for mat in materials.values():
        mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = True
        x, y, _ = poly.center
        poly.material_index = SURFACES.index(surface(name, x, y))
        for idx in poly.loop_indices:
            vx, vy, _ = verts[mesh.loops[idx].vertex_index]
            uvs.data[idx].uv = ((vx + HALF) / SIDE, (vy + HALF) / SIDE)
    normals = [(0, 0, 0)] * len(verts)
    for index, (x, y, _) in enumerate(verts):
        if abs(x) == HALF or abs(y) == HALF:
            if name == "Shore" and abs(x) != HALF:
                gradient = (shore_profile(x + STEP) - shore_profile(x - STEP)) / (2 * STEP)
                normals[index] = Vector((-gradient, 0, 1)).normalized()
            else:
                normals[index] = (0, 0, 1)
    mesh.normals_split_custom_set_from_vertices(normals)
    module = obj(group, name, mesh)
    module["edges_W_E_S_N"] = "/".join(EDGES[name][edge] for edge in ("W", "E", "S", "N"))
    module["footprint_BU"] = SIDE
    module["edge_vertex_step_BU"] = STEP
    module["land_datum_BU"] = 0.0
    module["water_reference_BU"] = WATER
    module.asset_mark()
    module.asset_data.description = f"ENV-001/v001 | {name} | 10 BU centre snap"
    return module


def samples_on_edge(mesh, edge):
    axis = 0 if edge in ("W", "E") else 1
    target = HALF if edge in ("E", "N") else -HALF
    buckets = defaultdict(list)
    uv_data = mesh.uv_layers.active.data
    for loop in mesh.loops:
        p = mesh.vertices[loop.vertex_index].co
        if abs(p[axis] - target) <= POSITION_TOL:
            buckets[round(p[1 - axis], 5)].append(
                (p.copy(), mesh.corner_normals[loop.index].vector.copy(), uv_data[loop.index].uv.copy()))
    check(sorted(buckets) == [i * STEP - HALF for i in range(CELLS + 1)], (mesh.name, edge))
    return buckets


def angle(a, b):
    return math.degrees(math.atan2(a.cross(b).length, a.dot(b)))


def tile_box(mesh):
    return [[min(v.co[i] for v in mesh.vertices), max(v.co[i] for v in mesh.vertices)] for i in range(3)]


def audit_surface(item):
    mesh = item.data
    mesh.calc_loop_triangles()
    check(len(mesh.loop_triangles) == 2 * CELLS ** 2, item.name)
    check(item.location.length <= POSITION_TOL and max(abs(s - 1) for s in item.scale) <= POSITION_TOL,
          (item.name, "translation or scale"))
    check(item.matrix_world.to_quaternion().angle <= POSITION_TOL, (item.name, "rotation"))
    box = tile_box(mesh)
    check(all(abs(v - expected) <= POSITION_TOL for dim in box[:2] for v, expected in zip(dim, (-HALF, HALF))),
          (item.name, box))
    check(all(p.normal.z > 0 and p.area > 0 for p in mesh.polygons), (item.name, "face winding"))
    area = sum(p.normal.z * p.area for p in mesh.polygons)
    check(abs(area - SIDE ** 2) < 5e-4, (item.name, area))
    grid = {tuple(round(value, 5) for value in vertex.co[:2]) for vertex in mesh.vertices}
    expected_grid = {(i * STEP - HALF, j * STEP - HALF) for j, i in product(range(CELLS + 1), repeat=2)}
    check(grid == expected_grid, (item.name, "grid"))
    faces_per_cell = defaultdict(list)
    for poly in mesh.polygons:
        corners = [mesh.vertices[index].co for index in poly.vertices]
        x, y = [min(point[i] for point in corners) for i in (0, 1)]
        check(len(corners) == 3 and max(p.x for p in corners) - x == STEP
              and max(p.y for p in corners) - y == STEP, (item.name, "triangle out of cell"))
        faces_per_cell[x, y].append({tuple(v[:2]) for v in corners})
    check(len(faces_per_cell) == CELLS ** 2, (item.name, "missing cell"))
    for (x, y), faces in faces_per_cell.items():
        check(len(faces) == 2, (item.name, x, y, "face count"))
        first, second = faces
        shared = first & second
        check(len(first | second) == 4 and len(shared) == 2, (item.name, x, y, "cell overlap"))
        a, b = sorted(shared)
        check(abs(a[0] - b[0]) == STEP and abs(a[1] - b[1]) == STEP,
              (item.name, x, y, "triangles do not share the diagonal"))
    return {
        "bounds_BU": box,
        "triangle_count": len(mesh.loop_triangles),
        "mesh_vertices": len(mesh.vertices),
        "unique_xy_grid_vertices": len(grid),
        "projected_area_BU2": area,
        "max_face_slope_deg": max(math.degrees(math.acos(p.normal.z)) for p in mesh.polygons),
    }


def audit_join(name_a, name_b, side_a, side_b, mesh_a, mesh_b, offset):
    first, second = samples_on_edge(mesh_a, side_a), samples_on_edge(mesh_b, side_b)
    position = normal = uv = z = 0.0
    for key in first:
        for (ap, an, at), (bp, bn, bt) in product(first[key], second[key]):
            position = max(position, (ap - (bp + offset)).length)
            z = max(z, abs(ap.z - bp.z))
            normal = max(normal, angle(an, bn))
            uv = max(uv, *(abs(a - round(a)) for a in at - bt))
    a_box, b_box = tile_box(mesh_a), tile_box(mesh_b)
    axis = 0 if side_a == "E" else 1
    gap = b_box[axis][0] + offset[axis] - a_box[axis][1]
    check(position <= POSITION_TOL and abs(gap) <= POSITION_TOL and normal <= NORMAL_TOL and uv <= UV_TOL,
          (name_a, name_b, position, gap, normal, uv))
    return {
        "join": f"{name_a}.{side_a} → {name_b}.{side_b}", "type": EDGES[name_a][side_a],
        "vertices": len(first), "max_vertex_gap_BU": position, "max_height_delta_BU": z,
        "signed_footprint_gap_BU": gap, "max_normal_angle_deg": normal, "max_uv_error_mod_1": uv,
    }


def all_joins(modules):
    checks = []
    for a, b in product(NAMES, repeat=2):
        for side_a, side_b, offset in (("E", "W", (SIDE, 0, 0)), ("N", "S", (0, SIDE, 0))):
            kind = EDGES[a][side_a]
            if kind == EDGES[b][side_b] and kind != "W":
                checks.append(audit_join(a, b, side_a, side_b, modules[a].data, modules[b].data, Vector(offset)))
    check(len(checks) == 22, len(checks))
    return checks


def simple_mesh(group, name, points, faces, material):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], faces)
    mesh.update()
    mesh.materials.append(material)
    return obj(group, name, mesh)


def rectangle(group, name, xmin, xmax, ymin, ymax, z, mat):
    return simple_mesh(group, name, [(xmin, ymin, z), (xmax, ymin, z), (xmax, ymax, z), (xmin, ymax, z)],
                       [(0, 1, 2, 3)], mat)


def camera(group, name, eye, target, width=None):
    data = bpy.data.cameras.new(name)
    data.sensor_fit = "VERTICAL"
    data.sensor_height = 24
    data.lens = 12 / math.tan(math.radians(50) / 2)
    data.clip_start, data.clip_end = .05 / SCALE, 30000 / SCALE
    if width is not None:
        data.type = "ORTHO"
        data.sensor_fit = "HORIZONTAL"
        data.ortho_scale = width
    cam = obj(group, name, data, eye)
    if eye[0] == target[0] and eye[1] == target[1]:
        cam.rotation_euler = (0, 0, 0)
    else:
        cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    return cam


def follow(cam, leader, heading):
    x, y = leader
    back = 180 * math.cos(.48) / SCALE
    cam.location = (x - heading.x * back, y - heading.y * back, 180 * math.sin(.48) / SCALE)
    aim = Vector((x, y, 6 / SCALE))
    cam.rotation_euler = (aim - cam.location).to_track_quat("-Z", "Y").to_euler()


def new_stage(modules, root):
    stage = collection("01 | Assembled modules", root)
    tiles = {}
    for row, kinds in enumerate(ROWS):
        for col, name in enumerate(kinds):
            item = obj(stage, f"{name} | {col},{row}", modules[name].data, (col * SIDE - 20, row * SIDE - 10, 0))
            item["module"] = name
            tiles[col, row] = item
    bpy.context.view_layer.update()
    joins = []
    for (i, j), a in tiles.items():
        for delta, sides in (((1, 0), ("E", "W")), ((0, 1), ("N", "S"))):
            b = tiles.get((i + delta[0], j + delta[1]))
            if b is not None:
                joins.append(audit_join(a["module"], b["module"], *sides, a.data, b.data,
                                        b.location - a.location))
    corners = []
    for i, j in product(range(3), repeat=2):
        points, normals = [], []
        for di, dj in product(range(2), repeat=2):
            tile = tiles[i + di, j + dj]
            side = "W" if di else "E"
            axis_y = -HALF if dj else HALF
            for p, n, _ in samples_on_edge(tile.data, side)[axis_y]:
                points.append(tile.location + p)
                normals.append(n)
        error = max((p - points[0]).length for p in points)
        n_error = max(angle(n, normals[0]) for n in normals)
        check(error <= POSITION_TOL and n_error <= NORMAL_TOL, (i, j, error, n_error))
        corners.append({"grid_corner": [i, j], "max_gap_BU": error, "max_normal_angle_deg": n_error})
    return stage, tiles, {"joins": joins, "four_way_corners": corners}


def cover_underwater(tiles):
    """The review water is a horizontal rectangle contained within the terrain XY bounds."""
    vertices_checked = 0
    intersections = []
    min_outer_depth = math.inf
    max_outer_depth = -math.inf
    for (col, _), item in tiles.items():
        if col != 3:
            continue
        mesh = item.data
        mesh.calc_loop_triangles()
        for tri in mesh.loop_triangles:
            points = [mesh.vertices[v].co for v in tri.vertices]
            for a, b in zip(points, points[1:] + points[:1]):
                if (a.z < WATER) != (b.z < WATER):
                    point = a.lerp(b, (WATER - a.z) / (b.z - a.z))
                    intersections.append((item.location.x + point.x, item.location.y + point.y))
        for v in mesh.vertices:
            if abs(v.co.x - HALF) <= POSITION_TOL:
                depth = WATER - v.co.z
                min_outer_depth = min(min_outer_depth, depth)
                max_outer_depth = max(max_outer_depth, depth)
                vertices_checked += 1
    water_xy = [5, 15, -15, 25]
    check(intersections and all(water_xy[0] < x < water_xy[1] and water_xy[2] <= y <= water_xy[3]
                                for x, y in intersections), "water doesn't cover full shoreline")
    check(min_outer_depth >= .46, "shallow outer edge")
    water_gaps = []
    for y in (-5, 5, 15):
        xs = [x for x, yy in intersections if abs(yy - y) <= POSITION_TOL]
        check(len(xs) >= 2 and max(xs) - min(xs) <= POSITION_TOL, (y, xs))
        water_gaps.append(max(xs) - min(xs))
    return {
        "plane_z_BU": WATER, "plane_xy_BU": water_xy, "intersection_x_span_BU":
            [min(p[0] for p in intersections), max(p[0] for p in intersections)],
        "coast_joint_intersection_gap_BU": max(water_gaps),
        "bottom_coverage_BU2": (water_xy[1] - water_xy[0]) * (water_xy[3] - water_xy[2]),
        "bottom_coverage_method": "Full 10 × 40 rectangle covered by four audited adjoining terrain grids.",
        "east_edge_depth_BU": [min_outer_depth, max_outer_depth], "east_edge_vertices_checked": vertices_checked,
    }


def studio(scene, root):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 10
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = "AgX"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.world = bpy.data.worlds.new("Overcast pale sky")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (.59, .68, .71, 1)
    background.inputs["Strength"].default_value = .55
    group = collection("04 | Review cameras and lights", root)
    sun = bpy.data.lights.new("Low soft daylight", "SUN")
    sun.energy, sun.angle = 1.5, .34
    key = obj(group, sun.name, sun)
    key.rotation_euler = Vector((.66, .43, -1)).to_track_quat("-Z", "Y").to_euler()
    return group


def render(scene, cam, folder, name, size, samples=12):
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.cycles.samples = samples
    scene.render.filepath = str(folder / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    bpy.context.view_layer.update()


def route_points():
    """Catmull-Rom interpolation with clamped end tangents for the review-only route."""
    points = [Vector(point) for point in ROUTE]
    path = []
    for i in range(len(points) - 1):
        a, b, c, d = points[max(0, i - 1)], points[i], points[i + 1], points[min(i + 2, len(points) - 1)]
        for j in range(24):
            t = j / 24
            path.append(.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t ** 2
                               + (d - a + 3 * (b - c)) * t ** 3))
    return path + points[-1:]


def mark_route(group, tiles, path):
    from mathutils.bvhtree import BVHTree

    terrain = {}
    for key, item in tiles.items():
        terrain[key] = BVHTree.FromPolygons([item.location + v.co for v in item.data.vertices],
                                           [tuple(p.vertices) for p in item.data.polygons],
                                           all_triangles=True)
    floor_heights = []
    for x, y in path:
        tile = (math.floor((x + 25) / SIDE), math.floor((y + 15) / SIDE))
        point, *_ = terrain[tile].ray_cast(Vector((x, y, 2)), Vector((0, 0, -1)), 4)
        check(point is not None, ("route missed ground", x, y))
        floor_heights.append(point.z)
    marker_height = 1 / SCALE
    check(max(floor_heights) < marker_height, ("buried path", max(floor_heights)))
    markers = paint("Review | path warm gold", "E5B97C", emission=True)
    # Match the App's marker dimensions and height. Spacing is for this sample route.
    vertices, faces = [], []
    half_width, half_height = 2.5 / SCALE, .6 / SCALE
    for k in range(0, len(path), 3):
        x, y = path[k]
        base = len(vertices)
        for dz in (-half_height, half_height):
            for dx, dy in ((-half_width, -half_width), (half_width, -half_width),
                           (half_width, half_width), (-half_width, half_width)):
                vertices.append((x + dx, y + dy, marker_height + dz))
        faces.extend(tuple(base + i for i in face)
                     for face in ((4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
                                  (2, 3, 7, 6), (3, 0, 4, 7)))
    route = simple_mesh(group, "Review path | code-size world marks", vertices, faces, markers)
    return route, {
        "centerline_samples": len(path),
        "rendered_mark_count": len(vertices) // 8,
        "terrain_range_BU": [min(floor_heights), max(floor_heights)],
        "min_center_clearance_BU": marker_height - max(floor_heights),
        "marker_dimensions_game_units": [5, 5, 1.2],
        "marker_center_height_game_units": 1.0,
    }


def add_goose(group):
    with bpy.data.libraries.load(str(CHR / "CHR-001_goose_rig.blend"), link=False) as (_, target):
        target.objects = ["Goose_LOD0", "GooseRig"]
    goose, rig = target.objects
    group.objects.link(rig)
    group.objects.link(goose)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    frozen = bpy.data.meshes.new_from_object(goose.evaluated_get(depsgraph))
    bird = obj(group, "Review | CHR-001 neutral pose", frozen)
    bpy.data.objects.remove(goose, do_unlink=True)
    bpy.data.objects.remove(rig, do_unlink=True)
    return bird


def route_pose(cam, bird, path, index):
    location = path[index]
    direction = (path[min(index + 6, len(path) - 1)] - path[max(0, index - 6)]).normalized()
    pose_at(cam, bird, location, direction)


def pose_at(cam, bird, location, direction):
    follow(cam, location, direction)
    bird.location = (*location, 8 / SCALE)
    bird.rotation_euler.z = math.atan2(-direction.x, direction.y)


def load_materials():
    manifest = json.loads((MAT / "asset_manifest.json").read_text())
    blend = MAT / "MAT-003_wetland_rock.blend"
    with bpy.data.libraries.load(str(blend), link=False) as (_, target):
        target.materials = list(SURFACES)
    materials, sources = {}, {}
    for name, mat in zip(SURFACES, target.materials):
        texture = next(n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE")
        relative = manifest["materials"][name]["file"]
        source = MAT / relative
        digest = file_hash(source)
        check(texture.extension == "REPEAT" and texture.image.size[:] == (1024, 1024)
              and texture.image.colorspace_settings.name == "sRGB", name)
        shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        check(abs(shader.inputs["Roughness"].default_value - manifest["materials"][name]["roughness"]) < 1e-6,
              (name, "roughness"))
        check(sha256(texture.image.packed_file.data).hexdigest() == digest == manifest["files"][relative], name)
        texture.image.filepath = "//../../MAT-003/v001/" + relative
        materials[name] = mat
        sources[name] = {"path_relative_to_candidate": "../../MAT-003/v001/" + relative, "sha256": digest,
                         "dimensions": [1024, 1024], "color_space": "sRGB", "wrap": "repeat U/V",
                         "roughness": manifest["materials"][name]["roughness"]}
    return materials, sources


def assign_materials(modules, materials):
    for module in modules.values():
        for i, mat in enumerate(materials.values()):
            module.data.materials[i] = mat


def export_modules(modules, output):
    for name, module in modules.items():
        bpy.ops.object.select_all(action="DESELECT")
        module.select_set(True)
        bpy.context.view_layer.objects.active = module
        status = bpy.ops.export_scene.gltf(filepath=str(output / f"ENV-001_{name}.glb"), export_format="GLB",
                                          use_selection=True, export_yup=True, export_extras=True,
                                          export_image_format="AUTO", export_animations=False)
        check(status == {"FINISHED"}, (name, status))
        module.select_set(False)


def signature(mesh):
    """Match triangles by vertex position and material, preserving winding and corner data."""
    mesh.calc_loop_triangles()
    result = {}
    for tri in mesh.loop_triangles:
        corners = []
        for index in tri.loops:
            loop = mesh.loops[index]
            p = mesh.vertices[loop.vertex_index].co.copy()
            corners.append((p, mesh.corner_normals[index].vector.copy(), mesh.uv_layers.active.data[index].uv.copy()))
        pivot = min(range(3), key=lambda i: tuple(corners[i][0]))
        corners = corners[pivot:] + corners[:pivot]
        key = tuple(tuple(round(v, 5) for v in p) for p, _, _ in corners)
        check(key not in result, (mesh.name, key))
        result[key] = (mesh.materials[tri.material_index].name.split(".")[0], corners)
    return result


def glb_chunks(path):
    raw = path.read_bytes()
    check(struct.unpack_from("<4sII", raw) == (b"glTF", 2, len(raw)), path.name)
    json_len, typ = struct.unpack_from("<I4s", raw, 12)
    check(typ == b"JSON", path.name)
    doc = json.loads(raw[20:20 + json_len])
    blob_len, typ = struct.unpack_from("<I4s", raw, 20 + json_len)
    check(typ == b"BIN\x00", path.name)
    return doc, raw[28 + json_len:28 + json_len + blob_len]


def inspect_glb(path, name, box, source_triangles, source_images):
    doc, blob = glb_chunks(path)
    node, = doc["nodes"]
    check(node["name"] == name and node["mesh"] == 0 and "matrix" not in node, node)
    for field, default in (("translation", [0, 0, 0]), ("scale", [1, 1, 1]), ("rotation", [0, 0, 0, 1])):
        check(node.get(field, default) == default, (name, node))
    check(not doc.get("animations") and not doc.get("cameras") and not doc.get("extensions"), name)
    result = {}
    expected_positions = {tuple(round(v, 5) for v in (p.x, p.z, -p.y))
                          for _, corners in source_triangles.values() for p, _, _ in corners}
    raw_positions = set()
    triangle_count = 0
    raw_min, raw_max = [math.inf] * 3, [-math.inf] * 3
    primitives = doc["meshes"][0]["primitives"]
    for primitive in primitives:
        attrs = primitive["attributes"]
        check(primitive.get("mode", 4) == 4 and {"POSITION", "NORMAL", "TEXCOORD_0"} <= attrs.keys(), name)
        access = doc["accessors"][attrs["POSITION"]]
        pos_view = doc["bufferViews"][access["bufferView"]]
        start = pos_view.get("byteOffset", 0) + access.get("byteOffset", 0)
        stride = pos_view.get("byteStride", 12)
        check(access["componentType"] == 5126 and access["type"] == "VEC3", name)
        for index in range(access["count"]):
            position = struct.unpack_from("<3f", blob, start + index * stride)
            raw_positions.add(tuple(round(value, 5) for value in position))
        triangle_count += doc["accessors"][primitive["indices"]]["count"] // 3
        for i in range(3):
            raw_min[i] = min(raw_min[i], access["min"][i])
            raw_max[i] = max(raw_max[i], access["max"][i])
        material = doc["materials"][primitive["material"]]
        pbr = material["pbrMetallicRoughness"]
        tex = doc["textures"][pbr["baseColorTexture"]["index"]]
        image = doc["images"][tex["source"]]
        view = doc["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        digest = sha256(blob[start:start + view["byteLength"]]).hexdigest()
        source = source_images[material["name"]]
        check(image["mimeType"] == "image/png" and digest == source["sha256"], (name, material["name"], digest))
        check(abs(pbr.get("roughnessFactor", 1) - source["roughness"]) < 1e-6
              and pbr.get("metallicFactor", 1) == 0, (name, pbr))
        sampler = doc["samplers"][tex["sampler"]] if "sampler" in tex else {}
        check(all(sampler.get(key, 10497) == 10497 for key in ("wrapS", "wrapT")), (name, sampler))
        result[material["name"]] = digest
    expected_materials = {material for material, _ in source_triangles.values()}
    check(set(result) == expected_materials and len(doc["images"]) == len(result), (name, result))
    check(raw_positions == expected_positions, (name, "GLB coordinate conversion"))
    check(triangle_count == 512, (name, triangle_count))
    want_min = [box[0][0], box[2][0], -box[1][1]]
    want_max = [box[0][1], box[2][1], -box[1][0]]
    check(max(abs(a - b) for a, b in zip(raw_min + raw_max, want_min + want_max)) <= POSITION_TOL,
          (name, raw_min, raw_max))
    return {"raw_gltf_bounds_X_Y_Z": list(zip(raw_min, raw_max)), "triangle_count": triangle_count,
            "coordinate_samples_checked": len(raw_positions), "embedded_png_sha256": result}


def verify_roundtrip(folder, modules, source_images):
    reference = {name: signature(module.data) for name, module in modules.items()}
    imported = {}
    checks = {}
    for name in NAMES:
        path = folder / f"ENV-001_{name}.glb"
        raw = inspect_glb(path, name, tile_box(modules[name].data), reference[name], source_images)
        before = set(bpy.data.objects)
        status = bpy.ops.import_scene.gltf(filepath=str(path), import_pack_images=True, merge_vertices=False)
        check(status == {"FINISHED"}, (name, status))
        item, = set(bpy.data.objects) - before
        check(item.type == "MESH" and item.name.split(".")[0] == name and item.parent is None, item.name)
        measured = audit_surface(item)
        actual = signature(item.data)
        check(reference[name].keys() == actual.keys(), (name, "geometry or winding"))
        pos = normal = uv = 0.0
        for key, (material, corners) in reference[name].items():
            other_material, other_corners = actual[key]
            check(material == other_material, (name, key, material, other_material))
            for (a, n, t), (b, m, s) in zip(corners, other_corners):
                pos = max(pos, (a - b).length)
                normal = max(normal, angle(n, m))
                uv = max(uv, (t - s).length)
        check(pos <= POSITION_TOL and normal <= NORMAL_TOL and uv <= UV_TOL, (name, pos, normal, uv))
        imported[name] = item
        checks[name] = dict(raw, blender_import=measured, max_position_error_BU=pos,
                            max_normal_angle_deg=normal, max_uv_error=uv)
    return imported, checks


def add_cameras(scene, review):
    group = studio(scene, review)
    cams = {
        "top": camera(group, "Top | N up", (-5, 5, 60), (-5, 5, 0), 45.5),
        "seam": camera(group, "Detail | grass, bank and submerged seam",
                       (14, -12, 6.5), (5.5, -4.75, -.15), 12.6),
        "game": camera(group, "Gameplay | fixed rear", (0, 0, 1), (0, 1, 0)),
    }
    return cams


def add_water(group):
    material = paint("Review | translucent reference water", "88B7B3")
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    surface = nodes.get("Principled BSDF")
    surface.inputs["Roughness"].default_value = .4
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = .43
    links.new(surface.outputs["BSDF"], mix.inputs[1])
    links.new(transparent.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], nodes.get("Material Output").inputs["Surface"])
    return rectangle(group, "Review only | water level -0.18 BU", 5, 15, -15, 25, WATER, material)


def add_context(group, modules, water):
    """Frame only the certified sample in diagnostic views; extend the land for the long gameplay lens."""
    context = collection("05 | Fixed camera backdrop only", group)
    for row in range(-1, 13):
        for col in range(-9, 4):
            if 0 <= col <= 3 and 0 <= row <= 3:
                continue
            name = "Shore" if col == 3 else "Flat"
            obj(context, f"Backdrop | {col},{row}", modules[name].data, (col * SIDE - 20, row * SIDE - 10, 0))
    water_mat = water.data.materials[0]
    rectangle(context, "Review | water beyond sample E", 15, 350, -30, 350, WATER, water_mat)
    for lower, upper in ((-25, -15), (25, 125)):
        rectangle(context, "Review | water beyond sample N/S", 5, 15, lower, upper, WATER, water_mat)
    wash = paint("Review | submerged backdrop", "829295")
    rectangle(context, "Review | submerged backdrop", 15, 350, -30, 350, FLOOR, wash)
    return context


def show_context(group, show):
    group.hide_render = not show
    group.hide_viewport = not show


def frame_path_report(scene, cam, route):
    rendered = []
    for polygon in route.data.polygons:
        if polygon.normal.z <= .99:
            continue
        points = [world_to_camera_view(scene, cam, route.data.vertices[i].co) for i in polygon.vertices]
        if not all(p.z > 0 and 0 < p.x < 1 and 0 < p.y < 1 for p in points):
            continue
        x = [p.x * GAME_SIZE[0] for p in points]
        y = [p.y * GAME_SIZE[1] for p in points]
        rendered.append((max(x) - min(x), max(y) - min(y)))
    check(rendered, "no visible path markers")
    return {"frame_px": list(GAME_SIZE), "fully_in_frame_marks": len(rendered),
            "mark_bbox_width_px": [min(p[0] for p in rendered), max(p[0] for p in rendered)],
            "mark_bbox_height_px": [min(p[1] for p in rendered), max(p[1] for p in rendered)]}


def set_preview_workspace(scene, cam):
    scene.camera = cam
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                view = area.spaces.active
                view.region_3d.view_distance = 45
                view.region_3d.view_location = (-5, 5, 0)
                view.region_3d.view_perspective = "CAMERA"
                view.region_3d.view_camera_zoom = 9
                view.shading.color_type = "MATERIAL"
                view.overlay.show_overlays = False


def fresh_scene(name):
    scene = bpy.data.scenes.new(name)
    scene.unit_settings.system = "NONE"
    scene.unit_settings.scale_length = 1
    bpy.context.window.scene = scene
    return scene


def build(output, video_frames, draft):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.preferences.filepaths.temporary_directory = str(output)
    library = bpy.context.scene
    library.name = "ENV-001 | Module library"
    library.unit_settings.system = "NONE"
    originals = collection("ENV-001 | Four export meshes at origin", library.collection)
    gray = {name: paint("Graybox | " + name, hex_code) for name, hex_code in zip(
        SURFACES, ("ADAE9D", "999687", "A2A9A4", "818A8C", "829597"))}
    modules = {name: build_module(name, originals, gray) for name in NAMES}
    bpy.context.view_layer.update()
    geometry = {name: audit_surface(item) for name, item in modules.items()}
    source_joins = all_joins(modules)

    scene = fresh_scene("ENV-001 | Review sample")
    root = collection("ENV-001 | Review assembly", scene.collection)
    _, tiles, sample_checks = new_stage(modules, root)
    water_group = collection("02 | Reference water", root)
    water = add_water(water_group)
    water_checks = cover_underwater(tiles)
    evidence = collection("03 | Review path and CHR-001 scale", root)
    path = route_points()
    route, route_checks = mark_route(evidence, tiles, path)
    bird = add_goose(evidence)
    bird.hide_render = True
    cams = add_cameras(scene, root)
    context = add_context(root, modules, water)
    studio_floor = rectangle(root, "Review | survey background", -200, 200, -200, 200, -1.6,
                             paint("Review | survey neutral", "D2DBD7"))
    show_context(context, False)
    evidence.hide_render = True
    render(scene, cams["top"], output, "graybox_top", (1080, 1080))
    render(scene, cams["seam"], output, "graybox_seam", (1100, 650))
    evidence.hide_render = False
    bird.hide_render = False
    studio_floor.hide_render = True
    show_context(context, True)
    route_pose(cams["game"], bird, path, 94)
    render(scene, cams["game"], output, "graybox_fixed_rear", GAME_SIZE)

    materials, sources = load_materials()
    assign_materials(modules, materials)
    show_context(context, False)
    studio_floor.hide_render = False
    bird.hide_render = True
    render(scene, cams["top"], output, "preview_top", (1280, 1280), 20)
    evidence.hide_render = True
    render(scene, cams["seam"], output, "preview_seam", (1400, 800), 22)
    slopes = camera(cams["seam"].users_collection[0], "Detail | ridge and slope seam",
                    (-15, -17, 5), (-15, -5, .02), 16)
    render(scene, slopes, output, "preview_slope_join", (1200, 680), 20)
    studio_floor.hide_render = True
    evidence.hide_render = False
    bird.hide_render = False
    show_context(context, True)
    for index, label in ((34, "entry"), (94, "shore"), (149, "bend")):
        route_pose(cams["game"], bird, path, index)
        render(scene, cams["game"], output, f"preview_fixed_rear_{label}", GAME_SIZE, 24)
        route_checks[label] = frame_path_report(scene, cams["game"], route)
    if video_frames:
        sequence = output / "frames"
        sequence.mkdir()
        video_path = path[33:170]
        distances = [0.0]
        for start, end in zip(video_path, video_path[1:]):
            distances.append(distances[-1] + (end - start).length)
        segment = 0
        for frame in range(video_frames):
            distance = distances[-1] * frame / (video_frames - 1)
            while distance > distances[segment + 1]:
                segment += 1
            start, end = distances[segment:segment + 2]
            mix = (distance - start) / (end - start)
            location = video_path[segment].lerp(video_path[segment + 1], mix)
            index = segment + 33
            heading_a = (path[index + 6] - path[index - 6]).normalized()
            heading_b = (path[index + 7] - path[index - 5]).normalized()
            pose_at(cams["game"], bird, location, heading_a.lerp(heading_b, mix).normalized())
            render(scene, cams["game"], sequence, f"{frame:04}", GAME_SIZE, 10)

    if draft:
        return

    bpy.context.window.scene = library
    export_modules(modules, output)
    bpy.context.window.scene = scene
    route_pose(cams["game"], bird, path, 94)
    set_preview_workspace(scene, cams["game"])
    scene.render.resolution_x, scene.render.resolution_y = GAME_SIZE
    scene.render.filepath = "//review.png"
    bpy.ops.wm.save_as_mainfile(filepath=str(output / f"{STEM}.blend"))
    save_qa(output, sources, geometry, source_joins, sample_checks, water_checks, route_checks)


def save_qa(output, sources, geometry, joins, sample, water, route):
    fresh_scene("ENV-001 | Final GLB roundtrip")
    scene = bpy.context.scene
    originals = {name: bpy.data.objects[name] for name in NAMES}
    imported, roundtrip = verify_roundtrip(output, originals, sources)
    imported_joins = all_joins(imported)
    for item in imported.values():
        item.hide_render = True
        item.hide_set(True)
    root = collection("Roundtrip | Snap imported meshes", scene.collection)
    _, tiles, assembled = new_stage(imported, root)
    water_group = collection("Roundtrip | reference water", root)
    add_water(water_group)
    water_after = cover_underwater(tiles)
    cams = add_cameras(scene, root)
    rectangle(root, "Review | survey background", -200, 200, -200, 200, -1.6,
              paint("Roundtrip | survey neutral", "D2DBD7"))
    render(scene, cams["seam"], output, "preview_roundtrip_seam", (1400, 800), 22)

    qa = {
        "id": "ENV-001", "version": "v001", "status": "needs_review",
        "blender": bpy.app.version_string,
        "tolerances": {"vertex_or_height_BU": POSITION_TOL, "normal_degrees": NORMAL_TOL,
                       "uv": UV_TOL, "projected_area_BU2": 5e-4},
        "graybox_before_materials": {"result": "pass", "modules": geometry,
                                      "compatibility_joins": joins, "assembly": sample,
                                      "reference_water": water, "route_geometry": route},
        "final_glb_roundtrip": {"result": "pass", "modules": roundtrip,
                                "compatibility_joins": imported_joins,
                                "reassembled": assembled, "reference_water": water_after},
        "app_baseline": {"origin": "plans/active/goose-preview-model-cleanup.md",
                         "device": "iPhone 18 Pro Simulator", "os": "iOS 27.2",
                         "prior_test_count": 340, "prior_failures": 0, "rerun_in_this_task": False},
        "pending": ["Paco review of shape, route reading, material contrast and repetition.",
                    "Compare apparent route with RealityKit path and actual traversability/collision.",
                    "USDZ, App integration, ENV-003 shoreline treatment and iPhone/iPad verification."],
    }
    write_json(output / "qa.json", qa)
    manifest = {
        "id": "ENV-001", "version": "v001", "name": "通用地形与岸线基座", "status": "needs_review",
        "execution_order_1_based": 15, "depends": ["MAT-003/v001"],
        "dependency_status": {"MAT-003/v001": "needs_review"},
        "review_reference": {"id": "CHR-001/v001", "path": "../../CHR-001/v001/CHR-001_goose_rig.blend",
                             "sha256": file_hash(CHR / "CHR-001_goose_rig.blend")},
        "source": "Original procedural mesh construction in Blender based on production spec p.9.",
        "rights": "Project-original geometry; unchanged packed MAT-003 project images; CHR-001 review only.",
        "blender": bpy.app.version_string,
        "asset_scene": "ENV-001 | Module library", "review_scene": "ENV-001 | Review sample",
        "interface": {
            "units": "BU", "footprint_xy_BU": [SIDE, SIDE], "center_pivot_xyz": [0, 0, 0],
            "pitch_BU": SIDE, "allowed_yaw_deg": [0], "object_scale": [1, 1, 1],
            "edge_sample_count": CELLS + 1, "edge_sample_step_BU": STEP,
            "blender_to_gltf_xyz": ["x", "z", "-y"], "land_datum_BU": 0.0,
            "reference_water_BU": WATER, "shore_floor_BU": FLOOR,
            "edge_types": {"L": "horizontal land at z=0", "C": "shore cross-section increasing x into water",
                           "W": "open submerged terminal at z=-0.65; no mate in v001"},
            "shore_edge_z_BU_in_increasing_local_x": [
                shore_profile(i * STEP - HALF) for i in range(CELLS + 1)],
            "uv": {"blender": ["(x+5)/10", "(y+5)/10"], "address": "repeat", "period_BU": 10},
        },
        "review_conversion": {
            "game_units_per_BU": SCALE, "CHR_bill_to_tail_BU": .9900, "leader_bill_to_tail_game_units": 27.5,
            "camera_distance_parameter_game_units": 180, "camera_pitch_parameter_rad": .48,
            "vertical_fov_deg": 50, "eye_height_game_units": 180 * math.sin(.48),
            "target_height_game_units": 6, "bird_root_height_game_units": 8, "depth_lift": 0,
            "landscape_keyframe_px": list(GAME_SIZE),
        },
        "source_material_library": {"path": "../../MAT-003/v001/MAT-003_wetland_rock.blend",
                                    "sha256": file_hash(MAT / "MAT-003_wetland_rock.blend"),
                                    "sha256_listed_by_mat_manifest": json.loads(
                                        (MAT / "asset_manifest.json").read_text())["files"]["MAT-003_wetland_rock.blend"]},
        "textures": sources,
        "modules": {name: {"file": f"ENV-001_{name}.glb", "edges": EDGES[name],
                           "bounds_xyz_BU": geometry[name]["bounds_BU"],
                           "triangles": geometry[name]["triangle_count"],
                           "materials": sorted(roundtrip[name]["embedded_png_sha256"])} for name in NAMES},
        "files": {item.name: file_hash(item) for item in sorted(output.iterdir()) if item.is_file()},
    }
    write_json(output / "asset_manifest.json", manifest)


def verify_only(candidate, output):
    bpy.ops.wm.open_mainfile(filepath=str(candidate / f"{STEM}.blend"))
    manifest = json.loads((candidate / "asset_manifest.json").read_text())
    source = {name: bpy.data.objects[name] for name in NAMES}
    fresh_scene("ENV-001 | Independent GLB verification")
    modules, report = verify_roundtrip(candidate, source, manifest["textures"])
    joins = all_joins(modules)
    for item in modules.values():
        item.hide_render = True
        item.hide_set(True)
    scene = bpy.context.scene
    root = collection("Reassembly", scene.collection)
    _, tiles, sample = new_stage(modules, root)
    write_json(output / "recheck.json", {"result": "pass", "modules": report, "joins": joins,
                                       "sample": sample, "water": cover_underwater(tiles)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Empty directory for generated assets or recheck.json")
    parser.add_argument("--video-frames", type=int, default=0)
    parser.add_argument("--draft", action="store_true", help="Render stills without exporting")
    parser.add_argument("--verify", type=Path, help="Independently open and recheck an existing candidate")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    check(not any(output.iterdir()), f"Output must be empty: {output}")
    check(args.video_frames != 1 and args.video_frames >= 0, "video frames must be zero or at least two")
    if args.verify:
        verify_only(args.verify.resolve(), output)
    else:
        build(output, args.video_frames, args.draft)


if __name__ == "__main__":
    main()
