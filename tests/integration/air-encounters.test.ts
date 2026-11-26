import { gzipSync } from "node:zlib";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";
import { FixedClock } from "../../src/core/clock";
import type { GooseState, WorldInput } from "../../src/core/game";
import { GameRuntime } from "../../src/core/runtime";
import { readCheckpoint } from "../../src/core/save";
import {
  advanceEncounters,
  initialEncounters,
  kitePose,
  gliderPose,
} from "../../src/simulation/air-encounters";
import { GOOSE } from "../../src/simulation/goose";
import { initialState } from "../../src/simulation/world";
import { aim, migration } from "../fixtures/flight";
import { tailwindPractice } from "../../src/levels/tailwind-practice";

const config = migration.encounters;
if (!config) throw new Error("Missing migration encounters");
const course = config;
const initial = initialState(migration, "journey");
const birds = initial.actors;
const phases = initialEncounters();

test("the family holds for every bird, including a distant tail and a returning leader", () => {
  const beyond = birds.map((actor) => ({
    ...actor,
    pos: { x: 0, z: course.kite.clearZ + 1 },
  }));
  const held = { ...phases, kite: "holding" as const };
  for (const n of [1, 11, 12]) {
    const flock = beyond.map((a, i) =>
      i < n ? a : { ...a, pos: { x: -80, z: course.kite.clearZ - 1 } },
    );
    const next = advanceEncounters(course, held, 900, flock, flock);
    expect(next.kite).toBe(n === 12 ? "rising" : "holding");
  }
  const back = beyond.map((a, i) =>
    i === 0 ? { ...a, pos: course.kite.bank } : a,
  );
  expect(advanceEncounters(course, held, 900, back, back).kite).toBe("holding");
});

test("a raised kite reacts to the bird sweeping past; held paper and its string are safe", () => {
  const previous = birds.map((a, i) => ({
    ...a,
    speed: GOOSE.cruise,
    pos:
      i === 9
        ? { x: course.kite.aloft.x - 9, z: course.kite.aloft.z }
        : { x: -60, z: 12 },
  }));
  const after = previous.map((a, i) =>
    i === 9 ? { ...a, pos: { ...a.pos, x: a.pos.x + 18 } } : a,
  );
  const next = advanceEncounters(course, phases, 1, previous, after);
  expect(next.wingAt).toEqual({ "goose-9": 1 });
  expect(next.disrupted).toBe(false);
  const held = { ...phases, kite: "holding" as const };
  const point = kitePose(course.kite, held, 2);
  const under = birds.map((a) => ({ ...a, pos: point, speed: 1 }));
  expect(advanceEncounters(course, held, 2, under, under).wingAt).toEqual({});
});

test("near-bank flight can brush the kite without changing any simulation rule for the flock", () => {
  const withKite = new GameRuntime(migration, "journey");
  const withoutKite = new GameRuntime(
    { ...migration, encounters: undefined },
    "journey",
  );
  let reacted = false;
  while (withKite.current.segmentId === "S0" && withKite.current.tick < 1200) {
    const p = withKite.current.actors[0]?.pos;
    if (!p) throw new Error("Missing leader");
    const input = aim(p, { x: 12, z: p.z + 19 }, 1, true);
    for (const runtime of [withKite, withoutKite]) {
      runtime.dispatch({ type: "input", input });
      runtime.step();
    }
    reacted ||=
      Object.keys(withKite.current.encounters?.wingAt ?? {}).length > 0;
  }
  expect(reacted).toBe(true);
  expect({ ...withKite.current, encounters: undefined }).toEqual({
    ...withoutKite.current,
    encounters: undefined,
  });
});

type Route = "outer" | "yield" | "release" | "brush" | "tail";
function steer(route: Route, state: GooseState): WorldInput {
  const p = state.actors[0]?.pos;
  if (!p) throw new Error("Missing leader");
  if (route === "tail")
    return aim(p, { x: p.z < 138 ? -27 : -22, z: p.z + 28 }, 0.84, p.z >= 100);
  if (route === "brush" && p.z >= 160)
    return aim(p, { x: 20, z: p.z + 16 }, 0.84, true);
  if (p.z < 94 || route === "brush")
    return { move: { x: 0, z: 0.84 }, ability: p.z >= 103 };
  if (route === "yield")
    return aim(
      p,
      { x: p.z < 148 ? 0 : 18, z: p.z + 18 },
      p.z > 124 && p.z < 148 ? 0.22 : 0.84,
      p.z >= 100,
    );
  if (route === "release")
    return aim(
      p,
      { x: p.z < 124 ? 0 : -36, z: p.z + 16 },
      0.84,
      p.z >= 100 && (p.z < 126 || p.z > 159),
    );
  return aim(p, { x: -36, z: p.z + 24 }, 0.84, p.z >= 100);
}

function play(route: Route) {
  const runtime = new GameRuntime(migration, "journey");
  const inputs: WorldInput[] = [],
    changes: { tick: number; ids: string[]; formation: number }[] = [];
  const samples: {
    tick: number;
    x: number;
    z: number;
    formation: number;
    kite?: string;
    glider?: string;
  }[] = [];
  let second = 0,
    warned = 0,
    touchedAt = 0,
    recovered = 0,
    clearingEnded = 0;
  while (runtime.current.segmentId !== "S2" && runtime.current.tick < 3000) {
    const before = runtime.current;
    const input = steer(route, before);
    inputs.push(input);
    runtime.dispatch({ type: "input", input });
    runtime.step();
    const s = runtime.current,
      e = s.encounters;
    if (!e) throw new Error("Missing encounter snapshot");
    if (e.glider === "inflating" && !warned) warned = s.tick;
    if (e.disrupted && !before.encounters?.disrupted) {
      touchedAt = s.tick;
      changes.push({
        tick: s.tick,
        ids: Object.keys(e.wingAt),
        formation: s.formation,
      });
    }
    if (before.encounters?.clearingWing && !e.clearingWing)
      clearingEnded = s.tick;
    if (touchedAt && !recovered && s.formation === 1) recovered = s.tick;
    if (s.occupied.includes("tailwind-second")) second++;
    if (
      s.tick % 30 === 0 ||
      before.encounters?.glider !== e.glider ||
      before.encounters?.kite !== e.kite
    ) {
      const p = s.actors[0]?.pos;
      if (p)
        samples.push({
          tick: s.tick,
          ...p,
          formation: s.formation,
          kite: e.kite,
          glider: e.glider,
        });
    }
  }
  const dir = process.env.FEATHER_AIR_EVIDENCE;
  if (dir) {
    mkdirSync(dir, { recursive: true });
    writeFileSync(
      join(dir, route + ".json.gz"),
      gzipSync(
        JSON.stringify({
          revision: migration.levelRevision,
          route,
          inputs,
          samples,
          changes,
          second,
          clearingEnded,
          recovered,
        }),
      ),
    );
  }
  return {
    runtime,
    inputs,
    changes,
    second,
    warned,
    touchedAt,
    clearingEnded,
    recovered,
  };
}

test.each(["outer", "yield", "release", "brush", "tail"] as const)(
  "journey route %s safely reaches A with the expected wing response",
  (route) => {
    const r = play(route);
    expect(r.runtime.checkpoint.id).toBe("A");
    expect(r.runtime.current.segmentId).toBe("S2");
    expect(r.runtime.current.actors).toHaveLength(12);
    expect(r.runtime.current.actors.every((a) => a.rescueTicks === null)).toBe(
      true,
    );
    expect(r.runtime.current.energy).toBeGreaterThan(0);
    if (route === "brush" || route === "tail") {
      expect(r.changes).toHaveLength(1);
      expect(r.changes[0]?.ids).not.toContain("goose-0");
      if (route === "tail") expect(r.changes[0]?.ids).toEqual(["goose-11"]);
      expect(r.changes[0]?.formation).toBe(0);
      expect(r.touchedAt - r.warned).toBeGreaterThanOrEqual(180);
      expect(r.recovered - r.clearingEnded).toBe(GOOSE.formTicks - 1);
    } else expect(r.changes).toEqual([]);
    if (route === "yield") expect(r.second).toBeGreaterThan(120);
  },
);

test("late birds can brush after the V reforms without causing a second disruption", () => {
  const active = {
    ...phases,
    glider: "crossing" as const,
    gliderTick: 60,
    disrupted: true,
  };
  const p = gliderPose(course.glider, active, 120);
  const flock = birds.map((a, i) => ({
    ...a,
    speed: 10,
    pos: i === 11 ? p : { x: -70, z: 150 },
  }));
  const next = advanceEncounters(course, active, 120, flock, flock);
  expect(next.clearingWing).toBe(false);
  expect(next.wingAt).toEqual({ "goose-11": 120 });
});

test("fixed-step replay and pause reproduce the entire encounter and flock", () => {
  const { inputs, runtime } = play("brush");
  for (const hz of [30, 60, 120]) {
    const clock = new FixedClock(),
      r = new GameRuntime(migration, "journey");
    let time = 0;
    for (
      let frame = 0;
      r.current.tick < inputs.length && frame < 6000;
      frame++
    ) {
      clock.frame(time, true, () => {
        const input = inputs[r.current.tick];
        if (!input) return false;
        r.dispatch({ type: "input", input });
        r.step();
        if (
          r.current.encounters?.clearingWing ||
          r.current.encounters?.kite === "lowering" ||
          r.current.encounters?.glider === "inflating"
        ) {
          r.dispatch({ type: "pause" });
          const paused = r.current;
          r.step();
          expect(r.current).toBe(paused);
          r.dispatch({ type: "resume" });
        }
        return true;
      });
      time += 1000 / hz;
    }
    expect(r.current).toEqual(runtime.current);
  }
});

test("checkpoint restores a live glider phase, authentic old A marks encounters complete and practice stays independent", () => {
  const r = play("brush").runtime;
  const saved = r.checkpoint;
  expect(readCheckpoint(saved, migration, "journey")).toEqual(saved);
  const restored = new GameRuntime(migration, "journey", saved);
  expect(restored.current.encounters).toEqual(
    saved.state.species === "goose" && saved.state.encounters,
  );
  restored.dispatch({ type: "pause" });
  restored.dispatch({ type: "retry" });
  expect(restored.current.encounters).toEqual(
    r.checkpoint.state.species === "goose" && r.checkpoint.state.encounters,
  );
  const legacy = {
    ...saved,
    state: {
      ...saved.state,
      encounters: undefined,
      levelRevision: "goose-p0-8",
    },
  };
  const upgraded = readCheckpoint(legacy, migration, "journey");
  expect(upgraded?.state).toMatchObject({
    actors: saved.state.actors,
    encounters: initialEncounters(true),
  });
  expect(
    readCheckpoint(
      {
        ...saved,
        state: {
          ...saved.state,
          encounters: { ...phases, kiteTick: Infinity },
        },
      },
      migration,
      "journey",
    ),
  ).toBeUndefined();
  expect(tailwindPractice(migration).encounters).toBeUndefined();
});
