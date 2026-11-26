"""Export ENV-009 B and C using the same GLB surface conversion as the baseline."""
import importlib.util
import sys
from pathlib import Path

parent = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("baseline_route", parent.parent / "LinearRoute3D/prepare.py")
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)

output = Path(sys.argv[sys.argv.index("--") + 1])
for variant in ("B", "C"):
    source = baseline.ART / f"ENV-009/v001/ENV-009_FarRidge_{variant}.glb"
    baseline.export_glb(source, output / f"ft_goose_linear_ridge_{variant.lower()}.usdz")
