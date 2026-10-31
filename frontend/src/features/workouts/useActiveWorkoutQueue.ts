import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, ApiError, getUserFacingErrorMessage } from '../../shared/api/client';
import { crossContextCoordinator } from '../../shared/browser/crossContextLock';
import type { Workout, WorkoutStatus } from '../../shared/api/types';
import { YFC_PLATFORM_ACTIVATED_EVENT } from '../../shared/telegram/layout';
import {
  acknowledgeLegacyWorkoutMutation,
  acknowledgeWorkoutMutation,
  activeWorkoutLockName,
  activeWorkoutQueueKey,
  clearActiveWorkoutData,
  emptyActiveWorkoutQueue,
  enqueueWorkoutMutation,
  latestMutationForSet,
  legacyActiveWorkoutQueueKey,
  loadActiveWorkoutQueue,
  resolveSideWorkoutConflict,
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

interface SideConflict {
  setId: number;
  mutationIds: string[];
  local: ActiveWorkoutSetValues;
  server: WorkoutStatus;
}

function hasSideMode(mode: WorkoutStatus['execution_mode']): boolean {
  return mode === 'per_side' || mode === 'alternating';
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

async function updateCachedSet(
  queryClient: ReturnType<typeof useQueryClient>,
  current: WorkoutStatus,
): Promise<void> {
  // An older GET must not overwrite the version accepted by this PATCH.
  await queryClient.cancelQueries({ queryKey: ['workout', 'today'], exact: true });
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
  const [sideConflict, setSideConflict] = useState<SideConflict | null>(null);
  const sideConflictRef = useRef<SideConflict | null>(null);
  const inFlightId = useRef<string | null>(null);
  const flushPromise = useRef<Promise<boolean> | null>(null);
  const enqueuePromise = useRef<Promise<void> | null>(null);

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
    if (sideConflictRef.current) return false;
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
      if (!validSetIds.has(pending.set_id)) {
        persist(fresh);
        setSyncState('conflict');
        setMessage(
          'Подход больше не найден в тренировке. Локальные данные сохранены на устройстве.',
        );
        return false;
      }
      inFlightId.current = pending.mutation_id;
      try {
        const usesSideContract =
          pending.values.execution_mode === 'per_side' ||
          pending.values.execution_mode === 'alternating' ||
          pending.values.confirm_mode_change === true;
        const saved = await api<WorkoutStatus>(`/api/v1/workouts/sets/${pending.set_id}`, {
          method: 'PATCH',
          body: {
            ...pending.values,
            ...(usesSideContract
              ? { is_completed: 'sides-v1', side_is_completed: pending.values.is_completed }
              : {}),
            expected_version: pending.expected_version,
            mutation_id: pending.mutation_id,
          },
        });
        if (usesSideContract && !Object.hasOwn(saved, 'sides')) {
          setSyncState('error');
          setMessage(
            'Сервер не подтвердил сохранение сторон. Локальные данные сохранены на устройстве.',
          );
          return false;
        }
        await updateCachedSet(queryClient, saved);
        persist(acknowledgeWorkoutMutation(readFresh(), pending.mutation_id, saved.version));
        acknowledgeLegacyWorkoutMutation(userId, workoutId, pending.mutation_id);
        conflictAttempts = 0;
      } catch (reason) {
        if (reason instanceof ApiError && reason.status === 409) {
          const detail = conflictDetail(reason);
          const current = detail?.current;
          if (
            [
              'workout_set_version_conflict',
              'workout_set_side_aware_required',
              'workout_set_mode_change_confirmation',
            ].includes(String(detail?.code)) &&
            validWorkoutStatus(current) &&
            (hasSideMode(pending.values.execution_mode) || hasSideMode(current.execution_mode))
          ) {
            await updateCachedSet(queryClient, current);
            const fresh = readFresh();
            const local = latestMutationForSet(fresh, pending.set_id) ?? pending;
            const conflict = {
              setId: pending.set_id,
              mutationIds: fresh.queue
                .filter((item) => item.set_id === pending.set_id)
                .map((item) => item.mutation_id),
              local: local.values,
              server: current,
            };
            sideConflictRef.current = conflict;
            setSideConflict(conflict);
            setSyncState('conflict');
            setMessage('Подход изменён в другой вкладке. Сравните версии перед сохранением.');
            return false;
          }
          if (detail?.code === 'workout_set_version_conflict' && validWorkoutStatus(current)) {
            await updateCachedSet(queryClient, current);
            persist(
              resolveWorkoutVersionConflict(readFresh(), pending.mutation_id, current.version),
            );
            conflictAttempts += 1;
            continue;
          }
          if (detail?.code === 'workout_set_idempotency_conflict') {
            // Do not silently bypass the server's idempotency protection by changing the ID.
            if (validWorkoutStatus(current)) await updateCachedSet(queryClient, current);
            setSyncState('conflict');
            setMessage(
              getUserFacingErrorMessage(
                reason,
                'Конфликт изменения подхода. Локальные данные сохранены для проверки.',
              ),
            );
            return false;
          }
          setSyncState('conflict');
          setMessage(
            getUserFacingErrorMessage(
              reason,
              'Серверная тренировка уже изменилась. Локальные данные сохранены на устройстве.',
            ),
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
              ? getUserFacingErrorMessage(reason, 'Не удалось синхронизировать тренировку.')
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
  }, [persist, queryClient, readFresh, userId, validSetIds, workoutId]);

  const flushNow = useCallback((): Promise<boolean> => {
    if (flushPromise.current) return flushPromise.current;
    const promise = (async (): Promise<boolean> => {
      if (!lockName) return runQueue();
      try {
        return await crossContextCoordinator.run(lockName, runQueue);
      } catch (reason) {
        setSyncState('error');
        setMessage(getUserFacingErrorMessage(reason, 'Не удалось синхронизировать очередь.'));
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
      onlyIfNoPending = false,
    ): Promise<boolean> => {
      if (!userId || !workoutId || !lockName) return false;
      let releaseEnqueue!: () => void;
      const currentEnqueue = new Promise<void>((resolve) => {
        releaseEnqueue = resolve;
      });
      const previousEnqueue = enqueuePromise.current;
      enqueuePromise.current = currentEnqueue;
      await previousEnqueue;
      try {
        setSyncState(navigator.onLine ? 'pending' : 'offline');
        try {
          const result = await crossContextCoordinator.run(lockName, () => {
            const fresh = readFresh();
            if (onlyIfNoPending && latestMutationForSet(fresh, setId)) {
              return { durable: false, skipped: true };
            }
            const next = enqueueWorkoutMutation(fresh, {
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
            return { durable, skipped: false };
          });
          if (result.skipped) return false;
          const { durable } = result;
          if (!navigator.onLine) {
            setSyncState(durable ? 'offline' : 'error');
            return durable;
          }
          if (!immediate) return durable;
          const acceptDurableOffline = () =>
            durable && !navigator.onLine && latestMutationForSet(readFresh(), setId) !== undefined;
          if (!(await flushNow())) return acceptDurableOffline();
          // An existing flush can finish just before this enqueue acquires its write turn.
          return latestMutationForSet(readFresh(), setId)
            ? (await flushNow()) || acceptDurableOffline()
            : true;
        } catch (reason) {
          setSyncState('error');
          setMessage(getUserFacingErrorMessage(reason, 'Не удалось сохранить изменение.'));
          return false;
        }
      } finally {
        releaseEnqueue();
        if (enqueuePromise.current === currentEnqueue) enqueuePromise.current = null;
      }
    },
    [flushNow, lockName, persist, readFresh, userId, workoutId],
  );

  const clear = useCallback(async () => {
    if (!userId || !workoutId || !lockName) return;
    await crossContextCoordinator.run(lockName, () => {
      if (!clearActiveWorkoutData(userId, workoutId)) {
        const fresh = readFresh();
        setStoredState({ key: activeWorkoutQueueKey(userId, workoutId), data: fresh });
        setSyncState('conflict');
        setMessage(
          'После завершения появились несохранённые изменения. Они остались на устройстве.',
        );
        return;
      }
      storageAvailable.current = true;
      setDurable(true);
      memoryState.current = emptyActiveWorkoutQueue(userId, workoutId);
      setStoredState({
        key: activeWorkoutQueueKey(userId, workoutId),
        data: memoryState.current,
      });
      setSyncState('idle');
      setMessage(null);
      sideConflictRef.current = null;
      setSideConflict(null);
    });
  }, [lockName, readFresh, userId, workoutId]);

  const resolveSideConflict = useCallback(
    async (choice: 'local' | 'server') => {
      const conflict = sideConflictRef.current;
      if (!conflict || !lockName || !userId || !workoutId) return false;
      const resolved = await crossContextCoordinator.run(lockName, () => {
        const fresh = readFresh();
        const mutations = fresh.queue.filter((item) => item.set_id === conflict.setId);
        if (
          mutations.map((item) => item.mutation_id).join(',') !== conflict.mutationIds.join(',')
        ) {
          const latest = mutations.at(-1);
          if (latest) {
            const updated = {
              ...conflict,
              local: latest.values,
              mutationIds: mutations.map((item) => item.mutation_id),
            };
            sideConflictRef.current = updated;
            setSideConflict(updated);
          }
          setMessage('Локальная версия изменилась. Сравните её ещё раз.');
          return false;
        }
        const next = resolveSideWorkoutConflict(
          fresh,
          conflict.setId,
          conflict.server.version,
          choice,
        );
        if (!persist(next, true)) {
          setMessage(
            'Не удалось сохранить выбор на устройстве. Локальная версия сохранена в памяти.',
          );
          return false;
        }
        for (const mutation of mutations) {
          acknowledgeLegacyWorkoutMutation(userId, workoutId, mutation.mutation_id);
        }
        sideConflictRef.current = null;
        setSideConflict(null);
        setSyncState('pending');
        setMessage(null);
        return true;
      });
      if (resolved) void flushNow();
      return resolved;
    },
    [flushNow, lockName, persist, readFresh, userId, workoutId],
  );

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
    const refreshWorkout = async () => {
      const pendingEnqueue = enqueuePromise.current;
      if (pendingEnqueue) await pendingEnqueue;
      if (!pendingEnqueue) await flushNow();
      const nextEnqueue = enqueuePromise.current;
      if (nextEnqueue) await nextEnqueue;
      if (!navigator.onLine || readFresh().queue.length > 0) return;
      await queryClient.invalidateQueries({ queryKey: ['workout', 'today'], exact: true });
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key !== key && event.key !== legacyActiveWorkoutQueueKey(userId!, workoutId!))
        return;
      const fresh = readFresh();
      memoryState.current = fresh;
      setStoredState({ key, data: fresh });
      retry();
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') refreshWorkout();
    };
    window.addEventListener('online', refreshWorkout);
    window.addEventListener('focus', refreshWorkout);
    window.addEventListener('pageshow', refreshWorkout);
    window.addEventListener(YFC_PLATFORM_ACTIVATED_EVENT, retry);
    window.addEventListener('storage', onStorage);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('online', refreshWorkout);
      window.removeEventListener('focus', refreshWorkout);
      window.removeEventListener('pageshow', refreshWorkout);
      window.removeEventListener(YFC_PLATFORM_ACTIVATED_EVENT, retry);
      window.removeEventListener('storage', onStorage);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [flushNow, key, queryClient, readFresh, userId, workoutId]);

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
    sideConflict,
    resolveSideConflict,
    enqueue,
    flushNow,
    clear,
    retry: flushNow,
  };
}
