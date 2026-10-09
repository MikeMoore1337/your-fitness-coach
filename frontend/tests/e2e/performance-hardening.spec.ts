import { expect, test, type Page } from '@playwright/test';
import { installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

type PerformanceWindow = typeof window & {
  __yfcLabMetrics?: {
    cls: number;
    clsEntries: Array<{ value: number; sources: string[] }>;
    lcp: number | null;
    inp: number | null;
    eventTimingSupported: boolean;
  };
};

async function observeLabMetrics(page: Page) {
  await page.addInitScript(() => {
    const state: NonNullable<PerformanceWindow['__yfcLabMetrics']> = {
      cls: 0,
      clsEntries: [],
      lcp: null as number | null,
      inp: null as number | null,
      eventTimingSupported: false,
    };
    (window as PerformanceWindow).__yfcLabMetrics = state;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as PerformanceEntry & {
          hadRecentInput?: boolean;
          value?: number;
          sources?: Array<{ node?: Node | null }>;
        };
        if (!shift.hadRecentInput) {
          const value = shift.value ?? 0;
          state.cls += value;
          state.clsEntries.push({
            value,
            sources: (shift.sources ?? []).map(({ node }) =>
              node instanceof HTMLElement
                ? `${node.tagName.toLowerCase()}.${node.className}`
                : (node?.nodeName ?? 'unknown'),
            ),
          });
        }
      }
    }).observe({ type: 'layout-shift', buffered: true });
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const lastEntry = entries.at(-1);
      if (lastEntry) state.lcp = lastEntry.startTime;
    }).observe({ type: 'largest-contentful-paint', buffered: true });
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const interaction = entry as PerformanceEntry & {
            duration: number;
            interactionId?: number;
          };
          if (interaction.interactionId && interaction.duration > (state.inp ?? 0)) {
            state.inp = interaction.duration;
          }
        }
      }).observe({
        type: 'event',
        buffered: true,
        durationThreshold: 16,
      } as PerformanceObserverInit & {
        durationThreshold: number;
      });
      state.eventTimingSupported = true;
    } catch {
      state.eventTimingSupported = false;
    }
  });
}

async function readLabMetrics(page: Page) {
  return page.evaluate(() => (window as PerformanceWindow).__yfcLabMetrics);
}

async function settle(page: Page) {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
}

async function loadedFrontendResources(page: Page) {
  return page.evaluate(() =>
    performance
      .getEntriesByType('resource')
      .map((entry) => new URL(entry.name).pathname)
      .filter((path) => /\.(?:css|js)$/.test(path))
      .map((path) => path.split('/').at(-1) ?? path)
      .sort(),
  );
}

function captureConsoleFailures(page: Page) {
  const failures: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      failures.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
  return failures;
}

function captureUnexpectedApiRequests(page: Page, allowedPaths: readonly string[]) {
  const unexpected: string[] = [];
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith('/api/v1/') && !allowedPaths.includes(path)) {
      unexpected.push(`${request.method()} ${path}`);
    }
  });
  return unexpected;
}

async function installLoginApi(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/public/config')) {
      await route.fulfill({
        json: {
          app_env: 'prod',
          enable_dev_auth: false,
          enable_web_auth: true,
          enable_email_auth: true,
          telegram_bot_username: 'fitness_bot',
          oauth_providers: ['google', 'vk'],
        },
      });
      return;
    }
    if (path.endsWith('/auth/refresh') || path.endsWith('/me')) {
      await route.fulfill({ status: 401, json: { detail: 'Требуется вход' } });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: 'Недоступно в performance fixture' } });
  });
}

test('Landing and login keep public/auth initial work bounded in desktop and mobile lab', async ({
  browser,
}, testInfo) => {
  for (const viewport of [
    { name: 'mobile', width: 390, height: 844, hasTouch: true, isMobile: true },
    { name: 'desktop', width: 1440, height: 900, hasTouch: false, isMobile: false },
  ] as const) {
    for (const route of ['/', '/login'] as const) {
      const context = await browser.newContext({
        viewport,
        hasTouch: viewport.hasTouch,
        isMobile: viewport.isMobile,
        reducedMotion: 'reduce',
      });
      const page = await context.newPage();
      const consoleFailures = captureConsoleFailures(page);
      const unexpectedApiRequests = captureUnexpectedApiRequests(
        page,
        route === '/'
          ? ['/api/v1/public/articles']
          : ['/api/v1/public/config', '/api/v1/auth/refresh', '/api/v1/me'],
      );
      await observeLabMetrics(page);
      if (route === '/') {
        await page.route('**/api/v1/public/articles*', (request) => request.fulfill({ json: [] }));
      }
      if (route === '/login') await installLoginApi(page);

      await page.goto(route);
      await expect(
        page.getByRole('heading', {
          level: 1,
          name:
            route === '/'
              ? 'СИЛА В ДЕЙСТВИИ.'
              : viewport.name === 'mobile'
                ? 'Войти и продолжить'
                : 'Вернитесь к своему плану.',
        }),
      ).toBeVisible();
      const themeToggle = page.getByRole('button', { name: /тёмную тему|светлую тему/ });
      if (await themeToggle.count()) await themeToggle.click();
      await settle(page);

      const resources = await loadedFrontendResources(page);
      expect(resources.some((file) => /DataViz/i.test(file))).toBe(false);
      expect(resources.some((file) => /telegram-web-app/i.test(file))).toBe(false);
      if (route === '/login') {
        expect(resources.some((file) => /publicContent/i.test(file))).toBe(false);
      }
      const metrics = await readLabMetrics(page);
      expect(metrics).not.toBeUndefined();
      console.log(`H50_LAB_METRICS ${viewport.name} ${route} ${JSON.stringify(metrics)}`);
      expect(metrics?.cls ?? 0).toBeLessThanOrEqual(0.1);
      if (metrics?.lcp !== null && metrics?.lcp !== undefined) {
        expect(metrics.lcp).toBeLessThanOrEqual(2500);
      }
      if (metrics?.inp !== null && metrics?.inp !== undefined) {
        expect(metrics.inp).toBeLessThanOrEqual(200);
      }
      testInfo.annotations.push({
        type: 'lab-metrics',
        description: `${viewport.name} ${route}: ${JSON.stringify(metrics)}`,
      });
      expect(
        consoleFailures.filter(
          (message) => !message.includes('server responded with a status of 401'),
        ),
      ).toEqual([]);
      expect(unexpectedApiRequests).toEqual([]);
      await context.close();
    }
  }
});

test('Mobile Web and mocked TMA share one frontend resource graph', async ({ browser }) => {
  const resourceGraphs: string[][] = [];

  for (const surface of ['web', 'tma'] as const) {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      hasTouch: true,
      isMobile: true,
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    const consoleFailures = captureConsoleFailures(page);
    if (surface === 'tma') await installTelegramHarness(page, { colorScheme: 'dark' });
    await installPlatformApi(page, { browserSession: surface === 'web', workoutStatus: 'planned' });

    await page.goto('/app?section=today');
    await expect(page.getByRole('heading', { level: 1, name: /^Сегодня/ })).toBeVisible();
    await settle(page);
    const resources = await loadedFrontendResources(page);
    expect(resources.some((file) => /publicContent/i.test(file))).toBe(false);
    expect(resources.some((file) => /(?:telegram|tma).*(?:css|js)$/i.test(file))).toBe(false);
    expect(
      consoleFailures.filter(
        (message) => !message.includes('server responded with a status of 401'),
      ),
    ).toEqual([]);
    resourceGraphs.push(resources);
    await context.close();
  }

  expect(resourceGraphs[1]).toEqual(resourceGraphs[0]);
});

test('Today initial queries settle without duplicate fetches', async ({ page }) => {
  const requestCounts = new Map<string, number>();
  page.on('request', (request) => {
    if (request.method() !== 'GET') return;
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/v1/')) return;
    requestCounts.set(url.pathname, (requestCounts.get(url.pathname) ?? 0) + 1);
  });
  await installPlatformApi(page, { browserSession: true, workoutStatus: 'planned' });

  await page.goto('/app?section=today');
  await expect(page.getByRole('heading', { level: 1, name: /^Сегодня/ })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await settle(page);

  const counts = Object.fromEntries(
    [...requestCounts.entries()].sort(([left], [right]) => left.localeCompare(right)),
  );
  console.log(`H50_QUERY_COUNTS ${JSON.stringify(counts)}`);
  const expectedPaths = [
    '/api/v1/check-ins/weekly/current',
    '/api/v1/me',
    '/api/v1/nutrition/diary',
    '/api/v1/nutrition/hydration',
    '/api/v1/public/config',
    '/api/v1/workouts/42/comments',
    '/api/v1/workouts/cardio',
    '/api/v1/workouts/progress/summary',
    '/api/v1/workouts/recovery',
    '/api/v1/workouts/today',
    '/api/v1/workouts/week',
  ];
  expect(Object.keys(counts)).toEqual(expectedPaths);
  expect(Object.values(counts)).toEqual(expectedPaths.map(() => 1));
});

test('Mocked TMA preserves 404 for an unknown nested public route', async ({ page }) => {
  await installTelegramHarness(page, { colorScheme: 'dark' });

  await page.goto('/knowledge/unknown-performance-route');

  await expect(page.getByText('Страница не найдена')).toBeVisible();
  await expect(page).toHaveURL(/\/knowledge\/unknown-performance-route$/);
});

test('Telegram knowledge launch keeps the handoff when the SDK is unavailable', async ({
  page,
}) => {
  await page.route('https://telegram.org/js/telegram-web-app.js', (route) => route.abort());
  await page.goto('/knowledge?tgWebAppPlatform=web');

  await expect(page.getByRole('heading', { name: 'Продолжить чтение на сайте' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Открыть материал на сайте' })).toHaveAttribute(
    'href',
    '/knowledge',
  );
  await expect(page.getByRole('heading', { name: /База знаний/i })).not.toBeAttached();
});

test('Client navigation preserves metadata owned by a lazy public landing route', async ({
  page,
}) => {
  await page.route('**/api/v1/public/articles*', (request) => request.fulfill({ json: [] }));
  await page.goto('/');

  await page
    .locator('.landing-v10-hero-audience')
    .getByRole('link', { name: 'Для тренера', exact: true })
    .click();

  await expect(page).toHaveURL(/\/for-trainers$/);
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: 'ВАШ МЕТОД В ДЕЙСТВИИ.',
    }),
  ).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'index, follow');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    new URL('/for-trainers', page.url()).href,
  );
});
