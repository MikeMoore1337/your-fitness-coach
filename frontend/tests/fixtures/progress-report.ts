import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { ProgressReport } from '../../src/shared/api/types';

type CanonicalFacts = {
  period: { period: string; start: string; end: string; timezone: string };
  subject: { name: string; role: string; goal: string };
  training: {
    planned_workouts: number;
    completed_workouts: number;
    skipped_workouts: number;
    frequency_per_week: number;
    completed_working_sets: number;
    external_load_volume_kg: number;
    volume_recorded_sets: number;
    new_personal_records: number;
    exercises: Array<{
      exercise_title: string;
      performed_session_count: number;
      completed_set_count: number;
      first_performed_on: string;
      last_performed_on: string;
      reps_total: number;
      max_external_load_kg: number;
      external_load_volume_kg: number;
      volume_recorded_sets: number;
      sessions: Array<{
        performed_on: string;
        completed_set_count: number;
        max_external_load_kg: number;
        external_load_volume_kg: number;
      }>;
    }>;
  };
  cardio: { completed_sessions: number; duration_minutes: number };
  nutrition: {
    logged_days: number;
    eligible_days: number;
    missing_days: number;
    logged_date: string;
    target: {
      calories: number;
      protein_g: number;
      fat_g: number;
      carbs_g: number;
    };
    exact_entry_count: number;
    approximate_entry_count: number;
    partial_entry_count: number;
    calories_average: number;
    protein_g_average: number;
    fat_g_average: number;
    carbs_g_average: number;
  };
  body: Array<{
    metric: string;
    label: string;
    unit: 'kg' | 'cm';
    first_value: number;
    latest_value: number;
    change: number;
    first_measured_on: string;
    latest_measured_on: string;
    point_count: number;
    span_days: number;
  }>;
  privacy: string[];
};

export const canonicalFacts = JSON.parse(
  readFileSync(resolve(process.cwd(), '../tests/fixtures/progress-report-canonical.json'), 'utf8'),
) as CanonicalFacts;

type ReportState = 'empty' | 'full' | 'partial';
type SufficiencyReason =
  ProgressReport['data_sufficiency']['workout_logging']['reason_keys'][number];

function signal(
  status: 'sufficient' | 'limited' | 'insufficient',
  counters: Record<string, number>,
  ...reasonKeys: SufficiencyReason[]
) {
  return { status, counters, reason_keys: reasonKeys };
}

function component(percent: number | null, achieved: number, evaluated: number, weight: number) {
  return {
    status: percent == null ? ('insufficient_data' as const) : ('available' as const),
    percent,
    achieved,
    evaluated,
    weight,
    reason: percent == null ? 'insufficient_data' : null,
  };
}

export function makeProgressReportFixture(state: ReportState = 'full'): ProgressReport {
  const populated = state !== 'empty';
  const full = state === 'full';
  const weightPoints = populated
    ? [
        { measured_on: '2026-07-28', value: 82.4 },
        { measured_on: '2026-08-10', value: 81.6 },
        { measured_on: '2026-08-23', value: 80.9 },
      ]
    : [];
  const metric = (average: number | null, sampleDays: number) => ({
    average,
    minimum: average,
    maximum: average,
    sample_days: sampleDays,
  });
  const comparison = (actual: number | null, target: number | null, days: number) => ({
    average_actual: actual,
    average_target: target,
    average_deviation: actual != null && target != null ? actual - target : null,
    evaluated_days: days,
  });

  return {
    generated_at: '2026-08-24T09:30:00+03:00',
    period: 'days_30',
    period_start: '2026-07-26',
    period_end: '2026-08-24',
    timezone: 'Europe/Moscow',
    subject: {
      name: full
        ? 'Александр Константинович Очень-Длинная-Фамилия Для Проверки Переносов'
        : 'Александр Петров',
      role: 'self',
      goal: 'muscle_gain',
    },
    training: {
      planned_workouts: populated ? 12 : 0,
      completed_workouts: populated ? 9 : 0,
      skipped_workouts: populated ? 1 : 0,
      frequency_per_week: populated ? 2.1 : 0,
      completed_working_sets: populated ? 84 : 0,
      external_load_volume_kg: populated ? 48620 : null,
      volume_recorded_sets: populated ? 80 : 0,
      new_personal_records: populated ? 3 : 0,
      exercises: populated
        ? [
            {
              exercise_title:
                'Жим штанги лёжа с контролируемой паузой и очень длинным уточнением варианта',
              performed_session_count: 4,
              completed_set_count: 16,
              first_performed_on: '2026-07-29',
              last_performed_on: '2026-08-22',
              reps_total: 124,
              max_external_load_kg: 92.5,
              external_load_volume_kg: 9840,
              volume_recorded_sets: 16,
              sessions: [
                {
                  performed_on: '2026-07-29',
                  completed_set_count: 4,
                  max_external_load_kg: 85,
                  external_load_volume_kg: 2240,
                },
                {
                  performed_on: '2026-08-22',
                  completed_set_count: 4,
                  max_external_load_kg: 92.5,
                  external_load_volume_kg: 2520,
                },
              ],
            },
            {
              exercise_title: 'Приседание со штангой',
              performed_session_count: 4,
              completed_set_count: 14,
              first_performed_on: '2026-07-27',
              last_performed_on: '2026-08-20',
              reps_total: 108,
              max_external_load_kg: 120,
              external_load_volume_kg: 12600,
              volume_recorded_sets: 14,
              sessions: [
                {
                  performed_on: '2026-07-27',
                  completed_set_count: 3,
                  max_external_load_kg: 110,
                  external_load_volume_kg: 2860,
                },
                {
                  performed_on: '2026-08-20',
                  completed_set_count: 4,
                  max_external_load_kg: 120,
                  external_load_volume_kg: 3240,
                },
              ],
            },
          ]
        : [],
    },
    cardio: {
      completed_sessions: populated ? 5 : 0,
      planned_sessions: populated ? 1 : 0,
      frequency_per_week: populated ? 1.17 : 0,
      duration_minutes: populated ? 178 : 0,
      distance_km: populated ? 19.4 : null,
      zone_duration: populated ? [{ zone: 2, duration_minutes: 96 }] : [],
    },
    body: {
      latest_measurement: populated
        ? {
            measured_on: '2026-08-23',
            weight_kg: 80.9,
            chest_cm: 104.5,
            waist_cm: 84.2,
            hips_cm: null,
            biceps_cm: null,
            thigh_cm: null,
          }
        : null,
      trends: populated
        ? [
            {
              metric: 'weight_kg',
              label: 'Вес',
              unit: 'kg',
              first_value: 82.4,
              latest_value: 80.9,
              change: -1.5,
              first_measured_on: '2026-07-28',
              latest_measured_on: '2026-08-23',
              point_count: 3,
              span_days: 26,
              interpretation_status: 'available',
              points: weightPoints,
            },
            {
              metric: 'waist_cm',
              label: 'Талия',
              unit: 'cm',
              first_value: 86.1,
              latest_value: 84.2,
              change: -1.9,
              first_measured_on: '2026-07-28',
              latest_measured_on: '2026-08-23',
              point_count: 3,
              span_days: 26,
              interpretation_status: 'available',
              points: [
                { measured_on: '2026-07-28', value: 86.1 },
                { measured_on: '2026-08-10', value: 85 },
                { measured_on: '2026-08-23', value: 84.2 },
              ],
            },
            {
              metric: 'custom:17',
              label: 'Живот',
              unit: 'cm',
              definition_id: 17,
              first_value: 86,
              latest_value: 84,
              change: -2,
              first_measured_on: '2026-07-28',
              latest_measured_on: '2026-08-23',
              point_count: 3,
              span_days: 26,
              interpretation_status: 'available',
              points: [
                { measured_on: '2026-07-28', value: 86 },
                { measured_on: '2026-08-10', value: 85 },
                { measured_on: '2026-08-23', value: 84 },
              ],
            },
          ]
        : [],
      priority: { mode: 'balanced', muscle_group_ids: [] },
      guidance: {
        comparison_basis: 'self',
        minimum_points_for_interpretation: 3,
        minimum_span_days_for_interpretation: 14,
        consistency_tips: ['Снимайте замеры в одинаковых условиях.'],
        circumference_limitations: ['Окружность не измеряет отдельную мышцу.'],
      },
    },
    nutrition: {
      period: 'days_30',
      period_start: '2026-07-26',
      period_end: '2026-08-24',
      timezone: 'Europe/Moscow',
      summary: {
        logged_days: populated ? 24 : 0,
        eligible_days: 30,
        coverage_percent: populated ? 80 : 0,
        complete_days: populated ? 22 : 0,
        incomplete_days: populated ? 2 : 0,
        fasted_days: 0,
        missing_days: populated ? 6 : 30,
        current_day_status: 'missing',
        calories: metric(populated ? 2184 : null, populated ? 22 : 0),
        protein_g: metric(populated ? 158 : null, populated ? 22 : 0),
        fat_g: metric(populated ? 72 : null, populated ? 22 : 0),
        carbs_g: metric(populated ? 226 : null, populated ? 22 : 0),
        calorie_comparison: comparison(
          populated ? 2184 : null,
          populated ? 2200 : null,
          populated ? 22 : 0,
        ),
        protein_comparison: comparison(
          populated ? 158 : null,
          populated ? 160 : null,
          populated ? 22 : 0,
        ),
        fat_comparison: comparison(
          populated ? 72 : null,
          populated ? 70 : null,
          populated ? 22 : 0,
        ),
        carbs_comparison: comparison(
          populated ? 226 : null,
          populated ? 235 : null,
          populated ? 22 : 0,
        ),
        days_within_calorie_tolerance: populated ? 19 : 0,
        calorie_tolerance_evaluated_days: populated ? 22 : 0,
        days_meeting_protein_target: populated ? 16 : 0,
        protein_target_evaluated_days: populated ? 22 : 0,
        exact_entry_count: 0,
        approximate_entry_count: 0,
        partial_entry_count: 0,
      },
      daily: [],
      target_changes: populated
        ? [
            {
              effective_from: '2026-08-08',
              source: 'trainer',
              calories: 2200,
              protein_g: 160,
              fat_g: 70,
              carbs_g: 235,
            },
          ]
        : [],
    },
    adherence: {
      formula_version: 'adherence-v1',
      overall_percent: populated ? 78.4 : null,
      included_components: populated ? ['workouts', 'calories', 'protein'] : [],
      workouts: component(populated ? 75 : null, populated ? 9 : 0, populated ? 12 : 0, 0.4),
      cardio: component(populated ? 83.3 : null, populated ? 5 : 0, populated ? 6 : 0, 0.2),
      calories: component(populated ? 86.4 : null, populated ? 19 : 0, populated ? 22 : 0, 0.2),
      protein: component(populated ? 72.7 : null, populated ? 16 : 0, populated ? 22 : 0, 0.2),
    },
    data_sufficiency: {
      ruleset_version: 'data-sufficiency-v1',
      workout_logging: signal(
        full ? 'sufficient' : populated ? 'limited' : 'insufficient',
        { completed_workout_count: populated ? 9 : 0 },
        full ? 'thresholds_met' : 'no_completed_workouts',
      ),
      working_sets: signal(
        full ? 'sufficient' : populated ? 'limited' : 'insufficient',
        {
          workout_session_count: populated ? 9 : 0,
          working_set_count: populated ? 84 : 0,
          required_workout_session_count: 2,
          required_working_set_count: 6,
        },
        full ? 'thresholds_met' : 'no_working_sets',
      ),
      rir_coverage: signal(
        'limited',
        { working_set_count: populated ? 84 : 0, recorded_set_count: populated ? 52 : 0 },
        'rir_coverage_too_low',
      ),
      nutrition_coverage: signal(
        full ? 'sufficient' : populated ? 'limited' : 'insufficient',
        { logged_day_count: populated ? 24 : 0, eligible_day_count: 30 },
        full ? 'thresholds_met' : 'no_logged_days',
      ),
      weight_trend: signal(
        full ? 'sufficient' : populated ? 'limited' : 'insufficient',
        {
          point_count: weightPoints.length,
          span_days: populated ? 26 : 0,
          required_point_count: 3,
          required_span_days: 14,
        },
        full ? 'thresholds_met' : 'no_measurements',
      ),
      anthropometry: signal(
        populated ? 'sufficient' : 'insufficient',
        {
          maximum_point_count: populated ? 3 : 0,
          sufficient_metric_count: populated ? 1 : 0,
          required_point_count_per_metric: 3,
          required_span_days_per_metric: 14,
        },
        populated ? 'thresholds_met' : 'no_anthropometry_measurements',
      ),
      schedule_adherence: signal(
        populated ? 'sufficient' : 'insufficient',
        { evaluable_workout_count: populated ? 12 : 0 },
        populated ? 'thresholds_met' : 'no_evaluable_planned_workouts',
      ),
    },
    program: populated
      ? {
          title: 'Силовая база — второй мезоцикл',
          status: 'active',
          start_date: '2026-07-01',
          duration_weeks: 10,
          active_block: {
            title: 'Накопление рабочего объёма',
            start_date: '2026-08-01',
            end_date: '2026-08-28',
            purpose: 'Постепенно наращивать рабочий объём без причинных выводов по самочувствию.',
            is_deload: false,
            status: 'active',
          },
          changes: [{ changed_on: '2026-08-08', change_kind: 'block_updated' }],
        }
      : null,
    check_ins: populated
      ? [
          {
            week_start: '2026-08-17',
            week_end: '2026-08-23',
            submitted_on: '2026-08-23',
            status: 'completed',
            training_load: 4,
            recovery: 3,
            hunger: 2,
            adherence_difficulty: 2,
          },
        ]
      : [],
    wellbeing: populated
      ? {
          period_start: '2026-07-26',
          period_end: '2026-08-24',
          eligible_days: 30,
          recorded_days: full ? 6 : 2,
          coverage_percent: full ? 20 : 6.7,
          sleep: {
            recorded_days: full ? 5 : 2,
            distribution: [
              { value: 1, count: 0 },
              { value: 2, count: full ? 1 : 0 },
              { value: 3, count: full ? 1 : 1 },
              { value: 4, count: full ? 2 : 1 },
              { value: 5, count: full ? 1 : 0 },
            ],
            trend: full ? 'improving' : 'insufficient_data',
          },
          mood: {
            recorded_days: full ? 5 : 2,
            distribution: [
              { value: 1, count: 0 },
              { value: 2, count: full ? 1 : 0 },
              { value: 3, count: full ? 2 : 2 },
              { value: 4, count: full ? 1 : 0 },
              { value: 5, count: full ? 1 : 0 },
            ],
            trend: full ? 'stable' : 'insufficient_data',
          },
          daily: [
            {
              local_date: '2026-08-19',
              sleep_quality: 3,
              sleep_duration_minutes: 390,
              mood: 3,
              source: 'manual',
            },
            ...(full
              ? [
                  {
                    local_date: '2026-08-20',
                    sleep_quality: null,
                    sleep_duration_minutes: 420,
                    mood: null,
                    source: 'manual' as const,
                  },
                ]
              : []),
            {
              local_date: '2026-08-21',
              sleep_quality: 4,
              sleep_duration_minutes: 450,
              mood: 4,
              source: 'manual',
            },
            ...(full
              ? [
                  {
                    local_date: '2026-08-22',
                    sleep_quality: 4,
                    sleep_duration_minutes: 420,
                    mood: 3,
                    source: 'manual' as const,
                  },
                  {
                    local_date: '2026-08-23',
                    sleep_quality: 5,
                    sleep_duration_minutes: 480,
                    mood: 5,
                    source: 'manual' as const,
                  },
                  {
                    local_date: '2026-08-24',
                    sleep_quality: 4,
                    sleep_duration_minutes: 420,
                    mood: 3,
                    source: 'manual' as const,
                  },
                ]
              : []),
          ],
        }
      : null,
  };
}

export function makeCanonicalProgressReportFixture(): ProgressReport {
  const report = makeProgressReportFixture('empty');
  const periodStart = canonicalFacts.period.start;
  const periodEnd = canonicalFacts.period.end;
  const periodDays = canonicalFacts.nutrition.eligible_days;
  const addDays = (value: string, offset: number) => {
    const date = new Date(`${value}T12:00:00Z`);
    date.setUTCDate(date.getUTCDate() + offset);
    return date.toISOString().slice(0, 10);
  };
  const percentage = (achieved: number, evaluated: number) =>
    evaluated > 0 ? Number(((achieved * 100) / evaluated).toFixed(1)) : null;

  report.generated_at = `${periodEnd}T09:30:00+03:00`;
  report.period = canonicalFacts.period.period as ProgressReport['period'];
  report.period_start = periodStart;
  report.period_end = periodEnd;
  report.timezone = canonicalFacts.period.timezone;
  report.subject = canonicalFacts.subject as ProgressReport['subject'];

  report.training.planned_workouts = canonicalFacts.training.planned_workouts;
  report.training.completed_workouts = canonicalFacts.training.completed_workouts;
  report.training.skipped_workouts = canonicalFacts.training.skipped_workouts;
  report.training.frequency_per_week = canonicalFacts.training.frequency_per_week;
  report.training.completed_working_sets = canonicalFacts.training.completed_working_sets;
  report.training.external_load_volume_kg = canonicalFacts.training.external_load_volume_kg;
  report.training.volume_recorded_sets = canonicalFacts.training.volume_recorded_sets;
  report.training.new_personal_records = canonicalFacts.training.new_personal_records;
  report.training.exercises = canonicalFacts.training.exercises;

  report.cardio.completed_sessions = canonicalFacts.cardio.completed_sessions;
  report.cardio.planned_sessions = 0;
  report.cardio.duration_minutes = canonicalFacts.cardio.duration_minutes;
  report.cardio.frequency_per_week = 0;
  report.cardio.distance_km = null;
  report.cardio.zone_duration = [];

  const weightTrend = canonicalFacts.body[0]!;
  const waistTrend = canonicalFacts.body[1]!;
  report.body.latest_measurement = {
    measured_on: waistTrend.latest_measured_on,
    weight_kg: weightTrend.latest_value,
    chest_cm: null,
    waist_cm: waistTrend.latest_value,
    hips_cm: null,
    biceps_cm: null,
    thigh_cm: null,
    custom_measurements: [],
  };
  report.body.trends = canonicalFacts.body.map((trend) => ({
    metric: trend.metric,
    label: trend.label,
    unit: trend.unit,
    first_value: trend.first_value,
    latest_value: trend.latest_value,
    change: trend.change,
    first_measured_on: trend.first_measured_on,
    latest_measured_on: trend.latest_measured_on,
    point_count: trend.point_count,
    span_days: trend.span_days,
    interpretation_status:
      trend.point_count === 1
        ? 'single_point'
        : trend.point_count < 3
          ? 'insufficient_points'
          : trend.span_days < 14
            ? 'insufficient_period'
            : 'available',
    points: [
      { measured_on: trend.first_measured_on, value: trend.first_value },
      { measured_on: trend.latest_measured_on, value: trend.latest_value },
    ],
  }));
  report.body.priority = null;
  report.body.guidance = {
    comparison_basis: 'self',
    minimum_points_for_interpretation: 3,
    minimum_span_days_for_interpretation: 14,
    consistency_tips: [
      'Снимайте замеры в похожее время суток и в одинаковых условиях.',
      'Используйте одну технику и одно место наложения измерительной ленты.',
      'Оценивайте последовательность замеров, а не отдельное колебание.',
    ],
    circumference_limitations: [
      'Окружность плеча не измеряет отдельно бицепс или трицепс.',
      'Окружность бедра не измеряет отдельно квадрицепс или другие мышцы бедра.',
      'Окружности сами по себе не показывают рост конкретной мышцы.',
    ],
  };

  report.nutrition.period = canonicalFacts.period.period as ProgressReport['nutrition']['period'];
  report.nutrition.period_start = periodStart;
  report.nutrition.period_end = periodEnd;
  report.nutrition.timezone = canonicalFacts.period.timezone;
  const summary = report.nutrition.summary;
  summary.logged_days = canonicalFacts.nutrition.logged_days;
  summary.eligible_days = periodDays;
  summary.coverage_percent = Number(
    ((canonicalFacts.nutrition.logged_days * 100) / periodDays).toFixed(1),
  );
  summary.complete_days = canonicalFacts.nutrition.logged_days;
  summary.incomplete_days = 0;
  summary.fasted_days = 0;
  summary.missing_days = canonicalFacts.nutrition.missing_days;
  summary.current_day_status = null;
  for (const [key, value] of [
    ['calories', canonicalFacts.nutrition.calories_average],
    ['protein_g', canonicalFacts.nutrition.protein_g_average],
    ['fat_g', canonicalFacts.nutrition.fat_g_average],
    ['carbs_g', canonicalFacts.nutrition.carbs_g_average],
  ] as const) {
    const metric = report.nutrition.summary[key]!;
    metric.average = value;
    metric.minimum = value;
    metric.maximum = value;
    metric.sample_days = canonicalFacts.nutrition.logged_days;
  }
  const target = canonicalFacts.nutrition.target;
  summary.calorie_comparison = {
    average_actual: canonicalFacts.nutrition.calories_average,
    average_target: target.calories,
    average_deviation: canonicalFacts.nutrition.calories_average - target.calories,
    evaluated_days: canonicalFacts.nutrition.logged_days,
  };
  summary.protein_comparison = {
    average_actual: canonicalFacts.nutrition.protein_g_average,
    average_target: target.protein_g,
    average_deviation: canonicalFacts.nutrition.protein_g_average - target.protein_g,
    evaluated_days: canonicalFacts.nutrition.logged_days,
  };
  summary.fat_comparison = {
    average_actual: canonicalFacts.nutrition.fat_g_average,
    average_target: target.fat_g,
    average_deviation: canonicalFacts.nutrition.fat_g_average - target.fat_g,
    evaluated_days: canonicalFacts.nutrition.logged_days,
  };
  summary.carbs_comparison = {
    average_actual: canonicalFacts.nutrition.carbs_g_average,
    average_target: target.carbs_g,
    average_deviation: canonicalFacts.nutrition.carbs_g_average - target.carbs_g,
    evaluated_days: canonicalFacts.nutrition.logged_days,
  };
  summary.days_within_calorie_tolerance = 1;
  summary.calorie_tolerance_evaluated_days = canonicalFacts.nutrition.logged_days;
  summary.days_meeting_protein_target = 0;
  summary.protein_target_evaluated_days = canonicalFacts.nutrition.logged_days;
  summary.exact_entry_count = canonicalFacts.nutrition.exact_entry_count;
  summary.approximate_entry_count = canonicalFacts.nutrition.approximate_entry_count;
  summary.partial_entry_count = canonicalFacts.nutrition.partial_entry_count;
  report.nutrition.daily = Array.from({ length: periodDays }, (_, offset) => {
    const diaryDate = addDays(periodStart, offset);
    const logged = diaryDate === canonicalFacts.nutrition.logged_date;
    return {
      diary_date: diaryDate,
      status: logged ? 'complete' : 'missing',
      is_current_day: false,
      calories: logged ? canonicalFacts.nutrition.calories_average : null,
      protein_g: logged ? canonicalFacts.nutrition.protein_g_average : null,
      fat_g: logged ? canonicalFacts.nutrition.fat_g_average : null,
      carbs_g: logged ? canonicalFacts.nutrition.carbs_g_average : null,
      fiber_g: null,
      target_calories: target.calories,
      target_protein_g: target.protein_g,
      target_fat_g: target.fat_g,
      target_carbs_g: target.carbs_g,
      calorie_deviation: logged
        ? canonicalFacts.nutrition.calories_average - target.calories
        : null,
      protein_deviation_g: logged
        ? canonicalFacts.nutrition.protein_g_average - target.protein_g
        : null,
      fat_deviation_g: logged ? canonicalFacts.nutrition.fat_g_average - target.fat_g : null,
      carbs_deviation_g: logged ? canonicalFacts.nutrition.carbs_g_average - target.carbs_g : null,
      within_calorie_tolerance: logged ? true : null,
      meets_protein_target: logged ? false : null,
      target_changed: false,
      hydration_ml: null,
      hydration_target_ml: null,
      hydration_progress_percent: null,
    };
  });
  report.nutrition.target_changes = [];
  report.nutrition.insights = [];
  report.adherence = {
    formula_version: 'adherence-v1',
    overall_percent: 50,
    included_components: ['workouts', 'calories', 'protein'],
    workouts: component(
      percentage(
        canonicalFacts.training.completed_workouts,
        canonicalFacts.training.planned_workouts,
      ),
      canonicalFacts.training.completed_workouts,
      canonicalFacts.training.planned_workouts,
      0.4,
    ),
    cardio: {
      status: 'not_applicable',
      percent: null,
      achieved: 0,
      evaluated: 0,
      weight: 0.2,
      reason: 'cardio_not_planned',
    },
    calories: component(
      100,
      summary.days_within_calorie_tolerance,
      summary.calorie_tolerance_evaluated_days,
      0.2,
    ),
    protein: component(
      0,
      summary.days_meeting_protein_target,
      summary.protein_target_evaluated_days,
      0.2,
    ),
  };
  report.data_sufficiency = {
    ruleset_version: 'data-sufficiency-v1',
    workout_logging: signal(
      'sufficient',
      {
        completed_workout_count: canonicalFacts.training.completed_workouts,
        prescribed_set_count: canonicalFacts.training.completed_working_sets,
        logged_set_count: canonicalFacts.training.completed_working_sets,
        coverage_percent: 100,
      },
      'thresholds_met',
    ),
    working_sets: signal(
      'limited',
      {
        workout_session_count: canonicalFacts.training.completed_workouts,
        working_set_count: canonicalFacts.training.completed_working_sets,
        required_workout_session_count: 2,
        required_working_set_count: 6,
      },
      'too_few_working_sets',
      'too_few_workout_sessions',
    ),
    rir_coverage: signal(
      'insufficient',
      {
        working_set_count: canonicalFacts.training.completed_working_sets,
        recorded_set_count: 0,
        required_recorded_set_count: 3,
        coverage_percent: 0,
        required_coverage_percent: 50,
      },
      'no_rir_observations',
    ),
    nutrition_coverage: signal(
      'limited',
      {
        logged_day_count: canonicalFacts.nutrition.logged_days,
        eligible_day_count: canonicalFacts.nutrition.eligible_days,
        required_logged_day_count: 7,
        coverage_percent: summary.coverage_percent,
        exact_entry_count: canonicalFacts.nutrition.exact_entry_count,
        approximate_entry_count: canonicalFacts.nutrition.approximate_entry_count,
        partial_entry_count: canonicalFacts.nutrition.partial_entry_count,
      },
      'below_required_coverage',
    ),
    weight_trend: signal(
      'limited',
      {
        point_count: weightTrend.point_count,
        span_days: weightTrend.span_days,
        required_point_count: 3,
        required_span_days: 14,
      },
      'too_few_points',
    ),
    anthropometry: signal(
      'limited',
      {
        measured_metric_count: 1,
        sufficient_metric_count: 0,
        maximum_point_count: waistTrend.point_count,
        maximum_span_days: waistTrend.span_days,
        required_point_count_per_metric: 3,
        required_span_days_per_metric: 14,
      },
      'too_few_points',
    ),
    schedule_adherence: signal(
      'limited',
      {
        evaluable_workout_count: canonicalFacts.training.planned_workouts,
        required_evaluable_workout_count: 3,
      },
      'too_few_evaluable_workouts',
    ),
  };
  report.program = {
    title: 'Текущая программа',
    status: 'active',
    start_date: '2026-07-27',
    duration_weeks: 8,
    active_block: null,
    changes: [],
  };
  const privateCheckIn = {
    week_start: '2026-08-18',
    week_end: periodEnd,
    submitted_on: canonicalFacts.nutrition.logged_date,
    status: 'completed',
    training_load: 4,
    recovery: 3,
    hunger: 2,
    adherence_difficulty: 2,
    note: 'Скрытая заметка еженедельной отметки',
  };
  report.check_ins = [privateCheckIn as ProgressReport['check_ins'][number]];
  report.wellbeing = null;
  return report;
}

export function assertCanonicalProgressReportInvariants(report: ProgressReport): void {
  const inclusiveDays =
    (Date.parse(`${report.period_end}T12:00:00Z`) -
      Date.parse(`${report.period_start}T12:00:00Z`)) /
      86_400_000 +
    1;
  const { training, nutrition, body, adherence, data_sufficiency: sufficiency } = report;

  if (report.period_start !== canonicalFacts.period.start) throw new Error('period start drift');
  if (report.period_end !== canonicalFacts.period.end) throw new Error('period end drift');
  if (report.timezone !== canonicalFacts.period.timezone) throw new Error('timezone drift');
  if (training.planned_workouts !== training.completed_workouts + training.skipped_workouts) {
    throw new Error('training totals drift');
  }
  if (
    training.frequency_per_week !==
    Number(((training.completed_workouts * 7) / inclusiveDays).toFixed(2))
  ) {
    throw new Error('training frequency drift');
  }
  const exerciseVolume = training.exercises.reduce(
    (total, exercise) => total + (exercise.external_load_volume_kg ?? 0),
    0,
  );
  const exerciseSets = training.exercises.reduce(
    (total, exercise) => total + exercise.volume_recorded_sets,
    0,
  );
  if (
    training.external_load_volume_kg !== exerciseVolume ||
    training.volume_recorded_sets !== exerciseSets
  ) {
    throw new Error('training exercise totals drift');
  }
  for (const exercise of training.exercises) {
    if (exercise.performed_session_count !== exercise.sessions.length) {
      throw new Error('exercise session count drift');
    }
    if (
      exercise.sessions[0]?.performed_on !== exercise.first_performed_on ||
      exercise.sessions.at(-1)?.performed_on !== exercise.last_performed_on
    ) {
      throw new Error('exercise dates drift');
    }
  }
  if (nutrition.summary.eligible_days !== inclusiveDays) throw new Error('nutrition period drift');
  if (
    nutrition.summary.logged_days + nutrition.summary.missing_days !==
    nutrition.summary.eligible_days
  ) {
    throw new Error('nutrition day totals drift');
  }
  if (
    nutrition.summary.coverage_percent !==
    Number(((nutrition.summary.logged_days * 100) / nutrition.summary.eligible_days).toFixed(1))
  ) {
    throw new Error('nutrition coverage drift');
  }
  if (nutrition.daily.length !== nutrition.summary.eligible_days) {
    throw new Error('nutrition daily detail drift');
  }
  if (
    nutrition.daily[0]?.diary_date !== report.period_start ||
    nutrition.daily.at(-1)?.diary_date !== report.period_end ||
    nutrition.daily.some((point) => point.is_current_day)
  ) {
    throw new Error('nutrition daily dates drift');
  }
  for (const trend of body.trends) {
    const expectedTrend = canonicalFacts.body.find((item) => item.metric === trend.metric);
    if (!expectedTrend || trend.unit !== expectedTrend.unit) throw new Error('body unit drift');
    if (trend.points.length !== trend.point_count) throw new Error('body point count drift');
    if (trend.points[0]?.measured_on !== trend.first_measured_on) {
      throw new Error('body first date drift');
    }
    if (trend.points.at(-1)?.measured_on !== trend.latest_measured_on) {
      throw new Error('body latest date drift');
    }
    if (trend.change !== null && trend.change !== trend.latest_value - trend.first_value) {
      throw new Error('body change drift');
    }
  }
  if (
    adherence.workouts.achieved !== training.completed_workouts ||
    adherence.workouts.evaluated !== training.planned_workouts ||
    adherence.calories.achieved !== nutrition.summary.days_within_calorie_tolerance ||
    adherence.protein.achieved !== nutrition.summary.days_meeting_protein_target
  ) {
    throw new Error('adherence components drift');
  }
  const availableAdherence = [adherence.workouts, adherence.calories, adherence.protein];
  const adherenceWeight = availableAdherence.reduce((total, item) => total + item.weight, 0);
  const expectedOverall = Number(
    (
      availableAdherence.reduce((total, item) => total + (item.percent ?? 0) * item.weight, 0) /
      adherenceWeight
    ).toFixed(1),
  );
  if (adherence.overall_percent !== expectedOverall) throw new Error('adherence overall drift');
  if (
    sufficiency.working_sets.counters.working_set_count !== training.completed_working_sets ||
    sufficiency.nutrition_coverage.counters.logged_day_count !== nutrition.summary.logged_days ||
    sufficiency.weight_trend.counters.point_count !==
      body.trends.find((trend) => trend.metric === 'weight_kg')?.point_count
  ) {
    throw new Error('data sufficiency drift');
  }
}
