import type { ReindeerActor, ReindeerState } from "../core/game";
import { clamp, distance, lerp, type Vec2 } from "../core/math";
import { groundBlocked, hoofRadius } from "../levels/reindeer-ground";
import type { ReindeerLevel } from "../levels/schema";
import { REINDEER as R } from "./reindeer-tuning";

export function reindeerFollowTarget(
  level: ReindeerLevel,
  route: Pick<ReindeerState, "trail" | "trailStart" | "waitTicks">,
  leader: ReindeerActor,
  actor: ReindeerActor,
  index: number,
  keepGathered = false,
): { point: Vec2; cursor: number; nextIndex: number; withinCall: boolean } {
  const { trail, trailStart, waitTicks } = route;
  const trailEnd = trailStart + trail.length - 1;
  const withinCall =
    waitTicks > 0 && distance(actor.pos, leader.pos) <= R.callRadius;
  const cursor = clamp(actor.trailIndex, trailStart, trailEnd);
  const normalSlot =
    trailEnd - Math.round((index * R.spacing) / R.sampleSpacing);
  // Let a deer retain ground already gained by gathering. Once it drops
  // back to its ordinary slot, it follows at the usual spacing again.
  const packed =
    keepGathered && actor.status === "following" && cursor > normalSlot + 1;
  const spacing = withinCall
    ? lerp(R.spacing, R.callSpacing, waitTicks / R.waitTicks)
    : packed
      ? R.callSpacing
      : R.spacing;
  const tail = Math.max(
    trailStart,
    trailEnd - Math.round((index * spacing) / R.sampleSpacing),
  );
  const nextIndex = Math.min(Math.max(cursor, tail), cursor + 1);
  if (actor.status === "rejoining")
    return { point: leader.pos, cursor, nextIndex, withinCall };

  const sampleIndex = nextIndex - trailStart;
  const center = trail[sampleIndex] ?? leader.pos;
  const prior = trail[Math.max(0, sampleIndex - 1)] ?? center;
  const after = trail[sampleIndex + 1] ?? center;
  const tangent = Math.atan2(after.x - prior.x, after.z - prior.z);
  const side = (index % 2 ? -1 : 1) * 1.1;
  const offset = {
    x: center.x + Math.cos(tangent) * side,
    z: center.z - Math.sin(tangent) * side,
  };
  const radius = hoofRadius(index);
  const point =
    groundBlocked(level, center, offset, radius) ||
    groundBlocked(level, actor.pos, offset, radius)
      ? center
      : offset;
  return { point, cursor, nextIndex, withinCall };
}
