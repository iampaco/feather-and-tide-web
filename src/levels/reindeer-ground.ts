import { clamp, distance, type Vec2 } from "../core/math";
import { sweptCircle } from "./geometry";
import type { ReindeerLevel, RoadCrossing } from "./schema";
import type { MovingHazard } from "./moving-hazard";
import { hazardOffset } from "./moving-hazard";

export function insideCulvert(road: RoadCrossing, { x, z }: Vec2): boolean {
  const { culvert } = road;
  return (
    x > culvert.left && x < culvert.right && z > culvert.near && z < culvert.far
  );
}

export function onRoad(road: RoadCrossing, pos: Vec2): boolean {
  return pos.z >= road.near && pos.z <= road.far && !insideCulvert(road, pos);
}

export function groundHeight(road: RoadCrossing, pos: Vec2): number {
  if (!insideCulvert(road, pos)) return 0;
  const { culvert, near, far } = road;
  return (
    -culvert.depth *
    Math.min(
      1,
      (pos.z - culvert.near) / (near - culvert.near),
      (culvert.far - pos.z) / (culvert.far - far),
    )
  );
}

export function hoofRadius(index: number): number {
  return index === 0 || index === 1 ? 0.66 : 0.94;
}

export function groundBlocked(
  level: ReindeerLevel,
  from: Vec2,
  to: Vec2,
  radius: number,
): boolean {
  return level.barriers.some(({ points }) =>
    sweptCircle(points, from, to, radius),
  );
}

export function groundMove(
  level: ReindeerLevel,
  from: Vec2,
  to: Vec2,
  radius: number,
): Vec2 {
  const { min, max } = level.bounds;
  const end = {
    x: clamp(to.x, min.x + radius, max.x - radius),
    z: clamp(to.z, min.z + radius, max.z - radius),
  };
  if (!groundBlocked(level, from, end, radius)) return end;
  // Resolve a glancing step along the edge using the same swept footprint.
  return (
    [
      { x: end.x, z: from.z },
      { x: from.x, z: end.z },
    ]
      .sort((a, b) => distance(from, b) - distance(from, a))
      .find((point) => !groundBlocked(level, from, point, radius)) ?? from
  );
}

export function roadVehicle(level: ReindeerLevel): MovingHazard {
  const vehicle = level.zones.find(
    (zone) => zone.kind === "hazard" && zone.id === level.road.vehicleId,
  );
  if (vehicle?.kind !== "hazard") throw new Error("Missing road vehicle");
  return vehicle;
}

export function vehicleDirection(vehicle: MovingHazard, tick: number): -1 | 1 {
  return hazardOffset(vehicle, tick + 1).x >= hazardOffset(vehicle, tick).x
    ? 1
    : -1;
}

export interface FencePassage {
  readonly left: number;
  readonly right: number;
  readonly near: number;
  readonly far: number;
  readonly wholeHerd: boolean;
}

/** Compare adjacent spans within a single row, never across different fence rows. */
export function reindeerFencePassages(level: ReindeerLevel): FencePassage[] {
  const rows = new Map<string, FencePassage[]>();
  for (const barrier of level.barriers) {
    if (barrier.kind !== "fence") continue;
    const xs = barrier.points.map(({ x }) => x);
    const zs = barrier.points.map(({ z }) => z);
    const near = Math.min(...zs),
      far = Math.max(...zs);
    const key = `${near}:${far}`;
    const row = rows.get(key) ?? [];
    row.push({
      left: Math.min(...xs),
      right: Math.max(...xs),
      near,
      far,
      wholeHerd: false,
    });
    rows.set(key, row);
  }
  const passages: FencePassage[] = [];
  for (const row of rows.values()) {
    row.sort((a, b) => a.left - b.left);
    for (let index = 1; index < row.length; index++) {
      const west = row[index - 1],
        east = row[index];
      if (!west || !east || east.left <= west.right) continue;
      passages.push({
        left: west.right,
        right: east.left,
        near: west.near,
        far: west.far,
        wholeHerd: east.left - west.right > 2 * hoofRadius(8),
      });
    }
  }
  return passages.sort((a, b) => a.near - b.near || a.left - b.left);
}

export function reindeerShortFenceRunouts(
  level: ReindeerLevel,
  passages = reindeerFencePassages(level),
): { gap: FencePassage; end: Vec2 }[] {
  const trail = level.trails.find(({ id }) => id === "trail-fence-short");
  if (!trail) return [];
  return passages.flatMap((gap) => {
    const index = trail.points.findIndex((point, i) => {
      const before = trail.points[i - 1];
      return (
        before &&
        before.x === point.x &&
        point.x > gap.left &&
        point.x < gap.right &&
        before.z <= gap.near &&
        point.z > gap.far
      );
    });
    const first = trail.points[index];
    if (!first || !gap.wholeHerd) return [];
    let end = first;
    for (const point of trail.points.slice(index + 1)) {
      if (point.x !== end.x || point.z <= end.z) break;
      end = point;
    }
    return [{ gap, end }];
  });
}
