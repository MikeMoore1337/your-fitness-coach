import type { Browser, Page } from '@playwright/test';
import type { DemoScenario, DemoSessionSnapshot } from '../../src/features/demo/demoApi';
import {
  expect,
  expectNoHorizontalOverflow,
  expectNoOverlap,
  expectTouchTargets,
  installTelegramHarness,
  MOBILE_CONTEXTS,
  setNetworkOffline,
  test,
} from './fixtures/mobile-tma';

const CAPTURE =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.YFC_CAPTURE_TASK_69 === '1';
const LIVE_DEMO =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.YFC_DEMO_LIVE === '1';
const SCREENSHOT_DIR = '../.artifacts/screenshots/task-69';
const CABINET_CAPTURE =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.YFC_CAPTURE_TASK_69A === '1';
const CABINET_SCREENSHOT_DIR = '../.artifacts/screenshots/task-69a';
const TASK_74_CAPTURE =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.YFC_CAPTURE_TASK_74 === '1';
const TASK_74_SCREENSHOT_DIR = '../.artifacts/screenshots/task-74';
const TASK_74A_DEMO_VIDEO =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.YFC_CAPTURE_TASK_74A_DEMO === '1';

function cabinetFixture(scenario: DemoScenario): DemoSessionSnapshot['cabinet'] {
  return {
    today: {
      title: scenario === 'trainer' ? 'Результат клиента готов к разбору' : 'План на сегодня',
      summary: 'Подготовленный связный контекст',
      status_label: 'Нужно действие',
      completed_days: 3,
      planned_days: 5,
    },
    nutrition: {
      calories: 1160,
      calorie_target: 2150,
      protein_g: 82,
      protein_target_g: 145,
      meals_logged: 2,
      item_added: false,
      recent_item: {
        name: 'Овсяная каша с бананом и греческим йогуртом',
        serving: '320 г · недавний продукт',
        calories: 428,
        protein_g: 24,
      },
    },
    progress: {
      workouts_completed: 11,
      latest_volume_kg: 6220,
      volume_change_percent: 4.2,
      nutrition_days_logged: 5,
      nutrition_completion_percent: 54,
      summary: 'Итог использует только подтверждённые записи.',
    },
    trainer: null,
    meaningful_action_completed: false,
    conversion_title:
      scenario === 'nutrition'
        ? 'Настройте дневник питания под себя'
        : scenario === 'trainer'
          ? 'Начните работать с реальными клиентами'
          : 'Ведите настоящую историю тренировок',
  };
}

function demoFixture(scenario: DemoScenario): DemoSessionSnapshot {
  const base = {
    capability: 'demo' as const,
    scenario,
    fixture_version: 'demo-curated-v1' as const,
    revision: 1,
    expires_at: '2026-08-24T12:30:00Z',
    cabinet: cabinetFixture(scenario),
  };
  if (scenario === 'nutrition') {
    return {
      ...base,
      state: {
        kind: 'nutrition',
        screen: 'diary',
        date_label: 'Сегодня · подготовленный дневник',
        item_added: false,
        recent_item: {
          name: 'Овсяная каша с бананом и греческим йогуртом',
          serving: '320 г · недавний продукт',
          calories: 428,
          protein_g: 24,
        },
        calories: 1160,
        calorie_target: 2150,
        protein_g: 82,
        protein_target_g: 145,
        meals_logged: 2,
      },
    };
  }
  if (scenario === 'trainer') {
    const trainerState = {
      kind: 'trainer' as const,
      screen: 'client' as const,
      client_name: 'Алексей Воронов — подготовленный демо-клиент',
      context_label: 'Последняя тренировка · сегодня, 18:40',
      workout_title: 'Ноги и корпус · неделя 4',
      facts: [
        { label: 'Выполнено', value: '6 из 6 упражнений' },
        { label: 'Объём', value: '6 840 кг' },
        { label: 'Самочувствие', value: '8 из 10' },
        { label: 'Следующий ориентир', value: '+2,5 кг в приседе' },
      ],
      comment: null,
    };
    return {
      ...base,
      state: trainerState,
      cabinet: { ...base.cabinet, trainer: trainerState },
    };
  }
  return {
    ...base,
    state: {
      kind: 'self_training',
      screen: 'today',
      workout_title: 'Верх тела · уверенный старт',
      workout_subtitle: 'Подготовленная тренировка на сегодня',
      completed_sets: 2,
      total_sets: 3,
      exercises: [
        {
          name: 'Жим гантелей лёжа с контролируемой паузой',
          prescription: '3 × 10 · 18 кг · отдых 90 сек.',
          status: 'current',
        },
        {
          name: 'Тяга верхнего блока нейтральным хватом',
          prescription: '3 × 12 · 40 кг · отдых 75 сек.',
          status: 'next',
        },
      ],
      duration_minutes: 0,
      total_volume_kg: 0,
      progress_change_percent: 0,
    },
  };
}

function applyMockAction(snapshot: DemoSessionSnapshot, action: string, comment?: string) {
  const next = structuredClone(snapshot);
  next.revision += 1;
  if (next.state.kind === 'self_training') {
    if (action === 'start_workout') next.state.screen = 'active_workout';
    if (action === 'complete_set') next.state.completed_sets = next.state.total_sets;
    if (action === 'finish_workout') {
      next.state.screen = 'summary';
      next.state.duration_minutes = 46;
      next.state.total_volume_kg = 6840;
      next.cabinet.today.status_label = 'Тренировка завершена';
      next.cabinet.progress.workouts_completed = 12;
      next.cabinet.progress.latest_volume_kg = 6840;
      next.cabinet.progress.volume_change_percent = 6.5;
      next.cabinet.progress.summary = 'Сегодняшняя тренировка уже учтена в динамике.';
      next.cabinet.meaningful_action_completed = true;
    }
    if (action === 'open_progress') {
      next.state.screen = 'progress';
      next.state.progress_change_percent = 6.5;
    }
  } else if (next.state.kind === 'nutrition') {
    if (action === 'add_recent' && !next.state.item_added) {
      next.state.item_added = true;
      next.state.calories += next.state.recent_item.calories;
      next.state.protein_g += next.state.recent_item.protein_g;
      next.state.meals_logged += 1;
      next.cabinet.nutrition.calories = next.state.calories;
      next.cabinet.nutrition.protein_g = next.state.protein_g;
      next.cabinet.nutrition.meals_logged = next.state.meals_logged;
      next.cabinet.nutrition.item_added = true;
      next.cabinet.progress.nutrition_days_logged = 6;
      next.cabinet.progress.nutrition_completion_percent = 74;
      next.cabinet.progress.summary = 'Новая запись уже отражена в дневном итоге.';
      next.cabinet.meaningful_action_completed = true;
    }
    if (action === 'open_nutrition_report') next.state.screen = 'report';
  } else if (action === 'save_comment') {
    next.state.comment = comment ?? 'Техника стабильна.';
    if (next.cabinet.trainer) next.cabinet.trainer.comment = next.state.comment;
    next.cabinet.meaningful_action_completed = true;
  }
  return next;
}

async function installDemoApi(page: Page, forcedCurrentStatus?: 403 | 410) {
  const sessions = new Map<string, DemoSessionSnapshot>();
  let sequence = 0;
  let unavailable = false;
  await page.route('**/api/v1/demo/**', async (route) => {
    if (unavailable) {
      await route.abort('internetdisconnected');
      return;
    }
    const request = route.request();
    const url = new URL(request.url());
    const token = request.headers()['x-demo-session'];
    if (url.pathname.endsWith('/sessions') && request.method() === 'POST') {
      const body = request.postDataJSON() as { scenario: DemoScenario };
      const nextToken = `demo-token-${String(++sequence).padStart(32, '0')}`;
      const snapshot = demoFixture(body.scenario);
      sessions.set(nextToken, snapshot);
      await route.fulfill({ status: 201, json: { ...snapshot, session_token: nextToken } });
      return;
    }
    if (forcedCurrentStatus && request.method() === 'GET') {
      await route.fulfill({
        status: forcedCurrentStatus,
        json: {
          detail:
            forcedCurrentStatus === 410
              ? 'Демо-сессия истекла. Начните новый сценарий.'
              : 'Это действие недоступно в демо-режиме.',
        },
      });
      return;
    }
    const snapshot = token ? sessions.get(token) : undefined;
    if (!token || !snapshot) {
      await route.fulfill({ status: 410, json: { detail: 'Демо-сессия истекла.' } });
      return;
    }
    if (url.pathname.endsWith('/actions')) {
      const body = request.postDataJSON() as { action: string; comment?: string };
      const next = applyMockAction(snapshot, body.action, body.comment);
      sessions.set(token, next);
      await route.fulfill({ status: 200, json: next });
      return;
    }
    if (url.pathname.endsWith('/reset')) {
      const next = demoFixture(snapshot.scenario);
      sessions.set(token, next);
      await route.fulfill({ status: 200, json: next });
      return;
    }
    await route.fulfill({ status: 200, json: snapshot });
  });
  return {
    setUnavailable(value: boolean) {
      unavailable = value;
    },
  };
}

async function installAuthApi(page: Page) {
  let authenticated = false;
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes('/demo/')) return route.fallback();
    if (path.endsWith('/public/config')) {
      return route.fulfill({
        json: {
          app_env: 'prod',
          enable_dev_auth: false,
          enable_web_auth: true,
          enable_email_auth: false,
          telegram_bot_username: 'fitness_bot',
          oauth_providers: ['telegram', 'google', 'yandex', 'vk'],
        },
      });
    }
    if (path.endsWith('/auth/refresh')) {
      return route.fulfill({ status: 401, json: { detail: 'Сессия отсутствует' } });
    }
    if (path.endsWith('/auth/telegram/init')) {
      authenticated = true;
      return route.fulfill({ json: { access_token: 'telegram-demo-handoff-token' } });
    }
    if (path.endsWith('/me')) {
      return authenticated
        ? route.fulfill({
            json: {
              id: 69,
              is_coach: false,
              is_admin: false,
              is_root: false,
              has_active_program: false,
              has_workout_history: false,
              onboarding: {
                status: 'required',
                required_fields: ['goal'],
                missing_fields: ['goal'],
              },
              profile: null,
              trainer: null,
            },
          })
        : route.fulfill({ status: 401, json: { detail: 'Требуется вход' } });
    }
    return route.fallback();
  });
}

async function completeScenario(page: Page, scenario: DemoScenario) {
  if (scenario === 'self_training') {
    await page.getByRole('button', { name: 'Начать тренировку' }).click();
    await page.getByRole('button', { name: 'Завершить текущий подход' }).click();
    await page.getByRole('button', { name: 'Завершить тренировку' }).click();
    await expectMetricSpacing(page);
    if (CAPTURE && page.viewportSize()?.width === 360) {
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/mobile-web-360-training-summary-spacing.png`,
        fullPage: true,
      });
    }
    await page.getByRole('button', { name: 'Перейти к прогрессу' }).click();
  } else if (scenario === 'nutrition') {
    await expectMetricSpacing(page);
    await page.getByRole('button', { name: 'Добавить недавний продукт' }).click();
    await page.getByRole('button', { name: 'Открыть отчёт по питанию' }).click();
  } else {
    await page.getByRole('button', { name: 'Сохранить комментарий' }).click();
  }
  const authHandoff = page.getByRole('link', { name: 'Войти в приложение' });
  await expect(authHandoff).toBeVisible();
  await authHandoff.scrollIntoViewIfNeeded();
  await expect(authHandoff).toBeInViewport();

  const isTma = await page.evaluate(() => Boolean(window.Telegram?.WebApp?.initData?.trim()));
  if (CAPTURE && !isTma) {
    const width = page.viewportSize()?.width;
    const shouldCapture =
      (scenario === 'self_training' && width === 360) ||
      (scenario === 'nutrition' && width === 390) ||
      (scenario === 'trainer' && width === 390);
    if (shouldCapture) {
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/mobile-web-${width}-${scenario}-conversion-light.png`,
        fullPage: true,
      });
    }
  }
}

async function expectMetricSpacing(page: Page) {
  const metrics = page.locator('.demo-metrics');
  await expect(metrics.locator('.ui-metric')).toHaveCount(3);
  const gaps = await metrics.evaluate((element) => {
    const styles = getComputedStyle(element);
    return { column: Number.parseFloat(styles.columnGap), row: Number.parseFloat(styles.rowGap) };
  });
  expect(gaps.column).toBeGreaterThanOrEqual(8);
  expect(gaps.row).toBeGreaterThanOrEqual(8);
}

async function expectPrimaryContract(page: Page) {
  const primary = page.locator('.demo-stage .ui-button:not(.ui-button--secondary)').first();
  await expect(primary).toBeVisible();
  const contract = await primary.evaluate(() => {
    const sample = document.createElement('span');
    sample.style.backgroundColor = 'var(--v2-lime)';
    sample.style.borderRadius = 'var(--radius-action)';
    document.body.append(sample);
    const expected = getComputedStyle(sample);
    const result = {
      expectedBackground: expected.backgroundColor,
      expectedRadius: expected.borderRadius,
    };
    sample.remove();
    return result;
  });
  await expect(primary).toHaveCSS('background-color', contract.expectedBackground);
  await expect(primary).toHaveCSS('border-radius', contract.expectedRadius);
}

async function expectSelectionContract(page: Page) {
  const active = page.locator('.demo-scenario-nav button.is-active');
  const contract = await active.evaluate(() => {
    const sample = document.createElement('span');
    sample.style.backgroundColor = 'var(--v2-surface-secondary)';
    sample.style.borderLeftColor = 'var(--v2-lime)';
    sample.style.borderRadius = 'var(--v2-compact-radius)';
    document.body.append(sample);
    const expected = getComputedStyle(sample);
    const result = {
      background: expected.backgroundColor,
      boundary: expected.borderLeftColor,
      radius: expected.borderRadius,
    };
    sample.remove();
    return result;
  });
  await expect(active).toHaveCSS('background-color', contract.background);
  await expect(active).toHaveCSS('border-left-color', contract.boundary);
  await expect(active).toHaveCSS('border-radius', contract.radius);
}

async function openMobilePage(browser: Browser, scenario: DemoScenario, width: 360 | 390 | 430) {
  const viewport =
    width === 360
      ? MOBILE_CONTEXTS.compact
      : width === 390
        ? MOBILE_CONTEXTS.baseline
        : MOBILE_CONTEXTS.large;
  const context = await browser.newContext({
    viewport,
    hasTouch: true,
    isMobile: true,
    reducedMotion: TASK_74A_DEMO_VIDEO ? 'no-preference' : 'reduce',
    recordVideo: TASK_74A_DEMO_VIDEO
      ? { dir: '../.artifacts/videos/task-74a/demo', size: viewport }
      : undefined,
  });
  const page = await context.newPage();
  const api = LIVE_DEMO ? null : await installDemoApi(page);
  await page.goto(`/demo?scenario=${scenario}`);
  return { api, context, page };
}

test('three curated scenarios work at compact Mobile Web widths without visual forks', async ({
  browser,
}) => {
  for (const scenario of ['self_training', 'nutrition', 'trainer'] as const) {
    for (const width of [360, 390] as const) {
      const { context, page } = await openMobilePage(browser, scenario, width);
      await expect(page.getByText('Демо', { exact: true })).toBeVisible();
      const themeToggle = page.getByRole('button', { name: /Включить (тёмную|светлую) тему/ });
      await expect(themeToggle).toBeVisible();
      await expectTouchTargets(themeToggle);
      await expectNoHorizontalOverflow(page);
      await expectTouchTargets(page.locator('.demo-scenario-nav button'));
      await expectSelectionContract(page);
      if (width === 360 && scenario === 'self_training') {
        await themeToggle.click();
        await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
        await page.getByRole('button', { name: 'Включить светлую тему' }).click();
        await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
        const activeButton = page.locator('.demo-scenario-nav button.is-active');
        const [buttonBox, labelBox] = await Promise.all([
          activeButton.boundingBox(),
          activeButton.locator('strong').boundingBox(),
        ]);
        expect(buttonBox).not.toBeNull();
        expect(labelBox).not.toBeNull();
        expect(labelBox!.x - buttonBox!.x).toBeGreaterThanOrEqual(8);
        expect(
          buttonBox!.x + buttonBox!.width - labelBox!.x - labelBox!.width,
        ).toBeGreaterThanOrEqual(8);
        await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeInViewport();
        if (CAPTURE) {
          await page.screenshot({
            path: `${SCREENSHOT_DIR}/mobile-web-360-training-entry-light.png`,
            fullPage: true,
          });
        }
      }
      await expectPrimaryContract(page);
      await completeScenario(page, scenario);
      await expectNoHorizontalOverflow(page);
      if (CAPTURE && scenario === 'self_training' && width === 360) {
        await page.screenshot({
          path: `${SCREENSHOT_DIR}/mobile-web-360-training-light.png`,
          fullPage: true,
        });
      }
      await context.close();
    }
  }

  const { context, page } = await openMobilePage(browser, 'nutrition', 430);
  await expectNoHorizontalOverflow(page);
  await expect(page.getByRole('button', { name: 'Добавить недавний продукт' })).toBeVisible();
  await context.close();
});

test('signed TMA launch does not open the Web-only demo', async ({ browser }) => {
  const context = await browser.newContext({
    viewport: MOBILE_CONTEXTS.baseline,
    hasTouch: true,
    isMobile: true,
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  const requestedPaths: string[] = [];
  page.on('request', (request) => requestedPaths.push(new URL(request.url()).pathname));
  await installTelegramHarness(page, { colorScheme: 'dark' });
  await installAuthApi(page);

  await page.goto('/demo?scenario=trainer&tgWebAppPlatform=android');

  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole('heading', { level: 1, name: /^Сегодня ·/ })).toBeVisible();
  await expect(page.getByText('Демо', { exact: true })).toHaveCount(0);
  expect(requestedPaths.some((path) => path.includes('/api/v1/demo/'))).toBe(false);
  expect(requestedPaths.some((path) => path.includes('/auth/telegram/init'))).toBe(true);
  await context.close();

  const failedSdkContext = await browser.newContext({ viewport: MOBILE_CONTEXTS.baseline });
  const failedSdkPage = await failedSdkContext.newPage();
  const failedSdkRequests: string[] = [];
  failedSdkPage.on('request', (request) => failedSdkRequests.push(new URL(request.url()).pathname));
  await failedSdkPage.route('https://telegram.org/js/telegram-web-app.js', (route) =>
    route.abort(),
  );
  await installAuthApi(failedSdkPage);
  await failedSdkPage.goto('/demo?scenario=trainer&tgWebAppPlatform=android');

  await expect(failedSdkPage).not.toHaveURL(/\/demo/);
  await expect(failedSdkPage.getByText('Демо', { exact: true })).toHaveCount(0);
  expect(failedSdkRequests.some((path) => path.includes('/api/v1/demo/'))).toBe(false);
  await failedSdkContext.close();
});

test('Web cabinet preview uses production shell across the required viewport matrix', async ({
  browser,
}) => {
  const viewports = [
    { name: 'mobile-360-light', width: 360, height: 800, touch: true, dark: false },
    { name: 'mobile-390-light', width: 390, height: 844, touch: true, dark: false },
    { name: 'mobile-390-dark', width: 390, height: 844, touch: true, dark: true },
    { name: 'mobile-430-light', width: 430, height: 932, touch: true, dark: false },
    { name: 'tablet-768-light', width: 768, height: 900, touch: true, dark: false },
    { name: 'desktop-1280-light', width: 1280, height: 900, touch: false, dark: false },
    { name: 'desktop-1440-dark', width: 1440, height: 900, touch: false, dark: true },
  ] as const;

  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      hasTouch: viewport.touch,
      isMobile: viewport.width < 768,
      colorScheme: viewport.dark ? 'dark' : 'light',
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => pageErrors.push(error.message));
    await installDemoApi(page);
    await page.goto('/demo?cabinet=1&scenario=self_training&section=today');

    await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'План на сегодня' })).toBeVisible();
    await expect(page.getByText('Подготовленные данные без сохранения')).toBeVisible();
    const weekLegendSummary = page.locator('.week-strip__legend-summary');
    const weekLegend = page.getByRole('list', { name: 'Обозначения недели' });
    const weekStrip = page.locator('.week-strip');
    const legendDisclosure = page.locator('.week-strip__legend-disclosure');
    const focusGrid = page.locator('.demo-cabinet-focus-grid');
    await expect(weekLegendSummary).toBeVisible();
    await expect(weekLegendSummary).toHaveText('Обозначения');
    await expect(weekLegend).toBeHidden();
    expect((await weekLegendSummary.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    const collapsedWeekBox = await weekStrip.boundingBox();
    const legendDisclosureBox = await legendDisclosure.boundingBox();
    const collapsedFocusBox = await focusGrid.boundingBox();
    const summaryLabelBox = await page.locator('.week-strip__legend-summary-label').boundingBox();
    expect(collapsedWeekBox).not.toBeNull();
    expect(legendDisclosureBox).not.toBeNull();
    expect(collapsedFocusBox).not.toBeNull();
    expect(summaryLabelBox).not.toBeNull();
    expect(
      Math.abs((summaryLabelBox?.x ?? 0) - ((legendDisclosureBox?.x ?? 0) + 2)),
    ).toBeLessThanOrEqual(1);
    if (viewport.touch) {
      await weekLegendSummary.click();
    } else {
      await weekLegendSummary.focus();
      await page.keyboard.press('Enter');
    }
    await expect(weekLegend).toBeVisible();
    const expandedWeekBox = await weekStrip.boundingBox();
    const expandedFocusBox = await focusGrid.boundingBox();
    expect((expandedWeekBox?.height ?? 0) - (collapsedWeekBox?.height ?? 0)).toBeGreaterThan(0);
    expect((expandedFocusBox?.y ?? 0) - (collapsedFocusBox?.y ?? 0)).toBeGreaterThan(0);
    await expect(weekLegend).toContainText('Силовая');
    await expect(weekLegend).toContainText('Кардио');
    await expect(weekLegend).toContainText('Отдых');
    await expect(weekLegend).toContainText('Выполнено');
    const legendCenterOffset = await weekLegend.evaluate((legend) => {
      const legendItems = Array.from(legend.querySelectorAll<HTMLElement>(':scope > li'));
      const firstItem = legendItems[0];
      if (!firstItem) return Number.POSITIVE_INFINITY;
      const availableBox = legend.getBoundingClientRect();
      const rowTop = firstItem.getBoundingClientRect().top;
      const firstRowItems = legendItems.filter(
        (item) => Math.abs(item.getBoundingClientRect().top - rowTop) <= 1,
      );
      const firstBox = firstRowItems[0]?.getBoundingClientRect();
      const lastBox = firstRowItems.at(-1)?.getBoundingClientRect();
      if (!firstBox || !lastBox) return Number.POSITIVE_INFINITY;
      const rowCenter = (firstBox.left + lastBox.right) / 2;
      return Math.abs(rowCenter - (availableBox.left + availableBox.width / 2));
    });
    expect(legendCenterOffset).toBeLessThanOrEqual(2);
    await expectNoHorizontalOverflow(page);
    await expectNoOverlap(
      page.locator('.demo-cabinet-boundary'),
      page.locator('.demo-cabinet-title'),
    );
    await expectNoOverlap(page.locator('.week-strip'), page.locator('.demo-cabinet-focus-grid'));

    const scenarioSelector = page.getByLabel('Демо-сценарий');
    const moreButton = page.getByRole('button', { name: 'Сценарии' });
    if (viewport.width >= 900) {
      await expect(scenarioSelector).toBeVisible();
      await expect(moreButton).toBeHidden();
      await expect(page.getByText('Отдельная сессия', { exact: true })).toBeVisible();
      await expect(page.getByText('Изолированная сессия', { exact: true })).toHaveCount(0);
    } else {
      await expect(scenarioSelector).toBeHidden();
      await expect(moreButton).toBeVisible();
    }

    const primary = page.getByRole('button', { name: 'Продолжить тренировку' });
    await expect(primary).toBeInViewport();
    await expect(primary).toHaveCSS('border-radius', '12px');
    await expect(primary).toHaveCSS(
      'background-color',
      viewport.dark ? 'rgb(181, 239, 50)' : 'rgb(181, 239, 50)',
    );
    if (viewport.touch) {
      await expectTouchTargets(page.locator('#appBottomNav .app-bottom-nav__primary > *'));
      await expectTouchTargets(primary);
    }
    if (
      CABINET_CAPTURE &&
      [
        'mobile-360-light',
        'mobile-390-light',
        'mobile-390-dark',
        'desktop-1280-light',
        'desktop-1440-dark',
      ].includes(viewport.name)
    ) {
      await page.screenshot({
        path: `${CABINET_SCREENSHOT_DIR}/${viewport.name}-today.png`,
      });
    }
    if (
      TASK_74_CAPTURE &&
      ['mobile-360-light', 'mobile-390-dark', 'desktop-1280-light', 'desktop-1440-dark'].includes(
        viewport.name,
      )
    ) {
      await page.screenshot({
        path: `${TASK_74_SCREENSHOT_DIR}/cabinet-${viewport.name}-today.png`,
      });
    }
    if (viewport.width >= 900) {
      await page.getByRole('link', { name: 'Питание', exact: true }).click();
      const metricSpacing = await page
        .locator('.demo-cabinet-metrics')
        .first()
        .evaluate((node) => {
          const groupStyle = window.getComputedStyle(node);
          const firstMetric = node.querySelector<HTMLElement>('.ui-metric');
          const metricStyle = firstMetric ? window.getComputedStyle(firstMetric) : null;
          return {
            gap: Number.parseFloat(groupStyle.columnGap),
            paddingLeft: Number.parseFloat(metricStyle?.paddingLeft ?? '0'),
          };
        });
      expect(metricSpacing.gap).toBeGreaterThan(0);
      expect(metricSpacing.paddingLeft).toBeGreaterThan(0);
    }
    expect(consoleErrors).toEqual([]);
    expect(pageErrors).toEqual([]);
    await context.close();
  }
});

test('three Web presets keep linked state, conversion and browser history inside the allowlist', async ({
  browser,
}) => {
  const training = await openMobilePage(browser, 'self_training', 390);
  await training.page.goto('/demo?cabinet=1&scenario=self_training&section=today');
  await training.page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await training.page.getByRole('button', { name: 'Завершить текущий подход' }).click();
  await training.page.getByRole('button', { name: 'Завершить тренировку' }).click();
  await expect(training.page).toHaveURL(/section=progress/);
  await expect(training.page.getByText('6 840 кг')).toBeVisible();
  await expect(
    training.page.getByRole('heading', { name: 'Ведите настоящую историю тренировок' }),
  ).toBeVisible();
  if (CABINET_CAPTURE) {
    await training.page
      .getByRole('heading', { name: 'Ведите настоящую историю тренировок' })
      .scrollIntoViewIfNeeded();
    await training.page.screenshot({
      path: `${CABINET_SCREENSHOT_DIR}/mobile-390-training-result-light.png`,
    });
  }
  await training.context.close();

  const nutrition = await openMobilePage(browser, 'nutrition', 430);
  await nutrition.page.goto('/demo?cabinet=1&scenario=nutrition&section=nutrition');
  await nutrition.page.getByRole('button', { name: 'Добавить недавний продукт' }).click();
  await expect(nutrition.page.getByText('1588 / 2150')).toBeVisible();
  await nutrition.page.getByRole('link', { name: /Прогресс/ }).click();
  await expect(
    nutrition.page.getByRole('progressbar', { name: 'Дневной итог питания: 74 из 100 %' }),
  ).toBeVisible();
  await nutrition.page.goBack();
  await expect(nutrition.page).toHaveURL(/section=nutrition/);
  await nutrition.page.goForward();
  await expect(nutrition.page).toHaveURL(/section=progress/);
  await nutrition.page.reload();
  await expect(
    nutrition.page.getByRole('progressbar', { name: 'Дневной итог питания: 74 из 100 %' }),
  ).toBeVisible();
  if (CABINET_CAPTURE) {
    await nutrition.page.screenshot({
      path: `${CABINET_SCREENSHOT_DIR}/mobile-430-nutrition-linked-light.png`,
    });
  }
  await nutrition.context.close();

  const trainer = await openMobilePage(browser, 'trainer', 390);
  await trainer.page.goto('/demo?cabinet=1&scenario=trainer&section=trainer');
  await expect(
    trainer.page.getByRole('heading', {
      name: 'Алексей Воронов — подготовленный демо-клиент',
    }),
  ).toBeVisible();
  await expect(trainer.page.getByLabel('Комментарий к этой тренировке')).toBeVisible();
  if (CABINET_CAPTURE) {
    await trainer.page.screenshot({
      path: `${CABINET_SCREENSHOT_DIR}/mobile-390-trainer-entry-light.png`,
    });
  }
  const trainerComment = trainer.page.getByLabel('Комментарий к этой тренировке');
  const saveComment = trainer.page.getByRole('button', { name: 'Сохранить комментарий' });
  await trainerComment.focus();
  await expect(trainer.page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
  await expect(trainer.page.locator('#appBottomNav')).toBeHidden();
  await trainerComment.fill('Сохраняем темп и добавляем 2,5 кг.');
  await saveComment.scrollIntoViewIfNeeded();
  await expect(saveComment).toBeInViewport();
  await saveComment.click();
  await expect(trainer.page.getByText('Комментарий сохранён до конца демо-сессии')).toBeVisible();
  await expect(
    trainer.page.getByRole('button', { name: 'Пригласить нового клиента' }),
  ).toBeDisabled();
  await expect(
    trainer.page.getByRole('heading', { name: 'Начните работать с реальными клиентами' }),
  ).toBeVisible();
  if (CABINET_CAPTURE) {
    await trainer.page
      .getByRole('heading', { name: 'Начните работать с реальными клиентами' })
      .scrollIntoViewIfNeeded();
    await trainer.page.screenshot({
      path: `${CABINET_SCREENSHOT_DIR}/mobile-390-trainer-result-light.png`,
    });
  }
  await trainer.context.close();
});

test('desktop demo keeps metric groups separated and conversion copy honest', async ({
  browser,
}) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
  const page = await context.newPage();
  if (!LIVE_DEMO) await installDemoApi(page);
  await page.goto('/demo?cabinet=1&scenario=nutrition&section=nutrition');
  await page.getByRole('button', { name: 'Добавить недавний продукт' }).click();

  await expect(page.getByRole('button', { name: 'Сценарии' })).toBeHidden();
  const scenarioSelector = page.getByLabel('Демо-сценарий');
  await expect(scenarioSelector).toHaveValue('nutrition');
  await expect(scenarioSelector.locator('option')).toHaveText(['Для себя', 'Питание', 'Тренер']);
  const scenarioAffordance = await scenarioSelector.evaluate((select) => {
    const control = select as HTMLSelectElement;
    const label = select.closest('label');
    const indicator = label ? window.getComputedStyle(label, '::after') : null;
    const style = window.getComputedStyle(select);
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    if (context) context.font = style.font;
    const selectedLabel = control.options[control.selectedIndex]?.text ?? '';
    return {
      backgroundImage: style.backgroundImage,
      duplicateIndicator: indicator?.content ?? 'none',
      labelWidth: context?.measureText(selectedLabel).width ?? 0,
      paddingLeft: Number.parseFloat(style.paddingLeft),
      paddingRight: Number.parseFloat(style.paddingRight),
      width: select.getBoundingClientRect().width,
    };
  });
  expect(scenarioAffordance.width).toBeGreaterThanOrEqual(118);
  expect(scenarioAffordance.width).toBeLessThanOrEqual(122);
  expect(scenarioAffordance.backgroundImage).not.toBe('none');
  expect(scenarioAffordance.duplicateIndicator).toBe('none');
  expect(
    scenarioAffordance.labelWidth +
      scenarioAffordance.paddingLeft +
      scenarioAffordance.paddingRight,
  ).toBeLessThan(scenarioAffordance.width);
  const logoOffset = await page.locator('#appBottomNav').evaluate((navigation) => {
    const lockup = navigation.querySelector<HTMLElement>('.yfc-lockup');
    if (!lockup) return Number.POSITIVE_INFINITY;
    const navigationBox = navigation.getBoundingClientRect();
    const lockupBox = lockup.getBoundingClientRect();
    return Math.abs(
      navigationBox.left + navigationBox.width / 2 - (lockupBox.left + lockupBox.width / 2),
    );
  });
  expect(logoOffset).toBeLessThanOrEqual(1);
  await expect(
    page.getByRole('heading', { name: 'Настройте дневник питания под себя' }),
  ).toBeVisible();
  await expect(
    page.getByText('Подготовленный пример останется в демо.', { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Войти в приложение' })).toBeVisible();

  await page.getByRole('link', { name: 'Сегодня', exact: true }).click();
  const pictogramSizes = await page.locator('.week-strip__pictogram').evaluateAll((pictograms) =>
    pictograms.map((pictogram) => {
      const box = pictogram.getBoundingClientRect();
      return { height: box.height, width: box.width };
    }),
  );
  expect(pictogramSizes.length).toBeGreaterThan(0);
  expect(
    pictogramSizes.every(
      (size) => Math.abs(size.width - 16) <= 0.1 && Math.abs(size.height - 16) <= 0.1,
    ),
  ).toBe(true);
  const statusGeometry = await page.evaluate(() => {
    const geometry = (kind: string) => {
      const pictogram = document.querySelector<HTMLElement>(
        `.week-strip__pictogram[data-pictogram="${kind}"]`,
      );
      const shape = pictogram?.querySelector<SVGGraphicsElement>('path, circle');
      if (!pictogram || !shape) return null;
      const box = shape.getBBox();
      return {
        canvasHeight: pictogram.getBoundingClientRect().height,
        canvasWidth: pictogram.getBoundingClientRect().width,
        shapeHeight: box.height,
        shapeWidth: box.width,
        strokeWidth: Number.parseFloat(window.getComputedStyle(shape).strokeWidth),
      };
    };
    return { inProgress: geometry('in-progress'), planned: geometry('planned') };
  });
  expect(statusGeometry.planned).toMatchObject({ canvasHeight: 16, canvasWidth: 16 });
  expect(statusGeometry.planned?.shapeHeight).toBeGreaterThanOrEqual(7);
  expect(statusGeometry.planned?.shapeWidth).toBeGreaterThanOrEqual(7);
  expect(statusGeometry.inProgress).toMatchObject({ canvasHeight: 16, canvasWidth: 16 });
  expect(statusGeometry.inProgress?.shapeHeight).toBeGreaterThanOrEqual(9);
  expect(statusGeometry.inProgress?.shapeWidth).toBeGreaterThanOrEqual(4);
  expect(statusGeometry.inProgress?.strokeWidth).toBeGreaterThanOrEqual(1.8);
  const statusColors = await page.evaluate(() => {
    const color = (kind: string) => {
      const pictogram = document.querySelector<HTMLElement>(
        `.week-strip__pictogram[data-pictogram="${kind}"]`,
      );
      return pictogram ? window.getComputedStyle(pictogram).color : null;
    };
    return {
      inProgress: color('in-progress'),
      planned: color('planned'),
      strength: color('strength'),
    };
  });
  expect(statusColors.planned).toBe(statusColors.strength);
  expect(statusColors.planned).toBe(statusColors.inProgress);
  const legendDisclosure = page.locator('.week-strip__legend-disclosure');
  if ((await legendDisclosure.getAttribute('open')) === null) {
    await page.locator('.week-strip__legend-summary').click();
  }
  await expect(page.getByRole('list', { name: 'Обозначения недели' })).toBeVisible();
  const legendCenterOffset = await page
    .locator('.week-strip__legend-disclosure')
    .evaluate((disclosure) => {
      const legend = disclosure.querySelector<HTMLElement>('.week-strip__legend');
      const legendItems = Array.from(legend?.querySelectorAll<HTMLElement>(':scope > li') ?? []);
      const firstItem = legendItems[0];
      if (!legend || !firstItem) return Number.POSITIVE_INFINITY;
      const availableBox = legend.getBoundingClientRect();
      const rowTop = firstItem.getBoundingClientRect().top;
      const firstRowItems = legendItems.filter(
        (item) => Math.abs(item.getBoundingClientRect().top - rowTop) <= 1,
      );
      const firstBox = firstRowItems[0]?.getBoundingClientRect();
      const lastBox = firstRowItems.at(-1)?.getBoundingClientRect();
      if (!firstBox || !lastBox) return Number.POSITIVE_INFINITY;
      const legendCenter = (firstBox.left + lastBox.right) / 2;
      return Math.abs(legendCenter - (availableBox.left + availableBox.width / 2));
    });
  expect(legendCenterOffset).toBeLessThanOrEqual(2);
  await page.getByRole('link', { name: 'Питание', exact: true }).click();

  const nutritionMetrics = page.locator('.demo-cabinet-metrics').first();
  const nutritionGeometry = await nutritionMetrics.evaluate((node) => {
    const metrics = Array.from(node.querySelectorAll<HTMLElement>('.ui-metric'));
    const first = metrics[0];
    const second = metrics[1];
    return {
      gap: Number.parseFloat(window.getComputedStyle(node).columnGap),
      firstPaddingLeft: first ? Number.parseFloat(window.getComputedStyle(first).paddingLeft) : 0,
      renderedGap:
        first && second
          ? second.getBoundingClientRect().left - first.getBoundingClientRect().right
          : 0,
    };
  });
  expect(nutritionGeometry.gap).toBeGreaterThan(0);
  expect(nutritionGeometry.firstPaddingLeft).toBeGreaterThan(0);
  expect(nutritionGeometry.renderedGap).toBeGreaterThan(0);
  if (CABINET_CAPTURE) {
    await page.screenshot({
      path: `${CABINET_SCREENSHOT_DIR}/desktop-1280-nutrition-conversion-light.png`,
    });
  }

  await page.getByRole('link', { name: 'Прогресс', exact: true }).click();
  const progressMetrics = page.locator('.demo-cabinet-metrics').first();
  await expect(progressMetrics).toBeVisible();
  expect(
    await progressMetrics.evaluate((node) => window.getComputedStyle(node).columnGap),
  ).not.toBe('0px');
  if (CABINET_CAPTURE) {
    await page.screenshot({
      path: `${CABINET_SCREENSHOT_DIR}/desktop-1280-progress-conversion-light.png`,
    });
  }
  await context.close();
});

test('desktop demo selector stays compact, readable and deterministic at layout boundaries', async ({
  browser,
}) => {
  const viewports = [
    { width: 1280, height: 900 },
    { width: 1024, height: 900 },
    { width: 900, height: 900 },
  ];

  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    if (!LIVE_DEMO) await installDemoApi(page);
    await page.goto('/demo?cabinet=1&scenario=self_training&section=today');

    const selector = page.getByLabel('Демо-сценарий');
    await expect(selector).toBeVisible();
    for (const option of [
      { label: 'Для себя', value: 'self_training' },
      { label: 'Питание', value: 'nutrition' },
      { label: 'Тренер', value: 'trainer' },
    ]) {
      await selector.selectOption(option.value);
      await expect(selector).toHaveValue(option.value);
      await expect(selector.locator('option:checked')).toHaveText(option.label);
      const fit = await selector.evaluate((select) => {
        const control = select as HTMLSelectElement;
        const style = window.getComputedStyle(select);
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        if (context) context.font = style.font;
        const selectedLabel = control.options[control.selectedIndex]?.text ?? '';
        return {
          available:
            select.clientWidth -
            Number.parseFloat(style.paddingLeft) -
            Number.parseFloat(style.paddingRight),
          label: context?.measureText(selectedLabel).width ?? 0,
          width: select.getBoundingClientRect().width,
        };
      });
      expect(fit.width).toBeGreaterThanOrEqual(118);
      expect(fit.width).toBeLessThanOrEqual(122);
      expect(fit.label).toBeLessThan(fit.available);
    }

    const layout = await page.locator('.demo-cabinet-boundary').evaluate((boundary) => {
      const intro = boundary.querySelector<HTMLElement>(':scope > div:first-child');
      const scenario = boundary.querySelector<HTMLElement>('.demo-cabinet-boundary__scenario');
      const actions = boundary.querySelector<HTMLElement>('.demo-cabinet-boundary__actions');
      if (!intro || !scenario || !actions) return null;
      const introBox = intro.getBoundingClientRect();
      const scenarioBox = scenario.getBoundingClientRect();
      const actionsBox = actions.getBoundingClientRect();
      return {
        actionsCenter: actionsBox.top + actionsBox.height / 2,
        introBottom: introBox.bottom,
        introCenter: introBox.top + introBox.height / 2,
        scenarioCenter: scenarioBox.top + scenarioBox.height / 2,
        scenarioTop: scenarioBox.top,
      };
    });
    expect(layout).not.toBeNull();
    if (viewport.width >= 1100) {
      expect(
        Math.abs((layout?.introCenter ?? 0) - (layout?.scenarioCenter ?? 0)),
      ).toBeLessThanOrEqual(2);
    } else {
      expect((layout?.scenarioTop ?? 0) - (layout?.introBottom ?? 0)).toBeGreaterThan(0);
    }
    expect(
      Math.abs((layout?.scenarioCenter ?? 0) - (layout?.actionsCenter ?? 0)),
    ).toBeLessThanOrEqual(2);

    if (CABINET_CAPTURE) {
      await page.screenshot({
        path: `${CABINET_SCREENSHOT_DIR}/desktop-${viewport.width}-selector-trainer-light.png`,
        fullPage: true,
      });
    }
    await context.close();
  }

  const forcedColorsContext = await browser.newContext({
    forcedColors: 'active',
    viewport: { width: 1280, height: 900 },
  });
  const forcedColorsPage = await forcedColorsContext.newPage();
  if (!LIVE_DEMO) await installDemoApi(forcedColorsPage);
  await forcedColorsPage.goto('/demo?cabinet=1&scenario=self_training&section=today');
  const forcedColorsSelect = forcedColorsPage.getByLabel('Демо-сценарий');
  const forcedColorsStyle = await forcedColorsSelect.evaluate((select) => {
    const style = window.getComputedStyle(select);
    return { appearance: style.appearance, backgroundImage: style.backgroundImage };
  });
  expect(forcedColorsStyle.appearance).toBe('auto');
  expect(forcedColorsStyle.backgroundImage).toBe('none');
  await forcedColorsContext.close();
});

test('Web cabinet auth return stays clean and damaged routes recover safely', async ({
  browser,
}) => {
  const context = await browser.newContext({ viewport: MOBILE_CONTEXTS.baseline, hasTouch: true });
  const page = await context.newPage();
  await installDemoApi(page);
  await installAuthApi(page);

  await page.goto('/demo?cabinet=1&scenario=nutrition&section=admin');
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=nutrition&section=today');
  await page.getByRole('button', { name: 'Добавить недавний продукт' }).click();
  await page.getByRole('link', { name: 'Войти в приложение' }).click();
  await expect(page).toHaveURL(
    '/login?next=%2Fapp&from=demo&scenario=nutrition&cabinet=1&section=today',
  );
  await expect(page.getByText('После демо — чистый профиль')).toBeVisible();
  if (CABINET_CAPTURE) {
    await page.screenshot({
      path: `${CABINET_SCREENSHOT_DIR}/mobile-390-auth-return-light.png`,
    });
  }
  await page.getByRole('link', { name: 'Вернуться в демо' }).click();
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=nutrition&section=today');
  await expect(page.getByRole('button', { name: 'Добавить недавний продукт' })).toBeVisible();
  await context.close();
});

test('Web cabinet reset, reload, expired and forbidden states are predictable', async ({
  browser,
}) => {
  const { api, context, page } = await openMobilePage(browser, 'nutrition', 390);
  await page.goto('/demo?cabinet=1&scenario=nutrition&section=nutrition');
  await page.getByRole('button', { name: 'Добавить недавний продукт' }).click();
  await page.reload();
  await expect(page.getByText('1588 / 2150')).toBeVisible();
  await page.getByRole('button', { name: 'Сбросить' }).click();
  await expect(page.getByText('1160 / 2150')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Добавить недавний продукт' })).toBeVisible();
  if (api) api.setUnavailable(true);
  else await setNetworkOffline(page, true);
  await page.getByRole('button', { name: 'Добавить недавний продукт' }).click();
  await expect(page.getByText(/Нет соединения с сервером/)).toBeVisible();
  if (api) api.setUnavailable(false);
  else await setNetworkOffline(page, false);
  await page.getByRole('button', { name: 'Повторить' }).click();
  await expect(page.getByRole('button', { name: 'Добавить недавний продукт' })).toBeVisible();
  await context.close();

  if (LIVE_DEMO) return;

  for (const status of [410, 403] as const) {
    const stateContext = await browser.newContext({ viewport: MOBILE_CONTEXTS.baseline });
    const statePage = await stateContext.newPage();
    await statePage.addInitScript(() => {
      sessionStorage.setItem(
        'fit_demo_sessions_v1',
        JSON.stringify({ self_training: 'forced-demo-token-000000000000000000000000' }),
      );
    });
    await installDemoApi(statePage, status);
    await statePage.goto('/demo?cabinet=1&scenario=self_training&section=today');
    await expect(
      statePage.getByText(status === 410 ? /Демо-сессия истекла/ : /действие недоступно/),
    ).toBeVisible();
    if (CABINET_CAPTURE) {
      await statePage.screenshot({
        path: `${CABINET_SCREENSHOT_DIR}/${status === 410 ? 'expired' : 'forbidden'}-390.png`,
        fullPage: true,
      });
    }
    await stateContext.close();
  }
});

test('desktop keeps the canonical content width and separated adjacent regions', async ({
  browserName,
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  if (!LIVE_DEMO) await installDemoApi(page);
  await page.goto('/demo?scenario=self_training');
  await expect(page.getByText('Демо', { exact: true })).toBeVisible();
  const skipLink = page.getByRole('link', { name: 'К демо-сценарию' });
  if (browserName === 'webkit') await skipLink.focus();
  else await page.keyboard.press('Tab');
  await expect(skipLink).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#demoContent')).toBeFocused();

  const geometry = await page.evaluate(() => {
    const main = document.querySelector<HTMLElement>('.demo-main')!.getBoundingClientRect();
    const boundary = document.querySelector<HTMLElement>('.demo-boundary')!.getBoundingClientRect();
    const stage = document.querySelector<HTMLElement>('.demo-stage')!.getBoundingClientRect();
    return {
      mainWidth: main.width,
      boundaryRight: boundary.right,
      stageLeft: stage.left,
      stageRight: stage.right,
      viewportWidth: document.documentElement.clientWidth,
    };
  });
  expect(geometry.mainWidth).toBeLessThanOrEqual(980);
  expect(geometry.boundaryRight).toBeLessThan(geometry.stageLeft);
  expect(geometry.stageRight).toBeLessThanOrEqual(geometry.viewportWidth);
  if (CAPTURE) {
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/desktop-1280-training-light.png`,
      fullPage: true,
    });
  }

  await page.getByRole('button', { name: 'Начать тренировку' }).click();
  await page.getByRole('button', { name: 'Завершить текущий подход' }).click();
  await page.getByRole('button', { name: 'Завершить тренировку' }).click();
  await expectMetricSpacing(page);
  await page.getByRole('button', { name: 'Перейти к прогрессу' }).click();
  if (CAPTURE) {
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/desktop-1280-training-conversion-light.png`,
      fullPage: true,
    });
  }

  await page.setViewportSize({ width: 768, height: 900 });
  await expectNoHorizontalOverflow(page);
  await expectNoOverlap(page.locator('.demo-stage'), page.locator('.demo-boundary'));
});

test('Landing entry opens the cabinet and keeps scenario history plus browser auth return explicit', async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: MOBILE_CONTEXTS.baseline,
    hasTouch: true,
    isMobile: true,
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  await installAuthApi(page);
  await installDemoApi(page);

  await page.goto('/');
  await page
    .locator('.landing-hero__actions')
    .getByRole('link', { name: /Попробовать демо/ })
    .click();
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=self_training&section=today');
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await page.getByRole('button', { name: 'Завершить текущий подход' }).click();
  await page.getByRole('button', { name: 'Завершить тренировку' }).click();
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=self_training&section=progress');
  await expect(
    page.getByRole('heading', { name: 'Подтверждённые действия становятся историей' }),
  ).toBeVisible();
  const demoTokenBeforeHandoff = await page.evaluate(() =>
    sessionStorage.getItem('fit_demo_sessions_v1'),
  );
  expect(demoTokenBeforeHandoff).not.toBeNull();

  await page.getByRole('link', { name: 'Войти в приложение' }).click();
  await expect(page).toHaveURL(
    '/login?next=%2Fapp&from=demo&scenario=self_training&cabinet=1&section=progress',
  );
  await expect(page.getByText('После демо — чистый профиль')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Продолжить с Google' })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('fit_demo_sessions_v1'))).toBeNull();
  if (CAPTURE) {
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/mobile-web-390-auth-handoff-light.png`,
      fullPage: true,
    });
  }

  await page.getByRole('link', { name: 'Вернуться в демо' }).click();
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=self_training&section=progress');
  await expect(
    page.getByRole('heading', { name: 'Подтверждённые действия становятся историей' }),
  ).toBeVisible();
  const demoTokenAfterReturn = await page.evaluate(() =>
    sessionStorage.getItem('fit_demo_sessions_v1'),
  );
  expect(demoTokenAfterReturn).not.toBe(demoTokenBeforeHandoff);

  await page.getByRole('button', { name: 'Сценарии' }).click();
  await page.getByRole('link', { name: 'Питание: дневник и итог' }).click();
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=nutrition&section=today');
  await page.getByRole('button', { name: 'Сценарии' }).click();
  await page.getByRole('link', { name: 'Тренер: разбор результата клиента' }).click();
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=trainer&section=trainer');
  await page.goBack();
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=nutrition&section=today');
  await context.close();
});

test('signed TMA launch clears a stale Web demo session before clean first run', async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: MOBILE_CONTEXTS.baseline,
    hasTouch: true,
    isMobile: true,
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  await page.addInitScript(() => {
    sessionStorage.setItem(
      'fit_demo_sessions_v1',
      JSON.stringify({ nutrition: 'stale-web-demo-token-000000000000000000000000' }),
    );
  });
  await installTelegramHarness(page, { colorScheme: 'dark' });
  await installAuthApi(page);
  await page.goto('/demo?scenario=nutrition&tgWebAppPlatform=android');

  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole('heading', { level: 1, name: /^Сегодня ·/ })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('fit_demo_sessions_v1'))).toBeNull();
  await context.close();
});
