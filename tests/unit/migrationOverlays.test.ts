import { InstancedMesh, Matrix4, Mesh, ShaderMaterial, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import { contains, sweptCircle } from "../../src/levels/geometry";
import { buildMigrationOverlays } from "../../src/rendering/migrationOverlays";
import { migration } from "../fixtures/flight";

describe("migration overlays", () => {
  it("draws a closed terrain-conforming stroke centered on each authoritative hazard edge", () => {
    const height = (x: number, z: number): number =>
      0.4 + z * 0.002 - x * 0.003;
    const { group } = buildMigrationOverlays(migration, height);
    for (const zone of migration.zones.filter(
      ({ kind }) => kind === "hazard",
    )) {
      const outline = group
        .getObjectByName(zone.id)
        ?.getObjectByName("outline");
      if (!(outline instanceof Mesh))
        throw new Error(`Missing ${zone.id} outline`);
      const { geometry } = outline;
      const positions = geometry.getAttribute("position");
      const centers = [];
      for (let i = 0; i < positions.count; i += 2) {
        const x = (positions.getX(i) + positions.getX(i + 1)) / 2;
        const z = (positions.getZ(i) + positions.getZ(i + 1)) / 2;
        centers.push({ x, z });
        expect(sweptCircle(zone.points, { x, z }, { x, z }, 0.0001)).toBe(true);
        expect(positions.getY(i)).toBeCloseTo(height(x, z) + 0.16, 4);
      }
      for (const point of zone.points) {
        expect(
          centers.some(
            ({ x, z }) => Math.hypot(x - point.x, z - point.z) < 0.0001,
          ),
        ).toBe(true);
      }
      const indices = geometry.getIndex();
      expect(indices?.array.slice(-6)).toEqual(
        new Uint16Array([
          positions.count - 2,
          positions.count - 1,
          0,
          positions.count - 1,
          1,
          0,
        ]),
      );
    }
  });

  it("clears scenic goal paint during landing and restores it on a new approach", () => {
    const { group, setLanding } = buildMigrationOverlays(migration, () => 0);
    const goal = group.getObjectByName("goal");
    if (!(goal instanceof Mesh) || !(goal.material instanceof ShaderMaterial))
      throw new Error("Missing landing water marker");
    const visibility = goal.material.uniforms.visibility;
    if (!visibility) throw new Error("Missing goal marker visibility");
    setLanding(0.4);
    expect(visibility.value).toBe(0);
    setLanding(0);
    expect(visibility.value).toBe(1);
  });

  it.each([false, true])(
    "keeps gallery roofs and railings inside the glass footprint with low quality %s",
    (low) => {
      const { group } = buildMigrationOverlays(migration, () => 0.5, low);
      for (const zone of migration.zones) {
        if (zone.kind !== "hazard" || zone.appearance !== "glass") continue;
        const structure = group
          .getObjectByName(zone.id)
          ?.getObjectByName("gallery-structure");
        if (!(structure instanceof InstancedMesh))
          throw new Error(`Missing ${zone.id} structure`);
        const matrix = new Matrix4();
        const point = new Vector3();
        const vertices = structure.geometry.getAttribute("position");
        for (let part = 0; part < structure.count; part++) {
          structure.getMatrixAt(part, matrix);
          for (let i = 0; i < vertices.count; i++) {
            point.fromBufferAttribute(vertices, i).applyMatrix4(matrix);
            const tolerance = 0.0001;
            // Box instance matrices store coordinates as float32 at world scale.
            const offsets = [
              [0, 0],
              [tolerance, 0],
              [-tolerance, 0],
              [0, tolerance],
              [0, -tolerance],
            ] as const;
            const inside = offsets.some(([dx, dz]) =>
              contains(zone.points, { x: point.x + dx, z: point.z + dz }),
            );
            expect(
              inside,
              `${zone.id} part ${part} at ${point.x}, ${point.z}`,
            ).toBe(true);
          }
        }
      }
    },
  );
});
