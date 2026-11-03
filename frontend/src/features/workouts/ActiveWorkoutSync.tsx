import { createContext, useContext, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { Workout } from '../../shared/api/types';
import { loadCurrentActiveWorkoutSnapshot } from './activeWorkoutQueue';
import { useActiveWorkoutQueue } from './useActiveWorkoutQueue';

export const ActiveWorkoutSyncContext = createContext<ReturnType<
  typeof useActiveWorkoutQueue
> | null>(null);

export function ActiveWorkoutSyncProvider({
  userId,
  enabled,
  children,
}: {
  userId: number | undefined;
  enabled: boolean;
  children: ReactNode;
}) {
  const workout = useQuery({
    queryKey: ['workout', 'today'],
    queryFn: () => api<Workout>('/api/v1/workouts/today'),
    enabled: false,
    initialData: () => (enabled && userId ? loadCurrentActiveWorkoutSnapshot(userId) : undefined),
    initialDataUpdatedAt: 0,
  });
  const sync = useActiveWorkoutQueue(
    enabled ? userId : undefined,
    enabled ? workout.data : undefined,
  );
  return (
    <ActiveWorkoutSyncContext.Provider value={enabled ? sync : null}>
      {children}
    </ActiveWorkoutSyncContext.Provider>
  );
}

export function ActiveWorkoutSyncNotice() {
  const sync = useContext(ActiveWorkoutSyncContext);
  if (!sync?.pendingCount) return null;
  return (
    <p className="muted" role="status">
      {sync.message ??
        (sync.durable
          ? 'Изменения тренировки сохранены на устройстве и ожидают синхронизации.'
          : 'Не удалось сохранить изменения на устройстве. Не закрывайте приложение.')}
    </p>
  );
}
