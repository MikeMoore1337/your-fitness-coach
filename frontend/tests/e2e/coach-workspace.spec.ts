import { expect, test, type Page } from '@playwright/test';

const captureAudit = Boolean(
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.CAPTURE_COACH_AUDIT,
);
const captureTask76 =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.CAPTURE_TASK_76 === '1';
const captureLandingProductProofs =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.YFC_CAPTURE_LANDING_PRODUCT_PROOFS === '1';

const clients = [
  {
    id: 11,
    invite_id: null,
    telegram_user_id: 3011,
    username: 'anna_runner',
    full_name: 'Анна Петрова',
    goal: 'maintenance',
    level: 'intermediate',
    height_cm: 168,
    weight_kg: 62,
    workouts_per_week: 3,
    cardio_trainings_per_week: 1,
    timezone: 'Europe/Moscow',
    kbju: null,
    status: 'active',
  },
  {
    id: 12,
    invite_id: null,
    telegram_user_id: 3012,
    username: 'boris_long',
    full_name: 'Борис Александрович С Очень Длинной Фамилией',
    goal: 'muscle_gain',
    level: 'beginner',
    height_cm: 190,
    weight_kg: 92,
    workouts_per_week: 2,
    cardio_trainings_per_week: 0,
    timezone: 'Europe/Moscow',
    kbju: null,
    status: 'active',
  },
  {
    id: 13,
    invite_id: null,
    telegram_user_id: 3013,
    username: 'maria',
    full_name: 'Мария Орлова',
    goal: 'fat_loss',
    level: 'advanced',
    height_cm: 172,
    weight_kg: 70,
    workouts_per_week: 4,
    cardio_trainings_per_week: 2,
    timezone: 'Europe/Moscow',
    kbju: null,
    status: 'active',
  },
  {
    id: null,
    invite_id: 91,
    telegram_user_id: null,
    username: null,
    full_name: 'Елена — приглашение ожидает подтверждения',
    status: 'pending',
  },
];

const component = (
  status: 'available' | 'not_applicable',
  percent: number | null,
  achieved: number,
  evaluated: number,
) => ({ status, percent, achieved, evaluated, weight: status === 'available' ? 1 : 0 });

function summary(
  userId: number,
  name: string,
  lastWorkout: string | null,
  personalRecords: number,
  measuredOn: string | null,
) {
  return {
    user_id: userId,
    client_name: name,
    period_days: 30,
    period_start: '2026-07-22',
    period_end: '2026-08-20',
    training: {
      planned_workouts: 8,
      completed_workouts: 6,
      frequency_per_week: 1.5,
      volume_kg: 14200,
      new_personal_records: personalRecords,
      last_completed_workout_on: lastWorkout,
      next_workout:
        userId === 11
          ? {
              id: 501,
              scheduled_date: '2026-08-22',
              scheduled_time: '18:30:00',
              title: 'Ноги и корпус',
              status: 'planned',
            }
          : null,
    },
    nutrition: {
      visible: userId !== 13,
      logged_days: userId === 13 ? 0 : 16,
      adherence_evaluated_days: userId === 13 ? 0 : 14,
      average_calories: userId === 13 ? null : 2050,
      target_calories: userId === 13 ? null : 2150,
      average_protein_g: userId === 13 ? null : 132,
      target_protein_g: userId === 13 ? null : 140,
      target_effective_on: userId === 13 ? null : '2026-07-01',
    },
    body: {
      latest_measurement: measuredOn ? { measured_on: measuredOn, weight_kg: 68.5 } : null,
      trends: [],
      priority: null,
      guidance: {},
    },
    adherence: {
      formula_version: 'adherence-v1',
      overall_percent: 75,
      included_components: ['workouts'],
      workouts: component('available', 75, 6, 8),
      cardio: component('not_applicable', null, 0, 0),
      calories: component('not_applicable', null, 0, 0),
      protein: component('not_applicable', null, 0, 0),
    },
    data_sufficiency: {},
  };
}

function coachNutritionReport(url: URL) {
  const period = url.searchParams.get('period') ?? 'days_30';
  const dayCount = period === 'days_7' ? 7 : period === 'days_90' ? 90 : 30;
  const periodEnd = new Date('2026-08-20T12:00:00Z');
  const periodStart = new Date(periodEnd);
  periodStart.setUTCDate(periodEnd.getUTCDate() - (dayCount - 1));
  const dates = Array.from({ length: dayCount }, (_, index) => {
    const date = new Date(periodStart);
    date.setUTCDate(periodStart.getUTCDate() + index);
    return date.toISOString().slice(0, 10);
  });
  const daily = dates.map((diaryDate, index) => ({
    diary_date: diaryDate,
    status: index === 0 ? 'complete' : index === dayCount - 1 ? 'incomplete' : 'missing',
    is_current_day: false,
    calories: index === 0 ? 2050 : index === dayCount - 1 ? 720 : null,
    protein_g: index === 0 ? 142 : index === dayCount - 1 ? 48 : null,
    fat_g: index === 0 ? 68 : index === dayCount - 1 ? 25 : null,
    carbs_g: index === 0 ? 210 : index === dayCount - 1 ? 82 : null,
    target_calories: 2100,
    target_protein_g: 140,
    target_fat_g: 70,
    target_carbs_g: 220,
    calorie_deviation: index === 0 ? -50 : null,
    protein_deviation_g: index === 0 ? 2 : null,
    fat_deviation_g: index === 0 ? -2 : null,
    carbs_deviation_g: index === 0 ? -10 : null,
    within_calorie_tolerance: index === 0 ? true : null,
    meets_protein_target: index === 0 ? true : null,
    target_changed: false,
  }));
  const metric = (average: number) => ({
    average,
    minimum: average,
    maximum: average,
    sample_days: 1,
  });
  const comparison = (actual: number, target: number) => ({
    average_actual: actual,
    average_target: target,
    average_deviation: actual - target,
    evaluated_days: 1,
  });
  return {
    period,
    period_start: dates[0],
    period_end: dates.at(-1),
    timezone: 'Europe/Moscow',
    summary: {
      logged_days: 1,
      eligible_days: dayCount,
      coverage_percent: Math.round(1000 / dayCount) / 10,
      complete_days: 1,
      incomplete_days: 1,
      fasted_days: 0,
      missing_days: dayCount - 2,
      current_day_status: null,
      calories: metric(2050),
      protein_g: metric(142),
      fat_g: metric(68),
      carbs_g: metric(210),
      calorie_comparison: comparison(2050, 2100),
      protein_comparison: comparison(142, 140),
      fat_comparison: comparison(68, 70),
      carbs_comparison: comparison(210, 220),
      days_within_calorie_tolerance: 1,
      calorie_tolerance_evaluated_days: 1,
      days_meeting_protein_target: 1,
      protein_target_evaluated_days: 1,
    },
    daily,
    target_changes: [],
  };
}

async function mockCoachWorkspace(page: Page) {
  const feedbackComments: Array<{
    id: number;
    trainer_author_id: number;
    client_user_id: number;
    workout_id: number;
    workout_exercise_id: number | null;
    body: string;
    body_format: string;
    created_at: string;
    updated_at: string | null;
    revisions: unknown[];
  }> = [
    {
      id: 801,
      trainer_author_id: 1,
      client_user_id: 11,
      workout_id: 501,
      workout_exercise_id: null,
      body: 'Хороший контроль темпа во всех подходах.',
      body_format: 'plain_text',
      created_at: '2026-08-19T19:30:00',
      updated_at: null,
      revisions: [],
    },
  ];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path.endsWith('/public/config'))
      return route.fulfill({
        json: { app_env: 'dev', enable_dev_auth: true, telegram_bot_username: 'fit_bot' },
      });
    if (path.endsWith('/auth/refresh'))
      return route.fulfill({ status: 401, json: { detail: 'No refresh cookie' } });
    if (path.endsWith('/auth/dev-login'))
      return route.fulfill({ json: { access_token: 'coach-token', token_type: 'bearer' } });
    if (path.endsWith('/me'))
      return route.fulfill({
        json: {
          id: 1,
          telegram_user_id: 2001,
          username: 'coach',
          first_name: 'Ирина',
          is_coach: true,
          is_admin: false,
          has_active_program: true,
          has_workout_history: true,
          onboarding: { status: 'complete', required_fields: [], missing_fields: [] },
          profile: {
            full_name: 'Ирина Тренер',
            goal: 'maintenance',
            level: 'advanced',
            workouts_per_week: 3,
            timezone: 'Europe/Moscow',
            kbju: null,
          },
          trainer: null,
        },
      });
    if (path.endsWith('/coach/client-summaries'))
      return route.fulfill({
        json: {
          items: [
            summary(11, 'Анна Петрова', '2026-08-19', 2, '2026-08-18'),
            summary(12, 'Борис Александрович', '2026-08-08', 0, null),
            summary(13, 'Мария Орлова', null, 1, '2026-08-01'),
          ],
          total: 3,
          limit: 100,
          offset: 0,
        },
      });
    if (path.endsWith('/coach/assigned-programs'))
      return route.fulfill({
        json: [
          {
            id: 701,
            client_id: 11,
            client_telegram_user_id: 3011,
            client_username: 'anna_runner',
            client_full_name: 'Анна Петрова',
            template_id: 17,
            title: 'Силовая база · четыре недели',
            goal: 'maintenance',
            level: 'intermediate',
            assigned_at: '2026-08-01T10:00:00',
            is_active: true,
            status: 'active',
            start_date: '2026-08-03',
            duration_weeks: 4,
            schedule_weekdays: [1, 3, 5],
            completed_at: null,
            workouts_total: 12,
            workouts_completed: 5,
            next_workout_date: '2026-08-22',
            current_revision_number: 2,
          },
        ],
      });
    if (path.endsWith('/coach/clients')) return route.fulfill({ json: clients });
    if (/\/coach\/clients\/\d+\/nutrition-report\.csv$/.test(path))
      return route.fulfill({
        body: '\ufeffrow_type,period_start,period_end\nsummary,2026-07-22,2026-08-20\n',
        contentType: 'text/csv; charset=utf-8',
        headers: { 'Content-Disposition': 'attachment; filename="nutrition-report.csv"' },
      });
    if (/\/coach\/clients\/\d+\/nutrition-report$/.test(path))
      return route.fulfill({ json: coachNutritionReport(url) });
    if (path.endsWith('/coach/clients/11/analytics'))
      return route.fulfill({
        json: {
          adherence_percent: 80,
          workouts_completed: 8,
          workouts_skipped: 1,
          workouts_missed: 1,
          current_streak: 3,
          weight_change_kg: -0.8,
          personal_records: [],
        },
      });
    if (path.endsWith('/coach/clients/11/workouts/501/comments')) {
      if (request.method() === 'POST') {
        const payload = request.postDataJSON() as {
          body: string;
          workout_exercise_id: number | null;
        };
        const created = {
          ...feedbackComments[0]!,
          id: 802,
          body: payload.body,
          workout_exercise_id: payload.workout_exercise_id,
          created_at: '2026-08-20T15:00:00',
        };
        feedbackComments.push(created);
        return route.fulfill({ status: 201, json: created });
      }
      return route.fulfill({ json: feedbackComments });
    }
    if (path.endsWith('/coach/clients/11/workouts'))
      return route.fulfill({
        json: [
          {
            id: 501,
            scheduled_date: '2026-08-19',
            scheduled_time: '18:30:00',
            title: 'Ноги и корпус',
            status: 'completed',
            completed_at: '2026-08-19T19:20:00',
            completed_sets: 4,
            volume_kg: 1480,
            exercises: [
              {
                workout_exercise_id: 551,
                exercise_id: 51,
                exercise_title: 'Присед со штангой',
                notes: 'Спокойный темп',
                superset_group: null,
                superset_order: null,
                sets: [
                  {
                    set_number: 1,
                    actual_reps: 8,
                    actual_weight: 60,
                    rir: '2',
                    set_kind: 'working',
                    reached_failure: false,
                    is_completed: true,
                  },
                ],
              },
            ],
          },
        ],
      });
    if (path.endsWith('/programs/exercises')) return route.fulfill({ json: [] });
    if (/\/programs\/assigned\/\d+\/(revisions|blocks)$/.test(path))
      return route.fulfill({ json: [] });
    if (path.endsWith('/coach/invite-links') && request.method() === 'POST')
      return route.fulfill({
        json: {
          token: 'test',
          start_param: 'coach_test',
          code: 'YFC-TEST',
          url: 'https://example.test/join/test',
          web_url: 'https://example.test/join/test',
          telegram_url: 'https://t.me/fit_bot?startapp=coach_test',
          expires_at: '2026-08-27T12:00:00',
        },
      });
    return route.fulfill({ json: [] });
  });
}

async function openCoach(page: Page) {
  await mockCoachWorkspace(page);
  await page.goto('/coach');
  await page.getByRole('button', { name: 'Тренер' }).click();
  await expect(page.getByRole('heading', { name: 'Кабинет тренера' })).toBeVisible();
}

test('dashboard даёт обзор и фильтрует клиентов без загрузки полной истории', async ({ page }) => {
  await page.setViewportSize(
    captureLandingProductProofs ? { width: 1280, height: 972 } : { width: 1440, height: 1000 },
  );
  if (captureLandingProductProofs) {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  }
  const fullHistoryRequests: string[] = [];
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (/\/coach\/clients\/\d+\/(workouts|training-analytics)$/.test(path)) {
      fullHistoryRequests.push(path);
    }
  });
  await openCoach(page);

  await expect(page.getByText('Состояние клиентской базы')).toBeVisible();
  await expect(
    page.getByLabel('Состояние клиентской базы').getByText('Тренировались за 7 дней'),
  ).toBeVisible();
  await expect(page.getByText('Борис Александрович С Очень Длинной Фамилией')).toBeVisible();
  await expect(page.getByText('Сейчас открыт клиент')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Анна Петрова', exact: true })).toBeVisible();
  await expect(page.getByText('16 учтённых дней питания за период')).toBeVisible();
  await expect(page.locator('.coach-client-program .ui-badge--success')).toHaveCSS(
    'border-radius',
    '10px',
  );
  await expect(page.locator('.coach-client-program .ui-badge--success')).toHaveCSS(
    'padding-top',
    '3px',
  );
  expect(
    (await page.locator('.coach-client-program .ui-badge--success').boundingBox())?.height,
  ).toBeLessThanOrEqual(26);
  expect(fullHistoryRequests).toEqual([]);

  if (captureTask76) {
    await page.screenshot({
      path: '../.artifacts/screenshots/task-76/coach-nutrition-coverage-desktop-light.png',
      fullPage: true,
    });
  }

  if (captureAudit) {
    await page.screenshot({
      path: '../.artifacts/ui-audit/task-48/coach-desktop-light.png',
      fullPage: true,
    });
  }
  if (captureLandingProductProofs) {
    await page.screenshot({
      path: '../.artifacts/runtime/tests/product-proofs/landing-trainer-desktop-light.png',
    });
  }

  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await expect(page.getByRole('tab', { name: 'Клиенты' })).toHaveCSS(
    'background-color',
    'rgb(20, 23, 23)',
  );
  await expect(page.getByLabel('Найти клиента')).toHaveCSS('background-color', 'rgb(20, 23, 23)');
  await expect(page.getByRole('button', { name: 'Пригласить клиента', exact: true })).toHaveCSS(
    'background-color',
    'rgb(178, 245, 32)',
  );
  if (captureAudit) {
    await page.screenshot({
      path: '../.artifacts/ui-audit/task-48/coach-desktop-dark.png',
      fullPage: true,
    });
  }
  if (captureLandingProductProofs) {
    await page.screenshot({
      path: '../.artifacts/runtime/tests/product-proofs/landing-trainer-desktop-dark.png',
    });
    return;
  }
  await page.getByRole('button', { name: 'Включить светлую тему' }).click();

  await page.getByLabel('Показать').selectOption('attention');
  const clientList = page.locator('.coach-client-list');
  await expect(clientList.getByText('Анна Петрова', { exact: true })).toHaveCount(1);
  await expect(clientList.getByText('Борис Александрович С Очень Длинной Фамилией')).toBeVisible();
  await expect(clientList.getByText('Мария Орлова')).toBeVisible();

  await page.getByLabel('Найти клиента').fill('Борис');
  await expect(clientList.getByText('Мария Орлова')).toHaveCount(0);
  await expect(clientList.getByText('Борис Александрович С Очень Длинной Фамилией')).toBeVisible();
  await page.getByLabel('Найти клиента').fill('');
  await page.getByLabel('Показать').selectOption('pending');
  await expect(page.locator('.coach-client-roster .coach-client-row')).toHaveCount(1);
  await expect(page.getByText('Елена — приглашение ожидает подтверждения')).toBeVisible();
  await page.getByRole('button', { name: 'Пригласить клиента', exact: true }).click();
  await expect(page.getByLabel('Универсальная ссылка — для браузера и Telegram')).toHaveValue(
    'https://example.test/join/test',
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(1440);
});

test('trainer nutrition report stays scoped to the active client and remains read-only', async ({
  page,
}) => {
  const reportRequests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/nutrition-report')) reportRequests.push(request.url());
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await openCoach(page);
  await page
    .getByRole('button', { name: /Анна Петрова/ })
    .first()
    .click();

  const nutrition = page.locator('#coach-client-nutrition');
  await nutrition.locator(':scope > summary').click();
  const report = nutrition.locator('#nutrition-period-report');
  await expect(report.getByRole('heading', { name: 'Отчёт по питанию' })).toBeVisible();
  await expect(report.getByText('Заполнено 1 из 30 дней')).toBeVisible();
  await expect(
    report.getByRole('table', {
      name: 'Дневные КБЖУ, статус заполнения и действовавшая цель',
    }),
  ).toBeAttached();
  await expect(report.getByRole('link', { name: /Открыть дневник/ })).toHaveCount(0);
  expect(reportRequests.some((url) => url.includes('/coach/clients/11/nutrition-report'))).toBe(
    true,
  );
  expect(reportRequests.some((url) => url.includes('/workouts/progress/nutrition-report'))).toBe(
    false,
  );

  await report.getByRole('button', { name: 'Скачать CSV' }).click();
  await expect
    .poll(() =>
      reportRequests.some((url) => url.includes('/coach/clients/11/nutrition-report.csv')),
    )
    .toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test('mobile использует список и отдельный контекст клиента', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openCoach(page);

  expect((await page.locator('.coach-workspace-header').boundingBox())?.height).toBeLessThan(190);
  await expect(page.getByRole('heading', { name: 'Анна Петрова', exact: true })).toBeHidden();
  await page.getByRole('button', { name: /Борис Александрович/ }).click();
  await expect(
    page.getByRole('heading', {
      name: 'Борис Александрович С Очень Длинной Фамилией',
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText('Сейчас открыт клиент')).toBeVisible();
  await expect(page.getByText('Цель: Набор мышц')).toBeVisible();
  await expect(page.getByRole('button', { name: 'К списку клиентов' })).toBeVisible();
  await expect(page.getByRole('tablist', { name: 'Разделы тренера' })).toBeHidden();
  const headerBox = await page.locator('.coach-workspace-header').boundingBox();
  const dashboardEyebrowBox = await page.locator('.coach-dashboard .eyebrow').boundingBox();
  expect(
    (dashboardEyebrowBox?.y ?? 0) - ((headerBox?.y ?? 0) + (headerBox?.height ?? 0)),
  ).toBeLessThanOrEqual(44);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  await page.getByText('Назначить новую программу').click();
  await expect(page.getByRole('heading', { name: 'Добавьте упражнения' })).toBeVisible();
  const trainingFields = page.locator('.program-exercise-row__metrics .field');
  await expect(trainingFields).toHaveCount(3);
  const fieldBoxes = await trainingFields.evaluateAll((fields) =>
    fields.map((field) => field.getBoundingClientRect()),
  );
  expect(fieldBoxes.every((box) => box.width >= 70)).toBe(true);
  expect(
    Math.max(...fieldBoxes.map((box) => box.top)) - Math.min(...fieldBoxes.map((box) => box.top)),
  ).toBeLessThan(2);
  const dayHeader = page.locator('.program-day__head');
  const dayInput = dayHeader.getByLabel('Название дня 1');
  const dayControls = dayHeader.locator('.program-order-controls');
  expect((await dayControls.boundingBox())?.y).toBeLessThan(
    ((await dayInput.boundingBox())?.y ?? 0) + ((await dayInput.boundingBox())?.height ?? 0),
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  const exerciseActions = page.locator('.program-exercise-row__actions').first();
  const exerciseHeading = page.locator('.program-exercise-row__heading').first();
  const exerciseAdvanced = page.locator('.program-exercise-advanced').first();
  const exerciseActionsBox = await exerciseActions.boundingBox();
  const exerciseHeadingBox = await exerciseHeading.boundingBox();
  const exerciseAdvancedBox = await exerciseAdvanced.boundingBox();
  expect(Math.abs((exerciseActionsBox?.y ?? 0) - (exerciseHeadingBox?.y ?? 0))).toBeLessThan(4);
  expect((exerciseActionsBox?.y ?? 0) < (exerciseAdvancedBox?.y ?? 0)).toBe(true);
  await expect(
    exerciseActions.getByRole('button', { name: 'Переместить упражнение 1 выше' }),
  ).toBeHidden();
  await expect(
    exerciseActions.getByRole('button', { name: 'Переместить упражнение 1 ниже' }),
  ).toBeHidden();
  await expect(exerciseAdvanced.getByText('Заметка, суперсет и замены')).toBeVisible();
  await expect(exerciseAdvanced.getByText('Необязательные настройки упражнения')).toBeVisible();
  expect(
    (
      await exerciseActions
        .getByRole('button', { name: 'Удалить упражнение 1 из дня 1' })
        .boundingBox()
    )?.height,
  ).toBeGreaterThanOrEqual(44);
  const addExercise = page.getByRole('button', { name: 'Добавить упражнение' }).first();
  await expect(addExercise).toHaveCSS('border-top-style', 'solid');
  expect((await addExercise.boundingBox())?.height).toBeGreaterThanOrEqual(44);

  for (const viewport of [
    { width: 430, height: 932 },
    { width: 360, height: 800 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
    const actionsBox = await exerciseActions.boundingBox();
    const headingBox = await exerciseHeading.boundingBox();
    expect(Math.abs((actionsBox?.y ?? 0) - (headingBox?.y ?? 0))).toBeLessThan(4);
  }

  await page.setViewportSize({ width: 1280, height: 900 });
  const desktopActionsBox = await exerciseActions.boundingBox();
  const desktopAdvancedBox = await exerciseAdvanced.boundingBox();
  expect((desktopActionsBox?.y ?? 0) < (desktopAdvancedBox?.y ?? 0)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(1280);
  await page.setViewportSize({ width: 390, height: 844 });

  if (captureAudit) {
    await page.screenshot({
      path: '../.artifacts/ui-audit/task-48/coach-mobile-program-390.png',
      fullPage: true,
    });
  }

  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.keyboard.press('Escape');
  await expect(dayInput).toHaveCSS('background-color', 'rgb(20, 23, 23)');
  await expect(dayControls.getByRole('button', { name: 'Переместить день 1 выше' })).toHaveCSS(
    'background-color',
    'rgba(0, 0, 0, 0)',
  );
  if (captureAudit) {
    await page.screenshot({
      path: '../.artifacts/ui-audit/task-48/coach-mobile-program-dark-390.png',
      fullPage: true,
    });
  }

  await page.setViewportSize({ width: 360, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
  expect(
    (
      await trainingFields.evaluateAll((fields) =>
        fields.map((field) => field.getBoundingClientRect().width),
      )
    ).every((width) => width >= 65),
  ).toBe(true);
  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить светлую тему' }).click();
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: 'К списку клиентов' }).click();
  await expect(page.getByLabel('Найти клиента')).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
  if (captureAudit) {
    await page.screenshot({
      path: '../.artifacts/ui-audit/task-48/coach-mobile-360.png',
      fullPage: true,
    });
  }
});

test('trainer leaves contextual workout and exercise feedback without messenger UI', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockCoachWorkspace(page);
  await page.goto('/coach');
  await page.getByRole('button', { name: 'Тренер' }).click();

  const rosterBox = await page.locator('.coach-client-roster').boundingBox();
  const detailBox = await page.locator('.coach-client-detail').boundingBox();
  expect(Math.abs((rosterBox?.y ?? 0) - (detailBox?.y ?? 0))).toBeLessThan(2);

  const progress = page.locator('#coach-client-progress');
  await progress.locator(':scope > summary').click();
  const workout = progress
    .locator('details.compact-disclosure')
    .filter({ hasText: 'Ноги и корпус' });
  await workout.locator(':scope > summary').click();
  const feedback = workout.locator('.workout-feedback-disclosure');
  await feedback.locator(':scope > summary').click();

  await expect(feedback.getByText('Анна Петрова · 19 августа 2026 г.')).toBeVisible();
  await expect(feedback.getByText('Хороший контроль темпа во всех подходах.')).toBeVisible();
  const desktopContextField = await feedback
    .getByRole('combobox', { name: 'Контекст комментария' })
    .locator('..')
    .boundingBox();
  const desktopCommentField = await feedback
    .getByRole('textbox', { name: 'Комментарий' })
    .locator('..')
    .boundingBox();
  expect(desktopContextField).not.toBeNull();
  expect(desktopCommentField).not.toBeNull();
  expect(Math.abs(desktopContextField!.y - desktopCommentField!.y)).toBeLessThan(2);
  await feedback.getByRole('combobox', { name: 'Контекст комментария' }).selectOption('551');
  await feedback
    .getByRole('textbox', { name: 'Комментарий' })
    .fill('Колени держите по направлению носков.');
  await expect(feedback.getByText(/\d+ из 2000/)).toBeVisible();
  await feedback.getByRole('button', { name: 'Отправить комментарий' }).click();
  await expect(feedback.getByText('Колени держите по направлению носков.')).toBeVisible();
  await expect(feedback.getByText('Упражнение · Присед со штангой')).toBeVisible();
  await expect(page.locator('[class*="chat"], [class*="bubble"]')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(1440);

  if (captureAudit) {
    await page.getByRole('button', { name: 'Закрыть сообщение' }).click();
    await feedback.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: '../.artifacts/ui-audit/task-49/trainer-feedback-desktop-light.png',
      fullPage: false,
    });
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole('button', { name: /Анна Петрова/ })
    .first()
    .click();
  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.keyboard.press('Escape');
  await expect(feedback.getByText('Колени держите по направлению носков.')).toBeVisible();
  await expect(feedback.getByRole('textbox', { name: 'Комментарий' })).toHaveCSS(
    'background-color',
    'rgb(20, 23, 23)',
  );
  const mobileContextField = await feedback
    .getByRole('combobox', { name: 'Контекст комментария' })
    .locator('..')
    .boundingBox();
  const mobileCommentField = await feedback
    .getByRole('textbox', { name: 'Комментарий' })
    .locator('..')
    .boundingBox();
  expect(mobileContextField).not.toBeNull();
  expect(mobileCommentField).not.toBeNull();
  expect(mobileCommentField!.y).toBeGreaterThan(mobileContextField!.y + mobileContextField!.height);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  if (captureAudit) {
    await page.screenshot({
      path: '../.artifacts/ui-audit/task-49/trainer-feedback-mobile-dark.png',
      fullPage: true,
    });
  }
});
