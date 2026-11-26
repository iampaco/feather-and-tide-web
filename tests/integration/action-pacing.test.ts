import { expect, test } from "vitest";
import {
  freshGooseTeaching,
  gooseTeaching,
} from "../../src/app/goose-teaching";
import {
  reindeerDustGuidance,
  reindeerWinterBend,
} from "../../src/app/reindeer-guidance";
import { whaleGuidance } from "../../src/app/whale-guidance";
import { FixedClock } from "../../src/core/clock";
import {
  NEUTRAL_INPUT,
  type GameEvent,
  type ReindeerState,
  type WorldInput,
} from "../../src/core/game";
import { distance } from "../../src/core/math";
import { GameRuntime } from "../../src/core/runtime";
import { DEFAULT_SETTINGS } from "../../src/input/input";
import type { AnyLevelSchema } from "../../src/levels/schema";
import { WHALE } from "../../src/simulation/whale-motion";
import { goalStatus, leaderOf, tickWorld } from "../../src/simulation/world";
import { aim, migration, trip } from "../fixtures/flight";
import {
  herdAt,
  moveTo,
  reindeerLevel,
  reindeerTrip,
} from "../fixtures/reindeer";
import {
  forwardSwim,
  podAt,
  shippingApproach,
  whaleLevel,
  whaleTrip,
} from "../fixtures/whale";

const journeys = [
  [
    "goose mountain",
    () => {
      const run = trip("journey", "mountain");
      return { ...run, inputs: run.input };
    },
  ],
  [
    "goose lake",
    () => {
      const run = trip("journey", "lake");
      return { ...run, inputs: run.input };
    },
  ],
  ["whale shipping", () => whaleTrip("journey", "shipping")],
  ["whale quiet", () => whaleTrip("journey", "quiet")],
  ["reindeer dust", () => reindeerTrip("dust", 0, true, "short")],
  ["reindeer greenbelt", () => reindeerTrip("greenbelt", 0, true, "short")],
] as const;

test("each opening shows a steering choice within twelve seconds at cruise", () => {
  const goose = new GameRuntime(migration, "journey");
  const whale = new GameRuntime(whaleLevel, "journey");
  const reindeer = new GameRuntime(reindeerLevel, "journey");
  const seen = { goose: false, whale: false, reindeer: false };
  for (const runtime of [goose, whale, reindeer])
    runtime.dispatch({ type: "input", input: forwardSwim });
  for (let tick = 0; tick < 12 * 60; tick++) {
    for (const runtime of [goose, whale, reindeer]) runtime.step();
    seen.goose ||=
      gooseTeaching(freshGooseTeaching, {
        enabled: true,
        state: goose.current,
        level: migration,
        leaderZ: leaderOf(goose.current).pos.z,
        touch: true,
        settings: DEFAULT_SETTINGS,
        abilityHeld: false,
        cameraDragDistance: 0,
        seenReset: false,
        inWind: false,
      }).cue?.id === "island-glide";
    seen.whale ||= whaleGuidance(whale.current, whaleLevel, true, {
      moved: true,
      stopped: false,
      dragged: false,
      reset: false,
      submerged: false,
      recovered: false,
      toggle: false,
      desktop: false,
    }).markers.some(({ id }) => id === "bay-surface-turn");
    seen.reindeer ||= reindeerWinterBend(reindeer.current, reindeerLevel);
  }
  expect(seen).toEqual({ goose: true, whale: true, reindeer: true });
});

function replay(
  level: AnyLevelSchema,
  inputs: readonly WorldInput[],
  fps: number,
) {
  const clock = new FixedClock();
  const runtime = new GameRuntime(level, "journey");
  const events: { tick: number; event: GameEvent }[] = [];
  const frameLimit = Math.ceil((inputs.length * fps) / 60) + 4;
  for (
    let frame = 0;
    runtime.current.tick < inputs.length && frame < frameLimit;
    frame++
  ) {
    clock.frame(
      (frame * 1000) / fps,
      runtime.current.phase === "playing",
      () => {
        const input = inputs[runtime.current.tick];
        if (!input) return false;
        runtime.dispatch({ type: "input", input });
        for (const event of runtime.step())
          events.push({ tick: runtime.current.tick, event });
        return runtime.current.phase === "playing";
      },
    );
  }
  return { current: runtime.current, checkpoint: runtime.checkpoint, events };
}

test.each(journeys)(
  "%s completes with identical state and events at 30, 60 and 120 FPS",
  (_, drive) => {
    const { runtime, inputs, events } = drive();
    const goal = runtime.level.zones.find(({ kind }) => kind === "goal");
    expect(runtime.current.phase).toBe("landing");
    expect(goalStatus(runtime.current, goal).canLand).toBe(true);
    for (const fps of [30, 60, 120]) {
      expect(replay(runtime.level, inputs, fps)).toEqual({
        current: runtime.current,
        checkpoint: runtime.checkpoint,
        events,
      });
    }
  },
);

test("W1 warns before a straight approach stalls and steering clears the breakwater for all six", () => {
  const bank = whaleLevel.zones.find(
    ({ id }) => id === "ship-approach-breakwater",
  );
  const warning = whaleLevel.zones.find(
    ({ id }) => id === "ship-approach-breakwater-warning",
  );
  if (!bank || !warning)
    throw new Error("Missing shipping approach collision and warning");
  const near = Math.min(...bank.points.map(({ z }) => z));
  const far = Math.max(...bank.points.map(({ z }) => z));
  const warningStart = Math.min(...warning.points.map(({ z }) => z));
  expect(
    (near - WHALE.hitRadius - warningStart) / WHALE.cruise,
  ).toBeGreaterThanOrEqual(3);
  const start = {
    version: 1 as const,
    id: "start",
    state: podAt({ x: 0, z: warningStart }),
  };
  const straight = new GameRuntime(whaleLevel, "journey", start);
  straight.dispatch({ type: "input", input: forwardSwim });
  for (let tick = 0; tick < 360; tick++) straight.step();
  expect(straight.current.occupied).toContain(bank.id);
  expect(leaderOf(straight.current).pos.z).toBeLessThan(near);
  expect(straight.current.energy).toBe(1);

  let next = 0;
  const bend = new GameRuntime(whaleLevel, "journey", start);
  for (
    let tick = 0;
    tick < 1000 &&
    bend.current.actors.some(({ pos }) => pos.z < far + WHALE.hitRadius);
    tick++
  ) {
    const { pos } = leaderOf(bend.current);
    const mark = shippingApproach[next];
    if (!mark) throw new Error("Missing approach marker");
    if (next < shippingApproach.length - 1 && distance(pos, mark) < 4) next++;
    bend.dispatch({
      type: "input",
      input: aim(pos, shippingApproach[next] ?? mark, 0.83),
    });
    bend.step();
    expect(bend.current.occupied).not.toContain(bank.id);
  }
  expect(
    bend.current.actors.filter(({ pos }) => pos.z >= far + WHALE.hitRadius),
  ).toHaveLength(6);
});

const dustLine = [
  { x: 17, z: 353 },
  { x: 17, z: 401 },
  { x: 17, z: 453 },
  { x: 0, z: 482 },
];
const greenbelt = [
  { x: -47, z: 361 },
  { x: -47, z: 400 },
  { x: -18, z: 406 },
  { x: -18, z: 451 },
  { x: 0, z: 482 },
];

function crossMine(start: ReindeerState, takeDust: boolean): number {
  const points = takeDust ? dustLine : greenbelt;
  let state = start;
  let next = 0;
  let waiting = false;
  while (state.tick - start.tick < 7200) {
    const { pos } = leaderOf(state);
    const target = points[next];
    if (!target) break;
    if (waiting || distance(pos, target) < 1.3) {
      waiting =
        takeDust &&
        next < 2 &&
        !reindeerDustGuidance(state, reindeerLevel)?.detail.includes(
          "现在可出发",
        );
      if (!waiting) next++;
    }
    const point = points[next];
    if (!point) break;
    const input = waiting
      ? { ...NEUTRAL_INPUT, ability: true }
      : moveTo(pos, point);
    state = tickWorld(state, input, reindeerLevel).state;
  }
  expect(next).toBe(points.length);
  expect(
    state.actors.filter(({ status }) => status === "following"),
  ).toHaveLength(9);
  return state.tick - start.tick;
}

test("R3 the timed shortcut rewards a favorable phase and the greenbelt wins when the window is poor", () => {
  const fork = herdAt(
    { x: 0, z: 337 },
    { segmentId: "R3", triggered: ["C1"], energy: 0.8 },
  );
  const favorable = { ...fork, tick: 2040 };
  expect(crossMine(favorable, true)).toBeLessThan(
    crossMine(favorable, false) - 180,
  );
  expect(crossMine(fork, false)).toBeLessThan(crossMine(fork, true));
});
