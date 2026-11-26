import { validateLevel, type LevelSchema } from "./schema";

export const tailwindPracticeId = "tailwind-practice";
export const tailwindReedBankId = "tailwind-reed-bank";
export const tailwindCourseZones = [
  "tailwind-first",
  "tailwind-wide-water",
  "tailwind-second",
  tailwindReedBankId,
];
export const tailwindCourseMarks = [
  "tailwind-entry",
  "tailwind-bend",
  "tailwind-next",
  "tailwind-wide",
];

export function tailwindPractice(migration: LevelSchema): LevelSchema {
  const course = migration.segments.find(({ id }) => id === "S1");
  const entry = migration.landmarks.find(({ id }) => id === "tailwind-entry");
  const zones = migration.zones.filter(({ id }) =>
    tailwindCourseZones.includes(id),
  );
  const landmarks = migration.landmarks.filter(({ id }) =>
    tailwindCourseMarks.includes(id),
  );
  if (
    !course ||
    !entry ||
    zones.length !== tailwindCourseZones.length ||
    landmarks.length !== tailwindCourseMarks.length
  ) {
    throw new Error("Tailwind Turn Practice course is incomplete");
  }

  // Reuse the live course in world coordinates so wind behavior is identical.
  const start = { x: migration.bounds.min.x, z: 73 };
  const end = { x: 55, z: 261 };
  const finish = [
    { x: start.x, z: 217 },
    { x: end.x, z: 217 },
    end,
    { x: start.x, z: end.z },
    { x: start.x, z: 217 },
  ];
  return validateLevel(
    {
      schemaVersion: 1,
      levelRevision: "tailwind-practice-2",
      id: tailwindPracticeId,
      title: "顺风转弯试飞",
      titleEn: "Tailwind Turn Practice",
      species: "goose",
      modes: ["journey"],
      bounds: { min: start, max: end },
      spawn: { x: entry.pos.x, z: 99 },
      spawnSegment: course.id,
      segments: [{ ...course, start: start.z }],
      zones: [
        ...zones,
        {
          id: "goal",
          kind: "goal",
          label: "芦苇落脚地",
          labelEn: "Reedbed Landing Area",
          points: finish,
        },
      ],
      triggers: [],
      landmarks: [
        ...landmarks,
        {
          id: "goal-mark",
          kind: "beacon",
          label: "芦苇落脚地 · 全队抵达",
          labelEn: "Reedbed Landing Area · Land Together",
          pos: { x: -2, z: 231 },
        },
      ],
    },
    tailwindPracticeId,
    "goose",
  );
}
