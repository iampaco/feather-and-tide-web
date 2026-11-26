import type { GameMode, ReindeerRoute, Route, WhaleRoute } from "../core/game";
import type { Vec2 } from "../core/math";
import { contains, polygonError } from "./geometry.ts";

interface ZoneBase {
  readonly id: string;
  readonly points: readonly Vec2[];
  readonly label: string;
  readonly labelEn?: string;
}

export interface HazardMotion {
  readonly travel: Vec2;
  readonly periodTicks: number;
  readonly phaseTicks: number;
}

export interface WindGust {
  readonly periodTicks: number;
  readonly phaseTicks: number;
  readonly peak: Vec2;
}

export interface NoiseCycle {
  readonly periodTicks: number;
  readonly activeTicks: number;
  readonly phaseTicks: number;
  readonly followSpeed: number;
  readonly cohesionLoss: number;
}

export type Zone = ZoneBase &
  (
    | { readonly kind: "warning"; readonly hazardId: string }
    | {
        readonly kind: "hazard";
        readonly cost: number;
        readonly appearance?: "glass";
        readonly structure?: "breakwater";
        readonly depthMask?: number;
        readonly motion?: HazardMotion;
      }
    | {
        readonly kind: "interference";
        readonly strain: number;
        readonly wind?: Vec2;
        readonly gust?: WindGust;
        readonly cycle?: NoiseCycle;
      }
    | {
        readonly kind: "current";
        readonly direction: Vec2;
        readonly minAlignment: number;
        readonly speedAssist: number;
        readonly fullAssistAt?: number;
        readonly energySaving: number;
      }
    | { readonly kind: "crossCurrent"; readonly velocity: Vec2 }
    | { readonly kind: "supply"; readonly capacity: number }
    | { readonly kind: "sanctuary" | "checkpoint" | "goal" }
  );

export type Trigger = ZoneBase &
  (
    | {
        readonly kind: "route";
        readonly route: Route;
        readonly crossingZ?: number;
      }
    | { readonly kind: "merge" }
    | { readonly kind: "rescue"; readonly actorId: string }
  );

export interface Segment {
  readonly id: string;
  readonly title: string;
  readonly titleEn?: string;
  readonly start: number;
  readonly wind: Vec2;
  readonly color: string;
  readonly motionWind?: Readonly<{ speed: number; transition: number }>;
}

export interface Landmark {
  readonly id: string;
  readonly pos: Vec2;
  readonly label: string;
  readonly labelEn?: string;
  readonly kind: "beacon" | "peak" | "water" | "turbine" | "reed" | "shoal";
}

export interface GooseEncounters {
  readonly kite: {
    readonly bank: Vec2;
    readonly aloft: Vec2;
    readonly noticeZ: number;
    readonly clearZ: number;
    readonly noticeHalfWidth: number;
    readonly reelTicks: number;
    readonly span: number;
    readonly depthRadius: number;
    readonly heightRadius: number;
    readonly height: number;
    readonly heldHeight: number;
  };
  readonly glider: {
    readonly launch: Vec2;
    readonly crossTo: Vec2;
    readonly land: Vec2;
    readonly noticeZ: number;
    readonly inflateTicks: number;
    readonly crossTicks: number;
    readonly leaveTicks: number;
    readonly departureLift: number;
    readonly harnessDrop: number;
    readonly span: number;
    readonly depthRadius: number;
    readonly heightRadius: number;
    readonly height: number;
  };
}

export interface LevelSchema {
  readonly encounters?: GooseEncounters;
  readonly schemaVersion: 1;
  readonly levelRevision: string;
  readonly id: string;
  readonly title: string;
  readonly titleEn?: string;
  readonly species: "goose";
  readonly modes: readonly GameMode[];
  readonly bounds: { readonly min: Vec2; readonly max: Vec2 };
  readonly spawn: Vec2;
  readonly spawnSegment: string;
  readonly segments: readonly Segment[];
  readonly zones: readonly Zone[];
  readonly triggers: readonly Trigger[];
  readonly landmarks: readonly Landmark[];
}

export interface WhaleLevel extends Omit<
  LevelSchema,
  "species" | "encounters"
> {
  readonly species: "whale";
  readonly routes: readonly WhaleRoute[];
}

export interface RoadCrossing {
  readonly near: number;
  readonly far: number;
  readonly vehicleId: string;
  readonly culvert: {
    readonly left: number;
    readonly right: number;
    readonly near: number;
    readonly far: number;
    readonly depth: number;
  };
}

export interface GroundBarrier extends ZoneBase {
  readonly kind: "slope" | "fence" | "culvert";
}

export interface ReindeerLevel extends Omit<
  LevelSchema,
  "species" | "encounters"
> {
  readonly species: "reindeer";
  readonly routes: readonly ReindeerRoute[];
  readonly road: RoadCrossing;
  readonly barriers: readonly GroundBarrier[];
  readonly trails: readonly {
    readonly id: string;
    readonly points: readonly Vec2[];
  }[];
  readonly dustCycle: {
    readonly zoneIds: readonly string[];
    readonly phaseTicks: number;
    readonly calmTicks: number;
    readonly warningTicks: number;
    readonly activeTicks: number;
  };
}

export type AnyLevelSchema = LevelSchema | WhaleLevel | ReindeerLevel;

export function validateLevel(
  source: unknown,
  file: string,
  expected: "goose",
): LevelSchema;
export function validateLevel(
  source: unknown,
  file: string,
  expected: "whale",
): WhaleLevel;
export function validateLevel(
  source: unknown,
  file: string,
  expected: "reindeer",
): ReindeerLevel;
export function validateLevel(
  source: unknown,
  file: string,
  expected?: AnyLevelSchema["species"],
): AnyLevelSchema;
export function validateLevel(
  source: unknown,
  file: string,
  expected?: AnyLevelSchema["species"],
): AnyLevelSchema {
  const ids = new Set<string>();
  function fail(path: string, message: string): never {
    throw new Error(`${file} ${path}: ${message}`);
  }
  function record(value: unknown, path: string): Record<string, unknown> {
    if (value === null || typeof value !== "object" || Array.isArray(value))
      fail(path, "expected an object");
    return value as Record<string, unknown>;
  }
  function array(value: unknown, path: string): unknown[] {
    if (!Array.isArray(value)) fail(path, "expected an array");
    return value;
  }
  function string(value: unknown, path: string): string {
    if (typeof value !== "string" || !value.trim())
      fail(path, "expected a non-empty string");
    return value;
  }
  function english(value: unknown, path: string): string | undefined {
    if (value === undefined) return;
    const copy = string(value, path);
    if (/\p{Script=Han}/u.test(copy)) fail(path, "expected English copy");
    return copy;
  }
  function number(
    value: unknown,
    path: string,
    min = -Infinity,
    max = Infinity,
    integer = false,
  ): number {
    if (
      typeof value !== "number" ||
      !Number.isFinite(value) ||
      value < min ||
      value > max ||
      (integer && !Number.isInteger(value))
    )
      fail(path, "number out of range");
    return value;
  }
  function choice<T extends string>(
    value: unknown,
    choices: readonly T[],
    path: string,
  ): T {
    const match = choices.find((item) => item === value);
    if (match === undefined) fail(path, `expected ${choices.join(" or ")}`);
    return match;
  }
  function id(value: unknown, path: string): string {
    const key = string(value, path);
    if (!/^[A-Za-z][A-Za-z0-9-]*$/.test(key)) fail(path, "invalid ID");
    if (ids.has(key)) fail(path, `duplicate ID ${key}`);
    ids.add(key);
    return key;
  }
  function vec(value: unknown, path: string): Vec2 {
    const point = record(value, path);
    return { x: number(point.x, `${path}.x`), z: number(point.z, `${path}.z`) };
  }
  function windVector(value: unknown, path: string): Vec2 {
    const wind = vec(value, path);
    if (Math.hypot(wind.x, wind.z) > 1) fail(path, "maximum magnitude is 1");
    return wind;
  }

  const root = record(source, "$");
  if (root.schemaVersion !== 1) fail("schemaVersion", "unsupported version");
  const levelId = id(root.id, "id");
  const levelRevision = string(root.levelRevision, "levelRevision");
  const title = string(root.title, "title");
  const species = choice(
    root.species,
    ["goose", "whale", "reindeer"],
    "species",
  );
  if (expected && species !== expected) fail("species", `expected ${expected}`);
  const routes: readonly WhaleRoute[] =
    species === "whale"
      ? array(root.routes, "routes").map((route, i) =>
          choice(route, ["shipping", "quiet"], `routes[${i}]`),
        )
      : [];
  if (
    species === "whale" &&
    (routes.length !== 2 || new Set(routes).size !== 2)
  )
    fail("routes", "expected shipping and quiet");
  const groundRoutes =
    species === "reindeer"
      ? array(root.routes, "routes").map((route, i) =>
          choice<ReindeerRoute>(route, ["dust", "greenbelt"], `routes[${i}]`),
        )
      : [];
  if (
    species === "reindeer" &&
    (groundRoutes.length !== 2 || new Set(groundRoutes).size !== 2)
  )
    fail("routes", "expected dust and greenbelt");
  const modes = array(root.modes, "modes").map((mode) =>
    choice<GameMode>(mode, ["journey"], "modes"),
  );
  if (modes.length !== 1) fail("modes", "expected journey only");
  const dimensions = record(root.bounds, "bounds");
  const min = vec(dimensions.min, "bounds.min");
  const max = vec(dimensions.max, "bounds.max");
  if (min.x >= max.x || min.z >= max.z)
    fail("bounds", "empty or reversed limits");

  function position(value: unknown, path: string): Vec2 {
    const p = vec(value, path);
    if (p.x < min.x || p.x > max.x || p.z < min.z || p.z > max.z)
      fail(path, "outside map");
    return p;
  }

  const spawn = position(root.spawn, "spawn");
  const spawnSegment = string(root.spawnSegment, "spawnSegment");
  let previousStart = -Infinity;
  const segments = array(root.segments, "segments").map((value, i): Segment => {
    const path = `segments[${i}]`;
    const item = record(value, path);
    const start = number(item.start, `${path}.start`, min.z, max.z);
    if (start <= previousStart || (i === 0 && start !== min.z))
      fail(
        `${path}.start`,
        "segments must begin at world minimum and increase",
      );
    previousStart = start;
    const color = string(item.color, `${path}.color`);
    if (!/^#[0-9a-f]{6}$/i.test(color))
      fail(`${path}.color`, "expected RGB hex");
    const motion =
      item.motionWind === undefined
        ? undefined
        : record(item.motionWind, `${path}.motionWind`);
    return {
      id: id(item.id, `${path}.id`),
      title: string(item.title, `${path}.title`),
      titleEn: english(item.titleEn, `${path}.titleEn`),
      start,
      wind: windVector(item.wind, `${path}.wind`),
      color,
      ...(motion && {
        motionWind: {
          speed: number(motion.speed, `${path}.motionWind.speed`, 0, 5),
          transition: number(
            motion.transition,
            `${path}.motionWind.transition`,
            1,
            max.z - min.z,
          ),
        },
      }),
    };
  });
  if (
    segments.findLast((segment) => segment.start <= spawn.z)?.id !==
    spawnSegment
  )
    fail("spawnSegment", "does not reference the segment containing spawn");
  if (
    species === "whale" &&
    segments.map((segment) => segment.id).join(",") !== "W0,W1,W2,W3,W4"
  )
    fail("segments", "expected W0 through W4 in order");
  if (
    species === "reindeer" &&
    segments.map(({ id }) => id).join(",") !== "R0,R1,R2,R3,R4"
  )
    fail("segments", "expected R0 through R4 in order");

  function boundary(item: Record<string, unknown>, path: string): ZoneBase {
    const points = array(item.points, `${path}.points`).map((point, j) =>
      position(point, `${path}.points[${j}]`),
    );
    const error = polygonError(points);
    if (error) fail(`${path}.points`, error);
    return {
      id: id(item.id, `${path}.id`),
      points,
      label: string(item.label, `${path}.label`),
      labelEn: english(item.labelEn, `${path}.labelEn`),
    };
  }

  const zones = array(root.zones, "zones").map((value, i): Zone => {
    const path = `zones[${i}]`;
    const item = record(value, path);
    const base = boundary(item, path);
    const kind = choice(
      item.kind,
      [
        "warning",
        "hazard",
        "interference",
        "current",
        "crossCurrent",
        "supply",
        "sanctuary",
        "checkpoint",
        "goal",
      ],
      `${path}.kind`,
    );
    switch (kind) {
      case "current": {
        if (species !== "whale") fail(path, "expected a whale level");
        const direction = vec(item.direction, `${path}.direction`);
        const length = Math.hypot(direction.x, direction.z);
        if (!Number.isFinite(length) || length === 0)
          fail(`${path}.direction`, "expected a nonzero flow direction");
        return {
          ...base,
          kind,
          direction: { x: direction.x / length, z: direction.z / length },
          minAlignment: number(
            item.minAlignment,
            `${path}.minAlignment`,
            0.5,
            1,
          ),
          speedAssist: number(item.speedAssist, `${path}.speedAssist`, 0.1, 2),
          ...(item.fullAssistAt === undefined
            ? {}
            : {
                fullAssistAt: number(
                  item.fullAssistAt,
                  `${path}.fullAssistAt`,
                  0.2,
                  1,
                ),
              }),
          energySaving: number(
            item.energySaving,
            `${path}.energySaving`,
            0,
            0.75,
          ),
        };
      }
      case "crossCurrent": {
        if (species !== "whale") fail(path, "expected a whale level");
        const velocity = vec(item.velocity, `${path}.velocity`);
        const speed = Math.hypot(velocity.x, velocity.z);
        if (speed < 0.1 || speed > 4)
          fail(`${path}.velocity`, "expected flow speed between 0.1 and 4");
        return { ...base, kind, velocity };
      }
      case "warning":
        return {
          ...base,
          kind,
          hazardId: string(item.hazardId, `${path}.hazardId`),
        };
      case "hazard": {
        let depthMask: number | undefined;
        let motion: HazardMotion | undefined;
        if (species === "whale") {
          depthMask = number(item.depthMask, `${path}.depthMask`, 1, 7);
          if (!Number.isInteger(depthMask))
            fail(
              `${path}.depthMask`,
              "expected a non-empty integer layer mask",
            );
        }
        if (species !== "goose") {
          if (item.motion !== undefined) {
            const spec = record(item.motion, `${path}.motion`);
            const travel = vec(spec.travel, `${path}.motion.travel`);
            if (!travel.x && !travel.z)
              fail(`${path}.motion.travel`, "empty path");
            const periodTicks = number(
              spec.periodTicks,
              `${path}.motion.periodTicks`,
              2,
              60 * 3600,
            );
            if (periodTicks % 2 !== 0)
              fail(`${path}.motion.periodTicks`, "expected an even tick count");
            const phaseTicks = number(
              spec.phaseTicks,
              `${path}.motion.phaseTicks`,
              0,
              periodTicks - 1,
            );
            if (!Number.isInteger(phaseTicks))
              fail(`${path}.motion.phaseTicks`, "expected integer ticks");
            for (const point of base.points)
              position(
                { x: point.x + travel.x, z: point.z + travel.z },
                `${path}.motion.travel`,
              );
            motion = { travel, periodTicks, phaseTicks };
          }
        }
        const structure =
          item.structure === undefined
            ? undefined
            : choice(item.structure, ["breakwater"], `${path}.structure`);
        if (structure && (species !== "whale" || depthMask !== 7 || motion))
          fail(path, "expected a stationary, full-depth breakwater");
        return {
          ...base,
          kind,
          cost: number(item.cost, `${path}.cost`, 0, 1),
          ...(depthMask !== undefined && { depthMask }),
          ...(motion && { motion }),
          ...(structure && { structure }),
          ...(item.appearance === undefined
            ? {}
            : {
                appearance: choice(
                  item.appearance,
                  ["glass"] as const,
                  `${path}.appearance`,
                ),
              }),
        };
      }
      case "interference": {
        let cycle: NoiseCycle | undefined;
        if (item.cycle !== undefined) {
          if (species !== "whale")
            fail(`${path}.cycle`, "expected a whale level");
          const spec = record(item.cycle, `${path}.cycle`);
          const periodTicks = number(
            spec.periodTicks,
            `${path}.cycle.periodTicks`,
            2,
            60 * 3600,
          );
          const activeTicks = number(
            spec.activeTicks,
            `${path}.cycle.activeTicks`,
            1,
            periodTicks - 1,
          );
          const phaseTicks = number(
            spec.phaseTicks,
            `${path}.cycle.phaseTicks`,
            0,
            periodTicks - 1,
          );
          if (![periodTicks, activeTicks, phaseTicks].every(Number.isInteger))
            fail(`${path}.cycle`, "expected integer ticks");
          cycle = {
            periodTicks,
            activeTicks,
            phaseTicks,
            followSpeed: number(
              spec.followSpeed,
              `${path}.cycle.followSpeed`,
              0.1,
              30,
            ),
            cohesionLoss: number(
              spec.cohesionLoss,
              `${path}.cycle.cohesionLoss`,
              0,
              1,
            ),
          };
        }
        const wind =
          item.wind === undefined
            ? undefined
            : windVector(item.wind, `${path}.wind`);
        let gust: WindGust | undefined;
        if (item.gust !== undefined) {
          if (species !== "goose" || !wind)
            fail(`${path}.gust`, "expected a goose wind zone");
          const spec = record(item.gust, `${path}.gust`);
          const periodTicks = number(
            spec.periodTicks,
            `${path}.gust.periodTicks`,
            2,
            60 * 3600,
          );
          const phaseTicks = number(
            spec.phaseTicks,
            `${path}.gust.phaseTicks`,
            0,
            periodTicks - 1,
          );
          if (![periodTicks, phaseTicks].every(Number.isInteger))
            fail(`${path}.gust`, "expected integer ticks");
          gust = {
            periodTicks,
            phaseTicks,
            peak: windVector(spec.peak, `${path}.gust.peak`),
          };
        }
        return {
          ...base,
          kind,
          strain: number(item.strain, `${path}.strain`, 0, 1),
          ...(cycle && { cycle }),
          ...(wind && { wind }),
          ...(gust && { gust }),
        };
      }
      case "supply":
        return {
          ...base,
          kind,
          capacity: number(item.capacity, `${path}.capacity`, 0.01, 1),
        };
      default:
        return { ...base, kind };
    }
  });
  for (const zone of zones) {
    if (
      zone.kind === "warning" &&
      !zones.some(
        (candidate) =>
          candidate.kind === "hazard" && candidate.id === zone.hazardId,
      )
    )
      fail(`zones.${zone.id}.hazardId`, "unknown hazard");
    if (
      species !== "goose" &&
      zone.kind === "hazard" &&
      !zones.some(
        (candidate) =>
          candidate.kind === "warning" && candidate.hazardId === zone.id,
      )
    )
      fail(`zones.${zone.id}`, "missing a warning zone");
  }
  if (zones.filter((zone) => zone.kind === "goal").length > 1)
    fail("zones", "expected at most one goal");
  const triggers = array(root.triggers, "triggers").map((value, i): Trigger => {
    const path = `triggers[${i}]`;
    const item = record(value, path);
    const base = boundary(item, path);
    const kind = choice(
      item.kind,
      ["route", "merge", "rescue"],
      `${path}.kind`,
    );
    switch (kind) {
      case "route": {
        const crossingZ =
          item.crossingZ === undefined
            ? undefined
            : number(
                item.crossingZ,
                `${path}.crossingZ`,
                Math.min(...base.points.map(({ z }) => z)),
                Math.max(...base.points.map(({ z }) => z)),
              );
        return {
          ...base,
          kind,
          route: choice<Route>(
            item.route,
            species === "whale"
              ? routes
              : species === "reindeer"
                ? groundRoutes
                : ["mountain", "lake"],
            `${path}.route`,
          ),
          ...(crossingZ === undefined ? {} : { crossingZ }),
        };
      }
      case "rescue": {
        const actorId = string(item.actorId, `${path}.actorId`);
        const roster =
          species === "whale"
            ? /^whale-[1-5]$/
            : species === "reindeer"
              ? /^reindeer-[1-8]$/
              : /^goose-(?:[1-9]|10|11)$/;
        if (!roster.test(actorId)) fail(`${path}.actorId`, "unknown companion");
        return { ...base, kind, actorId };
      }
      default:
        return { ...base, kind };
    }
  });
  const landmarks = array(root.landmarks, "landmarks").map(
    (value, i): Landmark => {
      const path = `landmarks[${i}]`;
      const item = record(value, path);
      const kind = choice(
        item.kind,
        ["beacon", "peak", "water", "turbine", "reed", "shoal"],
        `${path}.kind`,
      );
      if (kind === "shoal" && species !== "whale")
        fail(`${path}.kind`, "expected a whale level");
      return {
        id: id(item.id, `${path}.id`),
        pos: position(item.pos, `${path}.pos`),
        label: string(item.label, `${path}.label`),
        labelEn: english(item.labelEn, `${path}.labelEn`),
        kind,
      };
    },
  );
  if (species !== "goose") {
    for (const route of species === "whale" ? routes : groundRoutes)
      if (
        !triggers.some(
          (item) =>
            item.kind === "route" &&
            item.route === route &&
            item.crossingZ !== undefined,
        )
      )
        fail(`routes.${route}`, "missing a crossing gate");
    if (!triggers.some((item) => item.kind === "merge"))
      fail("triggers", "missing route merge");
    for (const id of ["C1", "C2"])
      if (!zones.some((zone) => zone.kind === "checkpoint" && zone.id === id))
        fail(`zones.${id}`, "missing checkpoint");
    if (!zones.some((zone) => zone.kind === "goal"))
      fail("zones", "missing goal");
  }
  const common = {
    schemaVersion: 1 as const,
    levelRevision,
    id: levelId,
    title,
    titleEn: english(root.titleEn, "titleEn"),
    modes,
    bounds: { min, max },
    spawn,
    spawnSegment,
    segments,
    zones,
    triggers,
    landmarks,
  };
  if (species === "reindeer") {
    function rectangle(points: readonly Vec2[], path: string) {
      const x = [...new Set(points.map((point) => point.x))].sort(
        (a, b) => a - b,
      );
      const z = [...new Set(points.map((point) => point.z))].sort(
        (a, b) => a - b,
      );
      if (
        points.length !== 5 ||
        x.length !== 2 ||
        z.length !== 2 ||
        x[0] === undefined ||
        x[1] === undefined ||
        z[0] === undefined ||
        z[1] === undefined
      )
        fail(path, "expected an axis-aligned rectangle");
      for (let i = 1; i < points.length; i++) {
        const a = points[i - 1];
        const b = points[i];
        if (a && b && a.x !== b.x && a.z !== b.z)
          fail(path, "expected horizontal or vertical edges");
      }
      return { left: x[0], right: x[1], near: z[0], far: z[1] };
    }
    const spec = record(root.road, "road");
    const near = number(spec.near, "road.near", min.z, max.z);
    const far = number(spec.far, "road.far", near + 1, max.z);
    const vehicleId = string(spec.vehicleId, "road.vehicleId");
    const vehicle = zones.find((zone) => zone.id === vehicleId);
    if (
      vehicle?.kind !== "hazard" ||
      !vehicle.motion ||
      vehicle.motion.travel.z !== 0 ||
      vehicle.points.some(({ z }) => z < near || z > far)
    )
      fail("road.vehicleId", "expected a moving vehicle inside the road");
    rectangle(vehicle.points, "road.vehicleId");
    const passage = record(spec.culvert, "road.culvert");
    const left = number(passage.left, "road.culvert.left", min.x, max.x);
    const right = number(passage.right, "road.culvert.right", left + 3, max.x);
    const culvert = {
      left,
      right,
      near: number(passage.near, "road.culvert.near", min.z, near - 3),
      far: number(passage.far, "road.culvert.far", far + 3, max.z),
      depth: number(passage.depth, "road.culvert.depth", 0.5, 5),
    };
    const barriers = array(root.barriers, "barriers").map(
      (value, i): GroundBarrier => {
        const path = `barriers[${i}]`;
        const item = record(value, path);
        const base = boundary(item, path);
        rectangle(base.points, path);
        if (contains(base.points, spawn)) fail(path, "blocks spawn");
        return {
          ...base,
          kind: choice(
            item.kind,
            ["slope", "fence", "culvert"],
            `${path}.kind`,
          ),
        };
      },
    );
    const walls = barriers
      .filter(({ kind }) => kind === "culvert")
      .map(({ id, points }) => rectangle(points, id));
    if (
      walls.length !== 2 ||
      !walls.every(
        (wall) => wall.near === culvert.near && wall.far === culvert.far,
      ) ||
      !walls.some((wall) => wall.right === culvert.left) ||
      !walls.some((wall) => wall.left === culvert.right)
    )
      fail("road.culvert", "expected both continuous side walls");
    if (culvert.depth / Math.min(near - culvert.near, culvert.far - far) > 0.5)
      fail("road.culvert", "ramp slope exceeds the walkable grade");
    if (
      spawn.z >= near ||
      zones.filter(({ kind }) => kind === "hazard").length !== 1
    )
      fail("road", "expected spawn before the road and a single vehicle");
    const trails = array(root.trails, "trails").map((value, i) => {
      const path = `trails[${i}]`;
      const item = record(value, path);
      const points = array(item.points, `${path}.points`).map((point, j) =>
        vec(point, `${path}.points[${j}]`),
      );
      if (
        points.length < 2 ||
        points.some(
          ({ x, z }) => x < min.x || x > max.x || z < min.z || z > max.z,
        )
      )
        fail(path, "expected at least two in-bounds trail points");
      return { id: id(item.id, `${path}.id`), points };
    });
    const dust = record(root.dustCycle, "dustCycle");
    const dustZoneIds = array(dust.zoneIds, "dustCycle.zoneIds").map(
      (value, i) => string(value, `dustCycle.zoneIds[${i}]`),
    );
    if (
      !dustZoneIds.length ||
      new Set(dustZoneIds).size !== dustZoneIds.length ||
      dustZoneIds.some(
        (id) =>
          !zones.some((zone) => zone.id === id && zone.kind === "interference"),
      )
    )
      fail("dustCycle.zoneIds", "expected distinct interference zones");
    const calmTicks = number(
      dust.calmTicks,
      "dustCycle.calmTicks",
      1,
      36000,
      true,
    );
    const warningTicks = number(
      dust.warningTicks,
      "dustCycle.warningTicks",
      180,
      36000,
      true,
    );
    const activeTicks = number(
      dust.activeTicks,
      "dustCycle.activeTicks",
      1,
      36000,
      true,
    );
    const phaseTicks = number(
      dust.phaseTicks,
      "dustCycle.phaseTicks",
      0,
      calmTicks + warningTicks + activeTicks - 1,
      true,
    );
    return {
      ...common,
      species,
      routes: groundRoutes,
      road: { near, far, vehicleId, culvert },
      barriers,
      trails,
      dustCycle: {
        zoneIds: dustZoneIds,
        calmTicks,
        warningTicks,
        activeTicks,
        phaseTicks,
      },
    };
  }
  if (species === "whale") return { ...common, species, routes };
  if (root.encounters === undefined) return { ...common, species };
  const encounters = record(root.encounters, "encounters");
  const kite = record(encounters.kite, "encounters.kite");
  const glider = record(encounters.glider, "encounters.glider");
  const bank = position(kite.bank, "kite.bank");
  const aloft = position(kite.aloft, "kite.aloft");
  const launch = position(glider.launch, "glider.launch");
  const crossTo = position(glider.crossTo, "glider.crossTo");
  const heldHeight = number(kite.heldHeight, "kite.heldHeight", 0.1, 3);
  return {
    ...common,
    species,
    encounters: {
      kite: {
        bank,
        aloft,
        heldHeight,
        height: number(kite.height, "kite.height", heldHeight + 1, 20),
        depthRadius: number(kite.depthRadius, "kite.depthRadius", 0.1, 20),
        heightRadius: number(kite.heightRadius, "kite.heightRadius", 0.1, 20),
        span: number(kite.span, "kite.span", 1, 20),
        noticeZ: number(kite.noticeZ, "kite.noticeZ", min.z, aloft.z),
        noticeHalfWidth: number(
          kite.noticeHalfWidth,
          "kite.noticeHalfWidth",
          1,
          max.x - min.x,
        ),
        clearZ: number(
          kite.clearZ,
          "kite.clearZ",
          Math.max(bank.z, aloft.z),
          max.z,
        ),
        reelTicks: number(kite.reelTicks, "kite.reelTicks", 1, 3600, true),
      },
      glider: {
        launch,
        crossTo,
        land: position(glider.land, "glider.land"),
        height: number(glider.height, "glider.height", 2, 20),
        departureLift: number(
          glider.departureLift,
          "glider.departureLift",
          0,
          30,
        ),
        harnessDrop: number(glider.harnessDrop, "glider.harnessDrop", 0, 10),
        depthRadius: number(glider.depthRadius, "glider.depthRadius", 0.1, 20),
        heightRadius: number(
          glider.heightRadius,
          "glider.heightRadius",
          0.1,
          20,
        ),
        span: number(glider.span, "glider.span", 1, 20),
        noticeZ: number(glider.noticeZ, "glider.noticeZ", min.z, launch.z),
        inflateTicks: number(
          glider.inflateTicks,
          "glider.inflateTicks",
          1,
          3600,
          true,
        ),
        crossTicks: number(
          glider.crossTicks,
          "glider.crossTicks",
          1,
          3600,
          true,
        ),
        leaveTicks: number(
          glider.leaveTicks,
          "glider.leaveTicks",
          1,
          3600,
          true,
        ),
      },
    },
  };
}
