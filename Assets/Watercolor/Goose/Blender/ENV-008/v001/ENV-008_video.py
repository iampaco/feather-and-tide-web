"""Encode the RGB or RGBA review frames without changing the Blender evidence."""
import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blender_output", type=Path)
    settings = parser.parse_args()
    folder = settings.blender_output
    destination = folder / "preview_lake_motion.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-framerate", "12", "-i",
            str(folder / "wind_frames" / "%04d.png"),
            "-vf", "pad=852:394:0:0,fps=24", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", "17", "-movflags", "+faststart", str(destination),
        ],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-i", str(destination), "-f", "null", "-"],
        check=True,
    )


if __name__ == "__main__":
    main()
