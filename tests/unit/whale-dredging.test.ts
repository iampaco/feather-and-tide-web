import { Box3, Mesh, ShaderMaterial } from "three";
import { expect, test } from "vitest";
import { contains } from "../../src/levels/geometry";
import {
  dredgingPassage,
  dredgingTurbidity,
} from "../../src/levels/whale-dredging";
import { WhaleDredging } from "../../src/rendering/whale-dredging";
import { whaleLevel } from "../fixtures/whale";

test("W3 alternate route and regroup lie in clear water outside the authored plume", () => {
  const passage = dredgingPassage(whaleLevel);
  if (!passage) throw new Error("Missing dredging passage");
  for (const { pos } of passage.clear)
    expect(dredgingTurbidity(passage, pos)).toBe(0);
  expect(dredgingTurbidity(passage, { x: 68, z: 1210 })).toBe(1);
  expect(dredgingTurbidity(passage, { x: 39, z: 1213 })).toBeGreaterThan(0);
  expect(dredgingTurbidity(passage, { x: 39, z: 1213 })).toBeLessThan(0.2);
  expect(contains(passage.rest.points, passage.regroup.pos)).toBe(true);
  expect(dredgingTurbidity(passage, passage.regroup.pos)).toBe(0);
});

test("W3 dredger stays outside play and both routes are marked in reduced motion", () => {
  const art = new WhaleDredging(whaleLevel);
  const sediment = art.group.getObjectByName("Dredging suspended sediment");
  const pontoon = art.group.getObjectByName("Harbor dredging pontoon");
  const surface = art.group.getObjectByName("Dredging surface channel");
  const edge = art.group.getObjectByName("Dredging clear-edge surface guide");
  const shallow = art.group.getObjectByName(
    "Dredging clear-edge shallow guide",
  );
  if (
    !(sediment instanceof Mesh) ||
    !(sediment.material instanceof ShaderMaterial) ||
    !pontoon ||
    !surface ||
    !edge ||
    !shallow
  )
    throw new Error("Missing dredging art");

  expect(new Box3().setFromObject(pontoon).min.x).toBeGreaterThan(
    whaleLevel.bounds.max.x,
  );
  art.update(90, { low: false, reduced: false }, 0);
  expect(sediment.material.uniforms.travel?.value).toBeGreaterThan(0);
  expect(surface.visible && edge.visible && !shallow.visible).toBe(true);
  art.update(180, { low: true, reduced: true }, 1);
  expect(sediment.material.uniforms.travel?.value).toBe(0);
  expect(
    sediment.visible && surface.visible && !edge.visible && shallow.visible,
  ).toBe(true);
});
