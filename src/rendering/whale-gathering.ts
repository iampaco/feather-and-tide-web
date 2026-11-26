import {
  Color,
  DynamicDrawUsage,
  InstancedBufferAttribute,
  InstancedMesh,
  MathUtils,
  Object3D,
  PlaneGeometry,
  ShaderMaterial,
} from "three";
import type { WhaleActor } from "../core/game";
import type { InputSettings } from "../input/input";
import type { Zone } from "../levels/schema";
import { whaleGoalBlocker } from "../simulation/world-rules";

const POD_RIPPLE_START = 0.035;
const POD_RIPPLE_STAGGER = 0.024;
const POD_RIPPLE_LIFETIME = 0.72;
const ARRIVAL_RIPPLE_START = 0.008;
const ARRIVAL_RIPPLE_LIFETIME = 0.82;
const WATERLINE = 0.145;

export class WhaleGathering {
  readonly mesh: InstancedMesh<PlaneGeometry, ShaderMaterial>;
  private readonly ripple: InstancedBufferAttribute;
  private readonly transform = new Object3D();
  private readonly detail = { value: 1 };
  private poseActors?: readonly WhaleActor[];

  constructor(
    capacity: number,
    private readonly goal?: Zone,
  ) {
    this.ripple = new InstancedBufferAttribute(
      new Float32Array(capacity * 3),
      3,
    ).setUsage(DynamicDrawUsage);
    const geometry = new PlaneGeometry(15, 16)
      .rotateX(-Math.PI / 2)
      .translate(0, 0, -1.95);
    geometry.setAttribute("ripple", this.ripple);
    this.mesh = new InstancedMesh(
      geometry,
      new ShaderMaterial({
        uniforms: {
          silver: { value: new Color("#ddf4eb") },
          ivory: { value: new Color("#fff5d7") },
          wash: { value: new Color("#9ac6c2") },
          detail: this.detail,
        },
        transparent: true,
        depthWrite: false,
        vertexShader: `
          attribute vec3 ripple;
          varying vec2 water;
          varying vec3 life;
          void main() {
            water = position.xz;
            life = ripple;
            gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
          }
        `,
        fragmentShader: `
          uniform vec3 silver;
          uniform vec3 ivory;
          uniform vec3 wash;
          uniform float detail;
          varying vec2 water;
          varying vec3 life;

          float trailingArc(vec2 point, float center, float width, float feather) {
            float across = abs(point.x) / width;
            float crest = center - across * across * 1.16;
            float delta = abs(point.y - crest);
            float antialias = clamp(fwidth(delta), 0.07, 0.28);
            float stroke = 1.0 - smoothstep(feather * 0.37, feather + antialias, delta);
            return stroke * (1.0 - smoothstep(0.48, 0.98, across));
          }

          void main() {
            if (life.y <= 0.0) discard;
            float spread = life.x;
            float accent = life.z;
            float paper = sin(water.x * 2.91 + water.y * 1.34) + sin(water.x * 1.47 - water.y * 3.12);
            float breakage = 0.70 + 0.30 * smoothstep(-0.38, 1.52, paper);
            vec2 brush = water + vec2(0.0, 0.08 * sin(water.x * 1.6 + spread));
            float width = mix(1.72, 3.18 + accent * 0.82, spread);
            float center = -1.24 - spread * 2.14;
            float wake = trailingArc(brush, center, width, 0.30);
            float outerWash = trailingArc(brush, center - 0.25, width * 1.13, 0.85);
            float feather = trailingArc(brush - vec2(0.38, 0.0), center - 1.34, width * 0.93, 0.22);
            vec2 flank = vec2(water.x / (1.42 + spread * 0.56), (water.y - 0.45) / 2.66);
            float contact = (1.0 - smoothstep(0.05, 0.17, abs(length(flank) - 1.0)))
                          * smoothstep(0.51, 0.86, abs(flank.x))
                          * smoothstep(-0.59, -0.13, flank.y)
                          * (1.0 - smoothstep(0.48, 0.81, flank.y));
            float mainStroke = max(wake * (0.77 + accent * 0.17), contact * (0.45 + accent * 0.27));
            float light = max(mainStroke, detail * feather * (0.28 + accent * 0.16)) * breakage;
            float body = outerWash * 0.23;
            vec2 ring = vec2(water.x, (water.y - 0.3) * 0.77);
            float crest = abs(length(ring) - mix(2.1, 6.6, spread));
            float ripple = (1.0 - smoothstep(0.12, 0.56, crest)) * (0.59 + accent * 0.16);
            light = max(light, ripple * breakage);
            vec3 color = mix(wash, mix(silver, ivory, accent), smoothstep(0.0, 0.54, light));
            gl_FragColor = vec4(color, max(light, body) * life.y);
            #include <colorspace_fragment>
          }
        `,
      }),
      capacity,
    );
    this.mesh.name = "Offshore gathering waterlines";
    this.mesh.visible = false;
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 2;
    this.mesh.instanceMatrix.setUsage(DynamicDrawUsage);
  }

  update(
    actors: readonly WhaleActor[],
    progress: number,
    { low, reduced }: Pick<InputSettings, "low" | "reduced">,
    previousActors: readonly WhaleActor[] = actors,
  ): void {
    this.detail.value = Number(!low);
    // Landing freezes this roster while its independently paused presentation progresses.
    if (this.poseActors !== actors) {
      this.mesh.count = actors.length;
      for (const [index, actor] of actors.entries()) {
        this.transform.position.set(actor.pos.x, WATERLINE, actor.pos.z);
        this.transform.rotation.y = actor.heading;
        this.transform.updateMatrix();
        this.mesh.setMatrixAt(index, this.transform.matrix);
      }
      this.mesh.instanceMatrix.needsUpdate = true;
      this.poseActors = actors;
    }

    for (const [index, actor] of actors.entries()) {
      const prior = previousActors.find(({ id }) => id === actor.id);
      const arrived =
        prior !== undefined &&
        whaleGoalBlocker(prior, this.goal) !== null &&
        whaleGoalBlocker(actor, this.goal) === null;
      const start = arrived
        ? ARRIVAL_RIPPLE_START
        : POD_RIPPLE_START + index * POD_RIPPLE_STAGGER;
      const duration = arrived ? ARRIVAL_RIPPLE_LIFETIME : POD_RIPPLE_LIFETIME;
      const elapsed = MathUtils.clamp((progress - start) / duration, 0, 1);
      const spread = reduced
        ? arrived
          ? 0.54
          : 0.38
        : MathUtils.smoothstep(elapsed, 0, 1);
      const opacity = reduced
        ? 0.74 + Number(arrived) * 0.22
        : MathUtils.smoothstep(elapsed, 0, 0.16) *
          (1 - MathUtils.smoothstep(elapsed, 0.63, 1));
      this.ripple.setXYZ(index, spread, opacity, Number(arrived));
    }
    this.ripple.needsUpdate = true;
  }
}
