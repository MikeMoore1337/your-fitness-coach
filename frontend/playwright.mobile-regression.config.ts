import { defineConfig, devices } from '@playwright/test';
import { getPlaywrightReporters } from './playwright-reporting';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'mobile-ui-regression.spec.ts',
  grep: /@critical/,
  snapshotPathTemplate: '{testDir}/{testFileName}-snapshots/{projectName}/{platform}/{arg}{ext}',
  outputDir: '../.artifacts/runtime/tests/playwright-mobile-regression',
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: getPlaywrightReporters(),
  expect: {
    toHaveScreenshot: {
      animations: 'disabled',
      caret: 'hide',
      scale: 'css',
    },
  },
  use: {
    baseURL: process.env.PW_BASE_URL ?? 'http://127.0.0.1:4173',
    trace: 'on-first-retry',
    serviceWorkers: 'block',
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
  },
  projects: [
    {
      name: 'mobile-chromium',
      use: {
        ...devices['iPhone 13'],
        browserName: 'chromium',
        viewport: { width: 390, height: 844 },
      },
    },
    {
      name: 'mobile-webkit',
      use: {
        ...devices['iPhone 13'],
        browserName: 'webkit',
        viewport: { width: 390, height: 844 },
      },
    },
  ],
  webServer: process.env.PW_EXTERNAL_SERVER
    ? undefined
    : {
        command: 'node ./node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4173',
        url: 'http://127.0.0.1:4173/app',
        reuseExistingServer: !process.env.CI,
      },
});
