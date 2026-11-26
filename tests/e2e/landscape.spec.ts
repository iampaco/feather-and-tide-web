import { writeFile } from "node:fs/promises";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { angleDelta } from "../../src/core/math";
import { migration } from "../fixtures/flight";
import { mouseOrbit, pointer } from "../fixtures/pointer";
import { openMenu } from "../fixtures/menu";

test.describe.configure({ timeout: 60_000 });

const browserErrors = new WeakMap<Page, string[]>();

test.beforeEach(({ page }) => {
  const errors: string[] = [];
  browserErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (entry) => {
    if (/Shader Error|Couldn't load texture/.test(entry.text()))
      errors.push(entry.text());
  });
});

test.afterEach(({ page }) => {
  expect(browserErrors.get(page)).toEqual([]);
});

interface View {
  x: number;
  z: number;
  basis: { up: { x: number; z: number } };
  camera: { yaw: number; pitch: number; requestedPitch: number };
  scenery: Record<string, string>;
}

async function readView(page: Page): Promise<View> {
  const data = await page.locator("#game").getAttribute("data-flight");
  if (!data) throw new Error("Flight diagnostics are missing");
  return JSON.parse(data) as View;
}

async function parkAt(
  page: Page,
  x: number,
  z: number,
  spawnSegment: string,
  low: boolean,
  mapping: "A" | "B" = "A",
  wideMouseOrbit = false,
  terrainCoverage = false,
): Promise<void> {
  await page.addInitScript(
    ({ low, mapping, wideMouseOrbit }) => {
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({
          low,
          mapping,
          wideMouseOrbit,
          reduced: low || wideMouseOrbit,
          music: false,
        }),
      );
    },
    { low, mapping, wideMouseOrbit },
  );
  // Change only the initial pose. The built game's textures, zones and all other geometry load normally.
  await page.route("**/levels/migration.json", (route) =>
    route.fulfill({
      json: { ...migration, spawn: { x, z }, spawnSegment },
    }),
  );
  await openMenu(
    page,
    terrainCoverage ? "/?diagnostics=terrain" : "/?diagnostics",
  );
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await expect(page.getByRole("button", { name: "结阵" })).toBeVisible();
  if (spawnSegment === "S0")
    await page.getByRole("button", { name: "跳过飞行教学" }).click();
  await expect.poll(async () => (await readView(page)).z).toBe(z);
}

async function orbit(
  page: Page,
  id: number,
  dx: number,
  dy: number,
  yaw: number,
  pitch: number,
  advanceMs = 0,
): Promise<void> {
  const bounds = await page.locator("#game").boundingBox();
  if (!bounds) throw new Error("Game surface is missing");
  const x = bounds.x + bounds.width * 0.78;
  const y = bounds.y + bounds.height * 0.52;
  await pointer(page, "pointerdown", id, x, y);
  await pointer(page, "pointermove", id, x + dx, y + dy);
  await pointer(page, "pointerup", id, x + dx, y + dy);
  if (advanceMs) await page.clock.runFor(advanceMs);
  await expect
    .poll(async () => {
      const { basis } = await readView(page);
      const heading = Math.atan2(basis.up.x, basis.up.z);
      const elevation = Math.asin(1 / Math.hypot(basis.up.x, basis.up.z));
      return Math.max(
        Math.abs(angleDelta(heading, yaw)),
        Math.abs(elevation - (pitch * Math.PI) / 180),
      );
    })
    .toBeLessThan(0.02);
}

async function capture(
  page: Page,
  info: TestInfo,
  name: string,
): Promise<Buffer> {
  const screenshot = await page.screenshot({
    path: info.outputPath(name + ".png"),
    scale: "css",
  });
  await writeFile(
    info.outputPath(name + ".json"),
    JSON.stringify(
      {
        flight: await readView(page),
        camera: await page.locator("#marker-layer").getAttribute("data-camera"),
        notice: await page.locator("#notice").textContent(),
        viewport: page.viewportSize(),
        performance: await page
          .locator("#game")
          .getAttribute("data-performance"),
      },
      null,
      2,
    ) + "\n",
  );
  return screenshot;
}

async function countExposedBackground(
  page: Page,
  image: Buffer,
): Promise<number> {
  return page.evaluate(async (data) => {
    const capture = new Image();
    capture.src = "data:image/png;base64," + data;
    await capture.decode();
    const probe = document.createElement("canvas");
    probe.width = capture.width;
    probe.height = capture.height;
    const context = probe.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("Unable to sample game screenshot");
    context.drawImage(capture, 0, 0);
    const { data: pixels } = context.getImageData(
      0,
      0,
      probe.width,
      probe.height,
    );
    let count = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i] === 255 && pixels[i + 1] === 0 && pixels[i + 2] === 255)
        count++;
    }
    return count;
  }, image.toString("base64"));
}

test("S0 the nearer waterway label guides takeoff before the fog-line label", async ({
  page,
}, info) => {
  await page.clock.install();
  await parkAt(page, 0, 30, "S0", false);
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 1000);
  async function advancePast(target: number): Promise<void> {
    for (let elapsed = 0; elapsed < 4000; elapsed += 100) {
      if ((await readView(page)).z > target) return;
      await page.clock.runFor(100);
    }
    expect((await readView(page)).z).toBeGreaterThan(target);
  }

  const markers = page.locator("#marker-layer");
  const waterway = markers.getByText("沿水道飞行", { exact: true });
  const turn = markers.getByText("绕过芦苇岛", { exact: true });
  const fog = markers.getByText("雾线", { exact: true });
  await expect(waterway).toBeVisible();
  await expect(turn).toBeHidden();
  await expect(fog).toBeHidden();
  await capture(page, info, "waterway-first");

  await pointer(page, "pointerdown", 49, 105, 247);
  await pointer(page, "pointermove", 49, 105, 193);
  await advancePast(55);
  await expect(turn).toBeVisible();
  await expect(fog).toBeHidden();
  await capture(page, info, "reed-turn");
  await advancePast(71);
  await pointer(page, "pointerup", 49, 105, 193);
  await expect(fog).toBeVisible();
  await capture(page, info, "fog-line-next");
  await page.clock.resume();
});

for (const low of [false, true]) {
  const quality = low ? "low" : "standard";
  test(`S2 legal lake edge keeps backdrop covered through a full orbit at ${quality} quality`, async ({
    page,
    isMobile,
  }, info) => {
    if (!isMobile) await page.setViewportSize({ width: 1440, height: 720 });
    await page.addInitScript(() => {
      // A sentinel exposes holes without coupling the regression to any palette.
      const clearColor = WebGL2RenderingContext.prototype.clearColor;
      WebGL2RenderingContext.prototype.clearColor = function (_r, _g, _b, a) {
        clearColor.call(this, 1, 0, 1, a);
      };
    });
    const position = { x: 104, z: 314 };
    await parkAt(page, position.x, position.z, "S2", low, "A", false, true);
    const coverage: Record<string, number> = {};
    coverage.default = await countExposedBackground(
      page,
      await capture(page, info, "default"),
    );
    for (const [index, view] of [
      { name: "side-low", yaw: Math.PI / 2, pitch: 35, dy: -125 },
      {
        name: "behind",
        yaw: Math.PI,
        pitch: 49,
        dy: ((Math.PI / 180) * 14) / 0.006,
      },
      { name: "other-side-high", yaw: -Math.PI / 2, pitch: 65, dy: 125 },
      {
        name: "all-the-way-around",
        yaw: 0,
        pitch: 49,
        dy: ((-Math.PI / 180) * 16) / 0.006,
      },
    ].entries()) {
      await orbit(page, 51 + index, -262, view.dy, view.yaw, view.pitch);
      const { x, z } = await readView(page);
      expect({ x, z }).toEqual(position);
      coverage[view.name] = await countExposedBackground(
        page,
        await capture(page, info, view.name),
      );
    }
    expect(coverage).toEqual({
      default: 0,
      "side-low": 0,
      behind: 0,
      "other-side-high": 0,
      "all-the-way-around": 0,
    });
  });

  test(`S4 outer route and warning stay readable from steep and shallow views at ${quality} quality`, async ({
    page,
  }, info) => {
    await page.clock.install();
    await parkAt(page, 0, 525, "S4", low, "B");
    await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 500);
    await page.keyboard.down("KeyC");
    await page.keyboard.down("KeyW");
    // Hold the flock in the approach window while loading scenery and capturing angles.
    await page.clock.runFor(340);
    await expect
      .poll(async () => (await readView(page)).z, { timeout: 10_000 })
      .toBeGreaterThan(525.4);
    await expect
      .poll(async () => {
        await page.clock.runFor(32);
        return (await readView(page)).scenery["STR-001"];
      })
      .toBe(low ? "procedural" : "model");
    const warning = page.locator("#hazard-notice");
    const route = page
      .locator("#marker-layer")
      .getByText("外围直达航道", { exact: true });
    await expect(warning).toContainText("前方风机");
    await expect(route).toBeVisible();
    await capture(page, info, "default");
    for (const [index, view] of [
      { name: "shallow", dx: -262, yaw: Math.PI / 2, pitch: 35, dy: -125 },
      { name: "steep", dx: 524, yaw: -Math.PI / 2, pitch: 65, dy: 250 },
    ].entries()) {
      await orbit(
        page,
        51 + index,
        view.dx,
        view.dy,
        view.yaw,
        view.pitch,
        600,
      );
      await expect(warning).toContainText("前方风机");
      await expect(route).toBeVisible();
      const banner = await warning.boundingBox();
      const marker = await route.boundingBox();
      if (!banner || !marker) throw new Error("Wind farm guidance is missing");
      expect(
        banner.x < marker.x + marker.width &&
          marker.x < banner.x + banner.width &&
          banner.y < marker.y + marker.height &&
          marker.y < banner.y + banner.height,
      ).toBe(false);
      await capture(page, info, view.name);
    }
    await page.keyboard.up("KeyW");
    await page.keyboard.up("KeyC");
    await page.clock.resume();
  });
}

for (const vista of [
  { segment: "S0", z: 0, width: 1280, height: 720 },
  { segment: "S2", z: 224, width: 1400, height: 600 },
]) {
  test(`desktop wide orbit shows the ${vista.segment} vista across pitch and heading`, async ({
    page,
    isMobile,
  }, info) => {
    test.skip(isMobile, "desktop panorama");
    await page.setViewportSize({ width: vista.width, height: vista.height });
    await parkAt(page, 0, vista.z, vista.segment, false, "B", true);
    if (vista.segment === "S2") {
      const markers = page.locator("#marker-layer");
      await expect(markers.getByText("短山口 · 风向分水岭")).toBeVisible();
      await expect(markers.getByText("长湖路 · 沿岸补给")).toBeVisible();
    }
    await capture(page, info, "follow-49");

    await mouseOrbit(page, 0, -240);
    for (const [i, heading] of [0, 90, 180, -90].entries()) {
      if (i) await mouseOrbit(page, -262, 0, "right");
      await expect
        .poll(async () => {
          const { yaw, requestedPitch } = (await readView(page)).camera;
          const headingError = Math.abs(
            angleDelta((yaw * Math.PI) / 180, (heading * Math.PI) / 180),
          );
          return headingError < 0.01 && Math.abs(requestedPitch - 20) < 0.05;
        })
        .toBe(true);
      const { pitch } = (await readView(page)).camera;
      expect(pitch).toBeGreaterThanOrEqual(19.99);
      expect(pitch).toBeLessThan(24);
      await capture(page, info, `low-${heading}`);
    }

    await mouseOrbit(page, 0, 260);
    await expect
      .poll(async () => (await readView(page)).camera.pitch)
      .toBeCloseTo(80, 0);
    await capture(page, info, "high-80");
    const { x, z } = await readView(page);
    expect({ x, z }).toEqual({ x: 0, z: vista.z });
  });
}

for (const side of [-55, 56]) {
  test(`S4 an aligned flock at x=${side} sees the exit on its side without an urgent warning`, async ({
    page,
  }) => {
    await parkAt(page, side, 563, "S4", true);
    await page.keyboard.down("KeyW");
    await expect
      .poll(async () => (await readView(page)).z)
      .toBeGreaterThan(566);
    await expect(page.locator("#hazard-cue")).toBeHidden();
    const exit = page.locator("#marker-layer").getByText("沿外围继续");
    await expect(exit).toBeVisible();
    const box = await exit.boundingBox();
    const viewport = page.viewportSize();
    if (!box || !viewport) throw new Error("Missing outer route marker");
    expect(Math.abs(box.x + box.width / 2 - viewport.width / 2)).toBeLessThan(
      viewport.width * 0.2,
    );
    await page.keyboard.up("KeyW");
  });
}

test("gallery warning shows both routes inside the horizontal safe area in low quality", async ({
  page,
}, info) => {
  await parkAt(page, -48, 684, "S5", true);
  await page.addStyleTag({
    content: ":root { --pad-left: 42px; --pad-right: 42px; }",
  });
  const warning = page.locator("#hazard-notice");
  await page.keyboard.down("KeyC");
  await page.keyboard.down("KeyW");
  await expect(warning).toContainText("前方玻璃幕墙");
  await expect(page.locator("#warning-detail")).toContainText("内廊浅湾可补给");
  const markers = page.locator("#marker-layer");
  const width = page.viewportSize()?.width ?? 0;
  for (const name of ["内廊 · 背风，两道弯", "外侧河道 · 宽阔"]) {
    const marker = markers.getByText(name, { exact: true });
    await expect(marker).toBeVisible();
    const bounds = await marker.boundingBox();
    if (!bounds) throw new Error(`Missing gallery marker ${name}`);
    expect(bounds.x).toBeGreaterThanOrEqual(42);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width - 42);
  }
  await capture(page, info, "gallery-warning");
  await page.keyboard.up("KeyW");
  await page.keyboard.up("KeyC");
});

test("S2 can rebuild the scene at both quality levels while paused", async ({
  page,
}, info) => {
  const position = { x: 104, z: 314 };
  await parkAt(page, position.x, position.z, "S2", false);
  await page.getByRole("button", { name: "暂停" }).click();
  const pause = page.getByRole("dialog", { name: "飞行暂停" });
  for (const low of [true, false]) {
    await pause.getByRole("button", { name: "设置" }).click();
    const settings = page.getByRole("dialog", { name: "设置" });
    await settings.getByLabel("低画质").setChecked(low);
    await settings.getByRole("button", { name: "返回", exact: true }).click();
    await expect(pause).toBeVisible();
    await capture(page, info, low ? "switched-to-low" : "restored-standard");
    const { x, z } = await readView(page);
    expect({ x, z }).toEqual(position);
  }
  await pause.getByRole("button", { name: "继续飞行" }).click();
  await expect(page.getByRole("button", { name: "结阵" })).toBeVisible();
});

for (const specimen of [
  { segment: "S2", x: 104, z: 314, width: 1400, height: 600, low: false },
  { segment: "S5", x: -84, z: 746, width: 1280, height: 720, low: true },
]) {
  test(`desktop wide orbit at ${specimen.segment} covers the landscape and avoids solid scenery`, async ({
    page,
    isMobile,
  }, info) => {
    test.skip(isMobile, "desktop mouse preview");
    await page.setViewportSize({
      width: specimen.width,
      height: specimen.height,
    });
    await page.addInitScript(() => {
      const clearColor = WebGL2RenderingContext.prototype.clearColor;
      WebGL2RenderingContext.prototype.clearColor = function (_r, _g, _b, a) {
        clearColor.call(this, 1, 0, 1, a);
      };
    });
    await parkAt(
      page,
      specimen.x,
      specimen.z,
      specimen.segment,
      specimen.low,
      "B",
      true,
      true,
    );
    expect(
      await countExposedBackground(
        page,
        await capture(page, info, "classic-follow"),
      ),
    ).toBe(0);
    await mouseOrbit(page, 0, -240);
    for (const [index, heading] of [0, 90, 180, -90].entries()) {
      if (index > 0) await mouseOrbit(page, -262, 0, "right");
      await expect
        .poll(async () => {
          const view = await readView(page);
          return Math.abs(
            angleDelta(
              Math.atan2(view.basis.up.x, view.basis.up.z),
              (heading * Math.PI) / 180,
            ),
          );
        })
        .toBeLessThan(0.02);
      const sample = await readView(page);
      const pitch =
        (Math.asin(1 / Math.hypot(sample.basis.up.x, sample.basis.up.z)) *
          180) /
        Math.PI;
      expect(pitch).toBeGreaterThanOrEqual(19.99);
      if (specimen.segment === "S5" && heading === 180)
        expect(pitch).toBeGreaterThan(25);
      const screenshot = await capture(page, info, `low-${heading}`);
      expect(await countExposedBackground(page, screenshot)).toBe(0);
    }
    await mouseOrbit(page, 0, 260);
    await expect
      .poll(async () => {
        const { basis } = await readView(page);
        return (
          (Math.asin(1 / Math.hypot(basis.up.x, basis.up.z)) * 180) / Math.PI
        );
      })
      .toBeCloseTo(80, 0);
    expect(
      await countExposedBackground(page, await capture(page, info, "wide-top")),
    ).toBe(0);
  });
}
