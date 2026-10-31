import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Workout } from '../../../../src/shared/api/types';
import {
  acknowledgeWorkoutMutation,
  acknowledgeLegacyWorkoutMutation,
  activeWorkoutLockName,
  activeWorkoutQueueKey,
  clearActiveWorkoutData,
  clearActiveWorkoutDataForUser,
  emptyActiveWorkoutQueue,
  enqueueWorkoutMutation,
  loadActiveWorkoutQueue,
  loadCurrentActiveWorkoutSnapshot,
  legacyActiveWorkoutQueueKey,
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
  const [accepted, setAccepted] = useState<boolean | null>(null);
  const pending = sync.pendingBySet.get(201);
  return (
    <div>
      <span data-testid="pending">{sync.pendingCount}</span>
      <span data-testid="reps">{pending?.values.actual_reps ?? ''}</span>
      <span data-testid="sync-state">{sync.syncState}</span>
      <span data-testid="message">{sync.message ?? ''}</span>
      <span data-testid="accepted">{accepted === null ? 'waiting' : String(accepted)}</span>
      <button
        onClick={async () =>
          setAccepted(
            await sync.enqueue(
              201,
              1,
              { actual_reps: 8, actual_weight: 40, is_completed: true },
              true,
            ),
          )
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

function SideHarness() {
  const sync = useActiveWorkoutQueue(7, workout);
  return (
    <div>
      <span data-testid="side-state">{sync.syncState}</span>
      <span data-testid="side-local">
        {sync.sideConflict?.local.sides?.left?.actual_weight ?? ''}
      </span>
      <span data-testid="side-server">
        {sync.sideConflict?.server.sides?.left?.actual_weight ?? ''}
      </span>
      <button
        onClick={() =>
          void sync.enqueue(
            201,
            1,
            {
              actual_reps: null,
              actual_weight: null,
              execution_mode: 'per_side',
              is_completed: false,
              sides: {
                left: { actual_reps: 10, actual_weight: 18, is_completed: true },
                right: { actual_reps: 8, actual_weight: 16, is_completed: false },
              },
            },
            true,
          )
        }
      >
        Сохранить стороны
      </button>
      <button onClick={() => void sync.resolveSideConflict('local')}>Оставить локальную</button>
      <button onClick={() => void sync.resolveSideConflict('server')}>Выбрать серверную</button>
    </div>
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

  it('использует подтверждённую версию своего предыдущего сохранения для следующего ввода', async () => {
    setOnline(true);
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      const body = JSON.parse(init!.body as string);
      return new Response(
        JSON.stringify({
          id: 201,
          set_number: 1,
          execution_mode: 'per_side',
          is_completed: false,
          sides: body.sides,
          version: body.expected_version + 1,
        }),
        { status: 200 },
      );
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <SideHarness />
      </QueryClientProvider>,
    );
    act(() => screen.getByRole('button', { name: 'Сохранить стороны' }).click());
    await waitFor(() => expect(screen.getByTestId('side-state')).toHaveTextContent('idle'));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    act(() => screen.getByRole('button', { name: 'Сохранить стороны' }).click());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetchMock.mock.calls[1]![1]!.body as string).expected_version).toBe(2);
  });

  it('не перебазирует стороны при 409 до явного выбора полной версии', async () => {
    setOnline(true);
    const server = {
      id: 201,
      set_number: 1,
      version: 2,
      is_completed: false,
      execution_mode: 'per_side',
      sides: {
        left: { actual_reps: 9, actual_weight: 20, is_completed: true },
        right: { actual_reps: 8, actual_weight: 15, is_completed: false },
      },
    };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: { code: 'workout_set_version_conflict', current: server },
          }),
          { status: 409 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...server,
            version: 3,
            sides: {
              left: { actual_reps: 10, actual_weight: 18, is_completed: true },
              right: { actual_reps: 8, actual_weight: 16, is_completed: false },
            },
          }),
          { status: 200 },
        ),
      );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <SideHarness />
      </QueryClientProvider>,
    );
    act(() => screen.getByRole('button', { name: 'Сохранить стороны' }).click());
    await waitFor(() => expect(screen.getByTestId('side-state')).toHaveTextContent('conflict'));
    expect(screen.getByTestId('side-local')).toHaveTextContent('18');
    expect(screen.getByTestId('side-server')).toHaveTextContent('20');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    act(() => window.dispatchEvent(new Event('online')));
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    act(() => screen.getByRole('button', { name: 'Оставить локальную' }).click());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const first = JSON.parse(fetchMock.mock.calls[0]![1]!.body as string);
    const second = JSON.parse(fetchMock.mock.calls[1]![1]!.body as string);
    expect(first.is_completed).toBe('sides-v1');
    expect(first.side_is_completed).toBe(false);
    expect(second).toMatchObject({
      expected_version: 2,
      confirm_mode_change: true,
      sides: { left: { actual_weight: 18 }, right: { actual_weight: 16 } },
    });
    expect(second.mutation_id).not.toBe(first.mutation_id);
    await waitFor(() => expect(loadActiveWorkoutQueue(7, 42).queue).toHaveLength(0));
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

  it('не принимает offline-завершение при отказе durable storage', async () => {
    renderHarness();
    await waitFor(() => expect(loadCurrentActiveWorkoutSnapshot(7)?.id).toBe(42));
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Quota', 'QuotaExceededError');
    });
    act(() => screen.getByRole('button', { name: 'Изменить' }).click());
    await waitFor(() => expect(screen.getByTestId('accepted')).toHaveTextContent('false'));
    expect(screen.getByTestId('sync-state')).toHaveTextContent('error');
    expect(screen.getByTestId('pending')).toHaveTextContent('0');
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual([]);
  });

  it('принимает durable completion, если сеть пропала во время flush', async () => {
    setOnline(true);
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      setOnline(false);
      throw new TypeError('Failed to fetch');
    });
    renderHarness();

    act(() => screen.getByRole('button', { name: 'Изменить' }).click());

    await waitFor(() => expect(screen.getByTestId('accepted')).toHaveTextContent('true'));
    expect(screen.getByTestId('pending')).toHaveTextContent('1');
    expect(screen.getByTestId('sync-state')).toHaveTextContent('offline');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('возвращает отказ API без удаления данных для явного повтора', async () => {
    setOnline(true);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Сервис временно недоступен' }), { status: 503 }),
    );
    renderHarness();
    act(() => screen.getByRole('button', { name: 'Изменить' }).click());
    await waitFor(() => expect(screen.getByTestId('accepted')).toHaveTextContent('false'));
    expect(screen.getByTestId('sync-state')).toHaveTextContent('error');
    expect(loadActiveWorkoutQueue(7, 42).queue[0]?.values).toMatchObject({
      is_completed: true,
      actual_reps: 8,
      actual_weight: 40,
    });
  });

  it('различает таймаут PATCH и оставляет завершение для явного повтора', async () => {
    setOnline(true);
    vi.useFakeTimers();
    try {
      const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((_input, init) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('The request timed out', 'AbortError'));
          });
        });
      });
      renderHarness();

      act(() => screen.getByRole('button', { name: 'Изменить' }).click());
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(fetchMock).toHaveBeenCalledTimes(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(15_000);
      });

      expect(screen.getByTestId('accepted')).toHaveTextContent('false');
      expect(screen.getByTestId('sync-state')).toHaveTextContent('offline');
      expect(screen.getByTestId('message')).toHaveTextContent(
        'Сервер не ответил вовремя. Попробуйте снова.',
      );
      expect(screen.getByTestId('pending')).toHaveTextContent('1');
      expect(loadActiveWorkoutQueue(7, 42).queue[0]?.values.is_completed).toBe(true);
    } finally {
      vi.useRealTimers();
    }
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
    expect(
      loadActiveWorkoutQueue(7, 42)
        .queue.map((item) => item.set_id)
        .sort(),
    ).toEqual([202, 203, 204, 205]);
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

    expect(restored.schema_version).toBe(3);
    expect(restored.queue[0]?.values).toEqual({
      actual_reps: null,
      actual_weight: null,
      is_completed: false,
    });
    expect(restored.workout_snapshot?.id).toBe(42);
    expect(restored.workout_snapshot?.exercises[0]?.metric_type).toBe('cardio');
    expect(loadCurrentActiveWorkoutSnapshot(7)?.exercises[0]?.metric_type).toBe('cardio');
  });

  it('сохраняет обе стороны отдельно от очереди старой вкладки и переносит v2 без потерь', () => {
    const oldKey = legacyActiveWorkoutQueueKey(7, 42);
    const oldMutation = {
      mutation_id: 'legacy-v2-mutation-0001',
      set_id: 201,
      expected_version: 1,
      values: { actual_reps: 8, actual_weight: 40, is_completed: false },
      created_at: 1,
    };
    localStorage.setItem(
      oldKey,
      JSON.stringify({
        schema_version: 2,
        user_id: 7,
        workout_id: 42,
        queue: [oldMutation],
        workout_snapshot: workout,
      }),
    );
    const migrated = loadActiveWorkoutQueue(7, 42, new Set([201]), workout);
    expect(migrated.schema_version).toBe(3);
    expect(migrated.queue).toEqual([oldMutation]);
    expect(JSON.parse(localStorage.getItem(oldKey)!).queue).toEqual([oldMutation]);
    acknowledgeLegacyWorkoutMutation(7, 42, oldMutation.mutation_id);
    expect(JSON.parse(localStorage.getItem(oldKey)!).queue).toEqual([]);

    const sideState = enqueueWorkoutMutation(emptyActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 2,
      values: {
        actual_reps: null,
        actual_weight: null,
        execution_mode: 'per_side',
        is_completed: false,
        sides: {
          left: { actual_reps: 10, actual_weight: 18, rir: '2', is_completed: true },
          right: { actual_reps: 8, actual_weight: 16, rir: '0', is_completed: false },
        },
      },
    });
    expect(saveActiveWorkoutQueue(sideState)).toBe(true);
    localStorage.setItem(
      oldKey,
      JSON.stringify({
        schema_version: 2,
        user_id: 7,
        workout_id: 42,
        queue: [oldMutation],
      }),
    );
    const combined = loadActiveWorkoutQueue(7, 42);
    expect(combined.queue.map((item) => item.mutation_id)).toEqual([
      oldMutation.mutation_id,
      sideState.queue[0]!.mutation_id,
    ]);
    expect(combined.queue[1]?.values.sides).toEqual(sideState.queue[0]?.values.sides);
    expect(JSON.parse(localStorage.getItem(oldKey)!).queue).toEqual([oldMutation]);
  });

  it('не объединяет версии одного подхода из разных вкладок до разрешения конфликта', () => {
    const values = {
      actual_reps: null,
      actual_weight: null,
      execution_mode: 'per_side' as const,
      is_completed: false,
      sides: {
        left: { actual_reps: 10, actual_weight: 18, is_completed: true },
        right: { actual_reps: 8, actual_weight: 16, is_completed: false },
      },
    };
    let state = enqueueWorkoutMutation(emptyActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 1,
      values,
      originId: 'context-a-0000000001',
    });
    state = enqueueWorkoutMutation(state, {
      setId: 201,
      serverVersion: 1,
      values: {
        ...values,
        sides: {
          ...values.sides,
          right: {
            actual_reps: 9,
            actual_weight: 17,
            is_completed: true,
          },
        },
      },
      originId: 'context-b-0000000001',
    });
    expect(state.queue).toHaveLength(2);
    expect(state.queue[1]?.expected_version).toBe(1);
    const afterFirstSave = acknowledgeWorkoutMutation(state, state.queue[0]!.mutation_id, 2);
    expect(afterFirstSave.queue[0]?.expected_version).toBe(1);
    expect(afterFirstSave.queue[0]?.values.sides?.right?.actual_weight).toBe(17);
  });

  it('передаёт автору подтверждение, если его операцию отправила соседняя вкладка', () => {
    const values = {
      actual_reps: null,
      actual_weight: null,
      execution_mode: 'per_side' as const,
      is_completed: false,
      sides: { left: { actual_weight: 18, actual_reps: 10, is_completed: true }, right: null },
    };
    let state = enqueueWorkoutMutation(emptyActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 1,
      values,
      originId: 'context-a-0000000001',
    });
    state = acknowledgeWorkoutMutation(state, state.queue[0]!.mutation_id, 2);
    saveActiveWorkoutQueue(state);
    const restored = loadActiveWorkoutQueue(7, 42);
    expect(
      enqueueWorkoutMutation(restored, {
        setId: 201,
        serverVersion: 1,
        values,
        originId: 'context-a-0000000001',
      }).queue[0]?.expected_version,
    ).toBe(2);
    expect(
      enqueueWorkoutMutation(restored, {
        setId: 201,
        serverVersion: 1,
        values,
        originId: 'context-b-0000000001',
      }).queue[0]?.expected_version,
    ).toBe(1);
  });

  it('не удаляет локальные изменения при смене или завершении тренировки', () => {
    const state = enqueueWorkoutMutation(emptyActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 1,
      values: { actual_reps: 8, actual_weight: 40, is_completed: true },
    });
    saveActiveWorkoutQueue(state);
    localStorage.setItem(activeWorkoutPointerStorageKey(7), '42');
    saveActiveWorkoutSnapshot(7, { ...workout, id: 43 });
    clearActiveWorkoutData(7, 42);
    expect(loadActiveWorkoutQueue(7, 42).queue[0]?.mutation_id).toBe(state.queue[0]?.mutation_id);
  });

  it('сохраняет ожидающий подход, если текущий серверный снимок его больше не содержит', () => {
    const state = enqueueWorkoutMutation(emptyActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 1,
      values: { actual_reps: 8, actual_weight: 40, is_completed: true },
    });
    saveActiveWorkoutQueue(state);
    expect(loadActiveWorkoutQueue(7, 42, new Set([202])).queue[0]?.mutation_id).toBe(
      state.queue[0]?.mutation_id,
    );
    expect(clearActiveWorkoutData(7, 42)).toBe(false);
  });

  it.each([null, '0', '1', '2', '3', '4+'] as const)(
    'сохраняет RIR %s вместе с завершённым подходом в offline-очереди',
    (rir) => {
      const state = enqueueWorkoutMutation(emptyActiveWorkoutQueue(7, 42), {
        setId: 201,
        serverVersion: 1,
        values: { actual_reps: 8, actual_weight: 40, rir, is_completed: true },
        now: 1,
      });

      expect(saveActiveWorkoutQueue(state)).toBe(true);
      expect(loadActiveWorkoutQueue(7, 42).queue[0]?.values).toEqual({
        actual_reps: 8,
        actual_weight: 40,
        rir,
        is_completed: true,
      });
    },
  );

  it('восстанавливает завершённый подход без поля RIR', () => {
    const state = enqueueWorkoutMutation(emptyActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 1,
      values: { actual_reps: 8, actual_weight: 40, is_completed: true },
    });

    expect(saveActiveWorkoutQueue(state)).toBe(true);
    expect(loadActiveWorkoutQueue(7, 42).queue[0]?.values).toEqual({
      actual_reps: 8,
      actual_weight: 40,
      is_completed: true,
    });
  });

  it('не принимает 4 вместо отдельного значения 4+ в сохранённой очереди', () => {
    const state = enqueueWorkoutMutation(emptyActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 1,
      values: { actual_reps: 8, actual_weight: 40, rir: '4+', is_completed: true },
    });
    expect(saveActiveWorkoutQueue(state)).toBe(true);
    const key = activeWorkoutQueueKey(7, 42);
    const stored = JSON.parse(localStorage.getItem(key)!);
    stored.queue[0].values.rir = '4';
    localStorage.setItem(key, JSON.stringify(stored));

    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual([]);
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
