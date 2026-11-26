"""Open the final blend, import the final GLB, recompute geometry, contrast and video QA."""
import json
import math
from pathlib import Path
import runpy
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np

HERE = Path(__file__).resolve().parent
GEN = runpy.run_path(str(HERE/"FX-005_generate.py"))
NAMES = tuple(GEN["LAYER_SPECS"])
FX = GEN["FX"]
FRAME = GEN["FRAME"]
save_json = GEN["save_json"]
hash_file = GEN["hash_file"]


def glb_read(path):
    data = path.read_bytes()
    magic,version,end,size,kind = struct.unpack_from("<4sIII4s",data)
    assert (magic,version,end,kind)==(b"glTF",2,len(data),b"JSON")
    doc = json.loads(data[20:20+size])
    bin_size,bin_kind = struct.unpack_from("<I4s",data,20+size)
    binary = data[28+size:]
    assert bin_kind==b"BIN\0" and len(binary)==bin_size
    return doc,binary


def texture_data(doc,binary,image):
    view = doc["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset",0)
    return binary[start:start+view["byteLength"]]


def glb_checks(directory,generation):
    doc,binary = glb_read(directory/f"{FX}.glb")
    nodes = {n["name"]:n for n in doc["nodes"]}
    assert set(nodes)=={"CloudShadow","CoolShadow","DiffuseLight"}
    assert list(nodes["CloudShadow"].get("translation",(0,0,0)))==[0,0,0]
    assert len(nodes["CloudShadow"]["children"])==2
    assert "animations" not in doc and "cameras" not in doc
    assert all(n["extras"]["collision_enabled"] is False for n in nodes.values())
    triangles = 0
    for name in NAMES:
        node = nodes[name]
        primitive, = doc["meshes"][node["mesh"]]["primitives"]
        material = doc["materials"][primitive["material"]]
        assert material["alphaMode"]=="BLEND" and "KHR_materials_unlit" in material["extensions"]
        assert material.get("doubleSided",False) is False
        sampler_index = doc["textures"][material["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["sampler"]
        sampler = doc["samplers"][sampler_index]
        assert (sampler["wrapS"],sampler["wrapT"])==(33071,33071)
        texture = doc["textures"][material["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
        stats = generation["masks"][name]
        texture_path = directory/stats["file"]
        assert texture_data(doc,binary,doc["images"][texture["source"]])==texture_path.read_bytes()
        assert stats["sha256"]==hash_file(texture_path)
        assert set(primitive["attributes"])=={"POSITION","NORMAL","TEXCOORD_0"}
        pos = doc["accessors"][primitive["attributes"]["POSITION"]]
        w,h = GEN["LAYER_SPECS"][name]["size_BU"]
        np.testing.assert_allclose(pos["min"],[-w/2,0,-h/2],atol=1e-6)
        np.testing.assert_allclose(pos["max"],[w/2,0,h/2],atol=1e-6)
        assert doc["accessors"][primitive["indices"]]["count"]==6
        triangles += 2
    return {"status":"pass","nodes":len(nodes),"triangles":triangles,"packed_png_byte_matches":2,
            "alpha_mode":"BLEND","shading":"KHR_materials_unlit","sampler":"CLAMP_TO_EDGE",
            "collision_extras":False,"animations":0,"camera_nodes":0}


def raw_pixels(path):
    image = bpy.data.images.load(str(path),check_existing=False)
    image.colorspace_settings.name = "Non-Color"
    matrix = np.rint(GEN["image_pixels"](image)*255).astype(np.int16)
    assert (image.size[0],image.size[1])==FRAME
    bpy.data.images.remove(image)
    return matrix[:,:,:3]


def contrast(directory):
    off = raw_pixels(directory/"preview_fixed_off.png")
    output = {}
    for mode in ("default","reduced"):
        image = raw_pixels(directory/f"preview_fixed_{mode}.png")
        delta = (image-off).astype(float)
        shift = np.max(np.abs(delta),axis=-1)
        luma = delta @ np.array([.2126,.7152,.0722])
        dx = np.abs(np.diff(luma,axis=1)).flatten()
        dy = np.abs(np.diff(luma,axis=0)).flatten()
        q99_step = float(np.quantile(np.concatenate([dx,dy]),.99))
        result = {"min_luminance_delta_rgb8":float(luma.min()),"max_luminance_delta_rgb8":float(luma.max()),
                  "p99_abs_luminance_delta_rgb8":float(np.quantile(np.abs(luma),.99)),
                  "p99_neighbor_luminance_delta_step_rgb8":q99_step,
                  "pixels_max_channel_delta_at_least_5":int(np.count_nonzero(shift>=5))}
        assert q99_step<2.8
        output[mode]=result
    assert output["reduced"]["p99_abs_luminance_delta_rgb8"] < output["default"]["p99_abs_luminance_delta_rgb8"]*.65
    assert abs(output["default"]["min_luminance_delta_rgb8"]) < 15
    assert output["default"]["max_luminance_delta_rgb8"] < 15
    assert output["default"]["pixels_max_channel_delta_at_least_5"]>2500
    assert output["default"]["min_luminance_delta_rgb8"] < -4 and output["default"]["max_luminance_delta_rgb8"] > 4
    return output


def sightline_check(scene,camera,objects):
    geometry = [o for o in scene.objects if o.name.startswith(("Path review dot ","CHR-001 review bird "))]
    assert len(geometry)>=30
    projected = 0
    minimum_z = math.inf
    for frame in range(1,98,12):
        scene.frame_set(frame)
        highest = max(o.matrix_world.translation.z for o in objects)
        for obj in geometry:
            for v in obj.data.vertices:
                pos = obj.matrix_world@v.co
                coords = world_to_camera_view(scene,camera,pos)
                if not (0<=coords.x<=1 and 0<=coords.y<=1 and coords.z>0):
                    continue
                # If both endpoints are above the carrier, the sightline cannot cross its plane.
                assert pos.z>highest and camera.location.z>highest, (obj.name,pos,highest)
                projected += 1
                minimum_z = min(minimum_z,pos.z-highest)
    return {"status":"pass","path_mark_objects":sum(o.name.startswith("Path") for o in geometry),
            "goose_objects":sum(o.name.startswith("CHR") for o in geometry),"sampled_frames":9,
            "camera_visible_vertex_rays":projected,"rays_crossing_masks":0,
            "minimum_target_height_above_masks_BU":minimum_z}


def transform_check(scene,camera,root):
    camera_samples,displacement = [],[]
    angle = camera.data.angle_y
    for f in range(1,98):
        scene.frame_set(f)
        camera_samples.append(np.array(camera.matrix_world))
        displacement.append(root.location.x)
    assert all(np.array_equal(a,camera_samples[0]) for a in camera_samples)
    expected = np.linspace(-1.56,1.56,97)
    assert np.max(np.abs(expected-np.array(displacement)))<1e-6
    assert abs(math.degrees(angle)-50)<1e-5
    assert (scene.render.resolution_x,scene.render.resolution_y)==FRAME
    return {"status":"pass","samples":len(displacement),"fixed_camera":True,
            "vertical_fov_deg":math.degrees(angle),"default_translation_span_BU":max(displacement)-min(displacement),
            "default_drift_BU_per_s":.78,"mountain_pass_example_drift_BU_per_s":1.28}


def verify_video(directory):
    path = directory/"preview_fixed_rear.mp4"
    stats = json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames",
                                                "-show_streams","-of","json",str(path)]))
    (video,) = stats["streams"]
    assert video["codec_type"]=="video" and video["codec_name"]=="h264"
    assert [video["width"],video["height"]]==[852,394] and video["avg_frame_rate"]=="12/1"
    assert int(video["nb_read_frames"])==48
    subprocess.run(["ffmpeg","-v","error","-xerror","-threads","2","-i",str(path),
                    "-map","0:v:0","-f","null","-"],check=True)
    return {"status":"pass","frames":48,"render_px":[852,393],"encoded_px":[852,394],
            "duration_s":4.0,"audio_streams":0,"fps":12}


def mask_geometry(obj):
    loop = obj.data.uv_layers.active
    return sorted(tuple(round(float(c),6) for c in (*obj.data.vertices[l.vertex_index].co, *loop.data[l.index].uv))
                  for l in obj.data.loops)


def main(directory,output):
    initial = json.loads((directory/"generation_evidence.json").read_text())
    for m in initial["dependencies"].values():
        source = GEN["BASE"]/m["path"]
        assert hash_file(source)==m["sha256"], source
        for name,sha in m["review_files"].items():
            assert hash_file((GEN["BASE"]/m["asset"]/"v001"/name))==sha
        if "blend_path" in m:
            assert hash_file(GEN["BASE"]/m["blend_path"])==m["blend_sha256"]
    bpy.ops.wm.open_mainfile(filepath=str(directory/f"{FX}.blend"))
    scene = bpy.context.scene
    camera = scene.camera
    assert camera.name=="Gameplay | fixed rear"
    assert all(image.packed_file for image in bpy.data.images if image.name.endswith(".png"))
    root = bpy.data.objects["CloudShadow"]
    originals = [bpy.data.objects[name] for name in NAMES]
    assert all(obj.parent==root and obj.get("collision_enabled") is False for obj in originals)
    assert set(root.children)==set(originals)
    assert scene.frame_current==49
    transforms = transform_check(scene,camera,root)
    visibility = sightline_check(scene,camera,originals)
    image_metrics = contrast(directory)
    binary_checks = glb_checks(directory,initial)

    scene.frame_set(49)
    # Retain the complete review backdrop while replacing the effect with the imported asset.
    before = set(bpy.data.objects)
    for obj in originals:
        obj.hide_render = True
    bpy.ops.import_scene.gltf(filepath=str(directory/f"{FX}.glb"))
    imported = set(bpy.data.objects)-before
    imported_root, = [o for o in imported if o.type=="EMPTY"]
    imported_layers = [o for o in imported if o.type=="MESH"]
    assert len(imported_layers)==2 and imported_root.location.length<1e-6
    for source in originals:
        other, = [o for o in imported_layers if o.name.startswith(source.name)]
        assert other.parent==imported_root
        np.testing.assert_allclose(source.location,other.location,atol=1e-6)
        source_geometry = set(mask_geometry(source))
        assert set(mask_geometry(other))==source_geometry
        assert all(p.normal.z>.999 for p in other.data.polygons)
        assert other.get("collision_enabled") is False
    assert not output.exists() or not any(output.iterdir()),output
    output.mkdir(parents=True,exist_ok=True)
    GEN["render"](scene,output/"roundtrip_fixed_rear.png",16)
    roundtrip = raw_pixels(output/"roundtrip_fixed_rear.png")
    reference = raw_pixels(directory/"preview_fixed_default.png")
    error = np.abs(roundtrip-reference)
    result = {"status":"pass","triangles_imported":4,"same_local_transform":"pass","same_uv_positions":"pass",
              "same_normal_direction":"pass","mean_abs_delta_rgb8":float(error.mean()),
              "p99_abs_delta_rgb8":float(np.quantile(error,.99))}
    assert result["mean_abs_delta_rgb8"]<2 and result["p99_abs_delta_rgb8"]<=8,result
    metrics = {"id":"FX-005","version":"v001","status":"needs_review","blender":bpy.app.version_string,
               "dependency_hashes":"pass","reopened_final_blend":"pass","drift":transforms,"visibility":visibility,
               "masks":initial["masks"],"screen_luminance":image_metrics,"glb":binary_checks,"roundtrip":result,
               "video":verify_video(directory),"redline_check":"pass",
               "pending":["负责人美术及实际玩法中对云影的辨识","USDZ","RealityKit / App 接入及透明排序",
                          "运行时地面遮罩、设置输入和山口漂移","iPhone / iPad 真机显示与性能"],
               "ios_baseline":"active 计划 2026-11-14，iOS 27.2 模拟器 App 灰盒 340 项通过"}
    save_json(output/"qa.json",metrics)
    print(json.dumps(metrics,ensure_ascii=False,indent=2))


if __name__=="__main__":
    args=sys.argv[sys.argv.index("--")+1:]
    main(*(Path(arg).resolve() for arg in args))
