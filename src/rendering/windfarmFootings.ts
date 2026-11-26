import {
  BufferGeometry,
  Color,
  CylinderGeometry,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  Object3D,
} from "three";
import type { Vec2 } from "../core/math";
import { riverStone } from "./migrationVegetation";

type Height = (x: number, z: number) => number;

function footingWash(
  centers: readonly Vec2[],
  height: Height,
  sides: number,
): Mesh {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const submerged = new Color("#3f6056");
  const foam = new Color("#bdc2a3");
  const rings = [
    [3.9, 0.1, 0],
    [4.7, 0.31, 0],
    [5.45, 0.24, 0.2],
    [5.87, 0.17, 0.78],
    [6.65, 0, 0.35],
  ] as const;
  const tint = new Color();
  for (const [index, center] of centers.entries()) {
    for (const [ring, [radius, opacity, light]] of rings.entries()) {
      const first = positions.length / 3;
      for (let side = 0; side < sides; side++) {
        const angle = (side / sides) * Math.PI * 2;
        const edge =
          0.24 * Math.sin(angle * 3 + index) + 0.17 * Math.cos(angle * 5);
        const x = center.x + Math.cos(angle) * (radius + edge);
        const z = center.z + Math.sin(angle) * (radius + edge);
        const broken = 0.58 + 0.42 * Math.sin(angle * 2 + index) ** 2;
        tint.copy(submerged).lerp(foam, light * broken);
        positions.push(x, Math.max(0, height(x, z)) + 0.027, z);
        colors.push(tint.r, tint.g, tint.b, opacity * broken);
        if (ring > 0) {
          const a = first + side;
          const b = first + ((side + 1) % sides);
          indices.push(a - sides, a, b, a - sides, b, b - sides);
        }
      }
    }
  }
  const geometry = new BufferGeometry()
    .setIndex(indices)
    .setAttribute("position", new Float32BufferAttribute(positions, 3))
    .setAttribute("color", new Float32BufferAttribute(colors, 4));
  const wash = new Mesh(
    geometry,
    new MeshBasicMaterial({
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      side: DoubleSide,
      forceSinglePass: true,
    }),
  );
  wash.name = "windfarm-waterline";
  wash.renderOrder = 2;
  return wash;
}

export function buildWindfarmFootings(
  centers: readonly Vec2[],
  height: Height,
  low: boolean,
): Group {
  const group = new Group();
  group.name = "windfarm-footings";
  if (!centers.length) return group;
  const stamp = new Object3D();
  const tierSides = low ? 12 : 24;
  const piles = new InstancedMesh(
    new CylinderGeometry(1, 1.26, 1, tierSides),
    new MeshLambertMaterial({ color: "white" }),
    centers.length * 2,
  );
  const chipCount = low ? 8 : 17;
  const chips = new InstancedMesh(
    riverStone(),
    new MeshLambertMaterial({ vertexColors: true }),
    centers.length * chipCount,
  );
  const wetStone = new Color("#92968a");
  const dryStone = new Color("#c5b8a1");
  const chipTone = new Color("#b3b4a5");
  const tint = new Color();

  for (const [index, { x, z }] of centers.entries()) {
    const bank = Math.max(0, height(x, z));
    // The upper cap meets both the procedural tower and the authored GLB plinth.
    const tiers = [
      [3.85, bank - 0.27, 0.75, wetStone],
      [3.13, bank + 0.17, 0.2, dryStone],
    ] as const;
    for (const [tier, [radius, y, span, color]] of tiers.entries()) {
      stamp.position.set(x, y, z);
      stamp.rotation.set(0, index * 0.16, 0);
      stamp.scale.set(radius, span, radius);
      stamp.updateMatrix();
      piles.setMatrixAt(index * tiers.length + tier, stamp.matrix);
      piles.setColorAt(index * tiers.length + tier, color);
    }
    for (let chip = 0; chip < chipCount; chip++) {
      const angle = ((chip + index * 0.47) / chipCount) * Math.PI * 2;
      const variation = 0.5 + 0.5 * Math.sin(chip * 2.4 + index);
      const radius = 4.08 + variation * 0.69;
      const px = x + Math.cos(angle) * radius;
      const pz = z + Math.sin(angle) * radius;
      const scale = 0.45 + variation * 0.68;
      // Set the bank stones into the skirt of the plinth above the deeper bed.
      stamp.position.set(px, Math.max(height(px, pz), bank - 0.41) - 0.06, pz);
      stamp.rotation.set(0, -angle, 0);
      stamp.scale.set(scale, 0.75 * scale, 0.8 * scale);
      stamp.updateMatrix();
      chips.setMatrixAt(index * chipCount + chip, stamp.matrix);
      chips.setColorAt(
        index * chipCount + chip,
        tint.copy(chipTone).lerp(dryStone, variation * 0.5),
      );
    }
  }
  piles.name = "windfarm-concrete-plinths";
  chips.name = "windfarm-bank-stones";
  group.add(piles, chips, footingWash(centers, height, tierSides));
  return group;
}
