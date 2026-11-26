import { readFile, readdir } from "node:fs/promises";
import { validateLevel } from "../src/levels/schema.ts";

const directory = new URL("../public/levels/", import.meta.url);
const files = (await readdir(directory))
  .filter((file) => file.endsWith(".json") && !/ \d+\.json$/.test(file))
  .sort();
if (
  !files.includes("playground.json") ||
  !files.includes("migration.json") ||
  !files.includes("rules.json") ||
  !files.includes("whale.json") ||
  !files.includes("reindeer.json")
) {
  throw new Error("Missing a required level");
}
for (const file of files) {
  const data: unknown = JSON.parse(
    await readFile(new URL(file, directory), "utf8"),
  );
  const level = validateLevel(data, file);
  if (file !== `${level.id}.json`)
    throw new Error(`${file}: mismatched level ID`);
  if (!level.titleEn) throw new Error(`${file}: missing English level title`);
  for (const segment of level.segments) {
    if (!segment.titleEn)
      throw new Error(`${file}: ${segment.id} is missing its English title`);
  }
  const markedAreas = [
    ...level.zones,
    ...level.triggers,
    ...level.landmarks,
    ...(level.species === "reindeer" ? level.barriers : []),
  ];
  for (const area of markedAreas) {
    if (!area.labelEn)
      throw new Error(`${file}: ${area.id} is missing its English label`);
  }
  console.log(`${level.id} ${level.levelRevision}`);
}
