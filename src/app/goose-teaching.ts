import { copy, isEnglish } from "../i18n/language";
import type { GooseState } from "../core/game";
import type { InputSettings } from "../input/input";
import { keyLabel, movementLabel } from "../input/keyboard";
import type { LevelSchema } from "../levels/schema";

const glideLessonTicks = 12;
const glideLessonEnd = 70;
const observationDrag = 36;
const formationPracticeEndTick = 1000;
export const gooseTurnLessonStart = 133;
export const gooseTurnLessonEnd = 151;

export interface GooseTeachingProgress {
  readonly learnedGlide: boolean;
  readonly learnedFormation: boolean;
  readonly passedTurnLesson: boolean;
}

export const freshGooseTeaching: GooseTeachingProgress = {
  learnedGlide: false,
  learnedFormation: false,
  passedTurnLesson: false,
};

export interface GooseTeachingInput {
  readonly enabled: boolean;
  readonly state: GooseState;
  readonly level: LevelSchema;
  readonly leaderZ: number;
  readonly touch: boolean;
  readonly settings: Pick<InputSettings, "mirror" | "toggle" | "bindings">;
  readonly abilityHeld: boolean;
  readonly cameraDragDistance: number;
  readonly seenReset: boolean;
  readonly inWind: boolean;
}

export interface GooseTeachingCue {
  readonly id:
    | "takeoff"
    | "glide"
    | "island-glide"
    | "orbit"
    | "recenter"
    | "formation"
    | "forming"
    | "release-formation"
    | "formation-releasing"
    | "turn"
    | "second-tailwind";
  readonly title: string;
  readonly detail: string;
}

function flightLesson(
  progress: GooseTeachingProgress,
  input: GooseTeachingInput,
): GooseTeachingCue | null {
  const { state, level, leaderZ, touch, settings } = input;
  const { bindings } = settings;
  const formationKey = touch
    ? copy("结阵键", "Formation")
    : `${copy(" ", "")}${keyLabel(bindings.formation)}`;
  const abilityPress = settings.toggle
    ? touch
      ? copy("点按", "Tap")
      : copy("按下", "Press")
    : copy("按住", "Hold");
  const abilityRelease = settings.toggle
    ? touch
      ? copy("再点一次", "Tap again")
      : copy("再按一次", "Press again")
    : copy("松开", "Release");

  if (!state.airborne) {
    if (state.segmentId !== level.spawnSegment) return null;
    return {
      id: "takeoff",
      title: touch
        ? isEnglish()
          ? `Hold and drag on the ${settings.mirror ? "right" : "left"} to lead the flock into the air`
          : `在${settings.mirror ? copy("右", "right") : copy("左", "left")}侧按住并拖动，带雁群起飞`
        : isEnglish()
          ? `Take off with ${movementLabel(bindings)} or the arrow keys`
          : `${movementLabel(bindings)} / 方向键起飞`,
      detail: touch
        ? copy(
            "轻推可缓行，推到外圈会加速，更费体力。",
            "Push gently to slow down. Push to the edge to boost and use more stamina.",
          )
        : isEnglish()
          ? `Hold ${keyLabel(bindings.boost)} while flying to boost. Boosting uses more stamina.`
          : `飞行时按住 ${keyLabel(bindings.boost)} 加速，更费体力。`,
    };
  }

  const practice = level.id === "playground";
  if (state.segmentId === "S0" || practice) {
    const waitingForTail =
      state.encounters?.kite === "holding" &&
      level.encounters &&
      leaderZ >= level.encounters.kite.bank.z;
    if (state.encounters?.kite === "lowering") return null;
    const turn = level.landmarks.find(({ id }) => id === "s0-turn");
    if (turn && leaderZ >= turn.pos.z - 18 && leaderZ < turn.pos.z + 8) {
      return {
        id: "island-glide",
        title:
          state.releasedTicks >= glideLessonTicks
            ? copy("正在滑翔 · 前方是雾线", "Gliding · Mist line ahead")
            : copy(
                "沿航标绕过芦苇岛 · 宽水面滑翔",
                "Bank around the reed island · Glide over open water",
              ),
        detail: touch
          ? copy(
              "转正后短暂松开摇杆，再轻推飞向雾线。",
              "Straighten out, release the stick briefly, then push gently toward the mist line.",
            )
          : copy(
              "转正后短暂松开移动键，再沿水道飞向雾线。",
              "Straighten out, release the movement keys briefly, then follow the channel toward the mist line.",
            ),
      };
    }
    if (!waitingForTail && !progress.learnedGlide && leaderZ < glideLessonEnd) {
      return {
        id: "glide",
        title: touch
          ? copy("松开摇杆，试试滑翔", "Release the stick to glide")
          : copy("松开移动键，试试滑翔", "Release the movement keys to glide"),
        detail: practice
          ? copy(
              "雁群会先滑翔，再缓慢盘旋。",
              "The flock glides before slowly circling.",
            )
          : copy(
              "芦苇岛旁是宽水面。雁群会先滑翔，再缓慢盘旋。",
              "There’s open water beside the reed island. The flock will glide, then circle slowly.",
            ),
      };
    }
    if (input.cameraDragDistance < observationDrag) {
      return {
        id: "orbit",
        title: touch
          ? isEnglish()
            ? `Drag the open area on the ${settings.mirror ? "left" : "right"} to look back at the flock`
            : `拖动${settings.mirror ? copy("左", "left") : copy("右", "right")}侧空白处查看队尾`
          : copy("拖动画面查看队尾", "Drag the view to look back at the flock"),
        detail: waitingForTail
          ? copy(
              "岸上的人还握着线，队尾正在经过。",
              "Someone on the bank is still holding the line as the last geese pass.",
            )
          : touch
            ? copy(
                "另一只手可以继续操控飞行。",
                "Keep flying with your other hand.",
              )
            : copy(
                "按住鼠标左键或右键拖动。",
                "Hold either mouse button and drag.",
              ),
      };
    }
    if (!input.seenReset) {
      return {
        id: "recenter",
        title: touch
          ? isEnglish()
            ? `Tap the top ${settings.mirror ? "left" : "right"} to reset the camera`
            : `轻触${settings.mirror ? copy("左", "left") : copy("右", "right")}上角，复位镜头`
          : isEnglish()
            ? `Press ${keyLabel(bindings.recenter)} to return to the follow camera`
            : `按 ${keyLabel(bindings.recenter)} 回到跟随视角`,
        detail: copy("飞行会继续。", "The flock will keep flying."),
      };
    }
  }

  const inTailwind = state.segmentId === "S1";
  const second =
    inTailwind && level.landmarks.find(({ id }) => id === "tailwind-next");
  if (
    second &&
    leaderZ < second.pos.z + 3 &&
    state.occupied.includes("tailwind-second")
  ) {
    return {
      id: "second-tailwind",
      title: copy("已进入第二道顺风带", "Entered the second tailwind"),
      detail: copy(
        "顺风正在推着雁群前进，转正后可以结阵。",
        "The tailwind is carrying the flock. Straighten out, then form up.",
      ),
    };
  }
  const approachingBend =
    inTailwind && leaderZ >= gooseTurnLessonStart && !progress.passedTurnLesson;
  if (approachingBend) {
    if (input.abilityHeld) {
      return {
        id: "release-formation",
        title: copy("先解阵，再转弯", "Break formation before turning"),
        detail: isEnglish()
          ? `${abilityRelease} ${formationKey} to let the flock spread out.`
          : `${abilityRelease}${formationKey}，让队形舒展开。`,
      };
    }
    if (state.formation > 0) {
      return {
        id: "formation-releasing",
        title: copy("队形正在舒展", "The flock is spreading out"),
        detail: copy(
          "准备飞向第二道顺风带。",
          "Get ready to turn toward the second tailwind.",
        ),
      };
    }
    return {
      id: "turn",
      title: copy("飞向第二道顺风带", "Fly toward the second tailwind"),
      detail: copy("沿前方航标转弯。", "Follow the marker around the bend."),
    };
  }

  const canPracticeFormation =
    (practice && state.tick < formationPracticeEndTick) ||
    (inTailwind && (leaderZ < gooseTurnLessonStart || input.inWind));
  if (!canPracticeFormation || progress.learnedFormation) return null;
  return input.abilityHeld
    ? {
        id: "forming",
        title: settings.toggle
          ? copy("雁群正在排成 V 字", "The flock is forming a V")
          : copy("保持结阵", "Stay in formation"),
        detail: settings.toggle
          ? copy(
              "成阵后直飞更省力。",
              "Once formed, the flock saves stamina in straight flight.",
            )
          : copy("雁群正在排成 V 字。", "The flock is forming a V."),
      }
    : {
        id: "formation",
        title: isEnglish()
          ? `${abilityPress} ${formationKey} to form a V`
          : `${abilityPress}${formationKey}，排成 V 字`,
        detail: copy(
          "直飞更省力，转弯前再解阵。",
          "Save stamina in straight flight. Break formation before turns.",
        ),
      };
}

export function gooseTeaching(
  progress: GooseTeachingProgress,
  input: GooseTeachingInput,
): { progress: GooseTeachingProgress; cue: GooseTeachingCue | null } {
  if (!input.enabled || input.state.phase !== "playing")
    return { progress, cue: null };

  const { state, leaderZ } = input;
  const learnedGlide =
    progress.learnedGlide ||
    (state.airborne && state.releasedTicks >= glideLessonTicks);
  const learnedFormation = progress.learnedFormation || state.formation >= 1;
  const passedTurnLesson =
    progress.passedTurnLesson ||
    (state.segmentId === "S1" &&
      leaderZ >= gooseTurnLessonEnd &&
      (state.formation === 0 || input.abilityHeld));
  const next =
    learnedGlide === progress.learnedGlide &&
    learnedFormation === progress.learnedFormation &&
    passedTurnLesson === progress.passedTurnLesson
      ? progress
      : { learnedGlide, learnedFormation, passedTurnLesson };
  return { progress: next, cue: flightLesson(next, input) };
}
