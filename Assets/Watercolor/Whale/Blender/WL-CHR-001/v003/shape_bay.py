"""Build the W0 silhouette from v002 with Blender in background mode."""

import importlib.util
import json
from math import exp
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
STEM = "WL-CHR-001_whale_rig"


def ramp(value, start, end):
    t = max(0, min(1, (value - start) / (end - start)))
    return t * t * (3 - 2 * t)


def reshape(vertex):
    x, y, z = vertex
    side = 1 if x >= 0 else -1
    width = abs(x)
    shoulder = exp(-((y - 1.65) / 1.35) ** 2)
    rostrum = exp(-((y - 3.93) / 0.95) ** 2)
    body = 1 - ramp(width, 1.27, 1.89)
    fin = ramp(width, 1.18, 2.83) * ramp(y, -1.3, 0.2) * (1 - ramp(y, 1.8, 2.8))
    fluke = ramp(width, 0.28, 2.45) * (1 - ramp(y, -4.95, -4.4))
    notch = exp(-(x / 0.52) ** 2 - ((y + 5.63) / 0.48) ** 2)
    return (
        x * (1 + body * (0.06 * shoulder + 0.15 * rostrum))
        + side * (0.40 * fin + 0.47 * fluke),
        y + rostrum * 0.12 - fin * (0.29 + 0.46 * fin) - fluke * 0.30
        + notch * 0.24,
        z + body * (0.10 * shoulder + 0.06 * rostrum) - 0.29 * fin + 0.08 * fluke,
    )


bpy.ops.wm.open_mainfile(filepath=str(HERE.parent / "v002" / f"{STEM}.blend"))
bpy.context.preferences.filepaths.save_version = 0
obj = bpy.data.objects["Whale_LOD0"]
rig = bpy.data.objects["WhaleRig"]
obj.shape_key_add(name="Basis", from_mix=False)
bay = obj.shape_key_add(name="Bay_Silhouette", from_mix=False)
for vertex, target in zip(obj.data.vertices, bay.data, strict=True):
    target.co = reshape(vertex.co)

# Use the original rig checks against the intermediate and full in-game shapes.
generator_path = HERE.parent / "v001" / f"{STEM}_generate.py"
spec = importlib.util.spec_from_file_location("whale_rig", generator_path)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)
surface = generator.validate_surface(obj)
_, _, patches = generator.WhaleSurface().make()
checks = {}
for strength in (0.5, 1.0):
    bay.value = strength
    bpy.context.view_layer.update()
    poses = generator.validate_poses(obj, rig, patches)
    checks[str(strength)] = {
        "pose_count": len(poses),
        "minimum_triangle_area_ratio": min(p["minimum_triangle_area_ratio"] for p in poses.values()),
        "self_intersections": sum(p["self_intersections_non_neighbor_triangle_pairs"] for p in poses.values()),
    }
(HERE / "qa.json").write_text(json.dumps({"surface": surface, "morph": checks}, indent=2) + "\n")

bay.value = 0
bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.wm.save_as_mainfile(filepath=str(HERE / f"{STEM}.blend"), compress=True)
bpy.ops.export_scene.gltf(
    filepath=str(HERE / f"{STEM}.glb"),
    export_format="GLB",
    use_selection=True,
    use_active_scene=True,
    export_image_format="JPEG",
    export_jpeg_quality=89,
    export_yup=True,
    export_morph=True,
    export_morph_normal=True,
    export_animations=False,
)
