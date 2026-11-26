"""Bake the single-route river sheet using the registered mud, grass and water textures.

Run with Python 3 (NumPy and Pillow). The Blender-bundled Python supplies OpenUSD
for the second command described in this directory.
"""
import argparse
from functools import cache
import json
from pathlib import Path

import numpy as np

from ground_detail import MATERIALS, contact_shade, enrich, placements

ROOT = Path(__file__).resolve().parents[4]
ART = ROOT / "Assets/Watercolor/Goose/Blender"
BOUNDS = (-56, 56, 68, 256)
WATER_LEVEL = -0.278
OUTER_GRASS = (126, 137, 109)
MARSH_REST = (-20.0, 161.0)
CONTACT_LAYOUT = ROOT / "Sources/FeatherTide/Resources/ft_goose_chapter_layout.json"


def fade(lo, hi, value):
    t = np.clip((value - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def shore_edges(y):
    farm = fade(91, 118, y) * (1 - fade(195, 228, y))
    entry = np.sin((y - 70) * 0.085)
    left = -9.8 - 16.5 * farm + 1.3 * entry + 1.3 * np.sin(y * 0.219)
    right = 10.7 + 6.7 * farm + 1.7 * np.sin(y * 0.147 + 0.8) + 0.7 * np.sin(y * 0.41)
    # Scallop the outer bank at the refuge and leave a blue-water lane past its lip.
    left -= 2.8 * np.exp(-((y - 146) / 7.8) ** 2) + 2.1 * np.exp(-((y - 178.0) / 6.6) ** 2)
    right -= 1.2 * np.exp(-((y - 155) / 7.2) ** 2)
    return left, right


def marsh_distance(x, y):
    long = y - 161.5
    across = x + 23.8 - 0.17 * long
    lip = 6.1 - 0.35 * fade(160, 164, y) * (1 - fade(166, 169, y))
    width = np.where(across > 0, lip, 8.7)
    angle = np.arctan2(long / 10.6, across / width)
    wobble = 0.1 * np.sin(3 * angle + 0.9) + 0.08 * np.cos(5 * angle - 0.5)
    return 8.7 * (1 + wobble - np.hypot(across / width, long / 10.6))


def exit_shore_distance(x, y):
    long = y - 214
    cross = x - 0.5 + 0.27 * long
    angle = np.arctan2(long / 5.2, cross / 3.6)
    return 3.6 * (1 + 0.14 * np.cos(angle * 3 + 0.9) - np.hypot(cross / 3.6, long / 5.2))


def coast(x, y):
    left, right = shore_edges(y)
    noise = (0.44 * np.sin(y * 0.80 + x * 0.34) +
             0.21 * np.cos(y * 1.53 - x * 0.91) + 0.09 * np.sin(y * 3.80 + x * 2.77))
    distance = np.maximum(left - x, x - right)
    marsh = marsh_distance(x, y)
    # A soft union keeps the cove attached even where its tongue folds back.
    seam = np.maximum(1.8 - np.abs(distance - marsh), 0) / 1.8
    distance = np.maximum(distance, marsh) + seam * seam * 0.45
    return distance + noise


def elevation(x, y, outlet):
    bank = coast(x, y)
    # Keep the river bed at the same height on the opening and basin overlap.
    edge = 0.067 * fade(-0.45, 2.15, bank)
    plateau = fade(0.2, 2.15, marsh_distance(x, y))
    if outlet:
        plateau = np.maximum(plateau, fade(-0.35, 1.18, exit_shore_distance(x, y)))
    # Higher ground belongs on the backs of the banks. Keep the wet lip and the
    # whole stopping apron, including its approach, on the gameplay surface.
    left_bank = 0.78 * np.exp(-((x + 29.5) / 6.4) ** 2 - ((y - 158) / 19.0) ** 2)
    right_bank = 0.58 * np.exp(-((x - 19.8) / 5.6) ** 2 - ((y - 165) / 18.0) ** 2)
    apron = np.hypot(x - MARSH_REST[0], y - MARSH_REST[1])
    slope = (left_bank + right_bank) * fade(0.55, 3.85, bank) * fade(6, 8.2, apron)
    return (WATER_LEVEL + edge) * (1 - plateau) + slope


@cache
def protected_contacts():
    layout = json.loads(CONTACT_LAYOUT.read_text())
    origin_x, origin_y, _ = layout["rests"][2]
    return [(x - origin_x + MARSH_REST[0], y - origin_y + MARSH_REST[1])
            for x, y, _ in layout["protectedSlots"]]


def detail_allowed(x, y, radius, *, rock):
    if abs(x) < 8.5 + radius or np.hypot(x - MARSH_REST[0], y - MARSH_REST[1]) < 3.8 + radius:
        return False
    if any(np.hypot(x - sx, y - sy) < 0.85 + radius for sx, sy in protected_contacts()):
        return False
    return coast(x, y) > (0.72 if rock else 0.50) + 0.60 * radius


def texture(asset, name, x, y, period_x, period_y):
    from PIL import Image

    base = ART / f"{asset}/v001/textures/ft_goose_mat_{name}_basecolor"
    path = Path(str(base) + ("_alpha.png" if asset == "MAT-004" else ".png"))
    with Image.open(path) as source:
        data = np.asarray(source.convert("RGB").resize((512, 512), Image.Resampling.LANCZOS),
                          dtype=np.float32)
    value = data[..., 0] * 0.22 + data[..., 1] * 0.60 + data[..., 2] * 0.18
    value -= np.mean(value)
    ix = np.floor(np.mod(x / period_x, 1) * 512).astype(np.int32)
    iy = np.floor(np.mod(y / period_y, 1) * 512).astype(np.int32)
    return value[iy, ix]


def blend(a, b, amount):
    amount = amount[..., None]
    return a * (1 - amount) + b * amount


def atlas(output, outlet):
    from PIL import Image

    left, right, start, end = BOUNDS
    x = np.linspace(left, right, 2048, dtype=np.float32)[None, :]
    y = np.linspace(end, start, 4096, dtype=np.float32)[:, None]
    distance = coast(x, y)
    if outlet:
        distance = np.maximum(distance, exit_shore_distance(x, y))
    cloud = (0.53 * np.sin(x * 0.28 + y * 0.13) + 0.29 * np.sin(x * 0.83 - y * 0.33) +
             0.18 * np.cos(y * 1.35 + x * 1.27))
    river = texture("MAT-004", "water_river", x + 0.8 * np.sin(y * 0.23), y, 27, 14)
    shallows = texture("MAT-004", "water_shallow", x, y, 11.5, 8.5)
    mud = texture("MAT-003", "mud_bank", x + 0.5 * np.sin(y), y, 9.4, 10.3)
    grass = texture("MAT-003", "grass_flat", x, y, 16.8, 13.2)

    warm_reflection = np.exp(-((x + 2 + 2 * np.sin(y * 0.07)) / 7.4) ** 2)
    warm_reflection *= 0.52 + 0.48 * np.sin(y * 0.08 + 0.64) ** 2
    deep = np.asarray((76, 117, 125), dtype=np.float32)
    shallow = np.asarray((134, 160, 147), dtype=np.float32)
    wet_mud = np.asarray((133, 130, 108), dtype=np.float32)
    dry_mud = np.asarray((154, 144, 115), dtype=np.float32)
    bank = np.asarray(OUTER_GRASS, dtype=np.float32)
    deep = deep + (river * 0.68 + cloud * 6)[..., None] + warm_reflection[..., None] * (18, 15, 8)
    shallow = shallow + (shallows * 0.76 + cloud * 9)[..., None]
    wet_mud = wet_mud + (mud * 0.77 + cloud * 12)[..., None]
    dry_mud = dry_mud + (mud * 0.72 + cloud * 13)[..., None]
    bank = bank + (grass * 0.85 + cloud * 14)[..., None]

    mud_apron = np.exp(-((x + 20.7) / 4.3) ** 2 - ((y - 156.1) / 4.0) ** 2)
    reed_point = np.exp(-((x + 21.1) / 3.2) ** 2 - ((y - 167.0) / 3.8) ** 2)
    inside_bend = np.exp(-((x + 17.6) / 3.7) ** 2 - ((y - 157.7) / 4.6) ** 2)
    wetland = fade(129, 151, y) * (1 - fade(171, 185, y))
    shallow_width = (4.7 + 1.52 * cloud) * (1 - 0.48 * wetland * fade(-32, -20, x) * (1 - fade(-13, -8, x)))
    shallow_width += 1.0 * inside_bend
    mud_width = 2.35 + 1.40 * cloud + 2.40 * mud_apron - 1.0 * reed_point
    mud_flats = dry_mud + (mud_apron * 0.8)[..., None] * (19, 12, 5)
    color = blend(deep, shallow, fade(-shallow_width, -0.47, distance))
    color = blend(color, wet_mud, fade(-0.62, 0.94 + 0.35 * cloud, distance))
    color = blend(color, mud_flats, fade(0.20, 1.82 + 0.58 * cloud, distance))
    color = blend(color, bank, fade(0.79, 1.42 + mud_width, distance))
    # Silt streaks widen over the exposed apron, in the same palette as its bed.
    silt = np.maximum(0, np.cos(y * 2.22 + 0.78 * np.sin(x * 0.66) + x * 0.25)) ** 5
    color += (silt * mud_apron * fade(0.25, 1.8, distance))[..., None] * (11, 9, 5)
    # In the side bay, a broken wet rim and a darker reed bed describe the relief
    # even though the route uses painted, unlit ground.
    rim = wetland * np.exp(-((distance + 0.32) / 0.39) ** 2) * (0.62 + 0.38 * cloud) * (1 - fade(-14, -9, x))
    color += rim[..., None] * (15, 14, 7)
    reed_bed = wetland * (1 - fade(-18, -14.5, x)) * fade(1.5, 3.6, distance) * (1 - fade(4.0, 9.0, distance))
    color += (reed_bed * (0.66 - 0.45 * silt))[..., None] * (-21, -14, -15)
    far_bank = wetland * fade(1.5, 4.4, distance) * (1 - fade(8.0, 14.0, distance)) * fade(13, 18, x)
    color += (far_bank * (0.51 + 0.49 * cloud))[..., None] * (-15, -10, -10)
    if outlet:
        # A silted bar gently takes on the colors of the basin's arriving water.
        near_basin = fade(229, 253, y) * (1 - fade(-3.5, 0.8, distance))
        inward = np.exp(-((x + 0.20 + 0.12 * np.maximum(y - 242, 0)) / 5.0) ** 2)
        basin_inlet = np.asarray((94, 133, 136)) + (shallows * 0.56 + cloud * 7)[..., None]
        basin_inlet += inward[..., None] * (24, 18, 8)
        color = blend(color, basin_inlet, near_basin * (0.45 + 0.4 * inward))
    sources = {}
    for key, relative in MATERIALS.items():
        with Image.open(ART / relative) as image:
            sources[key] = np.asarray(image.convert("RGB"), dtype=np.float32)
    mud_mask = 1 - fade(0.8, 2.8 + 0.50 * cloud, distance)
    enrich(color, x, y, distance, mud_mask, sources)
    contact_shade(color, x, y, placements("River", detail_allowed), fade(0, 0.5, distance))
    color = blend(color, np.asarray(OUTER_GRASS), fade(43, 56, np.abs(x)))
    Image.fromarray(np.clip(color, 0, 255).astype(np.uint8)).save(
        output / "ft_goose_linear_landscape.jpg", quality=93, subsampling=0)


def geometry(output, outlet):
    left, right, start, end = BOUNDS
    x, y = np.meshgrid(np.linspace(left, right, 225), np.linspace(start, end, 395))
    h = elevation(x, y, outlet)
    np.savez_compressed(output / ".route-mesh.npz", x=x, y=y, height=h)
    rng = np.random.default_rng(161)
    clusters = []
    for side in (-1, 1):
        for cy in np.linspace(72, 244, 230):
            cy += rng.uniform(-0.85, 0.85)
            left_edge, right_edge = shore_edges(cy)
            slope = np.cos(cy * 0.24 + side * 1.45) + 0.45 * np.cos(cy * 0.81)
            if slope < -0.12 or rng.random() < 0.22:
                continue
            for _ in range(rng.integers(1, 4)):
                cx = (left_edge if side < 0 else right_edge) + side * rng.uniform(-0.3, 2.25)
                clusters.append((cx, cy + rng.uniform(-0.65, 0.65), rng.uniform(0.30, 0.88), 0))
    # Leave a low upstream lip. Wider, taller leaves group behind the dry apron
    # and down the far shoulder, with gaps between silhouettes.
    for cx, cy, count, spread, tallest in [
        (-26.7, 147.1, 12, 1.2, 0.92), (-24.4, 151.7, 12, 1.0, 0.82),
        (-26.2, 157.1, 17, 0.95, 1.46), (-27.9, 162.5, 22, 1.1, 1.65),
        (-23.3, 167.6, 14, 0.78, 1.18), (-21.2, 171.3, 11, 0.78, 1.11),
        (16.0, 156.9, 12, 0.87, 0.77), (17.8, 170.4, 12, 0.95, 0.88),
    ]:
        for _ in range(count):
            xx, yy = rng.normal(cx, spread), rng.normal(cy, spread * 0.72)
            if coast(xx, yy) > -0.24 and np.hypot(xx - MARSH_REST[0], yy - MARSH_REST[1]) > 5.6:
                clusters.append((xx, yy, rng.uniform(tallest * 0.53, tallest), 1))
    with (output / ".route-reeds.tsv").open("w") as file:
        for x, y, size, marsh in clusters:
            print(x, y, elevation(x, y, outlet) - 0.028, size, marsh, sep="\t", file=file)

    glints = []
    # Stagger the strokes across softly curved currents. A sparse central run
    # brings each turn forward in view, and a broader run skirts the refuge.
    for cy in np.arange(118.0, 181.0, 1.65):
        for cx, spread in (
            (-16.2 - 2.5 * np.exp(-((cy - 127) / 13) ** 2), 1.25),
            (-3.8 * np.exp(-((cy - 135) / 8.0) ** 2) + 3.9 * np.exp(-((cy - 166) / 8.8) ** 2), 0.92),
        ):
            xx = cx + rng.uniform(-spread, spread)
            yy = cy + rng.uniform(-0.80, 0.80)
            length = rng.uniform(0.33, 1.25)
            angle = rng.uniform(-0.23, 0.36)
            if coast(xx - length / 2, yy) < -0.62 and coast(xx + length / 2, yy) < -0.62:
                glints.append((xx, yy, WATER_LEVEL + 0.010, length, rng.uniform(0.012, 0.032), angle))
    np.savetxt(output / ".route-water.tsv", glints, delimiter="\t")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--outlet", action="store_true", help="Include the downstream sandbar")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    atlas(args.output, args.outlet)
    geometry(args.output, args.outlet)
