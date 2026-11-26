import type { ActorState, AirEncounterState } from "../core/game";
import { clamp, lerp, type Vec2 } from "../core/math";
import type { GooseEncounters } from "../levels/schema";

export const wingReactionTicks = 42;
export function initialEncounters(completed = false): AirEncounterState {
  return {
    kite: completed ? "done" : "aloft",
    kiteTick: 0,
    glider: completed ? "done" : "ready",
    gliderTick: 0,
    disrupted: false,
    clearingWing: false,
    wingAt: {},
  };
}

export function flightHeight(
  actor: ActorState,
  index: number,
  airborne: boolean,
): number {
  const lift = actor.status === "strayed" ? 0.11 : clamp(actor.speed / 4);
  return lerp(0.35, 3.95 + (index % 4) * 0.21, airborne ? lift : 0);
}

interface WingPose extends Vec2 {
  readonly y: number;
  readonly rise: number;
}
export function kitePose(
  kite: GooseEncounters["kite"],
  state: AirEncounterState,
  tick: number,
): WingPose {
  const t = clamp((tick - state.kiteTick) / kite.reelTicks);
  const rise =
    state.kite === "holding"
      ? 0
      : state.kite === "lowering"
        ? 1 - t
        : state.kite === "rising"
          ? t
          : 1;
  return {
    x:
      lerp(kite.bank.x - 3.5, kite.aloft.x, rise) +
      Math.sin(tick / 55) * 0.9 * rise,
    z: lerp(kite.bank.z + 1, kite.aloft.z, rise),
    y: lerp(kite.heldHeight, kite.height, rise),
    rise,
  };
}
export function gliderPose(
  glider: GooseEncounters["glider"],
  state: AirEncounterState,
  tick: number,
): WingPose {
  const age = Math.max(0, tick - state.gliderTick);
  if (state.glider === "crossing") {
    const t = clamp(age / glider.crossTicks);
    return {
      x: lerp(glider.launch.x, glider.crossTo.x, t),
      z: lerp(glider.launch.z, glider.crossTo.z, t),
      y: glider.height,
      rise: 1,
    };
  }
  if (state.glider === "leaving" || state.glider === "done") {
    const t = state.glider === "done" ? 1 : clamp(age / glider.leaveTicks);
    const rise = clamp((1 - t) * 2);
    return {
      x: lerp(glider.crossTo.x, glider.land.x, t),
      z: lerp(glider.crossTo.z, glider.land.z, t),
      y:
        lerp(1.4, glider.height, rise) +
        Math.sin(Math.PI * t) * glider.departureLift,
      rise,
    };
  }
  const rise = state.glider === "ready" ? 0 : clamp(age / glider.inflateTicks);
  return { ...glider.launch, y: lerp(1.4, glider.height, rise), rise };
}

// Closest approach in the wing's moving frame covers fast diagonal crossings.
// The ellipsoid includes bird clearance and the suspended space below the canopy.
function brushesWing(
  before: ActorState,
  after: ActorState,
  index: number,
  from: WingPose,
  to: WingPose,
  wing: GooseEncounters["glider"] | GooseEncounters["kite"],
): boolean {
  const rx = wing.span / 2 + 1;
  const rz = wing.depthRadius;
  const ry = wing.heightRadius;
  const offset = "harnessDrop" in wing ? wing.harnessDrop : 0;
  const x = (before.pos.x - from.x) / rx,
    z = (before.pos.z - from.z) / rz;
  const y = (flightHeight(before, index, true) - from.y + offset) / ry;
  const dx = (after.pos.x - to.x) / rx - x,
    dz = (after.pos.z - to.z) / rz - z;
  const dy = (flightHeight(after, index, true) - to.y + offset) / ry - y;
  const length = dx * dx + dy * dy + dz * dz;
  const t = length ? clamp(-(x * dx + y * dy + z * dz) / length) : 0;
  return (x + t * dx) ** 2 + (y + t * dy) ** 2 + (z + t * dz) ** 2 <= 1;
}

export function advanceEncounters(
  config: GooseEncounters,
  state: AirEncounterState,
  tick: number,
  before: readonly ActorState[],
  actors: readonly ActorState[],
): AirEncounterState {
  if (
    state.kite === "done" &&
    state.glider === "done" &&
    !Object.keys(state.wingAt).length
  )
    return state;
  let { kite, kiteTick, glider, gliderTick } = state;
  const k = config.kite,
    g = config.glider;
  if (
    kite === "aloft" &&
    actors.some(
      ({ pos }) =>
        pos.z >= k.noticeZ &&
        pos.z <= k.clearZ &&
        Math.abs(pos.x - k.bank.x) <= k.noticeHalfWidth,
    )
  ) {
    kite = "lowering";
    kiteTick = tick;
  } else if (kite === "aloft" && actors.every(({ pos }) => pos.z > k.clearZ)) {
    kite = "done";
  } else if (kite === "lowering" && tick - kiteTick >= k.reelTicks) {
    kite = "holding";
    kiteTick = tick;
  } else if (kite === "holding" && actors.every((a) => a.pos.z >= k.clearZ)) {
    kite = "rising";
    kiteTick = tick;
  } else if (kite === "rising" && tick - kiteTick >= k.reelTicks) {
    kite = "done";
    kiteTick = 0;
  }
  if (glider === "ready" && actors.some((a) => a.pos.z >= g.noticeZ)) {
    glider = "inflating";
    gliderTick = tick;
  } else if (glider === "inflating" && tick - gliderTick >= g.inflateTicks) {
    glider = "crossing";
    gliderTick = tick;
  } else if (glider === "crossing" && tick - gliderTick >= g.crossTicks) {
    glider = "leaving";
    gliderTick = tick;
  } else if (glider === "leaving" && tick - gliderTick >= g.leaveTicks) {
    glider = "done";
    gliderTick = 0;
  }
  const next = { ...state, kite, kiteTick, glider, gliderTick };
  const k0 = kitePose(k, state, tick - 1),
    k1 = kitePose(k, next, tick);
  const g0 = gliderPose(g, state, tick - 1),
    g1 = gliderPose(g, next, tick);
  const airborneKite =
    kite === "lowering" || kite === "aloft" || kite === "rising";
  const airborneGlider =
    glider === "crossing" || (glider === "leaving" && g1.rise > 0.55);
  const wingAt: Record<string, number> = {};
  let gliderContact = false;
  actors.forEach((actor, i) => {
    const previous = before[i];
    if (!previous) return;
    const hit = airborneGlider && brushesWing(previous, actor, i, g0, g1, g);
    gliderContact ||= hit;
    const stamp = state.wingAt[actor.id];
    if (hit || (airborneKite && brushesWing(previous, actor, i, k0, k1, k)))
      wingAt[actor.id] = tick;
    else if (stamp !== undefined && tick - stamp < wingReactionTicks)
      wingAt[actor.id] = stamp;
  });
  const clearingWing =
    gliderContact && (!state.disrupted || state.clearingWing);
  return {
    ...next,
    wingAt,
    clearingWing,
    disrupted: state.disrupted || gliderContact,
  };
}
