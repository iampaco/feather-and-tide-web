import type { ReindeerState } from "../core/game";
import { distance } from "../core/math";
import { groundBlocked, hoofRadius } from "../levels/reindeer-ground";
import type { ReindeerLevel } from "../levels/schema";
import { REINDEER as R } from "./reindeer-tuning";
import { leaderOf } from "./world-rules";

export interface ReindeerGatherStatus {
  readonly gathered: number;
  readonly total: number;
  readonly blockedIds: readonly string[];
  readonly outOfRangeIds: readonly string[];
  readonly ready: boolean;
}

/** Calling time describes the call, never whether actual companions have arrived. */
export function reindeerGatherStatus(
  state: ReindeerState,
  level: ReindeerLevel,
): ReindeerGatherStatus {
  const leader = leaderOf(state);
  const blockedIds: string[] = [];
  const outOfRangeIds: string[] = [];
  let gathered = leader.speed === 0 ? 1 : 0;
  for (let index = 1; index < state.actors.length; index++) {
    const actor = state.actors[index];
    if (!actor) continue;
    const gap = distance(actor.pos, leader.pos);
    const blocked = groundBlocked(
      level,
      actor.pos,
      leader.pos,
      hoofRadius(index),
    );
    if (blocked) blockedIds.push(actor.id);
    if (gap > R.callRadius) outOfRangeIds.push(actor.id);
    if (!blocked && gap <= R.gatherRadius && actor.status === "following")
      gathered++;
  }
  return {
    gathered,
    total: state.actors.length,
    blockedIds,
    outOfRangeIds,
    ready:
      leader.speed === 0 &&
      gathered === R.size &&
      state.actors.length === R.size,
  };
}
