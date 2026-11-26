import { readFileSync } from "node:fs";
import type {
  CheckpointSnapshot,
  GameEvent,
  ReindeerRoute,
  ReindeerState,
  WorldInput,
} from "../../src/core/game";
import { NEUTRAL_INPUT } from "../../src/core/game";
import { distance, type Vec2 } from "../../src/core/math";
import { GameRuntime } from "../../src/core/runtime";
import { validateLevel } from "../../src/levels/schema";
import { reindeerGatherStatus } from "../../src/simulation/reindeer-care";
import { sampleReindeerDust } from "../../src/simulation/reindeer-dust";
import { initialState } from "../../src/simulation/world";
import { leaderOf } from "../../src/simulation/world-rules";

export const reindeerSource: unknown = JSON.parse(
  readFileSync(
    new URL("../../public/levels/reindeer.json", import.meta.url),
    "utf8",
  ),
);
export const reindeerLevel = validateLevel(
  reindeerSource,
  "reindeer.json",
  "reindeer",
);

export function herdAt(
  pos: Vec2,
  patch: Partial<ReindeerState> = {},
): ReindeerState {
  const state = initialState(reindeerLevel, "journey");
  const shift = (p: Vec2) => ({
    x: p.x - reindeerLevel.spawn.x + pos.x,
    z: p.z - reindeerLevel.spawn.z + pos.z,
  });
  return {
    ...state,
    actors: state.actors.map((actor) => ({ ...actor, pos: shift(actor.pos) })),
    trail: state.trail.map(shift),
    ...patch,
  };
}

export function moveTo(pos: Vec2, goal: Vec2, speed = 0.84): WorldInput {
  const size = distance(pos, goal);
  return size
    ? {
        move: {
          x: ((goal.x - pos.x) / size) * speed,
          z: ((goal.z - pos.z) / size) * speed,
        },
        ability: false,
      }
    : NEUTRAL_INPUT;
}

export function reindeerTrip(
  route: ReindeerRoute,
  phaseTicks = 0,
  observeDust = true,
  fence: "wide" | "short" = "wide",
) {
  const waypoints = [
    { x: -16, z: 63 },
    { x: -13.5, z: 103 },
    { x: -13.5, z: 151 },
    { x: 0, z: 195 },
    ...(fence === "short"
      ? (reindeerLevel.trails
          .find(({ id }) => id === "trail-fence-short")
          ?.points.slice(1, -1) ?? [])
      : [
          { x: 17, z: 253 },
          { x: 17, z: 279 },
          { x: -6, z: 285 },
          { x: -6, z: 302 },
          { x: 17, z: 308 },
          { x: 17, z: 323 },
        ]),
    { x: 0, z: 337 },
    ...(route === "greenbelt"
      ? [
          { x: -47, z: 361 },
          { x: -47, z: 400 },
          { x: -18, z: 406 },
          { x: -18, z: 451 },
        ]
      : [
          { x: 17, z: 353 },
          { x: 17, z: 403 },
          { x: 17, z: 451 },
        ]),
    { x: 0, z: 482 },
    { x: 0, z: 533 },
    { x: 12, z: 545 },
    { x: 0, z: 559 },
    { x: 0, z: 579 },
  ];
  const level = {
    ...reindeerLevel,
    dustCycle: { ...reindeerLevel.dustCycle, phaseTicks },
  };
  const runtime = new GameRuntime(level, "journey");
  const inputs: WorldInput[] = [];
  const checkpoints: CheckpointSnapshot[] = [];
  const events: { tick: number; event: GameEvent }[] = [];
  let next = 0;
  for (
    let step = 0;
    step < 25_000 && runtime.current.phase === "playing";
    step++
  ) {
    const leader = leaderOf(runtime.current);
    const target = waypoints[next];
    if (!target) break;
    const arrived = distance(leader.pos, target) < 1.1;
    const dust = sampleReindeerDust(level, runtime.current.tick, leader.pos);
    const atDustStop =
      observeDust &&
      route === "dust" &&
      arrived &&
      (target.z === 353 || target.z === 403);
    const waitForDust =
      atDustStop &&
      (!reindeerGatherStatus(runtime.current, level).ready ||
        dust.phase !== "calm" ||
        dust.remainingTicks < 18.5 * 60);
    if (arrived && !waitForDust && next < waypoints.length - 1) next++;
    const input = waitForDust
      ? { ...NEUTRAL_INPUT, ability: true }
      : arrived && next === waypoints.length - 1 && waypoints[next] === target
        ? NEUTRAL_INPUT
        : moveTo(leader.pos, waypoints[next] ?? target);
    runtime.dispatch({ type: "input", input });
    for (const event of runtime.step((_, command) => inputs.push(command))) {
      events.push({ tick: runtime.current.tick, event });
      if (event.type === "checkpoint") checkpoints.push(runtime.checkpoint);
    }
  }
  return { runtime, inputs, checkpoints, events };
}
