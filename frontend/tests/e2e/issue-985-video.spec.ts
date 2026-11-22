import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

test.use({
  serviceWorkers: 'block',
  viewport: { width: 393, height: 852 },
  video: { mode: 'on', size: { width: 393, height: 852 } },
});

for (const skip of [false, true]) {
  test(`#985 video ${skip ? 'skip' : 'sport-and-record'}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
    await installPlatformApi(page, { browserSession: true, workoutStatus: 'planned' });
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
    await page.getByRole('button', { name: 'Начать тренировку' }).click();
    await page.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }).fill('8');
    await page.getByLabel('Вес, Приседания, подход 1').fill('40');
    await expect(page.getByText('Синхронизировано')).toBeVisible();
    await page.getByRole('button', { name: 'Завершить: Приседания, подход 1' }).click();
    await expect(page.getByText('Синхронизировано')).toBeVisible();
    await page.waitForTimeout(700);
    await page.getByRole('button', { name: 'Завершить тренировку' }).click();
    const completion = page.locator('.workout-completion');
    if (skip) await completion.getByRole('button', { name: 'Показать сразу' }).click();
    await expect(completion).toHaveAttribute('data-motion-phase', 'idle');
    await expect(completion.getByText(/максимальный вес 40 кг/)).toBeVisible();
    await completion.locator('.workout-completion__records').scrollIntoViewIfNeeded();
    await page.waitForTimeout(900);
  });
}
