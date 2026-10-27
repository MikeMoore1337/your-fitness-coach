import { beforeEach, describe, expect, it } from 'vitest';
import {
  acknowledgeRestPlan,
  activeRestJournalSession,
  beginMeasuredRest,
  loadRestJournal,
  markRestBackground,
  recoverRestAfterAbsence,
  restJournalStorageKey,
  restartMeasuredRest,
  REST_ABSENCE_REVIEW_MS,
  updateMeasuredRest,
} from '../../../../src/features/workouts/restSessions';

describe('measured rest journal #960', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('creates at most one rest interval per accepted set', () => {
    const initial = beginMeasuredRest(11, 56, 987, 90, 100_000);
    expect(initial?.source_set_id).toBe(987);
    expect(initial?.deadline).toBe(190_000);
    const replay = beginMeasuredRest(11, 56, 987, 90, 102_000);
    expect(replay?.start_mutation_id).toEqual(initial?.start_mutation_id);
    expect(loadRestJournal(11, 56)).toHaveLength(1);
    expect(loadRestJournal(12, 56)).toHaveLength(0);
  });

  it('rehydrates a new start and its interruption after a stale journal snapshot', () => {
    const start = 150_000;
    beginMeasuredRest(11, 56, 1009, 90, start);
    const key = restJournalStorageKey(11, 56);
    const staleSnapshot = localStorage.getItem(key);
    beginMeasuredRest(11, 56, 1010, 90, start + 1000);

    localStorage.setItem(key, staleSnapshot!);
    const restored = loadRestJournal(11, 56);

    expect(restored.map((row) => row.source_set_id)).toEqual([1009, 1010]);
    expect(restored[0]).toMatchObject({ status: 'interrupted' });
    expect(restored[0]?.pending.map((entry) => entry.action)).toEqual(['interrupt']);
    expect(restored[1]).toMatchObject({ status: 'running', start_mutation_id: expect.any(String) });
  });

  it('only extends target, never rewrites elapsed start', () => {
    const base = 1_900_000;
    beginMeasuredRest(11, 56, 1001, 90, base);
    const changed = updateMeasuredRest(11, 56, 1001, 'add60', base + 100_000);
    expect(changed?.deadline).toBe(base + 160_000);
    expect(changed?.started_at).toBe(new Date(base).toISOString());
    expect(changed?.adjusted_seconds).toBe(160);
    acknowledgeRestPlan(11, 56, 1001);
    expect(activeRestJournalSession(11, 56)?.notified).toBe(true);
    expect(loadRestJournal(11, 56)[0]?.pending.map((entry) => entry.action)).toEqual(['add60']);
  });

  it('completes only on explicit stop and survives reload', () => {
    const base = 2_000_000;
    beginMeasuredRest(11, 56, 1002, 90, base);
    const completed = updateMeasuredRest(11, 56, 1002, 'complete', base + 152_000);
    expect(completed?.status).toBe('completed');
    expect(completed?.source).toBe('USER_CONFIRMED');
    expect(completed?.ended_at).toBe(new Date(base + 152_000).toISOString());
    expect(activeRestJournalSession(11, 56)).toBeNull();
    expect(updateMeasuredRest(11, 56, 1002, 'complete', base + 200_000)).toBeNull();
    expect(loadRestJournal(11, 56)[0]?.pending).toHaveLength(1);
  });

  it('recovers terminal events after a second tab overwrites the shared journal', () => {
    const startedAt = 2_250_000;
    beginMeasuredRest(11, 56, 1008, 90, startedAt);
    const key = restJournalStorageKey(11, 56);
    const staleSnapshot = localStorage.getItem(key);
    const stopped = updateMeasuredRest(11, 56, 1008, 'complete', startedAt + 120_000);
    expect(stopped?.status).toBe('completed');
    expect(stopped?.pending).toHaveLength(1);
    // Emulate another tab saving an older copy after the stop was journaled.
    expect(staleSnapshot).not.toBeNull();
    localStorage.setItem(key, staleSnapshot!);
    const recovered = loadRestJournal(11, 56)[0];
    expect(recovered?.pending[0]?.action).toBe('complete');
    expect(recovered?.status).toBe('completed');
    expect(recovered?.source).toBe('USER_CONFIRMED');
    expect(activeRestJournalSession(11, 56)).toBeNull();
  });

  it('does not prompt while actively using the workout, even if rest is long', () => {
    const startedAt = 2_500_000;
    beginMeasuredRest(11, 56, 1005, 90, startedAt);
    const returned = recoverRestAfterAbsence(11, 56, startedAt + REST_ABSENCE_REVIEW_MS * 5);
    expect(returned?.needs_review).toBeUndefined();
    const confirmed = updateMeasuredRest(
      11,
      56,
      1005,
      'complete',
      startedAt + REST_ABSENCE_REVIEW_MS * 5,
    );
    expect(confirmed?.status).toBe('completed');
    expect(confirmed?.source).toBe('USER_CONFIRMED');
  });

  it('offers correction only after fifteen minutes away beyond the plan', () => {
    const start = 3_000_000;
    beginMeasuredRest(11, 56, 1006, 90, start);
    markRestBackground(11, 56, start + 90_000);
    const early = recoverRestAfterAbsence(11, 56, start + 90_000 + REST_ABSENCE_REVIEW_MS - 1000);
    expect(early?.needs_review).toBeUndefined();
    markRestBackground(11, 56, start + 90_000);
    const overdue = recoverRestAfterAbsence(11, 56, start + 90_000 + REST_ABSENCE_REVIEW_MS + 1);
    expect(overdue?.needs_review).toBe(true);
    expect(loadRestJournal(11, 56)[0]?.needs_review).toBe(true);
    expect(updateMeasuredRest(11, 56, 1006, 'complete')).toBeNull();
    expect(updateMeasuredRest(11, 56, 1006, 'add60')).toBeNull();
    const corrected = updateMeasuredRest(11, 56, 1006, 'complete', start + 25 * 60_000, 150);
    expect(corrected?.status).toBe('completed');
    expect(corrected?.source).toBe('USER_CORRECTED');
    expect(corrected?.pending.at(-1)).toMatchObject({
      action: 'complete',
      corrected: true,
      corrected_seconds: 150,
    });
  });

  it('uses the inclusive Policy C boundary and rejects a pre-start correction timestamp', () => {
    const start = 3_500_000;
    beginMeasuredRest(11, 56, 1011, 90, start);
    markRestBackground(11, 56, start + 90_000);

    const boundary = recoverRestAfterAbsence(11, 56, start + 90_000 + REST_ABSENCE_REVIEW_MS);
    expect(boundary?.needs_review).toBe(true);

    beginMeasuredRest(11, 56, 1012, 90, start + 1000);
    expect(updateMeasuredRest(11, 56, 1012, 'complete', start, 150)).toBeNull();
    expect(loadRestJournal(11, 56).find((row) => row.source_set_id === 1012)?.status).toBe(
      'running',
    );
  });

  it('allows discarding untrusted rest without inventing a measurement', () => {
    const start = 4_000_000;
    beginMeasuredRest(11, 56, 1007, 60, start);
    markRestBackground(11, 56, start + 60_000);
    expect(
      recoverRestAfterAbsence(11, 56, start + 60_000 + REST_ABSENCE_REVIEW_MS + 1)?.needs_review,
    ).toBe(true);
    const skipped = updateMeasuredRest(11, 56, 1007, 'skip');
    expect(skipped?.status).toBe('skipped');
    expect(skipped?.source).toBeUndefined();
  });

  it('does not invent a duration for skipped or unknown intervals', () => {
    beginMeasuredRest(11, 56, 1003, 60, 200_000);
    expect(updateMeasuredRest(11, 56, 1003, 'skip')?.status).toBe('skipped');
    expect(activeRestJournalSession(11, 56)).toBeNull();
    beginMeasuredRest(11, 56, 1004, 60, 300_000);
    expect(updateMeasuredRest(11, 56, 1004, 'unknown')?.status).toBe('unknown');
    expect(REST_ABSENCE_REVIEW_MS).toBe(15 * 60 * 1000);
  });
  it('creates a distinct measured interval after stop without rewriting its predecessor', () => {
    const at = 8_000_000;
    const initial = beginMeasuredRest(11, 56, 987, 90, at)!;
    const previous = updateMeasuredRest(11, 56, 987, 'complete', at + 42_000)!;
    const restart = restartMeasuredRest(11, 56, initial.start_mutation_id, at + 60_000)!;

    expect(restart).toMatchObject({
      source_set_id: 987,
      restart_of_start_mutation_id: initial.start_mutation_id,
      status: 'running',
      deadline: at + 150_000,
    });
    expect(restart.start_mutation_id).not.toBe(initial.start_mutation_id);
    expect(loadRestJournal(11, 56)).toHaveLength(2);
    expect(loadRestJournal(11, 56)[0]).toMatchObject({
      status: 'completed',
      ended_at: previous.ended_at,
      source: 'USER_CONFIRMED',
    });
    expect(
      restartMeasuredRest(11, 56, initial.start_mutation_id, at + 61_000)?.start_mutation_id,
    ).toBe(restart.start_mutation_id);
    expect(updateMeasuredRest(11, 56, 987, 'complete', at + 78_000)?.start_mutation_id).toBe(
      restart.start_mutation_id,
    );
    expect(loadRestJournal(11, 56)[0]?.ended_at).toBe(previous.ended_at);
  });

  it('restores two intervals and their actions after a stale shared journal write', () => {
    const start = 9_000_000;
    const initial = beginMeasuredRest(11, 56, 988, 90, start)!;
    updateMeasuredRest(11, 56, 988, 'skip', start + 20_000);
    const oldJournal = localStorage.getItem(restJournalStorageKey(11, 56))!;
    const repeat = restartMeasuredRest(11, 56, initial.start_mutation_id, start + 30_000)!;
    updateMeasuredRest(11, 56, 988, 'add30', start + 31_000);
    localStorage.setItem(restJournalStorageKey(11, 56), oldJournal);

    const restored = loadRestJournal(11, 56);
    expect(restored).toHaveLength(2);
    expect(restored[0]).toMatchObject({ status: 'skipped' });
    expect(restored[1]).toMatchObject({
      start_mutation_id: repeat.start_mutation_id,
      restart_of_start_mutation_id: initial.start_mutation_id,
      status: 'running',
    });
    expect(restored[1]?.pending).toMatchObject([{ action: 'add30' }]);
    expect(restored[0]?.pending.some((item) => item.action === 'add30')).toBe(false);
  });

  it('keeps an interrupted manual successor associated with the correct interval after stale writes', () => {
    const start = 12_000_000;
    const initial = beginMeasuredRest(11, 56, 990, 90, start)!;
    updateMeasuredRest(11, 56, 990, 'complete', start + 15_000);
    const staleJournal = localStorage.getItem(restJournalStorageKey(11, 56))!;
    const repeat = restartMeasuredRest(11, 56, initial.start_mutation_id, start + 20_000)!;
    beginMeasuredRest(11, 56, 991, 90, start + 45_000);
    localStorage.setItem(restJournalStorageKey(11, 56), staleJournal);

    const recovered = loadRestJournal(11, 56);
    expect(recovered).toHaveLength(3);
    expect(
      recovered.find((row) => row.start_mutation_id === initial.start_mutation_id),
    ).toMatchObject({
      status: 'completed',
      pending: expect.arrayContaining([expect.objectContaining({ action: 'complete' })]),
    });
    expect(
      recovered.find((row) => row.start_mutation_id === repeat.start_mutation_id),
    ).toMatchObject({
      status: 'interrupted',
      pending: expect.arrayContaining([expect.objectContaining({ action: 'interrupt' })]),
    });
    expect(recovered.find((row) => row.source_set_id === 991)).toMatchObject({ status: 'running' });
  });

  it('does not create a repeat for an active, unknown or interrupted predecessor', () => {
    const start = 10_000_000;
    const initial = beginMeasuredRest(11, 56, 989, 90, start)!;
    expect(restartMeasuredRest(11, 56, initial.start_mutation_id)).toBeNull();
    updateMeasuredRest(11, 56, 989, 'unknown', start + 10_000);
    expect(restartMeasuredRest(11, 56, initial.start_mutation_id)).toBeNull();
    expect(loadRestJournal(11, 56)).toHaveLength(1);
  });
});
