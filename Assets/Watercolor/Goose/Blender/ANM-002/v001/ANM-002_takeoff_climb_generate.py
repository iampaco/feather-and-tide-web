"""Build the editable wetland takeoff on CHR-001 and match the ANM-001 handoff.

blender -b --factory-startup --python-exit-code 1 --python this.py -- /empty/output
Use --checks-only to skip images and videos. Full previews require FFmpeg.
"""
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
import numpy as np

HERE = Path(__file__).resolve().parent
ANM = HERE.parents[1] / "ANM-001" / "v001"
CRUISE = runpy.run_path(str(ANM / "ANM-001_cruise_flap_generate.py"))
CHR = CRUISE["CHR"]
REFERENCE = CRUISE["REFERENCE"]
STEM = "ANM-002_takeoff_climb"
CLIP = "Takeoff_Climb"
START, RELEASE, END, REVIEW_END = 1, 25, 81, 101
FPS = CRUISE["FPS"]
GAME_SIZE = CRUISE["GAME_SIZE"]
MARKERS = {
    1:"Wetland · contact", 12:"Head lift", 18:"Load feet", 25:"Release",
    32:"Power downstroke", 43:"Second upstroke", 54:"Climb downstroke",
    81:"Handoff · Cruise_Flap_Loop",
}
# Values use CHR bone local axes. Every channel inherits its final value
# and tangent from frame 1 of the approved cruise action.
WING_X = {
    "WingRoot": [(1,19),(8,21),(16,28),(23,40),(32,-31),(43,42),(54,-27),(65,19),(73,-7)],
    "Elbow": [(1,5),(12,7),(22,11),(34,-5),(45,10),(56,-5),(66,5),(73,-1)],
    "Wrist": [(1,-8),(13,-8),(23,-12),(35,15),(45,-12),(57,15),(67,-5),(73,-5)],
    "Tip": [(1,-2),(13,-4),(24,-7),(36,8),(46,-7),(58,8),(68,-3),(73,-4)],
}
ROOT_SWEEP = [(1,8),(8,8),(15,6),(22,0),(54,0),(73,0)]
ELBOW_SWEEP = [(1,9),(9,9),(15,6),(21,0),(54,0),(73,0)]
WRIST_TWIST = [(1,5),(13,-2),(23,-8),(34,5),(44,-7),(55,5),(66,-2),(73,0)]
BODY_PITCH = [(1,-3),(10,-4),(18,3),(25,11),(36,9),(50,6),(64,3),(73,-1.1)]
BODY_LIFT = [(1,0),(10,-.005),(18,-.016),(25,.008),(34,.017),(44,.010),(55,.016),(67,.002),(73,.006)]
NECK_PITCH = [(1,-12),(8,-11),(13,8),(21,11),(28,4),(44,2),(58,-1),(73,-.4)]
HEAD_PITCH = [(1,10),(10,8),(16,-6),(25,-9),(37,-5),(53,-2),(66,-.8),(73,.25)]
FOOT_PITCH = [(1,-52),(10,-54),(17,-60),(22,-69),(25,-65),(34,10),(43,3),(53,0),(73,0)]
FLOCK_DELAYS = [3,5,1,7,5,8,3,9,6,2,7]


def curves(action):
    return action.layers[0].strips[0].channelbag(action.slots[0]).fcurves


def source_path(name):
    return ANM / f"ANM-001_cruise_flap.{name}"


def author(scene, rig, cruise):
    cruise_curves = {(c.data_path,c.array_index):c for c in curves(cruise)}
    rig.animation_data.action = None
    rig.animation_data.action = bpy.data.actions.new(CLIP)
    authored = {}
    for bone in rig.pose.bones:
        bone.rotation_mode = "XYZ"

    def channel(bone_name, prop, axis, keys, transform):
        bone = rig.pose.bones[bone_name]
        path = bone.path_from_id(prop)
        reference = cruise_curves.get((path,axis))
        end = reference.evaluate(START) if reference else 0
        for frame,value in keys:
            getattr(bone,prop)[axis] = transform(value)
            bone.keyframe_insert(prop,index=axis,frame=frame,group=bone_name)
        getattr(bone,prop)[axis] = end
        bone.keyframe_insert(prop,index=axis,frame=END,group=bone_name)
        authored[path,axis] = reference

    for side,sign in (("L",1),("R",-1)):
        for bone,keys in WING_X.items():
            channel(f"{bone}.{side}","rotation_euler",0,keys,math.radians)
        for bone,keys in (("WingRoot",ROOT_SWEEP),("Elbow",ELBOW_SWEEP)):
            channel(f"{bone}.{side}","rotation_euler",2,keys,lambda angle:sign*math.radians(angle))
        channel(f"Wrist.{side}","rotation_euler",1,WRIST_TWIST,lambda angle:-sign*math.radians(angle))
        channel(f"Foot.{side}","rotation_euler",0,FOOT_PITCH,math.radians)

    for name,keys in (("Body",BODY_PITCH),("Neck",NECK_PITCH),("Head",HEAD_PITCH),
                      ("Tail",[(f,-.42*a) for f,a in BODY_PITCH])):
        channel(name,"rotation_euler",0,keys,math.radians)
    up = rig.data.bones["Body"].matrix_local.to_3x3().inverted() @ Vector((0,0,1))
    for axis in (1,2):
        channel("Body","location",axis,BODY_LIFT,lambda height:height*up[axis])
    action = rig.animation_data.action
    action.use_fake_user = True
    action.asset_mark()
    action.asset_data.description = "ANM-002 / wetland launch / in-place / ends at cruise recovery"
    action.use_frame_range = True
    action.frame_start,action.frame_end = START,END
    for curve in curves(action):
        points = list(curve.keyframe_points)
        reference = authored[curve.data_path,curve.array_index]
        for i,point in enumerate(points):
            x,y = point.co
            prev,nxt = points[max(0,i-1)],points[min(len(points)-1,i+1)]
            left = max(1.,x-prev.co.x)
            right = max(1.,nxt.co.x-x)
            a,b = (y-prev.co.y)/left,(nxt.co.y-y)/right
            tangent = 2*a*b/(a+b) if a*b > 0 else 0
            if i == len(points)-1 and reference:
                first = reference.keyframe_points[0]
                tangent = (first.handle_right.y-first.co.y)/(first.handle_right.x-first.co.x)
            point.interpolation = "BEZIER"
            point.handle_left_type = point.handle_right_type = "FREE"
            point.handle_left = (x-left/3,y-tangent*left/3)
            point.handle_right = (x+right/3,y+tangent*right/3)
        curve.update()
        assert '"Root"' not in curve.data_path

    scene.render.fps,scene.render.fps_base = FPS,1
    scene.frame_start,scene.frame_end = START,END
    scene.use_preview_range = False
    scene.timeline_markers.clear()
    for frame,label in MARKERS.items():
        scene.timeline_markers.new(label,frame=frame)
        action.pose_markers.new(label).frame = frame
    return action


def sample_motion(scene, mesh, rig, launch, cruise):
    time_set,evaluated = CRUISE["time_set"],CRUISE["evaluated"]
    parts = CRUISE["mesh_parts"](mesh.data)
    feet = np.unique(np.array([tri for part in ("Foot.L","Foot.R") for tri in parts[part]]))
    sole = feet[np.argmin([mesh.data.vertices[i].co.z for i in feet])]
    edges = np.array([tuple(e.vertices) for e in mesh.data.edges])
    rest = np.array([tuple(v.co) for v in mesh.data.vertices])
    base_edges = np.linalg.norm(rest[edges[:,0]]-rest[edges[:,1]],axis=1)
    tested_pairs = [("Body and crown", name) for name in parts if name.startswith(
        ("Outer primary","Flight feather 7","Flight feather 8","Flight feather 9"))]
    tested_pairs += [("Wing.L","Wing.R"),("Foot.L","Foot.R")]
    tested_pairs += [(part,f"Wing.{s}") for s in ("L","R") for part in ("Bill",f"Foot.{s}")]
    samples = {}
    ratios = [1.,1.]
    extrema = [None,None]
    for frame in np.arange(START,END+.5,.5):
        time_set(scene,float(frame))
        root = rig.pose.bones["Root"]
        assert root.matrix_basis.is_identity and root.head.length < 1e-8 and rig.location.length < 1e-8
        coords = evaluated(mesh)
        assert np.isfinite(coords).all()
        samples[float(frame)] = coords
        verts = [tuple(v) for v in coords]
        trees = {n:BVHTree.FromPolygons(verts,faces,all_triangles=True) for n,faces in parts.items()}
        assert all(trees["Body and crown"].overlap(trees[f"Wing.{s}"]) for s in ("L","R")), frame
        intersections = [(a,b) for a,b in tested_pairs if trees[a].overlap(trees[b])]
        assert not intersections,(frame,intersections)
        edge = np.linalg.norm(coords[edges[:,0]]-coords[edges[:,1]],axis=1)/base_edges
        for i,index in enumerate((edge.argmin(),edge.argmax())):
            value = float(edge[index])
            if (value < ratios[i] if i == 0 else value > ratios[i]):
                ratios[i] = value
                extrema[i] = (float(frame),rest[edges[index]].tolist())
    assert ratios[0] > .49 and ratios[1] < 1.53,(ratios,extrema)

    time_set(scene,END-.02)
    previous = evaluated(mesh)
    CRUISE["bind_action"](rig,cruise)
    time_set(scene,float(START))
    first = evaluated(mesh)
    time_set(scene,START+.02)
    after = evaluated(mesh)
    cut = float(np.linalg.norm(samples[float(END)]-first,axis=1).max())
    velocity = float(np.linalg.norm(after+previous-2*first,axis=1).max()/.02*FPS)
    assert cut < 1e-6 and velocity < .025,(cut,velocity)
    for frame in range(END+1,REVIEW_END+1):
        time_set(scene,START+frame-END)
        samples[float(frame)] = evaluated(mesh)
    CRUISE["bind_action"](rig,launch)
    time_set(scene,float(START))
    return samples,feet,sole,{
        "sample_step_frames":.5,"takeoff_samples":2*(END-START)+1,
        "edge_length_ratio_range":ratios,"shoulder_attachment":"pass",
        "tested_nonadjacent_pairs":len(tested_pairs),"tested_intersections":"pass",
        "root_fixed":"pass","handoff_position_error_BU":cut,
        "handoff_velocity_difference_BU_per_s":velocity,
    }


def placement(samples, feet, sole, scale):
    # A preview carrier represents a flat shore and an engine launch trajectory.
    # During contact it keeps the lower foot surface at the shore and the
    # contact point stationary along the flight axis.
    release_y = samples[float(START)][sole,1] - samples[float(RELEASE)][sole,1]
    path = {}
    for frame,xyz in samples.items():
        if frame <= RELEASE:
            z = -float(xyz[feet,2].min()) + .0001
            y = float(samples[float(START)][sole,1] - xyz[sole,1])
        else:
            age = frame - RELEASE
            t = min(1.,age/(END-RELEASE))
            lift = 1-(1-t)**6
            z0 = -float(samples[float(RELEASE)][feet,2].min()) + .0001
            z = z0 + (.29-z0)*lift + .24*math.sin(math.pi*t)*(1-t)**3
            y = release_y + .0015*age + .00017*age*age
        path[frame] = (y,z)
    rows = []
    for frame,(y,z) in path.items():
        xyz = samples[frame]
        rows.append((frame,scale*(float(xyz[feet,2].min())+z),scale*(float(xyz[:,2].min())+z)))
    contact = [v for v in rows if v[0] <= RELEASE]
    flight = [v for v in rows if v[0] > RELEASE]
    assert min(row[1] for row in rows) >= -1e-6, min(rows,key=lambda r:r[1])
    assert min(row[2] for row in rows) >= -1e-6, min(rows,key=lambda r:r[2])
    return path,{
        "flat_shore_minimum_foot_clearance_game_units":min(row[1] for row in rows),
        "contact_foot_clearance_range_game_units":[min(row[1] for row in contact),max(row[1] for row in contact)],
        "minimum_post_release_any_vertex_clearance_game_units":min(row[2] for row in flight),
        "release_frame":RELEASE,"preview_handoff_altitude_game_units":path[float(END)][1]*scale,
        "preview_trajectory_excluded_from_export":True,
    }


def clip_tracks(path, name):
    doc,binary = REFERENCE["load_glb"](path)
    clip, = doc["animations"]
    assert clip["name"] == name
    tracks = {}
    for channel in clip["channels"]:
        target = channel["target"]
        node = doc["nodes"][target["node"]]["name"]
        sampler = clip["samplers"][channel["sampler"]]
        read = CRUISE["accessor"]
        tracks[node,target["path"]] = (read(doc,binary,sampler["input"]).ravel(),
                                       read(doc,binary,sampler["output"]))
    return doc,binary,tracks


def export(scene, mesh, rig, path):
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = rig
    scene.frame_set(START)
    bpy.ops.export_scene.gltf(filepath=str(path),export_format="GLB",use_selection=True,export_yup=True,
                              export_animation_mode="ACTIVE_ACTIONS",export_anim_single_armature=False,
                              export_nla_strips_merged_animation_name=CLIP,
                              export_force_sampling=True,export_anim_slide_to_zero=True)
    doc,binary,takeoff = clip_tracks(path,CLIP)
    original,base,cruise = clip_tracks(source_path("glb"),"Cruise_Flap_Loop")
    for field in ("nodes","meshes","skins","materials","images","extensions"):
        if field in ("skins","images"):
            # Accessor and buffer view indices may be relocated by the exporter.
            continue
        assert doc[field] == original[field],field
    for p in doc["meshes"][0]["primitives"]:
        for i in [*p["attributes"].values(),p["indices"]]:
            assert CRUISE["packed_accessor"](doc,binary,doc["accessors"][i]) == CRUISE["packed_accessor"](
                original,base,original["accessors"][i])
    skin, = doc["skins"]
    old_skin, = original["skins"]
    assert skin["joints"] == old_skin["joints"]
    assert CRUISE["packed_accessor"](doc,binary,doc["accessors"][skin["inverseBindMatrices"]]) == CRUISE["packed_accessor"](
        original,base,original["accessors"][old_skin["inverseBindMatrices"]])
    packed = REFERENCE["bin_data"]
    assert len(doc["images"]) == 4
    assert [packed(doc,binary,i["bufferView"]) for i in doc["images"]] == [
        packed(original,base,i["bufferView"]) for i in original["images"]]

    nodes = {n["name"]:n for n in doc["nodes"]}
    anim = doc["animations"][0]
    active, max_pose_delta = [],0.
    for c in anim["channels"]:
        node = doc["nodes"][c["target"]["node"]]["name"]
        prop = c["target"]["path"]
        times,values = takeoff[node,prop]
        default = {"rotation":[0,0,0,1],"translation":[0,0,0],"scale":[1,1,1]}[prop]
        rest = np.asarray(nodes[node].get(prop,default))
        if np.max(np.abs(values-values[0])) < 1e-6 and (
            np.linalg.norm(values[0]-rest) < 1e-6 or
            (prop == "rotation" and np.linalg.norm(values[0]+rest) < 1e-6)
        ):
            continue
        assert node != "Root" and node in rig.data.bones
        assert prop == "rotation" or (node,prop) == ("Body","translation")
        assert abs(times[0]) < 1e-7 and abs(times[-1]-(END-START)/FPS) < 1e-6
        initial = cruise[node,prop][1][0] if (node,prop) in cruise else rest
        delta = float(np.linalg.norm(values[-1]-initial))
        if prop == "rotation":
            delta = min(delta,float(np.linalg.norm(values[-1]+initial)))
        max_pose_delta = max(max_pose_delta,delta)
        active.append(c)
    assert max_pose_delta < 1e-6 and len(active) == 15,(max_pose_delta,len(active))
    used = sorted({c["sampler"] for c in active})
    for channel in active:
        channel["sampler"] = used.index(channel["sampler"])
    anim["channels"] = active
    anim["samplers"] = [anim["samplers"][i] for i in used]
    CRUISE["write_glb"](path,doc,binary)
    return {
        "clip":CLIP,"animation_count":1,"root_tracks":0,"channels":len(active),
        "duration_s":(END-START)/FPS,"handoff_gltf_channel_max_error":max_pose_delta,
        "same_mesh_weights_inverse_bind_and_textures":"pass",
    }


def verify_reimport(scene, mesh, rig, path, samples, output, preview):
    other = bpy.data.scenes.new("ANM-002 GLB round-trip")
    window = bpy.context.window
    window.scene = other
    other.render.fps = FPS
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path),bone_heuristic="BLENDER",disable_bone_shape=True)
    imported = set(bpy.data.objects)-before
    new_mesh, = [obj for obj in imported if obj.type == "MESH"]
    new_rig, = [obj for obj in imported if obj.type == "ARMATURE"]
    assert new_rig.location.length < 1e-6 and tuple(new_rig.scale) == (1,1,1)
    assert set(new_rig.data.bones.keys()) == set(rig.data.bones.keys())
    for bone in rig.data.bones:
        imported_bone = new_rig.data.bones[bone.name]
        assert (bone.parent and bone.parent.name) == (imported_bone.parent and imported_bone.parent.name)
        np.testing.assert_allclose(np.asarray(bone.matrix_local),np.asarray(imported_bone.matrix_local),atol=1e-5)
    action = new_rig.animation_data.action
    if not action:
        strip, = [s for t in new_rig.animation_data.nla_tracks for s in t.strips]
        action = strip.action
        for track in new_rig.animation_data.nla_tracks:
            track.mute = True
        CRUISE["bind_action"](new_rig,action)
    first,last = action.frame_range
    assert abs(last-first-(END-START)) < 1e-4
    kd = KDTree(len(mesh.data.vertices))
    for v in mesh.data.vertices:
        kd.insert(v.co,v.index)
    kd.balance()
    indices = []
    for v in new_mesh.data.vertices:
        _,i,d = kd.find(new_mesh.matrix_world@v.co)
        assert d < 1e-5
        indices.append(i)
    assert len(set(indices)) == len(mesh.data.vertices)
    errors = [0.,0.]
    for frame,coords in samples.items():
        if frame > END:
            break
        CRUISE["time_set"](other,float(first+frame-START))
        root = new_rig.pose.bones["Root"]
        assert root.head.length < 1e-6 and np.max(np.abs(np.asarray(root.matrix_basis)-np.eye(4))) < 1e-6
        error = float(np.linalg.norm(CRUISE["evaluated"](new_mesh)-coords[indices],axis=1).max())
        index = int(not frame.is_integer())
        errors[index] = max(errors[index],error)
    assert errors[0] < 3e-4 and errors[1] < .018,errors
    if preview:
        other.collection.children.link(bpy.data.collections["Review cameras and lights"])
        other.world = scene.world
        CRUISE["time_set"](other,float(first+43-START))
        REFERENCE["render"](other,scene.objects["Review | rear detail"],output,"glb_roundtrip",(1040,680),18)
    window.scene = scene
    bpy.data.scenes.remove(other)
    for obj in imported:
        bpy.data.objects.remove(obj,do_unlink=True)
    return {"animated_frame_samples":2*(END-START)+1,"keyframe_mesh_error_BU":errors[0],
            "half_frame_mesh_error_BU":errors[1],"bone_hierarchy_and_local_axes":"pass"}


def save_editable(scene, rig, output):
    scene["asset_id"] = "ANM-002"
    scene["Animation"] = "Takeoff_Climb · in-place · 48 fps · frames 1–81"
    scene["Transition"] = "Start Cruise_Flap_Loop at its frame 1 after takeoff frame 81"
    scene["Trajectory"] = "Set forward speed and altitude in the engine"
    scene.frame_set(START)
    scene.camera = scene.objects["Review | rear detail"]
    scene.render.filepath = "//"
    REFERENCE["render_settings"](scene,(1040,680),20)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{STEM}.blend"),compress=True)


def preview_scene(scene, mesh, rig, launch, cruise, path, scale, output):
    # This scene exists only for the review renders. Export and source retain the fixed rig.
    ground = scene.objects["Review Ground"]
    ground.location.z = 0
    floor = ground.data.materials[0].copy()
    floor.name = "Wetland water and shore | review only"
    ground.data.materials[0] = floor
    tree = floor.node_tree
    geometry = tree.nodes.new("ShaderNodeNewGeometry")
    position = tree.nodes.new("ShaderNodeSeparateXYZ")
    shore = tree.nodes.new("ShaderNodeMapRange")
    shore.inputs["From Min"].default_value = .29
    shore.inputs["From Max"].default_value = .34
    color = tree.nodes.new("ShaderNodeMixRGB")
    color.inputs[1].default_value = (.275,.36,.31,1)
    color.inputs[2].default_value = (.22,.34,.36,1)
    shader = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    tree.links.new(geometry.outputs["Position"],position.inputs[0])
    tree.links.new(position.outputs["Y"],shore.inputs[0])
    tree.links.new(shore.outputs[0],color.inputs[0])
    tree.links.new(color.outputs[0],shader.inputs["Base Color"])

    camera = scene.objects["Gameplay | fixed rear"]
    rear = scene.objects["Review | rear detail"]
    top = scene.objects["Review | top"]
    side = scene.objects["Review | side"]
    for c in (camera,rear,top,side):
        c["offset"] = list(c.location)
    CRUISE["bind_action"](rig,cruise)
    followers = CRUISE["add_followers"](scene,mesh,rig,cruise,scale)
    # The preview reuses one mesh across all birds. Followers launch with short
    # delays so the shared pose does not read as a single synchronized motion.
    followers.hide_render = True
    flock = sorted((o for o in followers.objects if o.type == "MESH"),key=lambda o:o.name)
    assert len(flock) == 11 and all(bird.data == mesh.data for bird in flock)
    for bird in flock:
        bird.parent.animation_data_clear()
    flock_checks = {"sampled_frames":0,"shared_mesh_datablocks":1,
                    "leader":1,"followers":11,"min_screen_margin_px":math.inf,
                    "min_flat_shore_clearance_game_units":math.inf}
    def set_preview(frame, ratio=1, show_flock=False):
        selected = launch if frame <= END else cruise
        if rig.animation_data.action != selected:
            CRUISE["bind_action"](rig,selected)
        scene.frame_set(frame if frame <= END else START+frame-END)
        y,z = path[float(frame)]
        rig.location = (0,y,z)
        rig.scale = (ratio,)*3
        # Preserve the shore contact datum in the reduced-size diagnostic.
        rig.location.z = z*ratio
        # Camera follows the ground position and lifts by the change in
        # carrier altitude from the production cruise reference.
        anchor_z = z - 8/scale
        camera.location = Vector(camera["offset"]) + Vector((0,y,anchor_z))
        for c in (rear,top,side):
            c.location = Vector(c["offset"]) + Vector((0,y,z))
        if show_flock:
            for i,bird in enumerate(flock):
                f = max(START,frame-FLOCK_DELAYS[i])
                yy,zz = path[float(f)]
                xx,base_y = CRUISE["FLOCK_POSITIONS"][i]
                # Place the follower and sample the same action at its delayed time.
                parent = bird.parent
                parent.location = (xx/scale,y+base_y/scale+(yy-y)*.26,zz*.8)
                bag = curves(launch if f <= END else cruise)
                action_frame = f if f <= END else START+f-END
                for curve in bag:
                    value = curve.evaluate(action_frame)
                    bone_name, prop = curve.data_path.split('"].')
                    bone_name = bone_name.split('["')[1]
                    getattr(parent.pose.bones[bone_name],prop)[curve.array_index] = value
                if f > END:
                    for s in ("L","R"):
                        parent.pose.bones[f"Foot.{s}"].rotation_euler.x = 0
        bpy.context.view_layer.update()
        if show_flock:
            flock_checks["sampled_frames"] += 1
            for obj in [mesh,*flock]:
                points = CRUISE["evaluated"](obj)
                bounds = CRUISE["frame_points"](camera,obj,points)
                margin = min(bounds[0],bounds[1],GAME_SIZE[0]-bounds[2],GAME_SIZE[1]-bounds[3])
                assert margin > 0,(frame,obj.name,bounds)
                clearance = float(points[:,2].min())*obj.matrix_world.to_scale().z+obj.matrix_world.translation.z
                assert clearance > -1e-6,(frame,obj.name,clearance)
                flock_checks["min_screen_margin_px"] = min(flock_checks["min_screen_margin_px"],margin)
                flock_checks["min_flat_shore_clearance_game_units"] = min(
                    flock_checks["min_flat_shore_clearance_game_units"],clearance*scale)

    render = REFERENCE["render"]
    for label,frame in (("contact",1),("push",25),("climb",43),("handoff",81)):
        set_preview(frame)
        render(scene,camera,output,f"gameplay_{label}",GAME_SIZE,22)
    set_preview(18)
    render(scene,side,output,"foot_contact",(1040,680),22)
    set_preview(43)
    render(scene,top,output,"top_climb",(1040,680),18)
    set_preview(43,.5)
    render(scene,camera,output,"gameplay_half_climb",GAME_SIZE,22)

    def encode(view, name, size, show_flock=False):
        followers.hide_render = not show_flock
        REFERENCE["render_settings"](scene,size,10)
        scene.camera = view
        with TemporaryDirectory(prefix="ft-takeoff-") as temporary:
            for index,frame in enumerate(range(START,REVIEW_END+1,2)):
                set_preview(frame,show_flock=show_flock)
                scene.render.filepath = str(Path(temporary)/f"{index:03}.png")
                bpy.ops.render.render(write_still=True,scene=scene.name)
            subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-framerate","24",
                            "-i",str(Path(temporary)/"%03d.png"),"-c:v","libx264","-crf","16",
                            "-vf","pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=black",
                            "-pix_fmt","yuv420p","-movflags","+faststart",str(output/f"preview_{name}.mp4")],check=True)

    encode(rear,"rear_detail",(832,540))
    encode(camera,"gameplay",(852,393))
    encode(camera,"gameplay_flock_12",GAME_SIZE,True)
    set_preview(43,show_flock=True)
    render(scene,camera,output,"gameplay_flock_12_still",GAME_SIZE,24)
    return flock_checks


def main(output,checks_only):
    output.mkdir(parents=True,exist_ok=True)
    assert not any(output.iterdir()),"Use an empty output directory."
    manifest = json.loads((ANM/"asset_manifest.json").read_text())
    assert manifest["status"] == "done"
    digest = CRUISE["digest"]
    assert digest(source_path("blend")) == manifest["files"][source_path("blend").name]
    assert digest(source_path("glb")) == manifest["files"][source_path("glb").name]
    bpy.context.preferences.addons["io_scene_gltf2"].preferences.KHR_materials_variants_ui = True
    bpy.ops.wm.open_mainfile(filepath=str(source_path("blend")))
    scene = bpy.context.scene
    scene.name = "ANM-002 | Wetland takeoff"
    rig,mesh = scene.objects["GooseRig"],scene.objects["Goose_LOD0"]
    cruise = rig.animation_data.action
    assert cruise.name == "Cruise_Flap_Loop"
    group = bpy.data.collections["Flock review | shared mesh"]
    for obj in list(group.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    bpy.data.collections.remove(group)

    launch = author(scene,rig,cruise)
    samples,feet,sole,geometry = sample_motion(scene,mesh,rig,launch,cruise)
    scale = manifest["camera"]["preview_game_units_per_BU"]
    carrier,shore = placement(samples,feet,sole,scale)
    path = output/f"{STEM}.glb"
    glb = export(scene,mesh,rig,path)
    reimport = verify_reimport(scene,mesh,rig,path,samples,output,not checks_only)
    save_editable(scene,rig,output)
    flock = None if checks_only else preview_scene(scene,mesh,rig,launch,cruise,carrier,scale,output)
    dump = CRUISE["dump"]
    dump(output/"asset_manifest.json",{
        "id":"ANM-002","version":"v001","status":"needs_review","blender":bpy.app.version_string,
        "depends":{"CHR-001/v001":"done","ANM-001/v001":"done"},
        "source":"Original in-place takeoff on accepted CHR-001 mesh and ANM-001 continuation.",
        "rights":"Original project animation and packed CHR-001 plumage.",
        "source_hashes":{p.name:digest(p) for p in [source_path("blend"),source_path("glb"),ANM/"ANM-001_cruise_flap_generate.py"]},
        "clip":{"name":CLIP,"fps":FPS,"start_frame":START,"end_frame":END,"duration_s":(END-START)/FPS,
                "loop":False,"root_motion":False,"markers":MARKERS,
                "handoff":{"clip":"Cruise_Flap_Loop","frame":1,"time_s":0}},
        "rig":manifest["rig"],"variants":manifest["variants"],"texture_mapping":manifest["texture_mapping"],
        "camera":manifest["camera"],"preview_carrier":{"description":"Blender-only launch placement above a flat shore",
                    "sample_step_frames_through_takeoff":.5,"sample_step_frames_during_preview_cruise":1,
                    "positions_forward_height_BU":carrier},
        "files":{p.name:digest(p) for p in [*sorted(output.iterdir()),Path(__file__)]},
    })
    dump(output/"qa.json",{"id":"ANM-002","version":"v001","status":"needs_review",
          "blender":{"geometry":geometry,"flat_shore":shore,"glb":glb,"roundtrip":reimport,"flock":flock},
          "visual_review":"pending","realitykit":"pending","iphone_ipad":"pending"})
    print("ANM-002 complete",output,flush=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if not args:
        raise SystemExit("Pass an empty output directory after --.")
    main(Path(args[0]).resolve(),"--checks-only" in args[1:])
