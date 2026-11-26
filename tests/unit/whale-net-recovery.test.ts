import { Box3, InstancedMesh, Matrix4, Vector3 } from "three";
import { expect, test } from "vitest";
import { sweptCircle } from "../../src/levels/geometry";
import { kelpApproaches } from "../../src/levels/whale-kelp";
import { isWhaleNet } from "../../src/levels/whale-geometry";
import { netApproaches } from "../../src/levels/whale-net";
import { drawNetRecovery } from "../../src/rendering/whale-net-recovery";
import { WHALE } from "../../src/simulation/whale-motion";
import { whaleLevel } from "../fixtures/whale";

function point(id: string) {
  const landmark = whaleLevel.landmarks.find((mark) => mark.id === id);
  if (!landmark) throw new Error(`Missing landmark ${id}`);
  return landmark.pos;
}

test("W2 gear, support piles and hoist stay beyond the swimmable world edge", () => {
  const recovery = drawNetRecovery(whaleLevel);
  const dock = recovery.getObjectByName("W2 fishing gear recovery dock");
  if (!dock) throw new Error("Missing fishing gear recovery dock");
  const names = [
    "W2 timber and sorting racks",
    "W2 collected floats",
    "W2 recovered nets",
    "W2 recovered rope and bindings",
  ];
  expect(dock.children.map(({ name }) => name)).toEqual(names);
  const bounds = new Box3().setFromObject(dock);
  expect(bounds.min.x).toBeGreaterThan(whaleLevel.bounds.max.x);
  expect(bounds.min.y).toBeLessThan(0);
  expect(bounds.max.y).toBeGreaterThan(6);
  expect(bounds.min.z).toBeLessThan(point("net-recovery-dock").z);
  expect(bounds.max.z).toBeGreaterThan(point("net-recovery-dock").z);
});

test("W2 paired passage marks bracket the clear route to the kelp bay", () => {
  const recovery = drawNetRecovery(whaleLevel);
  const marks = recovery.getObjectByName("W2 pale green floats");
  const divider = whaleLevel.zones.find(({ id }) => id === "net-divider");
  if (!(marks instanceof InstancedMesh) || !divider)
    throw new Error("Missing W2 lane geometry");
  const laneCenter = point("net-wide");
  const dividerEast = Math.max(...divider.points.map(({ x }) => x));
  const near = Math.min(...divider.points.map(({ z }) => z));
  const far = Math.max(...divider.points.map(({ z }) => z));
  const matrix = new Matrix4();
  const mark = new Vector3();
  const pairs = new Map<number, number[]>();
  expect(marks.count).toBe(12);
  for (let slot = 0; slot < marks.count; slot += 2) {
    marks.getMatrixAt(slot, matrix);
    mark.setFromMatrixPosition(matrix);
    const pair = pairs.get(mark.z) ?? [];
    pair.push(mark.x);
    pairs.set(mark.z, pair);
  }
  expect([...pairs.keys()]).toEqual([near - 7, far + 5, far + 27]);
  for (const pair of pairs.values()) {
    const [left, right] = pair;
    if (left === undefined || right === undefined)
      throw new Error("Unpaired W2 lane marker");
    expect(left).toBeGreaterThan(dividerEast + WHALE.hitRadius);
    expect(right).toBeLessThan(whaleLevel.bounds.max.x - WHALE.hitRadius);
    expect(left).toBeLessThan(laneCenter.x);
    expect(right).toBeGreaterThan(laneCenter.x);
  }

  const path = [...netApproaches.wide.slice(0, 3), ...kelpApproaches.arc].map(
    point,
  );
  const nets = whaleLevel.zones.filter(isWhaleNet);
  for (const [index, from] of path.entries()) {
    const to = path[index + 1];
    if (!to) continue;
    for (const net of nets)
      expect(sweptCircle(net.points, from, to, WHALE.hitRadius)).toBe(false);
  }
});
