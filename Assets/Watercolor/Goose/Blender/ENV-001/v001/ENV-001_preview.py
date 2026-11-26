"""Encode the fixed-camera review, label the assembly, and compare source/reimport renders."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
ROWS_NORTH_FIRST = (
    ("Flat", "GentleSlope", "Flat", "Shore"),
    ("GentleSlope", "Flat", "Flat", "Shore"),
    ("GentleSlope", "Ridge", "Flat", "Shore"),
    ("Ridge", "GentleSlope", "Flat", "Shore"),
)
PAPER = "#f4f3ec"
INK = "#263b36"
MUTED = "#536c62"


def board(folder, regular, mono):
    top = Image.open(folder / "preview_top.png").convert("RGB")
    top = top.resize((984, 984), Image.Resampling.LANCZOS)
    plate = Image.new("RGB", (1376, 1132), PAPER)
    ox, oy = 38, 112
    plate.paste(top, (ox, oy))
    draw = ImageDraw.Draw(plate, "RGBA")
    title = ImageFont.truetype(regular, 44)
    body = ImageFont.truetype(regular, 22)
    small = ImageFont.truetype(regular, 19)
    measure = ImageFont.truetype(mono, 17)
    draw.text((38, 30), "Terrain & shoreline assembly", font=title, fill=INK)
    draw.text((1340, 44), "ENV-001  /  v001", font=measure, fill=MUTED, anchor="rt")
    draw.line((38, 91, 1340, 91), fill="#9aaea3", width=1)

    # Top camera looks straight down, has no roll, and spans 45.5 BU on this square image.
    pitch_px = 984 * 10 / 45.5
    left = ox + (984 - pitch_px * 4) / 2
    top_edge = oy + (984 - pitch_px * 4) / 2
    grid_color = (239, 239, 219, 160)
    for index in range(5):
        x, y = left + index * pitch_px, top_edge + index * pitch_px
        draw.line((x, top_edge, x, top_edge + pitch_px * 4), fill=grid_color, width=2)
        draw.line((left, y, left + pitch_px * 4, y), fill=grid_color, width=2)
    for row, names in enumerate(ROWS_NORTH_FIRST):
        for col, name in enumerate(names):
            x, y = left + col * pitch_px + 10, top_edge + (row + 1) * pitch_px - 31
            label = f"{name}  {col},{3-row}"
            box = draw.textbbox((x + 5, y + 3), label, font=measure)
            draw.rounded_rectangle((x, y, box[2] + 5, y + 24), radius=3, fill=(37, 58, 52, 208))
            draw.text((x + 5, y + 3), label, font=measure, fill=PAPER)

    sx = 1060
    draw.text((sx, 144), "N", font=measure, fill=INK)
    draw.line((sx + 5, 174, sx + 5, 207), fill=INK, width=2)
    draw.polygon([(sx, 181), (sx + 5, 171), (sx + 10, 181)], fill=INK)
    draw.text((sx + 24, 176), "+Y in Blender", font=small, fill=MUTED)

    draw.text((sx, 246), "Centre grid", font=body, fill=INK)
    draw.text((sx, 278), "10 BU pitch · 4 × 4 tiles", font=small, fill=MUTED)
    draw.text((sx, 307), "17 vertices per edge", font=small, fill=MUTED)
    draw.text((sx, 336), "Land datum 0.00 BU", font=small, fill=MUTED)
    draw.line((sx, 392, 1340, 392), fill="#9aaea3", width=1)
    draw.text((sx, 423), "Shared edges", font=body, fill=INK)
    for row, (tag, label) in enumerate((("L", "Level land"), ("C", "Coast profile"),
                                         ("W", "Submerged terminal"))):
        y = 460 + row * 43
        draw.rounded_rectangle((sx, y, sx + 29, y + 25), radius=3, fill="#d9e4d8")
        draw.text((sx + 8, y + 3), tag, font=measure, fill=INK)
        draw.text((sx + 43, y + 2), label, font=small, fill=MUTED)

    draw.line((sx, 615, 1340, 615), fill="#9aaea3", width=1)
    draw.text((sx, 646), "Review overlays", font=body, fill=INK)
    draw.line((sx, 693, sx + 29, 693), fill="#c58a52", width=4)
    draw.text((sx + 43, 682), "Sample route", font=small, fill=MUTED)
    draw.rounded_rectangle((sx, 722, sx + 29, 738), radius=2, fill="#83aaa8")
    draw.text((sx + 43, 719), "Water at −0.18 BU", font=small, fill=MUTED)
    bar_end = sx + pitch_px
    draw.line((sx, 816, bar_end, 816), fill=INK, width=2)
    for x in (sx, bar_end):
        draw.line((x, 810, x, 822), fill=INK, width=2)
    draw.text((sx, 836), "10 BU in the inset", font=measure, fill=MUTED)
    plate.save(folder / "preview_assembly.png")


def video(folder):
    frames = folder / "frames"
    count = len(list(frames.glob("*.png")))
    if count < 2:
        raise ValueError("Build with --video-frames before encoding.")
    path = folder / "preview_fixed_rear.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", "15",
         "-i", str(frames / "%04d.png"), "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0,"
         "tpad=start_duration=0.5:stop_duration=0.65:start_mode=clone:stop_mode=clone,fps=30",
         "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", "-movflags", "+faststart", str(path)],
        check=True,
    )
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror",
                    "-i", str(path), "-f", "null", "-"], check=True)
    result = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,nb_frames,avg_frame_rate,duration",
         "-of", "json", str(path)],
        text=True,
    )
    info, = json.loads(result)["streams"]
    if (info["codec_name"], info["width"], info["height"], info["avg_frame_rate"]) != ("h264", 852, 394, "30/1"):
        raise ValueError(info)
    return dict(info, source_render_size_px=[852, 393], unique_rendered_frames=count)


def compare(folder):
    source = Image.open(folder / "preview_seam.png").convert("RGB")
    imported = Image.open(folder / "preview_roundtrip_seam.png").convert("RGB")
    if source.size != imported.size:
        raise ValueError("Roundtrip image size differs.")
    histogram = ImageChops.difference(source, imported).histogram()
    combined = [sum(histogram[i::256]) for i in range(256)]
    count = sum(combined)
    mean = sum(i * n for i, n in enumerate(combined)) / count
    cumulative = 0
    for p99, n in enumerate(combined):
        cumulative += n
        if cumulative >= .99 * count:
            break
    if mean > 1 or p99 > 3:
        raise ValueError((mean, p99))
    return {"result": "pass", "size_px": list(source.size), "mean_abs_rgb8": mean,
            "p99_abs_rgb8": p99, "mean_limit_rgb8": 1, "p99_limit_rgb8": 3}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Existing Blender render output")
    parser.add_argument("--font", default="/System/Library/Fonts/Helvetica.ttc")
    parser.add_argument("--mono", default="/System/Library/Fonts/Menlo.ttc")
    options = parser.parse_args()
    folder = options.output.resolve()
    board(folder, options.font, options.mono)
    qa_path = folder / "qa.json"
    qa = json.loads(qa_path.read_text())
    qa["review_media"] = {"video_decode": video(folder), "roundtrip_seam_render_comparison": compare(folder)}
    write_json(qa_path, qa)
    manifest_path = folder / "asset_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"] = {item.name: sha256(item.read_bytes()).hexdigest()
                         for item in sorted([*folder.iterdir(), *HERE.glob("ENV-001_*.py")])
                         if item.is_file() and item != manifest_path}
    write_json(manifest_path, manifest)


if __name__ == "__main__":
    main()
