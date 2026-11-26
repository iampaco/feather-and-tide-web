import {
  Box3,
  InstancedMesh,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  Vector3,
} from "three";
import { expect, test } from "vitest";
import { contains } from "../../src/levels/geometry";
import {
  ReindeerRoutes,
  reindeerFencePassages,
} from "../../src/rendering/reindeer-routes";
import { reindeerLevel } from "../fixtures/reindeer";

test("R2 gate spans reflect the real openings and visual fence pieces preserve their clearance", () => {
  const passages = reindeerFencePassages(reindeerLevel);
  expect(passages.map(({ wholeHerd }) => wholeHerd)).toEqual([
    false,
    true,
    true,
    true,
    true,
    true,
  ]);
  expect(passages.map(({ left, right }) => right - left)).toEqual([
    expect.closeTo(1.7),
    expect.closeTo(4.6),
    14,
    10,
    expect.closeTo(4.6),
    14,
  ]);
  const fences = reindeerLevel.barriers.filter(({ kind }) => kind === "fence");
  const art = new ReindeerRoutes(reindeerLevel);
  const rails = art.group.getObjectByName("R2 rails and gateposts");
  if (!(rails instanceof InstancedMesh)) throw new Error("Missing fence mesh");
  const transform = new Matrix4();
  const piece = new Box3();
  for (let index = 0; index < rails.count; index++) {
    rails.getMatrixAt(index, transform);
    piece
      .set(new Vector3(-0.5, -0.5, -0.5), new Vector3(0.5, 0.5, 0.5))
      .applyMatrix4(transform);
    const center = piece.getCenter(new Vector3());
    const fence = fences.find(({ points }) =>
      contains(points, { x: center.x, z: center.z }),
    );
    expect(fence).toBeDefined();
    for (const x of [piece.min.x + 0.0001, piece.max.x - 0.0001])
      for (const z of [piece.min.z + 0.0001, piece.max.z - 0.0001])
        expect(fence && contains(fence.points, { x, z })).toBe(true);
  }
});

test("R2 route pigments cross every real passage and stay off the fence spans", () => {
  const { group } = new ReindeerRoutes(reindeerLevel);
  const trails = group.getObjectByName(
    "R2 wide double track and narrow single track",
  );
  if (!(trails instanceof Mesh)) throw new Error("Missing fence track pigment");
  const positions = trails.geometry.getAttribute("position");
  const pigment = trails.geometry.getAttribute("color");
  const passages = reindeerFencePassages(reindeerLevel);
  const painted = new Set<number>();

  for (let i = 0; i < positions.count; i++) {
    if (pigment.getW(i) <= 0.36) continue;
    const z = positions.getZ(i);
    if (!passages.some(({ near, far }) => z >= near && z <= far)) continue;
    const x = positions.getX(i);
    const crossing = passages.findIndex(
      ({ left, right, near, far }) =>
        x > left && x < right && z >= near && z <= far,
    );
    expect(crossing).toBeGreaterThanOrEqual(0);
    painted.add(crossing);
  }

  expect(painted.size).toBe(passages.length);
});

test("R3 visibly branches upstream of the route trigger and grounds the old cut and vegetation", () => {
  const { group } = new ReindeerRoutes(reindeerLevel);
  const paths = group.getObjectByName(
    "R3 dust contours and green belt strokes",
  );
  const cut = group.getObjectByName("R3 old cut relief");
  const shoots = group.getObjectByName("R3 restored bank shoots");
  const barrier = reindeerLevel.barriers.find(({ id }) => id === "old-cut");
  const supply = reindeerLevel.zones.find(({ id }) => id === "green-supply");
  const gate = reindeerLevel.triggers.find(({ id }) => id === "green-gate");
  if (
    !(paths instanceof Mesh) ||
    !(cut instanceof Mesh) ||
    !(shoots instanceof InstancedMesh) ||
    !barrier ||
    !supply ||
    gate?.kind !== "route" ||
    gate.crossingZ === undefined
  )
    throw new Error("Incomplete route art");
  const divide = Math.max(...gate.points.map(({ x }) => x));
  const positions = paths.geometry.getAttribute("position");
  const rgba = paths.geometry.getAttribute("color");
  const beforeChoice = new Set<number>();
  for (let i = 0; i < positions.count; i++) {
    if (positions.getZ(i) < gate.crossingZ - 6 && rgba.getW(i) > 0.3)
      beforeChoice.add(Math.sign(positions.getX(i) - divide));
  }
  expect(beforeChoice).toEqual(new Set([-1, 1]));

  const ridge = cut.geometry.getAttribute("position");
  for (let vertex = 0; vertex < ridge.count; vertex++)
    expect(
      contains(barrier.points, {
        x: ridge.getX(vertex),
        z: ridge.getZ(vertex),
      }),
    ).toBe(true);
  const transform = new Matrix4();
  const point = new Vector3();
  for (let i = 0; i < shoots.count; i++) {
    shoots.getMatrixAt(i, transform);
    point.setFromMatrixPosition(transform);
    expect(contains(supply.points, { x: point.x, z: point.z })).toBe(true);
  }
});

test("R3 dust keeps its authored boundary readable through all three simulation phases", () => {
  const art = new ReindeerRoutes(reindeerLevel);
  const { zoneIds, phaseTicks, calmTicks, warningTicks, activeTicks } =
    reindeerLevel.dustCycle;
  const drift = art.group.getObjectByName("R3 suspended dust strokes");
  if (
    !(drift instanceof Mesh) ||
    !(drift.material instanceof MeshBasicMaterial)
  )
    throw new Error("Missing dust strokes");

  const period = calmTicks + warningTicks + activeTicks;
  const samples = [0, calmTicks, calmTicks + warningTicks].map(
    (offset) => (offset + period - phaseTicks) % period,
  );
  const strengths = samples.map((tick) => {
    art.update(tick);
    return drift.material instanceof MeshBasicMaterial
      ? drift.material.opacity
      : 0;
  });
  expect(strengths[0]).toBeLessThan(strengths[1] ?? 0);
  expect(strengths[1]).toBeLessThan(strengths[2] ?? 0);

  for (const id of zoneIds) {
    const zone = reindeerLevel.zones.find((item) => item.id === id);
    const boundary = art.group.getObjectByName(id);
    if (
      !zone ||
      !(boundary instanceof Mesh) ||
      !(boundary.material instanceof MeshBasicMaterial)
    )
      throw new Error(`Missing dust boundary ${id}`);
    const edge = boundary.geometry.getAttribute("position");
    const pigment = boundary.geometry.getAttribute("color");
    for (let i = 0; i < edge.count; i += 2) {
      expect(zone.points).toContainEqual({ x: edge.getX(i), z: edge.getZ(i) });
      expect(pigment.getW(i)).toBeGreaterThan(0);
    }
    art.update(samples[0] ?? 0);
    expect(boundary.material.opacity).toBeGreaterThan(0);
  }
});

test("R3 talus uses three-dimensional fragments inside the mine barrier footprints", () => {
  const { group } = new ReindeerRoutes(reindeerLevel);
  const talus = group.getObjectByName("R3 scree at the foot of the cut");
  if (!(talus instanceof InstancedMesh)) throw new Error("Missing mine talus");
  const slopes = reindeerLevel.barriers.filter(
    ({ kind, id }) => kind === "slope" && !id.startsWith("snowbank-"),
  );
  const vertices = talus.geometry.getAttribute("position");
  const transform = new Matrix4();
  const at = new Vector3();
  let tallest = 0;
  expect(talus.count).toBeGreaterThan(0);

  for (let i = 0; i < talus.count; i++) {
    talus.getMatrixAt(i, transform);
    at.setFromMatrixPosition(transform);
    const barrier = slopes.find(({ points }) =>
      contains(points, { x: at.x, z: at.z }),
    );
    if (!barrier) throw new Error("A talus fragment has no source barrier");
    for (let vertex = 0; vertex < vertices.count; vertex++) {
      at.fromBufferAttribute(vertices, vertex).applyMatrix4(transform);
      expect(contains(barrier.points, { x: at.x, z: at.z })).toBe(true);
      tallest = Math.max(tallest, at.y);
    }
  }

  expect(tallest).toBeGreaterThan(0.6);
});

test("R3 elevated dust stays inside the two channels and samples the restored phase", () => {
  const art = new ReindeerRoutes(reindeerLevel);
  const haze = art.group.getObjectByName("R3 airborne dust");
  if (!(haze instanceof Mesh) || !(haze.material instanceof MeshBasicMaterial))
    throw new Error("Missing elevated dust material");
  const { material } = haze;
  const { zoneIds, phaseTicks, calmTicks, warningTicks, activeTicks } =
    reindeerLevel.dustCycle;
  const channels = reindeerLevel.zones.filter(({ id }) => zoneIds.includes(id));
  const positions = haze.geometry.getAttribute("position");
  const populated = new Set<string>();
  let highest = 0;
  for (let i = 0; i < positions.count; i++) {
    const at = { x: positions.getX(i), z: positions.getZ(i) };
    const channel = channels.find(({ points }) => contains(points, at));
    if (!channel) throw new Error("Dust projects outside its source channel");
    populated.add(channel.id);
    highest = Math.max(highest, positions.getY(i));
  }
  expect(populated).toEqual(new Set(zoneIds));
  expect(highest).toBeGreaterThan(0.7);
  expect(highest).toBeLessThan(2.1);

  const period = calmTicks + warningTicks + activeTicks;
  const sample = (offset: number) => {
    art.update((offset + period - phaseTicks) % period);
    return material.opacity;
  };
  const calm = sample(0);
  const warning = sample(calmTicks);
  const active = sample(calmTicks + warningTicks);
  expect(calm).toBeLessThan(warning);
  expect(warning).toBeLessThan(active);
  expect(sample(0)).toBe(calm);
});
