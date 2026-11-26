"""Author the S0–S1 review pass in Blender units (+Y along the route)."""

from math import cos, pi, sin
from random import Random

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


RIVER_TEXTURE = "MAT-004/v001/textures/ft_goose_mat_water_river_basecolor_alpha.png"
SCENERY = {
    "reed_a": "ENV-004/v001/ENV-004_Reed_A_Height_S.glb",
    "reed_b": "ENV-004/v001/ENV-004_Reed_B_Height_S.glb",
    "reed_c": "ENV-004/v001/ENV-004_Reed_C_Height_S.glb",
    "rock_long": "ENV-011/v001/ENV-011_Rock_Long.glb",
    "rock_round": "ENV-011/v001/ENV-011_Rock_Round.glb",
    "ridge_a": "ENV-009/v001/ENV-009_FarRidge_A.glb",
    "ridge_b": "ENV-009/v001/ENV-009_FarRidge_B.glb",
    "ridge_c": "ENV-009/v001/ENV-009_FarRidge_C.glb",
}

# center X, Y, and half-width. The south taper lies away from the dry gate.
# The north taper runs into the west lobe of the authored A pool.
WATERCOURSE = (
    (-11.9, 2.6, 0.0), (-11.9, 5.2, 1.9), (-13.0, 10.8, 3.0),
    (-14.4, 16.4, 2.8), (-13.2, 22.4, 2.5), (-10.1, 27.8, 3.4),
    (-8.8, 33.0, 2.7), (-9.8, 37.1, 2.15), (-10.7, 39.8, 0.0),
)

# Cluster centers follow the outside of the water, leaving the formation and
# (-.65, 49.96) rest pad A a wide, open approach.
REED_CLUSTERS = {
    0: [
        (-5.1, -5.0, 2.2, 3.2), (5.4, -4.0, 2.0, 2.8),
        (-12.3, 5.5, 2.9, 3.3), (11.6, 8.0, 2.5, 3.1),
        (-14.1, 17.8, 2.5, 3.8), (14.0, 19.8, 3.0, 3.7),
        (-10.6, 28.0, 1.5, 2.9), (12.2, 27.4, 2.2, 3.7),
    ],
    1: [
        (-9.0, 7.3, 1.8, 2.8), (-16.8, 12.1, 2.6, 3.8),
        (8.1, 8.2, 2.0, 4.0), (12.2, 17.8, 2.4, 3.5),
        (-11.8, 21.0, 1.8, 2.7), (-14.3, 27.4, 2.0, 4.3),
        (9.5, 30.5, 2.0, 3.2), (-13.1, 35.3, 2.7, 3.5),
        (-8.6, 45.0, 2.2, 2.5), (5.3, 51.8, 2.5, 2.1),
    ],
}

# model, position X/Y/Z, horizontal turn and scale. Two offset banks frame
# the flight path while the widest silhouettes stay beyond the flight bounds.
RIDGES = {
    0: [
        ("ridge_a", (-37, 6, -0.34), 81, (1.55, 2.1, 1.32)),
        ("ridge_a", (38, 13, -0.33), 98, (1.65, 2.0, 1.29)),
        ("ridge_b", (-54, 13, -0.33), 74, (1.9, 2.1, 1.82)),
        ("ridge_b", (55, 14, -0.34), 108, (1.95, 2.1, 1.71)),
        ("ridge_c", (-20, -43, -0.40), 12, (1.55, 2.0, 1.7)),
        ("ridge_b", (45, -36, -0.35), 38, (1.45, 1.9, 2.0)),
    ],
    1: [
        ("ridge_a", (-40, 25, -0.31), 74, (1.75, 2.1, 1.41)),
        ("ridge_a", (39, 26, -0.32), 106, (1.75, 2.4, 1.40)),
        ("ridge_b", (-54, 29, -0.36), 80, (1.65, 1.9, 1.92)),
        ("ridge_c", (60, 22, -0.39), 104, (1.55, 2.1, 1.61)),
    ],
}

ROCKS = {
    0: [(-5.6, -4.0), (6.4, -2.2), (12.9, 14.5), (-13.6, 22.8), (15.4, 30.0)],
    1: [(9.4, 8.2), (-17.0, 16.5), (11.5, 29.5), (-15.0, 36.8), (5.6, 47.0), (-6.6, 51.4)],
}


def _section(y):
    for left, right in zip(WATERCOURSE, WATERCOURSE[1:]):
        if left[1] <= y <= right[1]:
            t = (y - left[1]) / (right[1] - left[1])
            shape = t * t * (3 - 2 * t)
            return (left[0] + (right[0] - left[0]) * shape, left[2] + (right[2] - left[2]) * shape)
    return None


def _water_color(art):
    # The original river atlas has painted color in RGB. Here the terrain
    # defines the water outline, so its sample-patch alpha is unnecessary.
    material = bpy.data.materials.new("Opening | pale teal watercolor")
    material.use_nodes = True
    tree = material.node_tree
    shader = tree.nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = 0.91
    shader.inputs["Specular IOR Level"].default_value = 0.0
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.label = "MAT-004 river watercolor (RGB)"
    texture.image = bpy.data.images.load(str(art / RIVER_TEXTURE), check_existing=True)
    texture.extension = "MIRROR"
    tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    return material


def _paint_water(obj, material):
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    mesh = obj.data
    mesh.materials.clear()
    mesh.materials.append(material)
    uv = mesh.uv_layers.active or mesh.uv_layers.new(name="UVMap")
    points = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
    edges = {}
    for point in points:
        key = round(point.y, 4)
        low, high = edges.get(key, (point.x, point.x))
        edges[key] = min(low, point.x), max(high, point.x)
    for face in mesh.polygons:
        for loop in face.loop_indices:
            p = points[mesh.loops[loop].vertex_index]
            low, high = edges[round(p.y, 4)]
            u = (p.x - low) / (high - low) if high - low > 0.001 else 0.5
            uv.data[loop].uv = (u, p.y / 11)


def _cut_channel(scene, water):
    names = ("Approach_", "Transition_", "CheckpointA_Ground")
    for obj in scene.objects:
        if obj.type != "MESH" or not obj.name.startswith(names):
            continue
        reverse = obj.matrix_world.inverted()
        edits = []
        for vertex in obj.data.vertices:
            p = obj.matrix_world @ vertex.co
            sample = _section(p.y)
            if sample is None:
                continue
            center, width = sample
            into_bank = abs(p.x - center) - width
            # Rounded shoulders leave two to three mesh rows from wet bed to dry bank.
            if width > 0.04 and into_bank < 1.30:
                shoulder = max(0.0, into_bank / 1.30)
                wet = min(1.0, width / 0.75)
                depth = wet * 0.36 * (1 - shoulder * shoulder)
                level = 0.015 - depth
                if p.z > level:
                    p.z = level
                    edits.append((vertex.index, reverse @ p))
        if edits:
            # A world-local cut cannot be written to the geometry shared by
            # unchanged tiles, including the east bank.
            if obj.data.users > 1:
                obj.data = obj.data.copy()
            for index, point in edits:
                obj.data.vertices[index].co = point
            obj.data.update()

    verts = []
    faces = []
    y0, y1 = WATERCOURSE[0][1], WATERCOURSE[-1][1]
    rows = 120
    for i in range(rows + 1):
        y = y0 + (y1 - y0) * i / rows
        center, width = _section(y)
        # The tips disappear into the bed, with no square end cap.
        width = max(0.004, width * 0.99)
        verts.extend([(center - width, y, -0.176), (center + width, y, -0.176)])
        if i:
            v = i * 2
            faces.append((v - 2, v - 1, v + 1, v))
    mesh = bpy.data.meshes.new("S1 Meandering side waterway")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(mesh.name, mesh)
    scene.collection.objects.link(obj)
    _paint_water(obj, water)


def _terrain_probes(scene, section):
    prefixes = (
        ("S0_Contact_Continued", "StartMudflat")
        if section == 0 else
        ("Approach_", "Transition_", "CheckpointA_Ground", "East_Bank_", "Exit_Apron_")
    )
    trees = []
    for obj in scene.objects:
        if obj.type != "MESH" or not obj.name.startswith(prefixes):
            continue
        tree = BVHTree.FromPolygons(
            [obj.matrix_world @ v.co for v in obj.data.vertices],
            [tuple(poly.vertices) for poly in obj.data.polygons],
        )
        trees.append(tree)
    return trees


def _height(trees, x, y):
    contacts = [tree.ray_cast((x, y, 5), (0, 0, -1), 10)[0] for tree in trees]
    return max((v.z for v in contacts if v is not None), default=-0.30)


def _load_models(art, scene):
    templates = {}
    for key, path in SCENERY.items():
        before = set(scene.objects)
        bpy.ops.import_scene.gltf(filepath=str(art / path))
        imported = set(scene.objects) - before
        parts = [(obj.data, obj.matrix_world.copy()) for obj in imported if obj.type == "MESH"]
        if not parts:
            raise ValueError(f"Missing mesh in opening scenery: {path}")
        templates[key] = parts
        for obj in imported:
            bpy.data.objects.remove(obj, do_unlink=True)
    return templates


def _place(collection, templates, key, name, pos, heading, scale):
    transform = Matrix.Translation(Vector(pos)) @ Matrix.Rotation(heading, 4, "Z") @ Matrix.Diagonal((*scale, 1))
    for index, (mesh, local) in enumerate(templates[key]):
        obj = bpy.data.objects.new(f"{name}_{index + 1:02d}", mesh)
        collection.objects.link(obj)
        obj.matrix_world = transform @ local


def dress_opening(art, section):
    scene = bpy.context.scene
    water = _water_color(art)
    if section == 0:
        for obj in scene.objects:
            if obj.type == "MESH" and obj.name.startswith("S0_Wash_"):
                _paint_water(obj, water)
    else:
        _cut_channel(scene, water)

    bank = _terrain_probes(scene, section)
    models = _load_models(art, scene)
    collection = bpy.data.collections.new(f"S{section} Opening shore and distant ridges")
    scene.collection.children.link(collection)
    rng = Random(914 + section)
    for i, (x, y, width, depth) in enumerate(REED_CLUSTERS[section]):
        for j in range(15 if i % 3 == 0 else 11):
            t = 2 * pi * j / 11 + rng.uniform(-0.33, 0.33)
            radius = rng.uniform(0.25, 1.0)
            px, py = x + cos(t) * width * radius, y + sin(t) * depth * radius
            if abs(px) < 4.5 or (section == 1 and py > 46 and abs(px + 0.65) < 3.25):
                continue
            floor = _height(bank, px, py)
            size = rng.uniform(0.77, 1.39)
            _place(collection, models, rng.choice(("reed_a", "reed_b", "reed_c")),
                   f"S{section}_ShoreReed_{i:02d}_{j:02d}", (px, py, max(-0.191, floor) - 0.014),
                   rng.uniform(-pi, pi), (size, size, size * 1.17))
    for i, (x, y) in enumerate(ROCKS[section]):
        scale = rng.uniform(0.48, 0.79)
        _place(collection, models, "rock_round" if i % 2 else "rock_long",
               f"S{section}_BankRock_{i:02d}", (x, y, _height(bank, x, y) - 0.055),
               rng.uniform(-pi, pi), (scale, scale, scale))
    for i, (key, pos, heading, scale) in enumerate(RIDGES[section]):
        _place(collection, models, key, f"S{section}_OuterRidge_{i:02d}", pos, heading * pi / 180, scale)
