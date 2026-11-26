import {
  BufferGeometry,
  HemisphereLight,
  Color,
  ConeGeometry,
  DirectionalLight,
  DoubleSide,
  Float32BufferAttribute,
  FogExp2,
  Group,
  InstancedMesh,
  LineSegments,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Object3D,
  RingGeometry,
  Scene,
  ShaderMaterial,
  SkinnedMesh,
  SphereGeometry,
  Vector2,
  Vector3,
  WebGLRenderer,
  type Material,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";
import { STEP_SEC } from "../core/clock";
import type { GameState } from "../core/game";
import { angleDelta, clamp, lerp, type Vec2 } from "../core/math";
import type { InputSettings } from "../input/input";
import type { WhaleLevel } from "../levels/schema";
import {
  canRideCurrent,
  hasVisibleDrift,
  type WaterCurrent,
} from "../levels/whale-current";
import { WHALE } from "../simulation/whale-motion";
import { CameraDirector } from "./camera";
import type { Projected } from "./scene";
import { WHALE_DEPTH_Y, WhaleCourse } from "./whale-course";
import { WhaleGathering } from "./whale-gathering";
import { WhaleOcean, type WhaleBayLight } from "./whale-ocean";
import { WhaleReef, type ReefView } from "./whale-reef";
import { hasWhaleSwimRig, WhaleSwim } from "./whale-swim";
import { whaleWaterLight } from "./whale-water-light";

const MODEL_ID = "WL-CHR-001";
const MODEL_MESH = "Whale_LOD0";
const BAY_SHAPE = "Bay_Silhouette";
const MODEL_SCALE = 0.85;
const SHIPPING_APPROACH_SPAN = 80;
const NET_APPROACH_SPAN = 78;
const OFFSHORE_FOLLOW_SPAN = 61;
const OFFSHORE_GATHERING = { span: 43, padding: 5.2, lookAhead: 0 };
const JUNCTION_PADDING = 23;

export type WhaleAssets =
  | { readonly kind: "graybox" }
  | {
      readonly kind: "model";
      readonly model: Object3D;
      readonly paint: MeshStandardMaterial;
      readonly bayShapeIndex: number;
    };

export async function loadWhaleAssets(graybox = false): Promise<WhaleAssets> {
  if (graybox) return { kind: "graybox" };
  const base = `${import.meta.env.BASE_URL}assets/`;
  const response = await fetch(`${base}manifest.json`);
  if (!response.ok) throw new Error(`鲸素材清单 HTTP ${response.status}`);
  const manifest = (await response.json()) as {
    version?: number;
    assets?: { assetId: string; url: string }[];
  };
  const asset = manifest.assets?.find(({ assetId }) => assetId === MODEL_ID);
  if (manifest.version !== 1 || !asset?.url)
    throw new Error(`鲸素材清单缺少 ${MODEL_ID}`);
  try {
    const gltf = await new GLTFLoader().loadAsync(base + asset.url);
    const mesh = gltf.scene.getObjectByName(MODEL_MESH);
    if (!hasWhaleSwimRig(gltf.scene)) throw new Error("缺少鲸游姿所需骨骼");
    if (
      !(mesh instanceof SkinnedMesh) ||
      !(mesh.material instanceof MeshStandardMaterial) ||
      !mesh.material.map
    )
      throw new Error("缺少鲸蒙皮或水彩贴图");
    const bayShapeIndex = mesh.morphTargetDictionary?.[BAY_SHAPE];
    if (bayShapeIndex === undefined || !mesh.morphTargetInfluences)
      throw new Error("缺少海湾鲸轮廓");
    return {
      kind: "model",
      model: gltf.scene,
      paint: mesh.material,
      bayShapeIndex,
    };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`无法载入鲸模型 ${asset.url} · ${detail}`, {
      cause: error,
    });
  }
}

function whaleDepthHeight(depth: number): number {
  const [surface, shallow, deep] = WHALE_DEPTH_Y;
  return depth <= 1
    ? lerp(surface, shallow, clamp(depth))
    : lerp(shallow, deep, clamp(depth - 1));
}

// Every finish shares the same atlas and shader. The lead whale's pale saddle
// and the companions' different fin values still read when their faces are tiny.
type WhaleFinish = readonly [back: string, fin: string, saddle: number];

const WHALE_FINISHES = [
  ["#355367", "#b4cdc2", 0.78],
  ["#354f64", "#8fb3bb", 0.1],
  ["#40566c", "#aabdc6", 0.18],
] as const satisfies readonly WhaleFinish[];

function whalePaint(
  bay: WhaleBayLight,
  time: { value: number },
  finish: WhaleFinish,
  source?: MeshStandardMaterial,
): MeshStandardMaterial {
  const material =
    source?.clone() ??
    new MeshStandardMaterial({
      color: "#528092",
      roughness: 0.88,
    });
  const [back, fin, saddle] = finish;
  const backInk = { value: new Color(back) };
  const finPaper = { value: new Color(fin) };
  const saddleStrength = { value: source ? saddle : 0 };
  material.onBeforeCompile = (shader) => {
    shader.uniforms.bayArt = bay.amount;
    shader.uniforms.viewDive = bay.depth;
    shader.uniforms.skinTime = time;
    shader.uniforms.backInk = backInk;
    shader.uniforms.finPaper = finPaper;
    shader.uniforms.saddleStrength = saddleStrength;
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        `#include <common>
        varying vec3 skinWorld;
        varying vec3 skinPigment;
        varying float skinDistance;`,
      )
      .replace(
        "#include <project_vertex>",
        `
        #include <project_vertex>
        skinWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;
        skinPigment = position;
        skinDistance = -mvPosition.z;
      `,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>
        varying vec3 skinWorld;
        varying vec3 skinPigment;
        varying float skinDistance;
        uniform float bayArt;
        uniform float viewDive;
        uniform float skinTime;
        uniform vec3 backInk;
        uniform vec3 finPaper;
        uniform float saddleStrength;
        ${whaleWaterLight}`,
      )
      .replace(
        "#include <opaque_fragment>",
        `
        // Read the pigment in the bind pose so it travels with the animated skin.
        float across = abs(skinPigment.x);
        float along = skinPigment.z;
        float crest = smoothstep(0.16, 1.06, skinPigment.y);
        float shoulder = smoothstep(-4.62, -3.7, along) * (1.0 - smoothstep(2.0, 4.1, along));
        float marbling = 0.5 + 0.5 * sin(along * 2.65 + skinPigment.x)
                         * sin(skinPigment.x * 3.1 - along * 1.4);
        float pectoral = smoothstep(1.45, 3.2, across) * (1.0 - smoothstep(1.8, 2.6, abs(along + 0.75)));
        float fluke = smoothstep(0.80, 2.55, across) * smoothstep(4.3, 5.2, along);
        vec3 pigment = mix(outgoingLight, backInk, shoulder * crest * (0.39 + marbling * 0.11));
        pigment = mix(pigment, finPaper, max(pectoral * 0.38, fluke * 0.55));
        float saddleAcross = abs(skinPigment.x + 0.16 * sin(along * 2.3));
        float saddleAlong = smoothstep(-3.76, -2.90, along) * (1.0 - smoothstep(-1.50, -0.52, along));
        float saddle = (1.0 - smoothstep(0.30, 0.92, saddleAcross)) * saddleAlong * crest;
        pigment = mix(pigment, finPaper, saddle * saddleStrength * (0.7 + 0.3 * marbling));

        float below = max(0.0, -skinWorld.y);
        float shallowGlow = smoothstep(0.20, 1.03, below) * (1.0 - smoothstep(2.9, 5.3, below));
        pigment += vec3(0.049, 0.097, 0.077)
                   * whaleRefractedLight(skinWorld, skinTime) * shallowGlow * crest;
        vec3 bayPigment = pigment * vec3(0.79, 0.90, 1.02) + vec3(0.022, 0.028, 0.037) * crest;
        pigment = mix(pigment, bayPigment, bayArt);
        outgoingLight = whaleThroughWater(pigment, skinWorld.y, skinDistance, viewDive, 0.80);
        float deepView = smoothstep(1.18, 1.95, viewDive);
        float rim = pow(1.0 - abs(dot(normal, normalize(vViewPosition))), 2.0);
        outgoingLight += vec3(0.055, 0.088, 0.12) * deepView * rim;
        float waterline = 1.0 - smoothstep(0.035, 0.18, abs(skinWorld.y));
        outgoingLight += vec3(0.085, 0.125, 0.13) * waterline;
        #include <opaque_fragment>
      `,
      );
  };
  return material;
}

function grayboxWhale(material: Material): Group {
  const model = new Group();
  const body = new Mesh(new SphereGeometry(1, 16, 12), material);
  body.scale.set(0.78, 0.57, 2.13);
  body.position.z = -0.52;
  const stock = new Mesh(new SphereGeometry(1, 10, 8), material);
  stock.scale.set(0.37, 0.25, 1.07);
  stock.position.z = 1.17;
  const tail = new Group();
  tail.name = "TailStock";
  tail.position.z = 1.85;
  for (const side of [-1, 1]) {
    const fluke = new Mesh(new SphereGeometry(1, 10, 6), material);
    fluke.scale.set(1, 0.14, 0.46);
    fluke.position.x = 0.65 * side;
    fluke.rotation.y = side * 0.35;
    tail.add(fluke);
    const fin = new Mesh(new SphereGeometry(1, 10, 6), material);
    fin.scale.set(0.82, 0.12, 0.36);
    fin.position.set(0.73 * side, -0.21, -0.49);
    fin.rotation.y = side * 0.41;
    model.add(fin);
  }
  const dorsal = new Mesh(new ConeGeometry(0.3, 0.57, 5), material);
  dorsal.position.set(0, 0.53, 0.21);
  dorsal.rotation.x = 0.27;
  model.add(body, stock, tail, dorsal);
  return model;
}

function reefWakes(): InstancedMesh {
  const vertices = [-1, 1].flatMap((side) => [
    0.74 * side,
    0,
    -2.8,
    1.25 * side,
    0,
    -3.7,
    1.78 * side,
    0,
    -8.3,
    0.97 * side,
    0,
    -5.5,
  ]);
  const geometry = new BufferGeometry().setAttribute(
    "position",
    new Float32BufferAttribute(vertices, 3),
  );
  geometry.setIndex([0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7]);
  const wake = new InstancedMesh(
    geometry,
    new MeshBasicMaterial({
      color: "#c0f5e3",
      opacity: 0.64,
      side: DoubleSide,
      transparent: true,
      depthWrite: false,
    }),
    WHALE.size,
  );
  wake.name = "Reef current wakes";
  wake.renderOrder = 1;
  // The batch follows the actors and travels far beyond its initial bounds.
  wake.frustumCulled = false;
  wake.visible = false;
  return wake;
}

interface WhaleView {
  readonly root: Group;
  readonly model: Object3D;
  readonly morphWeights?: number[];
  readonly swim: WhaleSwim;
  readonly crest: Mesh<RingGeometry, MeshBasicMaterial>;
  readonly rescue: Mesh<RingGeometry, ShaderMaterial>;
  readonly rescueProgress: { value: number };
}

function disposeGeometry(root: Object3D): void {
  const geometries = new Set<BufferGeometry>();
  const materials = new Set<Material>();
  root.traverse((element) => {
    if (element instanceof InstancedMesh) element.dispose();
    if (!(element instanceof Mesh || element instanceof LineSegments)) return;
    geometries.add(element.geometry);
    if (Array.isArray(element.material))
      for (const material of element.material) materials.add(material);
    else materials.add(element.material);
  });
  for (const geometry of geometries) geometry.dispose();
  for (const material of materials) material.dispose();
}

export class WhaleScene {
  readonly species = "whale";
  readonly camera = new CameraDirector();
  readonly renderer: WebGLRenderer;
  private readonly scene = new Scene();
  private readonly ocean: WhaleOcean;
  private readonly course: WhaleCourse;
  private readonly reef: WhaleReef;
  private readonly coastalCurrents: readonly WaterCurrent[];
  private readonly wake = reefWakes();
  private readonly wakeTransform = new Object3D();
  private readonly whales: WhaleView[] = [];
  private readonly crestGeometry = new RingGeometry(0.88, 1, 34).rotateX(
    -Math.PI / 2,
  );
  private readonly rescueGeometry = new RingGeometry(
    WHALE.rescueRadius - 0.27,
    WHALE.rescueRadius + 0.27,
    64,
  ).rotateX(-Math.PI / 2);
  private readonly gathering: WhaleGathering;
  private readonly screen = { width: 0, height: 0, pixelRatio: 0 };
  private readonly ownRenderer: boolean;
  private readonly incomingScreen = new Vector2();
  private readonly incomingPixelRatio: number;
  private readonly paint: {
    leader: MeshStandardMaterial;
    companions: readonly [MeshStandardMaterial, MeshStandardMaterial];
  };
  private readonly paintTime = { value: 0 };
  private readonly junction?: { minX: number; maxX: number; crossing: number };
  private junctionOffset = 0;
  private hasView = false;
  private readonly dredgingWork?: Vec2;
  private readonly watchingCoast?: Vec2;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    level: WhaleLevel,
    private readonly assets: WhaleAssets,
    renderer?: WebGLRenderer,
  ) {
    this.ownRenderer = renderer === undefined;
    this.renderer = renderer ?? new WebGLRenderer({ canvas, antialias: true });
    this.incomingPixelRatio = this.renderer.getPixelRatio();
    this.renderer.getSize(this.incomingScreen);
    this.gathering = new WhaleGathering(
      WHALE.size,
      level.zones.find(({ kind }) => kind === "goal"),
    );
    this.renderer.resetState();
    this.dredgingWork = level.landmarks.find(
      ({ id }) => id === "dredge-works",
    )?.pos;
    this.watchingCoast = level.landmarks.find(
      ({ id }) => id === "watching-coast",
    )?.pos;
    const quiet = level.landmarks.find(({ id }) => id === "quiet-entry");
    const shipping = level.landmarks.find(({ id }) => id === "shipping-entry");
    const gate = level.triggers.find(({ id }) => id === "quiet-gate");
    if (
      quiet &&
      shipping &&
      gate?.kind === "route" &&
      gate.crossingZ !== undefined
    )
      this.junction = {
        minX: Math.min(quiet.pos.x, shipping.pos.x),
        maxX: Math.max(quiet.pos.x, shipping.pos.x),
        crossing: gate.crossingZ,
      };
    this.scene.background = new Color("#b2cacb");
    this.scene.fog = new FogExp2("#b2cacb", 0.0029);
    const sun = new DirectionalLight("#fff0d1", 1.83);
    sun.position.set(-44, 65, 29);
    this.ocean = new WhaleOcean(level);
    const [leader, slate, smoke] = WHALE_FINISHES;
    const pigment = assets.kind === "model" ? assets.paint : undefined;
    const paint = (finish: WhaleFinish) =>
      whalePaint(this.ocean.bayLight, this.paintTime, finish, pigment);
    this.paint = {
      leader: paint(leader),
      companions: [paint(slate), paint(smoke)],
    };
    this.course = new WhaleCourse(level, this.ocean.bayLight);
    this.reef = new WhaleReef(level, this.ocean.bayLight.depth);
    this.coastalCurrents = level.zones.filter(
      (zone): zone is WaterCurrent =>
        zone.kind === "current" && hasVisibleDrift(zone),
    );
    this.scene.add(
      sun,
      new HemisphereLight("#dbeef6", "#638c92", 1.84),
      this.ocean.group,
      this.course.group,
      this.reef.group,
      this.wake,
      this.gathering.mesh,
    );
  }

  private addWhale(index: number): WhaleView {
    const root = new Group();
    const paint =
      index === 0
        ? this.paint.leader
        : this.paint.companions[index % 2 === 0 ? 0 : 1];
    const model =
      this.assets.kind === "model"
        ? clone(this.assets.model)
        : grayboxWhale(paint);
    if (this.assets.kind === "model") {
      model.traverse((node) => {
        if (node instanceof Mesh) node.material = paint;
      });
      model.scale.setScalar(MODEL_SCALE);
    }
    if (index !== 0) model.scale.multiplyScalar(0.83 + 0.035 * (index % 3));
    const swim = new WhaleSwim(model, index);
    const crest = new Mesh(
      this.crestGeometry,
      new MeshBasicMaterial({
        color: "#f9f6db",
        transparent: true,
        opacity: 0.6,
        depthWrite: false,
        side: DoubleSide,
      }),
    );
    crest.renderOrder = 1;
    const rescueProgress = { value: 0 };
    const rescue = new Mesh(
      this.rescueGeometry,
      new ShaderMaterial({
        uniforms: {
          progress: rescueProgress,
          waiting: { value: new Color("#efb977") },
          found: { value: new Color("#f9f6db") },
        },
        side: DoubleSide,
        transparent: true,
        depthWrite: false,
        vertexShader: `
          varying vec2 ring;
          void main() {
            ring = position.xz;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          }
        `,
        fragmentShader: `
          uniform float progress;
          uniform vec3 waiting;
          uniform vec3 found;
          varying vec2 ring;
          void main() {
            float angle = fract(atan(ring.x, ring.y) / 6.2831853 + 1.0);
            float ready = step(angle, progress);
            float dash = 1.0 - smoothstep(0.63, 0.8, fract(angle * 17.0));
            gl_FragColor = vec4(mix(waiting, found, ready), mix(dash * 0.78, 0.92, ready));
            #include <colorspace_fragment>
          }
        `,
      }),
    );
    rescue.renderOrder = 1;
    root.add(model);
    this.scene.add(root, crest, rescue);
    const skin = model.getObjectByName(MODEL_MESH);
    const morphWeights =
      skin instanceof SkinnedMesh ? skin.morphTargetInfluences : undefined;
    const view = {
      root,
      model,
      morphWeights,
      swim,
      crest,
      rescue,
      rescueProgress,
    };
    this.whales.push(view);
    return view;
  }

  resetFlightView(): void {
    this.hasView = false;
    this.junctionOffset = 0;
    this.camera.reset(true);
    this.reef.reset();
    for (const whale of this.whales) whale.swim.reset();
  }

  render(
    previous: GameState,
    current: GameState,
    alpha: number,
    delta: number,
    options: InputSettings,
    landing: number,
    guideBayTurn: boolean,
  ): void {
    if (current.species !== "whale" || previous.species !== "whale") return;
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    if (!width || !height || this.renderer.getContext().isContextLost()) return;
    const pixelRatio = Math.min(window.devicePixelRatio, options.low ? 1 : 2);
    if (
      this.screen.width !== width ||
      this.screen.height !== height ||
      this.screen.pixelRatio !== pixelRatio
    ) {
      this.renderer.setDrawingBufferSize(width, height, pixelRatio);
      Object.assign(this.screen, { width, height, pixelRatio });
    }
    const seconds = lerp(previous.tick, current.tick, alpha) * STEP_SEC;
    this.paintTime.value = options.reduced ? 0 : seconds;
    const landed = current.phase === "landing" || current.phase === "completed";
    const leader = current.actors[0];
    if (!leader) return;
    const viewDepth = lerp(
      previous.actors[0]?.dive.depth ?? leader.dive.depth,
      leader.dive.depth,
      alpha,
    );
    this.course.update(current.tick, landed, guideBayTurn, options, viewDepth);
    this.ocean.update(
      seconds,
      viewDepth,
      leader.pos.z,
      options.low,
      options.reduced,
      landed && options.reduced ? 1 : landing,
    );
    this.reef.update(leader, current.tick, options);
    const bayShapeIndex =
      this.assets.kind === "model" ? this.assets.bayShapeIndex : undefined;
    const coastalCurrents =
      (current.segmentId === "W0" ||
        current.segmentId === "W1" ||
        current.segmentId === "W3") &&
      !landed
        ? this.coastalCurrents
        : undefined;
    let wakeCount = 0;

    for (const [index, actor] of current.actors.entries()) {
      const before = previous.actors[index] ?? actor;
      const whale = this.whales[index] ?? this.addWhale(index);
      if (whale.morphWeights && bayShapeIndex !== undefined)
        whale.morphWeights[bayShapeIndex] = this.ocean.bayLight.amount.value;
      const depth = lerp(before.dive.depth, actor.dive.depth, alpha);
      const direction = actor.dive.direction;
      const active = options.reduced
        ? 0
        : clamp(actor.speed / WHALE.cruise) *
          (landed ? 1 - clamp(landing * 3) : 1);
      const bob = whale.swim.pose(
        before,
        actor,
        alpha,
        seconds,
        current.phase === "playing" ? delta : 0,
        options.reduced,
        landed ? clamp(landing * 3) : 0,
      );
      whale.root.position.set(
        lerp(before.pos.x, actor.pos.x, alpha),
        whaleDepthHeight(depth) + bob,
        lerp(before.pos.z, actor.pos.z, alpha),
      );
      // The model points -Z in glTF while simulation heading zero points +Z.
      whale.root.rotation.y =
        Math.PI +
        before.heading +
        angleDelta(before.heading, actor.heading) * alpha;
      if (
        actor.speed > WHALE.slow &&
        coastalCurrents?.some(
          (zone) =>
            canRideCurrent(zone, actor) &&
            (index > 0 || current.occupied.includes(zone.id)),
        )
      ) {
        this.wakeTransform.position.copy(whale.root.position);
        this.wakeTransform.position.y += 0.11;
        this.wakeTransform.rotation.y = whale.root.rotation.y - Math.PI;
        this.wakeTransform.scale.z = lerp(
          0.68,
          1.16,
          clamp(actor.speed / WHALE.boost),
        );
        this.wakeTransform.updateMatrix();
        this.wake.setMatrixAt(wakeCount++, this.wakeTransform.matrix);
      }
      const surfaced = actor.dive.layer === "surface";
      const strayed = actor.status === "strayed";
      const joining =
        current.segmentId === "W2" && actor.status === "rejoining";
      const identified = strayed || joining;
      const ripple = options.reduced ? 0 : (seconds * 0.45 + index * 0.173) % 1;
      const surfacing =
        direction === "up"
          ? clamp(1 - depth)
          : surfaced && direction === null && actor.dive.breath < 1
            ? 1
            : 0;
      const restingWater =
        current.segmentId === "W0" ||
        (current.segmentId === "W3" &&
          (current.occupied.includes("quiet-rest") ||
            current.occupied.includes("reef-eddy") ||
            current.occupied.includes("dredge-rest"))) ||
        current.segmentId === "W4";
      const breathRipple = restingWater && !landed ? surfacing : 0;
      const drawWake = surfaced && !options.low && active > 0.08 && !landed;
      whale.crest.visible = identified || breathRipple > 0 || drawWake;
      whale.crest.position.copy(whale.root.position);
      whale.crest.position.y = identified
        ? whale.root.position.y + 0.045
        : 0.12;
      if ((drawWake || breathRipple > 0) && !identified) {
        const behind = 2.4;
        whale.crest.position.x -= Math.sin(actor.heading) * behind;
        whale.crest.position.z -= Math.cos(actor.heading) * behind;
        whale.crest.rotation.y = actor.heading;
      }
      const size = identified
        ? 3.3
        : breathRipple > 0
          ? lerp(1.9, 3.05, options.reduced ? 1 : breathRipple)
          : lerp(1.5, 4.1, ripple);
      whale.crest.scale.set(size, 1, size * (identified ? 1 : 1.46));
      whale.crest.material.color.set(
        strayed ? "#ffc88a" : joining ? "#bbebe0" : "#f9f6db",
      );
      whale.crest.material.opacity = strayed
        ? 0.9
        : joining
          ? 0.78
          : breathRipple > 0
            ? options.reduced
              ? 0.62
              : 0.62 * breathRipple
            : 0.34 * (1 - ripple);
      whale.rescue.visible = strayed && current.mode === "journey";
      if (whale.rescue.visible) {
        whale.rescue.position.copy(whale.crest.position);
        whale.rescue.position.y += 0.02;
        whale.rescueProgress.value = actor.rescueProgress / WHALE.pickupTicks;
      }
    }

    this.wake.count = wakeCount;
    this.wake.visible = wakeCount > 0;
    if (this.wake.visible) this.wake.instanceMatrix.needsUpdate = true;

    const pod = this.whales.map(({ root }) => root.position);
    const leadView = this.whales[0]?.root.position;
    if (!leadView) return;
    const aspect = width / height;
    const { junction } = this;
    const showJunction =
      junction &&
      current.segmentId === "W3" &&
      current.route === null &&
      this.camera.mode !== "Explore";
    let span = this.followSpan(current);
    let offset = 0;
    if (showJunction) {
      const left = Math.min(leadView.x, junction.minX);
      const right = Math.max(leadView.x, junction.maxX);
      const approach = MathUtils.smoothstep(
        leadView.z,
        junction.crossing - 58,
        junction.crossing - 18,
      );
      offset = ((left + right) * 0.5 - leadView.x) * approach;
      span = lerp(
        71,
        Math.max(71, (right - left + 2 * JUNCTION_PADDING) / aspect),
        approach,
      );
    }
    const recenter =
      options.reduced || !this.hasView ? 1 : 1 - Math.exp(-6 * delta);
    this.junctionOffset = lerp(this.junctionOffset, offset, recenter);
    const target = { x: leadView.x + this.junctionOffset, z: leadView.z };
    if (landed && !this.hasView)
      this.camera.update(target, leadView.y, aspect, delta, options, false, 0);
    this.camera.update(
      target,
      leadView.y,
      aspect,
      delta,
      options,
      !landed && this.courseFocus(current),
      landed
        ? { progress: landing, birds: pod, framing: OFFSHORE_GATHERING }
        : 0,
      undefined,
      span,
    );
    this.hasView = true;
    this.gathering.mesh.visible = current.phase === "landing";
    if (this.gathering.mesh.visible)
      this.gathering.update(current.actors, landing, options, previous.actors);
    this.ocean.cullSeabed(this.camera.camera);
    this.renderer.render(this.scene, this.camera.camera);
  }

  private courseFocus(state: GameState): boolean {
    return (
      state.segmentId === "W1" ||
      state.segmentId === "W2" ||
      (state.segmentId === "W3" && state.route === null) ||
      (state.segmentId === "W4" &&
        state.triggered.includes("C2") &&
        !state.occupied.includes("offshore-goal"))
    );
  }

  private followSpan(state: GameState): number | undefined {
    if (state.segmentId === "W1" && !state.occupied.includes("crossing-rest"))
      return SHIPPING_APPROACH_SPAN;
    if (state.segmentId === "W2" && !state.occupied.includes("net-rest"))
      return NET_APPROACH_SPAN;
    const pos = state.actors[0]?.pos;
    if (
      state.species === "whale" &&
      state.segmentId === "W3" &&
      state.route === "shipping" &&
      pos &&
      this.dredgingWork &&
      pos.x > 42 &&
      Math.abs(pos.z - this.dredgingWork.z) < 42
    )
      return 91;
    if (state.segmentId === "W4" && state.triggered.includes("C2")) {
      const viewing =
        pos &&
        this.watchingCoast &&
        Math.abs(pos.z - this.watchingCoast.z) < 25 &&
        !state.occupied.includes("offshore-goal");
      return viewing ? 85 : OFFSHORE_FOLLOW_SPAN;
    }
    return undefined;
  }

  sceneryReport(): Record<string, string> {
    return { [MODEL_ID]: this.assets.kind, ocean: "painted-sea" };
  }

  reefReport(): ReefView | undefined {
    return this.reef.report();
  }

  framedWhales(): number {
    const projected = new Vector3();
    return this.whales.filter(({ root }) => {
      projected.copy(root.position).project(this.camera.camera);
      return Math.abs(projected.x) < 0.88 && Math.abs(projected.y) < 0.82;
    }).length;
  }

  project(pos: Vec2, depth?: number): Projected {
    const height = depth === undefined ? 1.5 : whaleDepthHeight(depth);
    const screen = new Vector3(pos.x, height, pos.z).project(
      this.camera.camera,
    );
    const rawX = (screen.x + 1) * 50;
    const rawY = (1 - screen.y) * 50;
    return {
      x: clamp(rawX, 8, 92),
      y: clamp(rawY, 36, 79),
      edge: rawX < 8 || rawX > 92 || rawY < 36 || rawY > 79,
      angle: (Math.atan2(rawY - 56, rawX - 50) * 180) / Math.PI,
    };
  }

  dispose(): void {
    if (this.assets.kind === "model") {
      // The six clones share geometry and pigment for this scene’s lifetime.
      for (const { model } of this.whales) {
        model.traverse((node) => {
          if (node instanceof SkinnedMesh) node.skeleton.dispose();
        });
        model.removeFromParent();
      }
      disposeGeometry(this.assets.model);
      this.assets.paint.map?.dispose();
    }
    if (this.whales.length === 0) {
      this.crestGeometry.dispose();
      this.rescueGeometry.dispose();
    }
    disposeGeometry(this.scene);
    if (this.assets.kind === "model" || this.whales.length === 0) {
      this.paint.leader.dispose();
      for (const paint of this.paint.companions) paint.dispose();
    }
    if (this.ownRenderer) this.renderer.dispose();
    else {
      this.renderer.resetState();
      this.renderer.setDrawingBufferSize(
        this.incomingScreen.x,
        this.incomingScreen.y,
        this.incomingPixelRatio,
      );
    }
  }
}
