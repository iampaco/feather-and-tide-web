import {
  Bone,
  Group,
  PropertyBinding,
  Quaternion,
  Vector3,
  type Object3D,
} from "three";
import { STEP_SEC } from "../core/clock";
import type { WhaleActor } from "../core/game";
import { angleDelta, clamp, lerp } from "../core/math";
import { WHALE } from "../simulation/whale-motion";

const FIN_POSES = [
  ["Spine.01", 0.05, 0, 0.43, 0],
  ["Spine.02", 0.09, 0.47, 0.34, 0],
  ["TailStock", 0.25, 0.94, 0.2, 0],
  ["Flukes", 0.12, 1.51, 0, 0],
  ["Pectoral.L", 0.047, 0.65, 0, -1],
  ["Pectoral.R", -0.047, 0.65, 0, 1],
] as const;
const X = new Vector3(1, 0, 0);
const Z = new Vector3(0, 0, 1);

export function hasWhaleSwimRig(model: Object3D): boolean {
  return FIN_POSES.every(
    ([name]) =>
      model.getObjectByName(PropertyBinding.sanitizeNodeName(name)) instanceof
      Bone,
  );
}

export class WhaleSwim {
  private readonly jointRotation = new Quaternion();
  private readonly joints: readonly {
    joint: Object3D;
    rest: Quaternion;
    stroke: number;
    lag: number;
    bend: number;
    fin: number;
  }[];
  private yawRate = 0;
  private trim = 0;

  constructor(
    private readonly model: Object3D,
    private readonly index: number,
  ) {
    this.joints = FIN_POSES.flatMap(([name, stroke, lag, bend, fin]) => {
      const joint = model.getObjectByName(
        PropertyBinding.sanitizeNodeName(name),
      );
      return joint instanceof Bone || joint instanceof Group
        ? [{ joint, rest: joint.quaternion.clone(), stroke, lag, bend, fin }]
        : [];
    });
  }

  reset(): void {
    this.yawRate = 0;
    this.trim = 0;
  }

  pose(
    before: WhaleActor,
    actor: WhaleActor,
    alpha: number,
    seconds: number,
    delta: number,
    reduced: boolean,
    rest: number,
  ): number {
    const speed = clamp(lerp(before.speed, actor.speed, alpha) / WHALE.cruise);
    const travel = reduced ? 0 : speed * (1 - rest);
    const blend = reduced ? 1 : 1 - Math.exp(-6 * delta);
    const turn = reduced
      ? 0
      : clamp(
          angleDelta(before.heading, actor.heading) / STEP_SEC,
          -1.55,
          1.55,
        );
    const { direction, progress } = actor.dive;
    // Ease the trim at each end of a real water-layer transition.
    const incline = direction === "down" ? -1 : direction === "up" ? 1 : 0;
    const dive = incline * (0.31 + Math.sin(Math.PI * progress) * 0.69);
    this.trim = lerp(this.trim, dive, blend);
    this.yawRate = lerp(this.yawRate, turn, blend);
    const phase = seconds * 2.46 + this.index * 0.98;
    const glide =
      0.55 + 0.45 * Math.sin(seconds * 0.81 + this.index * 0.83) ** 2;
    const propulse = glide * travel;
    this.model.rotation.x =
      this.trim * (reduced ? 0.06 : 0.21) + Math.sin(phase) * propulse * 0.036;
    this.model.rotation.z = this.yawRate * -0.12;
    for (const { joint, rest: neutral, stroke, lag, bend, fin } of this
      .joints) {
      const pitch =
        Math.sin(phase - lag) * propulse * stroke - fin * this.trim * 0.17;
      const yaw = this.yawRate * bend;
      joint.quaternion
        .copy(neutral)
        .multiply(this.jointRotation.setFromAxisAngle(Z, yaw))
        .multiply(this.jointRotation.setFromAxisAngle(X, pitch));
    }
    return Math.sin(phase * 0.5) * propulse * 0.1;
  }
}
