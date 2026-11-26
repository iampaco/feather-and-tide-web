import { copy, isEnglish, levelLabel } from "../i18n/language";
import type { ReindeerActor, ReindeerState } from "../core/game";
import { STEP_SEC } from "../core/clock";
import { distance, type Vec2 } from "../core/math";
import { contains, sweptCircle } from "../levels/geometry";
import {
  hoofRadius,
  insideCulvert,
  reindeerFencePassages,
  reindeerShortFenceRunouts,
} from "../levels/reindeer-ground";
import type { Landmark, ReindeerLevel, Zone } from "../levels/schema";
import {
  reindeerDustRefuges,
  sampleReindeerDust,
  type ReindeerDustSample,
} from "../simulation/reindeer-dust";
import { reindeerFollowTarget } from "../simulation/reindeer-trail";
import { REINDEER } from "../simulation/reindeer-tuning";
import {
  goalStatus,
  gooseGoalBlocker,
  leaderOf,
} from "../simulation/world-rules";

interface TailMarker {
  readonly actor: ReindeerActor;
  readonly label: string;
}

interface LocalGuidance {
  readonly notice: string;
  readonly detail: string;
  readonly tail?: TailMarker;
}

export function reindeerWinterBend(
  state: ReindeerState,
  level: ReindeerLevel,
): boolean {
  if (state.segmentId !== "R0") return false;
  const bank = level.barriers.find(({ id }) => id === "snowbank-trail");
  if (!bank) return false;
  const near = Math.min(...bank.points.map(({ z }) => z));
  const far = Math.max(...bank.points.map(({ z }) => z));
  const { z } = leaderOf(state).pos;
  return z >= near - 27 && z <= far;
}

export function reindeerWinterTail(
  state: ReindeerState,
  level: ReindeerLevel,
): ReindeerActor | undefined {
  const snowbank = level.barriers.find(({ id }) => id === "snowbank-trail");
  const leader = leaderOf(state);
  if (
    !snowbank ||
    state.segmentId !== "R0" ||
    leader.pos.z <= Math.max(...snowbank.points.map(({ z }) => z))
  )
    return;
  return state.actors.reduce<ReindeerActor | undefined>((tail, actor) => {
    const gap = distance(actor.pos, leader.pos);
    return gap > REINDEER.gatherRadius &&
      (!tail || gap > distance(tail.pos, leader.pos))
      ? actor
      : tail;
  }, undefined);
}

export function reindeerLandingCompanion(
  previous: ReindeerState,
  current: ReindeerState,
  goal: Zone | undefined,
): ReindeerActor | undefined {
  if (current.phase !== "landing" || !goal) return;
  return current.actors.findLast(
    (actor) =>
      actor.id !== current.leaderId &&
      gooseGoalBlocker(actor, goal) === null &&
      previous.actors.some(
        (prior) =>
          prior.id === actor.id && gooseGoalBlocker(prior, goal) !== null,
      ),
  );
}

export function reindeerPassageGuidance(
  state: ReindeerState,
  level: ReindeerLevel,
): (LocalGuidance & { choices?: boolean; runout?: Vec2 }) | undefined {
  const leader = leaderOf(state);
  const { road } = level;
  let far: number;
  const roadSegment = state.segmentId === "R1";
  const behindFence = ({ pos }: ReindeerActor, index: number) =>
    pos.z < far + hoofRadius(index);
  let runout: Vec2 | undefined;
  if (roadSegment) {
    const shoulder = level.zones.find(({ id }) => id === "far-shoulder");
    const shoulderEnd = shoulder
      ? Math.max(...shoulder.points.map(({ z }) => z))
      : road.culvert.far;
    if (
      !insideCulvert(road, leader.pos) &&
      (leader.pos.z < road.culvert.far ||
        leader.pos.z > shoulderEnd + REINDEER.gatherRadius)
    )
      return;
    far = road.culvert.far;
  } else if (state.segmentId === "R2") {
    const passages = reindeerFencePassages(level);
    const first = passages[0];
    if (!first) return;
    if (leader.pos.z < first.far && leader.pos.z >= first.near - 45)
      return {
        notice: copy(
          "前方可走宽路或短弯",
          "A wide route or a tight turn ahead",
        ),
        detail: copy(
          "先对准缺口，再收速沿直蹄迹带队过栏。",
          "Line up with a gap, ease off, and follow the straight hoofprints through the fence.",
        ),
        choices: true,
      };
    far = passages.findLast(({ far }) => far <= leader.pos.z)?.far ?? -Infinity;
    const currentRow = passages.find(
      ({ far, near }) => leader.pos.z >= near - 7 && leader.pos.z < far,
    );
    if (currentRow && !state.actors.some(behindFence))
      return {
        notice: copy("下一个围栏缺口", "Next fence opening"),
        detail: copy(
          "对准缺口，保持稳定步速。",
          "Line up with the opening and keep a steady pace.",
        ),
      };
    if (leader.pos.z > far + REINDEER.callRadius + REINDEER.gatherRadius)
      return;
    runout = reindeerShortFenceRunouts(level, passages).find(
      ({ gap, end }) =>
        gap.far === far &&
        leader.pos.x >= gap.left &&
        leader.pos.x <= gap.right &&
        leader.pos.z <= end.z + 1,
    )?.end;
  } else return;

  const behind = roadSegment
    ? state.actors.filter(({ pos }) => pos.z < far)
    : state.actors.filter(behindFence);
  const last = behind.reduce<ReindeerActor | undefined>(
    (tail, actor) => (!tail || actor.pos.z < tail.pos.z ? actor : tail),
    undefined,
  );
  const count = `${state.actors.length - behind.length} / ${state.actors.length}`;
  if (roadSegment) {
    return {
      notice: isEnglish() ? `Across: ${count}` : `已到远侧 ${count}`,
      detail: insideCulvert(road, leader.pos)
        ? copy("沿涵洞走到远侧路肩。", "Take the culvert to the far shoulder.")
        : last
          ? copy(
              "靠路肩停步呼唤，或沿蹄迹缓行，给队尾腾出空间。",
              "Stop on the shoulder to call the herd, or follow the hoofprints slowly to leave room behind you.",
            )
          : copy(
              "最后一只也到远侧了。沿蹄迹去缓坡。",
              "Everyone is across. Follow the hoofprints to the gentle slope.",
            ),
      tail:
        last && leader.pos.z >= far
          ? {
              actor: last,
              label: insideCulvert(road, last.pos)
                ? copy(
                    "队尾仍在涵洞",
                    "Trailing reindeer · Still in the culvert",
                  )
                : copy("队尾尚未到远侧", "Trailing reindeer · Still crossing"),
            }
          : undefined,
    };
  }
  return {
    notice: isEnglish() ? `Past this fence: ${count}` : `本排已通过 ${count}`,
    detail: last
      ? copy(
          "给队尾留出直路，再转向下一个缺口。",
          "Leave a straight path for the last reindeer before turning toward the next gap.",
        )
      : copy(
          "最后一只也过栏了，可以转向。",
          "Everyone is through. You can turn now.",
        ),
    tail: last
      ? {
          actor: last,
          label: copy(
            "队尾尚未过栏",
            "Trailing reindeer · Still behind the fence",
          ),
        }
      : undefined,
    runout: last ? runout : undefined,
  };
}

function dustWindowFits(
  dust: ReindeerDustSample,
  level: ReindeerLevel,
  entersIn: number,
  clearsIn: number,
): boolean {
  const { warningTicks, activeTicks, calmTicks } = level.dustCycle;
  const clear = (clearsIn + REINDEER.dustForecastMargin) / STEP_SEC;
  const enter = entersIn / STEP_SEC;
  if (dust.phase === "active")
    return (
      enter >= dust.remainingTicks &&
      clear <= dust.remainingTicks + calmTicks + warningTicks
    );
  const activeStarts =
    dust.remainingTicks + (dust.phase === "calm" ? warningTicks : 0);
  return clear <= activeStarts || enter >= activeStarts + activeTicks;
}

export function reindeerDustGuidance(
  state: ReindeerState,
  level: ReindeerLevel,
):
  | (LocalGuidance & {
      readonly next?: Landmark;
      readonly fork: boolean;
      readonly phase?: ReindeerDustSample["phase"];
    })
  | undefined {
  const leader = leaderOf(state);
  if (state.segmentId !== "R3") return;
  const dust = sampleReindeerDust(level, state.tick, leader.pos);
  const refuges = reindeerDustRefuges.flatMap(({ zone, sign }) => {
    const shelter = level.zones.find((item) => item.id === zone);
    const marker = level.landmarks.find((item) => item.id === sign);
    return shelter?.kind === "sanctuary" && marker
      ? [
          {
            shelter,
            marker,
            near: Math.min(...shelter.points.map(({ z }) => z)),
          },
        ]
      : [];
  });
  const [entry, firstShelter] = refuges;
  if (!entry || !firstShelter) return;
  const atFork =
    leader.pos.z < entry.near && distance(leader.pos, entry.marker.pos) <= 33;
  if (!atFork && (leader.pos.x <= 0 || state.route === "greenbelt")) return;
  const current = refuges.find(({ shelter }) =>
    contains(shelter.points, leader.pos),
  );
  const next = atFork
    ? firstShelter
    : refuges.find(({ near }) => near > leader.pos.z);
  if (!current && !next) return;
  const inside = current ? goalStatus(state, current.shelter) : undefined;
  const dustZones = level.zones.filter(({ id }) =>
    level.dustCycle.zoneIds.includes(id),
  );
  const exposed = state.actors.filter(
    (actor) =>
      actor.id !== leader.id &&
      dustZones.some(({ points }) => contains(points, actor.pos)),
  );
  const tail = exposed.reduce<ReindeerActor | undefined>(
    (last, actor) => (!last || actor.pos.z < last.pos.z ? actor : last),
    undefined,
  );
  const atExit = current?.shelter.id === "dust-exit-rest";
  if (atExit && inside?.canLand) return;
  const group =
    current && inside
      ? isEnglish()
        ? `In ${levelLabel(current.shelter)}: ${inside.arrived} of ${inside.expected}`
        : `${levelLabel(current.shelter)}内 ${inside.arrived} / ${inside.expected}`
      : exposed.length
        ? isEnglish()
          ? `Still in the dust: ${exposed.length}`
          : `${exposed.length} 位同伴还在雾带`
        : "";
  let action = "";
  if (next && (atFork || current)) {
    const band = dustZones.find(
      ({ points }) =>
        Math.abs(next.near - Math.max(...points.map(({ z }) => z))) <= 1,
    );
    if (band) {
      const startZ = atFork ? entry.marker.pos.z : leader.pos.z;
      const approach = atFork ? distance(leader.pos, entry.marker.pos) : 0;
      const bandStart = Math.min(...band.points.map(({ z }) => z));
      const back = Math.max(
        ...state.actors.map(({ pos }) => leader.pos.z - pos.z),
      );
      const untilBand =
        (approach + Math.max(0, bandStart - startZ)) / REINDEER.cruise;
      const untilClear =
        (approach + next.near - startZ + back) / REINDEER.cruise;
      const together = state.actors.every(
        (actor) =>
          actor.status === "following" &&
          distance(actor.pos, leader.pos) <= REINDEER.gatherRadius,
      );
      const fits =
        state.actors.every(
          ({ status }) => status !== "strayed" && status !== "rejoining",
        ) && dustWindowFits(dust, level, untilBand, untilClear);
      const canDivert = atFork || current === entry;
      if (canDivert && state.energy <= REINDEER.lowEnergy)
        action = copy(
          "体力偏低，恢复带有补给。",
          "Low stamina. Supplies are available in the Restored Greenbelt.",
        );
      else if (fits && (together || atFork))
        action = copy(
          "现在可出发 · 保持巡航，队尾预计能赶上。",
          "Go now at a steady pace. Lead the whole herd into shelter.",
        );
      else if (atFork)
        action = copy(
          "近路窗口偏紧，可在入口背风地收队，或走恢复带。",
          "The shortcut window is tight. Regroup in the sheltered area at the entrance or take the Restored Greenbelt.",
        );
      else if (!together)
        action = inside?.canLand
          ? copy(
              "先停步呼唤，再看出发空档。",
              "Stop and call the herd together, then watch for a crossing window.",
            )
          : canDivert
            ? copy(
                "队尾还远，可先收队，或折返走恢复带。",
                "The herd is stretched out. Regroup here or turn back for the Restored Greenbelt.",
              )
            : copy(
                "队尾还远，先在背风地收队。",
                "The herd is stretched out. Regroup in the sheltered area.",
              );
      else
        action = canDivert
          ? copy(
              "下一程窗口偏紧，可等雾散或走恢复带。",
              "The next window is tight. Wait for the dust to settle or take the Restored Greenbelt.",
            )
          : copy(
              "下一程窗口偏紧，可在背风地等雾散。",
              "The next window is tight. Wait for the dust to settle in the sheltered area.",
            );
    }
  }
  const destination =
    next && !atFork
      ? isEnglish()
        ? `Ahead: ${levelLabel(next.shelter)}`
        : `前方是${levelLabel(next.shelter)}`
      : "";
  const seconds = Math.ceil(dust.remainingTicks * STEP_SEC);
  return {
    notice: atExit
      ? copy("矿区出口缓坡", "Gentle Slope Beyond the Mine")
      : dust.phase === "calm"
        ? isEnglish()
          ? `Dust settled · Next dust warning in ${seconds}s`
          : `尘雾平静 · ${seconds} 秒后起雾预告`
        : dust.phase === "warning"
          ? isEnglish()
            ? `Dust picking up in ${seconds}s`
            : `尘雾将增强 · ${seconds} 秒后`
          : isEnglish()
            ? `Dust active · Settles in ${seconds}s`
            : `尘雾活跃 · ${seconds} 秒后平静`,
    detail: [group, action, destination].filter(Boolean).join(" · "),
    next: atFork ? undefined : next?.marker,
    fork: atFork,
    phase: atExit ? undefined : dust.phase,
    tail: tail
      ? {
          actor: tail,
          label: copy(
            "队尾还在尘雾里",
            "Trailing reindeer · Still in the dust",
          ),
        }
      : undefined,
  };
}

interface TeammateGuidance {
  readonly kind: "rescue" | "returning" | "fence" | "on-way";
  readonly actor: ReindeerActor;
  readonly label: string;
  readonly notice: string;
  readonly detail: string;
  readonly wideOpening: boolean;
  readonly opening?: Vec2;
}

function fenceBlocks(
  level: ReindeerLevel,
  from: Vec2,
  to: Vec2,
  actorIndex: number,
): boolean {
  return level.barriers.some(
    ({ kind, points }) =>
      kind === "fence" && sweptCircle(points, from, to, hoofRadius(actorIndex)),
  );
}

function openingFor(
  level: ReindeerLevel,
  from: Vec2,
  to: Vec2,
  index: number,
): Vec2 | undefined {
  const blocked = level.barriers.filter(
    ({ kind, points }) =>
      kind === "fence" && sweptCircle(points, from, to, hoofRadius(index)),
  );
  const passages = reindeerFencePassages(level).filter(
    (passage) =>
      passage.wholeHerd &&
      blocked.some(
        ({ points }) => Math.min(...points.map(({ z }) => z)) === passage.near,
      ),
  );
  passages.sort(
    (a, b) =>
      Math.abs(a.near - from.z) - Math.abs(b.near - from.z) ||
      b.right - b.left - (a.right - a.left),
  );
  const gap = passages[0];
  return gap
    ? { x: (gap.left + gap.right) / 2, z: (gap.near + gap.far) / 2 }
    : undefined;
}

export function reindeerTeammateGuidance(
  state: ReindeerState,
  level: ReindeerLevel,
  goal?: Zone,
): TeammateGuidance | undefined {
  const leader = leaderOf(state);
  const herd = state.actors.slice(1);
  const strayed = herd.filter(({ status }) => status === "strayed");
  const rescue = strayed.reduce<ReindeerActor | undefined>(
    (first, actor) =>
      !first ||
      (actor.rescueTicks ?? Infinity) < (first.rescueTicks ?? Infinity)
        ? actor
        : first,
    undefined,
  );
  if (rescue) {
    const retreating = rescue.retreatZ !== null;
    const acrossFence =
      !retreating &&
      fenceBlocks(level, rescue.pos, leader.pos, state.actors.indexOf(rescue));
    return {
      kind: "rescue",
      actor: rescue,
      label: retreating
        ? copy("正在离开车道", "Leaving the road")
        : copy("待接应", "Awaiting rescue"),
      notice:
        strayed.length === 1
          ? copy("一位同伴需要接应", "A companion needs help")
          : isEnglish()
            ? `Companions awaiting rescue: ${strayed.length}`
            : `${strayed.length} 位同伴需要接应`,
      detail: retreating
        ? copy(
            "先在路肩等它离开车道。",
            "Wait on the shoulder until the companion leaves the road.",
          )
        : acrossFence
          ? copy(
              "沿缺口回到同伴一侧，靠近并缓行。",
              "Go through a gap to reach your companion, then approach slowly.",
            )
          : copy(
              "沿可通行的路线靠近并缓行。",
              "Follow a clear route to your companion and approach slowly.",
            ),
      wideOpening: acrossFence,
      opening: acrossFence
        ? openingFor(
            level,
            rescue.pos,
            leader.pos,
            state.actors.indexOf(rescue),
          )
        : undefined,
    };
  }

  const returning = herd.findLast(({ status }) => status === "rejoining");
  if (returning)
    return {
      kind: "returning",
      actor: returning,
      label: copy("正在归队", "Rejoining"),
      notice: copy("同伴正在归队", "A companion is rejoining"),
      detail: goal
        ? copy(
            "在落脚区等它跟上。",
            "Wait inside the arrival area for your companion.",
          )
        : copy(
            "在安全处放慢，等它跟上。",
            "Slow down somewhere safe and wait for your companion.",
          ),
      wideOpening: false,
    };

  const waiting = goal
    ? herd.filter((actor) => gooseGoalBlocker(actor, goal) !== null)
    : herd;
  if (state.segmentId === "R2" || state.segmentId === "R3") {
    const blocked = waiting.findLast((actor) => {
      if (actor.speed > 0.14) return false;
      const index = state.actors.indexOf(actor);
      const { point } = reindeerFollowTarget(
        level,
        state,
        leader,
        actor,
        index,
      );
      return fenceBlocks(level, actor.pos, point, index);
    });
    if (blocked)
      return {
        kind: "fence",
        actor: blocked,
        label: copy("被围栏隔开", "Separated by a fence"),
        notice: copy(
          "队尾被围栏隔开",
          "Trailing reindeer · Separated by a fence",
        ),
        detail: copy(
          "沿缺口回到队尾一侧，停步呼唤后再带队过栏。",
          "Go back through the gap. Stop and call, then lead the herd through together.",
        ),
        wideOpening: true,
        opening: openingFor(
          level,
          blocked.pos,
          reindeerFollowTarget(
            level,
            state,
            leader,
            blocked,
            state.actors.indexOf(blocked),
          ).point,
          state.actors.indexOf(blocked),
        ),
      };
  }

  const tail = goal
    ? waiting.at(-1)
    : waiting.findLast(({ status }) => status === "loose");
  if (tail)
    return {
      kind: "on-way",
      actor: tail,
      label: goal
        ? copy("尚未抵达", "Still on the way")
        : copy("队尾", "Trailing reindeer"),
      notice: goal
        ? copy("同伴还没进落脚区", "A companion is outside the arrival area")
        : copy("队尾还在路上", "The last reindeer is still on the trail"),
      detail: goal
        ? copy(
            "在这里等队尾走进来。",
            "Wait here for the last reindeer to come in.",
          )
        : copy(
            "在安全处停步等它走近。",
            "Stop somewhere safe and wait for your companion.",
          ),
      wideOpening: false,
    };
}
