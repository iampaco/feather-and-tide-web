import { Vector3 } from "three";
import { expect, test } from "vitest";
import { angleDelta } from "../../src/core/math";
import { GameRuntime } from "../../src/core/runtime";
import { DEFAULT_SETTINGS } from "../../src/input/input";
import { CameraDirector } from "../../src/rendering/camera";
import { buildLandscape } from "../../src/rendering/landscape";
import { clearOrbitPitch } from "../../src/rendering/orbit-clearance";
import { leaderOf } from "../../src/simulation/world";
import { migration, playground } from "../fixtures/flight";

test.each(["default", "explored", "reduced"] as const)(
  "authored reindeer landing angles respect the %s view",
  (view) => {
    const camera = new CameraDirector(42);
    const settings = { ...DEFAULT_SETTINGS, reduced: view === "reduced" };
    const target = { x: 0, z: 0 };
    if (view === "explored") camera.drag(-140, 0, settings);
    camera.update(target, 1, 2, 1, settings, false, 0);
    const initialYaw = camera.viewAngles().yaw;
    expect(camera.viewAngles().pitch).toBeCloseTo(42);
    const actors = [
      { ...target, y: 0 },
      { x: 1, z: -2, y: 0 },
    ];
    camera.update(target, 1, 2, 1, settings, false, {
      progress: 1,
      birds: actors,
      framing: {
        span: 34,
        padding: 5.5,
        lookAhead: 1.5,
        defaultYawOffsetDegrees: 27,
        defaultPitchDegrees: 28,
      },
    });
    expect(camera.viewAngles().yaw).toBeCloseTo(
      initialYaw + (view === "default" ? 27 : 0),
    );
    expect(camera.viewAngles().pitch).toBeCloseTo(view === "default" ? 28 : 41);
    for (const actor of actors) {
      const point = new Vector3(actor.x, actor.y, actor.z).project(
        camera.camera,
      );
      expect(Math.abs(point.x)).toBeLessThan(0.86);
      expect(Math.abs(point.y)).toBeLessThan(0.78);
    }
    camera.reset(true);
    expect(camera.viewAngles()).toMatchObject({ pitch: 42, mode: "Follow" });
  },
);

test("horizontal drag crosses the rear seam in either direction without reversing", () => {
  const camera = new CameraDirector();
  const yaw = () => Math.atan2(camera.basis().up.x, camera.basis().up.z);
  const update = (delta: number) =>
    camera.update({ x: 0, z: 0 }, 4, 2, delta, DEFAULT_SETTINGS, false, 0);
  for (const direction of [1, -1]) {
    let total = 0;
    for (let step = 0; step < 56; step++) {
      const before = yaw();
      camera.drag(-45 * direction, 0, DEFAULT_SETTINGS);
      update(0.08);
      const traveled = angleDelta(before, yaw()) * direction;
      expect(traveled).toBeGreaterThan(0);
      expect(traveled).toBeLessThan(0.3);
      total += traveled;
    }
    expect(total).toBeGreaterThan(4 * Math.PI);
  }
});

test("reset takes the short route from the currently visible angle", () => {
  const camera = new CameraDirector();
  const yaw = () => Math.atan2(camera.basis().up.x, camera.basis().up.z);
  const update = (delta: number) =>
    camera.update({ x: 0, z: 0 }, 4, 2, delta, DEFAULT_SETTINGS, false, 0);
  camera.drag(-780, 800, DEFAULT_SETTINGS);
  update(2);
  expect(yaw()).toBeLessThan(-1.5);
  expect(Math.hypot(camera.basis().up.x, camera.basis().up.z)).toBeCloseTo(
    1 / Math.sin((65 * Math.PI) / 180),
  );
  camera.drag(-1000, 0, DEFAULT_SETTINGS);
  const before = yaw();
  camera.reset();
  update(0.015);
  expect(yaw()).toBeGreaterThan(before);
  expect(yaw()).toBeLessThan(0);
  update(1);
  expect(yaw()).toBeCloseTo(0, 4);
});

test.each([false, true])(
  "V2-06 orbit and smooth reset preserve fixed world input, wide=%s",
  (wideMouseOrbit) => {
    const observed = new GameRuntime(playground, "journey");
    const control = new GameRuntime(playground, "journey");
    const camera = new CameraDirector();
    const settings = { ...DEFAULT_SETTINGS, wideMouseOrbit };
    const command = {
      type: "input" as const,
      input: { move: { x: 0.5, z: 0.6 }, ability: false },
    };
    observed.dispatch(command);
    control.dispatch(command);
    for (let i = 0; i < 240; i++) {
      if (i === 24) camera.drag(160, 164, settings, "mouse");
      if (i === 156) {
        expect(camera.mode).toBe("Explore");
        expect(Math.abs(camera.basis().right.z)).toBeGreaterThan(0.5);
        camera.reset();
      }
      observed.step();
      control.step();
      camera.update(
        leaderOf(observed.current).pos,
        4,
        2,
        1 / 60,
        settings,
        false,
        0,
      );
    }
    expect(camera.mode).toBe("Follow");
    expect(camera.basis().right.z).toBeCloseTo(0, 4);
    expect(observed.current).toEqual(control.current);
  },
);

test("wide orbit centers the leader and classic pointer types keep their pitch limits", () => {
  const camera = new CameraDirector();
  const leader = new Vector3(14, 4, 30);
  const settings = { ...DEFAULT_SETTINGS, wideMouseOrbit: true, reduced: true };
  const update = () =>
    camera.update(leader, leader.y, 2, 1 / 60, settings, false, 0);
  camera.drag(0, -300, settings, "mouse");
  update();
  expect(camera.viewAngles().profile).toBe("wide");
  expect(camera.viewAngles().pitch).toBeCloseTo(20);
  expect(leader.clone().project(camera.camera).y).toBeCloseTo(0);
  camera.drag(0, 300, settings, "mouse");
  update();
  expect(camera.viewAngles().profile).toBe("wide");
  expect(camera.viewAngles().pitch).toBeCloseTo(80);
  camera.drag(0, 300, settings, "touch");
  update();
  expect(camera.viewAngles().profile).toBe("classic");
  expect(camera.viewAngles().pitch).toBeCloseTo(65);
  camera.reset(true);
  camera.drag(0, -300, { ...settings, vertical: false }, "mouse");
  update();
  expect(camera.viewAngles()).toMatchObject({ pitch: 49, mode: "Follow" });
});

test("the gallery raises the view temporarily, and turbine bounds use world positions", () => {
  const camera = new CameraDirector();
  const terrain = buildLandscape(migration, true).orbitClearance;
  if (!terrain) throw new Error("Missing camera clearance geometry");
  const tower = migration.landmarks.find(({ kind }) => kind === "turbine")?.pos;
  expect(
    terrain.obstacles.some(
      (box) => tower && box.containsPoint(new Vector3(tower.x, 4, tower.z)),
    ),
  ).toBe(true);
  expect(
    terrain.obstacles.some((box) => box.containsPoint(new Vector3(0, 4, 0))),
  ).toBe(false);

  const settings = { ...DEFAULT_SETTINGS, wideMouseOrbit: true, reduced: true };
  camera.drag(-Math.PI / 0.006, -300, settings, "mouse");
  camera.update(
    { x: -84, z: 746 },
    4,
    21 / 9,
    1 / 60,
    settings,
    false,
    0,
    terrain,
  );
  const lifted = camera.viewAngles();
  expect(lifted.requestedPitch).toBe(20);
  expect(lifted.pitch).toBeGreaterThan(25);
  const eased = { ...settings, reduced: false };
  camera.update({ x: 20, z: 746 }, 4, 21 / 9, 1 / 60, eased, false, 0, terrain);
  expect(camera.viewAngles().pitch).toBeGreaterThan(20);
  expect(camera.viewAngles().pitch).toBeLessThan(lifted.pitch);
  camera.update({ x: 20, z: 746 }, 4, 21 / 9, 1, eased, false, 0, terrain);
  expect(camera.viewAngles().pitch).toBeCloseTo(20, 2);
});

test("wide orbit raises the near plane above a ridge between the viewport corners", () => {
  const requested = (20 * Math.PI) / 180;
  const leader = new Vector3(0, 4, 0);
  const pitch = clearOrbitPitch(
    requested,
    (80 * Math.PI) / 180,
    0,
    100,
    leader,
    leader,
    29,
    (29 * 21) / 9,
    0.1,
    {
      height: (x, z) => Math.max(0, 13 - Math.hypot(x - 50, z + 104) * 2),
      obstacles: [],
    },
  );
  expect(pitch).toBeGreaterThan(requested);
  expect(pitch).toBeLessThan((23 * Math.PI) / 180);
});

test("S07 a checkpoint camera reset immediately restores its default framing", () => {
  const camera = new CameraDirector();
  const target = { x: 0, z: 210 };
  camera.update(target, 4, 2, 1, DEFAULT_SETTINGS, true, 0);
  expect(camera.camera.top).toBeGreaterThan(34);
  camera.reset(true);
  camera.update(target, 4, 2, 0, DEFAULT_SETTINGS, false, 0);
  expect(camera.camera.top).toBe(29);
  expect(camera.mode).toBe("Follow");
});

test("S6 landing gently pulls back from Follow and keeps the full flock in frame", () => {
  const camera = new CameraDirector();
  const leader = new Vector3(0, 4, 825);
  const birds = [
    leader,
    ...Array.from(
      { length: 11 },
      (_, index) =>
        new Vector3(
          index % 2 === 0 ? 5.6 : -5.6,
          4,
          821 - Math.floor(index / 2) * 3.2,
        ),
    ),
  ];
  const aspect = 852 / 393;
  camera.update(leader, leader.y, aspect, 1, DEFAULT_SETTINGS, false, 0);
  const start = camera.camera.top;
  expect(start).toBeCloseTo(29);
  let last = start;
  for (const progress of [0, 0.24, 0.52, 0.78, 1]) {
    camera.update(leader, leader.y, aspect, 1 / 60, DEFAULT_SETTINGS, false, {
      progress,
      birds,
    });
    expect(camera.mode).toBe("Cinematic");
    expect(camera.camera.top).toBeGreaterThanOrEqual(last);
    last = camera.camera.top;
    for (const bird of birds) {
      const screen = bird.clone().project(camera.camera);
      expect(Math.abs(screen.x)).toBeLessThan(0.84);
      expect(Math.abs(screen.y)).toBeLessThan(0.72);
    }
  }
  expect(camera.camera.top).toBeCloseTo(36.5);
});

test.each([-300, 300])(
  "S6 enters from a wide mouse view (%s) and fits all birds",
  (drag) => {
    const camera = new CameraDirector();
    const settings = { ...DEFAULT_SETTINGS, wideMouseOrbit: true };
    const leader = new Vector3(0, 4, 825);
    const birds = [
      leader,
      ...Array.from(
        { length: 11 },
        (_, i) => new Vector3(i % 2 ? 5 : -5, 4, 822 - i * 2),
      ),
    ];
    const aspect = 21 / 9;
    camera.drag(-524, drag, settings, "mouse");
    camera.update(leader, leader.y, aspect, 2, settings, false, 0);
    const entry = camera.camera.position.clone();
    camera.update(leader, leader.y, aspect, 1 / 60, settings, false, {
      progress: 0,
      birds,
    });
    expect(camera.camera.position.distanceTo(entry)).toBeCloseTo(0);
    for (const progress of [0, 0.2, 0.5, 1]) {
      camera.update(leader, leader.y, aspect, 1 / 60, settings, false, {
        progress,
        birds,
      });
      for (const bird of birds) {
        const point = bird.clone().project(camera.camera);
        expect(Math.abs(point.x)).toBeLessThan(0.84);
        expect(Math.abs(point.y)).toBeLessThan(0.72);
      }
    }
    expect(camera.viewAngles()).toMatchObject({ mode: "Cinematic", pitch: 41 });
  },
);

test("S6 reduced motion frames a wide flock in a steady view after orbit", () => {
  const camera = new CameraDirector();
  const settings = { ...DEFAULT_SETTINGS, reduced: true };
  const leader = new Vector3(-34, 4, 843);
  const birds = [
    leader,
    new Vector3(-55, 1.5, 839),
    new Vector3(43, 3.8, 817),
    new Vector3(55, 4, 804),
  ];
  const aspect = 16 / 9;
  camera.drag(-230, -20, settings);
  camera.update(leader, leader.y, aspect, 0.03, settings, false, 0);
  const basis = camera.basis();
  camera.update(leader, leader.y, aspect, 0.03, settings, false, {
    progress: 0,
    birds,
  });
  const position = camera.camera.position.clone();
  const span = camera.camera.top;
  for (const bird of birds) {
    const screen = bird.clone().project(camera.camera);
    expect(Math.abs(screen.x)).toBeLessThan(0.84);
    expect(Math.abs(screen.y)).toBeLessThan(0.72);
  }
  camera.update(leader, leader.y, aspect, 0.24, settings, false, {
    progress: 1,
    birds,
  });
  expect(camera.camera.position).toEqual(position);
  expect(camera.camera.top).toBe(span);
  expect(camera.basis().right).toEqual(basis.right);
});
