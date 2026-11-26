import { expect, test } from "vitest";
import type { GameMode, GooseState } from "../../src/core/game";
import { distance } from "../../src/core/math";
import { GameRuntime } from "../../src/core/runtime";
import { readRunRecord } from "../../src/core/save";
import { gustStrength, sampleWind } from "../../src/levels/wind";
import { GOOSE } from "../../src/simulation/goose";
import {
  goalStatus,
  initialState,
  leaderOf,
  tickWorld,
} from "../../src/simulation/world";
import { writeReplay } from "../fixtures/export-replays";
import {
  aim,
  flyCourse,
  migration,
  trip,
  wideTailwindWaypoints,
} from "../fixtures/flight";

const goal = migration.zones.find(({ kind }) => kind === "goal");
const modes = ["journey"] as const;
const routes = ["mountain", "lake"] as const;
const sanctuaryZ = 770;
const waypoint = (
  x: number,
  z: number,
  power = 0.83,
  radius = 5,
  ability = false,
) => ({ x, z, power, radius, ability });

const matrix = modes.flatMap((mode) =>
  routes.flatMap((route) =>
    [false, true].flatMap((bay) =>
      [false, true].map((gallery) => ({ mode, route, bay, gallery })),
    ),
  ),
);

test.each(matrix)(
  "full flight $mode $route bay=$bay gallery=$gallery",
  async ({ mode, route, bay, gallery }) => {
    const x = route === "mountain" ? -36 : 59;
    let beforeSafeWater = 0;
    const flight = flyCourse(
      migration,
      mode,
      [
        ...wideTailwindWaypoints(),
        waypoint(x, 272, 0.83, 7),
        waypoint(x, 362, 0.83, 7),
        waypoint(0, 455, 0.83, 7),
        ...(bay
          ? [
              waypoint(-87, 565, 0.65),
              waypoint(-89, 614, 0.65),
              waypoint(-57, 655),
            ]
          : [waypoint(-55, 532), waypoint(-55, 653)]),
        ...(gallery
          ? [
              waypoint(-83, 704),
              waypoint(-83, 746, 0.5, 2.5),
              waypoint(-30, 746, 0.5, 2.5),
              waypoint(-30, 783, 0.55),
            ]
          : [waypoint(0, 710), waypoint(0, 780)]),
        waypoint(0, 853),
      ],
      (state) => {
        if (leaderOf(state).pos.z < sanctuaryZ) beforeSafeWater = state.energy;
        return false;
      },
    );
    const { runtime, input, events } = flight;
    expect(runtime.checkpoint.id).toBe("A");
    expect(runtime.current).toMatchObject({
      phase: "landing",
      route,
      routeLocked: true,
    });
    expect(goalStatus(runtime.current, goal).arrived).toBe(12);
    expect(input.every(({ ability }) => !ability)).toBe(true);
    expect(
      events.flatMap(({ event }) =>
        event.type === "strayed" ? [event.id] : [],
      ),
    ).toEqual(["goose-11"]);
    expect(
      events.some(
        ({ event }) =>
          event.type === "zone" &&
          event.entered &&
          [
            "sweep",
            "ridge-wall",
            "gallery-panel-upstream",
            "gallery-panel-downstream",
          ].includes(event.id),
      ),
    ).toBe(false);
    const start = initialState(migration, mode);
    expect(runtime.current.supply["return-supply"]).toBe(
      start.supply["return-supply"],
    );
    expect(
      (runtime.current.supply["gallery-supply"] ?? 1) <
        (start.supply["gallery-supply"] ?? 0),
    ).toBe(gallery);
    expect(
      (runtime.current.supply["reserve-supply"] ?? 1) <
        (start.supply["reserve-supply"] ?? 0),
    ).toBe(bay);
    if (mode === "journey" && !bay && !gallery)
      expect(beforeSafeWater).toBeGreaterThanOrEqual(0.1);
    await writeReplay(
      `ux-${mode}-${route}-${bay ? "bay" : "outer"}-${gallery ? "gallery" : "river"}`,
      {
        levelRevision: migration.levelRevision,
        mode,
        start: null,
        inputs: input,
        events,
        expected: runtime.current,
      },
    );
  },
);

const edges = modes.flatMap((mode) =>
  ([-1, 1] as const).map((side) => ({ mode, side })),
);

test.each(edges)(
  "$mode on exact map edge $side records A, route and rescue",
  ({ mode, side }) => {
    const runtime = new GameRuntime(migration, mode);
    const bound = side < 0 ? migration.bounds.min.x : migration.bounds.max.x;
    const exit = [
      waypoint(side * 48, 680, 0.58),
      waypoint(0, 728, 0.69),
      waypoint(0, 853, 0.73),
    ] as const;
    let stage: "reach" | "edge" | "exit" = "reach";
    let target = 0;
    const eventsAtBoundary = new Map<string, number>();
    while (
      runtime.current.phase === "playing" &&
      runtime.current.tick < 15_000
    ) {
      const { pos } = leaderOf(runtime.current);
      if (stage === "reach" && pos.x === bound) stage = "edge";
      if (stage === "edge" && pos.z > 652) stage = "exit";
      const waypoint = exit[target] ?? exit[2];
      if (stage === "exit" && distance(pos, waypoint) < 5) target++;
      const dest = exit[target] ?? exit[2];
      const stray = runtime.current.actors.find(
        ({ status }) => status === "strayed",
      );
      const input =
        mode === "journey" && stray
          ? aim(pos, stray.pos, distance(pos, stray.pos) < 12 ? 0.09 : 0.45)
          : stage === "reach"
            ? aim(pos, { x: side * 180, z: 17 }, 0.57)
            : stage === "edge"
              ? { move: { x: side * 0.00001, z: 0.55 }, ability: false }
              : aim(pos, dest, dest.power);
      runtime.dispatch({ type: "input", input });
      for (const event of runtime.step())
        if (
          event.type === "checkpoint" ||
          event.type === "route" ||
          event.type === "strayed"
        )
          eventsAtBoundary.set(event.type, leaderOf(runtime.current).pos.x);
    }
    expect(eventsAtBoundary).toEqual(
      new Map(["checkpoint", "route", "strayed"].map((type) => [type, bound])),
    );
    expect(runtime.current).toMatchObject({
      phase: "landing",
      route: side < 0 ? "mountain" : "lake",
      routeLocked: true,
    });
    expect(goalStatus(runtime.current, goal).arrived).toBe(12);
  },
);

test("route can change after a genuine second crossing and locks at the confluence", () => {
  const run = flyCourse(
    migration,
    "journey",
    [
      ...wideTailwindWaypoints(0.65, 4),
      waypoint(-36, 272, 0.65, 4),
      waypoint(-36, 363, 0.65, 4),
      waypoint(-36, 389, 0.65, 4),
      waypoint(58, 385, 0.65, 4),
      waypoint(58, 330, 0.65, 4),
      waypoint(71, 366, 0.65, 4),
      waypoint(50, 410, 0.65, 4),
    ],
    (state) => state.routeLocked,
  );
  expect(
    run.events.flatMap(({ event }) =>
      event.type === "route" ? [event.route] : [],
    ),
  ).toEqual(["mountain", "lake"]);
  expect(run.runtime.current).toMatchObject({
    route: "lake",
    routeLocked: true,
  });
  const { runtime, events } = flyCourse(
    migration,
    "journey",
    [
      waypoint(71, 389, 0.55, 4),
      waypoint(71, 330, 0.55, 4),
      waypoint(65, 285, 0.55, 4),
    ],
    (state) => leaderOf(state).pos.z < 310,
    { ...run.runtime.checkpoint, state: run.runtime.current },
  );
  expect(events.some(({ event }) => event.type === "route")).toBe(false);
  expect(runtime.current).toMatchObject({ route: "lake", routeLocked: true });
});

test("a glance into the mountain entrance does not record that route", () => {
  const run = flyCourse(
    migration,
    "journey",
    [
      ...wideTailwindWaypoints(),
      waypoint(-20, 245, 0.59, 2),
      waypoint(48, 250, 0.59, 3),
      waypoint(59, 272),
      waypoint(59, 362),
      waypoint(0, 455),
    ],
    (state) => state.routeLocked,
  );
  expect(
    run.events.flatMap(({ event }) =>
      event.type === "route" ? [event.route] : [],
    ),
  ).toEqual(["lake"]);
});

test("the lake shallows pay back the detour by the actual confluence", () => {
  const start = trip("journey", "lake", 272).runtime;
  const restored = { ...start.checkpoint, state: start.current };
  const direct = flyCourse(
    migration,
    "journey",
    [waypoint(59, 362), waypoint(0, 455)],
    (state) => state.routeLocked,
    restored,
  );
  const lakeBay = flyCourse(
    migration,
    "journey",
    [
      waypoint(88, 327, 0.65),
      waypoint(88, 359, 0.65),
      waypoint(59, 390),
      waypoint(0, 455),
    ],
    (state) => state.routeLocked,
    restored,
  );
  expect(lakeBay.runtime.current.route).toBe("lake");
  expect(lakeBay.runtime.current.routeLocked).toBe(true);
  expect(
    lakeBay.runtime.current.energy - direct.runtime.current.energy,
  ).toBeGreaterThanOrEqual(0.1);
});

test.each(routes)(
  "S5 %s inlet is reachable on 22%% energy and formation saves energy on the main river",
  (route) => {
    const { checkpoint, current } = trip("journey", route, 666).runtime;
    const restored = { ...checkpoint, state: { ...current, energy: 0.22 } };
    const replenish = flyCourse(
      migration,
      "journey",
      [
        waypoint(24, 698, 0.72),
        waypoint(24, 722, 0.72),
        waypoint(0, 853, 0.72),
      ],
      sanctuaryZ,
      restored,
    );
    expect(replenish.runtime.current.energy).toBeGreaterThan(0.3);
    expect(replenish.runtime.current.supply["return-supply"]).toBeLessThan(
      0.34,
    );

    function direct(ability: boolean) {
      return flyCourse(
        migration,
        "journey",
        [
          waypoint(0, 713, 0.83, 5, ability),
          waypoint(0, 810, 0.83, 5, ability),
        ],
        sanctuaryZ,
        { ...checkpoint, state: current },
      ).runtime.current.energy;
    }
    expect(direct(true) - direct(false)).toBeGreaterThanOrEqual(0.04);
  },
);

test("S5 wind shares a smooth ground-drift field with the sheltered gallery", () => {
  expect(sampleWind(migration, { x: 0, z: 665 }).drift.z).toBe(0);
  expect(sampleWind(migration, { x: 0, z: 670 }).drift.z).toBeCloseTo(-0.8);
  expect(sampleWind(migration, { x: 0, z: 700 }).drift.z).toBeCloseTo(-1.6);
  expect(sampleWind(migration, { x: -82, z: 700 }).drift.z).toBeGreaterThan(0);
  expect(sampleWind(migration, { x: 0, z: 778 }).drift.z).toBe(0);
});

const gustZone = migration.zones.find(({ id }) => id === "return-gust");

test("S5 gust eases at a fixed phase, fades to zero at its edge, and leaves the lee wind stable", () => {
  if (gustZone?.kind !== "interference" || !gustZone.gust)
    throw new Error("Missing S5 gust");
  const gust = gustZone.gust;
  const weakTick = gust.periodTicks - gust.phaseTicks;
  const strongTick = weakTick + gust.periodTicks / 2;
  const center = { x: 0, z: 704 };
  const edge = { x: 0, z: 692 };
  const lee = { x: 21, z: 735 };

  expect(gustStrength(gust, weakTick)).toBe(0);
  expect(gustStrength(gust, strongTick)).toBe(1);
  expect(gustStrength(gust, weakTick + gust.periodTicks)).toBe(0);
  expect(sampleWind(migration, center, weakTick).drift.x).toBe(0);
  expect(sampleWind(migration, center, strongTick).drift.x).toBeLessThan(-1);
  expect(sampleWind(migration, edge, strongTick)).toEqual(
    sampleWind(migration, edge, weakTick),
  );
  expect(sampleWind(migration, lee, strongTick)).toEqual(
    sampleWind(migration, lee, weakTick),
  );
  expect(sampleWind(migration, lee, weakTick).drift.z).toBeGreaterThan(0);
});

test("S5 timing an optional lee cut gains ground while both direct flights still reach 12/12", () => {
  if (gustZone?.kind !== "interference" || !gustZone.gust)
    throw new Error("Missing S5 gust");
  const gust = gustZone.gust;
  const { checkpoint, current } = trip("journey", "mountain", 704).runtime;
  if (current.species !== "goose") throw new Error("Missing goose snapshot");
  const weakTick =
    current.tick - ((current.tick + gust.phaseTicks) % gust.periodTicks);
  const leeEntry = migration.landmarks.find(
    ({ id }) => id === "return-lee-entry",
  );
  const leeExit = migration.landmarks.find(
    ({ id }) => id === "return-lee-exit",
  );
  if (!leeEntry || !leeExit) throw new Error("Missing lee landmarks");

  const cross = (tick: number, cut: boolean, formation: boolean) => {
    const snapshot = {
      ...checkpoint,
      state: { ...current, tick, energy: 0.6 },
    };
    const points = cut
      ? ([
          waypoint(leeEntry.pos.x, leeEntry.pos.z, 0.83, 3, false),
          waypoint(leeExit.pos.x, leeExit.pos.z, 0.83, 3, true),
          waypoint(leeExit.pos.x, 806, 0.83, 5, true),
          waypoint(0, 853, 0.83, 5, true),
        ] as const)
      : ([waypoint(0, 850, 0.83, 5, formation)] as const);
    let exit: { tick: number; energy: number } | undefined;
    const { runtime, events } = flyCourse(
      migration,
      "journey",
      points,
      (state) => {
        if (leaderOf(state).pos.z >= 768) exit ??= state;
        return false;
      },
      snapshot,
    );

    if (!exit) throw new Error("Flight did not cross the inlet");
    expect(runtime.current.phase).toBe("landing");
    expect(goalStatus(runtime.current, goal).arrived).toBe(12);
    expect(runtime.current.supply["return-supply"]).toBe(
      snapshot.state.supply["return-supply"],
    );
    expect(events.some(({ event }) => event.type === "strayed")).toBe(false);
    expect(
      events.some(
        ({ event }) =>
          event.type === "zone" &&
          event.entered &&
          ["gallery-panel-upstream", "gallery-panel-downstream"].includes(
            event.id,
          ),
      ),
    ).toBe(false);
    expect(
      events.some(
        ({ event }) =>
          event.type === "zone" && event.entered && event.id === "return-lee",
      ),
    ).toBe(cut);
    return { ticks: exit.tick - tick, energy: exit.energy };
  };

  const cruise = cross(weakTick, false, false);
  const directV = cross(weakTick, false, true);
  const easing = cross(weakTick, true, true);
  const atPeak = cross(weakTick + gust.periodTicks / 2, true, true);

  expect(directV.energy).toBeGreaterThan(cruise.energy + 0.035);
  expect(easing.ticks).toBeLessThan(directV.ticks - 50);
  expect(easing.energy).toBeGreaterThan(directV.energy + 0.015);
  expect(easing.ticks).toBeLessThan(atPeak.ticks - 10);
});

test("S1 early release saves the crossing window and preparation shortens S3 recovery distance", () => {
  const state = initialState(migration, "journey");
  const ready: GooseState = {
    ...state,
    airborne: true,
    formation: 1,
    actors: state.actors.map((actor) => ({
      ...actor,
      pos: { x: actor.pos.x - 19, z: actor.pos.z + 146 },
      speed: 9.39,
    })),
  };
  function crossed(hold: boolean): boolean {
    let current = ready;
    for (let i = 0; i < 232; i++) {
      const angle = i < 45 ? 0 : (62 * Math.PI) / 180;
      current = tickWorld(
        current,
        {
          move: { x: Math.sin(angle) * 0.83, z: Math.cos(angle) * 0.83 },
          ability: hold,
        },
        migration,
      ).state;
      if (current.occupied.includes("tailwind-second")) return true;
    }
    return false;
  }
  expect(crossed(false)).toBe(true);
  expect(crossed(true)).toBe(false);

  const valley = trip("journey", "mountain", 410).runtime;
  const gapAtStray = (power: number, ability: boolean) => {
    const { runtime } = flyCourse(
      migration,
      "journey",
      [waypoint(0, 455, power, 5, ability)],
      (state) => state.actors[11]?.status === "strayed",
      { ...valley.checkpoint, state: valley.current },
    );
    const tail = runtime.current.actors[11];
    if (!tail || tail.status !== "strayed")
      throw new Error("Missing dropped companion");
    expect(tail.rescueTicks).toBe(GOOSE.rescueTicks);
    return distance(tail.pos, leaderOf(runtime.current).pos);
  };
  expect(gapAtStray(0.4, true)).toBeLessThan(gapAtStray(0.83, false) - 2);
});

test("legacy A migration retains actual supply spent, and historical results remain readable", () => {
  const mode: GameMode = "journey";
  const revision = "goose-p0-5";
  const runId = "c".repeat(32);
  const { checkpoint } = trip(mode, "mountain", 240).runtime;
  if (checkpoint.state.species !== "goose")
    throw new Error("Missing goose checkpoint A");
  const { species, ...checkpointState } = checkpoint.state;
  const state = {
    ...checkpointState,
    levelRevision: revision,
    route: "mountain",
    triggered: [...checkpoint.state.triggered, "pass-entry"],
    supply: { ...checkpoint.state.supply, "return-supply": 0.42 },
  };
  const legacy = {
    version: 1,
    runId,
    levelRevision: revision,
    kind: "checkpoint",
    checkpoint: { ...checkpoint, state },
  };
  const record = readRunRecord(legacy, migration, mode);
  expect(record?.kind).toBe("checkpoint");
  if (record?.kind !== "checkpoint")
    throw new Error("A point was not restored");
  expect(record.checkpoint.state.supply["return-supply"]).toBeCloseTo(0.14);
  expect(record.checkpoint.state).toEqual(
    expect.objectContaining({
      species,
      actors: state.actors,
      tick: state.tick,
      formation: state.formation,
      energy: state.energy,
      route: null,
      triggered: checkpoint.state.triggered,
    }),
  );
  const finished = {
    version: 1,
    runId,
    levelRevision: revision,
    kind: "arrived",
    tick: 6150,
    route: "lake",
  };
  expect(readRunRecord(finished, migration, mode)).toEqual({
    ...finished,
    levelRevision: migration.levelRevision,
  });
});

test("p0-6 checkpoints keep their wind clock and already migrated supply", () => {
  const { checkpoint } = trip("journey", "mountain", 240).runtime;
  const revision = "goose-p0-6";
  const state = {
    ...checkpoint.state,
    levelRevision: revision,
    supply: { ...checkpoint.state.supply, "return-supply": 0.21 },
  };
  const record = {
    version: 1,
    kind: "checkpoint",
    runId: "a".repeat(32),
    levelRevision: revision,
    checkpoint: { ...checkpoint, state },
  };
  const upgraded = { ...state, levelRevision: migration.levelRevision };
  expect(readRunRecord(record, migration, "journey")).toEqual({
    ...record,
    levelRevision: migration.levelRevision,
    checkpoint: { ...checkpoint, state: upgraded },
  });
});
