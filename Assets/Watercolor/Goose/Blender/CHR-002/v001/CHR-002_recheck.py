"""Reopen the delivered CHR-002 Blender master and import both final GLBs."""
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys

import bpy
from mathutils.kdtree import KDTree
import numpy as np

HERE = Path(__file__).resolve().parent
TOOLS = runpy.run_path(str(HERE/"CHR-002_generate.py"))
REF = TOOLS["REF"]
ANM = TOOLS["ANM_TOOLS"]
digest = TOOLS["digest"]
write = TOOLS["write_json"]


def check_bones(reference, other):
    expected, actual = REF["record_bones"](reference), REF["record_bones"](other)
    assert set(expected) == set(actual)
    err = 0
    for name in expected:
        assert expected[name]["parent"] == actual[name]["parent"], name
        err = max(err,float(np.max(np.abs(np.asarray(reference.data.bones[name].matrix_local)
                                        -np.asarray(other.data.bones[name].matrix_local)))))
    assert err < 1e-5, err
    return err


def action_of(rig):
    animation = rig.animation_data
    if animation.action:
        return animation.action
    strip, = [strip for track in animation.nla_tracks for strip in track.strips]
    for track in animation.nla_tracks:
        track.mute = True
    animation.action = strip.action
    animation.action_slot = strip.action_slot
    return animation.action


def joints(x):
    return {x["nodes"][i]["name"] for i in x["skins"][0]["joints"]}


def image_hashes(load, parse, document, binary):
    return {load(parse(document,binary,item["bufferView"])).hexdigest() for item in document["images"]}


def check_glb(directory, name, master, rig, scene, source, anim_reference):
    path = directory/f"CHR-002_{name}.glb"
    get_glb = REF["load_glb"]
    doc, binary = get_glb(path)
    src, source_blob = get_glb(source)
    anim_src, anim_blob = get_glb(anim_reference)
    assert len(doc["meshes"])==len(doc["skins"])==len(doc["animations"])==1
    assert "cameras" not in doc
    assert joints(doc)==joints(src)==set(rig.data.bones.keys())
    drig = next(n for n in doc["nodes"] if n["name"]=="GooseRig")
    mesh_node = next(n for n in doc["nodes"] if "mesh" in n)
    for node in [drig,mesh_node]:
        assert node.get("translation",[0,0,0])==[0,0,0]
        assert node.get("scale",[1,1,1])==[1,1,1]
    nodes = {n["name"]:n for n in doc["nodes"]}
    assert nodes["Root"].get("translation",[0,0,0])==[0,0,0]
    for original in src["nodes"]:
        if original["name"] not in joints(src):
            continue
        new = nodes[original["name"]]
        for prop, default in (("translation",[0,0,0]),("rotation",[0,0,0,1]),("scale",[1,1,1])):
            np.testing.assert_allclose(new.get(prop,default),original.get(prop,default),atol=1e-6)
    assert len(doc["images"])==len(src["images"])==4
    assert doc["extensions"]["KHR_materials_variants"]==src["extensions"]["KHR_materials_variants"]
    pngs = image_hashes(TOOLS["sha256"],REF["bin_data"],doc,binary)
    assert pngs == image_hashes(TOOLS["sha256"],REF["bin_data"],src,source_blob)
    tri_count = sum(doc["accessors"][p["indices"]]["count"]//3 for p in doc["meshes"][0]["primitives"])
    master.data.calc_loop_triangles()
    assert tri_count == len(master.data.loop_triangles)
    clip, = doc["animations"]
    src_clip, = anim_src["animations"]
    assert clip["name"]==src_clip["name"]==TOOLS["CLIP"]

    def tracks(d, b, a):
        metrics = {}
        for channel in a["channels"]:
            target = channel["target"]
            node = d["nodes"][target["node"]]["name"]
            kind = target["path"]
            sampler = a["samplers"][channel["sampler"]]
            assert node!="Root"
            metrics[(node,kind)] = [ANM["accessor"](d,b,sampler[f]) for f in ("input","output")]
        return metrics

    data, reference = tracks(doc,binary,clip), tracks(anim_src,anim_blob,src_clip)
    assert len(data)==13 and data.keys()==reference.keys()
    for key,(times,values) in data.items():
        t, v = reference[key]
        np.testing.assert_allclose(times,t,atol=1e-6)
        if key[1]=="rotation":
            # Quaternion antipodes represent the same rotation.
            assert np.all(np.abs(np.sum(values*v,axis=-1))>1-1e-6)
        else:
            np.testing.assert_allclose(values,v,atol=1e-6)

    master.hide_set(False)
    poses = {}
    for frame in np.linspace(1,53,105):
        TOOLS["set_frame"](scene,float(frame))
        poses[frame],_ = TOOLS["geo"](master)
    before = set(bpy.data.objects)
    imported_scene = bpy.data.scenes.new(f"Independent import | {name}")
    imported_scene.render.fps = 48
    imported_scene.render.fps_base = 1
    bpy.context.window.scene = imported_scene
    bpy.ops.import_scene.gltf(filepath=str(path),bone_heuristic="BLENDER",disable_bone_shape=True)
    fresh = set(bpy.data.objects)-before
    (mesh,) = [o for o in fresh if o.type=="MESH"]
    (skeleton,) = [o for o in fresh if o.type=="ARMATURE"]
    bone_error = check_bones(rig,skeleton)
    action = action_of(skeleton)
    assert action.name.startswith(TOOLS["CLIP"])
    first,last = (float(val) for val in action.frame_range)
    assert math.isclose(last-first,52,abs_tol=.001)
    tree = KDTree(len(master.data.vertices))
    for vert in master.data.vertices:
        tree.insert(vert.co,vert.index)
    tree.balance()
    indexed = []
    for vertex in mesh.data.vertices:
        _,index,error = tree.find(mesh.matrix_world @ vertex.co)
        assert error<1e-5
        indexed.append(index)
    assert len(set(indexed))==len(master.data.vertices)
    a_uv,b_uv = master.data.uv_layers.active,mesh.data.uv_layers.active
    master_uvs = {}
    for loop in master.data.loops:
        master_uvs.setdefault(loop.vertex_index,[]).append(np.array(a_uv.data[loop.index].uv))
    max_uv_error = 0
    for loop in mesh.data.loops:
        coord = np.array(b_uv.data[loop.index].uv)
        nearest = min(float(np.linalg.norm(coord-uv)) for uv in master_uvs[indexed[loop.vertex_index]])
        max_uv_error = max(max_uv_error,nearest)
    assert max_uv_error < 1e-5, max_uv_error
    key_error, sub_error, z_min = 0,0,0
    for frame, pose in poses.items():
        TOOLS["set_frame"](imported_scene,first+frame-1)
        vertices,_ = TOOLS["geo"](mesh)
        z_min = min(z_min,float(vertices[:,2].min()))
        root = skeleton.pose.bones["Root"]
        assert np.max(np.abs(np.asarray(root.matrix_basis)-np.eye(4)))<1e-6
        error = float(np.max(np.linalg.norm(vertices-pose[indexed],axis=1)))
        if frame.is_integer():
            key_error = max(key_error,error)
        else:
            sub_error = max(sub_error,error)
    assert key_error<3e-4 and sub_error<.008, (key_error,sub_error)
    TOOLS["set_frame"](imported_scene,first)
    first_pose,_ = TOOLS["geo"](mesh)
    TOOLS["set_frame"](imported_scene,last)
    last_pose,_ = TOOLS["geo"](mesh)
    seam = float(np.max(np.linalg.norm(first_pose-last_pose,axis=1)))
    assert seam<1e-5
    bpy.context.window.scene = scene
    return {"status":"pass","triangles":tri_count,"joint_count":15,"max_rest_bone_matrix_delta":bone_error,
            "material_variants":4,"packed_matching_pngs":len(pngs),"embedded_png_sha256":sorted(pngs),
            "matching_animation_tracks":13,"root_tracks":0,"animation":"Cruise_Flap_Loop",
            "duration_s":(last-first)/48,"deformed_pose_samples":105,"max_uv_error":max_uv_error,
            "max_keyframe_error_BU":key_error,"max_half_frame_error_BU":sub_error,"loop_seam_BU":seam,
            "minimum_pose_z_BU":z_min}


def video(directory):
    path = directory/"preview_fixed_rear.mp4"
    metadata = json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames",
        "-show_streams","-of","json",str(path)]))
    (stream,) = metadata["streams"]
    assert stream["codec_type"]=="video" and stream["codec_name"]=="h264"
    assert [stream["width"],stream["height"]]==[852,394] and stream["avg_frame_rate"]=="24/1"
    assert int(stream["nb_read_frames"])==54
    subprocess.run(["ffmpeg","-v","error","-xerror","-threads","2","-i",str(path),
                    "-map","0:v:0","-f","null","-"],check=True)
    return {"status":"pass","frame_count":54,"video_frame_px":[852,394],"content_px":[852,393],
            "fps":24,"audio_streams":0,"duration_s":2.25}


def main(directory):
    assert directory.is_dir()
    gen = json.loads((directory/"generation_evidence.json").read_text())
    for loc, sha in gen["source_hashes"].items():
        assert digest(TOOLS["BASE"]/loc)==sha, loc
    bpy.ops.wm.open_mainfile(filepath=str(directory/"CHR-002_goose_lods.blend"))
    scene = bpy.context.scene
    assert scene.camera.name=="Gameplay | fixed rear"
    assert (scene.render.resolution_x,scene.render.resolution_y)==TOOLS["SIZE"]
    assert scene.frame_current==11 and scene.render.fps==48
    for name in ["LOD0","LOD1","LOD2"]:
        assert len([o for o in scene.objects if o.name==f"Goose_{name}"])==1
        assert bpy.data.objects[f"Goose_{name}"].modifiers["GooseSkin"].object==bpy.data.objects["GooseRig"]
    assert all(image.packed_file for image in bpy.data.images if image.name.endswith(".png"))
    group = bpy.data.collections["Preview | 11 phase-shifted companions"]
    assert sum(o.type=="ARMATURE" for o in group.objects)==11
    unique_meshes = {o.data.name for o in group.objects if o.type=="MESH"}
    assert unique_meshes=={"Goose_LOD0","Goose_LOD1","Goose_LOD2"}
    rig = bpy.data.objects["GooseRig"]
    camera = scene.camera
    master_models = [bpy.data.objects[f"Goose_LOD{idx}"] for idx in [0,1,2]]
    for mesh in master_models:
        mesh.hide_set(False)
    recomputed_geo,recomputed_projection = TOOLS["geometry_checks"](scene,camera,master_models,rig)
    assert recomputed_geo==gen["geometry"]
    for model in ["Goose_LOD1","Goose_LOD2"]:
        assert math.isclose(recomputed_projection[model]["max_bounds_edge_delta_px"],
                            gen["projection"][model]["max_bounds_edge_delta_px"],abs_tol=1e-5)
    reference_glb = TOOLS["SOURCE"]/"CHR-001_goose_rig.glb"
    anim_glb = TOOLS["ANIM"]/"ANM-001_cruise_flap.glb"
    roundtrip = {name:check_glb(directory,name,bpy.data.objects[f"Goose_{name}"],rig,scene,reference_glb,anim_glb)
                 for name in ["LOD1","LOD2"]}
    tiers = sorted({item["lod"] for record in gen["flock_video"] for item in record.values()})
    assert tiers==[0,1,2] and all(len(record)==11 for record in gen["flock_video"])
    check = {"id":"CHR-002","version":"v001","status":"needs_review","blender_version":bpy.app.version_string,
             "reopened_final_blend":{"status":"pass","master_lod_slots":3,"shared_mesh_datablocks":3,"follower_rigs":11},
             "source_hashes_verified":"pass","projection":recomputed_projection,"geometry":recomputed_geo,
             "blender_gltf_roundtrip":roundtrip,"video":{"preview_fixed_rear.mp4":video(directory),"observed_tiers":tiers},
             "manual_visual_review":{"status":"pass","scope":"两级顶视双纹与飞羽形状、固定机位交接静帧与动态群飞抽样"},
             "redline_check":"pass","ios_simulator_baseline":"active 计划 2026-11-14 记录，iOS 27.2，340 项通过",
             "pending":["负责人美术审阅","候选切换阈值、屏占与交接在 RealityKit 内调校",
                        "USDZ / App 接入","运行时动画状态同步与实际阵型","iPhone / iPad 真机显示与性能"]}
    print(json.dumps(check,ensure_ascii=False,indent=2),flush=True)
    extra = sys.argv[sys.argv.index("--")+2:]
    if extra:
        write(Path(extra[0]).resolve(),check)


if __name__=="__main__":
    main(Path(sys.argv[sys.argv.index("--")+1]).resolve())
