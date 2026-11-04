import {
  defineConfig,
  devices,
} from "../../../frontend/node_modules/@playwright/test/index.mjs";

export default defineConfig({
  testDir: ".",
  testMatch: "prototype.spec.ts",
  timeout: 120_000,
  workers: 2,
  reporter: "line",
  outputDir: "../../../.artifacts/runtime/tests/issue-833-prototype",
  use: {
    baseURL: "http://127.0.0.1:5178",
    serviceWorkers: "block",
    reducedMotion: "reduce",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
