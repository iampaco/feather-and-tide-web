import type { WaterLayer } from "../core/game";
import type { Zone } from "./schema";

export type WaterHazard = Extract<Zone, { kind: "hazard" }>;
type WaterNet = WaterHazard & {
  readonly structure?: undefined;
  readonly motion?: undefined;
};
export type WhaleBreakwaterHazard = WaterHazard & {
  readonly structure: "breakwater";
  readonly motion?: undefined;
};

export function isWhaleNet(zone: Zone): zone is WaterNet {
  return zone.kind === "hazard" && !zone.motion && zone.structure === undefined;
}

export function isWhaleBreakwater(zone: Zone): zone is WhaleBreakwaterHazard {
  return zone.kind === "hazard" && zone.structure === "breakwater";
}

export const layerBit: Readonly<Record<WaterLayer, number>> = {
  surface: 1,
  shallow: 2,
  deep: 4,
};

export function occupiesLayer(hazard: WaterHazard, layer: WaterLayer): boolean {
  return ((hazard.depthMask ?? 0) & layerBit[layer]) !== 0;
}

export {
  hazardOffset,
  hazardPoints,
  hazardStep,
  hazardTravelBounds,
  sweptMovingHazard as sweptWaterHazard,
} from "./moving-hazard";
