export type Vec2 = Readonly<{ x: number; z: number }>;

export function clamp(value: number, min = 0, max = 1): number {
  return Math.max(min, Math.min(max, value));
}

export function approach(value: number, target: number, step: number): number {
  return value + clamp(target - value, -step, step);
}

export function angleDelta(from: number, to: number): number {
  const delta = to - from;
  return Math.atan2(Math.sin(delta), Math.cos(delta));
}

export function distance(a: Vec2, b: Vec2): number {
  return Math.hypot(a.x - b.x, a.z - b.z);
}

export function lerp(a: number, b: number, alpha: number): number {
  return a + (b - a) * alpha;
}
