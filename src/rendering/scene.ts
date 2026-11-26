import {
  AnimationMixer,
  type AnimationAction,
  type AnimationClip,
  AmbientLight,
  Box3,
  Color,
  DirectionalLight,
  FogExp2,
  Group,
  InstancedMesh,
  type MeshStandardMaterial,
  Object3D,
  Quaternion,
  Mesh,
  Scene,
  SkinnedMesh,
  SRGBColorSpace,
  TextureLoader,
  Vector3,
  WebGLRenderer,
  type Texture,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";
import { STEP_SEC } from "../core/clock";
import type { GooseState } from "../core/game";
import { angleDelta, clamp, lerp, type Vec2 } from "../core/math";
import type { InputSettings } from "../input/input";
import type { LevelSchema } from "../levels/schema";
import { GOOSE } from "../simulation/goose";
import { CameraDirector } from "./camera";
import { prepareGoosePlumage, useGooseCompanionPlumage } from "./goose-plumage";
import { GooseShadows } from "./goose-shadows";
import { LandingRipples, sampleLandingPose } from "./landing";
import { buildLandscape, type Landscape } from "./landscape";
import { MigrationAtmosphere, migrationSun } from "./migrationAtmosphere";
import { flightHeight } from "../simulation/air-encounters";
import { buildAirEncounters } from "./air-encounters";
import { RescueRing } from "./rescueRing";
import { FlightScenery } from "./scenery";

export async function loadFlightAssets(): Promise<FlightAssets> {
  const response = await fetch(
    `${import.meta.env.BASE_URL}assets/manifest.json`,
  );
  if (!response.ok) throw new Error(`素材清单 HTTP ${response.status}`);
  const manifest = (await response.json()) as {
    version: number;
    assets: { assetId: string; url: string; clips: string[] }[];
    images: { assetId: string; url: string }[];
    scenery: { assetId: string; url: string }[];
  };
  const asset = manifest.assets.find((item) => item.assetId === "ANM-001");
  if (manifest.version !== 1 || !asset) throw new Error("找不到雁群模型");
  const sky = manifest.images.find(
    (item) => item.assetId === "goose_scene_wet_sky",
  );
  if (!sky) throw new Error("找不到晨雾湿地天空素材");
  const loader = new GLTFLoader();
  const [loaded, skyPigment] = await Promise.all([
    Promise.all(
      manifest.assets
        .filter((entry) => entry.url.startsWith("goose/"))
        .map(async (entry) => ({
          entry,
          gltf: await loader.loadAsync(
            `${import.meta.env.BASE_URL}assets/${entry.url}`,
          ),
        })),
    ),
    new TextureLoader()
      .loadAsync(`${import.meta.env.BASE_URL}assets/${sky.url}`)
      .catch(() => {
        throw new Error("无法加载晨雾湿地天空素材");
      }),
  ]);
  skyPigment.colorSpace = SRGBColorSpace;
  const base = loaded.find((item) => item.entry === asset)?.gltf.scene;
  if (!base) throw new Error("找不到雁群骨架");
  const clips = new Map(
    loaded.flatMap(({ entry, gltf }) =>
      entry.clips.map((name) => {
        const clip = gltf.animations.find(
          (animation) => animation.name === name,
        );
        if (!clip) throw new Error(`找不到动画 ${name}`);
        return [name, clip] as const;
      }),
    ),
  );
  // The glide clip holds the shoulders steady. Sweep each forewing back on
  // the authored elbow axis for the short, individual close-pass reaction.
  const tucked = clips.get("Glide_Loop")?.clone();
  if (tucked) {
    tucked.name = "Close_Pass_Tuck";
    const q = new Quaternion(),
      axis = new Vector3(0, 0, 1);
    for (const track of tucked.tracks) {
      const side = /^Elbow([LR])\.quaternion$/.exec(track.name)?.[1];
      if (!side) continue;
      const fold = new Quaternion().setFromAxisAngle(
        axis,
        side === "L" ? 0.65 : -0.65,
      );
      for (let i = 0; i < track.values.length; i += 4)
        q.fromArray(track.values, i).multiply(fold).toArray(track.values, i);
    }
    clips.set(tucked.name, tucked);
  }
  const size = new Box3().setFromObject(base).getSize(new Vector3());
  return {
    model: base,
    companionBody: prepareGoosePlumage(base),
    clips,
    scale: 5.4 / Math.max(size.x, size.z),
    skyPigment,
    scenery: new Map(
      manifest.scenery.map((entry) => [
        entry.assetId,
        `${import.meta.env.BASE_URL}assets/${entry.url}`,
      ]),
    ),
  };
}

export interface FlightAssets {
  readonly model: Group;
  readonly companionBody: MeshStandardMaterial | undefined;
  readonly clips: ReadonlyMap<string, AnimationClip>;
  readonly scale: number;
  readonly skyPigment: Texture;
  readonly scenery: ReadonlyMap<string, string>;
}

export interface Projected {
  readonly x: number;
  readonly y: number;
  readonly edge: boolean;
  readonly angle: number;
}

const LOOPING_POSES = new Set([
  "Cruise_Flap_Loop",
  "Formation_Blend",
  "Glide_Loop",
  "Circle_Loop",
  "Close_Pass_Tuck",
  "Call_Loop",
]);

export class FlightScene {
  readonly camera = new CameraDirector();
  readonly renderer: WebGLRenderer;
  private readonly scene = new Scene();
  private readonly backdrop = new Color();
  private readonly haze = new FogExp2(0xffffff);
  private readonly atmosphere = new MigrationAtmosphere();
  private airScenes?: ReturnType<typeof buildAirEncounters>;
  private landscape: Landscape | undefined;
  private scenery: FlightScenery | undefined;
  private level: LevelSchema | undefined;
  private readonly landingRipples = new LandingRipples(GOOSE.size);
  private readonly shadows = new GooseShadows(GOOSE.size);
  private readonly rescueRing = new RescueRing();
  private flockPositions: Vector3[] = [];
  private flock: {
    root: Group;
    model: Object3D;
    size: number;
    mixer: AnimationMixer;
    actions: Map<string, AnimationAction>;
    animationTime: number | undefined;
    landingEntry:
      | {
          readonly terrain: number;
          readonly height: number;
          readonly bank: number;
          readonly weights: ReadonlyMap<string, number>;
        }
      | undefined;
    rejoinStarted: number | undefined;
    phase: number;
  }[] = [];
  private firstAirborneTime: number | undefined;
  private low: boolean | undefined;
  private readonly screen = { width: 0, height: 0, pixelRatio: 0 };

  constructor(
    private readonly canvas: HTMLCanvasElement,
    context: WebGL2RenderingContext,
    private readonly terrainCoverage = false,
  ) {
    this.renderer = new WebGLRenderer({ canvas, context, antialias: true });
    this.scene.background = this.backdrop;
    this.scene.fog = this.haze;
    const sun = new DirectionalLight("#fff2d5", 2.1);
    sun.position.copy(migrationSun);
    this.scene.add(
      sun,
      new AmbientLight("#dae9f4", 1.3),
      this.shadows.mesh,
      this.landingRipples.mesh,
      this.rescueRing.mesh,
      this.atmosphere.sky,
    );
  }

  setLevel(level: LevelSchema, goose: FlightAssets, low: boolean): void {
    this.level = level;
    const migration = level.id === "migration";
    this.atmosphere.sky.visible = migration && !this.terrainCoverage;
    this.atmosphere.setPigment(goose.skyPigment);
    this.backdrop.set(migration ? "#d7d9c3" : "#bfc8af");
    this.haze.color.copy(this.backdrop);
    this.haze.density = migration ? 0.0042 : 0.0065;
    if (!this.scenery) {
      this.scenery = new FlightScenery(goose.scenery, new GLTFLoader());
      this.scene.add(this.scenery.group);
    }
    this.setLandscape(low);
    for (const bird of this.flock) {
      bird.mixer.stopAllAction();
      bird.mixer.uncacheRoot(bird.model);
      bird.model.traverse((node) => {
        if (node instanceof SkinnedMesh) node.skeleton.dispose();
      });
      bird.root.removeFromParent();
    }
    this.flock = Array.from({ length: GOOSE.size }, (_, i) => {
      const root = new Group();
      const model = clone(goose.model);
      if (i > 0 && goose.companionBody)
        useGooseCompanionPlumage(model, goose.companionBody);
      const size = i === 0 ? 1.12 : 0.83 + (i % 4) * 0.037;
      model.rotation.y = Math.PI;
      model.scale.setScalar(goose.scale * size);
      const mixer = new AnimationMixer(model);
      const actions = new Map(
        [...goose.clips].map(([name, clip]) => {
          const action = mixer.clipAction(clip).play();
          action.enabled = false;
          return [name, action] as const;
        }),
      );
      root.add(model);
      this.scene.add(root);
      return {
        root,
        model,
        size,
        mixer,
        actions,
        animationTime: undefined,
        landingEntry: undefined,
        rejoinStarted: undefined,
        phase: i * 0.127,
      };
    });
    this.flockPositions = this.flock.map(({ root }) => root.position);
    this.resetFlightView();
  }

  resetFlightView(): void {
    this.firstAirborneTime = undefined;
    for (const bird of this.flock) {
      bird.animationTime = undefined;
      bird.landingEntry = undefined;
      bird.rejoinStarted = undefined;
    }
    this.camera.reset(true);
  }

  private setLandscape(low: boolean): void {
    if (
      !this.level ||
      (low === this.low && this.landscape?.group.userData.level === this.level)
    )
      return;
    this.scenery?.reset();
    if (this.landscape) {
      const geometries = new Set<Mesh["geometry"]>();
      const materials = new Set<Mesh["material"]>();
      this.landscape.group.traverse((child) => {
        if (child instanceof InstancedMesh) child.dispose();
        if ("geometry" in child && "material" in child) {
          const object = child as Mesh;
          geometries.add(object.geometry);
          materials.add(object.material);
        }
      });
      for (const geometry of geometries) geometry.dispose();
      for (const material of materials) {
        if (Array.isArray(material)) material.forEach((item) => item.dispose());
        else material.dispose();
      }
      this.landscape.group.removeFromParent();
    }
    this.low = low;
    this.landscape = buildLandscape(
      this.level,
      low,
      this.atmosphere.surfaceUniforms,
    );
    this.airScenes = this.level.encounters
      ? buildAirEncounters(
          this.level.encounters,
          this.landscape.height ?? (() => 0),
        )
      : undefined;
    if (this.airScenes) this.landscape.group.add(this.airScenes.group);
    this.landscape.group.userData.level = this.level;
    this.scene.add(this.landscape.group);
  }

  render(
    previous: GooseState,
    current: GooseState,
    alpha: number,
    delta: number,
    options: InputSettings,
    landing: number,
  ): void {
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    if (!width || !height || this.renderer.getContext().isContextLost()) return;
    const pixelRatio = Math.min(window.devicePixelRatio, options.low ? 1 : 2);
    if (
      width !== this.screen.width ||
      height !== this.screen.height ||
      pixelRatio !== this.screen.pixelRatio
    ) {
      this.renderer.setDrawingBufferSize(width, height, pixelRatio);
      Object.assign(this.screen, { width, height, pixelRatio });
    }
    this.setLandscape(options.low);
    this.landscape?.setLanding?.(landing);
    this.landscape?.setGustTick?.(current.tick);
    this.rescueRing.update(current, this.landscape?.height);
    const animationTime = lerp(previous.tick, current.tick, alpha) * STEP_SEC;
    if (current.airborne && this.firstAirborneTime === undefined) {
      this.firstAirborneTime = animationTime > 3 ? -10 : animationTime;
    }
    if (current.encounters)
      this.airScenes?.update(
        current.encounters,
        animationTime / STEP_SEC,
        current.actors[0]?.pos.z ?? 0,
      );
    const airborneTime =
      animationTime - (this.firstAirborneTime ?? animationTime);
    const formationBlend = lerp(previous.formation, current.formation, alpha);
    const poseBlend = 1 - Math.exp(-17 * delta);
    const flightBlend = 1 - Math.exp(-12 * delta);
    const landingFrame =
      current.phase === "landing" || current.phase === "completed";
    const groundHeight = this.landscape?.height;
    this.landingRipples.begin();
    current.actors.forEach((actor, index) => {
      const bird = this.flock[index];
      if (!bird) return;
      const before = previous.actors[index] ?? actor;
      const x = lerp(before.pos.x, actor.pos.x, alpha);
      const z = lerp(before.pos.z, actor.pos.z, alpha);
      const terrain = groundHeight?.(x, z) ?? 0;
      const headingChange = angleDelta(before.heading, actor.heading);
      const targetY = lerp(
        flightHeight(before, index, previous.airborne),
        flightHeight(actor, index, current.airborne),
        alpha,
      );
      const direct = options.reduced || bird.animationTime === undefined;
      const entry = landingFrame
        ? (bird.landingEntry ??= {
            terrain,
            height:
              bird.animationTime === undefined ? targetY : bird.root.position.y,
            bank: bird.root.rotation.z,
            weights: new Map(
              [...bird.actions].map(([name, action]) => [name, action.weight]),
            ),
          })
        : undefined;
      const landingPose =
        entry &&
        sampleLandingPose(
          landing,
          index,
          entry.height,
          bird.model.scale.x,
          entry.terrain,
          options.reduced,
        );
      const y =
        landingPose?.height ??
        (direct ? targetY : lerp(bird.root.position.y, targetY, flightBlend));
      bird.root.position.set(x, y, z);
      bird.root.rotation.y = before.heading + headingChange * alpha;
      const bank = options.reduced ? 0 : clamp(headingChange * 9, -0.4, 0.4);
      bird.root.rotation.z =
        landingPose && entry
          ? options.reduced
            ? 0
            : entry.bank * (1 - landingPose.contact)
          : direct
            ? bank
            : lerp(bird.root.rotation.z, bank, flightBlend);
      this.shadows.set(
        index,
        bird.root.position,
        bird.root.rotation.y,
        bird.size,
        landingPose?.surface ?? Math.max(0, terrain),
        landingPose?.contact ?? (current.airborne ? 0 : 1),
        groundHeight,
      );
      if (landingPose && current.phase === "landing")
        this.landingRipples.add(x, z, landingPose.ripple, bird.root.rotation.y);
      let pose = "Cruise_Flap_Loop";
      let localTime = 0;
      if (actor.status !== "rejoining") bird.rejoinStarted = undefined;
      if (landingPose) {
        pose = landingPose.clip;
        localTime = landingPose.seconds;
      } else if (!current.airborne) {
        pose = "Land_ShallowWater";
        localTime = 5;
      } else if (actor.status === "strayed") {
        pose = "Call_Loop";
      } else if (actor.status === "rejoining" && !options.reduced) {
        bird.rejoinStarted ??= animationTime;
        localTime = animationTime - bird.rejoinStarted;
        if (localTime < (bird.actions.get("Rejoin")?.getClip().duration ?? 0))
          pose = "Rejoin";
      } else if (!options.reduced && airborneTime < 1.5) {
        pose = "Takeoff_Climb";
        localTime = Math.max(0, airborneTime - bird.phase * 0.11);
      } else if (current.encounters?.wingAt[actor.id] !== undefined) {
        pose = "Close_Pass_Tuck";
      } else if (index === 0 && current.releasedTicks > 3) {
        pose =
          current.releasedTicks < GOOSE.coastTicks
            ? "Glide_Loop"
            : "Circle_Loop";
      }
      const cursorDelta = Math.max(
        0,
        animationTime - (bird.animationTime ?? animationTime),
      );
      for (const [name, action] of bird.actions) {
        const target =
          pose === "Cruise_Flap_Loop" && name === "Formation_Blend"
            ? formationBlend
            : pose === name
              ? pose === "Cruise_Flap_Loop"
                ? 1 - formationBlend
                : 1
              : 0;
        const weight =
          landingPose && entry
            ? lerp(entry.weights.get(name) ?? 0, target, landingPose.weight)
            : direct
              ? target
              : lerp(action.weight, target, poseBlend);
        action.enabled = weight > 0.006;
        if (action.enabled) {
          const duration = action.getClip().duration;
          // Both sides of a fade keep animating at the current flight phase.
          const cursor = LOOPING_POSES.has(name)
            ? ((options.reduced ? 0 : animationTime) + bird.phase) % duration
            : name === pose
              ? localTime
              : action.time + cursorDelta;
          action.time = Math.min(duration - 0.0001, cursor);
        }
        action.setEffectiveWeight(weight);
      }
      bird.animationTime = animationTime;
      bird.mixer.update(0);
    });
    this.shadows.finish(current.actors.length);
    this.landingRipples.finish();
    const leader = this.flock[0]?.root.position;
    if (!leader) return;
    const focus = current.segmentId === "S2" || current.segmentId === "S4";
    this.camera.update(
      leader,
      leader.y,
      width / height,
      delta,
      options,
      focus,
      landingFrame ? { progress: landing, birds: this.flockPositions } : 0,
      this.landscape?.orbitClearance,
    );
    if (this.landscape && this.level) {
      if (this.level.id === "migration") {
        this.atmosphere.update(leader.z, width / height, options.low);
        const { horizon } = this.atmosphere.surfaceUniforms;
        this.haze.color.copy(horizon.value);
        this.backdrop.copy(horizon.value);
      }
      this.scenery?.update(
        this.level,
        this.landscape,
        current,
        leader.z,
        options.low,
        options.reduced,
      );
      this.landscape.wind.position.y = options.reduced
        ? 0
        : Math.sin(animationTime * 0.75) * 0.22;
    }
    this.renderer.render(this.scene, this.camera.camera);
  }

  sceneryReport(): Record<string, string> | undefined {
    return this.scenery?.report();
  }

  project(pos: Vec2, height = 4): Projected {
    const screen = new Vector3(pos.x, height, pos.z).project(
      this.camera.camera,
    );
    const rawX = (screen.x + 1) * 50;
    const rawY = (1 - screen.y) * 50;
    const edge = rawX < 8 || rawX > 92 || rawY < 36 || rawY > 79;
    return {
      x: clamp(rawX, 8, 92),
      y: clamp(rawY, 36, 79),
      edge,
      angle: (Math.atan2(rawY - 56, rawX - 50) * 180) / Math.PI,
    };
  }
}
