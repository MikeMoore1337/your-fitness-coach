import { defineConfig, devices } from '@playwright/test';
import { getPlaywrightReporters } from './playwright-reporting';

const baseURL = process.env.PW_BASE_URL ?? 'http://127.0.0.1:4179';
const parsedBaseURL = new URL(baseURL);
const serverPort = parsedBaseURL.port || (parsedBaseURL.protocol === 'https:' ? '443' : '80');

export default defineConfig({
  testDir: './tests/integration',
  testMatch: 'migrated-stack.spec.ts',
  outputDir: '../.artifacts/runtime/tests/playwright-migrated-stack',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: getPlaywrightReporters(),
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env.PW_EXTERNAL_SERVER
    ? undefined
    : {
        command: `python -m uvicorn fitminiapp_api.main:app --app-dir backend --host 127.0.0.1 --port ${serverPort}`,
        cwd: '..',
        url: `${baseURL}/health/ready`,
        reuseExistingServer: false,
        timeout: 60_000,
      },
});
