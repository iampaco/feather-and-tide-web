import { readFileSync } from "node:fs";
import {
  NEUTRAL_INPUT,
  type CheckpointSnapshot,
  type GameEvent,
  type GameMode,
  type WhaleRoute,
  type WhaleState,
  type WorldInput,
} from "../../src/core/game";
import { angleDelta, distance, type Vec2 } from "../../src/core/math";
import { GameRuntime } from "../../src/core/runtime";
import { validateLevel } from "../../src/levels/schema";
import { hazardPoints } from "../../src/levels/whale-geometry";
import { netApproaches } from "../../src/levels/whale-net";
import { WHALE } from "../../src/simulation/whale-motion";
import { initialState } from "../../src/simulation/world";
import { surfaced } from "../../src/simulation/world-rules";
import { aim } from "./flight";

export const whaleSource: unknown = JSON.parse(
  readFileSync(
    new URL("../../public/levels/whale.json", import.meta.url),
    "utf8",
  ),
);
export const whaleLevel = validateLevel(whaleSource, "whale.json", "whale");
export const forwardSwim: WorldInput = {
  move: { x: 0, z: 0.83 },
  ability: false,
};

export const shippingApproach = [
  "ship-bend-in",
  "ship-bend-out",
  "ship-dive",
].map((id) => {
  const marker = whaleLevel.landmarks.find((candidate) => candidate.id === id);
  if (!marker) throw new Error(`Missing shipping approach marker ${id}`);
  return marker.pos;
});

export function podAt(
  pos: Vec2,
  mode: GameMode = "journey",
  tick = 0,
): WhaleState {
  const state = initialState(whaleLevel, mode);
  const actors = state.actors.map((actor) => ({
    ...actor,
    pos: {
      x: actor.pos.x - whaleLevel.spawn.x + pos.x,
      z: actor.pos.z - whaleLevel.spawn.z + pos.z,
    },
  }));
  return { ...state, tick, actors };
}

export function whaleState(state: GameRuntime["current"]): WhaleState {
  if (state.species !== "whale") throw new Error("Expected whale state");
  return state;
}

export function podLeader(state: WhaleState): WhaleState["actors"][number] {
  const actor = state.actors[0];
  if (!actor) throw new Error("Missing leader");
  return actor;
}

type InputPlan = (state: WhaleState) => WorldInput;
type End = (state: WhaleState) => boolean;

function capture(
  mode: GameMode,
  plan: InputPlan,
  end: End = ({ phase }) => phase !== "playing",
  start: CheckpointSnapshot | null = null,
) {
  const runtime = new GameRuntime(whaleLevel, mode, start ?? undefined);
  const inputs: WorldInput[] = [];
  const events: { tick: number; event: GameEvent }[] = [];
  const checkpoints: CheckpointSnapshot[] = [];
  for (let step = 0; step < 29_000; step++) {
    const state = whaleState(runtime.current);
    if (state.phase !== "playing" || end(state)) break;
    runtime.dispatch({ type: "input", input: plan(state) });
    const emitted = runtime.step((_, used) => inputs.push(used));
    for (const event of emitted) {
      events.push({ tick: runtime.current.tick, event });
      if (event.type === "checkpoint") checkpoints.push(runtime.checkpoint);
    }
  }
  return {
    runtime,
    inputs,
    events,
    checkpoints,
    start,
    mode,
    levelRevision: whaleLevel.levelRevision,
    expected: whaleState(runtime.current),
  };
}

export function whaleTrip(mode: GameMode, route: WhaleRoute) {
  const waypoints = [
    { x: 0, z: 270 },
    ...shippingApproach,
    { x: 0, z: 567 },
    { x: 124, z: 709 },
    { x: 124, z: 858 },
    { x: 65, z: 970 },
    ...(route === "quiet"
      ? [
          { x: -93, z: 1030 },
          { x: -82, z: 1114 },
          { x: -109, z: 1165 },
          { x: -78, z: 1219 },
        ]
      : [{ x: 60, z: 1140 }]),
    { x: 65, z: 1307 },
    { x: 65, z: 1385 },
    { x: 80, z: 1559 },
  ];
  let next = 0;
  return capture(mode, (state) => {
    const leader = podLeader(state);
    const current = waypoints[next];
    if (!current) throw new Error("No course waypoint");
    if (distance(leader.pos, current) < 5 && next < waypoints.length - 1)
      next++;
    const target = waypoints[next] ?? current;
    return next === waypoints.length - 1 && distance(leader.pos, target) < 4
      ? NEUTRAL_INPUT
      : aim(
          leader.pos,
          target,
          0.83,
          leader.pos.z >= 370 && leader.pos.z < 457,
        );
  });
}

export function bayPassage(practice: boolean) {
  const inner = whaleLevel.landmarks.find(({ id }) => id === "bay-bend-entry");
  const bend = whaleLevel.landmarks.find(({ id }) => id === "bay-stop");
  const exit = whaleLevel.landmarks.find(({ id }) => id === "ship-wait");
  const w1 = whaleLevel.segments.find(({ id }) => id === "W1");
  if (!inner || !bend || !exit || !w1) throw new Error("Missing bay course");
  let coasting = false;
  let inBay = false;
  let diveStart: number | undefined;
  let outbound = !practice;
  return capture(
    "journey",
    (state) => {
      const leader = podLeader(state);
      if (!outbound) {
        inBay ||= distance(leader.pos, inner.pos) < 5;
        if (!inBay) return aim(leader.pos, inner.pos, 0.83);
        coasting ||= distance(leader.pos, bend.pos) < 6;
        if (!coasting) return aim(leader.pos, bend.pos, 0.83);
        if (leader.speed > 0) return NEUTRAL_INPUT;
        diveStart ??= state.tick;
        const ability = state.tick - diveStart < WHALE.diveTicks[0] + 78;
        if (ability) return { ...NEUTRAL_INPUT, ability };
        outbound = state.actors.every(
          (actor) => surfaced(actor) && actor.dive.breath === 1,
        );
        if (!outbound) return NEUTRAL_INPUT;
      }
      return aim(leader.pos, exit.pos, 0.83);
    },
    ({ actors }) => actors.every(({ pos }) => pos.z >= w1.start),
  );
}

export function shipCrossing(dive: boolean) {
  const ship = whaleLevel.zones.find(
    (zone) => zone.kind === "hazard" && zone.id === "cargo-ship",
  );
  if (!ship || ship.kind !== "hazard") throw new Error("Missing ship");
  const state = podAt({ x: 0, z: 380 }, "journey", 3310);
  return capture(
    "journey",
    (current) => {
      const leader = podLeader(current);
      if (
        !dive &&
        Math.max(...hazardPoints(ship, current.tick).map((point) => point.x)) >
          -24
      )
        return NEUTRAL_INPUT;
      return {
        ...forwardSwim,
        ability: dive && leader.pos.z < 457,
      };
    },
    (current) => current.triggered.includes("C1"),
    { version: 1, id: "start", state },
  );
}

const netMistake = [
  { x: 0, z: 567 },
  { x: 5, z: 672 },
  { x: 70, z: 709 },
  { x: 33, z: 828 },
] as const;

export const netRecoveryBend = [
  { x: 75, z: 806 },
  { x: 75, z: 737 },
] as const;

function followWaypoints(
  points: readonly Vec2[],
  throttle: number,
  cutoff = 5,
) {
  let next = 0;
  return (leader: Vec2) => {
    const point = points[next];
    if (!point) throw new Error("Missing W2 waypoint");
    if (next < points.length - 1 && distance(leader, point) < cutoff) next++;
    return aim(leader, points[next] ?? point, throttle);
  };
}

export function netApproachForBrowser(start: CheckpointSnapshot) {
  const approach = followWaypoints(netMistake, 1);
  return capture(
    "journey",
    (state) => approach(podLeader(state).pos),
    (state) =>
      state.occupied.includes("drift-net") && podLeader(state).pos.z >= 775.9,
    start,
  ).expected;
}

export function netPassageFromC1(
  start: CheckpointSnapshot,
  path: "wide" | "short" | "rescue",
  end: End = (state) =>
    state.segmentId === "W3" &&
    state.actors.every(({ status }) => status === "following"),
) {
  const waypoints = [
    ...netApproaches[path === "short" ? "short" : "wide"],
    "branch-overlook",
  ].map((id) => {
    const mark = whaleLevel.landmarks.find((mark) => mark.id === id);
    if (!mark) throw new Error(`Missing ${id} on the W2 path`);
    return mark.pos;
  });
  const outbound = followWaypoints(waypoints, 0.83);
  const approach = followWaypoints(netMistake, 1);
  const clear = followWaypoints(
    [
      { x: 124, z: 715 },
      { x: 124, z: 838 },
      { x: 102, z: 940 },
    ],
    0.83,
    6,
  );
  let lost = false;
  let corner = 0;
  return capture(
    "journey",
    (state) => {
      const leader = podLeader(state).pos;
      if (path !== "rescue") {
        const input = outbound(leader);
        return path === "short" && leader.z >= 723 && leader.z < 774
          ? {
              ...input,
              move: { x: input.move.x * 0.68, z: input.move.z * 0.68 },
            }
          : input;
      }
      const missing = state.actors.find(({ status }) => status === "strayed");
      if (missing) {
        lost = true;
        const point = netRecoveryBend[corner];
        if (point && distance(leader, point) < 4) corner++;
        const next = netRecoveryBend[corner];
        if (next) return aim(leader, next, 0.65);
        return distance(leader, missing.pos) <= 6
          ? NEUTRAL_INPUT
          : aim(leader, missing.pos, 0.4);
      }
      if (!lost) return approach(leader);
      if (state.actors.some(({ status }) => status === "rejoining"))
        return NEUTRAL_INPUT;
      return clear(leader);
    },
    end,
    start,
  );
}

export function kelpForkFromC1(start: CheckpointSnapshot) {
  return netPassageFromC1(
    start,
    "short",
    (state) =>
      podLeader(state).pos.z >= 815 &&
      state.actors.every(({ pos }) => pos.z > 780),
  );
}

export function whaleFailure(
  checkpoint: CheckpointSnapshot,
  failure: "rescue" | "energy",
) {
  const mode = checkpoint.state.mode;
  let circling = false;
  const approach = followWaypoints(netMistake, 1);
  return capture(
    mode,
    (state) => {
      const leader = podLeader(state);
      if (failure === "energy") {
        // Keep swimming in the open channel between two rest waters.
        circling ||= leader.pos.z >= 1431;
        if (circling) {
          const bearing = angleDelta(0, leader.heading + Math.PI / 3);
          return {
            move: { x: Math.sin(bearing), z: Math.cos(bearing) },
            ability: false,
          };
        }
        return aim(leader.pos, { x: 65, z: 1437 }, 1);
      }
      return state.actors.some(({ status }) => status === "strayed")
        ? NEUTRAL_INPUT
        : approach(leader.pos);
    },
    undefined,
    checkpoint,
  );
}
