import { expect, test } from '@playwright/test';
import {
  expectNoHorizontalOverflow,
  expectTouchTargets,
  installTelegramHarness,
  setNetworkOffline,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test.use({
  serviceWorkers: 'block',
  video: process.env.ALLURE_RESULTS_DIR ? 'retain-on-failure' : 'on',
});

async function openActiveWorkout(
  page: Parameters<typeof installPlatformApi>[0],
  status: 'planned' | 'in_progress' = 'in_progress',
) {
  await page.goto('/app');
  await page
    .getByRole('button', {
      name: status === 'planned' ? 'Начать тренировку' : 'Продолжить тренировку',
    })
    .click();
  await expect(page.getByRole('region', { name: 'Что делать сейчас?' })).toBeVisible();
}

test('V9-05 keeps the active session summary collapsed until the user opens it', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installPlatformApi(page, {
    browserSession: true,
    workoutStatus: 'in_progress',
    progressionOutcome: 'consider_progressing',
  });
  await openActiveWorkout(page);

  const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
  const toggle = summary.getByRole('button', { name: 'Что делать сейчас?' });
  const details = summary.locator('.active-session-summary__details');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(toggle).toHaveAttribute('aria-controls', /active-session-summary-101-details/);
  await expect(details).toBeHidden();
  await expect(details.locator('button').first()).toBeHidden();
  await expect(summary.getByText('Следующее действие')).toHaveCount(0);
  await expect(summary.getByText('Актуальные данные')).toBeHidden();
  await expect(summary.getByText('Офлайн-снимок')).toBeHidden();
  const toggleBox = await toggle.boundingBox();
  expect(toggleBox?.height ?? 0).toBeGreaterThanOrEqual(44);

  await toggle.focus();
  await expect(toggle).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(details).toBeVisible();
  await expect(summary.getByText('Актуальные данные')).toBeVisible();
  await expect(summary).toContainText('Следующий подход');
  await expect(summary).toContainText('План');
  await expect(summary).toContainText('Последний результат');
  await expect(summary).toContainText('RIR');
  await expect(summary).toContainText('Отдых');
  await expect(summary).toContainText('Можно рассмотреть небольшое увеличение веса');
  await expect(summary.getByText('Серверное назначение')).toBeVisible();
  await expect(summary.getByRole('button', { name: 'Добавить настройку' })).toBeVisible();
  const safety = summary.getByRole('button', { name: 'Боль или травма во время тренировки' });
  await expect(safety).toBeVisible();
  await safety.click();
  const adaptationDialog = page.getByRole('dialog', { name: 'Подстроить тренировку' });
  await expect(adaptationDialog).toBeVisible();
  await adaptationDialog.locator('.workout-adaptation-dialog__close').click();
  await expectTouchTargets(summary.locator('button'));

  const weight = page.getByLabel('Вес, Приседания, подход 1');
  await summary.getByRole('button', { name: 'К текущему подходу' }).click();
  await expect(weight).toBeFocused();
  await expect(page.locator('[data-workout-set-id="201"]')).toHaveAttribute('aria-current', 'step');
  await expectNoHorizontalOverflow(page);

  await toggle.click();
  await expect(details).toBeHidden();

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

test('V12-01 starts a new workout collapsed and keeps the choice and inputs through reconnect', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const api = await installPlatformApi(page, {
    browserSession: true,
    workoutStatus: 'planned',
    progressionOutcome: 'consider_progressing',
  });
  await openActiveWorkout(page, 'planned');

  const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
  const toggle = summary.getByRole('button', { name: 'Что делать сейчас?' });
  const details = summary.locator('.active-session-summary__details');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(details).toBeHidden();

  await toggle.click();
  const weight = page.getByLabel('Вес, Приседания, подход 1');
  await weight.fill('82');
  await expect(weight).toHaveValue('82');
  await api.setOffline(true);
  await setNetworkOffline(page, true);
  const workoutRefresh = page.waitForRequest(
    (request) => request.method() === 'GET' && request.url().endsWith('/workouts/today'),
  );
  await api.setOffline(false);
  await setNetworkOffline(page, false);
  await workoutRefresh;

  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(weight).toHaveValue('82');
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

  const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
  await summary.getByRole('button', { name: 'Что делать сейчас?' }).click();
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

  const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
  await summary.getByRole('button', { name: 'Что делать сейчас?' }).click();
  await expect(summary.getByText('Офлайн-снимок')).toBeVisible();
  await expect(summary).toContainText('Серверное назначение');
  await expect(summary).toContainText('Последний результат');
  await expect(page.locator('[data-workout-set-id="201"]')).toHaveAttribute('aria-current', 'step');
  await expectNoHorizontalOverflow(page);

  await api.setOffline(false);
  await setNetworkOffline(page, false);
});

test('V12-01 keeps the collapsed summary compact across supported mobile widths', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 393, height: 844 });
  await installPlatformApi(page, {
    browserSession: true,
    workoutStatus: 'in_progress',
    progressionOutcome: 'consider_progressing',
  });
  await openActiveWorkout(page);

  const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
  const details = summary.locator('.active-session-summary__details');
  await expect(details).toBeHidden();

  for (const width of [320, 360, 393, 430]) {
    await page.setViewportSize({ width, height: 844 });
    const metrics = await page.evaluate(() => {
      const read = (selector: string) => {
        const element = document.querySelector<HTMLElement>(selector);
        if (!element) return null;
        const rect = element.getBoundingClientRect();
        return {
          top: rect.top + window.scrollY,
          height: rect.height,
          bottom: rect.bottom + window.scrollY,
        };
      };
      return {
        viewport: { width: window.innerWidth, height: window.innerHeight },
        scrollY: window.scrollY,
        summary: read('.active-session-summary'),
        currentSet: read('[data-workout-set-id="201"]'),
        weight: read('[data-workout-set-id="201"] [data-workout-field="weight"]'),
        done: read('[data-workout-set-id="201"] [data-workout-field="done"]'),
        documentWidth: document.documentElement.scrollWidth,
      };
    });
    await testInfo.attach(`issue-826-after-${width}.json`, {
      body: JSON.stringify(metrics, null, 2),
      contentType: 'application/json',
    });
    console.log(`ISSUE_826_AFTER_${width}=${JSON.stringify(metrics)}`);
    expect(metrics.summary?.height ?? 999, `collapsed summary at ${width}px`).toBeLessThan(320);
    expect(metrics.weight, `weight field at ${width}px`).not.toBeNull();
    expect(metrics.done, `completion field at ${width}px`).not.toBeNull();
    expect(metrics.documentWidth, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(
      width + 1,
    );
  }
});
