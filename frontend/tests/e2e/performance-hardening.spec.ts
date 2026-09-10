import { expect, test, type Page } from '@playwright/test';
import { installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

type PerformanceWindow = typeof window & {
  __yfcLabCls?: { value: number };
};

async function observeLabCls(page: Page) {
  await page.addInitScript(() => {
    const state = { value: 0 };
    (window as PerformanceWindow).__yfcLabCls = state;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number };
        if (!shift.hadRecentInput) state.value += shift.value ?? 0;
      }
    }).observe({ type: 'layout-shift', buffered: true });
  });
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

test('Landing and login keep public/auth initial work bounded in mobile lab', async ({
  browser,
}) => {
  for (const route of ['/', '/login'] as const) {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      hasTouch: true,
      isMobile: true,
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    const consoleFailures = captureConsoleFailures(page);
    await observeLabCls(page);
    if (route === '/') {
      await page.route('**/api/v1/public/articles*', (request) => request.fulfill({ json: [] }));
    }
    if (route === '/login') await installLoginApi(page);

    await page.goto(route);
    await expect(
      page.getByRole('heading', {
        level: 1,
        name: route === '/' ? 'СИЛА В ДЕЙСТВИИ.' : 'Войти и продолжить',
      }),
    ).toBeVisible();
    await settle(page);

    const resources = await loadedFrontendResources(page);
    expect(resources.some((file) => /DataViz/i.test(file))).toBe(false);
    expect(resources.some((file) => /telegram-web-app/i.test(file))).toBe(false);
    if (route === '/login') {
      expect(resources.some((file) => /publicContent/i.test(file))).toBe(false);
    }
    expect(
      await page.evaluate(() => (window as PerformanceWindow).__yfcLabCls?.value ?? 0),
    ).toBeLessThanOrEqual(0.1);
    expect(
      consoleFailures.filter(
        (message) => !message.includes('server responded with a status of 401'),
      ),
    ).toEqual([]);
    await context.close();
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

test('Client navigation preserves metadata owned by a lazy public route', async ({ page }) => {
  await page.goto('/');

  await page
    .locator('.landing-footer')
    .getByRole('link', { name: 'Тренировки', exact: true })
    .click();

  await expect(page).toHaveURL(/\/training$/);
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: /план тренировки, который остаётся перед глазами/i,
    }),
  ).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'index, follow');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    new URL('/training', page.url()).href,
  );
});
