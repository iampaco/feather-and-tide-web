import { clamp, type Vec2 } from "../core/math";
import { interiorDepth, polygonError } from "./geometry";
import type { Landmark, WhaleLevel, Zone } from "./schema";

export const DREDGING_FEATHER = 9;

const outlineIds = [
  "dredge-plume-a",
  "dredge-plume-b",
  "dredge-plume-c",
  "dredge-plume-d",
  "dredge-plume-e",
  "dredge-plume-f",
  "dredge-plume-g",
] as const;

const surfaceIds = [
  "dredge-surface-entry",
  "dredge-surface-mid",
  "dredge-surface-bend",
  "dredge-surface-exit",
] as const;

const clearIds = [
  "dredge-clear-entry",
  "dredge-clear-mid",
  "dredge-clear-bend",
  "dredge-clear-exit",
] as const;

export interface DredgingPassage {
  readonly plume: readonly Vec2[];
  readonly surface: readonly Landmark[];
  readonly clear: readonly Landmark[];
  readonly works: Landmark;
  readonly regroup: Landmark;
  readonly rest: Extract<Zone, { kind: "sanctuary" | "checkpoint" | "goal" }>;
}

export function isDredgingLandmark(id: string): boolean {
  return id.startsWith("dredge-");
}

export function dredgingPassage(
  level: WhaleLevel,
): DredgingPassage | undefined {
  const marks = new Map(level.landmarks.map((mark) => [mark.id, mark]));
  const read = (ids: readonly string[]) =>
    ids.flatMap((id) => {
      const mark = marks.get(id);
      return mark ? [mark] : [];
    });
  const marksOnPlume = read(outlineIds);
  const surface = read(surfaceIds);
  const clear = read(clearIds);
  const works = marks.get("dredge-works");
  const regroup = marks.get("dredge-regroup");
  const rest = level.zones.find(({ id }) => id === "dredge-rest");
  const first = marksOnPlume[0];
  if (
    !first ||
    marksOnPlume.length !== outlineIds.length ||
    surface.length !== surfaceIds.length ||
    clear.length !== clearIds.length ||
    !works ||
    !regroup ||
    rest?.kind !== "sanctuary"
  )
    return undefined;
  const plume = [...marksOnPlume, first].map(({ pos }) => pos);
  if (polygonError(plume)) return undefined;
  return { plume, surface, clear, works, regroup, rest };
}

export function dredgingTurbidity(
  passage: DredgingPassage,
  position: Vec2,
): number {
  const edge = clamp(interiorDepth(passage.plume, position) / DREDGING_FEATHER);
  return edge * edge * (3 - 2 * edge);
}
