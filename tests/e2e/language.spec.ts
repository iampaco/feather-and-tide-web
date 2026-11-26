import { expect, test } from "@playwright/test";
import { languageKey } from "../../src/i18n/language";
import { trip } from "../fixtures/flight";

test.use({ locale: "zh-CN", storageState: { cookies: [], origins: [] } });

test("language defaults to English and switches on the title without reloading", async ({
  page,
}, info) => {
  await page.goto("/");
  const root = page.locator("html");
  const picker = page.locator("#language");
  const open = page.getByRole("button", { name: "Enter game", exact: true });
  await expect(root).toHaveAttribute("lang", "en");
  await expect(picker).toHaveValue("en");
  await expect(picker).toHaveAccessibleName("Language");
  await expect(picker).toBeInViewport({ ratio: 1 });
  await expect(open).toBeVisible();
  await page.screenshot({ path: info.outputPath("english-title.png") });

  const main = await page.locator("#game").elementHandle();
  await picker.selectOption("zh-CN");
  await expect(root).toHaveAttribute("lang", "zh-CN");
  await expect(picker).toHaveAccessibleName("语言");
  await expect(page.getByRole("heading", { name: "羽与潮" })).toBeVisible();
  await expect(page).toHaveTitle("羽与潮 · Feather & Tide");
  expect(await main?.evaluate((node) => node.isConnected)).toBe(true);
  await page.reload();
  await expect(root).toHaveAttribute("lang", "zh-CN");
  await page.getByRole("button", { name: "进入游戏", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "选择同行的生命" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "返回标题", exact: true }).click();
  await picker.selectOption("en");
  await expect(open).toBeVisible();
  await expect(page).toHaveTitle("Feather & Tide");
  await page.reload();
  await expect(picker).toHaveValue("en");
  await expect(open).toBeVisible();
});

test("language falls back to English for an unknown saved value", async ({
  page,
}) => {
  await page.addInitScript(({ key }) => localStorage.setItem(key, "fr"), {
    key: languageKey,
  });
  await page.goto("/");
  await expect(page.locator("#language")).toHaveValue("en");
  await expect(
    page.getByRole("heading", { name: "Feather & Tide" }),
  ).toBeVisible();
});

for (const [entry, species, chapter, ability, stamina] of [
  ["Bar-headed geese", "goose", "Dawn Wetlands", "Formation", "Stamina"],
  ["Whales", "whale", "Leaving the Bay", "Dive", "Energy"],
  ["Reindeer", "reindeer", "Winter Woods", "Wait", "Stamina"],
] as const) {
  test(`English language covers the ${species} journey entry, HUD and pause`, async ({
    page,
    hasTouch,
  }, info) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Enter game", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Choose your companions" }),
    ).toBeVisible();
    const start = page.getByRole("button", {
      name: `${entry} Start journey`,
      exact: true,
    });
    await expect(start).toBeInViewport({ ratio: 1 });
    if (hasTouch) await start.tap();
    else await start.click();
    const hud = page.locator("#hud");
    await expect(hud).toBeVisible({ timeout: 20_000 });
    await expect(hud).toHaveAttribute("data-species", species);
    await expect(page.locator("#segment")).toHaveText(chapter);
    await expect(
      page.getByRole("progressbar", { name: stamina, exact: true }),
    ).toBeVisible();
    await expect(page.locator("#formation")).toHaveAccessibleName(ability);
    const abilityButton = await page.locator("#formation").boundingBox();
    const abilityLabel = await page.locator("#formation-label").boundingBox();
    expect(abilityButton).not.toBeNull();
    expect(abilityLabel).not.toBeNull();
    if (abilityButton && abilityLabel) {
      expect(abilityLabel.x).toBeGreaterThanOrEqual(abilityButton.x + 6);
      expect(abilityLabel.x + abilityLabel.width).toBeLessThanOrEqual(
        abilityButton.x + abilityButton.width - 6,
      );
    }
    await expect(page.locator("#notice")).toBeVisible();
    await expect(hud).not.toContainText(/\p{Script=Han}/u, {
      useInnerText: true,
    });
    if (species === "whale")
      await expect(page.locator("#whale-depth")).toHaveText("Surface");
    await page.screenshot({
      path: info.outputPath(`${species}-english-hud.png`),
    });
    await page.getByRole("button", { name: "Pause", exact: true }).click();
    const pause = page.getByRole("dialog");
    await expect(pause).toContainText(/paused/i);
    await expect(
      pause.getByRole("button", { name: "Back to title" }),
    ).toBeVisible();
    await pause.getByRole("button", { name: "Settings" }).click();
    const settings = page.getByRole("dialog", { name: "Settings" });
    await expect(settings.getByText("Mirror touch controls")).toBeVisible();
    await expect(settings.getByText(`Tap to toggle ${ability}`)).toBeVisible();
  });
}

test("language changes keep an existing journey checkpoint playable", async ({
  page,
}) => {
  const { checkpoint } = trip("journey", "mountain").runtime;
  await page.goto("/?diagnostics");
  await page.locator("#language").selectOption("zh-CN");
  await page.evaluate(
    (snapshot) =>
      new Promise<void>((resolve, reject) => {
        const request = indexedDB.open("feather-tide", 1);
        request.onupgradeneeded = () =>
          request.result.createObjectStore("checkpoint");
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
          const db = request.result;
          const tx = db.transaction("checkpoint", "readwrite");
          tx.objectStore("checkpoint").put(snapshot, "journey");
          tx.onabort = () => reject(tx.error);
          tx.oncomplete = () => {
            db.close();
            resolve();
          };
        };
      }),
    checkpoint,
  );
  await page.locator("#language").selectOption("en");
  await page.getByRole("button", { name: "Enter game", exact: true }).click();
  await page
    .getByRole("button", { name: "Continue from Reedbank", exact: true })
    .click();
  await expect(page.locator("#hud")).toBeVisible();
  await expect(page.locator("#game")).toHaveAttribute(
    "data-flight",
    /"segment":"S2"/,
  );
});

test("English language fits a small landscape flight", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 568, height: 320 });
  await page.goto("/");
  await expect(page.locator("#language")).toBeInViewport({ ratio: 1 });
  await page.getByRole("button", { name: "Enter game", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Bar-headed geese Start journey",
      exact: true,
    })
    .click();
  const cue = page.locator("#flight-cue");
  await expect(cue).toBeInViewport({ ratio: 1 });
  const stamina = page.locator("#energy-status");
  await expect(stamina).toBeInViewport({ ratio: 1 });
  const label = await page.locator("#energy-label").boundingBox();
  const percent = await page.locator("#energy-percent").boundingBox();
  expect(label).not.toBeNull();
  expect(percent).not.toBeNull();
  if (label && percent) expect(label.x + label.width).toBeLessThan(percent.x);
  await page.screenshot({
    path: info.outputPath("english-small-landscape.png"),
    scale: "css",
  });
});
