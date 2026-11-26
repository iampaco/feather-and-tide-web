"""Record the identified source assets and exact preview files staged for packaging."""
import argparse
import hashlib
import json
from pathlib import Path

from ground_detail import MATERIALS, MODELS
from landscape import CONTACT_LAYOUT

ROOT = Path(__file__).resolve().parents[4]
ART = Path("Assets/Watercolor/Goose/Blender")
RECIPE = Path("Assets/Processed/Goose/LinearRoutePolish")
LINEAR_LAYOUT = Path("Sources/FeatherTide/Systems/Chapter/GooseLinearLayout.swift")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finish(directory, basin_entry):
    manifest = directory / "manifest.json"
    records = json.loads(manifest.read_text())
    basin = json.loads(basin_entry.read_text())
    records["ft_goose_linear_basin"] = basin
    river_sources = [
        *(ART / path for path in MATERIALS.values()),
        ART / "MAT-004/v001/textures/ft_goose_mat_water_river_basecolor_alpha.png",
        ART / "MAT-004/v001/textures/ft_goose_mat_water_shallow_basecolor_alpha.png",
    ]
    layout = {"layout": str(LINEAR_LAYOUT), "layoutSHA256": sha(ROOT / LINEAR_LAYOUT)}
    detail_recipe = RECIPE / "ground_detail.py"
    detail_digest = {str(detail_recipe): sha(ROOT / detail_recipe)}
    records["ft_goose_linear_landscape.usdz"] = {
        "source": str(ART / "ENV-016/v001/ENV-016_ProtectedMarsh.glb"),
        "treatment": "Continuous riverbank relief with level rest aprons and clustered shoreline reeds",
        "recipes": {
            str(path): sha(ROOT / path) for path in [RECIPE / "landscape.py", RECIPE / "landscape_usdz.py"]
        },
        **layout,
    }
    records["ft_goose_linear_landscape.jpg"] = {
        "sources": {str(path): sha(ROOT / path) for path in river_sources},
        "treatment": "Baked river depth, broken damp shore edges and contact pigment from grounded props",
        "recipes": {str(RECIPE / "landscape.py"): sha(ROOT / RECIPE / "landscape.py"), **detail_digest},
        **layout,
    }
    records["ft_goose_linear_ground_details"] = {
        "sources": {
            **{str(ART / path): sha(ROOT / ART / path) for path in MODELS.values()},
            str(CONTACT_LAYOUT.relative_to(ROOT)): sha(CONTACT_LAYOUT),
        },
        "treatment": "Blender assembly of original grass and rock meshes in three grounded shoreline patches",
        "recipes": {str(RECIPE / "ground_props.py"): sha(ROOT / RECIPE / "ground_props.py"), **detail_digest},
        **layout,
    }
    records["ft_goose_linear_basin_paint.png"] = {
        "source": "ft_goose_linear_basin.usdz#textures/ft_goose_linear_basin_paint.png",
        "treatment": "Same embedded texels, shared unlit response with river and opening terrain",
    }
    for variant in ("b", "c"):
        source = ART / f"ENV-009/v001/ENV-009_FarRidge_{variant.upper()}.glb"
        records[f"ft_goose_linear_ridge_{variant}"] = {"source": str(source), "sourceSHA256": sha(ROOT / source)}
    for key, script in (
        ("ft_goose_scene_s0", "opening.py"), ("ft_goose_scene_s1", "opening.py"),
        ("ft_goose_linear_basin", "basin.py"),
    ):
        recipe = RECIPE / script
        records[key].update({"recipes": {str(recipe): sha(ROOT / recipe), **detail_digest}, **layout})
    for key, record in records.items():
        filename = key if Path(key).suffix else f"{key}.{record.get('extension', 'usdz')}"
        resource = directory / filename
        record["filename"] = filename
        record["exportSHA256"] = sha(resource)
    delivered = {file.name for file in directory.iterdir() if file.is_file() and file != manifest}
    if delivered != {record["filename"] for record in records.values()}:
        raise RuntimeError("Manifest and delivered preview files differ")
    manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("basin_entry", type=Path)
    args = parser.parse_args()
    finish(args.directory, args.basin_entry)
