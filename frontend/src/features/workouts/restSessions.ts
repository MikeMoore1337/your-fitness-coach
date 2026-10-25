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
  start_mutation_id?: string | null;
}

interface QueuedRestAction {
  action: RestAction;
  mutation_id: string;
  occurred_at: string;
  ended_at?: string;
  corrected?: boolean;
  corrected_seconds?: number;
}

interface RestStartRecovery {
  source_set_id: number;
  started_at: string;
  planned_seconds: number;
  adjusted_seconds: number;
  deadline: number;
  start_mutation_id: string;
  restart_of_start_mutation_id?: string;
  server_id?: number;
  server_version?: number;
}

interface StoredRestRecovery {
  source_set_id: number;
  session_start_mutation_id?: string;
  start?: RestStartRecovery;
  operation?: QueuedRestAction;
}

export interface LocalRestSession {
  source_set_id: number;
  started_at: string;
  planned_seconds: number;
  adjusted_seconds: number;
  deadline: number;
  status: RestStatus;
  ended_at?: string;
  measured_seconds?: number | null;
  source?: string;
  notified?: boolean;
  /** Timestamp of entering the background; survives WebView suspend/reload. */
  background_since?: number;
  /** Variant C: owner must recover or discard this measurement. */
  needs_review?: boolean;
  server_id?: number;
  server_version?: number;
  start_mutation_id: string;
  restart_of_start_mutation_id?: string;
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

function validStartRecovery(value: unknown): value is RestStartRecovery {
  if (!value || typeof value !== 'object') return false;
  const start = value as Partial<RestStartRecovery>;
  return Boolean(
    typeof start.source_set_id === 'number' &&
    Number.isInteger(start.source_set_id) &&
    start.source_set_id > 0 &&
    typeof start.started_at === 'string' &&
    Number.isFinite(Date.parse(start.started_at)) &&
    typeof start.planned_seconds === 'number' &&
    Number.isInteger(start.planned_seconds) &&
    start.planned_seconds > 0 &&
    typeof start.adjusted_seconds === 'number' &&
    Number.isInteger(start.adjusted_seconds) &&
    start.adjusted_seconds > 0 &&
    Number.isFinite(start.deadline) &&
    typeof start.start_mutation_id === 'string' &&
    start.start_mutation_id.length > 0 &&
    (start.server_id === undefined || (Number.isInteger(start.server_id) && start.server_id > 0)) &&
    (start.server_version === undefined ||
      (Number.isInteger(start.server_version) && start.server_version >= 0)) &&
    (start.restart_of_start_mutation_id === undefined ||
      (typeof start.restart_of_start_mutation_id === 'string' &&
        start.restart_of_start_mutation_id.length > 0)),
  );
}

function actionStorageKey(userId: number, workoutId: number, mutationId: string): string {
  return `${restJournalStorageKey(userId, workoutId)}:op:${mutationId}`;
}

function terminalStatusForAction(action: RestAction): RestStatus | undefined {
  switch (action) {
    case 'complete':
      return 'completed';
    case 'skip':
      return 'skipped';
    case 'interrupt':
      return 'interrupted';
    case 'unknown':
      return 'unknown';
    default:
      return undefined;
  }
}

function acknowledgedStartRecovery(
  start: RestStartRecovery,
  remote: RemoteRestSession,
): RestStartRecovery {
  const adjustedSeconds =
    Number.isInteger(remote.adjusted_seconds) && remote.adjusted_seconds > 0
      ? remote.adjusted_seconds
      : start.adjusted_seconds;
  const plannedSeconds =
    Number.isInteger(remote.planned_seconds) && remote.planned_seconds > 0
      ? remote.planned_seconds
      : start.planned_seconds;
  const startedAt = Date.parse(start.started_at);
  return {
    ...start,
    planned_seconds: plannedSeconds,
    adjusted_seconds: adjustedSeconds,
    deadline: Number.isFinite(startedAt) ? startedAt + adjustedSeconds * 1000 : start.deadline,
    server_id: remote.id,
    server_version: Math.max(start.server_version ?? 0, remote.version),
  };
}

function updateStartRecovery(
  userId: number,
  workoutId: number,
  startMutationId: string,
  remote: RemoteRestSession,
  remove: boolean,
): void {
  // Keep the start snapshot until a terminal action is acknowledged; the primary journal may be stale.
  const key = actionStorageKey(userId, workoutId, startMutationId);
  const recovery = readStorage<StoredRestRecovery | null>(key, null);
  if (!recovery?.start) return;
  if (remove) {
    removeStorage(key);
    return;
  }
  writeStorage(key, {
    ...recovery,
    start: acknowledgedStartRecovery(recovery.start, remote),
  });
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
    const recoveries = keys.map((key) => readStorage<StoredRestRecovery | null>(key, null));
    for (const value of recoveries) {
      const start = value?.start;
      if (!validStartRecovery(start)) continue;
      const existing = valid.find((session) => session.start_mutation_id === start.start_mutation_id);
      if (existing) {
        if (existing.server_id === undefined && start.server_id !== undefined) {
          existing.server_id = start.server_id;
        }
        if (start.server_version !== undefined) {
          existing.server_version = Math.max(existing.server_version ?? 0, start.server_version);
        }
        existing.adjusted_seconds = Math.max(existing.adjusted_seconds, start.adjusted_seconds);
        existing.deadline = Math.max(existing.deadline, start.deadline);
        continue;
      }
      valid.push({
        ...start,
        status: 'running',
        pending: [],
      });
    }
    for (const value of recoveries) {
      const operation = value?.operation;
      const row = valid.find((session) =>
        value?.session_start_mutation_id
          ? session.start_mutation_id === value.session_start_mutation_id
          : session.source_set_id === value?.source_set_id && !session.restart_of_start_mutation_id,
      );
      if (!row || !operation?.mutation_id) continue;
      if (!row.pending.some((item) => item.mutation_id === operation.mutation_id)) {
        row.pending.push(operation);
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
          row.measured_seconds = lastTerminal.corrected
            ? (lastTerminal.corrected_seconds ?? null)
            : Math.max(0, Math.floor((Date.parse(row.ended_at ?? row.started_at) - Date.parse(row.started_at)) / 1000));
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
  const found = records.find(
    (row) => row.source_set_id === sourceSetId && !row.restart_of_start_mutation_id,
  );
  if (found) return found.status === 'running' ? found : null;
  for (const row of records.filter((item) => item.status === 'running')) {
    row.status = 'interrupted';
    row.ended_at = new Date(acceptedAt).toISOString();
    const operation = {
      action: 'interrupt',
      occurred_at: row.ended_at,
      mutation_id: makeId(),
    } satisfies QueuedRestAction;
    row.pending.push(operation);
    writeStorage(actionStorageKey(userId, workoutId, operation.mutation_id), {
      source_set_id: row.source_set_id,
      operation,
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
  writeStorage(actionStorageKey(userId, workoutId, created.start_mutation_id), {
    source_set_id: sourceSetId,
    start: {
      source_set_id: created.source_set_id,
      started_at: created.started_at,
      planned_seconds: created.planned_seconds,
      adjusted_seconds: created.adjusted_seconds,
      deadline: created.deadline,
      start_mutation_id: created.start_mutation_id,
    },
  });
  saveRestJournal(userId, workoutId, records);
  return created;
}

/** New explicit interval after a finalised measured/omitted rest. Never re-open history. */
export function restartMeasuredRest(
  userId: number,
  workoutId: number,
  predecessorStartMutationId: string,
  at = Date.now(),
): LocalRestSession | null {
  const records = loadRestJournal(userId, workoutId);
  const predecessor = records.find((row) => row.start_mutation_id === predecessorStartMutationId);
  if (!predecessor || !['completed', 'skipped'].includes(predecessor.status)) return null;
  const existing = records.find(
    (row) => row.restart_of_start_mutation_id === predecessorStartMutationId,
  );
  if (existing) return existing.status === 'running' ? existing : null;
  if (records.some((row) => row.status === 'running')) return null;
  const startedAt = new Date(at).toISOString();
  const created: LocalRestSession = {
    source_set_id: predecessor.source_set_id,
    started_at: startedAt,
    planned_seconds: predecessor.planned_seconds,
    adjusted_seconds: predecessor.planned_seconds,
    deadline: at + predecessor.planned_seconds * 1000,
    status: 'running',
    start_mutation_id: makeId(),
    restart_of_start_mutation_id: predecessorStartMutationId,
    pending: [],
  };
  records.push(created);
  writeStorage(actionStorageKey(userId, workoutId, created.start_mutation_id), {
    source_set_id: created.source_set_id,
    session_start_mutation_id: created.start_mutation_id,
    start: {
      source_set_id: created.source_set_id,
      started_at: created.started_at,
      planned_seconds: created.planned_seconds,
      adjusted_seconds: created.adjusted_seconds,
      deadline: created.deadline,
      start_mutation_id: created.start_mutation_id,
      restart_of_start_mutation_id: predecessorStartMutationId,
    },
  });
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
  const row = records.find((item) => item.source_set_id === sourceSetId && item.status === 'running');
  if (!row) return null;
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
  if (action === 'complete' && at < Date.parse(row.started_at)) return null;
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
    const terminalStatus = {
      complete: 'completed',
      skip: 'skipped',
      interrupt: 'interrupted',
      unknown: 'unknown',
    } as const;
    row.status = terminalStatus[effectiveAction];
    row.ended_at = occurredAt;
    row.needs_review = false;
    row.background_since = undefined;
    if (effectiveAction === 'complete') {
      entry.ended_at = occurredAt;
      row.measured_seconds = correctedSeconds ?? Math.max(0, Math.floor((at - Date.parse(row.started_at)) / 1000));
      row.source = correctedSeconds === undefined ? 'USER_CONFIRMED' : 'USER_CORRECTED';
    } else {
      row.measured_seconds = null;
    }
  }
  row.pending.push(entry);
  writeStorage(actionStorageKey(userId, workoutId, entry.mutation_id), {
    source_set_id: sourceSetId,
    session_start_mutation_id: row.start_mutation_id,
    operation: entry,
  });
  saveRestJournal(userId, workoutId, records);
  return row;
}

export function acknowledgeRestPlan(userId: number, workoutId: number, sourceSetId: number): void {
  const records = loadRestJournal(userId, workoutId);
  const row = records.find((item) => item.source_set_id === sourceSetId && item.status === 'running');
  if (!row || row.notified) return;
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
  startMutationId: string,
  remote: RemoteRestSession,
  mutationId?: string,
): void {
  const records = loadRestJournal(userId, workoutId);
  const row = records.find((item) => item.start_mutation_id === startMutationId);
  if (!row) {
    if (mutationId) updateStartRecovery(userId, workoutId, mutationId, remote, false);
    return;
  }
  // Reject stale/cross-interval ACKs, even when multiple intervals share a set.
  if (
    remote.workout_id !== workoutId ||
    remote.source_set_id !== row.source_set_id ||
    Math.abs(Date.parse(remote.started_at) - Date.parse(row.started_at)) > 1000 ||
    (remote.start_mutation_id && remote.start_mutation_id !== row.start_mutation_id)
  ) {
    throw new Error('rest_interval_identity_mismatch');
  }
  const acknowledgedOperation = mutationId
    ? row.pending.find((operation) => operation.mutation_id === mutationId)
    : undefined;
  row.server_id = remote.id;
  row.server_version = Math.max(row.server_version ?? 0, remote.version);
  if (remote.measured_seconds !== undefined) row.measured_seconds = remote.measured_seconds;
  if (Number.isInteger(remote.adjusted_seconds) && remote.adjusted_seconds > 0) {
    row.adjusted_seconds = Math.max(row.adjusted_seconds, remote.adjusted_seconds);
    const startedAt = Date.parse(row.started_at);
    if (Number.isFinite(startedAt)) {
      row.deadline = Math.max(row.deadline, startedAt + remote.adjusted_seconds * 1000);
    }
  }
  if (mutationId) {
    row.pending = row.pending.filter((operation) => operation.mutation_id !== mutationId);
    if (mutationId !== row.start_mutation_id) {
      removeStorage(actionStorageKey(userId, workoutId, mutationId));
    }
  }
  const terminalStatus = acknowledgedOperation
    ? terminalStatusForAction(acknowledgedOperation.action)
    : undefined;
  updateStartRecovery(
    userId,
    workoutId,
    row.start_mutation_id,
    remote,
    terminalStatus !== undefined && remote.status === terminalStatus,
  );
  saveRestJournal(userId, workoutId, records);
}

/** Sync starts/actions in lineage order, preserving all local intervals and durable replay keys. */
export async function syncRestJournal(userId: number, workoutId: number): Promise<void> {
  if (typeof navigator !== 'undefined' && !navigator.onLine) return;
  const key = restJournalStorageKey(userId, workoutId);
  await crossContextCoordinator.run(`rest-sync:${key}`, async () => {
    const intervalIds = loadRestJournal(userId, workoutId)
      .filter((row) => !row.server_id || row.pending.length)
      .map((row) => row.start_mutation_id);
    for (const intervalId of intervalIds) {
      const latest = () =>
        loadRestJournal(userId, workoutId).find((row) => row.start_mutation_id === intervalId);
      let row = latest();
      if (!row) continue;
      if (!row.server_id) {
        const predecessor = row.restart_of_start_mutation_id
          ? loadRestJournal(userId, workoutId).find(
              (item) => item.start_mutation_id === row?.restart_of_start_mutation_id,
            )
          : null;
        // The predecessor's start AND stop/skip must be persisted before restart.
        if (row.restart_of_start_mutation_id && (!predecessor?.server_id || predecessor.pending.length)) {
          continue;
        }
        try {
          const remote = await api<RemoteRestSession>(
            predecessor
              ? `/api/v1/workouts/rest-sessions/${predecessor.server_id}/restart`
              : `/api/v1/workouts/${workoutId}/rest-sessions`,
            {
              method: 'POST',
              body: predecessor
                ? { started_at: row.started_at, mutation_id: row.start_mutation_id }
                : {
                    source_set_id: row.source_set_id,
                    started_at: row.started_at,
                    mutation_id: row.start_mutation_id,
                  },
            },
          );
          if (predecessor && remote.id === predecessor.server_id) {
            throw new Error('rest_restart_reused_predecessor');
          }
          acknowledgeRemote(userId, workoutId, intervalId, remote, row.start_mutation_id);
        } catch (error) {
          if (error instanceof ApiError && [409, 503].includes(error.status)) continue;
          throw error;
        }
      }
      row = latest();
      if (!row?.server_id) continue;
      for (const pendingId of row.pending.map((operation) => operation.mutation_id)) {
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
          acknowledgeRemote(userId, workoutId, intervalId, remote, operation.mutation_id);
        } catch (error) {
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
