import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProgressExperience } from '../../../../src/features/workouts/ProgressExperience';
import type {
  NutritionReport,
  ProgressSummary,
  TrainingAnalytics,
} from '../../../../src/shared/api/types';
import { NavigationProvider } from '../../../../src/shared/navigation/router';

const signal = (
  status: 'sufficient' | 'limited' | 'insufficient',
): ProgressSummary['data_sufficiency']['weight_trend'] => ({
  status,
  counters: {},
  reason_keys: status === 'sufficient' ? ['thresholds_met'] : ['too_few_points'],
});

function makeSummary(): ProgressSummary {
  return {
    user_id: 7,
    period_days: 30,
    period_start: '2030-01-01',
    period_end: '2030-01-30',
    training: {
      planned_workouts: 8,
      completed_workouts: 7,
      skipped_workouts: 1,
      frequency_per_week: 1.63,
      volume_kg: 12400,
      new_personal_records: 3,
      last_completed_workout_on: '2030-01-28',
      next_workout: null,
    },
    cardio: {
      completed_sessions: 2,
      planned_sessions: 1,
      frequency_per_week: 0.47,
      duration_minutes: 80,
      distance_km: 7.5,
      zone_duration: [{ zone: 2, duration_minutes: 45 }],
    },
    nutrition: {
      visible: true,
      logged_days: 20,
      complete_days: 18,
      incomplete_days: 2,
      fasted_days: 0,
      unlogged_days: 9,
      adherence_evaluated_days: 18,
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
          label: 'Вес',
          unit: 'kg',
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
          label: 'Талия',
          unit: 'cm',
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
        {
          metric: 'custom:17',
          label: 'Живот',
          unit: 'cm',
          definition_id: 17,
          first_value: 86,
          latest_value: 84,
          change: -2,
          first_measured_on: '2030-01-02',
          latest_measured_on: '2030-01-29',
          point_count: 3,
          span_days: 27,
          interpretation_status: 'available',
          points: [
            { measured_on: '2030-01-02', value: 86 },
            { measured_on: '2030-01-15', value: 85 },
            { measured_on: '2030-01-29', value: 84 },
          ],
        },
      ],
      priority: null,
      guidance: {
        comparison_basis: 'self',
        minimum_points_for_interpretation: 3,
        minimum_span_days_for_interpretation: 14,
        consistency_tips: [],
        circumference_limitations: [],
      },
    },
    adherence: {
      formula_version: 'adherence-v1',
      overall_percent: 84,
      included_components: ['workouts', 'calories', 'protein'],
      workouts: { status: 'available', percent: 87.5, achieved: 7, evaluated: 8, weight: 0.4 },
      cardio: { status: 'unsupported', percent: null, achieved: 0, evaluated: 0, weight: 0.2 },
      calories: { status: 'available', percent: 83.3, achieved: 15, evaluated: 18, weight: 0.2 },
      protein: { status: 'available', percent: 72.2, achieved: 13, evaluated: 18, weight: 0.2 },
    },
    data_sufficiency: {
      ruleset_version: 'data-sufficiency-v1',
      workout_logging: signal('sufficient'),
      working_sets: signal('sufficient'),
      rir_coverage: signal('limited'),
      nutrition_coverage: signal('sufficient'),
      weight_trend: signal('sufficient'),
      anthropometry: signal('limited'),
      schedule_adherence: signal('sufficient'),
    },
  };
}

function makeAnalytics(): TrainingAnalytics {
  return {
    period_days: 30,
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
        history_truncated: true,
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
      workout_logging: signal('sufficient'),
      working_sets: signal('sufficient'),
      rir_coverage: signal('limited'),
    },
  };
}

function makeNutritionReport(): NutritionReport {
  const emptyMetric = { average: null, minimum: null, maximum: null, sample_days: 0 };
  const emptyComparison = {
    average_actual: null,
    average_target: null,
    average_deviation: null,
    evaluated_days: 0,
  };
  return {
    period: 'days_30',
    period_start: '2030-01-01',
    period_end: '2030-01-30',
    timezone: 'Europe/Moscow',
    summary: {
      logged_days: 0,
      eligible_days: 30,
      coverage_percent: 0,
      complete_days: 0,
      incomplete_days: 0,
      fasted_days: 0,
      missing_days: 30,
      current_day_status: 'missing',
      calories: emptyMetric,
      protein_g: emptyMetric,
      fat_g: emptyMetric,
      carbs_g: emptyMetric,
      calorie_comparison: emptyComparison,
      protein_comparison: emptyComparison,
      fat_comparison: emptyComparison,
      carbs_comparison: emptyComparison,
      days_within_calorie_tolerance: 0,
      calorie_tolerance_evaluated_days: 0,
      days_meeting_protein_target: 0,
      protein_target_evaluated_days: 0,
    },
    daily: [],
    target_changes: [],
  };
}

function installApi({
  analytics = makeAnalytics(),
  failSummary = false,
  pending = false,
  summary = makeSummary(),
}: {
  analytics?: ReturnType<typeof makeAnalytics>;
  failSummary?: boolean;
  pending?: boolean;
  summary?: ReturnType<typeof makeSummary>;
} = {}) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (pending) return new Promise<Response>(() => undefined);
    const path = String(input);
    const period = Number(new URL(path, 'http://test.local').searchParams.get('period_days')) || 30;
    if (path.startsWith('/api/v1/workouts/progress/summary')) {
      if (failSummary) {
        return new Response(JSON.stringify({ detail: 'Сводка временно недоступна' }), {
          status: 503,
        });
      }
      return new Response(JSON.stringify({ ...summary, period_days: period }), { status: 200 });
    }
    if (path.startsWith('/api/v1/workouts/progress/training-analytics')) {
      return new Response(JSON.stringify({ ...analytics, period_days: period }), { status: 200 });
    }
    if (path.startsWith('/api/v1/workouts/progress/nutrition-report')) {
      return new Response(JSON.stringify(makeNutritionReport()), { status: 200 });
    }
    if (path.startsWith('/api/v1/me/profile/body-priority-options')) {
      return new Response(
        JSON.stringify({
          items: [
            { id: 'back', name: 'Мышцы спины' },
            { id: 'posterior_chain', name: 'Задняя поверхность тела' },
          ],
        }),
        { status: 200 },
      );
    }
    return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
  });
}

function renderExperience(search = '') {
  window.history.replaceState({}, '', `/app${search}`);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NavigationProvider>
      <QueryClientProvider client={queryClient}>
        <ProgressExperience />
      </QueryClientProvider>
    </NavigationProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('ProgressExperience', () => {
  it('shows backend summaries, factual body points and workout detail', async () => {
    installApi();
    renderExperience();

    expect(await screen.findByRole('heading', { name: 'Что изменилось' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Прогресс' })).toBeVisible();
    expect(screen.getAllByRole('link', { name: /Тренировки/ })).toHaveLength(2);
    expect(screen.queryByRole('heading', { name: 'Замеры и приоритеты' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Питание' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Соблюдение плана' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Скачать отчёт' })).toHaveAttribute(
      'href',
      '/app/report?period=days_30',
    );
    expect(screen.getByRole('img', { name: /Вес: 2 янв. — 69,4 кг/ })).toBeVisible();

    fireEvent.click(
      within(screen.getByRole('navigation', { name: 'Разделы прогресса' })).getByRole('link', {
        name: /^Тренировки/,
      }),
    );
    expect(await screen.findByRole('heading', { name: 'Тренировки', level: 2 })).toBeVisible();
    fireEvent.click(await screen.findByText('Жим штанги лёжа'));
    expect(screen.getByText('Детали тренировки')).toBeVisible();
    expect(screen.getByText('Показаны последние 20 тренировок упражнения.')).toBeVisible();
    expect(screen.queryByText('too_few_points')).not.toBeInTheDocument();
  });

  it('shows selected priorities as preferences without treating circumference as muscle analytics', async () => {
    const summary = makeSummary();
    summary.body.priority = {
      mode: 'muscle_groups',
      muscle_group_ids: ['back', 'posterior_chain'],
    };
    summary.body.guidance.consistency_tips = ['Снимайте замеры в похожее время суток.'];
    summary.body.guidance.circumference_limitations = [
      'Окружность плеча не измеряет отдельно бицепс или трицепс.',
    ];
    installApi({ summary });
    renderExperience('?section=progress&progress_view=body');

    await screen.findByRole('heading', { name: 'Замеры и приоритеты' });
    fireEvent.click(screen.getByText('Выбранные мышечные группы'));
    expect(await screen.findByText('Мышцы спины')).toBeVisible();
    expect(screen.getByText('Задняя поверхность тела')).toBeVisible();
    expect(
      screen.getByText(/Это предпочтение для планирования\. Оно не оценивает тело/),
    ).toBeVisible();
    expect(screen.getAllByText('Талия').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Живот').length).toBeGreaterThan(0);
    expect(screen.getAllByText('84 см').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText('Как сравнивать замеры'));
    expect(screen.getByText('Снимайте замеры в похожее время суток.')).toBeVisible();
    expect(
      screen.getByText('Окружность плеча не измеряет отдельно бицепс или трицепс.'),
    ).toBeVisible();
  });

  it('requests both backend aggregates when the period changes', async () => {
    installApi();
    renderExperience('?section=progress&progress_view=training');
    await screen.findByRole('heading', { name: 'Тренировки', level: 2 });

    fireEvent.click(
      within(screen.getByRole('tablist', { name: 'Период прогресса' })).getByRole('tab', {
        name: '7 дней',
      }),
    );

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/workouts/progress/summary?period_days=7',
        expect.anything(),
      );
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/workouts/progress/training-analytics?period_days=7',
        expect.anything(),
      );
    });
    expect(screen.getByRole('link', { name: 'Скачать отчёт' })).toHaveAttribute(
      'href',
      '/app/report?period=days_7',
    );
  });

  it('does not auto-select a custom metric when no canonical trend exists', async () => {
    const summary = makeSummary();
    const customTrend = summary.body.trends.find((trend) => trend.metric === 'custom:17');
    if (!customTrend) throw new Error('Expected the custom trend fixture');
    summary.body.trends = [customTrend];
    installApi({ summary });
    renderExperience('?section=progress&progress_view=body');

    await screen.findByRole('heading', { name: 'Замеры и приоритеты' });
    expect(screen.getByRole('tab', { name: 'Живот' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.queryByRole('img', { name: /Живот/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Живот' }));
    expect(await screen.findByRole('img', { name: /Живот/ })).toBeVisible();
  });

  it('keeps empty, one-point and partial adherence states factual', async () => {
    const summary = makeSummary();
    summary.training.planned_workouts = 0;
    summary.training.completed_workouts = 0;
    summary.training.new_personal_records = 0;
    summary.nutrition.logged_days = 0;
    summary.nutrition.complete_days = 0;
    summary.nutrition.incomplete_days = 0;
    summary.nutrition.fasted_days = 0;
    summary.nutrition.unlogged_days = 29;
    summary.nutrition.adherence_evaluated_days = 0;
    const weightTrend = summary.body.trends[0];
    if (!weightTrend) throw new Error('Weight trend fixture is missing');
    summary.body.trends = [
      {
        ...weightTrend,
        first_value: 68.4,
        latest_value: 68.4,
        change: null,
        first_measured_on: '2030-01-29',
        latest_measured_on: '2030-01-29',
        point_count: 1,
        span_days: 0,
        interpretation_status: 'single_point',
        points: [{ measured_on: '2030-01-29', value: 68.4 }],
      },
    ];
    summary.data_sufficiency.weight_trend = {
      status: 'limited',
      counters: {
        point_count: 1,
        span_days: 0,
        required_point_count: 3,
        required_span_days: 14,
      },
      reason_keys: ['too_few_points'],
    };
    summary.adherence.overall_percent = null;
    summary.adherence.included_components = [];
    summary.adherence.workouts = {
      status: 'not_applicable',
      percent: null,
      achieved: 0,
      evaluated: 0,
      weight: 0.4,
    };
    summary.adherence.calories = {
      status: 'insufficient_data',
      percent: null,
      achieved: 0,
      evaluated: 0,
      weight: 0.2,
    };
    const analytics = makeAnalytics();
    analytics.exercises = [];
    analytics.completed_set_count = 0;
    analytics.external_load_volume_kg = null;
    installApi({ summary, analytics });
    renderExperience();

    expect((await screen.findAllByText('Мало данных')).length).toBeGreaterThan(0);
    expect(screen.queryByText('История упражнений пока пуста')).not.toBeInTheDocument();
    expect(screen.queryByText('Нет подтверждённых дней питания')).not.toBeInTheDocument();

    fireEvent.click(
      within(screen.getByRole('navigation', { name: 'Разделы прогресса' })).getByRole('link', {
        name: /^Тело/,
      }),
    );
    expect(
      await screen.findByText(
        'Одна точка сохраняет факт, но ещё не показывает направление изменений.',
      ),
    ).toBeVisible();
    expect(screen.getByText(/1 замер/)).toBeVisible();

    fireEvent.click(
      within(screen.getByRole('navigation', { name: 'Разделы прогресса' })).getByRole('link', {
        name: /^Питание/,
      }),
    );
    expect(await screen.findByText('Нет подтверждённых дней питания')).toBeVisible();
    expect(
      screen.getByText('0 частичных и 29 отсутствующих дней не входят в средние значения.'),
    ).toBeVisible();
  });

  it('shows a loading state without inventing zero values', () => {
    installApi({ pending: true });
    renderExperience();

    expect(screen.getByText('Собираем динамику за период…')).toBeVisible();
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });

  it('keeps training analytics available when the main summary fails', async () => {
    installApi({ failSummary: true });
    renderExperience('?section=progress&progress_view=training');

    expect(await screen.findByRole('alert')).toHaveTextContent('Сводка временно недоступна');
    expect(await screen.findByText('Жим штанги лёжа')).toBeVisible();
    expect(screen.getByText('28')).toBeVisible();
  });
});
