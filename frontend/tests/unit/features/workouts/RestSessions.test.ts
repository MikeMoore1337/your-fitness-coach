import { beforeEach, describe, expect, it } from 'vitest';
import {
  acknowledgeRestPlan,
  activeRestJournalSession,
  beginMeasuredRest,
  loadRestJournal,
  markRestBackground,
  recoverRestAfterAbsence,
  restJournalStorageKey,
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
});
