import { Box3, InstancedMesh, Matrix4, Vector3 } from "three";
import { expect, test } from "vitest";
import { reindeerFencePassages } from "../../src/levels/reindeer-ground";
import { ReindeerRoutes } from "../../src/rendering/reindeer-routes";
import { reindeerLevel } from "../fixtures/reindeer";

test("R2 gate shoulders have distinct shapes at both ends of each first-row opening", () => {
  const { group } = new ReindeerRoutes(reindeerLevel);
  const rails = group.getObjectByName("R2 rails and gateposts");
  if (!(rails instanceof InstancedMesh)) throw new Error("Missing fence mesh");

  const unitBox = new Box3(
    new Vector3(-0.5, -0.5, -0.5),
    new Vector3(0.5, 0.5, 0.5),
  );
  const transform = new Matrix4();
  const pieces = Array.from({ length: rails.count }, (_, index) => {
    rails.getMatrixAt(index, transform);
    return unitBox.clone().applyMatrix4(transform);
  });
  const passages = reindeerFencePassages(reindeerLevel);
  const firstRow = passages
    .filter(({ near }) => near === passages[0]?.near)
    .sort((a, b) => a.right - a.left - (b.right - b.left));
  expect(firstRow).toHaveLength(3);

  for (const side of ["left", "right"] as const) {
    const gateShapes = firstRow.map((gap) => {
      const edge = gap[side];
      const shoulder = pieces
        .filter((piece) => {
          const face = side === "left" ? piece.max.x : piece.min.x;
          return (
            Math.abs(face - edge) < 0.001 &&
            piece.min.z >= gap.near &&
            piece.max.z <= gap.far
          );
        })
        .sort((a, b) => b.max.y - a.max.y)[0];
      if (!shoulder)
        throw new Error("Missing gate shoulder at the collision edge");
      return { height: shoulder.max.y, depth: shoulder.max.z - shoulder.min.z };
    });
    const [narrow, short, wide] = gateShapes;
    if (!narrow || !short || !wide) throw new Error("Missing gate profiles");

    expect(short.height - narrow.height).toBeGreaterThan(0.3);
    expect(wide.height - short.height).toBeGreaterThan(0.4);
    expect(short.depth - narrow.depth).toBeGreaterThan(0.25);
    expect(wide.depth - short.depth).toBeGreaterThan(0.25);
  }
});
