import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import {
  invalidateMeasurementMutation,
  invalidateNutritionSummaries,
  queryKeys,
} from '../../../src/shared/queryKeys';

function queryClientWithInvalidationSpy() {
  const queryClient = new QueryClient();
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();
  return { queryClient, invalidate };
}

describe('domain query invalidation', () => {
  it('invalidates current personal state after a personal measurement', async () => {
    const { queryClient, invalidate } = queryClientWithInvalidationSpy();

    await invalidateMeasurementMutation(queryClient);

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.measurements.subject() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.progress.summaries });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.nutrition.diary });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.nutrition.currentTarget });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['nutrition', 'targets', 'history'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.notifications.all });
  });

  it('invalidates client summaries after a trainer nutrition mutation', async () => {
    const { queryClient, invalidate } = queryClientWithInvalidationSpy();

    await invalidateNutritionSummaries(queryClient, 42);

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.trainer.clientSummary(42) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.trainer.clientSummaries });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.trainer.clients });
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: queryKeys.progress.summaries });
  });
});
