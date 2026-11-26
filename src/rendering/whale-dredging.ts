import {
  BoxGeometry,
  BufferGeometry,
  Color,
  CylinderGeometry,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  Mesh,
  MeshBasicMaterial,
  RingGeometry,
  ShaderMaterial,
  Shape,
  ShapeGeometry,
  Vector2,
} from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { STEP_SEC } from "../core/clock";
import type { Vec2 } from "../core/math";
import type { InputSettings } from "../input/input";
import type { Landmark, WhaleLevel } from "../levels/schema";
import {
  DREDGING_FEATHER,
  dredgingPassage,
  type DredgingPassage,
} from "../levels/whale-dredging";

type DredgingSettings = Pick<InputSettings, "low" | "reduced">;

const surfaceY = 0.19;
const clearColor = "#b3eee4";
const surfaceColor = "#fff0cb";

function sediment(passage: DredgingPassage) {
  const shape = new Shape();
  for (const [index, point] of passage.plume.entries()) {
    if (index === 0) shape.moveTo(point.x, -point.z);
    else shape.lineTo(point.x, -point.z);
  }
  const uniforms = {
    points: { value: passage.plume.map(({ x, z }) => new Vector2(x, z)) },
    paper: { value: new Color("#d2b691") },
    ink: { value: new Color("#8a674d") },
    travel: { value: 0 },
    descent: { value: 0 },
    fineDetail: { value: 1 },
  };
  const geometry = new ShapeGeometry(shape).rotateX(-Math.PI / 2);
  const material = new ShaderMaterial({
    uniforms,
    transparent: true,
    depthWrite: false,
    side: DoubleSide,
    vertexShader: `
      varying vec2 water;
      void main() {
        water = position.xz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying vec2 water;
      uniform vec2 points[${passage.plume.length}];
      uniform vec3 paper;
      uniform vec3 ink;
      uniform float travel;
      uniform float descent;
      uniform float fineDetail;

      float distanceToEdge(vec2 a, vec2 b) {
        vec2 along = b - a;
        float t = clamp(dot(water - a, along) / dot(along, along), 0.0, 1.0);
        return length(water - a - t * along);
      }

      void main() {
        float edge = 1000.0;
        for (int i = 0; i < ${passage.plume.length - 1}; i++) {
          edge = min(edge, distanceToEdge(points[i], points[i + 1]));
        }
        vec2 drift = water + travel * vec2(0.55, -0.17);
        float strand = sin(dot(drift, vec2(0.073, 0.255)) +
          cos(dot(drift, vec2(0.081, -0.162))) * 0.65);
        float pigment = 0.58 + 0.20 * sin(drift.x * 0.103 - drift.y * 0.052)
          + strand * 0.21;
        float grain = sin(drift.x * 2.1 + sin(drift.y * 4.1))
          * sin(drift.y * 3.7 - drift.x) * 0.09;
        vec3 mixed = mix(paper, ink, clamp(pigment + grain * fineDetail, 0.0, 1.0));
        float wash = smoothstep(0.0, ${DREDGING_FEATHER.toFixed(1)}, edge);
        float opacity = (0.19 + 0.22 * pigment + 0.08 * min(descent, 1.0)) * wash;
        gl_FragColor = vec4(mixed, opacity);
        #include <colorspace_fragment>
      }
    `,
  });
  const mesh = new Mesh(geometry, material);
  mesh.name = "Dredging suspended sediment";
  mesh.position.y = 0.045;
  mesh.renderOrder = -5;
  return { mesh, uniforms };
}

function paintedGeometry(geometry: BufferGeometry, pigment: string) {
  const color = new Color(pigment);
  const colors = new Float32Array(geometry.getAttribute("position").count * 3);
  for (let index = 0; index < colors.length; index += 3)
    color.toArray(colors, index);
  return geometry.setAttribute("color", new Float32BufferAttribute(colors, 3));
}

function paintedMesh(parts: BufferGeometry[]): Mesh {
  const unindexed = parts.map((geometry) =>
    geometry.index ? geometry.toNonIndexed() : geometry,
  );
  const geometry = mergeGeometries(unindexed) ?? new BufferGeometry();
  for (const geometry of new Set([...parts, ...unindexed])) geometry.dispose();
  return new Mesh(geometry, new MeshBasicMaterial({ vertexColors: true }));
}

function dredger({ x, z }: Vec2): Mesh {
  // Place all solid work equipment east of the authored playable edge.
  const box = (
    width: number,
    height: number,
    length: number,
    px: number,
    py: number,
    pz: number,
    pigment: string,
    tilt = 0,
  ) =>
    paintedGeometry(
      new BoxGeometry(width, height, length)
        .rotateX(tilt)
        .translate(x + px, py, z + pz),
      pigment,
    );
  const hull = "#644f50";
  const deck = "#b58c65";
  const paint = "#c18c63";
  const steel = "#505358";
  const mesh = paintedMesh([
    box(10, 2.5, 26, 0, 0.2, 0, hull),
    box(10.5, 0.38, 26.5, 0, 1.58, 0, deck),
    box(5.8, 3.1, 5.4, 0.8, 3.2, -7.6, "#cfbea2"),
    box(6.6, 0.34, 6.2, 0.8, 4.92, -7.6, "#87706d"),
    box(3.7, 1.04, 0.12, 0.8, 3.8, -4.84, "#537379"),
    box(0.74, 8.9, 0.72, -2.2, 5.9, 1.7, steel, 0.11),
    box(0.74, 8.9, 0.72, 2.2, 5.9, 1.7, steel, 0.11),
    box(5, 0.67, 0.83, 0, 10.15, 2.1, paint),
    box(0.75, 0.76, 12.6, 0, 8, 6.9, paint, 0.39),
    box(0.27, 5.9, 0.28, 0, 2.9, 12.1, steel),
    box(2.4, 0.95, 2, 0, 0.6, 12.1, hull),
  ]);
  mesh.name = "Harbor dredging pontoon";
  return mesh;
}

function floats(path: readonly Landmark[]): Mesh {
  const parts = path.flatMap(({ pos }, index) =>
    [-1, 1].flatMap((side) => {
      const x = pos.x + side * (index === 0 ? 6.9 : 5.7);
      const z = pos.z;
      return [
        paintedGeometry(
          new CylinderGeometry(0.68, 0.7, 0.34, 12).translate(x, 0.14, z),
          "#6d5653",
        ),
        paintedGeometry(
          new CylinderGeometry(0.28, 0.61, 0.6, 12).translate(x, 0.53, z),
          surfaceColor,
        ),
        paintedGeometry(
          new CylinderGeometry(0.11, 0.25, 0.31, 12).translate(x, 0.94, z),
          "#dda666",
        ),
      ];
    }),
  );
  const mesh = paintedMesh(parts);
  mesh.name = "Dredging surface buoy pairs";
  return mesh;
}

function guide(
  name: string,
  path: readonly Landmark[],
  y: number,
  color: string,
): Mesh {
  const vertices: number[] = [];
  for (const [index, { pos: from }] of path.entries()) {
    const to = path[index + 1]?.pos;
    if (!to) break;
    const dx = to.x - from.x;
    const dz = to.z - from.z;
    const length = Math.hypot(dx, dz);
    if (length === 0) continue;
    const x = dx / length;
    const z = dz / length;
    for (let step = 4.5; step <= length - 4.5; step += 7) {
      const cx = from.x + x * step;
      const cz = from.z + z * step;
      const outline = [
        { side: 0, forward: 1.15 },
        { side: 1.06, forward: -0.77 },
        { side: 0, forward: -0.32 },
        { side: 0, forward: 1.15 },
        { side: 0, forward: -0.32 },
        { side: -1.06, forward: -0.77 },
      ];
      for (const { side, forward } of outline)
        vertices.push(
          cx + x * forward + z * side,
          y,
          cz + z * forward - x * side,
        );
    }
  }
  const geometry = new BufferGeometry().setAttribute(
    "position",
    new Float32BufferAttribute(vertices, 3),
  );
  const mesh = new Mesh(
    geometry,
    new MeshBasicMaterial({ color, side: DoubleSide }),
  );
  mesh.name = name;
  return mesh;
}

function regroupRipple({ pos }: Landmark): Mesh {
  const rings = [
    new RingGeometry(4.65, 4.86, 40),
    new RingGeometry(6.7, 6.82, 40),
  ];
  const geometry = mergeGeometries(rings) ?? new BufferGeometry();
  for (const ring of rings) ring.dispose();
  geometry.rotateX(-Math.PI / 2);
  const mesh = new Mesh(
    geometry,
    new MeshBasicMaterial({
      color: clearColor,
      transparent: true,
      depthWrite: false,
      opacity: 0.74,
    }),
  );
  mesh.position.set(pos.x, surfaceY, pos.z);
  mesh.renderOrder = 1;
  mesh.name = "Dredging clear-water regroup ripples";
  return mesh;
}

export class WhaleDredging {
  readonly group = new Group();
  private readonly sediment?: ReturnType<typeof sediment>;
  private readonly surfaceEdge?: Mesh;
  private readonly shallowEdge?: Mesh;

  constructor(level: WhaleLevel) {
    this.group.name = "Harbor dredging passage";
    const passage = dredgingPassage(level);
    if (!passage) return;

    this.sediment = sediment(passage);
    this.surfaceEdge = guide(
      "Dredging clear-edge surface guide",
      passage.clear,
      surfaceY,
      clearColor,
    );
    this.shallowEdge = guide(
      "Dredging clear-edge shallow guide",
      passage.clear,
      -2.67,
      clearColor,
    );
    this.shallowEdge.visible = false;
    const works = {
      x: Math.max(level.bounds.max.x, passage.works.pos.x) + 10,
      z: passage.works.pos.z,
    };
    this.group.add(
      this.sediment.mesh,
      dredger(works),
      floats(passage.surface),
      guide(
        "Dredging surface channel",
        passage.surface,
        surfaceY,
        surfaceColor,
      ),
      this.surfaceEdge,
      this.shallowEdge,
      regroupRipple(passage.regroup),
    );
  }

  update(tick: number, settings: DredgingSettings, viewDepth = 0): void {
    if (!this.sediment || !this.surfaceEdge || !this.shallowEdge) return;
    const { travel, fineDetail, descent } = this.sediment.uniforms;
    travel.value = settings.reduced ? 0 : tick * STEP_SEC;
    fineDetail.value = Number(!settings.low);
    descent.value = viewDepth;
    this.surfaceEdge.visible = viewDepth < 0.55;
    this.shallowEdge.visible = !this.surfaceEdge.visible;
  }
}
