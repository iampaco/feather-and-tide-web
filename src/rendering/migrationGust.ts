import {
  BufferGeometry,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  Mesh,
  MeshBasicMaterial,
} from "three";
import type { Vec2 } from "../core/math";
import { contains } from "../levels/geometry";
import type { LevelSchema } from "../levels/schema";
import { gustStrength } from "../levels/wind";

type Height = (x: number, z: number) => number;

interface StrokeStyle {
  readonly color: string;
  readonly spacing: number;
  readonly length: number;
  readonly breadth: number;
  readonly opacity: number;
}

function strokeField(
  points: readonly Vec2[],
  direction: Vec2,
  height: Height,
  style: StrokeStyle,
  low: boolean,
): Mesh<BufferGeometry, MeshBasicMaterial> {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const ink = new Color(style.color);
  const minX = Math.min(...points.map(({ x }) => x));
  const maxX = Math.max(...points.map(({ x }) => x));
  const minZ = Math.min(...points.map(({ z }) => z));
  const maxZ = Math.max(...points.map(({ z }) => z));
  const stride = style.spacing * (low ? 1.28 : 1);
  const magnitude = Math.hypot(direction.x, direction.z) || 1;
  const dx = direction.x / magnitude;
  const dz = direction.z / magnitude;

  for (let z = minZ + stride * 0.55, row = 0; z < maxZ; z += stride, row++) {
    for (
      let x = minX + stride * (row % 2 === 0 ? 0.43 : 0.87);
      x < maxX;
      x += stride
    ) {
      // A staggered pattern reads as wind-carried foam without moving any
      // world markers that the player could use to judge their own drift.
      const length =
        style.length * (0.82 + 0.24 * (0.5 + 0.5 * Math.sin(x * 0.9 + z)));
      const tail = { x: x - dx * length * 0.62, z: z - dz * length * 0.62 };
      const tip = { x: x + dx * length * 0.38, z: z + dz * length * 0.38 };
      const left = { x: x + dz * style.breadth, z: z - dx * style.breadth };
      const right = { x: x - dz * style.breadth, z: z + dx * style.breadth };
      const corners = [tail, left, tip, right];
      if (
        corners.some(
          (point) =>
            !contains(points, point) || height(point.x, point.z) > 0.12,
        )
      ) {
        continue;
      }
      const first = positions.length / 3;
      for (const [index, point] of corners.entries()) {
        positions.push(point.x, 0.16, point.z);
        colors.push(
          ink.r,
          ink.g,
          ink.b,
          index === 0 ? 0.06 : index === 2 ? 0.36 : 1,
        );
      }
      indices.push(first, first + 1, first + 2, first, first + 2, first + 3);
    }
  }

  return new Mesh(
    new BufferGeometry()
      .setIndex(indices)
      .setAttribute("position", new Float32BufferAttribute(positions, 3))
      .setAttribute("color", new Float32BufferAttribute(colors, 4)),
    new MeshBasicMaterial({
      vertexColors: true,
      side: DoubleSide,
      transparent: true,
      depthWrite: false,
      opacity: style.opacity,
    }),
  );
}

export function buildReturnWind(
  level: LevelSchema,
  height: Height,
  low: boolean,
): { group: Group; setGustTick: (tick: number) => void } | undefined {
  const zone = level.zones.find(({ id }) => id === "return-gust");
  if (zone?.kind !== "interference" || !zone.wind || !zone.gust) return;
  const gust = zone.gust;
  const group = new Group();
  group.name = "return-wind";
  const calmOpacity = 0.64;
  const crestOpacity = 0.84;
  const calm = strokeField(
    zone.points,
    zone.wind,
    height,
    {
      color: "#f3e1b9",
      spacing: 7.2,
      length: 5.5,
      breadth: 0.36,
      opacity: calmOpacity,
    },
    low,
  );
  calm.name = "return-gust-weak";
  const crest = strokeField(
    zone.points,
    gust.peak,
    height,
    {
      color: "#f3e1b9",
      spacing: 4.9,
      length: 11.4,
      breadth: 0.42,
      opacity: crestOpacity,
    },
    low,
  );
  crest.name = "return-gust-crest";
  group.add(calm, crest);

  const lee = level.zones.find(({ id }) => id === "return-lee");
  if (lee?.kind === "interference" && lee.wind) {
    const current = strokeField(
      lee.points,
      lee.wind,
      height,
      {
        color: "#c7ece0",
        spacing: 6.5,
        length: 8.5,
        breadth: 0.34,
        opacity: 0.78,
      },
      low,
    );
    current.name = "return-lee-strokes";
    group.add(current);
  }

  function setGustTick(tick: number): void {
    // Contrast and stroke density convey phase even with reduced motion.
    const strength = gustStrength(gust, tick);
    calm.material.opacity = calmOpacity * (1 - 0.8 * strength);
    crest.material.opacity = crestOpacity * strength;
    crest.visible = strength > 0.04;
  }
  setGustTick(0);
  return { group, setGustTick };
}
