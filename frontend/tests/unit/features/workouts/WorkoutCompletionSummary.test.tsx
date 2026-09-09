import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Workout } from '../../../../src/shared/api/types';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import {
  formatCompletionDuration,
  WorkoutCompletionSummary,
} from '../../../../src/features/workouts/WorkoutCompletionSummary';
import {
  PRODUCT_EVENT_NAME,
  type ProductEventEnvelope,
} from '../../../../src/shared/analytics/productEvents';

const apiMock = vi.fn();

vi.mock('../../../../src/shared/api/client', async () => {
  const actual = await vi.importActual('../../../../src/shared/api/client');
  return { ...actual, api: (...args: unknown[]) => apiMock(...args) };
});

const workout: Workout = {
  id: 42,
  scheduled_date: '2030-01-10',
  scheduled_time: '18:30:00',
  title: 'Силовая база',
  status: 'completed',
  day_number: 1,
  week_number: 1,
  started_at: '2030-01-10T10:00:00',
  completed_at: '2030-01-10T11:15:00',
  exercises: [
    {
      id: 101,
      exercise_id: 11,
      exercise_title: 'Приседания',
      metric_type: 'strength',
      sort_order: 1,
      prescribed_sets: 2,
      prescribed_reps: '8-10',
      rest_seconds: 90,
      notes: null,
      superset_group: null,
      superset_order: null,
      has_guide: false,
      sets: [
        {
          id: 201,
          set_number: 1,
          actual_reps: 8,
          actual_weight: 50,
          rir: null,
          set_kind: 'working',
          reached_failure: false,
          is_completed: true,
          version: 2,
        },
        {
          id: 202,
          set_number: 2,
          actual_reps: null,
          actual_weight: null,
          rir: null,
          set_kind: 'working',
          reached_failure: false,
          is_completed: false,
          version: 1,
        },
      ],
    },
  ],
  completion_summary: {
    duration_seconds: 4500,
    performed_exercises: 1,
    completed_sets: 1,
    total_sets: 2,
    reps_total: 8,
    reps_recorded_sets: 1,
    load_recorded_sets: 1,
    exercises: [
      {
        workout_exercise_id: 101,
        exercise_id: 11,
        exercise_title: 'Приседания',
        metric_type: 'strength',
        completed_sets: 1,
        reps_total: 8,
        reps_recorded_sets: 1,
        max_load_kg: 50,
        load_recorded_sets: 1,
      },
    ],
    personal_records: [
      {
        exercise_id: 11,
        exercise_title: 'Приседания',
        kinds: ['max_load', 'best_set_volume'],
        max_load_kg: 50,
        best_set_volume_kg: 400,
      },
    ],
    next_workout: {
      id: 43,
      scheduled_date: '2030-01-13',
      scheduled_time: '19:00:00',
      title: 'Верх тела',
    },
    feedback: null,
    note: null,
  },
};

function renderSummary(onReturnToday = vi.fn(), targetWorkout: Workout = workout) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <NavigationProvider>
          <WorkoutCompletionSummary workout={targetWorkout} onReturnToday={onReturnToday} />
        </NavigationProvider>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
  return { onReturnToday, queryClient };
}

describe('WorkoutCompletionSummary', () => {
  afterEach(cleanup);

  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/comments')) return Promise.resolve([]);
      throw new Error(`Unexpected API path: ${path}`);
    });
    window.history.replaceState({}, '', '/app');
  });

  it('shows factual confirmation, next step, recorded load and canonical records', async () => {
    const analyticsEvents: ProductEventEnvelope[] = [];
    const listener = (event: Event) =>
      analyticsEvents.push((event as CustomEvent<ProductEventEnvelope>).detail);
    window.addEventListener(PRODUCT_EVENT_NAME, listener);
    const { onReturnToday } = renderSummary();

    expect(screen.getByRole('heading', { name: 'Тренировка завершена' })).toBeInTheDocument();
    const completion = screen
      .getByRole('heading', { name: 'Тренировка завершена' })
      .closest('.workout-completion');
    expect(completion).toHaveAttribute('data-motion-phase', expect.stringMatching(/pending|enter/));
    expect(
      completion?.querySelector('.ui-semantic-artwork--workout-completion'),
    ).not.toBeInTheDocument();
    expect(screen.getByText('1 ч 15 мин')).toBeInTheDocument();
    expect(screen.getByText(/1 подход/)).toBeInTheDocument();
    expect(screen.getByText(/Следующая тренировка .* Верх тела/)).toBeInTheDocument();
    expect(screen.getByText(/максимальный вес 50 кг/)).toBeInTheDocument();
    expect(
      screen.queryByText(/performance score|readiness|перетренирован/i),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(analyticsEvents).toContainEqual(
        expect.objectContaining({
          name: 'workout_completion_summary_viewed',
          surface: 'desktop_web',
        }),
      ),
    );
    expect(JSON.stringify(analyticsEvents)).not.toContain('Приседания');
    expect(JSON.stringify(analyticsEvents)).not.toContain('actual_weight');

    await userEvent.click(screen.getByRole('button', { name: 'Вернуться в Сегодня' }));
    expect(onReturnToday).toHaveBeenCalledOnce();
    expect(screen.getByRole('link', { name: 'Посмотреть Прогресс' })).toHaveAttribute(
      'href',
      '/app?section=progress',
    );
    window.removeEventListener(PRODUCT_EVENT_NAME, listener);
  });

  it('keeps the optional note after a recoverable save error and retries idempotent PUT', async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/comments')) return Promise.resolve([]);
      if (path.endsWith('/completion-feedback')) return Promise.reject(new Error('Нет сети'));
      throw new Error(`Unexpected API path: ${path}`);
    });
    renderSummary();

    await user.click(screen.getByRole('button', { name: 'Нормально' }));
    const note = screen.getByRole('textbox', { name: 'Заметка' });
    await user.type(note, 'Рабочий темп');
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Нет сети');
    expect(note).toHaveValue('Рабочий темп');
    expect(apiMock).toHaveBeenCalledWith('/api/v1/workouts/42/completion-feedback', {
      method: 'PUT',
      body: { feedback: 'as_expected', note: 'Рабочий темп' },
    });

    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/comments')) return Promise.resolve([]);
      if (path.endsWith('/completion-feedback'))
        return Promise.resolve({
          ...workout,
          completion_summary: {
            ...workout.completion_summary!,
            feedback: 'as_expected',
            note: 'Рабочий темп',
          },
        });
      throw new Error(`Unexpected API path: ${path}`);
    });
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByText('Обратная связь сохранена')).toBeInTheDocument();
  });

  it('formats a long workout without rolling hours over', () => {
    expect(formatCompletionDuration(26 * 60 * 60 + 35 * 60)).toBe('26 ч 35 мин');
    expect(formatCompletionDuration(null)).toBe('Не зафиксировано');
  });

  it('показывает cardio-результат без терминов силового подхода', async () => {
    const cardioWorkout: Workout = {
      ...workout,
      title: 'Смешанная тренировка',
      exercises: [
        ...workout.exercises,
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
          has_guide: false,
          sets: [
            {
              id: 203,
              set_number: 1,
              duration_minutes: 27,
              distance_km: 6.4,
              average_heart_rate_bpm: 138,
              heart_rate_zone: 3,
              is_completed: true,
              version: 2,
            },
          ],
        },
      ],
      completion_summary: {
        ...workout.completion_summary!,
        performed_exercises: 2,
        completed_sets: 2,
        total_sets: 3,
        exercises: [
          ...workout.completion_summary!.exercises,
          {
            workout_exercise_id: 102,
            exercise_id: 12,
            exercise_title: 'Велотренажёр',
            metric_type: 'cardio',
            completed_sets: 1,
            reps_total: null,
            reps_recorded_sets: 0,
            max_load_kg: null,
            load_recorded_sets: 0,
            duration_minutes: 27,
            distance_km: 6.4,
            average_heart_rate_bpm: 138,
            heart_rate_zone: 3,
          },
        ],
      },
    };
    renderSummary(vi.fn(), cardioWorkout);

    expect(screen.getByText('Этапов')).toBeInTheDocument();
    await userEvent.click(screen.getByText('Записанные результаты'));
    const cardioResult = screen.getByText('Велотренажёр').closest('li');
    expect(cardioResult).toHaveTextContent('27 мин · 6.4 км · средний пульс 138 · зона 3');
    expect(cardioResult).not.toHaveTextContent(/подход|повтор|вес/i);
  });
});
