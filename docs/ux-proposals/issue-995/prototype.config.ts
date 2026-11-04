import {
  defineConfig,
  devices,
} from "../../../frontend/node_modules/@playwright/test/index.mjs";

export default defineConfig({
  testDir: ".",
  testMatch: "prototype.spec.ts",
  timeout: 90_000,
  workers: 1,
  reporter: "line",
  outputDir: "../../../.artifacts/runtime/tests/issue-995-prototype",
  use: {
    baseURL: "http://127.0.0.1:5175",
    serviceWorkers: "block",
    reducedMotion: "reduce",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
