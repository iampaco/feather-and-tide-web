import { readFileSync } from "node:fs";
import {
  AnimationMixer,
  LoopOnce,
  SkinnedMesh,
  Vector3,
  type Object3D,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";
import { expect, test } from "vitest";
import {
  applyReindeerRole,
  batchReindeerCoat,
} from "../../src/rendering/reindeer-coat";

function skins(root: Object3D): SkinnedMesh[] {
  const parts: SkinnedMesh[] = [];
  root.traverse((node) => {
    if (node instanceof SkinnedMesh) parts.push(node);
  });
  return parts;
}

function sampleParts(
  parts: readonly SkinnedMesh[],
): [number, number, number][] {
  const point = new Vector3();
  return parts.flatMap((part) =>
    Array.from(
      { length: part.geometry.getAttribute("position").count },
      (_, index): [number, number, number] => {
        part.getVertexPosition(index, point).applyMatrix4(part.matrixWorld);
        return [point.x, point.y, point.z];
      },
    ),
  );
}

test("the original multi-part coat batches in one draw without moving animated vertices", async () => {
  const source = new URL(
    "../../Assets/Watercolor/Deer/Blender/RD-CHR-001/v001/reindeer-v001.glb",
    import.meta.url,
  );
  const data = Uint8Array.from(readFileSync(source)).buffer;
  const model = await new GLTFLoader().parseAsync(data, "");
  const original = skins(model.scene);
  expect(original.length).toBeGreaterThan(1);
  const clip = model.animations.find(({ name }) => name === "Settle");
  if (!clip) throw new Error("Missing reindeer settle clip");
  const mixer = new AnimationMixer(model.scene);
  mixer.clipAction(clip).play();
  mixer.setTime(clip.duration * 0.7);
  model.scene.updateMatrixWorld(true);
  const before = sampleParts(original);
  const triangles = original.reduce(
    (total, part) => total + (part.geometry.index?.count ?? 0),
    0,
  );
  batchReindeerCoat(model.scene);
  const packed = skins(model.scene);
  expect(packed).toHaveLength(1);
  expect(packed[0]?.geometry.index?.count).toBe(triangles);
  expect(packed[0]?.geometry.getAttribute("color").count).toBe(before.length);
  model.scene.updateMatrixWorld(true);
  expect(sampleParts(packed)).toEqual(before);
});

test("the current coat shares a single primitive and gives roles and hooves actual geometry", async () => {
  const source = new URL(
    "../../public/assets/reindeer/reindeer-v002.glb",
    import.meta.url,
  );
  const data = Uint8Array.from(readFileSync(source)).buffer;
  const { scene, animations } = await new GLTFLoader().parseAsync(data, "");
  expect(animations.map(({ name }) => name).sort()).toEqual([
    "Call",
    "Idle",
    "Run",
    "Settle",
    "Walk",
  ]);
  batchReindeerCoat(scene);
  const parts = skins(scene);
  expect(parts).toHaveLength(1);
  const adult = parts[0];
  if (!adult) throw new Error("Missing reindeer skin");
  expect(adult.geometry.getAttribute("color").count).toBe(
    adult.geometry.getAttribute("position").count,
  );
  expect(adult.morphTargetInfluences).toEqual([0, 0]);

  const leader = clone(scene);
  const calf = clone(scene);
  applyReindeerRole(leader, "leader");
  applyReindeerRole(calf, "calf");
  expect(skins(leader)[0]?.morphTargetInfluences).toEqual([1, 0]);
  expect(skins(calf)[0]?.morphTargetInfluences).toEqual([0, 1]);
  expect(adult.morphTargetInfluences).toEqual([0, 0]);

  const crownBounds = (root: Object3D) => {
    root.updateMatrixWorld(true);
    const crown = sampleParts(skins(root)).filter(([, height]) => height > 2.2);
    return {
      height: Math.max(...crown.map(([, height]) => height)),
      halfWidth: Math.max(...crown.map(([x]) => Math.abs(x))),
    };
  };
  const adultCrown = crownBounds(scene);
  expect(crownBounds(leader).halfWidth).toBeGreaterThan(
    adultCrown.halfWidth + 0.1,
  );
  expect(crownBounds(calf).height).toBeLessThan(adultCrown.height - 0.4);

  const hoofNames = [
    "HoofContact_FL",
    "HoofContact_FR",
    "HoofContact_HL",
    "HoofContact_HR",
  ];
  const anchors = hoofNames.map((name) => {
    const anchor = calf.getObjectByName(name);
    if (!anchor) throw new Error(`Missing reindeer anchor ${name}`);
    return anchor;
  });
  const anchorHeights = () =>
    anchors.map((anchor) => anchor.getWorldPosition(new Vector3()).y);
  for (const height of anchorHeights()) expect(height).toBeCloseTo(0.018, 3);

  const walk = animations.find(({ name }) => name === "Walk");
  if (!walk) throw new Error("Missing reindeer walk clip");
  const mixer = new AnimationMixer(calf);
  mixer.clipAction(walk).setLoop(LoopOnce, 1).play();
  for (let step = 0; step < 8; step++) {
    mixer.setTime(walk.duration * (step / 8));
    calf.updateMatrixWorld(true);
    expect(Math.min(...anchorHeights())).toBeCloseTo(0.018, 2);
  }
  mixer.setTime(walk.duration * 0.8);
  calf.updateMatrixWorld(true);
  expect(Math.max(...anchorHeights())).toBeGreaterThan(0.1);
});
