import { expect, test, type Page } from '@playwright/test';

test.use({ video: 'on' });

const captureLandingProductProofs =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.YFC_CAPTURE_LANDING_PRODUCT_PROOFS === '1';

type SetState = {
  actual_reps: number | null;
  actual_weight: number | null;
  duration_minutes?: number | null;
  distance_km?: number | null;
  average_heart_rate_bpm?: number | null;
  heart_rate_zone?: number | null;
  rir: '0' | '1' | '2' | '3' | '4+' | null;
  set_kind: 'warmup' | 'working' | 'drop' | null;
  reached_failure: boolean | null;
  is_completed: boolean;
  version: number;
};

async function mockActiveWorkout(page: Page, mixed = false) {
  const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Moscow' });
  let finished = false;
  let failSetPatch = false;
  let resolveCardioCompleted!: () => void;
  const cardioCompleted = new Promise<void>((resolve) => {
    resolveCardioCompleted = resolve;
  });
  const sets = new Map<number, SetState>([
    [
      201,
      {
        actual_reps: null,
        actual_weight: null,
        rir: null,
        set_kind: 'working',
        reached_failure: false,
        is_completed: false,
        version: 1,
      },
    ],
    [
      202,
      {
        actual_reps: null,
        actual_weight: null,
        rir: null,
        set_kind: 'working',
        reached_failure: false,
        is_completed: false,
        version: 1,
      },
    ],
    [
      203,
      {
        actual_reps: null,
        actual_weight: null,
        rir: null,
        set_kind: 'working',
        reached_failure: false,
        is_completed: false,
        version: 1,
      },
    ],
    ...(mixed
      ? ([
          [
            204,
            {
              actual_reps: null,
              actual_weight: null,
              duration_minutes: null,
              distance_km: null,
              average_heart_rate_bpm: null,
              heart_rate_zone: null,
              rir: null,
              set_kind: null,
              reached_failure: null,
              is_completed: false,
              version: 1,
            },
          ],
        ] as Array<[number, SetState]>)
      : []),
  ]);
  const workout = () => ({
    id: 42,
    scheduled_date: today,
    title: 'Силовая база',
    status: 'in_progress',
    day_number: 1,
    week_number: 1,
    started_at: new Date(Date.now() - 12 * 60_000).toISOString(),
    completed_at: null,
    exercises: [
      {
        id: 101,
        exercise_id: 11,
        exercise_title: 'Жим штанги лёжа',
        metric_type: 'strength',
        sort_order: 1,
        prescribed_sets: 3,
        prescribed_reps: '8–10',
        rest_seconds: 90,
        notes: 'Сохраняйте устойчивое положение корпуса.',
        has_guide: true,
        sets: [...sets]
          .filter(([id]) => id !== 204)
          .map(([id, state], index) => ({
            id,
            set_number: index + 1,
            ...state,
          })),
      },
      ...(mixed
        ? [
            {
              id: 102,
              exercise_id: 12,
              exercise_title: 'Велотренажёр',
              metric_type: 'cardio',
              sort_order: 2,
              prescribed_sets: 1,
              prescribed_reps: '',
              prescribed_duration_minutes: 25,
              rest_seconds: 0,
              notes: 'Ровный разговорный темп.',
              has_guide: false,
              progression_guidance: null,
              sets: [{ id: 204, set_number: 1, ...sets.get(204)! }],
            },
          ]
        : []),
    ],
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/public/config')) {
      return route.fulfill({
        json: { app_env: 'dev', enable_dev_auth: true, telegram_bot_username: 'fit_bot' },
      });
    }
    if (path.endsWith('/auth/refresh')) {
      return route.fulfill({ status: 401, json: { detail: 'No refresh cookie' } });
    }
    if (path.endsWith('/auth/telegram/init')) {
      return route.fulfill({ json: { access_token: 'telegram-test-token', token_type: 'bearer' } });
    }
    if (path.endsWith('/auth/dev-login')) {
      return route.fulfill({ json: { access_token: 'test-token', token_type: 'bearer' } });
    }
    if (path.endsWith('/me')) {
      return route.fulfill({
        json: {
          id: 7,
          first_name: 'Тест',
          is_coach: false,
          is_admin: false,
          has_active_program: true,
          has_workout_history: true,
          onboarding: { status: 'complete', required_fields: ['goal'], missing_fields: [] },
          profile: { full_name: 'Тестовый пользователь', timezone: 'Europe/Moscow' },
          trainer: null,
        },
      });
    }
    if (path.endsWith('/workouts/today')) {
      if (finished) {
        return route.fulfill({ status: 404, json: { detail: 'На сегодня тренировка завершена' } });
      }
      return route.fulfill({ json: workout() });
    }
    if (path.endsWith('/workouts/progress/summary')) {
      return route.fulfill({
        json: {
          training: { last_completed_workout_on: finished ? today : null, next_workout: null },
          body: { latest_measurement: null, trends: [] },
          adherence: {
            formula_version: 'adherence-v1',
            overall_percent: null,
            included_components: [],
          },
        },
      });
    }
    if (path.endsWith('/nutrition/diary')) {
      return route.fulfill({
        json: {
          diary_date: today,
          timezone: 'Europe/Moscow',
          meals: [],
          totals: { energy_kcal: '0', protein_g: '0', fat_g: '0', carbs_g: '0', fiber_g: null },
          targets: null,
          remaining: null,
        },
      });
    }
    if (path.endsWith('/programs/exercises/11')) {
      return route.fulfill({
        json: {
          id: 11,
          title: 'Жим штанги лёжа',
          metric_type: 'strength',
          primary_muscle: 'Грудь',
          equipment: 'Штанга и скамья',
          primary_muscle_ids: ['chest'],
          secondary_muscle_ids: ['triceps'],
          equipment_ids: ['barbell', 'bench'],
          alternatives: [],
          difficulty_level: 'beginner',
          is_custom: false,
          is_personalized: false,
          has_guide: true,
          guide: {
            technique_steps: ['Сведите лопатки.', 'Опускайте штангу под контролем.'],
            breathing: 'Вдох при опускании, выдох после тяжёлой части подъёма.',
            common_mistakes: ['Отрыв таза от скамьи'],
            muscles: [
              {
                identifier: 'chest',
                name: 'Грудь',
                role_id: 'primary',
                role: 'Основная',
                function: 'Перемещает руку вперёд в фазе усилия.',
              },
            ],
            equipment: [
              { identifier: 'barbell', name: 'Штанга' },
              { identifier: 'bench', name: 'Скамья' },
            ],
            safety_notes: ['Используйте страховку при тяжёлых подходах.'],
            alternatives: [],
            media: [],
            images: [],
            media_reference: 'test:bench-press',
            source_name: 'Test source',
            source_url: 'https://example.com',
            source_license: 'Public domain',
            source_license_url: null,
          },
        },
      });
    }
    const setMatch = path.match(/\/workouts\/sets\/(\d+)$/);
    if (setMatch) {
      if (failSetPatch) {
        return route.fulfill({ status: 503, json: { detail: 'Сервис временно недоступен' } });
      }
      const setId = Number(setMatch[1]);
      const current = sets.get(setId)!;
      const body = request.postDataJSON() as Partial<SetState>;
      const next = {
        ...current,
        actual_reps: body.actual_reps ?? null,
        actual_weight: body.actual_weight ?? null,
        duration_minutes: body.duration_minutes ?? null,
        distance_km: body.distance_km ?? null,
        average_heart_rate_bpm: body.average_heart_rate_bpm ?? null,
        heart_rate_zone: body.heart_rate_zone ?? null,
        rir: body.rir ?? null,
        set_kind: body.set_kind ?? null,
        reached_failure: body.reached_failure ?? null,
        is_completed: body.is_completed ?? false,
        version: current.version + 1,
      };
      sets.set(setId, next);
      if (setId === 204 && next.is_completed) resolveCardioCompleted();
      return route.fulfill({
        json: { id: setId, set_number: setId === 204 ? 1 : setId - 200, ...next },
      });
    }
    if (path.endsWith('/workouts/42/finish')) {
      finished = true;
      return route.fulfill({ status: 204, body: '' });
    }
    return route.fulfill({ json: [] });
  });

  return {
    failSetPatch(value: boolean) {
      failSetPatch = value;
    },
    cardioCompleted,
  };
}

test('active workout keeps one obvious next action through logging, timer and finish', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.setViewportSize({ width: 390, height: 844 });
  if (captureLandingProductProofs) {
    await page.addInitScript(() => {
      if (!localStorage.getItem('app-theme')) localStorage.setItem('app-theme', 'light');
    });
  }
  await page.addInitScript(() => {
    const events: unknown[] = [];
    Object.defineProperty(window, '__productAnalyticsEvents', { value: events, writable: false });
    window.addEventListener('yfc:product-event', (event) => {
      events.push((event as CustomEvent).detail);
    });
  });
  await mockActiveWorkout(page);

  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  if (captureLandingProductProofs) {
    await expect(page.getByRole('heading', { name: 'Жим штанги лёжа' })).toBeVisible();
    await page.screenshot({
      path: '../.artifacts/runtime/tests/product-proofs/landing-workout-mobile-light.png',
    });
    await page.evaluate(() => localStorage.setItem('app-theme', 'dark'));
    await page.reload({ waitUntil: 'domcontentloaded' });
    const darkClientEntry = page.getByRole('button', { name: 'Клиент' });
    if (await darkClientEntry.isVisible()) await darkClientEntry.click();
    const darkWorkoutEntry = page.getByRole('button', { name: 'Продолжить тренировку' });
    await expect(darkWorkoutEntry).toBeVisible();
    await darkWorkoutEntry.click();
    await expect(page.getByRole('heading', { name: 'Жим штанги лёжа' })).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
    await page.screenshot({
      path: '../.artifacts/runtime/tests/product-proofs/landing-workout-mobile-dark.png',
    });
    return;
  }

  const firstSet = page.locator('[data-workout-set-id="201"]');
  await expect(firstSet).toHaveAttribute('aria-current', 'step');
  await firstSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' }).fill('40');
  await firstSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 1' }).fill('8');
  await firstSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).dblclick();

  const secondSet = page.locator('[data-workout-set-id="202"]');
  await expect(secondSet).toHaveAttribute('aria-current', 'step');
  await expect(secondSet.getByText('Предыдущий подход: 40 кг × 8')).toBeVisible();
  await expect(page.getByRole('timer').filter({ hasText: 'Отдых' })).toContainText(
    'Дальше: Жим штанги лёжа, подход 2',
  );

  await secondSet.getByText('Дополнительно').click();
  await secondSet.getByLabel('Вид подхода').selectOption('drop');
  await secondSet.getByRole('button', { name: '2 — ещё примерно 2 повтора' }).click();
  await secondSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 2' }).fill('35');
  await secondSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 2' }).fill('9');
  await secondSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' }).click();

  const thirdSet = page.locator('[data-workout-set-id="203"]');
  await expect(thirdSet).toHaveAttribute('aria-current', 'step');
  await thirdSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 3' }).fill('32.5');
  await thirdSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 3' }).fill('10');
  await thirdSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 3' }).click();

  await expect(page.getByText('Все подходы отмечены — можно завершать.')).toBeVisible();
  await expect(page.getByText('Синхронизировано')).toBeVisible();
  await page.getByRole('button', { name: 'Завершить тренировку' }).click();
  const completedHeading = page.getByRole('heading', { name: 'Тренировка завершена' });
  await expect(completedHeading).toBeVisible();
  await completedHeading.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-62/mobile-web-390x844-light-workout-completed.png',
  });
  const analyticsEvents = await page.evaluate(
    () =>
      (
        window as typeof window & {
          __productAnalyticsEvents: Array<Record<string, unknown>>;
        }
      ).__productAnalyticsEvents,
  );
  expect(analyticsEvents).toContainEqual(
    expect.objectContaining({ name: 'workout_completed', surface: 'mobile_web' }),
  );
  expect(JSON.stringify(analyticsEvents)).not.toContain('actual_weight');
  expect(JSON.stringify(analyticsEvents)).not.toContain('actual_reps');
});

test('active workout has touch-size controls and no horizontal overflow', async ({ page }) => {
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const exercise = page.locator('.active-workout-exercise').first();
  await expect(exercise).toHaveCSS('border-radius', '0px');
  await expect(exercise).toHaveCSS('border-top-color', 'rgb(208, 208, 208)');
  await expect(exercise).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  const guideButton = page.getByRole('button', { name: 'Техника' });
  await expect(guideButton).toHaveText('Техника');
  await guideButton.click();
  await expect(page.getByRole('heading', { name: 'Техника выполнения' })).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();

  for (const viewport of [
    { width: 1280, height: 900 },
    { width: 768, height: 900 },
    { width: 430, height: 932 },
    { width: 390, height: 844 },
    { width: 360, height: 800 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
    const box = await page
      .getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' })
      .boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
    if (viewport.width <= 430) {
      const focusHeader = page.locator('.today-workout-focus__header');
      await expect(focusHeader.locator(':scope > div > span')).toBeHidden();
      await expect(focusHeader.locator(':scope > span')).toBeHidden();
      await expect(focusHeader.getByText('Текущая тренировка')).toBeVisible();
    }
  }
});

test('touch Mobile Web keeps mixed controls usable with hover none', async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 430, height: 932 },
    hasTouch: true,
    isMobile: true,
    colorScheme: 'light',
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  try {
    await mockActiveWorkout(page, true);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    expect(await page.evaluate(() => matchMedia('(hover: none)').matches)).toBe(true);
    expect(await page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(true);
    const cardio = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
    const done = cardio.getByRole('button', { name: 'Завершить кардио: Велотренажёр' });
    expect((await done.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
  } finally {
    await context.close();
  }
});

test('mixed workout keeps cardio type-aware, compact and stable during input', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' });
  await page.setViewportSize({ width: 390, height: 844 });
  const server = await mockActiveWorkout(page, true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const cardio = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
  await expect(cardio.getByRole('heading', { name: 'Велотренажёр' })).toBeVisible();
  await expect(cardio.getByText('План: 25 мин')).toBeVisible();
  await expect(cardio.getByText(/Рабочие подходы|Повторы|Отдых, сек/)).toHaveCount(0);
  await expect(cardio.getByRole('spinbutton', { name: /Вес/ })).toHaveCount(0);

  await cardio.getByRole('button', { name: 'Завершить кардио: Велотренажёр' }).click();
  await expect(cardio.getByRole('alert')).toHaveText('Укажите длительность кардио.');
  await cardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' }).fill('27');
  await cardio.getByRole('spinbutton', { name: 'Дистанция, Велотренажёр' }).fill('6.4');
  const pulse = cardio.getByText('Пульс (необязательно)');
  await pulse.click();
  await cardio.getByRole('spinbutton', { name: 'Средний пульс, уд/мин' }).fill('138');
  await cardio.getByRole('combobox', { name: 'Зона пульса' }).selectOption('3');
  await expect(cardio.locator('details')).toHaveAttribute('open', '');
  await expect(page.getByText('Синхронизировано')).toBeVisible();
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-119/mobile-web-390x844-dark-mixed-workout.png',
    fullPage: true,
  });

  await cardio.getByRole('button', { name: 'Завершить кардио: Велотренажёр' }).click();
  await server.cardioCompleted;
  await expect
    .poll(() =>
      page.evaluate(() => {
        const stored = localStorage.getItem('fit_active_workout_v1_user_7_workout_42');
        if (!stored) return -1;
        return (JSON.parse(stored) as { queue: unknown[] }).queue.length;
      }),
    )
    .toBe(0);
  await page.reload();
  const clientEntry = page.getByRole('button', { name: 'Клиент' });
  if (await clientEntry.isVisible()) await clientEntry.click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await expect(cardio.getByRole('button', { name: 'Кардио сохранено' })).toBeVisible();
  await expect(cardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' })).toHaveCount(
    0,
  );
  await cardio.getByRole('button', { name: 'Кардио сохранено' }).click();
  await expect(cardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' })).toHaveValue(
    '27',
  );

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.evaluate(() => localStorage.setItem('app-theme', 'light'));
  await page.reload();
  const desktopClientEntry = page.getByRole('button', { name: 'Клиент' });
  if (await desktopClientEntry.isVisible()) await desktopClientEntry.click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const desktopCardio = page
    .locator('.active-workout-exercise')
    .filter({ hasText: 'Велотренажёр' });
  await desktopCardio.getByRole('button', { name: 'Кардио сохранено' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    .toBe(true);
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-119/desktop-web-1280x900-light-mixed-workout.png',
    fullPage: true,
  });
});

test('TMA active workout keeps in-page back while native back stays hidden and keyboard nav restores', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    const handlers = new Map<string, Set<() => void>>();
    const backState = { hide: 0, show: 0 };
    const backButton = {
      show() {
        backState.show += 1;
      },
      hide() {
        backState.hide += 1;
      },
      setText() {},
      enable() {},
      disable() {},
      onClick() {},
      offClick() {},
    };
    const telegram = {
      initData: 'signed-test-data',
      initDataUnsafe: {},
      isActive: true,
      viewportHeight: 560,
      viewportStableHeight: 844,
      safeAreaInset: { top: 28, right: 2, bottom: 20, left: 2 },
      contentSafeAreaInset: { top: 44, right: 0, bottom: 16, left: 0 },
      colorScheme: 'dark' as const,
      themeParams: {},
      BackButton: backButton,
      ready() {},
      expand() {},
      onEvent(event: string, callback: () => void) {
        const callbacks = handlers.get(event) ?? new Set<() => void>();
        callbacks.add(callback);
        handlers.set(event, callbacks);
      },
      offEvent(event: string, callback: () => void) {
        handlers.get(event)?.delete(callback);
      },
    };
    Object.assign(window, {
      Telegram: { WebApp: telegram },
      __backButtonState: backState,
    });
  });
  await mockActiveWorkout(page, true);

  await page.goto('/app?tgWebAppPlatform=android');
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  await expect(page.getByRole('button', { name: 'К сводке' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'hidden');
  expect(
    await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--yfc-viewport-height').trim(),
    ),
  ).toBe('560px');
  expect(
    await page.evaluate(() =>
      getComputedStyle(document.documentElement)
        .getPropertyValue('--yfc-viewport-stable-height')
        .trim(),
    ),
  ).toBe('844px');
  const tmaCardio = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
  await expect(
    tmaCardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' }),
  ).toBeVisible();
  await expect(tmaCardio.getByRole('spinbutton', { name: /Вес/ })).toHaveCount(0);

  const navigation = page.locator('#appBottomNav');
  await expect(navigation).toBeVisible();
  const weight = page.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' });
  await weight.focus();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
  await expect(navigation).toBeHidden();

  await page.getByRole('button', { name: 'К сводке' }).focus();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'hidden');
  await expect(navigation).toBeVisible();
  await expect(page).toHaveURL(/\/app\?tgWebAppPlatform=android$/);
  const backState = await page.evaluate(
    () =>
      (
        window as unknown as Window & {
          __backButtonState: { hide: number; show: number };
        }
      ).__backButtonState,
  );
  expect(backState.hide).toBeGreaterThanOrEqual(1);
  expect(backState.show).toBe(0);
});

test('save failure stays compact, keeps controls open and retries explicitly', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const server = await mockActiveWorkout(page);
  server.failSetPatch(true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const firstSet = page.locator('[data-workout-set-id="201"]');
  await firstSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' }).fill('40');
  await expect(page.getByText('Требуется действие')).toBeVisible();
  await expect(
    firstSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }),
  ).toBeEnabled();

  server.failSetPatch(false);
  await page.getByRole('button', { name: 'Повторить' }).click();
  await expect(page.getByText('Синхронизировано')).toBeVisible();
});

test('rest timer reconciles its deadline after a simulated hidden-tab return', async ({ page }) => {
  const start = new Date('2026-09-09T12:00:00Z');
  await page.clock.setFixedTime(start);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const firstSet = page.locator('[data-workout-set-id="201"]');
  await firstSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' }).fill('40');
  await firstSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 1' }).fill('8');
  await firstSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click();
  const timer = page.getByRole('timer').filter({ hasText: 'Отдых' });
  await expect(timer).toContainText('1:30');
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.clock.setFixedTime(new Date(start.getTime() + 65_000));
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(timer).toContainText('0:25');
  await page.clock.setFixedTime(new Date(start.getTime() + 100_000));
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await expect(timer).toHaveCount(0);
});
