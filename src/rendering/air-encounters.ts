import {
  BoxGeometry,
  BufferGeometry,
  CircleGeometry,
  Color,
  CylinderGeometry,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  IcosahedronGeometry,
  Line,
  LineBasicMaterial,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  Vector3,
} from "three";
import type { AirEncounterState } from "../core/game";
import type { GooseEncounters } from "../levels/schema";
import { gliderPose, kitePose } from "../simulation/air-encounters";

type Vertex = [number, number, number];
function cloth() {
  const vertices: number[] = [],
    colors: number[] = [];
  return {
    panel(ink: string, a: Vertex, b: Vertex, c: Vertex) {
      const color = new Color(ink);
      for (const point of [a, b, c]) {
        vertices.push(...point);
        colors.push(color.r, color.g, color.b);
      }
    },
    mesh() {
      const geometry = new BufferGeometry();
      geometry.setAttribute(
        "position",
        new Float32BufferAttribute(vertices, 3),
      );
      geometry.setAttribute("color", new Float32BufferAttribute(colors, 3));
      geometry.computeVertexNormals();
      return new Mesh(
        geometry,
        new MeshBasicMaterial({ vertexColors: true, side: DoubleSide }),
      );
    },
  };
}

function swallow(span: number) {
  const paper = cloth();
  const chest: Vertex = [0, 0.3, 0],
    head: Vertex = [0, 0, -1.72],
    hip: Vertex = [0, 0, 0.7];
  for (const side of [-1, 1]) {
    const shoulder: Vertex = [side * 0.85, 0, -0.95],
      tip: Vertex = [(side * span) / 2, 0.18, -1.4];
    const elbow: Vertex = [side * 1.55, 0, 0.24],
      tail: Vertex = [side * 1.1, 0, 2.65];
    paper.panel("#293e4a", shoulder, tip, elbow);
    paper.panel("#c35b3d", chest, shoulder, elbow);
    paper.panel("#f2dba2", head, shoulder, chest);
    paper.panel("#294957", elbow, hip, chest);
    paper.panel("#b24e35", hip, tail, elbow);
  }
  return paper.mesh();
}

function canopy(span: number) {
  const fabric = cloth();
  const edge = (i: number, back: boolean): Vertex => {
    const u = i / 5;
    return [
      (u * span) / 2,
      -1.9 * u * u + (back ? -0.32 : 0),
      -1.65 * u * u + (back ? 1.6 : -1.15),
    ];
  };
  for (let i = -5; i < 5; i++) {
    const ink = [-4, -3, 2, 3].includes(i)
      ? "#f7e6b5"
      : i % 2
        ? "#cd6038"
        : "#e88742";
    const a = edge(i, false),
      b = edge(i + 1, false),
      c = edge(i, true),
      d = edge(i + 1, true);
    fabric.panel(ink, a, b, c);
    fabric.panel(ink, b, d, c);
    fabric.panel("#9a492e", [a[0], a[1] - 0.3, a[2] + 0.26], b, a);
  }
  return fabric.mesh();
}

function line(points: Vertex[], color: string) {
  return new Line(
    new BufferGeometry().setFromPoints(points.map((p) => new Vector3(...p))),
    new LineBasicMaterial({ color }),
  );
}

function person(coat: string) {
  const root = new Group(),
    upper = new Group();
  const jacket = new MeshLambertMaterial({ color: coat }),
    dark = new MeshLambertMaterial({ color: "#384746" });
  const skin = new MeshLambertMaterial({ color: "#bb8967" });
  const head = new Mesh(new IcosahedronGeometry(0.29, 1), skin);
  head.position.y = 0.98;
  const cap = new Mesh(new CylinderGeometry(0.24, 0.33, 0.17, 8), dark);
  cap.position.set(0, 1.18, -0.04);
  const torso = new Mesh(new CylinderGeometry(0.28, 0.38, 0.76, 7), jacket);
  torso.position.y = 0.43;
  upper.add(torso, head, cap);
  for (const side of [-1, 1]) {
    const leg = new Mesh(new BoxGeometry(0.19, 0.72, 0.24), dark);
    leg.position.set(side * 0.16, 0.38, 0);
    const sleeve = new Mesh(new CylinderGeometry(0.12, 0.095, 0.61, 6), jacket);
    sleeve.position.set(side * 0.32, 0.46, -0.16);
    sleeve.rotation.x = 0.87;
    upper.add(sleeve);
    root.add(leg);
  }
  upper.position.y = 0.74;
  root.add(upper);
  return { root, upper };
}

function shadow(radius: number) {
  const mesh = new Mesh(
    new CircleGeometry(1, 18),
    new MeshBasicMaterial({
      color: "#44594f",
      transparent: true,
      opacity: 0.25,
      depthWrite: false,
    }),
  );
  mesh.rotation.x = -Math.PI / 2;
  mesh.scale.set(radius, radius * 0.38, 1);
  return mesh;
}

export function buildAirEncounters(
  config: GooseEncounters,
  ground: (x: number, z: number) => number,
) {
  const group = new Group(),
    family = new Group(),
    flying = new Group();
  group.add(family, flying);
  const { kite, glider } = config;
  const adult = person("#447573"),
    child = person("#d88442");
  const { x, z } = kite.bank;
  const bankY = Math.max(0, ground(x, z));
  adult.root.position.set(x + 0.75, bankY, z + 0.85);
  adult.root.scale.setScalar(1.64);
  adult.root.rotation.y = 1;
  child.root.position.set(x - 0.82, bankY, z - 0.28);
  child.root.scale.setScalar(1.15);
  child.root.rotation.y = 1;
  const reel = new Mesh(
    new CylinderGeometry(0.19, 0.19, 0.42, 7),
    new MeshLambertMaterial({ color: "#a75e31" }),
  );
  reel.rotation.z = Math.PI / 2;
  reel.position.set(x - 1.12, bankY + 1.25, z - 0.48);
  const kiteBody = swallow(kite.span),
    kiteShadow = shadow(kite.span * 0.43);
  const string = line(
    [
      [0, 0, 0],
      [0, 0, 0],
    ],
    "#686252",
  );
  string.frustumCulled = false;
  const path = new Mesh(
    new CylinderGeometry(1, 1.04, 0.28, 14),
    new MeshLambertMaterial({ color: "#bda77b" }),
  );
  path.position.set(x, bankY - 0.06, z + 0.5);
  path.scale.set(2.9, 1, 5.3);
  path.rotation.y = 0.32;
  family.add(path);
  family.add(adult.root, child.root, reel, kiteBody, kiteShadow, string);
  const pilot = person("#394c60"),
    sail = canopy(glider.span),
    rig = new Group();
  pilot.root.scale.setScalar(1.12);
  const cords = new Group();
  for (const side of [-1, 1])
    for (const ratio of [0.45, 0.91]) {
      cords.add(
        line(
          [
            [
              (side * glider.span * ratio) / 2,
              -1.9 * ratio * ratio,
              -1.65 * ratio * ratio,
            ],
            [0, -3.25, -1.25],
          ],
          "#635854",
        ),
      );
    }
  rig.add(sail, cords);
  flying.add(rig, pilot.root);
  const sailShadow = shadow(glider.span / 2);
  flying.add(sailShadow);
  return {
    group,
    update(state: AirEncounterState, tick: number, leaderZ: number) {
      family.visible = Math.abs(leaderZ - z) < 95;
      flying.visible = Math.abs(leaderZ - glider.launch.z) < 110;
      if (family.visible) {
        const p = kitePose(kite, state, tick);
        kiteBody.position.set(p.x, p.y, p.z);
        kiteBody.rotation.set(-0.56, 0.2, 0.17 * p.rise);
        child.upper.rotation.x = -0.36 * (1 - p.rise);
        adult.upper.rotation.x = -0.65 * (1 - p.rise);
        adult.upper.position.y = 0.74 - 0.27 * (1 - p.rise);
        kiteShadow.position.set(
          p.x,
          Math.max(0.06, ground(p.x, p.z) + 0.05),
          p.z,
        );
        const points = string.geometry.getAttribute("position");
        points.setXYZ(0, reel.position.x, reel.position.y, reel.position.z);
        points.setXYZ(1, p.x, p.y, p.z);
        points.needsUpdate = true;
      }
      if (flying.visible) {
        const p = gliderPose(glider, state, tick),
          groundY = Math.max(0, ground(p.x, p.z));
        const y = Math.max(groundY + 0.3, p.y);
        rig.position.set(p.x, y, p.z);
        sail.scale.set(1, 0.12 + 0.88 * p.rise, 1);
        cords.visible = p.rise > 0.1;
        cords.scale.y = p.rise;
        pilot.root.position.set(
          p.x,
          Math.max(groundY, y - 4.55),
          p.z - 4.2 + 2.95 * p.rise,
        );
        pilot.root.rotation.y = -1.1 * p.rise;
        pilot.upper.rotation.x = -0.34 * p.rise;
        sailShadow.position.set(p.x, groundY + 0.07, p.z);
      }
    },
  };
}
