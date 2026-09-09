import { expect, test, type Page } from '@playwright/test';
import { emptyHydrationDay } from './fixtures/platform-api';
import { progressOverview } from './fixtures/locators';

const captureFeedbackAudit = Boolean(
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.CAPTURE_FEEDBACK_AUDIT,
);

const signal = (
  status: 'sufficient' | 'limited' | 'insufficient',
  counters: Record<string, number> = {},
  reasonKeys: string[] = status === 'sufficient' ? ['thresholds_met'] : ['too_few_points'],
) => ({
  status,
  counters,
  reason_keys: reasonKeys,
});

type NutritionReportState = 'partial' | 'no-data' | 'long';

function shiftDate(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function nutritionReportFixture(url: URL, state: NutritionReportState) {
  const period = url.searchParams.get('period') ?? 'days_30';
  let periodEnd = '2030-01-30';
  let periodStart = shiftDate(
    periodEnd,
    period === 'days_7' ? -6 : period === 'days_90' ? -89 : -29,
  );
  if (period === 'current_week') periodStart = '2030-01-28';
  if (period === 'current_month') periodStart = '2030-01-01';
  if (period === 'previous_month') {
    periodStart = '2029-12-01';
    periodEnd = '2029-12-31';
  }
  if (period === 'custom') {
    periodStart = url.searchParams.get('date_from') ?? periodStart;
    periodEnd = url.searchParams.get('date_to') ?? periodEnd;
  }
  const dayCount =
    Math.round(
      (Date.parse(`${periodEnd}T12:00:00Z`) - Date.parse(`${periodStart}T12:00:00Z`)) / 86_400_000,
    ) + 1;
  const targetChangeDate = shiftDate(
    periodStart,
    Math.min(Math.max(1, Math.floor(dayCount * 0.45)), dayCount - 1),
  );
  const daily = Array.from({ length: dayCount }, (_, index) => {
    const diaryDate = shiftDate(periodStart, index);
    const targetCalories = diaryDate < targetChangeDate ? 2100 : 1950;
    const targetProtein = diaryDate < targetChangeDate ? 140 : 135;
    const targetFat = diaryDate < targetChangeDate ? 70 : 65;
    const targetCarbs = diaryDate < targetChangeDate ? 230 : 210;
    const status =
      state === 'no-data'
        ? 'missing'
        : index === dayCount - 1
          ? 'incomplete'
          : index === dayCount - 3
            ? 'fasted'
            : index % (state === 'long' ? 6 : 4) === 0
              ? 'complete'
              : 'missing';
    const logged = status === 'complete' || status === 'fasted';
    const calories =
      status === 'fasted'
        ? 0
        : status === 'complete'
          ? 2020 + (index % 5) * 35
          : status === 'incomplete'
            ? 760
            : null;
    const protein =
      status === 'fasted'
        ? 0
        : status === 'complete'
          ? 138 + (index % 4) * 3
          : status === 'incomplete'
            ? 52
            : null;
    const fat =
      status === 'fasted'
        ? 0
        : status === 'complete'
          ? 64 + (index % 4) * 2
          : status === 'incomplete'
            ? 24
            : null;
    const carbs =
      status === 'fasted'
        ? 0
        : status === 'complete'
          ? 205 + (index % 4) * 4
          : status === 'incomplete'
            ? 85
            : null;
    return {
      diary_date: diaryDate,
      status,
      is_current_day: diaryDate === '2030-01-30',
      calories,
      protein_g: protein,
      fat_g: fat,
      carbs_g: carbs,
      target_calories: targetCalories,
      target_protein_g: targetProtein,
      target_fat_g: targetFat,
      target_carbs_g: targetCarbs,
      calorie_deviation: logged && calories != null ? calories - targetCalories : null,
      protein_deviation_g: logged && protein != null ? protein - targetProtein : null,
      fat_deviation_g: logged && fat != null ? fat - targetFat : null,
      carbs_deviation_g: logged && carbs != null ? carbs - targetCarbs : null,
      within_calorie_tolerance:
        logged && calories != null
          ? Math.abs(calories - targetCalories) <= targetCalories * 0.1
          : null,
      meets_protein_target: logged && protein != null ? protein >= targetProtein : null,
      target_changed: state !== 'no-data' && diaryDate === targetChangeDate,
    };
  });
  const logged = daily.filter((point) => point.status === 'complete' || point.status === 'fasted');
  const values = (key: 'calories' | 'protein_g' | 'fat_g' | 'carbs_g') =>
    logged.map((point) => point[key] as number);
  const metric = (key: 'calories' | 'protein_g' | 'fat_g' | 'carbs_g') => {
    const items = values(key);
    return items.length
      ? {
          average: items.reduce((sum, value) => sum + value, 0) / items.length,
          minimum: Math.min(...items),
          maximum: Math.max(...items),
          sample_days: items.length,
        }
      : { average: null, minimum: null, maximum: null, sample_days: 0 };
  };
  const comparison = (
    actualKey: 'calories' | 'protein_g' | 'fat_g' | 'carbs_g',
    targetKey: 'target_calories' | 'target_protein_g' | 'target_fat_g' | 'target_carbs_g',
  ) => {
    if (!logged.length)
      return {
        average_actual: null,
        average_target: null,
        average_deviation: null,
        evaluated_days: 0,
      };
    const actual =
      logged.reduce((sum, point) => sum + (point[actualKey] as number), 0) / logged.length;
    const target =
      logged.reduce((sum, point) => sum + (point[targetKey] as number), 0) / logged.length;
    return {
      average_actual: actual,
      average_target: target,
      average_deviation: actual - target,
      evaluated_days: logged.length,
    };
  };
  return {
    period,
    period_start: periodStart,
    period_end: periodEnd,
    timezone: 'Europe/Moscow',
    summary: {
      logged_days: logged.length,
      eligible_days: daily.length,
      coverage_percent: Math.round((logged.length * 1000) / daily.length) / 10,
      complete_days: daily.filter((point) => point.status === 'complete').length,
      incomplete_days: daily.filter((point) => point.status === 'incomplete').length,
      fasted_days: daily.filter((point) => point.status === 'fasted').length,
      missing_days: daily.filter((point) => point.status === 'missing').length,
      current_day_status: daily.find((point) => point.is_current_day)?.status ?? null,
      calories: metric('calories'),
      protein_g: metric('protein_g'),
      fat_g: metric('fat_g'),
      carbs_g: metric('carbs_g'),
      calorie_comparison: comparison('calories', 'target_calories'),
      protein_comparison: comparison('protein_g', 'target_protein_g'),
      fat_comparison: comparison('fat_g', 'target_fat_g'),
      carbs_comparison: comparison('carbs_g', 'target_carbs_g'),
      days_within_calorie_tolerance: logged.filter((point) => point.within_calorie_tolerance)
        .length,
      calorie_tolerance_evaluated_days: logged.length,
      days_meeting_protein_target: logged.filter((point) => point.meets_protein_target).length,
      protein_target_evaluated_days: logged.length,
    },
    daily,
    target_changes:
      state === 'no-data'
        ? []
        : [
            {
              effective_from: targetChangeDate,
              source: 'adaptive',
              calories: 1950,
              protein_g: 135,
              fat_g: 65,
              carbs_g: 210,
            },
          ],
  };
}

async function mockProgress(page: Page, reportState: NutritionReportState = 'partial') {
  const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Moscow' });
  const previousDate = shiftDate(today, -7);
  let measurements: Array<{
    id: number;
    measured_on: string;
    weight_kg: number | null;
    chest_cm: number | null;
    waist_cm: number | null;
    hips_cm: number | null;
    biceps_cm: number | null;
    thigh_cm: number | null;
    note: string | null;
  }> = [
    {
      id: 1,
      measured_on: previousDate,
      weight_kg: 69.1,
      chest_cm: null,
      waist_cm: 72.5,
      hips_cm: null,
      biceps_cm: null,
      thigh_cm: null,
      note: 'Утром до завтрака',
    },
  ];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const period = Number(url.searchParams.get('period_days')) || 30;
    if (path.endsWith('/public/config')) {
      return route.fulfill({
        json: { app_env: 'dev', enable_dev_auth: true, telegram_bot_username: '' },
      });
    }
    if (path.endsWith('/auth/refresh')) {
      return route.fulfill({ status: 401, json: { detail: 'No refresh cookie' } });
    }
    if (path.endsWith('/auth/dev-login')) {
      return route.fulfill({ json: { access_token: 'test-token', token_type: 'bearer' } });
    }
    if (path.endsWith('/me')) {
      return route.fulfill({
        json: {
          id: 7,
          first_name: 'Анна',
          is_coach: false,
          is_admin: false,
          has_active_program: true,
          has_workout_history: true,
          onboarding: { status: 'complete', required_fields: [], missing_fields: [] },
          profile: { full_name: 'Анна Петрова', timezone: 'Europe/Moscow', kbju: null },
          trainer: { id: 70 },
        },
      });
    }
    if (path.endsWith('/workouts/today')) {
      return route.fulfill({ status: 404, json: { detail: 'На сегодня тренировка не назначена' } });
    }
    if (path.endsWith('/nutrition/hydration')) {
      return route.fulfill({
        json: emptyHydrationDay(url.searchParams.get('diary_date') || '2030-01-30'),
      });
    }
    if (path.endsWith('/nutrition/diary')) {
      return route.fulfill({
        json: {
          diary_date: url.searchParams.get('diary_date') || '2030-01-30',
          timezone: 'Europe/Moscow',
          meals: [],
          status: 'unlogged',
          status_is_explicit: false,
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
    }
    if (path.endsWith('/workouts/progress/summary')) {
      return route.fulfill({
        json: {
          user_id: 7,
          period_days: period,
          period_start: '2030-01-01',
          period_end: '2030-01-30',
          training: {
            planned_workouts: 8,
            completed_workouts: 7,
            frequency_per_week: 1.63,
            volume_kg: 12400,
            new_personal_records: 2,
            last_completed_workout_on: '2030-01-28',
            next_workout: null,
          },
          nutrition: {
            visible: true,
            logged_days: 20,
            adherence_evaluated_days: 18,
            complete_days: 18,
            incomplete_days: 2,
            fasted_days: 0,
            unlogged_days: 10,
            average_calories: 1980,
            target_calories: 2100,
            average_protein_g: 132,
            target_protein_g: 140,
            target_effective_on: '2029-12-01',
          },
          body: {
            latest_measurement: { measured_on: '2030-01-29', weight_kg: 68.4, waist_cm: 72 },
            trends: [
              {
                metric: 'weight_kg',
                first_value: 69.4,
                latest_value: 68.4,
                change: -1,
                first_measured_on: '2030-01-02',
                latest_measured_on: '2030-01-29',
                point_count: 4,
                span_days: 27,
                interpretation_status: 'available',
                points: [
                  { measured_on: '2030-01-02', value: 69.4 },
                  { measured_on: '2030-01-05', value: 69.1 },
                  { measured_on: '2030-01-22', value: 68.8 },
                  { measured_on: '2030-01-29', value: 68.4 },
                ],
              },
              {
                metric: 'waist_cm',
                first_value: 73,
                latest_value: 72,
                change: -1,
                first_measured_on: '2030-01-02',
                latest_measured_on: '2030-01-29',
                point_count: 2,
                span_days: 27,
                interpretation_status: 'insufficient_points',
                points: [
                  { measured_on: '2030-01-02', value: 73 },
                  { measured_on: '2030-01-29', value: 72 },
                ],
              },
            ],
            priority: {
              mode: 'muscle_groups',
              muscle_group_ids: ['back', 'posterior_chain'],
            },
            guidance: {
              comparison_basis: 'self',
              minimum_points_for_interpretation: 3,
              minimum_span_days_for_interpretation: 14,
              consistency_tips: ['Снимайте замеры в похожее время суток и в одинаковых условиях.'],
              circumference_limitations: [
                'Окружность плеча не измеряет отдельно бицепс или трицепс.',
              ],
            },
          },
          cardio: {
            completed_sessions: 3,
            planned_sessions: 0,
            frequency_per_week: 0.7,
            duration_minutes: 120,
            distance_km: 12,
            zone_duration: [],
          },
          adherence: {
            formula_version: 'adherence-v1',
            overall_percent: 84,
            included_components: ['workouts', 'calories', 'protein'],
            workouts: {
              status: 'available',
              percent: 87.5,
              achieved: 7,
              evaluated: 8,
              weight: 0.4,
            },
            cardio: {
              status: 'unsupported',
              percent: null,
              achieved: 0,
              evaluated: 0,
              weight: 0.2,
            },
            calories: {
              status: 'available',
              percent: 83.3,
              achieved: 15,
              evaluated: 18,
              weight: 0.2,
            },
            protein: {
              status: 'available',
              percent: 72.2,
              achieved: 13,
              evaluated: 18,
              weight: 0.2,
            },
          },
          data_sufficiency: {
            ruleset_version: 'data-sufficiency-v1',
            workout_logging: signal('sufficient', {
              completed_workout_count: 7,
              prescribed_set_count: 28,
              logged_set_count: 28,
              coverage_percent: 100,
            }),
            working_sets: signal('sufficient', {
              workout_session_count: 7,
              working_set_count: 28,
              required_workout_session_count: 2,
              required_working_set_count: 6,
            }),
            rir_coverage: signal('limited', {
              working_set_count: 28,
              recorded_set_count: 16,
              required_recorded_set_count: 3,
              coverage_percent: 57.1,
              required_coverage_percent: 50,
            }),
            nutrition_coverage: signal('sufficient', {
              logged_day_count: 20,
              eligible_day_count: 29,
              required_logged_day_count: 7,
              coverage_percent: 69,
            }),
            weight_trend: signal('sufficient', {
              point_count: 4,
              span_days: 27,
              required_point_count: 3,
              required_span_days: 14,
            }),
            anthropometry: signal(
              'limited',
              {
                measured_metric_count: 1,
                sufficient_metric_count: 0,
                maximum_point_count: 2,
                maximum_span_days: 27,
                required_point_count_per_metric: 3,
                required_span_days_per_metric: 14,
              },
              ['too_few_points'],
            ),
            schedule_adherence: signal('sufficient', {
              evaluable_workout_count: 8,
              required_evaluable_workout_count: 3,
            }),
          },
        },
      });
    }
    if (path.endsWith('/workouts/progress/nutrition-report')) {
      return route.fulfill({ json: nutritionReportFixture(url, reportState) });
    }
    if (path.endsWith('/workouts/progress/nutrition-report.csv')) {
      return route.fulfill({
        body: '\ufeffrow_type,period_start,period_end\nsummary,2030-01-01,2030-01-30\n',
        contentType: 'text/csv; charset=utf-8',
        headers: { 'Content-Disposition': 'attachment; filename="nutrition-report.csv"' },
      });
    }
    if (path.endsWith('/workouts/progress/training-analytics')) {
      return route.fulfill({
        json: {
          period_days: period,
          period_start: '2030-01-01',
          period_end: '2030-01-30',
          exercise_history_limit: 20,
          completed_set_count: 28,
          reps_total: 226,
          reps_recorded_sets: 28,
          external_load_volume_kg: 12400,
          volume_recorded_sets: 24,
          exercises: [
            {
              exercise_id: 11,
              exercise_title: 'Жим штанги лёжа',
              uses_bodyweight_equipment: false,
              performed_session_count: 6,
              completed_set_count: 18,
              first_performed_on: '2030-01-03',
              last_performed_on: '2030-01-28',
              reps_total: 144,
              reps_recorded_sets: 18,
              max_external_load_kg: 62.5,
              best_set_volume_kg: 500,
              external_load_volume_kg: 7200,
              volume_recorded_sets: 18,
              history_truncated: false,
              sessions: [
                {
                  workout_id: 42,
                  workout_exercise_id: 101,
                  performed_on: '2030-01-28',
                  completed_set_count: 2,
                  reps_total: 16,
                  reps_recorded_sets: 2,
                  max_external_load_kg: 62.5,
                  external_load_volume_kg: 980,
                  volume_recorded_sets: 2,
                  sets: [
                    {
                      set_number: 1,
                      reps: 8,
                      external_load_kg: 60,
                      external_load_volume_kg: 480,
                      rir: '2',
                      set_kind: 'working',
                      reached_failure: false,
                    },
                    {
                      set_number: 2,
                      reps: 8,
                      external_load_kg: 62.5,
                      external_load_volume_kg: 500,
                      rir: null,
                      set_kind: 'working',
                      reached_failure: false,
                    },
                  ],
                },
              ],
            },
          ],
          rir: {
            completed_set_count: 28,
            recorded_set_count: 16,
            missing_set_count: 12,
            distribution: [],
          },
          primary_muscle_exposure: [
            { muscle_id: 'chest', muscle_name: 'Грудные', completed_set_count: 18 },
          ],
          secondary_muscle_exposure: [
            { muscle_id: 'triceps', muscle_name: 'Трицепс', completed_set_count: 18 },
          ],
          completed_sets_without_muscle_metadata: 0,
          data_sufficiency: {
            ruleset_version: 'data-sufficiency-v1',
            workout_logging: signal('sufficient', {
              completed_workout_count: 7,
              prescribed_set_count: 28,
              logged_set_count: 28,
              coverage_percent: 100,
            }),
            working_sets: signal('sufficient', {
              workout_session_count: 7,
              working_set_count: 28,
              required_workout_session_count: 2,
              required_working_set_count: 6,
            }),
            rir_coverage: signal('limited', {
              working_set_count: 28,
              recorded_set_count: 16,
              required_recorded_set_count: 3,
              coverage_percent: 57.1,
              required_coverage_percent: 50,
            }),
          },
        },
      });
    }
    if (path.endsWith('/me/profile/body-priority-options')) {
      return route.fulfill({
        json: {
          items: [
            { id: 'back', name: 'Мышцы спины' },
            { id: 'posterior_chain', name: 'Задняя поверхность тела и ягодичные мышцы' },
          ],
        },
      });
    }
    if (path.endsWith('/workouts/diary') && request.method() === 'GET') {
      return route.fulfill({ json: measurements });
    }
    if (path.endsWith('/workouts/diary') && request.method() === 'POST') {
      const body = request.postDataJSON() as Record<string, unknown> & { measured_on: string };
      const existing = measurements.find((item) => item.measured_on === body.measured_on);
      const saved = {
        id: existing?.id ?? measurements.length + 1,
        weight_kg: null,
        chest_cm: null,
        waist_cm: null,
        hips_cm: null,
        biceps_cm: null,
        thigh_cm: null,
        note: null,
        ...existing,
        ...body,
      };
      measurements = [saved, ...measurements.filter((item) => item.id !== saved.id)];
      return route.fulfill({ json: saved });
    }
    if (/\/workouts\/diary\/\d+$/.test(path) && request.method() === 'DELETE') {
      const id = Number(path.split('/').at(-1));
      measurements = measurements.filter((item) => item.id !== id);
      return route.fulfill({ status: 204, body: '' });
    }
    if (path.endsWith('/check-ins/weekly/current')) {
      return route.fulfill({
        json: {
          week_start: '2030-01-28',
          week_end: '2030-02-03',
          submitted_on: '2030-01-30',
          timezone: 'Europe/Moscow',
          existing: {
            id: 1,
            status: 'completed',
            note: null,
            summary: { adaptive_energy: null },
          },
          summary: {
            ruleset_version: 'weekly-review-summary-v2',
            period_start: '2030-01-28',
            period_end: '2030-02-03',
            goal: 'maintenance',
            training: { planned_workouts: 2, completed_workouts: 2, adherence: {} },
            nutrition: {
              logged_days: 3,
              complete_days: 2,
              incomplete_days: 1,
              fasted_days: 0,
              unlogged_days: 4,
              average_calories: 1980,
              target_calories: 2100,
              average_protein_g: 132,
              target_protein_g: 140,
              calories_adherence: {},
              protein_adherence: {},
              current_target: {
                effective_from: '2030-01-01',
                source: 'manual',
                calories: 2100,
                protein_g: 140,
                fat_g: 70,
                carbs_g: 230,
              },
              suspicious_low_days: [],
            },
            progression: { new_personal_records: 1 },
            weight_trend: null,
            anthropometry_trends: [],
            body_priority: null,
            data_sufficiency: {
              weight_trend: {
                status: 'insufficient',
                counters: { point_count: 0 },
                reason_keys: ['no_measurements'],
              },
            },
            adaptive_energy: null,
          },
        },
      });
    }
    if (path.endsWith('/check-ins/weekly')) {
      return route.fulfill({ json: { items: [], total: 0, limit: 4, offset: 0 } });
    }
    if (path.endsWith('/workouts/week')) {
      return route.fulfill({
        json: [
          {
            id: 43,
            scheduled_date: '2030-01-28',
            scheduled_time: '18:30:00',
            title: 'Ноги и корпус',
            status: 'completed',
            day_number: 2,
            week_number: 4,
          },
        ],
      });
    }
    if (path.endsWith('/workouts/schedule')) {
      return route.fulfill({
        json: [
          {
            id: 43,
            scheduled_date: '2030-01-28',
            scheduled_time: '18:30:00',
            title: 'Ноги и корпус',
            status: 'completed',
            day_number: 2,
            week_number: 4,
          },
        ],
      });
    }
    if (path.endsWith('/workouts/history')) {
      return route.fulfill({
        json: [
          {
            id: 43,
            scheduled_date: '2030-01-28',
            scheduled_time: '18:30:00',
            title: 'Ноги и корпус',
            status: 'completed',
            started_at: '2030-01-28T18:30:00',
            completed_at: '2030-01-28T19:20:00',
            completed_sets: 4,
            volume_kg: 1480,
            exercises: [
              {
                workout_exercise_id: 55,
                exercise_id: 11,
                title: 'Присед со штангой',
                prescribed_sets: 4,
                prescribed_reps: '8',
                sort_order: 1,
              },
            ],
            adaptations: [],
          },
        ],
      });
    }
    if (path.endsWith('/workouts/43/comments')) {
      return route.fulfill({
        json: [
          {
            id: 7,
            trainer_author_id: 70,
            client_user_id: 7,
            workout_id: 43,
            workout_exercise_id: 55,
            body: 'Держите колени по направлению носков. <script>не HTML</script>',
            body_format: 'plain_text',
            created_at: '2030-01-28T20:00:00',
            updated_at: '2030-01-28T20:05:00',
            revisions: [],
          },
        ],
      });
    }
    if (path.endsWith('/workouts/history/summary')) {
      return route.fulfill({
        json: { workouts_completed: 1, completed_sets: 4, volume_kg: 1480 },
      });
    }
    return route.fulfill({ json: [] });
  });
}

test('progress remains clear and free of horizontal overflow at supported widths', async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  const runtimeErrors: string[] = [];
  page.on('console', (message) => {
    const expectedHttpState =
      message.text().includes('401 (Unauthorized)') || message.text().includes('404 (Not Found)');
    if (message.type() === 'error' && !expectedHttpState) {
      consoleErrors.push(message.text());
    }
  });
  page.on('pageerror', (error) => runtimeErrors.push(error.stack || error.message));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();
  await expect(
    page
      .getByRole('heading', { name: 'Прогресс', exact: true })
      .or(page.getByRole('heading', { name: 'Приложение не смогло продолжить работу' })),
  ).toBeVisible();
  expect(consoleErrors).toEqual([]);
  expect(runtimeErrors).toEqual([]);
  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();
  await expect(page.getByText('84%').first()).toBeVisible();

  await page.getByText('Жим штанги лёжа').click();
  await expect(page.getByText('Детали тренировки')).toBeVisible();
  await page.locator('.progress-hero').getByRole('tab', { name: '7 дней' }).click();
  await expect(page.locator('.progress-hero').getByRole('tab', { name: '7 дней' })).toHaveAttribute(
    'aria-selected',
    'true',
  );

  for (const viewport of [
    { width: 1440, height: 1000 },
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
    await expect(
      page.locator('.progress-hero').getByRole('tab', { name: '30 дней' }),
    ).toBeVisible();
    await expect(
      page.getByRole('progressbar', { name: /Запланированные тренировки/ }),
    ).toBeVisible();
  }

  expect(consoleErrors).toEqual([]);
  expect(runtimeErrors).toEqual([]);
});

test('shared data confidence keeps analytics factual, responsive and explicit while refreshing', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await mockProgress(page);

  let releaseRefresh!: () => void;
  let markRefreshStarted!: () => void;
  const refreshGate = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });
  const refreshStarted = new Promise<void>((resolve) => {
    markRefreshStarted = resolve;
  });
  await page.route('**/workouts/progress/summary?period_days=7', async (route) => {
    markRefreshStarted();
    await refreshGate;
    await route.fallback();
  });

  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  const trainingConfidence = page
    .locator('#progress-training')
    .getByLabel('Достаточно ли данных: Данных достаточно для оценки')
    .first();
  const limitedConfidence = page.getByLabel('Достаточно ли данных: Вывод пока предварительный');
  await expect(trainingConfidence).toContainText('28 рабочих подходов в 7 тренировках');
  await expect(limitedConfidence).toContainText(
    'В самой заполненной окружности — 2 замера; для оценки одной окружности нужно минимум 3 замера',
  );
  await expect(limitedConfidence.locator('.badge')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Добавить замер' })).toBeVisible();

  const visualContract = await page.evaluate(() => {
    const tokenColor = (token: string) => {
      const sample = document.createElement('span');
      sample.style.color = `var(${token})`;
      document.body.append(sample);
      const value = getComputedStyle(sample).color;
      sample.remove();
      return value;
    };
    const sufficient = document.querySelector<HTMLElement>('.data-confidence--sufficient');
    const limited = document.querySelector<HTMLElement>('.data-confidence--limited');
    const disclosure = limited?.querySelector<HTMLElement>('.disclosure-icon');
    const disclosureBox = disclosure?.getBoundingClientRect();
    return {
      lime: tokenColor('--v2-lime'),
      sufficientBoundary: sufficient ? getComputedStyle(sufficient).borderLeftColor : null,
      limitedBoundary: limited ? getComputedStyle(limited).borderLeftColor : null,
      disclosure: disclosureBox
        ? {
            width: disclosureBox.width,
            height: disclosureBox.height,
            radius: getComputedStyle(disclosure!).borderRadius,
          }
        : null,
    };
  });
  expect(visualContract.sufficientBoundary).toBe(visualContract.lime);
  expect(visualContract.limitedBoundary).toBe(visualContract.lime);
  expect(visualContract.disclosure).toEqual({ width: 28, height: 28, radius: '50%' });

  const trainingRegion = page.locator('#progress-training');
  const confidenceBox = await trainingRegion.locator('.data-confidence').boundingBox();
  const nextBox = await trainingRegion.locator('.progress-subsection').boundingBox();
  expect(confidenceBox).not.toBeNull();
  expect(nextBox).not.toBeNull();
  expect(confidenceBox!.y + confidenceBox!.height).toBeLessThanOrEqual(nextBox!.y);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator('#progress-body').screenshot({
    path: '../.artifacts/screenshots/task-61/desktop-1440x900-light-analytics.png',
  });

  for (const viewport of [
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
    const disclosure = page.locator('.data-confidence__details > summary').first();
    expect((await disclosure.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }

  await trainingConfidence.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-61/mobile-web-360x800-light-analytics.png',
  });

  await expect(progressOverview(page)).toHaveCount(1);
  await expect(progressOverview(page)).toBeVisible();
  await page.locator('.progress-hero').getByRole('tab', { name: '7 дней' }).click();
  await refreshStarted;
  const loadingState = page.getByRole('status').filter({ hasText: 'Обновляем динамику за период' });
  await expect(loadingState).toBeVisible();
  await expect(progressOverview(page)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await loadingState.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-61/mobile-web-390x844-light-period-loading.png',
  });
  releaseRefresh();
  await expect(progressOverview(page)).toBeVisible();
});

test('measurements keep priority context, units, mobile order and add/edit history', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  const body = page.locator('#progress-body');
  await expect(body.getByRole('heading', { name: 'Замеры и приоритеты' })).toBeVisible();
  await expect(body.getByText('Мышцы спины')).toBeVisible();
  await expect(body.getByText('Задняя поверхность тела и ягодичные мышцы')).toBeVisible();
  await expect(body.getByText(/не оценивает тело/)).toBeVisible();
  await expect(body.getByText(/Вес: 69\.1 кг · Талия: 72\.5 см/)).toBeVisible();
  await expect(body.getByText(/разовое изменение не считаем трендом/)).toBeVisible();

  await page.setViewportSize({ width: 1440, height: 1000 });
  const desktopTrend = await body.locator('.progress-body-trends').boundingBox();
  const desktopDiary = await body.locator('.progress-body-diary').boundingBox();
  expect(desktopTrend).not.toBeNull();
  expect(desktopDiary).not.toBeNull();
  expect(desktopTrend!.y).toBeLessThan(desktopDiary!.y);
  await body.evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await page.screenshot({
    path: '../.artifacts/screenshots/task-60/desktop-1440x1000-light.png',
  });

  await page.setViewportSize({ width: 360, height: 800 });
  await expect
    .poll(async () => {
      const mobileTrend = await body.locator('.progress-body-trends').boundingBox();
      const mobileDiary = await body.locator('.progress-body-diary').boundingBox();
      return Boolean(mobileTrend && mobileDiary && mobileDiary.y < mobileTrend.y);
    })
    .toBe(true);
  await expect(body.getByLabel('Вес, кг')).toHaveAttribute('inputmode', 'decimal');
  await body.evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await expect(body.locator('.measurement-diary__save-dock')).toHaveCSS('position', 'static');
  await page.screenshot({
    path: '../.artifacts/screenshots/task-60/mobile-web-360x800-light.png',
  });
  const mobileSave = body.getByRole('button', { name: 'Сохранить замер' });
  await mobileSave.scrollIntoViewIfNeeded();
  const noteField = await body.getByLabel('Заметка').boundingBox();
  const saveButton = await mobileSave.boundingBox();
  expect(noteField).not.toBeNull();
  expect(saveButton).not.toBeNull();
  expect(saveButton!.y - (noteField!.y + noteField!.height)).toBeGreaterThanOrEqual(18);
  await page.screenshot({
    path: '../.artifacts/screenshots/task-60/mobile-web-360x800-light-save.png',
  });

  await body.getByLabel('Вес, кг').fill('68.7');
  await body.getByLabel('Талия, см').fill('71.9');
  expect(
    await body
      .locator('.measurement-diary__form :invalid')
      .evaluateAll((elements) => elements.map((element) => element.getAttribute('aria-label'))),
  ).toEqual([]);
  const createRequest = page.waitForRequest(
    (request) => request.url().endsWith('/workouts/diary') && request.method() === 'POST',
  );
  await body.getByRole('button', { name: 'Сохранить замер' }).click();
  await createRequest;
  await expect(body.getByText(/Вес: 68\.7 кг · Талия: 71\.9 см/)).toBeVisible();

  const todayRow = body.locator('.measurement-history__row').filter({ hasText: '68.7 кг' });
  await todayRow.getByRole('button', { name: 'Изменить' }).click();
  await expect(body.getByRole('heading', { name: 'Изменить замер' })).toBeVisible();
  await body.getByLabel('Вес, кг').fill('68.5');
  const editRequest = page.waitForRequest(
    (request) => request.url().endsWith('/workouts/diary') && request.method() === 'POST',
  );
  await body.getByRole('button', { name: 'Сохранить изменения' }).click();
  await editRequest;
  await expect(body.getByText(/Вес: 68\.5 кг · Талия: 71\.9 см/)).toBeVisible();
  await expect(body.getByText(/Вес: 68\.7 кг/)).not.toBeAttached();

  const save = body.getByRole('button', { name: 'Сохранить замер' });
  expect((await save.boundingBox())?.height).toBeGreaterThanOrEqual(48);
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    .toBe(true);
});

test('nutrition report preserves truthful period context, daily drill-down and responsive hierarchy', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await mockProgress(page, 'long');
  await page.goto('/app?section=progress&progress_period=days_7');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  const report = page.locator('#nutrition-period-report');
  const selector = page
    .locator('.progress-period-controls')
    .getByRole('tablist', { name: 'Период прогресса' });
  await expect(report.getByRole('heading', { name: 'Отчёт по питанию' })).toBeVisible();
  await selector.getByRole('tab', { name: '7 дней' }).click();
  await expect(report.getByText('Заполнено 2 из 7 дней')).toBeVisible();
  await expect(
    report.getByText('Средние значения рассчитаны только по заполненным дням.'),
  ).toBeVisible();
  await expect(report.getByRole('img', { name: /Калории по дням/ })).toBeVisible();
  await expect(report.getByText('Изменения цели в периоде')).toBeVisible();
  await expect(
    report.getByRole('table', {
      name: 'Дневные КБЖУ, статус заполнения и действовавшая цель',
    }),
  ).toBeVisible();
  const dailyTable = report.getByRole('table', {
    name: 'Дневные КБЖУ, статус заполнения и действовавшая цель',
  });
  await expect(
    dailyTable.getByRole('cell', { name: 'Нет данных', exact: true }).first(),
  ).toBeVisible();
  await expect(dailyTable.getByRole('cell', { name: '0 ккал', exact: true }).first()).toBeVisible();

  for (const period of ['30 дней', '90 дней']) {
    await selector.getByRole('tab', { name: period }).click();
    await expect(selector.getByRole('tab', { name: period })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    const pointNavigation = report.getByRole('group', {
      name: 'Навигация по точкам графика',
    });
    await expect(pointNavigation).toBeVisible();
    expect(
      (
        await pointNavigation
          .getByRole('button', { name: 'Предыдущая точка графика' })
          .boundingBox()
      )?.height,
    ).toBeGreaterThanOrEqual(44);
  }
  await expect(page).toHaveURL(/progress_period=days_90/);
  await expect(report.getByText(/Заполнено \d+ из 90 дней/)).toBeVisible();

  await selector.getByRole('tab', { name: 'Свой период' }).click();
  await page.getByLabel('Начало периода').fill('2025-01-01');
  await page.getByLabel('Конец периода').fill('2025-12-31');
  await page.getByRole('button', { name: 'Показать период' }).click();
  await expect(page).toHaveURL(/progress_period=custom/);
  await expect(report.getByText(/Заполнено \d+ из 365 дней/)).toBeVisible();
  const longRangeNavigation = report.getByRole('group', {
    name: 'Навигация по точкам графика',
  });
  await longRangeNavigation.focus();
  await page.keyboard.press('Home');
  const selectedDayLink = report.getByRole('link', { name: 'Открыть день' });
  await expect(selectedDayLink).toHaveAttribute('href', /date=2025-01-01/);
  await page.keyboard.press('ArrowRight');
  await expect(selectedDayLink).toHaveAttribute('href', /date=2025-01-07/);
  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
    expect((await longRangeNavigation.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    expect((await selectedDayLink.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }
  await report.locator('.data-viz-chart').screenshot({
    path: '../.artifacts/screenshots/task-69b/data-dense-chart-mobile-web-light.png',
  });
  await page.setViewportSize({ width: 768, height: 900 });
  await report.screenshot({
    path: '../.artifacts/screenshots/task-57/tablet-768x900-light-long-range.png',
  });

  await selector.getByRole('tab', { name: '7 дней' }).click();
  const dayLink = report.getByRole('link', { name: 'Открыть день' });
  const reportUrl = page.url();
  await dayLink.click();
  await expect(page).toHaveURL(/section=nutrition&date=/);
  const returnTo = await page.evaluate(() => new URLSearchParams(location.search).get('return_to'));
  expect(returnTo).toBe(
    new URL(reportUrl).pathname + new URL(reportUrl).search + '#nutrition-period-report',
  );
  await expect(page.getByRole('heading', { name: 'Питание', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'К отчёту по питанию' }).click();
  await expect(page).toHaveURL(`${reportUrl}#nutrition-period-report`);
  await expect(selector.getByRole('tab', { name: '7 дней' })).toHaveAttribute(
    'aria-selected',
    'true',
  );

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1280, height: 900 },
    { width: 1024, height: 900 },
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
    const selectorTargets = await selector
      .getByRole('tab')
      .evaluateAll((tabs) => tabs.map((tab) => tab.getBoundingClientRect().height));
    expect(selectorTargets.every((height) => height >= 44)).toBe(true);
    if (viewport.width <= 430) {
      const selectorScroller = page.locator('.progress-period-controls .ui-tabs');
      const selectorScrollState = await selectorScroller.evaluate((element) => {
        const style = getComputedStyle(element);
        return {
          clientWidth: element.clientWidth,
          overflowX: style.overflowX,
          scrollWidth: element.scrollWidth,
        };
      });
      expect(selectorScrollState.scrollWidth).toBeGreaterThanOrEqual(
        selectorScrollState.clientWidth,
      );
      expect(selectorScrollState.overflowX).toBe('auto');
    }
    const nextSection = page.locator('.progress-adherence');
    await expect
      .poll(async () => {
        const [reportBox, nextSectionBox] = await Promise.all([
          report.boundingBox(),
          nextSection.boundingBox(),
        ]);
        return Boolean(
          reportBox && nextSectionBox && reportBox.y + reportBox.height <= nextSectionBox.y + 1,
        );
      })
      .toBe(true);
    const reportBox = await report.boundingBox();
    const nextSectionBox = await nextSection.boundingBox();
    expect(reportBox).not.toBeNull();
    expect(nextSectionBox).not.toBeNull();
    expect(reportBox!.y + reportBox!.height).toBeLessThanOrEqual(nextSectionBox!.y + 1);
    if (viewport.width === 1440) {
      expect(reportBox!.x).toBeGreaterThanOrEqual(24);
      expect(reportBox!.x + reportBox!.width).toBeLessThanOrEqual(viewport.width - 24);
      await report.evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await page.screenshot({
        path: '../.artifacts/screenshots/task-57/desktop-1440x900-light-report.png',
      });
      await page.screenshot({
        path: '../.artifacts/screenshots/task-69b/desktop-1440x900-light-overview.png',
      });
      await report.screenshot({
        path: '../.artifacts/screenshots/task-57/desktop-1440x900-light-partial.png',
      });
      await report.locator('.data-viz-chart').screenshot({
        path: '../.artifacts/screenshots/task-69b/data-dense-chart-desktop-light.png',
      });
    }
    if (viewport.width === 360) {
      const pointStyle = await report
        .locator('.data-viz-chart__point-ring')
        .first()
        .evaluate((point) => {
          const style = getComputedStyle(point);
          return { fill: style.fill, stroke: style.stroke };
        });
      expect(pointStyle.fill).not.toBe(pointStyle.stroke);
      expect(
        (await report.getByRole('img', { name: /Калории по дням/ }).boundingBox())?.height,
      ).toBeGreaterThanOrEqual(180);
      const pointTargets = await report
        .locator('.data-viz-chart__point-navigation button')
        .evaluateAll((buttons) =>
          buttons.map((button) => {
            const box = button.getBoundingClientRect();
            return { width: box.width, height: box.height };
          }),
        );
      expect(pointTargets.length).toBeGreaterThan(0);
      expect(
        Math.min(...pointTargets.map((box) => Math.min(box.width, box.height))),
      ).toBeGreaterThanOrEqual(44);
      await report.evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await page.screenshot({
        path: '../.artifacts/screenshots/task-69b/mobile-web-360x800-light-compact.png',
      });
      await report.screenshot({
        path: '../.artifacts/screenshots/task-69b/mobile-web-360x800-light-report.png',
      });
    }
  }
});

test('nutrition report no-data state keeps missing days distinct from zero', async ({ page }) => {
  await page.setViewportSize({ width: 430, height: 932 });
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await mockProgress(page, 'no-data');
  await page.goto('/app?section=progress&progress_period=days_30');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  const report = page.locator('#nutrition-period-report');
  await expect(report.getByText('Заполнено 0 из 30 дней')).toBeVisible();
  await expect(report.getByText('Нет заполненных дней за период')).toBeVisible();
  await expect(report.getByRole('link', { name: 'Открыть дневник питания' })).toBeVisible();
  await expect(report.getByRole('img')).not.toBeAttached();
  await expect(report.getByText('0 ккал', { exact: true })).not.toBeAttached();
  await expect(report.locator('.nutrition-report-days')).not.toHaveAttribute('open', '');
  await report.screenshot({
    path: '../.artifacts/screenshots/task-69b/sparse-insufficient-mobile-light.png',
  });
});

test('notification deep-link opens exact workout feedback and preserves back navigation', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockProgress(page);

  await page.goto('/app?section=today');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  await page.goto('/app?workout_id=43&comment_id=7&workout_exercise_id=55');

  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();
  await expect(
    page.getByText('Держите колени по направлению носков.', { exact: false }),
  ).toBeVisible();
  await expect(page.locator('#workout-comment-7')).toHaveClass(/is-focused/);
  await expect(page.locator('#workout-comment-7')).toHaveCount(1);
  await expect(page.getByText('Упражнение · Присед со штангой')).toBeVisible();
  await expect(page.getByText('Изменено')).toBeVisible();
  await expect(page.locator('.workout-feedback script')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  const historyCard = page.locator('.workout-history-card');
  const clearHistory = historyCard.getByRole('button', { name: 'Очистить историю' });
  const clearHistoryBox = await clearHistory.boundingBox();
  const historyFeedbackBox = await historyCard.locator('.workout-feedback').boundingBox();
  expect(clearHistoryBox?.y ?? 0).toBeGreaterThan(
    (historyFeedbackBox?.y ?? 0) + (historyFeedbackBox?.height ?? 0),
  );
  expect(clearHistoryBox?.height).toBeGreaterThanOrEqual(44);
  await clearHistory.click();
  await expect(page.getByRole('dialog', { name: 'Очистить историю?' })).toBeVisible();
  await page.getByRole('button', { name: 'Отмена' }).click();
  await expect(historyCard).toHaveAttribute('open', '');
  const historyMetricBoxes = await historyCard
    .locator('.workout-history__metrics .metric')
    .evaluateAll((metrics) => metrics.map((metric) => metric.getBoundingClientRect()));
  expect(historyMetricBoxes).toHaveLength(3);
  expect(
    Math.max(...historyMetricBoxes.map((box) => box.top)) -
      Math.min(...historyMetricBoxes.map((box) => box.top)),
  ).toBeLessThan(2);
  expect(historyMetricBoxes.every((box) => box.width >= 90)).toBe(true);

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 430, height: 932 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
    const metricBoxes = await historyCard
      .locator('.workout-history__metrics .metric')
      .evaluateAll((metrics) => metrics.map((metric) => metric.getBoundingClientRect()));
    expect(
      Math.max(...metricBoxes.map((box) => box.top)) -
        Math.min(...metricBoxes.map((box) => box.top)),
    ).toBeLessThan(2);
  }
  const historyRowBox = await page.locator('#workout-history-43').boundingBox();
  const feedbackBox = await page
    .locator('#workout-history-43 .workout-feedback-disclosure')
    .boundingBox();
  expect(historyRowBox).not.toBeNull();
  expect(feedbackBox).not.toBeNull();
  expect(feedbackBox!.x).toBeGreaterThanOrEqual(historyRowBox!.x);
  expect(feedbackBox!.x + feedbackBox!.width).toBeLessThanOrEqual(
    historyRowBox!.x + historyRowBox!.width + 1,
  );

  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('.workout-feedback').first()).toHaveCSS('color', 'rgb(245, 245, 245)');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  if (captureFeedbackAudit) {
    await page.screenshot({
      path: '../.artifacts/ui-audit/task-49/client-feedback-mobile-dark.png',
      fullPage: true,
    });
  }

  await page.goBack();
  await expect(page).toHaveURL(/\/app(?:\?section=today)?$/);
  await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
});

test('dark progress keeps the bento adherence score readable on lime', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  const summaryScore = page.locator('.progress-bento__adherence .progress-summary__score');
  const adherenceScore = page.locator('.progress-adherence__score');
  await expect(summaryScore).toHaveText('84%');
  await expect(adherenceScore).toHaveText('84%');

  const colors = await page.evaluate(() => ({
    summary: getComputedStyle(
      document.querySelector('.progress-bento__adherence .progress-summary__score')!,
    ).color,
    adherence: getComputedStyle(document.querySelector('.progress-adherence__score')!).color,
    accent: (() => {
      const probe = document.createElement('span');
      probe.style.color = 'var(--v2-accent-text)';
      document.body.append(probe);
      const color = getComputedStyle(probe).color;
      probe.remove();
      return color;
    })(),
  }));
  expect(colors.summary).not.toBe(colors.accent);
  expect(colors.adherence).toBe(colors.accent);
});

test('light progress keeps the bento adherence score readable on lime', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  const summaryScore = page.locator('.progress-bento__adherence .progress-summary__score');
  const adherenceScore = page.locator('.progress-adherence__score');
  await expect(summaryScore).toHaveText('84%');
  await expect(adherenceScore).toHaveText('84%');

  const colors = await page.evaluate(() => ({
    summary: getComputedStyle(
      document.querySelector('.progress-bento__adherence .progress-summary__score')!,
    ).color,
    adherence: getComputedStyle(document.querySelector('.progress-adherence__score')!).color,
    accent: (() => {
      const probe = document.createElement('span');
      probe.style.color = 'var(--v2-accent-text)';
      document.body.append(probe);
      const color = getComputedStyle(probe).color;
      probe.remove();
      return color;
    })(),
  }));
  expect(colors.summary).not.toBe(colors.accent);
  expect(colors.adherence).toBe(colors.accent);
});

test('canonical charts and icons remain operable in forced colors and reduced motion', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  const chart = page.locator('.data-viz-chart').first();
  await expect(chart.getByRole('img')).toBeVisible();
  await expect(chart.getByRole('group', { name: 'Навигация по точкам графика' })).toBeVisible();
  await chart.getByRole('group', { name: 'Навигация по точкам графика' }).focus();
  await page.keyboard.press('Home');
  await expect(chart.locator('.data-viz-chart__selection')).toBeVisible();
  await expect(
    page
      .getByRole('navigation', { name: 'Основная навигация' })
      .getByRole('link', { name: 'Прогресс' })
      .locator('[data-icon="nav-progress"]'),
  ).toBeVisible();
  expect(
    await chart
      .locator('.data-viz-chart__actual')
      .first()
      .evaluate((line) => getComputedStyle(line).stroke),
  ).not.toBe('none');
  expect(
    await chart
      .locator('.data-viz-chart__point-ring')
      .first()
      .evaluate((point) => getComputedStyle(point).transitionDuration),
  ).toBe('0s');
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    .toBe(true);
});

test('exercise catalogue uses the selected folder and dumbbell glyph on desktop and mobile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();

  const desktopCatalogue = page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Упражнения' });
  const desktopIcon = desktopCatalogue.locator('[data-icon="nav-exercise-catalog"]');
  await expect(desktopIcon).toBeVisible();
  expect((await desktopIcon.boundingBox())?.width).toBeGreaterThanOrEqual(16);
  await desktopCatalogue.screenshot({
    path: '../.artifacts/screenshots/task-69b/exercise-catalog-desktop-light.png',
  });

  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  const morePanel = page.getByRole('dialog');
  const mobileCatalogue = morePanel.getByRole('link', { name: 'Упражнения' });
  await expect(mobileCatalogue.locator('[data-icon="nav-exercise-catalog"]')).toBeVisible();
  await morePanel.screenshot({
    path: '../.artifacts/screenshots/task-69b/exercise-catalog-mobile-dark.png',
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test('progress bento keeps matching light and dark visual forms for the same data', async ({
  browser,
  baseURL,
}) => {
  test.setTimeout(120_000);
  const surfaces = [
    { name: 'desktop-1440x900', width: 1440, height: 900 },
    { name: 'desktop-1280x900', width: 1280, height: 900 },
    { name: 'tablet-1024x900', width: 1024, height: 900 },
    { name: 'tablet-768x900', width: 768, height: 900 },
    { name: 'mobile-430x932', width: 430, height: 932 },
    { name: 'mobile-390x844', width: 390, height: 844 },
    { name: 'mobile-360x800', width: 360, height: 800 },
  ];

  for (const surface of surfaces) {
    for (const theme of ['light', 'dark'] as const) {
      const context = await browser.newContext({
        baseURL,
        colorScheme: theme,
        viewport: { width: 1440, height: 900 },
      });
      await context.addInitScript((selectedTheme) => {
        localStorage.setItem('app-theme', selectedTheme);
      }, theme);
      await context.addInitScript(() => {
        const RealDate = globalThis.Date;
        const fixedNow = RealDate.parse('2030-01-30T12:00:00Z');
        globalThis.Date = class extends RealDate {
          constructor(value?: string | number | Date) {
            super(value ?? fixedNow);
          }

          static now() {
            return fixedNow;
          }
        } as DateConstructor;
      });
      const page = await context.newPage();
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await mockProgress(page);
      await page.goto('/app?section=progress&progress_period=days_30');
      await page.getByRole('button', { name: 'Клиент' }).click();
      await page
        .getByRole('navigation', { name: 'Основная навигация' })
        .getByRole('link', { name: 'Прогресс' })
        .click();
      await page.locator('.progress-period-controls').getByRole('tab', { name: '30 дней' }).click();
      await page.setViewportSize({ width: surface.width, height: surface.height });

      await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();
      await expect(progressOverview(page)).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
      await expect(
        page.locator('.progress-period-controls').getByRole('tab', { name: '30 дней' }),
      ).toHaveAttribute('aria-selected', 'true');
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(surface.width);
      await page.screenshot({
        path: `../.artifacts/screenshots/task-111/progress-bento-${surface.name}-${theme}.png`,
      });
      await context.close();
    }
  }
});

test('progress period controls drive one exact URL and API range through history', async ({
  page,
}) => {
  await page.setViewportSize({ width: 430, height: 932 });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await mockProgress(page);
  const requests: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (/\/workouts\/progress\/(summary|training-analytics|nutrition-report)$/.test(url.pathname)) {
      requests.push(`${url.pathname}${url.search}`);
    }
  });

  await page.goto('/app?section=progress&progress_period=days_30');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();
  const controls = page.locator('.progress-period-controls');
  await expect(controls.getByRole('tab')).toHaveCount(4);
  await controls.getByRole('tab', { name: '30 дней' }).click();
  await expect(progressOverview(page)).toBeVisible();

  for (const period of [7, 30, 90] as const) {
    const label = `${period} дней`;
    await controls.getByRole('tab', { name: label }).click();
    await expect(page).toHaveURL(new RegExp(`progress_period=days_${period}(?:&|$)`));
    await expect(controls.getByRole('tab', { name: label })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await expect(progressOverview(page)).toBeVisible();
  }

  await controls.getByRole('tab', { name: 'Свой период' }).click();
  await page.getByLabel('Начало периода').fill('2025-01-01');
  await page.getByLabel('Конец периода').fill('2025-01-30');
  await page.getByRole('button', { name: 'Показать период' }).click();
  await expect(page).toHaveURL(/progress_period=custom/);
  await expect(page).toHaveURL(/progress_from=2025-01-01/);
  await expect(page).toHaveURL(/progress_to=2025-01-30/);
  expect(requests.some((request) => request.includes('date_from=2025-01-01'))).toBe(true);
  expect(requests.some((request) => request.includes('date_to=2025-01-30'))).toBe(true);

  await page.goBack();
  await expect(page).toHaveURL(/progress_period=days_90/);
  await page.goForward();
  await expect(page).toHaveURL(/progress_period=custom/);
  await expect(progressOverview(page)).toBeVisible();
});
