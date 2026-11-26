import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import {
  reindeerDustGuidance,
  reindeerLandingCompanion,
  reindeerPassageGuidance,
  reindeerTeammateGuidance,
  reindeerWinterTail,
} from "../../src/app/reindeer-guidance";
import { expect, test } from "vitest";
import { NEUTRAL_INPUT, type ReindeerState } from "../../src/core/game";
import { distance, type Vec2 } from "../../src/core/math";
import { GameRuntime } from "../../src/core/runtime";
import { readCheckpoint, readRunRecord } from "../../src/core/save";
import { groundBlocked, hoofRadius } from "../../src/levels/reindeer-ground";
import { sampleReindeerDust } from "../../src/simulation/reindeer-dust";
import { reindeerGatherStatus } from "../../src/simulation/reindeer-care";
import { goalStatus, leaderOf, tickWorld } from "../../src/simulation/world";
import {
  herdAt,
  moveTo,
  reindeerLevel as level,
  reindeerTrip,
} from "../fixtures/reindeer";

function walk(
  initial: ReindeerState,
  goals: readonly Vec2[],
  pressure = 0.84,
): ReindeerState {
  let state = initial;
  for (const target of goals) {
    for (
      let i = 0;
      i < 4500 &&
      distance(leaderOf(state).pos, target) > 0.25 &&
      state.phase === "playing";
      i++
    ) {
      const pos = leaderOf(state).pos;
      const next = tickWorld(
        state,
        moveTo(
          pos,
          target,
          distance(pos, target) < 2 ? Math.min(0.12, pressure) : pressure,
        ),
        level,
      ).state;
      expect(groundBlocked(level, pos, leaderOf(next).pos, hoofRadius(0))).toBe(
        false,
      );
      state = next;
    }
    expect(state.phase).toBe("playing");
    expect(distance(leaderOf(state).pos, target)).toBeLessThan(0.26);
  }
  return state;
}

for (const phase of [0, 1200, 1440, 2159]) {
  test(`R3 a safe complete dust journey exists at starting phase ${phase}`, () => {
    const { runtime, inputs, events } = reindeerTrip("dust", phase);
    expect(runtime.current.phase).toBe("landing");
    expect(events.filter(({ event }) => event.type === "strayed")).toEqual([]);
    expect(inputs.some(({ ability }) => ability)).toBe(true);
    expect(inputs.length / 60).toBeLessThan(360);
    expect(runtime.current.actors).toHaveLength(9);
  });
}

for (const phase of [0, 600, 1200, 1800]) {
  test(`R3 continuous cautious travel still completes at phase ${phase} without a call`, () => {
    const result = reindeerTrip("dust", phase, false);
    expect(result.runtime.current.phase).toBe("landing");
    expect(result.inputs.every(({ ability }) => !ability)).toBe(true);
    expect(
      result.events.filter(({ event }) => event.type === "strayed"),
    ).toEqual([]);
  });
}

test("R3 green route is longer, restores resources and remains reachable at low energy", async () => {
  const fork = herdAt(
    { x: 0, z: 337 },
    { segmentId: "R3", triggered: ["C1"], energy: 0.8 },
  );
  const green = [
    { x: -47, z: 361 },
    { x: -47, z: 400 },
    { x: -18, z: 406 },
    { x: -18, z: 451 },
    { x: 0, z: 482 },
  ];
  const dust = [
    { x: 17, z: 353 },
    { x: 17, z: 403 },
    { x: 17, z: 451 },
    { x: 0, z: 482 },
  ];
  const restored = walk(fork, green);
  const short = walk(fork, dust);
  expect(restored.tick - short.tick).toBeGreaterThan(10 * 60);
  expect(restored.energy - short.energy).toBeGreaterThan(0.065);
  expect(restored.supply["green-supply"]).toBeLessThan(
    fork.supply["green-supply"]!,
  );
  const low = walk({ ...fork, energy: 0.15 }, green);
  expect(low.energy).toBeGreaterThan(0.3);
  expect(low.actors.every(({ status }) => status !== "strayed")).toBe(true);
  const output = process.env.FEATHER_REPLAY_DIR;
  if (output) {
    await mkdir(output, { recursive: true });
    await writeFile(
      join(output, "route-comparison.json"),
      JSON.stringify(
        {
          revision: level.levelRevision,
          forkEnergy: fork.energy,
          merge: {
            greenbelt: {
              seconds: restored.tick / 60,
              energy: restored.energy,
              cohesion: restored.cohesion,
            },
            dust: {
              seconds: short.tick / 60,
              energy: short.energy,
              cohesion: short.cohesion,
            },
          },
          lowEnergy: { start: 0.15, merge: low.energy },
          journeys: ["dust", "greenbelt"].map((route) => {
            const trip = reindeerTrip(route === "dust" ? "dust" : "greenbelt");
            return {
              route,
              seconds: trip.inputs.length / 60,
              callSeconds:
                trip.inputs.filter(({ ability }) => ability).length / 60,
              phase: trip.runtime.current.phase,
            };
          }),
        },
        null,
        2,
      ) + "\n",
    );
  }
});

test("R3 can change route before merging, and locks one consistent route at C2", () => {
  let state = herdAt({ x: 0, z: 337 }, { segmentId: "R3", triggered: ["C1"] });
  state = walk(state, [{ x: 17, z: 353 }]);
  expect(state.route).toBe("dust");
  state = walk(state, [
    { x: 17, z: 337 },
    { x: -47, z: 361 },
  ]);
  expect(state.route).toBe("greenbelt");
  expect(state.triggered.filter((id) => id.endsWith("-gate"))).toEqual([
    "green-gate",
  ]);
  state = walk(state, [
    { x: -47, z: 400 },
    { x: -18, z: 406 },
    { x: -18, z: 451 },
    { x: 0, z: 510 },
  ]);
  for (let i = 0; i < 300; i++)
    state = tickWorld(state, { ...NEUTRAL_INPUT, ability: true }, level).state;
  expect(state.routeLocked).toBe(true);
  expect(state.triggered).toContain("C2");
  const snapshot = { version: 1 as const, id: "C2", state };
  expect(readCheckpoint(snapshot, level, "journey")).toBeDefined();
  expect(
    readCheckpoint(
      { ...snapshot, state: { ...state, levelRevision: "reindeer-p3-1" } },
      level,
      "journey",
    ),
  ).toBeUndefined();
  const runtime = new GameRuntime(level, "journey", snapshot);
  const phase = sampleReindeerDust(level, state.tick, { x: 17, z: 375 });
  runtime.dispatch({ type: "pause" });
  for (let i = 0; i < 100; i++) runtime.step();
  expect(
    sampleReindeerDust(level, runtime.current.tick, { x: 17, z: 375 }),
  ).toEqual(phase);
  runtime.dispatch({ type: "retry" });
  expect(runtime.current).toEqual({ ...state, phase: "playing", energy: 1 });
});

test("the entire herd can stop, gather and remain safe inside the dust shelter", () => {
  let state = herdAt({ x: 17, z: 408 }, { tick: 1440, energy: 0.2 });
  for (let i = 0; i < 3000; i++)
    state = tickWorld(state, { ...NEUTRAL_INPUT, ability: true }, level).state;
  expect(reindeerGatherStatus(state, level).ready).toBe(true);
  expect(
    state.actors.every(
      (actor) => !sampleReindeerDust(level, state.tick, actor.pos).inDust,
    ),
  ).toBe(true);
  expect(state.phase).toBe("playing");
  expect(state.energy).toBeGreaterThan(0.2);
});

for (const pressure of [0.12, 0.84]) {
  test(`R2 all nine deer can negotiate the S bend at pressure ${pressure}`, () => {
    let state = walk(
      herdAt({ x: 17, z: 253 }, { segmentId: "R2" }),
      [
        { x: 17, z: 279 },
        { x: -6, z: 285 },
        { x: -6, z: 302 },
        { x: 17, z: 308 },
        { x: 17, z: 332 },
      ],
      pressure,
    );
    for (let i = 0; i < 300; i++)
      state = tickWorld(
        state,
        { ...NEUTRAL_INPUT, ability: true },
        level,
      ).state;
    expect(
      state.actors.every(
        ({ pos, status }) => pos.z > 316 && status === "following",
      ),
    ).toBe(true);
  });
}

test("R2 blocked-tail guidance points to the current row instead of the first opening", () => {
  const base = herdAt({ x: 17, z: 306 }, { segmentId: "R2" });
  const state = {
    ...base,
    trailStart: 0,
    trail: Array.from({ length: 40 }, (_, i) => ({ x: 17, z: 295 + i * 0.2 })),
    actors: base.actors.map((actor, i) => ({
      ...actor,
      pos: i === 8 ? { x: 17, z: 289 } : { x: 17, z: 306 },
      status: i === 8 ? ("loose" as const) : actor.status,
      trailIndex: 0,
    })),
  };
  expect(reindeerTeammateGuidance(state, level)).toMatchObject({
    kind: "fence",
    opening: { x: -6, z: 293 },
  });
});

test("R2 centered short turns bring all nine through sooner than the wide route", () => {
  const start = herdAt({ x: 0, z: 245 }, { segmentId: "R2" });
  const end = { x: 0, z: 337 };
  const short = walk(start, [
    { x: -1, z: 266 },
    { x: -1, z: 272 },
    { x: -6, z: 288 },
    { x: -6, z: 298 },
    { x: 3, z: 310 },
    { x: 3, z: 318 },
    { x: 3, z: 324 },
    end,
  ]);
  const wide = walk(start, [
    { x: 17, z: 253 },
    { x: 17, z: 279 },
    { x: -6, z: 285 },
    { x: -6, z: 302 },
    { x: 17, z: 308 },
    { x: 17, z: 323 },
    end,
  ]);
  for (const state of [short, wide])
    expect(
      state.actors.every(
        ({ pos, status }) => pos.z > 316 && status === "following",
      ),
    ).toBe(true);
  expect(wide.tick - short.tick).toBeGreaterThan(10 * 60);
});

test("R2 the short route can continue from R0 through both checkpoints to 9/9", () => {
  const { runtime, checkpoints, events } = reindeerTrip(
    "greenbelt",
    0,
    true,
    "short",
  );
  expect(runtime.current.phase).toBe("landing");
  expect(runtime.current.actors).toHaveLength(9);
  expect(checkpoints.map(({ id }) => id)).toEqual(["C1", "C2"]);
  expect(events.filter(({ event }) => event.type === "strayed")).toEqual([]);
});

test("R2 an early turn leaves a recoverable tail, and a same-side call can clear the stuck trail", () => {
  const stopped = (state: ReindeerState, ability: boolean): ReindeerState => {
    for (let i = 0; i < 300; i++)
      state = tickWorld(state, { ...NEUTRAL_INPUT, ability }, level).state;
    return state;
  };
  const cut = stopped(
    walk(herdAt({ x: 0, z: 245 }, { segmentId: "R2" }), [
      { x: -1, z: 272 },
      { x: -6, z: 297 },
      { x: 3, z: 319 },
      { x: 0, z: 326 },
    ]),
    false,
  );
  expect(reindeerPassageGuidance(cut, level)?.notice).not.toBe(
    "本排已通过 9 / 9",
  );
  const earlyCall = stopped(cut, true);
  expect(earlyCall.actors.filter(({ pos }) => pos.z > 316)).toHaveLength(2);
  const back = walk(earlyCall, [
    { x: 3, z: 318 },
    { x: 3, z: 310 },
  ]);
  const reunited = stopped(back, true);
  const completed = walk(reunited, [
    { x: 3, z: 318 },
    { x: 3, z: 324 },
    { x: 0, z: 337 },
  ]);
  expect(
    completed.actors.every(
      ({ pos, status }) => pos.z > 316 && status === "following",
    ),
  ).toBe(true);
});

test("R1 the far-side stopping point makes space to call the last deer out of the culvert", () => {
  const start = herdAt({ x: -13.5, z: 102 }, { segmentId: "R1" });
  const atShoulder = walk(start, [{ x: -13.5, z: 155 }]);
  let idle = atShoulder;
  let called = atShoulder;
  let walking = atShoulder;
  for (let i = 0; i < 300; i++) {
    idle = tickWorld(idle, NEUTRAL_INPUT, level).state;
    called = tickWorld(
      called,
      { ...NEUTRAL_INPUT, ability: true },
      level,
    ).state;
    walking = tickWorld(
      walking,
      { move: { x: 0, z: 0.12 }, ability: false },
      level,
    ).state;
  }
  expect(reindeerPassageGuidance(idle, level)).toMatchObject({
    notice: "已到远侧 6 / 9",
    tail: { label: "队尾仍在涵洞" },
  });
  expect(reindeerPassageGuidance(called, level)).toMatchObject({
    notice: "已到远侧 9 / 9",
    tail: undefined,
  });
  expect(reindeerPassageGuidance(walking, level)).toMatchObject({
    notice: "已到远侧 9 / 9",
    detail: expect.stringContaining("最后一只"),
    tail: undefined,
  });
});

test("R2 shows both routes before the first row and the usable short runout after passing it", () => {
  const approach = herdAt({ x: 0, z: 228 }, { segmentId: "R2" });
  expect(reindeerPassageGuidance(approach, level)).toMatchObject({
    choices: true,
    notice: "前方可走宽路或短弯",
  });
  const passing = walk(herdAt({ x: -1, z: 259 }, { segmentId: "R2" }), [
    { x: -1, z: 271 },
  ]);
  expect(reindeerPassageGuidance(passing, level)).toMatchObject({
    runout: { x: -1, z: 272 },
    tail: { label: "队尾尚未过栏" },
  });
  const done = walk(passing, [{ x: -1, z: 285 }]);
  expect(reindeerPassageGuidance(done, level)).toMatchObject({
    notice: "本排已通过 9 / 9",
    detail: "最后一只也过栏了，可以转向。",
  });
});

test("R3 guidance connects actual shelter occupancy, fixed dust phases, and the next refuge", () => {
  const middle = herdAt({ x: 17, z: 398 }, { segmentId: "R3", tick: 1440 });
  const guidance = reindeerDustGuidance(middle, level);
  expect(guidance).toMatchObject({
    notice: "尘雾活跃 · 12 秒后平静",
    next: { id: "dust-exit-sign" },
    tail: { actor: { id: middle.actors[8]?.id }, label: "队尾还在尘雾里" },
  });
  expect(guidance?.detail).toContain("背风集队地内 7 / 9");
  expect(guidance?.detail).toContain("矿区出口缓坡");
  expect(reindeerDustGuidance({ ...middle, tick: 0 }, level)?.notice).toContain(
    "尘雾平静",
  );
  expect(
    reindeerDustGuidance(
      herdAt({ x: -18, z: 403 }, { segmentId: "R3" }),
      level,
    ),
  ).toBeUndefined();
});

test("R3 the fork reads the coming phase before route selection and points low-energy herds to supply", () => {
  const fork = herdAt(
    { x: 0, z: 342 },
    { segmentId: "R3", tick: 1380, energy: 0.8 },
  );
  expect(reindeerDustGuidance(fork, level)).toMatchObject({
    fork: true,
    phase: "warning",
    detail: expect.stringContaining("收队，或走恢复带"),
  });
  expect(
    reindeerDustGuidance({ ...fork, energy: 0.2 }, level)?.detail,
  ).toContain("恢复带有补给");
  expect(fork.route).toBeNull();
});

test("R3 gathering before departure physically improves passage into the first refuge", () => {
  const refuge = level.zones.find(({ id }) => id === "dust-shelter");
  const entrance = herdAt(
    { x: 17, z: 353 },
    { segmentId: "R3", route: "dust", tick: 420 },
  );
  expect(reindeerDustGuidance(entrance, level)?.detail).toContain("队尾还远");
  const gathered = (start: ReindeerState): ReindeerState => {
    let state = start;
    for (let i = 0; i < 180; i++)
      state = tickWorld(
        state,
        { ...NEUTRAL_INPUT, ability: true },
        level,
      ).state;
    return state;
  };
  const alreadyGathered = gathered({ ...entrance, tick: 240 });
  expect(reindeerDustGuidance(alreadyGathered, level)?.detail).toContain(
    "队尾预计能赶上",
  );
  const advance = (start: ReindeerState): ReindeerState => {
    let state = start;
    for (let i = 0; i < 1200 && leaderOf(state).pos.z < 406; i++)
      state = tickWorld(
        state,
        { move: { x: 0, z: 0.84 }, ability: false },
        level,
      ).state;
    expect(leaderOf(state).pos.z).toBeGreaterThanOrEqual(406);
    return state;
  };
  const late = { ...entrance, tick: 1080 };
  const spread = advance(late);
  const compactAtSamePhase = advance(gathered({ ...late, tick: 900 }));
  expect(compactAtSamePhase.tick).toBe(spread.tick);
  expect(goalStatus(compactAtSamePhase, refuge).arrived).toBeGreaterThan(
    goalStatus(spread, refuge).arrived,
  );
  const compact = advance(gathered(late));
  expect(goalStatus(compact, refuge).arrived).toBeGreaterThan(
    goalStatus(spread, refuge).arrived,
  );
  expect(goalStatus(compact, refuge).arrived).toBeGreaterThanOrEqual(8);
  expect(spread.actors.every(({ status }) => status !== "strayed")).toBe(true);
  expect(
    goalStatus(walk(spread, [{ x: 17, z: 413 }], 0.12), refuge).canLand,
  ).toBe(true);
});

test("R0 both trails reveal the actual stretched tail after the snowbank", () => {
  for (const id of ["trail-winter-left", "trail-winter-right"]) {
    const trail = level.trails.find((trail) => trail.id === id)!;
    const start = herdAt(level.spawn);
    expect(reindeerWinterTail(start, level)).toBeUndefined();
    const clearing = walk(start, [
      trail.points[1]!,
      trail.points[2]!,
      { x: trail.points[2]!.x, z: 77 },
    ]);
    expect(reindeerWinterTail(clearing, level)).toMatchObject({
      id: "reindeer-8",
      status: "following",
    });
    let resting = clearing;
    for (let i = 0; i < 300; i++)
      resting = tickWorld(
        resting,
        { ...NEUTRAL_INPUT, ability: true },
        level,
      ).state;
    expect(reindeerGatherStatus(resting, level).ready).toBe(true);
    expect(reindeerWinterTail(resting, level)).toBeUndefined();
    const end = walk(herdAt(level.spawn), trail.points.slice(1));
    expect(end.segmentId).toBe("R1");
    expect(end.actors.every(({ status }) => status === "following")).toBe(true);
  }
});

test("R4 the optional overlook provides a safe pause", () => {
  let resting = herdAt({ x: 12, z: 545 }, { segmentId: "R4", energy: 0.05 });
  for (let i = 0; i < 600; i++)
    resting = tickWorld(resting, NEUTRAL_INPUT, level).state;
  expect(resting.phase).toBe("playing");
  expect(resting.energy).toBeGreaterThan(0.05);
  expect(resting.occupied).toContain("thaw-overlook");
});

test("R4 the landing acknowledgment identifies the actual last eligible companion", () => {
  const goal = level.zones.find(({ kind }) => kind === "goal");
  const allIn = herdAt({ x: 0, z: 580 }, { segmentId: "R4" });
  const before: ReindeerState = {
    ...allIn,
    actors: allIn.actors.map((actor, index) =>
      index === 2 ? { ...actor, status: "rejoining" } : actor,
    ),
  };
  expect(goalStatus(before, goal).arrived).toBe(8);
  expect(reindeerLandingCompanion(before, allIn, goal)).toBeUndefined();
  expect(
    reindeerLandingCompanion(before, { ...allIn, phase: "landing" }, goal)?.id,
  ).toBe("reindeer-2");
  expect(
    reindeerLandingCompanion(allIn, { ...allIn, phase: "landing" }, goal),
  ).toBeUndefined();
});

test("earlier reindeer saves carry the complete herd and run identity into P3-5", () => {
  const { checkpoints } = reindeerTrip("greenbelt");
  expect(checkpoints.map(({ id }) => id)).toEqual(["C1", "C2"]);
  for (const current of checkpoints) {
    for (const levelRevision of [
      "reindeer-p3-2",
      "reindeer-p3-3",
      "reindeer-p3-4",
    ]) {
      const previous = {
        ...current,
        state: { ...current.state, levelRevision },
      };
      expect(readCheckpoint(previous, level, "journey")).toEqual(current);
      const record = {
        kind: "checkpoint",
        version: 1,
        runId: "e".repeat(32),
        checkpoint: previous,
        species: "reindeer",
        levelId: level.id,
        levelRevision: previous.state.levelRevision,
        mode: "journey",
      };
      expect(readRunRecord(record, level, "journey")).toEqual({
        ...record,
        levelRevision: level.levelRevision,
        checkpoint: current,
      });
      expect(
        readRunRecord({ ...record, checkpoint: current }, level, "journey"),
      ).toBeUndefined();
    }
  }
});
