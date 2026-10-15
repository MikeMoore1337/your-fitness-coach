import { expect, test, type Page } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
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

const TASK_111_SCREENSHOTS = resolve(
  process.cwd(),
  '..',
  '..',
  '..',
  'tasks',
  '111',
  'deliverables',
  'screenshots',
);

type NutritionReportState = 'partial' | 'no-data' | 'long';

const CAPTURE_PROGRESS_865 = process.env.CAPTURE_PROGRESS_865;
const CAPTURE_970_AFTER = process.env.CAPTURE_970_AFTER === '1';
const WORKTREE_ROOT = resolve(process.cwd(), '..');
const ISSUE_970_AFTER_DIR = resolve(
  WORKTREE_ROOT,
  'docs',
  'ux',
  'final-issues-acceptance',
  'evidence',
  '970-report-mobile-20261013',
  'after',
);

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
    const trainerTarget = state === 'long' && diaryDate > targetChangeDate;
    const targetCalories = diaryDate < targetChangeDate ? 2100 : trainerTarget ? 2000 : 1950;
    const targetProtein = diaryDate < targetChangeDate ? 140 : trainerTarget ? 140 : 135;
    const targetFat = diaryDate < targetChangeDate ? 70 : trainerTarget ? 70 : 65;
    const targetCarbs = diaryDate < targetChangeDate ? 230 : trainerTarget ? 220 : 210;
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
            ...(state === 'long'
              ? [
                  {
                    effective_from: shiftDate(targetChangeDate, 1),
                    source: 'trainer',
                    calories: 2000,
                    protein_g: 140,
                    fat_g: 70,
                    carbs_g: 220,
                  },
                ]
              : []),
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
          previous_period_start: '2029-12-02',
          previous_period_end: '2029-12-31',
          exercise_history_limit: 20,
          completed_set_count: 28,
          completed_workout_count: 7,
          frequency_per_week: 1.63,
          previous_completed_workout_count: 6,
          previous_frequency_per_week: 1.4,
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
          muscle_group_workload: [
            {
              muscle_id: 'chest',
              muscle_name: 'Грудные',
              current: {
                completed_set_count: 18,
                primary_completed_set_count: 18,
                secondary_completed_set_count: 0,
                completed_session_count: 6,
                frequency_per_week: 1.4,
              },
              previous: {
                completed_set_count: 12,
                primary_completed_set_count: 12,
                secondary_completed_set_count: 0,
                completed_session_count: 4,
                frequency_per_week: 0.93,
              },
              completed_set_count_change: 6,
              frequency_per_week_change: 0.47,
              trend: 'increased',
              contributing_exercises: [],
            },
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

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Тренировки/ })
    .click();
  await expect(page.getByRole('heading', { name: 'Тренировки', level: 2 })).toBeVisible();
  await expect(page.getByText('Грудные')).toBeVisible();
  await expect(page.getByText('+6 подх.')).toBeVisible();
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
    await expect(page.getByRole('heading', { name: 'Тренировки', level: 2 })).toBeVisible();
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

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Тренировки/ })
    .click();
  await expect(page.getByRole('heading', { name: 'Тренировки', level: 2 })).toBeVisible();
  const trainingConfidence = page
    .locator('#progress-training')
    .getByLabel('Достаточно ли данных: Данных достаточно для оценки')
    .first();
  await expect(trainingConfidence).toContainText('28 рабочих подходов в 7 тренировках');
  const trainingRegion = page.locator('#progress-training');
  const confidenceBox = await trainingRegion.locator('.data-confidence').boundingBox();
  const nextBox = await trainingRegion.locator('.progress-subsection').first().boundingBox();
  expect(confidenceBox).not.toBeNull();
  expect(nextBox).not.toBeNull();
  expect(confidenceBox!.y + confidenceBox!.height).toBeLessThanOrEqual(nextBox!.y);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator('#progress-training').screenshot({
    path: '../.artifacts/screenshots/task-61/desktop-1440x900-light-analytics.png',
  });

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Тело/ })
    .click();
  await expect(page.getByRole('heading', { name: 'Замеры и приоритеты' })).toBeVisible();
  const limitedConfidence = page.getByLabel('Достаточно ли данных: Вывод пока предварительный');
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

  await limitedConfidence.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-61/mobile-web-360x800-light-analytics.png',
  });

  await page.locator('.progress-detail-header__back').click();
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

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Тело/ })
    .click();

  const body = page.locator('#progress-body');
  await expect(body.getByRole('heading', { name: 'Замеры и приоритеты' })).toBeVisible();
  await body.getByText('Выбранные мышечные группы').click();
  await expect(body.getByText('Мышцы спины')).toBeVisible();
  await expect(body.getByText('Задняя поверхность тела и ягодичные мышцы')).toBeVisible();
  await expect(body.getByText(/не оценивает тело/)).toBeVisible();
  await expect(body.locator('.progress-measurement-editor')).not.toHaveAttribute('open');
  await body.locator('.progress-measurement-editor > summary').click();
  await expect(
    body.locator('.measurement-diary').getByText(/Вес: 69\.1 кг · Талия: 72\.5 см/),
  ).toBeVisible();
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
      return Boolean(mobileTrend && mobileDiary && mobileDiary.y > mobileTrend.y);
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
  expect(saveButton!.y - (noteField!.y + noteField!.height)).toBeGreaterThanOrEqual(18 - 0.01);
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

test('quick measurement can return without losing an unsaved draft', async ({ page }) => {
  await mockProgress(page);
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await page.setViewportSize({ width: 390, height: 844 });
  const evidenceRoot = resolve(
    process.cwd(),
    '..',
    '.artifacts',
    'runtime',
    'tests',
    'screenshots',
    'issue-969',
  );
  await mkdir(evidenceRoot, { recursive: true });
  await page.goto('/app?section=progress&focus=measurements');
  await page.getByRole('button', { name: 'Клиент' }).click();

  const diary = page.locator('#measurement-diary');
  await expect(diary.getByRole('heading', { name: 'Новый замер' })).toBeVisible();
  await page.screenshot({
    fullPage: true,
    path: resolve(evidenceRoot, `${test.info().project.name}-measurement-light-390x844.png`),
  });
  await page.setViewportSize({ width: 360, height: 800 });
  await page.screenshot({
    fullPage: true,
    path: resolve(evidenceRoot, `${test.info().project.name}-measurement-light-360x800.png`),
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.localStorage.setItem('app-theme', 'dark'));
  await page.reload();
  await expect(
    page.locator('#measurement-diary').getByRole('heading', { name: 'Новый замер' }),
  ).toBeVisible();
  await page.screenshot({
    fullPage: true,
    path: resolve(evidenceRoot, `${test.info().project.name}-measurement-dark-390x844.png`),
  });
  await page.setViewportSize({ width: 360, height: 800 });
  await page.screenshot({
    fullPage: true,
    path: resolve(evidenceRoot, `${test.info().project.name}-measurement-dark-360x800.png`),
  });
  await page.setViewportSize({ width: 390, height: 844 });
  const weight = diary.getByLabel('Вес, кг');
  await weight.fill('70.2');
  await diary.getByRole('button', { name: 'Вернуться' }).click();

  const discardDialog = page.getByRole('dialog', { name: 'Вернуться без сохранения?' });
  await expect(discardDialog).toBeVisible();
  await discardDialog.getByRole('button', { name: 'Отмена' }).click();
  await expect(weight).toHaveValue('70.2');

  await diary.getByRole('button', { name: 'Вернуться' }).click();
  await page
    .getByRole('dialog', { name: 'Вернуться без сохранения?' })
    .getByRole('button', { name: 'Вернуться' })
    .click();
  await expect(page).toHaveURL(/\/app\?section=progress$/);
  await expect(page.locator('[data-testid="quick-add-trigger"]')).toBeFocused();

  await page.goto('/app?section=progress&focus=measurements');
  await expect(page.locator('#measurement-diary').getByLabel('Вес, кг')).toHaveValue('70.2');
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

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Питание/ })
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
  await expect(report.getByText('Изменения цели в периоде')).toBeHidden();
  await report.getByText('История целей питания', { exact: true }).click();
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
    const previousPointButton = pointNavigation.getByRole('button', {
      name: 'Предыдущая точка графика',
    });
    await expect(previousPointButton).toBeVisible();
    await expect
      .poll(async () => (await previousPointButton.boundingBox())?.height ?? 0)
      .toBeGreaterThanOrEqual(44);
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
      const selectorScroller = page.locator('.progress-period-controls__tabs');
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
    const reportBox = await report.boundingBox();
    const categoryNavBox = await page.locator('.progress-category-nav').boundingBox();
    expect(reportBox).not.toBeNull();
    expect(categoryNavBox).not.toBeNull();
    expect(reportBox!.y).toBeGreaterThanOrEqual(categoryNavBox!.y);
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

for (const width of [320, 360, 390, 393, 430]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`#970 target changes stay readable at ${width}px ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 932 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await mockProgress(page, 'long');
      await page.goto('/app?section=progress&progress_period=days_30');
      await page.getByRole('button', { name: 'Клиент' }).click();
      await page
        .getByRole('navigation', { name: 'Основная навигация' })
        .getByRole('link', { name: 'Прогресс' })
        .click();
      await page
        .getByRole('navigation', { name: 'Разделы прогресса' })
        .getByRole('tab', { name: /^Питание/ })
        .click();

      const report = page.locator('#nutrition-period-report');
      await report.getByText('История целей питания', { exact: true }).click();
      const targetChanges = report
        .locator('.nutrition-report-targets')
        .filter({ hasText: 'Изменения цели в периоде' });
      await expect(targetChanges).toBeVisible();
      const cards = targetChanges.locator('ol > li');
      await expect(cards).toHaveCount(2);
      await expect(cards.first().getByText('Принятая адаптация', { exact: true })).toBeVisible();
      await expect(cards.last().getByText('Цель тренера', { exact: true })).toBeVisible();
      for (const card of await cards.all()) {
        for (const label of ['Дата', 'Источник', 'Калории', 'Б / Ж / У']) {
          await expect(card.getByText(label, { exact: true })).toBeVisible();
        }
      }

      // Layout stress only: keep valid API enums and model a longer localized label in the DOM.
      const source = cards.first().locator('.nutrition-report-targets__content--source');
      await source.evaluate((element) => {
        element.textContent = 'Принятая адаптация по согласованному индивидуальному плану питания';
      });
      await expect(source).toContainText('индивидуальному плану питания');

      const geometry = await targetChanges.evaluate((element) => {
        const viewport = document.documentElement.clientWidth;
        const heading = element.querySelector<HTMLElement>('h3');
        const list = element.querySelector<HTMLElement>('ol');
        const firstCard = element.querySelector<HTMLElement>('ol > li');
        const secondCard = element.querySelector<HTMLElement>('ol > li:nth-child(2)');
        if (!heading || !list || !firstCard || !secondCard)
          throw new Error('Target changes geometry is incomplete');
        const headingBox = heading.getBoundingClientRect();
        const firstCardBox = firstCard.getBoundingClientRect();
        const secondCardBox = secondCard.getBoundingClientRect();
        const rowGap = Number.parseFloat(getComputedStyle(element).rowGap);
        const listStyle = getComputedStyle(list);
        return {
          viewport,
          documentWidth: document.documentElement.scrollWidth,
          rowGap,
          headingToFirstCard: firstCardBox.top - headingBox.bottom,
          cardRowGap: Number.parseFloat(listStyle.rowGap),
          firstToSecondCard: secondCardBox.top - firstCardBox.bottom,
          listBorderWidths: [
            listStyle.borderTopWidth,
            listStyle.borderRightWidth,
            listStyle.borderBottomWidth,
            listStyle.borderLeftWidth,
          ],
          cards: [...element.querySelectorAll<HTMLElement>('ol > li')].map((cardElement) => {
            const box = cardElement.getBoundingClientRect();
            const descendants = [...cardElement.querySelectorAll<HTMLElement>('*')].map((child) => {
              const childBox = child.getBoundingClientRect();
              return { left: childBox.left, right: childBox.right };
            });
            return {
              left: box.left,
              right: box.right,
              width: box.width,
              descendants,
            };
          }),
        };
      });
      expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewport);
      expect(geometry.rowGap).toBeGreaterThanOrEqual(12);
      expect(geometry.headingToFirstCard).toBeGreaterThanOrEqual(geometry.rowGap - 0.5);
      expect(geometry.firstToSecondCard).toBeGreaterThanOrEqual(12);
      expect(geometry.cardRowGap).toBeGreaterThanOrEqual(12);
      expect(geometry.firstToSecondCard).toBeCloseTo(geometry.cardRowGap, 1);
      expect(geometry.listBorderWidths).toEqual(['0px', '0px', '0px', '0px']);
      for (const card of geometry.cards) {
        expect(card.width).toBeGreaterThan(0);
        expect(card.left).toBeGreaterThanOrEqual(-1);
        expect(card.right).toBeLessThanOrEqual(geometry.viewport + 1);
        for (const child of card.descendants) {
          expect(child.left).toBeGreaterThanOrEqual(card.left - 1);
          expect(child.right).toBeLessThanOrEqual(card.right + 1);
        }
      }

      if (CAPTURE_970_AFTER) {
        await mkdir(ISSUE_970_AFTER_DIR, { recursive: true });
        await targetChanges.screenshot({
          path: resolve(ISSUE_970_AFTER_DIR, `${testInfo.project.name}-${theme}-${width}.png`),
        });
        await writeFile(
          resolve(ISSUE_970_AFTER_DIR, `${testInfo.project.name}-${theme}-${width}-geometry.json`),
          JSON.stringify(
            { browser: testInfo.project.name, theme, width, height: 932, geometry },
            null,
            2,
          ) + '\n',
        );
      }

      if (width === 390) {
        const list = targetChanges.locator('ol');
        await page.emulateMedia({ media: 'print' });
        await expect(list).toHaveCSS('row-gap', 'normal');
        await expect(list).toHaveCSS('border-top-width', '1px');
        await page.emulateMedia({ media: 'screen' });
        await page.setViewportSize({ width: 1280, height: 932 });
        await expect(list).toHaveCSS('row-gap', 'normal');
        await expect(list).toHaveCSS('border-top-width', '1px');
        await expect(report.locator('.nutrition-report-days table')).toHaveCSS('display', 'table');
      }
    });
  }
}

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

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Питание/ })
    .click();

  const report = page.locator('#nutrition-period-report');
  await expect(report.getByText('Заполнено 0 из 30 дней')).toBeVisible();
  await expect(report.getByText('Нет заполненных дней за период')).toBeVisible();
  await expect(report.getByRole('link', { name: 'Открыть дневник питания' })).toHaveAttribute(
    'href',
    '/app?section=nutrition',
  );
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
  const historyCard = page.locator('.workout-history-card');
  await expect(historyCard).toHaveAttribute('open', '');
  const feedbackDisclosure = page.locator('#workout-history-43 .workout-feedback-disclosure');
  await expect(feedbackDisclosure).toHaveAttribute('open', '');
  await expect(feedbackDisclosure.locator('.workout-feedback__body')).toContainText(
    'Держите колени по направлению носков.',
  );
  await expect(page.locator('#workout-comment-7')).toHaveClass(/is-focused/);
  await expect(page.locator('#workout-comment-7')).toHaveCount(1);
  await expect(feedbackDisclosure.getByText('Упражнение · Присед со штангой')).toBeVisible();
  await expect(feedbackDisclosure.getByText('Изменено')).toBeVisible();
  await expect(page.locator('.workout-feedback script')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
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

test('dark progress keeps the compact overview readable', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  await expect(progressOverview(page)).toBeVisible();
  await expect(page.getByText('84%', { exact: true })).toBeVisible();
  await expect(page.locator('.progress-overview__metric')).toHaveCount(4);
  await expect(page.locator('.progress-overview__adherence')).toHaveCount(1);
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(page.locator('.progress-bento__adherence')).toHaveCount(0);
});

test('light progress keeps the compact overview readable', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  await expect(progressOverview(page)).toBeVisible();
  await expect(page.getByText('84%', { exact: true })).toBeVisible();
  await expect(page.locator('.progress-overview__metric')).toHaveCount(4);
  await expect(page.locator('.progress-overview__adherence')).toHaveCount(1);
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
  await expect(page.locator('.progress-bento__adherence')).toHaveCount(0);
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

test('progress overview keeps matching light and dark visual forms for the same data', async ({
  browser,
  baseURL,
}) => {
  test.setTimeout(120_000);
  const surfaces = [
    { name: 'desktop-1440x900', width: 1440, height: 900 },
    { name: 'tablet-768x900', width: 768, height: 900 },
    { name: 'mobile-390x844', width: 390, height: 844 },
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
        path: resolve(TASK_111_SCREENSHOTS, `progress-overview-${surface.name}-${theme}.png`),
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

test('progress header keeps the title row separate from period and report controls', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await mockProgress(page);
  await page.goto('/app?section=progress&progress_period=days_30');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();

  for (const theme of ['light', 'dark'] as const) {
    if (theme === 'dark') {
      await page.evaluate(() => {
        localStorage.setItem('app-theme', 'dark');
        window.dispatchEvent(new CustomEvent('yfc-theme-preference-change'));
      });
    }
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);

    for (const width of [320, 360, 393, 430, 1280, 1440, 1920, 2560]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
      const help = page.locator('.progress-hero__help summary');
      const report = page.getByRole('link', { name: 'Скачать отчёт' });
      const period = page.locator('.progress-hero__period');
      const tabs = period.getByRole('tablist', { name: 'Период прогресса' });

      await expect(help).toBeVisible();
      await expect(report).toBeVisible();
      await expect(tabs.getByRole('tab')).toHaveCount(4);
      await expect(page.locator('.progress-hero')).toHaveCSS('border-bottom-width', '0px');
      const selectorGeometry = await tabs.evaluate((element) => {
        const tabStyle = getComputedStyle(element);
        const wrapperStyle = getComputedStyle(element.parentElement!);
        return {
          radius: tabStyle.borderTopLeftRadius,
          overflowX: wrapperStyle.overflowX,
          overflowY: wrapperStyle.overflowY,
        };
      });
      expect(selectorGeometry.radius).not.toBe('0px');
      expect(selectorGeometry.overflowX).toBe('auto');
      expect(selectorGeometry.overflowY).toBe('hidden');
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);

      const helpGeometry = await help.evaluate((summary) => {
        const textNode = Array.from(summary.childNodes).find(
          (node) => node.nodeType === Node.TEXT_NODE,
        );
        const range = document.createRange();
        if (textNode) range.selectNodeContents(textNode);
        const textRects = textNode ? Array.from(range.getClientRects()) : [];
        const summaryBox = summary.getBoundingClientRect();
        const summaryStyle = getComputedStyle(summary);
        return {
          textRectCount: textRects.length,
          textWidths: textRects.map((rect) => Math.round(rect.width * 100) / 100),
          height: summaryBox.height,
          width: summaryBox.width,
          x: summaryBox.x,
          right: summaryBox.right,
          top: summaryBox.top,
          bottom: summaryBox.bottom,
          viewportWidth: window.innerWidth,
          minHeight: parseFloat(summaryStyle.minHeight),
        };
      });
      const boxes = await page.evaluate(() => {
        const rect = (selector: string) => {
          const element = document.querySelector<HTMLElement>(selector);
          if (!element) return null;
          const value = element.getBoundingClientRect();
          return {
            bottom: value.bottom,
            left: value.left,
            right: value.right,
            top: value.top,
          };
        };
        return {
          heading: rect('.progress-hero__heading'),
          title: rect('.progress-hero__copy h1'),
          help: rect('.progress-hero__help summary'),
          report: rect('.progress-hero__download'),
          period: rect('.progress-hero__period'),
        };
      });
      expect(boxes.heading).not.toBeNull();
      expect(boxes.title).not.toBeNull();
      expect(boxes.help).not.toBeNull();
      expect(boxes.report).not.toBeNull();
      expect(boxes.period).not.toBeNull();
      expect(helpGeometry.top).toBeLessThan(boxes.title!.bottom);
      expect(helpGeometry.bottom).toBeGreaterThan(boxes.title!.top);
      expect(boxes.help!.right).toBeLessThanOrEqual(boxes.heading!.right + 0.5);
      if (width <= 430) {
        expect(boxes.period!.left).toBeGreaterThanOrEqual(boxes.heading!.left - 0.5);
        expect(boxes.period!.right).toBeLessThanOrEqual(boxes.heading!.right + 0.5);
        expect(boxes.period!.top).toBeGreaterThanOrEqual(boxes.heading!.bottom - 1);
        expect(boxes.report!.left).toBeGreaterThanOrEqual(boxes.period!.left);
        expect(boxes.report!.top).toBeGreaterThanOrEqual(boxes.period!.bottom - 1);
        expect(
          helpGeometry.textRectCount,
          `wrapped at ${width}px: ${JSON.stringify(helpGeometry)}`,
        ).toBe(1);
        expect(helpGeometry.height, `touch target at ${width}px`).toBeGreaterThanOrEqual(44);
        expect(helpGeometry.right, `overflow at ${width}px`).toBeLessThanOrEqual(
          helpGeometry.viewportWidth,
        );
      }
      if (width >= 1280) {
        expect(boxes.period!.left).toBeGreaterThanOrEqual(boxes.heading!.right + 1);
        expect(boxes.help!.right).toBeLessThan(boxes.period!.left);
        expect(boxes.report!.left).toBeGreaterThanOrEqual(boxes.period!.left);
        expect(boxes.report!.top).toBeGreaterThanOrEqual(boxes.period!.bottom - 1);
      }
    }
  }
});

test('progress header keeps expanded help and custom period in normal flow', async ({ page }) => {
  test.setTimeout(120_000);
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await mockProgress(page);
  await page.goto('/app?section=progress&progress_period=days_30');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();

  const captureDirectory = CAPTURE_PROGRESS_865
    ? resolve(
        process.cwd(),
        '..',
        'docs',
        'ux',
        'final-issues-acceptance',
        'evidence',
        '865',
        CAPTURE_PROGRESS_865,
      )
    : null;

  for (const theme of ['light', 'dark'] as const) {
    if (theme === 'dark') {
      await page.evaluate(() => {
        localStorage.setItem('app-theme', 'dark');
        window.dispatchEvent(new CustomEvent('yfc-theme-preference-change'));
      });
    }
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);

    for (const width of [320, 360, 390, 393, 430, 1280, 1440, 1920, 2560]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
      const summary = page.locator('.progress-hero__help summary');
      const helpBody = page.locator('.progress-hero__help .contextual-help__body');
      const period = page.locator('.progress-hero__period');
      const customTab = period.getByRole('tab', { name: 'Свой период' });
      const customForm = period.locator('.progress-period-controls__custom');

      await expect(summary).toHaveAttribute('aria-expanded', 'false');
      await expect(customForm).toBeHidden();

      const measureGeometry = async () =>
        page.evaluate(() => {
          type Box = { bottom: number; left: number; right: number; top: number; width: number };
          const box = (selector: string): Box | null => {
            const element = document.querySelector<HTMLElement>(selector);
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            return {
              top: rect.top,
              right: rect.right,
              bottom: rect.bottom,
              left: rect.left,
              width: rect.width,
            };
          };
          const boxes = {
            heading: box('.progress-hero__copy h1'),
            headingRegion: box('.progress-hero__heading'),
            summary: box('.progress-hero__help summary'),
            helpBody: box('.progress-hero__help .contextual-help__body'),
            period: box('.progress-hero__period'),
            custom: box('.progress-period-controls__custom'),
            from: box('#progress-period-from'),
            to: box('#progress-period-to'),
            actions: box('.progress-period-controls__custom-actions'),
            download: box('.progress-hero__download'),
          };
          const overlaps = (left: Box | null, right: Box | null) =>
            Boolean(
              left &&
              right &&
              left.left < right.right &&
              left.right > right.left &&
              left.top < right.bottom &&
              left.bottom > right.top,
            );
          const topLevel = ['heading', 'summary', 'period', 'download'] as const;
          const internal = ['from', 'to', 'actions'] as const;
          const overlapPairs = [
            ...topLevel.flatMap((left, index) =>
              topLevel.slice(index + 1).map((right) => `${left}:${right}`),
            ),
            ...internal.flatMap((left, index) =>
              internal.slice(index + 1).map((right) => `${left}:${right}`),
            ),
            'helpBody:period',
            'helpBody:custom',
            'helpBody:download',
          ] as const;
          const outOfViewport = Object.entries(boxes)
            .filter(([, value]) => value)
            .filter(([, value]) => value!.left < -0.5 || value!.right > window.innerWidth + 0.5)
            .map(([name]) => name);
          return {
            boxes,
            overlapPairs: overlapPairs.filter((pair) => {
              const [left, right] = pair.split(':') as [keyof typeof boxes, keyof typeof boxes];
              return overlaps(boxes[left], boxes[right]);
            }),
            outOfViewport,
            scrollWidth: document.documentElement.scrollWidth,
            viewportWidth: window.innerWidth,
          };
        });

      const assertGeometry = async (state: string) => {
        const geometry = await measureGeometry();
        expect(
          geometry.overlapPairs,
          `${theme} ${width}px ${state}: ${JSON.stringify(geometry)}`,
        ).toEqual([]);
        expect(geometry.outOfViewport, `${theme} ${width}px ${state}`).toEqual([]);
        expect(geometry.scrollWidth, `${theme} ${width}px ${state}`).toBeLessThanOrEqual(
          geometry.viewportWidth,
        );
        const headingRegionBox = geometry.boxes.headingRegion;
        const headingBox = geometry.boxes.heading;
        const summaryBox = geometry.boxes.summary;
        expect(headingRegionBox).not.toBeNull();
        expect(headingBox).not.toBeNull();
        expect(summaryBox).not.toBeNull();
        expect(
          summaryBox!.top,
          `${theme} ${width}px ${state}: ${JSON.stringify(geometry)}`,
        ).toBeLessThan(headingBox!.bottom);
        expect(
          summaryBox!.bottom,
          `${theme} ${width}px ${state}: ${JSON.stringify(geometry)}`,
        ).toBeGreaterThan(headingBox!.top);
        if (state.includes('help')) {
          const helpBodyBox = geometry.boxes.helpBody;
          expect(helpBodyBox, `${theme} ${width}px ${state} help body`).not.toBeNull();
          expect(helpBodyBox!.left).toBeGreaterThanOrEqual(headingRegionBox!.left - 0.5);
          expect(helpBodyBox!.right).toBeLessThanOrEqual(headingRegionBox!.right + 0.5);
          expect(
            helpBodyBox!.top,
            `${theme} ${width}px ${state}: ${JSON.stringify(geometry)}`,
          ).toBeGreaterThanOrEqual(Math.max(headingBox!.bottom, summaryBox!.bottom) - 0.5);
        }
        if (state.includes('custom')) {
          expect(geometry.boxes.custom).not.toBeNull();
          expect(geometry.boxes.from).not.toBeNull();
          expect(geometry.boxes.to).not.toBeNull();
          expect(geometry.boxes.actions).not.toBeNull();
          const dateContract = await page.locator('#progress-period-from').evaluate((input) => {
            const style = getComputedStyle(input);
            const webkitValue = getComputedStyle(input, '::-webkit-date-and-time-value');
            const control = input.closest('.date-control');
            return {
              value: (input as HTMLInputElement).value,
              width: input.getBoundingClientRect().width,
              textAlign: style.textAlign,
              textAlignLast: style.textAlignLast,
              overflow: style.overflow,
              controlOverflow: control ? getComputedStyle(control).overflow : null,
              webkitTextAlign: webkitValue.textAlign,
            };
          });
          expect(dateContract.value).toBe('2025-01-01');
          expect(dateContract.width).toBeGreaterThanOrEqual(140);
          expect(dateContract.textAlign).toBe('start');
          expect(dateContract.textAlignLast).toBe('start');
          expect(['clip', 'visible']).toContain(dateContract.overflow);
          expect(dateContract.controlOverflow).toBe('visible');
          // WebKit does not expose this pseudo-element through computed styles.
          expect(['', 'start']).toContain(dateContract.webkitTextAlign);
        }
        if (captureDirectory) {
          await mkdir(captureDirectory, { recursive: true });
          await page.locator('.progress-hero').screenshot({
            path: resolve(
              captureDirectory,
              `${test.info().project.name}-${width}-${theme}-${state}.png`,
            ),
          });
        }
      };

      await assertGeometry('closed-closed');

      await summary.focus();
      await page.keyboard.press('Enter');
      await expect(summary).toHaveAttribute('aria-expanded', 'true');
      await expect(summary).toBeFocused();
      await expect(helpBody).toBeVisible();
      await assertGeometry('help-open');

      await summary.focus();
      await page.keyboard.press('Enter');
      await expect(summary).toHaveAttribute('aria-expanded', 'false');
      await expect(summary).toBeFocused();
      await expect(helpBody).toBeHidden();

      await customTab.click();
      await expect(customForm).toBeVisible();
      await page.getByLabel('Начало периода').fill('2025-01-01');
      await page.getByLabel('Конец периода').fill('2025-01-30');
      await assertGeometry('custom-open');

      await summary.click();
      await expect(summary).toHaveAttribute('aria-expanded', 'true');
      await expect(helpBody).toBeVisible();
      await assertGeometry('help-and-custom-open');

      await summary.focus();
      await page.keyboard.press('Enter');
      await expect(summary).toHaveAttribute('aria-expanded', 'false');
      await period.getByRole('button', { name: 'Отмена' }).click();
      await expect(customForm).toBeHidden();
    }
  }
});
