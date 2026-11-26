import { expect, test } from "@playwright/test";
import { enterSpeciesMenu, openMenu, openTitle } from "../fixtures/menu";

test("T17 T23 the title leads to species selection and a guided journey", async ({
  page,
  hasTouch,
}, info) => {
  await page.setViewportSize({ width: 852, height: 393 });
  const mediaRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/assets/media/"))
      mediaRequests.push(request.url());
  });
  await openTitle(page, "/?diagnostics");
  const title = page.getByRole("heading", { name: "羽与潮" });
  const enter = page.getByRole("button", { name: "进入游戏", exact: true });
  const choices = page.getByRole("group", { name: "选择迁徙生物" });
  const goose = choices.getByRole("button", { name: /^斑头雁/ });
  const whale = choices.getByRole("button", { name: /^鲸/ });
  const reindeer = choices.getByRole("button", { name: /^驯鹿/ });
  await expect(title).toBeVisible();
  await expect(enter).toBeVisible();
  await expect(choices).toBeHidden();
  await expect(page.locator("#hud")).toBeHidden();
  await page.screenshot({ path: info.outputPath("title.png"), scale: "css" });
  const selectionArt = Promise.all(
    ["goose", "whale", "reindeer", "open-water", "mountain-valley"].map(
      (name) => page.waitForResponse(`**/assets/entry/${name}.webp`),
    ),
  );
  if (hasTouch) await enter.tap();
  else await page.keyboard.press("Enter");
  await expect(title).toBeHidden();
  await expect(
    page.getByRole("heading", { name: "选择同行的生命" }),
  ).toBeVisible();
  for (const response of await selectionArt) expect(response.ok()).toBe(true);
  await expect(page.getByRole("button", { name: /漫游/ })).toHaveCount(0);
  await expect(page.locator("video")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "开场影片" })).toHaveCount(0);
  expect(mediaRequests).toEqual([]);
  for (const card of [goose, whale, reindeer]) {
    await expect(card).toBeVisible();
    await expect(card).toBeEnabled();
    const bounds = await card.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds?.y).toBeGreaterThanOrEqual(0);
    expect((bounds?.y ?? 0) + (bounds?.height ?? 0)).toBeLessThanOrEqual(393);
  }
  await page.screenshot({
    path: info.outputPath("species-selection.png"),
    scale: "css",
  });
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "设置" });
  await expect(settings).toBeVisible();
  await settings.getByRole("button", { name: "返回", exact: true }).click();
  await expect(choices).toBeVisible();
  await page.getByRole("button", { name: "返回标题", exact: true }).click();
  await expect(enter).toBeFocused();
  await expect(choices).toBeHidden();
  await enterSpeciesMenu(page);
  if (hasTouch) await goose.tap();
  else await goose.click();
  await expect(page.locator("#hud")).toBeVisible();
  await expect(page.locator("#notice")).toContainText("起飞");
  await expect(page.locator("#game")).toHaveAttribute(
    "data-flight",
    /"mode":"journey"/,
  );
  await page.screenshot({
    path: info.outputPath("guided-journey.png"),
    scale: "css",
  });
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  await page.getByRole("button", { name: "返回标题", exact: true }).click();
  await expect(enter).toBeVisible();
  await expect(enter).toBeFocused();
  await expect(choices).toBeHidden();
});

for (const [name, species, segment, ability] of [
  ["鲸", "whale", "W0", "下潜"],
  ["驯鹿", "reindeer", "R0", "等候"],
] as const) {
  test(`T23 a new player can start the ${species} journey first`, async ({
    page,
    hasTouch,
  }) => {
    await openMenu(page, "/?diagnostics");
    const entry = page.getByRole("button", {
      name: `${name} 开始旅程`,
      exact: true,
    });
    if (hasTouch) await entry.tap();
    else await entry.click();
    const hud = page.locator("#hud");
    await expect(hud).toBeVisible({ timeout: 20_000 });
    await expect(hud).toHaveAttribute("data-species", species);
    await expect(page.locator("#formation")).toHaveAccessibleName(
      new RegExp(ability),
    );
    await expect(page.locator("#game")).toHaveAttribute(
      "data-flight",
      new RegExp(
        `"species":"${species}","tick":[1-9]\\d*,"phase":"playing","mode":"journey","segment":"${segment}"`,
      ),
    );
  });
}

for (const viewport of [
  { width: 568, height: 320 },
  { width: 1440, height: 900 },
  { width: 393, height: 852 },
]) {
  test(`T23 species art and controls fit ${viewport.width}x${viewport.height}`, async ({
    page,
  }, info) => {
    await page.setViewportSize(viewport);
    await openMenu(page);
    const cards = page.getByRole("article");
    await expect(cards).toHaveCount(3);
    const first = await cards.first().boundingBox();
    const last = await cards.last().boundingBox();
    expect(first).not.toBeNull();
    expect(last).not.toBeNull();
    if (!first || !last) throw new Error("Missing species panels");
    if (viewport.width > viewport.height) {
      expect(first.y).toBe(last.y);
      expect(first.x).toBeLessThan(last.x);
    } else {
      expect(first.x).toBe(last.x);
      expect(first.y).toBeLessThan(last.y);
    }
    for (const button of await page
      .locator("#species-menu button:visible")
      .all())
      await expect(button).toBeInViewport({ ratio: 1 });
    await page.screenshot({
      path: info.outputPath("species-selection.png"),
      scale: "css",
    });
  });
}

test("T17 old roam slots stay isolated when starting a journey", async ({
  page,
}) => {
  await openMenu(page, "/?diagnostics");
  await expect(page.locator('[data-start="journey"]')).toBeVisible();
  const legacy = {
    version: 1,
    kind: "started",
    mode: "roam",
    runId: "d".repeat(32),
    levelRevision: "goose-p0-6",
  };
  await page.evaluate(async (record) => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("feather-tide", 1);
      request.onupgradeneeded = () =>
        request.result.createObjectStore("checkpoint");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("checkpoint", "readwrite");
      tx.objectStore("checkpoint").put(record, "roam");
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  }, legacy);
  await page.reload();
  await enterSpeciesMenu(page);
  await expect(page.locator('[data-continue="journey"]')).toBeHidden();
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await expect(page.locator("#hud")).toBeVisible();
  await expect(page.locator("#notice")).toContainText("起飞");
  await expect(page.locator("#game")).toHaveAttribute(
    "data-flight",
    /"mode":"journey"/,
  );
  const stored = await page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("feather-tide", 1);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const result = await new Promise<unknown>((resolve, reject) => {
      const request = db
        .transaction("checkpoint")
        .objectStore("checkpoint")
        .get("roam");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    db.close();
    return result;
  });
  expect(stored).toEqual(legacy);
});
