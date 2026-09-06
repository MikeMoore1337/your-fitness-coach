import { defineConfig, devices } from '@playwright/test';
import { getPlaywrightReporters } from './playwright-reporting';

export default defineConfig({
  testDir: './tests/e2e',
  outputDir: '../.artifacts/runtime/tests/playwright-cross-browser',
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: getPlaywrightReporters(),
  use: {
    baseURL: process.env.PW_BASE_URL ?? 'http://127.0.0.1:4173',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: process.env.PW_EXTERNAL_SERVER
    ? undefined
    : {
        command: 'node ./node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4173',
        url: 'http://127.0.0.1:4173/app',
        reuseExistingServer: !process.env.CI,
      },
});
