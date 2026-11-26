import { MathUtils, OrthographicCamera, Vector3 } from "three";
import { clamp, lerp, type Vec2 } from "../core/math";
import type { Basis, InputSettings } from "../input/input";
import { clearOrbitPitch, type OrbitClearance } from "./orbit-clearance";

const RAD = Math.PI / 180;
const FULL_TURN = 2 * Math.PI;
const DEFAULT_PITCH = 49 * RAD;
const CLASSIC_PITCH = [35 * RAD, 65 * RAD] as const;
const WIDE_PITCH = [20 * RAD, 80 * RAD] as const;
const FOLLOW_DISTANCE = 83;
const WIDE_DISTANCE = 100;
const FOLLOW_SPAN = 58;
const LANDING_SPAN = 73;
const LANDING_PITCH = 41 * RAD;

interface LandingFrame {
  readonly progress: number;
  readonly framing?: {
    readonly span: number;
    readonly padding: number;
    readonly lookAhead: number;
    readonly defaultYawOffsetDegrees?: number;
    readonly defaultPitchDegrees?: number;
  };
  readonly birds: readonly Readonly<{ x: number; y: number; z: number }>[];
}

export class CameraDirector {
  readonly camera = new OrthographicCamera(-40, 40, 25, -25, 0.1, 260);
  private readonly followPitch: number;
  private yaw = 0;
  private pitch: number;
  private targetYaw = 0;
  private targetPitch: number;
  private explored = false;
  private wide = false;
  private observationBlend = 0;
  private radius = FOLLOW_DISTANCE;
  private span = 56;
  private readonly center = new Vector3();
  private readonly leader = new Vector3();
  private landingEntry:
    | {
        readonly span: number;
        readonly pitch: number;
        readonly center: Vector3;
        readonly wide: boolean;
        readonly radius: number;
        readonly yaw: number;
        readonly explored: boolean;
      }
    | undefined;
  mode: "Follow" | "Explore" | "Focus" | "Cinematic" = "Follow";

  constructor(followPitchDegrees = DEFAULT_PITCH / RAD) {
    this.followPitch = followPitchDegrees * RAD;
    this.pitch = this.followPitch;
    this.targetPitch = this.followPitch;
  }

  drag(
    x: number,
    y: number,
    settings: InputSettings,
    pointerType = "touch",
  ): void {
    if (!x && (!y || !settings.vertical)) return;
    const factor = 0.006 * settings.sensitivity;
    this.wide = pointerType === "mouse" && settings.wideMouseOrbit;
    const [min, max] = this.wide ? WIDE_PITCH : CLASSIC_PITCH;
    this.targetYaw -= x * factor;
    this.targetPitch = clamp(
      this.targetPitch + (settings.vertical ? y * factor : 0),
      min,
      max,
    );
    this.explored = true;
  }

  reset(immediate = false): void {
    // Reset from the visible angle by the shortest arc, discarding pending drag.
    this.targetYaw = Math.round(this.yaw / FULL_TURN) * FULL_TURN;
    this.targetPitch = this.followPitch;
    this.explored = false;
    this.wide = false;
    if (immediate) {
      this.landingEntry = undefined;
      this.yaw = 0;
      this.targetYaw = 0;
      this.pitch = this.followPitch;
      this.observationBlend = 0;
      this.radius = FOLLOW_DISTANCE;
      this.span = FOLLOW_SPAN;
      this.mode = "Follow";
    }
  }

  basis(): Basis {
    const sin = Math.sin(this.yaw);
    const cos = Math.cos(this.yaw);
    return {
      right: { x: -cos, z: sin },
      up: { x: sin / Math.sin(this.pitch), z: cos / Math.sin(this.pitch) },
    };
  }

  viewAngles(): Readonly<{
    yaw: number;
    pitch: number;
    requestedPitch: number;
    profile: "classic" | "wide";
    mode: CameraDirector["mode"];
  }> {
    return {
      yaw: this.yaw / RAD,
      pitch: this.pitch / RAD,
      requestedPitch: this.targetPitch / RAD,
      profile: this.wide ? "wide" : "classic",
      mode: this.mode,
    };
  }

  update(
    target: Vec2,
    height: number,
    aspect: number,
    delta: number,
    settings: InputSettings,
    focus: boolean,
    landing: 0 | LandingFrame,
    clearance?: OrbitClearance,
    followSpan = FOLLOW_SPAN,
  ): void {
    if (landing) {
      this.mode = "Cinematic";
      this.frameLanding(landing, aspect, settings.reduced);
    } else {
      this.landingEntry = undefined;
      const blend = settings.reduced ? 1 : 1 - Math.exp(-11 * delta);
      this.yaw = lerp(this.yaw, this.targetYaw, blend);
      // Wrap both angles together so damping never reverses a drag at the seam.
      const completedTurns = Math.round(this.yaw / FULL_TURN) * FULL_TURN;
      this.yaw -= completedTurns;
      this.targetYaw -= completedTurns;
      this.pitch = lerp(this.pitch, this.targetPitch, blend);
      this.mode = this.explored ? "Explore" : focus ? "Focus" : "Follow";
      const span =
        focus && !this.explored ? Math.max(71, followSpan) : followSpan;
      this.span = lerp(this.span, span, blend);
      this.observationBlend = lerp(
        this.observationBlend,
        this.wide ? 1 : 0,
        blend,
      );
      // Extra standoff keeps the near plane clear at shallow angles without changing orthographic scale.
      this.radius = lerp(FOLLOW_DISTANCE, WIDE_DISTANCE, this.observationBlend);
      const forwardOffset = 7 * (1 - this.observationBlend);
      this.center.set(
        target.x + Math.sin(this.yaw) * forwardOffset,
        lerp(height * 0.45, height, this.observationBlend),
        target.z + Math.cos(this.yaw) * forwardOffset,
      );
      if (clearance && (this.wide || this.observationBlend > 0.001)) {
        this.leader.set(target.x, height, target.z);
        this.pitch = clearOrbitPitch(
          this.pitch,
          WIDE_PITCH[1],
          this.yaw,
          this.radius,
          this.center,
          this.leader,
          this.span / 2,
          (this.span * aspect) / 2,
          this.camera.near,
          clearance,
        );
      }
    }

    const halfHeight = this.span / 2;
    const halfWidth = halfHeight * aspect;
    this.camera.left = -halfWidth;
    this.camera.right = halfWidth;
    this.camera.top = halfHeight;
    this.camera.bottom = -halfHeight;
    const horizontalDistance = this.radius * Math.cos(this.pitch);
    this.camera.position.set(
      this.center.x - horizontalDistance * Math.sin(this.yaw),
      this.center.y + this.radius * Math.sin(this.pitch),
      this.center.z - horizontalDistance * Math.cos(this.yaw),
    );
    this.camera.lookAt(this.center);
    this.camera.updateProjectionMatrix();
    this.camera.updateMatrixWorld();
  }

  private frameLanding(
    { progress, birds, framing }: LandingFrame,
    aspect: number,
    reduced: boolean,
  ): void {
    const entry = (this.landingEntry ??= {
      span: this.span,
      pitch: this.pitch,
      center: this.center.clone(),
      wide: this.observationBlend > 0.001,
      radius: this.radius,
      yaw: this.yaw,
      explored: this.explored,
    });
    if (birds.length === 0) return;
    const blend = reduced ? 1 : MathUtils.smoothstep(progress, 0, 0.93);
    if (!reduced && !entry.explored && framing?.defaultYawOffsetDegrees)
      this.yaw = entry.yaw + framing.defaultYawOffsetDegrees * RAD * blend;
    const scenicPitch =
      !entry.explored && !reduced && framing?.defaultPitchDegrees !== undefined
        ? framing.defaultPitchDegrees * RAD
        : LANDING_PITCH;
    const landingPitch = entry.wide
      ? LANDING_PITCH
      : Math.min(entry.pitch, scenicPitch);
    this.pitch = lerp(entry.pitch, landingPitch, blend);
    this.radius = lerp(entry.radius, FOLLOW_DISTANCE, blend);
    const sinYaw = Math.sin(this.yaw);
    const cosYaw = Math.cos(this.yaw);
    const sinPitch = Math.sin(this.pitch);
    const cosPitch = Math.cos(this.pitch);
    let minX = Infinity;
    let maxX = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;
    for (const bird of birds) {
      minX = Math.min(minX, bird.x);
      maxX = Math.max(maxX, bird.x);
      minZ = Math.min(minZ, bird.z);
      maxZ = Math.max(maxZ, bird.z);
    }
    // Keep the last observed heading and pull out around the real group.
    const lead = framing?.lookAhead ?? 4;
    this.center.set(
      lerp(entry.center.x, (minX + maxX) / 2 + lead * sinYaw, blend),
      lerp(entry.center.y, 1, blend),
      lerp(entry.center.z, (minZ + maxZ) / 2 + lead * cosYaw, blend),
    );
    const padding = framing?.padding ?? 3.2;
    let span = lerp(
      entry.span,
      framing?.span ?? Math.max(entry.span, LANDING_SPAN),
      blend,
    );
    for (const bird of birds) {
      const x = bird.x - this.center.x;
      const z = bird.z - this.center.z;
      const screenX = x * -cosYaw + z * sinYaw;
      const screenY =
        (x * sinYaw + z * cosYaw) * sinPitch +
        (bird.y - this.center.y) * cosPitch;
      // Fit full silhouettes around the group, with room for the top and bottom HUD.
      span = Math.max(
        span,
        (2 * (Math.abs(screenX) + padding)) / (aspect * 0.84),
        (2 * (Math.abs(screenY) + padding)) / 0.72,
      );
    }
    this.span = framing ? span : Math.max(this.span, span);
  }
}
