import { Ray, Vector3, type Box3 } from "three";

export interface OrbitClearance {
  readonly height?: (x: number, z: number) => number;
  readonly obstacles: readonly Box3[];
}

const clearance = 0.5;
const gradeStep = Math.PI / 60;
const sampleSpacing = 2;
const viewportSampleSpacing = 1;

export function clearOrbitPitch(
  requested: number,
  maximum: number,
  yaw: number,
  radius: number,
  center: Vector3,
  leader: Vector3,
  halfHeight: number,
  halfWidth: number,
  near: number,
  terrain: OrbitClearance,
): number {
  const sinYaw = Math.sin(yaw);
  const cosYaw = Math.cos(yaw);
  const eye = new Vector3();
  const ray = new Ray();
  const hit = new Vector3();
  ray.origin.copy(leader);

  function clear(pitch: number): boolean {
    const sin = Math.sin(pitch);
    const cos = Math.cos(pitch);
    eye.set(
      center.x - radius * cos * sinYaw,
      center.y + radius * sin,
      center.z - radius * cos * cosYaw,
    );
    ray.direction.subVectors(eye, leader);
    const distance = ray.direction.length();
    ray.direction.divideScalar(distance);
    for (const obstacle of terrain.obstacles) {
      if (ray.intersectBox(obstacle, hit) && hit.distanceTo(leader) <= distance)
        return false;
    }

    const height = terrain.height;
    if (!height) return true;
    const { x, y, z } = ray.direction;
    for (let d = sampleSpacing; d < distance; d += sampleSpacing) {
      if (
        leader.y + y * d <
        Math.max(0, height(leader.x + x * d, leader.z + z * d)) + clearance
      )
        return false;
    }

    // The lower edge of the orthographic near plane is lower than the eye.
    const bottomY = eye.y - halfHeight * cos - near * sin;
    const along = near * cos - halfHeight * sin;
    const bottomX = eye.x + along * sinYaw;
    const bottomZ = eye.z + along * cosYaw;
    // Sweep the whole edge so narrow ridges between viewport probes cannot
    // cut into a wide shot.
    const intervals = Math.max(
      1,
      Math.ceil((2 * halfWidth) / viewportSampleSpacing),
    );
    for (let i = 0; i <= intervals; i++) {
      const offset = (2 * i * halfWidth) / intervals - halfWidth;
      const ground = height(
        bottomX - offset * cosYaw,
        bottomZ + offset * sinYaw,
      );
      if (bottomY < Math.max(0, ground) + clearance) return false;
    }
    return true;
  }

  if (clear(requested)) return requested;
  let blocked = requested;
  while (blocked < maximum) {
    let safe = Math.min(blocked + gradeStep, maximum);
    if (clear(safe)) {
      for (let i = 0; i < 6; i++) {
        const middle = (blocked + safe) / 2;
        if (clear(middle)) safe = middle;
        else blocked = middle;
      }
      return safe;
    }
    blocked = safe;
  }
  return maximum;
}
