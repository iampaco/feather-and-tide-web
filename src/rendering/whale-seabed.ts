import { MathUtils, PlaneGeometry } from "three";
import type { WhaleLevel } from "../levels/schema";

const HORIZON_MARGIN = 550;
const TILE_LENGTH = 148;
const ACROSS = 26;
const ALONG = 10;

// Sample one height field in world space so adjacent tiles share edge vertices
// and can be culled separately without opening gaps.
export function whaleSeabed(
  level: WhaleLevel,
  offshoreStart: number,
): PlaneGeometry[] {
  const { min, max } = level.bounds;
  const centerX = (min.x + max.x) * 0.5;
  const width = max.x - min.x + HORIZON_MARGIN * 2;
  const start = min.z - HORIZON_MARGIN;
  const length = max.z + HORIZON_MARGIN - start;
  const tiles = Math.ceil(length / TILE_LENGTH);
  const tileLength = length / tiles;
  const courseStart =
    level.segments.find(({ id }) => id === "W1")?.start ?? max.z;
  const quiet = level.zones.find(({ id }) => id === "quiet-rest");
  const quietEast = quiet ? Math.max(...quiet.points.map(({ x }) => x)) : min.x;
  const quietStart = quiet
    ? Math.min(...quiet.points.map(({ z }) => z))
    : max.z;
  const quietEnd = quiet ? Math.max(...quiet.points.map(({ z }) => z)) : max.z;
  const quietGate = level.triggers.find(
    (trigger) => trigger.kind === "route" && trigger.route === "quiet",
  );
  const quietApproach =
    quietGate?.kind === "route"
      ? (quietGate.crossingZ ?? quietStart)
      : quietStart;
  const floor: PlaneGeometry[] = [];
  for (let i = 0; i < tiles; i++) {
    const tile = new PlaneGeometry(width, tileLength, ACROSS, ALONG).rotateX(
      -Math.PI / 2,
    );
    const vertices = tile.getAttribute("position");
    for (let row = 0; row <= ALONG; row++) {
      const z = Math.fround(start + ((i * ALONG + row) / ALONG) * tileLength);
      const inlet = MathUtils.smoothstep(
        z,
        courseStart + 70,
        courseStart + 135,
      );
      const quietReach =
        MathUtils.smoothstep(z, quietApproach - 100, quietApproach - 54) *
        (1 - MathUtils.smoothstep(z, quietEnd + 22, quietEnd + 63));
      const drift = 19 * Math.sin(z * 0.012 + 1.3);
      const offshore = MathUtils.smoothstep(
        z,
        offshoreStart - 20,
        offshoreStart + 170,
      );
      for (let column = 0; column <= ACROSS; column++) {
        const vertex = row * (ACROSS + 1) + column;
        const x = centerX + (column / ACROSS - 0.5) * width;
        const cut =
          1 -
          quietReach *
            (1 - MathUtils.smoothstep(x, quietEast + 34, quietEast + 90));
        const channel = x - centerX + drift;
        const relief =
          Math.exp(-((channel / 65) ** 2)) *
          (0.75 + 0.25 * Math.sin(z * 0.026));
        const y =
          -11 -
          inlet * cut * (0.32 + 1.6 * relief) -
          offshore * (8 + 1.1 * Math.cos(x * 0.031));
        vertices.setXYZ(vertex, x, y, z);
      }
    }
    floor.push(tile);
  }
  return floor;
}
