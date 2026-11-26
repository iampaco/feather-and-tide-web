import { Box3, InstancedMesh, Matrix4, Mesh, Raycaster, Vector3 } from "three";
import { expect, test } from "vitest";
import { contains } from "../../src/levels/geometry";
import { whaleCoast } from "../../src/rendering/whale-coast";
import { WHALE_DEPTH_Y } from "../../src/rendering/whale-course";
import { WhaleOcean } from "../../src/rendering/whale-ocean";
import { WhaleReef } from "../../src/rendering/whale-reef";
import { whaleLevel } from "../fixtures/whale";

test("W0 above-water coast stays beyond the bay boundary and submerged decor clears the deep swim layer", () => {
  const coast = whaleCoast(whaleLevel, {
    amount: { value: 1 },
    depth: { value: 2 },
  });
  const artFloor = WHALE_DEPTH_Y[2] - 1.8;
  const ocean = new WhaleOcean(whaleLevel);
  for (const [group, name] of [
    [ocean.group, "W0 submerged terraces"],
    [ocean.group, "W0 submerged shore"],
    [coast, "W0 submerged ledges"],
  ] as const) {
    const mesh = group.getObjectByName(name);
    expect(mesh).toBeInstanceOf(Mesh);
    if (!mesh) throw new Error(`Missing ${name}`);
    expect(new Box3().setFromObject(mesh, true).max.y).toBeLessThan(artFloor);
  }
  for (const name of ["W0 headland", "W0 sea arch"]) {
    const mesh = coast.getObjectByName(name);
    if (!(mesh instanceof Mesh)) throw new Error(`Missing ${name}`);
    const index = mesh.geometry.getIndex();
    const vertices = mesh.geometry.getAttribute("position");
    if (!index) throw new Error(`Missing ${name} triangles`);
    let nearestShore = -Infinity;
    for (let i = 0; i < index.count; i += 3) {
      const triangle = [index.getX(i), index.getX(i + 1), index.getX(i + 2)];
      if (triangle.some((vertex) => vertices.getY(vertex) > artFloor))
        nearestShore = Math.max(
          nearestShore,
          ...triangle.map((vertex) => vertices.getZ(vertex)),
        );
    }
    expect(nearestShore).toBeLessThan(whaleLevel.bounds.min.z);
  }
});

test("WH-A07 W3 keeps the sand route open between the reef banks and lights the actual breathing pockets", () => {
  const { group } = new WhaleReef(whaleLevel);
  const rest = whaleLevel.zones.find(({ id }) => id === "quiet-rest");
  const eddy = whaleLevel.zones.find(({ id }) => id === "reef-eddy");
  const flow = whaleLevel.zones.find(({ id }) => id === "reef-current");
  const pool = whaleLevel.landmarks.find(({ id }) => id === "quiet-pool");
  const arc = whaleLevel.landmarks.find(({ id }) => id === "quiet-arc");
  const banks = group.getObjectByName("Submerged rocks");
  const lights = group.getObjectByName("Surface light");
  if (
    !rest ||
    !eddy ||
    !flow ||
    !pool ||
    !arc ||
    !(banks instanceof Mesh) ||
    !(lights instanceof InstancedMesh)
  )
    throw new Error("Incomplete W3 reef layout");

  const artFloor = WHALE_DEPTH_Y[2] - 1.5;
  const banksBounds = new Box3().setFromObject(banks);
  expect(banksBounds.max.y).toBeLessThan(artFloor);
  for (const name of ["Reef terrace fragments", "Reef grass clusters"]) {
    const detail = group.getObjectByName(name);
    if (!detail) throw new Error(`Missing ${name}`);
    expect(new Box3().setFromObject(detail).max.y).toBeLessThan(artFloor);
  }
  for (const bounds of [banksBounds, new Box3().setFromObject(lights)])
    for (const x of [bounds.min.x, bounds.max.x])
      for (const z of [bounds.min.z, bounds.max.z])
        expect(contains(rest.points, { x, z })).toBe(true);

  const ray = new Raycaster();
  const cast = (x: number) => {
    ray.set(new Vector3(x, 0, arc.pos.z), new Vector3(0, -1, 0));
    return ray.intersectObject(banks)[0]?.point.y ?? -Infinity;
  };
  const sand = cast(arc.pos.x);
  expect(sand).toBeGreaterThan(-10.7);
  expect(cast(arc.pos.x - 18) - sand).toBeGreaterThan(0.7);
  expect(cast(arc.pos.x + 18) - sand).toBeGreaterThan(0.4);

  expect(lights.count).toBe(2);
  const placement = new Matrix4();
  const center = new Vector3();
  lights.getMatrixAt(0, placement);
  center.setFromMatrixPosition(placement);
  expect({ x: center.x, z: center.z }).toEqual(pool.pos);
  expect(contains(flow.points, { x: center.x, z: center.z })).toBe(false);
  lights.getMatrixAt(1, placement);
  center.setFromMatrixPosition(placement);
  expect(contains(eddy.points, { x: center.x, z: center.z })).toBe(true);
});

test("W3 route scenery frames both entrances before the route choice while the quiet relief clears deep water", () => {
  const { group } = new WhaleReef(whaleLevel);
  const quiet = whaleLevel.triggers.find((gate) => gate.id === "quiet-gate");
  const ship = whaleLevel.triggers.find((gate) => gate.id === "ship-gate");
  if (
    quiet?.kind !== "route" ||
    quiet.crossingZ === undefined ||
    ship?.kind !== "route" ||
    ship.crossingZ === undefined
  )
    throw new Error("Missing W3 route gates");
  const quietMouth = group.getObjectByName("Quiet entrance shoals");
  const sandFan = group.getObjectByName("Quiet entrance sand fan");
  const shipMarks = group.getObjectByName("Shipping entrance marks");
  if (!quietMouth || !sandFan || !shipMarks)
    throw new Error("Missing entrance scenery");

  const quietBounds = new Box3().setFromObject(quietMouth);
  const fanBounds = new Box3().setFromObject(sandFan);
  const shipBounds = new Box3().setFromObject(shipMarks);
  const divide = Math.max(...quiet.points.map(({ x }) => x));
  expect(quietBounds.min.z).toBeLessThan(quiet.crossingZ);
  expect(quietBounds.max.z).toBeGreaterThan(quiet.crossingZ);
  expect(quietBounds.max.x).toBeLessThan(divide);
  expect(fanBounds.min.z).toBeLessThan(quiet.crossingZ);
  expect(fanBounds.min.x).toBeLessThan(divide);
  expect(shipBounds.min.x).toBeGreaterThan(divide);
  expect(shipBounds.min.z).toBeLessThan(ship.crossingZ);
  expect(shipBounds.max.z).toBeGreaterThan(ship.crossingZ);
  for (const bounds of [quietBounds, fanBounds]) {
    expect(bounds.max.y).toBeLessThan(WHALE_DEPTH_Y[2] - 1.5);
    expect(bounds.min.x).toBeGreaterThan(whaleLevel.bounds.min.x);
    expect(bounds.max.x).toBeLessThan(whaleLevel.bounds.max.x);
  }
});
