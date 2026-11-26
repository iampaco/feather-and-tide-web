import type { Page } from "@playwright/test";

export async function pointer(
  page: Page,
  type: string,
  id: number,
  x: number,
  y: number,
  selector = "#game",
): Promise<void> {
  await page.locator(selector).dispatchEvent(type, {
    pointerId: id,
    pointerType: "touch",
    button: 0,
    clientX: x,
    clientY: y,
    bubbles: true,
    cancelable: true,
  });
}

export async function mouseOrbit(
  page: Page,
  dx: number,
  dy: number,
  button: "left" | "right" = "left",
): Promise<void> {
  const viewport = page.viewportSize();
  if (!viewport) throw new Error("Missing browser viewport");
  const x = Math.round(viewport.width * 0.67);
  const y = Math.round(viewport.height * 0.53);
  await page.mouse.move(x, y);
  await page.mouse.down({ button });
  await page.mouse.move(x + dx, y + dy, { steps: 5 });
  await page.mouse.up({ button });
}
