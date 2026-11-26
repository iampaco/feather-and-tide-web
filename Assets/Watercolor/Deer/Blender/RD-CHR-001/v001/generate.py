"""Build the chapter's original low-poly, rigid-skinned reindeer rig."""
from math import cos, pi, sin
from pathlib import Path
import bpy
from mathutils import Vector

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
source = Path(__file__).resolve().parent
output = source.parents[5] / "public/assets/reindeer"
output.mkdir(parents=True, exist_ok=True)

def pigment(name, rgb):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = (*rgb, 1)
    surface = material.node_tree.nodes.get("Principled BSDF")
    surface.inputs["Base Color"].default_value = (*rgb, 1)
    surface.inputs["Roughness"].default_value = 0.92
    return material

coat = pigment("Burnt umber coat", (.30, .17, .095))
neck = pigment("Oat winter ruff", (.68, .51, .35))
rump = pigment("Parchment rump", (.81, .67, .49))
nose = pigment("Ink", (.042, .037, .033))
antler = pigment("Bone and sienna", (.55, .39, .25))
ear = pigment("Muted rose", (.38, .20, .17))

data = bpy.data.armatures.new("Reindeer skeleton")
rig = bpy.data.objects.new("Reindeer rig", data)
bpy.context.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")

def bone(name, head, tail, parent=None):
    part = data.edit_bones.new(name)
    part.head, part.tail = head, tail
    if parent:
        part.parent = data.edit_bones[parent]

bone("Body", (0, 0, 0), (0, 0, 1))
bone("Neck", (0, -.43, 1.17), (0, -.77, 1.79), "Body")
legs = {}
for side in (-1, 1):
    for front in (True, False):
        label = ("Front" if front else "Hind") + (".L" if side < 0 else ".R")
        x, y = side * .22, (-.47 if front else .54)
        legs[label] = (x, y, front)
        bone(label, (x, y, 1.01), (x, y, .10), "Body")
bpy.ops.object.mode_set(mode="OBJECT")

def attach(obj, name, material, parent):
    obj.name = name
    obj.data.materials.append(material)
    world = obj.matrix_world.copy()
    obj.parent = rig
    obj.parent_type = "BONE"
    obj.parent_bone = parent
    obj.matrix_world = world

def oval(name, location, scale, material, parent="Body", angle=0):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, location=location)
    obj = bpy.context.object
    obj.scale = scale
    obj.rotation_euler.x = angle
    bpy.context.view_layer.update()
    attach(obj, name, material, parent)

def branch(name, a, b, start, end, material, parent):
    va, vb = Vector(a), Vector(b)
    bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=start, radius2=end,
                                   depth=(vb - va).length, location=(va + vb) / 2)
    obj = bpy.context.object
    obj.rotation_euler = (vb - va).to_track_quat('Z', 'Y').to_euler()
    bpy.context.view_layer.update()
    attach(obj, name, material, parent)

oval("Torso", (0, .04, 1.22), (.38, .89, .44), coat)
oval("Hindquarters", (0, .58, 1.27), (.37, .42, .39), coat)
oval("Rump patch", (0, .85, 1.28), (.29, .15, .28), rump)
oval("Tail", (0, .94, 1.37), (.105, .19, .09), coat, angle=-.52)
oval("Ruff", (0, -.56, 1.46), (.27, .32, .54), neck, "Neck", -.46)
oval("Head", (0, -.90, 1.85), (.22, .40, .23), coat, "Neck", .24)
oval("Muzzle", (0, -1.18, 1.74), (.16, .23, .125), neck, "Neck", .25)
oval("Nose", (0, -1.34, 1.71), (.135, .08, .073), nose, "Neck")

for side in (-1, 1):
    oval("Eye", (side * .19, -1.06, 1.9), (.042, .042, .043), nose, "Neck")
    oval("Ear", (side * .25, -.75, 2.01), (.176, .09, .095), coat, "Neck", -.26)
    oval("Inner ear", (side * .29, -.81, 2.026), (.106, .044, .062), ear, "Neck")
    points = [(side*.12,-.82,2.02), (side*.27,-.71,2.27),
              (side*.39,-.47,2.54), (side*.49,-.29,2.64)]
    radii = [.054, .043, .027, .006]
    for i in range(len(points) - 1):
        branch("Antler beam", points[i], points[i+1], radii[i], radii[i+1], antler, "Neck")
    for base, target in [(points[1], (side*.22,-.94,2.47)),
                        (points[2], (side*.44,-.52,2.78)),
                        (points[2], (side*.62,-.45,2.68))]:
        branch("Antler tine", base, target, .027, .005, antler, "Neck")

for label, (x, y, front) in legs.items():
    knee = (x, y + (.02 if front else .13), .55)
    hoof = (x, y - .08, .12)
    oval("Leg shoulder", (x, y, .96), (.155, .23, .26), coat, label)
    branch("Upper leg", (x,y,1.04), knee, .13, .075, coat, label)
    branch("Shin", knee, hoof, .073, .048, neck, label)
    oval("Hoof", (x, y - .10, .085), (.087,.125,.09), nose, label)

# Preserve the rigid weighting while batching the mesh by material in glTF.
mesh_parts = [part for part in rig.children if part.type == "MESH"]
bpy.ops.object.select_all(action="DESELECT")
for obj in mesh_parts:
    joint = obj.parent_bone
    world = obj.matrix_world.copy()
    obj.parent_type = "OBJECT"
    obj.matrix_world = world
    group = obj.vertex_groups.new(name=joint)
    group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    obj.select_set(True)
bpy.context.view_layer.objects.active = mesh_parts[0]
bpy.ops.object.join()
skin = bpy.context.object
skin.name = "Reindeer coat, hooves and antlers"
binding = skin.modifiers.new(name="Reindeer skeleton", type="ARMATURE")
binding.object = rig
bpy.context.view_layer.objects.active = rig
for part in rig.pose.bones:
    part.rotation_mode = "XYZ"

def animate(name, frames, stride=0.0, call=False, settle=False):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = action
    for frame in frames:
        t = (frame - frames[0]) / (frames[-1] - frames[0])
        phase = 2 * pi * t
        body = rig.pose.bones["Body"]
        # The root moves locally on the vertical axis for breathing and rest.
        body.location.y = (-.70 * min(1, t * 1.25) if settle
                           else (.032 if stride else .014) * sin(phase * 2))
        body.keyframe_insert("location", frame=frame, group=body.name)
        neck_bone = rig.pose.bones["Neck"]
        neck_bone.rotation_euler.x = (-.28 * sin(pi*t) if call else
                                      .14 * t if settle else .06 * sin(phase))
        neck_bone.keyframe_insert("rotation_euler", frame=frame, group=neck_bone.name)
        for i, label in enumerate(legs):
            part = rig.pose.bones[label]
            part.rotation_euler.x = (t * (.99 if "Front" in label else -.84) if settle
                                     else stride * cos(phase + (pi if i in (1,2) else 0)))
            part.keyframe_insert("rotation_euler", frame=frame, group=label)

bpy.context.scene.render.fps = 30
bpy.context.preferences.filepaths.save_version = 0
for name, frames, stride, call, settle in [
    ("Idle", [1, 20, 40, 60, 81], 0, False, False),
    ("Walk", [1, 8, 16, 24, 33], .34, False, False),
    ("Run", [1, 5, 10, 15, 21], .55, False, False),
    ("Call", [1, 9, 17, 25, 34], 0, True, False),
    ("Settle", [1, 12, 23, 34, 45], 0, False, True),
]:
    animate(name, frames, stride, call, settle)
rig.animation_data.action = bpy.data.actions["Idle"]
bpy.context.scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(source / "reindeer-v001.blend"))
bpy.ops.export_scene.gltf(filepath=str(output / "reindeer-v001.glb"),
                         export_format="GLB", export_animation_mode="ACTIONS",
                         export_yup=True, export_animations=True)
