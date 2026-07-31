import { defineConfig } from "@playwright/test";

const browserChannel = process.env.SIFTLANE_E2E_BROWSER_CHANNEL;

export default defineConfig({
  testDir: "./tests",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:5173",
    ...(browserChannel ? { channel: browserChannel } : {}),
    actionTimeout: 10_000,
    trace: process.env.CI ? "on-first-retry" : "off",
  },
});
