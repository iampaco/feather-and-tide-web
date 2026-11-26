"""Join the single-route river to the LVL-S6 basin at the original landing anchors."""
import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import OpenImageIO as oiio
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils, Vt

from ground_detail import contact_shade, enrich, placements
from landscape import BOUNDS as RIVER_BOUNDS, elevation as river_elevation

ROOT = Path(__file__).resolve().parents[4]
ART = ROOT / "Assets/Watercolor/Goose/Blender"
M10A = ROOT / "Assets/Processed/Goose/M10a-chapter-polish/preview-manifest.json"
LAYOUT = ART / "LVL-S6/v001/s6_layout.json"
ATLAS_NAME = "ft_goose_linear_basin_paint.png"
GROUND = "/root/LandingBasin/LandingBasin_Ground"
WATER = "/root/LandingBasin/LandingBasin_Water"
REEDS = "/root/LandingBasin/LandingBasin_Reeds"
HALF_WIDTH = 32
ATLAS_END = 49
BASIN_ENTRY = 242
SOURCE_TEXTURES = {
    "grass": "MAT-003/v001/textures/ft_goose_mat_grass_flat_basecolor.png",
    "mud": "MAT-003/v001/textures/ft_goose_mat_mud_bank_basecolor.png",
    "wet": "MAT-003/v001/textures/ft_goose_mat_shallow_margin_basecolor.png",
    "river": "MAT-004/v001/textures/ft_goose_mat_water_river_basecolor_alpha.png",
    "shallow": "MAT-004/v001/textures/ft_goose_mat_water_shallow_basecolor_alpha.png",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smooth(t):
    v = np.clip(t, 0, 1)
    return v * v * (3 - 2 * v)


def mix(a, b, t):
    return a + (b - a) * t


def bay(x, y, cx, cy, rx, ry, lean, phase):
    dx, dy = x - cx - lean * (y - cy), y - cy
    bend = 0.41 * np.sin(dy * 0.62 + phase) + 0.23 * np.sin(dx * 0.91 + dy * 0.43)
    return (np.hypot((dx + bend) / rx, dy / ry) - 1.0) * min(rx, ry)


def bank_shoulders(x, y):
    east = np.exp(-((x - 10.3) / 4.0) ** 2 - ((y - 16.6) / 7.2) ** 2)
    west = np.exp(-((x + 11.5) / 4.8) ** 2 - ((y - 25.6) / 6.5) ** 2)
    return east, west


class Basin:
    def __init__(self):
        self.slots = [slot["blender_BU"] for slot in json.loads(LAYOUT.read_text())["landing_slots"]]

    def distance(self, x, y):
        """Negative values trace the water inside the inlet and its off-axis pools."""
        cx = np.interp(y, [0, 6, 10, 15, 20, 24], [-0.75, -1.35, -2.25, -4.8, -6.1, -7.4])
        width = np.interp(y, [0, 6, 10, 15, 20, 23, 26], [10.6, 8.8, 6.9, 3.65, 3.0, 1.8, -1.0])
        wobble = 0.44 * np.sin(y * 0.54 + x * 0.34) + 0.17 * np.cos(y * 1.45 - x * 0.52)
        inlet = np.maximum(abs(x - cx) - width + wobble, (y - 23.0) * 0.67)
        west = bay(x, y, -6.8, 23.1, 4.25, 9.65, -0.11, 0.7)
        east = bay(x, y, 6.3, 25.8, 3.1, 7.15, 0.23, -1.8)
        east_tip = bay(x, y, 9.7, 29.1, 2.6, 4.8, -0.26, 0.2)
        back = bay(x, y, -1.8, 32.6, 3.55, 1.45, -0.41, 0.5)
        west_finger = bay(x, y, -13.5, 16.2, 1.45, 4.3, 0.45, 1.9)
        distance = np.minimum.reduce((inlet, west, east, east_tip, back, west_finger))

        # A landing animation can plant a foot slightly behind its anchor.
        for px, py, height in self.slots:
            radius = np.hypot((x - px) / 1.08, (y - py + 0.15) / 1.24)
            if height == 0:
                distance = np.maximum(distance, 0.9 - radius)
            else:
                distance = np.minimum(distance, radius - 1.28)
        return distance

    def elevations(self, x, y, distance):
        crossing = 4.8 + 2.0 * np.sin(x * 0.27 + 0.6) + 0.9 * np.cos(x * 0.62)
        entrance = smooth((y - crossing + 4.5) / 12.0)
        water = -0.321 + 0.141 * entrance
        flooded = np.minimum(0.041 + 0.13 * (1 - entrance), 0.31 * np.maximum(-distance, 0))
        bank = 0.18 * smooth(distance / 1.8)
        east, west = bank_shoulders(x, y)
        bank += (0.92 * east + 0.52 * west) * smooth(distance / 2.45) * smooth((y - 7) / 6)
        entry_drop = 0.43 * (1 - smooth((y - crossing + 1.5) / 9.6))
        height = water + bank - flooded - entry_drop * smooth(distance / 1.6)
        for px, py, target in self.slots:
            radius = np.hypot(x - px, (y - py + 0.13) / 1.16)
            if target == 0:
                height = mix(height, 0, 1 - smooth((radius - 0.79) / 0.63))
            else:
                height = mix(height, -0.221, 1 - smooth((radius - 0.74) / 0.74))
        return height, water

    def detail_allowed(self, x, y, radius, *, rock):
        y -= BASIN_ENTRY
        if y < 29 and abs(x) < 5.4 + radius:
            return False
        if any(np.hypot(x - px, y - py) < 1.9 + radius for px, py, _ in self.slots):
            return False
        return self.distance(x, y) > (0.72 if rock else 0.49) + 0.42 * radius


def read_texture(path):
    options = oiio.ImageSpec()
    options.attribute("oiio:UnassociatedAlpha", 1)
    source = oiio.ImageInput.open(str(path), options)
    if source is None:
        raise OSError(f"Unable to read {path}: {oiio.geterror()}")
    pixels = source.read_image(format=oiio.UINT8)
    source.close()
    return pixels[:, :, :3].astype(np.float32)


def sample(texture, u, v, repeat_u=True):
    """Sample originals in world space so contour movement does not stretch the paint."""
    height, width = texture.shape[:2]
    u = np.mod(u, 1) if repeat_u else np.clip(u, 0, 1)
    col = u * (width - 1)
    row = (1 - np.mod(v, 1)) * (height - 1)
    left, top = col.astype(np.int32), row.astype(np.int32)
    fx, fy = (col - left)[..., None], (row - top)[..., None]
    right = np.minimum(left + 1, width - 1)
    bottom = np.minimum(top + 1, height - 1)
    return mix(mix(texture[top, left], texture[top, right], fx),
               mix(texture[bottom, left], texture[bottom, right], fx), fy)


def upstream_paint(pixels, x, y):
    left, right, start, end = RIVER_BOUNDS
    # Clamp to the final atlas row where the basin extends beyond the river sheet.
    u = (x - left) / (right - left)
    v = np.minimum((y + BASIN_ENTRY - start) / (end - start), 1 - 1e-7)
    return sample(pixels, u, v, repeat_u=False)


def paint(field, destination, river_atlas):
    width, height = 1536, 1280
    x, y = np.meshgrid(np.linspace(-HALF_WIDTH, HALF_WIDTH, width, dtype=np.float32),
                       np.linspace(ATLAS_END, 0, height, dtype=np.float32))
    distance = field.distance(x, y)
    lake = smooth((y - 3) / 16)[..., None]
    reeds = 0.40 * np.sin(x * 0.93 + y * 0.38) + 0.25 * np.cos(y * 1.68 - 0.52 * x)
    inner_silt = bay(x, y, 0.35, 20.65, 5.7, 9.1, 0.27, 1.4)
    muddy_rim = (1 - smooth((distance + reeds - 0.42) / 2.4))[..., None]
    exposed = (1 - smooth((inner_silt + reeds + 0.23) / 2.45))[..., None]
    light_axis = np.interp(y, [0, 8, 16, 24, 32], [-0.2, -1.4, -3.8, -5.7, -6.1])
    warm_reflection = np.exp(-((x - light_axis) / 4.65) ** 2 - ((y - 18.0) / 12.2) ** 2)
    calm_water = np.zeros_like(x)
    for px, py, landing_height in field.slots:
        if landing_height < 0:
            calm_water = np.maximum(calm_water, np.exp(-((x - px) / 2.0) ** 2 - ((y - py) / 1.75) ** 2))

    textures = {key: read_texture(ART / relative) for key, relative in SOURCE_TEXTURES.items()}
    grass = sample(textures["grass"], x / 10 + 2.0, y / 10)
    grass = np.asarray((130, 139, 110)) + (grass - (169, 176, 142)) * 0.47
    grass += (3.1 * np.sin(x * 0.19 - y * 0.43) + 2.0 * np.cos(x * 0.73 + y * 0.25))[..., None]
    east, west = bank_shoulders(x, y)
    reed_shadow = (0.87 * east + 0.75 * west) * smooth(distance / 1.33)
    grass -= reed_shadow[..., None] * np.asarray((25.0, 18.0, 11.0))

    mud = sample(textures["mud"], x / 8.5 + 0.17, y / 8.5 + 0.37)
    mud_variation = (mud - (174, 152, 127)) * 0.64
    wet_mud = np.asarray((145, 134, 116)) + mud_variation
    dry_mud = np.asarray((163, 149, 124)) + mud_variation
    ground = mix(grass, dry_mud, exposed * (0.80 + 0.2 * lake))
    ground = mix(ground, wet_mud, muddy_rim * 0.91)
    damp = 1 - smooth((distance + reeds - 0.02) / 0.67)
    wet = sample(textures["wet"], x / 6.7 + 0.23, y / 6.5)
    washed_mud = np.asarray((137, 142, 122)) + (wet - (178, 187, 171)) * 0.38
    ground = mix(ground, washed_mud, damp[..., None] * 0.86)

    river = sample(textures["river"], 0.14 + (x + 42) / 84 * 0.72,
                   (y + BASIN_ENTRY) / 39, repeat_u=False)
    shallow = sample(textures["shallow"], (x - 0.15 * y) / 17.0 + 0.22, y / 17.0 + 0.22)
    deep = np.asarray((85, 124, 128)) + (river - (154, 179, 180)) * 0.54
    basin = np.asarray((103, 139, 139)) + (shallow - (173, 193, 177)) * 0.63
    light = warm_reflection * (1 - 0.85 * calm_water)
    basin += light[..., None] * np.asarray((37, 29, 12))
    # Broken light stays away from the two animated landing ripples.
    wave = np.cos(y * 5.8 + 0.70 * np.sin(x * 0.81 + y * 0.34))
    gaps = smooth((np.cos(x * 1.5 + y * 0.53) + 0.2) / 1.25)
    glints = np.maximum(wave, 0) ** 5 * gaps * light * smooth((-distance - 0.2) / 0.66)
    basin += glints[..., None] * np.asarray((25, 19, 8))
    water = mix(deep, basin, lake)
    shallows = np.asarray((120, 155, 148)) + (wet - (178, 187, 171)) * 0.37
    wash = 1 - smooth((-distance + 0.24 * reeds) / (2.15 + 0.33 * np.cos(y * 0.48)))
    water = mix(water, shallows, wash[..., None] * 0.81)
    water = mix(water, np.asarray((99, 139, 141)), calm_water[..., None] * 0.79)
    paint_color = mix(ground, water, (1 - smooth((distance + 0.28) / 0.85))[..., None])
    world_y = y + BASIN_ENTRY
    enrich(paint_color, x, world_y, distance, np.maximum(exposed, muddy_rim)[..., 0],
           {"grass": textures["grass"], "mud": textures["mud"], "silt": textures["wet"]})
    contact_shade(paint_color, x, world_y, placements("Basin", field.detail_allowed), smooth(distance / 0.5))

    ground_height, water_height = field.elevations(x, y, distance)
    surface_height = np.maximum(ground_height, water_height)
    inherited_height = river_elevation(x, y + BASIN_ENTRY, outlet=True)
    emerge = smooth((surface_height - inherited_height - 0.012) / 0.086)
    remain = 1 - emerge * smooth((y - 4) / 7.0)
    remain *= 1 - smooth((y - 10.5) / 3.4)
    upstream = upstream_paint(read_texture(river_atlas), x, y)
    paint_color = mix(paint_color, upstream, remain[..., None])

    pixels = np.ascontiguousarray(np.rint(np.clip(paint_color, 0, 255)), dtype=np.uint8)
    output = oiio.ImageOutput.create(str(destination))
    spec = oiio.ImageSpec(width, height, 3, oiio.UINT8)
    spec.attribute("oiio:ColorSpace", "sRGB")
    if output is None or not output.open(str(destination), spec) or not output.write_image(pixels):
        raise OSError(f"Unable to write {destination}: {oiio.geterror()}")
    output.close()


def make_material(stage):
    path = "/root/_materials/BasinPaint"
    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1)
    shader.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0))
    shader.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int).Set(1)
    surface = shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput().ConnectToSource(surface)
    reader = UsdShade.Shader.Define(stage, f"{path}/Coordinates")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.String).Set("st")
    pixels = UsdShade.Shader.Define(stage, f"{path}/Pigment")
    pixels.CreateIdAttr("UsdUVTexture")
    pixels.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(f"./textures/{ATLAS_NAME}"))
    pixels.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
    for axis in ("wrapS", "wrapT"):
        pixels.CreateInput(axis, Sdf.ValueTypeNames.Token).Set("clamp")
    pixels.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
        reader.CreateOutput("result", Sdf.ValueTypeNames.Float2))
    color = pixels.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(color)
    return material


def write_mesh(stage, path, positions, triangles, material):
    # The inherited USD root already converts +Y forward / +Z up for RealityKit.
    UsdGeom.Xform.Define(stage, path)
    mesh = UsdGeom.Mesh.Define(stage, f"{path}/Surface")
    xyz = np.asarray(positions, dtype=np.float32)
    vertices = Vt.Vec3fArray.FromNumpy(xyz)
    mesh.CreatePointsAttr(vertices)
    mesh.CreateExtentAttr(UsdGeom.PointBased.ComputeExtent(vertices))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(triangles), 3, dtype=np.int32)))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(np.ravel(np.asarray(triangles, dtype=np.int32))))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(True)
    texcoords = np.stack(((xyz[:, 0] + HALF_WIDTH) / (2 * HALF_WIDTH), xyz[:, 1] / ATLAS_END), axis=-1)
    UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex
    ).Set(Vt.Vec2fArray.FromNumpy(texcoords))
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)


def clip_water(points, indices, water_heights, depth, wet_points, wet_tris, vertex_ids):
    previous = indices[-1]
    polygon = []
    for current in indices:
        flooded = depth[current] > 0
        if (depth[previous] > 0) != flooded:
            a, b = sorted((previous, current))
            key = (a, b)
            if key not in vertex_ids:
                t = depth[a] / (depth[a] - depth[b])
                xy = mix(points[a, :2], points[b, :2], t)
                z = mix(water_heights[a], water_heights[b], t)
                vertex_ids[key] = len(wet_points)
                wet_points.append((xy[0], xy[1], z))
            polygon.append(vertex_ids[key])
        if flooded:
            if current not in vertex_ids:
                vertex_ids[current] = len(wet_points)
                wet_points.append((*points[current, :2], water_heights[current]))
            polygon.append(vertex_ids[current])
        previous = current
    for i in range(1, len(polygon) - 1):
        wet_tris.append([polygon[0], polygon[i], polygon[i + 1]])


def surfaces(stage, field, material):
    xs = np.concatenate(([-144, -72, -48], np.linspace(-32, 32, 129), [48, 72, 144]))
    ys = np.concatenate((np.linspace(0, 40, 81), np.arange(41, 50), [53, 59, 68, 80, 101, 150]))
    x, y = np.meshgrid(xs, ys)
    distance = field.distance(x, y)
    height, water = field.elevations(x, y, distance)
    wet_height = water.ravel()
    wet_depth = wet_height - height.ravel()
    points = np.stack((x.ravel(), y.ravel(), height.ravel()), axis=-1)
    ground_tris, wet_points, wet_tris = [], [], []
    known_vertices = {}
    columns = x.shape[1]
    for row in range(y.shape[0] - 1):
        for col in range(columns - 1):
            a = row * columns + col
            b, c, d = a + 1, a + 1 + columns, a + columns
            triangles = ((a, b, d), (b, c, d)) if (row + col) % 2 == 0 else ((a, b, c), (a, c, d))
            for triangle in triangles:
                ground_tris.append(triangle)
                if any(wet_depth[index] > 1e-9 for index in triangle):
                    clip_water(points, triangle, wet_height, wet_depth, wet_points, wet_tris, known_vertices)
    write_mesh(stage, "/root/LandingBasin_Ground", points, ground_tris, material)
    write_mesh(stage, "/root/LandingBasin_Water", wet_points, wet_tris, material)
    return {"terrainTriangles": len(ground_tris), "waterTriangles": len(wet_tris)}


def fit_reeds(stage, field):
    """Keep the LVL-S6 reed geometry and sink roots along the new wet margin."""
    group = stage.GetPrimAtPath(REEDS)
    mesh = UsdGeom.Mesh(next(child for child in group.GetChildren() if child.IsA(UsdGeom.Mesh)))
    points = np.asarray(mesh.GetPointsAttr().Get()).copy()
    x, y = points[:, 0], points[:, 1] + 20
    shore = field.distance(x, y)
    ground, water = field.elevations(x, y, shore)
    # Let partly submerged stems frame the channel, with the inner route kept open.
    lower = 0.48 * (1 - smooth((shore + 1.55) / 1.42))
    join = 0.50 * (1 - smooth((y - 0.8) / 9.4))
    root = np.maximum(ground, water - 0.30)
    east, west = bank_shoulders(x, y)
    open_middle = np.exp(-((x + 0.4) / 3.2) ** 2 - ((y - 16.4) / 6.9) ** 2)
    points[:, 2] += np.maximum(points[:, 2], 0) * (0.73 * east + 0.40 * west - 0.42 * open_middle)
    points[:, 2] += np.maximum(0, root) * 0.82 + np.minimum(0, root) * 0.45 - lower - join
    vertices = Vt.Vec3fArray.FromNumpy(points)
    mesh.GetPointsAttr().Set(vertices)
    mesh.GetExtentAttr().Set(UsdGeom.PointBased.ComputeExtent(vertices))


def prepare(destination, river_atlas):
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    baseline = json.loads(M10A.read_text())["ft_goose_scene_s6"]
    package = ROOT / "build/M10a/FeatherTide-M10a-Simulator.zip"
    with zipfile.ZipFile(package) as preview:
        source = preview.read("GooseChapterPreview/ft_goose_scene_s6.usdz")
    if hashlib.sha256(source).hexdigest() != baseline["exportSHA256"]:
        raise RuntimeError("M10a LVL-S6 output differs from the recorded SHA-256.")

    field = Basin()
    with tempfile.TemporaryDirectory(prefix="ft-route-basin-") as workspace:
        workspace = Path(workspace)
        original = workspace / "source.usdz"
        original.write_bytes(source)
        with zipfile.ZipFile(original) as archive:
            crate = next(name for name in archive.namelist() if name.endswith(".usdc"))
            archive.extractall(workspace)
        layer = workspace / crate
        stage = Usd.Stage.Open(str(layer))
        for name in (GROUND, WATER, "/root/S6_NorthMeadow",
                     "/root/S6_Continuous_WestBank", "/root/S6_Continuous_EastBank"):
            if not stage.RemovePrim(name):
                raise RuntimeError(f"Missing baseline mesh {name}")
        reed_materials = {
            bound.GetPath()
            for prim in Usd.PrimRange(stage.GetPrimAtPath(REEDS))
            for bound, _ in [UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()]
            if bound
        }
        materials = stage.GetPrimAtPath("/root/_materials")
        for material in list(materials.GetChildren()):
            if material.GetPath() not in reed_materials:
                stage.RemovePrim(material.GetPath())
        fit_reeds(stage, field)
        paint(field, workspace / "textures" / ATLAS_NAME, river_atlas)
        rendered = surfaces(stage, field, make_material(stage))
        stage.GetRootLayer().Save()
        if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(layer)), str(destination)):
            raise RuntimeError(f"Unable to package {destination}")
    return {
        "source": baseline["source"],
        "m10aSHA256": baseline["exportSHA256"],
        "layout": str(LAYOUT.relative_to(ROOT)),
        "upstreamAtlasSHA256": digest(river_atlas),
        "textureSources": {
            str((ART / relative).relative_to(ROOT)): digest(ART / relative)
            for relative in SOURCE_TEXTURES.values()
        },
        "exportSHA256": digest(destination),
        **rendered,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--river-atlas", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.destination, arguments.river_atlas), indent=2))
