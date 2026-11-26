import { DoubleSide, Mesh, RingGeometry, ShaderMaterial } from "three";
import type { GooseState } from "../core/game";
import { GOOSE, rescueApproach } from "../simulation/goose";
import { leaderOf } from "../simulation/world";
import { gooseRescue } from "./goose-companions";

type TerrainHeight = (x: number, z: number) => number;

export class RescueRing {
  private readonly geometry = new RingGeometry(
    GOOSE.rescueRadius - 0.63,
    GOOSE.rescueRadius + 0.63,
    80,
  ).rotateX(-Math.PI / 2);
  private readonly uniforms = {
    radius: { value: GOOSE.rescueRadius },
    progress: { value: 0 },
    approach: { value: 0 },
  };
  private readonly material = new ShaderMaterial({
    uniforms: this.uniforms,
    side: DoubleSide,
    transparent: true,
    depthWrite: false,
    vertexShader: `
      varying vec2 ring;
      void main() {
        ring = position.xz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform float radius;
      uniform float progress;
      uniform float approach;
      varying vec2 ring;
      void main() {
        float offset = abs(length(ring) - radius);
        float rim = 1.0 - smoothstep(0.45, 0.60, offset);
        float stroke = 1.0 - smoothstep(0.20, 0.34, offset);
        float angle = fract(atan(ring.x, -ring.y) / 6.2831853 + 1.0);
        float dash = 1.0 - smoothstep(0.60, 0.78, fract(angle * 16.0));
        float activeArc = step(2.0, approach) * step(angle, progress);
        vec3 color = approach > 0.5 ? vec3(0.96, 0.67, 0.27) : vec3(0.93, 0.83, 0.61);
        vec3 ink = mix(vec3(0.09, 0.14, 0.12), color, stroke);
        ink = mix(ink, vec3(0.68, 0.97, 0.83), activeArc * stroke);
        float pattern = approach < 0.5 ? mix(0.18, 0.92, dash) : 0.93;
        gl_FragColor = vec4(ink, rim * pattern);
        #include <colorspace_fragment>
      }
    `,
  });
  readonly mesh = new Mesh(this.geometry, this.material);
  private height: TerrainHeight | undefined;

  constructor() {
    this.mesh.name = "rescue-pickup-ring";
    this.mesh.visible = false;
    this.mesh.renderOrder = 7;
    // The heights are sampled from terrain after the horizontal ring is built.
    this.mesh.frustumCulled = false;
  }

  update(state: GooseState, terrain: TerrainHeight | undefined): void {
    const target =
      state.mode === "journey" && state.phase !== "failed"
        ? gooseRescue(state).target
        : undefined;
    if (!target) {
      this.mesh.visible = false;
      return;
    }
    const { x, z } = target.pos;
    if (
      !this.mesh.visible ||
      x !== this.mesh.position.x ||
      z !== this.mesh.position.z ||
      terrain !== this.height
    ) {
      this.height = terrain;
      this.mesh.position.set(x, 0, z);
      const vertices = this.geometry.getAttribute("position");
      for (let i = 0; i < vertices.count; i++) {
        const ground =
          terrain?.(x + vertices.getX(i), z + vertices.getZ(i)) ?? 0;
        vertices.setY(i, Math.max(0, ground) + 0.23);
      }
      vertices.needsUpdate = true;
    }
    this.mesh.visible = true;
    const approach = rescueApproach(leaderOf(state), target);
    this.uniforms.approach.value =
      approach === "ready" ? 2 : approach === "speed" ? 1 : 0;
    this.uniforms.progress.value = target.rescueProgress / GOOSE.pickupTicks;
  }
}
