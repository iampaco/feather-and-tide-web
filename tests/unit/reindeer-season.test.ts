import { Box3, InstancedMesh, Matrix4, Mesh, Vector3 } from "three";
import { expect, test } from "vitest";
import { DEFAULT_SETTINGS } from "../../src/input/input";
import { contains } from "../../src/levels/geometry";
import { CameraDirector } from "../../src/rendering/camera";
import { ReindeerSeason } from "../../src/rendering/reindeer-season";
import { reindeerLevel } from "../fixtures/reindeer";

test("R0 snowbank geometry follows the blocked footprints and keeps tall spruces out of open ground", () => {
  const season = new ReindeerSeason(reindeerLevel);
  const { group } = season;
  const barriers = reindeerLevel.barriers.filter(({ id }) =>
    id.startsWith("snowbank-"),
  );
  const banks = group.children.filter(
    (node): node is Mesh =>
      node instanceof Mesh && node.name === "Winter snowbank",
  );
  expect(banks).toHaveLength(barriers.length);
  for (const [index, bank] of banks.entries()) {
    const outline = barriers[index]?.points;
    if (!outline) throw new Error("Missing snowbank outline");
    const bounds = new Box3().setFromObject(bank);
    expect(bounds.min.x).toBe(Math.min(...outline.map(({ x }) => x)));
    expect(bounds.max.x).toBe(Math.max(...outline.map(({ x }) => x)));
    expect(bounds.min.z).toBe(Math.min(...outline.map(({ z }) => z)));
    expect(bounds.max.z).toBe(Math.max(...outline.map(({ z }) => z)));
  }

  const matrix = new Matrix4();
  const origin = new Vector3();
  let instances = 0;
  let grove: { x: number; z: number } | undefined;
  for (const node of group.children) {
    if (
      !(node instanceof InstancedMesh) ||
      node.name !== "Winter spruce stands"
    )
      continue;
    for (let i = 0; i < node.count; i++) {
      node.getMatrixAt(i, matrix);
      const { x, z } = origin.setFromMatrixPosition(matrix);
      const { min, max } = reindeerLevel.bounds;
      if (x < min.x || x > max.x || z < min.z || z > max.z) {
        if (z < min.z && season.cameraHeight(x, z) > 20) grove ??= { x, z };
        continue;
      }
      expect(barriers.some(({ points }) => contains(points, { x, z }))).toBe(
        true,
      );
      instances++;
    }
  }
  expect(instances).toBeGreaterThan(0);
  expect(season.cameraHeight(0, reindeerLevel.spawn.z)).toBe(0);
  if (!grove) throw new Error("Missing tall winter canopy");
  const camera = new CameraDirector(42);
  const settings = { ...DEFAULT_SETTINGS, wideMouseOrbit: true };
  camera.drag(0, -300, settings, "mouse");
  camera.update(
    { x: grove.x, z: grove.z + 30 },
    1.6,
    2,
    1,
    settings,
    false,
    0,
    {
      height: (x, z) => season.cameraHeight(x, z),
      obstacles: [],
    },
  );
  expect(camera.viewAngles().requestedPitch).toBeCloseTo(20);
  expect(camera.viewAngles().pitch).toBeGreaterThan(20);
});

test("R4 keeps the grazing and resting ground flat and retains the washes in low quality", () => {
  const season = new ReindeerSeason(reindeerLevel);
  const outerRidges = season.group.getObjectByName("Tundra peripheral ridges");
  const farRidge = season.group.getObjectByName("Tundra far ridge");
  if (!(outerRidges instanceof Mesh) || !(farRidge instanceof Mesh))
    throw new Error("Missing backdrop layers");
  expect(new Box3().setFromObject(farRidge).min.z).toBeGreaterThan(
    reindeerLevel.bounds.max.z,
  );
  expect(farRidge.renderOrder).toBeLessThan(outerRidges.renderOrder);
  const position = outerRidges.geometry.getAttribute("position");
  const color = outerRidges.geometry.getAttribute("color");
  const { min, max } = reindeerLevel.bounds;
  let transparentFoot = 0;
  let visibleShoulder = 0;
  for (let i = 0; i < position.count; i++) {
    const x = position.getX(i);
    const z = position.getZ(i);
    if (x > min.x && x < max.x) {
      expect(z).toBeGreaterThan(max.z);
      if (z < max.z + 1) {
        expect(color.getW(i)).toBe(0);
        transparentFoot++;
      }
      if (position.getY(i) > 3 && color.getW(i) > 0.75) visibleShoulder++;
    }
  }
  expect(transparentFoot).toBeGreaterThan(0);
  expect(visibleShoulder).toBeGreaterThan(0);
  const thaw = season.group.children.filter(
    (node): node is Mesh =>
      node instanceof Mesh && node.name === "Spring snow and thaw wash",
  );
  expect(thaw.length).toBeGreaterThan(1);
  const snow = season.group.children.filter(
    (node): node is Mesh =>
      node instanceof Mesh && node.name === "Tundra residual snow",
  );
  expect(snow.length).toBeGreaterThan(1);
  for (const patch of snow)
    expect(new Box3().setFromObject(patch).max.y).toBeLessThan(0.025);
  const smallPlants = season.group.getObjectByName("Seasonal small plants");
  season.update(true);
  expect(smallPlants?.visible).toBe(false);
  expect([...thaw, ...snow].every(({ visible }) => visible)).toBe(true);
  season.update(false);
  expect(smallPlants?.visible).toBe(true);
});

test("R4 keeps the meltwater flush with the grazing plane and clear of the goal and trail", () => {
  const season = new ReindeerSeason(reindeerLevel);
  const water = season.group.getObjectByName("Tundra meltwater and shore");
  const goal = reindeerLevel.zones.find(({ kind }) => kind === "goal");
  if (!(water instanceof Mesh) || !goal)
    throw new Error("Missing spring scenery");
  const position = water.geometry.getAttribute("position");
  expect(position.count).toBeGreaterThan(0);
  const trail = reindeerLevel.trails.find(({ id }) => id === "trail-tundra");
  if (!trail) throw new Error("Missing tundra trail");
  for (let i = 0; i < position.count; i++) {
    const x = position.getX(i);
    const z = position.getZ(i);
    expect(position.getY(i)).toBeLessThan(0.025);
    expect(contains(goal.points, { x, z })).toBe(false);
    expect(x).toBeGreaterThan(Math.max(...trail.points.map((p) => p.x)) + 3);
  }
  season.update(true);
  expect(water.visible).toBe(true);
  expect(season.group.getObjectByName("Thaw bank sedges")?.visible).toBe(true);
});
