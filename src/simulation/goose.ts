import { STEP_SEC } from "../core/clock";
import type { ActorState, GooseState, WorldInput } from "../core/game";
import {
  angleDelta,
  approach,
  clamp,
  distance,
  lerp,
  type Vec2,
} from "../core/math";
import type { LevelSchema } from "../levels/schema";

export const GOOSE = {
  size: 12,
  hitRadius: 0.62,
  slow: 2.2,
  cruise: 10,
  boost: 17,
  boostInput: 0.9,
  turnRate: 1.76,
  circleRate: 0.62,
  acceleration: 13,
  deceleration: 12,
  coastTicks: 60,
  formTicks: 120,
  releaseTicks: 60,
  formationSaving: 1 / 3,
  formationTurnRatio: 0.5,
  breakAngle: 1.2,
  trailStride: 6,
  trailSamples: 24,
  followTurnRate: 5,
  followAcceleration: 24,
  followDeceleration: 36,
  followMaxSpeed: 21,
  separationRadius: 4,
  separationSpeed: 10,
  lowEnergy: 0.3,
  boostCutoff: 0.15,
  rescueRadius: 9,
  rescueSpeed: 3.7,
  rescueTicks: 2400,
  pickupTicks: 120,
} as const;

export function rescueApproach(
  leader: Pick<ActorState, "pos" | "speed">,
  companion: Pick<ActorState, "pos">,
): "distance" | "speed" | "ready" {
  if (distance(leader.pos, companion.pos) > GOOSE.rescueRadius)
    return "distance";
  return leader.speed > GOOSE.rescueSpeed ? "speed" : "ready";
}

export function headingVector(heading: number): Vec2 {
  return { x: Math.sin(heading), z: Math.cos(heading) };
}

export function boundPosition(
  position: Vec2,
  bounds: LevelSchema["bounds"],
): Vec2 {
  return {
    x: clamp(position.x, bounds.min.x, bounds.max.x),
    z: clamp(position.z, bounds.min.z, bounds.max.z),
  };
}

function moveAlong(pos: Vec2, heading: number, speed: number): Vec2 {
  const dir = headingVector(heading);
  return {
    x: pos.x + dir.x * speed * STEP_SEC,
    z: pos.z + dir.z * speed * STEP_SEC,
  };
}

export function moveLeader(
  actor: ActorState,
  state: GooseState,
  input: WorldInput,
  bounds: LevelSchema["bounds"],
): {
  actor: ActorState;
  formation: number;
  releasedTicks: number;
  turn: number;
} {
  const magnitude = clamp(Math.hypot(input.move.x, input.move.z));
  const active = magnitude > 0;
  const releasedTicks = active
    ? 0
    : Math.min(GOOSE.coastTicks, state.releasedTicks + 1);
  const targetHeading = active
    ? Math.atan2(input.move.x, input.move.z)
    : actor.heading;
  const difference = angleDelta(actor.heading, targetHeading);
  const broken = input.ability && Math.abs(difference) >= GOOSE.breakAngle;
  const formation = broken
    ? 0
    : clamp(
        state.formation +
          (input.ability ? 1 / GOOSE.formTicks : -1 / GOOSE.releaseTicks) +
          (input.ability ? 1e-12 : -1e-12),
      );

  if (!state.airborne && !active)
    return { actor, formation: 0, releasedTicks, turn: 0 };

  const turnRate =
    GOOSE.turnRate * lerp(1, GOOSE.formationTurnRatio, formation);
  const coasting = !active && releasedTicks < GOOSE.coastTicks;
  const turn = active
    ? clamp(difference, -turnRate * STEP_SEC, turnRate * STEP_SEC)
    : coasting
      ? 0
      : GOOSE.circleRate * STEP_SEC;
  const heading = angleDelta(0, actor.heading + turn);
  const boost = state.energy > GOOSE.boostCutoff ? GOOSE.boost : GOOSE.cruise;
  const targetSpeed = active
    ? magnitude < GOOSE.boostInput
      ? lerp(GOOSE.slow, GOOSE.cruise, magnitude / GOOSE.boostInput)
      : boost
    : coasting
      ? Math.max(GOOSE.slow, actor.speed - 2 * STEP_SEC)
      : GOOSE.slow;
  const speed = approach(
    actor.speed,
    targetSpeed,
    (targetSpeed >= actor.speed ? GOOSE.acceleration : GOOSE.deceleration) *
      STEP_SEC,
  );
  const pos = boundPosition(moveAlong(actor.pos, heading, speed), bounds);

  return {
    actor: { ...actor, pos, speed, heading },
    formation,
    releasedTicks,
    turn,
  };
}

export function slotPosition(
  anchor: Pick<ActorState, "pos" | "heading">,
  slot: number,
  formation: number,
  cohesion: number,
): Vec2 {
  const row = Math.floor((slot - 1) / 2) + 1;
  const side = slot % 2 === 1 ? 1 : -1;
  const lateral =
    side *
    lerp(3.9 + row * 0.49, row * 1.38, formation) *
    lerp(1.5, 1, cohesion);
  const trailing = row * lerp(2.9, 1.85, formation);
  const forward = headingVector(anchor.heading);
  return {
    x: anchor.pos.x - forward.x * trailing + forward.z * lateral,
    z: anchor.pos.z - forward.z * trailing - forward.x * lateral,
  };
}

type Anchor = Pick<ActorState, "pos" | "heading">;

// Sample at a constant delay even between the sparse checkpointed trail samples.
export function trailAnchor(
  leader: Anchor,
  trail: readonly Anchor[],
  tick: number,
  row: number,
): Anchor {
  const { trailStride } = GOOSE;
  const newestAge = tick % trailStride;
  const age = (row + 0.5) * trailStride;
  const sample = (age - newestAge) / trailStride;
  const newer = trail[Math.floor(sample)] ?? leader;
  const older = trail[Math.ceil(sample)];
  if (!older) return trail.at(-1) ?? leader;
  const alpha = sample < 0 ? age / newestAge : sample % 1;
  return {
    pos: {
      x: lerp(newer.pos.x, older.pos.x, alpha),
      z: lerp(newer.pos.z, older.pos.z, alpha),
    },
    heading: newer.heading + angleDelta(newer.heading, older.heading) * alpha,
  };
}

function slotRank(slot: number): number {
  return slot === 0 ? 0 : Math.ceil(slot / 2) * (slot % 2 === 1 ? 1 : -1);
}

function separation(
  actor: ActorState,
  index: number,
  leader: ActorState,
  flock: readonly ActorState[],
): Vec2 {
  const { separationRadius, separationSpeed } = GOOSE;
  let x = 0;
  let z = 0;
  for (let i = 0; i < flock.length; i++) {
    const other = flock[i];
    if (!other || i === index || other.status === "strayed") continue;
    const dx = actor.pos.x - other.pos.x;
    const dz = actor.pos.z - other.pos.z;
    const gapSq = dx * dx + dz * dz;
    if (gapSq >= separationRadius * separationRadius) continue;
    const gap = Math.sqrt(gapSq);
    const strength = (1 - gap / separationRadius) ** 2 * separationSpeed;
    if (gap > 1e-6) {
      x += (dx / gap) * strength;
      z += (dz / gap) * strength;
    } else {
      // Exactly coincident birds use stable opposite directions across the flock.
      const side = slotRank(index) > slotRank(i) ? 1 : -1;
      x += Math.cos(leader.heading) * strength * side;
      z -= Math.sin(leader.heading) * strength * side;
    }
  }
  const scale = Math.max(1, Math.hypot(x, z) / separationSpeed);
  return { x: x / scale, z: z / scale };
}

export function follow(
  actor: ActorState,
  index: number,
  leader: ActorState,
  anchor: Anchor,
  state: Pick<GooseState, "actors" | "formation" | "cohesion">,
  bounds: LevelSchema["bounds"],
): ActorState {
  if (actor.status === "strayed") return actor;
  const target = slotPosition(anchor, index, state.formation, state.cohesion);
  const gap = distance(actor.pos, target);
  // Read every neighbor from the same tick and steer gently, without moving the
  // leader or introducing a second collision/position correction pass.
  const apart = separation(actor, index, leader, state.actors);
  const gain = actor.status === "rejoining" ? 1.65 : 2.6;
  const desiredX = (target.x - actor.pos.x) * gain + apart.x;
  const desiredZ = (target.z - actor.pos.z) * gain + apart.z;
  const desiredSpeed = Math.hypot(desiredX, desiredZ);
  const targetHeading =
    desiredSpeed > 0.15 ? Math.atan2(desiredX, desiredZ) : leader.heading;
  const heading = angleDelta(
    0,
    actor.heading +
      clamp(
        angleDelta(actor.heading, targetHeading),
        -GOOSE.followTurnRate * STEP_SEC,
        GOOSE.followTurnRate * STEP_SEC,
      ),
  );
  const targetSpeed =
    Math.min(desiredSpeed, GOOSE.followMaxSpeed) *
    lerp(0.6, 1, clamp(Math.cos(angleDelta(heading, targetHeading))));
  const speed = approach(
    actor.speed,
    targetSpeed,
    (targetSpeed >= actor.speed
      ? GOOSE.followAcceleration
      : GOOSE.followDeceleration) * STEP_SEC,
  );
  const forward = headingVector(heading);
  // A bounded sideways drift opens space before the birds finish banking away.
  const vx = forward.x * speed + apart.x;
  const vz = forward.z * speed + apart.z;
  const scale = Math.max(1, Math.hypot(vx, vz) / GOOSE.followMaxSpeed);
  const pos = boundPosition(
    {
      x: actor.pos.x + (vx / scale) * STEP_SEC,
      z: actor.pos.z + (vz / scale) * STEP_SEC,
    },
    bounds,
  );
  let status = actor.status;
  if (status === "rejoining" && gap < 7) status = "following";
  if (status === "following" && gap > 18) status = "loose";
  if (status === "loose" && gap < 12) status = "following";
  return { ...actor, heading, speed, pos, status };
}
