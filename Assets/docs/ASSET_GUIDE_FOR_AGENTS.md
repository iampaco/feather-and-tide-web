# Feather & Tide — Asset Guide for Agents (EN index)

**Primary doc (Chinese, authoritative):** [`素材说明与接入指南.md`](./素材说明与接入指南.md)  
**Style board summary:** [`style-board.md`](./style-board.md)  
**Ledger (source of truth for counts/paths):** [`asset-ledger.md`](./asset-ledger.md)  
**Human/agent entry:** [`../README.md`](../README.md)

> English-only agents: follow this page for engineering contracts, then resolve every file by **Asset ID** in the ledger. Do not invent paths.

All index and ledger paths are relative to the **project root**. Read [library conventions](素材库使用约定.md) first. The library holds candidates; only cleared, cleaned and accepted exports enter `Sources/FeatherTide/Resources/`. Keep source IDs and map them to project `ft_…` export names in the production ledger. Follow the current active plan and selected V07 wetland direction; this batch style board does not override them.

## Project

- Game: **Feather & Tide / 羽与潮** — healing 2D watercolor migration, **iOS SpriteKit**
- Lines: **Goose** (bar-headed goose) · **Whale** (baleen) · **Deer** (reindeer)
- Locked `style_board`: **`SB-2026-11-07-v1`**
- License update, 2026-11-08: **Paco explicitly confirmed rights to use this Grok Imagine batch in Feather & Tide and authorized processing/integration**. Basis is the owner's statement; source terms still need archiving. This is not a universal commercial-license or attribution-free determination. Historical pending text below is superseded by `asset-index.json` / the current ledger; art/device acceptance remains separate.

## Read order

1. This index + Chinese §1–§3 (style / naming / bans)
2. `asset-ledger.md` → fetch by Asset ID
3. Integrate per Chinese §8: Graybox → parallax → hero loops → Trace overlay → UI → VFX

## Directory contract

```text
Assets/
  Watercolor/
    Goose/{Characters,Scenes/{WET,MTN,CST,OPT4},Traces,UI,VFX,Palette}
    Whale/{Characters,Scenes/{OPEN,NURSE,LANE},Traces,UI,VFX,Palette}
    Deer/{Characters,Scenes/{TUND,VAL,EDGE},Traces,UI,VFX,Palette}
    Shared/
  Graybox/
  Audio/{Creatures,Environment,Traces,Music,SFX}/
  UI/
  Haptics/
  refs/
  docs/
```

## Naming

| Kind | Pattern |
|---|---|
| General | `{line}_{category}_{desc}_{##}.png` (zero-padded frame indices) |
| Parallax | `{line}_scene_{seg}_{layer}.png` |
| Layers | `sky` \| `far` \| `mid` \| `near` \| `fog` \| `water` |
| Asset ID | filename without extension |

`line`: `goose` \| `whale` \| `deer` \| `shr`

Seg folders (UPPER) vs filename seg (lower): e.g. `Scenes/WET/goose_scene_wet_sky.png`.

## Color temperatures

| Line | Palette feel |
|---|---|
| Goose | warm gold / peach / mauve dusk |
| Whale | teal / ocean blue / pale wave |
| Deer | sage / lilac / moss brown |

**Banned:** alarm red, blood, logos/brands, car crashes, entanglement close-ups (nets only as distant soft traces).

## Anchors

| Line | `anchorPoint` semantics |
|---|---|
| Goose | chest center |
| Whale | inter-segment joints / tail axis / pectoral root |
| Deer | torso center |

## Animation loops

| Loop | Frames (pattern) |
|---|---|
| FLY | `goose_char_fly_side_01…08` |
| WALK | `deer_char_walk_01…08` |
| RUN | `deer_char_run_01…06` |
| BREACH | `whale_char_breach_01…04` |
| TAKEOFF→FLY | `goose_char_takeoff_01…06` then FLY |
| LAND→REST | `goose_char_land_01…06` then `rest_float_*` |

**Warning:** frames are **not** pixel-aligned to one skeleton. Do not ship loops without alignment. Comment `TODO: frames not pixel-aligned`.

## Parallax speed roles (v0–v3)

| Role | Layer | Suggested × playerVx |
|---|---|---|
| v0 | sky | 0.05–0.15 |
| v1 | far | 0.25–0.40 |
| v2 | mid | 0.55–0.70 |
| v3 | near | 0.85–1.10 |
| special | fog / water | see Chinese §4.4 |

**Traces are independent overlays** — never bake into `mid`.

## Palette JSON

- `{line}_pal_main.json` — base hex roles  
- `{line}_pal_swap_cfg.json` — named modes (`polluted`, `turbid`, `mine_dust`, …)  
- Assert `style_board == SB-2026-11-07-v1` before applying.

## Post-process truth

- PNGs are **JPG rewrapped**; **no effective transparency** (some RGBA files have fully opaque alpha)
- Agents may preview with chroma-key against paper cream; mark nodes as needing real cutout
- Do **not** claim cutouts done or cite unverified performance numbers

## Approx counts (ledger wins)

| Line | ~PNG |
|---|---|
| Goose full (MVP≈57 + delta≈37, incl. Shared) | ~90+ |
| Whale | ~50 |
| Deer | ~58 |

## Do not

- Invent audio/haptics files  
- Claim commercial license cleared  
- Use alarm-red danger styling  
- Rename files without updating the ledger  
- Treat unaligned frames as final animation  

## SpriteKit sketch

```swift
let tex = (1...8).map { SKTexture(imageNamed: String(format: "goose_char_fly_side_%02d", $0)) }
node.anchorPoint = CGPoint(x: 0.5, y: 0.45) // chest-ish until art-aligned
node.run(.repeatForever(.animate(with: tex, timePerFrame: 0.1)), withKey: "FLY")
```

For full tables, swap keys, integration steps, and ledger column definitions, read the Chinese guide §§4–10.
