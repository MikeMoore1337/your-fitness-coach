import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkoutHistory } from '../../../../src/features/workouts/WorkoutHistory';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const week = [
  {
    id: 42,
    scheduled_date: '2030-01-10',
    title: 'Тренировка A',
    status: 'planned',
    day_number: 1,
    week_number: 1,
  },
  {
    id: 43,
    scheduled_date: '2030-01-09',
    title: 'Тренировка B',
    status: 'completed',
    day_number: 2,
    week_number: 1,
  },
  {
    id: 44,
    scheduled_date: '2020-01-08',
    title: 'Прошедшая пропущенная тренировка',
    status: 'skipped',
    day_number: 3,
    week_number: 1,
  },
];

const history = [
  {
    id: 43,
    scheduled_date: '2030-01-09',
    title: 'Тренировка B',
    status: 'completed',
    started_at: '2030-01-09T09:00:00',
    completed_at: '2030-01-09T10:00:00',
    completed_sets: 4,
    volume_kg: 1200,
    exercises: [
      {
        workout_exercise_id: 55,
        exercise_id: 7,
        title: 'Жим гантелей лежа',
        equipment_ids: ['dumbbell'],
        prescribed_sets: 4,
        prescribed_reps: '8-10',
        rest_seconds: 90,
        sort_order: 1,
        priority: 'core',
      },
    ],
    adaptations: [
      {
        id: 5,
        reason: 'replace_exercise',
        ruleset_version: 'workout-adaptation-v1',
        applied_at: '2030-01-09T08:55:00',
        changes: [
          {
            kind: 'replaced',
            workout_exercise_id: 55,
            from_exercise_id: 6,
            from_title: 'Жим штанги лежа',
            to_exercise_id: 7,
            to_title: 'Жим гантелей лежа',
          },
        ],
      },
    ],
  },
];

function renderHistory(
  onWorkoutSelect = vi.fn(),
  focus: Pick<
    React.ComponentProps<typeof WorkoutHistory>,
    'focusedWorkoutId' | 'focusedCommentId' | 'focusedExerciseId'
  > = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <WorkoutHistory onWorkoutSelect={onWorkoutSelect} {...focus} />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
  return onWorkoutSelect;
}

function DelayedFocusHistoryHarness() {
  const [focusedWorkoutId, setFocusedWorkoutId] = useState<number | null>(null);

  return (
    <>
      <button type="button" onClick={() => setFocusedWorkoutId(43)}>
        Открыть deep-link истории
      </button>
      <WorkoutHistory
        focusedCommentId={1}
        focusedExerciseId={55}
        focusedWorkoutId={focusedWorkoutId}
      />
    </>
  );
}

describe('WorkoutHistory', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2030-01-08T12:00:00Z'));
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path === '/api/v1/workouts/week') {
        return new Response(JSON.stringify(week), { status: 200 });
      }
      if (path.startsWith('/api/v1/workouts/history?')) {
        return new Response(JSON.stringify(history), { status: 200 });
      }
      if (path === '/api/v1/workouts/history/summary') {
        return new Response(
          JSON.stringify({ workouts_completed: 1, completed_sets: 4, volume_kg: 1200 }),
          { status: 200 },
        );
      }
      if (path === '/api/v1/programs/exercises/7') {
        return new Response(
          JSON.stringify({
            id: 7,
            title: 'Жим гантелей лежа',
            primary_muscle: 'Грудь',
            equipment: 'Гантели',
            primary_muscle_ids: [],
            secondary_muscle_ids: [],
            equipment_ids: [],
            alternatives: [],
            difficulty_level: 'beginner',
            is_custom: true,
            is_personalized: true,
            has_guide: false,
            guide: null,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('показывает русские статусы и выбирает корректную цель для дня', async () => {
    const onWorkoutSelect = renderHistory();

    expect(await screen.findByText('Запланирована')).toBeInTheDocument();
    expect(screen.getByText('Завершена')).toBeInTheDocument();
    expect(screen.queryByText('planned')).not.toBeInTheDocument();
    expect(screen.queryByText('completed')).not.toBeInTheDocument();
    const exerciseDetails = screen.getByRole('button', { name: 'Жим гантелей лежа' });
    expect(exerciseDetails).toBeInTheDocument();
    expect(screen.getByText('Изменено перед тренировкой: замена упражнения')).toBeInTheDocument();
    expect(screen.getByText('Прошедшая пропущенная тренировка').closest('a')).toBeNull();

    const plannedDay = screen.getByRole('link', {
      name: 'Открыть тренировочный день: Тренировка A',
    });
    expect(plannedDay).toHaveAttribute('href', '#workout-schedule-42');
    fireEvent.click(plannedDay);
    expect(onWorkoutSelect).toHaveBeenLastCalledWith(42, 'schedule');
    fireEvent.click(plannedDay);
    expect(onWorkoutSelect).toHaveBeenCalledTimes(2);

    const completedDay = screen.getByRole('link', {
      name: 'Открыть тренировочный день: Тренировка B',
    });
    expect(completedDay).toHaveAttribute('href', '#workout-history-43');
    fireEvent.click(completedDay);
    expect(onWorkoutSelect).toHaveBeenLastCalledWith(43, 'history');

    fireEvent.click(exerciseDetails);
    expect(await screen.findByRole('heading', { name: 'Техника пока не добавлена' })).toBeVisible();
  });

  it('открывает историю для deep-link тренировки до прокрутки к строке', async () => {
    renderHistory(vi.fn(), { focusedWorkoutId: 43, focusedCommentId: 1, focusedExerciseId: 55 });

    const historyHeading = await screen.findByRole('heading', { name: 'История' });
    await waitFor(() => expect(historyHeading.closest('details')).toHaveAttribute('open', ''));
  });

  it('открывает историю, если deep-link приходит после первого mount', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <DelayedFocusHistoryHarness />
        </FeedbackProvider>
      </QueryClientProvider>,
    );

    await screen.findByRole('heading', { name: 'История' });
    expect(document.querySelector('.workout-history-card')).not.toHaveAttribute('open', '');
    fireEvent.click(screen.getByRole('button', { name: 'Открыть deep-link истории' }));

    expect(document.querySelector('.workout-history-card')).toHaveAttribute('open', '');
  });
});
