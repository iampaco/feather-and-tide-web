import { describe, expect, it } from "vitest";
import { InstancedMesh, Matrix4, Vector3 } from "three";
import { buildMigrationDressing } from "../../src/rendering/migrationDressing";
import { migration } from "../fixtures/flight";

function instancePositions(
  land: ReturnType<typeof buildMigrationDressing>,
  name: string,
): Vector3[] {
  const mesh = land.group.getObjectByName(name);
  if (!(mesh instanceof InstancedMesh)) throw new Error(`Missing ${name}`);
  const matrix = new Matrix4();
  return Array.from({ length: mesh.count }, (_, i) => {
    mesh.getMatrixAt(i, matrix);
    return new Vector3().setFromMatrixPosition(matrix);
  });
}

describe("migration ground dressing", () => {
  it("keeps roots on the supplied bed elevation and skips deep water", () => {
    const terrain = (x: number, z: number) =>
      x < 0 ? -0.028 * x + z * 0.001 : -2;
    const land = buildMigrationDressing(migration, terrain, false);
    const reeds = instancePositions(land, "S0-reed-beds");
    expect(reeds.length).toBeGreaterThan(0);
    for (const root of reeds) {
      expect(root.x).toBeLessThan(0);
      expect(root.y).toBeCloseTo(terrain(root.x, root.z) - 0.037, 5);
    }
    expect(land.trees.length).toBeGreaterThan(0);
    for (const tree of land.trees) {
      const { x, y, z } = tree.position;
      expect(x).toBeLessThan(0);
      expect(y).toBeCloseTo(terrain(x, z) - 0.045);
    }
  });

  it("keeps major landmarks and a stable subset of reed positions in low quality", () => {
    const terrain = () => 0.5;
    const standard = buildMigrationDressing(migration, terrain, false);
    const low = buildMigrationDressing(migration, terrain, true);
    expect(low.trees.map(({ position }) => position.toArray())).toEqual(
      standard.trees.map(({ position }) => position.toArray()),
    );
    const fullBeds = instancePositions(standard, "S6-reed-beds").map((root) =>
      root.toArray(),
    );
    const lowBeds = instancePositions(low, "S6-reed-beds").map((root) =>
      root.toArray(),
    );
    expect(lowBeds.length).toBeGreaterThan(0);
    expect(lowBeds.length).toBeLessThan(fullBeds.length);
    expect(fullBeds).toEqual(expect.arrayContaining(lowBeds));
  });

  it("draws wind strokes only where the corresponding reach has wind", () => {
    const calm = {
      ...migration,
      segments: migration.segments.map((reach) =>
        reach.id === "S1" ? { ...reach, wind: { x: 0, z: 0 } } : reach,
      ),
    };
    const { wind } = buildMigrationDressing(calm, () => -0.4, false);
    expect(wind.getObjectByName("S1-wind-ribbons")).toBeUndefined();
    expect(wind.getObjectByName("S3-wind-ribbons")).toBeDefined();
  });

  it("keeps grounded slate landmarks on both banks and the rescue channel open in both quality settings", () => {
    const terrain = (x: number, z: number) =>
      Math.abs(x) > 42 ? 0.22 + z * 0.001 : -2;
    const standard = buildMigrationDressing(migration, terrain, false);
    const low = buildMigrationDressing(migration, terrain, true);
    const full = instancePositions(standard, "layered-slate-shore");
    const reduced = instancePositions(low, "layered-slate-shore");
    expect(reduced.some(({ x }) => x < 0)).toBe(true);
    expect(reduced.some(({ x }) => x > 0)).toBe(true);
    expect(reduced.length).toBeLessThan(full.length);
    expect(full).toEqual(expect.arrayContaining(reduced));
    for (const { x, y, z } of full) {
      expect(Math.abs(x)).toBeGreaterThan(42);
      expect(y).toBeCloseTo(terrain(x, z) - 0.16);
    }
  });

  it("uses the water surface for floating marks and keeps the landing water free of a pole", () => {
    const water = buildMigrationDressing(migration, () => -1.25, false);
    const land = buildMigrationDressing(migration, () => 0.45, false);
    expect(water.group.getObjectByName("outer-mark-waymark")?.position.y).toBe(
      0,
    );
    expect(
      land.group.getObjectByName("outer-mark-waymark")?.position.y,
    ).toBeCloseTo(0.39);
    expect(water.group.getObjectByName("goal-mark-waymark")).toBeUndefined();
  });
});
