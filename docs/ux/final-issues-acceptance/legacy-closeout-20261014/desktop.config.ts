import cross from '../../../../frontend/playwright.cross-browser.config';
export default {
  ...cross,
  testDir: __dirname,
  testMatch: 'desktop.spec.ts',
  retries: 0,
  projects: cross.projects!.filter((project) => ['chromium', 'webkit'].includes(project.name!)),
  reporter: [['line'], ['json', { outputFile: process.env.YFC_JSON_REPORT }]],
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR,
  use: { ...cross.use, baseURL: process.env.PW_BASE_URL },
  webServer: undefined,
};
