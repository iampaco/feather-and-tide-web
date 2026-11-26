import {
  Box3,
  InstancedMesh,
  Matrix4,
  Mesh,
  MeshStandardMaterial,
  ShaderMaterial,
  Vector3,
} from "three";
import { expect, test } from "vitest";
import type { Vec2 } from "../../src/core/math";
import { contains, sweptCircle } from "../../src/levels/geometry";
import {
  canRideCurrent,
  currentGuide,
  flowProjection,
} from "../../src/levels/whale-current";
import { kelpApproaches } from "../../src/levels/whale-kelp";
import {
  hazardOffset,
  hazardPoints,
  hazardStep,
} from "../../src/levels/whale-geometry";
import { WHALE_DEPTH_Y, WhaleCourse } from "../../src/rendering/whale-course";
import { podAt, podLeader, whaleLevel } from "../fixtures/whale";

function course() {
  return new WhaleCourse(whaleLevel, {
    amount: { value: 0 },
    depth: { value: 0 },
  });
}

function onOutline(points: readonly Vec2[], { x, z }: Vec2): boolean {
  return points.slice(1).some((b, index) => {
    const a = points[index];
    if (!a) return false;
    const cross = (b.x - a.x) * (z - a.z) - (b.z - a.z) * (x - a.x);
    return (
      Math.abs(cross) < 0.002 &&
      x >= Math.min(a.x, b.x) - 0.0001 &&
      x <= Math.max(a.x, b.x) + 0.0001 &&
      z >= Math.min(a.z, b.z) - 0.0001 &&
      z <= Math.max(a.z, b.z) + 0.0001
    );
  });
}

test("W1 cargo waterline shares the moving footprint and reverses foam at the simulation tick", () => {
  const view = course();
  const hazard = whaleLevel.zones.find(({ id }) => id === "cargo-ship");
  const hull = view.group.getObjectByName("Cargo hull");
  const fittings = view.group.getObjectByName("Cargo deck fittings");
  const containers = view.group.getObjectByName("Cargo container stacks");
  const foam = view.group.getObjectByName("Cargo bow and stern foam");
  if (
    hazard?.kind !== "hazard" ||
    !hazard.motion ||
    !(hull instanceof Mesh) ||
    !(fittings instanceof Mesh) ||
    !(containers instanceof InstancedMesh) ||
    !(foam instanceof Mesh) ||
    !(foam.material instanceof ShaderMaterial)
  )
    throw new Error("Missing W1 geometry");
  const turn = hazard.motion.periodTicks / 2 - hazard.motion.phaseTicks;
  const point = new Vector3();
  const waterline = hull.geometry.getAttribute("position");
  const deck = fittings.geometry.getAttribute("position");
  const container = containers.geometry.getAttribute("position");
  const placement = new Matrix4();
  for (const tick of [turn - 1, turn, turn + 55]) {
    view.update(tick, false, false, { low: true, reduced: true });
    view.group.updateMatrixWorld(true);
    expect(hull.parent?.position.toArray()).toEqual([
      hazardOffset(hazard, tick).x,
      0,
      hazardOffset(hazard, tick).z,
    ]);
    expect(foam.parent?.rotation.y).toBe(
      Math.atan2(hazardStep(hazard, tick).x, 0),
    );
    const outline = hazardPoints(hazard, tick);
    let found = 0;
    for (let index = 0; index < waterline.count; index++) {
      if (waterline.getY(index) !== 0) continue;
      const world = point
        .fromBufferAttribute(waterline, index)
        .applyMatrix4(hull.matrixWorld);
      expect(onOutline(outline, world)).toBe(true);
      found++;
    }
    expect(found).toBeGreaterThanOrEqual(outline.length - 1);
    for (let index = 0; index < deck.count; index++)
      expect(
        contains(
          outline,
          point
            .fromBufferAttribute(deck, index)
            .applyMatrix4(fittings.matrixWorld),
        ),
      ).toBe(true);
    const tiers = new Set<number>();
    for (let index = 0; index < containers.count; index++) {
      containers.getMatrixAt(index, placement);
      tiers.add(point.setFromMatrixPosition(placement).y);
      for (let vertex = 0; vertex < container.count; vertex++)
        expect(
          contains(
            outline,
            point
              .fromBufferAttribute(container, vertex)
              .applyMatrix4(placement)
              .applyMatrix4(containers.matrixWorld),
          ),
        ).toBe(true);
    }
    expect(tiers.size).toBe(2);
    expect(foam.material.uniforms.time?.value).toBe(0);
    const strength = foam.material.uniforms.strength?.value;
    if (tick === turn) expect(strength).toBe(0);
    else if (tick > turn) expect(strength).toBe(1);
    else expect(strength).toBeLessThan(0.01);
  }
});

test("W2 net curtain stays on the three-layer footprint and retains both east anchors", () => {
  const view = course();
  const zone = whaleLevel.zones.find(({ id }) => id === "drift-net");
  const weave = view.group.getObjectByName("Net curtain and cables");
  const floats = view.group.getObjectByName("Net anchor floats");
  const weights = view.group.getObjectByName("Net lead weights");
  if (
    zone?.kind !== "hazard" ||
    !(weave instanceof Mesh) ||
    !(floats instanceof InstancedMesh) ||
    !(weights instanceof InstancedMesh)
  )
    throw new Error("Missing W2 geometry");
  const positions = weave.geometry.getAttribute("position");
  let highest = -Infinity;
  let lowest = Infinity;
  for (let index = 0; index < positions.count; index++) {
    expect(
      onOutline(zone.points, {
        x: positions.getX(index),
        z: positions.getZ(index),
      }),
    ).toBe(true);
    highest = Math.max(highest, positions.getY(index));
    lowest = Math.min(lowest, positions.getY(index));
  }
  expect(highest).toBeGreaterThan(0);
  expect(lowest).toBeLessThan(-7);
  const east = Math.max(...zone.points.map(({ x }) => x));
  const corners = zone.points
    .filter(({ x }) => x === east)
    .map(({ z }) => z)
    .sort((a, b) => a - b);
  const anchors: number[] = [];
  const matrix = new Matrix4();
  const position = new Vector3();
  expect(weights.count).toBe(floats.count);
  for (let index = 0; index < floats.count; index++) {
    floats.getMatrixAt(index, matrix);
    position.setFromMatrixPosition(matrix);
    if (position.x === east && matrix.elements[0] > 1) anchors.push(position.z);
    const anchor = { x: position.x, z: position.z };
    weights.getMatrixAt(index, matrix);
    position.setFromMatrixPosition(matrix);
    expect(position.x).toBe(anchor.x);
    expect(position.z).toBe(anchor.z);
    expect(position.y).toBeLessThan(WHALE_DEPTH_Y[2]);
  }
  expect(anchors.sort((a, b) => a - b)).toEqual(corners);
  expect(new Box3().setFromObject(floats).max.x).toBeLessThanOrEqual(
    east + 1.72,
  );
});

test("W2 kelp and submerged shelves keep both signed approaches and the deep swim layer clear", () => {
  const view = course();
  const zone = whaleLevel.zones.find(({ id }) => id === "net-kelp");
  if (zone?.kind !== "supply") throw new Error("Missing W2 kelp shelter");
  const route = (ids: readonly string[]) =>
    ids.map((id) => {
      const landmark = whaleLevel.landmarks.find((mark) => mark.id === id);
      if (!landmark) throw new Error(`Missing W2 landmark ${id}`);
      return landmark.pos;
    });
  const approaches = [route(kelpApproaches.short), route(kelpApproaches.arc)];
  const matrix = new Matrix4();
  const point = new Vector3();
  view.update(0, false, false, { low: true, reduced: true });
  for (const name of ["Net shelter kelp", "Net shelter submerged shelves"]) {
    const mesh = view.group.getObjectByName(name);
    if (!(mesh instanceof InstancedMesh)) throw new Error(`Missing W2 ${name}`);
    expect(mesh.visible).toBe(true);
    expect(new Box3().setFromObject(mesh).max.y).toBeLessThan(
      WHALE_DEPTH_Y[2] - 1.8,
    );
    const positions = mesh.geometry.getAttribute("position");
    for (let instance = 0; instance < mesh.count; instance++) {
      mesh.getMatrixAt(instance, matrix);
      const bounds = new Box3();
      for (let vertex = 0; vertex < positions.count; vertex++) {
        point.fromBufferAttribute(positions, vertex).applyMatrix4(matrix);
        expect(contains(zone.points, point)).toBe(true);
        bounds.expandByPoint(point);
      }
      const { min, max } = bounds;
      const outline = [
        { x: min.x, z: min.z },
        { x: max.x, z: min.z },
        { x: max.x, z: max.z },
        { x: min.x, z: max.z },
        { x: min.x, z: min.z },
      ];
      for (const path of approaches)
        for (const [index, from] of path.entries()) {
          const to = path[index + 1];
          if (to) expect(sweptCircle(outline, from, to, 2)).toBe(false);
        }
    }
  }
});

test("W1 submerged art keeps the shallow mark and moving shadow on the hull's footprint", () => {
  const view = course();
  const hazard = whaleLevel.zones.find(({ id }) => id === "cargo-ship");
  const hull = view.group.getObjectByName("Cargo hull");
  const deck = view.group.getObjectByName("Cargo deck fittings");
  const shadow = view.group.getObjectByName("Cargo submerged shadow");
  const occupied = view.group.getObjectByName("Cargo submerged occupancy");
  if (
    hazard?.kind !== "hazard" ||
    !(hull instanceof Mesh) ||
    !(hull.material instanceof MeshStandardMaterial) ||
    !(deck instanceof Mesh) ||
    !(deck.material instanceof MeshStandardMaterial) ||
    !(shadow instanceof Mesh) ||
    !(shadow.material instanceof ShaderMaterial) ||
    !occupied
  )
    throw new Error("Missing W1 submerged art");
  const tick = 3600;
  const settings = { low: true, reduced: true };
  view.update(tick, false, false, settings, 0);
  expect(deck.material.opacity).toBe(1);
  const surfaceShadow = shadow.material.uniforms.strength?.value;
  view.update(tick, false, false, settings, 2);
  expect(deck.material.opacity).toBeLessThan(hull.material.opacity);
  expect(hull.material.depthWrite).toBe(false);
  expect(shadow.material.uniforms.strength?.value).toBeGreaterThan(
    surfaceShadow,
  );
  expect(shadow.position.y).toBeGreaterThan(WHALE_DEPTH_Y[2]);
  expect(shadow.position.y).toBeLessThan(WHALE_DEPTH_Y[1]);
  expect(new Box3().setFromObject(occupied).min.y).toBeCloseTo(
    WHALE_DEPTH_Y[1],
  );
  expect(
    hull.parent?.children.filter(
      ({ name }) => name === "Cargo submerged occupancy",
    ),
  ).toEqual([occupied]);

  view.group.updateMatrixWorld(true);
  const outline = hazardPoints(hazard, tick);
  const vertices = shadow.geometry.getAttribute("position");
  const point = new Vector3();
  for (let index = 0; index < vertices.count; index++) {
    if (index % 3 === 0) continue;
    point.fromBufferAttribute(vertices, index).applyMatrix4(shadow.matrixWorld);
    expect(onOutline(outline, point)).toBe(true);
  }
});

test("W2 posts connect both net ends and the gap's bed reference stays below the deep route", () => {
  const view = course();
  const zone = whaleLevel.zones.find(({ id }) => id === "drift-net");
  const gap = whaleLevel.landmarks.find(({ id }) => id === "net-gap");
  const posts = view.group.getObjectByName("Net east end posts");
  const rocks = view.group.getObjectByName("Net gap outer bed rock");
  if (
    zone?.kind !== "hazard" ||
    !gap ||
    !(posts instanceof InstancedMesh) ||
    !(rocks instanceof InstancedMesh)
  )
    throw new Error("Missing W2 gap art");
  const east = Math.max(...zone.points.map(({ x }) => x));
  const anchors = zone.points.filter(({ x }) => x === east);
  const matrix = new Matrix4();
  const position = new Vector3();
  expect(posts.count).toBe(anchors.length);
  for (const [index, anchor] of anchors.entries()) {
    posts.getMatrixAt(index, matrix);
    expect(position.setFromMatrixPosition(matrix).toArray()).toEqual([
      anchor.x,
      0,
      anchor.z,
    ]);
  }
  const ends = new Box3().setFromObject(posts);
  expect(ends.max.y).toBeGreaterThan(0);
  expect(ends.min.y).toBeLessThan(WHALE_DEPTH_Y[2]);
  const bed = new Box3().setFromObject(rocks);
  expect(bed.max.y).toBeLessThan(WHALE_DEPTH_Y[2] - 1.8);
  expect(bed.min.x).toBeGreaterThan(gap.pos.x);
  expect(bed.max.x).toBeLessThan(whaleLevel.bounds.max.x);
});

test.each(["reef-current", "reef-current-east"])(
  "W3 %s cues stay within the simulation footprint",
  (id) => {
    const current = whaleLevel.zones.find((zone) => zone.id === id);
    const view = course();
    const art = view.group.getObjectByName(id);
    const drift = view.group.getObjectByName(`${id}-drift`);
    if (
      current?.kind !== "current" ||
      !art ||
      !(drift instanceof Mesh) ||
      !(drift.material instanceof ShaderMaterial)
    )
      throw new Error("Missing W3 current");
    const { entry, exit } = currentGuide(current);
    expect(contains(current.points, entry)).toBe(true);
    expect(contains(current.points, exit)).toBe(true);
    expect(flowProjection(current, exit)).toBeGreaterThan(
      flowProjection(current, entry),
    );
    const { flow, travel, density } = drift.material.uniforms;
    expect(flow?.value.toArray()).toEqual([
      current.direction.x,
      current.direction.z,
    ]);
    view.update(300, false, false, { reduced: false, low: false });
    expect(travel?.value).toBeGreaterThan(0);
    view.update(301, false, false, { reduced: true, low: true });
    expect(travel?.value).toBe(0);
    expect(density?.value).toBe(0);
    const arrows = art.children.slice(-3);
    for (const layer of [0, 1, 2]) {
      view.update(301, false, false, { reduced: true, low: true }, layer);
      expect(arrows.map(({ visible }) => visible)).toEqual(
        [0, 1, 2].map((index) => index === layer),
      );
    }
    for (const mesh of [...arrows, drift]) {
      if (!(mesh instanceof Mesh)) throw new Error("Missing current arrows");
      const vertices = mesh.geometry.getAttribute("position");
      expect(vertices.count).toBeGreaterThan(0);
      for (let i = 0; i < vertices.count; i++)
        expect(
          contains(current.points, {
            x: vertices.getX(i),
            z: vertices.getZ(i),
          }),
        ).toBe(true);
    }
  },
);

test("W3 wake eligibility follows each whale's actual lane, layer and heading", () => {
  const current = whaleLevel.zones.find(({ id }) => id === "reef-current");
  if (current?.kind !== "current") throw new Error("Missing W3 current");
  const { entry } = currentGuide(current);
  const pod = podAt(entry);
  const leader = podLeader(pod);
  const submerged = { ...leader.dive, layer: "shallow", depth: 1 } as const;
  const heading = Math.atan2(current.direction.x, current.direction.z);
  const riding = { ...leader, heading, dive: submerged };
  expect(canRideCurrent(current, riding)).toBe(true);
  expect(
    canRideCurrent(current, { ...riding, heading: heading + Math.PI }),
  ).toBe(false);
  expect(canRideCurrent(current, { ...riding, dive: leader.dive })).toBe(false);
  expect(
    canRideCurrent(current, {
      ...riding,
      dive: { ...submerged, forced: true },
    }),
  ).toBe(false);
  const tail = pod.actors.at(-1);
  if (!tail) throw new Error("Missing trailing whale");
  expect(canRideCurrent(current, { ...tail, heading, dive: submerged })).toBe(
    false,
  );
  expect(canRideCurrent(current, { ...riding, id: tail.id })).toBe(true);
});
