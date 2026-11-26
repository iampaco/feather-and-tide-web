import {
  BufferGeometry,
  Color,
  Float32BufferAttribute,
  Group,
  Mesh,
  ShapeUtils,
  Vector2,
  type ShaderMaterial,
} from "three";
import { clamp, lerp, type Vec2 } from "../core/math";
import { contains } from "../levels/geometry";
import type { LevelSchema } from "../levels/schema";
import { createSurfaceUniforms } from "./migrationAtmosphere";
import { riverBankMaterial, riverWaterMaterial } from "./water";

export interface MigrationTerrain {
  readonly group: Group;
  height(x: number, z: number): number;
}

type Reach = readonly [z: number, west: number, east: number, depth: number];

// The authored banks follow the Web route. Islands and shallows share the same
// bed, so the shoreline keeps its shape when the player looks back or banks.
const reaches: readonly Reach[] = [
  [-70, -30, 35, 2.4],
  [-14, -18, 22, 2.0],
  [18, -17, 33, 3.2],
  [47, -29, 22, 3.4],
  [68, -23, 39, 3.9],
  [103, -30, 47, 4.0],
  [126, -33, 45, 4.0],
  [152, -49, 23, 3.1],
  [178, -36, 21, 3.1],
  [205, -26, 31, 2.9],
  [222, -41, 49, 3.5],
  [247, -52, 85, 4.0],
  [283, -56, 108, 4.6],
  [314, -59, 112, 5.1],
  [348, -53, 112, 5.3],
  [378, -58, 98, 4.8],
  [397, -54, 73, 4.0],
  [416, -37, 52, 3.2],
  [432, -29, 40, 4.1],
  [458, -27, 40, 4.4],
  [480, -35, 29, 4.8],
  [511, -35, 55, 4.0],
  [552, -101, 56, 3.2],
  [581, -105, 54, 2.8],
  [608, -108, 55, 3.5],
  [636, -94, 53, 3.4],
  [657, -68, 42, 4.0],
  [675, -54, 34, 3.3],
  [698, -43, 32, 2.7],
  [724, -52, 27, 3.9],
  [746, -43, 29, 3.4],
  [774, -27, 35, 2.6],
  [795, -31, 32, 1.8],
  [816, -42, 41, 1.65],
  [838, -46, 46, 1.85],
  [855, -35, 36, 1.8],
  [875, -27, 17, 2.1],
  [896, -34, 15, 2.8],
  [925, -41, 31, 3.1],
  [964, -36, 28, 3.9],
];

type Inlet = readonly [
  x: number,
  z: number,
  width: number,
  length: number,
  top: number,
  angle?: number,
];

const islands: readonly Inlet[] = [
  [-10, -14, 29, 23, 0.48, -0.2],
  [-20, 26, 17, 25, 0.96, 0.28],
  [-24, 33, 11, 19, 1.22, -0.32],
  [24, 57, 15.5, 25, 1.26, -0.37],
  [29, 63, 11, 15, 1.36, 0.51],
  [26, 149, 13, 25, 0.7, 0.35],
  [-21, 204, 23, 24, 0.9, -0.46],
  [9, 224, 11, 22, 0.42, 0.2],
  [97, 302, 10, 20, 0.48, -0.35],
  [100, 332, 7, 24, 0.28, 0.17],
  [102, 359, 19, 24, 0.82, 0.34],
  [35, 446, 20, 28, 1.02, 0.31],
  [-20, 461, 16, 26, 0.83, -0.19],
  [-71, 567, 6.8, 14, 0.64, -0.26],
  [-69, 586, 5.4, 23, 0.52, 0.07],
  [-70, 605, 6.5, 16, 0.68, 0.25],
  [-105, 561, 8, 15, 0.48, -0.31],
  [-104, 617, 9.5, 24, 0.67, 0.22],
  [-30, 694, 27, 26, 1.16, -0.28],
  [26, 711, 19, 20, 0.7, 0.35],
  [-35, 797, 20, 24, 0.98, -0.43],
  [37, 813, 23, 23, 0.91, 0.29],
  [-39, 836, 20, 26, 0.79, 0.27],
  [39, 849, 23, 22, 0.84, -0.36],
  [-24, 867, 23, 16, 0.83, -0.39],
  [15, 876, 22, 18, 0.88, 0.39],
];

// Narrow channels behind the spits break the dry bank into wetland shelves.
const openingSideChannels: readonly Inlet[] = [
  [-26, -3, 5.5, 17, -0.44, 0.16],
  [33, 15, 7.5, 24, -0.64, 0.24],
  [38, 61, 6.3, 23, -0.56, -0.34],
  [-32, 62, 7.4, 14, -0.34, -0.52],
];

type Chroma = readonly [
  deep: Color,
  shallow: Color,
  sky: Color,
  earth: Color,
  wet: Color,
  rock: Color,
];

interface Paint {
  readonly tones: Chroma;
  readonly flow: number;
  readonly glint: number;
}

interface Wash {
  readonly z: number;
  readonly paint: Paint;
}

function colors(
  deep: string,
  shallow: string,
  sky: string,
  earth: string,
  wet: string,
  rock: string,
): Chroma {
  return [
    new Color(deep),
    new Color(shallow),
    new Color(sky),
    new Color(earth),
    new Color(wet),
    new Color(rock),
  ];
}

const washes: readonly Wash[] = [
  {
    z: 12,
    paint: {
      tones: colors(
        "#3e757b",
        "#a5b493",
        "#f3d7a1",
        "#8c9d71",
        "#a58c66",
        "#777f73",
      ),
      flow: -0.19,
      glint: 0.46,
    },
  },
  {
    z: 101,
    paint: {
      tones: colors(
        "#527f7d",
        "#84a68f",
        "#e3d5a0",
        "#91a16f",
        "#b19e73",
        "#79847d",
      ),
      flow: -0.06,
      glint: 0.38,
    },
  },
  {
    z: 190,
    paint: {
      tones: colors(
        "#4f8c88",
        "#8eb096",
        "#e6d7a3",
        "#8f9f67",
        "#b7a57b",
        "#7a8580",
      ),
      flow: 0.14,
      glint: 0.43,
    },
  },
  {
    z: 286,
    paint: {
      tones: colors(
        "#426977",
        "#789897",
        "#ced1c0",
        "#8a9273",
        "#95988a",
        "#727789",
      ),
      flow: -0.1,
      glint: 0.23,
    },
  },
  {
    z: 369,
    paint: {
      tones: colors(
        "#467d8d",
        "#83aca5",
        "#d5ded6",
        "#8d9e77",
        "#a5a68d",
        "#728490",
      ),
      flow: 0.06,
      glint: 0.3,
    },
  },
  {
    z: 459,
    paint: {
      tones: colors(
        "#3f7779",
        "#779e91",
        "#d0d9ba",
        "#8a9b67",
        "#aa9c73",
        "#727f76",
      ),
      flow: -0.36,
      glint: 0.37,
    },
  },
  {
    z: 540,
    paint: {
      tones: colors(
        "#477e82",
        "#8fa992",
        "#d4ddc3",
        "#83976d",
        "#a5a182",
        "#737f7a",
      ),
      flow: -0.21,
      glint: 0.35,
    },
  },
  {
    z: 603,
    paint: {
      tones: colors(
        "#4e8781",
        "#8fb496",
        "#e6e1b1",
        "#87a775",
        "#a9a479",
        "#738584",
      ),
      flow: 0.1,
      glint: 0.32,
    },
  },
  {
    z: 704,
    paint: {
      tones: colors(
        "#527c79",
        "#94aa8e",
        "#ded8a7",
        "#939b68",
        "#b0a278",
        "#858479",
      ),
      flow: -0.06,
      glint: 0.41,
    },
  },
  {
    z: 781,
    paint: {
      tones: colors(
        "#5d877e",
        "#a0b092",
        "#ebcc8e",
        "#a5a371",
        "#c1a679",
        "#8a8476",
      ),
      flow: 0.08,
      glint: 0.53,
    },
  },
  {
    z: 834,
    paint: {
      tones: colors(
        "#466f68",
        "#859c83",
        "#f1d7a3",
        "#a49765",
        "#b89064",
        "#857b6f",
      ),
      flow: 0.025,
      glint: 0.26,
    },
  },
  {
    z: 903,
    paint: {
      tones: colors(
        "#697f73",
        "#9ca784",
        "#e6cc96",
        "#969c6f",
        "#b1a478",
        "#818377",
      ),
      flow: 0.12,
      glint: 0.35,
    },
  },
];

const passSpur: Inlet = [-73, 319, 12, 35, 0, 0.17];
const lakeShelf: Inlet = [92, 330, 20, 53, 0, -0.1];

// Low dry-bank shoulders frame S0 and S2 from inside the valley. The higher
// ridgelines sit outside the flight area and share the ground mesh and sampler.
const bankShoulders: readonly Inlet[] = [
  [-48, 18, 21, 29, 2.9, -0.33],
  [-47, 67, 16, 25, 2.4, 0.23],
  [49, 35, 17, 30, 2.9, 0.41],
  [59, 79, 25, 28, 3.6, -0.42],
  [-61, 247, 17, 22, 4.6, -0.35],
  [-74, 278, 20, 32, 8.8, 0.27],
  [-79, 310, 17, 27, 6.2, -0.29],
  [-73, 345, 20, 33, 7.4, -0.16],
  [-68, 371, 13, 22, 4.8, 0.35],
  [-64, 804, 22, 44, 1.9, -0.31],
  [61, 844, 26, 30, 1.5, 0.48],
];

const exteriorRidges: readonly Inlet[] = [
  [-37, -65, 64, 34, 8, 0.37],
  [39, -164, 65, 51, 18, -0.38],
  [-149, 40, 48, 71, 17, -0.31],
  [140, 56, 33, 66, 14, 0.22],
  [194, 80, 52, 96, 28, -0.48],
  [-192, 154, 60, 70, 25, 0.49],
  [-137, 233, 37, 45, 23, -0.4],
  [-150, 302, 43, 57, 33, 0.32],
  [-204, 358, 67, 77, 39, -0.44],
  [126, 309, 33, 71, 6, -0.11],
  [155, 368, 56, 57, 12, 0.25],
  [194, 289, 56, 89, 19, -0.34],
  [-154, 438, 44, 54, 19, 0.34],
  [164, 457, 56, 63, 17, -0.4],
  [-181, 570, 68, 112, 17, -0.23],
  [156, 611, 42, 87, 13, 0.39],
  [-174, 734, 56, 69, 14, 0.46],
  [154, 773, 52, 80, 15, -0.38],
  [-77, 905, 48, 56, 14, 0.23],
  [49, 920, 64, 57, 11, -0.34],
];

const lakeColors = colors(
  "#477f9a",
  "#88aeaa",
  "#d4e1e0",
  "#809777",
  "#adb6a0",
  "#748c9a",
);
const shoalPigment = new Color("#b8c8a0");
const passColors = colors(
  "#3e5e73",
  "#69848d",
  "#ccd5d4",
  "#777e77",
  "#969b8c",
  "#666f8b",
);
const reserveColors = colors(
  "#4d8171",
  "#92aa87",
  "#d7d8a6",
  "#7e995f",
  "#a49870",
  "#6c8274",
);
const openingWetSoil = new Color("#736c54");
const openingMeadow = new Color("#7e9569");

function blend01(start: number, end: number, value: number): number {
  const t = clamp((value - start) / (end - start));
  return t * t * (3 - 2 * t);
}

function range(
  min: number,
  max: number,
  shoulder: number,
  value: number,
): number {
  return (
    blend01(min - shoulder, min, value) *
    (1 - blend01(max, max + shoulder, value))
  );
}

function oval(x: number, z: number, shape: Inlet): number {
  const [centerX, centerZ, width, length, , angle = 0] = shape;
  const dx = x - centerX;
  const dz = z - centerZ;
  const sin = Math.sin(angle);
  const cos = Math.cos(angle);
  return Math.hypot(
    (dx * cos - dz * sin) / width,
    (dz * cos + dx * sin) / length,
  );
}

function lakeShoal(x: number, z: number): number {
  const scallop = 0.07 * Math.sin(z * 0.15 + x * 0.11);
  return 1 - blend01(0.25, 1.08, oval(x, z, lakeShelf) + scallop);
}

function ridgeRelief(
  x: number,
  z: number,
  shapes: readonly Inlet[],
  rugged: boolean,
): number {
  let rise = 0;
  for (const shape of shapes) {
    const [cx, cz, width, length, elevation] = shape;
    const reach = Math.max(width, length);
    if (Math.abs(x - cx) > reach || Math.abs(z - cz) > reach) continue;
    const foot = oval(x, z, shape);
    const shoulder = 1 - blend01(0.12, 1, foot);
    const crest = rugged
      ? 0.75 + 0.25 * Math.cos((x - cx) * 0.15 + (z - cz) * 0.1)
      : 1;
    rise = Math.max(rise, shoulder * crest * elevation);
  }
  return rise;
}

function softHigher(a: number, b: number): number {
  const overlap = Math.max(0.24 - Math.abs(a - b), 0);
  return Math.max(a, b) + (overlap * overlap) / 0.96;
}

function channel(z: number): Reach {
  const [first = [-70, -30, 35, 3]] = reaches;
  if (z <= first[0]) return first;
  for (let i = 1; i < reaches.length; i++) {
    const after = reaches[i];
    const before = reaches[i - 1];
    if (before && after && z <= after[0]) {
      const t = blend01(before[0], after[0], z);
      return [
        z,
        lerp(before[1], after[1], t),
        lerp(before[2], after[2], t),
        lerp(before[3], after[3], t),
      ];
    }
  }
  return reaches.at(-1) ?? first;
}

function paintAt(z: number): Paint {
  const previousIndex = washes.findLastIndex((anchor) => z >= anchor.z);
  const previous = washes[Math.max(0, previousIndex)];
  const next = washes[previousIndex + 1];
  if (!previous) throw new Error("Migration water palette is empty");
  if (!next || next === previous) return previous.paint;

  const t = blend01(previous.z, next.z, z);
  const a = previous.paint;
  const b = next.paint;
  const tones: Chroma = [
    a.tones[0].clone().lerp(b.tones[0], t),
    a.tones[1].clone().lerp(b.tones[1], t),
    a.tones[2].clone().lerp(b.tones[2], t),
    a.tones[3].clone().lerp(b.tones[3], t),
    a.tones[4].clone().lerp(b.tones[4], t),
    a.tones[5].clone().lerp(b.tones[5], t),
  ];
  return {
    tones,
    flow: lerp(a.flow, b.flow, t),
    glint: lerp(a.glint, b.glint, t),
  };
}

function bankElevation(
  x: number,
  z: number,
  profile: Reach,
  level: LevelSchema,
  turbines: readonly Vec2[],
): number {
  const [, west, east, depth] = profile;
  const broad = Math.sin(x * 0.12 + z * 0.14) * Math.sin(z * 0.13 - x * 0.11);
  const fine = Math.sin(x * 0.28 - z * 0.22) * Math.cos(z * 0.21 + x * 0.08);
  const shoreline = Math.min(
    x - west + Math.sin(z * 0.171) * 1.7 + Math.sin(z * 0.34 + 0.6) * 1.25,
    east - x + Math.sin(z * 0.135 + 3) * 2.15 + Math.sin(z * 0.27) * 0.86,
  );
  let y =
    shoreline >= 0
      ? -0.12 - depth * blend01(0, 17 + 2.4 * broad, shoreline)
      : lerp(-0.12, 1.26 + 0.23 * broad, blend01(0, 15, -shoreline));
  y += broad * 0.14 + fine * 0.1;

  for (const shape of islands) {
    const reach = (shape[2] + shape[3]) * 1.64;
    if (Math.abs(z - shape[1]) > reach || Math.abs(x - shape[0]) > reach)
      continue;
    const distance = oval(x, z, shape) + 0.07 * broad;
    if (distance >= 1.56) continue;
    const top = shape[4] + broad * 0.29 + fine * 0.12;
    const shelf = top - (top + 1.95) * blend01(0.12, 1.14, distance);
    const basinFalloff = 4.7 * blend01(1.02, 1.56, distance);
    y = softHigher(y, shelf - basinFalloff);
  }

  if (z > -26 && z < 90) {
    for (const channel of openingSideChannels) {
      const distance = oval(x, z, channel) + fine * 0.11;
      const creek = 1 - blend01(0.22, 1.05, distance);
      y = lerp(y, Math.min(y, channel[4] + fine * 0.16), creek);
    }
  }

  // The sheltered shelf is shallower along the reeds and open down the middle.
  // It shades the bay through the same bed as the main river.
  const sheltered = range(552, 623, 17, z) * range(-101, -76, 7, x);
  if (sheltered > 0) {
    const channel = 1 - blend01(2, 12, Math.abs(x + 88));
    const shelf = lerp(-0.52, -1.65, channel) + 0.16 * broad;
    y = lerp(y, Math.max(y, shelf), sheltered * 0.85);
  }

  // The infrastructure has its own low shelves inside the sweep; the outer
  // channel remains uninterrupted and the visible volume cannot suggest a gap.
  for (const point of turbines) {
    const distance = Math.hypot(x - point.x, z - point.z);
    if (distance <= 11)
      y = softHigher(y, lerp(0.21, -6.65, blend01(2.6, 11, distance)));
  }

  if (
    z > 677 &&
    z < 754 &&
    level.landmarks.some(({ id }) => id === "gallery-inlet")
  ) {
    const inlet =
      range(691, 739, 14, z) * (1 - blend01(8, 19, Math.abs(x + 82)));
    const outlet = range(736, 743, 10, z) * range(-82, -40, 12, x);
    y = lerp(y, Math.min(-0.69, y), Math.max(inlet, outlet));
  }

  const openingPool = 1 - blend01(0.22, 0.91, oval(x, z, [1, -9, 8, 22, 0]));
  y = lerp(y, -0.035, openingPool);
  const rescuePool = 1 - blend01(0.34, 1.2, oval(x, z, [-49, 485, 19, 17, 0]));
  y = lerp(y, Math.min(y, -0.44), rescuePool);
  // The basin and its two smaller flooded shelves are cut into the same bed.
  // Their shallows sit behind the mud tongues and leave the flock's center open.
  const landingPool =
    1 - blend01(0.52, 1.14, oval(x, z, [-4, 832, 28, 35, 0, -0.22]));
  y = lerp(y, -1.22 - 0.27 * broad, landingPool);
  const westReedPool =
    1 - blend01(0.29, 1.0, oval(x, z, [-45, 812, 9, 16, 0, -0.34]));
  const eastReedPool =
    1 - blend01(0.3, 1.02, oval(x, z, [43, 845, 11, 18, 0, 0.28]));
  y = lerp(
    y,
    Math.min(y, -0.34 - 0.15 * broad),
    Math.max(westReedPool, eastReedPool),
  );
  const landingBanks = range(806, 875, 15, z);
  y -= Math.max(0, y - 1.2) * landingBanks;
  const westPass = range(263, 361, 29, z) * (1 - blend01(-68, -47, x));
  const spur = 1 - blend01(0.14, 1.05, oval(x, z, passSpur));
  const ribs = 0.7 + 0.3 * Math.cos(z * 0.22 + x * 0.41);
  y += westPass * (0.27 + spur * ribs * 1.33);
  // The lake side shoal is read in the water's depth, including from above.
  // Keep the open approach underwater and the higher reeds on its outer lip.
  y += Math.max(0, -0.46 + fine * 0.12 - y) * lakeShoal(x, z);

  const legalDistance = Math.max(
    level.bounds.min.x - x,
    x - level.bounds.max.x,
    level.bounds.min.z - z,
    z - level.bounds.max.z,
  );
  const outerRise = blend01(6, 82, legalDistance);
  const bankRise =
    blend01(0.34, 1.05, y) * ridgeRelief(x, z, bankShoulders, false);
  const rollingGround = 4.3 + 2.2 * Math.cos(x * 0.045 + z * 0.046);
  const backbone =
    blend01(2, 24, legalDistance) * ridgeRelief(x, z, exteriorRidges, true);
  return y + bankRise + outerRise * rollingGround + backbone;
}

function positions(start: number, end: number, spacing: number): number[] {
  const count = Math.ceil((end - start) / spacing);
  return Array.from({ length: count + 1 }, (_, i) =>
    lerp(start, end, i / count),
  );
}

function cell(axis: readonly number[], point: number): number {
  let first = 0;
  let last = axis.length - 1;
  while (last - first > 1) {
    const middle = Math.floor((first + last) / 2);
    if (point >= (axis[middle] ?? Infinity)) first = middle;
    else last = middle;
  }
  return first;
}

type Vertex = readonly [x: number, y: number, z: number];

function writeColor(buffer: number[], rgb: Color): void {
  buffer.push(rgb.r, rgb.g, rgb.b);
}

function makeRidge(
  level: LevelSchema,
  material: ShaderMaterial,
): { mesh: Mesh; height(x: number, z: number): number } | undefined {
  const zone = level.zones.find(
    (candidate) => candidate.id === "ridge-wall" && candidate.kind === "hazard",
  );
  if (!zone) return;
  const outline = zone.points.slice(0, -1).flatMap((point, i) => {
    const next = zone.points[i + 1] ?? point;
    const steps = Math.max(
      1,
      Math.ceil(Math.hypot(next.x - point.x, next.z - point.z) / 3.5),
    );
    return Array.from({ length: steps }, (_, step) => ({
      x: lerp(point.x, next.x, step / steps),
      z: lerp(point.z, next.z, step / steps),
    }));
  });
  const center = {
    x:
      (Math.min(...outline.map(({ x }) => x)) +
        Math.max(...outline.map(({ x }) => x))) *
      0.5,
    z:
      (Math.min(...outline.map(({ z }) => z)) +
        Math.max(...outline.map(({ z }) => z))) *
      0.5,
  };
  // The two bevels on each terrace interrupt the shale slopes with a narrow
  // ledge. The outermost ring still follows the complete hazard boundary.
  const profile = [
    [1, -0.045],
    [0.91, 0.72],
    [0.78, 2.25],
    [0.68, 2.48],
    [0.58, 5.75],
    [0.48, 6.14],
    [0.31, 9.18],
    [0.17, 11.2],
  ] as const;
  const vertices: Vertex[] = [];
  for (const [ring, [radius, height]] of profile.entries()) {
    for (const p of outline) {
      const fold = Math.sin(p.z * 0.23 + p.x * 0.43);
      const wobble = fold * 0.035 + 0.018 * Math.sin(p.z * 0.53);
      const innerRadius = radius + (ring > 1 ? wobble * radius : 0);
      const drift = 2.1 * Math.sin((p.z - 268) * 0.089) * (1 - innerRadius);
      const x = lerp(center.x, p.x, innerRadius) + drift;
      const longer = lerp(
        center.z,
        p.z,
        lerp(innerRadius, Math.sqrt(innerRadius), 0.44),
      );
      const projected = contains(zone.points, { x, z: longer })
        ? { x, z: longer }
        : {
            x: lerp(center.x, p.x, innerRadius),
            z: lerp(center.z, p.z, innerRadius),
          };
      const shoulder = Math.max(
        1 - blend01(0, 24, Math.abs(projected.z - 286)),
        0.86 * (1 - blend01(0, 26, Math.abs(projected.z - 334))),
      );
      const crest = 0.63 + 0.39 * shoulder + 0.07 * fold;
      vertices.push([
        projected.x,
        height * (ring > 1 ? crest : 1),
        projected.z,
      ]);
    }
  }

  const actualMin = {
    x: Math.min(...outline.map((point) => point.x)),
    z: Math.min(...outline.map((point) => point.z)),
  };
  const actualMax = {
    x: Math.max(...outline.map((point) => point.x)),
    z: Math.max(...outline.map((point) => point.z)),
  };
  const triangles: { a: Vertex; b: Vertex; c: Vertex; det: number }[] = [];
  const index: number[] = [];
  const size = outline.length;

  function triangle(i: number, j: number, k: number): void {
    const a = vertices[i],
      b = vertices[j],
      c = vertices[k];
    if (!a || !b || !c) return;
    const det = (b[0] - a[0]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[0] - a[0]);
    if (Math.abs(det) < 0.00001) return;
    if (det < 0) index.push(i, j, k);
    else index.push(i, k, j);
    triangles.push({ a, b, c, det });
  }

  for (let i = 0; i < size; i++) {
    const j = (i + 1) % size;
    for (let ring = 0; ring < profile.length - 1; ring++) {
      triangle(ring * size + i, ring * size + j, (ring + 1) * size + i);
      triangle((ring + 1) * size + i, ring * size + j, (ring + 1) * size + j);
    }
  }
  const inner = (profile.length - 1) * size;
  // The two crowns share a meandering cap rather than converging on one
  // center vertex. Sample it through the same triangles used for the slopes.
  const contour = vertices.slice(inner).map(([x, , z]) => new Vector2(x, z));
  for (const [a, b, c] of ShapeUtils.triangulateShape(contour, []))
    if (a !== undefined && b !== undefined && c !== undefined)
      triangle(inner + a, inner + b, inner + c);

  const pigments = [[], [], []] as [number[], number[], number[]];
  const peak = new Color("#a0a7b8");
  const shale = new Color("#4c5671");
  const lichen = new Color("#acac89");
  const toe = new Color("#838970");
  const shade = new Color();
  for (const [i, [x, y, z]] of vertices.entries()) {
    const band = Math.floor(i / size);
    const strata = 0.5 + 0.5 * Math.sin(x * 0.33 - z * 0.17 + y * 0.59);
    const ledge = band === 3 || band === 5;
    const pigment = clamp(0.17 + (y / 10) * 0.5 + strata * 0.24);
    writeColor(
      pigments[0],
      shade
        .copy(toe)
        .lerp(peak, pigment)
        .lerp(lichen, ledge ? 0.34 + strata * 0.26 : 0),
    );
    writeColor(
      pigments[1],
      shade
        .copy(shale)
        .lerp(peak, pigment)
        .lerp(lichen, ledge ? 0.32 + strata * 0.16 : strata * 0.12),
    );
    writeColor(pigments[2], shade.copy(toe).multiplyScalar(0.88));
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute(
    "position",
    new Float32BufferAttribute(vertices.flat(), 3),
  );
  geometry.setAttribute(
    "earthPigment",
    new Float32BufferAttribute(pigments[0], 3),
  );
  geometry.setAttribute(
    "rockPigment",
    new Float32BufferAttribute(pigments[1], 3),
  );
  geometry.setAttribute(
    "wetPigment",
    new Float32BufferAttribute(pigments[2], 3),
  );
  geometry.setIndex(index);
  geometry.computeVertexNormals();
  const mesh = new Mesh(geometry, material);
  mesh.name = "watershed";

  return {
    mesh,
    height(x, z) {
      if (
        x < actualMin.x ||
        x > actualMax.x ||
        z < actualMin.z ||
        z > actualMax.z
      )
        return -Infinity;
      for (const { a, b, c, det } of triangles) {
        const dx = x - a[0],
          dz = z - a[2];
        const u = (dx * (c[2] - a[2]) - dz * (c[0] - a[0])) / det;
        const v = ((b[0] - a[0]) * dz - (b[2] - a[2]) * dx) / det;
        if (u >= -1e-7 && v >= -1e-7 && u + v <= 1 + 1e-7)
          return a[1] + u * (b[1] - a[1]) + v * (c[1] - a[1]);
      }
      return -Infinity;
    },
  };
}

function writePigment(
  pigments: readonly number[][],
  x: number,
  y: number,
  z: number,
  paint: Paint,
  color: Color,
): void {
  const eastLake = blend01(13, 37, x) * range(241, 371, 22, z);
  const westPass = (1 - blend01(-34, -8, x)) * range(244, 366, 23, z);
  const marsh = (1 - blend01(-72, -60, x)) * range(552, 634, 18, z);
  const spur = 1 - blend01(0.14, 1.16, oval(x, z, passSpur));
  const warmInlet =
    range(824, 871, 22, z) *
    (1 - blend01(7, 30, Math.abs(x - 25 + (z - 833) * 0.29)));
  const hillside = blend01(3.0, 18, y);
  const westernScarp = (1 - blend01(-60, -43, x)) * range(232, 351, 17, z);
  const shoal = lakeShoal(x, z);
  const opening = range(-36, 71, 28, z) * blend01(7, 24, Math.abs(x));
  const brokenBank =
    0.5 +
    0.33 * Math.sin(x * 0.41 + z * 0.19) +
    0.17 * Math.sin(x * 0.16 - z * 0.61);
  for (let i = 0; i < paint.tones.length; i++) {
    const bank = paint.tones[i],
      target = pigments[i];
    const lake = lakeColors[i],
      pass = passColors[i],
      reserve = reserveColors[i];
    if (!bank || !target || !lake || !pass || !reserve) continue;
    color
      .copy(bank)
      .lerp(lake, eastLake)
      .lerp(pass, westPass)
      .lerp(reserve, marsh);
    if (i === 1) color.lerp(shoalPigment, shoal * 0.9);
    if (i <= 1) color.lerp(paint.tones[2], warmInlet * (i === 0 ? 0.13 : 0.26));
    if (i === 3) color.lerp(passColors[5], spur * 0.85);
    if (i === 3)
      color.lerp(openingMeadow, opening * brokenBank * blend01(0.3, 1.1, y));
    if (i === 4)
      color.lerp(openingWetSoil, opening * (0.22 + 0.65 * brokenBank));
    if (i >= 3) {
      color.lerp(paint.tones[5], hillside * 0.67);
      color.lerp(passColors[5], westernScarp * blend01(1.15, 3.9, y) * 0.72);
    }
    writeColor(target, color);
  }
}

export function buildMigrationTerrain(
  level: LevelSchema,
  low: boolean,
  atmosphere = createSurfaceUniforms(),
): MigrationTerrain {
  const group = new Group();
  group.name = "migration-terrain";

  // Every view can turn back and towards the playable boundaries. Keep the
  // exterior mesh present even at the lowest camera pitch in a wide viewport.
  const margin = 195;
  const { min, max } = level.bounds;
  const xAxis = [
    ...positions(min.x - margin, min.x - 15, 10).slice(0, -1),
    ...positions(min.x - 15, max.x + 15, 2.5),
    ...positions(max.x + 15, max.x + margin, 10).slice(1),
  ];
  const zAxis = [
    ...positions(min.z - margin, min.z - 25, 10).slice(0, -1),
    ...positions(min.z - 25, max.z + 45, 3.5),
    ...positions(max.z + 45, max.z + margin, 10).slice(1),
  ];
  const profiles = zAxis.map(channel);
  const turbines = level.landmarks
    .filter((mark) => mark.kind === "turbine")
    .map((mark) => mark.pos);
  const heights = zAxis.map((z, k) =>
    xAxis.map((x) =>
      bankElevation(x, z, profiles[k] ?? channel(z), level, turbines),
    ),
  );
  const paints = zAxis.map(paintAt);
  const bankMaterial = riverBankMaterial(low, atmosphere);
  const waterMaterial = riverWaterMaterial(low, atmosphere);

  function sample(i: number, j: number): number {
    return (
      heights[Math.min(zAxis.length - 1, Math.max(0, j))]?.[
        Math.min(xAxis.length - 1, Math.max(0, i))
      ] ?? 0
    );
  }

  const vertexColor = new Color();
  function addPatch(
    left: number,
    right: number,
    start: number,
    end: number,
  ): void {
    const columns = right - left + 1;

    const land: number[] = [];
    const water: number[] = [];
    const bed: number[] = [];
    const normals: number[] = [];
    const flow: number[] = [];
    const pigments: number[][] = Array.from({ length: 6 }, () => []);
    const soilIndices: number[] = [];
    const waterIndices: number[] = [];

    function triangle(
      a: number,
      b: number,
      c: number,
      minY: number,
      maxY: number,
    ): void {
      // With the camera above the opaque water, submerged bed triangles and
      // water hidden by dry ground produce no pixels. Keep the whole shoreline.
      if (maxY >= 0) soilIndices.push(a, b, c);
      if (minY <= 0) waterIndices.push(a, b, c);
    }

    for (let j = start; j <= end; j++) {
      const z = zAxis[j];
      const paint = paints[j];
      if (z === undefined || !paint) continue;
      for (let i = left; i <= right; i++) {
        const x = xAxis[i];
        if (x === undefined) continue;
        const y = sample(i, j);
        land.push(x, y, z);
        water.push(x, 0, z);
        bed.push(y);
        const dx =
          (sample(i + 1, j) - sample(i - 1, j)) /
          ((xAxis[i + 1] ?? x) - (xAxis[i - 1] ?? x));
        const dz =
          (sample(i, j + 1) - sample(i, j - 1)) /
          ((zAxis[j + 1] ?? z) - (zAxis[j - 1] ?? z));
        const length = Math.hypot(dx, 1, dz);
        normals.push(-dx / length, 1 / length, -dz / length);
        writePigment(pigments, x, y, z, paint, vertexColor);
        const openLake = blend01(14, 40, x) * range(258, 376, 32, z);
        flow.push(
          lerp(paint.flow, -0.035, openLake * 0.82),
          lerp(paint.glint, 0.13, openLake),
        );
        if (i < right && j < end) {
          const a = (j - start) * columns + i - left;
          const b = a + columns;
          const south = sample(i, j + 1);
          const east = sample(i + 1, j);
          const corner = sample(i + 1, j + 1);
          triangle(
            a,
            b,
            a + 1,
            Math.min(y, south, east),
            Math.max(y, south, east),
          );
          triangle(
            a + 1,
            b,
            b + 1,
            Math.min(east, south, corner),
            Math.max(east, south, corner),
          );
        }
      }
    }
    if (soilIndices.length) addSoil();
    if (waterIndices.length) addWater();

    function addSoil(): void {
      const soil = new BufferGeometry();
      soil.setAttribute("position", new Float32BufferAttribute(land, 3));
      soil.setAttribute("normal", new Float32BufferAttribute(normals, 3));
      for (const [name, i] of [
        ["earthPigment", 3],
        ["wetPigment", 4],
        ["rockPigment", 5],
      ] as const)
        soil.setAttribute(
          name,
          new Float32BufferAttribute(pigments[i] ?? [], 3),
        );
      soil.setIndex(soilIndices);
      const banks = new Mesh(soil, bankMaterial);
      banks.name = "riverbank";
      group.add(banks);
    }

    function addWater(): void {
      const surface = new BufferGeometry();
      surface.setAttribute("position", new Float32BufferAttribute(water, 3));
      surface.setAttribute("bed", new Float32BufferAttribute(bed, 1));
      surface.setAttribute("localFlow", new Float32BufferAttribute(flow, 2));
      for (const [name, i] of [
        ["deepPigment", 0],
        ["shallowPigment", 1],
        ["reflectedLight", 2],
      ] as const)
        surface.setAttribute(
          name,
          new Float32BufferAttribute(pigments[i] ?? [], 3),
        );
      surface.setIndex(waterIndices);
      const river = new Mesh(surface, waterMaterial);
      river.name = "river";
      group.add(river);
    }
  }

  // Shared column samples and normals keep the patches' joins invisible.
  for (let z = 0; z < zAxis.length - 1; z += 21)
    for (let x = 0; x < xAxis.length - 1; x += 33)
      addPatch(
        x,
        Math.min(xAxis.length - 1, x + 33),
        z,
        Math.min(zAxis.length - 1, z + 21),
      );

  const ridge = makeRidge(level, bankMaterial);
  if (ridge) group.add(ridge.mesh);
  return {
    group,
    height(x, z) {
      const i = cell(xAxis, x);
      const j = cell(zAxis, z);
      const u = clamp(
        (x - (xAxis[i] ?? x)) / ((xAxis[i + 1] ?? x + 1) - (xAxis[i] ?? x)),
      );
      const v = clamp(
        (z - (zAxis[j] ?? z)) / ((zAxis[j + 1] ?? z + 1) - (zAxis[j] ?? z)),
      );
      const b = sample(i + 1, j);
      const c = sample(i, j + 1);
      const ground =
        u + v <= 1
          ? (1 - u - v) * sample(i, j) + u * b + v * c
          : (u + v - 1) * sample(i + 1, j + 1) + (1 - v) * b + (1 - u) * c;
      return Math.max(ground, ridge?.height(x, z) ?? -Infinity);
    },
  };
}
