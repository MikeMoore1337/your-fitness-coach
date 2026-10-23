import { test, type Browser, type Page } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

type Transition = {
  name: string;
  link: string;
  readySelector: string;
};

const transitions: Transition[] = [
  {
    name: 'Today to Nutrition',
    link: 'Питание',
    readySelector: '.app-section--nutrition .nutrition-day-summary',
  },
  { name: 'Today to Programs', link: 'План', readySelector: '.app-section--programs h1' },
];

async function throttle(page: Page): Promise<void> {
  const client = await page.context().newCDPSession(page);
  await client.send('Network.enable');
  await client.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: 150,
    downloadThroughput: (1_500 * 1_000) / 8,
    uploadThroughput: (750 * 1_000) / 8,
    connectionType: 'cellular3g',
  });
  await client.send('Emulation.setCPUThrottlingRate', { rate: 4 });
}

async function sample(browser: Browser, transition: Transition, revision: string, run: number) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
    reducedMotion: 'reduce',
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  await throttle(page);
  const apiRequests: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/v1/'))
      apiRequests.push(`${request.method()} ${url.pathname}`);
  });
  await installPlatformApi(page, { browserSession: true, workoutStatus: 'planned' });
  await page.goto('/app?section=today', { waitUntil: 'domcontentloaded' });
  await page
    .locator('[data-testid="today-dashboard"], .app-section--today h1')
    .first()
    .waitFor({ state: 'visible' });
  await page.evaluate(() => {
    performance.clearResourceTimings();
  });
  apiRequests.length = 0;
  const start = await page.evaluate(() => performance.now());
  await page.getByRole('link', { name: transition.link, exact: true }).click();
  await page
    .locator(transition.readySelector)
    .first()
    .waitFor({ state: 'visible', timeout: 30_000 });
  const routeReadyMs = await page.evaluate((startTime) => performance.now() - startTime, start);
  const resources = await page.evaluate(() =>
    performance
      .getEntriesByType('resource')
      .map((entry) => entry as PerformanceResourceTiming)
      .filter((entry) => /\.js(?:\?|$)/.test(new URL(entry.name).pathname)),
  );
  await context.close();
  return {
    revision,
    mode: 'transition',
    transition: transition.name,
    run,
    routeReadyMs,
    jsCount: resources.length,
    jsEncodedBytes: resources.reduce((sum, resource) => sum + resource.encodedBodySize, 0),
    apiRequests,
    apiCounts: apiRequests.reduce<Record<string, number>>((counts, path) => {
      counts[path] = (counts[path] ?? 0) + 1;
      return counts;
    }, {}),
  };
}

test('V11 private-route client transitions', async ({ browser }) => {
  const runs = Number(process.env.V11_PROFILE_RUNS ?? 5);
  const revision = process.env.V11_PROFILE_REVISION ?? 'unknown';
  const samples = [];
  for (const transition of transitions) {
    for (let run = 1; run <= runs; run += 1) {
      samples.push(await sample(browser, transition, revision, run));
    }
  }
  const outputPath = process.env.V11_PROFILE_OUT;
  if (outputPath) {
    const { writeFileSync } = await import('node:fs');
    writeFileSync(outputPath, JSON.stringify({ runs, revision, samples }, null, 2));
  }
  console.log(`V11_TRANSITION_PROFILE ${JSON.stringify({ runs, revision, samples })}`);
});
