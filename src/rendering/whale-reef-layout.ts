import {
  BufferGeometry,
  Color,
  CylinderGeometry,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Object3D,
} from "three";
import { clamp, lerp, type Vec2 } from "../core/math";
import type { WhaleLevel, Zone } from "../levels/schema";
import { whaleWaterLight } from "./whale-water-light";

type Ribbon = {
  readonly from: Vec2;
  readonly to: Vec2;
  readonly via?: Vec2;
  readonly width: number;
  readonly height: number;
  readonly phase: number;
  readonly sand?: boolean;
  readonly reverse?: boolean;
};

const BED = -11.13;
const reefProfile = [
  [-1, 0],
  [-0.83, 0.12],
  [-0.67, 0.24],
  [-0.53, 0.31],
  [-0.41, 0.54],
  [-0.25, 0.6],
  [-0.09, 0.91],
  [0.1, 0.96],
  [0.27, 0.73],
  [0.37, 0.69],
  [0.49, 0.41],
  [0.65, 0.38],
  [0.81, 0.14],
  [1, 0],
] as const;
const sandProfile = [
  [-1, 0],
  [-0.7, 0.32],
  [-0.37, 0.73],
  [-0.08, 0.94],
  [0.35, 0.86],
  [0.72, 0.43],
  [1, 0],
] as const;
const sand = new Color("#c6bb92");
const base = new Color("#507d79");
const strata = new Color("#799985");
const shadow = new Color("#365e62");

function smooth(value: number): number {
  const t = clamp(value);
  return t * t * (3 - 2 * t);
}

function extent(points: readonly Vec2[]) {
  return {
    left: Math.min(...points.map(({ x }) => x)),
    right: Math.max(...points.map(({ x }) => x)),
    near: Math.min(...points.map(({ z }) => z)),
    far: Math.max(...points.map(({ z }) => z)),
  };
}

function terrain(
  ribbons: readonly Ribbon[],
  paint: MeshStandardMaterial,
): Mesh {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const color = new Color();
  for (const {
    from,
    to,
    via,
    width,
    height,
    phase,
    sand: shoal,
    reverse,
  } of ribbons) {
    const profile = shoal ? sandProfile : reefProfile;
    const steps = Math.max(2, Math.ceil((to.z - from.z) / 5));
    const start = positions.length / 3;
    for (let row = 0; row <= steps; row++) {
      const t = row / steps;
      const z = lerp(from.z, to.z, t);
      const taper = smooth(t / 0.17) * smooth((1 - t) / 0.19);
      const widthVariation =
        0.94 + 0.08 * Math.sin(z * 0.14 + phase) + 0.05 * Math.sin(z * 0.29);
      const shore = (0.44 + 0.56 * taper) * widthVariation;
      const strataNoise = 0.14 * Math.sin(z * 0.25 + phase);
      const swell = 0.83 + strataNoise + 0.08 * Math.cos(z * 0.58 + phase);
      const centerX = !via
        ? lerp(from.x, to.x, t)
        : z <= via.z
          ? lerp(from.x, via.x, smooth((z - from.z) / (via.z - from.z)))
          : lerp(via.x, to.x, smooth((z - via.z) / (to.z - via.z)));
      const x =
        centerX + taper * (shoal ? 0.75 : 2.1) * Math.sin(z * 0.12 + phase);
      for (const [edge, relief] of profile) {
        const face = reverse ? -edge : edge;
        const fracture = Math.sin(z * 0.39 + phase + face * 6);
        const rise = taper * swell * relief * (1 + 0.12 * fracture);
        positions.push(
          x +
            edge * width * shore +
            (1 - Math.abs(edge)) * taper * 0.75 * fracture,
          BED + rise * height,
          z + rise * (0.52 * Math.sin(z * 0.44 + edge * 3 + phase)),
        );
        if (shoal) {
          const grain = 0.09 * Math.sin(z * 0.63 - edge * 4.2);
          color.copy(base).lerp(sand, smooth(relief + grain));
        } else {
          const ledge = smooth((relief + strataNoise - 0.08) * 1.17);
          color.copy(shadow).lerp(base, smooth((face + 0.9) * 1.8));
          color.lerp(strata, ledge * (0.65 + 0.24 * fracture));
          color.lerp(sand, ledge * Math.max(0, fracture) * 0.28);
        }
        color.toArray(colors, colors.length);
      }
      if (!row) continue;
      for (let col = 0; col < profile.length - 1; col++) {
        const a = start + (row - 1) * profile.length + col;
        const b = a + profile.length;
        indices.push(a, b, a + 1, a + 1, b, b + 1);
      }
    }
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 3))
    .setIndex(indices);
  geometry.computeVertexNormals();
  const seabed = new Mesh(geometry, paint);
  seabed.renderOrder = -9;
  return seabed;
}

export function reefPaint(viewDepth: { value: number }): MeshStandardMaterial {
  const paint = new MeshStandardMaterial({
    vertexColors: true,
    roughness: 1,
    side: DoubleSide,
    transparent: true,
    depthWrite: false,
    forceSinglePass: true,
  });
  paint.name = "W3 reef terrain";
  paint.onBeforeCompile = (shader) => {
    shader.uniforms.viewDive = viewDepth;
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        "#include <common>\nvarying vec3 bedPoint;\nvarying float bedEyeDepth;",
      )
      .replace(
        "#include <project_vertex>",
        `
        #include <project_vertex>
        bedPoint = (modelMatrix * vec4(transformed, 1.0)).xyz;
        bedEyeDepth = -mvPosition.z;
      `,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>
        varying vec3 bedPoint;
        varying float bedEyeDepth;
        uniform float viewDive;
        ${whaleWaterLight}`,
      )
      .replace(
        "#include <alphatest_fragment>",
        `
        // Feather the feet into the painted sea floor, while the terraces keep solid cores.
        diffuseColor.a *= smoothstep(-11.04, -10.52, bedPoint.y);
        #include <alphatest_fragment>
      `,
      )
      .replace(
        "#include <opaque_fragment>",
        `
        float mottling = sin(bedPoint.x * 0.47 + bedPoint.z * 0.34)
                       * cos(bedPoint.z * 0.63 - bedPoint.x * 0.48);
        float terrace = smoothstep(-10.53, -9.83, bedPoint.y);
        float bedding = sin(bedPoint.y * 6.6 + bedPoint.z * 0.16 + bedPoint.x * 0.19 + mottling * 0.87);
        float seam = smoothstep(0.45, 0.92, bedding) * terrace;
        float lamina = smoothstep(0.6, 0.94, -bedding) * terrace;
        float sandRipple = sin(bedPoint.z * 1.52 - bedPoint.x * 0.24 + mottling);
        outgoingLight *= 0.98 - 0.21 * seam + 0.046 * mottling
                       + (1.0 - terrace) * sandRipple * 0.032;
        outgoingLight += vec3(0.035, 0.040, 0.027) * lamina;
        outgoingLight = whaleThroughWater(outgoingLight, bedPoint.y, bedEyeDepth, viewDive, 0.84);
        #include <opaque_fragment>
      `,
      );
  };
  return paint;
}

export function reefBanks(
  water: Zone,
  mid: Vec2,
  bend: Vec2,
  paint: MeshStandardMaterial,
  arc?: Vec2,
): Mesh {
  const bounds = extent(water.points);
  const width = Math.min(
    mid.x - bounds.left,
    bounds.right - mid.x,
    bend.x - bounds.left,
    bounds.right - bend.x,
    arc ? Math.min(arc.x - bounds.left, bounds.right - arc.x) : Infinity,
  );
  const near = bounds.near + 3;
  const far = bounds.far - 4;
  const banks = terrain(
    [
      {
        from: { x: mid.x - width * 0.53, z: near },
        to: { x: bend.x - width * 0.69, z: far },
        via: arc && { x: arc.x - width * 0.53, z: arc.z },
        width: width * 0.38,
        height: 2.72,
        phase: 3.7,
      },
      {
        from: { x: mid.x + width * 0.61, z: near + 12 },
        to: { x: bend.x + width * 0.57, z: far - 10 },
        via: arc && { x: arc.x + width * 0.61, z: arc.z },
        width: width * 0.33,
        height: 2.38,
        phase: 1.4,
        reverse: true,
      },
      {
        from: { x: mid.x + 5, z: near },
        to: { x: bend.x - 6, z: far },
        via: arc,
        width: width * 0.48,
        height: 0.78,
        phase: 0,
        sand: true,
      },
    ],
    paint,
  );
  banks.name = "Submerged rocks";
  return banks;
}

function shippingEntrance(entry: Vec2, gate: number): Group {
  const group = new Group();
  group.name = "Shipping entrance marks";
  const buoys = new InstancedMesh(
    new CylinderGeometry(0.37, 0.79, 1.72, 6).translate(0, 0.63, 0),
    new MeshStandardMaterial({ color: "#cbb892", roughness: 1 }),
    6,
  );
  const place = new Object3D();
  for (let i = 0; i < buoys.count; i++) {
    place.position.set(
      entry.x + (i % 2 === 0 ? -17 : 17),
      0,
      gate - 25 + Math.floor(i / 2) * 16,
    );
    place.updateMatrix();
    buoys.setMatrixAt(i, place.matrix);
  }
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const ink = new Color("#e2d0a9");
  for (let wake = 0; wake < 9; wake++) {
    const x = entry.x + Math.sin(wake * 2.39) * 10;
    const z = gate - 34 + wake * 5.6;
    const span = 3.7 + (wake % 3) * 2.6;
    const start = positions.length / 3;
    for (let i = 0; i <= 6; i++) {
      const t = i / 6;
      const strength = Math.sin(t * Math.PI);
      const crest = z + 1.8 * Math.sin(t * Math.PI + wake * 0.8) + 1.9 * t;
      positions.push(
        x + span * (2 * t - 1),
        0.052,
        crest + 0.48,
        x + span * (2 * t - 1),
        0.052,
        crest,
        x + span * (2 * t - 1),
        0.052,
        crest - 0.94,
      );
      colors.push(
        ink.r,
        ink.g,
        ink.b,
        0,
        ink.r,
        ink.g,
        ink.b,
        0.45 * strength,
        ink.r,
        ink.g,
        ink.b,
        0,
      );
      if (!i) continue;
      for (let col = 0; col < 2; col++) {
        const a = start + (i - 1) * 3 + col;
        indices.push(a, a + 3, a + 1, a + 1, a + 3, a + 4);
      }
    }
  }
  const water = new Mesh(
    new BufferGeometry()
      .setAttribute("position", new Float32BufferAttribute(positions, 3))
      .setAttribute("color", new Float32BufferAttribute(colors, 4))
      .setIndex(indices),
    new MeshBasicMaterial({
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      side: DoubleSide,
    }),
  );
  water.renderOrder = -3;
  group.add(buoys, water);
  return group;
}

export function reefApproach(
  level: WhaleLevel,
  mid: Vec2,
  paint: MeshStandardMaterial,
): Group {
  const group = new Group();
  group.name = "W3 route scenery";
  const quietEntry = level.landmarks.find(
    ({ id }) => id === "quiet-entry",
  )?.pos;
  const shipEntry = level.landmarks.find(
    ({ id }) => id === "shipping-entry",
  )?.pos;
  const quietGate = level.triggers.find(
    (gate) => gate.kind === "route" && gate.route === "quiet",
  );
  const shipGate = level.triggers.find(
    (gate) => gate.kind === "route" && gate.route === "shipping",
  );
  if (
    shipEntry &&
    shipGate?.kind === "route" &&
    shipGate.crossingZ !== undefined
  )
    group.add(shippingEntrance(shipEntry, shipGate.crossingZ));

  if (
    quietEntry &&
    quietGate?.kind === "route" &&
    quietGate.crossingZ !== undefined
  ) {
    const { left, right } = extent(quietGate.points);
    const z = quietGate.crossingZ;
    const width = Math.min(quietEntry.x - left, right - quietEntry.x);
    const entrance = terrain(
      [
        {
          from: { x: quietEntry.x + width * 0.6, z: quietEntry.z - 12 },
          to: { x: mid.x + width * 0.72, z: mid.z + 4 },
          width: width * 0.23,
          height: 2.18,
          phase: 2.1,
          reverse: true,
        },
        {
          from: { x: quietEntry.x - width * 0.83, z: z - 31 },
          to: { x: mid.x - width * 0.75, z: mid.z + 1 },
          width: width * 0.34,
          height: 2.7,
          phase: 5.4,
        },
        {
          from: { x: quietEntry.x + 3, z: quietEntry.z - 18 },
          to: { x: mid.x + 5, z: mid.z + 7 },
          width: width * 0.49,
          height: 0.76,
          phase: 0,
          sand: true,
        },
      ],
      paint,
    );
    entrance.name = "Quiet entrance shoals";
    // The fan starts in the observing water and meets the quiet gate at its inner side.
    const fan = terrain(
      [
        {
          from: { x: right + width * 0.42, z: z - 48 },
          to: { x: quietEntry.x + width * 0.33, z: z + 11 },
          width: width * 0.33,
          height: 0.65,
          phase: 2.9,
          sand: true,
        },
      ],
      paint,
    );
    fan.name = "Quiet entrance sand fan";
    group.add(entrance, fan);
  }
  return group;
}
