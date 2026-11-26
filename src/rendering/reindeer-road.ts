import {
  BufferGeometry,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  Mesh,
  MeshLambertMaterial,
  type ColorRepresentation,
} from "three";
import { groundHeight, insideCulvert } from "../levels/reindeer-ground";
import { lerp, type Vec2 } from "../core/math";
import type { ReindeerLevel } from "../levels/schema";

type Point = readonly [x: number, y: number, z: number];
const SOLID = [1, 1, 1, 1] as const;
const SNOW = ["#d8e2e5", "#e7e8e2", "#c5d2dd"] as const;
const STONE = ["#a49481", "#b4a593", "#9f9991", "#c1af9b"] as const;
const ASPHALT_Y = 0.09;
const COPING_Y = 0.15;
const COPING_WIDTH = 0.43;

function grain(seed: number): number {
  const value = Math.sin(seed * 12.9898 + 23.41) * 43758.5453;
  return value - Math.floor(value);
}

function material(transparent = false): MeshLambertMaterial {
  return new MeshLambertMaterial({
    vertexColors: true,
    side: DoubleSide,
    transparent,
    depthWrite: !transparent,
    forceSinglePass: true,
  });
}

// These static surfaces share vertex paint so the road markings, stonework
// and repeated retaining-wall fittings can each be submitted with the bridge.
class RoadBatch {
  private readonly positions: number[] = [];
  private readonly colors: number[] = [];
  private readonly indices: number[] = [];

  quad(
    a: Point,
    b: Point,
    c: Point,
    d: Point,
    tone: ColorRepresentation,
    farTone: ColorRepresentation = tone,
    alpha: readonly [number, number, number, number] = SOLID,
  ): void {
    const base = this.positions.length / 3;
    this.positions.push(...a, ...b, ...c, ...d);
    const near = new Color(tone);
    const far = new Color(farTone);
    for (const [index, color] of [near, near, far, far].entries())
      this.colors.push(color.r, color.g, color.b, alpha[index] ?? 1);
    this.indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
  }

  triangle(
    a: Point,
    b: Point,
    c: Point,
    tone: ColorRepresentation,
    alpha: readonly [number, number, number],
  ): void {
    const base = this.positions.length / 3;
    this.positions.push(...a, ...b, ...c);
    const color = new Color(tone);
    for (const opacity of alpha)
      this.colors.push(color.r, color.g, color.b, opacity);
    this.indices.push(base, base + 1, base + 2);
  }

  surface(
    left: number,
    right: number,
    near: number,
    far: number,
    nearY: number,
    farY: number,
    color: ColorRepresentation,
    farColor: ColorRepresentation = color,
  ): void {
    this.quad(
      [right, nearY, near],
      [left, nearY, near],
      [left, farY, far],
      [right, farY, far],
      color,
      farColor,
    );
  }

  block(
    left: number,
    right: number,
    near: number,
    far: number,
    bottom: number,
    top: number,
    color: ColorRepresentation,
  ): void {
    const side = new Color(color).multiplyScalar(0.77);
    this.surface(left, right, near, far, top, top, color);
    for (const x of [left, right]) {
      this.quad(
        [x, bottom, near],
        [x, bottom, far],
        [x, top, far],
        [x, top, near],
        side,
        color,
      );
    }
    for (const z of [near, far]) {
      this.quad(
        [left, bottom, z],
        [right, bottom, z],
        [right, top, z],
        [left, top, z],
        side,
        color,
      );
    }
  }

  mesh(name: string, paint: MeshLambertMaterial): Mesh {
    const geometry = new BufferGeometry()
      .setAttribute("position", new Float32BufferAttribute(this.positions, 3))
      .setAttribute("color", new Float32BufferAttribute(this.colors, 4))
      .setIndex(this.indices);
    geometry.computeVertexNormals();
    const mesh = new Mesh(geometry, paint);
    mesh.name = name;
    return mesh;
  }
}

function pigmentPatch(
  batch: RoadBatch,
  center: Point,
  radiusX: number,
  radiusZ: number,
  tone: ColorRepresentation,
  opacity: number,
  seed: number,
): void {
  const [x, y, z] = center;
  const shape = Array.from({ length: 9 }, (_, index) => {
    const angle = (index / 9) * 2 * Math.PI;
    const edge = 0.76 + grain(seed + index) * 0.24;
    return [
      Math.cos(angle) * radiusX * edge,
      Math.sin(angle) * radiusZ * edge,
    ] as const;
  });
  for (let index = 0; index < shape.length; index++) {
    const a = shape[index];
    const b = shape[(index + 1) % shape.length];
    if (!a || !b) continue;
    const innerA: Point = [x + a[0] * 0.61, y, z + a[1] * 0.61];
    const innerB: Point = [x + b[0] * 0.61, y, z + b[1] * 0.61];
    batch.triangle(center, innerB, innerA, tone, [opacity, opacity, opacity]);
    batch.quad(
      innerB,
      innerA,
      [x + a[0], y, z + a[1]],
      [x + b[0], y, z + b[1]],
      tone,
      tone,
      [opacity, opacity, 0, 0],
    );
  }
}

function frostGrass(
  batch: RoadBatch,
  x: number,
  z: number,
  seed: number,
): void {
  for (let stem = 0; stem < 5; stem++) {
    const t = grain(seed + stem * 3);
    const angle = grain(seed + stem * 3 + 1) * 2 * Math.PI;
    const dx = Math.cos(angle);
    const dz = Math.sin(angle);
    const bend = 0.17 + 0.48 * t;
    batch.triangle(
      [x - dz * 0.083, 0.02, z + dx * 0.083],
      [x + dz * 0.083, 0.02, z - dx * 0.083],
      [x + dx * bend, 0.29 + 0.54 * t, z + dz * bend],
      stem % 2 === 0 ? "#9c8a68" : "#818c7c",
      [1, 1, 1],
    );
  }
}

function ploughedSnow(
  batch: RoadBatch,
  x: number,
  length: number,
  edge: number,
  direction: -1 | 1,
  seed: number,
): void {
  const rows = Array.from({ length: 8 }, (_, index) => {
    const t = index / 7;
    const taper = Math.sin(t * Math.PI) ** 0.82;
    const along = x + (t - 0.5) * length;
    const distance = 2.1 + 0.5 * Math.sin(seed + t * 5);
    const span = taper * (0.78 + grain(seed + index) * 0.48);
    const base = 0.027;
    const z = edge + direction * distance;
    return {
      lip: [along, base, z - direction * span] as Point,
      crown: [along, base + taper * 0.29, z] as Point,
      toe: [along, base, z + direction * span * 1.2] as Point,
      opacity: taper ** 0.42 * 0.84,
    };
  });
  for (let index = 1; index < rows.length; index++) {
    const a = rows[index - 1];
    const b = rows[index];
    if (!a || !b) continue;
    batch.quad(a.lip, a.crown, b.crown, b.lip, "#b8c8d6", "#c6d2d9", [
      0,
      a.opacity,
      b.opacity,
      0,
    ]);
    batch.quad(a.toe, a.crown, b.crown, b.toe, "#edf0ed", "#e3ebe8", [
      0,
      a.opacity,
      b.opacity,
      0,
    ]);
  }
}

function verge(
  wash: RoadBatch,
  detail: RoadBatch,
  level: ReindeerLevel,
  edge: number,
  direction: -1 | 1,
): void {
  const { bounds, road } = level;
  const { culvert } = road;
  for (const [start, end] of [
    [bounds.min.x, culvert.left],
    [culvert.right, bounds.max.x],
  ] as const) {
    // Fade ploughed snow into the ground while leaving the vehicle lane sharp.
    const length = end - start;
    const count = Math.ceil(length / 9);
    for (let index = 0; index < count; index++) {
      const seed = index * 47 + start + edge;
      const x = start + ((index + 0.3 + grain(seed) * 0.4) * length) / count;
      const depth = 3.6 + 4.2 * grain(seed + 1);
      pigmentPatch(
        wash,
        [x, 0.019, edge + direction * depth],
        Math.min(6.8 + 3 * grain(seed + 2), x - start, end - x),
        depth - 0.8,
        SNOW[index % SNOW.length] ?? SNOW[0],
        0.64 + 0.24 * grain(seed + 3),
        seed,
      );
      const fromPortal = Math.min(
        Math.abs(x - culvert.left),
        Math.abs(x - culvert.right),
      );
      if (fromPortal < 36 && grain(seed + 7) > 0.34)
        ploughedSnow(
          wash,
          x,
          Math.min(9 + 4 * grain(seed + 8), 2 * (x - start), 2 * (end - x)),
          edge,
          direction,
          seed,
        );
      if (grain(seed + 4) > 0.51) {
        const z = edge + direction * (depth + 0.9);
        pigmentPatch(wash, [x, 0.023, z], 2.1, 1.7, "#919e9d", 0.25, seed);
        for (let tuft = 0; tuft < 4; tuft++)
          frostGrass(
            detail,
            x + grain(seed + tuft) * 2.5 - 1.25,
            z + grain(seed + tuft + 4) * 1.45 - 0.7,
            seed + tuft * 19,
          );
      }
    }
  }
}

function shoulderDrift(
  batch: RoadBatch,
  start: Vec2,
  end: Vec2,
  side: number,
  width: number,
): void {
  const rows = Array.from({ length: 9 }, (_, index) => {
    const t = index / 8;
    const taper = Math.sin(Math.PI * t) ** 0.72;
    const x = lerp(start.x, end.x, t) + side * 1.17 * taper;
    const z = lerp(start.z, end.z, t);
    const span = width * taper;
    return {
      crest: [x, 0.029 + taper * 0.13, z] as Point,
      near: [x - span * 0.78, 0.028, z] as Point,
      far: [x + span, 0.028, z] as Point,
      opacity: taper ** 0.32 * 0.92,
    };
  });

  for (let index = 1; index < rows.length; index++) {
    const a = rows[index - 1];
    const b = rows[index];
    if (!a || !b) continue;
    for (const edge of ["near", "far"] as const)
      batch.quad(a[edge], a.crest, b.crest, b[edge], "#e2e7e8", "#e6e7e0", [
        0,
        a.opacity,
        b.opacity,
        0,
      ]);
  }
}

function approach(
  wash: RoadBatch,
  detail: RoadBatch,
  level: ReindeerLevel,
  shoulderId: string,
  mouth: number,
  direction: -1 | 1,
): void {
  const shoulder = level.zones.find(({ id }) => id === shoulderId);
  if (!shoulder) return;
  const { left, right } = level.road.culvert;
  const mid = (left + right) / 2;
  const width = (right - left) / 2;
  const zLow = Math.min(...shoulder.points.map(({ z }) => z));
  const zHigh = Math.max(...shoulder.points.map(({ z }) => z));
  const xLow = Math.min(...shoulder.points.map(({ x }) => x));
  const xHigh = Math.max(...shoulder.points.map(({ x }) => x));
  const reach = direction < 0 ? mouth - zLow : zHigh - mouth;
  if (reach < 1) return;

  const clearing = level.landmarks.find(
    ({ id }) => id === (direction > 0 ? "culvert-exit" : "shoulder-sign"),
  )?.pos;
  const center = clearing ?? { x: mid, z: mouth + direction * reach * 0.67 };
  const gatheringWidth = width * (direction > 0 ? 1.9 : 1.38);
  const sections = [
    { z: mouth, left, right, opacity: 0.98, tone: "#c3b098" },
    {
      z: lerp(mouth, center.z, 0.7),
      left: Math.max(xLow, lerp(mid, center.x, 0.7) - gatheringWidth),
      right: Math.min(xHigh, lerp(mid, center.x, 0.7) + gatheringWidth),
      opacity: 0.88,
      tone: "#d6c5a9",
    },
    {
      z: mouth + direction * reach,
      left: Math.max(xLow, center.x - gatheringWidth * 0.87),
      right: Math.min(xHigh, center.x + gatheringWidth * 1.1),
      opacity: 0,
      tone: "#a79d87",
    },
  ].sort((a, b) => a.z - b.z);

  for (let i = 1; i < sections.length; i++) {
    const a = sections[i - 1];
    const b = sections[i];
    if (!a || !b) continue;
    for (const key of ["left", "right"] as const)
      wash.quad(
        [a[key], 0.025, a.z],
        [mid, 0.025, a.z],
        [mid, 0.025, b.z],
        [b[key], 0.025, b.z],
        a.tone,
        b.tone,
        [0, a.opacity, b.opacity, 0],
      );
  }

  // A crescent of melting snow and grit frames the far-side gathering pocket.
  // The materials meet at ground level so actors can cross the entire shoulder.
  for (const side of [-1, 1]) {
    const x = mid + side * gatheringWidth * 0.84;
    if (x < xLow + 1.6 || x > xHigh - 1.6) continue;
    const z = mouth + direction * reach * 0.95;
    shoulderDrift(
      wash,
      { x, z: mouth },
      { x: x - side * 0.85, z },
      side,
      Math.min(3.4, x - xLow - 1.35, xHigh - x - 1.35),
    );
    for (let tuft = 0; tuft < 5; tuft++) {
      const along = 0.19 + grain(mouth + side * 13 + tuft) * 0.66;
      frostGrass(
        detail,
        x + side * grain(z + tuft) * 1.75,
        lerp(mouth, z, along),
        z + side * 8 + tuft * 13,
      );
    }
  }
  if (direction === 1)
    pigmentPatch(
      wash,
      [center.x + width * 0.62, 0.026, center.z - 1.1],
      Math.max(0, Math.min(width * 1.4, xHigh - center.x - width * 0.62)),
      Math.min(3.7, zHigh - center.z + 1.1),
      "#dacaab",
      0.65,
      center.z,
    );
  for (let chip = 0; chip < (direction > 0 ? 36 : 18); chip++) {
    const seed = mouth + chip * 13;
    const side = chip % 2 ? -1 : 1;
    const x = center.x + side * width * (0.45 + 0.84 * grain(seed));
    const distance = reach * (0.13 + 0.71 * grain(seed + 2));
    const z = mouth + direction * distance;
    if (x <= xLow + 0.4 || x >= xHigh - 0.4) continue;
    const size = 0.09 + 0.24 * grain(seed + 3);
    wash.triangle(
      [x - size, 0.031, z],
      [x + size * 0.51, 0.031, z + size * 0.54],
      [x + size, 0.031, z - size * 0.31],
      STONE[chip % STONE.length] ?? STONE[0],
      [0.8, 0.61, 0.78],
    );
  }
}

function retainingWalls(batch: RoadBatch, level: ReindeerLevel): void {
  const { road } = level;
  const mid = (road.culvert.left + road.culvert.right) / 2;
  for (const wall of level.barriers) {
    if (wall.kind !== "culvert") continue;
    const left = Math.min(...wall.points.map(({ x }) => x));
    const right = Math.max(...wall.points.map(({ x }) => x));
    const near = Math.min(...wall.points.map(({ z }) => z));
    const far = Math.max(...wall.points.map(({ z }) => z));
    const inner = right <= mid ? right : left;
    const face = inner + (right <= mid ? 0.006 : -0.006);
    const points = [near, road.near, road.far, far];
    for (let section = 1; section < points.length; section++) {
      const start = points[section - 1];
      const end = points[section];
      if (start === undefined || end === undefined) continue;
      const steps = Math.ceil((end - start) / 2.3);
      for (let i = 0; i < steps; i++) {
        const z0 = lerp(start, end, i / steps);
        const z1 = lerp(start, end, (i + 1) / steps);
        const y0 = groundHeight(road, { x: mid, z: z0 });
        const y1 = groundHeight(road, { x: mid, z: z1 });
        batch.quad(
          [inner, y0 - 0.06, z0],
          [inner, y1 - 0.06, z1],
          [inner, 0.16, z1],
          [inner, 0.16, z0],
          "#575f62",
          "#9a8d7d",
        );
        for (let course = 0; course < 3; course++) {
          const low = course / 3;
          const high = (course + 1) / 3;
          const joint = 0.045 + ((i + course) % 3) * 0.06;
          const tone = STONE[(course + i + section) % STONE.length] ?? STONE[0];
          batch.quad(
            [face, lerp(y0, 0.15, low) + 0.025, z0 + joint],
            [face, lerp(y1, 0.15, low) + 0.025, z1 - 0.035],
            [face, lerp(y1, 0.15, high), z1 - 0.035],
            [face, lerp(y0, 0.15, high), z0 + joint],
            new Color(tone).multiplyScalar(0.66 + course * 0.08),
            tone,
          );
        }
        const cap = grain(z0 + left) > 0.55 ? "#efebdd" : "#c2b39e";
        batch.block(left, right, z0 + 0.027, z1 - 0.027, 0.15, 0.26, cap);
      }
    }
    // The higher stone pilasters sit only on the existing wall footprints.
    for (const z of [road.near, road.far]) {
      batch.block(left, right, z - 0.68, z + 0.68, -0.07, 0.89, "#a99882");
      batch.block(left, right, z - 0.62, z + 0.62, 0.89, 1.05, "#dfd6c4");
      batch.block(
        left + 0.08,
        right - 0.08,
        z - 0.49,
        z + 0.4,
        1.05,
        1.13,
        "#eeebdf",
      );
    }
    for (const z of [near, far - 1.18]) {
      batch.block(left, right, z, z + 1.18, -0.06, 0.53, "#b4a491");
      batch.block(left, right, z + 0.07, z + 1.11, 0.53, 0.62, "#e3ded1");
    }
  }
}

function portal(batch: RoadBatch, level: ReindeerLevel): void {
  const { road } = level;
  const { left, right, depth } = road.culvert;
  const arch = (t: number) => -depth * (0.12 + 0.24 * (2 * t - 1) ** 2);
  const thickness = Math.min(0.58, (road.far - road.near) * 0.12);
  for (const [edge, direction] of [
    [road.near, -1],
    [road.far, 1],
  ] as const) {
    // The reveals recede into the bridge footprint above the original arch
    // envelope, so the raised stonework leaves the crossing clearance intact.
    const throat = edge - direction * thickness;
    const count = 13;
    for (let index = 0; index < count; index++) {
      const from = index / count;
      const to = (index + 1) / count;
      const x0 = lerp(left, right, from);
      const x1 = lerp(left, right, to);
      const y0 = arch(from);
      const y1 = arch(to);
      batch.quad(
        [x1, y1, throat],
        [x0, y0, throat],
        [x0, y0, edge],
        [x1, y1, edge],
        "#514f4a",
        "#817b70",
      );
      batch.quad(
        [x0, y0, edge],
        [x1, y1, edge],
        [x1, ASPHALT_Y, edge],
        [x0, ASPHALT_Y, edge],
        "#615b54",
        "#817c74",
      );

      const middle = index === Math.floor(count / 2);
      const inset = Math.min(0.034, (x1 - x0) * 0.08);
      const ringHeight = Math.min(depth * 0.145, 0.24 + grain(index) * 0.1);
      const low0 = lerp(y0, y1, inset / (x1 - x0)) + 0.019;
      const low1 = lerp(y1, y0, inset / (x1 - x0)) + 0.019;
      const high = (y: number) =>
        Math.min(ASPHALT_Y - 0.022, y + ringHeight + (middle ? 0.09 : 0));
      const tone = middle
        ? "#d2bda0"
        : (STONE[index % STONE.length] ?? STONE[0]);
      const face = edge - direction * 0.009;
      // Leave dark joints between the voussoirs and a shaded bevel under the rim.
      batch.quad(
        [x0 + inset, low0 + 0.04, face],
        [x1 - inset, low1 + 0.04, face],
        [x1 - inset, high(low1), face],
        [x0 + inset, high(low0), face],
        new Color(tone).multiplyScalar(0.8),
        tone,
      );
      batch.quad(
        [x0 + inset, low0, edge],
        [x1 - inset, low1, edge],
        [x1 - inset, low1 + 0.04, face],
        [x0 + inset, low0 + 0.04, face],
        "#746b60",
        tone,
      );
    }
  }
}

function deckCoping(batch: RoadBatch, level: ReindeerLevel): void {
  const { near, far, culvert } = level.road;
  const count = 13;
  for (const z of [near, far - COPING_WIDTH]) {
    // The thin opaque curb shows exactly where the elevated lane ends even
    // when the deck has faded to surface the herd below.
    batch.block(
      culvert.left,
      culvert.right,
      z,
      z + COPING_WIDTH,
      ASPHALT_Y - 0.035,
      COPING_Y - 0.022,
      "#77776e",
    );
    for (let index = 0; index < count; index++)
      batch.surface(
        lerp(culvert.left, culvert.right, index / count) + 0.023,
        lerp(culvert.left, culvert.right, (index + 1) / count) - 0.023,
        z + 0.036,
        z + COPING_WIDTH - 0.037,
        COPING_Y,
        COPING_Y,
        index % 3 === 1 ? "#b6afa1" : "#d7cdb9",
        "#9f9a8e",
      );
  }
}

function roadwayWear(
  batch: RoadBatch,
  left: number,
  right: number,
  near: number,
  far: number,
): void {
  const width = far - near;
  for (let index = 0; index < 13; index++) {
    const seed = left * 3 + index * 17;
    const run = (right - left) / 13;
    const x = left + run * (index + 0.25);
    const end = Math.min(right - 0.04, x + run * (0.76 + grain(seed) * 1.06));
    const z = near + width * (index % 2 === 0 ? 0.27 : 0.73);
    const shift = (grain(seed + 3) - 0.5) * width * 0.13;
    const size = width * (0.022 + grain(seed + 9) * 0.023);
    // Subdued, broken aggregate marks establish the scale of the top surface.
    batch.quad(
      [x, ASPHALT_Y + 0.003, z + shift],
      [x + (end - x) * 0.28, ASPHALT_Y + 0.003, z + shift - size],
      [end, ASPHALT_Y + 0.003, z + shift + size * 0.37],
      [x + (end - x) * 0.46, ASPHALT_Y + 0.003, z + shift + size],
      index % 3 === 0 ? "#59646a" : "#505b62",
      "#566169",
    );
  }
}

function passage(batch: RoadBatch, level: ReindeerLevel): void {
  const { road } = level;
  const { left, right, near, far } = road.culvert;
  const mid = (left + right) / 2;
  const verge = Math.min(1.04, (right - left) * 0.12);
  const positions = [
    { z: near, tread: "#d3c5ae", damp: "#9da39a" },
    { z: lerp(near, road.near, 0.48), tread: "#c8b59b", damp: "#9b9b8b" },
    { z: lerp(near, road.near, 0.83), tread: "#a2937a", damp: "#7a827b" },
    { z: road.near, tread: "#857962", damp: "#626b66" },
    { z: lerp(road.near, road.far, 0.18), tread: "#7b705c", damp: "#555f5a" },
    { z: lerp(road.near, road.far, 0.82), tread: "#80735d", damp: "#59605a" },
    { z: road.far, tread: "#8f8066", damp: "#687067" },
    { z: lerp(road.far, far, 0.24), tread: "#aa997e", damp: "#7f887d" },
    { z: lerp(road.far, far, 0.61), tread: "#c6b58f", damp: "#969b84" },
    { z: far, tread: "#d4c6af", damp: "#a2a69a" },
  ];
  for (let index = 1; index < positions.length; index++) {
    const a = positions[index - 1];
    const b = positions[index];
    if (!a || !b) continue;
    const y0 = groundHeight(road, { x: mid, z: a.z });
    const y1 = groundHeight(road, { x: mid, z: b.z });
    batch.surface(
      left + verge,
      right - verge,
      a.z,
      b.z,
      y0,
      y1,
      a.tread,
      b.tread,
    );
    batch.surface(left, left + verge, a.z, b.z, y0, y1, a.damp, b.damp);
    batch.surface(right - verge, right, a.z, b.z, y0, y1, a.damp, b.damp);
  }
}

export class ReindeerRoad {
  readonly group = new Group();
  private readonly roof = material(true);

  constructor(private readonly level: ReindeerLevel) {
    this.group.name = "R1 road and culvert";
    const { road, bounds } = level;
    const { near, far, culvert } = road;
    const lane = new RoadBatch();
    const deck = new RoadBatch();
    const ground = new RoadBatch();
    const edging = new RoadBatch();
    const structure = new RoadBatch();
    const shoulders = new RoadBatch();

    const center = (near + far) / 2;
    const bands = [
      [0, "#505e65"],
      [0.12, "#586268"],
      [0.31, "#4c565d"],
      [0.5, "#656a6b"],
      [0.7, "#535d63"],
      [0.88, "#5e676c"],
      [1, "#505e65"],
    ] as const;
    for (const [batch, left, right] of [
      [lane, bounds.min.x, culvert.left],
      [deck, culvert.left, culvert.right],
      [lane, culvert.right, bounds.max.x],
    ] as const) {
      for (let i = 1; i < bands.length; i++) {
        const a = bands[i - 1];
        const b = bands[i];
        if (!a || !b) continue;
        batch.surface(
          left,
          right,
          lerp(near, far, a[0]),
          lerp(near, far, b[0]),
          ASPHALT_Y,
          ASPHALT_Y,
          a[1],
          b[1],
        );
      }
      roadwayWear(batch, left, right, near, far);
      for (const z of [near + COPING_WIDTH + 0.12, far - COPING_WIDTH - 0.12]) {
        // Keep the roadway continuous in projection even through the cutaway.
        edging.surface(
          left,
          right,
          z - 0.088,
          z + 0.088,
          0.108,
          0.108,
          "#e4d8ba",
        );
      }
      for (let x = bounds.min.x + 2; x < bounds.max.x - 1; x += 7) {
        if (x >= right || x + 3.6 <= left) continue;
        batch.surface(
          Math.max(x, left),
          Math.min(x + 3.6, right),
          center - 0.078,
          center + 0.078,
          0.104,
          0.104,
          "#ece1c3",
        );
      }
    }
    for (const [start, stop] of [
      [bounds.min.x, culvert.left],
      [culvert.right, bounds.max.x],
    ] as const) {
      ground.surface(
        start,
        stop,
        near - 1.68,
        near - 0.012,
        0.012,
        0.012,
        "#a5aaa2",
        "#9a9283",
      );
      ground.surface(
        start,
        stop,
        far + 0.012,
        far + 1.68,
        0.012,
        0.012,
        "#a19889",
        "#b2b5ab",
      );
    }

    deckCoping(edging, level);
    passage(ground, level);
    retainingWalls(structure, level);
    portal(structure, level);
    verge(shoulders, structure, level, near, -1);
    verge(shoulders, structure, level, far, 1);
    approach(shoulders, structure, level, "near-shoulder", culvert.near, -1);
    approach(shoulders, structure, level, "far-shoulder", culvert.far, 1);

    const paint = material();
    const bridge = deck.mesh("Road deck cutaway", this.roof);
    bridge.renderOrder = 2;
    this.group.add(
      lane.mesh("Vehicle roadway", paint),
      bridge,
      edging.mesh("Road edge lines", paint),
      structure.mesh("Culvert masonry", paint),
      ground.mesh("Culvert ramps and road verges", paint),
      shoulders.mesh("Safe shoulder pigment", material(true)),
    );
    this.reset();
  }

  reset(): void {
    this.roof.opacity = 0.81;
  }

  update(
    actors: readonly { readonly pos: Vec2 }[],
    delta: number,
    reduced: boolean,
  ): void {
    const { road } = this.level;
    const beneath = actors.some(
      ({ pos }) =>
        pos.z >= road.near - 3 &&
        pos.z <= road.far + 3 &&
        insideCulvert(road, pos),
    );
    const opacity = beneath ? 0.12 : 0.81;
    this.roof.opacity +=
      (opacity - this.roof.opacity) * (reduced ? 1 : 1 - Math.exp(-15 * delta));
  }
}
