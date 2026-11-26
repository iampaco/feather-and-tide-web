"""Refine the gameplay silhouette using the validated v003 rig and UVs.

Run with Blender 5.2.2 in background mode:
  blender -b -t 4 --python Assets/Watercolor/Whale/Blender/WL-CHR-001/v004/shape_whale.py
"""

import importlib.util
import json
from math import exp
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
STEM = "WL-CHR-001_whale_rig"


def ramp(value, start, end):
    t = max(0.0, min(1.0, (value - start) / (end - start)))
    return t * t * (3.0 - 2.0 * t)


def refined(point):
    x, y, z = point
    width = abs(x)
    side = -1.0 if x < 0 else 1.0
    body = 1.0 - ramp(width, 1.20, 1.76)
    crown = exp(-((y - 3.55) / 1.05) ** 2) * body
    stock = exp(-((y + 3.71) / 0.73) ** 2)
    fin = ramp(width, 1.34, 2.72) * ramp(y, -1.38, 0.24)
    fin *= 1.0 - ramp(y, 1.78, 2.66)
    fluke = ramp(width, 0.39, 2.50) * (1.0 - ramp(y, -4.98, -4.42))
    notch = exp(-(x / 0.68) ** 2 - ((y + 5.74) / 0.53) ** 2)
    return (
        x * (1.0 + 0.085 * crown - 0.095 * stock)
        + side * (0.27 * fin + 0.28 * fluke),
        y - 0.26 * fin + 0.25 * notch,
        z + 0.08 * crown + 0.12 * fin - 0.05 * fluke,
    )


bpy.ops.wm.open_mainfile(filepath=str(HERE.parent / "v003" / f"{STEM}.blend"))
bpy.context.preferences.filepaths.save_version = 0
whale = bpy.data.objects["Whale_LOD0"]
rig = bpy.data.objects["WhaleRig"]
keys = whale.data.shape_keys.key_blocks
# Apply the same anatomical refinement to both shapes to keep the blend continuous.
for key in (keys["Basis"], keys["Bay_Silhouette"]):
    for vertex in key.data:
        vertex.co = refined(vertex.co)
for vertex, rest in zip(whale.data.vertices, keys["Basis"].data, strict=True):
    vertex.co = rest.co
whale.data.update()

reference = HERE.parent / "v001" / f"{STEM}_generate.py"
spec = importlib.util.spec_from_file_location("whale_reference", reference)
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
surface = validation.validate_surface(whale)
_, _, patches = validation.WhaleSurface().make()
posed = {}
for strength in (0.0, 0.5, 1.0):
    keys["Bay_Silhouette"].value = strength
    bpy.context.view_layer.update()
    poses = validation.validate_poses(whale, rig, patches)
    posed[str(strength)] = {
        "pose_count": len(poses),
        "minimum_triangle_area_ratio": min(
            sample["minimum_triangle_area_ratio"] for sample in poses.values()
        ),
        "self_intersections": sum(
            sample["self_intersections_non_neighbor_triangle_pairs"]
            for sample in poses.values()
        ),
    }
(HERE / "qa.json").write_text(
    json.dumps({"surface": surface, "morph": posed}, indent=2) + "\n"
)

keys["Bay_Silhouette"].value = 0.0
bpy.ops.object.select_all(action="DESELECT")
whale.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = whale
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
