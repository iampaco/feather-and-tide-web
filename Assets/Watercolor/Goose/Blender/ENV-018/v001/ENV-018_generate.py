"""Make editable soft-edge atmosphere cards and audit fixed-camera gameplay targets."""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import runpy
import struct
import sys
import zlib

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np

HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
BASE = runpy.run_path(str(LIB/"ENV-001/v001/ENV-001_generate.py"))
MAT = LIB/"MAT-001/v001"
BANK = LIB/"ENV-007/v001/ENV-007_river_valley.blend"
PASS = LIB/"ENV-010/v001/ENV-010_short_pass.blend"
RIDGES = LIB/"ENV-009/v001/ENV-009_far_ridges.blend"
RIVER_WORK = runpy.run_path(str(LIB/"ENV-007/v001/ENV-007_generate.py"))
NAMES = ("MistLow","CloudPatch","CloudStreak")
STEM = "ENV-018_atmosphere_cards"
FRAME = (852,393)
ATLAS = 512
DRIFT_SECONDS = {"s3":12,"s4":12,"s2":4}
WIDTH_HEIGHT = dict(MistLow=(18.,1.45),CloudPatch=(13.5,3.85),CloudStreak=(20.,1.55))
ALPHA_CAP = dict(MistLow=.38,CloudPatch=.54,CloudStreak=.45)
check, obj, group, write = (BASE[k] for k in ("check","obj","collection","write_json"))
hash_file = BASE["file_hash"]
ROOT = HERE.parents[5]


def library(path, block, names):
    with bpy.data.libraries.load(str(path),link=False) as (source,target):
        check(set(names)<=set(getattr(source,block)),(path,names))
        setattr(target,block,list(names))
    return dict(zip(names,getattr(target,block)))


def rgba_png(path, pixels):
    def chunk(name,data):
        return struct.pack(">I",len(data))+name+data+struct.pack(">I",zlib.crc32(name+data))
    rows=b"".join(b"\0"+r.tobytes() for r in pixels[::-1])
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">2I5B",ATLAS,ATLAS,8,6,0,0,0))+
                     chunk(b"IDAT",zlib.compress(rows,9))+chunk(b"IEND",b""))


def rgba_physical_image(image):
    count=image.size[0]*image.size[1]*4
    values=np.empty(count,dtype=np.float32)
    image.pixels.foreach_get(values)
    return values.reshape(image.size[1],image.size[0],4)


def smooth_range(t):
    a=np.clip(t,0,1)
    return a*a*(3-2*a)


def matte(name, paper):
    """Asymmetric overlapping pigment forms; a zero border survives texture filtering."""
    u,v=np.meshgrid(np.linspace(0,1,ATLAS),np.linspace(0,1,ATLAS))
    lobes={
        "MistLow": ((.27,.46,.33,.22,.63),(.49,.37,.29,.31,.71),(.72,.56,.29,.29,.71),
                    (.54,.64,.46,.12,.49),(.79,.32,.22,.13,.47)),
        "CloudPatch": ((.31,.40,.25,.25,.74),(.46,.55,.22,.35,.98),(.65,.52,.27,.27,.96),
                       (.78,.39,.22,.24,.70),(.52,.29,.36,.19,.69),(.63,.72,.18,.19,.60)),
        "CloudStreak": ((.28,.39,.28,.25,.81),(.49,.45,.35,.31,.94),(.72,.57,.32,.22,.85),
                        (.44,.27,.36,.11,.60),(.72,.71,.27,.15,.54)),
    }
    sinus=.024*np.sin(u*21.4+v*6.6)+.012*np.sin(u*48.1-v*9.2)
    x=u+.021*np.sin(v*12.+u*8.)
    y=v+sinus
    if name=="CloudStreak": y=y-.19*(u-.5)
    complement=np.ones(u.shape)
    for cx,cy,rx,ry,amp in lobes[name]:
        radius=np.sqrt(((x-cx)/rx)**2+((y-cy)/ry)**2)
        cloud=amp*smooth_range((1.10-radius)/.97)
        complement*=1-cloud
    grain=(paper-.5)
    edge=smooth_range(np.minimum.reduce((u,v,1-u,1-v))/.13)
    opacity=ALPHA_CAP[name]*np.power(1-complement,1.19)*edge*(.94+.095*grain)
    opacity=np.clip(opacity,0,ALPHA_CAP[name])
    palette={"MistLow":((.69,.73,.735),(.94,.898,.788)),
             "CloudPatch":((.755,.795,.826),(.985,.950,.863)),
             "CloudStreak":((.585,.675,.772),(.848,.90,.952))}
    bottom,top=(np.array(c) for c in palette[name])
    tint=smooth_range(.12+.63*v+.26*(1-complement)+.10*np.sin(u*7.8))
    rgb=bottom+(top-bottom)*tint[:,:,None]+grain[:,:,None]*.040
    return np.rint(np.dstack((rgb,opacity))*255).clip(0,255).astype(np.uint8)


def colored(folder):
    path=MAT/"MAT-001_watercolor_master.blend"
    template=library(path,"materials",["DryGround"])["DryGround"]
    reading=json.loads((MAT/"asset_manifest.json").read_text())
    source_rel=reading["textures"]["DryGround"]["path"]
    source_png=MAT/source_rel
    check(hash_file(source_png)==reading["files"][source_rel],source_png)
    node=next(n for n in template.node_tree.nodes if n.type=="TEX_IMAGE")
    check(hash_file(source_png)==sha256(node.image.packed_file.data).hexdigest(),node.image)
    paper=rgba_physical_image(node.image)[...,:3].mean(axis=2)
    # Isolate paper variation from the warm source wash before applying new cloud colors.
    normalized=(paper-np.quantile(paper,.04))/max(.01,np.quantile(paper,.96)-np.quantile(paper,.04))
    mapped={}
    mats={}
    samples={}
    folder_tex=folder/"textures"
    folder_tex.mkdir()
    for name in NAMES:
        rgba=matte(name,normalized.clip(0,1))
        filename=f"ft_shared_atmosphere_{name.lower()}_basecolor_alpha.png"
        path=folder_tex/filename
        rgba_png(path,rgba)
        image=bpy.data.images.load(str(path),check_existing=False)
        image.pack()
        image.filepath=f"//textures/{filename}"
        image.alpha_mode="STRAIGHT"
        mat=template.copy()
        mat.name=name+"_RGBA"
        mat.use_backface_culling=False
        mat.surface_render_method="BLENDED"
        nodes=mat.node_tree.nodes
        tex=next(n for n in nodes if n.type=="TEX_IMAGE")
        tex.image,tex.extension=image,"EXTEND"
        shader=next(n for n in nodes if n.type=="BSDF_PRINCIPLED")
        shader.inputs["Metallic"].default_value=0
        shader.inputs["Roughness"].default_value=1
        shader.inputs["Specular IOR Level"].default_value=0
        mat.node_tree.links.new(tex.outputs["Color"],shader.inputs["Base Color"])
        mat.node_tree.links.new(tex.outputs["Alpha"],shader.inputs["Alpha"])
        a=rgba[...,3]
        border=np.concatenate((a[0],a[-1],a[:,0],a[:,-1]))
        check(not np.any(border) and a.max()>46 and a.max()<=math.ceil(ALPHA_CAP[name]*255),name)
        mapped[name]={"file":f"textures/{filename}","sha256":hash_file(path),"image_size_px":[ATLAS,ATLAS],
                      "alpha_rgb8_min_max":[int(a.min()),int(a.max())],"border_alpha_rgb8_max":int(border.max()),
                      "partial_alpha_pixels":int(np.count_nonzero((a>0)&(a<a.max()))),
                      "source_paper_png":source_rel,"source_paper_sha256":hash_file(source_png)}
        mats[name]=mat
        samples[name]=a.astype(np.float32)/255.
    return mats,mapped,samples


def mesh_card(parent,name,mat):
    w,h=WIDTH_HEIGHT[name]
    points=[(w*(i/4-.5),0.,h*(j/2-.5)) for j in range(3) for i in range(5)]
    faces=[]
    for j in range(2):
        for i in range(4):
            a=j*5+i
            faces.extend(((a,a+1,a+6),(a,a+6,a+5)))
    item=BASE["simple_mesh"](parent,name,points,faces,mat)
    uv=item.data.uv_layers.new(name="AtmosphereUV")
    for loop in item.data.loops:
        x,_,z=points[loop.vertex_index]
        uv.data[loop.index].uv=(x/w+.5,z/h+.5)
    item["role"]="atmosphere_render_only"
    item["collision_enabled"]=False
    item["alpha_strength_default"]=1.
    item["accessibility_alpha_strength_reduced"]=.35
    item["accessibility_alpha_strength_off"]=0.
    item.asset_mark()
    return item


def stage_cards(parent, sources, place):
    rows=[]
    for variant,x,y,z,scx,scz,drift in place:
        item=obj(parent,variant+" | "+str(len(rows)+1),sources[variant].data,(x,y,z))
        item.scale=(scx,1,scz)
        rows.append((variant,item,Vector((x,y,z)),drift))
    return rows


def position_cards(rows,phase,mode=1):
    for i,(_,item,pos,drift) in enumerate(rows):
        item.location=pos+Vector((math.sin(phase*math.tau+i*.57)*drift*mode,0,0))


def accessibility(rows, amount):
    for _,item,_,_ in rows:
        slot=item.material_slots[0]
        slot.link="OBJECT"
        if amount==0:
            item.hide_render=True
            continue
        item.hide_render=False
        core=item.data.materials[0]
        if amount==1:
            slot.material=core
            continue
        material=core.copy()
        material.name=core.name+" | reduced opacity review"
        nodes=material.node_tree.nodes
        shader=next(n for n in nodes if n.type=="BSDF_PRINCIPLED")
        tex=next(n for n in nodes if n.type=="TEX_IMAGE")
        gain=nodes.new("ShaderNodeMath")
        gain.operation="MULTIPLY"
        gain.inputs[1].default_value=amount
        material.node_tree.links.new(tex.outputs["Alpha"],gain.inputs[0])
        material.node_tree.links.new(gain.outputs[0],shader.inputs["Alpha"])
        slot.material=material


def sample_mask(alpha,u,v):
    if not 0<=u<=1 or not 0<=v<=1:return 0.
    x,y=[max(0,min(ATLAS-1,t*ATLAS-.5)) for t in (u,v)]
    ix,iy=int(x),int(y)
    jx,jy=min(ix+1,ATLAS-1),min(iy+1,ATLAS-1)
    dx,dy=x-ix,y-iy
    return float((1-dy)*((1-dx)*alpha[iy,ix]+dx*alpha[iy,jx])+dy*((1-dx)*alpha[jy,ix]+dx*alpha[jy,jx]))


def blocked_alpha(camera,point,rows,alpha,amount):
    transmittance=1.
    direction=point-camera.location
    if abs(direction.y)<1e-8:return 0.
    for variant,item,_,_ in rows:
        t=(item.location.y-camera.location.y)/direction.y
        if not 0.<t<1.:continue
        v=camera.location+t*direction-item.location
        w,h=WIDTH_HEIGHT[variant]
        u,vertical=v.x/(w*item.scale.x)+.5,v.z/(h*item.scale.z)+.5
        transmittance*=1-sample_mask(alpha[variant],u,vertical)*amount
    return 1-transmittance


def visibility(scene,cam,rows,alpha,positions,targets):
    scene.render.resolution_x,scene.render.resolution_y=FRAME
    details={}
    for value in (1.,.35,0.):
        all_alpha=[]
        outside=0
        for x,y,a in positions:
            BASE["follow"](cam,(x,y),Vector((a,1.)).normalized())
            bpy.context.view_layer.update()
            for phase in (0.,.125,.25,.375,.5,.625,.75,.875):
                position_cards(rows,phase,value)
                for p in targets:
                    output=world_to_camera_view(scene,cam,p)
                    if not (output.z>0 and 0.<output.x<1. and 0.<output.y<1.):
                        outside+=1
                        continue
                    all_alpha.append(blocked_alpha(cam,p,rows,alpha,value))
        check(not outside and len(all_alpha)==len(positions)*8*len(targets),(outside,len(all_alpha)))
        details[str(value)]={"lines_tested":len(all_alpha),"max_combined_alpha":max(all_alpha),
                            "max_attenuation_limit":.075 if value==1 else .028 if value else 0}
        check(max(all_alpha)<=details[str(value)]["max_attenuation_limit"],(value,max(all_alpha)))
    heights=[v.z for v in targets]
    return {"settings":details,"camera_poses":positions, "target_count":len(targets),
            "target_height_BU":[min(heights),max(heights)],"drift_sample_count":8}


def verify_alpha_composite(item, masks):
    """Check that the unobstructed-corridor QA can detect overlapping matte coverage."""
    variant=item.name
    y,x=np.unravel_index(np.argmax(masks[variant]),masks[variant].shape)
    w,h=WIDTH_HEIGHT[variant]
    zz=h*((y+.5)/ATLAS-.5)
    xx=w*((x+.5)/ATLAS-.5)
    camera=type("AlphaProbe",(),{"location":Vector((xx,-2,zz))})()
    mark=Vector((xx,2,zz))
    rows=[(variant,item,item.location,0.)]*2
    a=float(masks[variant][y,x])
    received={}
    for power in (1.,.35,0.):
        result=blocked_alpha(camera,mark,rows,masks,power)
        check(abs(result-(1-(1-a*power)**2))<1e-6,(power,result,a))
        received[str(power)]=result
    return received


def river_stage(scene, gray, assets):
    root=group("OpenBank S3 context (review only)",scene.collection)
    names=[f"{a}_{b}" for a in ("Straight","Bend","OpenBank") for b in ("Bed","Water")]
    terrain=library(BANK,"objects",names)
    modules={a:(terrain[a+"_Bed"],terrain[a+"_Water"]) for a in ("Straight","Bend","OpenBank")}
    flat=library(LIB/"ENV-001/v001/ENV-001_terrain.blend","objects",["Flat"])["Flat"]
    if gray:
        make_gray([*terrain.values(),flat])
    for item in terrain.values():
        # Append data as editable copies while keeping the reference objects out of the render.
        root.objects.link(item)
        item.hide_render=True
        item.hide_set(True)
    _,beds=RIVER_WORK["scene_geometry"](scene,modules,flat,gray,extended=True)
    lead=BASE["add_goose"](root)
    rescue,rescue_data=RIVER_WORK["support_bird"](root,modules["OpenBank"][0],show_color=not gray)
    bpy.context.view_layer.update()
    targets=[rescue.matrix_world@Vector((x,y,z)) for x,y,z in ((0,0,.13),(-.09,-.05,.15),
        (.09,-.05,.15),(0,.25,.23),(0,.37,.27),(-.17,-.10,.08),(.17,-.10,.08))]
    targets += [Vector((x,y,.03)) for x in (2.,3.16,4.38) for y in (7.65,10.,12.35)]
    cameras=group("View-specific items",scene.collection)
    rows=stage_cards(cameras,assets,(
        ("MistLow",-8.0,8.9,.61,.83,.66,.59),("MistLow",13.5,12.5,.70,.93,1.0,.64),
        ("CloudPatch",-9.0,32.6,1.7,1.81,.78,.72),
        ("CloudStreak",14.5,37,1.35,1.26,1.0,.89)))
    poses=((3.40,.5,.030),(3.42,3.6,.019),(3.86,5.7,-.075))
    return root,lead,rows,poses,targets


def make_gray(items):
    inks={}
    for item in items:
        for index,mat in enumerate(item.data.materials):
            label=mat.name.split(".")[0]
            if label not in inks:
                inks[label]=BASE["paint"]("Graybox context | "+label,"8AA4A6" if "Water" in label else "A3AD9F")
            item.data.materials[index]=inks[label]


def scaffold(root,flat):
    for j in range(-3,12):
        for i in range(-6,7):
            obj(root,f"Plain land {i},{j}",flat.data,(i*10,j*10,0.))


def prop_box(root,name,center,size,material):
    x,y,z=center
    a,b,c=[n/2 for n in size]
    corners=[(x+s*a,y+t*b,z+u*c) for u in (-1,1) for s,t in ((-1,-1),(1,-1),(1,1),(-1,1))]
    faces=((3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
    return BASE["simple_mesh"](root,name,corners,faces,material)


def turbine_stage(scene,gray,assets):
    root=group("S4 | Swift turbine outline and sweep reference",scene.collection)
    flat=library(LIB/"ENV-001/v001/ENV-001_terrain.blend","objects",["Flat"])["Flat"]
    if gray:make_gray([flat])
    scaffold(root,flat)
    neutral=BASE["paint"]("Runtime reference | warm metal","73726B")
    blade=BASE["paint"]("Runtime reference | cool blade","7A8387")
    ink=BASE["paint"]("Runtime reference | muted warm lamp","CBB881",emission=True)
    s=BASE["SCALE"]
    swift=(ROOT/"Sources/FeatherTide/Data/GrayboxPlaces.swift").read_text()
    radius=float(re.search(r"windSweepRadius: CGFloat = (\d+)",swift).group(1))/s
    swift_view=(ROOT/"Sources/FeatherTide/Rendering/PlayfieldView.swift").read_text()
    for prototype in ("width: 16, height: 70, depth: 16","width: 86, height: 3, depth: 8",
                      "width: 8, height: 3, depth: 86","height: 68, enabled: showTraces"):
        check(prototype in swift_view,prototype)
    # Use the current code's shape and relative vertical dimensions at an authored camera test location.
    x,y=1.75,14.5
    prop_box(root,"Tower | code proxy",(x,y,35/s),(16/s,16/s,70/s),neutral)
    prop_box(root,"Rotor cross | code proxy",(x,y,68/s),(86/s,8/s,3/s),blade)
    prop_box(root,"Rotor length | code proxy",(x,y,68/s),(8/s,86/s,3/s),blade)
    prop_box(root,"Hub lamp | review scale",(x,y,74/s),(6/s,6/s,5/s),ink)
    cord=BASE["paint"]("Sweep perimeter | review only","948D7D")
    vertices,faces=[],[]
    for i in range(88):
        a=i*math.tau/88
        d=math.tau/88*.74
        idx=len(vertices)
        vertices.extend((x+r*math.cos(t),y+r*math.sin(t),.021)
                        for r,t in ((radius-.035,a),(radius+.035,a),(radius+.035,a+d),(radius-.035,a+d)))
        faces.append((idx,idx+1,idx+2,idx+3))
    BASE["simple_mesh"](root,"Measured outline | review mark",vertices,faces,cord)
    target=[Vector((x+dx/s,y+dy/s,h/s)) for dx,dy,h in ((0,0,74),(0,0,64),
        (-43,0,68),(43,0,68),(0,-43,68),(0,43,68),(0,0,7),(7,0,35),(-7,0,35))]
    target += [Vector((x+radius*math.cos(i*math.tau/16),y+radius*math.sin(i*math.tau/16),.029))
               for i in range(16)]
    lead=BASE["add_goose"](root)
    rows=stage_cards(root,assets,(
        ("MistLow",-9.8,10.8,.71,.88,1.,.68),("MistLow",13.4,16,.74,.79,1.04,.73),
        ("CloudPatch",-14.8,26,1.01,2.18,.53,.74),("CloudStreak",10.2,31,1.23,1.35,.72,.85)))
    poses=((0.,.0,.055),(.43,1.80,.02),(.82,3.4,.0))
    return root,lead,rows,poses,target


def pass_stage(scene,gray,assets):
    root=group("S2 gorge and distant silhouettes",scene.collection)
    terrain=library(PASS,"objects",["Pass_Left","Pass_Right","Mouth","Flat"])
    if gray:make_gray(terrain.values())
    for key in ("Pass_Left","Pass_Right","Mouth"):
        obj(root,key+" | review",terrain[key].data)
    for i in range(-5,5):
        for j in range(-1,11):
            if i in (0,1) and 1<=j<=4:continue
            obj(root,f"Gorge outskirts {i},{j}",terrain["Flat"].data,(-16.5+10*i,5+10*j,0))
    ridges=library(RIDGES,"objects",["FarRidge_A","FarRidge_B"])
    if gray:make_gray(ridges.values())
    for item,p in zip(ridges.values(),((-24,62,-.3),(8,85,-.25))):obj(root,item.name+" | sky depth",item.data,p)
    leader=BASE["add_goose"](root)
    rows=stage_cards(root,assets,(
        ("CloudStreak",-18.6,26,2.6,.82,.75,2.0),("CloudStreak",-5.8,34,3.0,.82,.82,1.65),
        ("CloudStreak",-15.3,44,1.6,1.20,.62,2.3),("MistLow",.9,28,1.2,.69,.74,.48),
        ("CloudPatch",-10.,58,1.50,1.66,.66,.85)))
    return root,leader,rows,((-6.6,9.,-.27),(-10.7,21.,.035),(-10.82,31.,.035)),[]


def stage_rear(scene, role, assets, output, alpha=None):
    gray=alpha is None
    fn={"s3":river_stage,"s4":turbine_stage,"s2":pass_stage}[role]
    root,lead,cards,poses,targets=fn(scene,gray,assets)
    studio=BASE["studio"](scene,scene.collection)
    world=scene.world.node_tree.nodes.get("Background")
    world.inputs["Color"].default_value=(.53,.65,.735,1)
    world.inputs["Strength"].default_value=.72
    sun=next(item for item in studio.objects if item.type=="LIGHT")
    sun.data.energy=1.80
    sun.data.color=(1.,.93,.85) if role=="s4" else (.91,.95,1.) if role=="s2" else (1.,.98,.94)
    cam=BASE["camera"](studio,"Fixed rear | "+role,(0,0,1),(0,1,0))
    scene.camera=cam
    verification=visibility(scene,cam,cards,alpha,poses,targets) if targets and not gray else None
    x,y,facing=poses[1] if role=="s3" else poses[0]
    BASE["pose_at"](cam,lead,(x,y),Vector((facing,1.)).normalized())
    position_cards(cards,.13)
    if gray:
        BASE["render"](scene,cam,output,"graybox_"+role,FRAME,13)
    else:
        for label,opacity in (("default",1.),("reduced",.35),("off",0.)) if targets else (("default",1.),):
            accessibility(cards,opacity)
            position_cards(cards,.13,opacity)
            BASE["render"](scene,cam,output,"preview_"+role+"_"+label,FRAME,22)
        accessibility(cards,1.)
        fps=24
        loop=DRIFT_SECONDS[role]*fps
        scene.render.fps=fps
        scene.frame_end=loop
        for n in range(0,loop+1,4):
            position_cards(cards,n/loop)
            for _,item,_,_ in cards:
                item.keyframe_insert(data_path="location",index=0,frame=n+1)
        scene.frame_set(round(.13*loop)+1)
    BASE["set_preview_workspace"](scene,cam)
    scene.render.filepath="//review.png"
    return verification


def motion_preview(folder, variant, delivery):
    bpy.ops.wm.open_mainfile(filepath=str(delivery/f"{STEM}.blend"))
    scene=bpy.data.scenes[f"ENV-018 | {variant.upper()} fixed camera"]
    bpy.context.window.scene=scene
    start=round(.13*scene.frame_end)+1
    for step in range(24):
        scene.frame_set(start+step*2)
        BASE["render"](scene,scene.camera,folder,f"motion_{step:03d}",FRAME,10)


def verify_saved_drift():
    results={}
    for role,seconds in DRIFT_SECONDS.items():
        scene=bpy.data.scenes[f"ENV-018 | {role.upper()} fixed camera"]
        bpy.context.window.scene=scene
        check(scene.frame_end==seconds*scene.render.fps,role)
        cards=[item for item in scene.objects if item.animation_data and item.animation_data.action
               and item.data.name in NAMES]
        check(len(cards)>=4,(role,[item.name for item in cards]))
        offsets=[]
        cameras=[]
        start=round(.13*scene.frame_end)+1
        for frame in (start,start+46):
            scene.frame_set(frame)
            offsets.append([tuple(item.location) for item in cards])
            cameras.append(scene.camera.matrix_world.copy())
        displacement=[abs(a[0]-b[0]) for a,b in zip(*offsets)]
        check(cameras[0]==cameras[1] and max(displacement)>.1, (role,displacement))
        check(all(a[1:]==b[1:] for a,b in zip(*offsets)),role)
        results[role]={"period_seconds":seconds,"keys_previewed":len(cards),
                       "max_x_displacement_BU":max(displacement),"camera_fixed":True}
    return results


def lineup(scene,assets,output,title):
    root=group("Turned card comparison",scene.collection)
    dark=BASE["paint"]("Comparison blue-grey wash","536D79",emission=True)
    card_fn=BASE["camera"]
    backdrop=[(-19,2,-7),(19,2,-7),(19,2,7),(-19,2,7)]
    BASE["simple_mesh"](root,"Comparison backdrop",backdrop,[(0,1,2,3)],dark)
    for i,name in enumerate(NAMES):
        original=assets[name]
        item=obj(root,name+" | detail",original.data,(0,0,3.5-i*3.55))
        item.scale=(1,1,.75)
    studio=BASE["studio"](scene,scene.collection)
    cam=card_fn(studio,"Flat atlas detail",(0,-20,0),(0,0,0),24)
    BASE["render"](scene,cam,output,title,(1120,650),20)
    scene.render.filepath="//lineup.png"
    BASE["set_preview_workspace"](scene,cam)


def export(output,items):
    for name,item in items.items():
        bpy.ops.object.select_all(action="DESELECT")
        item.select_set(True)
        bpy.context.view_layer.objects.active=item
        r=bpy.ops.export_scene.gltf(filepath=str(output/f"ENV-018_{name}.glb"),export_format="GLB",
                      use_selection=True,export_yup=True,export_animations=False,export_extras=True)
        check(r=={"FINISHED"},name)


def signature(obj):
    data=obj.data
    uvs=data.uv_layers.active.data
    signatures={}
    for tri in data.polygons:
        check(len(tri.vertices)==3,tri)
        raw=[]
        for loop in tri.loop_indices:
            p=data.vertices[data.loops[loop].vertex_index].co
            raw.append((tuple(round(v,6) for v in p),tuple(round(t,6) for t in uvs[loop].uv),
                        data.corner_normals[loop].vector.copy()))
        start=min(range(3),key=lambda i:raw[i][:2])
        ordered=raw[start:]+raw[:start]
        signatures[tuple(r[:2] for r in ordered)]=[r[-1] for r in ordered]
    return signatures


def readback(output,items,mapping):
    imported,qa={},{}
    for name,item in items.items():
        path=output/f"ENV-018_{name}.glb"
        doc,blob=BASE["glb_chunks"](path)
        node,=doc["nodes"]
        check(node["name"]==name and node.get("translation",[0]*3)==[0]*3 and
              node.get("rotation",[0,0,0,1])==[0,0,0,1] and node.get("scale",[1]*3)==[1]*3,name)
        fields=node["extras"]
        check(fields["collision_enabled"] is False and fields["accessibility_alpha_strength_off"]==0 and
              fields["accessibility_alpha_strength_reduced"]==.35 and fields["alpha_strength_default"]==1.,fields)
        mat,=doc["materials"]
        check(mat["name"]==name+"_RGBA" and mat["alphaMode"]=="BLEND" and mat.get("doubleSided") is True,mat)
        tex=doc["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
        image=doc["images"][tex["source"]]
        sampler=doc["samplers"][tex["sampler"]]
        check(sampler["wrapS"]==sampler["wrapT"]==33071,(name,sampler))
        view=doc["bufferViews"][image["bufferView"]]
        start=view.get("byteOffset",0)
        checksum=sha256(blob[start:start+view["byteLength"]]).hexdigest()
        check(checksum==mapping[name]["sha256"],(name,checksum,mapping[name]))
        primitive,=doc["meshes"][0]["primitives"]
        accessor=doc["accessors"][primitive["attributes"]["POSITION"]]
        w,h=WIDTH_HEIGHT[name]
        check(max(abs(a-b) for a,b in zip(accessor["min"]+accessor["max"],[-w/2,-h/2,0,w/2,h/2,0]))<1e-6,name)
        old=set(bpy.data.objects)
        check(bpy.ops.import_scene.gltf(filepath=str(path),merge_vertices=False,import_pack_images=True)=={"FINISHED"},name)
        clone,=set(bpy.data.objects)-old
        a,b=signature(item),signature(clone)
        check(a.keys()==b.keys() and len(a)==16 and clone.location.length==0 and tuple(clone.scale)==(1,1,1),name)
        normal=max(BASE["angle"](x,y) for k in a for x,y in zip(a[k],b[k]))
        check(normal<.001,(name,normal))
        qa[name]={"triangles":16,"source_vertices":len(item.data.vertices),"bounds_glTF":[accessor["min"],accessor["max"]],
                  "max_corner_normal_delta_degrees":normal,"embedded_png_sha256":checksum,
                  "alpha_mode":"BLEND","wrap":"CLAMP_TO_EDGE"}
        imported[name]=clone
    return imported,qa


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--gray-only",action="store_true")
    parser.add_argument("--motion",choices=tuple(DRIFT_SECONDS))
    parser.add_argument("--delivery",type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    check(not any(out.iterdir()),"Use an empty temporary output directory.")
    if args.motion:
        check(args.delivery is not None,"Pass the delivered asset directory with --delivery.")
        motion_preview(out,args.motion,args.delivery.resolve())
        return
    if args.verify:
        d=args.verify.resolve()
        bpy.ops.wm.open_mainfile(filepath=str(d/f"{STEM}.blend"))
        mapping=json.loads((d/"asset_manifest.json").read_text())["textures"]
        want=json.loads((d/"qa.json").read_text())["roundtrip"]
        originals={name:bpy.data.objects[name] for name in NAMES}
        drift=verify_saved_drift()
        BASE["fresh_scene"]("Independent delivered GLBs")
        _, got=readback(d,originals,mapping)
        check(want==got,"Readback differs")
        write(out/"recheck.json",{"result":"pass","roundtrip":got,"drift":drift})
        return

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    scene=bpy.context.scene
    scene.name="ENV-018 | Editable atmospheric cards"
    library_group=group("Three atmosphere cards at origin",scene.collection)
    grey=BASE["paint"]("Graybox card bounds","9DA8AA")
    data={name:mesh_card(library_group,name,grey) for name in NAMES}
    grey_scenes=[]
    for role in ("s3","s4","s2"):
        stage=BASE["fresh_scene"]("Graybox | "+role)
        stage_rear(stage,role,data,out)
        grey_scenes.append(stage)
    if args.gray_only:return
    bpy.context.window.scene=scene
    for s in grey_scenes:bpy.data.scenes.remove(s)
    mats,mapping,alpha=colored(out)
    for name,item in data.items():item.data.materials[0]=mats[name]
    positive_control=verify_alpha_composite(data["CloudPatch"],alpha)
    export(out,data)
    shelf=BASE["fresh_scene"]("ENV-018 | Cloud atlas appearance")
    lineup(shelf,data,out,"preview_lineup")
    proof, scenes={},[]
    for role in ("s3","s4","s2"):
        stage=BASE["fresh_scene"]("ENV-018 | "+role.upper()+" fixed camera")
        report=stage_rear(stage,role,data,out,alpha)
        if report:proof[role]=report
        scenes.append(stage)
    bpy.context.window.scene=scenes[0]
    bpy.ops.wm.save_as_mainfile(filepath=str(out/f"{STEM}.blend"))
    last=BASE["fresh_scene"]("ENV-018 | Imported atlas appearance")
    imported,qa=readback(out,data,mapping)
    for item in imported.values():item.hide_render=True
    lineup(last,imported,out,"preview_glb_roundtrip")
    write(out/"qa.json",{"id":"ENV-018","status":"needs_review","version":"v001","version_blender":bpy.app.version_string,
          "roundtrip":qa,"visibility":proof,"visibility_alpha_positive_control":positive_control,
          "visibility_method":"Sample UV alpha bilinearly for each target ray, composite transmittance of all foreground cards.",
          "pending":["Real STR-002 array, runtime sorting and visibility, accessibility option, FX-004, actual devices."]})
    write(out/"asset_manifest.json",{"id":"ENV-018","status":"needs_review","version":"v001","execution_order_1_based":28,
            "depends":["MAT-001/v001"], "review_only_sources":{"ENV-007":hash_file(BANK),"ENV-010":hash_file(PASS),
              "ENV-009":hash_file(RIDGES),"MAT-001":hash_file(MAT/"MAT-001_watercolor_master.blend")},
            "variants":{name:{"width_height_BU":WIDTH_HEIGHT[name],"file":f"ENV-018_{name}.glb"} for name in NAMES},
            "blend":f"{STEM}.blend","pivot_BU":[0,0,0],"geometry_blender_plane":"XZ, front normal -Y",
            "gltf_coord":"(x,z,-y)","alpha_controls_review":{"default":1.,"reduce":.35,"hide":0.},
            "drift_seconds_review":DRIFT_SECONDS,
            "textures":mapping,"role":"Render-only cards; no physics shapes.",
            "rights":"Original procedural alpha and color design using project-owned MAT-001 paper grain."})


if __name__=="__main__":
    main()
