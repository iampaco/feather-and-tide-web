import { expect, test, type Page } from "@playwright/test";
import { openTitle } from "../fixtures/menu";
import { pointer } from "../fixtures/pointer";

interface Flight {
  readonly revision: string;
  readonly phase: string;
  readonly x: number;
  readonly z: number;
  readonly energy: number;
  readonly formation: number;
  readonly tick: number;
}

async function flight(page: Page): Promise<Flight> {
  const snapshot = await page.locator("#game").getAttribute("data-flight");
  if (!snapshot) throw new Error("Missing flight diagnostics");
  return JSON.parse(snapshot) as Flight;
}

async function advance(page: Page, until: (state: Flight) => boolean) {
  for (let i = 0; i < 100; i++) {
    const state = await flight(page);
    if (until(state)) return state;
    if (state.phase === "failed") throw new Error("Practice failed");
    await page.clock.runFor(200);
  }
  throw new Error("Practice did not reach the requested state");
}

test("the wind turn can be flown both ways with one-click restarts", async ({
  page,
  hasTouch,
}, info) => {
  test.skip(hasTouch, "keyboard route comparison");
  test.setTimeout(145_000);
  await page.setViewportSize({ width: 960, height: 600 });
  await page.addInitScript(() =>
    localStorage.setItem(
      "feather-tide-settings-v1",
      JSON.stringify({ low: true, reduced: true, music: false }),
    ),
  );
  await page.clock.install();
  await openTitle(page, "/?diagnostics");
  await page.getByRole("button", { name: "练习飞行" }).click();
  await page.getByRole("button", { name: "顺风转弯试飞" }).click();
  await expect(page.getByRole("button", { name: "结阵" })).toBeVisible();
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 1500);
  const start = await advance(
    page,
    ({ revision }) => revision === "tailwind-practice-2",
  );
  const restart = page.getByRole("button", { name: "从起点重飞" });
  const notice = page.locator("#notice");

  await page.keyboard.down("KeyW");
  await page.keyboard.down("Space");
  await advance(page, ({ z }) => z >= 135);
  await expect(notice).toHaveText("选航线 · 借顺风或飞宽水面");
  await expect(
    page.getByText("宽水面 · 绕芦苇浅滩", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("第二道顺风带", { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("wind-choice.png") });
  await page.keyboard.up("Space");
  await page.keyboard.down("KeyD");
  await advance(page, ({ x }) => x <= -26);
  await page.keyboard.up("KeyD");
  await page.keyboard.down("Space");
  await advance(page, ({ z }) => z >= 170);
  await expect(notice).toHaveText("宽水面 · 逆风减慢推进");
  const wide = await advance(page, ({ phase }) => phase === "landing");
  await expect(page.locator("#arrived")).toHaveText("12/12");
  await page.keyboard.up("KeyW");
  await page.keyboard.up("Space");
  await page.getByRole("button", { name: "跳过落脚演出" }).click();
  await expect(
    page.getByRole("heading", { name: "全队完成试飞" }),
  ).toBeVisible();
  await restart.click();
  await page.clock.runFor(120);
  expect(await flight(page)).toMatchObject({
    x: start.x,
    z: start.z,
    energy: 1,
    formation: 0,
    phase: "playing",
  });

  await page.keyboard.down("KeyW");
  await page.keyboard.down("Space");
  await advance(page, ({ z }) => z >= 135);
  await page.keyboard.up("Space");
  await advance(page, ({ z }) => z >= 146);
  // The default camera faces +Z, so world +X is on the screen's left.
  await page.keyboard.down("KeyA");
  await advance(page, ({ x }) => x >= 14);
  await page.keyboard.up("KeyA");
  await page.keyboard.down("Space");
  await advance(page, ({ z }) => z >= 179);
  await expect(notice).toHaveText("借到第二道顺风");
  await page.screenshot({ path: info.outputPath("second-tailwind.png") });
  const cut = await advance(page, ({ phase }) => phase === "landing");
  await expect(page.locator("#arrived")).toHaveText("12/12");
  expect(cut.tick).toBeLessThan(wide.tick);
  expect(cut.energy).toBeGreaterThan(wide.energy);
  await page.keyboard.up("KeyW");
  await page.keyboard.up("Space");
  await page.getByRole("button", { name: "跳过落脚演出" }).click();
  await restart.click();
  await page.clock.runFor(300);
  await page.keyboard.down("KeyW");
  await page.clock.runFor(700);
  await page.keyboard.press("Escape");
  await restart.click();
  await page.clock.runFor(300);
  expect(await flight(page)).toMatchObject({
    x: start.x,
    z: start.z,
    energy: 1,
  });
  await page.keyboard.up("KeyW");
});

test("the two wind routes are readable while moving and forming on touch", async ({
  page,
  hasTouch,
}, info) => {
  test.skip(!hasTouch, "requires the landscape touch project");
  test.setTimeout(100_000);
  await page.addInitScript(() =>
    localStorage.setItem(
      "feather-tide-settings-v1",
      JSON.stringify({ low: true, reduced: true, music: false }),
    ),
  );
  await page.clock.install();
  await openTitle(page, "/?diagnostics");
  await page.getByRole("button", { name: "练习飞行" }).click();
  await page.getByRole("button", { name: "顺风转弯试飞" }).click();
  const ability = page.getByRole("button", { name: "结阵" });
  await expect(ability).toBeVisible();
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 1500);
  const box = await ability.boundingBox();
  if (!box) throw new Error("Missing formation button bounds");
  const abilityX = box.x + box.width / 2;
  const abilityY = box.y + box.height / 2;

  await pointer(page, "pointerdown", 51, 125, 260);
  await pointer(page, "pointermove", 51, 125, 219);
  await pointer(page, "pointerdown", 52, abilityX, abilityY, "#formation");
  await advance(page, ({ z }) => z >= 135);
  await expect(ability).toHaveAttribute("data-state", "formed");
  await expect(
    page.getByText("宽水面 · 绕芦苇浅滩", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("第二道顺风带", { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("touch-wind-choice.png") });
  await pointer(page, "pointerup", 52, abilityX, abilityY);
  await pointer(page, "pointermove", 51, 96, 232);
  await advance(page, ({ x, formation }) => x > -6 && formation === 0);
  await pointer(page, "pointerup", 51, 96, 232);
  await page.getByRole("button", { name: "暂停" }).click();
  await page.getByRole("button", { name: "从起点重飞" }).click();
  await page.clock.runFor(250);
  expect(await flight(page)).toMatchObject({ z: 99, formation: 0, energy: 1 });
});
