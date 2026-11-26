import { copy, isEnglish, levelLabel } from "../i18n/language";
import type { WaterLayer, WhaleActor, WhaleState } from "../core/game";
import { distance, type Vec2 } from "../core/math";
import { STEP_SEC } from "../core/clock";
import { contains, sweptCircle } from "../levels/geometry";
import type { Landmark, WhaleLevel, Zone } from "../levels/schema";
import { currentGuide, type WaterCurrent } from "../levels/whale-current";
import {
  whaleCheckpointArea,
  whaleCheckpointAvailable,
  type WhaleCheckpointArea,
} from "../levels/whale-checkpoint";
import { dredgingPassage } from "../levels/whale-dredging";
import { kelpApproaches } from "../levels/whale-kelp";
import { netApproaches } from "../levels/whale-net";
import { insideNoise, isCyclicNoise, noisePhase } from "../levels/whale-noise";
import {
  hazardPoints,
  hazardStep,
  hazardTravelBounds,
  isWhaleBreakwater,
  isWhaleNet,
  occupiesLayer,
} from "../levels/whale-geometry";
import {
  podSlot,
  WHALE,
  whaleRescueApproach,
} from "../simulation/whale-motion";
import {
  goalStatus,
  leaderOf,
  surfaced,
  whaleGoalBlocker,
  whaleSupplyStatus,
} from "../simulation/world-rules";
import { shipPassage, surfaceCruiseWindow } from "./whale-ship";

export interface WhaleTutorialView {
  readonly dragged: boolean;
  readonly reset: boolean;
  readonly moved: boolean;
  readonly stopped: boolean;
  readonly submerged: boolean;
  readonly recovered: boolean;
  readonly toggle: boolean;
  readonly desktop: boolean;
  readonly moveKey?: string;
  readonly diveKey?: string;
  readonly resetKey?: string;
}

interface WhaleMarker {
  readonly id: string;
  readonly label: string;
  readonly labelEn?: string;
  readonly pos: Vec2;
  readonly kind:
    "landmark" | "route" | "supply" | "rescue" | "hazard" | "gathering";
  readonly allowEdge?: boolean;
  readonly depth?: number;
}

export interface WhaleGuidance {
  readonly notice: string;
  readonly detail: string;
  readonly danger: string;
  readonly warningDetail: string;
  readonly markers: readonly WhaleMarker[];
  readonly depthLabel: string;
  readonly depthCue: string;
  readonly breath: number;
  readonly transition: number;
  readonly rescue: { readonly ticks: number; readonly progress: number } | null;
  readonly routeCohesion: number | null;
  readonly arrival: {
    readonly visible: boolean;
    readonly caption: string;
    readonly count: string;
    readonly detail: string;
  };
  readonly tutorial: boolean;
}

interface ActivityCue {
  readonly notice: string;
  readonly detail: string;
  readonly markers: readonly WhaleMarker[];
}

type Hazard = Extract<Zone, { kind: "hazard" }>;
type NetBounds = { readonly near: number; readonly far: number };
type RestZone = Zone & { readonly kind: "sanctuary" | "supply" };

interface Refill {
  readonly zone: RestZone;
  readonly pos: Vec2;
}

const waterLayers: readonly WaterLayer[] = ["surface", "shallow", "deep"];

function waterLabel(layer: WaterLayer): string {
  switch (layer) {
    case "surface":
      return copy("水面", "Surface");
    case "shallow":
      return copy("浅潜", "Shallow");
    case "deep":
      return copy("深潜", "Deep");
  }
}

function center(points: readonly Vec2[]): Vec2 {
  const corners = points.slice(0, -1);
  return {
    x: corners.reduce((sum, point) => sum + point.x, 0) / corners.length,
    z: corners.reduce((sum, point) => sum + point.z, 0) / corners.length,
  };
}

function shipDirectionMarker(
  ship: Hazard,
  tick: number,
  name = copy("货船", "Cargo ship"),
): WhaleMarker {
  const step = hazardStep(ship, tick);
  const direction =
    Math.abs(step.x) >= Math.abs(step.z)
      ? step.x < 0
        ? copy("向西", "westbound")
        : copy("向东", "eastbound")
      : step.z < 0
        ? copy("向南", "southbound")
        : copy("向北", "northbound");
  return {
    id: ship.id,
    label: `${name} · ${direction}`,
    pos: center(hazardPoints(ship, tick)),
    kind: "hazard",
  };
}

function landmark(level: WhaleLevel, id: string): Landmark | undefined {
  return level.landmarks.find((mark) => mark.id === id);
}

function netBounds(nets: readonly Hazard[]): NetBounds | undefined {
  if (!nets.length) return undefined;
  const bounds = nets.map(hazardTravelBounds);
  return {
    near: Math.min(...bounds.map(({ min }) => min.z)),
    far: Math.max(...bounds.map(({ max }) => max.z)),
  };
}

function netsBlock(nets: readonly Hazard[], from: Vec2, to: Vec2): boolean {
  return nets.some(({ points }) =>
    sweptCircle(points, from, to, WHALE.hitRadius),
  );
}

function routeMarkers(
  state: WhaleState,
  level: WhaleLevel,
  leader: WhaleActor,
  tips: boolean,
  nets: readonly Hazard[] = [],
): readonly WhaleMarker[] {
  const target = (id: string, z?: number): WhaleMarker[] => {
    const mark = landmark(level, id);
    return mark
      ? [{ ...mark, kind: "route", pos: { ...mark.pos, z: z ?? mark.pos.z } }]
      : [];
  };
  const past = (id: string, margin = 5): boolean => {
    const mark = landmark(level, id);
    return !mark || leader.pos.z >= mark.pos.z - margin;
  };
  switch (state.segmentId) {
    case "W0": {
      const next = level.segments.find(({ id }) => id === "W1");
      const exit = target(
        "bay-exit",
        past("bay-exit") ? next?.start : undefined,
      );
      if (tips && !past("bay-bend-entry", 6))
        return [...target("bay-bend-entry"), ...exit];
      if (tips && !past("bay-turn", 15))
        return [...target("bay-turn"), ...exit];
      if (tips && !past("bay-stop", 6)) return [...target("bay-stop"), ...exit];
      return exit;
    }
    case "W1": {
      const bendIn = landmark(level, "ship-bend-in");
      const bendOut = landmark(level, "ship-bend-out");
      const seawall = level.zones.find(
        (zone) =>
          zone.id === "ship-approach-breakwater" && isWhaleBreakwater(zone),
      );
      const warning = level.zones.find(
        ({ id }) => id === "ship-approach-breakwater-warning",
      );
      if (
        bendIn &&
        bendOut &&
        seawall?.kind === "hazard" &&
        warning &&
        contains(warning.points, leader.pos) &&
        !past(bendOut.id, 3)
      ) {
        const { min, max } = hazardTravelBounds(seawall);
        const side = leader.pos.x < min.x - WHALE.hitRadius ? -1 : 1;
        const lateral =
          side < 0 ? (landmark(level, "ship-west-bend-in") ?? bendIn) : bendIn;
        const exit =
          side < 0
            ? (landmark(level, "ship-west-bend-out") ?? bendOut)
            : bendOut;
        const abreast = leader.pos.z < max.z + WHALE.hitRadius;
        const aligned = side * leader.pos.x >= Math.abs(lateral.pos.x) - 5;
        const next = abreast && !aligned ? lateral : exit;
        return [{ ...next, kind: "route" }];
      }
      if (!past("ship-wait")) return target("ship-wait");
      if (!past("ship-dive")) return target("ship-dive");
      if (!past("ship-clear")) {
        const ship = level.zones.find(
          (zone): zone is Hazard => zone.kind === "hazard" && !!zone.motion,
        );
        const far = ship ? shipPassage(ship).far : -Infinity;
        const across = state.actors.every(({ pos }) => pos.z > far);
        return target("ship-clear").map((mark) =>
          across
            ? mark
            : {
                ...mark,
                label: "过船集合水域",
                labelEn: "Gathering Water Beyond the Lane",
              },
        );
      }
      if (!state.triggered.includes("C1")) return target("first-checkpoint");
      return past("net-preview-wide", -4)
        ? [...target("net-short-entry"), ...target("net-wide-entry")]
        : [...target("net-preview-short"), ...target("net-preview-wide")];
    }
    case "W2": {
      const net = netBounds(nets);
      const gap = landmark(level, "net-gap");
      const wide = landmark(level, "net-wide");
      if (!net || !gap || !wide) return target("net-detour");
      const before = net.near - 12;
      const clear = net.far + WHALE.hitRadius;
      const onWideLine = leader.pos.x > (wide.pos.x + gap.pos.x) / 2;
      const blocked = (pos: Vec2) => netsBlock(nets, leader.pos, pos);
      if (leader.pos.z < net.near - 34)
        return [netApproaches.short[0], netApproaches.wide[0]].flatMap((id) =>
          target(id),
        );
      if (leader.pos.z < before)
        return [gap, wide].flatMap(({ id, pos }) =>
          target(id, blocked(pos) ? leader.pos.z : pos.z),
        );
      if (leader.pos.z <= clear) {
        const ahead = { x: leader.pos.x, z: clear + 1 };
        if (blocked(ahead)) {
          const alignZ = Math.min(leader.pos.z, before);
          return [...target("net-gap", alignZ), ...target("net-wide", alignZ)];
        }
        return target(onWideLine ? "net-wide" : "net-gap");
      }
      const exit = onWideLine
        ? past("net-clear")
          ? "net-wide-merge"
          : "net-clear"
        : "net-short-clear";
      return target(past(exit) ? "branch-overlook" : exit);
    }
    case "W3": {
      if (state.routeLocked)
        return state.triggered.includes("C2")
          ? target("surface-here")
          : target("second-checkpoint");
      const choices = level.triggers.flatMap((gate) => {
        if (
          gate.kind !== "route" ||
          (state.route && leader.pos.z >= (gate.crossingZ ?? Infinity))
        )
          return [];
        const id = gate.route === "quiet" ? "quiet-entry" : "shipping-entry";
        return target(id, gate.crossingZ);
      });
      if (choices.length) return choices;
      if (state.route === "quiet" && !past("quiet-bend")) {
        if (!past("quiet-mid")) return target("quiet-mid");
        if (!past("quiet-arc"))
          return [...target("quiet-arc"), ...target("quiet-pool")];
        return target("quiet-bend");
      }
      return target("merge-here");
    }
    case "W4": {
      const checkpoint = level.zones.find(({ id }) => id === "C2");
      if (
        checkpoint &&
        state.routeLocked &&
        !state.triggered.includes("C2") &&
        checkpoint.points.some(({ z }) => leader.pos.z <= z)
      )
        return target("second-checkpoint");
      return target(past("surface-here") ? "offshore-marker" : "surface-here");
    }
    default:
      return [];
  }
}

function netRescueWaypoint(
  level: WhaleLevel,
  nets: readonly Hazard[],
  net: NetBounds,
  from: Vec2,
  to: Vec2,
): Vec2 | undefined {
  const blocked = (a: Vec2, b: Vec2) => netsBlock(nets, a, b);
  if (!blocked(from, to)) return undefined;
  const approaches = ["net-gap", "net-wide"].flatMap((id) => {
    const x = landmark(level, id)?.pos.x;
    if (x === undefined) return [];
    return [
      { x, z: net.near - 8 },
      { x, z: net.far + 8 },
    ];
  });
  // Route over only the authored passage approaches. A whale may be between
  // the two nets, so the nearest opening alone cannot choose a safe return.
  const waiting = [from, ...approaches, to];
  const costs = new Map<Vec2, number>([[from, 0]]);
  const firstStep = new Map<Vec2, Vec2>();
  while (waiting.length) {
    waiting.sort(
      (a, b) => (costs.get(a) ?? Infinity) - (costs.get(b) ?? Infinity),
    );
    const point = waiting.shift();
    const cost = point && costs.get(point);
    if (!point || cost === undefined) break;
    if (point === to) return firstStep.get(point);
    for (const next of waiting) {
      const candidate = cost + distance(point, next);
      if (candidate >= (costs.get(next) ?? Infinity) || blocked(point, next))
        continue;
      costs.set(next, candidate);
      firstStep.set(next, firstStep.get(point) ?? next);
    }
  }
  return undefined;
}

function netRunoutCue(
  level: WhaleLevel,
  nets: readonly Hazard[],
  net: NetBounds,
  leader: WhaleActor,
): WhaleMarker | undefined {
  const runout = landmark(level, "net-runout");
  if (!runout || leader.pos.z < (net.near + net.far) / 2) return;
  // Lead the pod away from the mesh along the player's actual clear line.
  const pos = { x: leader.pos.x, z: runout.pos.z };
  if (
    leader.pos.z + WHALE.hitRadius >= pos.z ||
    netsBlock(nets, leader.pos, pos)
  )
    return;
  return {
    id: "net-runout-cue",
    label: copy("先沿这里直游", "Keep swimming straight here"),
    pos,
    kind: "route",
  };
}

function approachingHazard(
  state: WhaleState,
  level: WhaleLevel,
  leader: WhaleActor,
): Hazard | undefined {
  const warning = level.zones.find(
    (zone) =>
      zone.kind === "warning" &&
      (state.occupied.includes(zone.id) ||
        state.actors.some((actor) => contains(zone.points, actor.pos))),
  );
  return level.zones.find(
    (zone): zone is Hazard =>
      zone.kind === "hazard" &&
      (state.occupied.includes(zone.id) ||
        (warning?.kind === "warning" && zone.id === warning.hazardId) ||
        (state.segmentId === "W1" &&
          zone.motion !== undefined &&
          level.zones.some(
            (water) =>
              water.id === "waiting-water" &&
              contains(water.points, leader.pos),
          ))),
  );
}

function shipRefill(
  level: WhaleLevel,
  leader: WhaleActor,
  passage: ReturnType<typeof shipPassage>,
): Refill | undefined {
  // W1 spans both banks of a crossing. A depleted pod must not be routed
  // through the hull's travel band just because the current hull is elsewhere.
  const before = leader.pos.z - passage.near <= passage.far - leader.pos.z;
  const zone = level.zones.find(
    (candidate): candidate is RestZone =>
      candidate.kind === "sanctuary" &&
      candidate.id === (before ? "waiting-water" : "crossing-rest") &&
      candidate.points.every(({ z }) =>
        before ? z < passage.near : z > passage.far,
      ),
  );
  if (!zone) return undefined;
  if (contains(zone.points, leader.pos)) return { zone, pos: leader.pos };
  const anchor = landmark(level, before ? "ship-dive" : "ship-clear")?.pos;
  const middle = center(zone.points);
  const alongside = { x: leader.pos.x, z: anchor?.z ?? middle.z };
  return { zone, pos: contains(zone.points, alongside) ? alongside : middle };
}

function safeWater(
  state: WhaleState,
  level: WhaleLevel,
  leader: WhaleActor,
): Refill | undefined {
  const rest = level.zones.filter(
    (zone): zone is RestZone =>
      zone.kind === "sanctuary" ||
      (zone.kind === "supply" && (state.supply[zone.id] ?? 0) > 0),
  );
  const current = rest.find((zone) => contains(zone.points, leader.pos));
  if (current) return { zone: current, pos: leader.pos };
  const hazards = level.zones.filter(
    (zone): zone is Hazard => zone.kind === "hazard",
  );
  return rest
    .flatMap((zone) =>
      [center(zone.points), ...level.landmarks.map((mark) => mark.pos)]
        .filter((pos) => contains(zone.points, pos))
        .map((pos) => ({ zone, pos })),
    )
    .filter(({ pos }) =>
      hazards.every(
        (hazard) =>
          !occupiesLayer(hazard, leader.dive.layer) ||
          !sweptCircle(
            hazardPoints(hazard, state.tick),
            leader.pos,
            pos,
            WHALE.hitRadius,
          ),
      ),
    )
    .sort(
      (a, b) => distance(a.pos, leader.pos) - distance(b.pos, leader.pos),
    )[0];
}

function arrivalCue(
  state: WhaleState,
  level: WhaleLevel,
  leader: WhaleActor,
  view: WhaleTutorialView,
): WhaleGuidance["arrival"] & {
  readonly marker?: WhaleMarker;
  readonly center?: WhaleMarker;
} {
  const goal = level.zones.find((zone) => zone.kind === "goal");
  if (!goal || !["playing", "landing"].includes(state.phase))
    return { visible: false, caption: "", count: "", detail: "" };
  const ready = goalStatus(state, goal);
  const count = `${ready.arrived}/${ready.expected}`;
  if (state.phase === "landing")
    return {
      visible: true,
      caption: copy("全队汇合", "The whole pod is together"),
      count,
      detail: "",
    };
  const leaderInside = contains(goal.points, leader.pos);
  if (!leaderInside)
    return { visible: false, caption: "", count: "", detail: "" };
  if (state.actors.some(({ status }) => status === "strayed"))
    return {
      visible: true,
      caption: copy("仍有同伴待接应", "A companion still needs rescue"),
      count,
      detail: "",
    };
  if (state.actors.some(({ status }) => status === "rejoining"))
    return {
      visible: true,
      caption: copy("等待同伴归队", "Waiting for a companion to rejoin"),
      count,
      detail: "",
    };
  if (!surfaced(leader))
    return {
      visible: true,
      caption: copy("浮出水面汇合", "Surface to reunite"),
      count,
      detail: leader.dive.direction === "up" ? "" : surfaceHint(view),
    };
  const outside = state.actors.findLast(
    (actor) => whaleGoalBlocker(actor, goal) === "outside",
  );
  const needsRoom = outside && podNeedsRoom(state, leader, goal);
  const waiting =
    outside ??
    state.actors.findLast(
      (actor) => whaleGoalBlocker(actor, goal) === "submerged",
    );
  if (ready.arrived === ready.expected) {
    return {
      visible: true,
      caption: copy("全队已到齐", "The whole pod is in place"),
      count,
      detail: copy(
        "松开方向滑停，进入汇合",
        "Release movement and glide to a stop to reunite",
      ),
    };
  }
  const marker =
    waiting &&
    companionMarker(
      waiting,
      outside
        ? copy("同伴 · 仍在区外", "Companion · Outside the reunion area")
        : waiting.dive.direction === "up"
          ? copy("同伴 · 正在上浮", "Companion · Surfacing")
          : isEnglish()
            ? `Companion · ${waterLabel(waiting.dive.layer)}`
            : `同伴 · ${waterLabel(waiting.dive.layer)}`,
    );
  return {
    visible: true,
    caption: outside
      ? copy(
          "等待同伴进入汇合区",
          "Waiting for the pod to enter the reunion area",
        )
      : copy("等待同伴上浮", "Waiting for the pod to surface"),
    count,
    detail: needsRoom
      ? copy(
          "向亮水中央再游，给同伴留出空间，再松手滑停",
          "Swim closer to the center of the bright water to make room, then release to glide to a stop",
        )
      : outside
        ? leader.speed > WHALE.reunionSpeed
          ? copy(
              "松开方向滑停，等队尾进入汇合区",
              "Release to glide to a stop and let the trailing whales enter",
            )
          : copy(
              "已停稳 · 可转镜看队尾入区",
              "Stopped · Look back to watch the last whales enter",
            )
        : leader.speed > WHALE.reunionSpeed
          ? copy(
              "松开方向滑停，等同伴浮出水面",
              "Release to glide to a stop and wait for the pod to surface",
            )
          : copy(
              "在水面等候，可转镜观察同伴",
              "Wait at the surface and look around for your companions",
            ),
    marker,
    center: needsRoom
      ? routeMarkers(state, level, leader, false)[0]
      : undefined,
  };
}

function surfaceHint(view: WhaleTutorialView): string {
  const control = view.desktop
    ? (view.diveKey ?? "Space")
    : copy("下潜键", "Dive");
  return view.toggle
    ? isEnglish()
      ? `Tap ${control} again to surface`
      : `再点按 ${control} 上浮`
    : isEnglish()
      ? `Release ${control} to surface`
      : `松开 ${control} 上浮`;
}

function bayHint(
  state: WhaleState,
  leader: WhaleActor,
  view: WhaleTutorialView,
): Pick<WhaleGuidance, "notice" | "detail" | "tutorial"> & {
  readonly marker?: WhaleMarker;
} {
  const key = view.desktop ? (view.diveKey ?? "Space") : copy("下潜键", "Dive");
  const step = (notice: string, detail = "", marker?: WhaleMarker) => ({
    notice,
    detail,
    marker,
    tutorial: true,
  });
  if (!view.recovered) {
    const tailMarker = baySubmergedTail(state);
    if (leader.dive.direction === "up")
      return step(
        copy("正在上浮", "Surfacing"),
        copy("可停稳，回望同伴", "Glide to a stop and look back at the pod"),
        tailMarker,
      );
    if (leader.dive.layer !== "surface")
      return step(
        surfaceHint(view),
        copy("浮回水面可以换气", "Return to the surface to breathe"),
      );
    if (leader.dive.direction === "down")
      return step(
        copy("等深度栏显示浅潜", "Wait for the depth gauge to show Shallow"),
      );
    if (view.submerged) {
      if (tailMarker)
        return step(
          copy("领鲸已浮出水面", "The lead whale has surfaced"),
          copy(
            "可回望，等同伴陆续上浮",
            "Look back and watch for the rest of the pod to surface",
          ),
          tailMarker,
        );
      return step(
        copy("全队已浮出水面", "The whole pod has surfaced"),
        copy(
          "留在水面，看呼吸条回满",
          "Stay at the surface until your breath refills",
        ),
      );
    }
  }
  if (!view.moved)
    return step(
      view.desktop
        ? isEnglish()
          ? `Swim with ${view.moveKey ?? "WASD"} or the arrow keys`
          : `${view.moveKey ?? "WASD"} / 方向键游动`
        : copy("轻推摇杆起游", "Push the stick gently to start swimming"),
      copy(
        "沿水面出湾，或到银鱼群旁浅潜借流",
        "Leave the bay at the surface, or dive shallow near the silver fish to ride the current",
      ),
    );
  if (!view.stopped)
    return step(
      view.desktop
        ? copy(
            "松开方向键，滑行至停稳",
            "Release the movement keys to glide to a stop",
          )
        : copy("松开摇杆，滑行至停稳", "Release the stick to glide to a stop"),
      copy(
        "在内湾弯标前松手，滑进静水后回望海蚀拱",
        "Release at the inner-bay marker and glide into calm water, then look back at the sea arch",
      ),
    );
  if (!view.dragged)
    return step(
      view.desktop
        ? copy("拖动画面观察队尾", "Drag the view to look back at the pod")
        : copy(
            "拖动空白水面观察队尾",
            "Drag the open water to look back at the pod",
          ),
    );
  if (!view.reset)
    return step(
      view.desktop
        ? isEnglish()
          ? `Press ${view.resetKey ?? "R"} to reset the camera`
          : `按 ${view.resetKey ?? "R"} 复位镜头`
        : copy("轻触镜头复位", "Tap Reset Camera"),
    );
  if (!view.recovered)
    return step(
      isEnglish()
        ? `${view.toggle ? "Tap" : "Hold"} ${key} to try a shallow dive`
        : `${view.toggle ? copy("点按", "Tap") : copy("按住", "Hold")} ${key} 试试浅潜`,
    );
  return surfaced(leader) && leader.speed < 0.15
    ? {
        notice: copy("可以出湾了", "Ready to leave the bay"),
        detail: copy(
          "跟随航标，或留在海湾继续练习",
          "Follow the markers or stay in the bay to practice",
        ),
        tutorial: false,
      }
    : { notice: "", detail: "", tutorial: false };
}

function baySubmergedTail(state: WhaleState): WhaleMarker | undefined {
  const tail = state.actors.slice(1).findLast((actor) => !surfaced(actor));
  if (tail)
    return companionMarker(
      tail,
      tail.dive.direction === "up"
        ? copy("队尾 · 正在上浮", "Trailing whale · Surfacing")
        : isEnglish()
          ? `Trailing whale · ${waterLabel(tail.dive.layer)}`
          : `队尾 · ${waterLabel(tail.dive.layer)}`,
    );
}

function checkpointWaiting(
  state: WhaleState,
  level: WhaleLevel,
  leader: WhaleActor,
): WhaleCheckpointArea | undefined {
  return level.zones
    .filter(({ points }) => contains(points, leader.pos))
    .map(whaleCheckpointArea)
    .find(
      (area) =>
        area &&
        whaleCheckpointAvailable(
          level,
          area,
          state.triggered,
          state.routeLocked,
        ),
    );
}

function podNeedsRoom(
  state: WhaleState,
  leader: WhaleActor,
  zone: Zone,
): boolean {
  return state.actors.some(
    (_, index) =>
      index > 0 &&
      !contains(zone.points, podSlot(leader, index, state.cohesion)),
  );
}

function companionMarker(actor: WhaleActor, label: string): WhaleMarker {
  return {
    id: actor.id,
    label,
    kind: "gathering",
    pos: actor.pos,
    depth: actor.dive.depth,
  };
}

function checkpointCue(
  state: WhaleState,
  checkpoint: Zone,
  leader: WhaleActor,
  view: WhaleTutorialView,
): { detail: string; marker?: WhaleMarker } {
  const { arrived, expected } = goalStatus(state, checkpoint);
  const outside = state.actors.findLast(
    (actor) => whaleGoalBlocker(actor, checkpoint) === "outside",
  );
  const submerged = state.actors.findLast(
    (actor) =>
      actor.id !== leader.id &&
      whaleGoalBlocker(actor, checkpoint) === "submerged",
  );
  const action = !surfaced(leader)
    ? leader.dive.direction === "up"
      ? copy("正在上浮，水面可换气", "Surfacing to breathe")
      : surfaceHint(view)
    : outside
      ? podNeedsRoom(state, leader, checkpoint)
        ? copy(
            "向静水中央再游，等队尾进入",
            "Swim farther into calm water to give the pod room to enter",
          )
        : copy(
            "减速或停稳，等同伴入区",
            "Slow down or stop and let the pod enter",
          )
      : copy(
          "保持在水面，等全队上浮后保存",
          "Stay at the surface. The game saves when the whole pod surfaces.",
        );
  const marker = outside
    ? companionMarker(
        outside,
        copy("同伴 · 尚未进入检查点", "Companion · Outside the checkpoint"),
      )
    : submerged &&
      companionMarker(
        submerged,
        submerged.dive.direction === "up"
          ? copy("同伴 · 正在上浮", "Companion · Surfacing")
          : isEnglish()
            ? `Companion · ${waterLabel(submerged.dive.layer)}`
            : `同伴 · ${waterLabel(submerged.dive.layer)}`,
      );
  return {
    detail: isEnglish()
      ? `Ready at surface: ${arrived}/${expected} · ${action}`
      : `水面就绪 ${arrived}/${expected} · ${action}`,
    marker,
  };
}

function shipWarning(
  ship: Hazard,
  state: WhaleState,
  leader: WhaleActor,
  level: WhaleLevel,
  passage: ReturnType<typeof shipPassage>,
  lowBreath: boolean,
  podInPassage: boolean,
): { detail: string; tail?: WhaleMarker } {
  if (lowBreath)
    return {
      detail: podInPassage
        ? copy(
            "先带全队离开船道",
            "Lead the whole pod out of the shipping lane first",
          )
        : copy(
            "先在船道外换气，再选择等船或深潜",
            "Breathe outside the lane, then choose whether to wait or dive deep",
          ),
    };
  const behind = state.actors
    .filter((actor) => actor.pos.z <= passage.far)
    .sort((a, b) => a.pos.z - b.pos.z);
  const clearedCount = `${state.actors.length - behind.length}/${state.actors.length}`;
  const trailing = behind.find(({ id }) => id !== leader.id);
  if (leader.dive.layer === "deep") {
    const vulnerable = behind.find(
      (actor) =>
        actor.id !== leader.id &&
        (actor.dive.direction !== null ||
          occupiesLayer(ship, actor.dive.layer)),
    );
    if (vulnerable) {
      const layer = waterLabel(vulnerable.dive.layer);
      return {
        detail:
          leader.pos.z < passage.near
            ? isEnglish()
              ? `Trailing whale at ${layer} · Wait outside the lane until everyone is deep`
              : `队尾仍在${layer} · 在船道外等全队下潜`
            : isEnglish()
              ? `Trailing whale at ${layer} · Stay deep and keep swimming. Across: ${clearedCount}`
              : `队尾仍在${layer} · 保持深潜向前，已清船 ${clearedCount}`,
        tail: companionMarker(
          vulnerable,
          isEnglish() ? `Trailing whale · ${layer}` : `队尾 · ${layer}`,
        ),
      };
    }
    if (leader.pos.z > passage.far && trailing)
      return {
        detail: isEnglish()
          ? `Across: ${clearedCount} · Stay deep and keep going until everyone clears the lane`
          : `已清船 ${clearedCount} · 保持深潜，向前等队尾清船`,
        tail: companionMarker(
          trailing,
          copy(
            "队尾 · 尚未清船",
            "Trailing whale · Still in the shipping lane",
          ),
        ),
      };
    if (leader.pos.z < passage.near) {
      const canStart = state.actors.every(
        (actor) =>
          actor.status === "following" &&
          actor.dive.layer === "deep" &&
          actor.dive.direction === null &&
          actor.dive.breath * WHALE.breathSeconds.deep >=
            (passage.far - actor.pos.z) / WHALE.cruise +
              WHALE.cruise / WHALE.acceleration,
      );
      return {
        detail: canStart
          ? copy(
              "全队已深潜 · 可向前起游，等最后一只清船再上浮",
              "The whole pod is deep. Swim ahead and wait until everyone clears the lane before surfacing",
            )
          : copy(
              "先在船道外集队换气，再深潜起游",
              "Gather the pod and breathe outside the lane before diving deep",
            ),
      };
    }
    if (leader.pos.z <= passage.far)
      return {
        detail: isEnglish()
          ? `The pod is deep · Keep swimming. Across: ${clearedCount}`
          : `全队已深潜 · 继续向前，已清船 ${clearedCount}`,
      };
  }
  if (leader.pos.z > passage.far && trailing)
    return {
      detail: isEnglish()
        ? `Across: ${clearedCount} · Keep swimming until the last whales clear the lane`
        : `已清船 ${clearedCount} · 继续向前，等队尾清船`,
      tail: companionMarker(
        trailing,
        copy("队尾 · 尚未清船", "Trailing whale · Still in the shipping lane"),
      ),
    };
  if (leader.pos.z > passage.far)
    return {
      detail: copy(
        `全队已过船道 ${clearedCount} · 沿航标前往静水换气`,
        `Across: ${clearedCount} · Follow the markers to calm water and breathe`,
      ),
    };
  if (leader.pos.z >= passage.near)
    return {
      detail: isEnglish()
        ? `Make room past the shipping lane. Across: ${clearedCount}`
        : `越过船道后给队尾留出空间 · 已清船 ${clearedCount}`,
    };
  const waiting = landmark(level, "ship-wait");
  if (
    surfaced(leader) &&
    state.actors.every(surfaced) &&
    leader.pos.z >= (waiting?.pos.z ?? passage.near) &&
    surfaceCruiseWindow(ship, state, leader, passage.far)
  )
    return {
      detail: copy(
        "前方有水面空档 · 沿当前航线向前巡航",
        "Clear at the surface · Cruise straight ahead",
      ),
    };
  return {
    detail: copy(
      "减速让船先过，或等全队深潜后穿越",
      "Slow down to let the ship pass, or wait for the whole pod to dive deep",
    ),
  };
}

function shippingCue(
  state: WhaleState,
  level: WhaleLevel,
  leader: WhaleActor,
):
  | (Pick<WhaleGuidance, "notice" | "detail" | "markers"> & {
      readonly navigation?: readonly WhaleMarker[];
    })
  | undefined {
  const zone = level.zones.find(isCyclicNoise);
  if (!zone) return;
  const near = Math.min(...zone.points.map(({ z }) => z));
  const far = Math.max(...zone.points.map(({ z }) => z));
  const phase = noisePhase(zone.cycle, state.tick);
  const tail = state.actors.findLast(
    (actor) => actor.id !== leader.id && insideNoise(zone, actor.pos),
  );
  const markers: WhaleMarker[] = [];
  if (phase.active && tail)
    markers.push(
      companionMarker(
        tail,
        copy("队尾 · 仍在噪声带", "Trailing whale · Still in the noise zone"),
      ),
    );
  const supply = landmark(level, "shipping-supply");
  if (
    supply &&
    leader.pos.z >= near &&
    leader.pos.z < supply.pos.z + 15 &&
    (state.supply["shipping-refill"] ?? 0) > 0
  )
    markers.push({ ...supply, kind: "supply" });
  if (leader.pos.z >= near) {
    if (phase.active && (insideNoise(zone, leader.pos) || tail))
      return {
        notice: copy("噪声影响各水层", "Noise affects all depths"),
        detail: copy(
          "继续游出噪声带，在带后静水等队尾收拢",
          "Swim out of the noise zone and regroup in the calm water beyond it",
        ),
        markers,
      };
    return {
      notice: copy("已选近航道", "Short Channel chosen"),
      detail: copy(
        "沿航标前往汇流处",
        "Follow the markers to where the channels meet",
      ),
      markers,
    };
  }
  const forward = { pos: leader.pos, heading: 0 };
  const tailZ = Math.min(
    ...state.actors.map(({ pos }) => pos.z),
    podSlot(forward, state.actors.length - 1, state.cohesion).z,
  );
  const crossingTime =
    (far - tailZ) / WHALE.cruise + WHALE.cruise / WHALE.acceleration;
  const waiting = ["shipping-wait", "shipping-hold"].flatMap(
    (id): WhaleMarker[] => {
      const mark = landmark(level, id);
      return mark && distance(mark.pos, leader.pos) > 8
        ? [{ ...mark, kind: "route" }]
        : [];
    },
  );
  if (
    crossingTime >
    (zone.cycle.periodTicks - zone.cycle.activeTicks) * STEP_SEC
  )
    return {
      notice: copy(
        "近航道 · 靠近待航标",
        "Short Channel · Approach the waiting marker",
      ),
      detail: copy(
        "到带前停稳，等队尾靠近后再看空档",
        "Stop short of the noise zone, let the pod catch up, and watch for a quiet window",
      ),
      markers,
      navigation: waiting,
    };
  const ready =
    !phase.active && phase.remainingTicks * STEP_SEC >= crossingTime;
  const exitWater = supply ? { ...supply, kind: "supply" as const } : undefined;
  return {
    notice: ready
      ? copy("安静空档 · 可巡航通过", "Quiet window · Cruise through")
      : phase.active
        ? copy(
            "噪声带 · 等下一轮",
            "Noise zone active · Wait for the next window",
          )
        : copy(
            "安静空档已不足 · 等下一轮",
            "Quiet window too short · Wait for the next one",
          ),
    detail: ready
      ? copy(
          "朝出口巡航，留意队尾",
          "Cruise toward the exit and watch the trailing whales",
        )
      : copy(
          "在带前减速，或进入侧边静水湾等队尾",
          "Slow before the noise zone, or wait for the pod in the sheltered bay",
        ),
    markers,
    navigation: ready && exitWater ? [exitWater] : waiting,
  };
}

function findCurrent(level: WhaleLevel, id: string): WaterCurrent | undefined {
  return level.zones.find(
    (zone): zone is WaterCurrent => zone.kind === "current" && zone.id === id,
  );
}

function currentCue(
  state: WhaleState,
  leader: WhaleActor,
  zone: WaterCurrent | undefined,
):
  | (Pick<WhaleGuidance, "notice" | "detail"> & { marker: WhaleMarker })
  | undefined {
  if (!zone) return;
  const { entry, exit } = currentGuide(zone);
  const inside = contains(zone.points, leader.pos);
  const active = state.occupied.includes(zone.id);
  if (inside || active)
    return {
      notice: active
        ? copy("正在借流", "Riding the current")
        : levelLabel(zone),
      detail: active
        ? copy(
            "顺着水纹推进更省力，出带可上浮换气",
            "Follow the ripples to save energy. Surface to breathe after leaving the current",
          )
        : surfaced(leader)
          ? copy(
              "浅潜后顺着水纹轻推，或继续沿水面航标",
              "Dive shallow and follow the ripples, or follow the surface markers",
            )
          : copy(
              "朝水纹箭头轻推，或上浮回宽水面",
              "Push gently in the direction of the ripples, or surface in open water",
            ),
      marker: {
        id: "current-exit",
        label: copy("顺流方向", "Current direction"),
        pos: exit,
        kind: "route",
      },
    };
  if (leader.pos.z <= entry.z && distance(leader.pos, entry) < 48)
    return {
      notice: levelLabel(zone),
      detail: copy(
        "可下潜顺水纹借流，也可沿宽水面的航标通过",
        "Dive and follow the ripples to ride the current, or follow the markers over open water",
      ),
      marker: {
        id: "current-entry",
        label: copy("顺流入口 · 可选", "Current entrance · Optional"),
        pos: entry,
        kind: "route",
      },
    };
}

function reefPassageCue(
  state: WhaleState,
  level: WhaleLevel,
  leader: WhaleActor,
  view: WhaleTutorialView,
  lowBreath: boolean,
):
  | (Pick<WhaleGuidance, "notice" | "detail" | "markers"> & {
      inEddy?: boolean;
      riding?: boolean;
    })
  | undefined {
  const first = findCurrent(level, "reef-current");
  const second = findCurrent(level, "reef-current-east");
  const eddy = level.zones.find(({ id }) => id === "reef-eddy");
  const pool = landmark(level, "current-eddy");
  if (!first || !second || !eddy || !pool) return;

  const poolMarker: WhaleMarker = { ...pool, kind: "supply", allowEdge: false };
  const secondEntry: WhaleMarker = {
    id: "reef-current-east-entry",
    label: copy("第二段顺流入口", "Second current entrance"),
    pos: currentGuide(second).entry,
    kind: "route",
  };
  if (contains(eddy.points, leader.pos)) {
    const { arrived, expected } = goalStatus(state, eddy);
    const tail = state.actors.findLast(
      (actor) => actor.id !== leader.id && whaleGoalBlocker(actor, eddy),
    );
    const next = lowBreath
      ? surfaced(leader)
        ? copy(
            "缓游或停稳，等全队换气",
            "Slow down or stop so the whole pod can breathe",
          )
        : isEnglish()
          ? `${surfaceHint(view)}. Wait for the pod in calm water`
          : `${surfaceHint(view)}，在静水等同伴`
      : surfaced(leader)
        ? arrived === expected
          ? copy(
              "可停留换气，或下潜接第二段",
              "Stop for a breath or dive to ride the second current",
            )
          : copy(
              "往静水中央缓游，给队尾留出空间",
              "Swim farther into calm water to make room for the pod",
            )
        : copy(
            "继续顺流，或上浮换气集队",
            "Ride the current onward or surface to breathe and regroup",
          );
    return {
      notice: copy("礁间静水", "Calm Reef Waters"),
      detail: isEnglish()
        ? `Ready at surface: ${arrived}/${expected} · ${next}`
        : `水面就绪 ${arrived}/${expected} · ${next}`,
      markers: [
        poolMarker,
        secondEntry,
        ...(tail
          ? [
              companionMarker(
                tail,
                contains(eddy.points, tail.pos)
                  ? copy("队尾 · 尚未上浮", "Trailing whale · Submerged")
                  : copy(
                      "队尾 · 尚在静水外",
                      "Trailing whale · Outside calm water",
                    ),
              ),
            ]
          : []),
      ],
      inEddy: true,
    };
  }

  const firstExit = currentGuide(first).exit;
  const onFirst = leader.pos.z < firstExit.z;
  const zone = onFirst ? first : second;
  const cue = currentCue(state, leader, zone);
  if (!cue) return;
  const riding = state.occupied.includes(zone.id);
  const approaching = cue.marker.id === "current-entry";
  const marker =
    approaching && !onFirst
      ? secondEntry
      : {
          ...cue.marker,
          label: approaching
            ? copy("第一段顺流入口", "First current entrance")
            : isEnglish()
              ? `Toward ${levelLabel(zone)}`
              : `${levelLabel(zone)}方向`,
        };
  const nearPool =
    onFirst && !approaching && distance(leader.pos, firstExit) < 32;
  let detail = cue.detail;
  if (nearPool)
    detail = copy(
      "转向顺着第二段漂粒，或进静水上浮等队尾",
      "Bank into the second current, or surface in calm water to wait for the pod",
    );
  else if (riding)
    detail = copy(
      "轻推顺着漂粒提速 · 留意队尾尾迹",
      "Push gently and follow the drifting particles to gain speed. Watch the pod’s trails",
    );
  else if (onFirst && approaching)
    detail = copy(
      "看水下漂粒 · 下潜轻推，或走宽水面",
      "Watch the drifting particles. Dive and push gently, or take the open water route",
    );
  const poolEntry = landmark(level, "current-eddy-entry") ?? pool;
  return {
    notice: riding
      ? isEnglish()
        ? `Riding the current · ${levelLabel(zone)}`
        : `正在借流 · ${levelLabel(zone)}`
      : cue.notice,
    detail,
    markers: nearPool
      ? [{ ...poolEntry, kind: "supply" }, secondEntry]
      : [marker],
    riding,
  };
}

function kelpCue(
  state: WhaleState,
  level: WhaleLevel,
  leader: WhaleActor,
  view: WhaleTutorialView,
):
  | (Pick<WhaleGuidance, "notice" | "detail" | "markers"> & { inside: boolean })
  | undefined {
  const zone = level.zones.find(
    ({ id, kind }) => id === "net-kelp" && kind === "supply",
  );
  if (!zone) return;
  const pos = landmark(level, "kelp-center")?.pos ?? center(zone.points);
  const { arrived, required, inside, ready } = whaleSupplyStatus(
    leader,
    state.actors,
    zone,
  );
  const remaining = state.supply[zone.id] ?? 0;
  if (
    !inside &&
    (leader.pos.z > Math.max(...zone.points.map(({ z }) => z)) ||
      distance(leader.pos, pos) > 120)
  )
    return;
  const bayMarker: WhaleMarker = {
    id: zone.id,
    label:
      remaining > 0
        ? copy("海藻湾 · 补给", "Kelp Bay · Supplies")
        : copy("海藻湾 · 补给已用完", "Kelp Bay · Supplies depleted"),
    pos,
    kind: "supply",
    allowEdge: false,
  };
  if (!inside) {
    const wide = landmark(level, "net-wide");
    const onMaintainedRoute =
      wide &&
      landmark(level, "net-recovery-dock") &&
      leader.pos.x >= wide.pos.x - 18;
    const entries = Object.values(kelpApproaches).flatMap(
      (path): WhaleMarker[] => {
        const mark = path
          .slice(0, -1)
          .map((id) => landmark(level, id))
          .find(
            (mark) =>
              mark &&
              mark.pos.z >= leader.pos.z - 2 &&
              distance(leader.pos, mark.pos) > 7,
          );
        return mark ? [{ ...mark, kind: "route" }] : [];
      },
    );
    return {
      notice: state.occupied.includes("net-rest")
        ? copy("网外静水", "Calm Water Beyond the Nets")
        : copy("海藻湾", "Kelp Bay"),
      detail: onMaintainedRoute
        ? copy(
            "沿无网水道缓弧进海藻湾补给，也可直去分岔",
            "Follow the gentle curve through net-free water to refuel at Kelp Bay, or swim straight to the fork",
          )
        : copy(
            "可收速短切，或沿外侧缓弧带队靠拢 · 也可直去分岔",
            "Slow down for a shortcut into the bay, take the open curve to regroup, or go straight to the fork",
          ),
      markers: entries.length ? entries : [bayMarker],
      inside,
    };
  }
  const tail = state.actors.findLast(
    (actor) => !contains(zone.points, actor.pos),
  );
  const supply =
    remaining <= 0
      ? copy("补给已用完", "Supplies depleted")
      : !surfaced(leader)
        ? isEnglish()
          ? `Refuel after reaching ${surfaceHint(view)}`
          : `${surfaceHint(view)}后可补给`
        : !ready
          ? isEnglish()
            ? `Swim slowly and wait for the pod. At least ${required} whales must be in the bay to refuel`
            : `缓游等队尾，至少 ${required} 只进湾才补给`
          : state.energy < 1
            ? copy("正在补给", "Refueling")
            : copy("能量已满", "Energy full");
  return {
    notice: copy("海藻湾", "Kelp Bay"),
    detail: isEnglish()
      ? `In the bay: ${arrived}/${state.actors.length} · ${supply}`
      : `进湾 ${arrived}/${state.actors.length} · ${supply}`,
    markers: tail
      ? [
          bayMarker,
          companionMarker(
            tail,
            copy("队尾 · 尚未进湾", "Trailing whale · Outside the bay"),
          ),
        ]
      : [],
    inside,
  };
}

function activityMarkers(
  ...marks: readonly (Landmark | undefined)[]
): WhaleMarker[] {
  return marks.flatMap((mark) => (mark ? [{ ...mark, kind: "route" }] : []));
}

function dredgingCue(
  state: WhaleState,
  level: WhaleLevel,
  leader: WhaleActor,
  view: WhaleTutorialView,
): ActivityCue | undefined {
  const passage = dredgingPassage(level);
  if (!passage) return;
  const surface = passage.surface.find(({ pos }) => pos.z > leader.pos.z + 5);
  const clear = passage.clear.find(({ pos }) => pos.z > leader.pos.z + 5);
  const entrance = passage.surface[0];
  const exit = passage.regroup;
  if (
    !entrance ||
    leader.pos.x < (passage.clear[0]?.pos.x ?? entrance.pos.x) - 25 ||
    leader.pos.z < entrance.pos.z - 26 ||
    leader.pos.z > exit.pos.z + 9
  )
    return;
  if (!surface && !clear) {
    const tail = state.actors.findLast(
      (actor) =>
        actor.id !== leader.id && whaleGoalBlocker(actor, passage.rest),
    );
    return {
      notice: copy(
        "疏浚区外 · 清水换气",
        "Clear water beyond the dredging area · Breathe here",
      ),
      detail: surfaced(leader)
        ? copy(
            "可缓行等队尾，再游向汇流处",
            "Slow down to let the pod catch up, then swim toward the junction",
          )
        : isEnglish()
          ? `${surfaceHint(view)}. Wait for the pod in clear water`
          : `${surfaceHint(view)}，可在清水中等队尾`,
      markers: [
        ...activityMarkers(exit),
        ...(tail
          ? [
              companionMarker(
                tail,
                contains(passage.rest.points, tail.pos)
                  ? copy("队尾 · 尚未上浮", "Trailing whale · Submerged")
                  : copy(
                      "队尾 · 尚未到清水",
                      "Trailing whale · Has yet to reach clear water",
                    ),
              ),
            ]
          : []),
      ],
    };
  }
  const choosing = leader.pos.z < entrance.pos.z;
  const onClearSide =
    clear && surface && leader.pos.x < (clear.pos.x + surface.pos.x) / 2;
  return {
    notice: copy("港口疏浚区", "Harbor Dredging Area"),
    detail: choosing
      ? copy(
          "水面沿浮标直游，也可浅潜沿清水边缘绕行",
          "Follow the buoys at the surface, or dive shallow and skirt the edge in clear water",
        )
      : copy(
          "沿下一处航标游到清水，再上浮等队尾",
          "Follow the next marker to clear water, then surface and wait for the pod",
        ),
    markers: choosing
      ? activityMarkers(surface, clear)
      : activityMarkers(onClearSide ? clear : (surface ?? clear)),
  };
}

function breakwaterCue(
  state: WhaleState,
  level: WhaleLevel,
  leader: WhaleActor,
): ActivityCue | undefined {
  const flow = level.zones.find(({ id }) => id === "breakwater-cross-current");
  const preview = landmark(level, "breakwater-preview");
  const cross = landmark(level, "breakwater-cross");
  const wide = landmark(level, "breakwater-wide");
  const exit = landmark(level, "breakwater-clear");
  if (!flow || !preview || !cross || !wide || !exit) return;
  const near = Math.min(...flow.points.map(({ z }) => z));
  const far = Math.max(...flow.points.map(({ z }) => z));
  if (leader.pos.z < preview.pos.z - 8 || leader.pos.z > exit.pos.z + 3) return;
  if (contains(flow.points, leader.pos))
    return {
      notice: copy("正在穿越横流", "Crossing the current"),
      detail: copy(
        "略朝水纹来向修正航向，出流后收速看队尾",
        "Steer gently into the current. Slow down and look back once you’re through",
      ),
      markers: activityMarkers(exit),
    };
  if (leader.pos.z > far) {
    const tail = state.actors.findLast(
      (actor) => actor.id !== leader.id && actor.pos.z <= far,
    );
    return {
      notice: copy("防波堤外 · 静水", "Calm Water Beyond the Breakwater"),
      detail: tail
        ? copy(
            "缓行等队尾过堤，再前往换气水域",
            "Slow down for the last whales to round the breakwater, then head to the breathing area",
          )
        : copy(
            "全队已过堤，可继续巡航",
            "The whole pod has rounded the breakwater. You can cruise on",
          ),
      markers: [
        ...activityMarkers(exit),
        ...(tail
          ? [
              companionMarker(
                tail,
                copy(
                  "队尾 · 尚未过堤",
                  "Trailing whale · Still behind the breakwater",
                ),
              ),
            ]
          : []),
      ],
    };
  }
  return {
    notice: copy("防波堤横流", "Breakwater Crosscurrent"),
    detail: copy(
      "斜向迎流可走短线，也可沿外侧宽水面绕过",
      "Angle into the current for the short route, or go around through wide open water",
    ),
    markers:
      leader.pos.z < near
        ? activityMarkers(cross, wide)
        : activityMarkers(exit, wide),
  };
}

function watchingCue(
  state: WhaleState,
  level: WhaleLevel,
  leader: WhaleActor,
  view: WhaleTutorialView,
): ActivityCue | undefined {
  const water = level.zones.find(({ id }) => id === "watching-rest");
  const entry = landmark(level, "watching-entry");
  const coast = landmark(level, "watching-coast");
  const exit = landmark(level, "watching-exit");
  if (!water || !entry || !coast || !exit || leader.pos.z < entry.pos.z - 5)
    return;
  if (leader.pos.z > exit.pos.z + 2) return;
  const inside = contains(water.points, leader.pos);
  if (!inside)
    return {
      notice: copy("观鲸船减速区", "Whale-Watching Slow Zone"),
      detail: copy(
        "船只留在浮标外 · 内侧可换气等同伴，也可直游",
        "Boats stay outside the buoys. Breathe and wait inside, or keep swimming",
      ),
      markers: activityMarkers(coast, exit),
    };
  const ready = goalStatus(state, water);
  const tail = state.actors.findLast(
    (actor) => actor.id !== leader.id && whaleGoalBlocker(actor, water),
  );
  return {
    notice: isEnglish()
      ? `Whale-Watching Slow Zone · At surface: ${ready.arrived}/${ready.expected}`
      : `观鲸船减速区 · 水面 ${ready.arrived}/${ready.expected}`,
    detail: surfaced(leader)
      ? copy(
          "可松手滑停等队尾，或沿航标继续游向外海",
          "Release to glide to a stop and wait for the pod, or follow the markers offshore",
        )
      : isEnglish()
        ? `${surfaceHint(view)}. Breathe here with the pod`
        : `${surfaceHint(view)}，可与同伴一起换气`,
    markers: [
      ...activityMarkers(leader.pos.z < coast.pos.z - 5 ? coast : exit),
      ...(tail
        ? [
            companionMarker(
              tail,
              copy(
                "队尾 · 尚未就绪",
                "Trailing whale · Still getting into position",
              ),
            ),
          ]
        : []),
    ],
  };
}

export function whaleGuidance(
  state: WhaleState,
  level: WhaleLevel,
  tips: boolean,
  view: WhaleTutorialView,
): WhaleGuidance {
  const leader = leaderOf(state);
  const {
    marker: gatheringMarker,
    center: gatheringCenter,
    ...arrival
  } = arrivalCue(state, level, leader, view);

  const dive = leader.dive;
  const depthCue =
    dive.forced && dive.direction === "up"
      ? copy(
          "呼吸耗尽 · 正在自动上浮",
          "Out of breath · Surfacing automatically",
        )
      : dive.direction === "up"
        ? copy("↑ 正在上浮", "↑ Surfacing")
        : dive.direction === "down"
          ? copy("↓ 正在下潜", "↓ Diving")
          : dive.needsRelease
            ? view.toggle
              ? copy(
                  "关闭下潜，换气后再开启",
                  "Toggle Dive off, then breathe before diving again",
                )
              : copy(
                  "松开下潜，换气后再按",
                  "Release Dive and breathe before diving again",
                )
            : dive.layer === "surface" && dive.breath < WHALE.releaseBreath
              ? copy(
                  "正在换气 · 呼吸恢复后可下潜",
                  "Breathing · Dive again after recovering your breath",
                )
              : surfaced(leader) && state.segmentId === "W0" && dive.breath < 1
                ? copy("正在换气", "Breathing")
                : "";
  const indicators = {
    depthLabel: waterLabel(dive.layer),
    depthCue,
    breath: dive.breath,
    transition: dive.depth / 2,
    arrival,
  };
  let notice = "";
  let detail = "";
  let danger = "";
  let warningDetail = "";
  let tutorial = false;
  const markers: WhaleMarker[] = [];
  const rescue = state.actors.reduce<WhaleActor | undefined>(
    (urgent, actor) => {
      if (actor.status !== "strayed" || actor.rescueTicks === null)
        return urgent;
      return actor.rescueTicks < (urgent?.rescueTicks ?? Infinity)
        ? actor
        : urgent;
    },
    undefined,
  );
  const rejoining = state.actors.findLast(
    ({ status }) => status === "rejoining",
  );
  const lowBreathTail = state.actors
    .slice(1)
    .find(
      (actor) =>
        actor.status !== "strayed" &&
        actor.dive.layer !== "surface" &&
        actor.dive.breath <= WHALE.lowBreath,
    );
  const lowBreath =
    dive.breath <= WHALE.lowBreath || lowBreathTail !== undefined;
  const routeCohesion =
    state.phase === "playing" &&
    state.segmentId === "W3" &&
    state.route !== null &&
    !state.routeLocked &&
    !rescue &&
    !rejoining &&
    !lowBreath &&
    state.energy > WHALE.lowEnergy
      ? state.cohesion
      : null;

  if (state.phase === "playing") {
    const reefPassage =
      state.segmentId === "W3" && state.route === "quiet" && !state.routeLocked
        ? reefPassageCue(state, level, leader, view, lowBreath)
        : undefined;
    const hazard = approachingHazard(state, level, leader);
    const nets = state.segmentId === "W2" ? level.zones.filter(isWhaleNet) : [];
    const net = netBounds(nets);
    const practiced =
      view.moved &&
      view.stopped &&
      view.dragged &&
      view.reset &&
      view.recovered;
    let navigation = routeMarkers(
      state,
      level,
      leader,
      tips && !practiced,
      nets,
    );
    const ship = hazard?.motion
      ? hazard
      : state.segmentId === "W1"
        ? level.zones.find(
            (zone): zone is Hazard => zone.kind === "hazard" && !!zone.motion,
          )
        : undefined;
    const passage = ship ? shipPassage(ship) : undefined;
    const inPassage = ({ pos }: WhaleActor) =>
      passage !== undefined && pos.z >= passage.near && pos.z <= passage.far;
    const podInPassage = state.actors.some(inPassage);
    const inCrossingRest =
      state.segmentId === "W1" && state.occupied.includes("crossing-rest");
    const safelyAcross =
      passage && state.actors.every(({ pos }) => pos.z > passage.far);
    const shipStillBehind =
      passage && leader.pos.z > passage.far && !safelyAcross;
    const netTrailing =
      net &&
      state.actors
        .filter(({ pos }) => pos.z <= net.far + WHALE.hitRadius)
        .sort((a, b) => a.pos.z - b.pos.z);
    const netTail = netTrailing?.find(({ id }) => id !== leader.id);
    const netRunout =
      net && netTail ? netRunoutCue(level, nets, net, leader) : undefined;
    const beyondNet = netTrailing?.length === 0;
    const kelp = beyondNet ? kelpCue(state, level, leader, view) : undefined;
    const checkpoint = checkpointWaiting(state, level, leader);
    const warning = shipStillBehind ? ship : hazard;
    if (
      warning &&
      !(warning.motion && inCrossingRest && safelyAcross) &&
      !(isWhaleNet(warning) && beyondNet)
    ) {
      const layers = waterLayers
        .filter((layer) => occupiesLayer(warning, layer))
        .map(waterLabel);
      const name = levelLabel(warning).split(" · ", 1)[0];
      danger = isEnglish()
        ? `${name} · Blocks ${layers.join(" / ")}`
        : `${name} · ${layers.join("／")}受阻`;
      if (isWhaleNet(warning))
        warningDetail = rescue
          ? copy("接应时留在网外", "Stay clear of the nets during rescue")
          : copy(
              "短网口需先对准再缓游 · 外侧可巡航绕行",
              "Line up and slow down for the narrow gap, or cruise around the outside",
            );
      if (isWhaleBreakwater(warning))
        warningDetail =
          warning.id === "ship-approach-breakwater"
            ? copy(
                "先收速，沿浮标游到堤侧，再转向船道。",
                "Slow down. Swim beside the breakwater using the buoys, then turn toward the lane.",
              )
            : copy(
                "避开堤身，沿横流短线或外侧宽水面通过",
                "Avoid the breakwater. Take the crosscurrent shortcut or the wide outer route",
              );
      if (warning.motion && passage) {
        const crossing = shipWarning(
          warning,
          state,
          leader,
          level,
          passage,
          lowBreath,
          podInPassage,
        );
        warningDetail = crossing.detail;
        if (crossing.tail && !rescue) markers.push(crossing.tail);
        markers.push(shipDirectionMarker(warning, state.tick));
      }
    }

    if (rescue) {
      const depth = waterLabel(rescue.dive.layer);
      notice = isEnglish()
        ? `Rescue companion · ${depth}`
        : `接应同伴 · ${depth}`;
      const approach = whaleRescueApproach(leader, rescue);
      const behind =
        (rescue.pos.x - leader.pos.x) * Math.sin(leader.heading) +
          (rescue.pos.z - leader.pos.z) * Math.cos(leader.heading) <
        0;
      const hints = {
        distance: behind
          ? copy(
              "减速折返，沿标记靠近掉队同伴",
              "Slow down and turn back. Follow the marker to the separated whale",
            )
          : copy(
              "沿标记靠近掉队同伴",
              "Follow the marker to the separated whale",
            ),
        layer: rescue.dive.direction
          ? copy(
              "在附近等待同伴完成浮潜",
              "Wait nearby while your companion changes depth",
            )
          : rescue.dive.layer === "surface"
            ? dive.direction === "up"
              ? copy(
                  "正在上浮，与同伴在水面接应",
                  "Surfacing · Meet your companion at the surface",
                )
              : isEnglish()
                ? `${surfaceHint(view)}. Stay at your companion’s depth`
                : `${surfaceHint(view)}，与同伴保持同层`
            : isEnglish()
              ? `Reach the ${depth} layer and stay with your companion`
              : `到${depth}层，与同伴保持同层`,
        speed: view.desktop
          ? copy(
              "松开方向键停稳，等接应开始",
              "Release the movement keys and glide to a stop to start the rescue",
            )
          : copy(
              "松开摇杆停稳，等接应开始",
              "Release the stick and glide to a stop to start the rescue",
            ),
        ready: copy(
          "保持同层低速，等接应进度完成",
          "Stay close and slow at the same depth until the rescue is complete",
        ),
      };
      detail = hints[approach];
      const waypoint =
        approach === "distance" && net
          ? netRescueWaypoint(level, nets, net, leader.pos, rescue.pos)
          : undefined;
      if (waypoint) {
        detail = copy(
          "减速折返，沿可通行水域接近同伴",
          "Slow down and turn back toward your companion through open water",
        );
        markers.push({
          id: "rescue-net-detour",
          label: copy("沿这里折返", "Turn back here"),
          pos: waypoint,
          kind: "route",
        });
      }
      markers.push({
        id: "whale-rescue",
        label: isEnglish()
          ? `Companion awaiting rescue · ${depth}`
          : `待接应同伴 · ${depth}`,
        pos: rescue.pos,
        kind: "rescue",
        depth: rescue.dive.depth,
      });
    } else if (rejoining) {
      if (!indicators.arrival.visible)
        notice = copy("同伴正在归队", "A companion is rejoining");
      detail = copy(
        "放慢游速，给队尾留出空间",
        "Slow down to make room for the last whales",
      );
      if (net)
        markers.push(
          companionMarker(
            rejoining,
            copy("同伴 · 正在归队", "Companion · Rejoining"),
          ),
        );
    } else if (indicators.arrival.visible) {
      detail = indicators.arrival.detail;
      if (gatheringMarker) markers.push(gatheringMarker);
      if (gatheringCenter) markers.push(gatheringCenter);
    } else if (reefPassage?.inEddy) {
      ({ notice, detail } = reefPassage);
      markers.push(...reefPassage.markers);
    } else if (kelp?.inside) {
      ({ notice, detail } = kelp);
      if (lowBreath && surfaced(leader))
        detail += copy(" · 保持水面换气", " · Stay at the surface to breathe");
      markers.push(...kelp.markers);
      const exit = landmark(level, "branch-overlook");
      navigation = exit ? [{ ...exit, kind: "route" }] : [];
    } else if (lowBreath || state.energy <= WHALE.lowEnergy) {
      const refill =
        lowBreath && passage
          ? shipRefill(level, leader, passage)
          : safeWater(state, level, leader);
      notice =
        dive.breath <= WHALE.lowBreath
          ? copy("呼吸偏低", "Low breath")
          : lowBreathTail
            ? copy("队尾需要换气", "Trailing whale needs to breathe")
            : copy("能量偏低", "Low energy");
      if (refill) {
        const nearby = distance(leader.pos, refill.pos) < 2;
        const action =
          refill.zone.kind === "supply"
            ? copy("补给", "refuel")
            : copy("休整", "rest");
        detail = lowBreath
          ? podInPassage
            ? nearby
              ? copy(
                  "在这里缓行，等队尾离开船道",
                  "Slow down here and let the pod clear the shipping lane",
                )
              : copy(
                  "沿箭头游离船道，再到静水换气",
                  "Follow the arrow out of the lane to breathe in calm water",
                )
            : nearby
              ? surfaced(leader)
                ? copy("保持在水面换气", "Stay at the surface to breathe")
                : copy("可在此浮出水面换气", "Surface here to breathe")
              : copy(
                  "沿箭头前往静水，再上浮换气",
                  "Follow the arrow to calm water, then surface to breathe",
                )
          : nearby
            ? isEnglish()
              ? `You can ${action} here`
              : `可在此${action}`
            : isEnglish()
              ? `Follow the marker to safe water to ${action}`
              : `沿指示前往${action}水域`;
        if (!nearby)
          markers.push({
            id: "whale-refill",
            label: lowBreath
              ? copy("换气水域", "Breathing Area")
              : levelLabel(refill.zone),
            pos: refill.pos,
            kind: "supply",
          });
      } else {
        detail = lowBreath
          ? copy(
              "离开危险区域后上浮换气",
              "Clear the hazard zone before surfacing to breathe",
            )
          : copy("放慢游速，寻找安全水域", "Slow down and look for safe water");
      }
    } else if (checkpoint && (!checkpoint.fallback || checkpoint.id === "C2")) {
      const name =
        checkpoint.id === "C1"
          ? copy("检查点 1", "Checkpoint 1")
          : copy("检查点 2", "Checkpoint 2");
      notice = checkpoint.fallback
        ? `${name}${copy(" · 可在此补存", " · Save here")}`
        : name;
      const waiting = checkpointCue(state, checkpoint.zone, leader, view);
      detail = waiting.detail;
      if (waiting.marker) markers.push(waiting.marker);
    } else if (
      inCrossingRest &&
      safelyAcross &&
      !state.triggered.includes("C1")
    ) {
      notice = copy("船后静水", "Calm Water Beyond the Shipping Lane");
      const count = `${state.actors.length}/${state.actors.length}`;
      detail = surfaced(leader)
        ? copy(
            `全队已过船道 ${count} · 可在这里停留换气，再去检查点 1`,
            `Across: ${count} · Take a breath here before swimming to Checkpoint 1`,
          )
        : dive.direction === "up"
          ? copy(
              "正在上浮 · 可停稳等同伴",
              "Surfacing · You can stop and wait for the pod",
            )
          : isEnglish()
            ? `Across: ${count} · ${surfaceHint(view)}. You can stop and wait for the pod`
            : `全队已过船道 ${count} · ${surfaceHint(view)}，可停稳等同伴`;
    } else if (
      safelyAcross &&
      navigation.some(({ id }) => id === "net-preview-wide")
    ) {
      notice = copy(
        "前方渔网 · 两条路线可绕行",
        "Nets ahead · Two routes around",
      );
      detail = copy(
        "短口要提前对准收速 · 外侧宽线可保持巡航",
        "Line up and slow early for the narrow gap, or cruise along the wide outer route",
      );
    } else if (
      net &&
      netTrailing &&
      netTail &&
      (netRunout || leader.pos.z > net.far + WHALE.hitRadius)
    ) {
      notice = isEnglish()
        ? `Past the nets: ${state.actors.length - netTrailing.length}/${state.actors.length}`
        : `已清网 ${state.actors.length - netTrailing.length}/${state.actors.length}`;
      detail = netRunout
        ? copy(
            "先直游或缓行，等队尾清网再转向",
            "Swim straight or slow down. Let the last whales clear the nets before turning",
          )
        : copy(
            "缓行等队尾通过，再转向",
            "Slow down for the last whales to pass before turning",
          );
      markers.push(
        companionMarker(
          netTail,
          copy("队尾 · 尚未清网", "Trailing whale · Still among the nets"),
        ),
      );
      if (netRunout) markers.push(netRunout);
      navigation = [];
    } else if (
      net &&
      !beyondNet &&
      state.actors.some(
        ({ id, pos }) =>
          id !== leader.id && distance(pos, leader.pos) >= WHALE.netCautionGap,
      )
    ) {
      const tail = state.actors
        .slice(1)
        .reduce((a, b) =>
          distance(a.pos, leader.pos) >= distance(b.pos, leader.pos) ? a : b,
        );
      notice = copy("队尾拉开", "The pod is spreading out");
      detail = copy(
        "缓行等队尾清网，再转向",
        "Slow down and let the last whales clear the nets before turning",
      );
      markers.push(
        companionMarker(
          tail,
          copy("队尾 · 拉开", "Trailing whale · Falling behind"),
        ),
      );
    } else if (net && beyondNet) {
      if (kelp) {
        ({ notice, detail } = kelp);
        markers.push(...kelp.markers);
        if (kelp.markers.length > 1)
          navigation = navigation.filter(
            ({ id }) =>
              id === "branch-overlook" ||
              (state.occupied.includes("net-rest") &&
                (id === "net-clear" || id === "net-wide-merge")),
          );
      } else if (state.occupied.includes("net-rest")) {
        notice = copy("网外静水", "Calm Water Beyond the Nets");
        detail = surfaced(leader)
          ? copy(
              "可停留换气，沿航标前往分岔",
              "Stop to breathe or follow the markers to the fork",
            )
          : isEnglish()
            ? `${surfaceHint(view)}. Follow the markers to the fork`
            : `${surfaceHint(view)}，沿航标前往分岔`;
      }
    } else if (
      net &&
      !danger &&
      navigation.some(
        ({ id }) =>
          id === netApproaches.short[0] ||
          id === netApproaches.wide[0] ||
          id === "net-gap" ||
          id === "net-wide",
      )
    ) {
      notice = copy("选择绕网路线", "Choose a route past the nets");
      detail = landmark(level, "net-recovery-dock")
        ? copy(
            "短网口对准后缓游 · 外侧无网水道可巡航",
            "Line up and swim slowly through the gap, or cruise through net-free water around the outside",
          )
        : copy(
            "短网口对准后缓游 · 外侧宽线可巡航",
            "Line up and swim slowly through the gap, or cruise along the wide outer route",
          );
    } else if (
      state.segmentId === "W3" &&
      !state.routeLocked &&
      (!state.route ||
        level.triggers.some(
          (gate) =>
            gate.kind === "route" &&
            leader.pos.z < (gate.crossingZ ?? -Infinity),
        ))
    ) {
      notice = state.route
        ? state.route === "shipping"
          ? copy(
              "已选近航道 · 可重新越线选路",
              "Short Channel chosen · Cross back to choose again",
            )
          : copy(
              "已选安静航道 · 可重新越线选路",
              "Quiet Passage chosen · Cross back to choose again",
            )
        : copy("选择航道", "Choose a channel");
      detail = copy(
        "近航道看空档，噪声会拉开队伍 · 安静航道绕浅礁，队伍更稳",
        "Watch for a quiet window in the Short Channel. Noise spreads the pod out. The Quiet Passage skirts the reef and keeps the pod closer",
      );
    } else if (state.segmentId === "W3" && state.route && !state.routeLocked) {
      const noisy = level.zones.some(
        (zone) =>
          zone.kind === "interference" && state.occupied.includes(zone.id),
      );
      const reef =
        state.route === "quiet" && state.occupied.includes("quiet-rest");
      notice = reef
        ? copy("浅礁静水", "Calm Water by the Shallow Reef")
        : state.route === "shipping"
          ? copy("已选近航道", "Short Channel chosen")
          : copy("已选安静航道", "Quiet Passage chosen");
      detail = noisy
        ? copy(
            "各水层都受噪声影响 · 放慢游速，留意队尾",
            "Noise affects all depths · Slow down and watch the pod",
          )
        : reef
          ? surfaced(leader)
            ? copy(
                "减速转镜，或浅潜看鱼群 · 随航标前往汇流处",
                "Slow down to look around, or dive shallow to see fish. Follow the markers to the channel junction",
              )
            : isEnglish()
              ? `${surfaceHint(view)} · Breathe in the sunlit water`
              : `${surfaceHint(view)} · 光斑水域可换气`
          : copy(
              "沿航标前往汇流处",
              "Follow the markers to where the channels meet",
            );
      if (noisy) {
        const mark = landmark(level, "shipping-supply");
        if (
          mark &&
          mark.pos.z + 10 > leader.pos.z &&
          distance(leader.pos, mark.pos) < 100 &&
          (state.supply["shipping-refill"] ?? 0) > 0
        )
          markers.push({ ...mark, kind: "supply", allowEdge: false });
      }
      const shipping =
        state.route === "shipping"
          ? shippingCue(state, level, leader)
          : undefined;
      if (shipping) {
        ({ notice, detail } = shipping);
        markers.push(...shipping.markers);
        navigation = shipping.navigation ?? navigation;
        if (
          !noisy &&
          !shipping.markers.some(({ kind }) => kind === "gathering")
        ) {
          const dredge = dredgingCue(state, level, leader, view);
          if (dredge) {
            ({ notice, detail } = dredge);
            navigation = dredge.markers;
          }
        }
      }
      if (reefPassage) {
        ({ notice, detail } = reefPassage);
        markers.push(...reefPassage.markers);
        if (reefPassage.riding)
          navigation = reefPassage.markers.some(
            ({ id }) => id === "reef-current-east-entry",
          )
            ? []
            : navigation.filter(({ id }) => id !== "quiet-pool");
      }
    } else if (state.segmentId === "W4") {
      const rest = state.occupied.includes("offshore-rest");
      notice = rest
        ? copy("外海静水", "Calm Offshore Waters")
        : copy("驶向外海", "Heading offshore");
      detail = !rest
        ? copy(
            "跟随水面航标前往静水",
            "Follow the surface markers to calm water",
          )
        : surfaced(leader)
          ? copy(
              "可停留换气，沿亮水游到中央，再松手滑停",
              "Stop for a breath, then swim into the bright water and release to glide to a stop",
            )
          : isEnglish()
            ? `${surfaceHint(view)}. Wait for the pod in calm water`
            : `${surfaceHint(view)}，可在静水等候同伴`;
      if (state.triggered.includes("C2")) {
        const current = currentCue(
          state,
          leader,
          findCurrent(level, "offshore-current"),
        );
        const breakwater = breakwaterCue(state, level, leader);
        const activity = breakwater ?? watchingCue(state, level, leader, view);
        const wide = landmark(level, "breakwater-wide");
        if (
          current &&
          (!breakwater || (wide && leader.pos.x >= wide.pos.x - 12))
        ) {
          ({ notice, detail } = current);
          markers.push(current.marker);
          if (state.occupied.includes("offshore-current")) navigation = [];
        } else if (activity) {
          ({ notice, detail } = activity);
          navigation = activity.markers;
        }
      }
    } else if (state.segmentId === "W0") {
      if (tips) {
        const lesson = bayHint(state, leader, view);
        ({ notice, detail, tutorial } = lesson);
        if (lesson.marker) markers.push(lesson.marker);
      }
      const shoal = landmark(level, "bay-shoal");
      const shoalDistance = shoal ? distance(leader.pos, shoal.pos) : Infinity;
      const byShoal = shoalDistance < 34;
      if (shoal && shoalDistance < 56)
        markers.push({ ...shoal, kind: "landmark", allowEdge: false });
      if (
        shoal &&
        byShoal &&
        (!tutorial || (!view.stopped && !view.submerged))
      ) {
        notice = levelLabel(shoal);
        detail = surfaced(leader)
          ? copy(
              "绕过鱼群沿水面转向航标，或浅潜对准水纹顺流。",
              "Bank around the shoal at the surface, or dive shallow and line up with the ripples.",
            )
          : copy(
              "放慢游速，看看身边的鱼群重新聚拢",
              "Slow down to see the shoal gather around you again",
            );
        tutorial = false;
        const turn = landmark(level, "bay-surface-turn");
        if (turn && surfaced(leader) && leader.pos.z < turn.pos.z)
          navigation = [{ ...turn, kind: "route" }, ...navigation];
      }
      const current = findCurrent(level, "bay-current");
      const flow = currentCue(state, leader, current);
      if (flow) {
        markers.push(flow.marker);
        const inside = current && contains(current.points, leader.pos);
        if (inside || (!tutorial && !byShoal)) {
          notice = flow.notice;
          detail = flow.detail;
          tutorial = false;
        }
      }
      const refill = landmark(level, "bay-refill");
      if (current && refill && leader.pos.z >= currentGuide(current).exit.z) {
        const tail = baySubmergedTail(state);
        const refilling = dive.breath < 1 || tail !== undefined;
        if (leader.pos.z < refill.pos.z + 5 || refilling)
          markers.push({ ...refill, kind: "supply", allowEdge: false });
        if (tail && !markers.some(({ id }) => id === tail.id))
          markers.push(tail);
        if (refilling) {
          notice = levelLabel(refill);
          detail = surfaced(leader)
            ? tail
              ? copy(
                  "领鲸已上浮 · 可缓行等队尾",
                  "The lead whale has surfaced · Swim slowly for the pod to catch up",
                )
              : copy("留在水面换气", "Stay at the surface to breathe")
            : dive.direction === "up"
              ? copy(
                  "正在上浮 · 可停稳等同伴",
                  "Surfacing · You can stop and wait for the pod",
                )
              : surfaceHint(view);
          tutorial = false;
        } else if (leader.pos.z >= refill.pos.z) {
          notice = copy("湾外是船道", "Shipping lane beyond the bay");
          detail = copy(
            "留在宽水面，观察货船的航向",
            "Stay in open water and watch which way the cargo ship is moving",
          );
          tutorial = false;
        }
      }
      if (refill && leader.pos.z >= refill.pos.z) {
        const cargo = level.zones.find(
          (zone): zone is Hazard =>
            zone.id === "cargo-ship" && zone.kind === "hazard",
        );
        if (cargo)
          markers.push(
            shipDirectionMarker(
              cargo,
              state.tick,
              copy("湾外货船", "Cargo ship beyond the bay"),
            ),
          );
      }
    }

    if (
      checkpoint?.fallback &&
      checkpoint.id === "C1" &&
      !rescue &&
      !rejoining &&
      !lowBreath &&
      !danger
    ) {
      const waiting = checkpointCue(state, checkpoint.zone, leader, view);
      detail = [
        detail,
        copy("在此上浮可补存检查点 1", "Surface here to save Checkpoint 1"),
        waiting.detail,
      ]
        .filter(Boolean)
        .join(" · ");
      if (waiting.marker) markers.push(waiting.marker);
    }
    if (!checkpoint && !rescue && !rejoining && !lowBreath && !danger) {
      if (
        state.segmentId === "W1" &&
        safelyAcross &&
        state.triggered.includes("C1")
      ) {
        const flow = currentCue(
          state,
          leader,
          findCurrent(level, "shelf-current"),
        );
        if (
          flow &&
          (flow.marker.id === "current-exit" ||
            leader.pos.z >= flow.marker.pos.z - 4)
        ) {
          if (!notice || state.occupied.includes("shelf-current"))
            ({ notice, detail } = flow);
          markers.push(flow.marker);
        }
      }
      if (
        state.segmentId === "W2" &&
        net &&
        leader.pos.z < net.near - 55 &&
        !state.triggered.includes("C1") &&
        !state.triggered.includes("C2")
      ) {
        const main = level.zones.find(({ id }) => id === "C1");
        if (main) {
          const last = Math.max(...main.points.map(({ z }) => z));
          notice ||= copy("检查点 1 尚未保存", "Checkpoint 1 not saved yet");
          detail = [
            detail,
            copy(
              "检查点 1 未保存 · 可折返或在分岔静水补存",
              "Checkpoint 1 not saved · Turn back or save at the calm fork",
            ),
          ]
            .filter(Boolean)
            .join(" · ");
          markers.push({
            id: "return-to-c1",
            kind: "supply",
            pos: { x: leader.pos.x, z: last - 25 },
            label: "折返静水 · 保存检查点",
            labelEn: "Return to Calm Water to Save",
          });
        }
      }
      if (
        state.segmentId === "W4" &&
        state.routeLocked &&
        !state.triggered.includes("C2")
      ) {
        detail = [
          detail,
          copy(
            "全队上浮后可在前方静水补存检查点 2",
            "Surface together in the calm water ahead to save Checkpoint 2",
          ),
        ]
          .filter(Boolean)
          .join(" · ");
      }
      const { min, max } = level.bounds;
      const outwardX = Math.sin(leader.heading);
      const outwardZ = Math.cos(leader.heading);
      if (
        !indicators.arrival.visible &&
        leader.speed <= WHALE.reunionSpeed &&
        ((leader.pos.x === min.x && outwardX < -0.5) ||
          (leader.pos.x === max.x && outwardX > 0.5) ||
          (leader.pos.z === min.z && outwardZ < -0.5) ||
          (leader.pos.z === max.z && outwardZ > 0.5))
      ) {
        notice = copy("已到航域边缘", "At the edge of the course");
        detail = copy(
          "转向浮标，回到航道",
          "Turn toward the buoys to return to the route",
        );
      }
    }

    if (
      !rescue &&
      (!net || !rejoining) &&
      !indicators.arrival.visible &&
      !lowBreath &&
      !markers.some(({ id }) => id === "whale-refill")
    )
      markers.push(...navigation);
  }

  return {
    ...indicators,
    notice,
    detail,
    danger,
    warningDetail,
    markers,
    rescue:
      state.phase === "playing" && rescue?.rescueTicks != null
        ? {
            ticks: rescue.rescueTicks,
            progress: rescue.rescueProgress / WHALE.pickupTicks,
          }
        : null,
    routeCohesion,
    tutorial,
  };
}
