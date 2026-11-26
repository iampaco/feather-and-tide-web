"""Derive CHR-002 LODs from CHR-001. See README for headless usage."""
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get("FT_GOOSE_ASSET_ROOT", HERE.parents[1])).resolve()
SOURCE = BASE / "CHR-001" / "v001"
ANIM = BASE / "ANM-001" / "v001"
REF = runpy.run_path(str(SOURCE / "CHR-001_goose_rig_generate.py"))
ANM_TOOLS = runpy.run_path(str(ANIM / "ANM-001_cruise_flap_generate.py"))
SIZE = (852, 393)
SCALE = 27.5 / .9900
CLIP = "Cruise_Flap_Loop"
NAME = "CHR-002_goose_lods"
FOLLOWERS = [(-45,-25), (45,-25), (0,-30), (-76,-48), (-25,-49), (25,-49), (76,-48),
             (-71,-69), (-23,-71), (23,-72), (71,-71)]
SOURCE_FILES = (
    SOURCE/"CHR-001_goose_rig.blend", SOURCE/"CHR-001_goose_rig.glb",
    SOURCE/"asset_manifest.json", SOURCE/"qa.json", SOURCE/"CHR-001_goose_rig_generate.py",
    ANIM/"ANM-001_cruise_flap.blend", ANIM/"asset_manifest.json", ANIM/"qa.json",
)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def ring_subset(out, source, part, segments, rings, angles):
    """Reuse original sampled positions, UV endpoints and vertex weights."""
    face_ids = source.parts[part]
    first = min(source.faces[face_ids[0]])
    start = len(out.vertices)
    for row in rings:
        for i in angles:
            vertex = first + row * segments + i
            out.vertices.append(source.vertices[vertex])
            out.weights.append(source.weights[vertex])

    def emit(indices, uv, index):
        reverse = part.startswith("Wing.") and part.endswith(".R")
        out.faces.append(tuple(reversed(indices)) if reverse else tuple(indices))
        out.uvs.append(tuple(reversed(uv)) if reverse else tuple(uv))
        out.slots.append(index)

    # Read the original per-row V boundaries from the quad UVs.
    nrows = (len(face_ids)-2)//segments + 1
    edge = lambda row: [coord[1] for coord in source.uvs[face_ids[row*segments]]]
    values = [edge(row)[0 if not part == "Wing.R" else 2] for row in range(nrows-1)]
    values.append(edge(nrows-2)[2 if not part == "Wing.R" else 0])
    n = len(angles)
    for row, (lo, hi) in enumerate(zip(rings, rings[1:])):
        index = source.slots[face_ids[lo * segments]]
        for i, a in enumerate(angles):
            j = (i+1)%n
            b = angles[j] if j else segments
            va, vb = start + row*n+i, start + row*n+j
            u0, u1, v0, v1 = a/segments, b/segments, values[lo], values[hi]
            emit((va,vb,vb+n,va+n), ((u0,v0),(u1,v0),(u1,v1),(u0,v1)), index)

    for row, cap, v in [(0,0,.05),(len(rings)-1,1,.95)]:
        indices = [start + row*n+i for i in range(n)]
        coordinates = [(0.5+.04*math.sin(math.tau*a/segments),v+.04*math.cos(math.tau*a/segments)) for a in angles]
        if cap == 0:
            indices.reverse()
            coordinates.reverse()
        emit(indices, coordinates, source.slots[face_ids[-2+cap]])
    out.parts[part] = list(range(len(out.faces)-(len(rings)-1)*n-2, len(out.faces)))


def build_lod1(source):
    out = REF["GooseMesh"]()
    ring_subset(out,source,"Body and crown",20,
                [0,1,3,5,7,9,11,13,14,15,16,17,18,19,20,21,22,24],
                [0,2,4,5,6,8,10,12,14,15,16,18])
    ring_subset(out,source,"Bill",12,[0,1,3,4],[0,2,3,6,9,10])
    for i in range(5):
        ring_subset(out,source,f"Tail feather {i+1}",6,[0,2,5],[0,1,3,5])
    for side in "LR":
        ring_subset(out,source,f"Eye.{side}",8,[0,2,3],[0,2,4,6])
        ring_subset(out,source,f"Foot.{side}",10,[0,2,5],[0,2,5,8])
        ring_subset(out,source,f"Wing.{side}",14,[0,1,2,4,6,8,9,10,12,13],[0,2,4,6,7,8,10,12])
        for i in range(9):
            ring_subset(out,source,f"Flight feather {i+1}.{side}",6,[0,2,5],[0,1,3,5])
        ring_subset(out,source,f"Outer primary.{side}",6,[0,2,4,5],[0,1,3,5])
    return out


def build_lod2(source):
    out = REF["GooseMesh"]()
    ring_subset(out,source,"Body and crown",20,
                [0,2,5,8,11,13,14,16,18,21,22,24],[0,2,5,8,10,12,15,18])
    ring_subset(out,source,"Bill",12,[0,2,4],[0,3,6,9])
    for i in [1,3,5]:
        ring_subset(out,source,f"Tail feather {i}",6,[0,2,5],[0,1,3,5])
    # One closed envelope per wing combines coverts and the flight-feather edge.
    # The six-point cross section gives the dark trailing third its own smooth UV strip.
    profiles = [
        (.080,.017,-.193,.027,.048), (.124,.040,-.224,.037,.039),
        (.178,.056,-.253,.036,.034), (.288,.076,-.277,.028,.027),
        (.398,.053,-.281,.030,.023), (.511,.017,-.271,.037,.017),
        (.625,-.050,-.252,.045,.012), (.712,-.117,-.231,.051,.006),
        (.778,-.151,-.210,.053,.003), (.8002,-.176,-.178,.058,.0007),
    ]
    for side,sign in [("L",-1),("R",1)]:
        rings = []
        for x, leading, trailing, z, h in profiles:
            center = .69*leading + .31*trailing
            def sample(s,c,x=x,leading=leading,trailing=trailing,z=z,h=h,center=center):
                width = leading-center if s >= 0 else center-trailing
                return (sign*x, center+width*s/.8660254037844386, z+h*c)
            rings.append(((x-.08)/(.8002-.08),sample))
        out.tube(f"Wing.{side}", rings, 6, lambda p: REF["wing_weights"](abs(p[0]), side),
                 lambda row,angle: 2 if row >= 7 or angle in {4,5} else 0, reverse=sign > 0)
    return out


def make_lod(builder, source, rig, coll, tier):
    model = builder.object(coll, list(source.data.materials))
    model.name = model.data.name = f"Goose_{tier}"
    by_bone = {name: model.vertex_groups.new(name=name) for name in source.vertex_groups.keys()}
    for i, entries in enumerate(builder.weights):
        norm = sum(entries.values())
        for name, value in entries.items():
            by_bone[name].add([i], value/norm, "REPLACE")
    model.parent = rig
    mod = model.modifiers.new("GooseSkin", "ARMATURE")
    mod.object = rig
    model["asset_id"] = "CHR-002"
    model["lod"] = tier
    return model


def materials(model, source):
    for original in source.data.gltf2_variant_mesh_data:
        mapping = model.data.gltf2_variant_mesh_data.add()
        mapping.material_slot_index = original.material_slot_index
        mapping.material = original.material
        for variant in original.variants:
            mapping.variants.add().variant.variant_idx = variant.variant.variant_idx
    for original in source.data.gltf2_variant_default_materials:
        setting = model.data.gltf2_variant_default_materials.add()
        setting.material_slot_index = original.material_slot_index
        setting.default_material = original.default_material


def geo(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    data = obj.evaluated_get(deps).data
    data.calc_loop_triangles()
    return (np.array([obj.matrix_world @ v.co for v in data.vertices]),
            np.array([tuple(t.vertices) for t in data.loop_triangles]))


def project(scene, camera, verts):
    coords = np.array([world_to_camera_view(scene,camera,Vector(v))[:2] for v in verts])
    return coords * np.array(SIZE)


def masks(tris, coords, lo, hi):
    # The grid is 2x supersampled in the same fixed gameplay projection.
    xy = (coords-lo)*2
    width, height = ((hi-lo)*2).astype(int)
    coverage = np.zeros((height,width),dtype=bool)
    for tri in xy[tris]:
        x0,y0 = np.maximum(0,np.floor(tri.min(axis=0)).astype(int))
        x1,y1 = np.minimum([width,height],np.ceil(tri.max(axis=0)).astype(int))
        if x1 <= x0 or y1 <= y0:
            continue
        yy,xx = np.mgrid[y0:y1,x0:x1] + .5
        a,b,c = tri
        ab,bc,ca = b-a,c-b,a-c
        cross = lambda p,e: e[0]*(yy-p[1]) - e[1]*(xx-p[0])
        d1,d2,d3 = cross(a,ab),cross(b,bc),cross(c,ca)
        coverage[y0:y1,x0:x1] |= ((d1>=0)&(d2>=0)&(d3>=0))|((d1<=0)&(d2<=0)&(d3<=0))
    return coverage


def set_frame(scene, value):
    scene.frame_set(int(value),subframe=value-int(value))


def geometry_checks(scene,camera,models,rig):
    report = {}
    for model in models:
        model.data.calc_loop_triangles()
        coords = np.array([tuple(v.co) for v in model.data.vertices])
        assert np.isfinite(coords).all()
        assert all(p.area > 1e-10 for p in model.data.polygons), model.name
        assert all(abs(sum(g.weight for g in v.groups)-1) < 2e-6 and 0<len(v.groups)<=4 for v in model.data.vertices)
        report[model.name] = {"triangles":len(model.data.loop_triangles),
                              "vertices":len(coords),"bounds_BU":[coords.min(0).tolist(),coords.max(0).tolist()],
                              "dimensions_BU":np.ptp(coords,axis=0).tolist()}
    for model,budget in zip(models,[4000,1500,500]):
        record = report[model.name]
        assert record["triangles"] <= budget, record
        reference = report[models[0].name]
        assert abs(record["dimensions_BU"][0]-reference["dimensions_BU"][0]) < .001
        assert abs(record["dimensions_BU"][1]-reference["dimensions_BU"][1]) < .001
    near_far = {}
    for idx, distance in [(1,150),(2,560)]:
        rig.location.y = distance/SCALE
        bpy.context.view_layer.update()
        pairs = []
        for frame in [1,7,11,17,23,29,35,41,47,53]:
            set_frame(scene,frame)
            p0,t0 = geo(models[idx-1])
            p1,t1 = geo(models[idx])
            p0,p1 = project(scene,camera,p0),project(scene,camera,p1)
            extent = np.concatenate([p0,p1],axis=0)
            lo,hi = np.floor(extent.min(0))-1,np.ceil(extent.max(0))+1
            m0,m1 = masks(t0,p0,lo,hi),masks(t1,p1,lo,hi)
            pairs.append((frame, (m0&m1).sum()/(m0|m1).sum(),
                          float(np.max(np.abs(np.array([p0.min(0),p0.max(0)])-np.array([p1.min(0),p1.max(0)])))),
                          float(np.ptp(p0[:,0])),float(np.ptp(p1[:,0]))))
        near_far[models[idx].name] = {"forward_offset_game_units":distance,
                                      "frames_iou_max_edge_delta_widths_px":pairs,
                                      "min_mask_iou":min(p[1] for p in pairs),
                                      "max_bounds_edge_delta_px":max(p[2] for p in pairs)}
        assert min(p[1] for p in pairs)>[0,.84,.73][idx], near_far
        assert max(p[2] for p in pairs)<1.7, near_far
    rig.location.y = 0
    bpy.context.view_layer.update()
    return report,near_far


def only(models, model):
    for obj in models:
        obj.hide_render = obj != model
        obj.hide_set(obj != model)


def still(scene, view, path, samples=10, size=SIZE):
    REF["render_settings"](scene,size,samples)
    scene.camera = view
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True,scene=scene.name)


def export(scene, rig, model, path):
    only([model],model)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    model.select_set(True)
    bpy.context.view_layer.objects.active = rig
    scene.frame_set(1)
    bpy.ops.export_scene.gltf(filepath=str(path),export_format="GLB",use_selection=True,
                              export_yup=True, export_animations=True, export_force_sampling=True,
                              export_animation_mode="ACTIVE_ACTIONS", export_anim_single_armature=False,
                              export_nla_strips_merged_animation_name=CLIP,
                              export_anim_slide_to_zero=True)
    doc,binary = REF["load_glb"](path)
    clip, = doc["animations"]
    assert clip["name"] == CLIP, clip["name"]
    channels = []
    for channel in clip["channels"]:
        sample = clip["samplers"][channel["sampler"]]
        values = ANM_TOOLS["accessor"](doc,binary,sample["output"])
        node = doc["nodes"][channel["target"]["node"]]
        prop = channel["target"]["path"]
        if np.max(np.abs(values-values[0])) < 1e-6:
            if prop == "rotation":
                assert abs(float(values[0] @ node.get(prop,[0,0,0,1]))) > 1-1e-6
            else:
                default = [1,1,1] if prop == "scale" else [0,0,0]
                np.testing.assert_allclose(values[0],node.get(prop,default),atol=1e-6)
            continue
        assert node["name"] != "Root"
        channels.append(channel)
    assert len(channels)==13
    samplers = sorted({channel["sampler"] for channel in channels})
    for channel in channels:
        channel["sampler"] = samplers.index(channel["sampler"])
    clip["channels"] = channels
    clip["samplers"] = [clip["samplers"][i] for i in samplers]
    ANM_TOOLS["write_glb"](path,doc,binary)


def review_flock(scene, group, rig, action, models):
    bases = []
    for index, (x,y) in enumerate(FOLLOWERS):
        copy_rig = rig.copy()
        group.objects.link(copy_rig)
        copy_rig.name = f"FollowerRig.{index+1:02}"
        copy_rig.location = (x/SCALE,y/SCALE,-2/SCALE)
        copy_rig.scale = (.8,)*3
        copy_rig.animation_data_clear()
        animation = copy_rig.animation_data_create()
        strip = animation.nla_tracks.new().strips.new(CLIP,-52,action)
        strip.action_slot = action.slots[0]
        strip.action_frame_start,strip.action_frame_end = 1,53
        strip.repeat = 6
        strip.frame_start = -51 - (index*11)%52
        strip.frame_end = strip.frame_start + 52*6
        birds = []
        for model in models:
            bird = model.copy()
            group.objects.link(bird)
            bird.name = f"Follower.{index+1:02}.{model['lod'] if 'lod' in model else 'LOD0'}"
            bird.parent = copy_rig
            bird.material_slots[0].link = "OBJECT"
            bird.material_slots[0].material = bpy.data.materials[f"Body_Follower_{'ABC'[index%3]}"]
            bird.modifiers["GooseSkin"].object = copy_rig
            birds.append(bird)
        bases.append((copy_rig,birds,x,y,index))
    return bases


def lodge(scene,birds,cam,factor):
    report = {}
    for copy_rig,variants,x,y,index in birds:
        offset_x = x + (1 if x>=0 else -1)*(index%4)*factor*1.6
        offset_y = y + (34 + index*5.5)*factor
        copy_rig.location = (offset_x/SCALE,offset_y/SCALE,-2/SCALE)
    bpy.context.view_layer.update()
    for copy_rig,variants,x,y,index in birds:
        # This proxy scales with projected width without following wing phase.
        root = copy_rig.location.copy()
        basis = project(scene,cam,np.array([root-Vector((.64,0,0)),root+Vector((.64,0,0))]))
        width = float(np.ptp(basis[:,0]))
        choice = 2 if width<32 else 1 if width<70 else 0
        only(variants,variants[choice])
        report[str(index+1)] = {"lod":choice,"projected_span_proxy_px":width}
    return report


def motion(scene,camera,output,birds,models):
    only(models,models[0])
    REF["render_settings"](scene,SIZE,7)
    scene.camera=camera
    evidence = []
    with TemporaryDirectory(prefix="chr-002-video-") as temp:
        directory = Path(temp)
        for i in range(54):
            factor = i/53*11.0
            scene.frame_set(i*2 % 52+1)
            evidence.append(lodge(scene,birds,camera,factor))
            scene.render.filepath = str(directory/f"{i:03d}.png")
            bpy.ops.render.render(write_still=True,scene=scene.name)
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-framerate","24","-i",
                        str(directory/"%03d.png"),"-an","-c:v","libx264","-crf","15","-pix_fmt","yuv420p",
                        "-vf","pad=852:394:0:0:color=0x778579","-movflags","+faststart",
                        str(output/"preview_fixed_rear.mp4")],check=True)
    return evidence


def main(output):
    output.mkdir(parents=True,exist_ok=True)
    assert not any(output.iterdir()), "Use an empty staging directory."
    manifest = json.loads((SOURCE/"asset_manifest.json").read_text())
    assert manifest["status"]=="done"
    for path in (SOURCE_FILES[0],SOURCE_FILES[1],SOURCE_FILES[3],SOURCE_FILES[4]):
        assert manifest["files"][path.name]==digest(path), path
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE_FILES[0]))
    scene = bpy.context.scene
    scene.name = "CHR-002 | Fixed camera LOD review"
    camera = bpy.data.objects["Gameplay | fixed rear"]
    top = bpy.data.objects["Review | top"]
    rig = bpy.data.objects["GooseRig"]
    model0 = bpy.data.objects["Goose_LOD0"]
    source = REF["model"]()
    assert len(model0.data.vertices)==len(source.vertices)
    np.testing.assert_allclose([tuple(v.co) for v in model0.data.vertices],source.vertices,atol=1e-7)
    # Keep the fixed camera driven by the rounded CHR-001 project contract.
    eye = (0,-180*math.cos(.48)/SCALE,(180*math.sin(.48)-8)/SCALE)
    camera.location = eye
    camera.rotation_euler = (Vector((0,0,-2/SCALE))-camera.location).to_track_quat("-Z","Y").to_euler()
    collection = REF["collection"](scene,"CHR-002 | Editable tiers")
    model1 = make_lod(build_lod1(source),model0,rig,collection,"LOD1")
    model2 = make_lod(build_lod2(source),model0,rig,collection,"LOD2")
    models = [model0,model1,model2]
    with bpy.data.libraries.load(str(ANIM/"ANM-001_cruise_flap.blend")) as (library,dest):
        assert CLIP in library.actions
        dest.actions = [CLIP]
    (action,) = dest.actions
    rig.animation_data_clear()
    animation = rig.animation_data_create()
    animation.action = action
    animation.action_slot = action.slots[0]
    scene.render.fps,scene.render.fps_base = 48,1
    scene.frame_start,scene.frame_end = 1,52
    scene.use_preview_range = False
    shapes, projected = geometry_checks(scene,camera,models,rig)
    print("LOD_GEOMETRY",json.dumps({"shapes":shapes,"projected":projected}),flush=True)

    clay = REF["plain"]("Silhouette clay","747A77")
    distances = [0,150,560]
    bpy.context.view_layer.material_override = clay
    for index, (model,distance) in enumerate(zip(models,distances)):
        only(models,model)
        rig.location.y = distance/SCALE
        scene.frame_set(11)
        still(scene,camera,output/f"graybox_fixed_lod{index}.png")
    bpy.context.view_layer.material_override = None
    bpy.context.preferences.addons["io_scene_gltf2"].preferences.KHR_materials_variants_ui = True
    for model in models[1:]:
        materials(model,model0)
        only(models,model)
        rig.location.y = 0
        scene.frame_set(1)
        still(scene,top,output/f"preview_top_{model['lod'].lower()}.png",18,(852,560))
        export(scene,rig,model,output/f"CHR-002_{model['lod']}.glb")
    for before,after,distance in ((0,1,150),(1,2,560)):
        for index in [before,after]:
            only(models,models[index])
            rig.location.y = distance/SCALE
            scene.frame_set(11)
            still(scene,camera,output/f"preview_fixed_switch_{before}{after}_lod{index}.png",14)
    rig.location.y = 0
    bpy.context.view_layer.update()
    group = REF["collection"](scene,"Preview | 11 phase-shifted companions")
    birds = review_flock(scene,group,rig,action,models)
    only(models,model0)
    scene.frame_set(11)
    flock = lodge(scene,birds,camera,4.2)
    still(scene,camera,output/"preview_fixed_flock.png",16)
    scene.camera = camera
    scene.render.filepath = "//"
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{NAME}.blend"),relative_remap=False)
    evidence = motion(scene,camera,output,birds,models)
    write_json(output/"generation_evidence.json", {"geometry":shapes,"projection":projected,"flock_still":flock,
        "flock_video":evidence,"source_hashes":{str(path.relative_to(BASE)):digest(path) for path in SOURCE_FILES}})


if __name__ == "__main__":
    main(Path(sys.argv[sys.argv.index("--")+1]).resolve())
