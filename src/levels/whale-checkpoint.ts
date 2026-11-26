import type { WhaleLevel, Zone } from "./schema";

export type WhaleCheckpointArea = {
  readonly id: string;
  readonly zone: Zone;
  readonly fallback: boolean;
};

const checkpointWater = { "junction-rest": "C1", "offshore-rest": "C2" };

export function whaleCheckpointArea(
  zone: Zone,
): WhaleCheckpointArea | undefined {
  if (zone.kind === "checkpoint") return { id: zone.id, zone, fallback: false };
  if (zone.kind !== "sanctuary") return;
  if (zone.id === "junction-rest" || zone.id === "offshore-rest")
    return { id: checkpointWater[zone.id], zone, fallback: true };
}

export function whaleCheckpointAvailable(
  level: WhaleLevel,
  area: WhaleCheckpointArea,
  triggered: readonly string[],
  routeLocked: boolean,
): boolean {
  return (
    !triggered.includes(area.id) &&
    (area.id === "C1" ? !triggered.includes("C2") : routeLocked) &&
    (!area.fallback ||
      level.zones.some(
        (zone) => zone.id === area.id && zone.kind === "checkpoint",
      ))
  );
}
