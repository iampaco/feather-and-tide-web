import type { Vec2 } from "../core/math";

const EPSILON = 1e-8;

function cross(a: Vec2, b: Vec2, c: Vec2): number {
  return (b.x - a.x) * (c.z - a.z) - (b.z - a.z) * (c.x - a.x);
}

function onSegment(a: Vec2, b: Vec2, p: Vec2): boolean {
  return (
    Math.abs(cross(a, b, p)) < EPSILON &&
    p.x >= Math.min(a.x, b.x) - EPSILON &&
    p.x <= Math.max(a.x, b.x) + EPSILON &&
    p.z >= Math.min(a.z, b.z) - EPSILON &&
    p.z <= Math.max(a.z, b.z) + EPSILON
  );
}

export function intersects(a: Vec2, b: Vec2, c: Vec2, d: Vec2): boolean {
  const ac = cross(a, b, c);
  const ad = cross(a, b, d);
  const ca = cross(c, d, a);
  const cb = cross(c, d, b);
  return (
    onSegment(a, b, c) ||
    onSegment(a, b, d) ||
    onSegment(c, d, a) ||
    onSegment(c, d, b) ||
    (ac * ad < 0 && ca * cb < 0)
  );
}

export function contains(points: readonly Vec2[], p: Vec2): boolean {
  let inside = false;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (!a || !b) continue;
    if (onSegment(a, b, p)) return true;
    if (
      a.z > p.z !== b.z > p.z &&
      p.x < a.x + ((b.x - a.x) * (p.z - a.z)) / (b.z - a.z)
    )
      inside = !inside;
  }
  return inside;
}

export function crosses(
  points: readonly Vec2[],
  from: Vec2,
  to: Vec2,
): boolean {
  if (contains(points, from) || contains(points, to)) return true;
  return points.some((point, i) => {
    const next = points[i + 1];
    return next !== undefined && intersects(from, to, point, next);
  });
}

function pointToEdgeSquared(point: Vec2, a: Vec2, b: Vec2): number {
  const x = b.x - a.x;
  const z = b.z - a.z;
  const denominator = x * x + z * z;
  const t =
    denominator === 0
      ? 0
      : Math.max(
          0,
          Math.min(
            1,
            ((point.x - a.x) * x + (point.z - a.z) * z) / denominator,
          ),
        );
  const dx = point.x - a.x - x * t;
  const dz = point.z - a.z - z * t;
  return dx * dx + dz * dz;
}

export function interiorDepth(points: readonly Vec2[], point: Vec2): number {
  if (!contains(points, point)) return 0;
  let nearest = Infinity;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (a && b) nearest = Math.min(nearest, pointToEdgeSquared(point, a, b));
  }
  return Math.sqrt(nearest);
}

export function sweptCircle(
  points: readonly Vec2[],
  from: Vec2,
  to: Vec2,
  radius: number,
): boolean {
  const left = Math.min(from.x, to.x) - radius;
  const right = Math.max(from.x, to.x) + radius;
  const near = Math.min(from.z, to.z) - radius;
  const far = Math.max(from.z, to.z) + radius;
  if (
    points.every((p) => p.x < left) ||
    points.every((p) => p.x > right) ||
    points.every((p) => p.z < near) ||
    points.every((p) => p.z > far)
  )
    return false;
  if (crosses(points, from, to)) return true;
  const squared = radius * radius;
  return points.some((a, i) => {
    const b = points[i + 1];
    return (
      b !== undefined &&
      (pointToEdgeSquared(from, a, b) <= squared ||
        pointToEdgeSquared(to, a, b) <= squared ||
        pointToEdgeSquared(a, from, to) <= squared ||
        pointToEdgeSquared(b, from, to) <= squared)
    );
  });
}

export function polygonError(points: readonly Vec2[]): string | undefined {
  const first = points[0];
  const last = points.at(-1);
  if (
    points.length < 4 ||
    !first ||
    !last ||
    first.x !== last.x ||
    first.z !== last.z
  ) {
    return "polygon must be closed with at least three vertices";
  }
  let area = 0;
  const edgeCount = points.length - 1;
  for (let i = 0; i < edgeCount; i++) {
    const a = points[i];
    const b = points[i + 1];
    if (!a || !b || (a.x === b.x && a.z === b.z)) return "zero length edge";
    const next = points[(i + 2) % edgeCount];
    if (next && (onSegment(a, b, next) || onSegment(b, next, a)))
      return "overlapping adjacent edges";
    area += a.x * b.z - a.z * b.x;
    for (let j = i + 2; j < edgeCount; j++) {
      if (i === 0 && j === edgeCount - 1) continue;
      const c = points[j];
      const d = points[j + 1];
      if (c && d && intersects(a, b, c, d)) return "polygon self-intersection";
    }
  }
  if (Math.abs(area) < EPSILON) return "polygon has zero area";
  return undefined;
}
