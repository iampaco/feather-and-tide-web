import { copy, isEnglish, levelLabel } from "../i18n/language";
import type { ActorState, GooseState } from "../core/game";
import { distance, type Vec2 } from "../core/math";
import { contains, sweptCircle } from "../levels/geometry";
import type { Landmark, LevelSchema, Zone } from "../levels/schema";
import { tailwindReedBankId } from "../levels/tailwind-practice";
import { sampleWind } from "../levels/wind";
import { GOOSE, headingVector } from "../simulation/goose";
import { gooseGoalBlocker, leaderOf } from "../simulation/world-rules";

const lookaheadSeconds = 3.5;
const crosswindLeadDistance = 42;
const compactFlockDistance = 21;
const flockApproachSpeed = GOOSE.cruise * 0.65;
const tailwindTailGap = 30;

type Hazard = Extract<Zone, { kind: "hazard" }>;
type FlightThreat = "sweep" | "glass" | "ridge" | "other";

interface Cue {
  readonly title: string;
  readonly detail: string;
}

export function gooseFlockStretched(state: GooseState): boolean {
  const { pos } = leaderOf(state);
  return state.actors.some(
    (actor) =>
      actor.status !== "strayed" && distance(actor.pos, pos) > tailwindTailGap,
  );
}

export function gooseTailwindCue(
  state: GooseState,
  level: LevelSchema,
): (Cue & { readonly glider?: true }) | undefined {
  if (state.segmentId !== "S1" || state.phase !== "playing") return;
  const leader = leaderOf(state);
  const glider = level.encounters?.glider;
  const encounter = state.encounters;
  if (glider && encounter) {
    if (encounter.clearingWing)
      return {
        glider: true,
        title: copy("伞翼擦近雁群", "The glider wing brushed the flock"),
        detail: copy(
          "沿开阔水面飞出，过伞后可以重新结阵。",
          "Fly out over open water. Form up again once you’ve cleared the wing.",
        ),
      };
    const nearCourse =
      leader.pos.x >
        Math.min(glider.launch.x, glider.crossTo.x) - glider.span &&
      leader.pos.x <
        Math.max(glider.launch.x, glider.crossTo.x) + glider.span &&
      leader.pos.z >= glider.noticeZ + 7 &&
      leader.pos.z < 135;
    if (
      nearCourse &&
      (encounter.glider === "inflating" || encounter.glider === "crossing")
    )
      return {
        glider: true,
        title: copy(
          "滑翔伞起飞，外侧水面开阔",
          "Glider taking off · Open water on the outside",
        ),
        detail: copy(
          "可以缓行让伞先过，或沿外侧带队绕行。",
          "Slow down to let it pass, or lead the flock around the outside.",
        ),
      };
  }
  const { drift } = sampleWind(level, leader.pos, state.tick);
  const tailAtBank = state.occupied.includes(tailwindReedBankId);
  if (state.occupied.includes("tailwind-second") && drift.z > 0.4)
    return {
      title: copy("借到第二道顺风", "Riding the second tailwind"),
      detail:
        tailAtBank || gooseFlockStretched(state)
          ? copy(
              "队尾拉开了 · 收速让雁群靠拢。",
              "The flock is stretching. Ease off to let the tail catch up.",
            )
          : state.formation >= 0.94
            ? copy(
                "航向稳定时可短暂加速，留意队尾。",
                "Try a short boost once aligned, and watch the tail.",
              )
            : copy(
                "风正推着雁群前进。对准风纹后可重新结阵。",
                "Line up with the wind streaks, then form up again.",
              ),
    };
  if (state.occupied.includes("tailwind-wide-water") && drift.z < -0.4)
    return {
      title: copy(
        "宽水面 · 逆风减慢推进",
        "Open water · Headwind slows the flock",
      ),
      detail: copy(
        "沿宽水面航标绕过芦苇浅滩，再转正结阵。",
        "Bank around the reed bank on the buoy side, then straighten and form up.",
      ),
    };
  if (leader.pos.z < 133 || leader.pos.z >= 182) return;
  return {
    title: copy(
      "选航线 · 借顺风或飞宽水面",
      "Choose a route · Tailwind or open water",
    ),
    detail:
      state.formation > 0
        ? copy(
            "解阵斜切借顺风，或沿宽水面航标提前缓转。",
            "Break formation for the wind cut, or bank early toward the open-water marker.",
          )
        : copy(
            "斜切借第二道顺风，或沿宽水面航标绕过芦苇。",
            "Cut across to the second tailwind, or follow the open-water marker around the reeds.",
          ),
  };
}

interface HazardCue extends Cue {
  readonly threat: FlightThreat;
  readonly ridgeRecovery?: GooseState["ridgeRecovery"];
}

interface RouteMark {
  readonly mark: Landmark;
  readonly label: string;
}

interface SupplyMark extends RouteMark {
  readonly stocked: boolean;
}

interface FlockCue extends Cue {
  readonly tail?: ActorState;
}

export interface CrosswindPickup {
  readonly actorId: string;
  readonly distanceToCircle: number;
}

interface RecoveryTarget {
  readonly mark: Landmark;
  readonly zone: Zone;
}

interface SupplyCue extends Cue {
  readonly id:
    | "none"
    | "refilling"
    | "gathering"
    | "resting"
    | "depleted-rest"
    | "depleted"
    | "low-supply"
    | "low-rest"
    | "low-no-target";
  readonly recovering: boolean;
  readonly target?: RecoveryTarget;
}

export function supplyAvailable(
  state: GooseState,
  zone: Pick<Zone, "id"> | undefined,
): boolean {
  return zone !== undefined && (state.supply[zone.id] ?? 0) > 0;
}

function hazardKind(zone: Hazard): FlightThreat {
  if (zone.id === "sweep") return "sweep";
  if (zone.id === "ridge-wall") return "ridge";
  return zone.appearance ?? "other";
}

function predictedHazard(
  state: GooseState,
  level: LevelSchema,
): Hazard | undefined {
  if (!state.airborne) return;
  const leader = leaderOf(state);
  const heading = headingVector(leader.heading);
  const reach = Math.max(GOOSE.cruise, leader.speed) * lookaheadSeconds;
  return level.zones.find(
    (zone): zone is Hazard =>
      zone.kind === "hazard" &&
      (zone.id === tailwindReedBankId ? [leader] : state.actors).some(
        ({ status, pos }) =>
          status !== "strayed" &&
          sweptCircle(
            zone.points,
            pos,
            { x: pos.x + heading.x * reach, z: pos.z + heading.z * reach },
            GOOSE.hitRadius,
          ),
      ),
  );
}

export function flightThreat(
  state: GooseState,
  level: LevelSchema,
): FlightThreat | undefined {
  const hazard = predictedHazard(state, level);
  return hazard && hazardKind(hazard);
}

function clearFlightLine(level: LevelSchema, from: Vec2, to: Vec2): boolean {
  return !level.zones.some(
    (zone) =>
      zone.kind === "hazard" &&
      sweptCircle(zone.points, from, to, GOOSE.hitRadius),
  );
}

function windfarmBay(
  state: GooseState,
  level: LevelSchema,
): SupplyMark | undefined {
  const mark = level.landmarks.find(({ id }) => id === "reserve-entry");
  const supply = level.zones.find(({ id }) => id === "reserve-supply");
  const { pos } = leaderOf(state);
  if (
    !mark ||
    !supply ||
    state.occupied.includes("reserve") ||
    pos.z >= mark.pos.z + 24 ||
    !clearFlightLine(level, pos, mark.pos)
  )
    return;
  const stocked = supplyAvailable(state, supply);
  return {
    mark,
    stocked,
    label: stocked
      ? levelLabel(mark)
      : copy("浅湾 · 可休整", "Shallow Bay · Safe to rest"),
  };
}

export function gooseWindfarmOptions(
  state: GooseState,
  level: LevelSchema,
  threat: FlightThreat | undefined,
): {
  readonly direct?: RouteMark;
  readonly bay?: SupplyMark;
  readonly cue?: Cue;
} {
  if (state.segmentId !== "S4" && !state.occupied.includes("wind-warning"))
    return {};
  const { pos } = leaderOf(state);
  const entrance = level.landmarks.find(({ id }) => id === "outer-mark");
  const exit = level.landmarks.find(({ id }) => id === "wind-exit");
  const eastExit = level.landmarks.find(({ id }) => id === "wind-east-exit");
  const sweep = level.zones.find(({ id }) => id === "sweep");
  const eastSide =
    sweep &&
    pos.x > Math.max(...sweep.points.map(({ x }) => x)) + GOOSE.hitRadius;
  const approachClear = entrance && clearFlightLine(level, pos, entrance.pos);
  const eastClear = eastExit && clearFlightLine(level, pos, eastExit.pos);
  const westExit =
    entrance &&
    exit &&
    pos.z > entrance.pos.z &&
    threat !== "sweep" &&
    clearFlightLine(level, pos, exit.pos);
  const mark =
    eastClear && (eastSide || !approachClear)
      ? eastExit
      : westExit
        ? exit
        : entrance;
  const direct = mark && {
    mark,
    label:
      mark === entrance
        ? levelLabel(mark)
        : copy("沿外围继续", "Follow the outer channel"),
  };
  const bay = windfarmBay(state, level);
  const cue =
    direct && bay && mark === entrance && pos.z < entrance.pos.z && !threat
      ? {
          title: copy("风场外围 · 先选航道", "Wind farm · Choose your route"),
          detail: isEnglish()
            ? `The outer channel goes straight through. ${bay.stocked ? "Turn into the shallow bay to refuel." : "Rest in the shallow bay."}`
            : `外围水道可直达，${bay.stocked ? copy("转入浅湾可补给。", "Turn into the shallow bay to refuel.") : copy("浅湾可休整。", "Rest in the shallow bay.")}`,
        }
      : undefined;
  return { direct, bay, cue };
}

function stretched(leader: ActorState, actor: ActorState): boolean {
  return (
    actor.status === "loose" ||
    distance(leader.pos, actor.pos) > compactFlockDistance
  );
}

function crosswindTrigger(level: LevelSchema) {
  if (level.id !== "migration") return;
  const trigger = level.triggers.find(({ id }) => id === "crosswind");
  return trigger?.kind === "rescue" ? trigger : undefined;
}

export function gooseCrosswindPickup(
  previous: GooseState,
  state: GooseState,
  level: LevelSchema,
  actorId: string,
): CrosswindPickup | undefined {
  const trigger = crosswindTrigger(level);
  if (
    !trigger ||
    trigger.actorId !== actorId ||
    previous.triggered.includes(trigger.id) ||
    !state.triggered.includes(trigger.id)
  )
    return;
  const tail = state.actors.find(
    ({ id, status }) => id === actorId && status === "strayed",
  );
  if (!tail) return;
  return {
    actorId,
    distanceToCircle: Math.max(
      0,
      distance(leaderOf(state).pos, tail.pos) - GOOSE.rescueRadius,
    ),
  };
}

export function gooseCrosswindApproach(
  state: GooseState,
  level: LevelSchema,
): FlockCue | undefined {
  const trigger = crosswindTrigger(level);
  if (!trigger) return;
  const leader = leaderOf(state);
  if (state.triggered.includes(trigger.id)) {
    if (
      state.segmentId !== "S3" ||
      state.actors.some(({ status }) => status !== "following")
    )
      return;
    if (state.occupied.includes("rescue-lee"))
      return {
        title: copy(
          "背风芦苇湾 · 队伍休整",
          "Sheltered Reed Bay · Flock resting",
        ),
        detail: copy(
          "缓行恢复体力，再飞向风场。",
          "Slow down to recover stamina before the wind farm.",
        ),
      };
    const bay = level.landmarks.find(({ id }) => id === "rescue-bay");
    if (bay && leader.pos.z >= bay.pos.z - 18)
      return {
        title: copy("队伍已重新靠拢", "The flock is back together"),
        detail: copy(
          "前方水面开阔，也可转入背风芦苇湾休整。",
          "Continue over open water or rest in Sheltered Reed Bay.",
        ),
      };
    return;
  }
  const start = Math.min(...trigger.points.map(({ z }) => z));
  if (leader.pos.z < start - crosswindLeadDistance || leader.pos.z >= start)
    return;
  const tail = state.actors.find(({ id }) => id === trigger.actorId);
  if (!tail) return;
  const tailStretched = stretched(leader, tail);
  const preparing =
    leader.speed <= flockApproachSpeed || state.formation >= 0.94;
  if (preparing && !tailStretched)
    return {
      title: copy(
        "前方侧风 · 队尾已靠拢",
        "Crosswind ahead · Flock close together",
      ),
      detail: copy(
        "保持队尾靠近。遇侧风掉队时，折返更短。",
        "Keep the last geese close so you can reach them quickly if they separate.",
      ),
      tail,
    };
  if (preparing)
    return {
      title: copy(
        "前方侧风 · 给队尾留时间",
        "Crosswind ahead · Give the flock time",
      ),
      detail: copy(
        "留意队尾间距。靠得越近，掉队后越好接应。",
        "The closer the last geese are, the easier it is to reach them if they separate.",
      ),
      tail,
    };
  return {
    title: copy(
      "前方侧风 · 放慢留意队尾",
      "Crosswind ahead · Slow and watch the flock",
    ),
    detail: tailStretched
      ? copy(
          "队尾已拉长。提前缓行或结阵，掉队后少折返。",
          "The flock has stretched out. Slow down or form up so you have less distance to turn back.",
        )
      : copy(
          "提前缓行或结阵，让队尾靠近，掉队后少折返。",
          "Slow down or form up early so the flock stays within easy reach.",
        ),
    tail,
  };
}

export function gooseLandingApproach(
  state: GooseState,
  level: LevelSchema,
  goal: Zone | undefined,
): FlockCue | undefined {
  if (state.segmentId !== "S6" || !goal) return;
  const leader = leaderOf(state);
  if (gooseGoalBlocker(leader, goal) === null) return;
  const water = level.zones.find(({ id }) => id === "reeds");
  if (!water || !contains(water.points, leader.pos)) return;
  let trailing: ActorState | undefined;
  let greatestGap = 0;
  for (const actor of state.actors) {
    if (
      actor.id === state.leaderId ||
      gooseGoalBlocker(actor, goal) !== "outside" ||
      !stretched(leader, actor)
    )
      continue;
    const gap = distance(leader.pos, actor.pos);
    if (gap <= greatestGap) continue;
    greatestGap = gap;
    trailing = actor;
  }
  if (trailing)
    return {
      title:
        leader.speed > flockApproachSpeed
          ? copy(
              "放慢飞行，先让雁群靠拢",
              "Slow down and let the flock close up",
            )
          : copy(
              "沿水面缓飞，等队尾跟上",
              "Fly slowly over the water while the last geese catch up",
            ),
      detail: copy(
        "水面宽阔，可缓慢转弯，让队尾跟上再飞入芦苇湾。",
        "Make a gentle turn over open water to let the flock catch up before entering the reed bay.",
      ),
      tail: trailing,
    };
  return {
    title: copy(
      "队伍齐整 · 飞入芦苇湾",
      "Flock together · Fly into the reed bay",
    ),
    detail: copy(
      "保持航向，带全队进入落脚水域。",
      "Hold your heading and lead the whole flock into the landing waters.",
    ),
  };
}

export function gooseHazardCue(
  state: GooseState,
  level: LevelSchema,
): HazardCue | undefined {
  if (state.phase !== "playing") return;
  if (state.ridgeRecovery)
    return {
      threat: "ridge",
      ridgeRecovery: state.ridgeRecovery,
      title:
        state.ridgeRecovery === "blocked"
          ? copy("分水岭挡住前进", "The ridge blocks your path")
          : copy("正在脱离分水岭", "Clearing the ridge"),
      detail: copy(
        "先斜向来路拉开，再沿一侧航标绕飞。",
        "Angle back to clear the ridge, then follow the markers on either side.",
      ),
    };
  const leader = leaderOf(state);
  const heading = headingVector(leader.heading);
  const contact = level.zones.find(
    (zone): zone is Hazard =>
      zone.kind === "hazard" &&
      state.occupied.includes(zone.id) &&
      (zone.id !== tailwindReedBankId ||
        sweptCircle(
          zone.points,
          leader.pos,
          {
            x: leader.pos.x + heading.x * GOOSE.hitRadius,
            z: leader.pos.z + heading.z * GOOSE.hitRadius,
          },
          GOOSE.hitRadius,
        )),
  );
  const hazard = contact ?? predictedHazard(state, level);
  if (!hazard) return;
  const threat = hazardKind(hazard);
  switch (threat) {
    case "ridge":
      return {
        threat,
        title: isEnglish()
          ? `${contact ? "Ridge boundary" : "Ridge ahead"} · Follow the markers on either side`
          : `${contact ? copy("分水岭边界", "Ridge boundary") : copy("前方分水岭", "Ridge ahead")} · 沿两侧航标绕行`,
        detail: "",
      };
    case "sweep": {
      const bay = !contact && windfarmBay(state, level);
      return {
        threat,
        title: isEnglish()
          ? `${contact ? "Turbine sweep boundary" : "Turbines ahead"} · Take the outer channel`
          : `${contact ? copy("风机扫掠边界", "Turbine sweep boundary") : copy("前方风机", "Turbines ahead")} · 沿外侧水道绕行`,
        detail: bay
          ? bay.stocked
            ? copy("向浅湾转入可补给", "Turn into the shallow bay to refuel")
            : copy(
                "浅湾补给已用完，可休整",
                "The bay is out of supplies. You can still rest here",
              )
          : "",
      };
    }
    case "glass": {
      const inlet = level.landmarks.find(({ id }) => id === "gallery-inlet");
      const supply = level.zones.find(({ id }) => id === "gallery-supply");
      let detail = copy(
        "外侧河道宽阔直达",
        "The outer river channel is wide and direct",
      );
      if (
        !contact &&
        inlet &&
        supply &&
        leader.pos.z < inlet.pos.z &&
        clearFlightLine(level, leader.pos, inlet.pos)
      )
        detail = supplyAvailable(state, supply)
          ? copy(
              "内廊浅湾可补给，过墙后再转弯 · 外侧河道宽阔直达",
              "Refuel in the inner bay and turn after the wall, or take the wide outer channel.",
            )
          : copy(
              "内廊补给已用完 · 外侧河道宽阔直达",
              "The inner channel is out of supplies. The wide outer channel goes straight through.",
            );
      return {
        threat,
        title: contact
          ? copy(
              "到达玻璃边界 · 沿河道绕行",
              "Glass boundary reached · Follow the river around",
            )
          : copy(
              "前方玻璃幕墙 · 沿航标绕行",
              "Glass facade ahead · Follow the markers around",
            ),
        detail: contact ? "" : detail,
      };
    }
    case "other":
      if (hazard.id === tailwindReedBankId)
        return {
          threat,
          title: contact
            ? copy("芦苇浅滩挡住去路", "The reed bank blocks the way")
            : copy(
                "前方芦苇浅滩 · 从两侧绕行",
                "Reed bank ahead · Pass on either side",
              ),
          detail: copy(
            "沿宽水面航标缓转，或解阵斜切进顺风带。",
            "Bank toward open water, or break formation and cut into the tailwind.",
          ),
        };
      return {
        threat,
        title: isEnglish()
          ? `${contact ? "" : "Ahead: "}${levelLabel(hazard)} · Go around the side`
          : `${contact ? "" : "前方"}${levelLabel(hazard)} · 从侧面绕行`,
        detail: "",
      };
  }
}

export function gooseRouteCue(
  state: GooseState,
  level: LevelSchema,
): Cue | undefined {
  if (level.id !== "migration" || state.segmentId !== "S2") return;
  const lakeSupply = level.zones.find(({ id }) => id === "lake-supply");
  const hasLakeSupply = supplyAvailable(state, lakeSupply);
  const windDetail = state.occupied.includes("pass-wind")
    ? copy(
        "侧风把雁群推向分水岭，小幅调整航向。",
        "Crosswind is pushing the flock toward the ridge. Adjust your heading gently.",
      )
    : state.occupied.includes("pass-wind-return")
      ? copy(
          "侧风转向西坡，小幅调整航向。",
          "Crosswind is shifting toward the west slope. Adjust your heading gently.",
        )
      : "";
  if (state.route === "mountain")
    return {
      title: copy("已进入短山口", "Entered the Mountain Pass"),
      detail:
        windDetail || copy("留意前方横风。", "Watch for crosswinds ahead."),
    };
  if (state.route === "lake")
    return {
      title: copy("已进入长湖路", "Entered the Long Lake Route"),
      detail: hasLakeSupply
        ? copy(
            "带雁群飞入沿岸浅滩可补给。",
            "Bring the flock into the shallows along the shore to refuel.",
          )
        : copy("沿湖面继续飞行。", "Continue over the lake."),
    };
  if (windDetail)
    return {
      title: copy("沿山口航标飞行", "Follow the Mountain Pass markers"),
      detail: windDetail,
    };
  return {
    title: copy(
      "前方分岔 · 先观察，再选路",
      "Fork ahead · Look before choosing",
    ),
    detail: hasLakeSupply
      ? copy(
          "短山口的风先吹向分水岭。长湖靠外岸有补给浅滩。",
          "Wind in the Mountain Pass first blows toward the ridge. The Long Lake Route has supplies in the far shallows.",
        )
      : copy(
          "短山口的风先吹向分水岭。长湖路较远，风势更稳。",
          "Wind in the Mountain Pass first blows toward the ridge. The Long Lake Route is longer with calmer winds.",
        ),
  };
}

function recoveryTarget(
  state: GooseState,
  level: LevelSchema,
  landmarkRange: number,
  windWarning: boolean,
): RecoveryTarget | undefined {
  const { pos } = leaderOf(state);
  const available = level.zones.filter(
    (zone) => zone.kind === "supply" && supplyAvailable(state, zone),
  );
  const resting = level.zones.filter(({ kind }) => kind === "sanctuary");
  const candidates = level.landmarks
    .filter(
      ({ kind }) => kind === "beacon" || kind === "reed" || kind === "water",
    )
    .map((mark) => ({
      mark,
      gap: distance(mark.pos, pos),
      preferred:
        windWarning &&
        (mark.id === "reserve-entry" || mark.id === "wetland-mark"),
    }))
    .filter(({ gap }) => gap <= landmarkRange)
    .sort((a, b) => Number(b.preferred) - Number(a.preferred) || a.gap - b.gap);
  for (const { mark } of candidates) {
    const zone =
      available.find(({ points }) => contains(points, mark.pos)) ??
      resting.find(({ points }) => contains(points, mark.pos));
    if (zone && clearFlightLine(level, pos, mark.pos)) return { mark, zone };
  }
}

export function gooseSupplyCue(
  state: GooseState,
  level: LevelSchema,
  landmarkRange: number,
  windWarning: boolean,
): SupplyCue {
  if (!state.airborne)
    return { id: "none", title: "", detail: "", recovering: false };

  const { pos } = leaderOf(state);
  const supply = level.zones.filter(({ kind }) => kind === "supply");
  const rest = level.zones.find(
    ({ id, kind }) => kind === "sanctuary" && state.occupied.includes(id),
  );
  const needsEnergy = state.energy < 1;
  const resting = needsEnergy && rest !== undefined;
  const here = supply.find(({ points }) => contains(points, pos));
  if (needsEnergy && supplyAvailable(state, here)) {
    // The occupied supply IDs already encode the simulation's flock quorum.
    if (here && state.occupied.includes(here.id))
      return {
        id: "refilling",
        title: copy(
          "正在补给 · 保持队伍靠拢",
          "Refueling · Keep the flock together",
        ),
        detail: copy(
          "留在水域缓行，补充体力。",
          "Stay in the water and fly slowly to recover stamina.",
        ),
        recovering: true,
      };
    return {
      id: "gathering",
      title: copy(
        "放慢飞行，等队伍进入补给区",
        "Slow down and wait for the flock to reach the supplies",
      ),
      detail: copy(
        "大半队伍进入后开始补给。",
        "Refueling starts when most of the flock is inside.",
      ),
      recovering: resting,
    };
  }

  const depleted = here !== undefined && !supplyAvailable(state, here);
  if (resting || (rest && depleted))
    return {
      id: depleted ? "depleted-rest" : "resting",
      title: depleted
        ? copy(
            "补给已用完，可在这里休整",
            "Supplies depleted · You can still rest here",
          )
        : copy("安全水域 · 正在恢复体力", "Safe water · Recovering stamina"),
      detail: copy(
        "在水域缓行，让队伍靠拢。",
        "Stay over the water and fly slowly to let the flock close up.",
      ),
      recovering: resting,
    };
  if (state.energy <= GOOSE.lowEnergy) {
    const target = recoveryTarget(state, level, landmarkRange, windWarning);
    const status =
      state.energy <= GOOSE.boostCutoff
        ? copy("加速受限", "Boost unavailable")
        : copy("体力偏低", "Low stamina");
    return {
      id: !target
        ? "low-no-target"
        : target.zone.kind === "supply"
          ? "low-supply"
          : "low-rest",
      title: target
        ? `${status} · ${target.zone.kind === "supply" ? copy("飞向补给水域", "Fly to the supplies") : copy("飞向安全水域", "Fly to safe water")}`
        : isEnglish()
          ? `${status} · Slow down to save stamina`
          : `${status} · 减速节能`,
      detail: target
        ? isEnglish()
          ? `Follow the marker for ${levelLabel(target.zone)}.`
          : `沿「${levelLabel(target.zone)}」标记飞行。`
        : depleted
          ? copy(
              "这里的补给已用完，直线飞行时结阵可以省力。",
              "Supplies here are depleted. Form up on straight stretches to save stamina.",
            )
          : copy(
              "直线飞行时结阵可以省力。",
              "Form up on straight stretches to save stamina.",
            ),
      recovering: false,
      target,
    };
  }
  return {
    id: depleted ? "depleted" : "none",
    title: depleted
      ? copy("这里的补给已用完", "Supplies here are depleted")
      : "",
    detail: "",
    recovering: false,
  };
}
