import type { ProgressReport } from '../../src/shared/api/types';

type ReportState = 'empty' | 'full' | 'partial';
type SufficiencyReason =
  ProgressReport['data_sufficiency']['workout_logging']['reason_keys'][number];

function signal(
  status: 'sufficient' | 'limited' | 'insufficient',
  counters: Record<string, number>,
  reason: SufficiencyReason,
) {
  return { status, counters, reason_keys: [reason] };
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
            note: 'Неделя прошла ровно. В длинной пользовательской заметке проверяем перенос строк, отсутствие clipping и сохранение фактической формулировки без диагностических выводов.',
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
