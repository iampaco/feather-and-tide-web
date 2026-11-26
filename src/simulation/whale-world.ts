import { STEP_SEC } from "../core/clock";
import type {
  GameEvent,
  GameMode,
  WhaleActor,
  WhaleState,
  WorldInput,
} from "../core/game";
import { clamp, distance, lerp, type Vec2 } from "../core/math";
import { contains, crosses, sweptCircle } from "../levels/geometry";
import type { Trigger, WhaleLevel } from "../levels/schema";
import {
  whaleCheckpointArea,
  whaleCheckpointAvailable,
} from "../levels/whale-checkpoint";
import { whaleCrossflowVelocity } from "../levels/whale-crossflow";
import {
  canRideCurrent,
  flowProjection,
  type WaterCurrent,
} from "../levels/whale-current";
import {
  activeNoiseAt,
  insideNoise,
  isCyclicNoise,
} from "../levels/whale-noise";
import {
  hazardOffset,
  isWhaleNet,
  occupiesLayer,
  sweptWaterHazard,
  type WaterHazard,
} from "../levels/whale-geometry";
import { boundPosition } from "./goose";
import {
  followWhale,
  INITIAL_DIVE,
  podSlot,
  swimLeader,
  updateDive,
  WHALE,
  whaleRescueApproach,
} from "./whale-motion";
import {
  goalStatus,
  leaderOf,
  MODE_RULES,
  surfaced,
  type TickResult,
  whaleSupplyStatus,
} from "./world-rules";

export function initialWhaleState(
  level: WhaleLevel,
  mode: GameMode,
): WhaleState {
  const origin = { pos: level.spawn, heading: 0 };
  const actors = Array.from({ length: WHALE.size }, (_, i): WhaleActor => ({
    ...origin,
    id: `whale-${i}`,
    pos: i ? boundPosition(podSlot(origin, i, 1), level.bounds) : origin.pos,
    speed: 0,
    status: "following",
    rescueTicks: null,
    rescueProgress: 0,
    dive: { ...INITIAL_DIVE },
  }));
  return {
    schemaVersion: 1,
    species: "whale",
    levelId: level.id,
    levelRevision: level.levelRevision,
    mode,
    phase: "playing",
    tick: 0,
    leaderId: "whale-0",
    actors,
    energy: 1,
    cohesion: 1,
    diveInputTicks: 0,
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

function resolveWaterHazards(
  before: WhaleActor,
  after: WhaleActor,
  hazards: readonly WaterHazard[],
  tick: number,
  bounds: WhaleLevel["bounds"],
  contacts: Set<WaterHazard>,
): WhaleActor {
  const oldLayer = hazards.filter((hazard) =>
    occupiesLayer(hazard, before.dive.layer),
  );
  const hits = (hazard: WaterHazard, point: Vec2): boolean =>
    sweptWaterHazard(
      hazard,
      before.pos,
      point,
      WHALE.hitRadius,
      tick - 1,
      tick,
    );
  const impacts = oldLayer.filter((hazard) => hits(hazard, after.pos));
  let pos = after.pos;
  let speed = after.speed;
  if (impacts.length) {
    for (const hazard of impacts) contacts.add(hazard);
    const slides = [
      { x: after.pos.x, z: before.pos.z },
      { x: before.pos.x, z: after.pos.z },
    ].sort((a, b) => distance(before.pos, b) - distance(before.pos, a));
    // A lateral ship sweep can hit a stationary whale. In that case inherit
    // the ship's displacement for the contact step, with no added propulsion.
    for (const hazard of impacts) {
      if (!hazard.motion) continue;
      const from = hazardOffset(hazard, tick - 1);
      const to = hazardOffset(hazard, tick);
      slides.push(
        boundPosition(
          {
            x: before.pos.x + to.x - from.x,
            z: before.pos.z + to.z - from.z,
          },
          bounds,
        ),
      );
    }
    pos =
      slides.find((point) => !oldLayer.some((hazard) => hits(hazard, point))) ??
      before.pos;
    speed = Math.min(speed, distance(before.pos, pos) / STEP_SEC);
  }

  let dive = after.dive;
  if (dive.layer !== before.dive.layer) {
    // The path belongs to the old layer. Commit the new layer only at the
    // resolved endpoint and wait just below an occupied layer until it clears.
    const blocked = hazards.filter(
      (hazard) =>
        occupiesLayer(hazard, dive.layer) &&
        sweptWaterHazard(hazard, pos, pos, WHALE.hitRadius, tick, tick),
    );
    if (blocked.length) {
      for (const hazard of blocked) contacts.add(hazard);
      dive = {
        ...before.dive,
        direction: dive.depth > before.dive.depth ? "down" : "up",
        breath: dive.breath,
        needsRelease: dive.needsRelease,
        forced: before.dive.forced || dive.breath === 0,
      };
    }
  }
  return { ...after, pos, speed, dive };
}

function whaleRouteGate(
  level: WhaleLevel,
  state: WhaleState,
  leader: WhaleActor,
): Extract<Trigger, { kind: "route" }> | undefined {
  const from = leaderOf(state).pos;
  const to = leader.pos;
  const gates = level.triggers.filter((trigger) => trigger.kind === "route");
  const crossing = gates.find(({ crossingZ, points }) => {
    if (crossingZ === undefined || from.z >= crossingZ || to.z < crossingZ)
      return false;
    const x = lerp(from.x, to.x, (crossingZ - from.z) / (to.z - from.z));
    return contains(points, { x, z: crossingZ });
  });
  if (crossing || state.segmentId !== "W3") return crossing;

  const shipping = gates.find(({ route }) => route === "shipping");
  const quiet = gates.find(({ route }) => route === "quiet");
  const split = shipping?.crossingZ;
  if (
    split === undefined ||
    !shipping ||
    !quiet ||
    from.z < split ||
    to.z < split
  )
    return;
  const noise = level.zones.find(isCyclicNoise);
  const quietWater = level.zones.find(({ id }) => id === "quiet-rest");
  const clearWater = level.zones.find(({ id }) => id === "dredge-rest");
  const lastCurrent = level.zones.find(({ id }) => id === "reef-current-east");
  if (!noise || !quietWater || !clearWater || !lastCurrent) return;
  // Before the routes converge, remember the channel the player actually enters.
  // A gap between thresholds keeps the selection stable between the corridors.
  if (to.z > Math.max(...lastCurrent.points.map(({ z }) => z))) return;
  const alongsideNoise = to.z <= Math.max(...noise.points.map(({ z }) => z));
  const seam = Math.min(...shipping.points.map(({ x }) => x));
  const quietSide = alongsideNoise
    ? seam - WHALE.hitRadius * 2
    : Math.max(...quietWater.points.map(({ x }) => x));
  const shippingSide = alongsideNoise
    ? seam + WHALE.hitRadius * 2
    : Math.min(...clearWater.points.map(({ x }) => x));
  return to.x <= quietSide
    ? quiet
    : to.x >= shippingSide
      ? shipping
      : undefined;
}

export function tickWhale(
  state: WhaleState,
  input: WorldInput,
  level: WhaleLevel,
): TickResult<WhaleState> {
  const events: GameEvent[] = [];
  const tick = state.tick + 1;
  const rules = MODE_RULES[state.mode];
  const lastLeader = leaderOf(state);
  const podDive =
    input.ability && !lastLeader.dive.forced && !lastLeader.dive.needsRelease;
  const signed = podDive ? 1 : -1;
  const delayCap = WHALE.followDiveTicks * (WHALE.size - 1) + 1;
  const diveInputTicks =
    signed * Math.min(delayCap, 1 + Math.max(0, signed * state.diveInputTicks));
  const hazards = level.zones.filter((zone) => zone.kind === "hazard");
  const crossflows = level.zones.filter((zone) => zone.kind === "crossCurrent");
  function withDrift(before: WhaleActor, after: WhaleActor): WhaleActor {
    const drift = whaleCrossflowVelocity(crossflows, before.pos);
    if (!drift) return after;
    return {
      ...after,
      pos: boundPosition(
        {
          x: after.pos.x + drift.x * STEP_SEC,
          z: after.pos.z + drift.z * STEP_SEC,
        },
        level.bounds,
      ),
    };
  }
  const contacts = new Set<WaterHazard>();
  const netContacts = new Set<string>();
  const noise = activeNoiseAt(level, tick);
  const push = Math.hypot(input.move.x, input.move.z);
  const current =
    push > 0
      ? level.zones.find(
          (zone): zone is WaterCurrent =>
            zone.kind === "current" &&
            flowProjection(zone, input.move) >= zone.minAlignment * push &&
            canRideCurrent(zone, lastLeader),
        )
      : undefined;
  const dive = (actor: WhaleActor, i: number) => {
    const delay = i * WHALE.followDiveTicks;
    // The leading whale's emergency ascent propagates up the pod using the
    // same release delay as a deliberate ascent.
    const maintainDepth = Math.abs(diveInputTicks) <= delay;
    return updateDive(
      actor.dive,
      i === 0
        ? input.ability
        : actor.status === "strayed"
          ? false
          : maintainDepth
            ? actor.dive.direction === "down" ||
              (actor.dive.depth > 0 && actor.dive.direction !== "up")
            : podDive,
    );
  };
  const leader = resolveWaterHazards(
    lastLeader,
    withDrift(lastLeader, {
      ...swimLeader(lastLeader, input, state.energy, level.bounds, current),
      dive: dive(lastLeader, 0),
    }),
    hazards,
    tick,
    level.bounds,
    contacts,
  );
  let actors = [
    leader,
    ...state.actors.slice(1).map((actor, index) => {
      const actorContacts = new Set<WaterHazard>();
      const speedLimit = noise.reduce<number>(
        (speed, zone) =>
          insideNoise(zone, actor.pos)
            ? Math.min(speed, zone.cycle.followSpeed)
            : speed,
        WHALE.followMaxSpeed,
      );
      const swimmer = resolveWaterHazards(
        actor,
        withDrift(actor, {
          ...followWhale(
            actor,
            index + 1,
            leader,
            state.cohesion,
            level.bounds,
            speedLimit,
          ),
          dive: dive(actor, index + 1),
        }),
        hazards,
        tick,
        level.bounds,
        actorContacts,
      );
      for (const hazard of actorContacts) {
        contacts.add(hazard);
        if (isWhaleNet(hazard)) netContacts.add(actor.id);
      }
      return swimmer;
    }),
  ];

  let route = state.route;
  let routeLocked = state.routeLocked;
  let triggered = [...state.triggered];
  const gate = !routeLocked && whaleRouteGate(level, state, leader);
  if (gate && route !== gate.route) {
    route = gate.route;
    const gates = new Set(
      level.triggers
        .filter((trigger) => trigger.kind === "route")
        .map(({ id }) => id),
    );
    triggered = triggered.filter((id) => !gates.has(id));
    triggered.push(gate.id);
    events.push({ type: "route", route });
  }
  const newRescues = new Set<string>();
  for (const trigger of level.triggers) {
    if (
      trigger.kind === "route" ||
      triggered.includes(trigger.id) ||
      !crosses(trigger.points, lastLeader.pos, leader.pos)
    )
      continue;
    if (trigger.kind === "merge") {
      if (route === null) continue;
      routeLocked = true;
    } else {
      newRescues.add(trigger.actorId);
    }
    triggered.push(trigger.id);
  }

  const inNetSegment = state.segmentId === "W2";
  const rescueCandidates = actors.slice(1).filter((actor) => {
    if (actor.status === "strayed" || actor.status === "rejoining")
      return false;
    const gap = distance(actor.pos, leader.pos);
    return (
      newRescues.has(actor.id) ||
      (actor.status === "loose" && gap > WHALE.severeRescueGap) ||
      (inNetSegment && netContacts.has(actor.id) && gap >= WHALE.netRescueGap)
    );
  });
  const rescueIds = new Set(
    !inNetSegment
      ? rescueCandidates.map(({ id }) => id)
      : actors.some(
            ({ status }) => status === "strayed" || status === "rejoining",
          )
        ? []
        : rescueCandidates
            .sort(
              (a, b) =>
                distance(b.pos, leader.pos) - distance(a.pos, leader.pos),
            )
            .slice(0, 1)
            .map(({ id }) => id),
  );
  actors = actors.map((actor, i) => {
    if (i === 0) return actor;
    if (actor.status !== "strayed") {
      if (!rescueIds.has(actor.id)) return actor;
      events.push({ type: "strayed", id: actor.id });
      return {
        ...actor,
        speed: 0,
        status: "strayed",
        rescueProgress: 0,
        rescueTicks: WHALE.rescueTicks,
      };
    }
    const progress =
      whaleRescueApproach(leader, actor) === "ready"
        ? actor.rescueProgress + 1
        : 0;
    if (progress >= WHALE.pickupTicks) {
      events.push({ type: "rejoined", id: actor.id });
      return {
        ...actor,
        status: "rejoining",
        rescueProgress: 0,
        rescueTicks: null,
      };
    }
    return {
      ...actor,
      rescueProgress: progress,
      rescueTicks:
        actor.rescueTicks === null ? null : Math.max(0, actor.rescueTicks - 1),
    };
  });

  const activeZones = level.zones.filter(
    (zone) =>
      zone.kind !== "hazard" &&
      (zone.kind !== "current" || zone === current) &&
      !(
        zone.kind === "interference" &&
        zone.cycle &&
        !noise.some((active) => active === zone)
      ) &&
      contains(zone.points, leader.pos),
  );
  // Brief clearance while sliding along the same net is still one encounter.
  // Rescue eligibility above uses the actual swept hits for each whale.
  for (const net of hazards.filter(isWhaleNet)) {
    if (
      state.occupied.includes(net.id) &&
      actors.some(({ pos }) =>
        sweptCircle(
          net.points,
          pos,
          pos,
          WHALE.hitRadius + WHALE.netContactReleaseMargin,
        ),
      )
    )
      contacts.add(net);
  }
  const occupied = [...activeZones, ...contacts].map(({ id }) => id);
  for (const id of occupied)
    if (!state.occupied.includes(id))
      events.push({ type: "zone", id, entered: true });
  for (const id of state.occupied)
    if (!occupied.includes(id))
      events.push({ type: "zone", id, entered: false });

  const rest = activeZones.some(
    ({ kind }) => kind === "sanctuary" || kind === "supply",
  );
  const resting = activeZones.some(({ kind }) => kind === "sanctuary");
  const speedRatio = leader.speed / WHALE.cruise;
  const strain = activeZones.reduce(
    (amount, zone) => amount + (zone.kind === "interference" ? zone.strain : 0),
    0,
  );
  let energy =
    state.energy +
    STEP_SEC *
      (resting && surfaced(leader)
        ? 0.065
        : -0.0035 *
          speedRatio ** 2 *
          (1 + 0.2 * strain) *
          (1 - (current?.energySaving ?? 0)));
  const steadyStrain = activeZones.reduce(
    (amount, zone) =>
      amount + (zone.kind === "interference" && !zone.cycle ? zone.strain : 0),
    0,
  );
  const noiseLoss = noise.reduce(
    (amount, zone) =>
      amount +
      (zone.cycle.cohesionLoss *
        actors.filter(({ pos }) => insideNoise(zone, pos)).length) /
        actors.length,
    0,
  );
  let cohesion =
    state.cohesion +
    STEP_SEC * (noiseLoss > 0 ? -noiseLoss : 0.09 - steadyStrain * 0.12);
  const supply = { ...state.supply };
  for (const zone of activeZones) {
    if (
      zone.kind !== "supply" ||
      !whaleSupplyStatus(leader, actors, zone).ready
    )
      continue;
    const capacity = supply[zone.id] ?? 0;
    const transfer = Math.min(
      capacity,
      Math.max(0, 1 - energy),
      0.14 * STEP_SEC,
    );
    supply[zone.id] = capacity - transfer;
    energy += transfer;
  }
  if (rules.contactCost) {
    let netCost = 0;
    for (const hazard of contacts) {
      if (state.occupied.includes(hazard.id)) continue;
      if (isWhaleNet(hazard)) {
        netCost = Math.max(netCost, hazard.cost);
        continue;
      }
      energy -= hazard.cost;
      cohesion -= hazard.cost;
    }
    if (
      !hazards.some(
        (zone) => isWhaleNet(zone) && state.occupied.includes(zone.id),
      )
    ) {
      energy -= netCost;
      cohesion -= netCost;
    }
  }
  energy = clamp(energy, rules.fatigueFloor);
  if (energy <= WHALE.lowEnergy && state.energy > WHALE.lowEnergy)
    events.push({ type: "lowEnergy" });

  const roster = {
    species: "whale" as const,
    actors,
    leaderId: state.leaderId,
  };
  let checkpoint: string | null = null;
  for (const zone of activeZones) {
    const area = whaleCheckpointArea(zone);
    if (
      !area ||
      !whaleCheckpointAvailable(level, area, triggered, routeLocked) ||
      !goalStatus(roster, zone).canLand
    )
      continue;
    checkpoint = area.id;
    triggered.push(area.id);
    events.push({ type: "checkpoint", id: area.id });
    break;
  }
  const next: WhaleState = {
    ...state,
    tick,
    actors,
    energy,
    cohesion: clamp(cohesion),
    diveInputTicks,
    segmentId:
      level.segments.findLast(({ start }) => start <= leader.pos.z)?.id ??
      level.spawnSegment,
    route,
    routeLocked,
    supply,
    occupied,
    triggered,
  };
  const goal = level.zones.find(({ kind }) => kind === "goal");
  // The recovery water overlaps the goal. Publish its playable snapshot before
  // handing control to the reunion sequence.
  if (!checkpoint && goalStatus(next, goal).canLand) {
    events.push({ type: "phase", phase: "landing" });
    return { state: { ...next, phase: "landing" }, events, checkpoint };
  }
  const failure = rules.canFail
    ? actors.some(({ rescueTicks }) => rescueTicks === 0)
      ? "rescue"
      : energy === 0 && !rest
        ? "energy"
        : null
    : null;
  if (failure) events.push({ type: "phase", phase: "failed" });
  return {
    state: failure ? { ...next, phase: "failed", failure } : next,
    events,
    checkpoint,
  };
}
