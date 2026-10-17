import { beforeEach, describe, expect, it } from 'vitest';
import {
  acknowledgeRestPlan,
  activeRestJournalSession,
  beginMeasuredRest,
  loadRestJournal,
  restHardCutoffMs,
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

  it('never marks a forgotten stop after the hard cutoff as measured', () => {
    const startedAt = 2_500_000;
    beginMeasuredRest(11, 56, 1005, 90, startedAt);
    const elapsed = restHardCutoffMs(90) + 1000;
    const recovered = updateMeasuredRest(11, 56, 1005, 'complete', startedAt + elapsed);
    expect(recovered?.status).toBe('unknown');
    expect(recovered?.source).toBeUndefined();
    expect(recovered?.pending.at(-1)?.action).toBe('unknown');
  });

  it('does not invent a duration for skipped or unknown intervals', () => {
    beginMeasuredRest(11, 56, 1003, 60, 200_000);
    expect(updateMeasuredRest(11, 56, 1003, 'skip')?.status).toBe('skipped');
    expect(activeRestJournalSession(11, 56)).toBeNull();
    beginMeasuredRest(11, 56, 1004, 60, 300_000);
    expect(updateMeasuredRest(11, 56, 1004, 'unknown')?.status).toBe('unknown');
    expect(restHardCutoffMs(90)).toBe(12 * 3600 * 1000);
    expect(restHardCutoffMs(24 * 3600)).toBe(24 * 3600 * 1000);
  });
});
