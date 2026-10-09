import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'landing-approved-visual.spec.ts',
  outputDir: '../.artifacts/tasks/895/evidence/visual-test-output',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30000,
  reporter: [['list']],
  updateSnapshots: 'none',
  use: {
    baseURL: process.env.PW_BASE_URL ?? 'http://127.0.0.1:4176',
    deviceScaleFactor: 1,
    trace: 'retain-on-failure',
  },
});
