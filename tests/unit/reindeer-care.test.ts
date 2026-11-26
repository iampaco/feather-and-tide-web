import { expect, test } from "vitest";
import { NEUTRAL_INPUT } from "../../src/core/game";
import { distance } from "../../src/core/math";
import { reindeerGatherStatus } from "../../src/simulation/reindeer-care";
import { sampleReindeerDust } from "../../src/simulation/reindeer-dust";
import { REINDEER as R } from "../../src/simulation/reindeer-tuning";
import { tickWorld, leaderOf } from "../../src/simulation/world";
import { validateLevel } from "../../src/levels/schema";
import { groundBlocked, hoofRadius } from "../../src/levels/reindeer-ground";
import {
  herdAt,
  reindeerLevel as level,
  reindeerSource,
} from "../fixtures/reindeer";

test("calling physically shortens the herd compared with an ordinary stop", () => {
  const start = herdAt({ x: 0, z: 35 });
  let normal = start,
    called = start;
  for (let tick = 0; tick < 300; tick++) {
    normal = tickWorld(normal, NEUTRAL_INPUT, level).state;
    called = tickWorld(
      called,
      { ...NEUTRAL_INPUT, ability: true },
      level,
    ).state;
  }
  const tailGap = (state: typeof start) =>
    distance(state.actors[8]!.pos, leaderOf(state).pos);
  expect(tailGap(called)).toBeLessThan(tailGap(normal) - 3);
  expect(reindeerGatherStatus(normal, level).ready).toBe(false);
  expect(reindeerGatherStatus(called, level)).toMatchObject({
    ready: true,
    gathered: 9,
    total: 9,
  });
  expect(called.actors.map(({ id }) => id)).toEqual(
    start.actors.map(({ id }) => id),
  );
});

test("a completed call cannot report separated, distant or rejoining deer as gathered", () => {
  const base = herdAt({ x: 0, z: 35 }, { waitTicks: R.waitTicks });
  for (const status of ["following", "rejoining", "strayed"] as const) {
    const state = {
      ...base,
      actors: base.actors.map((actor, i) => ({
        ...actor,
        pos: { x: 0, z: i === 8 ? 10 : 35 },
        status: i === 8 ? status : actor.status,
      })),
    };
    expect(reindeerGatherStatus(state, level)).toMatchObject({
      ready: false,
      gathered: 8,
      outOfRangeIds: ["reindeer-8"],
    });
  }
  const fence = herdAt({ x: -10, z: 274 }, { waitTicks: R.waitTicks });
  const blocked = {
    ...fence,
    actors: fence.actors.map((actor, i) => ({
      ...actor,
      pos: { x: -10, z: i === 8 ? 264 : 274 },
    })),
  };
  expect(reindeerGatherStatus(blocked, level)).toMatchObject({
    ready: false,
    blockedIds: ["reindeer-8"],
  });
});

test("dust has exact repeatable calm, four-second warning and active boundaries", () => {
  const pos = { x: 17, z: 375 };
  for (const [tick, phase, strain] of [
    [0, "calm", 0],
    [1199, "calm", 0],
    [1200, "warning", 0],
    [1439, "warning", 0],
    [1440, "active", 0.55],
    [2159, "active", 0.55],
    [2160, "calm", 0],
  ] as const) {
    expect(sampleReindeerDust(level, tick, pos)).toMatchObject({
      phase,
      strain,
      inDust: true,
    });
    expect(sampleReindeerDust(level, tick + 2160, pos)).toEqual(
      sampleReindeerDust(level, tick, pos),
    );
  }
  expect(sampleReindeerDust(level, 1440, { x: 17, z: 403 }).strain).toBe(0);
  expect(sampleReindeerDust(level, 1440, { x: 17, z: 430 }).strain).toBe(0.55);
});

test("only exposed companions slow down when the leader has left the dust", () => {
  const forward = { move: { x: 0, z: 0.84 }, ability: false };
  let moving = herdAt({ x: 17, z: 450 }, { energy: 0.8 });
  for (let i = 0; i < 60; i++) moving = tickWorld(moving, forward, level).state;
  const base = { ...moving, tick: 1440 };
  const calm = { ...base, tick: 0 };
  const activeResult = tickWorld(base, forward, level).state;
  const calmResult = tickWorld(calm, forward, level).state;
  expect(activeResult.actors[8]!.speed).toBeLessThan(
    calmResult.actors[8]!.speed,
  );
  expect(activeResult.energy).toBeLessThan(calmResult.energy);
  const before = herdAt({ x: 17, z: 353 }, { tick: 1440 });
  expect(tickWorld(before, NEUTRAL_INPUT, level).state.energy).toBe(
    tickWorld({ ...before, tick: 0 }, NEUTRAL_INPUT, level).state.energy,
  );
});

test("dust data rejects fractional periods, missing zones and insufficient warning", () => {
  const raw = reindeerSource as Record<string, unknown>;
  for (const patch of [
    { calmTicks: 1.5 },
    { warningTicks: 179 },
    { zoneIds: ["missing"] },
    { zoneIds: ["dust-bank", "dust-bank"] },
    { phaseTicks: 2160 },
  ])
    expect(() =>
      validateLevel(
        { ...raw, dustCycle: { ...level.dustCycle, ...patch } },
        "test",
        "reindeer",
      ),
    ).toThrow("dustCycle");
});

test("every painted trail segment is actually traversable by the largest companion", () => {
  for (const trail of level.trails)
    for (let i = 1; i < trail.points.length; i++) {
      const from = trail.points[i - 1],
        to = trail.points[i];
      if (!from || !to) throw new Error("Incomplete trail");
      expect(groundBlocked(level, from, to, hoofRadius(8)), trail.id).toBe(
        false,
      );
    }
});
