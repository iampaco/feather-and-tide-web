"""Package the approved goose model for Web and extract the pose clips."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import struct

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public/assets"
MODELS = "Assets/Watercolor/Goose/Blender"
GOOSE_TEXTURE_SIZE = 512

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read_glb(path):
    data = path.read_bytes()
    magic, version, total, length, chunk_type = struct.unpack_from("<4sIIII", data)
    if (magic, version, total, chunk_type) != (b"glTF", 2, len(data), 0x4E4F534A):
        raise ValueError(f"Unexpected GLB header at {path}")
    binary_length, kind = struct.unpack_from("<II", data, 20 + length)
    if kind != 0x004E4942:
        raise ValueError(f"Missing binary at {path}")
    offset = 28 + length
    return json.loads(data[20:20 + length]), data[offset:offset + binary_length]

def write_glb(tree, binary):
    document = json.dumps(tree, separators=(",", ":")).encode()
    document += b" " * (-len(document) % 4)
    prefix = struct.pack("<4sIIII", b"glTF", 2, 28 + len(document) + len(binary), len(document), 0x4E4F534A)
    return prefix + document + struct.pack("<II", len(binary), 0x004E4942) + binary

def web_goose(source):
    tree, raw = read_glb(source)
    if len(tree["buffers"]) != 1:
        raise ValueError("Expected one embedded glTF buffer")
    image_views = {image["bufferView"] for image in tree["images"]}
    accessor_views = {item.get("bufferView") for item in tree["accessors"]}
    if image_views & accessor_views:
        raise ValueError("Goose textures must have their own buffer views")

    binary = bytearray()
    for i, view in enumerate(tree["bufferViews"]):
        offset = view.get("byteOffset", 0)
        payload = raw[offset:offset + view["byteLength"]]
        if i in image_views:
            with Image.open(BytesIO(payload)) as image:
                if image.format != "PNG" or image.mode != "RGB":
                    raise ValueError("Expected an opaque PNG goose texture")
                resized = image.resize((GOOSE_TEXTURE_SIZE, GOOSE_TEXTURE_SIZE), Image.Resampling.LANCZOS)
                png = BytesIO()
                resized.save(png, format="PNG", optimize=True)
                payload = png.getvalue()
        view.update(byteOffset=len(binary), byteLength=len(payload))
        binary.extend(payload)
        binary.extend(b"\0" * (-len(binary) % 4))
    tree["buffers"][0]["byteLength"] = len(binary)
    return write_glb(tree, binary)

def clips_only(source):
    tree, raw = read_glb(source)
    animations = tree["animations"]
    nodes = []
    accessors = []
    views = []
    binary = bytearray()
    node_ids, accessor_ids = {}, {}

    def extract_node(index):
        if index not in node_ids:
            node_ids[index] = len(nodes)
            nodes.append({"name": tree["nodes"][index]["name"]})
        return node_ids[index]

    def extract_accessor(index):
        if index not in accessor_ids:
            item = dict(tree["accessors"][index])
            view = tree["bufferViews"][item["bufferView"]]
            offset = view.get("byteOffset", 0)
            if view["buffer"] != 0:
                raise ValueError("Expected one embedded glTF buffer")
            start = len(binary)
            binary.extend(raw[offset:offset + view["byteLength"]])
            binary.extend(b"\0" * (-len(binary) % 4))
            new_view = {**view, "byteOffset": start}
            item["bufferView"] = len(views)
            views.append(new_view)
            accessor_ids[index] = len(accessors)
            accessors.append(item)
        return accessor_ids[index]

    for animation in animations:
        for channel in animation["channels"]:
            target = channel["target"]
            target["node"] = extract_node(target["node"])
        for sampler in animation["samplers"]:
            for key in ("input", "output"):
                sampler[key] = extract_accessor(sampler[key])

    result = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "animations": animations,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
    }
    return write_glb(result, binary)

def main():
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    base = next(entry for entry in manifest["assets"] if entry["assetId"] == "ANM-001")
    source_file = ROOT / base["source"]
    payload = web_goose(source_file)
    base.update(
        version="v002", url="goose/cruise-v002.glb", size=len(payload),
        sha256=digest(payload), sourceSha256=digest(source_file.read_bytes()),
        textureSize=GOOSE_TEXTURE_SIZE,
        conversion=f"Pillow Lanczos to {GOOSE_TEXTURE_SIZE} × {GOOSE_TEXTURE_SIZE} embedded RGB PNG; original rig and animation",
    )
    (OUT / base["url"]).write_bytes(payload)
    manifest["assets"] = [base]
    sources = {
        "ANM-002": "takeoff_climb",
        "ANM-003": "glide_circle",
        "ANM-006": "formation_blend",
        "ANM-007": "landing",
        "ANM-009": "call_rejoin",
    }
    for asset_id, name in sources.items():
        source = f"{MODELS}/{asset_id}/v001/{asset_id}_{name}.glb"
        file = ROOT / source
        tree, _ = read_glb(file)
        url = f"goose/{asset_id.lower()}-clips-v001.glb"
        payload = clips_only(file)
        (OUT / url).write_bytes(payload)
        manifest["assets"].append({
            "assetId": asset_id, "version": "v001", "url": url, "source": source,
            "rights": "Original project animation per Assets/docs/asset-ledger.md. Runtime prototype pending art review.",
            "size": len(payload), "sha256": digest(payload), "sourceSha256": digest(file.read_bytes()),
            "forward": "-Z", "up": "+Y", "pivot": "body", "clipsOnly": True,
            "clips": [item["name"] for item in tree["animations"]], "segments": base["segments"],
        })
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
