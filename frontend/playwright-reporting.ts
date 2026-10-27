import type { ReporterDescription } from '@playwright/test';

export function getPlaywrightReporters(): ReporterDescription[] {
  const nativeReporter: ReporterDescription = [process.env.CI ? 'github' : 'list'];
  const resultDirectory = process.env.ALLURE_RESULTS_DIR;
  if (!resultDirectory) return [nativeReporter];

  const reporter = process.env.ALLURE_PLAYWRIGHT_REPORTER_PATH ?? 'allure-playwright';
  return [nativeReporter, [reporter, { resultsDir: resultDirectory }]];
}
