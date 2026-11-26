"""Fit the private LVL-S4–S6 shoulders without touching the authored water and landing slots."""

import bpy

from fork import checkpoint_height
from terrain import OUTER_BANKS, add_patch, blend, far_bank_height, smooth


def _height(x, y, length, world_offset):
    if abs(x) <= 25:
        return 0.0
    inland = blend(0.0, far_bank_height(x, y + world_offset), smooth((abs(x) - 25) / 14))
    return blend(checkpoint_height(x), inland, smooth(min(y, length - y) / 9))


def _fit_grass(objects, grass_uv, height=None):
    for obj in objects:
        # Imported terrain tiles can instance the same vertex and UV data.
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        mesh = obj.data
        world = obj.matrix_world
        positions = [world @ vertex.co for vertex in mesh.vertices]
        if height is not None:
            inverse = world.inverted()
            for vertex, point in zip(mesh.vertices, positions):
                point.z += height(point.x, point.y)
                vertex.co = inverse @ point
        grass = {i for i, mat in enumerate(mesh.materials) if mat.name.startswith("GrassFlat")}
        for face in mesh.polygons:
            if face.material_index in grass:
                for loop in face.loop_indices:
                    p = positions[mesh.loops[loop].vertex_index]
                    mesh.uv_layers.active.data[loop].uv = grass_uv(p.x, p.y, p.y)
        mesh.update()


def _shoulders(section, start, end, west, east, height, uv, source, world_dx=0):
    for side, label, edge in ((-1, "West", west), (1, "East", east)):
        outer = tuple(side * width - world_dx for width in OUTER_BANKS)
        columns = [edge, *(x for x in outer if (x - edge) * side > 0.001)]
        rows = [
            [(x, y, height(x, y)) for x in columns]
            for y in range(start, end + 1)
        ]
        add_patch(f"S{section}_Continuous_{label}Bank", rows, source, uv, reverse=side < 0)


def _farm():
    # The authored farm is centered two units east of the world origin.
    def uv(x, y, _):
        entry = 1.0 - smooth((y + 45) / 8)
        return x / 10 + 0.5 + 0.1 * entry, y / 10 + 0.5 - 0.1 * entry

    def height(x, y):
        return _height(x - 2, y + 45, 90, 236)

    source = bpy.data.objects["Terrain 0,-40"]
    tiles = [obj for obj in bpy.context.scene.objects if obj.name.startswith("Terrain ") and obj.type == "MESH"]
    _fit_grass(tiles, uv, height)
    for label, y_start, y_end in (("South", -45, -25), ("North", 35, 45)):
        rows = [[(x, y, height(x, y)) for x in (15, 20, 25)] for y in range(y_start, y_end + 1)]
        add_patch(f"S4_{label}EastApron", rows, source, uv)
    _shoulders(4, -45, 45, -25, 25, height, uv, source, world_dx=-2)


def _headwind():
    def uv(x, y, _):
        return x / 10 + 0.75 - 0.05 * (1.0 - smooth(y / 8)), y / 10

    def height(x, y):
        return _height(x, y, 64, 326)

    source = bpy.data.objects["S5_Terrain_West_bank"]
    banks = [obj for obj in bpy.context.scene.objects if obj.name.startswith("S5_Terrain_") and obj.type == "MESH"]
    _fit_grass(banks, uv)
    _shoulders(5, 0, 64, -22, 22, height, uv, source)


def _basin():
    def uv(x, y, _):
        entry = 1.0 - smooth(y / 8)
        return x / 10 + 2.0 - 0.25 * entry, y / 10 + 0.4 * entry

    def height(x, y):
        if y <= 40:
            return _height(x, y, 49, 390)
        rim = _height(x, 40, 49, 390)
        return blend(rim, far_bank_height(x, y + 390), smooth((y - 40) / 24))

    source = bpy.data.objects["LandingBasin_Ground"]
    _fit_grass([source], uv)
    _shoulders(6, 0, 40, -20, 20, height, uv, source)
    east = [20, *OUTER_BANKS]
    columns = [-x for x in reversed(east)] + list(range(-15, 16, 5)) + east
    rows = [[(x, y, height(x, y)) for x in columns] for y in range(40, 151, 2)]
    add_patch("S6_NorthMeadow", rows, source, uv)


def extend_last_reaches(section):
    (_farm, _headwind, _basin)[section - 4]()
