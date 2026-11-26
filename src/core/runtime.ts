import {
  type CheckpointSnapshot,
  type GameCommand,
  type GameEvent,
  type GameMode,
  type GamePhase,
  type GameState,
  type GooseState,
  type ReindeerState,
  type WhaleState,
  NEUTRAL_INPUT,
  type WorldInput,
} from "./game";
import type { AnyLevelSchema, LevelSchema, WhaleLevel } from "../levels/schema";
import { initialState, tickWorld } from "../simulation/world";

type LevelState<L extends AnyLevelSchema> = L extends LevelSchema
  ? GooseState
  : L extends WhaleLevel
    ? WhaleState
    : ReindeerState;

export class GameRuntime<L extends AnyLevelSchema = AnyLevelSchema> {
  private before: GameState;
  private state: GameState;
  private saved: CheckpointSnapshot;
  private input = NEUTRAL_INPUT;

  constructor(
    readonly level: L,
    mode: GameMode,
    restored?: CheckpointSnapshot,
  ) {
    if (mode !== "journey") throw new Error("Only journey mode is supported");
    if (
      restored &&
      (restored.state.species !== level.species ||
        restored.state.levelId !== level.id ||
        restored.state.levelRevision !== level.levelRevision ||
        restored.state.mode !== mode)
    ) {
      throw new Error("Checkpoint does not match the active voyage");
    }
    this.state = restored?.state ?? initialState(level, mode);
    this.before = this.state;
    this.saved = restored ?? { version: 1, id: "start", state: this.state };
  }

  get current(): LevelState<L> {
    return this.state as LevelState<L>;
  }
  get previous(): LevelState<L> {
    return this.before as LevelState<L>;
  }
  get checkpoint(): CheckpointSnapshot {
    return this.saved;
  }

  private phase(phase: GamePhase): readonly GameEvent[] {
    this.input = NEUTRAL_INPUT;
    this.state = { ...this.state, phase };
    this.before = this.state;
    return [{ type: "phase", phase }];
  }

  dispatch(command: GameCommand): readonly GameEvent[] {
    switch (command.type) {
      case "input":
        if (this.state.phase === "playing") {
          const { move, ability } = command.input;
          const length = Math.hypot(move.x, move.z);
          this.input = Number.isFinite(length)
            ? {
                move: {
                  x: move.x / Math.max(1, length),
                  z: move.z / Math.max(1, length),
                },
                ability,
              }
            : NEUTRAL_INPUT;
        }
        break;
      case "pause":
        if (this.state.phase === "playing") return this.phase("paused");
        break;
      case "resume":
        if (this.state.phase === "paused") return this.phase("playing");
        break;
      case "retry":
        if (this.state.phase === "failed" || this.state.phase === "paused") {
          this.state = { ...this.saved.state, energy: 1, failure: null };
          return this.phase("playing");
        }
        break;
      case "finishLanding":
        if (this.state.phase === "landing")
          return [
            ...this.phase("completed"),
            { type: "completed", route: this.state.route },
          ];
        break;
    }
    return [];
  }

  step(
    onInput?: (tick: number, input: WorldInput) => void,
  ): readonly GameEvent[] {
    if (this.state.phase !== "playing") return [];
    onInput?.(this.state.tick + 1, this.input);
    const tick = tickWorld(this.state, this.input, this.level);
    this.before = this.state;
    this.state = tick.state;
    if (tick.checkpoint && tick.state.phase === "playing")
      this.saved = { version: 1, id: tick.checkpoint, state: tick.state };
    return tick.events;
  }
}
