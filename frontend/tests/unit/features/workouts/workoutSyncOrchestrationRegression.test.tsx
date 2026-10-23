import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useActiveWorkoutQueue } from '../../../../src/features/workouts/useActiveWorkoutQueue';
import { loadActiveWorkoutQueue } from '../../../../src/features/workouts/activeWorkoutQueue';
import type { Workout } from '../../../../src/shared/api/types';

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
      exercise_title: 'Жим штанги лёжа',
      metric_type: 'strength',
      sort_order: 1,
      prescribed_sets: 1,
      prescribed_reps: '8-10',
      rest_seconds: 90,
      has_guide: false,
      progression_guidance: null,
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

const saved = {
  id: 201,
  set_number: 1,
  actual_reps: 8,
  actual_weight: 40,
  is_completed: true,
  version: 2,
};

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}
function makeWrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}
const complete = { actual_reps: 8, actual_weight: 40, is_completed: true };

describe('QA: delayed GET and idempotency conflict', () => {
  beforeEach(() => {
    localStorage.clear();
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('does not let a GET started before successful PATCH undo acknowledged completion', async () => {
    const client = makeClient();
    client.setQueryData(['workout', 'today'], workout);
    let resolveStaleGet!: (value: Workout) => void;
    const staleGet = new Promise<Workout>((resolve) => {
      resolveStaleGet = resolve;
    });
    const query = client.fetchQuery({
      queryKey: ['workout', 'today'],
      queryFn: () => staleGet,
    });
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify(saved), { status: 200 }));
    const { result } = renderHook(() => useActiveWorkoutQueue(7, workout), {
      wrapper: makeWrapper(client),
    });
    let accepted = false;
    await act(async () => {
      accepted = await result.current.enqueue(201, 1, complete, true);
    });
    expect(accepted).toBe(true);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(
      client.getQueryData<Workout>(['workout', 'today'])?.exercises[0]?.sets[0]?.is_completed,
    ).toBe(true);
    await act(async () => {
      resolveStaleGet(workout);
      await query;
    });
    expect(
      client.getQueryData<Workout>(['workout', 'today'])?.exercises[0]?.sets[0]?.is_completed,
    ).toBe(true);
    expect(loadActiveWorkoutQueue(7, 42).queue).toHaveLength(0);
  });

  it('stops on idempotency conflict instead of retrying with a new mutation ID', async () => {
    const client = makeClient();
    let requestCount = 0;
    const sentMutationIds: string[] = [];
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => {
      requestCount += 1;
      const payload = JSON.parse(String(options?.body)) as { mutation_id: string };
      sentMutationIds.push(payload.mutation_id);
      if (requestCount === 1) {
        return new Response(
          JSON.stringify({
            detail: {
              code: 'workout_set_idempotency_conflict',
              message: 'Этот идентификатор изменения уже использован с другими данными',
              current: { ...saved, is_completed: false, version: 2 },
            },
          }),
          { status: 409 },
        );
      }
      return new Response(JSON.stringify(saved), { status: 200 });
    });
    const { result } = renderHook(() => useActiveWorkoutQueue(7, workout), {
      wrapper: makeWrapper(client),
    });
    let accepted = true;
    await act(async () => {
      accepted = await result.current.enqueue(201, 1, complete, true);
    });
    await waitFor(() => expect(result.current.syncState).toBe('conflict'));
    expect(accepted).toBe(false);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(sentMutationIds).toHaveLength(1);
    expect(loadActiveWorkoutQueue(7, 42).queue[0]?.mutation_id).toBe(sentMutationIds[0]);
    expect(loadActiveWorkoutQueue(7, 42).queue[0]?.values.is_completed).toBe(true);
  });
});
