import { Box3, BufferGeometry, Raycaster, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import { contains, sweptCircle } from "../../src/levels/geometry";
import { buildMigrationTerrain } from "../../src/rendering/terrain";
import { migration } from "../fixtures/flight";

describe("migration landscape", () => {
  const standard = buildMigrationTerrain(migration, false);

  it("covers the orbit outside every playable edge", () => {
    const bounds = new Box3().setFromObject(standard.group, true);
    expect(bounds.min.x).toBeLessThanOrEqual(migration.bounds.min.x - 140);
    expect(bounds.max.x).toBeGreaterThanOrEqual(migration.bounds.max.x + 140);
    expect(bounds.min.z).toBeLessThanOrEqual(migration.bounds.min.z - 140);
    expect(bounds.max.z).toBeGreaterThanOrEqual(migration.bounds.max.z + 140);
  });

  it("separates the reed headland with a side channel and keeps the waterway open", () => {
    expect(standard.height(24, 57)).toBeGreaterThan(0.85);
    expect(standard.height(38, 61)).toBeLessThan(-0.3);
    expect(standard.height(51, 61)).toBeGreaterThan(0.85);
    for (const z of [0, 12, 24, 36, 48, 60, 72, 84, 96]) {
      for (const x of [-5, 0, 5]) {
        expect(standard.height(x, z)).toBeLessThan(0.08);
      }
    }
  });

  it("keeps the watershed volume inside the authored hazard", () => {
    const hazard = migration.zones.find(({ id }) => id === "ridge-wall");
    const ridge = standard.group.getObjectByName("watershed");
    if (!hazard || !ridge || !("geometry" in ridge))
      throw new Error("Migration is missing its watershed");
    const geometry = new Box3().setFromObject(ridge, true);
    expect(geometry.min.z).toBe(Math.min(...hazard.points.map(({ z }) => z)));
    expect(geometry.max.z).toBe(Math.max(...hazard.points.map(({ z }) => z)));
    expect(standard.height(-2, 263)).toBeLessThan(0.05);
    expect(standard.height(7, 310)).toBeGreaterThan(3);

    if (!(ridge.geometry instanceof BufferGeometry))
      throw new Error("Watershed is missing mesh geometry");
    const position = ridge.geometry.getAttribute("position");
    for (let i = 0; i < position.count; i++) {
      const point = { x: position.getX(i), z: position.getZ(i) };
      // The outer submerged seam is stored with Float32 precision.
      expect(
        position.getY(i) < 0
          ? sweptCircle(hazard.points, point, point, 0.0001)
          : contains(hazard.points, point),
      ).toBe(true);
    }
    const index = ridge.geometry.index;
    if (!index) throw new Error("Watershed is missing triangle indices");
    for (let i = 0; i < index.count; i += 3) {
      const a = index.getX(i);
      const b = index.getX(i + 1);
      const c = index.getX(i + 2);
      expect(
        contains(hazard.points, {
          x: (position.getX(a) + position.getX(b) + position.getX(c)) / 3,
          z: (position.getZ(a) + position.getZ(b) + position.getZ(c)) / 3,
        }),
      ).toBe(true);
    }
  });

  it("samples the drawn terrain for contacts and keeps both routes and the basin open", () => {
    const low = buildMigrationTerrain(migration, true);
    const samplePoints = [
      { x: -18, z: 26 }, // first reed island
      { x: -43, z: 63 }, // opening bank shoulder
      { x: -150, z: 302 }, // exterior mountain shoulder
      { x: 126, z: 309 }, // low exterior lake bank
      { x: -27, z: 302 }, // short mountain pass
      { x: 59, z: 329 }, // long lake
      { x: -55, z: 570 }, // wetland bend
      { x: -12, z: 573 }, // turbine pedestal
      { x: -11, z: 822 }, // landing basin
      { x: 32, z: 830 }, // basin bank
      { x: 7, z: 310 }, // watershed crest
    ];
    const ray = new Raycaster(new Vector3(), new Vector3(0, -1, 0));
    standard.group.updateMatrixWorld(true);
    const surfaces = standard.group.children.filter(
      ({ name }) =>
        name === "riverbank" || name === "watershed" || name === "river",
    );
    for (const { x, z } of samplePoints) {
      const height = standard.height(x, z);
      ray.ray.origin.set(x, 80, z);
      expect(ray.intersectObjects(surfaces)[0]?.point.y).toBeCloseTo(
        Math.max(height, 0),
        4,
      );
      expect(low.height(x, z)).toBe(height);
    }
    expect(standard.height(-27, 302)).toBeLessThan(0);
    expect(standard.height(59, 329)).toBeLessThan(0);
    expect(standard.height(-43, 63)).toBeGreaterThan(2);
    expect(standard.height(-150, 302)).toBeGreaterThan(
      standard.height(126, 309) + 15,
    );
    expect(standard.height(-11, 822)).toBeLessThan(0);
    expect(standard.height(22, 837)).toBeLessThan(0);
    expect(standard.height(23, 870)).toBeGreaterThan(0);
    expect(standard.height(45, 850)).toBeLessThan(0);
    expect(standard.height(-12, 573)).toBeGreaterThan(0);
  });

  it("frames the pass above the water and keeps a shallow approach to the lake supply", () => {
    expect(standard.height(-74, 277)).toBeGreaterThan(4);
    expect(standard.height(-30, 277)).toBeLessThan(0);

    const lake = standard.height(59, 329);
    const shoal = standard.height(86, 329);
    expect(shoal).toBeLessThan(0);
    expect(shoal).toBeGreaterThan(lake + 2);
  });
});
