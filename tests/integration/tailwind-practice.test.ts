import { expect, test } from "vitest";
import {
  gooseHazardCue,
  gooseTailwindCue,
} from "../../src/app/flight-guidance";
import { GameRuntime } from "../../src/core/runtime";
import { readRunRecord } from "../../src/core/save";
import {
  tailwindCourseZones,
  tailwindPractice,
} from "../../src/levels/tailwind-practice";
import { goalStatus, initialState, leaderOf } from "../../src/simulation/world";
import { aim, migration, trip } from "../fixtures/flight";

const course = tailwindPractice(migration);
const goal = course.zones.find(({ kind }) => kind === "goal");

test("a trailing bird touching the bank leaves the lead goose's wind cue visible", () => {
  const start = initialState(course, "journey");
  const threaded = {
    ...start,
    airborne: true,
    occupied: ["tailwind-reed-bank", "tailwind-second"],
    actors: start.actors.map((actor, i) => ({
      ...actor,
      pos: { x: i === 0 ? 18 : 5, z: 184 - i },
    })),
  };
  expect(gooseHazardCue(threaded, course)).toBeUndefined();
  expect(gooseTailwindCue(threaded, course)?.detail).toContain("收速");
});

function fly(
  releaseZ: number,
  turnZ: number,
  route: "wide" | "cut" | "boost" | "straight" = "cut",
) {
  const runtime = new GameRuntime(course, "journey");
  let straightened = false;
  let wideReady = false;
  let maxTailGap = 0;
  let sawWide = false;
  let secondWindTicks = 0;
  let leaderArrivedFirst = false;
  while (runtime.current.phase === "playing" && runtime.current.tick < 1800) {
    const { pos } = leaderOf(runtime.current);
    straightened ||= pos.x >= 14 && pos.z >= turnZ;
    const turn = pos.z >= turnZ && !straightened;
    const diagonal = 0.84 / Math.SQRT2;
    wideReady ||= pos.x <= -24;
    const bank = route === "wide" && pos.z > 133 && !wideReady;
    const boost =
      route === "boost" && straightened && pos.z >= 174 && pos.z < 199;
    const input = bank
      ? aim(pos, { x: -28, z: 168 })
      : {
          move: turn
            ? { x: diagonal, z: diagonal }
            : { x: 0, z: boost ? 1 : 0.84 },
          ability: pos.z < releaseZ || straightened,
        };
    runtime.dispatch({
      type: "input",
      input,
    });
    runtime.step();
    const state = runtime.current;
    const cue = gooseTailwindCue(state, course);
    maxTailGap = Math.max(
      maxTailGap,
      ...state.actors.map((actor) =>
        Math.hypot(actor.pos.x - pos.x, actor.pos.z - pos.z),
      ),
    );
    sawWide ||= cue?.title === "宽水面 · 逆风减慢推进";
    if (cue?.title === "借到第二道顺风") secondWindTicks++;
    const arrival = goalStatus(state, goal);
    leaderArrivedFirst ||=
      arrival.leaderArrived &&
      arrival.arrived < arrival.expected &&
      state.phase === "playing";
  }
  return { runtime, sawWide, secondWindTicks, leaderArrivedFirst, maxTailGap };
}

test("the wind practice shares live S1 wind and both lines land only at 12/12", () => {
  expect(course.zones.slice(0, -1)).toEqual(
    migration.zones.filter(({ id }) => tailwindCourseZones.includes(id)),
  );
  const wide = fly(Infinity, Infinity, "wide");
  const cut = fly(135, 146);
  const boost = fly(135, 146, "boost");
  for (const { runtime, leaderArrivedFirst } of [wide, cut, boost]) {
    expect(leaderArrivedFirst).toBe(true);
    expect(runtime.current.phase).toBe("landing");
    expect(goalStatus(runtime.current, goal).arrived).toBe(12);
  }
  expect(wide.sawWide).toBe(true);
  expect(wide.secondWindTicks).toBe(0);
  expect(cut.secondWindTicks).toBeGreaterThan(120);
  expect(cut.runtime.current.tick).toBeLessThan(wide.runtime.current.tick - 30);
  expect(boost.runtime.current.tick).toBeLessThanOrEqual(
    wide.runtime.current.tick - 90,
  );
  expect(boost.maxTailGap).toBeGreaterThan(cut.maxTailGap);
  expect(cut.runtime.current.energy).toBeGreaterThan(
    wide.runtime.current.energy + 0.01,
  );
});

test("holding straight reaches the bank and a late steering correction clears it", () => {
  const { runtime } = fly(Infinity, Infinity, "straight");
  const bank = course.zones.find(({ id }) => id === "tailwind-reed-bank");
  if (!bank) throw new Error("Missing reed bank");
  expect(runtime.current.phase).toBe("playing");
  expect(leaderOf(runtime.current).pos.z).toBeLessThan(
    Math.min(...bank.points.map(({ z }) => z)),
  );
  while (runtime.current.phase === "playing" && runtime.current.tick < 3600) {
    const pos = leaderOf(runtime.current).pos;
    const input =
      pos.x > -25
        ? aim(pos, { x: -30, z: pos.z }, 0.6)
        : { move: { x: 0, z: 0.84 }, ability: false };
    runtime.dispatch({ type: "input", input });
    runtime.step();
  }
  expect(runtime.current.phase).toBe("landing");
  expect(goalStatus(runtime.current, goal).arrived).toBe(12);
});

test("correcting a late turn still works, with less time in beneficial wind", () => {
  const early = fly(135, 146);
  const late = fly(155, 166);
  expect(late.sawWide).toBe(true);
  expect(late.secondWindTicks).toBeGreaterThan(0);
  expect(late.secondWindTicks).toBeLessThan(early.secondWindTicks - 25);
  expect(late.runtime.current.phase).toBe("landing");
  expect(late.runtime.current.tick).toBeGreaterThan(
    early.runtime.current.tick + 45,
  );
  expect(late.runtime.current.energy).toBeLessThan(
    early.runtime.current.energy - 0.02,
  );
});

test("pausing and restarting the practice clears the whole run and held input", () => {
  const runtime = new GameRuntime(course, "journey");
  const initial = runtime.current;
  runtime.dispatch({
    type: "input",
    input: { move: { x: 0, z: 0.84 }, ability: true },
  });
  for (let i = 0; i < 400; i++) runtime.step();
  expect(runtime.current.formation).toBe(1);
  expect(runtime.current.energy).toBeLessThan(initial.energy);
  runtime.dispatch({ type: "pause" });
  runtime.dispatch({ type: "retry" });
  expect(runtime.current).toEqual(initial);
  runtime.step();
  expect(runtime.current).toMatchObject({
    airborne: false,
    formation: 0,
    tick: 1,
  });
});

test.each(["goose-p0-7", "goose-p0-9"])(
  "the S1 wind revision preserves the %s journey checkpoint",
  (levelRevision) => {
    const { checkpoint } = trip("journey", "mountain", 240).runtime;
    expect(checkpoint.id).toBe("A");
    const record = {
      version: 1,
      runId: "a".repeat(32),
      kind: "checkpoint",
      levelRevision,
      checkpoint: {
        ...checkpoint,
        state: { ...checkpoint.state, levelRevision },
      },
    };
    expect(readRunRecord(record, migration, "journey")).toEqual({
      ...record,
      levelRevision: migration.levelRevision,
      checkpoint,
    });
  },
);
