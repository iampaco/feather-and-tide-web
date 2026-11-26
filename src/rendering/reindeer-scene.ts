import {
  AmbientLight,
  AnimationMixer,
  BoxGeometry,
  BufferGeometry,
  CircleGeometry,
  Color,
  CylinderGeometry,
  DirectionalLight,
  DoubleSide,
  Float32BufferAttribute,
  Fog,
  Group,
  InstancedMesh,
  LoopOnce,
  DynamicDrawUsage,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  Object3D,
  MathUtils,
  Scene,
  SkinnedMesh,
  Vector3,
  type AnimationAction,
  type Material,
  type WebGLRenderer,
} from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";
import type { ReindeerState } from "../core/game";
import { angleDelta, clamp, lerp, type Vec2 } from "../core/math";
import type { InputSettings } from "../input/input";
import { hazardOffset, type MovingHazard } from "../levels/moving-hazard";
import {
  groundHeight,
  roadVehicle,
  vehicleDirection,
} from "../levels/reindeer-ground";
import type { ReindeerLevel } from "../levels/schema";
import { sampleReindeerDust } from "../simulation/reindeer-dust";
import { REINDEER } from "../simulation/reindeer-tuning";
import { CameraDirector } from "./camera";
import type { OrbitClearance } from "./orbit-clearance";
import { applyReindeerRole, batchReindeerCoat } from "./reindeer-coat";
import { ReindeerRoad } from "./reindeer-road";
import { ReindeerRoutes } from "./reindeer-routes";
import { ReindeerSeason } from "./reindeer-season";
import { ReindeerTerrain } from "./reindeer-terrain";

const clipNames = ["Idle", "Walk", "Run", "Call", "Settle"] as const;
type ClipName = (typeof clipNames)[number];

const winterAir = "#d5d8e4";
const atmosphere = new Map([
  ["R0", { sky: winterAir, light: "#ffecd8" }],
  ["R1", { sky: "#d3dbdd", light: "#fff1dc" }],
  ["R2", { sky: "#deded3", light: "#fff2d8" }],
  ["R3", { sky: "#e2d6c7", light: "#ffead2" }],
  ["R4", { sky: "#e7dfd6", light: "#fff0cf" }],
]);

export async function loadReindeerAssets(
  graybox: boolean,
): Promise<GLTF | null> {
  if (graybox) return null;
  const base = `${import.meta.env.BASE_URL}assets/`;
  const response = await fetch(`${base}manifest.json`);
  if (!response.ok) throw new Error(`驯鹿素材清单 HTTP ${response.status}`);
  const manifest = (await response.json()) as {
    version?: number;
    assets?: { assetId: string; url: string }[];
  };
  const entry = manifest.assets?.find(
    ({ assetId }) => assetId === "RD-CHR-001",
  );
  if (manifest.version !== 1 || !entry?.url)
    throw new Error("驯鹿素材清单缺少 RD-CHR-001");
  const model = await new GLTFLoader().loadAsync(base + entry.url);
  for (const name of clipNames)
    if (!model.animations.some((clip) => clip.name === name))
      throw new Error(`Reindeer model is missing ${name}`);
  batchReindeerCoat(model.scene);
  return model;
}

function pigment(color: string, opacity = 1): MeshLambertMaterial {
  return new MeshLambertMaterial({
    color,
    opacity,
    transparent: opacity < 1,
    depthWrite: opacity === 1,
    side: DoubleSide,
  });
}

function bounds(points: readonly Vec2[]) {
  return {
    left: Math.min(...points.map(({ x }) => x)),
    right: Math.max(...points.map(({ x }) => x)),
    near: Math.min(...points.map(({ z }) => z)),
    far: Math.max(...points.map(({ z }) => z)),
  };
}

interface DeerView {
  readonly root: Group;
  readonly mixer: AnimationMixer;
  readonly actions: ReadonlyMap<ClipName, AnimationAction>;
  readonly groundContacts: readonly Object3D[];
  readonly scale: number;
  active: ClipName | undefined;
  called: boolean;
  scripted: boolean;
}

const landingCallTime = 0.84;
const landingReplyDelay = 0.2;
const hoofContactNames = [
  "HoofContact_FL",
  "HoofContact_FR",
  "HoofContact_HL",
  "HoofContact_HR",
] as const;

function shadowGeometry(): BufferGeometry {
  const sides = 16;
  const positions = [0, 0, 0];
  const colors = [1, 1, 1, 0.32];
  const indices: number[] = [];
  for (const [radius, opacity] of [
    [0.37, 0.27],
    [0.72, 0.11],
    [1, 0],
  ] as const) {
    const start = positions.length / 3;
    for (let side = 0; side < sides; side++) {
      const angle = (side * 2 * Math.PI) / sides;
      positions.push(Math.cos(angle) * radius, 0, Math.sin(angle) * radius);
      colors.push(1, 1, 1, opacity);
      const current = start + side;
      const next = start + ((side + 1) % sides);
      if (start === 1) indices.push(0, next, current);
      else {
        indices.push(
          current - sides,
          next - sides,
          current,
          next - sides,
          next,
          current,
        );
      }
    }
  }
  return new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 4))
    .setIndex(indices);
}

export class ReindeerScene {
  readonly species = "reindeer";
  readonly camera = new CameraDirector(42);
  private readonly world = new Scene();
  private readonly deer: readonly DeerView[];
  private readonly vehicle: MovingHazard;
  private readonly car = new Group();
  private readonly headlights = new Map<-1 | 1, Group>();
  private readonly sky = new Color(winterAir);
  private readonly fog = new Fog(winterAir, 82, 174);
  private readonly sun = new DirectionalLight("#ffecd8", 1.9);
  private readonly roadArt: ReindeerRoad;
  private readonly season: ReindeerSeason;
  private readonly terrain: ReindeerTerrain;
  private readonly routes: ReindeerRoutes;
  private readonly clearance: OrbitClearance;
  private readonly choices: ReadonlyMap<string, readonly Vec2[]>;
  private readonly overlook: Vec2 | undefined;
  private frameOffset = 0;
  private hasView = false;
  private readonly stamp = new Object3D();
  private readonly hoof = new Vector3();
  private readonly shadowProbe = { x: 0, z: 0 };
  private readonly shadows = new InstancedMesh(
    shadowGeometry(),
    new MeshBasicMaterial({
      color: "#564d58",
      vertexColors: true,
      transparent: true,
      depthWrite: false,
    }),
    REINDEER.size * (1 + hoofContactNames.length),
  );
  private readonly marker = new Vector3();
  private readonly size = { width: 0, height: 0, ratio: 0 };
  private readonly frameColor = new Color();

  constructor(
    readonly renderer: WebGLRenderer,
    private readonly level: ReindeerLevel,
    private readonly assets: GLTF | null,
  ) {
    this.vehicle = roadVehicle(level);
    this.world.background = this.sky;
    this.world.fog = this.fog;
    this.sun.position.set(11, 16, -13);
    this.roadArt = new ReindeerRoad(level);
    this.season = new ReindeerSeason(level);
    this.clearance = {
      height: (x, z) =>
        Math.max(
          groundHeight(level.road, { x, z }),
          this.season.cameraHeight(x, z),
        ),
      obstacles: [],
    };
    this.terrain = new ReindeerTerrain(level);
    this.routes = new ReindeerRoutes(level);
    this.overlook = level.landmarks.find(({ id }) => id === "thaw-turn")?.pos;
    this.choices = new Map(
      (
        [
          ["R0", ["winter-trail", "winter-right"]],
          ["R2", ["wide-sign", "short-fence-sign"]],
          ["R3", ["dust-sign", "green-sign"]],
        ] as const
      ).map(([segment, ids]) => [
        segment,
        ids.flatMap((id) => {
          const landmark = level.landmarks.find((mark) => mark.id === id);
          return landmark ? [landmark.pos] : [];
        }),
      ]),
    );
    this.shadows.name = "Herd contact shadows";
    this.shadows.renderOrder = 1;
    this.shadows.frustumCulled = false;
    this.shadows.instanceMatrix.setUsage(DynamicDrawUsage);
    this.world.add(
      new AmbientLight("#e1e5f3", 1.12),
      this.sun,
      this.terrain.group,
      this.roadArt.group,
      this.routes.group,
      this.season.group,
      this.shadows,
    );
    this.buildTracks();
    this.buildVehicle();
    this.deer = Array.from({ length: REINDEER.size }, (_, index) =>
      this.buildDeer(index),
    );
    this.resetFlightView();
  }

  private buildTracks(): void {
    const { road } = this.level;
    const paths = this.level.trails.map(({ points }) => points);
    const toes = [-1, 1].map((side) =>
      new CircleGeometry(1, 8)
        .rotateX(-Math.PI / 2)
        .scale(0.102, 1, 0.28)
        .rotateY(side * 0.16)
        .translate(side * 0.122, 0, side * 0.021),
    );
    const geometry = mergeGeometries(toes);
    for (const toe of toes) toe.dispose();
    if (!geometry) throw new Error("Unable to prepare reindeer hoof marks");
    const ink = new MeshBasicMaterial({
      color: "#827165",
      opacity: 0.46,
      transparent: true,
      depthWrite: false,
    });
    const transform = new Object3D();
    for (const path of paths) {
      const tracks: { pos: Vec2; yaw: number; pitch: number }[] = [];
      for (let index = 1; index < path.length; index++) {
        const a = path[index - 1];
        const b = path[index];
        if (!a || !b) continue;
        const length = Math.hypot(b.x - a.x, b.z - a.z);
        if (length === 0) continue;
        const dx = (b.x - a.x) / length;
        const dz = (b.z - a.z) / length;
        const yaw = Math.atan2(dx, dz);
        const byRoad =
          a.z >= road.culvert.near - 16 && b.z <= road.culvert.far + 18;
        const steps = Math.max(1, Math.floor(length / (byRoad ? 1.55 : 2.6)));
        for (let step = 0; step < steps; step++) {
          const t = (step + 0.48) / steps;
          const offset = (tracks.length % 2 === 0 ? -1 : 1) * 0.52;
          const pos = {
            x: lerp(a.x, b.x, t) + offset * dz,
            z: lerp(a.z, b.z, t) - offset * dx,
          };
          const rise =
            groundHeight(road, { x: pos.x + dx * 0.3, z: pos.z + dz * 0.3 }) -
            groundHeight(road, { x: pos.x - dx * 0.3, z: pos.z - dz * 0.3 });
          tracks.push({ pos, yaw, pitch: -Math.atan2(rise, 0.6) });
        }
      }
      const prints = new InstancedMesh(geometry, ink, tracks.length);
      prints.name = "Cloven hoof trail";
      tracks.forEach(({ pos, yaw, pitch }, index) => {
        transform.position.set(pos.x, groundHeight(road, pos) + 0.036, pos.z);
        transform.rotation.set(pitch, yaw, 0, "YXZ");
        transform.updateMatrix();
        prints.setMatrixAt(index, transform.matrix);
      });
      this.world.add(prints);
    }
  }

  private buildVehicle(): void {
    const { left, right, near, far } = bounds(this.vehicle.points);
    const length = right - left;
    const width = far - near;
    const centerX = (left + right) / 2;
    const centerZ = (far + near) / 2;
    const parts: BufferGeometry[] = [];
    const swatch = new Color();
    const paint = (geometry: BufferGeometry, color: string) => {
      const count = geometry.getAttribute("position").count;
      const colors = new Float32Array(count * 3);
      swatch.set(color);
      for (let i = 0; i < count; i++) swatch.toArray(colors, i * 3);
      parts.push(
        geometry.setAttribute("color", new Float32BufferAttribute(colors, 3)),
      );
    };
    const shell = (
      x: number,
      y: number,
      z: number,
      color: string,
      rise: number,
    ) => {
      paint(
        new RoundedBoxGeometry(x, y, z, 1, 0.32).translate(
          centerX,
          rise,
          centerZ,
        ),
        color,
      );
    };
    shell(length, 0.46, width * 0.99, "#565356", 0.69);
    shell(length * 0.99, 1.1, width * 0.96, "#9e6854", 1.23);
    shell(length * 0.63, 0.82, width * 0.82, "#4d666c", 2.08);
    shell(length * 0.46, 0.25, width * 0.77, "#b4836a", 2.58);
    const tire = new CylinderGeometry(0.59, 0.59, 0.4, 10);
    const wheel = tire.toNonIndexed().rotateX(Math.PI / 2);
    tire.dispose();
    for (const x of [left + length * 0.21, right - length * 0.21]) {
      for (const z of [near + 0.23, far - 0.23])
        paint(wheel.clone().translate(x, 0.72, z), "#3d4148");
    }
    wheel.dispose();
    const body = mergeGeometries(parts);
    for (const part of parts) part.dispose();
    if (!body) throw new Error("Unable to prepare reindeer road vehicle");
    this.car.add(
      new Mesh(body, new MeshLambertMaterial({ vertexColors: true })),
    );
    const lamp = new BoxGeometry(0.12, 0.3, 0.61);
    const lightPaint = new MeshBasicMaterial({ color: "#ffedb1" });
    for (const direction of [-1, 1] as const) {
      const x = direction < 0 ? left + 0.05 : right - 0.05;
      const lamps = new Group();
      for (const z of [near + 0.65, far - 0.65]) {
        const light = new Mesh(lamp, lightPaint);
        light.position.set(x, 1.38, z);
        lamps.add(light);
      }
      this.headlights.set(direction, lamps);
      this.car.add(lamps);
    }
    this.world.add(this.car);
  }

  private buildDeer(index: number): DeerView {
    const root = new Group();
    const model = this.assets;
    const deer = model ? clone(model.scene) : new Group();
    if (model) {
      if (index === 0) applyReindeerRole(deer, "leader");
      if (index === 1) applyReindeerRole(deer, "calf");
    } else {
      const shell = pigment(index === 0 ? "#9b6738" : "#7c776f");
      const trunk = new Mesh(new BoxGeometry(0.82, 0.92, 1.68), shell);
      const head = new Mesh(new BoxGeometry(0.5, 0.51, 0.6), shell);
      trunk.position.y = 0.93;
      head.position.set(0, 1.55, 0.8);
      deer.add(trunk, head);
    }
    const groundContacts = hoofContactNames.flatMap((name) => {
      const contact = deer.getObjectByName(name);
      return contact ? [contact] : [];
    });
    const scale = index === 0 ? 1.24 : index === 1 ? 0.88 : 1.06;
    deer.scale.setScalar(scale);
    root.add(deer);
    if (index === 0) {
      const halo = new Mesh(
        new CircleGeometry(0.32, 12).rotateX(-Math.PI / 2),
        new MeshBasicMaterial({ color: "#f2ce85" }),
      );
      halo.position.set(0, 0.03, -1.42);
      root.add(halo);
    }
    const mixer = new AnimationMixer(deer);
    const actions = new Map<ClipName, AnimationAction>();
    for (const name of clipNames) {
      const clip = model?.animations.find(
        (candidate) => candidate.name === name,
      );
      if (clip) actions.set(name, mixer.clipAction(clip));
    }
    this.world.add(root);
    return {
      root,
      mixer,
      actions,
      groundContacts,
      scale,
      active: undefined,
      called: false,
      scripted: false,
    };
  }

  private placeShadow(
    slot: number,
    pos: Vec2,
    height: number,
    heading: number,
    width: number,
    length: number,
  ): void {
    const probe = this.shadowProbe;
    probe.x = pos.x;
    probe.z = pos.z - 0.08;
    const before = groundHeight(this.level.road, probe);
    probe.z = pos.z + 0.08;
    const after = groundHeight(this.level.road, probe);
    this.stamp.position.set(pos.x, height + 0.033, pos.z);
    this.stamp.rotation.set(-Math.atan2(after - before, 0.16), heading, 0);
    this.stamp.scale.set(width, 1, length);
    this.stamp.updateMatrix();
    this.shadows.setMatrixAt(slot, this.stamp.matrix);
  }

  resetFlightView(): void {
    this.camera.reset(true);
    this.roadArt.reset();
    this.frameOffset = 0;
    this.hasView = false;
    for (const entry of this.deer) {
      entry.mixer.stopAllAction();
      entry.active = undefined;
      entry.called = false;
      entry.scripted = false;
    }
  }

  render(
    previous: ReindeerState,
    current: ReindeerState,
    alpha: number,
    delta: number,
    settings: InputSettings,
    landing: number,
    landingCompanion?: string,
  ): void {
    const canvas = this.renderer.domElement;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    const ratio = Math.min(devicePixelRatio, settings.low ? 1 : 1.7);
    if (
      width !== this.size.width ||
      height !== this.size.height ||
      ratio !== this.size.ratio
    ) {
      this.renderer.setDrawingBufferSize(width, height, ratio);
      Object.assign(this.size, { width, height, ratio });
    }
    this.terrain.update(settings.low);
    this.season.update(settings.low);
    this.routes.update(current.tick);
    const damp =
      sampleReindeerDust(
        this.level,
        current.tick,
        current.actors[0]?.pos ?? this.level.spawn,
      ).strain > 0;
    const air = atmosphere.get(current.segmentId);
    const colorBlend =
      !this.hasView || settings.reduced ? 1 : 1 - Math.exp(-4 * delta);
    this.sky.lerp(
      this.frameColor.set(damp ? "#d8c4a9" : (air?.sky ?? winterAir)),
      colorBlend,
    );
    this.sun.color.lerp(
      this.frameColor.set(air?.light ?? "#ffecd8"),
      colorBlend,
    );
    this.fog.color.copy(this.sky);
    this.fog.far = lerp(
      this.fog.far,
      damp && !settings.reduced ? 145 : 174,
      colorBlend,
    );
    const vehicleOffset = hazardOffset(
      this.vehicle,
      lerp(previous.tick, current.tick, alpha),
    );
    this.car.position.x = vehicleOffset.x;
    this.car.position.z = vehicleOffset.z;
    const heading = vehicleDirection(this.vehicle, current.tick);
    for (const [direction, lamps] of this.headlights)
      lamps.visible = direction === heading;
    const lead = current.actors[0];
    if (!lead) return;
    const companion = current.actors.find(({ id }) => id === landingCompanion);
    const scripted = landing > 0;
    const endingTime = landing * 3.35;
    const callTime = companion && !settings.reduced ? landingCallTime : 0;
    const greeting = scripted && endingTime < callTime;
    const settleTime = Math.max(0, endingTime - callTime);
    this.roadArt.update(current.actors, delta, settings.reduced);
    let hoofShadow = this.deer.length;
    for (const [index, actor] of current.actors.entries()) {
      const entry = this.deer[index];
      if (!entry) continue;
      const before = previous.actors[index] ?? actor;
      const pos = {
        x: lerp(before.pos.x, actor.pos.x, alpha),
        z: lerp(before.pos.z, actor.pos.z, alpha),
      };
      const y = groundHeight(this.level.road, pos);
      entry.root.position.set(pos.x, y, pos.z);
      const headed =
        before.heading + angleDelta(before.heading, actor.heading) * alpha;
      const settle =
        settings.reduced && scripted
          ? 1
          : MathUtils.smoothstep(settleTime, 0.28, 1.65);
      const callActor = greeting && (index === 0 || actor.id === companion?.id);
      const turnToTail =
        greeting && index === 0 && companion
          ? angleDelta(
              headed,
              Math.atan2(companion.pos.x - pos.x, companion.pos.z - pos.z),
            ) *
            MathUtils.smoothstep(endingTime, 0, 0.32) *
            (1 - MathUtils.smoothstep(endingTime, 0.56, callTime))
          : 0;
      entry.root.rotation.y =
        headed + turnToTail + (index % 2 ? -0.11 : 0.09) * settle;
      const { scale } = entry;
      this.placeShadow(
        index,
        pos,
        y,
        entry.root.rotation.y,
        (0.61 + settle * 0.19) * scale,
        1.17 * scale,
      );
      const waiting = index === 0 && current.waitTicks > 0;
      if (!waiting) entry.called = false;
      const call = entry.actions.get("Call");
      const calling =
        waiting &&
        actor.speed === 0 &&
        (!entry.called || (entry.active === "Call" && call?.isRunning()));
      const name: ClipName = scripted
        ? greeting
          ? callActor
            ? "Call"
            : "Idle"
          : "Settle"
        : calling
          ? "Call"
          : actor.speed > 3.55
            ? "Run"
            : actor.speed > 0.14
              ? "Walk"
              : "Idle";
      const action = entry.actions.get(name);
      if (name !== entry.active || entry.scripted !== scripted) {
        if (scripted) {
          entry.mixer.stopAllAction();
          if (action) {
            action.reset().setLoop(LoopOnce, 1).play();
            action.clampWhenFinished = true;
            action.paused = true;
          }
        } else {
          const fade = name === "Call" ? 0.1 : 0.19;
          if (entry.active) entry.actions.get(entry.active)?.fadeOut(fade);
          action?.reset().fadeIn(fade).play();
          if (name === "Call") {
            entry.called = true;
            if (action) {
              action.setLoop(LoopOnce, 1);
              action.clampWhenFinished = true;
            }
          }
        }
        entry.active = name;
        entry.scripted = scripted;
      }
      if (name === "Walk" || name === "Run")
        action?.setEffectiveTimeScale(
          clamp(
            actor.speed / (name === "Run" ? REINDEER.run : REINDEER.cruise),
            0.28,
            1.4,
          ),
        );
      if (scripted && action) {
        const duration = action.getClip().duration;
        const delay = index === 0 ? 0 : landingReplyDelay;
        action.time =
          name === "Call"
            ? clamp((endingTime - delay) / (callTime - delay)) * duration
            : name === "Settle"
              ? settings.reduced
                ? duration
                : clamp(settleTime - Math.min(index, 8) * 0.047, 0, duration)
              : 0;
        entry.mixer.update(0);
      } else if (current.phase === "playing") {
        entry.mixer.update(delta);
      }
      if (entry.groundContacts.length) {
        entry.root.updateWorldMatrix(false, true);
        for (const contact of entry.groundContacts) {
          this.hoof.setFromMatrixPosition(contact.matrixWorld);
          const floor = groundHeight(this.level.road, this.hoof);
          const contactSize =
            1 - MathUtils.smoothstep(this.hoof.y - floor, 0.06, 0.24);
          if (contactSize > 0.02)
            this.placeShadow(
              hoofShadow++,
              this.hoof,
              floor,
              entry.root.rotation.y,
              0.17 * contactSize * scale,
              0.22 * contactSize * scale,
            );
        }
      }
    }
    this.shadows.count = hoofShadow;
    this.shadows.instanceMatrix.needsUpdate = true;
    const aspect = width / height;
    const target = this.deer[0]?.root.position;
    if (!target) return;
    const [first, second] = this.choices.get(current.segmentId) ?? [];
    let span = 37;
    let offset = 0;
    if (first && second && !landing && this.camera.mode !== "Explore") {
      const entry = Math.min(first.z, second.z);
      const leadIn = current.segmentId === "R2" ? 45 : 30;
      const approach =
        MathUtils.smoothstep(target.z, entry - leadIn, entry - 9) *
        (1 - MathUtils.smoothstep(target.z, entry, entry + 12));
      const left = Math.min(target.x, first.x, second.x);
      const right = Math.max(target.x, first.x, second.x);
      offset = ((left + right) * 0.5 - target.x) * approach;
      span = lerp(
        span,
        clamp((right - left + 25) / aspect, span, 60),
        approach,
      );
    }
    this.frameOffset = lerp(
      this.frameOffset,
      offset,
      !this.hasView || settings.reduced ? 1 : 1 - Math.exp(-8 * delta),
    );
    const authoredView = this.camera.mode !== "Explore" && !landing;
    const { road, spawn } = this.level;
    const winterOpening =
      authoredView && current.segmentId === "R0"
        ? 1 - MathUtils.smoothstep(target.z, spawn.z + 6, spawn.z + 27)
        : 0;
    const roadApproach =
      authoredView && current.segmentId === "R1"
        ? MathUtils.smoothstep(target.z, road.near - 31, road.near - 18) *
          (1 - MathUtils.smoothstep(target.z, road.culvert.near, road.near))
        : 0;
    const springOverlook =
      authoredView && this.overlook && current.segmentId === "R4"
        ? 1 - MathUtils.smoothstep(Math.abs(target.z - this.overlook.z), 5, 20)
        : 0;
    span += -1.5 * winterOpening + 4 * roadApproach + 3 * springOverlook;
    const center = {
      x: target.x + this.frameOffset + 12 * roadApproach + 6 * springOverlook,
      z: target.z - 4 * winterOpening + 3 * roadApproach + 5 * springOverlook,
    };
    if (landing && !this.hasView)
      this.camera.update(
        center,
        target.y + 1.6,
        aspect,
        delta,
        settings,
        false,
        0,
        this.clearance,
        span,
      );
    this.hasView = true;
    this.camera.update(
      center,
      target.y + 1.6,
      aspect,
      delta,
      settings,
      false,
      landing
        ? {
            progress: landing,
            framing: {
              span: 34,
              padding: 5,
              lookAhead: 16,
              defaultYawOffsetDegrees: 22,
              defaultPitchDegrees: 22,
            },
            birds: this.deer.map(({ root }) => root.position),
          }
        : 0,
      this.clearance,
      span,
    );
    this.renderer.render(this.world, this.camera.camera);
  }

  project(
    pos: Vec2,
    roadSurface = false,
    teammate = false,
  ): { x: number; y: number; edge: boolean; angle: number } {
    const screen = this.marker
      .set(
        pos.x,
        (roadSurface ? 0 : groundHeight(this.level.road, pos)) + 2.6,
        pos.z,
      )
      .project(this.camera.camera);
    const x = (screen.x + 1) * 50;
    const y = (1 - screen.y) * 50;
    const bottom = teammate ? 92 : 79;
    return {
      x: clamp(x, 8, 92),
      y: clamp(y, 31, bottom),
      edge: x < 8 || x > 92 || y < 31 || y > bottom,
      angle: (Math.atan2(y - 55, x - 50) * 180) / Math.PI,
    };
  }

  sceneryReport(): Record<string, string> {
    return {
      winter: "watercolor",
      road: "cutaway",
      deer: this.assets ? "RD-CHR-001" : "graybox",
    };
  }

  dispose(): void {
    for (const deer of this.deer) deer.mixer.stopAllAction();
    const geometries = new Set<Mesh["geometry"]>();
    const materials = new Set<Material>();
    const skeletons = new Set<SkinnedMesh["skeleton"]>();
    this.world.traverse((object: Object3D) => {
      if (!(object instanceof Mesh)) return;
      if (object instanceof InstancedMesh) object.dispose();
      if (object instanceof SkinnedMesh) skeletons.add(object.skeleton);
      geometries.add(object.geometry);
      for (const material of Array.isArray(object.material)
        ? object.material
        : [object.material])
        materials.add(material);
    });
    for (const item of geometries) item.dispose();
    for (const item of materials) item.dispose();
    for (const skeleton of skeletons) skeleton.dispose();
    this.assets?.scene.traverse((node) => {
      if (node instanceof SkinnedMesh) node.skeleton.dispose();
    });
    this.world.clear();
  }
}
