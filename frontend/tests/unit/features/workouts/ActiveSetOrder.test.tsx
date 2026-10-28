import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Workout } from '../../../../src/shared/api/types';
import { TodayWorkout } from '../../../../src/features/workouts/TodayWorkout';

const mocks = vi.hoisted(() => ({ enqueue: vi.fn().mockResolvedValue(true) }));

vi.mock('../../../../src/app/AuthProvider', () => ({ useAuth: () => ({ user: null }) }));
vi.mock('../../../../src/shared/ui/FeedbackProvider', () => ({
  useFeedback: () => ({ toast: vi.fn(), confirm: vi.fn().mockResolvedValue(true) }),
}));
vi.mock('../../../../src/features/workouts/useScreenWakeLock', () => ({
  useScreenWakeLock: vi.fn(),
}));
vi.mock('../../../../src/features/workouts/useActiveWorkoutQueue', () => ({
  useActiveWorkoutQueue: () => ({
    pendingBySet: new Map(),
    pendingCount: 0,
    durable: true,
    syncState: 'synced',
    enqueue: mocks.enqueue,
    clear: vi.fn(),
    flushNow: vi.fn().mockResolvedValue(true),
    retry: vi.fn(),
  }),
}));
vi.mock('../../../../src/features/ai/AiCoachContextualEntry', () => ({
  AiCoachContextualEntry: () => null,
}));
vi.mock('../../../../src/features/workouts/WorkoutAdaptation', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  WorkoutAdaptation: () => null,
}));
vi.mock('../../../../src/features/workouts/ExerciseSetupMemory', () => ({
  ExerciseSetupMemory: () => null,
}));

function renderWorkout(withPrevious: boolean) {
  const previous = {
    id: 201,
    set_number: 1,
    actual_reps: 8,
    actual_weight: 40,
    is_completed: true,
    version: 1,
  };
  const current = {
    id: 202,
    set_number: 2,
    actual_reps: null,
    actual_weight: null,
    rir: null,
    is_completed: false,
    version: 1,
  };
  const workout: Workout = {
    id: 42,
    scheduled_date: '2030-01-10',
    title: 'Тренировка A',
    status: 'in_progress',
    day_number: 1,
    week_number: 1,
    exercises: [
      {
        id: 101,
        exercise_id: 11,
        exercise_title: 'Жим штанги лёжа',
        metric_type: 'strength',
        sort_order: 1,
        prescribed_sets: 2,
        prescribed_reps: '8-10',
        rest_seconds: 90,
        has_guide: false,
        progression_guidance: null,
        sets: withPrevious ? [previous, current] : [current],
      },
    ],
  };
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(['workout', 'today'], workout);
  client.setQueryData(['workout', 'exercise-history', 11], { recent_sessions: [] });
  const { container } = render(
    <QueryClientProvider client={client}>
      <TodayWorkout />
    </QueryClientProvider>,
  );
  const row = container.querySelector<HTMLElement>('[data-workout-set-id="202"]');
  if (!row) throw new Error('Current set is missing');
  return { row, controls: within(row) };
}

function expectDomOrder(elements: HTMLElement[]) {
  for (let index = 0; index < elements.length - 1; index += 1) {
    expect(elements[index]!.compareDocumentPosition(elements[index + 1]!)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  }
}

beforeEach(() => {
  mocks.enqueue.mockClear();
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  );
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('active set action order', () => {
  it('places both prefill actions between completion and the helpers and preserves RIR', async () => {
    const user = userEvent.setup();
    const { row, controls } = renderWorkout(true);
    const weight = controls.getByLabelText('Вес, Жим штанги лёжа, подход 2');
    const reps = controls.getByLabelText('Повторы, Жим штанги лёжа, подход 2');
    const rir = controls.getByRole('button', { name: '2 — ещё примерно 2 повтора' });
    const done = controls.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' });
    const prefill = controls.getByRole('button', { name: 'Подставить предыдущий результат' });
    const quick = controls.getByRole('button', { name: 'Подставить и завершить' });
    expectDomOrder([
      controls.getByText('Предыдущий подход: 40 кг × 8'),
      controls.getByText('Отдых 90 с'),
      weight,
      reps,
      rir,
      done,
      prefill,
      quick,
      controls.getByText('Что такое RIR?', { exact: true }),
      controls.getByText('Разминка и блины', { exact: true }),
      controls.getByText('Дополнительно', { exact: true }),
    ]);

    await user.click(rir);
    await user.click(prefill);
    expect(weight).toHaveValue('40');
    expect(reps).toHaveValue(8);
    expect(rir).toHaveAttribute('aria-pressed', 'true');
    expect(row.querySelector('.active-workout-set__prefill-actions')).toHaveClass('is-hidden');
    await user.click(done);
    await waitFor(() =>
      expect(mocks.enqueue).toHaveBeenCalledWith(
        202,
        1,
        expect.objectContaining({
          actual_weight: 40,
          actual_reps: 8,
          rir: '2',
          is_completed: true,
        }),
        true,
      ),
    );
  });

  it('keeps the helpers adjacent when a previous result is unavailable', () => {
    const { row, controls } = renderWorkout(false);
    expect(row.querySelector('.active-workout-set__prefill-actions')).toBeNull();
    expectDomOrder([
      controls.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' }),
      controls.getByText('Что такое RIR?', { exact: true }),
      controls.getByText('Разминка и блины', { exact: true }),
      controls.getByText('Дополнительно', { exact: true }),
    ]);
  });

  it.each([null, '0', '1', '2', '3', '4+'] as const)(
    'quickly completes the previous result with RIR %s',
    async (rir) => {
      const user = userEvent.setup();
      const { controls } = renderWorkout(true);
      if (rir !== null) {
        const option = controls.getByText(rir, { selector: '.active-workout-rir__options button' });
        await user.click(option);
      }
      await user.click(controls.getByRole('button', { name: 'Подставить и завершить' }));
      await waitFor(() =>
        expect(mocks.enqueue).toHaveBeenCalledWith(
          202,
          1,
          expect.objectContaining({ actual_weight: 40, actual_reps: 8, rir, is_completed: true }),
          true,
        ),
      );
    },
  );
});
