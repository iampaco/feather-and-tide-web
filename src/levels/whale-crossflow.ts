import { clamp, type Vec2 } from "../core/math";
import { interiorDepth } from "./geometry";
import type { Zone } from "./schema";

export type WhaleCrossflow = Extract<Zone, { kind: "crossCurrent" }>;

// Taper the drift near every edge so crossing into and out of the displayed
// polygon does not abruptly change the whales' lateral velocity.
const FLOW_EDGE_BLEND = 4;

export function whaleCrossflowVelocity(
  flows: readonly WhaleCrossflow[],
  position: Vec2,
): Vec2 | undefined {
  for (const flow of flows) {
    const blend = clamp(interiorDepth(flow.points, position) / FLOW_EDGE_BLEND);
    if (blend > 0)
      return { x: flow.velocity.x * blend, z: flow.velocity.z * blend };
  }
  return undefined;
}
