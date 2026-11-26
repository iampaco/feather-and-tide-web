import { MeshStandardMaterial, SkinnedMesh, type Object3D } from "three";

const leaderBodyName = "Body_Leader";

export function prepareGoosePlumage(
  model: Object3D,
): MeshStandardMaterial | undefined {
  const materials = new Set<MeshStandardMaterial>();
  model.traverse((node) => {
    if (
      node instanceof SkinnedMesh &&
      node.material instanceof MeshStandardMaterial
    )
      materials.add(node.material);
  });
  let companionBody: MeshStandardMaterial | undefined;
  for (const material of materials) {
    if (material.name === leaderBodyName) {
      companionBody = material.clone();
      companionBody.name = "Body_Companion";
      companionBody.color.setRGB(0.83, 0.88, 0.92);
      material.color.setRGB(1.08, 1.06, 1.02);
    } else if (material.name === "FlightFeather") {
      material.color.setRGB(0.69, 0.74, 0.79);
    } else if (material.name === "Head" && material.map) {
      // Grade the two bars already painted in the atlas after mip filtering.
      // This carries the head pattern to small sizes without sharpening noise.
      material.onBeforeCompile = (shader) => {
        shader.fragmentShader = shader.fragmentShader.replace(
          "#include <map_fragment>",
          `#include <map_fragment>
          float plumeValue = dot(diffuseColor.rgb, vec3(0.2126, 0.7152, 0.0722));
          float paper = smoothstep(0.06, 0.47, plumeValue);
          diffuseColor.rgb *= mix(vec3(0.53, 0.59, 0.66), vec3(1.22, 1.24, 1.28), paper);`,
        );
      };
    }
  }
  return companionBody;
}

export function useGooseCompanionPlumage(
  model: Object3D,
  body: MeshStandardMaterial,
): void {
  model.traverse((node) => {
    if (
      node instanceof SkinnedMesh &&
      node.material instanceof MeshStandardMaterial &&
      node.material.name === leaderBodyName
    )
      node.material = body;
  });
}
