"""Build and independently verify ENV-007 channel modules in Blender 5.2."""
import argparse
from collections import Counter
import hashlib
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
LIBRARY = HERE.parents[1]
ENV1 = LIBRARY / "ENV-001/v001"
ENV2 = LIBRARY / "ENV-002/v001"
MAT3 = LIBRARY / "MAT-003/v001"
MAT4 = LIBRARY / "MAT-004/v001"
BASE = runpy.run_path(str(ENV1 / "ENV-001_generate.py"))
check = BASE["check"]
group = BASE["collection"]
obj = BASE["obj"]
names = ("Straight", "Bend", "OpenBank")
STEM = "ENV-007_river_valley"
SIZE = 10.0
STEP = .625
LEVEL = -.18
POSITION_TOL = 1e-5
NORMAL_TOL = .03
UV_TOL = 1e-6
MATERIALS = ("GrassFlat", "MudBank", "MossStone", "ShallowMargin")
WATER = "ENV007_Water_River"
SEAMS = {"W": "L", "E": "L", "S": "R", "N": "R"}
# Coordinates are local to OpenBank, at the shared land datum.
RESCUE = (1.72, 4.55, -2.72, 2.72)
SETTLED = (3.19, 1.65)


def json_read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def hashes(root):
    return {p.relative_to(root).as_posix(): BASE["file_hash"](p)
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != "asset_manifest.json"}


def smooth(t):
    return BASE["smooth"](t)


def profile(name, y):
    """Return a complete left-to-right terrain profile with exact waterline vertices."""
    # One full station on each end shares the rail profile. This avoids a tangent kink on joins.
    fade = smooth((4.375 - abs(y)) / 1.32)
    centre = 0
    left_width, right_width = 1.39, 1.39
    if name == "Straight":
        centre = .12 * math.sin(.86 * y) * fade
        left_width += .09 * math.cos(.8 * y) * fade
        right_width -= .12 * math.cos(.7 * y) * fade
    if name == "Bend":
        centre = 1.46 * math.sin(.5 * (y + 4.375) * math.pi / 4.375) * fade
        left_width += (.12 + .2 * math.sin(.73 * y + .44)) * fade
        right_width += .22 * math.cos(.64 * y) * fade
    if name == "OpenBank":
        centre = (-1.02 + .11 * math.sin(y)) * fade
        left_width += .19 * math.cos(y * .61) * fade
        right_width -= .19 * math.cos(y * .51) * fade
    left_water, right_water = centre - left_width, centre + right_width
    left_berm, right_berm = left_water - .69, right_water + .68
    left = [-5, -4.375, (-4.375 * .59 + left_berm * .41), left_berm, left_water - .27,
            left_water, centre - left_width * .68, centre - left_width * .36]
    right = [centre + right_width * .36, centre + right_width * .68, right_water,
             right_water + .27, right_berm, (right_berm * .55 + 4.375 * .45), 4.375, 5]
    left_rise = (.095 + .08 * math.cos(y * .61 + .4)) * fade
    right_rise = 0 if name == "OpenBank" else (.021 + .011 * math.sin(y * .75)) * fade
    depths = [0, 0, left_rise, .035 * fade, -.077, LEVEL, -.390, -.535, -.545,
              -.535, -.388, LEVEL, -.077, 0, right_rise, 0, 0]
    points = list(zip(left + [centre] + right, depths))
    check(all(a[0] < b[0] for a, b in zip(points, points[1:])), (name, y, "channel profile folded over"))
    return points


def grid_triangles(rows, columns):
    for j in range(rows - 1):
        for i in range(columns - 1):
            a = j * columns + i
            b, c, d = a + 1, a + columns + 1, a + columns
            yield from ((a, b, c), (a, c, d)) if (i + j) % 2 == 0 else ((a, b, d), (b, c, d))


def build_bed(parent, name, materials):
    rows = [k * STEP - 5 for k in range(17)]
    points = [(x, y, z) for y in rows for x, z in profile(name, y)]
    bed = BASE["simple_mesh"](parent, name + "_Bed", points, list(grid_triangles(17, 17)), materials[0])
    mesh = bed.data
    for material in materials[1:]:
        mesh.materials.append(material)
    uv = mesh.uv_layers.new(name="TerrainUV")
    for face in mesh.polygons:
        i = face.index // 2 % 16
        j = face.index // 32
        face.use_smooth = True
        if i in range(5, 11):
            face.material_index = 3
        elif i in (3, 4, 11, 12):
            face.material_index = 1
        elif i in (2, 13) and j not in (0, 15):
            # Sparse moss patches follow the shoulder contours, leaving the rescue shelf quiet.
            moss = i == 2 and j % 6 in (2, 3, 4)
            moss |= i == 13 and name != "OpenBank" and (j + 3) % 7 in (3, 4)
            if moss:
                face.material_index = 2
        for loop in face.loop_indices:
            x, y, _ = points[mesh.loops[loop].vertex_index]
            uv.data[loop].uv = ((x + 5) / SIZE, (y + 5) / SIZE)
    custom = [(0, 0, 0)] * len(points)
    section = profile(name, -5)
    for index, (x, y, z) in enumerate(points):
        col = index % 17
        if col in (0, 16):
            custom[index] = (0, 0, 1)
        elif abs(y) == 5:
            left, right = section[col - 1], section[col + 1]
            slope = (right[1] - left[1]) / (right[0] - left[0])
            custom[index] = tuple(Vector((-slope, 0, 1)).normalized())
    mesh.normals_split_custom_set_from_vertices(custom)
    bed["edges_W_E_S_N"] = "L/L/R/R"
    bed["water_height_BU"] = LEVEL
    bed["grid_pitch_BU"] = SIZE
    if name == "OpenBank":
        bed["review_rescue_clear_box_XY_BU"] = RESCUE
    bed.asset_mark()
    return bed


def build_water(parent, name, material):
    vertices, uv_values = [], []
    for j in range(17):
        y = -5 + j * STEP
        ring = profile(name, y)
        left, right = ring[5][0], ring[11][0]
        for i in range(5):
            u = i / 4
            vertices.append((left + (right - left) * u, y, LEVEL))
            uv_values.append((u, j / 16))
    water = BASE["simple_mesh"](parent, name + "_Water", vertices, list(grid_triangles(17, 5)), material)
    uv = water.data.uv_layers.new(name="FlowUV")
    for loop in water.data.loops:
        uv.data[loop.index].uv = uv_values[loop.vertex_index]
    water["flow_direction_blender"] = "+Y"
    water["water_height_BU"] = LEVEL
    water.asset_mark()
    return water


def import_land_reference(parent):
    with bpy.data.libraries.load(str(ENV1 / "ENV-001_terrain.blend"), link=False) as (source, target):
        check("Flat" in source.objects, source.objects)
        target.objects = ["Flat"]
    tile = target.objects[0]
    parent.objects.link(tile)
    return tile


def shader_materials():
    terrain, terrain_map = BASE["load_materials"]()
    source = json_read(MAT4 / "asset_manifest.json")
    config = source["materials"]["Water_River"]
    original = MAT4 / config["file"]
    digest = BASE["file_hash"](original)
    check(digest == source["files"][config["file"]], "MAT-004 river PNG hash changed")
    water = bpy.data.materials.new(WATER)
    water.diffuse_color = (.37, .50, .54, .88)
    water.use_nodes = True
    water.use_backface_culling = True
    water.surface_render_method = "BLENDED"
    shader = water.node_tree.nodes["Principled BSDF"]
    shader.inputs["Roughness"].default_value = config["roughness"]
    shader.inputs["Specular IOR Level"].default_value = .21
    shader.inputs["IOR"].default_value = 1.333
    tex = water.node_tree.nodes.new("ShaderNodeTexImage")
    tex.label = "MAT-004 • Straight RGBA / repeat along stream"
    tex.extension = "REPEAT"
    tex.image = bpy.data.images.load(str(original), check_existing=False)
    tex.image.alpha_mode = "STRAIGHT"
    tex.image.pack()
    tex.image.filepath = "//../../MAT-004/v001/" + config["file"]
    water.node_tree.links.new(tex.outputs["Color"], shader.inputs["Base Color"])
    water.node_tree.links.new(tex.outputs["Alpha"], shader.inputs["Alpha"])
    water.asset_mark()
    mapping = {n: terrain_map[n] for n in MATERIALS}
    mapping[WATER] = {"sha256": digest, "path_relative_to_candidate": "../../MAT-004/v001/" + config["file"],
                      "alpha_mode": "BLEND", "dimensions": config["size"], "wrap": "repeat U/V",
                      "roughness": config["roughness"]}
    return [terrain[n] for n in MATERIALS], water, mapping


def bvh(item):
    return BVHTree.FromPolygons([v.co for v in item.data.vertices],
                               [tuple(p.vertices) for p in item.data.polygons], all_triangles=True)


def polygons(item):
    return [tuple(item.data.vertices[i].co for i in p.vertices) for p in item.data.polygons]


def outline(item):
    return [[min(v.co[i] for v in item.data.vertices), max(v.co[i] for v in item.data.vertices)]
            for i in range(3)]


def clipped(pts):
    out = []
    for a, b in zip(pts, pts[1:] + pts[:1]):
        if a.z < LEVEL + 1e-7:
            out.append(a)
        if (a.z < LEVEL + 1e-7) != (b.z < LEVEL + 1e-7):
            out.append(a.lerp(b, max(0, min(1, (LEVEL - a.z) / (b.z - a.z)))))
    return out


def projected_area(vertices):
    return abs(sum(a.x * b.y - a.y * b.x for a, b in zip(vertices, vertices[1:] + vertices[:1]))) / 2


def bed_height(tree, x, y):
    point, normal, _, _ = tree.ray_cast(Vector((max(-4.9999995,min(4.9999995,x)),
                                               max(-4.9999995,min(4.9999995,y)),2)), Vector((0,0,-1)),3)
    check(point is not None, ("missed riverbed",x,y))
    return point.z, normal


def module_geometry(name, bed, water):
    terrain = polygons(bed)
    wet = polygons(water)
    for mesh_faces in (terrain, wet):
        check(all(len(t) == 3 and (t[1] - t[0]).cross(t[2] - t[0]).z > 0 for t in mesh_faces), name)
    bounds = outline(bed)
    check(bounds[:2] == [[-5.0,5.0],[-5.0,5.0]], bounds)
    check(abs(sum(projected_area(t) for t in terrain) - 100) < 1e-5, name)
    expected = sum(projected_area(clipped(t)) for t in terrain)
    area = sum(projected_area(t) for t in wet)
    check(abs(expected - area) < 1e-5, (name, expected, area))
    tree = bvh(bed)
    sample_points = [v.co.copy() for v in water.data.vertices] + [p.center for p in water.data.polygons]
    path = [bed_height(tree, point.x, point.y)[0] for point in sample_points]
    clearance = [point.z - depth for point, depth in zip(sample_points,path)]
    check(min(clearance) >= -1e-6 and all(abs(point.z - LEVEL) <= 1e-6 for point in sample_points), name)
    deepest = max(clearance)
    check(deepest > .30, (name, "river too shallow for sample"))
    # Width, lateral connectivity, and absence of dry islands are checked across 65 cross sections.
    widths, all_profiles = [], []
    for j in range(65):
        y = -5 + j / 64 * 10
        distances = [i / 160 * 10 - 5 for i in range(161)]
        statuses = [bed_height(tree,x,y)[0] < LEVEL - 1e-5 for x in distances]
        transitions = sum(a != b for a,b in zip(statuses, statuses[1:]))
        check(transitions == 2 and not statuses[0] and not statuses[-1], (name, y, transitions))
        active = [x for x,wetness in zip(distances,statuses) if wetness]
        widths.append(active[-1] - active[0])
        all_profiles.append([round(y,5),len(active)])
    return {
        "bed_triangles":len(terrain), "water_triangles":len(wet), "bed_bounds_XYZ_BU":bounds,
        "bed_vertices":len(bed.data.vertices), "water_vertices":len(water.data.vertices),
        "water_area_BU2":area, "terrain_clipping_area_difference_BU2":abs(area-expected),
        "water_plane_elevation_BU":LEVEL,"min_water_vertex_and_face_centroid_clearance_BU":min(clearance),
        "max_bed_depth_BU":deepest,"waterbed_sample_points":len(sample_points),
        "channel_width_X_estimated_BU":[min(widths),max(widths)], "width_sample_spacing_BU":.0625,
        "cross_sections_one_wet_interval_connected_to_ends":len(all_profiles),
    }


def rescue_geometry(bed, water):
    tree = bvh(bed)
    xmin, xmax, ymin, ymax = RESCUE
    waterline = [tuple(p) for p in polygons(water)]
    boundary = Counter(tuple(sorted((tuple(a),tuple(b)))) for tri in waterline
                       for a,b in zip(tri,tri[1:] + tri[:1]))
    bank = [(Vector(a).xy,Vector(b).xy) for (a,b), count in boundary.items() if count == 1]
    distances, heights, slope = [], [], []
    for i in range(22):
        x = xmin + (xmax - xmin) * i / 21
        for j in range(40):
            y = ymin + (ymax - ymin) * j / 39
            z, norm = bed_height(tree,x,y)
            heights.append(z)
            slope.append(math.degrees(math.acos(min(1,norm.z))))
            v = Vector((x,y))
            distances.append(min((v - (a + (b - a)*max(0,min(1,(v-a).dot(b-a)/(b-a).length_squared)))).length
                                 for a,b in bank))
    # At the east bank, both ends reach the rectangle and adjacent terrain along dry ground.
    approach = [(3.20, y) for y in (-5,-4.25,-3.5,-2.72,2.72,3.5,4.25,5)]
    approach.extend((x,0.) for x in (4.55,4.67,4.79,4.91,5.0))
    corridor_probes = []
    for start,end in ((approach[0],approach[3]),(approach[4],approach[7]),(approach[8],approach[-1])):
        for i in range(41):
            x,y = Vector(start).lerp(Vector(end),i/40)
            corridor_probes.append(bed_height(tree,x,y)[0]-LEVEL)
    minimum = min(distances)
    check(minimum > .37 and min(heights) >= -1e-6 and max(slope)<3
          and min(corridor_probes) > .16,(minimum,min(heights),max(slope),min(corridor_probes)))
    return {"openbank_local_xy_BU":list(RESCUE),
            "width_BU":xmax-xmin,"length_BU":ymax-ymin,"clear_area_BU2":(xmax-xmin)*(ymax-ymin),
            "surface_probes":len(heights),"height_range_BU":[min(heights),max(heights)],
            "max_floor_slope_deg":max(slope),"min_distance_to_waterline_BU":minimum,
            "dry_approach_probe_count":len(corridor_probes),"min_approach_height_above_water_BU":min(corridor_probes)}


def edge_info(item, side):
    across = side in {"S", "N"}
    axis = 1 if across else 0
    wanted = 5 if side in {"E", "N"} else -5
    result = {}
    mesh = item.data
    uvs = mesh.uv_layers.active.data
    for loop in mesh.loops:
        point = mesh.vertices[loop.vertex_index].co
        if abs(wanted - point[axis]) >= 1e-6:
            continue
        coord = round(point[1 - axis], 5)
        result.setdefault(coord, []).append((point.copy(), mesh.corner_normals[loop.index].vector.copy(),
                                             uvs[loop.index].uv.copy()))
    return result


def fit(first, second, sides, offset):
    a, b = (edge_info(mesh, side) for mesh,side in zip((first,second),sides))
    check(list(sorted(a)) == list(sorted(b)), (first.name,second.name,sides,sorted(a),sorted(b)))
    check(len(a) in (5,17), (first.name,sides,len(a)))
    all_gaps = [(float((v - w - offset).length), BASE["angle"](n,m),
                 max(abs(x - round(x)) for x in t - s))
                for key in a for v,n,t in a[key] for w,m,s in b[key]]
    position, normal, uv = (max(row[k] for row in all_gaps) for k in range(3))
    check(position <= POSITION_TOL and normal <= NORMAL_TOL and uv <= UV_TOL,
          (first.name, second.name, sides, position, normal, uv))
    return {"first":first.name.rsplit(".",1)[0], "second":second.name.rsplit(".",1)[0],
            "edges":list(sides), "vertices_per_edge":len(a),"max_position_error_BU":position,
            "max_normal_delta_deg":normal,"max_wrapped_UV_error":uv}


def check_joins(modules, flat):
    river, cross = Vector((0,10,0)),Vector((10,0,0))
    all_joins = []
    for a, (bed_a, water_a) in modules.items():
        for b, (bed_b, water_b) in modules.items():
            all_joins.append({"pair":[a,b],"bed":fit(bed_a,bed_b,("N","S"),river),
                              "water":fit(water_a,water_b,("N","S"),river)})
    sides = [{"variant":name, "west":fit(flat,bed,("E","W"),cross),
              "east":fit(bed,flat,("E","W"),cross)}
             for name,(bed,_) in modules.items()]
    return {"ordered_R_pairs":all_joins, "L_matches_to_ENV001_Flat":sides}


def mesh_signature(item):
    mesh = item.data
    uvs = mesh.uv_layers.active.data
    face_data = {}
    for face in mesh.polygons:
        coordinates = []
        payload = []
        for loop in face.loop_indices:
            vertex = mesh.vertices[mesh.loops[loop].vertex_index].co
            uv = uvs[loop].uv
            coordinates.append(tuple(round(x,6) for x in vertex))
            payload.append((uv.copy(), mesh.corner_normals[loop].vector.copy()))
        first = min(range(3), key=lambda i:coordinates[i])
        connected = tuple(coordinates[first:] + coordinates[:first])
        check(connected not in face_data, (item.name, "duplicate terrain face"))
        label = mesh.materials[face.material_index].name.split(".")[0]
        face_data[connected] = (label,payload[first:] + payload[:first])
    return face_data


def compare_mesh(source, incoming):
    expected = mesh_signature(source)
    actual = mesh_signature(incoming)
    check(expected.keys() == actual.keys(), (source.name,len(expected),len(actual),"triangle topology changed"))
    normal_error, uv_error = 0, 0
    for key,(name,corners) in expected.items():
        taken_name,taken = actual[key]
        check(name == taken_name, (source.name,name,taken_name))
        for (a,n),(b,m) in zip(corners,taken):
            uv_error = max(uv_error, float((a-b).length))
            normal_error = max(normal_error, BASE["angle"](n,m))
    check(normal_error < .10 and uv_error < UV_TOL, (source.name,normal_error,uv_error))
    return {"max_corner_normal_delta_deg":normal_error,"max_corner_uv_error":uv_error,
            "triangles_matched_by_ordered_XYZ":len(expected)}


def glb_info(path, name, originals, material_map):
    data, blob = BASE["glb_chunks"](path)
    check(not data.get("animations") and not data.get("cameras") and len(data["nodes"]) == 2,path.name)
    check({n["name"] for n in data["nodes"]} == {name+"_Bed",name+"_Water"},path.name)
    a,b = originals
    by_name = {a.name:a,b.name:b}
    for node in data["nodes"]:
        check(node.get("translation",[0,0,0]) == [0,0,0] and node.get("scale",[1,1,1]) == [1,1,1]
              and node.get("rotation",[0,0,0,1]) == [0,0,0,1],node)
        primitives = data["meshes"][node["mesh"]]["primitives"]
        expected = set(tuple(round(x,5) for x in (v.co.x,v.co.z,-v.co.y))
                       for v in by_name[node["name"]].data.vertices)
        raw_positions = set()
        for primitive in primitives:
            check(primitive.get("mode",4) == 4,(node,primitive))
            attributes = primitive["attributes"]
            check({"POSITION","NORMAL","TEXCOORD_0"} <= attributes.keys(),(node,attributes))
            accessor = data["accessors"][attributes["POSITION"]]
            view = data["bufferViews"][accessor["bufferView"]]
            check(accessor["componentType"] == 5126 and accessor["type"] == "VEC3",node)
            start = view.get("byteOffset",0) + accessor.get("byteOffset",0)
            stride = view.get("byteStride",12)
            raw_positions.update(tuple(round(v,5) for v in struct.unpack_from("<3f",blob,start+i*stride))
                                 for i in range(accessor["count"]))
        check(raw_positions == expected,(node, "Y-up/-Z-forward conversion"))
    checks = {}
    for m in data["materials"]:
        label = m["name"]
        expected = material_map[label]
        tex = data["textures"][m["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
        sampler = data.get("samplers",[])[tex["sampler"]] if "sampler" in tex else {}
        image = data["images"][tex["source"]]
        view = data["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset",0)
        rgb = hashlib.sha256(blob[start:start + view["byteLength"]]).hexdigest()
        alpha = m.get("alphaMode","OPAQUE")
        check(alpha == expected.get("alpha_mode","OPAQUE") and rgb == expected["sha256"],(path.name,label,alpha,rgb))
        check(sampler.get("wrapT",10497)==10497,(path.name,label,sampler))
        checks[label] = {"embedded_png_sha256":rgb,"alpha_mode":alpha,"repeat_V":True}
    return checks


def import_roundtrip(folder, originals, mapping):
    imports, report = {}, {}
    for name, source in originals.items():
        path = folder / f"ENV-007_{name}.glb"
        details = glb_info(path,name,source,mapping)
        old = set(bpy.data.objects)
        result = bpy.ops.import_scene.gltf(filepath=str(path),merge_vertices=False,import_pack_images=True)
        check(result == {"FINISHED"}, path.name)
        items = sorted(set(bpy.data.objects)-old,key=lambda a:a.name)
        check(len(items)==2 and all(item.type=="MESH" for item in items),path.name)
        bed, water = items
        check(bed.name.split(".")[0] == name+"_Bed" and water.name.split(".")[0]==name+"_Water",path.name)
        measure = module_geometry(name,bed,water)
        comparisons = {"bed":compare_mesh(source[0],bed),"water":compare_mesh(source[1],water)}
        report[name] = {"mesh":measure,"comparisons":comparisons,"material_readback":details}
        imports[name] = (bed,water)
        for item in items:
            item.hide_render = True
            item.hide_set(True)
    return imports,report


def load_preview_plants(parent):
    reeds = LIBRARY/"ENV-004/v001/ENV-004_reeds.blend"
    grasses = LIBRARY/"ENV-006/v001/ENV-006_grass.blend"
    plants = []
    for variant, path in ((["Reed_A_Height_S","Reed_B_Height_S"],reeds),
                          (["Grass_A","Grass_B","Grass_C"],grasses)):
        with bpy.data.libraries.load(str(path),link=False) as (a,b):
            check(all(n in a.objects for n in variant),(path,a.objects))
            b.objects = variant
        plants.extend(b.objects)
    for plant in plants:
        parent.objects.link(plant)
        plant.hide_render = True
        plant.hide_set(True)
    return plants


def scatter_preview(scene,parent,modules):
    selected = load_preview_plants(parent)
    root = group("Review • Grass silhouettes on outer slopes",scene.collection)
    clips = {}
    counts = 0
    left = [(y, -3.06-.46*math.sin(y*.7)+.22*math.cos(y*2.51)) for y in
            [-13.2,-12.7,-11.8,-10.9,-10.18,-8.3,-6.7,-6.22,-4.64,-2.9,-.14,.52,1.13,2.96,5.64,
             6.48,7.3,8.42,10.37,10.91,11.28,12.97,14.59,15.26,16.34,16.72,17.4,18.28,19.24,21.41]]
    right = [(y, 2.78 + .75*math.sin(y*.73)) for y in [-12.8,-12.4,-10.1,-7.25,-6.54,-3.8,-2.21,
             -1.54,.73,1.32,2.03,3.8,4.65,5.15,6.12,14.65,15.64,16.92,18.71,19.15,21.04]]
    for i,(y,x) in enumerate(left+right):
        slot = math.floor((y+5)/10)
        key = {-1:"Straight",0:"Bend",1:"OpenBank",2:"Straight"}[slot]
        bed = modules[key][0]
        if key not in clips:
            clips[key] = bvh(bed)
        local_y = y-slot*10
        z = bed_height(clips[key],x,local_y)[0]
        if z < .005 or (slot == 1 and x > 0 and local_y > -3.28 and local_y < 3.28):
            continue
        if i % 13 == 3:
            proto = selected[i % 2]
            size = .56
        else:
            proto = selected[2+i%3]
            size = .67 + .21*math.cos(i*2.21)
        plant = obj(root, f"Review bank grass {i:02}",proto.data,(x,y,z-.009))
        plant.rotation_euler[2] = i*1.71
        plant.scale = (size,size,size)
        counts += 1
    return counts


def support_bird(parent, bed, show_color=True):
    # Use the existing ANM-007 candidate pose and the same ENV-002 foot-contact solver.
    GEOM2 = runpy.run_path(str(ENV2/"ENV-002_generate.py"))
    standing, points, sole = GEOM2["load_standing_mesh"](parent)
    valid, record = GEOM2["place"](bvh(bed), points, sole, SETTLED, -.27, .8)
    check(valid is not None, record)
    bird = obj(parent,"Review • Tail goose on accessible bank",standing,
               (SETTLED[0], SETTLED[1] + 10, record["root_z_BU"]))
    bird.rotation_euler.z = -.27
    bird.scale = (.8,.8,.8)
    if not show_color:
        neutral = BASE["paint"]("Standing bird • Graybox bronze","A59276")
        for idx in range(len(bird.data.materials)):
            bird.data.materials[idx] = neutral
    return bird,record


def scene_geometry(scene, modules, flat, gray, extended):
    set_group = group("Review • 10 BU river connectors",scene.collection)
    beds = []
    stops = ((-1,"Straight"),(0,"Bend"),(1,"OpenBank"))
    for row,name in stops:
        bed,water = modules[name]
        beds.append(obj(set_group,name+" assembled bed",bed.data,(0,row*10,0)))
        obj(set_group,name+" assembled water",water.data,(0,row*10,0))
    rows = range(-3,12) if extended else range(-1,2)
    if extended:
        for row in (-3,-2,2,3,4,5,6,7,8,9,10,11):
            name = {2:"Straight",3:"Bend",4:"OpenBank"}.get(row,"Straight")
            bed,water = modules[name]
            beds.append(obj(set_group,f"Context • Riverbed {row}",bed.data,(0,row*10,0)))
            obj(set_group,f"Context • River water {row}",water.data,(0,row*10,0))
    for row in rows:
        for side in range(-5,6) if extended else (-1,1):
            if side:
                obj(set_group,f"Context • ENV-001 Flat {side},{row}",flat.data,(side*10,row*10,0))
    frame = BASE["paint"]("Review • Backdrop","C5CDBE") if not gray else BASE["paint"]("Review • Backdrop","777D82")
    BASE["rectangle"](set_group,"Review • horizon ground",-105,105,-110,220,-.61,frame)
    return set_group,beds


def route_overlay(parent):
    mat = BASE["paint"]("Review • Path colour","DEBC76",emission=True)
    vert,faces=[],[]
    for i in range(39):
        y = -7.6 + i * .47
        x = 3.84 - .56*smooth((y - 4.1)/5.1) - .12*math.cos(y*.49)
        idx = len(vert)
        for dx,dy in ((-.066,-.104),(.066,-.104),(.066,.104),(-.066,.104)):
            vert.append((x+dx,y+dy,.036))
        faces.append((idx,idx+1,idx+2,idx+3))
    return BASE["simple_mesh"](parent,"Review • Sample approach",vert,faces,mat)


def rendered_rescue_check(scene, cam, tail, beds, label):
    bpy.context.view_layer.update()
    x0,x1,y0,y1=RESCUE
    vertices = [Vector((x,y+10,.018)) for x,y in ((x0,y0),(x1,y0),(x0,y1),(x1,y1))]
    projections = [world_to_camera_view(scene,cam,v) for v in vertices]
    centre = world_to_camera_view(scene,cam,tail.location + Vector((0,0,.1)))
    check(all(0 < co.x < 1 and 0 < co.y < 1 and co.z > 0 for co in projections+[centre]),
          (label,projections,centre))
    world_verts,faces=[],[]
    for item in beds:
        base = len(world_verts)
        world_verts.extend(item.matrix_world @ v.co for v in item.data.vertices)
        faces.extend(tuple(base+i for i in p.vertices) for p in item.data.polygons)
    tree = BVHTree.FromPolygons(world_verts,faces,all_triangles=True)
    tests = [tail.location + Vector((0,0,.1))]
    tests.extend(Vector((x,y + 10,.018)) for x in (1.88,3.16,4.39) for y in (-2.5,0,2.5))
    for p in tests:
        delta = p-cam.location
        hit,*_ = tree.ray_cast(cam.location,delta.normalized(),delta.length-.003)
        check(hit is None,(label,"terrain obscures rescue area",p,hit))
    corners = [[float(co.x*852),float((1-co.y)*393)] for co in projections]
    return {"cases":len(tests),"rescue_corner_pixels_XY":corners,
            "tail_goose_centre_pixels_XY":[float(centre.x*852),float((1-centre.y)*393)]}


def gallery(scene, modules, flat, folder, prefix, gray=False):
    root,beds = scene_geometry(scene,modules,flat,gray,extended=True)
    overlays = group("Review • Approach and tail goose",root)
    route_overlay(overlays)
    leader = BASE["add_goose"](overlays)
    tail,pose = support_bird(overlays,modules["OpenBank"][0],show_color=not gray)
    scatter_count = scatter_preview(scene,overlays,modules) if not gray else 0
    rigs = BASE["studio"](scene,scene.collection)
    light = next(o for o in rigs.objects if o.type == "LIGHT")
    light.rotation_euler = Vector((.29,.37,-1)).to_track_quat("-Z","Y").to_euler()
    top = BASE["camera"](rigs,"River fittings • Top",(0,0,48),(0,0,0),25)
    cam = BASE["camera"](rigs,"Game fixed 180 / 0.48 / 50",(0,0,1),(0,1,0))
    side = BASE["camera"](rigs,"OpenBank close study",(6.4,6.0,4.1),(1.74,9.9,.0),11.9)
    BASE["pose_at"](cam,leader,(3.52,3.5),Vector((-.01,.99995)).normalized())
    frame = rendered_rescue_check(scene,cam,tail,beds,"rescue_approach")
    BASE["render"](scene,cam,folder,prefix+"_fixed_rear",BASE["GAME_SIZE"],18)
    overlays.hide_render = True
    BASE["render"](scene,top,folder,prefix+"_top",(840,1134),14)
    overlays.hide_render = False
    if not gray:
        BASE["render"](scene,side,folder,prefix+"_open_bank",(1000,600),18)
        BASE["pose_at"](cam,leader,(3.71,-6.1),Vector((-.02,.9998)).normalized())
        BASE["render"](scene,cam,folder,prefix+"_bend_approach",BASE["GAME_SIZE"],15)
        BASE["pose_at"](cam,leader,(3.52,3.5),Vector((-.01,.99995)).normalized())
    BASE["set_preview_workspace"](scene,cam)
    scene.render.filepath = "//review.png"
    return {"rescue_approach":frame,"landed_tail_goose":pose,"review_only_plant_instances":scatter_count}


def glb_export(folder,modules,scene):
    bpy.context.window.scene = scene
    for name,items in modules.items():
        bpy.ops.object.select_all(action="DESELECT")
        for item in items:
            item.select_set(True)
        bpy.context.view_layer.objects.active = items[0]
        result = bpy.ops.export_scene.gltf(filepath=str(folder/f"ENV-007_{name}.glb"),
                    export_format="GLB",use_selection=True,export_yup=True,export_extras=True,export_animations=False)
        check(result == {"FINISHED"},(name,result))


def review(directory, source_library, modules, flat, prefix, gray):
    scene = BASE["fresh_scene"](prefix+" | Rivers")
    result = gallery(scene,modules,flat,directory,prefix,gray)
    if gray:
        bpy.context.window.scene = source_library
        bpy.data.scenes.remove(scene)
    return result


def run_build(folder, geometry_only=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.preferences.filepaths.temporary_directory = str(folder)
    library = bpy.context.scene
    library.name = "ENV-007 | Source objects at origin"
    library.unit_settings.system = "NONE"
    export_group = group("ENV-007 • Toggle variants",library.collection)
    props = group("ENV-001 • Terrain side connector",library.collection)
    source_flags = [BASE["paint"]("Graybox "+n,c) for n,c in
                    zip(MATERIALS,("9EA6A4","A29785","919990","839D9B"))]
    gray_water = BASE["paint"]("Graybox water","789499")
    # Graybox geometry and fitting checks run before sourcing any production materials.
    modules = {}
    for name in names:
        root = group(name+" | 10×10 BU",export_group)
        modules[name] = (build_bed(root,name,source_flags),build_water(root,name,gray_water))
    flat = import_land_reference(props)
    flat_materials = {material.name:material for material in flat.data.materials}
    flat.data.materials[0] = source_flags[0]
    bpy.context.view_layer.update()
    gray_metrics = {n:module_geometry(n,*p) for n,p in modules.items()}
    joins = check_joins(modules,flat)
    dry = rescue_geometry(*modules["OpenBank"])
    print("GRAYBOX OK",dry,flush=True)
    if geometry_only:
        BASE["write_json"](folder/"graybox_measurements.json",{"modules":gray_metrics,"joins":joins,"rescue":dry})
        return
    gray_review = review(folder,library,modules,flat,"graybox",True)
    # Retain the actual ENV-001 tile material for matching the outer land edge.
    flat.data.materials[0] = flat_materials["GrassFlat"]
    terrain,water,mapping = shader_materials()
    terrain = [flat_materials.get(name, material) for name,material in zip(MATERIALS,terrain)]
    for bed,surface in modules.values():
        for i,material in enumerate(terrain):
            bed.data.materials[i] = material
        surface.data.materials[0] = water
    for material in terrain:
        texture = next(n for n in material.node_tree.nodes if n.type == "TEX_IMAGE")
        check(hashlib.sha256(texture.image.packed_file.data).hexdigest()==mapping[material.name]["sha256"],
              (material.name,"ENV-001 texture no longer matches MAT-003"))
    glb_export(folder,modules,library)
    flat.hide_set(True)
    flat.hide_render = True
    arts_review = review(folder,library,modules,flat,"preview",False)
    bpy.context.scene.name = "ENV-007 | River fitting + fixed rear review"
    bpy.ops.wm.save_as_mainfile(filepath=str(folder/f"{STEM}.blend"))
    retry_scene = BASE["fresh_scene"]("Independent GLB import • River fitting")
    incoming,report = import_roundtrip(folder,modules,mapping)
    retry_joins = check_joins(incoming,flat)
    retry_dry = rescue_geometry(*incoming["OpenBank"])
    scene_geometry(retry_scene,incoming,flat,False,extended=True)
    rigs = BASE["studio"](retry_scene,retry_scene.collection)
    light = next(o for o in rigs.objects if o.type == "LIGHT")
    light.rotation_euler = Vector((.29,.37,-1)).to_track_quat("-Z","Y").to_euler()
    top = BASE["camera"](rigs,"GLB fitting • Top",(0,0,48),(0,0,0),25)
    BASE["render"](retry_scene,top,folder,"preview_glb_roundtrip",(840,1134),14)
    inputs = {
        "ENV-001_terrain.blend":ENV1/"ENV-001_terrain.blend",
        "ENV-001_generate.py":ENV1/"ENV-001_generate.py",
        "MAT-003_wetland_rock.blend":MAT3/"MAT-003_wetland_rock.blend",
        "MAT-004_water_surfaces.blend":MAT4/"MAT-004_water_surfaces.blend",
        "ENV-002_generate.py (review only)":ENV2/"ENV-002_generate.py",
        "ANM-007_landing.blend (review only)":LIBRARY/"ANM-007/v001/ANM-007_landing.blend",
        "ENV-004_reeds.blend (review only)":LIBRARY/"ENV-004/v001/ENV-004_reeds.blend",
        "ENV-006_grass.blend (review only)":LIBRARY/"ENV-006/v001/ENV-006_grass.blend",
    }
    manifest = {
        "id":"ENV-007","version":"v001","status":"needs_review","blender":bpy.app.version_string,
        "execution_order_1_based":20,"production_spec_page":10,"levels":["S2","S3","S5"],
        "depends":["ENV-001/v001","MAT-004/v001"], "material_inputs":["MAT-003/v001","MAT-004/v001"],
        "blender_file":STEM+".blend","module_pitch_BU":SIZE,"axis_map_xyz_to_gltf":["x","z","-y"],
        "centre_pivot_local_BU":[0,0,0],"translation_stride_BU":[10,10],"rotation_qualified_deg":0,
        "edge_types":SEAMS,"water_level_local_z_BU":LEVEL,
        "water_flow_UV":["U across the channel from left to right","V along +Y with period 10 BU"],
        "R_profile_station_xz_BU":profile("Straight",-5),
        "variants":{name:{"file":f"ENV-007_{name}.glb","nodes":[i.name for i in modules[name]],
                         "bed_triangles":gray_metrics[name]["bed_triangles"],
                         "water_triangles":gray_metrics[name]["water_triangles"]} for name in names},
        "source_hashes":{n:BASE["file_hash"](p) for n,p in inputs.items()},"images":mapping,
        "source_notes":"Original geometry; environment inputs and materials retain their existing candidate states.",
    }
    qa = {
        "id":"ENV-007","version":"v001","status":"needs_review","graybox_before_materials":gray_metrics,
        "source_joins":joins,"source_rescue":dry,"graybox_camera":gray_review,
        "material_camera":arts_review,"glb_roundtrip":{"modules":report,"joins":retry_joins,"rescue":retry_dry},
        "tolerances":{"seam_position_BU":POSITION_TOL,"seam_normal_deg":NORMAL_TOL,
                      "wrapped_UV":UV_TOL,"terrain_vs_surface_area_BU2":1e-5,
                      "plane_and_intrusion_BU":1e-6,"roundtrip_corner_normal_deg":.1},
        "source_rig":{"distance_game_units":180,"pitch_radians":.48,"vertical_fov_degrees":50,
                      "target_height_game_units":6,"flight_height_game_units":8,"game_units_per_BU":BASE["SCALE"],
                      "fixed_rear_preview_px":BASE["GAME_SIZE"]},
        "application_baseline":{"record":"plans/active/goose-preview-model-cleanup.md",
                                "simulator":"iPhone 18 Pro","os":"iOS 27.2","prior_test_count":340,
                                "rerun_this_task":False},
        "design_redline_review":"Pass for candidate geometry and offline preview only.",
        "pending":["S3 runtime rescue target and landing logic", "RealityKit water sorting, USDZ, FX-006",
                   "Visual acceptance", "iPhone / iPad device verification"],
    }
    BASE["write_json"](folder/"qa.json",qa)
    manifest["files"] = hashes(folder)
    BASE["write_json"](folder/"asset_manifest.json",manifest)


def run_verify(candidate, folder):
    manifest = json_read(candidate/"asset_manifest.json")
    check(hashes(candidate)==manifest["files"],"candidate files do not match manifest")
    bpy.ops.wm.open_mainfile(filepath=str(candidate/f"{STEM}.blend"))
    qa = json_read(candidate/"qa.json")
    source = {name:tuple(bpy.data.objects[name+s] for s in ("_Bed","_Water")) for name in names}
    flat = bpy.data.objects["Flat"]
    BASE["fresh_scene"]("ENV-007 | Readback checks from saved candidate")
    incoming,report = import_roundtrip(candidate,source,manifest["images"])
    joins = check_joins(incoming,flat)
    rescue = rescue_geometry(*incoming["OpenBank"])
    result = json.loads(json.dumps({"modules":report,"joins":joins,"rescue":rescue}))
    check(result == qa["glb_roundtrip"],"independent delivered candidate changed")
    BASE["write_json"](folder/"recheck.json",{"result":"pass",**result})
    print("Independent reopen and all three GLB roundtrips passed.",flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--geometry-only",action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    folder = args.output.resolve()
    folder.mkdir(parents=True,exist_ok=True)
    check(not any(folder.iterdir()),f"Use an empty temporary output directory: {folder}")
    if args.verify:
        run_verify(args.verify.resolve(),folder)
    else:
        run_build(folder,args.geometry_only)


if __name__ == "__main__":
    main()
