import { expect, test } from "vitest";
import type { GameMode } from "../../src/core/game";
import { readCheckpoint, readRunRecord } from "../../src/core/save";
import type { Vec2 } from "../../src/core/math";
import { validateLevel, type WhaleLevel } from "../../src/levels/schema";
import { initialState } from "../../src/simulation/world";
import migrationData from "../../public/levels/migration.json";

function strip(z: number): readonly Vec2[] {
  return [
    { x: -20, z },
    { x: 20, z },
    { x: 20, z: z + 40 },
    { x: -20, z: z + 40 },
    { x: -20, z },
  ];
}

const level: WhaleLevel = {
  schemaVersion: 1,
  id: "whale",
  levelRevision: "whale-test",
  title: "Whale persistence fixture",
  species: "whale",
  modes: ["journey"],
  bounds: { min: { x: -50, z: -30 }, max: { x: 50, z: 600 } },
  spawn: { x: 0, z: 0 },
  spawnSegment: "W0",
  segments: [
    {
      id: "W0",
      title: "Bay",
      start: -30,
      wind: { x: 0, z: 0 },
      color: "#416b89",
    },
  ],
  routes: ["shipping", "quiet"],
  zones: [
    { id: "C1", label: "Bay", kind: "checkpoint", points: strip(120) },
    {
      id: "supply",
      label: "Bay",
      kind: "supply",
      capacity: 0.4,
      points: strip(120),
    },
    { id: "C2", label: "Sea", kind: "checkpoint", points: strip(420) },
  ],
  triggers: [
    {
      id: "shipping-gate",
      label: "Shipping",
      kind: "route",
      route: "shipping",
      crossingZ: 240,
      points: strip(230),
    },
    {
      id: "quiet-gate",
      label: "Quiet",
      kind: "route",
      route: "quiet",
      crossingZ: 240,
      points: strip(230),
    },
    { id: "merge", label: "Join", kind: "merge", points: strip(360) },
  ],
  landmarks: [],
};

const start = {
  version: 1 as const,
  kind: "started" as const,
  species: "whale" as const,
  levelId: level.id,
  levelRevision: level.levelRevision,
  mode: "journey" as const,
  runId: "a".repeat(32),
};

function bayCheckpoint(mode: GameMode) {
  const initial = initialState(level, mode);
  return {
    version: 1 as const,
    id: "C1",
    state: {
      ...initial,
      tick: 1241,
      energy: 0.64,
      cohesion: 0.8,
      supply: { supply: 0.28 },
      occupied: ["supply"],
      triggered: ["C1"],
      actors: initial.actors.map((actor) => ({
        ...actor,
        pos: { ...actor.pos, z: actor.pos.z + 150 },
      })),
    },
  };
}

test("whale run records are tied to one species, chapter, mode and revision", () => {
  expect(readRunRecord(start, level, "journey")).toEqual(start);
  expect(
    readRunRecord({ ...start, mode: "roam" }, level, "journey"),
  ).toBeUndefined();
  expect(
    Reflect.apply(readRunRecord, undefined, [
      { ...start, mode: "roam" },
      level,
      "roam",
    ]),
  ).toBeUndefined();
  const migration = validateLevel(migrationData, "migration.json", "goose");
  expect(readRunRecord(start, migration, "journey")).toBeUndefined();
  for (const record of [
    { ...start, runId: "bad" },
    { ...start, version: 2 },
    { ...start, levelRevision: "whale-old" },
    { ...start, levelId: "different-chapter" },
    { ...start, species: undefined },
  ]) {
    expect(readRunRecord(record, level, "journey")).toBeUndefined();
  }
  const arrived = {
    ...start,
    kind: "arrived",
    route: "quiet",
    tick: 7822,
  };
  expect(readRunRecord(arrived, level, "journey")).toEqual(arrived);
  expect(
    readRunRecord({ ...arrived, route: "lake" }, level, "journey"),
  ).toBeUndefined();
});

test("C1 restores the entire pod and resources, and rejects corrupt state", () => {
  const checkpoint = bayCheckpoint("journey");
  const state = checkpoint.state;
  const callerRecord = { ...start, kind: "checkpoint", checkpoint };
  expect(readRunRecord(callerRecord, level, "journey")).toEqual(callerRecord);
  expect(
    readCheckpoint(
      { ...checkpoint, state: { ...state, mode: "roam" } },
      level,
      "journey",
    ),
  ).toBeUndefined();
  for (const badState of [
    { ...state, actors: state.actors.slice(1) },
    {
      ...state,
      actors: state.actors.map((actor) => ({ ...actor, id: "whale-0" })),
    },
    {
      ...state,
      actors: state.actors.map((actor) => ({
        ...actor,
        dive: { ...actor.dive, breath: NaN },
      })),
    },
    {
      ...state,
      actors: state.actors.map((actor) => ({
        ...actor,
        dive: { ...actor.dive, layer: "abyss" },
      })),
    },
    { ...state, diveInputTicks: -500 },
    { ...state, occupied: ["missing"] },
    { ...state, supply: { supply: 0.41 } },
    { ...state, route: "quiet", triggered: ["C1", "quiet-gate"] },
  ]) {
    expect(
      readCheckpoint({ ...checkpoint, state: badState }, level, "journey"),
    ).toBeUndefined();
  }
});

test("C2 retains the crossed route and verifies the merge was committed", () => {
  const c1 = bayCheckpoint("journey");
  const state = {
    ...c1.state,
    tick: 9400,
    route: "quiet",
    routeLocked: true,
    triggered: ["C1", "quiet-gate", "merge", "C2"],
    actors: c1.state.actors.map((actor) => ({
      ...actor,
      pos: { ...actor.pos, z: actor.pos.z + 300 },
    })),
  };
  const c2 = { ...c1, id: "C2", state };
  expect(readCheckpoint(c2, level, "journey")).toEqual(c2);
  for (const badState of [
    { ...state, route: "shipping" },
    { ...state, routeLocked: false },
    { ...state, triggered: ["C1", "quiet-gate", "C2"] },
  ]) {
    expect(
      readCheckpoint({ ...c2, state: badState }, level, "journey"),
    ).toBeUndefined();
  }
});

test("legacy untagged goose start, checkpoint and arrival remain readable", () => {
  const migration = validateLevel(migrationData, "migration.json", "goose");
  const initial = initialState(migration, "journey");
  const legacy = {
    version: 1 as const,
    runId: "b".repeat(32),
    levelRevision: migration.levelRevision,
  };
  const started = { ...legacy, kind: "started" };
  const arrived = { ...legacy, kind: "arrived", tick: 1432, route: "lake" };
  const checkpoint = {
    version: 1,
    id: "A",
    state: { ...initial, triggered: ["A"] },
  };
  const state = Object.fromEntries(
    Object.entries(checkpoint.state).filter(([key]) => key !== "species"),
  );
  const saved = {
    ...legacy,
    kind: "checkpoint",
    checkpoint: { ...checkpoint, state },
  };
  expect(readRunRecord(started, migration, "journey")).toEqual(started);
  expect(readRunRecord(arrived, migration, "journey")).toEqual(arrived);
  expect(readRunRecord(saved, migration, "journey")).toEqual({
    ...saved,
    checkpoint,
  });
});
