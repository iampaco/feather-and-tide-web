"""Generate CHR-001 with Blender 5.2. Run with -- /empty/output [--graybox]."""

from hashlib import sha256
import faulthandler
import json
import math
from pathlib import Path
import runpy
import struct
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import numpy as np


HERE = Path(__file__).resolve().parent
MAT = HERE.parents[1] / "MAT-002" / "v001"
MASTER = HERE.parents[1] / "MAT-001" / "v001"
TOOLS = runpy.run_path(str(MASTER / "MAT-001_watercolor_master_generate.py"))
STEM = "CHR-001_goose_rig"
GAME_SIZE = (852, 393)
MATERIALS = ("Body_Leader", "Head", "FlightFeather", "BillFeet", "Eye")
TINTS = {
    "Leader": (1.0, 0.976, 0.925, 1.0),
    "Follower A": (0.965, 0.985, 1.0, 1.0),
    "Follower B": (0.91, 0.925, 0.94, 1.0),
    "Follower C": (0.98, 0.96, 0.94, 1.0),
}


def smooth(a, b, x):
    t = min(1, max(0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def body_weights(y):
    neck = smooth(0.11, 0.29, y)
    head = smooth(0.29, 0.415, y)
    tail = 1 - smooth(-0.345, -0.185, y)
    return {"Tail": tail, "Body": 1 - neck - tail, "Neck": neck - head, "Head": head}


def wing_weights(x, side):
    root = smooth(0.100, 0.206, x)
    elbow = smooth(0.233, 0.401, x)
    wrist = smooth(0.431, 0.573, x)
    tip = smooth(0.605, 0.744, x)
    return {"Body": 1 - root, f"WingRoot.{side}": root - elbow,
            f"Elbow.{side}": elbow - wrist, f"Wrist.{side}": wrist - tip,
            f"Tip.{side}": tip}


class GooseMesh:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.uvs = []
        self.weights = []
        self.slots = []
        self.parts = {}

    def tube(self, name, rings, segments, weights, slot, reverse=False):
        """Join equal-size cross sections. Keep the U seam at the top of each ring."""
        start = len(self.vertices)
        for _, sample in rings:
            for side in range(segments):
                angle = math.tau * side / segments
                vertex = sample(math.sin(angle), math.cos(angle))
                self.vertices.append(vertex)
                self.weights.append({k: w for k, w in weights(vertex).items() if w > 1e-8})
        first_face = len(self.faces)

        def face(indices, uv, material, flip):
            self.faces.append(tuple(reversed(indices)) if flip else tuple(indices))
            self.uvs.append(tuple(reversed(uv)) if flip else tuple(uv))
            self.slots.append(material)

        for row in range(len(rings) - 1):
            v0, v1 = rings[row][0], rings[row + 1][0]
            for i in range(segments):
                j = (i + 1) % segments
                a = start + row * segments
                u0, u1 = i / segments, (i + 1) / segments
                face((a+i, a+j, a+j+segments, a+i+segments),
                     ((u0,v0), (u1,v0), (u1,v1), (u0,v1)), slot(row, i), reverse)
        # UV discs keep the closed ends valid for triangulation and export.
        for row, flip, center_v in [(0, True, 0.05), (len(rings)-1, False, 0.95)]:
            ids = [start + row * segments + i for i in range(segments)]
            uv = [(0.5 + 0.04 * math.sin(math.tau*i/segments),
                   center_v + 0.04 * math.cos(math.tau*i/segments)) for i in range(segments)]
            face(ids, uv, slot(min(row, len(rings)-2), 0), flip != reverse)
        self.parts[name] = list(range(first_face, len(self.faces)))

    def along_y(self, name, rows, segments, weights, slot, x=0):
        rings = []
        for v, y, z, w, h in rows:
            def sample(s, c, y=y, z=z, w=w, h=h):
                return (x + w*s, y, z + h*c)
            rings.append((v, sample))
        self.tube(name, rings, segments, weights, slot)

    def feather(self, name, base, tip, width, thickness, weights, segments=6):
        base, tip = Vector(base), Vector(tip)
        axis = (tip - base).normalized()
        cross = Vector((axis.y, -axis.x, 0)).normalized()
        up = cross.cross(axis)
        rings = []
        for t, shape in [(0, .39), (.22, .91), (.55, 1), (.78, .83), (.94, .40), (1, .035)]:
            point = base.lerp(tip, t)
            point.z += .009 * math.sin(t * math.pi)
            def sample(s, c, point=point, shape=shape):
                return tuple(point + cross * (width*shape*s) + up * (thickness*shape*c))
            rings.append((t, sample))
        self.tube(name, rings, segments, weights, lambda *_: 2)

    def object(self, group, materials):
        mesh = bpy.data.meshes.new("Goose_LOD0")
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        for mat in materials:
            mesh.materials.append(mat)
        uv = mesh.uv_layers.new(name="Plumage")
        for face, coordinates, slot in zip(mesh.polygons, self.uvs, self.slots):
            face.use_smooth = len(face.vertices) == 4
            face.material_index = slot
            for i, coord in zip(face.loop_indices, coordinates):
                uv.data[i].uv = coord
        obj = bpy.data.objects.new("Goose_LOD0", mesh)
        group.objects.link(obj)
        return obj


def model():
    mesh = GooseMesh()
    # Y, Z, width and height are authored as one continuous body-to-crown surface.
    torso = [
        (-.321, -.018, .012, .011), (-.303, -.015, .049, .031),
        (-.263, -.012, .087, .054), (-.206, -.008, .120, .078),
        (-.143, -.004, .143, .097), (-.071, .000, .150, .103),
        (.000, .000, .148, .105), (.065, .009, .131, .093),
        (.116, .025, .100, .075), (.154, .049, .074, .059),
        (.187, .078, .056, .048), (.221, .110, .046, .039),
        (.254, .146, .044, .035), (.284, .184, .049, .041),
    ]
    # MAT-002 PNG rows run down from the top, so texture V = 1 - PNG row.
    # Stretch both bands along the visible crown and preserve a warm white gap.
    crown = [
        (.025, .300, .193, .055, .043), (.165, .317, .207, .066, .050),
        (.190, .337, .225, .073, .060), (.240, .365, .242, .078, .069),
        (.292, .392, .253, .081, .076), (.360, .414, .263, .081, .083),
        (.402, .441, .269, .079, .088), (.450, .466, .267, .075, .092),
        (.495, .493, .259, .066, .087), (.66, .521, .246, .052, .071),
        (.96, .543, .231, .038, .043),
    ]
    rows = [(i / (len(torso)-1) * .94, *row) for i, row in enumerate(torso)]
    rows.extend(crown)
    mesh.along_y("Body and crown", rows, 20, lambda p: body_weights(p[1]),
                 lambda row, _: 1 if row >= len(torso) else 0)
    mesh.along_y("Bill", [
        (0, .517, .225, .038, .022), (.25, .548, .220, .040, .021),
        (.53, .578, .215, .031, .015), (.86, .605, .212, .018, .010),
        (1, .614, .212, .004, .004),
    ], 12, lambda p: {"Head": 1}, lambda *_: 3)
    for i in range(5):
        spread = i - 2
        mesh.feather(f"Tail feather {i+1}", (spread*.020, -.238, -.010-abs(spread)*.003),
                     (spread*.031, -.376+abs(spread)*.015, -.016-abs(spread)*.005),
                     .027, .007, lambda p: body_weights(p[1]))
    for sign, label in [(-1, "L"), (1, "R")]:
        mesh.along_y(f"Eye.{label}", [
            (0, .470, .269, .003, .003), (.30, .476, .269, .007, .010),
            (.68, .490, .269, .008, .010), (1, .497, .269, .003, .003),
        ], 8, lambda p: {"Head": 1}, lambda *_: 4, x=sign*.062)
        mesh.along_y(f"Foot.{label}", [
            (0, -.281, -.084, .006, .003), (.18, -.270, -.090, .022, .006),
            (.39, -.246, -.092, .024, .008), (.68, -.213, -.093, .016, .010),
            (.86, -.189, -.085, .014, .011), (1, -.169, -.066, .011, .011),
        ], 10, lambda p, label=label: {f"Foot.{label}": 1}, lambda *_: 3, x=sign*.068)
        def weights(p, label=label):
            return wing_weights(abs(p[0]), label)

        sections = [
            (.080,.017,-.193,.027,.048), (.124,.040,-.224,.037,.047),
            (.178,.056,-.240,.042,.042), (.232,.072,-.242,.041,.033),
            (.288,.076,-.237,.038,.028), (.343,.069,-.231,.034,.024),
            (.398,.053,-.227,.034,.021), (.455,.038,-.218,.036,.018),
            (.511,.017,-.205,.041,.016), (.567,-.015,-.192,.046,.014),
            (.625,-.050,-.169,.050,.011), (.675,-.086,-.161,.052,.008),
            (.712,-.117,-.158,.054,.005), (.739,-.144,-.156,.054,.003),
        ]
        rings = []
        for x, leading, trailing, z, h in sections:
            def sample(s, c, x=x, leading=leading, trailing=trailing, z=z, h=h):
                return (sign*x, (leading+trailing)/2 + (leading-trailing)/2*s, z+h*c)
            rings.append(((x-.080)/(.739-.080), sample))
        mesh.tube(f"Wing.{label}", rings, 14, weights,
                  lambda *_: 0, reverse=sign > 0)

        # Each closed blade overlaps the wing bed. Shared span weights keep
        # the overlapping roots travelling with their supporting wing.
        for i in range(9):
            x = .167 + i * .061
            end_x = (.183,.251,.322,.392,.462,.537,.616,.701,.778)[i]
            end_y = (-.253,-.270,-.280,-.281,-.276,-.265,-.251,-.230,-.210)[i]
            end_z = (.034,.024,.021,.020,.022,.030,.038,.045,.051)[i]
            mesh.feather(f"Flight feather {i+1}.{label}",
                         (sign*x, -.138 if i < 7 else -.143, end_z+.007),
                         (sign*end_x, end_y, end_z), .041 if i < 6 else .035, .006, weights)
        mesh.feather(f"Outer primary.{label}", (sign*.674, -.138, .053),
                     (sign*.800, -.177, .058), .024, .005, weights)
    return mesh


def add_object(group, name, data, location=(0,0,0)):
    obj = bpy.data.objects.new(name, data)
    group.objects.link(obj)
    obj.location = location
    return obj


def collection(scene, name):
    group = bpy.data.collections.new(name)
    scene.collection.children.link(group)
    return group


def plain(name, color):
    return TOOLS["plain_material"](name, color)


def render_settings(scene, size, samples=20):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"


def camera(group, name, eye, aim, fov=50, ortho=None):
    data = bpy.data.cameras.new(name)
    data.sensor_fit = "VERTICAL"
    data.sensor_height = 24
    data.lens = 12 / math.tan(math.radians(fov) / 2)
    data.clip_start, data.clip_end = .015, 2400
    if ortho:
        data.type = "ORTHO"
        data.ortho_scale = ortho
    obj = add_object(group, name, data, eye)
    obj.rotation_euler = (Vector(aim) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def studio(scene, scale):
    group = collection(scene, "Review cameras and lights")
    scene.world = bpy.data.worlds.new("Diffuse daylight")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (.44, .45, .46, 1)
    background.inputs["Strength"].default_value = .74

    floor = bpy.data.meshes.new("Review Ground")
    floor.from_pydata([(-1200,-1200,0),(1200,-1200,0),(1200,1200,0),(-1200,1200,0)], [], [(0,1,2,3)])
    floor.materials.append(plain("Sage backdrop", "9CAFA5"))
    ground = add_object(group, "Review Ground", floor, (0,0,-8/scale))
    ground.hide_select = True

    sun = bpy.data.lights.new("Neutral key", "SUN")
    sun.energy, sun.angle = 1.68, .38
    key = add_object(group, sun.name, sun)
    key.rotation_euler = Vector((.39,.49,-1)).to_track_quat("-Z","Y").to_euler()
    camera(group, "Gameplay | fixed rear", (0, -180*math.cos(.48)/scale,
           (180*math.sin(.48)-8)/scale), (0,0,-2/scale))
    camera(group, "Review | rear detail", (.69,-1.49,1.11), (0,.05,.09), ortho=2.14)
    camera(group, "Review | top", (0,.09,2.6), (0,.09,0), ortho=1.99)
    camera(group, "Review | side", (1.45,-.06,.76), (0,.05,.09), ortho=1.77)
    return group, key


def render(scene, view, output, name, size, samples=20):
    render_settings(scene, size, samples)
    TOOLS["render"](scene, view, output / f"preview_{name}.png")


def graybox(scene, mesh, group, output, scale):
    gray = plain("Silhouette clay", "747A77")
    obj = mesh.object(group, [gray] * len(MATERIALS))
    cameras, _ = studio(scene, scale)
    render(scene, cameras.objects["Gameplay | fixed rear"], output, "graybox_gameplay", GAME_SIZE)
    render(scene, cameras.objects["Review | rear detail"], output, "graybox_rear", (1040,680))
    render(scene, cameras.objects["Review | top"], output, "graybox_top", (1040,680))
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(data)
    return cameras


def append_plumage():
    source_names = list(MATERIALS[:-1]) + ["Body_Follower"]
    with bpy.data.libraries.load(str(MAT / "MAT-002_goose_plumage.blend")) as (source, target):
        assert set(source_names) <= set(source.materials)
        target.materials = source_names.copy()
    imported = {material.name: material for material in target.materials}
    followers = {}
    for name, tint in list(TINTS.items())[1:]:
        mat = imported["Body_Leader"].copy()
        mat.name = "Body_" + name.replace(" ", "_")
        mat.asset_clear()
        mat.asset_mark()
        mat.asset_data.description = f"Feather & Tide / CHR-001 / {name}, from MAT-002"
        mat.node_tree.nodes.get("Mix").inputs[7].default_value = tint
        followers[name] = mat
    for mat in imported.values():
        mat.use_fake_user = True
    for image in bpy.data.images:
        if image.packed_file:
            image.filepath = f"//../../MAT-002/v001/textures/{image.name}"
    eye = plain("Eye", "302B28")
    shader = next(n for n in eye.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    shader.inputs["Roughness"].default_value = .57
    return [imported[n] for n in MATERIALS[:-1]] + [eye], followers


def register_variants(scene, obj, followers):
    # Set the bundled exporter properties for this Blender process.
    prefs = bpy.context.preferences.addons["io_scene_gltf2"].preferences
    prefs.KHR_materials_variants_ui = True
    for index, name in enumerate(TINTS):
        entry = scene.gltf2_KHR_materials_variants_variants.add()
        entry["name"] = name
        entry.variant_idx = index
        mapping = obj.data.gltf2_variant_mesh_data.add()
        mapping.material_slot_index = 0
        mapping.material = followers.get(name, obj.data.materials[0])
        mapping.variants.add().variant.variant_idx = index
    default = obj.data.gltf2_variant_default_materials.add()
    default.material_slot_index = 0
    default.default_material = obj.data.materials[0]


def skeleton(group, obj, weights):
    armature = bpy.data.armatures.new("GooseSkeleton")
    rig = add_object(group, "GooseRig", armature)
    rig.show_in_front = True
    armature.display_type = "STICK"
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    def bone(name, head, tail, parent=None, connected=False):
        item = armature.edit_bones.new(name)
        item.head, item.tail = head, tail
        if parent:
            item.parent = armature.edit_bones[parent]
            item.use_connect = connected
        item.align_roll(Vector((0, 0, 1)))
        return item

    bone("Root", (0,0,0), (0,.13,0)).use_deform = False
    bone("Body", (0,0,0), (0,.154,.048), "Root")
    bone("Neck", (0,.154,.048), (0,.344,.244), "Body", True)
    bone("Head", (0,.344,.244), (0,.536,.249), "Neck", True)
    bone("Tail", (0,-.184,-.012), (0,-.376,-.016), "Body")
    for sign, side in [(-1, "L"), (1, "R")]:
        positions = [(sign*x,y,z) for x,y,z in [
            (.121,-.080,.035), (.307,-.066,.038), (.502,-.086,.043),
            (.668,-.119,.051), (.800,-.177,.058)]]
        parent = "Body"
        for index, name in enumerate(["WingRoot", "Elbow", "Wrist", "Tip"]):
            label = f"{name}.{side}"
            bone(label, positions[index], positions[index+1], parent, index > 0)
            parent = label
        bone(f"Foot.{side}", (sign*.068,-.169,-.066), (sign*.068,-.274,-.089), "Body")
    bpy.ops.object.mode_set(mode="OBJECT")

    groups = {b.name: obj.vertex_groups.new(name=b.name) for b in armature.bones if b.use_deform}
    for index, values in enumerate(weights):
        for name, weight in values.items():
            groups[name].add([index], weight, "REPLACE")
    skin = obj.modifiers.new("GooseSkin", "ARMATURE")
    skin.object = rig
    obj.parent = rig
    rig.pose.bones["Root"].lock_location = (True, True, True)
    rig.pose.bones["Root"].lock_rotation = (True, True, True)
    rig.pose.bones["Root"].lock_scale = (True, True, True)
    return rig


def pose_specs():
    def wings(root, elbow, wrist, tip):
        return {f"{name}.{side}": (angle,0,0)
                for side in ("L","R") for name, angle in
                zip(("WingRoot","Elbow","Wrist","Tip"), (root,elbow,wrist,tip))}
    return {
        "Neutral": {},
        "Upstroke": wings(39, 13, -14, -10),
        "Downstroke": wings(-34, -12, 19, 10),
        "Wrist flex": {"Wrist.L": (25,0,16), "Tip.L": (13,0,7),
                       "Wrist.R": (19,0,-13), "Tip.R": (9,0,-6)},
        "Neck turn": {"Neck": (4,0,-24), "Head": (-4,0,11)},
    }


def set_pose(rig, rotations):
    for bone in rig.pose.bones:
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = tuple(map(math.radians, rotations.get(bone.name, (0,0,0))))
    bpy.context.view_layer.update()


def save_pose_assets(rig):
    for name, rotations in pose_specs().items():
        set_pose(rig, rotations)
        for bone in rig.pose.bones:
            if bone.name != "Root":
                bone.keyframe_insert("rotation_euler", frame=1, group=bone.name)
        action = rig.animation_data.action
        action.name = f"QA · {name}"
        action.use_fake_user = True
        action.asset_mark()
        action.asset_data.description = "Single-frame deformation test for CHR-001"
        rig.animation_data.action = None
    set_pose(rig, {})


def verify_mesh(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    counts = len(mesh.loop_triangles)
    assert counts <= 4000 and all(t.area > 1e-10 for t in mesh.loop_triangles), counts
    uv = mesh.uv_layers.active
    uv_values = np.array([tuple(x.uv) for x in uv.data])
    assert np.isfinite(uv_values).all() and uv_values.min() >= 0 and uv_values.max() <= 1
    triangles = uv_values[[list(t.loops) for t in mesh.loop_triangles]]
    a, b = triangles[:,1] - triangles[:,0], triangles[:,2] - triangles[:,0]
    assert np.min(np.abs(a[:,0]*b[:,1] - a[:,1]*b[:,0])) > 1e-10
    weights = [list(g.weight for g in v.groups) for v in mesh.vertices]
    error = max(abs(sum(w)-1) for w in weights)
    assert error < 1e-6 and max(map(len,weights)) <= 4
    return {"triangles": counts, "vertices": len(mesh.vertices),
            "max_influences": max(map(len,weights)), "max_weight_sum_error": error,
            "uv_finite_bounded_and_nondegenerate": "pass"}


def pose_geometry(obj, rig, builder):
    mesh = obj.data
    edges = np.array([tuple(e.vertices) for e in mesh.edges])
    neutral = np.array([tuple(v.co) for v in mesh.vertices])
    lengths = np.linalg.norm(neutral[edges[:,0]] - neutral[edges[:,1]], axis=1)
    tris = [tuple(t.vertices) for t in mesh.loop_triangles]
    parts = {name: {i for i in faces} for name, faces in builder.parts.items()}
    part_tris = {name: [tri for tri,t in zip(tris, mesh.loop_triangles) if t.polygon_index in faces]
                 for name,faces in parts.items()}

    # Adjacent feather layers and the buried shoulder roots intentionally meet.
    # Test contacts where clearance is expected, and require both shoulder roots to stay attached.
    forbidden = [("Body and crown", name) for name in parts if
                 name.startswith("Outer primary") or name.startswith(("Flight feather 7","Flight feather 8","Flight feather 9"))]
    forbidden += [(f"Wing.{a}", f"Wing.{b}") for a,b in [("L","R")]]
    forbidden += [(f"Foot.{side}", f"Wing.{side}") for side in ("L","R")]
    forbidden += [("Bill", f"Wing.{side}") for side in ("L","R")]
    forbidden += [("Foot.L", "Foot.R")]

    checks = {}
    for name, rotations in pose_specs().items():
        set_pose(rig, rotations)
        assert rig.pose.bones["Root"].head.length < 1e-7
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        result = [tuple(v.co) for v in evaluated.data.vertices]
        coords = np.array(result)
        assert np.isfinite(coords).all()
        ratios = np.linalg.norm(coords[edges[:,0]] - coords[edges[:,1]], axis=1) / lengths
        assert np.min(ratios) > .46 and np.max(ratios) < 1.58, (name, ratios.min(), ratios.max())
        trees = {part: BVHTree.FromPolygons(result, faces, all_triangles=True)
                 for part,faces in part_tris.items()}
        hits = [pair for pair in forbidden if trees[pair[0]].overlap(trees[pair[1]])]
        assert not hits, (name,hits)
        shoulders = [bool(trees["Body and crown"].overlap(trees[f"Wing.{side}"]))
                     for side in ("L","R")]
        assert all(shoulders), (name, shoulders)
        checks[name] = {"edge_length_ratio_min": round(float(np.min(ratios)),4),
                        "edge_length_ratio_max": round(float(np.max(ratios)),4),
                        "unintended_pairs_intersecting": hits, "shoulder_attachment": shoulders,
                        "minimum_z_BU": round(float(np.min(coords[:,2])),6)}
    set_pose(rig, {})
    return checks


def load_glb(path):
    blob = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", blob)
    assert (magic, version, length) == (b"glTF", 2, len(blob))
    json_size, kind = struct.unpack_from("<I4s", blob, 12)
    assert kind == b"JSON"
    doc = json.loads(blob[20:20+json_size])
    binary_size, kind = struct.unpack_from("<I4s", blob, 20+json_size)
    binary = blob[28+json_size:]
    assert kind == b"BIN\x00" and len(binary) == binary_size
    return doc, binary


def bin_data(doc, binary, index):
    view = doc["bufferViews"][index]
    start = view.get("byteOffset", 0)
    return binary[start:start+view["byteLength"]]


def export_asset(obj, rig, output):
    for other in bpy.context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    path = output / f"{STEM}.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_yup=True, export_animations=False)
    doc, binary = load_glb(path)
    assert len(doc["meshes"]) == len(doc["skins"]) == 1
    assert not doc.get("animations") and not doc.get("cameras")
    assert not doc.get("extensionsRequired")
    skin = doc["skins"][0]
    nodes = {n["name"]: n for n in doc["nodes"]}
    assert {doc["nodes"][i]["name"] for i in skin["joints"]} == set(rig.data.bones.keys())
    assert len(skin["joints"]) == 15
    assert nodes["Root"].get("translation", [0,0,0]) == [0,0,0]
    primitives = doc["meshes"][0]["primitives"]
    attributes = {"POSITION","NORMAL","TEXCOORD_0","JOINTS_0","WEIGHTS_0"}
    assert all(attributes <= set(p["attributes"]) for p in primitives)
    assert sum(doc["accessors"][p["indices"]]["count"]//3 for p in primitives) == len(obj.data.loop_triangles)

    # The exported mesh node has identity transform. Compare the raw glTF
    # coordinates to the Blender bounds after (x,y,z) → (x,z,-y).
    mesh_node = next(n for n in nodes.values() if "mesh" in n)
    assert mesh_node.get("translation",[0,0,0]) == [0,0,0]
    assert mesh_node.get("scale",[1,1,1]) == [1,1,1]
    assert mesh_node.get("rotation",[0,0,0,1]) == [0,0,0,1]
    positions = [doc["accessors"][p["attributes"]["POSITION"]] for p in primitives]
    xyz = np.array([(v.co.x,v.co.z,-v.co.y) for v in obj.data.vertices])
    np.testing.assert_allclose(np.min([p["min"] for p in positions], axis=0), xyz.min(axis=0), atol=1e-6)
    np.testing.assert_allclose(np.max([p["max"] for p in positions], axis=0), xyz.max(axis=0), atol=1e-6)
    bill_material = next(i for i,m in enumerate(doc["materials"]) if m["name"] == "BillFeet")
    bill_bounds = doc["accessors"][next(p for p in primitives if p["material"] == bill_material)["attributes"]["POSITION"]]
    assert bill_bounds["min"][2] < -.60 and bill_bounds["max"][2] > .27
    head_material = next(i for i,m in enumerate(doc["materials"]) if m["name"] == "Head")
    head_bounds = doc["accessors"][next(p for p in primitives if p["material"] == head_material)["attributes"]["POSITION"]]
    assert head_bounds["min"][2] < -.53 and head_bounds["min"][1] > .14

    extension = "KHR_materials_variants"
    variants = doc["extensions"][extension]["variants"]
    assert [v["name"] for v in variants] == list(TINTS)
    mapping = next(p["extensions"][extension]["mappings"] for p in primitives if extension in p.get("extensions", {}))
    for item in mapping:
        pbr = doc["materials"][item["material"]]["pbrMetallicRoughness"]
        for i in item["variants"]:
            assert np.allclose(pbr["baseColorFactor"], TINTS[variants[i]["name"]])
    assert {i for item in mapping for i in item["variants"]} == set(range(len(TINTS)))
    textures = sorted((MAT / "textures").glob("*.png"))
    embedded = {sha256(bin_data(doc,binary,im["bufferView"])).hexdigest() for im in doc["images"]}
    assert len(embedded) == len(textures) == 4
    assert embedded == {sha256(t.read_bytes()).hexdigest() for t in textures}
    return path, {"one_mesh_one_skin": "pass", "joint_count": len(skin["joints"]),
                  "axes": "+X right, +Y up, -Z forward",
                  "bounds_gltf": [xyz.min(axis=0).tolist(), xyz.max(axis=0).tolist()],
                  "root_translation": [0,0,0], "pbr_textures_exact_png_match": "pass",
                  "variants": [v["name"] for v in variants], "animation_count": 0}


def compare_roundtrip(scene, source, rig, path, studio_group, output):
    from mathutils.kdtree import KDTree

    window = bpy.context.window
    other = bpy.data.scenes.new("GLB round-trip")
    window.scene = other
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path), bone_heuristic="BLENDER", disable_bone_shape=True)
    created = set(bpy.data.objects) - before
    mesh, = [o for o in created if o.type == "MESH"]
    imported, = [o for o in created if o.type == "ARMATURE"]
    assert all(abs(s-1) < 1e-6 for o in (mesh,imported) for s in o.scale)
    assert mesh.matrix_world.translation.length < 1e-6
    assert [m.object for m in mesh.modifiers if m.type == "ARMATURE"] == [imported]
    assert imported.data.bones["Root"].head_local.length < 1e-6
    matrix_error = 0
    for bone in rig.data.bones:
        target = imported.data.bones[bone.name]
        assert (target.parent.name if target.parent else None) == (bone.parent.name if bone.parent else None)
        matrix_error = max(matrix_error, float(np.max(np.abs(np.array(bone.matrix_local)-np.array(target.matrix_local)))))
    assert matrix_error < 1e-5, matrix_error
    mesh.data.calc_loop_triangles()
    assert len(mesh.data.loop_triangles) == len(source.data.loop_triangles)
    def point_uvs(obj):
        points = {}
        for loop, uv in zip(obj.data.loops, obj.data.uv_layers.active.data):
            points.setdefault(loop.vertex_index, set()).add(tuple(uv.uv))
        return points

    tree = KDTree(len(source.data.vertices))
    for vertex in source.data.vertices:
        tree.insert(vertex.co, vertex.index)
    tree.balance()
    source_uvs, imported_uvs = point_uvs(source), point_uvs(mesh)
    position_error, weight_error, uv_error = 0, 0, 0
    matched = []
    for vert in mesh.data.vertices:
        _, index, dist = tree.find(mesh.matrix_world @ vert.co)
        position_error = max(position_error, dist)
        matched.append(index)
        expected = {source.vertex_groups[g.group].name:g.weight for g in source.data.vertices[index].groups}
        actual = {mesh.vertex_groups[g.group].name:g.weight for g in vert.groups if g.weight > 1e-8}
        assert actual, (vert.index, index, tuple(vert.co), dist, expected, [(g.group, g.weight) for g in vert.groups])
        for name in expected.keys() | actual.keys():
            weight_error = max(weight_error, abs(actual.get(name,0)-expected.get(name,0)))
        for uv in imported_uvs[vert.index]:
            uv_error = max(uv_error, min(math.dist(uv, xy) for xy in source_uvs[index]))
    assert position_error < 1e-5 and uv_error < 1e-5 and weight_error < 2e-4, (position_error,uv_error,weight_error)
    assert set(matched) == set(range(len(source.data.vertices)))
    images = {n.image.name for m in mesh.data.materials for n in m.node_tree.nodes
              if n.type == "TEX_IMAGE" and n.image.packed_file and tuple(n.image.size) == (1024,1024)}
    assert len(images) == 4
    other.collection.children.link(studio_group)
    other.world = scene.world
    render(other, studio_group.objects["Review | rear detail"], output, "glb_roundtrip", (1040,680))
    window.scene = scene
    bpy.data.scenes.remove(other)
    return {"bone_rest_matrix_error": matrix_error, "position_error_BU": position_error,
            "weights_max_error": weight_error, "uv_error": uv_error, "packed_1k_images": len(images)}


def camera_bounds(scene, view, obj):
    w, h = GAME_SIZE
    projected = [world_to_camera_view(scene, view, obj.matrix_world @ v.co) for v in obj.data.vertices]
    assert min(v.z for v in projected) > 0
    x, y = [v.x*w for v in projected], [(1-v.y)*h for v in projected]
    return [round(f,2) for f in (min(x), min(y), max(x), max(y))]


def flock_preview(scene, view, source, followers, group, scale, output):
    # Review layout keeps all 12 birds inside the fixed viewport.
    placements = [(-45,-25), (45,-25), (0,-30), (-76,-48), (-25,-49), (25,-49), (76,-48),
                  (-71,-69), (-23,-71), (23,-72), (71,-71)]
    instances = []
    for index, (x,y) in enumerate(placements):
        name = list(followers)[index%3]
        obj = add_object(group, f"{name} · {index+1:02}", source.data, (x/scale,y/scale,-2/scale))
        obj.scale = (.8,.8,.8)
        obj.material_slots[0].link = "OBJECT"
        obj.material_slots[0].material = followers[name]
        instances.append(obj)
    bpy.context.view_layer.update()
    assert len({o.data for o in [source, *instances]}) == 1
    frames = {o.name: camera_bounds(scene,view,o) for o in [source,*instances]}
    assert all(0 <= x0 < x1 <= GAME_SIZE[0] and 0 <= y0 < y1 <= GAME_SIZE[1]
               for x0,y0,x1,y1 in frames.values())
    render(scene, view, output, "gameplay_flock_12", GAME_SIZE, 32)
    for obj in instances:
        bpy.data.objects.remove(obj, do_unlink=True)
    return {"leader_count":1,"follower_count":11,"shared_mesh_datablocks":1,
            "follower_scale":.8,"follower_root_positions_game_xy":placements,"screen_bounds_px":frames}


def read_pixels(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    image.colorspace_settings.name = "Non-Color"
    w,h = image.size
    pixels = np.empty(w*h*4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return pixels.reshape(h,w,4)[::-1,:,:3]


def crown_samples(scene, camera_obj, obj, builder, path):
    # Derive the five samples from the crown seam itself, so the report
    # tracks revisions to head shape and UV placement.
    rows = [
        ("front_white", 22), ("front_bar", 20), ("white_gap", 18),
        ("rear_bar", 15), ("rear_white", 14),
    ]
    pixels = read_pixels(path)
    w,h = GAME_SIZE
    result = {}
    for name,row in rows:
        point = Vector(builder.vertices[row*20])
        uv = world_to_camera_view(scene,camera_obj,obj.matrix_world @ point)
        x,y = uv.x*w-.5,(1-uv.y)*h-.5
        ix,iy = int(x),int(y)
        s,t = x-ix,y-iy
        colors = (pixels[iy,ix]*(1-s)*(1-t) + pixels[iy,ix+1]*s*(1-t)
                  + pixels[iy+1,ix]*(1-s)*t + pixels[iy+1,ix+1]*s*t)
        luma = float(np.dot(colors,[.2126,.7152,.0722])*255)
        result[name] = {"px": [round(x,2), round(y,2)], "luma_rgb8": round(luma,1)}
    return result


def record_bones(rig):
    def coords(v):
        return [round(float(x),7) for x in v]
    return {b.name: {
        "parent": b.parent.name if b.parent else None, "deform": b.use_deform,
        "connected": b.use_connect, "head_BU": coords(b.head_local), "tail_BU": coords(b.tail_local),
        "local_axes_in_blender": {axis: coords(b.matrix_local.col[i][:3]) for i,axis in enumerate("XYZ")},
    } for b in rig.data.bones}


def prepare_view(scene, obj, rig, cameras):
    for other in bpy.context.selected_objects:
        other.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    scene.camera = cameras.objects["Review | rear detail"]
    scene.render.filepath = "//"
    render_settings(scene,(1040,680))
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.clip_end = 120
                space.region_3d.view_perspective = "CAMERA"
                space.region_3d.view_camera_zoom = 12
                space.overlay.show_overlays = False
                space.shading.type = "MATERIAL"


def main(output, gray_only=False):
    assert not bpy.data.filepath, "Start Blender with --factory-startup."
    output.mkdir(parents=True, exist_ok=True)
    assert not any(output.iterdir()), "Use an empty output directory to preserve delivered assets."
    scene = bpy.context.scene
    scene.name = "CHR-001 | Bar-headed goose"
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.orphans_purge(do_recursive=True)
    group = collection(scene, "CHR-001 | Character")
    builder = model()
    xyz = np.array(builder.vertices)
    size = xyz.max(axis=0) - xyz.min(axis=0)
    scale = 27.5/size[1]
    cameras = graybox(scene,builder,group,output,scale)
    if gray_only:
        return

    mats, followers = append_plumage()
    goose = builder.object(group,mats)
    register_variants(scene,goose,followers)
    rig = skeleton(group,goose,builder.weights)
    checks = verify_mesh(goose)
    poses = pose_geometry(goose,rig,builder)
    save_pose_assets(rig)
    glb, wire = export_asset(goose,rig,output)

    view = cameras.objects["Gameplay | fixed rear"]
    top = cameras.objects["Review | top"]
    rear = cameras.objects["Review | rear detail"]
    side = cameras.objects["Review | side"]
    key = cameras.objects["Neutral key"]
    render(scene,top,output,"top",(1040,680))
    render(scene,rear,output,"rear_detail",(1200,780))
    render(scene,side,output,"side",(1040,680))
    ground = cameras.objects["Review Ground"]
    ground.location.z = -.54
    for name, rotations in list(pose_specs().items())[1:]:
        set_pose(rig,rotations)
        render(scene,rear,output,"pose_"+name.lower().replace(" ","_"),(880,580))
    set_pose(rig,{})
    ground.location.z = -8/scale
    reports = {}
    for name, factor, cold in [("1x",1,False),("1x_cool",1,True),("half",.5,False),("half_cool",.5,True)]:
        key.data.color = (.77,.88,1) if cold else (1,1,1)
        key.data.energy = 1.13 if cold else 1.68
        rig.scale = (factor,)*3
        bpy.context.view_layer.update()
        render(scene,view,output,"gameplay_"+name,GAME_SIZE,40)
        reports[name] = {"bounds_px":camera_bounds(scene,view,goose),
                         "crown_samples":crown_samples(scene,view,goose,builder,output/f"preview_gameplay_{name}.png")}
    rig.scale = (1,1,1)
    key.data.color = (1,1,1)
    key.data.energy = 1.68
    flock = flock_preview(scene,view,goose,followers,group,scale,output)

    source = output / f"{STEM}.blend"
    scene["asset_id"] = "CHR-001"
    scene["model_space"] = "BU; +X right, +Y forward, +Z up; Root at torso center"
    scene["preview_game_units_per_BU"] = float(scale)
    scene["pose_assets"] = "QA single-frame actions. Neutral bind pose is the default."
    prepare_view(scene,goose,rig,cameras)
    bpy.ops.wm.save_as_mainfile(filepath=str(source), compress=True)
    roundtrip = compare_roundtrip(scene,goose,rig,glb,cameras,output)
    files = [source,glb,*sorted(output.glob("preview_*.png")),Path(__file__)]
    sha = lambda p: sha256(p.read_bytes()).hexdigest()
    TOOLS["write_json"](output / "asset_manifest.json", {
        "id":"CHR-001","version":"v001","status":"needs_review","blender":bpy.app.version_string,
        "dependencies":{"MAT-001/v001":"done","MAT-002/v001":"needs_review"},
        "source":"Original procedural geometry, skin weights, pose tests and lighting; append MAT-002/v001 plumage.",
        "rights":"Original project production; no external textures or third-party attribution.",
        "reference":["完整AI建模任务包/羽与潮_斑头雁_Blender资源制作规格书_v1.0.pdf (pp. 3, 6–7)",
                     "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift",
                     "Sources/FeatherTide/Rendering/PlayfieldView.swift"],
        "dimensions_BU": dict(zip(("wingspan","bill_to_tail","height"),map(float,size))),
        "scale_objects":[1,1,1],"pivot_BU":[0,0,0],
        "axes_blender":{"right":"+X","up":"+Z","forward":"+Y"},
        "axes_gltf":{"right":"+X","up":"+Y","forward":"-Z"},
        "gltf_from_blender":"(x,y,z) → (x,z,-y)",
        "triangles_lod0":checks["triangles"],
        "bones":record_bones(rig),"pose_tests_degrees_local_xyz":pose_specs(),
        "variants":TINTS,"texture_mapping":{
            p.name:{"from":str(p.relative_to(HERE.parents[5])),"sha256":sha(p),"embedded_in":[".blend",".glb"]}
            for p in sorted((MAT/"textures").glob("*.png"))
        },
        "source_dependency_hashes":{
            name:sha(path) for name,path in [
                ("MAT-002_goose_plumage.blend",MAT/"MAT-002_goose_plumage.blend"),
                ("MAT-001_watercolor_master_generate.py",MASTER/"MAT-001_watercolor_master_generate.py")]
        },
        "camera":{"distance_game_units":180,"pitch_parameter_rad":.48,"vertical_fov_deg":50,
                  "aim_height_game_units":6,"leader_height_game_units":8,"follower_height_game_units":6,
                  "leader_bill_to_tail_game_units":27.5,"preview_game_units_per_BU":float(scale),
                  "render_px":GAME_SIZE,"camera_location_BU":list(view.location)},
        "files":{file.name:sha(file) for file in files},
    })
    TOOLS["write_json"](output / "qa.json", {
        "id":"CHR-001","version":"v001","status":"needs_review",
        "blender":{"source":checks,"poses":poses,"export":wire,"roundtrip":roundtrip,
                   "gameplay_frame_measurements":reports,"flock_preview":flock},
        "visual_review":"Pending image review",
        "realitykit_asset_integration":"pending",
        "iphone_ipad":"pending",
    })


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if not args:
        raise SystemExit("Usage: blender -b --factory-startup --python script.py -- /empty/output [--graybox]")
    faulthandler.enable()
    main(Path(args[0]).resolve(), "--graybox" in args[1:])
