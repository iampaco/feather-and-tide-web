import {
  BufferGeometry,
  Color,
  Float32BufferAttribute,
  IcosahedronGeometry,
  Vector3,
} from "three";

type Paint = (t: number, shadow: boolean) => Color;

class PaintedPlant {
  readonly positions: number[] = [];
  readonly colors: number[] = [];

  private triangle(a: Vector3, b: Vector3, c: Vector3, color: Color): void {
    for (const point of [a, b, c]) {
      this.positions.push(point.x, point.y, point.z);
      this.colors.push(color.r, color.g, color.b);
    }
  }

  blade(
    spine: readonly Vector3[],
    widths: readonly number[],
    angle: number,
    fold: number,
    paint: Paint,
  ): void {
    const side = new Vector3(Math.cos(angle), 0, Math.sin(angle));
    for (let i = 1; i < spine.length; i++) {
      const before = spine[i - 1];
      const point = spine[i];
      if (!before || !point) continue;
      const width = widths[i - 1] ?? 0;
      const nextWidth = widths[i] ?? 0;
      const left = before.clone().addScaledVector(side, width);
      const right = before.clone().addScaledVector(side, -width);
      const nextLeft = point.clone().addScaledVector(side, nextWidth);
      const nextRight = point.clone().addScaledVector(side, -nextWidth);
      const t = i / (spine.length - 1);
      const light = paint(t, false);
      const dark = paint(t, true);
      if (fold === 0) {
        this.triangle(left, right, nextRight, light);
        this.triangle(left, nextRight, nextLeft, dark);
        continue;
      }
      left.y -= fold;
      right.y -= fold;
      this.triangle(left, before, point, light);
      this.triangle(before, right, point, dark);
      if (nextWidth > 0) {
        nextLeft.y -= fold;
        nextRight.y -= fold;
        this.triangle(left, point, nextLeft, light);
        this.triangle(right, nextRight, point, dark);
      }
    }
  }

  spike(base: Vector3, tip: Vector3, width: number): void {
    const center = base.clone().lerp(tip, 0.53);
    const pigment = new Color("#9c7142");
    const sunlight = new Color("#d7ac63");
    for (let i = 0; i < 4; i++) {
      const angle = (i * Math.PI * 2) / 4;
      const next = ((i + 1) * Math.PI * 2) / 4;
      const a = center
        .clone()
        .add(new Vector3(Math.cos(angle) * width, 0, Math.sin(angle) * width));
      const b = center
        .clone()
        .add(new Vector3(Math.cos(next) * width, 0, Math.sin(next) * width));
      this.triangle(base, a, b, pigment);
      this.triangle(a, tip, b, sunlight);
    }
  }

  geometry(): BufferGeometry {
    const geometry = new BufferGeometry()
      .setAttribute("position", new Float32BufferAttribute(this.positions, 3))
      .setAttribute("color", new Float32BufferAttribute(this.colors, 3));
    geometry.computeVertexNormals();
    return geometry;
  }
}

function leafPaint(warm: boolean): Paint {
  const base = new Color(warm ? "#6c6735" : "#536b4f");
  const tip = new Color(warm ? "#efd08b" : "#bfcd8e");
  const shadow = new Color(warm ? "#9b8a4f" : "#739360");
  return (t, dark) => base.clone().lerp(dark ? shadow : tip, t);
}

export function reedFans(warm: boolean): BufferGeometry {
  const plant = new PaintedPlant();
  const paint = leafPaint(warm);
  const stems = warm
    ? ([
        [-0.3, -0.11, 1.42, 0.24, 0.15],
        [0.15, 0.19, 1.16, 0.32, 1.7],
        [0.3, -0.2, 1.72, 0.26, 3.9],
      ] as const)
    : ([
        [-0.34, 0.17, 1.36, 0.25, 1.7],
        [-0.07, -0.16, 1.62, 0.43, 2.6],
        [0.34, 0.04, 1.3, 0.34, 4.5],
      ] as const);
  for (const [x, z, height, lean, angle] of stems) {
    const root = new Vector3(x, 0, z);
    const bend = new Vector3(x + lean * 0.23, height * 0.53, z + 0.025);
    const neck = new Vector3(x + lean, height, z + 0.09);
    const spine = [root, bend, neck];
    plant.blade(spine, [0.023, 0.02, 0.013], angle, 0.0, paint);
    plant.blade(spine, [0.023, 0.018, 0.012], angle + Math.PI / 2, 0.0, paint);
    plant.spike(
      neck.clone().lerp(bend, 0.16),
      neck.clone().add(new Vector3(0.095, 0.33, 0.03)),
      0.095,
    );
    for (const [sign, along] of [
      [1, 0.8],
      [-1, 0.93],
    ] as const) {
      const start = root.clone().lerp(bend, along);
      const sweep = new Vector3(
        Math.cos(angle + sign * 0.8),
        0,
        Math.sin(angle + sign * 0.8),
      ).multiplyScalar(sign);
      const middle = start
        .clone()
        .addScaledVector(sweep, 0.33)
        .add(new Vector3(0.13, 0.46, 0));
      const tip = start
        .clone()
        .addScaledVector(sweep, 0.94)
        .add(new Vector3(0.23, 0.57, 0.075));
      plant.blade(
        [start, middle, tip],
        [0.039, 0.145, 0.0],
        angle + Math.PI / 2,
        0.037,
        paint,
      );
    }
  }
  return plant.geometry();
}

export function sedgeFans(): BufferGeometry {
  const plant = new PaintedPlant();
  const paint = leafPaint(false);
  for (const [x, z, height, angle] of [
    [-0.16, -0.1, 0.58, 1.2],
    [0.07, 0.19, 0.49, 2.4],
    [0.24, 0.04, 0.65, 4.7],
    [0.12, -0.23, 0.42, 5.6],
    [-0.27, 0.2, 0.53, 0.24],
  ] as const) {
    const root = new Vector3(x, 0, z);
    const bend = new Vector3(
      Math.cos(angle) * 0.5,
      height,
      Math.sin(angle) * 0.5,
    );
    const middle = root.clone().addScaledVector(bend, 0.5);
    const tip = root.clone().add(bend);
    plant.blade(
      [root, middle, tip],
      [0.041, 0.155, 0],
      angle + Math.PI / 2,
      0.045,
      paint,
    );
  }
  return plant.geometry();
}

export function riverStone(): BufferGeometry {
  const geometry = new IcosahedronGeometry(1, 1);
  const positions = geometry.getAttribute("position");
  const cool = new Color("#546d63");
  const upper = new Color("#a69a75");
  const color: number[] = [];
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i);
    const y = positions.getY(i);
    const z = positions.getZ(i);
    const bulge =
      1 + 0.11 * Math.sin(x * 5 + z * 4) + 0.06 * Math.cos(y * 5 - z * 5);
    const layer = Math.max(0, 0.45 + y * 0.46);
    positions.setXYZ(i, x * bulge + layer * 0.09, layer, z * bulge);
    const tint = cool
      .clone()
      .lerp(upper, Math.min(1, layer * 0.73 + 0.14 * Math.cos(x * 3 - z)));
    color.push(tint.r, tint.g, tint.b);
  }
  geometry.setAttribute("color", new Float32BufferAttribute(color, 3));
  geometry.computeVertexNormals();
  return geometry;
}
