import { Color, ShaderMaterial } from "three";
import {
  distanceWash,
  skyWash,
  type AtmosphericUniforms,
} from "./migrationAtmosphere";

export function waterMaterial(
  color: string,
  prior: string,
  low: boolean,
): ShaderMaterial {
  return new ShaderMaterial({
    uniforms: {
      color: { value: new Color(color) },
      prior: { value: new Color(prior) },
    },
    defines: low ? { LOW: 1 } : {},
    vertexShader: `
      varying vec2 paint;
      varying float along;
      void main() {
        vec4 world = modelMatrix * vec4(position, 1.0);
        paint = world.xz;
        along = 1.0 - uv.y;
        gl_Position = projectionMatrix * viewMatrix * world;
      }
    `,
    fragmentShader: `
      uniform vec3 color;
      uniform vec3 prior;
      varying vec2 paint;
      varying float along;

      float hash(vec2 tile) {
        vec3 p = fract(vec3(tile.xyx) * 0.1031);
        p += dot(p, p.yzx + 33.33);
        return fract((p.x + p.y) * p.z);
      }

      float watercolor(vec2 p) {
        vec2 j = floor(p), f = fract(p);
        f = f * f * (3.0 - 2.0 * f);
        return mix(mix(hash(j), hash(j + vec2(1,0)), f.x),
                   mix(hash(j + vec2(0,1)), hash(j + vec2(1,1)), f.x), f.y);
      }

      void main() {
        float broad = watercolor(paint * vec2(0.048, 0.073));
        float grain = hash(floor(gl_FragCoord.xy * 0.73)) - 0.5;
        float ripple = watercolor(paint * vec2(0.073, 1.36) + broad * 1.4);
        #ifndef LOW
          ripple = ripple * 0.62 + watercolor(paint * vec2(0.142, 3.24) + broad) * 0.38;
        #endif
        float glint = smoothstep(0.52, 0.91, ripple) * smoothstep(0.22, 0.74, broad);
        vec3 surface = mix(prior, color, smoothstep(0.0, 0.14, along));
        surface *= 0.86 + broad * 0.27;
        surface = mix(surface, vec3(0.86, 0.73, 0.46), glint * 0.28);
        surface += grain * 0.039;
        gl_FragColor = vec4(surface, 1.0);
        #include <colorspace_fragment>
      }
    `,
  });
}

const pigment = `
  float paperHash(vec2 cell) {
    vec3 p = fract(vec3(cell.xyx) * 0.1031);
    p += dot(p, p.yzx + 33.33);
    return fract((p.x + p.y) * p.z);
  }

  float wash(vec2 point) {
    vec2 cell = floor(point);
    vec2 f = fract(point);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(paperHash(cell), paperHash(cell + vec2(1.0, 0.0)), f.x),
      mix(paperHash(cell + vec2(0.0, 1.0)), paperHash(cell + 1.0), f.x),
      f.y
    );
  }

  float paperGrain(vec2 point) {
    vec2 positionOnPaper = point * 4.1;
    float pixelSize = max(length(dFdx(positionOnPaper)), length(dFdy(positionOnPaper)));
    return (paperHash(floor(positionOnPaper)) - 0.5) * (1.0 - smoothstep(0.55, 1.6, pixelSize));
  }
`;

export function riverWaterMaterial(
  low: boolean,
  atmosphere: AtmosphericUniforms,
): ShaderMaterial {
  return new ShaderMaterial({
    defines: low ? { LOW: 1 } : {},
    uniforms: atmosphere,
    vertexShader: `
      attribute float bed;
      attribute vec3 deepPigment;
      attribute vec3 shallowPigment;
      attribute vec3 reflectedLight;
      attribute vec2 localFlow;
      varying vec2 site;
      varying float depth;
      varying vec3 deep;
      varying vec3 shallow;
      varying vec3 sunlight;
      varying vec2 flow;
      varying float viewDepth;

      void main() {
        site = position.xz;
        depth = -bed;
        deep = deepPigment;
        shallow = shallowPigment;
        sunlight = reflectedLight;
        flow = localFlow;
        vec4 view = modelViewMatrix * vec4(position, 1.0);
        viewDepth = -view.z;
        gl_Position = projectionMatrix * view;
      }
    `,
    fragmentShader: `
      varying vec2 site;
      varying float depth;
      varying vec3 deep;
      varying vec3 shallow;
      varying vec3 sunlight;
      varying vec2 flow;
      varying float viewDepth;
      uniform vec3 skyLight, sunDirection;

      ${pigment}
      ${distanceWash}
      #ifndef LOW
        ${skyWash}
      #endif

      void main() {
        float pooling = wash(site * vec2(0.051, 0.075));
        float bedWeight = smoothstep(0.15, 4.35, depth + (pooling - 0.5) * 0.28);
        vec3 color = mix(shallow, deep, bedWeight);
        color *= 0.88 + 0.22 * pooling;

        // Light is broken into overlapping patches instead of one stripe field.
        vec2 rippleSite = vec2(site.x * 0.21 + site.y * 0.033, (site.y + site.x * flow.x) * 1.08);
        float ripples = wash(rippleSite + pooling * 1.4);
        #ifndef LOW
          ripples = mix(ripples, wash(rippleSite * 1.76 + vec2(5.6, 0.0)), 0.25);
        #endif
        float brokenLight = smoothstep(0.62, 0.9, ripples);
        float lightPool = smoothstep(0.30, 0.82, wash(site * 0.029 + vec2(13.0, 2.4)));
        vec3 eyeRay = vec3(viewMatrix[0].z, viewMatrix[1].z, viewMatrix[2].z);
        vec3 reflectedRay = eyeRay * vec3(-1.0, 1.0, -1.0);
        float reflection = pow(max(0.0, dot(reflectedRay, sunDirection)), 2.0);
        vec3 glint = mix(sunlight, skyLight, 0.24 + 0.32 * reflection);
        color = mix(color, horizon, (1.0 - eyeRay.y) * (0.09 + 0.10 * pooling));
        #ifndef LOW
          vec3 cloudDirection = normalize(reflectedRay + vec3(pooling - 0.5, 0.25, lightPool - 0.5) * 0.6);
          glint = mix(glint, paintedSky(cloudDirection), 0.24);
        #endif
        color = mix(color, glint, brokenLight * lightPool * flow.y);
        float wetRim = (1.0 - smoothstep(0.16, 0.54, depth)) * (0.44 + 0.56 * pooling);
        color = mix(color, shallow * 0.78, wetRim * 0.42);
        // The sheltered opening shows wet silt and small breaks of reflected sky
        // at the waterline. Both marks follow the actual bed depth.
        if (site.y < 105.0) {
          float morning = 1.0 - smoothstep(63.0, 105.0, site.y);
          float silt = smoothstep(0.24, 0.73, pooling) * wetRim;
          color = mix(color, shallow * vec3(0.65, 0.74, 0.66), morning * silt * 0.52);
          float sill = smoothstep(0.08, 0.22, depth) * (1.0 - smoothstep(0.26, 0.56, depth));
          float rimLight = smoothstep(0.52, 0.81, ripples) * sill * (1.0 - pooling);
          color = mix(color, glint, morning * rimLight * 0.58);
        }
        #ifndef LOW
          color += paperGrain(site) * 0.023;
        #endif
        gl_FragColor = vec4(aerialPerspective(max(color, vec3(0.0)), viewDepth, 0.64), 1.0);
        #include <colorspace_fragment>
      }
    `,
  });
}

export function riverBankMaterial(
  low: boolean,
  atmosphere: AtmosphericUniforms,
): ShaderMaterial {
  return new ShaderMaterial({
    defines: low ? { LOW: 1 } : {},
    uniforms: atmosphere,
    vertexShader: `
      attribute vec3 earthPigment;
      attribute vec3 rockPigment;
      attribute vec3 wetPigment;
      varying vec3 site;
      varying vec3 slope;
      varying vec3 earth;
      varying vec3 rock;
      varying vec3 wet;
      varying float viewDepth;

      void main() {
        site = position;
        slope = normal;
        earth = earthPigment;
        rock = rockPigment;
        wet = wetPigment;
        vec4 view = modelViewMatrix * vec4(position, 1.0);
        viewDepth = -view.z;
        gl_Position = projectionMatrix * view;
      }
    `,
    fragmentShader: `
      varying vec3 site;
      varying vec3 slope;
      varying vec3 earth;
      varying vec3 rock;
      varying vec3 wet;
      varying float viewDepth;
      uniform vec3 sunDirection;

      ${pigment}
      ${distanceWash}

      void main() {
        vec3 normal = normalize(slope);
        float pooling = wash(site.xz * 0.088 + site.y * 0.036);
        float bloom = wash(site.xz * 0.23 + pooling * 0.8);
        float stone = smoothstep(0.075, 0.42, 1.0 - normal.y + (pooling - 0.5) * 0.12);
        float damp = 1.0 - smoothstep(0.04, 0.68, site.y + (bloom - 0.5) * 0.3);
        vec3 color = mix(mix(earth, rock, stone), wet, damp);
        float growth = smoothstep(0.36, 0.77, wash(site.xz * 0.059 + vec2(29.0, 8.0)));
        vec3 moss = color * vec3(0.64, 0.9, 0.71);
        color = mix(color, moss, growth * (1.0 - damp) * (1.0 - stone) * 0.48);
        float strata = wash(vec2(0.19 * site.x + 0.075 * site.z, site.y * 1.65 + site.z * 0.009));
        color *= 0.83 + 0.23 * pooling + 0.09 * bloom + stone * (strata - 0.5) * 0.29;
        float light = dot(normal, sunDirection);
        color *= 0.72 + 0.3 * light;
        #ifndef LOW
          color += paperGrain(site.xz + site.y * 0.34) * 0.027;
        #endif
        gl_FragColor = vec4(aerialPerspective(max(color, vec3(0.0)), viewDepth, 0.84), 1.0);
        #include <colorspace_fragment>
      }
    `,
  });
}
