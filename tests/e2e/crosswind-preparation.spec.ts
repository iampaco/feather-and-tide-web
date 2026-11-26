import { writeFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import type { Vec2 } from "../../src/core/math";
import { GOOSE } from "../../src/simulation/goose";
import { openMenu } from "../fixtures/menu";
import { pointer } from "../fixtures/pointer";

interface Flight extends Vec2 {
  readonly tick: number;
  readonly phase: string;
  readonly route: string | null;
  readonly basis: { readonly right: Vec2; readonly up: Vec2 };
  readonly rescue?: Vec2 & {
    readonly id: string;
    readonly ticks: number;
    readonly progress: number;
  };
}

async function flight(page: Page): Promise<Flight> {
  const raw = await page.locator("#game").getAttribute("data-flight");
  if (!raw) throw new Error("Missing flight state");
  return JSON.parse(raw) as Flight;
}

async function moveUntil(
  page: Page,
  until: (state: Flight) => boolean,
  ms = 200,
) {
  for (let i = 0; i < 180; i++) {
    const state = await flight(page);
    if (until(state)) return state;
    if (state.phase !== "playing") throw new Error("The journey stopped");
    await page.clock.runFor(ms);
  }
  throw new Error("The journey did not reach the expected state");
}

async function startJourney(page: Page): Promise<void> {
  await page.addInitScript(() =>
    localStorage.setItem(
      "feather-tide-settings-v1",
      JSON.stringify({ low: true, reduced: true, music: false }),
    ),
  );
  await page.clock.install();
  await openMenu(page, "/?diagnostics");
  await page.locator("#goose-entry").click();
  await expect(page.locator("#formation")).toBeVisible();
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 1500);
}

function pickupGap(state: Flight) {
  if (!state.rescue) throw new Error("Missing fixed S3 rescue");
  return Math.max(
    0,
    Math.hypot(state.x - state.rescue.x, state.z - state.rescue.z) -
      GOOSE.rescueRadius,
  );
}

const steering = [
  [0, 1, ["KeyW"]],
  [1, 1, ["KeyW", "KeyD"]],
  [1, 0, ["KeyD"]],
  [1, -1, ["KeyS", "KeyD"]],
  [0, -1, ["KeyS"]],
  [-1, -1, ["KeyS", "KeyA"]],
  [-1, 0, ["KeyA"]],
  [-1, 1, ["KeyW", "KeyA"]],
] as const;

async function pickUpTail(page: Page) {
  const start = await flight(page);
  let keys: readonly string[] = [];
  for (let i = 0; i < 120; i++) {
    const { x, z, basis, rescue, tick } = await flight(page);
    if (!rescue) return (tick - start.tick) / 60;
    if (rescue.id !== "goose-11") throw new Error("The rescue target changed");
    const dx = rescue.x - x;
    const dz = rescue.z - z;
    let best = -Infinity;
    let next: readonly string[] = [];
    for (const [right, up, candidate] of steering) {
      const vx = right * basis.right.x + up * basis.up.x;
      const vz = right * basis.right.z + up * basis.up.z;
      const alignment = (dx * vx + dz * vz) / Math.hypot(vx, vz);
      if (alignment <= best) continue;
      best = alignment;
      next = candidate;
    }
    for (const key of keys)
      if (!next.includes(key)) await page.keyboard.up(key);
    for (const key of next)
      if (!keys.includes(key)) await page.keyboard.down(key);
    keys = next;
    await page.clock.runFor(100);
  }
  throw new Error("The player did not bring the tail back");
}

test("desktop keyboard-only S3 shows the shorter pickup after slowing or forming", async ({
  browser,
  baseURL,
  hasTouch,
}, info) => {
  test.skip(hasTouch, "keyboard comparison from the title");
  test.setTimeout(230_000);
  const results = [];
  for (const strategy of ["cruise", "slow", "formation"] as const) {
    const page = await browser.newPage({
      baseURL,
      viewport: { width: 900, height: 530 },
    });
    try {
      await startJourney(page);
      await page.keyboard.down("KeyW");
      await moveUntil(page, ({ z }) => z >= 130);
      await page.keyboard.down("KeyA");
      await moveUntil(page, ({ x }) => x >= 25);
      await page.keyboard.up("KeyA");
      await moveUntil(page, ({ z }) => z >= 210);
      await page.keyboard.up("KeyW");
      await page.keyboard.down("KeyA");
      await moveUntil(page, ({ x }) => x >= 44);
      await page.keyboard.up("KeyA");
      await page.keyboard.down("KeyW");
      const entry = await moveUntil(page, ({ z }) => z >= 401);
      expect(entry.route).toBe("lake");
      const readout = page.locator("#goose-crosswind-distance");
      const entryGap = Number((await readout.textContent())?.match(/\d+/)?.[0]);
      if (strategy === "slow") await page.keyboard.down("KeyC");
      if (strategy === "formation") await page.keyboard.down("Space");
      await moveUntil(page, ({ z }) => z >= 424, 100);
      await expect(readout).toHaveText(/队尾间距约 \d+ 单位/);
      await expect(page.locator("#detail")).toContainText(/间距|折返/);
      const tailGap = Number((await readout.textContent())?.match(/\d+/)?.[0]);
      await page.screenshot({
        path: info.outputPath(`${strategy}-approach.png`),
      });

      await moveUntil(page, ({ z }) => z >= 431, 100);
      const drop = await moveUntil(page, ({ rescue }) => Boolean(rescue), 16);
      expect(drop.rescue).toMatchObject({
        id: "goose-11",
        ticks: GOOSE.rescueTicks,
      });
      const gap = pickupGap(drop);
      const reported = `掉队时直线距接应圈约 ${Math.round(gap)} 单位`;
      await expect(readout).toHaveText(reported);
      await expect(page.locator("#notice")).toHaveText("接应同伴");
      await expect(page.locator("#detail")).toContainText("沿标记飞入接应圈");
      await expect(page.locator("#goose-flight-announcement")).toContainText(
        reported,
      );
      await page.screenshot({ path: info.outputPath(`${strategy}-drop.png`) });

      await page.clock.runFor(400);
      expect(pickupGap(await flight(page))).toBeGreaterThan(gap + 1);
      await expect(readout).toHaveText(reported);
      await page.keyboard.up("KeyW");
      await page.keyboard.up("Space");
      await page.keyboard.down("KeyC");
      const pickupSeconds = await pickUpTail(page);
      await expect(readout).toBeHidden();
      results.push({ strategy, entryGap, tailGap, gap, pickupSeconds });
    } finally {
      await page.close();
    }
  }
  await writeFile(
    info.outputPath("comparison.json"),
    JSON.stringify(results, null, 2),
  );
  const [cruise, slow, formation] = results;
  if (!cruise || !slow || !formation) throw new Error("Missing comparison run");
  for (const prepared of [slow, formation]) {
    expect(prepared.entryGap).toBe(cruise.entryGap);
    expect(prepared.tailGap).toBeLessThan(cruise.tailGap);
    expect(prepared.gap).toBeLessThan(cruise.gap - 4);
  }
});

test("S3 landscape touch displays the tail gap and first pickup distance", async ({
  page,
  hasTouch,
}, info) => {
  test.skip(!hasTouch, "landscape touch layout");
  test.setTimeout(100_000);
  await startJourney(page);
  const stickX = 125;
  const stickY = 242;
  await pointer(page, "pointerdown", 51, stickX, stickY);
  await pointer(page, "pointermove", 51, stickX, stickY - 45);
  await moveUntil(page, ({ z }) => z >= 130);
  await pointer(page, "pointermove", 51, stickX - 33, stickY - 34);
  await moveUntil(page, ({ x }) => x >= 25);
  await pointer(page, "pointermove", 51, stickX, stickY - 45);
  await moveUntil(page, ({ z }) => z >= 210);
  await pointer(page, "pointermove", 51, stickX - 45, stickY);
  await moveUntil(page, ({ x }) => x >= 44);
  await pointer(page, "pointermove", 51, stickX, stickY - 45);
  await moveUntil(page, ({ z }) => z >= 401);
  await pointer(page, "pointermove", 51, stickX, stickY - 7);
  await moveUntil(page, ({ z }) => z >= 424);
  const readout = page.locator("#goose-crosswind-distance");
  await expect(readout).toBeVisible();
  await expect(readout).toHaveText(/队尾间距约 \d+ 单位/);
  await moveUntil(page, ({ z }) => z >= 431, 100);
  const drop = await moveUntil(page, ({ rescue }) => Boolean(rescue), 16);
  await expect(readout).toHaveText(
    `掉队时直线距接应圈约 ${Math.round(pickupGap(drop))} 单位`,
  );
  await expect(page.locator("#rescue-clock")).toBeVisible();
  await expect(page.locator("#detail")).toBeVisible();
  await page.screenshot({ path: info.outputPath("touch-drop.png") });
  await pointer(page, "pointerup", 51, stickX, stickY - 7);
});
