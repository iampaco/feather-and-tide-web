import { Mesh, MeshBasicMaterial } from "three";
import { describe, expect, it } from "vitest";
import { contains } from "../../src/levels/geometry";
import { buildLandscape } from "../../src/rendering/landscape";
import { migration } from "../fixtures/flight";

function strokes(
  group: ReturnType<typeof buildLandscape>["group"],
  name: string,
): Mesh {
  const stroke = group.getObjectByName(name);
  if (!(stroke instanceof Mesh)) throw new Error(`Missing ${name}`);
  return stroke;
}

describe("goose return wind strokes", () => {
  it.each([false, true])(
    "follows the same gust and lee geometry in low=%s",
    (low) => {
      const gustZone = migration.zones.find(({ id }) => id === "return-gust");
      const leeZone = migration.zones.find(({ id }) => id === "return-lee");
      if (gustZone?.kind !== "interference" || !gustZone.gust || !leeZone)
        throw new Error("Missing return wind zones");

      const landscape = buildLandscape(migration, low);
      const weak = strokes(landscape.group, "return-gust-weak");
      const crest = strokes(landscape.group, "return-gust-crest");
      const lee = strokes(landscape.group, "return-lee-strokes");
      expect(landscape.group.getObjectByName("return-gust")).toBeUndefined();
      expect(landscape.group.getObjectByName("return-lee")).toBeUndefined();
      for (const [stroke, zone] of [
        [weak, gustZone],
        [crest, gustZone],
        [lee, leeZone],
      ] as const) {
        const points = stroke.geometry.getAttribute("position");
        expect(points.count, stroke.name).toBeGreaterThanOrEqual(16);
        for (let i = 0; i < points.count; i++) {
          const point = { x: points.getX(i), z: points.getZ(i) };
          expect(contains(zone.points, point)).toBe(true);
          expect(landscape.height?.(point.x, point.z)).toBeLessThan(
            points.getY(i),
          );
        }
      }

      const { periodTicks, phaseTicks } = gustZone.gust;
      const calmTick = periodTicks - phaseTicks;
      const peakTick = calmTick + periodTicks / 2;
      if (
        !landscape.setGustTick ||
        !(weak.material instanceof MeshBasicMaterial) ||
        !(crest.material instanceof MeshBasicMaterial)
      )
        throw new Error("Missing gust phase controls");

      landscape.setGustTick(calmTick);
      expect(crest.visible).toBe(false);
      const weakOpacity = weak.material.opacity;
      landscape.setGustTick(peakTick);
      expect(crest.visible).toBe(true);
      expect(crest.material.opacity).toBeGreaterThan(weakOpacity);
      expect(weak.material.opacity).toBeLessThan(weakOpacity);
      expect(lee.visible).toBe(true);
      landscape.setGustTick(calmTick + periodTicks);
      expect(weak.material.opacity).toBeCloseTo(weakOpacity);
      expect(crest.visible).toBe(false);
    },
  );
});
