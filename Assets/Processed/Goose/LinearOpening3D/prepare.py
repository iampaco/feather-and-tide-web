"""Prepare the private single-route preview with Blender's USD Python bindings."""
import hashlib
import io
import json
import math
import sys
import tempfile
import zipfile
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdUtils


def sha(data):
    return hashlib.sha256(data).hexdigest()


def adapt_shallows(data, destination):
    # The north edge descends into the next stretch of water. A varied shoreline
    # breaks the straight export boundary while leaving the landing pad untouched.
    with tempfile.TemporaryDirectory(prefix="feathertide-shallows-") as workspace:
        with zipfile.ZipFile(data) as source:
            source.extractall(workspace)
        layer = Path(workspace) / "ft_goose_scene_s1.usdc"
        stage = Usd.Stage.Open(str(layer))
        transforms = UsdGeom.XformCache()
        updated = 0
        for prim in stage.Traverse():
            if not prim.IsA(UsdGeom.Mesh):
                continue
            mesh = UsdGeom.Mesh(prim)
            matrix = transforms.GetLocalToWorldTransform(prim)
            inverse = matrix.GetInverse()
            points = mesh.GetPointsAttr().Get()
            for index, point in enumerate(points):
                world = matrix.Transform(point)
                start = 54 + 1.2 * math.sin(world[0] * 0.28) + 0.65 * math.sin(world[0] * 0.71)
                fraction = max(0, min(1, (-world[2] - start) / (60 - start)))
                if fraction == 0:
                    continue
                world[1] -= 0.86 * fraction**2 * (3 - 2 * fraction)
                points[index] = Gf.Vec3f(*inverse.Transform(world))
                updated += 1
            mesh.GetPointsAttr().Set(points)
            mesh.GetExtentAttr().Set(UsdGeom.PointBased.ComputeExtent(points))
        if updated == 0:
            raise RuntimeError("No authored wetland vertices crossed the transition")
        stage.GetRootLayer().Save()
        if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(layer)), str(destination)):
            raise RuntimeError("Could not package the wetland USDZ")


def prepare(output):
    root = Path(__file__).resolve().parents[4]
    opening = root / "Assets/Processed/Goose/M10a-chapter-polish/preview-manifest.json"
    known = json.loads(opening.read_bytes())
    names = ["ft_goose_actor_" + clip for clip in ("cruise", "takeoff", "glide", "form", "land", "water", "rest")]
    names += ["ft_goose_scene_s0", "ft_goose_scene_s1"]
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    with zipfile.ZipFile(root / "build/M10a/FeatherTide-M10a-Simulator.zip") as package:
        for name in names:
            filename = name + ".usdz"
            data = package.read("GooseChapterPreview/" + filename)
            source_hash = sha(data)
            if source_hash != known[name]["exportSHA256"]:
                raise RuntimeError("M10a preview source differs from its recorded hash: " + filename)
            destination = output / filename
            if name == "ft_goose_scene_s1":
                adapt_shallows(io.BytesIO(data), destination)
            else:
                destination.write_bytes(data)
            result[name] = {
                "source": known[name]["source"],
                "clip": known[name]["clip"],
                "m10aSHA256": source_hash,
                "exportSHA256": sha(destination.read_bytes()),
            }
            print("Prepared", destination.name, flush=True)
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    prepare(Path(sys.argv[sys.argv.index("--") + 1]).resolve())
