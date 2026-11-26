import { defineConfig, devices } from "@playwright/test";
import { languageKey } from "./src/i18n/language";

const port = Number(process.env.FEATHER_E2E_PORT ?? 4173);
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests/e2e",
  forbidOnly: Boolean(process.env.CI),
  workers: process.env.CI ? 1 : undefined,
  use: {
    baseURL,
    trace: "retain-on-failure",
    // Existing gameplay assertions use the Chinese copy.
    storageState: {
      cookies: [],
      origins: [
        {
          origin: baseURL,
          localStorage: [{ name: languageKey, value: "zh-CN" }],
        },
      ],
    },
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        channel: process.env.FEATHER_CHROMIUM_CHANNEL,
      },
    },
    {
      name: "desktop-webkit",
      grep: /desktop (keyboard-only|speed tiers|key settings|full orbit|wide orbit)|A01|WH-A|RD-A|T23|language/,
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "mobile-webkit",
      use: { ...devices["iPhone 15 landscape"] },
    },
  ],
  webServer: {
    command: `npm run preview -- --host 127.0.0.1 --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
  },
});
