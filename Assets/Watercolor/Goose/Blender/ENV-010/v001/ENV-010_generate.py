"""Generate the pass walls and mouth, and certify the snapped review corridor in Blender."""
import argparse
from hashlib import sha256
from itertools import product
import json
import math
from pathlib import Path
import runpy
import struct
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree


HERE = Path(__file__).resolve().parent
LIB = HERE.parents[1]
ENV1 = LIB / "ENV-001/v001"
ENV9 = LIB / "ENV-009/v001"
BASE = runpy.run_path(str(ENV1 / "ENV-001_generate.py"))
check, obj, group = (BASE[k] for k in ("check", "obj", "collection"))
file_hash, write_json = BASE["file_hash"], BASE["write_json"]
NAMES = ("Pass_Left", "Pass_Right", "Mouth")
STEM = "ENV-010_short_pass"
MATERIALS = ("GrassFlat", "MossStone", "MountainRock")
CAMERA_POSES = {"checkpoint_a": (0., 0., (0., 1.)), "approach": (-6.6, 9.0, (-.27, .96286)),
                "mouth": (-11.1, 19.0, (-.045, .998987)), "throat": (-10.82, 31.0, (.035, .999387)),
                "exit": (-11.17, 43.0, (-.024, .999712))}
PITCH = .625
X_LO, X_HI, DIVIDER = -21.5, -1.5, -11.5
FRONT, BOUNDARY, EXIT = 10., 20., 50.
ENVELOPE_HALF = 2.6
TOL = 1e-5
SEAM_NORMAL_TOL = .03
RAW_NORMAL_TOL = .03
IMPORT_NORMAL_TOL = .12
DESIGN_Y = (10, 13, 17, 20, 23, 27, 32, 36, 41, 46, 50)
LEFT_HEIGHT = (0, 1.24, 3.20, 4.05, 5.30, 6.7, 6.1, 7.2, 5.7, 2.5, 0)
RIGHT_HEIGHT = (0, .61, 1.86, 2.96, 4.23, 5.97, 5.75, 5.8, 5.25, 2.8, 0)
CENTRE_SHIFT = (0, 0, .04, -.31, -.70, -.46, .48, .62, .30, -.23, 0)
CLEAR_HALF = (10, 7.5, 5.22, 4.1, 3.72, 3.37, 3.52, 3.57, 4.18, 5.6, 10)


def mix(keys, values, x):
    if x <= keys[0]:
        return values[0]
    if x >= keys[-1]:
        return values[-1]
    i = next(i for i in range(1, len(keys)) if x <= keys[i])
    t = (x - keys[i - 1]) / (keys[i] - keys[i - 1])
    a, b = values[i - 1:i + 1]
    return a + (b - a) * t


def center(y):
    return DIVIDER + mix(DESIGN_Y, CENTRE_SHIFT, y)


def height(x, y):
    datum = center(y)
    if y <= FRONT or y >= EXIT or x <= X_LO or x >= X_HI:
        return 0.0
    half = mix(DESIGN_Y, CLEAR_HALF, y)
    radial = abs(x - datum)
    outer = (datum - X_LO) if x <= datum else (X_HI - datum)
    u = (radial - half) / max(.01, outer - half)
    if not 0 < u < 1:
        return 0.0
    left = x <= datum
    max_height = mix(DESIGN_Y, LEFT_HEIGHT if left else RIGHT_HEIGHT, y)
    ledge = .04 * math.sin(.62 * y + 2.5 * u) + .025 * math.sin(1.45 * y - 8 * u)
    profile = mix((0,.09,.25,.37,.53,.67,.80,.91,1), (0,.07,.32,.38,.73,1,.89,.47,0), u)
    contour = profile + ledge * math.sin(math.pi * u)
    return max(0.0, max_height * contour)


def select_surface(x, y, z, slope):
    if z < .08 or (z < .38 and slope > .83):
        return 0
    if z < .86 + .27 * math.sin(y * .56 + x * .7) and slope > .47:
        return 1
    if z < 1.70 and slope > .75 and math.sin(y * .81 + x) > .3:
        return 1
    return 2


def module(name, parent, materials):
    bounds = (X_LO, DIVIDER, BOUNDARY, EXIT) if name == "Pass_Left" else (
             (DIVIDER, X_HI, BOUNDARY, EXIT) if name == "Pass_Right" else (X_LO, X_HI, FRONT, BOUNDARY))
    x0, x1, y0, y1 = bounds
    nx, ny = round((x1 - x0) / PITCH), round((y1 - y0) / PITCH)
    vertices = []
    for iy in range(ny + 1):
        y = y0 + iy * PITCH
        for ix in range(nx + 1):
            x = x0 + ix * PITCH
            # Keep Y row cross sections exact. Jitter X in rock interiors to soften the triangulation.
            if 0 < iy < ny and 0 < ix < nx and abs(x - center(y)) > 3.25:
                x += .17 * math.sin(iy * .92 + ix * 2.31) + .09 * math.cos(iy * .83 - ix * .69)
            vertices.append((x, y, height(x, y)))
    faces = []
    for j, i in product(range(ny), range(nx)):
        a = j * (nx + 1) + i
        b, c, d = a + 1, a + nx + 2, a + nx + 1
        faces.extend(((a,b,c),(a,c,d)) if (i+j)%2 else ((a,b,d),(b,c,d)))
    mesh = bpy.data.meshes.new(name + "_surface")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for mat in materials.values():
        mesh.materials.append(mat)
    uv = mesh.uv_layers.new(name="TerrainUV")
    for face in mesh.polygons:
        x, y, z = face.center
        face.material_index = select_surface(x, y, z, face.normal.z)
        face.use_smooth = face.material_index != 2
        for loop in face.loop_indices:
            vx, vy, _ = mesh.vertices[mesh.loops[loop].vertex_index].co
            uv.data[loop].uv = ((vx - X_LO) / 10, vy / 10)
    # Keep normals identical where submeshes meet and across the ENV-001 flat-tile connectors.
    normals = [(0,0,0)] * len(vertices)
    for i, (x, y, z) in enumerate(vertices):
        if x in bounds[:2] or y in bounds[2:]:
            if z == 0:
                normals[i] = (0,0,1)
            else:
                dx = (height(x+.04,y) - height(x-.04,y)) / .08
                dy = (height(x,y+.04) - height(x,y-.04)) / .08
                normals[i] = Vector((-dx,-dy,1)).normalized()
    for face in mesh.polygons:
        if any(normals[i] != (0,0,0) for i in face.vertices):
            face.use_smooth = True
    mesh.normals_split_custom_set_from_vertices(normals)
    tile = obj(parent, name, mesh)
    tile["assembly_pivot_BU"] = [0., 0., 0.]
    tile["cross_section_step_BU"] = PITCH
    tile.asset_mark()
    tile.asset_data.description = "ENV-010 v001 | Shared origin at S2 checkpoint A | +Y forward"
    return tile


def append(path, names):
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        check(set(names) <= set(source.objects), (path, names, source.objects))
        target.objects = list(names)
    return dict(zip(names, target.objects))


def outline(mesh, axis, coord, offset=(0, 0, 0)):
    shift = Vector(offset)
    uv = mesh.uv_layers.active.data
    buckets = {}
    for loop in mesh.loops:
        p = mesh.vertices[loop.vertex_index].co + shift
        if abs(p[axis] - coord) <= TOL:
            buckets.setdefault(round(p[1-axis], 5), []).append((p, mesh.corner_normals[loop.index].vector.copy(),
                                                             uv[loop.index].uv.copy()))
    return buckets


def compare_edges(first, second, label):
    check(first.keys() == second.keys(), (label, first.keys(), second.keys()))
    pos = normal = uv = 0.
    for key in first:
        for (a,n,t),(b,m,u) in product(first[key],second[key]):
            pos = max(pos, (a-b).length)
            normal = max(normal, BASE["angle"](n,m))
            uv = max(uv, *(abs(v - round(v)) for v in t - u))
    check(pos < TOL and normal < SEAM_NORMAL_TOL and uv < 1e-5, (label,pos,normal,uv))
    return {"label":label, "samples":len(first), "max_gap_BU":pos, "max_normal_error_deg":normal,"max_uv_modulo_error":uv}


def joins(tiles, flat):
    result = []
    mouth = outline(tiles["Mouth"].data, 1, BOUNDARY)
    front = outline(tiles["Mouth"].data, 1, FRONT)
    p_l, p_r = tiles["Pass_Left"].data, tiles["Pass_Right"].data
    result.append(compare_edges(outline(p_l, 0, DIVIDER),outline(p_r,0,DIVIDER),"Left–Right central longitudinal join"))
    for left, mesh in ((True, p_l), (False,p_r)):
        x0, x1 = (X_LO,DIVIDER) if left else (DIVIDER,X_HI)
        x_center = (x0 + x1) / 2
        key_subset = lambda ring: {x: points for x,points in ring.items() if x0 <= x <= x1}
        result.append(compare_edges(key_subset(mouth),outline(mesh,1,BOUNDARY),"Mouth–" + mesh.name))
        flat_s = outline(flat.data,1,FRONT,(x_center,FRONT-5,0))
        flat_n = outline(flat.data,1,EXIT,(x_center,EXIT+5,0))
        result.append(compare_edges(key_subset(front),flat_s,"Approach Flat–" + mesh.name))
        result.append(compare_edges(outline(mesh,1,EXIT),flat_n,mesh.name + "–Exit Flat"))
    for exterior_x, offset_x, name in ((X_LO, X_LO-5,"west"), (X_HI, X_HI+5,"east")):
        wall_parts=(tiles["Mouth"],tiles["Pass_Left" if name=="west" else "Pass_Right"])
        for y in (15, 25, 35, 45):
            mesh=wall_parts[y>=20].data
            limits=(y-5,y+5)
            exterior={pos:points for pos,points in outline(mesh,0,exterior_x).items()
                      if limits[0] <= pos <= limits[1]}
            comparison=outline(flat.data,0,exterior_x,(offset_x,y,0))
            result.append(compare_edges(exterior,comparison,f"{name} outer Flat y={y}"))
    return result


def clipped(vertices, signed):
    values = []
    for a, b in zip(vertices, vertices[1:] + vertices[:1]):
        da, db = signed(a), signed(b)
        if da >= 0:
            values.append(a)
        if (da >= 0) != (db >= 0):
            values.append(a.lerp(b, da / (da - db)))
    return values


def corridor(tiles):
    # Linear interpolation of the intended center at each row so clipping is exact on every triangle.
    centerline = [(FRONT + j*PITCH, center(FRONT+j*PITCH)) for j in range(65)]
    meshes = [item.data for item in tiles.values()]
    dry_triangles, corridor_area = 0, 0.
    min_height, max_height = math.inf, -math.inf
    for mesh in meshes:
        for face in mesh.polygons:
            check(face.area > 0 and face.normal.z > 0, (mesh.name, face.index))
            points = [mesh.vertices[i].co for i in face.vertices]
            row = round((min(v.y for v in points)-FRONT)/PITCH)
            y0, left_pos = centerline[row]
            y1, right_pos = centerline[row+1]
            def cross_section(v):
                return v.x - (left_pos + (right_pos-left_pos)*(v.y-y0)/(y1-y0))
            intersection = clipped(points,lambda v: ENVELOPE_HALF + cross_section(v))
            if intersection:
                intersection = clipped(intersection,lambda v: ENVELOPE_HALF - cross_section(v))
            if not intersection:
                continue
            dry_triangles += 1
            min_height = min(min_height, *(p.z for p in intersection))
            max_height = max(max_height, *(p.z for p in intersection))
            corridor_area += sum(a.x*b.y-a.y*b.x for a,b in zip(intersection,intersection[1:]+intersection[:1])) / 2
    expected = 2 * ENVELOPE_HALF * (EXIT-FRONT)
    check(abs(corridor_area-expected) < .001 and abs(max_height) < TOL and abs(min_height) < TOL,
          (corridor_area, expected,min_height,max_height))
    # Independent width along the section lines, using the first 0.05 BU rise as the toe of each wall.
    parts = []
    for row,(y,x) in enumerate(centerline):
        if y <= FRONT or y >= EXIT: continue
        bounds = []
        for sign,edge in ((-1,X_LO),(1,X_HI)):
            columns = set()
            for mesh in meshes:
                for v in mesh.vertices:
                    if abs(v.co.y-y) < TOL and (v.co.x-x)*sign>=0:
                        columns.add((round(v.co.x,6),float(v.co.z)))
            samples = sorted(columns,key=lambda p:sign*p[0])
            a,b = x,0.
            crossing = edge
            for c,d in samples:
                if d > .05:
                    crossing = a + (c-a)*(.05-b)/(d-b)
                    break
                a,b = c,d
            bounds.append(crossing)
        parts.append({"y_BU":y, "left_rock_toe_x_BU":bounds[0],"right_rock_toe_x_BU":bounds[1],
                      "width_at_toe_BU":bounds[1]-bounds[0]})
    return {"envelope_width_BU":2*ENVELOPE_HALF,"envelope_area_BU2":corridor_area,
            "triangle_intersections":dry_triangles,"min_max_ground_z_BU":[min_height,max_height],
            "minimum_toe_to_toe_width_BU":min(p["width_at_toe_BU"] for p in parts),
            "width_sections":parts,"method":"Exact 2D triangle clipping against piecewise linear strip; no simulated collision."}


def body_ray_clearance(tiles, goose):
    all_points, faces = [], []
    for item in tiles.values():
        offset = len(all_points)
        all_points.extend(v.co.copy() for v in item.data.vertices)
        faces.extend(tuple(offset+i for i in face.vertices) for face in item.data.polygons)
    bvh = BVHTree.FromPolygons(all_points,faces,all_triangles=True)
    root = 8/BASE["SCALE"]
    positions = []
    bbox = [(min(v.co[k] for v in goose.data.vertices),max(v.co[k] for v in goose.data.vertices)) for k in range(3)]
    probe_height = root + bbox[2][0]
    for y in (10 + i*.25 for i in range(161)):
        for dx in (-1.55, 0.,1.55):
            for cross in (bbox[0][0],0.,bbox[0][1]):
                x = center(y)+dx+cross
                yi = max(FRONT+.000003,min(EXIT-.000003,y))
                hit,*_ = bvh.ray_cast(Vector((x,yi,14)),Vector((0,0,-1)),20)
                check(hit is not None,(x,y))
                positions.append(probe_height-hit.z)
    check(min(positions) > .04,(probe_height,min(positions)))
    return {"sample_count":len(positions),"min_clearance_BU":min(positions),"bird_full_span_BU":bbox[0][1]-bbox[0][0],
            "root_height_game_units":8,"center_offsets_BU":[-1.55,0,1.55],
            "method":"Center and wingtips at lower bound of CHR-001 neutral-pose Z, three parallel lanes."}


def materials():
    all_mats, mapping = BASE["load_materials"]()
    for name in MATERIALS:
        mat=all_mats[name]
        if mat.name != name:
            previous=bpy.data.materials.get(name)
            if previous:
                previous.user_remap(mat)
                bpy.data.materials.remove(previous,do_unlink=True)
            mat.name=name
    return {n: all_mats[n] for n in MATERIALS}, {n: mapping[n] for n in MATERIALS}


def far_ridges(parent, path):
    items = append(path, ("FarRidge_A", "FarRidge_B", "FarRidge_C"))
    placements = ((-25, 70, -.10), (13, 95, -.12), (-28, 123, -.15))
    for (name, source), offset in zip(items.items(), placements):
        parent.objects.link(source)
        source.name = name + " | ENV-009 context"
        source.location = offset
    return items


def add_trees(parent, mats):
    verts, faces, inks = [], [], []
    for y, x, scale in ((15,-19,.51),(15.7,-3.5,.45),(16.6,-4.5,.65),(17,-18,.66),
                         (17.8,-20.2,.48),(18.8,-3.25,.58),(21.5,-19.4,.57),(23.6,-2.8,.52),
                         (24.2,-3.37,.57),(25.3,-18.6,.61),(37,-19.8,.40),(44.2,-3.7,.48)):
        floor = height(x,y)
        start = Vector((x,y,floor-.025))
        # Tilt the crown in one direction while the trunk stays planted.
        for item, w, h, lean in ((0,.037*scale,.64*scale,.09*scale),(1,.22*scale,.65*scale,.21*scale),
                                  (1,.15*scale,.49*scale,.32*scale)):
            origin = start + Vector((.11*scale,-.04*scale,.34*scale)) if item else start
            if lean > .25*scale:
                origin += Vector((.06*scale,.01*scale,.31*scale))
            rings = []
            for factor, radius in ((0,.30),(.34,1),(.72,.66)):
                c = origin + Vector((lean * factor,.05*scale*factor,h*factor))
                ring = list(range(len(verts),len(verts)+5))
                verts.extend(c + Vector((w*radius*math.cos(i*math.tau/5),w*radius*math.sin(i*math.tau/5),0))
                             for i in range(5))
                rings.append(ring)
            tip = len(verts)
            verts.append(origin + Vector((lean,.05*scale,h)))
            for a,b in zip(rings,rings[1:]):
                for i in range(5):
                    j=(i+1)%5
                    faces.extend(((a[i],a[j],b[j]),(a[i],b[j],b[i])))
                    inks.extend((item,item))
            for i in range(5):
                faces.append((rings[-1][i],rings[-1][(i+1)%5],tip))
                inks.append(item)
    mesh=bpy.data.meshes.new("Review tree line proxy")
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    for mat in mats: mesh.materials.append(mat)
    for poly, slot in zip(mesh.polygons,inks):poly.material_index=slot
    obj(parent,"Tree lines | review proxies until ENV-012",mesh)


def cloud_material():
    m = BASE["paint"]("Ridge mist | soft emission edge", "DCE4E8")
    nodes=m.node_tree.nodes
    nodes.clear()
    out=nodes.new("ShaderNodeOutputMaterial")
    transparent=nodes.new("ShaderNodeBsdfTransparent")
    em=nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value=BASE["color"]("D9E4EA")
    mix_shader=nodes.new("ShaderNodeMixShader")
    uv=nodes.new("ShaderNodeUVMap")
    uv.uv_map="MistUV"
    distance=nodes.new("ShaderNodeVectorMath")
    distance.operation="DISTANCE"
    distance.inputs[1].default_value=(.5,.5,0)
    fade=nodes.new("ShaderNodeMapRange")
    fade.interpolation_type="SMOOTHERSTEP"
    fade.inputs["From Min"].default_value=.07
    fade.inputs["From Max"].default_value=.48
    fade.inputs["To Min"].default_value=.52
    fade.inputs["To Max"].default_value=0
    links=m.node_tree.links
    links.new(uv.outputs[0],distance.inputs[0])
    links.new(distance.outputs["Value"],fade.inputs["Value"])
    links.new(fade.outputs[0],mix_shader.inputs[0])
    links.new(transparent.outputs[0],mix_shader.inputs[1])
    links.new(em.outputs[0],mix_shader.inputs[2])
    links.new(mix_shader.outputs[0],out.inputs[0])
    return m


def mist(parent):
    mat=cloud_material()
    data=bpy.data.meshes.new("Review ridge mist streamers")
    verts,faces=[],[]
    for x,y,z,w,h in ((-18.7,18.8,2.38,5.5,.77),(-18.8,23,3.10,6.60,.88),
                         (-5.8,23.6,2.38,5.1,.64),(-4.9,33,3.22,7.20,.78),
                         (-16.7,45.8,1.97,7.1,.64),(-12.8,62,.80,9.3,.71)):
        a=len(verts)
        verts.extend(((x-w/2,y,z-h/2),(x+w/2,y+.22,z-h/2+.095*w),(x+w/2,y+.22,z+h/2+.095*w),
                      (x-w/2,y,z+h/2)))
        faces.append((a,a+1,a+2,a+3))
    data.from_pydata(verts,[],faces)
    data.materials.append(mat)
    uv=data.uv_layers.new(name="MistUV")
    for face in data.polygons:
        for i,k in enumerate(face.loop_indices):uv.data[k].uv=((0,0),(1,0),(1,1),(0,1))[i]
    mist_object=obj(parent,"Ridge streamers | atmospheric review",data)
    mist_object["wind_axis"]="Positive X"
    return mist_object


def walk_way():
    return [(0,0),(-2.5,4),(-6.1,8.5),(-9.15,12),(-11.1,17.4)]


def path_markers(parent):
    mat=BASE["paint"]("Review | ochre route marks", "C8A36A", emission=True)
    path=[]
    points=walk_way()
    for a,b in zip(points,points[1:]):
        ax,ay=a
        bx,by=b
        for i in range(math.ceil(math.hypot(bx-ax,by-ay)/.52)):
            t=i/math.ceil(math.hypot(bx-ax,by-ay)/.52)
            path.append((ax+(bx-ax)*t,ay+(by-ay)*t))
    for i in range(62):
        y=17.4+i*.50
        path.append((center(y),y))
    verts, faces = [], []
    for x,y in path:
        a=len(verts)
        w=.09
        verts.extend(((x-w,y-w,.04),(x+w,y-w,.04),(x+w,y+w,.04),(x-w,y+w,.04)))
        faces.append((a,a+1,a+2,a+3))
    BASE["simple_mesh"](parent,"Review | path at source game-plane height",verts,faces,mat)


def terrain_accel(tiles, exterior):
    vertices,faces=[],[]
    for tile in (*tiles.values(), *exterior):
        offset=len(vertices)
        # module objects are at the shared asset origin; context flat copies are translated.
        vertices.extend(v.co + tile.location for v in tile.data.vertices)
        faces.extend(tuple(i+offset for i in p.vertices) for p in tile.data.polygons)
    return BVHTree.FromPolygons(vertices,faces,all_triangles=True)


def view_audit(scene, cameras, tiles, exterior):
    tree=terrain_accel(tiles,exterior)
    result={}
    for name,cam in cameras.items():
        scene.camera=cam
        scene.render.resolution_x, scene.render.resolution_y=BASE["GAME_SIZE"]
        bpy.context.view_layer.update()
        y={"checkpoint_a":21.5,"approach":25.625,"mouth":31.25,"throat":37.5,"exit":48.125}[name]
        xs=[center(y)+i*(2*ENVELOPE_HALF)/12-ENVELOPE_HALF for i in range(13)]
        gate=[]
        for x in xs:
            p=Vector((x,y,.09))
            ndc=world_to_camera_view(scene,cam,p)
            direction=p-cam.location
            hit,*_=tree.ray_cast(cam.location, direction.normalized(), direction.length-1e-4)
            gate.append({"inside_frame":0<ndc.x<1 and 0<ndc.y<1 and ndc.z>0, "ray_clear":hit is None,"x_ndc":float(ndc.x)})
        count=sum(row["inside_frame"] and row["ray_clear"] for row in gate)
        check(count>=11,(name,count,gate))
        width=(max(row["x_ndc"] for row in gate)-min(row["x_ndc"] for row in gate))*BASE["GAME_SIZE"][0]
        result[name]={"test_y_BU":y,"samples":len(gate),"visible_samples":count,"gate_width_px":width}
    return result


def stage(scene, tiles, flat, output, prefix, far_path=None, evidence=True):
    root=group("01 | Snapped mountain pass",scene.collection)
    for name,item in tiles.items():obj(root,name+" assembly",item.data)
    flats=group("02 | ENV-001 approach and exterior terrain",scene.collection)
    terrain=[]
    for row in range(-2,13):
        for col in range(-8,6):
            x=-16.5+col*10
            y=5+row*10
            if col in (0,1) and 1<=row<=4:continue
            terrain.append(obj(flats,f"Flat | {col},{row}",flat.data,(x,y,0)))
    canopy=group("03 | Review cues",scene.collection)
    camera_group=BASE["studio"](scene,scene.collection)
    scene.world.node_tree.nodes.get("Background").inputs["Color"].default_value=(.56,.68,.77,1)
    sky=BASE["paint"]("Sky backdrop | powder blue","A3BAC8",emission=True)
    BASE["simple_mesh"](canopy,"Sky wash", [(-600,205,-1),(600,205,-1),(600,205,180),(-600,205,180)],
                                  [(0,1,2,3)],sky)
    if far_path and evidence:
        far_ridges(group("04 | ENV-009 distant silhouettes",scene.collection),far_path)
    top=BASE["camera"](camera_group,"Mountain pass | top",(-11.5,27,83),(-11.5,27,0),60)
    cameras={}
    for name,(x,y,heading) in CAMERA_POSES.items():
        cam=BASE["camera"](camera_group,"Fixed rear | "+name,(0,0,1),(0,1,0))
        BASE["follow"](cam,(x,y),Vector(heading).normalized())
        cameras[name]=cam
    audit=view_audit(scene,cameras,tiles,terrain)
    if not evidence:
        BASE["render"](scene,top,output,prefix+"_top",(1050,1050),14)
        BASE["render"](scene,cameras["checkpoint_a"],output,prefix+"_checkpoint_a",BASE["GAME_SIZE"],18)
        return {"view":audit}
    scenery=group("05 | Atmosphere and inclined tree review proxies",scene.collection)
    mist_item=mist(scenery)
    add_trees(scenery,[BASE["paint"]("Tree trace | bark","837D71"),BASE["paint"]("Tree trace | grey green","657970")])
    route=group("06 | Route and goose scale review",scene.collection)
    path_markers(route)
    bird=BASE["add_goose"](route)
    clear=body_ray_clearance(tiles,bird)
    bird.hide_render=True
    mist_item.hide_render=True
    BASE["render"](scene,top,output,prefix+"_top",(1050,1050),20)
    bird.hide_render=False
    mist_item.hide_render=False
    keys=("checkpoint_a",) if prefix.endswith("roundtrip") else ("checkpoint_a","approach","mouth","throat","exit")
    for name in keys:
        x,y,heading=CAMERA_POSES[name]
        bird.location=(x,y,8/BASE["SCALE"])
        bird.rotation_euler.z=math.atan2(-heading[0],heading[1])
        BASE["render"](scene,cameras[name],output,prefix+"_"+name,BASE["GAME_SIZE"],24)
    x,y,_=CAMERA_POSES["checkpoint_a"]
    bird.location=(x,y,8/BASE["SCALE"])
    bird.rotation_euler=(0,0,0)
    BASE["set_preview_workspace"](scene,cameras["checkpoint_a"])
    scene.render.filepath="//review.png"
    return {"view":audit,"goose_geometry":clear}


def glb_export(output, tiles):
    for name,tile in tiles.items():
        bpy.ops.object.select_all(action="DESELECT")
        tile.select_set(True)
        bpy.context.view_layer.objects.active=tile
        status=bpy.ops.export_scene.gltf(filepath=str(output/f"ENV-010_{name}.glb"),export_format="GLB",
                    use_selection=True,export_yup=True,export_animations=False,export_extras=True)
        check(status=={"FINISHED"},name)


def encoded_normals(doc, blob, originals):
    data={}
    for name,corners in originals.values():
        for pos,normal,_ in corners:
            key=(name,tuple(round(v,5) for v in (pos.x,pos.z,-pos.y)))
            data.setdefault(key,[]).append(Vector((normal.x,normal.z,-normal.y)))

    def entries(i):
        access=doc["accessors"][i]
        view=doc["bufferViews"][access["bufferView"]]
        check(access["componentType"]==5126 and access["type"]=="VEC3",access)
        start=view.get("byteOffset",0)+access.get("byteOffset",0)
        stride=view.get("byteStride",12)
        return (struct.unpack_from("<3f",blob,start+k*stride) for k in range(access["count"]))

    maximum=0.
    for primitive in doc["meshes"][0]["primitives"]:
        mat=doc["materials"][primitive["material"]]["name"]
        attrs=primitive["attributes"]
        for p,n in zip(entries(attrs["POSITION"]),entries(attrs["NORMAL"]),strict=True):
            key=mat,tuple(round(v,5) for v in p)
            maximum=max(maximum,min(BASE["angle"](Vector(n),e) for e in data[key]))
    check(maximum < RAW_NORMAL_TOL,maximum)
    return maximum


def transport(output, local, textures):
    returned,report={},{}
    for name,tile in local.items():
        path=output/f"ENV-010_{name}.glb"
        doc,blob=BASE["glb_chunks"](path)
        node,=doc["nodes"]
        check(node["name"]==name and node.get("translation",[0,0,0])==[0,0,0]
              and node.get("rotation",[0,0,0,1])==[0,0,0,1] and node.get("scale",[1,1,1])==[1,1,1]
              and not doc.get("animations"),node)
        originals=BASE["signature"](tile.data)
        encoded_delta=encoded_normals(doc,blob,originals)
        source_positions={tuple(round(v,5) for v in (p.x,p.z,-p.y)) for p in (v.co for v in tile.data.vertices)}
        exported_positions=set()
        count=0
        for primitive in doc["meshes"][0]["primitives"]:
            acc=doc["accessors"][primitive["attributes"]["POSITION"]]
            view=doc["bufferViews"][acc["bufferView"]]
            start=view.get("byteOffset",0)+acc.get("byteOffset",0)
            stride=view.get("byteStride",12)
            for i in range(acc["count"]):
                exported_positions.add(tuple(round(f,5) for f in struct.unpack_from("<3f",blob,start+i*stride)))
            count+=doc["accessors"][primitive["indices"]]["count"]//3
        check(source_positions==exported_positions and count==len(originals),(name,count))
        for mat in doc["materials"]:
            info=mat["pbrMetallicRoughness"]
            tex=doc["textures"][info["baseColorTexture"]["index"]]
            image=doc["images"][tex["source"]]
            v=doc["bufferViews"][image["bufferView"]]
            start=v.get("byteOffset",0)
            actual=sha256(blob[start:start+v["byteLength"]]).hexdigest()
            check(actual==textures[mat["name"]]["sha256"],(name,mat["name"],actual))
        before=set(bpy.data.objects)
        status=bpy.ops.import_scene.gltf(filepath=str(path),merge_vertices=False)
        check(status=={"FINISHED"},name)
        loaded,=set(bpy.data.objects)-before
        check(loaded.type=="MESH" and loaded.location.length<TOL and loaded.matrix_world.to_scale()==Vector((1,1,1))
              and loaded.name.split(".")[0]==name,name)
        after=BASE["signature"](loaded.data)
        check(set(after)==set(originals),(name,"triangle identity"))
        position = normal = uv = 0.
        for k,(mat,old) in originals.items():
            transferred,new=after[k]
            check(mat==transferred,(name,k,mat,transferred))
            for (a,n,t),(b,m,u) in zip(old,new):
                position=max(position,(a-b).length)
                normal=max(normal,BASE["angle"](n,m))
                uv=max(uv,(t-u).length)
        check(position < TOL and normal < IMPORT_NORMAL_TOL and uv < TOL,(name, position,normal,uv))
        summary={"triangles":count,"vertices_in_blender":len(loaded.data.vertices),"max_position_delta_BU":position,
                 "max_corner_normal_delta_degrees":normal,"max_encoded_normal_delta_degrees":encoded_delta,"max_uv_delta":uv,
                 "bounds_BU":BASE["tile_box"](tile.data),"embedded_PNG_verified":True}
        returned[name]=loaded
        report[name]=summary
    return returned,report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--gray-only",action="store_true")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    check(not any(output.iterdir()),"Use an empty temporary directory.")
    if args.verify:
        path=args.verify.resolve()
        bpy.ops.wm.open_mainfile(filepath=str(path/f"{STEM}.blend"))
        manifest=json.loads((path/"asset_manifest.json").read_text())
        local={name:bpy.data.objects[name] for name in NAMES}
        flat=bpy.data.objects["Flat"]
        BASE["fresh_scene"]("Independent delivered GLBs")
        incoming,measures=transport(path,local,manifest["textures"])
        actual={"glb":measures,"joins":joins(incoming,flat),"corridor":corridor(incoming)}
        expect=json.loads((path/"qa.json").read_text())["roundtrip"]
        check(actual==expect,(actual.keys(),expect.keys()))
        write_json(output/"recheck.json",dict(result="pass",**actual))
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    lib=bpy.context.scene
    lib.name="ENV-010 | Source geometry"
    refs=group("ENV-001 connector reference",lib.collection)
    flat=append(ENV1/"ENV-001_terrain.blend",("Flat",))["Flat"]
    refs.objects.link(flat)
    flat.hide_set(True)
    flat.hide_render=True
    old=list(flat.data.materials)
    geometry=group("ENV-010 | Three snapped components",lib.collection)
    neutral={n:BASE["paint"]("Graybox | "+n,c) for n,c in zip(MATERIALS,("A6AEA4","A2A9A4","82929A"))}
    for i in range(len(flat.data.materials)):flat.data.materials[i]=neutral["GrassFlat"]
    local={name:module(name,geometry,neutral) for name in NAMES}
    original={"joins":joins(local,flat),"corridor":corridor(local)}
    gray=BASE["fresh_scene"]("ENV-010 | Graybox review")
    original.update(stage(gray,local,flat,output,"graybox",evidence=False))
    if args.gray_only:
        write_json(output/"graybox_qa.json",original)
        return
    ridge=ENV9/"ENV-009_far_ridges.blend"
    check(ridge.is_file(),"Build requires actual delivered ENV-009 far ridge library.")
    bpy.data.scenes.remove(gray)
    for i,mat in enumerate(old):flat.data.materials[i]=mat
    look,mapping=materials()
    for tile in local.values():
        for i,mat in enumerate(look.values()):tile.data.materials[i]=mat
    bpy.context.window.scene=lib
    glb_export(output,local)
    review=BASE["fresh_scene"]("ENV-010 | Fixed rear and corridor")
    textured=stage(review,local,flat,output,"preview",ridge)
    bpy.ops.wm.save_as_mainfile(filepath=str(output/f"{STEM}.blend"))
    final=BASE["fresh_scene"]("ENV-010 | Reimport")
    records,roundtrip=transport(output,local,mapping)
    after={"glb":roundtrip,"joins":joins(records,flat),"corridor":corridor(records)}
    for tile in records.values():tile.hide_render=True
    reassembled=stage(final,records,flat,output,"preview_glb_roundtrip",ridge,evidence=True)
    check(textured==reassembled,"Reimported camera or clearance results differed.")
    write_json(output/"qa.json",{"id":"ENV-010","version":"v001","status":"needs_review","graybox":original,
                     "fixed_rear_review":textured,"roundtrip":after,
                     "pending":["Full-energy passage, runtime collision and touch route validation.",
                        "FX-002 wind strength and time profile, ENV-012 animated trees, RealityKit and iPhone/iPad."]})
    write_json(output/"asset_manifest.json",{"id":"ENV-010","version":"v001","status":"needs_review",
        "execution_order_1_based":23,"depends":["ENV-001/v001","ENV-009/v001"],"materials":"MAT-003/v001",
        "source_hashes":{"ENV-001.blend":file_hash(ENV1/"ENV-001_terrain.blend"),"ENV-009.blend":file_hash(ridge)},
        "textures":mapping,"blender_file":f"{STEM}.blend","variants":list(local),
        "glb_files":[f"ENV-010_{name}.glb" for name in local],"blender_to_gltf_xyz":["x","z","-y"],
        "pivot_BU":[0,0,0],"checkpoint_A_BU":[0,0,0],"heading":[0,1],"layout":
         {"pitch_BU":PITCH,"section_xy_BU":[X_LO,X_HI,FRONT,EXIT],"mouth_join_y_BU":BOUNDARY,
          "shared_origin_placement":True,"envelope_width_BU":2*ENVELOPE_HALF},
        "rights":"Project-original modeled terrain and review cues, project-owned MAT-003 and ENV-009 inputs."})


if __name__ == "__main__":
    main()
