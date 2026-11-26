import {
  BoxGeometry,
  BufferGeometry,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  Mesh,
  MeshLambertMaterial,
  Object3D,
  ShaderMaterial,
  SphereGeometry,
  Vector2,
  Vector3,
  type ShapeGeometry,
} from "three";
import type { Vec2 } from "../core/math";
import { contains } from "../levels/geometry";

interface Edge {
  readonly start: Vec2;
  readonly end: Vec2;
  readonly length: number;
  readonly direction: Vec2;
  readonly inward: Vec2;
  readonly bays: number;
}

function at(edge: Edge, along: number, inset: number, y: number): Vector3 {
  return new Vector3(
    edge.start.x + edge.direction.x * along + edge.inward.x * inset,
    y,
    edge.start.z + edge.direction.z * along + edge.inward.z * inset,
  );
}

const timber = "#ac7752";
const metal = "#3e554e";
const trim = "#826850";
const stone = "#9c9c89";
const terrace = [0.42, 0.56] as const;

function glazing(edges: readonly Edge[], deck: number, eave: number): Mesh {
  const positions: number[] = [];
  const uv: number[] = [];
  for (const edge of edges) {
    const { start: a, end: b, bays } = edge;
    positions.push(
      a.x,
      deck,
      a.z,
      b.x,
      deck,
      b.z,
      b.x,
      eave,
      b.z,
      a.x,
      deck,
      a.z,
      b.x,
      eave,
      b.z,
      a.x,
      eave,
      a.z,
    );
    uv.push(
      0,
      0,
      bays,
      0,
      bays,
      eave - deck,
      0,
      0,
      bays,
      eave - deck,
      0,
      eave - deck,
    );
  }
  const panes = new Mesh(
    new BufferGeometry()
      .setAttribute("position", new Float32BufferAttribute(positions, 3))
      .setAttribute("uv", new Float32BufferAttribute(uv, 2)),
    new ShaderMaterial({
      side: DoubleSide,
      transparent: true,
      depthWrite: false,
      forceSinglePass: true,
      vertexShader: `
        varying vec2 pane;
        varying vec3 viewPosition;
        void main() {
          pane = uv;
          vec4 view = modelViewMatrix * vec4(position, 1.0);
          viewPosition = view.xyz;
          gl_Position = projectionMatrix * view;
        }
      `,
      fragmentShader: `
        varying vec2 pane;
        varying vec3 viewPosition;
        void main() {
          vec3 normal = normalize(cross(dFdx(viewPosition), dFdy(viewPosition)));
          float reflection = pow(1.0 - abs(normal.z), 2.3);
          float heightMix = smoothstep(0.1, 5.8, pane.y);
          float panel = fract(sin(floor(pane.x) * 17.81 + 1.86) * 437.7);
          float sweep = sin(pane.y * 0.65 + pane.x * 0.47);
          float sheen = smoothstep(0.63, 0.98, sweep) * 0.17;
          vec3 river = vec3(0.18, 0.32, 0.30);
          vec3 sky = vec3(0.56, 0.68, 0.64);
          vec3 color = mix(river, sky, heightMix * 0.62 + reflection * 0.27 + panel * 0.08);
          color += sheen;

          // The staggered marks stay legible when the individual mullions are small.
          float row = floor(pane.y * 2.6);
          vec2 cell = vec2(pane.x * 5.0 + mod(row, 2.0) * 0.5, pane.y * 2.6);
          float dotDistance = length(fract(cell) - 0.5);
          float antialias = clamp(fwidth(dotDistance), 0.035, 0.14);
          float dotMask = 1.0 - smoothstep(0.18 - antialias, 0.18 + antialias, dotDistance);
          dotMask *= step(0.75, pane.y) * step(pane.y, 4.95);
          gl_FragColor = vec4(
            mix(color, vec3(0.96, 0.91, 0.76), dotMask),
            mix(0.34 + reflection * 0.30 + sheen * 0.45, 0.93, dotMask)
          );
          #include <colorspace_fragment>
        }
      `,
    }),
  );
  panes.name = "marked-glass-panes";
  panes.renderOrder = 6;
  return panes;
}

function plankDeck(
  geometry: ShapeGeometry,
  edge: Edge,
  y: number,
  canopyDepth: number,
): Mesh {
  const deck = new Mesh(
    geometry,
    new ShaderMaterial({
      uniforms: {
        axis: { value: new Vector2(edge.direction.x, edge.direction.z) },
        inward: { value: new Vector2(edge.inward.x, edge.inward.z) },
        origin: { value: new Vector2(edge.start.x, edge.start.z) },
        canopyDepth: { value: canopyDepth },
        inverseLength: { value: 1 / edge.length },
        terrace: { value: new Vector2(...terrace) },
      },
      vertexShader: `
        uniform vec2 axis;
        uniform vec2 inward, origin;
        varying vec2 floorboard;
        varying vec2 deckPosition;
        void main() {
          floorboard = vec2(dot(position.xz, axis), dot(position.xz, vec2(-axis.y, axis.x)));
          vec2 local = position.xz - origin;
          deckPosition = vec2(dot(local, axis), dot(local, inward));
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec2 floorboard;
        varying vec2 deckPosition;
        uniform float canopyDepth, inverseLength;
        uniform vec2 terrace;
        void main() {
          float board = floorboard.y / 0.38;
          float row = floor(board);
          float lengthwise = floorboard.x / 4.7 + row * 0.447;
          float variation = fract(sin(dot(vec2(row, floor(lengthwise)), vec2(13.7, 5.2))) * 192.8);
          float longSeam = smoothstep(0.42, 0.50, abs(fract(board) - 0.5));
          float endSeam = smoothstep(0.475, 0.50, abs(fract(lengthwise) - 0.5));
          float grain = sin(floorboard.y * 45.0 + sin(floorboard.x * 2.3)) * 0.022;
          vec3 wood = mix(vec3(0.28, 0.16, 0.09), vec3(0.51, 0.32, 0.18), variation);
          float along = deckPosition.x * inverseLength;
          float openAir = smoothstep(terrace.x, terrace.x + 0.02, along) *
                          (1.0 - smoothstep(terrace.y - 0.02, terrace.y, along));
          float shade = canopyDepth > 0.01 ? smoothstep(
            canopyDepth * 0.24, canopyDepth * 0.48, deckPosition.y
          ) * 0.23 * (1.0 - openAir) : 0.0;
          gl_FragColor = vec4((wood + grain) * (1.0 - 0.26 * max(longSeam, endSeam) - shade), 1.0);
          #include <colorspace_fragment>
        }
      `,
    }),
  );
  deck.name = "timber-plank-deck";
  deck.position.y = y;
  return deck;
}

export function buildObservationGallery(
  points: readonly Vec2[],
  footprint: ShapeGeometry,
  height: (x: number, z: number) => number,
  low: boolean,
): Group {
  const gallery = new Group();
  gallery.name = "observation-gallery";
  const winding = points.slice(1).reduce((sum, point, index) => {
    const previous = points[index];
    return previous ? sum + previous.x * point.z - point.x * previous.z : sum;
  }, 0);
  const edges: Edge[] = [];
  let deck = 0.91;
  for (const [index, end] of points.slice(1).entries()) {
    const start = points[index];
    if (!start) continue;
    const length = Math.hypot(end.x - start.x, end.z - start.z);
    const direction = {
      x: (end.x - start.x) / length,
      z: (end.z - start.z) / length,
    };
    const inward = {
      x: -direction.z * Math.sign(winding),
      z: direction.x * Math.sign(winding),
    };
    const edge = {
      start,
      end,
      length,
      direction,
      inward,
      bays: Math.max(1, Math.round(length / 3.25)),
    };
    edges.push(edge);

    const steps = Math.ceil(length / 2);
    for (let step = 0; step <= steps; step++) {
      const p = at(edge, (length * step) / steps, 0, 0);
      deck = Math.max(deck, height(p.x, p.z) + 0.73);
    }
  }
  const longEdge = edges.reduce<Edge | undefined>(
    (longest, edge) =>
      !longest || edge.length > longest.length ? edge : longest,
    undefined,
  );
  if (!longEdge) return gallery;
  const eave = deck + 5.49;
  gallery.add(glazing(edges, deck, eave));

  const stamp = new Object3D();
  const parts: { stamp: Object3D["matrix"]; color: Color }[] = [];
  function box(
    position: Vector3,
    width: number,
    tall: number,
    depth: number,
    yaw: number,
    color: string,
    tilt = 0,
  ): void {
    stamp.position.copy(position);
    stamp.scale.set(width, tall, depth);
    stamp.rotation.set(tilt, yaw, 0, "YXZ");
    stamp.updateMatrix();
    parts.push({ stamp: stamp.matrix.clone(), color: new Color(color) });
  }

  for (const edge of edges) {
    const yaw = -Math.atan2(edge.direction.z, edge.direction.x);
    const beam = (
      y: number,
      inset: number,
      tall: number,
      wide: number,
      color: string,
    ) =>
      box(
        at(edge, edge.length / 2, inset, y),
        edge.length,
        tall,
        wide,
        yaw,
        color,
      );
    beam(deck - 0.13, 0.2, 0.27, 0.4, "#897052");
    beam(deck - 0.39, 0.23, 0.29, 0.45, "#5f5346");
    beam(deck + 0.04, 0.22, 0.09, 0.43, "#c1a077");
    beam(deck + 0.25, 0.13, 0.4, 0.26, metal);
    beam(eave - 0.91, 0.15, 0.12, 0.21, metal);
    beam(eave - 0.11, 0.17, 0.28, 0.34, metal);
    beam(eave + 0.07, 0.22, 0.08, 0.44, trim);
    beam(deck + 1.5, 0.53, 0.16, 0.28, timber);
    beam(deck + 0.65, 0.53, 0.1, 0.13, metal);
    const pitch = edge.length / edge.bays;
    for (let i = 0; i <= edge.bays; i++) {
      // End posts meet just inside the perimeter, keeping the water passage open.
      const along = Math.min(edge.length - 0.16, Math.max(0.16, i * pitch));
      box(
        at(edge, along, 0.17, (deck + eave) / 2),
        0.21,
        eave - deck,
        0.29,
        yaw,
        metal,
      );
      box(at(edge, along, 0.53, deck + 0.77), 0.15, 1.43, 0.15, yaw, metal);
      if (!low && i < edge.bays)
        box(
          at(edge, (i + 0.5) * pitch, 0.53, deck + 0.97),
          0.08,
          0.98,
          0.09,
          yaw,
          metal,
        );
    }
  }

  const yaw = -Math.atan2(longEdge.direction.z, longEdge.direction.x);
  // Size the canopy and furnishings from the usable depth behind the long facade.
  const depth = Math.max(
    ...points.map(
      (p) =>
        (p.x - longEdge.start.x) * longEdge.inward.x +
        (p.z - longEdge.start.z) * longEdge.inward.z,
    ),
  );
  const length = longEdge.length;
  const roofInset = depth * 0.61;
  const roofWidth = depth * 0.68;
  const roofFits =
    length > 2.8 &&
    roofWidth > 0.5 &&
    [0.55, length - 0.55].every((along) =>
      [roofInset - roofWidth / 2, roofInset + roofWidth / 2].every((inset) =>
        contains(points, at(longEdge, along, inset, 0)),
      ),
    );
  gallery.add(plankDeck(footprint, longEdge, deck, roofFits ? depth : 0));
  if (roofFits) {
    // Two covered portions leave an open terrace behind the continuous glazing.
    const roofSlope = 0.24;
    const halfWidth = roofWidth / 2;
    const slopeWidth = halfWidth / Math.cos(roofSlope);
    const slopeY = eave + 0.24 + (Math.tan(roofSlope) * halfWidth) / 2;
    const roofTints = ["#80938a", "#8d9b8d", "#758b84"] as const;
    for (const [start, end] of [
      [0.55, length * terrace[0]],
      [length * terrace[1], length - 0.55],
    ] as const) {
      const span = end - start;
      const center = (start + end) / 2;
      const bays = Math.max(1, Math.round(span / 3));
      for (const side of [-1, 1]) {
        const pitch = side * Math.sign(winding) * roofSlope;
        const inset = roofInset + (side * halfWidth) / 2;
        box(
          at(longEdge, center, inset, slopeY),
          span,
          0.19,
          slopeWidth,
          yaw,
          side < 0 ? "#829589" : "#71877f",
          pitch,
        );
        for (let i = 0; i <= bays; i++) {
          box(
            at(
              longEdge,
              start + 0.08 + ((span - 0.16) * i) / bays,
              inset,
              slopeY + 0.11,
            ),
            low ? 0.125 : 0.1,
            0.1,
            slopeWidth - 0.14,
            yaw,
            roofTints[i % roofTints.length] ?? roofTints[0],
            pitch,
          );
        }
        box(
          at(
            longEdge,
            center,
            roofInset + side * (halfWidth - 0.11),
            eave + 0.24,
          ),
          span,
          0.17,
          0.22,
          yaw,
          metal,
        );
      }
      box(
        at(longEdge, center, roofInset, 2 * slopeY - eave - 0.13),
        span,
        0.145,
        0.24,
        yaw,
        "#566f67",
      );
    }
    for (const fraction of [0.1, 0.37, 0.63, 0.9]) {
      box(
        at(
          longEdge,
          length * fraction,
          roofInset - roofWidth * 0.47,
          (deck + eave) / 2,
        ),
        0.29,
        eave - deck,
        0.26,
        yaw,
        trim,
      );
    }
  }

  // Separate stone feet and timber bents reveal the level deck above the uneven bank.
  const supports = Math.max(2, Math.ceil(length / 7.3));
  for (let i = 0; i < supports; i++) {
    const along = 1.4 + ((length - 2.8) * i) / (supports - 1);
    for (const inset of [0.72, depth - 0.72]) {
      const p = at(longEdge, along, inset, deck - 0.28);
      if (!contains(points, p)) continue;
      const ground = height(p.x, p.z);
      const base = Math.min(Math.max(-0.32, ground - 0.13), p.y - 0.36);
      const cap = Math.min(base + 0.42, p.y - 0.18);
      const pierColor = ground < 0.05 ? "#747f75" : stone;
      box(
        p.clone().setY((cap + base) / 2),
        1.02,
        cap - base,
        1.06,
        yaw,
        pierColor,
      );
      box(p.clone().setY(cap), 0.83, 0.13, 0.85, yaw, stone);
      box(p.clone().setY((cap + p.y) / 2), 0.58, p.y - cap, 0.6, yaw, trim);
    }
  }

  for (const fraction of [0.24, 0.74]) {
    const along = length * fraction;
    const inset = depth * 0.37;
    if (!contains(points, at(longEdge, along, inset, 0))) continue;
    box(at(longEdge, along, inset, deck + 0.46), 2.65, 0.16, 0.55, yaw, timber);
    box(
      at(longEdge, along, inset + 0.21, deck + 0.76),
      2.65,
      0.29,
      0.12,
      yaw,
      timber,
    );
    for (const side of [-1, 1])
      box(
        at(longEdge, along + side * 0.9, inset, deck + 0.22),
        0.18,
        0.44,
        0.4,
        yaw,
        metal,
      );
  }
  const structure = new InstancedMesh(
    new BoxGeometry(1, 1, 1),
    new MeshLambertMaterial({ color: "white" }),
    parts.length,
  );
  structure.name = "gallery-structure";
  parts.forEach(({ stamp, color }, index) => {
    structure.setMatrixAt(index, stamp);
    structure.setColorAt(index, color);
  });
  gallery.add(structure);

  const guests = [
    { fraction: 0.37, color: "#b4674e" },
    { fraction: 0.44, color: "#48716e" },
    { fraction: 0.66, color: "#be9355" },
  ].filter(({ fraction }) =>
    contains(points, at(longEdge, length * fraction, depth * 0.27, 0)),
  );
  const visitors = new InstancedMesh(
    new SphereGeometry(1, 8, 6),
    new MeshLambertMaterial({ color: "white" }),
    guests.length * 2,
  );
  visitors.name = "gallery-visitors";
  stamp.rotation.set(0, yaw, 0);
  for (const [i, guest] of guests.entries()) {
    stamp.position.copy(
      at(longEdge, length * guest.fraction, depth * 0.27, deck + 0.83),
    );
    stamp.scale.set(0.33, 0.79, 0.25);
    stamp.updateMatrix();
    visitors.setMatrixAt(i * 2, stamp.matrix);
    visitors.setColorAt(i * 2, new Color(guest.color));
    stamp.position.y = deck + 1.79;
    stamp.scale.setScalar(0.24);
    stamp.updateMatrix();
    visitors.setMatrixAt(i * 2 + 1, stamp.matrix);
    visitors.setColorAt(i * 2 + 1, new Color("#b78b69"));
  }
  gallery.add(visitors);
  return gallery;
}
