import { writeFile } from "node:fs/promises";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import type { GamePhase, WhaleState } from "../../src/core/game";
import { angleDelta, type Vec2 } from "../../src/core/math";
import type { Basis } from "../../src/input/input";
import { contains } from "../../src/levels/geometry";
import { currentGuide } from "../../src/levels/whale-current";
import { kelpApproaches } from "../../src/levels/whale-kelp";
import type { ReefView } from "../../src/rendering/whale-reef";
import { WHALE } from "../../src/simulation/whale-motion";
import { enterSpeciesMenu, openMenu } from "../fixtures/menu";
import { mouseOrbit, pointer } from "../fixtures/pointer";
import {
  kelpForkFromC1,
  netApproachForBrowser,
  netRecoveryBend,
  podAt,
  whaleLevel,
  whaleTrip,
} from "../fixtures/whale";

function whaleEntry(page: Page) {
  return page.locator('[data-action="whale"]');
}

async function selectWhale(page: Page, path = "/?diagnostics") {
  await openMenu(page, path);
  await enterWhaleChapter(page);
}

async function enterWhaleChapter(page: Page) {
  await whaleEntry(page).click();
}

async function start(page: Page) {
  await expect(page.locator("#hud")).toBeVisible();
  await expect(page.locator("#formation")).toHaveAccessibleName(/下潜/);
}

interface SwimDiagnostic {
  readonly phase: GamePhase;
  readonly tick: number;
  readonly speed: number;
  readonly energy: number;
  readonly heading: number;
  readonly x: number;
  readonly z: number;
  readonly route: string | null;
  readonly reef?: ReefView;
  readonly camera: { readonly yaw: number };
  readonly basis: Basis;
  readonly segment: string;
  readonly actors?: WhaleState["actors"];
  readonly checkpoint: string;
  readonly occupied: readonly string[];
  readonly framedWhales?: number;
  readonly landingProgress?: number;
  readonly scenery: Readonly<Record<string, string>>;
}

async function sample(page: Page): Promise<SwimDiagnostic> {
  const value = await page.locator("#game").getAttribute("data-flight");
  if (!value) throw new Error("Missing swim diagnostics");
  return JSON.parse(value);
}

function depth(page: Page) {
  return page.locator("#whale-depth");
}

async function swimToZ(page: Page, target: number) {
  let state = await sample(page);
  for (let step = 0; step < 100 && state.z < target; step++) {
    const ms = ((target - state.z) * 1000) / WHALE.boost;
    await page.clock.runFor(Math.max(80, Math.min(1300, Math.floor(ms))));
    state = await sample(page);
  }
  expect(state.z).toBeGreaterThanOrEqual(target);
  return state;
}

async function swimOutOfBay(page: Page, targetZ: number, offset = 0) {
  const x = 140;
  const y = 290;
  await pointer(page, "pointerdown", 51, x, y);
  await pointer(page, "pointermove", 51, x + offset, y - 56);
  const arrival = await swimToZ(page, targetZ);
  await pointer(page, "pointerup", 51, x + offset, y - 56);
  return arrival;
}

test("WH-A11 whale entry is available on the species menu", async ({
  page,
}) => {
  await openMenu(page);
  await expect(page.locator('[data-start="journey"]')).toBeVisible();
  await expect(whaleEntry(page)).toBeVisible();
  await expect(whaleEntry(page)).toBeEnabled();
});

test.describe("Whale journey controls", () => {
  test("WH-A11 starts a voyage while the browser audio clock is unavailable", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({ music: false }),
      );
      Object.defineProperty(AudioContext.prototype, "currentTime", {
        get: () => Number.NaN,
        configurable: true,
      });
    });
    await selectWhale(page);
    await start(page);
    await expect.poll(async () => (await sample(page)).tick).toBeGreaterThan(0);
  });

  test("WH-A01 W0 skips the lesson and takes the direct route to W1", async ({
    page,
  }, info) => {
    test.setTimeout(150_000);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.addInitScript(() =>
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({ low: true, reduced: true, music: false }),
      ),
    );
    await page.clock.install();
    await selectWhale(page);
    await start(page);
    await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 1500);
    const cue = page.locator("#flight-cue");
    await expect(cue).toHaveAttribute("data-kind", "tutorial");
    await expect(page.locator("#notice")).toContainText(/起游|游动/);
    await expect(page.locator("#whale-depth")).toHaveText("水面");
    await expect(
      page.getByText("海蚀拱内湾 · 练习滑停", { exact: true }),
    ).toBeVisible();
    await page.locator("#dismiss-tips").dispatchEvent("click");
    await page.clock.runFor(32);
    await expect(page.locator("#dismiss-tips")).toBeHidden();
    await expect(page.locator("#notice")).toHaveText("");
    await expect(page.getByText("出湾航标", { exact: true })).toBeVisible();
    await expect(
      page.getByText("海蚀拱内湾 · 练习滑停", { exact: true }),
    ).toBeHidden();
    await page.screenshot({
      path: info.outputPath("06-skip-direct.png"),
      scale: "css",
    });
    await swimOutOfBay(page, 304);
    const arrival = await sample(page);
    expect(Math.abs(arrival.x)).toBeLessThan(1);
    expect(arrival).toMatchObject({
      segment: "W1",
      occupied: ["waiting-water", "ship-approach-breakwater-warning"],
    });
    expect(arrival.actors?.map(({ dive }) => dive.breath)).toEqual(
      Array(6).fill(1),
    );
    await expect(
      page.getByText("沿浮标绕防波堤", { exact: true }),
    ).toBeVisible();
    await expect(page.locator("#hazard-notice")).toContainText("湾口防波堤");
    await page.screenshot({
      path: info.outputPath("07-shipping-approach.png"),
    });
  });

  test("WH-A03 W0 coasts, looks back, practices surfacing and leads six whales to waiting water", async ({
    page,
    isMobile,
  }, info) => {
    test.setTimeout(150_000);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.addInitScript(
      (touch) =>
        localStorage.setItem(
          "feather-tide-settings-v1",
          JSON.stringify({
            toggle: touch,
            low: touch,
            reduced: touch,
            music: false,
          }),
        ),
      isMobile,
    );
    // Freeze before entering W0, so a busy rendering worker cannot pass the pause instant.
    const epoch = Date.UTC(2026, 0, 1);
    await openMenu(page, "/?diagnostics");
    await page.clock.install({ time: epoch });
    await page.clock.pauseAt(epoch + 30_000);
    await whaleEntry(page).dispatchEvent("click");
    await start(page);
    await page.clock.runFor(240);
    const notice = page.locator("#notice");
    const markerLayer = page.locator("#marker-layer");
    const shot = (name: string) =>
      page.screenshot({ path: info.outputPath(name), scale: "css" });
    await shot("01-bay-arrival.png");
    if (isMobile) {
      await pointer(page, "pointerdown", 41, 140, 290);
      await pointer(page, "pointermove", 41, 148, 245);
    } else await page.keyboard.down("KeyW");
    await page.clock.runFor(2260);
    const moving = await sample(page);
    expect(moving.speed).toBeGreaterThan(4);
    await expect(notice).toContainText("滑行至停稳");
    if (isMobile) await pointer(page, "pointerup", 41, 148, 245);
    else await page.keyboard.up("KeyW");
    await page.clock.runFor(2600);
    const stopped = await sample(page);
    expect(stopped.speed).toBe(0);
    expect(stopped.z - moving.z).toBeGreaterThan(2);
    await expect(notice).toContainText("观察队尾");

    const lookBack = async (id: number) => {
      if (!isMobile) await mouseOrbit(page, -420, 0);
      else {
        await pointer(page, "pointerdown", id, 680, 202);
        await pointer(page, "pointermove", id, 248, 202);
        await pointer(page, "pointerup", id, 248, 202);
      }
    };
    const reset = async () => {
      if (!isMobile) await page.keyboard.press("KeyR");
      else await page.locator("#camera-reset").dispatchEvent("click");
    };
    await reset();
    await lookBack(42);
    await page.clock.runFor(780);
    await expect(markerLayer).toHaveAttribute("data-camera", "Explore");
    await expect(notice).toHaveText(
      isMobile ? "轻触镜头复位" : "按 R 复位镜头",
    );
    const looking = await sample(page);
    expect(Math.abs(looking.camera.yaw)).toBeGreaterThan(90);
    expect([looking.x, looking.z, looking.heading]).toEqual([
      stopped.x,
      stopped.z,
      stopped.heading,
    ]);
    await shot("02-stopped-look-back.png");
    await reset();
    await page.clock.runFor(780);
    await expect(markerLayer).toHaveAttribute("data-camera", "Follow");
    await expect(notice).toContainText(isMobile ? "点按" : "按住");

    const box = await page.locator("#formation").boundingBox();
    if (!box) throw new Error("Missing dive control");
    const tap = async (id: number) => {
      const x = box.x + box.width / 2;
      const y = box.y + box.height / 2;
      await pointer(page, "pointerdown", id, x, y, "#formation");
      await pointer(page, "pointerup", id, x, y, "#formation");
    };
    if (isMobile) await tap(43);
    else await page.keyboard.down("Space");
    await page.clock.runFor(1980);
    await expect(depth(page)).toHaveText("浅潜");
    await expect(notice).toContainText(isMobile ? "再点按" : "松开");
    await shot("03-shallow-dive.png");

    if (isMobile) await tap(44);
    else await page.keyboard.up("Space");
    await lookBack(45);
    await page.clock.runFor(1190);
    for (
      let step = 0;
      step < 11 && (await depth(page).textContent()) !== "水面";
      step++
    )
      await page.clock.runFor(48);
    await expect(notice).toHaveText("领鲸已浮出水面");
    await expect(page.locator("#whale-depth-cue")).toHaveText("正在换气");
    await expect(
      page.getByText("队尾 · 正在上浮", { exact: true }),
    ).toBeVisible();
    const breathing = await sample(page);
    expect(breathing.actors?.[0]?.dive.breath).toBeLessThan(1);
    expect(breathing.actors?.at(-1)?.dive.direction).toBe("up");
    await shot("04-surfacing-with-tail.png");
    await page.clock.runFor(1640);
    await expect(notice).toHaveText("可以出湾了");
    expect(
      (await sample(page)).actors?.every(
        ({ dive }) => dive.breath === 1 && !dive.direction,
      ),
    ).toBe(true);

    await reset();
    await page.clock.runFor(780);
    await swimOutOfBay(page, 106, 13);
    await expect(page.getByText("出湾航标", { exact: true })).toBeVisible();
    await swimOutOfBay(page, 304, -9);
    const arrival = await sample(page);
    expect(arrival).toMatchObject({
      segment: "W1",
      occupied: ["waiting-water", "ship-approach-breakwater-warning"],
    });
    expect(
      arrival.actors?.filter(
        ({ dive, pos }) => dive.layer === "surface" && pos.z >= 270,
      ),
    ).toHaveLength(6);
    await expect(notice).toHaveText("");
    await expect(
      page.getByText("沿浮标绕防波堤", { exact: true }),
    ).toBeVisible();
    await shot("05-into-w1.png");
  });

  test("WH-A02 paired A/B camera mapping preserves the whale turn limit and coast", async ({
    page,
    isMobile,
  }, info) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.clock.install();
    const at = async (ms: number) => {
      await page.clock.runFor(ms);
      return sample(page);
    };
    async function trial(mapping: "A" | "B") {
      await openMenu(page, "/?diagnostics");
      await page.getByRole("button", { name: "设置", exact: true }).click();
      await page.getByLabel("移动方向").selectOption(mapping);
      await page.getByRole("button", { name: "返回", exact: true }).click();
      await enterWhaleChapter(page);
      await start(page);
      await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 500);
      await pointer(page, "pointerdown", 31, 140, 290);
      await pointer(page, "pointermove", 31, 140, 244);
      const straight = await at(640);
      await pointer(page, "pointerdown", 32, 650, 180);
      await pointer(page, "pointermove", 32, 530, 180);
      await pointer(page, "pointerup", 32, 530, 180);
      const turning = await at(320);
      const orbit = await at(850);
      await pointer(page, "pointerup", 31, 140, 244);
      const stopped = await at(3200);
      await page.locator("#camera-reset").dispatchEvent("click");
      const reset = await at(720);
      await page.clock.resume();
      return { straight, turning, orbit, stopped, reset };
    }
    const order = isMobile ? (["B", "A"] as const) : (["A", "B"] as const);
    const first = await trial(order[0]);
    const second = await trial(order[1]);
    const { A, B } = isMobile
      ? { A: second, B: first }
      : { A: first, B: second };
    for (const { straight, turning, orbit, stopped, reset } of [A, B]) {
      expect(straight.heading).toBeCloseTo(0, 8);
      expect(
        Math.abs(angleDelta(straight.heading, turning.heading)),
      ).toBeLessThanOrEqual(
        ((turning.tick - straight.tick) * WHALE.turnRate) / 60 + 1e-8,
      );
      expect(orbit.camera.yaw).toBeGreaterThan(30);
      expect(stopped.heading).toBeCloseTo(orbit.heading, 8);
      expect(stopped.speed).toBe(0);
      expect(reset.camera.yaw).toBeCloseTo(0, 1);
      expect([reset.x, reset.z, reset.heading]).toEqual([
        stopped.x,
        stopped.z,
        stopped.heading,
      ]);
    }
    expect(A.turning.heading).toBeGreaterThan(0.1);
    expect(B.turning.heading).toBeCloseTo(0, 8);
    expect(A.orbit.x - B.orbit.x).toBeGreaterThan(1);
    const evidence = info.outputPath("W0-mapping-samples.json");
    await writeFile(evidence, JSON.stringify({ order, A, B }, null, 2) + "\n");
    await info.attach("W0-mapping-samples", {
      path: evidence,
      contentType: "application/json",
    });
  });

  test("WH-A01 desktop keyboard-only movement, dive, orbit and pause", async ({
    page,
    isMobile,
  }, info) => {
    test.skip(isMobile, "uses keyboard and mouse");
    await selectWhale(page);
    await start(page);
    await expect(depth(page)).toContainText("水面");
    const initial = await sample(page);
    expect(initial.scenery["WL-CHR-001"]).toBe("model");
    await page.keyboard.down("KeyW");
    await page.keyboard.down("Space");
    await expect(depth(page)).toContainText("浅潜");
    await expect
      .poll(async () => (await sample(page)).z)
      .toBeGreaterThan(initial.z + 2);
    await mouseOrbit(page, 175, -25);
    await expect(page.locator("#marker-layer")).toHaveAttribute(
      "data-camera",
      "Explore",
    );
    await expect(page.locator("#formation")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(depth(page)).toContainText("深潜");
    await page.screenshot({
      path: info.outputPath("W0-deep-orbit.png"),
      scale: "css",
    });
    await page.keyboard.press("KeyR");
    await expect(page.locator("#marker-layer")).toHaveAttribute(
      "data-camera",
      "Follow",
    );

    await page.keyboard.press("Escape");
    await expect.poll(async () => (await sample(page)).phase).toBe("paused");
    const paused = await sample(page);
    const pausedText = await depth(page).textContent();
    await page.evaluate(
      () =>
        new Promise<void>((resolve) => {
          requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
        }),
    );
    expect((await sample(page)).tick).toBe(paused.tick);
    expect(await depth(page).textContent()).toBe(pausedText);
    await page.keyboard.up("Space");
    await page.keyboard.up("KeyW");
    const dialog = page.locator("#panel");
    await dialog.getByRole("button", { name: /继续/ }).click();
    await expect.poll(async () => (await sample(page)).phase).toBe("playing");
    await expect(depth(page)).toContainText("水面");
    await expect(page.locator("#formation")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  test("WH-A01 two pointers retain independent movement, observation and dive responsibilities", async ({
    page,
  }, info) => {
    await page.addInitScript(() =>
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({ reduced: true }),
      ),
    );
    await page.setViewportSize({ width: 852, height: 393 });
    await selectWhale(page);
    await start(page);
    const ability = page.locator("#formation");
    const box = await ability.boundingBox();
    if (!box) throw new Error("Missing dive control");
    const abilityX = box.x + box.width / 2;
    const abilityY = box.y + box.height / 2;
    await pointer(page, "pointerdown", 1, 130, 260);
    await pointer(page, "pointermove", 1, 130, 211);
    await pointer(page, "pointerdown", 2, 640, 182);
    await pointer(page, "pointermove", 2, abilityX, abilityY, "#formation");
    await expect(page.locator("#stick")).toBeVisible();
    await expect(page.locator("#marker-layer")).toHaveAttribute(
      "data-camera",
      "Explore",
    );
    await expect(ability).toHaveAttribute("aria-pressed", "false");
    await pointer(page, "pointerup", 2, abilityX, abilityY);
    const yaw = (await sample(page)).camera.yaw;
    await pointer(page, "pointerdown", 3, abilityX, abilityY, "#formation");
    await pointer(page, "pointermove", 3, 645, 164);
    await expect(ability).toHaveAttribute("aria-pressed", "true");
    await expect(depth(page)).toContainText("浅潜");
    await expect(page.locator("#stick")).toBeVisible();
    await expect
      .poll(async () => (await sample(page)).speed)
      .toBeGreaterThan(2);
    expect((await sample(page)).camera.yaw).toBe(yaw);
    await page.screenshot({
      path: info.outputPath("W0-dual-hand.png"),
      scale: "css",
    });
    await pointer(page, "pointercancel", 3, 645, 164);
    await expect(ability).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#stick")).toBeHidden();
    await expect(depth(page)).toContainText("水面");
  });

  test("WH-A01 mirror, larger control, tap-to-dive and portrait interruption", async ({
    page,
    isMobile,
  }, info) => {
    test.skip(!isMobile, "uses coarse-pointer orientation and mirrored touch");
    await page.addInitScript(() =>
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({
          mirror: true,
          large: true,
          toggle: true,
          reduced: true,
          low: true,
          music: false,
        }),
      ),
    );
    await page.setViewportSize({ width: 852, height: 393 });
    await selectWhale(page);
    await start(page);
    const ability = page.locator("#formation");
    const box = await ability.boundingBox();
    if (!box) throw new Error("Missing mirror control");
    expect(box.x + box.width / 2).toBeLessThan(426);
    expect(box.width).toBeGreaterThanOrEqual(64);
    await pointer(page, "pointerdown", 1, 731, 290);
    await pointer(page, "pointermove", 1, 731, 240);
    await pointer(page, "pointerdown", 2, box.x + 20, box.y + 20, "#formation");
    await pointer(page, "pointerup", 2, box.x + 20, box.y + 20, "#formation");
    await expect(ability).toHaveAttribute("aria-pressed", "true");
    await expect(depth(page)).toContainText("浅潜");
    await expect(page.locator("#stick")).toBeVisible();
    await page.screenshot({
      path: info.outputPath("W0-mirror-low.png"),
      scale: "css",
    });

    await page.setViewportSize({ width: 393, height: 852 });
    await expect.poll(async () => (await sample(page)).phase).toBe("paused");
    const paused = await sample(page);
    await page.setViewportSize({ width: 852, height: 393 });
    await expect(ability).toHaveAttribute("aria-pressed", "false");
    expect((await sample(page)).tick).toBe(paused.tick);
    await page.locator("#panel").getByRole("button", { name: /继续/ }).click();
    await expect(depth(page)).toContainText("水面");
    await expect(page.locator("#stick")).toBeHidden();
  });
});

async function seedWhale(
  page: Page,
  state: WhaleState,
  id: "C1" | "C2",
  runId = "d1064fac819444e7b88b4bc1812d22a4",
) {
  await page.evaluate(
    ({ state, id, runId }) =>
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
              species: state.species,
              levelId: state.levelId,
              levelRevision: state.levelRevision,
              mode: state.mode,
              version: 1,
              runId,
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
    { state, id, runId },
  );
}

async function openWhaleArtView(
  page: Page,
  state: WhaleState,
  checkpoint: "C1" | "C2",
  settings: { low?: boolean; reduced?: boolean } = {},
) {
  await page.setViewportSize({ width: 852, height: 393 });
  await page.addInitScript((settings) => {
    localStorage.setItem(
      "feather-tide-settings-v1",
      JSON.stringify({ music: false, ...settings }),
    );
  }, settings);
  await openMenu(page, "/?diagnostics");
  await seedWhale(page, state, checkpoint);
  await enterWhaleChapter(page);
  const resume = page.getByRole("button", { name: "从检查点继续" });
  await expect(resume).toBeVisible({ timeout: 20_000 });
  const epoch = Date.UTC(2026, 0, 1);
  await page.clock.install({ time: epoch });
  await page.clock.pauseAt(epoch + 30_000);
  await resume.dispatchEvent("click");
  await start(page);
}

async function captureWhaleArt(page: Page, info: TestInfo, name: string) {
  await writeFile(
    info.outputPath(`${name}.json`),
    JSON.stringify(await sample(page), null, 2) + "\n",
  );
  await page.screenshot({ path: info.outputPath(`${name}.png`), scale: "css" });
}

async function turnWhaleCamera(page: Page, endX: number, endY: number) {
  await pointer(page, "pointerdown", 76, 711, 178);
  await pointer(page, "pointermove", 76, endX, endY);
  await pointer(page, "pointerup", 76, endX, endY);
  await page.clock.runFor(480);
}

function offshorePod(position: Vec2): WhaleState {
  const checkpoint = whaleTrip("journey", "quiet").checkpoints[1];
  if (!checkpoint || checkpoint.state.species !== "whale")
    throw new Error("Missing C2");
  return {
    ...checkpoint.state,
    segmentId: "W4",
    actors: podAt(position).actors,
  };
}

test.describe("Whale voyage pacing", () => {
  test("WH-A03 W0 borrows the optional current and reads the ship before leaving the bay", async ({
    page,
  }, info) => {
    test.setTimeout(80_000);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.addInitScript(() =>
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({ music: false, low: true, reduced: true }),
      ),
    );
    await page.clock.install();
    await openMenu(page, "/?diagnostics");
    await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 100);
    await enterWhaleChapter(page);
    await start(page);
    await page.locator("#dismiss-tips").dispatchEvent("click");
    await page.clock.runFor(200);
    await swimOutOfBay(page, 132, -11);
    await expect(
      page.getByText("顺流入口 · 可选", { exact: true }),
    ).toBeVisible();
    const box = await page.locator("#formation").boundingBox();
    if (!box) throw new Error("Missing dive control");
    const diveX = box.x + box.width / 2;
    const diveY = box.y + box.height / 2;
    await pointer(page, "pointerdown", 53, diveX, diveY, "#formation");
    await pointer(page, "pointerdown", 54, 140, 290);
    await pointer(page, "pointermove", 54, 140, 242);
    const flow = await swimToZ(page, 163);
    expect(flow.occupied).toContain("bay-current");
    await expect(page.locator("#notice")).toHaveText("正在借流");
    await captureWhaleArt(page, info, "W0-bay-current");
    await swimToZ(page, 196);
    await pointer(page, "pointerup", 53, diveX, diveY, "#formation");
    await pointer(page, "pointerup", 54, 140, 242);
    await page.clock.runFor(1100);
    await expect(page.locator("#notice")).toHaveText("湾口亮水");
    await page.clock.runFor(3500);
    expect(
      (await sample(page)).actors?.every(
        ({ dive }) => dive.layer === "surface" && dive.direction === null,
      ),
    ).toBe(true);
    const mouth = await swimOutOfBay(page, 226);
    expect(mouth.segment).toBe("W0");
    await expect(page.getByText(/湾外货船 · 向[东西]/)).toBeVisible();
    await expect(page.locator("#hazard-cue")).toBeHidden();
    await captureWhaleArt(page, info, "W0-ship-preview");
    expect((await swimOutOfBay(page, 305)).segment).toBe("W1");
    await expect(page.locator("#hazard-cue")).toBeVisible();
  });

  test("WH-A03 W0 meets a reactive silverfish shoal on the direct route", async ({
    page,
  }, info) => {
    test.setTimeout(80_000);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.addInitScript(() => {
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({ music: false }),
      );
    });
    await page.clock.install();
    await openMenu(page, "/?diagnostics");
    await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 100);
    await enterWhaleChapter(page);
    await start(page);
    await page.locator("#dismiss-tips").dispatchEvent("click");
    await page.clock.runFor(200);
    const shoal = whaleLevel.landmarks.find(({ id }) => id === "bay-shoal");
    if (!shoal) throw new Error("Missing opening silverfish shoal");
    const departure = (await sample(page)).tick;
    const approach = await swimOutOfBay(page, shoal.pos.z - 10);
    expect(approach.tick - departure).toBeLessThan(12 * 60);
    expect(approach.speed).toBeGreaterThan(8);
    await expect(page.locator("#notice")).toHaveText("银鱼群");
    expect((await sample(page)).reef?.fish).toBe(22);

    const dive = page.locator("#formation");
    const box = await dive.boundingBox();
    if (!box) throw new Error("Missing dive control");
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await pointer(page, "pointerdown", 52, x, y, "#formation");
    await page.clock.runFor(1120);
    await expect(depth(page)).toHaveText("浅潜");
    const passing = (await sample(page)).reef?.spread.at(-1) ?? 0;
    expect(passing).toBeGreaterThan(0.1);
    await captureWhaleArt(page, info, "W0-silverfish");

    await pointer(page, "pointerup", 52, x, y, "#formation");
    await page.clock.runFor(4000);
    const stopped = await sample(page);
    expect(stopped.speed).toBe(0);
    expect(stopped.reef?.spread.at(-1)).toBeLessThan(passing * 0.5);
    await expect(depth(page)).toHaveText("水面");
  });

  test("WH-A06 W2 replenishes a regrouped pod at the kelp shelter", async ({
    page,
  }, info) => {
    const pod = podAt({ x: 38, z: 876 });
    await openWhaleArtView(
      page,
      { ...pod, segmentId: "W2", triggered: ["C1"], energy: 0.42 },
      "C1",
      { low: true, reduced: true },
    );
    await page.clock.runFor(300);
    await expect(page.locator("#notice")).toHaveText("海藻湾");
    await expect(page.locator("#detail")).toContainText("正在补给");
    await captureWhaleArt(page, info, "W2-kelp-shelter");
    await page.clock.runFor(3100);
    expect((await sample(page)).energy).toBeCloseTo(0.8);
    await expect(page.locator("#detail")).toHaveText("进湾 6/6 · 补给已用完");
  });

  test("WH-A10 W4 borrows the offshore current with two pointers in silence", async ({
    page,
  }, info) => {
    await openWhaleArtView(page, offshorePod({ x: 97, z: 1395 }), "C2", {
      low: true,
    });
    await page.clock.runFor(240);
    await expect(page.locator("#notice")).toHaveText("外海顺流带");
    const box = await page.locator("#formation").boundingBox();
    if (!box) throw new Error("Missing dive control");
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await pointer(page, "pointerdown", 75, x, y, "#formation");
    await page.clock.runFor(1100);
    await pointer(page, "pointerdown", 76, 142, 288);
    await pointer(page, "pointermove", 76, 142, 240);
    await page.clock.runFor(3100);
    const assisted = await sample(page);
    expect(assisted.occupied).toContain("offshore-current");
    await expect(page.locator("#notice")).toHaveText("正在借流");
    await captureWhaleArt(page, info, "W4-offshore-current");
    await pointer(page, "pointerup", 75, x, y, "#formation");
    await swimToZ(page, 1466);
    await pointer(page, "pointerup", 76, 142, 240);
    const clear = await sample(page);
    expect(clear.occupied).toContain("offshore-rest");
    expect(clear.occupied).not.toContain("offshore-current");
    expect(clear.actors?.every(({ dive }) => dive.depth === 0)).toBe(true);
  });
});

test.describe("Whale course art comparison", () => {
  const renderErrors = new WeakMap<Page, string[]>();
  test.beforeEach(({ page }) => {
    const errors: string[] = [];
    renderErrors.set(page, errors);
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (
        message.type() === "error" &&
        /WebGLProgram|Shader Error/i.test(message.text())
      )
        errors.push(message.text());
    });
  });

  test.afterEach(({ page }) => {
    expect(renderErrors.get(page)).toEqual([]);
  });

  for (const [name, position, firstTick] of [
    ["east", { x: 0, z: 372 }, 890],
    ["west", { x: 0, z: 372 }, 3310],
    ["deep", { x: 0, z: 418 }, 3600],
    ["mixed-depth", { x: 0, z: 418 }, 3600],
    ["look-back", { x: 0, z: 393 }, 3460],
  ] as const) {
    test(`WH-A12 course art W1 ${name}`, async ({ page }, info) => {
      test.setTimeout(60_000);
      const pod = podAt(position, "journey", firstTick - 23);
      const submerged = name === "deep" || name === "mixed-depth";
      await openWhaleArtView(
        page,
        {
          ...pod,
          segmentId: "W1",
          triggered: ["C1"],
          actors: submerged
            ? pod.actors.map((actor, index) => {
                const shallow =
                  name === "mixed-depth" && index === pod.actors.length - 1;
                return {
                  ...actor,
                  dive: {
                    ...actor.dive,
                    layer: shallow ? "shallow" : "deep",
                    depth: shallow ? 1 : 2,
                  },
                };
              })
            : pod.actors,
        },
        "C1",
        name === "look-back" ? { low: true, reduced: true } : {},
      );
      for (
        let frame = 0;
        frame < 32 && (await sample(page)).tick < firstTick;
        frame++
      )
        await page.clock.runFor(16);
      expect((await sample(page)).tick).toBe(firstTick);
      if (name === "east" || name === "west") {
        await expect(
          page.getByText(`货船 · 向${name === "east" ? "东" : "西"}`, {
            exact: true,
          }),
        ).toBeVisible();
      } else if (submerged) {
        await expect(depth(page)).toHaveText("深潜");
        expect((await sample(page)).occupied).not.toContain("cargo-ship");
        const warning = await page.locator("#hazard-cue").boundingBox();
        const game = await page.locator("#game").boundingBox();
        if (!warning || !game) throw new Error("Missing W1 warning layout");
        // This fixture centers the hull. Leave its entire central region free.
        expect(
          warning.x + warning.width < game.x + game.width * 0.39 ||
            warning.x > game.x + game.width * 0.61,
        ).toBe(true);
        if (name === "mixed-depth") {
          await expect(page.locator("#warning-detail")).toContainText(
            "队尾仍在浅潜",
          );
          await expect(
            page.getByText("队尾 · 浅潜", { exact: true }),
          ).toBeVisible();
        }
      } else {
        await turnWhaleCamera(page, 306, 173);
        await expect(page.locator("#hazard-cue")).toBeVisible();
      }
      await captureWhaleArt(page, info, `W1-${name}`);
    });
  }

  test("WH-A12 course art W2 gap through three layers", async ({
    page,
  }, info) => {
    await openWhaleArtView(
      page,
      {
        ...podAt({ x: 75, z: 739 }, "journey", 8250),
        segmentId: "W2",
        triggered: ["C1"],
      },
      "C1",
    );
    await page.clock.runFor(400);
    const gap = page.getByText("短网口 · 对准后缓游", { exact: true });
    await expect(gap).toBeVisible();
    async function expectClearOpening() {
      const viewport = page.viewportSize();
      const card = await page.locator("#flight-cue").boundingBox();
      if (!viewport || !card) throw new Error("Missing W2 layout");
      const middle = viewport.width / 2;
      expect(card.x > middle + 38 || card.x + card.width < middle - 38).toBe(
        true,
      );
    }
    await expectClearOpening();
    await captureWhaleArt(page, info, "W2-surface");
    const box = await page.locator("#formation").boundingBox();
    if (!box) throw new Error("Missing dive control");
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await pointer(page, "pointerdown", 77, x, y, "#formation");
    for (const [view, label, duration] of [
      ["shallow", "浅潜", 1200],
      ["deep", "深潜", 2300],
    ] as const) {
      await page.clock.runFor(duration);
      await expect(depth(page)).toHaveText(label);
      await expect(gap).toBeVisible();
      await expectClearOpening();
      expect((await sample(page)).occupied).not.toContain("drift-net");
      expect((await sample(page)).occupied).not.toContain("net-divider");
      await captureWhaleArt(page, info, `W2-${view}`);
    }
  });

  test("W1 to W2 keeps both overlapping edge labels readable", async ({
    page,
  }, info) => {
    const pod = podAt({ x: 7, z: 574 }, "journey", 3840);
    await openWhaleArtView(
      page,
      { ...pod, segmentId: "W1", triggered: ["C1"] },
      "C1",
    );
    await page.clock.runFor(260);
    const short = page.getByText("短口前 · 提前对准", { exact: true });
    const wide = page.getByText("外侧弧线 · 向静水", { exact: true });
    await expect(short).toBeVisible();
    await expect(wide).toBeVisible();
    const a = await short.boundingBox();
    const b = await wide.boundingBox();
    if (!a || !b) throw new Error("Missing one of the net choices");
    expect(
      a.x + a.width <= b.x ||
        b.x + b.width <= a.x ||
        a.y + a.height <= b.y ||
        b.y + b.height <= a.y,
    ).toBe(true);
    await captureWhaleArt(page, info, "W1-two-net-choices");
  });

  test("WH-A12 course art W2 look back beyond the gap", async ({
    page,
  }, info) => {
    await openWhaleArtView(
      page,
      {
        ...podAt({ x: 94, z: 804 }, "journey", 8710),
        segmentId: "W2",
        triggered: ["C1"],
      },
      "C1",
      { low: true, reduced: true },
    );
    await page.clock.runFor(400);
    await turnWhaleCamera(page, 256, 156);
    expect((await sample(page)).camera.yaw).toBeGreaterThan(145);
    await captureWhaleArt(page, info, "W2-look-back");
  });

  test("WH-A13 W3 near route reaches the dredging choices and clear water in silence", async ({
    page,
  }, info) => {
    test.setTimeout(90_000);
    const state = podAt({ x: 69, z: 1038 }, "journey", 11_330);
    await openWhaleArtView(
      page,
      { ...state, segmentId: "W3", triggered: ["C1"] },
      "C1",
      {
        low: true,
        reduced: true,
      },
    );
    await page.clock.runFor(240);
    await pointer(page, "pointerdown", 81, 142, 288);
    await pointer(page, "pointermove", 81, 142, 227);
    const entrance = await swimToZ(page, 1167);
    expect(entrance.route).toBe("shipping");
    await expect(page.locator("#notice")).toHaveText("港口疏浚区");
    await expect(page.locator("#detail")).toContainText("清水边缘");
    await captureWhaleArt(page, info, "W3-dredging-entrance");
    const clearing = await swimToZ(page, 1250);
    await pointer(page, "pointerup", 81, 142, 227);
    expect(clearing.occupied).toContain("dredge-rest");
    expect(clearing.actors?.map(({ status }) => status)).toEqual(
      Array(6).fill("following"),
    );
    await expect(page.locator("#notice")).toHaveText("疏浚区外 · 清水换气");
  });

  test("WH-A13 W4 previews the breakwater and applies sideways drift with touch controls", async ({
    page,
  }, info) => {
    test.setTimeout(70_000);
    await openWhaleArtView(page, offshorePod({ x: 58, z: 1395 }), "C2", {
      low: true,
      reduced: true,
    });
    await page.clock.runFor(240);
    await expect(page.locator("#notice")).toHaveText("防波堤横流");
    await expect(page.locator("#detail")).toContainText("外侧宽水面");
    await captureWhaleArt(page, info, "W4-breakwater-preview");
    await pointer(page, "pointerdown", 82, 142, 288);
    await pointer(page, "pointermove", 82, 142, 227);
    const crossing = await swimToZ(page, 1439);
    expect(crossing.x).toBeGreaterThan(60);
    expect(crossing.occupied).toContain("breakwater-cross-current");
    await expect(page.locator("#notice")).toHaveText("正在穿越横流");
    await captureWhaleArt(page, info, "W4-breakwater-crossing");
    const cleared = await swimToZ(page, 1464);
    await pointer(page, "pointerup", 82, 142, 227);
    expect(cleared.occupied).not.toContain("breakwater-cross-current");
    expect(cleared.occupied).not.toContain("offshore-breakwater");
    expect(cleared.checkpoint).toBe("C2");
  });

  test("WH-A12 course art W4 approach through the optional watching reach", async ({
    page,
  }, info) => {
    await openWhaleArtView(page, offshorePod({ x: 100, z: 1482 }), "C2");
    await page.clock.runFor(400);
    await expect(page.locator("#notice")).toHaveText(
      /观鲸船减速区 · 水面 [1-6]\/6/,
    );
    await expect(page.locator("#detail")).toContainText("滑停等队尾");
    await expect(page.locator("#arrival-status")).toBeHidden();
    await captureWhaleArt(page, info, "W4-watching-reach");
  });

  test("W4 shows six ready whales and waits for the player's glide to stop", async ({
    page,
  }, info) => {
    const pod = offshorePod({ x: 80, z: 1545 });
    await openWhaleArtView(
      page,
      {
        ...pod,
        actors: pod.actors.map((actor) => ({ ...actor, speed: WHALE.boost })),
      },
      "C2",
    );
    await pointer(page, "pointerdown", 82, 142, 288);
    await pointer(page, "pointermove", 82, 142, 227);
    await page.clock.runFor(670);
    await expect(page.locator("#arrived")).toHaveText("6/6");
    await expect(page.locator("#detail")).toContainText("松开方向滑停");
    const charging = await sample(page);
    expect(charging.phase).toBe("playing");
    expect(charging.speed).toBeGreaterThan(WHALE.cruise);
    await captureWhaleArt(page, info, "W4-six-ready-still-swimming");
    await pointer(page, "pointerup", 82, 142, 227);
    await page.clock.runFor(2260);
    const settled = await sample(page);
    expect(settled.phase).toBe("landing");
    expect(settled.speed).toBeLessThanOrEqual(WHALE.reunionSpeed);
  });

  for (const reduced of [false, true]) {
    test(`WH-A12 course art W4 gathering ${reduced ? "reduced" : "standard"}`, async ({
      page,
    }, info) => {
      const pod = offshorePod({ x: 80, z: 1551 });
      await openWhaleArtView(
        page,
        {
          ...pod,
          actors: pod.actors.map((actor, index) =>
            index === 5
              ? { ...actor, pos: { x: actor.pos.x, z: 1502 } }
              : actor,
          ),
        },
        "C2",
        { reduced, low: reduced },
      );
      await page.clock.runFor(32);
      await expect(page.locator("#arrived")).toHaveText("5/6");
      await turnWhaleCamera(page, 262, 172);
      await expect(
        page.getByText("同伴 · 仍在区外", { exact: true }),
      ).toBeVisible();
      if (!reduced) await captureWhaleArt(page, info, "W4-look-back");
      for (let attempt = 0; attempt < 30; attempt++) {
        const state = await sample(page);
        if ((state.landingProgress ?? 0) >= 0.46) break;
        await page.clock.runFor(125);
      }
      const landed = await sample(page);
      expect(landed.phase).toBe("landing");
      expect(landed.framedWhales).toBe(6);
      expect(landed.landingProgress).toBeGreaterThanOrEqual(0.46);
      await captureWhaleArt(
        page,
        info,
        reduced ? "W4-reduced" : "W4-gathering",
      );
    });
  }
});

test.describe("Whale journey restore and evidence", () => {
  const shipStartZ = 372;
  const shipStartTick = 3310;
  const w1Clock = Date.UTC(2026, 0, 1);
  const hazard = (page: Page) => page.locator("#warning-detail");

  async function openShipStart(page: Page) {
    // Equivalent hull phase at tick zero, with a fresh journey and no C1 record.
    await page.route("**/levels/whale.json", async (route) => {
      await route.fulfill({
        json: {
          ...whaleLevel,
          spawn: { x: 0, z: shipStartZ },
          spawnSegment: "W1",
          zones: whaleLevel.zones.map((zone) =>
            zone.kind === "hazard" && zone.motion
              ? {
                  ...zone,
                  motion: {
                    ...zone.motion,
                    phaseTicks:
                      (zone.motion.phaseTicks + shipStartTick) %
                      zone.motion.periodTicks,
                  },
                }
              : zone,
          ),
        },
      });
    });
    await page.setViewportSize({ width: 852, height: 393 });
    await page.addInitScript(() =>
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({ music: false }),
      ),
    );
    await openMenu(page, "/?diagnostics");
    await expect(whaleEntry(page)).toBeEnabled();
    await page.clock.install({ time: w1Clock });
    await page.clock.pauseAt(w1Clock + 30_000);
    await whaleEntry(page).dispatchEvent("click");
    await start(page);
    await page.clock.runFor(430);
    expect(await sample(page)).toMatchObject({
      checkpoint: "start",
      z: shipStartZ,
    });
  }

  test("WH-A05 W1 default camera warning leaves a measured cruise reaction window", async ({
    page,
  }, info) => {
    test.setTimeout(55_000);
    await openShipStart(page);
    await expect(page.locator("#hazard-cue")).toBeVisible();
    await expect(page.locator("#hazard-notice")).toContainText(
      "水面／浅潜受阻",
    );
    await expect(hazard(page)).toContainText("减速让船先过");
    await expect(page.getByText("货船 · 向西", { exact: true })).toBeVisible();
    const first = await sample(page);
    expect(first.camera.yaw).toBe(0);
    await page.screenshot({
      path: info.outputPath("01-default-warning.png"),
      scale: "css",
    });
    await pointer(page, "pointerdown", 101, 142, 288);
    await pointer(page, "pointermove", 101, 142, 240);
    await page.clock.runFor(3950);
    let clear = await sample(page);
    let contact: SwimDiagnostic | undefined;
    for (let step = 0; step < 16; step++) {
      await page.clock.runFor(220);
      const current = await sample(page);
      // Contact can clear within one rendered frame as the hull passes. Its
      // immediate energy cost also identifies the first sampled impact.
      if (
        current.occupied.includes("cargo-ship") ||
        current.energy < first.energy - 0.1
      ) {
        contact = current;
        break;
      }
      clear = current;
    }
    await pointer(page, "pointerup", 101, 142, 240);
    if (!contact)
      throw new Error("The reference cruise did not reach the moving hull");
    const lower = (clear.tick - first.tick) / 60;
    const upper = (contact.tick - first.tick) / 60;
    const nominalCruiseSeconds = (clear.z - first.z) / WHALE.cruise;
    expect(lower).toBeGreaterThanOrEqual(3);
    expect(nominalCruiseSeconds).toBeGreaterThanOrEqual(3);
    expect(clear.speed).toBeGreaterThan(6.3);
    expect(contact.phase).toBe("playing");
    await writeFile(
      info.outputPath("W1-reaction-window.json"),
      JSON.stringify(
        {
          equivalentJourneyStartTick: shipStartTick,
          yaw: first.camera.yaw,
          warningTick: first.tick,
          warningZ: first.z,
          lastClearTick: clear.tick,
          lastClearZ: clear.z,
          firstContactSampleTick: contact.tick,
          contactZ: contact.z,
          approachSpeed: clear.speed,
          nominalCruiseSeconds,
          boundsSeconds: [lower, upper],
        },
        null,
        2,
      ) + "\n",
    );
  });

  for (const dive of [false, true]) {
    test(`WH-A04 W1 follows the ${dive ? "deep" : "surface"} route and saves the whole pod at C1`, async ({
      page,
    }, info) => {
      test.setTimeout(150_000);
      await openShipStart(page);
      const ability = page.locator("#formation");
      const box = await ability.boundingBox();
      if (!box) throw new Error("Missing dive control");
      const ax = box.x + box.width / 2;
      const ay = box.y + box.height / 2;
      if (dive) {
        await pointer(page, "pointerdown", 102, ax, ay, "#formation");
        await page.clock.runFor(3190);
        await expect(hazard(page)).toContainText("队尾仍在浅潜");
        await expect(
          page.locator('[data-kind="gathering"]:visible'),
        ).toHaveText("队尾 · 浅潜");
        await page.screenshot({
          path: info.outputPath("03-tail-in-shallow.png"),
          scale: "css",
        });
        await page.clock.runFor(990);
        await expect(hazard(page)).toContainText("全队已深潜");
        expect(
          (await sample(page)).actors?.every(
            ({ dive }) => dive.layer === "deep",
          ),
        ).toBe(true);
      } else {
        await expect(hazard(page)).toContainText("减速让船先过");
        await page.clock.runFor(6300);
        for (
          let step = 0;
          step < 15 &&
          !(await hazard(page).textContent())?.includes("有水面空档");
          step++
        )
          await page.clock.runFor(550);
        await expect(hazard(page)).toContainText("有水面空档");
        expect((await sample(page)).z).toBe(shipStartZ);
        await page.screenshot({
          path: info.outputPath("02-surface-opening.png"),
          scale: "css",
        });
      }
      await pointer(page, "pointerdown", 103, 142, 288);
      const stickY = dive ? 227 : 240;
      await pointer(page, "pointermove", 103, 142, stickY);
      for (let step = 0; step < 17 && (await sample(page)).z < 460; step++) {
        await page.clock.runFor(970);
        expect((await sample(page)).occupied).not.toContain("cargo-ship");
      }
      const cleared = await sample(page);
      expect(cleared.z).toBeGreaterThanOrEqual(460);
      expect(cleared.actors?.every(({ pos }) => pos.z > 429.7)).toBe(true);
      await expect(page.locator("#notice")).toHaveText("船后静水");
      await expect(page.locator("#hazard-cue")).toBeHidden();
      if (dive) {
        await expect(page.locator("#detail")).toContainText("上浮");
        await page.screenshot({
          path: info.outputPath("04-breathe-after-crossing.png"),
          scale: "css",
        });
        await pointer(page, "pointerup", 102, ax, ay, "#formation");
      }
      for (let step = 0; step < 8 && (await sample(page)).z < 488; step++)
        await page.clock.runFor(800);
      expect((await sample(page)).checkpoint).toBe("start");
      await expect(page.locator("#notice")).toHaveText("检查点 1");
      await expect(page.locator("#detail")).toContainText("水面就绪");
      if (dive)
        await page.screenshot({
          path: info.outputPath("05-c1-waiting.png"),
          scale: "css",
        });
      await page.clock.runFor(dive ? 2900 : 4600);
      await pointer(page, "pointerup", 103, 142, stickY);
      const saved = await sample(page);
      expect(saved.checkpoint).toBe("C1");
      expect(
        saved.actors?.every(
          ({ dive }) => dive.layer === "surface" && dive.direction === null,
        ),
      ).toBe(true);
      await expect(page.locator("#whale-save-detail")).toHaveText(
        "检查点 C1 已保存",
      );
      await expect(page.locator("#notice")).toHaveText(
        "前方渔网 · 两条路线可绕行",
      );
      for (const label of ["短网口 · 提前收速", "外侧宽线 · 可巡航"])
        await expect(page.getByText(label, { exact: true })).toBeVisible();
      if (dive)
        await page.screenshot({
          path: info.outputPath("06-c1-saved.png"),
          scale: "css",
        });
      await page.clock.resume();
      await page.reload();
      await enterSpeciesMenu(page);
      await enterWhaleChapter(page);
      await expect(page.locator("#panel-text")).toContainText("C1", {
        timeout: 25000,
      });
    });
  }

  test("WH-A05 W1 low breath points back to the same bank in low quality", async ({
    page,
  }, info) => {
    test.setTimeout(55_000);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.addInitScript(() =>
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({
          low: true,
          reduced: true,
          music: false,
          mapping: "B",
        }),
      ),
    );
    await openMenu(page, "/?diagnostics");
    const staged = podAt({ x: 0, z: 389 }, "journey", 3500);
    await seedWhale(
      page,
      {
        ...staged,
        segmentId: "W1",
        occupied: ["ship-approach"],
        triggered: ["C1"],
        actors: staged.actors.map((actor, index) => ({
          ...actor,
          speed: index === 0 ? WHALE.cruise : actor.speed,
          dive: { ...actor.dive, layer: "deep", depth: 2, breath: 0.055 },
        })),
      },
      "C1",
    );
    await enterWhaleChapter(page);
    await page.clock.install({ time: w1Clock });
    await page.clock.pauseAt(w1Clock + 30_000);
    await page
      .getByRole("button", { name: "从检查点继续" })
      .dispatchEvent("click");
    await page.clock.runFor(48);
    await expect(page.locator("#notice")).toHaveText("呼吸偏低");
    await expect(page.getByText("换气水域", { exact: true })).toBeVisible();
    await expect(hazard(page)).toContainText("先在船道外换气");
    await page.screenshot({
      path: info.outputPath("07-low-air-refill.png"),
      scale: "css",
    });
    await pointer(page, "pointerdown", 104, 142, 248);
    await pointer(page, "pointermove", 104, 142, 278);
    for (let step = 0; step < 12 && (await sample(page)).z >= 380; step++) {
      await page.clock.runFor(900);
      expect((await sample(page)).occupied).not.toContain("cargo-ship");
    }
    await pointer(page, "pointerup", 104, 142, 278);
    await page.clock.runFor(7500);
    const restored = await sample(page);
    expect(restored.phase).toBe("playing");
    expect(restored.occupied).toContain("waiting-water");
    expect(
      restored.actors?.every(
        ({ dive }) => dive.layer === "surface" && dive.breath >= 0.95,
      ),
    ).toBe(true);
  });

  async function openReefGate(page: Page) {
    await openMenu(page, "/?diagnostics");
    // A local browser fixture at the W3 entrance. Integration tests navigate here from C1.
    await seedWhale(
      page,
      {
        ...podAt({ x: -75, z: 1038 }, "journey", 11370),
        segmentId: "W3",
        triggered: ["C1"],
      },
      "C1",
    );
    await enterWhaleChapter(page);
    const resume = page.getByRole("button", { name: "从检查点继续" });
    await expect(resume).toBeVisible();
    await resume.click();
    await expect(page.locator("#notice")).toHaveText("选择航道");
  }

  for (const reduced of [false, true]) {
    test(`WH-A07 W3 reef responds to a shallow pass in ${reduced ? "low quality and reduced motion" : "standard quality"}`, async ({
      page,
    }, info) => {
      test.setTimeout(150_000);
      await page.setViewportSize({ width: 852, height: 393 });
      await page.addInitScript((reduced) => {
        localStorage.setItem(
          "feather-tide-settings-v1",
          JSON.stringify({
            mapping: "B",
            music: false,
            low: reduced,
            reduced,
            toggle: reduced,
          }),
        );
      }, reduced);
      await page.clock.install();
      await openReefGate(page);
      await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 200);
      const shot = (name: string) =>
        page.screenshot({ path: info.outputPath(`${name}.png`), scale: "css" });
      const move = () => pointer(page, "pointermove", 51, 142, 242);
      await pointer(page, "pointerdown", 51, 142, 288);
      await move();
      const surface = await swimToZ(page, 1116);
      expect(surface.route).toBe("quiet");
      await expect(page.locator("#notice")).toHaveText("第一段顺流");
      expect(surface.occupied).toContain("quiet-rest");
      expect(surface.reef?.fish).toBe(reduced ? 42 : 66);
      expect(surface.camera.yaw).toBeCloseTo(0);
      await expect(depth(page)).toHaveText("水面");
      await shot("01-surface");

      await pointer(page, "pointerdown", 52, 643, 176);
      await pointer(page, "pointermove", 52, 507, 162);
      await pointer(page, "pointerup", 52, 507, 162);
      const ability = page.locator("#formation");
      const box = await ability.boundingBox();
      if (!box) throw new Error("Missing dive control");
      const ax = box.x + box.width / 2;
      const ay = box.y + box.height / 2;
      const divePointer = (phase: "down" | "up", id: number) =>
        pointer(page, `pointer${phase}`, id, ax, ay, "#formation");
      await divePointer("down", 53);
      if (reduced) await divePointer("up", 53);
      await page.clock.runFor(1770);
      const dispersed = await sample(page);
      await expect(depth(page)).toContainText("浅潜");
      await expect(page.locator("#flight-cue")).toContainText("光斑水域可换气");
      expect(dispersed.camera.yaw).toBeGreaterThan(35);
      expect(dispersed.reef?.spread[0]).toBeGreaterThan(0.42);
      expect(dispersed.z).toBeGreaterThan(surface.z + 8);
      await shot("02-shallow-scatter");

      await expect(ability).toHaveAttribute("aria-pressed", "true");
      await pointer(page, "pointerup", 51, 142, 242);
      if (reduced) await divePointer("down", 54);
      await divePointer("up", reduced ? 54 : 53);
      await page.clock.runFor(32);
      await expect(ability).toHaveAttribute("aria-pressed", "false");
      await expect(page.locator("#whale-depth-cue")).toContainText("上浮");
      await page.evaluate(() => {
        Object.defineProperty(document, "hidden", {
          configurable: true,
          value: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });
      await page.clock.runFor(800);
      await expect(page.locator("#panel")).toContainText("航行暂停");
      await page.evaluate(() => {
        Reflect.deleteProperty(document, "hidden");
        document.dispatchEvent(new Event("visibilitychange"));
      });
      await page.clock.runFor(32);
      const paused = await sample(page);
      expect(paused.phase).toBe("paused");
      await page.clock.runFor(1000);
      expect(await sample(page)).toMatchObject({
        tick: paused.tick,
        reef: paused.reef,
      });
      await page
        .getByRole("button", { name: "继续航行" })
        .dispatchEvent("click");
      await page.clock.runFor(5400);
      const gathered = await sample(page);
      expect(gathered.phase).toBe("playing");
      expect(gathered.speed).toBe(0);
      expect(gathered.reef?.spread[0]).toBeLessThan(
        (dispersed.reef?.spread[0] ?? 0) * 0.4,
      );
      expect(gathered.reef?.glintPhase === surface.reef?.glintPhase).toBe(
        reduced,
      );
      await expect(depth(page)).toHaveText("水面");
      expect(gathered.actors?.[0]?.dive.breath).toBe(1);
      await shot("03-school-regrouped");

      if (!reduced) {
        await page.locator("#camera-reset").dispatchEvent("click");
        await page.clock.runFor(720);
        await pointer(page, "pointerdown", 51, 142, 288);
        await move();
        await swimToZ(page, 1202);
        await pointer(page, "pointerup", 51, 142, 242);
        const bend = page.getByText("安静航道 · 向汇流处转弯", { exact: true });
        await expect(bend).toBeVisible();
        const bendBox = await bend.boundingBox();
        const cueBox = await page.locator("#flight-cue").boundingBox();
        if (!bendBox || !cueBox) throw new Error("Missing the bend cue");
        expect(bendBox.y).toBeGreaterThanOrEqual(cueBox.y + cueBox.height);
        expect((await sample(page)).z).toBeGreaterThan(1196);
        await shot("04-bend-after-surfacing");
      } else {
        // Turn far enough to look back from the same anchor in the reduced setting.
        await pointer(page, "pointerdown", 55, 720, 180);
        await pointer(page, "pointermove", 55, 246, 180);
        await pointer(page, "pointerup", 55, 246, 180);
        await page.clock.runFor(32);
        expect(Math.abs((await sample(page)).camera.yaw)).toBeGreaterThan(140);
        await expect(
          page.getByText("水面宽线 · 沿浅礁缓转", { exact: true }),
        ).toBeVisible();
        await shot("04-look-back-low");
      }
    });
  }

  for (const low of [false, true]) {
    test(`WH-A07 records W3 real frame timings in ${low ? "low" : "standard"} quality`, async ({
      page,
      browser,
    }, info) => {
      test.setTimeout(60_000);
      await page.setViewportSize({ width: 852, height: 393 });
      await page.addInitScript((low) => {
        localStorage.setItem(
          "feather-tide-settings-v1",
          JSON.stringify({ low, music: false }),
        );
      }, low);
      await page.clock.install();
      await openReefGate(page);
      await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 200);
      await pointer(page, "pointerdown", 61, 142, 288);
      await pointer(page, "pointermove", 61, 142, 242);
      await swimToZ(page, 1138);
      await pointer(page, "pointerup", 61, 142, 242);
      await page.clock.runFor(2400);
      await page.locator("#pause-flight").dispatchEvent("click");
      await page.clock.runFor(32);
      await page.clock.resume();
      await page.getByRole("button", { name: "继续航行" }).click();
      await expect(page.locator("#notice")).toHaveText("浅礁静水");
      expect((await sample(page)).reef?.fish).toBe(low ? 42 : 66);
      let report: { samples: number } | undefined;
      await expect
        .poll(
          async () => {
            const value = await page
              .locator("#game")
              .getAttribute("data-performance");
            report = value ? JSON.parse(value) : undefined;
            return report?.samples ?? 0;
          },
          { timeout: 45_000 },
        )
        .toBeGreaterThanOrEqual(150);
      expect(report).toMatchObject({
        segment: "W3",
        phase: "playing",
        quality: low ? "low" : "standard",
        medianMs: expect.any(Number),
        p95Ms: expect.any(Number),
        calls: expect.any(Number),
      });
      const gpu = await page
        .locator("canvas")
        .evaluate((canvas: HTMLCanvasElement) => {
          const gl = canvas.getContext("webgl2");
          const debug = gl?.getExtension("WEBGL_debug_renderer_info");
          return debug
            ? String(gl?.getParameter(debug.UNMASKED_RENDERER_WEBGL))
            : undefined;
        });
      const { x, z } = await sample(page);
      await writeFile(
        info.outputPath(`W3-${low ? "low" : "standard"}.json`),
        JSON.stringify(
          {
            browser: browser.version(),
            gpu,
            viewport: page.viewportSize(),
            leader: { x, z },
            ...report,
          },
          null,
          2,
        ) + "\n",
      );
    });
  }

  for (const shallow of [false, true]) {
    test(`WH-A10 W4 from an original C2 save completes via ${shallow ? "shallow" : "surface"} entry`, async ({
      page,
    }, info) => {
      test.setTimeout(120_000);
      await page.setViewportSize({ width: 852, height: 393 });
      await page.addInitScript(
        (shallow) =>
          localStorage.setItem(
            "feather-tide-settings-v1",
            JSON.stringify({
              low: shallow,
              reduced: shallow,
              toggle: shallow,
              music: false,
            }),
          ),
        shallow,
      );
      await page.clock.install();
      await openMenu(page, "/?diagnostics");
      const route = shallow ? "shipping" : "quiet";
      const c2 = whaleTrip("journey", route).checkpoints.find(
        ({ id }) => id === "C2",
      );
      if (!c2 || c2.state.species !== "whale") throw new Error("Missing C2");
      const savedState = shallow
        ? {
            ...c2.state,
            levelRevision: "whale-p2-1",
            triggered: [...c2.state.triggered, "net-rescue"],
          }
        : { ...c2.state, levelRevision: "whale-p2-8" };
      await seedWhale(page, savedState, "C2");
      await enterWhaleChapter(page);
      const resume = page.getByRole("button", {
        name: "从检查点继续",
        exact: true,
      });
      await expect(resume).toBeVisible({ timeout: 20_000 });
      await expect(page.locator("#panel-text")).toContainText("C2");
      await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 200);
      await resume.dispatchEvent("click");
      await page.clock.runFor(32);
      expect(await sample(page)).toMatchObject({
        checkpoint: "C2",
        route,
        phase: "playing",
      });
      await expect(
        page.getByText("外海静水 · 上浮等候", { exact: true }),
      ).toBeVisible();

      await pointer(page, "pointerdown", 71, 142, 288);
      await pointer(page, "pointermove", 71, 142, 227);
      const approach = await swimToZ(page, 1453);
      expect(approach.z).toBeGreaterThan(1440);
      await expect(page.locator("#marker-layer")).toHaveAttribute(
        "data-camera",
        "Focus",
      );
      if (!shallow)
        await page.screenshot({
          path: info.outputPath("01-offshore-approach.png"),
          scale: "css",
        });
      await swimToZ(page, 1510);
      if (shallow) {
        const ability = page.locator("#formation");
        const box = await ability.boundingBox();
        if (!box) throw new Error("Missing dive control");
        const tapDive = async (id: number) => {
          const x = box.x + box.width / 2;
          const y = box.y + box.height / 2;
          await pointer(page, "pointerdown", id, x, y, "#formation");
          await pointer(page, "pointerup", id, x, y, "#formation");
        };
        await tapDive(72);
        await page.clock.runFor(1420);
        const entry = await sample(page);
        expect(entry.z).toBeGreaterThan(1518);
        expect(entry.phase).toBe("playing");
        await expect(depth(page)).toHaveText("浅潜");
        await expect(page.locator("#arrival-caption")).toHaveText(
          "浮出水面汇合",
        );
        await expect(page.locator("#detail")).toContainText("再点按");
        await page.screenshot({
          path: info.outputPath("02-shallow-entry.png"),
          scale: "css",
        });
        await tapDive(73);
      }
      await swimToZ(page, 1547);
      expect((await sample(page)).phase).toBe("playing");
      await pointer(page, "pointerup", 71, 142, 227);
      for (
        let step = 0;
        step < 30 && (await sample(page)).phase === "playing";
        step++
      )
        await page.clock.runFor(250);
      const offshore = await sample(page);
      expect(offshore).toMatchObject({
        checkpoint: "C2",
        route,
        phase: "landing",
        framedWhales: 6,
      });
      expect(offshore.actors?.map(({ dive }) => dive.layer)).toEqual(
        Array(6).fill("surface"),
      );
      await expect(page.locator("#arrived")).toHaveText("6/6");
      if (shallow) {
        await page.clock.runFor(480);
        const stored = await page.evaluate(
          () =>
            new Promise<unknown>((resolve, reject) => {
              const request = indexedDB.open("feather-tide", 1);
              request.onerror = () => reject(request.error);
              request.onsuccess = () => {
                const db = request.result;
                const read = db
                  .transaction("checkpoint")
                  .objectStore("checkpoint")
                  .get(["whale", "whale", "journey"]);
                read.onsuccess = () => {
                  db.close();
                  resolve(read.result);
                };
                read.onerror = () => {
                  db.close();
                  reject(read.error);
                };
              };
            }),
        );
        expect(stored).toMatchObject({
          kind: "arrived",
          levelRevision: whaleLevel.levelRevision,
          route,
        });
      }
    });
  }

  for (const path of ["short", "arc"] as const) {
    test(`WH-A06 W2 kelp ${path} shows actual pod and supply status before six enter W3`, async ({
      page,
    }, info) => {
      test.setTimeout(150_000);
      const checkpoint = whaleTrip("journey", "quiet").checkpoints[0];
      const bay = whaleLevel.zones.find(({ id }) => id === "net-kelp");
      const w3 = whaleLevel.segments.find(({ id }) => id === "W3");
      if (!checkpoint || !bay || !w3) throw new Error("Missing kelp course");
      const bayPoints = bay.points;
      const fork = kelpForkFromC1(checkpoint).expected;
      await openWhaleArtView(page, fork, "C1", {
        low: true,
        reduced: path === "arc",
      });
      await page.clock.runFor(160);
      await expect(
        page.getByText("短切进湾 · 提前收速", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText("外侧缓弧 · 带队靠拢", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText("短网口出口 · 前往分岔", { exact: true }),
      ).toBeHidden();
      if (path === "short")
        await captureWhaleArt(page, info, "W2-kelp-choices");

      const stick = { x: 142, y: 280 };
      const notice = page.locator("#detail");
      let waiting = false;
      let replenishing = false;
      let moving = false;
      async function swimTo(target: Vec2, strength: number) {
        if (!moving) {
          await pointer(page, "pointerdown", 81, stick.x, stick.y);
          moving = true;
        }
        for (let step = 0; step < 100; step++) {
          const state = await sample(page);
          expect(state.occupied).not.toContain("drift-net");
          expect(state.occupied).not.toContain("net-divider");
          if (state.occupied.includes("net-kelp")) {
            const count = state.actors?.filter(
              (actor) =>
                actor.status !== "strayed" && contains(bayPoints, actor.pos),
            ).length;
            await expect(notice).toContainText(`进湾 ${count}/6`);
            if (count !== undefined && count < 4 && !waiting) {
              await expect(notice).toContainText("至少 4 只进湾才补给");
              if (path === "short")
                await captureWhaleArt(page, info, "W2-kelp-waiting-tail");
              waiting = true;
            }
            if (
              count !== undefined &&
              count >= 4 &&
              state.energy < 0.995 &&
              !replenishing
            ) {
              await expect(notice).toContainText("正在补给");
              await captureWhaleArt(page, info, `W2-kelp-${path}-replenishing`);
              replenishing = true;
            }
          }
          const dx = target.x - state.x;
          const dz = target.z - state.z;
          if (Math.hypot(dx, dz) <= 3) return;
          const { right, up } = state.basis;
          const horizontal = dx * right.x + dz * right.z;
          const forward = (dx * up.x + dz * up.z) / (up.x ** 2 + up.z ** 2);
          const scale =
            ((0.1 + 0.9 * strength) * 54) / Math.hypot(horizontal, forward);
          await pointer(
            page,
            "pointermove",
            81,
            stick.x + horizontal * scale,
            stick.y - forward * scale,
          );
          await page.clock.runFor(210);
        }
        throw new Error(
          `Did not reach kelp waypoint ${JSON.stringify(target)}`,
        );
      }
      const speed = path === "short" ? 0.64 : 0.83;
      for (const id of kelpApproaches[path]) {
        const mark = whaleLevel.landmarks.find((mark) => mark.id === id);
        if (!mark) throw new Error(`Missing kelp landmark ${id}`);
        await swimTo(mark.pos, speed);
      }
      await pointer(page, "pointerup", 81, stick.x, stick.y);
      moving = false;
      await page.clock.runFor(4100);
      expect(waiting).toBe(true);
      expect(replenishing).toBe(true);
      await expect(notice).toHaveText("进湾 6/6 · 能量已满");
      if (path === "arc")
        await captureWhaleArt(page, info, "W2-kelp-six-in-bay");

      await swimTo({ x: 34, z: 963 }, 0.83);
      await pointer(page, "pointerup", 81, stick.x, stick.y);
      const arrived = await sample(page);
      expect(arrived).toMatchObject({
        segment: "W3",
        phase: "playing",
        route: null,
      });
      expect(arrived.actors).toHaveLength(6);
      expect(
        arrived.actors?.every(
          (actor) =>
            actor.pos.z >= w3.start &&
            actor.status === "following" &&
            actor.dive.depth === 0,
        ),
      ).toBe(true);
    });
  }

  test("WH-A06 W2 turns through the outer route with the whole pod", async ({
    page,
  }, info) => {
    test.setTimeout(150_000);
    await openWhaleArtView(
      page,
      {
        ...podAt({ x: 35, z: 704 }, "journey", 6900),
        segmentId: "W2",
        triggered: ["C1"],
      },
      "C1",
      { low: true, reduced: true },
    );
    await page.clock.runFor(160);
    await expect(page.locator("#warning-detail")).toContainText(
      "短网口需先对准再缓游",
    );
    await pointer(page, "pointerdown", 111, 142, 288);
    await pointer(page, "pointermove", 111, 81, 288);
    for (let step = 0; step < 14 && (await sample(page)).x < 112; step++)
      await page.clock.runFor(780);
    const aligned = await sample(page);
    expect(aligned.x).toBeGreaterThanOrEqual(112);
    expect(aligned.z).toBeLessThan(741);
    await expect(
      page.getByText("外侧弧线 · 向静水", { exact: true }),
    ).toBeVisible();
    await pointer(page, "pointermove", 111, 142, 227);
    let sawOpening = false;
    for (let step = 0; step < 22 && (await sample(page)).z < 825; step++) {
      await page.clock.runFor(610);
      const crossing = await sample(page);
      expect(crossing.occupied).not.toContain("drift-net");
      expect(crossing.occupied).not.toContain("net-divider");
      if (!sawOpening && crossing.z >= 715 && crossing.z < 747) {
        await expect(
          page.getByText("外侧宽线 · 可巡航绕行", { exact: true }),
        ).toBeVisible();
        sawOpening = true;
      }
    }
    expect(sawOpening).toBe(true);
    await expect(page.locator("#notice")).toHaveText("网外静水");
    await captureWhaleArt(page, info, "W2-outer");
    for (
      let step = 0;
      step < 18 && (await sample(page)).segment === "W2";
      step++
    )
      await page.clock.runFor(1000);
    const junction = await sample(page);
    expect(junction.segment).toBe("W3");
    expect(junction.actors?.every(({ status }) => status === "following")).toBe(
      true,
    );
    await pointer(page, "pointerup", 111, 142, 227);
  });

  test("WH-A06 W2 eases through the short opening and keeps the tail in view", async ({
    page,
  }, info) => {
    test.setTimeout(60_000);
    await openWhaleArtView(
      page,
      {
        ...podAt({ x: 75, z: 737 }, "journey", 8250),
        segmentId: "W2",
        triggered: ["C1"],
      },
      "C1",
      { low: true, reduced: true },
    );
    await page.clock.runFor(240);
    await expect(
      page.getByText("短网口 · 对准后缓游", { exact: true }),
    ).toBeVisible();
    await pointer(page, "pointerdown", 73, 142, 288);
    await pointer(page, "pointermove", 73, 142, 264);
    let prepared = false;
    let counted = false;
    for (let step = 0; step < 28; step++) {
      await page.clock.runFor(864);
      const trace = await sample(page);
      expect(trace.occupied).not.toContain("drift-net");
      expect(trace.occupied).not.toContain("net-divider");
      if (!prepared && trace.z >= 761 && trace.z < 774) {
        await expect(page.locator("#detail")).toContainText("等队尾清网再转向");
        await expect(
          page.getByText("队尾 · 尚未清网", { exact: false }),
        ).toBeVisible();
        await expect(
          page.getByText("先沿这里直游", { exact: false }),
        ).toBeVisible();
        await captureWhaleArt(page, info, "W2-before-turn");
        prepared = true;
      }
      if (
        !counted &&
        trace.z > 776 &&
        trace.actors?.some(({ pos }) => pos.z <= 775.7)
      ) {
        counted = true;
        await expect(page.locator("#notice")).toHaveText(/已清网 [1-5]\/6/);
        await captureWhaleArt(page, info, "W2-short-tail");
      }
      if (trace.actors?.every(({ pos }) => pos.z > 786)) break;
    }
    expect(prepared).toBe(true);
    expect(counted).toBe(true);
    expect(
      (await sample(page)).actors?.every(
        ({ pos, status }) => pos.z > 786 && status === "following",
      ),
    ).toBe(true);
    await pointer(page, "pointerup", 73, 142, 264);
  });

  test("WH-A06 W2 actual net contact leaves a whale to pick up across the net", async ({
    page,
  }, info) => {
    test.setTimeout(125_000);
    const checkpoint = whaleTrip("journey", "quiet").checkpoints[0];
    if (!checkpoint) throw new Error("Missing C1");
    const before = netApproachForBrowser(checkpoint);
    expect(before.actors.every(({ status }) => status !== "strayed")).toBe(
      true,
    );
    await openWhaleArtView(page, before, "C1", { low: true, reduced: true });

    const fallen = (state: SwimDiagnostic) =>
      state.actors?.find(({ status }) => status === "strayed");
    const within = (state: SwimDiagnostic, target: Vec2, range: number) =>
      Math.hypot(state.x - target.x, state.z - target.z) <= range;
    async function steer(
      id: number,
      target: Vec2,
      strength: number,
      done: (state: SwimDiagnostic) => boolean,
      steps = 65,
    ) {
      await pointer(page, "pointerdown", id, 142, 270);
      for (let i = 0; i < steps; i++) {
        const state = await sample(page);
        if (done(state)) break;
        const dx = target.x - state.x;
        const dz = target.z - state.z;
        const { right, up } = state.basis;
        const horizontal = dx * right.x + dz * right.z;
        const forward = (dx * up.x + dz * up.z) / (up.x ** 2 + up.z ** 2);
        const scale =
          (Math.min(1, strength * 0.9 + 0.1) * 54) /
          Math.hypot(horizontal, forward);
        await pointer(
          page,
          "pointermove",
          id,
          142 + horizontal * scale,
          270 - forward * scale,
        );
        await page.clock.runFor(192);
      }
      const result = await sample(page);
      await pointer(page, "pointerup", id, 142, 270);
      expect(done(result)).toBe(true);
      return result;
    }

    await page.clock.runFor(32);
    const contact = await steer(
      111,
      { x: 33, z: 828 },
      1,
      (state) => !!fallen(state),
      18,
    );
    const separated = fallen(contact);
    if (!separated) throw new Error("Missing whale after the net contact");
    expect(separated.id).toBe("whale-2");
    await expect(page.locator("#detail")).toContainText("沿可通行水域接近同伴");
    await turnWhaleCamera(page, 267, 157);
    await expect(
      page.getByText("待接应同伴 · 水面", { exact: true }),
    ).toBeVisible();
    await captureWhaleArt(page, info, "W2-look-back");
    await page.locator("#camera-reset").dispatchEvent("click");
    await page.clock.runFor(400);
    for (const [i, point] of netRecoveryBend.entries())
      await steer(113 + i, point, 0.65, (state) => within(state, point, 4), 95);
    await steer(115, separated.pos, 0.4, (state) =>
      within(state, separated.pos, 6),
    );
    await page.clock.runFor(850);
    const progress = page.getByLabel("接应进度");
    await expect(progress).toBeVisible();
    expect(fallen(await sample(page))?.rescueProgress).toBeGreaterThan(0);
    await captureWhaleArt(page, info, "W2-pickup");
    for (let step = 0; step < 30 && fallen(await sample(page)); step++)
      await page.clock.runFor(120);
    await expect(
      page.getByText("同伴 · 正在归队", { exact: true }),
    ).toBeVisible();
    for (
      let step = 0;
      step < 30 &&
      (await sample(page)).actors?.some(({ status }) => status === "rejoining");
      step++
    )
      await page.clock.runFor(200);
    expect(
      (await sample(page)).actors?.find(({ id }) => id === separated.id)
        ?.status,
    ).toBe("following");
  });

  test("WH-A06 W2 shows actual pickup progress and freezes it while paused", async ({
    page,
  }, info) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.clock.install();
    await openMenu(page, "/?diagnostics");
    const state = podAt({ x: 92, z: 842 }, "journey", 9000);
    await seedWhale(
      page,
      {
        ...state,
        segmentId: "W2",
        triggered: ["C1"],
        actors: state.actors.map((actor, index) =>
          index === 5
            ? {
                ...actor,
                pos: { x: 96, z: 838 },
                status: "strayed",
                rescueTicks: 1800,
              }
            : actor,
        ),
      },
      "C1",
    );
    await enterWhaleChapter(page);
    const resume = page.getByRole("button", {
      name: "从检查点继续",
      exact: true,
    });
    await expect(resume).toBeVisible();
    await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 500);
    await resume.dispatchEvent("click");
    await page.clock.runFor(450);
    const progress = page.getByLabel("接应进度");
    await expect(progress).toBeVisible();
    await expect(page.getByRole("timer")).toBeVisible();
    await expect(page.locator("#notice")).toHaveText("接应同伴 · 水面");
    expect(Number(await progress.getAttribute("value"))).toBeGreaterThan(0);
    await page.screenshot({
      path: info.outputPath("W2-rescue.png"),
      scale: "css",
    });
    await page.locator("#pause-flight").dispatchEvent("click");
    await page.clock.runFor(32);
    const paused = await sample(page);
    expect(paused.phase).toBe("paused");
    await page.clock.runFor(1000);
    const frozen = await sample(page);
    expect(frozen.tick).toBe(paused.tick);
    expect(frozen.actors?.at(-1)?.rescueProgress).toBe(
      paused.actors?.at(-1)?.rescueProgress,
    );
    expect(frozen.actors?.at(-1)?.rescueTicks).toBe(
      paused.actors?.at(-1)?.rescueTicks,
    );
    await page
      .getByRole("button", { name: "继续航行", exact: true })
      .dispatchEvent("click");
    await page.clock.runFor(1800);
    await expect(progress).toBeHidden();
    await expect(page.getByRole("timer")).toBeHidden();
  });

  test("WH-A07 W3 shows both routes before crossing and reports the selected route in silence", async ({
    page,
  }, info) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.addInitScript(() =>
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({ music: false }),
      ),
    );
    await page.clock.install();
    await openMenu(page, "/?diagnostics");
    await seedWhale(
      page,
      {
        ...podAt({ x: 20, z: 1036 }, "journey", 9900),
        segmentId: "W3",
        triggered: ["C1"],
      },
      "C1",
    );
    await enterWhaleChapter(page);
    const resume = page.getByRole("button", {
      name: "从检查点继续",
      exact: true,
    });
    await expect(resume).toBeVisible();
    await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 500);
    await resume.dispatchEvent("click");
    await page.clock.runFor(400);
    await expect(page.locator("#notice")).toHaveText("选择航道");
    for (const label of ["近航道 · 看空档", "安静航道 · 绕浅礁"]) {
      const marker = page.getByText(label, { exact: true });
      await expect(marker).toBeVisible();
      await expect(marker).not.toHaveClass(/\bedge\b/);
    }
    await page.screenshot({
      path: info.outputPath("W3-branch.png"),
      scale: "css",
    });
    await pointer(page, "pointerdown", 40, 140, 290);
    await pointer(page, "pointermove", 40, 140, 244);
    await page.clock.runFor(3300);
    await pointer(page, "pointerup", 40, 140, 244);
    await expect(page.locator("#notice")).toHaveText(
      /近航道 · 靠近待航标|安静空档 · 可巡航通过|噪声带 · 等下一轮|安静空档已不足 · 等下一轮/,
    );
    await expect(page.getByLabel("队伍凝聚")).toBeVisible();
    expect((await sample(page)).route).toBe("shipping");
    await page.screenshot({
      path: info.outputPath("W3-shipping.png"),
      scale: "css",
    });
  });

  test("WH-A07 W3 waits for a quiet window and crosses without noise in silence", async ({
    page,
  }, info) => {
    test.setTimeout(60_000);
    const pod = podAt({ x: 62, z: 1038 }, "journey", 11_670);
    await openWhaleArtView(
      page,
      {
        ...pod,
        segmentId: "W3",
        triggered: ["C1"],
      },
      "C1",
      { low: true, reduced: true },
    );
    await page.clock.runFor(32);
    await pointer(page, "pointerdown", 41, 142, 288);
    await pointer(page, "pointermove", 41, 142, 242);
    for (let step = 0; step < 45 && (await sample(page)).z < 1077; step++)
      await page.clock.runFor(192);
    await pointer(page, "pointerup", 41, 142, 242);
    await page.clock.runFor(2000);
    expect(await sample(page)).toMatchObject({ route: "shipping", speed: 0 });
    await expect(page.locator("#notice")).toHaveText("噪声带 · 等下一轮");
    await expect(
      page.getByText("静水湾 · 等队尾", { exact: true }),
    ).toBeVisible();
    await captureWhaleArt(page, info, "W3-noise-active");
    const waiting = await sample(page);
    await page.locator("#pause-flight").dispatchEvent("click");
    await page.clock.runFor(4200);
    expect((await sample(page)).tick).toBe(waiting.tick);
    await page.getByRole("button", { name: "继续航行" }).dispatchEvent("click");
    const untilQuiet = 420 - (waiting.tick % 1200);
    expect(untilQuiet).toBeGreaterThan(0);
    await page.clock.runFor(Math.ceil((untilQuiet * 1000) / 60) + 64);
    const calm = await sample(page);
    expect(calm.z).toBe(waiting.z);
    await expect(page.locator("#notice")).toHaveText("安静空档 · 可巡航通过");
    await expect(page.getByText("换气及补给", { exact: true })).toBeVisible();
    await captureWhaleArt(page, info, "W3-noise-quiet");
    await pointer(page, "pointerdown", 43, 142, 288);
    await pointer(page, "pointermove", 43, 142, 242);
    for (let step = 0; step < 12 && (await sample(page)).z < 1147; step++) {
      await page.clock.runFor(920);
      expect((await sample(page)).occupied).not.toContain("shipping-noise");
    }
    await pointer(page, "pointerup", 43, 142, 242);
    expect(
      (await sample(page)).actors?.every(
        ({ pos, status }) => pos.z > 1126 && status === "following",
      ),
    ).toBe(true);
  });

  test("WH-A07 W3 borrows the optional current with two pointers in silence", async ({
    page,
  }, info) => {
    test.setTimeout(60_000);
    const pod = podAt({ x: -95, z: 1038 }, "journey", 11_330);
    await openWhaleArtView(
      page,
      {
        ...pod,
        segmentId: "W3",
        triggered: ["C1"],
      },
      "C1",
      { low: true, reduced: true },
    );
    await page.clock.runFor(240);
    await pointer(page, "pointerdown", 73, 142, 288);
    await pointer(page, "pointermove", 73, 142, 242);
    for (let i = 0; i < 24 && (await sample(page)).z < 1119; i++)
      await page.clock.runFor(640);
    await pointer(page, "pointerup", 73, 142, 242);
    await page.clock.runFor(2200);
    expect(await sample(page)).toMatchObject({ route: "quiet", speed: 0 });
    await expect(
      page.getByText("第一段顺流入口", { exact: true }),
    ).toBeVisible();
    await expect(page.locator("#detail")).toContainText("宽水面");
    await captureWhaleArt(page, info, "W3-current-entry");

    const box = await page.locator("#formation").boundingBox();
    if (!box) throw new Error("Missing dive control");
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await pointer(page, "pointerdown", 72, x, y, "#formation");
    await page.clock.runFor(1100);
    await expect(depth(page)).toHaveText("浅潜");
    expect((await sample(page)).occupied).not.toContain("reef-current");
    await pointer(page, "pointerdown", 71, 142, 288);
    await pointer(page, "pointermove", 71, 142, 242);
    await page.clock.runFor(1850);
    await expect(page.locator("#notice")).toHaveText("正在借流 · 第一段顺流");
    expect((await sample(page)).occupied).toContain("reef-current");
    await captureWhaleArt(page, info, "W3-current-active");
    await pointer(page, "pointerup", 71, 142, 242);
    await pointer(page, "pointerup", 72, x, y, "#formation");
    await page.clock.runFor(4000);
    const stopped = await sample(page);
    expect(stopped.occupied).not.toContain("reef-current");
    expect(stopped.speed).toBe(0);
    expect(stopped.actors?.every(({ dive }) => dive.depth === 0)).toBe(true);
  });

  for (const path of ["continuous", "regroup", "surface"] as const) {
    test(`WH-A07 W3 ${path} travels to C2 with six whales using touch controls`, async ({
      page,
    }, info) => {
      test.setTimeout(150_000);
      const pod = podAt({ x: -95, z: 1038 }, "journey", 11_330);
      await openWhaleArtView(
        page,
        { ...pod, segmentId: "W3", triggered: ["C1"] },
        "C1",
        { low: true, reduced: path === "surface" },
      );
      await page.clock.runFor(240);

      const stick = { x: 142, y: 280 };
      let moving = false;
      async function swimTo(target: Vec2) {
        if (!moving) {
          await pointer(page, "pointerdown", 81, stick.x, stick.y);
          moving = true;
        }
        for (let step = 0; step < 100; step++) {
          const state = await sample(page);
          const dx = target.x - state.x;
          const dz = target.z - state.z;
          if (Math.hypot(dx, dz) <= 3) return state;
          const { right, up } = state.basis;
          const horizontal = dx * right.x + dz * right.z;
          const forward = (dx * up.x + dz * up.z) / (up.x ** 2 + up.z ** 2);
          const scale = (0.847 * 54) / Math.hypot(horizontal, forward);
          await pointer(
            page,
            "pointermove",
            81,
            stick.x + horizontal * scale,
            stick.y - forward * scale,
          );
          await page.clock.runFor(280);
        }
        throw new Error(`Did not reach W3 waypoint ${JSON.stringify(target)}`);
      }
      async function stop() {
        await pointer(page, "pointerup", 81, stick.x, stick.y);
        moving = false;
      }
      function landmarkPosition(id: string) {
        const mark = whaleLevel.landmarks.find((mark) => mark.id === id);
        if (!mark) throw new Error(`Missing W3 landmark ${id}`);
        return mark.pos;
      }

      if (path === "surface") {
        await swimTo(landmarkPosition("quiet-mid"));
        const wide = await swimTo(landmarkPosition("quiet-arc"));
        expect(
          wide.actors?.every(
            ({ dive }) => dive.depth === 0 && dive.breath === 1,
          ),
        ).toBe(true);
        expect(wide.occupied).not.toContain("reef-current");
        await captureWhaleArt(page, info, "W3-surface-channel");
        await swimTo(landmarkPosition("quiet-bend"));
      } else {
        const first = whaleLevel.zones.find(({ id }) => id === "reef-current");
        const second = whaleLevel.zones.find(
          ({ id }) => id === "reef-current-east",
        );
        if (first?.kind !== "current" || second?.kind !== "current")
          throw new Error("Missing W3 current lanes");
        const ability = await page.locator("#formation").boundingBox();
        if (!ability) throw new Error("Missing dive control");
        const divePointer = (edge: "down" | "up") =>
          pointer(
            page,
            `pointer${edge}`,
            82,
            ability.x + ability.width / 2,
            ability.y + ability.height / 2,
            "#formation",
          );
        const { entry: firstEntry, exit: firstExit } = currentGuide(first);
        await swimTo({
          x: firstEntry.x - first.direction.x * 12,
          z: firstEntry.z - first.direction.z * 12,
        });
        await divePointer("down");
        const firstRide = await swimTo(firstExit);
        expect(firstRide.occupied).toContain(first.id);
        await expect(page.locator("#detail")).toContainText("上浮等队尾");
        const eddyChoice = page.getByText("礁间静水 · 换气", { exact: true });
        const currentChoice = page.getByText("第二段顺流入口", { exact: true });
        await expect(eddyChoice).toBeVisible();
        await expect(currentChoice).toBeVisible();
        if (path === "continuous") {
          const [eddyBox, currentBox] = await Promise.all([
            eddyChoice.boundingBox(),
            currentChoice.boundingBox(),
          ]);
          if (!eddyBox || !currentBox) throw new Error("Missing W3 choices");
          expect(eddyBox.x).toBeGreaterThanOrEqual(
            currentBox.x + currentBox.width,
          );
          await captureWhaleArt(page, info, "W3-two-choices");
        }
        if (path === "regroup") await divePointer("up");

        const mid = await swimTo(landmarkPosition("current-eddy"));
        expect(mid.occupied).toContain("reef-eddy");
        await expect(page.locator("#notice")).toHaveText("礁间静水");
        if (path === "regroup") {
          await stop();
          await page.clock.runFor(5300);
          await expect(page.locator("#detail")).toContainText("水面就绪 6/6");
          expect(
            (await sample(page)).actors?.every(
              ({ dive }) => dive.depth === 0 && dive.breath === 1,
            ),
          ).toBe(true);
          await captureWhaleArt(page, info, "W3-eddy-six-ready");
          await divePointer("down");
        } else {
          expect(mid.actors?.every(({ dive }) => dive.depth > 0)).toBe(true);
        }

        const { entry, exit } = currentGuide(second);
        const secondRide = await swimTo({
          x: entry.x + (exit.x - entry.x) * 0.74,
          z: entry.z + (exit.z - entry.z) * 0.74,
        });
        expect(secondRide.occupied).toContain(second.id);
        await expect(page.locator("#notice")).toHaveText(
          "正在借流 · 第二段顺流",
        );
        if (path === "continuous")
          await captureWhaleArt(page, info, "W3-second-current");
        await divePointer("up");
      }
      await swimTo(landmarkPosition("merge-here"));
      await swimTo({ x: 64, z: 1380 });
      await stop();
      const saved = await sample(page);
      expect(saved).toMatchObject({
        checkpoint: "C2",
        route: "quiet",
        phase: "playing",
      });
      expect(saved.actors).toHaveLength(6);
      expect(
        saved.actors?.every(
          ({ dive, status }) => dive.depth === 0 && status === "following",
        ),
      ).toBe(true);
    });
  }

  test("WH-A11 an incompatible whale save opens the recovery entry", async ({
    page,
  }) => {
    await openMenu(page, "/?diagnostics");
    await seedWhale(
      page,
      { ...podAt({ x: 40, z: 500 }), levelRevision: "whale-incompatible" },
      "C1",
    );
    await enterWhaleChapter(page);
    await expect(page.locator('[data-continue="journey"]')).toBeHidden();
    const panel = page.locator("#panel");
    await expect(panel).toContainText("鲸航程存档无法继续");
    await panel.getByRole("button", { name: "开始新航程" }).click();
    await expect(page.locator("#hud")).toBeVisible();
    await expect
      .poll(async () => (await sample(page)).z)
      .toBe(whaleLevel.spawn.z);
  });

  test("WH-A11 a stale whale landing cannot replace a run saved in another tab", async ({
    page,
    context,
  }) => {
    const other = await context.newPage();
    await openMenu(other);
    await page.bringToFront();
    await openMenu(page, "/?diagnostics");
    const checkpoint = whaleTrip("journey", "quiet").checkpoints[1];
    if (!checkpoint || checkpoint.state.species !== "whale")
      throw new Error("Missing W3 checkpoint");
    const landing: WhaleState = {
      ...checkpoint.state,
      segmentId: "W4",
      actors: podAt({ x: 80, z: 1560 }).actors,
    };
    await seedWhale(page, landing, "C2");
    await enterWhaleChapter(page);
    const beforeArrival = Date.UTC(2026, 0, 1);
    await page.clock.install({ time: beforeArrival });
    await page.clock.pauseAt(beforeArrival + 30_000);
    await page
      .getByRole("button", { name: "从检查点继续", exact: true })
      .dispatchEvent("click");
    await expect(page.locator("#hud")).toBeVisible();
    await seedWhale(other, checkpoint.state, "C2", "b".repeat(32));
    await page.clock.runFor(96);
    await expect(page.locator("#skip-landing")).toBeVisible();
    await page.locator("#skip-landing").dispatchEvent("click");
    await expect(page.locator("#panel-note")).toHaveText(
      "存档已被更新，本次结果未写入。",
    );
    await page.clock.resume();
    await page.reload();
    await enterSpeciesMenu(page);
    await enterWhaleChapter(page);
    await expect(page.locator("#panel-text")).toContainText("C2");
    await other.close();
  });

  for (const checkpoint of ["C1", "C2"] as const) {
    test(`WH-A08 ${checkpoint} retry restores the snapshot and default camera`, async ({
      page,
    }) => {
      await page.addInitScript(() =>
        localStorage.setItem(
          "feather-tide-settings-v1",
          JSON.stringify({ reduced: true, music: false }),
        ),
      );
      await page.clock.install();
      await openMenu(page, "/?diagnostics");
      const routeCheckpoint = whaleTrip("journey", "quiet").checkpoints.find(
        ({ id }) => id === checkpoint,
      );
      if (!routeCheckpoint || routeCheckpoint.state.species !== "whale")
        throw new Error(`Missing ${checkpoint} waypoint`);
      const rescue = checkpoint === "C1";
      const actors = podAt(
        rescue ? { x: 92, z: 840 } : { x: 80, z: 1430 },
      ).actors;
      const state: WhaleState = {
        ...routeCheckpoint.state,
        segmentId: rescue ? "W2" : "W4",
        energy: rescue ? 0.48 : 0,
        actors: actors.map((actor, i) =>
          rescue && i === actors.length - 1
            ? { ...actor, status: "strayed", rescueTicks: 150 }
            : actor,
        ),
      };
      await seedWhale(page, state, checkpoint);
      await enterWhaleChapter(page);
      // Set the simulated time budget before entering a staged failure state.
      await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 500);
      await page
        .getByRole("button", { name: "从检查点继续", exact: true })
        .dispatchEvent("click");
      await expect(page.locator("#hud")).toBeVisible();
      if (rescue) {
        await pointer(page, "pointerdown", 11, 710, 150);
        await pointer(page, "pointermove", 11, 620, 150);
        await pointer(page, "pointerup", 11, 620, 150);
        await page.clock.runFor(96);
        expect((await sample(page)).camera.yaw).toBeGreaterThan(20);
      }
      await page.clock.runFor(rescue ? 2500 : 96);
      await expect(page.locator("#panel-title")).toHaveText(
        rescue ? "再接应一次" : "停一停，歇一歇",
      );
      await page
        .getByRole("button", { name: `从检查点 ${checkpoint} 重试` })
        .dispatchEvent("click");
      const saved = await page.locator("#game").getAttribute("data-retry");
      expect(saved && JSON.parse(saved)).toEqual({ ...state, energy: 1 });
      await page.clock.runFor(16);
      expect((await sample(page)).camera.yaw).toBe(0);
      await page.clock.resume();
    });
  }

  test("WH-A08 goose and whale journeys use independent saves and the whale score", async ({
    page,
  }) => {
    await openMenu(page);
    async function returnToTitle() {
      await page.locator("#pause-flight").click();
      await page
        .locator("#panel")
        .getByRole("button", { name: "返回标题" })
        .click();
    }
    for (const mode of ["journey"] as const) {
      await page.locator(`[data-start="${mode}"]`).click();
      await expect(page.locator("#formation")).toHaveAccessibleName("结阵");
      await returnToTitle();
      await enterSpeciesMenu(page);
    }
    const score = page.waitForRequest("**/media/deep-blue-drones.mp3");
    await enterWhaleChapter(page);
    await start(page);
    await score;
    await returnToTitle();
    await enterSpeciesMenu(page);
    await enterWhaleChapter(page);
    await start(page);

    await expect
      .poll(() =>
        page.evaluate(async () => {
          const db = await new Promise<IDBDatabase>((resolve, reject) => {
            const request = indexedDB.open("feather-tide", 1);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          try {
            const store = db
              .transaction("checkpoint")
              .objectStore("checkpoint");
            return await Promise.all(
              [
                "journey",
                "roam",
                ["whale", "whale", "journey"],
                ["whale", "whale", "roam"],
              ].map(
                (key) =>
                  new Promise<unknown>((resolve, reject) => {
                    const request = store.get(key);
                    request.onsuccess = () =>
                      resolve(
                        request.result && {
                          kind: request.result.kind,
                          species: request.result.species,
                          mode: request.result.mode,
                        },
                      );
                    request.onerror = () => reject(request.error);
                  }),
              ),
            );
          } finally {
            db.close();
          }
        }),
      )
      .toEqual([
        { kind: "started" },
        undefined,
        { kind: "started", species: "whale", mode: "journey" },
        undefined,
      ]);
  });

  for (const [name, position, segment, tick, label] of [
    ["W1", { x: 0, z: 370 }, "W1", 3540, /船|浅潜/],
    ["W2", { x: 20, z: 716 }, "W2", 6900, /全深|渔网/],
  ] as const satisfies readonly [string, Vec2, string, number, RegExp][]) {
    test(`WH-A05 ${name} hazard remains readable while looking back in low quality`, async ({
      page,
    }, info) => {
      await page.addInitScript(() =>
        localStorage.setItem(
          "feather-tide-settings-v1",
          JSON.stringify({ low: true, reduced: true, music: false }),
        ),
      );
      await openMenu(page, "/?diagnostics");
      const state = {
        ...podAt(position, "journey", tick),
        segmentId: segment,
        triggered: ["C1"],
      };
      await seedWhale(page, state, "C1");
      await enterWhaleChapter(page);
      await page
        .getByRole("button", { name: "从检查点继续", exact: true })
        .click();
      const hazard = page.locator("#hazard-cue");
      await expect(hazard).toBeVisible();
      await expect(hazard).toContainText(label);
      if (name === "W2") {
        await expect(hazard).toContainText("短网口需先对准再缓游");
        await expect(
          page.getByText("短网口 · 对准后缓游", { exact: true }),
        ).toBeVisible();
      }
      await page.screenshot({
        path: info.outputPath(`${name}-default-low.png`),
        scale: "css",
      });
      await mouseOrbit(page, -475, -25);
      await expect(hazard).toBeVisible();
      await expect(hazard).toContainText(label);
      await page.screenshot({
        path: info.outputPath(`${name}-orbit-low.png`),
        scale: "css",
      });
    });
  }

  test("WH-A10 W4 only settles once and exposes the saved result after reload", async ({
    page,
  }, info) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.clock.install();
    await openMenu(page, "/?diagnostics");
    const checkpoint = whaleTrip("journey", "shipping").checkpoints[1];
    if (!checkpoint || checkpoint.state.species !== "whale")
      throw new Error("Missing W3 checkpoint");
    const state = {
      ...checkpoint.state,
      actors: podAt({ x: 80, z: 1560 }).actors.map((actor, index) =>
        index === 5
          ? {
              ...actor,
              dive: {
                ...actor.dive,
                layer: "shallow" as const,
                direction: "up" as const,
                depth: 1,
              },
            }
          : actor,
      ),
      segmentId: "W4",
    };
    await seedWhale(page, state, "C2");
    await enterWhaleChapter(page);
    const resume = page.getByRole("button", {
      name: "从检查点继续",
      exact: true,
    });
    await expect(resume).toBeVisible();
    await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 500);
    await resume.dispatchEvent("click");
    await page.clock.runFor(32);
    await expect(page.locator("#arrival-caption")).toHaveText("等待同伴上浮");
    await expect(page.locator("#arrived")).toHaveText("5/6");
    await expect(page.locator('[data-kind="gathering"]:visible')).toHaveText(
      "同伴 · 正在上浮",
    );
    await page.screenshot({
      path: info.outputPath("W4-waiting.png"),
      scale: "css",
    });
    await page.clock.runFor(2080);
    await expect.poll(async () => (await sample(page)).phase).toBe("landing");
    await expect(page.locator("#arrived")).toHaveText(/6\s*\/\s*6/);
    await expect(page.locator("#flight-cue")).toHaveAttribute(
      "data-kind",
      "landing",
    );
    const badge = await page.locator("#flight-cue").boundingBox();
    expect(badge?.x).toBeGreaterThan(852 * 0.7);
    await expect(page.locator("#marker-layer")).toHaveAttribute(
      "data-camera",
      "Cinematic",
    );
    await expect(page.locator('[data-kind="gathering"]:visible')).toHaveCount(
      0,
    );
    await page.screenshot({
      path: info.outputPath("W4-gathering.png"),
      scale: "css",
    });
    const landed = await sample(page);
    expect(landed.framedWhales).toBe(6);
    await page.locator("#pause-flight").dispatchEvent("click");
    await expect(page.locator("#panel-title")).toHaveText("汇合暂停");
    await page.clock.runFor(4300);
    expect(await sample(page)).toMatchObject({
      tick: landed.tick,
      phase: "landing",
      actors: landed.actors,
      landingProgress: landed.landingProgress,
    });
    await page
      .getByRole("button", { name: "继续汇合", exact: true })
      .dispatchEvent("click");
    const skip = page.locator("#skip-landing");
    await skip.evaluate((button: HTMLButtonElement) => {
      button.click();
      button.click();
    });
    await page.clock.runFor(32);
    await expect.poll(async () => (await sample(page)).phase).toBe("completed");
    expect((await sample(page)).tick).toBe(landed.tick);
    await page.clock.resume();
    await page.reload();
    await enterSpeciesMenu(page);
    await enterWhaleChapter(page);
    await expect(page.locator("#panel")).toContainText(/已汇合|已抵达|已落脚/);
    await expect(page.locator("#panel")).toContainText(/近航道|船道/);
  });

  test("WH-A10 W4 the leader can stop and look back at the actual whale outside", async ({
    page,
  }, info) => {
    test.setTimeout(60_000);
    const pod = offshorePod({ x: 80, z: 1551 });
    await openWhaleArtView(
      page,
      {
        ...pod,
        actors: pod.actors.map((actor, index) =>
          index === 5 ? { ...actor, pos: { x: actor.pos.x, z: 1502 } } : actor,
        ),
      },
      "C2",
    );
    await page.clock.runFor(32);
    const first = await sample(page);
    await expect(page.locator("#arrived")).toHaveText("5/6");
    await expect(page.locator("#arrival-caption")).toHaveText(
      "等待同伴进入汇合区",
    );
    const marker = page.locator('[data-kind="gathering"]:visible');
    await expect(marker).toHaveText("同伴 · 仍在区外");
    await pointer(page, "pointerdown", 81, 711, 180);
    await pointer(page, "pointermove", 81, 262, 174);
    await pointer(page, "pointerup", 81, 262, 174);
    await page.clock.runFor(620);
    const observed = await sample(page);
    expect(observed.camera.yaw).toBeGreaterThan(145);
    expect(observed).toMatchObject({
      x: first.x,
      z: first.z,
      speed: 0,
      phase: "playing",
    });
    await expect(marker).toBeVisible();
    await page.screenshot({
      path: info.outputPath("03-look-back-at-tail.png"),
      scale: "css",
    });
    await page.clock.runFor(2350);
    await expect(page.locator("#arrived")).toHaveText("6/6");
    const joined = await sample(page);
    expect(joined.framedWhales).toBe(6);
    expect(joined.camera.yaw).toBeCloseTo(observed.camera.yaw, 0);
  });

  test("WH-A10 W4 makes room for the pod when the leader stops at the entrance", async ({
    page,
  }, info) => {
    test.setTimeout(45_000);
    await openWhaleArtView(page, offshorePod({ x: 80, z: 1520 }), "C2");
    await page.clock.runFor(120);
    await expect(page.locator("#detail")).toHaveText(
      "向亮水中央再游，给同伴留出空间，再松手滑停",
    );
    await expect(page.locator('[data-kind="gathering"]:visible')).toHaveText(
      "同伴 · 仍在区外",
    );
    await page.screenshot({
      path: info.outputPath("06-make-room.png"),
      scale: "css",
    });
    await pointer(page, "pointerdown", 91, 142, 288);
    await pointer(page, "pointermove", 91, 142, 240);
    await page.clock.runFor(4500);
    await pointer(page, "pointerup", 91, 142, 240);
    await page.clock.runFor(2000);
    await expect(page.locator("#arrived")).toHaveText("6/6");
    expect(await sample(page)).toMatchObject({
      phase: "landing",
      framedWhales: 6,
    });
  });

  for (const [segment, settling] of [
    ["W1", false],
    ["W2", false],
    ["W4", false],
    ["W4", true],
  ] as const) {
    for (const low of [false, true]) {
      const view = settling ? "gathering" : "approach";
      test(`WH-A10 ${segment} records live ${view} performance in ${low ? "low" : "standard"} quality`, async ({
        page,
        browser,
      }, info) => {
        test.setTimeout(60_000);
        await page.setViewportSize({ width: 852, height: 393 });
        await page.addInitScript(
          (low) =>
            localStorage.setItem(
              "feather-tide-settings-v1",
              JSON.stringify({ music: false, low }),
            ),
          low,
        );
        await openMenu(page, "/?diagnostics");
        const position =
          segment === "W1" ? { x: 0, z: 372 } : { x: 75, z: 739 };
        const state =
          segment === "W4"
            ? offshorePod(settling ? { x: 80, z: 1560 } : { x: 78, z: 1482 })
            : {
                ...podAt(position, "journey", segment === "W1" ? 3310 : 8250),
                segmentId: segment,
                triggered: ["C1"],
              };
        await seedWhale(page, state, segment === "W4" ? "C2" : "C1");
        await enterWhaleChapter(page);
        await page
          .getByRole("button", { name: "从检查点继续", exact: true })
          .click();
        await expect(page.locator("#hud")).toBeVisible();
        let report: { samples: number } | undefined;
        await expect
          .poll(
            async () => {
              const value = await page
                .locator("#game")
                .getAttribute("data-performance");
              report = value ? JSON.parse(value) : undefined;
              return report?.samples ?? 0;
            },
            { timeout: 45_000 },
          )
          .toBeGreaterThanOrEqual(settling ? 45 : 150);
        expect(report).toMatchObject({
          segment,
          phase: settling ? "landing" : "playing",
          quality: low ? "low" : "standard",
          medianMs: expect.any(Number),
          p95Ms: expect.any(Number),
          calls: expect.any(Number),
        });
        const gpu = await page
          .locator("canvas")
          .evaluate((canvas: HTMLCanvasElement) => {
            const gl = canvas.getContext("webgl2");
            const debug = gl?.getExtension("WEBGL_debug_renderer_info");
            return debug
              ? String(gl?.getParameter(debug.UNMASKED_RENDERER_WEBGL))
              : undefined;
          });
        await writeFile(
          info.outputPath(
            `${segment}${settling ? "-gathering" : ""}-${low ? "low" : "standard"}.json`,
          ),
          JSON.stringify(
            {
              browser: browser.version(),
              gpu,
              viewport: page.viewportSize(),
              ...report,
            },
            null,
            2,
          ) + "\n",
        );
      });
    }
  }

  test("WH-A08 records W4 rendering diagnostics while the simulation is frozen", async ({
    page,
  }) => {
    await page.addInitScript(() =>
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({ reduced: true, music: false, low: true }),
      ),
    );
    await page.clock.install();
    await openMenu(page, "/?diagnostics");
    const checkpoint = whaleTrip("journey", "shipping").checkpoints[1];
    if (!checkpoint || checkpoint.state.species !== "whale")
      throw new Error("Missing W3 checkpoint");
    await seedWhale(
      page,
      {
        ...checkpoint.state,
        actors: podAt({ x: 80, z: 1560 }).actors,
        segmentId: "W4",
      },
      "C2",
    );
    await enterWhaleChapter(page);
    await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 500);
    await page
      .getByRole("button", { name: "从检查点继续", exact: true })
      .dispatchEvent("click");
    await expect(page.locator("#hud")).toBeVisible();
    await page.clock.runFor(850);
    const state = await sample(page);
    expect(state.phase).toBe("landing");
    const report = await page.locator("#game").getAttribute("data-performance");
    expect(report && JSON.parse(report)).toMatchObject({
      segment: "W4",
      phase: "landing",
      tick: checkpoint.state.tick + 1,
      calls: expect.any(Number),
      triangles: expect.any(Number),
      quality: "low",
    });
    expect(state.tick).toBe(checkpoint.state.tick + 1);
    await page.clock.resume();
  });

  test("WH-A12 W0 holds a fixed heading through all three water layers and looks back from the bay", async ({
    page,
  }, info) => {
    test.setTimeout(55_000);
    const renderErrors: string[] = [];
    page.on("pageerror", (error) => renderErrors.push(error.message));
    page.on("console", (message) => {
      if (
        message.type() === "error" &&
        /WebGLProgram|Shader Error/i.test(message.text())
      )
        renderErrors.push(message.text());
    });
    const epoch = Date.UTC(2026, 0, 1);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.addInitScript(() => {
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({ music: false, reduced: true }),
      );
    });
    await openMenu(page, "/?diagnostics");
    await page.clock.install({ time: epoch });
    await page.clock.pauseAt(epoch + 30_000);
    await whaleEntry(page).dispatchEvent("click");
    await start(page);
    await page.clock.runFor(400);
    const views: Record<string, SwimDiagnostic> = {};
    const shot = async (name: string) => {
      views[name] = await sample(page);
      await page.screenshot({
        path: info.outputPath(`W0-${name}.png`),
        scale: "css",
      });
    };
    const surface = await sample(page);
    await expect(depth(page)).toHaveText("水面");
    await shot("surface");
    const ability = await page.locator("#formation").boundingBox();
    if (!ability) throw new Error("Missing dive control");
    const x = ability.x + ability.width / 2;
    const y = ability.y + ability.height / 2;
    await pointer(page, "pointerdown", 45, x, y, "#formation");
    await page.clock.runFor(1740);
    await expect(depth(page)).toHaveText("浅潜");
    await shot("shallow");
    await page.clock.runFor(2140);
    await expect(depth(page)).toHaveText("深潜");
    await shot("deep");
    const deep = await sample(page);
    expect([deep.x, deep.z, deep.heading, deep.camera.yaw]).toEqual([
      surface.x,
      surface.z,
      surface.heading,
      surface.camera.yaw,
    ]);
    await pointer(page, "pointerup", 45, x, y, "#formation");
    await page.clock.runFor(3640);
    await pointer(page, "pointerdown", 46, 710, 183);
    await pointer(page, "pointermove", 46, 306, 143);
    await pointer(page, "pointerup", 46, 306, 143);
    await page.clock.runFor(150);
    await expect(depth(page)).toHaveText("水面");
    expect(Math.abs((await sample(page)).camera.yaw)).toBeGreaterThan(125);
    await shot("look-back");
    await writeFile(
      info.outputPath("W0-views.json"),
      JSON.stringify(views, null, 2),
    );
    expect(renderErrors).toEqual([]);
  });

  test("WH-A12 W1 frames the moving ship on the original course from the default camera", async ({
    page,
  }, info) => {
    const epoch = Date.UTC(2026, 0, 1);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.addInitScript(() => {
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({ music: false }),
      );
    });
    await openMenu(page, "/?diagnostics");
    await seedWhale(
      page,
      {
        ...podAt({ x: 0, z: shipStartZ }, "journey", shipStartTick),
        segmentId: "W1",
        triggered: ["C1"],
      },
      "C1",
    );
    await enterWhaleChapter(page);
    await page.clock.install({ time: epoch });
    await page.clock.pauseAt(epoch + 30_000);
    await page
      .getByRole("button", { name: "从检查点继续" })
      .dispatchEvent("click");
    await page.clock.runFor(400);
    await expect(hazard(page)).toContainText("减速让船先过");
    await expect(page.getByText("货船 · 向西", { exact: true })).toBeVisible();
    expect((await sample(page)).camera.yaw).toBe(0);
    await page.screenshot({
      path: info.outputPath("W1-default-course.png"),
      scale: "css",
    });
  });

  test("WH-A12 W2 keeps the east net edge and gap readable at the surface, in shallow water and orbiting", async ({
    page,
  }, info) => {
    test.setTimeout(55_000);
    const epoch = Date.UTC(2026, 0, 1);
    const anchor = { x: 75, z: 739 };
    await page.setViewportSize({ width: 852, height: 393 });
    await page.addInitScript(() => {
      localStorage.setItem(
        "feather-tide-settings-v1",
        JSON.stringify({ music: false, reduced: true }),
      );
    });
    await openMenu(page, "/?diagnostics");
    await seedWhale(
      page,
      {
        ...podAt(anchor, "journey", 8250),
        segmentId: "W2",
        triggered: ["C1"],
      },
      "C1",
    );
    await enterWhaleChapter(page);
    await page.clock.install({ time: epoch });
    await page.clock.pauseAt(epoch + 30_000);
    await page
      .getByRole("button", { name: "从检查点继续" })
      .dispatchEvent("click");
    await page.clock.runFor(400);
    const shot = (name: string) =>
      page.screenshot({
        path: info.outputPath(`W2-${name}.png`),
        scale: "css",
      });
    const gap = page.getByText("短网口 · 对准后缓游", { exact: true });
    await expect(gap).toBeVisible();
    await expect(depth(page)).toHaveText("水面");
    await shot("surface");
    const ability = await page.locator("#formation").boundingBox();
    if (!ability) throw new Error("Missing dive control");
    const x = ability.x + ability.width / 2;
    const y = ability.y + ability.height / 2;
    await pointer(page, "pointerdown", 47, x, y, "#formation");
    await page.clock.runFor(1740);
    await expect(depth(page)).toHaveText("浅潜");
    await expect(gap).toBeVisible();
    await shot("shallow");
    await pointer(page, "pointerup", 47, x, y, "#formation");
    await pointer(page, "pointerdown", 48, 680, 165);
    await pointer(page, "pointermove", 48, 829, 155);
    await pointer(page, "pointerup", 48, 829, 155);
    await page.clock.runFor(176);
    expect(Math.abs((await sample(page)).camera.yaw)).toBeGreaterThan(43);
    await expect(gap).toBeVisible();
    await shot("orbit");
  });

  test("WH-A11 whale resource failure offers an in-app retry", async ({
    page,
  }) => {
    let requests = 0;
    await page.route("**/levels/whale.json", async (route) => {
      if (++requests === 1) await route.abort();
      else await route.continue();
    });
    await openMenu(page);
    await whaleEntry(page).click();
    await expect(page.locator("#boot-status")).toContainText(/无法|失败/);
    const retry = page.locator("#retry-load");
    await expect(retry).toBeVisible();
    await retry.click();
    await start(page);
    expect(requests).toBeGreaterThanOrEqual(2);
  });

  test("WH-A11 a WebGL interruption clears dive input until the player resumes", async ({
    page,
  }) => {
    await selectWhale(page);
    await start(page);
    const ability = page.locator("#formation");
    const box = await ability.boundingBox();
    if (!box) throw new Error("Missing dive control");
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await pointer(page, "pointerdown", 1, x, y, "#formation");
    await expect(depth(page)).toContainText("浅潜");

    const canvas = page.locator("canvas");
    await canvas.dispatchEvent("webglcontextlost", { cancelable: true });
    const panel = page.locator("#panel");
    await expect(panel).toContainText("图形连接已中断");
    const beforeRestore = await sample(page);
    await canvas.dispatchEvent("webglcontextrestored");
    await expect(panel).toContainText("航行暂停");
    await expect.poll(async () => (await sample(page)).phase).toBe("paused");
    expect((await sample(page)).tick).toBe(beforeRestore.tick);
    await expect(ability).toHaveAttribute("aria-pressed", "false");
    await panel.getByRole("button", { name: "继续航行" }).click();
    await expect(depth(page)).toHaveText("水面");
  });
});
