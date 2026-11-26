import {
  BoxGeometry,
  BufferGeometry,
  Color,
  CylinderGeometry,
  DoubleSide,
  ExtrudeGeometry,
  Float32BufferAttribute,
  Group,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Shape,
  SphereGeometry,
} from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { STEP_SEC } from "../core/clock";
import type { Vec2 } from "../core/math";
import type { InputSettings } from "../input/input";
import type { WhaleLevel } from "../levels/schema";

const SLOW_SPEED = 1.56;
const CRUISE_SPEED = 4.4;
const RUN_IN = 14;
const TURN_RADIUS = 12;
const BOAT_CLEARANCE = 8;

export const watchingBoundaryLandmarks = [
  "watching-buoy-near",
  "watching-buoy-far",
] as const;

interface VesselPose {
  readonly x: number;
  readonly z: number;
  readonly heading: number;
  readonly speed: number;
}

function rampDistance(seconds: number, speed: number, target: number): number {
  const duration = (2 * RUN_IN) / (speed + target);
  return seconds * (speed + ((target - speed) * seconds) / (2 * duration));
}

export function watchingVesselAt(
  tick: number,
  coast: number,
  near: number,
  far: number,
): VesselPose {
  const x = coast + BOAT_CLEARANCE;
  const rampTime = (2 * RUN_IN) / (CRUISE_SPEED + SLOW_SPEED);
  const slowTime = (far - near) / SLOW_SPEED;
  const turnTime = (Math.PI * TURN_RADIUS) / CRUISE_SPEED;
  const returnTime = (far - near + 2 * RUN_IN) / CRUISE_SPEED;
  const cycle = 2 * (rampTime + turnTime) + slowTime + returnTime;
  let seconds = (tick * STEP_SEC) % cycle;
  if (seconds < rampTime)
    return {
      x,
      z: near - RUN_IN + rampDistance(seconds, CRUISE_SPEED, SLOW_SPEED),
      heading: 0,
      speed: MathUtils.lerp(CRUISE_SPEED, SLOW_SPEED, seconds / rampTime),
    };
  seconds -= rampTime;
  if (seconds < slowTime)
    return { x, z: near + seconds * SLOW_SPEED, heading: 0, speed: SLOW_SPEED };
  seconds -= slowTime;
  if (seconds < rampTime)
    return {
      x,
      z: far + rampDistance(seconds, SLOW_SPEED, CRUISE_SPEED),
      heading: 0,
      speed: MathUtils.lerp(SLOW_SPEED, CRUISE_SPEED, seconds / rampTime),
    };
  seconds -= rampTime;
  if (seconds < turnTime) {
    const heading = (seconds / turnTime) * Math.PI;
    return {
      x: x + TURN_RADIUS * (1 - Math.cos(heading)),
      z: far + RUN_IN + TURN_RADIUS * Math.sin(heading),
      heading,
      speed: CRUISE_SPEED,
    };
  }
  seconds -= turnTime;
  if (seconds < returnTime)
    return {
      x: x + 2 * TURN_RADIUS,
      z: far + RUN_IN - seconds * CRUISE_SPEED,
      heading: Math.PI,
      speed: CRUISE_SPEED,
    };
  const turn = ((seconds - returnTime) / turnTime) * Math.PI;
  return {
    x: x + TURN_RADIUS * (1 + Math.cos(turn)),
    z: near - RUN_IN - TURN_RADIUS * Math.sin(turn),
    heading: Math.PI + turn,
    speed: CRUISE_SPEED,
  };
}

type PaintPiece = readonly [BufferGeometry, string];

function painted(parts: readonly PaintPiece[]): Mesh {
  const colored = parts.map(([geometry, pigment]) => {
    const paint = new Color(pigment);
    const surface = geometry.index ? geometry.toNonIndexed() : geometry;
    if (surface !== geometry) geometry.dispose();
    const colors = new Float32Array(surface.getAttribute("position").count * 3);
    for (let offset = 0; offset < colors.length; offset += 3)
      paint.toArray(colors, offset);
    surface.setAttribute("color", new Float32BufferAttribute(colors, 3));
    return surface;
  });
  const geometry = mergeGeometries(colored);
  for (const part of colored) part.dispose();
  if (!geometry) throw new Error("Unable to combine whale-watching scenery");
  return new Mesh(
    geometry,
    new MeshStandardMaterial({ vertexColors: true, roughness: 0.87 }),
  );
}

function hullPart(
  width: number,
  length: number,
  bottom: number,
  height: number,
) {
  const shape = new Shape();
  shape.moveTo(-0.93 * width, 0.89 * length);
  shape.lineTo(0.93 * width, 0.89 * length);
  shape.lineTo(width, -0.28 * length);
  shape.lineTo(0.69 * width, -0.67 * length);
  shape.lineTo(0, -length);
  shape.lineTo(-0.69 * width, -0.67 * length);
  shape.lineTo(-width, -0.28 * length);
  shape.closePath();
  return new ExtrudeGeometry(shape, { bevelEnabled: false, depth: height })
    .rotateX(-Math.PI / 2)
    .translate(0, bottom, 0);
}

function watchingBoat(): Mesh {
  const deck: PaintPiece[] = [
    [hullPart(2.45, 5.65, -0.46, 0.99), "#416370"],
    [hullPart(2.48, 5.64, 0.52, 0.2), "#bf6653"],
    [hullPart(2.39, 5.53, 0.71, 0.18), "#e0d2af"],
    [new BoxGeometry(2.85, 1.1, 3.48).translate(0, 1.37, 0.92), "#e5d9bd"],
    [new BoxGeometry(2.79, 0.63, 3.55).translate(0, 2.14, 0.94), "#52727b"],
    [new BoxGeometry(3.19, 0.22, 3.84).translate(0, 2.55, 0.88), "#f2e3c5"],
    [new BoxGeometry(2.12, 0.12, 2.45).translate(0, 2.73, 0.47), "#9e6d57"],
    [
      new CylinderGeometry(0.07, 0.11, 1.87, 6).translate(-0.54, 3.58, 0.31),
      "#5c7475",
    ],
    [new BoxGeometry(1.54, 0.09, 0.14).translate(-0.54, 4.23, 0.31), "#e4d5b5"],
    [new BoxGeometry(0.11, 0.94, 0.11).translate(1.64, 1.38, -3.98), "#f2e3c5"],
    [
      new BoxGeometry(0.11, 0.94, 0.11).translate(-1.64, 1.38, -3.98),
      "#f2e3c5",
    ],
    [new BoxGeometry(3.38, 0.1, 0.11).translate(0, 1.86, -3.98), "#f2e3c5"],
  ];
  for (const side of [-1, 1]) {
    const x = side * 2.02;
    deck.push(
      [new BoxGeometry(0.12, 0.91, 0.12).translate(x, 1.35, -1.42), "#f2e3c5"],
      [new BoxGeometry(0.12, 0.91, 0.12).translate(x, 1.35, -3.97), "#f2e3c5"],
      [new BoxGeometry(0.11, 0.11, 2.59).translate(x, 1.8, -2.69), "#f2e3c5"],
      [
        new BoxGeometry(0.09, 0.65, 0.12).translate(side * 0.88, 2.14, 2.73),
        "#eee1c6",
      ],
    );
  }
  for (const [x, z, pigment] of [
    [-1.34, -1.92, "#ba8066"],
    [-1.29, -3.19, "#789393"],
    [0.51, -3.1, "#a2a077"],
  ] as const) {
    deck.push(
      [new BoxGeometry(0.37, 0.82, 0.28).translate(x, 1.49, z), pigment],
      [new SphereGeometry(0.16, 7, 5).translate(x, 2.03, z), "#c1a188"],
    );
  }
  const boat = painted(deck);
  boat.name = "Whale-watching vessel hull and deck";
  return boat;
}

function boundaryBuoys(near: Vec2, far: Vec2): Mesh {
  const paint: PaintPiece[] = [];
  const count = Math.ceil(Math.hypot(far.x - near.x, far.z - near.z) / 8);
  for (let i = 0; i <= count; i++) {
    const x = MathUtils.lerp(near.x, far.x, i / count);
    const z = MathUtils.lerp(near.z, far.z, i / count);
    const endpoint = i === 0 || i === count;
    paint.push(
      [
        new SphereGeometry(1, 9, 6)
          .scale(endpoint ? 1.06 : 0.63, 0.45, endpoint ? 1.06 : 0.63)
          .translate(x, 0.33, z),
        "#c2a06b",
      ],
      [
        new CylinderGeometry(0.36, 0.55, endpoint ? 0.47 : 0.29, 9).translate(
          x,
          0.59,
          z,
        ),
        "#e8d3a4",
      ],
    );
    if (!endpoint) continue;
    paint.push(
      [
        new CylinderGeometry(0.085, 0.135, 2.46, 7).translate(x, 1.67, z),
        "#5e7477",
      ],
      [
        new BoxGeometry(0.19, 0.86, 1.34).translate(x, 2.62, z + 0.5),
        "#a8d8cd",
      ],
    );
  }
  const buoys = painted(paint);
  buoys.name = "Whale-watching outer buoy line";
  return buoys;
}

function shortWake(): Mesh<BufferGeometry, MeshBasicMaterial> {
  const vertices: number[] = [];
  for (const side of [-1, 1]) {
    const point = (i: number, edge: number) => {
      const t = i / 10;
      const x = 1.45 + t * 4.8 + edge * (0.23 * (1 - t) + 0.07);
      return [side * x, 0.2, -13 * t] as const;
    };
    for (let i = 0; i < 10; i++)
      vertices.push(
        ...point(i, -1),
        ...point(i, 1),
        ...point(i + 1, -1),
        ...point(i + 1, -1),
        ...point(i, 1),
        ...point(i + 1, 1),
      );
  }
  const mesh = new Mesh(
    new BufferGeometry().setAttribute(
      "position",
      new Float32BufferAttribute(vertices, 3),
    ),
    new MeshBasicMaterial({
      color: "#f9f1d5",
      side: DoubleSide,
      transparent: true,
      depthWrite: false,
    }),
  );
  mesh.material.forceSinglePass = true;
  mesh.position.z = -4.86;
  mesh.name = "Whale-watching wake";
  return mesh;
}

export class WhaleWatching {
  readonly group = new Group();
  private readonly vessel?: Readonly<{
    boat: Group;
    wake: ReturnType<typeof shortWake>;
    near: number;
    far: number;
  }>;

  constructor(private readonly level: WhaleLevel) {
    this.group.name = "Whale-watching reach";
    const [nearId, farId] = watchingBoundaryLandmarks;
    const near = level.landmarks.find(({ id }) => id === nearId)?.pos;
    const far = level.landmarks.find(({ id }) => id === farId)?.pos;
    if (!near || !far || near.z >= far.z) return;
    const boat = new Group();
    boat.name = "Whale-watching vessel";
    const wake = shortWake();
    const hull = watchingBoat();
    hull.scale.set(1.34, 1.21, 1.48);
    boat.add(hull, wake);
    this.vessel = { boat, wake, near: near.z, far: far.z };
    this.group.add(boundaryBuoys(near, far), boat);
    this.update(0, { low: false, reduced: false }, 0);
  }

  update(
    tick: number,
    settings: Pick<InputSettings, "low" | "reduced">,
    viewDepth: number,
  ): void {
    if (!this.vessel) return;
    const { boat, wake, near, far } = this.vessel;
    const pose = watchingVesselAt(tick, this.level.bounds.max.x, near, far);
    const pace = (pose.speed - SLOW_SPEED) / (CRUISE_SPEED - SLOW_SPEED);
    const lift =
      settings.reduced || settings.low
        ? 0
        : 0.075 * Math.sin(tick * STEP_SEC * 1.8);
    boat.position.set(pose.x, lift, pose.z);
    boat.rotation.y = pose.heading;
    wake.scale.set(
      MathUtils.lerp(0.88, 1.25, pace),
      1,
      MathUtils.lerp(0.48, 1.36, pace),
    );
    wake.material.opacity =
      MathUtils.lerp(0.47, 0.76, pace) *
      (1 - MathUtils.smoothstep(viewDepth, 0.2, 1.1));
    wake.visible = wake.material.opacity > 0.015;
  }
}
