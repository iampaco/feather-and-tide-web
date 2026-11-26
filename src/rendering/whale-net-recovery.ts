import {
  BoxGeometry,
  Color,
  CylinderGeometry,
  Group,
  InstancedMesh,
  MeshStandardMaterial,
  Object3D,
  SphereGeometry,
  TorusGeometry,
  type BufferGeometry,
} from "three";
import type { Vec2 } from "../core/math";
import type { WhaleLevel } from "../levels/schema";

interface PaintedPiece {
  readonly at: readonly [number, number, number];
  readonly size: readonly [number, number, number];
  readonly color: string;
  readonly tilt?: number;
  readonly turn?: number;
}

function batch(
  name: string,
  geometry: BufferGeometry,
  material: MeshStandardMaterial,
  pieces: readonly PaintedPiece[],
): InstancedMesh {
  const mesh = new InstancedMesh(geometry, material, pieces.length);
  mesh.name = name;
  const pose = new Object3D();
  const pigment = new Color();
  pieces.forEach(({ at, size, color, tilt = 0, turn = 0 }, index) => {
    pose.position.set(...at);
    pose.scale.set(...size);
    pose.rotation.set(tilt, turn, 0);
    pose.updateMatrix();
    mesh.setMatrixAt(index, pose.matrix);
    mesh.setColorAt(index, pigment.set(color));
  });
  return mesh;
}

function laneMarks(
  center: Vec2,
  innerEdge: number,
  outerEdge: number,
  netEnds: readonly [number, number],
  paint: MeshStandardMaterial,
): Group {
  const marks = new Group();
  marks.name = "W2 maintained lane marks";
  const halfWidth = Math.min(center.x - innerEdge, outerEdge - center.x) - 3.5;
  if (halfWidth <= 1.5) return marks;
  const [near, far] = netEnds;
  const pairs = [near - 7, far + 5, far + 27].flatMap((z) =>
    [-halfWidth, halfWidth].map((offset) => ({ x: center.x + offset, z })),
  );
  const floats: PaintedPiece[] = pairs.flatMap(({ x, z }) => [
    { at: [x, 0.36, z], size: [1.02, 0.56, 1.24], color: "#568987" },
    { at: [x, 0.65, z], size: [0.76, 0.46, 0.93], color: "#b9dbc8" },
  ]);
  const plates: PaintedPiece[] = pairs.flatMap(({ x, z }) => [
    { at: [x, 1.21, z], size: [0.15, 1.18, 0.15], color: "#305d5d" },
    { at: [x, 1.84, z], size: [1.03, 0.6, 0.65], color: "#eaf5db" },
    { at: [x, 1.59, z], size: [1.04, 0.19, 0.66], color: "#769f91" },
  ]);
  marks.add(
    batch("W2 pale green floats", new SphereGeometry(1, 10, 6), paint, floats),
    batch("W2 lane marker plates", new BoxGeometry(1, 1, 1), paint, plates),
  );
  return marks;
}

function recoveryDock(anchor: Vec2, paint: MeshStandardMaterial): Group {
  const dock = new Group();
  dock.name = "W2 fishing gear recovery dock";
  dock.position.set(anchor.x, 0, anchor.z);
  const timber = "#765e53";
  const wetTimber = "#586b64";
  const dryPlank = ["#be9b77", "#aa8b70", "#c3a788"];
  const deck: PaintedPiece[] = Array.from({ length: 11 }, (_, row) => ({
    at: [17.5, 2.35, (row - 5) * 2.12],
    size: [29, 0.52, 2.03],
    color: dryPlank[row % dryPlank.length] ?? timber,
  }));
  for (const z of [-9.8, 0, 9.8]) {
    deck.push({ at: [17.5, 1.53, z], size: [30, 1.1, 0.8], color: timber });
    for (const x of [4.3, 16, 30]) {
      deck.push({ at: [x, -0.4, z], size: [1.0, 7.4, 1.0], color: wetTimber });
    }
  }
  for (const z of [-12.2, 12.2]) {
    deck.push({ at: [18, 2.76, z], size: [28.8, 0.45, 0.58], color: timber });
    if (z < 0) continue;
    for (const x of [5.5, 15, 24.5, 31])
      deck.push({ at: [x, 4.05, z], size: [0.62, 3.0, 0.68], color: timber });
    deck.push({ at: [18, 5.51, z], size: [26, 0.43, 0.46], color: "#a17d63" });
  }

  const floatRack: PaintedPiece[] = [
    { at: [24.7, 3.04, 4.6], size: [8.9, 0.64, 6.3], color: timber },
    { at: [20.2, 3.56, 4.6], size: [0.45, 1.44, 6.3], color: timber },
    { at: [29.1, 3.56, 4.6], size: [0.45, 1.44, 6.3], color: timber },
    { at: [24.7, 3.61, 7.7], size: [8.7, 1.7, 0.45], color: timber },
    { at: [10.6, 4.98, -6.8], size: [0.91, 4.8, 0.87], color: timber },
    { at: [21.5, 4.98, -6.8], size: [0.91, 4.8, 0.87], color: timber },
    { at: [16.05, 7.42, -6.8], size: [12.7, 0.56, 0.91], color: "#a2836c" },
    { at: [15.3, 6.69, -6.8], size: [0.82, 1.06, 1.02], color: wetTimber },
    { at: [15.3, 5.67, -6.8], size: [0.13, 1.84, 0.13], color: "#6d5a4f" },
  ];
  const floatPigments = ["#cc9871", "#e4ba86", "#738f87"];
  const collectedFloats: PaintedPiece[] = Array.from(
    { length: 15 },
    (_, index) => ({
      at: [
        21.4 + (index % 4) * 2.04,
        index > 10 ? 5.14 : 4.15,
        2.1 + Math.floor((index % 12) / 4) * 1.74,
      ],
      size: [0.94, 0.69, 0.74],
      color: floatPigments[index % floatPigments.length] ?? timber,
    }),
  );

  const coiledLine = new TorusGeometry(1, 0.12, 6, 20).rotateX(-Math.PI / 2);
  const coils: PaintedPiece[] = [];
  for (const [x, z, size] of [
    [8.4, 1.8, 2.05],
    [14.8, 7.1, 1.6],
    [16.6, 1.3, 1.25],
  ] as const) {
    for (const [tier, dye] of [
      "#8b7867",
      "#9a9072",
      "#796f63",
      "#b1a184",
    ].entries()) {
      coils.push({
        at: [x + 0.16 * tier, 2.84 + tier * 0.48, z],
        size: [size - tier * 0.08, 1.16, size * 0.8 - tier * 0.06],
        color: dye,
      });
    }
  }
  const rolledNet: PaintedPiece[] = [
    {
      at: [15.3, 3.45, -6.8],
      size: [0.97, 7.5, 0.98],
      color: "#828b70",
      tilt: Math.PI / 2,
    },
    {
      at: [26.5, 3.72, -4.2],
      size: [1.1, 6.7, 1.1],
      color: "#6c806f",
      tilt: Math.PI / 2,
      turn: 0.23,
    },
    {
      at: [29.4, 3.51, -5.4],
      size: [0.92, 6.5, 0.92],
      color: "#8c8874",
      tilt: Math.PI / 2,
      turn: 0.23,
    },
  ];
  for (const {
    at: [x, y, z],
    size: [width, length],
    turn = 0,
  } of rolledNet) {
    for (const seam of [-0.39, -0.15, 0.19, 0.38]) {
      coils.push({
        at: [
          x + Math.sin(turn) * length * seam,
          y,
          z + Math.cos(turn) * length * seam,
        ],
        size: [width, 1, width],
        color: "#b1a78d",
        tilt: Math.PI / 2,
        turn,
      });
    }
  }
  dock.add(
    batch("W2 timber and sorting racks", new BoxGeometry(1, 1, 1), paint, [
      ...deck,
      ...floatRack,
    ]),
    batch(
      "W2 collected floats",
      new SphereGeometry(1, 10, 6),
      paint,
      collectedFloats,
    ),
    batch(
      "W2 recovered nets",
      new CylinderGeometry(1, 0.92, 1, 10),
      paint,
      rolledNet,
    ),
    batch("W2 recovered rope and bindings", coiledLine, paint, coils),
  );
  return dock;
}

export function drawNetRecovery(level: WhaleLevel): Group {
  const group = new Group();
  group.name = "W2 restored no-net passage";
  const dock = level.landmarks.find(({ id }) => id === "net-recovery-dock");
  const route = level.landmarks.find(({ id }) => id === "net-wide");
  const divider = level.zones.find(({ id }) => id === "net-divider");
  if (!dock || !route || divider?.kind !== "hazard") return group;
  const paint = new MeshStandardMaterial({ roughness: 0.96 });
  const dividerDepth = divider.points.map(({ z }) => z);
  group.add(
    recoveryDock({ x: level.bounds.max.x, z: dock.pos.z }, paint),
    laneMarks(
      route.pos,
      Math.max(...divider.points.map(({ x }) => x)),
      level.bounds.max.x,
      [Math.min(...dividerDepth), Math.max(...dividerDepth)],
      paint,
    ),
  );
  return group;
}
