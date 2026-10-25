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
  restartMeasuredRest,
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
    const startRecovery = JSON.parse(
      localStorage.getItem(`${restJournalStorageKey(31, 44)}:op:${startMutationId}`) ?? '{}',
    );
    expect(startRecovery.start).toMatchObject({ server_id: 66, server_version: 2 });
  });

  it.each([
    ['complete', 'completed'],
    ['skip', 'skipped'],
    ['interrupt', 'interrupted'],
  ] as const)(
    'recovers an ACKed start before reconnecting %s after a stale snapshot',
    async (action, status) => {
      const start = new Date('2026-10-18T08:00:00Z').getTime();
      const key = restJournalStorageKey(31, 44);
      const staleSnapshot = localStorage.getItem(key) ?? '[]';
      beginMeasuredRest(31, 44, 57, 90, start);

      mockApi.mockResolvedValueOnce({
        id: 68,
        workout_id: 44,
        source_set_id: 57,
        started_at: new Date(start).toISOString(),
        planned_seconds: 90,
        adjusted_seconds: 90,
        version: 1,
        status: 'running',
      });
      await syncRestJournal(31, 44);
      const startMutationId = loadRestJournal(31, 44)[0]?.start_mutation_id;
      expect(startMutationId).toEqual(expect.any(String));
      expect(localStorage.getItem(`${key}:op:${startMutationId}`)).not.toBeNull();

      const stopped = updateMeasuredRest(31, 44, 57, action, start + 30_000);
      const mutationId = stopped?.pending[0]?.mutation_id;
      expect(mutationId).toEqual(expect.any(String));
      localStorage.setItem(key, staleSnapshot);

      const restored = loadRestJournal(31, 44)[0];
      expect(restored).toMatchObject({ source_set_id: 57, server_id: 68, server_version: 1 });
      expect(restored?.pending).toMatchObject([{ action, mutation_id: mutationId }]);
      expect(restored?.status).toBe(status);

      mockApi.mockResolvedValueOnce({
        id: 68,
        workout_id: 44,
        source_set_id: 57,
        started_at: new Date(start).toISOString(),
        planned_seconds: 90,
        adjusted_seconds: 90,
        version: 2,
        status,
      });
      await syncRestJournal(31, 44);

      expect(mockApi).toHaveBeenCalledTimes(2);
      expect(mockApi.mock.calls[1]?.[1]?.body?.mutation_id).toBe(mutationId);
      expect(loadRestJournal(31, 44)[0]?.pending).toHaveLength(0);
      expect(localStorage.getItem(`${key}:op:${startMutationId}`)).toBeNull();

      await syncRestJournal(31, 44);
      expect(mockApi).toHaveBeenCalledTimes(2);
    },
  );

  it('replays the same terminal mutation after the server saved it but the ACK was lost', async () => {
    const start = new Date('2026-10-18T08:00:00Z').getTime();
    const key = restJournalStorageKey(31, 44);
    const staleSnapshot = localStorage.getItem(key) ?? '[]';
    beginMeasuredRest(31, 44, 58, 90, start);
    mockApi.mockResolvedValueOnce({
      id: 69,
      workout_id: 44,
      source_set_id: 58,
      started_at: new Date(start).toISOString(),
      planned_seconds: 90,
      adjusted_seconds: 90,
      version: 1,
      status: 'running',
    });
    await syncRestJournal(31, 44);

    const stopped = updateMeasuredRest(31, 44, 58, 'complete', start + 30_000);
    const mutationId = stopped?.pending[0]?.mutation_id;
    localStorage.setItem(key, staleSnapshot);
    mockApi.mockRejectedValueOnce(new Error('connection lost after server commit'));

    await expect(syncRestJournal(31, 44)).rejects.toThrow('connection lost after server commit');
    expect(loadRestJournal(31, 44)[0]?.pending).toMatchObject([{ mutation_id: mutationId }]);

    mockApi.mockResolvedValueOnce({
      id: 69,
      workout_id: 44,
      source_set_id: 58,
      started_at: new Date(start).toISOString(),
      planned_seconds: 90,
      adjusted_seconds: 90,
      version: 2,
      status: 'completed',
    });
    await syncRestJournal(31, 44);

    expect(mockApi).toHaveBeenCalledTimes(3);
    expect(mockApi.mock.calls[2]?.[1]?.body?.mutation_id).toBe(mutationId);
    expect(loadRestJournal(31, 44)[0]?.pending).toHaveLength(0);
    await syncRestJournal(31, 44);
    expect(mockApi).toHaveBeenCalledTimes(3);
  });

  it('merges a durable server version before ordering multiple pending actions', async () => {
    const start = new Date('2026-10-18T08:00:00Z').getTime();
    const key = restJournalStorageKey(31, 44);
    beginMeasuredRest(31, 44, 59, 90, start);
    mockApi.mockResolvedValueOnce({
      id: 70,
      workout_id: 44,
      source_set_id: 59,
      started_at: new Date(start).toISOString(),
      planned_seconds: 90,
      adjusted_seconds: 90,
      version: 1,
      status: 'running',
    });
    await syncRestJournal(31, 44);
    const staleServerSnapshot = localStorage.getItem(key);

    updateMeasuredRest(31, 44, 59, 'add30', start + 10_000);
    mockApi.mockResolvedValueOnce({
      id: 70,
      workout_id: 44,
      source_set_id: 59,
      started_at: new Date(start).toISOString(),
      planned_seconds: 90,
      adjusted_seconds: 120,
      version: 2,
      status: 'running',
    });
    await syncRestJournal(31, 44);

    updateMeasuredRest(31, 44, 59, 'add60', start + 20_000);
    const completed = updateMeasuredRest(31, 44, 59, 'complete', start + 30_000);
    const terminalMutationId = completed?.pending.at(-1)?.mutation_id;
    localStorage.setItem(key, staleServerSnapshot!);

    const restored = loadRestJournal(31, 44)[0];
    expect(restored).toMatchObject({ server_id: 70, server_version: 2, adjusted_seconds: 120 });
    expect(restored?.pending.map((item) => item.action)).toEqual(['add60', 'complete']);

    mockApi.mockResolvedValueOnce({
      id: 70,
      workout_id: 44,
      source_set_id: 59,
      started_at: new Date(start).toISOString(),
      planned_seconds: 90,
      adjusted_seconds: 180,
      version: 3,
      status: 'running',
    });
    mockApi.mockResolvedValueOnce({
      id: 70,
      workout_id: 44,
      source_set_id: 59,
      started_at: new Date(start).toISOString(),
      planned_seconds: 90,
      adjusted_seconds: 180,
      version: 4,
      status: 'completed',
    });
    await syncRestJournal(31, 44);

    expect(mockApi.mock.calls[2]?.[1]?.body).toMatchObject({
      mutation_id: restored?.pending[0]?.mutation_id,
      expected_version: 2,
    });
    expect(mockApi.mock.calls[3]?.[1]?.body).toMatchObject({
      mutation_id: terminalMutationId,
      expected_version: 3,
    });
    expect(loadRestJournal(31, 44)[0]?.pending).toHaveLength(0);
    expect(
      localStorage.getItem(`${key}:op:${loadRestJournal(31, 44)[0]?.start_mutation_id}`),
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

    const blocked: number[] = [];
    await syncRestJournal(31, 44, (status) => blocked.push(status));

    const row = loadRestJournal(31, 44)[0];
    expect(blocked).toEqual([409]);
    expect(row).toMatchObject({ server_id: 67, status: 'completed' });
    expect(row?.pending).toHaveLength(1);
    expect(row?.pending[0]?.action).toBe('complete');
  });
  it('persists the predecessor action before an explicit restart on the same set', async () => {
    const start = new Date('2026-10-18T08:00:00Z').getTime();
    const initial = beginMeasuredRest(31, 44, 72, 90, start)!;
    updateMeasuredRest(31, 44, 72, 'complete', start + 25_000);
    const repeat = restartMeasuredRest(31, 44, initial.start_mutation_id, start + 30_000)!;
    expect(loadRestJournal(31, 44)).toHaveLength(2);

    mockApi.mockImplementation((url: string) => {
      if (url === '/api/v1/workouts/44/rest-sessions') {
        return Promise.resolve({
          id: 110,
          workout_id: 44,
          source_set_id: 72,
          started_at: initial.started_at,
          adjusted_seconds: 90,
          version: 1,
          status: 'running',
        });
      }
      if (url === '/api/v1/workouts/rest-sessions/110/actions') {
        return Promise.resolve({
          id: 110,
          workout_id: 44,
          source_set_id: 72,
          started_at: initial.started_at,
          adjusted_seconds: 90,
          version: 2,
          status: 'completed',
        });
      }
      if (url === '/api/v1/workouts/rest-sessions/110/restart') {
        return Promise.resolve({
          id: 111,
          workout_id: 44,
          source_set_id: 72,
          started_at: repeat.started_at,
          start_mutation_id: repeat.start_mutation_id,
          adjusted_seconds: 90,
          version: 1,
          status: 'running',
        });
      }
      throw new Error('Unexpected rest API request: ' + url);
    });

    await syncRestJournal(31, 44);
    expect(mockApi.mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/workouts/44/rest-sessions',
      '/api/v1/workouts/rest-sessions/110/actions',
      '/api/v1/workouts/rest-sessions/110/restart',
    ]);
    expect(mockApi.mock.calls[2]?.[1]?.body).toMatchObject({
      started_at: repeat.started_at,
      mutation_id: repeat.start_mutation_id,
    });
    const saved = loadRestJournal(31, 44);
    expect(saved[0]).toMatchObject({ server_id: 110, status: 'completed', pending: [] });
    expect(saved[1]).toMatchObject({
      server_id: 111,
      status: 'running',
      start_mutation_id: repeat.start_mutation_id,
    });

    updateMeasuredRest(31, 44, 72, 'skip', start + 35_000);
    mockApi.mockImplementationOnce(() =>
      Promise.resolve({
        id: 111,
        workout_id: 44,
        source_set_id: 72,
        started_at: repeat.started_at,
        version: 2,
        status: 'skipped',
      }),
    );
    await syncRestJournal(31, 44);
    expect(loadRestJournal(31, 44)[0]).toMatchObject({ server_id: 110, status: 'completed' });
    expect(loadRestJournal(31, 44)[1]).toMatchObject({ server_id: 111, status: 'skipped' });
  });

  it('does not accept a stale restart ACK for the predecessor interval', async () => {
    const start = new Date('2026-10-18T08:00:00Z').getTime();
    const first = beginMeasuredRest(31, 44, 73, 90, start)!;
    updateMeasuredRest(31, 44, 73, 'skip', start + 15_000);
    const repeat = restartMeasuredRest(31, 44, first.start_mutation_id, start + 20_000)!;

    mockApi.mockResolvedValueOnce({
      id: 200,
      workout_id: 44,
      source_set_id: 73,
      started_at: first.started_at,
      adjusted_seconds: 90,
      version: 1,
    });
    mockApi.mockResolvedValueOnce({
      id: 200,
      workout_id: 44,
      source_set_id: 73,
      started_at: first.started_at,
      adjusted_seconds: 90,
      version: 2,
    });
    mockApi.mockResolvedValueOnce({
      id: 200,
      workout_id: 44,
      source_set_id: 73,
      started_at: repeat.started_at,
      adjusted_seconds: 90,
      version: 1,
    });
    await expect(syncRestJournal(31, 44)).rejects.toThrow('rest_restart_reused_predecessor');
    expect(loadRestJournal(31, 44)[1]?.start_mutation_id).toBe(repeat.start_mutation_id);
    expect(loadRestJournal(31, 44)[1]).not.toHaveProperty('server_id');
  });
});
