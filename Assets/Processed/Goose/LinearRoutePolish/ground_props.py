"""Assemble registered rock and grass models against the actual single-route terrain."""
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import basin
import landscape
import opening
from ground_detail import MODELS, placements


def imported_models():
    models = {}
    for key, relative in MODELS.items():
        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.import_scene.gltf(filepath=str(landscape.ART / relative))
        bpy.context.view_layer.update()
        parts = [(obj.data, obj.matrix_world.copy()) for obj in bpy.context.selected_objects if obj.type == "MESH"]
        if not parts:
            raise RuntimeError(f"No geometry imported from {relative}")
        models[key] = parts
    return models


def assemble_section(name, items, sample_height, models):
    collection = bpy.context.scene.collection
    objects = []
    for kind, x, y, scale, angle in items:
        # Sink the original ground pivot slightly so the rocks and leaves hug the shore.
        height = float(sample_height(x, y)) - (0.026 if kind.startswith("grass") else 0.052)
        matrix = Matrix.Translation((x, y, height)) @ Matrix.Rotation(angle, 4, "Z") @ Matrix.Scale(scale, 4)
        for data, local in models[kind]:
            obj = bpy.data.objects.new(kind, data)
            collection.objects.link(obj)
            obj.matrix_world = matrix @ local
            objects.append(obj)
    if not objects:
        raise RuntimeError(f"No shoreline detail landed on {name}")
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    merged = objects[0]
    merged.data = merged.data.copy()
    bpy.context.view_layer.objects.active = merged
    bpy.ops.object.join()
    merged.data.transform(merged.matrix_world)
    merged.matrix_world = Matrix.Identity(4)
    merged.name = f"GroundDetail_{name}"
    merged.data.name = merged.name
    merged.data.calc_loop_triangles()
    print(f"{name}: {len(items)} placements, {len(merged.data.loop_triangles)} triangles", flush=True)
    return merged


def export(destination):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    models = imported_models()
    field = basin.Basin()

    def basin_height(x, y):
        local = y - basin.BASIN_ENTRY
        return field.elevations(x, local, field.distance(x, local))[0]

    sections = [
        assemble_section("Opening", placements("Opening", opening.detail_allowed), opening.height, models),
        assemble_section("River", placements("River", landscape.detail_allowed),
                         lambda x, y: landscape.elevation(x, y, outlet=True), models),
        assemble_section("Basin", placements("Basin", field.detail_allowed), basin_height, models),
    ]
    bpy.ops.object.select_all(action="DESELECT")
    for item in sections:
        item.select_set(True)
    result = bpy.ops.wm.usd_export(
        filepath=str(destination), selected_objects_only=True, export_animation=False, export_lights=False,
        export_cameras=False, export_custom_properties=False, convert_orientation=True,
        export_global_forward_selection="NEGATIVE_Z", export_global_up_selection="Y", meters_per_unit=1.0,
        relative_paths=True, usdz_downscale_size="1024",
    )
    if "FINISHED" not in result or not destination.is_file():
        raise RuntimeError(f"Could not write {destination}")


if __name__ == "__main__":
    export(Path(sys.argv[sys.argv.index("--") + 1]).resolve())
