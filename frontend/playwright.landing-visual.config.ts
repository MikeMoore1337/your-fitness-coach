import { defineConfig } from '@playwright/test';
const previewPort = process.env.PW_PREVIEW_PORT ?? '4176';
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: ['landing-approved-visual.spec.ts', 'landing-frozen-visual.spec.ts'],
  outputDir: '../.artifacts/tasks/895/evidence/visual-test-output',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30000,
  reporter: [['list']],
  updateSnapshots: 'none',
  webServer: process.env.PW_EXTERNAL_SERVER
    ? undefined
    : {
        command: `node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port ${previewPort} --strictPort`,
        url: `http://127.0.0.1:${previewPort}`,
        reuseExistingServer: false,
      },
  use: {
    baseURL: process.env.PW_BASE_URL ?? `http://127.0.0.1:${previewPort}`,
    deviceScaleFactor: 1,
    trace: 'retain-on-failure',
  },
});
