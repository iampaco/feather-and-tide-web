import { expect, test } from "vitest";
import {
  gooseCrosswindApproach,
  gooseHazardCue,
  gooseLandingApproach,
  gooseRouteCue,
  gooseSupplyCue,
  gooseWindfarmOptions,
} from "../../src/app/flight-guidance";
import type { GooseState } from "../../src/core/game";
import { GOOSE } from "../../src/simulation/goose";
import { initialState, leaderOf } from "../../src/simulation/world";
import { migration } from "../fixtures/flight";

function parked(
  segmentId: string,
  x: number,
  z: number,
  occupied: readonly string[] = [],
): GooseState {
  const state = initialState(migration, "journey");
  const from = leaderOf(state).pos;
  return {
    ...state,
    segmentId,
    occupied,
    airborne: true,
    energy: 0.52,
    actors: state.actors.map((actor) => ({
      ...actor,
      pos: { x: actor.pos.x - from.x + x, z: actor.pos.z - from.z + z },
      heading: 0,
      speed: GOOSE.cruise,
    })),
  };
}

test("S2 predicts collision at the ridge and leaves the clear sides open", () => {
  const approaching = parked("S2", 0, 255, ["ridge-warning"]);
  expect(gooseHazardCue(approaching, migration)).toMatchObject({
    threat: "ridge",
    title: "前方分水岭 · 沿两侧航标绕行",
  });
  expect(gooseHazardCue(parked("S2", -46, 255), migration)).toBeUndefined();
  expect(
    gooseHazardCue({ ...approaching, occupied: ["ridge-wall"] }, migration),
  ).toMatchObject({
    threat: "ridge",
    title: "分水岭边界 · 沿两侧航标绕行",
  });
});

test("S2 wind and position alone do not confirm a route", () => {
  const state = parked("S2", -30, 270, ["pass-wind"]);
  expect(gooseRouteCue(state, migration)?.title).toBe("沿山口航标飞行");
  expect(gooseRouteCue({ ...state, route: "mountain" }, migration)?.title).toBe(
    "已进入短山口",
  );
  expect(
    gooseRouteCue(
      {
        ...state,
        route: "lake",
        supply: { ...state.supply, "lake-supply": 0 },
      },
      migration,
    ),
  ).toEqual({ title: "已进入长湖路", detail: "沿湖面继续飞行。" });
});

test("S3 previews the real tail and acknowledges a prepared approach and regroup", () => {
  const valley = parked("S3", 1, 410);
  const stretched: GooseState = {
    ...valley,
    actors: valley.actors.map((actor) =>
      actor.id === "goose-11" ? { ...actor, pos: { x: 1, z: 378 } } : actor,
    ),
  };
  expect(gooseCrosswindApproach(stretched, migration)).toMatchObject({
    title: "前方侧风 · 放慢留意队尾",
    detail: expect.stringContaining("队尾已拉长"),
    tail: { id: "goose-11", pos: { x: 1, z: 378 } },
  });
  const prepared = {
    ...valley,
    actors: valley.actors.map((actor) => ({ ...actor, speed: 4 })),
  };
  expect(gooseCrosswindApproach(prepared, migration)?.title).toBe(
    "前方侧风 · 队尾已靠拢",
  );
  const regrouped = { ...parked("S3", 0, 485), triggered: ["crosswind"] };
  expect(gooseCrosswindApproach(regrouped, migration)?.title).toBe(
    "队伍已重新靠拢",
  );
  expect(
    gooseCrosswindApproach(
      {
        ...regrouped,
        actors: regrouped.actors.map((actor) =>
          actor.id === "goose-11" ? { ...actor, status: "rejoining" } : actor,
        ),
      },
      migration,
    ),
  ).toBeUndefined();
});

test("S4 shows the approach choices ahead of the warning and respects the rotor boundary", () => {
  const before = parked("S4", -8, 506);
  expect(gooseWindfarmOptions(before, migration, undefined)).toMatchObject({
    direct: { mark: { id: "outer-mark" } },
    bay: { mark: { id: "reserve-entry" }, stocked: true },
    cue: { detail: expect.stringContaining("转入浅湾可补给") },
  });
  const exhausted = {
    ...before,
    supply: { ...before.supply, "reserve-supply": 0 },
  };
  expect(
    gooseWindfarmOptions(exhausted, migration, undefined).bay,
  ).toMatchObject({
    label: "浅湾 · 可休整",
    stocked: false,
  });
  const east = gooseWindfarmOptions(
    parked("S4", 46, 577, ["wind-warning"]),
    migration,
    undefined,
  );
  expect(east.direct?.mark.id).toBe("wind-east-exit");
  expect(east.bay).toBeUndefined();
});

test("S4 warning reports depleted reserve supply accurately", () => {
  const state = parked("S4", 0, 530, ["wind-warning"]);
  expect(gooseHazardCue(state, migration)?.detail).toBe("向浅湾转入可补给");
  expect(
    gooseHazardCue(
      { ...state, supply: { ...state.supply, "reserve-supply": 0 } },
      migration,
    ),
  ).toMatchObject({
    threat: "sweep",
    detail: "浅湾补给已用完，可休整",
  });
});

test("S4 sanctuary can restore stamina while the active supply waits for quorum", () => {
  const state = parked("S4", -87, 565, ["wind-warning", "reserve"]);
  expect(gooseSupplyCue(state, migration, 82, true)).toMatchObject({
    title: "放慢飞行，等队伍进入补给区",
    recovering: true,
  });
  expect(
    gooseSupplyCue(
      { ...state, occupied: [...state.occupied, "reserve-supply"] },
      migration,
      82,
      true,
    ),
  ).toMatchObject({ title: "正在补给 · 保持队伍靠拢", recovering: true });
  expect(
    gooseSupplyCue(
      { ...state, supply: { ...state.supply, "reserve-supply": 0 } },
      migration,
      82,
      true,
    ),
  ).toMatchObject({ title: "补给已用完，可在这里休整", recovering: true });
});

test("S4 low stamina does not guide the flock through a rotor boundary to the reserve", () => {
  const state = {
    ...parked("S4", 44, 584, ["wind-warning"]),
    energy: 0.1,
  };
  expect(gooseSupplyCue(state, migration, 160, true).target?.mark.id).not.toBe(
    "reserve-entry",
  );
  expect(gooseSupplyCue(state, migration, 160, true).target?.mark.id).not.toBe(
    "wetland-mark",
  );
});

test("S5 warning removes the promise of supply when the gallery stock is empty", () => {
  const state = parked("S5", -48, 684, ["gallery-warning"]);
  expect(gooseHazardCue(state, migration)?.detail).toContain("内廊浅湾可补给");
  expect(
    gooseHazardCue(
      { ...state, supply: { ...state.supply, "gallery-supply": 0 } },
      migration,
    )?.detail,
  ).toContain("内廊补给已用完");
});

test("S6 advises the leader based on the real flock before the landing boundary", () => {
  const goal = migration.zones.find(({ kind }) => kind === "goal");
  const compact = parked("S6", 0, 781);
  expect(gooseLandingApproach(compact, migration, goal)?.title).toBe(
    "队伍齐整 · 飞入芦苇湾",
  );
  const spread: GooseState = {
    ...compact,
    actors: compact.actors.map((actor) =>
      actor.id === "goose-7"
        ? { ...actor, pos: { x: 4, z: 749 }, status: "loose" }
        : actor,
    ),
  };
  expect(gooseLandingApproach(spread, migration, goal)).toMatchObject({
    title: "放慢飞行，先让雁群靠拢",
    tail: { id: "goose-7" },
  });
  const slowing = {
    ...spread,
    actors: spread.actors.map((actor) => ({ ...actor, speed: 4 })),
  };
  expect(gooseLandingApproach(slowing, migration, goal)?.title).toBe(
    "沿水面缓飞，等队尾跟上",
  );
  expect(
    gooseLandingApproach(parked("S6", 0, 802), migration, goal),
  ).toBeUndefined();
});
