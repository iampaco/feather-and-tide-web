import { Matrix4, Vector3 } from "three";
import { expect, test } from "vitest";
import { WhaleGathering } from "../../src/rendering/whale-gathering";
import { podAt, whaleLevel } from "../fixtures/whale";

const goal = whaleLevel.zones.find(({ kind }) => kind === "goal");
const actors = podAt({ x: 80, z: 1551 }).actors.map((actor, index) => ({
  ...actor,
  heading: index * 0.39,
}));

test("W4 emphasizes whales that become ready on the actual landing tick", () => {
  const gathering = new WhaleGathering(actors.length, goal);
  const previous = actors
    .map((actor, index) => {
      if (index === 2) {
        return { ...actor, dive: { ...actor.dive, direction: "up" as const } };
      }
      if (index === 4) return { ...actor, pos: { ...actor.pos, z: 1502 } };
      return actor;
    })
    .reverse();
  gathering.update(actors, 0.46, { low: false, reduced: false }, previous);
  const ripple = gathering.mesh.geometry.getAttribute("ripple");
  expect(actors.map((_, index) => ripple.getZ(index))).toEqual([
    0, 0, 1, 0, 1, 0,
  ]);
  expect(ripple.getY(2)).toBeGreaterThan(0.85);
  expect(ripple.getY(4)).toBeGreaterThan(0.85);

  gathering.update(actors, 0.46, { low: false, reduced: false });
  expect(actors.every((_, index) => ripple.getZ(index) === 0)).toBe(true);
});

test("W4 waterline arcs follow authoritative whale headings and positions", () => {
  const gathering = new WhaleGathering(actors.length, goal);
  gathering.update(actors, 0.43, { low: false, reduced: false });
  const matrix = new Matrix4();
  const position = new Vector3();
  const heading = new Vector3();
  for (const [index, actor] of actors.entries()) {
    gathering.mesh.getMatrixAt(index, matrix);
    position.setFromMatrixPosition(matrix);
    heading.set(0, 0, 1).transformDirection(matrix);
    expect(position.x).toBeCloseTo(actor.pos.x, 4);
    expect(position.y).toBeCloseTo(0.145, 4);
    expect(position.z).toBeCloseTo(actor.pos.z, 4);
    expect(heading.x).toBeCloseTo(Math.sin(actor.heading), 5);
    expect(heading.z).toBeCloseTo(Math.cos(actor.heading), 5);
  }
});

test("W4 ripples stop with presentation progress and stay static in reduced motion", () => {
  const gathering = new WhaleGathering(actors.length, goal);
  const previous = actors.map((actor, index) =>
    index === 1 ? { ...actor, status: "rejoining" as const } : actor,
  );
  const ripple = gathering.mesh.geometry.getAttribute("ripple");
  gathering.update(actors, 0.32, { low: true, reduced: false }, previous);
  const moving = Array.from(ripple.array);
  expect(ripple.getY(1)).toBeGreaterThan(0);
  gathering.update(actors, 0.32, { low: true, reduced: false }, previous);
  expect(Array.from(ripple.array)).toEqual(moving);
  gathering.update(actors, 1, { low: true, reduced: false }, previous);
  expect(ripple.getY(1)).toBe(0);

  gathering.update(actors, 0, { low: true, reduced: true }, previous);
  const still = Array.from(ripple.array);
  expect(ripple.getY(1)).toBeGreaterThan(ripple.getY(0));
  expect(gathering.mesh.material.uniforms.detail?.value).toBe(0);
  gathering.update(actors, 1, { low: true, reduced: true }, previous);
  expect(Array.from(ripple.array)).toEqual(still);
});
