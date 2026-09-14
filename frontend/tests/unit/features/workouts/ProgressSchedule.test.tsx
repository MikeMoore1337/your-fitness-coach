import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProgressSchedule } from '../../../../src/features/workouts/ProgressSchedule';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const progress = {
  user_id: 7,
  period_days: 30,
  period_start: '2029-12-12',
  period_end: '2030-01-10',
  training: {
    planned_workouts: 5,
    completed_workouts: 4,
    frequency_per_week: 1.2,
    volume_kg: 1200,
    new_personal_records: 1,
    last_completed_workout_on: '2030-01-09',
    next_workout: null,
  },
  cardio: {
    completed_sessions: 0,
    planned_sessions: 0,
    frequency_per_week: 0,
    duration_minutes: 0,
    distance_km: null,
    zone_duration: [],
  },
  nutrition: {
    visible: true,
    logged_days: 4,
    complete_days: 3,
    incomplete_days: 1,
    fasted_days: 0,
    unlogged_days: 25,
    adherence_evaluated_days: 4,
    average_calories: 2000,
    target_calories: 2100,
    average_protein_g: 140,
    target_protein_g: 150,
    target_effective_on: '2029-12-01',
  },
  body: {
    latest_measurement: null,
    trends: [],
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
    overall_percent: 80,
    included_components: ['workouts', 'calories', 'protein'],
    workouts: { status: 'available', percent: 80, achieved: 4, evaluated: 5, weight: 0.4 },
    cardio: { status: 'unsupported', percent: null, achieved: 0, evaluated: 0, weight: 0.2 },
    calories: { status: 'available', percent: 75, achieved: 3, evaluated: 4, weight: 0.2 },
    protein: { status: 'available', percent: 75, achieved: 3, evaluated: 4, weight: 0.2 },
  },
  data_sufficiency: {
    ruleset_version: 'data-sufficiency-v1',
    workout_logging: { status: 'sufficient', counters: {}, reason_keys: ['thresholds_met'] },
    working_sets: { status: 'limited', counters: {}, reason_keys: ['too_few_working_sets'] },
    rir_coverage: { status: 'insufficient', counters: {}, reason_keys: ['no_rir_observations'] },
    nutrition_coverage: {
      status: 'limited',
      counters: {},
      reason_keys: ['below_required_coverage'],
    },
    weight_trend: { status: 'insufficient', counters: {}, reason_keys: ['no_measurements'] },
    anthropometry: {
      status: 'insufficient',
      counters: {},
      reason_keys: ['no_anthropometry_measurements'],
    },
    schedule_adherence: { status: 'sufficient', counters: {}, reason_keys: ['thresholds_met'] },
  },
};

const trainingAnalytics = {
  period_days: 30,
  period_start: '2029-12-12',
  period_end: '2030-01-10',
  exercise_history_limit: 20,
  completed_set_count: 12,
  reps_total: 96,
  reps_recorded_sets: 12,
  external_load_volume_kg: 1200,
  volume_recorded_sets: 12,
  exercises: [],
  rir: { completed_set_count: 12, recorded_set_count: 0, missing_set_count: 12, distribution: [] },
  primary_muscle_exposure: [],
  secondary_muscle_exposure: [],
  completed_sets_without_muscle_metadata: 12,
  data_sufficiency: {
    ruleset_version: 'data-sufficiency-v1',
    workout_logging: { status: 'sufficient', counters: {}, reason_keys: ['thresholds_met'] },
    working_sets: { status: 'limited', counters: {}, reason_keys: ['too_few_working_sets'] },
    rir_coverage: { status: 'insufficient', counters: {}, reason_keys: ['no_rir_observations'] },
  },
};

const schedule = [
  {
    id: 42,
    scheduled_date: '2030-01-10',
    scheduled_time: '18:30:00',
    title: 'Тренировка A',
    status: 'planned',
    day_number: 1,
    week_number: 1,
  },
];

const suspiciousLowDays: Array<{
  diary_date: string;
  calories: number;
  target_calories: number;
}> = [];

const weeklyCheckIn = {
  week_start: '2030-01-07',
  week_end: '2030-01-13',
  submitted_on: '2030-01-10',
  timezone: 'Europe/Moscow',
  existing: null,
  summary: {
    ruleset_version: 'weekly-review-summary-v2',
    period_start: '2030-01-07',
    period_end: '2030-01-10',
    goal: 'maintenance',
    training: {
      planned_workouts: 2,
      completed_workouts: 1,
      adherence: { status: 'available', percent: 50, achieved: 1, evaluated: 2, weight: 0.4 },
    },
    nutrition: {
      logged_days: 3,
      complete_days: 2,
      incomplete_days: 1,
      fasted_days: 0,
      unlogged_days: 0,
      average_calories: 2000,
      target_calories: 2000,
      average_protein_g: 140,
      target_protein_g: 150,
      calories_adherence: {
        status: 'available',
        percent: 100,
        achieved: 3,
        evaluated: 3,
        weight: 0.2,
      },
      protein_adherence: {
        status: 'available',
        percent: 66.7,
        achieved: 2,
        evaluated: 3,
        weight: 0.2,
      },
      current_target: {
        effective_from: '2029-12-01',
        source: 'calculated',
        calories: 2000,
        protein_g: 150,
        fat_g: 70,
        carbs_g: 190,
      },
      suspicious_low_days: suspiciousLowDays,
    },
    weight_trend: null,
    anthropometry_trends: [],
    body_priority: null,
    progression: { training_volume_kg: 1200, new_personal_records: 1 },
    data_sufficiency: {
      ...progress.data_sufficiency,
      weight_trend: {
        status: 'insufficient',
        counters: { point_count: 0 },
        reason_keys: ['no_measurements'],
      },
    },
    adaptive_energy: null,
  },
};

const insufficientCalibration = {
  id: null,
  status: 'insufficient',
  ruleset_version: 'adaptive-energy-v1',
  period_start: '2029-12-13',
  period_end: '2030-01-09',
  sufficiency: {
    status: 'insufficient',
    counters: { logged_day_count: 3, eligible_day_count: 28, weight_point_count: 0 },
    reason_keys: ['too_few_logged_days'],
  },
  average_intake_kcal: null,
  smoothed_start_weight_kg: null,
  smoothed_end_weight_kg: null,
  estimated_expenditure_kcal: null,
  estimate_low_kcal: null,
  estimate_high_kcal: null,
  goal: 'maintenance',
  current_target_calories: 2000,
  current_target_protein_g: 150,
  current_target_fat_g: 70,
  current_target_carbs_g: 190,
  proposed_target_calories: null,
  proposed_target_protein_g: null,
  proposed_target_fat_g: null,
  proposed_target_carbs_g: null,
  proposed_effective_from: null,
  rationale: ['Пока недостаточно данных.'],
  created_at: null,
  decided_at: null,
};

const pendingCalibration = {
  ...insufficientCalibration,
  id: 17,
  status: 'pending',
  sufficiency: {
    status: 'sufficient',
    counters: { logged_day_count: 24, eligible_day_count: 28, weight_point_count: 6 },
    reason_keys: ['thresholds_met'],
  },
  average_intake_kcal: 2300,
  smoothed_start_weight_kg: 80,
  smoothed_end_weight_kg: 80,
  estimated_expenditure_kcal: 2300,
  estimate_low_kcal: 2050,
  estimate_high_kcal: 2550,
  current_target_calories: 1700,
  current_target_protein_g: 144,
  current_target_fat_g: 72,
  current_target_carbs_g: 119,
  proposed_target_calories: 1900,
  proposed_target_protein_g: 144,
  proposed_target_fat_g: 72,
  proposed_target_carbs_g: 169,
  proposed_effective_from: '2030-01-10',
  rationale: ['Дневник и тренд массы дают достаточно данных.'],
};

let calibrationResult: Record<string, unknown> = insufficientCalibration;

function renderPanel(userId: number | 'anonymous' = 'anonymous') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NavigationProvider>
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <ProgressSchedule userId={userId} />
        </FeedbackProvider>
      </QueryClientProvider>
    </NavigationProvider>,
  );
}

describe('ProgressSchedule', () => {
  beforeEach(() => {
    localStorage.clear();
    suspiciousLowDays.length = 0;
    calibrationResult = insufficientCalibration;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === '/api/v1/workouts/progress/summary?period_days=30') {
        return new Response(JSON.stringify(progress), { status: 200 });
      }
      if (path === '/api/v1/workouts/progress/training-analytics?period_days=30') {
        return new Response(JSON.stringify(trainingAnalytics), { status: 200 });
      }
      if (path === '/api/v1/check-ins/weekly/current') {
        return new Response(JSON.stringify(weeklyCheckIn), { status: 200 });
      }
      if (path === '/api/v1/check-ins/weekly?limit=4&offset=0') {
        return new Response(JSON.stringify({ items: [], total: 0, limit: 4, offset: 0 }), {
          status: 200,
        });
      }
      if (path === '/api/v1/nutrition/energy-calibration/preview' && init?.method === 'POST') {
        return new Response(JSON.stringify(calibrationResult), { status: 200 });
      }
      if (path === '/api/v1/nutrition/energy-calibration/17/decision' && init?.method === 'POST') {
        const decision = JSON.parse(String(init.body)).decision;
        return new Response(
          JSON.stringify({
            ...pendingCalibration,
            status: decision === 'accept' ? 'accepted' : 'rejected',
          }),
          { status: 200 },
        );
      }
      if (path === '/api/v1/check-ins/weekly' && init?.method === 'POST') {
        return new Response(JSON.stringify({ id: 1 }), { status: 201 });
      }
      if (path === '/api/v1/nutrition/diary/status' && init?.method === 'PUT') {
        return new Response(JSON.stringify({ status: 'incomplete' }), { status: 200 });
      }
      if (path === '/api/v1/workouts/schedule' && (!init?.method || init.method === 'GET')) {
        return new Response(JSON.stringify(schedule), { status: 200 });
      }
      if (path === '/api/v1/workouts/42/schedule' && init?.method === 'PATCH') {
        return new Response(JSON.stringify({ ...schedule[0], scheduled_date: '2030-01-12' }), {
          status: 200,
        });
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows progress and sends a reschedule request', async () => {
    renderPanel();

    expect(await screen.findByText('80%', { exact: true })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Прогресс' })).toBeInTheDocument();
    fireEvent.click(
      within(screen.getByRole('navigation', { name: 'Разделы прогресса' })).getByRole('link', {
        name: /^Тело/,
      }),
    );
    expect(await screen.findByText('Мало данных для динамики')).toBeVisible();
    expect(screen.getByText('Тренировка A')).toBeInTheDocument();
    expect(screen.getByText('Запланирована')).toBeInTheDocument();
    expect(screen.queryByText('planned')).not.toBeInTheDocument();

    const input = screen.getByLabelText('Новая дата для Тренировка A');
    fireEvent.change(input, { target: { value: '2030-01-12' } });
    fireEvent.change(screen.getByLabelText('Новое время для Тренировка A'), {
      target: { value: '19:15' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Перенести' }));

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/workouts/42/schedule',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ scheduled_date: '2030-01-12', scheduled_time: '19:15' }),
        }),
      ),
    );
  });

  it('submits optional weekly self-assessment', async () => {
    renderPanel();

    expect(await screen.findByText('Итоги недели')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Всё верно, продолжить' }));
    fireEvent.change(screen.getByRole('combobox', { name: /Как вы восстанавливались/ }), {
      target: { value: '4' },
    });
    fireEvent.change(screen.getByLabelText(/Заметка о неделе/), {
      target: { value: 'Больше сна' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Перейти к решению' }));
    expect(await screen.findByText('Данных пока недостаточно')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Завершить обзор' }));

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/check-ins/weekly',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            status: 'completed',
            training_load: null,
            recovery: 4,
            hunger: null,
            adherence_difficulty: null,
            note: 'Больше сна',
            energy_calibration_id: null,
          }),
        }),
      ),
    );
  });

  it('skips the entire review without requesting or changing an energy target', async () => {
    renderPanel();

    await screen.findByText('Итоги недели');
    fireEvent.click(screen.getByRole('button', { name: 'Пропустить обзор' }));
    const dialog = screen.getByRole('dialog', { name: 'Пропустить недельный обзор?' });
    expect(dialog).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Пропустить' }));

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/check-ins/weekly',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ status: 'skipped' }),
        }),
      ),
    );
    expect(globalThis.fetch).not.toHaveBeenCalledWith(
      '/api/v1/nutrition/energy-calibration/preview',
      expect.anything(),
    );
  });

  it.each([
    ['Принять новую цель', 'accept'],
    ['Оставить текущую цель', 'reject'],
    ['Отложить решение', null],
  ])(
    'keeps %s distinct and records the proposal with the review',
    async (label, expectedDecision) => {
      calibrationResult = pendingCalibration;
      renderPanel();

      await screen.findByText('Итоги недели');
      fireEvent.click(screen.getByRole('button', { name: 'Всё верно, продолжить' }));
      fireEvent.click(screen.getByRole('button', { name: 'Пропустить вопросы' }));
      expect(await screen.findByText('1900 ккал')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: label }));

      if (expectedDecision) {
        await waitFor(() =>
          expect(globalThis.fetch).toHaveBeenCalledWith(
            '/api/v1/nutrition/energy-calibration/17/decision',
            expect.objectContaining({
              method: 'POST',
              body: JSON.stringify({ decision: expectedDecision }),
            }),
          ),
        );
      }
      await waitFor(() =>
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/check-ins/weekly',
          expect.objectContaining({
            method: 'POST',
            body: expect.stringContaining('"energy_calibration_id":17'),
          }),
        ),
      );
    },
  );

  it('marks only an explicitly selected suspicious low day as incomplete', async () => {
    suspiciousLowDays.push({
      diary_date: '2030-01-08',
      calories: 600,
      target_calories: 2000,
    });
    renderPanel();

    const lowDay = await screen.findByRole('checkbox', { name: /8 января 2030/ });
    expect(globalThis.fetch).not.toHaveBeenCalledWith(
      '/api/v1/nutrition/diary/status',
      expect.anything(),
    );
    fireEvent.click(lowDay);
    fireEvent.click(screen.getByRole('button', { name: 'Отметить выбранные как неполные' }));

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/nutrition/diary/status',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ diary_date: '2030-01-08', status: 'incomplete' }),
        }),
      ),
    );
  });

  it('restores an unfinished question draft only for the same user', async () => {
    const view = renderPanel(7);
    await screen.findByText('Итоги недели');
    fireEvent.click(screen.getByRole('button', { name: 'Всё верно, продолжить' }));
    fireEvent.change(screen.getByLabelText(/Заметка о неделе/), {
      target: { value: 'Черновик после background' },
    });
    view.unmount();

    const restored = renderPanel(7);
    expect(await screen.findByDisplayValue('Черновик после background')).toBeInTheDocument();
    restored.unmount();

    renderPanel(8);
    await screen.findByText('Итоги недели');
    fireEvent.click(screen.getByRole('button', { name: 'Всё верно, продолжить' }));
    expect(screen.getByLabelText(/Заметка о неделе/)).toHaveValue('');
  });
});
