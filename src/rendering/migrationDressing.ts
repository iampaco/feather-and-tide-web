import {
  BufferGeometry,
  Color,
  CylinderGeometry,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  IcosahedronGeometry,
  InstancedMesh,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  Object3D,
  OctahedronGeometry,
  Vector3,
} from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { clamp } from "../core/math";
import { crosses } from "../levels/geometry";
import type { LevelSchema } from "../levels/schema";
import { sampleWind } from "../levels/wind";
import { buildCrosswindBanks } from "./crosswindBanks";
import { buildReturnWind } from "./migrationGust";
import { reedFans, riverStone, sedgeFans } from "./migrationVegetation";

type Height = (x: number, z: number) => number;
type Bed = readonly [
  x: number,
  z: number,
  spreadX: number,
  spreadZ: number,
  reeds: number,
];
type Stamp = {
  x: number;
  y: number;
  z: number;
  yaw: number;
  width: number;
  height: number;
  depth: number;
  tint: Color;
};

const REED_BEDS: Record<string, readonly Bed[]> = {
  S0: [
    [-19, -10, 6, 13, 36],
    [-23, 7, 6, 10, 26],
    [22, 12, 6, 16, 29],
    [-19, 29, 7, 13, 52],
    [-24, 42, 6, 10, 24],
    [36, 33, 6, 13, 11],
    [22, 54, 5, 12, 46],
    [26, 66, 6, 13, 52],
    [-27, 69, 7, 16, 17],
    [44, 94, 7, 12, 11],
  ],
  S1: [
    [-41, 129, 13, 15, 17],
    [29, 156, 10, 25, 25],
    [-39, 182, 17, 14, 20],
    [-22, 205, 10, 18, 41],
    [41, 218, 16, 10, 16],
  ],
  S2: [
    [9, 222, 4, 7, 10],
    [-48, 236, 7, 11, 9],
    [36, 244, 10, 13, 10],
    [64, 253, 9, 18, 14],
    [96, 298, 7, 15, 26],
    [101, 324, 6, 16, 17],
    [101, 350, 10, 16, 31],
    [93, 372, 10, 15, 18],
  ],
  S3: [
    [-43, 404, 9, 18, 18],
    [-37, 427, 6, 15, 20],
    [41, 448, 9, 17, 35],
    [-65, 470, 8, 12, 23],
    [-67, 490, 9, 14, 33],
    [30, 487, 11, 15, 16],
  ],
  S4: [
    [-72, 547, 6, 14, 16],
    [-71, 568, 5, 10, 28],
    [-69, 583, 4, 13, 34],
    [-70, 605, 5, 12, 31],
    [-104, 557, 5, 12, 24],
    [-106, 589, 5, 16, 25],
    [-102, 619, 7, 12, 35],
    [-66, 643, 12, 18, 15],
    [56, 605, 10, 15, 14],
  ],
  S5: [
    [-46, 682, 13, 12, 17],
    [36, 696, 12, 15, 20],
    [-48, 721, 10, 20, 19],
    [30, 744, 10, 15, 16],
    [-38, 761, 13, 15, 21],
    [37, 772, 11, 12, 19],
  ],
  S6: [
    [-28, 790, 6, 9, 29],
    [-31, 801, 7, 13, 33],
    [-42, 821, 7, 14, 29],
    [-36, 839, 8, 16, 48],
    [-30, 858, 8, 12, 26],
    [28, 806, 6, 10, 26],
    [29, 820, 5, 13, 38],
    [45, 835, 7, 13, 27],
    [34, 852, 10, 13, 38],
    [20, 874, 9, 13, 37],
    [-13, 878, 10, 9, 27],
  ],
};

const openingShoreSedges: readonly Bed[] = [
  [-26, -1, 7, 14, 22],
  [24, 7, 5, 17, 17],
  [-29, 31, 8, 13, 23],
  [17, 49, 5, 13, 21],
  [32, 64, 7, 13, 22],
];

const STONE_BEDS: Record<string, readonly Bed[]> = {
  S0: [
    [-21, -5, 6, 10, 9],
    [21, 18, 4, 7, 5],
    [-23, 34, 4, 6, 8],
    [20, 54, 4, 6, 7],
  ],
  S1: [
    [26, 158, 6, 11, 6],
    [-27, 204, 5, 10, 7],
  ],
  S2: [
    [-56, 266, 7, 12, 13],
    [-58, 301, 6, 17, 12],
    [-54, 340, 8, 20, 16],
    [93, 358, 6, 10, 7],
  ],
  S3: [
    [-33, 427, 7, 12, 6],
    [38, 474, 9, 13, 7],
  ],
  S4: [
    [-73, 565, 4, 8, 7],
    [-68, 602, 3, 8, 7],
    [-102, 622, 5, 12, 5],
  ],
  S5: [
    [-46, 713, 9, 11, 6],
    [34, 744, 7, 9, 6],
  ],
  S6: [
    [-24, 796, 4, 7, 5],
    [-38, 824, 4, 8, 5],
    [38, 831, 6, 12, 9],
    [22, 868, 5, 9, 6],
  ],
};

const WIND_REACHES = [
  {
    name: "S3",
    x: -1,
    z: 444,
    spanX: 32,
    spanZ: 45,
    density: 24,
    length: 18,
    color: "#e8edce",
  },
  {
    name: "S5",
    x: -4,
    z: 712,
    spanX: 35,
    spanZ: 43,
    density: 26,
    length: 19,
    color: "#f3e1b9",
  },
] as const;

function seeded(seed: number): () => number {
  return () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
}

function placeBatch(
  parent: Group,
  geometry: BufferGeometry,
  material: MeshLambertMaterial,
  stamps: readonly Stamp[],
  name: string,
): void {
  const mesh = new InstancedMesh(geometry, material, stamps.length);
  mesh.name = name;
  const transform = new Object3D();
  for (const [i, stamp] of stamps.entries()) {
    transform.position.set(stamp.x, stamp.y, stamp.z);
    transform.rotation.set(0, stamp.yaw, 0);
    transform.scale.set(stamp.width, stamp.height, stamp.depth);
    transform.updateMatrix();
    mesh.setMatrixAt(i, transform.matrix);
    mesh.setColorAt(i, stamp.tint);
  }
  mesh.computeBoundingSphere();
  parent.add(mesh);
}

function scatterBed(
  bed: Bed,
  sampler: Height,
  random: () => number,
  accepted: readonly [number, number],
  tint: Color,
  plant: "reed" | "sedge" | "stone",
  low: boolean,
): Stamp[] {
  const [cx, cz, radiusX, radiusZ, count] = bed;
  const placements: Stamp[] = [];
  for (let i = 0; i < count; i++) {
    const angle = random() * Math.PI * 2;
    const radius = Math.pow(random(), 0.7);
    const x = cx + Math.cos(angle) * radius * radiusX;
    const z = cz + Math.sin(angle) * radius * radiusZ;
    const y = sampler(x, z);
    const orientation = random() * Math.PI * 2;
    const size = random();
    const color = tint.clone().lerp(new Color("#fff3d5"), random() * 0.25);
    if (y < accepted[0] || y > accepted[1]) continue;
    if (low && i % 3 === 2 && plant !== "stone") continue;

    const width =
      plant === "stone" ? 0.53 + size ** 2 * 1.75 : 0.75 + size * 0.67;
    const elevation =
      plant === "reed" ? 0.77 + size * 0.68 : 0.58 + size * 0.66;
    placements.push({
      x,
      y: y - 0.037,
      z,
      yaw: orientation,
      width,
      height: elevation,
      depth: width * (plant === "stone" ? 0.76 : 1),
      tint: color,
    });
  }
  return placements;
}

function bankUnderpainting(
  beds: readonly Bed[],
  height: Height,
  material: MeshBasicMaterial,
  tint: Color,
): Mesh {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const sides = 12;
  const rings = 3;
  // Low, ground-hugging washes join individual stems into a single reed bed.
  // Geometry samples the same bed as the plants and disappears under water.
  for (const [i, [x, z, width, depth, count]] of beds.entries()) {
    if (count < 15) continue;
    const random = seeded(11839 + i * 517 + Math.round(z) * 239);
    const offset = positions.length / 3;
    const leaf = tint.clone().lerp(new Color("#867743"), random() * 0.37);
    const phase = random() * Math.PI * 2;
    const centerHeight = height(x, z);
    positions.push(x, centerHeight + 0.018, z);
    colors.push(leaf.r, leaf.g, leaf.b, 0.3 * clamp(centerHeight * 4));
    for (let ring = 1; ring <= rings; ring++) {
      const t = ring / rings;
      for (let v = 0; v < sides; v++) {
        const angle = (v * Math.PI * 2) / sides;
        const edge =
          1 +
          0.22 * Math.sin(angle * 3 + phase) +
          0.09 * Math.cos(angle * 5 - phase);
        const px = x + Math.cos(angle) * width * t * edge;
        const pz = z + Math.sin(angle) * depth * t * edge;
        const y = height(px, pz);
        positions.push(px, y + 0.018, pz);
        const alpha = (1 - t ** 1.6) * (0.14 + 0.17 * random()) * clamp(y * 4);
        colors.push(leaf.r, leaf.g, leaf.b, alpha);
        const a = offset + 1 + (ring - 1) * sides + v;
        const b = offset + 1 + (ring - 1) * sides + ((v + 1) % sides);
        if (ring === 1) indices.push(offset, a, b);
        else indices.push(a - sides, b - sides, a, b - sides, b, a);
      }
    }
  }
  const geometry = new BufferGeometry()
    .setIndex(indices)
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 4));
  return new Mesh(geometry, material);
}

function paintBanks(
  group: Group,
  height: Height,
  low: boolean,
  level: LevelSchema,
): void {
  const ground = new MeshLambertMaterial({ vertexColors: true });
  const plant = new MeshLambertMaterial({
    vertexColors: true,
    side: DoubleSide,
  });
  const groundWash = new MeshBasicMaterial({
    vertexColors: true,
    side: DoubleSide,
    transparent: true,
    depthWrite: false,
    polygonOffset: true,
    polygonOffsetFactor: -1,
    polygonOffsetUnits: -1,
  });
  const coolReeds = reedFans(false);
  const warmReeds = reedFans(true);
  const sedges = sedgeFans();
  const stones = riverStone();

  for (const [index, [segment, beds]] of Object.entries(REED_BEDS).entries()) {
    const opening = segment === "S0";
    const tinted = index === 0 || index >= 5;
    const basin = segment === "S6";
    const section = new Group();
    section.name = `${segment}-ground-dressing`;
    const seed = 6817 + index * 3997;
    const reedColor = new Color(
      basin ? "#dcc595" : tinted ? "#ead5a4" : "#bacc9e",
    );
    const grassColor = new Color(index === 2 ? "#a6a990" : "#bfcca2");
    const stoneColor = new Color(
      index === 2 || index === 3 ? "#bdc4bd" : "#d9caa9",
    );
    const reedHeights: readonly [number, number] = opening
      ? [-0.55, 1.34]
      : basin
        ? [-0.48, 1.08]
        : [-0.55, 0.93];
    const reeds = beds.flatMap((bed, i) =>
      scatterBed(
        bed,
        height,
        seeded(seed + i * 312),
        reedHeights,
        reedColor,
        "reed",
        low,
      ),
    );
    const clearing =
      segment === "S0"
        ? level.encounters?.kite.bank
        : segment === "S1"
          ? level.encounters?.glider.launch
          : undefined;
    // Leave a clear patch around the figures and laid-out sail, including the
    // footprint of wide rocks that would otherwise hide them on a small screen.
    const outsideClearing = (stamp: Stamp) =>
      !clearing ||
      Math.hypot(stamp.x - clearing.x, stamp.z - clearing.z) >
        5.4 + Math.max(stamp.width, stamp.depth);
    if (basin) {
      for (const stamp of reeds) {
        // Taller seed heads sit on the dry crowns while short leaves fringe the pool.
        stamp.height *= 1.13 + 0.37 * clamp(stamp.y * 1.3 + 0.21);
        stamp.width *= 1.24;
      }
    }
    const grass = (opening ? openingShoreSedges : beds).flatMap(
      ([x, z, sx, sz, count], i) =>
        scatterBed(
          [x, z, sx * 1.36, sz * 1.2, Math.round(count * (opening ? 1 : 0.5))],
          height,
          seeded(seed + 173 + i * 413),
          [opening ? -0.18 : 0.07, 1.6],
          grassColor,
          "sedge",
          low,
        ),
    );
    const washColor = new Color(
      basin ? "#736b48" : tinted ? "#7c8050" : "#648656",
    );
    section.add(bankUnderpainting(beds, height, groundWash, washColor));
    const rock = (STONE_BEDS[segment] ?? []).flatMap((bed, i) =>
      scatterBed(
        bed,
        height,
        seeded(seed + 53 + i * 279),
        [-0.39, 1.55],
        stoneColor,
        "stone",
        low,
      ),
    );
    if (opening) {
      const islandStone = new Color("#d9d4b9");
      // The low split rock marks the upstream end of the tall reed island.
      for (const [x, z, width, depth, elevation, yaw] of [
        [22.7, 47.8, 2.45, 1.1, 0.96, -0.4],
        [20.2, 46.1, 1.35, 0.86, 0.65, -0.72],
        [24.4, 45.6, 1.08, 0.82, 0.55, 0.17],
      ] as const) {
        rock.push({
          x,
          z,
          y: height(x, z) - 0.045,
          yaw,
          width,
          height: elevation,
          depth,
          tint: islandStone,
        });
      }

      const footprints = rock
        .filter(outsideClearing)
        .map(({ x, z, width, depth }): Bed => [
          x,
          z,
          width * 1.5,
          depth * 1.65,
          15,
        ]);
      const contacts = bankUnderpainting(
        footprints,
        height,
        groundWash,
        new Color("#394c3c"),
      );
      contacts.name = "S0-stone-contact-wash";
      section.add(contacts);
    }

    placeBatch(
      section,
      tinted ? warmReeds : coolReeds,
      plant,
      reeds.filter(outsideClearing),
      `${segment}-reed-beds`,
    );
    placeBatch(
      section,
      sedges,
      plant,
      grass.filter(outsideClearing),
      `${segment}-sedges`,
    );
    placeBatch(
      section,
      stones,
      ground,
      rock.filter(outsideClearing),
      `${segment}-bank-stones`,
    );
    group.add(section);
  }
}

function bandedTree(): Group {
  const trunk = new MeshLambertMaterial({ color: "#63533e" });
  const canopy = new MeshLambertMaterial({ color: "#789068" });
  const bark = [
    { from: [0, -0.065, 0], to: [0.36, 1.58, -0.05], radius: 0.15 },
    { from: [0.17, 0.86, -0.015], to: [0.81, 1.52, 0.105], radius: 0.076 },
    { from: [0.2, 0.96, -0.03], to: [0.04, 1.66, -0.31], radius: 0.083 },
  ];
  const trunkPieces = bark.map(({ from, to, radius }) => {
    const lower = new Vector3(...from);
    const upper = new Vector3(...to);
    const vector = upper.clone().sub(lower);
    const object = new Object3D();
    object.position.copy(lower).lerp(upper, 0.5);
    object.quaternion.setFromUnitVectors(
      new Vector3(0, 1, 0),
      vector.clone().normalize(),
    );
    object.updateMatrix();
    return new CylinderGeometry(
      radius * 0.37,
      radius,
      vector.length(),
      7,
    ).applyMatrix4(object.matrix);
  });
  const crownParts = [
    [0.33, 1.72, -0.03, 0.65, 0.49, 0.5],
    [0.65, 1.88, 0.09, 0.47, 0.36, 0.46],
    [0.87, 1.61, 0.12, 0.41, 0.35, 0.43],
    [0.12, 1.69, -0.37, 0.38, 0.37, 0.39],
  ] as const;
  const crownPieces = crownParts.map(([x, y, z, sx, sy, sz]) =>
    new IcosahedronGeometry(1, 1).scale(sx, sy, sz).translate(x, y, z),
  );
  const model = new Group();
  model.name = "leaning-bank-tree";
  model.add(
    new Mesh(mergeGeometries(trunkPieces), trunk),
    new Mesh(mergeGeometries(crownPieces), canopy),
  );
  for (const geometry of [...trunkPieces, ...crownPieces]) geometry.dispose();
  return model;
}

function dryRoot(
  height: Height,
  x: number,
  z: number,
  bank: number,
): readonly [number, number] | undefined {
  for (const offset of [0, 2, 4, 7]) {
    const rootX = x + bank * offset;
    const y = height(rootX, z);
    if (y >= 0.24 && y <= 2.25) return [rootX, y];
  }
  return undefined;
}

function plantTrees(land: Group, height: Height): Group[] {
  const template = bandedTree();
  const trees: Group[] = [];
  for (const [x, z, scale, still] of [
    [-37, -7, 2.12],
    [-35, 0, 1.42],
    [42, 24, 1.86, true],
    [46, 28, 1.27, true],
    [-59, 242, 1.54],
    [-70, 276, 1.66],
    [-67, 299, 1.34],
    [-68, 344, 1.84],
    [-64, 370, 1.42],
    [-45, 419, 1.78],
    [-37, 434, 1.25],
    [55, 421, 2.25],
    [50, 432, 3.15],
    [45, 445, 2.0],
    [118, 281, 1.18, true],
    [122, 288, 0.82, true],
    [121, 299, 1.05, true],
    [127, 342, 1.48, true],
    [124, 348, 0.93, true],
    [133, 355, 1.17, true],
  ] as const) {
    const root = still
      ? ([x, height(x, z)] as const)
      : dryRoot(height, x, z, Math.sign(x));
    if (!root) continue;
    const [rootX, y] = root;
    const tree = template.clone();
    tree.position.set(rootX, y - 0.045, z);
    tree.scale.setScalar(scale);
    land.add(tree);
    // The lake-edge copses mark the far shore and don't need animated GLBs.
    if (!still) trees.push(tree);
  }
  return trees;
}

function addWaymarks(land: Group, level: LevelSchema, height: Height): void {
  const wood = new MeshLambertMaterial({ color: "#73583b" });
  const floatPaint = new MeshLambertMaterial({ color: "#e0c58e" });
  const bronze = new MeshLambertMaterial({ color: "#b19162" });
  const inset = new MeshBasicMaterial({ color: "#f4deb3" });
  const float = new CylinderGeometry(0.82, 0.55, 0.38, 10);
  const pole = new CylinderGeometry(0.16, 0.22, 1.8, 7);
  const ring = new CylinderGeometry(0.26, 0.26, 0.14, 8);
  const marker = new OctahedronGeometry(0.52).scale(1, 0.68, 0.83);

  for (const mark of level.landmarks) {
    if (mark.kind !== "beacon" || mark.id === "goal-mark") continue;
    const { x, z } = mark.pos;
    const y = height(x, z);
    const markerRoot = new Group();
    const afloat = y < -0.13;
    markerRoot.name = `${mark.id}-waymark`;
    markerRoot.position.set(x, afloat ? 0 : y - 0.06, z);
    markerRoot.rotation.y = (x - z) * 0.13;
    const base = new Mesh(float, afloat ? floatPaint : bronze);
    base.position.y = afloat ? 0.11 : 0.05;
    if (!afloat) base.scale.set(0.52, 1, 0.52);
    const stem = new Mesh(pole, wood);
    stem.position.y = afloat ? 0.85 : 0.88;
    if (afloat) stem.scale.set(0.8, 0.83, 0.8);
    const band = new Mesh(ring, bronze);
    band.position.y = afloat ? 1.48 : 1.59;
    const cap = new Mesh(marker, inset);
    cap.position.y = afloat ? 1.73 : 1.99;
    markerRoot.add(base, stem, band, cap);
    land.add(markerRoot);
  }
}

function makeWind(level: LevelSchema, height: Height, low: boolean): Group {
  const wind = new Group();
  wind.name = "directional-wind";
  const returnZones = level.zones.filter(
    ({ id }) => id === "return-gust" || id === "return-lee",
  );
  const paper = new MeshBasicMaterial({
    vertexColors: true,
    side: DoubleSide,
    transparent: true,
    depthWrite: false,
  });
  for (const [index, reach] of WIND_REACHES.entries()) {
    const random = seeded(4132 + index * 700);
    const positions: number[] = [];
    const colors: number[] = [];
    const triangles: number[] = [];
    const pigment = new Color(reach.color);
    const segment = level.segments.find((segment) => segment.id === reach.name);
    if (!segment) continue;
    const baseMagnitude = Math.hypot(segment.wind.x, segment.wind.z);
    const steps = 7;

    for (let i = 0; i < reach.density; i++) {
      const x = reach.x + (random() * 2 - 1) * reach.spanX;
      const z = reach.z + (random() * 2 - 1) * reach.spanZ;
      const length = reach.length * (0.41 + random() * 0.86);
      const breadth = 0.24 + random() * 0.28;
      const lift = 0.95 + random() * 0.97;
      const bend = (random() * 2 - 1) * 1.05;
      const weight = 0.17 + 0.2 * random();
      if ((low && i % 3 === 2) || height(x, z) >= 0.85) continue;
      const flow = segment.motionWind
        ? sampleWind(level, { x, z }).direction
        : segment.wind;
      const magnitude = Math.hypot(flow.x, flow.z);
      if (magnitude < 0.05) continue;
      const dx = flow.x / magnitude;
      const dz = flow.z / magnitude;
      if (
        reach.name === "S5" &&
        returnZones.some(({ points }) =>
          crosses(
            points,
            { x: x - dx * length * 0.5, z: z - dz * length * 0.5 },
            { x: x + dx * length * 0.5, z: z + dz * length * 0.5 },
          ),
        )
      )
        continue;
      const flowOpacity =
        segment.motionWind && baseMagnitude > 0
          ? clamp(magnitude / baseMagnitude)
          : 1;
      const first = positions.length / 3;

      for (let point = 0; point <= steps; point++) {
        const t = point / steps;
        const arc = Math.sin(t * Math.PI);
        const offset = bend * arc;
        const cx = x + dx * (t - 0.5) * length - dz * offset;
        const cz = z + dz * (t - 0.5) * length + dx * offset;
        const y = lift + 0.25 * arc;
        const strokeWidth = breadth * arc * (0.45 + 0.77 * t);
        const left = point < steps ? -strokeWidth : 0;
        positions.push(
          cx - dz * left,
          y,
          cz + dx * left,
          cx - dz * strokeWidth,
          y,
          cz + dx * strokeWidth,
        );
        const opacity = weight * flowOpacity * arc * (0.52 + t * 0.48);
        colors.push(
          pigment.r,
          pigment.g,
          pigment.b,
          opacity,
          pigment.r,
          pigment.g,
          pigment.b,
          opacity,
        );
        if (point > 0) {
          const a = first + 2 * point;
          triangles.push(a - 2, a - 1, a, a - 1, a + 1, a);
        }
      }
    }

    const geometry = new BufferGeometry()
      .setIndex(triangles)
      .setAttribute("position", new Float32BufferAttribute(positions, 3))
      .setAttribute("color", new Float32BufferAttribute(colors, 4));
    const ribbons = new Mesh(geometry, paper);
    ribbons.name = `${reach.name}-wind-ribbons`;
    wind.add(ribbons);
  }
  return wind;
}

export function buildMigrationDressing(
  level: LevelSchema,
  height: Height,
  low: boolean,
): {
  group: Group;
  wind: Group;
  trees: Group[];
  setGustTick?: (tick: number) => void;
} {
  const group = new Group();
  group.name = "migration-dressing";
  paintBanks(group, height, low, level);
  if (level.segments.some(({ id }) => id === "S3"))
    group.add(buildCrosswindBanks(height, low));
  const trees = plantTrees(group, height);
  addWaymarks(group, level, height);
  const wind = makeWind(level, height, low);
  group.add(wind);
  const returnWind = buildReturnWind(level, height, low);
  if (returnWind) group.add(returnWind.group);
  return { group, wind, trees, setGustTick: returnWind?.setGustTick };
}
