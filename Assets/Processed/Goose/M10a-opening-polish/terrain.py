"""Visual terrain around the first wetland, in Blender/world BU."""

from math import copysign, cos, hypot, sin

import bpy

# The v001 footprints meet at world Y=36. S1 begins at local Y=0
# and ends at A/S2 (local Y=60).
S0_NORTH = 36.0
S0_SOUTH = -13.0
S0_BANK = 26.0
S1_BANK = 25.0
S1_NORTH = 60.0
OUTER_BANKS = (26.0, 27.25, 29.0, 32.0, 38.0, 47.0, 60.0, 78.0, 102.0, 126.0, 148.0)
OUTER_SOUTH = -145.0


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def blend(a, b, t):
    return a + (b - a) * t


def far_bank_height(x, world_y):
    rise = 0.24 * sin(x * 0.14 + world_y * 0.071) + 0.17 * cos(world_y * 0.20 - x * 0.057)
    distance = max(abs(x), max(0.0, -world_y))
    return blend(-0.19 + rise, -0.60, smooth((distance - 75.0) / 73.0))


def s0_south_at(bank):
    return blend(S0_SOUTH, OUTER_SOUTH, smooth((bank - S0_BANK) / (OUTER_BANKS[-1] - S0_BANK)))


def s0_uv(x, y):
    return x / 10.0 + 0.5, y / 10.0 + 0.4 * smooth((y - 22.0) / 12.0)


def s1_uv(x, y, face_y):
    # The approach uses full tiles. The half-tile transition and the basin
    # share a half-repeat phase along the north axis.
    return x / 10.0 + 0.5, y / 10.0 + (0.5 if face_y >= 20.0 else 0.0)


def s0_tint(x, y):
    # Wetland v001 assigns the perimeter its sage wash and restores the
    # underlying grass color at the north seam.
    clear = max(1.0 - smooth(abs(y) / 2.0), smooth((y - 30.0) / 6.0))
    return (*(blend(tone, 1.0, clear) for tone in (0.63, 0.73, 0.73)), 1.0)


def add_patch(name, rows, source, uv_for, reverse=False, tint=None):
    columns = len(rows[0])
    vertices = [point for row in rows for point in row]
    faces = []
    for row in range(len(rows) - 1):
        for column in range(columns - 1):
            a = row * columns + column
            face = (a, a + 1, a + columns + 1, a + columns)
            faces.append(face[::-1] if reverse else face)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(source.data.materials[0])
    uv = mesh.uv_layers.new(name=source.data.uv_layers.active.name)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
        face_y = sum(vertices[index][1] for index in polygon.vertices) / len(polygon.vertices)
        for index in polygon.loop_indices:
            x, y, _ = vertices[mesh.loops[index].vertex_index]
            uv.data[index].uv = uv_for(x, y, face_y)
    if tint is not None:
        source_color = source.data.color_attributes.active_color
        if source_color is not None:
            color = mesh.color_attributes.new(name=source_color.name, type="FLOAT_COLOR", domain="POINT")
            for item, (x, y, _) in zip(color.data, vertices):
                item.color = tint(x, y)
    return obj


def prepare_s0(source):
    """Match S1's flat entry outside the 24 BU seam before extending both banks."""
    transform = source.matrix_world
    inverse = transform.inverted()
    shores = {-1: {}, 1: {}}
    south = {}
    for vertex in source.data.vertices:
        point = transform @ vertex.co
        x, y, z = (round(float(component), 5) for component in point)
        if y > 35.0 and abs(x) > 12.0:
            point.z *= 1.0 - smooth(y - 35.0)
            vertex.co = inverse @ point
            z = float(point.z)
        for side in (-1, 1):
            if x == side * S0_BANK:
                shores[side][y] = z
        if y == S0_SOUTH:
            south[x] = z
    source.data.update()
    if not all(S0_SOUTH in edge and S0_NORTH in edge for edge in shores.values()):
        raise ValueError("S0 terrain perimeter no longer matches its v001 shore")
    if not (-S0_BANK in south and S0_BANK in south):
        raise ValueError("S0 terrain perimeter no longer matches its v001 rear bank")
    return shores, south


def extend_s0(source):
    shores, south = prepare_s0(source)
    patches = []
    for side, label in ((-1, "West"), (1, "East")):
        rows = []
        for y, border_height in sorted(shores[side].items()):
            along = (y - S0_SOUTH) / (S0_NORTH - S0_SOUTH)
            row = []
            for bank in OUTER_BANKS:
                x = side * bank
                level_y = blend(s0_south_at(bank), S0_NORTH, along)
                z = blend(border_height, far_bank_height(x, level_y), smooth((bank - S0_BANK) / 9.0))
                row.append((x, level_y, z))
            rows.append(row)
        patches.append(add_patch(f"S0_OuterTerrain_{label}", rows, source,
                                 lambda x, y, _: s0_uv(x, y), reverse=side < 0, tint=s0_tint))
    rows = []
    for bank in reversed(OUTER_BANKS):
        y = s0_south_at(bank)
        row = []
        for x, border_height in sorted(south.items()):
            # Widen the flat outer shoulder while keeping the shallows pinned
            # to their original world x coordinates behind the mudflat.
            spread = (bank - S0_BANK) * smooth((abs(x) - 18.0) / (S0_BANK - 18.0))
            widened = x + copysign(spread, x)
            distance = min(bank - S0_BANK, hypot(spread, y - S0_SOUTH))
            z = blend(border_height, far_bank_height(widened, y), smooth(distance / 9.0))
            row.append((widened, y, z))
        rows.append(row)
    patches.append(add_patch("S0_OuterTerrain_South", rows, source, lambda x, y, _: s0_uv(x, y), tint=s0_tint))
    return patches


def extend_s1(source):
    patches = []
    for side, label in ((-1, "West"), (1, "East")):
        rows = []
        for row_index in range(97):
            y = row_index * 0.625
            row = []
            for bank in (S1_BANK, *OUTER_BANKS):
                x = side * bank
                z = blend(0.0, far_bank_height(x, y + S0_NORTH), smooth((bank - S0_BANK) / 9.0))
                # A ends at the original 60 BU apron. Keep the last transition
                # low outside the apron so that the fork remains the focal point.
                end = smooth((y - 54.0) / (S1_NORTH - 54.0)) * smooth((bank - S1_BANK) / 4.0)
                row.append((x, y, blend(z, -0.60, end)))
            rows.append(row)
        patches.append(add_patch(f"S1_OuterTerrain_{label}", rows, source, s1_uv, reverse=side < 0))
    return patches


def extend_opening_terrain(section):
    """Add stable, visual-only banks to a freshly imported S0 or S1 v001 GLB."""
    bpy.context.view_layer.update()
    if section == 0:
        return extend_s0(bpy.data.objects["S0_Contact_Continued"])
    if section == 1:
        return extend_s1(bpy.data.objects["Approach_+20_05"])
    raise ValueError("Opening terrain supports chapter sections 0 and 1")
