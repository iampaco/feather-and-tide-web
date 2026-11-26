import { Box3, Mesh } from "three";
import { expect, test } from "vitest";
import { NEUTRAL_INPUT } from "../../src/core/game";
import { contains } from "../../src/levels/geometry";
import {
  WhaleWatching,
  watchingBoundaryLandmarks,
  watchingVesselAt,
} from "../../src/rendering/whale-watching";
import { goalStatus, tickWorld } from "../../src/simulation/world";
import { podAt, whaleLevel } from "../fixtures/whale";

const reduced = { low: true, reduced: true };

test("W4 watching vessel slows by the buoy line and stays outside the voyage", () => {
  const [nearId, farId] = watchingBoundaryLandmarks;
  const near = whaleLevel.landmarks.find(({ id }) => id === nearId)?.pos;
  const far = whaleLevel.landmarks.find(({ id }) => id === farId)?.pos;
  if (!near || !far) throw new Error("Missing observation buoy limits");
  const view = new WhaleWatching(whaleLevel);
  const hull = view.group.getObjectByName(
    "Whale-watching vessel hull and deck",
  );
  const wake = view.group.getObjectByName("Whale-watching wake");
  if (!(hull instanceof Mesh) || !(wake instanceof Mesh))
    throw new Error("Missing whale-watching vessel");
  const bound = whaleLevel.bounds.max.x;
  const box = new Box3();
  const maximumSpeed = watchingVesselAt(0, bound, near.z, far.z).speed;
  view.update(0, reduced, 0);
  const longWake = wake.scale.z;

  // Sample more than a full lap, including the sections where the hull turns.
  let slowed = 0;
  let turned = 0;
  for (let tick = 0; tick <= 5400; tick += 17) {
    const pose = watchingVesselAt(tick, bound, near.z, far.z);
    view.update(tick, reduced, 0);
    view.group.updateMatrixWorld(true);
    expect(box.setFromObject(hull).min.x).toBeGreaterThan(bound);
    if (pose.heading !== 0) {
      turned++;
    } else if (pose.z >= near.z && pose.z <= far.z) {
      expect(pose.speed).toBeLessThan(maximumSpeed * 0.42);
      expect(wake.scale.z).toBeLessThan(longWake * 0.4);
      slowed++;
    }
  }
  expect(slowed).toBeGreaterThan(40);
  expect(turned).toBeGreaterThan(40);

  // Returning to a saved tick restores the same placement and wake.
  view.update(620, reduced, 0);
  const saved = hull.parent?.position.toArray();
  const savedWake = wake.scale.z;
  view.update(1210, reduced, 0);
  view.update(620, reduced, 0);
  expect(hull.parent?.position.toArray()).toEqual(saved);
  expect(wake.scale.z).toBe(savedWake);
});

test("W4 the observation waypoint permits optional coasting and safe surfacing", () => {
  const mark = whaleLevel.landmarks.find(({ id }) => id === "watching-coast");
  const rest = whaleLevel.zones.find(({ id }) => id === "watching-rest");
  if (!mark || rest?.kind !== "sanctuary")
    throw new Error("Missing inner observation waters");

  const start = podAt(mark.pos);
  for (const actor of start.actors)
    expect(contains(rest.points, actor.pos)).toBe(true);
  const state = tickWorld(start, NEUTRAL_INPUT, whaleLevel).state;
  expect(state.segmentId).toBe("W4");
  expect(state.occupied).toContain(rest.id);
  expect(state.phase).toBe("playing");
  expect(state.actors).toHaveLength(6);
  const goal = whaleLevel.zones.find(({ kind }) => kind === "goal");
  expect(goalStatus(state, goal).arrived).toBe(0);

  const through = { ...mark.pos, x: 62 };
  expect(contains(rest.points, through)).toBe(false);
  const outside = tickWorld(podAt(through), NEUTRAL_INPUT, whaleLevel).state;
  expect(outside.phase).toBe("playing");
  expect(outside.occupied).toContain("offshore-rest");
});
