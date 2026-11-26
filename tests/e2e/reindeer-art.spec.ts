import { writeFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import type { Vec2 } from "../../src/core/math";
import { enterSpeciesMenu, openTitle } from "../fixtures/menu";
import { pointer } from "../fixtures/pointer";
import { herdAt, reindeerLevel } from "../fixtures/reindeer";

const epoch = Date.UTC(2026, 0, 1);

async function enterView(
  page: Page,
  spawn: Vec2,
  segment: string,
  options: { readonly low?: boolean; readonly fixed?: boolean } = {},
): Promise<void> {
  await page.setViewportSize({ width: 852, height: 393 });
  await page.addInitScript((low) => {
    localStorage.setItem(
      "feather-tide-settings-v1",
      JSON.stringify({ music: false, low, reduced: low }),
    );
  }, options.low === true);
  const locked = spawn.z > 479;
  const route =
    locked || (spawn.z > 347 && spawn.x < 0)
      ? "greenbelt"
      : spawn.z > 347
        ? "dust"
        : null;
  const id = "art-anchor";
  const state = herdAt(spawn, {
    segmentId: segment,
    tick: segment === "R3" && spawn.x > 0 ? 1440 : 0,
    route,
    routeLocked: locked,
    triggered: [
      id,
      ...(route ? [route === "greenbelt" ? "green-gate" : "dust-gate"] : []),
      ...(locked ? ["mining-merge", "C1", "C2"] : []),
    ],
  });
  const xMin = Math.min(...state.actors.map(({ pos }) => pos.x)) - 1;
  const xMax = Math.max(...state.actors.map(({ pos }) => pos.x)) + 1;
  const zMin = Math.min(...state.actors.map(({ pos }) => pos.z)) - 1;
  const zMax = Math.max(...state.actors.map(({ pos }) => pos.z)) + 1;
  // The published level keeps its real spawn and checkpoints. A fixture-only
  // checkpoint lets both builds enter with identical positions and car phase.
  await page.route("**/levels/reindeer.json", (request) =>
    request.fulfill({
      json: {
        ...reindeerLevel,
        zones: [
          ...reindeerLevel.zones.map((zone) =>
            zone.kind === "hazard" && zone.motion
              ? { ...zone, motion: { ...zone.motion, phaseTicks: 220 } }
              : zone,
          ),
          {
            id,
            kind: "checkpoint",
            label: "画面对照",
            points: [
              { x: xMin, z: zMin },
              { x: xMax, z: zMin },
              { x: xMax, z: zMax },
              { x: xMin, z: zMax },
              { x: xMin, z: zMin },
            ],
          },
        ],
      },
    }),
  );
  await openTitle(page, "/?diagnostics");
  await page.evaluate(
    ({ id, state }) =>
      new Promise<void>((resolve, reject) => {
        const request = indexedDB.open("feather-tide", 1);
        request.onupgradeneeded = () =>
          request.result.createObjectStore("checkpoint");
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
          const db = request.result;
          const tx = db.transaction("checkpoint", "readwrite");
          tx.objectStore("checkpoint").put(
            {
              kind: "checkpoint",
              version: 1,
              runId: "f".repeat(32),
              species: state.species,
              levelId: state.levelId,
              levelRevision: state.levelRevision,
              mode: state.mode,
              checkpoint: { id, version: 1, state },
            },
            [state.species, state.levelId, state.mode],
          );
          tx.oncomplete = () => {
            db.close();
            resolve();
          };
          tx.onabort = () => {
            db.close();
            reject(tx.error);
          };
        };
      }),
    { id, state },
  );
  await enterSpeciesMenu(page);
  await page.getByRole("button", { name: /^驯鹿/ }).click();
  const resume = page.getByRole("button", { name: "从检查点继续" });
  await expect(resume).toBeVisible({ timeout: 15_000 });
  if (options.fixed !== false) {
    await page.clock.install({ time: epoch });
    await page.clock.pauseAt(epoch + 10_000);
    await resume.dispatchEvent("click");
  } else {
    await resume.click();
  }
  await expect(page.locator("#hud")).toHaveAttribute(
    "data-species",
    "reindeer",
  );
  if (options.fixed !== false) await page.clock.runFor(420);
  await expect(page.locator("#game")).toHaveAttribute(
    "data-flight",
    new RegExp(`"segment":"${segment}"`),
  );
}

const views = [
  { id: "R0-winter", segment: "R0", x: 0, z: 12, text: "冬林出发" },
  { id: "R0-fork", segment: "R0", x: 0, z: 38, text: "松荫缓路" },
  { id: "R1-approach", segment: "R1", x: -13.5, z: 103, text: "车流" },
  { id: "R1-underpass", segment: "R1", x: -13.5, z: 125, text: "动物通道" },
  { id: "R1-exit", segment: "R1", x: -13.5, z: 147, text: "远侧路肩" },
  { id: "R1-gathering", segment: "R1", x: -13.5, z: 155, text: "已到远侧" },
  { id: "R2-openings", segment: "R2", x: 2, z: 258, text: "短弯 · 对正再过" },
  {
    id: "R2-S-bend",
    segment: "R2",
    x: -6,
    z: 302,
    text: "出口宽口 · 沿蹄迹转弯",
  },
  {
    id: "R3-junction",
    segment: "R3",
    x: 0,
    z: 337,
    text: "近路 · 留意尘雾时机",
  },
  { id: "R3-dust", segment: "R3", x: 17, z: 385, text: "尘雾活跃" },
  { id: "R3-shelter", segment: "R3", x: 17, z: 408, text: "背风集队地" },
  { id: "R3-greenbelt", segment: "R3", x: -47, z: 385, text: "恢复植被带" },
  { id: "R3-merge", segment: "R3", x: 0, z: 473, text: "" },
  { id: "R4-overlook", segment: "R4", x: 12, z: 545, text: "融雪观景坡" },
  { id: "R4-tundra", segment: "R4", x: 0, z: 581, text: "9 / 9" },
] as const;

const reducedViews = new Set([
  "R0-winter",
  "R1-underpass",
  "R2-openings",
  "R3-dust",
  "R3-greenbelt",
  "R4-overlook",
  "R4-tundra",
]);

test.describe("reindeer scene evidence", () => {
  test("RD-A16 touch crosses the short opening and follows the actual tail", async ({
    page,
    hasTouch,
  }, info) => {
    test.skip(!hasTouch, "requires the landscape touch project");
    await enterView(page, { x: -1, z: 259 }, "R2");
    const markers = page.locator("#marker-layer");
    await expect(page.locator("#notice")).toHaveText("前方可走宽路或短弯");
    await expect(markers.getByText("短弯 · 对正再过")).toBeVisible();
    await expect(markers.getByText("宽口 · 稳步绕行")).toBeVisible();
    await pointer(page, "pointerdown", 18, 150, 235);
    await pointer(page, "pointermove", 18, 150, 195);
    await page.clock.runFor(4300);
    await pointer(page, "pointerup", 18, 150, 195);
    await page.clock.runFor(350);
    await expect(page.locator("#notice")).toContainText("本排已通过");
    await expect(markers.getByText("队尾尚未过栏")).toBeVisible();
    await expect(markers.getByText("沿直蹄迹到这里再转")).toBeVisible();
    await pointer(page, "pointerdown", 19, 677, 175);
    await pointer(page, "pointermove", 19, 762, 183);
    await pointer(page, "pointerup", 19, 762, 183);
    await page.clock.runFor(350);
    await expect(markers.getByText("队尾尚未过栏")).toBeVisible();
    await page.screenshot({
      path: info.outputPath("R2-short-opening-tail.png"),
      scale: "css",
    });
  });

  test("RD-A16 the dust decision is readable before entering either route", async ({
    page,
    hasTouch,
  }, info) => {
    test.skip(!hasTouch, "requires the landscape touch project");
    await enterView(page, { x: 0, z: 337 }, "R3", { low: true });
    const markers = page.locator("#marker-layer");
    await expect(markers.getByText("近路 · 留意尘雾时机")).toBeVisible();
    await expect(markers.getByText("恢复带 · 更远，可补给")).toBeVisible();
    await expect(page.locator("#detail")).toContainText("入口背风地收队");
    await expect(page.locator("#game")).toHaveAttribute(
      "data-flight",
      /"route":null/,
    );
    await page.screenshot({
      path: info.outputPath("R3-fork-decision.png"),
      scale: "css",
    });
  });

  test("RD-A16 the final companion is acknowledged with reduced motion and muted audio", async ({
    page,
    hasTouch,
  }, info) => {
    test.skip(!hasTouch, "requires the landscape touch project");
    await enterView(page, { x: 0, z: 565 }, "R4", { low: true });
    await expect(page.locator("#arrival-caption")).toHaveText("等待同伴");
    await pointer(page, "pointerdown", 18, 150, 235);
    await pointer(page, "pointermove", 18, 150, 165);
    await page.clock.runFor(4300);
    await pointer(page, "pointerup", 18, 150, 165);
    await expect(page.locator("#arrived")).toHaveText("9 / 9");
    await expect(
      page.locator("#marker-layer").getByText("最后一位同伴已归队"),
    ).toBeVisible();
    await page.screenshot({
      path: info.outputPath("R4-reduced-acknowledgment.png"),
      scale: "css",
    });
  });

  const qualityViews = views.flatMap((view) =>
    (reducedViews.has(view.id) ? ["", "-low"] : [""]).map((suffix) => ({
      ...view,
      suffix,
    })),
  );
  for (const { id, segment, x, z, text, suffix } of qualityViews) {
    test(`RD-A12 ${id}${suffix} matched view`, async ({ page }, info) => {
      const renderErrors: string[] = [];
      page.on("pageerror", (error) => renderErrors.push(error.message));
      page.on("console", (message) => {
        if (
          message.type() === "error" &&
          /WebGLProgram|Shader Error/i.test(message.text())
        )
          renderErrors.push(message.text());
      });
      await enterView(page, { x, z }, segment, { low: suffix === "-low" });
      if (id === "R4-tundra") await page.clock.runFor(1840);
      if (text) await expect(page.locator("#hud")).toContainText(text);
      await page.screenshot({
        path: info.outputPath(`${id}${suffix}.png`),
        scale: "css",
      });
      const state = await page.locator("#game").getAttribute("data-flight");
      if (!state) throw new Error("Missing reindeer diagnostic state");
      await writeFile(info.outputPath(`${id}${suffix}.json`), state + "\n");
      if (id === "R1-underpass") {
        await expect(
          page.getByRole("button", { name: "等候" }),
        ).toHaveAttribute("aria-disabled", "false");
        await pointer(page, "pointerdown", 18, 686, 179);
        await pointer(page, "pointermove", 18, 246, 143);
        await pointer(page, "pointerup", 18, 246, 143);
        await page.clock.runFor(440);
        const diagnostic = JSON.parse(
          (await page.locator("#game").getAttribute("data-flight")) ?? "{}",
        ) as { camera?: { yaw: number } };
        expect(Math.abs(diagnostic.camera?.yaw ?? 0)).toBeGreaterThan(125);
        await expect(page.locator("#notice")).toHaveText("动物通道");
        await page.screenshot({
          path: info.outputPath(`R1-underpass-rear${suffix}.png`),
          scale: "css",
        });
      }
      expect(renderErrors).toEqual([]);
    });
  }

  for (const low of [false, true]) {
    for (const view of views.filter(({ id }) =>
      ["R1-approach", "R2-openings", "R3-junction", "R4-tundra"].includes(id),
    )) {
      test(`RD-A14 ${view.id} ${low ? "low" : "standard"} frame sample`, async ({
        page,
      }, info) => {
        test.setTimeout(45_000);
        // Sample R4 while waiting for the pod, before the timed ending begins.
        const z = view.id === "R4-tundra" ? 560 : view.z;
        await enterView(page, { x: view.x, z }, view.segment, {
          fixed: false,
          low,
        });
        const game = page.locator("#game");
        let frames: { samples: number } | undefined;
        await expect
          .poll(
            async () => {
              const raw = await game.getAttribute("data-performance");
              frames = raw
                ? (JSON.parse(raw) as { samples: number })
                : undefined;
              return frames?.samples ?? 0;
            },
            { timeout: 35_000 },
          )
          .toBeGreaterThanOrEqual(150);
        await writeFile(
          info.outputPath(`${view.id}-${low ? "low" : "standard"}.json`),
          JSON.stringify(frames, null, 2) + "\n",
        );
      });
    }
  }
});
