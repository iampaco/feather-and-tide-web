import { expect, test } from "vitest";
import { NEUTRAL_INPUT, type WhaleState } from "../../src/core/game";
import { distance } from "../../src/core/math";
import { contains } from "../../src/levels/geometry";
import { dredgingPassage } from "../../src/levels/whale-dredging";
import { tickWorld } from "../../src/simulation/world";
import { surfaced } from "../../src/simulation/world-rules";
import { aim } from "../fixtures/flight";
import { podAt, podLeader, whaleLevel } from "../fixtures/whale";

const hazardIds = new Set(
  whaleLevel.zones.filter(({ kind }) => kind === "hazard").map(({ id }) => id),
);

test.each(["surface", "clear"] as const)(
  "W3 dredging %s route brings the whole pod to the clear-water shelter",
  (route) => {
    const passage = dredgingPassage(whaleLevel);
    if (!passage) throw new Error("Missing dredging passage");
    const waypoints = [...passage[route], passage.regroup].map(
      ({ pos }) => pos,
    );
    let reachedWaypoint = 0;
    let didSubmerge = false;
    let startDive: number | undefined;
    let state: WhaleState = {
      ...podAt({ x: 65, z: 1150 }),
      segmentId: "W3",
      route: "shipping",
    };
    for (let tick = 0; tick < 2_100; tick++) {
      if (!waypoints[reachedWaypoint]) break;
      const lead = podLeader(state);
      didSubmerge ||= lead.dive.layer !== "surface";
      const target = waypoints[reachedWaypoint];
      if (!target) break;
      if (distance(lead.pos, target) < 2.9) reachedWaypoint++;
      const next = waypoints[reachedWaypoint] ?? target;
      if (route === "clear" && lead.pos.z > 1192) startDive ??= tick;
      const ability = startDive !== undefined && tick - startDive < 124;
      const result = tickWorld(
        state,
        aim(lead.pos, next, 0.73, ability),
        whaleLevel,
      );
      expect(
        result.events.some(
          (event) =>
            event.type === "zone" && event.entered && hazardIds.has(event.id),
        ),
      ).toBe(false);
      state = result.state;
    }

    for (let tick = 0; tick < 240; tick++)
      state = tickWorld(state, NEUTRAL_INPUT, whaleLevel).state;

    expect(reachedWaypoint).toBe(waypoints.length);
    expect(state.phase).toBe("playing");
    expect(state.actors).toHaveLength(6);
    expect(
      state.actors.every(
        (actor) => actor.status === "following" && surfaced(actor),
      ),
    ).toBe(true);
    expect(
      state.actors.every(({ pos }) => contains(passage.rest.points, pos)),
    ).toBe(true);
    expect(didSubmerge).toBe(route === "clear");
  },
);
