import {
  Color,
  DynamicDrawUsage,
  InstancedBufferAttribute,
  InstancedMesh,
  MathUtils,
  Matrix4,
  PlaneGeometry,
  ShaderMaterial,
} from "three";
import { lerp } from "../core/math";

const PRESENTATION_SECONDS = 3.35;
const BIRD_DELAY_SECONDS = 0.065;
const CLIP_RATE = 0.65;
const CLIP_END = 80 / 48;
const RIPPLE_SECONDS = 1.3;

// ANM-007's 48 Hz contact frames. The shared support curve samples the
// exported Web mesh through the half-second of leg compression after contact.
const SURFACES = {
  water: { frame: 51, clip: "Land_ShallowWater" },
  mud: { frame: 47, clip: "Land_Mudflat" },
} as const;
const FOOT_OFFSET_SAMPLES = [
  0.17645, 0.17234, 0.16286, 0.16127, 0.16205, 0.16423, 0.16685, 0.16858,
  0.16895,
];
const FOOT_SAMPLES_HZ = 16;

export interface LandingPose {
  readonly clip: (typeof SURFACES)[keyof typeof SURFACES]["clip"];
  readonly seconds: number;
  readonly weight: number;
  readonly height: number;
  readonly surface: number;
  readonly contact: number;
  readonly ripple: number;
}

export function sampleLandingPose(
  progress: number,
  index: number,
  entryHeight: number,
  modelScale: number,
  terrain: number,
  reduced: boolean,
): LandingPose {
  const onWater = terrain <= 0;
  const surface = Math.max(terrain, 0);
  const { frame, clip } = onWater ? SURFACES.water : SURFACES.mud;
  const contactSecond = (frame - 1) / 48;
  const elapsed = progress * PRESENTATION_SECONDS - index * BIRD_DELAY_SECONDS;
  const seconds = reduced
    ? CLIP_END
    : MathUtils.clamp(elapsed * CLIP_RATE, 0, CLIP_END);
  const weight = reduced ? 1 : MathUtils.smoothstep(seconds, 0, 0.19);
  const contact = MathUtils.smoothstep(seconds, 0, contactSecond);
  const sample = MathUtils.clamp(
    (seconds - contactSecond) * FOOT_SAMPLES_HZ,
    0,
    FOOT_OFFSET_SAMPLES.length - 1,
  );
  const sampleIndex = Math.floor(sample);
  const offset = FOOT_OFFSET_SAMPLES[sampleIndex] ?? 0;
  const footOffset = lerp(
    offset,
    FOOT_OFFSET_SAMPLES[sampleIndex + 1] ?? offset,
    sample - sampleIndex,
  );
  const ripple =
    onWater && !reduced
      ? MathUtils.clamp(
          (elapsed - contactSecond / CLIP_RATE) / RIPPLE_SECONDS,
          -1,
          1,
        )
      : -1;
  return {
    clip,
    seconds,
    weight,
    height: lerp(entryHeight, surface + footOffset * modelScale, contact),
    surface,
    contact,
    ripple,
  };
}

export class LandingRipples {
  readonly mesh: InstancedMesh<PlaneGeometry, ShaderMaterial>;
  private readonly phases: InstancedBufferAttribute;
  private readonly transform = new Matrix4();
  private readonly scale = new Matrix4().makeScale(6.4, 1, 5.2);
  private count = 0;

  constructor(capacity: number) {
    const geometry = new PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
    this.phases = new InstancedBufferAttribute(new Float32Array(capacity), 1);
    this.phases.setUsage(DynamicDrawUsage);
    geometry.setAttribute("phase", this.phases);
    const material = new ShaderMaterial({
      transparent: true,
      depthWrite: false,
      uniforms: {
        highlight: { value: new Color("#f4dea9") },
        wetInk: { value: new Color("#315d57") },
      },
      vertexShader: `
        attribute float phase;
        varying vec2 rippleUv;
        varying float age;

        void main() {
          rippleUv = 2.0 * uv - 1.0;
          age = phase;
          gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 highlight;
        uniform vec3 wetInk;
        varying vec2 rippleUv;
        varying float age;

        float ring(float radius, float edge, float width, float feather) {
          return 1.0 - smoothstep(width * 0.30, width + feather, abs(radius - edge));
        }

        void main() {
          float radius = length(rippleUv);
          float angle = atan(rippleUv.y, rippleUv.x);
          float feather = clamp(fwidth(radius) * 0.58, 0.009, 0.041);
          float crest = mix(0.09, 0.88, pow(age, 0.72));
          float tooth = 0.015 * cos(angle * 5.0) + 0.008 * sin(angle * 11.0);
          float stroke = 0.46 + 0.54 * smoothstep(-0.60, 0.77, cos(angle * 3.0 + 0.4));
          float echo = smoothstep(0.10, 0.38, age);
          float ink = ring(radius, crest + tooth + 0.027, 0.055, feather) * 0.40;
          ink += (1.0 - smoothstep(0.07, crest + 0.08, radius)) * (1.0 - age) * 0.24;
          float light = ring(radius, crest + tooth, 0.039, feather) * 0.83;
          light += ring(radius, crest - 0.17 + tooth, 0.034, feather) * echo * 0.43;
          float fade = smoothstep(0.0, 0.09, age) * (1.0 - smoothstep(0.44, 1.0, age));
          vec3 pigment = mix(wetInk, highlight, light / max(ink + light, 0.0001));
          gl_FragColor = vec4(pigment, (ink + light) * stroke * fade * 0.72);
          #include <colorspace_fragment>
        }
      `,
    });
    this.mesh = new InstancedMesh(geometry, material, capacity);
    this.mesh.instanceMatrix.setUsage(DynamicDrawUsage);
    this.mesh.name = "landing-water-ripples";
    this.mesh.count = 0;
    // The same small batch moves to whatever position the flock actually reaches.
    this.mesh.frustumCulled = false;
    this.mesh.visible = false;
    this.mesh.renderOrder = 3;
  }

  begin(): void {
    this.count = 0;
  }

  add(x: number, z: number, age: number, heading: number): void {
    if (age <= 0 || age >= 1) return;
    this.transform.makeRotationY(heading);
    this.transform.multiply(this.scale);
    this.transform.setPosition(x, 0.038, z);
    this.mesh.setMatrixAt(this.count, this.transform);
    this.phases.setX(this.count, age);
    this.count++;
  }

  finish(): void {
    this.mesh.count = this.count;
    this.mesh.visible = this.count > 0;
    if (this.count > 0) {
      this.mesh.instanceMatrix.needsUpdate = true;
      this.phases.needsUpdate = true;
    }
  }
}
