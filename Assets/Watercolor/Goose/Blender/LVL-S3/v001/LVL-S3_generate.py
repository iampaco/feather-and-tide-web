"""Assemble S3, render review evidence, or independently reread the delivered files."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory

import bpy
from mathutils import Quaternion, Vector
from mathutils.bvhtree import BVHTree

ASSET = "LVL-S3"
MOTHER = "LVL-S3_S3_Rescue.blend"
GLB = "LVL-S3_S3_Rescue.glb"
VIDEO = "preview_fixed_rear.mp4"
SCENE = "S3 | Rescue review"
VERSION = "v001"
LIB_PATH = Path("Assets/Watercolor/Goose/Blender")
BASE = .036
SIZE = 852, 393
FPS, VIDEO_FPS, LAST = 24, 8, 409
WATER = -.18
RIVER_X = -3.
RESCUE = (2.40, 21.78, .038)
EVENT = 1.9166666667
APPROACH, REJOIN_END = 14.0, 16.0
PATH = [(0., -1.4, 15.9), (2., -1.4, 21.6), (4., -1.50, 27.5),
        (6., .55, 31.4), (8., 4.25, 28.8), (10.8, 4.15, 25.9),
        (12.1, 3.87, 24.76), (14., 2.52, 23.62),
        (16., 1.94, 21.68), (17., 1.86, 20.47)]
TREES = [("RiverTree_A", -6.63, 21.64, .09, 1.10), ("RiverTree_B", -5.9, 25.4, -.33, .95),
         ("LeaningTree", -6.82, 30.2, .44, 1.03), ("RiverTree_A", 6.65, 21.55, -.17, .98),
         ("RiverTree_B", 7.40, 28.6, .47, 1.12), ("LeaningTree", -6.5, 35.3, -.10, 1.07),
         ("RiverTree_B", 6.44, 36.7, -.45, .96), ("RiverTree_A", -5.9, 43.1, .25, .95)]
WIND = {
    "WarnBand": ((-.95, 20.3, .98), (-1.72, 22.7, 1.28), (-.42, 25.9, 1.51), (-.35, 28.2, 1.07)),
    "CrownSweep": ((-5.83, 21.61, 1.71), (-5.29, 25.18, 1.48), (-6.15, 29.87, 1.96)),
    "GustBand": ((-1.31, 21.32, .86), (-1.66, 22.88, 1.48), (-1.2, 25.0, 1.24), (-.42, 27.55, 1.13)),
    "Leaf": ((-2.4, 21.13, .98), (-2.9, 22.32, 1.4), (-3.21, 24.92, 1.29), (-4.4, 25.2, 1.63)),
}
RIVER = [(10, "Straight"), (20, "OpenBank"), (30, "Bend"), (40, "Straight"), (50, "Straight")]
CHAPTER = {
    "S3_Entry": ((0, 0, 0), "from S2 merge; heading +Y"),
    "S3_Exit": ((0, 64, 0), "to S4 (2,-45,0); heading +Y"),
    "S3_WindZone": ((-2.75, 22.5, .0), "fixed world visual station; use translated wind field"),
    "S3_SeparationSample": ((-1.4, 21.4, .0), "offline reference for lead at separation"),
    "S3_RescueAnchor": (RESCUE, "OpenBank east-side apron; FX-009 center"),
    "S3_ApproachSample": ((2.52, 23.62, 0), "offline leader sample at escort transition"),
}
DIRECT = {"ENV-007", "ENV-012", "FX-002", "FX-009", "ANM-009"}
INPUTS = {
    "ENV-001": ["ENV-001_Flat.glb"],
    "ENV-005": ["ENV-005_Sparse.glb"],
    "ENV-007": [f"ENV-007_{variant}.glb" for variant in ("Straight", "Bend", "OpenBank")],
    "ENV-012": [f"ENV-012_{variant}.glb" for variant in ("RiverTree_A", "RiverTree_B", "LeaningTree")],
    "FX-002": ["FX-002_CrosswindWarn.glb", "FX-002_Gust.glb", "runtime_mapping.json"],
    "FX-009": ["FX-009_RescueBeacon.glb", "runtime_mapping.json"],
    "ANM-009": ["ANM-009_call_rejoin.glb"],
    "ANM-001": ["ANM-001_cruise_flap.glb"],
    "ENV-009": ["ENV-009_FarRidge_A.glb", "ENV-009_FarRidge_B.glb"],
}
CAMERA_PATH = "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift"
VIEW_PATH = "Sources/FeatherTide/Rendering/PlayfieldView.swift"


def check(condition, detail):
    if not condition:
        raise RuntimeError(str(detail))


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def files(lib, aid):
    return lib / aid / VERSION


def path_for(lib, name):
    return files(lib, name.split("_",1)[0]) / name


def source_audit(lib):
    report = {}
    for aid, names in INPUTS.items():
        folder = files(lib, aid)
        manifest = read(folder / "asset_manifest.json")
        qa = read(folder / "qa.json")
        check(manifest["status"] in {"needs_review", "done"}, (aid, "source candidate status"))
        check(qa and (folder / "README.md").stat().st_size > 100, (aid, "missing evidence"))
        result = {"role": "spec dependency" if aid in DIRECT else "additional in-project assembly/review dependency",
                  "version": VERSION, "status": manifest["status"], "files": {}}
        for name in ["README.md", "qa.json", "asset_manifest.json", *names]:
            expected = manifest.get("files", {}).get(name)
            checksum = sha(folder / name)
            if isinstance(expected, dict):
                expected = expected.get("sha256")
            check(expected is None or checksum == expected, (aid, name, checksum, expected))
            if name not in {"README.md", "qa.json", "asset_manifest.json"}:
                check(expected is not None, (aid, name, "source is not pinned"))
            result["files"][name] = {"sha256": checksum, "bytes": (folder / name).stat().st_size}
        report[aid] = result
    repo = lib.parents[3]
    camera, player = (repo / CAMERA_PATH).read_text(), (repo / VIEW_PATH).read_text()
    check(all(token in camera for token in ("distance: 180, pitch: 0.48, fieldOfViewDegrees: 50", "Float(6 + lift)"))
          and all(token in player for token in ("CGFloat(sample.depthLift)", "(body.leader ? 8 : 6)")),
          "Swift camera contract changed")
    return report, {name: sha(repo / name) for name in (CAMERA_PATH, VIEW_PATH)}


def coll(scene, name):
    collection = bpy.data.collections.new(name)
    scene.collection.children.link(collection)
    return collection


def put(collection, name, data=None, parent=None, loc=None):
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.parent = parent
    if loc is not None:
        obj.location = loc
    return obj


def imported(path, destination):
    known = set(bpy.data.objects)
    check(bpy.ops.import_scene.gltf(filepath=str(path)) == {"FINISHED"}, path)
    # glTF creates bone display custom shapes. Their internal collection must stay presentation-only.
    objs = [obj for obj in bpy.context.scene.objects if obj not in known and not obj.name.startswith("Icosphere")]
    for obj in objs:
        for group in tuple(obj.users_collection):
            group.objects.unlink(obj)
        destination.objects.link(obj)
    return objs


def polygons(rows, cols):
    for j in range(rows - 1):
        for i in range(cols - 1):
            a = j * cols + i
            b, c, d = a + 1, a + cols + 1, a + cols
            yield from ((a, b, c), (a, c, d)) if (i + j) % 2 == 0 else ((a, b, d), (b, c, d))


def surface(group, name, points, faces, mats, uv_fn, index_fn=None, parent=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], list(faces))
    mesh.update()
    obj = put(group, name, mesh, parent)
    for mat in mats:
        mesh.materials.append(mat)
    uv = mesh.uv_layers.new()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
        if index_fn:
            polygon.material_index = index_fn(polygon.index)
        for i in polygon.loop_indices:
            uv.data[i].uv = uv_fn(points[mesh.loops[i].vertex_index])
    return obj


def smooth(x):
    u = max(0., min(1., x))
    return u*u*(3.-2.*u)


def row_at(mesh, local_y):
    # The raw tile splits vertices at different texture islands. Use physical positions.
    return sorted(set((round(v.co.x, 6), round(v.co.z, 6))
                      for v in mesh.vertices if abs(v.co.y - local_y) < 1e-5))


def span_at_water(row):
    borders = []
    for (x0, z0), (x1, z1) in zip(row, row[1:]):
        if (z0 > WATER) != (z1 > WATER):
            borders.append(x0 + (WATER-z0)/(z1-z0)*(x1-x0))
    check(len(borders) == 2, row)
    return borders


def cap(group, root, bed, water, incoming):
    profile = row_at(bed.data, -5 if incoming else 5)
    check(len(profile) == 17, profile)
    near, far = (0, 5) if incoming else (55, 64)
    # Water/riverbank fades inward, with genuine flat shared land for 2 BU at the gates.
    def factor(y):
        return smooth((y-2)/3) if incoming else 1.-smooth((y-55)/7)
    heights = [near + i*.25 for i in range(round((far-near)*4)+1)]
    def section(y):
        return [(x, z*factor(y)) for x,z in profile]
    pts = [(RIVER_X+x, y, z) for y in heights for x,z in section(y)]
    # Texture phase continues by modular V and original lateral profile UV.
    def land_uv(p):
        return ((p[0]-RIVER_X+5)/10, (p[1]-5)/10)
    def land_zone(index):
        col = (index//2)%16
        row = index//32
        weight = (factor(heights[row])+factor(heights[row+1]))*.5
        return (3 if 5 <= col < 11 else 1 if col in (3,4,11,12) else 0) if weight > .33 else 0
    sign = "South" if incoming else "North"
    land = surface(group, f"S3_BedCap_{sign}", pts, polygons(len(heights), 17), bed.data.materials,
                   land_uv, land_zone, root)
    # Trace the exact linear interpolation of the bed between adjacent rows.
    wet_rows = [y for y in heights if min(z for _,z in section(y)) < WATER - 1e-6]
    first_y = min(wet_rows) - .25 if incoming else max(wet_rows) + .25
    edge_y = min(wet_rows) if incoming else max(wet_rows)
    a = min(z for _, z in section(first_y))
    b = min(z for _, z in section(edge_y))
    cut = first_y + (edge_y-first_y)*(WATER-a)/(b-a)
    wet_rows = [cut, *wet_rows] if incoming else [*wet_rows, cut]
    water_points = []
    for j,y in enumerate(wet_rows):
        if y == cut:
            x0 = x1 = min(profile, key=lambda item:item[1])[0]
        else:
            x0, x1 = span_at_water(section(y))
        water_points.extend((RIVER_X+x0+(x1-x0)*i/4, y, WATER) for i in range(5))
    # Use a fan at the closed tip; keep the two adjacent row triangles nondegenerate.
    tip_cols = len(wet_rows)-1 if not incoming else 0
    faces = []
    for face in polygons(len(wet_rows), 5):
        fixed = tuple((tip_cols*5 if idx//5==tip_cols else idx) for idx in face)
        if len(set(fixed)) == 3:
            faces.append(fixed)
    w = surface(group, f"S3_WaterCap_{sign}", water_points, faces, water.data.materials,
                lambda p:(.5,(p[1]-5)/10), parent=root)
    for loop in w.data.loops:
        k = loop.vertex_index
        y = water_points[k][1]
        w.data.uv_layers[0].data[loop.index].uv = ((.5 if y==cut else (k%5)/4),(y-5)/10)
    return land,w


def terrain(lib, group, root, source):
    flats = imported(path_for(lib,"ENV-001_Flat.glb"), source)
    grass = next(obj for obj in flats if obj.type=="MESH").data.materials[0]
    corners_y = [n/2 for n in range(129)]
    for side, (x0,x1) in (("West", (-25,-8)),("East", (2,25))):
        xs = [x0+(x1-x0)*i/34 for i in range(35)]
        pts = [(x,y,0) for y in corners_y for x in xs]
        surface(group,f"S3_GrassLand_{side}",pts,polygons(len(corners_y),len(xs)),[grass],
                lambda p:((p[0]+8)/10,(p[1]-5)/10),parent=root)
    proto = {}
    for variant in ("Straight","OpenBank","Bend"):
        objs = imported(path_for(lib,f"ENV-007_{variant}.glb"), source)
        proto[variant] = sorted(objs, key=lambda o:o.name)
    for y, variant in RIVER:
        for obj in proto[variant]:
            new = put(group, f"S3_{obj.name}_{y:02d}", obj.data, root, (RIVER_X,y,0))
            new["source"] = f"ENV-007/v001 {variant}"
    bed, water = proto["Straight"]
    cap(group,root,bed,water,True)
    cap(group,root,bed,water,False)


def trees_and_reeds(lib, plants, root, source):
    templates = {}
    for variant, *_ in TREES:
        if variant not in templates:
            objs = imported(path_for(lib,f"ENV-012_{variant}.glb"), source)
            rig = next(obj for obj in objs if obj.type=="ARMATURE")
            rig.animation_data_clear()
            templates[variant] = rig, next(obj for obj in objs if obj.type=="MESH")
    for i,(variant,x,y,yaw,scale) in enumerate(TREES,1):
        ar, body = templates[variant]
        rig = ar.copy()
        rig.data = ar.data
        plants.objects.link(rig)
        rig.parent = root
        rig.name = f"S3_TreeRig_{i:02d}_{variant}"
        rig.location = (x,y,0)
        rig.rotation_euler = (0,0,yaw)
        rig.scale = (scale,)*3
        rig["instanceYawRad"] = yaw
        rig["phaseRad"] = .31*i
        rig["source"] = f"ENV-012/v001 {variant}"
        for bone in rig.pose.bones:
            bone.rotation_mode = "QUATERNION"
            bone.rotation_quaternion = Quaternion()
        mesh = body.copy()
        plants.objects.link(mesh)
        mesh.parent = rig
        mesh.name = f"S3_TreeMesh_{i:02d}_{variant}"
        next(m for m in mesh.modifiers if m.type=="ARMATURE").object = rig
    reeds = next(o for o in imported(path_for(lib,"ENV-005_Sparse.glb"),source) if o.type=="MESH")
    for name,x,y,yaw,sx,sy in (("SW",-8.8,10,.18,.53,.40),("West",-9.05,25,-.03,.55,.38),
                             ("NW",-9.2,43,.12,.59,.52),("Far_NE",10.1,43.3,-.12,.55,.43),
                             ("SE",9.1,10,-.02,.47,.39)):
        obj = put(plants,f"S3_Reeds_{name}",reeds.data,root,(x,y,.012))
        obj.rotation_euler.z=yaw
        obj.scale=(sx,sy,.69)
        obj["source"]="ENV-005/v001 Sparse"


def effects(lib, group, root, source):
    prototypes = {}
    for v in ("CrosswindWarn","Gust"):
        prototypes.update({o.name:o for o in imported(path_for(lib,f"FX-002_{v}.glb"),source) if o.type=="MESH"})
    x,y=read(files(lib,"FX-002")/"runtime_mapping.json")["review"]["direction"]
    yaw=math.atan2(-x,y)
    for role, placements in WIND.items():
        for i, loc in enumerate(placements,1):
            obj = put(group, f"S3_{role}_{i:02d}", prototypes[role].data, root, loc)
            obj["source"]="FX-002/v001"
            obj["effectPart"]=role
            obj.rotation_euler.z=yaw
            obj["basePosition_BU"]=loc
            obj["defaultVisible"]=False
    incoming=imported(path_for(lib,"FX-009_RescueBeacon.glb"),group)
    beacon=next(o for o in incoming if o.type=="EMPTY")
    beacon.name="S3_RescueBeacon"
    beacon.parent=root
    beacon.location=RESCUE
    beacon["source"]="FX-009/v001"
    beacon["defaultVisible"]=False
    for obj in beacon.children:
        obj.name="S3_" + obj.name
        obj["effectPart"]="Beacon"
    return beacon


def setup_static(lib):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.name=SCENE
    scene.render.fps=FPS
    scene.frame_start,scene.frame_end=1,LAST
    temp=coll(scene,"Source import staging")
    anatomy=coll(scene,"S3  |  Runtime root and spatial anchors")
    root=put(anatomy,"S3_Rescue")
    root["forward"]="+Y"
    root["up"]="+Z"
    root["reference_water_z_BU"]=WATER
    root["BU_per_game_unit"]=BASE
    for name,(loc,role) in CHAPTER.items():
        obj=put(anatomy,name,parent=root,loc=loc)
        obj.empty_display_type="ARROWS"
        obj["forward_blender"]=(0,1,0)
        obj["role"]=role
    ground=coll(scene,"S3  |  Lands, river and bed")
    terrain(lib,ground,root,temp)
    vegetation=coll(scene,"S3  |  River trees and dry-bank reeds")
    trees_and_reeds(lib,vegetation,root,temp)
    cues=coll(scene,"S3  |  World-positioned wind and rescue effect instances")
    effects(lib,cues,root,temp)
    for obj in list(temp.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    bpy.data.collections.remove(temp)
    return scene, root


def export_glb(scene,path,root):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in [root,*root.children_recursive]:
        obj.select_set(True)
    check(bpy.ops.export_scene.gltf(filepath=str(path),use_selection=True,use_active_scene=True,
          export_yup=True,export_animations=False,export_extras=True) == {"FINISHED"},path)


def drive(entity, field, expression, control, fields, index=None):
    curve = entity.driver_add(field) if index is None else entity.driver_add(field,index)
    driver=curve.driver
    driver.type="SCRIPTED"
    for name,prop in fields.items():
        variable=driver.variables.new()
        variable.name=name
        variable.type="SINGLE_PROP"
        variable.targets[0].id=control
        variable.targets[0].data_path=f'["{prop}"]'
    driver.expression=expression


def authored_knob(control, key, value, lo, hi, description):
    control[key]=value
    control.id_properties_ui(key).update(min=lo,max=hi,description=description)


def cue_keys(control, property_name, points):
    control[property_name]=float(points[0][1])
    for second,value in points:
        control[property_name]=value
        control.keyframe_insert(f'["{property_name}"]',frame=1+second*FPS,group="Event envelopes")
    curve=control.animation_data.action.layers[0].strips[0].channelbag(control.animation_data.action_slot).fcurves.find(f'["{property_name}"]')
    for key in curve.keyframe_points:
        key.interpolation="LINEAR"


def use_opacity(original, control, field, name):
    """Insert one envelope while preserving the map, tint, and original straight alpha."""
    material=original.copy()
    material.name=name
    nodes=material.node_tree.nodes
    links=material.node_tree.links
    alpha_tex=next(n.outputs["Alpha"] for n in nodes if n.type=="TEX_IMAGE" and n.outputs["Alpha"].is_linked)
    destinations=[link.to_socket for link in alpha_tex.links]
    check(destinations,(original.name,"alpha connections not found"))
    scale=nodes.new("ShaderNodeMath")
    scale.name="Review event opacity"
    scale.operation="MULTIPLY"
    scale.location=(45,-80)
    links.new(alpha_tex, scale.inputs[0])
    if field=="beaconEnvelope":
        drive(scale.inputs[1],"default_value","e",control,{"e":field})
    else:
        baseline="m" if name.endswith("Leaf") else "(.48+.52*m)"
        drive(scale.inputs[1],"default_value",f"e*s*{baseline}",control,{"e":field,"s":"strength","m":"motionScale"})
    for socket in destinations:
        links.new(scale.outputs[0],socket)
    return material


def setup_fx(lib,scene,group):
    ctrl=put(group,"S3_WindControl")
    ctrl.empty_display_type="ARROWS"
    ctrl.location=CHAPTER["S3_WindZone"][0]
    upstream=read(files(lib,"FX-002")/"runtime_mapping.json")["review"]
    x,y=upstream["direction"]
    authored_knob(ctrl,"windBearingRad",math.atan2(-x,y),-math.pi,math.pi,"Blender yaw from +Y to normalized world downwind.")
    authored_knob(ctrl,"strength",upstream["strength"],0,1,"One normalized strength for Stem/Crown and VFX.")
    authored_knob(ctrl,"motionScale",1.,0,1,"Zero neutralizes trees and advection, removes leaves, keeps soft ribbons.")
    authored_knob(ctrl,"windSpeedBUPerSecond",1.95,0,6,"Along normalized downwind in Blender BU/s.")
    for name,keys in upstream["preset_intensity_curves"].items():
        cue_keys(ctrl,name,keys)
    cue_keys(ctrl,"beaconEnvelope",[(0.,0.),(EVENT,0.),(2.26,1.),(14.,1.),(16.,0.)])
    ctrl["hostExampleSeparationS"]=EVENT
    ctrl["hostExampleEscortS"]=APPROACH
    ctrl["hostOwnsSpatialAndGameplayGates"]=True
    expressions={"s":"strength","m":"motionScale","a":"windBearingRad"}
    for rig in [o for o in scene.objects if o.name.startswith("S3_TreeRig_")]:
        yaw=float(rig["instanceYawRad"])
        phase=float(rig["phaseRad"])
        for bone_name, degrees, lag in (("Stem",8,.0),("Crown",18,.43)):
            bone=rig.pose.bones[bone_name]
            bone.rotation_mode="QUATERNION"
            inv=bone.bone.matrix_local.to_3x3().inverted()
            local_x=inv@Vector((-1,0,0))
            local_y=inv@Vector((0,-1,0))
            angle=f"{math.radians(degrees)/2:.12f}*s*m*e*(.87+.13*sin((frame-1)*.149+{phase}-{lag}))"
            fields={**expressions,"e":"treeEnvelope"}
            drive(bone,"rotation_quaternion",f"cos({angle})",ctrl,fields,0)
            for idx in range(3):
                axis=f"({local_x[idx]:.12f}*cos(a-{yaw})+{local_y[idx]:.12f}*sin(a-{yaw}))"
                drive(bone,"rotation_quaternion",f"{axis}*sin({angle})",ctrl,fields,idx+1)
    overrides={}
    for o in scene.objects:
        part=o.get("effectPart")
        if part not in WIND and part!="Beacon":
            continue
        if part=="Beacon":
            field="beaconEnvelope"
        else:
            field="warnEnvelope" if part in ("WarnBand","CrownSweep") else "gustEnvelope"
            start=upstream["warn_starts_seconds"] if field=="warnEnvelope" else upstream["gust_starts_seconds"]
            travel=f"min(1.6,max(0,(frame-1)/{FPS}-{start}))*s*m*v"
            base=o["basePosition_BU"]
            params={**expressions,"v":"windSpeedBUPerSecond"}
            scale={"WarnBand":.5,"CrownSweep":.6,"GustBand":1.,"Leaf":.79}[part]
            drive(o,"location",f"{base[0]}-sin(a)*{travel}*{scale}",ctrl,params,0)
            drive(o,"location",f"{base[1]}+cos(a)*{travel}*{scale}",ctrl,params,1)
            drive(o,"rotation_euler","a",ctrl,params,2)
            o.rotation_euler.x=math.radians(12 if part=="GustBand" else 7)
            if part=="Leaf":
                seed=int(o.name[-2:])
                drive(o,"location",f"{base[2]}+.10*m*sin((frame-1)*.30+{seed})",ctrl,params,2)
                drive(o,"rotation_euler",f".65*m*sin((frame-1)*.22+{seed})",ctrl,params,0)
        initial=o.data.materials[0]
        key=(part,initial.name)
        if key not in overrides:
            overrides[key]=use_opacity(initial,ctrl,field,f"S3 effect opacity | {part}")
        o.material_slots[0].link="OBJECT"
        o.material_slots[0].material=overrides[key]
    return ctrl


def track(t):
    """Cubic Hermite using neighboring stations with derivatives in BU/s."""
    for i in range(len(PATH)-1):
        if t<=PATH[i+1][0]+1e-8:
            break
    a,b=PATH[i],PATH[i+1]
    before,after=PATH[max(i-1,0)],PATH[min(i+2,len(PATH)-1)]
    pa,pb=Vector(a[1:]),Vector(b[1:])
    dt=b[0]-a[0]
    m0=(pb-Vector(before[1:]))*dt/(b[0]-before[0])
    m1=(Vector(after[1:])-pa)*dt/(after[0]-a[0])
    u=max(0,min(1,(t-a[0])/dt))
    p=(2*u**3-3*u*u+1)*pa +(u**3-2*u*u+u)*m0+(-2*u**3+3*u*u)*pb+(u**3-u*u)*m1
    d=(6*u*u-6*u)*pa +(3*u*u-4*u+1)*m0+(-6*u*u+6*u)*pb+(3*u*u-2*u)*m1
    return p,d.normalized()


def formation(t,index):
    xy,heading=track(t)
    x=0.
    back=0.
    if index:
        lane=(index+1)//2
        x=(.57+.37*lane)*(1 if index%2 else -1)
        back=.55+.43*lane
    if index==11:
        x,back=3.13+1.19*(1.-smooth(t-APPROACH+1)),2.25
    right=Vector((heading.y,-heading.x))
    p=xy+right*x-heading*back
    return Vector((*p, (.288 if index==0 else .216)+.40))


def isolated(t):
    regular=formation(t,11)
    watch=Vector((RESCUE[0]-.06,RESCUE[1]+.47,.51))
    if t<EVENT:
        return regular
    if t<3.25:
        amount=smooth((t-EVENT)/(3.25-EVENT))
        return regular.lerp(watch,amount)
    if t<APPROACH:
        return watch
    return watch.lerp(regular,smooth((t-APPROACH)/(REJOIN_END-APPROACH)))


def action_curves(action):
    layer=action.layers[0].strips[0]
    return {(fc.data_path,fc.array_index):fc for fc in layer.channelbag(action.slots[0]).fcurves}


def setup_actors(lib,scene,group):
    source=coll(scene,"Review motion import staging")
    folk=imported(path_for(lib,"ANM-009_call_rejoin.glb"),source)
    bird=next(o for o in folk if o.type=="ARMATURE")
    skin=next(o for o in folk if o.type=="MESH")
    for track_obj in bird.animation_data.nla_tracks:
        for strip in track_obj.strips:
            strip.action.use_fake_user=True
    bird.animation_data_clear()
    cruise=imported(path_for(lib,"ANM-001_cruise_flap.glb"),source)
    for obj in cruise:
        if obj.animation_data:
            for track_obj in obj.animation_data.nla_tracks:
                for strip in track_obj.strips:
                    strip.action.use_fake_user=True
    actions={key:action_curves(bpy.data.actions[key]) for key in ("Call_Loop","Rejoin","Cruise_Flap_Loop")}
    keyset=sorted(set.union(*(set(value) for value in actions.values())))
    channels={}
    for path,index in keyset:
        if path.startswith("pose.bones["):
            bone_text,prop=path.split('"].')
            name=bone_text.split('["',1)[1]
            channels.setdefault((name,prop),[]).append((index,path))
    birds=[]
    for i in range(12):
        rig=bird.copy()
        rig.data=bird.data
        rig.name=f"Review_GooseRig_{i+1:02d}"
        group.objects.link(rig)
        rig.rotation_mode="QUATERNION"
        model=skin.copy()
        group.objects.link(model)
        model.name=f"Review_GooseSkin_{i+1:02d}"
        model.parent=rig
        next(m for m in model.modifiers if m.type=="ARMATURE").object=rig
        birds.append(rig)
    for obj in list(source.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    bpy.data.collections.remove(source)
    return birds,actions,channels


def timeline(t,index):
    cruise_t=(t*FPS+2.17*index)%26.
    if index!=11:
        return (("Cruise_Flap_Loop",cruise_t,1.),)
    if t<EVENT:
        return (("Cruise_Flap_Loop",cruise_t,1.),)
    if t<3.25:
        k=smooth((t-EVENT)/(3.25-EVENT))
        return (("Cruise_Flap_Loop",cruise_t,1.-k),("Call_Loop",0.,k))
    rejoin_starts=REJOIN_END-26/FPS
    if t<rejoin_starts:
        return (("Call_Loop",((t-3.25)*FPS)%28.,1.),)
    if t<REJOIN_END:
        return (("Rejoin",(t-rejoin_starts)*FPS,1.),)
    return (("Cruise_Flap_Loop",((t-REJOIN_END)*FPS)%26.,1.),)


def bake_motion(scene,birds,actions,channels,eye,beacon):
    last_q={}
    for frame in range(1,LAST+1):
        t=(frame-1)/FPS
        _,forward=track(t)
        for i,rig in enumerate(birds):
            p=isolated(t) if i==11 else formation(t,i)
            rig.location=p
            heading=forward
            if i==11 and EVENT<=t<REJOIN_END:
                if t<3.25 or t>APPROACH:
                    before=isolated(max(0,t-.035))
                    after=isolated(min(17.,t+.035))
                    tangent=(after-before).xy
                    heading=tangent.normalized() if tangent.length>.002 else Vector((0,1))
                else:
                    # Face slightly across the bright dry reach while calling.
                    heading=Vector((-.30, .954))
            angle=math.atan2(-heading.x,heading.y)
            turn=Quaternion((0,0,1),angle)
            if i in last_q and turn.dot(last_q[i])<0:
                turn.negate()
            last_q[i]=turn.copy()
            rig.rotation_quaternion=turn
            for prop in ("location","rotation_quaternion"):
                rig.keyframe_insert(prop,frame=frame,group="Review world carrier")
            mix=timeline(t,i)
            for (bone_name,prop),components in channels.items():
                bone=rig.pose.bones[bone_name]
                if prop=="rotation_quaternion":
                    bone.rotation_mode="QUATERNION"
                vec=getattr(bone,prop)
                for idx,source in components:
                    default=1. if prop=="scale" or prop=="rotation_quaternion" and idx==0 else 0.
                    vec[idx]=sum((actions[action][source,idx].evaluate(tick)
                                  if (source,idx) in actions[action] else default)*weight for action,tick,weight in mix)
                if prop=="rotation_quaternion":
                    vec.normalize()
                bone.keyframe_insert(prop,frame=frame,group=bone_name)
        lead=formation(t,0)
        lift=lead.z-8*BASE
        off=Vector((-forward.x*180*BASE*math.cos(.48),-forward.y*180*BASE*math.cos(.48),180*BASE*math.sin(.48)))
        eye.location=Vector((lead.x,lead.y,lift))+off
        aim=Vector((lead.x,lead.y,lift+6*BASE))
        q=(aim-eye.location).to_track_quat("-Z","Y")
        if "camera" in last_q and q.dot(last_q["camera"])<0:
            q.negate()
        last_q["camera"]=q.copy()
        eye.rotation_quaternion=q
        for prop in ("location","rotation_quaternion"):
            eye.keyframe_insert(prop,frame=frame)
        # The FX-009 plane rotates about world up only and stays at its authored XY.
        beacon.rotation_euler.z=math.atan2(-(eye.location.x-RESCUE[0]),eye.location.y-RESCUE[1])
        beacon.keyframe_insert("rotation_euler",index=2,frame=frame)
    for obj in [*birds,eye,beacon]:
        action=obj.animation_data.action
        action.name=f"{obj.name} | S3 timeline"
        for curve in action.layers[0].strips[0].channelbag(obj.animation_data.action_slot).fcurves:
            for key in curve.keyframe_points:
                key.interpolation="LINEAR"


def setup_cameras_and_light(scene,group):
    scene.render.engine="BLENDER_EEVEE"
    scene.eevee.taa_render_samples=12
    scene.render.resolution_x,scene.render.resolution_y=SIZE
    scene.render.resolution_percentage=100
    scene.render.fps=FPS
    scene.frame_start,scene.frame_end=1,LAST
    scene.render.image_settings.file_format="PNG"
    scene.render.image_settings.color_mode="RGB"
    scene.view_settings.view_transform="AgX"
    world=bpy.data.worlds.new("S3 | Cool overcast river valley")
    world.use_nodes=True
    world.node_tree.nodes["Background"].inputs[0].default_value=(.40,.55,.62,1)
    world.node_tree.nodes["Background"].inputs[1].default_value=.62
    scene.world=world
    sun=bpy.data.lights.new("S3 | Soft gold overcast","SUN")
    sun.angle=math.radians(14)
    sun.energy=2.20
    sun.color=(1.,.92,.78)
    lamp=put(group,sun.name,sun)
    lamp.rotation_euler=(.47,-.55,-.45)
    camdata=bpy.data.cameras.new("S3 | Swift 50° vertical")
    camdata.sensor_fit="VERTICAL"
    camdata.sensor_height=24
    camdata.lens=12/math.tan(math.radians(25))
    camdata.clip_start,camdata.clip_end=.05,200
    camera=put(group,"S3_FixedThirdPerson",camdata)
    camera.rotation_mode="QUATERNION"
    ortho=bpy.data.cameras.new("S3 | Technical plan")
    ortho.type="ORTHO"
    ortho.sensor_fit="HORIZONTAL"
    ortho.ortho_scale=43
    ortho.clip_end=190
    top=put(group,"S3_TechnicalTop",ortho,loc=(0,25,81))
    scene.camera=camera
    markers=[(1,"Approach the river shelf"),(7,"Tree crowns respond"),(16,"Sidewind becomes visible"),
             (32,"Gust enters"),(47,"Offline separation"),(79,"Tail calls at ClearBank"),
             (337,"Reach escort radius"),(385,"Formation restored")]
    for frame,name in markers:
        scene.timeline_markers.new(name,frame=frame)
    return camera,top


def setup_review(lib,scene):
    group=coll(scene,"Review only | Leader, flock, Swift camera and shared driver")
    ctrl=setup_fx(lib,scene,group)
    birds,actions,channels=setup_actors(lib,scene,group)
    camera,top=setup_cameras_and_light(scene,group)
    bake_motion(scene,birds,actions,channels,camera,scene.objects["S3_RescueBeacon"])
    back=coll(scene,"Review only | River valley horizon")
    for type_id,loc,scale in (("A",(-16,58,-.13),1.03),("B",(14,68,-.10),.78)):
        ridge=next(o for o in imported(path_for(lib,f"ENV-009_FarRidge_{type_id}.glb"),back) if o.type=="MESH")
        ridge.location=loc
        ridge.scale=(scale,)*3
    scene.frame_set(20)
    bpy.context.view_layer.update()
    return ctrl,camera,top


def verts(obj,graph):
    evaluated=obj.evaluated_get(graph)
    mesh=evaluated.to_mesh()
    world=evaluated.matrix_world
    vv=[world@v.co for v in mesh.vertices]
    evaluated.to_mesh_clear()
    return vv


def tree_for(objects, graph):
    vertices,polys=[],[]
    for obj in objects:
        evaluated=obj.evaluated_get(graph)
        mesh=evaluated.to_mesh()
        xf=evaluated.matrix_world
        first=len(vertices)
        vertices.extend(xf @ v.co for v in mesh.vertices)
        polys.extend(tuple(first+index for index in poly.vertices) for poly in mesh.polygons)
        evaluated.to_mesh_clear()
    return BVHTree.FromPolygons(vertices,polys) if polys else None


def hits(bvh, start, end):
    delta=end-start
    if bvh is None or delta.length<.0001:
        return False
    return bvh.ray_cast(start,delta.normalized(),delta.length-.003)[0] is not None


def xy_box(vals):
    return (min(v[0] for v in vals),min(v[1] for v in vals),max(v[0] for v in vals),max(v[1] for v in vals))


def gap(first,second):
    return math.hypot(max(first[0]-second[2],second[0]-first[2],0.),
                      max(first[1]-second[3],second[1]-first[3],0.))


def in_frame(box,margin=1):
    return margin<=box[0]<box[2]<=SIZE[0]-margin and margin<=box[1]<box[3]<=SIZE[1]-margin


def pixels(scene,eye,coordinates):
    camera=eye.matrix_world
    # Project at native film fit. In this layout all tracked points stay in front of the near plane
    # whenever the corresponding cue is in the gameplay frame.
    inv=camera.inverted()
    px=[]
    focal=SIZE[1]/(2*math.tan(math.radians(25)))
    for world in coordinates:
        p=inv @ world
        if p.z < -.02:
            px.append((SIZE[0]/2+focal*p.x/-p.z,SIZE[1]/2+focal*p.y/-p.z))
    return px


def geometry_check(scene):
    scene.frame_set(1)
    graph=bpy.context.evaluated_depsgraph_get()
    beds=[o for o in scene.objects if o.type=="MESH" and o.name.startswith(("S3_GrassLand","S3_BedCap","S3_Straight_Bed","S3_OpenBank_Bed","S3_Bend_Bed"))]
    waters=[o for o in scene.objects if o.type=="MESH" and "Water" in o.name and o.name.startswith("S3_")]
    reeds=[o for o in scene.objects if o.name.startswith("S3_Reeds_")]
    vegetation=reeds+[o for o in scene.objects if o.name.startswith("S3_TreeMesh")]
    terrain_bvh=tree_for(beds,graph)
    plant_bvh=tree_for(vegetation,graph)
    water_bvh=tree_for(waters,graph)
    def floor(x,y):
        pos,normal,*_=terrain_bvh.ray_cast(Vector((x,y,6)),Vector((0,0,-1)),9)
        check(pos is not None,(x,y,"no bed"))
        return pos.z,normal.z
    poles=[]
    for gate_y,inward in ((0,1),(64,-1)):
        for i in range(97):
            x=-12+i/4
            for depth in (.002,.4,.9,1.4,1.99):
                y=gate_y+inward*depth
                z,nz=floor(x,y)
                check(abs(z)<2e-5 and nz>.9999,(x,y,z,nz))
                top=Vector((x,y,3))
                bottom=Vector((x,y,-.3))
                check(not hits(plant_bvh,top,bottom) and not hits(water_bvh,top,bottom),(x,y,"blocked seam"))
                poles.append(z)
    # Existing OpenBank rectangle is at the positive-X side of the river tile.
    xmin,xmax,ymin,ymax=RIVER_X+1.72,RIVER_X+4.55,20.-2.72,20.+2.72
    shelf=[]
    for i in range(22):
        for j in range(40):
            x=xmin+(xmax-xmin)*i/21
            y=ymin+(ymax-ymin)*j/39
            z,nz=floor(x,y)
            check(z>=-1e-5 and nz>math.cos(math.radians(4.)),(x,y,z,nz,"dry rescue platform"))
            check(not hits(plant_bvh,Vector((x,y,3)),Vector((x,y,z-.05))),(x,y,"plant on rescue platform"))
            shelf.append(z)
    # Check a 1.30-BU-wide dry run from the camera approach down to the beacon. All
    # points are checked against the delivered textured mesh rather than input bounds.
    arrival=Vector(CHAPTER["S3_ApproachSample"][0])
    finish=Vector(RESCUE)
    directed=(finish-arrival).xy.normalized()
    cross=Vector((directed.y,-directed.x,0))
    corridor=[]
    for i in range(61):
        for offset in (-.65,-.40,0.,.40,.65):
            at=arrival.lerp(finish,i/60)+cross*offset
            z,nz=floor(at.x,at.y)
            check(z >= -.003 and not hits(plant_bvh,Vector((at.x,at.y,3)),Vector((at.x,at.y,z-.05))),
                  (list(at),z,nz,"escort corridor"))
            corridor.append(z)
    anchor_support=[]
    for i in range(9):
        for j in range(9):
            x=RESCUE[0]+(i-4)*.13
            y=RESCUE[1]+(j-4)*.13
            az,_=floor(x,y)
            check(az>=-1e-5 and not hits(plant_bvh,Vector((x,y,3)),Vector((x,y,az-.04))),
                  (x,y,az,"extended OpenBank apron"))
            anchor_support.append(az)
    world_water=sum(len(w.data.polygons) for w in waters)
    water_z=max(abs(v.z-WATER) for w in waters for v in verts(w,graph))
    check(water_z<3e-6,water_z)
    route=[Vector(track(EVENT+i*(APPROACH-EVENT)/240)[0]) for i in range(241)]
    length=sum((b-a).length for a,b in zip(route,route[1:]))
    return {"gate_ground_samples":len(poles),"gate_max_abs_z_error_BU":max(map(abs,poles)),
            "gate_ground_width_BU":24.,"gate_checked_inward_BU":1.99,
            "water_triangles":world_water,"water_max_level_error_BU":water_z,
            "openbank_dry_samples":len(shelf),"openbank_floor_z_range_BU":[min(shelf),max(shelf)],
            "openbank_area_BU2":(xmax-xmin)*(ymax-ymin),"apron_beacon_support_samples":len(anchor_support),
            "escort_corridor_samples":len(corridor),"escort_corridor_width_BU":1.3,
            "escort_min_terrain_above_water_BU":min(corridor)-WATER,
            "review_separation_to_escort_seconds":APPROACH-EVENT,
            "review_return_path_length_BU":length,"escort_window_seconds":REJOIN_END-APPROACH}


def cue_check(scene):
    camera=scene.objects["S3_FixedThirdPerson"]
    ctrl=scene.objects["S3_WindControl"]
    beacon=scene.objects["S3_RescueBeacon"]
    trees=[o for o in scene.objects if o.name.startswith("S3_TreeMesh")]
    wind=[o for o in scene.objects if o.get("effectPart") in WIND]
    reeds=[o for o in scene.objects if o.name.startswith("S3_Reeds_")]
    beds=[o for o in scene.objects if o.type=="MESH" and o.name.startswith(("S3_GrassLand","S3_BedCap","S3_Straight_Bed","S3_OpenBank_Bed","S3_Bend_Bed"))]
    ring=next(o for o in beacon.children if o.name.endswith("Ring"))
    spot=next(o for o in beacon.children if o.name.endswith("SoftPoint"))
    caller=scene.objects["Review_GooseSkin_12"]
    scene.frame_set(1)
    graph=bpy.context.evaluated_depsgraph_get()
    fixed=tree_for([*reeds,*beds],graph)
    t0=[verts(o,graph) for o in trees]
    canopy_ids=[sorted(range(len(vv)),key=lambda i:vv[i].z,reverse=True)[:12] for vv in t0]
    observed={}
    measured_shift=[]
    ray_stats={"wind_phase":0,"escort_phase":0}
    projected_min={"wind_to_marker_px":float("inf"),
                   "vegetation_to_marker_px":float("inf"),"marker_size_px":float("inf")}
    phase_intervals=(("wind_phase",2.21,3.37),("escort_phase",12.65,14.55))
    element_keys={"WarnBand":"warnEnvelope","CrownSweep":"warnEnvelope","GustBand":"gustEnvelope","Leaf":"gustEnvelope"}
    camera_position_max=0.
    camera_ang_max=0.
    direction=Vector((-.98,.2)).normalized()
    gust_directions=[]
    departure_frames=[]
    for step in range(0,2*LAST-1):
        t=step/(2*FPS)
        in_wind=t<=3.79
        active=next((phase for phase,a,b in phase_intervals if a<=t<=b),None)
        if not in_wind and active is None and step%12!=0:
            continue
        scene.frame_set(1+step//2,subframe=(step%2)*.5)
        graph=bpy.context.evaluated_depsgraph_get()
        current=ctrl.evaluated_get(graph)
        model=camera.evaluated_get(graph)
        lead=scene.objects["Review_GooseRig_01"].evaluated_get(graph).matrix_world.translation
        _,heading=track(t)
        baseeye=Vector((lead.x-heading.x*180*BASE*math.cos(.48),
                        lead.y-heading.y*180*BASE*math.cos(.48),
                        lead.z-.288+180*BASE*math.sin(.48)))
        aim=Vector((lead.x,lead.y,lead.z-.288+6*BASE))
        vector=(model.matrix_world.to_quaternion() @ Vector((0,0,-1))).normalized()
        camera_position_max=max(camera_position_max,(baseeye-model.matrix_world.translation).length)
        camera_ang_max=max(camera_ang_max,vector.angle((aim-baseeye).normalized()))
        if in_wind:
            per_tree=[verts(o,graph) for o in trees]
            for i,(original, shifted) in enumerate(zip(t0,per_tree)):
                for j in canopy_ids[i]:
                    p0=pixels(scene,camera,[original[j]])
                    p1=pixels(scene,camera,[shifted[j]])
                    delta=(shifted[j]-original[j]).xy.dot(direction)
                    if p0 and p1 and in_frame((p1[0][0]-2,p1[0][1]-2,p1[0][0]+2,p1[0][1]+2)):
                        shift=math.dist(p0[0],p1[0])
                        measured_shift.append(shift)
                        if delta>.055 and shift>2.5:
                            observed.setdefault("tree",t)
            for label,field in (("warning","warnEnvelope"),("gust","gustEnvelope")):
                if current[field]>.055:
                    active_wind=[o for o in wind if element_keys[o["effectPart"]]==field]
                    if any((p:=pixels(scene,camera,verts(o,graph))) and
                           in_frame(xy_box(p)) for o in active_wind):
                        observed.setdefault(label,t)
        if active:
            bvv=verts(spot,graph)+verts(ring,graph)
            points=pixels(scene,camera,bvv)
            if not points or not in_frame(xy_box(points)):
                continue
            marker=xy_box(points)
            projected_min["marker_size_px"]=min(projected_min["marker_size_px"], marker[2]-marker[0],marker[3]-marker[1])
            look=model.matrix_world.translation
            plants=tree_for(trees,graph)
            for dest in bvv[::2]+[spot.evaluated_get(graph).matrix_world.translation]:
                check(not hits(fixed,look,dest) and not hits(plants,look,dest),(t,active,list(dest),"occluded beacon"))
                ray_stats[active]+=1
            for cluster in trees:
                v=pixels(scene,camera,verts(cluster,graph))
                if v:
                    projected_min["vegetation_to_marker_px"]=min(projected_min["vegetation_to_marker_px"],gap(marker,xy_box(v)))
            if active=="wind_phase":
                show=[o for o in wind if current[element_keys[o["effectPart"]]]>.045]
                for fx in show:
                    pts=pixels(scene,camera,verts(fx,graph))
                    if not pts:
                        continue
                    delta=(fx.evaluated_get(graph).matrix_world.translation-Vector(fx["basePosition_BU"])).xy
                    if delta.length>.06:
                        gust_directions.append(delta.normalized().dot(direction))
                    projected_min["wind_to_marker_px"]=min(projected_min["wind_to_marker_px"],gap(marker,xy_box(pts)))
                tv=verts(caller,graph)
                centre=sum(tv,Vector((0.,0.,0.)))/len(tv)
                check(not hits(fixed,look,centre) and not hits(plants,look,centre),(t,"calling bird blocked"))
    check(all(key in observed for key in ("tree","warning","gust")),observed)
    check(observed["tree"]<observed["warning"]<observed["gust"]<EVENT,observed)
    check(min(ray_stats.values())>=50,ray_stats)
    check(projected_min["wind_to_marker_px"]>3,projected_min)
    check(camera_position_max<.002 and camera_ang_max<.001,(camera_position_max,camera_ang_max))
    check(gust_directions and min(gust_directions)>.998,gust_directions)
    last_rig=scene.objects["Review_GooseRig_12"]
    for second in (EVENT,3.375,APPROACH,REJOIN_END):
        f=1+second*FPS
        scene.frame_set(math.floor(f),subframe=f%1)
        p=last_rig.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation
        departure_frames.append((second,list(p),(p-formation(second,11)).length))
    drift=departure_frames[1][1][0]-departure_frames[0][1][0]
    check(drift<-.3 and departure_frames[1][2]>.5 and departure_frames[-1][2]<1e-5,departure_frames)
    return {"first_readable_tree_seconds":observed["tree"],"first_visible_warning_seconds":observed["warning"],
            "first_visible_gust_seconds":observed["gust"],"scripted_separation_seconds":EVENT,
            "tree_lead_before_warning_seconds":observed["warning"]-observed["tree"],
            "gust_lead_before_scripted_separation_seconds":EVENT-observed["gust"],
            "tree_screen_displacement_peak_px":max(measured_shift),
            "visibility_rays_passed":ray_stats,"clearance_bbox":{k:(v if math.isfinite(v) else None) for k,v in projected_min.items()},
            "tail_checkpoints_seconds_position_slot_offset_BU":departure_frames,
            "tail_world_x_displacement_on_separation_BU":drift,
            "min_downwind_vector_dot":min(gust_directions),"camera_pose_position_error_BU":camera_position_max,
            "camera_axis_error_rad":camera_ang_max,
            "note":"LOS is computed over the frames in each test interval with the full beacon box in-frame. Off-frame portions of the return are deliberate in this offline path."}


def grayscale(scene, enable, mappings=None):
    if not enable:
        for obj,slots in mappings:
            for i,(link,mat) in enumerate(slots):
                obj.material_slots[i].link=link
                obj.material_slots[i].material=mat
        return
    dyes={"land":(.37,.40,.38,1),"water":(.24,.36,.40,1),"reeds":(.20,.28,.21,1),
          "tree":(.27,.37,.25,1),"bird":(.69,.70,.63,1),"ridge":(.28,.33,.36,1)}
    mats={}
    for key,value in dyes.items():
        mat=bpy.data.materials.new(f"S3 graybox | {key}")
        mat.diffuse_color=value
        mat.use_nodes=True
        mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value=value
        mats[key]=mat
    originals=[]
    for o in scene.objects:
        if o.type!="MESH" or not o.material_slots or o.get("effectPart"):
            continue
        if o.name.startswith("S3_TreeMesh"):
            key="tree"
        elif o.name.startswith("S3_Reeds"):
            key="reeds"
        elif "Water" in o.name:
            key="water"
        elif o.name.startswith("Review_Goose"):
            key="bird"
        elif o.name.startswith("FarRidge"):
            key="ridge"
        else:
            key="land"
        originals.append((o,[(slot.link,slot.material) for slot in o.material_slots]))
        for slot in o.material_slots:
            slot.link="OBJECT"
            slot.material=mats[key]
    return originals


def render(scene,frame,path,camera=None,samples=12):
    previous=scene.camera
    scene.camera=camera or previous
    scene.frame_set(frame)
    scene.eevee.taa_render_samples=samples
    scene.render.filepath=str(path)
    check(bpy.ops.render.render(write_still=True)=={"FINISHED"},path)
    scene.camera=previous


def binary(name):
    return shutil.which(name) or str(Path("/opt/homebrew/bin")/name)


def encode(scene,out):
    with TemporaryDirectory(prefix="s3-frames-",dir=out) as temp:
        frames=Path(temp)
        for i, frame in enumerate(range(1,LAST+1,FPS//VIDEO_FPS)):
            render(scene,frame,frames/f"{i:03d}.png",samples=6)
        subprocess.run([binary("ffmpeg"),"-hide_banner","-nostdin","-v","error","-y",
                       "-framerate",str(VIDEO_FPS),"-i",str(frames/"%03d.png"),"-vf","pad=852:394:0:0",
                       "-c:v","libx264","-threads","2","-pix_fmt","yuv420p","-crf","17",
                       "-movflags","+faststart",str(out/VIDEO)],check=True)


def decode(path):
    subprocess.run([binary("ffmpeg"),"-hide_banner","-nostdin","-v","error","-xerror","-i",str(path),
                   "-map","0:v:0","-f","null","-"],check=True)
    probed=json.loads(subprocess.check_output([binary("ffprobe"),"-v","error","-count_frames","-show_streams",
                                             "-of","json",str(path)]))
    video=next(s for s in probed["streams"] if s["codec_type"]=="video")
    frames=len(range(1,LAST+1,FPS//VIDEO_FPS))
    check(int(video["nb_read_frames"])==frames and (video["width"],video["height"])==(852,394)
          and len(probed["streams"])==1,probed)
    return {"status":"pass","source_px":list(SIZE),"coded_px":[852,394],"decoded_frames":frames,
            "audio_streams":0,"fps":VIDEO_FPS}


def glb_document(path):
    data=path.read_bytes()
    magic,version,length=struct.unpack_from("<4sII",data)
    check((magic,version,length)==(b"glTF",2,len(data)),path)
    n,kind=struct.unpack_from("<I4s",data,12)
    check(kind==b"JSON",path)
    doc=json.loads(data[20:20+n])
    count,binary_kind=struct.unpack_from("<I4s",data,20+n)
    check(binary_kind==b"BIN\x00",path)
    return doc,data[28+n:28+n+count]


def glb_textures(doc,blob):
    result={}
    for image in doc.get("images",[]):
        check("bufferView" in image,("texture must be embedded",image))
        view=doc["bufferViews"][image["bufferView"]]
        offset=view.get("byteOffset",0)
        data=blob[offset:offset+view["byteLength"]]
        result[image.get("name",str(image["bufferView"]))]={"sha256":hashlib.sha256(data).hexdigest(),
                       "bytes":len(data),"mime":image.get("mimeType")}
    return result


def transport(lib,path):
    doc,blob=glb_document(path)
    nodes={n.get("name",""):n for n in doc["nodes"]}
    check([doc["nodes"][i]["name"] for i in doc["scenes"][0]["nodes"]]==["S3_Rescue"],
          [doc["nodes"][i]["name"] for i in doc["scenes"][0]["nodes"]])
    positions={}
    for name,(loc,_) in CHAPTER.items():
        expected=Vector((loc[0],loc[2],-loc[1]))
        node=nodes[name]
        p=Vector(node.get("translation",(0,0,0)))
        check((p-expected).length<2e-5 and node.get("scale",[1,1,1])==[1,1,1],(name,list(p),list(expected)))
        positions[name]=list(p)
    geo_tree=[n for n in nodes if n.startswith("S3_TreeRig")]
    geo_wind=[n for n in nodes if n.startswith(tuple(f"S3_{role}_" for role in WIND))]
    check(len(geo_tree)==len(TREES) and len(doc.get("skins",[]))==len(TREES)
          and len(geo_wind)==sum(len(v) for v in WIND.values()),(geo_tree,geo_wind))
    check(not doc.get("animations") and not doc.get("cameras") and all(not n.startswith("Review_") for n in nodes),
          "Review-only movement and cameras must be unrouted from the visual export")
    textures=glb_textures(doc,blob)
    expected_fx=set()
    for name in ("FX-002_CrosswindWarn.glb","FX-002_Gust.glb","FX-009_RescueBeacon.glb"):
        d,b=glb_document(path_for(lib,name))
        expected_fx.update(row["sha256"] for row in glb_textures(d,b).values())
    actual={row["sha256"] for row in textures.values()}
    exact_fx=len(actual.intersection(expected_fx))
    effect_mats=[m for m in doc["materials"] if m["name"].startswith(("FX-002","RescueBeacon"))]
    check(len(effect_mats)==6 and all(m.get("alphaMode")=="BLEND" for m in effect_mats), effect_mats)
    check(sum("KHR_materials_unlit" in m.get("extensions",{}) for m in effect_mats)==2,
          "Beacon unlit material override was lost")
    return {"root":"S3_Rescue","node_count":len(nodes),"mesh_count":len(doc["meshes"]),
            "animated_tree_skin_count":len(doc["skins"]),"wind_instance_count":len(geo_wind),
            "anchors_GLTF_xyz":positions,"embedded_images":textures,
            "unique_source_FX_texture_byte_match_count":exact_fx,
            "unique_source_FX_texture_total":len(expected_fx),
            "alpha_blend_effect_material_count":len(effect_mats)}


def layout(lib):
    fx=read(files(lib,"FX-002")/"runtime_mapping.json")
    return {
        "id":ASSET,"version":VERSION,"status":"needs_review","variant":"S3_Rescue",
        "coordinates":{"units":"BU","Blender_forward":"+Y","Blender_up":"+Z",
                       "BLENDER_to_GLTF":"(x,z,-y)","BU_per_game_unit":BASE},
        "entry":{"node":"S3_Entry","location_BU":[0,0,0],"forward_BU":[0,1,0],
                 "source_segment":"LVL-S2 merge seam"},
        "exit":{"node":"S3_Exit","location_BU":[0,64,0],"forward_BU":[0,1,0],
                "destination":"LVL-S4 actual dry frontage center at local [2,-45,0]"},
        "gate":{"cross_section_x_BU":[-12,12],"dry_floor_z_BU":0,"inward_clear_depth_BU":2.0,
                "reference_water_z_BU":WATER,"water_crosses_gate":False},
        "anchors":{name:{"location_BU":loc,"role":role} for name,(loc,role) in CHAPTER.items()},
        "river_placements":[{"variant":variant,"translation_BU":[RIVER_X,y,0]} for y,variant in RIVER],
        "trees":[{"variant":name,"origin_BU":[x,y,0],"yaw_rad":a,"uniform_scale":s} for name,x,y,a,s in TREES],
        "open_bank_surface_xy_BU":[RIVER_X+1.72,RIVER_X+4.55,20.-2.72,20.+2.72],
        "wind_runtime":{"direction_xy":fx["review"]["direction"],"strength":fx["review"]["strength"],
                       "motionScale":1.,"windSpeedBUPerSecond":1.95,"placements":WIND,
                       "curve_source":"FX-002/v001/runtime_mapping.json",
                       "local_velocity":"normalize(direction_xy) * speedBUPerSecond; Blender yaw atan2(-dx,dy)",
                       "shared_input":"direction, strength, motionScale, clockSeconds and cue envelopes drive both ENV-012 tree bones and FX-002 bands/leaf",
                       "vegetation_joints":["Stem","Crown"],"default_effect_visibility":False,
                       "bellwether":"S3_WindZone placed in world before separation"},
        "review":{
            "path_xy_by_seconds":PATH,"event_seconds":EVENT,"start_escort_seconds":APPROACH,
            "finish_escort_seconds":REJOIN_END,"separated_actor_index_1_based":12,
            "source_clips":{"regular":"ANM-001/v001 Cruise_Flap_Loop",
                            "caller":"ANM-009/v001 Call_Loop; Rejoin; Cruise_Flap_Loop"},
            "camera":{"horizontal_px":852,"vertical_px":393,"distance_game_units":180,
                      "pitch_parameter_rad":.48,"fov_y_deg":50,"target_lift_game_units":6,
                      "lead_base_height_game_units":8,"depth_lift_BU_for_review":.40},
        },
        "runtime":{"resume_hint":"Checkpoint_A in S1 before the S2 fork",
                   "own_in_app":["actual foliage blend and wind triggers","separation eligibility and fixed tail selection",
                                  "bounded return path, pacing and 2-second escort trigger",
                                  "rescue/failure/retry and collision","sound and any approved accessible cues"],
                   "asset_contents":"visual terrain/materials, tree skin and configured FX instances only",
                   "character_source_not_in_assembly":"ANM-001/v001 and ANM-009/v001 rigs reviewed in the Blender master",
                   "assigned_animation_times":"review only"},
    }


def count_and_types(scene):
    return {"review_geese":len([o for o in scene.objects if o.name.startswith("Review_GooseRig")]),
            "shelter_tree_rigs":len([o for o in scene.objects if o.name.startswith("S3_TreeRig")]),
            "water_meshes":len([o for o in scene.objects if o.name.startswith("S3_") and "Water" in o.name])}


def grayscale_keyframes(scene,out,top):
    stash=grayscale(scene,True)
    try:
        render(scene,65,out/"graybox_fixed_rear.png")
        render(scene,70,out/"graybox_top.png",top)
    finally:
        grayscale(scene,False,stash)


def material_keyframes(scene,out,ctrl,top):
    snapshots={
        1:"preview_fixed_rear_approach.png",
        14:"preview_fixed_rear_tree_cue.png",
        25:"preview_fixed_rear_crosswind.png",
        65:"preview_fixed_rear_rescue.png",
        335:"preview_fixed_rear_return.png",
        389:"preview_fixed_rear_rejoined.png",
    }
    for frame,name in snapshots.items():
        render(scene,frame,out/name)
    render(scene,70,out/"preview_top.png",top)
    ctrl["strength"]=0.
    ctrl.update_tag()
    render(scene,14,out/"comparison_tree_still.png")
    ctrl["strength"]=.90
    ctrl.update_tag()


def build(lib,out,quick):
    deps,swift=source_audit(lib)
    scene,root=setup_static(lib)
    neutral=geometry_check(scene)
    export_glb(scene,out/GLB,root)
    shape=transport(lib,out/GLB)
    ctrl,cam,top=setup_review(lib,scene)
    grayscale_keyframes(scene,out,top)
    cues=cue_check(scene)
    if quick:
        render(scene,65,out/"preview_fixed_rear_rescue.png")
        return
    material_keyframes(scene,out,ctrl,top)
    scene.frame_set(65)
    scene.camera=cam
    # On open, the default view shows the gameplay camera and the full recovery pose.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=="VIEW_3D":
                area.spaces.active.region_3d.view_perspective="CAMERA"
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version=0
    check(bpy.ops.wm.save_as_mainfile(filepath=str(out/MOTHER))=={"FINISHED"},MOTHER)
    encode(scene,out)
    write(out/"s3_layout.json",layout(lib))
    write(out/"build_report.json",{"id":ASSET,"version":VERSION,"status":"needs_review",
                                  "geometry":neutral,"cues":cues,"GLB":shape,"video":decode(out/VIDEO),
                                  "dependencies":deps,"camera_swift_sha256":swift,"scene_counts":count_and_types(scene)})


def verify(lib,delivery,out):
    deps,swift=source_audit(lib)
    shape=transport(lib,delivery/GLB)
    check(bpy.ops.wm.open_mainfile(filepath=str(delivery/MOTHER))=={"FINISHED"},MOTHER)
    source=bpy.context.scene
    check(source.name==SCENE and count_and_types(source)["review_geese"]==12,source.name)
    geom_source=geometry_check(source)
    cues_source=cue_check(source)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.name="S3 | Independent GLB review"
    scene.render.fps=FPS
    group=coll(scene,"Reimported scene | delivery only")
    objects=imported(delivery/GLB,group)
    check({key for key in CHAPTER}.issubset({obj.name for obj in objects}),objects)
    neutral=geometry_check(scene)
    ctrl,cam,top=setup_review(lib,scene)
    cues_reimport=cue_check(scene)
    compare={}
    for key in ("gate_max_abs_z_error_BU","escort_min_terrain_above_water_BU"):
        compare[key]=abs(geom_source[key]-neutral[key])
        check(compare[key]<2e-5,(key,compare[key]))
    for key in ("first_readable_tree_seconds","first_visible_warning_seconds","first_visible_gust_seconds"):
        compare[key]=abs(cues_source[key]-cues_reimport[key])
        check(compare[key] < 1/FPS,(key,compare[key]))
    render(scene,65,out/"roundtrip_fixed_rear_rescue.png",cam)
    render(scene,335,out/"roundtrip_fixed_rear_return.png",cam)
    write(out/"qa.json",{"id":ASSET,"version":VERSION,"status":"needs_review",
          "independent_delivery_recheck":{
              "status":"pass","method":"Separate headless Blender opens actual editable scene, then reloads static delivery GLB in a fresh scene and reconstructs preview inputs only",
              "mother_filename":MOTHER,"GLB_filename":GLB,"reopened_blend_geometry":geom_source,
              "reopened_blend_cues":cues_source,"GLB_geometry":neutral,"GLB_cues":cues_reimport,
              "cross_format_measurement_delta":compare,"direct_GLTF_transport":shape,
              "video_full_decode":decode(delivery/VIDEO),"reimport_review_actor_counts":count_and_types(scene)
          },"dependencies":deps,"camera_swift_sha256":swift,
          "redline_review":"Quiet foliage, slate sidewind and warm recovery anchor follow project palette and redline checklist.",
          "app_baseline_reference":"Existing iPhone 18 Pro iOS 27.2 simulator, 340 tests documented in active plan.",
          "pending":["Owner visual and small screen reading review",
                     "Runtime wind, collision, physical reachability, rescue activation, escort, retry from A and timing",
                     "USDZ, RealityKit/App integration and real iPhone/iPad validation"]
          })


def main():
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument("--library",type=Path,required=True)
    args.add_argument("--out",type=Path,required=True)
    args.add_argument("--verify",type=Path)
    args.add_argument("--quick",action="store_true")
    opts=args.parse_args(sys.argv[sys.argv.index("--")+1:])
    lib=opts.library.resolve()
    output=opts.out.resolve()
    output.mkdir(parents=True,exist_ok=True)
    check(not any(output.iterdir()),"Always use a fresh temporary output directory")
    if opts.verify:
        verify(lib,opts.verify.resolve(),output)
    else:
        build(lib,output,opts.quick)


if __name__=="__main__":
    main()
