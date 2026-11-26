import { readFileSync } from "node:fs";
import {
  NEUTRAL_INPUT,
  type GameEvent,
  type GameMode,
  type GameState,
  type Route,
  type WorldInput,
} from "../../src/core/game";
import { distance, type Vec2 } from "../../src/core/math";
import { GameRuntime } from "../../src/core/runtime";
import { validateLevel, type LevelSchema } from "../../src/levels/schema";
import { leaderOf } from "../../src/simulation/world";

function fixture(id: string) {
  const file = `${id}.json`;
  return validateLevel(
    JSON.parse(
      readFileSync(
        new URL(`../../public/levels/${file}`, import.meta.url),
        "utf8",
      ),
    ),
    file,
    "goose",
  );
}

export const migration = fixture("migration");
export const playground = fixture("playground");
export const shortCourse = fixture("rules");

type StopAt = number | ((state: GameState) => boolean);
type Waypoint = Vec2 & {
  readonly power?: number;
  readonly radius?: number;
  readonly ability?: boolean;
};

export function aim(
  from: Vec2,
  to: Vec2,
  power = 0.83,
  ability = false,
): WorldInput {
  const length = distance(from, to) || 1;
  return {
    move: {
      x: ((to.x - from.x) / length) * power,
      z: ((to.z - from.z) / length) * power,
    },
    ability,
  };
}

export function wideTailwindWaypoints(
  power = 0.83,
  radius = 7,
  formation = false,
) {
  return [
    { x: 0, z: 130, power, radius, ability: formation },
    { x: -28, z: 164, power, radius, ability: false },
    { x: -28, z: 200, power, radius, ability: formation },
    { x: 0, z: 212, power, radius, ability: false },
  ] as const;
}

export function trip(mode: GameMode, route: Route, stopAt: StopAt = Infinity) {
  const routeX = route === "mountain" ? -30 : 59;
  return flyCourse(
    migration,
    mode,
    [
      ...wideTailwindWaypoints(0.83, 7, true),
      { x: routeX, z: 272 },
      { x: routeX, z: 357 },
      { x: 0, z: 455 },
      { x: -55, z: 532 },
      { x: -55, z: 653 },
      { x: 0, z: 716 },
      { x: 0, z: 853 },
    ],
    stopAt,
  );
}

export function shortTrip(mode: GameMode) {
  return flyCourse(shortCourse, mode, [
    { x: 0, z: 80 },
    { x: -27, z: 128 },
    { x: -42, z: 171 },
    { x: -42, z: 221 },
    { x: -12, z: 255 },
    { x: 0, z: 264 },
  ]);
}

export function flyCourse(
  level: LevelSchema,
  mode: GameMode,
  points: readonly [Waypoint, ...Waypoint[]],
  stopAt: StopAt = Infinity,
  restored?: GameRuntime["checkpoint"],
) {
  const runtime = new GameRuntime(level, mode, restored);
  const input: WorldInput[] = [];
  const events: { tick: number; event: GameEvent }[] = [];
  let next = 0;
  let waiting = false;
  let rescuedAt: number | undefined;
  let strayedAt: number | undefined;
  while (runtime.current.phase === "playing" && runtime.current.tick < 15_000) {
    const state = runtime.current;
    const leader = leaderOf(state);
    if (typeof stopAt === "number" ? leader.pos.z >= stopAt : stopAt(state))
      break;
    const waypoint = points[next];
    if (
      waypoint &&
      distance(leader.pos, waypoint) < (waypoint.radius ?? 7) &&
      next < points.length - 1
    )
      next++;
    const target = points[next] ?? points[0];
    waiting ||=
      next === points.length - 1 &&
      level.id === "rules" &&
      distance(leader.pos, target) < 8;
    const strayed = state.actors.find((actor) => actor.status === "strayed");
    const nearby = strayed && distance(leader.pos, strayed.pos) < 12;
    const command =
      strayed && mode === "journey"
        ? aim(leader.pos, strayed.pos, nearby ? 0.09 : 0.45)
        : waiting
          ? NEUTRAL_INPUT
          : aim(
              leader.pos,
              target,
              target.power ?? 0.83,
              target.ability ??
                ((state.segmentId === "S1" && leader.pos.z < 180) ||
                  state.segmentId === "S5"),
            );
    runtime.dispatch({ type: "input", input: command });
    for (const event of runtime.step((_, used) => input.push(used))) {
      events.push({ tick: runtime.current.tick, event });
      if (event.type === "strayed") strayedAt = runtime.current.tick;
      if (event.type === "rejoined") rescuedAt = runtime.current.tick;
    }
  }
  return { runtime, input, events, strayedAt, rescuedAt };
}
