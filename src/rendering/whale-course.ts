import {
  BoxGeometry,
  BufferGeometry,
  Color,
  CylinderGeometry,
  DoubleSide,
  ExtrudeGeometry,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Object3D,
  OctahedronGeometry,
  PlaneGeometry,
  ShaderMaterial,
  SphereGeometry,
  TorusGeometry,
  Shape,
  ShapeGeometry,
  Vector2,
  type Material,
} from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { STEP_SEC } from "../core/clock";
import type { Vec2 } from "../core/math";
import type { InputSettings } from "../input/input";
import type { WhaleLevel, Zone } from "../levels/schema";
import {
  currentGuide,
  hasVisibleDrift,
  isReefCurrent,
  type WaterCurrent,
} from "../levels/whale-current";
import { isDredgingLandmark } from "../levels/whale-dredging";
import { kelpApproaches } from "../levels/whale-kelp";
import { netApproaches } from "../levels/whale-net";
import {
  isCyclicNoise,
  noisePhase,
  type CyclicNoise,
} from "../levels/whale-noise";
import {
  hazardOffset,
  hazardStep,
  hazardTravelBounds,
  isWhaleBreakwater,
  isWhaleNet,
  layerBit,
} from "../levels/whale-geometry";

import { reefRockInstances, whaleCoast } from "./whale-coast";
import { WhaleBreakwater } from "./whale-breakwater";
import { WhaleDredging } from "./whale-dredging";
import { drawNetRecovery } from "./whale-net-recovery";
import type { WhaleBayLight } from "./whale-ocean";
import { WhaleWatching, watchingBoundaryLandmarks } from "./whale-watching";
import { whaleWaterLandmarks } from "./whale-water-landmarks";

type Hazard = Extract<Zone, { kind: "hazard" }>;
type Edge = readonly [Vec2, Vec2];
type CourseArtSettings = Pick<InputSettings, "low" | "reduced">;

const SURFACE = 0.18;
export const WHALE_DEPTH_Y = [0.12, -2.8, -5.9] as const;
const DEPTH_BITS = [layerBit.surface, layerBit.shallow, layerBit.deep] as const;
const danger = "#f6c073";
const ink = "#253a43";
const foam = "#fff9dc";
const shallow = "#97d7d2";

function edges(points: readonly Vec2[]): Edge[] {
  return points.flatMap((point, index) => {
    const next = points[(index + 1) % points.length];
    return next ? [[point, next] as const] : [];
  });
}

function footprint(points: readonly Vec2[]): Shape {
  const shape = new Shape();
  for (const [index, { x, z }] of points.entries()) {
    if (index === 0) shape.moveTo(x, -z);
    else shape.lineTo(x, -z);
  }
  shape.closePath();
  return shape;
}

function fill<T extends Material>(
  points: readonly Vec2[],
  height: number,
  material: T,
): Mesh<ShapeGeometry, T> {
  const geometry = new ShapeGeometry(footprint(points)).rotateX(-Math.PI / 2);
  const mesh = new Mesh(geometry, material);
  mesh.position.y = height;
  return mesh;
}

// Stroke widths are in world units so the boundary remains readable on mobile
// GPUs that clamp GL lines to a single device pixel.
function stroke(
  paths: readonly Edge[],
  height: number,
  width: number,
  color: string,
  gap = 0,
  opacity = 1,
): Mesh<BufferGeometry, MeshBasicMaterial> {
  const vertices: number[] = [];
  for (const [start, end] of paths) {
    const dx = end.x - start.x;
    const dz = end.z - start.z;
    const length = Math.hypot(dx, dz);
    if (length <= 0) continue;
    const nx = (dz / length) * width * 0.5;
    const nz = (-dx / length) * width * 0.5;
    const cadence = gap > 0 ? gap : length;
    for (let step = 0; step < length; step += cadence) {
      const a = step / length;
      const b = Math.min(step + cadence * (gap > 0 ? 0.7 : 1), length) / length;
      const x0 = start.x + dx * a;
      const z0 = start.z + dz * a;
      const x1 = start.x + dx * b;
      const z1 = start.z + dz * b;
      vertices.push(
        x0 - nx,
        height,
        z0 - nz,
        x1 - nx,
        height,
        z1 - nz,
        x1 + nx,
        height,
        z1 + nz,
        x0 - nx,
        height,
        z0 - nz,
        x1 + nx,
        height,
        z1 + nz,
        x0 + nx,
        height,
        z0 + nz,
      );
    }
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(vertices, 3));
  const material = new MeshBasicMaterial({
    color,
    side: DoubleSide,
    transparent: opacity < 1,
    opacity,
    depthWrite: opacity === 1,
  });
  return new Mesh(geometry, material);
}

function layerOutline(path: readonly Edge[], depth: number) {
  const surfaceLayer = depth === WHALE_DEPTH_Y[0];
  const y = surfaceLayer ? SURFACE : depth;
  return [
    stroke(path, y, 0.98, ink),
    stroke(
      path,
      y + 0.02,
      surfaceLayer ? 0.55 : 0.38,
      surfaceLayer ? danger : "#bacec5",
      surfaceLayer ? 0 : 3.2,
    ),
  ] as const;
}

function atDepth(points: readonly Vec2[], mask: number): Group {
  const outline = new Group();
  const path = edges(points);
  for (const [index, depth] of WHALE_DEPTH_Y.entries()) {
    if (!(mask & (DEPTH_BITS[index] ?? 0))) continue;
    outline.add(...layerOutline(path, depth));
  }
  return outline;
}

function netSpans(points: readonly Vec2[]): Edge[] {
  return edges(points).flatMap(([a, b]) => {
    const count = Math.ceil(Math.hypot(b.x - a.x, b.z - a.z) / 7.8);
    const at = (index: number): Vec2 => {
      if (index === 0) return a;
      if (index === count) return b;
      const t = (index + 0.24 * Math.sin(index * 2.41)) / count;
      return { x: MathUtils.lerp(a.x, b.x, t), z: MathUtils.lerp(a.z, b.z, t) };
    };
    return Array.from(
      { length: count },
      (_, index) => [at(index), at(index + 1)] as const,
    );
  });
}

const NET_CABLE_Y = SURFACE + 0.12;
const NET_WEIGHT_Y = WHALE_DEPTH_Y[2] - 1.32;

function netCurtain(
  spans: readonly Edge[],
  mask: number,
  detail: { value: number },
): Mesh {
  const vertices: number[] = [];
  const weave: number[] = [];
  const indices: number[] = [];
  let along = 0;
  const steps = 4;
  for (const [start, end] of spans) {
    const length = Math.hypot(end.x - start.x, end.z - start.z);
    for (const [layer, y] of WHALE_DEPTH_Y.entries()) {
      if (!(mask & (DEPTH_BITS[layer] ?? 0))) continue;
      const top = layer === 0 ? NET_CABLE_Y + 0.2 : y;
      const bottom = WHALE_DEPTH_Y[layer + 1] ?? NET_WEIGHT_Y - 0.16;
      const base = vertices.length / 3;
      for (let i = 0; i <= steps; i++) {
        const t = i / steps;
        const x = MathUtils.lerp(start.x, end.x, t);
        const z = MathUtils.lerp(start.z, end.z, t);
        const slack =
          Math.sin(t * Math.PI) *
          (0.21 + length * 0.032 + 0.12 * Math.sin(along * 0.31));
        for (const height of [top, bottom]) {
          // Keep the curtain on the collision plane. The float anchors bear the weight.
          const fall =
            slack *
            MathUtils.lerp(
              0.46,
              1,
              MathUtils.smoothstep(height, NET_WEIGHT_Y, NET_CABLE_Y),
            );
          vertices.push(x, height - fall, z);
          weave.push(along + t * length, height);
        }
        if (i < steps) {
          const a = base + i * 2;
          indices.push(a, a + 1, a + 2, a + 2, a + 1, a + 3);
        }
      }
    }
    along += length;
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(vertices, 3))
    .setAttribute("weave", new Float32BufferAttribute(weave, 2))
    .setIndex(indices);
  const mesh = new Mesh(
    geometry,
    new ShaderMaterial({
      uniforms: {
        detail,
        cableY: { value: NET_CABLE_Y },
        weightY: { value: NET_WEIGHT_Y },
        cork: { value: new Color("#c7a678") },
        submerged: { value: new Color("#7caaa4") },
        ballast: { value: new Color("#4f7275") },
      },
      side: DoubleSide,
      transparent: true,
      depthWrite: false,
      forceSinglePass: true,
      vertexShader: `
        attribute vec2 weave;
        varying vec2 net;
        varying float eyeDistance;
        void main() {
          net = weave;
          vec4 view = modelViewMatrix * vec4(position, 1.0);
          eyeDistance = -view.z;
          gl_Position = projectionMatrix * view;
        }
      `,
      fragmentShader: `
        uniform float detail;
        uniform float cableY;
        uniform float weightY;
        uniform vec3 cork;
        uniform vec3 submerged;
        uniform vec3 ballast;
        varying vec2 net;
        varying float eyeDistance;

        float thread(float row, float thickness) {
          float distance = abs(fract(row + 0.5) - 0.5);
          return 1.0 - smoothstep(thickness, thickness + clamp(fwidth(row) * 0.48, 0.024, 0.11), distance);
        }

        void main() {
          float down = smoothstep(cableY * -1.0, -weightY, -net.y);
          float u = net.x * mix(0.22, 0.31, detail);
          float v = net.y * mix(0.25, 0.34, detail);
          float warp = sin(net.x * 0.48 - net.y * 0.36) * 0.15;
          float first = u + v + warp;
          float second = u - v - warp * 0.73;
          float knot = thread(first, 0.058) * thread(second, 0.082);
          float braid = max(thread(first, 0.043), thread(second, 0.049));
          float fade = (1.0 - smoothstep(0.32, 0.66, fwidth(first) + fwidth(second)))
                       * (1.0 - 0.43 * smoothstep(103.0, 151.0, eyeDistance));
          float main = 1.0 - smoothstep(0.08, 0.23, abs(net.y - cableY));
          float lead = 1.0 - smoothstep(0.08, 0.21, abs(net.y - weightY));
          vec3 paint = mix(mix(cork, submerged, down), ballast, lead * 0.84);
          float fiber = 0.5 + 0.5 * sin(net.x * 3.7 + net.y * 8.4);
          paint *= 0.82 + 0.1 * sin(net.x * 0.18 - net.y) + main * fiber * 0.2 + knot * 0.24;
          float opacity = max(main * 0.91, max(lead * 0.69, mix(0.12, 0.47, braid * fade)));
          gl_FragColor = vec4(paint, opacity);
          #include <colorspace_fragment>
        }
      `,
    }),
  );
  mesh.name = "Net curtain and cables";
  mesh.renderOrder = -7;
  return mesh;
}

function netBuoys(
  points: readonly Vec2[],
  spans: readonly Edge[],
): InstancedMesh {
  const east = Math.max(...points.map(({ x }) => x));
  const near = Math.min(...points.map(({ z }) => z));
  const far = Math.max(...points.map(({ z }) => z));
  const shape = new SphereGeometry(1, 10, 6);
  const vertices = shape.getAttribute("position");
  const paint: number[] = [];
  const cream = new Color("#f1e4c9");
  const shade = new Color("#a27d62");
  const swatch = new Color();
  for (let i = 0; i < vertices.count; i++) {
    const y = vertices.getY(i);
    const band = MathUtils.lerp(
      0.69,
      1,
      MathUtils.smoothstep(Math.abs(vertices.getZ(i)), 0.22, 0.62),
    );
    swatch
      .copy(shade)
      .lerp(cream, MathUtils.smoothstep(y, -0.52, 0.57))
      .multiplyScalar(band)
      .toArray(paint, paint.length);
  }
  shape.setAttribute("color", new Float32BufferAttribute(paint, 3));
  const floats = new InstancedMesh(
    shape,
    new MeshStandardMaterial({ vertexColors: true, roughness: 0.99 }),
    spans.length,
  );
  floats.name = "Net anchor floats";
  const transform = new Object3D();
  const cork = new Color("#d29c6b");
  const ochre = new Color("#b47659");
  const ivory = new Color(foam);
  for (const [index, [{ x, z }, end]] of spans.entries()) {
    const corner = x === east && (z === near || z === far);
    const size = 0.79 + 0.26 * Math.sin(index * 2.39996);
    transform.position.set(x, corner ? 0.47 : 0.37 + 0.09 * size, z);
    if (corner) transform.scale.set(1.24, 1.18, 1.72);
    else transform.scale.set(0.63 * size, 0.55 * size, 1.13 * size);
    transform.rotation.y = corner ? 0 : Math.atan2(end.x - x, end.z - z);
    transform.updateMatrix();
    floats.setMatrixAt(index, transform.matrix);
    floats.setColorAt(
      index,
      corner || index % 7 === 0 ? ivory : index % 3 === 0 ? ochre : cork,
    );
  }
  return floats;
}

function netSinkers(spans: readonly Edge[]): InstancedMesh {
  const weights = new InstancedMesh(
    new SphereGeometry(1, 7, 4),
    new MeshStandardMaterial({ color: "#617b7a", roughness: 1 }),
    spans.length,
  );
  weights.name = "Net lead weights";
  const transform = new Object3D();
  for (const [index, [start, end]] of spans.entries()) {
    const tail = 0.24 + 0.11 * Math.sin(index * 1.45);
    transform.position.set(start.x, NET_WEIGHT_Y - 0.15, start.z);
    transform.rotation.y = Math.atan2(end.x - start.x, end.z - start.z);
    transform.scale.set(0.27, 0.27 + tail * 0.52, 0.65 + tail);
    transform.updateMatrix();
    weights.setMatrixAt(index, transform.matrix);
  }
  return weights;
}

function netEndPosts(edge: Edge, mask: number): InstancedMesh {
  const lastLayer = DEPTH_BITS.findLastIndex((bit) => (mask & bit) !== 0);
  const base =
    lastLayer === 2 ? NET_WEIGHT_Y : (WHALE_DEPTH_Y[lastLayer + 1] ?? 0);
  const height = NET_CABLE_Y - base;
  const shaft = new CylinderGeometry(0.22, 0.31, height, 7, 6).translate(
    0,
    base + height / 2,
    0,
  );
  const position = shaft.getAttribute("position");
  const colors = new Float32BufferAttribute(
    new Float32Array(position.count * 3),
    3,
  );
  const oak = new Color("#b0a384");
  const weight = new Color("#44666e");
  const collars = new Color("#edcc94");
  for (let i = 0; i < position.count; i++) {
    const y = position.getY(i);
    const hue = y > -0.19 ? collars : y < base + 0.75 ? weight : oak;
    colors.setXYZ(i, hue.r, hue.g, hue.b);
  }
  shaft.setAttribute("color", colors);
  const posts = new InstancedMesh(
    shaft,
    new MeshStandardMaterial({ vertexColors: true, roughness: 0.94 }),
    edge.length,
  );
  const anchor = new Object3D();
  for (const [index, { x, z }] of edge.entries()) {
    anchor.position.set(x, 0, z);
    anchor.updateMatrix();
    posts.setMatrixAt(index, anchor.matrix);
  }
  posts.name = "Net east end posts";
  return posts;
}

function netGapBed(
  edge: Edge,
  gap: Vec2,
  east: number,
  viewDepth: { value: number },
): InstancedMesh {
  const outerWater = east - gap.x;
  const near = Math.min(edge[0].z, edge[1].z);
  const far = Math.max(edge[0].z, edge[1].z);
  const stones = reefRockInstances(7, true, viewDepth);
  const place = new Object3D();
  const paint = new Color("#82999a");
  for (let i = 0; i < stones.count; i++) {
    const t = i / (stones.count - 1);
    const span = Math.sin(Math.PI * t);
    place.position.set(
      gap.x + outerWater * (0.74 + 0.085 * Math.sin(i * 2.24)),
      -10.92 - 0.2 * Math.cos(i * 1.4),
      MathUtils.lerp(near - 11, far + 11, t),
    );
    place.scale.set(
      Math.min(outerWater * 0.064, 3.6) * (0.64 + 0.36 * span),
      0.42 + 0.43 * span,
      3.4 + 3.6 * span,
    );
    place.rotation.y = 0.22 * Math.sin(i * 2.1);
    place.updateMatrix();
    stones.setMatrixAt(i, place.matrix);
    stones.setColorAt(i, paint);
  }
  stones.name = "Net gap outer bed rock";
  return stones;
}

function drawNet(
  zone: Hazard,
  level: WhaleLevel,
  detail: { value: number },
  viewDepth: { value: number },
): Group {
  const mask = zone.depthMask ?? 0;
  const group = atDepth(zone.points, mask);
  group.name = zone.id;
  const spans = netSpans(zone.points);
  const bottom = fill(
    zone.points,
    WHALE_DEPTH_Y[2] - 1.4,
    new MeshBasicMaterial({
      color: "#173943",
      transparent: true,
      opacity: 0.22,
      depthWrite: false,
    }),
  );
  bottom.renderOrder = -8;
  group.add(
    bottom,
    netCurtain(spans, mask, detail),
    netBuoys(zone.points, spans),
  );
  if (mask & layerBit.deep) group.add(netSinkers(spans));
  const { min, max } = hazardTravelBounds(zone);
  const edge = edges(zone.points).filter(
    ([a, b]) =>
      a.x === b.x &&
      (a.x === max.x || (a.x === min.x && min.x > level.bounds.min.x)),
  );
  group.add(
    stroke(edge, SURFACE + 0.04, 1.23, danger),
    stroke(edges(zone.points), SURFACE + 0.035, 0.22, "#e6d1ab"),
  );
  if (mask !== 0)
    for (const endpoint of edge) {
      const posts = netEndPosts(endpoint, mask);
      if (endpoint[0].x === min.x) posts.name = "Net west end posts";
      group.add(posts);
    }
  if (min.x > level.bounds.min.x) return group;

  const gap = level.landmarks.find(({ id }) => id === "net-gap")?.pos;
  if (gap) {
    const east = level.zones.filter(isWhaleNet).reduce((edge, other) => {
      const x = hazardTravelBounds(other).min.x;
      return x >= gap.x ? Math.min(edge, x) : edge;
    }, level.bounds.max.x);
    const clearance = Math.min(gap.x - max.x, east - gap.x);
    const mouth: Edge[] = [];
    for (const z of [min.z - 7, max.z + 7]) {
      for (const side of [-1, 1]) {
        mouth.push([
          { x: gap.x + side * clearance * 0.43, z: z - 4 },
          { x: gap.x + side * clearance * 0.19, z: z + 2 },
        ]);
      }
    }
    // Open chevrons point through the water beside the net.
    group.add(stroke(mouth, 0.09, 1.14, foam, 0, 0.88));
    const endpoint = edge[0];
    if (endpoint && clearance > 0)
      group.add(netGapBed(endpoint, gap, east, viewDepth));
  }
  return group;
}

function drawWake(length: number, width: number) {
  const reach = 32;
  const forward = 4;
  const centerZ = (forward - reach) / 2;
  const strength = { value: 1 };
  const time = { value: 0 };
  const detail = { value: 1 };
  const submersion = { value: 0 };
  const mesh = new Mesh(
    new PlaneGeometry(width * 2.3, length + reach + forward).rotateX(
      -Math.PI / 2,
    ),
    new ShaderMaterial({
      uniforms: {
        foam: { value: new Color("#f8eed5") },
        halfLength: { value: length / 2 },
        halfWidth: { value: width / 2 },
        centerZ: { value: centerZ },
        strength,
        time,
        detail,
        submersion,
      },
      transparent: true,
      depthWrite: false,
      vertexShader: `
        varying vec2 paint;
        uniform float centerZ;
        void main() {
          paint = vec2(position.x, position.z + centerZ);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec2 paint;
        uniform vec3 foam;
        uniform float halfLength;
        uniform float halfWidth;
        uniform float strength;
        uniform float time;
        uniform float detail;
        uniform float submersion;
        void main() {
          float crossWake = abs(paint.x);
          float water = 0.5 + 0.5 * sin(paint.y * 0.89 + 0.95 * sin(paint.x * 0.46) + time * 3.9);
          float flecks = 0.5 + 0.5 * sin(paint.y * 2.7 + 1.7 * cos(paint.x * 1.6) + time * 4.3);
          float tip = halfLength + 1.8 - paint.y;
          float bowCurve = 0.35 + halfWidth * smoothstep(0.0, 8.6, tip);
          float lip = 1.0 - smoothstep(0.23, 1.35, abs(crossWake - bowCurve - water * 0.31));
          float wash = 1.0 - smoothstep(0.42, 2.64, abs(crossWake - bowCurve - 0.68));
          float bow = (lip * 0.89 + wash * 0.23) * smoothstep(0.0, 1.3, tip)
                     * (1.0 - smoothstep(5.7, 13.9, tip));
          float aft = -paint.y - halfLength + 1.7;
          float distance = max(0.0, aft);
          float center = 1.0 - smoothstep(0.8, 2.65 + 0.13 * distance, crossWake);
          float fan = 1.0 - smoothstep(0.25, 1.45 + distance * 0.028, abs(crossWake - (1.9 + aft * 0.49)));
          float inner = 1.0 - smoothstep(0.12, 0.93, abs(crossWake - (1.0 + aft * 0.28)));
          float envelope = smoothstep(0.0, 2.2, aft) * (1.0 - smoothstep(7.0, 33.7, aft));
          float broken = mix(0.76, mix(0.42, 1.0, water), detail);
          float stern = envelope * (0.64 * fan + 0.37 * center + inner * 0.17 * detail) * broken;
          stern += 0.16 * detail * center * flecks * envelope * (1.0 - smoothstep(6.0, 22.0, aft));
          float alpha = strength * (bow * (0.68 + water * 0.18) + stern)
                      * mix(1.0, 0.32, submersion);
          gl_FragColor = vec4(foam, min(alpha, 0.83));
          #include <colorspace_fragment>
        }
      `,
    }),
  );
  mesh.position.set(0, 0.048, centerZ);
  mesh.name = "Cargo bow and stern foam";
  mesh.renderOrder = -1;
  return { mesh, strength, time, detail, submersion };
}

const CARGO_DECK_Y = 1.86;

function cargoHull(
  points: readonly Vec2[],
  center: Vec2,
): Mesh<BufferGeometry, MeshStandardMaterial> {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const layers = [
    [-2.53, 0.7, "#354958"],
    [-1.74, 0.87, "#534b55"],
    [-0.65, 0.97, "#8f5d52"],
    [-0.11, 0.997, "#b27960"],
    [0, 1, "#344b59"],
    [0.52, 1, "#456474"],
    [1.51, 0.99, "#527786"],
    [1.68, 0.985, "#304c5b"],
    [1.78, 0.98, "#b4a687"],
    [CARGO_DECK_Y, 0.91, "#cec3a6"],
  ] as const;
  const outline = edges(points)
    .filter(([a, b]) => a.x !== b.x || a.z !== b.z)
    .flatMap(([a, b]) => {
      const count = Math.ceil(Math.hypot(b.x - a.x, b.z - a.z) / 4);
      return Array.from({ length: count }, (_, index) => ({
        x: MathUtils.lerp(a.x, b.x, index / count),
        z: MathUtils.lerp(a.z, b.z, index / count),
      }));
    });
  for (const [i, [y, inset, hue]] of layers.entries()) {
    for (const [j, { x, z }] of outline.entries()) {
      positions.push(
        center.x + (x - center.x) * inset,
        y,
        center.z + (z - center.z) * inset,
      );
      new Color(hue)
        .multiplyScalar(
          0.93 + 0.09 * Math.sin(j * 0.74) + 0.035 * Math.cos(j * 1.9),
        )
        .toArray(colors, colors.length);
      if (i === 0) continue;
      const a = (i - 1) * outline.length + j;
      const b = (i - 1) * outline.length + ((j + 1) % outline.length);
      indices.push(
        a,
        a + outline.length,
        b,
        b,
        a + outline.length,
        b + outline.length,
      );
    }
  }
  const keel = positions.length / 3;
  positions.push(center.x, layers[0][0], center.z);
  new Color(layers[0][2]).toArray(colors, colors.length);
  for (let j = 0; j < outline.length; j++)
    indices.push(keel, j, (j + 1) % outline.length);
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 3))
    .setIndex(indices);
  geometry.computeVertexNormals();
  const hull = new Mesh(
    geometry,
    new MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.95,
      side: DoubleSide,
    }),
  );
  hull.name = "Cargo hull";
  return hull;
}

function cargoShadow(points: readonly Vec2[], center: Vec2) {
  const positions: number[] = [];
  const paint: number[] = [];
  // The cargo footprint is convex. Fading toward each edge keeps the wash inside it.
  for (const [a, b] of edges(points)) {
    if (a.x === b.x && a.z === b.z) continue;
    positions.push(center.x, 0, center.z, a.x, 0, a.z, b.x, 0, b.z);
    paint.push(1, 0, 0);
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("paint", new Float32BufferAttribute(paint, 1));
  const strength = { value: 0.06 };
  const material = new ShaderMaterial({
    uniforms: {
      strength,
      pigment: { value: new Color("#103849") },
    },
    transparent: true,
    depthWrite: false,
    side: DoubleSide,
    forceSinglePass: true,
    vertexShader: `
      attribute float paint;
      varying float shadow;
      void main() {
        shadow = paint;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform float strength;
      uniform vec3 pigment;
      varying float shadow;
      void main() {
        gl_FragColor = vec4(pigment, strength * smoothstep(0.02, 0.54, shadow));
        #include <colorspace_fragment>
      }
    `,
  });
  const mesh = new Mesh(geometry, material);
  mesh.name = "Cargo submerged shadow";
  mesh.position.y = WHALE_DEPTH_Y[1] - 0.5;
  mesh.renderOrder = -8;
  return { mesh, strength };
}

function setSurfaceVisibility(material: Material, opacity: number): void {
  const transparent = opacity < 1;
  if (material.transparent !== transparent) {
    material.transparent = transparent;
    material.depthWrite = !transparent;
    material.needsUpdate = true;
  }
  material.opacity = opacity;
}

function patrolRails(hazard: Hazard): Mesh {
  const { min, max } = hazardTravelBounds(hazard);
  const paths: Edge[] = [min.z, max.z].map((z) => [
    { x: min.x, z },
    { x: max.x, z },
  ]);
  return stroke(paths, 0.085, 0.75, danger, 6.5, 0.77);
}

function cargoFittings(
  length: number,
  width: number,
): Mesh<BufferGeometry, MeshStandardMaterial> {
  const parts: BufferGeometry[] = [];
  function add(
    geometry: BufferGeometry,
    x: number,
    y: number,
    z: number,
    hue: string,
  ) {
    const part = geometry.index ? geometry.toNonIndexed() : geometry;
    if (part !== geometry) geometry.dispose();
    part.translate(x, y, z);
    part.deleteAttribute("uv");
    const color = new Color(hue);
    const paint = new Float32BufferAttribute(
      new Float32Array(part.getAttribute("position").count * 3),
      3,
    );
    for (let i = 0; i < paint.count; i++)
      paint.setXYZ(i, color.r, color.g, color.b);
    part.setAttribute("color", paint);
    parts.push(part);
  }
  function cabin(w: number, d: number, h: number, clip: number) {
    const x = w * 0.5;
    const z = d * 0.5;
    const outline = [
      { x: -x + clip, z: -z },
      { x: x - clip, z: -z },
      { x, z: -z + clip },
      { x, z: z - clip },
      { x: x - clip, z },
      { x: -x + clip, z },
      { x: -x, z: z - clip },
      { x: -x, z: -z + clip },
    ];
    return new ExtrudeGeometry(footprint(outline), {
      depth: h,
      bevelEnabled: false,
    }).rotateX(-Math.PI / 2);
  }
  const stern = -length * 0.252;
  const bridgeFloor = CARGO_DECK_Y + 2.14;
  const windows = bridgeFloor + 1.34;
  const roof = windows + 0.65;
  add(
    cabin(width * 0.48, length * 0.246, 2.14, 0.74),
    0,
    CARGO_DECK_Y,
    stern,
    "#a99d83",
  );
  add(
    cabin(width * 0.405, length * 0.172, 1.34, 0.68),
    0,
    bridgeFloor,
    stern + 0.63,
    "#eee2c5",
  );
  add(
    cabin(width * 0.411, length * 0.178, 0.65, 0.71),
    0,
    windows,
    stern + 0.63,
    "#34515f",
  );
  add(
    cabin(width * 0.458, length * 0.205, 0.31, 0.78),
    0,
    roof,
    stern + 0.63,
    "#c29676",
  );
  for (const mullion of [-1, 0, 1]) {
    add(
      new BoxGeometry(0.17, 0.65, 0.24),
      mullion * width * 0.076,
      windows + 0.325,
      stern + 0.63 + length * 0.09,
      "#dbceb4",
    );
  }
  add(
    new CylinderGeometry(0.64, 0.84, 1.35, 8),
    -width * 0.086,
    roof + 0.94,
    stern - 0.73,
    "#a07763",
  );
  add(
    new CylinderGeometry(0.67, 0.7, 0.3, 8),
    -width * 0.086,
    roof + 1.75,
    stern - 0.73,
    "#334b54",
  );
  add(
    new CylinderGeometry(0.09, 0.14, 1.68, 6),
    width * 0.085,
    roof + 1.12,
    stern + 1,
    "#d1c3a3",
  );
  add(
    new BoxGeometry(1.63, 0.17, 0.28),
    width * 0.085,
    roof + 1.98,
    stern + 1,
    "#e3d8ba",
  );
  for (const side of [-1, 1]) {
    add(
      new CylinderGeometry(0.64, 0.93, 0.48, 8),
      side * width * 0.133,
      CARGO_DECK_Y + 0.49,
      length * 0.353,
      "#59686c",
    );
    add(
      new BoxGeometry(0.28, 0.27, length * 0.41),
      side * width * 0.4,
      CARGO_DECK_Y + 0.18,
      length * 0.026,
      "#c5bca0",
    );
  }
  add(
    new BoxGeometry(width * 0.25, 0.22, length * 0.082),
    0,
    CARGO_DECK_Y + 0.17,
    length * 0.345,
    "#c4ac7b",
  );
  const geometry = mergeGeometries(parts);
  for (const part of parts) part.dispose();
  if (!geometry) throw new Error("Unable to combine cargo fittings");
  const details = new Mesh(
    geometry,
    new MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.92,
    }),
  );
  details.name = "Cargo deck fittings";
  return details;
}

const CONTAINER_HEIGHT = 1.48;

function cargoBoxes(
  width: number,
  length: number,
): InstancedMesh<BufferGeometry, MeshStandardMaterial> {
  const shell = new BoxGeometry(
    width,
    CONTAINER_HEIGHT - 0.13,
    length,
  ).translate(0, -0.065, 0);
  const ribs = [-0.31, -0.1, 0.13, 0.34].map((offset) =>
    new BoxGeometry(width * 0.95, 0.13, 0.17).translate(
      0,
      CONTAINER_HEIGHT / 2 - 0.065,
      length * offset,
    ),
  );
  const parts = [shell, ...ribs].map((block) => {
    const part = block.toNonIndexed();
    block.dispose();
    return part;
  });
  const geometry = mergeGeometries(parts);
  for (const part of parts) part.dispose();
  if (!geometry) throw new Error("Unable to combine cargo boxes");
  const containers = new InstancedMesh(
    geometry,
    new MeshStandardMaterial({ roughness: 0.91 }),
    10,
  );
  containers.name = "Cargo container stacks";
  return containers;
}

class CargoShip {
  readonly group = new Group();
  private readonly heading = new Group();
  private readonly wash: ReturnType<typeof drawWake>;
  private readonly shadow: ReturnType<typeof cargoShadow>;
  private readonly hull: MeshStandardMaterial;
  private readonly deck: readonly Material[];
  private readonly outlines: readonly {
    readonly depth: number;
    readonly lines: ReturnType<typeof layerOutline>;
  }[];
  private readonly hullTint = new Color("#5f899d");

  constructor(private readonly hazard: Hazard) {
    this.group.name = hazard.id;
    const { points, motion, depthMask } = hazard;
    const minX = Math.min(...points.map((p) => p.x));
    const maxX = Math.max(...points.map((p) => p.x));
    const minZ = Math.min(...points.map((p) => p.z));
    const maxZ = Math.max(...points.map((p) => p.z));
    const center = { x: (maxX + minX) * 0.5, z: (maxZ + minZ) * 0.5 };
    this.heading.position.set(center.x, 0, center.z);
    const eastWest =
      Math.abs(motion?.travel.x ?? 0) > Math.abs(motion?.travel.z ?? 0);
    const length = eastWest ? maxX - minX : maxZ - minZ;
    const width = eastWest ? maxZ - minZ : maxX - minX;
    const hull = cargoHull(points, center);
    this.hull = hull.material;
    this.hull.forceSinglePass = true;
    this.shadow = cargoShadow(points, center);
    const deck = fill(
      points.map(({ x, z }) => ({
        x: center.x + (x - center.x) * 0.91,
        z: center.z + (z - center.z) * 0.91,
      })),
      CARGO_DECK_Y,
      new MeshStandardMaterial({
        color: "#7f8072",
        roughness: 1,
        side: DoubleSide,
      }),
    );
    const foredeck = fill(
      [
        { x: 0, z: length * 0.446 },
        { x: width * 0.321, z: length * 0.285 },
        { x: width * 0.29, z: length * 0.229 },
        { x: -width * 0.29, z: length * 0.229 },
        { x: -width * 0.321, z: length * 0.285 },
      ],
      CARGO_DECK_Y + 0.07,
      new MeshStandardMaterial({
        color: "#bbaf8b",
        roughness: 0.96,
        side: DoubleSide,
      }),
    );
    const containers = cargoBoxes(width * 0.171, length * 0.119);
    const crate = new Object3D();
    const cargoColors = [
      new Color("#b17d68"),
      new Color("#bba781"),
      new Color("#66838a"),
      new Color("#987265"),
      new Color("#8c9d90"),
    ] as const;
    const stackSlots = [0, 1, 2, 3, 4, 5, 0, 2, 3, 5];
    for (const [index, slot] of stackSlots.entries()) {
      crate.position.set(
        (slot % 2 === 0 ? -1 : 1) * width * 0.107,
        CARGO_DECK_Y + CONTAINER_HEIGHT * (index < 6 ? 0.5 : 1.5),
        Math.floor(slot / 2) * length * 0.137 - length * 0.116,
      );
      crate.updateMatrix();
      containers.setMatrixAt(index, crate.matrix);
      containers.setColorAt(
        index,
        cargoColors[(index + slot) % cargoColors.length] ?? cargoColors[0],
      );
    }
    const bowMark = fill(
      [
        { x: -width * 0.104, z: length * 0.259 },
        { x: 0, z: length * 0.32 },
        { x: width * 0.104, z: length * 0.259 },
        { x: width * 0.104, z: length * 0.307 },
        { x: 0, z: length * 0.421 },
        { x: -width * 0.104, z: length * 0.307 },
      ],
      CARGO_DECK_Y + 0.085,
      new MeshBasicMaterial({ color: foam, side: DoubleSide }),
    );
    const fittings = cargoFittings(length, width);
    this.deck = [
      deck.material,
      foredeck.material,
      containers.material,
      bowMark.material,
      fittings.material,
    ];
    for (const material of this.deck) material.forceSinglePass = true;
    const path = edges(points);
    this.outlines = WHALE_DEPTH_Y.flatMap((depth, index) => {
      if (!((depthMask ?? 0) & (DEPTH_BITS[index] ?? 0))) return [];
      const lines = layerOutline(path, depth);
      for (const line of lines) line.material.forceSinglePass = true;
      const layer = new Group();
      layer.name =
        depth === WHALE_DEPTH_Y[0]
          ? "Cargo waterline"
          : "Cargo submerged occupancy";
      layer.add(...lines);
      this.group.add(layer);
      return [{ depth, lines }];
    });
    this.wash = drawWake(length, width);
    this.heading.add(fittings, foredeck, containers, bowMark, this.wash.mesh);
    this.group.add(this.shadow.mesh, hull, deck, this.heading);
  }

  update(
    tick: number,
    { low, reduced }: CourseArtSettings,
    depth: number,
  ): void {
    const offset = hazardOffset(this.hazard, tick);
    const direction = hazardStep(this.hazard, tick);
    this.group.position.set(offset.x, 0, offset.z);
    this.heading.rotation.y = Math.atan2(direction.x, direction.z);
    const travel = this.hazard.motion?.travel ?? offset;
    const endDistance = Math.min(
      Math.hypot(offset.x, offset.z),
      Math.hypot(travel.x - offset.x, travel.z - offset.z),
    );
    this.wash.strength.value = MathUtils.smoothstep(endDistance, 0, 4.2);
    this.wash.time.value = reduced ? 0 : tick * STEP_SEC;
    this.wash.detail.value = Number(!low);
    const submerged = MathUtils.smoothstep(depth, 0.22, 1.5);
    this.wash.submersion.value = submerged;
    this.shadow.strength.value = 0.06 + submerged * 0.37;
    this.hull.color.setRGB(1, 1, 1).lerp(this.hullTint, submerged * 0.61);
    setSurfaceVisibility(this.hull, 1 - submerged * 0.58);
    for (const material of this.deck)
      setSurfaceVisibility(material, 1 - submerged * 0.87);
    for (const {
      depth: level,
      lines: [base, trim],
    } of this.outlines) {
      const surface = level === WHALE_DEPTH_Y[0];
      setSurfaceVisibility(
        base.material,
        surface ? 1 - submerged * 0.62 : 0.58 + submerged * 0.42,
      );
      setSurfaceVisibility(
        trim.material,
        surface ? 1 - submerged * 0.38 : 0.55 + submerged * 0.45,
      );
    }
  }
}

function drawNoise(points: readonly Vec2[]) {
  const group = new Group();
  const travel = { value: 0 };
  const polygon = fill(
    points,
    0.031,
    new MeshBasicMaterial({
      color: "#866d91",
      side: DoubleSide,
      transparent: true,
      opacity: 0.3,
      depthWrite: false,
    }),
  );
  const geometry = polygon.geometry;
  const material = new MeshBasicMaterial({
    color: "#ffeac4",
    side: DoubleSide,
    transparent: true,
    depthWrite: false,
  });
  material.onBeforeCompile = (shader) => {
    shader.uniforms.noiseTravel = travel;
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        "#include <common>\nvarying vec2 noiseWater;",
      )
      .replace(
        "#include <begin_vertex>",
        "#include <begin_vertex>\nnoiseWater = position.xz;",
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        "#include <common>\nvarying vec2 noiseWater;\nuniform float noiseTravel;",
      )
      .replace(
        "#include <alphatest_fragment>",
        `
          vec2 water = noiseWater * vec2(0.055, 0.25);
          water.y -= noiseTravel;
          float cross = sin(water.x * 4.1 - water.y * 0.23);
          float crest = water.y + 0.63 * cos(water.x) + cross * 0.44;
          float stripe = abs(sin(crest));
          float echo = abs(sin(crest - 0.39));
          float breaks = smoothstep(-0.66, 0.61, sin(water.x * 2.6 + water.y * 0.17));
          diffuseColor.a *= ((1.0 - smoothstep(0.05, 0.26, stripe)) * 0.62
                          + (1.0 - smoothstep(0.04, 0.17, echo)) * 0.29) * breaks;
          #include <alphatest_fragment>
        `,
      );
  };
  polygon.renderOrder = -3;
  const bands = new Mesh(geometry, material);
  bands.position.y = 0.05;
  bands.renderOrder = -2;
  const boundary = stroke(edges(points), SURFACE, 0.5, danger, 5, 0.8);
  group.add(polygon, bands, boundary);
  return {
    group,
    travel,
    wash: polygon.material,
    bands: material,
    boundary: boundary.material,
  };
}

function drawBeacons(
  landmarks: WhaleLevel["landmarks"],
  segments: WhaleLevel["segments"],
): Group {
  const group = new Group();
  const routes = landmarks.filter(({ kind }) => kind === "beacon");
  const rest = landmarks.filter(({ kind }) => kind === "water");
  const transform = new Object3D();
  for (const [marks, breathing] of [
    [routes, false],
    [rest, true],
  ] as const) {
    if (!marks.length) continue;
    const pieces = [
      [
        new SphereGeometry(1, 10, 6)
          .scale(1.57, 0.76, 1.57)
          .translate(0, 0.23, 0),
        "#b79075",
      ],
      [
        new CylinderGeometry(1.3, 1.53, 0.35, 10).translate(0, 0.55, 0),
        "#f8ebce",
      ],
      [
        new CylinderGeometry(0.11, 0.21, 2.6, 6).translate(0, 1.92, 0),
        "#516466",
      ],
      [
        breathing
          ? new TorusGeometry(0.86, 0.22, 6, 14)
              .rotateY(Math.PI / 4)
              .translate(0, 3.43, 0)
          : new OctahedronGeometry(1.19)
              .scale(0.87, 1.15, 0.87)
              .translate(0, 3.45, 0),
        breathing ? "#b3e4d2" : foam,
      ],
    ] as const;
    const painted = pieces.map(([source, hue]) => {
      const geometry = source.index ? source.toNonIndexed() : source;
      const count = geometry.getAttribute("position").count;
      const colors: number[] = [];
      const color = new Color(hue);
      for (let i = 0; i < count; i++) color.toArray(colors, i * 3);
      geometry.setAttribute("color", new Float32BufferAttribute(colors, 3));
      return geometry;
    });
    const geometry = mergeGeometries(painted);
    for (const piece of new Set([
      ...painted,
      ...pieces.map(([shape]) => shape),
    ]))
      piece.dispose();
    const paint = new MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.9,
    });
    const aquamarine = new Color("#c4eee4");
    const ivory = new Color();
    for (const [index, segment] of segments.entries()) {
      const end = segments[index + 1]?.start ?? Infinity;
      const visibleBatch = marks.filter(
        ({ pos }) => pos.z >= segment.start && pos.z < end,
      );
      if (!visibleBatch.length) continue;
      const instances = new InstancedMesh(geometry, paint, visibleBatch.length);
      for (const [slot, landmark] of visibleBatch.entries()) {
        transform.position.set(landmark.pos.x, 0, landmark.pos.z);
        transform.updateMatrix();
        instances.setMatrixAt(slot, transform.matrix);
        instances.setColorAt(
          slot,
          landmark.id.startsWith("quiet-") ? aquamarine : ivory,
        );
      }
      group.add(instances);
    }
  }
  return group;
}

function directionStamps(start: Vec2, end: Vec2): Edge[] {
  const length = Math.hypot(end.x - start.x, end.z - start.z);
  const ux = (end.x - start.x) / length;
  const uz = (end.z - start.z) / length;
  const stamps: Edge[] = [];
  for (let step = 13; step < length - 10; step += 16) {
    const tip = { x: start.x + ux * step, z: start.z + uz * step };
    const center = { x: tip.x - ux * 3.6, z: tip.z - uz * 3.6 };
    for (const side of [-1, 1])
      stamps.push([
        { x: center.x - uz * 3.2 * side, z: center.z + ux * 3.2 * side },
        tip,
      ]);
  }
  return stamps;
}

function drawCurrentDrift(zone: WaterCurrent, depth: { value: number }) {
  const { entry } = currentGuide(zone);
  const travel = { value: 0 };
  const density = { value: 1 };
  const drift = fill(
    zone.points,
    WHALE_DEPTH_Y[1] + 0.3,
    new ShaderMaterial({
      uniforms: {
        entry: { value: new Vector2(entry.x, entry.z) },
        flow: { value: new Vector2(zone.direction.x, zone.direction.z) },
        travel,
        density,
        depth,
        emphasis: { value: isReefCurrent(zone) ? 0.68 : 1 },
      },
      transparent: true,
      depthWrite: false,
      side: DoubleSide,
      vertexShader: `
        varying vec2 water;
        varying float viewDistance;
        void main() {
          water = position.xz;
          vec4 view = modelViewMatrix * vec4(position, 1.0);
          viewDistance = -view.z;
          gl_Position = projectionMatrix * view;
        }
      `,
      fragmentShader: `
        uniform vec2 entry;
        uniform vec2 flow;
        uniform float travel;
        uniform float density;
        uniform float depth;
        uniform float emphasis;
        varying vec2 water;
        varying float viewDistance;
        void main() {
          vec2 offset = water - entry;
          float crosswise = dot(offset, vec2(-flow.y, flow.x)) / 2.3;
          float lane = floor(crosswise);
          float along = (dot(offset, flow) - travel) / 9.2;
          float pulse = fract(along + lane * 0.618);
          float taper = smoothstep(0.16, 0.43, pulse) * (1.0 - smoothstep(0.43, 0.61, pulse));
          float center = abs(fract(crosswise) - 0.5);
          float fleck = 1.0 - smoothstep(0.0, 0.13 * taper + 0.001, center);
          float alternate = mix(1.0 - mod(lane, 2.0), 1.0, density);
          float visibility = mix(0.45, 0.75, smoothstep(0.0, 1.0, depth));
          visibility *= 1.0 - smoothstep(78.0, 150.0, viewDistance);
          gl_FragColor = vec4(vec3(0.62, 0.90, 0.84), fleck * taper * alternate * visibility * emphasis);
          #include <colorspace_fragment>
        }
      `,
    }),
  );
  drift.name = `${zone.id}-drift`;
  drift.renderOrder = -3;
  return { drift, travel, density };
}

function drawCurrent(zone: WaterCurrent) {
  const group = new Group();
  group.name = zone.id;
  const { entry, exit } = currentGuide(zone);
  const chevrons = directionStamps(entry, exit);
  if (zone.id === "bay-current") {
    // A soft current uses direction marks and moving water, leaving the
    // dashed enclosures for hazards and other explicit boundaries.
    group.add(stroke(chevrons, SURFACE + 0.012, 0.66, shallow, 0, 0.93));
    return { group };
  }
  const outline = edges(zone.points);
  const wash = fill(
    zone.points,
    SURFACE - 0.02,
    new MeshBasicMaterial({
      color: "#63b9c4",
      transparent: true,
      opacity: 0.15,
      depthWrite: false,
      side: DoubleSide,
    }),
  );
  wash.renderOrder = -4;
  const guides = [
    stroke(chevrons, SURFACE + 0.012, 0.8, foam, 0, 0.83),
    stroke(chevrons, WHALE_DEPTH_Y[1], 0.95, shallow, 0, 0.9),
    stroke(chevrons, WHALE_DEPTH_Y[2], 0.95, shallow, 0, 0.9),
  ];
  const reef = isReefCurrent(zone);
  if (reef) {
    for (const [layer, guide] of guides.entries()) guide.visible = layer === 0;
  }
  group.add(
    wash,
    stroke(outline, SURFACE, 0.52, shallow, 3.1, reef ? 0.5 : 0.74),
    ...guides,
  );
  return { group, reefGuides: reef ? guides : undefined };
}

function bayMouthWash(level: WhaleLevel): Mesh {
  const mouth = level.landmarks.find(({ id }) => id === "bay-exit")?.pos;
  const crests: Edge[] = [];
  if (mouth && level.landmarks.some(({ id }) => id === "bay-refill")) {
    for (const side of [-1, 1]) {
      for (const [index, offset] of [-17, -7, 4].entries()) {
        const x = mouth.x + side * (32 - index * 4);
        const z = mouth.z + offset;
        crests.push(
          [
            { x, z },
            { x: x - side * 3, z: z + 3 },
          ],
          [
            { x: x - side * 3, z: z + 3 },
            { x: x - side * 5, z: z + 7 },
          ],
        );
      }
    }
  }
  return stroke(crests, SURFACE + 0.024, 0.78, foam, 0, 0.66);
}

function kelpFronds(): BufferGeometry {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const root = new Color("#2a5250");
  const leaf = new Color("#628a65");
  const tip = new Color("#bec389");
  const paint = new Color();
  const sides = [-1, 0, 1];
  const tiers = [
    [0.96, 0.69, 0.155],
    [0.75, 0.86, 0.19],
    [1, 0.55, 0.15],
    [0.88, 0.73, 0.17],
  ] as const;
  const rows = 6;
  for (const [frond, [height, reach, blade]] of tiers.entries()) {
    const base = positions.length / 3;
    const angle = frond * 2.39996;
    for (let row = 0; row <= rows; row++) {
      const t = row / rows;
      const flare = Math.sin(Math.PI * t);
      const spread = 0.027 + flare * blade * (1 + Math.sin(t * 13) * 0.26);
      const curl = angle + Math.PI / 2 + Math.sin(t * 4) * 0.32 + t * 0.49;
      const stem = reach * t * t;
      for (const side of sides) {
        positions.push(
          Math.cos(angle) * stem + Math.cos(curl) * side * spread,
          height * (1 - (1 - t) ** 1.35) - Math.abs(side) * flare * 0.052,
          Math.sin(angle) * stem + Math.sin(curl) * side * spread,
        );
        paint
          .copy(root)
          .lerp(leaf, MathUtils.smoothstep(t, 0.08, 0.62))
          .lerp(
            tip,
            MathUtils.smoothstep(t, 0.34, 1) * (side === 0 ? 0.92 : 0.58),
          )
          .toArray(colors, colors.length);
      }
      if (row === 0) continue;
      const a = base + (row - 1) * 3;
      const b = a + 3;
      indices.push(
        a,
        a + 1,
        b,
        b,
        a + 1,
        b + 1,
        a + 1,
        a + 2,
        b + 1,
        b + 1,
        a + 2,
        b + 2,
      );
    }
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 3))
    .setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function kelpBeds(zone: Zone, viewDepth: { value: number }): Group {
  const left = Math.min(...zone.points.map(({ x }) => x));
  const right = Math.max(...zone.points.map(({ x }) => x));
  const near = Math.min(...zone.points.map(({ z }) => z));
  const far = Math.max(...zone.points.map(({ z }) => z));
  // The two eastern entries approach opposite ends. Leave open mouths on both sides of that bank.
  const clumps = [
    [0.16, 0.21],
    [0.13, 0.43],
    [0.15, 0.65],
    [0.17, 0.84],
    [0.85, 0.44],
    [0.86, 0.63],
  ] as const;
  const plantsPerClump = 4;
  const grass = new InstancedMesh(
    kelpFronds(),
    new MeshStandardMaterial({
      vertexColors: true,
      side: DoubleSide,
      roughness: 0.99,
      emissive: "#667c45",
      emissiveIntensity: 0.09,
    }),
    clumps.length * plantsPerClump,
  );
  grass.name = "Net shelter kelp";
  const shelves = reefRockInstances(clumps.length, true, viewDepth);
  shelves.name = "Net shelter submerged shelves";
  const stone = new Color("#748a6a");
  const transform = new Object3D();
  for (const [index, [u, v]] of clumps.entries()) {
    const x = MathUtils.lerp(left, right, u);
    const z = MathUtils.lerp(near, far, v);
    transform.position.set(x, -11.94, z);
    transform.scale.set(2.8 + u, 0.34, 4.1);
    transform.rotation.y = Math.sin(index * 2.41) * 0.46;
    transform.updateMatrix();
    shelves.setMatrixAt(index, transform.matrix);
    shelves.setColorAt(index, stone);
    for (let plant = 0; plant < plantsPerClump; plant++) {
      const offset = plant * 2.4 + index * 0.87;
      const size = 0.75 + 0.25 * Math.sin(offset * 0.88 + 1) ** 2;
      transform.position.set(
        x + Math.cos(offset) * 1.7,
        -12.52,
        z + Math.sin(offset) * 3.1,
      );
      transform.rotation.y = offset + 0.72;
      transform.scale.set(3.1 * size, 4.57 * size, 3.2 * size);
      transform.updateMatrix();
      grass.setMatrixAt(index * plantsPerClump + plant, transform.matrix);
    }
  }
  const beds = new Group();
  beds.add(shelves, grass);
  return beds;
}

function channelArrows(
  level: WhaleLevel,
  ids: readonly string[],
  color = shallow,
  start?: Vec2,
): Mesh {
  const landmarks = ids.flatMap((id) =>
    level.landmarks.filter((mark) => mark.id === id).map(({ pos }) => pos),
  );
  const anchors = start ? [start, ...landmarks] : landmarks;
  const stamps: Edge[] = [];
  for (let index = 1; index < anchors.length; index += 1) {
    const start = anchors[index - 1];
    const end = anchors[index];
    if (!start || !end) continue;
    stamps.push(...directionStamps(start, end));
  }
  return stroke(stamps, 0.06, 0.68, color, 0, 0.54);
}

function routeGates(level: WhaleLevel): Mesh[] {
  return level.triggers.flatMap((gate) => {
    if (gate.kind !== "route" || gate.crossingZ === undefined) return [];
    const xs = gate.points.map(({ x }) => x);
    const z = gate.crossingZ;
    const quiet = gate.route === "quiet";
    return [
      stroke(
        [
          [
            { x: Math.min(...xs), z },
            { x: Math.max(...xs), z },
          ],
        ],
        SURFACE + 0.08,
        0.9,
        quiet ? shallow : danger,
        quiet ? 0 : 5.5,
        0.85,
      ),
    ];
  });
}

function approachMarks(goal: Zone): Mesh {
  const front = Math.min(...goal.points.map(({ z }) => z));
  const marks = edges(goal.points)
    .filter(([a, b]) => a.z === front && b.z === front && a.x !== b.x)
    .flatMap(([a, b]) => {
      const at = (t: number): Vec2 => ({ x: a.x + (b.x - a.x) * t, z: front });
      return [
        [at(0.06), at(0.22)],
        [at(0.78), at(0.94)],
      ] as const;
    });
  return stroke(marks, 0.09, 1.6, foam, 0, 0.94);
}

export class WhaleCourse {
  readonly group = new Group();
  private readonly boats: CargoShip[] = [];
  private readonly noise: {
    zone: CyclicNoise;
    art: ReturnType<typeof drawNoise>;
  }[] = [];
  private readonly currentDrift: ReturnType<typeof drawCurrentDrift>[] = [];
  private readonly reefGuides: Mesh[][] = [];
  private readonly offshoreCues = new Group();
  private readonly breakwater: WhaleBreakwater;
  private readonly dredging: WhaleDredging;
  private readonly watching: WhaleWatching;
  private readonly netDetail = { value: 1 };
  private readonly bayBend: Mesh;
  private readonly bayDirect: Mesh;

  constructor(level: WhaleLevel, bayLight: WhaleBayLight) {
    this.breakwater = new WhaleBreakwater(level);
    this.dredging = new WhaleDredging(level);
    this.watching = new WhaleWatching(level);
    const crossings = new Set(
      level.triggers.flatMap((trigger) =>
        trigger.kind === "route" ? [trigger.crossingZ] : [],
      ),
    );
    for (const zone of level.zones) {
      switch (zone.kind) {
        case "hazard":
          if (isWhaleBreakwater(zone)) break;
          if (zone.motion) {
            const boat = new CargoShip(zone);
            this.boats.push(boat);
            this.group.add(boat.group);
            if (zone.id === "cargo-ship" && zone.motion.travel.z === 0)
              this.group.add(patrolRails(zone));
          } else {
            this.group.add(
              drawNet(zone, level, this.netDetail, bayLight.depth),
            );
          }
          break;
        case "warning":
          this.group.add(
            stroke(edges(zone.points), 0.08, 0.37, danger, 6.6, 0.59),
          );
          break;
        case "interference": {
          const art = drawNoise(zone.points);
          if (isCyclicNoise(zone)) this.noise.push({ zone, art });
          this.group.add(art.group);
          break;
        }
        case "current": {
          const { group, reefGuides } = drawCurrent(zone);
          this.group.add(group);
          if (reefGuides) this.reefGuides.push(reefGuides);
          if (hasVisibleDrift(zone)) {
            const drift = drawCurrentDrift(zone, bayLight.depth);
            this.currentDrift.push(drift);
            this.group.add(drift.drift);
          }
          break;
        }
        case "crossCurrent":
          break;
        case "sanctuary":
        case "supply":
        case "checkpoint":
        case "goal": {
          if (zone.id === "watching-rest") break;
          const goal = zone.kind === "goal";
          const kelp = zone.id === "net-kelp";
          const eddy = zone.id === "reef-eddy";
          const offshore =
            zone.id === "offshore-goal" || zone.id === "offshore-rest";
          const group = offshore ? this.offshoreCues : this.group;
          const color = goal || eddy ? foam : kelp ? "#b9dca5" : shallow;
          const path = edges(zone.points).filter(
            ([a, b]) =>
              zone.id !== "junction-rest" || a.z !== b.z || !crossings.has(a.z),
          );
          group.add(
            stroke(
              path,
              0.075,
              goal || eddy ? 0.92 : 0.5,
              color,
              goal ? 0 : 4.7,
              0.81,
            ),
          );
          if (goal || kelp || zone.kind === "sanctuary") {
            const quietWash = fill(
              zone.points,
              0.04,
              new MeshBasicMaterial({
                color,
                side: DoubleSide,
                transparent: true,
                opacity: goal || eddy ? 0.14 : 0.075,
                depthWrite: false,
              }),
            );
            quietWash.renderOrder = -4;
            group.add(quietWash);
          }
          if (kelp) group.add(kelpBeds(zone, bayLight.depth));
          if (zone.id === "offshore-goal") group.add(approachMarks(zone));
          break;
        }
      }
    }
    const offshoreLandmark = (id: string) =>
      id === "surface-here" ||
      id === "offshore-marker" ||
      id.startsWith("watching-");
    const offshoreMarks = level.landmarks.filter(
      ({ id }) =>
        offshoreLandmark(id) &&
        !watchingBoundaryLandmarks.some((boundary) => id === boundary),
    );
    this.group.add(
      drawBeacons(
        level.landmarks.filter(
          ({ id }) => !offshoreLandmark(id) && !isDredgingLandmark(id),
        ),
        level.segments,
      ),
    );
    this.offshoreCues.add(
      drawBeacons(offshoreMarks, level.segments),
      channelArrows(
        level,
        level.landmarks.some(({ id }) => id === "breakwater-preview")
          ? ["surface-here", "offshore-marker"]
          : ["second-checkpoint", "surface-here", "offshore-marker"],
        foam,
      ),
      channelArrows(level, ["second-checkpoint", "breakwater-preview"], foam),
      channelArrows(level, ["breakwater-wide", "breakwater-clear"], "#bdebd8"),
      this.watching.group,
    );
    this.bayBend = channelArrows(
      level,
      ["bay-bend-entry", "bay-turn", "bay-stop", "bay-exit"],
      shallow,
    );
    this.bayDirect = channelArrows(level, ["bay-exit"], foam, level.spawn);
    this.group.add(
      this.offshoreCues,
      this.breakwater.group,
      this.dredging.group,
      drawNetRecovery(level),
      whaleCoast(level, bayLight),
      whaleWaterLandmarks(level, bayLight.depth),
      this.bayBend,
      this.bayDirect,
      bayMouthWash(level),
      channelArrows(
        level,
        ["bay-exit", "ship-bend-in", "ship-bend-out", "ship-dive"],
        foam,
      ),
      channelArrows(level, [
        "ship-west-bend-in",
        "ship-west-bend-out",
        "ship-dive",
      ]),
      channelArrows(level, ["ship-clear", "first-checkpoint"], foam),
      channelArrows(level, ["first-checkpoint", "net-preview-short"], shallow),
      channelArrows(level, ["first-checkpoint", "net-preview-wide"], foam),
      channelArrows(level, [
        "net-preview-short",
        ...netApproaches.short,
        "branch-overlook",
      ]),
      channelArrows(
        level,
        ["net-preview-wide", ...netApproaches.wide, "branch-overlook"],
        "#bdebd8",
      ),
      channelArrows(level, kelpApproaches.short, "#c8dfa5"),
      channelArrows(level, kelpApproaches.arc, "#d9e8c5"),
      channelArrows(level, [
        "quiet-entry",
        "quiet-mid",
        "quiet-arc",
        "quiet-bend",
        "merge-here",
      ]),
      ...routeGates(level),
    );
    const { min, max } = level.bounds;
    const left = { x: min.x, z: max.z };
    const right = { x: max.x, z: max.z };
    this.group.add(
      stroke(
        [
          [min, left],
          [left, right],
          [right, { x: max.x, z: min.z }],
        ],
        0.085,
        0.62,
        "#a8c9cc",
        10,
        0.66,
      ),
    );
  }

  update(
    tick: number,
    gathering: boolean,
    guideBayTurn: boolean,
    settings: CourseArtSettings,
    viewDepth = 0,
  ): void {
    this.breakwater.update(tick, settings, viewDepth);
    this.dredging.update(tick, settings, viewDepth);
    this.watching.update(tick, settings, viewDepth);
    for (const boat of this.boats) boat.update(tick, settings, viewDepth);
    for (const { zone, art } of this.noise) {
      const phase = noisePhase(zone.cycle, tick);
      art.travel.value =
        phase.active && !settings.reduced
          ? phase.elapsedTicks * STEP_SEC * 1.3
          : 0;
      art.wash.opacity = phase.active ? 0.46 : 0.027;
      art.bands.opacity = phase.active ? 1 : 0.085;
      art.boundary.opacity = phase.active ? 0.93 : 0.44;
    }
    for (const { travel, density } of this.currentDrift) {
      travel.value = settings.reduced ? 0 : tick * STEP_SEC * 4.2;
      density.value = Number(!settings.low);
    }
    // Only the nearest layer's arrows should compete with the reef and fish.
    const guideLayer = Math.round(viewDepth);
    for (const guides of this.reefGuides)
      for (const [layer, guide] of guides.entries())
        guide.visible = layer === guideLayer;
    this.netDetail.value = Number(!settings.low);
    this.offshoreCues.visible = !gathering;
    this.bayBend.visible = guideBayTurn;
  }
}
