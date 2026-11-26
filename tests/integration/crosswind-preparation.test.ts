import { expect, test } from "vitest";
import {
  gooseCrosswindApproach,
  gooseCrosswindPickup,
} from "../../src/app/flight-guidance";
import { GameRuntime } from "../../src/core/runtime";
import { distance } from "../../src/core/math";
import { GOOSE } from "../../src/simulation/goose";
import { leaderOf } from "../../src/simulation/world";
import { aim, migration, trip } from "../fixtures/flight";

test("slowing or forming before the fixed S3 drop shortens the distance to the same pickup circle", () => {
  const { runtime: approach } = trip("journey", "mountain", 401);
  const snapshot = { ...approach.checkpoint, state: approach.current };

  function cross(power: number, ability: boolean) {
    const runtime = new GameRuntime(migration, "journey", snapshot);
    let preview: ReturnType<typeof gooseCrosswindApproach>;
    while (runtime.current.tick < snapshot.state.tick + 900) {
      const leader = leaderOf(runtime.current);
      if (leader.pos.z >= 424)
        preview = gooseCrosswindApproach(runtime.current, migration);
      runtime.dispatch({
        type: "input",
        input: aim(leader.pos, { x: 0, z: 455 }, power, ability),
      });
      const drop = runtime.step().find(({ type }) => type === "strayed");
      if (drop?.type !== "strayed") continue;
      expect(drop.id).toBe("goose-11");
      const tail = runtime.current.actors.find(({ id }) => id === drop.id);
      if (!tail) throw new Error("Missing tail goose");
      expect(tail.rescueTicks).toBe(GOOSE.rescueTicks);
      expect(tail.rescueProgress).toBe(0);
      expect(
        gooseCrosswindPickup(
          runtime.previous,
          runtime.current,
          migration,
          "goose-10",
        ),
      ).toBeUndefined();
      const pickup = gooseCrosswindPickup(
        runtime.previous,
        runtime.current,
        migration,
        drop.id,
      );
      const actualDistance =
        distance(leaderOf(runtime.current).pos, tail.pos) - GOOSE.rescueRadius;
      expect(pickup).toEqual({
        actorId: drop.id,
        distanceToCircle: actualDistance,
      });
      expect(preview?.tail?.id).toBe(drop.id);
      expect(preview?.detail).toMatch(/间距|折返/);
      runtime.step();
      expect(
        gooseCrosswindPickup(
          runtime.previous,
          runtime.current,
          migration,
          drop.id,
        ),
      ).toBeUndefined();
      return actualDistance;
    }
    throw new Error("S3 did not trigger the fixed rescue");
  }

  const cruise = cross(0.84, false);
  expect(cross(0.12, false)).toBeLessThan(cruise - 4);
  expect(cross(0.84, true)).toBeLessThan(cruise - 4);
});
