import { defineConfig, devices } from "@playwright/test";

const externalBaseUrl = process.env.PLAYWRIGHT_BASE_URL;
const baseURL = externalBaseUrl ?? "http://127.0.0.1:3100";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL,
    trace: "retain-on-failure"
  },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"], channel: process.env.CI ? undefined : "chrome" }
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 7"], channel: process.env.CI ? undefined : "chrome" }
    }
  ],
  webServer: externalBaseUrl ? undefined : {
    command: "npm run start -- --hostname 127.0.0.1 --port 3100",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      COLLECTOR_PREVIEW_UI_ENABLED: "true",
      COLLECTOR_SHADOW_FIXTURES_ENABLED: "true"
    }
  }
});
