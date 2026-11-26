import type {
  CheckpointSnapshot,
  GameMode,
  GooseState,
  Route,
  WhaleActor,
} from "./game";
import type {
  AnyLevelSchema,
  ReindeerLevel,
  WhaleLevel,
  Zone,
} from "../levels/schema";
import { contains } from "../levels/geometry";
import { whaleCheckpointArea } from "../levels/whale-checkpoint";
import { REINDEER } from "../simulation/reindeer-tuning";
import {
  initialEncounters,
  wingReactionTicks,
} from "../simulation/air-encounters";
import { GOOSE } from "../simulation/goose";
import { WHALE } from "../simulation/whale-motion";
import { goalStatus, initialState } from "../simulation/world";

function object(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function numeric(
  value: unknown,
  min: number,
  max: number,
  integer = false,
): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= min &&
    value <= max &&
    (!integer || Number.isInteger(value))
  );
}

function canUpgradeRevision(previous: unknown, current: string): boolean {
  const revisions = [
    "goose-p0-3",
    "goose-p0-4",
    "goose-p0-5",
    "goose-p0-6",
    "goose-p0-7",
    "goose-p0-8",
    "goose-p0-9",
    "goose-p0-10",
  ];
  const previousIndex = revisions.findIndex(
    (revision) => revision === previous,
  );
  return previousIndex >= 0 && previousIndex < revisions.indexOf(current);
}

function canUpgradeWhaleRevision(
  previous: unknown,
  level?: AnyLevelSchema,
): boolean {
  const revisions = [
    "whale-p2-1",
    "whale-p2-2",
    "whale-p2-3",
    "whale-p2-4",
    "whale-p2-5",
    "whale-p2-6",
    "whale-p2-7",
    "whale-p2-8",
    "whale-p2-9",
    "whale-p2-10",
    "whale-p2-11",
  ];
  const previousIndex = revisions.findIndex(
    (revision) => revision === previous,
  );
  return (
    level?.species === "whale" &&
    level.id === "whale" &&
    previousIndex >= 0 &&
    previousIndex < revisions.indexOf(level.levelRevision)
  );
}

function canUpgradeReindeerRevision(
  previous: unknown,
  level?: AnyLevelSchema,
): boolean {
  const revisions = [
    "reindeer-p3-2",
    "reindeer-p3-3",
    "reindeer-p3-4",
    "reindeer-p3-5",
  ];
  const previousIndex = revisions.findIndex(
    (revision) => revision === previous,
  );
  return (
    level?.species === "reindeer" &&
    level.id === "reindeer" &&
    previousIndex >= 0 &&
    previousIndex < revisions.indexOf(level.levelRevision)
  );
}

function canUpgradeSpeciesRevision(
  previous: unknown,
  level?: AnyLevelSchema,
): boolean {
  return (
    canUpgradeWhaleRevision(previous, level) ||
    canUpgradeReindeerRevision(previous, level)
  );
}

function knownRoute(value: unknown, level: AnyLevelSchema): value is Route {
  return level.species !== "goose"
    ? level.routes.some((route) => route === value)
    : value === "mountain" || value === "lake";
}

function validDive(value: unknown): boolean {
  const dive = object(value);
  if (
    !dive ||
    (dive.layer !== "surface" &&
      dive.layer !== "shallow" &&
      dive.layer !== "deep") ||
    (dive.direction !== null &&
      dive.direction !== "down" &&
      dive.direction !== "up") ||
    !numeric(dive.progress, 0, 1) ||
    !numeric(dive.depth, 0, 2) ||
    !numeric(dive.breath, 0, 1) ||
    typeof dive.forced !== "boolean" ||
    typeof dive.needsRelease !== "boolean"
  )
    return false;

  const layerDepth = { surface: 0, shallow: 1, deep: 2 }[dive.layer];
  return dive.direction === null
    ? dive.depth === layerDepth && dive.progress === 0
    : Math.abs(dive.depth - layerDepth) <= 1;
}

function validBranchRoute(
  level: WhaleLevel | ReindeerLevel,
  checkpoint: Zone,
  route: unknown,
  locked: boolean,
  triggered: readonly string[],
  recoveredBeforeFork: boolean,
): boolean {
  const divergence = level.triggers.filter(
    (trigger) => trigger.kind === "route",
  );
  const mergers = level.triggers.filter((trigger) => trigger.kind === "merge");
  const selectedGate = divergence.filter(({ id }) => triggered.includes(id));
  const routeConsistent =
    route === null
      ? selectedGate.length === 0
      : selectedGate.length === 1 && selectedGate[0]?.route === route;
  const hasMerge = mergers.some((trigger) => triggered.includes(trigger.id));

  const beforeFork =
    Math.max(...checkpoint.points.map(({ z }) => z)) <
    Math.min(
      ...divergence.map(
        (trigger) =>
          trigger.crossingZ ?? Math.min(...trigger.points.map(({ z }) => z)),
      ),
    );
  const beyondMerge =
    Math.min(...checkpoint.points.map(({ z }) => z)) >
    Math.max(...mergers.flatMap((trigger) => trigger.points.map(({ z }) => z)));

  return (
    (recoveredBeforeFork || !beforeFork || route === null) &&
    (!beyondMerge || locked) &&
    routeConsistent &&
    locked === hasMerge
  );
}

export function readCheckpoint(
  value: unknown,
  level: AnyLevelSchema,
  mode: GameMode,
): CheckpointSnapshot | undefined {
  if (mode !== "journey") return;
  const snapshot = object(value);
  if (!snapshot || snapshot.version !== 1 || typeof snapshot.id !== "string")
    return;
  const checkpoint = level.zones.find(
    (zone) => zone.kind === "checkpoint" && zone.id === snapshot.id,
  );
  const rawState = object(snapshot.state);
  const upgradingWhale = canUpgradeWhaleRevision(
    rawState?.levelRevision,
    level,
  );
  // P3-3 opens gaps and adds rest areas between the existing checkpoint sites.
  const upgradingReindeer = canUpgradeReindeerRevision(
    rawState?.levelRevision,
    level,
  );
  const state =
    upgradingWhale && rawState
      ? {
          ...rawState,
          levelRevision: level.levelRevision,
          triggered: Array.isArray(rawState.triggered)
            ? rawState.triggered.filter((id) => id !== "net-rescue")
            : rawState.triggered,
        }
      : upgradingReindeer && rawState
        ? { ...rawState, levelRevision: level.levelRevision }
        : rawState;
  const initial = initialState(level, mode);
  const tuning = { goose: GOOSE, whale: WHALE, reindeer: REINDEER }[
    level.species
  ];
  const upgrading =
    level.species === "goose" &&
    level.id === "migration" &&
    snapshot.id === "A" &&
    canUpgradeRevision(state?.levelRevision, level.levelRevision);
  if (
    !state ||
    !checkpoint ||
    state.schemaVersion !== 1 ||
    (state.species !== level.species &&
      !(level.species === "goose" && state.species === undefined)) ||
    state.phase !== "playing" ||
    state.failure !== null ||
    state.levelId !== level.id ||
    (state.levelRevision !== level.levelRevision && !upgrading) ||
    state.mode !== mode ||
    state.leaderId !== initial.leaderId ||
    !level.segments.some((segment) => segment.id === state.segmentId) ||
    !numeric(state.tick, 0, Number.MAX_SAFE_INTEGER, true) ||
    !numeric(state.energy, 0, 1) ||
    !numeric(state.cohesion, 0, 1) ||
    typeof state.routeLocked !== "boolean" ||
    (state.route !== null && !knownRoute(state.route, level)) ||
    (state.routeLocked && state.route === null)
  )
    return;

  function pose(value: unknown): boolean {
    const datum = object(value);
    const p = object(datum?.pos);
    return (
      !!p &&
      numeric(p.x, level.bounds.min.x, level.bounds.max.x) &&
      numeric(p.z, level.bounds.min.z, level.bounds.max.z) &&
      numeric(datum?.heading, -Math.PI, Math.PI)
    );
  }

  if (level.species === "goose") {
    if (level.encounters && (!upgrading || state.encounters !== undefined)) {
      const encounter = object(state.encounters);
      const wing = object(encounter?.wingAt);
      if (
        !encounter ||
        !wing ||
        !["aloft", "lowering", "holding", "rising", "done"].includes(
          String(encounter.kite),
        ) ||
        !["ready", "inflating", "crossing", "leaving", "done"].includes(
          String(encounter.glider),
        ) ||
        !numeric(encounter.kiteTick, 0, state.tick as number, true) ||
        !numeric(encounter.gliderTick, 0, state.tick as number, true) ||
        typeof encounter.disrupted !== "boolean" ||
        typeof encounter.clearingWing !== "boolean" ||
        (encounter.clearingWing && !encounter.disrupted) ||
        !Object.entries(wing).every(
          ([id, at]) =>
            initial.actors.some((a) => a.id === id) &&
            numeric(
              at,
              Math.max(0, (state.tick as number) - wingReactionTicks + 1),
              state.tick as number,
              true,
            ),
        )
      )
        return;
    }
    if (
      !numeric(state.releasedTicks, 0, GOOSE.coastTicks, true) ||
      !numeric(state.formation, 0, 1) ||
      typeof state.airborne !== "boolean" ||
      !Array.isArray(state.trail) ||
      state.trail.length > GOOSE.trailSamples ||
      !state.trail.every(pose)
    )
      return;
  } else if (level.species === "whale") {
    const delay = WHALE.followDiveTicks * (WHALE.size - 1) + 1;
    if (!numeric(state.diveInputTicks, -delay, delay, true)) return;
  } else if (
    !numeric(state.waitTicks, 0, REINDEER.waitTicks, true) ||
    typeof state.waitBlocked !== "boolean" ||
    !numeric(state.alarmTicks, 0, REINDEER.alarmTicks, true) ||
    !numeric(state.trailStart, 0, state.tick as number, true) ||
    !Array.isArray(state.trail) ||
    !state.trail.length ||
    state.trail.length > REINDEER.trailSamples ||
    !state.trail.every((pos: unknown) => pose({ pos, heading: 0 }))
  ) {
    return;
  }

  if (
    !Array.isArray(state.actors) ||
    state.actors.length !== initial.actors.length ||
    !state.actors.every((value: unknown, index: number) => {
      const actor = object(value);
      return (
        actor &&
        actor.id === initial.actors[index]?.id &&
        pose(actor) &&
        numeric(actor.speed, 0, tuning.followMaxSpeed) &&
        (level.species !== "whale" ||
          (validDive(actor.dive) &&
            (index !== 0 || actor.status === "following") &&
            (actor.status === "strayed" || actor.rescueProgress === 0))) &&
        ["following", "loose", "strayed", "rejoining"].includes(
          actor.status as string,
        ) &&
        (actor.status === "strayed"
          ? numeric(actor.rescueTicks, 1, tuning.rescueTicks, true)
          : actor.rescueTicks === null) &&
        numeric(actor.rescueProgress, 0, tuning.pickupTicks, true)
      );
    })
  )
    return;
  if (level.species === "reindeer") {
    const first = state.trailStart as number;
    const end = first + (state.trail as unknown[]).length - 1;
    if (
      !state.actors.every(
        (actor: Record<string, unknown>, index: number) =>
          (actor.status === "following" ||
            (index > 0 && actor.status === "loose")) &&
          contains(checkpoint.points, actor.pos as { x: number; z: number }) &&
          actor.retreatZ === null &&
          actor.rescueProgress === 0 &&
          numeric(actor.trailIndex, 0, end, true) &&
          (index !== 0 || actor.trailIndex === end),
      )
    )
      return;
  }

  const beforeForkRevision =
    upgrading && canUpgradeRevision(state.levelRevision, "goose-p0-6");
  const supply = object(state.supply);
  let restoredSupply =
    beforeForkRevision && supply && !("gallery-supply" in supply)
      ? { ...supply, "gallery-supply": initial.supply["gallery-supply"] }
      : supply;
  const kelpCapacity = initial.supply["net-kelp"];
  if (
    upgradingWhale &&
    supply &&
    kelpCapacity !== undefined &&
    !("net-kelp" in supply)
  )
    restoredSupply = { ...supply, "net-kelp": kelpCapacity };
  const returnCapacity = initial.supply["return-supply"];
  if (beforeForkRevision && returnCapacity !== undefined) {
    const oldCapacity = 0.62;
    const remaining = restoredSupply?.["return-supply"];
    if (typeof remaining !== "number" || !numeric(remaining, 0, oldCapacity))
      return;
    restoredSupply = {
      ...restoredSupply,
      "return-supply": Math.max(0, returnCapacity - (oldCapacity - remaining)),
    };
  }
  if (
    !restoredSupply ||
    Object.keys(restoredSupply).length !== Object.keys(initial.supply).length ||
    !Object.entries(initial.supply).every(([id, capacity]) =>
      numeric(restoredSupply[id], 0, capacity),
    )
  )
    return;
  const triggeredIds = new Set([
    ...level.triggers.map((trigger) => trigger.id),
    ...level.zones
      .filter((zone) => zone.kind === "checkpoint")
      .map((zone) => zone.id),
  ]);
  const zoneIds = new Set(level.zones.map((zone) => zone.id));
  if (
    !Array.isArray(state.triggered) ||
    !state.triggered.includes(checkpoint.id) ||
    !state.triggered.every((id) => triggeredIds.has(id)) ||
    !Array.isArray(state.occupied) ||
    !state.occupied.every((id) => zoneIds.has(id))
  )
    return;

  // A recovered C1 can retain the player's W3 decision, but must actually
  // contain the ready pod in one of the course's C1 saving areas.
  const recoveredBeforeFork =
    level.species === "whale" &&
    snapshot.id === "C1" &&
    state.route !== null &&
    level.zones.some((zone) => {
      const area = whaleCheckpointArea(zone);
      return area?.id === "C1" && area.fallback;
    }) &&
    level.zones.some(
      (zone) =>
        whaleCheckpointArea(zone)?.id === "C1" &&
        goalStatus(
          {
            species: "whale",
            actors: state.actors as WhaleActor[],
            leaderId: initial.leaderId,
          },
          zone,
        ).canLand,
    );
  if (
    level.species !== "goose" &&
    (new Set(state.triggered).size !== state.triggered.length ||
      new Set(state.occupied).size !== state.occupied.length ||
      !validBranchRoute(
        level,
        checkpoint,
        state.route,
        state.routeLocked,
        state.triggered,
        recoveredBeforeFork,
      ))
  )
    return;

  const validated = snapshot as unknown as CheckpointSnapshot;
  if (upgradingWhale || upgradingReindeer)
    return {
      ...validated,
      state: {
        ...state,
        supply: restoredSupply,
      } as unknown as CheckpointSnapshot["state"],
    };
  const unpublishedRoute =
    beforeForkRevision &&
    !validated.state.routeLocked &&
    level.triggers.some(
      (trigger) =>
        trigger.kind === "route" &&
        trigger.crossingZ !== undefined &&
        (validated.state.actors[0]?.pos.z ?? Infinity) < trigger.crossingZ,
    );
  if (!upgrading && state.species !== undefined) return validated;
  const goose = validated.state as GooseState;
  return {
    ...validated,
    state: {
      ...goose,
      ...(level.species === "goose" &&
        level.encounters &&
        !goose.encounters && { encounters: initialEncounters(true) }),
      species: "goose",
      levelRevision: level.levelRevision,
      supply: restoredSupply as CheckpointSnapshot["state"]["supply"],
      ...(unpublishedRoute && {
        route: null,
        triggered: validated.state.triggered.filter(
          (id) =>
            !level.triggers.some(
              (trigger) => trigger.kind === "route" && trigger.id === id,
            ),
        ),
      }),
    },
  };
}

interface SlotIdentity {
  readonly species: AnyLevelSchema["species"];
  readonly levelId: string;
  readonly mode: GameMode;
}

function slotIdentity(
  level: AnyLevelSchema | undefined,
  mode: GameMode,
): SlotIdentity | undefined {
  if (!level || (level.species === "goose" && level.id === "migration")) return;
  return { species: level.species, levelId: level.id, mode };
}

function slotKey(mode: GameMode, slot: SlotIdentity | undefined): IDBValidKey {
  return slot ? [slot.species, slot.levelId, slot.mode] : mode;
}

function sameSlot(
  record: Record<string, unknown>,
  slot: SlotIdentity | undefined,
  mode: GameMode,
): boolean {
  return slot
    ? record.species === slot.species &&
        record.levelId === slot.levelId &&
        record.mode === slot.mode
    : (record.species === undefined || record.species === "goose") &&
        (record.levelId === undefined || record.levelId === "migration") &&
        (record.mode === undefined || record.mode === mode);
}

interface RunIdentity extends Partial<SlotIdentity> {
  readonly version: 1;
  readonly runId: string;
  readonly levelRevision: string;
}

export type RunRecord = RunIdentity &
  (
    | { readonly kind: "started" }
    | { readonly kind: "checkpoint"; readonly checkpoint: CheckpointSnapshot }
    | {
        readonly kind: "arrived";
        readonly route: Route | null;
        readonly tick: number;
      }
  );

export function readRunRecord(
  value: unknown,
  level: AnyLevelSchema,
  mode: GameMode,
): RunRecord | undefined {
  if (mode !== "journey") return;
  const record = object(value);
  const slot = slotIdentity(level, mode);
  if (
    !record ||
    !sameSlot(record, slot, mode) ||
    record.version !== 1 ||
    (record.levelRevision !== level.levelRevision &&
      !canUpgradeSpeciesRevision(record.levelRevision, level) &&
      !(
        !slot && canUpgradeRevision(record.levelRevision, level.levelRevision)
      )) ||
    typeof record.runId !== "string" ||
    !/^[0-9a-f]{32}$/.test(record.runId)
  )
    return;
  const identity = {
    ...slot,
    version: 1 as const,
    runId: record.runId,
    levelRevision: level.levelRevision,
  };
  if (record.kind === "started") return { ...identity, kind: record.kind };
  if (record.kind === "checkpoint") {
    if (
      canUpgradeSpeciesRevision(record.levelRevision, level) &&
      object(object(record.checkpoint)?.state)?.levelRevision !==
        record.levelRevision
    )
      return;
    const checkpoint = readCheckpoint(record.checkpoint, level, mode);
    if (checkpoint) return { ...identity, kind: record.kind, checkpoint };
  }
  if (
    record.kind === "arrived" &&
    numeric(record.tick, 1, Number.MAX_SAFE_INTEGER, true) &&
    (knownRoute(record.route, level) ||
      (level.species !== "whale" && record.route === null))
  ) {
    return {
      ...identity,
      kind: record.kind,
      route: record.route,
      tick: record.tick,
    };
  }
}

function prepareWrite(
  mode: GameMode,
  record: RunRecord,
  level?: AnyLevelSchema,
) {
  const slot = slotIdentity(level, mode);
  const entry = { ...record, ...slot };
  if (
    (record.species !== undefined &&
      record.species !== (slot?.species ?? "goose")) ||
    (record.levelId !== undefined &&
      record.levelId !== (slot?.levelId ?? "migration")) ||
    (record.mode !== undefined && record.mode !== mode) ||
    (level && !readRunRecord(entry, level, mode))
  )
    throw new Error("航程存档无效");
  return { key: slotKey(mode, slot), slot, entry };
}

export class SaveStore {
  private opened: Promise<IDBDatabase> | undefined;

  private open(): Promise<IDBDatabase> {
    if (!this.opened) {
      this.opened = new Promise<IDBDatabase>((resolve, reject) => {
        const request = indexedDB.open("feather-tide", 1);
        request.onupgradeneeded = () =>
          request.result.createObjectStore("checkpoint");
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
        request.onblocked = () => reject(new Error("另一个页面正在使用存档"));
      }).catch((error: unknown) => {
        this.opened = undefined;
        throw error;
      });
    }
    return this.opened;
  }

  private async transaction<T>(
    mode: IDBTransactionMode,
    run: (store: IDBObjectStore, result: (value: T) => void) => void,
  ): Promise<T> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("checkpoint", mode);
      let value: T;
      tx.oncomplete = () => resolve(value);
      tx.onabort = () => reject(tx.error ?? new Error("存档事务中断"));
      tx.onerror = () => reject(tx.error);
      run(tx.objectStore("checkpoint"), (result) => {
        value = result;
      });
    });
  }

  read(mode: GameMode, level?: AnyLevelSchema): Promise<unknown> {
    const key = slotKey(mode, slotIdentity(level, mode));
    return this.transaction("readonly", (store, done) => {
      const request = store.get(key);
      request.onsuccess = () => done(request.result);
    });
  }

  async begin(
    mode: GameMode,
    record: RunRecord,
    level?: AnyLevelSchema,
  ): Promise<void> {
    const { key, entry } = prepareWrite(mode, record, level);
    return this.transaction("readwrite", (store, done) => {
      const request = store.get(key);
      request.onsuccess = () => {
        // A repeated initialization of the same run can't replace its progress.
        if (object(request.result)?.runId !== entry.runId)
          store.put(entry, key);
        done();
      };
    });
  }

  async replace(
    mode: GameMode,
    record: RunRecord,
    level?: AnyLevelSchema,
  ): Promise<boolean> {
    const { key, entry, slot } = prepareWrite(mode, record, level);
    return this.transaction("readwrite", (store, done) => {
      const request = store.get(key);
      request.onsuccess = () => {
        const latest = object(request.result);
        // Resolve competing writes in the same transaction that reads the slot.
        if (
          !latest ||
          (level && !readRunRecord(latest, level, mode)) ||
          !sameSlot(latest, slot, mode) ||
          latest.runId !== record.runId ||
          (latest.levelRevision !== record.levelRevision &&
            !canUpgradeSpeciesRevision(latest.levelRevision, level) &&
            !(
              !slot &&
              latest.kind === "checkpoint" &&
              canUpgradeRevision(latest.levelRevision, record.levelRevision)
            ))
        )
          return done(false);
        if (latest.kind === "arrived")
          return done(
            record.kind === "arrived" &&
              latest.tick === record.tick &&
              latest.route === record.route,
          );
        if (latest.kind === "checkpoint") {
          const latestTick = object(object(latest.checkpoint)?.state)?.tick;
          const nextTick =
            record.kind === "checkpoint"
              ? record.checkpoint.state.tick
              : record.kind === "arrived"
                ? record.tick
                : -1;
          if (typeof latestTick === "number" && latestTick > nextTick)
            return done(false);
        }
        store.put(entry, key);
        done(true);
      };
    });
  }
}
