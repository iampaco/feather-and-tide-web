"""World-space ground pigment and placements shared by the paint and Blender exports."""
import numpy as np


MATERIALS = {
    "grass": "MAT-003/v001/textures/ft_goose_mat_grass_flat_basecolor.png",
    "mud": "MAT-003/v001/textures/ft_goose_mat_mud_bank_basecolor.png",
    "silt": "MAT-003/v001/textures/ft_goose_mat_shallow_margin_basecolor.png",
}

MODELS = {
    "grass_a": "ENV-006/v001/ENV-006_Grass_A.glb",
    "grass_b": "ENV-006/v001/ENV-006_Grass_B.glb",
    "grass_c": "ENV-006/v001/ENV-006_Grass_C.glb",
    "pebbles": "ENV-011/v001/ENV-011_PebbleCluster.glb",
    "low_rock": "ENV-011/v001/ENV-011_Rock_Long.glb",
    "round_rock": "ENV-011/v001/ENV-011_Rock_Round.glb",
}

# Each planting bed gives the bank a silhouette while leaving the approach open.
# x, forward, lateral spread, forward spread, rock, rock scale, grass clusters
BEDS = {
    "Opening": (
        (-4.9, -2.7, 1.40, 1.64, "pebbles", 0.51, 10),
        (4.8, 1.9, 1.10, 1.72, "pebbles", 0.37, 8),
        (-3.5, 7.0, 1.26, 2.2, "low_rock", 0.37, 9),
        (4.4, 12.6, 1.05, 2.00, "pebbles", 0.39, 7),
        (-5.2, 20.3, 1.12, 2.68, "round_rock", 0.39, 13),
        (6.7, 27.7, 1.16, 2.75, "pebbles", 0.49, 12),
        (-4.5, 45.8, 1.25, 2.58, "pebbles", 0.35, 9),
        (4.5, 58.2, 1.45, 2.56, "low_rock", 0.37, 9),
        (-4.3, 74.0, 0.84, 1.70, "pebbles", 0.42, 7),
        (4.3, 78.5, 1.34, 2.22, "low_rock", 0.43, 13),
    ),
    "River": (
        (-14.0, 92.3, 1.60, 2.73, "low_rock", 0.58, 10),
        (14.9, 99.6, 2.00, 3.73, "round_rock", 0.52, 11),
        (-24.8, 114.6, 2.47, 3.90, "pebbles", 0.61, 12),
        (20.5, 121.4, 2.45, 3.35, "low_rock", 0.66, 13),
        (-29.5, 131.2, 2.42, 4.25, "low_rock", 0.62, 14),
        (-26.5, 146.7, 1.82, 3.23, "pebbles", 0.64, 13),
        (-24.0, 155.1, 1.33, 1.82, "low_rock", 0.47, 11),
        (-24.4, 164.0, 1.53, 2.08, "round_rock", 0.51, 12),
        (-23.2, 168.9, 1.52, 2.81, "pebbles", 0.56, 13),
        (19.1, 165.8, 2.30, 4.25, "low_rock", 0.63, 15),
        (-28.3, 187.3, 2.20, 3.52, "pebbles", 0.54, 11),
        (18.8, 193.9, 2.10, 3.13, "round_rock", 0.46, 10),
        (-13.3, 220.4, 1.54, 2.72, "low_rock", 0.47, 10),
        (16.8, 231.1, 1.44, 2.40, "pebbles", 0.52, 10),
    ),
    "Basin": (
        (11.3, 252.7, 1.63, 3.30, "low_rock", 0.57, 14),
        (9.5, 262.0, 1.72, 2.83, "pebbles", 0.49, 12),
        (-10.9, 260.6, 1.58, 2.40, "low_rock", 0.55, 12),
        (-11.7, 269.2, 1.73, 2.65, "round_rock", 0.46, 14),
        (7.0, 274.1, 1.43, 2.01, "pebbles", 0.41, 10),
        (-4.1, 276.4, 1.40, 1.98, "pebbles", 0.44, 12),
    ),
}


def placements(section, accepts):
    rng = np.random.default_rng({"Opening": 164, "River": 468, "Basin": 582}[section])
    items = []
    for x, y, rx, ry, rock, scale, count in BEDS[section]:
        angle = rng.uniform(-np.pi, np.pi)
        if accepts(x, y, scale * 1.45, rock=True):
            items.append((rock, x, y, scale, angle))
        # A few irregular pockets of foliage with breaks between each bed.
        for _ in range(count):
            xx, yy = x + rng.normal(0, rx * 0.54), y + rng.normal(0, ry * 0.56)
            size = rng.uniform(0.72, 1.36)
            kind = rng.choice(("grass_a", "grass_b", "grass_c"), p=(0.57, 0.18, 0.25))
            angle = rng.uniform(-np.pi, np.pi)
            if accepts(xx, yy, size * 0.24, rock=False) and np.hypot(xx - x, yy - y) > scale * 0.92:
                items.append((kind, xx, yy, size, angle))
    return items


def pigment(image, x, y, period):
    rows, cols = image.shape[:2]
    u = np.mod((x + 0.22 * y) / period, 1) * cols
    v = np.mod((y - 0.17 * x) / period, 1) * rows
    return image[v.astype(np.int32), u.astype(np.int32)]


def enrich(color, x, y, shore, mud, textures):
    """Keep a broken damp edge and visible pigment at the same world-space scale."""
    centered = {key: image.astype(np.float32) - image.mean(axis=(0, 1)) for key, image in textures.items()}
    for start in range(0, color.shape[0], 192):
        rows = slice(start, start + 192)
        xx = x if x.shape[0] == 1 else x[rows]
        yy, edge, blend = y[rows], shore[rows], mud[rows]
        grass = pigment(centered["grass"], xx, yy, 3.4)
        sediment = pigment(centered["mud"], xx, yy, 2.7)
        fine = pigment(centered["silt"], xx - 0.8 * np.sin(yy * 0.83), yy, 1.7)
        dry = np.clip((edge + 0.22) / 0.65, 0, 1)
        pigment_mask = (0.52 + 0.48 * np.sin(xx * 1.12 + yy * 0.74) ** 2) * dry
        detail = grass + (sediment - grass) * blend[..., None]
        color[rows] += detail * (pigment_mask * 1.02)[..., None]
        broken = 0.60 + 0.40 * np.cos(xx * 1.9 - yy * 2.3 + np.sin(yy * 0.71))
        wet_rim = np.exp(-((edge - 0.19) / 0.38) ** 2) * broken
        silt = np.exp(-((edge + 0.48) / 0.57) ** 2) * (1 - 0.38 * broken)
        color[rows] += fine * (wet_rim * 0.52 + silt * 0.62)[..., None]
        color[rows] += wet_rim[..., None] * (-11, -9, -5) + silt[..., None] * (6, 5, 1)
    return color


def contact_shade(color, x, y, items, dry):
    """Bake a grounded soft edge into the matte surface instead of adding transparent planes."""
    xs, ys = x[0], y[:, 0]
    for kind, cx, cy, size, _ in items:
        grass = kind.startswith("grass")
        radius = size * (0.33 if grass else 0.83)
        # Shift the wash slightly away from the game's warm upper-left light.
        cx += radius * 0.24
        cy += radius * 0.14
        cols = np.flatnonzero(abs(xs - cx) < radius * 2.5)
        rows = np.flatnonzero(abs(ys - cy) < radius * 2.0)
        if not len(cols) or not len(rows):
            continue
        cols, rows = slice(cols[0], cols[-1] + 1), slice(rows[0], rows[-1] + 1)
        wash = np.exp(-((xs[cols] - cx) / radius) ** 2 - ((ys[rows, None] - cy) / (radius * 0.74)) ** 2)
        amount = (wash * dry[rows, cols] * (0.52 if grass else 1.0))[..., None]
        color[rows, cols] += amount * (-18, -15, -11)
    return color
