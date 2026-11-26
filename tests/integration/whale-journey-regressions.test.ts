import { expect, test } from "vitest";
import {
  whaleGuidance,
  type WhaleTutorialView,
} from "../../src/app/whale-guidance";
import {
  NEUTRAL_INPUT,
  type WhaleState,
  type WorldInput,
} from "../../src/core/game";
import { distance, type Vec2 } from "../../src/core/math";
import { GameRuntime } from "../../src/core/runtime";
import { readCheckpoint } from "../../src/core/save";
import { currentGuide } from "../../src/levels/whale-current";
import { goalStatus } from "../../src/simulation/world-rules";
import { WHALE } from "../../src/simulation/whale-motion";
import { aim } from "../fixtures/flight";
import { podAt, podLeader, whaleLevel } from "../fixtures/whale";

const view: WhaleTutorialView = {
  dragged: false,
  reset: false,
  moved: true,
  stopped: false,
  submerged: false,
  recovered: false,
  toggle: false,
  desktop: false,
};

function staged(position: Vec2, patch: Partial<WhaleState> = {}): WhaleState {
  const start = podAt(position, "journey", 11010);
  const segmentId = whaleLevel.segments.findLast(
    ({ start }) => start <= position.z,
  )?.id;
  if (!segmentId) throw new Error("Missing whale segment");
  return { ...start, segmentId, ...patch };
}

function runtimeFrom(state: WhaleState) {
  return new GameRuntime(whaleLevel, "journey", {
    id: "start",
    version: 1,
    state,
  });
}

function step(
  runtime: GameRuntime<typeof whaleLevel>,
  input: WorldInput = NEUTRAL_INPUT,
) {
  runtime.dispatch({ type: "input", input });
  return runtime.step();
}

test("W1 keeps the bend-in marker until a central approach has steered beside the seawall", () => {
  const late = staged({ x: 0, z: 300 });
  expect(whaleGuidance(late, whaleLevel, false, view).markers[0]?.id).toBe(
    "ship-bend-in",
  );
  const state = staged({ x: 0, z: 270 });
  const runtime = runtimeFrom({
    ...state,
    actors: state.actors.map((actor) => ({ ...actor, speed: WHALE.cruise })),
  });
  expect(
    whaleGuidance(runtime.current, whaleLevel, false, view).markers[0]?.id,
  ).toBe("ship-bend-in");
  let reachedBend = false;
  for (let i = 0; i < 660; i++) {
    const before = runtime.current;
    const target = whaleGuidance(before, whaleLevel, false, view).markers.find(
      ({ kind }) => kind === "route",
    );
    if (!target) throw new Error("Missing ship approach marker");
    reachedBend ||= target.id === "ship-bend-out";
    const events = step(runtime, aim(podLeader(before).pos, target.pos, 0.83));
    expect(events).not.toContainEqual({
      type: "zone",
      id: "ship-approach-breakwater",
      entered: true,
    });
    if (podLeader(runtime.current).pos.z > 333) break;
  }
  expect(reachedBend).toBe(true);
  expect(podLeader(runtime.current).pos.z).toBeGreaterThan(333);
});

test("W1 only labels the far waypoint as a place to surface after the whole pod clears", () => {
  const submerged = {
    layer: "deep",
    depth: 2,
    direction: null,
    progress: 0,
    breath: 0.83,
    forced: false,
    needsRelease: false,
  } as const;
  const position = staged({ x: 0, z: 445 });
  const diving = {
    ...position,
    actors: position.actors.map((actor) => ({ ...actor, dive: submerged })),
  };
  const cases = [
    diving,
    {
      ...diving,
      actors: diving.actors.map((actor) => ({
        ...actor,
        pos: { ...actor.pos, z: 449 },
      })),
    },
  ];
  const labels = cases.map(
    (state) =>
      whaleGuidance(state, whaleLevel, false, view).markers.find(
        ({ id }) => id === "ship-clear",
      )?.label,
  );
  expect(labels).toEqual(["过船集合水域", "穿越后可在这里上浮"]);
});

test("W3 recognizes a lateral move into the quiet channel and retains it at the merge", () => {
  const runtime = runtimeFrom(
    staged(
      { x: 58, z: 1064 },
      { route: "shipping", triggered: ["C1", "ship-gate"] },
    ),
  );
  const sail = (target: Vec2) => {
    for (
      let i = 0;
      i < 2200 && distance(podLeader(runtime.current).pos, target) > 4;
      i++
    )
      step(runtime, aim(podLeader(runtime.current).pos, target, 0.83));
    expect(
      distance(podLeader(runtime.current).pos, target),
    ).toBeLessThanOrEqual(4);
  };
  sail({ x: -101, z: 1082 });
  sail({ x: -103, z: 1165 });
  expect(runtime.current).toMatchObject({
    route: "quiet",
    routeLocked: false,
    triggered: ["C1", "quiet-gate"],
  });
  expect(
    whaleGuidance(runtime.current, whaleLevel, false, view).notice,
  ).not.toBe("港口疏浚区");
  sail({ x: -103, z: 1234 });
  sail({ x: 62, z: 1313 });
  expect(runtime.current).toMatchObject({ route: "quiet", routeLocked: true });
});

test("checkpoints save on the outer edges and a missed C1 can be recovered after the fork", () => {
  const left = whaleLevel.bounds.min.x;
  const dock = staged({ x: left + 10, z: 555 });
  const paths = [
    { id: "C1", state: dock },
    {
      id: "C1",
      state: staged(
        { x: -105, z: 990 },
        { route: "quiet", triggered: ["quiet-gate"] },
      ),
    },
    {
      id: "C2",
      state: staged(
        { x: whaleLevel.bounds.max.x - 10, z: 1375 },
        {
          route: "shipping",
          routeLocked: true,
          triggered: ["ship-gate", "whale-merge"],
        },
      ),
    },
  ];
  for (const { id, state } of paths) {
    const runtime = runtimeFrom(state);
    expect(step(runtime)).toContainEqual({ type: "checkpoint", id });
    expect(runtime.checkpoint.id).toBe(id);
    expect(readCheckpoint(runtime.checkpoint, whaleLevel, "journey")).toEqual(
      runtime.checkpoint,
    );
  }
});

test("the C2 fallback saves a playable snapshot before a water-surface reunion", () => {
  const runtime = runtimeFrom(
    staged(
      { x: 80, z: 1560 },
      {
        route: "quiet",
        routeLocked: true,
        triggered: ["C1", "quiet-gate", "whale-merge"],
      },
    ),
  );
  expect(step(runtime)).toContainEqual({ type: "checkpoint", id: "C2" });
  expect(runtime.current.phase).toBe("playing");
  expect(readCheckpoint(runtime.checkpoint, whaleLevel, "journey")).toEqual(
    runtime.checkpoint,
  );
  expect(step(runtime)).toContainEqual({ type: "phase", phase: "landing" });
});

test("outward propulsion at the course boundary reports the actual stopped speed", () => {
  const position = { x: whaleLevel.bounds.min.x, z: 649 };
  const state = staged(position);
  const runtime = runtimeFrom({
    ...state,
    actors: state.actors.map((actor) => ({
      ...actor,
      heading: -Math.PI / 2,
      pos: { ...actor.pos, x: Math.max(actor.pos.x, position.x) },
    })),
  });
  for (let i = 0; i < 90; i++)
    step(runtime, { move: { x: -1, z: 0 }, ability: false });
  expect(podLeader(runtime.current)).toMatchObject({ pos: position, speed: 0 });
  expect(runtime.current.energy).toBe(1);
});

test("six surfaced whales at full speed stay playable until the leader glides to a stop", () => {
  const state = staged(
    { x: 80, z: 1545 },
    {
      route: "quiet",
      routeLocked: true,
      triggered: ["C1", "quiet-gate", "whale-merge", "C2"],
    },
  );
  const runtime = runtimeFrom({
    ...state,
    actors: state.actors.map((actor) => ({ ...actor, speed: WHALE.boost })),
  });
  const goal = whaleLevel.zones.find(({ kind }) => kind === "goal");
  for (let i = 0; i < 45; i++) {
    step(runtime, { move: { x: 0, z: 1 }, ability: false });
    expect(runtime.current.phase).toBe("playing");
  }
  expect(goalStatus(runtime.current, goal)).toMatchObject({
    arrived: 6,
    canLand: false,
  });
  expect(
    whaleGuidance(runtime.current, whaleLevel, false, view).arrival.detail,
  ).toContain("松开方向滑停");
  for (let i = 0; i < 180 && runtime.current.phase === "playing"; i++)
    step(runtime);
  expect(runtime.current.phase).toBe("landing");
  expect(podLeader(runtime.current).speed).toBeLessThanOrEqual(
    WHALE.reunionSpeed,
  );
});

test("the sandy channel assists aligned shallow swimming and allows a surface crossing", () => {
  const current = whaleLevel.zones.find(({ id }) => id === "shelf-current");
  if (current?.kind !== "current") throw new Error("Missing sandy channel");
  const { entry, exit } = currentGuide(current);
  const position = { x: (entry.x + exit.x) / 2, z: (entry.z + exit.z) / 2 };
  const state = staged(position, { triggered: ["C1"] });
  const heading = Math.atan2(current.direction.x, current.direction.z);
  const input = aim(position, exit, 0.42, true);
  const surface = runtimeFrom(state);
  step(surface, input);
  expect(surface.current.occupied).not.toContain(current.id);
  const shallow = runtimeFrom({
    ...state,
    actors: state.actors.map((actor) => ({
      ...actor,
      heading,
      dive: { ...actor.dive, layer: "shallow", depth: 1 },
    })),
  });
  step(shallow, input);
  expect(shallow.current.occupied).toContain(current.id);
});
