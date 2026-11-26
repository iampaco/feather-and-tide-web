"""Fit the private LVL-S2 fork and LVL-S3 river to the expanded wetland banks."""

from math import radians

import bpy
from mathutils import Matrix, Vector

from terrain import OUTER_BANKS, S0_BANK, S0_NORTH, S1_BANK, S1_NORTH, add_patch, blend, far_bank_height, smooth

FORK_SCENERY = (
    "ENV-009/v001/ENV-009_FarRidge_A.glb",
    "ENV-009/v001/ENV-009_FarRidge_B.glb",
)
RIDGES = (
    # Leave the original mouth clear and keep the lake's far shore low.
    ((-29, 22, -0.24), 76, (1.0, 1.7, 1.72)),
    ((50, 44, -0.24), 68, (1.16, 1.92, 0.97)),
    ((-40, 35, -0.26), 86, (1.22, 2.34, 1.65)),
    ((65, 50, -0.27), 95, (1.61, 2.45, 1.13)),
)
FORK_LENGTH = 76.0
RIVER_LENGTH = 64.0
CHECKPOINT_Y = S0_NORTH + S1_NORTH
BANKS = (S1_BANK, *OUTER_BANKS)


def checkpoint_height(x):
    # Use the same vertices and elevation as the north edge of the S1 extension.
    distance = abs(x) - S1_BANK
    h = blend(0.0, far_bank_height(x, CHECKPOINT_Y), smooth((abs(x) - S0_BANK) / 9.0))
    return blend(h, -0.6, smooth(distance / 4.0))


def outer_height(x, y, length, offset):
    distance = abs(x) - S1_BANK
    common_gate = 1.0 - smooth(min(y, length - y) / 9.0)
    inland = blend(0.0, far_bank_height(x, y + offset), smooth(distance / 14.0))
    return blend(inland, checkpoint_height(x), common_gate)


def fork_uv(x, y, _):
    return x / 10.0 + 0.5, y / 10.0 + 0.5


def river_phase(y):
    # Match the fork at the south gate and recover the river's existing phase
    # before the first bend, where the separate mud and water materials begin.
    return 1.0 - smooth((y - 3.0) / 12.0)


def river_uv(x, y, _):
    phase = river_phase(y)
    return x / 10.0 + 0.8 - 0.3 * phase, y / 10.0 - 0.5 + 0.6 * phase


def east_edge(shore):
    """Read the source bank's exact row starts and make its dry caps flat."""
    world = shore.matrix_world
    local = world.inverted()
    rows = {}
    for vertex in shore.data.vertices:
        point = world @ vertex.co
        y = round(float(point.y), 4)
        z = float(point.z) * smooth(min(y, 63.0 - y) / 4.0)
        if z != point.z:
            point.z = z
            vertex.co = local @ point
        xyz = (float(point.x), y, z)
        rows.setdefault(y, {})[round(float(point.x), 5)] = xyz
    shore.data.update()
    return rows


def fit_fork_ground():
    left = bpy.data.objects["West apron"]
    right = bpy.data.objects["East bank apron"]
    north = bpy.data.objects["North merge apron"]
    source = east_edge(bpy.data.objects["LakeShore"])

    west_rows = [
        [(x, y, outer_height(x, y, FORK_LENGTH, CHECKPOINT_Y))
         for x in (-21.5, -23.25, *(-distance for distance in BANKS))]
        for y in range(0, int(FORK_LENGTH) + 1)
    ]
    add_patch("S2_Continuous_WestBank", west_rows, left, fork_uv, reverse=True)

    entry_edge = max(source[0.0])
    close_edge = max(source[63.0])

    def east_row(y, edge, z):
        # Follow the lake's existing edge and keep the outer vertices pinned at
        # the dry gates, where they meet the wetland and river extensions.
        columns = [edge] + [
            blend(edge, 60.0, (x - entry_edge) / (60.0 - entry_edge)) if x < 60.0 else x
            for x in BANKS
        ]
        return [(x, y, blend(outer_height(x, y, FORK_LENGTH, CHECKPOINT_Y), z,
                            1.0 - smooth((x - edge) / 3.5)))
                for x in columns]

    shore_rows = []
    for y, points in sorted(source.items()):
        x, _, z = points[max(points)]
        shore_rows.append(east_row(y, x, z))
    add_patch("S2_Continuous_EastBank", shore_rows, right, fork_uv)

    last_cap = list(sorted(source[63.0].values()))
    north_distances = [x for x, _, _ in last_cap]
    merge_rows = []
    for y in range(63, int(FORK_LENGTH) + 1):
        ratio = smooth((y - 63.0) / (FORK_LENGTH - 63.0))
        edge = blend(close_edge, entry_edge, ratio)
        # Keep the corner vertices identical to the lake cap and eastern wing.
        center = [(blend(-1.0, edge, (x + 1.0) / (close_edge + 1.0)), y, 0.0)
                  for x in north_distances[:-1]]
        merge_rows.append(center + east_row(y, edge, 0.0))
    add_patch("S2_Merge_DryApron", merge_rows, north, fork_uv)
    for obj in (left, right, north):
        bpy.data.objects.remove(obj, do_unlink=True)


def fit_river_ground():
    scene = bpy.context.scene
    for side, label in ((-1, "West"), (1, "East")):
        grass = bpy.data.objects[f"S3_GrassLand_{label}"]
        rows = [
            [(side * x, y, outer_height(side * x, y, RIVER_LENGTH, CHECKPOINT_Y + FORK_LENGTH))
             for x in BANKS]
            for y in range(0, int(RIVER_LENGTH) + 1)
        ]
        add_patch(f"S3_Continuous_{label}Bank", rows, grass, river_uv, reverse=side < 0)
    for obj in scene.objects:
        if not obj.name.startswith(("S3_GrassLand_", "S3_BedCap_South", "S3_Straight_Bed_10")):
            continue
        mesh = obj.data
        grass_slots = {i for i, mat in enumerate(mesh.materials) if mat.name.startswith("GrassFlat")}
        uv = mesh.uv_layers.active.data
        for face in mesh.polygons:
            if face.material_index not in grass_slots:
                continue
            for i in face.loop_indices:
                world = obj.matrix_world @ mesh.vertices[mesh.loops[i].vertex_index].co
                phase = river_phase(world.y)
                uv[i].uv += Vector((-0.3 * phase, 0.6 * phase))


def place_ridges(art):
    scene = bpy.context.scene
    for source_index, source in enumerate(FORK_SCENERY):
        before = set(scene.objects)
        bpy.ops.import_scene.gltf(filepath=str(art / source))
        added = set(scene.objects) - before
        parts = [(obj.data, obj.matrix_world.copy()) for obj in added if obj.type == "MESH"]
        if not parts:
            raise ValueError(f"No ridge mesh in {source}")
        for obj in added:
            bpy.data.objects.remove(obj, do_unlink=True)
        for index, (location, heading, scale) in enumerate(RIDGES[2 * source_index:2 * source_index + 2]):
            transform = (Matrix.Translation(Vector(location)) @ Matrix.Rotation(radians(heading), 4, "Z")
                         @ Matrix.Diagonal((*scale, 1)))
            for part_index, (mesh, local) in enumerate(parts):
                ridge = bpy.data.objects.new(f"S2_FarBank_{source_index}_{index}_{part_index}", mesh)
                scene.collection.objects.link(ridge)
                ridge.matrix_world = transform @ local


def polish_fork(art, section):
    """Extend coverage for banked turns while preserving the approved layout anchors."""
    if section == 2:
        fit_fork_ground()
        place_ridges(art)
    elif section == 3:
        fit_river_ground()
    else:
        raise ValueError(f"Fork treatment supports sections 2 and 3, got {section}")
