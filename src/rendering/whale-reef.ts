import {
  BufferGeometry,
  Color,
  DoubleSide,
  DynamicDrawUsage,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  MeshBasicMaterial,
  Object3D,
  PlaneGeometry,
  ShaderMaterial,
} from "three";
import { STEP_SEC } from "../core/clock";
import type { WhaleActor } from "../core/game";
import { clamp, type Vec2 } from "../core/math";
import type { InputSettings } from "../input/input";
import { contains } from "../levels/geometry";
import type { WhaleLevel } from "../levels/schema";
import { reefGrass, reefRockInstances } from "./whale-coast";
import { reefApproach, reefBanks, reefPaint } from "./whale-reef-layout";

// Keep the first school near the entrance. The other two share the shelter
// of the inner reef, on the east side of the current.
const SHOALS = [
  { anchor: "entrance", x: 6.5, z: 10, phase: 0.5 },
  { anchor: "pool", x: 7, z: -7, phase: 2.4 },
  { anchor: "pool", x: 6, z: 8, phase: 4.3 },
] as const;
const ROCK_COLORS = ["#8e9e88", "#658d7e", "#b5ad8d"];
const FISH_COLORS = ["#badbd3", "#f3e9bc", "#93c7ba", "#d5e2d7"];
const REEF_FISH_COLORS = ["#9fc1b9", "#f3e9bc", "#769f9e", "#b8cec1"];
const WHITE = new Color();
const FISH_PER_SHOAL = 22;
const LOW_FISH_PER_SHOAL = 14;
const FRAGMENTS_PER_SHOAL = 4;
const TURN = 2 * Math.PI;
type School = Vec2 & { readonly phase: number };

function fishGeometry(): BufferGeometry {
  // Paint both the top and side silhouette so low orbit angles still show a forked tail.
  const vertices = [
    0, 0, 0.64, -0.21, 0, 0.27, 0, 0.24, 0.22, 0.21, 0, 0.27, 0.12, 0, -0.24,
    -0.12, 0, -0.24, 0, -0.12, 0.13, 0, 0, -0.44, -0.18, 0, -0.7, 0, 0, -0.58,
    0.18, 0, -0.7, -0.36, -0.04, -0.12,
  ];
  const pigment = [
    1, 0.66, 0.94, 0.76, 0.81, 0.68, 0.52, 0.71, 0.76, 0.59, 0.83, 0.66,
  ];
  return new BufferGeometry()
    .setAttribute("position", new Float32BufferAttribute(vertices, 3))
    .setAttribute(
      "color",
      new Float32BufferAttribute(
        pigment.flatMap((value) => [value, value, value]),
        3,
      ),
    )
    .setIndex([
      0, 1, 2, 0, 2, 3, 2, 1, 5, 2, 5, 7, 2, 7, 4, 2, 4, 3, 0, 6, 1, 0, 3, 6, 6,
      3, 4, 6, 4, 7, 6, 7, 5, 6, 5, 1, 5, 8, 7, 8, 9, 7, 9, 10, 7, 7, 10, 4, 1,
      11, 5,
    ]);
}

function surfaceLight(
  time: { value: number },
  count: number,
  dive = { value: 0 },
): InstancedMesh {
  const light = new InstancedMesh(
    new PlaneGeometry(1, 1).rotateX(-Math.PI / 2),
    new ShaderMaterial({
      uniforms: { time, dive },
      transparent: true,
      depthWrite: false,
      vertexShader: `
        varying vec2 wash;
        void main() {
          wash = uv * 2.0 - 1.0;
          gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform float time;
        uniform float dive;
        varying vec2 wash;
        void main() {
          vec2 p = wash;
          float edge = length(p) + 0.08 * sin(p.x * 17.0 + p.y * 11.0);
          float halo = 1.0 - smoothstep(0.14, 1.0, edge);
          float streak = sin(p.y * 28.0 + sin(p.x * 9.0) * 1.1 + time);
          float broken = smoothstep(-0.4, 0.73, sin(p.x * 24.0 + p.y * 14.0));
          float flecks = smoothstep(0.70, 0.98, streak) * broken * halo;
          float visibility = 1.0 - 0.82 * smoothstep(0.45, 1.6, dive);
          gl_FragColor = vec4(mix(vec3(0.30, 0.65, 0.56), vec3(0.95, 0.89, 0.62), flecks),
                              visibility * (halo * 0.16 + flecks * 0.24));
          #include <colorspace_fragment>
        }
      `,
    }),
    count,
  );
  light.renderOrder = -3;
  return light;
}

export interface ReefView {
  readonly fish: number;
  readonly spread: readonly number[];
  readonly glintPhase: number;
}

export class WhaleReef {
  readonly group = new Group();
  private readonly rest = new Group();
  private readonly lightTime = { value: 0 };
  private readonly fish: InstancedMesh;
  private readonly transform = new Object3D();
  private readonly bayColors = FISH_COLORS.map((color) => new Color(color));
  private readonly reefColors = REEF_FISH_COLORS.map(
    (color) => new Color(color),
  );
  private readonly fishColor = new Color();
  private readonly spread: number[];
  private readonly reefSchools: readonly School[];
  private readonly baySchools: readonly School[];
  private tick = -1;
  private low = false;
  private reduced = false;

  constructor(level: WhaleLevel, viewDepth = { value: 0 }) {
    this.group.name = "W3 shallow reef";
    const bank = level.landmarks.find(({ id }) => id === "quiet-mid");
    const bend = level.landmarks.find(({ id }) => id === "quiet-bend");
    const arc = level.landmarks.find(({ id }) => id === "quiet-arc");
    const poolMark = level.landmarks.find(({ id }) => id === "quiet-pool");
    const eddyMark = level.landmarks.find(({ id }) => id === "current-eddy");
    const water = level.zones.find(
      ({ id, kind }) => id === "quiet-rest" && kind === "sanctuary",
    );
    this.reefSchools =
      bank && water && contains(water.points, bank.pos)
        ? SHOALS.map(({ anchor, x, z, phase }) => {
            const origin =
              anchor === "pool" ? (poolMark?.pos ?? bank.pos) : bank.pos;
            return { x: origin.x + x, z: origin.z + z, phase };
          })
        : [];
    this.baySchools = level.landmarks
      .filter(({ kind }) => kind === "shoal")
      .map(({ pos }, index) => ({ ...pos, phase: index * 2.4 }));
    const schoolCount = this.reefSchools.length + this.baySchools.length;
    this.fish = new InstancedMesh(
      fishGeometry(),
      new MeshBasicMaterial({ vertexColors: true, side: DoubleSide }),
      schoolCount * FISH_PER_SHOAL,
    );
    this.spread = Array.from({ length: schoolCount }, () => 0);
    this.fish.instanceMatrix.setUsage(DynamicDrawUsage);
    // Local activation below limits the active instances as the pod travels.
    this.fish.frustumCulled = false;
    this.fish.visible = false;
    this.rest.visible = false;
    this.group.add(this.rest, this.fish);
    const bayRefill = level.landmarks.find(({ id }) => id === "bay-refill");
    if (bayRefill) {
      const shoal = this.baySchools[0];
      const light = surfaceLight(this.lightTime, shoal ? 2 : 1);
      light.name = "Bay light on the shoal and surfacing water";
      this.transform.position.set(bayRefill.pos.x, 0.05, bayRefill.pos.z);
      this.transform.scale.set(32, 1, 22);
      this.transform.updateMatrix();
      light.setMatrixAt(0, this.transform.matrix);
      if (shoal) {
        this.transform.position.set(shoal.x, 0.05, shoal.z - 10);
        this.transform.scale.set(19, 1, 35);
        this.transform.updateMatrix();
        light.setMatrixAt(1, this.transform.matrix);
      }
      this.group.add(light);
    }
    if (!bank || !water || this.reefSchools.length === 0) return;
    const paint = reefPaint(viewDepth);
    this.group.add(reefApproach(level, bank.pos, paint));
    const banks = reefBanks(
      water,
      bank.pos,
      bend?.pos ?? bank.pos,
      paint,
      arc?.pos,
    );
    const count = this.reefSchools.length * FRAGMENTS_PER_SHOAL;
    const fragments = reefRockInstances(count, false, viewDepth);
    fragments.name = "Reef terrace fragments";
    const grass = reefGrass(count);
    grass.name = "Reef grass clusters";
    const shades = ROCK_COLORS.map((color) => new Color(color));
    const { transform } = this;
    for (const [school, center] of this.reefSchools.entries()) {
      const bankSide = school === 0 ? -1 : 1;
      for (let i = 0; i < FRAGMENTS_PER_SHOAL; i++) {
        const scatter = Math.sin(i * 2.4 + center.phase);
        const index = school * FRAGMENTS_PER_SHOAL + i;
        const x = center.x + bankSide * (6.4 + scatter * 3.4);
        const z = center.z - 8 + i * 4.7 + scatter * 2;
        const size = 0.68 + (1 + scatter) * 0.29;
        transform.position.set(x, -10.13 + scatter * 0.25, z);
        transform.scale.set(2.6 * size, 0.94 * size, 4.3 * size);
        transform.rotation.y = 0.36 * scatter - bankSide * 0.25;
        transform.updateMatrix();
        fragments.setMatrixAt(index, transform.matrix);
        fragments.setColorAt(index, shades[i % shades.length] ?? WHITE);
        transform.position.set(x + scatter * 2.15, -10.01, z + 2);
        transform.scale.set(1.43 * size, 1.64 * size, 1.43 * size);
        transform.updateMatrix();
        grass.setMatrixAt(index, transform.matrix);
      }
    }
    // Place focal light inside the two existing breathing pockets.
    const pockets = [
      {
        pos: poolMark?.pos ?? bank.pos,
        width: 31,
        length: 24,
        rotation: 0.34,
      },
      ...(eddyMark
        ? [
            {
              pos: { x: eddyMark.pos.x - 3, z: eddyMark.pos.z - 8 },
              width: 25,
              length: 17,
              rotation: -0.12,
            },
          ]
        : []),
    ];
    const pools = surfaceLight(this.lightTime, pockets.length, viewDepth);
    pools.name = "Surface light";
    for (const [index, { pos, width, length, rotation }] of pockets.entries()) {
      transform.position.set(pos.x, 0.05, pos.z);
      transform.rotation.y = rotation;
      transform.scale.set(width, 1, length);
      transform.updateMatrix();
      pools.setMatrixAt(index, transform.matrix);
    }
    this.rest.add(banks, fragments, grass, pools);
  }

  reset(): void {
    this.tick = -1;
    this.spread.fill(0);
  }

  update(
    leader: WhaleActor,
    tick: number,
    { low, reduced }: InputSettings,
  ): void {
    if (tick === this.tick && low === this.low && reduced === this.reduced)
      return;
    if (tick < this.tick) this.reset();
    const elapsed = this.tick < 0 ? 0 : (tick - this.tick) * STEP_SEC;
    this.tick = tick;
    this.low = low;
    this.reduced = reduced;
    // Allow the bank to enter frame before quiet-rest and remain visible on a look back.
    this.rest.visible = this.reefSchools.some(
      ({ x, z }) => Math.hypot(leader.pos.x - x, leader.pos.z - z) < 105,
    );
    const seconds = tick * STEP_SEC;
    this.lightTime.value = reduced ? 0 : seconds * 0.83;
    const shallow = leader.dive.layer === "shallow";
    const passing = clamp((leader.speed - 1.55) / 3.5);
    const perSchool = low ? LOW_FISH_PER_SHOAL : FISH_PER_SHOAL;
    const { transform } = this;
    let index = 0;
    for (const [school, anchor] of [
      ...this.reefSchools,
      ...this.baySchools,
    ].entries()) {
      const bay = school >= this.reefSchools.length;
      const visible = bay
        ? Math.hypot(leader.pos.x - anchor.x, leader.pos.z - anchor.z) < 64
        : this.rest.visible;
      if (!visible) {
        this.spread[school] = 0;
        continue;
      }
      const travel = reduced ? anchor.phase : anchor.phase + seconds * 0.37;
      const cross = bay ? 10 : 3.5;
      const x = anchor.x + Math.sin(travel) * cross;
      const z = anchor.z + Math.cos(travel) * 5;
      const distance = Math.hypot(leader.pos.x - x, leader.pos.z - z);
      const nearby = clamp(1 - (distance - 5) / 11);
      const target = nearby * passing * (shallow ? 1 : 0.52);
      let spread = this.spread[school] ?? 0;
      const rate = target > spread ? 5 : 0.75;
      spread +=
        (target - spread) *
        (1 - Math.exp(-elapsed * rate * (reduced ? 0.48 : 1)));
      this.spread[school] = spread;

      const expansion = spread * (reduced ? 4 : 11);
      const tint = bay ? 1.14 : shallow ? 0.92 : 0.73;
      const colors = bay ? this.bayColors : this.reefColors;
      const yaw = Math.atan2(Math.cos(travel) * cross, -Math.sin(travel) * 5);
      for (let i = 0; i < perSchool; i++) {
        const angle = i * 2.399963 + travel;
        const ring = Math.sqrt((i + 0.5) / perSchool);
        const radius = ring * ((bay ? 5.2 : 4.1) + expansion);
        const tailBeat = reduced ? 0 : 0.23 * Math.sin(seconds * 6 + i * 1.7);
        const size = (bay ? 1.46 : 1.22) + (i % 5) * 0.17;
        transform.position.set(
          x + Math.cos(angle) * radius,
          (bay ? -1.65 : -3.3) - (i % 4) * 0.42 - spread * 0.55,
          z + Math.sin(angle) * radius * 1.28,
        );
        transform.scale.set(size, size, size);
        transform.rotation.y =
          yaw + tailBeat + Math.sin(angle - yaw) * spread * TURN * 0.32;
        transform.updateMatrix();
        this.fish.setMatrixAt(index, transform.matrix);
        const color = colors[i % colors.length] ?? WHITE;
        this.fishColor.copy(color).multiplyScalar(tint);
        this.fish.setColorAt(index, this.fishColor);
        index++;
      }
    }
    this.fish.visible = index > 0;
    this.fish.count = index;
    this.fish.instanceMatrix.needsUpdate = true;
    if (this.fish.instanceColor) this.fish.instanceColor.needsUpdate = true;
  }

  report(): ReefView | undefined {
    if (!this.fish.visible) return undefined;
    return {
      fish: this.fish.count,
      spread: this.spread.map((value) => Math.round(value * 1000) / 1000),
      glintPhase: this.lightTime.value,
    };
  }
}
