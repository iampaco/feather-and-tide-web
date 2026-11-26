import { writeFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { openMenu } from "../fixtures/menu";
import { pointer } from "../fixtures/pointer";

interface Flight {
  readonly tick: number;
  readonly phase: string;
  readonly segment: string;
  readonly route: "mountain" | "lake" | null;
  readonly x: number;
  readonly z: number;
  readonly energy: number;
  readonly heading: number;
  readonly ridgeRecovery?: "blocked" | "clearing";
}

async function flight(page: Page): Promise<Flight> {
  const raw = await page.locator("#game").getAttribute("data-flight");
  if (!raw) throw new Error("Missing flight state");
  return JSON.parse(raw) as Flight;
}

async function advance(
  page: Page,
  until: (state: Flight) => boolean,
  ms = 200,
) {
  for (let i = 0; i < 100; i++) {
    const state = await flight(page);
    if (until(state)) return state;
    if (state.phase !== "playing") throw new Error("The journey stopped");
    await page.clock.runFor(ms);
  }
  throw new Error("The journey did not reach the expected position");
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
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 160);
}

for (const [route, lateralKey, clearSideX] of [
  ["mountain", "KeyD", -35],
  ["lake", "KeyA", 42],
] as const) {
  test(`desktop keyboard-only S2 ridge recovery reaches the ${route} route`, async ({
    page,
    hasTouch,
  }, info) => {
    test.skip(hasTouch, "keyboard controls and labels");
    test.setTimeout(240_000);
    await page.setViewportSize({ width: 850, height: 510 });
    await startJourney(page);

    await page.keyboard.down("KeyW");
    await advance(page, ({ z }) => z >= 130);
    await page.keyboard.down("KeyD");
    await advance(page, ({ x }) => x <= -26);
    await page.keyboard.up("KeyD");
    await advance(page, ({ z }) => z >= 196);
    await page.keyboard.down("KeyA");
    await advance(page, ({ x }) => x >= -1);
    await page.keyboard.up("KeyA");
    const blocked = await advance(
      page,
      (state) => state.ridgeRecovery === "blocked",
    );
    expect(blocked).toMatchObject({ segment: "S2", route: null });
    await page.clock.runFor(8000);
    const stillBlocked = await flight(page);
    expect(stillBlocked.tick - blocked.tick).toBeGreaterThanOrEqual(450);
    expect(stillBlocked).toMatchObject({
      x: blocked.x,
      z: blocked.z,
      energy: blocked.energy,
      phase: "playing",
      route: null,
      ridgeRecovery: "blocked",
    });
    await expect(page.locator("#hazard-notice")).toHaveText("分水岭挡住前进");
    await expect(page.locator("#warning-detail")).toContainText("按住 C 缓行");
    await expect(page.locator("#warning-detail")).toContainText("斜向来路");
    await expect(page.getByText("绕向短山口", { exact: true })).toBeVisible();
    await expect(page.getByText("绕向长湖路", { exact: true })).toBeVisible();
    await expect(page.getByText("绕向短山口", { exact: true })).toHaveAttribute(
      "data-marker-placement",
      "text",
    );
    await expect(page.getByText("绕向长湖路", { exact: true })).toHaveAttribute(
      "data-marker-placement",
      "text",
    );
    await page.screenshot({ path: info.outputPath("blocked.png") });

    await page.keyboard.up("KeyW");
    await page.keyboard.down("KeyC");
    await page.keyboard.down("KeyS");
    await page.keyboard.down(lateralKey);
    await advance(page, (state) => state.ridgeRecovery === "clearing", 100);
    await expect(page.locator("#hazard-notice")).toHaveText("正在脱离分水岭");
    const backedOut = await advance(page, ({ z }) => z <= blocked.z - 4, 100);
    expect(backedOut.energy).toBeLessThan(stillBlocked.energy);
    expect(backedOut.route).toBeNull();
    await page.keyboard.up("KeyC");
    await page.keyboard.up("KeyS");
    const alongside = await advance(page, ({ x }) =>
      clearSideX < 0 ? x <= clearSideX : x >= clearSideX,
    );
    expect(alongside.ridgeRecovery).toBeUndefined();
    await page.keyboard.up(lateralKey);
    await page.keyboard.down("KeyC");
    await page.keyboard.down("KeyW");
    await advance(page, ({ heading }) => Math.cos(heading) > 0.985, 100);
    await page.keyboard.up("KeyC");
    await page.clock.runFor(7400);
    const choice = await advance(page, (state) => state.route !== null, 600);
    await page.keyboard.up("KeyW");
    expect(choice).toMatchObject({ route, phase: "playing" });
    expect(choice.z).toBeGreaterThanOrEqual(350);
    await expect(page.locator("#notice")).toContainText(
      route === "mountain" ? "已进入短山口" : "已进入长湖路",
    );
    await page.screenshot({ path: info.outputPath(`${route}.png`) });
    await writeFile(
      info.outputPath("recovery.json"),
      JSON.stringify({ blocked, stillBlocked, backedOut, choice }, null, 2),
    );
  });
}

test("S2 landscape touch can back away using the visible guidance", async ({
  page,
  hasTouch,
}, info) => {
  test.skip(!hasTouch, "landscape touch controls");
  test.setTimeout(120_000);
  await startJourney(page);
  await pointer(page, "pointerdown", 51, 125, 240);
  await pointer(page, "pointermove", 51, 125, 194);
  await page.clock.runFor(27500);
  const blocked = await advance(
    page,
    (state) => state.ridgeRecovery === "blocked",
  );
  await expect(page.locator("#warning-detail")).toContainText("轻推摇杆");
  await expect(page.getByText("绕向短山口", { exact: true })).toBeVisible();
  await expect(page.getByText("绕向长湖路", { exact: true })).toBeVisible();
  await expect(page.getByText("绕向短山口", { exact: true })).toHaveAttribute(
    "data-marker-placement",
    "text",
  );
  await expect(page.getByText("绕向长湖路", { exact: true })).toHaveAttribute(
    "data-marker-placement",
    "text",
  );
  await page.screenshot({ path: info.outputPath("touch-blocked.png") });

  await pointer(page, "pointermove", 51, 117, 248);
  const backedOut = await advance(page, ({ z }) => z <= blocked.z - 4, 100);
  expect(backedOut.x).toBeGreaterThan(blocked.x);
  expect(backedOut.energy).toBeLessThan(blocked.energy);
  expect(backedOut.route).toBeNull();
  await pointer(page, "pointerup", 51, 117, 248);
});
