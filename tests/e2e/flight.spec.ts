import { writeFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { angleDelta } from "../../src/core/math";
import type { Basis } from "../../src/input/input";
import { GOOSE } from "../../src/simulation/goose";
import { trip } from "../fixtures/flight";
import { mouseOrbit, pointer } from "../fixtures/pointer";
import { enterSpeciesMenu, openMenu, openTitle } from "../fixtures/menu";

test("U02 the desktop keyboard-only journey can start, move, pause and resume", async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, "exercises the desktop keyboard controls");
  await openMenu(page, "/?diagnostics");
  const journey = page.getByRole("button", { name: /^斑头雁/ });
  const game = page.locator("#game");
  await expect(journey).toBeVisible();
  await expect(journey).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(game).toBeFocused();
  await page.keyboard.down("KeyW");
  await page.waitForFunction(() => {
    const state = JSON.parse(
      document.getElementById("game")?.dataset.flight ?? "{}",
    );
    return state.z > 0.1;
  });
  await page.keyboard.press("Escape");
  await page.keyboard.up("KeyW");
  const resume = page.getByRole("button", { name: "继续飞行" });
  await expect(resume).toBeFocused();
  expect(
    await resume.evaluate((button) => button.matches(":focus-visible")),
  ).toBe(true);
  await expect(game).toHaveAttribute("data-flight", /"phase":"paused"/);
  await page.keyboard.press("Enter");
  await expect(game).toBeFocused();
  await expect(game).toHaveAttribute("data-flight", /"phase":"playing"/);
});

async function desktopFlight(
  page: Page,
): Promise<{ speed: number; z: number; basis: Basis }> {
  const value = await page.locator("#game").getAttribute("data-flight");
  if (!value) throw new Error("Missing flight diagnostics");
  return JSON.parse(value);
}

test("S0 V2-08 flight teaches glide before orbit and recenter", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 852, height: 393 });
  await openMenu(page, "/?diagnostics");
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  const notice = page.locator("#notice");
  const energyCondition = page.locator("#energy-condition");
  await expect(notice).toContainText("起飞");
  await pointer(page, "pointerdown", 51, 120, 250);
  await pointer(page, "pointermove", 51, 120, 205);
  await expect(notice).toContainText("滑翔");
  await expect(energyCondition).toBeEmpty();
  await pointer(page, "pointermove", 51, 120, 180);
  await expect(energyCondition).toHaveText("加速中");
  await page.screenshot({ path: info.outputPath("touch-boost.png") });
  await pointer(page, "pointerup", 51, 120, 180);
  await expect(energyCondition).toBeEmpty();
  await expect(notice).toContainText("查看队尾");
  await pointer(page, "pointerdown", 52, 648, 190);
  await pointer(page, "pointermove", 52, 500, 190);
  await pointer(page, "pointerup", 52, 500, 190);
  await expect(notice).toContainText(/复位镜头|回到跟随视角/);
  await page.getByRole("button", { name: "镜头复位" }).click();
  await expect(notice).toBeEmpty();
  await expect(page.locator("#energy-status")).toBeVisible();
});

test("S0 skipped flight lessons remain available in the pause menu", async ({
  page,
  isMobile,
}) => {
  await page.setViewportSize({ width: 568, height: 320 });
  await page.addInitScript(() =>
    localStorage.setItem(
      "feather-tide-settings-v1",
      JSON.stringify({ mirror: true, toggle: true }),
    ),
  );
  await openMenu(page, "/?diagnostics");
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await page.getByRole("button", { name: "跳过飞行教学" }).click();
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  await page.getByRole("button", { name: "飞行操作" }).click();
  const help = page.getByRole("dialog");
  await expect(help.getByRole("heading", { name: "飞行操作" })).toBeVisible();
  await expect(help.locator("#panel-text")).toContainText(
    isMobile ? "在右侧按住并拖动" : "WASD 或方向键",
  );
  await expect(help.locator("#panel-text")).toContainText("加速更费体力");
  await expect(help.locator("#panel-text")).toContainText("再按一次解阵");
  await expect(page.locator("#game")).toHaveAttribute(
    "data-flight",
    /"phase":"paused"/,
  );
  await help.getByRole("button", { name: "返回暂停菜单" }).click();
  await help.getByRole("button", { name: "继续飞行" }).click();
  await expect(help).toBeHidden();
  await expect(page.locator("#notice")).toBeEmpty();
});

test("V2-08 the touch HUD lets the side hint fade while keeping the active lesson", async ({
  page,
  hasTouch,
}, info) => {
  test.skip(!hasTouch, "exercises the first-flight touch affordance");
  await page.setViewportSize({ width: 852, height: 393 });
  await page.clock.install();
  await openMenu(page, "/?diagnostics");
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  const hint = page.locator("#gesture-hint");
  const notice = page.locator("#notice");
  await expect(hint).toBeVisible();
  const passesThrough = await hint.evaluate((node) => {
    const { x, y, width, height } = node.getBoundingClientRect();
    return document
      .elementFromPoint(x + width / 2, y + height / 2)
      ?.matches("canvas");
  });
  expect(passesThrough).toBe(true);
  await page.clock.runFor(6_000);
  await expect(hint).toBeHidden();
  await expect(page.locator("#segment")).toBeHidden();
  await expect(notice).toContainText("起飞");

  await page.getByRole("button", { name: "跳过飞行教学" }).tap();
  await expect(page.locator("#flight-cue")).toBeHidden();
  await expect(page.getByRole("progressbar", { name: "体力" })).toBeVisible();
  await expect(page.locator("#stick")).toBeHidden();
  await page.screenshot({
    path: info.outputPath("quiet-flight.png"),
    scale: "css",
  });
});

for (const viewport of [
  { width: 480, height: 270 },
  { width: 568, height: 320 },
  { width: 852, height: 393 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
]) {
  test(`U03 stamina and readable guidance fit ${viewport.width}x${viewport.height} with mirrored large controls`, async ({
    page,
  }, info) => {
    await page.setViewportSize(viewport);
    await openMenu(page, "/?diagnostics");
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page.getByLabel("镜像操作").check();
    await page.getByLabel("放大按钮").check();
    await page.getByRole("button", { name: "返回", exact: true }).click();
    await page.getByRole("button", { name: /^斑头雁/ }).click();
    const stamina = page.getByRole("progressbar", {
      name: "体力",
      exact: true,
    });
    await expect(stamina).toBeVisible();
    await expect(page.locator("#energy-percent")).toHaveText("100%");
    await expect(page.locator("#energy-status")).toHaveAttribute(
      "data-level",
      "normal",
    );
    const cue = page.locator("#flight-cue");
    await expect(cue).toBeInViewport({ ratio: 1 });
    await expect(page.locator("#detail")).not.toBeEmpty();
    const textMetrics = await page.locator("#notice").evaluate((node) => ({
      size: parseFloat(getComputedStyle(node).fontSize),
      width: node.clientWidth,
      scrollWidth: node.scrollWidth,
    }));
    expect(textMetrics.size).toBeGreaterThanOrEqual(18);
    expect(textMetrics.scrollWidth).toBeLessThanOrEqual(textMetrics.width);
    expect(
      await page
        .locator("#detail")
        .evaluate((node) => parseFloat(getComputedStyle(node).fontSize)),
    ).toBeGreaterThanOrEqual(15);
    for (const control of [
      "#pause-flight",
      "#camera-reset",
      "#energy-status",
      "#formation",
    ]) {
      const controlBox = await page.locator(control).boundingBox();
      const cueBox = await cue.boundingBox();
      expect(controlBox && cueBox).toBeTruthy();
      if (!controlBox || !cueBox) throw new Error("Missing HUD geometry");
      expect(
        controlBox.x + controlBox.width <= cueBox.x ||
          cueBox.x + cueBox.width <= controlBox.x ||
          controlBox.y + controlBox.height <= cueBox.y ||
          cueBox.y + cueBox.height <= controlBox.y,
      ).toBe(true);
    }
    const pauseBox = await page.locator("#pause-flight").boundingBox();
    const resetBox = await page.locator("#camera-reset").boundingBox();
    const abilityBox = await page.locator("#formation").boundingBox();
    expect(pauseBox?.x).toBeGreaterThan(viewport.width / 2);
    expect(resetBox?.x).toBeLessThan(viewport.width / 2);
    expect(abilityBox?.x).toBeLessThan(viewport.width / 2);
    expect(resetBox?.width).toBeGreaterThanOrEqual(52);
    await page.screenshot({ path: info.outputPath("stamina-guidance.png") });
    await page.getByRole("button", { name: "跳过飞行教学" }).click();
    await expect(page.locator("#notice")).toBeEmpty();
    await expect(stamina).toBeVisible();
    await expect(stamina).toHaveJSProperty("value", 1);
    await pointer(page, "pointerdown", 81, viewport.width - 120, 240);
    await pointer(page, "pointermove", 81, viewport.width - 120, 190);
    await expect
      .poll(async () => {
        const state = await page.locator("#game").getAttribute("data-flight");
        return state ? (JSON.parse(state) as { z: number }).z : 0;
      })
      .toBeGreaterThan(1);
    await pointer(page, "pointerup", 81, viewport.width - 120, 190);
    const measured = await page.evaluate(() => {
      const bar = document.getElementById("energy");
      const state = JSON.parse(
        document.getElementById("game")?.dataset.flight ?? "{}",
      ) as { energy: number };
      if (!(bar instanceof HTMLProgressElement))
        throw new Error("Missing stamina");
      return {
        value: bar.value,
        expected: state.energy,
        percent: document.getElementById("energy-percent")?.textContent,
      };
    });
    expect(measured.value).toBeCloseTo(measured.expected, 5);
    expect(measured.percent).toBe(`${Math.round(measured.expected * 100)}%`);
  });
}

test("U02 formation feedback follows the simulated formation and release", async ({
  page,
}, info) => {
  await openTitle(page);
  await page.getByRole("button", { name: "练习飞行" }).click();
  await page.getByRole("button", { name: "飞行实验场" }).click();
  const ability = page.getByRole("button", { name: "结阵" });
  await expect(ability).toHaveAttribute("data-state", "idle");
  await expect(page.locator("#energy-status")).toBeVisible();
  await expect(page.locator("#arrival-status")).toBeHidden();
  await page.keyboard.down("KeyW");
  await page.keyboard.down("Space");
  await expect(ability).toHaveAttribute("data-state", "forming");
  await expect(ability).toHaveAttribute("data-state", "formed");
  await expect(ability.locator("#formation-label")).toHaveText("已成阵");
  await page.screenshot({ path: info.outputPath("formed.png"), scale: "css" });
  await page.keyboard.up("Space");
  await expect(ability).toHaveAttribute("data-state", "releasing");
  await expect(ability).toHaveAttribute("data-state", "idle");
  await page.keyboard.up("KeyW");
});

test("U02 short landscape settings keep the return action above the scrolling groups", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 568, height: 320 });
  await openMenu(page);
  await page.getByRole("button", { name: "设置" }).click();
  const settings = page.getByRole("dialog", { name: "设置" });
  const back = settings.getByRole("button", { name: "返回", exact: true });
  await expect(back).toBeInViewport({ ratio: 1 });
  const comfort = settings.getByRole("button", { name: "舒适性" });
  await comfort.press("Enter");
  await expect(settings.getByLabel("减少动态")).toBeInViewport({ ratio: 1 });
  await settings.getByRole("button", { name: "镜头", exact: true }).click();
  const sensitivity = settings.getByRole("slider", { name: "灵敏度" });
  await sensitivity.press("ArrowRight");
  await expect(settings.locator("#sensitivity-value")).toHaveText("1.1×");
  expect((await sensitivity.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  expect(
    (await settings.getByLabel("移动方向").boundingBox())?.height,
  ).toBeGreaterThanOrEqual(44);
  await settings.getByRole("button", { name: "操作", exact: true }).click();
  await page.screenshot({
    path: info.outputPath("short-settings.png"),
    scale: "css",
  });
  await settings.getByText("键鼠操作", { exact: true }).click();
  const defaults = settings.getByRole("button", { name: "恢复默认键位" });
  await defaults.scrollIntoViewIfNeeded();
  await expect(defaults).toBeInViewport({ ratio: 1 });
  await expect(back).toBeInViewport({ ratio: 1 });
  await back.click();
  await expect(settings).toBeHidden();
});

test("V2-18 mirrored floating stick stays in the safe viewport at a real canvas edge", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 568, height: 320 });
  await page.addInitScript(() =>
    localStorage.setItem(
      "feather-tide-settings-v1",
      JSON.stringify({ mirror: true, large: true }),
    ),
  );
  await openMenu(page, "/?diagnostics");
  await page.locator("#goose-entry").click();
  expect(
    await page.evaluate(() => document.elementFromPoint(557, 279)?.tagName),
  ).toBe("CANVAS");
  await pointer(page, "pointerdown", 41, 557, 279);
  await pointer(page, "pointermove", 41, 557, 235);
  await expect(page.locator("#stick")).toBeInViewport({ ratio: 1 });
  await expect(page.locator("#stick i")).toBeInViewport({ ratio: 1 });
  await expect
    .poll(async () => (await desktopFlight(page)).z)
    .toBeGreaterThan(0.1);
  await page.screenshot({
    path: info.outputPath("mirrored-edge.png"),
    scale: "css",
  });
  await pointer(page, "pointerup", 41, 557, 235);
  await expect(page.locator("#stick")).toBeHidden();
});

test("desktop speed tiers, right drag and recenter work together and release on pause", async ({
  page,
  isMobile,
}, info) => {
  test.skip(isMobile, "uses the desktop mouse and keyboard");
  await page.setViewportSize({ width: 900, height: 500 });
  await openTitle(page, "/?diagnostics");
  await page.getByRole("button", { name: "练习飞行" }).click();
  await page.getByRole("button", { name: "飞行实验场" }).click();
  const formation = page.getByRole("button", { name: "结阵" });
  const camera = page.locator("#marker-layer");
  const energyCondition = page.locator("#energy-condition");
  await expect(formation).toBeVisible();
  await page.keyboard.down("ShiftRight");
  expect((await desktopFlight(page)).speed).toBe(0);
  await expect(energyCondition).toBeEmpty();
  await page.keyboard.up("ShiftRight");
  await page.keyboard.down("KeyW");
  await expect
    .poll(async () => (await desktopFlight(page)).speed)
    .toBeCloseTo(9.48, 1);
  await page.keyboard.down("ShiftRight");
  await expect
    .poll(async () => (await desktopFlight(page)).speed)
    .toBeCloseTo(GOOSE.boost, 1);
  await expect(energyCondition).toHaveText("加速中");
  await page.screenshot({ path: info.outputPath("desktop-boost.png") });
  await page.keyboard.up("ShiftRight");
  await expect(energyCondition).toBeEmpty();
  await expect
    .poll(async () => (await desktopFlight(page)).speed)
    .toBeCloseTo(9.48, 1);
  await page.keyboard.down("ShiftRight");
  await page.keyboard.down("KeyC");
  await expect
    .poll(async () => (await desktopFlight(page)).speed)
    .toBeCloseTo(3.24, 1);
  await page.keyboard.up("ShiftRight");
  await page.keyboard.up("KeyC");
  await page.keyboard.down("AltLeft");
  await expect
    .poll(async () => (await desktopFlight(page)).speed)
    .toBeCloseTo(3.24, 1);
  await page.keyboard.up("AltLeft");

  await page.keyboard.down("Space");
  await page.mouse.move(655, 207);
  await page.mouse.down({ button: "right" });
  await expect(page.locator("canvas")).toHaveCSS("cursor", "grabbing");
  await page.mouse.move(529, 247, { steps: 5 });
  await expect(camera).toHaveAttribute("data-camera", "Explore");
  await expect(formation).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(async () => Math.abs((await desktopFlight(page)).basis.right.z))
    .toBeGreaterThan(0.25);
  const beforeRelease = await desktopFlight(page);
  await page.mouse.up({ button: "right" });
  await expect(page.locator("canvas")).toHaveCSS("cursor", "grab");
  await expect
    .poll(async () => (await desktopFlight(page)).z)
    .toBeGreaterThan(beforeRelease.z);
  await page.keyboard.press("KeyR");
  await expect(camera).toHaveAttribute("data-camera", "Follow");
  await expect
    .poll(async () => Math.abs((await desktopFlight(page)).basis.right.z))
    .toBeLessThan(0.01);
  await expect(formation).toHaveAttribute("aria-pressed", "true");

  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: "飞行暂停" })).toBeVisible();
  await page.keyboard.press("Escape");
  // Keys held across pause must be released before they can act again.
  await page.keyboard.down("Space");
  await page.keyboard.down("KeyW");
  await expect(formation).toHaveAttribute("aria-pressed", "false");
  await expect
    .poll(async () => (await desktopFlight(page)).speed)
    .toBeCloseTo(GOOSE.slow, 1);
  await page.keyboard.up("Space");
  await page.keyboard.up("KeyW");
  await page.keyboard.down("KeyW");
  await expect
    .poll(async () => (await desktopFlight(page)).speed)
    .toBeGreaterThan(5);
  await page.keyboard.up("KeyW");
});

test("desktop key settings reject conflicts, persist remaps and restore defaults", async ({
  page,
  isMobile,
}, testInfo) => {
  test.skip(isMobile, "exercises editable desktop shortcuts");
  await page.setViewportSize({ width: 1000, height: 760 });
  await openTitle(page, "/?diagnostics");
  async function openBindings() {
    await page.getByRole("button", { name: "设置" }).click();
    const section = page.locator(".desktop-settings");
    if (!(await section.evaluate((node) => node.hasAttribute("open")))) {
      await section.locator("summary").click();
    }
  }
  await openBindings();
  await page.getByRole("button", { name: "向前键 · W" }).click();
  await page.keyboard.press("KeyS");
  await expect(page.locator("#key-hint")).toHaveText("S 已用于向后。");
  await page.keyboard.press("KeyI");
  await expect(page.getByRole("button", { name: "向前键 · I" })).toBeVisible();
  await page.getByRole("button", { name: "镜头复位键 · R" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: "设置" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "镜头复位键 · R" }),
  ).toBeVisible();
  await page.reload();
  await openBindings();
  await expect(page.getByRole("button", { name: "向前键 · I" })).toBeVisible();
  const back = page.getByRole("button", { name: "返回", exact: true });
  await expect(back).toBeInViewport({ ratio: 1 });
  await page.screenshot({
    path: testInfo.outputPath("desktop-key-settings.png"),
  });
  await back.click();
  await page.getByRole("button", { name: "练习飞行" }).click();
  await page.getByRole("button", { name: "飞行实验场" }).click();
  await expect(page.locator("#notice")).toContainText("IASD");
  await page.keyboard.press("KeyW");
  expect((await desktopFlight(page)).z).toBe(0);
  await page.keyboard.down("KeyI");
  await expect
    .poll(async () => (await desktopFlight(page)).z)
    .toBeGreaterThan(0.1);
  await page.keyboard.up("KeyI");
  await page.keyboard.press("Escape");
  await openBindings();
  await page.getByRole("button", { name: "恢复默认键位" }).click();
  await expect(page.getByRole("button", { name: "向前键 · W" })).toBeVisible();
});

test("I01 V2-01–04 flight and orbit retain their touch roles across zones", async ({
  page,
  isMobile,
}) => {
  await page.setViewportSize({ width: 852, height: 393 });
  await openTitle(page);
  await page.getByRole("button", { name: "练习飞行" }).click();
  await page.getByRole("button", { name: "飞行实验场" }).click();
  const stick = page.locator("#stick");
  const camera = page.locator("#marker-layer");
  const ability = page.getByRole("button", { name: "结阵" });
  await expect(ability).toBeVisible();
  await expect(page.locator("#notice")).toHaveText(
    isMobile ? "在左侧按住并拖动，带雁群起飞" : "WASD / 方向键起飞",
  );
  await pointer(page, "pointerdown", 31, 140, 295);
  await pointer(page, "pointermove", 31, 140, 246);
  await expect(stick).toBeVisible();
  await expect(page.locator("#notice")).toHaveText("松开摇杆，试试滑翔");
  await pointer(page, "pointerdown", 32, 545, 130);
  await pointer(page, "pointermove", 32, 802, 335, "#formation");
  await expect(camera).toHaveAttribute("data-camera", "Explore");
  await expect(ability).toHaveAttribute("aria-pressed", "false");
  await expect(stick).toBeVisible();
  await pointer(page, "pointerup", 32, 802, 335);
  await page.getByRole("button", { name: "镜头复位" }).click();
  await expect(camera).toHaveAttribute("data-camera", "Follow");
  await pointer(page, "pointermove", 31, 750, 280);
  await expect(stick).toBeVisible();
  await expect(ability).toHaveAttribute("aria-pressed", "false");
  await expect(camera).toHaveAttribute("data-camera", "Follow");
  await pointer(page, "pointerdown", 33, 804, 335, "#formation");
  await expect(ability).toHaveAttribute("aria-pressed", "true");
  await pointer(page, "pointermove", 33, 505, 120);
  await expect(ability).toHaveAttribute("aria-pressed", "true");
  await expect(camera).toHaveAttribute("data-camera", "Follow");
  await pointer(page, "pointercancel", 33, 505, 120);
  await expect(stick).toBeHidden();
  await expect(ability).toHaveAttribute("aria-pressed", "false");
});

interface FlightSample {
  readonly tick: number;
  readonly x: number;
  readonly z: number;
  readonly heading: number;
  readonly basis: Basis;
}

interface OrbitSample extends FlightSample {
  readonly speed: number;
  readonly camera: {
    readonly yaw: number;
    readonly pitch: number;
    readonly requestedPitch: number;
    readonly profile: "wide" | "classic";
    readonly mode: string;
  };
}

async function readOrbit(page: Page): Promise<OrbitSample> {
  const raw = await page.locator("#game").getAttribute("data-flight");
  if (!raw) throw new Error("Missing camera diagnostics");
  return JSON.parse(raw) as OrbitSample;
}

test("desktop full orbit and horizontal touch drag look behind and all the way around", async ({
  page,
  isMobile,
}, testInfo) => {
  await page.setViewportSize({ width: 852, height: 393 });
  await openMenu(page, "/?diagnostics");
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await expect(page.getByRole("button", { name: "结阵" })).toBeVisible();

  const flight = page.locator("#game");
  const camera = page.locator("#marker-layer");
  async function sample(): Promise<FlightSample> {
    const data = await flight.getAttribute("data-flight");
    if (!data) throw new Error("Flight diagnostics are missing");
    return JSON.parse(data) as FlightSample;
  }
  const initial = await sample();
  for (const [index, angle] of [
    Math.PI / 2,
    Math.PI,
    -Math.PI / 2,
    0,
  ].entries()) {
    if (isMobile) {
      const id = 50 + index;
      await pointer(page, "pointerdown", id, 726, 205);
      await pointer(page, "pointermove", id, 464, 205);
      await pointer(page, "pointerup", id, 464, 205);
    } else {
      const button = index % 2 === 0 ? "left" : "right";
      await page.mouse.move(726, 205);
      await page.mouse.down({ button });
      await page.mouse.move(464, 205, { steps: 6 });
      await page.mouse.up({ button });
    }
    await expect
      .poll(async () => {
        const { basis } = await sample();
        return Math.abs(angleDelta(Math.atan2(basis.up.x, basis.up.z), angle));
      })
      .toBeLessThan(0.02);
    const { x, z, heading } = await sample();
    expect({ x, z, heading }).toEqual({
      x: initial.x,
      z: initial.z,
      heading: initial.heading,
    });
    await expect(camera).toHaveAttribute("data-camera", "Explore");
    if (index === 1) {
      await page.screenshot({
        path: testInfo.outputPath("looking-behind.png"),
      });
    }
  }
  await page.getByRole("button", { name: "镜头复位" }).dispatchEvent("click");
  await expect
    .poll(async () => Math.abs((await sample()).basis.right.z))
    .toBeLessThan(0.001);
  await expect(camera).toHaveAttribute("data-camera", "Follow");
});

test("desktop wide orbit uses both mouse buttons, keeps diagonal flight stable, and saves settings", async ({
  page,
  isMobile,
}, info) => {
  test.skip(isMobile, "exercises both desktop mouse buttons");
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openMenu(page, "/?diagnostics");
  await page.getByRole("button", { name: "设置" }).click();
  const wide = page.getByLabel("宽幅鼠标环绕");
  const vertical = page.getByLabel("垂直转镜");
  const close = page.getByRole("button", { name: "返回", exact: true });
  await expect(wide).not.toBeChecked();
  await wide.check();
  await close.click();
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await expect(page.getByRole("button", { name: "结阵" })).toBeVisible();

  let turned = 0;
  let before = (await readOrbit(page)).camera.yaw;
  const degrees = Math.PI / 180;
  for (let i = 0; i < 9; i++) {
    const direction = i % 2 === 0 ? "left" : "right";
    await mouseOrbit(page, -262, 0, direction);
    const expected = before + (262 * 0.006) / degrees;
    await expect
      .poll(async () =>
        Math.abs(
          angleDelta(
            (await readOrbit(page)).camera.yaw * degrees,
            expected * degrees,
          ),
        ),
      )
      .toBeLessThan(0.02);
    const after = (await readOrbit(page)).camera.yaw;
    const travel = angleDelta(before * degrees, after * degrees) / degrees;
    expect(travel).toBeGreaterThan(89);
    turned += travel;
    before = after;
  }
  expect(turned).toBeGreaterThan(720);
  await mouseOrbit(page, 0, -240, "left");
  await expect
    .poll(async () => (await readOrbit(page)).camera.pitch)
    .toBeCloseTo(20, 1);
  await page.screenshot({ path: info.outputPath("wide-20.png") });
  await mouseOrbit(page, 0, 260, "right");
  await expect
    .poll(async () => (await readOrbit(page)).camera.pitch)
    .toBeCloseTo(80, 1);
  await page.screenshot({ path: info.outputPath("wide-80.png") });
  const high = await readOrbit(page);
  await expect
    .poll(async () => (await readOrbit(page)).tick)
    .toBeGreaterThan(high.tick + 8);
  expect((await readOrbit(page)).camera).toEqual(high.camera);

  await page.keyboard.down("KeyW");
  await page.keyboard.down("KeyA");
  const heading = (before + 45) * degrees;
  await expect
    .poll(async () =>
      Math.abs(angleDelta((await readOrbit(page)).heading, heading)),
    )
    .toBeLessThan(0.012);
  await expect
    .poll(async () => (await readOrbit(page)).speed)
    .toBeCloseTo(9.48, 2);
  const highSpeed = (await readOrbit(page)).speed;
  await mouseOrbit(page, 0, -90, "right");
  await expect
    .poll(async () => (await readOrbit(page)).camera.pitch)
    .toBeCloseTo(49, 0);
  const middle = await readOrbit(page);
  expect(Math.abs(angleDelta(middle.heading, heading))).toBeLessThan(0.012);
  expect(middle.speed).toBeCloseTo(highSpeed, 2);
  await mouseOrbit(page, 0, -260, "right");
  await expect
    .poll(async () => (await readOrbit(page)).camera.pitch)
    .toBeCloseTo(20, 1);
  const low = await readOrbit(page);
  expect(Math.abs(angleDelta(low.heading, heading))).toBeLessThan(0.012);
  expect(low.speed).toBeCloseTo(highSpeed, 2);
  await page.keyboard.up("KeyA");
  await page.keyboard.up("KeyW");

  await page.keyboard.press("KeyR");
  await expect
    .poll(async () => (await readOrbit(page)).camera)
    .toMatchObject({
      yaw: 0,
      pitch: 49,
      profile: "classic",
      mode: "Follow",
    });
  await mouseOrbit(page, -100, 240, "right");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "设置" }).click();
  await wide.uncheck();
  await close.click();
  await page.getByRole("button", { name: "继续飞行" }).click();
  await expect.poll(async () => (await readOrbit(page)).camera.pitch).toBe(49);
  await mouseOrbit(page, -80, 240);
  await expect
    .poll(async () => (await readOrbit(page)).camera.pitch)
    .toBeCloseTo(65, 1);
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "设置" }).click();
  await wide.check();
  await vertical.uncheck();
  await close.click();
  await page.getByRole("button", { name: "继续飞行" }).click();
  await mouseOrbit(page, 0, -240);
  expect((await readOrbit(page)).camera).toMatchObject({
    yaw: 0,
    pitch: 49,
    mode: "Follow",
  });
  await page.reload();
  await page.getByRole("button", { name: "设置" }).click();
  await expect(wide).toBeChecked();
  await expect(vertical).not.toBeChecked();
});

test("wide mouse preference keeps touch orbit in the classic range", async ({
  page,
}) => {
  await page.setViewportSize({ width: 852, height: 393 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openMenu(page, "/?diagnostics");
  await page.getByRole("button", { name: "设置" }).click();
  await page.getByLabel("宽幅鼠标环绕").check();
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await expect(page.getByRole("button", { name: "结阵" })).toBeVisible();
  for (const [id, dy, pitch] of [
    [81, -180, 35],
    [82, 180, 65],
  ] as const) {
    await pointer(page, "pointerdown", id, 590, 197);
    await pointer(page, "pointermove", id, 590, 197 + dy);
    await pointer(page, "pointerup", id, 590, 197 + dy);
    await expect
      .poll(async () => (await readOrbit(page)).camera.profile)
      .toBe("classic");
    await expect
      .poll(async () => (await readOrbit(page)).camera.pitch)
      .toBeCloseTo(pitch, 2);
  }
});

test("S01 V2-05–06 paired A/B orbit, release, regrip and reset on the safe course", async ({
  page,
  isMobile,
}, testInfo) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 852, height: 393 });
  await page.clock.install();
  const flight = page.locator("#game");
  async function sample(afterMs: number): Promise<FlightSample> {
    await page.clock.runFor(afterMs);
    const data = await flight.getAttribute("data-flight");
    if (!data) throw new Error("Flight diagnostics are missing");
    return JSON.parse(data) as FlightSample;
  }

  async function trial(mapping: "A" | "B") {
    await openTitle(page, "/?diagnostics");
    await page.getByRole("button", { name: "设置" }).click();
    await page.getByLabel("移动方向").selectOption(mapping);
    await page.getByRole("button", { name: "返回", exact: true }).click();
    await page.getByRole("button", { name: "练习飞行" }).click();
    await page.getByRole("button", { name: "飞行实验场" }).click();
    await expect(flight).toHaveAttribute(
      "data-flight",
      /"revision":"flight-1"/,
    );
    await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 1000);

    await pointer(page, "pointerdown", 31, 140, 295);
    await pointer(page, "pointermove", 31, 140, 249);
    const straight = await sample(320);
    await pointer(page, "pointerdown", 32, 650, 180);
    await pointer(page, "pointermove", 32, 500, 180);
    await pointer(page, "pointerup", 32, 500, 180);
    const turning = await sample(96);
    const orbit = await sample(896);
    const screenshot = testInfo.outputPath(`mapping-${mapping}-orbit.png`);
    await page.screenshot({ path: screenshot });
    await testInfo.attach(`mapping-${mapping}-orbit`, {
      path: screenshot,
      contentType: "image/png",
    });

    await pointer(page, "pointerup", 31, 140, 249);
    const released = await sample(224);
    await pointer(page, "pointerdown", 33, 140, 295);
    await pointer(page, "pointermove", 33, 140, 249);
    const regripped = await sample(896);
    await page.getByRole("button", { name: "镜头复位" }).dispatchEvent("click");
    const reset = await sample(896);
    await pointer(page, "pointerup", 33, 140, 249);
    await page.clock.resume();
    return { straight, turning, orbit, released, regripped, reset };
  }

  const [first, second] = isMobile
    ? (["B", "A"] as const)
    : (["A", "B"] as const);
  const firstTrial = await trial(first);
  const secondTrial = await trial(second);
  const trials =
    first === "A"
      ? { A: firstTrial, B: secondTrial }
      : { A: secondTrial, B: firstTrial };
  const samples = testInfo.outputPath("paired-flight-samples.json");
  await writeFile(
    samples,
    JSON.stringify({ order: [first, second], trials }, null, 2) + "\n",
  );
  await testInfo.attach("paired-flight-samples", {
    path: samples,
    contentType: "application/json",
  });
  const a = trials.A;
  const b = trials.B;
  expect(a.straight.x).toBeCloseTo(0, 6);
  expect(b.straight.x).toBeCloseTo(0, 6);
  expect(a.straight.z).toBeCloseTo(b.straight.z, 0);
  expect(a.turning.heading).toBeGreaterThan(0.05);
  expect(angleDelta(a.straight.heading, a.turning.heading)).toBeLessThanOrEqual(
    ((a.turning.tick - a.straight.tick) * GOOSE.turnRate) / 60 + 1e-8,
  );
  const orbitHeading = Math.atan2(a.orbit.basis.up.x, a.orbit.basis.up.z);
  expect(orbitHeading).toBeCloseTo(0.9, 2);
  expect(a.orbit.heading).toBeCloseTo(orbitHeading, 2);
  expect(a.orbit.x - b.orbit.x).toBeGreaterThan(3);
  expect(b.orbit.heading).toBeCloseTo(0, 6);
  expect(b.orbit.x).toBeCloseTo(0, 6);
  expect(a.released.heading).toBeCloseTo(a.orbit.heading, 6);
  expect(b.released.heading).toBeCloseTo(b.orbit.heading, 6);
  expect(b.regripped.heading).toBeCloseTo(orbitHeading, 2);
  expect(a.reset.basis.right.z).toBeCloseTo(0, 3);
  expect(b.reset.basis.right.z).toBeCloseTo(0, 3);
  expect(a.reset.heading).toBeCloseTo(0, 3);
  expect(b.reset.heading).toBeCloseTo(b.regripped.heading, 6);
});

test("T18, V2-17–18 mirror, enlarge, mute, and release keys and touches on interruption", async ({
  page,
}) => {
  await page.setViewportSize({ width: 740, height: 350 });
  await openMenu(page);
  await page.getByRole("button", { name: "设置" }).click();
  await page.getByLabel("镜像操作").check();
  await page.getByLabel("放大按钮").check();
  await page.getByLabel("点按切换结阵").check();
  await page.getByLabel("配乐", { exact: true }).uncheck();
  await page.getByLabel("移动方向").selectOption("B");
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  const ability = page.getByRole("button", { name: "结阵" });
  await expect(ability).toBeVisible();
  expect((await ability.boundingBox())?.width).toBeGreaterThan(85);
  expect((await ability.boundingBox())?.x).toBeLessThan(50);
  await pointer(page, "pointerdown", 41, 605, 260);
  await expect(page.locator("#stick")).toBeVisible();
  await expect(page.locator("#notice")).toHaveText(
    "在右侧按住并拖动，带雁群起飞",
  );
  await pointer(page, "pointerdown", 42, 60, 290, "#formation");
  await pointer(page, "pointerup", 42, 60, 290, "#formation");
  await expect(ability).toHaveAttribute("aria-pressed", "true");
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await expect(page.getByRole("dialog").getByRole("heading")).toHaveText(
    "飞行暂停",
  );
  await expect(page.locator("#stick")).toBeHidden();
  await expect(ability).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("button", { name: "继续飞行" }).click();
  await expect(ability).toHaveAttribute("aria-pressed", "false");
  await page.keyboard.down("KeyW");
  await expect(page.locator("#notice")).toHaveText("松开移动键，试试滑翔");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "继续飞行" })).toBeVisible();
  await page.keyboard.up("KeyW");
  await page.reload();
  await page.getByRole("button", { name: "设置" }).click();
  await expect(page.getByLabel("镜像操作")).toBeChecked();
  await expect(page.getByLabel("配乐", { exact: true })).not.toBeChecked();
});

test("E03 loading errors surface in the menu with a usable retry", async ({
  page,
}) => {
  await page.route("**/levels/migration.json", (route) =>
    route.fulfill({ status: 200, json: { schemaVersion: 99 } }),
  );
  await openTitle(page);
  await expect(page.getByRole("status")).toContainText("schemaVersion");
  await page.unroute("**/levels/migration.json");
  await page.getByRole("button", { name: "重新加载" }).click();
  await enterSpeciesMenu(page);
  await expect(page.getByRole("button", { name: /^斑头雁/ })).toBeVisible();
});

test("S07 continue a valid checkpoint after refresh and recover from bad data", async ({
  page,
}) => {
  const snapshot = trip("journey", "mountain").runtime.checkpoint;
  await openMenu(page);
  await expect(page.getByRole("button", { name: /^斑头雁/ })).toBeVisible();
  async function seed(value: unknown): Promise<void> {
    await page.evaluate(
      (record) =>
        new Promise<void>((resolve, reject) => {
          const request = indexedDB.open("feather-tide", 1);
          request.onupgradeneeded = () =>
            request.result.createObjectStore("checkpoint");
          request.onerror = () => reject(request.error);
          request.onsuccess = () => {
            const db = request.result;
            const tx = db.transaction("checkpoint", "readwrite");
            tx.objectStore("checkpoint").put(record, "journey");
            tx.oncomplete = () => {
              db.close();
              resolve();
            };
            tx.onerror = () => reject(tx.error);
          };
        }),
      value,
    );
  }
  await seed(snapshot);
  await page.reload();
  await enterSpeciesMenu(page);
  const continueJourney = page.getByRole("button", {
    name: "从芦苇洲继续旅程",
  });
  await expect(continueJourney).toBeVisible();
  const restart = page.getByRole("button", { name: "斑头雁 重新起飞" });
  await expect(restart).toBeVisible();
  await restart.click();
  await expect(page.getByRole("dialog", { name: "回到芦苇洲" })).toBeVisible();
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "从芦苇洲继续漫游" }),
  ).toBeHidden();
  await continueJourney.click();
  await expect(page.locator("#segment")).toHaveText("顺风洲");
  await seed({ version: 0 });
  await page.reload();
  await enterSpeciesMenu(page);
  await page.getByRole("button", { name: "斑头雁 检查旅程存档" }).click();
  await expect(continueJourney).toBeHidden();
  const invalid = page.getByRole("dialog", { name: "雁旅程存档无法继续" });
  await expect(invalid).toContainText("存档已损坏或使用其他关卡版本");
  await expect(page.locator("#hud")).toBeHidden();
  await invalid.getByRole("button", { name: "开始新航程" }).click();
  await expect(page.locator("#segment")).toHaveText("晨雾湿地");
});

test("I01 native Chromium touch capture keeps independent move and camera touches", async ({
  page,
  browserName,
}) => {
  test.skip(
    browserName !== "chromium",
    "CDP touch dispatch is Chromium-specific",
  );
  await page.setViewportSize({ width: 852, height: 393 });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setTouchEmulationEnabled", {
    enabled: true,
    maxTouchPoints: 5,
  });
  await openTitle(page, "/?diagnostics");
  await page.getByRole("button", { name: "练习飞行" }).click();
  await page.getByRole("button", { name: "飞行实验场" }).click();
  await page.getByRole("button", { name: "结阵" }).waitFor();
  const a = { id: 1, x: 120, y: 260 };
  const b = { id: 2, x: 650, y: 185 };
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [a],
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [a, b],
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchMove",
    touchPoints: [
      { ...a, y: 220 },
      { ...b, x: 580 },
    ],
  });
  await expect(page.locator("#marker-layer")).toHaveAttribute(
    "data-camera",
    "Explore",
  );
  await expect(page.locator("#stick")).toBeVisible();
  await page.waitForFunction(() => {
    const state = JSON.parse(
      document.getElementById("game")?.dataset.flight ?? "{}",
    );
    return Math.hypot(state.x, state.z) > 0.1;
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchCancel",
    touchPoints: [],
  });
  await expect(page.locator("#stick")).toBeHidden();
  await expect(page.getByRole("button", { name: "结阵" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("R05 a failed goose asset request can be retried", async ({ page }) => {
  await page.route("**/assets/goose/cruise-*.glb", (route) =>
    route.fulfill({ status: 503 }),
  );
  await openTitle(page);
  await expect(page.getByRole("status")).toContainText("无法打开游戏");
  await page.unroute("**/assets/goose/cruise-*.glb");
  await page.getByRole("button", { name: "重新加载" }).click();
  await enterSpeciesMenu(page);
  await expect(page.getByRole("button", { name: /^斑头雁/ })).toBeVisible();
});
