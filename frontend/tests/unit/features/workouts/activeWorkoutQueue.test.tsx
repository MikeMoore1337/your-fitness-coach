import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Workout } from '../../../../src/shared/api/types';
import {
  acknowledgeWorkoutMutation,
  activeWorkoutLockName,
  activeWorkoutQueueKey,
  clearActiveWorkoutData,
  clearActiveWorkoutDataForUser,
  emptyActiveWorkoutQueue,
  enqueueWorkoutMutation,
  loadActiveWorkoutQueue,
  loadCurrentActiveWorkoutSnapshot,
  resolveWorkoutVersionConflict,
  saveActiveWorkoutQueue,
  saveActiveWorkoutSnapshot,
} from '../../../../src/features/workouts/activeWorkoutQueue';
import { useActiveWorkoutQueue } from '../../../../src/features/workouts/useActiveWorkoutQueue';
import { createCrossContextCoordinator } from '../../../../src/shared/browser/crossContextLock';
import { activeWorkoutPointerStorageKey } from '../../../../src/shared/userScopedStorage';

const workout: Workout = {
  id: 42,
  scheduled_date: '2030-01-10',
  title: 'Тренировка A',
  status: 'in_progress',
  day_number: 1,
  week_number: 1,
  started_at: '2030-01-10T10:00:00',
  exercises: [
    {
      id: 101,
      exercise_id: 11,
      exercise_title: 'Жим штанги лежа',
      metric_type: 'strength',
      sort_order: 1,
      prescribed_sets: 1,
      prescribed_reps: '8-10',
      rest_seconds: 90,
      has_guide: false,
      progression_guidance: {
        ruleset_version: 'progression-guidance-v2',
        outcome: 'review',
        message: 'Данных недостаточно — сначала закрепите текущий диапазон повторений',
        detail: 'Нужны полные сопоставимые рабочие подходы в текущем контексте программы.',
        suggested_increment: null,
        suggested_weight: null,
        load_unit: 'kg',
        evidence: {
          target_reps_min: 8,
          target_reps_max: 10,
          prescribed_sets: 1,
          comparable_session_count: 0,
          required_session_count: 2,
          working_set_count: 0,
          rir_recorded_set_count: 0,
          reason_keys: ['too_few_comparable_sessions'],
          sessions: [],
        },
      },
      sets: [
        {
          id: 201,
          set_number: 1,
          actual_reps: null,
          actual_weight: null,
          is_completed: false,
          version: 1,
        },
      ],
    },
  ],
};

const cardioWorkout: Workout = {
  ...workout,
  exercises: workout.exercises.map((exercise) => ({
    ...exercise,
    metric_type: 'cardio',
    prescribed_sets: 1,
    prescribed_reps: '',
    prescribed_duration_minutes: 25,
    rest_seconds: 0,
    progression_guidance: null,
  })),
};

function setOnline(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value });
}

function Harness() {
  const sync = useActiveWorkoutQueue(7, workout);
  const pending = sync.pendingBySet.get(201);
  return (
    <div>
      <span data-testid="pending">{sync.pendingCount}</span>
      <span data-testid="reps">{pending?.values.actual_reps ?? ''}</span>
      <span data-testid="sync-state">{sync.syncState}</span>
      <button
        onClick={() =>
          sync.enqueue(201, 1, { actual_reps: 8, actual_weight: 40, is_completed: true }, true)
        }
      >
        Изменить
      </button>
    </div>
  );
}

function renderHarness() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Harness />
    </QueryClientProvider>,
  );
}

describe('active workout durable queue', () => {
  beforeEach(() => {
    localStorage.clear();
    setOnline(false);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    setOnline(true);
  });

  it('восстанавливает offline-изменение после remount и очищает очередь после reconnect', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 201,
          set_number: 1,
          actual_reps: 8,
          actual_weight: 40,
          is_completed: true,
          version: 2,
        }),
        { status: 200 },
      ),
    );
    const first = renderHarness();

    act(() => screen.getByRole('button', { name: 'Изменить' }).click());
    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('1'));
    expect(screen.getByTestId('reps')).toHaveTextContent('8');
    expect(fetchMock).not.toHaveBeenCalled();
    first.unmount();

    renderHarness();
    expect(screen.getByTestId('pending')).toHaveTextContent('1');
    expect(screen.getByTestId('reps')).toHaveTextContent('8');

    setOnline(true);
    act(() => window.dispatchEvent(new Event('online')));
    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('0'));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual([]);
    expect(loadCurrentActiveWorkoutSnapshot(7)?.id).toBe(42);
    expect(loadCurrentActiveWorkoutSnapshot(7)?.exercises[0]?.progression_guidance).toBeUndefined();
  });

  it('сохраняет локальные данные при stale server вместо бесконечного retry', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: 'workout_not_active',
            message: 'Подходы можно изменять только во время тренировки',
            current: {
              id: 201,
              set_number: 1,
              actual_reps: null,
              actual_weight: null,
              is_completed: false,
              version: 1,
            },
          },
        }),
        { status: 409 },
      ),
    );
    renderHarness();
    act(() => screen.getByRole('button', { name: 'Изменить' }).click());

    setOnline(true);
    act(() => window.dispatchEvent(new Event('online')));
    await waitFor(() => expect(screen.getByTestId('sync-state')).toHaveTextContent('conflict'));
    expect(screen.getByTestId('pending')).toHaveTextContent('1');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('не даёт старой операции из второй вкладки перезаписать более новую', () => {
    let state = emptyActiveWorkoutQueue(7, 42);
    state = enqueueWorkoutMutation(state, {
      setId: 201,
      serverVersion: 1,
      values: { actual_reps: 8, actual_weight: 40, is_completed: true },
      inFlightMutationId: null,
      now: 1,
    });
    const olderId = state.queue[0]!.mutation_id;
    state = enqueueWorkoutMutation(state, {
      setId: 201,
      serverVersion: 1,
      values: { actual_reps: 10, actual_weight: 42.5, is_completed: true },
      inFlightMutationId: olderId,
      now: 2,
    });

    const resolved = resolveWorkoutVersionConflict(state, olderId, 3);

    expect(resolved.queue).toHaveLength(1);
    expect(resolved.queue[0]).toMatchObject({
      expected_version: 3,
      values: { actual_reps: 10, actual_weight: 42.5, is_completed: true },
    });
  });

  it('не теряет interleaved enqueue из двух contexts без Web Locks', async () => {
    const lockName = activeWorkoutLockName(7, 42);
    const firstContext = createCrossContextCoordinator({
      nativeLocks: null,
      ownerId: 'workout-context-a',
      pollMs: 1,
      leaseMs: 1000,
      timeoutMs: 2000,
    });
    const secondContext = createCrossContextCoordinator({
      nativeLocks: null,
      ownerId: 'workout-context-b',
      pollMs: 1,
      leaseMs: 1000,
      timeoutMs: 2000,
    });
    const enqueue = (
      coordinator: ReturnType<typeof createCrossContextCoordinator>,
      setId: number,
    ) =>
      coordinator.run(lockName, () => {
        const current = loadActiveWorkoutQueue(7, 42);
        saveActiveWorkoutQueue(
          enqueueWorkoutMutation(current, {
            setId,
            serverVersion: 1,
            values: { actual_reps: 8, actual_weight: 40, is_completed: true },
          }),
        );
      });

    await Promise.all([enqueue(firstContext, 201), enqueue(secondContext, 202)]);

    expect(
      loadActiveWorkoutQueue(7, 42)
        .queue.map((item) => item.set_id)
        .sort(),
    ).toEqual([201, 202]);
  });

  it('ack и clear под lock не перезаписывают последующую concurrent mutation', async () => {
    let initial = enqueueWorkoutMutation(emptyActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 1,
      values: { actual_reps: 8, actual_weight: 40, is_completed: true },
    });
    const acknowledgedId = initial.queue[0]!.mutation_id;
    initial = enqueueWorkoutMutation(initial, {
      setId: 202,
      serverVersion: 1,
      values: { actual_reps: 10, actual_weight: 30, is_completed: true },
    });
    saveActiveWorkoutQueue(initial);
    const lockName = activeWorkoutLockName(7, 42);
    const firstContext = createCrossContextCoordinator({
      nativeLocks: null,
      ownerId: 'workout-ack-context',
      pollMs: 1,
      leaseMs: 1000,
      timeoutMs: 2000,
    });
    const secondContext = createCrossContextCoordinator({
      nativeLocks: null,
      ownerId: 'workout-enqueue-context',
      pollMs: 1,
      leaseMs: 1000,
      timeoutMs: 2000,
    });

    await Promise.all([
      firstContext.run(lockName, () => {
        saveActiveWorkoutQueue(
          acknowledgeWorkoutMutation(loadActiveWorkoutQueue(7, 42), acknowledgedId, 2),
        );
      }),
      secondContext.run(lockName, () => {
        saveActiveWorkoutQueue(
          enqueueWorkoutMutation(loadActiveWorkoutQueue(7, 42), {
            setId: 203,
            serverVersion: 1,
            values: { actual_reps: 6, actual_weight: 50, is_completed: false },
          }),
        );
      }),
    ]);
    expect(
      loadActiveWorkoutQueue(7, 42)
        .queue.map((item) => item.set_id)
        .sort(),
    ).toEqual([202, 203]);

    const rebasedId = loadActiveWorkoutQueue(7, 42).queue.find(
      (item) => item.set_id === 202,
    )!.mutation_id;
    await Promise.all([
      firstContext.run(lockName, () => {
        saveActiveWorkoutQueue(
          resolveWorkoutVersionConflict(loadActiveWorkoutQueue(7, 42), rebasedId, 4),
        );
      }),
      secondContext.run(lockName, () => {
        saveActiveWorkoutQueue(
          enqueueWorkoutMutation(loadActiveWorkoutQueue(7, 42), {
            setId: 205,
            serverVersion: 1,
            values: { actual_reps: 7, actual_weight: 60, is_completed: false },
          }),
        );
      }),
    ]);
    const afterRebase = loadActiveWorkoutQueue(7, 42);
    expect(afterRebase.queue.find((item) => item.set_id === 202)?.expected_version).toBe(4);
    expect(afterRebase.queue.map((item) => item.set_id).sort()).toEqual([202, 203, 205]);

    let releaseClear!: () => void;
    const clearStarted = new Promise<void>((resolve) => {
      releaseClear = resolve;
    });
    let clearEntered!: () => void;
    const entered = new Promise<void>((resolve) => {
      clearEntered = resolve;
    });
    const clearing = firstContext.run(lockName, async () => {
      clearActiveWorkoutData(7, 42);
      clearEntered();
      await clearStarted;
    });
    await entered;
    const laterEnqueue = secondContext.run(lockName, () => {
      saveActiveWorkoutQueue(
        enqueueWorkoutMutation(loadActiveWorkoutQueue(7, 42), {
          setId: 204,
          serverVersion: 1,
          values: { actual_reps: 12, actual_weight: 20, is_completed: true },
        }),
      );
    });
    releaseClear();
    await Promise.all([clearing, laterEnqueue]);
    expect(loadActiveWorkoutQueue(7, 42).queue.map((item) => item.set_id)).toEqual([204]);
  });

  it('мигрирует queue v1 только после получения актуального metric type', () => {
    const legacySnapshot = {
      ...workout,
      exercises: workout.exercises.map((exercise) => {
        const legacyExercise = { ...exercise } as Partial<typeof exercise>;
        delete legacyExercise.metric_type;
        return legacyExercise;
      }),
    };
    localStorage.setItem(
      activeWorkoutQueueKey(7, 42),
      JSON.stringify({
        schema_version: 1,
        user_id: 7,
        workout_id: 42,
        queue: [
          {
            mutation_id: 'legacy-v1-mutation-0001',
            set_id: 201,
            expected_version: 1,
            values: { actual_reps: 9, actual_weight: 42.5, is_completed: true },
            created_at: 1,
          },
        ],
        workout_snapshot: legacySnapshot,
      }),
    );
    localStorage.setItem(activeWorkoutPointerStorageKey(7), '42');

    expect(loadCurrentActiveWorkoutSnapshot(7)).toBeUndefined();
    expect(localStorage.getItem(activeWorkoutQueueKey(7, 42))).not.toBeNull();

    const restored = loadActiveWorkoutQueue(7, 42, new Set([201]), cardioWorkout);

    expect(restored.schema_version).toBe(2);
    expect(restored.queue[0]?.values).toEqual({
      actual_reps: null,
      actual_weight: null,
      is_completed: false,
    });
    expect(restored.workout_snapshot?.id).toBe(42);
    expect(restored.workout_snapshot?.exercises[0]?.metric_type).toBe('cardio');
    expect(loadCurrentActiveWorkoutSnapshot(7)?.exercises[0]?.metric_type).toBe('cardio');
  });

  it('сохраняет расширенные поля подхода в offline-очереди', () => {
    const state = enqueueWorkoutMutation(emptyActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 1,
      values: {
        actual_reps: 8,
        actual_weight: 40,
        rir: '2',
        set_kind: 'drop',
        reached_failure: false,
        is_completed: true,
      },
      now: 1,
    });

    saveActiveWorkoutQueue(state);

    expect(loadActiveWorkoutQueue(7, 42).queue[0]?.values).toEqual({
      actual_reps: 8,
      actual_weight: 40,
      rir: '2',
      set_kind: 'drop',
      reached_failure: false,
      is_completed: true,
    });
  });

  it('сохраняет cardio-показатели без силовых значений в offline-очереди', () => {
    const state = enqueueWorkoutMutation(emptyActiveWorkoutQueue(7, 42), {
      setId: 204,
      serverVersion: 1,
      values: {
        actual_reps: null,
        actual_weight: null,
        duration_minutes: 27,
        distance_km: 6.4,
        average_heart_rate_bpm: 138,
        heart_rate_zone: 3,
        rir: null,
        set_kind: null,
        reached_failure: null,
        is_completed: true,
      },
      now: 1,
    });

    saveActiveWorkoutQueue(state);

    expect(loadActiveWorkoutQueue(7, 42).queue[0]?.values).toMatchObject({
      actual_reps: null,
      actual_weight: null,
      duration_minutes: 27,
      distance_km: 6.4,
      average_heart_rate_bpm: 138,
      heart_rate_zone: 3,
      is_completed: true,
    });
  });

  it('изолирует аккаунты и удаляет повреждённое хранилище', () => {
    saveActiveWorkoutSnapshot(7, workout);
    saveActiveWorkoutQueue({
      ...emptyActiveWorkoutQueue(8, 43),
      queue: [
        {
          mutation_id: 'valid-mutation-00000001',
          set_id: 301,
          expected_version: 1,
          values: { actual_reps: 6, actual_weight: 30, is_completed: false },
          created_at: 1,
        },
      ],
    });
    localStorage.setItem(activeWorkoutQueueKey(9, 44), '{broken');

    clearActiveWorkoutDataForUser(7);

    expect(loadCurrentActiveWorkoutSnapshot(7)).toBeUndefined();
    expect(loadActiveWorkoutQueue(8, 43).queue).toHaveLength(1);
    expect(loadActiveWorkoutQueue(9, 44).queue).toEqual([]);
    expect(localStorage.getItem(activeWorkoutQueueKey(9, 44))).toBeNull();
  });

  it('переносит прежний unscoped draft только в текущую авторизованную тренировку', () => {
    localStorage.setItem(
      'fit_workout_set_201',
      JSON.stringify({ actual_reps: 9, actual_weight: 42.5 }),
    );
    localStorage.setItem(
      'fit_workout_pending_201',
      JSON.stringify({ actual_reps: 9, actual_weight: 42.5, is_completed: true }),
    );

    saveActiveWorkoutSnapshot(7, workout);

    expect(loadActiveWorkoutQueue(7, 42).queue[0]).toMatchObject({
      set_id: 201,
      expected_version: 1,
      values: { actual_reps: 9, actual_weight: 42.5, is_completed: true },
    });
    expect(localStorage.getItem('fit_workout_set_201')).toBeNull();
    expect(localStorage.getItem('fit_workout_pending_201')).toBeNull();
  });

  it('не переносит силовой unscoped draft в кардио-тренировку', () => {
    localStorage.setItem(
      'fit_workout_pending_201',
      JSON.stringify({ actual_reps: 9, actual_weight: 42.5, is_completed: true }),
    );

    saveActiveWorkoutSnapshot(7, cardioWorkout);

    const restored = loadActiveWorkoutQueue(7, 42);
    expect(restored.queue).toEqual([]);
    expect(restored.workout_snapshot?.exercises[0]?.metric_type).toBe('cardio');
    expect(localStorage.getItem('fit_workout_pending_201')).toBeNull();
  });
});
