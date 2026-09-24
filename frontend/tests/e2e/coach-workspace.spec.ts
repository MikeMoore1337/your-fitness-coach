import { expect, test, type Locator, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

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
const captureTask291 =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.CAPTURE_TASK_291 === '1';
const task291EvidenceDir = (
  globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
  }
).process?.env?.TASK_291_EVIDENCE_DIR;
const task387EvidenceDir = (
  globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
  }
).process?.env?.TASK_387_EVIDENCE_DIR;
const task388EvidenceDir = (
  globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
  }
).process?.env?.TASK_388_EVIDENCE_DIR;

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
    weight_kg: 78.4,
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
      latest_measurement: measuredOn
        ? {
            measured_on: measuredOn,
            weight_kg: 68.5,
            custom_measurements:
              userId === 11
                ? [
                    {
                      definition_id: 91,
                      label: 'Талия',
                      unit: 'cm',
                      value: 86,
                      measured_on: measuredOn,
                      archived: false,
                    },
                  ]
                : [],
          }
        : null,
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

async function mockCoachWorkspace(
  page: Page,
  options: {
    attention?: 'empty' | 'actionable';
    operations?: 'empty' | 'seeded';
  } = {},
) {
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
  const operationDate = new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Moscow' });
  const seededSession = {
    id: 601,
    client_id: 11,
    client_name: 'Анна Петрова',
    starts_at: `${operationDate}T18:30:00+03:00`,
    starts_at_utc: `${operationDate}T15:30:00Z`,
    timezone: 'Europe/Moscow',
    duration_minutes: 60,
    format: 'online',
    location: 'Telegram-звонок',
    status: 'scheduled',
    private_note: null,
    package_id: 701,
    package_balance: 2,
    user_workout_id: null,
    series_id: null,
    occurrence_key: null,
    created_at: `${operationDate}T09:00:00Z`,
    updated_at: `${operationDate}T09:00:00Z`,
  };
  const seededTask = {
    id: 602,
    client_id: 12,
    client_name: 'Борис Александрович С Очень Длинной Фамилией',
    title: 'Проверить технику приседа',
    due_at: `${operationDate}T12:00:00+03:00`,
    due_at_utc: `${operationDate}T09:00:00Z`,
    timezone: 'Europe/Moscow',
    state: 'open',
    completed_at: null,
    created_at: `${operationDate}T09:00:00Z`,
    updated_at: `${operationDate}T09:00:00Z`,
  };
  const seededPackage = {
    id: 701,
    client_id: 11,
    client_name: 'Анна Петрова',
    name: 'Сопровождение · август',
    counts_sessions: true,
    included_sessions: 10,
    charged_sessions: 8,
    reversed_sessions: 0,
    balance: 2,
    starts_on: operationDate,
    expires_on: null,
    state: 'active',
    note: null,
    created_at: `${operationDate}T09:00:00Z`,
    updated_at: `${operationDate}T09:00:00Z`,
  };
  const seededPayment = {
    id: 703,
    client_id: 11,
    client_name: 'Анна Петрова',
    package_id: 701,
    expected_amount_minor: 300000,
    paid_amount_minor: 150000,
    currency: 'RUB',
    payment_date: operationDate,
    method: 'Перевод',
    note: null,
    status: 'partial',
    created_at: `${operationDate}T09:00:00Z`,
    updated_at: `${operationDate}T09:00:00Z`,
  };
  const operations =
    options.operations === 'seeded'
      ? {
          date: operationDate,
          timezone: 'Europe/Moscow',
          sessions: [seededSession],
          overdue_tasks: [seededTask],
          due_tasks: [],
          low_packages: [seededPackage],
          payment_facts: [seededPayment],
        }
      : {
          date: operationDate,
          timezone: 'Europe/Moscow',
          sessions: [],
          overdue_tasks: [],
          due_tasks: [],
          low_packages: [],
          payment_facts: [],
        };
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
    if (path.endsWith('/workouts/today'))
      return route.fulfill({ status: 404, json: { detail: 'На сегодня тренировка не назначена' } });
    if (path.endsWith('/workouts/week') || path.endsWith('/workouts/cardio'))
      return route.fulfill({ json: [] });
    if (path.endsWith('/workouts/progress/summary'))
      return route.fulfill({
        json: {
          user_id: 1,
          period_days: 30,
          period_start: '2026-08-01',
          period_end: '2026-08-30',
          training: { completed_workouts: 0, last_completed_workout_on: null, next_workout: null },
          nutrition: { visible: false },
          body: { latest_measurement: null, trends: [], priority: null, guidance: {} },
          adherence: {
            formula_version: 'adherence-v1',
            overall_percent: null,
            included_components: [],
            workouts: {},
            cardio: {},
            calories: {},
            protein: {},
          },
          data_sufficiency: {},
        },
      });
    if (path.endsWith('/nutrition/diary'))
      return route.fulfill({
        json: {
          diary_date: url.searchParams.get('diary_date') ?? '2026-08-30',
          timezone: 'Europe/Moscow',
          status: 'unlogged',
          status_is_explicit: false,
          meals: [],
          totals: {
            energy_kcal: '0',
            protein_g: '0',
            fat_g: '0',
            carbs_g: '0',
            fiber_g: null,
          },
          targets: null,
          remaining: null,
        },
      });
    if (path.endsWith('/nutrition/hydration'))
      return route.fulfill({
        json: {
          diary_date: url.searchParams.get('diary_date') ?? '2026-08-30',
          timezone: 'Europe/Moscow',
          total_ml: 0,
          goal: null,
          progress_percent: null,
          entries: [],
          presets: [],
          last_logged_at: null,
          reminder_suppression_key: null,
          action_url: '/app?section=nutrition',
        },
      });
    if (path.endsWith('/check-ins/weekly/current'))
      return route.fulfill({ json: { existing: false } });
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
    if (path.endsWith('/coach/attention'))
      return route.fulfill({
        json:
          options.attention === 'actionable'
            ? {
                items: [
                  {
                    key: 'without_program:12:12',
                    kind: 'without_program',
                    client: { id: 12, name: 'Борис Александрович С Очень Длинной Фамилией' },
                    title: 'Нужно назначить программу',
                    reason: 'У активного клиента пока нет действующей программы.',
                    source_kind: 'client',
                    source_id: 12,
                    source_state: 'without_program',
                    action: 'assign_program',
                    destination: '/coach?client_id=12',
                    created_at: '2026-08-20T10:00:00',
                  },
                ],
                total: 1,
                generated_at: '2026-08-20T10:00:00',
              }
            : { items: [], total: 0, generated_at: '2026-08-20T10:00:00' },
      });
    if (path.endsWith('/coach/operations/today')) return route.fulfill({ json: operations });
    if (path.endsWith('/coach/packages')) return route.fulfill({ json: operations.low_packages });
    if (path.endsWith('/coach/payments')) return route.fulfill({ json: operations.payment_facts });
    if (path.endsWith('/coach/tasks'))
      return route.fulfill({ json: [...operations.overdue_tasks, ...operations.due_tasks] });
    if (path.endsWith('/coach/agenda'))
      return route.fulfill({
        json: {
          date_from: url.searchParams.get('date_from') ?? '2026-08-20',
          date_to: url.searchParams.get('date_to') ?? '2026-08-26',
          timezone: 'Europe/Moscow',
          items: operations.sessions,
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
    if (/\/coach\/clients\/\d+\/operations$/.test(path))
      return route.fulfill({ json: { sessions: [], packages: [], payments: [], tasks: [] } });
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
    if (path.endsWith('/coach/clients/11/weekly-check-ins'))
      return route.fulfill({
        json: {
          items: [
            {
              id: 901,
              user_id: 11,
              week_start: '2026-08-10',
              week_end: '2026-08-16',
              submitted_on: '2026-08-17',
              timezone: 'Europe/Moscow',
              status: 'completed',
              summary_version: 'weekly-review-summary-v2',
              summary: {},
              note: 'Энергии на этой неделе было достаточно.',
              created_at: '2026-08-17T10:00:00',
            },
          ],
          total: 1,
          limit: 12,
          offset: 0,
        },
      });
    if (path.endsWith('/coach/clients/11/measurements'))
      return route.fulfill({
        json: [
          {
            id: 902,
            measured_on: '2026-08-18',
            weight_kg: 68.5,
            waist_cm: 86,
            custom_values: [
              { definition_id: 91, label: 'Талия', unit: 'cm', value: 86, archived: false },
            ],
          },
        ],
      });
    if (path.endsWith('/coach/clients/11/report-handoffs'))
      return route.fulfill({
        json: [
          {
            id: 903,
            trainer: { id: 1, full_name: 'Ирина Тренер', username: 'coach' },
            period: 'days_30',
            period_start: '2026-07-22',
            period_end: '2026-08-20',
            timezone: 'Europe/Moscow',
            report_contract_version: 'progress-report-v1',
            included_section_ids: ['overview', 'training', 'nutrition'],
            created_at: '2026-08-20T12:00:00',
            delivery_status: 'delivered',
            delivery_attempt: 1,
            client_comment: 'В целом стало легче держать план, спасибо за обратную связь.',
            live: true,
          },
        ],
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
  await trainerPrimaryNavigation(page).getByRole('link', { name: 'Клиенты', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Кабинет тренера' })).toBeVisible();
}

function trainerPrimaryNavigation(page: Page) {
  return page
    .getByRole('navigation', { name: 'Основная навигация' })
    .locator('.app-bottom-nav__primary');
}

async function captureTask291Evidence(page: Page, name: string) {
  if (!captureTask291 || !task291EvidenceDir) return;
  await page.screenshot({ path: `${task291EvidenceDir}/${name}.png`, fullPage: true });
}

async function captureTask387Evidence(page: Page, name: string) {
  if (!task387EvidenceDir) return;
  await page.screenshot({ path: `${task387EvidenceDir}/${name}.png`, fullPage: true });
}

async function captureTask388Evidence(page: Page, name: string) {
  if (!task388EvidenceDir) return;
  await page.screenshot({ path: `${task388EvidenceDir}/${name}.png`, fullPage: true });
}

async function captureTask388ViewportEvidence(page: Page, name: string) {
  if (!task388EvidenceDir) return;
  await page.screenshot({ path: `${task388EvidenceDir}/${name}.png` });
}

async function assertAboveMobileDock(page: Page, locator: Locator) {
  const targetBox = await locator.boundingBox();
  const dockBox = await page.locator('#appBottomNav').boundingBox();
  expect((targetBox?.y ?? 0) + (targetBox?.height ?? 0)).toBeLessThanOrEqual(dockBox?.y ?? 0);
}

async function assertCoachNavigationFits(page: Page, width: number) {
  await page.setViewportSize({ width, height: 844 });
  const duplicateNavigation = page.getByRole('navigation', { name: 'Разделы тренера' });
  const primaryNavigation = trainerPrimaryNavigation(page);
  const navigation = page.getByRole('navigation', { name: 'Основная навигация' });
  await expect(duplicateNavigation).toHaveCount(0);
  await expect(primaryNavigation).toBeVisible();
  await expect(primaryNavigation.getByRole('link')).toHaveCount(4);
  await expect(primaryNavigation.getByRole('link', { name: 'Ещё', exact: true })).toBeVisible();
  await expect
    .poll(() =>
      primaryNavigation
        .getByRole('link', { name: 'Ещё', exact: true })
        .evaluate((link) => (link as HTMLElement).innerText),
    )
    .toBe('Ещё');

  const geometry = await navigation.evaluate((element) => {
    const navigationRect = element.getBoundingClientRect();
    const linkRects = Array.from(element.querySelectorAll('.app-bottom-nav__primary a')).map(
      (link) => {
        const rect = link.getBoundingClientRect();
        return { left: rect.left, right: rect.right, width: rect.width };
      },
    );
    return {
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      left: navigationRect.left,
      right: navigationRect.right,
      linkRects,
    };
  });
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth);
  expect(geometry.left).toBeGreaterThanOrEqual(0);
  expect(geometry.right).toBeLessThanOrEqual(width);
  for (const link of geometry.linkRects) {
    expect(link.left).toBeGreaterThanOrEqual(geometry.left);
    expect(link.right).toBeLessThanOrEqual(geometry.right);
    expect(link.width).toBeGreaterThan(0);
  }
}

test('операционный roster даёт факты и не загружает полную историю заранее', async ({ page }) => {
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

  await expect(page.getByText('Состояние клиентской базы')).toHaveCount(0);
  await expect(page.getByText('Борис Александрович С Очень Длинной Фамилией')).toBeVisible();
  await expect(page.getByText('Сейчас открыт клиент')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Анна Петрова', exact: true })).toBeVisible();
  await page.locator('#coach-client-profile > summary').click();
  await expect(page.getByLabel('Вес, кг')).toHaveValue('78.4');
  await expect(page.getByText('16 учтённых дней питания за период')).toBeVisible();
  await page.locator('#coach-client-program > summary').click();
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
  await expect(
    trainerPrimaryNavigation(page).getByRole('link', { name: 'Клиенты', exact: true }),
  ).toHaveCSS('background-color', 'rgb(27, 31, 31)');
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
  await page.getByRole('button', { name: 'Пригласить клиента', exact: true }).first().click();
  await trainerPrimaryNavigation(page).getByRole('link', { name: 'Ещё', exact: true }).click();
  await page.getByRole('button', { name: 'Приглашения и подключения' }).click();
  await expect(page.getByLabel('Ссылка для браузера и Telegram')).toHaveValue(
    'https://example.test/join/test',
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(1440);
});

test('Task 291 показывает action-first Today и ленивый контекст клиента', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const contextRequests: string[] = [];
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (
      /\/coach\/clients\/11\/(workouts|weekly-check-ins|measurements|report-handoffs)$/.test(path)
    ) {
      contextRequests.push(path);
    }
  });
  await mockCoachWorkspace(page, { attention: 'actionable' });
  await page.goto('/coach');
  await page.getByRole('button', { name: 'Тренер' }).click();

  await expect(page.getByRole('heading', { name: 'Что требует действия?' })).toBeVisible();
  await expect(page.getByText('Нужно назначить программу')).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Разделы тренера' })).toHaveCount(0);
  await expect(
    page
      .getByRole('navigation', { name: 'Основная навигация' })
      .locator('.app-bottom-nav__primary')
      .getByRole('link'),
  ).toHaveCount(4);
  await captureTask291Evidence(page, 'today-actionable-mobile-light');

  await trainerPrimaryNavigation(page).getByRole('link', { name: 'Клиенты', exact: true }).click();
  await page.getByLabel('Показать').selectOption('pending');
  await expect(page.locator('.coach-client-roster .coach-client-row')).toHaveCount(1);
  await expect(page.getByText('Елена — приглашение ожидает подтверждения')).toBeVisible();
  await captureTask291Evidence(page, 'client-roster-mobile-pending-light');
  await page.getByLabel('Показать').selectOption('all');
  await page.getByLabel('Найти клиента').fill('Борис');
  await expect(page.getByText('Борис Александрович С Очень Длинной Фамилией')).toBeVisible();
  await expect(page.getByText('Мария Орлова')).toHaveCount(0);
  await captureTask291Evidence(page, 'client-roster-mobile-search-light');
  await page.getByLabel('Найти клиента').fill('');
  await page.getByLabel('Найти клиента').evaluate((element) => (element as HTMLElement).blur());
  await expect(page.locator('#appBottomNav')).toBeVisible();
  await trainerPrimaryNavigation(page).getByRole('link', { name: 'Сегодня', exact: true }).click();
  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('#appMorePanel')).toBeHidden();
  await captureTask291Evidence(page, 'today-actionable-mobile-dark');
  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить светлую тему' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('#appMorePanel')).toBeHidden();

  await trainerPrimaryNavigation(page).getByRole('link', { name: 'Клиенты', exact: true }).click();
  await page.getByRole('button', { name: /Анна Петрова/ }).click();
  await expect(page.getByRole('heading', { name: 'Анна Петрова', exact: true })).toBeVisible();
  expect(contextRequests).toEqual([]);
  await expect(page.getByText(/Талия: 86 cm/)).toBeVisible();
  const clientQuickActions = page.getByLabel('Данные клиента');
  await expect(clientQuickActions.getByRole('link', { name: 'Последние события' })).toBeVisible();
  await expect(clientQuickActions.getByRole('link', { name: 'Прогресс' })).toBeVisible();
  await expect(clientQuickActions.getByRole('link', { name: 'Отчёт' })).toBeVisible();

  await clientQuickActions.getByRole('link', { name: 'Последние события' }).click();
  await expect(page.getByTestId('coach-client-timeline')).toBeVisible();
  await expect(page.getByText('Тренировка завершена')).toBeVisible();
  await expect(page.getByText('Недельный итог отправлен')).toBeVisible();
  await expect(page.locator('[data-event-kind="measurement"] p')).toHaveText(
    'Вес 68.5 кг · Талия 86 см',
  );
  expect(contextRequests).toHaveLength(3);
  expect(new Set(contextRequests)).toEqual(
    new Set([
      '/api/v1/coach/clients/11/workouts',
      '/api/v1/coach/clients/11/weekly-check-ins',
      '/api/v1/coach/clients/11/measurements',
    ]),
  );
  await captureTask291Evidence(page, 'client-timeline-mobile-light');

  await clientQuickActions.getByRole('link', { name: 'Отчёт' }).click();
  const coachReportEntry = page.getByTestId('coach-report-entry');
  await expect(coachReportEntry).toBeVisible();
  await expect(coachReportEntry.getByText('Комментарий клиента')).toBeVisible();
  await expect(
    page.getByText('В целом стало легче держать план, спасибо за обратную связь.'),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Открыть расширенный отчёт' })).toHaveAttribute(
    'href',
    '/app/report?period=days_30&client_id=11',
  );
  await captureTask291Evidence(page, 'client-report-handoff-mobile-light');
  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('#appMorePanel')).toBeHidden();
  await clientQuickActions.getByRole('link', { name: 'Последние события' }).click();
  await expect(page.getByTestId('coach-client-timeline')).toBeVisible();
  await captureTask291Evidence(page, 'client-timeline-mobile-dark');
  await captureTask291Evidence(page, 'client-workspace-mobile-dark');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test('Task 291 показывает все четыре trainer destinations на узких mobile viewport', async ({
  page,
}) => {
  await mockCoachWorkspace(page, { attention: 'actionable' });
  await page.goto('/coach');
  await page.getByRole('button', { name: 'Тренер' }).click();
  await expect(page.getByRole('heading', { name: 'Что требует действия?' })).toBeVisible();

  for (const width of [320, 360, 390, 430]) {
    await assertCoachNavigationFits(page, width);
    await captureTask291Evidence(page, `trainer-navigation-${width}-light`);
  }
});

test('Stage 1 сохраняет trainer-first entry и явное переключение рабочего контекста', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockCoachWorkspace(page, { attention: 'actionable' });

  await page.goto('/app');
  await page.getByRole('button', { name: 'Тренер', exact: true }).click();
  await expect(page).toHaveURL('/coach');
  await expect(page.getByRole('heading', { name: 'Сегодня', exact: true })).toBeVisible();

  await page.goto('/app?section=nutrition');
  await expect(page).toHaveURL('/app?section=nutrition');
  await expect(page.getByRole('link', { name: 'В кабинет тренера', exact: true })).toHaveAttribute(
    'href',
    '/coach',
  );

  await page.goto('/app');
  await expect(page).toHaveURL('/coach');
  await expect(page.getByRole('navigation', { name: 'Разделы тренера' })).toHaveCount(0);
  const primaryNavigation = page.getByRole('navigation', { name: 'Основная навигация' });
  await expect(primaryNavigation.getByRole('link', { name: 'Сегодня', exact: true })).toBeVisible();
  await expect(primaryNavigation.getByRole('link', { name: 'Клиенты', exact: true })).toBeVisible();
  await expect(
    primaryNavigation.getByRole('link', { name: 'Программы', exact: true }),
  ).toBeVisible();
  await expect(primaryNavigation.getByRole('link', { name: 'Ещё', exact: true })).toBeVisible();
  await expect(primaryNavigation.getByRole('link', { name: 'Для себя', exact: true })).toHaveCount(
    0,
  );
  const mobileDockGeometry = await page.locator('#appBottomNav').evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const rootStyle = getComputedStyle(document.documentElement);
    return {
      position: getComputedStyle(element).position,
      left: rect.left,
      right: rect.right,
      bottom: rect.bottom,
      bottomInset: Number.parseFloat(getComputedStyle(element).bottom),
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      navHeight: Number.parseFloat(rootStyle.getPropertyValue('--app-bottom-nav-height')),
      bodyPaddingBottom: Number.parseFloat(getComputedStyle(document.body).paddingBottom),
    };
  });
  expect(mobileDockGeometry.position).toBe('fixed');
  expect(mobileDockGeometry.left).toBeGreaterThanOrEqual(0);
  expect(mobileDockGeometry.right).toBeLessThanOrEqual(mobileDockGeometry.viewportWidth);
  expect(mobileDockGeometry.bottomInset).toBeGreaterThan(0);
  expect(mobileDockGeometry.bottom + mobileDockGeometry.bottomInset).toBeCloseTo(
    mobileDockGeometry.viewportHeight,
    0,
  );
  expect(mobileDockGeometry.bodyPaddingBottom).toBeGreaterThanOrEqual(mobileDockGeometry.navHeight);
  await captureTask387Evidence(page, '390-light-trainer-today');

  await primaryNavigation.getByRole('link', { name: 'Программы', exact: true }).click();
  await expect(page).toHaveURL('/coach?tab=programs');
  await expect(page.getByRole('heading', { name: 'Кабинет тренера', exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Разделы тренера' })).toHaveCount(0);
  await expect(
    primaryNavigation.getByRole('link', { name: 'Программы', exact: true }),
  ).toHaveAttribute('aria-current', 'page');
  await captureTask387Evidence(page, '390-programs-trainer');

  await page.getByRole('link', { name: 'Для себя', exact: true }).click();
  await expect(page).toHaveURL(/\/app\?section=today&trainer_return=/);
  expect(new URL(page.url()).searchParams.get('trainer_return')).toBe('/coach?tab=programs');
  await expect(page.getByRole('link', { name: 'В кабинет тренера', exact: true })).toHaveAttribute(
    'href',
    '/coach?tab=programs',
  );
  await expect(
    page
      .getByRole('navigation', { name: 'Основная навигация' })
      .locator('.app-bottom-nav__primary')
      .getByRole('link', { name: 'Сегодня', exact: true }),
  ).toHaveAttribute('aria-current', 'page');
  await captureTask387Evidence(page, '390-personal-after-switch');

  await page.getByRole('link', { name: 'Питание', exact: true }).click();
  await expect(page).toHaveURL(/\/app\?section=nutrition&trainer_return=/);
  expect(new URL(page.url()).searchParams.get('trainer_return')).toBe('/coach?tab=programs');
  await page.getByRole('link', { name: 'В кабинет тренера', exact: true }).click();
  await expect(page).toHaveURL('/coach?tab=programs');

  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('#appMorePanel')).toBeHidden();
  await expect(page.getByRole('heading', { name: 'Кабинет тренера', exact: true })).toBeVisible();
  await captureTask387Evidence(page, '390-dark-trainer');

  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить светлую тему' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('#appMorePanel')).toBeHidden();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(
    page
      .getByRole('navigation', { name: 'Основная навигация' })
      .locator('.app-bottom-nav__primary')
      .getByRole('link', { name: 'Программы', exact: true }),
  ).toHaveAttribute('aria-current', 'page');
  await captureTask387Evidence(page, '1440-trainer-programs');

  await page.setViewportSize({ width: 320, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
});

test('Issue 388 оставляет Today компактным и ведёт CRM-факты в focused destinations', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockCoachWorkspace(page, { attention: 'actionable', operations: 'seeded' });
  await page.goto('/coach');
  await page.getByRole('button', { name: 'Тренер' }).click();

  await expect(page.getByRole('heading', { name: 'Сегодня', exact: true })).toBeVisible();
  await expect(page.getByTestId('coach-tools-hub')).toHaveCount(0);
  await expect(page.locator('.coach-operations__overview')).toBeVisible();
  await expect(page.locator('.coach-operations__agenda')).toHaveCount(0);
  await expect(page.getByText('Проверить технику приседа', { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  const clientsCta = page.getByRole('button', { name: /Открыть список клиентов/ });
  const clientsCard = page.locator('.coach-today__section--compact');
  await expect(clientsCta).toBeVisible();
  const clientsCtaBox = await clientsCta.boundingBox();
  const clientsCardBox = await clientsCard.boundingBox();
  expect(clientsCtaBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  expect(clientsCtaBox?.width ?? 0).toBeGreaterThanOrEqual((clientsCardBox?.width ?? 0) - 48);
  const todayInviteCta = page.getByRole('button', { name: 'Пригласить клиента', exact: true });
  await expect(todayInviteCta).toBeVisible();
  const todayInviteCtaBox = await todayInviteCta.boundingBox();
  const todayHeroBox = await page.locator('.coach-today__hero').boundingBox();
  expect(todayInviteCtaBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  expect(todayInviteCtaBox?.width ?? 0).toBeGreaterThanOrEqual((todayHeroBox?.width ?? 0) - 48);
  await todayInviteCta.scrollIntoViewIfNeeded();
  await assertAboveMobileDock(page, todayInviteCta);
  await captureTask388ViewportEvidence(page, '390-today-invite-cta');
  await clientsCta.scrollIntoViewIfNeeded();
  await captureTask388ViewportEvidence(page, '390-clients-cta-full-width');

  await captureTask388Evidence(page, '390-today-light');

  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('#appMorePanel')).toBeHidden();
  await captureTask388Evidence(page, '390-today-dark');
  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить светлую тему' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('#appMorePanel')).toBeHidden();

  const primaryNavigation = trainerPrimaryNavigation(page);
  await primaryNavigation.getByRole('link', { name: 'Ещё', exact: true }).click();
  await expect(page).toHaveURL('/coach?tab=tools');
  await expect(page.getByTestId('coach-tools-hub')).toBeVisible();
  await captureTask388Evidence(page, '390-tools-hub');

  await page.getByRole('button', { name: 'Расписание и встречи' }).click();
  await expect(page).toHaveURL('/coach?tab=tools&tool=schedule');
  await expect(page.getByRole('heading', { name: 'Встречи', exact: true })).toBeVisible();
  await expect(page.locator('.coach-operations__agenda')).toBeVisible();
  await expect(page.getByTestId('coach-session-601')).toBeVisible();
  await captureTask388Evidence(page, '390-schedule');

  await page.goBack();
  await expect(page).toHaveURL('/coach?tab=tools');
  await expect(page.getByTestId('coach-tools-hub')).toBeVisible();
  await page.goForward();
  await expect(page).toHaveURL('/coach?tab=tools&tool=schedule');
  await expect(page.getByTestId('coach-session-601')).toBeVisible();
  await primaryNavigation.getByRole('link', { name: 'Ещё', exact: true }).click();

  await page.getByRole('button', { name: 'Задачи' }).click();
  await expect(page).toHaveURL('/coach?tab=tools&tool=tasks');
  await expect(
    page.getByRole('heading', { name: 'Задачи клиентов', exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText('Проверить технику приседа', { exact: true })).toBeVisible();
  await captureTask388Evidence(page, '390-tasks');
  await primaryNavigation.getByRole('link', { name: 'Ещё', exact: true }).click();

  await page.getByRole('button', { name: 'Пакеты и оплаты' }).click();
  await expect(page).toHaveURL('/coach?tab=tools&tool=finance');
  await expect(page.getByRole('heading', { name: 'Пакеты и оплаты', exact: true })).toBeVisible();
  await expect(page.getByText(/Сопровождение · август/)).toBeVisible();
  await expect(page.getByText('Частично оплачено', { exact: true })).toBeVisible();
  const newPackageCta = page.getByRole('button', { name: 'Новый пакет', exact: true });
  const recordPaymentCta = page.getByRole('button', { name: 'Учесть оплату', exact: true });
  const newPackageBox = await newPackageCta.boundingBox();
  const recordPaymentBox = await recordPaymentCta.boundingBox();
  expect(newPackageBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  expect(recordPaymentBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  expect(recordPaymentBox?.y ?? 0).toBeGreaterThanOrEqual(
    (newPackageBox?.y ?? 0) + (newPackageBox?.height ?? 0) + 8,
  );
  await newPackageCta.scrollIntoViewIfNeeded();
  await assertAboveMobileDock(page, newPackageCta);
  await captureTask388ViewportEvidence(page, '390-finance-actions');
  await captureTask388Evidence(page, '390-finance');
  await primaryNavigation.getByRole('link', { name: 'Ещё', exact: true }).click();

  await page.getByRole('button', { name: 'Приглашения и подключения' }).click();
  const createInviteCta = page.getByRole('button', { name: 'Создать приглашение', exact: true });
  const pendingInvitesCta = page.getByRole('button', {
    name: /Открыть ожидающие подключения/,
  });
  await expect(createInviteCta).toBeVisible();
  await expect(pendingInvitesCta).toBeVisible();
  const createInviteBox = await createInviteCta.boundingBox();
  const pendingInvitesBox = await pendingInvitesCta.boundingBox();
  const inviteCardBox = await page.locator('.coach-invite-panel').boundingBox();
  expect(createInviteBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  expect(createInviteBox?.width ?? 0).toBeGreaterThanOrEqual((inviteCardBox?.width ?? 0) - 48);
  expect(pendingInvitesBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await pendingInvitesCta.scrollIntoViewIfNeeded();
  await assertAboveMobileDock(page, pendingInvitesCta);
  await captureTask388ViewportEvidence(page, '390-invitations-actions');
  await captureTask388Evidence(page, '390-invitations');

  await primaryNavigation.getByRole('link', { name: 'Клиенты', exact: true }).click();
  await expect(page.getByLabel('Найти клиента')).toBeVisible();
  await captureTask388Evidence(page, '390-clients');
  await primaryNavigation.getByRole('link', { name: 'Программы', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Программы клиентов', exact: true }),
  ).toBeVisible();
  await captureTask388Evidence(page, '390-programs');

  await primaryNavigation.getByRole('link', { name: 'Сегодня', exact: true }).click();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByRole('heading', { name: 'Сегодня', exact: true })).toBeVisible();
  await expect(page.locator('.coach-operations__agenda')).toHaveCount(0);
  await captureTask388Evidence(page, '1440-today-light');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(1440);
});

test('Task 291 сохраняет плотную desktop-композицию и Light/Dark контраст', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockCoachWorkspace(page, { attention: 'actionable' });
  await page.goto('/coach');
  await page.getByRole('button', { name: 'Тренер' }).click();
  await expect(page.getByRole('heading', { name: 'Что требует действия?' })).toBeVisible();
  await captureTask291Evidence(page, 'today-actionable-desktop-light');
  await page.setViewportSize({ width: 1280, height: 900 });
  await captureTask291Evidence(page, 'today-actionable-desktop-1280-light');
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await captureTask291Evidence(page, 'today-actionable-desktop-dark');
  await page.getByRole('button', { name: 'Включить светлую тему' }).click();

  await trainerPrimaryNavigation(page).getByRole('link', { name: 'Клиенты', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Анна Петрова', exact: true })).toBeVisible();
  await captureTask291Evidence(page, 'client-workspace-desktop-light');
  await page.getByLabel('Данные клиента').getByRole('link', { name: 'Последние события' }).click();
  await expect(page.getByTestId('coach-client-timeline')).toBeVisible();
  await captureTask291Evidence(page, 'client-timeline-desktop-light');
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await captureTask291Evidence(page, 'client-workspace-desktop-dark');
  await page.getByRole('button', { name: 'Включить светлую тему' }).click();

  for (const width of [320, 360, 390, 430]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
  }
});

test('Task 291 спокойно показывает отсутствие срочных действий', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockCoachWorkspace(page);
  await page.goto('/coach');
  await page.getByRole('button', { name: 'Тренер' }).click();
  await expect(page.getByRole('heading', { name: 'Что требует действия?' })).toBeVisible();
  await expect(page.getByText('Срочных действий нет')).toBeVisible();
  await expect(
    page.getByText('Здесь появятся только конкретные новые состояния клиента.'),
  ).toBeVisible();
  await captureTask291Evidence(page, 'today-no-attention-mobile-light');
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

  expect((await page.locator('.coach-os-header').boundingBox())?.height).toBeLessThan(210);
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
  await expect(page.getByRole('navigation', { name: 'Разделы тренера' })).toHaveCount(0);
  const headerBox = await page.locator('.coach-os-header').boundingBox();
  const detailHeaderBox = await page.locator('.coach-client-detail__header').boundingBox();
  expect(
    (detailHeaderBox?.y ?? 0) - ((headerBox?.y ?? 0) + (headerBox?.height ?? 0)),
  ).toBeGreaterThanOrEqual(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  await page.locator('#coach-client-program > summary').click();
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
  await trainerPrimaryNavigation(page).getByRole('link', { name: 'Клиенты', exact: true }).click();

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

test('Coach Programs keeps responsive geometry content-driven', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await page.setViewportSize({ width: 390, height: 844 });
  await openCoach(page);
  await trainerPrimaryNavigation(page)
    .getByRole('link', { name: 'Программы', exact: true })
    .click();

  const card = page.locator('.coach-programs-card');
  await card.locator(':scope > summary').click();
  const searchField = card.locator('.coach-programs-search');
  const searchInput = card.locator('input[type="search"]');
  await expect(card.locator('.card-disclosure__header-action')).toHaveCount(0);
  await expect(card.locator('.card-disclosure__actions')).toHaveCount(0);
  await expect(card.getByRole('link', { name: 'Мой план →', exact: true })).toHaveCount(0);
  await expect(card.getByText('Мои программы', { exact: true })).toHaveCount(0);
  await expect(
    card.getByText(
      'Здесь только назначения вашим клиентам. Собственные программы хранятся в личном плане.',
      { exact: true },
    ),
  ).toHaveCount(0);
  await expect(card.locator(':scope > summary small')).toHaveCount(0);
  await expect(card.getByText('Поиск', { exact: true })).toHaveCount(0);
  await expect(searchField).toBeVisible();
  await expect(searchInput).toHaveAttribute('placeholder', 'Поиск по клиенту или программе');
  await expect(searchField.locator('[data-icon="search"]')).toBeVisible();
  await expect(card.locator('.card-disclosure__body > :first-child')).toHaveClass(
    /coach-programs-search/,
  );
  await expect(card.getByText('Тренировочные блоки ещё не настроены')).toBeVisible();

  const measureGeometry = async () =>
    page.evaluate(() => {
      const box = (selector: string) => {
        const element = document.querySelector<HTMLElement>(selector);
        if (!element) throw new Error(`Missing geometry target: ${selector}`);
        const rect = element.getBoundingClientRect();
        return {
          top: rect.top,
          bottom: rect.bottom,
          left: rect.left,
          right: rect.right,
          width: rect.width,
          height: rect.height,
        };
      };
      const body = box('.coach-programs-card .card-disclosure__body');
      const bodyStyles = getComputedStyle(
        document.querySelector<HTMLElement>('.coach-programs-card .card-disclosure__body')!,
      );
      const header = box('.coach-os-header');
      const headerElement = document.querySelector<HTMLElement>('.coach-os-header')!;
      const headerStyles = getComputedStyle(headerElement);
      const headerContent = {
        left: header.left + Number.parseFloat(headerStyles.paddingLeft),
        right: header.right - Number.parseFloat(headerStyles.paddingRight),
      };
      const summary = box('.coach-programs-card > summary');
      const summaryCopy = box('.coach-programs-card > summary > span:first-child');
      const heading = box('.coach-programs-card > summary h2');
      const collapse = box('.coach-programs-card > summary .disclosure-icon');
      const summaryStyles = getComputedStyle(
        document.querySelector<HTMLElement>('.coach-programs-card > summary')!,
      );
      const headingStyles = getComputedStyle(
        document.querySelector<HTMLElement>('.coach-programs-card > summary h2')!,
      );
      const searchField = box('.coach-programs-card .coach-programs-search');
      const searchInput = box('.coach-programs-card input[type="search"]');
      const searchIcon = box('.coach-programs-card .coach-programs-search [data-icon="search"]');
      const programsDivider = box('.coach-programs-card .list-grid');
      const programRow = box('.coach-program-row');
      const evolution = box('.program-history');
      const evolutionIntro = box('.program-history__intro');
      const evolutionEmpty = box('.program-history .empty-state');
      const evolutionSummary = box('.program-history__disclosure > summary');
      const invite = box('.coach-os-header__actions > button');

      return {
        viewportWidth: window.innerWidth,
        dividerBottom: body.top + Number.parseFloat(bodyStyles.borderTopWidth),
        summary,
        summaryCopy,
        heading,
        collapse,
        summaryGap: Number.parseFloat(summaryStyles.gap),
        headingLineHeight: Number.parseFloat(headingStyles.lineHeight),
        searchField,
        searchInput,
        searchIcon,
        programsDivider,
        programRow,
        evolution,
        evolutionIntro,
        evolutionEmpty,
        evolutionSummary,
        invite,
        headerContent,
        documentScrollWidth: document.documentElement.scrollWidth,
      };
    });

  const assertGeometry = (geometry: Awaited<ReturnType<typeof measureGeometry>>) => {
    expect(geometry.documentScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth);
    expect(geometry.heading.left).toBeGreaterThanOrEqual(geometry.summary.left);
    expect(geometry.heading.right).toBeLessThanOrEqual(
      geometry.collapse.left - geometry.summaryGap + 1,
    );
    expect(geometry.collapse.left).toBeGreaterThanOrEqual(geometry.summary.left);
    expect(geometry.collapse.right).toBeLessThanOrEqual(geometry.summary.right);
    if (geometry.viewportWidth <= 430) {
      expect(geometry.heading.height).toBeLessThanOrEqual(geometry.headingLineHeight + 1);
    }
    expect(geometry.searchField.top - geometry.dividerBottom).toBeGreaterThanOrEqual(8);
    expect(geometry.searchField.top - geometry.dividerBottom).toBeLessThanOrEqual(24);
    expect(Math.abs(geometry.searchField.top - geometry.searchInput.top)).toBeLessThanOrEqual(1);
    expect(Math.abs(geometry.searchField.height - geometry.searchInput.height)).toBeLessThanOrEqual(
      1,
    );
    expect(
      Math.abs(
        geometry.searchIcon.top +
          geometry.searchIcon.height / 2 -
          (geometry.searchInput.top + geometry.searchInput.height / 2),
      ),
    ).toBeLessThanOrEqual(1);
    expect(geometry.programsDivider.top - geometry.searchField.bottom).toBeGreaterThanOrEqual(8);
    expect(geometry.programsDivider.top - geometry.searchField.bottom).toBeLessThanOrEqual(24);
    expect(Math.abs(geometry.programsDivider.top - geometry.programRow.top)).toBeLessThanOrEqual(1);

    for (const target of [
      geometry.evolution,
      geometry.evolutionIntro,
      geometry.evolutionEmpty,
      geometry.evolutionSummary,
    ]) {
      expect(Math.abs(target.left - geometry.programRow.left)).toBeLessThanOrEqual(1);
      expect(Math.abs(target.right - geometry.programRow.right)).toBeLessThanOrEqual(1);
    }

    if (geometry.viewportWidth <= 640) {
      expect(Math.abs(geometry.invite.left - geometry.headerContent.left)).toBeLessThanOrEqual(1);
      expect(Math.abs(geometry.invite.right - geometry.headerContent.right)).toBeLessThanOrEqual(1);
    } else {
      expect(geometry.invite.left).toBeGreaterThanOrEqual(geometry.headerContent.left);
      expect(geometry.invite.right).toBeLessThanOrEqual(geometry.headerContent.right);
    }
  };

  const widths = [320, 360, 390, 430, 768, 1280, 1440];
  const measurements: Array<Record<string, number | string>> = [];
  for (const width of widths) {
    await page.setViewportSize({ width, height: 1000 });
    const geometry = await measureGeometry();
    assertGeometry(geometry);
    measurements.push({
      theme: 'light',
      width,
      dividerBottom: geometry.dividerBottom,
      headingHeight: geometry.heading.height,
      collapseWidth: geometry.collapse.width,
      searchFieldTop: geometry.searchField.top,
      searchFieldBottom: geometry.searchField.bottom,
      dividerToSearch: geometry.searchField.top - geometry.dividerBottom,
      searchToProgramsDivider: geometry.programsDivider.top - geometry.searchField.bottom,
      searchInputTop: geometry.searchInput.top,
      evolutionWidth: geometry.evolution.width,
      parentWidth: geometry.programRow.width,
      evolutionEmptyWidth: geometry.evolutionEmpty.width,
      evolutionSummaryWidth: geometry.evolutionSummary.width,
      inviteWidth: geometry.invite.width,
      pageScrollWidth: geometry.documentScrollWidth,
    });
  }

  await page.setViewportSize({ width: 320, height: 844 });
  await page.screenshot({
    path: '../.artifacts/tasks/375/evidence/screenshots/coach-programs-320-light.png',
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: '../.artifacts/tasks/375/evidence/screenshots/coach-programs-390-light.png',
    fullPage: true,
  });

  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('#appMorePanel')).toBeHidden();
  for (const width of widths) {
    await page.setViewportSize({ width, height: 1000 });
    const geometry = await measureGeometry();
    assertGeometry(geometry);
    measurements.push({
      theme: 'dark',
      width,
      dividerBottom: geometry.dividerBottom,
      headingHeight: geometry.heading.height,
      collapseWidth: geometry.collapse.width,
      searchFieldTop: geometry.searchField.top,
      searchFieldBottom: geometry.searchField.bottom,
      dividerToSearch: geometry.searchField.top - geometry.dividerBottom,
      searchToProgramsDivider: geometry.programsDivider.top - geometry.searchField.bottom,
      searchInputTop: geometry.searchInput.top,
      evolutionWidth: geometry.evolution.width,
      parentWidth: geometry.programRow.width,
      evolutionEmptyWidth: geometry.evolutionEmpty.width,
      evolutionSummaryWidth: geometry.evolutionSummary.width,
      inviteWidth: geometry.invite.width,
      pageScrollWidth: geometry.documentScrollWidth,
    });
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: '../.artifacts/tasks/375/evidence/screenshots/coach-programs-390-dark.png',
    fullPage: true,
  });

  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить светлую тему' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('#appMorePanel')).toBeHidden();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: '../.artifacts/tasks/375/evidence/screenshots/coach-programs-1440-light.png',
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await card.locator('input[type="search"]').fill('несуществующая программа');
  await expect(card.getByText('Назначений не найдено', { exact: true })).toBeVisible();
  await card.locator('input[type="search"]').fill('');
  await expect(card.locator('.coach-program-row')).toBeVisible();
  await card.locator(':scope > summary').click();
  await expect(card.locator('.card-disclosure__body')).toBeHidden();
  await card.locator(':scope > summary').click();
  await expect(card.locator('.card-disclosure__body')).toBeVisible();

  console.log(`COACH_PROGRAMS_GEOMETRY ${JSON.stringify(measurements)}`);
});
