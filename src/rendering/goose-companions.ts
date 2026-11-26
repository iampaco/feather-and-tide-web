import { copy, isEnglish } from "../i18n/language";
import type { ActorState, GooseState } from "../core/game";
import type { Zone } from "../levels/schema";
import { gooseGoalBlocker } from "../simulation/world-rules";

type TimedCompanion = ActorState & { readonly rescueTicks: number };

function isTimedStray(actor: ActorState): actor is TimedCompanion {
  return actor.status === "strayed" && actor.rescueTicks !== null;
}

export function gooseRescue(state: GooseState): {
  readonly target: TimedCompanion | undefined;
  readonly count: number;
} {
  let target: TimedCompanion | undefined;
  let count = 0;
  for (const actor of state.actors) {
    if (!isTimedStray(actor)) continue;
    count++;
    // Ties keep roster order so a moving camera or leader cannot swap targets.
    if (!target || actor.rescueTicks < target.rescueTicks) target = actor;
  }
  return { target, count };
}

export function gooseLandingWait(
  state: GooseState,
  goal: Zone | undefined,
): {
  readonly target: ActorState | undefined;
  readonly action: string;
} {
  const outside = state.actors.filter(
    (actor) => gooseGoalBlocker(actor, goal) === "outside",
  );
  if (outside.length)
    return {
      target: outside[0],
      action: isEnglish()
        ? `Still outside the landing area: ${outside.length}. Slow down and let them catch up.`
        : `还有 ${outside.length} 只在落脚区外。放慢，等队尾跟上。`,
    };
  return {
    target: state.actors.find(
      (actor) => gooseGoalBlocker(actor, goal) === "rejoining",
    ),
    action: copy(
      "同伴正在跟上。保持缓行。",
      "A companion is catching up. Keep flying slowly.",
    ),
  };
}
