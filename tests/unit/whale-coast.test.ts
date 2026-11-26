import { Box3, InstancedMesh, Matrix4, Mesh, Raycaster, Vector3 } from "three";
import { expect, test } from "vitest";
import {
  bayChannelBounds,
  bayHeadland,
  bayTerraces,
  whaleCoast,
} from "../../src/rendering/whale-coast";
import { WHALE_DEPTH_Y } from "../../src/rendering/whale-course";
import { whaleLevel } from "../fixtures/whale";

test("the bay shelf meets the submerged shore without an open seam", () => {
  const shore = bayHeadland(whaleLevel, true).getAttribute("position");
  const shelf = bayTerraces(whaleLevel).getAttribute("position");
  const outerZByX = new Map<number, number>();
  for (let i = 0; i < shore.count; i++) {
    const x = shore.getX(i);
    outerZByX.set(x, Math.max(shore.getZ(i), outerZByX.get(x) ?? -Infinity));
  }
  expect(outerZByX.size).toBeGreaterThan(2);
  for (let i = 0; i < outerZByX.size; i++) {
    expect(shelf.getY(i)).toBeCloseTo(-11.08);
    expect(shelf.getZ(i)).toBe(outerZByX.get(shelf.getX(i)));
  }
});

test("the bay shelf leaves a low channel that opens into the waiting water", () => {
  const shelf = new Mesh(bayTerraces(whaleLevel));
  const ray = new Raycaster();
  const down = new Vector3(0, -1, 0);
  const height = (x: number, z: number) => {
    ray.set(new Vector3(x, 0, z), down);
    const hit = ray.intersectObject(shelf)[0];
    if (!hit) throw new Error(`No bay shelf at ${x}, ${z}`);
    return hit.point.y;
  };
  for (const z of [whaleLevel.spawn.z, 104, 210]) {
    const { west, east } = bayChannelBounds(whaleLevel, z);
    const channel = height((west + east) / 2, z);
    expect(height(west - 29, z) - channel).toBeGreaterThan(2);
    expect(height(east + 29, z) - channel).toBeGreaterThan(2);
  }
  const waiting = bayChannelBounds(whaleLevel, 327);
  const mouth = bayChannelBounds(whaleLevel, 210);
  expect(waiting.east - waiting.west).toBeGreaterThan(mouth.east - mouth.west);
  expect(height(35, 333)).toBeLessThan(-11);
  expect(new Box3().setFromObject(shelf).max.y).toBeLessThan(
    WHALE_DEPTH_Y[2] - 1.8,
  );
});

test("the bay rock clusters nest in the seabed outside the open channel", () => {
  const coast = whaleCoast(whaleLevel, {
    amount: { value: 1 },
    depth: { value: 0 },
  });
  const rocks = coast.getObjectByName("W0 submerged ledges");
  if (!(rocks instanceof InstancedMesh)) throw new Error("Missing bay rocks");

  const shelf = new Mesh(bayTerraces(whaleLevel));
  const vertices = rocks.geometry.getAttribute("position");
  const matrix = new Matrix4();
  const vertex = new Vector3();
  const center = new Vector3();
  const ray = new Raycaster();
  const down = new Vector3(0, -1, 0);
  for (let i = 0; i < rocks.count; i++) {
    rocks.getMatrixAt(i, matrix);
    center.setFromMatrixPosition(matrix);
    ray.set(center.clone().setY(0), down);
    let lowest = Infinity;
    for (let j = 0; j < vertices.count; j++) {
      vertex.fromBufferAttribute(vertices, j).applyMatrix4(matrix);
      const { west, east } = bayChannelBounds(whaleLevel, vertex.z);
      expect(vertex.x < west || vertex.x > east).toBe(true);
      lowest = Math.min(lowest, vertex.y);
    }
    const ground = ray.intersectObject(shelf)[0];
    if (!ground) throw new Error(`Missing shelf under rock ${i}`);
    expect(lowest).toBeLessThan(ground.point.y);
  }
});
