import { expect, test } from '@playwright/test';
import {
  expectNoHorizontalOverflow,
  expectTouchTargets,
  installTelegramHarness,
  setNetworkOffline,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ serviceWorkers: 'block', video: 'on' });

async function openActiveWorkout(page: Parameters<typeof installPlatformApi>[0]) {
  await page.goto('/app');
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await expect(page.getByRole('region', { name: 'Что делать сейчас' })).toBeVisible();
}

test('V9-05 composes the active session summary and focuses the current set', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installPlatformApi(page, {
    browserSession: true,
    workoutStatus: 'in_progress',
    progressionOutcome: 'consider_progressing',
  });
  await openActiveWorkout(page);

  const summary = page.getByRole('region', { name: 'Что делать сейчас' });
  await expect(summary).toContainText('Следующий подход');
  await expect(summary).toContainText('План');
  await expect(summary).toContainText('Предыдущий результат');
  await expect(summary).toContainText('RIR');
  await expect(summary).toContainText('Отдых');
  await expect(summary).toContainText('Можно рассмотреть небольшое увеличение веса');
  await expect(summary.getByText('Серверное назначение')).toBeVisible();
  await expect(summary.getByRole('button', { name: 'Добавить настройку' })).toBeVisible();
  await expectTouchTargets(summary.locator('button'));

  const weight = page.getByRole('spinbutton', { name: 'Вес, Приседания, подход 1' });
  await summary.getByRole('button', { name: 'К текущему подходу' }).click();
  await expect(weight).toBeFocused();
  await expect(page.locator('[data-workout-set-id="201"]')).toHaveAttribute('aria-current', 'step');
  await expectNoHorizontalOverflow(page);

  for (const [width, height] of [
    [360, 800],
    [390, 844],
    [430, 932],
  ] as const) {
    await page.setViewportSize({ width, height });
    await expect(summary).toBeVisible();
    await expectNoHorizontalOverflow(page);
  }
});

test('V9-05 keeps the composed summary usable in mocked TMA dark reduced-motion mode', async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await installTelegramHarness(page, {
    colorScheme: 'dark',
    viewportHeight: 800,
    viewportStableHeight: 800,
  });
  await installPlatformApi(page, {
    workoutStatus: 'in_progress',
    progressionOutcome: 'consider_progressing',
    longExerciseName: true,
  });
  await openActiveWorkout(page);

  const summary = page.getByRole('region', { name: 'Что делать сейчас' });
  await expect(page.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(summary).toContainText('Можно рассмотреть небольшое увеличение веса');
  await expect(summary.getByRole('button', { name: 'К текущему подходу' })).toBeVisible();
  await expectTouchTargets(summary.locator('button'));
  await expectNoHorizontalOverflow(page);
});

test('V9-05 shows a truthful offline state without losing the current set', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const api = await installPlatformApi(page, {
    browserSession: true,
    workoutStatus: 'in_progress',
    progressionOutcome: 'consider_progressing',
  });
  await openActiveWorkout(page);

  await api.setOffline(true);
  await setNetworkOffline(page, true);

  const summary = page.getByRole('region', { name: 'Что делать сейчас' });
  await expect(summary.getByText('Офлайн-снимок')).toBeVisible();
  await expect(summary).toContainText('Серверное назначение');
  await expect(summary).toContainText('Предыдущий результат');
  await expect(page.locator('[data-workout-set-id="201"]')).toHaveAttribute('aria-current', 'step');
  await expectNoHorizontalOverflow(page);

  await api.setOffline(false);
  await setNetworkOffline(page, false);
});
