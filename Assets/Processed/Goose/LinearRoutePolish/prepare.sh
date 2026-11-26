#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 1 ]]; then
    echo "Usage: $0 <new-output-directory>" >&2
    exit 2
fi

recipe="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$recipe/../../../.." && pwd)"
output="$1"
mkdir -p "$output"
output="$(cd "$output" && pwd)"
if [[ -e "$output/GooseLinearPreview" ]]; then
    echo "Choose an output directory without GooseLinearPreview." >&2
    exit 2
fi
baseline="$root/build/GooseLinearRoute3D/FeatherTide-GooseLinearRoute3D-Simulator.zip"
expected=4aeba7101c82339be68b3cab51157df829c6155ccadca3114848f16b8b006eb7
actual="$(shasum -a 256 "$baseline" | cut -d' ' -f1)"
[[ "$actual" == "$expected" ]]
unzip -q "$baseline" 'GooseLinearPreview/*' -d "$output"
preview="$output/GooseLinearPreview"
blender_path="${FT_BLENDER_PATH:-/Applications/Blender.app}"
usd_python="${FT_USD_PYTHON:-$blender_path/Contents/Resources/5.2/python/bin/python3.13}"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
export PYTHONDONTWRITEBYTECODE=1

python3 "$recipe/landscape.py" "$preview" --outlet
"$usd_python" "$recipe/landscape_usdz.py" "$preview"
python3 "$recipe/opening.py" "$preview" --usd-python "$usd_python"
"$usd_python" "$recipe/basin.py" "$scratch/ft_goose_linear_basin.usdz" \
    --river-atlas "$preview/ft_goose_linear_landscape.jpg" > "$scratch/manifest-entry.json"
cp "$scratch/ft_goose_linear_basin.usdz" "$preview/"
unzip -p "$preview/ft_goose_linear_basin.usdz" textures/ft_goose_linear_basin_paint.png \
    > "$preview/ft_goose_linear_basin_paint.png"
"$blender_path/Contents/MacOS/Blender" -b --factory-startup -t 4 --python-exit-code 1 \
    --python "$recipe/ground_props.py" -- "$preview/ft_goose_linear_ground_details.usdz"
python3 - "$root/build/GooseLinearSceneryDetail/FeatherTide-GooseLinearSceneryDetail-Simulator.zip" \
    "$recipe/preview-manifest-detail.json" "$preview" <<'PY'
from hashlib import sha256
import json
from pathlib import Path
import sys
from zipfile import ZipFile

bundle, manifest, destination = map(Path, sys.argv[1:])
records = json.loads(manifest.read_text())
with ZipFile(bundle) as package:
    for variant in ("b", "c"):
        record = records[f"ft_goose_linear_ridge_{variant}"]
        filename = record["filename"]
        data = package.read(f"GooseLinearPreview/{filename}")
        if sha256(data).hexdigest() != record["exportSHA256"]:
            raise RuntimeError(f"Baseline ridge export checksum mismatch: {filename}")
        (destination / filename).write_bytes(data)
PY
python3 "$recipe/manifest.py" "$preview" "$scratch/manifest-entry.json"
"$usd_python" "$recipe/contact_probe.py" "$preview"
