import { defineConfig, devices } from '@playwright/test';
import { getPlaywrightReporters } from './playwright-reporting';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'mobile-ui-regression.spec.ts',
  grep: /@extended/,
  snapshotPathTemplate: '{testDir}/{testFileName}-snapshots/{projectName}/{platform}/{arg}{ext}',
  outputDir: '../.artifacts/runtime/tests/playwright-mobile-regression-extended',
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: getPlaywrightReporters(),
  use: {
    baseURL: process.env.PW_BASE_URL ?? 'http://127.0.0.1:4173',
    trace: 'on-first-retry',
    serviceWorkers: 'block',
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
  },
  projects: [
    {
      name: 'mobile-firefox',
      use: {
        ...devices['Desktop Firefox'],
        browserName: 'firefox',
        viewport: { width: 390, height: 844 },
        hasTouch: true,
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
