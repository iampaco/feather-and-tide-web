import { expect, test } from "vitest";
import { whaleSeabed } from "../../src/rendering/whale-seabed";
import { whaleLevel } from "../fixtures/whale";

test("whale seabed tiles meet exactly, clear the swim layers and drop toward offshore", () => {
  const offshore = whaleLevel.landmarks.find(
    ({ id }) => id === "second-checkpoint",
  );
  if (!offshore) throw new Error("Missing offshore approach");
  const tiles = whaleSeabed(whaleLevel, offshore.pos.z);
  let previous: number[][] | undefined;
  let bayHeight = -Infinity;
  let basinHeight = -Infinity;
  let offshoreHeight = -Infinity;
  for (const tile of tiles) {
    const vertices = tile.getAttribute("position");
    const row = tile.parameters.widthSegments + 1;
    const edge: number[][] = [];
    for (let index = 0; index < vertices.count; index++) {
      const x = vertices.getX(index);
      const y = vertices.getY(index);
      const z = vertices.getZ(index);
      expect(y).toBeLessThanOrEqual(-11);
      if (index < row && previous) expect([x, y, z]).toEqual(previous[index]);
      if (index >= vertices.count - row) edge.push([x, y, z]);
      if (Math.abs(x - whaleLevel.spawn.x) < 1) {
        if (z >= 0 && z <= 110) bayHeight = Math.max(bayHeight, y);
        if (z >= 420 && z <= 470) basinHeight = Math.max(basinHeight, y);
        if (z >= 1518 && z <= 1600)
          offshoreHeight = Math.max(offshoreHeight, y);
      }
    }
    previous = edge;
  }
  expect(bayHeight).toBe(-11);
  expect(basinHeight).toBeLessThan(bayHeight - 0.5);
  expect(offshoreHeight).toBeLessThan(basinHeight - 3);
});
