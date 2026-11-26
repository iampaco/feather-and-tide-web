import { Color, Group, Mesh, MeshBasicMaterial, PlaneGeometry } from "three";
import type { ReindeerLevel } from "../levels/schema";

const washes = ["#e3e4e8", "#d3d9d8", "#d8d6c7", "#cbb99f", "#cbd6b3"];
const undertones = ["#a9b4cc", "#a9b8bd", "#b3b3a0", "#a78e7b", "#97ad97"];
const margin = 103;

// The tiles share one world-space paint field. The culvert is the only cut in
// the playable surface, and its apron follows the authoritative road profile.
export class ReindeerTerrain {
  readonly group = new Group();
  private readonly detail = { value: 1 };

  constructor(level: ReindeerLevel) {
    const { min, max } = level.bounds;
    const { culvert } = level.road;
    const material = new MeshBasicMaterial();
    const transitions = level.segments.slice(1).map(({ start }) => start);
    material.onBeforeCompile = (shader) => {
      shader.uniforms.paperDetail = this.detail;
      shader.uniforms.transitions = { value: transitions };
      shader.uniforms.washes = {
        value: washes.map((paint) => new Color(paint)),
      };
      shader.uniforms.undertones = {
        value: undertones.map((paint) => new Color(paint)),
      };
      shader.vertexShader = shader.vertexShader
        .replace(
          "#include <common>",
          "#include <common>\nvarying vec2 groundPoint;",
        )
        .replace(
          "#include <begin_vertex>",
          `
          #include <begin_vertex>
          groundPoint = (modelMatrix * vec4(position, 1.0)).xz;
        `,
        );
      shader.fragmentShader = shader.fragmentShader
        .replace(
          "#include <common>",
          `#include <common>
          varying vec2 groundPoint;
          uniform float paperDetail;
          uniform float transitions[4];
          uniform vec3 washes[5];
          uniform vec3 undertones[5];

          float seed(vec2 cell) {
            vec3 p = fract(vec3(cell.xyx) * 0.1031);
            p += dot(p, p.yzx + 33.33);
            return fract((p.x + p.y) * p.z);
          }

          float stain(vec2 p) {
            vec2 i = floor(p), w = fract(p);
            w = w * w * (3.0 - 2.0 * w);
            return mix(mix(seed(i), seed(i + vec2(1,0)), w.x),
                       mix(seed(i + vec2(0,1)), seed(i + vec2(1,1)), w.x), w.y);
          }
        `,
        )
        .replace(
          "#include <color_fragment>",
          `
          #include <color_fragment>
          vec2 p = groundPoint;
          float wash = stain(vec2(p.x * 0.045 - p.y * 0.026, p.y * 0.058));
          float bloom = stain(p * vec2(0.15, 0.21) + wash * 1.4);
          vec3 paper = washes[0];
          vec3 ink = undertones[0];
          for (int i = 0; i < 4; i++) {
            float season = smoothstep(-26.0, 26.0,
              p.y - transitions[i] + (wash - 0.5) * 30.0);
            paper = mix(paper, washes[i + 1], season);
            ink = mix(ink, undertones[i + 1], season);
          }
          float pool = wash * 0.64 + bloom * 0.36;
          float tide = 1.0 - smoothstep(0.013, 0.075, abs(pool - 0.45));
          vec3 paint = mix(paper, ink, 0.50 * (1.0 - smoothstep(0.24, 0.73, pool)));
          paint = mix(paint, ink, 0.09 * tide);
          if (paperDetail > 0.5) {
            vec2 grainPoint = p * 5.2;
            vec2 footprint = fwidth(grainPoint);
            float tooth = 1.0 - smoothstep(0.45, 1.35, max(footprint.x, footprint.y));
            float fleck = seed(floor(grainPoint)) - 0.5;
            paint += fleck * tooth * 0.032;
          }
          diffuseColor.rgb = paint;
        `,
        );
    };
    this.group.name = "Seasonal ground wash";
    const left = min.x - margin;
    const right = max.x + margin;
    const tile = (x0: number, x1: number, z0: number, z1: number) => {
      const floor = new Mesh(
        new PlaneGeometry(x1 - x0, z1 - z0).rotateX(-Math.PI / 2),
        material,
      );
      floor.position.set((x0 + x1) / 2, 0, (z0 + z1) / 2);
      this.group.add(floor);
    };
    const span = (z0: number, z1: number) => {
      const divisions = Math.ceil((z1 - z0) / 104);
      for (let i = 0; i < divisions; i++)
        tile(
          left,
          right,
          z0 + ((z1 - z0) * i) / divisions,
          z0 + ((z1 - z0) * (i + 1)) / divisions,
        );
    };
    span(min.z - margin, culvert.near);
    tile(left, culvert.left, culvert.near, culvert.far);
    tile(culvert.right, right, culvert.near, culvert.far);
    span(culvert.far, max.z + margin);
  }

  update(low: boolean): void {
    this.detail.value = Number(!low);
  }
}
