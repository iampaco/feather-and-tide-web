import type { ReindeerState } from "../core/game";
import { distance, type Vec2 } from "../core/math";
import { hazardOffset } from "../levels/moving-hazard";
import { insideCulvert, roadVehicle } from "../levels/reindeer-ground";
import type { ReindeerLevel } from "../levels/schema";
import { sampleReindeerDust } from "../simulation/reindeer-dust";
import { REINDEER } from "../simulation/reindeer-tuning";

/** Original filtered-noise Foley, driven by snapshots without affecting play. */
export class ReindeerSound {
  private readonly noise: AudioBuffer;
  private at: Vec2 | undefined;
  private stepDistance = 0;
  private lastStep = -Infinity;
  private called = false;
  private answered = false;
  private previousActors: ReindeerState["actors"] = [];
  private nextAir = 0;
  private nextRoad = 0;
  private readonly sources = new Set<AudioScheduledSourceNode>();

  constructor(
    private readonly context: AudioContext,
    private readonly output: AudioNode,
  ) {
    this.noise = context.createBuffer(
      1,
      context.sampleRate,
      context.sampleRate,
    );
    const data = this.noise.getChannelData(0);
    let seed = 7681;
    for (let i = 0; i < data.length; i++) {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      data[i] = seed / 2147483648 - 1;
    }
  }

  reset(): void {
    for (const item of this.sources) item.stop();
    this.sources.clear();
    this.at = undefined;
    this.stepDistance = 0;
    this.lastStep = -Infinity;
    this.called = false;
    this.answered = false;
    this.previousActors = [];
    this.nextAir = 0;
    this.nextRoad = 0;
  }

  private burst(
    now: number,
    length: number,
    frequency: number,
    volume: number,
    tone = false,
  ): void {
    const source = tone
      ? this.context.createOscillator()
      : this.context.createBufferSource();
    if (source instanceof OscillatorNode) {
      source.type = "triangle";
      source.frequency.setValueAtTime(frequency, now);
      source.frequency.exponentialRampToValueAtTime(
        frequency * 0.76,
        now + length,
      );
    } else {
      source.buffer = this.noise;
    }
    const filter = this.context.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = tone ? frequency * 2 : frequency;
    const gain = this.context.createGain();
    gain.gain.setValueAtTime(0.001, now);
    gain.gain.exponentialRampToValueAtTime(
      volume,
      now + Math.min(0.06, length * 0.15),
    );
    gain.gain.exponentialRampToValueAtTime(0.001, now + length);
    source.connect(filter).connect(gain).connect(this.output);
    this.sources.add(source);
    source.onended = () => {
      this.sources.delete(source);
      source.disconnect();
      filter.disconnect();
      gain.disconnect();
    };
    source.start(now);
    source.stop(now + length);
  }

  landing(hasReply: boolean): void {
    const now = this.context.currentTime;
    this.burst(now, 0.42, 208, 0.041, true);
    if (hasReply) this.burst(now + 0.2, 0.32, 275, 0.034, true);
  }

  render(state: ReindeerState, level: ReindeerLevel): void {
    const leader = state.actors[0];
    if (!leader) return;
    const now = this.context.currentTime;
    if (this.at) this.stepDistance += distance(this.at, leader.pos);
    this.at = leader.pos;
    const stride = leader.speed > 3.6 ? 1.32 : 0.94;
    const planting = leader.speed === 0 && this.stepDistance > stride * 0.36;
    if (
      (planting || this.stepDistance >= stride) &&
      now - this.lastStep >= 0.13
    ) {
      this.stepDistance = planting ? 0 : this.stepDistance % stride;
      this.lastStep = now;
      this.burst(
        now,
        0.12,
        insideCulvert(level.road, leader.pos) ? 420 : 260,
        planting ? 0.05 : 0.074,
      );
    }
    if (!state.waitTicks) {
      this.called = false;
      this.answered = false;
    } else if (!this.called && leader.speed === 0) {
      this.called = true;
      this.burst(now, 0.4, 208, 0.039, true);
    } else if (this.called && !this.answered && leader.speed === 0) {
      const responding = state.actors.some((actor, index) => {
        const prior = this.previousActors[index];
        if (!index || prior?.id !== actor.id || actor.status === "strayed")
          return false;
        const gap = distance(actor.pos, leader.pos);
        return (
          gap <= REINDEER.formationRadius * 3 &&
          distance(prior.pos, leader.pos) - gap > 0.008
        );
      });
      if (responding) {
        this.answered = true;
        this.burst(now + 0.14, 0.28, 275, 0.026, true);
      }
    }
    this.previousActors = state.actors;
    if (now >= this.nextAir) {
      this.nextAir = now + 1.48;
      const dust = sampleReindeerDust(level, state.tick, leader.pos);
      const rising =
        state.segmentId === "R3" && leader.pos.x > 0 && dust.phase !== "calm";
      this.burst(
        now,
        0.94,
        state.segmentId === "R4" ? 990 : rising ? 380 : 570,
        rising ? 0.042 : 0.029,
      );
    }
    if (now >= this.nextRoad && state.occupied.includes("vehicle-warning")) {
      this.nextRoad = now + 0.32;
      const car = roadVehicle(level);
      const position = car.points[0];
      if (!position) return;
      const offset = hazardOffset(car, state.tick);
      const gap = distance(leader.pos, {
        x: position.x + offset.x,
        z: position.z + offset.z,
      });
      if (gap < 32) this.burst(now, 0.31, 190, (32 - gap) * 0.003, false);
    }
  }
}
