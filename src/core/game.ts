import type { Vec2 } from "./math";

export type GameMode = "journey";
export type GamePhase =
  "playing" | "paused" | "failed" | "landing" | "completed";
export type CompanionStatus = "following" | "loose" | "strayed" | "rejoining";
export type Species = "goose" | "whale" | "reindeer";
export type GooseRoute = "mountain" | "lake";
export type WhaleRoute = "shipping" | "quiet";
export type ReindeerRoute = "dust" | "greenbelt";
export type Route = GooseRoute | WhaleRoute | ReindeerRoute;
export type WaterLayer = "surface" | "shallow" | "deep";
export type Failure = "energy" | "rescue";

export interface ActorState {
  readonly id: string;
  readonly pos: Vec2;
  readonly heading: number;
  readonly speed: number;
  readonly status: CompanionStatus;
  readonly rescueTicks: number | null;
  readonly rescueProgress: number;
}

export interface DiveState {
  readonly layer: WaterLayer;
  readonly direction: "down" | "up" | null;
  readonly progress: number;
  readonly depth: number;
  readonly breath: number;
  readonly forced: boolean;
  readonly needsRelease: boolean;
}

export interface WhaleActor extends ActorState {
  readonly dive: DiveState;
}

interface SharedState {
  readonly schemaVersion: 1;
  readonly levelId: string;
  readonly levelRevision: string;
  readonly mode: GameMode;
  readonly phase: GamePhase;
  readonly tick: number;
  readonly leaderId: string;
  readonly actors: readonly ActorState[];
  readonly energy: number;
  readonly cohesion: number;
  readonly segmentId: string;
  readonly route: Route | null;
  readonly routeLocked: boolean;
  readonly supply: Readonly<Record<string, number>>;
  readonly occupied: readonly string[];
  readonly triggered: readonly string[];
  readonly failure: Failure | null;
}

export interface AirEncounterState {
  readonly kite: "aloft" | "lowering" | "holding" | "rising" | "done";
  readonly kiteTick: number;
  readonly glider: "ready" | "inflating" | "crossing" | "leaving" | "done";
  readonly gliderTick: number;
  readonly disrupted: boolean;
  readonly clearingWing: boolean;
  readonly wingAt: Readonly<Record<string, number>>;
}

export interface GooseState extends SharedState {
  readonly encounters?: AirEncounterState;
  readonly species: "goose";
  readonly formation: number;
  readonly releasedTicks: number;
  readonly airborne: boolean;
  readonly ridgeRecovery?: "blocked" | "clearing";
  readonly trail: readonly { readonly pos: Vec2; readonly heading: number }[];
}

export interface WhaleState extends SharedState {
  readonly species: "whale";
  readonly actors: readonly WhaleActor[];
  /** Signed duration of the current ability input, capped at the pod's delay. */
  readonly diveInputTicks: number;
}

export interface ReindeerActor extends ActorState {
  /** Absolute breadcrumb index. Each companion follows its own part of the trail. */
  readonly trailIndex: number;
  readonly retreatZ: number | null;
}

export interface ReindeerState extends SharedState {
  readonly species: "reindeer";
  readonly actors: readonly ReindeerActor[];
  readonly trail: readonly Vec2[];
  readonly trailStart: number;
  readonly waitTicks: number;
  readonly waitBlocked: boolean;
  readonly alarmTicks: number;
}

export type GameState = GooseState | WhaleState | ReindeerState;

export interface WorldInput {
  readonly move: Vec2;
  readonly ability: boolean;
}

export const NEUTRAL_INPUT: WorldInput = Object.freeze({
  move: Object.freeze({ x: 0, z: 0 }),
  ability: false,
});

export type GameCommand =
  | { readonly type: "pause" | "resume" | "retry" | "finishLanding" }
  | { readonly type: "input"; readonly input: WorldInput };

export type GameEvent =
  | { readonly type: "phase"; readonly phase: GamePhase }
  | { readonly type: "zone"; readonly id: string; readonly entered: boolean }
  | { readonly type: "strayed" | "rejoined"; readonly id: string }
  | { readonly type: "checkpoint"; readonly id: string }
  | { readonly type: "route"; readonly route: Route }
  | { readonly type: "lowEnergy" }
  | { readonly type: "completed"; readonly route: Route | null };

export interface CheckpointSnapshot {
  readonly version: 1;
  readonly id: string;
  readonly state: GameState;
}
