import {
  BufferGeometry,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  Mesh,
  ShaderMaterial,
} from "three";

export function buildMigrationMist(low: boolean): Mesh {
  const veils = [
    {
      x: -28,
      z: 16,
      y: 1.55,
      width: 32,
      depth: 18,
      tilt: -0.29,
      alpha: 0.27,
      tint: "#e8dfc5",
    },
    {
      x: 32,
      z: 25,
      y: 1.24,
      width: 34,
      depth: 21,
      tilt: 0.24,
      alpha: 0.22,
      tint: "#d9dfcf",
    },
    {
      x: 32,
      z: 65,
      y: 1.82,
      width: 43,
      depth: 17,
      tilt: 0.16,
      alpha: 0.27,
      tint: "#e9dfc2",
    },
    {
      x: -29,
      z: 75,
      y: 1.64,
      width: 39,
      depth: 19,
      tilt: -0.34,
      alpha: 0.25,
      tint: "#f0e3c2",
    },
    {
      x: -23,
      z: 101,
      y: 1.52,
      width: 43,
      depth: 15,
      tilt: 0.22,
      alpha: 0.24,
      tint: "#ede0c4",
    },
    {
      x: -69,
      z: 286,
      y: 2.1,
      width: 23,
      depth: 39,
      tilt: -0.38,
      alpha: 0.2,
      tint: "#d7d6df",
    },
    {
      x: -74,
      z: 342,
      y: 2.4,
      width: 26,
      depth: 34,
      tilt: -0.28,
      alpha: 0.18,
      tint: "#cbd6d5",
    },
    {
      x: 37,
      z: 421,
      y: 1.3,
      width: 33,
      depth: 16,
      tilt: -0.2,
      alpha: 0.16,
      tint: "#dfd9c2",
    },
    {
      x: -38,
      z: 797,
      y: 1.4,
      width: 39,
      depth: 17,
      tilt: 0.1,
      alpha: 0.21,
      tint: "#f2d6a4",
    },
    {
      x: 36,
      z: 842,
      y: 1.6,
      width: 43,
      depth: 15,
      tilt: -0.14,
      alpha: 0.25,
      tint: "#f4deac",
    },
    {
      x: -21,
      z: 883,
      y: 2.4,
      width: 61,
      depth: 26,
      tilt: 0.16,
      alpha: 0.23,
      tint: "#f4e2b6",
    },
  ];
  const positions: number[] = [];
  const uvs: number[] = [];
  const colorOpacity: number[] = [];
  const indices: number[] = [];
  // Keep the broad washes in low quality and skip the overlapping wisps.
  for (const [index, veil] of veils.entries()) {
    if (low && index % 2 === 1) continue;
    const co = Math.cos(veil.tilt);
    const si = Math.sin(veil.tilt);
    const base = positions.length / 3;
    const color = new Color(veil.tint);
    for (const [u, v] of [
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
    ] as const) {
      const dx = (u - 0.5) * veil.width;
      const dz = (v - 0.5) * veil.depth;
      positions.push(
        veil.x + co * dx - si * dz,
        veil.y,
        veil.z + si * dx + co * dz,
      );
      uvs.push(u, v);
      colorOpacity.push(color.r, color.g, color.b, veil.alpha);
    }
    indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("uv", new Float32BufferAttribute(uvs, 2))
    .setAttribute("pigment", new Float32BufferAttribute(colorOpacity, 4))
    .setIndex(indices);
  const mesh = new Mesh(
    geometry,
    new ShaderMaterial({
      side: DoubleSide,
      transparent: true,
      depthWrite: false,
      vertexShader: `
        attribute vec4 pigment;
        varying vec4 ink;
        varying vec2 painted;
        void main() {
          ink = pigment;
          painted = uv * 2.0 - 1.0;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec4 ink;
        varying vec2 painted;
        void main() {
          vec2 p = painted;
          p.y += 0.22 * sin(p.x * 6.3) * (1.0 - abs(p.y));
          float feather = 1.0 - smoothstep(0.09, 0.94, length(p));
          float wisps = 0.72 + 0.21 * sin(12.0 * p.y - 3.2 * p.x) + 0.07 * sin(22.0 * p.y);
          gl_FragColor = vec4(ink.rgb, ink.a * feather * wisps);
          #include <colorspace_fragment>
        }
      `,
    }),
  );
  mesh.name = "Local river mist";
  mesh.renderOrder = 2;
  return mesh;
}
