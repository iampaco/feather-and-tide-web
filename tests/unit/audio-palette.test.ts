import { expect, test } from "vitest";
import { flightMix } from "../../src/audio/palette";
import { initialState } from "../../src/simulation/world";
import { migration } from "../fixtures/flight";
import { podAt, whaleLevel } from "../fixtures/whale";

const start = initialState(migration, "journey");
const flight = { ...start, airborne: true };

test("A01 the score progresses from silence to flight and landing", () => {
  const dawn = flightMix(start);
  expect(dawn.layer).toBe("ambient");
  expect(dawn.music).toBe(0);
  expect(flightMix(flight).layer).toBe("journey");
  const warned = { ...flight, segmentId: "S4", occupied: ["wind-warning"] };
  expect(flightMix(warned).layer).toBe("focus");
  expect(flightMix({ ...warned, occupied: ["sweep"] }).layer).toBe("tension");
  const reserve = flightMix({
    ...warned,
    occupied: ["wind-warning", "sweep", "reserve"],
  });
  expect(reserve.layer).toBe("release");
  expect(flightMix({ ...flight, segmentId: "S5" }).layer).toBe("journey");
  expect(flightMix({ ...flight, phase: "landing" }).layer).toBe("release");
});

test("A01 the score responds to the route and rescue state", () => {
  const ridge = flightMix({
    ...flight,
    segmentId: "S2",
    route: "mountain",
    occupied: ["pass-wind"],
  });
  const lake = flightMix({ ...flight, segmentId: "S2", route: "lake" });
  expect(ridge.layer).toBe("tension");
  expect(ridge.lake).toBe(false);
  expect(lake.layer).toBe("journey");
  expect(lake.lake).toBe(true);
  const rescue = flightMix({
    ...flight,
    segmentId: "S3",
    actors: flight.actors.map((actor) =>
      actor.id === "goose-11" ? { ...actor, status: "strayed" } : actor,
    ),
  });
  expect(rescue.layer).toBe("care");
  expect(rescue.music).toBeLessThan(flightMix(flight).music);
});

test("WH-A10 the whale score softens in depth and during rescue, then releases in still water", () => {
  const whale = podAt({ x: 0, z: 390 });
  const cruise = flightMix(whale, whaleLevel);
  const deep = {
    ...whale,
    actors: whale.actors.map((actor) => ({
      ...actor,
      dive: { ...actor.dive, layer: "deep" as const, depth: 2 },
    })),
  };
  expect(flightMix(deep, whaleLevel).music).toBeLessThan(cruise.music);
  const rescue = {
    ...whale,
    occupied: ["net-rest", "drift-net"],
    actors: whale.actors.map((actor, index) =>
      index === 5 ? { ...actor, status: "strayed" as const } : actor,
    ),
  };
  expect(flightMix(rescue, whaleLevel).layer).toBe("care");
  const rest = flightMix({ ...whale, occupied: ["net-rest"] }, whaleLevel);
  expect(rest.layer).toBe("release");
  expect(rest.music).toBeGreaterThan(cruise.music);
  expect(flightMix({ ...whale, phase: "landing" }, whaleLevel).layer).toBe(
    "release",
  );
});
