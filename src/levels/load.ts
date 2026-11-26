import {
  validateLevel,
  type AnyLevelSchema,
  type LevelSchema,
  type ReindeerLevel,
  type WhaleLevel,
} from "./schema";

type GooseLevelId = "playground" | "migration" | "rules";

export function loadLevel(id: GooseLevelId): Promise<LevelSchema>;
export function loadLevel(id: "whale"): Promise<WhaleLevel>;
export function loadLevel(id: "reindeer"): Promise<ReindeerLevel>;
export async function loadLevel(
  id: GooseLevelId | "whale" | "reindeer",
): Promise<AnyLevelSchema> {
  const url = `${import.meta.env.BASE_URL}levels/${id}.json`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  const level = validateLevel(
    await response.json(),
    url,
    id === "whale" || id === "reindeer" ? id : "goose",
  );
  if (level.id !== id)
    throw new Error(`${url}: unexpected level ID ${level.id}`);
  return level;
}
