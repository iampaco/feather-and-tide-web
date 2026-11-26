"""Build three original reindeer silhouettes on one skinned watercolor mesh."""

from math import acos, atan2, cos, hypot, pi, sin
from pathlib import Path

import bpy
from mathutils import Vector


SOURCE = Path(__file__).resolve().parent
OUTPUT = SOURCE.parents[5] / "public/assets/reindeer"
OUTPUT.mkdir(parents=True, exist_ok=True)
TURN = 2 * pi

BACK = (0.16, 0.082, 0.043)
AMBER = (0.41, 0.23, 0.115)
FLANK = (0.29, 0.17, 0.10)
RUFF = (0.77, 0.59, 0.41)
TAIL = (0.84, 0.72, 0.53)
INK = (0.049, 0.031, 0.026)
HORN = (0.43, 0.28, 0.156)
BONE = (0.76, 0.61, 0.39)
EAR = (0.37, 0.19, 0.14)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
armature = bpy.data.armatures.new("Reindeer skeleton")
rig = bpy.data.objects.new("Reindeer rig", armature)
bpy.context.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")


def add_bone(name, head, tail, parent=None):
    bone = armature.edit_bones.new(name)
    bone.head, bone.tail = head, tail
    if parent:
        bone.parent = armature.edit_bones[parent]


add_bone("Body", (0, 0, 0), (0, 0, 1))
add_bone("Neck", (0, -0.47, 1.24), (0, -0.76, 1.78), "Body")

legs = {}
for front, end in [(True, "F"), (False, "H")]:
    for side, direction in [(-1, "L"), (1, "R")]:
        code = end + direction
        x, y = side * (0.222 if front else 0.24), -0.53 if front else 0.58
        hip = (x, y, 1.16)
        knee = (x, y + (0.14 if front else -0.19), 0.63)
        ankle = (x, y + (0.035 if front else 0.08), 0.15)
        upper, lower, foot = ["Leg_" + code, "Shin_" + code, "Hoof_" + code]
        add_bone(upper, hip, knee, "Body")
        add_bone(lower, knee, ankle, upper)
        add_bone(foot, ankle, (x, ankle[1] - 0.13, 0.04), lower)
        legs[code] = (hip, knee, ankle, upper, lower, foot, front)
bpy.ops.object.mode_set(mode="OBJECT")


def blend(a, b, amount):
    return tuple(x + (y - x) * amount for x, y in zip(a, b))


def smooth(low, high, x):
    t = max(0, min(1, (x - low) / (high - low)))
    return t * t * (3 - 2 * t)


positions = []
faces = []
colors = []
skin_weights = []
regions = []


def loft(sections, sides, pigment, weights, region, across=(1, 0, 0)):
    """Loft tapered, capped sections along a centerline with continuous normals."""
    start = len(positions)
    centerline = [Vector(item[0]) for item in sections]
    for ring, (center, width, depth) in enumerate(sections):
        center = centerline[ring]
        tangent = (centerline[min(len(sections) - 1, ring + 1)] -
                   centerline[max(0, ring - 1)]).normalized()
        cross = Vector(across)
        horizontal = (cross - tangent * tangent.dot(cross)).normalized()
        upright = tangent.cross(horizontal)
        for point in range(sides):
            angle = TURN * point / sides
            stroke = cos(3 * angle + ring * 0.55) * 0.018
            position = center + horizontal * (cos(angle) * width * (1 + stroke))
            position += upright * (sin(angle) * depth * (1 + stroke))
            positions.append(tuple(position))
            color = pigment(position, ring, angle)
            colors.append(tuple(max(0, channel * (1 + stroke * 2.2)) for channel in color))
            skin_weights.append(weights(ring))
            regions.append(region)
        if ring:
            prior = start + (ring - 1) * sides
            current = prior + sides
            for point in range(sides):
                next_point = (point + 1) % sides
                faces.append((prior + point, prior + next_point, current + next_point,
                              current + point))
    faces.append(tuple(start + i for i in reversed(range(sides))))
    end = start + (len(sections) - 1) * sides
    faces.append(tuple(end + i for i in range(sides)))


def joint(name):
    return lambda _ring: ((name, 1),)


def coat(point, _ring, angle):
    x, y, z = point
    upper = smooth(0.13, 0.95, sin(angle))
    ruff = (1 - smooth(-0.72, -0.36, y)) * (1 - smooth(0.25, 0.86, sin(angle)))
    ruff *= smooth(-1.00, -0.77, y)
    rump = smooth(0.74, 1.01, y) * (1 - smooth(0.50, 0.97, sin(angle)))
    cheek = (1 - smooth(-1.27, -1.07, y)) * (1 - smooth(1.79, 1.96, z))
    color = blend(FLANK, BACK, upper * 0.73)
    shoulder = (1 - smooth(0.12, 0.59, abs(y + 0.52))) * (1 - upper)
    color = blend(color, AMBER, shoulder * 0.57)
    color = blend(color, RUFF, max(ruff * 0.9, cheek * 0.7))
    patch = rump * (1 - smooth(0.16, 0.39, abs(x))) * 0.96
    return blend(color, TAIL, patch)


coat_sections = [
    ((0, 1.04, 1.27), 0.035, 0.079),
    ((0, 0.91, 1.25), 0.22, 0.25),
    ((0, 0.69, 1.23), 0.35, 0.36),
    ((0, 0.42, 1.22), 0.375, 0.40),
    ((0, 0.08, 1.22), 0.336, 0.385),
    ((0, -0.26, 1.24), 0.38, 0.425),
    ((0, -0.49, 1.30), 0.35, 0.365),
    ((0, -0.63, 1.43), 0.27, 0.29),
    ((0, -0.69, 1.59), 0.24, 0.245),
    ((0, -0.76, 1.76), 0.23, 0.23),
    ((0, -0.87, 1.90), 0.222, 0.205),
    ((0, -1.03, 1.89), 0.195, 0.176),
    ((0, -1.16, 1.79), 0.15, 0.135),
    ((0, -1.33, 1.74), 0.122, 0.086),
    ((0, -1.385, 1.745), 0.088, 0.050),
]


def neck_weights(ring):
    flex = smooth(5, 9, ring)
    return (("Body", 1 - flex), ("Neck", flex))


loft(coat_sections, 16, coat, neck_weights, "coat")
loft([((0, 0.93, 1.48), 0.083, 0.06),
      ((0, 1.07, 1.41), 0.101, 0.062),
      ((0, 1.15, 1.31), 0.045, 0.034),
      ((0, 1.18, 1.26), 0.012, 0.01)],
     9, lambda _p, ring, a: blend(BACK, TAIL, smooth(-0.83, 0.15, -sin(a)) *
                                (0.57 + 0.1 * ring)), joint("Body"), "coat")
loft([((0, -1.36, 1.747), 0.113, 0.068),
      ((0, -1.402, 1.745), 0.108, 0.057),
      ((0, -1.427, 1.749), 0.065, 0.034)],
     10, lambda _p, _ring, a: blend(INK, FLANK, smooth(0.1, 1, sin(a)) * 0.23),
     joint("Neck"), "coat")


def horn_pigment(point, _ring, angle):
    height = smooth(2.12, 2.62, point.z)
    return blend(HORN, BONE, (0.36 + 0.38 * height) * (0.73 + 0.27 * sin(angle)))


for side in [-1, 1]:
    def mirrored(sections):
        return [((side * x, y, z), width, height)
                for x, y, z, width, height in sections]

    loft(mirrored([(0.155, -0.82, 1.973, 0.064, 0.050),
                   (0.25, -0.789, 2.03, 0.094, 0.065),
                   (0.365, -0.744, 2.115, 0.067, 0.047),
                   (0.439, -0.70, 2.18, 0.009, 0.009)]),
         10, lambda _p, _ring, a: blend(FLANK, EAR, smooth(-0.24, 0.94, cos(a)) *
                                      (0.68 + 0.15 * side)),
         joint("Neck"), "ear", (0, -1, 0))
    loft(mirrored([(0.172, -1.07, 1.925, 0.049, 0.045),
                   (0.189, -1.07, 1.926, 0.045, 0.037),
                   (0.196, -1.074, 1.929, 0.023, 0.021)]),
         8, lambda _p, _ring, a: blend(INK, AMBER, smooth(0.49, 1, sin(a)) * 0.21),
         joint("Neck"), "coat", (0, 1, 0))

    # The main antler sweeps back. Its forward brow and forked tines stay distinct
    # in both the follow camera and a side view.
    loft(mirrored([(0.126, -0.862, 2.031, 0.058, 0.057),
                   (0.193, -0.79, 2.167, 0.049, 0.055),
                   (0.284, -0.66, 2.31, 0.043, 0.048),
                   (0.395, -0.48, 2.438, 0.031, 0.039),
                   (0.481, -0.32, 2.556, 0.021, 0.026),
                   (0.532, -0.23 - side * 0.025, 2.64, 0.005, 0.006)]),
         7, horn_pigment, joint("Neck"), "antler")
    for tine in [
        [(0.212, -0.79, 2.177, .032, .038),
         (0.252, -0.934, 2.246, .032, .025),
         (0.298, -1.01, 2.365, .014, .012),
         (0.317, -1.007, 2.417, .005, .005)],
        [(0.314, -0.60, 2.349, .034, .038),
         (0.321, -0.63, 2.48, .023, .026),
         (0.352, -0.63, 2.604, .009, .012),
         (0.386, -0.59, 2.66 + .022 * side, .004, .004)],
        [(0.425, -0.439, 2.467, .025, .029),
         (0.517, -0.422, 2.526, .023, .028),
         (0.609, -0.395, 2.584, .012, .013),
         (0.648, -0.355, 2.636 - .021 * side, .004, .004)],
    ]:
        loft(mirrored(tine), 7, horn_pigment, joint("Neck"), "antler")


for code, (hip, knee, ankle, upper, lower, foot, front) in legs.items():
    x, y, _ = hip
    _, ky, kz = knee
    _, ay, az = ankle
    fore = 1 if front else 0

    def leg_weights(ring):
        if ring < 2:
            amount = (0.21, 0.76)[ring]
            return (("Body", 1 - amount), (upper, amount))
        if ring < 6:
            amount = (0, 0.19, 0.55, 0.92)[ring - 2]
            return ((upper, 1 - amount), (lower, amount))
        amount = (0, 0.29, 0.92, 1)[ring - 6]
        return ((lower, 1 - amount), (foot, amount))

    def leg_pigment(_point, ring, a):
        lighter = 0.30 + 0.18 * sin(a)
        color = blend(BACK, AMBER, lighter)
        color = blend(color, blend(FLANK, AMBER, 0.33 if front else 0.14),
                      1 - smooth(1, 4, ring))
        return blend(color, blend(RUFF, BACK, 0.22 + 0.16 * cos(a)),
                     (0.43 if front else 0.31) * smooth(2, 7, ring))

    # Bury the first rings in the torso so the shoulder reads as one volume.
    loft([((x * 0.60, y, 1.32), 0.125, 0.124 + 0.026 * (1 - fore)),
          ((x * 0.87, y, 1.135), 0.129, 0.15 + 0.022 * (1 - fore)),
          ((x * 1.01, (y + ky) * 0.5, 0.917), 0.116, 0.124),
          ((x, ky, kz + 0.095), 0.083, 0.089),
          ((x, ky, kz), 0.074, 0.079),
          ((x, ky, kz - 0.089), 0.056, 0.061),
          ((x, (ky + ay) * 0.5, 0.37), 0.047, 0.048),
          ((x, ay + 0.016, 0.224), 0.052, 0.060),
          ((x, ay - 0.017, az), 0.068, 0.068),
          ((x, ay - 0.033, 0.108), 0.075, 0.065)],
         10, leg_pigment, leg_weights, "leg")

    for toe in [-1, 1]:
        cx = x + toe * 0.043
        loft([((cx, ay - 0.029, 0.155), 0.034, 0.067),
              ((cx, ay - 0.044, 0.103), 0.043, 0.084),
              ((cx, ay - 0.063, 0.035), 0.044, 0.087),
              ((cx, ay - 0.061, 0.012), 0.038, 0.075)],
             8, lambda _p, ring, a: blend(INK, BACK,
                                          (1 - ring / 4) * (0.36 + 0.12 * cos(a))),
             joint(foot), "toe")

    # Bone parenting keeps the contact under the actual animated toe cap.
    anchor = bpy.data.objects.new("HoofContact_" + code, None)
    anchor.empty_display_type = "PLAIN_AXES"
    anchor.empty_display_size = 0.08
    bpy.context.collection.objects.link(anchor)
    anchor.parent = rig
    anchor.parent_type = "BONE"
    anchor.parent_bone = foot
    bpy.context.view_layer.update()
    anchor.matrix_world.translation = Vector((x, ay - 0.061, 0.018))


mesh = bpy.data.meshes.new("Watercolor coat")
mesh.from_pydata(positions, [], faces)
mesh.update()
for face in mesh.polygons:
    face.use_smooth = True

coat_material = bpy.data.materials.new("Matte watercolor pigments")
coat_material.use_nodes = True
surface = coat_material.node_tree.nodes.get("Principled BSDF")
surface.inputs["Roughness"].default_value = 0.92
vertex_pigment = coat_material.node_tree.nodes.new("ShaderNodeVertexColor")
vertex_pigment.layer_name = "Pigment"
coat_material.node_tree.links.new(vertex_pigment.outputs["Color"], surface.inputs["Base Color"])
mesh.materials.append(coat_material)
attribute = mesh.color_attributes.new(name="Pigment", type="FLOAT_COLOR", domain="POINT")
for pigment, color in zip(attribute.data, colors):
    pigment.color = (*color, 1)

skin = bpy.data.objects.new("Reindeer", mesh)
bpy.context.collection.objects.link(skin)
skin.parent = rig
groups = {bone.name: skin.vertex_groups.new(name=bone.name) for bone in armature.bones}
for index, weights in enumerate(skin_weights):
    for name, weight in weights:
        if weight:
            groups[name].add([index], weight, "REPLACE")
modifier = skin.modifiers.new("Reindeer skeleton", type="ARMATURE")
modifier.object = rig


def role_position(role, region, point):
    x, y, z = point
    if region == "toe":
        return point
    if region == "leg":
        upper = smooth(0.37, 1.31, z)
        return (x * (1 + upper * (0.13 if role == "Leader" else -0.14)),
                y, z - upper * (0 if role == "Leader" else 0.067))
    if region == "antler":
        height = max(0, z - 2.03)
        if role == "Leader":
            return (x * (1.07 + 0.22 * smooth(0, 0.65, height)),
                    y + height * 0.15, z + height * 0.045)
        return (x * (1.08 - 0.48 * smooth(0, 0.66, height)),
                -0.86 + (y + 0.86) * 0.31, 1.995 + height * 0.26)
    chest = (1 - smooth(-0.44, -0.06, y)) * (1 - smooth(1.61, 1.91, z))
    mask = (1 - smooth(-0.64, -0.30, y)) * smooth(1.33, 1.83, z)
    if role == "Leader":
        return (x * (1 + 0.17 * chest), y, z + 0.055 * chest)
    ears = 1.18 if region == "ear" else 1
    return (x * (0.94 + 0.18 * mask - 0.09 * chest) * ears,
            y + (0.14 if y < 0 else -0.07) * smooth(0.31, 1.35, abs(y)),
            z - 0.085 * (1 - mask) + 0.022 * mask)


skin.shape_key_add(name="Basis")
for role in ["Leader", "Calf"]:
    shape = skin.shape_key_add(name=role)
    shape.value = 0
    for vertex, region, position in zip(shape.data, regions, positions):
        vertex.co = role_position(role, region, position)


def angle(a, b):
    return atan2(b[1] - a[1], a[2] - b[2])


def length(a, b):
    return hypot(b[1] - a[1], b[2] - a[2])


def clamp_cos(value):
    return max(-1.0, min(1.0, value))


def posed_leg(leg, body_height, travel, lift, hoof_pitch):
    hip, knee, ankle, upper, lower, foot, front = leg
    dy, dz = ankle[1] + travel - hip[1], ankle[2] + lift - hip[2] - body_height
    thigh, shin = length(hip, knee), length(knee, ankle)
    reach = min(hypot(dy, dz), thigh + shin - 0.002)
    bearing = atan2(dy, -dz)
    spread = acos(clamp_cos((thigh ** 2 + reach ** 2 - shin ** 2) / (2 * thigh * reach)))
    bend = spread if front else -spread
    first = bearing + bend
    shin_y = reach * sin(bearing) - thigh * sin(first)
    shin_z = reach * cos(bearing) - thigh * cos(first)
    second = atan2(shin_y, shin_z)
    hip_turn = first - angle(hip, knee)
    shin_turn = second - angle(knee, ankle)
    rig.pose.bones[upper].rotation_euler.x = hip_turn
    rig.pose.bones[lower].rotation_euler.x = shin_turn - hip_turn
    rig.pose.bones[foot].rotation_euler.x = hoof_pitch - shin_turn


def animate(name, last, stride=0.0, rise=0.0):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = action
    for frame in range(1, last + 1):
        t = (frame - 1) / (last - 1)
        phase = TURN * t
        settle = smooth(0.02, 0.91, t) if name == "Settle" else 0
        breathe = 0.011 * sin(phase) if name == "Idle" else 0
        run_lift = rise * sin(phase) ** 2 * 0.21
        body = rig.pose.bones["Body"]
        body_height = -0.54 * settle + breathe + run_lift
        body.location.y = body_height
        body.keyframe_insert("location", frame=frame, group=body.name)
        neck = rig.pose.bones["Neck"]
        neck.rotation_euler.x = (-0.29 * sin(pi * t) if name == "Call"
                                 else 0.17 * settle + (0.035 if stride else 0.015) * sin(phase))
        neck.keyframe_insert("rotation_euler", frame=frame, group=neck.name)
        for code, leg in legs.items():
            front = leg[-1]
            offset = {"FL": 0, "HR": 0.09, "FR": 0.5, "HL": 0.59}[code]
            step = (t + offset) % 1
            if step <= 0.6:
                travel = stride * (step / 0.3 - 1)
                lift, toe = 0.0, 0.0
            else:
                swing = (step - 0.6) / 0.4
                travel = stride * cos(pi * swing)
                lift = sin(pi * swing) * rise
                toe = 0.17 * sin(TURN * swing) if stride else 0
            settle_travel = (0.33 if front else -0.27) * settle
            posed_leg(leg, body_height, travel + settle_travel, lift, toe + 0.18 * settle)
            for bone in leg[3:6]:
                part = rig.pose.bones[bone]
                part.keyframe_insert("rotation_euler", frame=frame, group=bone)


bpy.context.scene.render.fps = 30
bpy.context.preferences.filepaths.save_version = 0
for part in rig.pose.bones:
    part.rotation_mode = "XYZ"
for spec in [("Idle", 81), ("Walk", 33, 0.28, 0.18), ("Run", 21, 0.43, 0.29),
             ("Call", 34), ("Settle", 45)]:
    animate(*spec)
rig.animation_data.action = bpy.data.actions["Idle"]
bpy.context.view_layer.objects.active = skin
bpy.context.scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE / "reindeer-v002.blend"))
bpy.ops.export_scene.gltf(filepath=str(OUTPUT / "reindeer-v002.glb"),
                         export_format="GLB", export_animation_mode="ACTIONS",
                         export_yup=True, export_animations=True,
                         export_morph=True, export_morph_normal=True)
