import { describe, expect, it } from "vitest";
import {
  placeGooseMarkers,
  type GooseMarkerKind,
} from "../../src/app/goose-marker-layout";

function marker(kind: GooseMarkerKind, x: number, y: number) {
  return { kind, x, y, width: 96, height: 22, edge: true, angle: 20 };
}

describe("goose marker placement", () => {
  it("keeps a rescue and safe route clear of the stacked HUD and demotes an overlapping optional bay", () => {
    const area = { width: 536, height: 296 };
    const obstacles = [
      { x: 125, y: 0, width: 286, height: 169 },
      { x: 0, y: 206, width: 90, height: 90 },
      { x: 484, y: 0, width: 52, height: 52 },
    ];
    const placements = placeGooseMarkers(
      [
        marker("supply", 445, 194),
        marker("route", 445, 194),
        marker("rescue", 260, 175),
      ],
      area,
      obstacles,
    );

    expect(placements[0]).toBeUndefined();
    expect(placements[1]).toEqual({ x: 397, y: 175, mode: "text", angle: 20 });
    expect(placements[2]).toMatchObject({ mode: "text" });
    expect(placements[2]?.y).toBeGreaterThanOrEqual(175);
  });

  it("uses an aligned compact arrow when the focused route label cannot fit", () => {
    const placements = placeGooseMarkers(
      [marker("route", 80, 90)],
      { width: 90, height: 150 },
      [{ x: 66, y: 70, width: 24, height: 40 }],
    );
    expect(placements[0]).toMatchObject({ mode: "arrow", angle: 20 });
    expect(placements[0]?.y).toBeLessThanOrEqual(70 - 24 - 6);
  });

  it("keeps a named recovery destination ahead of a decorative marker at the same position", () => {
    const placements = placeGooseMarkers(
      [
        marker("landmark", 220, 120),
        { ...marker("supply", 220, 120), primary: true },
      ],
      { width: 536, height: 296 },
      [],
    );

    expect(placements[0]).toBeUndefined();
    expect(placements[1]).toMatchObject({ mode: "text", x: 172, y: 98 });
  });

  it("keeps the named route enough room to clear a status panel in landscape", () => {
    const placements = placeGooseMarkers(
      [
        marker("route", 245, 174),
        { ...marker("route", 245, 98), primary: true },
      ],
      { width: 568, height: 320 },
      [{ x: 137, y: 70, width: 296, height: 88 }],
    );
    expect(placements[1]).toMatchObject({ mode: "text" });
    expect(placements[0]).not.toEqual(placements[1]);
  });
});
