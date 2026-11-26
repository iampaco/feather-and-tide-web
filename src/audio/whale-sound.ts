import type { WhaleState } from "../core/game";
import type { WhaleLevel } from "../levels/schema";
import { hazardPoints } from "../levels/whale-geometry";
import { activeNoiseAt, insideNoise } from "../levels/whale-noise";
import { surfaced } from "../simulation/world-rules";

/** Original procedural water, breathing and vessel sounds. Reads voyage snapshots. */
export class WhaleSound {
  private readonly water: AudioBuffer;
  private readonly voices = new Set<AudioScheduledSourceNode>();
  private previousActors: WhaleState["actors"] = [];
  private nextSwell = 0;
  private nextBreath = 0;
  private nextEngine = 0;
  private heardShip = false;

  constructor(
    private readonly context: AudioContext,
    private readonly output: AudioNode,
  ) {
    this.water = context.createBuffer(
      1,
      context.sampleRate * 2,
      context.sampleRate,
    );
    const samples = this.water.getChannelData(0);
    let seed = 6217;
    for (let i = 0; i < samples.length; i++) {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      samples[i] = seed / 2147483648 - 1;
    }
  }

  reset(): void {
    for (const voice of this.voices) voice.stop();
    this.voices.clear();
    this.previousActors = [];
    this.nextSwell = 0;
    this.nextBreath = 0;
    this.nextEngine = 0;
    this.heardShip = false;
  }

  private play(
    start: number,
    seconds: number,
    pitch: number,
    volume: number,
    type?: OscillatorType,
  ): void {
    const filter = this.context.createBiquadFilter();
    filter.type = type ? "lowpass" : "bandpass";
    filter.Q.value = type ? 0.55 : 0.8;
    filter.frequency.setValueAtTime(type ? pitch * 3 : pitch, start);
    filter.frequency.exponentialRampToValueAtTime(
      type ? pitch * 2.35 : pitch * 0.57,
      start + seconds,
    );
    const gain = this.context.createGain();
    gain.gain.setValueAtTime(0.001, start);
    const attack = seconds * (seconds > 1 ? 0.38 : 0.18);
    gain.gain.exponentialRampToValueAtTime(volume, start + attack);
    gain.gain.exponentialRampToValueAtTime(0.001, start + seconds);

    let voice: AudioScheduledSourceNode;
    if (type) {
      const oscillator = this.context.createOscillator();
      oscillator.type = type;
      oscillator.frequency.setValueAtTime(pitch, start);
      oscillator.frequency.exponentialRampToValueAtTime(
        pitch * 0.88,
        start + seconds,
      );
      voice = oscillator;
    } else {
      const noise = this.context.createBufferSource();
      noise.buffer = this.water;
      voice = noise;
    }
    voice.connect(filter).connect(gain).connect(this.output);
    this.voices.add(voice);
    voice.onended = () => {
      this.voices.delete(voice);
      voice.disconnect();
      filter.disconnect();
      gain.disconnect();
    };
    voice.start(start);
    voice.stop(start + seconds);
  }

  render(state: WhaleState, level: WhaleLevel): void {
    const leader = state.actors[0];
    if (!leader) return;
    const now = this.context.currentTime;
    const air = surfaced(leader);
    if (now >= this.nextSwell) {
      this.nextSwell = now + 1.45 + 0.16 * Math.sin(state.tick * 0.013);
      this.play(
        now,
        1.8,
        air ? 670 : leader.dive.layer === "deep" ? 230 : 390,
        air ? 0.091 : 0.049,
      );
    }
    if (
      now >= this.nextBreath &&
      state.actors.some((actor, index) => {
        const before = this.previousActors[index];
        return (
          before?.id === actor.id &&
          before.dive.depth > 0 &&
          surfaced(actor) &&
          Math.hypot(actor.pos.x - leader.pos.x, actor.pos.z - leader.pos.z) <
            32
        );
      })
    ) {
      this.nextBreath = now + 0.23;
      this.play(now, 0.5, 1460, 0.17);
      this.play(now + 0.05, 0.48, 490, 0.077);
    }
    this.previousActors = state.actors;

    if (state.segmentId === "W1") {
      const ship = level.zones.find(
        (zone) => zone.kind === "hazard" && zone.id === "cargo-ship",
      );
      const gap =
        ship?.kind === "hazard"
          ? Math.min(
              ...hazardPoints(ship, state.tick).map(({ x, z }) =>
                Math.hypot(x - leader.pos.x, z - leader.pos.z),
              ),
            )
          : Infinity;
      if (gap > 72) this.heardShip = false;
      if (!this.heardShip && gap < 53) {
        this.heardShip = true;
        this.play(now, 0.78, 108, air ? 0.099 : 0.053, "triangle");
        this.play(now + 0.047, 0.69, 159, air ? 0.032 : 0.021, "sine");
      }
    }

    if (
      state.segmentId === "W3" &&
      now >= this.nextEngine &&
      activeNoiseAt(level, state.tick).some((zone) =>
        state.actors.some(
          ({ pos }) =>
            insideNoise(zone, { x: pos.x, z: pos.z + 13 }) ||
            insideNoise(zone, pos),
        ),
      )
    ) {
      this.nextEngine = now + 0.58;
      this.play(now, 0.64, 94, 0.062, "sawtooth");
      this.play(now, 0.7, 285, 0.115);
    }
  }

  reunion(): void {
    const now = this.context.currentTime;
    this.play(now, 0.58, 1400, 0.115);
    this.play(now + 0.2, 1.25, 214, 0.045, "sine");
    this.play(now + 0.67, 1.1, 286, 0.035, "triangle");
  }
}
