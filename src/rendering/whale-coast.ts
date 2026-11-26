import {
  BufferGeometry,
  CatmullRomCurve3,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Object3D,
  ShaderMaterial,
  Vector3,
} from "three";
import type { Vec2 } from "../core/math";
import type { WhaleLevel } from "../levels/schema";
import type { WhaleBayLight } from "./whale-ocean";
import { whaleWaterLight } from "./whale-water-light";

function surface(
  positions: number[],
  colors: number[],
  indices: number[],
): BufferGeometry {
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 3))
    .setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function connect(
  indices: number[],
  start: number,
  width: number,
  columns: number,
): void {
  for (let j = 0; j < columns; j++) {
    const a = start + j;
    const b = a + 1;
    indices.push(a, a + width, b, b, a + width, b + width);
  }
}

function stratum(slab: boolean): BufferGeometry {
  const profile: readonly (readonly [number, number, string])[] = slab
    ? [
        [0.78, -0.9, "#799599"],
        [1, -0.5, "#9faaa0"],
        [0.73, 0.52, "#dfd1b2"],
        [0.51, 0.81, "#c4c8a8"],
        [0.27, 0.91, "#b0ba9e"],
      ]
    : [
        [0.68, -0.9, "#7c8e8f"],
        [1, -0.37, "#aeb4a0"],
        [0.87, 0.15, "#8d9e97"],
        [0.53, 0.79, "#caceb7"],
        [0.33, 0.82, "#b2c3b0"],
      ];
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const sides = slab ? 13 : 8;
  for (const [ring, [radius, height, hue]] of profile.entries()) {
    for (let j = 0; j < sides; j++) {
      const t = (j / sides) * 2 * Math.PI;
      const broken =
        0.91 + 0.11 * Math.sin(t * 3 + 1.2) + 0.16 * Math.cos(t * 5);
      const x = Math.cos(t) * radius * broken + 0.1 * height;
      const z =
        Math.sin(t) * radius * broken + Math.sin(t * 2) * radius * 0.071;
      const y = height + Math.sin(t * 2 + 0.7) * radius * 0.18;
      positions.push(x, y, z);
      new Color(hue)
        .multiplyScalar(0.89 + 0.15 * broken)
        .toArray(colors, colors.length);
    }
    if (ring > 0) {
      for (let j = 0; j < sides; j++) {
        const a = (ring - 1) * sides + j;
        const b = (ring - 1) * sides + ((j + 1) % sides);
        indices.push(a, a + sides, b, b, a + sides, b + sides);
      }
    }
  }
  const top = positions.length / 3;
  positions.push(0.1, 0.94, 0);
  new Color("#c7c5a8").toArray(colors, colors.length);
  for (let j = 0; j < sides; j++)
    indices.push(top, top - sides + ((j + 1) % sides), top - sides + j);
  return surface(positions, colors, indices);
}

function stonePaint(
  viewDepth = { value: 0 },
  coastal = false,
): MeshStandardMaterial {
  const material = new MeshStandardMaterial({
    vertexColors: true,
    roughness: 1,
    side: DoubleSide,
  });
  material.onBeforeCompile = (shader) => {
    shader.uniforms.viewDive = viewDepth;
    shader.uniforms.coastal = { value: Number(coastal) };
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        "#include <common>\nvarying vec3 stone;\nvarying float stoneDistance;",
      )
      .replace(
        "#include <project_vertex>",
        `
        #include <project_vertex>
        vec4 stoneLocal = vec4(transformed, 1.0);
        #ifdef USE_INSTANCING
          stoneLocal = instanceMatrix * stoneLocal;
        #endif
        stone = (modelMatrix * stoneLocal).xyz;
        stoneDistance = -mvPosition.z;
      `,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>
        varying vec3 stone;
        varying float stoneDistance;
        uniform float viewDive;
        uniform float coastal;
        ${whaleWaterLight}`,
      )
      .replace(
        "#include <opaque_fragment>",
        `
        float layers = sin(stone.y * 3.1 + stone.x * 0.30 + stone.z * 0.23
                           + sin(stone.x * 0.71 - stone.z * 0.59) * 0.8);
        float stipple = sin(stone.x * 4.2 + stone.z * 1.2) * sin(stone.y * 4.5 - stone.z * 2.9);
        float ink = smoothstep(0.36, 0.92, layers) * (0.15 + 0.07 * stipple);
        outgoingLight *= 1.0 - ink;
        outgoingLight += smoothstep(0.49, 0.94, -layers) * (0.018 + 0.015 * stipple);
        if (coastal > 0.5) {
          // Preserve broad planes when the water glaze softens the surface texture.
          float up = transformNormalByInverseViewMatrix(normal, viewMatrix).y;
          float planes = smoothstep(0.16, 0.87, up);
          outgoingLight *= mix(vec3(0.73, 0.83, 0.89), vec3(1.14, 1.07, 0.95), planes);
          float fracture = sin(stone.y * 1.5 + stone.x * 0.14 + stone.z * 0.15 + layers * 0.35);
          outgoingLight *= 1.0 - 0.13 * smoothstep(0.48, 0.91, fracture) * (1.0 - 0.57 * planes);
        }
        outgoingLight = whaleThroughWater(outgoingLight, stone.y, stoneDistance, viewDive, 0.91);
        #include <opaque_fragment>
      `,
      );
  };
  return material;
}

export function reefRockInstances(
  count: number,
  slab = true,
  viewDepth?: { value: number },
): InstancedMesh<BufferGeometry, MeshStandardMaterial> {
  return new InstancedMesh(stratum(slab), stonePaint(viewDepth), count);
}

function bank(
  origin: Vec2,
  tangent: Vec2,
  inland: Vec2,
  length: number,
  height: number,
): BufferGeometry {
  const shelf = [
    [-18, -10.6, "#5c8e89"],
    [-7, -8.2, "#91aea1"],
    [-2.2, -7.7, "#b6b897"],
    [0, 0.35, "#c8bfa0"],
    [2.6, 1.15, "#e3d1ad"],
    [6, 3.1, "#869991"],
    [9, 5.5, "#afad97"],
    [11.8, 7.5, "#9a9d82"],
    [17, 9.2, "#75988c"],
    [27, 8.2, "#78948c"],
    [42, 6, "#73928f"],
  ] as const;
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const steps = Math.ceil(length / 3);
  for (let i = 0; i <= steps; i++) {
    const s = (i / steps) * length;
    const sway = 3.7 + 3.2 * Math.sin(s * 0.041) + 1.6 * Math.sin(s * 0.17);
    const caps = 0.57 + 0.49 * Math.sin((Math.PI * i) / steps);
    const rise =
      height *
      caps *
      (0.81 + 0.26 * Math.sin(s * 0.054 + 1.5) + 0.12 * Math.cos(s * 0.121));
    for (const [j, [distance, y, pigment]] of shelf.entries()) {
      const band =
        distance + sway + Math.sin(s * 0.41 + j * 1.29) * (j > 2 ? 0.83 : 1.9);
      // The outer shelf is always below the deepest whale, including its fins.
      const elevation =
        y < 0 ? y : y * rise + Math.sin(s * 0.27 + 1.8 * j) * Math.min(y, 0.7);
      positions.push(
        origin.x + s * tangent.x + band * inland.x,
        elevation,
        origin.z + s * tangent.z + band * inland.z,
      );
      new Color(pigment)
        .multiplyScalar(0.94 + 0.09 * Math.sin(s * 0.45 + j * 0.68))
        .toArray(colors, colors.length);
    }
    if (i > 0)
      connect(indices, (i - 1) * shelf.length, shelf.length, shelf.length - 1);
  }
  return surface(positions, colors, indices);
}

function rearShore(x: number, center: Vec2): number {
  const offset = x - center.x;
  const cove = Math.exp(-((offset / 10) ** 2));
  const abutments =
    Math.exp(-(((offset + 17) / 8) ** 2)) +
    Math.exp(-(((offset - 16) / 8) ** 2));
  return (
    center.z -
    13.7 +
    1.7 * Math.sin(offset * 0.076) +
    1.5 * Math.cos(offset * 0.135) +
    3 * abutments -
    6.7 * cove
  );
}

function headlandCenter(level: WhaleLevel): Vec2 {
  return { x: level.spawn.x + 2, z: level.bounds.min.z };
}

const SHORE_PROFILE = [
  [-53, 9.5, "#8c9c8e"],
  [-34, 12.8, "#96a38b"],
  [-21, 9.6, "#a4a78c"],
  [-13, 7.6, "#a5a58f"],
  [-7, 5.2, "#a09b82"],
  [-3.1, 2.9, "#d0b597"],
  [0, 0, "#ab9779"],
  [3.1, -5.7, "#78958c"],
  [6.3, -8.4, "#88aa98"],
  [13, -9.4, "#779c93"],
  [24, -11.08, "#66928d"],
] as const;
const SHORE_SEAM = SHORE_PROFILE[10];

function shoreSamples(level: WhaleLevel) {
  const left = level.bounds.min.x - 12;
  const right = level.bounds.max.x + 12;
  return { left, right, columns: Math.ceil((right - left) / 4.4) };
}

function shoreRow(
  center: Vec2,
  x: number,
  distance: number,
  row: number,
): number {
  const face = Math.sin((x - center.x) * 0.21 + row * 1.8);
  return (
    rearShore(x, center) +
    distance +
    face * Math.min(1.3, Math.abs(distance) * 0.12)
  );
}

export function bayHeadland(
  level: WhaleLevel,
  submerged: boolean,
): BufferGeometry {
  const center = headlandCenter(level);
  const { left, right, columns } = shoreSamples(level);
  // Both materials meet on the same submerged row.
  const join = 8;
  const width = submerged ? SHORE_PROFILE.length - join : join + 1;
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const palette = SHORE_PROFILE.map(([, , pigment]) => new Color(pigment));
  for (let i = 0; i <= columns; i++) {
    const x = MathUtils.lerp(left, right, i / columns);
    const offset = x - center.x;
    const prominence =
      0.73 +
      0.22 * Math.sin(offset * 0.087 + 1.2) +
      0.13 * Math.sin(offset * 0.195);
    for (const [j, [distance, height]] of SHORE_PROFILE.entries()) {
      if (submerged ? j < join : j > join) continue;
      const face = Math.sin(offset * 0.21 + j * 1.8);
      const z = shoreRow(center, x, distance, j);
      const y = height <= 0 ? height : height * (prominence + 0.075 * face);
      positions.push(x, y, z);
      palette[j]
        ?.clone()
        .multiplyScalar(0.9 + 0.17 * prominence + 0.06 * face)
        .toArray(colors, colors.length);
    }
    if (i > 0) connect(indices, (i - 1) * width, width, width - 1);
  }
  return surface(positions, colors, indices);
}

function arch(center: Vec2): BufferGeometry {
  const spine = new CatmullRomCurve3([
    new Vector3(-18.2, -1.8, -6.9),
    new Vector3(-14.8, 3.8, -2.65),
    new Vector3(-9.8, 8.6, -0.4),
    new Vector3(-2.1, 10.7, 0.55),
    new Vector3(6.5, 9.0, 0.36),
    new Vector3(12.3, 5, -1.6),
    new Vector3(16.4, -1.5, -6.4),
  ]);
  const shade = new Color("#526363");
  const face = new Color("#c8b394");
  const patina = new Color("#9a9e7c");
  const color = new Color();
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const sections = 28;
  const sides = 11;
  for (let i = 0; i <= sections; i++) {
    const fraction = i / sections;
    const p = spine.getPoint(fraction);
    const tangent = spine.getTangent(fraction);
    const radius =
      2.28 +
      2.72 * Math.cos(fraction * Math.PI) ** 4 +
      0.35 * Math.sin(i * 0.93) +
      0.38 * Math.sin(fraction * Math.PI * 2);
    for (let j = 0; j <= sides; j++) {
      const theta = ((j % sides) / sides) * 2 * Math.PI;
      const radiusAtAngle =
        radius * (0.89 + 0.13 * Math.sin(theta * 3 + i * 0.52)) +
        0.2 * Math.cos(theta * 5 - i * 0.35);
      const x = p.x - tangent.y * Math.cos(theta) * radiusAtAngle;
      const y = p.y + tangent.x * Math.cos(theta) * radiusAtAngle;
      const worldX = center.x + x;
      const z = Math.min(
        center.z - 0.9,
        center.z - 6.6 + p.z + Math.sin(theta) * radiusAtAngle * 0.93,
      );
      positions.push(worldX, y, z);
      const rim = MathUtils.smoothstep(Math.cos(theta), -0.54, 0.76);
      const bed =
        0.5 + 0.5 * Math.cos(y * 1.31 + x * 0.14 + 0.5 * Math.sin(x * 0.24));
      color
        .copy(shade)
        .lerp(face, 0.23 + 0.48 * rim + 0.21 * bed)
        .lerp(
          patina,
          rim *
            MathUtils.smoothstep(Math.sin(i * 0.57 + theta), 0.25, 1) *
            0.38,
        )
        .toArray(colors, colors.length);
    }
    if (i > 0) connect(indices, (i - 1) * (sides + 1), sides + 1, sides);
  }
  return surface(positions, colors, indices);
}

export function whaleCoast(level: WhaleLevel, light: WhaleBayLight): Group {
  const group = new Group();
  group.name = "Tidal headlands";
  const { min, max } = level.bounds;
  const industry = level.segments.find(({ id }) => id === "W1")?.start ?? 270;
  const junction = level.segments.find(({ id }) => id === "W3")?.start ?? 930;
  const banks = [
    bank(
      { x: max.x + 5, z: min.z - 29 },
      { x: 0, z: 1 },
      { x: 1, z: 0 },
      industry + 35,
      1.82,
    ),
    bank(
      { x: min.x - 5, z: min.z - 17 },
      { x: 0, z: 1 },
      { x: -1, z: 0 },
      industry + 110,
      1.11,
    ),
    bank(
      { x: max.x + 5, z: junction - 36 },
      { x: 0, z: 1 },
      { x: 1, z: 0 },
      325,
      1.15,
    ),
  ];
  // Cull each headland independently as the course moves away from the coast.
  const paint = stonePaint(light.depth, true);
  for (const geometry of banks) group.add(new Mesh(geometry, paint));
  const bay = new Group();
  bay.name = "W0 bay headland and reef";
  const center = headlandCenter(level);
  const headland = new Mesh(bayHeadland(level, false), paint);
  headland.name = "W0 headland";
  const seaArch = new Mesh(arch(center), paint);
  seaArch.name = "W0 sea arch";
  bay.add(
    headland,
    seaArch,
    bayShoreWash(center, min.x - 12, max.x + 12, light),
    bayReef(level, paint),
  );
  group.add(bay);
  return group;
}

// Signed offsets from the launch heading, sampled from the bay through the
// opening into the waiting water. The two shelves end at different points.
const BAY_CHANNEL = [
  [0, -22, 24],
  [0.16, -35, 29],
  [0.4, -45, 34],
  [0.61, -39, 35],
  [0.78, -34, 29],
  [0.94, -52, 46],
  [1.12, -99, 113],
  [1.3, -138, 150],
] as const;

function bayExit(level: WhaleLevel): number {
  return (
    level.segments.find(({ id }) => id === "W1")?.start ?? level.spawn.z + 270
  );
}

export function bayChannelBounds(
  level: WhaleLevel,
  z: number,
): Readonly<{ west: number; east: number }> {
  const progress =
    (z - level.spawn.z) / Math.max(1, bayExit(level) - level.spawn.z);
  let [lastZ, west, east]: [number, number, number] = [...BAY_CHANNEL[0]];
  for (const [nextZ, nextWest, nextEast] of BAY_CHANNEL) {
    if (progress <= nextZ && nextZ > lastZ) {
      const blend = MathUtils.smoothstep(progress, lastZ, nextZ);
      west = MathUtils.lerp(west, nextWest, blend);
      east = MathUtils.lerp(east, nextEast, blend);
      break;
    }
    [lastZ, west, east] = [nextZ, nextWest, nextEast];
  }
  return { west: west + level.spawn.x, east: east + level.spawn.x };
}

const APRON_BASE = -11.18;
const APRON_TOP = -7.94;

type BayRib = readonly [
  progress: number,
  run: number,
  shoulder: number,
  width: number,
  sweep: number,
  height: number,
];

// Unequal, overlapping ribs cut into the sand apron along each bank.
const WEST_RIBS: readonly BayRib[] = [
  [0.07, 0.22, 11, 13, 31, 1.27],
  [0.25, 0.21, 23, 16, -33, 0.87],
  [0.56, 0.22, 13, 18, 31, 1.12],
  [0.84, 0.14, 23, 15, -49, 0.83],
];
const EAST_RIBS: readonly BayRib[] = [
  [-0.03, 0.19, 13, 18, -27, 1.12],
  [0.17, 0.21, 25, 14, 49, 0.72],
  [0.42, 0.19, 12, 16, -29, 1.23],
  [0.64, 0.25, 19, 19, 31, 1.1],
  [0.91, 0.19, 15, 16, 28, 0.68],
];

function bayBedHeight(
  level: WhaleLevel,
  x: number,
  z: number,
  outerFade: number,
): number {
  const { west, east } = bayChannelBounds(level, z);
  const localZ = z - level.spawn.z;
  const side = x < (west + east) * 0.5 ? -1 : 1;
  const shoulder = Math.max(west - x, x - east);
  const rippled =
    shoulder +
    1.9 * Math.sin(localZ * 0.091 + side * 1.4) +
    0.86 * Math.sin(localZ * 0.23 - side);
  const slope = MathUtils.smoothstep(rippled, -10, 15);
  const shelf = MathUtils.smoothstep(rippled, 8, 26);
  const progress = localZ / Math.max(1, bayExit(level) - level.spawn.z);
  let relief = 0;
  for (const [center, run, edge, width, sweep, height] of side < 0
    ? WEST_RIBS
    : EAST_RIBS) {
    const offset = progress - center;
    const taper = 1 - MathUtils.smoothstep(Math.abs(offset), run * 0.17, run);
    const crease =
      edge + offset * sweep + 2.3 * Math.sin(localZ * 0.11 + center * 13);
    const flank = Math.abs(shoulder - crease) / (width * (0.61 + 0.39 * taper));
    const lip = 1 - MathUtils.smoothstep(flank, 0.25, 0.72);
    const footing = 1 - MathUtils.smoothstep(flank, 0.46, 1);
    relief = Math.max(relief, taper * (0.56 * lip + 0.44 * footing) * height);
  }
  const layers =
    1.22 * slope +
    1.48 * shelf +
    0.17 * slope * Math.sin(localZ * 0.29 + shoulder * 0.36) +
    relief;
  const rise =
    Math.max(0, layers) *
    MathUtils.smoothstep(localZ, -32, -7) *
    (1 - MathUtils.smoothstep(z, bayExit(level) - 43, bayExit(level) + 64));
  return Math.min(APRON_TOP, APRON_BASE + rise * outerFade);
}

export function bayTerraces(level: WhaleLevel): BufferGeometry {
  const center = headlandCenter(level);
  const { left, right, columns } = shoreSamples(level);
  const end = bayExit(level) + 64;
  const rows = Math.ceil((end - level.bounds.min.z) / 6.4);
  const positions: number[] = [];
  const indices: number[] = [];
  for (let row = 0; row <= rows; row++) {
    for (let col = 0; col <= columns; col++) {
      const x = MathUtils.lerp(left, right, col / columns);
      const seam = shoreRow(center, x, SHORE_SEAM[0], SHORE_PROFILE.length - 1);
      const z = MathUtils.lerp(seam, end, row / rows);
      const outerFade = MathUtils.smoothstep(
        Math.min(x - left, right - x),
        0,
        16,
      );
      const y =
        row === 0 ? SHORE_SEAM[1] : bayBedHeight(level, x, z, outerFade);
      positions.push(x, y, z);
    }
    if (row > 0)
      connect(indices, (row - 1) * (columns + 1), columns + 1, columns);
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function bayReef(
  level: WhaleLevel,
  paint: MeshStandardMaterial,
): InstancedMesh {
  const clusters = [
    [-1, 0.05, 13, 8.2, 4],
    [-1, 0.24, 18, 6.2, 3],
    [-1, 0.53, 14, 7.9, 4],
    [-1, 0.81, 23, 7.0, 3],
    [1, -0.04, 12, 7.7, 4],
    [1, 0.41, 13, 6.5, 3],
    [1, 0.61, 17, 9.0, 4],
    [1, 0.86, 18, 6.7, 3],
  ] as const;
  const count = clusters.reduce((total, entry) => total + entry[4], 0);
  const geometry = stratum(false);
  geometry.computeBoundingBox();
  const summit = geometry.boundingBox?.max.y ?? 1;
  const reef = new InstancedMesh(geometry, paint, count);
  reef.name = "W0 submerged ledges";
  const place = new Object3D();
  const shades = ["#a5b8a5", "#d5c5a1", "#8fa89c", "#b8b594"].map(
    (hue) => new Color(hue),
  );
  const length = Math.max(1, bayExit(level) - level.spawn.z);
  let instance = 0;
  for (const [side, progress, shoulder, size, stones] of clusters) {
    for (let i = 0; i < stones; i++) {
      const angle = i * 2.4 + progress * 19;
      const scatter = i === 0 ? 0 : size * (0.68 + 0.17 * i);
      const z = level.spawn.z + progress * length + Math.sin(angle) * scatter;
      const { west, east } = bayChannelBounds(level, z);
      const x =
        (side < 0 ? west : east) +
        side * (shoulder + Math.cos(angle) * scatter * 0.56);
      const span = size * (i === 0 ? 1 : 0.5 - 0.073 * i);
      const thickness = span * (0.16 + 0.026 * Math.sin(angle));
      place.position.set(
        x,
        Math.min(
          bayBedHeight(level, x, z, 1) - 0.16 * thickness,
          APRON_TOP - thickness * summit,
        ),
        z,
      );
      place.scale.set(span * (0.61 + 0.14 * Math.sin(angle)), thickness, span);
      place.rotation.y = side * (0.42 + 0.39 * Math.cos(angle));
      place.updateMatrix();
      reef.setMatrixAt(instance, place.matrix);
      reef.setColorAt(
        instance,
        shades[instance % shades.length] ?? new Color(),
      );
      instance++;
    }
  }
  return reef;
}

function bayShoreWash(
  center: Vec2,
  left: number,
  right: number,
  light: WhaleBayLight,
): Mesh {
  const positions: number[] = [];
  const weights: number[] = [];
  const indices: number[] = [];
  const steps = Math.ceil((right - left) / 2.5);
  for (let i = 0; i <= steps; i++) {
    const x = MathUtils.lerp(left, right, i / steps);
    const z = rearShore(x, center);
    const stroke = 0.12 + 0.53 * Math.max(0, Math.cos(x * 0.17 + 1.4)) ** 1.8;
    positions.push(
      x,
      0.038,
      z + 0.28,
      x,
      0.038,
      z + 0.45 + stroke,
      x,
      0.038,
      z + 1.6 + 1.3 * stroke,
    );
    weights.push(0, stroke, 0);
    if (i > 0) connect(indices, (i - 1) * 3, 3, 2);
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("strength", new Float32BufferAttribute(weights, 1))
    .setIndex(indices);
  const material = new ShaderMaterial({
    uniforms: { amount: light.amount, depth: light.depth },
    side: DoubleSide,
    transparent: true,
    depthWrite: false,
    vertexShader: `
      attribute float strength;
      varying float crest;
      void main() {
        crest = strength;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform float amount;
      uniform float depth;
      varying float crest;
      void main() {
        gl_FragColor = vec4(0.85, 0.92, 0.73, crest * amount * (1.0 - smoothstep(0.2, 1.7, depth)));
        #include <colorspace_fragment>
      }
    `,
  });
  const wash = new Mesh(geometry, material);
  wash.renderOrder = -5;
  return wash;
}

export function reefGrass(count: number): InstancedMesh {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  for (let blade = 0; blade < 6; blade++) {
    const angle = blade * 2.4;
    const turn = Math.sin(angle) * 0.7;
    const tip = 0.44 + 0.09 * (blade % 5);
    const i = positions.length / 3;
    const x = Math.cos(angle) * 0.22;
    const z = Math.sin(angle) * 0.22;
    positions.push(
      x - 0.055,
      0,
      z,
      x + 0.055,
      0,
      z,
      x + turn * 0.3 - 0.048,
      tip * 0.63,
      z + 0.11,
      x + turn * 0.3 + 0.048,
      tip * 0.63,
      z + 0.11,
      x + turn * 0.6,
      tip,
      z + 0.23,
    );
    indices.push(i, i + 1, i + 2, i + 2, i + 1, i + 3, i + 2, i + 3, i + 4);
    for (const color of ["#375850", "#335e53", "#5f9877", "#6da281", "#a1b186"])
      new Color(color).toArray(colors, colors.length);
  }
  return new InstancedMesh(
    surface(positions, colors, indices),
    new MeshBasicMaterial({ vertexColors: true, side: DoubleSide }),
    count,
  );
}
