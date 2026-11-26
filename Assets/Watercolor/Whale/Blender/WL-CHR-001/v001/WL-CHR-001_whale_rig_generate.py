"""Build WL-CHR-001 using Blender's bundled Python and glTF add-on."""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import bmesh
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


ASSET = "WL-CHR-001"
STEM = f"{ASSET}_whale_rig"
SIDES = (("R", 1), ("L", -1))
SEGMENTS = 32
GAME_CAMERA_SIZE = (1280, 640)
UNITS_PER_BU = 10.0
GAME_CAMERA_DISTANCE = 180.0
GAME_PITCH = 0.48
GAME_FOV = 50.0

# Longitudinal sections: Y, half width, half height, vertical center.
BODY = [
    (-5.35, 0, 0, 0.02),
    (-5.31, .11, .057, .02),
    (-5.23, .22, .089, .02),
    (-5.14, .29, .118, .015),
    (-4.96, .36, .16, .008),
    (-4.77, .36, .196, .005),
    (-4.58, .335, .228, .005),
    (-4.39, .33, .251, .005),
    (-4.10, .345, .30, .01),
    (-3.74, .40, .39, .015),
    (-3.34, .50, .50, .025),
    (-2.91, .63, .655, .04),
    (-2.42, .78, .81, .055),
    (-2.15, .86, .89, .058),
    (-1.88, .94, .965, .06),
    (-1.61, 1.019, 1.032, .057),
    (-1.30, 1.105, 1.10, .05),
    (-1.00, 1.177, 1.158, .037),
    (-.69, 1.235, 1.21, .02),
    (0.0, 1.335, 1.27, 0.0),
    (.58, 1.39, 1.275, -.015),
    (.88, 1.405, 1.268, -.025),
    (1.19, 1.41, 1.245, -.032),
    (1.51, 1.40, 1.21, -.037),
    (1.84, 1.37, 1.16, -.032),
    (2.18, 1.33, 1.10, -.025),
    (2.60, 1.275, 1.022, -.025),
    (3.03, 1.20, .938, -.03),
    (3.42, 1.115, .848, -.04),
    (3.81, 1.022, .754, -.058),
    (4.17, .905, .661, -.083),
    (4.48, .764, .555, -.108),
    (4.71, .592, .444, -.128),
    (4.87, .419, .321, -.144),
    (4.96, .248, .195, -.153),
    (5.00, .104, .084, -.156),
    (5.012, 0, 0, -.156),
]

# Outboard sections: |X|, chord center Y, half chord, half thickness, Z, chord camber.
PECTORAL = [
    (1.47, 1.50, .59, .367, -.335, .030),
    (1.59, 1.41, .577, .284, -.385, .029),
    (1.76, 1.27, .544, .222, -.448, .026),
    (1.98, 1.08, .487, .173, -.524, .023),
    (2.23, .85, .41, .128, -.606, .020),
    (2.46, .62, .326, .093, -.675, .014),
    (2.64, .40, .242, .067, -.714, .010),
    (2.78, .20, .152, .043, -.727, .005),
    (2.86, .06, .070, .022, -.722, .002),
    (2.89, -.015, 0, 0, -.715, 0),
]
FLUKE = [
    (.42, -4.77, .424, .117, .003, .012),
    (.57, -4.83, .475, .100, .011, .019),
    (.78, -4.92, .526, .091, .030, .022),
    (1.02, -5.015, .547, .080, .055, .024),
    (1.29, -5.11, .536, .065, .080, .024),
    (1.57, -5.22, .469, .049, .115, .021),
    (1.83, -5.32, .360, .036, .151, .014),
    (2.04, -5.42, .235, .025, .190, .009),
    (2.18, -5.49, .125, .015, .224, .005),
    (2.25, -5.53, .049, .007, .243, .002),
    (2.277, -5.542, 0, 0, .252, 0),
]

BONES = (
    ("Root", None, (0, 0, 0), (0, .55, 0), False),
    ("Body", "Root", (0, 0, 0), (0, 2.30, 0), True),
    ("Spine.01", "Body", (0, -.26, .018), (0, -1.79, .04), True),
    ("Spine.02", "Spine.01", (0, -1.79, .04), (0, -3.24, .025), True),
    ("TailStock", "Spine.02", (0, -3.24, .025), (0, -4.52, .005), True),
    ("Flukes", "TailStock", (0, -4.52, .005), (0, -5.22, .018), True),
    *[(f"Fluke.{side}", "Flukes", (sign * .72, -4.91, .024),
       (sign * 2.20, -5.53, .23), True) for side, sign in SIDES],
    *[(f"Pectoral.{side}", "Body", (sign * 1.30, 1.54, -.345),
       (sign * 2.82, .12, -.725), True) for side, sign in SIDES],
)

# Extremes are separate pose assets with no root motion.
POSES = {
    "Neutral": {},
    "Tail up": {"Spine.02": (12, 0, 0), "TailStock": (34, 0, 0), "Flukes": (15, 0, 0)},
    "Tail down": {"Spine.02": (-12, 0, 0), "TailStock": (-34, 0, 0), "Flukes": (-15, 0, 0)},
    "Bend left": {"Spine.01": (0, 0, -22), "Spine.02": (0, 0, -24), "TailStock": (0, 0, -18)},
    "Bend right": {"Spine.01": (0, 0, 22), "Spine.02": (0, 0, 24), "TailStock": (0, 0, 18)},
    "Rise and trim": {"Body": (18, 0, 0), "TailStock": (-10, 0, 0),
                      "Pectoral.L": (28, -10, 9), "Pectoral.R": (-26, 11, -8)},
    "Dive and trim": {"Body": (-18, 0, 0), "Spine.01": (7, 0, -12),
                      "TailStock": (24, 0, -10), "Flukes": (-11, 0, 0),
                      "Fluke.L": (12, 0, 0), "Fluke.R": (11, 0, 0),
                      "Pectoral.L": (-24, 12, -9), "Pectoral.R": (28, -11, 8)},
}
POSE_NAMES = {name: name.lower().replace(" ", "_") for name in POSES}

FOLLOWERS = [
    ("Companion L", (-4.95, -.72, -.22), .72, -3.0, "Tail up", .24),
    ("Companion R", (5.25, -2.40, -.40), .76, 5.0, "Tail down", .28),
    ("Companion aft L", (-9.15, -2.45, -.30), .58, -3.0, "Bend left", .18),
]
PENDING = [
    "负责人审阅通用鲸灰盒轮廓、鳍根和骨骼操作",
    "WL-ANM-001 慢游循环与过渡，WL-ANM-002 惯性转向",
    "WL-LVL-M12-SAMPLE 固定机位中校准鲸长、队形、近中远取景及海面高程",
    "WL-MAT-001 水彩材质",
    "USDZ / RealityKit 的轴向、材质与动画，以及 iPhone / iPad 显示与性能，待真机验证",
]


def smoothstep(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def interval(value, start, end):
    return smoothstep((value - start) / (end - start))


def spine_weights(y):
    stations = [
        (1.0, "Body"), (-1.02, "Spine.01"), (-2.49, "Spine.02"),
        (-3.85, "TailStock"), (-4.91, "Flukes"),
    ]
    if y >= stations[0][0]:
        return {"Body": 1.0}
    for (front, first), (back, second) in zip(stations, stations[1:]):
        if y >= back:
            t = (y - front) / (back - front)
            alpha = .70 * t + .30 * smoothstep(t)
            return {first: 1 - alpha, second: alpha}
    return {"Flukes": 1.0}


def fin_weights(region, side, point):
    x, y, _ = point
    if region == "Pectoral":
        fin = interval(abs(x), 1.07, 1.97)
        weights = {name: weight * (1 - fin) for name, weight in spine_weights(y).items()}
        weights[f"Pectoral.{side}"] = fin
        return weights
    tip = .88 * interval(abs(x), .72, 1.93)
    return {"Flukes": 1 - tip, f"Fluke.{side}": tip}


class WhaleSurface:
    def __init__(self):
        self.points = []
        self.weights = []
        self.faces = []
        self.uv = []
        self.regions = {}
        self.smooth_junction = set()

    def vertex(self, point, weights):
        self.points.append(Vector(point))
        self.weights.append(weights)
        return len(self.points) - 1

    def face(self, indices, uv):
        self.faces.append(indices)
        self.uv.append(uv)

    def make(self):
        def section(index):
            return next(i for i, row in enumerate(BODY) if row[0] == index)

        ports = [
            (name, side, sign, section(a), section(b), low, high, loft, atlas)
            for name, a, b, low, high, loft, atlas_row in (
                ("Pectoral", .88, 2.18, -4, 0, PECTORAL, .65),
                ("Fluke", -5.14, -4.39, -2, 2, FLUKE, .81),
            )
            for (side, sign), u in zip(SIDES, (.045, .54))
            for atlas in [(u, atlas_row, .41, .125)]
        ]

        def angle_index(j, sign):
            return (j if sign == 1 else SEGMENTS // 2 - j) % SEGMENTS

        holes = set()
        rings = {}
        for region, side, sign, start, end, low, high, _, _ in ports:
            for i in range(start, end):
                for j in range(low, high):
                    a = angle_index(j, sign)
                    b = angle_index(j + 1, sign)
                    holes.add((i, a if sign == 1 else b))

        for i, (y, width, depth, center) in enumerate(BODY[1:-1], 1):
            for j in range(SEGMENTS):
                theta = math.tau * j / SEGMENTS
                # Low dorsal rise gives the broad backs a readable transition to the tail.
                dorsal = .34 * math.exp(-((y + 1.74) / .66)**2)
                dorsal *= math.exp(-((theta - math.pi / 2) / .32)**2)
                p = (width * math.cos(theta), y, center + depth * math.sin(theta) + dorsal)
                rings[i, j] = self.vertex(p, spine_weights(y))

        def body_uv(i, j):
            return (.04 + .92 * (j - 24) / SEGMENTS,
                    .04 + .54 * (BODY[i][0] - BODY[0][0]) / (BODY[-1][0] - BODY[0][0]))

        rear = self.vertex((0, BODY[0][0], BODY[0][3]), {"Flukes": 1.0})
        front = self.vertex((0, BODY[-1][0], BODY[-1][3]), {"Body": 1.0})
        for j in range(24, 24 + SEGMENTS):
            a, b = j % SEGMENTS, (j + 1) % SEGMENTS
            self.face((rear, rings[1, a], rings[1, b]),
                      (body_uv(0, j + .5), body_uv(1, j), body_uv(1, j + 1)))
            for i in range(1, len(BODY) - 2):
                if (i, a) in holes:
                    continue
                self.face((rings[i, a], rings[i, b], rings[i+1, b], rings[i+1, a]),
                          (body_uv(i, j), body_uv(i, j+1), body_uv(i+1, j+1), body_uv(i+1, j)))
            last = len(BODY) - 2
            self.face((rings[last, a], front, rings[last, b]),
                      (body_uv(last, j), body_uv(last + 1, j + .5), body_uv(last, j + 1)))

        for region, side, sign, start, end, low, high, loft, atlas in ports:
            base = []
            phases = []
            # Run around each rectangular port once, matching each quarter of the oval loft.
            corners = ((start, low), (end, low), (end, high), (start, high), (start, low))
            for quarter, ((i0, j0), (i1, j1)) in enumerate(zip(corners, corners[1:])):
                count = abs(i1 - i0) + abs(j1 - j0)
                for step in range(count):
                    t = step / count
                    i = round(i0 + (i1 - i0) * t)
                    j = round(j0 + (j1 - j0) * t)
                    base.append(rings[i, angle_index(j, sign)])
                    phases.append(math.pi / 2 * (quarter + t - 1.5))
            self.graft(region, side, sign, base, phases, loft, atlas)

        # Turn the middle of the trailing edge into a shallow, continuous fluke notch.
        for point in self.points:
            carve = interval(point.y, -4.72, -5.35) * interval(abs(point.x), .66, 0)
            point.y += .30 * carve
            point.z *= 1 - .23 * carve

        used = sorted({index for face in self.faces for index in face})
        remap = {old: new for new, old in enumerate(used)}
        neighbors = {index: set() for index in self.smooth_junction}
        for face in self.faces:
            for a, b in zip(face, face[1:] + face[:1]):
                if a in neighbors:
                    neighbors[a].add(b)
                if b in neighbors:
                    neighbors[b].add(a)
        for _ in range(3):
            for index, point in {
                i: self.points[i].lerp(sum((self.points[j] for j in sorted(adj)), Vector()) / len(adj), .32)
                for i, adj in neighbors.items()
            }.items():
                self.points[index] = point

        mesh = bpy.data.meshes.new("Whale_Surface")
        mesh.from_pydata([tuple(self.points[i]) for i in used], [],
                         [tuple(remap[i] for i in face) for face in self.faces])
        assert not mesh.validate()
        mesh.update()
        uv = mesh.uv_layers.new(name="Whale_Atlas")
        for polygon, coords in zip(mesh.polygons, self.uv):
            for loop_index, coordinate in zip(polygon.loop_indices, coords):
                uv.uv[loop_index].vector = coordinate
        with_bmesh = bmesh.new()
        with_bmesh.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(with_bmesh, faces=list(with_bmesh.faces))
        assert all(edge.is_manifold for edge in with_bmesh.edges)
        assert with_bmesh.calc_volume(signed=True) > 0
        with_bmesh.to_mesh(mesh)
        with_bmesh.free()
        mesh.update()
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        patches = {name: [remap[i] for i in indices] for name, indices in self.regions.items()}
        return mesh, [self.weights[i] for i in used], patches

    def graft(self, region, side, sign, base, phases, loft, atlas):
        name = f"{region}.{side}"
        self.regions[name] = base.copy()
        self.smooth_junction.update(base)
        for index in base:
            point = self.points[index]
            if region == "Pectoral":
                self.weights[index] = fin_weights(region, side, point)

        previous = base
        count = len(base)
        u, v, width, height = atlas

        def uv(i, j):
            return (u + width * j / count, v + height * i / len(loft))

        for ring, (x, y, chord, thickness, z, camber) in enumerate(loft, 1):
            if ring == len(loft):
                tip = (sign * x, y, z)
                pole = self.vertex(tip, fin_weights(region, side, tip))
                for j in range(count):
                    a, b = previous[j], previous[(j + 1) % count]
                    self.face((a, b, pole), (uv(ring - 1, j), uv(ring - 1, j + 1), uv(ring, j + .5)))
                continue

            current = []
            for angle, base_index in zip(phases, base):
                chord_phase = math.cos(angle)
                px = x
                if ring <= 2:
                    # A laterally curved collar seats cleanly on the oval body.
                    rim_x = abs(self.points[base_index].x)
                    px = max(rim_x + .052, x + (rim_x - x) * (.62 if ring == 1 else .21))
                point = (sign * px, y + chord * chord_phase,
                         z + thickness * math.sin(angle) * (.92 + .18 * chord_phase)
                         + camber * chord_phase)
                current.append(self.vertex(point, fin_weights(region, side, point)))
            if ring <= 2:
                self.regions[name].extend(current)
            if ring == 1:
                self.smooth_junction.update(current)
            for j in range(count):
                next_j = (j + 1) % count
                self.face((previous[j], previous[next_j], current[next_j], current[j]),
                          (uv(ring - 1, j), uv(ring - 1, j + 1), uv(ring, j + 1), uv(ring, j)))
            previous = current


def add_collection(scene, name):
    collection = bpy.data.collections.new(name)
    scene.collection.children.link(collection)
    return collection


def add_object(collection, name, data):
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    return obj


def add_material():
    material = bpy.data.materials.new("Whale · slate graybox")
    material.diffuse_color = (.225, .273, .31, 1.0)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = material.diffuse_color
    shader.inputs["Roughness"].default_value = .56
    return material


def make_character(collection):
    mesh, weights, patches = WhaleSurface().make()
    rig = add_object(collection, "WhaleRig", bpy.data.armatures.new("Whale_Skeleton"))
    rig.show_in_front = True
    rig.data.display_type = "OCTAHEDRAL"
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    bones = rig.data.edit_bones
    for name, parent, head, tail, deform in BONES:
        bone = bones.new(name)
        bone.head, bone.tail = head, tail
        bone.use_deform = deform
        if parent:
            bone.parent = bones[parent]
            bone.use_connect = (bone.head - bone.parent.tail).length < 1e-5
        bone.align_roll(Vector((0, 0, 1)))
    bpy.ops.object.mode_set(mode="OBJECT")
    torso = rig.data.collections.new("Root & Body")
    tail = rig.data.collections.new("Spine & Tail")
    fins = rig.data.collections.new("Pectorals")
    for bone in rig.data.bones:
        if bone.name in ("Root", "Body"):
            torso.assign(bone)
        elif bone.name.startswith("Pectoral"):
            fins.assign(bone)
        else:
            tail.assign(bone)

    # Give the coincident Root and Body heads separate viewport handles.
    ring = bpy.data.meshes.new("Root control outline")
    outline = [(1.2 * math.cos(i * math.tau / 48), 1.2 * math.sin(i * math.tau / 48), 0)
               for i in range(48)]
    ring.from_pydata(outline, [(i, (i + 1) % 48) for i in range(48)], [])
    shape = bpy.data.objects.new("Root control outline · viewport", ring)
    root = rig.pose.bones["Root"]
    root.custom_shape = shape
    root.use_custom_shape_bone_size = False

    obj = add_object(collection, "Whale_LOD0", mesh)
    obj.parent = rig
    mesh.materials.append(add_material())
    groups = {name: obj.vertex_groups.new(name=name) for name, _, _, _, deform in BONES if deform}
    for i, weights_at_point in enumerate(weights):
        kept = {name: value for name, value in weights_at_point.items() if value > .0001}
        total = sum(kept.values())
        for name, value in kept.items():
            groups[name].add([i], value / total, "REPLACE")
    modifier = obj.modifiers.new("Whale skin", "ARMATURE")
    modifier.object = rig
    modifier.use_deform_preserve_volume = False
    rig["asset_id"] = ASSET
    rig["pose_assets"] = "Pose Mode > Asset Browser > Current File > QA"
    return obj, rig, patches


def set_pose(rig, rotations, factor=1.0):
    for bone in rig.pose.bones:
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = [math.radians(value * factor) for value in rotations.get(bone.name, (0, 0, 0))]
    bpy.context.view_layer.update()


def make_pose_assets(rig):
    for name, rotations in POSES.items():
        set_pose(rig, rotations)
        for bone in rig.pose.bones:
            if bone.name != "Root":
                bone.keyframe_insert(data_path="rotation_euler", frame=1, group=bone.name)
        action = rig.animation_data.action
        action.name = f"QA · {name}"
        action.use_fake_user = True
        action.asset_mark()
        action.asset_data.description = f"{ASSET}/v001 single-frame skinning test"
        rig.animation_data.action = None
    set_pose(rig, {})


def add_camera(collection, name, eye, target, ortho=None):
    camera = add_object(collection, name, bpy.data.cameras.new(name))
    camera.location = eye
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    if direction.x == direction.y == 0 and direction.z < 0:
        camera.rotation_euler = (0, 0, 0)
    if ortho:
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = ortho
    else:
        camera.data.sensor_fit = "VERTICAL"
        camera.data.lens_unit = "FOV"
        camera.data.angle = math.radians(GAME_FOV)
    return camera


def add_backdrop(scene):
    world = bpy.data.worlds.new("Whale · neutral studio")
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    ambient = nodes.get("Background")
    ambient.inputs["Color"].default_value = (.41, .50, .62, 1)
    ambient.inputs["Strength"].default_value = .43
    backdrop = nodes.new("ShaderNodeBackground")
    backdrop.inputs["Color"].default_value = (.080, .115, .150, 1)
    backdrop.inputs["Strength"].default_value = .92
    mix = nodes.new("ShaderNodeMixShader")
    light_path = nodes.new("ShaderNodeLightPath")
    links.new(light_path.outputs["Is Camera Ray"], mix.inputs[0])
    links.new(ambient.outputs[0], mix.inputs[1])
    links.new(backdrop.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], nodes.get("World Output").inputs["Surface"])


def make_studio(scene):
    guides = add_collection(scene, f"GUIDE_{ASSET}")
    add_backdrop(scene)
    for name, position, color, energy, size in (
        ("Key", (-5, -3, 11), (.91, .95, 1), 1750, 8),
        ("Rim", (2, 7, 8), (.78, .88, 1), 2000, 8),
        ("Fill", (7, -5, 4), (1, .91, .79), 710, 9),
    ):
        light = add_object(guides, name, bpy.data.lights.new(name, "AREA"))
        light.location = position
        light.rotation_euler = (-light.location).to_track_quat("-Z", "Y").to_euler()
        light.data.energy, light.data.shape, light.data.size = energy, "DISK", size
        light.data.color = color

    game_eye = (0, -GAME_CAMERA_DISTANCE * math.cos(GAME_PITCH) / UNITS_PER_BU,
                GAME_CAMERA_DISTANCE * math.sin(GAME_PITCH) / UNITS_PER_BU)
    fixed = add_camera(guides, "Review · fixed gameplay", game_eye, (0, 0, 6 / UNITS_PER_BU))
    close = add_camera(guides, "Review · rear detail", (6.4, -8.65, 6.25), (0, -.22, 0))
    side = add_camera(guides, "Review · right profile", (16, -.25, .1), (0, -.25, .1), 12.6)
    top = add_camera(guides, "Review · top +Y up", (0, -.28, 18), (0, -.28, 0), 12.8)
    wide_top = add_camera(guides, "Review · top bend", (0, -.12, 18), (0, -.12, 0), 14.4)
    bank = add_camera(guides, "Review · fin trim", (8.4, -8.5, 8.2), (0, -.4, 0), 13.9)
    add_camera(guides, "Review · side stroke", (16, -.35, 0), (0, -.35, 0), 13.2)
    return guides, {"fixed": fixed, "rear": close, "side": side, "top": top,
                    "top_bend": wide_top, "trim": bank, "stroke": guides.objects["Review · side stroke"]}


def configure_scene(scene):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 20
    scene.cycles.use_denoising = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 45
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "AgX"
    scene.unit_settings.system = "NONE"


def render(scene, camera, path, size):
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.filepath = str(path)
    bpy.ops.render.render(scene=scene.name, write_still=True)


def make_pod(source, guides, character, rig, camera):
    pod = bpy.data.scenes.new("02 · Fixed camera pod")
    pod.world = source.world
    configure_scene(pod)
    pod.collection.children.link(guides)
    staging = add_collection(pod, f"GUIDE_{ASSET}_POD")
    bpy.context.window.scene = pod

    def instance(name, location, scale, yaw, pose, strength):
        new_rig = rig.copy()
        new_rig.name = f"{name} rig · preview"
        staging.objects.link(new_rig)
        new_rig.animation_data_clear()
        new_rig.location = location
        new_rig.scale = (scale,) * 3
        new_rig.rotation_euler.z = math.radians(yaw)
        new_rig.show_in_front = False
        mesh = character.copy()
        mesh.name = f"{name} · shared mesh"
        staging.objects.link(mesh)
        mesh.parent = new_rig
        mesh.modifiers[0].object = new_rig
        set_pose(new_rig, POSES[pose], strength)
        return mesh

    instances = [instance("Leader", (0, 0, 0), 1, 0, "Neutral", 1)]
    instances.extend(instance(*settings) for settings in FOLLOWERS)
    assert all(obj.data == character.data and obj.parent.data == rig.data for obj in instances)
    pod.camera = camera
    pod.render.resolution_x, pod.render.resolution_y = GAME_CAMERA_SIZE
    bpy.context.view_layer.update()
    return pod, instances


def mesh_points(obj, evaluated=False):
    if evaluated:
        obj = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return np.array([tuple(vertex.co) for vertex in obj.data.vertices])


def bounds(points):
    return [points.min(axis=0).tolist(), points.max(axis=0).tolist()]


def validate_surface(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    assert all(triangle.area > 1e-8 for triangle in mesh.loop_triangles)
    edges = {tuple(edge.vertices): i for i, edge in enumerate(mesh.edges)}
    hits = np.bincount([loop.edge_index for loop in mesh.loops], minlength=len(edges))
    assert np.all(hits == 2)
    connected = {0}
    pending = [0]
    adjacent = [[] for _ in mesh.vertices]
    for a, b in edges:
        adjacent[a].append(b)
        adjacent[b].append(a)
    while pending:
        for vertex in adjacent[pending.pop()]:
            if vertex not in connected:
                connected.add(vertex)
                pending.append(vertex)
    assert len(connected) == len(mesh.vertices)
    weights = [[g.weight for g in vertex.groups] for vertex in mesh.vertices]
    weight_error = max(abs(sum(w) - 1) for w in weights)
    assert all(0 < len(w) <= 4 for w in weights) and weight_error < 1e-6
    uv = mesh.uv_layers.active.uv
    assert all(0 <= value <= 1 for loop in uv for value in loop.vector)
    assert all(abs((uv[b].vector - uv[a].vector).cross(uv[c].vector - uv[a].vector)) > 1e-9
               for a, b, c in (tri.loops for tri in mesh.loop_triangles))
    return {"connected_components": 1, "vertices": len(mesh.vertices),
            "faces": len(mesh.polygons), "triangles": len(mesh.loop_triangles),
            "boundary_or_non_manifold_edges": int(np.sum(hits != 2)),
            "minimum_triangle_area_BU2": min(t.area for t in mesh.loop_triangles),
            "weight_sum_max_error": weight_error, "max_weights_per_vertex": max(map(len, weights)),
            "uv_atlas": "Whale_Atlas"}


def validate_poses(obj, rig, patches):
    rest = mesh_points(obj)
    triangles = np.array([tuple(t.vertices) for t in obj.data.loop_triangles])
    edges = np.array([tuple(e.vertices) for e in obj.data.edges])
    edge_length = np.linalg.norm(rest[edges[:, 1]] - rest[edges[:, 0]], axis=1)

    def areas(points):
        a, b, c = (points[triangles[:, i]] for i in range(3))
        return np.linalg.norm(np.cross(b - a, c - a), axis=1) * .5

    rest_area = areas(rest)
    patch_edges = {name: np.all(np.isin(edges, ids), axis=1) for name, ids in patches.items()}
    tail_edges = np.all((rest[edges, 1] < -3.25) & (rest[edges, 1] > -4.40), axis=1)
    patch_edges["TailStock"] = tail_edges
    cap = np.argmin(rest[:, 1] + np.abs(rest[:, 0]) * 3)
    reports = {}
    triangle_vertex_sets = [set(vertices) for vertices in triangles.tolist()]
    for name, rotations in POSES.items():
        set_pose(rig, rotations)
        posed = mesh_points(obj, evaluated=True)
        assert np.isfinite(posed).all()
        tree = BVHTree.FromPolygons(posed.tolist(), triangles.tolist(), all_triangles=True)
        collision = [(a, b) for a, b in tree.overlap(tree)
                     if a < b and triangle_vertex_sets[a].isdisjoint(triangle_vertex_sets[b])]
        posed_areas = areas(posed)
        ratios = posed_areas / rest_area
        stretches = np.linalg.norm(posed[edges[:, 1]] - posed[edges[:, 0]], axis=1) / edge_length
        reports[name] = {
            "root_BU": list(rig.pose.bones["Root"].head),
            "local_euler_XYZ_deg": rotations,
            "tail_center_delta_BU": (posed[cap] - rest[cap]).tolist(),
            "self_intersections_non_neighbor_triangle_pairs": len(collision),
            "minimum_triangle_area_ratio": float(ratios.min()),
            "junction_edge_length_ratios": {
                patch: [float(stretches[mask].min()), float(stretches[mask].max())]
                for patch, mask in patch_edges.items()},
        }
        print(f"QA {name}: {reports[name]}", flush=True)
    set_pose(rig, {})
    for report in reports.values():
        assert Vector(report["root_BU"]).length < 1e-6
        assert report["self_intersections_non_neighbor_triangle_pairs"] == 0
        assert report["minimum_triangle_area_ratio"] > .35
        assert all(.55 < lo < 1.5 and hi < 1.55 for lo, hi in report["junction_edge_length_ratios"].values())
    return reports


def export_glb(obj, rig, folder):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    path = folder / f"{STEM}.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_yup=True, export_animations=False)
    return path


def verify_glb_json(path, obj, rig):
    payload = path.read_bytes()
    magic, version, declared_size, json_size, chunk = struct.unpack_from("<4sIII4s", payload)
    assert (magic, version, declared_size, chunk) == (b"glTF", 2, len(payload), b"JSON")
    doc = json.loads(payload[20:20+json_size])
    mesh, = doc["meshes"]
    skin, = doc["skins"]
    primitive, = mesh["primitives"]
    nodes = doc["nodes"]
    joints = {nodes[i]["name"] for i in skin["joints"]}
    assert joints == set(rig.data.bones.keys())
    assert not any(doc.get(key) for key in ("animations", "cameras", "images", "extensionsRequired"))
    assert not any(node["name"].startswith(("Review", "Companion", "Leader")) for node in nodes)
    mesh_node, = [node for node in nodes if "mesh" in node]
    assert mesh_node.get("translation", [0, 0, 0]) == [0, 0, 0]
    assert mesh_node.get("scale", [1, 1, 1]) == [1, 1, 1]
    assert mesh_node.get("rotation", [0, 0, 0, 1]) == [0, 0, 0, 1]
    root, = [node for node in nodes if node["name"] == "Root"]
    assert Vector(root.get("translation", (0, 0, 0))).length < 1e-6
    attributes = primitive["attributes"]
    assert {"POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"} <= set(attributes)
    assert doc["accessors"][primitive["indices"]]["count"] // 3 == len(obj.data.loop_triangles)
    position = doc["accessors"][attributes["POSITION"]]
    mapped = np.array([(v.co.x, v.co.z, -v.co.y) for v in obj.data.vertices])
    np.testing.assert_allclose([position["min"], position["max"]], bounds(mapped), atol=1e-6, rtol=0)
    return {"meshes": len(doc["meshes"]), "skins": len(doc["skins"]), "joints": len(joints),
            "triangles": doc["accessors"][primitive["indices"]]["count"] // 3,
            "bounds_gltf": [position["min"], position["max"]],
            "position_count": position["count"], "animations": 0, "textures": 0}


def roundtrip(source, obj, rig, path, guides, camera, output):
    scene = bpy.data.scenes.new("GLB round trip · initially empty")
    bpy.context.window.scene = scene
    assert not scene.objects
    bpy.ops.import_scene.gltf(filepath=str(path), bone_heuristic="BLENDER", disable_bone_shape=True)
    imported, = [o for o in scene.objects if o.type == "MESH"]
    imported_rig, = [o for o in scene.objects if o.type == "ARMATURE"]
    assert len(scene.objects) == 2
    identity = np.eye(4)
    for instance in (imported, imported_rig):
        np.testing.assert_allclose(instance.matrix_world, identity, atol=2e-6)
        assert all(abs(a - 1) < 2e-6 for a in instance.scale)
    assert imported.parent == imported_rig
    assert [m.object for m in imported.modifiers if m.type == "ARMATURE"] == [imported_rig]
    assert imported_rig.data.bones["Root"].head_local.length < 1e-6
    assert set(imported_rig.data.bones.keys()) == set(rig.data.bones.keys())
    rest_matrix_error = 0.0
    for bone in rig.data.bones:
        other = imported_rig.data.bones[bone.name]
        assert (bone.parent and bone.parent.name) == (other.parent and other.parent.name)
        delta = np.abs(np.array(bone.matrix_local) - np.array(other.matrix_local)).max()
        rest_matrix_error = max(rest_matrix_error, float(delta))
    assert rest_matrix_error < 2e-5

    kd = KDTree(len(obj.data.vertices))
    for vertex in obj.data.vertices:
        kd.insert(vertex.co, vertex.index)
    kd.balance()

    def weights_for(mesh_obj, index):
        return {mesh_obj.vertex_groups[group.group].name: group.weight
                for group in mesh_obj.data.vertices[index].groups if group.weight > 1e-8}

    def point_uvs(mesh_obj):
        result = {}
        for loop, uv in zip(mesh_obj.data.loops, mesh_obj.data.uv_layers.active.uv):
            result.setdefault(loop.vertex_index, set()).add(tuple(uv.vector))
        return result

    original_uvs = point_uvs(obj)
    imported_uvs = point_uvs(imported)
    matched = []
    rest_error = weight_error = uv_error = 0.0
    for vertex in imported.data.vertices:
        _, index, distance = kd.find(imported.matrix_world @ vertex.co)
        matched.append(index)
        actual, expected = weights_for(imported, vertex.index), weights_for(obj, index)
        assert actual
        rest_error = max(rest_error, distance)
        weight_error = max(weight_error, *(abs(actual.get(k, 0) - expected.get(k, 0))
                                           for k in actual.keys() | expected.keys()))
        for uv in imported_uvs[vertex.index]:
            uv_error = max(uv_error, min(math.dist(uv, prior) for prior in original_uvs[index]))
    assert len(set(matched)) == len(obj.data.vertices)
    assert rest_error < 2e-6 and weight_error < 2e-5 and uv_error < 2e-6
    imported.data.calc_loop_triangles()
    assert len(imported.data.loop_triangles) == len(obj.data.loop_triangles)
    expected_shader = obj.data.materials[0].node_tree.nodes.get("Principled BSDF")
    actual_shader = imported.data.materials[0].node_tree.nodes.get("Principled BSDF")
    for socket in ("Base Color", "Metallic", "Roughness"):
        np.testing.assert_allclose(expected_shader.inputs[socket].default_value,
                                   actual_shader.inputs[socket].default_value, atol=2e-6)

    pose_error = {}
    for name, rotations in POSES.items():
        bpy.context.window.scene = source
        set_pose(rig, rotations)
        expected = mesh_points(obj, evaluated=True)[matched]
        bpy.context.window.scene = scene
        set_pose(imported_rig, rotations)
        actual = mesh_points(imported, evaluated=True)
        delta = float(np.max(np.linalg.norm(expected - actual, axis=1)))
        pose_error[name] = delta
        assert delta < 3e-5, (name, delta)

    set_pose(imported_rig, {})
    scene.collection.children.link(guides)
    scene.world = source.world
    configure_scene(scene)
    render(scene, camera, output / "preview_glb_roundtrip.png", (1100, 760))
    bpy.context.window.scene = source
    set_pose(rig, {})
    bpy.data.scenes.remove(scene)
    for item in (imported, imported_rig):
        bpy.data.objects.remove(item, do_unlink=True)
    return {"initial_scene_object_count": 0, "imported_object_count": 2,
            "object_world_transforms": "identity", "root_BU": [0, 0, 0],
            "hierarchy": {name: parent for name, parent, *_ in BONES},
            "imported_vertices": len(matched), "bone_rest_matrix_max_error": rest_matrix_error,
            "vertex_position_max_error_BU": rest_error, "weight_max_error": weight_error,
            "uv_max_error": uv_error, "pose_deformation_max_error_BU": pose_error,
            "passed": True}


def projection_summary(scene, camera, objects):
    width, height = GAME_CAMERA_SIZE
    result = {}
    camera_frame = camera.data.view_frame(scene=scene)
    near = -camera_frame[0].z
    vertical_fov = 2 * math.degrees(math.atan(abs(camera_frame[0].y) / near))
    assert abs(vertical_fov - GAME_FOV) < 1e-4, vertical_fov
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        uv = np.array([tuple(world_to_camera_view(scene, camera, evaluated.matrix_world @ v.co))
                       for v in evaluated.data.vertices])
        assert uv[:, 2].min() > 0
        frame = uv[:, :2]
        assert frame.min() > 0 and frame.max() < 1, (obj.name, bounds(frame))
        local = mesh_points(obj)
        nose = np.argmax(local[:, 1])
        fluke_center = np.argmin(local[:, 1] + np.abs(local[:, 0]) * 3)
        separation = float((frame[nose, 1] - frame[fluke_center, 1]) * height)
        assert separation > 0, (obj.name, separation)
        result[obj.name] = {"bounds_screen01_origin_lower_left": bounds(frame),
                            "width_px": float(np.ptp(frame[:, 0]) * width),
                            "height_px": float(np.ptp(frame[:, 1]) * height),
                            "nose_above_tail_center_px": separation}
    return result


def json_file(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(output):
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    source = bpy.context.scene
    source.name = "01 · Whale master"
    configure_scene(source)
    export = add_collection(source, f"EXPORT_{ASSET}")
    obj, rig, patches = make_character(export)
    guides, cameras = make_studio(source)
    make_pose_assets(rig)
    stats = validate_surface(obj)
    checks = validate_poses(obj, rig, patches)
    corners = bounds(mesh_points(obj))
    path = export_glb(obj, rig, output)
    wire = verify_glb_json(path, obj, rig)
    reimport = roundtrip(source, obj, rig, path, guides, cameras["rear"], output)

    previews = {
        "fixed_gameplay": "preview_gameplay.png",
        "fixed_gameplay_pod": "preview_gameplay_pod.png",
        "near_rear_review": "preview_rear_detail.png",
        "right_profile": "preview_side.png",
        "top": "preview_top.png",
        "empty_scene_glb_reimport": "preview_glb_roundtrip.png",
    }
    render(source, cameras["fixed"], output / previews["fixed_gameplay"], GAME_CAMERA_SIZE)
    fixed_solo = projection_summary(source, cameras["fixed"], [obj])
    for view, size, camera in (
        ("near_rear_review", (1100, 760), "rear"),
        ("right_profile", (1320, 620), "side"),
        ("top", (780, 1120), "top"),
    ):
        render(source, cameras[camera], output / previews[view], size)
    pose_previews = {}
    for pose, camera in (
        ("Tail up", "stroke"), ("Tail down", "stroke"), ("Bend left", "top_bend"),
        ("Bend right", "top_bend"), ("Rise and trim", "trim"), ("Dive and trim", "trim"),
    ):
        set_pose(rig, POSES[pose])
        filename = f"preview_pose_{POSE_NAMES[pose]}.png"
        render(source, cameras[camera], output / filename, (1000, 850))
        pose_previews[pose] = filename

    set_pose(rig, {})
    pod, instances = make_pod(source, guides, obj, rig, cameras["fixed"])
    fixed_pod = projection_summary(pod, cameras["fixed"], instances)
    render(pod, cameras["fixed"], output / previews["fixed_gameplay_pod"], GAME_CAMERA_SIZE)
    bpy.context.window.scene = source
    source.camera = cameras["fixed"]
    source.render.resolution_x, source.render.resolution_y = GAME_CAMERA_SIZE
    source.render.filepath = "//preview_gameplay.png"
    pod.render.filepath = "//preview_gameplay_pod.png"

    # Keep a clean editable rest state, with the review collection one click away.
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.shading.type = "SOLID"
                space.shading.color_type = "MATERIAL"
                space.shading.show_cavity = True
                space.overlay.show_overlays = False
                region = space.region_3d
                region.view_distance = 14.3
                region.view_location = (0, -.15, 0)
                region.view_rotation = cameras["rear"].rotation_euler.to_quaternion()
                region.view_perspective = "PERSP"
    guide_text = bpy.data.texts.new("WL-CHR-001 · Editing and QA")
    guide_text.write(
        "WL-CHR-001 / v001\n"
        "01 · Whale master: Whale_LOD0 + WhaleRig in EXPORT_WL-CHR-001.\n"
        "Use the viewport Overlays icon to see the bones.\n"
        "Select WhaleRig, enter Pose Mode, then use Current File > QA in the Asset Browser.\n"
        "Each QA action contains one test pose at frame 1. Neutral clears the pose.\n"
        "02 · Fixed camera pod: four preview objects share Whale_Surface and Whale_Skeleton.\n"
        "The render camera is fixed directly behind and above the leader, looking +Y.\n"
        "Graybox dimensions and the review-only camera ratios are in asset_manifest.json.\n"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output / f"{STEM}.blend"), compress=True)

    camera = cameras["fixed"]
    camera_details = {"resolution": GAME_CAMERA_SIZE, "projection": "perspective, directly behind leader",
                      "eye_BU": list(camera.location), "target_BU": [0, 0, .6],
                      "vertical_fov_deg": GAME_FOV,
                      "actual_down_angle_deg": math.degrees(math.atan2(camera.location.z - .6, -camera.location.y)),
                      "ThirdPersonRig_parameters": {"distance_game_units": GAME_CAMERA_DISTANCE,
                                                     "pitch_rad": GAME_PITCH,
                                                     "target_height_game_units": 6.0},
                      "review_only_game_units_per_BU": UNITS_PER_BU,
                      "water_plane_BU": None,
                      "water_plane_note": "预览使用无水面的中性棚拍。海面高程由 WL-LVL-M12-SAMPLE 校准。"}
    generated_files = [f"{STEM}.blend", f"{STEM}.glb", *previews.values(), *pose_previews.values()]
    manifest = {
        "id": ASSET, "version": "v001", "status": "needs_review", "kind": "rigged_mesh",
        "blender": bpy.app.version_string,
        "source": "项目原创 Blender Python 灰盒造型、拓扑、骨架、权重与棚拍。",
        "rights": "项目内原创制作。无外部模型、图像、贴图或署名要求。",
        "dependencies": [],
        "reference": ["docs/adr/0003-realitykit-third-person.md",
                      "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift",
                      "完整AI建模任务包/Whale/羽与潮_鲸_Blender资源制作规格书_v1.0.md"],
        "files": {"blend": f"{STEM}.blend", "glb": f"{STEM}.glb", "script": f"{STEM}_generate.py",
                  "qa": "qa.json", "previews": previews, "pose_previews": pose_previews},
        "sha256": {**{name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                       for name in generated_files},
                   f"{STEM}_generate.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "axes_blender": {"right": "+X", "forward": "+Y", "up": "+Z"},
        "axes_glb": {"right": "+X", "forward": "-Z", "up": "+Y"},
        "blender_to_glb": "(x, y, z) → (x, z, -y)",
        "pivot_BU": [0, 0, 0], "object_scale": [1, 1, 1],
        "bounds_BU": corners,
        "dimensions_BU": dict(zip(("width_X", "length_Y", "height_Z"), np.diff(corners, axis=0)[0].tolist())),
        "collections": {"export": f"EXPORT_{ASSET}", "export_objects": [obj.name, rig.name],
                        "guide": guides.name, "pod": f"GUIDE_{ASSET}_POD"},
        "surface": stats,
        "bones": {bone.name: {
            "parent": bone.parent.name if bone.parent else None, "deform": bone.use_deform,
            "connected": bone.use_connect, "head_BU": list(bone.head_local), "tail_BU": list(bone.tail_local),
            "local_axes_in_blender": {letter: list(bone.matrix_local.to_3x3().col[i])
                                      for i, letter in enumerate("XYZ")}}
                  for bone in rig.data.bones},
        "control_notes": {"Root": "母版原点。测试姿势均原地。", "Body": "局部 X 浮潜俯仰。",
                          "Spine.01 / Spine.02": "局部 Z 侧弯，局部 X 可分担尾摆。",
                          "TailStock / Flukes": "局部 X 抬降尾轴。",
                          "Fluke.L / Fluke.R": "外侧尾鳍微调。",
                          "Pectoral.L / Pectoral.R": "胸鳍摆角和轴向调姿。"},
        "attachment_points": {"runtime_empty_count": 0, "joints": "Use the named bone heads recorded above."},
        "material": "单槽纯色 PBR，预留无重叠 UV 岛。正式材质由 WL-MAT-001 接续。",
        "pose_assets": [f"QA · {name}" for name in POSES],
        "gameplay_preview": camera_details,
        "pod_instances": [{"name": "Leader", "origin_BU": [0, 0, 0], "scale": 1, "yaw_deg": 0},
                          *[{"name": name, "origin_BU": p, "scale": s, "yaw_deg": yaw,
                             "test_pose": pose, "pose_factor": factor}
                            for name, p, s, yaw, pose, factor in FOLLOWERS]],
        "pending": PENDING,
    }
    json_file(output / "asset_manifest.json", manifest)
    json_file(output / "qa.json", {
        "id": ASSET, "version": "v001", "blender": bpy.app.version_string,
        "date_local": "2026-11-16", "timezone": "Asia/Shanghai",
        "status": "needs_review", "scope": "Blender 离线灰盒",
        "surface": stats, "poses": checks, "wire_GLTF": wire, "GLB_roundtrip_empty_scene": reimport,
        "fixed_camera": {**camera_details, "solo": fixed_solo,
                         "pod": fixed_pod, "shared_mesh_datablocks": 1, "shared_rig_datablocks": 1},
        "pending": PENDING,
    })
    print(f"{ASSET} output: {output}", flush=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) != 1:
        raise SystemExit("Usage: blender -b --factory-startup --python-exit-code 1 --python script.py -- OUTPUT_DIR")
    main(Path(args[0]).expanduser().resolve())
