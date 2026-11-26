import {
  Box3,
  BufferGeometry,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  Quaternion,
  Vector3,
} from "three";
import { clamp, lerp, type Vec2 } from "../core/math";
import type { ReindeerLevel } from "../levels/schema";

interface Wash {
  readonly center: Vec2;
  readonly width: number;
  readonly length: number;
  readonly angle: number;
  readonly pigment: string;
  readonly opacity: number;
}

interface Plant {
  readonly pos: Vec2;
  readonly y: number;
  readonly radius: number;
  readonly height: number;
  readonly seed: number;
  readonly pigment: string;
}

interface MeshData {
  readonly positions: number[];
  readonly colors: number[];
  readonly indices: number[];
}

interface SeasonMaterials {
  readonly relief: MeshLambertMaterial;
  readonly softRelief: MeshLambertMaterial;
  readonly wash: MeshBasicMaterial;
}

const BAND_LENGTH = 32;
const TUFT_PALETTE = ["#778762", "#a19764", "#748e7e", "#9f9a70"] as const;
const FIR_PALETTE = ["#c5d4cf", "#abbdbb", "#d8ddcf"] as const;
const TAU = 2 * Math.PI;

function seed(n: number): number {
  const value = Math.sin(127.1 * n + 17.3) * 43758.5453;
  return value - Math.floor(value);
}

function extent(points: readonly Vec2[]) {
  return {
    minX: Math.min(...points.map(({ x }) => x)),
    maxX: Math.max(...points.map(({ x }) => x)),
    minZ: Math.min(...points.map(({ z }) => z)),
    maxZ: Math.max(...points.map(({ z }) => z)),
  };
}

function triangleStrip(data: MeshData, offset: number, columns: number): void {
  for (let i = 0; i < columns - 1; i++) {
    const a = offset + i;
    const b = a + columns;
    data.indices.push(a, b, a + 1, a + 1, b, b + 1);
  }
}

function makeGeometry(data: MeshData, rgba = false): BufferGeometry {
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(data.positions, 3))
    .setAttribute(
      "color",
      new Float32BufferAttribute(data.colors, rgba ? 4 : 3),
    )
    .setIndex(data.indices);
  if (!rgba) geometry.computeVertexNormals();
  return geometry;
}

function rowsFor<T>(
  items: readonly T[],
  locate: (value: T) => Vec2,
  splitAcross = false,
): Iterable<T[]> {
  const buckets = new Map<string, T[]>();
  for (const item of items) {
    const { x, z } = locate(item);
    const row = Math.floor(z / BAND_LENGTH);
    const column = splitAcross ? Math.floor((x + 24) / 48) : 0;
    const key = `${column},${row}`;
    let bucket = buckets.get(key);
    if (!bucket) buckets.set(key, (bucket = []));
    bucket.push(item);
  }
  return buckets.values();
}

function paintWash(
  parent: Group,
  name: string,
  material: MeshBasicMaterial,
  washes: readonly Wash[],
): void {
  const sides = 12;
  const columns = sides + 1;
  const rings = [
    [0, 0.93],
    [0.52, 1],
    [0.79, 0.56],
    [1, 0],
  ] as const;
  const color = new Color();
  for (const row of rowsFor(washes, ({ center }) => center)) {
    const data: MeshData = { positions: [], colors: [], indices: [] };
    for (const patch of row) {
      const { center, angle, pigment, width, length, opacity } = patch;
      const start = data.positions.length / 3;
      const sin = Math.sin(angle);
      const cos = Math.cos(angle);
      color.set(pigment);
      for (const [ring, [radius, strength]] of rings.entries()) {
        for (let i = 0; i <= sides; i++) {
          const a = TAU * (i / sides);
          const p = seed((i % sides) * 23 + center.x * 7 + center.z * 3);
          const shape = radius * (0.87 + p * 0.2);
          const x = Math.cos(a) * shape * width;
          const z = Math.sin(a) * shape * length;
          data.positions.push(
            center.x + x * cos + z * sin,
            0.009,
            center.z - x * sin + z * cos,
          );
          const value = 0.94 + 0.06 * p;
          data.colors.push(
            color.r * value,
            color.g * value,
            color.b * value,
            opacity * strength,
          );
        }
        if (ring) triangleStrip(data, start + (ring - 1) * columns, columns);
      }
    }
    const mesh = new Mesh(makeGeometry(data, true), material);
    mesh.name = name;
    // The washes precede hoofprints and route cues that share the ground.
    mesh.renderOrder = -5;
    parent.add(mesh);
  }
}

function canopyShadows(
  parent: Group,
  material: MeshBasicMaterial,
  plants: readonly Plant[],
): void {
  const profile = [
    [0, 0.16, 0],
    [0.12, 0.26, 0.65],
    [0.27, 1, 1],
    [0.35, 0.52, 0.91],
    [0.47, 0.86, 0.83],
    [0.55, 0.36, 0.71],
    [0.66, 0.59, 0.62],
    [0.76, 0.24, 0.49],
    [0.85, 0.31, 0.36],
    [1, 0.03, 0],
  ] as const;
  const feather = [
    [-1, 0],
    [-0.58, 0.78],
    [0, 1],
    [0.59, 0.75],
    [1, 0],
  ] as const;
  const color = new Color("#687890");
  const data: MeshData = { positions: [], colors: [], indices: [] };
  // Paint the projected shape of each visible crown into the snow. The
  // low branches can frame the path without taking away sight of the herd.
  for (const { pos, seed: phase, radius, height, y } of plants) {
    const reach = Math.min(28, (height + y) * 2.4);
    const crown = radius * (1.15 + seed(phase + 3) * 0.4);
    const lean = 0.57 + seed(phase + 41) * 0.12;
    const shade = 0.2 + seed(phase + 2) * 0.13;
    const first = data.positions.length / 3;
    for (const [row, [t, width, ink]] of profile.entries()) {
      for (const [cross, soft] of feather) {
        const offset = cross * crown * width;
        data.positions.push(
          pos.x - lean * t * reach + offset * 0.72,
          0.013,
          pos.z + 0.81 * t * reach + offset * 0.58,
        );
        data.colors.push(color.r, color.g, color.b, shade * ink * soft);
      }
      if (row)
        triangleStrip(data, first + (row - 1) * feather.length, feather.length);
    }
  }
  const shadow = new Mesh(makeGeometry(data, true), material);
  shadow.name = "Winter canopy shadows";
  shadow.renderOrder = -3;
  parent.add(shadow);
}

function firGeometry(): BufferGeometry {
  const data: MeshData = { positions: [], colors: [], indices: [] };
  const sides = 10;
  const swatch = new Color();
  const color = new Color();
  const trunk = [
    [0, 0.085, "#594b49"],
    [0.12, 0.064, "#7b6455"],
    [0.34, 0.042, "#66564e"],
    [0.66, 0.021, "#66564e"],
    [0.96, 0.009, "#52615a"],
  ] as const;
  for (const [row, [y, radius, pigment]] of trunk.entries()) {
    swatch.set(pigment);
    for (let i = 0; i <= sides; i++) {
      const angle = TAU * (i / sides);
      data.positions.push(
        Math.cos(angle) * radius + y * y * 0.105,
        y,
        Math.sin(angle) * radius,
      );
      color
        .copy(swatch)
        .multiplyScalar(0.69 + seed((i % sides) * 19) * 0.36)
        .toArray(data.colors, data.colors.length);
    }
    if (row) triangleStrip(data, (row - 1) * (sides + 1), sides + 1);
  }

  const whorls = [
    [0.31, 0.98, 0.17, 0.05],
    [0.48, 0.8, 0.17, 0.33],
    [0.63, 0.62, 0.16, 0.51],
    [0.76, 0.44, 0.13, 0.88],
    [0.86, 0.28, 0.14, 1.03],
  ] as const;
  const profile = [
    [0.05, 0.04, "#455950"],
    [0.53, 0.09, "#51695d"],
    [0.95, 0, "#61796a"],
    [0.82, 0.11, "#8ea798"],
    [0.51, 0.48, "#d7ddd1"],
    [0.24, 0.76, "#aebeb3"],
    [0.018, 1, "#84998c"],
  ] as const;
  for (const [tier, [base, width, rise, twist]] of whorls.entries()) {
    const first = data.positions.length / 3;
    for (const [row, [radius, height, pigment]] of profile.entries()) {
      swatch.set(pigment);
      for (let i = 0; i <= sides; i++) {
        const spoke = i % sides;
        const asymmetry = seed(tier * 37 + spoke * 13 + 15);
        const needle = spoke % 2 ? 0.14 : -0.08;
        const reach = radius * width * (0.78 + 0.3 * asymmetry + needle);
        const angle = TAU * (i / sides) + twist + needle * radius;
        const y = base + rise * height + (asymmetry - 0.5) * 0.12 * radius;
        data.positions.push(
          Math.cos(angle) * reach + y * y * 0.105,
          y,
          Math.sin(angle) * reach * 0.86 + y * 0.045,
        );
        color
          .copy(swatch)
          .multiplyScalar(0.74 + 0.34 * asymmetry)
          .toArray(data.colors, data.colors.length);
      }
      if (row) triangleStrip(data, first + (row - 1) * (sides + 1), sides + 1);
    }
  }
  return makeGeometry(data);
}

function winterBrushGeometry(reeds: boolean): BufferGeometry {
  const data: MeshData = { positions: [], colors: [], indices: [] };
  const base = new Color(reeds ? "#807769" : "#566a62");
  const tip = new Color(reeds ? "#ccc0a5" : "#b8c6b6");
  const color = new Color();
  const profile = [
    [0, 0, 0.022],
    [0.16, 0.42, 0.036],
    [0.52, 0.77, 0.027],
    [1, 1, 0],
  ] as const;
  const stems = reeds ? 7 : 11;
  for (let stem = 0; stem < stems; stem++) {
    const angle =
      (stem / stems - 0.5) * (reeds ? 1.6 : 3.8) + seed(stem * 3) * 0.38;
    const x = Math.cos(angle);
    const z = Math.sin(angle);
    const height = (reeds ? 0.51 : 0.38) + seed(stem * 7 + 9) * 0.48;
    const reach = 0.24 + seed(stem * 11 + 19) * (reeds ? 0.55 : 0.74);
    const offset = (seed(stem * 15 + 92) - 0.5) * 0.88;
    const first = data.positions.length / 3;
    for (const [row, [radius, y, width]] of profile.entries()) {
      color.copy(base).lerp(tip, y * (0.49 + seed(stem * 13) * 0.42));
      const breadth = width * (reeds ? 1 : 2.2);
      for (const side of [-1, 1]) {
        data.positions.push(
          (radius * reach + offset * 0.36) * x + side * breadth * z,
          y * height,
          (radius * reach + offset * 0.36) * z - (side * breadth + offset) * x,
        );
        color.toArray(data.colors, data.colors.length);
      }
      if (row) triangleStrip(data, first + (row - 1) * 2, 2);
    }
    if (!reeds) {
      const turn = stem % 2 ? 1 : -1;
      const twig = data.positions.length / 3;
      const groundX = offset * 0.36 * x;
      const groundZ = offset * (0.36 * z - x);
      const fork = reach * 0.43;
      const overhang = 0.14 + seed(stem * 5 + 6) * 0.11;
      data.positions.push(
        groundX + fork * x,
        height * 0.67,
        groundZ + fork * z,
        groundX + (fork + 0.09) * x + turn * z * overhang,
        height * 0.83,
        groundZ + (fork + 0.09) * z - turn * x * overhang,
        groundX + (fork + 0.22) * x + turn * z * overhang * 0.78,
        height * 0.91,
        groundZ + (fork + 0.22) * z - turn * x * overhang * 0.78,
      );
      base.toArray(data.colors, data.colors.length);
      color.copy(base).lerp(tip, 0.72).toArray(data.colors, data.colors.length);
      tip.toArray(data.colors, data.colors.length);
      data.indices.push(twig, twig + 1, twig + 2);
    }
  }
  return makeGeometry(data);
}

function placePlants(
  parent: Group,
  name: string,
  geometry: BufferGeometry,
  material: MeshLambertMaterial,
  plants: readonly Plant[],
  tallCanopies?: Box3[],
): void {
  const matrix = new Matrix4();
  const axis = new Vector3(0, 1, 0);
  const position = new Vector3();
  const rotation = new Quaternion();
  const scale = new Vector3();
  const tint = new Color();
  if (tallCanopies) geometry.computeBoundingBox();
  for (const row of rowsFor(plants, ({ pos }) => pos, true)) {
    const mesh = new InstancedMesh(geometry, material, row.length);
    mesh.name = name;
    for (const [
      i,
      { pos, y, radius, height, seed: phase, pigment },
    ] of row.entries()) {
      matrix.compose(
        position.set(pos.x, y, pos.z),
        rotation.setFromAxisAngle(axis, seed(phase) * TAU),
        scale.set(radius, height, radius * (0.84 + seed(phase + 4) * 0.34)),
      );
      mesh.setMatrixAt(i, matrix);
      mesh.setColorAt(i, tint.set(pigment));
      if (tallCanopies && height >= 20 && geometry.boundingBox)
        tallCanopies.push(geometry.boundingBox.clone().applyMatrix4(matrix));
    }
    mesh.computeBoundingSphere();
    parent.add(mesh);
  }
}

function bankHeight(u: number, v: number, phase: number): number {
  const shoulder = (Math.sin(Math.PI * u) * Math.sin(Math.PI * v)) ** 0.65;
  const swell = Math.sin(u * 11 + v * 5 + phase) * 0.45;
  const scarp = 0.48 * Math.exp(-((v - 0.4 - 0.1 * Math.sin(u * 9)) ** 2) * 38);
  return 0.023 + shoulder * (1.22 + swell + scarp);
}

function snowbank(
  points: readonly Vec2[],
  phase: number,
  shelterSide: boolean,
  material: MeshLambertMaterial,
): { readonly snow: Mesh; readonly trees: Plant[] } {
  const { minX, minZ, maxX, maxZ } = extent(points);
  const data: MeshData = { positions: [], colors: [], indices: [] };
  const toe = new Color("#e5e8ed");
  const shadow = new Color("#98a8c1");
  const pale = new Color("#f6f5f0");
  const color = new Color();
  const width = maxX - minX;
  const length = maxZ - minZ;
  const columns = 15;
  const rows = 13;
  for (let row = 0; row < rows; row++) {
    const v = row / (rows - 1);
    for (let col = 0; col < columns; col++) {
      const u = col / (columns - 1);
      const y = bankHeight(u, v, phase);
      data.positions.push(lerp(minX, maxX, u), y, lerp(minZ, maxZ, v));
      const light = clamp(
        0.44 + (u - v) * 0.48 + Math.sin(u * 15 + v * 11 + phase) * 0.21,
      );
      const toeDistance = Math.min(
        u * width,
        (1 - u) * width,
        v * length,
        (1 - v) * length,
      );
      color
        .copy(toe)
        .lerp(shadow, clamp(y * 0.42 * (1 - light)))
        .lerp(pale, clamp(y * 0.7 * light))
        .toArray(data.colors, data.colors.length);
      // Taper at the collision edge so the bank reads as a drift in the snow.
      const feather = clamp(
        toeDistance / (width < 8 || length < 8 ? 0.84 : 2.5),
      );
      data.colors.push(feather * feather * (3 - 2 * feather));
    }
    if (row) triangleStrip(data, (row - 1) * columns, columns);
  }
  const surface = makeGeometry(data, true);
  surface.computeVertexNormals();
  const snow = new Mesh(surface, material);
  snow.name = "Winter snowbank";
  snow.renderOrder = -4;

  const trees: Plant[] = [];
  const positions: readonly (readonly [number, number, number, number])[] =
    width > 8 && length > 8
      ? shelterSide
        ? [
            [0.18, 0.27, 1.6, 5.2],
            [0.46, 0.38, 2.35, 8.1],
            [0.77, 0.2, 2.3, 7.35],
            [0.79, 0.41, 2.6, 9.5],
            [0.64, 0.65, 2.4, 8.2],
            [0.47, 0.79, 1.9, 6.6],
            [0.25, 0.62, 1.5, 4.7],
            [0.84, 0.76, 1.5, 5.6],
          ]
        : [
            [0.34, 0.42, 1.1, 3.45],
            [0.43, 0.48, 1.65, 4.9],
            [0.72, 0.71, 2.0, 6.25],
            [0.82, 0.77, 1.45, 4.15],
          ]
      : width > 8
        ? [
            [0.27, 0.5, 0.89, 2.7],
            [0.39, 0.54, 0.53, 1.62],
            [0.69, 0.58, 0.65, 1.95],
          ]
        : [[0.5, 0.55, 0.52, 1.65]];
  for (const [index, [u, v, radius, height]] of positions.entries()) {
    trees.push({
      pos: { x: lerp(minX, maxX, u), z: lerp(minZ, maxZ, v) },
      y: bankHeight(u, v, phase) - 0.085,
      radius,
      height,
      seed: phase + index * 31,
      pigment: FIR_PALETTE[index % FIR_PALETTE.length] ?? FIR_PALETTE[0],
    });
  }
  return { snow, trees };
}

function winter(
  level: ReindeerLevel,
  group: Group,
  detail: Group,
  materials: SeasonMaterials,
  tallCanopies: Box3[],
): void {
  const { bounds, spawn } = level;
  const woodlandEnd = level.segments.find(({ id }) => id === "R1")?.start ?? 91;
  const shade = level.zones.find(({ id }) => id === "winter-pines");
  const open = level.landmarks.find(({ id }) => id === "winter-right")?.pos;
  const washes: Wash[] = [];
  const firs: Plant[] = [];
  const willow: Plant[] = [];
  const needles: Plant[] = [];
  const rearCopses = [
    [-41, 14, 5.8, 31],
    [-34, 8, 6.1, 32],
    [-27, 4, 6, 29],
    [-21, 8, 4.8, 29],
    [-15, 1.75, 4.05, 27],
    [17, 2.8, 4.8, 27],
    [23, 4.7, 4.4, 29],
    [30, 3.15, 6.35, 31],
    [36, 8, 5.2, 34],
    [46, 10, 5.7, 28],
  ] as const;
  for (const [index, [x, retreat, radius, height]] of rearCopses.entries()) {
    firs.push({
      pos: { x: spawn.x + x, z: bounds.min.z - retreat },
      y: -0.03,
      radius,
      height,
      seed: index * 19 + 31,
      pigment: FIR_PALETTE[index % FIR_PALETTE.length] ?? FIR_PALETTE[0],
    });
  }

  if (shade && open) {
    const range = extent(shade.points);
    const edge = range.minX;
    const left = edge + (range.maxX - edge) * 0.35;
    const length = range.maxZ - range.minZ;
    const right = open.x + 5;
    // The shade follows the safe side of the existing fork. Receding edges
    // and bare ground mark the inner path while the existing tracks stay clear.
    washes.push(
      {
        center: { x: left - 4, z: range.minZ - 8 },
        width: 9,
        length: 11,
        angle: -0.39,
        pigment: "#778d9f",
        opacity: 0.24,
      },
      {
        center: { x: left - 1.4, z: range.minZ + length * 0.12 },
        width: 14,
        length: 16,
        angle: 0.18,
        pigment: "#8197a2",
        opacity: 0.35,
      },
      {
        center: { x: left - 3, z: range.minZ + length * 0.58 },
        width: 12,
        length: 21,
        angle: 0.27,
        pigment: "#6e8493",
        opacity: 0.37,
      },
      {
        center: { x: right, z: open.z - 8 },
        width: 12,
        length: 22,
        angle: -0.17,
        pigment: "#f6e7cf",
        opacity: 0.57,
      },
      {
        center: { x: right + 5, z: open.z + 10 },
        width: 17,
        length: 24,
        angle: 0.21,
        pigment: "#f3e9d8",
        opacity: 0.47,
      },
    );
  }

  const pockets = [
    [-34, -12, 5, 6, 12],
    [-25, -3, 7, 5, 10],
    [-31, 14, 8, 5, 12],
    [-24, 25, 4, 6, 8],
    [-30, 36, 8, 8, 11],
    [-28, 50, 4, 8, 9],
    [-26, 69, 5, 8, 10],
    [27, -10, 9, 7, 11],
    [29, 9, 6, 4, 7],
    [23, 22, 5, 4, 6],
    [31, 36, 9, 5, 7],
    [31, 52, 11, 6, 6],
    [48, 70, 8, 6, 8],
  ] as const;
  for (const [index, [x, z, width, length, count]] of pockets.entries()) {
    const center = { x: spawn.x + x, z: spawn.z + z - 12 };
    const isWillow = x < 0;
    const phase = index * 53;
    washes.push({
      center,
      width: width * 1.57,
      length: length * 1.39,
      angle: isWillow ? -0.43 : 0.35,
      pigment: isWillow ? "#a1afb6" : "#dfd7cb",
      opacity: isWillow ? 0.31 : 0.32,
    });
    // Broad clumps sit between the tree layers and smaller brush. They
    // stay low so the open ground still reads as walkable from the saddle.
    const clumps = isWillow ? 3 : index % 2 === 0 ? 2 : 1;
    for (let clump = 0; clump < clumps; clump++) {
      const p = phase + clump * 21;
      willow.push({
        pos: {
          x: center.x + (seed(p + 64) - 0.5) * width,
          z: center.z + (seed(p + 72) - 0.5) * length,
        },
        y: 0.005,
        radius: 1.6 + seed(p + 83) * (isWillow ? 2.1 : 0.77),
        height: 0.6 + seed(p + 16) * 0.56,
        seed: p,
        pigment: isWillow ? "#a9bbb4" : "#bdc6b8",
      });
    }
    for (let stem = 0; stem < count; stem++) {
      const p = phase + stem * 13;
      (isWillow ? willow : needles).push({
        pos: {
          x: center.x + (seed(p + 3) - 0.5) * width * 1.8,
          z: center.z + (seed(p + 7) - 0.5) * length * 1.7,
        },
        y: 0.006,
        radius: 0.65 + seed(p + 31) * (isWillow ? 0.93 : 0.58),
        height: 0.22 + seed(p + 27) * (isWillow ? 0.87 : 0.4),
        seed: p,
        pigment: isWillow ? "#bcc8bb" : "#d1c4ac",
      });
    }
  }

  // Pale crests sit at ground level. They add wind direction without
  // turning either of the walkable verges into apparent obstacles.
  for (let i = 0; i < 15; i++) {
    const phase = i * 31;
    const side = i % 3 === 0 ? -1 : 1;
    const z = lerp(bounds.min.z + 7, woodlandEnd - 12, (i % 8) / 7);
    const x = side * (19 + seed(phase + 17) * 27);
    washes.push({
      center: { x, z },
      width: 10 + seed(phase + 3) * 7,
      length: 1.15 + seed(phase + 9) * 2.1,
      angle: -0.42 + seed(phase + 8) * 0.57,
      pigment: i % 4 === 0 ? "#bfc9d5" : "#f6f0e5",
      opacity: 0.4 + seed(phase + 12) * 0.24,
    });

    const edge = side < 0 ? bounds.min.x : bounds.max.x;
    firs.push({
      pos: {
        x: edge + side * (3.8 + seed(phase + 36) * 9),
        z: z + 7 * seed(phase + 11),
      },
      y: -0.035,
      radius: 2.1 + seed(phase + 6) * 2.0,
      height: 4.2 + seed(phase + 22) * 6.6,
      seed: phase,
      pigment: FIR_PALETTE[i % FIR_PALETTE.length] ?? FIR_PALETTE[0],
    });
  }
  washes.push({
    center: { x: spawn.x, z: spawn.z + 9 },
    width: 14,
    length: 19,
    angle: -0.17,
    pigment: "#f2dfc8",
    opacity: 0.47,
  });

  for (const [i, barrier] of level.barriers.entries()) {
    if (barrier.kind !== "slope" || !barrier.id.startsWith("snowbank-"))
      continue;
    const { snow, trees } = snowbank(
      barrier.points,
      i * 29,
      barrier.id === "snowbank-west",
      materials.softRelief,
    );
    group.add(snow);
    firs.push(...trees);
  }
  paintWash(group, "Winter snow and shelter wash", materials.wash, washes);
  canopyShadows(group, materials.wash, firs);
  const fir = firGeometry();
  placePlants(
    group,
    "Winter spruce stands",
    fir,
    materials.relief,
    firs,
    tallCanopies,
  );
  placePlants(
    group,
    "Frosted willow",
    winterBrushGeometry(false),
    materials.relief,
    willow,
  );
  placePlants(
    detail,
    "Drift grasses",
    winterBrushGeometry(true),
    materials.relief,
    needles,
  );
}

function peripheralRidges(
  level: ReindeerLevel,
  start: number,
  material: MeshLambertMaterial,
): Group {
  const { min, max } = level.bounds;
  const group = new Group();
  group.name = "Spring valley backdrop";
  const nearData: MeshData = { positions: [], colors: [], indices: [] };
  const farData: MeshData = { positions: [], colors: [], indices: [] };
  const grass = new Color("#a8af8c");
  const stone = new Color("#747f91");
  const snow = new Color("#e5e2da");
  const haze = new Color("#a7a6ba");
  const color = new Color();
  const columns = 42;
  const rows = 20;

  // Those hills belong beyond the simulation boundary. The near toes fade
  // into the painted ground and the far shoulder is a separately drawn layer.
  for (const side of [0, -1, 1, 2]) {
    const distant = side === 2;
    const endRidge = distant || side === 0;
    const data = distant ? farData : nearData;
    const first = data.positions.length / 3;
    for (let row = 0; row < rows; row++) {
      const depth = row / (rows - 1);
      for (let col = 0; col < columns; col++) {
        const along = col / (columns - 1);
        const fold = along * 18 + side * 1.8;
        const spur = Math.sin(fold * 0.73) + Math.sin(fold * 1.53 + 1.2) * 0.32;
        const length = endRidge ? (distant ? 34 : 25) : 41;
        const reach = length * depth;
        const x = endRidge
          ? lerp(min.x - 40, max.x + 40, along)
          : (side < 0 ? min.x : max.x) + side * (0.05 + reach);
        const z = endRidge
          ? max.z + (distant ? 15 : 0.05) + reach
          : lerp(start - 11, max.z - 0.1, along);
        const crest = 0.47 + spur * 0.13;
        const profile =
          Math.sin(Math.PI * clamp(depth / crest) * 0.5) *
          (1 - clamp((depth - crest) / (1 - crest)) ** 1.35);
        const massif =
          0.53 + 0.18 * spur + 0.105 * Math.sin(fold * 2.15 + depth * 9);
        const entry = endRidge ? 1 : clamp(along * 5);
        const height =
          profile *
          Math.max(0.2, massif) *
          entry *
          (distant ? 14 : endRidge ? 10.5 : 12);
        const y = depth === 0 ? -0.015 : height - 0.015;
        const slope = Math.sin(fold * 1.65 - depth * 7);
        const snowline = clamp((profile + 0.28 * slope - 0.77) * 2.4);
        data.positions.push(x, y, z);
        color
          .copy(distant ? haze : grass)
          .lerp(
            stone,
            clamp(profile * 0.82 + slope * 0.09) * (distant ? 0.53 : 1),
          )
          .lerp(snow, snowline * (distant ? 0.53 : 0.68))
          .multiplyScalar(0.91 + 0.1 * slope)
          .toArray(data.colors, data.colors.length);
        const toe = 0.032 + Math.max(0, spur) * 0.026;
        data.colors.push(
          clamp((depth - toe) * 12) *
            clamp((1 - depth) * 8) *
            entry *
            (distant ? 0.8 : 1),
        );
      }
      if (row) triangleStrip(data, first + (row - 1) * columns, columns);
    }
  }
  for (const [name, data, order] of [
    ["Tundra far ridge", farData, -7],
    ["Tundra peripheral ridges", nearData, -6],
  ] as const) {
    const geometry = makeGeometry(data, true);
    geometry.computeVertexNormals();
    const ridge = new Mesh(geometry, material);
    ridge.name = name;
    ridge.renderOrder = order;
    group.add(ridge);
  }
  return group;
}

interface Pool {
  readonly near: number;
  readonly far: number;
  readonly mouth: number;
  readonly tip: number;
  readonly width: number;
  readonly curve: number;
  readonly leftLimit: number;
  readonly rightLimit: number;
}

function waterline(pool: Pool, t: number, phase: number) {
  const taper = Math.min(1, t * 7, (1 - t) * 6);
  const turn = Math.sin(t * Math.PI) * pool.curve;
  const x =
    lerp(pool.mouth, pool.tip, t) +
    turn +
    taper * Math.sin(t * 10 + phase) * 1.04;
  const z = lerp(pool.near, pool.far, t);
  const width = taper * pool.width;
  return {
    x,
    z,
    left: Math.min(
      (x - pool.leftLimit) / 1.17,
      width *
        (0.59 + 0.19 * Math.sin(t * 12 + phase) + 0.07 * Math.sin(t * 26)),
    ),
    right: Math.min(
      (pool.rightLimit - x) / 1.17,
      width *
        (0.81 + 0.19 * Math.cos(t * 15 - phase) + 0.05 * Math.sin(t * 32)),
    ),
  };
}

function shoreX(section: ReturnType<typeof waterline>, across: number): number {
  return section.x + across * (across < 0 ? section.left : section.right);
}

function meltwater(
  group: Group,
  material: MeshBasicMaterial,
  pools: readonly Pool[],
  plants: Plant[],
): void {
  const data: MeshData = { positions: [], colors: [], indices: [] };
  const bands = [
    [-1.17, "#908b69", 0],
    [-1, "#a49d7b", 0.86],
    [-0.89, "#958770", 0.95],
    [-0.71, "#aeb7a0", 1],
    [-0.51, "#879d9a", 1],
    [-0.24, "#7f9b9e", 1],
    [0.08, "#70939c", 1],
    [0.32, "#8ba8a6", 1],
    [0.65, "#9cafa0", 1],
    [0.83, "#a6a78a", 1],
    [0.94, "#93886f", 0.88],
    [1.04, "#aaa581", 0.73],
    [1.17, "#908b69", 0],
  ] as const;
  const pigments = bands.map(([, color]) => new Color(color));
  const reedShadow = new Color("#767e6f");
  const skyGlint = new Color("#dbe1c8");
  const color = new Color();

  for (const [poolIndex, pool] of pools.entries()) {
    const phase = poolIndex * 2.16 + 0.7;
    const first = data.positions.length / 3;
    const rows = Math.max(2, Math.ceil((pool.far - pool.near) * 1.7));
    for (let row = 0; row < rows; row++) {
      const t = row / (rows - 1);
      const section = waterline(pool, t, phase);
      for (const [i, [edge, , opacity]] of bands.entries()) {
        const settled = Math.sin(t * 6.2 + edge * 1.9 + phase);
        const stain = Math.sin(t * 18 + edge * 3.5) ** 2;
        data.positions.push(shoreX(section, edge), 0.018, section.z);
        color
          .copy(pigments[i] ?? skyGlint)
          .lerp(reedShadow, 0.16 * stain * Math.abs(edge))
          .lerp(
            skyGlint,
            Math.max(0, settled) * (1 - Math.abs(edge) / 1.17) * 0.21,
          )
          .toArray(data.colors, data.colors.length);
        data.colors.push(opacity * Math.min(1, t * 26, (1 - t) * 26));
      }
      if (row)
        triangleStrip(data, first + (row - 1) * bands.length, bands.length);
    }

    // Small irregular inflections read as reflected light on a single water
    // mass. Variable lengths and spacing keep them from forming a striped fill.
    for (let i = 0; i < (poolIndex === 0 ? 17 : 9); i++) {
      const p = i * 113 + poolIndex * 29;
      const t = 0.12 + seed(p + 25) * 0.75;
      const section = waterline(pool, t, phase);
      const center = (seed(p + 7) - 0.46) * 0.95;
      const reach = 0.07 + 0.18 * seed(p + 4);
      const thickness = 0.07 + 0.09 * seed(p + 29);
      const first = data.positions.length / 3;
      const highlight = i % 5 !== 0;
      color.copy(highlight ? skyGlint : reedShadow);
      for (const [along, opacity] of [
        [-1, 0],
        [-0.56, 0.7],
        [0.26, 1],
        [1, 0],
      ] as const) {
        const x = shoreX(section, center + along * reach);
        const z = section.z + along * 0.16 + Math.sin(along * 2 + p) * 0.13;
        for (const edge of [-1, 1]) {
          data.positions.push(x, 0.021, z + edge * thickness);
          color.toArray(data.colors, data.colors.length);
          data.colors.push(opacity * (highlight ? 0.73 : 0.38));
        }
      }
      for (let row = 0; row < 3; row++) triangleStrip(data, first + row * 2, 2);
    }

    // Shallow stones mark the shoals, sized by the local pool width so they
    // stay within the authored shore even on the small satellite pool.
    for (let i = 0; i < 13; i++) {
      const p = i * 37 + poolIndex * 163;
      const side = i % 5 < 3 ? -1 : 1;
      const t = 0.24 + seed(p + 7) * 0.52;
      const section = waterline(pool, t, phase);
      const x = shoreX(section, side * (0.69 + seed(p + 16) * 0.25));
      const bankWidth = side < 0 ? section.left : section.right;
      const radius = Math.min(bankWidth * 0.15, 0.18 + seed(p + 81) * 0.34);
      const first = data.positions.length / 3;
      data.positions.push(x, 0.024, section.z);
      color.set(i % 3 === 0 ? "#c8bf9b" : "#a4a28a");
      color.toArray(data.colors, data.colors.length);
      data.colors.push(0.84);
      for (let corner = 0; corner < 6; corner++) {
        const angle = (corner / 6) * TAU + p;
        const edge = 0.75 + seed(p + corner * 7) * 0.25;
        data.positions.push(
          x + Math.cos(angle) * radius * edge,
          0.021,
          section.z + Math.sin(angle) * radius * edge * 0.67,
        );
        reedShadow.toArray(data.colors, data.colors.length);
        data.colors.push(0.51);
        data.indices.push(
          first,
          first + corner + 1,
          first + ((corner + 1) % 6) + 1,
        );
      }
    }

    // Wet-ground plants follow irregular colonies with stretches of open bank.
    for (const [i, [t, side]] of (
      [
        [0.18, 1],
        [0.29, 1],
        [0.44, -1],
        [0.52, -1],
        [0.7, 1],
        [0.84, -1],
      ] as const
    ).entries()) {
      const p = i * 38 + poolIndex * 71;
      for (let shoot = 0; shoot < 9; shoot++) {
        const q = p + shoot * 13;
        const section = waterline(pool, t + (seed(q + 55) - 0.5) * 0.13, phase);
        const shoreline = shoreX(section, side * (0.82 + seed(q + 32) * 0.27));
        plants.push({
          pos: { x: shoreline + side * (seed(q + 22) * 0.75), z: section.z },
          y: 0.015,
          radius: 0.63 + seed(q + 33) * 0.72,
          height: 0.35 + seed(q + 28) * 0.44,
          seed: q,
          pigment: TUFT_PALETTE[shoot % TUFT_PALETTE.length] ?? TUFT_PALETTE[0],
        });
      }
    }
  }
  const mesh = new Mesh(makeGeometry(data, true), material);
  mesh.name = "Tundra meltwater and shore";
  mesh.renderOrder = -3;
  group.add(mesh);
}

function springSedges(): BufferGeometry {
  const data: MeshData = { positions: [], colors: [], indices: [] };
  const blade = [
    [0.08, 0, 0.028],
    [0.22, 0.44, 0.044],
    [0.43, 0.76, 0.044],
    [0.73, 0.89, 0.029],
    [1, 0.74, 0],
  ] as const;
  for (let shoot = 0; shoot < 9; shoot++) {
    const angle = shoot * 2.37 + seed(shoot + 16) * 0.47;
    const x = Math.cos(angle);
    const z = Math.sin(angle);
    const reach = 0.42 + seed(shoot + 19) * 0.51;
    const height = 0.65 + seed(shoot + 5) * 0.35;
    const first = data.positions.length / 3;
    for (const [row, [distance, y, width]] of blade.entries()) {
      const light = 0.63 + y * 0.54 + 0.12 * seed(shoot + 73);
      for (const side of [-1, 1]) {
        data.positions.push(
          x * distance * reach + side * z * width,
          y * height,
          z * distance * reach - side * x * width,
        );
        data.colors.push(
          light * (0.88 + y * 0.12),
          light,
          light * (0.74 + y * 0.12),
        );
      }
      if (row) triangleStrip(data, first + (row - 1) * 2, 2);
    }
  }
  return makeGeometry(data);
}

type SnowPatch = Omit<Wash, "pigment">;

function residualSnow(
  group: Group,
  material: MeshBasicMaterial,
  patches: readonly SnowPatch[],
): void {
  const core = new Color("#e8e7de");
  const edge = new Color("#b2bbaf");
  const color = new Color();
  const sides = 20;
  const rings = [
    [0, 0.96],
    [0.53, 1],
    [0.8, 0.95],
    [0.9, 0.74],
    [1, 0],
  ] as const;
  for (const batch of rowsFor(patches, ({ center }) => center)) {
    const data: MeshData = { positions: [], colors: [], indices: [] };
    for (const { center, width, length, angle, opacity } of batch) {
      const first = data.positions.length / 3;
      const cos = Math.cos(angle),
        sin = Math.sin(angle);
      for (const [ring, [radius, alpha]] of rings.entries()) {
        for (let step = 0; step <= sides; step++) {
          const a = (TAU * step) / sides;
          const p = seed(center.x * 7 + center.z + (step % sides) * 41);
          const edgeScale = 0.69 + 0.26 * p + Math.cos(a * 3 + center.z) * 0.16;
          const u = Math.cos(a) * radius * edgeScale * width;
          const v = Math.sin(a) * radius * edgeScale * length;
          data.positions.push(
            center.x + u * cos + v * sin,
            0.012 + (1 - radius) * 0.009,
            center.z - u * sin + v * cos,
          );
          color
            .copy(core)
            .lerp(edge, 0.08 * p + 0.66 * clamp((radius - 0.64) * 3));
          color.toArray(data.colors, data.colors.length);
          data.colors.push(alpha * opacity);
        }
        if (ring)
          triangleStrip(data, first + (ring - 1) * (sides + 1), sides + 1);
      }
    }
    const mesh = new Mesh(makeGeometry(data, true), material);
    mesh.name = "Tundra residual snow";
    mesh.renderOrder = -4;
    group.add(mesh);
  }
}

function tundra(
  level: ReindeerLevel,
  group: Group,
  detail: Group,
  materials: SeasonMaterials,
): void {
  const { max } = level.bounds;
  const start =
    level.segments.find(({ id }) => id === "R4")?.start ?? max.z - 75;
  const goal = level.zones.find(({ kind }) => kind === "goal");
  const center = goal ? extent(goal.points) : null;
  const landmark = level.landmarks.find(({ id }) => id === "tundra-sign")?.pos;
  const x = landmark?.x ?? (center ? (center.minX + center.maxX) * 0.5 : 0);
  const clearWidth = center ? (center.maxX - center.minX) * 0.21 : 18;
  const meet = landmark?.z ?? start + 42;
  const washes: Wash[] = [];
  const snow: SnowPatch[] = [];
  const understory: Plant[] = [];
  const sedges: Plant[] = [];

  washes.push({
    center: { x, z: meet + 7 },
    width: clearWidth + 2,
    length: 22,
    angle: -0.19,
    pigment: "#e1cda2",
    opacity: 0.45,
  });
  const thawTurn = level.landmarks.find(({ id }) => id === "thaw-turn")?.pos;
  if (center && thawTurn) {
    const rightOfTrail =
      Math.max(
        thawTurn.x,
        ...(
          level.trails.find(({ id }) => id === "trail-tundra")?.points ?? []
        ).map(({ x }) => x),
      ) + 3.8;
    meltwater(
      group,
      materials.wash,
      [
        {
          near: Math.max(start + 4, thawTurn.z - 12),
          far: center.minZ - 0.9,
          mouth: thawTurn.x + 24,
          tip: thawTurn.x + 10,
          width: 10.6,
          curve: 3.9,
          leftLimit: rightOfTrail,
          rightLimit: max.x - 2,
        },
        {
          near: thawTurn.z + 4,
          far: thawTurn.z + 14,
          mouth: thawTurn.x + 31,
          tip: thawTurn.x + 28,
          width: 3.8,
          curve: 1.2,
          leftLimit: thawTurn.x + 23,
          rightLimit: max.x - 2,
        },
        {
          near: center.minZ + 5,
          far: center.maxZ - 4,
          mouth: center.maxX + 12,
          tip: center.maxX + 9,
          width: 7.9,
          curve: -2.8,
          leftLimit: center.maxX + 1.7,
          rightLimit: max.x - 1,
        },
      ],
      sedges,
    );
  }

  for (const side of [-1, 1]) {
    for (let cluster = 0; cluster < 8; cluster++) {
      const phase = (side + 1) * 139 + cluster * 53;
      const z =
        lerp(start + 9, max.z - 9, cluster / 7) + (seed(phase + 3) - 0.5) * 9;
      const verge = clearWidth * (0.82 + seed(phase + 57) * 0.38) + 6;
      const spot = {
        x: x + side * (verge + seed(phase + 2) * 13),
        z,
      };
      const thaw = clamp((z - start) / 50);
      const width = 6.9 + seed(phase + 22) * 12;
      const length = 3.2 + seed(phase + 14) * 5.8;
      const angle = side * (0.42 + seed(phase + 23) * 0.53);
      washes.push({
        center: spot,
        width,
        length,
        angle,
        pigment: cluster % 3 === 0 ? "#b6a577" : "#819b81",
        opacity: 0.46 + seed(phase + 10) * 0.14,
      });
      if (cluster < 4 || cluster % 2 === 0) {
        const drift = {
          x: spot.x + side * (3.2 + seed(phase + 21) * 8),
          z: z - 3.2,
        };
        snow.push(
          {
            center: drift,
            width: width * (0.57 - thaw * 0.13),
            length: length * 0.67,
            angle,
            opacity: 0.77 - thaw * 0.19,
          },
          {
            center: { x: drift.x - side * (width * 0.36), z: drift.z + 3.1 },
            width: width * 0.27,
            length: length * 0.35,
            angle: angle - 0.32,
            opacity: 0.72 - thaw * 0.16,
          },
        );
      }
      for (let plant = 0; plant < 14; plant++) {
        const p = phase + plant * 23;
        const pos = {
          x: spot.x + (seed(p + 30) - 0.5) * width * 1.44,
          z: spot.z + (seed(p + 55) - 0.5) * length * 1.44,
        };
        const pale = plant % 4 === 0;
        const stronger = plant < 5;
        (stronger ? sedges : understory).push({
          pos,
          y: 0,
          radius: 0.42 + seed(p + 1) * (stronger ? 0.88 : 0.59),
          height: 0.18 + seed(p + 8) * (stronger ? 0.42 : 0.28),
          seed: p,
          pigment: pale ? "#a4986b" : "#758464",
        });
      }
    }
  }

  paintWash(group, "Spring snow and thaw wash", materials.wash, washes);
  residualSnow(group, materials.wash, snow);
  const sedgeGeometry = springSedges();
  placePlants(
    group,
    "Thaw bank sedges",
    sedgeGeometry,
    materials.relief,
    sedges,
  );
  placePlants(
    detail,
    "Tundra sedge and lichen",
    sedgeGeometry,
    materials.relief,
    understory,
  );
  group.add(peripheralRidges(level, start, materials.softRelief));
}

export class ReindeerSeason {
  readonly group = new Group();
  private readonly detail = new Group();
  private readonly tallCanopies: Box3[] = [];

  constructor(level: ReindeerLevel) {
    this.group.name = "Reindeer seasonal landscapes";
    this.detail.name = "Seasonal small plants";
    const materials = {
      relief: new MeshLambertMaterial({ vertexColors: true, side: DoubleSide }),
      softRelief: new MeshLambertMaterial({
        vertexColors: true,
        side: DoubleSide,
        transparent: true,
        forceSinglePass: true,
        depthWrite: false,
      }),
      wash: new MeshBasicMaterial({
        vertexColors: true,
        transparent: true,
        depthWrite: false,
        side: DoubleSide,
        forceSinglePass: true,
      }),
    };
    winter(level, this.group, this.detail, materials, this.tallCanopies);
    tundra(level, this.group, this.detail, materials);
    this.group.add(this.detail);
  }

  update(low: boolean): void {
    this.detail.visible = !low;
  }

  // The wide camera probes both the sightline and its lower edge. Using the
  // same transformed canopy bounds keeps low views from entering the grove.
  cameraHeight(x: number, z: number): number {
    let height = 0;
    for (const { min, max } of this.tallCanopies) {
      if (x >= min.x && x <= max.x && z >= min.z && z <= max.z)
        height = Math.max(height, max.y);
    }
    return height;
  }
}
