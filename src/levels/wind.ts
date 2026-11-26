import { clamp, lerp, type Vec2 } from "../core/math";
import { interiorDepth } from "./geometry";
import type { LevelSchema, WindGust } from "./schema";

const still = { x: 0, z: 0 };
const localEdgeFade = 7;
const localSpeed = 2.5;

export function gustStrength(gust: WindGust, tick: number): number {
  const cycle =
    ((tick + gust.phaseTicks) % gust.periodTicks) / gust.periodTicks;
  return (1 - Math.cos(cycle * 2 * Math.PI)) / 2;
}

export function sampleWind(
  level: LevelSchema,
  pos: Vec2,
  tick = 0,
): { direction: Vec2; drift: Vec2 } {
  const index = level.segments.findLastIndex(({ start }) => start <= pos.z);
  const segment = level.segments[index];
  let direction = segment?.wind ?? still;
  let drift = still;
  if (segment?.motionWind) {
    const { speed, transition } = segment.motionWind;
    const end = level.segments[index + 1]?.start ?? level.bounds.max.z;
    const amount = clamp(
      Math.min(pos.z - segment.start, end - pos.z) / transition,
    );
    direction = amount
      ? { x: direction.x * amount, z: direction.z * amount }
      : still;
    if (amount) drift = { x: direction.x * speed, z: direction.z * speed };
  }
  for (const zone of level.zones) {
    if (zone.kind !== "interference" || !zone.wind) continue;
    const amount = clamp(interiorDepth(zone.points, pos) / localEdgeFade);
    if (amount === 0) continue;
    const strength = zone.gust ? gustStrength(zone.gust, tick) : 0;
    const wind = zone.gust
      ? {
          x: lerp(zone.wind.x, zone.gust.peak.x, strength),
          z: lerp(zone.wind.z, zone.gust.peak.z, strength),
        }
      : zone.wind;
    direction = {
      x: lerp(direction.x, wind.x, amount),
      z: lerp(direction.z, wind.z, amount),
    };
    drift = {
      x: lerp(drift.x, wind.x * localSpeed, amount),
      z: lerp(drift.z, wind.z * localSpeed, amount),
    };
    break;
  }
  return { direction, drift };
}
