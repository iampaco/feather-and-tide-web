import { copy } from "../i18n/language";
import type { GooseState } from "../core/game";
import type { Landmark, LevelSchema } from "../levels/schema";
import { gustStrength } from "../levels/wind";
import { leaderOf } from "../simulation/world-rules";
import { gooseFlockStretched } from "./flight-guidance";

const gustApproach = "return-gust-approach";
const leeEntry = "return-lee-entry";
const leeExit = "return-lee-exit";
const weakWind = 0.35;

export function isGooseGustLandmark(id: string): boolean {
  return id === gustApproach || id === leeEntry || id === leeExit;
}

interface GustCue {
  readonly title: string;
  readonly detail: string;
  readonly target: Landmark;
}

export function gooseGustCue(
  state: GooseState,
  level: LevelSchema,
): GustCue | undefined {
  if (state.segmentId !== "S5" || state.phase !== "playing") return;

  const gustZone = level.zones.find(({ id }) => id === "return-gust");
  const approach = level.landmarks.find(({ id }) => id === gustApproach);
  const entry = level.landmarks.find(({ id }) => id === leeEntry);
  const exit = level.landmarks.find(({ id }) => id === leeExit);
  if (
    gustZone?.kind !== "interference" ||
    !gustZone.gust ||
    !approach ||
    !entry ||
    !exit
  )
    return;

  const { pos } = leaderOf(state);
  if (state.occupied.includes("return-lee")) {
    const stretched = gooseFlockStretched(state);
    if (pos.z >= exit.pos.z && !stretched) return;
    return {
      title: copy("已进入背风水道", "Entered the sheltered channel"),
      detail: stretched
        ? copy(
            "收速，让队尾也进入背风水道。",
            "Ease off so the tail can reach the sheltered channel.",
          )
        : state.formation >= 0.94
          ? copy(
              "保持航向，借背风直飞。",
              "Hold your heading and fly straight through the shelter.",
            )
          : copy(
              "对准出口后可再次结阵。",
              "Line up with the exit before forming up again.",
            ),
      target: exit,
    };
  }
  if (
    pos.z < approach.pos.z - 16 ||
    pos.z > entry.pos.z + 3 ||
    Math.abs(pos.x - approach.pos.x) > 29
  )
    return;

  const weakening = gustStrength(gustZone.gust, state.tick) <= weakWind;
  return {
    title: weakening
      ? copy(
          "阵风已弱 · 可转入背风水道",
          "Gust easing · You can turn into the sheltered channel",
        )
      : copy(
          "前方阵风 · 可结阵直飞",
          "Gust ahead · Form up for straight flight",
        ),
    detail: weakening
      ? copy(
          "斜切进水道，转向来不及时可先解阵。",
          "Cut across into the channel. Break formation first if you need a sharper turn.",
        )
      : copy(
          "也可放慢，等风纹稀疏再转入背风水道。",
          "You can also slow down and wait for the wind streaks to thin before turning in.",
        ),
    target: entry,
  };
}
