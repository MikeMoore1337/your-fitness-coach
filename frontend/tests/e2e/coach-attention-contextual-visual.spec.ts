import { expect, test, type Locator, type Page } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import {
  expectNoHorizontalOverflow,
  expectTouchTargets,
  installTelegramHarness,
} from './fixtures/mobile-tma';

const FIXED_DATE = '2026-09-06';

async function enableAiCoach(page: import('@playwright/test').Page): Promise<void> {
  await page.route('**/api/v1/ai-coach/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith('/status')) {
      await route.fulfill({
        json: { ui_enabled: true, generic_available: true, personal_available: true },
      });
      return;
    }
    if (url.pathname.endsWith('/quota')) {
      await route.fulfill({
        json: {
          limit: 20,
          used: 2,
          remaining: 18,
          reset_at: '2026-09-07T12:00:00+03:00',
          retry_after_seconds: 86400,
          can_send: true,
        },
      });
      return;
    }
    if (url.pathname.endsWith('/conversations')) {
      await route.fulfill({ json: { items: [] } });
      return;
    }
    if (url.pathname.endsWith('/memory')) {
      await route.fulfill({
        json: {
          status: 'revoked',
          scope: 'ai_coach_memory_v1',
          consent_version: 'ai-coach-memory-v1',
          categories: [],
          category_labels: {},
          purpose: 'Отдельный контекст.',
          retention_notice: 'История и память разделены.',
          max_items: 20,
          consent_source: 'test',
          items: [],
          granted_at: null,
          paused_at: null,
          revoked_at: '2026-09-06T12:00:00Z',
        },
      });
      return;
    }
    await route.fallback();
  });
}

async function expectNoVisibleOverlap(
  first: Locator,
  second: Locator,
  description: string,
): Promise<void> {
  const [firstCount, secondCount] = await Promise.all([first.count(), second.count()]);
  if (firstCount === 0 || secondCount === 0) return;
  const [firstBox, secondBox] = await Promise.all([
    first.first().boundingBox(),
    second.first().boundingBox(),
  ]);
  if (!firstBox || !secondBox) return;
  const overlaps =
    firstBox.x < secondBox.x + secondBox.width &&
    firstBox.x + firstBox.width > secondBox.x &&
    firstBox.y < secondBox.y + secondBox.height &&
    firstBox.y + firstBox.height > secondBox.y;
  expect(overlaps, `${description}: ${JSON.stringify({ firstBox, secondBox })}`).toBe(false);
}

async function assertTodayFloatingGeometry(page: Page): Promise<void> {
  const quickAdd = page.getByTestId('quick-add-trigger');
  const bottomNav = page.locator('#appBottomNav');
  const workoutAction = page.locator('.today-workout-actions .today-pulse-action:visible');
  await expectNoVisibleOverlap(quickAdd, bottomNav, 'Today FAB must not overlap bottom navigation');
  await expectNoVisibleOverlap(
    quickAdd,
    workoutAction,
    'Today FAB must not overlap the primary workout action',
  );
  await expectNoVisibleOverlap(
    bottomNav,
    workoutAction,
    'Today bottom navigation must not overlap the primary workout action',
  );
}

async function assertTodayHasNoPermanentAiEntry(page: Page): Promise<void> {
  await expect(page.getByTestId('ai-coach-contextual-entry-today')).toHaveCount(0);
  await expect(page.getByText('Разобрать: сегодня', { exact: false })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Спросить AI', exact: true })).toHaveCount(0);
}

test('Task 284 keeps the planned workout primary and removes the permanent Today AI entry', async ({
  page,
}) => {
  await installPlatformApi(page, { browserSession: true, fixedDate: FIXED_DATE });
  await enableAiCoach(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.goto('/app?section=today');

  await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  await assertTodayHasNoPermanentAiEntry(page);
  await expect(page.locator('.today-workout-spotlight')).toBeVisible();
  await expect(page.locator('.today-workout-actions .today-pulse-action:visible')).toBeVisible();
  await expectNoVisibleOverlap(
    page.getByTestId('quick-add-trigger'),
    page.locator('#appBottomNav'),
    'Desktop Today FAB must not overlap the navigation rail',
  );
  await expectNoHorizontalOverflow(page);
});

test('Task 284 keeps Today floating geometry across supported responsive widths without an AI CTA', async ({
  page,
}) => {
  await installPlatformApi(page, { browserSession: true, fixedDate: FIXED_DATE });
  await enableAiCoach(page);

  for (const viewport of [
    { width: 320, height: 568 },
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 768, height: 900 },
    { width: 1280, height: 900 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    await page.goto('/app?section=today');
    await assertTodayHasNoPermanentAiEntry(page);
    await expect(page.locator('.today-workout-actions .today-pulse-action:visible')).toBeVisible();
    await assertTodayFloatingGeometry(page);
    await expectNoHorizontalOverflow(page);
    if (viewport.width <= 430) {
      await expectTouchTargets(page.locator('.today-workout-actions .today-pulse-action:visible'));
    }
  }
});

test('Task 284 exposes contextual entries on workout, nutrition, program and progress surfaces', async ({
  page,
}) => {
  await installPlatformApi(page, { browserSession: true, fixedDate: FIXED_DATE });
  await enableAiCoach(page);

  await page.goto('/app?section=today');
  await page.getByRole('button', { name: 'Посмотреть упражнения' }).click();
  const primaryWorkoutAction = page.getByRole('button', { name: 'Начать тренировку', exact: true });
  await expect(primaryWorkoutAction).toBeVisible();
  const workoutEntry = page.getByTestId('ai-coach-contextual-entry-workout');
  await expect(workoutEntry).toBeVisible();
  await expect(workoutEntry).toContainText('Разобрать: эта тренировка');
  const primaryActionComesFirst = await page.evaluate(() => {
    const primary = document.querySelector('.today-workout-focus .active-workout > button');
    const contextual = document.querySelector('[data-testid="ai-coach-contextual-entry-workout"]');
    return Boolean(
      primary &&
      contextual &&
      primary.compareDocumentPosition(contextual) & Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
  expect(primaryActionComesFirst).toBe(true);
  await workoutEntry.getByRole('link', { name: 'Спросить про тренировку' }).click();
  const workspace = page.getByTestId('ai-coach-workspace');
  await expect(workspace).toBeVisible();
  await expect(page.getByTestId('ai-coach-context-attachment')).toContainText('Эта тренировка');
  await expect(page.getByRole('textbox', { name: 'Сообщение AI Coach' })).toHaveValue('');
  await expect(page.getByRole('textbox', { name: 'Сообщение AI Coach' })).toBeFocused();
  await expectNoVisibleOverlap(
    workspace,
    page.getByTestId('quick-add-trigger'),
    'Desktop contextual workspace must not overlap the floating + action',
  );
  await expectNoVisibleOverlap(
    workspace,
    page.locator('#appBottomNav'),
    'Desktop contextual workspace must not overlap bottom navigation',
  );
  await expectNoVisibleOverlap(
    workspace,
    page.locator('.today-workout-focus .active-workout > button:visible'),
    'Desktop contextual workspace must not overlap the primary workout action',
  );
  await workspace.getByRole('button', { name: 'Закрыть AI Coach' }).click();
  await expect(workspace).toHaveCount(0);

  for (const surface of [
    {
      path: '/app?section=nutrition',
      testId: 'ai-coach-contextual-entry-nutrition',
      label: 'Разобрать: питание за 7 дней',
    },
    {
      path: '/app?section=programs',
      testId: 'ai-coach-contextual-entry-program',
      label: 'Разобрать: активная программа',
    },
    {
      path: '/app?section=progress',
      testId: 'ai-coach-contextual-entry-progress',
      label: 'Разобрать: прогресс за 30 дней',
    },
  ]) {
    await page.goto(surface.path);
    const entry = page.getByTestId(surface.testId);
    await expect(entry).toBeVisible();
    await expect(entry).toContainText(surface.label);
    await expectNoHorizontalOverflow(page);
  }
});

test('Task 284 attention center renders a compact deterministic trainer surface', async ({
  page,
}) => {
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: FIXED_DATE,
    trainerActive: true,
  });
  await page.route('**/api/v1/coach/attention**', async (route) => {
    await route.fulfill({
      json: {
        total: 2,
        generated_at: '2026-09-06T12:00:00Z',
        items: [
          {
            key: 'weekly_check_in:11:44',
            kind: 'weekly_check_in',
            client: { id: 11, name: 'Анна Петрова' },
            title: 'Новый недельный итог',
            reason: 'Клиент заполнил недельный итог.',
            source_kind: 'weekly_check_in',
            source_id: 44,
            source_state: 'completed',
            action: 'review_check_in',
            destination: '/coach?client_id=11&focus=weekly_check_in',
            created_at: '2026-09-06T11:00:00Z',
          },
          {
            key: 'workout_feedback:11:43',
            kind: 'workout_feedback',
            client: { id: 11, name: 'Анна Петрова' },
            title: 'Новая обратная связь по тренировке',
            reason: 'Клиент отметил тренировку как «тяжелее, чем ожидалось».',
            source_kind: 'workout',
            source_id: 43,
            source_state: 'harder_than_expected',
            action: 'review_workout',
            destination: '/coach?client_id=11&workout_id=43',
            created_at: '2026-09-06T10:00:00Z',
          },
        ],
      },
    });
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.goto('/coach');

  await expect(page.getByRole('heading', { name: 'Что требует действия?' })).toBeVisible();
  const center = page.getByRole('region', { name: 'Требует внимания' });
  await expect(center).toBeVisible();
  await expect(center).toContainText('Анна Петрова');
  await expect(center).toContainText('Новый недельный итог');
  await expectNoHorizontalOverflow(page);
});

test('Task 284 keeps contextual entry usable in dark mocked TMA', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await installTelegramHarness(page, {
    colorScheme: 'dark',
    viewportHeight: 760,
    viewportStableHeight: 844,
    safeAreaInset: { top: 28, right: 2, bottom: 20, left: 2 },
    contentSafeAreaInset: { top: 44, right: 0, bottom: 16, left: 0 },
  });
  await installPlatformApi(page, { fixedDate: FIXED_DATE });
  await enableAiCoach(page);
  await page.goto('/app?section=today&tgWebAppPlatform=android');

  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
  await expect(page.locator('.today-workout-actions .today-pulse-action:visible')).toBeVisible();
  await assertTodayHasNoPermanentAiEntry(page);
  await assertTodayFloatingGeometry(page);
  await expectNoHorizontalOverflow(page);
  await expectTouchTargets(page.locator('.today-workout-actions .today-pulse-action:visible'));
});
