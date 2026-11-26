import {
  BoxGeometry,
  BufferGeometry,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  IcosahedronGeometry,
  InstancedMesh,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  Object3D,
} from "three";
import { lerp, type Vec2 } from "../core/math";
import { contains, interiorDepth } from "../levels/geometry";
import {
  reindeerFencePassages,
  reindeerShortFenceRunouts,
  type FencePassage,
} from "../levels/reindeer-ground";
export { reindeerFencePassages } from "../levels/reindeer-ground";
import { sampleReindeerDust } from "../simulation/reindeer-dust";
import type { GroundBarrier, ReindeerLevel, Zone } from "../levels/schema";

interface Extent {
  readonly left: number;
  readonly right: number;
  readonly near: number;
  readonly far: number;
}

interface Timber {
  readonly x: number;
  readonly y: number;
  readonly z: number;
  readonly width: number;
  readonly height: number;
  readonly length: number;
  readonly color: string;
  readonly tilt?: number;
}

function extent(points: readonly Vec2[]): Extent {
  return {
    left: Math.min(...points.map(({ x }) => x)),
    right: Math.max(...points.map(({ x }) => x)),
    near: Math.min(...points.map(({ z }) => z)),
    far: Math.max(...points.map(({ z }) => z)),
  };
}

function fenceSpans(level: ReindeerLevel): Extent[] {
  return level.barriers
    .filter(({ kind }) => kind === "fence")
    .map(({ points }) => extent(points))
    .sort((a, b) => a.left - b.left);
}

function timber(name: string, placements: readonly Timber[]): InstancedMesh {
  const geometry = new BoxGeometry(1, 1, 1);
  const normals = geometry.getAttribute("normal");
  const positions = geometry.getAttribute("position");
  const colors: number[] = [];
  for (let i = 0; i < normals.count; i++) {
    const exposed = normals.getY(i) > 0 ? 0.98 : 0.73;
    const grain = 0.08 * positions.getX(i) + 0.06 * positions.getY(i);
    const end = Math.abs(normals.getX(i)) * 0.08;
    const tint = exposed + grain + end;
    colors.push(tint, tint * 0.98, tint * 0.96);
  }
  geometry.setAttribute("color", new Float32BufferAttribute(colors, 3));
  const mesh = new InstancedMesh(
    geometry,
    new MeshLambertMaterial({ vertexColors: true }),
    placements.length,
  );
  const piece = new Object3D();
  const color = new Color();
  for (const [i, placement] of placements.entries()) {
    piece.position.set(placement.x, placement.y, placement.z);
    piece.scale.set(placement.width, placement.height, placement.length);
    piece.rotation.z = placement.tilt ?? 0;
    piece.updateMatrix();
    mesh.setMatrixAt(i, piece.matrix);
    mesh.setColorAt(i, color.set(placement.color));
  }
  mesh.name = name;
  return mesh;
}

/** Several feathered watercolor strokes are drawn together on the existing ground plane. */
class GroundWash {
  private readonly positions: number[] = [];
  private readonly colors: number[] = [];
  private readonly indices: number[] = [];

  stroke(
    start: Vec2,
    end: Vec2,
    halfWidth: (t: number) => number,
    pigment: string,
    strength: number,
    ripple: number,
    clip?: readonly Vec2[],
  ): void {
    const rows = Math.max(
      4,
      Math.ceil(Math.hypot(end.x - start.x, end.z - start.z) / 2),
    );
    const first = this.positions.length / 3;
    const color = new Color(pigment);
    const dx = end.x - start.x;
    const dz = end.z - start.z;
    const distance = Math.hypot(dx, dz);
    if (!distance) return;
    const acrossX = dz / distance;
    const acrossZ = -dx / distance;
    for (let row = 0; row <= rows; row++) {
      const t = row / rows;
      const fade =
        MathUtils.smoothstep(t, 0, 0.15) *
        (1 - MathUtils.smoothstep(t, 0.83, 1));
      const feather =
        halfWidth(t) * (0.87 + 0.13 * Math.sin(t * 17.2 + ripple));
      const wobble =
        Math.sin(t * Math.PI) * Math.sin(t * 19 + ripple) * feather * 0.13;
      for (const edge of [-1, -0.57, 0, 0.57, 1]) {
        const span = feather * edge + wobble;
        const point = {
          x: lerp(start.x, end.x, t) + span * acrossX,
          z: lerp(start.z, end.z, t) + span * acrossZ,
        };
        this.positions.push(point.x, 0.022, point.z);
        const ink =
          !clip || contains(clip, point) ? 1 - Math.abs(edge) ** 2 : 0;
        this.colors.push(color.r, color.g, color.b, ink * strength * fade);
      }
      if (!row) continue;
      for (let col = 0; col < 4; col++) {
        const a = first + (row - 1) * 5 + col;
        this.indices.push(a, a + 5, a + 1, a + 1, a + 5, a + 6);
      }
    }
  }

  trail(
    points: readonly Vec2[],
    tracks: readonly {
      readonly offset: number;
      readonly halfWidth: number;
      readonly pigment: string;
      readonly strength: number;
    }[],
  ): void {
    const samples: (Vec2 & { distance: number })[] = [];
    let distance = 0;
    for (let i = 1; i < points.length; i++) {
      const before = points[i - 1];
      const after = points[i];
      if (!before || !after) continue;
      const length = Math.hypot(after.x - before.x, after.z - before.z);
      if (!length) continue;
      const divisions = Math.ceil(length / 1.15);
      for (let step = 0; step < divisions; step++) {
        const t = step / divisions;
        samples.push({
          x: lerp(before.x, after.x, t),
          z: lerp(before.z, after.z, t),
          distance: distance + length * t,
        });
      }
      distance += length;
    }
    const last = points.at(-1);
    if (!last || !samples[0]) return;
    samples.push({ ...last, distance });

    for (const { offset, halfWidth, pigment, strength } of tracks) {
      const first = this.positions.length / 3;
      const color = new Color(pigment);
      for (const [row, point] of samples.entries()) {
        const before = samples[row - 1] ?? point;
        const after = samples[row + 1] ?? point;
        const tangent =
          before.x === after.x && before.z === after.z ? point : before;
        const dx = after.x - tangent.x;
        const dz = after.z - tangent.z;
        const length = Math.hypot(dx, dz);
        const fade = MathUtils.smoothstep(
          Math.min(point.distance, distance - point.distance),
          0,
          9,
        );
        const dryEdge = point.distance * 0.42 + offset;
        const edgeWidth =
          halfWidth *
          (0.92 + 0.13 * Math.sin(dryEdge) + 0.06 * Math.sin(dryEdge * 2.7));
        const wornCenter = offset * (0.96 + 0.08 * Math.cos(dryEdge * 0.67));
        for (const edge of [-1, -0.59, 0, 0.59, 1]) {
          const span = wornCenter + edgeWidth * edge;
          this.positions.push(
            point.x + (span * dz) / length,
            0.023,
            point.z - (span * dx) / length,
          );
          this.colors.push(
            color.r,
            color.g,
            color.b,
            (1 - Math.abs(edge) ** 2) * strength * fade,
          );
        }
        if (!row) continue;
        for (let col = 0; col < 4; col++) {
          const a = first + (row - 1) * 5 + col;
          this.indices.push(a, a + 5, a + 1, a + 1, a + 5, a + 6);
        }
      }
    }
  }

  mesh(name: string): Mesh {
    const geometry = new BufferGeometry()
      .setAttribute("position", new Float32BufferAttribute(this.positions, 3))
      .setAttribute("color", new Float32BufferAttribute(this.colors, 4))
      .setIndex(this.indices);
    const mesh = new Mesh(
      geometry,
      new MeshBasicMaterial({
        vertexColors: true,
        side: DoubleSide,
        transparent: true,
        depthWrite: false,
      }),
    );
    mesh.name = name;
    mesh.renderOrder = -2;
    return mesh;
  }
}

const broadGateWidth = 5;
type GateStyle = "wide" | "short" | "narrow" | "end";

function gateStyle(gap: FencePassage | undefined): GateStyle {
  if (!gap) return "end";
  if (!gap.wholeHerd) return "narrow";
  return gap.right - gap.left >= broadGateWidth ? "wide" : "short";
}

const gatePosts = {
  wide: {
    width: 1.1,
    depth: 0.92,
    height: 2.6,
    cap: 0.24,
    timber: "#846951",
    crown: "#eadcc1",
  },
  short: {
    width: 0.72,
    depth: 0.66,
    height: 1.93,
    cap: 0.34,
    timber: "#895e42",
    crown: "#bc8b5b",
  },
  narrow: {
    width: 0.43,
    depth: 0.43,
    height: 1.48,
    cap: 0.13,
    timber: "#645447",
    crown: "#897362",
  },
  end: {
    width: 0.39,
    depth: 0.37,
    height: 1.45,
    cap: 0.11,
    timber: "#776352",
    crown: "#a08b70",
  },
} as const;

function gatePost(
  span: Extent,
  inward: number,
  style: GateStyle,
  pieces: Timber[],
): void {
  const { left, right, near, far } = span;
  const shape = gatePosts[style];
  const edge = inward > 0 ? left : right;
  const width = Math.min((right - left) * 0.4, shape.width);
  const length = (far - near) * shape.depth;
  const x = edge + inward * width * 0.5;
  const z = (near + far) * 0.5;
  const shaft = shape.height - shape.cap;
  pieces.push(
    {
      x,
      y: shaft * 0.5,
      z,
      width: width * 0.94,
      height: shaft,
      length: length * 0.8,
      color: shape.timber,
    },
    {
      x,
      y: shape.height - shape.cap * 0.5,
      z,
      width,
      height: shape.cap,
      length,
      color: shape.crown,
    },
  );

  if (style === "wide") {
    // The rake is behind the gatepost face, entirely on the existing blocked span.
    const braceEnd = edge + inward * Math.min(4.2, (right - left) * 0.45);
    const top = { x: x + inward * width * 0.26, y: shaft * 0.79 };
    const toe = { x: braceEnd, y: 0.34 };
    pieces.push({
      x: (top.x + toe.x) * 0.5,
      y: (top.y + toe.y) * 0.5,
      z: z - length * 0.2,
      width: Math.hypot(top.x - toe.x, top.y - toe.y),
      height: 0.26,
      length: length * 0.33,
      color: "#91765b",
      tilt: Math.atan2(top.y - toe.y, top.x - toe.x),
    });
    pieces.push({
      x: x + inward * width * 0.18,
      y: 0.27,
      z,
      width: width * 1.36,
      height: 0.54,
      length,
      color: "#726a5c",
    });
  } else if (style === "short") {
    // A second, shorter stake gives the single-track gate a stepped profile.
    pieces.push({
      x: x + inward * width * 0.81,
      y: 0.78,
      z,
      width: width * 0.61,
      height: 1.56,
      length: length * 0.6,
      color: "#a57954",
    });
  }
}

function fenceTimbers(
  span: Extent,
  passages: readonly FencePassage[],
  pieces: Timber[],
): void {
  const { left, right, near, far } = span;
  const length = far - near;
  const width = right - left;
  const z = (near + far) * 0.5;
  // The low apron traces the full collision footprint under the thinner rails.
  pieces.push({
    x: (left + right) * 0.5,
    y: 0.022,
    z,
    width,
    height: 0.044,
    length,
    color: "#9c9387",
  });

  const rowGaps = passages.filter(
    (gap) => gap.near === near && gap.far === far,
  );
  gatePost(
    span,
    1,
    gateStyle(rowGaps.find((gap) => gap.right === left)),
    pieces,
  );
  gatePost(
    span,
    -1,
    gateStyle(rowGaps.find((gap) => gap.left === right)),
    pieces,
  );

  const bays = Math.ceil(width / 6.4);
  const bayEdge = (i: number): number =>
    left +
    ((i + (i > 0 && i < bays ? 0.14 * Math.sin(left + 2.27 * i) : 0)) * width) /
      bays;
  const upperTones = ["#806956", "#92795f", "#756255", "#876f56"];
  const lowerTones = ["#56483f", "#6c5849", "#695747"];
  for (let i = 0; i < bays; i++) {
    const from = bayEdge(i);
    const to = bayEdge(i + 1);
    const phase = left + i * 2.9;
    const paint = Math.floor(Math.abs(from * 1.09 + i * 3.41));
    const x = (from + to) * 0.5;
    pieces.push(
      {
        x,
        z: z - length * 0.15,
        y: 0.55,
        width: to - from,
        height: 0.23,
        length: length * 0.33,
        color: lowerTones[paint % lowerTones.length] ?? "#695747",
      },
      {
        x,
        z: z + length * (0.14 + 0.028 * Math.sin(phase)),
        y: 1.12 + 0.065 * Math.cos(phase),
        width: to - from,
        height: 0.25,
        length: length * 0.31,
        color: upperTones[paint % upperTones.length] ?? "#806956",
      },
    );
    if (i === 0) continue;
    const height = 1.48 + 0.16 * Math.sin(phase);
    const depth = length * (0.47 + 0.04 * Math.sin(phase));
    const size = Math.min((width / bays) * 0.24, 0.39);
    pieces.push(
      {
        x: from,
        z,
        y: (height - 0.09) * 0.5,
        width: size,
        height: height - 0.09,
        length: depth,
        color: "#695848",
      },
      {
        x: from,
        z,
        y: height - 0.045,
        width: size,
        height: 0.09,
        length: depth,
        color: "#b4a38b",
      },
    );
  }
}

function fenceVerge(
  spans: readonly Extent[],
  passages: readonly FencePassage[],
): Group {
  const group = new Group();
  const wash = new GroundWash();
  const tufts: { x: number; z: number; size: number; angle: number }[] = [];
  const stones: { x: number; z: number; size: number }[] = [];
  const palette = ["#8f8766", "#a28c63", "#7c8067", "#aea284"];
  for (const [index, { left, right, near, far }] of spans.entries()) {
    const middle = (near + far) * 0.5;
    const length = right - left;
    const clusters = Math.ceil(length / 10);
    for (let i = 0; i < clusters; i++) {
      const phase = (i + 1) * 1.91 + index * 2.38;
      const center =
        left + (length * (i + 0.5 + 0.23 * Math.sin(phase))) / clusters;
      const side = Math.sin(phase) > 0 ? 1 : -1;
      const offset = (far - near) * 0.5 + 1;
      const reach = Math.min(
        center - left,
        right - center,
        3 + 1.4 * Math.cos(phase + 0.2),
      );
      wash.stroke(
        { x: center - reach, z: middle + side * offset },
        { x: center + reach, z: middle + side * (offset + 0.8) },
        (t) => 0.55 + Math.sin(t * Math.PI) * (1.7 + 0.62 * Math.cos(phase)),
        i % 3 === 0 ? "#a39b7b" : "#f0ede2",
        0.72,
        phase,
      );
      stones.push({
        x: center,
        z: middle + side * (far - near) * 0.21,
        size: Math.min(reach, far - near) * 0.7,
      });
      for (let j = 0; j < 4 + (i % 3); j++) {
        const scatter = j * 1.71 + phase;
        tufts.push({
          x: center + Math.cos(scatter) * reach * 0.58,
          z: middle + side * (offset + 1.2 + Math.sin(scatter) * 1.2),
          size: 0.6 + 0.73 * Math.abs(Math.sin(scatter)),
          angle: scatter,
        });
      }
    }
  }
  for (const gap of passages) {
    const style = gateStyle(gap);
    const spread = style === "wide" ? 5.3 : style === "short" ? 3.2 : 2.35;
    for (const [edge, away] of [
      [gap.left, -1],
      [gap.right, 1],
    ] as const) {
      const phase = gap.near + edge;
      for (const side of [-1, 1]) {
        const z = side < 0 ? gap.near : gap.far;
        // Snow gathers against the fence ends. The grass and the drift run away
        // from the opening so the gate reads as a clear break in the verge.
        wash.stroke(
          { x: edge + away * 0.8, z: z + side * 1.8 },
          {
            x: edge + away * spread,
            z: z + side * (2.9 + 0.7 * Math.sin(phase)),
          },
          (t) => 0.67 + 1.4 * Math.sin(Math.PI * t),
          side > 0 ? "#b6ac8c" : "#f2eddf",
          side > 0 ? 0.53 : 0.81,
          phase,
        );
        for (let i = 0; i < 4; i++) {
          tufts.push({
            x: edge + away * (1.8 + (i * (spread - 1.8)) / 4),
            z: z + side * (1.26 + 0.75 * Math.sin(phase + i)),
            size: 0.7 + 0.66 * Math.abs(Math.cos(phase + 2.3 * i)),
            angle: phase + i * 1.7,
          });
        }
      }
    }
  }
  group.add(wash.mesh("R2 drifted snow and verge pigments"));

  const blades: number[] = [];
  for (let i = 0; i < 7; i++) {
    const theta = i * 2.4;
    const reach = 0.53 + 0.24 * Math.cos(i * 2.6);
    const x = Math.cos(theta);
    const z = Math.sin(theta);
    blades.push(
      x * 0.13 - z * 0.06,
      0,
      z * 0.13 + x * 0.06,
      x * 0.13 + z * 0.06,
      0,
      z * 0.13 - x * 0.06,
      x * reach,
      0.25 + 0.24 * Math.abs(Math.sin(i * 2.1)),
      z * reach,
    );
  }
  const tuft = new BufferGeometry().setAttribute(
    "position",
    new Float32BufferAttribute(blades, 3),
  );
  tuft.computeVertexNormals();
  const grass = new InstancedMesh(
    tuft,
    new MeshLambertMaterial({ side: DoubleSide, forceSinglePass: true }),
    tufts.length,
  );
  grass.name = "R2 dormant grass at fence bases";
  const stone = new InstancedMesh(
    new IcosahedronGeometry(0.5, 0),
    new MeshLambertMaterial(),
    stones.length,
  );
  stone.name = "R2 snow-clad stones within fence spans";
  const instance = new Object3D();
  const color = new Color();
  for (const [i, patch] of tufts.entries()) {
    instance.position.set(patch.x, 0.023, patch.z);
    instance.scale.setScalar(patch.size);
    instance.rotation.y = patch.angle;
    instance.updateMatrix();
    grass.setMatrixAt(i, instance.matrix);
    grass.setColorAt(i, color.set(palette[i % palette.length] ?? "#8f8766"));
  }
  for (const [i, rock] of stones.entries()) {
    instance.position.set(rock.x, 0.11, rock.z);
    // Keep the stone radius inside the apron along both axes.
    instance.scale.set(rock.size, 0.43, rock.size * 0.49);
    instance.rotation.y = 0;
    instance.updateMatrix();
    stone.setMatrixAt(i, instance.matrix);
    stone.setColorAt(i, color.set(i % 3 === 0 ? "#a7a49a" : "#e4dfd5"));
  }
  group.add(grass, stone);
  return group;
}

function softenFenceTrail(points: readonly Vec2[]): Vec2[] {
  const softened: Vec2[] = [];
  for (const [i, point] of points.entries()) {
    const before = points[i - 1];
    const after = points[i + 1];
    if (!before || !after) {
      softened.push(point);
      continue;
    }
    const incoming = Math.hypot(before.x - point.x, before.z - point.z);
    const outgoing = Math.hypot(after.x - point.x, after.z - point.z);
    const trim = Math.min(3.2, incoming * 0.27, outgoing * 0.27);
    if (!trim) {
      softened.push(point);
      continue;
    }
    // Break the miter of the painted track within each trail bend.
    const start = {
      x: lerp(point.x, before.x, trim / incoming),
      z: lerp(point.z, before.z, trim / incoming),
    };
    const end = {
      x: lerp(point.x, after.x, trim / outgoing),
      z: lerp(point.z, after.z, trim / outgoing),
    };
    for (let j = 0; j <= 4; j++) {
      const t = j / 4;
      softened.push({
        x: lerp(lerp(start.x, point.x, t), lerp(point.x, end.x, t), t),
        z: lerp(lerp(start.z, point.z, t), lerp(point.z, end.z, t), t),
      });
    }
  }
  return softened;
}

function fence(level: ReindeerLevel): Group {
  const group = new Group();
  group.name = "R2 fence and passages";
  const spans = fenceSpans(level);
  const passages = reindeerFencePassages(level);
  const pieces: Timber[] = [];
  for (const span of spans) fenceTimbers(span, passages, pieces);
  group.add(
    timber("R2 rails and gateposts", pieces),
    fenceVerge(spans, passages),
  );

  const paint = new GroundWash();
  for (const { id, points } of level.trails) {
    if (id === "trail-fence")
      paint.trail(softenFenceTrail(points), [
        { offset: 0, halfWidth: 4.1, pigment: "#cfbf9c", strength: 0.32 },
        { offset: -1.95, halfWidth: 1.07, pigment: "#907e61", strength: 0.66 },
        { offset: 1.95, halfWidth: 1.08, pigment: "#978166", strength: 0.63 },
      ]);
    if (id === "trail-fence-short")
      paint.trail(softenFenceTrail(points), [
        { offset: 0, halfWidth: 1.57, pigment: "#d6c9ac", strength: 0.5 },
        { offset: 0, halfWidth: 0.82, pigment: "#7d7964", strength: 0.68 },
      ]);
  }
  for (const { gap, end } of reindeerShortFenceRunouts(level, passages)) {
    paint.stroke(
      { x: end.x, z: gap.far - 1 },
      end,
      () => 0.52,
      "#625849",
      0.84,
      gap.far,
    );
    paint.stroke(
      { x: end.x - 1.05, z: end.z },
      { x: end.x + 1.05, z: end.z },
      () => 0.23,
      "#625849",
      0.72,
      gap.far,
    );
  }
  for (const gap of passages) {
    const x = (gap.left + gap.right) * 0.5;
    if (gateStyle(gap) === "wide") {
      // Extra wear stays on the open threshold beneath the existing parallel tracks.
      paint.stroke(
        { x, z: gap.near - 5.8 },
        { x, z: gap.far + 4.9 },
        (t) => (gap.right - gap.left) * (0.4 - 0.075 * Math.sin(t * Math.PI)),
        "#bcaa85",
        0.27,
        x,
      );
    }
    if (gap.wholeHerd) continue;
    paint.stroke(
      { x, z: gap.near - 6 },
      { x, z: gap.far + 4.5 },
      () => (gap.right - gap.left) * 0.29,
      "#8b7b69",
      0.51,
      x,
    );
  }
  group.add(paint.mesh("R2 wide double track and narrow single track"));
  return group;
}

function dustBoundary(zone: Zone): Mesh {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const contour = zone.points.slice(0, -1);
  const area = contour.reduce((sum, point, index) => {
    const next = contour[(index + 1) % contour.length] ?? point;
    return sum + point.x * next.z - next.x * point.z;
  }, 0);
  const ink = new Color("#9b694e");
  for (const [index, a] of contour.entries()) {
    const b = contour[(index + 1) % contour.length];
    if (!b) continue;
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const width = (Math.sign(area) * 0.58) / Math.hypot(dx, dz);
    const first = positions.length / 3;
    for (const point of [a, b]) {
      positions.push(point.x, 0.034, point.z);
      positions.push(point.x - dz * width, 0.034, point.z + dx * width);
      colors.push(ink.r, ink.g, ink.b, 0.61, ink.r, ink.g, ink.b, 0);
    }
    indices.push(first, first + 1, first + 2, first + 1, first + 3, first + 2);
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 4))
    .setIndex(indices);
  const mesh = new Mesh(
    geometry,
    new MeshBasicMaterial({
      vertexColors: true,
      side: DoubleSide,
      transparent: true,
      depthWrite: false,
      forceSinglePass: true,
    }),
  );
  mesh.name = zone.id;
  mesh.renderOrder = -1;
  return mesh;
}

function mineGrain(seed: number): number {
  const value = Math.sin(seed * 127.141 + 81.31) * 43159.21;
  return value - Math.floor(value);
}

function rockGrain(coordinate: number): number {
  const cell = Math.floor(coordinate);
  return lerp(
    mineGrain(cell),
    mineGrain(cell + 1),
    MathUtils.smoothstep(coordinate - cell, 0, 1),
  );
}

function cutRock(barrier: GroundBarrier, material: MeshLambertMaterial): Mesh {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const contour = barrier.points;
  const levels = [...new Set(contour.map(({ z }) => z))].sort((a, b) => a - b);
  const { left, right, near, far } = extent(contour);
  // Short steep risers alternate with broad benches on the corridor-facing side.
  const profile = [
    [0, 0],
    [0.055, 0.12],
    [0.13, 0.2],
    [0.2, 0.23],
    [0.24, 0.49],
    [0.34, 0.52],
    [0.39, 0.84],
    [0.49, 0.97],
    [0.58, 1],
    [0.69, 0.81],
    [0.8, 0.52],
    [0.9, 0.25],
    [1, 0],
  ] as const;
  const westFacing = barrier.id === "mine-east-bank";
  const sections = westFacing
    ? profile
    : Array.from(profile, ([u, rise]) => [1 - u, rise] as const).reverse();
  const silt = new Color("#b19a85");
  const chalk = new Color("#bea68b");
  const slate = new Color("#68636a");
  const iron = new Color("#9e775e");
  const swatch = new Color();
  const peak = Math.min(6.5, (right - left) * 0.47);
  const seed = Math.floor(left * 0.7 + near * 0.3);
  // Pair the authored polygon edges by cross section so the ledges never
  // bridge an opening, even when the source outline turns inward.
  const edges = contour.slice(1).flatMap((b, index) => {
    const a = contour[index];
    return a && a.z !== b.z
      ? [
          {
            near: Math.min(a.z, b.z),
            far: Math.max(a.z, b.z),
            xAt: (z: number) => lerp(a.x, b.x, (z - a.z) / (b.z - a.z)),
          },
        ]
      : [];
  });
  for (let index = 1; index < levels.length; index++) {
    const bottom = levels[index - 1];
    const top = levels[index];
    if (bottom === undefined || top === undefined) continue;
    const mid = (bottom + top) / 2;
    const spans = edges
      .filter((edge) => edge.near < mid && edge.far > mid)
      .sort((a, b) => a.xAt(mid) - b.xAt(mid));
    for (let spanIndex = 1; spanIndex < spans.length; spanIndex += 2) {
      const west = spans[spanIndex - 1];
      const east = spans[spanIndex];
      if (!west || !east) continue;
      const first = positions.length / 3;
      const rows = Math.ceil((top - bottom) / 1.6);
      for (let row = 0; row <= rows; row++) {
        const z = lerp(bottom, top, row / rows);
        const start = west.xAt(z);
        const end = east.xAt(z);
        const along = z - near;
        const endDepth = Math.min(along, far - z);
        const taper = MathUtils.smoothstep(endDepth, 0, 8.5);
        const skew = (rockGrain(along / 11 + seed) - 0.5) * 0.28;
        for (const [column, [u, rise]] of sections.entries()) {
          const shifted = u + Math.sin(Math.PI * u) * skew;
          const x = lerp(start, end, shifted);
          const depth = interiorDepth(contour, { x, z });
          const folded = along + u * 15;
          const gully = MathUtils.smoothstep(
            rockGrain(folded / 7 + seed + 24),
            0.26,
            0.58,
          );
          const faceU = westFacing ? u : 1 - u;
          const bedding =
            faceU + (rockGrain(folded / 10 + seed - 17) - 0.5) * 0.06;
          const exposedFace =
            1 - MathUtils.smoothstep(Math.abs(bedding - 0.375), 0.014, 0.075);
          const bed = rockGrain((along - u * 14) / 4.7 + seed - 30);
          const ridge = 0.57 + 0.37 * rockGrain(folded / 16 + seed + 7);
          const y =
            0.016 +
            peak *
              rise *
              ridge *
              (0.57 + 0.53 * gully) *
              taper *
              MathUtils.smoothstep(depth, 0, 1.1) +
            0.46 * bed * taper * MathUtils.smoothstep(depth, 0.4, 2.5);
          positions.push(x, y, z);
          swatch
            .copy(silt)
            .lerp(slate, (1 - gully) * 0.44 + bed * 0.21)
            .lerp(slate, exposedFace * (0.21 + gully * 0.38))
            .lerp(iron, rockGrain((along + u * 9) / 8 + seed + 47) * 0.48)
            .lerp(chalk, MathUtils.smoothstep(y, 1.7, 4.2) * 0.47)
            .multiplyScalar(0.84 + 0.22 * bed)
            .toArray(colors, colors.length);
          colors.push(MathUtils.smoothstep(depth, 0, 0.46));
          if (row && column) {
            const at = first + row * sections.length + column;
            const above = at - sections.length;
            // Alternate diagonals so eroded facets do not form a repeating seam.
            if ((row + column) % 2)
              indices.push(above - 1, at - 1, above, above, at - 1, at);
            else indices.push(above - 1, at - 1, at, above - 1, at, above);
          }
        }
      }
    }
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 4))
    .setIndex(indices);
  geometry.computeVertexNormals();
  return new Mesh(geometry, material);
}

function routeEntrance(
  level: ReindeerLevel,
  paint: GroundWash,
  route: "dust" | "greenbelt",
  tint: string,
): void {
  const gate = level.triggers.find(
    (trigger) => trigger.kind === "route" && trigger.route === route,
  );
  if (gate?.kind !== "route" || gate.crossingZ === undefined) return;
  const id = route === "dust" ? "dust-sign" : "green-sign";
  const entry = level.landmarks.find((landmark) => landmark.id === id)?.pos;
  if (!entry) return;
  const { left, right } = extent(gate.points);
  const inner =
    Math.abs(left - entry.x) < Math.abs(right - entry.x) ? left : right;
  const direction = Math.sign(entry.x - inner);
  const start = { x: lerp(inner, entry.x, 0.43), z: gate.crossingZ - 24 };
  const end = { x: entry.x + direction * 2, z: gate.crossingZ + 29 };
  const width = Math.abs(inner - entry.x);
  paint.stroke(
    start,
    end,
    (t) => width * lerp(0.18, 0.41, t),
    tint,
    0.72,
    direction,
  );
  if (route === "greenbelt") {
    for (const side of [-1, 1])
      paint.stroke(
        { x: start.x + side * 4.2, z: start.z + 7 },
        { x: end.x + side * 6.2, z: end.z - 3 },
        () => 1.8,
        "#aaa76b",
        0.58,
        side * 2,
      );
  } else {
    for (let i = 1; i <= 5; i++) {
      const t = i / 6;
      const z = lerp(start.z, end.z, t);
      const x = lerp(start.x, end.x, t);
      paint.stroke(
        { x: x - 3.6, z },
        { x: x + 5.7, z: z + 2.5 },
        () => 1.2,
        "#d3b28b",
        0.61,
        i,
      );
    }
  }
}

interface GroundCover {
  readonly at: Vec2;
  readonly size: number;
  readonly height: number;
  readonly angle: number;
  readonly tint: string;
}

function coverGeometry(): BufferGeometry {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  // Low, connected lobes form a shrub crown from above and a mounded edge
  // from the side, without the spoke-like silhouette of the sedge.
  for (let lobe = 0; lobe < 6; lobe++) {
    const angle = lobe * 2.4;
    const spread = lobe === 0 ? 0 : 0.26 + mineGrain(lobe * 7) * 0.26;
    const size = lobe === 0 ? 0.57 : 0.33 + mineGrain(lobe * 2) * 0.18;
    const x = Math.cos(angle) * spread;
    const z = Math.sin(angle) * spread;
    const first = positions.length / 3;
    const tall = 0.52 + mineGrain(lobe + 11) * 0.39;
    for (let edge = 0; edge < 5; edge++) {
      const turn = angle + (edge * Math.PI * 2) / 5;
      const r = size * (0.8 + mineGrain(lobe * 5 + edge + 10) * 0.38);
      positions.push(x + Math.cos(turn) * r, 0.06, z + Math.sin(turn) * r);
      colors.push(0.58, 0.68, 0.53);
      positions.push(
        x + Math.cos(turn + 0.2) * r * 0.65,
        tall * (0.39 + mineGrain(lobe * 7 + edge + 18) * 0.27),
        z + Math.sin(turn + 0.2) * r * 0.65,
      );
      const tone = 0.72 + mineGrain(lobe * 5 + edge + 47) * 0.22;
      colors.push(tone, tone + 0.05, tone * 0.83);
    }
    const crown = positions.length / 3;
    positions.push(x - size * 0.17, tall, z + size * 0.17);
    colors.push(1, 0.97, 0.75);
    for (let edge = 0; edge < 5; edge++) {
      const base = first + edge * 2;
      const next = first + ((edge + 1) % 5) * 2;
      indices.push(base, base + 1, next, next, base + 1, next + 1);
      indices.push(base + 1, crown, next + 1);
    }
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 3))
    .setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function sedgeGeometry(): BufferGeometry {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  for (let blade = 0; blade < 8; blade++) {
    const angle = blade * 2.39996;
    const dx = Math.cos(angle),
      dz = Math.sin(angle);
    const reach = 0.29 + mineGrain(blade * 9 + 17) * 0.54;
    const tall = 0.44 + mineGrain(blade * 5 + 22) * 0.53;
    const first = positions.length / 3;
    positions.push(
      dx * 0.13 - dz * 0.07,
      0,
      dz * 0.13 + dx * 0.07,
      dx * 0.13 + dz * 0.07,
      0,
      dz * 0.13 - dx * 0.07,
      dx * reach * 0.6 - dz * 0.085,
      tall * 0.66,
      dz * reach * 0.6 + dx * 0.085,
      dx * reach * 0.6 + dz * 0.085,
      tall * 0.66,
      dz * reach * 0.6 - dx * 0.085,
      dx * reach,
      tall,
      dz * reach,
    );
    colors.push(
      0.61,
      0.66,
      0.51,
      0.61,
      0.66,
      0.51,
      0.83,
      0.81,
      0.57,
      0.83,
      0.81,
      0.57,
      1,
      0.98,
      0.72,
    );
    indices.push(
      first,
      first + 1,
      first + 2,
      first + 1,
      first + 3,
      first + 2,
      first + 2,
      first + 3,
      first + 4,
    );
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 3))
    .setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function coverMesh(
  name: string,
  tiles: readonly GroundCover[],
  geometry: BufferGeometry,
  material: MeshLambertMaterial,
): InstancedMesh {
  const mesh = new InstancedMesh(geometry, material, tiles.length);
  const plant = new Object3D();
  const shade = new Color();
  for (const [index, { at, size, height, angle, tint }] of tiles.entries()) {
    plant.position.set(at.x, 0.025, at.z);
    plant.scale.set(size, height, size * 0.83);
    plant.rotation.y = angle;
    plant.updateMatrix();
    mesh.setMatrixAt(index, plant.matrix);
    mesh.setColorAt(index, shade.set(tint));
  }
  mesh.name = name;
  return mesh;
}

const greenTints = ["#6c8165", "#8e9d73", "#76876b", "#acaa70"] as const;
const supplyTints = ["#b0ae69", "#a4a66c", "#c1b983", "#697f55"] as const;

function paintGreenbelt(
  level: ReindeerLevel,
  paint: GroundWash,
  group: Group,
  slopes: readonly GroundBarrier[],
): void {
  const route = level.trails.find(({ id }) => id === "trail-greenbelt");
  if (!route) return;
  const geometry = coverGeometry();
  const sedges = sedgeGeometry();
  const material = new MeshLambertMaterial({
    vertexColors: true,
    side: DoubleSide,
  });
  const fringe: GroundCover[] = [];
  const stems: GroundCover[] = [];
  const { min, max } = level.bounds;
  for (const [i, start] of route.points.entries()) {
    const end = route.points[i + 1];
    if (!end) continue;
    const dx = end.x - start.x;
    const dz = end.z - start.z;
    const length = Math.hypot(dx, dz);
    if (!length) continue;
    const count = Math.max(1, Math.floor(length / 7.4));
    for (let step = 1; step <= count; step++) {
      const key = i * 51 + step * 19;
      const t = (step + (mineGrain(key) - 0.5) * 0.54) / (count + 1);
      for (const side of [-1, 1]) {
        const phase = key + side * 13;
        const verge = side * (5.1 + mineGrain(phase) * 2.65);
        const at = {
          x: lerp(start.x, end.x, t) + (verge * dz) / length,
          z: lerp(start.z, end.z, t) - (verge * dx) / length,
        };
        const size = 1.15 + mineGrain(phase + 9) * 1.12;
        if (
          at.x < min.x + size ||
          at.x > max.x - size ||
          slopes.some(({ points }) => contains(points, at)) ||
          mineGrain(phase + 15) < 0.16
        )
          continue;
        fringe.push({
          at,
          size,
          height: 0.56 + mineGrain(phase + 19) * 0.72,
          angle: phase * 2.4,
          tint: greenTints[(i + step) % greenTints.length] ?? greenTints[0],
        });
        paint.stroke(
          { x: at.x - 2.15, z: at.z - 0.3 },
          { x: at.x + 2, z: at.z + 1 },
          (t) => size * (0.46 + Math.sin(t * Math.PI) * 0.28),
          "#617d62",
          0.48,
          phase,
        );
        for (let clump = 0; clump < 3; clump++) {
          const shift = 1.9 + 1.5 * mineGrain(phase + clump * 6);
          const angle = clump * 2.4 + phase;
          const point = {
            x: at.x + Math.cos(angle) * shift,
            z: at.z + Math.sin(angle) * shift,
          };
          if (
            Math.abs(
              verge +
                (shift * (Math.cos(angle) * dz - Math.sin(angle) * dx)) /
                  length,
            ) < 3.4 ||
            point.x < min.x + 1 ||
            point.x > max.x - 1 ||
            slopes.some(({ points }) => contains(points, point))
          )
            continue;
          stems.push({
            at: point,
            size: 0.75 + mineGrain(phase + clump * 5 + 4) * 0.72,
            height: 0.28 + mineGrain(phase + clump * 5 + 18) * 0.65,
            angle,
            tint: clump === 0 ? "#c6b17c" : "#8d9c70",
          });
        }
      }
    }
  }
  group.add(
    coverMesh("R3 greenbelt verge clusters", fringe, geometry, material),
    coverMesh("R3 greenbelt sedges", stems, sedges, material),
  );
  for (const [zoneId, markId, name] of [
    ["green-supply", "supply-sign", "R3 restored bank shoots"],
    ["green-supply-exit", "green-return", "R3 moss pocket shoots"],
  ] as const) {
    const zone = level.zones.find(({ id }) => id === zoneId);
    const at = level.landmarks.find(({ id }) => id === markId)?.pos;
    if (!zone || !at) continue;
    const tiles: GroundCover[] = [];
    const { left, right, near, far } = extent(zone.points);
    for (const side of [-1, 1]) {
      for (let i = 0; i < 26; i++) {
        const phase = i * 2.39996 + side;
        const width = side < 0 ? at.x - left : right - at.x;
        const point = {
          x:
            at.x +
            side * width * (0.58 + 0.28 * Math.sin(phase)) +
            Math.cos(i) * 0.38,
          z: lerp(near + 1.7, far - 1.7, (i + 0.5) / 26) + Math.cos(phase),
        };
        if (
          interiorDepth(zone.points, point) < 0.7 ||
          Math.abs(point.x - at.x) < 3.3
        )
          continue;
        tiles.push({
          at: point,
          size: 0.9 + mineGrain(i * 7 + side) * 0.68,
          height: 0.42 + mineGrain(i * 7 + side + 16) * 0.65,
          angle: phase,
          tint: supplyTints[i % supplyTints.length] ?? supplyTints[0],
        });
      }
      const bank = lerp(at.x, side < 0 ? left : right, 0.68);
      paint.stroke(
        { x: bank - side * 1.3, z: near + 1.4 },
        { x: bank, z: far - 1.3 },
        (t) => 2.7 + 2.1 * Math.sin(t * Math.PI),
        side < 0 ? "#788e60" : "#8e9a70",
        0.74,
        side * 3.1,
        zone.points,
      );
    }
    group.add(coverMesh(name, tiles, sedges, material));
    paint.stroke(
      { x: at.x - 3, z: at.z - 4.2 },
      { x: at.x + 2.7, z: at.z + 4.3 },
      () => 3.1,
      "#ded4a0",
      0.56,
      2,
      zone.points,
    );
  }
}

function slateGeometry(): BufferGeometry {
  const geometry = new BufferGeometry()
    .setAttribute(
      "position",
      new Float32BufferAttribute(
        [
          -1, 0, -0.22, -0.34, 0, 0.76, 0.58, 0, 0.61, 0.93, 0, -0.16, 0.07, 0,
          -0.66, -0.31, 0.88, -0.16, 0.51, 0.43, 0.29,
        ],
        3,
      ),
    )
    .setIndex([0, 1, 5, 1, 2, 6, 1, 6, 5, 2, 3, 6, 3, 4, 6, 4, 5, 6, 4, 0, 5])
    .toNonIndexed();
  geometry.computeVertexNormals();
  return geometry;
}

function paintShelters(
  level: ReindeerLevel,
  paint: GroundWash,
  group: Group,
  slopes: readonly GroundBarrier[],
): void {
  const scree: GroundCover[] = [];
  for (const [zoneId, markId] of [
    ["dust-entry-rest", "dust-entry"],
    ["dust-shelter", "dust-shelter-sign"],
    ["dust-exit-rest", "dust-exit-sign"],
  ] as const) {
    const zone = level.zones.find(({ id }) => id === zoneId);
    const at = level.landmarks.find(({ id }) => id === markId)?.pos;
    if (!zone || !at) continue;
    const { left, right, near, far } = extent(zone.points);
    for (let i = 0; i < 11; i++) {
      const angle = lerp(-1.15, 1.22, i / 10);
      const key = i * 7 + near;
      const size = 0.52 + mineGrain(key) * 1.18;
      const atEdge = {
        x:
          lerp(at.x, right, 0.49) +
          3.3 * Math.cos(angle) +
          1.35 * (mineGrain(key + 6) - 0.5),
        z: at.z + (far - near) * 0.34 * Math.sin(angle),
      };
      if (interiorDepth(zone.points, atEdge) < size * 1.05) continue;
      scree.push({
        at: atEdge,
        size,
        height: mineGrain(key + 11) * 0.67 + 0.24,
        angle: i * 1.39,
        tint: i % 4 === 0 ? "#aca28c" : "#80777a",
      });
    }
    paint.stroke(
      { x: at.x + 2.4, z: near + 0.8 },
      { x: at.x - 1.1, z: far - 0.8 },
      (t) => (right - left) * (0.23 + 0.13 * Math.sin(t * Math.PI)),
      "#dddab7",
      0.82,
      at.z,
      zone.points,
    );
    for (const [i, shade] of ["#79736b", "#9f9b7c", "#b7b187"].entries()) {
      const x = lerp(at.x, right, 0.42 + i * 0.12);
      paint.stroke(
        { x, z: far - 1.7 - i * 0.6 },
        { x: x + 3.4, z: near + 2.2 + i * 1.5 },
        (t) => 1.2 + 1.6 * Math.sin(t * Math.PI),
        shade,
        0.42,
        i * 2.2,
        zone.points,
      );
    }
  }
  const talus: GroundCover[] = [];
  for (const { points } of slopes) {
    const { left, right, near, far } = extent(points);
    const clusters = Math.ceil((far - near) / 10.5);
    for (let row = 1; row <= clusters; row++) {
      const phase = near + row * 13;
      const center = lerp(
        near,
        far,
        (row + 0.7 * (mineGrain(phase) - 0.5)) / (clusters + 1),
      );
      for (const side of [-1, 1]) {
        for (let rock = 0; rock < 3; rock++) {
          const key = phase + side * 27 + rock * 7;
          const size = (rock === 0 ? 0.92 : 0.37) + mineGrain(key) * 0.57;
          const z = center + rock * (mineGrain(key + 16) - 0.42) * 3.1;
          const x =
            (side < 0 ? left : right) -
            side * (size * 1.1 + mineGrain(key + 4) * 1.15);
          if (interiorDepth(points, { x, z }) < size * 1.05) continue;
          talus.push({
            at: { x, z },
            size,
            height: size * (0.58 + mineGrain(key + 11) * 0.64),
            angle: key * 0.83,
            tint: rock === 0 ? "#9c8b86" : "#aa947f",
          });
        }
      }
    }
  }
  const geometry = slateGeometry();
  const material = new MeshLambertMaterial({ side: DoubleSide });
  group.add(
    coverMesh("R3 shelter slate crescents", scree, geometry, material),
    coverMesh("R3 scree at the foot of the cut", talus, geometry, material),
  );
}

function suspendedDust(zones: readonly Zone[]): Mesh {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const ash = new Color("#c9a88c");
  const cream = new Color("#efe1c6");
  const color = new Color();
  for (const zone of zones) {
    const { left, right, near, far } = extent(zone.points);
    for (let plume = 0; plume < 7; plume++) {
      const key = near + plume * 19;
      const side = plume % 3 === 1 ? 0.22 : 0.73;
      const x = lerp(left, right, side + mineGrain(key) * 0.064);
      const z = lerp(near + 3, far - 5, (plume + 0.5) / 7);
      const length = 2.6 + mineGrain(key + 8) * 2.1;
      // The entire feathered ribbon fits inside the authoritative zone.
      if (interiorDepth(zone.points, { x, z }) < length * 0.91 + 1.25) continue;
      const rise = 0.7 + mineGrain(key + 13) * 0.79;
      color.copy(ash).lerp(cream, 0.52 + mineGrain(key + 3) * 0.45);
      const first = positions.length / 3;
      for (let row = 0; row <= 6; row++) {
        const t = row / 6;
        const taper = Math.sin(Math.PI * t);
        for (const edge of [-1, 0, 1]) {
          const at = {
            x: x + (t - 0.5) * length * 1.5 + edge * 0.14,
            z: z + (t - 0.5) * length + edge * taper * 1.2,
          };
          positions.push(at.x, 0.18 + taper * (rise + 0.39 * edge), at.z);
          const opacity = edge === 0 ? taper * 0.26 : 0;
          colors.push(color.r, color.g, color.b, opacity);
        }
        if (!row) continue;
        for (let column = 0; column < 2; column++) {
          const a = first + (row - 1) * 3 + column;
          indices.push(a, a + 3, a + 1, a + 1, a + 3, a + 4);
        }
      }
    }
  }
  const geometry = new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 4))
    .setIndex(indices);
  const mesh = new Mesh(
    geometry,
    new MeshBasicMaterial({
      vertexColors: true,
      side: DoubleSide,
      transparent: true,
      depthWrite: false,
      forceSinglePass: true,
    }),
  );
  mesh.name = "R3 airborne dust";
  mesh.renderOrder = 1;
  return mesh;
}

function mining(level: ReindeerLevel): Group {
  const group = new Group();
  group.name = "R3 old mine and restored verge";
  const slopes = level.barriers.filter(
    ({ kind, id }) => kind === "slope" && !id.startsWith("snowbank-"),
  );
  const stone = new MeshLambertMaterial({
    vertexColors: true,
    side: DoubleSide,
    transparent: true,
    alphaTest: 0.035,
    forceSinglePass: true,
  });
  for (const barrier of slopes) {
    const rock = cutRock(barrier, stone);
    rock.name =
      barrier.id === "old-cut"
        ? "R3 old cut relief"
        : `R3 terrain ${barrier.id}`;
    rock.renderOrder = -3;
    group.add(rock);
  }
  const paint = new GroundWash();
  routeEntrance(level, paint, "dust", "#ad7e5c");
  routeEntrance(level, paint, "greenbelt", "#83925e");
  const drift = new GroundWash();
  const dustZones = level.zones.filter(({ id }) =>
    level.dustCycle.zoneIds.includes(id),
  );
  for (const dust of dustZones) {
    group.add(dustBoundary(dust));
    const { left, right, near, far } = extent(dust.points);
    for (let i = 0; i < 9; i++) {
      const t = i / 8;
      const phase = i * 2.19;
      const x = lerp(left + 2.8, right - 10.8, 0.5 + 0.5 * Math.sin(phase));
      const z = lerp(near + 2.4, far - 5.7, t);
      drift.stroke(
        { x, z },
        {
          x: Math.min(right - 1.9, x + 13.5 + 4.4 * Math.cos(phase)),
          z: z + 3.2,
        },
        (u) => 1.32 + 1.35 * Math.sin(u * Math.PI),
        i % 3 === 0 ? "#af8b71" : "#ddc3a2",
        0.59,
        phase,
        dust.points,
      );
    }
    paint.stroke(
      { x: left + 4, z: near + 4 },
      { x: right - 4, z: far - 3.8 },
      (t) => 4.7 + 4.6 * Math.sin(t * Math.PI),
      "#ab866a",
      0.48,
      near,
      dust.points,
    );
  }
  for (const trail of level.trails.filter(
    ({ id }) => id === "trail-greenbelt" || id === "trail-dust",
  )) {
    const green = trail.id === "trail-greenbelt";
    for (let i = 1; i < trail.points.length; i++) {
      const a = trail.points[i - 1];
      const b = trail.points[i];
      if (!a || !b) continue;
      paint.stroke(
        a,
        b,
        (t) => (green ? 4.1 : 2.2) + 0.62 * Math.sin(t * Math.PI),
        green ? "#8a9a6a" : "#a8866f",
        0.71,
        i,
      );
    }
  }
  paintGreenbelt(level, paint, group, slopes);
  paintShelters(level, paint, group, slopes);
  const driftMesh = drift.mesh("R3 suspended dust strokes");
  driftMesh.renderOrder = -1;
  group.add(
    driftMesh,
    paint.mesh("R3 dust contours and green belt strokes"),
    suspendedDust(dustZones),
  );
  return group;
}

export class ReindeerRoutes {
  readonly group = new Group();

  constructor(private readonly level: ReindeerLevel) {
    this.group.add(fence(level), mining(level));
    const shade = new GroundWash();
    for (const zone of level.zones) {
      if (zone.id !== "winter-pines" && zone.id !== "thaw-overlook") continue;
      const { left, right, near, far } = extent(zone.points);
      const x = (left + right) / 2;
      shade.stroke(
        { x, z: near },
        { x, z: far },
        () => (right - left) * 0.49,
        zone.id === "winter-pines" ? "#819c8e" : "#d1d4a1",
        0.42,
        x,
        zone.points,
      );
    }
    this.group.add(shade.mesh("Winter clearing and thaw lookout"));
  }

  update(tick: number): void {
    const { phase } = sampleReindeerDust(this.level, tick, this.level.spawn);
    for (const id of this.level.dustCycle.zoneIds) {
      const mesh = this.group.getObjectByName(id);
      if (mesh instanceof Mesh && mesh.material instanceof MeshBasicMaterial)
        mesh.material.opacity = phase === "calm" ? 0.67 : 1;
    }
    const drift = this.group.getObjectByName("R3 suspended dust strokes");
    if (drift instanceof Mesh && drift.material instanceof MeshBasicMaterial)
      drift.material.opacity =
        phase === "active" ? 1 : phase === "warning" ? 0.54 : 0.15;
    const haze = this.group.getObjectByName("R3 airborne dust");
    if (haze instanceof Mesh && haze.material instanceof MeshBasicMaterial)
      haze.material.opacity =
        phase === "active" ? 1 : phase === "warning" ? 0.46 : 0.04;
  }
}
