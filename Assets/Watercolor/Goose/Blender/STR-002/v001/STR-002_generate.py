"""Build the editable S4 array and prove the review footprint directly from layout JSON."""
import argparse
import json
import math
from pathlib import Path
import runpy
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.geometry import tessellate_polygon
import numpy as np

ROOT = "CurvedFarm_Layout"
BLEND = "STR-002_CurvedFarm_Layout.blend"
GLB = "STR-002_CurvedFarm_Layout.glb"
ASSET = "CurvedFarm_Layout | shared STR-001 meshes"
GUIDE = "Review only | RotorFootprint from farm_layout.json"
WET = ("ProtectedMarsh", "ProtectedMarsh_Ground", "ProtectedMarsh_Water", "ProtectedMarsh_Reeds")


def load_objects(path, names, group):
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        if not set(names).issubset(source.objects):
            raise ValueError((path, names))
        target.objects = list(names)
    result = dict(zip(names, target.objects))
    for obj in result.values():
        if obj.name not in group.objects:
            group.objects.link(obj)
    return result


def circles(data, centers=None):
    radius = data["sweep"]["radius_game_units"] * data["BU_per_game_unit"]
    return [(row["id"], Vector((centers or {})[row["id"]]).xy if centers else
             Vector(row["center_BU"]).xy, radius) for row in data["instances"]]


def build_array(scene, single, source, data):
    group = single["collection_in"](scene, ASSET)
    root = single["object_in"](group, ROOT)
    root["zone_authority"] = data["sweep"]["collision_authority"]
    root["source"] = "STR-001/v001 Main_Turbine"
    with bpy.data.libraries.load(str(source), link=False) as (_, target):
        target.collections = [single["COLLECTION"]]
    template = target.collections[0]
    def depth(obj):
        value = 0
        while obj.parent:
            obj = obj.parent
            value += 1
        return value
    objects = sorted(template.objects, key=depth)
    check = single["check"]
    rows = data["instances"]
    check(len({row["id"] for row in rows}) == len(rows) and len(rows) > 1, "Unique turbine IDs required")
    rotors = {}
    for spec in rows:
        clones = {}
        tag = spec["id"]
        for original in objects:
            duplicate = original.copy()
            group.objects.link(duplicate)
            duplicate.name = tag if original.name == single["ROOT"] else tag + "_" + original.name
            duplicate.animation_data_clear()
            duplicate.parent = clones[original.parent.name] if original.parent else root
            clones[original.name] = duplicate
        instance = clones[single["ROOT"]]
        instance.location = spec["center_BU"]
        instance.rotation_euler.z = math.radians(spec["yaw_deg"])
        instance.scale = (spec["scale"],) * 3
        instance["yaw_degrees"] = spec["yaw_deg"]
        instance["phase_degrees"] = spec["rotor_phase_deg"]
        instance["zone_reference_radius_BU"] = data["sweep"]["radius_game_units"] * data["BU_per_game_unit"]
        rotors[tag] = clones["Rotor"]
        single["animate"](rotors[tag], spec["rotor_phase_deg"], tag + "_Rotor_Constant_Loop")
    for item in list(template.objects):
        bpy.data.objects.remove(item, do_unlink=True)
    bpy.data.collections.remove(template)
    scene.frame_set(0)
    bpy.context.view_layer.update()
    return group, root, rotors


def exposed_arcs(discs):
    """Split circles only at analytic intersections and keep the outside arcs."""
    arcs = []
    for name, center, radius in discs:
        angles = [0., math.tau]
        for other, far, far_radius in discs:
            if other == name:
                continue
            d = (far - center).length
            if abs(radius - far_radius) < d < radius + far_radius:
                axis = math.atan2(far.y - center.y, far.x - center.x)
                half = math.acos((radius*radius + d*d - far_radius*far_radius) / (2*radius*d))
                angles.extend(((axis-half) % math.tau, (axis+half) % math.tau))
        for start, end in zip(sorted(angles), sorted(angles)[1:]):
            mid = (start + end) / 2
            probe = center + Vector((radius*math.cos(mid), radius*math.sin(mid)))
            if all(other == name or (probe-far).length >= far_radius-1e-6
                   for other, far, far_radius in discs):
                arcs.append((center, radius, start, end))
    return arcs


def polygon_from_arcs(arcs, max_angle):
    paths = []
    for center, r, a, b in arcs:
        count = max(1, math.ceil((b-a)/max_angle))
        paths.append([center + Vector((r*math.cos(t), r*math.sin(t)))
                      for t in np.linspace(a,b,count+1)])
    chain = paths.pop(0)
    max_join = 0
    while paths:
        index = min(range(len(paths)), key=lambda i: (paths[i][0] - chain[-1]).length)
        next_path = paths.pop(index)
        gap = (next_path[0] - chain[-1]).length
        max_join = max(gap, max_join)
        if gap >= 1e-4:
            raise ValueError(("Disconnected outline or interior hole", gap))
        chain += next_path[1:]
    closure = (chain[0] - chain[-1]).length
    if closure >= 1e-4:
        raise ValueError(("Open outline", closure))
    return chain[:-1], max(max_join, closure)


def footprint(scene, base, data, discs):
    sw = data["sweep"]
    group = bpy.data.collections.new(GUIDE)
    scene.collection.children.link(group)
    angle = math.radians(sw["render_subdivision_max_angle_degrees"])
    points, gap = polygon_from_arcs(exposed_arcs(discs), angle)
    xy = [(v.x, v.y) for v in points]
    vertices = [Vector((x,y,.012)) for x,y in xy]
    triangles = tessellate_polygon([vertices])
    # Blender exposes either element indices or input vertices depending on version.
    if triangles and isinstance(triangles[0][0], int):
        faces = [tuple(tri) for tri in triangles]
    else:
        lookup = {tuple(v): i for i,v in enumerate(vertices)}
        faces = [tuple(lookup[tuple(v)] for v in tri) for tri in triangles]
    if len(faces) != len(points)-2:
        raise ValueError(("Footprint tessellation",len(points),len(faces)))
    fill = base["paint"]("Sweep fill | muted violet", "676072")
    shader = next(n for n in fill.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    shader.inputs["Alpha"].default_value = sw["fill_opacity"]
    fill.diffuse_color[3] = sw["fill_opacity"]
    base["simple_mesh"](group, "Sweep union fill | review only", vertices, faces, fill)
    edge = base["paint"]("Sweep edge | warm slate", "77717E")
    band = []
    n = len(points)
    for i, p in enumerate(points):
        chord = (points[(i+1)%n] - points[(i-1)%n]).normalized()
        inward = Vector((-chord.y,chord.x))
        inner = p + inward * sw["outline_width_BU"]
        band.extend([(p.x,p.y,.018),(inner.x,inner.y,.018)])
    rim = base["simple_mesh"](group,"Sweep union boundary | review only", band,
                              [(2*i,2*((i+1)%n),2*((i+1)%n)+1,2*i+1) for i in range(n)], edge)
    rim["export_role"] = "technical preview, see farm_layout.json"
    rim["closed_boundary"] = True
    measurements = [min((Vector(v)-c).length-r for _,c,r in discs) for v in xy]
    midpoints = [(p + points[(i+1)%n]) / 2 for i,p in enumerate(points)]
    sagitta = max(abs(min((p-c).length-r for _,c,r in discs)) for p in midpoints)
    tol = sw["geometric_tolerance_BU"]
    if max(map(abs,measurements)) > tol or sagitta > tol:
        raise ValueError((max(map(abs,measurements)), sagitta))
    return group, points, {"closed_outer_boundary_count":1, "boundary_vertices":n,
        "fill_triangles":len(faces), "max_arc_join_error_BU":gap,
        "max_boundary_vertex_distance_error_BU":max(map(abs,measurements)),
        "max_edge_midpoint_chord_distance_error_BU":sagitta}


def glb_footprint(scene, data, base, single, discs, output):
    group, points, stats = footprint(scene, base, data, discs)
    bpy.ops.object.select_all(action="DESELECT")
    for item in group.objects:
        item.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(output / "STR-002_RotorFootprint_Review.glb"),
                              use_selection=True, export_animations=False, export_extras=True)
    return group, points, stats


def slot_offsets(spacing):
    return [Vector((0,0))] + [Vector(((-1 if i%2==0 else 1)*r,-r))
                              for i in range(11) for r in ((i//2+1)*spacing,)]


def layout_proof(data, discs, bird, terrain, landed, swift, check):
    route = data["review_route"]
    x = route["leader_x_BU"]
    y0, y1 = route["extent_y_BU"]
    west = route["western_reserved_edge_x_BU"]
    sw = data["sweep"]
    tol = sw["geometric_tolerance_BU"]
    offsets = slot_offsets(swift["rank_spacing_BU"])
    xmin = min(v.co.x for v in bird.data.vertices)
    xmax = max(v.co.x for v in bird.data.vertices)
    bird_radius = max(v.co.xy.length for v in bird.data.vertices)
    width = max(v.x for v in offsets)-min(v.x for v in offsets)+xmax-xmin
    required = width * route["width_target_flock_ratio"]
    check(abs(swift["radius_BU"] - discs[0][2]) < 1e-7, "JSON radius no longer matches Swift")
    pair_results = []
    for (a, c, r), (b, d, s) in zip(discs, discs[1:]):
        length = (c-d).length
        depth = r+s-length
        throat = 2*math.sqrt(r*r-(length/2)**2) if depth > 0 else 0
        check(depth >= sw["minimum_nearest_overlap_BU"] + tol, (a,b,depth))
        pair_results.append({"pair":[a,b],"center_distance_BU":length,
                             "overlap_axial_BU":depth,"common_chord_width_BU":throat})
    min_westmost, at_y, at_id = min((c.x-r,c.y,name) for name,c,r in discs)
    minimum = min_westmost - west
    check(y0 <= at_y <= y1 and minimum-tol >= required and
          minimum/width - route["ratio_tolerance"] >= 2, (minimum, required))
    centerline_to_west = x-west
    centerline_to_east = min_westmost-x
    check(centerline_to_west > -min(v.x for v in offsets)-xmin+tol and
          centerline_to_east > max(v.x for v in offsets)+xmax+tol, "Route does not fit the V")
    # Gate endpoints and the entire path share the same wing-conservative swept disc per slot.
    stages = [("ingress",y0,route["wetland_gate_y_BU"][0]),
              ("inside_marsh",*route["wetland_gate_y_BU"]),
              ("egress",route["wetland_gate_y_BU"][1],y1)]
    clearances = {}
    for label, start, end in stages:
        distance, name, slot = min(
            (math.hypot(c.x-x-off.x, max(start+off.y-c.y, c.y-(end+off.y), 0))-r-bird_radius,
             name, i) for name,c,r in discs for i,off in enumerate(offsets))
        check(distance > tol, (label, distance))
        clearances[label] = {"min_gap_BU":distance,"turbine":name,"bird_slot":slot}
    layers = {}
    for item in terrain:
        coords = [item.matrix_world @ v.co for v in item.data.vertices]
        x0,x1 = min(v.x for v in coords), max(v.x for v in coords)
        a,b = min(v.y for v in coords), max(v.y for v in coords)
        layers[item.name] = min(math.hypot(max(x0-c.x,c.x-x1,0),max(a-c.y,c.y-b,0))-r
                                for _,c,r in discs)
    check(min(layers.values()) > tol, layers)
    aperture = data["review_route"]["overflight_lift_game_units"] * data["BU_per_game_unit"]
    lowest_wing = aperture + 6 * data["BU_per_game_unit"] + min(v.co.z for v in bird.data.vertices)
    obstacle_top = max((ob.matrix_world @ vertex.co).z for ob in terrain for vertex in ob.data.vertices)
    check(lowest_wing - obstacle_top > tol, (lowest_wing, obstacle_top))
    landing = min(((obj.matrix_world @ v.co).xy - c).length-r
                  for obj in landed for v in obj.data.vertices for _,c,r in discs)
    check(landing > tol,landing)
    # Entire landing layout is bounded by a convex AABB for a conservative polygon certificate.
    rest_xy = [(obj.matrix_world @ v.co).xy for obj in landed for v in obj.data.vertices]
    lx,rx = min(p.x for p in rest_xy),max(p.x for p in rest_xy)
    by,ty = min(p.y for p in rest_xy),max(p.y for p in rest_xy)
    landing_aabb = min(math.hypot(max(lx-c.x,c.x-rx,0), max(by-c.y,c.y-ty,0))-r
                       for _,c,r in discs)
    check(landing_aabb > tol, landing_aabb)
    ox,oy = data["anchor"]["candidate_xy_BU"]
    gx,gy = data["anchor"]["graybox_origin_relative_game_xy"]
    scale = data["BU_per_game_unit"]
    return {"adjacent_overlap":pair_results,"conservative_landing_AABB_gap_BU":landing_aabb,
      "landing_mesh_vertex_gap_BU":landing,"landing_goose_count":len(landed),
      "wetland_layer_AABB_min_sweep_gap_BU":layers,"whole_flock_tracks":clearances,
      "whole_track_min_gap_BU":min(row["min_gap_BU"] for row in clearances.values()),
      "reused_CHR001_wingtip_X_BU":[xmin,xmax],"full_V_count":len(offsets),
      "rank_spacing_BU":swift["rank_spacing_BU"],"V_formation_width_BU":width,
      "bird_conservative_planar_radius_BU":bird_radius,
      "minimum_reserved_lane_width_BU":minimum,"minimum_at_y_BU":at_y,"limiting_turbine":at_id,
      "minimum_width_to_formation_ratio":minimum/width,"width_target_BU":required,
      "width_margin_BU":minimum-required,"geometry_tolerance_BU":tol,
      "overflight_clearance_above_marsh_geometry_BU":lowest_wing-obstacle_top,
      "ratio_tolerance":route["ratio_tolerance"],"lane_west_edge_X_BU":west,
      "route_centerline_distances_BU":{"west":centerline_to_west,"sweep":centerline_to_east},
      "anchor_relative_game_centers":{name:[gx+(c.x-ox)/scale,gy+(c.y-oy)/scale] for name,c,_ in discs}}


def context(scene, base, env, library, data, imported=False):
    art = bpy.data.collections.new("Review | ENV-016 wetland and approach")
    scene.collection.children.link(art)
    if imported:
        bpy.ops.import_scene.gltf(filepath=str(library / "ENV-016/v001/ENV-016_ProtectedMarsh.glb"))
        marsh = {name:bpy.data.objects[name] for name in WET}
        for item in marsh.values():
            if item.name not in art.objects:
                art.objects.link(item)
    else:
        marsh = load_objects(library/"ENV-016/v001/ENV-016_protected_marsh.blend", WET, art)
    wet_root = marsh[WET[0]]
    wet_root.location = data["review_route"]["wetland_root_BU"]
    flat = load_objects(library/"ENV-001/v001/ENV-001_terrain.blend", ["Flat"], art)["Flat"]
    ground = bpy.data.collections.new("Review | Same ENV-001 10 BU interfaces")
    scene.collection.children.link(ground)
    for x in range(-90,111,10):
        for y in range(-70,181,10):
            if x in env["COLS"] and y in env["ROWS"]:
                continue
            base["obj"](ground, f"Terrain {x},{y}", flat.data, (x,y,0))
    bpy.data.objects.remove(flat, do_unlink=True)
    bird = base["add_goose"](art)
    bird.name = "CHR-001 | neutral flight source"
    bird.hide_render = True
    route = data["review_route"]
    flock = [base["obj"](art, f"V flight | {i+1:02}", bird.data) for i in range(12)]
    bpy.context.view_layer.update()
    layers = [marsh[name] for name in WET[1:]]
    resting, landing = env["BASELINE"]["populate_flock"](art, layers[0])
    for obj in resting:
        obj.hide_render = True
    pads = [art, ground]
    bpy.context.view_layer.update()
    # The review surround must not introduce a second coplanar terrain surface.
    min_x,max_x,min_y,max_y = env["RECT"]
    for tile in ground.objects:
        xx, yy, _ = tile.location
        if min_x + 5 <= xx <= max_x - 5 and min_y + 5 <= yy <= max_y - 5:
            raise ValueError(("Overlapping terrain in marsh footprint", tile.name))
    return pads, layers, bird, flock, resting, landing


def route_geometry(scene, base, env, data, layers):
    group = bpy.data.collections.new("Review only | Outer lane and wetland gates")
    scene.collection.children.link(group)
    route = data["review_route"]
    y0,y1 = route["extent_y_BU"]
    x = route["leader_x_BU"]
    z = route["technical_lane_markers_z_BU"]
    terrain = env["BASELINE"]["ray_tree"]([layers[0]])
    def surface(x,y):
        found = terrain.ray_cast(Vector((x,y,2)),Vector((0,0,-1)),4)[0]
        return max(0,found.z) if found else 0
    def tone(name,color,emission=False):
        return base["paint"](name,color,emission=emission)
    pale = tone("Sage route elements","D9D6A5",True)
    outer = tone("Reserved western edge","79857A")
    vertices,faces = [],[]
    for y in np.arange(y0,y1,1.55):
        a = len(vertices)
        vertices.extend((x+dx,y+dy,z+surface(x+dx,y+dy)) for dx,dy in
                        ((-.18,-.34),(0,-.19),(.18,-.34),(0,.40)))
        faces.extend(((a,a+1,a+3),(a+1,a+2,a+3)))
    base["simple_mesh"](group,"Ongoing exterior bypass direction",vertices,faces,pale)
    for y in np.arange(y0,y1,1.6):
        west = route["western_reserved_edge_x_BU"]
        ground = surface(west,y)
        base["rectangle"](group,f"Reservation tick {y:.1f}",west-.08,west+.08,y,y+.60,z+ground,outer)
    for n, y in enumerate(route["wetland_gate_y_BU"]):
        for side in (-1,1):
            bx = x + side * 3.2
            base["rectangle"](group,f"Wetland gate {n+1}/{side}",bx-.37,bx+.37,y-.12,y+.12,
                              z+surface(bx,y),pale)
    return group


def composition(scene, base, single, env, fog, library, data, discs, imported=False):
    pads, layers, bird, flock, resting, landing = context(scene, base, env, library, data, imported)
    studio = base["studio"](scene, scene.collection)
    sky = scene.world.node_tree.nodes.get("Background")
    sky.inputs["Color"].default_value = (.68,.74,.75,1)
    sky.inputs["Strength"].default_value = .59
    vents = route_geometry(scene, base, env, data, layers)
    fog_collection = single["collection_in"](scene,"Review | ENV-018 atmosphere")
    cards = load_objects(library/"ENV-018/v001/ENV-018_atmosphere_cards.blend",fog["NAMES"],fog_collection)
    rows = fog["stage_cards"](fog_collection, cards, data["review_atmosphere"]["cards"])
    for obj in cards.values():
        bpy.data.objects.remove(obj, do_unlink=True)
    masks = {}
    for kind, item, _, _ in rows:
        image = next(n.image for n in item.data.materials[0].node_tree.nodes if n.type == "TEX_IMAGE")
        pixels = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(pixels)
        masks[kind] = pixels.reshape(image.size[1],image.size[0],4)[:,:,3]
    cam = base["camera"](studio,"Current Swift rig | fixed rear", (0,0,1),(0,1,0))
    x0,x1,y0,y1 = data["review_route"]["top_camera_bounds_BU"]
    top = base["camera"](studio,"Technical plan | full formation",
                         ((x0+x1)/2,(y0+y1)/2,110),((x0+x1)/2,(y0+y1)/2,0),x1-x0)
    return {"pads":pads,"layers":layers,"bird":bird,"flight":flock,"resting":resting,"landing":landing,
            "cam":cam,"top":top,"fog_rows":rows,"masks":masks,"studio":studio,"markers":vents}


def flight_pose(scene, stage, base, data, y, pose="flight", yaw=0, lift=0):
    route = data["review_route"]
    x = route["leader_x_BU"]
    head = Vector((math.sin(yaw),math.cos(yaw)))
    if pose=="landing":
        base["follow"](stage["cam"],(0,-3.05),head)
    else:
        base["follow"](stage["cam"],(x,y),head)
        stage["cam"].location.z += lift*data["BU_per_game_unit"]
    offsets = slot_offsets(36*data["BU_per_game_unit"])
    for i,(bird,off) in enumerate(zip(stage["flight"],offsets)):
        bx = off.x*math.cos(yaw) + off.y*math.sin(yaw)
        by = -off.x*math.sin(yaw) + off.y*math.cos(yaw)
        bird.location = (x+bx,y+by,((8 if i==0 else 6)+lift)*data["BU_per_game_unit"])
        bird.rotation_euler.z = -yaw
        bird.hide_render = pose=="landing"
    for bird in stage["resting"]:
        bird.hide_render = pose!="landing"
    bpy.context.view_layer.update()


def visibility(scene, stage, base, fog, data, discs, rotors, boundary, single):
    """Measure projected silhouette and sampled attenuation of every part of the route."""
    scene.render.resolution_x, scene.render.resolution_y = single["FRAME"]
    views = data["review_route"]["exposure_poses_y_BU"]
    settings = data["review_atmosphere"]["levels"]
    result = {}
    cam = stage["cam"]
    for mode, amount in settings.items():
        max_alpha = 0.
        visible_ids = set()
        all_counts = 0
        views_record = []
        maximum_height_by_turbine = {}
        for idx, y in enumerate(views):
            flight_pose(scene,stage,base,data,y,yaw=.28,lift=48)
            counts = {k:0 for k in ("farm","outline","route")}
            for phase in range(8):
                scene.frame_set(round(phase*single["PERIOD"]*single["FPS"]/8))
                fog["position_cards"](stage["fog_rows"], phase/8, amount)
                targets = []
                for tag, c, r in discs:
                    r_o = rotors[tag]
                    hub = r_o.matrix_world.translation
                    tips = [o.matrix_world @ max(o.data.vertices,key=lambda v:v.co.z).co
                            for o in r_o.children if "_Blade_" in o.name]
                    hub_p = world_to_camera_view(scene,cam,hub)
                    if hub_p.z>0 and .02<hub_p.x<.98 and .05<hub_p.y<.95:
                        visible_ids.add(tag)
                        size = world_to_camera_view(scene,cam,Vector((c.x,c.y,0)))
                        if size.z>0 and 0<size.y<1:
                            maximum_height_by_turbine[tag] = max(maximum_height_by_turbine.get(tag,0),
                                abs(hub_p.y-size.y)*single["FRAME"][1])
                    targets += [("farm",p) for p in [hub,*tips,Vector((c.x,c.y,.8))]]
                targets += [("outline",Vector((p.x,p.y,.022))) for p in boundary[::8]]
                targets += [("route",Vector((data["review_route"]["leader_x_BU"],p,.04)))
                            for p in np.arange(y+3,y+24,1.6)]
                for kind, p in targets:
                    q = world_to_camera_view(scene, cam, p)
                    if q.z <= 0 or not .01<q.x<.99 or not .01<q.y<.99:
                        continue
                    max_alpha=max(max_alpha,fog["blocked_alpha"](cam,p,stage["fog_rows"],stage["masks"],amount))
                    counts[kind]+=1
                    all_counts+=1
            views_record.append({"leader_y_BU":y,"visible_target_samples":counts})
        single["check"](max_alpha<=data["review_atmosphere"]["candidate_alpha_caps"][mode],
                        (mode,max_alpha,views_record))
        single["check"](len(visible_ids)==len(discs) and all(v>10 for v in maximum_height_by_turbine.values()),
                        (mode,visible_ids,maximum_height_by_turbine))
        single["check"](all(sum(v["visible_target_samples"][k] for v in views_record)>0
                            for k in ("farm","outline","route")), (mode,views_record))
        result[mode] = {"maximum_combined_alpha_at_visible_targets":max_alpha,"ray_count":all_counts,
                        "visible_hubs_across_views":sorted(visible_ids),
                        "largest_hub_to_base_height_px_by_instance":maximum_height_by_turbine,
                        "views":views_record}
    positive_row = stage["fog_rows"][0]
    original_location = positive_row[1].location.copy()
    positive_row[1].location = cam.location + Vector((0,10,.6))
    hit = positive_row[1].location + Vector((0,3,.18))
    positive = fog["blocked_alpha"](cam,hit,[positive_row],stage["masks"],1)
    positive_row[1].location = original_location
    single["check"](positive > .08, ("Fog positive control",positive))
    return {"settings":result,"eight_drift_samples_per_view":8,"positive_control_alpha":positive,
            "limits":data["review_atmosphere"]["candidate_alpha_caps"]}


def foliage_and_flight(stage, review_group, env, swift):
    """Reuse the marsh's actual seam and three-body-point clearance probes."""
    flat = next(iter(stage["pads"][1].objects))
    layers = dict(zip(WET[1:], stage["layers"]))
    # The upstream seam/ray implementation expects the original proxy. Its result supplies
    # land/reed evidence; candidate sweep distances are exclusively computed by layout_proof.
    proof = env["boundary_proof"](layers,stage["bird"],swift,flat,review_group)
    flight = proof["flight"]
    fields = ("positions","full_formation_count","fit_probe_count","minimum_static_mesh_clearance_above_ground_BU")
    return {"joined_boundary_samples":proof["connection_joins"],
            "flight_surface_probe":{k:flight[k] for k in fields},
            "all_birds_clear_of_marsh_at_ingress_BU":proof["all_birds_clear_of_marsh_at_ingress_BU"],
            "all_birds_clear_of_marsh_at_egress_BU":proof["all_birds_clear_of_marsh_at_egress_BU"],
            "landing_surface_contact":{k:stage["landing"][k] for k in
                ("goose_count","pair_count","min_hull_gap_BU","worst_foot_contact_gap_BU")}}


def gray_layers(groups, base):
    palette = [base["paint"]("Clay context "+str(i),c) for i,c in enumerate(
               ("A8A5A1","7F8B8D","666B65","BDBBB5","A0A09D","787777"))]
    swaps = []
    for group in groups:
        for o in group.objects:
            if o.type != "MESH":
                continue
            original = o.data
            gray = bpy.data.meshes.get(original.name + " | clay")
            if gray is None:
                gray = original.copy()
                gray.name = original.name + " | clay"
                part = o.name.lower()
                for idx in range(len(gray.materials)):
                    color = (1 if "water" in part else 2 if "reed" in part else
                             3+min(idx,2) if o.name.startswith("T0") else 0)
                    gray.materials[idx] = palette[color]
            o.data = gray
            swaps.append((o,original))
    return swaps


def meters_for_transforms(data, docs, group_root, single):
    check = single["check"]
    check(group_root.name == ROOT and len(group_root.children)==len(data["instances"]) and
          group_root.location.length < 1e-7 and (group_root.scale-Vector((1,1,1))).length < 1e-7,
          "Farm root transform")
    centers = {}
    errors = {}
    doc_nodes = {n["name"]:n for n in docs["nodes"]}
    for row in data["instances"]:
        tag = row["id"]
        obj = bpy.data.objects[tag]
        rotor = bpy.data.objects[tag+"_Rotor"]
        center = Vector(row["center_BU"])
        scale = row["scale"]
        yaw = math.radians(row["yaw_deg"])
        err = (obj.location-center).length
        check(obj.parent == group_root and len(obj.children_recursive)==9, (tag,"topology"))
        check(err < 3e-6 and (obj.scale-Vector((scale,)*3)).length < 3e-6, (tag,"trs"))
        q = obj.matrix_basis.to_quaternion()
        check(abs(math.remainder(q.to_euler().z-yaw,math.tau))<3e-6,(tag,"yaw"))
        check((rotor.location-Vector(single["HUB"])).length < 3e-6, (tag,"hub"))
        check((Vector(doc_nodes[tag]["translation"])-Vector((center.x,center.z,-center.y))).length<3e-6,tag)
        base = bpy.data.objects[tag+"_Foundation"]
        check(min((base.matrix_world@v.co).z for v in base.data.vertices) >= -3e-6, tag)
        centers[tag] = tuple(obj.location)
        errors[tag] = err
    return centers,errors


def check_ring_readback(data, guide_path, discs, points, single):
    doc,_ = single["glb_parts"](guide_path)
    single["check"](len(doc["meshes"])==2 and not doc.get("animations") and
                    any(m.get("alphaMode")=="BLEND" for m in doc["materials"]), "Guide GLB material")
    bpy.ops.import_scene.gltf(filepath=str(guide_path))
    edge = bpy.data.objects["Sweep union boundary | review only"]
    fill = bpy.data.objects["Sweep union fill | review only"]
    single["check"](edge["closed_boundary"] and len(fill.data.polygons)==len(points)-2, "Guide roundtrip")
    vs = [(edge.matrix_world @ v.co).xy for v in edge.data.vertices]
    missing=max(min((q-p).length for q in vs) for p in points)
    single["check"](missing<data["sweep"]["geometric_tolerance_BU"], missing)
    bpy.data.objects.remove(edge,do_unlink=True)
    bpy.data.objects.remove(fill,do_unlink=True)
    return {"max_outer_boundary_vertex_roundtrip_error_BU":missing,"triangles":len(points)-2}


def fog_pixel_comparison(folder):
    images = {}
    for name in ("default","reduced","off"):
        image = bpy.data.images.load(str(folder/f"preview_fog_{name}.png"))
        flat = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(flat)
        images[name] = flat.reshape(-1,4)[:,:3]
        bpy.data.images.remove(image)
    return {name:int((np.max(abs(images[name]-images["off"]),axis=1)>=5/255).sum())
            for name in ("default","reduced")}


def build(out, library, layout_file, single, helpers):
    base, env, fog = helpers
    data=json.loads(layout_file.read_text())
    check=single["check"]
    swift=env["runtime_inputs"]()
    scene=single["reset"]()
    scene.name="STR-002 | S4 farm and marsh review"
    source=library/"STR-001/v001"/single["BLEND"]
    group, root, rotors = build_array(scene,single,source,data)
    stage=composition(scene,base,single,env,fog,library,data,circles(data))
    guide, boundary, geo = glb_footprint(scene,data,base,single,circles(data),out)
    flight_pose(scene,stage,base,data,11.)
    shore = foliage_and_flight(stage,stage["markers"],env,swift)
    report=layout_proof(data,circles(data),stage["bird"],stage["layers"],stage["resting"],swift,check)
    materials=gray_layers([group,*stage["pads"]],base)
    fog["accessibility"](stage["fog_rows"],0)
    base["render"](scene,stage["top"],out,"graybox_top",(1020,1120),10)
    flight_pose(scene,stage,base,data,-22,yaw=.28,lift=48)
    base["render"](scene,stage["cam"],out,"graybox_fixed_rear",single["FRAME"],12)
    for item,original in materials:
        item.data=original
    bpy.ops.object.select_all(action="DESELECT")
    for item in group.objects:
        item.select_set(True)
    scene.frame_set(0)
    bpy.ops.export_scene.gltf(filepath=str(out/GLB),use_selection=True,export_extras=True,
                              export_animation_mode="SCENE",export_anim_scene_split_object=False,
                              export_nla_strips_merged_animation_name="Farm_Rotor_Loop",
                              export_anim_single_armature=False,export_frame_step=1)
    metrics=visibility(scene,stage,base,fog,data,circles(data),rotors,boundary,single)
    scene.frame_set(42)
    flight_pose(scene,stage,base,data,-22,yaw=.28,lift=48)
    for name,value in data["review_atmosphere"]["levels"].items():
        fog["accessibility"](stage["fog_rows"],value)
        fog["position_cards"](stage["fog_rows"],.125,value)
        base["render"](scene,stage["cam"],out,"preview_fog_"+name,single["FRAME"],26)
    compare = fog_pixel_comparison(out)
    check(compare["default"] > compare["reduced"] > 0, compare)
    fog["accessibility"](stage["fog_rows"],1)
    fog["position_cards"](stage["fog_rows"],.125)
    flight_pose(scene,stage,base,data,11)
    base["render"](scene,stage["top"],out,"preview_top",(1020,1120),24)
    flight_pose(scene,stage,base,data,-11,pose="landing")
    base["render"](scene,stage["cam"],out,"preview_wetland_rest",single["FRAME"],24)
    flight_pose(scene,stage,base,data,17)
    base["render"](scene,stage["cam"],out,"preview_egress",single["FRAME"],20)
    scene.frame_set(42)
    flight_pose(scene,stage,base,data,-22,yaw=.28,lift=48)
    base["set_preview_workspace"](scene,stage["cam"])
    scene.render.filepath="//preview_fog_default.png"
    bpy.ops.wm.save_as_mainfile(filepath=str(out/BLEND))
    frames=out/"frames"
    frames.mkdir()
    y0,y1=data["review_route"]["fixed_rear_motion_extent_y_BU"]
    for i,y in enumerate(np.linspace(y0,y1,48)):
        scene.frame_set(i*3)
        flight_pose(scene,stage,base,data,float(y),lift=48)
        fog["position_cards"](stage["fog_rows"], i/(8*12))
        base["render"](scene,stage["cam"],frames,f"{i:04d}",single["FRAME"],8)
    single["encode"](frames,out/"preview_fixed_rear_flight.mp4",8)
    single["write"](out/"measurements.json",{"layout":report,"wetland_checks":shore,
                      "outline":geo,"fog_visibility":metrics,"fog_pixels_delta_5_from_off":compare,"source_swift_before_array":swift})


def verify(out, delivery, library, layout_file, single, helpers):
    base,env,fog=helpers
    data=json.loads(layout_file.read_text())
    check=single["check"]
    swift=env["runtime_inputs"]()
    single["reset"]()
    bpy.ops.wm.open_mainfile(filepath=str(delivery/BLEND))
    scene=bpy.context.scene
    scene.frame_set(0)
    root=bpy.data.objects[ROOT]
    shared={name:len({bpy.data.objects[row["id"]+"_"+name].data for row in data["instances"]})
            for name in ("Foundation","Tower","Nacelle","Hub","Blade_01","Blade_02","Blade_03","Service hatch")}
    check(all(x==1 for x in shared.values()),shared)
    check(WET[0] in bpy.data.objects and "Sweep union boundary | review only" in bpy.data.objects, "Master context")
    check(abs(scene.camera.data.lens-12/math.tan(math.radians(25)))<1e-5 and
          tuple((scene.render.resolution_x,scene.render.resolution_y))==single["FRAME"], "Master camera")
    for row in data["instances"]:
        single["check_animation"](scene,bpy.data.objects[row["id"]+"_Rotor"],row["rotor_phase_deg"])
    single["reset"]()
    doc,_=single["glb_parts"](delivery/GLB)
    check(len(doc["animations"])==1 and len(doc["animations"][0]["channels"])==len(data["instances"]),
          [(a["name"],len(a["channels"])) for a in doc["animations"]])
    clip = doc["animations"][0]
    paths = {channel["target"]["path"] for channel in clip["channels"]}
    clip_nodes = {doc["nodes"][channel["target"]["node"]]["name"] for channel in clip["channels"]}
    check(paths == {"rotation"} and clip_nodes == {row["id"]+"_Rotor" for row in data["instances"]},
          (paths,clip_nodes))
    for sampler in clip["samplers"]:
        times = doc["accessors"][sampler["input"]]
        check(times["min"][0] == 0 and abs(times["max"][0] - single["PERIOD"]) < 1e-6 and
              sampler.get("interpolation","LINEAR")=="LINEAR", (times,sampler))
    master_pngs=single["image_hashes_glb"](library/"STR-001/v001"/single["GLB"])
    check(single["image_hashes_glb"](delivery/GLB)==master_pngs,"Turbine texture payload differs")
    check(len(doc["meshes"])==8,("Expected shared mesh references",len(doc["meshes"])))
    bpy.ops.import_scene.gltf(filepath=str(delivery/GLB))
    scene=bpy.context.scene
    scene.frame_set(0)
    centers,errors=meters_for_transforms(data,doc,bpy.data.objects[ROOT],single)
    roundtrip_discs=circles(data,centers)
    rotor_motion = {}
    rotors={}
    for row in data["instances"]:
        tag=row["id"]
        rotor=bpy.data.objects[tag+"_Rotor"]
        if rotor.animation_data.action is None:
            for track in rotor.animation_data.nla_tracks:
                rotor.animation_data.action=track.strips[0].action
                track.mute=True
        rotor_motion[tag]=single["check_animation"](scene,rotor,row["rotor_phase_deg"])
        rotors[tag]=rotor
    # Compare independent STR-001 GLB primitives to the array meshes, ignoring instance transforms.
    ref_doc, _ = single["glb_parts"](library/"STR-001/v001"/single["GLB"])
    def mesh_shape(gltf):
        return sorted(tuple(sorted((gltf["accessors"][p["indices"]]["count"],
                                     gltf["accessors"][p["attributes"]["POSITION"]]["count"])
                                    for p in m["primitives"])) for m in gltf["meshes"])
    check(mesh_shape(ref_doc)==mesh_shape(doc),"Array mesh/primitive sizes differ")
    src=library/"STR-001/v001"/single["BLEND"]
    for name in shared:
        with bpy.data.libraries.load(str(src),link=False) as (_, target):
            target.objects=[name]
        original = single["mesh_fingerprint"](target.objects[0])
        imported_parts = [bpy.data.objects[row["id"]+"_"+name] for row in data["instances"]]
        check(len({part.data for part in imported_parts}) == 1, (name,"imported mesh sharing"))
        check(single["mesh_fingerprint"](imported_parts[0]) == original, (name,"geometry, UV, material"))
    guide,boundary,outline=footprint(scene,base,data,roundtrip_discs)
    for guide_item in list(guide.objects):
        bpy.data.objects.remove(guide_item,do_unlink=True)
    outline_roundtrip=check_ring_readback(data,delivery/"STR-002_RotorFootprint_Review.glb",
                                        roundtrip_discs,boundary,single)
    guide,boundary,outline=footprint(scene,base,data,roundtrip_discs)
    stage=composition(scene,base,single,env,fog,library,data,roundtrip_discs,imported=True)
    proof=layout_proof(data,roundtrip_discs,stage["bird"],stage["layers"],stage["resting"],swift,check)
    shore=foliage_and_flight(stage,stage["markers"],env,swift)
    distance_deltas = {}
    source_notes=json.loads((delivery/"qa.json").read_text())["source"] if (delivery/"qa.json").is_file() else None
    if source_notes:
        for label in ("minimum_reserved_lane_width_BU","whole_track_min_gap_BU",
                      "conservative_landing_AABB_gap_BU","V_formation_width_BU"):
            distance_deltas[label] = abs(source_notes["layout"][label]-proof[label])
            check(distance_deltas[label]<data["sweep"]["geometric_tolerance_BU"],
                  (label,source_notes["layout"][label],proof[label]))
    blade_check={}
    for row in data["instances"]:
        tag=row["id"]
        rotor=rotors[tag]
        max_dist=max(math.hypot(math.hypot((blade.matrix_basis@v.co).x,(blade.matrix_basis@v.co).z),
                                rotor.location.y+(blade.matrix_basis@v.co).y)*row["scale"]
                     for blade in rotor.children if "_Blade_" in blade.name for v in blade.data.vertices)
        gap=roundtrip_discs[0][2]-max_dist
        check(gap>data["sweep"]["geometric_tolerance_BU"],(tag,gap))
        blade_check[tag]=gap
    scene.frame_set(42)
    flight_pose(scene,stage,base,data,11)
    fog["accessibility"](stage["fog_rows"],0)
    base["render"](scene,stage["top"],out,"roundtrip_wetland_array_top",(1020,1120),16)
    flight_pose(scene,stage,base,data,-22,yaw=.28,lift=48)
    base["render"](scene,stage["cam"],out,"roundtrip_fixed_rear",single["FRAME"],20)
    movie=single["decoded"](delivery/"preview_fixed_rear_flight.mp4",(852,394),48)
    single["write"](out/"recheck.json",{"result":"pass","blender":bpy.app.version_string,
        "editable_shared_meshes_per_part":shared,"glb_meshes":len(doc["meshes"]),
        "glb_center_error_BU":errors,"embedded_STR001_textures_match":True,
        "part_geometry_UV_and_material_fingerprints_match":True,
        "GLB_rotor_animation_clip":clip["name"],"GLB_rotor_channels":sorted(clip_nodes),
        "roundtrip_rotor_motion":rotor_motion,"roundtrip_analytic_blade_margin_BU":blade_check,
        "roundtrip_outline_metrics":outline,"review_only_guide_GLTF":outline_roundtrip,
        "source_to_GLTF_critical_distance_deltas_BU":distance_deltas,
        "stitched_array_marsh_layout":proof,"stitched_ENV016_surface_checks":shore,"decoded_video":movie})


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output",type=Path)
    cli.add_argument("--library",type=Path,default=Path(__file__).resolve().parents[2])
    cli.add_argument("--layout",type=Path,default=Path(__file__).with_name("farm_layout.json"))
    cli.add_argument("--verify",type=Path)
    options=cli.parse_args(sys.argv[sys.argv.index("--")+1:])
    library=options.library.resolve()
    output=options.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    single=runpy.run_path(str(library/"STR-001/v001/STR-001_generate.py"))
    single["check"](not any(output.iterdir()),"Use an independent empty directory")
    env=runpy.run_path(str(library/"ENV-016/v001/ENV-016_generate.py"))
    fog=runpy.run_path(str(library/"ENV-018/v001/ENV-018_generate.py"))
    base=env["B"]
    if options.verify:
        verify(output,options.verify.resolve(),library,options.layout.resolve(),single,(base,env,fog))
    else:
        build(output,library,options.layout.resolve(),single,(base,env,fog))
