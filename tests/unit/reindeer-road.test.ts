import { Box3, Mesh, MeshLambertMaterial, Raycaster, Vector3 } from "three";
import { expect, test } from "vitest";
import { groundHeight } from "../../src/levels/reindeer-ground";
import { ReindeerRoad } from "../../src/rendering/reindeer-road";
import { reindeerLevel } from "../fixtures/reindeer";

test("R1 road is batched and its ramp follows the collision passage at each transition", () => {
  const art = new ReindeerRoad(reindeerLevel);
  const { road, bounds } = reindeerLevel;
  const { culvert } = road;
  const ramp = art.group.getObjectByName("Culvert ramps and road verges");
  const lane = art.group.getObjectByName("Vehicle roadway");
  const deck = art.group.getObjectByName("Road deck cutaway");
  if (
    !(ramp instanceof Mesh) ||
    !(lane instanceof Mesh) ||
    !(deck instanceof Mesh)
  )
    throw new Error("Missing R1 visuals");

  expect(art.group.children).toHaveLength(6);
  for (const [part, left, right] of [
    [lane, bounds.min.x, bounds.max.x],
    [deck, culvert.left, culvert.right],
  ] as const) {
    const extent = new Box3().setFromObject(part);
    expect([extent.min.x, extent.max.x, extent.min.z, extent.max.z]).toEqual([
      left,
      right,
      road.near,
      road.far,
    ]);
  }

  const ray = new Raycaster();
  const down = new Vector3(0, -1, 0);
  const x = (culvert.left + culvert.right) / 2;
  for (const z of [
    culvert.near + 0.01,
    (culvert.near + road.near) / 2,
    road.near,
    (road.near + road.far) / 2,
    road.far,
    (road.far + culvert.far) / 2,
    culvert.far - 0.01,
  ]) {
    ray.set(new Vector3(x, 5, z), down);
    const hit = ray.intersectObject(ramp)[0];
    if (!hit) throw new Error(`Passage floor missing at z=${z}`);
    expect(hit.point.y).toBeCloseTo(groundHeight(road, { x, z }), 5);
  }
});

test("R1 deck opens for the tail while the road edges remain above the crossing", () => {
  const view = new ReindeerRoad(reindeerLevel);
  const { road } = reindeerLevel;
  const crossingZ = (road.near + road.far) / 2;
  const deck = view.group.getObjectByName("Road deck cutaway");
  const edging = view.group.getObjectByName("Road edge lines");
  if (
    !(deck instanceof Mesh) ||
    !(deck.material instanceof MeshLambertMaterial) ||
    !(edging instanceof Mesh) ||
    !(edging.material instanceof MeshLambertMaterial)
  )
    throw new Error("Missing R1 cutaway materials");
  const roadUser = { pos: { x: road.culvert.right + 3, z: crossingZ } };
  view.update([roadUser], 1, true);
  expect(deck.material.opacity).toBeCloseTo(0.81);
  const lagging = { pos: { x: road.culvert.right - 2, z: crossingZ } };
  view.update([roadUser, lagging], 1 / 60, true);
  expect(deck.material.opacity).toBeCloseTo(0.12);
  expect(edging.material.transparent).toBe(false);
  const x = (road.culvert.left + road.culvert.right) / 2;
  const ray = new Raycaster();
  for (const z of [road.near + 0.2, road.far - 0.2]) {
    ray.set(new Vector3(x, 5, z), new Vector3(0, -1, 0));
    const coping = ray.intersectObject(edging)[0];
    const pavement = ray.intersectObject(deck)[0];
    if (!coping || !pavement) throw new Error("Missing elevated crossing edge");
    expect(coping.point.y).toBeGreaterThan(pavement.point.y);
  }
  view.update([roadUser], 1 / 60, false);
  expect(deck.material.opacity).toBeGreaterThan(0.12);
  expect(deck.material.opacity).toBeLessThan(0.81);
  view.reset();
  expect(deck.material.opacity).toBe(0.81);
});

test("R1 stone portals keep the visible passage open from both directions", () => {
  const view = new ReindeerRoad(reindeerLevel);
  const masonry = view.group.getObjectByName("Culvert masonry");
  if (!(masonry instanceof Mesh)) throw new Error("Missing R1 masonry");
  const { road } = reindeerLevel;
  const { left, right, depth } = road.culvert;
  const ray = new Raycaster(undefined, undefined, 0, 1.2);
  for (const [edge, direction] of [
    [road.near, 1],
    [road.far, -1],
  ] as const) {
    for (const x of [left + 0.95, (left + right) / 2, right - 0.95]) {
      const z = edge - direction * 0.6;
      const forward = new Vector3(0, 0, direction);
      ray.set(new Vector3(x, -depth * 0.05, z), forward);
      expect(ray.intersectObject(masonry).length).toBeGreaterThan(0);
      ray.set(new Vector3(x, -depth * 0.52, z), forward);
      expect(ray.intersectObject(masonry)).toHaveLength(0);
    }
    const x = (left + right) / 2;
    ray.set(
      new Vector3(x, -depth * 0.47, edge + direction * 0.3),
      new Vector3(0, 1, 0),
    );
    const reveal = ray.intersectObject(masonry)[0];
    if (!reveal) throw new Error("Missing recessed portal reveal");
    expect(reveal.point.y).toBeGreaterThan(-depth * 0.19);
  }
});
