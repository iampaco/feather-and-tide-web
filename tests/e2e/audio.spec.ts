import { expect, test, type Page } from "@playwright/test";
import { migration } from "../fixtures/flight";
import { openMenu, openTitle } from "../fixtures/menu";
import { reindeerLevel } from "../fixtures/reindeer";
import { whaleLevel } from "../fixtures/whale";

type AudioSample = {
  readonly state: string;
  readonly buffers: number;
  readonly codas: number;
  readonly tones: number;
  readonly calls: number;
  readonly filterFrequencies: readonly number[];
  readonly recording: string;
  readonly recordingAt: number;
  readonly recordingPaused: boolean;
  readonly recordingLoops: boolean;
  readonly recordingRms: number;
  readonly rms: number;
};

type AudioWindow = Window & {
  measureFlightAudio?: () => AudioSample;
};

async function installAudioProbe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    let context: AudioContext | undefined;
    let analyser: AnalyserNode | undefined;
    let recordingAnalyser: AnalyserNode | undefined;
    let buffers = 0;
    let codas = 0;
    let tones = 0;
    let calls = 0;
    const filterFrequencies: number[] = [];
    let recording: HTMLMediaElement | undefined;
    let recordingSource: MediaElementAudioSourceNode | undefined;
    const createFilter = AudioContext.prototype.createBiquadFilter;
    AudioContext.prototype.createBiquadFilter = function () {
      const filter = createFilter.call(this);
      const setFrequency = filter.frequency.setValueAtTime.bind(
        filter.frequency,
      );
      filter.frequency.setValueAtTime = (value, when) => {
        filterFrequencies.push(value);
        return setFrequency(value, when);
      };
      return filter;
    };
    const connectRecording = AudioContext.prototype.createMediaElementSource;
    AudioContext.prototype.createMediaElementSource = function (
      element: HTMLMediaElement,
    ): MediaElementAudioSourceNode {
      recording = element;
      recordingSource = connectRecording.call(this, element);
      return recordingSource;
    };
    const connect = AudioNode.prototype.connect;
    AudioNode.prototype.connect = new Proxy(connect, {
      apply(target, source: AudioNode, args: [AudioNode | AudioParam]) {
        if (source === recordingSource && args[0] instanceof GainNode) {
          recordingAnalyser = source.context.createAnalyser();
          Reflect.apply(target, args[0], [recordingAnalyser]);
        }
        if (args[0] === source.context.destination && !analyser) {
          context = source.context as AudioContext;
          analyser = context.createAnalyser();
          Reflect.apply(target, source, [analyser]);
        }
        return Reflect.apply(target, source, args);
      },
    });
    const startTone = OscillatorNode.prototype.start;
    OscillatorNode.prototype.start = function (when?: number): void {
      startTone.call(this, when);
      tones++;
      if (this.type === "sawtooth") calls++;
    };
    const startBuffer = AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start = function (
      when?: number,
      offset?: number,
      duration?: number,
    ): void {
      startBuffer.call(this, when, offset, duration);
      buffers++;
      if (this.buffer && Math.abs(this.buffer.duration - 3.34) < 0.1) codas++;
    };
    function rms(node: AnalyserNode | undefined): number {
      const samples = new Float32Array(node?.fftSize ?? 0);
      node?.getFloatTimeDomainData(samples);
      return Math.sqrt(
        samples.reduce((energy, sample) => energy + sample ** 2, 0) /
          Math.max(samples.length, 1),
      );
    }
    (window as AudioWindow).measureFlightAudio = () => {
      return {
        state: context?.state ?? "locked",
        buffers,
        codas,
        tones,
        calls,
        filterFrequencies: [...filterFrequencies],
        recording: recording?.currentSrc ?? "",
        recordingAt: recording?.currentTime ?? 0,
        recordingPaused: recording?.paused ?? true,
        recordingLoops: recording?.loop ?? false,
        recordingRms: rms(recordingAnalyser),
        rms: rms(analyser),
      };
    };
  });
}

async function sample(page: Page): Promise<AudioSample | undefined> {
  return page.evaluate(() => (window as AudioWindow).measureFlightAudio?.());
}

test("A01 the title player streams the theme and the whale track and stops on return", async ({
  page,
}, info) => {
  await openTitle(page);
  await page.getByRole("button", { name: "原声试听" }).click();
  const player = page.locator("#soundtrack-player");
  const playhead = () =>
    player.evaluate((media) => (media as HTMLAudioElement).currentTime);
  await expect(player).toHaveAttribute("src", /feather-and-tide\.mp3$/);
  await expect.poll(playhead).toBeGreaterThan(0.15);
  await page.getByLabel("曲目").selectOption("whale");
  await expect(player).toHaveAttribute("src", /deep-blue-drones\.mp3$/);
  await expect.poll(playhead).toBeGreaterThan(0.15);
  await page.screenshot({
    path: info.outputPath("soundtrack.png"),
    scale: "css",
  });
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await expect(player).toHaveJSProperty("paused", true);
  await expect(player).not.toHaveAttribute("src");
  await expect(page.getByRole("button", { name: "进入游戏" })).toBeVisible();
});

test("A01 BGM unlocks, suspends and mutes without other game sounds", async ({
  page,
  hasTouch,
}) => {
  await installAudioProbe(page);
  await page.addInitScript(() => {
    localStorage.setItem(
      "feather-tide-settings-v1",
      '{"ambience":true,"music":false}',
    );
  });
  await openMenu(page);
  expect((await sample(page))?.state).toBe("locked");
  await page.getByRole("button", { name: "设置" }).click();
  await expect(page.getByLabel("环境音与呼应")).toHaveCount(0);
  await expect(page.getByLabel("配乐", { exact: true })).not.toBeChecked();
  await page.getByRole("button", { name: "返回", exact: true }).click();
  const journey = page.getByRole("button", { name: /^斑头雁/ });
  if (hasTouch) await journey.tap();
  else await journey.click();
  await expect(page.getByRole("button", { name: "结阵" })).toBeVisible();

  await page.keyboard.down("KeyW");
  // Let the leader reach flight speed so the resumed music has its theme.
  await expect(page.locator("#notice")).toHaveText("松开移动键，试试滑翔");
  await page.keyboard.up("KeyW");
  await expect.poll(async () => (await sample(page))?.state).toBe("running");
  expect(await sample(page)).toMatchObject({
    buffers: 0,
    tones: 0,
    recording: "",
    rms: 0,
  });
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await expect(page.getByRole("heading", { name: "飞行暂停" })).toBeVisible();
  await expect.poll(async () => (await sample(page))?.state).toBe("suspended");
  await page.getByRole("button", { name: "设置" }).click();
  await page.getByLabel("配乐", { exact: true }).check();
  await page.getByRole("button", { name: "返回", exact: true }).click();
  expect((await sample(page))?.state).toBe("suspended");
  await page.getByRole("button", { name: "继续飞行" }).click();
  await expect
    .poll(async () => (await sample(page))?.recordingAt ?? 0)
    .toBeGreaterThan(0.15);
  expect((await sample(page))?.recording).toContain("plateau-at-dusk.mp3");
  await expect
    .poll(async () => (await sample(page))?.rms ?? 0)
    .toBeGreaterThan(0.004);
  expect((await sample(page))?.buffers).toBe(0);

  await page.getByRole("button", { name: "暂停", exact: true }).click();
  expect((await sample(page))?.recordingPaused).toBe(true);
  await page.getByRole("button", { name: "设置" }).click();
  await page.getByLabel("配乐", { exact: true }).uncheck();
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await page.getByRole("button", { name: "继续飞行" }).click();
  await expect.poll(async () => (await sample(page))?.state).toBe("running");
  await expect
    .poll(async () => (await sample(page))?.rms ?? 1)
    .toBeLessThan(0.001);
  expect((await sample(page))?.buffers).toBe(0);
  expect((await sample(page))?.recordingPaused).toBe(true);
});

test("A01 a missing flight recording falls back to the synthesized score", async ({
  page,
}) => {
  await installAudioProbe(page);
  await page.route("**/plateau-at-dusk.mp3", (route) => route.abort());
  await openMenu(page);
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await expect(page.getByRole("button", { name: "结阵" })).toBeVisible();
  await page.keyboard.down("KeyW");
  await expect
    .poll(async () => (await sample(page))?.tones ?? 0)
    .toBeGreaterThan(2);
  await page.keyboard.up("KeyW");
  await expect
    .poll(async () => (await sample(page))?.rms ?? 0)
    .toBeGreaterThan(0.004);
  expect((await sample(page))?.buffers).toBe(0);
});

test("A01 the S3 rescue cue leaves only music in the mix", async ({ page }) => {
  await installAudioProbe(page);
  await page.route("**/levels/migration.json", (route) =>
    route.fulfill({
      json: { ...migration, spawn: { x: 0, z: 429 }, spawnSegment: "S3" },
    }),
  );
  await openMenu(page);
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await expect(page.getByRole("button", { name: "结阵" })).toBeVisible();
  await page.keyboard.down("KeyW");
  await expect(page.locator("#flight-cue").getByRole("timer")).toBeVisible();
  await page.keyboard.up("KeyW");
  await expect
    .poll(async () => (await sample(page))?.rms ?? 0)
    .toBeGreaterThan(0.004);
  expect(await sample(page)).toMatchObject({ buffers: 0, calls: 0 });
});

test("A01 all geese landing cues one recorded coda", async ({ page }) => {
  await installAudioProbe(page);
  await page.route("**/levels/migration.json", (route) =>
    route.fulfill({
      json: { ...migration, spawn: { x: 0, z: 798 }, spawnSegment: "S6" },
    }),
  );
  await openMenu(page);
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await expect(page.getByRole("button", { name: "结阵" })).toBeVisible();
  expect((await sample(page))?.codas).toBe(0);
  await page.keyboard.down("KeyW");
  await expect(page.getByRole("button", { name: "跳过落脚演出" })).toBeVisible({
    timeout: 12_000,
  });
  await page.keyboard.up("KeyW");
  await expect.poll(async () => (await sample(page))?.codas).toBe(1);
  await expect(page.getByRole("heading", { name: "一起抵达" })).toBeVisible({
    timeout: 10_000,
  });
  expect((await sample(page))?.codas).toBe(1);
  expect((await sample(page))?.buffers).toBe(1);
  expect((await sample(page))?.recordingPaused).toBe(true);
});

test("WH-A14 surfaced breathing and water play independently of the score and respect mute", async ({
  page,
}) => {
  test.setTimeout(60_000);
  await installAudioProbe(page);
  await openMenu(page);
  await page.getByRole("button", { name: /^鲸/ }).click();
  await expect(page.locator("#whale-depth")).toHaveText("水面");
  await expect
    .poll(async () => (await sample(page))?.recordingAt ?? 0)
    .toBeGreaterThan(0.15);
  await expect
    .poll(async () => (await sample(page))?.filterFrequencies)
    .toContain(670);
  await page.keyboard.down("Space");
  try {
    await expect(page.locator("#whale-depth")).toHaveText("浅潜");
  } finally {
    await page.keyboard.up("Space");
  }
  await expect
    .poll(async () => (await sample(page))?.filterFrequencies)
    .toContain(1460);
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  await expect.poll(async () => (await sample(page))?.state).toBe("suspended");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByLabel("配乐", { exact: true }).uncheck();
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await page.getByRole("button", { name: "继续航行", exact: true }).click();
  await expect.poll(async () => (await sample(page))?.state).toBe("running");
  await expect
    .poll(async () => (await sample(page))?.rms ?? 1)
    .toBeLessThan(0.001);
});

for (const [segment, spawn, pitch] of [
  ["W1", { x: 0, z: 389 }, 324],
  ["W3", { x: 58, z: 1085 }, 282],
] as const) {
  test(`WH-A14 ${segment} has a distinct local vessel cue`, async ({
    page,
  }) => {
    await installAudioProbe(page);
    await page.route("**/levels/whale.json", (route) =>
      route.fulfill({
        json: {
          ...whaleLevel,
          spawn,
          spawnSegment: segment,
          zones: whaleLevel.zones.map((zone) =>
            zone.kind === "hazard" && zone.motion && zone.id === "cargo-ship"
              ? { ...zone, motion: { ...zone.motion, phaseTicks: 4500 } }
              : zone,
          ),
        },
      }),
    );
    await openMenu(page);
    await page.getByRole("button", { name: /^鲸/ }).click();
    await expect(page.locator("#whale-depth")).toHaveText("水面");
    await expect
      .poll(async () => (await sample(page))?.filterFrequencies)
      .toContain(pitch);
  });
}

test("RD-A17 the reindeer theme loops, resumes and fades into landing", async ({
  page,
  hasTouch,
}) => {
  test.setTimeout(75_000);
  await installAudioProbe(page);
  // Put the goal near the spawn to exercise the real audio and ending flow in one trip.
  await page.route("**/levels/reindeer.json", (route) =>
    route.fulfill({
      json: {
        ...reindeerLevel,
        zones: reindeerLevel.zones.map((zone) =>
          zone.kind === "goal"
            ? {
                ...zone,
                points: [
                  { x: -20, z: 18 },
                  { x: 20, z: 18 },
                  { x: 20, z: 50 },
                  { x: -20, z: 50 },
                  { x: -20, z: 18 },
                ],
              }
            : zone,
        ),
      },
    }),
  );
  await openMenu(page);
  const journey = page.getByRole("button", { name: /^驯鹿/ });
  if (hasTouch) await journey.tap();
  else await journey.click();
  await expect(page.getByRole("button", { name: "等候" })).toBeVisible();
  await expect
    .poll(async () => (await sample(page))?.recordingAt ?? 0)
    .toBeGreaterThan(0.15);
  expect(await sample(page)).toMatchObject({
    recording: expect.stringMatching(/\/feather-and-tide\.mp3$/),
    recordingLoops: true,
    recordingPaused: false,
  });
  await expect
    .poll(async () => (await sample(page))?.recordingRms ?? 0)
    .toBeGreaterThan(0.004);
  await expect
    .poll(async () => (await sample(page))?.rms ?? 0)
    .toBeGreaterThan(0.004);

  const pause = page.getByRole("button", { name: "暂停", exact: true });
  const resume = page.getByRole("button", { name: "继续旅程", exact: true });
  await pause.click();
  await expect.poll(async () => (await sample(page))?.state).toBe("suspended");
  const paused = await sample(page);
  expect(paused?.recordingPaused).toBe(true);
  await resume.click();
  await expect
    .poll(async () => (await sample(page))?.recordingAt ?? 0)
    .toBeGreaterThan((paused?.recordingAt ?? 0) + 0.15);

  const settings = page.getByRole("button", { name: "设置", exact: true });
  const music = page.getByLabel("配乐", { exact: true });
  const back = page.getByRole("button", { name: "返回", exact: true });
  await pause.click();
  await settings.click();
  await music.uncheck();
  await back.click();
  await resume.click();
  await expect.poll(async () => (await sample(page))?.state).toBe("running");
  await expect
    .poll(async () => (await sample(page))?.rms ?? 1)
    .toBeLessThan(0.001);
  expect((await sample(page))?.recordingPaused).toBe(true);

  await pause.click();
  await settings.click();
  await music.check();
  await back.click();
  await resume.click();
  await expect
    .poll(async () => (await sample(page))?.recordingPaused)
    .toBe(false);
  await page.keyboard.down("Shift");
  await page.keyboard.down("KeyW");
  const skip = page.getByRole("button", { name: "跳过落脚演出" });
  try {
    await expect(skip).toBeVisible({ timeout: 16_000 });
  } finally {
    await page.keyboard.up("KeyW");
    await page.keyboard.up("Shift");
  }
  expect(await sample(page)).toMatchObject({
    recordingPaused: false,
    codas: 0,
  });
  await skip.click();
  await expect(page.getByRole("heading", { name: "一起抵达" })).toBeVisible();
  await expect
    .poll(async () => (await sample(page))?.recordingPaused)
    .toBe(true);
});
