"""Build and independently verify the S4 turbine with Blender 5.2."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import runpy
import struct
import subprocess

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

FPS = 24
PERIOD = 9.0
FRAME = (852, 393)
HUB = (0, -.46, 2.45)
SCALE = .9900 / 27.5
REVIEW_LIFT = 48 * SCALE
RADIUS = 78 * SCALE
ROOT = "Main_Turbine"
CLIP = "Rotor_Constant_Loop"
BLEND = "STR-001_Main_Turbine.blend"
GLB = "STR-001_Main_Turbine.glb"
COLLECTION = "Main_Turbine | asset"
PAPER = "ft_goose_mat_soft_stone_basecolor.png"
PALETTE = {
    "Warm porcelain": ("D9D5C9", "F1ECE1", .73),
    "Aluminum shadow": ("A9ADB0", "CBD0CF", .63),
    "Dull zinc": ("737C7D", "A4ABAA", .77),
    "Foundation": ("93908A", "C0B9AB", .91),
    "Pale lichen | index stripe": ("A19678", "C3BBA4", .78),
}


def check(condition, detail):
    if not condition:
        raise ValueError(detail)


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def upstream(library):
    return runpy.run_path(str(library / "ENV-001/v001/ENV-001_generate.py"))


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 0, round(PERIOD * FPS)
    return scene


def object_in(collection, name, data=None, parent=None, location=(0, 0, 0)):
    item = bpy.data.objects.new(name, data)
    collection.objects.link(item)
    item.parent = parent
    item.location = location
    return item


def collection_in(scene, name):
    group = bpy.data.collections.new(name)
    scene.collection.children.link(group)
    return group


def paint_surface(material, name, parent, strips, materials):
    """Join section rings and unwrap each span before capping the ends."""
    cardinal = len(strips[0])
    points = [p for section in strips for p in section]
    faces = [tuple(reversed(range(cardinal)))]
    for row in range(len(strips) - 1):
        for col in range(cardinal):
            a = row * cardinal
            b = (row + 1) * cardinal
            faces.append((a + col, a + (col + 1) % cardinal,
                          b + (col + 1) % cardinal, b + col))
    end = (len(strips) - 1) * cardinal
    faces.append(tuple(range(end, end + cardinal)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], faces)
    mesh.update()
    for mat in materials:
        mesh.materials.append(mat)
    uv = mesh.uv_layers.new(name="Surface")
    for p in mesh.polygons:
        if p.index in (0, len(faces) - 1):
            for j, loop in enumerate(p.loop_indices):
                theta = j * math.tau / cardinal
                uv.data[loop].uv = (.5 + .42 * math.cos(theta), .5 + .42 * math.sin(theta))
        else:
            row, col = divmod(p.index - 1, cardinal)
            u, v = col / cardinal, row / (len(strips) - 1)
            du, dv = 1 / cardinal, 1 / (len(strips) - 1)
            for loop, coord in zip(p.loop_indices, ((u, v), (u + du, v),
                                                    (u + du, v + dv), (u, v + dv))):
                uv.data[loop].uv = coord
            p.use_smooth = True
        p.material_index = material(p.index)
    return object_in(parent.users_collection[0], name, mesh, parent)


def radial(parent, name, rings, mats, bands, axis="Z", count=32):
    sections = []
    for t, a, b, offset in rings:
        section = []
        for i in range(count):
            c, s = a * math.cos(i * math.tau / count), b * math.sin(i * math.tau / count)
            section.append((c, s + offset, t) if axis == "Z" else (c, -t, s + offset))
        sections.append(section)
    return paint_surface(lambda i: bands[min(max(0, (i - 1) // count), len(bands) - 1)],
                         name, parent, sections, mats)


def build_turbine(scene, gray):
    group = collection_in(scene, COLLECTION)
    root = object_in(group, ROOT)
    root["variant"] = ROOT
    root["ground_axis"] = "Blender XY, +Z up, rotor faces -Y"
    root["candidate_sweep_radius_BU"] = RADIUS
    root["collision_authority"] = "Engine Zone"
    base = radial(root, "Foundation", [(0,.45,.45,0),(.04,.51,.51,0),(.135,.50,.50,0),
                                      (.19,.43,.43,0),(.21,.32,.32,0)], gray, [3,3,3,2])
    tower = radial(root, "Tower", [(.19,.27,.27,0),(.235,.27,.27,0),(.31,.252,.252,0),
                                  (.50,.236,.236,0),(.54,.233,.233,0),(1.18,.184,.184,0),
                                  (2.08,.132,.132,0),(2.41,.127,.127,0)], gray, [2,1,1,2,0,0,0])
    nacelle = radial(root, "Nacelle", [(-.48,.064,.060,2.44),(-.435,.154,.132,2.47),
                                     (-.27,.225,.181,2.49),(.03,.241,.191,2.49),
                                     (.07,.241,.191,2.49),(.24,.230,.192,2.48),
                                     (.34,.196,.164,2.46),(.40,.150,.130,2.45)], gray, [2,1,0,2,0,0,1], "Y")
    door = radial(tower, "Service hatch", [(.231,.067,.139,.49),(.246,.069,.14,.49),
                                         (.254,.052,.12,.49)], gray, [2,1], "Y", 16)
    rotor = object_in(group, "Rotor", parent=root, location=HUB)
    rotor["axis_local"] = "+Y"
    rotor["positive_direction_from_front"] = "clockwise looking from -Y toward +Y"
    rotor["period_seconds"] = PERIOD
    hub = radial(rotor, "Hub", [(-.028,.19,.19,0),(.02,.207,.207,0),(.12,.202,.202,0),
                                (.20,.160,.160,0),(.273,.071,.071,0),(.29,.022,.022,0)],
                 gray, [2,1,0,0,0], "Y")
    blades = []
    profile = [(.13,.066,.05,.0,.004),(.22,.069,.048,.0,-.004),(.33,.123,.046,.014,-.012),
               (.53,.192,.041,.042,-.019),(.79,.170,.038,.084,-.021),(1.19,.132,.028,.143,-.013),
               (1.66,.091,.020,.192,-.008),(1.99,.072,.017,.231,-.003),(2.10,.069,.016,.246,0),
               (2.39,.048,.013,.282,.014),(2.54,.038,.010,.312,.032),(2.58,.010,.006,.329,.046)]
    for i in range(3):
        strips = []
        for z, chord, thickness, sweep, y in profile:
            strips.append([((sweep + chord * math.cos(theta)) * .85,
                            y + thickness * math.sin(theta) + .22 * chord * math.cos(theta), z * .72)
                           for theta in (j * math.tau / 12 for j in range(12))])
        blade = paint_surface(lambda k: ({1:1, 7:1 if i == 0 else 0, 8:4 if i == 0 else 1,
                                          9:1}.get(max(0, (k - 1) // 12), 0)),
                              f"Blade_{i + 1:02}", rotor, strips, gray)
        blade.rotation_euler.y = i * math.tau / 3
        blades.append(blade)
    animate(rotor, 0, CLIP)
    return group, root, rotor, blades


def animate(rotor, phase_degrees, name):
    """Quarter-turn quaternion keys prevent a full revolution collapsing in glTF."""
    rotor.rotation_mode = "QUATERNION"
    phase = math.radians(phase_degrees)
    for step in range(17):
        theta = phase + step * math.tau / 16
        rotor.rotation_quaternion = (math.cos(theta / 2), 0, math.sin(theta / 2), 0)
        rotor.keyframe_insert(data_path="rotation_quaternion", frame=step * FPS * PERIOD / 16)
    anim = rotor.animation_data
    anim.action.name = name
    curves = anim.action.layers[0].strips[0].channelbag(anim.action_slot).fcurves
    for curve in curves:
        for key in curve.keyframe_points:
            key.interpolation = "LINEAR"
        curve.modifiers.new("CYCLES")


def select_export(scene, items, path, scene_clip=None):
    bpy.context.window.scene = scene
    bpy.ops.object.select_all(action="DESELECT")
    for item in items:
        item.select_set(True)
    options = dict(filepath=str(path), use_selection=True, export_extras=True, export_yup=True,
                   export_apply=False, export_anim_single_armature=False,
                   export_animation_mode="SCENE" if scene_clip else "ACTIONS",
                   export_force_sampling=True, export_frame_range=True, export_frame_step=1)
    if scene_clip:
        options["export_nla_strips_merged_animation_name"] = scene_clip
    bpy.ops.export_scene.gltf(**options)


def apply_paper(library, output):
    mat_dir = library / "MAT-001/v001"
    parent = mat_dir / "MAT-001_watercolor_master.blend"
    with bpy.data.libraries.load(str(parent), link=False) as (_, dest):
        dest.materials = ["SoftStone"]
    stone = dest.materials[0]
    source = mat_dir / "textures" / PAPER
    source_img = next(n.image for n in stone.node_tree.nodes if n.type == "TEX_IMAGE")
    check(source_img.packed_file.data == source.read_bytes(), "MAT-001 PNG source differs")
    pixels = np.empty(len(source_img.pixels), dtype=np.float32)
    source_img.pixels.foreach_get(pixels)
    pixels = pixels.reshape(512, 512, 4)
    luminance = (pixels[:, :, :3] * [.2126, .7152, .0722]).sum(axis=2)
    paper = np.clip((luminance - np.percentile(luminance, 4)) /
                    (np.percentile(luminance, 96) - np.percentile(luminance, 4)), 0, 1)
    t = .34 + .61 * paper[:, :, None]
    texture_dir = output / "textures"
    texture_dir.mkdir()
    products = []
    mats = []
    for i, (name, (low, high, roughness)) in enumerate(PALETTE.items()):
        filename = "ft_goose_str_turbine_" + ("shell", "alloy", "zinc", "footing", "stripe")[i] + ".png"
        rgba = np.ones((512, 512, 4), dtype=np.float32)
        rgb = [np.array([int(value[j:j+2], 16) / 255 for j in (0, 2, 4)]) for value in (low, high)]
        rgba[:, :, :3] = rgb[0] + (rgb[1] - rgb[0]) * t
        source_out = bpy.data.images.new(filename, 512, 512, alpha=False)
        source_out.pixels.foreach_set(rgba.ravel())
        source_out.filepath_raw = str(texture_dir / filename)
        source_out.file_format = "PNG"
        source_out.save()
        bpy.data.images.remove(source_out)
        image = bpy.data.images.load(str(texture_dir / filename))
        image.pack()
        image.filepath = "//textures/" + filename
        mat = stone.copy()
        mat.name = name
        shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        shader.inputs["Roughness"].default_value = roughness
        next(n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE").image = image
        mat.diffuse_color = tuple(((rgb[0] + rgb[1]) / 2) ** 2.2) + (1,)
        mats.append(mat)
        products.append({"material": name, "file": "textures/" + filename,
                         "sha256": digest(texture_dir / filename),
                         "palette_sRGB": [low, high], "roughness": roughness})
    return mats, {"mother_blend": str(parent.relative_to(library)), "mother_sha256": digest(parent),
                  "material_template": "SoftStone", "source_png": str(source.relative_to(library)),
                  "source_png_sha256": digest(source), "outputs": products}


def stage(scene, library, base, root):
    studio = base["studio"](scene, scene.collection)
    sky = scene.world.node_tree.nodes.get("Background")
    sky.inputs["Color"].default_value = (.69, .75, .79, 1)
    sky.inputs["Strength"].default_value = .68
    sun = next(o for o in studio.objects if o.type == "LIGHT")
    sun.rotation_euler = Vector((.37,.57,-1)).to_track_quat("-Z","Y").to_euler()
    neutral = base["paint"]("Review ground", "96958B")
    base["rectangle"](studio, "Studio ground", -100, 100, -100, 100, -.006, neutral)
    bird = base["add_goose"](studio)
    cam = base["camera"](studio, "Gameplay rear | 50° vertical", (0,0,1), (0,1,0))
    base["pose_at"](cam, bird, (-2.8, -7.1), Vector((.07, .99755)).normalized())
    cam.location.z += REVIEW_LIFT
    bird.location.z += REVIEW_LIFT
    ring = base["paint"]("Review only | candidate sweep circle", "686471")
    vertices = [(r * math.cos(i * math.tau / 160), r * math.sin(i * math.tau / 160), .004)
                for i in range(160) for r in (RADIUS - .07, RADIUS)]
    faces = [(2*i, 2*i+1, (2*i+3)%320, (2*i+2)%320) for i in range(160)]
    base["simple_mesh"](studio, "Review only | 78-unit sweep boundary", vertices, faces, ring)
    base["set_preview_workspace"](scene, cam)
    return studio, cam


def swept_geometry(scene, root, rotor, blades):
    points = []
    for blade in blades:
        for vertex in blade.data.vertices:
            q = blade.matrix_basis @ vertex.co
            radius = math.hypot(q.x, q.z)
            points.append((radius, q.y))
    max_radius = max(r for r, _ in points)
    # At the worst phase X equals the in-plane radius and Z equals hub height.
    ground = max(math.hypot(radius, HUB[1] + y) for radius, y in points)
    lower = HUB[2] - max_radius
    check(lower > .25 and ground <= RADIUS - .10, (lower, ground, RADIUS))
    bpy.context.view_layer.update()
    actual = 0
    for i in range(361):
        frame = i * PERIOD * FPS / 360
        scene.frame_set(int(frame), subframe=frame % 1)
        for blade in blades:
            for v in blade.data.vertices:
                p = blade.matrix_world @ v.co
                actual = max(actual, math.hypot(p.x, p.y))
    check(abs(ground - actual) < .001, (ground, actual))
    scene.frame_set(0)
    return {"continuous_in_plane_tip_radius_BU": max_radius,
            "continuous_ground_envelope_radius_about_base_BU": ground,
            "sampled_ground_envelope_radius_BU": actual, "sampled_phases": 361,
            "minimum_tip_to_ground_BU": lower, "maximum_tip_height_BU": HUB[2] + max_radius,
            "reference_sweep_radius_BU": RADIUS, "margin_BU": RADIUS - ground,
            "hub_pivot_BU": list(rotor.location), "reference_envelope_verification_epsilon_BU": .001}


def glb_parts(path):
    payload = path.read_bytes()
    magic, version, total = struct.unpack_from("<4sII", payload)
    check((magic, version, total) == (b"glTF", 2, len(payload)), path)
    length = struct.unpack_from("<I", payload, 12)[0]
    return json.loads(payload[20:20 + length]), payload[28 + length:]


def image_hashes_glb(path):
    gltf, binary = glb_parts(path)
    hashes = set()
    for image in gltf["images"]:
        view = gltf["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        hashes.add(hashlib.sha256(binary[start:start + view["byteLength"]]).hexdigest())
    return hashes


def mesh_fingerprint(item):
    mesh = item.data
    mesh.calc_loop_triangles()
    uv = mesh.uv_layers.active.data
    signatures = Counter()
    for tri in mesh.loop_triangles:
        corners = []
        for idx in tri.loops:
            pos = mesh.vertices[mesh.loops[idx].vertex_index].co
            coord = [round(float(x), 4) for x in (*pos, *uv[idx].uv)]
            corners.append(tuple(coord))
        mat = item.material_slots[tri.material_index].material
        tex = next(n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE")
        texture = hashlib.sha256(tex.image.packed_file.data).hexdigest()
        signatures[(texture, tuple(sorted(corners)))] += 1
    return signatures


def scene_fingerprint(root):
    objects = [root, *root.children_recursive]
    return {o.name: {"parent": o.parent.name if o.parent else None, "type": o.type,
                     "location": tuple(o.location), "scale": tuple(o.scale),
                     "static_rotation": tuple(o.matrix_basis.to_quaternion()),
                     "mesh": mesh_fingerprint(o) if o.type == "MESH" else None}
            for o in objects}


def check_animation(scene, rotor, offset=0):
    bpy.context.view_layer.update()
    vector = Vector((0, 0, 1))
    period_frames = round(FPS * PERIOD)
    ell = []
    residuals = []
    for f in range(period_frames * 2 + 1):
        frame = f / 2
        scene.frame_set(int(frame), subframe=frame % 1)
        point = rotor.matrix_basis.to_quaternion() @ vector
        theta = math.atan2(point.x, point.z)
        residuals.append(abs(math.remainder(theta - math.radians(offset) - frame * math.tau / period_frames,
                                            math.tau)))
        ell.append(point)
    diffs = [math.atan2(a.cross(b).y, a.dot(b)) for a, b in zip(ell, ell[1:])]
    seam = (ell[0] - ell[-1]).length
    check(min(diffs) > 0 and max(residuals) < .0003 and seam < 1e-5,
          (min(diffs), max(residuals), seam))
    scene.frame_set(0)
    return {"half_frame_samples": len(ell), "period_seconds": PERIOD, "axis_Blender_local": "+Y",
            "angle_max_error_rad": max(residuals), "seam_unit_vector_gap": seam,
            "half_frame_step_min_max_degrees": [math.degrees(min(diffs)), math.degrees(max(diffs))]}


def screen_motion(scene, camera, rotor, frame_step=2):
    """Track the uniquely tinted blade through its whole visible cycle."""
    scene.render.resolution_x, scene.render.resolution_y = FRAME
    center = world_to_camera_view(scene, camera, rotor.matrix_world.translation)
    points = []
    margin = math.inf
    for frame in range(0, round(FPS * PERIOD) + 1, frame_step):
        scene.frame_set(frame)
        p = world_to_camera_view(scene, camera, rotor.matrix_world @ Vector((.25, .02, 1.80)))
        points.append(Vector(((p.x - center.x) * FRAME[0], (p.y - center.y) * FRAME[1])))
        for blade in (o for o in rotor.children if o.name.startswith("Blade_")):
            for v in blade.data.vertices:
                q = world_to_camera_view(scene, camera, blade.matrix_world @ v.co)
                margin = min(margin, q.x * FRAME[0], (1-q.x)*FRAME[0],
                             q.y * FRAME[1], (1-q.y)*FRAME[1])
    signed = [math.atan2(a.x*b.y-a.y*b.x, a.dot(b)) for a,b in zip(points, points[1:])]
    check(max(signed) < 0 and max(map(abs, signed)) < math.pi/3, (min(signed),max(signed)))
    print("ROTOR SCREEN MARGIN",margin, flush=True)
    check(margin > 2, margin)
    scene.frame_set(0)
    return {"all_blade_vertices_min_frame_margin_px": margin,
            "unique_blade_screen_samples_including_seam":len(points),
            "screen_clockwise_step_min_max_degrees": [math.degrees(-max(signed)), math.degrees(-min(signed))],
            "min_marker_radius_pixels":min(p.length for p in points),
            "source_degrees_per_video_frame":360/PERIOD/(FPS/frame_step),
            "three_blade_alias_limit_degrees_per_frame":60}


def encode(folder, path, fps):
    subprocess.run(["ffmpeg","-v","error","-y","-framerate",str(fps),"-i",str(folder / "%04d.png"),
                    "-vf","pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=0x243133",
                    "-c:v","libx264","-crf","17","-pix_fmt","yuv420p","-movflags","+faststart",str(path)],
                   check=True)


def decoded(path, size, count):
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                   check=True)
    info = json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0",
        "-count_frames","-show_entries","stream=width,height,r_frame_rate,duration,nb_read_frames,codec_name",
        "-of","json",str(path)]))["streams"][0]
    check((info["width"], info["height"]) == size and int(info["nb_read_frames"]) == count
          and info["codec_name"] == "h264", info)
    return info


def build(library, out):
    base = upstream(library)
    scene = reset()
    scene.name = "STR-001 | Main Turbine"
    gray = [base["paint"](f"Clay {i}", rgb) for i, rgb in enumerate(
            ("BFBDB7","AFAEAA","82817E","94918E","A2A09B"))]
    group, root, rotor, blades = build_turbine(scene, gray)
    studio, cam = stage(scene, library, base, root)
    bpy.context.view_layer.update()
    measure = swept_geometry(scene, root, rotor, blades)
    base["render"](scene, cam, out, "graybox_fixed_rear", FRAME, 12)
    mats, texture_map = apply_paper(library, out)
    for item in group.objects:
        if item.type == "MESH":
            for i, mat in enumerate(mats):
                item.data.materials[i] = mat
    scene.frame_set(18)
    base["render"](scene, cam, out, "preview_fixed_rear", FRAME, 18)
    scene.frame_set(73)
    base["render"](scene, cam, out, "preview_fixed_rear_phase", FRAME, 18)
    oblique = base["camera"](studio, "Model detail", (7,-9,5.9),(0,-.1,2.72))
    base["render"](scene, oblique, out, "preview_detail", (1000,680), 24)
    source_motion = screen_motion(scene, cam, rotor)
    scene.frame_set(0)
    select_export(scene, list(group.objects), out / GLB)
    scene.render.filepath = "//preview_fixed_rear.png"
    base["set_preview_workspace"](scene, cam)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / BLEND))
    frames = out / "frames"
    frames.mkdir()
    for i, frame in enumerate(range(0, int(FPS * PERIOD), 2)):
        scene.frame_set(frame)
        base["render"](scene, cam, frames, f"{i:04d}", FRAME, 6)
    encode(frames, out / "preview_rotor_loop.mp4", 12)
    write(out / "measurements.json", {"geometry":measure, "texture_mapping":texture_map,
                                      "source_screen_tracking":source_motion})


def verify(library, delivery, out):
    base = upstream(library)
    reset()
    bpy.ops.wm.open_mainfile(filepath=str(delivery / BLEND))
    scene = bpy.context.scene
    rotor = bpy.data.objects["Rotor"]
    source_motion = check_animation(scene, rotor)
    camera = scene.camera
    source_screen = screen_motion(scene, camera, rotor)
    camera_matrix = camera.matrix_world.copy()
    source = scene_fingerprint(bpy.data.objects[ROOT])
    triangles = sum(sum(info["mesh"].values()) for info in source.values() if info["mesh"])
    base_z = min(v.co.z for v in bpy.data.objects["Foundation"].data.vertices)
    check(base_z == 0 and tuple(bpy.data.objects[ROOT].location) == (0,0,0), base_z)
    reset()
    gltf, _ = glb_parts(delivery / GLB)
    rotor_doc = next(x for x in gltf["nodes"] if x["name"] == "Rotor")
    check(Vector(rotor_doc["translation"]).almost_equal(Vector((0, HUB[2], -HUB[1])))
          if hasattr(Vector(), "almost_equal")
          else (Vector(rotor_doc["translation"]) - Vector((0, HUB[2], -HUB[1]))).length < 1e-6,
          rotor_doc)
    check(len(gltf["animations"]) == 1 and len(gltf["animations"][0]["channels"]) == 1,
          "Expected one rotor animation")
    sampler = gltf["animations"][0]["samplers"][0]
    end = gltf["accessors"][sampler["input"]]["max"][0]
    check(abs(end - PERIOD) < 1e-6 and sampler["interpolation"] == "LINEAR", (sampler, end))
    check(image_hashes_glb(delivery / GLB) == {digest(p) for p in (delivery/"textures").glob("*.png")},
          "Embedded PNGs differ")
    bpy.ops.import_scene.gltf(filepath=str(delivery / GLB))
    scene = bpy.context.scene
    root, rotor = bpy.data.objects[ROOT], bpy.data.objects["Rotor"]
    for track in rotor.animation_data.nla_tracks:
        track.mute = True
        if rotor.animation_data.action is None:
            rotor.animation_data.action = track.strips[0].action
    scene.frame_set(0)
    bpy.context.view_layer.update()
    readback = scene_fingerprint(root)
    check(readback.keys() == source.keys(), (readback.keys(), source.keys()))
    mismatches = {}
    for name, info in source.items():
        other = readback[name]
        for key in ("parent", "type", "mesh"):
            if info[key] != other[key]:
                if key != "mesh" or info[key] is None:
                    raise ValueError((name, key))
                # 4-decimal bin boundaries can differ after the glTF V flip. Compare closest cyclic triangle.
                mismatches[name] = mesh_error(delivery, name, bpy.data.objects[name])
        for key in ("location", "scale", "static_rotation"):
            check(max(abs(a-b) for a,b in zip(info[key],other[key])) < 1e-5, (name,key))
    reimport_motion = check_animation(scene, rotor)
    blades = [bpy.data.objects[f"Blade_{i:02}"] for i in (1,2,3)]
    reimport_geometry = swept_geometry(scene, root, rotor, blades)
    _, cam = stage(scene, library, base, root)
    cam.matrix_world = camera_matrix
    scene.frame_set(18)
    base["render"](scene, cam, out, "roundtrip_fixed_rear", FRAME, 18)
    video = decoded(delivery / "preview_rotor_loop.mp4", (852,394), 108)
    write(out / "recheck.json", {"result":"pass", "blender":bpy.app.version_string,
          "checks":{"source_and_GLTF_object_count":len(source),"triangles":triangles,
                    "basis_parent_and_local_TRS_match":True,"mesh_vertices_uv_and_materials_match":True,
                    "per_corner_roundtrip_fallback_errors":mismatches,
                    "GLTF_rotation_channel_interpolation":sampler["interpolation"],
                    "GLTF_animation_name":gltf["animations"][0]["name"],"GLTF_animation_end_s":end,
                    "GLTF_hub_parent_translation":rotor_doc["translation"],
                    "five_embedded_png_match_by_sha256":True,
                    "source_animation":source_motion,"roundtrip_animation":reimport_motion,
                    "source_screen_rotation":source_screen,"roundtrip_geometry":reimport_geometry,
                    "decoded_video":video}})


def mesh_arrays(item):
    mesh = item.data
    mesh.calc_loop_triangles()
    uv = mesh.uv_layers.active.data
    rows = {}
    for tri in mesh.loop_triangles:
        material = item.material_slots[tri.material_index].material
        texture = next(n.image for n in material.node_tree.nodes if n.type == "TEX_IMAGE")
        key = hashlib.sha256(texture.packed_file.data).hexdigest()
        rows.setdefault(key, []).append([(*mesh.vertices[mesh.loops[i].vertex_index].co, *uv[i].uv)
                                          for i in tri.loops])
    return rows


def mesh_error(delivery, name, imported):
    readback = mesh_arrays(imported)
    with bpy.data.libraries.load(str(delivery / BLEND), link=False) as (_, target):
        target.objects = [name]
    original = mesh_arrays(target.objects[0])
    check(original.keys() == readback.keys(), (name, "material assignment"))
    maximum = 0
    for key, values in original.items():
        other = readback[key]
        check(len(values) == len(other), (name, "triangle count"))
        right = np.asarray(other)
        for left in np.asarray(values):
            distances = np.min([np.abs(right - np.roll(left, step, axis=0)).max(axis=(1,2))
                                for step in range(3)], axis=0)
            maximum = max(maximum, float(distances.min()))
    check(maximum < 3e-6, (name, maximum))
    return maximum


def parse():
    import sys
    args = sys.argv[sys.argv.index("--")+1:]
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    cli.add_argument("--library", type=Path, default=Path(__file__).resolve().parents[2])
    cli.add_argument("--verify", type=Path)
    options = cli.parse_args(args)
    options.output.mkdir(parents=True, exist_ok=True)
    check(not any(options.output.iterdir()), "Use an independent empty output directory")
    return options


if __name__ == "__main__":
    options = parse()
    if options.verify:
        verify(options.library.resolve(), options.verify.resolve(), options.output.resolve())
    else:
        build(options.library.resolve(), options.output.resolve())
