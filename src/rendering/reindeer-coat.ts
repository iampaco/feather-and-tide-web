import {
  Float32BufferAttribute,
  MeshStandardMaterial,
  SkinnedMesh,
  type Object3D,
} from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

function flatPigment(material: MeshStandardMaterial): boolean {
  return (
    material.constructor === MeshStandardMaterial &&
    !material.transparent &&
    material.opacity === 1 &&
    material.alphaTest === 0 &&
    !material.vertexColors &&
    material.emissive.getHex() === 0 &&
    !material.map &&
    !material.aoMap &&
    !material.lightMap &&
    !material.emissiveMap &&
    !material.bumpMap &&
    !material.normalMap &&
    !material.displacementMap &&
    !material.roughnessMap &&
    !material.metalnessMap &&
    !material.alphaMap &&
    !material.envMap
  );
}

// RD-CHR-001 v001 uses separate primitives for coat colors, all on one rig.
// Baking those colors into the vertices lets each deer upload one palette
// and draw its entire coat in one call, while the clips still target its bones.
export function batchReindeerCoat(root: Object3D): void {
  root.updateMatrixWorld(true);
  const parts: SkinnedMesh[] = [];
  root.traverse((node) => {
    if (node instanceof SkinnedMesh) parts.push(node);
  });
  const first = parts[0];
  const pigment = first?.material;
  const parent = first?.parent;
  if (
    parts.length < 2 ||
    !first ||
    !parent ||
    !(pigment instanceof MeshStandardMaterial)
  )
    return;
  const geometries = [];
  for (const part of parts) {
    const material = part.material;
    if (
      part.parent !== parent ||
      part.skeleton !== first.skeleton ||
      !part.matrix.equals(first.matrix) ||
      !part.bindMatrix.equals(first.bindMatrix) ||
      part.geometry.hasAttribute("color") ||
      Object.keys(part.geometry.morphAttributes).length > 0 ||
      !(material instanceof MeshStandardMaterial) ||
      !flatPigment(material) ||
      material.side !== pigment.side ||
      material.roughness !== pigment.roughness ||
      material.metalness !== pigment.metalness ||
      material.flatShading !== pigment.flatShading
    ) {
      for (const geometry of geometries) geometry.dispose();
      return;
    }
    const geometry = part.geometry.clone();
    const count = geometry.getAttribute("position").count;
    const colors = new Float32Array(count * 3);
    for (let index = 0; index < count; index++)
      material.color.toArray(colors, index * 3);
    geometry.setAttribute("color", new Float32BufferAttribute(colors, 3));
    geometries.push(geometry);
  }
  const merged = mergeGeometries(geometries);
  for (const geometry of geometries) geometry.dispose();
  if (!merged) return;

  const material = pigment.clone();
  material.color.setHex(0xffffff);
  material.vertexColors = true;
  const coat = new SkinnedMesh(merged, material);
  coat.name = first.name;
  coat.position.copy(first.position);
  coat.quaternion.copy(first.quaternion);
  coat.scale.copy(first.scale);
  coat.bindMode = first.bindMode;
  coat.bind(first.skeleton, first.bindMatrix);
  parent.add(coat);

  for (const part of parts) parent.remove(part);
  for (const geometry of new Set(parts.map(({ geometry }) => geometry)))
    geometry.dispose();
  for (const paint of new Set(parts.map(({ material }) => material)))
    if (!Array.isArray(paint)) paint.dispose();
}

export function applyReindeerRole(
  root: Object3D,
  role: "leader" | "calf",
): void {
  const targetName = role === "leader" ? "Leader" : "Calf";
  root.traverse((node) => {
    if (!(node instanceof SkinnedMesh)) return;
    const { morphTargetDictionary, morphTargetInfluences } = node;
    if (!morphTargetDictionary || !morphTargetInfluences) return;
    for (const name of ["Leader", "Calf"]) {
      const index = morphTargetDictionary[name];
      if (index !== undefined)
        morphTargetInfluences[index] = Number(name === targetName);
    }
  });
}
