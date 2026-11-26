import { expect, type Page } from "@playwright/test";

export async function openTitle(page: Page, path = "/"): Promise<void> {
  await page.goto(path);
}

export async function enterSpeciesMenu(page: Page): Promise<void> {
  await page.getByRole("button", { name: "进入游戏", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "选择同行的生命" }),
  ).toBeVisible();
}

export async function openMenu(page: Page, path = "/"): Promise<void> {
  await openTitle(page, path);
  await enterSpeciesMenu(page);
}
