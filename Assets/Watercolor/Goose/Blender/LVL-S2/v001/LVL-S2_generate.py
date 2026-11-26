"""S2 branch assembly and independent Blender roundtrip probes."""
from argparse import ArgumentParser
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Quaternion, Vector
from mathutils.bvhtree import BVHTree

HOME = Path(__file__).resolve().parent
MODEL = "LVL-S2_S2_Fork.blend"
EXPORT = "LVL-S2_S2_Fork.glb"
MOVIE = "preview_fixed_rear.mp4"
SIZE = (852, 393)
BU = .036
FOOTPRINT = (-52, 60, 0, 76)
WATER_Z = -.18
WIDTH = 12
DIRECTION = Vector((-.98, .20, 0)).normalized()
GATE_NODES = {"S2_Entry": (0., 0., 0.), "S2_Merge": (0., 76., 0.)}
REST = (3.48, 10.03, .04)
TOL = 5e-5
DEPENDENCIES = {
    "ENV-008": ("ENV-008_LakeShore.glb", "ENV-008_LakeWide.glb"),
    "ENV-010": ("ENV-010_Mouth.glb", "ENV-010_Pass_Left.glb", "ENV-010_Pass_Right.glb"),
    "ENV-012": ("ENV-012_RiverTree_A.glb", "ENV-012_RiverTree_B.glb", "ENV-012_LeaningTree.glb"),
    "ENV-015": ("ENV-015_LakesideRest.glb",),
    "FX-002": ("FX-002_CrosswindWarn.glb", "FX-002_Gust.glb", "runtime_mapping.json"),
    "ENV-018": ("ENV-018_CloudStreak.glb",),
    "CHR-001": ("CHR-001_goose_rig.glb",),
}
# These are graphics review centerlines. The S2 gate, merge and pad are separate exported anchors.
ROUTES = {
    "pass": [(0, 0), (-3.8, 7), (-9.25, 14.5), (-11.6, 20), (-12, 26), (-11.2, 33),
             (-10.95, 38), (-11.4, 45), (-11.5, 51), (-8, 57), (-3.2, 63), (0, 69), (0, 76)],
    "lake": [(0, 0), (4, 4), (12.5, 8), (19.2, 14), (28.8, 23), (30.5, 34),
             (31, 43), (24, 52.5), (21.8, 56.7), (13.4, 61), (4.5, 64.5), (0, 69), (0, 76)],
    "rest_detour": [(12.5, 8), (9.7, 8.3), (6.5, 8.9), (3.48, 10.03),
                    (6.1, 11.35), (10.2, 12.2), (15.2, 13.0), (19.2, 14)],
}
TREE_POINTS = [
    ("RiverTree_A", (-4.9, 14.4), 0), ("RiverTree_B", (-13.7, 14.3), .16),
    ("LeaningTree", (-6.1, 18.3), -.24), ("RiverTree_A", (-16.1, 20.2), .18),
    ("RiverTree_B", (-7.15, 23.2), 0), ("LeaningTree", (-16.35, 25.4), .08),
    ("RiverTree_A", (-7.1, 28), .22), ("RiverTree_B", (-16.4, 31), -.15),
]
CAMERA_SOURCE = "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift"
VIEW_SOURCE = "Sources/FeatherTide/Rendering/PlayfieldView.swift"


def require(condition, detail):
    if not condition:
        raise RuntimeError(str(detail))


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inventory(library):
    sources = {}
    for asset, files in DEPENDENCIES.items():
        folder = library / asset / "v001"
        manifest = read_json(folder / "asset_manifest.json")
        require(manifest["status"] in ("needs_review", "done"), (asset, manifest["status"]))
        qa = read_json(folder / "qa.json")
        require(bool(qa) and (folder / "README.md").stat().st_size > 200, asset)
        declared = manifest.get("files", manifest.get("file_sha256", manifest.get("files_sha256", {})))
        for name in (*files, "asset_manifest.json", "qa.json", "README.md"):
            path = folder / name
            hashed = digest(path)
            if name in files:
                expected = declared.get(name)
                if isinstance(expected, dict):
                    expected = expected.get("sha256")
                require(expected == hashed, ("dep hash mismatch", asset, name, expected, hashed))
            sources[str(path.relative_to(library))] = {"sha256": hashed, "bytes": path.stat().st_size,
                                                      "status": manifest["status"], "version": manifest.get("version")}
    root = library.parents[3]
    swift, view = (root / CAMERA_SOURCE).read_text(), (root / VIEW_SOURCE).read_text()
    require("distance: 180, pitch: 0.48, fieldOfViewDegrees: 50" in swift and "Float(6 + lift)" in swift
            and "altitude: CGFloat(sample.depthLift)" in view and "(body.leader ? 8 : 6) + sample.depthLift" in view,
            "Swift review pose changed")
    return sources, {name: digest(root / name) for name in (CAMERA_SOURCE, VIEW_SOURCE)}


def as_glb(path):
    blob = path.read_bytes()
    magic, version, size, n, kind = struct.unpack_from("<4sIIII", blob)
    require((magic, version, size, kind) == (b"glTF", 2, len(blob), 0x4E4F534A), path)
    return json.loads(blob[20:20+n]), blob[28+n:]


def image_hashes(path):
    document, data = as_glb(path)
    result = set()
    for image in document.get("images", []):
        view = document["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        result.add(hashlib.sha256(data[start:start+view["byteLength"]]).hexdigest())
    return result


def collection(name, parent):
    group = bpy.data.collections.new(name)
    parent.children.link(group)
    return group


def create(name, data, group, parent=None, at=(0, 0, 0)):
    obj = bpy.data.objects.new(name, data)
    group.objects.link(obj)
    obj.parent = parent
    obj.location = at
    return obj


def isolate_import(path, group, parent=None, at=(0, 0, 0)):
    existing = set(bpy.context.scene.objects)
    require(bpy.ops.import_scene.gltf(filepath=str(path), import_pack_images=True) == {"FINISHED"}, path)
    objects = [o for o in bpy.context.scene.objects if o not in existing]
    for obj in objects:
        for prior in list(obj.users_collection):
            prior.objects.unlink(obj)
        group.objects.link(obj)
    for obj in objects:
        if obj.parent is None:
            obj.parent = parent
            obj.location += Vector(at)
    bpy.context.view_layer.update()
    return objects


def dependency(library, asset, file):
    return library / asset / "v001" / file


def grid_mesh(name, verts, faces, material, group, parent=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    if material:
        mesh.materials.append(material)
        uv = mesh.uv_layers.new(name="UVMap")
        for loop in mesh.loops:
            x, y, z = mesh.vertices[loop.vertex_index].co
            uv.data[loop.index].uv = ((x+5)/10, (y+5)/10)
    return create(name, mesh, group, parent)


def plane(name, rect, material, group, parent=None, z=0):
    x0, x1, y0, y1 = rect
    return grid_mesh(name, [(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z)], [(0,1,2,3)], material, group, parent)


def edit_shore(shore):
    """Remove 512 original RestPatch faces and the donor backing south of the seam."""
    bm = bmesh.new()
    bm.from_mesh(shore.data)
    placeholder, south = [], []
    for f in bm.faces:
        center = f.calc_center_median()
        if -1 < center.x < 9 and 5 < center.y < 15:
            require(all(-1-TOL <= v.co.x <= 9+TOL and 5-TOL <= v.co.y <= 15+TOL for v in f.verts),
                    ("unexpected RestPatch straddler", f.index))
            placeholder.append(f)
        if center.y < -TOL:
            require(all(v.co.y <= TOL for v in f.verts), ("south apron straddler", f.index))
            south.append(f)
    require(len(placeholder) == 512 and len(south) > 0, (len(placeholder), len(south)))
    bmesh.ops.delete(bm, geom=[*placeholder, *south], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(shore.data)
    bm.free()
    shore.data.update()
    return {"placeholder_triangles_removed": len(placeholder), "pre_gate_triangles_removed": len(south)}


def apron(shore, group, root):
    material = next(m for m in shore.data.materials if m.name.startswith("GrassFlat"))
    rects = {
        "West apron": (-52,-21.5,0,76), "South pass apron": (-21.5,-1.5,0,10),
        "North pass apron": (-21.5,-1.5,50,76), "Central divider join": (-1.5,-1,0,76),
        "North merge apron": (-1,60,63,76),
    }
    chosen = [plane(name, rect, material, group, root) for name, rect in rects.items()]
    edge = {}
    for v in shore.data.vertices:
        x, y, z = v.co
        if y not in edge or x > edge[y][0]:
            edge[y] = (x, y, z)
    points = sorted(edge.values(), key=lambda point: point[1])
    verts = [p for a in points for p in (a, (60, a[1], 0))]
    faces = [(i,i+1,i+3,i+2) for i in range(0,len(verts)-2,2)]
    chosen.append(grid_mesh("East bank apron", verts, faces, material, group, root))
    return chosen, material


def paint(name, color, emission=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    node = mat.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*color, 1)
    node.inputs["Roughness"].default_value = .87
    if emission:
        node.inputs["Emission Color"].default_value = (*color,1)
        node.inputs["Emission Strength"].default_value = emission
    mat.diffuse_color = (*color, 1)
    return mat


def make_rest_cue(group, root):
    mat = paint("Lakeside rest | pale repair gold", (.65,.72,.41), .25)
    verts, faces = [], []
    for i in range(48):
        angle = i * math.tau / 48
        for r in (1.09, 1.14):
            verts.append((REST[0]+math.cos(angle)*r, REST[1]+math.sin(angle)*r*.73, REST[2]))
        j = 2*i
        k = 2*((i+1)%48)
        faces.append((j,j+1,k+1,k))
    obj = grid_mesh("S2_LakesideRest_Cue", verts, faces, mat, group, root)
    obj["runtime_role"] = "visual finder; zone state and refill owned by game"
    return obj


def ray_tree(objects, evaluated=False):
    verts, faces = [], []
    dg = bpy.context.evaluated_depsgraph_get()
    for item in objects:
        if item.type != "MESH":
            continue
        obj = item.evaluated_get(dg) if evaluated else item
        matrix = obj.matrix_world
        mesh = obj.data
        first = len(verts)
        verts.extend(matrix @ v.co for v in mesh.vertices)
        faces.extend(tuple(first+i for i in face.vertices) for face in mesh.polygons)
    require(bool(faces), "empty mesh ray surface")
    return BVHTree.FromPolygons(verts, faces)


def ground_at(tree, x, y):
    point, _, _, _ = tree.ray_cast((x,y,14), (0,0,-1), 20)
    return point.z if point is not None else None


def select_mesh(items, name):
    return next(o for o in items if o.type == "MESH" and o.name.split(".")[0] == name)


def label_surfaces(items, role):
    for o in items:
        if o.type == "MESH":
            o["s2_role"] = role


def basename(library, asset, name):
    return dependency(library, asset, f"{asset}_{name}.glb")


def assemble(library):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "S2 Fork | fixed follow material review"
    main = collection("S2 Fork | Runtime export", scene.collection)
    root = create("S2_Fork", None, main)
    root["asset_id"] = "LVL-S2"
    root["candidate"] = "needs_review"
    root["BU_per_game_unit"] = BU
    root["axis_map"] = "Blender XYZ -> glTF X,Z,-Y"
    root["game_logic"] = "runtime supplies collisions, wind, checkpoints, energy, rest and route selection"
    ground_group = collection("01 | Ground and independent water", main)
    pass_group = collection("02 | Short pass native terrain", main)
    lakeside_group = collection("03 | Lakeside rest replacement", main)
    wind_group = collection("04 | Shared wind field", main)
    anchors = collection("05 | Game anchors", main)
    simple = lambda asset, name, dest, host=root, at=(0,0,0): isolate_import(
        basename(library, asset, name), dest, host, at)
    shore = select_mesh(simple("ENV-008", "LakeShore", ground_group), "LakeShore")
    cut = edit_shore(shore)
    water = select_mesh(simple("ENV-008", "LakeWide", ground_group), "LakeWide")
    land, grass = apron(shore, ground_group, root)
    pmesh = []
    for part in ("Mouth","Pass_Left","Pass_Right"):
        obj = select_mesh(simple("ENV-010", part, pass_group), part)
        for uv in obj.data.uv_layers.active.data:
            uv.uv.x += .35
            uv.uv.y += .5
        pmesh.append(obj)
    rest = simple("ENV-015","LakesideRest",lakeside_group,root,(4,10,0))
    pad = select_mesh(rest, "LakesideRest_Ground")
    reeds = select_mesh(rest, "LakesideRest_Reeds")
    padwater = select_mesh(rest, "LakesideRest_Water")
    land = [shore, *land, *pmesh, pad]
    label_surfaces(land, "terrain")
    label_surfaces((water,padwater), "water")
    label_surfaces((reeds,), "plant")
    make_rest_cue(lakeside_group,root)
    for name, at in {**GATE_NODES,"S2_Checkpoint_A": (0,0,0), "S2_Pass": (-11.48,17,0),
                     "S2_Lake": (15.1,13.5,WATER_Z), "S2_Rest": REST,
                     "S2_JoinBeforeGate": (0,69,0)}.items():
        node = create(name, None, anchors, root, at)
        node["forward_BU"] = [0.,1.,0.]
    control = create("S2_WindField", None, wind_group, root)
    control["direction"] = list(DIRECTION)
    control["windSpeedBUPerSecond"] = 1.95
    control["strength"] = .82
    control["motionScale"] = 1.
    control["clockSeconds"] = 0.
    control["schedule"] = "spatial envelope: short pass only, advances before band onset"
    terrain = ray_tree(land)
    for i, (variant, (x,y), yaw) in enumerate(TREE_POINTS):
        place = create(f"S2_WindTree_{i+1:02}", None, wind_group, control, (x,y,ground_at(terrain,x,y)))
        place.rotation_euler.z = yaw
        place["s2_phase"] = i*.15
        pieces = simple("ENV-012", variant, wind_group, place)
        for obj in pieces:
            if obj.type == "ARMATURE":
                obj.animation_data_clear()
                obj["s2_wind_tree"] = i+1
        # glTF import adds a display-only custom bone shape. Keep it out of the scene geometry.
        meshes = [obj for obj in pieces if obj.type == "MESH" and not obj.name.startswith("Icosphere")]
        for obj in pieces:
            if obj.type == "MESH" and obj.name.startswith("Icosphere"):
                bpy.data.objects.remove(obj,do_unlink=True)
        label_surfaces(meshes,"plant")
    for variant, lanes in {
        "CrosswindWarn": ((-7.3,20.6,1.48),(-8.1,22.4,1.22),(-9.9,25.8,1.10)),
        "Gust": ((-8.25,25.8,1.65),(-9.05,27.8,1.78),(-8.65,30,1.05),(-10.9,34.7,.66)),
    }.items():
        for i, origin in enumerate(lanes):
            yaw = math.atan2(-DIRECTION.x,DIRECTION.y)
            place = create(f"S2_{variant}_{i+1:02}", None, wind_group, control, origin)
            place.rotation_euler.z = yaw
            place["s2_effect"] = variant
            place["s2_origin"] = list(origin)
            props = simple("FX-002",variant,wind_group,place)
            label_surfaces(props, "fx")
            for prop in props:
                if prop.type == "MESH" and prop.name.split(".")[0] in ("CrownSweep","Leaf"):
                    prop.location.x -= .75 if variant == "CrosswindWarn" else 1.55
                    prop.location.y += .65 + i*.15
                    prop.location.z += .2
    for i, origin in enumerate(((-15.6,34,3.7),(-9.2,37.2,5.10))):
        props = simple("ENV-018","CloudStreak",wind_group,control,origin)
        for cloud in props:
            cloud.name = f"S2_CloudStreak_{i+1}"
            cloud.scale = (.30,.5,.5)
            cloud["s2_cloud_origin"] = list(origin)
            cloud["s2_role"] = "fx"
    bpy.context.view_layer.update()
    return scene, root, main, grass, cut


def catmull(points, steps=24):
    values=[Vector((*xy,0)) for xy in points]
    dense=[]
    for i in range(len(values)-1):
        a=values[max(0,i-1)]
        b,c=values[i:i+2]
        d=values[min(len(values)-1,i+2)]
        for j in range(steps):
            t=j/steps
            dense.append(.5*(2*b+(c-a)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
    return [*dense,values[-1]]


def route_distances(points):
    distance = [0.]
    for a,b in zip(points,points[1:]):
        distance.append(distance[-1] + (b-a).length)
    return distance


def at_distance(points, distances, t):
    import bisect
    t = min(max(t, distances[0]), distances[-1])
    hi = min(max(1,bisect.bisect_left(distances,t)),len(points)-1)
    lo=hi-1
    p = points[lo].lerp(points[hi],(t-distances[lo])/(distances[hi]-distances[lo]))
    direction=(points[min(len(points)-1,hi+2)]-points[max(0,lo-2)]).normalized()
    if p.y >= 70:
        direction=Vector((0,1,0))
    return p,direction


def bodies(scene, library, group):
    items = isolate_import(dependency(library,"CHR-001", "CHR-001_goose_rig.glb"), group)
    source = next(o for o in items if o.type == "MESH")
    dg = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(source.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    require(len(mesh.vertices)>100, "review bird mesh")
    for source in items:
        bpy.data.objects.remove(source,do_unlink=True)
    return [create(f"S2_ReviewGoose_{i+1:02}", mesh, group) for i in range(12)]


def smooth(a,b,x):
    t = min(1., max(0., (x-a)/(b-a)))
    return t*t*(3-2*t)


def tail_coords(index):
    if not index:
        return 0, 0
    rank = (index+1)//2
    return ((1 if index%2 else -1)*min(2.,.57+.28*rank), .85*rank)


def altitude(y):
    # Default is Swift's lead height. This review trajectory climbs smoothly over branch terrain.
    return .288 + .92*smooth(0,7,y) - .52*smooth(63,76,y)


def camera_pose(camera, leader, heading):
    depth_lift = leader.z - 8*BU
    point = Vector((leader.x,leader.y,depth_lift))
    camera.location = point - heading*(180*BU*math.cos(.48)) + Vector((0,0,180*BU*math.sin(.48)))
    aim = point + Vector((0,0,6*BU))
    camera.rotation_euler = (aim - camera.location).to_track_quat("-Z","Y").to_euler()
    return aim


def camera_new(group):
    data = bpy.data.cameras.new("Swift ThirdPersonRig.graybox | 50 degrees vertical")
    data.sensor_fit = "VERTICAL"
    data.sensor_height = 24
    data.lens = 12/math.tan(math.radians(25))
    data.clip_start,data.clip_end = .015, 230
    return create("S2_FixedRear", data, group)


def wind_strength(y):
    return .82*smooth(9,17,y)*(1-smooth(36,47,y))


def apply_wind(scene, branch, y, clock, key=False, frame=1):
    wind = wind_strength(y) if branch=="pass" else 0.
    root=scene.objects["S2_WindField"]
    if key:
        root["clockSeconds"] = clock
        root["strength"] = wind
        for prop in ('["clockSeconds"]','["strength"]'):
            root.keyframe_insert(prop,frame=frame)
    object_direction = Vector((0,0,1)).cross(DIRECTION)
    for obj in list(scene.objects):
        if obj.get("s2_wind_tree"):
            phase = obj.parent.get("s2_phase",0)
            world_rotation = obj.matrix_world.to_quaternion()
            direction = world_rotation.inverted() @ object_direction
            bends = (.85 + .15*math.sin(phase + clock*4))
            for joint,angle in (("Stem",8),("Crown",18)):
                bone = obj.pose.bones.get(joint)
                if bone is not None:
                    axis = bone.bone.matrix_local.to_quaternion().inverted() @ direction
                    bone.rotation_mode="QUATERNION"
                    bone.rotation_quaternion=Quaternion(axis, math.radians(angle)*wind*bends)
                    if key:
                        bone.keyframe_insert("rotation_quaternion",frame=frame)
        if obj.get("s2_effect"):
            factor=wind*smooth(13,21,y) if obj["s2_effect"]=="CrosswindWarn" else wind*smooth(19,25,y)
            obj.scale=(.001+.999*factor,)*3
            adv = math.fmod(clock*1.95, 1.45)
            obj.location=Vector(obj["s2_origin"])+DIRECTION*adv
            if key:
                obj.keyframe_insert("location",frame=frame)
                obj.keyframe_insert("scale",frame=frame)
        if obj.get("s2_cloud_origin"):
            obj.location=Vector(obj["s2_cloud_origin"])+DIRECTION*((clock*.42)%1.7)
            if key:
                obj.keyframe_insert("location",frame=frame)


def add_studio(scene, group):
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.max_bounces=5
    scene.cycles.use_denoising=True
    scene.view_settings.view_transform="AgX"
    scene.render.image_settings.file_format="PNG"
    scene.render.image_settings.color_mode="RGB"
    scene.world=bpy.data.worlds.new("S2 | blue-gray daylight")
    scene.world.use_nodes=True
    bg=scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value=(.60,.71,.76,1)
    bg.inputs["Strength"].default_value=.6
    sun=bpy.data.lights.new("S2 | pale side sun","SUN")
    sun.energy,sun.angle=1.6,.32
    lamp=create(sun.name,sun,group)
    lamp.rotation_euler=Vector((.72,.31,-1)).to_track_quat("-Z","Y").to_euler()


def place_bird(obj, p, heading, index):
    obj.location = (*p.xy, altitude(p.y)-(.072 if index else 0))
    obj.rotation_euler.z = math.atan2(-heading.x, heading.y)


def pose(scene, camera, flock, branch, distance, clock, key=False, frame=1):
    dense = catmull(ROUTES[branch])
    distances = route_distances(dense)
    p, h = at_distance(dense,distances,distance)
    if distance < .02:
        h=Vector((0,1,0))
    for i, goose in enumerate(flock):
        side,trail=tail_coords(i)
        center,direction=at_distance(dense,distances,distance-trail)
        if distance-trail < 0:
            center = Vector((0,distance-trail,0))
            direction = Vector((0,1,0))
        if i == 0:
            direction=h
        right=Vector((direction.y,-direction.x,0))
        place_bird(goose,center+right*side,direction,i)
        if key:
            goose.keyframe_insert("location",frame=frame)
            goose.keyframe_insert("rotation_euler",frame=frame)
    camera_pose(camera,flock[0].location,h)
    if key:
        for prop in ("location","rotation_euler"):
            camera.keyframe_insert(prop,frame=frame)
    apply_wind(scene,branch,p.y,clock,key,frame)
    bpy.context.view_layer.update()


def review_stage(scene, library, grass, movie=True):
    group=collection("90 | Review only fixed camera, flock and backing",scene.collection)
    studio=collection("Lighting", group)
    add_studio(scene,studio)
    plane("Review acreage south",(-155,155,-120,0),grass,group)
    plane("Review acreage north",(-155,155,76,140),grass,group)
    plane("Review acreage west",(-155,-52,0,76),grass,group)
    plane("Review acreage east",(60,155,0,76),grass,group)
    flock=bodies(scene,library,group)
    camera=camera_new(studio)
    scene.camera=camera
    scene.render.resolution_x,scene.render.resolution_y=SIZE
    scene.render.fps=8
    scene.frame_start=1
    scene.frame_end=64
    if movie:
        for i,branch in enumerate(("pass","lake")):
            end = route_distances(catmull(ROUTES[branch]))[-1]
            for step in range(32):
                frame=1+step+32*i
                scene.frame_set(frame)
                degree=step/31
                pose(scene,camera,flock,branch,end*degree,step/8,key=True,frame=frame)
        # Keep the abrupt change between the two evidence clips.
        scene.timeline_markers.new("Pass route from checkpoint A",frame=1)
        scene.timeline_markers.new("Lake route from the same checkpoint",frame=33)
    scene.frame_set(1)
    if not movie:
        pose(scene,camera,flock,"pass",0,0)
    return group, camera, flock


def camera_targets(scene,camera, view_mesh, land, water):
    trees = ray_tree(view_mesh,evaluated=True)
    size=SIZE
    values={
        "pass_opening":[(-11.8-2.45+i*4.9/12,21.5,.26) for i in range(13)],
        "lake_forebay": [(x,y,-.14) for y in (11,12,13) for x in (10.9,12,13.25)],
        "lakeside_pad":[(x,y,ground_at(land,x,y)+.036) for y in (8.2,9,10,11.1,11.9)
                       for x in (2.56,3,3.48,4,4.45)],
    }
    result={}
    for label, points in values.items():
        visible=[]
        for p in points:
            p=Vector(p)
            if label=="lake_forebay":
                require(ground_at(water,p.x,p.y) is not None, ("lake probe above water",p))
            uv=world_to_camera_view(scene,camera,p)
            direction=p-camera.location
            obstacle=trees.ray_cast(camera.location,direction.normalized(),direction.length-.007)[0]
            if obstacle is None and uv.z>0 and 0.015<uv.x<.985 and .015<uv.y<.985:
                visible.append((uv.x*size[0],(1-uv.y)*size[1]))
        pixels=[[round(min(q[i] for q in visible),3),round(max(q[i] for q in visible),3)] for i in range(2)] if visible else None
        result[label]={"visible":len(visible),"tested":len(points),"pixel_box":pixels}
    require(result["pass_opening"]["visible"]>=10 and result["lake_forebay"]["visible"]>=8
            and result["lakeside_pad"]["visible"]>=18, result)
    left,right=result["pass_opening"]["pixel_box"],result["lake_forebay"]["pixel_box"]
    require(left[0][1]+30<right[0][0],result)
    return result


def travel_proof(ground_and_plants, bird):
    coords=[v.co for v in bird.data.vertices]
    half_width=max(abs(v.x) for v in coords)
    foot=min(v.z for v in coords)
    stats={}
    for branch, xy in ROUTES.items():
        points=catmull(xy,32)
        lengths=route_distances(points)
        min_clearance=99
        min_probe=None
        count=0
        side_offsets=(-2.0,0,2.0) if branch!="rest_detour" else (0,)
        for i in range(max(2,math.ceil(lengths[-1]/.19))):
            p,h = at_distance(points,lengths,.13+(lengths[-1]-.26)*i/max(1,math.ceil(lengths[-1]/.19)-1))
            right=Vector((h.y,-h.x,0))
            for lateral in side_offsets:
                for wing in (-half_width, 0, half_width):
                    q=p+right*(lateral+wing)
                    if not 0 <= q.y <= 76:
                        continue  # Side bodies still lie in the S1/S3 gate apron.
                    ground=ground_at(ground_and_plants,q.x,q.y)
                    require(ground is not None,("route sample uncovered",branch,tuple(q)))
                    clearance=altitude(p.y)-.072+foot-ground
                    if min_clearance>clearance:
                        min_clearance=clearance
                        min_probe=[q.x,q.y,ground,p.x,p.y,lateral,wing]
                    count+=1
        stats[branch]={"distance_BU":lengths[-1],"ray_count":count,
                       "tested_static_goose_span_BU":2*half_width,"min_clearance_BU":min_clearance, "tightest_probe":min_probe}
        require(min_clearance>.05,(branch,stats[branch]))
    require(stats["lake"]["distance_BU"] > 1.16*stats["pass"]["distance_BU"],stats)
    require(all(ROUTES[key][-2:] == [(0,69),(0,76)] for key in ("pass","lake")),"merge")
    return stats


def gate_proof(scene, land, water):
    result={}
    for name, expected in GATE_NODES.items():
        obj=scene.objects[name]
        vector=obj.matrix_world.to_quaternion() @ Vector((0,1,0))
        require((obj.matrix_world.translation-Vector(expected)).length < TOL and (vector-Vector((0,1,0))).length<TOL,
                (name,obj.matrix_world.translation,vector))
        sign=1 if expected[1]==0 else -1
        count=0
        max_height=0
        for d in (.003,.20,.97,1.99):
            for i in range(97):
                x=-WIDTH+.02+i*(2*WIDTH-.04)/96
                y=expected[1]+d*sign
                height=ground_at(land,x,y)
                require(height is not None and abs(height)<TOL,("gate not flat",x,y,height))
                require(ground_at(water,x,y) is None,("wet gate",x,y))
                max_height=max(max_height,abs(height))
                count+=1
        for x in (-11.7,-6,-2,0,2,6,11.7):
            require(ground_at(land,x,expected[1]-.002*sign) is None,("terrain leak",x,expected))
        result[name]={"position_BU":list(obj.matrix_world.translation),"direction_BU":list(vector),
                      "dry_samples":count,"max_abs_height_BU":max_height}
    return result


def seam_rest(surface_a, surface_b):
    def position_map(item):
        return {(round(v.x,5),round(v.y,5)):v.z for v in
                (item.matrix_world@point.co for point in item.data.vertices)}

    a,b=position_map(surface_a),position_map(surface_b)
    pairs=set()
    for ii in range(17):
        shift=ii*.625
        pairs.update(((-1+shift,5),(-1+shift,15),(9,5+shift)))
    require(pairs <= set(a) and pairs <= set(b),("missing seam vertices",sorted(pairs-set(a)),sorted(pairs-set(b))))
    greatest=max(abs(a[xy]-b[xy]) for xy in pairs)
    require(greatest<TOL,greatest)
    return {"matched_vertices":len(pairs),"max_height_delta_BU":greatest}


def proof(scene, camera, flock):
    bpy.context.view_layer.update()
    ground=[o for o in scene.objects if o.get("s2_role")=="terrain"]
    plants=[o for o in scene.objects if o.get("s2_role")=="plant"]
    water=[o for o in scene.objects if o.get("s2_role")=="water"]
    bottom=ray_tree(ground)
    wet=ray_tree(water)
    shared=ray_tree([*ground,*plants],evaluated=True)
    primary=scene.objects["LakeShore"]
    pad=scene.objects["LakesideRest_Ground"]
    entrance=camera_targets(scene,camera,[*ground,*plants],bottom,wet)
    max_water=max(abs((o.matrix_world@v.co).z-WATER_Z) for o in water for v in o.data.vertices)
    require(max_water<TOL,max_water)
    rotation=(camera.rotation_euler.to_quaternion()@Vector((0,0,-1)))
    theor=Vector((0,0,6*BU))-Vector((0,-180*BU*math.cos(.48),180*BU*math.sin(.48)))
    fov=math.degrees(2*math.atan(camera.data.sensor_height/(2*camera.data.lens)))
    require(abs(fov-50)<1e-6 and (rotation-theor.normalized()).length <1e-6, (fov,rotation,theor))
    require((camera.location-Vector((0,-180*BU*math.cos(.48),180*BU*math.sin(.48)))).length <TOL,
            camera.location)
    return {"routes":travel_proof(shared,flock[0]),"gates":gate_proof(scene,bottom,wet),
            "shared_entrance_view":entrance,"rest_patch_seam":seam_rest(primary,pad),
            "fixed_camera":{"size":list(SIZE),"distance_game_units":180,"pitch_parameter_rad":.48,
                            "aim_height_game_units":6,"default_leader_height_game_units":8,
                            "field_of_view_degrees_measured":fov},
            "max_water_height_diff_BU":max_water}


def render(scene,camera, path, size=SIZE, samples=8):
    scene.camera=camera
    scene.render.resolution_x,scene.render.resolution_y=size
    scene.render.resolution_percentage=100
    scene.cycles.samples=samples
    scene.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)


def rest_still(scene, camera, flock, group, out):
    detour_spot=Vector((10.8,7.05,1.05))
    detour_heading=Vector((-.92,.39,0)).normalized()
    rest_camera=camera_new(group)
    rest_camera.name="S2_Rest_Detour_FixedRear"
    leader=create("S2_Rest_Detour_Lead",flock[0].data,group,at=detour_spot)
    leader.rotation_euler.z=math.atan2(-detour_heading.x,detour_heading.y)
    for item in flock:
        item.hide_render=True
    camera_pose(rest_camera,detour_spot,detour_heading)
    render(scene,rest_camera,out/"preview_lakeside_rest.png",samples=10)
    for item in flock:
        item.hide_render=False
    scene.camera=camera
    bpy.data.objects.remove(rest_camera,do_unlink=True)
    bpy.data.objects.remove(leader,do_unlink=True)


def gray_shot(scene,camera,out):
    mats={}
    solids={
        "terrain": paint("Graybox | rock and earth",(.40,.43,.38)),
        "water": paint("Graybox | water",(.25,.39,.44)),
        "plant": paint("Graybox | plants",(.22,.29,.24)),
        "fx": paint("Graybox | wind",(.48,.59,.63)),
    }
    per_mesh={}
    for obj in scene.objects:
        role=obj.get("s2_role")
        if role in solids and obj.type=="MESH" and obj.data not in per_mesh:
            per_mesh[obj.data]=list(obj.data.materials)
            for i,mat in enumerate(obj.data.materials):
                obj.data.materials[i]=solids[role]
    render(scene,camera,out/"graybox_fixed_rear.png")
    for mesh, mats in per_mesh.items():
        for index, material in enumerate(mats):
            mesh.materials[index]=material


def draw_routes(scene, group):
    existing=[]
    for name,palette in (("pass",(.75,.65,.39)),("lake",(.40,.69,.73)),("rest_detour",(.77,.79,.39))):
        mat=paint(f"Survey | {name}",palette, .2)
        for index,p in enumerate(catmull(ROUTES[name],7)[::2]):
            z=7.5 if name=="pass" else 3.
            r=.095 if name!="rest_detour" else .069
            obj=plane(f"Survey {name} sample {index}",(p.x-r,p.x+r,p.y-r,p.y+r),mat,group,z=z)
            existing.append(obj)
    data=bpy.data.cameras.new("S2 technical top | both branches")
    data.type="ORTHO"
    data.ortho_scale=87
    obj=create("S2_TechnicalTop",data,group,at=(5,38,90))
    obj.rotation_euler=(0,0,0)
    return obj, existing


def export_assembly(scene, root, col, path):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in col.all_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active=root
    require(bpy.ops.export_scene.gltf(filepath=str(path),export_format="GLB",use_selection=True,export_yup=True,
                                      export_animations=False,export_extras=True,export_skins=True)=={"FINISHED"}, path)


def video_file(out, frame_folder):
    subprocess.run(["ffmpeg","-y","-v","error","-framerate","8","-i",str(frame_folder/"%03d.png"),
                    "-vf","pad=iw:ih+1:0:0:black","-an","-c:v","libx264","-pix_fmt","yuv420p","-crf","20",
                    "-threads","2","-movflags","+faststart",str(out/MOVIE)],check=True)
    return decode_video(out/MOVIE)


def decode_video(path):
    subprocess.run(["ffmpeg","-v","error","-xerror","-nostdin","-i",str(path),"-map","0:v:0","-f","null","-"],check=True)
    probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_streams","-of","json",str(path)]))
    stream=probe["streams"][0]
    require(len(probe["streams"])==1 and (stream["width"],stream["height"],int(stream["nb_read_frames"]))==(852,394,64),
            stream)
    return {"status":"pass","decoded_frames":64,"audio_streams":0,"source_resolution":list(SIZE),
            "encoded_resolution":[852,394],"duration_s":float(stream["duration"])}


def wind_proof(scene):
    evaluated=[]
    root=scene.objects["S2_WindField"]
    armed=[o for o in scene.objects if o.get("s2_wind_tree")]
    fx=[o for o in scene.objects if o.get("s2_effect")]
    require(len(armed)==8 and len(fx)==7,(len(armed),len(fx)))
    require((Vector(root["direction"])-DIRECTION).length<TOL, root["direction"])
    for node in fx:
        vector=node.matrix_world.to_quaternion() @ Vector((0,1,0))
        require(vector.dot(DIRECTION)>.9999,(node.name,vector))
    for t in (.10,.43):
        apply_wind(scene,"pass",24,t)
        bpy.context.view_layer.update()
        band=fx[0].location.copy()
        tree=armed[0]
        crown=tree.pose.bones["Crown"]
        # Transform the crown bend to the same world basis as effect translation.
        axis_world=(tree.matrix_world.to_quaternion() @ crown.bone.matrix_local.to_quaternion()
                    @ crown.rotation_quaternion.axis)
        result={"band_position":list(band),"tree_downwind_bend_angle_deg":math.degrees(crown.rotation_quaternion.angle),
                "axis_dot":axis_world.dot(Vector((0,0,1)).cross(DIRECTION))}
        evaluated.append(result)
    v=Vector(evaluated[1]["band_position"])-Vector(evaluated[0]["band_position"])
    require(v.length>.4 and v.normalized().dot(DIRECTION)>.9999 and all(a["axis_dot"]>.9999 for a in evaluated),
            evaluated)
    apply_wind(scene,"lake",24,0)
    bpy.context.view_layer.update()
    require(all(o.scale.x<.0011 for o in fx) and all(a.pose.bones["Crown"].rotation_quaternion.angle<1e-5 for a in armed),
            "lake review neutral")
    return {"tree_rigs":len(armed),"effect_instances":len(fx),"world_downwind":list(DIRECTION),
            "measured_translation_BU":v.length,"speed_BU_s":v.length/.33,
            "crown_downwind_probes":evaluated,"lake_branch_quiet":True,
            "review_distance_ramp":{"vegetation_onset_y":9,"warning_band_onset_y":13,"gust_onset_y":19}}


def layout(cut, deps, swift):
    return {
        "id":"LVL-S2","version":"v001","status":"needs_review","variant":"S2_Fork",
        "axis_map":"Blender (x,y,z) -> glTF (x,z,-y)","BU_per_game_unit":BU,
        "entry":{"node":"S2_Entry","location_BU":[0,0,0],"heading":[0,1,0],"previous":"LVL-S1/Checkpoint_A"},
        "exit":{"node":"S2_Merge","location_BU":[0,76,0],"heading":[0,1,0],"next":"LVL-S3/entry"},
        "connection":{"coincident_after_translation":True,"flat_gate_x_BU":[-12,12],
                      "inward_clear_BU":2,"ground_z_BU":0,"water_level_BU":WATER_Z,"water_crosses_gate":False},
        "anchors":{"S2_Checkpoint_A":[0,0,0],"S2_Pass":[-11.48,17,0],"S2_Lake":[15.1,13.5,WATER_Z],
                   "S2_Rest":list(REST),"S2_JoinBeforeGate":[0,69,0]},
        "routes_preview_control_points":ROUTES,
        "dependencies":deps,"camera_source_sha256":swift,"source_geometry_edits":cut,
        "module_placements":{
            "ENV-008":{"translation_BU":[0,0,0],"terrain_use_Y_BU":[0,63],"lake_water_Y_BU":[4,58]},
            "ENV-010":{"translation_BU":[0,0,0],"pass_Y_BU":[10,50],"UV_phase_offset":[.35,.5]},
            "ENV-012":{"instances":TREE_POINTS,"shared_field":"S2_WindField"},
            "ENV-015":{"translation_BU":[4,10,0],"replaces_exact_ENV008_placeholder":True},
            "FX-002":{"runtime_inputs":"direction,strength,clockSeconds,motionScale,windSpeedBUPerSecond",
                      "source_mapping":"../../FX-002/v001/runtime_mapping.json","weather_zone":"short pass only"},
            "ENV-018":{"role":"two short-pass cloud cards on the same wind clock"},
            "CHR-001":{"role":"review-only bird, 12 poses via one neutral mesh"}},
        "runtime_owned":["collision and true traversal","branch selection and merge","Checkpoint A and retry",
                         "lakeside rest/energy","wind consequence, low-energy cue and retry","performance"],
    }


def build(library,out,scratch,quick):
    deps,swift=inventory(library)
    scene,root,main,grass,cut=assemble(library)
    write_json(out/"s2_layout.json",layout(cut,deps,swift))
    export_assembly(scene,root,main,out/EXPORT)
    group,cam,flock=review_stage(scene,library,grass)
    scene.frame_set(1)
    initial=proof(scene,cam,flock)
    wind=wind_proof(scene)
    scene.frame_set(1)
    gray_shot(scene,cam,out)
    render(scene,cam,out/"preview_checkpoint_A.png",samples=12)
    for frame,name in ((10,"preview_short_pass"),(44,"preview_long_lake"),(29,"preview_merge")):
        scene.frame_set(frame)
        render(scene,cam,out/f"{name}.png",samples=10)
    rest_still(scene,cam,flock,group,out)
    scene.frame_set(1)
    top,lines=draw_routes(scene,group)
    render(scene,top,out/"preview_both_routes_top.png",(980,980),8)
    for line in lines:
        line.hide_render=True
        line.hide_set(True)
    scene.camera=cam
    scene.render.resolution_x,scene.render.resolution_y=SIZE
    scene.frame_set(1)
    scene.render.filepath="//preview_checkpoint_A.png"
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/MODEL))
    source={"status":"pass","geometry":initial,"wind":wind}
    write_json(out/"build_checks.json",source)
    if not quick:
        frames=scratch/"frames"
        frames.mkdir()
        for frame in range(1,65):
            scene.frame_set(frame)
            render(scene,cam,frames/f"{frame:03d}.png",samples=3)
        write_json(scratch/"video_decode.json",video_file(out,frames))


def verify(library, delivery, out):
    deps,swift=inventory(library)
    spec=read_json(delivery/"s2_layout.json")
    require(spec["dependencies"]==deps and spec["camera_source_sha256"]==swift,"dependencies changed")
    bpy.ops.wm.open_mainfile(filepath=str(delivery/MODEL))
    scene=bpy.context.scene
    scene.frame_set(1)
    flock=[scene.objects[f"S2_ReviewGoose_{i+1:02}"] for i in range(12)]
    main_proof=proof(scene,scene.camera,flock)
    wind=wind_proof(scene)
    for frame in (1,10,17,29,32,33,43,54,64):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        lead=flock[0].matrix_world.translation
        offset=scene.camera.matrix_world.translation-lead
        require(abs(offset.xy.length - 180*BU*math.cos(.48))<TOL and
                abs(offset.z-(180*BU*math.sin(.48)-.288))<TOL,("camera drift",frame,offset))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    group=collection("Roundtrip source",scene.collection)
    isolate_import(delivery/EXPORT, group)
    grass=next(m for m in scene.objects["LakeShore"].data.materials if m.name.startswith("GrassFlat"))
    _, camera, roundtrip_flock = review_stage(scene,library,grass,movie=False)
    after=proof(scene,camera,roundtrip_flock)
    post_wind=wind_proof(scene)
    require(all(after["shared_entrance_view"][key]["visible"]==main_proof["shared_entrance_view"][key]["visible"]
                for key in main_proof["shared_entrance_view"]), (main_proof["shared_entrance_view"],after["shared_entrance_view"]))
    require(all(abs(after["routes"][r]["min_clearance_BU"]-main_proof["routes"][r]["min_clearance_BU"])<TOL
                for r in ROUTES), "roundtrip clearance differs")
    required_images=set()
    for asset, files in DEPENDENCIES.items():
        if asset=="CHR-001":
            continue
        for file in files:
            if file.endswith(".glb"):
                required_images.update(image_hashes(dependency(library,asset,file)))
    embedded=image_hashes(delivery/EXPORT)
    require(required_images.issubset(embedded), ("missing source images",sorted(required_images-embedded)))
    document,_=as_glb(delivery/EXPORT)
    nodes={n.get("name"):n for n in document["nodes"]}
    require(all(name in nodes for name in GATE_NODES) and nodes["S2_Merge"].get("translation")==[0,0,-76],
            nodes.get("S2_Merge"))
    require(not document.get("animations") and len(document.get("skins",[]))==8, "neutral wind rigs expected")
    render(scene,camera,out/"roundtrip_fixed_rear.png",samples=12)
    movie=decode_video(delivery/MOVIE)
    write_json(out/"qa.json",{
        "id":"LVL-S2","version":"v001","status":"needs_review",
        "independent_delivery_recheck":{"status":"pass","reopened_mother":main_proof,
                                       "GLB_reimport":after,"mother_shared_wind":wind,
                                       "GLB_shared_wind":post_wind,"retained_source_image_hashes":sorted(required_images),
                                       "GLB_embedded_image_hashes":sorted(embedded),"skeletal_tree_instances":8,
                                       "full_video_decode":movie},
        "evidence_scope":"Offline evaluated mesh, route rays, camera projections and named gates. Branch trajectories and climate visual controls are review settings.",
        "app_baseline":"Existing iPhone 18 Pro iOS 27.2 simulator build and 340 passing tests in active plan.",
        "pending":["art review","human branch contrast glance","runtime collision, full flock formation and branch gameplay",
                   "Checkpoint A retry/refill, energy and wind response","USDZ / RealityKit / App","iPhone / iPad"],
        "redline_review":"Checked against plans/_templates/redline-checklist.md; environmental and route visuals only, dry-area patches and visual examples; device experience remains pending.",
    })


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument("--library",type=Path,default=HOME.parents[1])
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--scratch",type=Path)
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--quick",action="store_true")
    options=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    options.out.mkdir(parents=True,exist_ok=True)
    require(not any(options.out.iterdir()),"Choose an empty --out folder")
    if options.verify:
        verify(options.library.resolve(),options.verify.resolve(),options.out.resolve())
    else:
        require(options.scratch is not None,"--scratch required for build")
        options.scratch.mkdir(parents=True,exist_ok=True)
        require(not any(options.scratch.iterdir()),"Choose empty --scratch")
        build(options.library.resolve(), options.out.resolve(), options.scratch.resolve(),options.quick)


if __name__=="__main__":
    main()
