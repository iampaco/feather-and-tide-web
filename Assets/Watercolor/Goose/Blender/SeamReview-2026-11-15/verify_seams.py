"""Reimport shipped GLBs and test the common dry gate in the assembled coordinate system."""

from argparse import ArgumentParser
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


HERE = Path(__file__).resolve().parent
TOLERANCE = 3e-5
LATERAL = [-11.947 + 23.894 * index / 96 for index in range(97)]
DEPTH = (0.002, 0.043, 0.31, 0.79, 1.43, 1.99)


def load_json(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def placement(contract):
    items = list(contract["layout"].items())
    world_offset = Vector((0.0, 0.0, 0.0))
    result = {}
    for asset, record in items:
        entry = Vector(record["entry"])
        translation = world_offset - entry
        exit_point = record.get("exit")
        result[asset] = {"translation": list(translation), "entry": list(entry + translation)}
        if exit_point:
            world_offset = Vector(exit_point) + translation
            result[asset]["exit"] = list(world_offset)
    return result


def import_objects(path, translation):
    before = set(bpy.context.scene.objects)
    result = bpy.ops.import_scene.gltf(filepath=str(path))
    if result != {"FINISHED"}:
        raise RuntimeError(f"GLB import failed: {path}")
    objects = [obj for obj in bpy.context.scene.objects if obj not in before]
    # The glTF importer adds viewport widgets for skinning bones. They are Blender
    # display geometry, so keep them out of world placement and mesh probes.
    bone_widgets = {bone.custom_shape for obj in objects if obj.type == "ARMATURE"
                    for bone in obj.pose.bones if bone.custom_shape is not None}
    objects = [obj for obj in objects if obj not in bone_widgets]
    roots = [obj for obj in objects if obj.parent is None]
    for obj in roots:
        obj.location += translation
    bpy.context.view_layer.update()
    return objects


def find_named(objects, name):
    return next((obj for obj in objects if obj.name == name or obj.name.rsplit(".", 1)[0] == name), None)


def clip(points, axis, bound, sign):
    """Clip a polygon against an axis-aligned plane."""
    clipped = []
    for first, last in zip(points, points[1:] + points[:1]):
        inside_a = sign * (first[axis] - bound) >= 0
        inside_b = sign * (last[axis] - bound) >= 0
        if inside_a:
            clipped.append(first)
        if inside_a != inside_b:
            alpha = (bound - first[axis]) / (last[axis] - first[axis])
            clipped.append(first.lerp(last, alpha))
    return clipped


def gate_interval(points, y):
    """Return the X interval formed by intersecting a flat face with its gate plane."""
    values = []
    for first, last in zip(points, points[1:] + points[:1]):
        if abs(first.y - y) <= TOLERANCE:
            values.append(first.x)
        if (first.y - y) * (last.y - y) < 0:
            alpha = (y - first.y) / (last.y - first.y)
            values.append(first.x + (last.x - first.x) * alpha)
    return (min(values), max(values)) if len(values) >= 2 else None


def uncovered_width(intervals, start, end):
    covered = start
    gaps = []
    for low, high in sorted(intervals):
        if low > covered + TOLERANCE:
            gaps.append([covered, low])
        covered = max(covered, high)
    if end > covered + TOLERANCE:
        gaps.append([covered, end])
    return gaps


def geometry(objects, center, side):
    """Use the evaluated triangle mesh, with no extra backing surface in the probe."""
    vertices, triangles, names = [], [], []
    water_crossing = set()
    flat_crossing = set()
    flat_extents, intervals = [], []
    dg = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        if obj.type != "MESH":
            continue
        item = obj.evaluated_get(dg)
        matrix = item.matrix_world
        bounds = [matrix @ Vector(corner) for corner in item.bound_box]
        if (max(point.y for point in bounds) < center.y - 2.01
                or min(point.y for point in bounds) > center.y + 2.01
                or max(point.x for point in bounds) < center.x - 12
                or min(point.x for point in bounds) > center.x + 12
                or min(point.z for point in bounds) > 8):
            continue
        mesh = item.to_mesh()
        try:
            coords = [matrix @ vertex.co for vertex in mesh.vertices]
            mesh.calc_loop_triangles()
            for tri in mesh.loop_triangles:
                points = [coords[i] for i in tri.vertices]
                y0, y1 = min(p.y for p in points), max(p.y for p in points)
                if (y1 < center.y - 2.005 or y0 > center.y + 2.005
                        or max(p.x for p in points) < center.x - 12
                        or min(p.x for p in points) > center.x + 12):
                    continue
                slot = item.material_slots[tri.material_index] if tri.material_index < len(item.material_slots) else None
                material = slot.material.name if slot is not None and slot.material else ""
                if y0 <= center.y + TOLERANCE and y1 >= center.y - TOLERANCE:
                    clipped = clip(points, 0, center.x - 12, 1)
                    clipped = clip(clipped, 0, center.x + 12, -1)
                    if clipped:
                        coords_y = [p.y - center.y for p in clipped]
                        if ("water" in f"{obj.name} {material}".casefold()
                                and min(coords_y) <= TOLERANCE and max(coords_y) >= -TOLERANCE):
                            water_crossing.add(obj.name)
                        if all(abs(p.z - center.z) <= TOLERANCE for p in clipped):
                            extent = min(side * value for value in coords_y)
                            flat_extents.append(extent)
                            interval = gate_interval(clipped, center.y)
                            if interval:
                                intervals.append(interval)
                            if extent < -TOLERANCE:
                                flat_crossing.add(obj.name)
                triangles.append(tuple(range(len(vertices), len(vertices) + 3)))
                vertices.extend(points)
                names.append((obj.name, material))
        finally:
            item.to_mesh_clear()
    if not triangles:
        raise RuntimeError(f"No evaluated geometry at gate {list(center)}")
    bvh = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
    return (bvh, names, sorted(water_crossing), sorted(flat_crossing), min(flat_extents, default=None),
            uncovered_width(intervals, center.x - 12, center.x + 12))


def measure(objects, anchor, side):
    bvh, names, wet, crosses, edge, gaps = geometry(objects, anchor, side)
    samples, problems = [], []
    contributors = set()
    for offset in DEPTH:
        for x in LATERAL:
            point, normal, index, _ = bvh.ray_cast(
                (anchor.x + x, anchor.y + side * offset, anchor.z + 7.5),
                (0, 0, -1), 8.5,
            )
            if point is None or abs(point.z - anchor.z) > TOLERANCE or normal.z < 0.9999:
                problems.append({"x": x, "inward": offset,
                                 "hit": list(point) if point is not None else None,
                                 "object": names[index][0] if index is not None else None})
            if point is not None:
                samples.append(point.z - anchor.z)
                contributors.add(names[index])
    return {
        "status": "pass" if not (problems or wet or crosses or gaps or edge is None or abs(edge) > TOLERANCE) else "fail",
        "ray_count": len(DEPTH) * len(LATERAL),
        "flat_edge_signed_distance_inward_BU": edge,
        "max_abs_ground_error_BU": max(map(abs, samples), default=None),
        "visual_terrain_object_and_material": sorted(contributors),
        "bad_rays": problems,
        "uncovered_ground_intervals_x_BU": gaps,
        "water_at_gate": wet,
        "ground_protrudes_through_gate": crosses,
    }


def neighboring_side_intrusions(objects, anchor, own_side):
    """Find visual mesh faces placed 0.01–12 BU into the neighboring center corridor."""
    outside = sorted((anchor.y - own_side * 0.01, anchor.y - own_side * 12))
    limits = [(anchor.x - 12, anchor.x + 12), tuple(outside), (anchor.z - 1, anchor.z + 8)]
    graph = bpy.context.evaluated_depsgraph_get()
    intrusions = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(graph)
        matrix = evaluated.matrix_world
        bounds = [matrix @ Vector(corner) for corner in evaluated.bound_box]
        if any(max(p[axis] for p in bounds) < low or min(p[axis] for p in bounds) > high
               for axis, (low, high) in enumerate(limits)):
            continue
        mesh = evaluated.to_mesh()
        try:
            coords = [matrix @ vertex.co for vertex in mesh.vertices]
            mesh.calc_loop_triangles()
            for triangle in mesh.loop_triangles:
                polygon = [coords[index] for index in triangle.vertices]
                for axis, (low, high) in enumerate(limits):
                    polygon = clip(clip(polygon, axis, low, 1), axis, high, -1)
                    if len(polygon) < 3:
                        break
                if len(polygon) < 3:
                    continue
                area2 = sum((polygon[i] - polygon[0]).cross(polygon[i + 1] - polygon[0]).length
                            for i in range(1, len(polygon) - 1))
                if area2 > 1e-6:
                    intrusions.append({"object": obj.name, "example_face_BU": [list(p) for p in polygon]})
                    break
        finally:
            evaluated.to_mesh_clear()
    return intrusions


def check_anchor(objects, name, expected):
    obj = find_named(objects, name)
    if obj is None:
        return {"node": name, "status": "fail", "reason": "node missing after GLB import"}
    matrix = obj.matrix_world
    heading = (matrix.to_3x3() @ Vector((0, 1, 0))).normalized()
    offset = (matrix.translation - expected).length
    heading_error = (heading - Vector((0, 1, 0))).length
    return {
        "node": obj.name,
        "position_BU": list(matrix.translation),
        "heading_blender": list(heading),
        "position_error_BU": offset,
        "heading_error": heading_error,
        "status": "pass" if max(offset, heading_error) <= TOLERANCE else "fail",
    }


def add_camera(name, location, target, ortho=None):
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    data.clip_start = 0.006
    data.clip_end = 350
    if ortho is None:
        data.sensor_fit = "VERTICAL"
        data.sensor_height = 24
        data.lens = 12 / math.tan(math.radians(50) / 2)
    else:
        data.type = "ORTHO"
        data.ortho_scale = ortho
        obj.rotation_euler = (0, 0, 0)
    return obj


def lighting(scene):
    scene.render.engine = "CYCLES"
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 2
    scene.cycles.device = "CPU"
    scene.cycles.samples = 6
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 5
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.world = bpy.data.worlds.new("Overcast")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.59, 0.68, 0.71, 1)
    background.inputs["Strength"].default_value = 0.65
    key = bpy.data.lights.new("Daylight", "SUN")
    key.energy, key.angle = 1.5, 0.34
    obj = bpy.data.objects.new(key.name, key)
    scene.collection.objects.link(obj)
    obj.rotation_euler = Vector((0.66, 0.43, -1)).to_track_quat("-Z", "Y").to_euler()


def render(scene, camera, path, width, height):
    scene.camera = camera
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def proof_images(repo, output, anchor, title, extended):
    scene = bpy.context.scene
    lighting(scene)
    bird_path = (repo / "Assets/Watercolor/Goose/Blender/CHR-001/v001/CHR-001_goose_rig.glb")
    birds = import_objects(bird_path, anchor + Vector((0, 0, 0.288)))
    rig = next(obj for obj in birds if obj.type == "ARMATURE")
    rig_z = rig.location.z
    follow = add_camera("Fixed Swift follow", anchor, anchor + Vector((0, 1, 0)))
    poses = (("before", -3), ("gate", 0), ("after", +3)) if extended else (("gate", 0),)
    for name, offset in poses:
        rig.location = (anchor.x, anchor.y + offset, rig_z)
        pos = anchor + Vector((0, offset, 0))
        back = 180 * 0.036 * math.cos(0.48)
        height = 180 * 0.036 * math.sin(0.48)
        follow.location = pos + Vector((0, -back, height))
        follow.rotation_euler = (pos + Vector((0, 0, 6 * .036)) - follow.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        render(scene, follow, output / f"{title}_{name}.png", 852, 393)
    rig.location = (anchor.x, anchor.y, rig_z)
    top = add_camera("Technical gate plan", anchor + Vector((0, 0, 85)), anchor, ortho=30)
    render(scene, top, output / f"{title}_top.png", 780, 650)


def run(repo, contract_path, output, pair_start, probe_only):
    contract = load_json(contract_path)
    world = placement(contract)
    base = repo / "Assets/Watercolor/Goose/Blender"
    pairs = list(zip(list(world), list(world)[1:]))
    reports = []
    output.mkdir(parents=True, exist_ok=True)
    for index, (left, right) in enumerate(pairs):
        if pair_start is not None and index != pair_start:
            continue
        bpy.ops.wm.read_factory_settings(use_empty=True)
        seam = Vector(world[left]["exit"])
        assert (seam - Vector(world[right]["entry"])).length < 1e-6
        result = {}
        for asset, key, side in ((left, "exit", -1), (right, "entry", +1)):
            specification = contract["layout"][asset]
            paths = list((base / asset / "v001").glob("*.glb"))
            path = base / asset / "v001" / specification["glb"] if "glb" in specification else None
            if path is None and len(paths) == 1:
                path = paths[0]
            if path is None:
                raise RuntimeError(f"Declare the runtime assembly GLB for {asset}: {paths}")
            imported = import_objects(path, Vector(world[asset]["translation"]))
            exported_node = specification.get(f"{key}_node")
            point_measure = check_anchor(imported, exported_node, seam) if exported_node else None
            result[asset] = {
                "GLB": str(path.relative_to(repo)), "GLB_sha256": digest(path),
                "asset_local_gate_BU": specification[key],
                "imported_anchor": point_measure,
                "anchor_source": specification.get("anchor_source") if exported_node is None else "GLB named node",
                "gate_probe": measure(imported, seam, side),
                "visual_meshes_inside_neighbor_corridor": neighboring_side_intrusions(imported, seam, side),
            }
        title = f"{left[-2:]}_{right[-2:]}"
        clean = all(row["gate_probe"]["status"] == "pass" and not row["visual_meshes_inside_neighbor_corridor"]
                    and (row["imported_anchor"] is None or row["imported_anchor"]["status"] == "pass")
                    for row in result.values())
        reports.append({"pair": title, "status": "pass" if clean else "fail",
                        "world_seam_BU": list(seam), "sides": result})
        if not probe_only:
            proof_images(repo, output, seam, title, index in (1, 2, 5))
    report = {
        "contract": contract,
        "world_placements_BU": world,
        "method": "Independent Blender GLB reimports, evaluated triangles, separate side BVHs, dry gate probes and crossing-mesh checks",
        "neighbor_intrusion_search": {"width_BU": 24, "depth_BU": [0.01, 12], "z_BU": [-1, 8]},
        "height_tolerance_BU": TOLERANCE,
        "lateral_probe_offsets_BU": LATERAL,
        "inward_probe_offsets_BU": DEPTH,
        "pairs": reports,
        "status": "pass" if reports and all(row["status"] == "pass" for row in reports) else "fail",
    }
    outfile = "seam_qa.json" if pair_start is None else f"pair_{pair_start}_qa.json"
    (output / outfile).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(reports)} checked: {[(item['pair'], item['status']) for item in reports]}")
    if report["status"] != "pass":
        raise AssertionError(f"One or more seam checks failed. See {output / outfile}.")


if __name__ == "__main__":
    args = ArgumentParser()
    args.add_argument("--repo", required=True, type=Path)
    args.add_argument("--contract", default=HERE / "seam_contract.json", type=Path)
    args.add_argument("--out", required=True, type=Path)
    args.add_argument("--pair-start", type=int)
    args.add_argument("--probe-only", action="store_true")
    opts = args.parse_args(sys.argv[sys.argv.index("--") + 1:])
    run(opts.repo.resolve(), opts.contract, opts.out, opts.pair_start, opts.probe_only)
