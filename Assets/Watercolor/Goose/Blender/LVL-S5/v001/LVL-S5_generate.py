"""Assemble the S5 headwind candidate and independently verify the delivered Blender/GLB."""
import argparse
import hashlib
import json
import math
import random
from pathlib import Path
import struct
import subprocess
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ID = "LVL-S5"
VARIANT = "S5_Headwind"
BLEND = ID + "_" + VARIANT + ".blend"
GLB = ID + "_" + VARIANT + ".glb"
VIDEO = "preview_fixed_rear.mp4"
LIBRARY = "Assets/Watercolor/Goose/Blender"
RIG_SOURCE = "Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift"
SIZE = (852, 393)
FPS = 24
STEP = 4
END = 197
SCALE = .036
WATER = -.18
LAND_HALF = 22
RIVER_X = -2.5
RIVER = (("Straight", 17), ("OpenBank", 27), ("OpenBank", 37), ("Bend", 47))
PROFILE = (
    (-5, 0), (-4.375, 0), (-3.43405, 0), (-2.08, 0), (-1.66, -.077),
    (-1.39, -.18), (-.9452, -.39), (-.5004, -.535), (0, -.545),
    (.5004, -.535), (.9452, -.388), (1.39, -.18), (1.66, -.077),
    (2.07, 0), (3.10725, 0), (4.375, 0), (5, 0),
)
REST = (4.55, 33.4, 0)
WEST_GATE = (-12, 12)
ANCHORS = {
    "S5_Entry": (0, 0, 0),
    "S5_LowEnergySample": (0, 28.8, .556),
    "S5_SafeApproach": (1, 28.2, .6),
    "S5_SafeRest": REST,
    "S5_SafeReturn": (1.5, 43.6, .65),
    "S5_ExitApproach": (0, 57, .65),
    "S5_Exit": (0, 64, 0),
}
ROUTES = {
    "direct": ((0,0,.65), (0,15,.65), (0,31,.7), (0,49,.7), (0,64,.65)),
    "safe_detour": ((0,22,.65), (0,27,.65), (1,29,.65), (3,31,.65),
                    (4.55,33.4,.65), (4.6,37.6,.65), (3.1,40.4,.65),
                    (1.5,43.6,.65), (0,49,.65), (0,64,.65)),
}
FLOCK = ((0, 0), (-1.12, -1.5), (1.12, -1.5), (-2.25, -3.05), (2.25, -3.05),
         (-3.38, -4.6), (3.38, -4.6), (-4.5, -6.15), (4.5, -6.15),
         (-5.62, -7.7), (5.62, -7.7), (-6.72, -9.25))
WIND = ((-6.9, .47), (-6.25, .56), (-5.42, .51), (-4.52, .47), (-3.66, .52), (-2.77, .52),
        (6.3, .54), (6.92, .51), (7.62, .6), (8.45, .45), (9.15, .55), (10.3, .52))
WIND_PERIOD = 8.4
WIND_SPEED = 2.55
WIND_TILES_PER_LANE = 4
DEPS = {
    "ENV-007": ("ENV-007_river_valley.blend", "ENV-007_Straight.glb", "ENV-007_OpenBank.glb", "ENV-007_Bend.glb"),
    "ENV-009": ("ENV-009_far_ridges.blend", "ENV-009_FarRidge_A.glb", "ENV-009_FarRidge_B.glb", "ENV-009_FarRidge_C.glb"),
    "FX-003": ("FX-003_Headwind.blend", "FX-003_Headwind.glb", "wind_interface.json"),
    "ENV-001": ("ENV-001_terrain.blend", "ENV-001_Flat.glb"),
    "ANM-006": ("ANM-006_formation_blend.blend", "ANM-006_formation_blend.glb"),
    "ENV-017": ("ENV-017_landing_basin.blend", "ENV-017_LandingBasin.glb"),
}
RIDGES = (
    ("A", (-15, 33, .0), -67, (.76, .88, 1.28)),
    ("A", (+16, 37, .0), +67, (.78, .96, 1.2)),
    ("A", (-13.5, 48.5, .0), +50, (.66, .97, 1.36)),
    ("A", (+14, 49.5, .0), -50, (.65, .84, 1.23)),
    ("B", (-21, 39, .0), -62, (.83, 1, .9)),
    ("B", (+22, 40, .0), +69, (.79, .91, .9)),
)
PENDING = [
    "Art approval and short-play wind/readability study at device size",
    "Runtime energy threshold, warning, supply, collisions, formation and recharge/retry behavior",
    "USDZ export, RealityKit and App integration; iPhone and iPad actual devices",
]


def require(cond, what):
    if not cond:
        raise RuntimeError(what)


def read(path):
    return json.loads(path.read_text())


def write(path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def dependency_paths(repo):
    root = repo / LIBRARY
    proof = {}
    for asset, sources in DEPS.items():
        folder = root / asset / "v001"
        manifest_path = folder / "asset_manifest.json"
        manifest = read(manifest_path)
        quality = read(folder / "qa.json")
        require(manifest["status"] in ("needs_review", "done") and bool(quality), f"Unusable dependency {asset}")
        require((folder / "README.md").is_file(), f"Missing readme for {asset}")
        rows = manifest.get("files") or manifest.get("files_sha256")
        for name in (*sources, "README.md", "qa.json", "asset_manifest.json"):
            path = folder / name
            actual = sha(path)
            expected = rows.get(name)
            if isinstance(expected, dict):
                expected = expected["sha256"]
            if expected is not None:
                require(actual == expected, f"{asset}/{name}: dependency SHA changed. Re-evaluate placement.")
            proof[path.relative_to(repo).as_posix()] = {
                "sha256": actual, "matches_catalog_hash": actual == expected if expected else None,
                "candidate_status": manifest["status"], "version": manifest["version"],
                "usage": "fixed-camera review only" if asset in ("ANM-006","ENV-017") else "assembly source",
            }
    swift = repo / RIG_SOURCE
    require("distance: 180, pitch: 0.48, fieldOfViewDegrees: 50" in swift.read_text(), "Swift camera changed")
    proof[RIG_SOURCE] = {"sha256": sha(swift), "usage": "fixed-camera source"}
    return proof


def collection(name, containing):
    coll = bpy.data.collections.new(name)
    containing.children.link(coll)
    return coll


def object_(name, data, group):
    obj = bpy.data.objects.new(name, data)
    group.objects.link(obj)
    return obj


def import_asset(repo, asset, name, group):
    before = set(bpy.context.scene.objects)
    path = repo / LIBRARY / asset / "v001" / name
    result = bpy.ops.import_scene.gltf(filepath=str(path))
    require(result == {"FINISHED"}, path)
    objects = [ob for ob in bpy.context.scene.objects if ob not in before]
    for obj in objects:
        for other in tuple(obj.users_collection):
            other.objects.unlink(obj)
        group.objects.link(obj)
    return objects


def source_mesh(objects):
    return next(obj for obj in objects if obj.type == "MESH")


def relocate(obj, parent, position):
    obj.parent = parent
    obj.location += Vector(position)


def surface(name, vertices, quads, mats, uv, group, parent, material_index=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], quads)
    mesh.update()
    for mat in mats:
        mesh.materials.append(mat)
    if uv:
        layer = mesh.uv_layers.new(name="UVMap")
        for loop in mesh.loops:
            layer.data[loop.index].uv = uv[loop.vertex_index]
    if material_index:
        for polygon, index in zip(mesh.polygons, material_index):
            polygon.material_index = index
    obj = object_(name, mesh, group)
    obj.parent = parent
    return obj


def plane_grid(name, xs, ys, levels, mat, group, parent, channel_u=False, channel_v=False):
    vertices = [(x, y, levels[row][col]) for row, y in enumerate(ys) for col, x in enumerate(xs[row])]
    nx = len(xs[0])
    quads = [(j*nx+i, j*nx+i+1, (j+1)*nx+i+1, (j+1)*nx+i)
             for j in range(len(ys)-1) for i in range(nx-1)]
    uv = [((i/(nx-1)) if channel_u else (x - RIVER_X + 5)/10,
           ((y-12)/10) if channel_v else y/10) for i, (x,y,z) in enumerate(vertices)]
    if channel_u:
        uv = [(i%nx/(nx-1), (y-12)/10) for i, (x,y,z) in enumerate(vertices)]
    return surface(name, vertices, quads, mat, uv, group, parent)


def flat_rect(name, x0, x1, y0, y1, mat, group, parent):
    segments_x = math.ceil(x1-x0)
    segments_y = math.ceil(y1-y0)
    xs = [x0+(x1-x0)*i/segments_x for i in range(segments_x+1)]
    ys = [y0+(y1-y0)*i/segments_y for i in range(segments_y+1)]
    return plane_grid(name, [xs]*len(ys), ys, [[0]*len(xs)]*len(ys), [mat], group, parent)


def terminal_caps(group, root, water_group, water_root, band_mat, water_mat):
    for south in (True, False):
        at = 12 if south else 52
        direction = -1 if south else +1
        distances = [i/4 for i in range(21)]
        ys = sorted(at + direction * d for d in distances)
        rows = [[z * max(0, 1-abs(y-at)/5)**.65 for x,z in PROFILE] for y in ys]
        xs = [[x + RIVER_X for x,z in PROFILE] for _ in ys]
        title = "South" if south else "North"
        cap = plane_grid("RiverBed_" + title + "_closed_lip", xs, ys, rows, [band_mat], group, root, channel_v=True)
        cap["role"] = "Terrain"
        wet_rows = []
        for y, row in zip(ys, rows):
            wet = [i for i in range(len(row)) if row[i] <= WATER]
            if not wet:
                continue
            a, b = wet[0], wet[-1]
            x0, z0 = PROFILE[a-1][0]+RIVER_X, row[a-1]
            x1, z1 = PROFILE[a][0]+RIVER_X, row[a]
            x2, z2 = PROFILE[b][0]+RIVER_X, row[b]
            x3, z3 = PROFILE[b+1][0]+RIVER_X, row[b+1]
            left = x0 + (x1-x0)*(WATER-z0)/(z1-z0)
            right = x2 + (x3-x2)*(WATER-z2)/(z3-z2)
            wet_rows.append((y, [left + (right-left)*i/4 for i in range(5)]))
        # The tapered pool closes at the dry intersection of the two last sampled beds.
        outer = wet_rows[0][0] if south else wet_rows[-1][0]
        next_y = outer + direction * .25
        target = abs(WATER / PROFILE[8][1])
        closing_y = at + direction * 5 * (1 - target**(1/.65))
        d_at = abs(closing_y - at)
        guard = abs(next_y - at)
        if guard >= d_at:
            wet_rows.append((closing_y-.005*direction, [RIVER_X-.009 + .0045*i for i in range(5)]))
        wet_rows.sort()
        wet_ys = [y for y,_ in wet_rows]
        obj = plane_grid("RiverWater_" + title + "_fade", [x for _,x in wet_rows], wet_ys,
                         [[WATER]*5 for _ in wet_ys], [water_mat], water_group, water_root, channel_u=True)
        obj["role"] = "Water"


def material(name, rgba, roughness=1):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = rgba
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = rgba
    shader.inputs["Roughness"].default_value = roughness
    return mat


def pigment(name, color, opacity, kind, path):
    # Reproducible painted alpha, kept apart from the inherited meshes and textures.
    n = 128
    img = bpy.data.images.new(path.name, width=n, height=n, alpha=True)
    data = []
    for row in range(n):
        y = 2*row/(n-1)-1
        for col in range(n):
            x = 2*col/(n-1)-1
            wave = .035*math.sin(21*x+30*y) + .02*math.sin(35*x-36*y)
            radius = x*x + y*y
            shape = max(0., 1 - radius + wave)**2
            if kind == "shadow":
                shape *= (.85 + .15*math.sin(2.8*x + .35*math.cos(3.8*y)))
            data.extend((*color, min(1., opacity*shape)))
    img.alpha_mode = "STRAIGHT"
    img.pixels.foreach_set(data)
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    img.pack()
    mat = material(name, (*color, 1))
    mat.surface_render_method = "DITHERED"
    nodes = mat.node_tree.nodes
    shader = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image, tex.extension = img, "EXTEND"
    mat.node_tree.links.new(tex.outputs["Color"], shader.inputs["Base Color"])
    mat.node_tree.links.new(tex.outputs["Alpha"], shader.inputs["Alpha"])
    shader.inputs["Emission Strength"].default_value = .12 if kind != "shadow" else 0
    mat.node_tree.links.new(tex.outputs["Color"], shader.inputs["Emission Color"])
    return mat


def overlay(name, pos, dimensions, mat, group, root, angle=0):
    x,y = (d/2 for d in dimensions)
    obj = surface(name, ((-x,-y,0),(x,-y,0),(x,y,0),(-x,y,0)), [(0,1,2,3)], [mat],
                  [(0,0),(1,0),(1,1),(0,1)], group, root)
    obj.location = pos
    obj.rotation_euler.z = angle
    return obj


def scatter_reeds(group, root):
    rng = random.Random(56)
    stem = material("Reed_stem_olive", (.14,.19,.10,1))
    blade = material("Reed_blade_luminous_sage", (.33,.40,.21,1))
    catkin = material("Reed_catkin_warm_sedge", (.34,.248,.113,1))
    points = [(-7.3,12.5), (-7.6,17), (-6.8,22.3), (-7.2,33.6), (-6.8,38.6),
              (-7.1,47), (-4.5,53.5), (2.3,19.4), (1.1,24.0), (7.9,31.4),
              (8.1,35.5), (7.95,38.4), (5.9,44.1), (3.9,50.6), (-5.1,55.9),
              (-4.82,59), (4.7,55.8), (4.6,60.5), (-3.3,60.3), (3.5,60.7)]
    for cluster, (cx,cy) in enumerate(points):
        verts, faces, mids = [], [], []
        for reed in range(rng.randint(10,22)):
            x = cx + rng.uniform(-.53,.53)
            y = cy + rng.uniform(-.78,.78)
            h = rng.uniform(.32,.91)
            drift = rng.uniform(-.18,-.07)
            for axis in (0,math.pi/2):
                dx,dy = math.cos(axis)*.015,math.sin(axis)*.015
                base = len(verts)
                verts.extend(((x-dx,y-dy,0),(x+dx,y+dy,0),(x+dx/3,y+dy/3+drift,h),(x-dx/3,y-dy/3+drift,h)))
                faces.append(tuple(range(base,base+4)))
                mids.append(0)
                base = len(verts)
                verts.extend(((x-dx*1.9,y-dy*1.9+drift,h*.86),(x+dx*1.9,y+dy*1.9+drift,h*.86),
                              (x+dx*1.3,y+dy*1.3+drift,h*1.07),(x-dx*1.3,y-dy*1.3+drift,h*1.07)))
                faces.append(tuple(range(base,base+4)))
                mids.append(2)
            for leaf in range(3):
                z = h * (.22 + leaf*.19)
                az = rng.uniform(-math.pi, math.pi)
                dx,dy = math.cos(az), math.sin(az)
                base = len(verts)
                verts.extend(((x,y+drift*.35,z),(x+dx*.13-dy*.025,y+dy*.13+dx*.025+drift*.6,z+.11),
                              (x+dx*rng.uniform(.22,.31),y+dy*.34+drift,z+.24),
                              (x+dx*.13+dy*.027,y+dy*.13-dx*.027+drift*.6,z+.14)))
                faces.append(tuple(range(base,base+4)))
                mids.append(1)
        obj = surface(f"Weathered_reeds_{cluster+1:02}", verts, faces, [stem,blade,catkin], None,
                      group, root, mids)
        obj["role"] = "Scenery"


def stage(repo, out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "LVL-S5 | Fixed third-person review"
    scene.render.fps = FPS
    scene.frame_end = END
    assert scene.render.fps_base == 1
    export = collection("01 | Runtime S5 scene", scene.collection)
    ground = collection("Terrain | flat gates and reused river bed", export)
    waters = collection("Water | separate render layer", export)
    back = collection("Ridge masses and bank foliage", export)
    effects = collection("FX | headwind and bank pigment", export)
    review = collection("02 | Review camera, flock and demonstration path", scene.collection)

    root = object_(VARIANT, None, export)
    root["asset_version"] = "v001"
    root["BU_per_game_unit"] = SCALE
    root["collision_source"] = "Engine geometry/authoritative gameplay rules"
    terrain_root = object_("S5_Terrain", None, ground)
    water_root = object_("S5_Water", None, waters)
    fx_root = object_("S5_WindField", None, effects)
    ridge_root = object_("S5_Ridges", None, back)
    for part in (terrain_root, water_root, fx_root, ridge_root):
        part.parent = root

    flat = source_mesh(import_asset(repo, "ENV-001", "ENV-001_Flat.glb", ground))
    flat_mat = flat.data.materials[0]
    bpy.data.objects.remove(flat, do_unlink=True)
    for bounds in (
        ("Entry_gate", -LAND_HALF, LAND_HALF, 0, 7),
        ("West_bank", -LAND_HALF, RIVER_X-5, 7, 57),
        ("East_bank", RIVER_X+5, LAND_HALF, 7, 57),
        ("Exit_gate", -LAND_HALF, LAND_HALF, 57, 64),
    ):
        name, x0, x1, y0, y1 = bounds
        band = flat_rect(f"S5_Terrain_{name}", x0,x1,y0,y1,flat_mat,ground,terrain_root)
        band["role"] = "Terrain"

    prototypes = {}
    for variant, y in RIVER:
        if variant not in prototypes:
            nodes = import_asset(repo, "ENV-007", f"ENV-007_{variant}.glb", ground)
            parts = tuple(next(obj for obj in nodes if obj.name == f"{variant}_{kind}") for kind in ("Bed","Water"))
            prototypes[variant] = parts
        else:
            parts = tuple(object_(obj.name, obj.data, ground) for obj in prototypes[variant])
        bed, water = parts
        bed.name = f"RiverBed_{variant}_{y:02}"
        water.name = f"RiverWater_{variant}_{y:02}"
        relocate(bed, terrain_root, (RIVER_X,y,0))
        relocate(water, water_root, (RIVER_X,y,0))
        waters.objects.link(water)
        ground.objects.unlink(water)
        bed["role"] = "Terrain"
        water["role"] = "Water"
    water_mat = prototypes["Straight"][1].data.materials[0]
    material_by_name = {m.name: m for m in prototypes["Straight"][0].data.materials}
    terminal_caps(ground,terrain_root,waters,water_root,material_by_name["GrassFlat"] if "GrassFlat" in material_by_name else flat_mat,water_mat)

    for letter in ("A","B"):
        model = source_mesh(import_asset(repo, "ENV-009", f"ENV-009_FarRidge_{letter}.glb", back))
        for number, (which, pos, degrees, scale) in enumerate(RIDGES):
            if which != letter:
                continue
            ridge = object_(f"FarRidge_{letter}_{number+1}", model.data, back)
            ridge.parent = ridge_root
            ridge.location = pos
            ridge.rotation_euler.z = math.radians(degrees)
            ridge.scale = scale
            ridge["role"] = "Scenery"
        bpy.data.objects.remove(model, do_unlink=True)
    scatter_reeds(back, ridge_root)

    (out / "textures").mkdir(exist_ok=True)
    rest_mat = pigment("Sheltered bank | sage wash", (.31,.49,.29), .86, "wash",
                        out / "textures/ft_goose_env_s5_shelter_basecolor_alpha.png")
    rest_wash = overlay("Shelter_soft_sage_wash", (*REST[:2],.017), (5.6,8.1),rest_mat,effects,root,-.16)
    rest_wash["role"] = "Route cue only"
    path_mat = pigment("Shelter brush | clear pale gold", (.64,.66,.40), .87, "wash",
                        out / "textures/ft_goose_env_s5_shelter_path_basecolor_alpha.png")
    for index, (x,y,ang,w,h) in enumerate(((.53,27.5,-.26,.97,2.4),(1.42,28.78,-.48,1.2,2.7),
                  (2.59,29.83,-.62,1.35,2.29),(3.62,31.38,-.30,1.4,2.3),
                  (4.57,33.0,-.12,2.7,2.5),(4.62,34.67,0,2.8,2.6),(3.94,38.1,.37,1.35,3.1),
                  (3.05,40.13,.42,1.32,2.9),(1.87,42.46,.36,1.2,2.54),
                  (0,55.1,0,1.4,4.3),(0,59.2,0,1.25,4.3))):
        cue = overlay(f"Shelter_path_brush_{index+1:02}", (x,y,.026 + .0009*index), (w,h),path_mat,effects,root,ang)
        cue["role"] = "Route cue only"
    glow = pigment("Shelter cue | muted mint scatter", (.66,.88,.63), .94, "wash",
                    out / "textures/ft_goose_env_s5_shelter_cue_alpha.png")
    for index, (x,y,w,h) in enumerate(((3.63,33.1,.61,.37),(4.21,33.49,.89,.54),
                       (4.86,33.71,.69,.39),(4.42,34.48,.46,.31),(5.25,34.05,.38,.34),
                       (4.96,34.79,.58,.31))):
        cue = overlay(f"Shelter_rim_shimmer_{index+1:02}", (x,y,.043 + .0009*index), (w,h),glow,effects,root,-.2)
        cue["role"] = "Route cue only"
    shadow = pigment("Cloud shade | blue grey wool wash", (.19,.25,.31), .23, "shadow",
                     out / "textures/ft_goose_fx_s5_cloud_shadow_alpha.png")
    for i,(x,y,w,h) in enumerate(((-2.8,22.7,12,7),(.18,46.1,10,9))):
        card = overlay(f"S5_CloudShadow_{i+1:02}", (x,y,.007), (w,h),shadow,effects,fx_root,.19)
        card["role"] = "Wind shadow layer"
        card["dry_only"] = False

    asset = source_mesh(import_asset(repo,"FX-003","FX-003_Headwind.glb",effects))
    wind_material = asset.data.materials[0]
    wind_surface = wind_material.node_tree.nodes.get("Principled BSDF")
    if wind_surface is not None:
        wind_surface.inputs["Emission Strength"].default_value = .72
    for lane, (x,z) in enumerate(WIND):
        for streak in range(WIND_TILES_PER_LANE):
            obj = object_(f"S5_Wind_{lane+1:02}_{streak+1:02}", asset.data, effects)
            obj.parent = fx_root
            obj.location = (x, 13+streak*12+lane*.55, z)
            obj.rotation_euler.z = math.pi
            obj["role"] = "Headwind ribbon"
            obj["axis"] = "Blender local +Y with yaw pi, world -Y"
            obj["speed_BU_s"] = WIND_SPEED
            obj["start_y_BU"] = obj.location.y
            obj["phase_BU"] = (lane*.427 + streak*.617) % WIND_PERIOD
    bpy.data.objects.remove(asset, do_unlink=True)

    for name, position in ANCHORS.items():
        node = object_(name, None, export)
        node.parent = root
        node.location = position
        node.empty_display_type = "ARROWS"
        node.empty_display_size = .7
        node["heading"] = [0.,1.,0.]
        node["role"] = "Runtime placement anchor"
    flat_rect("Review entrance apron",-LAND_HALF,LAND_HALF,-22,0,flat_mat,review,None).location.z = -.014
    flat_rect("Beyond S6 only",-70,70,104,154,flat_mat,review,None).location.z = -.014
    basin = import_asset(repo,"ENV-017","ENV-017_LandingBasin.glb",review)
    for part in basin:
        if part.parent is None:
            part.location.y += 84
    horizon = source_mesh(import_asset(repo,"ENV-009","ENV-009_FarRidge_C.glb",review))
    horizon.location = (-8,135,0)
    horizon.scale = (1.22,1.2,1.1)
    camera, top = light_camera(scene, review)
    add_flock(repo, review)
    return scene, export, review, camera, top


def light_camera(scene, group):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 9
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.transparent_max_bounces = 8
    scene.view_settings.view_transform = "AgX"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.world = bpy.data.worlds.new("Silver-blue overcast")
    scene.world.use_nodes = True
    world = scene.world.node_tree.nodes.get("Background")
    world.inputs["Color"].default_value = (.61,.68,.74,1)
    world.inputs["Strength"].default_value = .73
    sun = object_("Soft daylight", bpy.data.lights.new("Soft daylight","SUN"), group)
    sun.data.energy = 2.2
    sun.data.angle = .39
    sun.data.color = (.83,.91,1)
    sun.rotation_euler = Vector((.5,.35,-1)).to_track_quat("-Z","Y").to_euler()
    camera = object_("FixedRear_Swift",bpy.data.cameras.new("FixedRear_Swift"),group)
    camera.data.sensor_fit = "VERTICAL"
    camera.data.sensor_height = 24
    camera.data.lens = 12 / math.tan(math.radians(25))
    camera.data.clip_start,camera.data.clip_end = .0018, 360
    top = object_("Technical top only",bpy.data.cameras.new("Technical top only"),group)
    top.location = (0,32,100)
    top.rotation_euler = (0,0,0)
    top.data.type = "ORTHO"
    top.data.sensor_fit = "VERTICAL"
    top.data.ortho_scale = 69
    top.data.clip_end = 230
    return camera, top


def add_flock(repo, group):
    model = import_asset(repo, "ANM-006", "ANM-006_formation_blend.glb", group)
    mesh = source_mesh(model)
    # Keep the applied formation pose and linked feather materials. Carrier animation is reviewed separately.
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    posed = bpy.data.meshes.new_from_object(evaluated)
    transform = mesh.matrix_world.copy()
    posed.transform(transform)
    for obj in model:
        bpy.data.objects.remove(obj, do_unlink=True)
    for i in range(len(FLOCK)):
        bird = object_(f"Review_Flock_{i+1:02}", posed, group)
        bird["role"] = "Review only"
    return posed


def catmull(points, position):
    left = min(int(position),len(points)-2)
    f = min(1.0, max(0.0,position-left))
    a,b,c,d = (Vector(points[i]) for i in (max(0,left-1),left,left+1,min(left+2,len(points)-1)))
    return .5 * (2*b + (c-a)*f + (2*a-5*b+4*c-d)*f*f + (3*b-a-3*c+d)*f*f*f)


def camera_at(camera, pos, heading, altitude):
    back = 180*SCALE*math.cos(.48)
    height = 180*SCALE*math.sin(.48)
    camera.location = (pos.x-heading.x*back,pos.y-heading.y*back,height+altitude)
    target = Vector((pos.x,pos.y,6*SCALE+altitude))
    camera.rotation_euler = (target-camera.location).to_track_quat("-Z","Y").to_euler()


def review_pose(scene, camera, frame, key=False):
    curve = ((0,18,.49),(0,23.4,.49),(.38,27.4,.49),(2.24,29.9,.47),(4.45,33.45,.45),
             (4.61,37.7,.45),(3.18,41.8,.47),(1.2,46.1,.49),(0,51.8,.49),
             (0,57.3,.49),(0,61.8,.49),(0,64,.49))
    f = (frame-1)/(END-1)*(len(curve)-1)
    pos = catmull(curve, f)
    aim = catmull(curve, f+.005) - catmull(curve, f-.005)
    forward = Vector((aim.x,aim.y,0)).normalized()
    camera_at(camera, pos, forward, pos.z)
    facing = -math.atan2(forward.x,forward.y)
    right = Vector((forward.y,-forward.x,0))
    if key:
        camera.keyframe_insert(data_path="location",frame=frame)
        camera.keyframe_insert(data_path="rotation_euler",frame=frame)
    for slot,(off_x,off_y) in enumerate(FLOCK):
        bird = bpy.data.objects[f"Review_Flock_{slot+1:02}"]
        bird.location = Vector((pos.x,pos.y,pos.z + (8 if slot==0 else 6)*SCALE + .024*math.sin(frame*.255+slot))) + right*off_x + forward*off_y
        bird.rotation_euler.z = facing
        bird.rotation_euler.y = .055*math.sin(frame*.21 + slot*.72)
        if key:
            bird.keyframe_insert(data_path="location",frame=frame)
            bird.keyframe_insert(data_path="rotation_euler",frame=frame)
    t = (frame-1)/FPS
    for obj in scene.objects:
        if obj.get("role") == "Headwind ribbon":
            obj.location.y = obj["start_y_BU"]+4.2-((obj["phase_BU"]+t*WIND_SPEED) % WIND_PERIOD)
            if key:
                obj.keyframe_insert(data_path="location",frame=frame)
        elif obj.get("role") == "Wind shadow layer":
            if "rest_y_BU" not in obj:
                obj["rest_y_BU"] = obj.location.y
            obj.location.y = obj["rest_y_BU"]-.53*t
            if key:
                obj.keyframe_insert(data_path="location",frame=frame)
    bpy.context.view_layer.update()


def render(scene, camera, path, size=SIZE, samples=9):
    scene.camera = camera
    scene.render.resolution_x,scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.cycles.samples = samples
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def mesh_triangles(objects):
    vertices, polys = [], []
    for obj in objects:
        matrix = obj.matrix_world
        mesh = obj.data
        mesh.calc_loop_triangles()
        n = len(vertices)
        vertices.extend(matrix @ v.co for v in mesh.vertices)
        polys.extend(tuple(n+i for i in p.vertices) for p in mesh.loop_triangles)
    return BVHTree.FromPolygons(vertices,polys,all_triangles=True) if polys else None


def sample_ground(bvh, x,y):
    return bvh.ray_cast((x,y,4),(0,0,-1),5)[0]


def track(points, resolution):
    for a,b in zip(points,points[1:]):
        a, b = Vector(a), Vector(b)
        for i in range(resolution):
            yield a.lerp(b,i/resolution)
    yield Vector(points[-1])


def visible(scene, camera, point, occluders):
    target = Vector(point)
    q = world_to_camera_view(scene,camera,target)
    view = camera.matrix_world.translation
    ray = target-view
    hit, _, _, _ = occluders.ray_cast(view,ray.normalized(),ray.length-.012)
    return {
        "normalized_screen_xy": [float(q.x),float(q.y)],
        "pixels_from_left_and_top": [float(q.x*SIZE[0]),float((1-q.y)*SIZE[1])],
        "in_frame": bool(0<q.x<1 and 0<q.y<1 and q.z>0),
        "occluded": hit is not None,
    }


def measurements(scene, objects, cam):
    bpy.context.view_layer.update()
    terrain = [o for o in objects if o.type=="MESH" and o.get("role")=="Terrain"]
    waters = [o for o in objects if o.type=="MESH" and o.get("role")=="Water"]
    scenery = [o for o in objects if o.type=="MESH" and o.get("role")=="Scenery"]
    ridge_vertices = [o.matrix_world @ v.co for o in scenery if o.name.startswith("FarRidge_") for v in o.data.vertices]
    ridge_y = [min(v.y for v in ridge_vertices), max(v.y for v in ridge_vertices)]
    require(ridge_y[0] > 2 and ridge_y[1] < 62, "Exported ridge encroaches on the neighboring tile")
    any_solid = mesh_triangles(terrain+scenery)
    ground = mesh_triangles(terrain)
    liquid = mesh_triangles(waters)
    require(terrain and waters and scenery, "Missing render layers")
    named = {obj.name:obj for obj in objects}
    require(set(ANCHORS) <= named.keys(), "Missing reimport anchors")
    anchors = {}
    for name, expected in ANCHORS.items():
        obj = named[name]
        deviation = (obj.matrix_world.translation-Vector(expected)).length
        direction = (obj.matrix_world.to_quaternion() @ Vector((0,1,0)) - Vector((0,1,0))).length
        require(max(deviation,direction)<1e-5, f"Wrong anchor or heading for {name}")
        anchors[name] = {"position_BU":list(obj.matrix_world.translation),"axis_error":direction,
                         "position_error_BU":deviation}

    gate_count, gate_error, gate_dry_samples = 0, 0, 0
    for y_center,sgn in ((0,1),(64,-1)):
        for off in (.001,.12,.50,1.02,1.55,1.995):
            for i in range(97):
                x = WEST_GATE[0] + (WEST_GATE[1]-WEST_GATE[0])*i/96
                y = y_center + sgn*off
                solid = sample_ground(any_solid,x,y)
                require(solid is not None, f"Terrain gap at ({x},{y})")
                require(abs(solid.z)<1e-5, f"Gate terrain nonzero at ({x},{y}): {solid.z}")
                gate_count += 1
                gate_error = max(gate_error, abs(solid.z))
                require(sample_ground(liquid,x,y) is None, f"Water crosses gate at ({x},{y})")
                require(sample_ground(ground,x,y_center-sgn*off) is None, f"Ground extends past gate near ({x},{y})")
                gate_dry_samples += 1

    bank = {"count":0,"maximum_flatness_error_BU":0}
    for i in range(25):
        for j in range(29):
            x,y = REST[0]-1.2+.10*i, REST[1]-1.4+.10*j
            z = sample_ground(any_solid,x,y)
            require(z is not None and abs(z.z)<1e-5, f"Rest not clear and flat at ({x},{y})")
            require(sample_ground(liquid,x,y) is None, f"Rest pad not dry at ({x},{y})")
            bank["maximum_flatness_error_BU"] = max(abs(z.z),bank["maximum_flatness_error_BU"])
            bank["count"] += 1
    route_checks = {}
    for route_name, route in ROUTES.items():
        probes = []
        for point in track(route,40):
            for side in (-.77,0,.77):
                x,y = point.x+side, min(63.999,max(.001,point.y))
                z = sample_ground(any_solid,x,y)
                require(z is not None, f"Missing route floor on {route_name}: {x,y}")
                probes.append(point.z-z.z)
        require(min(probes)>.20,f"Obstructed path {route_name}, clearance {min(probes)}")
        route_checks[route_name] = {
            "sample_count":len(probes),"min_upper_route_clearance_BU":min(probes),"half_lane_BU":.77,
            "control_polyline_length_BU":sum((Vector(b)-Vector(a)).length for a,b in zip(route,route[1:])),
        }

    water_extents = []
    for obj in waters:
        coords = [obj.matrix_world @ v.co for v in obj.data.vertices]
        water_extents.extend(coords)
    water_error = max(abs(v.z-WATER) for v in water_extents)
    require(water_error<1e-5, "River water height changes along the modular route")
    seams = []
    epsilon = .0001
    for y in (12,22,32,42,52):
        samples = []
        wet_height = []
        for i in range(161):
            x = RIVER_X-4.99 + 9.98*i/160
            a,b = sample_ground(ground,x,y-epsilon),sample_ground(ground,x,y+epsilon)
            require(a is not None and b is not None, "Hole at an ENV-007 join")
            samples.append(abs(a.z-b.z))
            a,b = sample_ground(liquid,x,y-epsilon),sample_ground(liquid,x,y+epsilon)
            require((a is None) == (b is None), f"Water topology mismatch at x {x}, y {y}")
            if a is not None:
                wet_height.append(abs(a.z-b.z))
        require(max(samples)<.0002 and max(wet_height,default=0)<1e-5,f"R seam mismatch at y {y}")
        seams.append({"y_BU":y,"bed_probes":len(samples),"water_probes":len(wet_height),
                      "bed_cross_sample_max_delta_BU":max(samples),
                      "wet_cross_sample_max_delta_BU":max(wet_height,default=0)})

    pose_inputs = (
        ("shelter_visible_ahead", (0,26.6,.491),(0,1,0),(*REST[:2],.07)),
        ("shelter_clear_on_return", (3.4,30.8,.47),(.36,.933,0),(*REST[:2],.07)),
        ("S6_exit_visible", (0,57,.49),(0,1,0), (0,63.97,.065)),
    )
    sightlines = {}
    ribbons = [obj for obj in objects if obj.get("role")=="Headwind ribbon"]
    ribbon_bvh = mesh_triangles(ribbons)
    for name, pos, heading, target in pose_inputs:
        camera_at(cam, Vector(pos), Vector(heading),pos[2])
        bpy.context.view_layer.update()
        record = visible(scene,cam,target,any_solid)
        require(record["in_frame"] and not record["occluded"], f"Target {name} obscured: {record}")
        record["wind_mesh_intersects_center_view_ray"] = visible(scene,cam,target,ribbon_bvh)["occluded"]
        require(not record["wind_mesh_intersects_center_view_ray"], f"Target {name} blocked by wind mesh")
        sightlines[name] = record

    winds = ribbons
    require(len(winds)==len(WIND)*WIND_TILES_PER_LANE, f"Only {len(winds)} wind streaks")
    require(all(abs(obj["speed_BU_s"]-WIND_SPEED)<1e-6 for obj in winds), "Wind speed metadata mismatch")
    dot_peaks, uworld = [], []
    for ribbon in winds:
        local_y_axis = ribbon.matrix_world.to_quaternion() @ Vector((0,1,0))
        dot_peaks.append(local_y_axis.dot(Vector((0,-1,0))))
        require(all(s>0 for s in ribbon.scale), "Mirrored rather than rotated ribbon")
        data = ribbon.data
        layer = data.uv_layers.active
        require(layer is not None, "Missing wind UV")
        means = [[],[]]
        for loop in data.loops:
            u = layer.data[loop.index].uv.x
            if u<.05 or u>.95:
                means[u>.95].append((ribbon.matrix_world @ data.vertices[loop.vertex_index].co).y)
        require(all(means), "Missing each end of FX-003 ribbon")
        uworld.append(sum(means[1])/len(means[1]) - sum(means[0])/len(means[0]))
    require(min(dot_peaks)>.9999 and max(uworld)<-2.4,"Wind not flowing along world -Y")

    return {"status":"pass","anchors":anchors,"exported_ridge_y_extent_BU":ridge_y,
            "dry_gate_samples":gate_count,"dry_gate_max_error_BU":gate_error,
            "gate_no_water_and_no_offsegment_ground_probes":gate_dry_samples,
            "safe_bank_plateau":bank,
            "safe_route_distance_low_energy_marker_to_rest_BU":
                (Vector(ANCHORS["S5_LowEnergySample"][:2])-Vector(REST[:2])).length,
            "shelter_and_exit_camera_visibility":sightlines,
            "routes":route_checks,
            "wet_height_error_BU":water_error,
            "wet_extent_y_BU":[min(v.y for v in water_extents),max(v.y for v in water_extents)],
            "river_joins":seams,
            "headwind":{"lanes":len(WIND),"streaks":len(winds),"min_direction_dot_minus_y":min(dot_peaks),
                        "mean_U1_minus_U0_extent_world_y_BU":sum(uworld)/len(uworld),
                        "speed_BU_s":WIND_SPEED}}


def animation_check(scene, cam):
    maximum_camera = 0.
    delta = []
    wrap_events = 0
    ribbon = bpy.data.objects["S5_Wind_01_02"]
    frames = range(1,END+1)
    coords = []
    all_y = []
    for f in frames:
        scene.frame_set(f)
        y = ribbon.matrix_world.translation.y
        all_y.append(y)
        lead = bpy.data.objects["Review_Flock_01"].matrix_world.translation
        eye = cam.matrix_world.translation
        back = (Vector((lead.x,lead.y,0))-Vector((eye.x,eye.y,0))).length
        want = 180*SCALE*math.cos(.48)
        error = abs(back-want)
        maximum_camera = max(maximum_camera,error)
        coords.append((lead.y, eye.y))
    for previous,current in zip(all_y,all_y[1:]):
        d=current-previous
        if d > 0:
            wrap_events+=1
        else:
            delta.append(d*FPS)
    worst_speed = max(abs(v+WIND_SPEED) for v in delta)
    require(worst_speed < .00012 and maximum_camera < .00002 and wrap_events>0, "Headwind or camera keyframes changed")
    return {"status":"pass","sampled_frames":len(all_y),"wraps_detected":wrap_events,
            "measured_headwind_speed_BU_s":[min(delta),max(delta)],
            "max_speed_error_BU_s":worst_speed,"max_camera_back_offset_error_BU":maximum_camera,
            "lead_y_extent_BU":[coords[0][0],coords[-1][0]],
            "camera_params":{"distance_game_units":180,"pitch_rad":.48,"vertical_FOV_deg":50,"look_height_game_units":6}}


def render_gray(scene,objects,cam,top,out):
    props = {
        "Terrain":(.29,.30,.29,1), "Water":(.115,.19,.22,1), "Scenery":(.18,.185,.17,1),
        "Route cue only":(.46,.49,.36,1),"Headwind ribbon":(.71,.77,.78,1),
    }
    grays = {name:material(f"Graybox | {name}",rgba) for name,rgba in props.items()}
    touched, hidden = [], []
    for obj in objects:
        if obj.get("role") == "Wind shadow layer" or ("Shelter" in obj.name and "brush" not in obj.name):
            obj.hide_render = True
            hidden.append(obj)
        if obj.type != "MESH" or obj.get("role") not in grays:
            continue
        gray = grays[obj["role"]]
        for slot in obj.material_slots:
            original=(slot,slot.link,slot.material)
            slot.link="OBJECT"
            slot.material=gray
            touched.append(original)
    review_pose(scene,cam,42)
    render(scene,cam,out/"graybox_fixed_rear.png",samples=7)
    render(scene,top,out/"graybox_top.png",(852,828),samples=5)
    for slot, prev_link, prev_mat in touched:
        if prev_link == "OBJECT":
            slot.material = prev_mat
        slot.link = prev_link
    for obj in hidden:
        obj.hide_render = False


def create_video(scene,cam,out):
    folder = out / ".frames"
    folder.mkdir()
    for i, frame in enumerate(range(1,END+1,STEP)):
        scene.frame_set(frame)
        render(scene,cam,folder/f"{i:04}.png",samples=2)
    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-framerate",str(FPS//STEP),
                    "-i",str(folder/"%04d.png"),"-vf","pad=ceil(iw/2)*2:ceil(ih/2)*2","-r","24",
                    "-c:v","libx264","-pix_fmt","yuv420p","-crf","18","-movflags","+faststart",
                    "-an",str(out/VIDEO)],check=True)
    count=len(list(folder.glob("*.png")))
    require(count==len(range(1,END+1,STEP)),"Movie rendering incomplete")
    return count


def decode_video(file):
    probe = subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_streams","-of","json",str(file)])
    streams=read_bytes_json(probe)["streams"]
    require(len(streams)==1 and streams[0]["codec_type"]=="video","Unexpected soundtrack or video asset")
    stream=streams[0]
    count=int(stream["nb_read_frames"])
    require((stream["width"],stream["height"])==(852,394),"Encoded video size mismatch")
    require(count==len(range(1,END+1,STEP))*STEP,"Video frame count mismatch")
    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-v","error","-xerror","-i",str(file),
                    "-map","0:v:0","-f","null","-"],check=True)
    return {"status":"pass","decoded_frames":count,"size_px":[852,394],"source_size_px":list(SIZE),
            "audio_streams":0,"duration_s":count/FPS}


def read_bytes_json(blob):
    return json.loads(blob.decode("utf-8"))


def read_glb(glb):
    data = glb.read_bytes()
    magic,ver,length,n,kind = struct.unpack_from("<4sIIII",data)
    require(magic==b"glTF" and ver==2 and length==len(data) and kind==0x4E4F534A,"Stale or malformed GLB")
    doc = read_bytes_json(data[20:20+n])
    binary = data[28+n:]
    return doc,binary


def embedded_images(doc,binary):
    result={}
    for im in doc.get("images",[]):
        require("bufferView" in im, "Nonportable texture URI in GLB")
        v=doc["bufferViews"][im["bufferView"]]
        start=v.get("byteOffset",0)
        result[im["name"]] = hashlib.sha256(binary[start:start+v["byteLength"]]).hexdigest()
    return result


def verify_glb(path,repo):
    glb, blob = read_glb(path)
    nodes = {n.get("name"):n for n in glb["nodes"]}
    scene=glb["scenes"][glb.get("scene",0)]
    require([glb["nodes"][i]["name"] for i in scene["nodes"]]==[VARIANT],"Wrong root or review objects exported")
    require(not glb.get("cameras") and not glb.get("animations") and not glb.get("skins"),"Export scope changed")
    for name, pos in ANCHORS.items():
        glb_pos = nodes[name].get("translation",[0,0,0])
        want = (pos[0],pos[2],-pos[1])
        require(max(abs(a-b) for a,b in zip(glb_pos,want))<1e-5, f"Axis mapping for {name}")
    textures=embedded_images(glb,blob)
    upstream=repo / LIBRARY / "FX-003" / "v001" / "FX-003_Headwind.glb"
    glb_src, data_src = read_glb(upstream)
    source_shas = set(embedded_images(glb_src,data_src).values())
    require(source_shas <= set(textures.values()),"Headwind texture re-encoded or missing")
    inherited = {}
    for asset, filename in (
        ("ENV-001","ENV-001_Flat.glb"),
        ("ENV-007","ENV-007_Straight.glb"),
        ("ENV-009","ENV-009_FarRidge_A.glb"),
        ("ENV-009","ENV-009_FarRidge_B.glb"),
    ):
        input_doc,input_binary = read_glb(repo / LIBRARY / asset / "v001" / filename)
        embedded = sorted(set(embedded_images(input_doc,input_binary).values()))
        require(set(embedded) <= set(textures.values()),f"Source texture missing from runtime GLB: {filename}")
        inherited[filename]=embedded
    wind_index=nodes["S5_Wind_01_01"]["mesh"]
    wind_mat=glb["meshes"][wind_index]["primitives"][0]["material"]
    require(glb["materials"][wind_mat].get("alphaMode") == "BLEND","Headwind lost its feathered alpha")
    wind_mesh = glb["meshes"][nodes["S5_Wind_01_01"]["mesh"]]
    triangles = sum(glb["accessors"][part["indices"]]["count"]//3 for part in wind_mesh["primitives"])
    require(triangles == 72,"FX-003 wind mesh changed from 72 tris")
    return {"status":"pass","nodes":len(nodes),"triangles_per_named_wind":triangles,
            "image_hashes":textures,"FX003_identical_GLTF_texture_sha256":sorted(source_shas),
            "reused_environment_image_sha256":inherited,"wind_alpha_mode":"BLEND",
            "visuals_only":True}


def make_layout(repo):
    wind_source=repo / LIBRARY / "FX-003/v001/wind_interface.json"
    return {"id":ID,"version":"v001","status":"needs_review","variant":VARIANT,
            "entry_node":"S5_Entry","exit_node":"S5_Exit",
            "entry_BU":[0,0,0],"exit_BU":[0,64,0],"heading_blender":[0,1,0],
            "neighbor_candidates":{
                "from_LVL-S4":{"S4_actual_apron_exit_BU":[2,45,0],"S5_node":"S5_Entry"},
                "to_LVL-S6":{"S5_node":"S5_Exit","S6_entry_BU":[0,0,0]},
            },
            "coordinate_system":{"Blender":"+Z up, +Y forward","gltf":"(x,z,-y)","BU_per_game_unit":SCALE},
            "seams":{"dry_both_gates":True,"terrain_z_BU":0,"reference_water_z_BU":WATER,
                     "shared_gate_width_BU":24,"S5_ground_width_BU":2*LAND_HALF,
                     "clear_inward_BU":2,"offset_reference":"Both gates exactly terminate export terrain"},
            "anchors_BU":ANCHORS,"routes_BU":ROUTES,
            "safe_bank":{"anchor":"S5_SafeRest","width_depth_BU":[2.4,2.8],
                         "usage":"proposed optional rest and recovery. Actual zone and resource rules authored by the game."},
            "river_modules":[{"variant":v,"x_BU":RIVER_X,"y_BU":y,"z_BU":0} for v,y in RIVER],
            "ridge_placements":[{"variant":v,"xyz_BU":p,"yaw_deg":d,"scale":s} for v,p,d,s in RIDGES],
            "runtime_inputs":{"wind":{"FX003_upstream_wind_interface_sha256":sha(wind_source),
                                      "worldWindDirection_blender":[0,-1,0],
                                      "yaw_about_up_rad":math.pi,"windSpeedBUPerSecond_preview":WIND_SPEED,
                                      "wind_instance_translation":"upstream contract; positive speed along normalized downwind",
                                      "serialized_review_lanes_xz_BU":WIND,"streaks_per_lane":WIND_TILES_PER_LANE,
                                      "phase_cycle_BU":WIND_PERIOD},
                              "low_energy_fraction_candidate":.30,"low_energy_marker":"S5_LowEnergySample",
                              "run_time_seconds_target_in_spec":40,
                              "trigger_authority":"app owns all recharge, energy, collisions, recovery/retry and continuation rules"},
            "review":{"camera_source":RIG_SOURCE,"source_size_px":SIZE,
                      "camera_params":[180,.48,50,6],"lead_pose_altitude_game_units":8,
                      "preview_seconds":len(range(1,END+1,STEP))*STEP/FPS}}


def prepare_output(out):
    out.mkdir(parents=True,exist_ok=True)
    require(not any(out.iterdir()), "Use an empty temporary output directory")


def build(repo,out,smoke=False):
    inputs=dependency_paths(repo)
    scene, asset, review, cam, top = stage(repo,out)
    scene.render.resolution_x,scene.render.resolution_y = SIZE
    source_checked=measurements(scene,list(asset.all_objects),cam)
    render_gray(scene,list(asset.all_objects),cam,top,out)
    for f in range(1,END+1):
        review_pose(scene,cam,f,key=True)
    motion=animation_check(scene,cam)
    for frame,title,camera,size in ((44,"preview_fixed_rear_shelter.png",cam,SIZE),
             (79,"preview_fixed_rear_detour.png",cam,SIZE),(171,"preview_fixed_rear_exit.png",cam,SIZE),
             (79,"preview_top.png",top,(852,828))):
        scene.frame_set(frame)
        render(scene,camera,out/title,size=size)
    if not smoke:
        create_video(scene,cam,out)
    scene.frame_set(1)
    scene.camera=cam
    scene.render.resolution_x,scene.render.resolution_y = SIZE
    bpy.ops.object.select_all(action="DESELECT")
    for obj in asset.all_objects:
        obj.select_set(True)
    result=bpy.ops.export_scene.gltf(filepath=str(out/GLB),use_selection=True,export_extras=True,export_yup=True,
                                  export_animations=False,export_cameras=False,export_lights=False)
    require(result=={"FINISHED"},"GLB export failed")
    scene.render.filepath="//review.png"
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/BLEND))
    write(out/"s5_layout.json",make_layout(repo))
    write(out/"build.json",{"id":ID,"version":"v001","status":"needs_review","source_gates":source_checked,
                            "source_motion":motion,"dependency_files":inputs,
                            "GLB_transport":verify_glb(out/GLB,repo),"pending":PENDING})
    if not smoke:
        print("SOURCE VIDEO", decode_video(out/VIDEO))


def verify(repo,delivery,out):
    pinned=dependency_paths(repo)
    saved=read(delivery/"qa.json")
    require(saved["dependency_files"]==pinned,"Source dependency pin changed")
    glb_proof=verify_glb(delivery/GLB,repo)
    bpy.ops.wm.open_mainfile(filepath=str(delivery/BLEND))
    scene=bpy.context.scene
    cam=bpy.data.objects["FixedRear_Swift"]
    runtime=bpy.data.collections["01 | Runtime S5 scene"]
    source=measurements(scene,list(runtime.all_objects),cam)
    motion=animation_check(scene,cam)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    objects=bpy.context.scene.collection
    result=bpy.ops.import_scene.gltf(filepath=str(delivery/GLB))
    require(result=={"FINISHED"},"Delivered GLB failed Blender reimport")
    imported=list(scene.objects)
    cam,top=light_camera(scene,collection("Independent review cameras",objects))
    scene.render.resolution_x,scene.render.resolution_y = SIZE
    roundtrip=measurements(scene,imported,cam)
    require(max(abs(source[k]-roundtrip[k]) for k in ("wet_height_error_BU","dry_gate_max_error_BU"))<1.e-5,"Roundtrip height deviation")
    for label in ROUTES:
        a,b=source["routes"][label],roundtrip["routes"][label]
        require(abs(a["min_upper_route_clearance_BU"]-b["min_upper_route_clearance_BU"])<1e-5,f"Roundtrip route drift: {label}")
    review=collection("Independent fixed-camera scale geese and aprons",objects)
    add_flock(repo,review)
    pos=Vector((0,26.6,.491))
    camera_at(cam,pos,Vector((0,1,0)),pos.z)
    for i,(x,y) in enumerate(FLOCK):
        bpy.data.objects[f"Review_Flock_{i+1:02}"].location = (x,pos.y+y,pos.z+(8 if i==0 else 6)*SCALE)
    bpy.context.view_layer.update()
    render(scene,cam,out/"roundtrip_fixed_rear.png")
    render(scene,top,out/"roundtrip_top.png",(852,828))
    decoded=decode_video(delivery/VIDEO)
    write(out/"independent.json",{
        "status":"pass","reopened_master":source,"reopened_master_motion":motion,
        "reimported_GLTF":roundtrip,"GLB_transport":glb_proof,"video_full_decode":decoded,
        "files_verified_sha256":{name:sha(delivery/name) for name in [BLEND,GLB,VIDEO,"s5_layout.json"]},
    })


def main():
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument("output",type=Path)
    args.add_argument("--repo",type=Path)
    args.add_argument("--verify",type=Path)
    args.add_argument("--smoke",action="store_true")
    ns=args.parse_args(sys.argv[sys.argv.index("--")+1:])
    repo=ns.repo or Path(__file__).resolve().parents[6]
    prepare_output(ns.output)
    if ns.verify:
        verify(repo.resolve(),ns.verify.resolve(),ns.output.resolve())
    else:
        build(repo.resolve(),ns.output.resolve(),ns.smoke)


if __name__=="__main__":
    main()
