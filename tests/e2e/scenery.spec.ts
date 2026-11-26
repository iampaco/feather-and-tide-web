import { expect, test, type Page } from "@playwright/test";
import { migration } from "../fixtures/flight";
import { openMenu } from "../fixtures/menu";

const turbine = "**/assets/goose/turbine-v001.glb";

async function enterSceneryFixture(
  page: Page,
  spawn = { x: 0, z: 399 },
  spawnSegment = "S2",
): Promise<void> {
  // Start near the target area with the real geometry and viewport.
  await page.route("**/levels/migration.json", (route) =>
    route.fulfill({
      json: {
        ...migration,
        spawn,
        spawnSegment,
        levelRevision: "goose-test-scenery",
      },
    }),
  );
  await openMenu(page, "/?diagnostics");
  await page.getByRole("button", { name: /^斑头雁/ }).waitFor();
  await expect(page.locator("#game")).toHaveAttribute(
    "data-flight",
    /"scenery":\{"ENV-012":"procedural","STR-001":"procedural"\}/,
  );
}

test("R05 standard scenery downloads after takeoff and retains live gameplay while loading", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (/wind-tree-v001|turbine-v001/.test(request.url()))
      requests.push(request.url());
  });
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(turbine, async (route) => {
    await gate;
    await route.continue();
  });
  await enterSceneryFixture(page);
  expect(requests).toHaveLength(0);
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await page.getByRole("button", { name: "结阵" }).waitFor();
  try {
    await page.keyboard.down("KeyW");
    const game = page.locator("#game");
    await expect(game).toHaveAttribute("data-flight", /"STR-001":"loading"/);
    await page.waitForFunction(() => {
      const flight = JSON.parse(
        document.getElementById("game")?.dataset.flight ?? "{}",
      );
      return flight.z > 401 && flight.phase === "playing";
    });
    release();
    await expect(game).toHaveAttribute(
      "data-flight",
      /"ENV-012":"model","STR-001":"model"/,
    );
    expect(requests).toHaveLength(2);
  } finally {
    release();
    await page.keyboard.up("KeyW");
  }
});

test("R05 a failed optional wind farm model keeps the procedural route running", async ({
  page,
}) => {
  await page.route(turbine, (route) => route.fulfill({ status: 503 }));
  await enterSceneryFixture(page, { x: -55, z: 545 }, "S4");
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await page.getByRole("button", { name: "结阵" }).waitFor();
  await page.keyboard.down("KeyW");
  try {
    await expect(page.locator("#game")).toHaveAttribute(
      "data-flight",
      /"ENV-012":"model","STR-001":"fallback"/,
    );
    await page.waitForFunction(() => {
      const flight = JSON.parse(
        document.getElementById("game")?.dataset.flight ?? "{}",
      );
      return flight.z > 550 && flight.phase === "playing";
    });
    await expect(
      page.locator("#marker-layer").getByText("沿外围继续", { exact: true }),
    ).toBeVisible();
    await expect(
      page.locator("#marker-layer").getByText("保护湿地", { exact: true }),
    ).toBeVisible();
    await page.keyboard.up("KeyW");
    await page.keyboard.down("KeyA");
    await expect(page.locator("#hazard-notice")).toContainText("前方风机", {
      timeout: 10_000,
    });
  } finally {
    await page.keyboard.up("KeyA");
    await page.keyboard.up("KeyW");
  }
});

test("R05 low quality skips both optional requests", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (/wind-tree-v001|turbine-v001/.test(request.url()))
      requests.push(request.url());
  });
  await page.addInitScript(() =>
    localStorage.setItem("feather-tide-settings-v1", '{"low":true}'),
  );
  await enterSceneryFixture(page);
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await page.getByRole("button", { name: "结阵" }).waitFor();
  await page.keyboard.down("KeyW");
  try {
    await page.waitForFunction(() => {
      const flight = JSON.parse(
        document.getElementById("game")?.dataset.flight ?? "{}",
      );
      return flight.z > 402;
    });
    await expect(page.locator("#game")).toHaveAttribute(
      "data-flight",
      /"scenery":\{"ENV-012":"procedural","STR-001":"procedural"\}/,
    );
    expect(requests).toHaveLength(0);
  } finally {
    await page.keyboard.up("KeyW");
  }
});
