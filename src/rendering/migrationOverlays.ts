import {
  Box3,
  BufferGeometry,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  Mesh,
  ShaderMaterial,
  Shape,
  ShapeGeometry,
  Vector2,
} from "three";
import type { LevelSchema, Zone } from "../levels/schema";
import { tailwindCourseZones } from "../levels/tailwind-practice";
import { buildObservationGallery } from "./observationGallery";

type GroundHeight = (x: number, z: number) => number;

function zoneSurface(zone: Zone): ShapeGeometry {
  const shape = new Shape();
  zone.points.forEach(({ x, z }, index) => {
    if (index === 0) shape.moveTo(x, -z);
    else shape.lineTo(x, -z);
  });
  return new ShapeGeometry(shape).rotateX(-Math.PI / 2);
}

const groundVertex = `
  varying vec2 ground;
  void main() {
    ground = position.xz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

function hazardInk(zone: Zone, height: GroundHeight): Group {
  const group = new Group();
  group.name = zone.id;
  const sweep = zone.id === "sweep";
  const glass = zone.kind === "hazard" && zone.appearance === "glass";
  const ink = new Color(sweep ? "#8e4836" : "#6d5a63");
  const paleInk = new Color(sweep ? "#f3c394" : "#e5cfb2");
  const wash = new Mesh(
    zoneSurface(zone),
    new ShaderMaterial({
      uniforms: { ink: { value: ink } },
      transparent: true,
      depthWrite: false,
      side: DoubleSide,
      vertexShader: groundVertex,
      fragmentShader: `
        uniform vec3 ink;
        varying vec2 ground;
        void main() {
          float phase = (ground.x - ground.y * 0.76) / 5.2;
          float band = abs(fract(phase) - 0.5);
          float pixel = clamp(fwidth(phase), 0.007, 0.085);
          float stripe = 1.0 - smoothstep(0.11 - pixel, 0.11 + pixel, band);
          gl_FragColor = vec4(ink, 0.095 + stripe * 0.26);
          #include <colorspace_fragment>
        }
      `,
    }),
  );
  wash.name = "sweep-hatching";
  wash.position.y = 0.11;
  wash.renderOrder = 4;

  // Subdivide source edges so the stroke can follow the terrain without
  // smoothing away any of the polygon's corners.
  const path = zone.points.slice(1).flatMap((b, index) => {
    const a = zone.points[index];
    if (!a) return [];
    const steps = Math.ceil(Math.hypot(b.x - a.x, b.z - a.z) / 1.4);
    return Array.from({ length: steps }, (_, i) => ({
      x: a.x + ((b.x - a.x) * i) / steps,
      z: a.z + ((b.z - a.z) * i) / steps,
    }));
  });
  const positions: number[] = [];
  const edges: number[] = [];
  const indices: number[] = [];
  const width = sweep ? 0.55 : 0.41;
  path.forEach(({ x, z }, i) => {
    const before = path[(i + path.length - 1) % path.length];
    const after = path[(i + 1) % path.length];
    if (!before || !after) return;
    const dx = after.x - before.x;
    const dz = after.z - before.z;
    const length = Math.hypot(dx, dz);
    const ox = (dz * width) / length;
    const oz = (-dx * width) / length;
    const y = Math.max(0, height(x, z)) + 0.16;
    positions.push(x - ox, y, z - oz, x + ox, y, z + oz);
    edges.push(-1, 1);
    const a = i * 2;
    const b = ((i + 1) % path.length) * 2;
    indices.push(a, a + 1, b, a + 1, b + 1, b);
  });
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("edge", new Float32BufferAttribute(edges, 1))
    .setIndex(indices);
  const outline = new Mesh(
    geometry,
    new ShaderMaterial({
      uniforms: { ink: { value: ink }, paleInk: { value: paleInk } },
      transparent: true,
      depthTest: glass,
      depthWrite: false,
      side: DoubleSide,
      vertexShader: `
        attribute float edge;
        varying float across;
        void main() {
          across = edge;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 ink;
        uniform vec3 paleInk;
        varying float across;
        void main() {
          float edge = abs(across);
          vec3 color = mix(ink, paleInk, smoothstep(0.45, 0.65, edge));
          gl_FragColor = vec4(color, 0.96 * (1.0 - smoothstep(0.76, 1.0, edge)));
          #include <colorspace_fragment>
        }
      `,
    }),
  );
  outline.name = "outline";
  outline.renderOrder = glass ? 5 : 7;
  group.add(wash, outline);
  return group;
}

function shelteredWater(zone: Zone): Mesh<ShapeGeometry, ShaderMaterial> {
  const xs = zone.points.map(({ x }) => x);
  const zs = zone.points.map(({ z }) => z);
  const min = new Vector2(Math.min(...xs), Math.min(...zs));
  const max = new Vector2(Math.max(...xs), Math.max(...zs));
  const center = min.clone().add(max).multiplyScalar(0.5);
  const radius = max.clone().sub(min).multiplyScalar(0.5);
  const marker = new Mesh(
    zoneSurface(zone),
    new ShaderMaterial({
      uniforms: {
        center: { value: center },
        radius: { value: radius },
        tint: {
          value: new Color(zone.kind === "goal" ? "#fddea0" : "#f7db9e"),
        },
        visibility: { value: 1 },
      },
      transparent: true,
      depthWrite: false,
      side: DoubleSide,
      vertexShader: groundVertex,
      fragmentShader: `
        uniform vec2 center;
        uniform vec2 radius;
        uniform vec3 tint;
        uniform float visibility;
        varying vec2 ground;
        void main() {
          vec2 p = (ground - center) / radius;
          p.x += 0.10 * sin(p.y * 4.0);
          float veil = 1.0 - smoothstep(0.2, 0.96, length(p));
          float brush = 0.55 + 0.45 * sin(ground.y * 1.3 + sin(ground.x * 0.22) * 1.1);
          float alpha = veil * (0.075 + brush * 0.065);
          gl_FragColor = vec4(tint, alpha * visibility);
          #include <colorspace_fragment>
        }
      `,
    }),
  );
  marker.name = zone.id;
  marker.position.y = 0.066;
  return marker;
}

const tailwindFragment = `
  uniform vec2 direction, entry;
  uniform float reachEnd;
  varying vec2 ground;

  float seed(vec2 cell) {
    return fract(sin(dot(cell, vec2(32.957, 48.137))) * 17315.71);
  }

  void main() {
    vec2 across = vec2(-direction.y, direction.x);
    vec2 aligned = vec2(dot(ground, across), dot(ground, direction));
    float lane = floor(aligned.x / 7.3);
    vec2 grid = vec2(aligned.x / 7.3, aligned.y / 17.4 + lane * 0.43);
    float variation = seed(floor(grid));
    vec2 within = fract(grid);
    float streak = within.y;
    float tip = 0.65 + variation * 0.22;
    float lengthwise = smoothstep(0.07 + variation * 0.29, 0.51, streak) *
                       (1.0 - smoothstep(tip - 0.18, tip, streak));
    float curve = 0.42 + 0.19 * variation + 0.061 * sin(streak * 3.14);
    float width = (0.025 + 0.072 * streak) * sqrt(lengthwise);
    float body = 1.0 - smoothstep(width * 0.23, width + 0.01, abs(within.x - curve));
    float edge = smoothstep(entry.y - 5.0, entry.y + 1.0, ground.y) *
                 (1.0 - smoothstep(reachEnd - 4.0, reachEnd, ground.y));
    float brush = body * lengthwise * mix(0.13, 0.35, variation) * edge;

    // The first few metres carry explicit direction. Across the interior the
    // tapered, staggered stroke field keeps the flock easier to read.
    float column = floor((ground.x - entry.x) / 12.0 + 0.5);
    vec2 offset = ground - entry - vec2(column * 12.0, 0.0);
    vec2 mark = vec2(abs(dot(offset, across)), dot(offset, direction));
    float lineWidth = clamp(fwidth(mark.y) + fwidth(mark.x), 0.015, 0.16);
    float head = 1.0 - smoothstep(0.12, 0.28 + lineWidth,
                                  abs(mark.y - (1.35 - mark.x * 0.72)));
    head *= 1.0 - smoothstep(1.25, 1.62, mark.x);
    float shaft = (1.0 - smoothstep(0.10, 0.25 + lineWidth, mark.x)) *
                  smoothstep(-2.3, -0.65, mark.y) *
                  (1.0 - smoothstep(0.82, 1.39, mark.y));
    float arrow = max(head, shaft * 0.73);
    vec3 pigment = mix(vec3(0.61, 0.75, 0.63), vec3(0.96, 0.87, 0.66), arrow);
    gl_FragColor = vec4(pigment, max(brush, arrow * 0.69));
    #include <colorspace_fragment>
  }
`;

export function directionalWind(
  zone: Extract<Zone, { kind: "interference" }>,
): Mesh {
  const flow = zone.wind ?? { x: 0, z: 0 };
  const direction = new Vector2(flow.x, flow.z).normalize();
  const tailwind = tailwindCourseZones.includes(zone.id);
  const start = Math.min(...zone.points.map(({ z }) => z));
  const entranceXs = zone.points
    .filter(({ z }) => z === start)
    .map(({ x }) => x);
  const entry = new Vector2(
    (Math.min(...entranceXs) + Math.max(...entranceXs)) * 0.5,
    start + 5,
  );
  const strokes = new Mesh(
    zoneSurface(zone),
    new ShaderMaterial({
      uniforms: {
        direction: { value: direction },
        entry: { value: entry },
        reachEnd: { value: Math.max(...zone.points.map(({ z }) => z)) },
      },
      transparent: true,
      depthWrite: false,
      side: DoubleSide,
      vertexShader: groundVertex,
      fragmentShader: tailwind
        ? tailwindFragment
        : `
        uniform vec2 direction;
        varying vec2 ground;
        void main() {
          vec2 across = vec2(-direction.y, direction.x);
          float lane = dot(ground, across) / 4.2;
          float row = floor(lane);
          float width = abs(fract(lane) - 0.5);
          float along = fract(dot(ground, direction) / 8.6 + row * 0.37);
          float wing = abs(along - (0.72 - width * 0.82));
          float chevron = (1.0 - smoothstep(0.022, 0.057, wing)) *
                          (1.0 - smoothstep(0.20, 0.26, width));
          float wake = (1.0 - smoothstep(0.015, 0.07, width)) *
                       smoothstep(0.15, 0.33, along) * (1.0 - smoothstep(0.62, 0.72, along));
          vec3 tint = mix(vec3(0.21, 0.34, 0.31), vec3(0.99, 0.92, 0.73), chevron);
          gl_FragColor = vec4(tint, max(chevron * 0.78, wake * 0.24));
          #include <colorspace_fragment>
        }
      `,
    }),
  );
  strokes.name = zone.id;
  strokes.position.y = 0.52;
  strokes.renderOrder = 5;
  return strokes;
}

export function buildMigrationOverlays(
  level: LevelSchema,
  height: GroundHeight,
  low = false,
): {
  readonly group: Group;
  readonly cameraObstacles: readonly Box3[];
  setLanding(amount: number): void;
} {
  const group = new Group();
  const cameraObstacles: Box3[] = [];
  let goal: Mesh<ShapeGeometry, ShaderMaterial> | undefined;
  for (const zone of level.zones) {
    if (zone.kind === "hazard") {
      const boundary = hazardInk(zone, height);
      if (zone.appearance === "glass") {
        const gallery = buildObservationGallery(
          zone.points,
          zoneSurface(zone),
          height,
          low,
        );
        cameraObstacles.push(
          new Box3().setFromObject(gallery).expandByScalar(0.35),
        );
        boundary.add(gallery);
      }
      group.add(boundary);
    }
    if (
      zone.kind === "interference" &&
      !zone.gust &&
      zone.id !== "return-lee" &&
      zone.wind &&
      (zone.wind.x || zone.wind.z)
    )
      group.add(directionalWind(zone));
    if (zone.kind === "supply" || zone.kind === "goal") {
      const marker = shelteredWater(zone);
      if (zone.kind === "goal") goal = marker;
      group.add(marker);
    }
  }
  return {
    group,
    cameraObstacles,
    setLanding(amount: number): void {
      const visibility = goal?.material.uniforms.visibility;
      if (visibility) visibility.value = 1 - Math.min(1, amount * 4);
    },
  };
}
