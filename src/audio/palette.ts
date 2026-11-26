import type { GameState } from "../core/game";
import type { AnyLevelSchema } from "../levels/schema";

export type ScoreLayer =
  "ambient" | "journey" | "focus" | "tension" | "care" | "release";

export interface FlightMix {
  readonly layer: ScoreLayer;
  readonly lake: boolean;
  readonly music: number;
}

const chapterMusic: Record<ScoreLayer, number> = {
  ambient: 0,
  journey: 0.68,
  focus: 0.61,
  tension: 0.56,
  care: 0.43,
  release: 0.76,
};

export function flightMix(state: GameState, level?: AnyLevelSchema): FlightMix {
  if (state.species !== "goose") {
    const layerAtLead =
      state.species === "whale" ? state.actors[0]?.dive.layer : undefined;
    const zones =
      level?.zones.filter(({ id }) => state.occupied.includes(id)) ?? [];
    const care = state.actors.some(
      ({ status }) => status === "strayed" || status === "rejoining",
    );
    const layer: ScoreLayer =
      state.phase === "landing"
        ? "release"
        : care
          ? "care"
          : zones.some(
                ({ kind }) => kind === "hazard" || kind === "interference",
              )
            ? "tension"
            : zones.some(({ kind }) => kind === "warning")
              ? "focus"
              : zones.some(({ kind }) => kind === "sanctuary")
                ? "release"
                : "journey";
    const depthGain =
      layerAtLead === "deep" ? 0.72 : layerAtLead === "shallow" ? 0.87 : 1;
    return {
      layer,
      lake: false,
      music:
        chapterMusic[layer] * (state.species === "reindeer" ? 0.8 : depthGain),
    };
  }
  const leader = state.actors[0];
  const lake =
    state.segmentId === "S2" &&
    (level && leader ? leader.pos.x > 0 : state.route === "lake");
  const ridge = state.occupied.some(
    (id) => id === "pass-wind" || id === "pass-wind-return",
  );
  const reserve = state.occupied.includes("reserve");
  const regroup = state.occupied.includes("rescue-lee");
  const gallery = state.occupied.includes("gallery-warning");
  const galleryContact = state.occupied.some(
    (id) =>
      id === "gallery-panel-upstream" || id === "gallery-panel-downstream",
  );
  const warned = state.occupied.includes("wind-warning");
  const sweep = state.occupied.includes("sweep");
  const care = state.actors.some(
    (actor) => actor.status === "strayed" || actor.status === "rejoining",
  );
  const layer: ScoreLayer = !state.airborne
    ? "ambient"
    : state.phase === "landing"
      ? "release"
      : care
        ? "care"
        : reserve || regroup
          ? "release"
          : sweep || ridge || galleryContact
            ? "tension"
            : warned ||
                (gallery && state.segmentId === "S5") ||
                (state.segmentId === "S2" && !lake)
              ? "focus"
              : "journey";
  return {
    layer,
    lake,
    music: layer === "ambient" ? 0 : care && layer === "care" ? 0.22 : 0.68,
  };
}

// Original four-beat phrases. The lake variation keeps the route's theme
// pitches and changes their register, rhythm, and timbre.
export const phrases = {
  ambient: { beat: 0.88, melody: [null, null, null, null], bass: 50 },
  journey: { beat: 0.76, melody: [62, 69, 71, 66], bass: 50 },
  focus: { beat: 0.68, melody: [64, null, 66, 69], bass: 47 },
  tension: { beat: 0.62, melody: [62, 64, 66, 64], bass: 45 },
  care: { beat: 0.71, melody: [62, null, 67, 69], bass: 50 },
  release: { beat: 0.89, melody: [66, 69, 74, null], bass: 50 },
} as const;
