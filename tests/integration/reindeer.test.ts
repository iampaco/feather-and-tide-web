import { writeReplay } from "../fixtures/export-replays";
import { expect, test } from "vitest";
import { reindeerTeammateGuidance } from "../../src/app/reindeer-guidance";
import { FixedClock, STEP_SEC } from "../../src/core/clock";
import {
  NEUTRAL_INPUT,
  type ReindeerState,
  type WorldInput,
} from "../../src/core/game";
import { distance } from "../../src/core/math";
import { GameRuntime } from "../../src/core/runtime";
import { readCheckpoint, readRunRecord } from "../../src/core/save";
import { contains } from "../../src/levels/geometry";
import { hazardPoints } from "../../src/levels/moving-hazard";
import {
  groundHeight,
  groundMove,
  hoofRadius,
  onRoad,
  roadVehicle,
} from "../../src/levels/reindeer-ground";
import { validateLevel } from "../../src/levels/schema";
import { REINDEER } from "../../src/simulation/reindeer-tuning";
import { goalStatus, leaderOf, tickWorld } from "../../src/simulation/world";
import {
  herdAt,
  moveTo,
  reindeerLevel,
  reindeerSource,
  reindeerTrip,
} from "../fixtures/reindeer";

const forward = { move: { x: 0, z: 0.84 }, ability: false };
const call = { ...NEUTRAL_INPUT, ability: true };

function followRecordedInputs(
  runtime: GameRuntime<typeof reindeerLevel>,
  inputs: readonly WorldInput[],
): void {
  for (const input of inputs) {
    if (runtime.current.phase !== "playing") return;
    runtime.dispatch({ type: "input", input });
    runtime.step();
  }
}

test("RD-A01 RD-A03 T21 walking, braking, stopping, calling and release", () => {
  let state = herdAt({ x: 0, z: 19 });
  for (let i = 0; i < 120; i++)
    state = tickWorld(state, forward, reindeerLevel).state;
  expect(leaderOf(state).speed).toBeCloseTo(REINDEER.cruise);
  const release = leaderOf(state).pos;
  for (let i = 0; i < 30; i++)
    state = tickWorld(state, NEUTRAL_INPUT, reindeerLevel).state;
  const stopped = leaderOf(state);
  expect(distance(stopped.pos, release)).toBeGreaterThan(0);
  expect(distance(stopped.pos, release)).toBeLessThan(0.8);
  expect(stopped.speed).toBe(0);
  const tail = state.actors.at(-1)!;
  const held: WorldInput = { move: { x: 0.84, z: 0 }, ability: true };
  for (let i = 0; i < REINDEER.waitTicks; i++)
    state = tickWorld(state, held, reindeerLevel).state;
  expect(state.waitTicks).toBe(REINDEER.waitTicks);
  expect(leaderOf(state).pos).toEqual(stopped.pos);
  expect(leaderOf(state).heading).toBeCloseTo(Math.PI / 2);
  expect(distance(state.actors.at(-1)!.pos, stopped.pos)).toBeLessThan(
    distance(tail.pos, stopped.pos),
  );
  expect(state.actors.map(({ id }) => id)).toHaveLength(9);
  state = tickWorld(state, NEUTRAL_INPUT, reindeerLevel).state;
  expect(state.waitTicks).toBe(0);
  expect(leaderOf(state).pos).toEqual(stopped.pos);
});

test("RD-A02 deterministic controls at 30/60/120 Hz and a frozen pause", () => {
  const run = (fps: number) => {
    const runtime = new GameRuntime(reindeerLevel, "journey");
    const clock = new FixedClock();
    clock.frame(0, true, () => true);
    for (let frame = 1; runtime.current.tick < 330; frame++)
      clock.frame((frame * 1000) / fps, true, () => {
        if (runtime.current.tick >= 330) return false;
        runtime.dispatch({
          type: "input",
          input: runtime.current.tick < 180 ? forward : call,
        });
        runtime.step();
        return runtime.current.tick < 330;
      });
    const played = runtime.current;
    runtime.dispatch({ type: "pause" });
    expect(runtime.step()).toEqual([]);
    expect(runtime.current).toEqual({ ...played, phase: "paused" });
    return played;
  };
  expect(run(30)).toEqual(run(60));
  expect(run(120)).toEqual(run(60));
});

test("R0 Wait brakes on the current heading before letting the leader turn in place", () => {
  let state = herdAt({ x: 0, z: 19 });
  for (let i = 0; i < 70; i++)
    state = tickWorld(
      state,
      { move: { x: 0, z: 1 }, ability: false },
      reindeerLevel,
    ).state;
  const start = leaderOf(state);
  expect(start.speed).toBeCloseTo(REINDEER.run);
  const held = { move: { x: 1, z: 0 }, ability: true };
  const stoppingTicks = Math.ceil(
    start.speed / (REINDEER.waitBraking * STEP_SEC),
  );
  for (let i = 0; i < stoppingTicks; i++) {
    const prior = leaderOf(state);
    state = tickWorld(state, held, reindeerLevel).state;
    const leader = leaderOf(state);
    expect(leader.pos.x).toBeCloseTo(start.pos.x);
    expect(leader.speed).toBeLessThan(prior.speed);
    if (leader.speed) expect(leader.heading).toBe(start.heading);
  }
  const stopped = leaderOf(state);
  expect(stopped.speed).toBe(0);
  expect(distance(start.pos, stopped.pos)).toBeLessThan(1.15);
  for (let i = 0; i < 24; i++)
    state = tickWorld(state, held, reindeerLevel).state;
  expect(leaderOf(state).heading).toBeCloseTo(Math.PI / 2);
  expect(leaderOf(state).pos).toEqual(stopped.pos);
  state = tickWorld(state, NEUTRAL_INPUT, reindeerLevel).state;
  expect(state.waitTicks).toBe(0);
  expect(leaderOf(state).pos).toEqual(stopped.pos);
});

test("RD-A05 T22 driving lane refuses wait while the culvert is traversable under a moving car", () => {
  const lane = herdAt({ x: 3, z: 125 }, { tick: 300 });
  const command = { ...forward, ability: true };
  const next = tickWorld(lane, command, reindeerLevel).state;
  expect(onRoad(reindeerLevel.road, leaderOf(lane).pos)).toBe(true);
  expect(next.waitBlocked).toBe(true);
  expect(next.waitTicks).toBe(0);
  expect(leaderOf(next).pos.z).toBeGreaterThan(125);
  expect(hazardPoints(roadVehicle(reindeerLevel), next.tick)).not.toEqual(
    hazardPoints(roadVehicle(reindeerLevel), lane.tick),
  );
  const tunnel = herdAt({ x: -13.5, z: 125 });
  const waited = tickWorld(tunnel, command, reindeerLevel).state;
  expect(groundHeight(reindeerLevel.road, leaderOf(tunnel).pos)).toBe(-3);
  expect(waited.waitTicks).toBe(1);
  expect(leaderOf(waited).pos).toEqual(leaderOf(tunnel).pos);
  const warning = reindeerLevel.zones.find(({ kind }) => kind === "warning")!;
  expect(
    (reindeerLevel.road.near - Math.min(...warning.points.map(({ z }) => z))) /
      REINDEER.cruise,
  ).toBeGreaterThan(3);
});

test("RD-A07 RD-A08 narrow clearance can split the herd and blocks a call across the rail", () => {
  const narrow = { x: -10, z: 263 };
  const beyond = { x: -10, z: 274 };
  const wide = { x: 17, z: 263 };
  expect(groundMove(reindeerLevel, narrow, beyond, hoofRadius(0))).toEqual(
    beyond,
  );
  expect(groundMove(reindeerLevel, narrow, beyond, hoofRadius(8))).toEqual(
    narrow,
  );
  expect(
    groundMove(reindeerLevel, wide, { ...wide, z: 274 }, hoofRadius(8)).z,
  ).toBe(274);
  const base = herdAt(beyond);
  const target = base.actors[8]!;
  const actors = base.actors.map((actor) =>
    actor === target
      ? {
          ...actor,
          pos: { x: -10, z: 266.04 },
          status: "strayed" as const,
          rescueTicks: REINDEER.rescueTicks,
        }
      : actor,
  );
  let state: ReindeerState = { ...base, actors };
  for (let i = 0; i < 160; i++)
    state = tickWorld(state, call, reindeerLevel).state;
  expect(state.actors[8]).toMatchObject({
    status: "strayed",
    rescueProgress: 0,
    pos: actors[8]!.pos,
  });
  const leader = { ...leaderOf(state), pos: { x: -10, z: 264 }, speed: 0 };
  state = { ...state, actors: [leader, ...state.actors.slice(1)] };
  for (let i = 0; i < REINDEER.pickupTicks; i++)
    state = tickWorld(state, call, reindeerLevel).state;
  expect(state.actors[8]?.status).toBe("rejoining");
});

test("R2 cue distinguishes a blocked breadcrumb from a usable opening", () => {
  const approaching = (x: number) => {
    const base = herdAt({ x, z: 282 }, { segmentId: "R2" });
    return {
      ...base,
      trailStart: 0,
      trail: Array.from({ length: 40 }, (_, i) => ({ x, z: 269 + i * 0.2 })),
      actors: base.actors.map((actor, i) => ({
        ...actor,
        pos: i === 8 ? { x, z: 266.04 } : { x, z: 282 },
        status: i === 8 ? ("loose" as const) : actor.status,
        trailIndex: 0,
      })),
    };
  };
  const narrow = approaching(-10);
  expect(reindeerTeammateGuidance(narrow, reindeerLevel)).toMatchObject({
    kind: "fence",
    actor: { id: narrow.actors[8]?.id },
    wideOpening: true,
  });
  const wide = approaching(17);
  expect(reindeerTeammateGuidance(wide, reindeerLevel)).toMatchObject({
    kind: "on-way",
    actor: { id: wide.actors[8]?.id },
    wideOpening: false,
  });
});

test("R4 cue names the actual ninth-deer blocker, including rejoining inside the goal", () => {
  const goal = reindeerLevel.zones.find(({ kind }) => kind === "goal");
  const base = herdAt({ x: 0, z: 588 }, { segmentId: "R4" });
  const reunion = {
    ...base,
    actors: base.actors.map((actor, i) =>
      i === 8 ? { ...actor, status: "rejoining" as const } : actor,
    ),
  };
  expect(goal && contains(goal.points, reunion.actors[8]!.pos)).toBe(true);
  expect(goalStatus(reunion, goal)).toMatchObject({
    arrived: 8,
    canLand: false,
  });
  expect(reindeerTeammateGuidance(reunion, reindeerLevel, goal)).toMatchObject({
    kind: "returning",
    actor: { id: base.actors[8]?.id },
  });
  const outside = {
    ...base,
    actors: base.actors.map((actor, i) =>
      i === 8 ? { ...actor, pos: { x: 0, z: 561 } } : actor,
    ),
  };
  expect(goalStatus(outside, goal)).toMatchObject({
    arrived: 8,
    canLand: false,
  });
  expect(reindeerTeammateGuidance(outside, reindeerLevel, goal)).toMatchObject({
    kind: "on-way",
    actor: { id: base.actors[8]?.id },
  });
  const rescue = {
    ...outside,
    actors: outside.actors.map((actor, i) =>
      i === 7 || i === 8
        ? {
            ...actor,
            status: "strayed" as const,
            rescueTicks: i === 7 ? 43 : 60,
          }
        : actor,
    ),
  };
  expect(reindeerTeammateGuidance(rescue, reindeerLevel, goal)).toMatchObject({
    kind: "rescue",
    actor: { id: base.actors[7]?.id },
  });
});

for (const route of ["dust", "greenbelt"] as const) {
  test(`RD-A06 RD-A09 RD-A11 RD-A15 entire ${route} journey reaches C1, C2 and 9/9`, async () => {
    const { runtime, checkpoints, inputs, events } = reindeerTrip(route);
    const state = runtime.current;
    expect({
      checkpoint: runtime.checkpoint.id,
      phase: state.phase,
      pos: leaderOf(state).pos,
    }).toMatchObject({
      checkpoint: "C2",
      phase: "landing",
    });
    expect(state.route).toBe(route);
    expect(inputs.length * STEP_SEC).toBeGreaterThan(180);
    expect(events.filter(({ event }) => event.type === "strayed")).toEqual([]);
    expect(checkpoints.map(({ id }) => id)).toEqual(["C1", "C2"]);
    for (const checkpoint of checkpoints) {
      expect(
        readCheckpoint(checkpoint, reindeerLevel, "journey"),
        JSON.stringify({
          id: checkpoint.id,
          state: { ...checkpoint.state, trail: undefined },
        }),
      ).toBeDefined();
    }
    const goal = reindeerLevel.zones.find(({ kind }) => kind === "goal");
    expect(goalStatus(state, goal)).toMatchObject({
      arrived: 9,
      expected: 9,
      canLand: true,
    });
    runtime.dispatch({ type: "finishLanding" });
    expect(runtime.dispatch({ type: "finishLanding" })).toEqual([]);
    expect(
      readRunRecord(
        {
          kind: "arrived",
          version: 1,
          runId: "a".repeat(32),
          species: "reindeer",
          levelId: reindeerLevel.id,
          mode: "journey",
          levelRevision: reindeerLevel.levelRevision,
          route,
          tick: state.tick,
        },
        reindeerLevel,
        "journey",
      ),
    ).toMatchObject({ kind: "arrived", route });
    await writeReplay(`R0-R4-${route}`, {
      levelRevision: reindeerLevel.levelRevision,
      mode: "journey",
      start: null,
      inputs,
      events,
      expected: state,
    });
  }, 12000);
}

test("RD-A09 RD-A10 RD-A11 supply safety, two failure causes, restore and roster gates", () => {
  const rest = herdAt({ x: -47, z: 400 }, { energy: 0 });
  const recovered = tickWorld(rest, NEUTRAL_INPUT, reindeerLevel).state;
  expect(recovered.phase).toBe("playing");
  expect(recovered.energy).toBeGreaterThan(0);
  expect(recovered.supply["green-supply"]).toBeLessThan(
    rest.supply["green-supply"]!,
  );

  const start = herdAt({ x: 0, z: 74 }, { energy: 0 });
  for (const failure of ["energy", "rescue"] as const) {
    const actors = start.actors.map((actor, i) =>
      i === 8 && failure === "rescue"
        ? { ...actor, status: "strayed" as const, rescueTicks: 1 }
        : actor,
    );
    const runtime = new GameRuntime(reindeerLevel, "journey", {
      version: 1,
      id: "start",
      state: { ...start, energy: failure === "energy" ? 0 : 0.7, actors },
    });
    runtime.step();
    expect(runtime.current.failure).toBe(failure);
    runtime.dispatch({ type: "retry" });
    expect(runtime.current).toEqual({
      ...runtime.checkpoint.state,
      phase: "playing",
      energy: 1,
    });
  }
  const state = herdAt({ x: 0, z: 577 });
  const goal = reindeerLevel.zones.find(({ kind }) => kind === "goal");
  expect(
    state.actors.every((actor) => goal && contains(goal.points, actor.pos)),
  ).toBe(true);
  const actors = state.actors.map((actor, i) =>
    i === 8 ? { ...actor, status: "rejoining" as const } : actor,
  );
  expect(goalStatus({ ...state, actors }, goal)).toMatchObject({
    arrived: 8,
    canLand: false,
  });
});

test("RD-A13 invalid corridor and disabled vehicle data reject before play", () => {
  const raw = structuredClone(reindeerSource) as Record<string, unknown>;
  expect(() =>
    validateLevel(
      { ...raw, road: { ...reindeerLevel.road, vehicleId: "missing" } },
      "test",
      "reindeer",
    ),
  ).toThrow("road.vehicleId");
  expect(() =>
    validateLevel(
      {
        ...raw,
        road: {
          ...reindeerLevel.road,
          culvert: { ...reindeerLevel.road.culvert, right: -18 },
        },
      },
      "test",
      "reindeer",
    ),
  ).toThrow("road.culvert.right");
});

test("RD-A05 actual vehicle overlap makes a companion retreat to the shoulder", () => {
  const vehicle = roadVehicle(reindeerLevel);
  const cross = { x: 5, z: 125 };
  const tick = Array.from({ length: 1140 }, (_, i) => i).find((i) =>
    contains(hazardPoints(vehicle, i), cross),
  )!;
  const start = herdAt({ x: 5, z: 137 }, { tick });
  const actors = start.actors.map((actor, i) =>
    i === 8 ? { ...actor, pos: cross } : actor,
  );
  const hit = tickWorld({ ...start, actors }, NEUTRAL_INPUT, reindeerLevel);
  expect(hit.events).toContainEqual({ type: "strayed", id: "reindeer-8" });
  expect(hit.state.energy).toBeLessThan(start.energy);
  expect(hit.state.phase).toBe("playing");
  expect(hit.state.actors[8]?.retreatZ).toBeLessThan(reindeerLevel.road.near);
  let state = hit.state;
  for (let step = 0; step < 210; step++)
    state = tickWorld(state, NEUTRAL_INPUT, reindeerLevel).state;
  expect(state.actors[8]).toMatchObject({ status: "strayed", retreatZ: null });
  expect(onRoad(reindeerLevel.road, state.actors[8]!.pos)).toBe(false);
});

test("RD-A07 RD-A08 taking the narrow gate, turning back to rescue, and crossing the wide gate", async () => {
  const journey = reindeerTrip("dust");
  const start = journey.checkpoints[0]!;
  const runtime = new GameRuntime(reindeerLevel, "journey", start);
  const inputs: WorldInput[] = [];
  const events: Parameters<typeof writeReplay>[1]["events"][number][] = [];
  const step = (input: WorldInput) => {
    runtime.dispatch({ type: "input", input });
    for (const event of runtime.step((_, used) => inputs.push(used)))
      events.push({ tick: runtime.current.tick, event });
  };
  const go = (x: number, z: number) => {
    const to = { x, z };
    for (
      let i = 0;
      i < 3200 && distance(leaderOf(runtime.current).pos, to) > 0.21;
      i++
    ) {
      const pos = leaderOf(runtime.current).pos;
      step(moveTo(pos, to, distance(pos, to) < 2 ? 0.12 : 0.84));
    }
    expect(leaderOf(runtime.current).pos).toMatchObject({
      x: expect.closeTo(x, 0),
      z: expect.closeTo(z, 0),
    });
  };
  go(-10, 253);
  go(-10, 280);
  go(-6, 284);
  go(-6, 305);
  expect(
    runtime.current.actors.filter(({ status }) => status === "strayed").length,
  ).toBeGreaterThan(0);
  const wrongTurn = new GameRuntime(reindeerLevel, "journey", start);
  const timeoutInputs = [...inputs];
  followRecordedInputs(wrongTurn, inputs);
  wrongTurn.dispatch({ type: "input", input: NEUTRAL_INPUT });
  const timeoutEvents = [...events];
  for (
    let tick = 0;
    tick < REINDEER.rescueTicks + 10 && wrongTurn.current.phase === "playing";
    tick++
  ) {
    for (const event of wrongTurn.step((_, used) => timeoutInputs.push(used)))
      timeoutEvents.push({ tick: wrongTurn.current.tick, event });
  }
  const failure = wrongTurn.current;
  expect(failure.phase).toBe("failed");
  expect(failure.failure).toBe("rescue");
  wrongTurn.dispatch({ type: "retry" });
  expect(wrongTurn.current).toEqual({ ...start.state, energy: 1 });
  await writeReplay("C1-rescue-timeout-retry", {
    levelRevision: reindeerLevel.levelRevision,
    mode: "journey",
    start,
    inputs: timeoutInputs,
    events: timeoutEvents,
    expected: failure,
    retry: wrongTurn.current,
  });
  followRecordedInputs(wrongTurn, journey.inputs.slice(start.state.tick));
  expect(wrongTurn.current.phase).toBe("landing");

  go(-6, 282);
  go(-10, 278);
  go(-10, 264);
  for (let i = 0; i < 270; i++) step(call);
  expect(
    runtime.current.actors.some(({ status }) => status === "strayed"),
  ).toBe(false);
  go(17, 253);
  go(17, 279);
  go(-6, 285);
  go(-6, 302);
  go(17, 308);
  go(17, 323);
  for (let i = 0; i < 240; i++) step(call);
  expect(runtime.current.actors.every(({ pos }) => pos.z > 269)).toBe(true);
  await writeReplay("R2-narrow-rescue-wide", {
    levelRevision: reindeerLevel.levelRevision,
    mode: "journey",
    start,
    inputs,
    events,
    expected: runtime.current,
  });
});

test("RD-A10 energy failure after C2 restores the full saved roster and continued branch", async () => {
  const journey = reindeerTrip("greenbelt");
  const saved = journey.checkpoints[1]!;
  const start = { ...saved, state: { ...saved.state, energy: 0.005 } };
  expect(readCheckpoint(start, reindeerLevel, "journey")).toBeDefined();
  const runtime = new GameRuntime(reindeerLevel, "journey", start);
  const inputs: WorldInput[] = [];
  const events: Parameters<typeof writeReplay>[1]["events"][number][] = [];
  const step = (command: WorldInput) => {
    runtime.dispatch({ type: "input", input: command });
    for (const event of runtime.step((_, used) => inputs.push(used)))
      events.push({ tick: runtime.current.tick, event });
  };
  for (let i = 0; i < 6_000 && leaderOf(runtime.current).pos.x < 67; i++) {
    step({ move: { x: 0.84, z: 0 }, ability: false });
  }
  expect(leaderOf(runtime.current).pos.x).toBeGreaterThan(67);
  let target = { x: 67, z: 470 };
  for (let i = 0; i < 9000 && runtime.current.phase === "playing"; i++) {
    const pos = leaderOf(runtime.current).pos;
    if (distance(pos, target) < 1)
      target = { x: target.x > 64 ? 60 : 68, z: 470 };
    step(moveTo(pos, target));
  }
  const failure = runtime.current;
  expect(failure.phase).toBe("failed");
  expect(failure.failure).toBe("energy");
  runtime.dispatch({ type: "retry" });
  expect(runtime.current).toEqual({ ...start.state, energy: 1 });
  await writeReplay("C2-energy-retry", {
    levelRevision: reindeerLevel.levelRevision,
    mode: "journey",
    start,
    inputs,
    events,
    expected: failure,
    retry: runtime.current,
  });
  followRecordedInputs(runtime, journey.inputs.slice(start.state.tick));
  expect(runtime.current.phase).toBe("landing");
});
