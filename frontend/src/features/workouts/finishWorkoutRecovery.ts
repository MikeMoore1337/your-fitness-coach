import type { QueryClient } from '@tanstack/react-query';
import type { Workout } from '../../shared/api/types';

export async function reconcileFinishedWorkout(
  queryClient: QueryClient,
  completedWorkout: Workout,
  clearLocalState: () => Promise<void>,
): Promise<void> {
  await clearLocalState();
  await queryClient.invalidateQueries({ queryKey: ['workout'] });
  await queryClient.invalidateQueries({ queryKey: ['weekly-check-ins'] });
  queryClient.setQueryData(['workout', 'today'], completedWorkout);
}
