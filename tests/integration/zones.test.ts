import { expect, test } from "vitest";
import { Mesh, Vector3 } from "three";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { flightThreat } from "../../src/app/flight-guidance";
import {
  NEUTRAL_INPUT,
  type GameEvent,
  type GameMode,
  type GooseState,
  type WorldInput,
} from "../../src/core/game";
import { GameRuntime } from "../../src/core/runtime";
import type { Vec2 } from "../../src/core/math";
import { contains, polygonError, sweptCircle } from "../../src/levels/geometry";
import { buildLandscape } from "../../src/rendering/landscape";
import { TURBINE_SCALE } from "../../src/rendering/scenery";
import { GOOSE } from "../../src/simulation/goose";
import { initialState, leaderOf, tickWorld } from "../../src/simulation/world";
import { writeReplay } from "../fixtures/export-replays";
import {
  aim,
  migration,
  shortCourse,
  shortTrip,
  trip,
} from "../fixtures/flight";

const forward: WorldInput = { move: { x: 0, z: 0.899 }, ability: false };

function translated(
  x: number,
  z: number,
  mode: GameMode = "journey",
): GooseState {
  const state = initialState(migration, mode);
  return {
    ...state,
    airborne: true,
    actors: state.actors.map((actor) => ({
      ...actor,
      pos: { x: actor.pos.x + x, z: actor.pos.z + z },
      speed: GOOSE.cruise,
    })),
  };
}

test.each(["journey"] as const)(
  "M2 the short course lands in %s after the same rescue trigger",
  async (mode) => {
    const { runtime, input, events } = shortTrip(mode);
    expect(
      runtime.current.phase,
      JSON.stringify({
        actors: runtime.current.actors.map(({ id, pos, status }) => ({
          id,
          pos,
          status,
        })),
        recent: events.slice(-8),
      }),
    ).toBe("landing");
    expect(runtime.checkpoint.id).toBe("A");
    expect(events.map(({ event }) => event.type)).toEqual(
      expect.arrayContaining(["checkpoint", "strayed", "rejoined"]),
    );
    expect(runtime.current.actors).toHaveLength(12);
    await writeReplay(`rules-${mode}`, {
      levelRevision: shortCourse.levelRevision,
      mode,
      start: null,
      inputs: input,
      events,
      expected: runtime.current,
    });
  },
);

function renderedSweep(low: boolean): Vec2[] {
  const { group } = buildLandscape(migration, low);
  const stroke = group.getObjectByName("sweep")?.getObjectByName("outline");
  if (!(stroke instanceof Mesh))
    throw new Error("Missing S4 rendered sweep outline");
  const vertex = stroke.geometry.getAttribute("position");
  const point = new Vector3();
  const opposite = new Vector3();
  return Array.from({ length: vertex.count / 2 }, (_, i) => {
    point.fromBufferAttribute(vertex, i * 2);
    point.lerp(opposite.fromBufferAttribute(vertex, i * 2 + 1), 0.5);
    stroke.localToWorld(point);
    return { x: point.x, z: point.z };
  });
}

test("T14 and V2-12 drawn S4 perimeter matches the collision polygon at each vertex", () => {
  const hazard = migration.zones.find((zone) => zone.id === "sweep");
  if (!hazard) throw new Error("Missing wind farm");
  for (const low of [true, false]) {
    const stroke = renderedSweep(low);
    for (const point of hazard.points)
      expect(
        stroke.some(
          ({ x, z }) => Math.hypot(x - point.x, z - point.z) < 0.0001,
        ),
      ).toBe(true);
    for (const point of stroke)
      expect(sweptCircle(hazard.points, point, point, 0.0001)).toBe(true);
  }
  expect(
    sweptCircle(
      hazard.points,
      { x: 0, z: 515 },
      { x: 0, z: 700 },
      GOOSE.hitRadius,
    ),
  ).toBe(true);
  expect(
    sweptCircle(
      hazard.points,
      { x: -55, z: 515 },
      { x: -55, z: 700 },
      GOOSE.hitRadius,
    ),
  ).toBe(false);
  expect(
    polygonError([
      { x: 0, z: 0 },
      { x: 10, z: 10 },
      { x: 10, z: 0 },
      { x: 0, z: 10 },
      { x: 0, z: 0 },
    ]),
  ).toBe("polygon self-intersection");
});

test("L03 T14 T15 the full flock clears the direct S4 channel without using bay supply", async () => {
  const sweep = migration.zones.find((zone) => zone.id === "sweep");
  if (!sweep) throw new Error("Missing S4 hazard boundary");
  const hazardZ = sweep.points.map(({ z }) => z);
  const firstHazardZ = Math.min(...hazardZ);
  const lastHazardZ = Math.max(...hazardZ);
  const trials = [];
  for (const mode of ["journey"] as const) {
    const start = trip(mode, "mountain", 490).runtime.current;
    for (const policy of ["hold", "release"] as const) {
      const snapshot = { version: 1 as const, id: "start", state: start };
      const flight = new GameRuntime(migration, mode, snapshot);
      const inputs: WorldInput[] = [];
      const events: { tick: number; event: GameEvent }[] = [];
      const leadPath: Vec2[] = [leaderOf(start).pos];
      let minimumCenterDistance = 100;
      let closestFlock = {
        tick: start.tick,
        positions: start.actors.map(({ pos }) => pos),
      };
      let widestFlock = 0;
      let observedHazardSpan = false;
      let waypoint = 0;
      const targets = [
        { x: -55, z: 532 },
        { x: -55, z: 690 },
      ];
      const cleared = () =>
        flight.current.actors.every(
          (actor) => actor.pos.z - GOOSE.hitRadius > lastHazardZ,
        );
      while (
        inputs.length < 1800 &&
        flight.current.phase === "playing" &&
        !cleared()
      ) {
        const before = flight.current;
        const lead = leaderOf(before).pos;
        if (waypoint === 0 && lead.z >= 530) waypoint = 1;
        const target = targets[waypoint];
        if (!target) throw new Error("Missing outer water waypoint");
        flight.dispatch({
          type: "input",
          input: aim(lead, target, 0.83, policy === "hold" || lead.z < 519),
        });
        for (const event of flight.step((_, input) => inputs.push(input)))
          events.push({ tick: flight.current.tick, event });
        const after = flight.current;
        if (after.tick % 15 === 0 || cleared())
          leadPath.push(leaderOf(after).pos);
        if (lead.z >= firstHazardZ && lead.z <= lastHazardZ) {
          observedHazardSpan = true;
          expect(after.formation).toBeCloseTo(policy === "hold" ? 1 : 0, 5);
          const positions = after.actors.map((actor) => actor.pos.x);
          widestFlock = Math.max(
            widestFlock,
            Math.max(...positions) - Math.min(...positions),
          );
        }
        for (const [i, actor] of after.actors.entries()) {
          const old = before.actors[i];
          if (!old) throw new Error("Missing prior flock member");
          expect(actor.id).toBe(old.id);
          expect(
            sweptCircle(sweep.points, old.pos, actor.pos, GOOSE.hitRadius),
          ).toBe(false);
          if (
            !sweptCircle(
              sweep.points,
              old.pos,
              actor.pos,
              minimumCenterDistance,
            )
          )
            continue;
          // Find the largest known clear radius using the same swept test as the game.
          let clear: number = GOOSE.hitRadius;
          let touching = minimumCenterDistance;
          while (touching - clear > 0.01) {
            const radius = (clear + touching) / 2;
            if (sweptCircle(sweep.points, old.pos, actor.pos, radius))
              touching = radius;
            else clear = radius;
          }
          minimumCenterDistance = clear;
          closestFlock = {
            tick: after.tick,
            positions: after.actors.map(({ pos }) => pos),
          };
        }
      }
      expect(observedHazardSpan).toBe(true);
      expect(cleared()).toBe(true);
      expect(flight.current.phase).toBe("playing");
      expect(flight.current.actors).toHaveLength(GOOSE.size);
      expect(
        events.some(
          ({ event }) =>
            event.type === "strayed" ||
            (event.type === "zone" && event.id === "sweep"),
        ),
      ).toBe(false);
      const replenished =
        (start.supply["reserve-supply"] ?? 0) -
        (flight.current.supply["reserve-supply"] ?? 0);
      expect(replenished).toBe(0);
      trials.push({
        mode,
        policy,
        ticks: inputs.length,
        minimumClearance: minimumCenterDistance - GOOSE.hitRadius,
        widestFlock,
        replenished,
        closestFlock,
        leadPath,
      });
      await writeReplay(`migration-${mode}-s4-outer-${policy}`, {
        levelRevision: migration.levelRevision,
        mode,
        start: snapshot,
        inputs,
        events,
        expected: flight.current,
      });
    }
  }
  const output = process.env.FEATHER_REPLAY_DIR;
  if (output) {
    await mkdir(output, { recursive: true });
    await writeFile(
      join(output, "s4-outer-water.json"),
      JSON.stringify(
        {
          levelRevision: migration.levelRevision,
          outline: { standard: renderedSweep(false), low: renderedSweep(true) },
          zones: migration.zones.filter(({ id }) =>
            ["wind-warning", "sweep", "reserve", "reserve-supply"].includes(id),
          ),
          trials,
        },
        null,
        2,
      ) + "\n",
    );
  }
});

test("T14 S4 journey warns before contact at cruise and blocking allows an exit", () => {
  const speed = GOOSE.cruise - 0.01;
  let journey = translated(0, 505);
  journey = {
    ...journey,
    actors: journey.actors.map((actor) => ({ ...actor, speed })),
  };
  const start = journey;
  let warned: number | undefined;
  let danger: number | undefined;
  let contact: number | undefined;
  for (let i = 0; i < 490 && contact === undefined; i++) {
    journey = tickWorld(journey, forward, migration).state;
    if (warned === undefined && journey.occupied.includes("wind-warning"))
      warned = journey.tick;
    if (flightThreat(journey, migration) === "sweep") danger ??= journey.tick;
    if (journey.occupied.includes("sweep")) contact = journey.tick;
  }
  expect(warned).toBeDefined();
  expect(contact).toBeDefined();
  expect(((contact ?? 0) - (warned ?? 0)) / 60).toBeGreaterThan(4);
  expect(danger).toBeDefined();
  expect(((contact ?? 0) - (danger ?? 0)) / 60).toBeGreaterThanOrEqual(3);
  expect(journey.phase).toBe("playing");
  // Compare against the same collision geometry with contact cost disabled in data.
  const noCost = {
    ...migration,
    zones: migration.zones.map((zone) =>
      zone.kind === "hazard" ? { ...zone, cost: 0 } : zone,
    ),
  };
  let control = start;
  while (control.tick < journey.tick)
    control = tickWorld(control, forward, noCost).state;
  expect(control.energy - journey.energy).toBeCloseTo(0.12, 3);
  const hazard = migration.zones.find((zone) => zone.id === "sweep");
  if (!hazard) throw new Error("Missing wind farm");
  expect(contains(hazard.points, leaderOf(journey).pos)).toBe(false);
  for (let i = 0; i < 610; i++) {
    const target = i < 360 ? { x: -61, z: 548 } : { x: -61, z: 645 };
    journey = tickWorld(
      journey,
      aim(leaderOf(journey).pos, target, 0.76),
      migration,
    ).state;
  }
  expect(leaderOf(journey).pos.z).toBeGreaterThan(565);
  expect(journey.actors.every((actor) => actor.rescueTicks === null)).toBe(
    true,
  );
});

test("T14 S4 still gives a reaction window after releasing into a glide", async () => {
  const start = translated(0, 505);
  let state = start;
  let warningTick: number | undefined;
  let contactTick: number | undefined;
  const inputs: WorldInput[] = [];
  const events: { tick: number; event: GameEvent }[] = [];
  while (state.tick < 490 && contactTick === undefined) {
    const gliding =
      warningTick !== undefined &&
      state.tick - warningTick < GOOSE.coastTicks - 1;
    const input = gliding ? NEUTRAL_INPUT : forward;
    inputs.push(input);
    const step = tickWorld(state, input, migration);
    state = step.state;
    for (const event of step.events) {
      events.push({ tick: state.tick, event });
      if (event.type !== "zone" || !event.entered) continue;
      if (event.id === "sweep") contactTick = state.tick;
    }
    if (flightThreat(state, migration) === "sweep") warningTick ??= state.tick;
  }
  expect(warningTick).toBeDefined();
  expect(contactTick).toBeDefined();
  expect(inputs.filter((input) => input === NEUTRAL_INPUT)).toHaveLength(
    GOOSE.coastTicks - 1,
  );
  expect(((contactTick ?? 0) - (warningTick ?? 0)) / 60).toBeGreaterThanOrEqual(
    3,
  );
  await writeReplay("migration-journey-s4-warning-glide", {
    levelRevision: migration.levelRevision,
    mode: state.mode,
    start: { version: 1, id: "start", state: start },
    inputs,
    events,
    expected: state,
  });
});

test("T07 T15 low energy recovers while capacity persists and the majority requirement holds", () => {
  let state = { ...translated(24, 700), energy: 0.14 };
  const supply = "return-supply";
  const first = state.supply[supply] ?? 0;
  const leader = leaderOf(state);
  const stranded = state.actors
    .slice(1)
    .map((actor) => ({ ...actor, pos: { x: 85, z: 704 } }));
  const noMajority = tickWorld(
    { ...state, actors: [leader, ...stranded] },
    NEUTRAL_INPUT,
    migration,
  ).state;
  expect(noMajority.supply[supply]).toBe(first);
  for (let i = 0; i < 145; i++)
    state = tickWorld(state, NEUTRAL_INPUT, migration).state;
  expect(state.energy).toBeGreaterThan(0.45);
  const after = state.supply[supply] ?? 0;
  expect(after).toBeLessThan(first);
  const outside = tickWorld(
    { ...translated(66, 698), supply: state.supply },
    NEUTRAL_INPUT,
    migration,
  ).state;
  expect(outside.supply[supply]).toBe(after);
  const returned = tickWorld(
    { ...translated(24, 701), supply: outside.supply, energy: 0.12 },
    NEUTRAL_INPUT,
    migration,
  ).state;
  expect(returned.supply[supply]).toBeLessThan(after);
});

test("T06 energy failure restores the complete in-memory checkpoint", async () => {
  const start = { ...translated(0, 165), energy: 0.0001 };
  const runtime = new GameRuntime(migration, "journey");
  // Cut the deterministic fixture into a low-energy state to exercise the boundary.
  const replay = new GameRuntime(migration, "journey", {
    ...runtime.checkpoint,
    state: start,
  });
  replay.dispatch({ type: "input", input: forward });
  const events = replay
    .step()
    .map((event) => ({ tick: replay.current.tick, event }));
  expect(replay.current.failure).toBe("energy");
  const expected = replay.current;
  replay.dispatch({ type: "retry" });
  expect(replay.current).toEqual({ ...start, energy: 1 });
  expect(replay.current.actors).toHaveLength(GOOSE.size);
  await writeReplay("migration-journey-energy-retry", {
    levelRevision: migration.levelRevision,
    mode: "journey",
    start: { ...runtime.checkpoint, state: start },
    inputs: [forward],
    events,
    expected,
    retry: replay.current,
  });
});

test("S04 flight energy and cohesion respond to speed, wind, turns and formation", () => {
  const start = { ...translated(0, 158), energy: 0.7, cohesion: 0.7 };
  function fly(input: WorldInput, wind = { x: 0, z: 0 }) {
    const level = {
      ...migration,
      segments: migration.segments.map((segment) => ({ ...segment, wind })),
      zones: [],
      triggers: [],
    };
    let state = start;
    for (let tick = 0; tick < 140; tick++)
      state = tickWorld(state, input, level).state;
    return state;
  }
  const cruise = fly(forward);
  const slow = fly({ ...forward, move: { x: 0, z: 0.15 } });
  const boost = fly({ ...forward, move: { x: 0, z: 1 } });
  const headwind = fly(forward, { x: 0, z: -0.8 });
  const tailwind = fly(forward, { x: 0, z: 0.8 });
  const crosswind = fly(forward, { x: 0.8, z: 0 });
  const turned = fly({ ...forward, move: { x: 0.899, z: 0 } });
  const formation = fly({ ...forward, ability: true });
  expect(boost.energy).toBeLessThan(cruise.energy);
  expect(boost.cohesion).toBeLessThan(cruise.cohesion);
  expect(cruise.energy).toBeLessThan(slow.energy);
  expect(headwind.energy).toBeLessThan(cruise.energy);
  expect(tailwind.energy).toBeGreaterThan(cruise.energy);
  expect(crosswind.cohesion).toBeLessThan(cruise.cohesion);
  expect(turned.energy).toBeLessThan(cruise.energy);
  expect(turned.cohesion).toBeLessThan(cruise.cohesion);
  expect(formation.energy).toBeGreaterThan(cruise.energy);
  expect(formation.cohesion).toBeGreaterThan(cruise.cohesion);
});

test("S04 alert crosses the low-energy threshold once and boost obeys the exact cutoff", () => {
  const start = translated(0, 165);
  const crossing = tickWorld(
    { ...start, energy: GOOSE.lowEnergy + 0.00001 },
    forward,
    migration,
  );
  expect(crossing.state.energy).toBeLessThan(GOOSE.lowEnergy);
  expect(crossing.events).toContainEqual({ type: "lowEnergy" });
  expect(
    tickWorld(crossing.state, forward, migration).events,
  ).not.toContainEqual({ type: "lowEnergy" });
  const boost = { ...forward, move: { x: 0, z: 1 } };
  const atCutoff = tickWorld(
    { ...start, energy: GOOSE.boostCutoff },
    boost,
    migration,
  ).state;
  const aboveCutoff = tickWorld(
    { ...start, energy: GOOSE.boostCutoff + 0.00001 },
    boost,
    migration,
  ).state;
  expect(leaderOf(atCutoff).speed).toBe(GOOSE.cruise);
  expect(leaderOf(aboveCutoff).speed).toBeGreaterThan(GOOSE.cruise);
});

test("S06 the last available rescue tick succeeds only at pickup speed and distance", () => {
  const start = translated(0, 30);
  const ready = {
    ...start,
    actors: start.actors.map((actor) =>
      actor.id === start.leaderId
        ? { ...actor, speed: 0 }
        : actor.id === "goose-11"
          ? {
              ...actor,
              pos: { x: 0, z: 32 },
              status: "strayed" as const,
              rescueTicks: 1,
              rescueProgress: GOOSE.pickupTicks - 1,
            }
          : actor,
    ),
  };
  const rescued = tickWorld(ready, NEUTRAL_INPUT, migration);
  expect(rescued.state.phase).toBe("playing");
  expect(rescued.events).toContainEqual({ type: "rejoined", id: "goose-11" });
  const misses = [
    ready.actors.map((actor) =>
      actor.id === start.leaderId ? { ...actor, speed: GOOSE.cruise } : actor,
    ),
    ready.actors.map((actor) =>
      actor.id === "goose-11"
        ? { ...actor, pos: { x: GOOSE.rescueRadius + 1, z: 30 } }
        : actor,
    ),
  ];
  for (const actors of misses) {
    const failed = tickWorld({ ...ready, actors }, NEUTRAL_INPUT, migration);
    expect(failed.state.failure).toBe("rescue");
    expect(
      failed.state.actors.find((actor) => actor.id === "goose-11")
        ?.rescueProgress,
    ).toBe(0);
    expect(failed.events).not.toContainEqual({
      type: "rejoined",
      id: "goose-11",
    });
  }
});

test("T14 the STR-001 configured blade envelope remains inside the authoritative S4 footprint", () => {
  const sweep = migration.zones.find((zone) => zone.id === "sweep");
  if (!sweep) throw new Error("Missing wind farm");
  // The STR-001 GLB source QA measures a 1.925 BU maximum projected radius.
  const radius = 1.925 * TURBINE_SCALE;
  for (const { pos } of migration.landmarks.filter(
    (mark) => mark.kind === "turbine",
  )) {
    for (let angle = 0; angle < Math.PI * 2; angle += Math.PI / 90) {
      expect(
        contains(sweep.points, {
          x: pos.x + Math.cos(angle) * radius,
          z: pos.z + Math.sin(angle) * radius,
        }),
      ).toBe(true);
    }
  }
});
