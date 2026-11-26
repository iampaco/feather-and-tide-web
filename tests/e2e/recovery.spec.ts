import { writeFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import type {
  CheckpointSnapshot,
  Failure,
  GameMode,
  GameState,
  Route,
} from "../../src/core/game";
import type { Vec2 } from "../../src/core/math";
import type { Basis } from "../../src/input/input";
import { contains } from "../../src/levels/geometry";
import { GOOSE } from "../../src/simulation/goose";
import { goalStatus, leaderOf } from "../../src/simulation/world";
import { migration, trip } from "../fixtures/flight";
import { mouseOrbit, pointer } from "../fixtures/pointer";
import { enterSpeciesMenu, openMenu, openTitle } from "../fixtures/menu";

const mode = "journey";
const name = /^斑头雁/;

for (const [energy, condition, level] of [
  [0.55, "", "normal"],
  [0.25, "偏低", "low"],
  [0.12, "危急", "critical"],
] as const) {
  test(`U03 restored stamina remains visible with ${level} feedback`, async ({
    page,
  }, info) => {
    const { current, checkpoint } = trip(mode, "mountain", 265).runtime;
    await openMenu(page, "/?diagnostics");
    await page.getByRole("button", { name }).waitFor();
    await saveSlot(page, { ...checkpoint, state: { ...current, energy } });
    await page.getByRole("button", { name }).click();
    await page.getByRole("button", { name: "从检查点继续" }).click();
    await expect(page.locator("#energy-status")).toBeVisible();
    await expect(page.locator("#energy-status")).toHaveAttribute(
      "data-level",
      level,
    );
    await expect(page.locator("#energy-condition")).toHaveText(condition);
    await expect(
      page.getByRole("progressbar", { name: "体力", exact: true }),
    ).toBeVisible();
    await expect
      .poll(async () =>
        Number(await page.locator("#energy").getAttribute("value")),
      )
      .toBeLessThan(energy);
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
    await page.screenshot({ path: info.outputPath(`stamina-${level}.png`) });
  });
}

async function saveSlot(
  page: Page,
  value: unknown,
  slot: GameMode = mode,
): Promise<void> {
  await page.evaluate(
    ({ record, slot }) =>
      new Promise<void>((resolve, reject) => {
        const request = indexedDB.open("feather-tide", 1);
        request.onupgradeneeded = () =>
          request.result.createObjectStore("checkpoint");
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
          const db = request.result;
          const tx = db.transaction("checkpoint", "readwrite");
          tx.objectStore("checkpoint").put(record, slot);
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
    { record: value, slot },
  );
}

async function enterRescue(page: Page): Promise<void> {
  const { current, checkpoint } = trip(
    mode,
    "mountain",
    hasStrayedGoose,
  ).runtime;
  expect(current.actors.some((actor) => actor.status === "strayed")).toBe(true);
  await openMenu(page, "/?diagnostics");
  await page.getByRole("button", { name }).waitFor();
  await saveSlot(page, { ...checkpoint, state: current });
  await page.getByRole("button", { name }).click();
  await page.getByRole("button", { name: "从检查点继续" }).click();
  await expect
    .poll(async () => (await readFlight(page)).rescue?.ticks)
    .toBeGreaterThan(0);
}

function hasStrayedGoose(state: GameState): boolean {
  return state.actors.some(
    ({ id, status }) => id === "goose-11" && status === "strayed",
  );
}

async function readFlight(page: Page): Promise<{
  phase: string;
  tick: number;
  route: Route | null;
  failure: Failure | null;
  rescue?: { id: string; ticks: number };
  basis: Basis;
  camera: {
    yaw: number;
    pitch: number;
    requestedPitch: number;
    profile: string;
    mode: string;
  };
}> {
  const value = await page.locator("#game").getAttribute("data-flight");
  if (!value) throw new Error("Missing diagnostic flight sample");
  const flight = JSON.parse(value);
  // Optional scenery can finish loading while the simulation is paused.
  delete flight.scenery;
  return flight;
}

async function enterGuidanceSnapshot(
  page: Page,
  snapshot: CheckpointSnapshot,
): Promise<void> {
  await page.setViewportSize({ width: 568, height: 320 });
  await page.clock.install();
  await page.addInitScript(() =>
    localStorage.setItem(
      "feather-tide-settings-v1",
      JSON.stringify({
        mirror: true,
        large: true,
        music: false,
        reduced: true,
      }),
    ),
  );
  await openMenu(page, "/?diagnostics");
  const start = page.getByRole("button", { name });
  await start.waitFor();
  await saveSlot(page, snapshot);
  await start.click();
  const resume = page.getByRole("button", { name: "从检查点继续" });
  await resume.waitFor();
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 5_000);
  await resume.dispatchEvent("click");
  await expect
    .poll(async () => {
      await page.clock.runFor(32);
      const flight = await page.locator("#game").getAttribute("data-flight");
      return flight ? (JSON.parse(flight) as { tick: number }).tick : -1;
    })
    .toBeGreaterThanOrEqual(snapshot.state.tick);
}

test("S2 the heading warning names the ridge before a route is recorded", async ({
  page,
}, info) => {
  const { current, checkpoint } = trip(mode, "mountain", 255).runtime;
  const offset = leaderOf(current).pos.x;
  await enterGuidanceSnapshot(page, {
    ...checkpoint,
    state: {
      ...current,
      actors: current.actors.map((actor) => ({
        ...actor,
        heading: 0,
        pos: { x: actor.pos.x - offset, z: actor.pos.z },
      })),
    },
  });
  await expect(page.locator("#hazard-notice")).toContainText("前方分水岭");
  expect((await readFlight(page)).route).toBeNull();
  const markers = page.locator("#marker-layer");
  await expect(markers.getByText(/短山口/)).toBeVisible();
  await expect(markers.getByText(/长湖路/)).toBeVisible();
  await expect(page.locator("#goose-hazard-announcement")).toContainText(
    "短山口侧风较强。长湖路较稳",
  );
  await page.screenshot({
    path: info.outputPath("ridge-warning.png"),
    scale: "css",
  });
});

test("S4 an exhausted bay offers rest in the warning and landmark", async ({
  page,
}, info) => {
  const { current, checkpoint } = trip(mode, "mountain", 530).runtime;
  const offset = leaderOf(current).pos.x;
  await enterGuidanceSnapshot(page, {
    ...checkpoint,
    state: {
      ...current,
      supply: { ...current.supply, "reserve-supply": 0 },
      actors: current.actors.map((actor) => ({
        ...actor,
        heading: 0,
        pos: { x: actor.pos.x - offset, z: actor.pos.z },
      })),
    },
  });
  await expect(page.locator("#hazard-notice")).toContainText("前方风机");
  await expect(page.locator("#warning-detail")).toHaveText(
    "浅湾补给已用完，可休整",
  );
  await expect(
    page.locator("#marker-layer").getByText("浅湾 · 可休整", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("exhausted-bay.png"),
    scale: "css",
  });
});

test("S4 tiny landscape keeps the urgent rescue and wind route legible together", async ({
  page,
}, info) => {
  const { current, checkpoint } = trip(mode, "mountain", 530).runtime;
  const offset = leaderOf(current).pos.x;
  await enterGuidanceSnapshot(page, {
    ...checkpoint,
    state: {
      ...current,
      energy: 0.12,
      actors: current.actors.map((actor) => {
        const aligned = {
          ...actor,
          heading: 0,
          pos: { x: actor.pos.x - offset, z: actor.pos.z },
        };
        if (actor.id !== "goose-10" && actor.id !== "goose-11") return aligned;
        return {
          ...aligned,
          status: "strayed",
          rescueProgress: 0,
          rescueTicks: actor.id === "goose-10" ? 2150 : 510,
        };
      }),
    },
  });
  await expect(page.locator("#hazard-notice")).toContainText("前方风机");
  await expect(page.locator("#notice")).toHaveText("2 只待接应");
  await expect(
    page.getByRole("timer", { name: "最短剩余接应时间" }),
  ).toHaveText("9 秒");
  expect((await readFlight(page)).rescue?.id).toBe("goose-11");
  await expect(page.locator("#goose-flight-announcement")).toContainText(
    "沿标记飞入接应圈",
  );
  await expect(page.locator("#goose-flight-announcement")).toContainText(
    /待接应同伴在画面/,
  );
  await expect(page.locator("#goose-hazard-announcement")).toContainText(
    /外围航道在画面/,
  );
  const information = await page.locator("#flight-information").boundingBox();
  expect(information?.height).toBeLessThanOrEqual(100);
  expect(
    (await page.locator("#energy-label").boundingBox())?.height,
  ).toBeLessThan(22);
  const announcement = await page
    .locator("#goose-flight-announcement")
    .textContent();
  await page.clock.runFor(1000);
  await expect(page.locator("#rescue-seconds")).toHaveText("8");
  await expect(page.locator("#goose-flight-announcement")).toHaveText(
    announcement ?? "",
  );

  const markers = page.locator("#marker-layer");
  for (const label of ["待接应同伴", "外围直达航道"]) {
    const marker = markers.getByText(label, { exact: true });
    await expect(marker).toBeVisible();
    // WebKit's intersection ratio can round below 1 at fractional pixel sizes.
    expect(
      await marker.evaluate((node) => {
        const bounds = node.getBoundingClientRect();
        return (
          bounds.left >= 0 &&
          bounds.top >= 0 &&
          bounds.right <= innerWidth &&
          bounds.bottom <= innerHeight
        );
      }),
    ).toBe(true);
  }
  const overlaps = await markers.evaluate((layer) => {
    const visible = (node: Element) =>
      getComputedStyle(node).visibility === "visible" &&
      node.getClientRects().length > 0;
    const labels = [...layer.querySelectorAll(".world-label")].filter(visible);
    const ui = [
      ...document.querySelectorAll(
        "#energy-status, #hazard-cue, #flight-cue, #formation",
      ),
    ].filter(visible);
    return labels.flatMap((label, index) => {
      const a = label.getBoundingClientRect();
      return [...ui, ...labels.slice(index + 1)].flatMap((other) => {
        const b = other.getBoundingClientRect();
        const touching =
          a.left < b.right &&
          b.left < a.right &&
          a.top < b.bottom &&
          b.top < a.bottom;
        return touching ? [`${label.textContent} / ${other.textContent}`] : [];
      });
    });
  });
  expect(overlaps).toEqual([]);
  await page.screenshot({
    path: info.outputPath("hazard-and-two-rescues.png"),
    scale: "css",
  });

  await page.setViewportSize({ width: 480, height: 270 });
  await page.clock.runFor(100);
  for (const id of ["hazard-cue", "flight-cue", "energy-status"]) {
    await expect(page.locator(`#${id}`)).toBeInViewport({ ratio: 0.99 });
  }
  const shortLayout = await page.locator("#flight-information").boundingBox();
  expect(shortLayout?.height).toBeLessThanOrEqual(116);
  await expect(page.getByRole("timer")).toHaveText("8 秒");
  await page.screenshot({
    path: info.outputPath("hazard-short-landscape.png"),
    scale: "css",
  });
});

for (const [approach, gap, speed, text] of [
  ["distance", GOOSE.rescueRadius + 5, 0, "飞入接应圈"],
  ["speed", 3, 7, "减速，留在接应圈内"],
  ["ready", 3, GOOSE.slow, "保持缓行"],
] as const) {
  test(`S3 rescue circle explains ${approach}`, async ({ page }, info) => {
    const { current, checkpoint } = trip(
      mode,
      "mountain",
      hasStrayedGoose,
    ).runtime;
    const companion = current.actors.find(({ status }) => status === "strayed");
    if (!companion) throw new Error("Missing S3 rescue target");
    const actors = current.actors.map((actor) =>
      actor.id === current.leaderId
        ? {
            ...actor,
            pos: { x: companion.pos.x + gap, z: companion.pos.z },
            speed,
          }
        : actor,
    );
    await openMenu(page, "/?diagnostics");
    await page.getByRole("button", { name }).waitFor();
    await saveSlot(page, { ...checkpoint, state: { ...current, actors } });
    await page.getByRole("button", { name }).click();
    await page.getByRole("button", { name: "从检查点继续" }).click();
    await expect(page.locator("#detail")).toContainText(text);
    await expect(page.locator("#flight-cue")).toHaveCSS(
      "background-color",
      "rgb(25, 45, 38)",
    );
    await expect(page.locator("#flight-cue").getByRole("timer")).toBeVisible();
    await expect(
      page.locator("#flight-cue").getByText("接应同伴"),
    ).toBeVisible();
    if (approach === "ready")
      await expect(page.locator("#detail")).toContainText(/\d+%/);
    await page.screenshot({
      path: info.outputPath("rescue-ring.png"),
      scale: "css",
    });
  });
}

for (const cue of [
  { stage: "S3", z: 395, text: "前方侧风 · 放慢留意队尾", marker: "队尾" },
  { stage: "S6", z: 779, text: "放慢飞行，先让雁群靠拢", marker: "芦苇落脚地" },
]) {
  test(`${cue.stage} guides the flock before the next event`, async ({
    page,
  }) => {
    const { current, checkpoint } = trip(mode, "mountain", cue.z).runtime;
    await openMenu(page, "/?diagnostics");
    await page.getByRole("button", { name }).waitFor();
    await saveSlot(page, { ...checkpoint, state: current });
    await page.getByRole("button", { name }).click();
    await page.getByRole("button", { name: "从检查点继续" }).click();
    await expect(page.locator("#notice")).toHaveText(cue.text);
    await expect(
      page.locator("#marker-layer").getByText(cue.marker, { exact: true }),
    ).toBeVisible();
    await expect(page.locator("#flight-cue").getByRole("timer")).toBeHidden();
    await expect(page.locator("#arrival-status")).toBeHidden();
  });
}

for (const { z, segment, title } of [
  { z: 412, segment: "S3", title: "前方侧风 · 队尾已靠拢" },
  { z: 789, segment: "S6", title: "队伍齐整 · 飞入芦苇湾" },
]) {
  test(`${segment} recognizes a compact flock in mirrored landscape`, async ({
    page,
  }) => {
    const { current, checkpoint } = trip(mode, "mountain", z).runtime;
    const leader = leaderOf(current);
    await enterGuidanceSnapshot(page, {
      ...checkpoint,
      state: {
        ...current,
        energy: 0.8,
        actors: current.actors.map((actor) => ({
          ...actor,
          pos: {
            x: leader.pos.x + (actor.pos.x - leader.pos.x) * 0.7,
            z: leader.pos.z + (actor.pos.z - leader.pos.z) * 0.7,
          },
          speed: 4,
          status: "following",
        })),
      },
    });
    await expect(page.locator("#notice")).toHaveText(title);
    await expect(page.locator("#arrival-status")).toBeHidden();
    await expect(page.locator("#flight-cue").getByRole("timer")).toBeHidden();
  });
}

test("S4 previews both flyable choices before the rotor warning", async ({
  page,
}, info) => {
  const { current, checkpoint } = trip(mode, "mountain", 507).runtime;
  await enterGuidanceSnapshot(page, {
    ...checkpoint,
    state: { ...current, energy: 0.8 },
  });
  await expect(page.locator("#notice")).toHaveText("风场外围 · 先选航道");
  const markers = page.locator("#marker-layer");
  await expect(
    markers.getByText("外围直达航道", { exact: true }),
  ).toBeVisible();
  await expect(markers.getByText("补给浅湾", { exact: true })).toBeVisible();
  await expect(page.locator("#hazard-notice")).toBeHidden();
  await page.screenshot({
    path: info.outputPath("windfarm-open-choices.png"),
    scale: "css",
  });
});

test("Q04 V2-17 hidden page freezes rescue until explicit resume", async ({
  page,
}, testInfo) => {
  await enterRescue(page);
  await expect(page.locator("#flight-cue").getByRole("timer")).toBeVisible();
  await page.keyboard.down("Space");
  await expect(page.locator("#formation")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const setHidden = (hidden: boolean) =>
    page.evaluate((hide) => {
      Object.defineProperty(document, "hidden", {
        configurable: true,
        value: hide,
      });
      document.dispatchEvent(new Event("visibilitychange"));
    }, hidden);
  const before = await readFlight(page);
  await setHidden(true);
  await expect(page.getByRole("heading", { name: "飞行暂停" })).toBeVisible();
  await page.waitForTimeout(1100);
  await setHidden(false);
  await expect.poll(async () => (await readFlight(page)).phase).toBe("paused");
  const frozen = await readFlight(page);
  if (!before.rescue || !frozen.rescue)
    throw new Error("Expected an active rescue during the entire interruption");
  const frozenTicks = frozen.rescue.ticks;
  expect(frozen.tick - before.tick).toBeLessThan(30);
  expect(frozenTicks).toBe(before.rescue.ticks - (frozen.tick - before.tick));
  await page.waitForTimeout(1100);
  const beforeResume = await readFlight(page);
  expect(beforeResume).toMatchObject({
    tick: frozen.tick,
    rescue: frozen.rescue,
  });
  await expect(page.locator("#formation")).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await page.getByRole("button", { name: "继续飞行" }).click();
  await expect
    .poll(async () => (await readFlight(page)).rescue?.ticks)
    .toBeLessThan(frozenTicks);
  await expect(page.locator("#formation")).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await writeFile(
    testInfo.outputPath("visibility-rescue-ticks.json"),
    JSON.stringify(
      { before, frozen, beforeResume, resumed: await readFlight(page) },
      null,
      2,
    ) + "\n",
  );
  await page.keyboard.up("Space");
});

async function flyTowards(
  page: Page,
  points: Vec2[],
  power: number,
  stop: "rescue" | "lake" | "failure" | "wetland" | "wind-exit",
): Promise<void> {
  await page.evaluate(
    ({ points, power, stop }) => {
      const surface = document.getElementById("game");
      if (!surface) throw new Error("Missing flight surface");
      const center = { x: 120, y: 250 };
      let waypoint = 0;
      let lastTick = -1;
      const touch = (type: string, x: number, y: number) =>
        surface.dispatchEvent(
          new PointerEvent(type, {
            pointerId: 31,
            pointerType: "touch",
            button: 0,
            clientX: x,
            clientY: y,
            bubbles: true,
            cancelable: true,
          }),
        );
      touch("pointerdown", center.x, center.y);
      function steer() {
        const state = JSON.parse(surface?.dataset.flight ?? "{}");
        if (
          state.phase !== "playing" ||
          (stop === "rescue" && state.rescue) ||
          (stop === "lake" && state.route === "lake") ||
          (stop === "wetland" && state.segment === "S6") ||
          (stop === "wind-exit" && state.segment === "S5")
        ) {
          touch("pointerup", center.x, center.y);
          return;
        }
        if (state.tick !== lastTick) {
          lastTick = state.tick;
          let target = points[waypoint];
          while (
            target &&
            waypoint < points.length - 1 &&
            Math.hypot(state.x - target.x, state.z - target.z) < 7
          )
            target = points[++waypoint];
          if (!target) throw new Error("Missing route waypoint");
          const x = state.x - target.x;
          const y = state.z - target.z;
          const radius = (54 * (power * 0.9 + 0.1)) / (Math.hypot(x, y) || 1);
          touch("pointermove", center.x + x * radius, center.y + y * radius);
        }
        requestAnimationFrame(steer);
      }
      requestAnimationFrame(steer);
    },
    { points, power, stop },
  );
}

for (const failure of ["energy", "rescue"] as const) {
  test(`S07 browser restores checkpoint A and allows choosing the lake after ${failure} failure`, async ({
    page,
  }, testInfo) => {
    test.setTimeout(150_000);
    await page.setViewportSize({ width: 852, height: 393 });
    await page.addInitScript(() =>
      localStorage.setItem(
        "feather-tide-settings-v1",
        '{"mapping":"B","music":false}',
      ),
    );
    const checkpoint = trip(mode, "mountain").runtime.checkpoint;
    await openMenu(page, "/?diagnostics");
    await page.getByRole("button", { name }).waitFor();
    await saveSlot(page, checkpoint);
    await page.getByRole("button", { name }).click();
    await page.getByRole("button", { name: "从检查点继续" }).click();
    await expect(page.locator("#game")).toHaveAttribute(
      "data-flight",
      /"phase":"playing"/,
    );
    await flyTowards(
      page,
      [
        { x: -30, z: 272 },
        { x: -30, z: 357 },
        { x: 0, z: 455 },
        { x: 0, z: 850 },
      ],
      failure === "energy" ? 1 : 0.83,
      failure === "energy" ? "failure" : "rescue",
    );
    await pointer(page, "pointerdown", 32, 650, 180);
    await pointer(page, "pointermove", 32, 500, 180);
    await pointer(page, "pointerup", 32, 500, 180);
    await expect
      .poll(async () => (await readFlight(page)).route, { timeout: 35_000 })
      .toBe("mountain");
    if (failure === "rescue")
      await expect
        .poll(async () => (await readFlight(page)).rescue?.ticks ?? 0, {
          timeout: 45_000,
        })
        .toBeGreaterThan(0);
    const dialog = page.getByRole("heading", {
      name: failure === "energy" ? "飞一段，歇一歇" : "再接应一次",
    });
    // The rescue countdown uses simulation ticks, so software-rendered WebKit can take longer than 40 wall-clock seconds.
    await expect(dialog).toBeVisible({ timeout: 80_000 });
    await expect
      .poll(async () => (await readFlight(page)).failure)
      .toBe(failure);
    const failed = await readFlight(page);
    expect(failed.phase).toBe("failed");
    expect(Math.abs(failed.basis.right.z)).toBeGreaterThan(0.4);
    if (failure === "rescue") expect(failed.rescue?.ticks).toBe(0);
    await page.screenshot({ path: testInfo.outputPath("failure.png") });

    await page.getByRole("button", { name: "从检查点 A 重试" }).click();
    const value = await page.locator("#game").getAttribute("data-retry");
    if (!value) throw new Error("Missing retry snapshot from the browser");
    const restored = JSON.parse(value) as GameState;
    expect(restored).toEqual({ ...checkpoint.state, energy: 1 });
    await expect
      .poll(async () => (await readFlight(page)).phase)
      .toBe("playing");
    expect((await readFlight(page)).basis.right.z).toBeCloseTo(0, 5);
    await flyTowards(
      page,
      [
        { x: 45, z: 229 },
        { x: 59, z: 272 },
        { x: 59, z: 362 },
      ],
      0.83,
      "lake",
    );
    await expect
      .poll(async () => (await readFlight(page)).route, { timeout: 26_000 })
      .toBe("lake");
    const reselected = await readFlight(page);
    expect(reselected.failure).toBeNull();
    await page.screenshot({
      path: testInfo.outputPath("lake-after-retry.png"),
    });
    await writeFile(
      testInfo.outputPath("checkpoint-retry.json"),
      JSON.stringify({ checkpoint, failed, restored, reselected }, null, 2) +
        "\n",
    );
  });
}

test.describe("touchscreen orientation", () => {
  test.use({ hasTouch: true });
  const landscape = { width: 852, height: 393 };
  const portrait = { width: 393, height: 852 };

  test("Q04 V2-17–18 portrait pauses the rescue and clears both touches", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(portrait);
    await enterRescue(page);
    await expect
      .poll(() => page.evaluate(() => matchMedia("(pointer: coarse)").matches))
      .toBe(true);
    const resumeFlight = page.getByRole("button", { name: "继续飞行" });
    await expect(resumeFlight).toBeDisabled();
    await expect(page.locator("#panel-summary")).toContainText("接应剩余");
    await expect
      .poll(async () => (await readFlight(page)).phase)
      .toBe("paused");
    const loaded = await readFlight(page);
    await page.setViewportSize(landscape);
    await expect(resumeFlight).toBeEnabled();
    expect(await readFlight(page)).toEqual(loaded);
    await resumeFlight.click();
    await expect(page.locator("#flight-cue").getByRole("timer")).toBeVisible();
    await pointer(page, "pointerdown", 21, 120, 220);
    await pointer(page, "pointermove", 21, 120, 170);
    await pointer(page, "pointerdown", 22, 800, 330, "#formation");
    await expect(page.locator("#stick")).toBeVisible();
    await expect(page.locator("#formation")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await page.setViewportSize(portrait);
    await expect(page.locator("#panel-text")).toContainText("请横置屏幕");
    await expect(resumeFlight).toBeDisabled();
    await expect(page.locator("#stick")).toBeHidden();
    await expect(page.locator("#formation")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect
      .poll(async () => (await readFlight(page)).phase)
      .toBe("paused");
    const frozen = await readFlight(page);
    await page.screenshot({
      path: testInfo.outputPath("portrait-rescue-paused.png"),
    });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(1100);
    expect(await readFlight(page)).toEqual(frozen);

    await page.setViewportSize(landscape);
    await expect(resumeFlight).toBeEnabled();
    const beforeResume = await readFlight(page);
    expect(beforeResume).toEqual(frozen);
    await page.screenshot({
      path: testInfo.outputPath("landscape-rescue-ready.png"),
    });
    await resumeFlight.click();
    await pointer(page, "pointermove", 21, 120, 150);
    await expect
      .poll(async () => (await readFlight(page)).tick)
      .toBeGreaterThan(frozen.tick);
    await expect(page.locator("#stick")).toBeHidden();
    await expect(page.locator("#formation")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await writeFile(
      testInfo.outputPath("orientation-rescue-ticks.json"),
      JSON.stringify(
        { loaded, frozen, beforeResume, resumed: await readFlight(page) },
        null,
        2,
      ) + "\n",
    );
  });

  test("Q04 portrait pauses the landing presentation until explicit resume", async ({
    page,
  }) => {
    await page.setViewportSize(landscape);
    await setupLanding(page);
    await page.getByRole("button", { name: "从检查点继续" }).click();
    await expect(
      page.getByRole("button", { name: "跳过落脚演出" }),
    ).toBeVisible();
    await page.setViewportSize(portrait);
    const resumeLanding = page.getByRole("button", { name: "继续落脚" });
    await expect(page.getByRole("heading", { name: "落脚暂停" })).toBeVisible();
    await expect(resumeLanding).toBeDisabled();
    await page.waitForTimeout(3800);
    expect((await readFlight(page)).phase).toBe("landing");
    await page.setViewportSize(landscape);
    await expect(resumeLanding).toBeEnabled();
    expect((await readFlight(page)).phase).toBe("landing");
    await resumeLanding.click();
    await expect(page.getByRole("heading", { name: "一起抵达" })).toBeVisible({
      timeout: 12_000,
    });
  });
});

async function enterLowEnergyReturn(
  page: Page,
  route: Route,
  depleted = false,
): Promise<void> {
  // Recover a real route's leader, flock, and phase. Set the energy and supply
  // scenario before the app reads it through its normal save entry point.
  const { current, checkpoint } = trip(
    mode,
    route,
    depleted ? 688 : 666,
  ).runtime;
  expect(current.segmentId).toBe("S5");
  expect(current.route).toBe(route);
  await openMenu(page, "/?diagnostics");
  await page.getByRole("button", { name }).waitFor();
  await saveSlot(page, {
    ...checkpoint,
    state: {
      ...current,
      energy: depleted ? 0.28 : 0.22,
      supply: depleted
        ? { ...current.supply, "return-supply": 0, "gallery-supply": 0 }
        : current.supply,
    },
  });
  await page.getByRole("button", { name }).click();
  await page.getByRole("button", { name: "从检查点继续" }).click();
}

for (const strength of ["weak", "strong"] as const) {
  test(`S5 ${strength} gust presents a readable choice in muted reduced-motion landscape`, async ({
    page,
  }, info) => {
    const { current, checkpoint } = trip(mode, "mountain", 704).runtime;
    const zone = migration.zones.find(({ id }) => id === "return-gust");
    if (zone?.kind !== "interference" || !zone.gust)
      throw new Error("Missing S5 gust");
    const { periodTicks, phaseTicks } = zone.gust;
    const weakTick = current.tick - ((current.tick + phaseTicks) % periodTicks);
    await enterGuidanceSnapshot(page, {
      ...checkpoint,
      state: {
        ...current,
        tick:
          strength === "weak"
            ? weakTick
            : weakTick + Math.floor(periodTicks / 2),
        energy: 0.6,
      },
    });
    await expect(page.locator("#notice")).toHaveText(
      strength === "weak"
        ? "阵风已弱 · 可转入背风水道"
        : "前方阵风 · 可结阵直飞",
    );
    const entrance = page
      .locator("#marker-layer")
      .getByText("背风水道入口", { exact: true });
    await expect(entrance).toHaveAttribute("data-marker-placement", "text");
    await page.screenshot({ path: info.outputPath(`s5-${strength}.png`) });
  });
}

for (const route of ["mountain", "lake"] as const) {
  test(`L04 S5 low energy can reach and use return supply after ${route}`, async ({
    page,
  }, testInfo) => {
    await enterLowEnergyReturn(page, route);
    const notice = page.locator("#notice");
    const markers = page.locator("#marker-layer");
    await expect(notice).toContainText("飞向补给水域");
    await expect(markers.getByText("逆风补给", { exact: true })).toHaveCount(1);
    await expect(markers.getByText("逆风补给", { exact: true })).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("low-energy-waypoint.png"),
    });
    await flyTowards(
      page,
      [
        { x: 24, z: 698 },
        { x: 24, z: 722 },
        { x: 0, z: 810 },
      ],
      0.72,
      "wetland",
    );
    await expect(notice).toContainText("正在补给", { timeout: 16_000 });
    await expect
      .poll(async () =>
        Number(await page.locator("#energy").getAttribute("value")),
      )
      .toBeGreaterThan(GOOSE.lowEnergy);
  });
}

test("S4 low energy guidance leads the flock into the optional bay", async ({
  page,
}, info) => {
  const { current, checkpoint } = trip(mode, "mountain", 514).runtime;
  await openMenu(page, "/?diagnostics");
  await page.getByRole("button", { name }).waitFor();
  await saveSlot(page, { ...checkpoint, state: { ...current, energy: 0.22 } });
  await page.getByRole("button", { name }).click();
  await page.getByRole("button", { name: "从检查点继续" }).click();
  await expect(page.locator("#notice")).toContainText("飞向补给水域");
  await expect(
    page.locator("#marker-layer").getByText("保护湿地补给", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator("#marker-layer").getByText("外围直达航道", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("wind-fork.png"),
    scale: "css",
  });
  await flyTowards(
    page,
    [
      { x: -87, z: 565 },
      { x: -89, z: 614 },
      { x: -57, z: 675 },
    ],
    0.65,
    "wind-exit",
  );
  await expect(page.locator("#notice")).toContainText("正在补给", {
    timeout: 26_000,
  });
  await expect
    .poll(async () =>
      Number(await page.locator("#energy").getAttribute("value")),
    )
    .toBeGreaterThan(GOOSE.lowEnergy);
  await page.screenshot({
    path: info.outputPath("bay-refill.png"),
    scale: "css",
  });
});

for (const wide of [false, true]) {
  test(
    wide
      ? "desktop wide orbit keeps the S4 warning and rescue visible when looking behind"
      : "S4 the wind warning leaves the active rescue cue and direction visible",
    async ({ page, isMobile }, info) => {
      test.skip(wide && isMobile, "desktop mouse preview");
      const { current, checkpoint } = trip(mode, "mountain", 530).runtime;
      const xOffset = current.actors[0]?.pos.x ?? 0;
      const actors = current.actors.map((member) => {
        const actor = {
          ...member,
          heading: 0,
          pos: { x: member.pos.x - xOffset, z: member.pos.z },
        };
        return actor.id === "goose-11"
          ? {
              ...actor,
              status: "strayed",
              rescueTicks: 1200,
              rescueProgress: 0,
            }
          : actor;
      });
      await page.setViewportSize(
        wide ? { width: 1280, height: 720 } : { width: 568, height: 320 },
      );
      if (wide) await enableWideMouseOrbit(page);
      else await page.clock.install();
      await openMenu(page, "/?diagnostics");
      await page.getByRole("button", { name }).waitFor();
      await saveSlot(page, { ...checkpoint, state: { ...current, actors } });
      await page.getByRole("button", { name }).click();
      const resume = page.getByRole("button", { name: "从检查点继续" });
      if (wide) await resume.click();
      else {
        // The bounds must describe the same instant while the warning is live.
        await resume.waitFor();
        await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 750);
        await resume.dispatchEvent("click");
        await page.clock.runFor(100);
      }
      if (wide) {
        await page.keyboard.down("KeyC");
        await page.keyboard.down("KeyW");
        await mouseOrbit(page, -524, -240, "right");
        await expect
          .poll(async () => Math.abs((await readFlight(page)).camera.yaw))
          .toBeCloseTo(180, 0);
        await expect
          .poll(async () => (await readFlight(page)).camera.requestedPitch)
          .toBeCloseTo(20, 1);
      }
      const warning = page.locator("#hazard-cue");
      const rescue = page.locator("#flight-cue");
      await expect(warning).toContainText("前方风机");
      await expect(rescue.getByRole("timer")).toBeVisible();
      const target = page.locator("#marker-layer").getByText("待接应同伴");
      await expect(target).toBeInViewport({ ratio: 1 });
      const warningBounds = await warning.boundingBox();
      const rescueBounds = await rescue.boundingBox();
      if (!warningBounds || !rescueBounds)
        throw new Error("Missing active cues");
      expect(warningBounds.y + warningBounds.height).toBeLessThan(
        rescueBounds.y,
      );
      if (wide) {
        await page.screenshot({
          path: info.outputPath("wind-warning-and-rescue.png"),
        });
        await page.keyboard.up("KeyW");
        await page.keyboard.up("KeyC");
      }
    },
  );
}

async function enableWideMouseOrbit(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem(
      "feather-tide-settings-v1",
      JSON.stringify({ wideMouseOrbit: true, reduced: true, mapping: "B" }),
    );
  });
}

test("desktop wide orbit looks back at the S3 rescue circle", async ({
  page,
  isMobile,
}, info) => {
  test.skip(isMobile, "desktop mouse preview");
  await page.setViewportSize({ width: 1400, height: 600 });
  await enableWideMouseOrbit(page);
  await enterRescue(page);
  const rescue = page.locator("#flight-cue");
  await expect(rescue.getByRole("timer")).toBeVisible();
  await page.screenshot({ path: info.outputPath("classic-rescue.png") });
  await mouseOrbit(page, -524, -220);
  await expect
    .poll(async () => Math.abs((await readFlight(page)).camera.yaw))
    .toBeCloseTo(180, 0);
  await expect(rescue.getByRole("timer")).toBeVisible();
  await expect(
    page.locator("#marker-layer").getByText("待接应同伴"),
  ).toBeInViewport({ ratio: 1 });
  await page.screenshot({ path: info.outputPath("wide-rescue.png") });
});

test("desktop wide orbit hands the S6 approach over to the landing camera", async ({
  page,
  isMobile,
}, info) => {
  test.skip(isMobile, "desktop mouse preview");
  await page.setViewportSize({ width: 1280, height: 720 });
  await enableWideMouseOrbit(page);
  const { current, checkpoint } = trip(mode, "mountain", 779).runtime;
  await openMenu(page, "/?diagnostics");
  await page.getByRole("button", { name }).waitFor();
  await saveSlot(page, { ...checkpoint, state: current });
  await page.getByRole("button", { name }).click();
  await page.getByRole("button", { name: "从检查点继续" }).click();
  await expect(page.locator("#notice")).toContainText("让雁群靠拢");
  await mouseOrbit(page, 0, -240);
  await expect
    .poll(async () => (await readFlight(page)).camera.profile)
    .toBe("wide");
  await page.screenshot({ path: info.outputPath("wide-approach.png") });
  await page.keyboard.down("KeyW");
  await expect(page.locator("#arrived")).toHaveText("12/12", {
    timeout: 16_000,
  });
  expect((await readFlight(page)).camera.mode).toBe("Cinematic");
  await page.keyboard.up("KeyW");
  await page.screenshot({ path: info.outputPath("wide-landing.png") });
});

test("L04 S5 exhausted supply is marked and the flock can recover in the next safe water", async ({
  page,
}, testInfo) => {
  await enterLowEnergyReturn(page, "mountain", true);
  const notice = page.locator("#notice");
  await expect(notice).toContainText("减速节能");
  await expect(
    page
      .locator("#marker-layer")
      .getByText("逆风补给 · 已用尽", { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("depleted-supply.png") });
  // Follow the marked wide-water approach before continuing to the next safe pool.
  await flyTowards(
    page,
    [
      { x: 2, z: 713 },
      { x: 2, z: 810 },
    ],
    0.83,
    "wetland",
  );
  await expect(notice).toContainText("飞向安全水域", { timeout: 14_000 });
  await expect(notice).toContainText("正在恢复体力", { timeout: 14_000 });
  await expect(page.locator("#energy-status")).toHaveAttribute(
    "data-level",
    "recovering",
  );
  await expect(page.locator("#energy-condition")).toHaveText("恢复中");
  await expect
    .poll(async () =>
      Number(await page.locator("#energy").getAttribute("value")),
    )
    .toBeGreaterThan(GOOSE.lowEnergy);
});

for (const scenario of ["one-outside", "one-strayed"] as const) {
  test(`S08 V2-13 the real landing area waits for ${scenario} and saves once`, async ({
    page,
    isMobile,
  }, testInfo) => {
    test.setTimeout(60_000);
    const selectedMode = "journey";
    const goal = migration.zones.find(({ kind }) => kind === "goal");
    if (!goal) throw new Error("Missing S6 landing area");
    const { current, checkpoint } = trip(
      selectedMode,
      "mountain",
      scenario === "one-outside"
        ? (state) => goalStatus(state, goal).arrived === 11
        : Infinity,
    ).runtime;
    const state: GameState =
      scenario === "one-outside"
        ? current
        : {
            ...current,
            phase: "playing",
            releasedTicks: GOOSE.coastTicks,
            actors: current.actors.map((actor) =>
              actor.id === "goose-11"
                ? {
                    ...actor,
                    pos: leaderOf(current).pos,
                    status: "strayed",
                    rescueProgress: 0,
                    rescueTicks: GOOSE.rescueTicks,
                  }
                : actor.id === current.leaderId
                  ? { ...actor, speed: GOOSE.slow }
                  : actor,
            ),
          };
    expect(
      state.actors.filter(({ pos }) => contains(goal.points, pos)),
    ).toHaveLength(scenario === "one-outside" ? 11 : 12);
    expect(goalStatus(state, goal)).toMatchObject({
      arrived: 11,
      leaderArrived: true,
      canLand: false,
    });

    await page.addInitScript(() => {
      const put = IDBObjectStore.prototype.put;
      IDBObjectStore.prototype.put = function (
        value: unknown,
        key?: IDBValidKey,
      ) {
        const request = put.call(this, value, key);
        if (
          value &&
          typeof value === "object" &&
          "kind" in value &&
          value.kind === "arrived"
        ) {
          this.transaction.addEventListener(
            "complete",
            () => {
              const data = document.documentElement.dataset;
              data.arrivalWrites = String(Number(data.arrivalWrites ?? 0) + 1);
            },
            { once: true },
          );
        }
        return request;
      };
    });
    await page.setViewportSize({ width: 852, height: 393 });
    await page.clock.install();
    await openMenu(page, "/?diagnostics");
    const menuMode = page.getByRole("button", {
      name: /^斑头雁/,
    });
    await menuMode.waitFor();
    await saveSlot(
      page,
      {
        version: 1,
        kind: "checkpoint",
        runId: "c".repeat(32),
        levelRevision: state.levelRevision,
        checkpoint: { ...checkpoint, state },
      },
      selectedMode,
    );
    await menuMode.click();
    const continueFromSave = page.getByRole("button", { name: "从检查点继续" });
    await continueFromSave.waitFor();
    await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 1000);
    await continueFromSave.dispatchEvent("click");
    await page.clock.runFor(64);

    const counter = page.locator("#arrived");
    const skip = page.locator("#skip-landing");
    const writes = page.locator("html");
    await expect(counter).toHaveText("11/12");
    await expect(page.locator("#arrival-status")).toHaveText("等待同伴 11/12");
    if (scenario === "one-outside") {
      await expect(page.locator("#goose-arrival-detail")).toContainText(
        "还有 1 只在落脚区外",
      );
      await expect(
        page.locator("#marker-layer").getByText("未抵达同伴"),
      ).toBeVisible();
    } else {
      await expect(page.locator("#goose-arrival-detail")).toBeHidden();
      await expect(page.locator("#notice")).toHaveText("接应同伴");
    }
    await expect(skip).toBeHidden();
    expect(await writes.getAttribute("data-arrival-writes")).toBeNull();
    const waiting = await readFlight(page);
    expect(waiting.phase).toBe("playing");
    await page.screenshot({ path: testInfo.outputPath("11-of-12.png") });

    for (let i = 0; i < 24 && (await readFlight(page)).phase === "playing"; i++)
      await page.clock.runFor(250);
    const landing = await readFlight(page);
    expect(landing.phase).toBe("landing");
    await expect(counter).toHaveText("12/12");
    await expect(page.locator("#goose-arrival-detail")).toBeHidden();
    await expect(skip).toBeVisible();
    await expect(page.getByRole("button", { name: "镜头复位" })).toBeHidden();
    await expect(page.locator("#energy-status")).toBeHidden();
    await expect(writes).toHaveAttribute("data-arrival-writes", "1");
    await page.screenshot({ path: testInfo.outputPath("12-of-12.png") });
    const pause = page.getByRole("button", { name: "暂停", exact: true });
    for (const key of ["Enter", "Space"]) {
      await pause.dispatchEvent("click");
      await expect(
        page.getByRole("button", { name: "继续落脚" }),
      ).toBeFocused();
      await page.keyboard.press(key);
      await expect(page.getByRole("dialog")).toBeHidden();
      expect((await readFlight(page)).phase).toBe("landing");
    }
    await pause.dispatchEvent("click");
    const skipAction = page
      .getByRole("dialog")
      .getByRole("button", { name: "跳过落脚演出" });
    if (isMobile) await skipAction.focus();
    else await page.keyboard.press("Tab");
    await expect(skipAction).toBeFocused();
    await page.keyboard.press("Enter");
    await page.clock.runFor(64);
    const result = page.getByRole("heading", { name: "一起抵达" });
    await expect(result).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(result).toBeVisible();
    await expect(page.locator("#panel-summary")).toHaveText("12 / 12 只雁落脚");
    expect((await readFlight(page)).tick).toBe(landing.tick);
    await expect(writes).toHaveAttribute("data-arrival-writes", "1");
    await page.clock.resume();
    await page.reload();
    await enterSpeciesMenu(page);
    await menuMode.click();
    await expect(
      page.getByRole("heading", { name: "上次飞行已落脚" }),
    ).toBeVisible();
    await writeFile(
      testInfo.outputPath("landing-gate.json"),
      JSON.stringify(
        {
          scenario,
          selectedMode,
          waiting,
          landing,
          arrivalWrites: 1,
          reloaded: true,
        },
        null,
        2,
      ) + "\n",
    );
  });
}

// Use the real route's recorded checkpoint. For persistence faults only, put
// the test landing polygon at A so the browser can reach landing immediately.
async function setupLanding(page: Page) {
  const checkpoint = trip(mode, "mountain").runtime.checkpoint;
  const area = migration.zones.find((zone) => zone.id === checkpoint.id);
  if (!area) throw new Error("No checkpoint A in the migration");
  const levelRevision = "goose-test-landing-at-a";
  await page.route("**/levels/migration.json", (route) =>
    route.fulfill({
      json: {
        ...migration,
        levelRevision,
        zones: migration.zones.map((zone) =>
          zone.kind === "goal" ? { ...zone, points: area.points } : zone,
        ),
      },
    }),
  );
  await openMenu(page, "/?diagnostics");
  const runId = "a".repeat(32);
  await saveSlot(page, {
    version: 1,
    runId,
    kind: "checkpoint",
    levelRevision,
    checkpoint: {
      ...checkpoint,
      state: { ...checkpoint.state, levelRevision },
    },
  });
  await page.getByRole("button", { name }).click();
  await expect(
    page.getByRole("button", { name: "从检查点继续" }),
  ).toBeVisible();
  return { levelRevision };
}

test("S08 an aborted landing write responds after skip and can be retried without another landing", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const put = IDBObjectStore.prototype.put;
    let abortArrival = true;
    IDBObjectStore.prototype.put = function (
      value: unknown,
      key?: IDBValidKey,
    ) {
      const request = put.call(this, value, key);
      if (
        abortArrival &&
        value !== null &&
        typeof value === "object" &&
        "kind" in value &&
        value.kind === "arrived"
      ) {
        abortArrival = false;
        request.addEventListener("success", () => this.transaction.abort());
      }
      return request;
    };
  });
  await setupLanding(page);
  await page.getByRole("button", { name: "从检查点继续" }).click();
  await page.getByRole("button", { name: "跳过落脚演出" }).click();
  await expect(page.getByRole("heading", { name: "一起抵达" })).toBeVisible();
  await expect(page.locator("#panel-note")).toContainText("落脚结果保存失败");
  const flight = page.locator("#game");
  await expect(flight).toHaveAttribute("data-flight", /"phase":"completed"/);
  const landed = await flight.getAttribute("data-flight");
  await page.getByRole("button", { name: "重试保存结果" }).click();
  await expect(page.locator("#panel-note")).toBeEmpty();
  await expect(page.locator("#panel-summary")).toHaveText("12 / 12 只雁落脚");
  expect(await flight.getAttribute("data-flight")).toBe(landed);
  await page.reload();
  await enterSpeciesMenu(page);
  await page.getByRole("button", { name }).click();
  await expect(
    page.getByRole("heading", { name: "上次飞行已落脚" }),
  ).toBeVisible();
});

test("S07 stale landing does not overwrite a newer run", async ({ page }) => {
  const { levelRevision } = await setupLanding(page);
  await saveSlot(page, {
    version: 1,
    runId: "b".repeat(32),
    levelRevision,
    kind: "arrived",
    route: "lake",
    tick: 6500,
  });
  await page.getByRole("button", { name: "从检查点继续" }).click();
  await page.getByRole("button", { name: "跳过落脚演出" }).click();
  await expect(page.locator("#panel-note")).toContainText("本次结果未写入");
  await page.reload();
  await enterSpeciesMenu(page);
  await page.getByRole("button", { name }).click();
  await expect(page.locator("#panel-text")).toContainText("这次经过长湖路");
});

test("Q04 losing the WebGL context freezes flight until explicit resume", async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "uses Chromium's WEBGL_lose_context");
  await openTitle(page, "/?diagnostics");
  await page.getByRole("button", { name: "练习飞行" }).click();
  await page.getByRole("button", { name: "飞行实验场" }).click();
  await expect(page.getByRole("button", { name: "结阵" })).toBeVisible();
  await page.keyboard.down("KeyW");
  await page.keyboard.down("Space");
  await expect(page.getByRole("button", { name: "结阵" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  // Keep the browser extension available across calls to restore the same context.
  const extension = await page.evaluateHandle(() => {
    const context = document.querySelector("canvas")?.getContext("webgl2");
    return context?.getExtension("WEBGL_lose_context");
  });
  await extension.evaluate((ext) => {
    if (!ext) throw new Error("WEBGL_lose_context unavailable");
    ext.loseContext();
  });
  await expect(
    page.getByRole("heading", { name: "图形连接已中断" }),
  ).toBeVisible();
  const flight = page.locator("#game");
  const frozen = JSON.parse((await flight.getAttribute("data-flight")) ?? "{}");
  await extension.evaluate((ext) => ext?.restoreContext());
  await expect(page.getByRole("heading", { name: "飞行暂停" })).toBeVisible();
  await expect
    .poll(
      async () =>
        JSON.parse((await flight.getAttribute("data-flight")) ?? "{}").phase,
    )
    .toBe("paused");
  expect(
    JSON.parse((await flight.getAttribute("data-flight")) ?? "{}").tick,
  ).toBe(frozen.tick);
  await expect(page.locator("#formation")).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await page.getByRole("button", { name: "继续飞行" }).click();
  await expect
    .poll(
      async () =>
        JSON.parse((await flight.getAttribute("data-flight")) ?? "{}").tick,
    )
    .toBeGreaterThan(frozen.tick);
  await expect(page.getByRole("button", { name: "结阵" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await page.keyboard.up("Space");
  await page.keyboard.up("KeyW");
});
