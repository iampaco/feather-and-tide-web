import { STEP_SEC } from "../core/clock";
import type {
  GameEvent,
  GameMode,
  ReindeerActor,
  ReindeerState,
  WorldInput,
} from "../core/game";
import {
  angleDelta,
  approach,
  clamp,
  distance,
  lerp,
  type Vec2,
} from "../core/math";
import { contains, crosses } from "../levels/geometry";
import { sweptMovingHazard, type MovingHazard } from "../levels/moving-hazard";
import {
  groundBlocked,
  groundMove,
  hoofRadius,
  onRoad,
  roadVehicle,
} from "../levels/reindeer-ground";
import type { ReindeerLevel } from "../levels/schema";
import { REINDEER as R } from "./reindeer-tuning";
import { reindeerFollowTarget } from "./reindeer-trail";
import { reindeerDustRefuges, sampleReindeerDust } from "./reindeer-dust";
import { goalStatus, leaderOf, type TickResult } from "./world-rules";

export function initialReindeerState(
  level: ReindeerLevel,
  mode: GameMode,
): ReindeerState {
  const sampleCount =
    Math.ceil((R.spacing * (R.size - 1)) / R.sampleSpacing) + 1;
  const trail = Array.from({ length: sampleCount }, (_, i): Vec2 => ({
    x: level.spawn.x,
    z: level.spawn.z - (sampleCount - 1 - i) * R.sampleSpacing,
  }));
  const actors = Array.from({ length: R.size }, (_, index): ReindeerActor => {
    const trailIndex =
      sampleCount - 1 - Math.round((index * R.spacing) / R.sampleSpacing);
    const center = trail[trailIndex] ?? level.spawn;
    const lateral = index ? (index % 2 ? -1 : 1) * 1.1 : 0;
    const row = { x: center.x + lateral, z: center.z };
    return {
      id: `reindeer-${index}`,
      pos: groundBlocked(level, center, row, hoofRadius(index)) ? center : row,
      heading: 0,
      speed: 0,
      status: "following",
      trailIndex,
      retreatZ: null,
      rescueTicks: null,
      rescueProgress: 0,
    };
  });
  return {
    schemaVersion: 1,
    species: "reindeer",
    levelId: level.id,
    levelRevision: level.levelRevision,
    mode,
    tick: 0,
    phase: "playing",
    leaderId: "reindeer-0",
    actors,
    trail,
    trailStart: 0,
    waitTicks: 0,
    waitBlocked: false,
    alarmTicks: 0,
    energy: 1,
    cohesion: 1,
    segmentId: level.spawnSegment,
    route: null,
    routeLocked: false,
    supply: Object.fromEntries(
      level.zones.flatMap((zone) =>
        zone.kind === "supply" ? [[zone.id, zone.capacity]] : [],
      ),
    ),
    occupied: [],
    triggered: [],
    failure: null,
  };
}

function turn(actor: ReindeerActor, toward: number): number {
  const next =
    actor.heading +
    clamp(
      angleDelta(actor.heading, toward),
      -R.turn * STEP_SEC,
      R.turn * STEP_SEC,
    );
  return angleDelta(0, next);
}

function leaderMotion(
  level: ReindeerLevel,
  actor: ReindeerActor,
  input: WorldInput,
  holding: boolean,
  energy: number,
): ReindeerActor {
  const pressure = Math.hypot(input.move.x, input.move.z);
  const pacing =
    pressure <= 0.12
      ? lerp(0, R.walk, pressure / 0.12)
      : pressure <= 0.84
        ? lerp(R.walk, R.cruise, (pressure - 0.12) / 0.72)
        : lerp(
            R.cruise,
            energy <= R.criticalEnergy ? R.cruise : R.run,
            (pressure - 0.84) / 0.16,
          );
  const target = holding || pressure <= 0.015 ? 0 : pacing;
  const braking = holding ? R.waitBraking : R.braking;
  const speed = approach(
    actor.speed,
    target,
    (target > actor.speed ? R.acceleration : braking) * STEP_SEC,
  );
  const heading =
    pressure > 0.015 && (!holding || speed === 0)
      ? turn(actor, Math.atan2(input.move.x, input.move.z))
      : actor.heading;
  const pos = groundMove(
    level,
    actor.pos,
    {
      x: actor.pos.x + Math.sin(heading) * speed * STEP_SEC,
      z: actor.pos.z + Math.cos(heading) * speed * STEP_SEC,
    },
    hoofRadius(0),
  );
  return {
    ...actor,
    pos,
    heading,
    speed: Math.min(speed, distance(actor.pos, pos) / STEP_SEC),
  };
}

function approachPoint(
  level: ReindeerLevel,
  actor: ReindeerActor,
  point: Vec2,
  speed: number,
  index: number,
): ReindeerActor {
  const gap = distance(actor.pos, point);
  if (gap < 0.0001) return { ...actor, speed: 0 };
  const step = Math.min(1, (speed * STEP_SEC) / gap);
  const pos = groundMove(
    level,
    actor.pos,
    {
      x: lerp(actor.pos.x, point.x, step),
      z: lerp(actor.pos.z, point.z, step),
    },
    hoofRadius(index),
  );
  const moved = distance(actor.pos, pos);
  return {
    ...actor,
    pos,
    speed: Math.min(speed, moved / STEP_SEC),
    heading:
      moved > 0.0001
        ? turn(actor, Math.atan2(pos.x - actor.pos.x, pos.z - actor.pos.z))
        : actor.heading,
  };
}

function vehicleHit(
  level: ReindeerLevel,
  vehicle: MovingHazard,
  before: ReindeerActor,
  after: ReindeerActor,
  index: number,
  tick: number,
): boolean {
  return (
    (onRoad(level.road, before.pos) || onRoad(level.road, after.pos)) &&
    sweptMovingHazard(
      vehicle,
      before.pos,
      after.pos,
      hoofRadius(index),
      tick - 1,
      tick,
    )
  );
}

function retreatPoint(
  level: ReindeerLevel,
  actor: ReindeerActor,
  index: number,
): number {
  const { near, far } = level.road;
  const edge = actor.pos.z < (near + far) / 2 ? near : far;
  return edge + (edge === near ? -1 : 1) * (hoofRadius(index) + 1.2);
}

export function tickReindeer(
  state: ReindeerState,
  input: WorldInput,
  level: ReindeerLevel,
): TickResult<ReindeerState> {
  if (state.phase !== "playing") return { state, events: [], checkpoint: null };
  const tick = state.tick + 1;
  const events: GameEvent[] = [];
  const before = leaderOf(state);
  const vehicle = roadVehicle(level);
  let waitBlocked =
    input.ability && (onRoad(level.road, before.pos) || state.waitBlocked);
  let holding = input.ability && !waitBlocked;
  let leader = leaderMotion(level, before, input, holding, state.energy);
  if (onRoad(level.road, leader.pos) && input.ability) {
    holding = false;
    waitBlocked = true;
  }
  const waitTicks = holding ? Math.min(R.waitTicks, state.waitTicks + 1) : 0;
  let alarmTicks = Math.max(0, state.alarmTicks - 1);
  let contacts = 0;
  if (vehicleHit(level, vehicle, before, leader, 0, tick) && alarmTicks === 0) {
    leader = { ...leader, speed: 0 };
    contacts++;
    alarmTicks = R.alarmTicks;
  }

  const last = state.trail.at(-1) ?? before.pos;
  const trail =
    distance(last, leader.pos) >= R.sampleSpacing
      ? [
          ...state.trail.slice(
            Math.max(0, state.trail.length + 1 - R.trailSamples),
          ),
          leader.pos,
        ]
      : state.trail;
  const trailStart =
    state.trailStart +
    (trail !== state.trail ? state.trail.length + 1 - trail.length : 0);
  const trailEnd = trailStart + trail.length - 1;
  leader = { ...leader, trailIndex: trailEnd };
  const exposures = state.actors.map(
    (actor) => sampleReindeerDust(level, tick, actor.pos).strain,
  );
  const strain = exposures.reduce((sum, value) => sum + value, 0) / R.size;
  const keepGathered =
    state.segmentId === "R3" &&
    (sampleReindeerDust(level, tick, before.pos).inDust ||
      reindeerDustRefuges.some(({ zone }) => state.occupied.includes(zone))) &&
    leader.speed <= R.cruise + 0.12;

  const actors = state.actors.map((actor, index): ReindeerActor => {
    if (index === 0) return leader;
    const gap = distance(actor.pos, leader.pos);
    const exposure = exposures[index] ?? 0;
    if (actor.status === "strayed") {
      if (actor.retreatZ !== null) {
        const far = { x: actor.pos.x, z: actor.retreatZ };
        const step = approachPoint(level, actor, far, R.retreatSpeed, index);
        return {
          ...step,
          retreatZ: distance(step.pos, far) < 0.05 ? null : actor.retreatZ,
          rescueTicks: Math.max(0, (actor.rescueTicks ?? 1) - 1),
        };
      }
      const canReach =
        gap <= R.pickupRadius &&
        leader.speed <= R.pickupSpeed &&
        !onRoad(level.road, leader.pos) &&
        !groundBlocked(level, actor.pos, leader.pos, hoofRadius(index));
      const rescueProgress = canReach ? actor.rescueProgress + 1 : 0;
      if (rescueProgress >= R.pickupTicks) {
        return {
          ...actor,
          status: "rejoining",
          trailIndex: trailEnd,
          rescueTicks: null,
          rescueProgress: 0,
        };
      }
      return {
        ...actor,
        speed: 0,
        rescueProgress,
        rescueTicks: Math.max(0, (actor.rescueTicks ?? 1) - 1),
      };
    }

    // Rejoining skips the abandoned trail only when the leader has reached the same side.
    const rejoining = actor.status === "rejoining";
    const {
      point: nextPoint,
      cursor,
      nextIndex,
      withinCall,
    } = reindeerFollowTarget(
      level,
      { trail, trailStart, waitTicks },
      leader,
      actor,
      index,
      keepGathered,
    );
    // A call from the same side can release a follower stuck on an old turn.
    if (
      !rejoining &&
      withinCall &&
      leader.speed === 0 &&
      actor.pos.z > level.road.far &&
      groundBlocked(level, actor.pos, nextPoint, hoofRadius(index)) &&
      !groundBlocked(level, actor.pos, leader.pos, hoofRadius(index))
    )
      return { ...actor, status: "rejoining", trailIndex: trailEnd };
    const leadSpeed = withinCall ? Math.max(R.walk, gap / 3) : R.followMaxSpeed;
    const next = approachPoint(
      level,
      actor,
      nextPoint,
      Math.min(R.followMaxSpeed, leadSpeed) *
        Math.max(R.dustMinimumPace, 1 - exposure * R.dustFollowPenalty),
      index,
    );
    const hit = vehicleHit(level, vehicle, actor, next, index, tick);
    const limit = R.strayDistance + index * 0.8 - exposure * R.dustStrayPenalty;
    if (hit || gap > limit) {
      if (hit) contacts++;
      events.push({ type: "strayed", id: actor.id });
      return {
        ...next,
        status: "strayed",
        retreatZ: onRoad(level.road, next.pos)
          ? retreatPoint(level, next, index)
          : null,
        rescueTicks: R.rescueTicks,
        rescueProgress: 0,
      };
    }
    if (rejoining && gap <= R.formationRadius * 0.7)
      events.push({ type: "rejoined", id: actor.id });
    return {
      ...next,
      status:
        rejoining && gap > R.formationRadius * 0.7
          ? "rejoining"
          : gap > R.looseDistance + index * 0.8
            ? "loose"
            : "following",
      trailIndex: distance(next.pos, nextPoint) < 0.06 ? nextIndex : cursor,
    };
  });

  let triggered = [...state.triggered];
  let route = state.route;
  let routeLocked = state.routeLocked;
  for (const gate of level.triggers) {
    if (
      (gate.kind !== "route" && triggered.includes(gate.id)) ||
      !crosses(gate.points, before.pos, leader.pos)
    )
      continue;
    if (
      gate.kind === "route" &&
      !routeLocked &&
      route !== gate.route &&
      gate.crossingZ !== undefined &&
      before.pos.z < gate.crossingZ &&
      leader.pos.z >= gate.crossingZ &&
      contains(gate.points, leader.pos)
    ) {
      route = gate.route;
      const routeIds = new Set(
        level.triggers
          .filter((trigger) => trigger.kind === "route")
          .map(({ id }) => id),
      );
      triggered = triggered.filter((id) => !routeIds.has(id));
      triggered.push(gate.id);
      events.push({ type: "route", route });
    } else if (gate.kind === "merge" && route && leader.pos.z > before.pos.z) {
      routeLocked = true;
      triggered.push(gate.id);
    }
  }

  const roster = { species: state.species, leaderId: state.leaderId, actors };
  const occupied: string[] = [];
  const supply = { ...state.supply };
  let rest = false;
  let checkpoint: string | null = null;
  let energy =
    state.energy -
    STEP_SEC *
      lerp(
        R.idleDrain,
        leader.speed > R.cruise + 0.12 ? R.runDrain : R.cruiseDrain,
        clamp(leader.speed / R.cruise),
      ) -
    contacts * vehicle.cost;
  energy -= strain * STEP_SEC * R.dustDrain;
  for (const zone of level.zones) {
    const inZone = contains(zone.points, leader.pos);
    if (zone.kind === "hazard" ? onRoad(level.road, leader.pos) : inZone)
      occupied.push(zone.id);
    if (zone.kind === "sanctuary" && inZone) {
      rest = true;
      energy += R.safeRecovery * STEP_SEC;
    }
    if (zone.kind === "supply" && inZone) {
      rest = true;
      const together = actors.filter(
        (actor) =>
          actor.status !== "strayed" && contains(zone.points, actor.pos),
      ).length;
      if (together > actors.length / 2) {
        const remaining = supply[zone.id] ?? 0;
        const transfer = Math.min(
          remaining,
          Math.max(0, 1 - energy),
          R.supplyRate * STEP_SEC,
        );
        supply[zone.id] = remaining - transfer;
        energy += transfer;
      }
    }
    if (
      zone.kind === "checkpoint" &&
      inZone &&
      !triggered.includes(zone.id) &&
      (zone.id === "C1" || (triggered.includes("C1") && routeLocked)) &&
      goalStatus(roster, zone).canLand
    ) {
      triggered.push(zone.id);
      checkpoint = zone.id;
      events.push({ type: "checkpoint", id: zone.id });
    }
  }
  for (const id of occupied)
    if (!state.occupied.includes(id))
      events.push({ type: "zone", id, entered: true });
  for (const id of state.occupied)
    if (!occupied.includes(id))
      events.push({ type: "zone", id, entered: false });
  energy = clamp(energy);
  if (energy <= R.lowEnergy && state.energy > R.lowEnergy)
    events.push({ type: "lowEnergy" });

  const loosened = actors.filter(
    (actor) => actor.status !== "following",
  ).length;
  const cohesion = clamp(
    state.cohesion +
      STEP_SEC *
        ((holding ? 0.1 : 0.04) -
          loosened * 0.014 -
          strain * R.dustCohesionDrain) -
      contacts * 0.12,
  );
  const next: ReindeerState = {
    ...state,
    actors,
    tick,
    trail,
    trailStart,
    waitTicks,
    waitBlocked,
    alarmTicks,
    energy,
    cohesion,
    occupied,
    supply,
    triggered,
    route,
    routeLocked,
    segmentId:
      level.segments.findLast((segment) => segment.start <= leader.pos.z)?.id ??
      state.segmentId,
  };
  const goal = level.zones.find((zone) => zone.kind === "goal");
  if (goalStatus(next, goal).canLand) {
    events.push({ type: "phase", phase: "landing" });
    return { state: { ...next, phase: "landing" }, events, checkpoint: null };
  }
  const failure = actors.some((actor) => actor.rescueTicks === 0)
    ? "rescue"
    : energy === 0 && !rest
      ? "energy"
      : null;
  if (failure) events.push({ type: "phase", phase: "failed" });
  return {
    state: failure ? { ...next, phase: "failed", failure } : next,
    events,
    checkpoint,
  };
}
