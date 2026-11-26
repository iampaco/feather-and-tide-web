"""Build a portable FormationGuide dab and stage a separate moving-flock review."""

import argparse
import math
import struct
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import zlib

import bpy
import numpy as np
from mathutils import Vector


VARIANT = "FormationGuide"
SOURCE_BASENAME = "FX-008_FormationGuide.blend"
GLB_BASENAME = "FX-008_FormationGuide.glb"
TEXTURE = "ft_goose_fx_formation_guide_basecolor_alpha.png"
VIDEO_BASENAME = "preview_fixed_rear_formation.mov"
HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
DEPENDENCY_BLEND = LIBRARY / "ANM-006/v001/ANM-006_formation_blend.blend"
REAR = "Gameplay | fixed rear"
TOP = "Review | formation overhead"
REVIEW_NAME = "FX-008 | fixed rear and V trace"
CONTROL_NAME = "Formation Guide | Review Controls"
GAME = (852, 393)
FPS = 24
CLIP_FPS = 12
FINAL_FRAME = 192
GAME_PER_BU = 27.5 / .9900
BASE_LENGTH = .64
BASE_WIDTH = .155
PHASE_OFFSETS = [0, 9, 20, 5, 31, 15, 37, 13, 45, 24, 43, 29]
MARKERS = {
    1: "Loose", 13: "Begin", 37: "Halfway", 61: "Formed",
    73: "Release", 97: "Released", 103: "Form again",
    151: "Formed again", 163: "Sharp turn", 167: "Broken", 192: "Loose after break",
}
DEFAULTS = {
    "form_seconds": 2., "release_seconds": 1., "break_fade_seconds": .15,
    "peak_opacity": 1., "ground_clearance_BU": .025,
    "vertical_offset_BU": -.12, "outside_offset_BU": .91,
    "dash_fill_ratio": .67, "width_BU": BASE_WIDTH,
}
LOOSE = [(-34, -10), (34, -11), (-41, -25), (41, -27), (-48, -42),
         (47, -44), (-54, -56), (53, -60), (-60, -70), (59, -74), (-66, -83)]
COMPACT_V = [(((-1) ** (i + 1)) * (26 + 6 * (i // 2)), -13 * (i // 2 + 1)) for i in range(11)]


def smootherstep(unit):
    unit = min(1., max(0., unit))
    return unit**3 * (10 + unit * (-15 + 6 * unit))


def guide_weight(frame, control=DEFAULTS):
    if frame < 73:
        return smootherstep((frame - 13) / (FPS * control["form_seconds"]))
    if frame < 103:
        return 1 - smootherstep((frame - 73) / (FPS * control["release_seconds"]))
    if frame < 163:
        return smootherstep((frame - 103) / (FPS * control["form_seconds"]))
    return 1 - smootherstep((frame - 163) / (FPS * control["break_fade_seconds"]))


def shape_weight(frame, control=DEFAULTS):
    # At a sharp turn the birds drift apart independently of the brief trace fade.
    return guide_weight(frame, control) if frame < 163 else 1 - smootherstep((frame - 163) / 19)


def png_chunk(tag, payload):
    return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload))


def write_texture(path):
    """Use a feathered watercolor wash with a fully transparent border."""
    w, h = 256, 64
    u = (np.arange(w)[None, :] + .5) / w
    v = (np.arange(h)[:, None] + .5) / h
    center = .5 + .063 * np.sin((u - .13) * math.tau)
    y = (v - center) / (.245 + .095 * u)
    side = np.clip((1.22 - abs(y)) / .48, 0, 1)
    length = (np.sin(math.pi * u) ** 1.22) * (.69 + .31 * u)
    grain = .96 + .025 * np.sin(93 * u + 28 * v) + .018 * np.sin(131 * u - 92 * v)
    alpha = .46 * length * side**2 * np.exp(-.59 * y**2) * grain
    alpha[[0, -1], :] = 0
    alpha[:, [0, -1]] = 0
    base = np.array([236, 216, 172])
    rgb = base[None, None, :] + (grain[:, :, None] - .95) * 60
    rgba = np.concatenate((rgb, 255 * alpha[:, :, None]), axis=2).round().astype(np.uint8)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">2I5B", w, h, 8, 6, 0, 0, 0))
        + png_chunk(b"sRGB", b"\x00")
        + png_chunk(b"IDAT", zlib.compress(b"".join(b"\x00" + row.tobytes() for row in rgba[::-1]), 8))
        + png_chunk(b"IEND", b"")
    )
    return {"px": [w, h], "max_alpha_8bit": int(rgba[:, :, 3].max())}


def make_dash(collection):
    """A single brushstroke fits any eligible gap between consecutive slot anchors."""
    vertices, uvs = [], []
    for row in range(6):
        u = row / 5
        tip = .76 + .24 * math.sin(math.pi * u)
        center = BASE_WIDTH * .12 * math.sin(math.pi * u * 1.16)
        for side in (-1, 1):
            vertices.append((center + side * BASE_WIDTH * tip / 2, (u - .5) * BASE_LENGTH, 0))
            uvs.append((u, (1 + side) / 2))
    faces = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(5)]
    mesh = bpy.data.meshes.new("FormationGuide | curved ribbon")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv = mesh.uv_layers.new(name="Brush UV")
    for loop in mesh.loops:
        uv.data[loop.index].uv = uvs[loop.vertex_index]
    dash = bpy.data.objects.new(VARIANT, mesh)
    collection.objects.link(dash)
    dash["variant"] = VARIANT
    dash["long_axis"] = "Blender +Y / glTF -Z"
    dash["rest_length_BU"] = BASE_LENGTH
    dash["max_width_BU"] = BASE_WIDTH
    dash["renderer_role"] = "Instantiate per consecutive slot gap, client supplies pose and opacity."
    dash.visible_shadow = False
    dash.visible_diffuse = False
    dash.visible_glossy = False
    dash.visible_transmission = False
    return dash


def material(name, image=None, review=False):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_backface_culling = False
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    surface = nodes.new("ShaderNodeOutputMaterial")
    feather = nodes.new("ShaderNodeMixShader")
    feather.location = (-20, 50)
    clear = nodes.new("ShaderNodeBsdfTransparent")
    clear.location = (-300, -20)
    links.new(clear.outputs["BSDF"], feather.inputs[1])
    if image is None:
        gray = nodes.new("ShaderNodeRGB")
        gray.outputs[0].default_value = (.66, .67, .66, 1)
        links.new(gray.outputs[0], feather.inputs[2])
        feather.inputs[0].default_value = 1
    else:
        ink = nodes.new("ShaderNodeTexImage")
        ink.image, ink.extension = image, "EXTEND"
        ink.location = (-630, 210)
        links.new(ink.outputs["Color"], feather.inputs[2])
        if review:
            gain = nodes.new("ShaderNodeMath")
            gain.operation, gain.name, gain.label = "MULTIPLY", "Review opacity", "Review opacity"
            gain.location = (-310, 220)
            gain.inputs[1].default_value = 1.
            links.new(ink.outputs["Alpha"], gain.inputs[0])
            links.new(gain.outputs[0], feather.inputs[0])
        else:
            links.new(ink.outputs["Alpha"], feather.inputs[0])
    links.new(feather.outputs[0], surface.inputs["Surface"])
    surface.location = (220, 50)
    return mat


def local_offset(index, frame, control):
    if index == 0:
        return Vector((0, 0, 0))
    t = shape_weight(frame, control)
    x, y = LOOSE[index - 1]
    bx, by = COMPACT_V[index - 1]
    return Vector(((x * (1 - t) + bx * t) / GAME_PER_BU,
                   (y * (1 - t) + by * t) / GAME_PER_BU, -2. / GAME_PER_BU))


def gap_pose(a, b, side, ground, control):
    """Fit one centered paper stroke to the gap, forward toward the leader."""
    line = a - b
    tangent = Vector((line.x, line.y, 0)).normalized()
    midpoint = (a + b) / 2 + Vector((side * control["outside_offset_BU"], 0, 0))
    midpoint.z = max(midpoint.z + control["vertical_offset_BU"], ground + control["ground_clearance_BU"])
    angle = math.atan2(-tangent.x, tangent.y)
    length = max(.05, line.xy.length * control["dash_fill_ratio"])
    return midpoint, angle, (control["width_BU"] / BASE_WIDTH, length / BASE_LENGTH, 1.)


def grouped(scene, name):
    group = bpy.data.collections.new(name)
    scene.collection.children.link(group)
    return group


def linearize(animated_id):
    animation = animated_id.animation_data
    for layer in animation.action.layers:
        for strip in layer.strips:
            for curve in strip.channelbag(animation.action_slot).fcurves:
                for key in curve.keyframe_points:
                    key.interpolation = "LINEAR"


def action_curves(action):
    return action.layers[0].strips[0].channelbag(action.slots[0]).fcurves


def remake_action(rig, source_curves, index, control):
    cruise, formed = source_curves
    rig.animation_data_clear()
    phase = PHASE_OFFSETS[index]
    for frame in range(1, FINAL_FRAME + 1):
        sample = 1 + (2 * (frame - 1) + phase) % 52
        weight = shape_weight(frame, control)
        for (data_path, component), before in cruise.items():
            value = before.evaluate(sample) * (1 - weight) + formed[data_path, component].evaluate(sample) * weight
            rig.path_resolve(data_path)[component] = value
            rig.keyframe_insert(data_path, index=component, frame=frame)
    rig.animation_data.action.name = f"FX review | flight blend {index:02}"
    linearize(rig)


def frame_settings(scene, size, samples=8):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"


def review_stage(scene, dash, guide_gray):
    group = grouped(scene, "FX-008 | review ribbons and controls")
    motion = bpy.data.objects.new("Review flight path", None)
    group.objects.link(motion)
    control = bpy.data.objects.new(CONTROL_NAME, None)
    group.objects.link(control)
    for prop, value in DEFAULTS.items():
        control[prop] = value
        control.id_properties_ui(prop).update(
            min=-3. if prop == "vertical_offset_BU" else 0., max=6.,
            description="Editable review input. Run the script with --rebuild-controls to re-key placement.",
        )
    control["opacity"] = 0.
    control.id_properties_ui("opacity").update(min=0., max=1., description="Preview mix; animated by the review action.")
    scene.name = REVIEW_NAME
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, FINAL_FRAME
    scene.camera = scene.objects[REAR]
    scene.camera.parent = motion
    scene.camera.location = (0, -180 * math.cos(.48) / GAME_PER_BU, (180 * math.sin(.48) - 8) / GAME_PER_BU)
    direction = Vector((0, 0, -2 / GAME_PER_BU)) - scene.camera.location
    scene.camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.objects[TOP].parent = motion

    carriers = [scene.objects[f"Preview carrier | {i:02}"] for i in range(12)]
    for carrier in carriers:
        carrier.animation_data_clear()
        carrier.parent = motion
    for marker in list(scene.timeline_markers):
        scene.timeline_markers.remove(marker)
    for frame, label in MARKERS.items():
        scene.timeline_markers.new(label, frame=frame)

    for side, label, indices in ((-1, "L", [1, 3, 5, 7, 9, 11]), (1, "R", [2, 4, 6, 8, 10])):
        for k, (start, end) in enumerate(zip(indices, indices[1:]), start=1):
            trace = dash.copy()
            trace.name = f"FormationGuide_{label}_{k:02}"
            group.objects.link(trace)
            trace.parent = motion
            trace.material_slots[0].link = "OBJECT"
            trace.material_slots[0].material = guide_gray
            trace["a"], trace["b"], trace["side"] = start, end, side

    gray = bpy.data.materials.new("Flock clay")
    gray.diffuse_color = (.32, .34, .33, 1.)
    gray.use_nodes = True
    gray.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = gray.diffuse_color
    ground = scene.objects["Review Ground"]
    ground_mat = ground.data.materials[0].copy()
    ground.data.materials[0] = ground_mat
    ground_mat.name = "Sage watercolor | review ground"
    nodes, links = ground_mat.node_tree.nodes, ground_mat.node_tree.links
    shader = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    coord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.1
    noise.inputs["Detail"].default_value = 2.2
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = .15
    ramp.color_ramp.elements[0].color = (.20, .29, .26, 1.)
    ramp.color_ramp.elements[1].position = .83
    ramp.color_ramp.elements[1].color = (.27, .36, .31, 1.)
    links.new(coord.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs[0])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    frame_settings(scene, GAME)
    rebuild_review(scene, control)
    return group, gray


def rebuild_review(scene, control):
    motion = scene.objects["Review flight path"]
    carriers = [scene.objects[f"Preview carrier | {i:02}"] for i in range(12)]
    traces = [obj for obj in scene.objects if obj.type == "MESH" and "a" in obj and "b" in obj]
    for item in (motion, control, *carriers, *traces):
        item.animation_data_clear()
    ground = scene.objects["Review Ground"].location.z
    source_curves = [
        {(c.data_path, c.array_index): c for c in action_curves(bpy.data.actions[name])}
        for name in ("Cruise_Flap_Loop", "Formation_Blend")
    ]
    for index in range(12):
        remake_action(scene.objects[f"Review rig | {index:02}"], source_curves, index, control)

    location = Vector((0, 0, 0))
    for frame in range(1, FINAL_FRAME + 1):
        turn = 1.35 * smootherstep((frame - 161) / 14)
        if frame > 1:
            location += .88 / FPS * Vector((-math.sin(turn), math.cos(turn), 0.))
        motion.location = location
        motion.rotation_euler.z = turn
        for attr in ("location", "rotation_euler"):
            motion.keyframe_insert(attr, frame=frame)
        control["opacity"] = guide_weight(frame, control) * control["peak_opacity"]
        control.keyframe_insert('["opacity"]', frame=frame)
        for idx, carrier in enumerate(carriers):
            carrier.location = local_offset(idx, frame, control)
            carrier.keyframe_insert("location", frame=frame)
        for trace in traces:
            a, b = carriers[trace["a"]].location, carriers[trace["b"]].location
            center, yaw, scale = gap_pose(a, b, trace["side"], ground, control)
            trace.location, trace.rotation_euler.z, trace.scale = center, yaw, scale
            for attr in ("location", "rotation_euler", "scale"):
                trace.keyframe_insert(attr, frame=frame)
    for item in (motion, control, *carriers, *traces):
        linearize(item)


def render(scene, path, frame, camera=REAR, size=GAME, samples=8):
    frame_settings(scene, size, samples)
    scene.frame_set(frame)
    scene.camera = scene.objects[camera]
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True, scene=scene.name)


def review_gray(scene, group, gray, guide_gray, output):
    birds = [scene.objects[f"Review mesh | {i:02}"] for i in range(12)]
    traces = [obj for obj in group.objects if obj.type == "MESH"]
    mats = [(ob, slot, slot.link, slot.material) for ob in [*birds, *traces] for slot in ob.material_slots]
    try:
        for ob, slot, _, _ in mats:
            slot.link = "OBJECT"
            slot.material = gray if ob in birds else guide_gray
        render(scene, output / "graybox_fixed_rear.png", 63)
        render(scene, output / "graybox_overhead.png", 63, TOP, (840, 520))
    finally:
        for _, slot, link, material in mats:
            slot.link = link
            slot.material = material


def export_dash(source, scene, path):
    bpy.context.window.scene = scene
    bpy.context.view_layer.objects.active = source
    source.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, use_active_scene=True,
                              export_extras=True, export_animations=False, export_cameras=False)
    source.select_set(False)


def export_video(scene, output):
    with TemporaryDirectory(prefix="FX-008-", dir=output.parent) as directory:
        scratch = Path(directory)
        for index, frame in enumerate(range(1, FINAL_FRAME + 1, FPS // CLIP_FPS)):
            render(scene, scratch / f"{index:03}.png", frame, samples=6)
        # 4:2:2 keeps the 393-line gate and supports default macOS playback.
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-framerate", str(CLIP_FPS),
            "-i", str(scratch / "%03d.png"), "-an", "-c:v", "prores_ks", "-profile:v", "1",
            "-pix_fmt", "yuv422p10le", "-movflags", "+faststart", str(output / VIDEO_BASENAME)
        ], check=True)


def prepare_master(scene, control, output):
    bpy.context.window.scene = scene
    scene.camera = scene.objects[REAR]
    scene.frame_set(63)
    frame_settings(scene, GAME, 14)
    scene.render.filepath = "//"
    bpy.ops.object.select_all(action="DESELECT")
    control.select_set(True)
    bpy.context.view_layer.objects.active = control
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output), compress=True)


def generate(output, skip_video):
    output.mkdir(parents=True, exist_ok=True)
    assert not any(output.iterdir()), "Provide an empty staging directory."
    bpy.ops.wm.open_mainfile(filepath=str(DEPENDENCY_BLEND), load_ui=False)
    scene = bpy.data.scenes["Review | Loose flock to V"]
    bpy.context.window.scene = scene
    for other in list(bpy.data.scenes):
        if other != scene:
            bpy.data.scenes.remove(other)
    asset_scene = bpy.data.scenes.new("FX-008 | portable ribbon")
    asset_group = grouped(asset_scene, "FX-008 | portable mesh")
    dash = make_dash(asset_group)
    guide_gray = material("Guide clay")
    dash.data.materials.append(guide_gray)
    group, gray = review_stage(scene, dash, guide_gray)
    review_gray(scene, group, gray, guide_gray, output)

    tex = output / "textures" / TEXTURE
    tex.parent.mkdir()
    texture_info = write_texture(tex)
    image = bpy.data.images.load(str(tex))
    image.pack()
    image.filepath = "//textures/" + TEXTURE
    dash.data.materials[0] = material("FormationGuide | warm gray-gold", image)
    install_review_material(scene, group, image)
    dash.asset_mark()
    dash.asset_data.description = "Feather & Tide FX-008 v001 | low-opacity watercolor brush ribbon"
    export_dash(dash, asset_scene, output / GLB_BASENAME)
    bpy.context.window.scene = scene
    control = scene.objects[CONTROL_NAME]
    prepare_master(scene, control, output / SOURCE_BASENAME)

    for label, frame in [
        ("loose", 5), ("forming", 37), ("formed", 63), ("releasing", 85),
        ("released", 97), ("broken", 169)
    ]:
        render(scene, output / f"preview_{label}.png", frame)
    render(scene, output / "preview_top_formed.png", 63, TOP, (840, 520))
    traces = [obj for obj in group.objects if obj.type == "MESH"]
    for trace in traces:
        trace.hide_render = True
    for label, frame in [("formed", 63), ("broken", 169), ("released", 97)]:
        render(scene, output / f"comparison_{label}_without_trace.png", frame)
    for trace in traces:
        trace.hide_render = False
    if not skip_video:
        export_video(scene, output)

    print("Texture", texture_info)


def install_review_material(scene, group, image):
    control = scene.objects[CONTROL_NAME]
    review = material("Warm gray-gold | review opacity", image, review=True)
    driver = review.node_tree.nodes["Review opacity"].inputs[1].driver_add("default_value").driver
    driver.type = "AVERAGE"
    variable = driver.variables.new()
    variable.name, variable.type = "preview_opacity", "SINGLE_PROP"
    variable.targets[0].id, variable.targets[0].data_path = control, '["opacity"]'
    for trace in group.objects:
        if trace.type == "MESH":
            trace.material_slots[0].link = "OBJECT"
            trace.material_slots[0].material = review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New staging directory or .blend destination for a controls rebuild.")
    parser.add_argument("--skip-video", action="store_true", help="Render only the stills for a quick look.")
    parser.add_argument("--rebuild-controls", type=Path, help="Key edited placement and opacity controls from this master.")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.rebuild_controls:
        assert args.output.resolve() != args.rebuild_controls.resolve(), "Choose a new .blend destination."
        bpy.ops.wm.open_mainfile(filepath=str(args.rebuild_controls.resolve()), load_ui=False)
        scene = bpy.data.scenes[REVIEW_NAME]
        control = scene.objects[CONTROL_NAME]
        rebuild_review(scene, control)
        prepare_master(scene, control, args.output.resolve())
    else:
        generate(args.output.resolve(), args.skip_video)


if __name__ == "__main__":
    main()
