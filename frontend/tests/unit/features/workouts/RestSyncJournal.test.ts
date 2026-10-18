import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockApi = vi.hoisted(() => vi.fn());
const MockApiError = vi.hoisted(
  () =>
    class MockApiError extends Error {
      constructor(public status: number) {
        super('Mock API error');
      }
    },
);

vi.mock('../../../../src/shared/api/client', () => ({
  api: mockApi,
  ApiError: MockApiError,
}));
vi.mock('../../../../src/shared/browser/crossContextLock', () => ({
  crossContextCoordinator: {
    run: (_name: string, task: () => Promise<void>) => task(),
  },
}));

import {
  beginMeasuredRest,
  loadRestJournal,
  restJournalStorageKey,
  syncRestJournal,
  updateMeasuredRest,
} from '../../../../src/features/workouts/restSessions';

describe('rest journal concurrent mutation preservation #960', () => {
  beforeEach(() => {
    localStorage.clear();
    mockApi.mockReset();
  });

  it('does not overwrite a new local event while an earlier REST POST is awaiting', async () => {
    const start = new Date('2026-10-17T08:00:00Z').getTime();
    beginMeasuredRest(31, 44, 55, 90, start);
    const startMutationId = loadRestJournal(31, 44)[0]!.start_mutation_id;
    updateMeasuredRest(31, 44, 55, 'add30', start + 10_000);
    mockApi.mockResolvedValueOnce({
      id: 66,
      workout_id: 44,
      source_set_id: 55,
      version: 1,
      status: 'running',
    });
    let acceptAction: ((value: unknown) => void) | undefined;
    mockApi.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          acceptAction = resolve;
        }),
    );
    const sync = syncRestJournal(31, 44);
    await vi.waitFor(() => expect(mockApi).toHaveBeenCalledTimes(2));
    updateMeasuredRest(31, 44, 55, 'skip', start + 15_000);
    acceptAction?.({ id: 66, source_set_id: 55, workout_id: 44, version: 2, status: 'running' });
    await sync;
    const journal = loadRestJournal(31, 44);
    expect(journal[0]?.server_id).toBe(66);
    expect(journal[0]?.pending.map((item) => item.action)).toContain('skip');
    expect(journal[0]?.pending.map((item) => item.action)).not.toContain('add30');
    expect(
      localStorage.getItem(`${restJournalStorageKey(31, 44)}:op:${startMutationId}`),
    ).toBeNull();
  });

  it('retains a terminal local action after a server conflict for explicit reconciliation', async () => {
    const start = new Date('2026-10-17T08:00:00Z').getTime();
    beginMeasuredRest(31, 44, 56, 90, start);
    updateMeasuredRest(31, 44, 56, 'complete', start + 30_000);
    mockApi.mockResolvedValueOnce({
      id: 67,
      workout_id: 44,
      source_set_id: 56,
      version: 1,
      status: 'running',
    });
    mockApi.mockRejectedValueOnce(new MockApiError(409));

    await syncRestJournal(31, 44);

    const row = loadRestJournal(31, 44)[0];
    expect(row).toMatchObject({ server_id: 67, status: 'completed' });
    expect(row?.pending).toHaveLength(1);
    expect(row?.pending[0]?.action).toBe('complete');
  });
});
