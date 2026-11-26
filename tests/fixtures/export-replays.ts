import { gzipSync } from "node:zlib";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type {
  CheckpointSnapshot,
  GameEvent,
  GameMode,
  GameState,
  WorldInput,
} from "../../src/core/game";

export interface ReplayRecord {
  readonly levelRevision: string;
  readonly mode: GameMode;
  readonly start: CheckpointSnapshot | null;
  readonly inputs: readonly WorldInput[];
  readonly events: readonly { tick: number; event: GameEvent }[];
  readonly expected: GameState;
  readonly retry?: GameState;
}

export async function writeReplay(
  name: string,
  replay: ReplayRecord,
): Promise<void> {
  const output = process.env.FEATHER_REPLAY_DIR;
  if (!output) return;
  await mkdir(output, { recursive: true });
  const record = {
    version: 1,
    tickHz: 60,
    levelRevision: replay.levelRevision,
    mode: replay.mode,
    start: replay.start,
    inputs: replay.inputs.map(({ move, ability }) => [
      move.x,
      move.z,
      ability ? 1 : 0,
    ]),
    events: replay.events,
    expected: replay.expected,
    retry: replay.retry,
  };
  await writeFile(
    join(output, `${name}.json.gz`),
    gzipSync(JSON.stringify(record)),
  );
}
