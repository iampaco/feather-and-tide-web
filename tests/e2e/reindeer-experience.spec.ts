import { expect, test, type Page } from "@playwright/test";
import type { CheckpointSnapshot, ReindeerState } from "../../src/core/game";
import { readCheckpoint } from "../../src/core/save";
import { herdAt, reindeerLevel, reindeerTrip } from "../fixtures/reindeer";
import { enterSpeciesMenu, openTitle } from "../fixtures/menu";
import { mouseOrbit } from "../fixtures/pointer";

async function seed(page: Page, checkpoint: CheckpointSnapshot): Promise<void> {
  await page.evaluate(
    (checkpoint) =>
      new Promise<void>((resolve, reject) => {
        const request = indexedDB.open("feather-tide", 1);
        request.onupgradeneeded = () =>
          request.result.createObjectStore("checkpoint");
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
          const db = request.result;
          const tx = db.transaction("checkpoint", "readwrite");
          const state = checkpoint.state;
          tx.objectStore("checkpoint").put(
            {
              kind: "checkpoint",
              version: 1,
              runId: "e".repeat(32),
              checkpoint,
              species: state.species,
              levelId: state.levelId,
              levelRevision: state.levelRevision,
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
    checkpoint,
  );
}

async function enter(page: Page): Promise<void> {
  await enterSpeciesMenu(page);
  await page.getByRole("button", { name: /^驯鹿/ }).click();
}

async function sample(
  page: Page,
): Promise<ReindeerState & { x: number; z: number }> {
  return JSON.parse(
    (await page.locator("#game").getAttribute("data-flight")) ?? "{}",
  );
}

test.describe("RD-A16 reindeer experience", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() =>
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({
          toggle: true,
          music: false,
          reduced: true,
          low: true,
        }),
      ),
    );
  });

  test("RD-A16 a real call reports actual gathering and pause releases the toggle", async ({
    page,
  }, info) => {
    await openTitle(page, "/?diagnostics");
    await enter(page);
    const ability = page.getByRole("button", { name: "等候", exact: true });
    await ability.click();
    await expect(page.locator("#notice")).toHaveText("全队已靠拢，可以出发", {
      timeout: 9000,
    });
    await expect(page.locator("#formation-status")).toContainText("9 / 9");
    await expect(ability).toHaveAttribute("data-state", "formed");
    await page.screenshot({
      path: info.outputPath("R0-real-gather.png"),
      scale: "css",
    });
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "继续旅程", exact: true }).click();
    await expect.poll(async () => (await sample(page)).waitTicks).toBe(0);
  });

  test("RD-A16 winter teaches waiting when the real trail stretches the herd", async ({
    page,
    hasTouch,
  }, info) => {
    test.skip(!hasTouch, "requires the landscape touch project");
    test.setTimeout(70_000);
    await openTitle(page, "/?diagnostics");
    await enter(page);
    await expect(page.locator("#game")).toHaveAttribute(
      "data-flight",
      /"segment":"R0"/,
    );
    await expect(page.locator("#notice")).not.toContainText("队尾拉开了");
    const now = Date.now();
    await page.clock.install({ time: now });
    await page.clock.pauseAt(now + 1000);
    await page.keyboard.down("KeyA");
    for (let i = 0; i < 14 && (await sample(page)).x < 14; i++)
      await page.clock.runFor(500);
    await page.keyboard.up("KeyA");
    expect((await sample(page)).x).toBeGreaterThanOrEqual(14);
    await page.clock.runFor(500);
    await page.keyboard.down("KeyW");
    for (let i = 0; i < 30 && (await sample(page)).z < 71; i++)
      await page.clock.runFor(850);
    await page.keyboard.up("KeyW");
    expect((await sample(page)).z).toBeGreaterThanOrEqual(71);
    await page.clock.runFor(550);
    await expect(page.locator("#notice")).toContainText("队尾拉开了");
    await expect(
      page.locator("#marker-layer").getByText("队尾", { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: info.outputPath("R0-trail-tail.png"),
      scale: "css",
    });
    await page.getByRole("button", { name: "等候", exact: true }).click();
    await page.clock.runFor(5200);
    await expect(page.locator("#formation-status")).toContainText("9 / 9");
  });

  test("RD-A16 a declared checkpoint fixture shows dust phases and a safe gathering pocket", async ({
    page,
  }, info) => {
    test.setTimeout(165_000);
    // This is an isolated render/interaction fixture, not the full journey evidence.
    const level = structuredClone(reindeerLevel);
    const checkpointZone = level.zones.find(({ id }) => id === "C1");
    if (!checkpointZone) throw new Error("Missing C1");
    const testLevel = {
      ...level,
      zones: level.zones.map((zone) =>
        zone.id === "C1"
          ? {
              ...zone,
              points: [
                { x: 5, z: 335 },
                { x: 35, z: 335 },
                { x: 35, z: 359 },
                { x: 5, z: 359 },
                { x: 5, z: 335 },
              ],
            }
          : zone,
      ),
    };
    const state = herdAt(
      { x: 17, z: 353 },
      {
        tick: 1440,
        segmentId: "R3",
        route: "dust",
        triggered: ["C1", "dust-gate"],
      },
    );
    const checkpoint = { version: 1 as const, id: "C1", state };
    expect(readCheckpoint(checkpoint, testLevel, "journey")).toBeDefined();
    await page.route("**/levels/reindeer.json", (route) =>
      route.fulfill({ json: testLevel }),
    );
    await openTitle(page, "/?diagnostics");
    await seed(page, checkpoint);
    await enter(page);
    await page.getByRole("button", { name: "从检查点继续" }).click();
    await expect(page.locator("#notice")).toContainText("尘雾活跃");
    await expect(page.locator("#detail")).toContainText("前方是背风集队地");
    await expect(page.locator("#detail")).toContainText("队尾还远");
    await page.screenshot({
      path: info.outputPath("R3-active-entry.png"),
      scale: "css",
    });
    const now = Date.now();
    await page.clock.install({ time: now });
    await page.clock.pauseAt(now + 1000);
    await page.keyboard.down("KeyW");
    for (let i = 0; i < 27 && (await sample(page)).z <= 406; i++)
      await page.clock.runFor(800);
    await page.keyboard.up("KeyW");
    expect((await sample(page)).z).toBeGreaterThan(406);
    const ability = page.getByRole("button", { name: "等候", exact: true });
    await ability.click();
    for (let i = 0; i < 4; i++) {
      await page.clock.runFor(2000);
      if ((await ability.getAttribute("data-state")) === "formed") break;
    }
    await expect(ability).toHaveAttribute("data-state", "formed");
    await expect(page.locator("#formation-status")).toContainText("9 / 9");
    await expect(page.locator("#notice")).toHaveText("全队已靠拢");
    await expect(page.locator("#detail")).toContainText("矿区出口缓坡");
    await page.screenshot({
      path: info.outputPath("R3-safe-pocket.png"),
      scale: "css",
    });
    await mouseOrbit(page, 75, 0);
    await page.clock.runFor(350);
    await page.screenshot({
      path: info.outputPath("R3-look-back.png"),
      scale: "css",
    });
    await page.keyboard.press("Escape");
    const paused = await sample(page);
    await page.clock.runFor(350);
    expect((await sample(page)).tick).toBe(paused.tick);
  });

  test("RD-A16 an old deer checkpoint explains the new map and survives returning", async ({
    page,
  }) => {
    const valid = reindeerTrip("greenbelt").checkpoints[0]!;
    const old = {
      ...valid,
      state: { ...valid.state, levelRevision: "reindeer-p3-1" },
    };
    await openTitle(page, "/?diagnostics");
    await seed(page, old);
    await enter(page);
    await expect(
      page.getByRole("heading", { name: "苔原路线已更新" }),
    ).toBeVisible();
    await expect(page.getByRole("dialog")).toContainText(
      "旧检查点不能直接继续",
    );
    await page
      .getByRole("button", { name: "返回", exact: true })
      .last()
      .click();
    const revision = await page.evaluate(
      () =>
        new Promise<unknown>((resolve, reject) => {
          const request = indexedDB.open("feather-tide", 1);
          request.onsuccess = () => {
            const db = request.result;
            const read = db
              .transaction("checkpoint")
              .objectStore("checkpoint")
              .get(["reindeer", "reindeer", "journey"]);
            read.onsuccess = () => {
              resolve(read.result?.levelRevision);
              db.close();
            };
            read.onerror = () => reject(read.error);
          };
          request.onerror = () => reject(request.error);
        }),
    );
    expect(revision).toBe("reindeer-p3-1");
  });
});
