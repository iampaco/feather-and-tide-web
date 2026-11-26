"""Author both landing clips. Shared rig, export, review and QA tools for ANM-007–009."""
import argparse
import json
import math
import runpy
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1]
CHR = LIBRARY / "CHR-001" / "v001"
CRUISE_DIR = LIBRARY / "ANM-001" / "v001"
CHR_BLEND = CHR / "CHR-001_goose_rig.blend"
CHR_GLB = CHR / "CHR-001_goose_rig.glb"
CRUISE_BLEND = CRUISE_DIR / "ANM-001_cruise_flap.blend"
CRUISE_SCRIPT = CRUISE_DIR / "ANM-001_cruise_flap_generate.py"
BLEND_SCRIPT = LIBRARY / "ANM-003" / "v001" / "ANM-003_glide_circle_generate.py"
TOOLS = runpy.run_path(str(CRUISE_SCRIPT))
BLEND = runpy.run_path(str(BLEND_SCRIPT))
REF = TOOLS["REFERENCE"]
TIME, EVAL, DIGEST, DUMP = (TOOLS[k] for k in ("time_set", "evaluated", "digest", "dump"))
CURVES, ACTION, SET, SAMPLE, SMOOTH = (BLEND[k] for k in ("curves","make_action","set_action","sample_action","smoothstep"))
FPS, GAME = 48, (852, 393)
REAR, TOP, DETAIL = BLEND["REAR"], BLEND["TOP"], BLEND["DETAIL"]
SIDE, WIDE_TOP = "Review | side", "Review | group overhead"
STEM = "ANM-007_landing"
MUD, WATER = "Land_Mudflat", "Land_ShallowWater"
LAND_END = 81
CONTACT = {MUD: 47, WATER: 51}
# Spread landing targets across depth as well as width to keep flared wings apart.
SLOTS = [(-42,-15),(42,-15),(0,-29),(-75,-33),(75,-33),(-43,-42),
         (43,-42),(-72,-56),(72,-56),(-30,-69),(30,-69)]
DELAYS = [7,12,17,22,27,32,37,42,47,52,57]


def options():
    p = argparse.ArgumentParser()
    p.add_argument("output", type=Path)
    p.add_argument("--checks", action="store_true")
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    assert not any(args.output.iterdir()), "Use an empty output directory."
    return args


def checked(path, status):
    manifest = json.loads((path.parent / "asset_manifest.json").read_text())
    assert manifest["status"] in status and DIGEST(path) == manifest["files"][path.name], path
    return manifest


def open_rig(label):
    manifest = checked(CHR_BLEND, ("done",))
    checked(CHR_GLB, ("done",))
    bpy.context.preferences.addons["io_scene_gltf2"].preferences.KHR_materials_variants_ui = True
    bpy.ops.wm.open_mainfile(filepath=str(CHR_BLEND))
    scene = bpy.context.scene
    scene.name = label
    scene.render.fps = FPS
    rig, mesh = scene.objects["GooseRig"], scene.objects["Goose_LOD0"]
    assert rig.matrix_world.is_identity and mesh.matrix_world.is_identity
    assert len(rig.data.bones) == 15 and len([i for i in bpy.data.images if i.packed_file]) == 4
    return scene, rig, mesh, manifest, manifest["camera"]["preview_game_units_per_BU"]


def append(path, name):
    with bpy.data.libraries.load(str(path), link=False) as (available, imported):
        assert name in available.actions
        imported.actions = [name]
    action, = imported.actions
    action.use_fake_user = True
    return action


def cruise_reference():
    checked(CRUISE_BLEND, ("done",))
    return append(CRUISE_BLEND, "Cruise_Flap_Loop")


def weight(t):
    return SMOOTH(min(1., max(0., t)))


def rotate(rig, values, bone, degrees, axis=0):
    values[(rig.pose.bones[bone].path_from_id("rotation_euler"), axis)] = math.radians(degrees)


def interpolate(knots, frame):
    for (a, value), (b, target) in zip(knots, knots[1:]):
        if frame <= b:
            return value + (target - value) * weight((frame - a) / (b - a))
    return knots[-1][1]


def decorate(action, description, markers):
    action.asset_mark()
    action.asset_data.description = description
    for frame, label in markers:
        action.pose_markers.new(label).frame = frame


def landing_pose(rig, cruise, name, frame):
    contact = CONTACT[name]
    t = min(6., max(0., frame - 1))
    # Keep the incoming recovery velocity, then take over with a controlled flare.
    source = SAMPLE(cruise, 49 + (frame - 1 if frame < 1 else t * (1 - t / 12)))
    result = dict(source)
    flare = 21 if name == MUD else 25
    curve = lambda *keys: interpolate(keys, frame)
    for side, sign in (("L", 1), ("R", -1)):
        for bone, pitch, sweep in (
            ("WingRoot", curve((1,2),(23,flare),(contact,14),(76,0),(81,0)),
             curve((1,0),(24,0),(contact,13),(76,22),(81,22))),
            ("Elbow", curve((1,1),(24,5),(contact,2),(76,-24),(81,-24)),
             curve((1,0),(28,0),(contact,4),(76,20),(81,20))),
            ("Wrist", curve((1,0),(25,-7),(contact,3),(77,2),(81,2)),
             curve((1,0),(contact,-2),(77,22),(81,22))),
            ("Tip", curve((1,0),(25,-4),(contact,2),(78,-16),(81,-16)),
             curve((1,0),(contact,0),(77,25),(81,25))),
        ):
            rotate(rig,result,f"{bone}.{side}",pitch)
            rotate(rig,result,f"{bone}.{side}",sign*sweep,2)
        rotate(rig,result,f"Foot.{side}",curve((1,0),(17,0),(contact-8,-53),(contact,-54),(68,-54),(81,-54)))
        for bone,twist in (("WingRoot",17),("Elbow",32),("Wrist",15),("Tip",-7)):
            rotate(rig,result,f"{bone}.{side}",sign*twist*weight((frame-contact)/(77-contact)),1)
    rotate(rig,result,"Body",curve((1,0),(25,6),(contact,2),(contact+8,-2),(71,0),(81,0)))
    rotate(rig,result,"Neck",curve((1,0),(25,-3),(contact,2),(contact+9,-5),(75,-6),(81,-6)))
    rotate(rig,result,"Head",curve((1,0),(25,-3),(contact,-1),(contact+9,5),(76,5),(81,5)))
    rotate(rig,result,"Tail",curve((1,0),(24,3),(contact,0),(75,2),(81,2)))
    for key in result:
        if key[0].endswith(".location"):
            result[key] = 0.
    w = weight((frame-1)/14)
    return {key:(1-w)*source.get(key,0.)+w*value for key,value in result.items()}


def landing_actions(rig, cruise):
    clips = {}
    for name in (MUD, WATER):
        action = ACTION(rig, name, lambda f: landing_pose(rig, cruise, name, f), list(range(1,LAND_END+1,2)))
        decorate(action, "In-place landing; the game supplies altitude, deceleration and ground contact.",
                 [(1,"Cruise recovery"),(23,"Flare"),(CONTACT[name],"Contact"),(LAND_END,"Stand / Rest_Idle entry")])
        clips[name] = action
    return clips


def geometry(mesh):
    parts = TOOLS["mesh_parts"](mesh.data)
    pairs = [("Body and crown", n) for n in parts if n.startswith(
        ("Outer primary","Flight feather 7","Flight feather 8","Flight feather 9"))]
    pairs += [("Wing.L","Wing.R"),("Foot.L","Foot.R")]
    pairs += [(part,f"Wing.{s}") for s in "LR" for part in ("Bill",f"Foot.{s}")]
    feet = {s: np.unique(parts[f"Foot.{s}"]) for s in "LR"}
    edges = np.array([tuple(e.vertices) for e in mesh.data.edges])
    rest = np.array([tuple(v.co) for v in mesh.data.vertices])
    length = np.linalg.norm(rest[edges[:,0]]-rest[edges[:,1]],axis=1)
    return parts,pairs,feet,edges,length


def scan(scene, mesh, rig, action, ground=False):
    parts,pairs,feet,edges,length = geometry(mesh)
    SET(rig, action)
    start,end = action.frame_range
    poses, feet_min, ratios = {}, [], [1.,1.]
    for index in range(round(2*start), round(2*end)+1):
        frame = index/2
        TIME(scene,frame)
        root = rig.pose.bones["Root"]
        assert rig.matrix_world.is_identity and mesh.matrix_world.is_identity
        assert root.matrix_basis.is_identity and root.head.length < 1e-8
        points = EVAL(mesh)
        assert np.isfinite(points).all()
        poses[frame] = points
        coords = [tuple(p) for p in points]
        trees = {n:BVHTree.FromPolygons(coords,tri,all_triangles=True) for n,tri in parts.items()}
        assert all(trees["Body and crown"].overlap(trees[f"Wing.{s}"]) for s in "LR"), (action.name,frame,"shoulder")
        hits = [(a,b) for a,b in pairs if trees[a].overlap(trees[b])]
        assert not hits, (action.name,frame,hits)
        edge = np.linalg.norm(points[edges[:,0]]-points[edges[:,1]],axis=1)/length
        ratios = [min(ratios[0],float(edge.min())),max(ratios[1],float(edge.max()))]
        feet_min.append([float(points[feet[s],2].min()) for s in "LR"])
    assert ratios[0] > .39 and ratios[1] < 1.68, (action.name,ratios)
    report = {"samples":len(poses),"step_frames":.5,"edge_length_ratio":ratios,
              "root_and_objects_fixed":"pass","shoulders_and_specified_intersections":"pass","pairs":pairs}
    if ground:
        report["foot_min_z_BU_range_each"] = np.array([np.min(feet_min,axis=0),np.max(feet_min,axis=0)]).T.tolist()
    if action.use_cyclic:
        seam = BLEND["seam_report"](start,end,lambda f: sample_mesh(scene,mesh,f))
        assert seam["position_BU"] < 1e-6 and seam["velocity_delta_BU_per_s"] < .018, (action.name,seam)
        report["loop_seam"] = seam
    return poses,report


def sample_mesh(scene, mesh, frame):
    TIME(scene,frame)
    return EVAL(mesh)


def distance(a,b):
    return float(np.linalg.norm(a-b,axis=1).max())


def join_error(scene,mesh,rig,a,af,b,bf):
    SET(rig,a)
    end = sample_mesh(scene,mesh,af)
    previous = sample_mesh(scene,mesh,af-.02)
    SET(rig,b)
    start = sample_mesh(scene,mesh,bf)
    following = sample_mesh(scene,mesh,bf+.02)
    return {"position_BU":distance(end,start),
            "velocity_delta_BU_per_s":distance(end-previous,following-start)*FPS/.02}


def export(scene,mesh,rig,clips,output):
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    actions = list(clips.values())
    SET(rig,actions[0])
    tracks = []
    for action in actions[1:]:
        track = rig.animation_data.nla_tracks.new()
        track.name = action.name
        track.strips.new(action.name,1,action).action_slot = action.slots[0]
        tracks.append(track)
    scene.frame_set(1)
    bpy.ops.export_scene.gltf(filepath=str(output),export_format="GLB",use_selection=True,
                              export_yup=True,export_animation_mode="ACTIONS",
                              export_anim_single_armature=False,export_force_sampling=True,
                              export_anim_slide_to_zero=True)
    for track in tracks:
        rig.animation_data.nla_tracks.remove(track)
    doc,blob = REF["load_glb"](output)
    base,original = REF["load_glb"](CHR_GLB)
    for field in ("nodes","meshes","materials","extensions"):
        assert doc[field] == base[field], field
    assert len(doc["meshes"]) == len(doc["skins"]) == len(doc["scenes"]) == 1
    assert not doc.get("cameras")
    assert doc["skins"][0]["joints"] == base["skins"][0]["joints"]
    packed = TOOLS["packed_accessor"]
    indices = [i for p in doc["meshes"][0]["primitives"] for i in [*p["attributes"].values(),p["indices"]]]
    for i in indices:
        assert packed(doc,blob,doc["accessors"][i]) == packed(base,original,base["accessors"][i])
    def bind(document,binary):
        return packed(document,binary,document["accessors"][document["skins"][0]["inverseBindMatrices"]])
    assert bind(doc,blob) == bind(base,original)
    def textures(document,binary):
        return [REF["bin_data"](document,binary,i["bufferView"]) for i in document["images"]]
    assert len(doc["images"]) == 4 and textures(doc,blob) == textures(base,original)
    assert sorted(c["name"] for c in doc["animations"]) == sorted(clips)
    report = {}
    for clip in doc["animations"]:
        action = clips[clip["name"]]
        start,end = action.frame_range
        active, targets = [], []
        for channel in clip["channels"]:
            node = doc["nodes"][channel["target"]["node"]]
            prop = channel["target"]["path"]
            sampler = clip["samplers"][channel["sampler"]]
            values = TOOLS["accessor"](doc,blob,sampler["output"])
            default = {"rotation":[0,0,0,1],"translation":[0,0,0],"scale":[1,1,1]}[prop]
            rest = node.get(prop,default)
            delta = np.linalg.norm(values-rest,axis=1)
            if prop == "rotation":
                delta = np.minimum(delta,np.linalg.norm(values+rest,axis=1))
            if delta.max() < 1e-6:
                continue
            assert node["name"] in rig.pose.bones and node["name"] != "Root"
            assert prop == "rotation" or (node["name"],prop) == ("Body","translation")
            times = TOOLS["accessor"](doc,blob,sampler["input"]).ravel()
            assert abs(times[0]) < 1e-7 and abs(times[-1]-(end-start)/FPS) < 1e-6
            active.append(channel)
            targets.append([node["name"],prop])
        assert active
        used = sorted({c["sampler"] for c in active})
        for c in active:
            c["sampler"] = used.index(c["sampler"])
        clip["channels"] = active
        clip["samplers"] = [clip["samplers"][i] for i in used]
        report[action.name] = {"duration_s":(end-start)/FPS,"targets":targets,"root_and_object_channels":0}
    TOOLS["write_glb"](output,doc,blob)
    return {"clips":report,"same_topology_uv_skin_axes_material_variants_and_texture_bytes":"pass"}


def reimport(source,source_mesh,source_rig,clips,motions,path,render):
    window = bpy.context.window
    scene = bpy.data.scenes.new("GLB verification")
    window.scene = scene
    scene.render.fps = FPS
    datablocks = (bpy.data.objects,bpy.data.meshes,bpy.data.armatures,bpy.data.materials,bpy.data.images,bpy.data.actions)
    existing = [set(block) for block in datablocks]
    for name,action in clips.items():
        action.name = "Source | "+name
    bpy.ops.import_scene.gltf(filepath=str(path),bone_heuristic="BLENDER",disable_bone_shape=True)
    created = set(bpy.data.objects)-existing[0]
    mesh, = [o for o in created if o.type == "MESH"]
    rig, = [o for o in created if o.type == "ARMATURE"]
    assert len(created) == 2 and rig.matrix_world.is_identity and mesh.matrix_world.is_identity
    mesh.data.calc_loop_triangles()
    assert len(mesh.data.loop_triangles) == 3940 and mesh.data.uv_layers.active
    assert mesh.modifiers[0].object == rig and len(mesh.data.materials) == len(source_mesh.data.materials)
    assert len({n.image for m in mesh.data.materials for n in m.node_tree.nodes if n.type=="TEX_IMAGE" and n.image}) == 4
    assert set(rig.data.bones.keys()) == set(source_rig.data.bones.keys())
    for b in source_rig.data.bones:
        imported = rig.data.bones[b.name]
        assert (b.parent and b.parent.name) == (imported.parent and imported.parent.name)
        np.testing.assert_allclose(np.asarray(b.matrix_local),np.asarray(imported.matrix_local),atol=1e-5)
    lookup = KDTree(len(source_mesh.data.vertices))
    for v in source_mesh.data.vertices:
        lookup.insert(v.co,v.index)
    lookup.balance()
    indices = []
    for v in mesh.data.vertices:
        _,i,d = lookup.find(v.co)
        assert d < 1e-5
        indices.append(i)
    assert len(set(indices)) == len(source_mesh.data.vertices)
    actions = {s.action.name:s.action for t in rig.animation_data.nla_tracks for s in t.strips}
    if rig.animation_data.action:
        action = rig.animation_data.action
        actions[action.name] = action
    assert set(actions) == set(clips), set(actions)
    for track in list(rig.animation_data.nla_tracks):
        rig.animation_data.nla_tracks.remove(track)
    report = {}
    if render:
        scene.collection.children.link(bpy.data.collections["Review cameras and lights"])
        scene.world = source.world
    for name,action in actions.items():
        SET(rig,action)
        start,end = action.frame_range
        expected = motions[name]
        assert abs(end-start-(max(expected)-min(expected))) < 1e-4
        assert all('"Root"' not in c.data_path and c.data_path.startswith("pose.bones[") for c in CURVES(action))
        errors = [0.,0.]
        for frame,points in expected.items():
            result = sample_mesh(scene,mesh,start+frame-min(expected))
            np.testing.assert_allclose(np.asarray(rig.pose.bones["Root"].matrix_basis),np.eye(4),atol=1e-6)
            index = int(not frame.is_integer())
            errors[index] = max(errors[index],distance(result,points[indices]))
        assert errors[0] < 3e-4 and errors[1] < .008,(name,errors)
        item = {"samples":len(expected),"duration_s":(end-start)/FPS,"max_mesh_error_BU_integer_and_half":errors}
        if clips[name].use_cyclic:
            seam = BLEND["seam_report"](start,end,lambda f:sample_mesh(scene,mesh,f),step=1)
            assert seam["position_BU"] < 1e-5 and seam["velocity_delta_BU_per_s"] < .15,(name,seam)
            item["loop_seam"] = seam
        if render:
            TIME(scene,start+(end-start)*.67)
            REF["render"](scene,scene.objects[DETAIL],path.parent,"glb_"+name.lower(),(864,486),16)
        report[name] = item
    window.scene = source
    bpy.data.scenes.remove(scene)
    bpy.data.batch_remove(ids=set().union(*(set(block)-old for block,old in zip(datablocks,existing))))
    for name,action in clips.items():
        action.name = name
    return {"clips":report,"imported_skin_axes_pivot_scale_and_plumage":"pass"}


def review_scene(source,label,scale,ground_z,ground_color=None):
    scene = bpy.data.scenes.new(label)
    scene.world = source.world
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.collection.children.link(bpy.data.collections["Review cameras and lights"])
    if ground_color:
        ground = scene.objects["Review Ground"].copy()
        ground.data = ground.data.copy()
        ground.name = f"{label} | reference plane"
        ground.location.z = ground_z
        ground.data.materials[0] = REF["plain"](ground.name,ground_color)
        scene.collection.objects.link(ground)
        # Exclude the original floor from this scene's render via a private studio collection.
        studio = bpy.data.collections["Review cameras and lights"]
        scene.collection.children.unlink(studio)
        for obj in studio.objects:
            if obj.name != "Review Ground":
                scene.collection.objects.link(obj)
    scene.camera = scene.objects[REAR]
    REF["camera"](scene.collection,WIDE_TOP,(0,-1.3,8),(0,-1.3,0),ortho=8.7)
    return scene


def actor(scene,group,mesh,rig,action,index,delay=0):
    carrier = bpy.data.objects.new(f"Preview carrier | {index:02}",None)
    group.objects.link(carrier)
    body = rig.copy()
    body.name = f"Review rig | {index:02}"
    group.objects.link(body)
    body.parent = carrier
    body.matrix_basis = Matrix.Identity(4)
    body.animation_data_clear()
    track = body.animation_data_create().nla_tracks.new()
    strip = track.strips.new(action.name,1+delay,action)
    strip.action_slot = action.slots[0]
    strip.extrapolation = "HOLD"
    bird = mesh.copy()
    bird.name = f"Review mesh | {index:02}"
    group.objects.link(bird)
    bird.parent = body
    bird.modifiers["GooseSkin"].object = body
    if index:
        carrier.scale = (.8,)*3
        bird.material_slots[0].link = "OBJECT"
        bird.material_slots[0].material = bpy.data.materials[f"Body_Follower_{'ABC'[(index-1)%3]}"]
    return carrier,bird


def key_carrier(carrier, samples):
    for frame,location in samples:
        carrier.location = location
        carrier.keyframe_insert("location",frame=frame)
    for c in CURVES(carrier.animation_data.action):
        for k in c.keyframe_points:
            k.interpolation = "LINEAR"


def check_group(scene,birds,end,scale,ground=None,stride=1,camera_name=REAR):
    previous = [None]*len(birds)
    margin,low,step = math.inf,math.inf,0.
    intersections = {}
    camera = scene.objects[camera_name]
    mesh = birds[0].data
    mesh.calc_loop_triangles()
    triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
    for f in range(1,end+1,stride):
        scene.frame_set(f)
        points,bounds,trees = [],[],{}
        for i,bird in enumerate(birds):
            pose = EVAL(bird)
            x0,y0,x1,y1 = TOOLS["frame_points"](camera,bird,pose)
            margin = min(margin,x0,y0,GAME[0]-x1,GAME[1]-y1)
            m = bird.matrix_world
            world = pose @ np.array(m.to_3x3()).T + np.array(m.translation)
            points.append(world)
            bounds.append((world.min(axis=0),world.max(axis=0)))
            if ground is not None:
                low = min(low,(world[:,2].min()-ground)*scale)
            if previous[i] is not None:
                step = max(step,float(np.linalg.norm(np.array(m.translation)-previous[i])*scale/stride))
            previous[i] = np.array(m.translation)
        for a in range(len(points)):
            for b in range(a+1,len(points)):
                if np.any(bounds[a][1] < bounds[b][0]) or np.any(bounds[b][1] < bounds[a][0]):
                    continue
                for i in (a,b):
                    if i not in trees:
                        trees[i] = BVHTree.FromPolygons(points[i].tolist(),triangles,all_triangles=True)
                if trees[a].overlap(trees[b]):
                    intersections.setdefault((a,b),[]).append(f)
    assert margin > 0 and not intersections and (ground is None or low > -.006),(scene.name,margin,{k:(min(v),max(v),len(v)) for k,v in intersections.items()},low)
    result = {"frames":len(range(1,end+1,stride)),"frame_step":stride,"birds":len(birds),
              "shared_mesh_datablocks":len({b.data for b in birds}),"min_screen_margin_px":margin,
              "interbird_intersections":sum(map(len,intersections.values())),"max_carrier_step_game_units_per_frame":step}
    if ground is not None:
        result["min_mesh_clearance_game_units"] = float(low)
    return result


def still(scene,camera,frame,output,name,size=GAME):
    scene.frame_set(frame)
    REF["render"](scene,scene.objects[camera],output,name,size,20)


def video(scene,camera,end,output,name,size=GAME,stride=4):
    REF["render_settings"](scene,size,8)
    scene.render.use_persistent_data = True
    scene.camera = scene.objects[camera]
    with TemporaryDirectory(prefix="ft-goose-review-") as temp:
        path = Path(temp)
        for i,frame in enumerate(range(1,end+1,stride)):
            scene.frame_set(frame)
            scene.render.filepath = str(path/f"{i:04}.png")
            bpy.ops.render.render(write_still=True,scene=scene.name)
        subprocess.run(["ffmpeg","-v","error","-framerate",str(FPS//stride),"-i",str(path/"%04d.png"),
                        "-c:v","libx264","-crf","16","-vf","pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=black",
                        "-pix_fmt","yuv420p","-movflags","+faststart",str(output/f"preview_{name}.mp4")],check=True)


def save(source,rig,action,output,frame):
    bpy.context.window.scene = source
    SET(rig,action)
    source.frame_start,source.frame_end = map(int,action.frame_range)
    source.frame_set(frame)
    source.camera = source.objects[DETAIL]
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    for scene in bpy.data.scenes:
        scene.render.filepath = "//"
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
                area.spaces.active.overlay.show_overlays = False
                area.spaces.active.shading.color_type = "TEXTURE"
    bpy.ops.wm.save_as_mainfile(filepath=str(output),compress=True)


def write_records(output,script,manifest,clips,dependencies,inputs,qa,review):
    identifier = script.name[:7]
    DUMP(output/"qa.json",{"id":identifier,"version":"v001","status":"needs_review","blender":qa})
    DUMP(output/"asset_manifest.json",{
        "id":identifier,"version":"v001","status":"needs_review","blender":bpy.app.version_string,
        "dependencies":dependencies,
        "source_hashes":{str(p.relative_to(LIBRARY)):DIGEST(p) for p in (
            CHR_BLEND,CHR_GLB,CRUISE_BLEND,CRUISE_SCRIPT,BLEND_SCRIPT,CHR/"CHR-001_goose_rig_generate.py",*inputs)},
        "clips":{name:{"frames":list(action.frame_range),"fps":FPS,
                       "duration_s":(action.frame_range[1]-action.frame_range[0])/FPS,
                       "cyclic":action.use_cyclic,"root_motion":False} for name,action in clips.items()},
        "rig":{"triangles_lod0":3940,"bones":15,"scale":[1,1,1],"pivot_BU":[0,0,0],
               "axes_blender":manifest["axes_blender"],"axes_gltf":manifest["axes_gltf"]},
        "rights":"Project-original animation on CHR-001 packed plumage.",
        "variants":manifest["variants"],"texture_mapping":manifest["texture_mapping"],
        "camera":manifest["camera"],"review":review,
        "files":{p.name:DIGEST(p) for p in [script,*sorted(output.iterdir())]},
    })


def landing_camera(review,leader,source_camera):
    camera = review.objects[source_camera].copy()
    camera.name = f"{review.name} | {source_camera}"
    review.collection.objects.link(camera)
    follow = camera.constraints.new("COPY_LOCATION")
    follow.target = leader
    follow.use_offset = True
    return camera.name


def landing_placement(samples,feet,name,scale):
    contact = CONTACT[name]
    all_feet = np.concatenate(list(feet.values()))
    pose = samples[float(contact)]
    # Keep both soles above the reference plane while moving the contact
    # carrier with the animated leg. Heights are engine-side in production.
    anchor = all_feet[np.argmin(pose[all_feet,2])]
    foot_y = float(pose[anchor,1])
    end_y = float(samples[float(LAND_END)][anchor,1])
    result,near = {},[]
    for f,points in samples.items():
        sole = float(points[all_feet,2].min())
        t = min(1.,(f-1)/(contact-1))
        if f < contact:
            z = -sole + (.288+float(samples[1.][all_feet,2].min()))*(1-t)**2
            y = -.75*(1-t)**2 + end_y-foot_y
        else:
            z = -sole
            y = end_y-float(points[anchor,1])
        result[f] = (0,y,z)
        near.append((f,scale*(points[:,2].min()+z),scale*(sole+z)))
    low = min(x[1] for x in near)
    assert low > -.0001,(name,min(near,key=lambda p:p[1]))
    return result,{"contact_frame":contact,"min_mesh_clearance_game_units":float(low),
                   "pre_contact_min_foot_clearance_game_units":float(min(x[2] for x in near if x[0]<contact)),
                   "contact_and_after_max_foot_clearance_game_units":float(max(abs(x[2]) for x in near if x[0]>=contact)),
                   "carrier_uses_flat_reference_plane":"pass"}


def main(args):
    output = args.output
    scene,rig,mesh,manifest,scale = open_rig("ANM-007 | Editable landing")
    cruise = cruise_reference()
    clips = landing_actions(rig,cruise)
    feet = geometry(mesh)[2]
    motions,paths,qa = {},{},{"clips":{}}
    for name,action in clips.items():
        motions[name],metrics = scan(scene,mesh,rig,action,ground=True)
        paths[name],metrics["contact"] = landing_placement(motions[name],feet,name,scale)
        metrics["cruise_entry"] = join_error(scene,mesh,rig,cruise,49,action,1)
        assert metrics["cruise_entry"]["position_BU"] < 1e-6 and metrics["cruise_entry"]["velocity_delta_BU_per_s"] < .025, metrics
        qa["clips"][name] = metrics
    assert distance(motions[MUD][81.],motions[WATER][81.]) < 1e-6
    qa["shared_standing_pose"] = {"mesh_error_BU":distance(motions[MUD][81.],motions[WATER][81.]),
        "approach_span_BU":float(np.ptp(motions[MUD][1.][:,0])),
        "folded_span_BU":float(np.ptp(motions[MUD][81.][:,0]))}
    assert qa["shared_standing_pose"]["folded_span_BU"] < .92
    glb = output/f"{STEM}.glb"
    qa["glb"] = export(scene,mesh,rig,clips,glb)
    qa["roundtrip"] = reimport(scene,mesh,rig,clips,motions,glb,not args.checks)
    reviews = {}
    for name,color in ((MUD,"A6A28B"),(WATER,"7E9F9A")):
        review = review_scene(scene,f"Review | {name}",scale,-8/scale,color)
        bpy.context.window.scene = review
        group = REF["collection"](review,f"{name} | followers")
        birds = []
        count = 12 if name == MUD else 1
        end = LAND_END + (DELAYS[-1] if count == 12 else 0)
        review.frame_end = end
        for i in range(count):
            carrier,bird = actor(review,group if i else review.collection,mesh,rig,clips[name],i,DELAYS[i-1] if i else 0)
            birds.append(bird)
            x,y = SLOTS[i-1] if i else (0,0)
            delay = DELAYS[i-1] if i else 0
            s = .8 if i else 1.
            key_carrier(carrier,[(f+delay,(x/scale,y/scale+p[1],-8/scale+s*p[2])) for f,p in paths[name].items()])
        for f,label in ((1,"Approach"),(23,"Flare"),(CONTACT[name],"Leader contact"),(end,"All settled")):
            review.timeline_markers.new(label,frame=f)
        leader = birds[0].parent.parent
        cameras = {n:landing_camera(review,leader,n) for n in (REAR,DETAIL,TOP,SIDE)}
        review.camera = review.objects[cameras[REAR]]
        qa["clips"][name]["preview"] = check_group(review,birds,end,scale,-8/scale,camera_name=cameras[REAR])
        reviews[name] = (review,group,birds,end,cameras)
        review.frame_set(end)
    save(scene,rig,clips[MUD],output/f"{STEM}.blend",47)
    if not args.checks:
        for name,(review,group,birds,end,cameras) in reviews.items():
            bpy.context.window.scene = review
            label = "mud" if name == MUD else "water"
            group.hide_render = True
            still(review,cameras[REAR],CONTACT[name],output,f"{label}_rear_1x")
            still(review,cameras[SIDE],CONTACT[name],output,f"{label}_contact_side",(920,518))
            still(review,cameras[TOP],81,output,f"{label}_folded_top",(920,518))
            if name == MUD:
                carrier = birds[0].parent.parent
                size_anchor = bpy.data.objects.new("Half-size diagnostic",None)
                review.collection.objects.link(size_anchor)
                size_anchor.parent = carrier
                bird_rig = birds[0].parent
                bird_rig.parent = size_anchor
                size_anchor.scale = (.5,)*3
                size_anchor.location.z = -.5*paths[name][float(CONTACT[name])][2]
                still(review,cameras[REAR],CONTACT[name],output,"mud_rear_half")
                size_anchor.location.z = -.5*paths[name][81.][2]
                still(review,cameras[TOP],81,output,"mud_folded_top_half",(920,518))
                bird_rig.parent = carrier
                group.hide_render = False
                still(review,cameras[REAR],CONTACT[MUD]+22,output,"mud_flock_12")
                still(review,WIDE_TOP,end,output,"mud_flock_12_top",(920,518))
                video(review,cameras[REAR],end,output,"landing_flock_12")
            else:
                video(review,cameras[DETAIL],end,output,"water_landing_detail",(832,468))
    write_records(output,Path(__file__),manifest,clips,{"CHR-001/v001":"done"},(),qa,
                  {"contact_frames":CONTACT,"cruise_entry_frame":49,"follower_delays_frames":DELAYS,
                   "water_plane":"flat reference, no water dynamics","motion":"independent review carriers"})


if __name__ == "__main__":
    main(options())
