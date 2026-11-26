import { Matrix4, Vector3 } from "three";
import { expect, test } from "vitest";
import { LandingRipples, sampleLandingPose } from "../../src/rendering/landing";

test("water contact settles from flight with successive ripples across the flock", () => {
  const entry = sampleLandingPose(0, 0, 4.2, 3.6, -0.8, false);
  const first = sampleLandingPose(0.53, 0, 4.2, 3.6, -0.8, false);
  const tail = sampleLandingPose(0.53, 11, 4.2, 3.6, -0.8, false);
  const end = sampleLandingPose(1, 11, 4.2, 3.6, -0.8, false);
  expect(entry.height).toBe(4.2);
  expect(entry.weight).toBe(0);
  expect(entry.ripple).toBeLessThan(0);
  expect(first.clip).toBe("Land_ShallowWater");
  expect(first.surface).toBe(0);
  expect(first.contact).toBe(1);
  expect(first.ripple).toBeGreaterThan(0);
  expect(tail.contact).toBeLessThan(1);
  expect(tail.ripple).toBeLessThan(0);
  expect(end.seconds).toBeCloseTo(80 / 48);
  expect(end.height).toBeCloseTo(0.16895 * 3.6);
});

test("dry margin is grounded and reduced motion presents a stable settled pose", () => {
  const mud = sampleLandingPose(0.7, 4, 4, 3.5, 1.25, false);
  expect(mud.clip).toBe("Land_Mudflat");
  expect(mud.surface).toBe(1.25);
  expect(mud.height).toBeGreaterThan(mud.surface + 0.55);
  expect(mud.height).toBeLessThan(mud.surface + 0.63);
  expect(mud.ripple).toBeLessThan(0);
  const still = sampleLandingPose(0, 11, 4, 3.5, -0.3, true);
  expect(still).toEqual(sampleLandingPose(1, 11, 4, 3.5, -0.3, true));
  expect(still.height).toBeCloseTo(0.16895 * 3.5);
  expect(still.weight).toBe(1);
  expect(still.ripple).toBeLessThan(0);
});

test("ripples reuse a single batch and clear when the landing effect ends", () => {
  const ripples = new LandingRipples(12);
  ripples.begin();
  ripples.add(3, 812, 0.42, 0);
  ripples.add(-2, 818, -0.2, 0);
  ripples.add(9, 840, 1, 0);
  ripples.finish();

  expect(ripples.mesh.visible).toBe(true);
  expect(ripples.mesh.count).toBe(1);
  const transform = new Matrix4();
  ripples.mesh.getMatrixAt(0, transform);
  const center = new Vector3().setFromMatrixPosition(transform);
  expect(center.x).toBe(3);
  expect(center.y).toBeCloseTo(0.038);
  expect(center.z).toBe(812);

  ripples.begin();
  ripples.finish();
  expect(ripples.mesh.visible).toBe(false);
  expect(ripples.mesh.count).toBe(0);
});
