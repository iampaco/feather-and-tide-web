import { expect, test } from "vitest";
import { Mesh } from "three";
import { GameRuntime } from "../../src/core/runtime";
import { readRunRecord } from "../../src/core/save";
import { distance, type Vec2 } from "../../src/core/math";
import type { GameMode, GameState } from "../../src/core/game";
import { sweptCircle } from "../../src/levels/geometry";
import { buildMigrationOverlays } from "../../src/rendering/migrationOverlays";
import { GOOSE } from "../../src/simulation/goose";
import {
  goalStatus,
  initialState,
  leaderOf,
  tickWorld,
} from "../../src/simulation/world";
import { aim, flyCourse, migration, trip } from "../fixtures/flight";

const walls = migration.zones.filter(
  (zone) => zone.kind === "hazard" && zone.appearance === "glass",
);
const goal = migration.zones.find(({ kind }) => kind === "goal");

function positionFlight(pos: Vec2, mode: GameMode, heading = 0): GameState {
  const state = initialState(migration, mode);
  return {
    ...state,
    airborne: true,
    energy: 0.8,
    actors: state.actors.map((actor) => ({
      ...actor,
      pos: {
        x: pos.x + actor.pos.x * Math.cos(heading),
        z: pos.z + actor.pos.z * Math.cos(heading),
      },
      heading,
      speed: GOOSE.cruise,
    })),
  };
}

test("offset tailwinds reward entering the second lane and mountain gusts push in opposite directions", () => {
  const forward = { move: { x: 0, z: 0.89 }, ability: false };
  function fly(pos: Vec2) {
    let state = positionFlight(pos, "journey");
    for (let step = 0; step < 120; step++)
      state = tickWorld(state, forward, migration).state;
    return state;
  }
  const first = fly({ x: -18, z: 116 });
  const second = fly({ x: 21, z: 170 });
  const missed = fly({ x: -18, z: 157 });
  expect(first.occupied).toContain("tailwind-first");
  expect(second.occupied).toContain("tailwind-second");
  expect(missed.occupied).not.toContain("tailwind-second");
  expect(second.energy).toBeGreaterThan(missed.energy);
  expect(leaderOf(second).pos.z - 170).toBeGreaterThan(
    leaderOf(missed).pos.z - 157,
  );
  expect(leaderOf(fly({ x: -46, z: 258 })).pos.x).toBeGreaterThan(-43);
  expect(leaderOf(fly({ x: -46, z: 323 })).pos.x).toBeLessThan(-49);
});

test("the lake main route can skip the shallows and a deliberate approach can replenish", () => {
  const bypass = trip("journey", "lake", 397).runtime.current;
  expect(bypass.supply["lake-supply"]).toBe(0.38);
  const start = trip("journey", "lake", 269).runtime;
  const flight = new GameRuntime(migration, "journey", {
    ...start.checkpoint,
    state: { ...start.current, energy: 0.62 },
  });
  for (let i = 0; i < 600; i++) {
    const pos = leaderOf(flight.current).pos;
    flight.dispatch({
      type: "input",
      input: aim(pos, { x: 88, z: 348 }, 0.73),
    });
    flight.step();
  }
  expect(flight.current.supply["lake-supply"]).toBeLessThan(0.25);
  expect(flight.current.energy).toBeGreaterThan(0.62);
  expect(
    flight.current.actors.every(({ status }) => status === "following"),
  ).toBe(true);
});

test.each(["journey"] as const)(
  "both S4 choices land all 12 after either S2 route in %s",
  (mode) => {
    for (const route of ["mountain", "lake"] as const) {
      const start = trip(mode, route, 512).runtime;
      for (const replenish of [false, true]) {
        const flight = new GameRuntime(migration, mode, {
          ...start.checkpoint,
          state: {
            ...start.current,
            energy: replenish ? 0.22 : start.current.energy,
          },
        });
        const points: [Vec2, ...Vec2[]] = replenish
          ? [
              { x: -87, z: 565 },
              { x: -89, z: 614 },
              { x: -57, z: 655 },
            ]
          : [
              { x: -55, z: 532 },
              { x: -55, z: 653 },
            ];
        points.push({ x: 0, z: 716 }, { x: 0, z: 853 });
        let index = 0;
        let exitEnergy: number | undefined;
        let hitSweep = false;
        let stranded = false;
        for (let i = 0; i < 5500 && flight.current.phase === "playing"; i++) {
          const state = flight.current;
          const pos = leaderOf(state).pos;
          if (
            distance(pos, points[index] ?? points[0]) < 6 &&
            index < points.length - 1
          )
            index++;
          if (pos.z >= 650) exitEnergy ??= state.energy;
          flight.dispatch({
            type: "input",
            input: aim(
              pos,
              points[index] ?? points[0],
              replenish && index < 2 ? 0.65 : 0.83,
              state.segmentId === "S5",
            ),
          });
          for (const event of flight.step()) {
            hitSweep ||= event.type === "zone" && event.id === "sweep";
            stranded ||= event.type === "strayed";
          }
        }
        expect(hitSweep, `${route} replenish=${replenish}`).toBe(false);
        expect(stranded).toBe(false);
        expect(flight.current.phase).toBe("landing");
        expect(goalStatus(flight.current, goal).arrived).toBe(12);
        const capacity = start.current.supply["reserve-supply"] ?? 0;
        if (replenish) {
          expect(flight.current.supply["reserve-supply"]).toBeLessThan(
            capacity,
          );
          expect(exitEnergy).toBeGreaterThan(GOOSE.lowEnergy);
        } else {
          expect(flight.current.supply["reserve-supply"]).toBe(capacity);
          expect(exitEnergy).toBeLessThan(start.current.energy);
        }
      }
    }
  },
);

test.each(["journey"] as const)(
  "both gallery routes finish with all 12 in %s after either fork",
  (mode) => {
    for (const route of ["mountain", "lake"] as const) {
      const start = trip(mode, route, 658).runtime;
      for (const inside of [true, false]) {
        const restored = {
          ...start.checkpoint,
          state: {
            ...start.current,
            energy: 0.28,
            supply: { ...start.current.supply, "return-supply": 0 },
          },
        };
        const points = inside
          ? ([
              { x: -83, z: 704, radius: 5 },
              { x: -83, z: 746, radius: 2.5, power: 0.5 },
              { x: -30, z: 746, radius: 2.5, power: 0.5, ability: false },
              { x: -30, z: 783, radius: 5, power: 0.55, ability: false },
              { x: 0, z: 853 },
            ] as const)
          : ([
              { x: 0, z: 710, radius: 5 },
              { x: 0, z: 780, radius: 5 },
              { x: 0, z: 853 },
            ] as const);
        const { runtime: flight, events } = flyCourse(
          migration,
          mode,
          points,
          Infinity,
          restored,
        );
        const touchedWall = events.some(
          ({ event }) =>
            event.type === "zone" &&
            event.entered &&
            walls.some(({ id }) => id === event.id),
        );
        const stranded = events.some(({ event }) => event.type === "strayed");
        expect(touchedWall, `${route} inside=${inside}`).toBe(false);
        expect(stranded).toBe(false);
        expect(flight.current.phase).toBe("landing");
        expect(goalStatus(flight.current, goal).arrived).toBe(12);
        expect((flight.current.supply["gallery-supply"] ?? 0) < 0.19).toBe(
          inside,
        );
      }
    }
  },
);

test("glass panels match their collision edges and warn from either approach", () => {
  expect(walls).toHaveLength(2);
  const { group } = buildMigrationOverlays(migration, () => 0.5);
  for (const wall of walls) {
    const panes = group
      .getObjectByName(wall.id)
      ?.getObjectByName("marked-glass-panes");
    if (!(panes instanceof Mesh))
      throw new Error(`Missing glass geometry for ${wall.id}`);
    const vertices = panes.geometry.getAttribute("position");
    for (let i = 0; i < vertices.count; i++) {
      const p = { x: vertices.getX(i), z: vertices.getZ(i) };
      expect(wall.points).toContainEqual(p);
    }
  }
  for (const { x, z, direction } of [
    { x: -40, z: 665, direction: 1 },
    { x: -77, z: 807, direction: -1 },
  ]) {
    const start = { x, z };
    const heading = direction > 0 ? 0 : Math.PI;
    let journey = positionFlight(start, "journey", heading);
    const noCost = {
      ...migration,
      zones: migration.zones.map((zone) =>
        zone.kind === "hazard" ? { ...zone, cost: 0 } : zone,
      ),
    };
    let control = journey;
    const command = { move: { x: 0, z: direction * 0.89 }, ability: false };
    let observedWarning = 0;
    let contact = 0;
    for (let step = 0; step < 420 && !contact; step++) {
      journey = tickWorld(journey, command, migration).state;
      control = tickWorld(control, command, noCost).state;
      if (journey.occupied.includes("gallery-warning"))
        observedWarning ||= journey.tick;
      if (walls.some(({ id }) => journey.occupied.includes(id)))
        contact = journey.tick;
    }
    expect(observedWarning).toBeGreaterThan(0);
    expect(contact - observedWarning).toBeGreaterThanOrEqual(180);
    const pos = leaderOf(journey).pos;
    expect(leaderOf(control).pos).toEqual(pos);
    expect(walls.some((wall) => sweptCircle(wall.points, pos, pos, 0))).toBe(
      false,
    );
    expect(journey.phase).toBe("playing");
    expect(control.energy - journey.energy).toBeCloseTo(0.09, 3);
  }
});

test.each(["goose-p0-3", "goose-p0-4", "goose-p0-5"])(
  "the %s checkpoint retains its flock and gallery supply",
  (previousRevision) => {
    const { checkpoint } = trip("journey", "mountain", 245).runtime;
    const previousSupply: Record<string, number> = {
      ...checkpoint.state.supply,
      "return-supply": 0.62,
    };
    if (previousRevision === "goose-p0-3")
      delete previousSupply["gallery-supply"];
    const legacy = {
      version: 1,
      kind: "checkpoint",
      levelRevision: previousRevision,
      runId: "a".repeat(32),
      checkpoint: {
        ...checkpoint,
        state: {
          ...checkpoint.state,
          levelRevision: previousRevision,
          supply: previousSupply,
        },
      },
    };
    expect(readRunRecord(legacy, migration, "journey")).toEqual({
      ...legacy,
      levelRevision: migration.levelRevision,
      checkpoint,
    });
    expect(
      readRunRecord(
        { ...legacy, levelRevision: "goose-p0-2" },
        migration,
        "journey",
      ),
    ).toBeUndefined();
  },
);
