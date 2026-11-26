"""Bake one continuous opening and first-shore surface under the authored layout."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import numpy as np

from ground_detail import MATERIALS, contact_shade, enrich, placements

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
ART = ROOT / "Assets/Watercolor/Goose/Blender"
BASELINE = ROOT / "build/GooseLinearRoute3D/FeatherTide-GooseLinearRoute3D-Simulator.zip"
MANIFEST = ROOT / "Assets/Processed/Goose/LinearRoute3D/preview-manifest.json"
USD_PYTHON = "/Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13"
TEXTURE_NAMES = {
    **MATERIALS,
    "shallow": "MAT-004/v001/textures/ft_goose_mat_water_shallow_basecolor_alpha.png",
    "river": "MAT-004/v001/textures/ft_goose_mat_water_river_basecolor_alpha.png",
}
FORWARD_SCALE = 28 / 36
TEXTURE_HALF_WIDTH = 46
STAGES = ("ft_goose_scene_s0", "ft_goose_scene_s1")
TERRAIN_TEXTURE = "ft_goose_opening_terrain_s0.jpg"
TERRAIN_START = -40.0 * FORWARD_SCALE
TERRAIN_END = 88.0


def ramp(edge0, edge1, value):
    t = np.clip((value - edge0) / (edge1 - edge0), 0, 1)
    return t * t * (3 - 2 * t)


def world_forward(stage, y):
    return y * FORWARD_SCALE if stage == 0 else y + 28


def cove(x, y, cx, cy, rx, ry, bend, phase):
    along = (y - cy) / ry
    side = (x - cx - bend * np.sin(along * 1.55 + phase)) / rx
    angle = np.arctan2(along, side)
    outline = 1 + 0.105 * np.sin(angle * 3 + phase) + 0.058 * np.cos(angle * 5 - phase)
    return (outline - np.hypot(side, along)) * min(rx, ry)


def fog_channel_center(y):
    return 0.6 + 1.35 * np.sin((y - 13.0) * 0.17)


def fog_islands(x, y):
    west = cove(x, y, -5.3, 19.2, 3.4, 7.2, 0.65, 0.4)
    east = cove(x, y, 6.4, 29.6, 3.9, 7.9, -0.85, 2.1)
    return west, east


def opening_depth(x, y):
    water = np.maximum.reduce([
        cove(x, y, -8.6, 10.2, 4.9, 12.2, 1.1, 0.6),
        cove(x, y, 11.4, 13.2, 5.2, 15.4, -1.8, 1.9),
        cove(x, y, 6.2, -4.1, 4.9, 3.7, 0.9, 2.3),
        cove(x, y, -10.8, 32, 4.3, 12.4, 1.3, 0.4),
        cove(x, y, 9.8, 41.5, 4.5, 14.7, -1.4, 1.1),
        cove(x, y, -11.6, 57.5, 5.8, 14.2, 2.3, 1.6),
        cove(x, y, -8.4, 74.9, 4.75, 10.2, -1.1, 2.5),
        cove(x, y, 6.8, 70.6, 4.1, 9.5, 1.6, 0.2),
    ])
    inlet = 6.2 + 0.9 * np.sin(y * 0.23 + 0.8) + ramp(77, 90, y) * 4.5
    offset = 1.40 * np.sin(y * 0.12 + 0.85) + 1.10
    depth = np.maximum(water, np.minimum(inlet - np.abs(x - offset), (y - 80.5) * 0.85))
    # Offset the banks around a single pool that points through the fog gate.
    sides = fog_islands(x, y)
    depth = np.minimum(depth, 0.35 - np.maximum(*sides))
    channel_width = 2.3 + 0.52 * np.sin(y * 0.23 + 0.6)
    channel = np.minimum(channel_width - np.abs(x - fog_channel_center(y)),
                         np.minimum((y - 11.0) * 0.43, (43.0 - y) * 0.36))
    depth = np.maximum(depth, channel)
    # The atlas and relief share dry contact floors for both authored stances.
    opening_clear = 1 - ramp(0.78, 1, np.hypot(x / 4.7, (y + 0.8) / 3.7))
    shore_clear = 1 - ramp(0.78, 1, np.hypot((x + 0.65) / 4.2, (y - 77.6) / 5.1))
    clearing = np.maximum(opening_clear, shore_clear)
    return np.minimum(depth, 12 - 13.8 * clearing)


def height(x, y):
    depth = opening_depth(x, y)
    # Submerge only the exit overlap. The playable first rest lies at y=78.
    outer = np.clip((np.abs(x) - 11) / 14, 0, 1)
    edge = 83.05 + 0.65 * np.sin(x * 0.27) + 0.44 * np.sin(x * 0.65) + 0.80 * outer
    west, east = fog_islands(x, y)
    island_banks = np.maximum(0.43 * ramp(0.1, 2.8, west), 0.57 * ramp(0.1, 3.2, east))
    east_rest_bank = 0.46 * ramp(0.1, 2.6, cove(x, y, 7.1, 77.2, 3.05, 5.7, -0.4, 1.4))
    relief = np.maximum(island_banks, east_rest_bank) * (1 - ramp(-0.35, 0.34, depth))
    return relief - 0.18 * ramp(0, 1.25, depth) - 0.42 * ramp(edge, 87.9, y)


def detail_allowed(x, y, radius, *, rock):
    if abs(x) < 2.8 + radius or np.hypot(x + 0.65, y - 78) < 3.55 + radius:
        return False
    if y < 3 and abs(x) < 3.7 + radius:
        return False
    return opening_depth(x, y) < -0.22 - 0.22 * radius


def mix(a, b, amount):
    return np.asarray(a) + (np.asarray(b) - a) * amount[..., None]


def pigment(src, x, y, scale, stretch=1):
    """Sample the original seamless repeat via the same coordinates on both sections."""
    rows, cols = src.shape[:2]
    u = x / scale + (y / scale) * 0.075
    v = y / (scale * stretch) - x / scale * 0.035
    return src[(np.floor(v * rows).astype("int32") % rows), (np.floor(u * cols).astype("int32") % cols)]


def paint(textures, x, y):
    d = opening_depth(x, y)
    field = np.sin(x * 0.27 + y * 0.17) * np.sin(y * 0.38 - x * 0.20)
    blooms = np.sin(y * 0.77 + x * 0.55) * np.cos(x * 0.92 - y * 0.44)
    texture = {k: v - np.mean(v, axis=(0, 1), keepdims=True) for k, v in textures.items()}
    grass = np.array([141, 151, 117]) + [0.8, 1.0, 0.7] * (field * 8 + blooms * 2.6)[..., None]
    mud = np.array([153, 138, 115]) + [1.0, 0.87, 0.67] * (field * 6 + blooms * 2)[..., None]
    grass = grass + pigment(texture["grass"], x, y, 15) * 0.55
    mud = mud + pigment(texture["mud"], x, y, 11) * 0.63
    spawn_terrace = 1 - ramp(0.65, 1.12, np.hypot((x + 0.55) / 7, (y + 1.8 + np.sin(x * .37)) / 5.2))
    shore_center = -0.65 - 0.19 * np.maximum(78 - y, 0)
    shore_terrace = 1 - ramp(0.45, 1.09, np.hypot((x - shore_center) / 3.7, (y - 76.3) / 7.5))
    exposed_west_shore = np.exp(-((x + 4.8) / 3.4) ** 2 - ((y - 73.2) / 3.7) ** 2)
    east_sedge = np.exp(-((x - 6.4) / 2.8) ** 2 - ((y - 75.3) / 3.2) ** 2)
    mud_width = 1.95 + blooms * 0.68 + exposed_west_shore * 1.05 - east_sedge * 0.75
    grass_to_mud = np.maximum(ramp(-mud_width, -0.16, d + blooms * 0.26) * 0.88,
                              np.maximum(spawn_terrace, shore_terrace) * 0.80)
    land = mix(grass, mud, grass_to_mud)
    west, east = fog_islands(x, y)
    reed_shadow = np.maximum(ramp(-0.6, 2.7, west), 0.83 * ramp(-0.4, 2.9, east))
    land += reed_shadow[..., None] * np.array([-25, -21, -12])
    land += (shore_terrace * (0.55 + 0.45 * exposed_west_shore))[..., None] * np.array([15, 8, 1])
    low_light = np.exp(-((x - fog_channel_center(y)) / 2.2) ** 2 - ((y - 25.5) / 13.5) ** 2)
    autumn = np.exp(-((x + 6.7) / 12.5)**2 - ((y - 6.0) / 21)**2)
    land = land + np.array([12.0, 8.3, 2.1]) * (low_light * .65 + autumn * .35)[..., None]
    water_pigment = pigment(texture["shallow"], x, y, 16, 1.2)
    shallow = np.array([120, 155, 141]) + water_pigment * 0.61
    water = np.array([104, 143, 144]) + pigment(texture["river"], x, y, 23, 1.45) * 0.69
    # Broken horizontal highlights stay inside the water and follow the bent opening.
    ripple = np.sin(y * 4.1 + np.sin(x * 0.65) * 0.80 + np.sin(y * 0.40) * 0.95)
    glint = np.maximum(0, ripple) ** 4 * (0.6 + 0.4 * blooms)
    reflected = np.array([204, 188, 143]) + water_pigment * 0.70 + glint[..., None] * [19, 14, 5]
    water = mix(water, reflected, low_light * 0.87 + autumn * 0.12)
    shallow = mix(shallow, reflected, low_light * (0.57 + 0.13 * glint))
    water = mix(water, np.array([85, 124, 128]) + pigment(texture["river"], x, y, 23, 1.45) * 0.54,
                ramp(77, 88, y))
    land = mix(land, np.array([130, 139, 110]) + pigment(texture["grass"], x, y, 15) * 0.36,
               ramp(78, 88, y) * (1 - grass_to_mud))
    inner = mix(shallow, water, ramp(0.05, 2.25 + 0.48 * field + 0.38 * exposed_west_shore, d))
    inner = mix(inner, reflected, low_light * 0.32 * ramp(0.15, 0.9, d))
    damp_lip = ramp(-0.50, -0.06, d) * (1 - ramp(0.08, 0.55, d))
    inner = mix(inner, np.array([166, 171, 143]), damp_lip * (0.19 + low_light * 0.20))
    color = mix(land, inner, ramp(-0.42, 0.73, d))
    enrich(color, x, y, -d, grass_to_mud, {key: textures[key] for key in MATERIALS})
    return contact_shade(color, x, y, placements("Opening", detail_allowed), 1 - ramp(-0.26, 0.12, d))


def sample_river(atlas, x, y):
    from landscape import BOUNDS

    left, right, start, end = BOUNDS
    rows, columns = atlas.shape[:2]
    u = np.clip((x - left) / (right - left) * (columns - 1), 0, columns - 1)
    v = np.clip((end - y) / (end - start) * (rows - 1), 0, rows - 1)
    i, j = np.floor(u).astype("int32"), np.floor(v).astype("int32")
    next_i, next_j = np.minimum(i + 1, columns - 1), np.minimum(j + 1, rows - 1)
    upper = mix(atlas[j, i], atlas[j, next_i], u - i)
    lower = mix(atlas[next_j, i], atlas[next_j, next_i], u - i)
    return mix(upper, lower, v - j)


def bake_texture(destination, textures, river_atlas):
    from PIL import Image

    x = np.linspace(-TEXTURE_HALF_WIDTH, TEXTURE_HALF_WIDTH, 1536, dtype=np.float32)
    y = np.linspace(TERRAIN_END, TERRAIN_START, 2048, dtype=np.float32)
    x, y = np.meshgrid(x, y)
    image = paint(textures, x, y)
    # Match the color beneath the submerged lip before the two meshes cross.
    image = mix(image, sample_river(river_atlas, x, y), ramp(81.7, 85.6, y))
    image = mix(image, np.array([126, 137, 109]), ramp(43, TEXTURE_HALF_WIDTH, np.abs(x)))
    Image.fromarray(np.clip(image + 0.5, 0, 255).astype("uint8")).save(
        destination, quality=91, subsampling=0, optimize=True
    )


def tint_ridges(texture_directory):
    from PIL import Image

    colors = ((100, 121, 133), (115, 133, 147), (133, 148, 160))
    for variant, tint in zip("abc", colors):
        for path in texture_directory.glob(f"*far_ridge_{variant}_basecolor*.png"):
            with Image.open(path) as source:
                image = np.asarray(source.convert("RGB"), dtype=np.float32)
            pigment = image.mean(axis=2)
            color = np.array(tint) + 1.4 * (pigment - pigment.mean())[..., None]
            Image.fromarray(np.clip(color + 0.5, 0, 255).astype("uint8")).save(path)


def prepare(output, usd_python, river_atlas_path):
    from PIL import Image

    known = json.loads(MANIFEST.read_text())
    with Image.open(river_atlas_path) as file:
        river_atlas = np.asarray(file.convert("RGB"), dtype=np.float32)
    river_sha = hashlib.sha256(river_atlas_path.read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    preview_manifest = output / "manifest.json"
    records = json.loads(preview_manifest.read_text()) if preview_manifest.exists() else {}
    textures = {k: np.asarray(Image.open(ART / path).convert("RGB"), dtype=np.float32)
                for k, path in TEXTURE_NAMES.items()}
    with zipfile.ZipFile(BASELINE) as package:
        for stage, name in enumerate(STAGES):
            data = package.read(f"GooseLinearPreview/{name}.usdz")
            sha = hashlib.sha256(data).hexdigest()
            if sha != known[name]["exportSHA256"]:
                raise RuntimeError(f"{name} does not match the baseline manifest")
            with tempfile.TemporaryDirectory(prefix=f"feathertide-opening-s{stage}-") as temp:
                workspace = Path(temp)
                with zipfile.ZipFile(io.BytesIO(data)) as asset:
                    asset.extractall(workspace)
                tint_ridges(workspace / "textures")
                if stage == 0:
                    texture = workspace / "textures" / TERRAIN_TEXTURE
                    bake_texture(texture, textures, river_atlas)
                    delivery_texture = output / TERRAIN_TEXTURE
                    delivery_texture.write_bytes(texture.read_bytes())
                    records[delivery_texture.stem] = {
                        "extension": "jpg",
                        "exportSHA256": hashlib.sha256(delivery_texture.read_bytes()).hexdigest(),
                        "samePixelsIn": f"{name}.usdz",
                    }
                destination = output / f"{name}.usdz"
                subprocess.run([usd_python, __file__, "--usd", str(stage), str(workspace), str(destination)], check=True)
            records[name] = {
                "source": known[name]["source"],
                "baselineSHA256": sha,
                **({"riverAtlasSHA256": river_sha} if stage == 0 else {}),
                "materialInputs": {
                    str((ART / path).relative_to(ROOT)): hashlib.sha256((ART / path).read_bytes()).hexdigest()
                    for path in TEXTURE_NAMES.values()
                },
                "exportSHA256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "treatment": (
                    "Single contact floor with an illuminated channel framed by staggered low reed banks"
                    if stage == 0 else "First-shore landing tongue, retained rocks and raised east reeds over S0"
                ),
            }
    preview_manifest.write_text(json.dumps(records, indent=2) + "\n")


def write_usd(stage_index, work, out):
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils, Vt

    name = STAGES[stage_index]
    layer = work / f"{name}.usdc"
    stage = Usd.Stage.Open(str(layer))
    root = "/root"
    section = root + ("/S0_StartWetland" if stage_index == 0 else "/S1_Tailwind")
    remove = (
        section + "/S0_ShallowWater", section + "/S0_ContactGround",
    ) if stage_index == 0 else (
        section + "/Tailwind_Approach_Tiles", section + "/CheckpointA_Visual/CheckpointA_Ground",
        section + "/CheckpointA_Visual/CheckpointA_Water", section + "/Rest_Pad_Sheen",
        root + "/S1_Meandering_side_waterway",
    )
    remove = list(remove)
    transforms = UsdGeom.XformCache()
    reeds = []
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        name = str(prim.GetName())
        if name.startswith(("S0_OuterTerrain_", "S1_OuterTerrain_")):
            if prim.GetParent().GetPath() == Sdf.Path(root):
                remove.append(path)
        if name.startswith(("S0_OuterRidge_", "S1_OuterRidge_", "S0_Ridge_")) and prim.IsA(UsdGeom.Xform):
            # Wide basins have restrained, distant silhouettes instead of near-white ridges.
            xform = UsdGeom.Xformable(prim)
            translation = next((op for op in xform.GetOrderedXformOps()
                                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate), None)
            if translation:
                pt = translation.Get()
                translation.Set(type(pt)(pt[0] * 1.45, pt[1] + (24 if stage_index == 0 else 19), pt[2] - 0.42))
        if prim.IsA(UsdGeom.Mesh) and "ShoreReed" in path:
            mesh = UsdGeom.Mesh(prim)
            pts = mesh.GetPointsAttr().Get()
            matrix = transforms.GetLocalToWorldTransform(prim)
            center = matrix.Transform(sum(pts, Gf.Vec3f()) / len(pts))
            x, native_y = center[0], -center[2]
            forward = world_forward(stage_index, native_y)
            delta_x, delta_forward = 0, 0
            if path.startswith("/root/S0_ShoreReed_06_"):
                delta_x, delta_forward = 4.4, -2.6
            elif path.startswith("/root/S0_ShoreReed_07_"):
                delta_x, delta_forward = -5.4, 8.0
            x += delta_x
            forward += delta_forward
            target = float(height(x, forward))
            current_base = min(matrix.Transform(point)[1] for point in pts)
            west_stand = np.exp(-((x + 8.8) / 4.0) ** 2 - ((forward - 67) / 7.0) ** 2)
            east_stand = np.exp(-((x - 7.3) / 3.5) ** 2 - ((forward - 76) / 4.7) ** 2)
            island = float(ramp(0.2, 2.8, np.maximum(*fog_islands(x, forward))))
            stature = (0.85 + 0.17 * np.sin(x * 1.63 + forward * 0.92)
                       + 0.25 * west_stand + 0.73 * east_stand + 0.35 * island)
            local_forward = delta_forward / FORWARD_SCALE if stage_index == 0 else delta_forward
            reeds.append((mesh, pts, matrix, current_base, target, stature, delta_x, local_forward))
            # Leave a broad opening on the right bank and vary the left foreground.
            if stage_index == 0 and x > 0 and native_y < 12 and any(digit in path for digit in ("_01_02_", "_01_05_", "_01_08_", "_03_03_", "_03_06_")):
                remove.append(str(prim.GetParent().GetPath()))
        if stage_index == 0 and prim.IsA(UsdGeom.Xform) and name in (
            "Fog_DistantEast", "Fog_DistantWest", "Fog_ShoreEast", "Fog_ShoreWest"
        ):
            xform = UsdGeom.Xformable(prim)
            translation = next(op for op in xform.GetOrderedXformOps()
                               if op.GetOpType() == UsdGeom.XformOp.TypeTranslate)
            x, y, z = translation.Get()
            translation.Set(Gf.Vec3d(x + np.copysign(1.7, x), y + (3.8 if x > 0 else 0), z * 0.72))
    for path in remove:
        stage.RemovePrim(path)
    for mesh, pts, matrix, base, target, stature, delta_x, delta_forward in reeds:
        if not mesh.GetPrim().IsValid():
            continue
        inverse = matrix.GetInverse()
        positions = []
        for point in pts:
            world = matrix.Transform(point)
            world[0] += delta_x
            world[1] = target + (world[1] - base) * stature
            world[2] -= delta_forward
            positions.append(Gf.Vec3f(*inverse.Transform(world)))
        mesh.GetPointsAttr().Set(positions)
        mesh.GetExtentAttr().Set(UsdGeom.PointBased.ComputeExtent(positions))

    if stage_index == 0:
        install_terrain(stage, root, section)

    used = set()
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            bound = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
            if bound:
                used.add(bound.GetPath())
    for prim in stage.GetPrimAtPath(root + "/_materials").GetChildren():
        if prim.GetPath() not in used:
            stage.RemovePrim(prim.GetPath())
    stage.GetRootLayer().Save()
    if out.exists():
        out.unlink()
    if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(layer)), str(out)):
        raise RuntimeError(f"Could not package {out}")


def install_terrain(stage, root, section):
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    paint_path = root + "/_materials/OpeningShorePaint"
    material = UsdShade.Material.Define(stage, paint_path)
    preview = UsdShade.Shader.Define(stage, paint_path + "/Surface")
    preview.CreateIdAttr("UsdPreviewSurface")
    preview.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.96)
    preview.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0)
    preview.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0))
    preview.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int).Set(1)
    texture = UsdShade.Shader.Define(stage, paint_path + "/Atlas")
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(
        Sdf.AssetPath(f"./textures/{TERRAIN_TEXTURE}")
    )
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
    for axis in ("S", "T"):
        texture.CreateInput("wrap" + axis, Sdf.ValueTypeNames.Token).Set("clamp")
    reader = UsdShade.Shader.Define(stage, paint_path + "/UV")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.String).Set("st")
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
        reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    )
    preview.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    )
    material.CreateSurfaceOutput().ConnectToSource(preview.CreateOutput("surface", Sdf.ValueTypeNames.Token))

    mesh = UsdGeom.Mesh.Define(stage, section + "/OpeningShoreTerrain")
    # Author in S0's local axes so the same surface spans both scenes after mounting.
    xs = np.concatenate((np.linspace(-148, -30.5, 11), np.linspace(-30, 30, 151), np.linspace(30.5, 148, 11)))
    ys = np.linspace(TERRAIN_START, TERRAIN_END, 1 + round((TERRAIN_END - TERRAIN_START) / 0.34))
    x, y = np.meshgrid(xs, ys)
    z = height(x, y)
    points = np.stack([x, y / FORWARD_SCALE, z], axis=-1).reshape(-1, 3)
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(points.astype("float32")))
    mesh.CreateExtentAttr(UsdGeom.PointBased.ComputeExtent(mesh.GetPointsAttr().Get()))
    uv = np.stack([(x + TEXTURE_HALF_WIDTH) / (2 * TEXTURE_HALF_WIDTH),
                   (y - TERRAIN_START) / (TERRAIN_END - TERRAIN_START)], axis=-1)
    UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex).Set(
        Vt.Vec2fArray.FromNumpy(uv.reshape(-1, 2).astype("float32")))
    a = np.arange(x.size, dtype="int32").reshape(x.shape)[:-1, :-1].ravel()
    faces = np.stack([a, a + 1, a + len(xs) + 1, a + len(xs)], axis=-1)
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(faces), 4, dtype="int32")))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(faces.ravel()))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("output", nargs="?", type=Path)
    args.add_argument("--river-atlas", type=Path,
                      help="Baked late-route atlas, defaults to ft_goose_linear_landscape.jpg under output")
    args.add_argument("--usd-python", default=USD_PYTHON)
    args.add_argument("--usd", nargs=3, help=argparse.SUPPRESS)
    options = args.parse_args()
    if options.usd:
        index, workspace, destination = options.usd
        write_usd(int(index), Path(workspace), Path(destination))
    elif options.output:
        atlas = options.river_atlas or options.output / "ft_goose_linear_landscape.jpg"
        prepare(options.output.resolve(), options.usd_python, atlas)
    else:
        args.error("output is required")
