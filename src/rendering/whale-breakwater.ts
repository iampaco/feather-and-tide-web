import {
  BufferGeometry,
  Color,
  CylinderGeometry,
  DodecahedronGeometry,
  DoubleSide,
  ExtrudeGeometry,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Object3D,
  ShaderMaterial,
  Shape,
  ShapeGeometry,
  Vector2,
} from "three";
import { STEP_SEC } from "../core/clock";
import type { Vec2 } from "../core/math";
import { interiorDepth } from "../levels/geometry";
import type { WhaleLevel } from "../levels/schema";
import type { WhaleCrossflow } from "../levels/whale-crossflow";
import {
  isWhaleBreakwater,
  type WhaleBreakwaterHazard,
} from "../levels/whale-geometry";

const WATERLINE = 0.23;
const LAYER_SPACING = 3.0;
type Line = readonly [Vec2, Vec2];

function footprint(points: readonly Vec2[]): Shape {
  const shape = new Shape();
  for (const [index, point] of points.entries()) {
    if (index === 0) shape.moveTo(point.x, -point.z);
    else shape.lineTo(point.x, -point.z);
  }
  shape.closePath();
  return shape;
}

function bounds(points: readonly Vec2[]) {
  return {
    minX: Math.min(...points.map(({ x }) => x)),
    maxX: Math.max(...points.map(({ x }) => x)),
    minZ: Math.min(...points.map(({ z }) => z)),
    maxZ: Math.max(...points.map(({ z }) => z)),
  };
}

function ribbon(
  lines: readonly Line[],
  width: number,
  color: string,
  opacity: number,
): Mesh {
  const vertices: number[] = [];
  for (const [from, to] of lines) {
    const dx = to.x - from.x;
    const dz = to.z - from.z;
    const scale = width / (2 * Math.hypot(dx, dz));
    const nx = -dz * scale;
    const nz = dx * scale;
    const a = [from.x + nx, 0, from.z + nz];
    const b = [from.x - nx, 0, from.z - nz];
    const c = [to.x + nx, 0, to.z + nz];
    const d = [to.x - nx, 0, to.z - nz];
    vertices.push(...a, ...b, ...c, ...c, ...b, ...d);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(vertices, 3));
  return new Mesh(
    geometry,
    new MeshBasicMaterial({
      color,
      transparent: true,
      opacity,
      side: DoubleSide,
      depthWrite: false,
    }),
  );
}

function perimeter(points: readonly Vec2[]): Line[] {
  return points.slice(1).flatMap((to, index) => {
    const from = points[index];
    return from ? [[from, to] as const] : [];
  });
}

function drawBreakwater(hazard: WhaleBreakwaterHazard): Group {
  const group = new Group();
  group.name = hazard.id;
  const geometry = new ExtrudeGeometry(footprint(hazard.points), {
    depth: 15,
    bevelEnabled: false,
    steps: 1,
  }).rotateX(-Math.PI / 2);
  const vertices = geometry.getAttribute("position");
  const stone = new Color("#7f9696");
  const submerged = new Color("#3d626b");
  const tint = new Color();
  const colors: number[] = [];
  for (let index = 0; index < vertices.count; index++) {
    const depth = vertices.getY(index) / 15;
    tint.copy(submerged).lerp(stone, Math.max(0, Math.min(1, depth)));
    tint.toArray(colors, index * 3);
  }
  geometry.setAttribute("color", new Float32BufferAttribute(colors, 3));
  const body = new Mesh(
    geometry,
    new MeshStandardMaterial({
      roughness: 0.96,
      flatShading: true,
      vertexColors: true,
    }),
  );
  body.position.y = -13.05;
  body.name = "Breakwater footprint";
  const boundary = ribbon(perimeter(hazard.points), 0.6, "#ecf1d8", 0.75);
  boundary.position.y = WATERLINE;
  boundary.name = "Breakwater waterline";
  group.add(body, boundary);

  const extent = bounds(hazard.points);
  const stones: Vec2[] = [];
  for (let z = extent.minZ + 4; z < extent.maxZ; z += 3.7) {
    for (let x = extent.minX + 4; x < extent.maxX; x += 4.4) {
      const center = { x: x + Math.sin(z * 0.92) * 1.4, z };
      if (interiorDepth(hazard.points, center) > 3.65) stones.push(center);
    }
  }
  const rockwork = new InstancedMesh(
    new DodecahedronGeometry(1, 0),
    new MeshStandardMaterial({ roughness: 0.97, flatShading: true }),
    stones.length,
  );
  const transform = new Object3D();
  const warm = new Color("#b8b3a0");
  const cold = new Color("#718c93");
  for (const [index, pos] of stones.entries()) {
    const variation = Math.sin(index * 4.7);
    transform.position.set(pos.x, 2.0 + variation * 0.18, pos.z);
    transform.rotation.set(0.27, index * 2.399, variation * 0.43);
    transform.scale.set(3.05, 1.45 + variation * 0.3, 2.63);
    transform.updateMatrix();
    rockwork.setMatrixAt(index, transform.matrix);
    rockwork.setColorAt(
      index,
      tint.copy(cold).lerp(warm, 0.48 + variation * 0.36),
    );
  }
  group.add(rockwork);

  const tip = hazard.points.find(({ x }) => x === extent.maxX);
  if (tip) {
    const x = tip.x - 6.3;
    const z = tip.z - 3.8;
    if (interiorDepth(hazard.points, { x, z }) > 2.05) {
      const paint = new MeshStandardMaterial({
        color: "#ede1cf",
        roughness: 0.89,
      });
      const red = new MeshStandardMaterial({
        color: "#a45e53",
        roughness: 0.86,
      });
      const beacon = new Group();
      beacon.name = "Stone pier marker";
      beacon.position.set(x, 0, z);
      const foot = new Mesh(new CylinderGeometry(1.45, 1.8, 0.85, 8), red);
      foot.position.y = 2.7;
      const column = new Mesh(new CylinderGeometry(0.81, 1.18, 3.9, 9), paint);
      column.position.y = 4.83;
      const lantern = new Mesh(new CylinderGeometry(0.92, 0.92, 0.88, 8), red);
      lantern.position.y = 6.95;
      const cap = new Mesh(new CylinderGeometry(0.14, 1.14, 0.7, 8), paint);
      cap.position.y = 7.68;
      beacon.add(foot, column, lantern, cap);
      group.add(beacon);
    }
  }
  return group;
}

function drawCrossflow(zone: WhaleCrossflow) {
  const surface = new Group();
  surface.name = zone.id;
  const speed = Math.hypot(zone.velocity.x, zone.velocity.z);
  const direction = new Vector2(
    zone.velocity.x / speed,
    zone.velocity.z / speed,
  );
  const extent = bounds(zone.points);
  const arrows: Line[] = [];
  for (let z = extent.minZ + 7; z < extent.maxZ - 3; z += 12) {
    for (let x = extent.minX + 7; x < extent.maxX - 2; x += 13) {
      const center = { x, z };
      if (interiorDepth(zone.points, center) < 4.1) continue;
      const tip = { x: x + direction.x * 2.1, z: z + direction.y * 2.1 };
      arrows.push([
        { x: x - direction.x * 3.5, z: z - direction.y * 3.5 },
        tip,
      ]);
      for (const side of [-1, 1])
        arrows.push([
          {
            x: x - direction.x * 0.2 - direction.y * side * 1.8,
            z: z - direction.y * 0.2 + direction.x * side * 1.8,
          },
          tip,
        ]);
    }
  }
  const washGeometry = new ShapeGeometry(footprint(zone.points)).rotateX(
    -Math.PI / 2,
  );
  const travel = { value: 0 };
  const density = { value: 1 };
  const wash = new Mesh(
    washGeometry,
    new ShaderMaterial({
      uniforms: { direction: { value: direction }, travel, density },
      transparent: true,
      depthWrite: false,
      side: DoubleSide,
      vertexShader: `
        varying vec2 water;
        varying float distanceToView;
        void main() {
          water = position.xz;
          vec4 view = modelViewMatrix * vec4(position, 1.0);
          distanceToView = -view.z;
          gl_Position = projectionMatrix * view;
        }
      `,
      fragmentShader: `
        uniform vec2 direction;
        uniform float travel;
        uniform float density;
        varying vec2 water;
        varying float distanceToView;
        void main() {
          float across = dot(water, vec2(-direction.y, direction.x)) / 1.75;
          float row = floor(across);
          float along = (dot(water, direction) - travel) / 8.7;
          float drift = fract(along + row * 0.618);
          float stroke = smoothstep(0.1, 0.26, drift) *
            (1.0 - smoothstep(0.44, 0.65, drift));
          float bristle = 1.0 - smoothstep(0.04, 0.18, abs(fract(across) - 0.5));
          float thread = stroke * bristle * density;
          float visible = 1.0 - smoothstep(89.0, 163.0, distanceToView);
          gl_FragColor = vec4(
            mix(vec3(0.20, 0.53, 0.52), vec3(0.73, 0.93, 0.84), thread),
            (0.23 + thread * 0.55) * visible
          );
          #include <colorspace_fragment>
        }
      `,
    }),
  );
  wash.renderOrder = -4;
  wash.name = "Breakwater foam";
  const rim = ribbon(perimeter(zone.points), 0.41, "#76c8c0", 0.8);
  const marks = ribbon(arrows, 0.47, "#f5f5d7", 0.92);
  rim.position.y = 0.008;
  marks.position.y = 0.015;
  marks.name = "Breakwater flow arrows";
  rim.renderOrder = 1;
  marks.renderOrder = 2;
  surface.add(wash, rim, marks);
  return { surface, speed, travel, density };
}

export class WhaleBreakwater {
  readonly group = new Group();
  private readonly flows: ReturnType<typeof drawCrossflow>[] = [];

  constructor(level: WhaleLevel) {
    this.group.name = "Breakwater and crossing currents";
    for (const zone of level.zones) {
      if (isWhaleBreakwater(zone)) this.group.add(drawBreakwater(zone));
      if (zone.kind === "crossCurrent") {
        const flow = drawCrossflow(zone);
        this.flows.push(flow);
        this.group.add(flow.surface);
      }
    }
  }

  update(
    tick: number,
    settings: { readonly low: boolean; readonly reduced: boolean },
    viewDepth: number,
  ): void {
    for (const { surface, speed, travel, density } of this.flows) {
      surface.position.y = WATERLINE - Math.round(viewDepth) * LAYER_SPACING;
      travel.value = settings.reduced ? 0 : tick * STEP_SEC * speed;
      density.value = settings.low ? 0.63 : 1;
    }
  }
}
