import { contains } from "./geometry";
import type { Vec2 } from "../core/math";
import type { NoiseCycle, WhaleLevel, Zone } from "./schema";

export type CyclicNoise = Extract<Zone, { kind: "interference" }> & {
  readonly cycle: NoiseCycle;
};

export function isCyclicNoise(zone: Zone): zone is CyclicNoise {
  return zone.kind === "interference" && zone.cycle !== undefined;
}

export function noisePhase(
  { periodTicks, phaseTicks, activeTicks }: NoiseCycle,
  tick: number,
): { active: boolean; remainingTicks: number; elapsedTicks: number } {
  const offset = ((tick % periodTicks) + phaseTicks) % periodTicks;
  const active = offset < activeTicks;
  return {
    active,
    remainingTicks: (active ? activeTicks : periodTicks) - offset,
    elapsedTicks: active ? offset : offset - activeTicks,
  };
}

export function activeNoiseAt(
  level: WhaleLevel,
  tick: number,
): readonly CyclicNoise[] {
  return level.zones
    .filter(isCyclicNoise)
    .filter(({ cycle }) => noisePhase(cycle, tick).active);
}

export function insideNoise(zone: CyclicNoise, pos: Vec2): boolean {
  return contains(zone.points, pos);
}
