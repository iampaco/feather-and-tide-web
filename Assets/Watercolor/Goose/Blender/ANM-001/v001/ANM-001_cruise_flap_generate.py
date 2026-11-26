"""Author, export and check the CHR-001 cruise flap in Blender 5.2.

blender -b --factory-startup --python-exit-code 1 --python this.py -- /empty/output
Add --checks-only to run the geometry and GLB checks without rendering.
"""

from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
import numpy as np
import runpy


HERE = Path(__file__).resolve().parent
CHR = HERE.parents[1] / "CHR-001" / "v001"
CHR_SOURCE = CHR / "CHR-001_goose_rig.blend"
REFERENCE = runpy.run_path(str(CHR / "CHR-001_goose_rig_generate.py"))
STEM = "ANM-001_cruise_flap"
CLIP = "Cruise_Flap_Loop"
FPS = 48
START, END = 1, 53
PERIOD = END - START
GAME_SIZE = (852, 393)
FOLLOWER_SCALE = .8
LEADER_Z, FOLLOWER_Z = 8, 6
FLOCK_POSITIONS = [
    (-45,-25), (45,-25), (0,-30), (-76,-48), (-25,-49), (25,-49),
    (76,-48), (-71,-69), (-23,-71), (23,-72), (71,-71),
]
FLOCK_PHASE_FRAMES = [9, 20, 5, 31, 15, 37, 13, 45, 24, 43, 29]
# Frame 0 is the middle of recovery. Local X is mirrored by the CHR rig.
WING_X = {
    "WingRoot": [(0,6),(10,30),(16,27),(28,-23),(34,-20),(43,-9),(52,6)],
    "Elbow": [(0,3),(13,7),(20,5),(30,-5),(37,-4),(46,0),(52,3)],
    "Wrist": [(0,-2),(10,-12),(15,-12),(24,3),(34,13),(41,6),(48,-3),(52,-2)],
    "Tip": [(0,-2),(13,-7),(18,-7),(25,0),(36,8),(43,5),(49,-2.5),(52,-2)],
}
WRIST_TWIST = [(0,0),(10,-4),(17,-7),(29,3),(36,5),(44,1),(52,0)]
BODY_PITCH = [(0,-.7),(10,1.5),(19,2.0),(32,-1.4),(38,-1.7),(52,-.7)]
BODY_LIFT = [(0,.002),(10,-.005),(19,-.010),(32,.012),(38,.014),(52,.002)]


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def bind_action(rig, action):
    rig.animation_data.action = action
    rig.animation_data.action_slot = action.slots[0]


def author_action(scene, rig):
    scene.render.fps, scene.render.fps_base = FPS, 1.0
    scene.frame_start, scene.frame_end = START, END
    scene.use_preview_range = True
    scene.frame_preview_start, scene.frame_preview_end = START, END - 1
    curves = {}

    def channel(bone_name, prop, axis, keys, transform):
        bone = rig.pose.bones[bone_name]
        bone.rotation_mode = "XYZ"
        path = bone.path_from_id(prop)
        for offset, value in keys:
            getattr(bone, prop)[axis] = transform(value)
            bone.keyframe_insert(prop, index=axis, frame=START+offset, group=bone_name)
        curves[path,axis] = keys

    for side, direction in (("L", -1), ("R", 1)):
        for name, keys in WING_X.items():
            channel(f"{name}.{side}", "rotation_euler", 0, keys, math.radians)
        channel(f"Wrist.{side}", "rotation_euler", 1, WRIST_TWIST,
                lambda angle: direction*math.radians(angle))
    channel("Body","rotation_euler",0,BODY_PITCH,math.radians)
    channel("Neck","rotation_euler",0,BODY_PITCH,lambda angle: -.62*math.radians(angle))
    channel("Head","rotation_euler",0,BODY_PITCH,lambda angle: -.38*math.radians(angle))
    channel("Tail","rotation_euler",0,BODY_PITCH,lambda angle: -.42*math.radians(angle))

    lift_axis = rig.data.bones["Body"].matrix_local.to_3x3().inverted() @ Vector((0,0,1))
    for axis in (1,2):
        channel("Body","location",axis,BODY_LIFT,lambda height: height*lift_axis[axis])

    action = rig.animation_data.action
    action.name = CLIP
    action.use_fake_user = True
    action.asset_mark()
    action.asset_data.description = "ANM-001 / relaxed cruise flap / in-place loop on CHR-001 v001"
    action.use_cyclic = True
    action.use_frame_range = True
    action.frame_start, action.frame_end = START, END
    slot = rig.animation_data.action_slot
    bag = action.layers[0].strips[0].channelbag(slot)
    for curve in bag.fcurves:
        assert (curve.data_path, curve.array_index) in curves
        points = list(curve.keyframe_points)
        # Periodic tangents let recovery pass through the loop boundary
        # without a stop. Monotone tangents keep extrema within the keyed range.
        for index, point in enumerate(points):
            previous = points[index-1] if index > 0 else points[-2]
            following = points[index+1] if index < len(points)-1 else points[1]
            px = previous.co.x - (PERIOD if index == 0 else 0)
            nx = following.co.x + (PERIOD if index == len(points)-1 else 0)
            x, y = point.co
            left, right = x-px, nx-x
            before = (y-previous.co.y)/left
            after = (following.co.y-y)/right
            tangent = 2*before*after/(before+after) if before*after > 0 else 0
            point.interpolation = "BEZIER"
            point.handle_left_type = point.handle_right_type = "FREE"
            point.handle_left = (x-left/3, y-tangent*left/3)
            point.handle_right = (x+right/3, y+tangent*right/3)
        curve.modifiers.new("CYCLES")
        curve.update()
        assert abs(curve.evaluate(START)-curve.evaluate(END)) < 1e-7
    assert all('"Root"' not in c.data_path for c in bag.fcurves)
    assert all(c.data_path.startswith("pose.bones[") for c in bag.fcurves)

    markers = [(1,"Recover · loop in"),(11,"Wing root high"),(16,"Wrist folds"),
               (29,"Wing root low"),(35,"Wrist releases"),(53,"Loop out")]
    for frame, name in markers:
        scene.timeline_markers.new(name, frame=frame)
        action.pose_markers.new(name).frame = frame
    return action, len(bag.fcurves)


def mesh_parts(mesh):
    builder = REFERENCE["model"]()
    assert len(mesh.vertices) == len(builder.vertices)
    assert np.max(np.abs(np.array([tuple(v.co) for v in mesh.vertices])-builder.vertices)) < 1e-7
    assert [tuple(p.vertices) for p in mesh.polygons] == builder.faces
    mesh.calc_loop_triangles()
    triangles = {name: [] for name in builder.parts}
    face_to_part = {face:name for name, faces in builder.parts.items() for face in faces}
    for tri in mesh.loop_triangles:
        triangles[face_to_part[tri.polygon_index]].append(tuple(tri.vertices))
    return triangles


def time_set(scene, frame):
    scene.frame_set(math.floor(frame), subframe=frame-math.floor(frame))


def evaluated(obj):
    obj = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return np.array([tuple(v.co) for v in obj.data.vertices], dtype=np.float64)


def frame_points(cam, obj, points):
    w,h = GAME_SIZE
    # Project all vertices together using the same camera transform as Blender.
    project = np.asarray(cam.calc_matrix_camera(
        bpy.context.evaluated_depsgraph_get(), x=w, y=h, scale_x=1, scale_y=1))
    view = np.asarray(cam.matrix_world.inverted() @ obj.matrix_world)
    xyz = points @ view[:3,:3].T + view[:3,3]
    xyzw = xyz @ project[:,:3].T + project[:,3]
    assert min(xyzw[:,3]) > 0
    x = (xyzw[:,0]/xyzw[:,3] + 1)*w/2
    y = (1 - xyzw[:,1]/xyzw[:,3])*h/2
    return [float(x.min()),float(y.min()),float(x.max()),float(y.max())]


def check_cycle(scene, mesh, rig, camera, scale):
    parts = mesh_parts(mesh.data)
    tested_pairs = [("Body and crown", n) for n in parts
                    if n.startswith(("Outer primary", "Flight feather 7", "Flight feather 8", "Flight feather 9"))]
    tested_pairs += [("Wing.L","Wing.R"),("Foot.L","Foot.R")]
    tested_pairs += [(part,f"Wing.{s}") for s in ("L","R") for part in ("Bill",f"Foot.{s}")]
    edges = np.array([tuple(edge.vertices) for edge in mesh.data.edges])
    rest = np.array([tuple(v.co) for v in mesh.data.vertices])
    base_edges = np.linalg.norm(rest[edges[:,0]]-rest[edges[:,1]], axis=1)
    lookup = KDTree(len(rest))
    for index, point in enumerate(rest):
        lookup.insert(point,index)
    lookup.balance()
    mirror = []
    for point in rest:
        _,index,dist = lookup.find((-point[0],point[1],point[2]))
        assert dist < 1e-6
        mirror.append(index)

    sampled = np.arange(START,END+.5,.5)
    trace = []
    meshes = []
    min_edge, max_edge, mirror_error = 1, 1, 0
    body_forward = rig.data.bones["Head"].matrix_local.to_3x3().inverted() @ Vector((0,1,0))
    for frame in sampled:
        time_set(scene,float(frame))
        assert rig.location.length < 1e-8 and rig.pose.bones["Root"].head.length < 1e-8
        assert rig.pose.bones["Root"].matrix_basis.is_identity
        assert abs((rig.pose.bones["Head"].matrix.to_3x3() @ body_forward).normalized().y - 1) < 1e-6
        points = evaluated(mesh)
        assert np.isfinite(points).all()
        meshes.append(points)
        mirror_error = max(mirror_error, float(np.max(np.abs(points[mirror]-points*[-1,1,1]))))
        ratios = np.linalg.norm(points[edges[:,0]]-points[edges[:,1]], axis=1)/base_edges
        min_edge, max_edge = min(min_edge,float(ratios.min())),max(max_edge,float(ratios.max()))
        verts = [tuple(v) for v in points]
        trees = {part:BVHTree.FromPolygons(verts,faces,all_triangles=True) for part,faces in parts.items()}
        assert all(trees["Body and crown"].overlap(trees[f"Wing.{s}"]) for s in ("L","R")), frame
        hits = [(a,b) for a,b in tested_pairs if trees[a].overlap(trees[b])]
        assert not hits, (frame,hits)
        z = float(points[:,2].min())
        trace.append({
            "frame":float(frame),"min_z_BU":z,
            "leader_clearance":LEADER_Z+scale*z,
            "follower_clearance":FOLLOWER_Z+FOLLOWER_SCALE*scale*z,
            "body_z_BU":float(rig.pose.bones["Body"].head.z),
            "root_x_deg":math.degrees(rig.pose.bones["WingRoot.L"].rotation_euler.x),
            "wrist_x_deg":math.degrees(rig.pose.bones["Wrist.L"].rotation_euler.x),
            "bounds_px":frame_points(camera,mesh,points),
        })

    time_set(scene,START-.02)
    before = evaluated(mesh)
    time_set(scene,START+.02)
    after = evaluated(mesh)
    seam = float(np.max(np.linalg.norm(meshes[-1]-meshes[0],axis=1)))
    speed_jump = float(np.max(np.linalg.norm(after+before-2*meshes[0],axis=1))/.02*FPS)
    assert seam < 1e-6 and speed_jump < .016, (seam,speed_jump)
    assert mirror_error < 1e-5 and min_edge > .58 and max_edge < 1.45, (mirror_error,min_edge,max_edge)
    lowest = min(trace, key=lambda x:x["min_z_BU"])
    assert min(lowest["leader_clearance"],lowest["follower_clearance"]) > 1.0, lowest
    assert all(0 <= x0 < x1 <= GAME_SIZE[0] and 0 <= y0 < y1 <= GAME_SIZE[1]
               for x0,y0,x1,y1 in [x["bounds_px"] for x in trace])
    high = max(trace,key=lambda r:r["root_x_deg"])
    wrist = max(trace,key=lambda r:r["wrist_x_deg"])
    low = min(trace,key=lambda r:r["root_x_deg"])
    assert high["frame"] < low["frame"] < wrist["frame"]
    time_set(scene,START)
    return {
        "samples":len(trace),"sample_step_frames":.5,"tested_nonadjacent_pairs":len(tested_pairs),
        "shoulder_attachment_all_samples":"pass","tested_intersections":"pass",
        "edge_length_ratio_range":[min_edge,max_edge],"left_right_mirror_error_BU":mirror_error,
        "seam_position_error_BU":seam,"seam_velocity_finite_difference_BU_per_s":speed_jump,
        "root_stationary_and_heading_preserved":"pass",
        "lowest":lowest,"leader_clearance_game_units":lowest["leader_clearance"],
        "follower_clearance_game_units":lowest["follower_clearance"],
        "root_peak_frame":high["frame"],"root_low_frame":low["frame"],
        "wrist_release_peak_frame":wrist["frame"],"wrist_lag_after_root_low_s":(wrist["frame"]-low["frame"])/FPS,
        "body_lift_range_BU":[min(t["body_z_BU"] for t in trace),max(t["body_z_BU"] for t in trace)],
        "screen_bbox_envelope_px":[min(t["bounds_px"][0] for t in trace),min(t["bounds_px"][1] for t in trace),
                                    max(t["bounds_px"][2] for t in trace),max(t["bounds_px"][3] for t in trace)],
    }, {float(f):m for f,m in zip(sampled,meshes)}


def accessor(document, binary, index):
    item = document["accessors"][index]
    view = document["bufferViews"][item["bufferView"]]
    assert item["componentType"] == 5126 and "byteStride" not in view
    columns = {"SCALAR":1,"VEC3":3,"VEC4":4}[item["type"]]
    start = view.get("byteOffset",0) + item.get("byteOffset",0)
    return np.frombuffer(binary,dtype="<f4",offset=start,count=item["count"]*columns).reshape(-1,columns)


def packed_accessor(document, binary, item):
    assert item.get("byteOffset",0) == 0
    return REFERENCE["bin_data"](document,binary,item["bufferView"])


def write_glb(path, document, binary):
    import struct

    json_bytes = json.dumps(document, separators=(",",":"), ensure_ascii=False).encode()
    json_bytes += b" " * (-len(json_bytes)%4)
    path.write_bytes(struct.pack("<4sIII4s",b"glTF",2,28+len(json_bytes)+len(binary),
                                 len(json_bytes),b"JSON") + json_bytes +
                     struct.pack("<I4s",len(binary),b"BIN\x00") + binary)


def export_glb(scene, mesh, rig, path):
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = rig
    # Export the base mesh at bind pose. The active action remains available
    # to the exporter for sampling its motion channels.
    scene.frame_set(START)
    bpy.ops.export_scene.gltf(filepath=str(path),export_format="GLB",use_selection=True,
                              export_yup=True,export_animations=True,export_force_sampling=True,
                              export_animation_mode="ACTIVE_ACTIONS",export_anim_single_armature=False,
                              export_nla_strips_merged_animation_name=CLIP,
                              export_anim_slide_to_zero=True)
    load = REFERENCE["load_glb"]
    doc, binary = load(path)
    model, source_binary = load(CHR/"CHR-001_goose_rig.glb")
    clip, = doc["animations"]
    assert clip["name"] == CLIP
    nodes = doc["nodes"]
    source_nodes = {n["name"]:n for n in model["nodes"]}
    assert {n["name"] for n in nodes} == set(source_nodes)
    for node in nodes:
        original = source_nodes[node["name"]]
        for prop, default in (("translation",[0,0,0]),("rotation",[0,0,0,1]),("scale",[1,1,1])):
            np.testing.assert_allclose(node.get(prop,default),original.get(prop,default),atol=1e-6)
    assert len(doc["meshes"]) == len(doc["skins"]) == 1
    primitives = doc["meshes"][0]["primitives"]
    rest_primitives = model["meshes"][0]["primitives"]
    assert len(primitives) == len(rest_primitives)
    for prim, original in zip(primitives,rest_primitives):
        assert prim["attributes"].keys() == original["attributes"].keys()
        for prop in prim["attributes"]:
            a = doc["accessors"][prim["attributes"][prop]]
            b = model["accessors"][original["attributes"][prop]]
            assert a["count"] == b["count"]
            assert packed_accessor(doc,binary,a) == packed_accessor(model,source_binary,b), prop
        a = doc["accessors"][prim["indices"]]
        b = model["accessors"][original["indices"]]
        assert a["count"] == b["count"]
        assert packed_accessor(doc,binary,a) == packed_accessor(model,source_binary,b)
    assert {nodes[i]["name"] for i in doc["skins"][0]["joints"]} == set(rig.data.bones.keys())
    assert doc["extensions"]["KHR_materials_variants"] == model["extensions"]["KHR_materials_variants"]
    assert len(doc["images"]) == len(model["images"]) == 4
    packed = REFERENCE["bin_data"]
    assert {sha256(packed(doc,binary,i["bufferView"])).hexdigest() for i in doc["images"]} == {
        sha256(packed(model,source_binary,i["bufferView"])).hexdigest() for i in model["images"]}

    # Blender can bake redundant constant channels for bones, including Root.
    # Leave those at the bind transforms so the file carries no Root track.
    active = []
    ignored = []
    quaternion_seam = 0
    translation_seam = 0
    for channel in clip["channels"]:
        node = nodes[channel["target"]["node"]]["name"]
        prop = channel["target"]["path"]
        sampler = clip["samplers"][channel["sampler"]]
        values = accessor(doc,binary,sampler["output"])
        if np.max(np.abs(values-values[0])) < 1e-6:
            if prop == "rotation":
                assert abs(float(values[0] @ nodes[channel["target"]["node"]].get(prop,[0,0,0,1]))) > 1-1e-6
            else:
                default = [1,1,1] if prop == "scale" else [0,0,0]
                np.testing.assert_allclose(values[0],nodes[channel["target"]["node"]].get(prop,default),atol=1e-6)
            ignored.append((node,prop))
            continue
        assert node in rig.data.bones and node != "Root"
        assert prop == "rotation" or (node,prop) == ("Body","translation"), (node,prop)
        times = accessor(doc,binary,sampler["input"]).ravel()
        assert abs(times[0]) < 1e-7 and abs(times[-1]-PERIOD/FPS) < 1e-6
        if prop == "rotation":
            q0,q1 = values[0].astype(float),values[-1].astype(float)
            q0,q1 = q0/np.linalg.norm(q0),q1/np.linalg.norm(q1)
            quaternion_seam = max(quaternion_seam,min(np.linalg.norm(q0-q1),np.linalg.norm(q0+q1)))
        else:
            translation_seam = float(np.linalg.norm(values[-1]-values[0]))
        active.append(channel)
    assert quaternion_seam < 1e-6 and translation_seam < 1e-6
    selected_samplers = sorted({channel["sampler"] for channel in active})
    for channel in active:
        channel["sampler"] = selected_samplers.index(channel["sampler"])
    clip["channels"] = active
    clip["samplers"] = [clip["samplers"][i] for i in selected_samplers]
    if ignored:
        write_glb(path,doc,binary)
    assert len(active) == 13
    return {"name":CLIP,"duration_s":PERIOD/FPS,"channels":len(active),
            "animated_targets":sorted([nodes[c["target"]["node"]]["name"]+"."+c["target"]["path"]
                                       for c in active]),
            "quaternion_seam_error":quaternion_seam,"translation_seam_error":translation_seam,
            "root_channels":0,"same_joint_rest_transforms":"pass","same_packed_texture_bytes":"pass",
            "same_exported_mesh_and_skin_attributes":"pass"}


def roundtrip(source_scene, source_mesh, rig, asset, output, source_motion, render_preview):
    window = bpy.context.window
    scene = bpy.data.scenes.new("ANM-001 | GLB round-trip")
    window.scene = scene
    scene.render.fps, scene.render.fps_base = FPS, 1
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(asset),bone_heuristic="BLENDER",disable_bone_shape=True)
    imported = set(bpy.data.objects)-before
    mesh, = [o for o in imported if o.type == "MESH"]
    armature, = [o for o in imported if o.type == "ARMATURE"]
    assert set(armature.data.bones.keys()) == set(rig.data.bones.keys())
    for bone in rig.data.bones:
        other = armature.data.bones[bone.name]
        assert (bone.parent and bone.parent.name) == (other.parent and other.parent.name)
        np.testing.assert_allclose(np.asarray(bone.matrix_local),np.asarray(other.matrix_local),atol=1e-5)
    assert tuple(armature.scale) == (1,1,1) and armature.location.length < 1e-6
    action = armature.animation_data.action
    if not action:
        strip, = [st for track in armature.animation_data.nla_tracks for st in track.strips]
        action = strip.action
        for track in armature.animation_data.nla_tracks:
            track.mute = True
        bind_action(armature,action)
    assert action.name.startswith(CLIP)
    first,last = action.frame_range
    assert abs(last-first-PERIOD) < 1e-4, (first,last)
    base = KDTree(len(source_mesh.data.vertices))
    for vert in source_mesh.data.vertices:
        base.insert(vert.co,vert.index)
    base.balance()
    indices = []
    for vert in mesh.data.vertices:
        _,index,distance = base.find(mesh.matrix_world@vert.co)
        assert distance < 1e-5, distance
        indices.append(index)
    assert len(set(indices)) == len(source_mesh.data.vertices)
    max_key_error, max_subframe_error = 0,0
    for phase,expected in source_motion.items():
        time_set(scene,float(first+phase-START))
        root = armature.pose.bones["Root"]
        assert root.head.length < 1e-6 and np.max(np.abs(np.asarray(root.matrix_basis)-np.eye(4))) < 1e-6
        error = float(np.max(np.linalg.norm(evaluated(mesh)-expected[indices],axis=1)))
        if phase.is_integer():
            max_key_error = max(max_key_error,error)
        else:
            max_subframe_error = max(max_subframe_error,error)
    assert max_key_error < 3e-4 and max_subframe_error < .008, (max_key_error,max_subframe_error)
    time_set(scene,float(first))
    initial = evaluated(mesh)
    time_set(scene,float(last))
    seam = float(np.max(np.linalg.norm(evaluated(mesh)-initial,axis=1)))
    assert seam < 1e-5, seam
    if render_preview:
        group = bpy.data.collections["Review cameras and lights"]
        scene.collection.children.link(group)
        scene.world = source_scene.world
        time_set(scene,float(first+10))
        REFERENCE["render"](scene,group.objects["Review | rear detail"],output,"glb_roundtrip",(1040,680),24)
    window.scene = source_scene
    bpy.data.scenes.remove(scene)
    for obj in imported:
        bpy.data.objects.remove(obj,do_unlink=True)
    return {"duration_s":float((last-first)/FPS),"samples":len(source_motion),
            "max_vertex_error_keyframes_BU":max_key_error,
            "max_vertex_error_half_frames_BU":max_subframe_error,
            "loop_seam_error_BU":seam,"same_hierarchy_and_local_axes":"pass",
            "root_fixed":"pass"}


def add_followers(scene, mesh, rig, action, scale):
    group = REFERENCE["collection"](scene,"Flock review | shared mesh")
    slot = rig.animation_data.action_slot
    for i, ((x,y), phase) in enumerate(zip(FLOCK_POSITIONS,FLOCK_PHASE_FRAMES)):
        copy_rig = rig.copy()
        copy_rig.name = f"FlockRig.{i+1:02}"
        group.objects.link(copy_rig)
        copy_rig.location = (x/scale,y/scale,-2/scale)
        copy_rig.scale = (FOLLOWER_SCALE,)*3
        copy_rig.animation_data_clear()
        track = copy_rig.animation_data_create().nla_tracks.new()
        strip = track.strips.new(CLIP,START-PERIOD,action)
        strip.action_slot = slot
        strip.action_frame_start, strip.action_frame_end = START, END
        strip.repeat = 3
        strip.frame_start = START-PERIOD-phase
        strip.frame_end = strip.frame_start + 3*PERIOD
        bird = mesh.copy()
        bird.name = f"Follower.{i+1:02}"
        group.objects.link(bird)
        bird.parent = copy_rig
        bird.material_slots[0].link = "OBJECT"
        bird.material_slots[0].material = bpy.data.materials[f"Body_Follower_{'ABC'[i%3]}"]
        bird.modifiers["GooseSkin"].object = copy_rig
    return group


def check_flock(scene, camera, leader, group, motion):
    followers = sorted((obj for obj in group.objects if obj.type == "MESH"), key=lambda obj: obj.name)
    assert len(followers) == 11 and all(obj.data == leader.data for obj in followers)
    union = np.array([math.inf,math.inf,-math.inf,-math.inf])
    margin = math.inf
    for frame in range(START,END):
        scene.frame_set(frame)
        for index,obj in enumerate([leader,*followers]):
            pose = evaluated(obj)
            offset = 0 if index == 0 else FLOCK_PHASE_FRAMES[index-1]
            assert np.max(np.abs(pose-motion[float(START+(frame-START+offset)%PERIOD)])) < 2e-6, (frame,obj.name)
            bounds = frame_points(camera,obj,pose)
            assert 0 <= bounds[0] < bounds[2] <= GAME_SIZE[0] and 0 <= bounds[1] < bounds[3] <= GAME_SIZE[1], (frame,obj.name,bounds)
            union[:2] = np.minimum(union[:2],bounds[:2])
            union[2:] = np.maximum(union[2:],bounds[2:])
            margin = min(margin,bounds[0],bounds[1],GAME_SIZE[0]-bounds[2],GAME_SIZE[1]-bounds[3])
    return {"sampled_frames":PERIOD,"leader":1,"followers":11,"mesh_datablocks":1,
            "phase_offsets_frames":FLOCK_PHASE_FRAMES,"follower_positions_game_xy":FLOCK_POSITIONS,
            "frame_envelope_px":union.tolist(),"min_screen_margin_px":margin,
            "all_poses_match_phase_shifted_source":"pass"}


def video(scene, camera, output, name, size, samples=12):
    REFERENCE["render_settings"](scene,size,samples)
    scene.camera = camera
    with TemporaryDirectory(prefix="anm-001-frames-") as temp:
        directory = Path(temp)
        for i,frame in enumerate(range(START,END,2)):
            scene.frame_set(frame)
            scene.render.filepath = str(directory / f"{i:03}.png")
            bpy.ops.render.render(write_still=True,scene=scene.name)
        path = output / f"preview_{name}.mp4"
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-framerate",str(FPS//2),
                        "-i",str(directory/"%03d.png"),"-c:v","libx264","-crf","16",
                        "-vf","pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=black",
                        "-pix_fmt","yuv420p","-movflags","+faststart",str(path)],check=True)


def preview(scene, rig, group, views, output):
    game, rear, top = views
    still = REFERENCE["render"]
    group.hide_render = True
    scene.frame_set(11)
    still(scene,top,output,"top_upstroke",(1040,680),24)
    scene.frame_set(29)
    still(scene,top,output,"top_downstroke",(1040,680),24)
    for name, frame in (("upstroke",11),("downstroke",29),("recovery",43)):
        scene.frame_set(frame)
        still(scene,game,output,f"gameplay_1x_{name}",GAME_SIZE,32)
        rig.scale = (.5,)*3
        bpy.context.view_layer.update()
        still(scene,game,output,f"gameplay_half_{name}",GAME_SIZE,32)
        rig.scale = (1,)*3
        bpy.context.view_layer.update()
    video(scene,rear,output,"rear_detail_loop",(960,624),14)
    video(scene,game,output,"gameplay_1x_loop",GAME_SIZE)
    group.hide_render = False
    video(scene,game,output,"gameplay_flock_12_loop",GAME_SIZE)
    scene.frame_set(11)
    still(scene,game,output,"gameplay_flock_12",GAME_SIZE,32)


def main(output, checks_only=False):
    output.mkdir(parents=True,exist_ok=True)
    assert not any(output.iterdir()), "Use an empty directory to preserve previous versions."
    source_manifest = json.loads((CHR/"asset_manifest.json").read_text())
    assert source_manifest["status"] == "done"
    assert digest(CHR_SOURCE) == source_manifest["files"][CHR_SOURCE.name]
    bpy.context.preferences.addons["io_scene_gltf2"].preferences.KHR_materials_variants_ui = True
    bpy.ops.wm.open_mainfile(filepath=str(CHR_SOURCE))
    scene = bpy.context.scene
    scene.name = "ANM-001 | Cruise flap"
    mesh,rig = scene.objects["Goose_LOD0"],scene.objects["GooseRig"]
    assert rig.animation_data.action is None and not rig.animation_data.nla_tracks
    assert tuple(rig.scale) == tuple(mesh.scale) == (1,1,1)
    assert len(rig.data.bones) == 15
    rig["Motion"] = "Cruise_Flap_Loop · in-place · select Play to preview"
    scene["asset_id"] = "ANM-001"
    scene["Source"] = "CHR-001/v001 · approved geometry, rig and plumage"
    scene["Cruise"] = "48 fps · frames 1–53 · Root fixed · phase markers in timeline"
    camera = scene.objects["Gameplay | fixed rear"]
    rear = scene.objects["Review | rear detail"]
    top = scene.objects["Review | top"]
    scale = source_manifest["camera"]["preview_game_units_per_BU"]

    action, curve_count = author_action(scene,rig)
    body, motion = check_cycle(scene,mesh,rig,camera,scale)
    asset = output/f"{STEM}.glb"
    glb = export_glb(scene,mesh,rig,asset)
    playback = roundtrip(scene,mesh,rig,asset,output,motion,not checks_only)
    group = add_followers(scene,mesh,rig,action,scale)
    flock = check_flock(scene,camera,mesh,group,motion)
    group.hide_render = True
    group.hide_viewport = True
    scene.frame_set(START)
    scene.render.filepath = "//"
    REFERENCE["render_settings"](scene,(1040,680),24)
    scene.camera = rear
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    source = output/f"{STEM}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(source),compress=True)
    if not checks_only:
        group.hide_viewport = False
        preview(scene,rig,group,(camera,rear,top),output)

    manifest = {
        "id":"ANM-001","version":"v001","status":"needs_review","blender":bpy.app.version_string,
        "depends":{"CHR-001/v001":"done"},
        "source":"Original keyframed animation on the accepted CHR-001/v001 armature and mesh.",
        "rights":"Original project production; reuses CHR-001 packed plumage; no third-party assets.",
        "source_hashes":{p.name:digest(p) for p in [CHR_SOURCE,CHR/"CHR-001_goose_rig.glb",CHR/"CHR-001_goose_rig_generate.py"]},
        "clip":{"name":CLIP,"start_frame":START,"end_frame":END,"author_fps":FPS,"duration_s":PERIOD/FPS,
                "loop":"Player loops at duration; endpoint is the duplicate boundary sample",
                "root_motion":False,"editable_bezier_curves":curve_count,
                "phase_markers":{str(m.frame):m.name for m in scene.timeline_markers}},
        "rig":{"bones":REFERENCE["record_bones"](rig),"axes_blender":source_manifest["axes_blender"],
               "axes_gltf":source_manifest["axes_gltf"],"triangles":source_manifest["triangles_lod0"],
               "dimensions_BU":source_manifest["dimensions_BU"],"pivot_BU":[0,0,0],"scale":[1,1,1]},
        "variants":source_manifest["variants"],"texture_mapping":source_manifest["texture_mapping"],
        "camera":source_manifest["camera"],
        "files":{p.name:digest(p) for p in [*sorted(output.iterdir()),Path(__file__)]}
    }
    dump(output/"asset_manifest.json",manifest)
    dump(output/"qa.json",{"id":"ANM-001","version":"v001","status":"needs_review",
                           "blender":{"cycle":body,"glb":glb,"roundtrip":playback,"flock":flock},
                           "preview_review":"pending","realitykit":"pending","iphone_ipad":"pending"})
    print("ANM-001 complete", output, flush=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if not args:
        raise SystemExit("Pass an empty output directory after --.")
    main(Path(args[0]).resolve(),"--checks-only" in args[1:])
