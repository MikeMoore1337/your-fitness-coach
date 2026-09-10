import type { Locator, Page } from '@playwright/test';
import {
  expect,
  expectNoHorizontalOverflow,
  expectNoOverlap,
  expectTouchTargets,
  installTelegramHarness,
  MOBILE_CONTEXTS,
  setNetworkOffline,
  sharedSurfaceSignature,
  test,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';
import { makeProgressReportFixture } from '../fixtures/progress-report';
import { namedArticle, notificationArticle } from './fixtures/locators';

const todayStates = [
  { name: 'planned', options: { workoutStatus: 'planned' as const }, action: 'Начать тренировку' },
  {
    name: 'in-progress',
    options: { workoutStatus: 'in_progress' as const },
    action: 'Продолжить тренировку',
  },
  {
    name: 'completed',
    options: { workoutStatus: 'completed' as const },
    action: 'Вернуться в Сегодня',
  },
  { name: 'rest', options: { workoutStatus: 'none' as const }, action: 'Добавить питание' },
  {
    name: 'no-program',
    options: { workoutStatus: 'none' as const, activeProgram: false },
    action: 'Создать свою программу',
  },
] as const;

const TASK_74_CAPTURE_PHASE = (
  globalThis as { process?: { env?: Record<string, string | undefined> } }
).process?.env?.YFC_CAPTURE_TASK_74_PHASE;
const TASK_74_SCREENSHOT_DIR = '../.artifacts/screenshots/task-74';

async function waitForVisualStability(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
  });
}

async function expectLimeStartBoundary(locator: Locator) {
  const colors = await locator.evaluate((element) => {
    const sample = document.createElement('span');
    sample.style.color = 'var(--v2-lime)';
    document.body.append(sample);
    const lime = getComputedStyle(sample).color;
    sample.remove();
    return {
      boundary: getComputedStyle(element).borderInlineStartColor,
      lime,
    };
  });
  expect(colors.boundary).toBe(colors.lime);
}

async function installBarcodeCameraCapability(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(globalThis, 'BarcodeDetector', {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: async () => {
          throw new DOMException(
            'Evidence harness does not open a real camera.',
            'NotAllowedError',
          );
        },
      },
    });
  });
}

test('TMA auth, shared UI, theme, viewport, safe areas and BackButton stay on one platform contract', async ({
  browserName,
  mobilePage,
  tma,
  tmaPage,
}) => {
  const tmaApi = await installPlatformApi(tmaPage);
  await installPlatformApi(mobilePage, { browserSession: true });

  await Promise.all([tmaPage.goto('/app'), mobilePage.goto('/app')]);
  await expect(tmaPage.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  await expect(mobilePage.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  expect(tmaApi.authInitCalls()).toBe(1);
  await expect(tmaPage.getByRole('heading', { name: 'Вход' })).not.toBeAttached();
  await expect(tmaPage.locator('body')).not.toContainText('query_id=test');
  await expect(tmaPage.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');
  await expect(mobilePage.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'browser');
  expect(await tmaPage.evaluate(() => matchMedia('(hover: none)').matches)).toBe(true);
  if (browserName === 'chromium') {
    expect(await tmaPage.evaluate(() => navigator.maxTouchPoints)).toBeGreaterThan(0);
  }
  expect(await sharedSurfaceSignature(tmaPage)).toEqual(await sharedSurfaceSignature(mobilePage));

  for (const viewport of Object.values(MOBILE_CONTEXTS)) {
    await tmaPage.setViewportSize(viewport);
    await tma.setViewport(viewport.height, viewport.height);
    await expectNoHorizontalOverflow(tmaPage);
  }
  await expectTouchTargets(
    tmaPage.locator('.app-bottom-nav__primary > a, .app-bottom-nav__primary > button'),
  );
  await expectTouchTargets(tmaPage.locator('.week-strip__day--interactive'));
  await expectNoOverlap(
    tmaPage.getByRole('button', { name: 'Начать тренировку' }),
    tmaPage.locator('#appBottomNav'),
  );

  await tma.setSafeArea({ top: 28, right: 2, bottom: 20, left: 2 });
  await tma.setContentSafeArea({ top: 44, right: 0, bottom: 16, left: 0 });
  await expect(tmaPage.locator('html')).toHaveCSS('--yfc-tg-safe-bottom', '20px');
  await expect(tmaPage.locator('html')).toHaveCSS('--yfc-tg-content-safe-top', '44px');

  const routeBeforeTheme = tmaPage.url();
  await tma.setTheme('dark');
  await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  expect(tmaPage.url()).toBe(routeBeforeTheme);
  await tma.setTheme('light');
  await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', 'light');

  await tma.setActive(false);
  await expect(tmaPage.locator('html')).toHaveAttribute('data-yfc-viewport-active', 'false');
  const meCallsBeforeRestore = tmaApi.meCalls();
  await tma.setActive(true);
  await expect(tmaPage.locator('html')).toHaveAttribute('data-yfc-viewport-active', 'true');
  await expect.poll(() => tmaApi.meCalls()).toBeGreaterThan(meCallsBeforeRestore);
  const lifecycleState = await tma.state();
  expect(lifecycleState.version).toBe('8.0');
  expect(lifecycleState.platform).toBe('android');
  expect(lifecycleState.ready).toBeGreaterThan(0);
  expect(lifecycleState.expand).toBeGreaterThan(0);
  expect(lifecycleState.platformButtons).toEqual({
    main: { visible: false, shown: 0, hidden: 0 },
    secondary: { visible: false, shown: 0, hidden: 0 },
  });

  const workoutDays = tmaPage.getByRole('button', {
    name: /Силовая.*(?:Запланировано|Предстоит тренировка|Выполнено)/i,
  });
  const contextualDayIndex = await workoutDays.evaluateAll((days) =>
    days.findIndex((day) => day.getAttribute('aria-current') !== 'date'),
  );
  expect(contextualDayIndex).toBeGreaterThanOrEqual(0);
  const contextualWorkoutDay = workoutDays.nth(contextualDayIndex);
  await contextualWorkoutDay.click();
  const weekLink = tmaPage.getByRole('link', { name: 'Открыть тренировку' });
  await weekLink.focus();
  await expect(weekLink).toBeFocused();
  await weekLink.press('Enter');
  await expect(tmaPage).toHaveURL(/section=progress&workout_id=43/);
  await expect(
    tmaPage.locator('#workout-schedule-43').or(tmaPage.locator('#workout-history-43')),
  ).toBeVisible();
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(true);
  await tma.clickBack();
  await expect(tmaPage).toHaveURL('/app?section=progress');
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(false);
});

test('progress report starts native PDF download and keeps BackButton contract', async ({
  tma,
  tmaPage,
}) => {
  await installPlatformApi(tmaPage);
  await tmaPage.route(
    /\/api\/v1\/workouts\/progress\/report(?:\/download-link)?(?:\?|$)/,
    async (route) => {
      const url = new URL(route.request().url());
      if (route.request().method() === 'POST' && url.pathname.endsWith('/download-link')) {
        await route.fulfill({
          json: {
            url: `${url.origin}/api/v1/workouts/progress/report/file/signed-smoke`,
            filename: 'progress-report-2026-07-26_2026-08-24.pdf',
            expires_at: '2026-08-29T19:05:00Z',
          },
        });
        return;
      }
      await route.fulfill({ json: makeProgressReportFixture('partial') });
    },
  );
  await tmaPage.goto('/app/report?period=days_90');

  await expect(tmaPage.getByRole('heading', { name: 'Александр Петров' })).toBeVisible();
  await expectNoHorizontalOverflow(tmaPage);
  await tmaPage.getByRole('button', { name: 'Скачать PDF' }).click();
  await expect(tmaPage.getByText('Telegram открыл сохранение PDF.')).toBeVisible();
  await expect
    .poll(async () => (await tma.state()).downloads)
    .toEqual([
      {
        url: `${new URL(tmaPage.url()).origin}/api/v1/workouts/progress/report/file/signed-smoke`,
        fileName: 'progress-report-2026-07-26_2026-08-24.pdf',
      },
    ]);
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(true);
  await tma.clickBack();
  await expect(tmaPage).toHaveURL('/app?section=progress');
});

test('an unplanned day keeps the first factual cardio entry compact but available in Today', async ({
  tma,
  tmaPage,
}) => {
  await installPlatformApi(tmaPage, { cardioState: 'empty' });
  const cardioRequest = tmaPage.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith('/api/v1/workouts/cardio') && url.searchParams.has('date_from');
  });
  await tmaPage.goto('/app?section=today');
  await cardioRequest;

  const cardio = tmaPage.locator('.cardio-log--quick');
  await expect(cardio).toHaveClass(/cardio-log--empty/);
  await expect(cardio.getByRole('heading', { name: 'Кардио', exact: true })).toBeVisible();
  await expect(cardio.getByRole('button', { name: 'Добавить' })).toBeVisible();
  await expect(cardio.getByLabel('Длительность, мин')).toHaveCount(0);
  await cardio.scrollIntoViewIfNeeded();
  await cardio.screenshot({
    path: '../.artifacts/screenshots/task-113A-round-5/tma-cardio-empty-entry-390x844.png',
  });

  await cardio.getByRole('button', { name: 'Добавить' }).click();
  const duration = cardio.getByLabel('Длительность, мин');
  await duration.focus();
  await expect(tmaPage.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
  await expect(duration).toBeVisible();
  await expect(tmaPage.locator('#appBottomNav')).toBeHidden();
  await tma.setActive(false);
  await tma.setActive(true);
  await expect(duration).toBeVisible();
});

test('cardio quick log keeps retry, editing and shared Mobile Web/TMA behavior', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  test.setTimeout(90_000);
  const tmaApi = await installPlatformApi(tmaPage, { cardioState: 'planned' });
  const mobileApi = await installPlatformApi(mobilePage, {
    browserSession: true,
    cardioState: 'planned',
  });
  await Promise.all([tmaPage.goto('/app'), mobilePage.goto('/app')]);

  for (const page of [tmaPage, mobilePage]) {
    const cardio = page.locator('.cardio-log--quick');
    await cardio.scrollIntoViewIfNeeded();
    await expect(cardio.getByRole('heading', { name: 'Кардио', exact: true })).toBeVisible();
    await expect(cardio.getByRole('heading', { name: 'План кардио' })).toBeVisible();
    await expect(cardio.getByRole('button', { name: 'Добавить фактическое кардио' })).toBeVisible();
    await expect(cardio.getByRole('button', { name: 'Сохранить кардио' })).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
  }
  expect(await sharedSurfaceSignature(tmaPage)).toEqual(await sharedSurfaceSignature(mobilePage));
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-113A-round-2/tma-cardio-planned-first-390x844-light.png',
  });

  const tmaCardio = tmaPage.locator('.cardio-log--quick');
  await tmaCardio.getByRole('button', { name: 'Добавить фактическое кардио' }).click();
  await expect(tmaCardio.getByLabel('Статус')).toHaveCount(0);
  const duration = tmaCardio.getByLabel('Длительность, мин');
  await tmaCardio.getByLabel('Вид активности').selectOption('stationary_bike');
  await duration.focus();
  await expect(tmaPage.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
  await expect(tmaPage.locator('#appBottomNav')).toBeHidden();
  await duration.fill('35');
  await tmaCardio.getByText('Дистанция, пульс и заметка').click();
  await tmaCardio.getByLabel('Дистанция, км').fill('5.2');
  await tmaCardio.getByLabel('Средний пульс, уд/мин').fill('142');
  await tmaCardio.getByLabel('Зона пульса').selectOption('3');
  await tmaCardio.getByLabel('Заметка').fill('Ровный темп, без часов');
  await tma.setActive(false);
  await tma.setActive(true);
  await expect(duration).toHaveValue('35');
  const saveCardio = tmaCardio.getByRole('button', { name: 'Сохранить кардио' });
  await saveCardio.scrollIntoViewIfNeeded();
  await expectNoOverlap(saveCardio, tmaPage.locator('#appBottomNav'));
  tmaApi.failNextCardioSave();
  await saveCardio.click();
  await expect.poll(() => tmaApi.cardioSaveCalls()).toBe(1);
  await expect(tmaCardio.getByRole('alert')).toContainText('Временная ошибка сохранения');
  await expect(duration).toHaveValue('35');
  await expect(tmaCardio.getByLabel('Заметка')).toHaveValue('Ровный темп, без часов');

  await saveCardio.click();
  await expect.poll(() => tmaApi.cardioSaveCalls()).toBe(2);
  const savedTmaRow = tmaCardio.locator('.cardio-session-row').filter({ hasText: '35 мин' });
  await expect(savedTmaRow).toContainText('5,2 км');
  await expect(savedTmaRow).toContainText('Велотренажёр / велоэргометр');
  await expect(tmaCardio.getByRole('heading', { name: 'Результат кардио' })).toBeVisible();
  await expect(tmaCardio.locator('.cardio-log__today > h3')).toHaveText([
    'Результат кардио',
    'План кардио',
  ]);
  await expect(tmaCardio.getByText('2 сегодня')).toBeVisible();
  await expect(tmaCardio.getByRole('button', { name: 'Добавить ещё кардио' })).toBeVisible();
  await savedTmaRow.getByRole('button', { name: 'Изменить' }).click();
  const editForm = tmaCardio.locator('.cardio-session-row--editing');
  await editForm.getByLabel('Длительность, мин').fill('40');
  await editForm.getByRole('button', { name: 'Сохранить изменения' }).click();
  await expect.poll(() => tmaApi.cardioSaveCalls()).toBe(3);
  const finalTmaRow = tmaCardio.locator('.cardio-session-row').filter({ hasText: '40 мин' });
  await expect(finalTmaRow).toBeVisible();
  await expect(finalTmaRow.getByText('Завершено')).toHaveCSS('white-space', 'nowrap');
  await tmaCardio.screenshot({
    path: '../.artifacts/screenshots/task-113A-round-2/tma-cardio-completed-result-first-390x844-light.png',
  });

  const mobileCardio = mobilePage.locator('.cardio-log--quick');
  await mobileCardio.getByRole('button', { name: 'Добавить фактическое кардио' }).click();
  await mobileCardio.getByLabel('Длительность, мин').fill('25');
  await mobileCardio.getByRole('button', { name: 'Сохранить кардио' }).click();
  await expect.poll(() => mobileApi.cardioSaveCalls()).toBe(1);
  const savedMobileRow = mobileCardio.locator('.cardio-session-row').filter({ hasText: '25 мин' });
  await expect(savedMobileRow).toBeVisible();

  for (const viewport of Object.values(MOBILE_CONTEXTS)) {
    await tmaPage.setViewportSize(viewport);
    await tma.setViewport(viewport.height, viewport.height);
    await expectNoHorizontalOverflow(tmaPage);
    await expectTouchTargets(tmaCardio.locator('.cardio-session-row__actions .ui-button'));
  }
  await tmaPage.setViewportSize(MOBILE_CONTEXTS.baseline);
  await tma.setViewport(MOBILE_CONTEXTS.baseline.height, MOBILE_CONTEXTS.baseline.height);
  await tma.setTheme('dark');
  const tmaToastClose = tmaPage.getByRole('button', { name: 'Закрыть сообщение', exact: true });
  if (await tmaToastClose.isVisible()) await tmaToastClose.click();
  await finalTmaRow.scrollIntoViewIfNeeded();
  await expectNoOverlap(finalTmaRow, tmaPage.locator('#appBottomNav'));
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-66/tma-390x844-dark-cardio-saved.png',
  });

  await mobilePage.setViewportSize(MOBILE_CONTEXTS.compact);
  const mobileToastClose = mobilePage.getByRole('button', {
    name: 'Закрыть сообщение',
    exact: true,
  });
  if (await mobileToastClose.isVisible()) await mobileToastClose.click();
  await savedMobileRow.scrollIntoViewIfNeeded();
  await mobilePage.screenshot({
    path: '../.artifacts/screenshots/task-66/mobile-web-360x800-light-cardio-saved.png',
  });

  await mobilePage.setViewportSize({ width: 1440, height: 900 });
  await mobilePage.goto('/app?section=progress');
  const history = mobilePage.locator('#progress-cardio');
  await history.scrollIntoViewIfNeeded();
  await expect(history.getByText('1 завершено')).toBeVisible();
  await expect(history).toContainText('25 мин');
  await mobilePage.screenshot({
    path: '../.artifacts/screenshots/task-66/desktop-1440x900-light-cardio-history.png',
  });
});

test('notification center keeps Mobile Web/TMA parity, unread geometry and an explicit return path', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  await installPlatformApi(tmaPage, { notificationState: 'populated' });
  await installPlatformApi(mobilePage, {
    browserSession: true,
    notificationState: 'populated',
  });
  await Promise.all([
    tmaPage.goto('/app?section=profile#profile-notifications'),
    mobilePage.goto('/app?section=profile#profile-notifications'),
  ]);

  for (const page of [tmaPage, mobilePage]) {
    await expect(page.getByRole('heading', { name: 'Каналы' })).toBeVisible();
    const notificationCenter = page.locator('details.notification-center');
    await expect(notificationCenter.locator(':scope > summary')).toContainText('Непрочитанные · 2');
    await notificationCenter.locator(':scope > summary').click();
    await expect(page.getByRole('heading', { name: 'Непрочитанные · 2' })).toBeVisible();
    await expect(page.getByText('Комментарий тренера к тренировке')).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await expectTouchTargets(page.locator('.notification-settings .switch-row'));
    await expectTouchTargets(page.locator('.notification-row button:visible'));
    const unreadNotification = notificationArticle(page, 'Комментарий тренера к тренировке');
    await expect(unreadNotification).toHaveCount(1);
    await expectLimeStartBoundary(unreadNotification);
    await expect(page.getByRole('button', { name: 'Отметить всё' })).toHaveCSS(
      'border-top-style',
      'solid',
    );
    const unreadDeleteButton = unreadNotification.getByRole('button', {
      name: 'Удалить',
      exact: true,
    });
    await expect(unreadDeleteButton).toHaveCount(1);
    await expect(unreadDeleteButton).toHaveCSS('border-top-style', 'solid');
    const readNotification = notificationArticle(page, 'Пора обновить замеры');
    await expect(readNotification).toHaveCount(1);
    const [readRow, personal] = await Promise.all([
      readNotification.boundingBox(),
      page.locator('.notification-personal').boundingBox(),
    ]);
    expect(readRow).not.toBeNull();
    expect(personal).not.toBeNull();
    expect(personal!.y - (readRow!.y + readRow!.height)).toBeLessThanOrEqual(20);
  }

  const signature = (page: typeof tmaPage) =>
    page.locator('#profile-notifications').evaluate((section) => ({
      headings: Array.from(section.querySelectorAll('h2, h3')).map((node) => node.textContent),
      switches: section.querySelectorAll('input[type="checkbox"]').length,
      rows: section.querySelectorAll('.notification-row').length,
    }));
  expect(await signature(tmaPage)).toEqual(await signature(mobilePage));

  await tma.setTheme('dark');
  await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(tmaPage.getByRole('heading', { name: 'Непрочитанные · 2' })).toBeVisible();

  await tmaPage.getByRole('button', { name: 'Открыть: Комментарий тренера к тренировке' }).click();
  await expect(tmaPage).toHaveURL(/workout_id=43&comment_id=91/);
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(true);
  await tma.clickBack();
  await expect(tmaPage).toHaveURL('/app?section=profile#profile-notifications');
  await expect(tmaPage.locator('details.notification-center > summary')).toContainText(
    'Всё прочитано',
  );
});

test('program history keeps current block, readable revisions and workout return in Mobile Web/TMA parity', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  await installPlatformApi(tmaPage, { programHistory: 'many' });
  await installPlatformApi(mobilePage, { browserSession: true, programHistory: 'many' });
  await Promise.all([
    tmaPage.goto('/app?section=programs'),
    mobilePage.goto('/app?section=programs'),
  ]);

  for (const page of [tmaPage, mobilePage]) {
    const history = page.locator('.program-history');
    await expect(history.getByText('Текущий тренировочный блок')).toBeVisible();
    await expect(
      history.getByRole('heading', {
        name: 'Устойчивый рабочий объём с постепенным усложнением основных движений без потери техники',
      }),
    ).toBeVisible();
    await expect(history.locator('.program-current-block__note')).toContainText(
      'Тренер скорректировал цель',
    );
    await history.getByText('Все этапы и изменения').click();
    await expect(history.getByRole('heading', { name: 'Тренировочные блоки' })).toBeVisible();
    const blockTimeline = history.locator('.program-block-timeline');
    await expect(blockTimeline.getByText('Вводный этап')).toBeVisible();
    await expect(
      blockTimeline.getByText('Облегчённая неделя перед следующим рабочим циклом'),
    ).toBeVisible();

    const revision = history.locator('#program-revision-77-4');
    await revision.locator('summary').click();
    await expect(revision.getByText(/Пользователь уверенно выполняет план/)).toBeVisible();
    await expect(
      revision.getByText('Сохранять рабочий объём без изменения сложности.'),
    ).toBeVisible();
    await expect(
      revision.getByText(
        'Увеличить рабочий объём, сохраняя стабильную технику и понятный запас повторов в каждом подходе.',
      ),
    ).toBeVisible();
    await expect(revision.getByRole('link', { name: /Контекст версии/ })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  }
  expect(await sharedSurfaceSignature(tmaPage)).toEqual(await sharedSurfaceSignature(mobilePage));

  for (const viewport of Object.values(MOBILE_CONTEXTS)) {
    await tmaPage.setViewportSize(viewport);
    await tma.setViewport(viewport.height, viewport.height);
    await expectNoHorizontalOverflow(tmaPage);
    await expectTouchTargets(tmaPage.locator('.program-history summary:visible'));
  }

  const tmaWorkoutLink = tmaPage
    .locator('#program-revision-77-4')
    .getByRole('link', { name: /Контекст версии/ });
  await tmaWorkoutLink.click();
  await expect(tmaPage).toHaveURL(
    /section=progress&workout_id=943&program_history=77&program_revision=4&return_to=/,
  );
  await expect(tmaPage.getByRole('link', { name: 'К истории программы' })).toBeVisible();
  await expect(tmaPage.getByRole('heading', { name: 'Контекст версии' })).toBeVisible();
  await expect(tmaPage.getByText('4 подх. · 6–8 повт. · отдых 120 сек.')).toBeVisible();
  await expect(tmaPage.getByText(/доступен только для просмотра/)).toBeVisible();
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(true);
  await tma.clickBack();
  await expect(tmaPage).toHaveURL('/app?section=programs&program_history=77&program_revision=4');
  await expect(tmaPage.locator('.program-history__disclosure')).toHaveJSProperty('open', true);
  await expect(tmaPage.locator('#program-revision-77-4')).toHaveJSProperty('open', true);
  await expect(tmaPage.locator('#program-revision-77-4 > summary')).toBeFocused();
  await expect(tmaPage.locator('#program-revision-77-4 > summary')).not.toHaveAttribute('tabindex');

  const olderRevision = tmaPage.locator('#program-revision-77-3');
  await olderRevision.locator('summary').click();
  await olderRevision.getByRole('link', { name: /Контекст версии/ }).click();
  await expect(tmaPage).toHaveURL(/program_revision=3/);
  await expect(tmaPage.getByText('3 подх. · 8–10 повт. · отдых 90 сек.')).toBeVisible();
  await expect(tmaPage.getByText('4 подх. · 6–8 повт. · отдых 120 сек.')).not.toBeAttached();
  await tma.clickBack();
  await expect(tmaPage).toHaveURL('/app?section=programs&program_history=77&program_revision=3');
  await expect(tmaPage.locator('#program-revision-77-3')).toHaveJSProperty('open', true);

  await mobilePage
    .locator('#program-revision-77-4')
    .getByRole('link', { name: /Контекст версии/ })
    .click();
  await expect(mobilePage.getByText('4 подх. · 6–8 повт. · отдых 120 сек.')).toBeVisible();
  await mobilePage.getByRole('link', { name: 'К истории программы' }).click();
  await expect(mobilePage).toHaveURL('/app?section=programs&program_history=77&program_revision=4');
  await expect(mobilePage.locator('#program-revision-77-4')).toHaveJSProperty('open', true);
});

test('program history renders empty, one-block and full lifecycle states honestly', async ({
  browser,
}) => {
  for (const state of ['empty', 'one', 'many'] as const) {
    const page = await browser.newPage({ viewport: MOBILE_CONTEXTS.baseline });
    await installPlatformApi(page, { browserSession: true, programHistory: state });
    await page.goto('/app?section=programs');
    const history = page.locator('.program-history');

    if (state === 'empty') {
      await expect(history.getByText('Тренировочные блоки ещё не настроены')).toBeVisible();
    } else {
      await expect(history.getByText('Текущий тренировочный блок')).toBeVisible();
    }
    await history.getByText('Все этапы и изменения').click();
    if (state === 'empty') {
      await expect(
        history.getByText('История появится после первого сохранённого изменения'),
      ).toBeVisible();
    } else if (state === 'one') {
      await expect(history.locator('.program-block-timeline > li')).toHaveCount(1);
      await expect(history.locator('.program-revision-timeline > li')).toHaveCount(2);
    } else {
      const timeline = history.locator('.program-block-timeline');
      await expect(timeline.locator(':scope > li')).toHaveCount(4);
      await expect(timeline.getByText('В архиве')).toBeVisible();
      await expect(timeline.getByText('Идёт сейчас')).toBeVisible();
      await expect(timeline.getByText('Запланирован')).toBeVisible();
    }
    await expectNoHorizontalOverflow(page);
    await page.close();
  }
});

test('simple program builder stays lightweight across Mobile Web, mocked TMA and desktop', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  await Promise.all([
    tmaPage.emulateMedia({ reducedMotion: 'reduce' }),
    mobilePage.emulateMedia({ reducedMotion: 'reduce' }),
  ]);
  await installPlatformApi(tmaPage, { programHistory: 'many' });
  await installPlatformApi(mobilePage, { browserSession: true, programHistory: 'many' });
  await Promise.all([
    tmaPage.goto('/app?section=programs'),
    mobilePage.goto('/app?section=programs'),
  ]);

  for (const page of [tmaPage, mobilePage]) {
    const builder = page.locator('#program-builder');
    await expect(builder.getByRole('heading', { name: 'Создать свою программу' })).toBeVisible();
    await expect(builder.getByLabel('Название', { exact: true })).toHaveValue('Моя программа');
    await expect(builder.getByLabel('Название дня 1')).toHaveValue('Тренировка 1');
    await expect(builder.getByRole('combobox', { name: 'Цель', exact: true })).toBeHidden();
    await expect(builder.getByRole('button', { name: 'Добавить упражнение' })).toBeVisible();
    await expect(builder.getByRole('button', { name: 'Создать программу' })).toBeVisible();
    expect(
      await page
        .locator('#program-builder, #program-library')
        .evaluateAll((elements) => elements.map((element) => element.id)),
    ).toEqual(['program-builder', 'program-library']);
  }

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
  ]) {
    await tmaPage.setViewportSize(viewport);
    await tma.setViewport(viewport.height, viewport.height);
    await mobilePage.setViewportSize(viewport);
    await expectNoHorizontalOverflow(tmaPage);
    await expectNoHorizontalOverflow(mobilePage);
    await expectTouchTargets(tmaPage.locator('#program-builder summary:visible'));
    await expectTouchTargets(mobilePage.locator('#program-builder summary:visible'));
    await expectTouchTargets(tmaPage.locator('#program-builder button:visible'));
    await expectTouchTargets(mobilePage.locator('#program-builder button:visible'));
  }

  await mobilePage.setViewportSize({ width: 390, height: 844 });
  await mobilePage.screenshot({
    path: '../.artifacts/screenshots/task-118/mobile-web-390x844-light.png',
    fullPage: true,
  });
  const mobileSearch = mobilePage
    .locator('#program-builder')
    .getByRole('combobox', { name: 'Поиск упражнения' });
  await mobileSearch.fill('Тяга');
  await expect(mobilePage.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
  await expect(mobilePage.locator('#appBottomNav')).toBeHidden();
  await mobileSearch.evaluate((element) => element.blur());
  await expect(mobilePage.locator('html')).toHaveAttribute('data-yfc-keyboard', 'hidden');
  await expect(mobileSearch).toHaveValue('Тяга');
  await mobileSearch.fill('');
  await mobileSearch.evaluate((element) => element.blur());

  await tma.setTheme('dark');
  await tmaPage.setViewportSize({ width: 430, height: 932 });
  await tma.setViewport(932, 932);
  await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-118/mocked-tma-430x932-dark.png',
    fullPage: true,
  });

  await mobilePage.setViewportSize({ width: 1280, height: 900 });
  await expectNoHorizontalOverflow(mobilePage);
  await mobilePage.screenshot({
    path: '../.artifacts/screenshots/task-118/desktop-1280x900-light.png',
    fullPage: true,
  });
});

test('program history visual evidence covers compact Mobile Web, dark TMA and desktop', async ({
  browser,
}) => {
  const cases = [
    {
      surface: 'mobile-web',
      viewport: MOBILE_CONTEXTS.compact,
      theme: 'light' as const,
      telegram: false,
      screenshot: true,
    },
    {
      surface: 'tma',
      viewport: MOBILE_CONTEXTS.baseline,
      theme: 'dark' as const,
      telegram: true,
      screenshot: true,
    },
    {
      surface: 'mobile-web',
      viewport: MOBILE_CONTEXTS.large,
      theme: 'light' as const,
      telegram: false,
      screenshot: false,
    },
    {
      surface: 'tablet',
      viewport: { width: 768, height: 900 },
      theme: 'light' as const,
      telegram: false,
      screenshot: false,
    },
    {
      surface: 'desktop',
      viewport: { width: 1280, height: 900 },
      theme: 'light' as const,
      telegram: false,
      screenshot: true,
    },
  ];

  for (const current of cases) {
    const page = await browser.newPage({
      viewport: current.viewport,
      hasTouch: current.telegram,
      reducedMotion: 'reduce',
    });
    if (current.telegram) {
      await installTelegramHarness(page, { colorScheme: current.theme });
    } else {
      await page.addInitScript((theme) => localStorage.setItem('app-theme', theme), current.theme);
    }
    await installPlatformApi(page, {
      browserSession: !current.telegram,
      programHistory: 'many',
    });
    await page.goto('/app?section=programs');
    const program = page.locator('.program-active');
    const history = program.locator('.program-history');
    await expect(history.getByText('Текущий тренировочный блок')).toBeVisible();
    await waitForVisualStability(page);
    if (current.screenshot) {
      await history
        .locator('.program-current-block')
        .evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await page.screenshot({
        path: `../.artifacts/screenshots/task-59/${current.surface}-${current.viewport.width}x${current.viewport.height}-${current.theme}-current-viewport.png`,
      });
      await page.locator('#appBottomNav').evaluate((element) => {
        element.style.visibility = 'hidden';
      });
      await history.locator('.program-current-block').screenshot({
        path: `../.artifacts/screenshots/task-59/${current.surface}-${current.viewport.width}x${current.viewport.height}-${current.theme}-current-block.png`,
      });
      await page.locator('#appBottomNav').evaluate((element) => {
        element.style.visibility = '';
      });
    }
    if (current.viewport.width < 900) {
      const lastCurrentAction = history.getByRole('button', { name: 'В архив' });
      await expect
        .poll(async () => {
          const [actionBox, dockBox] = await Promise.all([
            lastCurrentAction.boundingBox(),
            page.locator('#appBottomNav').boundingBox(),
          ]);
          if (!actionBox || !dockBox) return false;
          const overlap = actionBox.y + actionBox.height - dockBox.y;
          if (overlap >= 0) {
            await page.evaluate((distance) => window.scrollBy(0, distance), overlap + 16);
            return false;
          }
          return true;
        })
        .toBe(true);
      await expect(lastCurrentAction).toBeInViewport();
      await expectNoOverlap(lastCurrentAction, page.locator('#appBottomNav'));
    }
    await history.getByText('Все этапы и изменения').click();
    await history.locator('#program-revision-77-4 > summary').click();
    await expect(history.locator('#program-revision-77-4')).toHaveJSProperty('open', true);
    await waitForVisualStability(page);
    if (current.screenshot) {
      await history
        .locator('.program-current-block')
        .evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await page.screenshot({
        path: `../.artifacts/screenshots/task-59/${current.surface}-${current.viewport.width}x${current.viewport.height}-${current.theme}-current-viewport.png`,
      });
    }
    await expectNoHorizontalOverflow(page);
    await expectTouchTargets(history.locator('summary:visible'));
    await expectNoOverlap(
      history.locator('.program-current-block'),
      history.locator('.program-history__disclosure > summary'),
    );

    const brandContract = await history.evaluate((element) => {
      const rootStyle = getComputedStyle(document.documentElement);
      const colorSample = document.createElement('span');
      colorSample.style.color = 'var(--v2-lime)';
      const onLimeSample = document.createElement('span');
      onLimeSample.style.color = 'var(--v2-on-lime)';
      element.append(colorSample);
      element.append(onLimeSample);
      const lime = getComputedStyle(colorSample).color;
      const onLime = getComputedStyle(onLimeSample).color;
      colorSample.remove();
      onLimeSample.remove();
      const radius = rootStyle.getPropertyValue('--radius-action').trim();
      const currentBlock = element.querySelector<HTMLElement>('.program-current-block');
      const action = element.querySelector<HTMLElement>('.program-block-actions .ui-button');
      const editAction = element
        .closest('.program-active')
        ?.querySelector<HTMLElement>('.program-active__edit-action');
      const disclosure = element.querySelector<HTMLElement>('.disclosure-icon');
      const disclosureRect = disclosure?.getBoundingClientRect();
      return {
        lime,
        onLime,
        radius,
        boundaryShadow: currentBlock ? getComputedStyle(currentBlock).boxShadow : null,
        actionRadius: action ? getComputedStyle(action).borderRadius : null,
        editActionBackground: editAction ? getComputedStyle(editAction).backgroundColor : null,
        editActionColor: editAction ? getComputedStyle(editAction).color : null,
        disclosure: disclosureRect
          ? { width: disclosureRect.width, height: disclosureRect.height }
          : null,
      };
    });
    expect(brandContract.boundaryShadow).toContain(brandContract.lime);
    expect(brandContract.actionRadius).toBe(brandContract.radius);
    expect(brandContract.editActionBackground).toBe(brandContract.lime);
    expect(brandContract.editActionColor).toBe(brandContract.onLime);
    expect(brandContract.disclosure).toEqual({ width: 28, height: 28 });

    if (current.screenshot) {
      await history
        .locator('#program-revision-77-4')
        .evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await page.screenshot({
        path: `../.artifacts/screenshots/task-59/${current.surface}-${current.viewport.width}x${current.viewport.height}-${current.theme}-revision-v4-viewport.png`,
      });
      await page.locator('#appBottomNav').evaluate((element) => {
        element.style.visibility = 'hidden';
      });
      await history.locator('#program-revision-77-4').screenshot({
        path: `../.artifacts/screenshots/task-59/${current.surface}-${current.viewport.width}x${current.viewport.height}-${current.theme}-revision-v4.png`,
      });
      await page.locator('#appBottomNav').evaluate((element) => {
        element.style.visibility = '';
      });
      await program.screenshot({
        path: `../.artifacts/screenshots/task-59/${current.surface}-${current.viewport.width}x${current.viewport.height}-${current.theme}-history.png`,
      });
      await history
        .locator('#program-revision-77-4')
        .getByRole('link', { name: /Контекст версии/ })
        .click();
      const historicalWorkout = page.locator('.program-history-workout');
      await expect(
        historicalWorkout.getByRole('heading', { name: 'Контекст версии' }),
      ).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await page.locator('#appBottomNav').evaluate((element) => {
        element.style.visibility = 'hidden';
      });
      await historicalWorkout.screenshot({
        path: `../.artifacts/screenshots/task-59/${current.surface}-${current.viewport.width}x${current.viewport.height}-${current.theme}-historical-workout-v4.png`,
      });
    }
    await page.close();
  }
});

test('nutrition report keeps period analytics and diary return aligned in Mobile Web and TMA', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  const tmaApi = await installPlatformApi(tmaPage);
  const mobileApi = await installPlatformApi(mobilePage, { browserSession: true });
  await Promise.all([
    tmaPage.goto('/app?section=progress&progress_period=days_7'),
    mobilePage.goto('/app?section=progress&progress_period=days_7'),
  ]);

  for (const currentPage of [tmaPage, mobilePage]) {
    const report = currentPage.locator('#nutrition-period-report');
    await expect(report.getByRole('heading', { name: 'Отчёт по питанию' })).toBeVisible();
    await expect(report.getByText('Заполнено 3 из 7 дней')).toBeVisible();
    await expect(report.getByText('Изменения цели в периоде')).toBeVisible();
    await expect(
      report.getByRole('table', {
        name: 'Дневные КБЖУ, статус заполнения и действовавшая цель',
      }),
    ).toBeVisible();
  }
  expect(await sharedSurfaceSignature(tmaPage)).toEqual(await sharedSurfaceSignature(mobilePage));

  const tmaReport = tmaPage.locator('#nutrition-period-report');
  const tmaSelector = tmaPage.getByRole('tablist', { name: 'Период прогресса' });
  const mobileSelector = mobilePage.getByRole('tablist', { name: 'Период прогресса' });
  for (const period of ['30 дней', '90 дней', '7 дней']) {
    await Promise.all([
      tmaSelector.getByRole('tab', { name: period }).click(),
      mobileSelector.getByRole('tab', { name: period }).click(),
    ]);
  }
  await expect
    .poll(() => tmaApi.nutritionReportPeriods())
    .toEqual(expect.arrayContaining(['days_7', 'days_30', 'days_90']));
  await expect
    .poll(() => mobileApi.nutritionReportPeriods())
    .toEqual(expect.arrayContaining(['days_7', 'days_30', 'days_90']));

  for (const viewport of Object.values(MOBILE_CONTEXTS)) {
    await tmaPage.setViewportSize(viewport);
    await tma.setViewport(viewport.height, viewport.height);
    await expectNoHorizontalOverflow(tmaPage);
    await expectTouchTargets(tmaSelector.getByRole('tab'));
  }
  const diaryLink = tmaReport.getByRole('row').filter({ hasText: '· сегодня' }).getByRole('link');
  await expect(diaryLink).toHaveCount(1);
  await diaryLink.scrollIntoViewIfNeeded();
  await expectNoOverlap(diaryLink, tmaPage.locator('#appBottomNav'));

  await tmaPage.setViewportSize({ width: 390, height: 844 });
  await tma.setViewport(844, 844);
  await tma.setTheme('dark');
  await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect
    .poll(() =>
      tmaReport
        .locator('.data-viz-chart__point-ring')
        .first()
        .evaluate((point) => {
          const style = getComputedStyle(point);
          return {
            fill: style.fill,
            stroke: style.stroke,
            theme: document.documentElement.dataset.colorScheme,
          };
        }),
    )
    .toEqual({
      fill: 'rgb(20, 23, 23)',
      stroke: 'rgb(178, 245, 32)',
      theme: 'dark',
    });
  await tmaReport.evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-57/tma-390x844-dark-compact.png',
  });
  await tmaReport.screenshot({
    path: '../.artifacts/screenshots/task-57/tma-390x844-dark-partial.png',
  });
  await tmaReport.locator('.data-viz-chart').screenshot({
    path: '../.artifacts/screenshots/task-57/tma-390x844-dark-chart.png',
  });

  await diaryLink.click();
  await expect(tmaPage).toHaveURL(/section=nutrition&date=.*return_to=/);
  await expect(tmaPage.getByRole('heading', { name: 'Питание', exact: true })).toBeVisible();
  await tmaPage.getByRole('link', { name: 'К отчёту по питанию' }).click();
  await expect(tmaPage).toHaveURL(/section=progress&progress_period=days_7/);
  await expect(tmaSelector.getByRole('tab', { name: '7 дней' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
});

test('measurement add, edit, history and insufficient trend keep Mobile Web and TMA parity', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  const tmaApi = await installPlatformApi(tmaPage);
  await installPlatformApi(mobilePage, { browserSession: true });
  await Promise.all([
    tmaPage.goto('/app?section=progress'),
    mobilePage.goto('/app?section=progress'),
  ]);

  for (const currentPage of [tmaPage, mobilePage]) {
    const body = currentPage.locator('#progress-body');
    await expect(body.getByText('Сбалансированное развитие')).toBeVisible();
    await expect(body.getByText('Замеров за этот период нет')).toBeVisible();
    await expect(body.getByText('Замеров пока нет')).toBeVisible();
    await expect(body.getByLabel('Вес, кг')).toHaveAttribute('inputmode', 'decimal');
    await body.getByLabel('Вес, кг').fill('74.2');
    await body.getByLabel('Плечо (окружность), см').fill('31.6');
  }
  expect(await sharedSurfaceSignature(tmaPage)).toEqual(await sharedSurfaceSignature(mobilePage));

  const tmaBody = tmaPage.locator('#progress-body');
  await tmaBody.getByLabel('Вес, кг').focus();
  await expect(tmaPage.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
  await expect(tmaPage.locator('#appBottomNav')).toBeHidden();
  await expect(tmaBody.locator('.measurement-diary__save-dock')).toHaveCSS('position', 'sticky');
  await tma.setTheme('dark');
  await tma.setActive(false);
  await tma.setActive(true);
  await expect(tmaBody.getByLabel('Вес, кг')).toHaveValue('74.2');
  await expect(tmaBody.getByLabel('Плечо (окружность), см')).toHaveValue('31.6');

  tmaApi.failNextMeasurementSave();
  expect(
    await tmaBody
      .locator('.measurement-diary__form :invalid')
      .evaluateAll((elements) => elements.map((element) => element.getAttribute('aria-label'))),
  ).toEqual([]);
  await tmaBody.getByRole('button', { name: 'Сохранить замер' }).click();
  await expect.poll(() => tmaApi.measurementSaveCalls()).toBe(1);
  await expect(tmaBody.getByText(/Введённые значения сохранены/)).toBeVisible();
  await expect(tmaBody.getByLabel('Вес, кг')).toHaveValue('74.2');
  await tmaBody.getByRole('button', { name: 'Сохранить замер' }).click();
  await expect.poll(() => tmaApi.measurementSaveCalls()).toBe(2);

  const mobileBody = mobilePage.locator('#progress-body');
  await mobileBody.getByRole('button', { name: 'Сохранить замер' }).click();

  for (const currentPage of [tmaPage, mobilePage]) {
    const body = currentPage.locator('#progress-body');
    await expect(body.getByText(/Вес: 74\.2 кг · Окружность плеча: 31\.6 см/)).toBeVisible();
    const singlePointHints = body.getByText(
      'Одна точка сохраняет факт, но ещё не показывает направление изменений.',
    );
    await expect(singlePointHints).toHaveCount(2);
    for (const hint of await singlePointHints.all()) await expect(hint).toBeVisible();
    const noTrendStates = body.getByText('Пока без динамики', { exact: true });
    await expect(noTrendStates).toHaveCount(2);
    for (const state of await noTrendStates.all()) await expect(state).toBeVisible();
    const row = body.locator('.measurement-history__row').filter({ hasText: '74.2 кг' });
    await row.getByRole('button', { name: 'Изменить' }).click();
    await body.getByLabel('Вес, кг').fill('74.6');
    await body.getByRole('button', { name: 'Сохранить изменения' }).click();
    await expect(body.getByText(/Вес: 74\.6 кг · Окружность плеча: 31\.6 см/)).toBeVisible();
    await expectNoHorizontalOverflow(currentPage);
    await expectTouchTargets(body.locator('.measurement-history__actions .ui-button'));
  }

  for (const viewport of Object.values(MOBILE_CONTEXTS)) {
    await tmaPage.setViewportSize(viewport);
    await tma.setViewport(viewport.height, viewport.height);
    await expectNoHorizontalOverflow(tmaPage);
    const save = tmaBody.getByRole('button', { name: 'Сохранить замер' });
    await save.scrollIntoViewIfNeeded();
    await expectNoOverlap(save, tmaPage.locator('#appBottomNav'));
  }

  await tmaPage.setViewportSize({ width: 390, height: 844 });
  await tma.setViewport(844, 844);
  const toastClose = tmaPage.getByRole('button', { name: 'Закрыть сообщение' });
  if (await toastClose.isVisible()) await toastClose.click();
  const editedRow = tmaBody.locator('.measurement-history__row').filter({ hasText: '74.6 кг' });
  await editedRow.evaluate((element) => element.scrollIntoView({ block: 'center' }));
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-60/tma-390x844-dark.png',
  });
});

test('data confidence keeps insufficient analytics explicit in Mobile Web and dark TMA', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  await installPlatformApi(tmaPage, {
    workoutStatus: 'none',
    weeklyReviewAvailable: true,
    weeklyCalibration: 'pending',
  });
  await installPlatformApi(mobilePage, {
    browserSession: true,
    workoutStatus: 'none',
    weeklyReviewAvailable: true,
    weeklyCalibration: 'pending',
  });
  await Promise.all([
    tmaPage.goto('/app?section=progress'),
    mobilePage.goto('/app?section=progress'),
  ]);

  for (const page of [tmaPage, mobilePage]) {
    const insufficient = page
      .getByRole('region', { name: 'Достаточно ли данных: Пока мало данных', exact: true })
      .filter({ hasText: '0 рабочих подходов' });
    await expect(insufficient).toHaveCount(1);
    await expect(insufficient).toBeVisible();
    await expect(insufficient).toContainText('0 рабочих подходов');
    await expect(page.getByRole('link', { name: 'Открыть тренировку' })).toBeVisible();
    await expectLimeStartBoundary(insufficient);
    await expectNoHorizontalOverflow(page);
    await expectTouchTargets(page.locator('#progress-body details > summary:visible'));
  }
  expect(await sharedSurfaceSignature(tmaPage)).toEqual(await sharedSurfaceSignature(mobilePage));

  await tma.setTheme('dark');
  for (const viewport of Object.values(MOBILE_CONTEXTS)) {
    await tmaPage.setViewportSize(viewport);
    await tma.setViewport(viewport.height, viewport.height);
    await expectNoHorizontalOverflow(tmaPage);
  }
  await tmaPage.setViewportSize(MOBILE_CONTEXTS.baseline);
  await tma.setViewport(MOBILE_CONTEXTS.baseline.height, MOBILE_CONTEXTS.baseline.height);
  const bodyConfidence = tmaPage
    .locator('#progress-body')
    .getByRole('region', { name: 'Достаточно ли данных: Пока мало данных', exact: true })
    .filter({ hasText: 'Сейчас есть 0 замеров' });
  await expect(bodyConfidence).toHaveCount(1);
  await bodyConfidence.scrollIntoViewIfNeeded();
  await expectNoOverlap(bodyConfidence, tmaPage.locator('#appBottomNav'));
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-61/tma-390x844-dark-insufficient.png',
  });

  await tmaPage.goto('/app?section=progress&weekly_review=1');
  await tmaPage.getByRole('button', { name: 'Всё верно, продолжить' }).click();
  await tmaPage.getByRole('button', { name: 'Пропустить вопросы' }).click();
  await tma.setTheme('dark');
  await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  const decisionConfidence = tmaPage.locator('.weekly-review__calibration .data-confidence');
  await expect(decisionConfidence).toContainText('Данных достаточно для оценки');
  await expect(decisionConfidence).toContainText('24 из 28 завершённых дней');
  const primaryDecision = tmaPage.getByRole('button', { name: 'Принять новую цель' });
  await primaryDecision.scrollIntoViewIfNeeded();
  await expectNoOverlap(primaryDecision, tmaPage.locator('#appBottomNav'));
  await tmaPage.locator('.weekly-review__calibration').screenshot({
    path: '../.artifacts/screenshots/task-61/tma-390x844-dark-decision.png',
  });
});

test('data confidence keeps limited and stale transitions explicit in TMA', async ({
  tma,
  tmaPage,
}) => {
  await installPlatformApi(tmaPage, {
    workoutStatus: 'completed',
    weeklyReviewAvailable: true,
    weeklyCalibration: 'pending',
  });

  let releaseRefresh!: () => void;
  let markRefreshStarted!: () => void;
  const refreshGate = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });
  const refreshStarted = new Promise<void>((resolve) => {
    markRefreshStarted = resolve;
  });
  await tmaPage.route('**/workouts/progress/training-analytics?period_days=7', async (route) => {
    markRefreshStarted();
    await refreshGate;
    await route.fallback();
  });

  await tmaPage.goto('/app?section=progress');
  await tma.setTheme('dark');
  await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  const training = tmaPage.locator('#progress-training');
  const limited = training.getByLabel('Достаточно ли данных: Вывод пока предварительный');
  await expect(limited).toBeVisible();
  await expect(limited).toContainText('1 рабочий подход в 1 тренировке');
  await expect(training.getByRole('link', { name: 'Открыть тренировку' })).toBeVisible();
  await expectLimeStartBoundary(limited);
  await expectNoHorizontalOverflow(tmaPage);
  await expectTouchTargets(limited.locator('.data-confidence__details > summary'));
  await limited.screenshot({
    path: '../.artifacts/screenshots/task-61/tma-390x844-dark-limited.png',
  });

  await tmaPage.locator('.progress-hero').getByRole('tab', { name: '7 дней' }).click();
  await refreshStarted;
  const stale = training.getByLabel('Достаточно ли данных: Показана сохранённая оценка');
  await expect(stale).toBeVisible();
  await expect(stale).toContainText('Новые данные загружаются');
  await expect(training.getByRole('link', { name: 'Открыть тренировку' })).toHaveCount(0);
  await expectLimeStartBoundary(stale);
  await expectNoHorizontalOverflow(tmaPage);
  await expectNoOverlap(stale, tmaPage.locator('#appBottomNav'));
  await stale.screenshot({
    path: '../.artifacts/screenshots/task-61/tma-390x844-dark-stale.png',
  });

  releaseRefresh();
  await expect(stale).toHaveCount(0);
  await expect(limited).toBeVisible();
  await expect(training.getByRole('link', { name: 'Открыть тренировку' })).toBeVisible();
});

test('weekly review focus exposes a predictable TMA BackButton return path', async ({
  tma,
  tmaPage,
}) => {
  await installPlatformApi(tmaPage, {
    workoutStatus: 'none',
    weeklyReviewAvailable: true,
  });
  await tmaPage.goto('/app');

  await tmaPage.getByRole('link', { name: 'Пройти короткую проверку' }).click();
  await expect(tmaPage).toHaveURL('/app?section=progress&weekly_review=1');
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(true);

  await tmaPage.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await expect(tmaPage.getByRole('dialog')).toBeVisible();
  await tma.clickBack();
  await expect(tmaPage.getByRole('dialog')).not.toBeAttached();
  await expect(tmaPage).toHaveURL('/app?section=progress&weekly_review=1');
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(true);

  await tma.clickBack();
  await expect(tmaPage).toHaveURL('/app');
  await expect(tmaPage.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(false);
});

test('direct Trainer activation keeps client context focused in mocked TMA', async ({
  tma,
  tmaPage,
}) => {
  const api = await installPlatformApi(tmaPage);
  await tmaPage.goto('/app?section=profile');

  await tmaPage.getByRole('heading', { name: 'Тренер и приглашения' }).click();
  await tmaPage.getByText('Режим тренера', { exact: true }).click();
  await tmaPage
    .getByRole('checkbox', { name: /Принимаю условия использования режима тренера/ })
    .check();
  await tmaPage.getByRole('button', { name: 'Включить режим тренера' }).click();
  const trainerToast = tmaPage.getByRole('status').filter({ hasText: 'Режим тренера включён' });
  await expect(trainerToast).toHaveCount(1);
  await expect(trainerToast).toBeVisible();
  expect(api.trainerActivationCalls()).toBe(1);

  await tmaPage.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await tmaPage.getByRole('link', { name: 'Кабинет тренера' }).click();
  await expect(tmaPage).toHaveURL('/coach');
  await expect(tmaPage.getByRole('heading', { name: 'Кабинет тренера' })).toBeVisible();
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(true);

  await tmaPage.getByRole('button', { name: /Анна Петрова/ }).click();
  await expect(tmaPage.getByRole('heading', { name: 'Анна Петрова', exact: true })).toBeVisible();
  await expect(tmaPage.getByText('Сейчас открыт клиент')).toBeVisible();
  await tma.setTheme('dark');
  await tma.setActive(false);
  await tma.setActive(true);
  await expect(tmaPage.getByRole('heading', { name: 'Анна Петрова', exact: true })).toBeVisible();
  await expectNoHorizontalOverflow(tmaPage);
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-72/mock-tma-390x844-dark-trainer-client.png',
  });

  await tma.clickBack();
  await expect(tmaPage).toHaveURL('/coach');
  await expect(tmaPage.getByRole('heading', { name: 'Анна Петрова', exact: true })).toBeHidden();
  await expect(tmaPage.getByLabel('Найти клиента')).toBeVisible();
  await tma.clickBack();
  await expect(tmaPage).toHaveURL('/app');
});

test('workout adaptation keeps preview, cancel, apply and conflict recovery in Mobile Web/TMA parity', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  const mobileApi = await installPlatformApi(mobilePage, {
    browserSession: true,
    workoutStatus: 'planned',
  });
  const tmaApi = await installPlatformApi(tmaPage, { workoutStatus: 'planned' });
  await Promise.all([mobilePage.goto('/app'), tmaPage.goto('/app')]);

  await expect(mobilePage.getByRole('dialog', { name: 'Подстроить тренировку' })).toHaveCount(0);
  await expect(tmaPage.getByRole('dialog', { name: 'Подстроить тренировку' })).toHaveCount(0);
  expect(mobileApi.adaptationApplyCalls()).toBe(0);
  expect(tmaApi.adaptationApplyCalls()).toBe(0);
  await expect(mobilePage.getByRole('button', { name: 'Адаптировать тренировку' })).toBeVisible();
  await expect(tmaPage.getByRole('button', { name: 'Адаптировать тренировку' })).toBeVisible();

  await mobilePage.setViewportSize({ width: 1440, height: 900 });
  await mobilePage.screenshot({
    path: '../.artifacts/screenshots/task-58/desktop-1440-light-entry.png',
    fullPage: true,
  });
  await mobilePage.setViewportSize(MOBILE_CONTEXTS.baseline);

  for (const page of [mobilePage, tmaPage]) {
    await page.getByRole('button', { name: 'Адаптировать тренировку' }).click();
    await page.getByRole('button', { name: '20 мин' }).click();
    await page.getByRole('button', { name: 'Показать изменения' }).click();
    await expect(page.getByRole('heading', { name: 'Что изменится' })).toBeVisible();
    await expect(page.getByRole('list', { name: 'Сравнение тренировки' })).toContainText('56 мин');
    await expect(page.getByRole('list', { name: 'Сравнение тренировки' })).toContainText('20 мин');
  }

  const tmaRouteWithDraft = tmaPage.url();
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(true);
  await tma.clickBack();
  await expect(tmaPage.getByRole('dialog', { name: 'Подстроить тренировку' })).toHaveCount(0);
  expect(tmaPage.url()).toBe(tmaRouteWithDraft);
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(false);
  await tmaPage.getByRole('button', { name: 'Адаптировать тренировку' }).click();
  await expect(tmaPage.getByRole('button', { name: '20 мин' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(tmaPage.getByRole('button', { name: 'Применить' })).toBeVisible();
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(true);

  const dialogCopy = async (page: typeof mobilePage) =>
    page
      .getByRole('dialog', { name: 'Подстроить тренировку' })
      .locator('h2, h3, legend, .adaptation-diff__row')
      .allTextContents();
  expect(await dialogCopy(tmaPage)).toEqual(await dialogCopy(mobilePage));

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 768, height: 900 },
    { width: 1440, height: 900 },
  ]) {
    await mobilePage.setViewportSize(viewport);
    await expect.poll(() => mobilePage.evaluate(() => window.innerHeight)).toBe(viewport.height);
    await expectNoHorizontalOverflow(mobilePage);
    const panel = mobilePage.locator('.workout-adaptation-dialog__panel');
    await panel.scrollIntoViewIfNeeded();
    const box = await panel.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.y, `${viewport.width}x${viewport.height}`).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 1);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1);
    await expectTouchTargets(mobilePage.locator('.workout-adaptation-dialog button:visible'));
  }

  const apply = mobilePage.getByRole('button', { name: 'Применить' });
  await expect(mobilePage.locator('.workout-adaptation-dialog__panel')).toHaveCSS(
    'border-radius',
    '24px',
  );
  await expect(apply).toHaveCSS('background-color', 'rgb(178, 245, 32)');
  await expect(apply).toHaveCSS('border-radius', '14px');
  await expect(mobilePage.getByRole('button', { name: '20 мин' })).toHaveCSS(
    'border-top-color',
    'rgb(178, 245, 32)',
  );
  await mobilePage.locator('.adaptation-preview').scrollIntoViewIfNeeded();
  await mobilePage.screenshot({
    path: '../.artifacts/screenshots/task-58/desktop-1440-light-preview.png',
  });

  await mobilePage.getByRole('button', { name: 'Отмена' }).click();
  await expect(mobilePage.getByRole('dialog', { name: 'Подстроить тренировку' })).toHaveCount(0);
  expect(mobileApi.adaptationApplyCalls()).toBe(0);
  await mobilePage.getByRole('button', { name: 'Адаптировать тренировку' }).click();
  await expect(mobilePage.getByRole('button', { name: '20 мин' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(mobilePage.getByRole('button', { name: 'Применить' })).toBeVisible();
  await mobilePage.setViewportSize(MOBILE_CONTEXTS.compact);
  await mobilePage.locator('.adaptation-preview').scrollIntoViewIfNeeded();
  await mobilePage.screenshot({
    path: '../.artifacts/screenshots/task-58/mobile-360-light-restored-preview.png',
  });

  await tma.setTheme('dark');
  await tma.setActive(false);
  await tma.setActive(true);
  await expect(tmaPage.getByRole('dialog', { name: 'Подстроить тренировку' })).toBeVisible();
  await expect(tmaPage.getByRole('button', { name: '20 мин' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await tmaPage.locator('.adaptation-preview').scrollIntoViewIfNeeded();
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-58/tma-390-dark-preview.png',
  });
  await tmaPage.getByRole('button', { name: 'Применить' }).click();
  await expect(
    tmaPage.getByText('Изменения применены только к сегодняшней тренировке'),
  ).toBeVisible();
  expect(tmaApi.adaptationApplyCalls()).toBe(1);
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-58/tma-390-dark-applied.png',
    fullPage: true,
  });

  mobileApi.setAdaptationApplyMode('conflict');
  await mobilePage.getByRole('button', { name: 'Применить' }).click();
  await expect(mobilePage.getByText('Тренировка уже изменилась')).toBeVisible();
  await expect(mobilePage.getByText(/Ваш выбор сохранён/)).toBeVisible();
  await expect(mobilePage.getByRole('button', { name: '20 мин' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(mobilePage.getByRole('button', { name: 'Обновить изменения' })).toBeVisible();
  await mobilePage.setViewportSize(MOBILE_CONTEXTS.baseline);
  await mobilePage.locator('.adaptation-error').scrollIntoViewIfNeeded();
  await mobilePage.screenshot({
    path: '../.artifacts/screenshots/task-58/mobile-390-light-conflict.png',
  });

  mobileApi.setAdaptationApplyMode('error');
  await mobilePage.getByRole('button', { name: 'Обновить изменения' }).click();
  await mobilePage.getByRole('button', { name: 'Применить' }).click();
  await expect(mobilePage.getByText('Не удалось применить изменения')).toBeVisible();
  await expect(mobilePage.getByRole('button', { name: '20 мин' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  expect(mobileApi.adaptationApplyCalls()).toBe(2);
});

test('unified weekly review keeps Mobile Web/TMA parity and distinct adaptive decisions', async ({
  browser,
  mobilePage,
  tma,
  tmaPage,
}) => {
  const tmaApi = await installPlatformApi(tmaPage, {
    workoutStatus: 'none',
    weeklyReviewAvailable: true,
    weeklyCalibration: 'pending',
  });
  const mobileApi = await installPlatformApi(mobilePage, {
    browserSession: true,
    workoutStatus: 'none',
    weeklyReviewAvailable: true,
    weeklyCalibration: 'pending',
  });
  await Promise.all([
    tmaPage.goto('/app?section=progress&weekly_review=1'),
    mobilePage.goto('/app?section=progress&weekly_review=1'),
  ]);

  for (const page of [tmaPage, mobilePage]) {
    await expect(page.getByRole('heading', { name: 'Что известно приложению' })).toBeVisible();
    await expect(page.locator('#weekly-review')).toBeFocused();
    await page.getByRole('button', { name: 'Всё верно, продолжить' }).click();
    await expect(page.getByRole('heading', { name: 'Короткие уточнения' })).toBeVisible();
    await page.getByRole('button', { name: 'Пропустить вопросы' }).click();
    await expect(page.getByText('Есть предложение')).toBeVisible();
    const targetDecision = page.getByLabel('Решение по цели');
    await expect(targetDecision.getByText('2100 ккал', { exact: true })).toBeVisible();
    await expect(targetDecision.getByText('2300 ккал', { exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  }
  expect(await sharedSurfaceSignature(tmaPage)).toEqual(await sharedSurfaceSignature(mobilePage));
  for (const viewport of Object.values(MOBILE_CONTEXTS)) {
    await tmaPage.setViewportSize(viewport);
    await tma.setViewport(viewport.height, viewport.height);
    await expectNoHorizontalOverflow(tmaPage);
    await expectTouchTargets(tmaPage.locator('.weekly-review__decision button'));
  }
  const deferDecision = tmaPage.getByRole('button', { name: 'Отложить решение' });
  await deferDecision.scrollIntoViewIfNeeded();
  await expectNoOverlap(deferDecision, tmaPage.locator('#appBottomNav'));
  await tma.setActive(false);
  await tma.setActive(true);
  await expect(tmaPage.getByText('Есть предложение')).toBeVisible();

  await tmaPage.getByRole('button', { name: 'Принять новую цель' }).click();
  await mobilePage.getByRole('button', { name: 'Оставить текущую цель' }).click();
  await expect.poll(() => tmaApi.weeklyDecisionCalls()).toEqual(['accept']);
  await expect.poll(() => mobileApi.weeklyDecisionCalls()).toEqual(['reject']);
  await expect.poll(() => tmaApi.weeklyReviewSubmits()).toBe(1);
  await expect.poll(() => mobileApi.weeklyReviewSubmits()).toBe(1);

  const deferPage = await browser.newPage({ viewport: MOBILE_CONTEXTS.compact, hasTouch: true });
  const deferApi = await installPlatformApi(deferPage, {
    browserSession: true,
    weeklyReviewAvailable: true,
    weeklyCalibration: 'pending',
  });
  await deferPage.goto('/app?section=progress&weekly_review=1');
  await deferPage.getByRole('button', { name: 'Всё верно, продолжить' }).click();
  await deferPage.getByRole('button', { name: 'Пропустить вопросы' }).click();
  await deferPage.getByRole('button', { name: 'Отложить решение' }).click();
  await expect.poll(() => deferApi.weeklyDecisionCalls()).toEqual([]);
  await expect.poll(() => deferApi.weeklyReviewSubmits()).toBe(1);
  await deferPage.close();

  const insufficientPage = await browser.newPage({
    viewport: MOBILE_CONTEXTS.baseline,
    hasTouch: true,
  });
  const insufficientApi = await installPlatformApi(insufficientPage, {
    browserSession: true,
    weeklyReviewAvailable: true,
    weeklyCalibration: 'insufficient',
  });
  await insufficientPage.goto('/app?section=progress&weekly_review=1');
  await insufficientPage.getByRole('button', { name: 'Всё верно, продолжить' }).click();
  const note = insufficientPage.getByLabel('Заметка о неделе');
  await insufficientPage.setViewportSize({ width: 390, height: 560 });
  await note.focus();
  const skipQuestions = insufficientPage.getByRole('button', { name: 'Пропустить вопросы' });
  await skipQuestions.scrollIntoViewIfNeeded();
  await expectNoOverlap(skipQuestions, insufficientPage.locator('#appBottomNav'));
  await note.fill('Черновик переживает background и reload');
  await insufficientPage.reload();
  await expect(insufficientPage.getByLabel('Заметка о неделе')).toHaveValue(
    'Черновик переживает background и reload',
  );
  await skipQuestions.click();
  await expect(insufficientPage.getByText('Данных пока недостаточно')).toBeVisible();
  await insufficientPage.getByRole('button', { name: 'Завершить обзор' }).click();
  await expect.poll(() => insufficientApi.weeklyDecisionCalls()).toEqual([]);
  await expect.poll(() => insufficientApi.weeklyReviewSubmits()).toBe(1);
  await insufficientPage.close();
});

test('weekly review visual evidence covers compact Mobile Web, dark TMA and desktop', async ({
  browser,
}) => {
  const cases = [
    {
      surface: 'mobile-web',
      viewport: MOBILE_CONTEXTS.compact,
      theme: 'light' as const,
      step: 'facts' as const,
      telegram: false,
    },
    {
      surface: 'tma',
      viewport: MOBILE_CONTEXTS.baseline,
      theme: 'dark' as const,
      step: 'decision' as const,
      telegram: true,
    },
    {
      surface: 'desktop',
      viewport: { width: 1440, height: 960 },
      theme: 'light' as const,
      step: 'decision' as const,
      telegram: false,
    },
  ];

  for (const current of cases) {
    const page = await browser.newPage({ viewport: current.viewport, hasTouch: current.telegram });
    if (current.telegram) {
      await installTelegramHarness(page, { colorScheme: current.theme });
    } else {
      await page.addInitScript((theme) => localStorage.setItem('app-theme', theme), current.theme);
    }
    await installPlatformApi(page, {
      browserSession: !current.telegram,
      weeklyReviewAvailable: true,
      weeklyCalibration: 'pending',
    });
    await page.goto('/app?section=progress&weekly_review=1');
    await expect(page.getByRole('heading', { name: 'Что известно приложению' })).toBeVisible();
    if (current.step === 'decision') {
      await page.getByRole('button', { name: 'Всё верно, продолжить' }).click();
      await page.getByRole('button', { name: 'Пропустить вопросы' }).click();
      await expect(page.getByText('Есть предложение')).toBeVisible();
    }
    await expectNoHorizontalOverflow(page);

    const brandContract = await page.evaluate((step) => {
      const tokenValue = (property: 'color' | 'borderRadius', token: string) => {
        const sample = document.createElement('span');
        sample.style[property] = `var(${token})`;
        document.body.append(sample);
        const value = getComputedStyle(sample)[property];
        sample.remove();
        return value;
      };
      const primary = document.querySelector<HTMLElement>('.weekly-review__primary');
      const activeStep = document.querySelector<HTMLElement>(
        '.weekly-review__steps li[aria-current="step"]',
      );
      const boundary = document.querySelector<HTMLElement>(
        step === 'facts' ? '.weekly-review__target' : '.weekly-review__diff > div:last-child',
      );
      const decisionNote = document.querySelector<HTMLElement>('.weekly-review__decision-note');
      const disclosure = document.querySelector<HTMLElement>(
        '.weekly-review__history .disclosure-icon',
      );
      const disclosureRect = disclosure?.getBoundingClientRect();
      return {
        lime: tokenValue('color', '--v2-lime'),
        onLime: tokenValue('color', '--v2-on-lime'),
        actionRadius: tokenValue('borderRadius', '--radius-action'),
        primaryBackground: primary ? getComputedStyle(primary).backgroundColor : null,
        primaryColor: primary ? getComputedStyle(primary).color : null,
        primaryRadius: primary ? getComputedStyle(primary).borderRadius : null,
        activeStepBoundary: activeStep ? getComputedStyle(activeStep).borderBottomColor : null,
        boundaryBorder: boundary ? getComputedStyle(boundary).borderLeftColor : null,
        boundaryShadow: boundary ? getComputedStyle(boundary).boxShadow : null,
        noteBorder: decisionNote ? getComputedStyle(decisionNote).borderLeftColor : null,
        disclosure: disclosureRect
          ? {
              width: disclosureRect.width,
              height: disclosureRect.height,
              radius: getComputedStyle(disclosure!).borderRadius,
            }
          : null,
      };
    }, current.step);
    expect(brandContract.primaryBackground).toBe(brandContract.lime);
    expect(brandContract.primaryColor).toBe(brandContract.onLime);
    expect(brandContract.primaryRadius).toBe(brandContract.actionRadius);
    expect(brandContract.activeStepBoundary).toBe(brandContract.lime);
    if (current.step === 'facts') {
      expect(brandContract.boundaryBorder).toBe(brandContract.lime);
    } else {
      expect(brandContract.boundaryShadow).toContain(brandContract.lime);
      expect(brandContract.noteBorder).toBe(brandContract.lime);
    }
    expect(brandContract.disclosure).toEqual({ width: 28, height: 28, radius: '50%' });

    if (current.viewport.width >= 900) {
      const desktopPadding = await page.locator('.weekly-review-card').evaluate((card) => {
        const styles = getComputedStyle(card);
        return {
          left: styles.paddingLeft,
          right: styles.paddingRight,
          token: getComputedStyle(document.documentElement).getPropertyValue('--v2-space-4').trim(),
        };
      });
      expect(desktopPadding.left).toBe(desktopPadding.token);
      expect(desktopPadding.right).toBe(desktopPadding.token);
    }

    await page
      .locator('#weekly-review')
      .locator('..')
      .screenshot({
        path: `../.artifacts/screenshots/task-56/${current.surface}-${current.viewport.width}x${current.viewport.height}-${current.theme}-${current.step}.png`,
      });
    if (current.step === 'facts') {
      const primaryAction = page.getByRole('button', { name: 'Всё верно, продолжить' });
      await primaryAction.scrollIntoViewIfNeeded();
      await expectNoOverlap(primaryAction, page.locator('#appBottomNav'));
      const scheduleCard = page.locator('details.card').filter({
        has: page.getByRole('heading', { name: 'Расписание', exact: true }),
      });
      const weekCard = page.locator('details.card').filter({
        has: page.getByRole('heading', { name: 'Неделя', exact: true }),
      });
      const [scheduleBox, weekBox] = await Promise.all([
        scheduleCard.boundingBox(),
        weekCard.boundingBox(),
      ]);
      expect(scheduleBox).not.toBeNull();
      expect(weekBox).not.toBeNull();
      const adjacentGap = weekBox!.y - (scheduleBox!.y + scheduleBox!.height);
      expect(adjacentGap).toBeGreaterThanOrEqual(8);
      expect(adjacentGap).toBeLessThanOrEqual(16);
      await page.screenshot({
        path: `../.artifacts/screenshots/task-56/${current.surface}-${current.viewport.width}x${current.viewport.height}-${current.theme}-facts-actions.png`,
      });
    }
    if (current.telegram && current.step === 'decision') {
      const deferDecision = page.getByRole('button', { name: 'Отложить решение' });
      await deferDecision.scrollIntoViewIfNeeded();
      await expectNoOverlap(deferDecision, page.locator('#appBottomNav'));
      await page.screenshot({
        path: `../.artifacts/screenshots/task-56/${current.surface}-${current.viewport.width}x${current.viewport.height}-${current.theme}-decision-actions.png`,
      });
    }
    await page.close();
  }
});

for (const scenario of todayStates) {
  test(`Today ${scenario.name} keeps one primary action in Mobile Web and mocked TMA`, async ({
    mobilePage,
    tma,
    tmaPage,
  }) => {
    await installPlatformApi(tmaPage, scenario.options);
    await installPlatformApi(mobilePage, { ...scenario.options, browserSession: true });

    await Promise.all([tmaPage.goto('/app'), mobilePage.goto('/app')]);
    const tmaAction = tmaPage
      .getByRole('button', { name: scenario.action })
      .or(tmaPage.getByRole('link', { name: scenario.action }));
    const mobileAction = mobilePage
      .getByRole('button', { name: scenario.action })
      .or(mobilePage.getByRole('link', { name: scenario.action }));
    await expect(tmaAction).toBeVisible();
    await expect(mobileAction).toBeVisible();
    if (scenario.name === 'completed') {
      await expect(tmaPage.getByRole('navigation', { name: 'Эта неделя' })).not.toBeAttached();
      await expect(mobilePage.getByRole('navigation', { name: 'Эта неделя' })).not.toBeAttached();
    } else {
      await expect(tmaPage.getByRole('navigation', { name: 'Эта неделя' })).toBeVisible();
      await expect(mobilePage.getByRole('navigation', { name: 'Эта неделя' })).toBeVisible();
    }
    expect(await sharedSurfaceSignature(tmaPage)).toEqual(await sharedSurfaceSignature(mobilePage));
    await expectNoHorizontalOverflow(tmaPage);
    await expectNoHorizontalOverflow(mobilePage);
    await expectNoOverlap(tmaAction, tmaPage.locator('#appBottomNav'));

    const routeBeforeRuntimeEvents = tmaPage.url();
    await tma.setViewport(760, 844);
    await tma.setTheme('dark');
    await tma.setActive(false);
    await tma.setActive(true);
    await expect(tmaAction).toBeVisible();
    expect(tmaPage.url()).toBe(routeBeforeRuntimeEvents);
  });
}

test('active workout starts, logs offline and resumes once after reconnect and reload', async ({
  tma,
  tmaPage,
}) => {
  const api = await installPlatformApi(tmaPage, { workoutStatus: 'planned' });
  await tmaPage.goto('/app');
  await tmaPage.getByRole('button', { name: 'Начать тренировку' }).click();
  await expect(
    tmaPage.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }),
  ).toBeVisible();

  api.setOffline(true);
  await setNetworkOffline(tmaPage, true);
  const reps = tmaPage.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' });
  const weight = tmaPage.getByRole('spinbutton', { name: 'Вес, Приседания, подход 1' });
  await reps.fill('8');
  await weight.fill('40');
  await tma.setTheme('dark');
  await expect(reps).toHaveValue('8');
  await expect(weight).toHaveValue('40');
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-72/mock-tma-390x844-dark-active-workout.png',
  });
  await tmaPage.getByRole('button', { name: 'Завершить: Приседания, подход 1' }).click();
  await expect(tmaPage.getByText('Сохранено на устройстве')).toBeVisible();
  expect((await tma.state()).haptics.notifications).toContain('success');

  api.setOffline(false);
  await setNetworkOffline(tmaPage, false);
  await expect(tmaPage.getByText('Синхронизировано')).toBeVisible();
  expect(api.setPatchCalls()).toBe(1);
  expect(api.workoutValues()).toEqual({ actualReps: 8, actualWeight: 40, completed: true });

  await tmaPage.reload();
  await tmaPage.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await tmaPage.getByRole('button', { name: '1 из 1 сохранено' }).click();
  await expect(
    tmaPage.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }),
  ).toHaveValue('8');
  await expect(tmaPage.getByRole('spinbutton', { name: 'Вес, Приседания, подход 1' })).toHaveValue(
    '40',
  );
  await expectNoHorizontalOverflow(tmaPage);
});

test('progression guidance applies a configured step once, stays optional and matches Mobile Web', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  await tmaPage.addInitScript(() => {
    const events: unknown[] = [];
    Object.defineProperty(window, '__progressionEvents', { value: events, writable: false });
    window.addEventListener('yfc:product-event', (event) => {
      events.push((event as CustomEvent).detail);
    });
  });
  const api = await installPlatformApi(tmaPage, {
    workoutStatus: 'in_progress',
    progressionOutcome: 'consider_progressing',
  });
  await installPlatformApi(mobilePage, {
    browserSession: true,
    workoutStatus: 'in_progress',
    progressionOutcome: 'consider_progressing',
  });

  await Promise.all([tmaPage.goto('/app'), mobilePage.goto('/app')]);
  await Promise.all([
    tmaPage.getByRole('button', { name: 'Продолжить тренировку' }).click(),
    mobilePage.getByRole('button', { name: 'Продолжить тренировку' }).click(),
  ]);
  const tmaGuidance = tmaPage.getByRole('region', { name: 'Рекомендация по следующей нагрузке' });
  const mobileGuidance = mobilePage.getByRole('region', {
    name: 'Рекомендация по следующей нагрузке',
  });
  await expect(tmaGuidance).toContainText('Можно рассмотреть небольшое увеличение веса');
  await expect(mobileGuidance).toContainText('Можно рассмотреть небольшое увеличение веса');
  expect(await tmaGuidance.textContent()).toBe(await mobileGuidance.textContent());
  await expect(tmaGuidance.locator('.ui-button--primary')).not.toBeAttached();

  await tmaGuidance.getByText('Почему?', { exact: true }).click();
  await expect(tmaGuidance.getByText('Цель: 1 × 8–10')).toBeVisible();
  await expect(tmaGuidance.getByText(/запас записан: 1/)).toBeVisible();
  const disclosureGeometry = await tmaGuidance.locator('.disclosure-icon').evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      width: rect.width,
      height: rect.height,
      radius: getComputedStyle(element).borderRadius,
    };
  });
  expect(disclosureGeometry).toEqual({ width: 28, height: 28, radius: '50%' });
  await expectTouchTargets(tmaGuidance.locator('summary, button'));
  await expectNoHorizontalOverflow(tmaPage);

  api.setOffline(true);
  await setNetworkOffline(tmaPage, true);
  await tmaGuidance.getByRole('button', { name: 'Подставить 42,5 кг' }).dblclick();
  const weight = tmaPage.getByRole('spinbutton', { name: 'Вес, Приседания, подход 1' });
  await expect(weight).toHaveValue('42.5');
  await expect(tmaPage.getByText('Сохранено на устройстве')).toBeVisible();

  api.setOffline(false);
  await setNetworkOffline(tmaPage, false);
  await expect(tmaPage.getByText('Синхронизировано')).toBeVisible();
  expect(api.setPatchCalls()).toBe(1);
  expect(api.workoutValues().actualWeight).toBe(42.5);

  await tma.setTheme('dark');
  await tma.setActive(false);
  await tma.setActive(true);
  await tmaPage.reload();
  await tmaPage.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await expect(tmaPage.getByRole('spinbutton', { name: 'Вес, Приседания, подход 1' })).toHaveValue(
    '42.5',
  );
  await expect(tmaPage.getByRole('button', { name: 'Вес подставлен' })).toBeDisabled();
  expect(api.setPatchCalls()).toBe(1);

  await tmaPage.getByRole('button', { name: 'Скрыть подсказку' }).click();
  await expect(
    tmaPage.getByRole('region', { name: 'Рекомендация по следующей нагрузке' }),
  ).not.toBeAttached();
  const events = await tmaPage.evaluate(
    () =>
      (
        window as typeof window & {
          __progressionEvents: Array<Record<string, unknown>>;
        }
      ).__progressionEvents,
  );
  expect(events.map((event) => event.name)).toEqual(
    expect.arrayContaining(['progression_suggestion_shown', 'progression_suggestion_dismissed']),
  );
  expect(JSON.stringify(events)).not.toContain('Приседания');
});

test('progression guidance screenshots cover outcomes, long content and responsive themes', async ({
  browser,
}) => {
  const cases = [
    {
      surface: 'mobile-web',
      width: 360,
      height: 800,
      theme: 'light',
      outcome: 'review',
      label: 'review-insufficient',
    },
    {
      surface: 'mobile-web',
      width: 390,
      height: 844,
      theme: 'light',
      outcome: 'hold',
      label: 'hold-without-rir',
    },
    {
      surface: 'mobile-web',
      width: 430,
      height: 932,
      theme: 'light',
      outcome: 'consider_reducing',
      label: 'reduce',
    },
    {
      surface: 'tablet-web',
      width: 768,
      height: 900,
      theme: 'dark',
      outcome: 'hold',
      label: 'hold-dark',
    },
    {
      surface: 'desktop-web',
      width: 1440,
      height: 900,
      theme: 'light',
      outcome: 'consider_progressing',
      label: 'increase',
    },
    {
      surface: 'tma-mock',
      width: 390,
      height: 844,
      theme: 'dark',
      outcome: 'consider_progressing',
      label: 'increase-long-name-with-rir',
      longExerciseName: true,
    },
  ] as const;

  for (const current of cases) {
    const page = await browser.newPage({
      viewport: { width: current.width, height: current.height },
      hasTouch: current.width <= 768,
      isMobile: current.width <= 430,
      reducedMotion: 'reduce',
    });
    if (current.surface === 'tma-mock') {
      await installTelegramHarness(page, {
        colorScheme: current.theme,
        viewportHeight: current.height,
        viewportStableHeight: current.height,
      });
      await installPlatformApi(page, {
        workoutStatus: 'in_progress',
        progressionOutcome: current.outcome,
        longExerciseName: current.longExerciseName,
      });
    } else {
      await page.addInitScript((theme) => localStorage.setItem('app-theme', theme), current.theme);
      await installPlatformApi(page, {
        browserSession: true,
        workoutStatus: 'in_progress',
        progressionOutcome: current.outcome,
        longExerciseName: Boolean('longExerciseName' in current && current.longExerciseName),
      });
    }

    await page.goto('/app');
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    const exerciseTitle =
      'longExerciseName' in current && current.longExerciseName
        ? 'Приседания со штангой с контролируемой паузой в нижней точке'
        : 'Приседания';
    const exercise = namedArticle(page, exerciseTitle);
    await expect(exercise).toHaveCount(1);
    const guidance = exercise.getByRole('region', { name: 'Рекомендация по следующей нагрузке' });
    await guidance.getByText('Почему?', { exact: true }).click();
    await expect(guidance).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', current.theme);
    await expectNoHorizontalOverflow(page);
    await expectTouchTargets(guidance.locator('summary, button'));

    const geometry = await exercise.evaluate((element) => {
      const head = element.querySelector<HTMLElement>('.active-workout-exercise__head');
      const guidanceRegion = element.querySelector<HTMLElement>('.progression-guidance');
      const sets = element.querySelector<HTMLElement>('.active-workout-exercise__sets');
      if (!head || !guidanceRegion || !sets) throw new Error('Progression layout region missing');
      const headBox = head.getBoundingClientRect();
      const guidanceBox = guidanceRegion.getBoundingClientRect();
      const setsBox = sets.getBoundingClientRect();
      return {
        headBottom: headBox.bottom,
        guidanceTop: guidanceBox.top,
        guidanceBottom: guidanceBox.bottom,
        setsTop: setsBox.top,
      };
    });
    expect(geometry.headBottom).toBeLessThanOrEqual(geometry.guidanceTop);
    expect(geometry.guidanceBottom).toBeLessThanOrEqual(geometry.setsTop);

    await exercise.screenshot({
      path: `../.artifacts/screenshots/task-63/${current.surface}-${current.width}x${current.height}-${current.theme}-${current.label}.png`,
    });
    await page.close();
  }
});

test('completion summary survives finish retry, feedback error, reload and TMA lifecycle', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  const api = await installPlatformApi(tmaPage, { workoutStatus: 'planned' });
  await tmaPage.goto('/app');
  await tmaPage.getByRole('button', { name: 'Начать тренировку' }).click();
  await tmaPage.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }).fill('8');
  await tmaPage.getByRole('spinbutton', { name: 'Вес, Приседания, подход 1' }).fill('40');
  await tmaPage.getByRole('button', { name: 'Завершить: Приседания, подход 1' }).click();
  await expect(tmaPage.getByText('Синхронизировано')).toBeVisible();
  await tmaPage.getByRole('button', { name: 'Завершить тренировку' }).click();

  await expect(tmaPage.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible();
  await expect(tmaPage.getByText('1 ч')).toBeVisible();
  await expect(tmaPage.getByText(/максимальный вес 40 кг/)).toBeVisible();
  await expect(tmaPage.getByText(/Следующая тренировка/)).toBeVisible();
  expect(api.finishCalls()).toBe(1);
  await expectNoHorizontalOverflow(tmaPage);
  const focusHeader = tmaPage.locator('.today-workout-focus__header');
  const backAction = focusHeader.getByRole('button', { name: 'К сводке' });
  const focusTitle = focusHeader.getByText('Итог тренировки');
  const [backBox, titleBox] = await Promise.all([
    backAction.boundingBox(),
    focusTitle.boundingBox(),
  ]);
  expect(backBox?.x ?? 0).toBeGreaterThanOrEqual(24);
  expect((titleBox?.x ?? 0) + (titleBox?.width ?? 0)).toBeLessThanOrEqual(
    (await tmaPage.evaluate(() => window.innerWidth)) - 24,
  );
  const resultsDisclosure = tmaPage.locator('.workout-completion__results');
  const resultsSummary = resultsDisclosure.locator('summary');
  const [resultsBox, resultsTextBox] = await Promise.all([
    resultsDisclosure.boundingBox(),
    resultsSummary.boundingBox(),
  ]);
  expect(resultsBox?.height ?? Infinity).toBeLessThanOrEqual(54);
  expect(
    Math.abs(
      (resultsTextBox?.x ?? 0) +
        (resultsTextBox?.width ?? 0) / 2 -
        ((resultsBox?.x ?? 0) + (resultsBox?.width ?? 0) / 2),
    ),
  ).toBeLessThanOrEqual(2);

  const feedbackLegend = tmaPage.locator('.workout-completion__feedback legend');
  const firstFeedback = tmaPage.getByRole('button', { name: 'Легче ожидаемого' });
  const [legendBox, firstFeedbackBox] = await Promise.all([
    feedbackLegend.boundingBox(),
    firstFeedback.boundingBox(),
  ]);
  expect(
    (firstFeedbackBox?.y ?? 0) - ((legendBox?.y ?? 0) + (legendBox?.height ?? 0)),
  ).toBeGreaterThanOrEqual(11.99);
  await expect(firstFeedback).toHaveCSS('border-radius', '14px');
  await expect(tmaPage.getByRole('button', { name: 'Вернуться в Сегодня' })).toHaveCSS(
    'border-radius',
    '14px',
  );

  const duplicateStatus = await tmaPage.evaluate(async () => {
    const response = await fetch('/api/v1/workouts/42/finish', { method: 'POST' });
    return response.status;
  });
  expect(duplicateStatus).toBe(200);
  expect(api.finishCalls()).toBe(2);
  await expect(tmaPage.getByRole('heading', { name: 'Тренировка завершена' })).toHaveCount(1);

  await tma.setSafeArea({ top: 28, right: 2, bottom: 22, left: 2 });
  await tma.setContentSafeArea({ top: 40, right: 0, bottom: 18, left: 0 });
  const note = tmaPage.getByRole('textbox', { name: 'Заметка' });
  await note.fill('Сохранить ровный темп');
  await tmaPage.getByRole('button', { name: 'Нормально' }).click();
  await note.focus();
  await tma.setViewport(560, MOBILE_CONTEXTS.baseline.height, false);
  await expect(tmaPage.locator('#appBottomNav')).toBeHidden();
  await tmaPage.getByRole('button', { name: 'Сохранить' }).scrollIntoViewIfNeeded();
  await expectNoHorizontalOverflow(tmaPage);

  api.setOffline(true);
  await tmaPage.getByRole('button', { name: 'Сохранить' }).click();
  await expect(tmaPage.getByRole('alert')).toContainText('Введённый текст сохранён в форме');
  await expect(note).toHaveValue('Сохранить ровный темп');
  api.setOffline(false);
  await tmaPage.getByRole('button', { name: 'Сохранить' }).click();
  await expect(tmaPage.getByText('Обратная связь сохранена')).toBeVisible();
  expect(api.completionFeedback()).toEqual({
    feedback: 'as_expected',
    note: 'Сохранить ровный темп',
  });

  await tma.setTheme('dark');
  await tma.setActive(false);
  await tma.setActive(true);
  await tma.setViewport(MOBILE_CONTEXTS.baseline.height, MOBILE_CONTEXTS.baseline.height);
  await tmaPage.reload();
  await expect(tmaPage.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible();
  await expect(tmaPage.getByRole('textbox', { name: 'Заметка' })).toHaveValue(
    'Сохранить ровный темп',
  );
  await expect(
    tmaPage.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }),
  ).not.toBeAttached();
  await expect.poll(async () => (await tma.state()).backButton.visible).toBe(false);
  for (const viewport of Object.values(MOBILE_CONTEXTS)) {
    await tmaPage.setViewportSize(viewport);
    await tma.setViewport(viewport.height, viewport.height);
    await expectNoHorizontalOverflow(tmaPage);
  }

  await mobilePage.goto('/');
  const landingButtons = mobilePage.locator('.landing-button');
  await expect(landingButtons).not.toHaveCount(0);
  for (const button of await landingButtons.all()) {
    await expect(button).toHaveCSS('border-radius', '14px');
  }
});

test('nutrition quick paths recover in TMA and match Mobile Web before core navigation', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  await tmaPage.addInitScript(() => {
    const events: unknown[] = [];
    Object.defineProperty(window, '__productAnalyticsEvents', { value: events, writable: false });
    window.addEventListener('yfc:product-event', (event) => {
      events.push((event as CustomEvent).detail);
    });
  });
  const api = await installPlatformApi(tmaPage, { workoutStatus: 'in_progress' });
  await installPlatformApi(mobilePage, { workoutStatus: 'in_progress', browserSession: true });
  await Promise.all([
    tmaPage.goto('/app?section=nutrition'),
    mobilePage.goto('/app?section=nutrition'),
  ]);
  await expect(tmaPage.getByRole('heading', { name: 'Питание', exact: true })).toBeVisible();
  await expect(mobilePage.getByRole('heading', { name: 'Питание', exact: true })).toBeVisible();
  expect(await sharedSurfaceSignature(tmaPage)).toEqual(await sharedSurfaceSignature(mobilePage));
  for (const [surface, currentPage] of [
    ['mock-tma', tmaPage],
    ['mobile-web', mobilePage],
  ] as const) {
    const week = currentPage.getByRole('navigation', { name: 'Неделя дневника' });
    await expect(week.locator('button[aria-current="date"]')).toBeVisible();
    await expect(week.locator('button[aria-pressed="true"]')).toBeVisible();
    await expect(currentPage.getByRole('navigation', { name: 'Дата дневника' })).not.toBeAttached();
    if (TASK_74_CAPTURE_PHASE) {
      await currentPage.evaluate(() => window.scrollTo(0, 0));
      await currentPage.screenshot({
        path: `${TASK_74_SCREENSHOT_DIR}/${TASK_74_CAPTURE_PHASE}-${surface}-390x844-light-nutrition-week.png`,
      });
    }
    expect(
      await week.evaluate((element) => {
        const style = getComputedStyle(element);
        return [Number.parseFloat(style.paddingTop), Number.parseFloat(style.paddingBottom)];
      }),
    ).toEqual([0, 8]);
  }

  const breakfast = tmaPage.getByRole('region', { name: 'Завтрак' });
  await breakfast.getByRole('button', { name: /Добавить/ }).click();
  await expect(tmaPage.getByRole('button', { name: 'Добавить Овсяная каша' })).toBeVisible();
  await tmaPage.getByRole('button', { name: 'Поиск по штрихкоду', exact: true }).click();
  await tmaPage.getByRole('textbox', { name: 'Штрихкод' }).fill('3017620422003');
  await tmaPage.getByRole('button', { name: 'Найти', exact: true }).click();
  await expect(tmaPage.getByText('Овсяная каша')).toBeVisible();
  await tmaPage.getByRole('button', { name: 'Выбрать продукт' }).click();
  await tmaPage.getByRole('button', { name: 'Добавить в дневник' }).click();
  await expect(tmaPage.getByText('Овсяная каша')).toBeVisible();
  await breakfast.getByRole('button', { name: /Добавить/ }).click();
  await tmaPage.getByRole('button', { name: 'Избранное' }).click();
  await expect(tmaPage.getByRole('button', { name: 'Добавить Овсяная каша' })).toBeVisible();
  await tmaPage
    .getByRole('dialog')
    .getByRole('button', { name: 'Быстрый ввод', exact: true })
    .click();
  await tma.setSafeArea({ top: 20, right: 2, bottom: 24, left: 2 });
  await tma.setContentSafeArea({ top: 32, right: 0, bottom: 18, left: 0 });
  const calories = tmaPage.getByRole('spinbutton', { name: 'Калории' });
  await calories.fill('510');
  await tmaPage.getByRole('textbox', { name: 'Название (необязательно)' }).fill('TMA перекус');
  const quickAddAction = tmaPage.getByRole('button', {
    name: 'Сохранить Quick Add',
    exact: true,
  });
  const submitDock = tmaPage.locator('.nutrition-picker__submit');
  await expect(quickAddAction).toHaveCount(1);
  for (const viewport of [MOBILE_CONTEXTS.compact, MOBILE_CONTEXTS.baseline]) {
    await tmaPage.setViewportSize(viewport);
    await tma.setViewport(560, viewport.height, false);
    await quickAddAction.scrollIntoViewIfNeeded();
    const [actionBox, paddingBottom, viewportHeight] = await Promise.all([
      quickAddAction.boundingBox(),
      submitDock.evaluate((submit) => Number.parseFloat(getComputedStyle(submit).paddingBottom)),
      tmaPage.evaluate(() => window.innerHeight),
    ]);
    expect(actionBox).not.toBeNull();
    const geometry = {
      actionBottom: actionBox!.y + actionBox!.height,
      paddingBottom,
      viewportHeight,
    };
    expect(geometry.paddingBottom).toBeGreaterThanOrEqual(24);
    expect(geometry.actionBottom).toBeLessThanOrEqual(geometry.viewportHeight - 23);
    await expectNoHorizontalOverflow(tmaPage);
  }
  await expect(tmaPage.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
  await expect(tmaPage.locator('#appBottomNav')).toBeHidden();
  await tma.setTheme('dark');
  await tma.setActive(false);
  await tma.setActive(true);
  await expect(calories).toHaveValue('510');
  await expect(tmaPage.getByRole('dialog')).toBeVisible();

  api.setOffline(true);
  await tmaPage.getByRole('button', { name: 'Сохранить Quick Add' }).click();
  await expect(tmaPage.getByRole('alert')).toBeVisible();
  await expect(calories).toHaveValue('510');
  api.setOffline(false);
  await tmaPage.getByRole('dialog').getByRole('button', { name: 'Повторить', exact: true }).click();
  await expect(tmaPage.getByRole('dialog')).not.toBeAttached();
  await expect(tmaPage.getByText('TMA перекус')).toBeVisible();
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-62/tma-390x844-dark-food-logged.png',
  });
  if (TASK_74_CAPTURE_PHASE === 'after') {
    await tmaPage.screenshot({
      path: `${TASK_74_SCREENSHOT_DIR}/mock-tma-390x844-dark-food-logged.png`,
    });
  }
  const analyticsEvents = await tmaPage.evaluate(
    () =>
      (
        window as typeof window & {
          __productAnalyticsEvents: Array<Record<string, unknown>>;
        }
      ).__productAnalyticsEvents,
  );
  expect(analyticsEvents.filter((event) => event.name === 'tma_launched')).toHaveLength(1);
  expect(analyticsEvents).toContainEqual(
    expect.objectContaining({
      name: 'food_logged',
      surface: 'tma',
      entry_method: 'quick_add',
    }),
  );
  expect(analyticsEvents).toContainEqual(
    expect.objectContaining({
      name: 'tma_core_action_completed',
      surface: 'tma',
      action: 'food_logged',
    }),
  );
  expect(JSON.stringify(analyticsEvents)).not.toContain('TMA перекус');
  expect(JSON.stringify(analyticsEvents)).not.toContain('energy_kcal');

  const entry = tmaPage.locator('.nutrition-entry').filter({ hasText: 'TMA перекус' });
  await entry.getByRole('button', { name: 'Повторить' }).click();
  await tmaPage.getByRole('dialog').getByRole('button', { name: 'Повторить продукт' }).click();
  await expect(tmaPage.getByText('Скопировано записей: 1')).toBeVisible();
  await expectNoHorizontalOverflow(tmaPage);

  await tmaPage.getByRole('link', { name: 'Прогресс', exact: true }).click();
  await expect(tmaPage).toHaveURL('/app?section=progress');
  await tmaPage.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await tmaPage
    .getByRole('dialog')
    .getByRole('link', { name: 'Профиль и настройки', exact: true })
    .click();
  await expect(tmaPage.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
  await tmaPage.getByRole('link', { name: 'Сегодня', exact: true }).click();
  await expect(tmaPage.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  await expectNoHorizontalOverflow(tmaPage);
});

test('manual nutrition targets validate, preserve keyboard flow and expose effective history in Mobile Web and TMA', async ({
  mobilePage,
  tma,
  tmaPage,
}) => {
  const api = await installPlatformApi(tmaPage);
  await installPlatformApi(mobilePage, {
    browserSession: true,
    nutritionTargetSource: 'trainer',
  });
  await Promise.all([
    tmaPage.goto('/app?section=nutrition'),
    mobilePage.goto('/app?section=nutrition'),
  ]);

  for (const currentPage of [tmaPage, mobilePage]) {
    await currentPage
      .locator('#nutrition-target-settings')
      .getByRole('heading', { name: 'КБЖУ', exact: true })
      .click();
    if (currentPage === mobilePage) {
      await expect(currentPage.getByText('Назначено тренером', { exact: true })).toBeVisible();
      await expect(
        currentPage.getByLabel('Текущие ориентиры КБЖУ').getByText('Изменил: Ирина Тренерова'),
      ).toBeVisible();
      await currentPage.getByRole('button', { name: 'Указать вручную' }).click();
    }
    await expect(currentPage.getByRole('button', { name: 'Указать вручную' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(
      currentPage.getByText(currentPage === mobilePage ? 'Назначено тренером' : 'Указано вручную', {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      currentPage.getByLabel('Текущие ориентиры КБЖУ').getByText('Ориентир для текущего этапа'),
    ).toBeVisible();
    await expectNoHorizontalOverflow(currentPage);
  }
  expect(await sharedSurfaceSignature(tmaPage)).toEqual(await sharedSurfaceSignature(mobilePage));

  const calories = tmaPage.getByRole('spinbutton', { name: 'Калории, ккал' });
  const protein = tmaPage.getByRole('spinbutton', { name: 'Белки, г' });
  const fat = tmaPage.getByRole('spinbutton', { name: 'Жиры, г' });
  const carbs = tmaPage.getByRole('spinbutton', { name: 'Углеводы, г' });
  await calories.fill('1200');
  await protein.fill('200');
  await fat.fill('100');
  await carbs.fill('200');
  const save = tmaPage.getByRole('button', { name: 'Сохранить ручные ориентиры' });
  await expect(tmaPage.getByRole('alert')).toContainText('Проверьте разницу: 1300 ккал');
  await expect(save).toBeDisabled();
  await tmaPage.getByRole('checkbox', { name: /Сохранить значения/ }).check();

  await tma.setSafeArea({ top: 24, right: 2, bottom: 22, left: 2 });
  await tma.setContentSafeArea({ top: 36, right: 0, bottom: 18, left: 0 });
  await carbs.focus();
  await tma.setViewport(560, MOBILE_CONTEXTS.baseline.height, false);
  await expect(tmaPage.locator('#appBottomNav')).toBeHidden();
  await save.scrollIntoViewIfNeeded();
  await expect(save).toBeInViewport();
  await expectNoHorizontalOverflow(tmaPage);
  await tma.setTheme('dark');
  await tma.setActive(false);
  await tma.setActive(true);
  await expect(calories).toHaveValue('1200');
  await expect(tmaPage.getByRole('checkbox', { name: /Сохранить значения/ })).toBeChecked();

  await save.click();
  await expect(tmaPage.getByText('Ручные ориентиры КБЖУ сохранены')).toBeVisible();
  await expect(tmaPage.getByText('Калории 2100 → 1200 ккал')).toBeAttached();
  expect(api.manualTargetSaves()).toBe(1);
  expect(api.targetHistoryLength()).toBe(3);

  const retry = await tmaPage.evaluate(async () => {
    const response = await fetch('/api/v1/nutrition/targets/manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        calories: 1200,
        protein_g: 200,
        fat_g: 100,
        carbs_g: 200,
        effective_from: new Date().toLocaleDateString('sv-SE', {
          timeZone: 'Europe/Moscow',
        }),
        note: null,
        confirm_energy_mismatch: true,
      }),
    });
    return { status: response.status, id: (await response.json()).id };
  });
  expect(retry.status).toBe(200);
  expect(api.manualTargetSaves()).toBe(2);
  expect(api.targetHistoryLength()).toBe(3);

  const targetCard = tmaPage.locator('#nutrition-target-settings > details');
  if ((await targetCard.getAttribute('open')) === null) {
    await tmaPage
      .locator('#nutrition-target-settings')
      .getByRole('heading', { name: 'КБЖУ', exact: true })
      .click();
  }
  for (const viewport of Object.values(MOBILE_CONTEXTS)) {
    await tmaPage.setViewportSize(viewport);
    await tma.setViewport(viewport.height, viewport.height);
    await expectNoHorizontalOverflow(tmaPage);
    await expectTouchTargets(tmaPage.locator('.nutrition-target-mode > button'));
  }
});

test('manual nutrition target history screenshots cover all responsive surfaces and themes', async ({
  browser,
}) => {
  const cases = [
    { surface: 'mobile-web', width: 360, height: 800, theme: 'light' },
    { surface: 'mobile-web', width: 390, height: 844, theme: 'dark' },
    { surface: 'mobile-web', width: 430, height: 932, theme: 'light' },
    { surface: 'mobile-web', width: 768, height: 900, theme: 'dark' },
    { surface: 'desktop-web', width: 1440, height: 900, theme: 'light' },
    { surface: 'tma-mock', width: 360, height: 800, theme: 'dark' },
    { surface: 'tma-mock', width: 390, height: 844, theme: 'light' },
    { surface: 'tma-mock', width: 430, height: 932, theme: 'dark' },
  ] as const;

  for (const current of cases) {
    const page = await browser.newPage({
      viewport: { width: current.width, height: current.height },
      hasTouch: current.width <= 768,
      isMobile: current.width <= 430,
      reducedMotion: 'reduce',
    });
    if (current.surface === 'tma-mock') {
      await installTelegramHarness(page, {
        colorScheme: current.theme,
        viewportHeight: current.height,
        viewportStableHeight: current.height,
      });
      await installPlatformApi(page, { nutritionTargetSource: 'trainer' });
    } else {
      await page.addInitScript((theme) => localStorage.setItem('app-theme', theme), current.theme);
      await installPlatformApi(page, { browserSession: true });
    }

    await page.goto('/app?section=nutrition');
    await page
      .locator('#nutrition-target-settings')
      .getByRole('heading', { name: 'КБЖУ', exact: true })
      .click();
    if (current.surface === 'tma-mock') {
      await expect(page.getByText('Назначено тренером', { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Указать вручную' }).click();
    }
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', current.theme);
    await expect(page.getByLabel('Текущие ориентиры КБЖУ')).toBeVisible();
    await expectNoHorizontalOverflow(page);

    const brandContract = await page.evaluate(() => {
      const tokenColor = (token: string) => {
        const sample = document.createElement('span');
        sample.style.color = `var(${token})`;
        document.body.append(sample);
        const color = getComputedStyle(sample).color;
        sample.remove();
        return color;
      };
      const save = document.querySelector<HTMLElement>('.nutrition-target-save');
      const activeMode = document.querySelector<HTMLElement>(
        '.nutrition-target-mode > button.is-active',
      );
      const note = document.querySelector<HTMLElement>('.nutrition-target-note');
      const disclosureIcons = Array.from(
        document.querySelectorAll<HTMLElement>('.nutrition-target-history__list .disclosure-icon'),
      );
      return {
        lime: tokenColor('--v2-lime'),
        onLime: tokenColor('--v2-on-lime'),
        saveBackground: save ? getComputedStyle(save).backgroundColor : null,
        saveColor: save ? getComputedStyle(save).color : null,
        activeModeShadow: activeMode ? getComputedStyle(activeMode).boxShadow : null,
        noteBorder: note ? getComputedStyle(note).borderLeftColor : null,
        disclosureIcons: disclosureIcons.map((icon) => {
          const rect = icon.getBoundingClientRect();
          return {
            width: rect.width,
            height: rect.height,
            radius: getComputedStyle(icon).borderRadius,
          };
        }),
      };
    });
    expect(brandContract.saveBackground).toBe(brandContract.lime);
    expect(brandContract.saveColor).toBe(brandContract.onLime);
    expect(brandContract.activeModeShadow).toContain(brandContract.lime);
    expect(brandContract.noteBorder).toBe(brandContract.lime);
    expect(brandContract.disclosureIcons.length).toBeGreaterThan(0);
    expect(
      brandContract.disclosureIcons.every(
        ({ width, height, radius }) => width === 28 && height === 28 && radius === '50%',
      ),
    ).toBe(true);

    const targetCard = page.locator('#nutrition-target-settings > details');
    await targetCard.scrollIntoViewIfNeeded();
    await targetCard.screenshot({
      path: `../.artifacts/screenshots/task-55/${current.surface}-${current.width}x${current.height}-${current.theme}.png`,
    });
    await page.close();
  }
});

test('contextual help covers workout, nutrition and Progress without a TMA library', async ({
  tma,
  tmaPage,
}) => {
  await installPlatformApi(tmaPage, { workoutStatus: 'planned' });
  await tmaPage.goto('/app');

  await expect(tmaPage.getByRole('link', { name: 'База знаний' })).not.toBeAttached();
  await tmaPage.getByRole('button', { name: 'Начать тренировку' }).click();
  const currentSet = tmaPage.locator('[aria-current="step"]');
  await expect(currentSet).toHaveCount(1);
  await currentSet.getByText('Дополнительно', { exact: true }).click();
  const rirDetails = tmaPage.locator('.active-workout-rir .contextual-help');
  const rirHelp = rirDetails.getByText('Что это?', { exact: true });
  await rirHelp.click();
  const rirArticleLink = tmaPage
    .locator('.active-workout-rir')
    .getByRole('link', { name: /Подробнее на сайте/ });
  await expect(rirArticleLink).toHaveAttribute(
    'href',
    '/knowledge/training/repetitions-in-reserve',
  );
  await rirArticleLink.click();
  await expect
    .poll(async () => (await tma.state()).openedLinks)
    .toContain('http://127.0.0.1:4173/knowledge/training/repetitions-in-reserve');
  await expect(tmaPage).toHaveURL(/\/app$/);
  await expect(rirDetails).toHaveAttribute('open', '');
  await tma.setTheme('dark');
  await expect(rirDetails).toHaveAttribute('open', '');
  await rirHelp.click();
  await expect(rirHelp).toBeFocused();
  await expect(rirDetails).not.toHaveAttribute('open', '');

  await tmaPage.getByRole('link', { name: 'Питание', exact: true }).click();
  await tmaPage
    .locator('#nutrition-target-settings')
    .getByRole('heading', { name: 'КБЖУ', exact: true })
    .click();
  await tmaPage.getByRole('button', { name: 'Рассчитать ориентиры' }).click();
  const nutritionHelp = tmaPage.locator('.contextual-help').getByText('Что это?', { exact: true });
  await nutritionHelp.click();
  await expect(
    tmaPage.locator('.contextual-help').getByRole('link', { name: /Подробнее на сайте/ }),
  ).toHaveAttribute('href', '/knowledge/nutrition/kbju-as-a-reference');

  await tmaPage.getByRole('link', { name: 'Прогресс', exact: true }).click();
  await tmaPage.locator('.progress-hero').getByText('Что это?', { exact: true }).click();
  await expect(
    tmaPage.locator('.progress-hero').getByRole('link', { name: /Подробнее на сайте/ }),
  ).toHaveAttribute('href', '/knowledge/progress/how-to-read-progress');
  await tma.setTheme('light');
  await expectNoHorizontalOverflow(tmaPage);

  await tmaPage.goto('/knowledge');
  await expect(tmaPage.getByRole('heading', { name: 'Продолжить чтение на сайте' })).toBeVisible();
  await tma.setTheme('dark');
  await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-121/tma-knowledge-handoff-390x844-dark.png',
    fullPage: true,
  });
  const publicHandoff = tmaPage.getByRole('link', { name: 'Открыть материал на сайте' });
  await expectTouchTargets(tmaPage.locator('.knowledge-handoff__actions a'));
  await expectNoHorizontalOverflow(tmaPage);
  await tmaPage.keyboard.press('Tab');
  await expect(publicHandoff).toBeFocused();
  await publicHandoff.click();
  await expect(tmaPage).toHaveURL('/app');
  await expect
    .poll(async () => (await tma.state()).openedLinks)
    .toContain('http://127.0.0.1:4173/knowledge');
  await expect(tmaPage.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  await expect(tmaPage.getByRole('heading', { name: /База знаний/i })).not.toBeAttached();

  await tmaPage.goto('/app/knowledge/progress/how-to-read-progress');
  await expect(tmaPage.getByRole('heading', { name: 'Продолжить чтение на сайте' })).toBeVisible();
  await tmaPage.getByRole('link', { name: 'Открыть материал на сайте' }).click();
  await expect(tmaPage).toHaveURL('/app');
  await expect
    .poll(async () => (await tma.state()).openedLinks)
    .toContain('http://127.0.0.1:4173/knowledge/progress/how-to-read-progress');
});

test('task 72 screenshot packet keeps shared composition across core surfaces', async ({
  browser,
}) => {
  const phoneScenarios = [
    { label: 'today', viewport: MOBILE_CONTEXTS.compact, path: '/app', theme: 'light' as const },
    {
      label: 'progress',
      viewport: MOBILE_CONTEXTS.baseline,
      path: '/app?section=progress',
      theme: 'dark' as const,
    },
    {
      label: 'nutrition-barcode',
      viewport: MOBILE_CONTEXTS.large,
      path: '/app?section=nutrition',
      theme: 'dark' as const,
    },
  ];

  for (const scenario of phoneScenarios) {
    for (const surface of ['mobile-web', 'mock-tma'] as const) {
      const context = await browser.newContext({ viewport: scenario.viewport, hasTouch: true });
      const page = await context.newPage();
      if (scenario.label === 'nutrition-barcode') await installBarcodeCameraCapability(page);
      if (surface === 'mock-tma') {
        await installTelegramHarness(page, {
          colorScheme: scenario.theme,
          viewportHeight: scenario.viewport.height,
          viewportStableHeight: scenario.viewport.height,
          safeAreaInset: { top: 20, right: 0, bottom: 18, left: 0 },
          contentSafeAreaInset: { top: 32, right: 0, bottom: 14, left: 0 },
        });
        await installPlatformApi(page);
      } else {
        await page.addInitScript(
          (theme) => localStorage.setItem('app-theme', theme),
          scenario.theme,
        );
        await installPlatformApi(page, { browserSession: true });
      }
      await page.goto(scenario.path);
      if (scenario.label === 'today') {
        await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeVisible();
      } else if (scenario.label === 'progress') {
        const confidences = page
          .locator('#progress-body')
          .getByRole('region', { name: /^Достаточно ли данных:/ });
        await expect(confidences).not.toHaveCount(0);
        for (const confidence of await confidences.all()) await expect(confidence).toBeVisible();
      } else {
        await expect(page.getByRole('heading', { name: 'Питание', exact: true })).toBeVisible();
      }

      if (scenario.label === 'progress') {
        const confidences = page
          .locator('#progress-body')
          .getByRole('region', { name: /^Достаточно ли данных:/ });
        for (const confidence of await confidences.all()) {
          await confidence.scrollIntoViewIfNeeded();
          await expectLimeStartBoundary(confidence);
        }
      }
      if (scenario.label === 'nutrition-barcode') {
        await page
          .getByRole('region', { name: 'Завтрак' })
          .getByRole('button', { name: /Добавить/ })
          .click();
        await page.getByRole('button', { name: 'Поиск по штрихкоду', exact: true }).click();
        const barcodeInput = page.getByRole('textbox', { name: 'Штрихкод' });
        const manualSearch = page.getByRole('button', { name: 'Найти', exact: true });
        await expect(barcodeInput).toBeVisible();
        await expect(page.getByRole('button', { name: 'Сканировать камерой' })).toHaveClass(
          /ui-button--primary/,
        );
        await expect(manualSearch).toHaveClass(/ui-button--secondary/);
        const [inputBox, searchBox] = await Promise.all([
          barcodeInput.boundingBox(),
          manualSearch.boundingBox(),
        ]);
        expect(inputBox).not.toBeNull();
        expect(searchBox).not.toBeNull();
        expect(Math.abs(inputBox!.y - searchBox!.y)).toBeLessThanOrEqual(1);
        expect(Math.abs(inputBox!.height - searchBox!.height)).toBeLessThanOrEqual(1);
      }
      await expectNoHorizontalOverflow(page);
      await page.screenshot({
        path: `../.artifacts/screenshots/task-72/${surface}-${scenario.viewport.width}x${scenario.viewport.height}-${scenario.theme}-${scenario.label}.png`,
      });
      await context.close();
    }
  }

  for (const viewport of [
    { width: 768, height: 900 },
    { width: 1280, height: 900 },
  ]) {
    const page = await browser.newPage({ viewport });
    await installPlatformApi(page, { browserSession: true });
    await page.goto(viewport.width === 768 ? '/app?section=progress' : '/app');
    const progressConfidences = page
      .locator('#progress-body')
      .getByRole('region', { name: /^Достаточно ли данных:/ });
    if (viewport.width === 768) {
      await expect(progressConfidences).not.toHaveCount(0);
      for (const confidence of await progressConfidences.all())
        await expect(confidence).toBeVisible();
    } else {
      await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeVisible();
    }
    await expectNoHorizontalOverflow(page);
    await page.screenshot({
      path: `../.artifacts/screenshots/task-72/mobile-web-${viewport.width}x${viewport.height}-light-${viewport.width === 768 ? 'progress' : 'today'}.png`,
    });
    await page.close();
  }

  const desktopBarcode = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await installBarcodeCameraCapability(desktopBarcode);
  await installPlatformApi(desktopBarcode, { browserSession: true });
  await desktopBarcode.goto('/app?section=nutrition');
  await desktopBarcode
    .getByRole('region', { name: 'Завтрак' })
    .getByRole('button', { name: /Добавить/ })
    .click();
  await desktopBarcode.getByRole('button', { name: 'Поиск по штрихкоду', exact: true }).click();
  await expect(
    desktopBarcode.getByRole('button', { name: 'Сканировать камерой' }),
  ).not.toBeAttached();
  await expect(desktopBarcode.getByRole('button', { name: 'Найти', exact: true })).toHaveClass(
    /ui-button--primary/,
  );
  await expectNoHorizontalOverflow(desktopBarcode);
  await desktopBarcode.screenshot({
    path: '../.artifacts/screenshots/task-72/desktop-web-1280x900-light-nutrition-barcode.png',
  });
  await desktopBarcode.close();
});
