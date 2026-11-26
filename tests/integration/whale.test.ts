import { mkdir, writeFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gunzipSync } from "node:zlib";
import { describe, expect, test } from "vitest";
import { whaleGuidance } from "../../src/app/whale-guidance";
import { shipPassage, surfaceCruiseWindow } from "../../src/app/whale-ship";
import { FixedClock, STEP_SEC } from "../../src/core/clock";
import {
  NEUTRAL_INPUT,
  type GameEvent,
  type GameMode,
  type WhaleActor,
  type WhaleRoute,
  type WhaleState,
  type WorldInput,
} from "../../src/core/game";
import { distance, type Vec2 } from "../../src/core/math";
import { GameRuntime } from "../../src/core/runtime";
import { readCheckpoint, readRunRecord } from "../../src/core/save";
import { validateLevel, type WhaleLevel } from "../../src/levels/schema";
import { currentGuide } from "../../src/levels/whale-current";
import { kelpApproaches } from "../../src/levels/whale-kelp";
import {
  hazardPoints,
  sweptWaterHazard,
} from "../../src/levels/whale-geometry";
import { contains } from "../../src/levels/geometry";
import { isCyclicNoise, noisePhase } from "../../src/levels/whale-noise";
import { goalStatus, tickWorld } from "../../src/simulation/world";
import { WHALE } from "../../src/simulation/whale-motion";
import { surfaced, whaleSupplyStatus } from "../../src/simulation/world-rules";
import { writeReplay } from "../fixtures/export-replays";
import { aim } from "../fixtures/flight";
import {
  bayPassage,
  forwardSwim,
  kelpForkFromC1,
  netPassageFromC1,
  podAt,
  podLeader,
  shipCrossing,
  shippingApproach,
  whaleFailure,
  whaleLevel,
  whaleState,
  whaleTrip,
} from "../fixtures/whale";

const dive = { ...NEUTRAL_INPUT, ability: true };

test.each([false, true])(
  "W0 leads the whole pod into W1 after optional bay practice (%s)",
  async (practice) => {
    const replay = bayPassage(practice);
    expect(replay.expected).toMatchObject({
      segmentId: "W1",
      phase: "playing",
      failure: null,
      occupied: ["waiting-water", "ship-approach-breakwater-warning"],
    });
    expect(replay.expected.actors).toHaveLength(6);
    for (const actor of replay.expected.actors) {
      expect(actor).toMatchObject({
        status: "following",
        dive: { layer: "surface", direction: null, breath: 1 },
      });
    }
    expect(replay.inputs.some(({ ability }) => ability)).toBe(practice);
    await writeReplay(
      practice ? "W0-bay-practice-to-W1" : "W0-direct-to-W1",
      replay,
    );
  },
);

test("W0 only assists aligned submerged input and pauses the whole world", () => {
  const location = { x: 21, z: 167 };
  const shallow = withLeaderAt(location, "journey", "shallow");
  const surface = withLeaderAt(location, "journey", "surface");
  const input = { move: { x: 0, z: 0.42 }, ability: true };
  const withoutFlow = {
    ...whaleLevel,
    zones: whaleLevel.zones.filter(({ id }) => id !== "bay-current"),
  };
  const compare = (level: WhaleLevel) =>
    whaleState(tickWorld(shallow, input, level).state);
  expect(compare(whaleLevel).occupied).toContain("bay-current");
  expect(compare(whaleLevel).energy).toBeGreaterThan(
    compare(withoutFlow).energy,
  );
  for (const [state, command] of [
    [surface, input],
    [shallow, { ...NEUTRAL_INPUT, ability: true }],
    [shallow, { ...input, move: { x: 0, z: -0.42 } }],
  ] as const)
    expect(tickWorld(state, command, whaleLevel).state.occupied).not.toContain(
      "bay-current",
    );

  const runtime = new GameRuntime(whaleLevel, "journey", {
    version: 1,
    id: "start",
    state: shallow,
  });
  runtime.dispatch({ type: "pause" });
  const paused = runtime.current;
  expect(runtime.step()).toEqual([]);
  expect(runtime.current).toBe(paused);
  runtime.dispatch({ type: "resume" });
  expect(advance(runtime, 1, input).occupied).toContain("bay-current");
});

test.each(["surface", "current"] as const)(
  "W0 %s route brings six whales from spawn to C1",
  async (route) => {
    const ship = whaleLevel.zones.find(({ id }) => id === "cargo-ship");
    if (ship?.kind !== "hazard") throw new Error("Missing ship");
    const { far } = shipPassage(ship);
    const runtime = new GameRuntime(whaleLevel, "journey");
    const inputs: WorldInput[] = [];
    const events: { tick: number; event: GameEvent }[] = [];
    let borrowing = 0;
    let enteredW1 = false;
    let crossing = false;
    let approachIndex = 0;
    const cruise = { ...forwardSwim, move: { x: 0, z: 0.9 } };
    for (let step = 0; step < 7800 && runtime.checkpoint.id !== "C1"; step++) {
      const state = whaleState(runtime.current);
      const leader = podLeader(state);
      const { pos } = leader;
      let input = cruise;
      if (route === "current" && pos.z < 268) {
        input =
          pos.z < 138
            ? aim(pos, { x: 21, z: 145 }, 0.87)
            : pos.z < 192
              ? { move: { x: 0, z: 0.64 }, ability: true }
              : aim(pos, { x: 0, z: 276 }, 0.83);
      } else if (pos.z >= 270 && pos.z < 370) {
        const mark = shippingApproach[approachIndex];
        if (!mark) throw new Error("Missing shipping approach");
        if (
          approachIndex < shippingApproach.length - 1 &&
          distance(pos, mark) < 4
        )
          approachIndex++;
        input = aim(pos, shippingApproach[approachIndex] ?? mark, 0.83);
      } else if (pos.z >= 370) {
        if (route === "current") input = { ...cruise, ability: pos.z < 457 };
        else {
          crossing ||= surfaceCruiseWindow(ship, state, leader, far);
          if (!crossing) input = NEUTRAL_INPUT;
        }
      }
      runtime.dispatch({ type: "input", input });
      for (const event of runtime.step((_, used) => inputs.push(used)))
        events.push({ tick: runtime.current.tick, event });
      const next = whaleState(runtime.current);
      if (next.occupied.includes("bay-current")) borrowing++;
      if (!enteredW1 && next.actors.every(({ pos }) => pos.z >= 270)) {
        enteredW1 = true;
        expect(next.actors.every(surfaced)).toBe(true);
      }
    }
    expect(enteredW1).toBe(true);
    if (route === "current") expect(borrowing).toBeGreaterThan(180);
    else expect(borrowing).toBe(0);
    expect(runtime.checkpoint.id).toBe("C1");
    const saved = whaleState(runtime.checkpoint.state);
    expect(saved.actors).toHaveLength(6);
    expect(saved.actors.every(surfaced)).toBe(true);
    expect(events.map(({ event }) => event)).not.toContainEqual({
      type: "zone",
      id: "cargo-ship",
      entered: true,
    });
    await writeReplay(`W0-${route}-to-C1`, {
      levelRevision: whaleLevel.levelRevision,
      mode: "journey",
      start: null,
      inputs,
      events,
      expected: runtime.current,
    });
  },
);

test.each(["wide", "short", "rescue"] as const)(
  "WH-A06 W2 continues from a valid C1 to W3 via %s",
  async (path) => {
    const c1 = readCheckpoint(
      whaleTrip("journey", "quiet").checkpoints[0],
      whaleLevel,
      "journey",
    );
    if (!c1 || c1.id !== "C1") throw new Error("Missing real C1");
    const replay = netPassageFromC1(c1, path);
    const { expected, events } = replay;
    expect(expected).toMatchObject({
      phase: "playing",
      segmentId: "W3",
      route: null,
    });
    expect(expected.actors.map(({ id }) => id)).toEqual(
      c1.state.actors.map(({ id }) => id),
    );
    expect(
      expected.actors.every(
        ({ status, rescueTicks }) =>
          status === "following" && rescueTicks === null,
      ),
    ).toBe(true);
    expect(replay.runtime.checkpoint).toEqual(c1);
    const recorded = events.map(({ event }) => event);
    const rescues = recorded.filter(
      ({ type }) => type === "strayed" || type === "rejoined",
    );
    const contacts = events.filter(
      ({ event }) =>
        event.type === "zone" &&
        event.entered &&
        ["drift-net", "net-divider"].includes(event.id),
    );
    if (path === "rescue") {
      expect(rescues).toEqual([
        { type: "strayed", id: "whale-2" },
        { type: "rejoined", id: "whale-2" },
      ]);
      expect(contacts.length).toBeGreaterThan(0);
      expect(
        contacts.every(
          ({ tick, event }, i) =>
            !contacts
              .slice(0, i)
              .some(
                (previous) =>
                  previous.event.type === "zone" &&
                  event.type === "zone" &&
                  previous.event.id === event.id &&
                  tick - previous.tick <= 60,
              ),
        ),
      ).toBe(true);
    } else {
      expect(rescues).toEqual([]);
      expect(contacts).toEqual([]);
    }
    await writeReplay(`W2-C1-to-W3-${path}`, replay);
  },
);

test("W2 short route saves travel while the wide route passes through quiet water", () => {
  const start = whaleTrip("journey", "quiet").checkpoints[0];
  const w3 = whaleLevel.segments.find(({ id }) => id === "W3");
  if (!start || !w3) throw new Error("Missing W2 route");
  const finish = ({ actors }: WhaleState) =>
    actors.every(
      ({ pos, status }) => pos.z >= w3.start && status === "following",
    );
  const short = netPassageFromC1(start, "short", finish);
  const wide = netPassageFromC1(start, "wide", finish);
  for (const voyage of [short, wide]) {
    expect(voyage.expected.phase).toBe("playing");
    expect(finish(voyage.expected)).toBe(true);
    expect(
      voyage.events.some(
        ({ event }) =>
          event.type === "strayed" ||
          (event.type === "zone" &&
            event.entered &&
            ["drift-net", "net-divider", "net-kelp"].includes(event.id)),
      ),
    ).toBe(false);
  }
  expect((wide.inputs.length - short.inputs.length) * STEP_SEC).toBeGreaterThan(
    2,
  );
  const enteredWideRest = ({ event }: (typeof wide.events)[number]): boolean =>
    event.type === "zone" && event.entered && event.id === "net-rest";
  expect(wide.events.some(enteredWideRest)).toBe(true);
  expect(short.events.some(enteredWideRest)).toBe(false);
});

function advance(
  runtime: GameRuntime,
  ticks: number,
  input: WorldInput = NEUTRAL_INPUT,
) {
  runtime.dispatch({ type: "input", input });
  for (let step = 0; step < ticks; step++) runtime.step();
  return whaleState(runtime.current);
}

describe("WH-A03 depth, inertia and the fixed simulation clock", () => {
  test("crosses each down threshold on the configured tick and staggers the pod", () => {
    const runtime = new GameRuntime(whaleLevel, "journey");
    expect(podLeader(advance(runtime, 59, dive)).dive).toMatchObject({
      layer: "surface",
      direction: "down",
    });
    const shallow = advance(runtime, 1, dive);
    expect(podLeader(shallow).dive.layer).toBe("shallow");
    expect(
      shallow.actors.slice(1).every(({ dive }) => dive.layer === "surface"),
    ).toBe(true);
    const firstFollower = advance(runtime, 12, dive);
    expect(firstFollower.actors[1]?.dive.layer).toBe("shallow");
    expect(firstFollower.actors.at(-1)?.dive.layer).toBe("surface");
    expect(podLeader(advance(runtime, 107, dive)).dive.layer).toBe("shallow");
    expect(podLeader(advance(runtime, 1, dive)).dive.layer).toBe("deep");
    const ascending = advance(runtime, 1);
    expect(podLeader(ascending).dive).toMatchObject({
      layer: "deep",
      direction: "up",
    });
    expect(podLeader(advance(runtime, 300)).dive).toMatchObject({
      layer: "surface",
      direction: null,
    });
  });

  test("repeated short presses and direction reversals respect continuous depth", () => {
    const runtime = new GameRuntime(whaleLevel, "journey");
    let state = whaleState(runtime.current);
    for (let i = 0; i < 10; i++) {
      const partlyDown = advance(runtime, 6, dive);
      expect(podLeader(partlyDown).dive.layer).toBe("surface");
      state = advance(runtime, 30);
      expect(podLeader(state).dive).toMatchObject({
        layer: "surface",
        depth: 0,
      });
    }
    expect(podLeader(state).dive.breath).toBe(1);
    const halfDive = podLeader(advance(runtime, 35, dive)).dive;
    const rising = podLeader(advance(runtime, 8)).dive;
    expect(rising.depth).toBeLessThan(halfDive.depth);
    const repressed = podLeader(advance(runtime, 1, dive)).dive;
    expect(repressed.layer).toBe("surface");
    expect(repressed.depth).toBeGreaterThan(rising.depth);
    expect(repressed.depth).toBeLessThan(halfDive.depth);
  });

  test("exhaustion forces a gradual ascent and requires release and recovery", () => {
    const runtime = new GameRuntime(whaleLevel, "journey");
    expect(podLeader(advance(runtime, 600, dive)).dive.layer).toBe("deep");
    let forcedAt = -1;
    for (let tick = 0; tick < 1800; tick++) {
      const state = advance(runtime, 1, dive);
      const leader = podLeader(state);
      if (leader.dive.forced) {
        forcedAt = state.tick;
        expect(leader.dive.breath).toBe(0);
        expect(leader.dive.layer).toBe("deep");
        break;
      }
    }
    expect(forcedAt).toBeGreaterThan(600);
    const surfacing = podLeader(advance(runtime, 1, dive)).dive;
    expect(surfacing).toMatchObject({ layer: "deep", direction: "up" });
    const recovered = advance(runtime, 800, dive);
    expect(recovered.phase).toBe("playing");
    expect(recovered.failure).toBeNull();
    expect(podLeader(recovered).dive).toMatchObject({
      layer: "surface",
      breath: 1,
    });
    advance(runtime, 1);
    expect(podLeader(advance(runtime, 60, dive)).dive.layer).toBe("shallow");
  });

  test("forward momentum coasts to rest with no automatic heading change", () => {
    const runtime = new GameRuntime(whaleLevel, "journey");
    const before = podLeader(advance(runtime, 180, forwardSwim));
    const moving = podLeader(advance(runtime, 15));
    const stop = podLeader(advance(runtime, 300));
    expect(moving.speed).toBeGreaterThan(0);
    expect(moving.speed).toBeLessThan(before.speed);
    expect(stop.speed).toBe(0);
    expect(stop.heading).toBe(before.heading);
    expect(stop.pos.z - before.pos.z).toBeGreaterThan(2);
    expect(podLeader(advance(runtime, 120)).pos).toEqual(stop.pos);
    const reverse = podLeader(
      advance(runtime, 1, { move: { x: 0, z: -1 }, ability: false }),
    );
    expect(Math.abs(reverse.heading)).toBeLessThan(0.03);
  });

  test("30, 60 and 120 FPS replay the full pod state and events identically", () => {
    function replay(fps: number) {
      const runtime = new GameRuntime(whaleLevel, "journey");
      const clock = new FixedClock();
      const events: GameEvent[] = [];
      for (let frame = 0; runtime.current.tick < 1800; frame++) {
        clock.frame((frame * 1000) / fps, true, () => {
          const tick = runtime.current.tick;
          const input =
            tick < 480
              ? forwardSwim
              : tick < 840
                ? { ...forwardSwim, ability: true }
                : tick < 1080
                  ? { move: { x: 0.74, z: 0.38 }, ability: true }
                  : NEUTRAL_INPUT;
          runtime.dispatch({ type: "input", input });
          events.push(...runtime.step());
          return runtime.current.tick < 1800;
        });
      }
      const state = whaleState(runtime.current);
      runtime.dispatch({ type: "pause" });
      for (let step = 0; step < 60; step++) runtime.step();
      expect(runtime.current).toEqual({ ...state, phase: "paused" });
      return { state, events };
    }
    const reference = replay(60);
    expect(replay(30)).toEqual(reference);
    expect(replay(120)).toEqual(reference);
  });
});

test.each([false, true])(
  "WH-A04 W1 completes via waiting or diving (dive=%s)",
  async (useDive) => {
    const replay = shipCrossing(useDive);
    expect(replay.expected.phase).toBe("playing");
    expect(replay.checkpoints.map(({ id }) => id)).toEqual(["C1"]);
    expect(
      replay.expected.actors.every(({ dive }) => dive.layer === "surface"),
    ).toBe(true);
    expect(replay.events.map(({ event }) => event)).not.toContainEqual({
      type: "zone",
      id: "cargo-ship",
      entered: true,
    });
    await writeReplay(useDive ? "W1-deep-crossing" : "W1-surface-wait", replay);
  },
);

function withLayer(
  actor: WhaleActor,
  layer: WhaleActor["dive"]["layer"],
): WhaleActor {
  return {
    ...actor,
    dive: {
      ...actor.dive,
      layer,
      depth: { surface: 0, shallow: 1, deep: 2 }[layer],
      direction: null,
      progress: 0,
    },
  };
}

function withLeaderAt(
  pos: Vec2,
  mode: GameMode,
  layer: WhaleActor["dive"]["layer"],
  tick = 0,
) {
  const state = podAt(pos, mode, tick);
  return {
    ...state,
    diveInputTicks: layer === "surface" ? 0 : 61,
    actors: state.actors.map((actor, index) =>
      index === 0 ? { ...withLayer(actor, layer), speed: 8 } : actor,
    ),
  };
}

test.each(["surface", "shallow", "deep"] as const)(
  "WH-A04 both nets block the %s layer and leave two distinct passages open",
  (layer) => {
    const move = { ...forwardSwim, ability: layer !== "surface" };
    const blocked = withLeaderAt({ x: 0, z: 746.25 }, "journey", layer);
    const journey = whaleState(tickWorld(blocked, move, whaleLevel).state);
    expect(podLeader(journey).pos.z).toBeCloseTo(podLeader(blocked).pos.z);
    expect(journey.energy).toBeLessThan(0.95);
    const divider = withLeaderAt({ x: 96, z: 746.25 }, "journey", layer);
    const againstDivider = whaleState(
      tickWorld(divider, move, whaleLevel).state,
    );
    expect(againstDivider.occupied).toContain("net-divider");
    expect(podLeader(againstDivider).pos.z).toBeCloseTo(
      podLeader(divider).pos.z,
    );
    for (const x of [75, 124]) {
      const opening = withLeaderAt({ x, z: 746.25 }, "journey", layer);
      const through = whaleState(tickWorld(opening, move, whaleLevel).state);
      expect(podLeader(through).pos.z).toBeGreaterThan(
        podLeader(opening).pos.z + 0.05,
      );
    }
  },
);

test.each(["surface", "shallow", "deep"] as const)(
  "WH-A04 the entire pod can bypass W2 from the %s layer without triggering rescue",
  (layer) => {
    const start = podAt({ x: 123, z: 709 });
    const actors = start.actors.map((actor) => withLayer(actor, layer));
    const runtime = new GameRuntime(whaleLevel, "journey", {
      id: "start",
      version: 1,
      state: {
        ...start,
        actors,
        segmentId: "W2",
        diveInputTicks: layer === "surface" ? 0 : 61,
      },
    });
    runtime.dispatch({
      type: "input",
      input: { ...forwardSwim, ability: layer !== "surface" },
    });
    let touchedNet = false;
    for (let step = 0; step < 1600; step++) {
      const events = runtime.step();
      touchedNet ||= events.some(
        (event) =>
          event.type === "zone" &&
          ["drift-net", "net-divider"].includes(event.id) &&
          event.entered,
      );
    }
    const state = whaleState(runtime.current);
    expect(touchedNet).toBe(false);
    expect(state.actors.every((actor) => actor.pos.z > 840)).toBe(true);
    expect(state.triggered).not.toContain("net-rescue");
  },
);

test("WH-A04 the same ship tick blocks shallow and surface whales but clears a deep whale", () => {
  const tick = 3600;
  for (const layer of ["surface", "shallow", "deep"] as const) {
    const start = withLeaderAt({ x: 0, z: 406.25 }, "journey", layer, tick);
    const input = { ...forwardSwim, ability: layer !== "surface" };
    const step = tickWorld(start, input, whaleLevel);
    const current = whaleState(step.state);
    const contacted = step.events.some(
      (event) =>
        event.type === "zone" && event.id === "cargo-ship" && event.entered,
    );
    expect(contacted).toBe(layer !== "deep");
    if (layer === "deep") {
      expect(podLeader(current).pos.z).toBeGreaterThan(podLeader(start).pos.z);
    } else {
      expect(podLeader(current).pos.z).toBeCloseTo(podLeader(start).pos.z);
    }
  }
});

test("WH-A06 wrong layer and too-fast contact reset rescue progress", () => {
  const start = podAt({ x: 93, z: 830 });
  const tail = start.actors.at(-1);
  if (!tail) throw new Error("Missing whale to rescue");
  const lost: WhaleActor = {
    ...tail,
    pos: { x: 93, z: 828 },
    status: "strayed",
    rescueTicks: 2399,
    rescueProgress: 30,
  };
  for (const leader of [
    withLayer(podLeader(start), "deep"),
    { ...podLeader(start), speed: 8 },
    { ...podLeader(start), pos: { x: 110, z: 870 } },
  ]) {
    const next = tickWorld(
      { ...start, actors: [leader, ...start.actors.slice(1, -1), lost] },
      NEUTRAL_INPUT,
      whaleLevel,
    ).state;
    expect(next.actors.at(-1)).toMatchObject({
      id: "whale-5",
      status: "strayed",
      rescueTicks: 2398,
      rescueProgress: 0,
    });
  }
});

const courses: readonly [GameMode, WhaleRoute][] = [
  ["journey", "shipping"],
  ["journey", "quiet"],
];

for (const [mode, route] of courses) {
  test(`WH-A09 ${mode} completes W0–W4 via ${route} and records both checkpoints`, async () => {
    const replay = whaleTrip(mode, route);
    const { expected, runtime, checkpoints } = replay;
    const baseline = new URL(
      `../../docs/plans/whale/evidence/p2-3/W0-W4-journey-${route}.json.gz`,
      import.meta.url,
    );
    const previous = JSON.parse(gunzipSync(readFileSync(baseline)).toString());
    expect(expected.tick).toBeLessThan(previous.expected.tick * 0.8);
    expect(checkpoints.map(({ id }) => id)).toEqual(["C1", "C2"]);
    expect(expected).toMatchObject({
      phase: "landing",
      segmentId: "W4",
      route,
      routeLocked: true,
    });
    expect(expected.actors.every(({ dive }) => dive.layer === "surface")).toBe(
      true,
    );
    expect(checkpoints[0]?.state.route).toBeNull();
    expect(checkpoints[1]?.state.route).toBe(route);
    expect(replay.events.filter(({ event }) => event.type === "route")).toEqual(
      [{ tick: expect.any(Number), event: { type: "route", route } }],
    );
    for (const checkpoint of checkpoints)
      expect(readCheckpoint(checkpoint, whaleLevel, mode)).toEqual(checkpoint);
    expect(runtime.step()).toEqual([]);
    expect(runtime.current).toBe(expected);
    expect(runtime.dispatch({ type: "finishLanding" })).toContainEqual({
      type: "completed",
      route,
    });
    expect(runtime.dispatch({ type: "finishLanding" })).toEqual([]);
    await writeReplay(`W0-W4-${mode}-${route}`, replay);
  });
}

test("W2 kelp shelter has finite surface supplies for a pod that regroups", () => {
  const zone = whaleLevel.zones.find(({ id }) => id === "net-kelp");
  if (zone?.kind !== "supply") throw new Error("Missing kelp shelter");
  const pod = podAt({ x: 38, z: 876 });
  const ready = { ...pod, segmentId: "W2", energy: 0.4 };
  const leaderOnly = {
    ...ready,
    actors: ready.actors.map((actor, i) =>
      i > 0 ? { ...actor, pos: { ...actor.pos, x: 68 } } : actor,
    ),
  };
  const submerged = {
    ...ready,
    actors: ready.actors.map((actor) => withLayer(actor, "shallow")),
  };
  for (const state of [leaderOnly, submerged]) {
    expect(
      tickWorld(state, NEUTRAL_INPUT, whaleLevel).state.supply[zone.id],
    ).toBe(zone.capacity);
  }
  const runtime = new GameRuntime(whaleLevel, "journey", {
    version: 1,
    id: "start",
    state: ready,
  });
  expect(advance(runtime, 180).energy).toBeCloseTo(0.4 + zone.capacity);
  expect(runtime.current.supply[zone.id]).toBe(0);
  expect(advance(runtime, 180).energy).toBeCloseTo(0.4 + zone.capacity);
});

test.each(["short", "arc"] as const)(
  "WH-A06 W2 %s kelp approach supplies the pod and leads all six into W3",
  async (path) => {
    const start = readCheckpoint(
      whaleTrip("journey", "quiet").checkpoints[0],
      whaleLevel,
      "journey",
    );
    const bay = whaleLevel.zones.find(({ id }) => id === "net-kelp");
    const w3 = whaleLevel.segments.find(({ id }) => id === "W3");
    if (!start || bay?.kind !== "supply" || !w3)
      throw new Error("Missing W2 route");
    const runtime = new GameRuntime(whaleLevel, "journey", start);
    const inputs: WorldInput[] = [];
    const events: { tick: number; event: GameEvent }[] = [];
    const bayId = bay.id;
    let groupEnteredTick = 0;
    let leaderEnteredTick = 0;
    let supplyStartedTick = 0;
    const step = (input: WorldInput) => {
      const before = runtime.current.supply[bayId] ?? 0;
      runtime.dispatch({ type: "input", input });
      for (const event of runtime.step((_, used) => inputs.push(used)))
        events.push({ tick: runtime.current.tick, event });
      const state = runtime.current;
      const { arrived, inside, ready } = whaleSupplyStatus(
        podLeader(state),
        state.actors,
        bay,
      );
      if (inside && !leaderEnteredTick) leaderEnteredTick = state.tick;
      if (arrived === 6 && !groupEnteredTick) groupEnteredTick = state.tick;
      if ((state.supply[bayId] ?? 0) < before) {
        expect(ready).toBe(true);
        supplyStartedTick ||= state.tick;
      }
    };
    function swimTo(target: Vec2, throttle: number) {
      for (let i = 0; i < 1200; i++) {
        const leader = podLeader(runtime.current);
        if (distance(leader.pos, target) <= 3) return;
        step(aim(leader.pos, target, throttle));
      }
      throw new Error(`Did not reach W2 waypoint ${JSON.stringify(target)}`);
    }
    for (const input of kelpForkFromC1(start).inputs) step(input);
    const began = runtime.current;
    expect(began.actors.every(({ pos }) => pos.z > 780)).toBe(true);
    expect(podLeader(began).pos.z).toBeCloseTo(815, 0);
    for (const id of kelpApproaches[path]) {
      const mark = whaleLevel.landmarks.find((mark) => mark.id === id);
      if (!mark) throw new Error(`Missing kelp waypoint ${id}`);
      swimTo(mark.pos, path === "short" ? 0.64 : 0.83);
    }
    for (let i = 0; i < 240; i++) step(NEUTRAL_INPUT);
    const regrouped = runtime.current;
    expect(
      whaleSupplyStatus(podLeader(regrouped), regrouped.actors, bay),
    ).toMatchObject({ arrived: 6, inside: true, ready: true });
    expect(leaderEnteredTick).toBeGreaterThan(began.tick);
    expect(supplyStartedTick).toBeGreaterThan(leaderEnteredTick);
    expect(groupEnteredTick).toBeGreaterThanOrEqual(supplyStartedTick);
    expect(regrouped.supply[bayId]).toBeLessThan(bay.capacity);
    expect(regrouped.energy).toBeCloseTo(1);

    swimTo({ x: 34, z: 963 }, 0.83);
    const result = runtime.current;
    expect(result).toMatchObject({
      phase: "playing",
      segmentId: "W3",
      route: null,
    });
    expect(result.actors.map(({ id }) => id)).toEqual(
      start.state.actors.map(({ id }) => id),
    );
    expect(
      result.actors.every(
        (actor) =>
          actor.pos.z >= w3.start &&
          actor.status === "following" &&
          surfaced(actor),
      ),
    ).toBe(true);
    expect(
      events.some(
        ({ event }) =>
          event.type === "strayed" ||
          (event.type === "zone" &&
            event.entered &&
            (event.id === "drift-net" || event.id === "net-divider")),
      ),
    ).toBe(false);
    await writeReplay(`W2-kelp-${path}-C1-to-W3`, {
      levelRevision: whaleLevel.levelRevision,
      mode: "journey",
      start,
      inputs,
      events,
      expected: result,
    });
    if (process.env.FEATHER_REPLAY_DIR)
      await writeFile(
        join(process.env.FEATHER_REPLAY_DIR, `W2-kelp-${path}.json`),
        JSON.stringify(
          {
            path,
            clearedTick: began.tick,
            firstInBaySeconds: (leaderEnteredTick - began.tick) * STEP_SEC,
            secondsForPodToEnter:
              (groupEnteredTick - leaderEnteredTick) * STEP_SEC,
            secondsToW3WithSix: (result.tick - began.tick) * STEP_SEC,
            supplyUsed: bay.capacity - (regrouped.supply[bayId] ?? 0),
            energyAfterSupply: regrouped.energy,
          },
          null,
          2,
        ) + "\n",
      );
  },
);

test("W4 can borrow the offshore current from C2, then surface and finish together", () => {
  const start = readCheckpoint(
    whaleTrip("journey", "shipping").checkpoints[1],
    whaleLevel,
    "journey",
  );
  const current = whaleLevel.zones.find(({ id }) => id === "offshore-current");
  if (!start || current?.kind !== "current")
    throw new Error("Missing W4 course");
  const currentId = current.id;
  const { entry, exit } = currentGuide(current);
  const runtime = new GameRuntime(whaleLevel, "journey", start);
  function swimTo(target: Vec2, diving = false) {
    let assisted = 0;
    for (let i = 0; i < 1800; i++) {
      const { pos } = podLeader(runtime.current);
      if (distance(pos, target) < 4 || runtime.current.phase !== "playing")
        return assisted;
      const state = advance(runtime, 1, aim(pos, target, 0.83, diving));
      if (state.occupied.includes(currentId)) assisted++;
    }
    throw new Error("Offshore waypoint not reached");
  }
  expect(swimTo({ x: entry.x + 5, z: entry.z - 18 })).toBe(0);
  expect(swimTo(exit, true)).toBeGreaterThan(180);
  swimTo({ x: 77, z: 1482 });
  expect(runtime.current.occupied).not.toContain(current.id);
  expect(advance(runtime, 120).actors.every(surfaced)).toBe(true);
  swimTo({ x: 80, z: 1559 });
  expect(advance(runtime, 240).phase).toBe("landing");
  expect(
    goalStatus(
      runtime.current,
      whaleLevel.zones.find(({ kind }) => kind === "goal"),
    ),
  ).toMatchObject({ arrived: 6, expected: 6 });
});

test("WH-A07 W3 from C1 supports a direct passage or a shallow stop, and C2 still leads to 6/6", async () => {
  const { inputs, checkpoints, expected, events } = whaleTrip(
    "journey",
    "quiet",
  );
  const first = readCheckpoint(checkpoints[0], whaleLevel, "journey");
  const second = readCheckpoint(checkpoints[1], whaleLevel, "journey");
  if (!first || !second) throw new Error("Missing valid C1 or C2");

  const crossings = events.filter(
    ({ event }) => event.type === "zone" && event.id === "quiet-rest",
  );
  const enterTick = crossings[0]?.tick ?? 0;
  const exitTick = crossings[1]?.tick ?? 0;
  expect((exitTick - enterTick) / 60).toBeGreaterThanOrEqual(10);
  expect((exitTick - enterTick) / 60).toBeLessThanOrEqual(25);

  const direct = new GameRuntime(whaleLevel, "journey", first);
  for (const input of inputs.slice(first.state.tick)) advance(direct, 1, input);
  expect(direct.checkpoint).toEqual(second);
  expect(direct.current).toEqual(expected);

  const excursion = new GameRuntime(whaleLevel, "journey", first);
  const observationInputs: WorldInput[] = [];
  const observationEvents: { tick: number; event: GameEvent }[] = [];
  function swim(input: WorldInput, ticks = 1) {
    excursion.dispatch({ type: "input", input });
    for (let step = 0; step < ticks; step++) {
      for (const event of excursion.step((_, used) =>
        observationInputs.push(used),
      ))
        observationEvents.push({ tick: excursion.current.tick, event });
    }
  }
  for (const input of inputs.slice(first.state.tick, enterTick + 180))
    swim(input);
  expect(excursion.current).toMatchObject({
    route: "quiet",
    routeLocked: false,
  });
  expect(excursion.current.occupied).toContain("quiet-rest");
  const pool = { x: -73, z: 1123 };
  for (
    let tick = 0;
    tick < 600 && distance(podLeader(excursion.current).pos, pool) > 4;
    tick++
  )
    swim(aim(podLeader(excursion.current).pos, pool, 0.62));
  expect(distance(podLeader(excursion.current).pos, pool)).toBeLessThanOrEqual(
    4,
  );
  swim({ ...forwardSwim, ability: true }, 125);
  expect(podLeader(excursion.current).dive.layer).toBe("shallow");
  expect(podLeader(excursion.current).dive.breath).toBeLessThan(1);
  swim(NEUTRAL_INPUT, 540);
  expect(podLeader(excursion.current).speed).toBe(0);
  expect(
    excursion.current.actors.every(
      ({ dive }) => dive.layer === "surface" && dive.breath === 1,
    ),
  ).toBe(true);
  expect(excursion.current.occupied).toContain("quiet-rest");

  for (const target of [
    { x: -90, z: 1219 },
    { x: 65, z: 1307 },
    { x: 65, z: 1385 },
  ]) {
    for (let step = 0; step < 2400; step++) {
      const leader = podLeader(excursion.current);
      if (distance(leader.pos, target) < 5 || excursion.checkpoint.id === "C2")
        break;
      swim(aim(leader.pos, target, 0.83));
    }
  }
  expect(excursion.checkpoint.id).toBe("C2");
  expect(excursion.current).toMatchObject({
    route: "quiet",
    routeLocked: true,
  });
  expect(readCheckpoint(excursion.checkpoint, whaleLevel, "journey")).toEqual(
    excursion.checkpoint,
  );
  expect(
    observationEvents.filter(({ event }) => event.type === "route"),
  ).toEqual([
    { tick: expect.any(Number), event: { type: "route", route: "quiet" } },
  ]);
  await writeReplay("W3-quiet-reef-from-C1", {
    levelRevision: whaleLevel.levelRevision,
    mode: "journey",
    start: first,
    inputs: observationInputs,
    events: observationEvents,
    expected: excursion.current,
  });

  for (const checkpoint of [second, excursion.checkpoint]) {
    const offshore = new GameRuntime(whaleLevel, "journey", checkpoint);
    const target = { x: 80, z: 1559 };
    for (
      let step = 0;
      step < 3000 && offshore.current.phase === "playing";
      step++
    ) {
      const leader = podLeader(offshore.current);
      advance(
        offshore,
        1,
        distance(leader.pos, target) < 4
          ? NEUTRAL_INPUT
          : aim(leader.pos, target, 0.83),
      );
    }
    expect(offshore.current.phase).toBe("landing");
    const goal = whaleLevel.zones.find(({ kind }) => kind === "goal");
    expect(goalStatus(offshore.current, goal)).toMatchObject({
      arrived: 6,
      expected: 6,
    });
    expect(
      offshore.current.actors.every(({ dive }) => dive.layer === "surface"),
    ).toBe(true);
  }
});

test("W3 only assists actively aligned swimmers beneath the surface", () => {
  const current = whaleLevel.zones.find(({ id }) => id === "reef-current");
  if (current?.kind !== "current") throw new Error("Missing reef current");
  const plain = {
    ...whaleLevel,
    zones: whaleLevel.zones.filter((zone) => zone !== current),
  };
  const pos = { x: -85, z: 1151 };
  const turn = Math.atan2(current.direction.x, current.direction.z);
  const forward = {
    x: current.direction.x * 0.83,
    z: current.direction.z * 0.83,
  };
  function pair(
    layer: WhaleActor["dive"]["layer"],
    move: Vec2,
    position = pos,
    heading = turn,
  ) {
    const base = podAt(position);
    const state: WhaleState = {
      ...base,
      segmentId: "W3",
      route: "quiet",
      energy: 0.75,
      diveInputTicks: 61,
      actors: base.actors.map((actor) => ({
        ...withLayer(actor, layer),
        heading,
        speed: 5.9,
      })),
    };
    const input = { move, ability: layer !== "surface" };
    let normal = state;
    let withCurrent = state;
    for (let tick = 0; tick < 60; tick++) {
      normal = tickWorld(normal, input, plain).state;
      withCurrent = tickWorld(withCurrent, input, whaleLevel).state;
    }
    return { normal, withCurrent };
  }
  for (const layer of ["shallow", "deep"] as const) {
    const { normal, withCurrent } = pair(layer, forward);
    expect(withCurrent.occupied).toContain(current.id);
    expect(podLeader(withCurrent).speed).toBeGreaterThan(
      podLeader(normal).speed,
    );
    expect(withCurrent.energy).toBeGreaterThan(normal.energy);
    expect(podLeader(withCurrent).heading).toBe(podLeader(normal).heading);
  }
  const lightPush = {
    x: current.direction.x * 0.35,
    z: current.direction.z * 0.35,
  };
  const light = pair("shallow", lightPush);
  expect(
    podLeader(light.withCurrent).speed - podLeader(light.normal).speed,
  ).toBeGreaterThan(1.4);
  const full = pair("deep", current.direction);
  expect(podLeader(full.withCurrent).speed).toBeLessThanOrEqual(WHALE.boost);
  for (const { normal, withCurrent } of [
    pair("surface", forward),
    pair("shallow", { x: 0, z: 0 }),
    pair("shallow", { x: -forward.x, z: -forward.z }),
    pair("deep", forward, { x: -115, z: 1151 }),
  ])
    expect(withCurrent).toEqual(normal);
  const turning = pair("shallow", forward, pos, turn + Math.PI);
  expect(turning.withCurrent).toEqual(turning.normal);
});

test.each(["continuous", "regroup", "surface"] as const)(
  "WH-A07 W3 %s reaches C2 and offshore with all six whales from the same C1",
  async (path) => {
    const { checkpoints, inputs: directInputs } = whaleTrip("journey", "quiet");
    const start = readCheckpoint(checkpoints[0], whaleLevel, "journey");
    const first = whaleLevel.zones.find(({ id }) => id === "reef-current");
    const second = whaleLevel.zones.find(
      ({ id }) => id === "reef-current-east",
    );
    const pool = whaleLevel.zones.find(({ id }) => id === "reef-eddy");
    const waypoints = (id: string) => {
      const mark = whaleLevel.landmarks.find((mark) => mark.id === id);
      if (!mark) throw new Error(`Missing W3 landmark ${id}`);
      return mark.pos;
    };
    if (
      !start ||
      first?.kind !== "current" ||
      second?.kind !== "current" ||
      !pool
    )
      throw new Error("Missing W3 two-current course");

    const runtime = new GameRuntime(whaleLevel, "journey", start);
    const inputs: WorldInput[] = [];
    const events: { tick: number; event: GameEvent }[] = [];
    const assisted = new Map<string, number>();
    let minimumBreath = 1;
    let maximumTailGap = 0;
    function step(input: WorldInput, measure = true) {
      runtime.dispatch({ type: "input", input });
      for (const event of runtime.step((_, used) => inputs.push(used)))
        events.push({ tick: runtime.current.tick, event });
      if (!measure) return;
      const state = runtime.current;
      const leader = podLeader(state);
      for (const actor of state.actors) {
        minimumBreath = Math.min(minimumBreath, actor.dive.breath);
        maximumTailGap = Math.max(
          maximumTailGap,
          distance(leader.pos, actor.pos),
        );
      }
      for (const id of ["reef-current", "reef-current-east"]) {
        if (state.occupied.includes(id))
          assisted.set(id, (assisted.get(id) ?? 0) + 1);
      }
      expect(state.actors.every(({ dive }) => !dive.forced)).toBe(true);
    }
    function swimTo(
      target: Vec2,
      diving = false,
      throttle = 0.83,
      tolerance = 3,
    ) {
      for (let i = 0; i < 2400; i++) {
        const leader = podLeader(runtime.current);
        if (
          distance(leader.pos, target) <= tolerance ||
          runtime.current.phase !== "playing"
        )
          return;
        step(aim(leader.pos, target, throttle, diving));
      }
      throw new Error(`Did not reach W3 waypoint ${JSON.stringify(target)}`);
    }
    for (const input of directInputs.slice(start.state.tick)) {
      step(input, false);
      if (
        runtime.current.route === "quiet" &&
        podLeader(runtime.current).pos.z >= 1088
      )
        break;
    }
    const startTick = runtime.current.tick;
    expect(runtime.current.route).toBe("quiet");
    let airBeforeRest: number | undefined;
    if (path === "surface") {
      for (const id of ["quiet-mid", "quiet-arc", "quiet-bend"])
        swimTo(waypoints(id));
      expect(assisted.size).toBe(0);
      expect(minimumBreath).toBe(1);
    } else {
      const { entry, exit } = currentGuide(first);
      swimTo({
        x: entry.x - first.direction.x * 12,
        z: entry.z - first.direction.z * 12,
      });
      swimTo(exit, true);
      airBeforeRest = podLeader(runtime.current).dive.breath;
      expect(airBeforeRest).toBeLessThan(1);

      swimTo(waypoints("current-eddy"), path === "continuous");
      expect(runtime.current.occupied).toContain("reef-eddy");
      if (path === "regroup") {
        for (
          let i = 0;
          i < 560 &&
          !runtime.current.actors.every(({ dive }) => dive.breath === 1);
          i++
        )
          step(NEUTRAL_INPUT);
        expect(goalStatus(runtime.current, pool)).toMatchObject({
          arrived: 6,
          canLand: true,
        });
        expect(
          runtime.current.actors.every(({ dive }) => dive.breath === 1),
        ).toBe(true);
      } else {
        expect(
          runtime.current.actors.every(({ dive }) => dive.layer !== "surface"),
        ).toBe(true);
      }
      swimTo(currentGuide(second).exit, true);
      expect(assisted.get(first.id)).toBeGreaterThan(180);
      expect(assisted.get(second.id)).toBeGreaterThan(140);
      expect(minimumBreath).toBeGreaterThan(WHALE.lowBreath);
    }

    swimTo(waypoints("merge-here"));
    swimTo({ x: 64, z: 1380 });
    const c2 = readCheckpoint(runtime.checkpoint, whaleLevel, "journey");
    expect(c2?.id).toBe("C2");
    if (!c2) throw new Error("W3 passage did not save C2");
    expect(c2.state).toMatchObject({ route: "quiet", routeLocked: true });
    expect(c2.state.actors.map(({ id }) => id)).toEqual(
      start.state.actors.map(({ id }) => id),
    );
    expect(c2.state.actors.every((actor) => actor.status === "following")).toBe(
      true,
    );
    const hz = 1 / STEP_SEC;
    const report = {
      path,
      startTick,
      checkpointTick: c2.state.tick,
      secondsToC2: (c2.state.tick - startTick) / hz,
      minimumBreath,
      maximumTailGap,
      energyAtC2: c2.state.energy,
      airBeforeRest,
      assistedSeconds: Object.fromEntries(
        [...assisted].map(([id, ticks]) => [id, ticks / hz]),
      ),
    };

    swimTo(waypoints("offshore-marker"));
    for (let i = 0; i < 300 && runtime.current.phase === "playing"; i++)
      step(NEUTRAL_INPUT, false);
    const goal = whaleLevel.zones.find(({ kind }) => kind === "goal");
    expect(runtime.current.phase).toBe("landing");
    expect(goalStatus(runtime.current, goal)).toMatchObject({
      arrived: 6,
      expected: 6,
    });
    expect(events.some(({ event }) => event.type === "strayed")).toBe(false);
    await writeReplay(`W3-two-currents-${path}-C1-to-W4`, {
      levelRevision: whaleLevel.levelRevision,
      mode: "journey",
      start,
      events,
      inputs,
      expected: runtime.current,
    });
    if (process.env.FEATHER_REPLAY_DIR)
      await writeFile(
        join(process.env.FEATHER_REPLAY_DIR, `W3-two-currents-${path}.json`),
        JSON.stringify(report, null, 2) + "\n",
      );
  },
);

test("WH-A10 a valid C2 continues through a shallow entry and one surface gathering", async () => {
  const start = readCheckpoint(
    whaleTrip("journey", "shipping").checkpoints[1],
    whaleLevel,
    "journey",
  );
  const goal = whaleLevel.zones.find(({ kind }) => kind === "goal");
  if (!start || !goal) throw new Error("Missing valid C2 or offshore goal");
  const runtime = new GameRuntime(whaleLevel, "journey", start);
  const marker = { x: 80, z: 1559 };
  const inputs: WorldInput[] = [];
  const events: { tick: number; event: GameEvent }[] = [];
  function swim(ability: boolean) {
    const leader = podLeader(runtime.current);
    const input =
      distance(leader.pos, marker) < 4
        ? NEUTRAL_INPUT
        : aim(leader.pos, marker, 0.83, ability);
    runtime.dispatch({ type: "input", input });
    for (const event of runtime.step((_, used) => inputs.push(used)))
      events.push({ tick: runtime.current.tick, event });
  }
  for (
    let step = 0;
    step < 2400 && podLeader(runtime.current).pos.z < 1510;
    step++
  )
    swim(false);
  for (let step = 0; step < 125; step++) swim(true);
  const entry = podLeader(runtime.current);
  expect(contains(goal.points, entry.pos)).toBe(true);
  expect(entry.dive.layer).toBe("shallow");
  expect(runtime.current.phase).toBe("playing");
  expect(goalStatus(runtime.current, goal).canLand).toBe(false);

  let sawFiveWaiting = false;
  for (
    let step = 0;
    step < 900 && runtime.current.phase === "playing";
    step++
  ) {
    swim(false);
    sawFiveWaiting ||=
      runtime.current.phase === "playing" &&
      goalStatus(runtime.current, goal).arrived === 5;
  }
  expect(sawFiveWaiting).toBe(true);
  const settled = runtime.current;
  expect(settled.phase).toBe("landing");
  expect(runtime.checkpoint).toEqual(start);
  expect(goalStatus(settled, goal)).toMatchObject({
    arrived: 6,
    expected: 6,
    canLand: true,
  });
  expect(events.filter(({ event }) => event.type === "phase")).toEqual([
    { tick: settled.tick, event: { type: "phase", phase: "landing" } },
  ]);
  expect(runtime.step()).toEqual([]);
  expect(runtime.dispatch({ type: "finishLanding" })).toContainEqual({
    type: "completed",
    route: "shipping",
  });
  expect(runtime.dispatch({ type: "finishLanding" })).toEqual([]);
  await writeReplay("W4-shallow-entry-from-C2", {
    levelRevision: whaleLevel.levelRevision,
    mode: "journey",
    start,
    inputs,
    events,
    expected: settled,
  });
});

test("WH-A08 both journey failures restore the previous full snapshot and ship phase", async () => {
  const first = shipCrossing(true).checkpoints[0];
  const second = whaleTrip("journey", "quiet").checkpoints[1];
  if (!first || !second) throw new Error("Both checkpoints are required");
  const ship = whaleLevel.zones.find(
    (zone) => zone.kind === "hazard" && zone.id === "cargo-ship",
  );
  if (!ship || ship.kind !== "hazard") throw new Error("Missing cargo ship");
  for (const [checkpoint, failure] of [
    [first, "rescue"],
    [second, "energy"],
  ] as const) {
    const replay = whaleFailure(checkpoint, failure);
    const { runtime, expected } = replay;
    expect(expected).toMatchObject({ phase: "failed", failure });
    expect(runtime.checkpoint).toEqual(checkpoint);
    runtime.dispatch({ type: "retry" });
    expect(runtime.current).toEqual({ ...checkpoint.state, energy: 1 });
    expect(runtime.previous).toBe(runtime.current);
    expect(hazardPoints(ship, runtime.current.tick)).toEqual(
      hazardPoints(ship, checkpoint.state.tick),
    );
    await writeReplay(`retry-${checkpoint.id}-${failure}`, {
      ...replay,
      retry: runtime.current,
    });
  }
});

test("WH-A10 only six ready surface whales finish and freeze the tick", () => {
  const state = podAt({ x: 80, z: 1560 });
  const tail = state.actors.at(-1);
  const goal = whaleLevel.zones.find(({ kind }) => kind === "goal");
  if (!goal || !tail) throw new Error("Missing goal or tail");
  const cases: readonly WhaleActor[] = [
    { ...tail, pos: { x: 15, z: tail.pos.z } },
    withLayer(tail, "shallow"),
    {
      ...tail,
      dive: { ...tail.dive, direction: "up", depth: 0.2, progress: 0.8 },
    },
    { ...tail, status: "strayed", rescueTicks: 35 },
    { ...tail, status: "rejoining" },
  ];
  for (const notReady of cases) {
    expect(
      goalStatus(
        { ...state, actors: [...state.actors.slice(0, -1), notReady] },
        goal,
      ),
    ).toMatchObject({
      arrived: 5,
      expected: 6,
      leaderArrived: true,
      canLand: false,
    });
  }
  const ready = {
    ...state,
    energy: 0,
    route: "quiet" as const,
    routeLocked: true,
    triggered: ["C1", "quiet-gate", "whale-merge", "C2"],
  };
  expect(goalStatus(ready, goal)).toMatchObject({ arrived: 6, canLand: true });
  const runtime = new GameRuntime(whaleLevel, "journey", {
    version: 1,
    id: "C2",
    state: ready,
  });
  const events = runtime.step();
  expect(events).toContainEqual({ type: "phase", phase: "landing" });
  expect(runtime.current.failure).toBeNull();
  const landed = runtime.current;
  expect(runtime.step()).toEqual([]);
  expect(runtime.current).toBe(landed);
});

test("WH-C02 refuses invalid whale layer masks, ship timing, routes and warning links", () => {
  const ship = whaleLevel.zones.find(
    (zone) => zone.kind === "hazard" && zone.id === "cargo-ship",
  );
  if (!ship || ship.kind !== "hazard" || !ship.motion)
    throw new Error("Missing cargo ship");
  const badShip = (patch: Partial<typeof ship>): WhaleLevel => ({
    ...whaleLevel,
    zones: whaleLevel.zones.map((zone) =>
      zone.id === ship.id ? { ...ship, ...patch } : zone,
    ),
  });
  for (const depthMask of [0, 1.5, 8]) {
    expect(() =>
      validateLevel(badShip({ depthMask }), "whale.json", "whale"),
    ).toThrow("depthMask");
  }
  expect(() =>
    validateLevel(
      badShip({ motion: { ...ship.motion!, periodTicks: 5999 } }),
      "whale.json",
      "whale",
    ),
  ).toThrow("periodTicks");
  expect(() =>
    validateLevel(
      badShip({ motion: { ...ship.motion!, phaseTicks: -1 } }),
      "whale.json",
      "whale",
    ),
  ).toThrow("phaseTicks");
  expect(() =>
    validateLevel(
      { ...whaleLevel, routes: ["lake", "quiet"] },
      "whale.json",
      "whale",
    ),
  ).toThrow("routes[0]");
  expect(() =>
    validateLevel(
      {
        ...whaleLevel,
        zones: whaleLevel.zones.filter(({ id }) => id !== "ship-approach"),
      },
      "whale.json",
      "whale",
    ),
  ).toThrow("missing a warning zone");
});

test("WH-C02 rejects invalid current tuning and a zero-length flow direction", () => {
  const current = whaleLevel.zones.find(({ id }) => id === "reef-current");
  if (current?.kind !== "current") throw new Error("Missing reef current");
  for (const [patch, invalid] of [
    [{ direction: { x: 0, z: 0 } }, "direction"],
    [{ speedAssist: 3 }, "speedAssist"],
    [{ fullAssistAt: 0 }, "fullAssistAt"],
    [{ minAlignment: 0 }, "minAlignment"],
    [{ energySaving: 1 }, "energySaving"],
  ] as const) {
    const zones = whaleLevel.zones.map((zone) =>
      zone === current ? { ...zone, ...patch } : zone,
    );
    expect(() =>
      validateLevel({ ...whaleLevel, zones }, "whale.json", "whale"),
    ).toThrow(invalid);
  }
});

test("WH-A07 noise applies cohesional pressure across layers and the exterior supply is bounded", () => {
  for (const layer of ["surface", "shallow", "deep"] as const) {
    const noisy = withLeaderAt({ x: 70, z: 1100 }, "journey", layer);
    const calm = withLeaderAt({ x: -70, z: 1080 }, "journey", layer);
    const input = { ...forwardSwim, ability: layer !== "surface" };
    const afterNoise = tickWorld(noisy, input, whaleLevel).state;
    const afterCalm = tickWorld(calm, input, whaleLevel).state;
    expect(afterNoise.cohesion).toBeLessThan(afterCalm.cohesion);
  }
  const start = { ...podAt({ x: 75, z: 1102 }), energy: 0.08 };
  const refuge = whaleLevel.zones.find(({ id }) => id === "shipping-refill");
  if (!refuge) throw new Error("Missing shipping refuge");
  expect(contains(refuge.points, podLeader(start).pos)).toBe(false);
  const runtime = new GameRuntime(whaleLevel, "journey", {
    version: 1,
    id: "start",
    state: start,
  });
  for (
    let tick = 0;
    tick < 600 && podLeader(runtime.current).pos.z < 1150;
    tick++
  )
    advance(runtime, 1, forwardSwim);
  const reached = runtime.current;
  expect(contains(refuge.points, podLeader(reached).pos)).toBe(true);
  const restored = advance(runtime, 300);
  expect(restored.phase).toBe("playing");
  expect(restored.energy).toBeGreaterThan(start.energy + 0.2);
  expect(restored.supply["shipping-refill"]).toBe(0);
  expect(contains(refuge.points, podLeader(restored).pos)).toBe(true);
});

test("WH-A07 noise changes phase at fixed tick boundaries and responds to an exposed tail", () => {
  const noise = whaleLevel.zones.find(isCyclicNoise);
  if (!noise) throw new Error("Missing cyclic noise");
  const { cycle } = noise;
  expect(noisePhase(cycle, 419)).toMatchObject({
    active: true,
    remainingTicks: 1,
  });
  expect(noisePhase(cycle, 420)).toMatchObject({
    active: false,
    remainingTicks: 780,
  });
  expect(noisePhase(cycle, 1200)).toMatchObject({
    active: true,
    remainingTicks: 420,
  });
  expect(() =>
    validateLevel(
      {
        ...whaleLevel,
        zones: whaleLevel.zones.map((zone) =>
          zone === noise
            ? { ...noise, cycle: { ...cycle, activeTicks: cycle.periodTicks } }
            : zone,
        ),
      },
      "whale",
      "whale",
    ),
  ).toThrow("cycle.activeTicks");
  const pod = podAt({ x: 62, z: 1141 }, "journey", 418);
  const runtime = new GameRuntime(whaleLevel, "journey", {
    id: "start",
    version: 1,
    state: { ...pod, segmentId: "W3", route: "shipping" },
  });
  const first = advance(runtime, 1, forwardSwim);
  expect(first.cohesion).toBeLessThan(1);
  expect(first.occupied).not.toContain(noise.id);
  runtime.dispatch({ type: "pause" });
  expect(advance(runtime, 80).tick).toBe(first.tick);
  expect(runtime.current.cohesion).toBe(first.cohesion);
  runtime.dispatch({ type: "resume" });
  expect(advance(runtime, 1, forwardSwim).cohesion).toBeGreaterThan(
    first.cohesion,
  );
  function replay(fps: number) {
    const start = {
      ...pod,
      tick: 1140,
      segmentId: "W3",
      route: "shipping",
    } as const;
    const instance = new GameRuntime(whaleLevel, "journey", {
      id: "start",
      version: 1,
      state: start,
    });
    const clock = new FixedClock();
    const events: GameEvent[] = [];
    instance.dispatch({ type: "input", input: forwardSwim });
    for (let frame = 0; instance.current.tick < 1680; frame++)
      clock.frame((frame * 1000) / fps, true, () => {
        events.push(...instance.step());
        return instance.current.tick < 1680;
      });
    return { state: instance.current, events };
  }
  const baseline = replay(60);
  expect(replay(30)).toEqual(baseline);
  expect(replay(120)).toEqual(baseline);
});

test.each(["window", "late"] as const)(
  "WH-A07 near voyage from C1 crosses on the %s phase and reaches C2",
  async (timing) => {
    const voyage = whaleTrip("journey", "shipping");
    const c1 = voyage.checkpoints[0];
    const noise = whaleLevel.zones.find(isCyclicNoise);
    if (!c1 || !noise) throw new Error("Missing C1 or noise band");
    const runtime = new GameRuntime(whaleLevel, "journey", c1);
    const inputs: WorldInput[] = [];
    const events: { tick: number; event: GameEvent }[] = [];
    let minimumCohesion = 1;
    function swim(input: WorldInput) {
      runtime.dispatch({ type: "input", input });
      for (const event of runtime.step((_, used) => inputs.push(used)))
        events.push({ tick: runtime.current.tick, event });
      minimumCohesion = Math.min(minimumCohesion, runtime.current.cohesion);
    }
    for (const input of voyage.inputs.slice(c1.state.tick)) {
      if (podLeader(runtime.current).pos.z >= 1077) break;
      swim(input);
    }
    const cycleStart =
      Math.ceil((runtime.current.tick + 180) / noise.cycle.periodTicks) *
      noise.cycle.periodTicks;
    const departure =
      cycleStart + (timing === "window" ? noise.cycle.activeTicks : 1080);
    while (runtime.current.tick < departure) swim(NEUTRAL_INPUT);
    expect(podLeader(runtime.current).pos.z).toBeLessThan(1090);
    const beforeRun = runtime.current.tick;
    for (let i = 0; i < 3000 && runtime.checkpoint.id !== "C2"; i++)
      swim(aim(podLeader(runtime.current).pos, { x: 65, z: 1385 }, 0.83));
    expect(runtime.checkpoint.id).toBe("C2");
    expect(runtime.current.phase).toBe("playing");
    expect(runtime.current.route).toBe("shipping");
    expect(
      runtime.current.actors.every(({ status }) => status === "following"),
    ).toBe(true);
    expect(events.some(({ event }) => event.type === "strayed")).toBe(false);
    if (timing === "window") expect(minimumCohesion).toBe(1);
    else expect(minimumCohesion).toBeLessThan(0.9);
    expect(runtime.current.cohesion).toBe(1);
    expect(runtime.current.tick - beforeRun).toBeLessThan(3000);
    await writeReplay(`W3-near-${timing}-from-C1`, {
      levelRevision: whaleLevel.levelRevision,
      mode: "journey",
      start: c1,
      inputs,
      events,
      expected: runtime.current,
    });
  },
);

test("WH-A08 migrates archived C1 and C2 whale progress and the completed result", () => {
  const archives = [
    "../../docs/plans/whale/evidence/w2-net-rescue/W2-C1-to-W3-bypass.json.gz",
    "../../docs/plans/whale/evidence/w4-offshore/W4-shallow-entry-from-C2.json.gz",
  ];
  const run = {
    species: "whale",
    levelId: "whale",
    mode: "journey",
    version: 1,
    runId: "0123456789abcdef0123456789abcdef",
    levelRevision: "whale-p2-1",
  } as const;
  for (const file of archives) {
    const source = new URL(file, import.meta.url);
    const { start } = JSON.parse(gunzipSync(readFileSync(source)).toString());
    expect(start.state.levelRevision).toBe("whale-p2-1");
    if (start.id === "C2") start.state.triggered.push("net-rescue");
    const migrated = readRunRecord(
      { ...run, kind: "checkpoint", checkpoint: start },
      whaleLevel,
      "journey",
    );
    expect(migrated).toEqual({
      ...run,
      kind: "checkpoint",
      levelRevision: whaleLevel.levelRevision,
      checkpoint: {
        ...start,
        state: {
          ...start.state,
          levelRevision: whaleLevel.levelRevision,
          supply: { ...start.state.supply, "net-kelp": 0.38 },
          triggered: start.state.triggered.filter(
            (id: string) => id !== "net-rescue",
          ),
        },
      },
    });
    expect(
      readRunRecord(
        {
          ...run,
          kind: "checkpoint",
          checkpoint: { ...start, state: { ...start.state, tick: -1 } },
        },
        whaleLevel,
        "journey",
      ),
    ).toBeUndefined();
  }
  const arrived = { ...run, kind: "arrived", route: "quiet", tick: 16922 };
  expect(readRunRecord(arrived, whaleLevel, "journey")).toEqual({
    ...arrived,
    levelRevision: whaleLevel.levelRevision,
  });
});

test("WH-A08 restores whale-p2-2 checkpoints without moving the saved pod", () => {
  for (const name of ["W2-C1-to-W3-wide", "W4-shallow-entry-from-C2"]) {
    const url = new URL(
      `../../docs/plans/whale/evidence/p2-2/${name}.json.gz`,
      import.meta.url,
    );
    const { start } = JSON.parse(gunzipSync(readFileSync(url)).toString());
    expect(start.state.levelRevision).toBe("whale-p2-2");
    expect(readCheckpoint(start, whaleLevel, "journey")).toEqual({
      ...start,
      state: {
        ...start.state,
        levelRevision: whaleLevel.levelRevision,
        supply: { ...start.state.supply, "net-kelp": 0.38 },
      },
    });
  }
});

test("WH-A08 restores W2's archived C1 with the new kelp bed stocked", () => {
  const url = new URL(
    "../../docs/plans/whale/evidence/p2-3/W2-C1-to-W3-short.json.gz",
    import.meta.url,
  );
  const { start } = JSON.parse(gunzipSync(readFileSync(url)).toString());
  expect(start.state.levelRevision).toBe("whale-p2-3");
  expect(readCheckpoint(start, whaleLevel, "journey")).toEqual({
    ...start,
    state: {
      ...start.state,
      levelRevision: whaleLevel.levelRevision,
      supply: { ...start.state.supply, "net-kelp": 0.38 },
    },
  });
});

test("WH-A08 reopens the previous whale revision without resetting its C1 phase", () => {
  const url = new URL(
    "../../docs/plans/whale/evidence/p2-6/W2-kelp-short-C1-to-W3.json.gz",
    import.meta.url,
  );
  const { start } = JSON.parse(gunzipSync(readFileSync(url)).toString());
  expect(start.state.levelRevision).toBe("whale-p2-6");
  const restored = readCheckpoint(start, whaleLevel, "journey");
  expect(restored).toEqual({
    ...start,
    state: { ...start.state, levelRevision: whaleLevel.levelRevision },
  });
});

test.each([
  "whale-p2-4",
  "whale-p2-5",
  "whale-p2-6",
  "whale-p2-7",
  "whale-p2-8",
  "whale-p2-9",
])("WH-A08 %s checkpoints reopen with the same pod and supply", (revision) => {
  const { checkpoints } = whaleTrip("journey", "quiet");
  expect(checkpoints.map(({ id }) => id)).toEqual(["C1", "C2"]);
  for (const { state, ...checkpoint } of checkpoints) {
    const supply = { ...state.supply, "net-kelp": 0.19 };
    expect(
      readCheckpoint(
        {
          ...checkpoint,
          state: { ...state, supply, levelRevision: revision },
        },
        whaleLevel,
        "journey",
      ),
    ).toEqual({
      ...checkpoint,
      state: { ...state, supply },
    });
  }
});

test("WH-A08 keeps the completed p2-7 voyage and its route", () => {
  const previous = {
    version: 1,
    species: "whale",
    levelId: "whale",
    mode: "journey",
    runId: "0123456789abcdef0123456789abcdef",
    levelRevision: "whale-p2-7",
    kind: "arrived",
    route: "quiet",
    tick: 12279,
  };
  expect(readRunRecord(previous, whaleLevel, "journey")).toEqual({
    ...previous,
    levelRevision: whaleLevel.levelRevision,
  });
});

test("WH-A07 W3 compares both channels from the same state to C2", async () => {
  const shippingReplay = whaleTrip("journey", "shipping");
  const quietReplay = whaleTrip("journey", "quiet");
  const noise = whaleLevel.zones.find(isCyclicNoise);
  if (!noise) throw new Error("Missing shipping noise band");
  const reference = new GameRuntime(whaleLevel, "journey");
  let fork: WhaleState | undefined;
  for (const input of shippingReplay.inputs) {
    reference.dispatch({ type: "input", input });
    reference.step();
    const state = reference.current;
    if (state.segmentId === "W3") fork ??= state;
    if (state.actors.some(({ pos }) => contains(noise.points, pos))) break;
  }
  if (
    !fork ||
    !reference.current.actors.some(({ pos }) => contains(noise.points, pos))
  )
    throw new Error("Shipping replay did not reach the noise band");
  const prefixTicks = fork.tick;
  expect(shippingReplay.inputs.slice(0, prefixTicks)).toEqual(
    quietReplay.inputs.slice(0, prefixTicks),
  );
  // Stage entry at the start of an active cycle so the comparison still
  // exercises the pressure from noise after earlier legs are retimed.
  const { phaseTicks, periodTicks } = noise.cycle;
  const entryPhase = (reference.current.tick + phaseTicks) % periodTicks;
  const start = {
    ...fork,
    tick: fork.tick + ((periodTicks - entryPhase) % periodTicks),
  };
  function measure(route: WhaleRoute) {
    const runtime = new GameRuntime(whaleLevel, "journey", {
      version: 1,
      id: "C1",
      state: start,
    });
    const replay = route === "shipping" ? shippingReplay : quietReplay;
    let distanceSwum = 0;
    let minimumEnergy = 1;
    let minimumCohesion = 1;
    let maximumTailGap = 0;
    let tailGapSum = 0;
    let tailGapSamples = 0;
    for (const input of replay.inputs.slice(prefixTicks)) {
      const before = podLeader(runtime.current).pos;
      runtime.dispatch({ type: "input", input });
      runtime.step();
      const state = runtime.current;
      const leader = podLeader(state);
      const tail = state.actors.at(-1);
      if (!tail) throw new Error("Missing tail whale");
      distanceSwum += distance(before, leader.pos);
      minimumEnergy = Math.min(minimumEnergy, state.energy);
      minimumCohesion = Math.min(minimumCohesion, state.cohesion);
      const tailGap = distance(leader.pos, tail.pos);
      maximumTailGap = Math.max(maximumTailGap, tailGap);
      if (leader.pos.z >= 1080 && leader.pos.z < 1200) {
        tailGapSum += tailGap;
        tailGapSamples++;
      }
      if (runtime.checkpoint.id === "C2") {
        if (!tailGapSamples) throw new Error("Missing W3 channel samples");
        return {
          distanceSwum,
          minimumEnergy,
          minimumCohesion,
          maximumTailGap,
          cruisingMeanTailGap: tailGapSum / tailGapSamples,
          seconds: (state.tick - start.tick) / 60,
          c2Tick: state.tick,
          c2Energy: state.energy,
        };
      }
    }
    throw new Error(`No C2 for ${route}`);
  }
  const shipping = measure("shipping");
  const quiet = measure("quiet");
  expect(shipping.seconds).toBeLessThan(quiet.seconds);
  expect(shipping.distanceSwum).toBeLessThan(quiet.distanceSwum);
  expect(shipping.minimumCohesion).toBeLessThan(quiet.minimumCohesion);
  expect(shipping.cruisingMeanTailGap).toBeGreaterThan(
    quiet.cruisingMeanTailGap,
  );
  const output = process.env.FEATHER_REPLAY_DIR;
  if (output) {
    await mkdir(output, { recursive: true });
    await writeFile(
      join(output, "W3-route-comparison.json"),
      JSON.stringify(
        {
          levelRevision: whaleLevel.levelRevision,
          fromTick: start.tick,
          startEnergy: start.energy,
          shipping,
          quiet,
        },
        null,
        2,
      ) + "\n",
    );
  }
});

test("WH-A07 the shared gate edge chooses once and only a forward crossing can reselect before merge", () => {
  const entry = withLeaderAt({ x: -36, z: 1039.95 }, "journey", "surface");
  const first = tickWorld(entry, forwardSwim, whaleLevel);
  expect(first.events.filter(({ type }) => type === "route")).toEqual([
    { type: "route", route: "shipping" },
  ]);
  const returning = withLeaderAt({ x: -70, z: 1040.05 }, "journey", "surface");
  const backwards = tickWorld(
    {
      ...first.state,
      actors: returning.actors.map((actor, i) =>
        i === 0 ? { ...actor, heading: Math.PI } : actor,
      ),
    },
    { move: { x: 0, z: -0.83 }, ability: false },
    whaleLevel,
  );
  expect(podLeader(backwards.state).pos.z).toBeLessThan(1040);
  expect(backwards.state.route).toBe("shipping");
  expect(backwards.events.some(({ type }) => type === "route")).toBe(false);

  const secondEntry = withLeaderAt(
    { x: -70, z: 1039.95 },
    "journey",
    "surface",
  );
  const second = tickWorld(
    { ...backwards.state, actors: secondEntry.actors },
    forwardSwim,
    whaleLevel,
  );
  expect(second.events).toContainEqual({ type: "route", route: "quiet" });
  expect(second.state.triggered).toContain("quiet-gate");
  expect(second.state.triggered).not.toContain("ship-gate");

  const merge = withLeaderAt({ x: 72, z: 1289.95 }, "journey", "surface");
  const locked = tickWorld(
    { ...second.state, actors: merge.actors },
    forwardSwim,
    whaleLevel,
  ).state;
  expect(locked.routeLocked).toBe(true);
  const afterLock = tickWorld(
    { ...locked, actors: entry.actors },
    forwardSwim,
    whaleLevel,
  );
  expect(afterLock.state.route).toBe("quiet");
  expect(afterLock.events.some(({ type }) => type === "route")).toBe(false);
});

test("WH-A04 collision sweeps relative motion and uses the old layer up to a layer-switch endpoint", () => {
  const ship = whaleLevel.zones.find(
    (zone) => zone.kind === "hazard" && zone.id === "cargo-ship",
  );
  if (!ship || ship.kind !== "hazard") throw new Error("Missing cargo ship");
  const moving = {
    ...ship,
    points: [
      { x: -12, z: 408 },
      { x: -8, z: 408 },
      { x: -8, z: 428 },
      { x: -12, z: 428 },
      { x: -12, z: 408 },
    ],
    motion: { travel: { x: 20, z: 0 }, periodTicks: 2, phaseTicks: 0 },
  };
  const a = { x: 0.3, z: 417 };
  const b = { x: -0.3, z: 417 };
  expect(sweptWaterHazard(moving, a, a, WHALE.hitRadius, 0, 0)).toBe(false);
  expect(sweptWaterHazard(moving, b, b, WHALE.hitRadius, 1, 1)).toBe(false);
  expect(sweptWaterHazard(moving, a, b, WHALE.hitRadius, 0, 1)).toBe(true);

  const state = withLeaderAt({ x: 0, z: 406.25 }, "journey", "surface", 3600);
  const leader = podLeader(state);
  const result = tickWorld(
    {
      ...state,
      actors: [
        {
          ...leader,
          dive: {
            ...leader.dive,
            depth: 59 / 60,
            progress: 59 / 60,
            direction: "down",
          },
        },
        ...state.actors.slice(1),
      ],
    },
    { ...forwardSwim, ability: true },
    whaleLevel,
  );

  expect(result.events).toContainEqual({
    type: "zone",
    id: ship.id,
    entered: true,
  });
  const after = podLeader(whaleState(result.state));
  expect(after.pos).toEqual(leader.pos);
  expect(after.dive.layer).toBe("shallow");
});

test("WH-A04 releasing dive early cannot switch a whale into the hull's layer", () => {
  const state = withLeaderAt({ x: 0, z: 418 }, "journey", "deep", 3600);
  const leader = podLeader(state);
  const almostShallow = {
    ...state,
    actors: [
      {
        ...leader,
        dive: {
          ...leader.dive,
          direction: "up" as const,
          depth: 1 + 1 / 72,
          progress: 71 / 72,
        },
      },
      ...state.actors.slice(1).map((actor) => withLayer(actor, "deep")),
    ],
  };
  const released = tickWorld(almostShallow, forwardSwim, whaleLevel);
  const held = tickWorld(
    almostShallow,
    { ...forwardSwim, ability: true },
    whaleLevel,
  );
  expect(podLeader(whaleState(released.state)).dive.layer).toBe("deep");
  expect(released.events).toContainEqual({
    type: "zone",
    id: "cargo-ship",
    entered: true,
  });
  expect(held.events).not.toContainEqual({
    type: "zone",
    id: "cargo-ship",
    entered: true,
  });
  expect(podLeader(whaleState(held.state)).pos.z).toBeGreaterThan(leader.pos.z);
});

test("WH-A04 a breath-depleted whale cannot switch into the hull's layer", () => {
  const state = withLeaderAt({ x: 0, z: 418 }, "journey", "deep", 3600);
  const leader = podLeader(state);
  const runtime = new GameRuntime(whaleLevel, "journey", {
    version: 1,
    id: "start",
    state: {
      ...state,
      actors: [
        {
          ...leader,
          speed: 0,
          dive: {
            ...leader.dive,
            breath: 0,
            forced: true,
            needsRelease: true,
            direction: "up",
            depth: 1 + 1 / 72,
            progress: 71 / 72,
          },
        },
        ...state.actors.slice(1),
      ],
    },
  });
  const blocked = advance(runtime, 1, dive);
  expect(podLeader(blocked).dive).toMatchObject({
    layer: "deep",
    direction: "up",
    forced: true,
  });
  expect(podLeader(advance(runtime, 500, dive)).dive).toMatchObject({
    layer: "surface",
    direction: null,
    needsRelease: true,
  });
  expect(runtime.current.phase).toBe("playing");
});

test("WH-A05 the W1 warning edge is at least three seconds before the hull at cruise", () => {
  const ship = whaleLevel.zones.find(
    (zone) => zone.kind === "hazard" && zone.id === "cargo-ship",
  );
  const warning = whaleLevel.zones.find(({ id }) => id === "ship-approach");
  if (!ship || !warning) throw new Error("Missing ship or warning");
  const appear = Math.min(...warning.points.map((point) => point.z));
  const contact =
    Math.min(...ship.points.map((point) => point.z)) - WHALE.hitRadius;
  expect((contact - appear) / WHALE.cruise).toBeGreaterThanOrEqual(3);
});

test("WH-A05 W1 can coast to a stop after three seconds of reaction time", async () => {
  const staged = podAt({ x: 0, z: 372 }, "journey", 3334);
  const start = {
    id: "start",
    version: 1 as const,
    state: {
      ...staged,
      segmentId: "W1",
      occupied: ["waiting-water", "ship-approach"],
      actors: staged.actors.map((actor, i) =>
        i === 0 ? { ...actor, speed: WHALE.cruise } : actor,
      ),
    },
  };
  const runtime = new GameRuntime(whaleLevel, "journey", start);
  const inputs: WorldInput[] = [];
  const events: { tick: number; event: GameEvent }[] = [];
  for (let step = 0; step < 310; step++) {
    runtime.dispatch({
      type: "input",
      input:
        step < 180
          ? { move: { x: 0, z: 0.89 }, ability: false }
          : NEUTRAL_INPUT,
    });
    for (const event of runtime.step((_, used) => inputs.push(used)))
      events.push({ tick: runtime.current.tick, event });
  }
  const leader = podLeader(runtime.current);
  const ship = whaleLevel.zones.find((zone) => zone.id === "cargo-ship");
  if (!ship) throw new Error("Missing ship");
  const nearestEdge = Math.min(...ship.points.map(({ z }) => z));
  expect(leader.speed).toBe(0);
  expect(leader.pos.z).toBeLessThan(nearestEdge - WHALE.hitRadius);
  expect(events.map(({ event }) => event)).not.toContainEqual({
    type: "zone",
    id: "cargo-ship",
    entered: true,
  });
  await writeReplay("W1-reaction-coast", {
    levelRevision: whaleLevel.levelRevision,
    mode: "journey",
    start,
    inputs,
    events,
    expected: runtime.current,
  });
});

test("WH-A05 a low-breath pod can brake and follow W1 guidance back to safe water", async () => {
  const start = {
    version: 1 as const,
    id: "start",
    state: {
      ...withLeaderAt({ x: 0, z: 389 }, "journey", "deep", 3500),
      segmentId: "W1",
      occupied: ["ship-approach"],
    },
  };
  const state = {
    ...start.state,
    actors: start.state.actors.map((actor) => ({
      ...withLayer(actor, "deep"),
      dive: {
        ...withLayer(actor, "deep").dive,
        breath: 0.055,
      },
    })),
  };
  const hud = whaleGuidance(state, whaleLevel, false, {
    dragged: false,
    reset: false,
    moved: true,
    stopped: false,
    submerged: false,
    recovered: false,
    toggle: false,
    desktop: true,
  });
  const marker = hud.markers.find(({ id }) => id === "whale-refill");
  const waiting = whaleLevel.zones.find(({ id }) => id === "waiting-water");
  if (!marker || !waiting) throw new Error("Missing W1 refill marker");
  expect(hud.notice).toBe("呼吸偏低");
  expect(hud.warningDetail).toContain("先在船道外换气");
  expect(contains(waiting.points, marker.pos)).toBe(true);
  const snapshot = { ...start, state };
  const runtime = new GameRuntime(whaleLevel, "journey", snapshot);
  const inputs: WorldInput[] = [];
  const events: { tick: number; event: GameEvent }[] = [];
  let settled = false;
  for (let step = 0; step < 1500; step++) {
    const leader = podLeader(runtime.current);
    settled ||=
      contains(waiting.points, leader.pos) &&
      distance(leader.pos, marker.pos) < 2.5;
    const input =
      step < 540 || settled ? NEUTRAL_INPUT : aim(leader.pos, marker.pos, 0.5);
    runtime.dispatch({ type: "input", input });
    for (const event of runtime.step((_, used) => inputs.push(used)))
      events.push({ tick: runtime.current.tick, event });
    if (
      settled &&
      runtime.current.actors.every(
        ({ dive }) => dive.layer === "surface" && dive.breath >= 0.95,
      )
    )
      break;
  }
  expect(settled).toBe(true);
  expect(runtime.current.phase).toBe("playing");
  expect(runtime.current.actors.every(({ dive }) => dive.breath >= 0.95)).toBe(
    true,
  );
  expect(contains(waiting.points, podLeader(runtime.current).pos)).toBe(true);
  expect(events).not.toContainEqual(
    expect.objectContaining({
      event: { type: "zone", id: "cargo-ship", entered: true },
    }),
  );
  await writeReplay("W1-low-air-refill", {
    levelRevision: whaleLevel.levelRevision,
    mode: state.mode,
    start: snapshot,
    inputs,
    events,
    expected: runtime.current,
  });
});
