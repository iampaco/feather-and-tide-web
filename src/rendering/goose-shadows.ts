import {
  Color,
  DynamicDrawUsage,
  InstancedBufferAttribute,
  InstancedMesh,
  MathUtils,
  Matrix4,
  PlaneGeometry,
  ShaderMaterial,
  UniformsLib,
  UniformsUtils,
  Vector3,
} from "three";
import { migrationSun } from "./migrationAtmosphere";

export class GooseShadows {
  readonly mesh: InstancedMesh<PlaneGeometry, ShaderMaterial>;
  private readonly ink: InstancedBufferAttribute;
  private readonly transform = new Matrix4();
  private readonly scale = new Vector3();

  constructor(capacity: number) {
    const geometry = new PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
    this.ink = new InstancedBufferAttribute(new Float32Array(capacity * 2), 2);
    this.ink.setUsage(DynamicDrawUsage);
    geometry.setAttribute("shadowInk", this.ink);
    const material = new ShaderMaterial({
      transparent: true,
      depthWrite: false,
      fog: true,
      uniforms: {
        ...UniformsUtils.clone(UniformsLib.fog),
        wetInk: { value: new Color("#264c47") },
        dryInk: { value: new Color("#514537") },
      },
      vertexShader: `
        #include <fog_pars_vertex>
        attribute vec2 shadowInk;
        varying vec2 mark, ink;

        void main() {
          mark = uv * 2.0 - 1.0;
          ink = shadowInk;
          vec4 mvPosition = modelViewMatrix * instanceMatrix * vec4(position, 1.0);
          gl_Position = projectionMatrix * mvPosition;
          #include <fog_vertex>
        }
      `,
      fragmentShader: `
        #include <common>
        #include <fog_pars_fragment>
        uniform vec3 wetInk, dryInk;
        varying vec2 mark, ink;

        void main() {
          float radius = length(mark);
          float wash = 1.0 - smoothstep(0.12, 1.0, radius);
          float core = 1.0 - smoothstep(0.05, 0.67, radius);
          gl_FragColor = vec4(mix(wetInk, dryInk, ink.y), ink.x * (wash * 0.74 + core * 0.26));
          #include <colorspace_fragment>
          #include <fog_fragment>
        }
      `,
    });
    this.mesh = new InstancedMesh(geometry, material, capacity);
    this.mesh.instanceMatrix.setUsage(DynamicDrawUsage);
    this.mesh.name = "goose-contact-shadows";
    this.mesh.count = 0;
    // The projected spots follow the whole flock and sit below the mist and cues.
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 1;
  }

  set(
    index: number,
    position: Vector3,
    heading: number,
    size: number,
    surface: number,
    contact: number,
    height: ((x: number, z: number) => number) | undefined,
  ): void {
    const lift = Math.max(0, position.y - surface) * (1 - contact);
    const spread = MathUtils.smoothstep(lift, 0, 4.4);
    const x = position.x - (migrationSun.x / migrationSun.y) * lift;
    const z = position.z - (migrationSun.z / migrationSun.y) * lift;
    const receiver = height?.(x, z) ?? surface;
    const dry = MathUtils.smoothstep(receiver, -0.06, 0.12);
    this.scale.set(
      size * MathUtils.lerp(2.55, 4.8, spread),
      1,
      size * MathUtils.lerp(3.05, 3.85, spread),
    );
    this.transform.makeRotationY(heading).scale(this.scale);
    this.transform.setPosition(x, Math.max(0, receiver) + 0.045, z);
    this.mesh.setMatrixAt(index, this.transform);
    this.ink.setXY(
      index,
      MathUtils.lerp(0.35 + dry * 0.07, 0.16 + dry * 0.05, spread),
      dry,
    );
  }

  finish(count: number): void {
    this.mesh.count = count;
    this.mesh.instanceMatrix.needsUpdate = true;
    this.ink.needsUpdate = true;
  }
}
