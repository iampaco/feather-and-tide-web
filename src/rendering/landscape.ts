import {
  Box3,
  BoxGeometry,
  CircleGeometry,
  Color,
  CylinderGeometry,
  DoubleSide,
  Float32BufferAttribute,
  ShaderMaterial,
  Euler,
  Group,
  IcosahedronGeometry,
  InstancedMesh,
  Line,
  LineBasicMaterial,
  BufferGeometry,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  Object3D,
  PlaneGeometry,
  Shape,
  ShapeGeometry,
  Vector3,
} from "three";
import type { LevelSchema, Zone } from "../levels/schema";
import {
  tailwindPracticeId,
  tailwindReedBankId,
} from "../levels/tailwind-practice";
import { contains } from "../levels/geometry";
import type { AtmosphericUniforms } from "./migrationAtmosphere";
import { buildMigrationDressing } from "./migrationDressing";
import { buildMigrationOverlays, directionalWind } from "./migrationOverlays";
import { buildMigrationMist } from "./migrationVistas";
import type { OrbitClearance } from "./orbit-clearance";
import { buildMigrationTerrain } from "./terrain";
import { waterMaterial } from "./water";
import { reedClump } from "./reeds";
import { buildWindfarmFootings } from "./windfarmFootings";

const shore = "#c0b495";
const reedsGeometry = reedClump();
const rock = new IcosahedronGeometry(1, 0);
const plane = new PlaneGeometry(1, 1);
const disk = new CircleGeometry(1, 28);

function tailwindReeds(level: LevelSchema, low: boolean): Group {
  const group = new Group();
  const bank = level.zones.find(({ id }) => id === tailwindReedBankId);
  if (!bank) return group;
  const spacing = low ? 2.6 : 1.65;
  const xs = bank.points.map(({ x }) => x);
  const zs = bank.points.map(({ z }) => z);
  const clumps = [];
  for (let z = Math.min(...zs) + 1.3; z < Math.max(...zs) - 1; z += spacing) {
    for (let x = Math.min(...xs) + 1.3; x < Math.max(...xs) - 1; x += spacing) {
      const pos = {
        x: x + Math.sin(z * 1.83) * 0.31,
        z: z + Math.sin(x) * 0.26,
      };
      if (contains(bank.points, pos)) clumps.push(pos);
    }
  }
  const reeds = new InstancedMesh(
    reedsGeometry,
    new MeshLambertMaterial({ vertexColors: true, side: DoubleSide }),
    clumps.length,
  );
  reeds.name = "Tailwind reed bank clumps";
  const transform = new Object3D();
  for (const [i, { x, z }] of clumps.entries()) {
    const height = 1.6 + Math.sin(i * 2.4) * 0.45;
    transform.position.set(x, height * 0.5, z);
    transform.rotation.y = i * 0.8;
    transform.scale.set(1.2, height, 1.2);
    transform.updateMatrix();
    reeds.setMatrixAt(i, transform.matrix);
  }
  group.add(reeds);
  return group;
}

function filledZone(
  zone: Zone,
  color: string,
  opacity: number,
  height: number,
): Group {
  const group = new Group();
  group.name = zone.id;
  const shape = new Shape();
  zone.points.forEach((point, i) => {
    if (i === 0) shape.moveTo(point.x, -point.z);
    else shape.lineTo(point.x, -point.z);
  });
  const fill = new Mesh(
    new ShapeGeometry(shape),
    new MeshBasicMaterial({
      color,
      transparent: true,
      opacity,
      side: DoubleSide,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -1,
    }),
  );
  fill.rotateX(-Math.PI / 2);
  fill.position.y = height;
  const outline = new Line(
    new BufferGeometry().setFromPoints(
      zone.points.map((p) => new Vector3(p.x, height + 0.03, p.z)),
    ),
    new LineBasicMaterial({ color }),
  );
  outline.name = "outline";
  group.add(fill, outline);
  if (zone.kind === "hazard") {
    const stripe = new Mesh(
      new ShapeGeometry(shape),
      new ShaderMaterial({
        transparent: true,
        side: DoubleSide,
        depthWrite: false,
        uniforms: { shade: { value: new Color(color) } },
        vertexShader: `
          varying vec2 p;
          void main() { p = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
        `,
        fragmentShader: `
          uniform vec3 shade; varying vec2 p;
          void main() {
            float band = step(0.78, fract((p.x + p.y) / 3.8));
            gl_FragColor = vec4(shade, band * 0.29);
            #include <colorspace_fragment>
          }
        `,
      }),
    );
    stripe.position.y = height + 0.06;
    stripe.rotateX(-Math.PI / 2);
    stripe.renderOrder = 5;
    const width = 0.37;
    const vertices = zone.points.slice(1).flatMap((b, i) => {
      const a = zone.points[i];
      if (!a) return [];
      const length = Math.hypot(b.x - a.x, b.z - a.z);
      const dx = ((b.z - a.z) * width) / length;
      const dz = ((a.x - b.x) * width) / length;
      const ay = height + 0.02;
      const innerA = [a.x + dx, ay, a.z + dz];
      const outerA = [a.x - dx, ay, a.z - dz];
      const innerB = [b.x + dx, ay, b.z + dz];
      const outerB = [b.x - dx, ay, b.z - dz];
      return [...innerA, ...outerA, ...innerB, ...innerB, ...outerA, ...outerB];
    });
    const ribbon = new Mesh(
      new BufferGeometry().setAttribute(
        "position",
        new Float32BufferAttribute(vertices, 3),
      ),
      new MeshBasicMaterial({
        color,
        side: DoubleSide,
        depthTest: false,
        depthWrite: false,
      }),
    );
    ribbon.renderOrder = 6;
    outline.material.depthTest = false;
    outline.renderOrder = 7;
    group.add(stripe, ribbon);
  }
  return group;
}

function turbine(): { model: Group; rotor: Group; tower: Mesh } {
  const model = new Group();
  const tower = new Mesh(
    new CylinderGeometry(0.35, 0.8, 13, 8),
    new MeshLambertMaterial({ color: "#f0dcc3" }),
  );
  tower.position.y = 6.5;
  const rotor = new Group();
  rotor.position.set(0, 13, -0.8);
  rotor.add(
    new Mesh(
      new IcosahedronGeometry(0.95, 1),
      new MeshLambertMaterial({ color: "#e7bd8f" }),
    ),
  );
  for (let i = 0; i < 3; i++) {
    const arm = new Group();
    arm.rotation.z = (i * Math.PI * 2) / 3;
    const blade = new Mesh(
      new BoxGeometry(0.43, 6, 0.25),
      new MeshLambertMaterial({ color: "#f6e4c3" }),
    );
    blade.position.y = 3.3;
    blade.rotation.z = 0.09;
    arm.add(blade);
    rotor.add(arm);
  }
  model.add(tower, rotor);
  return { model, rotor, tower };
}

export interface Landscape {
  readonly group: Group;
  readonly wind: Group;
  readonly turbines: readonly { model: Group; rotor: Group }[];
  readonly trees: readonly Group[];
  readonly height?: (x: number, z: number) => number;
  readonly orbitClearance?: OrbitClearance;
  readonly setLanding?: (amount: number) => void;
  readonly setGustTick?: (tick: number) => void;
}

function migrationLandscape(
  level: LevelSchema,
  low: boolean,
  atmosphere?: AtmosphericUniforms,
): Landscape {
  const terrain = buildMigrationTerrain(level, low, atmosphere);
  const { group, height } = terrain;
  const {
    group: dressing,
    wind,
    trees,
    setGustTick,
  } = buildMigrationDressing(level, height, low);
  const overlays = buildMigrationOverlays(level, height, low);
  const turbinePositions = level.landmarks
    .filter(({ kind }) => kind === "turbine")
    .map(({ pos }) => pos);
  const turbines = turbinePositions.map(({ x, z }) => {
    const scenery = turbine();
    scenery.model.position.set(x, Math.max(0, height(x, z)) + 0.27, z);
    group.add(scenery.model);
    return scenery;
  });
  group.add(
    dressing,
    buildWindfarmFootings(turbinePositions, height, low),
    buildMigrationMist(low),
    overlays.group,
    tailwindReeds(level, low),
  );
  return {
    group,
    turbines,
    trees,
    wind,
    height,
    orbitClearance: {
      height,
      obstacles: [
        ...overlays.cameraObstacles,
        // Margin accommodates the wider authored tower at the same hub height.
        ...turbines.map(({ tower }) => {
          tower.updateWorldMatrix(true, false);
          return new Box3().setFromObject(tower).expandByScalar(0.5);
        }),
      ],
    },
    setLanding: overlays.setLanding,
    setGustTick,
  };
}

export function buildLandscape(
  level: LevelSchema,
  low: boolean,
  atmosphere?: AtmosphericUniforms,
): Landscape {
  if (level.id === "migration")
    return migrationLandscape(level, low, atmosphere);
  const group = new Group();
  const turbines: { model: Group; rotor: Group }[] = [];
  const trees: Group[] = [];
  const reedMaterial = new MeshLambertMaterial({
    vertexColors: true,
    side: DoubleSide,
  });
  const wind = new Group();
  let seed = 757;
  function random(): number {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  }
  const { min, max } = level.bounds;
  const width = max.x - min.x + 110;
  for (const [index, segment] of level.segments.entries()) {
    const end = level.segments[index + 1]?.start ?? max.z + 36;
    const begin = index === 0 ? segment.start - 44 : segment.start;
    const water = new Mesh(
      plane,
      waterMaterial(
        segment.color,
        level.segments[index - 1]?.color ?? segment.color,
        low,
      ),
    );
    water.position.z = (begin + end) / 2;
    water.scale.set(width, end - begin, 1);
    water.rotation.x = -Math.PI / 2;
    group.add(water);

    const color = new Color(segment.color);
    const washCount = Math.ceil((end - begin) / (low ? 7 : 2));
    const washes = new InstancedMesh(
      disk,
      new MeshBasicMaterial({
        transparent: true,
        opacity: 0.09,
        depthWrite: false,
      }),
      washCount,
    );
    const reeds = new InstancedMesh(
      reedsGeometry,
      reedMaterial,
      low ? 105 : 215,
    );
    const object = new Object3D();
    for (let i = 0; i < washCount; i++) {
      object.position.set(
        (random() - 0.5) * width,
        0.018 + i * 0.00001,
        begin + random() * (end - begin),
      );
      object.rotation.set(-Math.PI / 2, 0, (random() - 0.5) * 0.39);
      object.scale.set(4 + random() * 38, 0.12 + random() * 3.9, 1);
      object.updateMatrix();
      washes.setMatrixAt(i, object.matrix);
      washes.setColorAt(
        i,
        color
          .clone()
          .lerp(
            new Color(i % 4 === 0 ? "#e6dec2" : "#4f7774"),
            0.29 + random() * 0.53,
          ),
      );
    }
    // Preserve subsequent shoreline and wind placement when sampling fewer
    // positions for the multi-stem reeds.
    for (let i = 0; i < (low ? 180 : 430); i++) {
      const side = i % 2 === 0 ? -1 : 1;
      const along = begin + random() * (end - begin);
      const bend = 32 + 13 * Math.sin(along / 23 + side * 1.7);
      object.position.set(
        side * (bend + random() * 14),
        0.1 + random() * 0.65,
        along,
      );
      object.rotation.set(0.13 - random() * 0.28, random() * 6, side * 0.15);
      object.scale.set(0.6 + random() * 1.1, 0.7 + random() * 2.2, 0.75);
      const tone = random() < 0.4 ? "#e5d9ac" : "#b2b79a";
      const blend = random() * 0.3;
      if (i >= reeds.count) continue;
      object.updateMatrix();
      reeds.setMatrixAt(i, object.matrix);
      reeds.setColorAt(i, new Color(tone).lerp(color, blend));
    }
    group.add(washes, reeds);

    const windFarm = segment.id === "S4" || segment.id === "practice-wind";
    const banks = new InstancedMesh(
      rock,
      new MeshLambertMaterial({ flatShading: true }),
      low ? 36 : 72,
    );
    for (let i = 0; i < banks.count; i++) {
      const side = i % 2 === 0 ? -1 : 1;
      const z = begin + random() * (end - begin);
      const bend = 37 + 13 * Math.sin(z / 23 + side * 1.7);
      object.rotation.set(0.12, random() * Math.PI, 0);
      object.position.set(
        side * (bend + (windFarm ? 38 : 0) + random() * 49),
        -0.98,
        z,
      );
      object.scale.set(
        4 + random() * 19,
        0.78 + random() * (windFarm ? 0.65 : 1.6),
        9 + random() * 16,
      );
      object.updateMatrix();
      banks.setMatrixAt(i, object.matrix);
      banks.setColorAt(i, new Color(shore).lerp(color, random() * 0.51));
    }
    group.add(banks);

    if (Math.hypot(segment.wind.x, segment.wind.z) > 0.15) {
      const points: Vector3[] = [];
      const material = new LineBasicMaterial({
        color: "#f6efd6",
        transparent: true,
        opacity: 0.64,
      });
      for (let i = 0; i < (low ? 9 : 22); i++) {
        const x = (random() - 0.5) * width * 0.64;
        const z = begin + random() * (end - begin);
        for (let j = 0; j < 7; j++)
          points[j] = new Vector3(
            x + j * segment.wind.x * 2.4,
            0.63 + Math.sin(j / 4) * 0.48,
            z + j * segment.wind.z * 2.4,
          );
        wind.add(
          new Line(new BufferGeometry().setFromPoints(points), material),
        );
      }
    }
  }

  for (const mark of level.landmarks) {
    const { x, z } = mark.pos;
    if (mark.kind === "turbine") {
      const { model, rotor } = turbine();
      model.position.set(x, 0, z);
      group.add(model);
      turbines.push({ model, rotor });
    } else if (mark.kind === "peak") {
      const ridge = new Mesh(
        rock,
        new MeshLambertMaterial({ color: "#738681", flatShading: true }),
      );
      ridge.scale.set(12, 5, 31);
      ridge.position.set(x, -1.4, z);
      ridge.rotation.set(0.12, 0.28, 0.19);
      group.add(ridge);
    } else if (mark.kind === "water") {
      const pool = new Mesh(
        disk,
        new MeshBasicMaterial({
          color: "#b3c5b2",
          transparent: true,
          opacity: 0.48,
          depthWrite: false,
        }),
      );
      pool.rotateX(-Math.PI / 2);
      pool.scale.set(32, 48, 1);
      pool.position.set(x, 0.067, z);
      group.add(pool);
    } else if (mark.kind === "reed") {
      const patch = new InstancedMesh(
        reedsGeometry,
        reedMaterial,
        low ? 22 : 70,
      );
      const object = new Object3D();
      for (let i = 0; i < patch.count; i++) {
        object.position.set(
          x + (random() - 0.5) * 16,
          0.4,
          z + (random() - 0.5) * 13,
        );
        object.rotation.copy(new Euler(0.15, random() * 6, -0.21));
        object.scale.set(0.85 + random() * 0.85, 0.8 + random() * 3.2, 1.1);
        object.updateMatrix();
        patch.setMatrixAt(i, object.matrix);
        patch.setColorAt(i, new Color(random() < 0.35 ? "#f0c891" : "#c2c9a9"));
      }
      group.add(patch);
    } else {
      const post = new Mesh(
        new CylinderGeometry(0.14, 0.23, 4.2, 6),
        new MeshLambertMaterial({ color: "#5a6450" }),
      );
      post.position.set(x, 2.1, z);
      const lamp = new Mesh(rock, new MeshBasicMaterial({ color: "#edcf96" }));
      lamp.position.set(x, 4.3, z);
      lamp.scale.set(0.75, 1, 0.75);
      group.add(post, lamp);
    }
  }
  // Ground foliage marks the two winds without defining flight obstacles.
  for (const [anchorId, offsets] of [
    [
      "pass-ridge",
      [
        [3, -15],
        [0, 3],
        [11, 21],
        [4, 37],
      ],
    ],
    [
      "valley-mark",
      [
        [-34, 16],
        [-29, 37],
        [34, 23],
        [27, 57],
        [42, 71],
      ],
    ],
  ] as const) {
    const anchor = level.landmarks.find((mark) => mark.id === anchorId);
    if (!anchor) continue;
    for (const [index, [x, z]] of offsets.entries()) {
      const stem = new Group();
      stem.position.set(anchor.pos.x + x, 0, anchor.pos.z + z);
      stem.scale.setScalar(2.35 + (index % 3) * 0.29);
      const trunk = new Mesh(
        new CylinderGeometry(0.045, 0.095, 1.1, 5),
        new MeshLambertMaterial({ color: "#5b5d4c" }),
      );
      trunk.position.set(0.11, 0.52, 0);
      trunk.rotation.z = -0.21;
      const canopy = new Mesh(
        rock,
        new MeshLambertMaterial({
          color: index % 2 ? "#6f927d" : "#7d986b",
          flatShading: true,
        }),
      );
      canopy.position.set(0.23, 1.2, 0);
      canopy.scale.set(0.59, 0.73, 0.48);
      stem.add(trunk, canopy);
      trees.push(stem);
      group.add(stem);
    }
  }
  for (const zone of level.zones) {
    if (level.id === tailwindPracticeId && zone.kind === "interference")
      wind.add(directionalWind(zone));
    if (zone.kind === "hazard")
      group.add(
        filledZone(
          zone,
          zone.id === "sweep" ? "#a34632" : "#6d5148",
          0.29,
          0.12,
        ),
      );
    if (zone.kind === "supply")
      group.add(filledZone(zone, "#f4e1a6", 0.17, 0.105));
    if (zone.kind === "goal")
      group.add(filledZone(zone, "#f9e1af", 0.25, 0.11));
  }
  group.add(wind, tailwindReeds(level, low));
  return { group, turbines, trees, wind };
}
