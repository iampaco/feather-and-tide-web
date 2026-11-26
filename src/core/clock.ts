export const STEP_SEC = 1 / 60;
export const MAX_SUBSTEPS = 5;

export class FixedClock {
  private previousMs: number | undefined;
  private accumulator = 0;

  constructor(private readonly maxSubsteps = MAX_SUBSTEPS) {}

  reset(): void {
    this.previousMs = undefined;
    this.accumulator = 0;
  }

  frame(nowMs: number, playing: boolean, step: () => boolean): number {
    if (!playing) {
      this.reset();
      return 1;
    }

    const previousMs = this.previousMs;
    this.previousMs = nowMs;
    if (previousMs === undefined) return 0;

    this.accumulator += Math.min(
      0.25,
      Math.max(0, (nowMs - previousMs) / 1000),
    );
    const due = Math.floor((this.accumulator + 1e-10) / STEP_SEC);
    const steps = Math.min(due, this.maxSubsteps);
    for (let i = 0; i < steps; i++) {
      if (!step()) {
        this.reset();
        return 1;
      }
    }

    this.accumulator =
      due > steps ? 0 : Math.max(0, this.accumulator - steps * STEP_SEC);
    return this.accumulator / STEP_SEC;
  }
}
