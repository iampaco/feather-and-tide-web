"""Model the ENV-011 rock set, render Blender evidence, and verify each GLB."""
from argparse import ArgumentParser
from collections import defaultdict
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path
import runpy
import struct
import sys
import zlib

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import numpy as np


HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
ENV1 = LIB / "ENV-001/v001"
MAT3 = LIB / "MAT-003/v001"
STEM = "ENV-011_rock_sets"
NAMES = ("Rock_Round", "Rock_Long", "PebbleCluster")
ATLAS = "textures/ft_goose_env_rock_sets_basecolor.png"
BASE = runpy.run_path(str(ENV1 / "ENV-001_generate.py"))
check, obj, group, paint = (BASE[k] for k in ("check", "obj", "collection", "paint"))
digest, write = (BASE[k] for k in ("file_hash", "write_json"))
SOURCE_SIZE = BASE["GAME_SIZE"]
SUPPORT_EPS = 1e-6
PHI = math.tau
ATLAS_SIZE = 512
ROCKS = {
    # center xy, ellipse radii, height, angle, phase, plan vertices
    "Rock_Round": [((0., 0.), (.94, .78), .83, .26, .67, 12)],
    "Rock_Long": [((0., 0.), (.62, 1.47), .54, -.24, 2.13, 12)],
    "PebbleCluster": [
        ((-.46, -.41), (.37, .32), .32, .29, .35, 8),
        ((.42, -.34), (.28, .24), .23, -.37, 2.7, 8),
        ((-.14, .33), (.30, .27), .28, .41, 5.03, 8),
        ((.55, .36), (.24, .20), .20, -.53, 1.65, 8),
        ((-.74, .30), (.20, .16), .16, .55, 4.72, 8),
    ],
}
FRAME_POSES = {
    "fixed_rear": ((0, 0), (0, 1)),
    "fixed_rear_approach": ((.25, 1.7), (.11, .9939316)),
}


class RockMesh:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.corner_coords = []

    def triangle(self, ids, uvs, surface):
        self.faces.append(tuple(ids))
        self.corner_coords.append((tuple(uvs), surface))

    def stone(self, center, radii, height, angle, phase, steps):
        offset = len(self.vertices)
        ridge = radii[1] > 1
        # Follow the broad natural rolls from the bevel up to a squashed shoulder.
        rings = ((.0, .69), (.16, .96), (.39, 1), (.69, .85), (.89, .58))
        c, s = math.cos(angle), math.sin(angle)

        for row, (z, radius) in enumerate(rings):
            for col in range(steps):
                theta = PHI * col / steps + .08 * math.sin(1.9 * col + phase + row / 7)
                shape = 1 + .105 * math.cos(3 * theta + phase) + .062 * math.sin(2 * theta + 1.3 * phase)
                drift_x = (.14 if ridge else -.13) * radii[0] * z
                drift_y = (-.17 if ridge else .12) * radii[1] * z
                vx = radii[0] * radius * shape * math.cos(theta) + drift_x
                vy = radii[1] * radius * shape * math.sin(theta) + drift_y
                h = .0 if row == 0 else height * z * (1 + .115 * math.sin(theta + phase)
                                                       + .032 * math.cos(3 * theta - .7 * phase))
                self.vertices.append((center[0] + c*vx-s*vy, center[1] + s*vx+c*vy, h))
        peak = len(self.vertices)
        self.vertices.append((center[0] - .08*radii[0], center[1] + .06*radii[1], height))
        bottom = len(self.vertices)
        self.vertices.append((*center, 0.))

        def idx(row, col):
            return offset + row * steps + col % steps

        def uv(row, col):
            return (col / steps + phase / PHI, .08 + rings[row][0] * .77)

        for row in range(len(rings)-1):
            for col in range(steps):
                p, q = (col, col + 1)
                a, b, c, d = idx(row, p), idx(row, q), idx(row+1, q), idx(row+1, p)
                A, B, C, D = uv(row, p), uv(row, q), uv(row+1, q), uv(row+1, p)
                if (col + row) % 2 == 0:
                    self.triangle((a, b, c), (A, B, C), "body")
                    self.triangle((a, c, d), (A, C, D), "body")
                else:
                    self.triangle((a, b, d), (A, B, D), "body")
                    self.triangle((b, c, d), (B, C, D), "body")
        last = len(rings)-1
        for col in range(steps):
            following = col+1
            midpoint = (col+.5)/steps + phase/PHI
            self.triangle((idx(last,col), idx(last,following), peak),
                          (uv(last,col),uv(last,following),(midpoint,.875)),"body")
            self.triangle((idx(0,following),idx(0,col),bottom),
                          (uv(0,following),uv(0,col),(midpoint,.018)),"base")

    def build(self, parent, name, mat):
        mesh = bpy.data.meshes.new(name + " mesh")
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        mesh.materials.append(mat)
        uv = mesh.uv_layers.new(name="RockAtlas")
        for polygon, (coords, surface) in zip(mesh.polygons, self.corner_coords, strict=True):
            polygon.use_smooth = surface == "body"
            for k, value in zip(polygon.loop_indices, coords, strict=True):
                uv.data[k].uv = value
        rock = obj(parent, name, mesh)
        rock["asset_id"] = "ENV-011"
        rock["role"] = "decoration"
        rock["generate_hard_collision"] = False
        rock.asset_mark()
        rock.asset_data.description = "ENV-011/v001 | ground pivot at local Z=0 | static decoration"
        return rock


def solid_components(mesh):
    adj = defaultdict(set)
    uses = defaultdict(list)
    for poly in mesh.polygons:
        ids = list(poly.vertices)
        check(len(ids)==3 and poly.area>1e-8, (mesh.name, poly.index, poly.area))
        for a,b in zip(ids, ids[1:]+ids[:1]):
            adj[a].add(b)
            adj[b].add(a)
            uses[tuple(sorted((a,b)))].append(a<b)
    check(all(sorted(dirs)==[False,True] for dirs in uses.values()), (mesh.name,"manifold winding"))
    todo = set(adj)
    components = []
    while todo:
        component = set()
        fringe = [todo.pop()]
        while fringe:
            n = fringe.pop()
            component.add(n)
            unseen = adj[n] & todo
            todo -= unseen
            fringe.extend(unseen)
        components.append(component)
    return components


def validate_rock(item, name):
    mesh = item.data
    vertices = [v.co for v in mesh.vertices]
    extents = [[float(min(v[i] for v in vertices)), float(max(v[i] for v in vertices))] for i in range(3)]
    check(extents[2][0]==0. and extents[2][1] > .1, (name,extents))
    check(all(pair[0] < 0 < pair[1] for pair in extents[:2]), (name,extents))
    check(item.location.length < SUPPORT_EPS and item.rotation_euler.to_quaternion().angle < SUPPORT_EPS and
          tuple(item.scale) == (1,1,1), name)
    components = solid_components(mesh)
    check(len(components)==len(ROCKS[name]), (name,len(components)))
    counts, areas, volumes = [], [], []
    comps_xy = []
    for comp in components:
        support = {i for i in comp if abs(vertices[i].z) < SUPPORT_EPS}
        counts.append(len(support))
        faces = [p for p in mesh.polygons if p.vertices[0] in comp]
        foot = [p for p in faces if all(i in support for i in p.vertices)]
        check(len(support)>=7 and len(foot)>=6 and all(p.normal.z<-.99999 for p in foot), (name,counts))
        area = sum(p.area for p in foot)
        volume = sum(vertices[a].dot(vertices[b].cross(vertices[c]))/6 for a,b,c in [p.vertices for p in faces])
        check(area>.025 and volume>.008,(name,area,volume))
        areas.append(area)
        volumes.append(volume)
        comps_xy.append([[min(vertices[i][a] for i in comp),max(vertices[i][a] for i in comp)] for a in (0,1)])
    # A positive separation on one axis proves the disconnected stones never cross.
    distances=[]
    for a,b in combinations(comps_xy,2):
        gap=max(max(p[0]-q[1],q[0]-p[1]) for p,q in zip(a,b,strict=True))
        check(gap>.01,(name,gap,a,b))
        distances.append(gap)
    return {"triangles":len(mesh.polygons),"vertices":len(mesh.vertices),"bounds_BU":extents,
            "size_BU":[b-a for a,b in extents],"stones":len(components),
            "support_z_BU":extents[2][0],"base_vertices":sorted(counts),"footprint_BU2":sorted(areas),
            "component_volume_BU3":sorted(volumes),"min_component_separating_aabb_axis_BU":min(distances,default=None),
            "manifold_oriented":True,"decorative_scope":True}


def read_source_textures():
    materials, mapping = BASE["load_materials"]()
    files = {}
    for label in ("MossStone","MountainRock","MudBank"):
        src = materials[label]
        node = next(n for n in src.node_tree.nodes if n.type=="TEX_IMAGE")
        image = node.image
        rgba = np.empty(image.size[0]*image.size[1]*4,dtype=np.float32)
        image.pixels.foreach_get(rgba)
        color = rgba.reshape(image.size[1],image.size[0],4)[..., :3]
        check(np.isfinite(color).all(), label)
        files[label] = (color, mapping[label])
    return files


def color_to_linear(color):
    return np.asarray(BASE["color"](color)[:3], dtype=np.float64)


def encode_srgb(linear):
    return np.rint(np.clip(np.where(linear<=.0031308,12.92*linear,1.055*linear**(1/2.4)-.055),0,1)*255).astype(np.uint8)


def bake_atlas(output, sources):
    n=ATLAS_SIZE
    x,y=np.meshgrid(np.arange(n)/(n-1), np.arange(n)/(n-1))
    X=PHI*x
    rock, moss, clay = (sources[k][0][::2,::2] for k in ("MountainRock","MossStone","MudBank"))
    # Soft broad strata wrap around the object, then the source paper grain breaks up the bands.
    z=y+.045*np.sin(2*X-.37)+.025*np.sin(5*X+PHI*y)
    band=.5+.5*np.sin(14*z+.9*np.sin(2*X)+1.5)
    patches=.52*np.cos(X+.6)*np.sin(8*y+.5)+.31*np.sin(3*X-7*y)+.17*np.cos(6*X+23*y)
    growth=np.clip((patches-.14)/.53,0,1)**1.45
    growth*=np.clip(1.50-y,0,.83)
    dark, light=color_to_linear("554335"),color_to_linear("856951")
    warm=dark+(light-dark)*(.18+.69*band[...,None])
    pigment=.80*warm+.10*rock+.10*clay
    greens=.41*moss+.59*color_to_linear("495A38")
    pigment=pigment*(1-growth[...,None])+greens*growth[...,None]
    # Add a shallow illustrated sediment line without a separate decal or transparency pass.
    thin=np.exp(-((z-.37+.052*np.sin(X+.6))/.021)**2)
    pigment=.95*pigment*(1-.24*thin[...,None]) + .05*rock
    # Match edge texels so cylindrical seams stay invisible with texture repeat.
    pigment[:,0]=.5*(pigment[:,0]+pigment[:,-1])
    pigment[:,-1]=pigment[:,0]
    packed=encode_srgb(np.clip(pigment,0,1))
    def chunk(label, data):
        return struct.pack(">I",len(data))+label+data+struct.pack(">I",zlib.crc32(label+data))
    png=(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR",struct.pack(">IIBBBBB",n,n,8,2,0,0,0)) +
         chunk(b"IDAT",zlib.compress(b"".join(b"\0"+row.tobytes() for row in packed[::-1])))+chunk(b"IEND",b""))
    path=output/ATLAS
    path.parent.mkdir()
    path.write_bytes(png)
    material=paint("ENV011_RockAtlas","958A76")
    texture=material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image=bpy.data.images.load(str(path))
    texture.image.colorspace_settings.name="sRGB"
    texture.image.pack()
    texture.image.filepath="//"+ATLAS
    pbr=material.node_tree.nodes.get("Principled BSDF")
    pbr.inputs["Roughness"].default_value=.94
    pbr.inputs["Specular IOR Level"].default_value=.27
    material.node_tree.links.new(texture.outputs["Color"],pbr.inputs["Base Color"])
    return material,{"path":ATLAS,"sha256":digest(path),"extent_px":[n,n],"mode":"opaque sRGB",
                     "wrap_u_edge_rgb8_max_delta":int(np.max(np.abs(packed[:,0].astype(int)-packed[:,-1]))),
                     "rgb8_low_high":[int(packed.min()),int(packed.max())]}


def terrain_ink():
    loaded,_=BASE["load_materials"]()
    return loaded["GrassFlat"]


def place_tiles(parent, mat):
    shades=dict.fromkeys(BASE["SURFACES"],mat)
    source=BASE["build_module"]("Flat",parent,shades)
    source.location=(-35.,-35.,0)
    tiles={}
    for ix in range(-7,8):
        for iy in range(-2,13):
            name=f"Review terrain {ix},{iy}"
            if abs(ix) >= 2 and iy in (1,2,3,4):
                tile=BASE["build_module"]("GentleSlope",parent,shades)
                tile.name=name
                tile.location=(ix*10.,iy*10.,0)
            else:
                tile=obj(parent,name,source.data,(ix*10.,iy*10.,0))
            tiles[ix,iy]=tile
    bpy.data.objects.remove(source,do_unlink=True)
    return tiles


def arrange(scene, items, mat):
    g=group("Review | ENV-001 surface and placed rocks",scene.collection)
    lights=BASE["studio"](scene,scene.collection)
    next(o for o in lights.objects if o.type=="LIGHT").rotation_euler=Vector((.64,.40,-1)).to_track_quat("-Z","Y").to_euler()
    terrain=place_tiles(g,mat)
    grounding = (
        ("Rock_Round",(-2.21,1.25),-.31,.93),
        ("Rock_Long",(2.87,2.15),.71,1.03),
        ("PebbleCluster",(-2.26,4.95),-.22,1.00),
        ("PebbleCluster",(2.93,7.01),.94,.72),
        ("Rock_Round",(4.26,11.8),.37,.82),
        ("Rock_Long",(-4.37,13.7),.31,.85),
        ("Rock_Round",(-5.29,16.4),.82,.53),
        ("PebbleCluster",(6.01,17.1),-.64,.92),
        ("Rock_Long",(2.78,19.7),-.91,.60),
        ("PebbleCluster",(-4.55,24.45),.68,1.00),
        ("Rock_Round",(5.2,29.3),.34,.65),
    )
    placed=[]
    for index,(label,xy,angle,scale) in enumerate(grounding,1):
        item=obj(g,f"{label} | sample {index:02d}",items[label].data,(*xy,0))
        item.rotation_euler.z=angle
        item.scale=(scale,)*3
        placed.append(item)
    bird = BASE["add_goose"](g)
    pair=[]
    for name,(pos,heading) in FRAME_POSES.items():
        camera=BASE["camera"](lights,f"Gameplay | {name}",(0,-7,3),(0,0,0))
        BASE["pose_at"](camera,bird,pos,Vector(heading).normalized())
        pair.append((name,camera))
    bpy.context.view_layer.update()
    probe=contact_probes(placed,terrain)
    return bird,placed,pair,probe


def contact_probes(rocks, terrain):
    tests={}
    trees={}
    all_xy=[]
    for item in rocks:
        matrix=item.matrix_world
        supports={tuple(matrix @ v.co) for v in item.data.vertices if abs(v.co.z)<=SUPPORT_EPS}
        gaps=[]
        for inst_vert in (Vector(xyz) for xyz in sorted(supports)):
            i=int(math.floor((inst_vert.x+5)/10))
            j=int(math.floor((inst_vert.y+5)/10))
            if (i,j) not in trees:
                target=terrain[i,j]
                trees[i,j]=BVHTree.FromPolygons([target.matrix_world @ v.co for v in target.data.vertices],
                                               [tuple(p.vertices) for p in target.data.polygons],all_triangles=True)
            hit,*_=trees[i,j].ray_cast(Vector((inst_vert.x,inst_vert.y,5)),Vector((0,0,-1)),10)
            check(hit is not None,(item.name,inst_vert))
            gap=inst_vert.z-hit.z
            check(abs(gap)<SUPPORT_EPS,(item.name,gap))
            gaps.append(abs(gap))
        tests[item.name]=gaps
        all_xy.extend(matrix @ v.co for v in item.data.vertices)
    separation=min(abs(v.x) for v in all_xy)
    check(separation>1.1,separation)
    return {"support_rays":sum(len(v) for v in tests.values()),"max_ground_gap_BU":max(max(v) for v in tests.values()),
            "clearance_from_straight_route_centerline_BU":separation,"placement_count":len(tests),
            "sample_surface":"Actual ENV-001 Flat at each rock placement"}


def preview_lineup(scene, items, directory, name):
    set_collection=group("Rock prototypes | side by side",scene.collection)
    lights=BASE["studio"](scene,scene.collection)
    lamp=next(o for o in lights.objects if o.type=="LIGHT")
    lamp.data.energy=2.05
    lamp.rotation_euler=Vector((.46,.3,-1)).to_track_quat("-Z","Y").to_euler()
    floor=paint("Review stage | warm gray paper","B4B6AB")
    BASE["rectangle"](set_collection,"Review ground",-35,35,-35,35,-.001,floor)
    for label,cx,ang in (("Rock_Round",-2.65,-.07),("Rock_Long",0,.62),("PebbleCluster",2.75,.12)):
        clone=obj(set_collection,label+" | studio copy",items[label].data,(cx,0,0))
        clone.rotation_euler.z=ang
    cam=BASE["camera"](lights,"Asset proof | three forms",(1.35,-7.9,4.3),(0,0,.25),9.1)
    BASE["render"](scene,cam,directory,name,(1240,620),22 if name.startswith("preview") else 12)


def projection(scene,cam,item):
    return [world_to_camera_view(scene,cam,item.matrix_world @ v.co) for v in item.data.vertices]


def bounds_px(points):
    W,H=SOURCE_SIZE
    return [min(p.x for p in points)*W,min(p.y for p in points)*H,
            max(p.x for p in points)*W,max(p.y for p in points)*H]


def projected_hull(points):
    coords=sorted(set((p.x,p.y) for p in points))
    hull=[]
    for entries in (coords, coords[::-1]):
        edge=[]
        for p in entries:
            while len(edge)>=2:
                a,b=edge[-2:]
                if (b[0]-a[0])*(p[1]-a[1]) > (b[1]-a[1])*(p[0]-a[0]):
                    break
                edge.pop()
            edge.append(p)
        hull.extend(edge[:-1])
    return hull


def read_png_rgb8(path):
    """Read standard non-interlaced 8-bit RGB from a Blender PNG."""
    packed=path.read_bytes()
    cursor=8
    chunks=[]
    while cursor < len(packed):
        length,label=struct.unpack_from(">I4s",packed,cursor)
        data=packed[cursor+8:cursor+8+length]
        if label==b"IHDR":
            width,height,depth,ch,_,_,interlace=struct.unpack(">IIBBBBB",data)
        elif label==b"IDAT":
            chunks.append(data)
        cursor+=length+12
    check((width,height)==SOURCE_SIZE and (depth,ch,interlace)==(8,2,0),(path,width,height,depth,ch,interlace))
    stream=zlib.decompress(b"".join(chunks))
    stride=width*3
    result=np.zeros((height,stride),dtype=np.uint8)
    for y in range(height):
        offset=y*(stride+1)
        mode=stream[offset]
        raw=stream[offset+1:offset+stride+1]
        prev=result[y-1] if y else np.zeros(stride,dtype=np.uint8)
        row=result[y]
        if mode==0:
            row[:]=np.frombuffer(raw,dtype=np.uint8)
        elif mode==2:
            row[:]=np.frombuffer(raw,dtype=np.uint8)+prev
        else:
            for i,pixel in enumerate(raw):
                a=int(row[i-3]) if i>=3 else 0
                b=int(prev[i])
                c=int(prev[i-3]) if i>=3 else 0
                if mode==1: delta=a
                elif mode==3: delta=(a+b)//2
                else:
                    check(mode==4, mode)
                    p=a+b-c
                    u,v,w=abs(p-a),abs(p-b),abs(p-c)
                    delta=a if u<=v and u<=w else b if v<=w else c
                row[i]=(pixel+delta)&255
    return result.reshape(height,width,3)


def color_from_visible_pixels(scene,cam,objects,filename):
    # Cast through rendered pixel centers, selecting directly visible rock or goose surfaces.
    W,H=SOURCE_SIZE
    # An 8-bit Blender PNG is stored as display RGB; Blender exposes it with an sRGB image profile.
    # For unambiguous audit values, read the actual encoded scanlines rather than converting an image buffer twice.
    rgba=read_png_rgb8(filename)[::-1]
    dg=bpy.context.evaluated_depsgraph_get()
    frame=list(cam.data.view_frame(scene=scene))
    ordered=sorted(frame,key=lambda v:v.y)
    lowleft,lowright=sorted(ordered[:2],key=lambda v:v.x)
    highleft,highright=sorted(ordered[2:],key=lambda v:v.x)
    stats={}
    for item in objects:
        box=bounds_px(projection(scene,cam,item))
        lo_x,lo_y,hi_x,hi_y=[int(v) for v in box]
        color=[]
        for x in range(max(0,lo_x+1),min(W,hi_x),2):
            for y in range(max(0,lo_y+1),min(H,hi_y),2):
                sx,sy=(x+.5)/W,(y+.5)/H
                local=lowleft.lerp(lowright,sx).lerp(highleft.lerp(highright,sx),sy)
                ray=(cam.matrix_world.to_3x3() @ local).normalized()
                hit,_,_,_,surface,_=scene.ray_cast(dg,cam.location,ray)
                if hit and surface==item:
                    color.append(rgba[y,x,:3])
        check(len(color)>=12,(item.name,len(color),box))
        rgb=np.rint(np.median(np.asarray(color),axis=0)).astype(np.uint8)
        stats[item.name]={"visible_rgb_pixel_probes":len(color),"srgb_median_rgb8":rgb.tolist(),
                          "luma_rgb8":float(rgb @ np.asarray([.2126,.7152,.0722]))}
    return stats


def lens_evidence(scene,items,ground,folder,prefix,full):
    bird,placed,cameras,contact=arrange(scene,items,ground)
    frames={}
    for i,(name,cam) in enumerate(cameras):
        if i and not full:
            continue
        loc,heading=FRAME_POSES[name]
        BASE["pose_at"](cam,bird,loc,Vector(heading).normalized())
        filename=prefix+name
        BASE["render"](scene,cam,folder,filename,SOURCE_SIZE,22 if full else 12)
        leader=bounds_px(projection(scene,cam,bird))
        near={}
        for item in placed[:3]:
            p=bounds_px(projection(scene,cam,item))
            gap_x=max(p[0]-leader[2],leader[0]-p[2],0)
            gap_y=max(p[1]-leader[3],leader[1]-p[3],0)
            gap=math.hypot(gap_x,gap_y)
            check(0<=p[0]<p[2]<=SOURCE_SIZE[0] and 0<=p[1]<p[3]<=SOURCE_SIZE[1]
                  and p[2]-p[0]>18 and p[3]-p[1]>8 and gap>12,(item.name,p,gap))
            silhouette=projected_hull(projection(scene,cam,item))
            area=abs(sum(x0*y1-x1*y0 for (x0,y0),(x1,y1) in zip(silhouette,silhouette[1:]+silhouette[:1])))*.5
            near[item.name]={"bounds_px":p,"hull_area_px2":area*SOURCE_SIZE[0]*SOURCE_SIZE[1],"leader_projection_box_gap_px":gap}
        measurement={"leader_bounds_px":leader,"nearest_rock_groups":near}
        if full:
            appearance=color_from_visible_pixels(scene,cam,[bird,*placed[:3]],folder/(filename+".png"))
            leader_rgb=np.asarray(appearance[bird.name]["srgb_median_rgb8"])
            differences={k: float(np.linalg.norm(np.asarray(v["srgb_median_rgb8"])-leader_rgb))
                            for k,v in appearance.items() if k != bird.name}
            check(min(differences.values())>=12,(name,differences))
            measurement["appearance"]=appearance
            measurement["nearest_rock_to_leader_median_srgb_rgb8_euclidean"]=differences
        frames[name]=measurement
    p,h=FRAME_POSES["fixed_rear"]
    BASE["pose_at"](cameras[0][1],bird,p,Vector(h))
    BASE["set_preview_workspace"](scene,cameras[0][1])
    scene.render.filepath="//review.png"
    return {"screen_study":frames,"ground_contact":contact}


def check_gltf(path, source, tex_digest):
    doc, blob = BASE["glb_chunks"](path)
    node, = doc["nodes"]
    check(node["name"]==source.name and not doc.get("animations") and not doc.get("skins"), node)
    check(node.get("translation",[0,0,0])==[0,0,0] and node.get("scale",[1,1,1])==[1,1,1]
          and node.get("rotation",[0,0,0,1])==[0,0,0,1], node)
    check(node["extras"]["generate_hard_collision"] is False, node)
    primitive,=doc["meshes"][0]["primitives"]
    material,=doc["materials"]
    image,=doc["images"]
    view=doc["bufferViews"][image["bufferView"]]
    start=view.get("byteOffset",0)
    check(image["mimeType"]=="image/png" and sha256(blob[start:start+view["byteLength"]]).hexdigest()==tex_digest,path)
    check(material["name"]=="ENV011_RockAtlas" and material.get("alphaMode","OPAQUE")=="OPAQUE",material)
    signature={tuple(round(v,6) for v in (p.co.x,p.co.z,-p.co.y)) for p in source.data.vertices}
    accessor=doc["accessors"][primitive["attributes"]["POSITION"]]
    view=doc["bufferViews"][accessor["bufferView"]]
    start=view.get("byteOffset",0)+accessor.get("byteOffset",0)
    stride=view.get("byteStride",12)
    exported={tuple(round(v,6) for v in struct.unpack_from("<3f",blob,start+i*stride))
              for i in range(accessor["count"])}
    check(signature==exported,path)
    return {"raw_gltf_positions":len(exported),"atlas_sha256":tex_digest,"raw_rgb_material":material["name"],
            "root_identity":True,"no_hard_collision_hint":True}


def roundtrip(folder, rocks, texture):
    out={}
    imported={}
    for name,source in rocks.items():
        path=folder/f"ENV-011_{name}.glb"
        checks=check_gltf(path,source,texture)
        before=set(bpy.data.objects)
        status=bpy.ops.import_scene.gltf(filepath=str(path),merge_vertices=False,import_pack_images=True)
        check(status=={"FINISHED"},name)
        loaded,=set(bpy.data.objects)-before
        check(loaded.type=="MESH" and loaded.parent is None and loaded.location.length<1e-7
              and tuple(loaded.scale)==(1,1,1),name)
        a=BASE["signature"](source.data)
        b=BASE["signature"](loaded.data)
        check(a.keys()==b.keys(),(name,"positions and winding"))
        pos=normal=uv=0.
        for key,(mat,original) in a.items():
            restored, afterward=b[key]
            check(mat==restored,(name,mat,restored))
            for (p,n,t),(q,m,u) in zip(original,afterward,strict=True):
                pos=max(pos,(p-q).length)
                normal=max(normal,BASE["angle"](n,m))
                uv=max(uv,(t-u).length)
        check(pos<1e-6 and normal<.1 and uv<1e-6,(name,pos,normal,uv))
        out[name]=dict(checks,triangles=len(b),vertices_after_import=len(loaded.data.vertices),
                       max_position_delta_BU=pos,max_normal_delta_deg=normal,max_uv_delta=uv)
        imported[name]=loaded
    return imported,out


def build(output):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    library=bpy.context.scene
    library.name="ENV-011 | Asset library"
    library.unit_settings.system="NONE"
    roots=group("Three rock groups | models at origin",library.collection)
    neutral=paint("Graybox | rock form","8B8984")
    items={}
    for name,drafts in ROCKS.items():
        model=RockMesh()
        for dimensions in drafts:
            model.stone(*dimensions)
        items[name]=model.build(roots,name,neutral)
    geometry={label:validate_rock(rock,label) for label,rock in items.items()}
    gray_lineup=BASE["fresh_scene"]("ENV-011 | Graybox prototypes")
    preview_lineup(gray_lineup,items,output,"graybox_lineup")
    gray_land=BASE["fresh_scene"]("ENV-011 | Graybox placement")
    gray_evidence=lens_evidence(gray_land,items,paint("Graybox | green gray ground","A1A79B"),output,"graybox_",False)
    bpy.data.scenes.remove(gray_lineup)
    bpy.data.scenes.remove(gray_land)
    source=read_source_textures()
    material,meta=bake_atlas(output,source)
    for rock in items.values(): rock.data.materials[0]=material
    bpy.context.window.scene=library
    for name,rock in items.items():
        bpy.ops.object.select_all(action="DESELECT")
        rock.select_set(True)
        bpy.context.view_layer.objects.active=rock
        check(bpy.ops.export_scene.gltf(filepath=str(output/f"ENV-011_{name}.glb"),export_format="GLB",export_yup=True,
                                       use_selection=True,export_animations=False,export_extras=True)=={"FINISHED"},name)
    close=BASE["fresh_scene"]("ENV-011 | Model lineup")
    preview_lineup(close,items,output,"preview_lineup")
    scene=BASE["fresh_scene"]("ENV-011 | Fixed rear and ground contact")
    evidence=lens_evidence(scene,items,terrain_ink(),output,"preview_",True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{STEM}.blend"))
    rt=BASE["fresh_scene"]("ENV-011 | Reimported")
    loaded,transfers=roundtrip(output,items,meta["sha256"])
    for item in loaded.values():item.hide_render=True
    preview_lineup(rt,loaded,output,"preview_glb_roundtrip")
    assembled=BASE["fresh_scene"]("ENV-011 | Reimported placement")
    glb_evidence=lens_evidence(assembled,loaded,terrain_ink(),output,"roundtrip_",False)
    references=[v["ground_contact"] for v in (gray_evidence,evidence,glb_evidence)]
    for field in ("support_rays","max_ground_gap_BU","clearance_from_straight_route_centerline_BU","placement_count"):
        spread=max(v[field] for v in references)-min(v[field] for v in references)
        check(spread < SUPPORT_EPS,(field,spread,references))
    projections=[v["screen_study"]["fixed_rear"]["nearest_rock_groups"] for v in (evidence,glb_evidence)]
    for a,b in zip(*(p.values() for p in projections),strict=True):
        check(max(abs(x-y) for x,y in zip(a["bounds_px"],b["bounds_px"],strict=True))<1e-4,
              ("screen space invariance",a,b))
    write(output/"qa.json",{"id":"ENV-011","version":"v001","status":"needs_review",
        "geometry_graybox":geometry,"graybox_camera":gray_evidence,"camera_material_review":evidence,"roundtrip":transfers,
        "roundtrip_preview_contact":glb_evidence["ground_contact"],"hard_collision_policy":"Decorative role; extra carries false",
        "pending":["Art owner approval; RealityKit and actual scenery placement, avoidance and iPhone/iPad." ]})
    mats=MAT3/"MAT-003_wetland_rock.blend"
    source_manifest=json.loads((MAT3/"asset_manifest.json").read_text())
    write(output/"asset_manifest.json",{"id":"ENV-011","version":"v001","status":"needs_review",
        "production_order_1_based":51,"owner_request_scope":"Include v001 together with ENV-012 through ENV-014",
        "depends":["MAT-003/v001"],"materials":{"RockAtlas":meta},"texture_sources":{k:v for k,(_,v) in source.items()},
        "source_library_actual_sha256":digest(mats),"source_library_manifest_sha256":source_manifest["files"][mats.name],
        "expected_objects":list(items),"blender_file":f"{STEM}.blend","blender":"5.2.2 LTS",
        "glb_files":[f"ENV-011_{key}.glb" for key in items],"pivot_BU":[0,0,0],"model_local_xy_plus_y_forward":True,
        "up_gltf":"Y","axis_swizzle_gltf":["x","z","-y"],"review_only_sources":["ENV-001/v001","CHR-001/v001"],
        "rights":"Project-original mesh geometry and recoloring of existing project textures. No third-party input."})


def verify(source, output):
    bpy.ops.wm.open_mainfile(filepath=str(source/f"{STEM}.blend"))
    items={n:bpy.data.objects[n] for n in NAMES}
    expected=json.loads((source/"qa.json").read_text())
    texture=json.loads((source/"asset_manifest.json").read_text())["materials"]["RockAtlas"]
    mesh_checks={k:validate_rock(v,k) for k,v in items.items()}
    check(mesh_checks==expected["geometry_graybox"],"geometry changed")
    BASE["fresh_scene"]("ENV-011 | Independent verification")
    _,report=roundtrip(source,items,texture["sha256"])
    check(report==expected["roundtrip"],"roundtrip changed")
    write(output/"recheck.json",{"result":"pass","geometry":mesh_checks,"roundtrip":report})


def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument("output",type=Path)
    p.add_argument("--verify",type=Path)
    args=p.parse_args(sys.argv[sys.argv.index("--")+1:])
    args.output.mkdir(parents=True,exist_ok=True)
    check(not any(args.output.iterdir()),"Use an empty output folder")
    if args.verify:verify(args.verify.resolve(),args.output.resolve())
    else:build(args.output.resolve())


if __name__=="__main__":
    main()
