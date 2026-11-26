"""Sample the delivered private USDZ terrain at single-route spawn, rest and landing contacts.

Run with Blender's standalone USD-enabled Python; this script does not start Blender.
Arguments: the final outer Debug ZIP or directory containing GooseLinearPreview,
and optionally the project layout JSON. An outer ZIP is read directly.
"""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from pxr import Gf, Usd, UsdGeom


# Keep these layout/renderer transforms aligned with GooseLinearLayout and GooseLinearScenery.
FOG_SEAM = 28
FIRST_BANK = (-0.65, 78, 0)
FIRST_BANK_SPACING = 0.75
MARSH_ORIGIN = (-20, 161, 0)
BASELINE_MARSH_SCALE = (0.53, 0.74)
EXIT_BANK = (1, 214, 0)
EXIT_BANK_SPACING = 0.48
BASIN_ENTRY = 242
TOLERANCE = 0.010  # in Blender units (approximately 0.278 RealityKit units)
ROOT = Path(__file__).resolve().parents[4]
LAYOUT = ROOT / "Sources/FeatherTide/Resources/ft_goose_chapter_layout.json"
BASIN_ART_LAYOUT = ROOT / "Assets/Watercolor/Goose/Blender/LVL-S6/v001/s6_layout.json"


def usdz(source: Path, name: str) -> bytes:
    filename = name + ".usdz"
    if source.is_dir():
        nested = source / "GooseLinearPreview" / filename
        return (nested if nested.exists() else source / filename).read_bytes()
    with ZipFile(source) as bundle:
        return bundle.read(f"GooseLinearPreview/{filename}")


def triangles(stage: Usd.Stage, cache: UsdGeom.XformCache, group: str) -> list:
    output = []
    for prim in stage.Traverse():
        path = str(prim.GetPath()).split("/")
        if not prim.IsA(UsdGeom.Mesh) or group not in path:
            continue
        mesh = UsdGeom.Mesh(prim)
        if mesh.ComputeVisibility() == UsdGeom.Tokens.invisible:
            continue
        transform = cache.GetLocalToWorldTransform(prim)
        points = [transform.Transform(Gf.Vec3d(p)) for p in mesh.GetPointsAttr().Get()]
        game_axis = [(p[0], -p[2], p[1]) for p in points]
        face_indices = mesh.GetFaceVertexIndicesAttr().Get()
        start = 0
        hidden_faces = set(mesh.GetHoleIndicesAttr().Get() or ())
        for face_id, count in enumerate(mesh.GetFaceVertexCountsAttr().Get()):
            face = face_indices[start : start + count]
            start += count
            if face_id in hidden_faces:
                continue
            # The exported terrain comprises triangles and convex quads.
            for edge in range(1, count - 1):
                output.append(tuple(game_axis[face[i]] for i in (0, edge, edge + 1)))
    if not output:
        raise ValueError(f"No visible triangles under {group}")
    return output


def height_at(x: float, y: float, faces: list) -> float | None:
    hits = []
    for (ax, ay, ah), (bx, by, bh), (cx, cy, ch) in faces:
        if x < min(ax, bx, cx) or x > max(ax, bx, cx) or y < min(ay, by, cy) or y > max(ay, by, cy):
            continue
        det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(det) < 1e-12:
            continue
        a = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / det
        b = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / det
        c = 1 - a - b
        if min(a, b, c) >= -1e-9:
            hits.append(a * ah + b * bh + c * ch)
    return max(hits, default=None)


def slots(layout: dict, site: str, baseline: bool, unified_opening: bool):
    original_fog = layout["stages"][0]["exit"][1]
    if site == "opening":
        for x, y in layout["spawn"]:
            yield (x, y, 0), (x, y * original_fog / FOG_SEAM, 0)
    elif site == "marsh":
        rx, ry, rh = layout["rests"][2]
        ox, oy, oh = MARSH_ORIGIN
        sx, sy = BASELINE_MARSH_SCALE
        for x, y, h in layout["protectedSlots"]:
            point = (x - rx + ox, y - ry + oy, h - rh + oh)
            local = ((x - rx) / sx, (y - ry) / sy, h - rh) if baseline else point
            yield point, local
    elif site in ("first-shore", "exit-bank"):
        (x, y, h), spacing, entry = (
            (FIRST_BANK, FIRST_BANK_SPACING, FOG_SEAM) if site == "first-shore" else (EXIT_BANK, EXIT_BANK_SPACING, 0)
        )
        for index in range(12):
            side = x + (index % 3 - 1) * spacing
            forward = y + (index // 3 - 1.5) * spacing
            local = forward * original_fog / FOG_SEAM if site == "first-shore" and unified_opening else forward - entry
            yield (side, forward, h), (side, local, h)
    else:
        y0 = layout["stages"][6]["entry"][1]
        for x, y, h in layout["slots"]:
            yield (x, y - y0 + BASIN_ENTRY, h), (x, y - y0, h)


def contact_matches(expected: float, ground: float | None, water: float | None) -> bool:
    if expected < -0.1:
        return (
            water is not None and abs(water - expected) <= TOLERANCE
            and ground is not None and ground < water - TOLERANCE
        )
    return (
        ground is not None and abs(ground - expected) <= TOLERANCE
        and (water is None or water < ground - TOLERANCE)
    )


def probe_basin_supports(ground_faces: list, water_faces: list) -> list:
    """The authored animation plants the contact about 0.218 BU behind its slot."""
    slots = json.loads(BASIN_ART_LAYOUT.read_bytes())["landing_slots"]
    failures = []
    print("BASIN AUTHORED ANIMATION SUPPORTS")
    print("slot\tasset contact x\tasset contact forward\ttarget h\tground h\twater h\tverified")
    for i, slot in enumerate(slots, start=1):
        x, y, h = slot["measured_support_touch_BU"]
        ground = height_at(x, y, ground_faces)
        water = height_at(x, y, water_faces)
        ok = contact_matches(h, ground, water)
        if not ok:
            failures.append(f"basin animation support {i}")
        fields = [display_number(value) for value in (x, y, h, ground, water)]
        print("\t".join([f"{i:02d}", *fields, "PASS" if ok else "FAIL"]))
    return failures


def probe(source: Path, layout: dict, site: str, baseline: bool) -> list:
    if site == "basin":
        asset, ground_group, water_group = "ft_goose_linear_basin", "LandingBasin_Ground", "LandingBasin_Water"
    elif site in ("opening", "first-shore"):
        asset = "ft_goose_scene_s0" if site == "opening" else "ft_goose_scene_s1"
        ground_group, water_group = "OpeningShoreTerrain", None
    elif baseline:
        asset, ground_group, water_group = "ft_goose_linear_marsh", "ProtectedMarsh_Ground", "ProtectedMarsh_Water"
    else:
        # The polished river and banks share an opaque, continuous terrain mesh.
        asset, ground_group, water_group = "ft_goose_linear_landscape", "RouteGround", None
    failures = []
    with TemporaryDirectory(prefix=f"feathertide-contact-{site}-") as directory:
        layer = Path(directory) / f"{site}.usdz"
        data = usdz(source, asset)
        layer.write_bytes(data)
        stage = Usd.Stage.Open(str(layer))
        if stage is None or UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.y:
            raise ValueError(f"{site} is not a readable Y-up stage")
        unified_opening = site == "first-shore" and not stage.GetPrimAtPath("/root/S1_Tailwind/OpeningShoreTerrain")
        if unified_opening:
            asset = "ft_goose_scene_s0"
            data = usdz(source, asset)
            layer = Path(directory) / "opening.usdz"
            layer.write_bytes(data)
            stage = Usd.Stage.Open(str(layer))
        cache = UsdGeom.XformCache()
        ground_faces = triangles(stage, cache, ground_group)
        water_faces = triangles(stage, cache, water_group) if water_group else []
        anchor = {prim.GetName(): prim for prim in stage.Traverse() if prim.GetName().startswith("S6_LandingSlot_")}
        surface = f"{len(water_faces)} water triangles" if water_group else "continuous ground and water mesh"
        print(f"{site.upper()} | {len(ground_faces)} ground triangles, {surface}")
        print(f"{asset}.usdz SHA-256 {sha256(data).hexdigest()}")
        print("slot\tlayout x\tlayout forward\ttarget h\tmesh x\tmesh forward\tground h\twater h\tcontact\tverified")
        for i, (point, local) in enumerate(slots(layout, site, baseline, unified_opening), start=1):
            x, y, h = local
            ground = height_at(x, y, ground_faces)
            water = height_at(x, y, water_faces)
            ok = contact_matches(h, ground, water)
            if site == "basin":
                prim = anchor.get(f"S6_LandingSlot_{i:02d}")
                actual = cache.GetLocalToWorldTransform(prim).ExtractTranslation() if prim else None
                ok = ok and actual is not None and max(abs(a - b) for a, b in zip(actual, (x, h, -y))) <= TOLERANCE
            if not ok:
                failures.append(f"{site} slot {i}")
            label = "water" if h < -0.1 else "dry"
            values = (*point, x, y, ground, water)
            fields = [display_number(value) for value in values]
            print("\t".join([f"{i:02d}", *fields, label, "PASS" if ok else "FAIL"]))
        if site == "basin":
            failures.extend(probe_basin_supports(ground_faces, water_faces))
    return failures


def display_number(value: float | None) -> str:
    if value is None:
        return "none"
    return f"{0.0 if abs(value) < 0.000005 else value:.5f}"


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--layout", type=Path, default=LAYOUT)
    parser.add_argument("--baseline", action="store_true", help="Use the former scaled ENV-016 marsh model.")
    polished_sites = ("opening", "first-shore", "marsh", "exit-bank", "basin")
    baseline_sites = ("marsh", "basin")
    parser.add_argument("--site", choices=polished_sites, action="append")
    args = parser.parse_args()
    layout = json.loads(args.layout.read_bytes())
    sites = args.site or (baseline_sites if args.baseline else polished_sites)
    if args.baseline and any(site not in baseline_sites for site in sites):
        parser.error("Baseline sampling supports the protected marsh and basin.")
    failures = [
        failure for site in sites for failure in probe(args.source, layout, site, args.baseline)
    ]
    if failures:
        print("Failed: " + ", ".join(failures))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
