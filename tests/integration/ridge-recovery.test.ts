import { expect, test } from "vitest";
import { gooseHazardCue } from "../../src/app/flight-guidance";
import { GOOSE } from "../../src/simulation/goose";
import { leaderOf } from "../../src/simulation/world";
import {
  flyCourse,
  migration,
  wideTailwindWaypoints,
} from "../fixtures/flight";

test("a ridge stall holds stamina until the player backs into open water", () => {
  const { runtime } = flyCourse(
    migration,
    "journey",
    wideTailwindWaypoints(),
    (state) =>
      leaderOf(state).pos.z >= 206 && Math.abs(leaderOf(state).pos.x) < 4,
  );
  const step = (x: number, z: number) => {
    runtime.dispatch({
      type: "input",
      input: { move: { x, z }, ability: false },
    });
    runtime.step();
  };
  while (!runtime.current.ridgeRecovery && runtime.current.tick < 2800)
    step(0, 0.84);
  const blocked = runtime.current;
  expect(blocked).toMatchObject({
    phase: "playing",
    segmentId: "S2",
    route: null,
    ridgeRecovery: "blocked",
  });
  expect(gooseHazardCue(blocked, migration)?.title).toBe("分水岭挡住前进");
  const { pos } = leaderOf(blocked);
  for (let i = 0; i < 600; i++) step(0, 0.84);
  expect(runtime.current.energy).toBe(blocked.energy);
  expect(leaderOf(runtime.current).pos).toEqual(pos);

  let clearing = false;
  const slowDiagonal = 0.12 / Math.SQRT2;
  for (let i = 0; i < GOOSE.coastTicks * 4; i++) {
    step(-slowDiagonal, -slowDiagonal);
    if (runtime.current.ridgeRecovery !== "clearing") continue;
    clearing = true;
    expect(gooseHazardCue(runtime.current, migration)?.detail).toContain(
      "斜向来路",
    );
  }
  expect(clearing).toBe(true);
  expect(leaderOf(runtime.current).pos.z).toBeLessThan(pos.z - 4);
  expect(runtime.current.energy).toBeLessThan(blocked.energy);
  expect(runtime.current.ridgeRecovery).toBeUndefined();
  expect(runtime.current.route).toBeNull();
});
