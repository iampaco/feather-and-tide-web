"""Run with Blender in background mode: blender -b -t 4 --python paint_whale.py."""
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
STEM = "WL-CHR-001_whale_rig"
SIZE = 512


def bell(value, center, width):
    return np.exp(-((value - center) / width) ** 2)


def reshape(mesh):
    for vertex in mesh.vertices:
        x, y, z = vertex.co
        # Lift the crown and widen the forward jaw. Preserve the original graft topology.
        crown = bell(y, 3.6, 1.43)
        vertex.co.z += float(crown * (0.11 + 0.16 * max(0, z)))
        vertex.co.x *= float(1 + crown * 0.09)
        if y > 4.4:
            vertex.co.y -= (y - 4.4) ** 2 * 0.22
        if y > -0.4 and abs(x) > 1.37:
            flank = min(1, (abs(x) - 1.37) / 1.5)
            vertex.co.x += float(np.sign(x) * 0.29 * flank)
            vertex.co.z += 0.14 * flank
        if y < -4.38:
            fluke = min(1, abs(x) / 2.28)
            vertex.co.x *= 1 + fluke * 0.14
            vertex.co.y -= 0.27 * fluke
            vertex.co.y += float(0.26 * bell(x, 0, 0.40) * bell(y, -5.16, 0.28))
    mesh.update()


def pigment(xyz, uv, grain):
    x, y, z = xyz.T
    _, v = uv.T
    pectoral = (v >= 0.645) & (v <= 0.785)
    fluke = v > 0.8
    cloud = 0.5 + 0.25 * np.sin(3.6 * x + 1.84 * y + np.sin(3 * z)) + 0.25 * np.cos(y * 3.29 - 6 * z)
    molted = np.tanh(2 * (np.sin(11 * x + 3.7 * y) * np.cos(5.8 * y - 9 * z)))
    belly = np.clip((-z - 0.17 + cloud * 0.18) * 2.36, 0, 1)
    without_fins = ~(pectoral | fluke)
    # Match the hull pigment along the grafts before the fin edges take their own colour.
    fin_wash = pectoral * np.clip((v - 0.65) / 0.054, 0, 1)
    tail_wash = fluke * np.clip((v - 0.81) / 0.047, 0, 1)
    belly *= (1 - fin_wash * 0.74) * (1 - tail_wash)
    tail_ink = tail_wash * np.clip(abs(x) / 2.6, 0, 1)
    fin_edge = fin_wash * np.clip((abs(x) - 1.32) / 1.85, 0, 1)
    dorsal = bell(x, -0.24, 0.82) * np.clip(z + 0.11, 0, 1)
    color = (
        np.array([0.364, 0.489, 0.567])
        + dorsal[:, None] * np.array([0.18, 0.22, 0.22])
        + belly[:, None] * np.array([0.34, 0.31, 0.27])
        + fin_edge[:, None] * np.array([0.20, 0.22, 0.22])
        - tail_ink[:, None] * np.array([0.13, 0.16, 0.16])
        + (cloud[:, None] - 0.5) * np.array([0.132, 0.117, 0.100])
        + (molted * 0.012 + grain * 0.011)[:, None]
    )
    # Small marks live in the baked paint, with no separate geometry or skin assignment.
    eye = bell(y, 3.24, 0.110) * bell(z, 0.08, 0.089) * (abs(x) > 0.88) * without_fins
    mouth = bell(z, -0.17 - 0.135 * (4.68 - y), 0.034)
    mouth *= np.clip((y - 2.96) * 3, 0, 1) * np.clip((4.94 - y) * 3, 0, 1) * without_fins
    slit = bell(x, 0.015, 0.092) * bell(y, 3.05, 0.22) * (z > 0.7)
    return np.clip(color * (1 - 0.77 * eye - 0.30 * mouth - 0.54 * slit)[:, None], 0, 1)


def bake(mesh):
    uv = mesh.uv_layers.active.data
    mesh.calc_loop_triangles()
    rgb = np.zeros((SIZE, SIZE, 4), dtype=np.float32)
    known = np.zeros((SIZE, SIZE), dtype=bool)
    grain = np.random.default_rng(183).normal(0, 1, (SIZE, SIZE))
    for tri in mesh.loop_triangles:
        coords = np.array([tuple(uv[loop].uv) for loop in tri.loops])
        xyz = np.array([tuple(mesh.vertices[i].co) for i in tri.vertices])
        low = np.maximum(0, np.floor(coords.min(axis=0) * SIZE)).astype(int)
        high = np.minimum(SIZE, np.ceil(coords.max(axis=0) * SIZE)).astype(int)
        rows, cols = np.mgrid[low[1]:high[1], low[0]:high[0]]
        samples = (np.column_stack((cols.ravel(), rows.ravel())) + 0.5) / SIZE
        basis = (coords[1:] - coords[0]).T
        if abs(np.linalg.det(basis)) < 1e-10:
            continue
        tail = (samples - coords[0]) @ np.linalg.inv(basis).T
        weights = np.column_stack((1 - tail.sum(axis=1), tail))
        inside = (weights >= -1e-6).all(axis=1)
        rows, cols = rows.ravel()[inside], cols.ravel()[inside]
        rgb[rows, cols, :3] = pigment(weights[inside] @ xyz, samples[inside], grain[rows, cols])
        known[rows, cols] = True

    # Dilate the islands into the gutters so bilinear and mip sampling retain their paint.
    for _ in range(8):
        added = known.copy()
        for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
            frontier = np.roll(known, shift, axis) & ~added
            rgb[frontier] = np.roll(rgb, shift, axis)[frontier]
            added |= frontier
        known = added
    rgb[~known, :3] = (0.36, 0.49, 0.57)
    rgb[:, :, 3] = 1
    image = bpy.data.images.new("Whale watercolour · sRGB", SIZE, SIZE, alpha=False)
    image.pixels.foreach_set(rgb.ravel())
    image.filepath_raw = str(HERE / "whale-pigment.png")
    image.file_format = "PNG"
    image.save()
    image.pack()
    return image


bpy.ops.wm.open_mainfile(filepath=str(HERE.parent / "v001" / f"{STEM}.blend"))
bpy.context.preferences.filepaths.save_version = 0
obj = bpy.data.objects["Whale_LOD0"]
rig = bpy.data.objects["WhaleRig"]
reshape(obj.data)
image = bake(obj.data)
material = obj.data.materials[0]
material.name = "WL-CHR-001 · Watercolour"
nodes = material.node_tree.nodes
shader = nodes.get("Principled BSDF")
shader.inputs["Roughness"].default_value = 0.87
paint = nodes.new("ShaderNodeTexImage")
paint.image = image
paint.location = (-320, 280)
material.node_tree.links.new(paint.outputs["Color"], shader.inputs["Base Color"])
rig["runtime_animation"] = "In-place pose from swim speed, heading rate and dive transition in whale-swim.ts."

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
    export_animations=False,
)
