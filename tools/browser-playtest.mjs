/* global AudioNode, Blob, document, MediaRecorder, PointerEvent, requestAnimationFrame, window, process, console, Buffer */
import { access, mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath, URL } from "node:url";
import { chromium, devices, webkit } from "@playwright/test";
import { preview } from "vite";

const directory = process.argv[2];
if (!directory)
  throw new Error("Pass an output directory for screenshots and metrics");
await mkdir(directory, { recursive: true });
const route = process.argv[3] === "lake" ? "lake" : "mountain";
const platform = process.argv[4] === "chromium" ? "chromium" : "webkit";
const low = process.argv.includes("--low");
const silent = low || process.argv.includes("--silent");
const orbit = process.argv.includes("--s4-orbit");
const lookback = process.argv.includes("--s3-lookback");
const lockedMovement = orbit || lookback;
const audio = process.argv.includes("--audio");
const mode = "journey";
const prefix = [
  platform,
  mode,
  route,
  low ? "low" : "standard",
  ...(silent && !low ? ["silent"] : []),
  ...(orbit ? ["orbit"] : []),
  ...(lookback ? ["lookback"] : []),
].join("-");
const externalUrl = process.env.FEATHER_PLAYTEST_URL;
let server;
let browser;
try {
  if (!externalUrl) {
    await access(new URL("../dist/index.html", import.meta.url));
    server = await preview({
      root: fileURLToPath(new URL("..", import.meta.url)),
      preview: { host: "127.0.0.1", port: 0, strictPort: true },
    });
  }
  const baseUrl = externalUrl ?? server?.resolvedUrls?.local[0];
  if (!baseUrl) throw new Error("The production preview URL is unavailable");
  browser = await (platform === "chromium" ? chromium : webkit).launch();
  const page = await browser.newPage(
    platform === "webkit"
      ? devices["iPhone 15 landscape"]
      : devices["Desktop Chrome"],
  );
  const errors = [];
  const browserDiagnostics = [];
  if (audio) {
    await page.addInitScript(() => {
      const connect = AudioNode.prototype.connect;
      AudioNode.prototype.connect = new Proxy(connect, {
        apply(target, source, args) {
          if (
            args[0] === source.context.destination &&
            !window.stopFlightRecording
          ) {
            // Capture only the generated game mix, using the same signal sent to speakers.
            const capture = source.context.createMediaStreamDestination();
            Reflect.apply(target, source, [capture]);
            const recorder = new MediaRecorder(capture.stream);
            const startedAt = Date.now();
            const chunks = [];
            recorder.ondataavailable = (event) => chunks.push(event.data);
            window.stopFlightRecording = () =>
              new Promise((resolve, reject) => {
                recorder.onerror = (event) => reject(event.error);
                recorder.onstop = async () => {
                  const blob = new Blob(chunks, { type: recorder.mimeType });
                  resolve({
                    startedAt,
                    type: blob.type,
                    bytes: Array.from(new Uint8Array(await blob.arrayBuffer())),
                  });
                };
                recorder.stop();
              });
            recorder.start(1000);
          }
          return Reflect.apply(target, source, args);
        },
      });
    });
  }
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (entry) => {
    if (
      platform === "webkit" &&
      /^Button failed to load, iconName = (?:invalid|pip|airplay)-placard, layoutTraits = \[MacOSLayoutTraits Inline\], src = blob:https?:\/\/\S+$/.test(
        entry.text(),
      )
    ) {
      browserDiagnostics.push(entry.text());
      return;
    }
    if (
      entry.type() === "error" ||
      /THREE.PropertyBinding|Shader Error/.test(entry.text())
    )
      errors.push(entry.text());
  });
  page.on("requestfailed", (request) => {
    if (
      request.failure()?.errorText !== "net::ERR_ABORTED" &&
      request.failure()?.errorText !== "Cancelled"
    )
      errors.push(`${request.url()}: ${request.failure()?.errorText}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 400)
      errors.push(`${response.status()} ${response.url()}`);
  });
  const started = Date.now();
  const flight = page.locator("#game");
  await page.goto(new URL("?diagnostics", baseUrl).href);
  const start = page.getByRole("button", {
    name: /^斑头雁/,
  });
  await start.waitFor();
  const menuReadyMs = Date.now() - started;
  const build = await page.locator('script[type="module"]').getAttribute("src");
  await page.screenshot({ path: join(directory, prefix + "-title.png") });
  if (low || silent || lockedMovement) {
    await page.getByRole("button", { name: "设置" }).click();
    if (low) {
      await page.getByLabel("低画质").check();
      await page.getByLabel("减少动态").check();
    }
    if (silent) {
      await page.getByLabel("配乐", { exact: true }).uncheck();
    }
    if (lockedMovement) await page.getByLabel("移动方向").selectOption("B");
    await page.getByRole("button", { name: "返回", exact: true }).click();
  }
  await start.click();
  await page.getByRole("button", { name: "结阵" }).waitFor();
  await page.getByRole("button", { name: "略过提示" }).click();
  if (audio) await page.waitForTimeout(1500); // Capture the quiet lead-in before takeoff.

  // Exercise the normal DOM input path and read the same snapshots as the HUD.
  await page.evaluate(
    ({ route, mode }) => {
      const root = document.getElementById("game");
      if (!root) throw new Error("Game surface missing");
      const routeX = route === "mountain" ? -30 : 59;
      const points = [
        [0, 152],
        [0, 212],
        [routeX, 272],
        [routeX, 357],
        [0, 455],
        [-55, 532],
        [-55, 653],
        [0, 716],
        [0, 853],
      ];
      const touch = (type, id, x, y, target = root) =>
        target?.dispatchEvent(
          new PointerEvent(type, {
            pointerId: id,
            pointerType: "touch",
            clientX: x,
            clientY: y,
            button: 0,
            bubbles: true,
            cancelable: true,
          }),
        );
      let waypoint = 0;
      let holding = false;
      let previousTick = -1;
      const rescueTiming = {};
      window.playtestRescue = rescueTiming;
      const segments = {};
      window.playtestSegments = segments;
      touch("pointerdown", 11, 105, 247);

      function steer() {
        const state = JSON.parse(root?.dataset.flight ?? "{}");
        if (state.phase !== "playing") {
          touch("pointerup", 11, 105, 247);
          if (holding) touch("pointerup", 12, 0, 0);
          return;
        }
        if (state.tick !== previousTick) {
          previousTick = state.tick;
          segments[state.segment] ??= {
            tick: state.tick,
            energy: state.energy,
          };
          const gap = ([x, z]) => Math.hypot(x - state.x, z - state.z);
          if (gap(points[waypoint]) < 7 && waypoint < points.length - 1)
            waypoint++;
          const rescue = mode === "journey" && state.rescue;
          const target = rescue ? [rescue.x, rescue.z] : points[waypoint];
          const power = rescue ? (gap(target) < 12 ? 0.09 : 0.45) : 0.83;
          // The default camera has screen-right=-X and screen-up=+Z.
          const x = state.x - target[0];
          const y = state.z - target[1];
          if (
            rescue &&
            (rescueTiming.detected
              ? rescue.id === rescueTiming.detected.id
              : state.segment === "S3") &&
            !rescueTiming.rejoined
          ) {
            rescueTiming.detected ??= {
              tick: state.tick,
              id: rescue.id,
              ticksLeft: rescue.ticks,
              notice: document.getElementById("notice")?.textContent,
              detail: document.getElementById("detail")?.textContent,
              marker: Array.from(
                document.querySelectorAll(
                  "#marker-layer .world-label:not([hidden])",
                ),
              ).find((node) => node.textContent === "待接应同伴")?.className,
              camera: document.getElementById("marker-layer")?.dataset.camera,
            };
            const alignment =
              -(Math.sin(state.heading) * x + Math.cos(state.heading) * y) /
              Math.hypot(x, y);
            if (alignment >= Math.cos(Math.PI / 6))
              rescueTiming.turned ??= {
                tick: state.tick,
                gap: Math.hypot(x, y),
              };
            if (rescue.progress > 0)
              rescueTiming.pickup ??= {
                tick: state.tick,
                ticksLeft: rescue.ticks,
                progress: rescue.progress,
                gap: Math.hypot(x, y),
                detail: document.getElementById("detail")?.textContent,
              };
            rescueTiming.last = { tick: state.tick, ticksLeft: rescue.ticks };
          } else if (!rescue && rescueTiming.pickup && !rescueTiming.rejoined) {
            rescueTiming.rejoined = {
              tick: state.tick,
              notice: document.getElementById("notice")?.textContent,
              ticksLeft:
                rescueTiming.last.ticksLeft -
                (state.tick - rescueTiming.last.tick),
            };
          }
          const radius = (54 * (power * 0.9 + 0.1)) / (Math.hypot(x, y) || 1);
          touch("pointermove", 11, 105 + x * radius, 247 + y * radius);
          const wanted =
            !rescue &&
            (state.segment === "S5" ||
              (state.segment === "S1" && state.z < 180));
          if (wanted !== holding) {
            holding = wanted;
            touch(
              wanted ? "pointerdown" : "pointerup",
              12,
              0,
              0,
              document.getElementById("formation"),
            );
          }
        }
        requestAnimationFrame(steer);
      }
      requestAnimationFrame(steer);
    },
    { route, mode },
  );

  async function lookAround(dx, dy) {
    await page.evaluate(
      ([x, y]) => {
        const surface = document.getElementById("game");
        if (!surface) throw new Error("Game surface missing");
        const bounds = surface.getBoundingClientRect();
        const clientX = bounds.left + bounds.width * 0.72;
        const clientY = bounds.top + bounds.height * 0.47;
        const options = {
          pointerId: 13,
          pointerType: "touch",
          button: 0,
          bubbles: true,
          cancelable: true,
        };
        surface.dispatchEvent(
          new PointerEvent("pointerdown", { ...options, clientX, clientY }),
        );
        surface.dispatchEvent(
          new PointerEvent("pointermove", {
            ...options,
            clientX: clientX + x,
            clientY: clientY + y,
          }),
        );
        surface.dispatchEvent(
          new PointerEvent("pointerup", {
            ...options,
            clientX: clientX + x,
            clientY: clientY + y,
          }),
        );
      },
      [dx, dy],
    );
  }

  const evidence = {};
  for (const [name, field, threshold] of [
    ["wetland", "z", 30],
    ["tailwind", "z", 156],
    ["fork", "z", 229],
    ["branch", "z", 286],
    ["rescue", "z", 434],
    ["warning", "z", 520],
    ["windfarm", "z", 575],
    ["return", "z", 720],
    ["basin-approach", "z", 791],
  ]) {
    await page.waitForFunction(
      ({ field, threshold }) => {
        const state = JSON.parse(
          document.getElementById("game")?.dataset.flight ?? "{}",
        );
        if (state.phase === "failed")
          throw new Error("Flight failed before screenshot");
        return state[field] >= threshold;
      },
      { field, threshold },
      { timeout: 75_000 },
    );
    evidence[name] = {
      observedAt: Date.now(),
      state: JSON.parse((await flight.getAttribute("data-flight")) ?? "{}"),
      notice: await page.locator("#notice").textContent(),
      hazard: await page.locator("#hazard-notice").textContent(),
      detail: await page.locator("#detail").textContent(),
      performance: JSON.parse(
        (await flight.getAttribute("data-performance")) ?? "{}",
      ),
    };
    console.log(
      prefix,
      name,
      evidence[name].state.tick,
      evidence[name].performance,
    );
    await page.screenshot({
      path: join(directory, prefix + "-" + name + ".png"),
    });
    if (lookback && name === "rescue" && mode === "journey") {
      await lookAround(-524, -125);
      await page.waitForFunction(() => {
        const data = JSON.parse(
          document.getElementById("game")?.dataset.flight ?? "{}",
        );
        return data.basis.right.x > 0.99;
      });
      await page
        .locator("#marker-layer")
        .getByText("待接应同伴", { exact: true })
        .waitFor();
      evidence.lookback = {
        state: JSON.parse((await flight.getAttribute("data-flight")) ?? "{}"),
        notice: await page.locator("#notice").textContent(),
      };
      await page.screenshot({
        path: join(directory, prefix + "-rescue-lookback.png"),
      });
      await page.getByRole("button", { name: "镜头复位" }).click();
    }
    if (orbit && name === "windfarm") {
      // Keep the same left-hand gesture through both views so mapping B holds
      // its original world basis while the right hand explores.
      for (const [view, dx, dy] of [
        ["left-low", 190, -125],
        ["right-high", -390, 250],
      ]) {
        await lookAround(dx, dy);
        await page.waitForFunction((direction) => {
          const data = JSON.parse(
            document.getElementById("game")?.dataset.flight ?? "{}",
          );
          return data.basis.right.z * direction > 0.84;
        }, -Math.sign(dx));
        const notice = page.locator("#hazard-notice");
        const outlet = page
          .locator("#marker-layer")
          .getByText(/^(Follow the outer channel|沿外围继续)$/);
        const state = JSON.parse(
          (await flight.getAttribute("data-flight")) ?? "{}",
        );
        const banner = await notice.boundingBox();
        const marker = await outlet.boundingBox();
        if (
          !marker ||
          (state.revision === "goose-p0-5" && !banner) ||
          (banner &&
            banner.x < marker.x + marker.width &&
            marker.x < banner.x + banner.width &&
            banner.y < marker.y + marker.height &&
            marker.y < banner.y + banner.height)
        )
          throw new Error(
            "Wind-farm marker missing or overlapping the warning during " +
              view,
          );
        evidence[view] = {
          state,
          boxes: { banner, marker },
        };
        await page.screenshot({
          path: join(directory, prefix + "-windfarm-" + view + ".png"),
        });
      }
      await page.getByRole("button", { name: "镜头复位" }).click();
    }
  }
  await page
    .getByRole("button", { name: "跳过落脚演出" })
    .waitFor({ timeout: 75_000 });
  if ((await page.locator("#arrived").textContent()) !== "12/12")
    throw new Error("Flight reached landing before the full flock arrived");
  await page.screenshot({ path: join(directory, prefix + "-landing.png") });
  // Let the first birds reach the water while the final companions approach.
  await page.waitForTimeout(2350);
  const skipLanding = page.getByRole("button", { name: "跳过落脚演出" });
  if (await skipLanding.isVisible()) {
    await page.screenshot({
      path: join(directory, prefix + "-landing-settle.png"),
    });
    if (!audio) await skipLanding.click();
  }
  await page.getByRole("heading", { name: "一起抵达" }).waitFor();
  await page.waitForFunction(
    () =>
      JSON.parse(document.getElementById("game")?.dataset.flight || "{}")
        .phase === "completed",
  );
  const completion = JSON.parse(
    (await flight.getAttribute("data-flight")) ?? "{}",
  );
  const rescueTiming = await page.evaluate(() => window.playtestRescue);
  const segments = await page.evaluate(() => window.playtestSegments);
  let audioPath;
  let audioStartedAt;
  if (audio) {
    const recording = await page.evaluate(() => {
      if (!window.stopFlightRecording)
        throw new Error("Game audio was not connected");
      return window.stopFlightRecording();
    });
    if (!recording.bytes.length) throw new Error("Empty game audio recording");
    const extension = recording.type.includes("mp4") ? "m4a" : "webm";
    audioPath = prefix + "-score." + extension;
    audioStartedAt = recording.startedAt;
    await writeFile(join(directory, audioPath), Buffer.from(recording.bytes));
  }
  await page.reload();
  await page.getByRole("button", { name: /^斑头雁/ }).click();
  await page.getByRole("heading", { name: "上次飞行已落脚" }).waitFor();
  const metrics = {
    build,
    platform,
    low,
    silent,
    mapping: lockedMovement ? "B" : "A",
    mode,
    route,
    menuReadyMs,
    completion,
    rescueTiming,
    segments,
    evidence,
    errors,
    browserDiagnostics,
    audioPath,
    audioStartedAt,
  };
  await writeFile(
    join(directory, prefix + ".json"),
    JSON.stringify(metrics, null, 2) + "\n",
  );
  if (
    errors.length ||
    completion.route !== route ||
    completion.phase !== "completed" ||
    (mode === "journey" &&
      (!rescueTiming.detected?.detail?.includes("接应圈") ||
        !rescueTiming.pickup?.detail?.includes("接应中") ||
        (completion.revision !== "goose-p0-5" &&
          !rescueTiming.rejoined?.notice?.includes("接应成功")) ||
        !rescueTiming.detected?.marker?.includes("edge") ||
        !["Follow", "Focus"].includes(rescueTiming.detected?.camera) ||
        !rescueTiming.turned ||
        !rescueTiming.pickup ||
        !rescueTiming.rejoined ||
        rescueTiming.rejoined.ticksLeft <= 0)) ||
    evidence.rescue.state.scenery?.["ENV-012"] !==
      (low ? "procedural" : "model") ||
    evidence.windfarm.state.scenery?.["STR-001"] !==
      (low ? "procedural" : "model")
  ) {
    throw new Error(
      JSON.stringify({
        errors,
        completion,
        rescueDetail: evidence.rescue.detail,
        rescueTiming,
        scenery: evidence.windfarm.state.scenery,
      }),
    );
  }
} finally {
  try {
    await browser?.close();
  } finally {
    await server?.close();
  }
}
