import { STEP_SEC } from "../core/clock";
import type {
  DiveState,
  WhaleActor,
  WorldInput,
  WaterLayer,
} from "../core/game";
import {
  angleDelta,
  approach,
  clamp,
  distance,
  lerp,
  type Vec2,
} from "../core/math";
import type { WhaleLevel } from "../levels/schema";
import type { WaterCurrent } from "../levels/whale-current";
import { boundPosition, headingVector } from "./goose";

export const WHALE = {
  size: 6,
  hitRadius: 1.7,
  cruise: 9.2,
  boost: 12.4,
  slow: 1.5,
  turnRate: 1.15,
  acceleration: 6.6,
  deceleration: 6,
  followMaxSpeed: 15.2,
  netCautionGap: 28,
  netContactReleaseMargin: 1,
  netRescueGap: 32,
  severeRescueGap: 58,
  followTurnRate: 3.5,
  followAcceleration: 14,
  followDeceleration: 20,
  diveTicks: [60, 120],
  riseTicks: [48, 72],
  breathSeconds: { surface: Infinity, shallow: 40, deep: 20 },
  recoverySeconds: 7,
  releaseBreath: 0.45,
  lowBreath: 0.24,
  followDiveTicks: 12,
  lowEnergy: 0.28,
  boostCutoff: 0.12,
  rescueRadius: 10,
  rescueSpeed: 2.2,
  reunionSpeed: 0.15,
  rescueTicks: 2400,
  pickupTicks: 120,
} as const;

const layers = ["surface", "shallow", "deep"] as const;

export const INITIAL_DIVE: DiveState = {
  layer: "surface",
  direction: null,
  progress: 0,
  depth: 0,
  breath: 1,
  forced: false,
  needsRelease: false,
};

export function updateDive(dive: DiveState, held: boolean): DiveState {
  const surfaced = dive.layer === "surface" && dive.depth === 0;
  const breath = clamp(
    dive.breath +
      STEP_SEC *
        (surfaced
          ? 1 / WHALE.recoverySeconds
          : -1 / WHALE.breathSeconds[dive.layer]),
  );
  const forced = !surfaced && (dive.forced || breath <= 1e-10);
  // A depleted whale completes the ascent even if the player keeps holding.
  // Release during or after the ascent and recover enough air for another dive.
  const needsRelease = held && (forced || dive.needsRelease);
  const breathingLock = dive.forced || dive.needsRelease || surfaced;
  const wantsDive =
    held &&
    !forced &&
    !needsRelease &&
    (!breathingLock || breath >= WHALE.releaseBreath);
  const deeper = wantsDive && dive.depth < 2;
  const shallower = !wantsDive && dive.depth > 0;
  const direction = deeper ? "down" : shallower ? "up" : null;
  if (!direction)
    return { ...dive, direction, progress: 0, breath, forced, needsRelease };

  const down = direction === "down";
  // Reverse toward the previous whole layer if a gesture changes mid-transition.
  const band = clamp(
    down ? Math.floor(dive.depth + 1e-10) : Math.ceil(dive.depth - 1e-10) - 1,
    0,
    1,
  ) as 0 | 1;
  const target = down ? band + 1 : band;
  const ticks = down ? WHALE.diveTicks[band] : WHALE.riseTicks[band];
  const advanced = approach(dive.depth, target, 1 / ticks);
  const reached = Math.abs(advanced - target) < 1e-10;
  const depth = reached ? target : advanced;
  const layer: WaterLayer = reached
    ? (layers[target] ?? dive.layer)
    : dive.layer;
  return {
    layer,
    direction: reached ? null : direction,
    progress: reached ? 0 : down ? depth - band : band + 1 - depth,
    depth,
    breath,
    forced: forced && !(reached && target === 0),
    needsRelease,
  };
}

function swim(
  actor: WhaleActor,
  heading: number,
  speed: number,
  bounds: WhaleLevel["bounds"],
): WhaleActor {
  const dir = headingVector(heading);
  const target = {
    x: actor.pos.x + dir.x * speed * STEP_SEC,
    z: actor.pos.z + dir.z * speed * STEP_SEC,
  };
  const pos = boundPosition(target, bounds);
  const travelled =
    pos.x === target.x && pos.z === target.z
      ? speed
      : distance(actor.pos, pos) / STEP_SEC;
  return { ...actor, heading, speed: Math.min(speed, travelled), pos };
}

export function swimLeader(
  actor: WhaleActor,
  input: WorldInput,
  energy: number,
  bounds: WhaleLevel["bounds"],
  current?: WaterCurrent,
): WhaleActor {
  const magnitude = clamp(Math.hypot(input.move.x, input.move.z));
  const delta = magnitude
    ? angleDelta(actor.heading, Math.atan2(input.move.x, input.move.z))
    : 0;
  const heading = angleDelta(
    0,
    actor.heading +
      clamp(delta, -WHALE.turnRate * STEP_SEC, WHALE.turnRate * STEP_SEC),
  );
  const desired =
    magnitude === 0
      ? 0
      : magnitude < 0.9
        ? lerp(WHALE.slow, WHALE.cruise, magnitude / 0.9)
        : energy > WHALE.boostCutoff
          ? WHALE.boost
          : WHALE.cruise;
  const speedLimit = energy > WHALE.boostCutoff ? WHALE.boost : WHALE.cruise;
  const assist = current
    ? current.speedAssist * clamp(magnitude / (current.fullAssistAt ?? 1))
    : 0;
  const turningSpeed = Math.min(
    speedLimit,
    desired * lerp(0.38, 1, clamp(Math.cos(delta))) + assist,
  );
  const speed = approach(
    actor.speed,
    turningSpeed,
    STEP_SEC *
      (turningSpeed > actor.speed ? WHALE.acceleration : WHALE.deceleration),
  );
  return swim(actor, heading, speed, bounds);
}

export function podSlot(
  leader: Pick<WhaleActor, "heading" | "pos">,
  index: number,
  cohesion: number,
): Vec2 {
  const row = Math.ceil(index / 2);
  const back = row * lerp(8.6, 6.4, cohesion);
  const side =
    (index % 2 ? 1 : -1) * (3.6 + row * 1.35) * lerp(1.35, 1, cohesion);
  const forward = headingVector(leader.heading);
  return {
    x: leader.pos.x - forward.x * back + forward.z * side,
    z: leader.pos.z - forward.z * back - forward.x * side,
  };
}

export function followWhale(
  actor: WhaleActor,
  index: number,
  leader: WhaleActor,
  cohesion: number,
  bounds: WhaleLevel["bounds"],
  maxSpeed: number = WHALE.followMaxSpeed,
): WhaleActor {
  if (actor.status === "strayed") return actor;
  const target = boundPosition(podSlot(leader, index, cohesion), bounds);
  const gap = distance(target, actor.pos);
  const desiredHeading =
    gap > 0.25
      ? Math.atan2(target.x - actor.pos.x, target.z - actor.pos.z)
      : leader.heading;
  const heading = angleDelta(
    0,
    actor.heading +
      clamp(
        angleDelta(actor.heading, desiredHeading),
        -WHALE.followTurnRate * STEP_SEC,
        WHALE.followTurnRate * STEP_SEC,
      ),
  );
  const desired =
    Math.min(gap * 2.3, maxSpeed) *
    clamp(Math.cos(angleDelta(heading, desiredHeading)));
  const speed = approach(
    actor.speed,
    desired,
    STEP_SEC *
      (desired > actor.speed
        ? WHALE.followAcceleration
        : WHALE.followDeceleration),
  );
  let status = actor.status;
  if ((status === "rejoining" || status === "loose") && gap < 8)
    status = "following";
  if (status === "following" && gap > 18) status = "loose";
  return { ...swim(actor, heading, speed, bounds), status };
}

export function whaleRescueApproach(
  leader: WhaleActor,
  companion: WhaleActor,
): "distance" | "layer" | "speed" | "ready" {
  if (distance(leader.pos, companion.pos) > WHALE.rescueRadius)
    return "distance";
  if (
    leader.dive.layer !== companion.dive.layer ||
    leader.dive.direction !== null ||
    companion.dive.direction !== null
  )
    return "layer";
  return leader.speed > WHALE.rescueSpeed ? "speed" : "ready";
}
