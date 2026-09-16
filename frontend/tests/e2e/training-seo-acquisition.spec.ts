import { expect, test, type Browser, type Page } from '@playwright/test';
import { resolve } from 'node:path';

const workflowTitles = ['Программа', 'Занятие', 'Запись подходов', 'История', 'Прогресс'];
const viewports = [
  { width: 320, height: 800 },
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 768, height: 900 },
  { width: 1024, height: 900 },
  { width: 1366, height: 900 },
  { width: 1440, height: 1000 },
];

const screenshotRoot = resolve(
  process.cwd(),
  '..',
  '..',
  '..',
  '..',
  '.artifacts',
  'tasks',
  '241D',
  'evidence',
  'screenshots',
);

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }));
  expect(dimensions.content).toBe(dimensions.viewport);
}

async function expectTrainingPage(page: Page): Promise<void> {
  await expect(page).toHaveTitle(
    'Дневник тренировок: программа, подходы и прогресс | Your Fitness Coach',
  );
  await expect(
    page.getByRole('heading', { level: 1, name: 'Дневник тренировок: от программы до прогресса' }),
  ).toBeVisible();
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    new URL('/training', page.url()).href,
  );
  await expect(page.locator('.public-workflow ol')).toHaveCount(1);
  await expect(page.locator('.public-workflow li')).toHaveCount(5);
  await expect(page.locator('.public-workflow h3')).toHaveText(workflowTitles);
  await expect(page.getByRole('link', { name: 'Начать вести тренировки' })).toHaveCount(2);
  for (const link of await page.getByRole('link', { name: 'Начать вести тренировки' }).all()) {
    await expect(link).toHaveAttribute('href', '/app');
  }
  for (const path of [
    '/progress',
    '/exercises',
    '/exercises/bench-press',
    '/knowledge/training/progressive-overload',
  ]) {
    await expect(page.locator(`.public-related a[href="${path}"]`)).toHaveCount(1);
  }
}

async function runThemeMatrix(browser: Browser, theme: 'light' | 'dark'): Promise<void> {
  const context = await browser.newContext({
    colorScheme: theme,
    locale: 'ru-RU',
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);

  try {
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      const response = await page.goto('/training', { waitUntil: 'domcontentloaded' });
      expect(response?.status()).toBe(200);
      await expectTrainingPage(page);
      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
      await expectNoHorizontalOverflow(page);
      await page.screenshot({
        path: resolve(screenshotRoot, `training-${viewport.width}-${theme}.png`),
        fullPage: true,
      });
    }

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/training', { waitUntil: 'domcontentloaded' });
    const skipLink = page.getByRole('link', { name: 'К содержимому' });
    await skipLink.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('#public-content')).toBeFocused();
  } finally {
    await context.close();
  }

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
}

test('training acquisition page keeps the canonical content contract across themes and viewports', async ({
  browser,
}) => {
  test.setTimeout(120_000);
  await runThemeMatrix(browser, 'light');
  await runThemeMatrix(browser, 'dark');
});
