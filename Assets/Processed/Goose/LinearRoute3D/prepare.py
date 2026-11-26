"""Adapt the turbine, protected marsh and landing basin for the single-route Debug."""
import importlib.util
import io
import json
import math
import sys
import tempfile
import zipfile
from pathlib import Path

import bpy
from pxr import Gf, Sdf, Usd, UsdGeom, UsdUtils

ROOT = Path(__file__).resolve().parents[4]
ART = ROOT / "Assets/Watercolor/Goose/Blender"
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("opening", Path(__file__).parent.parent / "LinearOpening3D/prepare.py")
opening = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opening)


def smoothstep(value):
    t = min(1, max(0, value))
    return t * t * (3 - 2 * t)


def adapt_terrain(source, destination, drop, flatten_marsh=False):
    with tempfile.TemporaryDirectory(prefix="feathertide-route-") as temp:
        with zipfile.ZipFile(source) as package:
            crate = next(name for name in package.namelist() if name.endswith(".usdc"))
            package.extractall(temp)
        layer = Path(temp) / crate
        stage = Usd.Stage.Open(str(layer))
        transforms = UsdGeom.XformCache()
        lowered = 0
        flattened = 0
        for prim in stage.Traverse():
            if not prim.IsA(UsdGeom.Mesh):
                continue
            mesh = UsdGeom.Mesh(prim)
            matrix = transforms.GetLocalToWorldTransform(prim)
            inverse = matrix.GetInverse()
            points = mesh.GetPointsAttr().Get()
            authored_ground = flatten_marsh and "ProtectedMarsh_Ground" in str(prim.GetPath())
            modified = False
            for index, point in enumerate(points):
                world = matrix.Transform(point)
                x, y, height = world[0], -world[2], world[1]
                if authored_ground:
                    # Form a shallow dry apron at the existing twelve rest positions.
                    outside = max(abs(x + 3.6) - 6.5, abs(y) - 6.5, 0)
                    height *= smoothstep(outside / 3.2)
                    flattened += height != world[1]
                amount = drop(x, y)
                lowered += amount > 0
                changed = height - amount
                if changed != world[1]:
                    world[1] = changed
                    points[index] = Gf.Vec3f(*inverse.Transform(world))
                    modified = True
            if modified:
                mesh.GetPointsAttr().Set(points)
                mesh.GetExtentAttr().Set(UsdGeom.PointBased.ComputeExtent(points))
        if lowered == 0 or (flatten_marsh and flattened == 0):
            raise RuntimeError(f"No mesh vertices crossed the transition or rest apron in {crate}")
        stage.GetRootLayer().Save()
        if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(layer)), str(destination)):
            raise RuntimeError(f"Could not package {destination}")
        return lowered, flattened


def export_glb(source, destination):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    for material in bpy.data.materials:
        if not material.use_nodes or material.node_tree is None:
            continue
        nodes = material.node_tree.nodes
        emission = next((node for node in nodes if node.type == "EMISSION"), None)
        if emission is None or any(node.type == "BSDF_PRINCIPLED" for node in nodes):
            continue
        # Use the authored image and alpha on a surface RealityKit can import.
        surface = nodes.new("ShaderNodeBsdfPrincipled")
        surface.inputs["Roughness"].default_value = 1.0
        surface.inputs["Specular IOR Level"].default_value = 0.0
        image = next((node for node in nodes if node.type == "TEX_IMAGE"), None)
        links = material.node_tree.links
        if image:
            links.new(image.outputs["Color"], surface.inputs["Base Color"])
            if material.surface_render_method == "BLENDED":
                links.new(image.outputs["Alpha"], surface.inputs["Alpha"])
        else:
            surface.inputs["Base Color"].default_value = emission.inputs["Color"].default_value
        output = next(node for node in nodes if node.type == "OUTPUT_MATERIAL")
        links.new(surface.outputs["BSDF"], output.inputs["Surface"])
    bpy.ops.wm.usd_export(
        filepath=str(destination), export_animation=False, export_lights=False, export_cameras=False,
        export_custom_properties=False, convert_orientation=True, export_global_forward_selection="NEGATIVE_Z",
        export_global_up_selection="Y", meters_per_unit=1.0, relative_paths=True, usdz_downscale_size="1024",
    )


def marsh_edge(x, y):
    distance = min(x + 25, 15 - x, 25 - abs(y))
    return 0.81 * smoothstep((5 - distance) / 5)


def basin_entrance(x, y):
    # Leave all authored slot contacts intact. The entrance submerges into the preceding water.
    reach = 7 + 0.7 * math.sin(x * 0.32)
    return 0.82 * smoothstep((reach - y) / reach)


def prepare(output):
    opening.prepare(output)
    manifest = output / "manifest.json"
    records = json.loads(manifest.read_bytes())
    for name, source in {
        "ft_goose_linear_turbine": ART / "STR-001/v001/STR-001_Main_Turbine.glb",
        "ft_goose_linear_marsh": ART / "ENV-016/v001/ENV-016_ProtectedMarsh.glb",
        "ft_goose_linear_ridge": ART / "ENV-009/v001/ENV-009_FarRidge_A.glb",
    }.items():
        destination = output / (name + ".usdz")
        if name.endswith("marsh"):
            with tempfile.TemporaryDirectory(prefix="feathertide-marsh-") as temp:
                original = Path(temp) / "marsh.usdz"
                export_glb(source, original)
                lowered, flattened = adapt_terrain(original, destination, marsh_edge, flatten_marsh=True)
        else:
            export_glb(source, destination)
            lowered, flattened = 0, 0
        records[name] = {
            "source": str(source.relative_to(ROOT)),
            "sourceSHA256": opening.sha(source.read_bytes()),
            "exportSHA256": opening.sha(destination.read_bytes()),
            "verticesLowered": lowered,
            "verticesFlattened": flattened,
        }

    name = "ft_goose_linear_basin"
    destination = output / (name + ".usdz")
    known = json.loads((ROOT / "Assets/Processed/Goose/M10a-chapter-polish/preview-manifest.json").read_bytes())
    original = known["ft_goose_scene_s6"]
    with zipfile.ZipFile(ROOT / "build/M10a/FeatherTide-M10a-Simulator.zip") as package:
        data = package.read("GooseChapterPreview/ft_goose_scene_s6.usdz")
    if opening.sha(data) != original["exportSHA256"]:
        raise RuntimeError("Recorded M10a basin export hash does not match")
    lowered, _ = adapt_terrain(io.BytesIO(data), destination, basin_entrance)
    records[name] = {
        "source": original["source"],
        "m10aSHA256": original["exportSHA256"],
        "exportSHA256": opening.sha(destination.read_bytes()),
        "verticesLowered": lowered,
    }
    river_name = "ft_goose_linear_river"
    river = ART / "MAT-004/v001/textures/ft_goose_mat_water_river_basecolor_alpha.png"
    data = river.read_bytes()
    (output / (river_name + ".png")).write_bytes(data)
    records[river_name] = {
        "source": str(river.relative_to(ROOT)),
        "extension": "png",
        "sourceSHA256": opening.sha(data),
        "exportSHA256": opening.sha(data),
    }
    manifest.write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    prepare(Path(sys.argv[sys.argv.index("--") + 1]).resolve())
