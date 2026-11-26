import type { WhaleActor } from "../core/game";
import type { Vec2 } from "../core/math";
import { contains } from "./geometry";
import type { Zone } from "./schema";

export type WaterCurrent = Extract<Zone, { kind: "current" }>;

export function isReefCurrent(zone: Zone): zone is WaterCurrent {
  return (
    zone.kind === "current" &&
    (zone.id === "reef-current" || zone.id === "reef-current-east")
  );
}

export function hasVisibleDrift(zone: WaterCurrent): boolean {
  return (
    zone.id === "bay-current" ||
    zone.id === "shelf-current" ||
    isReefCurrent(zone)
  );
}

export function canRideCurrent(
  current: WaterCurrent,
  actor: WhaleActor,
): boolean {
  return (
    actor.status !== "strayed" &&
    actor.dive.layer !== "surface" &&
    !actor.dive.forced &&
    contains(current.points, actor.pos) &&
    flowProjection(current, {
      x: Math.sin(actor.heading),
      z: Math.cos(actor.heading),
    }) >= current.minAlignment
  );
}

export function flowProjection(current: WaterCurrent, point: Vec2): number {
  return current.direction.x * point.x + current.direction.z * point.z;
}

export function currentGuide(current: WaterCurrent): {
  entry: Vec2;
  exit: Vec2;
} {
  const centers = current.points.slice(1).map((point, i) => {
    const previous = current.points[i] ?? point;
    return { x: (previous.x + point.x) / 2, z: (previous.z + point.z) / 2 };
  });
  centers.sort(
    (a, b) => flowProjection(current, a) - flowProjection(current, b),
  );
  const origin = current.points[0] ?? { x: 0, z: 0 };
  return {
    entry: centers[0] ?? origin,
    exit: centers.at(-1) ?? origin,
  };
}
