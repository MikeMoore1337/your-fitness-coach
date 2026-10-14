import mobile from '../../../../frontend/playwright.mobile-regression.config';
import { resolve } from 'node:path';

export default {
  ...mobile,
  testDir: resolve(__dirname, '../../../../frontend/tests/e2e'),
  testMatch: '**/*.spec.ts',
  grep: undefined,
  projects: mobile.projects!.map((project) => ({ ...project, use: { ...project.use, deviceScaleFactor: 1 } })),
  retries: 0,
  reporter: [['line'], ['json', { outputFile: process.env.YFC_JSON_REPORT }]],
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR,
  use: { ...mobile.use, baseURL: process.env.PW_BASE_URL },
  webServer: undefined,
};
