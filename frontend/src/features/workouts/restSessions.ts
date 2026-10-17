import { api, ApiError } from '../../shared/api/client';
import { crossContextCoordinator } from '../../shared/browser/crossContextLock';
import { readStorage, removeStorage, writeStorage } from '../../shared/storage';
import { activeWorkoutRestKey } from './activeWorkoutQueue';

type RestAction = 'add30' | 'add60' | 'complete' | 'skip' | 'interrupt' | 'unknown';
type RestStatus = 'running' | 'completed' | 'skipped' | 'interrupted' | 'unknown';

interface RemoteRestSession {
  id: number;
  workout_id: number;
  source_set_id: number;
  started_at: string;
  ended_at: string | null;
  planned_seconds: number;
  adjusted_seconds: number;
  measured_seconds: number | null;
  status: RestStatus;
  source: string | null;
  quality: string;
  version: number;
}

interface QueuedRestAction {
  action: RestAction;
  mutation_id: string;
  occurred_at: string;
  ended_at?: string;
  corrected?: boolean;
  corrected_seconds?: number;
}

export interface LocalRestSession {
  source_set_id: number;
  started_at: string;
  planned_seconds: number;
  adjusted_seconds: number;
  deadline: number;
  status: RestStatus;
  ended_at?: string;
  source?: string;
  notified?: boolean;
  /** Timestamp of entering the background; survives WebView suspend/reload. */
  background_since?: number;
  /** Variant C: owner must recover or discard this measurement. */
  needs_review?: boolean;
  server_id?: number;
  server_version?: number;
  start_mutation_id: string;
  pending: QueuedRestAction[];
}

const REST_JOURNAL_VERSION = 1;
const CHANGE_EVENT = 'fit:rest-journal';
const MAX_JOURNAL = 256;
/** A return from background prompts for recovery only after 15 minutes past the plan. */
export const REST_ABSENCE_REVIEW_MS = 15 * 60 * 1000;

function makeId(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `rest-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function restJournalStorageKey(userId: number, workoutId: number): string {
  return `${activeWorkoutRestKey(userId, workoutId)}:measured:v${REST_JOURNAL_VERSION}`;
}

function validSession(row: LocalRestSession): boolean {
  return (
    Number.isInteger(row.source_set_id) &&
    row.source_set_id > 0 &&
    Number.isFinite(Date.parse(row.started_at)) &&
    Number.isInteger(row.planned_seconds) &&
    row.planned_seconds > 0 &&
    Number.isFinite(row.deadline) &&
    Array.isArray(row.pending) &&
    ['running', 'completed', 'skipped', 'interrupted', 'unknown'].includes(row.status)
  );
}

function actionStorageKey(userId: number, workoutId: number, mutationId: string): string {
  return `${restJournalStorageKey(userId, workoutId)}:op:${mutationId}`;
}

export function loadRestJournal(userId: number, workoutId: number): LocalRestSession[] {
  const journalKey = restJournalStorageKey(userId, workoutId);
  const records = readStorage<LocalRestSession[]>(journalKey, []);
  if (!Array.isArray(records)) return [];
  const valid = records.filter(validSession);
  // A separate immutable localStorage key per mutation prevents another tab's
  // stale journal snapshot from erasing an action that has not reached the API.
  try {
    const prefix = `${journalKey}:op:`;
    const keys = Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i)).filter(
      (key): key is string => Boolean(key?.startsWith(prefix)),
    );
    for (const key of keys) {
      const value = readStorage<{ source_set_id: number; operation: QueuedRestAction } | null>(
        key,
        null,
      );
      const row = valid.find((session) => session.source_set_id === value?.source_set_id);
      if (!row || !value?.operation?.mutation_id) continue;
      if (!row.pending.some((operation) => operation.mutation_id === value.operation.mutation_id)) {
        row.pending.push(value.operation);
      }
    }
    for (const row of valid) {
      row.pending.sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));
      // Rehydrate terminal state when a stale tab overwrote the primary snapshot.
      const lastTerminal = [...row.pending]
        .reverse()
        .find((operation) =>
          ['complete', 'skip', 'interrupt', 'unknown'].includes(operation.action),
        );
      if (row.status === 'running' && lastTerminal) {
        switch (lastTerminal.action) {
          case 'complete':
            row.status = 'completed';
            break;
          case 'skip':
            row.status = 'skipped';
            break;
          case 'interrupt':
            row.status = 'interrupted';
            break;
          case 'unknown':
            row.status = 'unknown';
            break;
          default:
            break;
        }
        row.ended_at = lastTerminal.ended_at ?? lastTerminal.occurred_at;
        if (lastTerminal.action === 'complete') {
          row.source = lastTerminal.corrected ? 'USER_CORRECTED' : 'USER_CONFIRMED';
        }
      }
    }
  } catch {
    // Restricted browsers without accessible localStorage retain in-memory flow.
  }
  return valid;
}

function saveRestJournal(userId: number, workoutId: number, records: LocalRestSession[]): void {
  // Unsynced records are never pruned to make room for newer measurements.
  const settled = records.filter((row) => row.server_id && !row.pending.length);
  const outstanding = records.filter((row) => !row.server_id || row.pending.length);
  const keep = [...settled.slice(-Math.max(0, MAX_JOURNAL - outstanding.length)), ...outstanding];
  writeStorage(restJournalStorageKey(userId, workoutId), keep);
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: { userId, workoutId } }));
}

export function activeRestJournalSession(
  userId: number,
  workoutId: number,
): LocalRestSession | null {
  return (
    loadRestJournal(userId, workoutId)
      .slice()
      .reverse()
      .find((row) => row.status === 'running') ?? null
  );
}

export function beginMeasuredRest(
  userId: number,
  workoutId: number,
  sourceSetId: number,
  plannedSeconds: number,
  acceptedAt = Date.now(),
): LocalRestSession | null {
  if (sourceSetId <= 0 || plannedSeconds <= 0) return null;
  const records = loadRestJournal(userId, workoutId);
  const found = records.find((row) => row.source_set_id === sourceSetId);
  if (found) return found.status === 'running' ? found : null;
  for (const row of records.filter((item) => item.status === 'running')) {
    row.status = 'interrupted';
    row.ended_at = new Date(acceptedAt).toISOString();
    row.pending.push({
      action: 'interrupt',
      occurred_at: row.ended_at,
      mutation_id: makeId(),
    });
  }
  const created: LocalRestSession = {
    source_set_id: sourceSetId,
    started_at: new Date(acceptedAt).toISOString(),
    planned_seconds: plannedSeconds,
    adjusted_seconds: plannedSeconds,
    deadline: acceptedAt + plannedSeconds * 1000,
    status: 'running',
    start_mutation_id: makeId(),
    pending: [],
  };
  records.push(created);
  saveRestJournal(userId, workoutId, records);
  return created;
}

export function updateMeasuredRest(
  userId: number,
  workoutId: number,
  sourceSetId: number,
  action: RestAction,
  at = Date.now(),
  correctedSeconds?: number,
): LocalRestSession | null {
  const records = loadRestJournal(userId, workoutId);
  const row = records.find((item) => item.source_set_id === sourceSetId);
  if (!row || row.status !== 'running') return null;
  // Variant C: unresolved background returns must be explicitly corrected or skipped.
  if (
    row.needs_review &&
    action !== 'skip' &&
    !(action === 'complete' && correctedSeconds !== undefined)
  )
    return null;
  if (
    correctedSeconds !== undefined &&
    (action !== 'complete' ||
      !Number.isInteger(correctedSeconds) ||
      correctedSeconds < 0 ||
      correctedSeconds > 86400)
  )
    return null;
  if (action === 'complete' && correctedSeconds === undefined && at < Date.parse(row.started_at))
    return null;
  const effectiveAction = action;
  const occurredAt = new Date(at).toISOString();
  const entry: QueuedRestAction = {
    action: effectiveAction,
    occurred_at: occurredAt,
    mutation_id: makeId(),
  };
  if (correctedSeconds !== undefined) {
    entry.corrected = true;
    entry.corrected_seconds = correctedSeconds;
  }
  if (effectiveAction === 'add30' || effectiveAction === 'add60') {
    row.deadline = Math.max(row.deadline, at) + (action === 'add30' ? 30 : 60) * 1000;
    row.adjusted_seconds = Math.max(
      1,
      Math.round((row.deadline - Date.parse(row.started_at)) / 1000),
    );
  } else {
    const terminalStatus: Record<Exclude<RestAction, 'add30' | 'add60'>, RestStatus> = {
      complete: 'completed',
      skip: 'skipped',
      interrupt: 'interrupted',
      unknown: 'unknown',
    };
    row.status = terminalStatus[effectiveAction];
    row.ended_at = occurredAt;
    row.needs_review = false;
    row.background_since = undefined;
    if (effectiveAction === 'complete') {
      entry.ended_at = occurredAt;
      row.source = correctedSeconds === undefined ? 'USER_CONFIRMED' : 'USER_CORRECTED';
    }
  }
  row.pending.push(entry);
  writeStorage(actionStorageKey(userId, workoutId, entry.mutation_id), {
    source_set_id: sourceSetId,
    operation: entry,
  });
  saveRestJournal(userId, workoutId, records);
  return row;
}

export function acknowledgeRestPlan(userId: number, workoutId: number, sourceSetId: number): void {
  const records = loadRestJournal(userId, workoutId);
  const row = records.find((item) => item.source_set_id === sourceSetId);
  if (!row || row.notified || row.status !== 'running') return;
  row.notified = true;
  saveRestJournal(userId, workoutId, records);
}

/** Record departure; do not convert time away into a fictitious measured interval. */
export function markRestBackground(userId: number, workoutId: number, at = Date.now()): void {
  const records = loadRestJournal(userId, workoutId);
  const row = records.find((item) => item.status === 'running');
  if (!row || row.needs_review || row.background_since !== undefined) return;
  row.background_since = at;
  saveRestJournal(userId, workoutId, records);
}

/** Variant C: prompt only if the user was away AND the plan is overdue by 15 min. */
export function recoverRestAfterAbsence(
  userId: number,
  workoutId: number,
  at = Date.now(),
): LocalRestSession | null {
  const records = loadRestJournal(userId, workoutId);
  const row = records.find((item) => item.status === 'running');
  if (!row) return null;
  if (row.background_since !== undefined) {
    if (
      at - row.background_since >= REST_ABSENCE_REVIEW_MS &&
      at - row.deadline >= REST_ABSENCE_REVIEW_MS
    ) {
      row.needs_review = true;
    }
    row.background_since = undefined;
    saveRestJournal(userId, workoutId, records);
  }
  return row;
}

/**
 * Merge a network acknowledgement into the newest durable journal. Never overwrite
 * an event appended by a concurrent set completion or a second browser tab.
 */
function acknowledgeRemote(
  userId: number,
  workoutId: number,
  sourceSetId: number,
  remote: RemoteRestSession,
  mutationId?: string,
): void {
  const records = loadRestJournal(userId, workoutId);
  const row = records.find((item) => item.source_set_id === sourceSetId);
  if (!row) return;
  row.server_id = remote.id;
  row.server_version = Math.max(row.server_version ?? 0, remote.version);
  if (mutationId) {
    row.pending = row.pending.filter((operation) => operation.mutation_id !== mutationId);
    removeStorage(actionStorageKey(userId, workoutId, mutationId));
  }
  saveRestJournal(userId, workoutId, records);
}

/** Sync accepted set journal before any rest actions; retain 409s for recovery. */
export async function syncRestJournal(userId: number, workoutId: number): Promise<void> {
  if (typeof navigator !== 'undefined' && !navigator.onLine) return;
  const key = restJournalStorageKey(userId, workoutId);
  await crossContextCoordinator.run(`rest-sync:${key}`, async () => {
    const sourceSetIds = loadRestJournal(userId, workoutId)
      .filter((row) => !row.server_id || row.pending.length)
      .map((row) => row.source_set_id);
    for (const sourceSetId of sourceSetIds) {
      const latest = () =>
        loadRestJournal(userId, workoutId).find((row) => row.source_set_id === sourceSetId);
      let row = latest();
      if (!row) continue;
      if (!row.server_id) {
        try {
          const remote = await api<RemoteRestSession>(
            `/api/v1/workouts/${workoutId}/rest-sessions`,
            {
              method: 'POST',
              body: {
                source_set_id: row.source_set_id,
                started_at: row.started_at,
                mutation_id: row.start_mutation_id,
              },
            },
          );
          acknowledgeRemote(userId, workoutId, sourceSetId, remote);
        } catch (error) {
          // Completion of the source set can still be in its separate offline queue.
          if (error instanceof ApiError && [409, 503].includes(error.status)) continue;
          throw error;
        }
      }
      row = latest();
      if (!row?.server_id) continue;
      for (const pendingId of row.pending.map((operation) => operation.mutation_id)) {
        // Refresh on every iteration: a foreground click can append while a POST awaits.
        row = latest();
        const operation = row?.pending.find((entry) => entry.mutation_id === pendingId);
        if (!row?.server_id || !operation) continue;
        try {
          const remote = await api<RemoteRestSession>(
            `/api/v1/workouts/rest-sessions/${row.server_id}/actions`,
            {
              method: 'POST',
              body: { ...operation, expected_version: row.server_version },
            },
          );
          acknowledgeRemote(userId, workoutId, sourceSetId, remote, operation.mutation_id);
        } catch (error) {
          // Conflicts require explicit reconciliation, not data loss or silent retries.
          if (error instanceof ApiError && [409, 503].includes(error.status)) break;
          throw error;
        }
      }
    }
  });
}

export function listenToRestJournal(callback: () => void): () => void {
  const handleLocal = () => callback();
  const handleStorage = (event: StorageEvent) => {
    if (event.key?.includes(':measured:v1')) callback();
  };
  window.addEventListener(CHANGE_EVENT, handleLocal);
  window.addEventListener('storage', handleStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, handleLocal);
    window.removeEventListener('storage', handleStorage);
  };
}
