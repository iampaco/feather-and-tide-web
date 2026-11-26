/* global URL, console, document, performance, process */
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { chromium, devices, webkit } from "@playwright/test";

const [directory, baseline, candidate] = process.argv.slice(2);
if (!directory || !baseline || !candidate)
  throw new Error(
    "Pass an output directory and the baseline and candidate server URLs",
  );

await mkdir(directory, { recursive: true });
const phone = devices["iPhone 15 landscape"];
const builds = [
  { label: "baseline", url: baseline },
  { label: "candidate", url: candidate },
];
const slowLink = { latency: 120, bytesPerSecond: 625_000 };

async function open(page, url) {
  await page.goto(new URL("?diagnostics", url).href, {
    waitUntil: "domcontentloaded",
    timeout: 45_000,
  });
  const start = page.getByRole("button", { name: /旅程/ });
  await start.waitFor({ timeout: 45_000 });
  return start;
}

async function sample(browser, build, link) {
  const context = await browser.newContext(phone);
  try {
    const page = await context.newPage();
    const session = await context.newCDPSession(page);
    await session.send("Network.enable");
    await session.send("Network.setCacheDisabled", { cacheDisabled: true });
    if (link) {
      await session.send("Network.emulateNetworkConditions", {
        offline: false,
        latency: link.latency,
        downloadThroughput: link.bytesPerSecond,
        uploadThroughput: link.bytesPerSecond,
      });
    }
    const start = await open(page, build.url);
    const entry = await page.evaluate(() => ({
      menuMs: performance.now(),
      resources: [
        ...performance.getEntriesByType("navigation"),
        ...performance.getEntriesByType("resource"),
      ].map(
        ({
          name,
          transferSize,
          encodedBodySize,
          decodedBodySize,
          startTime,
          responseEnd,
        }) => ({
          path: new URL(name).pathname,
          transferSize,
          encodedBodySize,
          decodedBodySize,
          startTime,
          responseEnd,
        }),
      ),
    }));
    await start.click();
    await page.getByRole("button", { name: "结阵" }).waitFor();
    await page.keyboard.down("KeyW");
    await page.waitForFunction(() => {
      const state = JSON.parse(
        document.getElementById("game")?.dataset.flight ?? "{}",
      );
      return state.phase === "playing" && state.z > 0.01;
    });
    const movableMs = await page.evaluate(() => performance.now());
    await page.keyboard.up("KeyW");
    return { ...entry, movableMs };
  } finally {
    await context.close();
  }
}

async function capture(browser, engine) {
  for (const build of builds) {
    const context = await browser.newContext(phone);
    try {
      const page = await context.newPage();
      const start = await open(page, build.url);
      await start.click();
      await page.getByRole("button", { name: "结阵" }).waitFor();
      await page.waitForFunction(() => {
        const state = JSON.parse(
          document.getElementById("game")?.dataset.flight ?? "{}",
        );
        return (
          state.phase === "playing" &&
          state.tick > 1 &&
          state.x === 0 &&
          state.z === 0
        );
      });
      await page.screenshot({
        path: join(directory, `${engine}-${build.label}-s0.png`),
      });
    } finally {
      await context.close();
    }
  }
}

const results = [];
const chrome = await chromium.launch();
try {
  for (const link of [null, slowLink]) {
    for (let trial = 1; trial <= 3; trial++) {
      const order = trial % 2 ? builds : [...builds].reverse();
      for (const build of order) {
        const measured = await sample(chrome, build, link);
        results.push({ label: build.label, link, trial, ...measured });
        console.log(
          build.label,
          link ?? "loopback",
          trial,
          Math.round(measured.menuMs),
          Math.round(measured.movableMs),
        );
      }
    }
  }
  await capture(chrome, "chromium");
} finally {
  await chrome.close();
}
const safari = await webkit.launch();
try {
  await capture(safari, "webkit");
} finally {
  await safari.close();
}
await writeFile(
  join(directory, "startup.json"),
  JSON.stringify({ builds, viewport: phone.viewport, results }, null, 2) + "\n",
);
