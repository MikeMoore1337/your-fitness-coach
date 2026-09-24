import { defineConfig, devices } from '@playwright/test';
import { getPlaywrightReporters } from './playwright-reporting';

const webServers = [];
if (process.env.PW_API_SERVER === 'true') {
  webServers.push({
    command:
      'python -m uvicorn fitminiapp_api.main:app --app-dir backend --host 127.0.0.1 --port 8000',
    cwd: '..',
    url: 'http://127.0.0.1:8000/health/ready',
    reuseExistingServer: false,
    timeout: 60_000,
  });
}
if (!process.env.PW_EXTERNAL_SERVER) {
  webServers.push({
    command: 'node ./node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173/app',
    reuseExistingServer: !process.env.CI,
  });
}

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'ui-quality-sweep.spec.ts',
  outputDir: '../.artifacts/runtime/tests/playwright-ui-quality-sweep',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: getPlaywrightReporters(),
  use: {
    baseURL: process.env.PW_BASE_URL ?? 'http://127.0.0.1:4173',
    trace: 'off',
    serviceWorkers: 'block',
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: webServers,
});
