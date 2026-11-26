import { Mesh, ShaderMaterial, Vector3 } from "three";
import { expect, test } from "vitest";
import { STEP_SEC } from "../../src/core/clock";
import { NEUTRAL_INPUT, type WhaleState } from "../../src/core/game";
import { distance } from "../../src/core/math";
import { GameRuntime } from "../../src/core/runtime";
import { contains } from "../../src/levels/geometry";
import { whaleCrossflowVelocity } from "../../src/levels/whale-crossflow";
import {
  isWhaleBreakwater,
  isWhaleNet,
  occupiesLayer,
} from "../../src/levels/whale-geometry";
import { WhaleBreakwater } from "../../src/rendering/whale-breakwater";
import { tickWhale } from "../../src/simulation/whale-world";
import { goalStatus } from "../../src/simulation/world";
import { aim } from "../fixtures/flight";
import { podAt, podLeader, whaleLevel } from "../fixtures/whale";

const crossflows = whaleLevel.zones.filter(
  (zone) => zone.kind === "crossCurrent",
);
const breakwater = whaleLevel.zones
  .filter(isWhaleBreakwater)
  .find(({ id }) => id === "offshore-breakwater");
const goal = whaleLevel.zones.find(({ kind }) => kind === "goal");

test("breakwater appearance follows the solid collision footprint at all layers", () => {
  if (!breakwater) throw new Error("Missing breakwater");
  expect(isWhaleNet(breakwater)).toBe(false);
  for (const layer of ["surface", "shallow", "deep"] as const)
    expect(occupiesLayer(breakwater, layer)).toBe(true);

  const testPod = { ...podAt({ x: 9, z: 1409.4 }), segmentId: "W4" };
  const before: WhaleState = {
    ...testPod,
    actors: testPod.actors.map((actor) => ({ ...actor, speed: 9 })),
  };
  const after = tickWhale(
    before,
    { ...NEUTRAL_INPUT, move: { x: 0, z: 1 } },
    whaleLevel,
  ).state;
  expect(after.occupied).toContain(breakwater.id);
  expect(podLeader(after).pos).toEqual(podLeader(before).pos);

  const art = new WhaleBreakwater(whaleLevel);
  const body = art.group
    .getObjectByName(breakwater.id)
    ?.getObjectByName("Breakwater footprint");
  if (!(body instanceof Mesh)) throw new Error("Missing solid breakwater");
  const modelPoints = body.geometry.getAttribute("position");
  const point = new Vector3();
  const visibleOutline = new Set<string>();
  for (let index = 0; index < modelPoints.count; index++) {
    point.fromBufferAttribute(modelPoints, index);
    visibleOutline.add(`${point.x.toFixed(3)},${point.z.toFixed(3)}`);
  }
  for (const { x, z } of breakwater.points)
    expect(visibleOutline.has(`${x.toFixed(3)},${z.toFixed(3)}`)).toBe(true);
});

test("crossflow moves an idle leader and a separated tail from the same fixed world tick", () => {
  const openWater = { x: 58, z: 1444 };
  const pod = podAt(openWater);
  const actors = pod.actors.map((actor, index) =>
    index === pod.actors.length - 1
      ? {
          ...actor,
          status: "strayed" as const,
          pos: { x: 41, z: 1432 },
          rescueTicks: 100,
        }
      : actor,
  );
  const state = { ...pod, actors, segmentId: "W4" };
  const runtime = new GameRuntime(whaleLevel, "journey", {
    version: 1,
    id: "start",
    state,
  });
  runtime.dispatch({ type: "pause" });
  const paused = runtime.current;
  expect(runtime.step()).toEqual([]);
  expect(runtime.current).toBe(paused);
  runtime.dispatch({ type: "resume" });
  runtime.step();
  const advanced = runtime.current;
  expect(advanced.tick).toBe(state.tick + 1);
  const leading = podLeader(advanced);
  expect(leading.pos.x - openWater.x).toBeCloseTo(3.1 * STEP_SEC, 7);
  expect(leading.pos.z).toBe(openWater.z);
  expect(leading.speed).toBe(0);
  expect(leading.heading).toBe(0);
  expect(advanced.actors.at(-1)?.pos.x).toBeCloseTo(41 + 3.1 * STEP_SEC, 7);
  expect(advanced.actors.at(-1)?.pos.z).toBe(1432);
  expect(advanced.occupied).toContain("breakwater-cross-current");
  expect(
    whaleCrossflowVelocity(crossflows, { x: 94, z: 1422 }),
  ).toBeUndefined();
  const edge = whaleCrossflowVelocity(crossflows, { x: 58, z: 1458 });
  expect(edge?.x).toBeGreaterThan(0);
  expect(edge?.x).toBeLessThan(3.1);

  runtime.dispatch({ type: "pause" });
  runtime.dispatch({ type: "retry" });
  expect(runtime.current).toEqual(state);
  runtime.step();
  expect(runtime.current).toEqual(advanced);
});

test.each(["crossing", "wide"] as const)(
  "the W4 %s brings all six whales through to the same surface finish",
  (route) => {
    if (!goal) throw new Error("Missing offshore goal");
    const x = route === "crossing" ? 62 : 94;
    const start: WhaleState = {
      ...podAt({ x, z: 1392 }),
      segmentId: "W4",
      route: "quiet",
      routeLocked: true,
      triggered: ["quiet-gate", "whale-merge", "C2"],
    };
    const runtime = new GameRuntime(whaleLevel, "journey", {
      version: 1,
      id: "C2",
      state: start,
    });
    const marker = { x: 81, z: 1559 };
    let enteredFlow = false;
    let reachedRest = false;
    for (
      let step = 0;
      step < 2500 && runtime.current.phase === "playing";
      step++
    ) {
      const { pos } = podLeader(runtime.current);
      const input =
        pos.z < 1463
          ? {
              ...NEUTRAL_INPUT,
              move: {
                x: route === "crossing" && pos.z >= 1423 ? -0.27 : 0,
                z: 0.82,
              },
            }
          : distance(pos, marker) < 4
            ? NEUTRAL_INPUT
            : aim(pos, marker, 0.83);
      runtime.dispatch({ type: "input", input });
      runtime.step();
      enteredFlow ||= runtime.current.occupied.includes(
        "breakwater-cross-current",
      );
      reachedRest ||= runtime.current.occupied.includes("offshore-rest");
      expect(runtime.current.occupied).not.toContain(breakwater?.id);
    }
    expect(reachedRest).toBe(true);
    expect(enteredFlow).toBe(route === "crossing");
    expect(runtime.current.phase).toBe("landing");
    expect(goalStatus(runtime.current, goal)).toMatchObject({
      arrived: 6,
      canLand: true,
    });
  },
);

test("reduced motion keeps the directional arrows inside the authored current", () => {
  const art = new WhaleBreakwater(whaleLevel);
  const flow = crossflows[0];
  const arrows = art.group.getObjectByName("Breakwater flow arrows");
  const foam = art.group.getObjectByName("Breakwater foam");
  if (!flow || !(arrows instanceof Mesh) || !(foam instanceof Mesh))
    throw new Error("Missing rendered crossflow");
  if (!(foam.material instanceof ShaderMaterial))
    throw new Error("Missing drifting foam material");
  expect(arrows.visible).toBe(true);
  art.update(360, { low: false, reduced: false }, 0);
  expect(foam.material.uniforms.travel?.value).toBeCloseTo(18.6);
  art.update(360, { low: true, reduced: true }, 2);
  expect(foam.material.uniforms.travel?.value).toBe(0);
  expect(arrows.visible).toBe(true);
  expect(arrows.parent?.position.y).toBeLessThan(-5);
  const position = arrows.geometry.getAttribute("position");
  expect(position.count).toBeGreaterThan(0);
  for (let index = 0; index < position.count; index++) {
    expect(
      contains(flow.points, {
        x: position.getX(index),
        z: position.getZ(index),
      }),
    ).toBe(true);
  }
});
