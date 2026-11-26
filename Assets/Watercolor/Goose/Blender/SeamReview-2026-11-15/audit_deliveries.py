"""Audit candidate outputs, local README links, their manifest hashes and complete video decoding."""
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
from urllib.parse import unquote, urlsplit


TARGETS = ("FX-002", "FX-003", "LVL-S0", "LVL-S1", "LVL-S2", "LVL-S3", "LVL-S5", "LVL-S6")
REQUIRED = ("README.md", "asset_manifest.json", "qa.json")
GLB_MAGIC = b"glTF"
LOCAL_MARKDOWN_LINK = re.compile(r"\[[^\]\n]*\]\(\s*(<[^>]+>|[^)\n]+)\)")
HASH = re.compile("[0-9a-fA-F]{64}")


def file_hash(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def manifest_hashes(manifest):
    for key in ("files", "files_sha256", "file_sha256", "sha256"):
        rows = manifest.get(key)
        if isinstance(rows, list):
            rows = {row["path"]: row for row in rows if isinstance(row, dict) and "path" in row}
        if isinstance(rows, dict):
            for name, expected in rows.items():
                digest = expected.get("sha256") if isinstance(expected, dict) else expected
                if isinstance(digest, str) and HASH.fullmatch(digest):
                    yield name, digest.lower()


def inspect_glb(path):
    with path.open("rb") as handle:
        magic, version, declared_size = struct.unpack("<4sII", handle.read(12))
        assert (magic, version, declared_size) == (GLB_MAGIC, 2, path.stat().st_size)
        n, kind = struct.unpack("<II", handle.read(8))
        assert kind == 0x4E4F534A
        doc = json.loads(handle.read(n))
    assert doc.get("scenes") and doc.get("meshes"), path
    assert all(not node.get("uri") or node["uri"].startswith("data:") for node in doc.get("images", [])), path
    return {
        "meshes": len(doc.get("meshes", [])),
        "nodes": len(doc.get("nodes", [])),
        "images": len(doc.get("images", [])),
        "animations": [item.get("name") for item in doc.get("animations", [])],
    }


def video(path):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, check=True, text=True,
    )
    doc = json.loads(probe.stdout)
    tracks = doc["streams"]
    track = next(item for item in tracks if item["codec_type"] == "video")
    assert track["width"] == 852 and track["height"] in (393, 394), track
    assert int(track["nb_read_frames"]) > 1
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"],
        check=True, capture_output=True,
    )
    return {"frames_decoded": int(track["nb_read_frames"]), "width": track["width"], "height": track["height"],
            "duration_s": float(doc["format"]["duration"]), "audio_tracks": sum(item["codec_type"] == "audio" for item in tracks)}


def links(folder):
    readme = (folder / "README.md").read_text()
    items, bad = [], []
    for raw in LOCAL_MARKDOWN_LINK.findall(readme):
        raw = raw.strip().strip("<>")
        value = urlsplit(raw)
        if value.scheme or value.netloc or not value.path:
            continue
        name = unquote(value.path)
        path = folder / name
        (items if path.exists() else bad).append(name)
    return sorted(set(items)), sorted(set(bad))


def asset_audit(library, asset):
    folder = library / asset / "v001"
    missing = [name for name in REQUIRED if not (folder / name).is_file()]
    if missing:
        return {"asset": asset, "status": "incomplete", "missing": missing}
    manifest = json.loads((folder / "asset_manifest.json").read_text())
    qa = json.loads((folder / "qa.json").read_text())
    names = sorted(p for p in folder.rglob("*") if p.is_file() and not p.name.startswith("."))
    blends = sorted(p for p in names if p.suffix == ".blend")
    glbs = sorted(p for p in names if p.suffix == ".glb")
    previews = sorted(p for p in names if p.suffix == ".mp4")
    stills = [p for p in names if p.suffix == ".png" and p.parent == folder]
    scripts = [p for p in names if p.suffix in {".py", ".sh"}]
    for script in scripts:
        if script.suffix == ".py":
            compile(script.read_bytes(), str(script), "exec")
    listed = dict(manifest_hashes(manifest))
    checked_hashes = {}
    problems = []
    for label, paths in (("blend", blends), ("glb", glbs), ("video", previews), ("script", scripts), ("stills", stills)):
        if not paths:
            problems.append(f"no {label}")
    for name, expected in listed.items():
        file = folder / name
        actual = file_hash(file) if file.is_file() else None
        checked_hashes[name] = {"expected": expected, "actual": actual}
        if actual != expected:
            problems.append(f"sha256 mismatch: {name}")
    unchecked_outputs = [p.relative_to(folder).as_posix() for p in [*blends, *glbs, *previews, *scripts]
                         if p.relative_to(folder).as_posix() not in listed]
    if unchecked_outputs:
        problems.append(f"primary files absent from manifest hashes: {unchecked_outputs}")
    good_links, bad_links = links(folder)
    if bad_links:
        problems.append(f"Broken README links: {bad_links}")
    for name, value in (("manifest", manifest), ("QA", qa)):
        if value.get("status") != "needs_review" and not (name == "QA" and qa.get("candidate_status") == "needs_review"):
            problems.append(f"{name} candidate status needs confirmation: {value.get('status')!r}")
    return {
        "asset": asset,
        "status": "pass" if not problems else "review",
        "problems": problems,
        "candidate_status": manifest.get("status"),
        "blends": [p.name for p in blends],
        "glbs": {p.name: inspect_glb(p) for p in glbs},
        "videos": {p.name: video(p) for p in previews},
        "linked_files": good_links,
        "checked_hashes": checked_hashes,
        "qa_top_level_fields": sorted(qa),
    }


def run(repo, output, selected):
    library = repo / "Assets/Watercolor/Goose/Blender"
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(lambda asset: asset_audit(library, asset), selected or TARGETS))
    inventory = [
        folder.parent.name for folder in sorted(library.glob("*/v001"))
        if all((folder / name).is_file() for name in REQUIRED) and list(folder.glob("*.blend")) and list(folder.glob("*.glb"))
    ]
    doc = {"version": "v001", "candidate_count": len(inventory), "assets": records}
    output.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    for record in records:
        print(record["asset"], record["status"], record.get("problems", record.get("missing", [])))
    if any(record["status"] != "pass" for record in records):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("assets", nargs="*")
    args = parser.parse_args()
    run(args.repo.resolve(), args.out, args.assets)
