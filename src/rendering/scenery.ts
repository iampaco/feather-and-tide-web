import { AnimationMixer, Group, SkinnedMesh, type Object3D } from "three";
import type { GLTF, GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";
import type { GooseState } from "../core/game";
import type { LevelSchema } from "../levels/schema";
import { rotorPhase } from "../simulation/world";
import type { Landscape } from "./landscape";

const assets = [
  { id: "ENV-012", firstSegment: "S2" },
  { id: "STR-001", firstSegment: "S4" },
] as const;
// Published STR-001 hub pivot y is 2.45 Blender units.
export const TURBINE_SCALE = 13 / 2.45;
type ArtId = (typeof assets)[number]["id"];
type Load = { state: "loading" | "fallback" } | { state: "ready"; gltf: GLTF };

export class FlightScenery {
  readonly group = new Group();
  private readonly loads = new Map<ArtId, Load>();
  private readonly installed = new Set<ArtId>();
  private readonly rotors: (Object3D | undefined)[] = [];
  private readonly trees: { model: Object3D; mixer: AnimationMixer }[] = [];

  constructor(
    private readonly urls: ReadonlyMap<string, string>,
    private readonly loader: GLTFLoader,
  ) {}

  reset(): void {
    for (const { model, mixer } of this.trees) {
      mixer.stopAllAction();
      mixer.uncacheRoot(model);
      model.traverse((node) => {
        if (node instanceof SkinnedMesh) node.skeleton.dispose();
      });
    }
    this.trees.length = 0;
    this.rotors.length = 0;
    this.installed.clear();
    this.group.clear();
  }

  report(): Record<string, string> {
    return Object.fromEntries(
      assets.map(({ id }) => [
        id,
        this.installed.has(id)
          ? "model"
          : (this.loads.get(id)?.state ?? "procedural"),
      ]),
    );
  }

  update(
    level: LevelSchema,
    land: Landscape,
    state: GooseState,
    z: number,
    low: boolean,
    reduced: boolean,
  ): void {
    if (level.id === "migration" && state.airborne && !low) {
      for (const { id, firstSegment } of assets) {
        const start = level.segments.find(
          (segment) => segment.id === firstSegment,
        )?.start;
        if (start === undefined || z < start - 125) continue;
        const loaded = this.loads.get(id);
        if (!loaded) this.fetch(id);
        else if (loaded.state === "ready" && !this.installed.has(id))
          this.install(id, loaded.gltf, land);
      }
    }
    land.turbines.forEach(({ rotor }, index) => {
      const phase = rotorPhase(reduced ? 0 : state.tick, index);
      rotor.rotation.z = phase;
      const imported = this.rotors[index];
      // STR-001's exported hinge rotates about local -Z.
      if (imported) imported.rotation.z = -phase;
    });
    this.trees.forEach(({ mixer }, index) =>
      mixer.setTime(reduced ? 0 : state.tick / 60 + index * 0.27),
    );
  }

  private fetch(id: ArtId): void {
    const url = this.urls.get(id);
    this.loads.set(id, { state: url ? "loading" : "fallback" });
    if (!url) return;
    void this.loader
      .loadAsync(url)
      .then((gltf) => {
        this.loads.set(id, { state: "ready", gltf });
      })
      .catch(() => {
        // Keep the already-visible procedural landmarks on weak connections.
        this.loads.set(id, { state: "fallback" });
      });
  }

  private install(id: ArtId, gltf: GLTF, land: Landscape): void {
    if (id === "STR-001") {
      if (!gltf.scene.getObjectByName("Rotor")) {
        this.loads.set(id, { state: "fallback" });
        return;
      }
      land.turbines.forEach(({ model }, index) => {
        const authored = gltf.scene.clone();
        authored.position.copy(model.position);
        authored.rotation.y = Math.PI;
        authored.scale.setScalar(TURBINE_SCALE);
        this.rotors[index] = authored.getObjectByName("Rotor");
        this.group.add(authored);
        model.visible = false;
      });
    } else {
      const clip = gltf.animations.find(
        ({ name }) => name === "LeaningTree_WindCue",
      );
      if (!clip) {
        this.loads.set(id, { state: "fallback" });
        return;
      }
      for (const fallback of land.trees) {
        const authored = clone(gltf.scene);
        authored.position.copy(fallback.position);
        authored.scale.copy(fallback.scale);
        // The source canopy swings toward local -X. Both route cues point east.
        authored.rotation.y = Math.PI;
        const mixer = new AnimationMixer(authored);
        mixer.clipAction(clip).play();
        this.trees.push({ model: authored, mixer });
        this.group.add(authored);
        fallback.visible = false;
      }
    }
    this.installed.add(id);
  }
}
