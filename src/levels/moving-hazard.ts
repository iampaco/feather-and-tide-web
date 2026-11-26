import type { Vec2 } from "../core/math";
import { sweptCircle } from "./geometry";
import type { Zone } from "./schema";

export type MovingHazard = Extract<Zone, { kind: "hazard" }>;

export function hazardOffset(hazard: MovingHazard, tick: number): Vec2 {
  const motion = hazard.motion;
  if (!motion) return { x: 0, z: 0 };
  const cycle =
    ((tick + motion.phaseTicks) % motion.periodTicks) / motion.periodTicks;
  const progress = 1 - Math.abs(2 * cycle - 1);
  return { x: motion.travel.x * progress, z: motion.travel.z * progress };
}

export function hazardPoints(
  hazard: MovingHazard,
  tick: number,
): readonly Vec2[] {
  if (!hazard.motion) return hazard.points;
  const offset = hazardOffset(hazard, tick);
  return hazard.points.map(({ x, z }) => ({
    x: x + offset.x,
    z: z + offset.z,
  }));
}

export function hazardTravelBounds(hazard: MovingHazard): {
  readonly min: Vec2;
  readonly max: Vec2;
} {
  const x = hazard.points.map((point) => point.x);
  const z = hazard.points.map((point) => point.z);
  const travel = hazard.motion?.travel ?? { x: 0, z: 0 };
  return {
    min: {
      x: Math.min(...x) + Math.min(0, travel.x),
      z: Math.min(...z) + Math.min(0, travel.z),
    },
    max: {
      x: Math.max(...x) + Math.max(0, travel.x),
      z: Math.max(...z) + Math.max(0, travel.z),
    },
  };
}

export function hazardStep(hazard: MovingHazard, tick: number): Vec2 {
  const from = hazardOffset(hazard, tick);
  const to = hazardOffset(hazard, tick + 1);
  return { x: to.x - from.x, z: to.z - from.z };
}

export function sweptMovingHazard(
  hazard: MovingHazard,
  from: Vec2,
  to: Vec2,
  radius: number,
  fromTick: number,
  toTick: number,
): boolean {
  if (!hazard.motion) return sweptCircle(hazard.points, from, to, radius);
  // Motion turns at integer tick boundaries. Over a single step translation is
  // linear, so a sweep in the hazard's frame tests the same footprint as rendering.
  const start = hazardOffset(hazard, fromTick);
  const end = hazardOffset(hazard, toTick);
  return sweptCircle(
    hazard.points,
    { x: from.x - start.x, z: from.z - start.z },
    { x: to.x - end.x, z: to.z - end.z },
    radius,
  );
}
