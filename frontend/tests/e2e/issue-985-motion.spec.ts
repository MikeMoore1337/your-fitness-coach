import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from '@playwright/test';
import { installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ serviceWorkers: 'block' });

for (const surface of ['web', 'tma'] as const) {
  for (const theme of ['dark', 'light'] as const) {
    for (const width of [320, 360, 393, 430]) {
      test(`#985 ${surface} ${theme} ${width}`, async ({ page }, info) => {
        await page.setViewportSize({ width, height: 852 });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        if (surface === 'tma') {
          await installTelegramHarness(page, {
            colorScheme: theme,
            safeAreaInset: { top: 20, bottom: 16, left: 0, right: 0 },
          });
        }
        const server = await installPlatformApi(page, {
          browserSession: true,
          workoutStatus: 'planned',
        });
        await page.route('**/api/v1/workouts/42/rest-sessions', async (route) => {
          const body = route.request().postDataJSON();
          await route.fulfill({
            json: {
              id: 1,
              workout_id: 42,
              source_set_id: body.source_set_id,
              started_at: body.started_at,
              ended_at: null,
              planned_seconds: 90,
              adjusted_seconds: 90,
              measured_seconds: null,
              status: 'running',
              source: 'timer',
              quality: 'measured',
              version: 1,
              start_mutation_id: body.mutation_id,
            },
          });
        });
        await page.goto('/app?section=today');
        await expect(page.locator('html')).toHaveAttribute(
          'data-yfc-layout-surface',
          surface === 'tma' ? 'telegram' : 'browser',
        );
        await page.getByRole('button', { name: 'Начать тренировку' }).click();
        await page.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }).fill('8');
        await page.getByLabel('Вес, Приседания, подход 1').fill('40');
        await page.getByRole('button', { name: 'Завершить: Приседания, подход 1' }).click();
        await expect(page.getByText('Синхронизировано')).toBeVisible();
        const row = page.locator('[data-workout-set-id="201"]');
        await expect(row.locator('.active-workout-set__complete-label')).toContainText('Выполнен');
        const root = resolve(
          process.cwd(),
          '..',
          'docs',
          'ux-proposals',
          'issue-985-after',
          'screens',
        );
        if (process.env.CAPTURE_985 === '1') {
          await mkdir(root, { recursive: true });
          if (!(await row.isVisible()))
            await page.getByRole('button', { name: '1 из 1 сохранено' }).click();
          await row.scrollIntoViewIfNeeded();
          await page.screenshot({
            path: resolve(root, `${info.project.name}-${surface}-${theme}-${width}-set.png`),
          });
        }
        await page.getByRole('button', { name: 'Завершить тренировку' }).click();
        const completion = page.locator('.workout-completion');
        await expect(completion).toBeVisible();
        await expect(completion.getByText('1 ч')).toBeVisible();
        await expect(completion.getByText(/максимальный вес 40 кг/)).toBeVisible();
        await expect(completion).toHaveAttribute('data-motion-phase', 'idle');
        await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
          ),
        ).toBeLessThanOrEqual(1);
        expect(server.finishCalls()).toBe(1);
        if (process.env.CAPTURE_985 === '1') {
          await completion.locator('.workout-completion__hero').scrollIntoViewIfNeeded();
          await page.screenshot({
            path: resolve(root, `${info.project.name}-${surface}-${theme}-${width}-summary.png`),
            fullPage: true,
          });
        }
        const copy = completion.getByRole('button', { name: 'Скопировать тренировку' });
        await copy.evaluate((element) =>
          element.scrollIntoView({ block: 'center', behavior: 'instant' }),
        );
        const geometry = await copy.evaluate((element) => {
          const rect = element.getBoundingClientRect();
          const hit = document.elementFromPoint(
            rect.left + rect.width / 2,
            rect.top + rect.height / 2,
          );
          return {
            width: rect.width,
            height: rect.height,
            hit: hit === element || element.contains(hit),
            center: [rect.left + rect.width / 2, rect.top + rect.height / 2],
            hitName: hit?.outerHTML.slice(0, 200),
          };
        });
        expect(geometry.width).toBeGreaterThanOrEqual(44);
        expect(geometry.height).toBeGreaterThanOrEqual(44);
        expect(geometry.hit, JSON.stringify(geometry)).toBe(true);
      });
    }
  }
}

test('#985 skip remains clickable and within 320px during Sport', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 852 });
  await installPlatformApi(page, { browserSession: true, workoutStatus: 'planned' });
  await page.goto('/app?section=today');
  await page.getByRole('button', { name: 'Начать тренировку' }).click();
  await page.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }).fill('8');
  await page.getByLabel('Вес, Приседания, подход 1').fill('40');
  await page.getByRole('button', { name: 'Завершить: Приседания, подход 1' }).click();
  await expect(page.getByText('Синхронизировано')).toBeVisible();
  await page.getByRole('button', { name: 'Завершить тренировку' }).click();
  const skip = page.getByRole('button', { name: 'Показать сразу' });
  const box = await skip.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(320);
  expect(box!.height).toBeGreaterThanOrEqual(44);
  await skip.click();
  await expect(page.locator('.workout-completion')).toHaveAttribute('data-motion-phase', 'idle');
});
