import {
  Color,
  MathUtils,
  Mesh,
  PlaneGeometry,
  ShaderMaterial,
  Vector3,
  type Texture,
} from "three";

interface SkyPalette {
  readonly z: number;
  readonly horizon: Color;
  readonly zenith: Color;
  readonly light: Color;
}

const palettes = [
  { z: 15, colors: ["#ddd8be", "#a9b5bd", "#efd0a2"] },
  { z: 143, colors: ["#cdd7c5", "#9fbabf", "#e9dcb3"] },
  { z: 309, colors: ["#c2cfcc", "#909db5", "#d4e1d9"] },
  { z: 465, colors: ["#ccd6c8", "#a1b4bc", "#dedbc0"] },
  { z: 590, colors: ["#bfcfc9", "#92adb8", "#e2dfc6"] },
  { z: 715, colors: ["#ced4bf", "#a7b2b1", "#e7d8ae"] },
  { z: 835, colors: ["#e8d9b7", "#b3b5b4", "#f2cf98"] },
].map(({ z, colors: [horizon, zenith, light] }): SkyPalette => ({
  z,
  horizon: new Color(horizon),
  zenith: new Color(zenith),
  light: new Color(light),
}));

export const migrationSun = new Vector3(-20, 46, -8);

export function createSurfaceUniforms() {
  return {
    horizon: { value: new Color("#ddd8be") },
    skyLight: { value: new Color("#efd0a2") },
    sunDirection: { value: migrationSun.clone().normalize() },
    skyPigment: { value: null as Texture | null },
  };
}

export type AtmosphericUniforms = ReturnType<typeof createSurfaceUniforms>;

export const distanceWash = `
  uniform vec3 horizon;

  vec3 aerialPerspective(vec3 color, float viewDepth, float strength) {
    float washAmount = smoothstep(102.0, 232.0, viewDepth);
    return mix(color, horizon, washAmount * strength);
  }
`;

export const skyWash = `
  uniform sampler2D skyPigment;

  vec3 paintedSky(vec3 direction) {
    // Bounded projection in world space has no longitude seam.
    vec2 uv = vec2(direction.x + direction.z * 0.37, direction.y + direction.z * 0.52);
    return texture2D(skyPigment, uv * vec2(0.29, 0.30) + 0.5).rgb;
  }
`;

export class MigrationAtmosphere {
  readonly surfaceUniforms = createSurfaceUniforms();
  private readonly frameUniforms = {
    zenith: { value: new Color() },
    aspect: { value: 1 },
    pigmentStrength: { value: 0.3 },
  };
  readonly sky = new Mesh(
    new PlaneGeometry(2, 2),
    new ShaderMaterial({
      uniforms: {
        ...this.surfaceUniforms,
        ...this.frameUniforms,
      },
      depthWrite: false,
      vertexShader: `
        uniform float aspect;
        varying vec3 skyDirection;
        void main() {
          // Pan the painted backdrop in world space, including across the yaw seam.
          skyDirection = transpose(mat3(viewMatrix)) *
            vec3(position.x * aspect * 0.48, position.y * 0.48, -1.0);
          gl_Position = vec4(position.xy, 1.0, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 horizon, zenith, skyLight, sunDirection;
        uniform float pigmentStrength;
        varying vec3 skyDirection;
        ${skyWash}
        void main() {
          vec3 direction = normalize(skyDirection);
          float height = smoothstep(-0.18, 0.72, direction.y);
          float sun = pow(max(0.0, dot(direction, sunDirection)), 6.0);
          vec3 color = mix(mix(horizon, zenith, height), skyLight, sun * 0.5);
          color = mix(color, paintedSky(direction), pigmentStrength * smoothstep(-0.50, 0.45, direction.y));
          gl_FragColor = vec4(color, 1.0);
          #include <colorspace_fragment>
        }
      `,
    }),
  );

  constructor() {
    this.sky.name = "Migration sky";
    this.sky.frustumCulled = false;
    // Fill only uncovered pixels after opaque scenery has written its depth.
    this.sky.renderOrder = 10;
    this.update(0, 1, false);
  }

  setPigment(texture: Texture): void {
    this.surfaceUniforms.skyPigment.value = texture;
  }

  update(z: number, aspect: number, low: boolean): void {
    const first = palettes[0];
    if (!first) return;
    const index = palettes.findLastIndex((palette) => palette.z <= z);
    const before = palettes[index] ?? first;
    const after = palettes[index + 1] ?? before;
    const t = before === after ? 0 : MathUtils.smoothstep(z, before.z, after.z);
    const { horizon, skyLight } = this.surfaceUniforms;
    horizon.value.copy(before.horizon).lerp(after.horizon, t);
    this.frameUniforms.zenith.value.copy(before.zenith).lerp(after.zenith, t);
    skyLight.value.copy(before.light).lerp(after.light, t);
    this.frameUniforms.aspect.value = aspect;
    this.frameUniforms.pigmentStrength.value = low ? 0.14 : 0.3;
  }
}
