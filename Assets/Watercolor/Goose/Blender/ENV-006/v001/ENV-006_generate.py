"""Build and audit the grass variants using the reed library's shared ribbon workflow."""
from pathlib import Path
import runpy


if __name__ == "__main__":
    shared = Path(__file__).resolve().parents[2] / "ENV-004/v001/ENV-004_generate.py"
    runpy.run_path(str(shared))["main"]("ENV-006")
