import { defineConfig, devices } from '@playwright/test';
import { getPlaywrightReporters } from './playwright-reporting';

const webServers = [];
const apiPort = process.env.PW_API_PORT ?? '8000';
const previewPort = process.env.PW_PREVIEW_PORT ?? '4173';
if (process.env.PW_API_SERVER === 'true') {
  webServers.push({
    command: `python -m uvicorn fitminiapp_api.main:app --app-dir backend --host 127.0.0.1 --port ${apiPort}`,
    cwd: '..',
    url: `http://127.0.0.1:${apiPort}/health/ready`,
    reuseExistingServer: false,
    timeout: 60_000,
  });
}
if (!process.env.PW_EXTERNAL_SERVER) {
  webServers.push({
    command: `node ./node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port ${previewPort}`,
    url: `http://127.0.0.1:${previewPort}/app`,
    reuseExistingServer: !process.env.CI,
  });
}

export default defineConfig({
  testDir: './tests/e2e',
  testIgnore: ['**/mobile-ui-regression.spec.ts', '**/ui-quality-sweep.spec.ts'],
  outputDir:
    process.env.PLAYWRIGHT_OUTPUT_DIR ?? '../.artifacts/runtime/tests/playwright-cross-browser',
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: getPlaywrightReporters(),
  use: {
    baseURL: process.env.PW_BASE_URL ?? `http://127.0.0.1:${previewPort}`,
    trace: 'on-first-retry',
    serviceWorkers: 'block',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: webServers,
});
