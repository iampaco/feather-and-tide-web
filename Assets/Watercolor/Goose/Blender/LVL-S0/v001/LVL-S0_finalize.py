"""Bundle independent S0 evidence and fingerprint candidate paths."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

STEM = "LVL-S0_S0_StartWetland"
ROUNDTRIP = ("roundtrip_fixed_rear_takeoff.png", "roundtrip_fixed_rear_glide.png",
             "roundtrip_fixed_rear_fog_exit.png", "roundtrip_top_flock.png", "qa.json")


def verify_links(folder):
    for relative in re.findall(r"\]\(([^)]+)\)", (folder / "README.md").read_text()):
        if not (folder/relative).is_file():
            raise FileNotFoundError(folder/relative)


def finalize(folder, evidence):
    qa = json.loads((evidence / "qa.json").read_text())
    if qa["result"] != "offline_pass" or qa["video"]["frames_decoded"] != 168:
        raise RuntimeError("Independent offline evidence is incomplete")
    for name in ROUNDTRIP:
        source, dest = evidence/name, folder/name
        if source.resolve() != dest.resolve():
            shutil.copyfile(source,dest)
    deps = json.loads((folder/"dependencies.json").read_text())
    manifest = {
        "id": "LVL-S0", "version": "v001", "status": "needs_review",
        "variant": "S0_StartWetland", "execution_order_1_based": 42,
        "tool": "Blender 5.2.2 LTS",
        "runtime_export": {
            "path": STEM+".glb", "coordinates": "(x,z,-y)",
            "entry": "S0_Entry", "exit_to_S1": "S0_Exit_to_S1",
            "review_flock_glb": STEM+"_ReviewFlock.glb",
            "standalone_backdrop_glb": STEM+"_Backdrop.glb",
            "notes": "Travel/trigger logic and USDZ left for App integration.",
        },
        "dependencies": deps,
        "embedded_texture_mapping": {
            "world": qa["GLB_transport"]["runtime_images"],
            "standalone_backdrop": qa["GLB_transport"]["optional_backdrop_images"],
            "review_flock": qa["GLB_transport"]["flock_images"],
            "source_map": {
                "grass_and_wetland": ["ENV-002/v001", "ENV-003/v001", "S0 vertex wash"],
                "vegetation": "ENV-005/v001",
                "mist": "FX-004/v001",
                "mountains": "ENV-009/v001",
                "feather_materials": "CHR-001/v001",
            },
        },
        "sources_and_rights": "Project-authored continuation and placements using inherited v001 project geometry and materials.",
        "review": {
            "fixed_rear_video": "preview_fixed_rear.mp4","qa": "qa.json",
            "layout":"s0_layout.json","dependency_fingerprints":"dependencies.json",
        },
        "pending": qa["pending"],
        "files": {
            path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "bytes":path.stat().st_size}
            for path in sorted(folder.iterdir())
            if path.is_file() and not path.name.startswith(".") and path.name != "asset_manifest.json"
        },
    }
    (folder/"asset_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    verify_links(folder)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("folder",type=Path)
    parser.add_argument("evidence",type=Path)
    options=parser.parse_args()
    finalize(options.folder,options.evidence)
