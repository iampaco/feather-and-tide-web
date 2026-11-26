import { STEP_SEC } from "../core/clock";
import type {
  ActorState,
  GameEvent,
  GameMode,
  GameState,
  GooseState,
  ReindeerState,
  WhaleState,
  WorldInput,
} from "../core/game";
import { clamp, distance, lerp, type Vec2 } from "../core/math";
import { contains, crosses, sweptCircle } from "../levels/geometry";
import type {
  AnyLevelSchema,
  LevelSchema,
  ReindeerLevel,
  WhaleLevel,
  Zone,
} from "../levels/schema";
import { advanceEncounters, initialEncounters } from "./air-encounters";
import { sampleWind } from "../levels/wind";
import {
  follow,
  boundPosition,
  GOOSE,
  headingVector,
  moveLeader,
  rescueApproach,
  slotPosition,
  trailAnchor,
} from "./goose";

import { initialWhaleState, tickWhale } from "./whale-world";
import { initialReindeerState, tickReindeer } from "./reindeer-world";
import {
  MODE_RULES,
  goalStatus,
  leaderOf,
  type TickResult,
} from "./world-rules";

export { goalStatus, leaderOf } from "./world-rules";

// Keep the escape cue visible through the first few units of a low-speed turn.
const ridgeClearance = 4;

export function initialState(level: LevelSchema, mode: GameMode): GooseState;
export function initialState(level: WhaleLevel, mode: GameMode): WhaleState;
export function initialState(
  level: ReindeerLevel,
  mode: GameMode,
): ReindeerState;
export function initialState(level: AnyLevelSchema, mode: GameMode): GameState;
export function initialState(level: AnyLevelSchema, mode: GameMode): GameState {
  if (mode !== "journey") throw new Error("Only journey mode is supported");
  if (level.species === "reindeer") return initialReindeerState(level, mode);
  return level.species === "whale"
    ? initialWhaleState(level, mode)
    : initialGooseState(level, mode);
}

function initialGooseState(level: LevelSchema, mode: GameMode): GooseState {
  const leader = { pos: level.spawn, heading: 0 };
  const actors = Array.from({ length: GOOSE.size }, (_, i): ActorState => ({
    id: `goose-${i}`,
    pos: i === 0 ? leader.pos : slotPosition(leader, i, 0, 1),
    heading: 0,
    speed: 0,
    status: "following",
    rescueTicks: null,
    rescueProgress: 0,
  }));
  return {
    schemaVersion: 1,
    species: "goose",
    ...(level.encounters && { encounters: initialEncounters() }),
    levelId: level.id,
    levelRevision: level.levelRevision,
    mode,
    phase: "playing",
    tick: 0,
    leaderId: "goose-0",
    actors,
    energy: 1,
    cohesion: 1,
    formation: 0,
    releasedTicks: 0,
    airborne: false,
    trail: [],
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

export function rotorPhase(tick: number, index: number): number {
  return (tick * STEP_SEC * 1.65 + index * 1.7) % (2 * Math.PI);
}

function avoidHazards(
  before: ActorState,
  after: ActorState,
  hazards: readonly Zone[],
): ActorState {
  function blocked(pos: Vec2): boolean {
    return hazards.some((zone) =>
      sweptCircle(zone.points, before.pos, pos, GOOSE.hitRadius),
    );
  }
  if (!blocked(after.pos)) return after;

  // Try tangential motion against the same visible boundaries, including corners.
  const horizontal = { x: after.pos.x, z: before.pos.z };
  const vertical = { x: before.pos.x, z: after.pos.z };
  const slide = [horizontal, vertical]
    .sort((a, b) => distance(before.pos, b) - distance(before.pos, a))
    .find((pos) => !blocked(pos));
  return { ...after, pos: slide ?? before.pos };
}

function arriveInZone(
  zone: Zone,
  actors: readonly ActorState[],
  leader: ActorState,
): boolean {
  const leaderIn = contains(zone.points, leader.pos);
  switch (zone.kind) {
    case "hazard":
      return actors.some((actor) => contains(zone.points, actor.pos));
    case "supply":
      return (
        leaderIn &&
        actors.filter(
          (actor) =>
            actor.status !== "strayed" && contains(zone.points, actor.pos),
        ).length >
          actors.length / 2
      );
    case "checkpoint":
      return goalStatus({ species: "goose", actors, leaderId: leader.id }, zone)
        .canLand;
    default:
      return leaderIn;
  }
}

export function tickWorld(
  state: GooseState,
  input: WorldInput,
  level: LevelSchema,
): TickResult<GooseState>;
export function tickWorld(
  state: WhaleState,
  input: WorldInput,
  level: WhaleLevel,
): TickResult<WhaleState>;
export function tickWorld(
  state: ReindeerState,
  input: WorldInput,
  level: ReindeerLevel,
): TickResult<ReindeerState>;
export function tickWorld(
  state: GameState,
  input: WorldInput,
  level: AnyLevelSchema,
): TickResult;
export function tickWorld(
  state: GameState,
  input: WorldInput,
  level: AnyLevelSchema,
): TickResult {
  if (state.species === "whale" && level.species === "whale")
    return tickWhale(state, input, level);
  if (state.species === "reindeer" && level.species === "reindeer")
    return tickReindeer(state, input, level);
  if (state.species === "goose" && level.species === "goose")
    return tickGoose(state, input, level);
  throw new Error("State and level species differ");
}

function tickGoose(
  state: GooseState,
  input: WorldInput,
  level: LevelSchema,
): TickResult<GooseState> {
  const events: GameEvent[] = [];
  const tick = state.tick + 1;
  const rules = MODE_RULES[state.mode];
  const leaderBefore = leaderOf(state);
  const flight = moveLeader(leaderBefore, state, input, level.bounds);
  const { direction: wind, drift } = sampleWind(
    level,
    leaderBefore.pos,
    state.tick,
  );
  const travel =
    !state.airborne || (drift.x === 0 && drift.z === 0)
      ? flight.actor
      : {
          ...flight.actor,
          pos: boundPosition(
            {
              x: flight.actor.pos.x + drift.x * STEP_SEC,
              z: flight.actor.pos.z + drift.z * STEP_SEC,
            },
            level.bounds,
          ),
        };
  const hazards = level.zones.filter((zone) => zone.kind === "hazard");
  const leader = avoidHazards(leaderBefore, travel, hazards);
  const airborne = state.airborne || leader.speed > 0;
  const segment = level.segments.findLast((item) => item.start <= leader.pos.z);
  const segmentId = segment?.id ?? level.spawnSegment;
  const ridge =
    segmentId === "S2" && hazards.find(({ id }) => id === "ridge-wall");
  const ridgeStalled = Boolean(
    ridge &&
    leader.pos.x === leaderBefore.pos.x &&
    leader.pos.z === leaderBefore.pos.z &&
    sweptCircle(ridge.points, leaderBefore.pos, travel.pos, GOOSE.hitRadius),
  );
  const ridgeRecovery = ridgeStalled
    ? "blocked"
    : ridge &&
        state.ridgeRecovery &&
        sweptCircle(
          ridge.points,
          leader.pos,
          leader.pos,
          GOOSE.hitRadius + ridgeClearance,
        )
      ? "clearing"
      : undefined;
  const trail =
    airborne && tick % GOOSE.trailStride === 0
      ? [{ pos: leader.pos, heading: leader.heading }, ...state.trail].slice(
          0,
          GOOSE.trailSamples,
        )
      : state.trail;
  const companions = state.actors.slice(1);
  const flockState = {
    actors: state.actors,
    formation: flight.formation,
    cohesion: state.cohesion,
  };
  const attempted = companions.map((actor, i) => {
    return airborne
      ? follow(
          actor,
          i + 1,
          leader,
          trailAnchor(leader, trail, tick, Math.floor(i / 2)),
          flockState,
          level.bounds,
        )
      : actor;
  });
  let actors = [
    leader,
    ...attempted.map((actor, i) => {
      const before = companions[i];
      return before ? avoidHazards(before, actor, hazards) : actor;
    }),
  ];
  const encounters =
    airborne && level.encounters && state.encounters
      ? advanceEncounters(
          level.encounters,
          state.encounters,
          tick,
          state.actors,
          actors,
        )
      : state.encounters;
  const formation = encounters?.clearingWing ? 0 : flight.formation;
  const occupied = level.zones
    .filter((zone) => arriveInZone(zone, actors, leader))
    .map((zone) => zone.id);
  const contacts = hazards.filter((zone) => {
    if (sweptCircle(zone.points, leaderBefore.pos, travel.pos, GOOSE.hitRadius))
      return true;
    return attempted.some((actor, i) => {
      const before = companions[i];
      return (
        before !== undefined &&
        sweptCircle(zone.points, before.pos, actor.pos, GOOSE.hitRadius)
      );
    });
  });
  occupied.push(
    ...contacts.map((zone) => zone.id).filter((id) => !occupied.includes(id)),
  );
  for (const id of occupied)
    if (!state.occupied.includes(id))
      events.push({ type: "zone", id, entered: true });
  for (const id of state.occupied)
    if (!occupied.includes(id))
      events.push({ type: "zone", id, entered: false });

  let route = state.route;
  let routeLocked = state.routeLocked;
  const triggered = [...state.triggered];
  const newRescues = new Set<string>();
  for (const trigger of level.triggers) {
    if (trigger.kind === "route" && trigger.crossingZ !== undefined) {
      const from = leaderBefore.pos;
      const to = leader.pos;
      const z = trigger.crossingZ;
      if (routeLocked || from.z >= z || to.z < z) continue;
      const x = lerp(from.x, to.x, (z - from.z) / (to.z - from.z));
      if (!contains(trigger.points, { x, z })) continue;
      if (route !== trigger.route) {
        route = trigger.route;
        events.push({ type: "route", route });
      }
      if (!triggered.includes(trigger.id)) triggered.push(trigger.id);
      continue;
    }
    if (
      triggered.includes(trigger.id) ||
      !crosses(trigger.points, leaderBefore.pos, leader.pos)
    )
      continue;
    if (trigger.kind === "route" && !routeLocked && route === null) {
      route = trigger.route;
      events.push({ type: "route", route });
    }
    if (trigger.kind === "merge" && route !== null) routeLocked = true;
    if (trigger.kind === "rescue") newRescues.add(trigger.actorId);
    triggered.push(trigger.id);
  }

  const supply = { ...state.supply };
  let energy = state.energy;
  let cohesion = state.cohesion;
  const inRest = level.zones.some(
    (zone) =>
      (zone.kind === "sanctuary" || zone.kind === "supply") &&
      contains(zone.points, leader.pos),
  );
  if (airborne) {
    const direction = headingVector(leader.heading);
    const headwind = -(direction.x * wind.x + direction.z * wind.z);
    const crosswind = Math.abs(wind.x * direction.z - wind.z * direction.x);
    const activeZones = level.zones.filter((zone) =>
      occupied.includes(zone.id),
    );
    const interference = activeZones.reduce(
      (strain, zone) =>
        strain + (zone.kind === "interference" ? zone.strain : 0),
      0,
    );
    const speedRatio = leader.speed / GOOSE.cruise;
    const drain =
      0.012 *
        (0.22 + 0.78 * speedRatio ** 2) *
        (1 + 0.65 * headwind + 0.12 * interference) *
        (1 - GOOSE.formationSaving * formation) +
      0.09 * Math.abs(flight.turn);
    const safeHabitat = activeZones.some((zone) => zone.kind === "sanctuary");
    // Airspeed still drives inertia and steering. Charging it while the ridge
    // rejects all movement would punish a player who is stuck at the boundary.
    if (safeHabitat) energy += 0.1 * STEP_SEC;
    else if (!ridgeStalled) energy -= drain * STEP_SEC;
    cohesion = clamp(
      cohesion +
        STEP_SEC *
          (0.085 +
            0.13 * formation -
            0.15 * crosswind -
            0.08 * interference -
            0.18 * Math.max(0, speedRatio - 1)) -
        0.12 * Math.abs(flight.turn),
    );
    for (const zone of activeZones) {
      if (zone.kind !== "supply") continue;
      const capacity = supply[zone.id] ?? 0;
      const transfer = Math.min(
        capacity,
        Math.max(0, 1 - energy),
        0.14 * STEP_SEC,
      );
      supply[zone.id] = Math.max(0, capacity - transfer);
      energy += transfer;
    }
    if (rules.contactCost) {
      for (const zone of contacts) {
        if (zone.kind !== "hazard" || state.occupied.includes(zone.id))
          continue;
        energy -= zone.cost;
        cohesion = clamp(cohesion - zone.cost);
      }
    }
    energy = clamp(energy, rules.fatigueFloor);
    if (energy <= GOOSE.lowEnergy && state.energy > GOOSE.lowEnergy)
      events.push({ type: "lowEnergy" });
  }

  actors = actors.map((actor, i): ActorState => {
    if (i === 0) return actor;
    if (actor.status !== "strayed") {
      if (
        !newRescues.has(actor.id) &&
        (actor.status !== "loose" || distance(actor.pos, leader.pos) < 67)
      )
        return actor;
      events.push({ type: "strayed", id: actor.id });
      return {
        ...actor,
        status: "strayed",
        speed: 0,
        rescueTicks: GOOSE.rescueTicks,
        rescueProgress: 0,
      };
    }
    const rescueProgress =
      rescueApproach(leader, actor) === "ready" ? actor.rescueProgress + 1 : 0;
    if (rescueProgress >= GOOSE.pickupTicks) {
      events.push({ type: "rejoined", id: actor.id });
      return {
        ...actor,
        status: "rejoining",
        rescueTicks: null,
        rescueProgress: 0,
      };
    }
    return {
      ...actor,
      rescueProgress,
      rescueTicks:
        actor.rescueTicks === null ? null : Math.max(0, actor.rescueTicks - 1),
    };
  });
  let checkpoint: string | null = null;
  for (const zone of level.zones) {
    if (
      zone.kind === "checkpoint" &&
      !triggered.includes(zone.id) &&
      arriveInZone(zone, actors, leader)
    ) {
      checkpoint = zone.id;
      triggered.push(zone.id);
      events.push({ type: "checkpoint", id: zone.id });
    }
  }
  const next: GooseState = {
    ...state,
    tick,
    airborne,
    actors,
    energy,
    cohesion,
    formation,
    releasedTicks: flight.releasedTicks,
    ...(encounters && { encounters }),
    ridgeRecovery,
    trail,
    segmentId,
    route,
    routeLocked,
    supply,
    occupied,
    triggered,
  };
  const goal = level.zones.find((zone) => zone.kind === "goal");
  if (goalStatus(next, goal).canLand) {
    events.push({ type: "phase", phase: "landing" });
    return { state: { ...next, phase: "landing" }, events, checkpoint };
  }
  if (rules.canFail) {
    const failure = actors.some((actor) => actor.rescueTicks === 0)
      ? "rescue"
      : energy === 0 && !inRest
        ? "energy"
        : null;
    if (failure) {
      events.push({ type: "phase", phase: "failed" });
      return {
        state: { ...next, phase: "failed", failure },
        events,
        checkpoint,
      };
    }
  }
  return { state: next, events, checkpoint };
}
