import { STEP_SEC } from "../core/clock";
import type { WhaleActor, WhaleState } from "../core/game";
import {
  hazardOffset,
  hazardTravelBounds,
  type WaterHazard,
} from "../levels/whale-geometry";
import { podSlot, WHALE } from "../simulation/whale-motion";

export function shipPassage(ship: WaterHazard): { near: number; far: number } {
  const { min, max } = hazardTravelBounds(ship);
  return { near: min.z - WHALE.hitRadius, far: max.z + WHALE.hitRadius };
}

export function surfaceCruiseWindow(
  ship: WaterHazard,
  state: WhaleState,
  leader: WhaleActor,
  far: number,
): boolean {
  const motion = ship.motion;
  if (!motion || motion.travel.z !== 0 || motion.travel.x === 0) return false;
  const pod = state.actors;
  if (pod.some(({ status }) => status === "strayed" || status === "rejoining"))
    return false;
  const forward = { pos: leader.pos, heading: 0 };
  const width = [
    ...pod.map(({ pos }) => pos.x),
    ...state.actors
      .slice(1)
      .map((_, index) => podSlot(forward, index + 1, state.cohesion).x),
  ];
  const tail = Math.min(
    ...pod.map(({ pos }) => pos.z),
    podSlot(forward, state.actors.length - 1, state.cohesion).z,
  );
  // Use the whole pod's current and settled footprint, plus acceleration
  // from rest. A hull that turns back before the tail clears still blocks.
  const duration = Math.ceil(
    ((far - tail) / WHALE.cruise + WHALE.cruise / WHALE.acceleration) /
      STEP_SEC,
  );
  const end = state.tick + duration;
  const halfPeriod = motion.periodTicks / 2;
  const turn =
    (Math.floor((state.tick + motion.phaseTicks) / halfPeriod) + 1) *
      halfPeriod -
    motion.phaseTicks;
  const offsets = [hazardOffset(ship, state.tick).x, hazardOffset(ship, end).x];
  if (turn < end) offsets.push(hazardOffset(ship, turn).x);
  if (turn + halfPeriod < end)
    offsets.push(hazardOffset(ship, turn + halfPeriod).x);
  const hull = ship.points.map(({ x }) => x);
  return (
    Math.max(...hull) + Math.max(...offsets) <
      Math.min(...width) - WHALE.hitRadius ||
    Math.min(...hull) + Math.min(...offsets) >
      Math.max(...width) + WHALE.hitRadius
  );
}
