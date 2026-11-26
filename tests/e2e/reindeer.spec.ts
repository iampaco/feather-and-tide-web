import { writeFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import type { ReindeerState } from "../../src/core/game";
import { enterSpeciesMenu, openTitle } from "../fixtures/menu";
import { mouseOrbit, pointer } from "../fixtures/pointer";
import { reindeerTrip } from "../fixtures/reindeer";

type Sample = Pick<ReindeerState, "tick" | "phase" | "waitTicks" | "actors"> & {
  readonly x: number;
  readonly z: number;
  readonly speed: number;
  readonly checkpoint: string;
  readonly camera: { readonly yaw: number; readonly pitch: number };
  readonly landingProgress?: number;
  readonly landingCompanion?: string;
};

type MoveTarget =
  | { readonly xBelow: number }
  | { readonly xAbove: number }
  | { readonly zAbove: number }
  | { readonly checkpoint: "C1" | "C2" }
  | { readonly landing: true };

async function current(page: Page): Promise<Sample> {
  return JSON.parse(
    (await page.locator("#game").getAttribute("data-flight")) ?? "{}",
  ) as Sample;
}

async function openReindeer(page: Page, reload = true): Promise<void> {
  if (reload) await openTitle(page, "/?diagnostics");
  await enterSpeciesMenu(page);
  const entry = page.getByRole("button", { name: /^驯鹿/ });
  await expect(entry).toBeEnabled();
  await entry.click();
}

async function moveUntil(
  page: Page,
  key: string,
  target: MoveTarget,
  run = true,
): Promise<void> {
  // Release at the next rendered snapshot even when the test runner is busy.
  const watch = await page.evaluateHandle(
    ({ key, target }) => {
      const game = document.getElementById("game");
      if (!game) throw new Error("Missing game");
      const code = `Key${key.toUpperCase()}`;
      const result = { reached: false };
      const observer = new MutationObserver(() => {
        const state: Sample = JSON.parse(game.dataset.flight ?? "{}");
        result.reached =
          "xBelow" in target
            ? state.x < target.xBelow
            : "xAbove" in target
              ? state.x > target.xAbove
              : "zAbove" in target
                ? state.z > target.zAbove
                : "checkpoint" in target
                  ? state.checkpoint === target.checkpoint
                  : state.phase === "landing" || state.phase === "completed";
        if (result.reached) {
          observer.disconnect();
          window.dispatchEvent(new KeyboardEvent("keyup", { code }));
        }
      });
      observer.observe(game, {
        attributes: true,
        attributeFilter: ["data-flight"],
      });
      return { result, observer };
    },
    { key, target },
  );
  try {
    if (run) await page.keyboard.down("Shift");
    await page.keyboard.down(key);
    await expect
      .poll(() => watch.evaluate(({ result }) => result.reached), {
        timeout: 48_000,
        intervals: [100, 100, 150],
      })
      .toBe(true);
  } finally {
    await page.keyboard.up(key);
    if (run) await page.keyboard.up("Shift");
    await watch.evaluate(({ observer }) => observer.disconnect());
    await watch.dispose();
  }
}

test.describe("reindeer journey", () => {
  for (const quality of ["standard", "low"] as const) {
    test(`RD-A14 reports reindeer startup and rendering in ${quality} quality`, async ({
      page,
    }, info) => {
      await page.addInitScript((low) => {
        localStorage.setItem(
          "feather-tide-settings-v1",
          JSON.stringify({ low, music: false }),
        );
      }, quality === "low");
      await openReindeer(page);
      const game = page.locator("#game");
      await expect(game).toHaveAttribute(
        "data-reindeer-startup",
        /firstPlayableFrameMs/,
      );
      const startup: unknown = JSON.parse(
        (await game.getAttribute("data-reindeer-startup")) ?? "null",
      );
      expect(startup).toMatchObject({
        from: "selection",
        checkpoint: null,
        titleReadyMs: expect.any(Number),
        firstPlayableFrameMs: expect.any(Number),
      });
      // A diagnostic sample needs 180 rendered frames, including a cold shader start.
      await expect(game).toHaveAttribute("data-performance", /geometries/, {
        timeout: 20000,
      });
      const frames: unknown = JSON.parse(
        (await game.getAttribute("data-performance")) ?? "null",
      );
      expect(frames).toMatchObject({
        segment: "R0",
        quality,
        medianMs: expect.any(Number),
        p95Ms: expect.any(Number),
        calls: expect.any(Number),
        geometries: expect.any(Number),
        textures: expect.any(Number),
      });
      await writeFile(
        info.outputPath("startup-and-frames.json"),
        JSON.stringify({ startup, frames }, null, 2) + "\n",
      );
    });
  }

  test("RD-A03 RD-A04 T21 real entrance, stopping, wait, mirror-safe pointers and pause", async ({
    page,
    hasTouch,
  }, info) => {
    await openReindeer(page);
    await expect(page.locator("#hud")).toHaveAttribute(
      "data-species",
      "reindeer",
    );
    const wait = page.getByRole("button", { name: "等候", exact: true });
    await expect(wait).toBeVisible();
    await expect.poll(async () => (await current(page)).actors?.length).toBe(9);
    await page.screenshot({
      path: info.outputPath("R0-winter-start.png"),
      scale: "css",
    });
    if (hasTouch) {
      const size = page.viewportSize()!;
      const left = Math.floor(size.width * 0.18);
      const right = Math.floor(size.width * 0.66);
      const y = Math.floor(size.height * 0.69);
      const start = await current(page);
      await pointer(page, "pointerdown", 11, left, y);
      await pointer(page, "pointermove", 11, left, y - 60);
      await pointer(page, "pointerdown", 12, right, y);
      await pointer(page, "pointermove", 12, right + 65, y - 9);
      await expect
        .poll(async () => Math.abs((await current(page)).camera.yaw))
        .toBeGreaterThan(5);
      await expect
        .poll(async () => (await current(page)).z)
        .toBeGreaterThan(start.z + 0.4);
      await pointer(page, "pointerup", 12, right + 65, y - 9);
      const button = await wait.boundingBox();
      expect(button).not.toBeNull();
      const bx = button!.x + button!.width / 2;
      const by = button!.y + button!.height / 2;
      await pointer(page, "pointerdown", 13, bx, by, "#formation");
      await pointer(page, "pointermove", 13, right, y);
      await expect
        .poll(async () => (await current(page)).waitTicks)
        .toBeGreaterThan(15);
      await expect.poll(async () => (await current(page)).speed).toBe(0);
      await pointer(page, "pointercancel", 13, right, y);
    } else {
      await moveUntil(page, "w", { zAbove: 15 });
      await expect.poll(async () => (await current(page)).speed).toBe(0);
      const settled = await current(page);
      await page.keyboard.down("Space");
      await page.keyboard.down("d");
      await expect
        .poll(async () => (await current(page)).waitTicks)
        .toBeGreaterThan(20);
      expect(await current(page)).toMatchObject({ x: settled.x, z: settled.z });
      await page.keyboard.up("d");
      await page.keyboard.up("Space");
      await mouseOrbit(page, 90, 0);
      await expect
        .poll(async () => Math.abs((await current(page)).camera.yaw))
        .toBeGreaterThan(9);
    }
    await page.locator("#camera-reset").click();
    await expect
      .poll(async () => Math.abs((await current(page)).camera.yaw))
      .toBeLessThan(0.15);
    await page.locator("#pause-flight").click();
    await expect(page.getByRole("heading", { name: "旅程暂停" })).toBeVisible();
    const paused = await current(page);
    await expect(wait).toHaveAttribute("aria-pressed", "false");
    expect((await current(page)).tick).toBe(paused.tick);
    await page.getByRole("button", { name: "继续旅程" }).click();
    await expect
      .poll(async () => (await current(page)).tick)
      .toBeGreaterThan(paused.tick);
    expect((await current(page)).waitTicks).toBe(0);
  });

  test("RD-A04 R0 compares live and locked movement mapping with the same touch orbit", async ({
    page,
    hasTouch,
  }, info) => {
    test.skip(!hasTouch, "mobile touch project");
    test.setTimeout(48_000);
    const results = [];
    for (const mapping of ["A", "B"] as const) {
      await openTitle(page, "/?diagnostics");
      await page.evaluate((chosen) => {
        localStorage.setItem(
          "feather-tide-settings-v1",
          JSON.stringify({
            mapping: chosen,
            music: false,
            low: true,
            reduced: true,
          }),
        );
      }, mapping);
      await openReindeer(page);
      await expect
        .poll(async () => (await current(page)).actors?.length)
        .toBe(9);
      const { width, height } = page.viewportSize()!;
      const left = Math.floor(width * 0.18);
      const right = Math.floor(width * 0.65);
      const y = Math.floor(height * 0.63);
      await pointer(page, "pointerdown", 31, left, y);
      await pointer(page, "pointermove", 31, left, y - 63);
      const start = await current(page);
      await pointer(page, "pointerdown", 32, right, y);
      await pointer(page, "pointermove", 32, right + 120, y);
      await pointer(page, "pointerup", 32, right + 120, y);
      await expect
        .poll(async () => (await current(page)).tick)
        .toBeGreaterThan(start.tick + 60);
      const end = await current(page);
      const heading = Math.abs(end.actors[0]!.heading);
      expect(Math.abs(end.camera.yaw)).toBeGreaterThan(20);
      if (mapping === "A") expect(heading).toBeGreaterThan(0.25);
      else expect(heading).toBeLessThan(0.06);
      results.push({
        mapping,
        yaw: end.camera.yaw,
        heading,
        x: end.x - start.x,
        z: end.z - start.z,
      });
      await pointer(page, "pointercancel", 31, left, y - 63);
      await expect.poll(async () => (await current(page)).speed).toBe(0);
    }
    await writeFile(
      info.outputPath("R0-mapping-comparison.json"),
      JSON.stringify(results, null, 2) + "\n",
    );
  });

  test("RD-A05 RD-A06 RD-A15 the real journey crosses R1, reloads C1 and finishes from R0", async ({
    page,
    browserName,
  }, info) => {
    test.skip(browserName !== "chromium", "long keyboard journey covered once");
    test.setTimeout(265_000);
    await page.setViewportSize({ width: 960, height: 540 });
    await openReindeer(page);
    await expect(page.locator("#hud")).toHaveAttribute(
      "data-species",
      "reindeer",
    );
    await moveUntil(page, "d", { xBelow: -11.6 });
    await moveUntil(page, "w", { zAbove: 102 });
    await expect(page.locator("#hazard-notice")).toContainText("车道有车流");
    await expect(page.locator("#marker-layer")).toContainText("动物通道");
    await expect(page.locator("#notice")).toHaveText("路肩集队点");
    await page.screenshot({
      path: info.outputPath("R1-road-approach.png"),
      scale: "css",
    });
    const sampleR1 = await page
      .locator("#game")
      .getAttribute("data-performance");
    if (sampleR1)
      await writeFile(info.outputPath("R1-frame-samples.json"), sampleR1);
    await moveUntil(page, "w", { zAbove: 123 }, false);
    await expect(page.locator("#notice")).toHaveText("动物通道");
    await expect(page.locator("#detail")).toContainText("已到远侧");
    await expect(page.getByRole("button", { name: "等候" })).toHaveAttribute(
      "aria-disabled",
      "false",
    );
    await page.screenshot({
      path: info.outputPath("R1-culvert.png"),
      scale: "css",
    });
    await moveUntil(page, "w", { checkpoint: "C1" });
    await expect(page.locator("#notice")).toContainText("检查点 C1 已保存");
    await openReindeer(page);
    await expect(
      page.getByRole("heading", { name: "继续苔原过路" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "从检查点继续" }).click();
    await expect.poll(async () => (await current(page)).checkpoint).toBe("C1");
    await moveUntil(page, "a", { xAbove: 15.5 });
    await moveUntil(page, "w", { zAbove: 258 });
    await expect(page.locator("#marker-layer")).toContainText("宽口");
    await page.screenshot({
      path: info.outputPath("R2-wide-opening.png"),
      scale: "css",
    });
    const sampleR2 = await page
      .locator("#game")
      .getAttribute("data-performance");
    if (sampleR2)
      await writeFile(info.outputPath("R2-frame-samples.json"), sampleR2);
    await moveUntil(page, "w", { zAbove: 278 });
    await moveUntil(page, "d", { xBelow: -5.5 });
    await moveUntil(page, "w", { zAbove: 301 });
    await page.screenshot({
      path: info.outputPath("R2-S-bend.png"),
      scale: "css",
    });
    await moveUntil(page, "a", { xAbove: 15.5 });
    await moveUntil(page, "w", { zAbove: 322 });
    await moveUntil(page, "d", { xBelow: -46 });
    await page.screenshot({
      path: info.outputPath("R3-greenbelt-approach.png"),
      scale: "css",
    });
    await moveUntil(page, "w", { zAbove: 399 });
    await page.screenshot({
      path: info.outputPath("R3-greenbelt-supply.png"),
      scale: "css",
    });
    await moveUntil(page, "a", { xAbove: -18.5 });
    await moveUntil(page, "w", { zAbove: 451 });
    await moveUntil(page, "a", { xAbove: -1.8 });
    await moveUntil(page, "w", { checkpoint: "C2" });
    await moveUntil(page, "w", { zAbove: 550 });
    const sampleR4 = await page
      .locator("#game")
      .getAttribute("data-performance");
    if (sampleR4)
      await writeFile(info.outputPath("R4-frame-samples.json"), sampleR4);
    await moveUntil(page, "w", { landing: true });
    await expect(page.locator("#arrived")).toHaveText("9 / 9");
    await expect
      .poll(async () => (await current(page)).landingProgress ?? 0, {
        intervals: [50, 70, 100],
        timeout: 3000,
      })
      .toBeGreaterThan(0.55);
    await page.screenshot({
      path: info.outputPath("R4-full-journey.png"),
      scale: "css",
    });
    const perf = await page.locator("#game").getAttribute("data-performance");
    if (perf)
      await info.attach("reindeer-frame-samples", {
        body: perf,
        contentType: "application/json",
      });
  });

  test("RD-A11 RD-A13 a P3-2 C2 resumes and acknowledges the final deer at 9/9", async ({
    page,
    browserName,
  }, info) => {
    test.skip(browserName !== "chromium", "long keyboard journey covered once");
    test.setTimeout(68_000);
    const currentC2 = reindeerTrip("greenbelt").checkpoints[1]!;
    const snapshot = {
      ...currentC2,
      state: { ...currentC2.state, levelRevision: "reindeer-p3-2" },
    };
    await openTitle(page, "/?diagnostics");
    await page.evaluate(
      (checkpoint) =>
        new Promise<void>((resolve, reject) => {
          const request = indexedDB.open("feather-tide", 1);
          request.onerror = () => reject(request.error);
          request.onupgradeneeded = () =>
            request.result.createObjectStore("checkpoint");
          request.onsuccess = () => {
            const db = request.result;
            const tx = db.transaction("checkpoint", "readwrite");
            const { state } = checkpoint;
            tx.objectStore("checkpoint").put(
              {
                kind: "checkpoint",
                version: 1,
                runId: "f".repeat(32),
                checkpoint,
                levelId: state.levelId,
                levelRevision: state.levelRevision,
                species: state.species,
                mode: state.mode,
              },
              [state.species, state.levelId, state.mode],
            );
            tx.oncomplete = () => {
              db.close();
              resolve();
            };
            tx.onerror = () => {
              db.close();
              reject(tx.error);
            };
          };
        }),
      snapshot,
    );
    await openReindeer(page, false);
    await page.getByRole("button", { name: "从检查点继续" }).click();
    await expect(page.locator("#game")).toHaveAttribute(
      "data-reindeer-startup",
      /"from":"start","checkpoint":"C2"/,
    );
    await moveUntil(page, "w", { zAbove: 564 });
    await expect(page.locator("#flight-cue")).toHaveAttribute(
      "data-teammate",
      "on-way",
    );
    await expect(page.locator("#notice")).toHaveText("同伴还没进落脚区");
    await expect(
      page.locator("#marker-layer").getByText("尚未抵达", { exact: true }),
    ).toBeVisible();
    await page.keyboard.down("c");
    await page.keyboard.down("w");
    try {
      await expect(page.locator("#arrived")).toHaveText("8 / 9", {
        timeout: 16_000,
      });
      await expect(page.locator("#notice")).toHaveText("同伴还没进落脚区");
      await page.screenshot({
        path: info.outputPath("R4-waiting-for-herd.png"),
        scale: "css",
      });
    } finally {
      await page.keyboard.up("w");
      await page.keyboard.up("c");
    }
    await moveUntil(page, "w", { landing: true });
    await expect(page.locator("#arrived")).toHaveText("9 / 9");
    expect((await current(page)).landingCompanion).toBe("reindeer-8");
    await expect(
      page.locator("#marker-layer").getByText("最后一位同伴已归队"),
    ).toBeVisible();
    await page.screenshot({
      path: info.outputPath("R4-nine-reindeer.png"),
      scale: "css",
    });
    const skip = page.getByRole("button", { name: "跳过落脚演出" });
    if (await skip.isVisible()) await skip.click();
    await expect(page.getByRole("heading", { name: "一起抵达" })).toBeVisible();
    await expect(page.locator("#panel-summary")).toHaveText("9 / 9 只鹿落脚");
    await expect(page.locator("#panel-note")).toBeEmpty();
    await openReindeer(page);
    await expect(
      page.getByRole("heading", { name: "上次旅程已落脚" }),
    ).toBeVisible();
  });

  test("RD-A13 a failed model request can retry the reindeer entry", async ({
    page,
  }) => {
    const model = "**/assets/reindeer/reindeer-*.glb";
    await page.route(model, (route) => route.abort());
    await openReindeer(page);
    await expect(page.locator("#boot-status")).toContainText(
      "苔原过路加载失败",
    );
    await page.unroute(model);
    await page.locator("#retry-load").click();
    await expect(page.locator("#hud")).toHaveAttribute(
      "data-species",
      "reindeer",
    );
    await expect(page.locator("#notice")).toContainText("蹄印");
  });

  test("RD-A04 RD-A12 mirrored large tap-to-wait and reduced visuals in landscape", async ({
    page,
    hasTouch,
  }, info) => {
    test.skip(!hasTouch, "mobile touch project");
    await page.addInitScript(() => {
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({
          mirror: true,
          large: true,
          toggle: true,
          music: false,
          mapping: "B",
          reduced: true,
          low: true,
        }),
      );
    });
    await openReindeer(page);
    await expect(page.locator("#game")).toHaveClass(/mirrored/);
    await expect(page.locator("#game")).toHaveClass(/large/);
    const control = page.getByRole("button", { name: "等候", exact: true });
    await expect(control).toBeVisible();
    const box = await control.boundingBox();
    const viewport = page.viewportSize()!;
    expect(box!.x + box!.width).toBeLessThan(viewport.width / 2);
    const x = box!.x + box!.width / 2;
    const y = box!.y + box!.height / 2;
    await pointer(page, "pointerdown", 21, x, y, "#formation");
    await pointer(page, "pointerup", 21, x, y, "#formation");
    await expect
      .poll(async () => (await current(page)).waitTicks)
      .toBeGreaterThan(42);
    await page.screenshot({
      path: info.outputPath("R0-mirrored-low-wait.png"),
      scale: "css",
    });
    await pointer(page, "pointerdown", 22, x, y, "#formation");
    await pointer(page, "pointerup", 22, x, y, "#formation");
    await expect.poll(async () => (await current(page)).waitTicks).toBe(0);
  });

  test("RD-A05 RD-A12 R1 graybox and watercolour share lane rules and warnings in a rear view", async ({
    page,
    browserName,
  }, info) => {
    test.skip(browserName !== "chromium", "R1 matched camera evidence");
    test.setTimeout(52_000);
    await page.route("**/levels/reindeer.json", async (route) => {
      const response = await route.fetch();
      const level = (await response.json()) as {
        spawn: { x: number; z: number };
        spawnSegment: string;
        zones: { id: string; motion?: { phaseTicks: number } }[];
      };
      level.spawn = { x: 1, z: 112 };
      level.spawnSegment = "R1";
      const vehicle = level.zones.find(({ id }) => id === "road-vehicle");
      if (vehicle?.motion) vehicle.motion.phaseTicks = 0;
      await route.fulfill({ response, json: level });
    });
    await page.addInitScript(() => {
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({
          music: false,
          reduced: true,
          low: true,
        }),
      );
    });
    for (const form of ["model", "graybox"] as const) {
      await openTitle(
        page,
        `/?diagnostics${form === "graybox" ? "&reindeerGraybox=1" : ""}`,
      );
      await openReindeer(page, false);
      await expect
        .poll(async () => (await current(page)).actors?.length)
        .toBe(9);
      await expect(page.locator("#hazard-notice")).toContainText("车道有车流");
      const incoming = page
        .locator("#marker-layer")
        .getByText("来车", { exact: true });
      await expect(incoming).toBeVisible();
      await page.screenshot({
        path: info.outputPath(`R1-${form}-default.png`),
        scale: "css",
      });
      await mouseOrbit(page, -199, 72);
      await expect
        .poll(async () => Math.abs((await current(page)).camera.yaw))
        .toBeGreaterThan(55);
      await expect(page.locator("#hazard-notice")).toBeVisible();
      await page.screenshot({
        path: info.outputPath(`R1-${form}-side.png`),
        scale: "css",
      });
      await mouseOrbit(page, -220, -160);
      await expect
        .poll(async () => Math.abs((await current(page)).camera.yaw))
        .toBeGreaterThan(120);
      await expect
        .poll(async () => (await current(page)).camera.pitch)
        .toBeLessThanOrEqual(36);
      await expect(page.locator("#hazard-notice")).toBeVisible();
      await expect(incoming).toBeVisible({ timeout: 12_000 });
      await page.screenshot({
        path: info.outputPath(`R1-${form}-rear.png`),
        scale: "css",
      });
      await page.locator("#camera-reset").click();
      await expect
        .poll(async () => Math.abs((await current(page)).camera.yaw))
        .toBeLessThan(0.15);
      await moveUntil(page, "w", { zAbove: 122 });
      const wait = page.getByRole("button", { name: "等候", exact: true });
      await expect(wait).toHaveAttribute("aria-disabled", "true");
      await page.keyboard.down("Space");
      await expect(page.locator("#hazard-notice")).toHaveText("先离开车道");
      expect((await current(page)).waitTicks).toBe(0);
      await page.keyboard.up("Space");
    }
  });

  test("RD-A10 RD-A13 three real journey slots and reindeer graphics interruption", async ({
    page,
    browserName,
  }) => {
    test.skip(
      browserName !== "chromium",
      "requires Chromium graphics recovery",
    );
    test.setTimeout(52_000);
    await openTitle(page, "/?diagnostics");
    for (const [name, species] of [
      [/^斑头雁/, "goose"],
      [/^鲸/, "whale"],
      [/^驯鹿/, "reindeer"],
    ] as const) {
      await enterSpeciesMenu(page);
      await page.getByRole("button", { name }).click();
      await expect(page.locator("#hud")).toHaveAttribute(
        "data-species",
        species,
      );
      if (species !== "reindeer") {
        await page.locator("#pause-flight").click();
        await page
          .getByRole("button", { name: "返回标题", exact: true })
          .click();
      }
    }
    const slots = () =>
      page.evaluate(
        () =>
          new Promise<IDBValidKey[]>((resolve, reject) => {
            const open = indexedDB.open("feather-tide", 1);
            open.onsuccess = () => {
              const db = open.result;
              const request = db
                .transaction("checkpoint")
                .objectStore("checkpoint")
                .getAllKeys();
              request.onsuccess = () => {
                db.close();
                resolve(request.result);
              };
              request.onerror = () => {
                db.close();
                reject(request.error);
              };
            };
            open.onerror = () => reject(open.error);
          }),
      );
    await expect
      .poll(slots)
      .toEqual(
        expect.arrayContaining([
          "journey",
          ["whale", "whale", "journey"],
          ["reindeer", "reindeer", "journey"],
        ]),
      );
    await page.keyboard.down("Space");
    await expect
      .poll(async () => (await current(page)).waitTicks)
      .toBeGreaterThan(3);
    await page.evaluate(() => {
      const extension = document
        .querySelector("canvas")
        ?.getContext("webgl2")
        ?.getExtension("WEBGL_lose_context");
      if (!extension) throw new Error("Missing WebGL loss test extension");
      extension.loseContext();
      setTimeout(() => extension.restoreContext(), 300);
    });
    await expect(page.locator("#panel")).toBeVisible();
    await expect(page.getByRole("button", { name: "继续旅程" })).toBeVisible();
    await page.keyboard.up("Space");
    await page.getByRole("button", { name: "继续旅程" }).click();
    await expect.poll(async () => (await current(page)).waitTicks).toBe(0);
    await expect.poll(async () => (await current(page)).phase).toBe("playing");
  });
});
