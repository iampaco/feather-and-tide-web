import type {
  ActorState,
  GameEvent,
  GameState,
  WhaleActor,
} from "../core/game";
import { contains } from "../levels/geometry";
import type { Zone } from "../levels/schema";
import { GOOSE } from "./goose";
import { WHALE } from "./whale-motion";
import { REINDEER } from "./reindeer-tuning";

const rosterSizes = {
  goose: GOOSE.size,
  whale: WHALE.size,
  reindeer: REINDEER.size,
};

export const MODE_RULES = {
  journey: {
    canFail: true,
    contactCost: true,
    timedRescue: true,
    fatigueFloor: 0,
  },
} as const;

export function leaderOf<A extends ActorState>(state: {
  readonly actors: readonly A[];
  readonly leaderId: string;
}): A {
  const leader = state.actors[0];
  if (!leader || leader.id !== state.leaderId)
    throw new Error("Missing leader");
  return leader;
}

export function surfaced(actor: WhaleActor): boolean {
  return actor.dive.layer === "surface" && actor.dive.direction === null;
}

export function whaleSupplyStatus(
  leader: WhaleActor,
  actors: readonly WhaleActor[],
  zone: Zone,
): { arrived: number; required: number; inside: boolean; ready: boolean } {
  const arrived = actors.filter(
    (actor) => actor.status !== "strayed" && contains(zone.points, actor.pos),
  ).length;
  const required = Math.floor(actors.length / 2) + 1;
  const inside = contains(zone.points, leader.pos);
  return {
    arrived,
    required,
    inside,
    ready: inside && surfaced(leader) && arrived >= required,
  };
}

type GooseGoalBlocker = "strayed" | "rejoining" | "outside";
type WhaleGoalBlocker = GooseGoalBlocker | "submerged";

export function gooseGoalBlocker(
  actor: ActorState,
  goal: Zone | undefined,
): GooseGoalBlocker | null {
  if (actor.status === "strayed" || actor.status === "rejoining")
    return actor.status;
  return goal && contains(goal.points, actor.pos) ? null : "outside";
}

export function whaleGoalBlocker(
  actor: WhaleActor,
  goal: Zone | undefined,
): WhaleGoalBlocker | null {
  if (actor.status === "strayed" || actor.status === "rejoining")
    return actor.status;
  if (!goal || !contains(goal.points, actor.pos)) return "outside";
  return surfaced(actor) ? null : "submerged";
}

export function goalStatus(
  state:
    | Pick<
        Extract<GameState, { species: "goose" | "reindeer" }>,
        "species" | "actors" | "leaderId"
      >
    | Pick<
        Extract<GameState, { species: "whale" }>,
        "species" | "actors" | "leaderId"
      >,
  goal: Zone | undefined,
): {
  arrived: number;
  expected: number;
  leaderArrived: boolean;
  canLand: boolean;
} {
  const readyActors =
    state.species === "whale"
      ? state.actors.filter((actor) => whaleGoalBlocker(actor, goal) === null)
      : state.actors.filter((actor) => gooseGoalBlocker(actor, goal) === null);
  const arrived = readyActors.length;
  const leader = readyActors.find(({ id }) => id === state.leaderId);
  const leaderArrived = leader !== undefined;
  const expected = rosterSizes[state.species];
  const settled =
    state.species !== "whale" ||
    goal?.kind !== "goal" ||
    (leader !== undefined && leader.speed <= WHALE.reunionSpeed);
  return {
    arrived,
    expected,
    leaderArrived,
    canLand:
      settled &&
      leaderArrived &&
      state.actors.length === expected &&
      arrived === expected,
  };
}

export interface TickResult<S extends GameState = GameState> {
  readonly state: S;
  readonly events: readonly GameEvent[];
  readonly checkpoint: string | null;
}
