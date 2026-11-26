import {
  BufferGeometry,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  Object3D,
} from "three";

type GroundHeight = (x: number, z: number) => number;

const ledgeOutline = [
  [-0.97, -0.41],
  [-0.63, -0.85],
  [0.26, -0.94],
  [0.84, -0.56],
  [1.0, 0.19],
  [0.49, 0.78],
  [-0.27, 0.88],
  [-0.88, 0.44],
] as const;

// Long shore-parallel slabs under the wind trees and a much lower cluster
// to the west frame the channel the flock returns through.
const riverLedges = [
  [50, 421, 4.2, 1.38, 2.9, 0.18],
  [48.5, 426, 4.5, 3.0, 4.7, -0.58],
  [53.5, 429, 3.2, 1.8, 3.9, -0.4],
  [47.3, 433, 3.6, 1.36, 3.7, 0.12],
  [43.8, 438.5, 1.9, 0.9, 2.1, -0.44],
  [39.2, 443.5, 2.6, 0.62, 2.9, 0.25],
  [-68, 473, 4.1, 0.88, 3.5, 0.25],
  [-69, 480, 3.0, 0.65, 3.4, 0.12],
  [-72, 487, 3.3, 0.71, 2.2, -0.24],
] as const;

function ledgeGeometry(): BufferGeometry {
  const bands = [
    [1, -0.55, "#465950"],
    [0.99, 0.09, "#59685d"],
    [0.95, 0.32, "#748375"],
    [0.93, 0.41, "#8c947f"],
    [0.86, 0.57, "#687666"],
    [0.8, 0.72, "#7c8a78"],
    [0.54, 0.91, "#a1a58e"],
  ] as const;
  const vertices: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const sides = ledgeOutline.length;
  for (const [band, [scale, rise, tint]] of bands.entries()) {
    const color = new Color(tint);
    for (const [side, [x, z]] of ledgeOutline.entries()) {
      const shelf = rise * (0.91 + 0.11 * x - 0.1 * z);
      vertices.push(x * scale - rise * 0.22, shelf, z * scale + rise * 0.07);
      const variation = color.clone().multiplyScalar(0.95 + 0.09 * (1 + x));
      colors.push(variation.r, variation.g, variation.b);
      if (band > 0) {
        const a = (band - 1) * sides + side;
        const b = (band - 1) * sides + ((side + 1) % sides);
        indices.push(a, a + sides, b, b, a + sides, b + sides);
      }
    }
  }
  const top = vertices.length / 3;
  vertices.push(-0.25, 0.94, 0.09);
  const crown = new Color("#b0ac92");
  colors.push(crown.r, crown.g, crown.b);
  for (let side = 0; side < sides; side++) {
    const offset = (bands.length - 1) * sides;
    indices.push(offset + side, top, offset + ((side + 1) % sides));
  }
  const geometry = new BufferGeometry()
    .setIndex(indices)
    .setAttribute("position", new Float32BufferAttribute(vertices, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  return geometry;
}

function slateContact(
  height: GroundHeight,
  ledges: readonly (typeof riverLedges)[number][],
): Mesh {
  const ink = new Color("#3e574a");
  const vertices: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const sides = 16;
  for (const [x, z, width, , length, yaw] of ledges) {
    const center = vertices.length / 3;
    const originY = height(x, z);
    vertices.push(x, originY + 0.045, z);
    colors.push(ink.r, ink.g, ink.b, 0.28);
    for (let side = 0; side < sides; side++) {
      const angle = (side * Math.PI * 2) / sides;
      const dx = width * 1.3 * Math.cos(angle);
      const dz = length * 1.26 * Math.sin(angle);
      const px = x + dx * Math.cos(yaw) + dz * Math.sin(yaw);
      const pz = z - dx * Math.sin(yaw) + dz * Math.cos(yaw);
      vertices.push(px, height(px, pz) + 0.045, pz);
      colors.push(ink.r, ink.g, ink.b, 0);
      indices.push(
        center,
        center + 1 + side,
        center + 1 + ((side + 1) % sides),
      );
    }
  }
  const geometry = new BufferGeometry()
    .setIndex(indices)
    .setAttribute("position", new Float32BufferAttribute(vertices, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 4));
  return new Mesh(
    geometry,
    new MeshBasicMaterial({
      side: DoubleSide,
      vertexColors: true,
      transparent: true,
      depthWrite: false,
    }),
  );
}

export function buildCrosswindBanks(height: GroundHeight, low: boolean): Group {
  const group = new Group();
  group.name = "S3-crosswind-bank-landmarks";
  const ledges = riverLedges.filter(
    ([x, z], index) => height(x, z) > 0.06 && (!low || index % 3 !== 2),
  );
  const ridge = new InstancedMesh(
    ledgeGeometry(),
    new MeshLambertMaterial({ vertexColors: true }),
    ledges.length,
  );
  ridge.name = "layered-slate-shore";
  const transform = new Object3D();
  for (const [index, [x, z, width, rise, length, yaw]] of ledges.entries()) {
    transform.position.set(x, height(x, z) - 0.16, z);
    transform.rotation.y = yaw;
    transform.scale.set(width, rise, length);
    transform.updateMatrix();
    ridge.setMatrixAt(index, transform.matrix);
  }
  ridge.computeBoundingSphere();
  group.add(ridge, slateContact(height, ledges));
  return group;
}
