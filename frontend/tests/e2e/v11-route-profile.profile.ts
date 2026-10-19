import { test, type Browser, type Page } from '@playwright/test';
import { installPlatformApi, type PlatformApiOptions } from './fixtures/platform-api';

type ProfileMode = 'cold' | 'warm';

type Scenario = {
  name: string;
  path: string;
  options: PlatformApiOptions;
  readySelector: string;
  action?: 'continue-workout';
};

type ResourceSample = {
  name: string;
  startTime: number;
  responseEnd: number;
  duration: number;
  transferSize: number;
  encodedBodySize: number;
  decodedBodySize: number;
};

type RunSample = {
  revision: string;
  mode: ProfileMode;
  scenario: string;
  run: number;
  readyMs: number;
  settledMs: number;
  jsCount: number;
  jsTransferBytes: number;
  jsEncodedBytes: number;
  jsDecodedBytes: number;
  jsResources: string[];
  apiRequests: string[];
  apiCounts: Record<string, number>;
  longTasks: number[];
  tbtMs: number;
  lcpMs: number | null;
  resources: ResourceSample[];
};

type ProfileWindow = Window & {
  __v11RouteProfile?: {
    longTasks: number[];
    lcpMs: number | null;
  };
};

const scenarios: Scenario[] = [
  {
    name: 'Today',
    path: '/app?section=today',
    options: { browserSession: true, workoutStatus: 'planned' },
    readySelector: '[data-testid="today-dashboard"], .app-section--today h1',
  },
  {
    name: 'Active Workout',
    path: '/app?section=today',
    options: { browserSession: true, workoutStatus: 'in_progress' },
    readySelector: 'button:has-text("Продолжить тренировку")',
    action: 'continue-workout',
  },
  {
    name: 'Nutrition',
    path: '/app?section=nutrition',
    options: { browserSession: true, workoutStatus: 'planned' },
    readySelector: '.app-section--nutrition .nutrition-day-summary',
  },
  {
    name: 'Programs',
    path: '/app?section=programs',
    options: { browserSession: true, workoutStatus: 'planned' },
    readySelector: '.app-section--programs h1',
  },
  {
    name: 'Exercise Encyclopedia',
    path: '/app?section=catalog',
    options: { browserSession: true, workoutStatus: 'planned' },
    readySelector: '.app-section--catalog .exercise-catalog__filters',
  },
  {
    name: 'Coach OS',
    path: '/coach',
    options: { browserSession: true, trainerActive: true },
    readySelector: '.coach-os-header h1',
  },
];

function profileConfig() {
  const mode = (process.env.V11_PROFILE_MODE ?? 'cold') as ProfileMode;
  if (mode !== 'cold' && mode !== 'warm') throw new Error(`Unsupported profile mode: ${mode}`);
  return {
    mode,
    runs: Number(process.env.V11_PROFILE_RUNS ?? 10),
    revision: process.env.V11_PROFILE_REVISION ?? 'unknown',
    outputPath: process.env.V11_PROFILE_OUT,
    mobile: {
      width: 390,
      height: 844,
      isMobile: true,
      hasTouch: true,
    },
  };
}

async function installObservers(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const state = { longTasks: [] as number[], lcpMs: null as number | null };
    (window as ProfileWindow).__v11RouteProfile = state;
    new PerformanceObserver((list) => {
      state.longTasks.push(...list.getEntries().map((entry) => entry.duration));
    }).observe({ type: 'longtask', buffered: true });
    new PerformanceObserver((list) => {
      const last = list.getEntries().at(-1);
      if (last) state.lcpMs = last.startTime;
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  });
}

async function applyMobileThrottling(page: Page): Promise<void> {
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

async function settle(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
}

async function readSample(
  page: Page,
  revision: string,
  mode: ProfileMode,
  scenario: Scenario,
  run: number,
  apiRequests: string[],
): Promise<RunSample> {
  return page.evaluate(
    ({ revision, mode, scenario, run, apiRequests }) => {
      const resources = performance
        .getEntriesByType('resource')
        .map((entry) => entry as PerformanceResourceTiming)
        .filter((entry) => /\.js(?:\?|$)/.test(new URL(entry.name).pathname))
        .map<ResourceSample>((entry) => ({
          name: new URL(entry.name).pathname.split('/').at(-1) ?? entry.name,
          startTime: entry.startTime,
          responseEnd: entry.responseEnd,
          duration: entry.duration,
          transferSize: entry.transferSize,
          encodedBodySize: entry.encodedBodySize,
          decodedBodySize: entry.decodedBodySize,
        }));
      const metrics = (window as ProfileWindow).__v11RouteProfile ?? {
        longTasks: [],
        lcpMs: null,
      };
      const apiCounts = apiRequests.reduce<Record<string, number>>((counts, path) => {
        counts[path] = (counts[path] ?? 0) + 1;
        return counts;
      }, {});
      return {
        revision,
        mode,
        scenario,
        run,
        readyMs: performance.now(),
        settledMs: performance.now(),
        jsCount: resources.length,
        jsTransferBytes: resources.reduce((sum, resource) => sum + resource.transferSize, 0),
        jsEncodedBytes: resources.reduce((sum, resource) => sum + resource.encodedBodySize, 0),
        jsDecodedBytes: resources.reduce((sum, resource) => sum + resource.decodedBodySize, 0),
        jsResources: resources.map((resource) => resource.name),
        apiRequests,
        apiCounts,
        longTasks: metrics.longTasks,
        tbtMs: metrics.longTasks.reduce((sum, duration) => sum + Math.max(0, duration - 50), 0),
        lcpMs: metrics.lcpMs,
        resources,
      };
    },
    { revision, mode, scenario: scenario.name, run, apiRequests },
  );
}

async function completeScenarioAction(page: Page, scenario: Scenario): Promise<void> {
  if (scenario.action !== 'continue-workout') return;
  await page.getByRole('button', { name: 'Продолжить тренировку', exact: true }).click();
  await page.getByRole('button', { name: 'Завершить тренировку', exact: true }).waitFor({
    state: 'visible',
    timeout: 30_000,
  });
}

async function runScenario(
  browser: Browser,
  scenario: Scenario,
  config: ReturnType<typeof profileConfig>,
  run: number,
): Promise<RunSample> {
  const context = await browser.newContext({
    viewport: config.mobile,
    hasTouch: config.mobile.hasTouch,
    isMobile: config.mobile.isMobile,
    reducedMotion: 'reduce',
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  await installObservers(page);
  await applyMobileThrottling(page);
  const apiRequests: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/v1/'))
      apiRequests.push(`${request.method()} ${url.pathname}`);
  });
  await installPlatformApi(page, scenario.options);
  await page.goto(scenario.path, { waitUntil: 'domcontentloaded' });
  const ready = page.locator(scenario.readySelector).first();
  await ready.waitFor({ state: 'visible', timeout: 30_000 });
  await completeScenarioAction(page, scenario);
  const readyMs = await page.evaluate(() => performance.now());
  await settle(page);
  const sample = await readSample(page, config.revision, config.mode, scenario, run, apiRequests);
  sample.readyMs = readyMs;
  sample.settledMs = await page.evaluate(() => performance.now());
  await context.close();
  return sample;
}

test('V11 private-route mobile profile', async ({ browser }) => {
  const config = profileConfig();
  const samples: RunSample[] = [];
  for (const scenario of scenarios) {
    if (config.mode === 'cold') {
      for (let run = 1; run <= config.runs; run += 1) {
        samples.push(await runScenario(browser, scenario, config, run));
      }
      continue;
    }
    const context = await browser.newContext({
      viewport: config.mobile,
      hasTouch: config.mobile.hasTouch,
      isMobile: config.mobile.isMobile,
      reducedMotion: 'reduce',
      serviceWorkers: 'block',
    });
    const page = await context.newPage();
    await installObservers(page);
    await applyMobileThrottling(page);
    const apiRequests: string[] = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/api/v1/'))
        apiRequests.push(`${request.method()} ${url.pathname}`);
    });
    await installPlatformApi(page, scenario.options);
    await page.goto(scenario.path, { waitUntil: 'domcontentloaded' });
    await page
      .locator(scenario.readySelector)
      .first()
      .waitFor({ state: 'visible', timeout: 30_000 });
    await settle(page);
    for (let run = 1; run <= config.runs; run += 1) {
      apiRequests.length = 0;
      const nextPath = scenario.path;
      await page.goto(nextPath, { waitUntil: 'domcontentloaded' });
      const ready = page.locator(scenario.readySelector).first();
      await ready.waitFor({ state: 'visible', timeout: 30_000 });
      await completeScenarioAction(page, scenario);
      const readyMs = await page.evaluate(() => performance.now());
      await settle(page);
      const sample = await readSample(
        page,
        config.revision,
        config.mode,
        scenario,
        run,
        apiRequests,
      );
      sample.readyMs = readyMs;
      sample.settledMs = await page.evaluate(() => performance.now());
      samples.push(sample);
    }
    await context.close();
  }
  if (config.outputPath) {
    const { writeFileSync } = await import('node:fs');
    writeFileSync(config.outputPath, JSON.stringify({ config, samples }, null, 2));
  }
  console.log(`V11_ROUTE_PROFILE ${JSON.stringify({ config, samples })}`);
});
