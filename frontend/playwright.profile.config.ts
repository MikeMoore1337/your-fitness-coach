import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.profile.ts',
  outputDir: '../.artifacts/runtime/tests/playwright-profile',
  workers: 1,
  retries: 0,
  use: {
    baseURL: process.env.PW_BASE_URL ?? 'http://127.0.0.1:4173',
    trace: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
