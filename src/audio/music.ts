import type { GameState, Species } from "../core/game";
import type { AnyLevelSchema } from "../levels/schema";
import { landingMusic, soundtrack } from "./media";
import { ReindeerSound } from "./reindeer-sound";
import { WhaleSound } from "./whale-sound";
import { flightMix, phrases, type ScoreLayer } from "./palette";

interface AudioStage {
  readonly context: AudioContext;
  readonly score: GainNode;
  readonly synth: GainNode;
  readonly recording: GainNode;
  readonly effects: AudioNode;
}

function bus(context: AudioContext, output: AudioNode): GainNode {
  const gain = context.createGain();
  gain.gain.value = 0;
  gain.connect(output);
  return gain;
}

function createStage(): AudioStage {
  const context = new AudioContext();
  const master = context.createDynamicsCompressor();
  master.threshold.value = -15;
  master.knee.value = 18;
  master.ratio.value = 3;
  master.connect(context.destination);
  const score = bus(context, master);
  return {
    context,
    score,
    synth: bus(context, score),
    recording: bus(context, score),
    effects: master,
  };
}

function glide(
  param: AudioParam,
  value: number,
  now: number,
  time: number,
): void {
  param.cancelScheduledValues(now);
  param.setTargetAtTime(value, now, time);
}

function hz(pitch: number): number {
  return 440 * 2 ** ((pitch - 69) / 12);
}

const recordingLevels: Record<ScoreLayer, number> = {
  ambient: 0,
  journey: 0.49,
  focus: 0.37,
  tension: 0.28,
  care: 0.32,
  release: 0.56,
};

export class MusicDirector {
  private stage: AudioStage | undefined;
  private track: HTMLAudioElement | undefined;
  private landingRequested = false;
  private landingBuffer: AudioBuffer | undefined;
  private recordingGain = -1;
  private tookOff = false;
  private nextBeat = 0;
  private beatIndex = 0;
  private layer: ScoreLayer = "ambient";
  private lake = false;
  private cadence = false;
  private scoreGain = -1;
  private reindeerSound: ReindeerSound | undefined;
  private whaleSound: WhaleSound | undefined;
  private readonly voices = new Set<AudioScheduledSourceNode>();

  // Called synchronously from a user gesture before any asynchronous loading.
  async unlock(
    musicEnabled: boolean,
    species: Species = "goose",
  ): Promise<void> {
    this.stage ??= createStage();
    const { context, recording } = this.stage;
    if (musicEnabled && !this.track) {
      const track = new Audio();
      track.preload = "none";
      track.loop = true;
      context.createMediaElementSource(track).connect(recording);
      this.track = track;
    }
    if (musicEnabled && species !== "reindeer" && !this.landingRequested) {
      this.landingRequested = true;
      void fetch(landingMusic)
        .then((response) => {
          if (!response.ok) throw new Error("Landing score unavailable");
          return response.arrayBuffer();
        })
        .then((bytes) => context.decodeAudioData(bytes))
        .then((buffer) => {
          this.landingBuffer = buffer;
        })
        .catch(() => {});
    }
    const recordingUrl =
      species === "reindeer" ? soundtrack.theme : soundtrack[species];
    if (musicEnabled && this.track) {
      if (this.track.getAttribute("src") !== recordingUrl)
        this.track.src = recordingUrl;
      // Start within the gesture so Safari permits playback when the scene loads.
      if (this.track.paused && !this.track.error)
        void this.track.play().catch(() => {});
    }
    if (context.state !== "running") await context.resume();
  }

  pause(): void {
    this.track?.pause();
    if (this.stage) void this.stage.context.suspend().catch(() => {});
  }

  reset(): void {
    this.reindeerSound?.reset();
    this.whaleSound?.reset();
    for (const voice of this.voices) voice.stop();
    this.voices.clear();
    if (this.track) this.track.currentTime = 0;
    if (this.stage) {
      const { context, score } = this.stage;
      const now = context.currentTime;
      if (Number.isFinite(now)) score.gain.cancelScheduledValues(now);
      score.gain.value = 0;
    }
    this.recordingGain = -1;
    this.tookOff = false;
    this.nextBeat = 0;
    this.beatIndex = 0;
    this.layer = "ambient";
    this.lake = false;
    this.cadence = false;
    this.scoreGain = -1;
  }

  private note(
    stage: AudioStage,
    pitch: number,
    when: number,
    duration: number,
    amplitude: number,
    timbre: OscillatorType = "sine",
  ): void {
    const { context } = stage;
    const tone = context.createOscillator();
    tone.type = timbre;
    tone.frequency.value = hz(pitch);
    const envelope = context.createGain();
    envelope.gain.setValueAtTime(0.0001, when);
    envelope.gain.exponentialRampToValueAtTime(amplitude, when + 0.11);
    envelope.gain.exponentialRampToValueAtTime(0.0001, when + duration);
    const stereo = context.createStereoPanner();
    tone.connect(envelope).connect(stereo).connect(stage.synth);
    this.voices.add(tone);
    tone.onended = () => {
      this.voices.delete(tone);
      tone.disconnect();
      envelope.disconnect();
      stereo.disconnect();
    };
    tone.start(when);
    tone.stop(when + duration);
  }

  private playCoda(stage: AudioStage, now: number): void {
    if (!this.landingBuffer) {
      this.note(stage, 50, now + 0.14, 2.75, 0.11);
      this.note(stage, 66, now + 0.26, 1.28, 0.12, "triangle");
      this.note(stage, 69, now + 0.68, 1.7, 0.12);
      this.note(stage, 74, now + 1.18, 2.05, 0.14);
      return;
    }
    const clip = stage.context.createBufferSource();
    clip.buffer = this.landingBuffer;
    clip.connect(stage.score);
    this.voices.add(clip);
    clip.onended = () => {
      this.voices.delete(clip);
      clip.disconnect();
    };
    // Give the flight track time to fade and fit inside the landing view.
    clip.start(now + 0.2);
  }

  render(
    state: GameState,
    musicEnabled: boolean,
    level: AnyLevelSchema,
    reindeerEnding?: { progress: number; companion?: string },
  ): void {
    const stage = this.stage;
    if (!stage || stage.context.state !== "running") return;
    const now = stage.context.currentTime;
    // WebKit can have an unavailable audio clock while the device starts.
    if (!Number.isFinite(now)) return;
    const landing = state.phase === "landing";
    const live = state.phase === "playing" || landing;
    const reindeer = state.species === "reindeer";
    if (state.species === "whale" && level.species === "whale") {
      if (!musicEnabled || !live) {
        this.whaleSound?.reset();
        this.whaleSound = undefined;
      } else {
        this.whaleSound ??= new WhaleSound(stage.context, stage.effects);
        if (state.phase === "playing") this.whaleSound.render(state, level);
        else if (!this.cadence) this.whaleSound.reunion();
      }
    }
    const mix = flightMix(state, level);
    if (!musicEnabled || !live) this.track?.pause();
    const traveling = state.species !== "goose" || state.airborne;
    if (traveling && !this.tookOff) {
      this.tookOff = true;
      if (this.track && this.track.currentTime > 0.1)
        this.track.currentTime = 0;
    }
    const endingProgress = reindeerEnding?.progress ?? 0;
    const reindeerRelease =
      endingProgress < 0.27 ? 0.32 : endingProgress < 0.55 ? 0.56 : 0;
    const recordedLevel =
      musicEnabled &&
      (state.phase === "playing" || (reindeer && landing)) &&
      traveling &&
      this.track &&
      !this.track.paused &&
      this.track.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA
        ? landing
          ? reindeerRelease
          : recordingLevels[mix.layer] + (mix.lake ? 0.04 : 0)
        : 0;
    if (recordedLevel !== this.recordingGain) {
      this.recordingGain = recordedLevel;
      glide(
        stage.recording.gain,
        recordedLevel,
        now,
        landing ? (reindeer ? (recordedLevel ? 0.15 : 0.42) : 0.09) : 0.22,
      );
      glide(stage.synth.gain, recordedLevel ? 0 : 1, now, 0.15);
    }
    const loudness =
      musicEnabled && live ? (landing && !reindeer ? 0.63 : mix.music) : 0;
    if (loudness !== this.scoreGain) {
      this.scoreGain = loudness;
      glide(
        stage.score.gain,
        loudness,
        now,
        state.species === "whale" && state.phase === "playing" ? 0.42 : 0.2,
      );
    }
    if (!live) return;
    if (reindeer) {
      if (level.species === "reindeer" && musicEnabled) {
        // Foley must stay audible while the recording takes over the score.
        this.reindeerSound ??= new ReindeerSound(stage.context, stage.score);
        if (!landing) this.reindeerSound.render(state, level);
        else if (!this.cadence) {
          this.cadence = true;
          this.reindeerSound.landing(Boolean(reindeerEnding?.companion));
        }
      }
      return;
    }

    if (landing) {
      if (!this.cadence) {
        this.cadence = true;
        if (musicEnabled) this.playCoda(stage, now);
      }
      return;
    }

    if (
      recordedLevel ||
      !traveling ||
      !musicEnabled ||
      this.nextBeat > now + 0.075
    )
      return;

    if (this.beatIndex === 0) {
      this.layer = mix.layer;
      this.lake = mix.lake;
    }
    const phrase = phrases[this.layer];
    const beat = this.lake ? phrase.beat * 1.12 : phrase.beat;
    const start = Math.max(now + 0.02, this.nextBeat);
    const pitch = phrase.melody[this.beatIndex];
    if (this.beatIndex === 0)
      this.note(stage, phrase.bass, start, beat * 3.5, 0.115);
    if (pitch != null) {
      this.note(
        stage,
        pitch,
        start,
        beat * 1.95,
        0.15,
        this.lake ? "sine" : "triangle",
      );
      this.note(
        stage,
        pitch + 12,
        start + 0.09,
        beat * 1.45,
        this.lake ? 0.038 : 0.024,
      );
    }
    this.nextBeat = start + beat;
    this.beatIndex = (this.beatIndex + 1) % phrase.melody.length;
  }
}
