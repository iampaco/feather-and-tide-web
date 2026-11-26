import {
  type Box3,
  type Camera,
  Color,
  DoubleSide,
  Frustum,
  Group,
  MathUtils,
  Matrix4,
  Mesh,
  PlaneGeometry,
  ShaderMaterial,
  Vector2,
  Vector4,
} from "three";
import type { WhaleLevel } from "../levels/schema";
import { bayHeadland, bayTerraces } from "./whale-coast";
import { whaleSeabed } from "./whale-seabed";
import { whaleWaterLight } from "./whale-water-light";

export interface WhaleBayLight {
  readonly amount: { value: number };
  readonly depth: { value: number };
}

const pigment = `
  float pigmentSeed(vec2 cell) {
    vec3 p = fract(vec3(cell.xyx) * 0.1031);
    p += dot(p, p.yzx + 33.33);
    return fract((p.x + p.y) * p.z);
  }

  float wash(vec2 position) {
    vec2 cell = floor(position);
    vec2 blend = fract(position);
    blend = blend * blend * (3.0 - 2.0 * blend);
    return mix(
      mix(pigmentSeed(cell), pigmentSeed(cell + vec2(1.0, 0.0)), blend.x),
      mix(pigmentSeed(cell + vec2(0.0, 1.0)), pigmentSeed(cell + 1.0), blend.x),
      blend.y
    );
  }
`;

const bayReflections = `
  float bayReflection(vec2 position, float time) {
    vec2 p = vec2(position.x * 0.94 + position.y * 0.34,
                  position.y * 0.94 - position.x * 0.34);
    float body = wash(p * vec2(0.052, 0.18));
    float gaps = wash(p * vec2(0.21, 0.12) + vec2(time * 0.07, 0.0));
    float wave = sin(p.y * 0.92 + body * 5.0 + time * 0.74);
    float feather = smoothstep(0.44, 0.97, wave);
    float rim = smoothstep(0.87, 0.995, wave);
    return (feather * 0.57 + rim * 0.43)
         * smoothstep(0.42, 0.82, body * 0.43 + gaps * 0.57);
  }
`;

const offshoreWash = `
  uniform vec4 offshoreCourse;
  uniform vec2 surfaceMark;

  float offshoreBlend(vec2 position) {
    return smoothstep(offshoreCourse.y - 20.0, offshoreCourse.w, position.y);
  }

  float silverWater(vec2 position, float broad, float pool) {
    float approach = smoothstep(offshoreCourse.y, surfaceMark.y, position.y);
    float arrival = smoothstep(surfaceMark.y, offshoreCourse.w, position.y);
    float spine = mix(offshoreCourse.x, surfaceMark.x, approach)
                + (offshoreCourse.z - surfaceMark.x) * arrival;
    float width = mix(20.0, 56.0, offshoreBlend(position));
    float edge = abs(position.x - spine + (broad - 0.5) * 21.0) / width;
    return (1.0 - smoothstep(0.10, 1.18, edge + (pool - 0.5) * 0.21))
         * smoothstep(offshoreCourse.y - 16.0, surfaceMark.y, position.y);
  }

  vec2 offshoreStroke(vec2 position) {
    float turn = clamp((offshoreCourse.z - offshoreCourse.x)
                       / max(1.0, offshoreCourse.w - offshoreCourse.y), -0.65, 0.65);
    return vec2(position.x + position.y * turn, position.y - position.x * turn);
  }
`;

// The wash sits below the deepest pose. A thin glaze over the waterline
// tints submerged bodies while leaving their silhouettes and outlines readable.
export class WhaleOcean {
  readonly group = new Group();
  private readonly quality = { value: 1 };
  private readonly animation = { value: 0 };
  private readonly gathering = { value: 0 };
  private readonly bayExit: number;
  private readonly frustum = new Frustum();
  private readonly viewProjection = new Matrix4();
  private readonly bedTiles: { mesh: Mesh; bounds: Box3 }[] = [];
  readonly bayLight: WhaleBayLight = {
    amount: { value: 0 },
    depth: { value: 0 },
  };

  constructor(level: WhaleLevel) {
    const starts = level.segments.slice(1).map((segment) => segment.start);
    this.bayExit = starts[0] ?? level.bounds.max.z;
    const bayMouth = level.landmarks.find(({ id }) => id === "bay-exit")?.pos;
    const c2 = level.landmarks.find(
      ({ id }) => id === "second-checkpoint",
    )?.pos;
    const offshore = level.landmarks.find(
      ({ id }) => id === "offshore-marker",
    )?.pos;
    const surface = level.landmarks.find(
      ({ id }) => id === "surface-here",
    )?.pos;
    const quiet = level.zones.find(({ id }) => id === "quiet-rest");
    const shipClear = level.landmarks.find(
      ({ id }) => id === "ship-clear",
    )?.pos;
    const netMouth = level.landmarks.find(
      ({ id }) => id === "net-short-entry",
    )?.pos;
    const quietBay = quiet?.points ?? [];
    const quietBounds = quietBay.length
      ? new Vector4(
          Math.min(...quietBay.map(({ x }) => x)),
          Math.min(...quietBay.map(({ z }) => z)),
          Math.max(...quietBay.map(({ x }) => x)),
          Math.max(...quietBay.map(({ z }) => z)),
        )
      : new Vector4(0, 1e6, 0, 1e6 + 1);
    const uniforms = {
      depth: this.bayLight.depth,
      quietBounds: { value: quietBounds },
      sandReach: {
        value: new Vector4(
          shipClear?.x ?? 0,
          shipClear?.z ?? 1e6,
          netMouth?.x ?? 0,
          netMouth?.z ?? 1e6 + 145,
        ),
      },
      bayRear: { value: level.bounds.min.z },
      waterBounds: {
        value: new Vector4(
          level.bounds.min.x,
          level.bounds.min.z,
          level.bounds.max.x,
          level.bounds.max.z,
        ),
      },
      selectedQuality: this.quality,
      time: this.animation,
      gathering: this.gathering,
      sectionStart: { value: starts },
      bayOrigin: { value: new Vector2(level.spawn.x, level.spawn.z) },
      bayMouth: {
        value: new Vector2(
          bayMouth?.x ?? level.spawn.x,
          bayMouth?.z ?? this.bayExit,
        ),
      },
      pigments: {
        value: [
          new Color("#528f96"),
          new Color("#3d7180"),
          new Color("#527d70"),
          new Color("#567a88"),
          new Color("#5b819c"),
        ],
      },
      paper: { value: new Color("#f4e7cd") },
      horizon: { value: new Color("#b2cacb") },
      shallows: { value: new Color("#bdd3af") },
      offshoreCourse: {
        value:
          c2 &&
          offshore &&
          surface &&
          c2.z < surface.z &&
          surface.z < offshore.z
            ? new Vector4(c2.x, c2.z, offshore.x, offshore.z)
            : new Vector4(0, 1e6, 0, 1e6 + 1),
      },
      surfaceMark: {
        value: new Vector2(surface?.x ?? 0, surface?.z ?? 1e6 + 0.5),
      },
      offshoreBlue: { value: new Color("#555d80") },
      offshoreLight: { value: new Color("#f0d3a6") },
    };
    const vertexShader = `
      varying vec2 sea;
      varying float viewDepth;
      varying float seaHeight;
      void main() {
        vec4 world = modelMatrix * vec4(position, 1.0);
        vec4 view = viewMatrix * world;
        sea = world.xz;
        seaHeight = world.y;
        viewDepth = -view.z;
        gl_Position = projectionMatrix * view;
      }
    `;
    const floorMaterial = new ShaderMaterial({
      uniforms,
      vertexShader,
      side: DoubleSide,
      fragmentShader: `
        varying vec2 sea;
        varying float viewDepth;
        varying float seaHeight;
        uniform float selectedQuality;
        uniform float sectionStart[4];
        uniform vec3 pigments[5];
        uniform vec3 paper;
        uniform vec3 horizon;
        uniform vec3 shallows;
        uniform vec2 bayOrigin;
        uniform vec2 bayMouth;
        uniform vec3 offshoreBlue;
        uniform vec3 offshoreLight;
        uniform float depth;
        uniform float time;
        uniform float bayRear;
        uniform vec4 quietBounds;
        uniform vec4 sandReach;
        ${pigment}
        ${offshoreWash}
        ${whaleWaterLight}

        void main() {
          float broad = wash(sea * vec2(0.041, 0.053));
          float pool = wash(sea * vec2(0.11, 0.086) + broad * 2.8);
          float blooms = smoothstep(0.30, 0.73, broad);
          float bayArt = 1.0 - smoothstep(sectionStart[0] - 52.0, sectionStart[0] + 42.0, sea.y);
          vec3 ocean = pigments[0];
          for (int i = 0; i < 4; i++) {
            ocean = mix(
              ocean, pigments[i + 1],
              smoothstep(sectionStart[i] - 34.0, sectionStart[i] + 45.0, sea.y)
            );
          }
          float descent = smoothstep(0.10, 1.95, depth);
          float shallowView = smoothstep(0.10, 0.92, depth) * (1.0 - smoothstep(1.14, 1.92, depth));
          float deepView = smoothstep(1.16, 1.95, depth);
          float clearBed = (1.0 - descent * 0.76) * (1.0 - smoothstep(88.0, 161.0, viewDepth));
          float pigmentEdge = smoothstep(0.37, 0.50, pool) - smoothstep(0.51, 0.67, pool);
          vec3 color = ocean * (0.79 + blooms * 0.21 + pool * 0.16 - pigmentEdge * 0.09);
          color *= 1.0 - 0.12 * smoothstep(11.0, 13.5, -seaHeight);
          vec2 quietCenter = (quietBounds.xy + quietBounds.zw) * 0.5;
          vec2 quietRadius = (quietBounds.zw - quietBounds.xy) * 0.5 + vec2(24.0, 33.0);
          vec2 toReef = abs(sea - quietCenter) / quietRadius;
          float reef = 1.0 - smoothstep(0.34, 1.0, max(toReef.x, toReef.y) + (pool - 0.5) * 0.22);
          color = mix(color, shallows * vec3(0.52, 0.89, 0.96), reef * (0.58 + 0.25 * broad));
          float shelf = smoothstep(sandReach.y - 16.0, sandReach.y + 38.0, sea.y)
                     * (1.0 - smoothstep(sandReach.w - 34.0, sandReach.w + 24.0, sea.y));
          float along = smoothstep(sandReach.y, sandReach.w, sea.y);
          float channel = mix(sandReach.x, sandReach.z, along) + 13.0 * sin(along * 7.2);
          float bank = smoothstep(12.0, 49.0, abs(sea.x - channel) + (broad - 0.5) * 17.0);
          float grain = wash(sea * vec2(0.17, 0.21));
          vec3 sand = mix(vec3(0.17, 0.30, 0.24), vec3(0.59, 0.49, 0.28), smoothstep(0.15, 0.86, broad * 0.78 + grain * 0.22));
          color = mix(color, mix(vec3(0.035, 0.204, 0.213), sand, bank), shelf * (0.76 + 0.22 * shallowView));
          float openWater = offshoreBlend(sea);
          if (selectedQuality > 0.5) {
            float feather = wash(sea * 0.31 + pool * 1.1);
            float grain = pigmentSeed(floor(sea * 7.0)) - 0.5;
            color += ((feather - 0.5) * 0.021 + grain * 0.020) * (1.0 - openWater * 0.74);
          }
          // The light samples the same world height field as the sand and rock.
          float refraction = 0.0;
          if (max(max(bayArt, reef), shelf) * clearBed > 0.01 || shallowView > 0.01) {
            refraction = whaleRefractedLight(vec3(sea.x, seaHeight, sea.y), time);
            color += paper * refraction * reef * clearBed * smoothstep(0.37, 0.80, pool) * 0.056;
            color += vec3(0.49, 0.85, 0.77) * refraction * clearBed
                   * (shelf * bank * 0.12 + shallowView * (0.12 + 0.17 * blooms));
          }
          if (bayArt > 0.0) {
            // Pigment follows the actual sand relief, including the apron in the turn.
            float relief = smoothstep(-11.0, -8.35, seaHeight);
            float sand = max(
              smoothstep(-10.98, -9.28, seaHeight + (pool - 0.5) * 0.34),
              (1.0 - smoothstep(0.0, 39.0, sea.y - bayRear)) * 0.46
            );
            vec3 teal = mix(vec3(0.033, 0.194, 0.243), vec3(0.079, 0.32, 0.350), blooms);
            float sandbank = 1.0 - smoothstep(-39.0, -11.0, sea.x - bayOrigin.x);
            vec3 goldenSand = mix(vec3(0.43, 0.43, 0.27), vec3(0.79, 0.69, 0.46), pool);
            vec3 reefWash = mix(vec3(0.20, 0.39, 0.31), vec3(0.40, 0.62, 0.51), pool);
            vec3 beachWash = mix(reefWash, goldenSand, sandbank);
            vec3 cove = mix(teal, beachWash, sand);
            float opening = smoothstep(bayMouth.y - 142.0, bayMouth.y + 18.0, sea.y);
            float windowWidth = mix(16.0, 78.0, opening);
            float window = 1.0 - smoothstep(windowWidth * 0.1, windowWidth, abs(sea.x - bayMouth.x));
            cove = mix(cove, vec3(0.23, 0.44, 0.46), window * opening * (1.0 - sand) * 0.73);
            float granulation = wash(sea * vec2(0.22, 0.17) + broad * 1.8);
            float seam = sin(seaHeight * 3.6 + broad * 5.4 + sea.y * 0.083);
            vec3 shelfPaint = mix(vec3(0.086, 0.21, 0.23), vec3(0.54, 0.54, 0.36), granulation);
            cove = mix(cove, shelfPaint, relief * (0.27 + 0.16 * seam));
            float deposit = smoothstep(0.30, 0.48, granulation) - smoothstep(0.52, 0.68, granulation);
            cove *= 1.0 - 0.072 * deposit * (0.38 + 0.62 * sand);
            float lightPool = smoothstep(0.26, 0.76, pool) * (0.40 + 0.60 * sand);
            lightPool *= 0.35 + 0.65 * smoothstep(0.24, 0.58, broad + granulation * 0.18);
            float diveLight = mix(0.46, 1.12, smoothstep(0.06, 0.78, depth));
            cove += paper * refraction * lightPool * diveLight * clearBed * (0.11 + 0.15 * relief);
            if (selectedQuality > 0.5) {
              float grain = pigmentSeed(floor(sea * 6.5)) - 0.5;
              cove += ((granulation - 0.5) * 0.027 + grain * 0.013) * clearBed;
            }
            color = mix(color, cove, bayArt);
          }
          color = whaleThroughWater(color, seaHeight, viewDepth, depth, 0.82);
          if (openWater > 0.0) {
            // The long silver wash softens at the shoulders of the surface route.
            vec2 stroke = offshoreStroke(sea);
            float swell = wash(stroke * vec2(0.012, 0.019));
            float bands = wash(stroke * vec2(0.014, 0.068) + swell * 2.4);
            float lightPath = silverWater(sea, swell, bands);
            float cloud = smoothstep(0.24, 0.79, swell * 0.38 + bands * 0.62);
            vec3 blue = mix(offshoreBlue * 0.78, horizon, cloud * 0.32);
            float reflectedSky = lightPath * (0.50 + cloud * 0.44) * (1.0 - descent * 0.85);
            vec3 reflected = mix(blue, offshoreLight, reflectedSky);
            reflected = whaleThroughWater(reflected, seaHeight, viewDepth, depth, 0.74);
            color = mix(color, reflected, openWater * 0.94);
          }
          color = mix(color, vec3(0.023, 0.047, 0.108) + color * vec3(0.23, 0.52, 0.79), deepView * 0.62);
          vec3 distanceTint = mix(horizon, vec3(0.024, 0.102, 0.181), descent);
          color = mix(color, distanceTint, smoothstep(98.0, 177.0, viewDepth) * (0.46 + descent * 0.18));
          gl_FragColor = vec4(color, 1.0);
          #include <colorspace_fragment>
        }
      `,
    });
    const glazeMaterial = new ShaderMaterial({
      uniforms,
      vertexShader,
      transparent: true,
      depthWrite: false,
      side: DoubleSide,
      fragmentShader: `
        varying vec2 sea;
        varying float viewDepth;
        uniform float time;
        uniform float depth;
        uniform float bayRear;
        uniform vec4 waterBounds;
        uniform float gathering;
        uniform float sectionStart[4];
        uniform float selectedQuality;
        uniform vec2 bayOrigin;
        uniform vec3 paper;
        ${pigment}
        ${bayReflections}
        ${offshoreWash}
        void main() {
          float bloom = wash(sea * vec2(0.045, 0.067));
          float breadth = wash(sea * vec2(0.09, 0.17) + bloom * 1.5);
          float distanceFade = 1.0 - smoothstep(109.0, 177.0, viewDepth);
          float surfaceView = 1.0 - smoothstep(0.0, 1.19, depth);
          float bayArt = 1.0 - smoothstep(sectionStart[0] - 52.0, sectionStart[0] + 42.0, sea.y);
          vec2 bay = sea - bayOrigin;
          float shore = 1.0 - smoothstep(6.0, 26.0, sea.y - bayRear);
          float outerWash = smoothstep(35.0, 59.0, abs(bay.x + sin(bay.y * 0.023) * 12.0));
          outerWash *= 1.0 - smoothstep(sectionStart[0] - 76.0, sectionStart[0] + 9.0, sea.y);
          float seam = abs(sin(sea.y * 0.43 + bloom * 3.8 + time * 0.24));
          float edge = (1.0 - smoothstep(0.06, 0.28, seam)) * smoothstep(0.43, 0.84, breadth);
          float glint = edge * max(shore * 0.86, outerWash * 0.47);
          float film = smoothstep(0.41, 0.86, breadth) * (0.057 + 0.097 * bloom);
          float opacity = 0.040 + film * surfaceView + glint * 0.30 * surfaceView;
          vec3 washColor = mix(vec3(0.11, 0.34, 0.44), paper, glint * 0.86 + bloom * surfaceView * 0.18);
          float haze = smoothstep(0.35, 1.97, depth) * smoothstep(86.0, 139.0, viewDepth);
          opacity = opacity * distanceFade + haze * 0.33;
          washColor = mix(washColor, vec3(0.07, 0.25, 0.36), haze);
          float openWater = offshoreBlend(sea);
          if (openWater > 0.0) {
            vec2 drift = offshoreStroke(sea);
            float swell = wash(drift * vec2(0.012, 0.019));
            float lightPath = silverWater(sea, swell, breadth);
            float ridge = sin(drift.y * 0.49 + swell * 4.9 + (bloom - 0.5) * 1.65 + time * 0.42);
            float lengths = smoothstep(0.26, 0.78, 0.53 * swell + 0.47 * breadth);
            float highlight = lightPath * smoothstep(0.49, 0.98, ridge) * lengths;
            if (selectedQuality > 0.5) {
              float broken = wash(drift * vec2(0.045, 0.13));
              highlight *= mix(0.44, 1.0, smoothstep(0.34, 0.77, broken));
            }
            float mirror = highlight * surfaceView * distanceFade * mix(1.0, 0.54, gathering);
            opacity = mix(opacity, 0.021 + mirror * 0.35 + haze * 0.17, openWater);
            washColor = mix(washColor, mix(vec3(0.65, 0.75, 0.87), vec3(1.0, 0.85, 0.65), lightPath), openWater * 0.85);
          }
          if (bayArt > 0.0) {
            float sunlight = smoothstep(0.27, 0.86, bloom);
            float glimmer = bayReflection(sea, time) * (0.30 + 0.70 * sunlight);
            vec3 reflection = mix(vec3(0.12, 0.38, 0.43), paper, glimmer * 0.81 + 0.11);
            reflection = mix(reflection, vec3(0.043, 0.19, 0.30), haze);
            float veil = 0.024 + sunlight * 0.043 * surfaceView + glimmer * 0.30 * surfaceView;
            opacity = mix(opacity, veil * distanceFade + haze * 0.17, bayArt);
            washColor = mix(washColor, reflection, bayArt);
          }
          // A broken outer swell sits beyond the bounds. Keeping it sparse
          // and outside the fairway gives an edge reference without a hazard stripe.
          float beyond = max(max(waterBounds.x - sea.x, sea.x - waterBounds.z), sea.y - waterBounds.w);
          if (beyond > 0.0) {
            float outer = smoothstep(0.0, 18.0, beyond);
            float swell = 1.0 - smoothstep(0.24, 0.78, abs(sin(beyond * 0.155 + bloom * 3.7 + time * 0.24)));
            float breakers = swell * smoothstep(0.46, 0.83, breadth) * outer;
            opacity += distanceFade * outer * (0.10 + breakers * 0.09 * surfaceView);
            washColor = mix(washColor, mix(vec3(0.035, 0.14, 0.23), paper, breakers * 0.62), outer * 0.72);
          }
          gl_FragColor = vec4(washColor, opacity);
          #include <colorspace_fragment>
        }
      `,
    });

    const { min, max } = level.bounds;
    const plane = new PlaneGeometry(
      max.x - min.x + 1100,
      max.z - min.z + 1100,
    ).rotateX(-Math.PI / 2);
    const floor = new Group();
    floor.name = "Painted seabed";
    for (const tile of whaleSeabed(level, c2?.z ?? max.z)) {
      const mesh = new Mesh(tile, floorMaterial);
      tile.computeBoundingBox();
      if (tile.boundingBox)
        this.bedTiles.push({ mesh, bounds: tile.boundingBox });
      floor.add(mesh);
    }
    const terraces = new Mesh(bayTerraces(level), floorMaterial);
    terraces.name = "W0 submerged terraces";
    const shoreBed = new Mesh(bayHeadland(level, true), floorMaterial);
    shoreBed.name = "W0 submerged shore";
    const glaze = new Mesh(plane, glazeMaterial);
    glaze.position.set((min.x + max.x) * 0.5, 0, (min.z + max.z) * 0.5);
    glaze.renderOrder = -6;
    this.group.add(floor, shoreBed, terraces, glaze);
  }

  cullSeabed(camera: Camera): void {
    // Each tile spans the sea. A sphere around that width keeps distant
    // tiles alive long after their flat world-space bounds leave the view.
    this.viewProjection.multiplyMatrices(
      camera.projectionMatrix,
      camera.matrixWorldInverse,
    );
    this.frustum.setFromProjectionMatrix(this.viewProjection);
    for (const { mesh, bounds } of this.bedTiles)
      mesh.visible = this.frustum.intersectsBox(bounds);
  }

  update(
    seconds: number,
    depth: number,
    z: number,
    low: boolean,
    reduced: boolean,
    gathering: number,
  ): void {
    this.bayLight.depth.value = depth;
    this.bayLight.amount.value =
      1 - MathUtils.smoothstep(z, this.bayExit - 68, this.bayExit - 6);
    this.quality.value = Number(!low);
    this.animation.value = reduced ? 0 : seconds;
    this.gathering.value = MathUtils.smoothstep(gathering, 0, 0.28);
  }
}
