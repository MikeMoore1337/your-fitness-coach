import { expect, test, type Locator, type Page } from '@playwright/test';

const mediaThumbnailUrl = '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg';
const mediaAnimationUrl = '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif';

test.use({ serviceWorkers: 'block', video: 'on' });

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
  planned_role?:
    | 'warmup'
    | 'working'
    | 'top'
    | 'backoff'
    | 'drop'
    | 'activation'
    | 'mini_set'
    | 'cluster_member'
    | null;
  planned_group_id?: number | null;
  planned_group_kind?:
    | 'sequence'
    | 'superset'
    | 'rest_pause'
    | 'myo_reps'
    | 'cluster'
    | 'drop_chain'
    | 'circuit'
    | null;
};

async function mockActiveWorkout(
  page: Page,
  mixed = false,
  mediaState: 'approved_animated' | 'blocked' = 'approved_animated',
) {
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
        planned_role: 'top',
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
        planned_role: 'backoff',
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
        planned_role: 'backoff',
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
        media_state: mediaState,
        media_thumbnail_url: mediaState === 'approved_animated' ? mediaThumbnailUrl : null,
        media_animation_url: mediaState === 'approved_animated' ? mediaAnimationUrl : null,
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
            media: [
              {
                type: 'animation',
                url: mediaAnimationUrl,
                poster: mediaThumbnailUrl,
                phase_id: 'movement',
                phase: 'Движение',
                alt: 'Жим штанги лёжа: движение',
                source_name: 'Gym visual',
                source_url: 'https://github.com/hasaneyldrm/exercises-dataset',
                source_license: 'Owner-purchased GymVisual license',
                source_license_url: 'https://gymvisual.com/',
                asset_id: 'gymvisual:0025:EIeI8Vf',
                asset_version: 'gymvisual-7455efae',
                variant_key: 'movement',
                width: 180,
                height: 180,
                byte_size: 12000,
                sort_order: 0,
                sources: [
                  {
                    url: mediaAnimationUrl,
                    mime_type: 'image/gif',
                    width: 180,
                    height: 180,
                    byte_size: 12000,
                  },
                  {
                    url: mediaThumbnailUrl,
                    mime_type: 'image/jpeg',
                    width: 180,
                    height: 180,
                    byte_size: 9000,
                  },
                ],
              },
            ],
            images: [
              {
                phase: 'Движение',
                url: mediaAnimationUrl,
                alt: 'Жим штанги лёжа: движение',
              },
            ],
            media_reference: 'exercise-guides:bench-press',
            source_name: 'Gym visual',
            source_url: 'https://github.com/hasaneyldrm/exercises-dataset',
            source_license: 'Owner-purchased GymVisual license',
            source_license_url: 'https://gymvisual.com/',
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

  await page.route(
    /\/static\/exercise-guides\/gymvisual\/bench-press-0025-EIeI8Vf\.jpg(?:\?.*)?$/,
    (route) =>
      route.fulfill({
        path: '../backend/assets/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg',
        contentType: 'image/jpeg',
      }),
  );
  await page.route(
    /\/static\/exercise-guides\/gymvisual\/bench-press-0025-EIeI8Vf\.gif(?:\?.*)?$/,
    (route) =>
      route.fulfill({
        path: '../backend/assets/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif',
        contentType: 'image/gif',
      }),
  );

  return {
    failSetPatch(value: boolean) {
      failSetPatch = value;
    },
    cardioCompleted,
  };
}

function waitForCompletedSetPatch(page: Page, setId: number) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    if (
      response.request().method() !== 'PATCH' ||
      !url.pathname.endsWith(`/workouts/sets/${setId}`) ||
      !response.ok()
    ) {
      return false;
    }
    try {
      return response.request().postDataJSON()?.is_completed === true;
    } catch {
      return false;
    }
  });
}

async function expectClearOfBottomDock(target: Locator, label: string) {
  await target.scrollIntoViewIfNeeded();
  const geometry = await target.evaluate((element) => {
    const dock = document.querySelector<HTMLElement>('#appBottomNav');
    const targetRect = element.getBoundingClientRect();
    const dockRect = dock?.getBoundingClientRect();
    const dockStyle = dock ? getComputedStyle(dock) : null;
    const dockVisible = Boolean(
      dockRect &&
      dockRect.width > 0 &&
      dockRect.height > 0 &&
      dockStyle?.display !== 'none' &&
      dockStyle?.visibility !== 'hidden',
    );
    return {
      dockTop: dockRect ? Math.round(dockRect.top) : null,
      dockVisible,
      targetBottom: Math.round(targetRect.bottom),
      targetHeight: Math.round(targetRect.height),
    };
  });

  expect(geometry.targetHeight, `${label} must be in the viewport`).toBeGreaterThan(0);
  if (geometry.dockVisible) {
    expect(
      geometry.targetBottom,
      `${label} bottom ${geometry.targetBottom}px must stay above dock top ${geometry.dockTop}px with 8px clearance`,
    ).toBeLessThanOrEqual((geometry.dockTop ?? 0) - 8);
  }
}

async function expectRealMediaFullWidth(page: Page, label: string) {
  const geometry = await page.evaluate(() => {
    const media = document.querySelector<HTMLElement>(
      '.active-workout-exercise__media:not(.active-workout-exercise__media--blocked)',
    );
    const technique = document.querySelector<HTMLElement>(
      '.active-workout-exercise__head .exercise-guide-trigger',
    );
    const image = media?.querySelector<HTMLImageElement>('img');
    if (!media || !technique || !image) return null;

    const mediaRect = media.getBoundingClientRect();
    const techniqueRect = technique.getBoundingClientRect();
    const imageRect = image.getBoundingClientRect();
    return {
      imageWidth: imageRect.width,
      mediaLeft: mediaRect.left,
      mediaRight: mediaRect.right,
      mediaWidth: mediaRect.width,
      techniqueLeft: techniqueRect.left,
      techniqueRight: techniqueRect.right,
      techniqueWidth: techniqueRect.width,
    };
  });

  expect(geometry, `${label}: real media geometry must be measurable`).not.toBeNull();
  const tolerance = 2;
  expect(
    Math.abs((geometry?.mediaLeft ?? 0) - (geometry?.techniqueLeft ?? 0)),
    `${label}: media and Technique left edges must align`,
  ).toBeLessThanOrEqual(tolerance);
  expect(
    Math.abs((geometry?.mediaRight ?? 0) - (geometry?.techniqueRight ?? 0)),
    `${label}: media and Technique right edges must align`,
  ).toBeLessThanOrEqual(tolerance);
  expect(
    geometry?.mediaWidth ?? 0,
    `${label}: media wrapper must fill the workout content column`,
  ).toBeGreaterThanOrEqual((geometry?.techniqueWidth ?? 0) - tolerance);
  expect(
    geometry?.imageWidth ?? 0,
    `${label}: rendered image must fill the media wrapper`,
  ).toBeGreaterThanOrEqual((geometry?.mediaWidth ?? 0) - tolerance);
}

async function resetPageScroll(page: Page) {
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    document.querySelector<HTMLElement>('#appContent')?.scrollTo(0, 0);
  });
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
  await expect(firstSet.getByText('Топ-сет', { exact: true })).toBeVisible();
  await firstSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' }).fill('40');
  await firstSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 1' }).fill('8');
  const firstDone = firstSet.getByRole('button', {
    name: 'Завершить: Жим штанги лёжа, подход 1',
  });
  await firstDone.scrollIntoViewIfNeeded();
  await Promise.all([waitForCompletedSetPatch(page, 201), firstDone.dblclick()]);

  const secondSet = page.locator('[data-workout-set-id="202"]');
  await expect(secondSet).toHaveAttribute('aria-current', 'step');
  await expect(secondSet.getByText('Бэкофф', { exact: true })).toBeVisible();
  await expect(secondSet.getByText('Предыдущий подход: 40 кг × 8')).toBeVisible();
  await secondSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 2' }).fill('35');
  await secondSet.getByRole('button', { name: 'Подставить предыдущий результат' }).click();
  await expect(
    secondSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 2' }),
  ).toHaveValue('35');
  await expect(
    secondSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 2' }),
  ).toHaveValue('8');
  await expect(
    secondSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' }),
  ).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByRole('timer').filter({ hasText: 'Отдых' })).toContainText(
    'Дальше: Жим штанги лёжа, подход 2',
  );

  await secondSet.getByText('Дополнительно').click();
  await secondSet.getByLabel('Вид подхода').selectOption('drop');
  await secondSet.getByRole('button', { name: '2 — ещё примерно 2 повтора' }).click();
  await secondSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 2' }).fill('35');
  await secondSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 2' }).fill('9');
  await Promise.all([
    waitForCompletedSetPatch(page, 202),
    secondSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' }).click(),
  ]);

  const thirdSet = page.locator('[data-workout-set-id="203"]');
  await expect(thirdSet).toHaveAttribute('aria-current', 'step');
  await thirdSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 3' }).fill('32.5');
  await thirdSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 3' }).fill('10');
  const thirdDone = thirdSet.getByRole('button', {
    name: 'Завершить: Жим штанги лёжа, подход 3',
  });
  await thirdDone.evaluate((element) =>
    element.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'nearest' }),
  );
  await expect(thirdDone).toBeVisible();
  await Promise.all([waitForCompletedSetPatch(page, 203), thirdDone.click()]);

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

test('active workout keeps the current exercise primary and exposes keyboard handoff', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page, true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const currentSet = page.locator('[data-workout-set-id="201"]');
  const weight = currentSet.getByRole('spinbutton', {
    name: 'Вес, Жим штанги лёжа, подход 1',
  });
  const reps = currentSet.getByRole('spinbutton', {
    name: 'Повторы, Жим штанги лёжа, подход 1',
  });
  const done = currentSet.getByRole('button', {
    name: 'Завершить: Жим штанги лёжа, подход 1',
  });
  await weight.focus();
  await weight.press('Enter');
  await expect(reps).toBeFocused();
  await reps.press('Enter');
  await expect(done).toBeFocused();

  const nextExercise = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
  await expect(nextExercise.getByRole('button', { name: 'Открыть упражнение' })).toBeVisible();
  await expect(nextExercise.locator('[id$="-details"][hidden]')).toHaveCount(1);
  await nextExercise.getByRole('button', { name: 'Открыть упражнение' }).click();
  await expect(
    nextExercise.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' }),
  ).toBeVisible();
});

test('active workout checkpoint evidence covers light dark reduced and responsive states', async ({
  page,
}) => {
  const enterWorkout = async () => {
    const clientEntry = page.getByRole('button', { name: 'Клиент' });
    const continueButton = page.getByRole('button', { name: 'Продолжить тренировку' });
    await Promise.race([
      clientEntry.waitFor({ state: 'visible', timeout: 5000 }),
      continueButton.waitFor({ state: 'visible', timeout: 5000 }),
    ]);
    if (await continueButton.isVisible()) {
      await continueButton.click();
      return;
    }
    await clientEntry.click();
    await expect(continueButton).toBeVisible();
    await continueButton.click();
  };

  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'no-preference', colorScheme: 'light' });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await enterWorkout();
  await expect(page.locator('.active-workout-exercise__media img')).toHaveAttribute(
    'data-media-mode',
    'animated',
  );
  await expectRealMediaFullWidth(page, '390px light animated');
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-light-390x844.png',
    fullPage: true,
  });
  await resetPageScroll(page);
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-light-390x844-viewport.png',
  });

  await page.evaluate(() => localStorage.setItem('app-theme', 'dark'));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await enterWorkout();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(page.locator('.active-workout-exercise__media img')).toHaveAttribute(
    'data-media-mode',
    'animated',
  );
  await expectRealMediaFullWidth(page, '390px dark animated');
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-dark-390x844.png',
    fullPage: true,
  });
  await resetPageScroll(page);
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-dark-390x844-viewport.png',
  });

  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await enterWorkout();
  await expect(page.locator('.active-workout-exercise__media img')).toHaveAttribute(
    'data-media-mode',
    'static-poster',
  );
  await expectRealMediaFullWidth(page, '390px dark reduced motion');
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-reduced-390x844.png',
    fullPage: true,
  });
  await resetPageScroll(page);
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-reduced-390x844-viewport.png',
  });

  for (const viewport of [
    { width: 320, height: 800 },
    { width: 430, height: 932 },
  ]) {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: 'no-preference', colorScheme: 'light' });
    await page.evaluate(() => localStorage.setItem('app-theme', 'light'));
    await page.reload({ waitUntil: 'domcontentloaded' });
    await enterWorkout();
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
    await expect(page.locator('.active-workout-exercise__media img')).toHaveAttribute(
      'data-media-mode',
      'animated',
    );
    await expectRealMediaFullWidth(page, `${viewport.width}px light animated`);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
    await page.screenshot({
      path: `../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-${viewport.width}x${viewport.height}.png`,
      fullPage: true,
    });
    await resetPageScroll(page);
    await page.screenshot({
      path: `../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-light-${viewport.width}x${viewport.height}-viewport.png`,
    });
  }
});

test('blocked exercise media stays compact and neutral in active workout', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page, false, 'blocked');
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const media = page.locator('.active-workout-exercise__media--blocked').first();
  await expect(media).toContainText('Изображение пока недоступно');
  await expect(media).toContainText('Для этого упражнения нет проверенного визуального материала.');
  await expect(media.locator('img')).toHaveCount(0);
  const box = await media.boundingBox();
  expect(box?.height).toBeGreaterThanOrEqual(150);
  expect(box?.height).toBeLessThan(220);
  const widthGeometry = await media.evaluate((element) => {
    const exercise = element.closest<HTMLElement>('.active-workout-exercise');
    if (!exercise) return null;
    const style = getComputedStyle(exercise);
    const contentWidth =
      exercise.getBoundingClientRect().width -
      parseFloat(style.paddingLeft) -
      parseFloat(style.paddingRight) -
      parseFloat(style.borderLeftWidth) -
      parseFloat(style.borderRightWidth);
    return {
      contentWidth,
      mediaWidth: element.getBoundingClientRect().width,
    };
  });
  expect(widthGeometry).not.toBeNull();
  expect(widthGeometry?.mediaWidth).toBeGreaterThanOrEqual((widthGeometry?.contentWidth ?? 0) - 1);
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-blocked-mobile-390x844.png',
    fullPage: true,
  });
});

test('active workout actionable controls clear the mobile bottom dock', async ({
  browser,
  baseURL,
}) => {
  for (const viewport of [
    { width: 320, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
  ]) {
    const context = await browser.newContext({
      baseURL,
      viewport,
      serviceWorkers: 'block',
    });
    const page = await context.newPage();
    try {
      await mockActiveWorkout(page);
      await page.goto('/app');
      await page.getByRole('button', { name: 'Клиент' }).click();
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

      await expect(page.locator('#appBottomNav')).toBeVisible();
      const currentSet = page.locator('[data-workout-set-id="201"]');
      const weight = currentSet.getByRole('spinbutton', {
        name: 'Вес, Жим штанги лёжа, подход 1',
      });
      const reps = currentSet.getByRole('spinbutton', {
        name: 'Повторы, Жим штанги лёжа, подход 1',
      });
      const done = currentSet.getByRole('button', {
        name: 'Завершить: Жим штанги лёжа, подход 1',
      });
      await expectClearOfBottomDock(weight, `${viewport.width}px focused input`);
      await weight.focus();
      await expectClearOfBottomDock(weight, `${viewport.width}px focused input`);
      await expectClearOfBottomDock(done, `${viewport.width}px complete CTA`);

      await weight.fill('40');
      await reps.fill('8');
      await Promise.all([waitForCompletedSetPatch(page, 201), done.dblclick()]);
      const rest = page.locator('.active-workout-rest');
      await expect(rest).toBeVisible();
      await expectClearOfBottomDock(
        rest.getByRole('button', { name: '+30 сек' }),
        `${viewport.width}px rest timer control`,
      );
    } finally {
      await context.close();
    }
  }
});

test('active workout has touch-size controls and no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const exercise = page.locator('.active-workout-exercise').first();
  await expect(exercise.locator('.active-workout-exercise__media img')).toHaveAttribute(
    'src',
    mediaAnimationUrl,
  );
  await expect(exercise.locator('.active-workout-exercise__media img')).toHaveAttribute(
    'data-media-mode',
    'animated',
  );
  await exercise.locator('.active-workout-exercise__media img').scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/tasks/390/evidence/screenshots/active-workout-inline-mobile-390x844.png',
  });
  await expect(exercise).toHaveCSS('border-radius', '0px');
  await expect(exercise).toHaveCSS('border-top-color', 'rgb(208, 208, 208)');
  await expect(exercise).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  const guideButton = page.getByRole('button', { name: 'Техника' });
  await expect(guideButton).toHaveText('Техника');
  await guideButton.click();
  await expect(page.getByRole('heading', { name: 'Техника выполнения' })).toBeVisible();
  const guideImages = page.locator('.exercise-guide-image img');
  await expect(guideImages).toHaveCount(1);
  await expect(guideImages.first()).toHaveAttribute('data-media-mode', 'animation');
  await guideImages.first().scrollIntoViewIfNeeded();
  await expect
    .poll(() => guideImages.nth(0).evaluate((image) => (image as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
  await expect(page.locator('.exercise-guide-image video')).toHaveCount(0);
  await page.screenshot({
    path: '../.artifacts/tasks/390/evidence/screenshots/active-workout-mobile-390x844.png',
  });
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
    await expect(page.locator('.active-workout-exercise__media img')).toHaveAttribute(
      'data-media-mode',
      'static-poster',
    );
    const cardio = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
    await cardio.getByRole('button', { name: 'Открыть упражнение' }).click();
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
  await cardio.getByRole('button', { name: 'Открыть упражнение' }).click();
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
  await tmaCardio.getByRole('button', { name: 'Открыть упражнение' }).click();
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
