"""Build the Fog_Start candidate, or verify the actual delivery in a fresh Blender process."""
import argparse
import hashlib
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


def project_root():
    for location in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        for parent in (location, *location.parents):
            if (parent / "AGENTS.md").is_file() and (parent / "Assets").is_dir():
                return parent
    raise FileNotFoundError("Run from the Feather & Tide project or the delivered candidate folder")


ROOT = project_root()
LIB = ROOT / "Assets/Watercolor/Goose/Blender"
ENV = LIB / "ENV-018/v001"
SCALE = 27.5 / .9900
FRAME = (852, 393)
FRAME_RATE = 12
SOURCE_FRAMES = 48
PERIOD = 12.0
BLEND = "FX-004_Fog_Start.blend"
GLB = "FX-004_Fog_Start.glb"
TEXTURES = ("low_blue", "shore_warm", "distance_wash")
KINDS = (("LowWest", 0, -6.95, 10.25, .24, 7.1, .63, .59, .18),
         ("LowEast", 0, 6.7, 11.8, .30, 7.25, .74, .79, .38),
         ("ShoreWest", 1, -9.2, 14.0, .57, 13.4, 1.36, .85, .03),
         ("ShoreEast", 1, 10.0, 17.6, .83, 14.6, 1.72, .99, .65),
         ("DistantWest", 2, -15.0, 25.0, 1.06, 22.2, 2.02, 1.24, .85),
         ("DistantEast", 2, 17.5, 33.0, 1.25, 24.0, 2.40, 1.30, .48))
CLOUDS = (("CloudPatch", -24.0, 55.0, 3.3, 2.12, 1.0),
          ("CloudStreak", 35.0, 74.0, 2.10, 1.64, 1.28))
UPSTREAM = ("ENV-018_atmosphere_cards.blend", "ENV-018_MistLow.glb",
            "ENV-018_CloudPatch.glb", "ENV-018_CloudStreak.glb", "README.md", "qa.json",
            "textures/ft_shared_atmosphere_mistlow_basecolor_alpha.png",
            "textures/ft_shared_atmosphere_cloudpatch_basecolor_alpha.png",
            "textures/ft_shared_atmosphere_cloudstreak_basecolor_alpha.png")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def append(path, category, names):
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        assert set(names).issubset(getattr(source, category)), (path, names)
        setattr(target, category, names)
    return list(getattr(target, category))


def packed_digest(image):
    return hashlib.sha256(image.packed_file.data).hexdigest()


def map_path(kind):
    return f"textures/ft_goose_fx_fog_start_{kind}_basecolor_alpha.png"


def upstream():
    manifest = json.loads((ENV / "asset_manifest.json").read_text())
    assert manifest["id"] == "ENV-018" and manifest["version"] == "v001"
    for filename in UPSTREAM:
        assert digest(ENV / filename) == manifest["files"][filename], filename
    path = ENV / "ENV-018_atmosphere_cards.blend"
    objects = append(path, "objects", ["MistLow", "CloudPatch", "CloudStreak"])
    for item in objects:
        image = next(node.image for node in item.data.materials[0].node_tree.nodes if node.type == "TEX_IMAGE")
        assert packed_digest(image) == manifest["textures"][item.name]["sha256"], item.name
    return objects


def smooth(x):
    u = np.clip(x, 0., 1.)
    return u*u*(3.-2.*u)


def pixels(image):
    values = np.empty(image.size[0]*image.size[1]*4, dtype=np.float32)
    image.pixels.foreach_get(values)
    return values.reshape(image.size[1], image.size[0], 4)


def write_png(path, rgba):
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name+data))
    height, width = rgba.shape[:2]
    rows = b"".join(b"\0"+row.tobytes() for row in rgba[::-1])
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def paint_texture(source, layer):
    """Carry source wash texture into softer, offset lobes with zero-alpha edges."""
    height, width = source.shape[:2]
    u, v = np.meshgrid(np.linspace(0, 1, width), np.linspace(0, 1, height))
    bend = v + .035*np.sin(u*13.+layer) + .023*np.sin(u*29.-v*3.0) + .012*np.sin(u*66+v*9)
    shapes = (
        ((.25,.42,.28,.31,.82), (.48,.36,.35,.24,.77), (.68,.51,.27,.35,.82), (.82,.46,.21,.17,.64)),
        ((.25,.59,.30,.32,.61), (.48,.52,.40,.34,.86), (.69,.45,.29,.29,.82), (.50,.32,.31,.15,.35)),
        ((.28,.51,.30,.38,.66), (.51,.41,.35,.37,.84), (.73,.57,.28,.32,.72), (.61,.63,.32,.19,.49)),
    )
    remainder = np.ones(u.shape)
    for x, y, a, b, weight in shapes[layer]:
        radius = np.sqrt(((u-x)/a)**2 + ((bend-y)/b)**2)
        remainder *= 1.-weight*smooth(1.10-radius)
    source_alpha = source[..., 3]
    gain = .79 + .21*np.clip(source_alpha / max(.001, source_alpha.max()), 0, 1)
    edge = smooth(np.minimum.reduce((u, v, 1-u, 1-v)) / .12)
    alpha = (.37, .51, .40)[layer]*(1.-remainder)*gain*edge
    palette = (((.664,.745,.781),(.855,.899,.892)),
               ((.797,.817,.779),(.98,.944,.842)),
               ((.739,.808,.835),(.944,.937,.858)))
    bottom, top = map(np.array, palette[layer])
    amount = smooth(.18 + .60*v + .16*u + .13*(1.-remainder))
    grain = np.clip((source[..., :3].mean(axis=2)-.60)*.033, -.009, .009)
    rgb = bottom + amount[..., np.newaxis]*(top-bottom) + grain[..., np.newaxis]
    return np.rint(np.dstack((rgb, alpha))*255).clip(0, 255).astype(np.uint8)


def group(parent, name):
    result = bpy.data.collections.new(name)
    parent.children.link(result)
    return result


def object_in(collection, name, data=None, position=(0, 0, 0)):
    item = bpy.data.objects.new(name, data)
    collection.objects.link(item)
    item.location = position
    return item


def mesh_object(collection, name, vertices, faces, material):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    if material:
        mesh.materials.append(material)
    return object_in(collection, name, mesh)


def matte(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = 1
    shader.inputs["Specular IOR Level"].default_value = .22
    return mat


def unlit(name, color, opacity, image=None):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, opacity)
    mat.surface_render_method = "BLENDED"
    mat.use_backface_culling = False
    mat.use_nodes = True
    n = mat.node_tree.nodes
    n.clear()
    links = mat.node_tree.links
    out = n.new("ShaderNodeOutputMaterial")
    out.location = (350, 80)
    mix = n.new("ShaderNodeMixShader")
    mix.location = (100, 80)
    transparent = n.new("ShaderNodeBsdfTransparent")
    transparent.location = (-155, 70)
    ink = n.new("ShaderNodeEmission")
    ink.location = (-155, -120)
    links.new(transparent.outputs["BSDF"], mix.inputs[1])
    links.new(ink.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    mix.inputs[0].default_value = opacity
    ink.inputs["Color"].default_value = (*color, 1)
    if image:
        texture = n.new("ShaderNodeTexImage")
        texture.name = "Packed RGBA"
        texture.location = (-650, -120)
        texture.image = image
        texture.extension = "EXTEND"
        links.new(texture.outputs["Color"], mix.inputs[2])
        links.new(texture.outputs["Alpha"], mix.inputs[0])
    return mat


def asset_card(collection, parent, row, material):
    name, _, x, y, z, w, h, amplitude, phase = row
    points = [(w*(i/4-.5), 0, h*(j/2-.5)) for j in range(3) for i in range(5)]
    quads = [(j*5+i, j*5+i+1, j*5+i+6, j*5+i+5) for j in range(2) for i in range(4)]
    triangles = [tri for a, b, c, d in quads for tri in ((a, b, c), (a, c, d))]
    item = mesh_object(collection, f"Fog_{name}", points, triangles, material)
    item.parent = parent
    item.location = (x, y, z)
    uv = item.data.uv_layers.new(name="FogUV")
    for loop in item.data.loops:
        px, _, pz = points[loop.vertex_index]
        uv.data[loop.index].uv = (px/w+.5, pz/h+.5)
    item["base_x_BU"] = x
    item["amplitude_BU"] = amplitude
    item["phase_turns"] = phase
    item["collision_enabled"] = False
    return item


def operator(scene, name, eye, aim, orthographic=None):
    data = bpy.data.cameras.new(name)
    data.sensor_fit = "VERTICAL"
    data.sensor_height = 24
    data.lens = 12 / math.tan(math.radians(50)/2)
    data.clip_start = .05 / SCALE
    data.clip_end = 30000 / SCALE
    cam = object_in(scene, name, data, eye)
    cam.rotation_euler = (Vector(aim)-cam.location).to_track_quat("-Z", "Y").to_euler()
    if orthographic:
        data.type = "ORTHO"
        data.sensor_fit = "HORIZONTAL"
        data.ortho_scale = orthographic
    return cam


def follow(camera, leader, heading=0, lift=0):
    x, y = leader
    back = 180 * math.cos(.48) / SCALE
    camera.location = (x - math.sin(heading)*back, y - math.cos(heading)*back,
                       (180*math.sin(.48)+lift)/SCALE)
    aim = Vector((x, y, (6+lift)/SCALE))
    camera.rotation_euler = (aim-camera.location).to_track_quat("-Z", "Y").to_euler()


def elongated_wash(name, a, b, scale, warm=False):
    mat = matte(name, a)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    tc = nodes.new("ShaderNodeTexCoord")
    frequency = nodes.new("ShaderNodeVectorMath")
    frequency.operation = "MULTIPLY"
    frequency.inputs[1].default_value = scale
    links.new(tc.outputs["Object"], frequency.inputs[0])
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.
    noise.inputs["Detail"].default_value = 2.
    noise.inputs["Roughness"].default_value = .57
    links.new(frequency.outputs["Vector"], noise.inputs["Vector"])
    ramps = nodes.new("ShaderNodeValToRGB")
    ramps.color_ramp.elements[0].position = .19
    ramps.color_ramp.elements[1].position = .76
    ramps.color_ramp.elements[0].color = (*a, 1.)
    ramps.color_ramp.elements[1].color = (*b, 1.)
    links.new(noise.outputs["Fac"], ramps.inputs[0])
    shader = nodes.get("Principled BSDF")
    if warm:
        # A broad dawn wash reveals the corridor through gaps between the near cards.
        separate = nodes.new("ShaderNodeSeparateXYZ")
        links.new(tc.outputs["Object"], separate.inputs[0])
        absolute = nodes.new("ShaderNodeMath")
        absolute.operation = "ABSOLUTE"
        links.new(separate.outputs["X"], absolute.inputs[0])
        falloff = nodes.new("ShaderNodeMapRange")
        falloff.interpolation_type = "SMOOTHSTEP"
        falloff.inputs["From Min"].default_value = 1.8
        falloff.inputs["From Max"].default_value = 17.
        falloff.inputs["To Min"].default_value = .88
        falloff.inputs["To Max"].default_value = 0.
        links.new(absolute.outputs[0], falloff.inputs["Value"])
        mix = nodes.new("ShaderNodeMixRGB")
        mix.inputs[2].default_value = (.403,.488,.410,1)
        links.new(falloff.outputs["Result"], mix.inputs[0])
        links.new(ramps.outputs[0], mix.inputs[1])
        links.new(mix.outputs[0], shader.inputs["Base Color"])
        links.new(mix.outputs[0], shader.inputs["Emission Color"])
        shader.inputs["Emission Strength"].default_value = .10
    else:
        links.new(ramps.outputs[0], shader.inputs["Base Color"])
    return mat


def ribbon(collection, name, rows, material):
    points = [point for row in rows for point in row]
    quads = [(i, i+1, i+3, i+2) for i in range(0, len(points)-2, 2)]
    return mesh_object(collection, name, points, quads, material)


def appearance_context(scene, clouds):
    context = group(scene.collection, "S0 wetland | review context only")
    wet_mud = elongated_wash("Dawn | saturated mud", (.142,.162,.108),(.297,.317,.232),(.68,.42,1))
    land = elongated_wash("Dawn | sage wetland", (.172,.226,.137),(.322,.359,.240),(.49,.34,1))
    water = elongated_wash("Dawn | luminous water", (.134,.261,.256),(.270,.405,.351),(.085,2.5,1), True)
    ys = np.linspace(-14, 265, 150)
    full = [[(-210, y, -.195), (210, y, -.195)] for y in ys]
    ribbon(context, "Shallow water", full, water)
    for side in (-1, 1):
        field, shore = [], []
        for y in ys:
            w = 2.65 + 2.0*math.exp(-((y-8)/9)**2) + .061*max(0,y)
            wave = .80*math.sin(.31*y + side*.8) + 1.1*math.sin(.11*y)
            edge = side*(w+wave) + .57*math.sin(.21*y)
            blend = side*(.45+.22*(1+math.sin(y*.53)))
            outer = side*211
            field.append(sorted(((edge+blend, y, -.11), (outer, y, -.11))))
            shore.append(sorted(((edge, y, -.193), (edge+blend, y, -.11))))
        ribbon(context, f"Wetland bank {side:+d}", field, land)
        ribbon(context, f"Waterline {side:+d}", shore, wet_mud)

    shelf_rows = []
    for y in np.linspace(-9., 4., 96):
        half = 4.0 * math.sqrt(max(0., 1.-((y+2.5)/6.53)**2))
        width = half * (1. + .062*math.cos(y*2.4) + .055*math.sin(y*3.2))
        center = .12*math.sin(y*1.85)+.11*math.sin(y*2.9)
        shelf_rows.append([(center-width, y, -.046), (center+width, y, -.046)])
    ribbon(context, "Soft-sided muddy shelf", shelf_rows, wet_mud)
    fringe = elongated_wash("Dawn | damp waterline",(.232,.270,.180),(.368,.382,.275),(.79,.54,1))
    for side,index in ((-1,0),(1,1)):
        shore_rows = []
        for pair in shelf_rows:
            x,y,z = pair[index]
            width = .29 + .15*math.sin(1.6*y+side)
            shore_rows.append(sorted(((x-side*.006,y,z+.0002),
                                      (x+side*width,y,-.190))))
        ribbon(context,f"Mud shelf waterline {side:+d}",shore_rows,fringe)

    reeds = append(LIB/"ENV-004/v001/ENV-004_reeds.blend", "objects",
                   ["Reed_A_Height_M", "Reed_B_Height_M", "Reed_C_Height_S"])
    generator = np.random.default_rng(404)
    for index in range(142):
        side = (-1, 1)[index % 2]
        y = float(generator.uniform(-2.6, 39))
        edge = 2.65 + 2.0*math.exp(-((y-8)/9)**2) + .061*max(0,y)
        edge += .80*math.sin(.31*y+side*.8) + 1.1*math.sin(.11*y)
        x = side*(edge+float(generator.uniform(.38, 4.7))) + .57*math.sin(.21*y)
        reed = object_in(context, f"Review reed {index+1}", reeds[index%3].data, (x, y, -.101))
        reed.rotation_euler.z = float(generator.uniform(-math.pi, math.pi))
        reed.scale = (value := float(generator.uniform(.64,1.29)), value, value)

    ridges = append(LIB/"ENV-009/v001/ENV-009_far_ridges.blend", "objects", ["FarRidge_A", "FarRidge_B", "FarRidge_C"])
    for index,(x,y,z,scale) in enumerate(((-41,65,0,1.78),(42,75,.06,1.75),(-8,105,.15,2.2))):
        mountain = object_in(context, f"ENV-009 | distance ridge {index+1}", ridges[index].data, (x,y,z))
        mountain.scale = (scale,1,scale)
    # Preserve the source cloud card shapes and pack their actual upstream textures with the review.
    for placement, source in zip(CLOUDS, clouds):
        name, x, y, z, sx, sz = placement
        item = object_in(context, f"Review_ENV018_{name}", source.data, (x,y,z))
        item.scale = (sx,1,sz)
        item["review_only"] = True

    base = runpy.run_path(str(LIB/"ENV-001/v001/ENV-001_generate.py"))
    goose = base["add_goose"](context)
    goose.name = "Review_Leader_CHR001"
    goose.location = (0,0,8/SCALE)
    for idx,(x,y) in enumerate(((-1.29,-.49),(1.32,-.48),(-.73,1.08),(.76,1.12))):
        follower = object_in(context, f"Review_Follower_{idx+1}", goose.data, (x,y,6/SCALE))
        follower.scale = (.72,.72,.72)
        follower.rotation_euler.z = (-.10,.09,-.14,.15)[idx]
    return context


def driver_for(item, path, variables, expression, index=None):
    driver = (item.driver_add(path, index) if index is not None else item.driver_add(path)).driver
    driver.type = "SCRIPTED"
    for name, target, target_path in variables:
        v = driver.variables.new()
        v.name, v.type = name, "SINGLE_PROP"
        v.targets[0].id = target
        v.targets[0].data_path = target_path
    driver.expression = expression


def install_controls(ctrl, cards, materials, cloud_cards):
    specs = {"opacity_strength": (1.,0.,1.,"Global fog alpha multiplier"),
             "motion_strength": (1.,0.,1.,"Horizontal drift amplitude multiplier"),
             "period_seconds": (PERIOD,1.,60.,"Seconds for one full drift"),
             "phase_turns": (0.,0.,1.,"Phase offset in revolutions")}
    for label, (value, lo, hi, description) in specs.items():
        ctrl[label] = value
        ctrl.id_properties_ui(label).update(min=lo, max=hi, description=description)
    for item in cards:
        driver_for(item, "location", [
            ("base",item,'["base_x_BU"]'),("amp",item,'["amplitude_BU"]'),
            ("phase",item,'["phase_turns"]'),("global_phase",ctrl,'["phase_turns"]'),
            ("motion",ctrl,'["motion_strength"]'),("period",ctrl,'["period_seconds"]')],
            f"base+amp*motion*sin(6.283185307179586*(phase+global_phase+(frame-1)/({FRAME_RATE}*period)))", 0)
    for mat in materials:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        gain = nodes.new("ShaderNodeMath")
        gain.name = "Fog opacity control"
        gain.label = "Fog_Start · opacity strength"
        gain.operation = "MULTIPLY"
        gain.location = (-315, 180)
        gain.inputs[1].default_value = 1.
        mat.node_tree.animation_data_create()
        driver_for(gain.inputs[1], "default_value",
                   [("opacity",ctrl,'["opacity_strength"]')], "opacity")
        links.new(nodes["Packed RGBA"].outputs["Alpha"],gain.inputs[0])
        mix = next(n for n in nodes if n.type=="MIX_SHADER")
        links.new(gain.outputs[0], mix.inputs[0])
    for item in cloud_cards:
        local = item.data.materials[0].copy()
        local.name = f"{item.name} | review opacity"
        item.material_slots[0].link = "OBJECT"
        item.material_slots[0].material = local
        nodes, links = local.node_tree.nodes, local.node_tree.links
        texture = next(n for n in nodes if n.type == "TEX_IMAGE")
        shader = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
        gain = nodes.new("ShaderNodeMath")
        gain.operation = "MULTIPLY"
        driver_for(gain.inputs[1], "default_value", [("opacity",ctrl,'["opacity_strength"]')], "opacity")
        links.new(texture.outputs["Alpha"], gain.inputs[0])
        links.new(gain.outputs[0], shader.inputs["Alpha"])


def mode(scene, ctrl, value, frame):
    ctrl["opacity_strength"] = value
    ctrl["motion_strength"] = value
    ctrl.update_tag()
    scene.frame_set(frame)
    bpy.context.view_layer.update()


def render(scene, path, samples=8):
    scene.cycles.samples = samples
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def load_alpha(image):
    return pixels(image)[..., 3]


def sample_alpha(mask, u, v):
    if not 0 <= u <= 1 or not 0 <= v <= 1:
        return 0.
    h, w = mask.shape
    x = min(w-1,max(0,u*w-.5))
    y = min(h-1,max(0,v*h-.5))
    ix, iy = int(x), int(y)
    jx, jy = min(ix+1,w-1), min(iy+1,h-1)
    fx, fy = x-ix, y-iy
    return float((1-fy)*((1-fx)*mask[iy,ix]+fx*mask[iy,jx])
                 +fy*((1-fx)*mask[jy,ix]+fx*mask[jy,jx]))


def trace(eye, target, layers, strength):
    transmission = 1.
    difference = target-eye
    for center, w, h, mask in layers:
        t = (center.y-eye.y)/difference.y
        if 0. < t < 1.:
            delta = eye + t*difference-center
            transmission *= (1.-strength*sample_alpha(mask, delta.x/w+.5, delta.z/h+.5))
    return 1.-transmission


def viewing_layers(cards, clouds):
    layers = []
    for row,item in zip(KINDS,cards):
        material = item.material_slots[0].material
        texture = next(n.image for n in material.node_tree.nodes if n.type=="TEX_IMAGE")
        layers.append((item,*row[5:7],load_alpha(texture)))
    far_sizes = {"CloudPatch":(13.5,3.85), "CloudStreak":(20,1.55)}
    for row,item in zip(CLOUDS,clouds):
        material = item.material_slots[0].material
        texture = next(n.image for n in material.node_tree.nodes if n.type=="TEX_IMAGE")
        w,h = far_sizes[row[0]]
        layers.append((item,w*item.scale.x,h*item.scale.z,load_alpha(texture)))
    return layers


def visibility(scene, cam, cards, clouds, ctrl):
    layers = viewing_layers(cards,clouds)
    poses = (((0,0),0,0),((-.34,1.3),-.028,2.5),((.46,2.6),.045,5))
    corridor = [Vector((x,y,z)) for x in (-.88,0,.88) for y in (4.2,6.5,9.5,13.8,20.,31.)
                for z in (.14,.45,.83,1.18)]
    starts = [Vector((x,y,z)) for x in (-1.65,-.9,0,.9,1.65) for y in (.3,.85,1.4)
              for z in (.07,.32,.52)]
    limits = {1.: .075, .35: .028, 0.: 0.}
    frame_width, frame_height = FRAME
    guard = []
    for safe_left, safe_bottom in ((0,0),(32,21),(64,34)):
        center_x = safe_left+28+108
        center_from_bottom = safe_bottom+24+108
        guard.extend((center_x+radius*math.cos(phase*math.tau/32),
                      center_from_bottom+radius*math.sin(phase*math.tau/32))
                     for radius in (0,36,72,95) for phase in range(32))
    result = {}
    for strength, cap in limits.items():
        opacity_max = dict(start=0., corridor=0., stick=0., flank=0.)
        samples = dict.fromkeys(opacity_max,0)
        for leader, heading, lift in poses:
            follow(cam,leader,heading,lift)
            for frame in range(1,145,9):
                mode(scene,ctrl,strength,frame)
                transforms = [(item.matrix_world.translation,w,h,mask) for item,w,h,mask in layers]
                eye = cam.matrix_world.translation
                for name, targets in (("start",starts),("corridor",corridor)):
                    for target in targets:
                        p = world_to_camera_view(scene,cam,target)
                        assert p.z > 0 and 0. < p.x < 1. and 0. < p.y < 1., (name,target,p)
                        opacity_max[name] = max(opacity_max[name],trace(eye,target,transforms,strength))
                        samples[name] += 1
                for x, y in guard:
                    # Use an unterminated screen ray to conservatively include all card depths.
                    nx,ny = 2*x/frame_width-1.,2*y/frame_height-1.
                    projection = math.tan(math.radians(25))
                    far = cam.matrix_world @ Vector((nx*frame_width/frame_height*projection*200,
                                                     ny*projection*200,-200))
                    opacity_max["stick"] = max(opacity_max["stick"],trace(eye,far,transforms,strength))
                    samples["stick"] += 1
                for item,w,h,_ in layers[:len(cards)]:
                    for px,pz in ((-.14,0),(0,0),(.12,.10)):
                        ray = item.matrix_world.translation + Vector((px*w,0,pz*h))-eye
                        opacity_max["flank"] = max(opacity_max["flank"],
                                                   trace(eye,eye+ray*1.2,transforms,strength))
                        samples["flank"] += 1
        assert opacity_max["start"] <= cap and opacity_max["corridor"] <= cap, opacity_max
        assert opacity_max["stick"] <= .01, opacity_max
        if strength:
            assert opacity_max["flank"] > .08*strength, opacity_max
        else:
            assert opacity_max["flank"] == 0., opacity_max
        result[str(strength)] = {"sample_count": samples, "max_composite_alpha": opacity_max,
                                 "route_alpha_limit": cap, "stick_alpha_limit": .01}
    follow(cam,(0,0))
    mode(scene,ctrl,1.,1)
    return {"camera_poses": poses, "motion_phases_per_pose": 16, "settings": result,
            "safe_insets_examples_left_bottom_px": [[0,0],[32,21],[64,34]],
            "joystick_reference": {"leftInset":28,"bottomInset":24,"radius":72,"grabRadius":108,"fullTravelVisualRadius":95},
            "method": "Trace rays through all card planes and bilinearly sample alpha; multiply transmittance."}


def raw_glb(path):
    data = path.read_bytes()
    assert struct.unpack_from("<4sII",data) == (b"glTF",2,len(data))
    size, tag = struct.unpack_from("<II",data,12)
    assert tag == 0x4E4F534A
    return json.loads(data[20:20+size]), data[28+size:]


def view_bytes(doc, buffer, index):
    view = doc["bufferViews"][index]
    offset = view.get("byteOffset",0)
    return buffer[offset:offset+view["byteLength"]]


def file_report(path):
    gltf, binary = raw_glb(path)
    assert not gltf.get("animations") and not gltf.get("cameras")
    root = next(node for node in gltf["nodes"] if node["name"]=="Fog_Start")
    assert root.get("translation",[0,0,0]) == [0,0,0]
    assert root.get("scale",[1,1,1]) == [1,1,1]
    assert root["extras"]["collision_enabled"] is False
    assert len(root["children"]) == len(KINDS) and len(gltf["images"]) == len(TEXTURES)
    report = {}
    for row in KINDS:
        name, layer, x, y, z, w, h, _, _ = row
        node = next(node for node in gltf["nodes"] if node["name"]==f"Fog_{name}")
        assert node in [gltf["nodes"][index] for index in root["children"]]
        assert np.allclose(node["translation"],[x,z,-y],atol=1e-6)
        geometry, = gltf["meshes"][node["mesh"]]["primitives"]
        assert gltf["accessors"][geometry["indices"]]["count"] == 48
        accessor = gltf["accessors"][geometry["attributes"]["POSITION"]]
        assert np.allclose([accessor["min"],accessor["max"]],[[-w/2,-h/2,0],[w/2,h/2,0]],atol=1e-6)
        material = gltf["materials"][geometry["material"]]
        assert material["alphaMode"]=="BLEND" and material["doubleSided"]
        assert "KHR_materials_unlit" in material["extensions"]
        texture = gltf["textures"][material["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
        assert all(gltf["samplers"][texture["sampler"]][axis]==33071 for axis in ["wrapS","wrapT"])
        image = gltf["images"][texture["source"]]
        sha = hashlib.sha256(view_bytes(gltf,binary,image["bufferView"])).hexdigest()
        assert sha == digest(path.parent/map_path(TEXTURES[layer]))
        report[node["name"]] = {"triangles":16,"center_glTF":[x,z,-y],
                                "width_height_BU":[w,h],"image_sha256":sha,
                                "double_sided":True,"alpha_mode":"BLEND","wrap":"CLAMP_TO_EDGE"}
    return report


def init_scene(scene, lights):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.use_denoising = True
    scene.cycles.transparent_max_bounces = 12
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.resolution_x, scene.render.resolution_y = FRAME
    scene.render.resolution_percentage = 100
    scene.render.fps = FRAME_RATE
    scene.frame_start, scene.frame_end = 1, int(PERIOD*FRAME_RATE)+1
    scene.view_settings.view_transform = "AgX"
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("Morning sky")
    scene.world.use_nodes = True
    n = scene.world.node_tree.nodes
    n.get("Background").inputs["Color"].default_value = (.57,.66,.70,1)
    n.get("Background").inputs["Strength"].default_value = .48
    sun = bpy.data.lights.new("Soft morning sun", "SUN")
    sun.energy, sun.angle, sun.color = 1.35,.17,(1.,.89,.72)
    light = object_in(lights, "Soft morning sun", sun, (0,12,8))
    light.rotation_euler = (Vector((0,1,0))-light.location).to_track_quat("-Z","Y").to_euler()


def verify_camera_source():
    rig = ROOT/"Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift"
    source = rig.read_text()
    assert re.search(r"ThirdPersonRig\(distance: 180, pitch: 0\.48, fieldOfViewDegrees: 50\)",source)
    assert "height: Float(6 + lift)" in source
    view = ROOT/"Sources/FeatherTide/Rendering/PlayfieldView.swift"
    assert "body.leader ? 8 : 6" in view.read_text()
    stick = ROOT/"Sources/FeatherTide/Systems/Input/PlayfieldPilot.swift"
    for name,value in (("radius",72),("grabRadius",108),("fixedInset",28),("fixedBottomInset",24)):
        assert f"static let {name}: CGFloat = {value}" in stick.read_text()
    return {str(path.relative_to(ROOT)): digest(path) for path in (rig,view,stick)}


def startup(output):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source = upstream()
    scene = bpy.context.scene
    scene.name = "FX-004 | S0 fixed rear review"
    review = group(scene.collection,"Review cameras and lights")
    geometry = group(scene.collection,"Fog_Start | editable runtime cards")
    control = object_in(geometry,"Fog_Start")
    control.empty_display_size = .6
    control["variant"] = "Fog_Start"
    control["collision_enabled"] = False
    control["coordinate_axes"] = "Blender +Z up / +Y forward; glTF +Y up / -Z forward"
    control.asset_mark()
    init_scene(scene,review)
    cam = operator(review,"Fixed rear | ThirdPersonRig", (0,-5.75,3), (0,0,.216))
    follow(cam,(0,0))
    diagnostic = operator(review,"Diagnostic | high oblique", (21,-15,28), (0,14,.3), 54.)
    scene.camera = cam
    context = appearance_context(scene,source[1:])
    clouds = [bpy.data.objects[f"Review_ENV018_{name}"] for name,*_ in CLOUDS]
    gray = [unlit("Graybox · fog card "+str(i+1),(.54,.62,.65),.16) for i in range(3)]
    cards = [asset_card(geometry,control,row,gray[row[1]]) for row in KINDS]
    bpy.context.view_layer.update()
    slots = [(item, [slot.material for slot in item.material_slots]) for item in context.objects
             if item.type == "MESH" and not item.hide_render and not item.name.startswith("Review_ENV018_")]
    review_gray = [matte("Graybox · ground",(.31,.34,.35)),matte("Graybox · shallow water",(.19,.23,.24)),
                   matte("Graybox · flock",(.62,.63,.62)),matte("Graybox · reeds",(.20,.24,.25))]
    for item, materials in slots:
        slot_idx = 1 if item.name=="Shallow water" else 2 if item.name.startswith(("Review_Leader","Review_Follower")) else 3 if item.name.startswith("Review reed") else 0
        for slot in item.material_slots:
            slot.link = "OBJECT"
            slot.material = review_gray[slot_idx]
    for item in clouds:
        item.hide_render = True
    render(scene,output/"graybox_fixed_rear.png")
    scene.camera = diagnostic
    render(scene,output/"graybox_layout.png")
    scene.camera = cam
    for item, materials in slots:
        for slot, mat in zip(item.material_slots,materials):
            slot.material = mat
    for item in clouds:
        item.hide_render = False
    texture_folder = output/"textures"
    texture_folder.mkdir()
    material = []
    texture_report = {}
    for index, kind in enumerate(TEXTURES):
        original = next(n.image for n in source[index].data.materials[0].node_tree.nodes if n.type=="TEX_IMAGE")
        rgba = paint_texture(pixels(original),index)
        path = output/map_path(kind)
        write_png(path,rgba)
        image = bpy.data.images.load(str(path),check_existing=False)
        image.alpha_mode = "STRAIGHT"
        image.pack()
        image.filepath = "//"+map_path(kind)
        alpha = rgba[...,3]
        assert not np.any(np.concatenate((alpha[0],alpha[-1],alpha[:,0],alpha[:,-1])))
        assert 40 <= int(alpha.max()) <= 132
        texture_report[kind] = {"path":map_path(kind),"sha256":digest(path),"alpha_max_rgb8":int(alpha.max()),
                                "nonzero_alpha_pixels":int(np.count_nonzero(alpha)),
                                "width_height_px":[image.size[0],image.size[1]],
                                "source": original.name, "source_packed_sha256":packed_digest(original)}
        material.append(unlit(f"Fog_Start_{kind}",(.78,.82,.83),1.,image))
    for row, item in zip(KINDS,cards):
        item.data.materials[0] = material[row[1]]
    bpy.ops.object.select_all(action="DESELECT")
    for item in [control,*cards]:
        item.select_set(True)
    bpy.context.view_layer.objects.active = control
    result = bpy.ops.export_scene.gltf(filepath=str(output/GLB), use_selection=True,
                                       export_format="GLB", export_yup=True,export_animations=False,
                                       export_extras=True,export_image_format="AUTO")
    assert "FINISHED" in result
    export = file_report(output/GLB)
    install_controls(control,cards,material,clouds)
    for i,value in enumerate((1.,.35,0.)):
        mode(scene,control,value,1)
        render(scene,output/f"preview_fixed_rear_{('default','reduced','off')[i]}.png",samples=12)
    mode(scene,control,1.,55)
    render(scene,output/"preview_fixed_rear_drift.png",samples=10)
    scene.camera = diagnostic
    render(scene,output/"preview_layout.png")
    scene.camera = cam
    mode(scene,control,1.,1)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                view = area.spaces.active
                view.region_3d.view_perspective = "CAMERA"
                view.region_3d.view_camera_zoom = 7.
                view.overlay.show_overlays = False
                view.shading.color_type = "MATERIAL"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output/BLEND),compress=True)
    write(output/"build_report.json", {"camera_sources":verify_camera_source(),"glb":export,
                                      "blender":bpy.app.version_string,"textures":texture_report,
                                      "upstream_hashes":{str((ENV/n).relative_to(ROOT)):digest(ENV/n)
                                                         for n in (*UPSTREAM,"asset_manifest.json")}})


def roundtrip(scene, cam, output, delivery, control, cards, clouds):
    # Native default pose drifts; compare static exports after dialing motion to zero.
    control["motion_strength"] = 0.
    control.update_tag()
    scene.frame_set(1)
    render(scene,output/"roundtrip_native_reference.png",samples=10)
    for item in cards:
        item.hide_render = True
    for item in clouds:
        assert item.visible_get()
    old = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(delivery/GLB))
    imported = list(set(bpy.data.objects)-old)
    root, = [o for o in imported if o.type=="EMPTY"]
    assert root.parent is None and root.location.length < 1e-7
    assert np.allclose(root.scale,[1,1,1],atol=1e-7)
    assert root["collision_enabled"] is False
    for row, saved in zip(KINDS,cards):
        name = f"Fog_{row[0]}"
        new, = [o for o in imported if o.name.split(".")[0]==name]
        assert new.parent == root
        assert (new.location-saved.location).length < 1e-6
        assert np.allclose(new.scale,[1,1,1],atol=1e-7)
        assert len(new.data.polygons)==16
        assert len(new.data.uv_layers)==1
        source_uv = {tuple(round(v,5) for v in loop.uv) for loop in saved.data.uv_layers[0].data}
        imported_uv = {tuple(round(v,5) for v in loop.uv) for loop in new.data.uv_layers[0].data}
        assert source_uv==imported_uv
        for polygon in new.data.polygons:
            assert polygon.normal.y < -.99999
        texture = next(n.image for n in new.data.materials[0].node_tree.nodes if n.type=="TEX_IMAGE")
        assert packed_digest(texture)==digest(delivery/map_path(TEXTURES[row[1]]))
    render(scene,output/"preview_glb_roundtrip.png",samples=10)
    for item in imported:
        bpy.data.objects.remove(item,do_unlink=True)
    for item in cards:
        item.hide_render = False
    mode(scene,control,1.,1)


def reopen(output, delivery, video):
    bpy.ops.wm.open_mainfile(filepath=str(delivery/BLEND))
    scene = bpy.context.scene
    cam = bpy.data.objects["Fixed rear | ThirdPersonRig"]
    ctrl = bpy.data.objects["Fog_Start"]
    cards = [bpy.data.objects[f"Fog_{row[0]}"] for row in KINDS]
    clouds = [bpy.data.objects[f"Review_ENV018_{name}"] for name,*_ in CLOUDS]
    assert scene.camera==cam and (scene.render.resolution_x,scene.render.resolution_y)==FRAME
    check_alpha = {}
    camera_matrix = cam.matrix_world.copy()
    for amount in (1.,.35,0.):
        samples = []
        for frame in (1,37,73,109,145):
            mode(scene,ctrl,amount,frame)
            bpy.context.view_layer.update()
            assert all((a-b).length < 1e-10 for a,b in zip(cam.matrix_world.col,camera_matrix.col))
            samples.append([tuple(item.matrix_world.translation) for item in cards])
            graph = bpy.context.evaluated_depsgraph_get()
            for item in cards:
                gain = item.material_slots[0].material.node_tree.evaluated_get(graph).nodes["Fog opacity control"]
                assert abs(gain.inputs[1].default_value-amount)<1e-6, (gain.inputs[1].default_value, amount)
        positions = np.asarray(samples)
        base_positions = np.asarray([row[2:5] for row in KINDS])
        assert np.max(np.abs(positions[0]-positions[-1]))<2e-6
        assert np.max(np.abs(positions[:,:,1:]-base_positions[None,:,1:]))<2e-6
        motion = np.max(np.abs(positions[:,:,0]-base_positions[None,:,0]))
        assert (motion>.5*amount) if amount>0 else (motion<2e-6)
        check_alpha[str(amount)] = {"measured_peak_abs_horizontal_motion_BU":float(motion),
                                   "cycle_closure_error_BU":float(np.max(np.abs(positions[0]-positions[-1]))),
                                   "sampled_material_gain":amount}
    evidence = visibility(scene,cam,cards,clouds,ctrl)
    roundtrip(scene,cam,output,delivery,ctrl,cards,clouds)
    write(output/"recheck.json",{"visibility":evidence, "material_motion_controls":check_alpha,
                                "raw_glb":file_report(delivery/GLB),
                                "source_files_sha256":{n:digest(delivery/n) for n in (BLEND,GLB)}})
    if video:
        sequence = output/"frames"
        sequence.mkdir()
        for frame in range(1,SOURCE_FRAMES+1):
            mode(scene,ctrl,1.,frame)
            render(scene,sequence/f"fog_{frame:04d}.png",samples=4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("--verify",type=Path)
    parser.add_argument("--video",action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    assert not list(out.iterdir()), f"Output must be empty: {out}"
    if args.verify:
        reopen(out,args.verify.resolve(),args.video)
    else:
        startup(out)


if __name__=="__main__":
    main()
