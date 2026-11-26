import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import {
  freshGooseTeaching,
  gooseTeaching,
  gooseTurnLessonEnd,
  type GooseTeachingInput,
} from "../../src/app/goose-teaching";
import type { GooseState } from "../../src/core/game";
import { DEFAULT_SETTINGS } from "../../src/input/input";
import { validateLevel } from "../../src/levels/schema";
import { initialState } from "../../src/simulation/world";

function loadLevel(name: string) {
  const path = `public/levels/${name}.json`;
  return validateLevel(JSON.parse(readFileSync(path, "utf8")), path, "goose");
}

const level = loadLevel("migration");
const initial = initialState(level, "journey");
const input = {
  enabled: true,
  level,
  state: initial,
  leaderZ: level.spawn.z,
  touch: true,
  settings: DEFAULT_SETTINGS,
  abilityHeld: false,
  cameraDragDistance: 0,
  seenReset: false,
  inWind: false,
} satisfies GooseTeachingInput;

test("a touch starts the floating stick on the configured side", () => {
  expect(gooseTeaching(freshGooseTeaching, input).cue?.title).toBe(
    "在左侧按住并拖动，带雁群起飞",
  );
  expect(gooseTeaching(freshGooseTeaching, input).cue?.detail).toContain(
    "推到外圈会加速",
  );
  expect(
    gooseTeaching(freshGooseTeaching, {
      ...input,
      settings: { ...input.settings, mirror: true },
    }).cue?.title,
  ).toBe("在右侧按住并拖动，带雁群起飞");
});

test("takeoff, glide and camera instructions honor remapped keyboard controls", () => {
  const keyboard = {
    ...input,
    touch: false,
    settings: {
      ...input.settings,
      bindings: {
        ...input.settings.bindings,
        up: "KeyI",
        boost: "KeyB",
        recenter: "KeyP",
      },
    },
  };
  const takeoff = gooseTeaching(freshGooseTeaching, keyboard).cue;
  expect(takeoff?.title).toBe("IASD / 方向键起飞");
  expect(takeoff?.detail).toContain("按住 B 加速，更费体力");
  const airborne = { ...initial, airborne: true };
  expect(
    gooseTeaching(freshGooseTeaching, { ...keyboard, state: airborne }).cue
      ?.title,
  ).toBe("松开移动键，试试滑翔");
  const afterGlide = {
    ...keyboard,
    state: { ...airborne, releasedTicks: 12 },
  };
  const observing = gooseTeaching(freshGooseTeaching, afterGlide);
  expect(observing.cue?.id).toBe("orbit");
  expect(
    gooseTeaching(observing.progress, {
      ...afterGlide,
      cameraDragDistance: 36,
    }).cue?.title,
  ).toBe("按 P 回到跟随视角");
  expect(
    gooseTeaching(observing.progress, {
      ...afterGlide,
      cameraDragDistance: 36,
      seenReset: true,
    }).cue,
  ).toBeNull();
});

test("formation teaching records a completed V and follows actual release at the bend", () => {
  const straight = {
    ...input,
    state: { ...initial, airborne: true, segmentId: "S1" },
    leaderZ: 128,
  };
  expect(gooseTeaching(freshGooseTeaching, straight).cue?.title).toBe(
    "按住结阵键，排成 V 字",
  );
  const held = { ...straight, abilityHeld: true };
  expect(
    gooseTeaching(freshGooseTeaching, {
      ...held,
      state: { ...held.state, formation: 0.5 },
    }).cue?.id,
  ).toBe("forming");
  const formed = gooseTeaching(freshGooseTeaching, {
    ...held,
    state: { ...held.state, formation: 1 },
  });
  expect(formed.cue).toBeNull();
  expect(gooseTeaching(formed.progress, straight).cue).toBeNull();

  const bend = { ...held, leaderZ: 143 };
  expect(gooseTeaching(formed.progress, bend).cue?.detail).toContain(
    "松开结阵键",
  );
  expect(
    gooseTeaching(formed.progress, {
      ...bend,
      settings: { ...input.settings, toggle: true },
    }).cue?.detail,
  ).toContain("再点一次结阵键");
  const released = { ...bend, abilityHeld: false };
  expect(
    gooseTeaching(formed.progress, {
      ...released,
      state: { ...released.state, formation: 0.4 },
    }).cue?.title,
  ).toBe("队形正在舒展");
  expect(gooseTeaching(formed.progress, released).cue?.id).toBe("turn");
  expect(
    gooseTeaching(formed.progress, {
      ...released,
      leaderZ: gooseTurnLessonEnd,
      state: { ...released.state, formation: 0.25 },
    }).cue?.id,
  ).toBe("formation-releasing");
  const cleared = gooseTeaching(formed.progress, {
    ...released,
    leaderZ: gooseTurnLessonEnd,
  });
  expect(cleared.cue).toBeNull();
  expect(gooseTeaching(cleared.progress, bend).cue).toBeNull();
});

test("practice can teach formation once and skipped or paused lessons stay hidden", () => {
  const practice = loadLevel("playground");
  const state: GooseState = {
    ...initialState(practice, "journey"),
    airborne: true,
    releasedTicks: 12,
  };
  const practiceInput = {
    ...input,
    level: practice,
    state,
    cameraDragDistance: 36,
    seenReset: true,
  };
  expect(gooseTeaching(freshGooseTeaching, practiceInput).cue?.id).toBe(
    "formation",
  );
  expect(
    gooseTeaching(freshGooseTeaching, {
      ...practiceInput,
      state: { ...state, formation: 1 },
    }).cue,
  ).toBeNull();
  expect(
    gooseTeaching(freshGooseTeaching, { ...input, enabled: false }).cue,
  ).toBeNull();
  expect(
    gooseTeaching(freshGooseTeaching, {
      ...input,
      state: { ...input.state, phase: "paused" },
    }).cue,
  ).toBeNull();
});

test("the reed island provides a safe glide cue and confirms the actual release", () => {
  const clearing = {
    ...input,
    state: { ...initial, airborne: true },
    leaderZ: 71,
    cameraDragDistance: 36,
    seenReset: true,
  };
  const progress = { ...freshGooseTeaching, learnedGlide: true };
  expect(gooseTeaching(progress, clearing).cue?.title).toContain("宽水面滑翔");
  expect(
    gooseTeaching(progress, {
      ...clearing,
      state: { ...clearing.state, releasedTicks: 12 },
    }).cue?.title,
  ).toContain("正在滑翔");
  expect(gooseTeaching(progress, { ...clearing, leaderZ: 90 }).cue).toBeNull();
});

test("entering the second tailwind gives feedback even after the turn lesson ended", () => {
  const progress = {
    ...freshGooseTeaching,
    learnedFormation: true,
    passedTurnLesson: true,
  };
  const approach = {
    ...input,
    state: { ...initial, airborne: true, segmentId: "S1" },
    leaderZ: 176,
  };
  expect(gooseTeaching(progress, approach).cue).toBeNull();
  expect(
    gooseTeaching(progress, {
      ...approach,
      state: { ...approach.state, occupied: ["tailwind-second"] },
    }).cue?.id,
  ).toBe("second-tailwind");
});
