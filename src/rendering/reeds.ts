import { BufferGeometry, Float32BufferAttribute, Color } from "three";

export function reedClump(): BufferGeometry {
  const vertices: number[] = [];
  const colors: number[] = [];
  const stem = new Color("#64865f");
  const leaf = new Color("#9e9d61");
  const seed = new Color("#b1814b");

  function triangle(a: number[], b: number[], c: number[], tint: Color): void {
    vertices.push(...a, ...b, ...c);
    for (let corner = 0; corner < 3; corner++)
      colors.push(tint.r, tint.g, tint.b);
  }

  for (const [x, z, tip] of [
    [-0.35, -0.12, 0.42],
    [0.06, 0.12, 0.52],
    [0.36, -0.06, 0.3],
  ] as const) {
    const bottom = -0.5;
    const lean = x * 0.35;
    triangle(
      [x - 0.06, bottom, z],
      [x + 0.06, bottom, z],
      [x + lean, tip, z],
      stem,
    );
    triangle(
      [x, bottom, z - 0.07],
      [x, bottom, z + 0.07],
      [x + lean, tip, z],
      stem,
    );
    triangle(
      [x, -0.32, z],
      [x + 0.11, -0.09, z + 0.08],
      [x + 0.42, 0.13, z + 0.15],
      leaf,
    );
    triangle(
      [x, -0.23, z],
      [x - 0.12, 0.07, z - 0.11],
      [x - 0.44, 0.18, z - 0.21],
      leaf,
    );
    triangle(
      [x + lean - 0.09, tip - 0.17, z],
      [x + lean + 0.075, tip - 0.06, z],
      [x + lean, tip + 0.03, z],
      seed,
    );
    triangle(
      [x + lean, tip - 0.18, z - 0.07],
      [x + lean, tip - 0.09, z + 0.07],
      [x + lean, tip + 0.03, z],
      seed,
    );
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(vertices, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  return geometry;
}
