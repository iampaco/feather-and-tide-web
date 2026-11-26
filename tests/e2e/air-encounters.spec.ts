import { expect, test, type Page } from "@playwright/test";
import type { AirEncounterState } from "../../src/core/game";
import { openMenu } from "../fixtures/menu";
import { pointer } from "../fixtures/pointer";

interface Sample {
  x: number;
  z: number;
  tick: number;
  formation: number;
  encounters: AirEncounterState;
}

async function advance(page: Page, until: (s: Sample) => boolean) {
  for (let i = 0; i < 140; i++) {
    const raw = await page.locator("#game").getAttribute("data-flight");
    if (raw) {
      const state: Sample = JSON.parse(raw);
      if (until(state)) return state;
    }
    await page.clock.runFor(180);
  }
  throw new Error("Flight did not reach the encounter");
}

test("the family waits and the whole V can fly outside the launch", async ({
  page,
  hasTouch,
}, info) => {
  test.setTimeout(220000);
  await page.addInitScript(
    (touch) =>
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({
          low: touch,
          reduced: touch,
          mirror: touch,
          large: touch,
          music: false,
        }),
      ),
    hasTouch,
  );
  await page.clock.install();
  await openMenu(page, "/?diagnostics");
  await page.locator("#goose-entry").click();
  await expect(page.locator("#formation")).toBeVisible();
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 150);
  const width = page.viewportSize()?.width ?? 844;
  const x = width - 122,
    y = 245;
  if (hasTouch) {
    await pointer(page, "pointerdown", 21, x, y);
    await pointer(page, "pointermove", 21, x, y - 49);
  } else await page.keyboard.down("KeyW");
  await advance(page, (s) => s.z >= 40);
  await page.screenshot({ path: info.outputPath("S0-reeling.jpg") });
  const held = await advance(
    page,
    (s) => s.z >= 63 && s.encounters.kite === "holding",
  );
  await page.screenshot({ path: info.outputPath("S0-waiting.jpg") });
  const away = await advance(page, (s) => s.encounters.kite === "rising");
  expect(away.tick).toBeGreaterThan(held.tick);
  await advance(page, (s) => s.z >= 85);
  if (hasTouch) await pointer(page, "pointermove", 21, x + 36, y - 38);
  else await page.keyboard.down("KeyD");
  const preview = await advance(
    page,
    (s) => s.z >= 118 && s.encounters.glider === "inflating",
  );
  await page.screenshot({ path: info.outputPath("S1-launch.jpg") });
  if (hasTouch) {
    const button = await page.locator("#formation").boundingBox();
    if (!button) throw new Error("Ability control missing");
    await pointer(
      page,
      "pointerdown",
      22,
      button.x + button.width / 2,
      button.y + button.height / 2,
      "#formation",
    );
  } else await page.keyboard.down("Space");
  await advance(page, (s) => s.x < -32);
  if (hasTouch) await pointer(page, "pointermove", 21, x, y - 48);
  else await page.keyboard.up("KeyD");
  const passing = await advance(
    page,
    (s) => s.encounters.glider === "crossing" && s.formation > 0.99,
  );
  expect(passing.tick - preview.encounters.gliderTick).toBeGreaterThanOrEqual(
    180,
  );
  await page.screenshot({ path: info.outputPath("S1-outer.jpg") });
  const clear = await advance(page, (s) => s.z > 210);
  expect(clear.encounters.disrupted).toBe(false);
  expect(clear.formation).toBe(1);
});

test("touch approach shows the pilot before the crossing and freezes on pause", async ({
  page,
  hasTouch,
}, info) => {
  test.skip(!hasTouch, "landscape touch and pause controls");
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
  await pointer(page, "pointerdown", 31, 125, 245);
  await pointer(page, "pointermove", 31, 125, 199);
  await advance(page, (s) => s.z >= 125 && s.encounters.glider === "inflating");
  await expect(page.locator("#notice")).toContainText("滑翔伞起飞");
  await page.screenshot({ path: info.outputPath("S1-default-warning.jpg") });
  await pointer(page, "pointerup", 31, 125, 199);
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  await page.clock.runFor(150);
  const paused = await page.locator("#game").getAttribute("data-flight");
  await page.clock.runFor(3500);
  expect(await page.locator("#game").getAttribute("data-flight")).toBe(paused);
  await page.getByRole("button", { name: "继续飞行" }).click();
  await pointer(page, "pointerdown", 32, 125, 245);
  await pointer(page, "pointermove", 32, 125, 228);
  await advance(page, (s) => s.encounters.glider === "leaving");
  await pointer(page, "pointerup", 32, 125, 228);
});
