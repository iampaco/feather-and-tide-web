"""Build and audit the three ENV-002 wetland terrain modules in Blender."""
import argparse
from itertools import combinations, product
import json
import math
from pathlib import Path
import runpy
import struct
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import convex_hull_2d


HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
ENV1 = LIBRARY / "ENV-001/v001"
ANM = LIBRARY / "ANM-007/v001/ANM-007_landing.blend"
BASE = runpy.run_path(str(ENV1 / "ENV-001_generate.py"))
SIDE, HALF, STEP, CELLS = (BASE[name] for name in ("SIDE", "HALF", "STEP", "CELLS"))
WATER, FLOOR, SCALE, GAME_SIZE = (BASE[name] for name in ("WATER", "FLOOR", "SCALE", "GAME_SIZE"))
SURFACES = BASE["SURFACES"]
NAMES = ("StartMudflat", "ReedIslet", "RestPatch")
LEGACY = ("Flat", "GentleSlope", "Shore", "Ridge")
EDGES = dict(BASE["EDGES"])
EDGES.update({name: dict(W="L", E="L", S="L", N="L") for name in NAMES})
EDGES["ReedIslet"] = dict(EDGES["Shore"])
# audit_join uses this shared dictionary for the reported connector type.
BASE["EDGES"].update({name: EDGES[name] for name in NAMES})
check = BASE["check"]
smooth = BASE["smooth"]
collection = BASE["collection"]
obj = BASE["obj"]
paint = BASE["paint"]
file_hash = BASE["file_hash"]
write_json = BASE["write_json"]
STEM = "ENV-002_wetland"
FOOT_GAP_TOL = .009
PENETRATION_TOL = .003
MIN_EDGE_WATER_GAP = .040
PAIR_GAP_TOL = .030
UV_TOL = BASE["UV_TOL"]
POSITION_TOL = BASE["POSITION_TOL"]
NORMAL_TOL = BASE["NORMAL_TOL"]
IMPORT_NORMAL_TOL = NORMAL_TOL
RAW_NORMAL_TOL = NORMAL_TOL
POSTURE = ("Land_Mudflat", 81)


def footprint(name, x, y):
    """Rounded, asymmetric distance fields. A radius <= the flat cutoff is a common contact level."""
    if name == "ReedIslet":
        x -= .53 + .31 * math.sin(.68 * y + .2)
        return (abs(x / 2.47) ** 3 + abs((y + .04) / 3.88) ** 3) ** (1 / 3)
    if name == "StartMudflat":
        x += .34 + .27 * math.sin(.92 * y)
        y -= .10 - .19 * math.sin(.81 * x)
        return (abs(x / 4.0) ** 2.7 + abs(y / 3.72) ** 2.7) ** (1 / 2.7)
    x += .53 - .33 * math.sin(.8 * y + .8)
    y += .22 + .23 * math.sin(x)
    return (abs(x / 3.65) ** 2.55 + abs(y / 3.81) ** 2.55) ** (1 / 2.55)


def basin(x, y, center, radii):
    radius = math.hypot((x - center[0]) / radii[0], (y - center[1]) / radii[1])
    return 1 - smooth(radius)


def height(name, x, y):
    radius = footprint(name, x, y)
    collar = smooth((HALF - STEP - max(abs(x), abs(y))) / .85)
    if name == "ReedIslet":
        base = BASE["height"]("Shore", x, y)
        channel = smooth((1.58 - radius) / .32)
        channel *= smooth((y + 3.95) / .92) * smooth((3.95 - y) / .92)
        floor = min(base, -.46 * channel)
        crown = 1 - smooth((radius - .83) / .38)
        return base + (floor * (1 - crown) - base) * collar
    if name == "StartMudflat":
        low = max(basin(x, y, (3.32, 1.75), (1.29, 2.35)),
                  basin(x, y, (-2.74, 2.80), (1.25, 1.41)))
        dip = -.39 * low * smooth((radius - .73) / .16)
    else:
        low = max(basin(x, y, (2.74, .87), (1.65, 2.56)),
                  basin(x, y, (2.80, -2.73), (1.25, 1.24)),
                  basin(x, y, (-3.20, 1.78), (1.10, 1.67)))
        dip = -.48 * low * smooth((radius - .69) / .16)
    return min(0.0, collar * dip)


def surface(name, x, y, z):
    if max(abs(x), abs(y)) > HALF - STEP:
        if name == "ReedIslet":
            return BASE["surface"]("Shore", x, y)
        return "GrassFlat"
    radius = footprint(name, x, y)
    if z < WATER - .025:
        return "ShallowMargin"
    if name == "ReedIslet":
        if z > -.045 and radius > 1.45:
            return BASE["surface"]("Shore", x, y)
        if radius < .69 + .065 * math.sin(2.25 * y + .7 * x):
            return "GrassFlat"
        return "MudBank"
    if name == "StartMudflat" and radius < .91 + .07 * math.sin(1.28 * y - 1.15 * x):
        return "MudBank"
    if name == "RestPatch":
        if z < -.045 or (.85 < radius < 1.0 and x > 1.0):
            return "MudBank"
        if radius > .69 and math.sin(1.74 * x + .7 * y) + .67 * math.cos(1.4 * y) > 1.11:
            return "MossStone"
    return "MudBank" if z < -.055 else "GrassFlat"


def build_module(name, group, materials):
    coordinates = [i * STEP - HALF for i in range(CELLS + 1)]
    vertices = [(x, y, height(name, x, y)) for y in coordinates for x in coordinates]
    faces = []
    for row, col in product(range(CELLS), repeat=2):
        a = row * (CELLS + 1) + col
        b, c, d = a + 1, a + CELLS + 2, a + CELLS + 1
        faces.extend(((a, b, c), (a, c, d)) if (row + col) % 2 == 0 else ((a, b, d), (b, c, d)))
    mesh = bpy.data.meshes.new(name + "_surface")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uvs = mesh.uv_layers.new(name="TerrainUV")
    for mat in materials.values():
        mesh.materials.append(mat)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
        polygon.material_index = SURFACES.index(surface(name, *polygon.center))
        for index in polygon.loop_indices:
            x, y, _ = vertices[mesh.loops[index].vertex_index]
            uvs.data[index].uv = ((x + HALF) / SIDE, (y + HALF) / SIDE)
    normals = [(0, 0, 0)] * len(vertices)
    for index, (x, y, _) in enumerate(vertices):
        if abs(x) == HALF or abs(y) == HALF:
            n = (0, 0, 1)
            if name == "ReedIslet" and abs(x) != HALF:
                f = BASE["shore_profile"]
                gradient = (f(x + STEP) - f(x - STEP)) / (2 * STEP)
                n = Vector((-gradient, 0, 1)).normalized()
            normals[index] = n
    mesh.normals_split_custom_set_from_vertices(normals)
    tile = obj(group, name, mesh)
    tile["edges_W_E_S_N"] = "/".join(EDGES[name][side] for side in "WESN")
    tile["water_reference_BU"] = WATER
    tile["edge_vertex_step_BU"] = STEP
    tile.asset_mark()
    tile.asset_data.description = f"ENV-002/v001 | {name} | 10 BU centre snap"
    return tile


def land_mesh(mesh):
    return BVHTree.FromPolygons([v.co for v in mesh.vertices], [tuple(p.vertices) for p in mesh.polygons],
                                all_triangles=True)


def terrain_at(tree, x, y):
    point, _, _, _ = tree.ray_cast(Vector((x, y, 1)), Vector((0, 0, -1)), 3)
    return None if point is None else float(point.z)


def load_standing_mesh(group):
    with bpy.data.libraries.load(str(ANM), link=False) as (_, target):
        target.objects = ["Goose_LOD0", "GooseRig"]
        target.actions = [POSTURE[0]]
    goose, rig = target.objects
    action, = target.actions
    group.objects.link(rig)
    group.objects.link(goose)
    rig.animation_data_clear()
    rig.animation_data_create().action = action
    rig.animation_data.action_slot = action.slots[0]
    bpy.context.scene.frame_set(POSTURE[1])
    bpy.context.view_layer.update()
    foot_groups = [goose.vertex_groups["Foot." + side].index for side in ("L", "R")]
    foot_indices = [
        [v.index for v in goose.data.vertices if any(g.group == group_id and g.weight > .99 for g in v.groups)]
        for group_id in foot_groups
    ]
    evaluated = goose.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = bpy.data.meshes.new_from_object(evaluated)
    mesh.name = "Review | ANM-007 standing pose"
    check(len(mesh.vertices) == len(goose.data.vertices), "foot IDs no longer match evaluated mesh")
    points = [v.co.copy() for v in mesh.vertices]
    soles = []
    # The foot mesh has a rounded sole. Sample its lower vertices and lower-facing triangle interiors.
    mesh.calc_loop_triangles()
    for indices in foot_indices:
        floor = min(points[i].z for i in indices)
        selected = {i for i in indices if points[i].z <= floor + .006}
        samples = [points[i] for i in sorted(selected)]
        for triangle in mesh.loop_triangles:
            if triangle.normal.z < -.2 and set(triangle.vertices) <= selected:
                a, b, c = [points[i] for i in triangle.vertices]
                samples += [(a + b + c) / 3, (a + b) / 2, (b + c) / 2, (c + a) / 2]
        check(len(samples) >= 4, ("too few sole probes", len(samples)))
        soles.append(samples)
    for item in (goose, rig):
        bpy.data.objects.remove(item, do_unlink=True)
    return mesh, points, soles


def moved(point, center, yaw, size, lift=0.0):
    c, s = math.cos(yaw), math.sin(yaw)
    return Vector((center[0] + size * (c * point.x - s * point.y),
                   center[1] + size * (s * point.x + c * point.y), size * point.z + lift))


def contact(tree, samples, center, yaw, size):
    foot_probes = []
    for sole in samples:
        transformed = [moved(v, center, yaw, size) for v in sole]
        ground = [terrain_at(tree, v.x, v.y) for v in transformed]
        if None in ground:
            return None
        foot_probes.append(list(zip(transformed, ground)))
    lift = max(z - point.z for foot in foot_probes for point, z in foot)
    feet = []
    for foot in foot_probes:
        feet.append({
            "sample_count": len(foot),
            "contact_gap_BU": min(point.z + lift - z for point, z in foot),
            "max_sole_probe_gap_BU": max(point.z + lift - z for point, z in foot),
            "min_ground_above_water_BU": min(z - WATER for _, z in foot),
        })
    if any(f["contact_gap_BU"] > FOOT_GAP_TOL or f["min_ground_above_water_BU"] < MIN_EDGE_WATER_GAP
           or f["max_sole_probe_gap_BU"] > FOOT_GAP_TOL + .006 for f in feet):
        return None
    return lift, feet


def place(tree, points, soles, center, yaw, size, required=True):
    fit = contact(tree, soles, center, yaw, size)
    if fit is None and not required:
        return None
    check(fit is not None, ("unsupported stance", center, yaw, size))
    lift, feet = fit
    transformed = [moved(v, center, yaw, size, lift) for v in points]
    clearance = []
    for v in transformed:
        z = terrain_at(tree, v.x, v.y)
        if z is None and not required:
            return None
        check(z is not None, ("posed mesh over tile boundary", center, v))
        clearance.append(v.z - z)
    if min(clearance) < -PENETRATION_TOL and not required:
        return None
    check(min(clearance) >= -PENETRATION_TOL, ("stance penetrates terrain", center, min(clearance)))
    xy = [v.xy for v in transformed]
    hull = [xy[i] for i in convex_hull_2d(xy)]
    return hull, {"xy_BU": list(center), "yaw_degrees": math.degrees(yaw), "scale": size,
                  "root_z_BU": lift, "min_mesh_vertex_clearance_BU": min(clearance), "feet": feet}


def interval_separation(first, second):
    """Positive interval separation on at least one hull normal proves the 3D meshes are disjoint."""
    gaps = []
    for hull in (first, second):
        for i, p in enumerate(hull):
            edge = hull[(i + 1) % len(hull)] - p
            axis = Vector((-edge.y, edge.x)).normalized()
            a, b = [p.dot(axis) for p in first], [p.dot(axis) for p in second]
            gaps.append(max(min(a) - max(b), min(b) - max(a)))
    return max(gaps)


def layout(name):
    x0 = .61 if name == "ReedIslet" else (-.35 if name == "StartMudflat" else -.60)
    locations = []
    stride = 1.09 if name == "ReedIslet" else 1.19
    rows = (-2.05, -.70, .65, 1.95) if name == "ReedIslet" else (-2.20, -.75, .72, 2.17)
    jitter = .05 if name == "ReedIslet" else .13
    for row, y in enumerate(rows):
        for column, dx in enumerate((-stride, 0.0, stride)):
            drift = .14 * math.sin(1.65 * row + column)
            dx += drift
            locations.append((x0 + dx, y + jitter * math.sin(2.1 * column + row)))
    # The rear middle bird is the leader so the other birds are up-frame in the fixed shot.
    indices = (1, 0, *range(2, 12))
    return [(locations[i], math.radians((i * 13 % 25) - 12) if i != 1 else 0) for i in indices]


def audit_flock(tile, points, soles, full_size=False):
    tree = land_mesh(tile.data)
    poses, hulls = [], []
    for i, (center, yaw) in enumerate(layout(tile.name.split(".")[0])):
        size = 1.0 if i == 0 or full_size else .8
        hull, data = place(tree, points, soles, center, yaw, size)
        poses.append(data)
        hulls.append(hull)
    distances = [interval_separation(a, b) for a, b in combinations(hulls, 2)]
    check(len(poses) == 12 and len(distances) == 66 and min(distances) > PAIR_GAP_TOL,
          (tile.name, "flock overlaps", min(distances)))
    return {"birds": poses, "pair_count": len(distances), "min_projected_separating_gap_BU": min(distances)}


def waterline_segments(mesh):
    segments = []
    mesh.calc_loop_triangles()
    for tri in mesh.loop_triangles:
        corners = [mesh.vertices[index].co for index in tri.vertices]
        crossings = [a.lerp(b, (WATER - a.z) / (b.z - a.z)).xy
                     for a, b in zip(corners, corners[1:] + corners[:1]) if (a.z < WATER) != (b.z < WATER)]
        if crossings:
            check(len(crossings) == 2, (mesh.name, "water crossing"))
            segments.append(crossings)
    check(segments, (mesh.name, "no wet geometry"))
    return segments


def near_segment(point, a, b):
    delta = b - a
    return a.lerp(b, max(0.0, min(1.0, (point - a).dot(delta) / delta.length_squared)))


def wet_area(mesh):
    """Clip each triangle by the horizontal review water level and integrate its XY area."""
    wet = 0.0
    for polygon in mesh.polygons:
        corners = [mesh.vertices[index].co for index in polygon.vertices]
        clipped = []
        for a, b in zip(corners, corners[1:] + corners[:1]):
            if a.z < WATER:
                clipped.append(a)
            if (a.z < WATER) != (b.z < WATER):
                clipped.append(a.lerp(b, (WATER - a.z) / (b.z - a.z)))
        if len(clipped) >= 3:
            wet += .5 * abs(sum(a.x * b.y - a.y * b.x for a, b in zip(clipped, clipped[1:] + clipped[:1])))
    check(wet > .15, (mesh.name, "review waterline too small", wet))
    return wet


def audit_edge_stances(tile, points, soles, earlier=None):
    tree = land_mesh(tile.data)
    segments = waterline_segments(tile.data)
    name = tile.name.split(".")[0]
    tested = []
    # Search around the actual sliced waterline, then pin the final stance locations for the GLB recheck.
    if earlier is None:
        candidates = []
        for yaw_index in range(8):
            yaw = yaw_index * math.tau / 8
            ranked = []
            for a, b in segments:
                mid = a.lerp(b, .5)
                tangent = (b - a).normalized()
                n = Vector((tangent.y, -tangent.x))
                for side in (-1, 1):
                    for setback in (.14, .23, .33, .45, .58, .74, .92):
                        center = mid + (setback * side) * n
                        if max(abs(v) for v in center) > 4.24:
                            continue
                        fitted = contact(tree, soles, center, yaw, 1)
                        if fitted is None:
                            continue
                        foot_xy = [moved(v, center, yaw, 1).xy for foot in soles for v in foot]
                        distance = min((p - near_segment(p, c, d)).length
                                       for p in foot_xy for c, d in segments)
                        ranked.append((distance, tuple(center)))
                        break
            for distance, center in sorted(ranked):
                if (all((Vector(center) - Vector(other)).length > .19 for other, _ in candidates)
                        and place(tree, points, soles, center, yaw, 1, required=False) is not None):
                    candidates.append((center, yaw))
                    break
        check(len(candidates) == 8, (name, "not enough distinct shoreline stances", candidates))
    else:
        candidates = [(row["xy_BU"], math.radians(row["yaw_degrees"])) for row in earlier]
    for center, yaw in candidates:
        _, data = place(tree, points, soles, center, yaw, 1)
        foot_xy = [moved(v, center, yaw, 1).xy for foot in soles for v in foot]
        distance = min((p - near_segment(p, a, b)).length for p in foot_xy for a, b in segments)
        check(distance < 1.0, (name, "stance too far from shoreline", distance))
        data["nearest_sole_sample_to_waterline_BU"] = distance
        tested.append(data)
    return tested


def joins(modules, legacy):
    checked = []
    meshes = dict(legacy, **modules)
    for a, b in product(meshes, repeat=2):
        if a in LEGACY and b in LEGACY:
            continue
        for left, right, offset in (("E", "W", (SIDE, 0, 0)), ("N", "S", (0, SIDE, 0))):
            if EDGES[a][left] == EDGES[b][right] != "W":
                checked.append(BASE["audit_join"](a, b, left, right, meshes[a].data, meshes[b].data, Vector(offset)))
    return checked


def encoded_normal_error(path, source_triangles):
    """Measure encoder precision separately from Blender's imported custom normals."""
    doc, blob = BASE["glb_chunks"](path)
    source_normals = {}
    for material, corners in source_triangles.values():
        for p, n, _ in corners:
            key = (material, tuple(round(v, 5) for v in (p.x, p.z, -p.y)))
            source_normals.setdefault(key, []).append(Vector((n.x, n.z, -n.y)))

    def vectors(accessor_index):
        access = doc["accessors"][accessor_index]
        view = doc["bufferViews"][access["bufferView"]]
        check(access["componentType"] == 5126 and access["type"] == "VEC3", access)
        start = view.get("byteOffset", 0) + access.get("byteOffset", 0)
        stride = view.get("byteStride", 12)
        return [struct.unpack_from("<3f", blob, start + stride * i) for i in range(access["count"])]

    result = 0.0
    for primitive in doc["meshes"][0]["primitives"]:
        material = doc["materials"][primitive["material"]]["name"]
        attrs = primitive["attributes"]
        for p, n in zip(vectors(attrs["POSITION"]), vectors(attrs["NORMAL"]), strict=True):
            key = (material, tuple(round(value, 5) for value in p))
            candidates = source_normals[key]
            result = max(result, min(BASE["angle"](normal, Vector(n)) for normal in candidates))
    check(result <= RAW_NORMAL_TOL, (path.name, "encoded normal error", result))
    return result


def roundtrip(folder, source, textures):
    imported, report = {}, {}
    for name, mesh in source.items():
        original = BASE["signature"](mesh.data)
        path = folder / f"ENV-002_{name}.glb"
        raw = BASE["inspect_glb"](path, name, BASE["tile_box"](mesh.data), original, textures)
        encoded_error = encoded_normal_error(path, original)
        before = set(bpy.data.objects)
        status = bpy.ops.import_scene.gltf(filepath=str(path), import_pack_images=True, merge_vertices=False)
        check(status == {"FINISHED"}, (name, status))
        tile, = set(bpy.data.objects) - before
        check(tile.type == "MESH" and tile.name.split(".")[0] == name and tile.parent is None, tile.name)
        geometry = BASE["audit_surface"](tile)
        after = BASE["signature"](tile.data)
        check(original.keys() == after.keys(), (name, "geometry or winding changed"))
        errors = [0.0, 0.0, 0.0]
        for key, (material, corners) in original.items():
            other_material, imported_corners = after[key]
            check(material == other_material, (name, material, other_material))
            for (a, n, u), (b, m, v) in zip(corners, imported_corners):
                for i, value in enumerate(((a - b).length, BASE["angle"](n, m), (u - v).length)):
                    errors[i] = max(errors[i], value)
        check(all(a <= b for a, b in zip(errors, (POSITION_TOL, IMPORT_NORMAL_TOL, UV_TOL))), (name, errors))
        report[name] = dict(raw, blender_import=geometry, max_position_error_BU=errors[0],
                            max_normal_angle_deg=errors[1], max_uv_error=errors[2],
                            max_encoded_normal_angle_deg=encoded_error)
        imported[name] = tile
    return imported, report


def append_legacy(group):
    with bpy.data.libraries.load(str(ENV1 / "ENV-001_terrain.blend"), link=False) as (_, target):
        target.objects = list(LEGACY)
    result = {}
    for name, tile in zip(LEGACY, target.objects):
        group.objects.link(tile)
        result[name] = tile
    return result


ASSEMBLY = (
    ("Flat", "StartMudflat", "Shore"),
    ("GentleSlope", "Flat", "ReedIslet"),
    ("Ridge", "RestPatch", "Shore"),
)
CENTRES = {"StartMudflat": (0, -10), "ReedIslet": (10, 0), "RestPatch": (0, 10)}


def assemble(group, tiles):
    placed = {}
    for j, names in enumerate(ASSEMBLY):
        for i, name in enumerate(names):
            position = ((i - 1) * SIDE, (j - 1) * SIDE, 0)
            tile = obj(group, f"{name} | {i},{j}", tiles[name].data, position)
            placed[i, j] = (name, tile)
    checked = []
    for (i, j), (name, tile) in placed.items():
        for neighbor, sides in (((i + 1, j), ("E", "W")), ((i, j + 1), ("N", "S"))):
            if neighbor in placed:
                other_name, other = placed[neighbor]
                checked.append(BASE["audit_join"](name, other_name, *sides, tile.data, other.data,
                                                  other.location - tile.location))
    corners = []
    for i, j in product(range(2), repeat=2):
        points, normals = [], []
        for di, dj in product(range(2), repeat=2):
            _, tile = placed[i + di, j + dj]
            row = BASE["samples_on_edge"](tile.data, "W" if di else "E")
            for p, n, _ in row[-HALF if dj else HALF]:
                points.append(tile.location + p)
                normals.append(n)
        gap = max((p - points[0]).length for p in points)
        normal = max(BASE["angle"](n, normals[0]) for n in normals)
        check(gap <= POSITION_TOL and normal <= NORMAL_TOL, (i, j, gap, normal))
        corners.append({"grid_corner": [i, j], "position_gap_BU": gap, "normal_gap_degrees": normal})
    return {"neighbor_edges": checked, "four_way_corners": corners}


def survey(group, floor, water):
    rectangle = BASE["rectangle"]
    plane = rectangle(group, "Review water | level -0.18 BU", -15, 15, -15, 15, WATER, water)
    rectangle(group, "Review floor | survey only", -190, 190, -190, 190, -.86, floor)
    return plane


def backdrop(group, legacy, material, water):
    """Repeat the ENV-001 ground beyond the sample to cover the gameplay sightline."""
    rectangle = BASE["rectangle"]
    for row in range(-4, 14):
        for col in range(-9, 2):
            if -1 <= col <= 1 and -1 <= row <= 1:
                continue
            name = "Shore" if col == 1 else "Flat"
            obj(group, f"Context | {col},{row}", legacy[name].data, (col * SIDE, row * SIDE, 0))
    rectangle(group, "Gameplay reference water | single level plane", -85, 290, -45, 340, WATER, water)
    bottom = rectangle(group, "Context submerged floor", 15, 290, -45, 340, FLOOR, material)
    uvs = bottom.data.uv_layers.new(name="TerrainUV")
    for loop in bottom.data.loops:
        x, y, _ = bottom.data.vertices[loop.vertex_index].co
        uvs.data[loop.index].uv = ((x + HALF) / SIDE, (y + HALF) / SIDE)
    return bottom


def add_flock(group, name, mesh, data):
    items = []
    dx, dy = CENTRES[name]
    for i, bird in enumerate(data["birds"]):
        bx, by = bird["xy_BU"]
        item = obj(group, f"{name} | bird {i + 1:02}", mesh, (dx + bx, dy + by, bird["root_z_BU"]))
        item.scale = (bird["scale"],) * 3
        item.rotation_euler.z = math.radians(bird["yaw_degrees"])
        items.append(item)
    return items


def audit_tiles(tiles, points, soles, original=None):
    result = {}
    for name, tile in tiles.items():
        edge = None if original is None else original[name]["shoreline_stances"]
        mesh = tile.data
        result[name] = {
            "geometry": BASE["audit_surface"](tile),
            "flock_leader_1_and_followers_point8": audit_flock(tile, points, soles),
            "flock_all_1x": audit_flock(tile, points, soles, full_size=True),
            "shoreline_stances": audit_edge_stances(tile, points, soles, edge),
            "area_below_review_water_BU2": wet_area(mesh),
            "waterline_segments_xy_BU": [[list(a), list(b)] for a, b in waterline_segments(mesh)],
        }
    return result


def measure_view(scene, camera, bird_items):
    visible = []
    bpy.context.view_layer.update()
    for bird in bird_items:
        coords = [world_to_camera_view(scene, camera, bird.matrix_world @ vertex.co) for vertex in bird.data.vertices]
        x = [point.x for point in coords]
        y = [point.y for point in coords]
        check(min(point.z for point in coords) > 0 and min(x) >= 0 and max(x) <= 1
              and min(y) >= 0 and max(y) <= 1, (camera.name, bird.name, "out of frame"))
        visible.append({"width_px": (max(x) - min(x)) * GAME_SIZE[0],
                        "height_px": (max(y) - min(y)) * GAME_SIZE[1]})
    return visible


def close_view(light_group, edge_group, name, mesh, edge, terrain):
    dx, dy = CENTRES[name]
    x, y = edge["xy_BU"]
    lift = edge["root_z_BU"]
    bird = obj(edge_group, f"{name} | close stance", mesh, (dx + x, dy + y, lift))
    bird.rotation_euler.z = math.radians(edge["yaw_degrees"])
    tree = land_mesh(terrain.data)
    slope = terrain_at(tree, x, y)
    target = Vector((dx + x, dy + y - .05, slope + .14))
    yaw = math.radians(edge["yaw_degrees"])
    # The forward-quarter angle exposes the feet below the folded wings.
    offset = moved(Vector((1.65, 1.9, 1.22)), (0, 0), yaw, 1)
    cam = BASE["camera"](light_group, f"{name} | feet and waterline", target + offset, target, 2.2)
    return bird, cam


def export(tiles, output):
    for name, tile in tiles.items():
        bpy.ops.object.select_all(action="DESELECT")
        tile.select_set(True)
        bpy.context.view_layer.objects.active = tile
        status = bpy.ops.export_scene.gltf(filepath=str(output / f"ENV-002_{name}.glb"), export_format="GLB",
                                          use_selection=True, export_yup=True, export_extras=True,
                                          export_image_format="AUTO", export_animations=False)
        check(status == {"FINISHED"}, (name, status))
        tile.select_set(False)


def materials_for_review():
    materials, textures = BASE["load_materials"]()
    # The ENV-001 mesh objects bring packed copies of the same materials.
    # Use one shared set of unsuffixed material IDs in the terrain exports.
    for name, mat in materials.items():
        if mat.name != name:
            previous = bpy.data.materials.get(name)
            if previous:
                previous.user_remap(mat)
                bpy.data.materials.remove(previous, do_unlink=True)
            mat.name = name
    return materials, textures


def build(output, diagnostics_only=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.preferences.filepaths.temporary_directory = str(output)
    library = bpy.context.scene
    library.name = "ENV-002 | Module library"
    library.unit_settings.system = "NONE"
    gray = {name: paint("Graybox | " + name, color) for name, color in zip(
        SURFACES, ("ADAE9D", "9F9586", "A2A9A4", "818A8C", "829597"))}
    group = collection("ENV-002 | Three export meshes at origin", library.collection)
    tiles = {name: build_module(name, group, gray) for name in NAMES}
    refs = collection("ENV-001 | Comparison meshes", library.collection)
    legacy = append_legacy(refs)
    legacy_materials = {name: [mat for mat in tile.data.materials] for name, tile in legacy.items()}
    bpy.context.view_layer.update()
    source_joins = joins(tiles, legacy)

    review = BASE["fresh_scene"]("ENV-002 | Review assembly")
    root = collection("ENV-002 | Wetland review", review.collection)
    geog = collection("01 | 3 by 3 snapped modules", root)
    assembly = assemble(geog, dict(legacy, **tiles))
    standing_group = collection("02 | ANM-007 pose and flock placements", root)
    standing, points, soles = load_standing_mesh(standing_group)
    source = audit_tiles(tiles, points, soles)
    if diagnostics_only:
        write_json(output / "diagnostics.json", source)
        return
    flock_groups, flocks = {}, {}
    for name in NAMES:
        flock_groups[name] = collection(name + " | 12 goose placements", standing_group)
        flocks[name] = add_flock(flock_groups[name], name, standing,
                                source[name]["flock_leader_1_and_followers_point8"])
    contacts = collection("03 | Stand probes near the waterline", root)
    water_group = collection("04 | Independent reference water", root)
    lights = BASE["studio"](review, root)
    temp_water = collection("Reference material donor", root)
    water_plane = BASE["add_water"](temp_water)
    water = water_plane.data.materials[0]
    water.name = "Review only | level reference water"
    bpy.data.objects.remove(water_plane, do_unlink=True)
    bpy.data.collections.remove(temp_water)
    gaze = BASE["camera"]
    land = paint("Review survey palette", "D2DAD2")
    bounded_water = survey(water_group, land, water)
    context = collection("Terrain context | fixed camera only", root)
    submerged = backdrop(context, legacy, paint("Review | submerged surround", "78918B"), water)
    BASE["show_context"](context, False)
    top = gaze(lights, "Assembly | orthographic top", (0, 0, 42), (0, 0, 0), 34.2)
    game = gaze(lights, "Gameplay | fixed rear per flock", (0, 0, 1), (0, 1, 0))
    close_cameras, edge_birds = {}, {}
    for name, data in source.items():
        stance = min(data["shoreline_stances"], key=lambda s: s["nearest_sole_sample_to_waterline_BU"])
        edge_birds[name], close_cameras[name] = close_view(lights, contacts, name, standing, stance, tiles[name])
    contacts.hide_render = True
    for name, tile in legacy.items():
        for i, mat in enumerate(legacy_materials[name]):
            tile.data.materials[i] = gray[mat.name.split(".")[0]]
    render = BASE["render"]
    render(review, top, output, "graybox_top", (1000, 1000))
    standing_group.hide_render = True
    contacts.hide_render = False
    render(review, close_cameras["ReedIslet"], output, "graybox_foot_detail", (950, 550))
    contacts.hide_render = True
    standing_group.hide_render = False

    for name, tile in legacy.items():
        for i, mat in enumerate(legacy_materials[name]):
            tile.data.materials[i] = mat
    mats, textures = materials_for_review()
    BASE["assign_materials"](tiles, mats)
    submerged.data.materials[0] = mats["ShallowMargin"]
    render(review, top, output, "preview_top", (1200, 1200), 20)
    frame_reports = {}
    BASE["show_context"](context, True)
    bounded_water.hide_render = True
    for name in NAMES:
        for other, group in flock_groups.items():
            group.hide_render = other != name
        leader = flocks[name][0]
        BASE["follow"](game, leader.location.xy, Vector((0, 1)))
        render(review, game, output, f"preview_fixed_rear_{name}", GAME_SIZE, 24)
        frame_reports[name] = measure_view(review, game, flocks[name])
    BASE["show_context"](context, False)
    bounded_water.hide_render = False
    standing_group.hide_render = True
    contacts.hide_render = False
    for name in NAMES:
        for other, bird in edge_birds.items():
            bird.hide_render = other != name
        render(review, close_cameras[name], output, f"preview_foot_{name}", (950, 550), 22)
    standing_group.hide_render = False
    contacts.hide_render = True
    for group in flock_groups.values():
        group.hide_render = False
    for bird in edge_birds.values():
        bird.hide_render = False
    BASE["set_preview_workspace"](review, top)
    review.render.resolution_x = review.render.resolution_y = 1200
    review.render.filepath = "//review.png"

    bpy.context.window.scene = library
    export(tiles, output)
    for tile in legacy.values():
        tile.hide_set(True)
    bpy.context.window.scene = review
    bpy.ops.wm.save_as_mainfile(filepath=str(output / f"{STEM}.blend"))

    final = BASE["fresh_scene"]("ENV-002 | Roundtrip")
    imported, transport = roundtrip(output, tiles, textures)
    after = audit_tiles(imported, points, soles, source)
    after_joins = joins(imported, legacy)
    final_root = collection("GLB terrain reassembly", final.collection)
    for tile in imported.values():
        tile.hide_set(True)
        tile.hide_render = True
    after_assembly = assemble(final_root, dict(legacy, **imported))
    for name in NAMES:
        add_flock(final_root, name, standing, after[name]["flock_leader_1_and_followers_point8"])
    survey(final_root, land, water)
    camera_group = BASE["studio"](final, final_root)
    final_top = gaze(camera_group, "Roundtrip | orthographic top", (0, 0, 42), (0, 0, 0), 34.2)
    render(final, final_top, output, "preview_glb_roundtrip", (1200, 1200), 20)

    qa = {
        "id": "ENV-002", "version": "v001", "status": "needs_review",
        "blender": bpy.app.version_string,
        "tolerances": {"per_foot_contact_gap_max_BU": FOOT_GAP_TOL, "per_probe_gap_max_BU": FOOT_GAP_TOL + .006,
                       "bird_mesh_vertex_penetration_max_BU": PENETRATION_TOL,
                       "dry_support_above_reference_water_min_BU": MIN_EDGE_WATER_GAP,
                       "hull_separation_min_BU": PAIR_GAP_TOL,
                       "position_BU": POSITION_TOL, "seam_normals_degrees": NORMAL_TOL, "uv": UV_TOL,
                       "encoded_normals_degrees": RAW_NORMAL_TOL,
                       "blender_import_interior_normals_degrees": IMPORT_NORMAL_TOL},
        "stance_method": {"asset": "ANM-007/v001 from CHR-001/v001", "action": POSTURE[0], "frame": POSTURE[1],
                          "sole_probes_left_right": [len(v) for v in soles],
                          "foot_gap_method": "Downward terrain ray under each lower sole sample. Rigid torso lift, no foot retargeting.",
                          "pair_method": "Separating-axis gap between convex hulls of all posed goose vertices projected onto XY."},
        "graybox": {"result": "pass", "modules": source, "joins": source_joins, "reassembled": assembly},
        "glb_roundtrip": {"result": "pass", "modules": transport, "after_import_geometry_and_stances": after,
                          "joins": after_joins, "reassembled": after_assembly},
        "fixed_rear_bird_projections": frame_reports,
        "app_baseline": {"origin": "plans/active/goose-preview-model-cleanup.md", "device": "iPhone 18 Pro Simulator",
                         "os": "iOS 27.2", "prior_test_count": 340, "rerun_in_this_task": False},
        "pending": ["Paco review of shapes and surface palette; MAT-003 and ANM-007 remain needs_review.",
                    "Runtime landing slot assignment, dynamic landing and collisions on wetland, real water and USDZ.",
                    "iPhone and iPad review."],
    }
    write_json(output / "qa.json", qa)
    manifest = {
        "id": "ENV-002", "version": "v001", "name": "湿地泥滩 / 浅滩岛", "status": "needs_review",
        "execution_order_1_based": 16, "depends": ["ENV-001/v001", "MAT-003/v001"],
        "references": {
            "env001_blend_sha256": file_hash(ENV1 / "ENV-001_terrain.blend"),
            "env001_generation_script_sha256": file_hash(ENV1 / "ENV-001_generate.py"),
            "mat003_blend_sha256": file_hash(LIBRARY / "MAT-003/v001/MAT-003_wetland_rock.blend"),
            "anm007_review_pose_sha256": file_hash(ANM),
        },
        "dependency_status": {"ENV-001/v001": "needs_review", "MAT-003/v001": "needs_review",
                              "ANM-007/v001_review_pose": "needs_review"},
        "source_and_rights": "Original project geometry, unchanged packed MAT-003 PNGs and ANM-007 pose for review only.",
        "blender": bpy.app.version_string,
        "interface": {
            "footprint_xy_BU": [SIDE, SIDE], "center_pivot_xyz": [0, 0, 0],
            "pitch_BU": SIDE, "allowed_yaw_deg": [0], "object_scale": [1, 1, 1],
            "edge_samples": CELLS + 1, "edge_step_BU": STEP, "land_datum_BU": 0,
            "reference_water_level_BU": WATER, "submerged_east_edge_BU": FLOOR,
            "blender_to_gltf": ["x", "z", "-y"], "local_uv": ["(x+5)/10", "(y+5)/10"],
        },
        "source_camera": {"distance_game_units": 180, "pitch_parameter_rad": .48, "vertical_fov_deg": 50,
                          "look_height_game_units": 6, "depth_lift_game_units": 0,
                          "frame_px": list(GAME_SIZE), "game_units_per_BU_review_only": SCALE},
        "modules": {name: {"glb": f"ENV-002_{name}.glb", "edges": EDGES[name],
                           "materials": sorted(transport[name]["embedded_png_sha256"]),
                           "bounds_BU": source[name]["geometry"]["bounds_BU"], "triangles": 512} for name in NAMES},
        "textures": {name: value for name, value in textures.items()
                     if any(name in item["embedded_png_sha256"] for item in transport.values())},
        "files": {p.name: file_hash(p) for p in sorted(output.iterdir()) if p.is_file()},
    }
    write_json(output / "asset_manifest.json", manifest)


def verify(candidate, output):
    bpy.ops.wm.open_mainfile(filepath=str(candidate / f"{STEM}.blend"))
    tiles = {name: bpy.data.objects[name] for name in NAMES}
    legacy = {name: bpy.data.objects[name] for name in LEGACY}
    manifest = json.loads((candidate / "asset_manifest.json").read_text())
    qa = json.loads((candidate / "qa.json").read_text())
    scene = BASE["fresh_scene"]("ENV-002 | Independent verification")
    review = collection("Independent verification", scene.collection)
    _, points, soles = load_standing_mesh(review)
    imported, transport = roundtrip(candidate, tiles, manifest["textures"])
    earlier = qa["graybox"]["modules"]
    module_qa = audit_tiles(imported, points, soles, earlier)
    recheck = {"modules": transport, "after_import_geometry_and_stances": module_qa,
               "joins": joins(imported, legacy), "reassembled": assemble(review, dict(legacy, **imported))}
    # Convert GLB bounds tuples to the same arrays used in the JSON report.
    comparable = json.loads(json.dumps(recheck))
    differing = [key for key in comparable if comparable[key] != qa["glb_roundtrip"][key]]
    check(not differing, ("roundtrip reports differ", differing))
    check(all(transport[name]["max_normal_angle_deg"] <= IMPORT_NORMAL_TOL for name in NAMES),
          "Blender interior normals differ")
    write_json(output / "recheck.json", dict(result="pass", **recheck))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--diagnostics-only", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1:]
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    check(not any(output.iterdir()), "Use an empty temporary output directory.")
    if args.verify:
        verify(args.verify.resolve(), output)
    else:
        build(output, args.diagnostics_only)


if __name__ == "__main__":
    main()
