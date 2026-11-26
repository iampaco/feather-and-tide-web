"""Package the route's fixed world-space relief and bank reeds with Blender's OpenUSD Python."""
import argparse
from pathlib import Path

import numpy as np
from pxr import Sdf, Usd, UsdGeom, UsdUtils, Vt


def mesh(stage, name, points, faces):
    value = UsdGeom.Mesh.Define(stage, "/Landscape/" + name)
    value.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(points.astype(np.float32)))
    value.GetFaceVertexCountsAttr().Set(Vt.IntArray.FromNumpy(
        np.full(faces.shape[0], faces.shape[1], dtype=np.int32)))
    value.GetFaceVertexIndicesAttr().Set(Vt.IntArray.FromNumpy(faces.astype(np.int32).ravel()))
    value.GetExtentAttr().Set(UsdGeom.PointBased.ComputeExtent(value.GetPointsAttr().Get()))
    value.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
    return value


def terrain(stage, directory):
    grid = np.load(directory / ".route-mesh.npz")
    x, y, height = (grid[key] for key in ("x", "y", "height"))
    rows, cols = x.shape
    points = np.column_stack((x.ravel(), height.ravel(), -y.ravel()))
    base = np.arange(rows * cols).reshape(x.shape)[:-1, :-1].ravel()
    faces = np.column_stack((base, base + 1, base + cols + 1, base + cols))
    ground = mesh(stage, "RouteGround", points, faces)
    uv = np.column_stack(((x.ravel() - x.min()) / np.ptp(x), (y.ravel() - y.min()) / np.ptp(y)))
    coordinates = UsdGeom.PrimvarsAPI(ground).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    coordinates.Set(Vt.Vec2fArray.FromNumpy(uv.astype(np.float32)))


def reeds(stage, directory):
    rng = np.random.default_rng(407)
    stems, seeds, leaves = [], [], []
    for x, y, height, size, marsh in np.loadtxt(directory / ".route-reeds.tsv"):
        for _ in range(rng.integers(4, 8)):
            angle = rng.uniform(0, 2 * np.pi)
            width = rng.uniform(0.010, 0.026)
            axis_x, axis_y = np.cos(angle), np.sin(angle)
            xx, zz = x + rng.normal(0, 0.12), -y + rng.normal(0, 0.12)
            bent_x = xx + 0.13 * size * axis_x
            bent_z = zz + 0.11 * size * axis_y
            top = height + size * rng.uniform(0.44, 1.09)
            stems.extend([(xx - width * axis_x, height, zz - width * axis_y),
                          (xx + width * axis_x, height, zz + width * axis_y), (bent_x, top, bent_z)])
            if rng.random() < 0.28:
                seeds.extend([(bent_x - 0.020, top - 0.052, bent_z),
                              (bent_x + 0.022, top - 0.041, bent_z),
                              (bent_x + 0.005, top + size * 0.10, bent_z + 0.01)])
            if marsh:
                leaf_direction = rng.uniform(0, 2 * np.pi)
                reach = rng.uniform(0.19, 0.46) * size
                wide = rng.uniform(0.031, 0.058) * size
                dx, dz = np.cos(leaf_direction), np.sin(leaf_direction)
                base = np.array((xx, height + (top - height) * 0.19, zz))
                middle = base + np.array((dx * reach * 0.51, size * 0.38, dz * reach * 0.51))
                side = np.array((-dz * wide, 0, dx * wide))
                tip = base + np.array((dx * reach, size * rng.uniform(0.37, 0.67), dz * reach))
                leaves.extend((base, middle - side, middle + side, middle - side, tip, middle + side))
    for name, data in (("BankStems", stems), ("BankSeeds", seeds), ("MarshReedLeaves", leaves)):
        points = np.asarray(data)
        blades = mesh(stage, name, points, np.arange(len(points)).reshape(-1, 3))
        blades.GetDoubleSidedAttr().Set(True)


def water_glints(stage, directory):
    points, faces = [], []
    for x, y, height, length, width, angle in np.loadtxt(directory / ".route-water.tsv"):
        root = np.array((x, height, -y))
        along = np.array((np.cos(angle), 0, -np.sin(angle)))
        across = np.array((-np.sin(angle), 0, -np.cos(angle)))
        base = len(points)
        # Narrow ends and an off-center bend keep each patch from reading as a
        # second set of navigation marks.
        points.extend((
            root - along * length * 0.51,
            root - along * length * 0.23 + across * width * 0.30,
            root + along * length * 0.16 + across * width * 0.88,
            root + along * length * 0.49 + across * width * 0.42,
            root + along * length * 0.12 - across * width * 0.15,
            root - along * length * 0.25 - across * width * 0.44,
        ))
        faces.extend(tuple(base + index for index in triangle)
                     for triangle in ((0, 1, 5), (1, 2, 5), (2, 4, 5), (2, 3, 4)))
    glints = mesh(stage, "ShallowWaterGlints", np.asarray(points), np.asarray(faces))
    glints.GetDoubleSidedAttr().Set(True)


def package(directory):
    path = directory / ".route-geometry.usdc"
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/Landscape").GetPrim())
    terrain(stage, directory)
    reeds(stage, directory)
    water_glints(stage, directory)
    stage.GetRootLayer().Save()
    destination = directory / "ft_goose_linear_landscape.usdz"
    destination.unlink(missing_ok=True)
    if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(path)), str(destination), "landscape.usdc"):
        raise RuntimeError("Cannot package river relief")
    for temporary in (path, directory / ".route-mesh.npz", directory / ".route-reeds.tsv", directory / ".route-water.tsv"):
        temporary.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    package(parser.parse_args().directory.resolve())
