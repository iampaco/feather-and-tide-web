import { describe, expect, test } from "vitest";
import { FixedClock } from "../../src/core/clock";
import {
  NEUTRAL_INPUT,
  type GameEvent,
  type WorldInput,
} from "../../src/core/game";
import { GameRuntime } from "../../src/core/runtime";
import { readCheckpoint } from "../../src/core/save";
import { validateLevel } from "../../src/levels/schema";
import { angleDelta, distance } from "../../src/core/math";
import {
  GOOSE,
  headingVector,
  moveLeader,
  trailAnchor,
} from "../../src/simulation/goose";
import {
  goalStatus,
  initialState,
  leaderOf,
  rotorPhase,
  tickWorld,
} from "../../src/simulation/world";
import { writeReplay } from "../fixtures/export-replays";
import { migration, playground, trip } from "../fixtures/flight";

const forward = { move: { x: 0, z: 0.83 }, ability: false };

test("E02 same tick input, snapshots and events at 30, 60 and 120 FPS", () => {
  function replay(fps: number) {
    const runtime = new GameRuntime(playground, "journey");
    const clock = new FixedClock();
    const events: GameEvent[] = [];
    const consumed: { tick: number; used: WorldInput }[] = [];
    for (let frame = 0; runtime.current.tick < 480; frame++) {
      clock.frame((frame * 1000) / fps, true, () => {
        const t = runtime.current.tick;
        const input =
          t < 120
            ? forward
            : t < 240
              ? { ...forward, ability: true }
              : t < 360
                ? NEUTRAL_INPUT
                : { move: { x: 0.7, z: 0.6 }, ability: false };
        runtime.dispatch({ type: "input", input });
        events.push(
          ...runtime.step((tick, used) => consumed.push({ tick, used })),
        );
        return runtime.current.tick < 480;
      });
    }
    return { state: runtime.current, events, consumed };
  }
  expect(replay(30)).toEqual(replay(60));
  expect(replay(120)).toEqual(replay(60));
});

test("E02 T10 V2-17 freeze and discard backlog, first resumed frame executes no ticks", () => {
  const clock = new FixedClock();
  const runtime = new GameRuntime(playground, "journey");
  function step(): boolean {
    runtime.step();
    return true;
  }
  clock.frame(0, true, step);
  clock.frame(20_000, true, step);
  expect(runtime.current.tick).toBe(5);
  runtime.dispatch({ type: "pause" });
  const paused = runtime.current;
  expect(runtime.dispatch({ type: "pause" })).toEqual([]);
  runtime.step();
  clock.frame(90_000, false, step);
  expect(runtime.current).toBe(paused);
  runtime.dispatch({ type: "resume" });
  expect(runtime.previous).toBe(runtime.current);
  clock.frame(120_000, true, step);
  expect(runtime.current.tick).toBe(5);
  clock.frame(120_018, true, step);
  expect(runtime.current.tick).toBe(6);
});

test("E03 reports invalid versions, IDs, coordinates, polygon and references", () => {
  expect(() =>
    validateLevel({ ...migration, schemaVersion: 2 }, "fixture"),
  ).toThrow("fixture schemaVersion");
  expect(() =>
    validateLevel(
      {
        ...migration,
        landmarks: [migration.landmarks[0], migration.landmarks[0]],
      },
      "fixture",
    ),
  ).toThrow("duplicate ID");
  expect(() =>
    validateLevel({ ...migration, spawn: { x: Infinity, z: 0 } }, "fixture"),
  ).toThrow("spawn.x");
  expect(() =>
    validateLevel({ ...migration, spawnSegment: "missing" }, "fixture"),
  ).toThrow("spawnSegment");
  expect(() =>
    validateLevel(
      {
        ...migration,
        zones: [
          {
            id: "bad",
            label: "bad",
            kind: "goal",
            points: [
              { x: 0, z: 0 },
              { x: 1, z: 0 },
              { x: 0, z: 1 },
            ],
          },
        ],
      },
      "fixture",
    ),
  ).toThrow("closed");
  expect(() =>
    validateLevel(
      {
        ...migration,
        zones: migration.zones.filter((zone) => zone.kind !== "hazard"),
      },
      "fixture",
    ),
  ).toThrow("unknown hazard");
});

test("T03–T05 and V2-05 glide, turn ceiling, formation progression and release", () => {
  const runtime = new GameRuntime(playground, "journey");
  function fly(ticks: number, input = forward): void {
    runtime.dispatch({ type: "input", input });
    for (let i = 0; i < ticks; i++) runtime.step();
  }
  fly(120, { ...forward, ability: true });
  expect(runtime.current.formation).toBe(1);
  const formed = runtime.current;
  const turn = { move: { x: 0.5, z: 0.6 }, ability: true };
  const regular = moveLeader(
    leaderOf(formed),
    { ...formed, formation: 0 },
    turn,
    playground.bounds,
  );
  const v = moveLeader(leaderOf(formed), formed, turn, playground.bounds);
  expect(v.turn).toBeCloseTo(regular.turn * 0.5, 3);
  fly(1, { move: { x: 0, z: -1 }, ability: true });
  expect(runtime.current.formation).toBe(0);
  expect(Math.abs(leaderOf(runtime.current).heading)).toBeLessThan(0.031);
  fly(90);
  const beforeGlide = leaderOf(runtime.current);
  fly(59, NEUTRAL_INPUT);
  expect(leaderOf(runtime.current).heading).toBe(beforeGlide.heading);
  expect(leaderOf(runtime.current).pos.z).toBeGreaterThan(
    beforeGlide.pos.z + 5,
  );
  fly(81, NEUTRAL_INPUT);
  expect(leaderOf(runtime.current).heading).not.toBe(beforeGlide.heading);
  expect(leaderOf(runtime.current).speed).toBe(GOOSE.slow);
  for (let i = 0; i < 30; i++) {
    fly(1, { ...forward, ability: true });
    fly(1, forward);
  }
  expect(runtime.current.formation).toBe(0);
});

test("T06 and V2-14 journey energy zero safety", () => {
  const initial = initialState(migration, "journey");
  const leader = leaderOf(initial);
  function at(z: number, mode = initial.mode) {
    return {
      ...initial,
      mode,
      airborne: true,
      energy: 0,
      actors: [{ ...leader, pos: { x: 0, z } }, ...initial.actors.slice(1)],
    };
  }
  expect(
    tickWorld(at(0), NEUTRAL_INPUT, migration).state.energy,
  ).toBeGreaterThan(0);
  expect(tickWorld(at(163), NEUTRAL_INPUT, migration).state.failure).toBe(
    "energy",
  );
});

test("delayed flock anchors move between trail samples and cross the heading seam smoothly", () => {
  const sample = (tick: number) => ({
    pos: { x: 0, z: tick / 10 },
    heading: angleDelta(0, Math.PI + (tick - 17) / 20),
  });
  for (let tick = 19; tick <= 33; tick++) {
    const newest = tick - (tick % 6);
    const trail = [newest, newest - 6, newest - 12].map(sample);
    const anchor = trailAnchor(sample(tick), trail, tick, 0);
    expect(anchor.pos.z).toBeCloseTo(sample(tick - 3).pos.z, 8);
    expect(angleDelta(anchor.heading, sample(tick - 3).heading)).toBeCloseTo(
      0,
      8,
    );
  }
});

test("coincident flockmates spread out without a snap or steering the leader", () => {
  const control = new GameRuntime(playground, "journey");
  const formed = { ...forward, ability: true };
  control.dispatch({ type: "input", input: formed });
  for (let tick = 0; tick < 120; tick++) control.step();
  const state = control.current;
  const fly = new GameRuntime(playground, "journey", {
    version: 1,
    id: "start",
    state: {
      ...state,
      actors: state.actors.map((actor, index) =>
        index === 1 || index === 2
          ? { ...actor, pos: leaderOf(state).pos }
          : actor,
      ),
    },
  });
  for (let tick = 0; tick < 480; tick++) {
    const heading = tick < 120 ? 0 : tick < 240 ? 1.55 : tick < 360 ? -1.4 : 0;
    const { x, z } = headingVector(heading);
    const input = { move: { x: x * 0.72, z: z * 0.72 }, ability: tick < 120 };
    fly.dispatch({ type: "input", input });
    control.dispatch({ type: "input", input });
    fly.step();
    control.step();
    const actors = fly.current.actors;
    expect(leaderOf(fly.current)).toEqual(leaderOf(control.current));
    for (const [index, actor] of actors.entries()) {
      const before = fly.previous.actors[index];
      expect(before?.id).toBe(actor.id);
      if (!before || index === 0) continue;
      expect(distance(before.pos, actor.pos)).toBeLessThanOrEqual(0.350001);
      expect(Math.abs(actor.speed - before.speed)).toBeLessThanOrEqual(
        0.600001,
      );
    }
    if (tick === 30 || tick === 479) {
      for (const [index, actor] of actors.entries()) {
        for (const neighbor of actors.slice(0, index))
          expect(distance(actor.pos, neighbor.pos)).toBeGreaterThan(2);
      }
    }
  }
  expect(fly.current.actors).toHaveLength(12);
});

test("T12–T13 V2-13 one predicate for 11/12, rejoining, and exactly one completion", () => {
  const goal = migration.zones.find((zone) => zone.kind === "goal");
  const state = initialState(migration, "journey");
  const together = state.actors.map((actor, i) => ({
    ...actor,
    pos: { x: i, z: 826 },
  }));
  function last(status: "following" | "strayed" | "rejoining", z: number) {
    return together.map((actor, i) =>
      i === 11 ? { ...actor, status, pos: { x: 11, z } } : actor,
    );
  }
  expect(
    goalStatus({ ...state, actors: last("following", 780) }, goal),
  ).toMatchObject({ arrived: 11, leaderArrived: true, canLand: false });
  expect(
    goalStatus({ ...state, actors: last("strayed", 826) }, goal).canLand,
  ).toBe(false);
  expect(
    goalStatus({ ...state, actors: last("rejoining", 826) }, goal).canLand,
  ).toBe(false);
  const runtime = new GameRuntime(migration, "journey", {
    version: 1,
    id: "A",
    state: { ...state, actors: together },
  });
  runtime.step();
  expect(runtime.current.phase).toBe("landing");
  runtime.step();
  expect(runtime.current.tick).toBe(1);
  expect(
    runtime
      .dispatch({ type: "finishLanding" })
      .filter((event) => event.type === "completed"),
  ).toHaveLength(1);
  expect(runtime.dispatch({ type: "finishLanding" })).toEqual([]);
});

describe("T08 T11 T16, both journey routes replay to completion", () => {
  test.each([
    ["journey", "mountain"],
    ["journey", "lake"],
  ] as const)("%s %s", async (mode, route) => {
    const { runtime, input, events, strayedAt, rescuedAt } = trip(mode, route);
    expect(
      runtime.current.phase,
      JSON.stringify({
        tick: input.length,
        failure: runtime.current.failure,
        pos: leaderOf(runtime.current).pos,
        energy: runtime.current.energy,
        events: events.slice(-8),
      }),
    ).toBe("landing");
    expect(runtime.current.route).toBe(route);
    expect(runtime.current.routeLocked).toBe(true);
    expect(runtime.checkpoint.id).toBe("A");
    expect(readCheckpoint(runtime.checkpoint, migration, mode)).toEqual(
      runtime.checkpoint,
    );
    expect(strayedAt).toBeDefined();
    expect(rescuedAt).toBeDefined();
    expect((rescuedAt ?? 0) - (strayedAt ?? 0)).toBeLessThan(GOOSE.rescueTicks);
    const replay = new GameRuntime(migration, mode);
    input.forEach((command) => {
      replay.dispatch({ type: "input", input: command });
      replay.step();
    });
    expect(replay.current).toEqual(runtime.current);
    await writeReplay(`migration-${mode}-${route}`, {
      levelRevision: migration.levelRevision,
      mode,
      start: null,
      inputs: input,
      events,
      expected: runtime.current,
    });
  });
});

test("T09, T11, V2-16 rescue timeout preserves complete checkpoint and rotor phase on retry", async () => {
  const { runtime, input, strayedAt } = trip("journey", "mountain");
  const state = runtime.checkpoint.state;
  const checkpoint = runtime.checkpoint;
  const failed = new GameRuntime(migration, "journey", checkpoint);
  const consumed: WorldInput[] = [];
  const recordedEvents: { tick: number; event: GameEvent }[] = [];
  const step = () => {
    for (const event of failed.step((_, command) => consumed.push(command)))
      recordedEvents.push({ tick: failed.current.tick, event });
  };
  for (const command of input.slice(state.tick, strayedAt)) {
    failed.dispatch({ type: "input", input: command });
    step();
  }
  expect(
    failed.current.actors.some((actor) => actor.status === "strayed"),
  ).toBe(true);
  failed.dispatch({ type: "input", input: NEUTRAL_INPUT });
  while (failed.current.phase === "playing" && failed.current.tick < 7000)
    step();
  expect(failed.current.failure).toBe("rescue");
  const expected = failed.current;
  failed.dispatch({ type: "retry" });
  expect(failed.previous).toBe(failed.current);
  expect(failed.current).toEqual({ ...state, energy: 1 });
  expect(rotorPhase(failed.current.tick, 2)).toBe(rotorPhase(state.tick, 2));
  expect(
    readCheckpoint({ ...checkpoint, version: 0 }, migration, "journey"),
  ).toBeUndefined();
  expect(
    readCheckpoint(
      { ...checkpoint, state: { ...state, actors: state.actors.slice(1) } },
      migration,
      "journey",
    ),
  ).toBeUndefined();
  await writeReplay("migration-journey-rescue-timeout-retry", {
    levelRevision: migration.levelRevision,
    mode: "journey",
    start: checkpoint,
    inputs: consumed,
    events: recordedEvents,
    expected,
    retry: failed.current,
  });
});

test("T17 journey-only schema and runtime reject legacy roam", () => {
  expect(() =>
    validateLevel({ ...migration, modes: ["journey", "roam"] }, "legacy"),
  ).toThrow("modes");
  expect(() => validateLevel({ ...migration, modes: [] }, "empty")).toThrow(
    "journey only",
  );
  expect(() =>
    validateLevel({ ...migration, modes: ["journey", "journey"] }, "duplicate"),
  ).toThrow("journey only");
  expect(() => Reflect.construct(GameRuntime, [migration, "roam"])).toThrow(
    "Only journey",
  );
  const checkpoint = trip("journey", "mountain", 245).runtime.checkpoint;
  expect(readCheckpoint(checkpoint, migration, "journey")).toEqual(checkpoint);
  expect(
    readCheckpoint(
      { ...checkpoint, state: { ...checkpoint.state, mode: "roam" } },
      migration,
      "journey",
    ),
  ).toBeUndefined();
});

test("journey checkpoints reject strayed companions without rescue clocks", () => {
  const checkpoint = trip("journey", "mountain", 245).runtime.checkpoint;
  const state = checkpoint.state;
  expect(
    readCheckpoint(
      {
        ...checkpoint,
        state: {
          ...state,
          actors: state.actors.map((actor, i) =>
            i === 1
              ? { ...actor, status: "strayed", rescueTicks: null }
              : actor,
          ),
        },
      },
      migration,
      "journey",
    ),
  ).toBeUndefined();
});
