import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import { crossContextCoordinator } from '../../shared/browser/crossContextLock';
import type { Workout, WorkoutStatus } from '../../shared/api/types';
import { YFC_PLATFORM_ACTIVATED_EVENT } from '../../shared/telegram/layout';
import {
  acknowledgeWorkoutMutation,
  activeWorkoutLockName,
  activeWorkoutQueueKey,
  clearActiveWorkoutData,
  emptyActiveWorkoutQueue,
  createWorkoutMutationId,
  enqueueWorkoutMutation,
  latestMutationForSet,
  loadActiveWorkoutQueue,
  resolveWorkoutVersionConflict,
  saveActiveWorkoutSnapshot,
  saveActiveWorkoutQueue,
  type ActiveWorkoutQueue,
  type ActiveWorkoutSetValues,
} from './activeWorkoutQueue';

type SyncState = 'idle' | 'pending' | 'syncing' | 'offline' | 'error' | 'conflict';

interface ConflictDetail {
  code?: unknown;
  message?: unknown;
  current?: unknown;
}

function conflictDetail(error: ApiError): ConflictDetail | null {
  if (!error.body || typeof error.body !== 'object' || !('detail' in error.body)) return null;
  const detail = (error.body as { detail?: unknown }).detail;
  return detail && typeof detail === 'object' ? (detail as ConflictDetail) : null;
}

function validWorkoutStatus(value: unknown): value is WorkoutStatus {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<WorkoutStatus>;
  return (
    Number.isInteger(item.id) &&
    Number.isInteger(item.version) &&
    Number(item.version) >= 1 &&
    typeof item.is_completed === 'boolean'
  );
}

function updateCachedSet(queryClient: ReturnType<typeof useQueryClient>, current: WorkoutStatus) {
  queryClient.setQueryData<Workout>(['workout', 'today'], (workout) => {
    if (!workout) return workout;
    return {
      ...workout,
      exercises: workout.exercises.map((exercise) => ({
        ...exercise,
        sets: exercise.sets.map((set) => (set.id === current.id ? { ...set, ...current } : set)),
      })),
    };
  });
}

export function useActiveWorkoutQueue(userId: number | undefined, workout: Workout | undefined) {
  const queryClient = useQueryClient();
  const workoutId = workout?.id;
  const validSetIds = useMemo(
    () =>
      new Set(workout?.exercises.flatMap((exercise) => exercise.sets.map((set) => set.id)) ?? []),
    [workout],
  );
  const key = userId && workoutId ? activeWorkoutQueueKey(userId, workoutId) : null;
  const lockName = userId && workoutId ? activeWorkoutLockName(userId, workoutId) : null;
  const [storedState, setStoredState] = useState<{
    key: string | null;
    data: ActiveWorkoutQueue;
  }>(() => ({
    key,
    data:
      userId && workoutId
        ? loadActiveWorkoutQueue(userId, workoutId, validSetIds, workout)
        : emptyActiveWorkoutQueue(0, 0),
  }));
  const memoryState = useRef(storedState.data);
  const storageAvailable = useRef(true);
  const [durable, setDurable] = useState(true);
  const loadedState = useMemo(
    () =>
      userId && workoutId
        ? loadActiveWorkoutQueue(userId, workoutId, validSetIds, workout)
        : emptyActiveWorkoutQueue(0, 0),
    [userId, validSetIds, workout, workoutId],
  );
  const state = storedState.key === key ? storedState.data : loadedState;
  const [syncState, setSyncState] = useState<SyncState>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const inFlightId = useRef<string | null>(null);
  const flushPromise = useRef<Promise<boolean> | null>(null);

  const persist = useCallback((next: ActiveWorkoutQueue, requireDurable = false) => {
    const durable = saveActiveWorkoutQueue(next);
    storageAvailable.current = durable;
    setDurable(durable);
    if (requireDurable && !durable) return false;
    memoryState.current = next;
    setStoredState({ key: activeWorkoutQueueKey(next.user_id, next.workout_id), data: next });
    return durable;
  }, []);

  const readFresh = useCallback(() => {
    if (!userId || !workoutId) return emptyActiveWorkoutQueue(0, 0);
    if (!storageAvailable.current) {
      const current = memoryState.current;
      return current.user_id === userId && current.workout_id === workoutId
        ? current
        : emptyActiveWorkoutQueue(userId, workoutId);
    }
    const fresh = loadActiveWorkoutQueue(userId, workoutId, validSetIds, workout);
    memoryState.current = fresh;
    return fresh;
  }, [userId, validSetIds, workout, workoutId]);

  const persistSnapshot = useCallback(() => {
    if (!userId || !workout || workout.status !== 'in_progress') return;
    const next = saveActiveWorkoutSnapshot(userId, workout);
    if (!next) return;
    memoryState.current = next;
    setStoredState({ key: activeWorkoutQueueKey(userId, workout.id), data: next });
  }, [userId, workout]);

  const persistSnapshotWithLock = useCallback(() => {
    if (!lockName) {
      persistSnapshot();
      return;
    }
    void crossContextCoordinator.run(lockName, persistSnapshot).catch(() => undefined);
  }, [lockName, persistSnapshot]);

  useEffect(() => {
    if (!userId || !workout || workout.status !== 'in_progress') return;
    let cancelled = false;
    void crossContextCoordinator
      .run(activeWorkoutLockName(userId, workout.id), () => {
        if (cancelled) return;
        persistSnapshot();
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [persistSnapshot, userId, validSetIds, workout]);

  useEffect(() => {
    const persistWhenHidden = () => {
      if (document.visibilityState === 'hidden') persistSnapshotWithLock();
    };
    window.addEventListener('pagehide', persistSnapshotWithLock);
    window.addEventListener('freeze', persistSnapshotWithLock);
    document.addEventListener('visibilitychange', persistWhenHidden);
    return () => {
      window.removeEventListener('pagehide', persistSnapshotWithLock);
      window.removeEventListener('freeze', persistSnapshotWithLock);
      document.removeEventListener('visibilitychange', persistWhenHidden);
    };
  }, [persistSnapshotWithLock]);

  const runQueue = useCallback(async (): Promise<boolean> => {
    if (!userId || !workoutId || !navigator.onLine) {
      setSyncState('offline');
      setMessage(
        storageAvailable.current
          ? 'Нет сети. Изменения сохранены на этом устройстве.'
          : 'Нет сети и хранилище устройства недоступно. Не закрывайте приложение.',
      );
      return false;
    }
    setSyncState('syncing');
    setMessage(null);
    let conflictAttempts = 0;
    while (conflictAttempts < 12) {
      const fresh = readFresh();
      const pending = fresh.queue[0];
      if (!pending) {
        persist(fresh);
        setSyncState('idle');
        return true;
      }
      inFlightId.current = pending.mutation_id;
      try {
        const saved = await api<WorkoutStatus>(`/api/v1/workouts/sets/${pending.set_id}`, {
          method: 'PATCH',
          body: {
            ...pending.values,
            expected_version: pending.expected_version,
            mutation_id: pending.mutation_id,
          },
        });
        updateCachedSet(queryClient, saved);
        persist(acknowledgeWorkoutMutation(readFresh(), pending.mutation_id, saved.version));
        conflictAttempts = 0;
      } catch (reason) {
        if (reason instanceof ApiError && reason.status === 409) {
          const detail = conflictDetail(reason);
          const current = detail?.current;
          if (detail?.code === 'workout_set_version_conflict' && validWorkoutStatus(current)) {
            updateCachedSet(queryClient, current);
            persist(
              resolveWorkoutVersionConflict(readFresh(), pending.mutation_id, current.version),
            );
            conflictAttempts += 1;
            continue;
          }
          if (detail?.code === 'workout_set_idempotency_conflict' && validWorkoutStatus(current)) {
            const rebased = resolveWorkoutVersionConflict(
              readFresh(),
              pending.mutation_id,
              current.version,
            );
            const index = rebased.queue.findIndex(
              (item) => item.mutation_id === pending.mutation_id,
            );
            if (index >= 0) {
              rebased.queue[index] = {
                ...rebased.queue[index]!,
                mutation_id: createWorkoutMutationId(),
              };
            }
            persist(rebased);
            conflictAttempts += 1;
            continue;
          }
          setSyncState('conflict');
          setMessage(
            typeof detail?.message === 'string'
              ? detail.message
              : 'Серверная тренировка уже изменилась. Локальные данные сохранены на устройстве.',
          );
          return false;
        }
        setSyncState(
          !navigator.onLine || (reason instanceof ApiError && reason.status === 0)
            ? 'offline'
            : 'error',
        );
        setMessage(
          !storageAvailable.current
            ? 'Изменения ещё не сохранены. Хранилище устройства недоступно. Не закрывайте приложение.'
            : navigator.onLine
              ? reason instanceof Error
                ? reason.message
                : 'Не удалось синхронизировать тренировку.'
              : 'Нет сети. Изменения сохранены на этом устройстве.',
        );
        return false;
      } finally {
        inFlightId.current = null;
      }
    }
    setSyncState('conflict');
    setMessage('Тренировка часто меняется в другой вкладке. Повторите синхронизацию.');
    return false;
  }, [persist, queryClient, readFresh, userId, workoutId]);

  const flushNow = useCallback((): Promise<boolean> => {
    if (flushPromise.current) return flushPromise.current;
    const promise = (async (): Promise<boolean> => {
      if (!lockName) return runQueue();
      try {
        return await crossContextCoordinator.run(lockName, runQueue);
      } catch (reason) {
        setSyncState('error');
        setMessage(
          reason instanceof Error ? reason.message : 'Не удалось синхронизировать очередь.',
        );
        return false;
      }
    })();
    flushPromise.current = promise;
    void promise.finally(() => {
      flushPromise.current = null;
    });
    return promise;
  }, [lockName, runQueue]);

  const enqueue = useCallback(
    async (
      setId: number,
      serverVersion: number,
      values: ActiveWorkoutSetValues,
      immediate = false,
    ): Promise<boolean> => {
      if (!userId || !workoutId || !lockName) return false;
      setSyncState(navigator.onLine ? 'pending' : 'offline');
      try {
        const durable = await crossContextCoordinator.run(lockName, () => {
          const next = enqueueWorkoutMutation(readFresh(), {
            setId,
            serverVersion,
            values,
            inFlightMutationId: inFlightId.current,
          });
          const durable = persist(next, immediate && !navigator.onLine);
          setMessage(
            durable
              ? navigator.onLine
                ? null
                : 'Нет сети. Изменения сохранены на этом устройстве.'
              : 'Хранилище устройства недоступно. Не закрывайте приложение до синхронизации.',
          );
          return durable;
        });
        if (!navigator.onLine) {
          setSyncState(durable ? 'offline' : 'error');
          return durable;
        }
        if (!immediate) return durable;
        if (!(await flushNow())) return false;
        // An existing flush can finish just before this enqueue acquires its write turn.
        return latestMutationForSet(readFresh(), setId) ? await flushNow() : true;
      } catch (reason) {
        setSyncState('error');
        setMessage(reason instanceof Error ? reason.message : 'Не удалось сохранить изменение.');
        return false;
      }
    },
    [flushNow, lockName, persist, readFresh, userId, workoutId],
  );

  const clear = useCallback(async () => {
    if (!userId || !workoutId || !lockName) return;
    await crossContextCoordinator.run(lockName, () => {
      clearActiveWorkoutData(userId, workoutId);
      storageAvailable.current = true;
      setDurable(true);
      memoryState.current = emptyActiveWorkoutQueue(userId, workoutId);
      setStoredState({
        key: activeWorkoutQueueKey(userId, workoutId),
        data: memoryState.current,
      });
      setSyncState('idle');
      setMessage(null);
    });
  }, [lockName, userId, workoutId]);

  useEffect(() => {
    if (
      !key ||
      state.queue.length === 0 ||
      !navigator.onLine ||
      syncState === 'conflict' ||
      syncState === 'syncing' ||
      syncState === 'offline' ||
      syncState === 'error'
    )
      return;
    const timer = window.setTimeout(() => void flushNow(), 600);
    return () => window.clearTimeout(timer);
  }, [flushNow, key, state.queue, syncState]);

  useEffect(() => {
    if (!key) return;
    const retry = () => void flushNow();
    const refreshWorkout = () => {
      if (navigator.onLine) {
        void queryClient.invalidateQueries({ queryKey: ['workout', 'today'], exact: true });
      }
      retry();
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key !== key) return;
      const fresh = readFresh();
      memoryState.current = fresh;
      setStoredState({ key, data: fresh });
      retry();
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') refreshWorkout();
    };
    window.addEventListener('online', retry);
    window.addEventListener('focus', refreshWorkout);
    window.addEventListener('pageshow', refreshWorkout);
    window.addEventListener(YFC_PLATFORM_ACTIVATED_EVENT, retry);
    window.addEventListener('storage', onStorage);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('online', retry);
      window.removeEventListener('focus', refreshWorkout);
      window.removeEventListener('pageshow', refreshWorkout);
      window.removeEventListener(YFC_PLATFORM_ACTIVATED_EVENT, retry);
      window.removeEventListener('storage', onStorage);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [flushNow, key, queryClient, readFresh]);

  const pendingBySet = useMemo(() => {
    const result = new Map<number, ReturnType<typeof latestMutationForSet>>();
    for (const setId of validSetIds) {
      const pending = latestMutationForSet(state, setId);
      if (pending) result.set(setId, pending);
    }
    return result;
  }, [state, validSetIds]);

  return {
    pendingBySet,
    pendingCount: state.queue.length,
    durable,
    syncState,
    message,
    enqueue,
    flushNow,
    clear,
    retry: flushNow,
  };
}
