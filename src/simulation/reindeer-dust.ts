import type { Vec2 } from "../core/math";
import { contains } from "../levels/geometry";
import type { ReindeerLevel } from "../levels/schema";

export const reindeerDustRefuges = [
  { zone: "dust-entry-rest", sign: "dust-entry" },
  { zone: "dust-shelter", sign: "dust-shelter-sign" },
  { zone: "dust-exit-rest", sign: "dust-exit-sign" },
] as const;

export interface ReindeerDustSample {
  readonly phase: "calm" | "warning" | "active";
  readonly remainingTicks: number;
  readonly strain: number;
  readonly inDust: boolean;
}

/** World phase is reconstructed from the checkpoint tick, including during retries. */
export function sampleReindeerDust(
  level: ReindeerLevel,
  tick: number,
  pos: Vec2,
): ReindeerDustSample {
  const cycle = level.dustCycle;
  const period = cycle.calmTicks + cycle.warningTicks + cycle.activeTicks;
  const phaseTick = (tick + cycle.phaseTicks) % period;
  const phase =
    phaseTick < cycle.calmTicks
      ? "calm"
      : phaseTick < cycle.calmTicks + cycle.warningTicks
        ? "warning"
        : "active";
  const end =
    phase === "calm"
      ? cycle.calmTicks
      : phase === "warning"
        ? cycle.calmTicks + cycle.warningTicks
        : period;
  const zone = level.zones.find(
    (zone) => cycle.zoneIds.includes(zone.id) && contains(zone.points, pos),
  );
  return {
    phase,
    remainingTicks: end - phaseTick,
    inDust: zone !== undefined,
    strain:
      phase === "active" && zone?.kind === "interference" ? zone.strain : 0,
  };
}
