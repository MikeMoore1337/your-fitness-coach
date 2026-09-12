import { expect, test, type Page } from '@playwright/test';
import { installTelegramHarness, setDocumentVisibility } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

const capture =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.YFC_CAPTURE_TASK_74A === '1';
const screenshotRoot = '../.artifacts/runtime/tests/screenshots/task-74a';

interface PilotTmaHarness {
  active(value: boolean): void;
  back(): void;
  contentSafeArea(value: { top: number; right: number; bottom: number; left: number }): void;
  safeArea(value: { top: number; right: number; bottom: number; left: number }): void;
  state(): { backButton: { visible: boolean } };
  theme(value: 'light' | 'dark'): void;
  viewport(height: number, stableHeight: number, stable: boolean): void;
}

type PilotTmaWindow = typeof window & { __yfcTmaHarness?: PilotTmaHarness };

async function installAuthPilotApi(page: Page) {
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
    await route.fulfill({ status: 404, json: { detail: 'Недоступно в pilot' } });
  });
}

test('production Progress uses one entrance, semantic update and no theme or resize replay', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installPlatformApi(page, {
    browserSession: true,
    measurementHistory: 'many',
    workoutStatus: 'completed',
  });
  await page.goto('/app?section=progress');
  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();

  const chart = page.locator('.data-viz-chart').first();
  await chart.scrollIntoViewIfNeeded();
  await expect(chart).toHaveAttribute('data-motion-phase', 'enter');
  await expect(chart).toHaveAttribute('data-motion-phase', 'idle', { timeout: 2_000 });
  expect(Number(await chart.getAttribute('data-motion-revision'))).toBe(1);
  if (capture) await page.screenshot({ path: `${screenshotRoot}/app-progress-390-light.png` });

  await page.reload();
  const reloadedChart = page.locator('.data-viz-chart').first();
  await reloadedChart.scrollIntoViewIfNeeded();
  await expect(reloadedChart).toHaveAttribute('data-motion-phase', 'enter');
  await expect(reloadedChart).toHaveAttribute('data-motion-phase', 'idle', { timeout: 2_000 });
  const reloadedChartId = await reloadedChart.getAttribute('id');
  const reloadedChartHandle = await reloadedChart.elementHandle();

  const longerPeriod = page
    .getByRole('tablist', { name: 'Период прогресса' })
    .getByRole('tab', { name: '90 дней' });
  await longerPeriod.evaluate((button: HTMLButtonElement) => button.focus({ preventScroll: true }));
  await page.keyboard.press('Enter');
  expect(await reloadedChartHandle?.evaluate((node) => node.isConnected)).toBe(true);
  expect(await reloadedChart.getAttribute('id')).toBe(reloadedChartId);
  await expect(reloadedChart).toHaveAttribute('data-motion-phase', 'update');
  await expect(reloadedChart).toHaveAttribute('data-motion-phase', 'idle', { timeout: 1_500 });
  const updateRevision = await reloadedChart.getAttribute('data-motion-revision');

  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.getByRole('button', { name: 'Закрыть меню' }).click();
  await expect(page.locator('.app-more-layer')).not.toBeAttached();
  await page.setViewportSize({ width: 430, height: 932 });
  expect(await reloadedChart.getAttribute('data-motion-revision')).toBe(updateRevision);
  if (capture) await page.screenshot({ path: `${screenshotRoot}/app-progress-430-dark.png` });

  await page.reload();
  const darkReloadedChart = page.locator('.data-viz-chart').first();
  await darkReloadedChart.scrollIntoViewIfNeeded();
  await expect(darkReloadedChart).toHaveAttribute('data-motion-phase', 'enter');
  if (capture)
    await page.screenshot({ path: `${screenshotRoot}/app-progress-430-dark-reload.png` });
});

test('production Progress exposes final data immediately with reduced motion', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await installPlatformApi(page, {
    browserSession: true,
    measurementHistory: 'many',
    workoutStatus: 'completed',
  });
  await page.goto('/app?section=progress');
  const chart = page.locator('.data-viz-chart').first();
  await chart.scrollIntoViewIfNeeded();
  await expect(chart).toHaveAttribute('data-motion-phase', 'idle');
  await expect(chart.getByRole('img')).toBeVisible();
  await expect(chart.getByRole('table')).toBeAttached();
  const more = page.getByRole('button', {
    name: 'Открыть профиль и настройки',
    exact: true,
  });
  await more.click();
  await expect(page.locator('.app-more-layer')).toHaveAttribute('data-motion-phase', 'open');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('.app-more-layer')).not.toBeAttached();
  await expect(more).toBeFocused();
  if (capture) await page.screenshot({ path: `${screenshotRoot}/app-progress-390-reduced.png` });
});

test('controlled slow Progress data reserves the state and enters once after success', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installPlatformApi(page, {
    browserSession: true,
    measurementHistory: 'many',
    workoutStatus: 'completed',
  });
  let releaseSummary: (() => void) | undefined;
  const summaryGate = new Promise<void>((resolve) => {
    releaseSummary = resolve;
  });
  await page.route('**/api/v1/workouts/progress/summary?*', async (route) => {
    await summaryGate;
    await route.fallback();
  });

  await page.goto('/app?section=progress');
  await expect(page.getByText('Собираем динамику за период…')).toBeVisible();
  await expect(page.locator('.data-viz-chart')).toHaveCount(0);
  releaseSummary?.();

  const chart = page.locator('.data-viz-chart').first();
  await chart.scrollIntoViewIfNeeded();
  await expect(chart).toHaveAttribute('data-motion-phase', 'enter');
  await expect(chart).toHaveAttribute('data-motion-phase', 'idle', { timeout: 2_000 });
  expect(Number(await chart.getAttribute('data-motion-revision'))).toBe(1);
});

test('desktop production Progress keeps the same data motion grammar', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installPlatformApi(page, {
    browserSession: true,
    measurementHistory: 'many',
    workoutStatus: 'completed',
  });
  await page.goto('/app?section=progress');
  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
  const chart = page.locator('.data-viz-chart').first();
  await chart.scrollIntoViewIfNeeded();
  await expect(chart).toHaveAttribute('data-motion-phase', 'enter');
  await expect(chart).toHaveAttribute('data-motion-phase', 'idle', { timeout: 2_000 });
  if (capture) {
    await page.screenshot({
      path: `${screenshotRoot}/app-progress-1440-light.png`,
      fullPage: true,
    });
  }
});

test('shared motion geometry fits the required responsive viewport matrix', async ({ page }) => {
  await installPlatformApi(page, {
    browserSession: true,
    measurementHistory: 'many',
    workoutStatus: 'completed',
  });
  const viewports = [
    { width: 1440, height: 900 },
    { width: 1280, height: 800 },
    { width: 768, height: 1024 },
    { width: 430, height: 932 },
    { width: 390, height: 844 },
    { width: 360, height: 800 },
  ];

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.goto('/app?section=progress');
    const chart = page.locator('.data-viz-chart').first();
    await chart.scrollIntoViewIfNeeded();
    await expect(chart).toBeVisible();
    const geometry = await page.evaluate(() => {
      const plot = document.querySelector('.data-viz-chart')?.getBoundingClientRect();
      return {
        documentWidth: document.documentElement.scrollWidth,
        plotLeft: plot?.left ?? -1,
        plotRight: plot?.right ?? Number.POSITIVE_INFINITY,
        viewportWidth: window.innerWidth,
      };
    });
    expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
    expect(geometry.plotLeft).toBeGreaterThanOrEqual(0);
    expect(geometry.plotRight).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  }

  const tokens = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    const durationMs = (name: string) => {
      const value = style.getPropertyValue(name).trim();
      return value.endsWith('ms') ? Number.parseFloat(value) : Number.parseFloat(value) * 1_000;
    };
    return {
      press: durationMs('--motion-press'),
      spatial: durationMs('--motion-spatial'),
      state: durationMs('--motion-state'),
    };
  });
  expect(tokens).toEqual({ press: 120, spatial: 260, state: 180 });

  // 768 CSS px covers a 1536 px desktop viewport at 200% reflow.
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.emulateMedia({ forcedColors: 'active' });
  await page.goto('/app?section=progress');
  const forcedColorsChart = page.locator('.data-viz-chart').first();
  await forcedColorsChart.scrollIntoViewIfNeeded();
  const strokeGrammar = await forcedColorsChart.evaluate((chart) => {
    const actual = chart.querySelector<SVGPathElement>('.data-viz-chart__actual');
    const target = chart.querySelector<SVGPathElement>('.data-viz-chart__target');
    return {
      actualDash: actual ? getComputedStyle(actual).strokeDasharray : '',
      targetDash: target ? getComputedStyle(target).strokeDasharray : '',
    };
  });
  expect(strokeGrammar.actualDash).not.toBe(strokeGrammar.targetDash);
  await expect(forcedColorsChart.getByRole('table')).toBeAttached();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(769);
});

test('workout confirmation and Nutrition add keep final production state immediately available', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installPlatformApi(page, { browserSession: true, workoutStatus: 'planned' });
  await page.goto('/app?section=today');
  await page.getByRole('button', { name: 'Начать тренировку' }).click();
  await page.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }).fill('8');
  await page.getByRole('spinbutton', { name: 'Вес, Приседания, подход 1' }).fill('40');
  await page.getByRole('button', { name: 'Завершить: Приседания, подход 1' }).click();
  const completedSet = page.locator('.active-workout-set').first();
  await expect(completedSet).toHaveAttribute('data-motion-confirm', 'true');
  await expect(completedSet).toContainText('Выполнен');
  const restTimer = page.locator('.active-workout-rest');
  await expect(restTimer).toBeVisible();
  await restTimer.evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished));
  });
  const restGeometry = await restTimer.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return {
      background: getComputedStyle(element).backgroundColor,
      bottom: box.bottom,
    };
  });
  expect(restGeometry.background).toBe('rgba(248, 250, 250, 0.92)');
  const completedExercise = page.locator('.active-workout-exercise').first();
  await expect(completedExercise.getByRole('button', { name: '1 из 1 сохранено' })).toBeVisible();
  expect(restGeometry.bottom).toBeLessThanOrEqual(
    (await completedExercise.boundingBox())?.y ?? Number.NEGATIVE_INFINITY,
  );
  if (capture) await page.screenshot({ path: `${screenshotRoot}/app-workout-390-confirmed.png` });

  await page.getByRole('link', { name: 'Питание', exact: true }).click();
  const breakfast = page.getByRole('region', { name: 'Завтрак' });
  await breakfast.getByRole('button', { name: /Добавить/ }).click();
  await page.getByRole('button', { name: 'Добавить Овсяная каша' }).click();
  await page.getByRole('button', { name: 'Добавить в дневник' }).click();
  const addedEntry = page.locator('.nutrition-entry').filter({ hasText: 'Овсяная каша' });
  await expect(addedEntry).toBeVisible();
  await expect(addedEntry).toHaveAttribute('data-motion-phase', /enter|idle/);
  await expect(
    page.getByRole('progressbar', { name: /Калории: 180 из 2.*100 ккал/ }),
  ).toBeVisible();
  await expect(page.locator('.nutrition-day-summary')).toContainText('КБЖУ');
  const toast = page.locator('.toast');
  await expect(toast).toHaveAttribute('data-motion-phase', /opening|open/);
  await expect(addedEntry).toHaveAttribute('data-motion-phase', 'idle', { timeout: 2_000 });
  await expect(toast).toHaveAttribute('data-motion-phase', 'open', { timeout: 2_000 });
  if (capture) await page.screenshot({ path: `${screenshotRoot}/app-nutrition-390-added.png` });
  await toast.getByRole('button', { name: 'Закрыть сообщение' }).click();
  await expect(toast).toHaveAttribute('data-motion-phase', 'closing');
  await expect(toast).not.toBeAttached();
});

test('mocked TMA overlay keeps BackButton, focus and lifecycle interruption semantics', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegramHarness(page, { colorScheme: 'dark' });
  await installPlatformApi(page, { measurementHistory: 'many', workoutStatus: 'completed' });
  await page.goto('/app?section=progress');
  const chart = page.locator('.data-viz-chart').first();
  await chart.scrollIntoViewIfNeeded();
  await expect(chart).toHaveAttribute('data-motion-phase', 'enter');
  await expect(chart).toHaveAttribute('data-motion-phase', 'idle', { timeout: 2_000 });
  const revision = await chart.getAttribute('data-motion-revision');

  const more = page.getByRole('button', {
    name: 'Открыть профиль и настройки',
    exact: true,
  });
  await more.click();
  await expect(page.locator('.app-more-layer')).toHaveAttribute(
    'data-motion-phase',
    /opening|open/,
  );
  expect(
    await page.evaluate(
      () => (window as PilotTmaWindow).__yfcTmaHarness?.state().backButton.visible,
    ),
  ).toBe(true);
  await page.evaluate(() => {
    const harness = (window as PilotTmaWindow).__yfcTmaHarness;
    harness?.viewport(620, 844, false);
    harness?.safeArea({ top: 20, right: 0, bottom: 18, left: 0 });
    harness?.contentSafeArea({ top: 28, right: 0, bottom: 12, left: 0 });
    harness?.theme('light');
    harness?.theme('dark');
    harness?.active(false);
    harness?.active(true);
  });
  await setDocumentVisibility(page, 'hidden');
  await setDocumentVisibility(page, 'visible');
  expect(await chart.getAttribute('data-motion-revision')).toBe(revision);
  await page.evaluate(() => (window as PilotTmaWindow).__yfcTmaHarness?.back());
  await expect(page.locator('.app-more-layer')).toHaveAttribute('data-motion-phase', 'closing');
  await expect(more).toBeFocused();
  expect(
    await page.evaluate(
      () => (window as PilotTmaWindow).__yfcTmaHarness?.state().backButton.visible,
    ),
  ).toBe(true);
  await expect(page.locator('.app-more-layer')).not.toBeAttached();
  expect(
    await page.evaluate(
      () => (window as PilotTmaWindow).__yfcTmaHarness?.state().backButton.visible,
    ),
  ).toBe(false);
  if (capture) await page.screenshot({ path: `${screenshotRoot}/mock-tma-progress-390-dark.png` });
});

test('Login motion stays calm across provider, email, error and reduced-motion states', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installAuthPilotApi(page);
  await page.goto('/login');
  const layout = page.locator('.login-layout');
  await expect(layout).toHaveAttribute('data-motion-phase', /enter|idle/);
  if (capture) await page.screenshot({ path: `${screenshotRoot}/login-390-light.png` });

  await page.evaluate(() => {
    document.addEventListener(
      'click',
      (event) => {
        if ((event.target as Element).closest('.oauth-button')) event.preventDefault();
      },
      true,
    );
  });
  await page.getByRole('link', { name: 'Продолжить с Google' }).click();
  const busyProvider = page.getByRole('link', { name: 'Переходим…' });
  await expect(busyProvider).toHaveAttribute('aria-busy', 'true');
  await expect(page.getByRole('link', { name: 'Войти с VK ID' })).toHaveAttribute(
    'aria-disabled',
    'true',
  );

  await page.reload();
  await page.getByRole('tab', { name: 'Регистрация' }).click();
  await expect(page.locator('.email-auth__mode-panel')).toHaveAttribute(
    'data-motion-phase',
    'update',
  );
  await expect(page.getByLabel('Имя пользователя')).toBeVisible();
  if (capture) await page.screenshot({ path: `${screenshotRoot}/login-390-email-register.png` });

  await page.goto('/login?auth_error=denied');
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(layout).toHaveCount(1);
  if (capture) await page.screenshot({ path: `${screenshotRoot}/login-390-oauth-error.png` });

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/login');
  await expect(page.locator('.login-layout')).toHaveAttribute('data-motion-phase', 'idle');
  if (capture) await page.screenshot({ path: `${screenshotRoot}/login-390-reduced.png` });
});
