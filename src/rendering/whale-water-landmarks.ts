import { Group, Object3D } from "three";
import type { Vec2 } from "../core/math";
import type { WhaleLevel } from "../levels/schema";
import { reefGrass, reefRockInstances } from "./whale-coast";

export function whaleWaterLandmarks(
  level: WhaleLevel,
  depth: { value: number },
): Group {
  const group = new Group();
  group.name = "Tidal shelves and offshore reefs";
  const mark = (id: string) =>
    level.landmarks.find((landmark) => landmark.id === id)?.pos;
  const patches: { at: Vec2; spread: number; side: number }[] = [];
  for (const [id, x, z, spread] of [
    ["ship-clear", -25, 30, 16],
    ["first-checkpoint", 33, 5, 21],
    ["net-preview-wide", -25, 24, 18],
    ["net-preview-short", -53, 36, 23],
    ["net-detour", 26, -8, 20],
    ["net-wide-entry", 7, -33, 16],
    ["kelp-center", -31, 3, 17],
    ["kelp-center", 27, 24, 17],
    ["surface-here", -24, 4, 14],
    ["offshore-marker", -28, 11, 19],
    ["offshore-marker", 26, 17, 23],
  ] as const) {
    const at = mark(id);
    if (at)
      patches.push({
        at: { x: at.x + x, z: at.z + z },
        spread,
        side: Math.sign(x),
      });
  }
  const rocks = reefRockInstances(patches.length * 5, true, depth);
  const grass = reefGrass(patches.length * 8);
  const transform = new Object3D();
  for (const [patch, { at, spread, side }] of patches.entries()) {
    for (let i = 0; i < 5; i++) {
      const angle = patch * 0.81 + i * 2.4;
      const radius = spread * (0.22 + i * 0.12);
      transform.position.set(
        at.x + Math.cos(angle) * radius,
        -10.7,
        at.z + Math.sin(angle) * radius,
      );
      transform.scale.set(
        1.8 + (i % 3) * 0.9,
        1.6 + (i % 4) * 0.38,
        2.2 + (i % 3) * 1.25,
      );
      transform.rotation.y = angle + side * 0.8;
      transform.updateMatrix();
      rocks.setMatrixAt(patch * 5 + i, transform.matrix);
    }
    for (let i = 0; i < 8; i++) {
      const angle = i * 2.4 + patch;
      const radius = spread * (0.23 + i * 0.084);
      transform.position.set(
        at.x + Math.sin(angle) * radius,
        -10.1,
        at.z + Math.cos(angle) * radius,
      );
      transform.scale.set(1.3 + i * 0.16, 2.1 + (i % 5) * 0.31, 1.3 + i * 0.16);
      transform.rotation.y = angle;
      transform.updateMatrix();
      grass.setMatrixAt(patch * 8 + i, transform.matrix);
    }
  }
  if (patches.length) group.add(rocks, grass);
  if (mark("offshore-marker")) {
    // These exposed ridges stay beyond the navigable bounds at every height.
    const islets = reefRockInstances(7, true, depth);
    const edge = level.bounds.max;
    for (let i = 0; i < 7; i++) {
      const size = 5.2 + (i % 3) * 2.6;
      transform.position.set(
        edge.x + size * 1.5 + (i % 2) * 8,
        -1.4,
        edge.z - 101 + i * 18.1,
      );
      transform.scale.set(size, 3.3 + (i % 3) * 1.9, size * 1.38);
      transform.rotation.y = i * 0.47;
      transform.updateMatrix();
      islets.setMatrixAt(i, transform.matrix);
    }
    group.add(islets);
  }
  return group;
}
