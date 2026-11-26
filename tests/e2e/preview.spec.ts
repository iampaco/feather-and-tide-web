import { expect, test } from "@playwright/test";
import { openTitle } from "../fixtures/menu";

test("renders the game title scene and resizes its drawing buffer", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  await openTitle(page);
  await expect(page.getByRole("heading", { name: "羽与潮" })).toBeVisible();
  await expect(page.getByRole("button", { name: "进入游戏" })).toBeVisible();

  const canvas = page.locator("canvas");
  await expect(canvas).toBeVisible();
  for (const viewport of [
    { width: 800, height: 400 },
    { width: 400, height: 800 },
  ]) {
    await page.setViewportSize(viewport);
    const scale = await page.evaluate(() =>
      Math.min(window.devicePixelRatio, 2),
    );
    await expect(canvas).toHaveAttribute(
      "width",
      String(viewport.width * scale),
    );
    await expect(canvas).toHaveAttribute(
      "height",
      String(viewport.height * scale),
    );
  }
  expect(errors).toEqual([]);
});

test("explains what to do when WebGL 2 is unavailable", async ({ page }) => {
  await page.addInitScript(() => {
    HTMLCanvasElement.prototype.getContext = new Proxy(
      HTMLCanvasElement.prototype.getContext,
      {
        apply(getContext, canvas, args) {
          return args[0] === "webgl2"
            ? null
            : Reflect.apply(getContext, canvas, args);
        },
      },
    );
  });

  await openTitle(page);
  await expect(page.getByRole("status")).toContainText("无法启动 WebGL 2");
  await expect(page.getByRole("status")).toContainText("硬件加速设置");
});
