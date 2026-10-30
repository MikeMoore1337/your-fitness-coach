import { api, ApiError } from '../../shared/api/client';
import { crossContextCoordinator } from '../../shared/browser/crossContextLock';
import { readStorage, removeStorage, writeStorage } from '../../shared/storage';
import type { components } from '../../shared/api/schema';
import type { Workout } from '../../shared/api/types';

export type NoteResponse = components['schemas']['ExerciseNoteResponse'];
export type NoteTag = components['schemas']['ExerciseNoteValue']['tags'][number];
export type NoteIdentity = Pick<
  NoteResponse,
  | 'exercise_id'
  | 'source_template_exercise_id'
  | 'plan_revision_number'
  | 'week_number'
  | 'day_number'
  | 'source_cycle_week'
  | 'cycle_iteration'
>;
export type NoteContent = { body: string | null; tags: NoteTag[] };
export const NOTE_TAGS: Array<{ value: NoteTag; label: string }> = [
  { value: 'easy', label: 'Легко' },
  { value: 'hard', label: 'Тяжело' },
  { value: 'increase_weight', label: 'Повысить вес' },
];
type Pending =
  | (NoteIdentity &
      NoteContent & {
        mutation_id: string;
        expected_version: number;
        action: 'put' | 'delete';
        target?: 'current';
      })
  | (NoteContent & {
      mutation_id: string;
      expected_version: number;
      action: 'put' | 'delete';
      target: 'history';
      note_id: number;
    });
export type NoteQueue = {
  userId: number;
  workoutId: number;
  occurrenceId: number;
  exerciseTitle: string;
  pending: Pending[];
  blocked: string | null;
};
export type StoredNoteDraft = NoteContent & {
  userId: number;
  workoutId: number;
  occurrenceId: number;
  exerciseTitle: string;
  expectedVersion: number;
  identity?: NoteIdentity;
  note?: components['schemas']['ExerciseNoteHistoryItem'];
};

const PREFIX = 'fit_exercise_note_v1_';
export const NOTE_QUEUE_EVENT = 'fit:exercise-note-queue';
export const NOTE_DRAFT_EVENT = 'fit:exercise-note-draft';
const draftTab = (() => {
  try {
    const key = 'fit_exercise_note_draft_tab';
    const existing = sessionStorage.getItem(key);
    if (existing) return existing;
    const id = makeMutationId();
    sessionStorage.setItem(key, id);
    return id;
  } catch {
    return makeMutationId();
  }
})();
const IDENTITY_KEYS: Array<keyof NoteIdentity> = [
  'exercise_id',
  'source_template_exercise_id',
  'plan_revision_number',
  'week_number',
  'day_number',
  'source_cycle_week',
  'cycle_iteration',
];

export function noteQueueKey(userId: number, workoutId: number, occurrenceId: number): string {
  return `${PREFIX}user_${userId}_workout_${workoutId}_occurrence_${occurrenceId}`;
}

export function historyNoteQueueKey(userId: number, workoutId: number, noteId: number): string {
  return `${PREFIX}user_${userId}_history_${workoutId}_note_${noteId}`;
}

export function noteDraftKey(key: string, identity?: NoteIdentity): string {
  const context = identity
    ? `${Object.values(identity)
        .map((value) => value ?? 'none')
        .join('_')}_`
    : '';
  return `${key}_draft_${context}tab_${draftTab}`;
}

export function noteDrafts(userId: number): Array<{ key: string; data: StoredNoteDraft }> {
  try {
    return Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index))
      .filter((key): key is string =>
        Boolean(key?.startsWith(`${PREFIX}user_${userId}_`) && key.includes('_draft_')),
      )
      .flatMap((key) => {
        const data = readStorage<StoredNoteDraft | null>(key, null);
        return data &&
          data.userId === userId &&
          Number.isInteger(data.workoutId) &&
          Number.isInteger(data.occurrenceId) &&
          typeof data.exerciseTitle === 'string' &&
          (typeof data.body === 'string' || data.body === null) &&
          Array.isArray(data.tags)
          ? [{ key, data }]
          : [];
      });
  } catch {
    return [];
  }
}

export function noteIdentity(
  workout: Workout,
  exercise: Workout['exercises'][number],
): NoteIdentity {
  return {
    exercise_id: exercise.exercise_id,
    source_template_exercise_id: exercise.source_template_exercise_id ?? null,
    plan_revision_number: workout.plan_revision_number ?? null,
    week_number: workout.week_number,
    day_number: workout.day_number,
    source_cycle_week: workout.source_cycle_week ?? null,
    cycle_iteration: workout.cycle_iteration ?? null,
  };
}

export function sameNoteIdentity(left: NoteIdentity, right: NoteIdentity): boolean {
  return IDENTITY_KEYS.every((key) => left[key] === right[key]);
}

function validQueue(value: unknown, userId: number): value is NoteQueue {
  if (!value || typeof value !== 'object') return false;
  const data = value as Partial<NoteQueue>;
  return (
    data.userId === userId &&
    Number.isInteger(data.workoutId) &&
    Number.isInteger(data.occurrenceId) &&
    typeof data.exerciseTitle === 'string' &&
    Array.isArray(data.pending) &&
    data.pending.every(
      (item) =>
        item &&
        typeof item.mutation_id === 'string' &&
        Number.isInteger(item.expected_version) &&
        item.expected_version >= 0 &&
        ['put', 'delete'].includes(item.action) &&
        (item.target === 'history'
          ? Number.isInteger(item.note_id)
          : typeof item.exercise_id === 'number') &&
        (typeof item.body === 'string' || item.body === null) &&
        Array.isArray(item.tags),
    ) &&
    (data.blocked === null || typeof data.blocked === 'string')
  );
}

export function readNoteQueue(key: string, userId: number): NoteQueue | null {
  const data = readStorage<unknown>(key, null);
  return validQueue(data, userId) ? data : null;
}

function existingQueue(key: string, userId: number): NoteQueue | null | undefined {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return null;
    const data: unknown = JSON.parse(raw);
    return validQueue(data, userId) ? data : undefined;
  } catch {
    return undefined;
  }
}

export function noteQueues(userId: number): Array<{ key: string; data: NoteQueue }> {
  try {
    return Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index))
      .filter((key): key is string => Boolean(key?.startsWith(`${PREFIX}user_${userId}_`)))
      .flatMap((key) => {
        const data = readNoteQueue(key, userId);
        return data ? [{ key, data }] : [];
      });
  } catch {
    return [];
  }
}

function notify(): void {
  window.dispatchEvent(new Event(NOTE_QUEUE_EVENT));
}

function saveQueue(key: string, data: NoteQueue): boolean {
  const saved = writeStorage(key, data);
  if (saved) notify();
  return saved;
}

function makeMutationId(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `note-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export async function enqueueExerciseNote(
  userId: number,
  workout: Workout,
  exercise: Workout['exercises'][number],
  version: number,
  action: 'put' | 'delete',
  content: NoteContent,
): Promise<'queued' | 'blocked' | 'unavailable'> {
  const key = noteQueueKey(userId, workout.id, exercise.id);
  const identity = noteIdentity(workout, exercise);
  return crossContextCoordinator.run(key, () => {
    const existing = existingQueue(key, userId);
    if (existing === undefined) return 'unavailable';
    const current = existing ?? {
      userId,
      workoutId: workout.id,
      occurrenceId: exercise.id,
      exerciseTitle: exercise.exercise_title,
      pending: [],
      blocked: null,
    };
    const last = current.pending.at(-1);
    if (
      current.blocked ||
      (last &&
        (last.target === 'history' ||
          !sameNoteIdentity(last, identity) ||
          version !== last.expected_version + 1))
    )
      return 'blocked';
    if (
      last &&
      last.action === action &&
      last.body === content.body &&
      JSON.stringify(last.tags) === JSON.stringify(content.tags)
    )
      return 'queued';
    const next: NoteQueue = {
      ...current,
      pending: [
        ...current.pending,
        {
          ...identity,
          ...content,
          action,
          mutation_id: makeMutationId(),
          expected_version: last ? last.expected_version + 1 : version,
        },
      ],
    };
    return saveQueue(key, next) ? 'queued' : 'unavailable';
  });
}

export async function enqueueHistoricalExerciseNote(
  userId: number,
  note: components['schemas']['ExerciseNoteHistoryItem'],
  action: 'put' | 'delete',
  content: NoteContent,
  expectedVersion: number,
): Promise<'queued' | 'blocked' | 'unavailable'> {
  const key = historyNoteQueueKey(userId, note.workout_id, note.id);
  return crossContextCoordinator.run(key, () => {
    const existing = existingQueue(key, userId);
    if (existing === undefined) return 'unavailable';
    const current = existing ?? {
      userId,
      workoutId: note.workout_id,
      occurrenceId: note.workout_exercise_id,
      exerciseTitle: note.exercise_title ?? 'Упражнение',
      pending: [],
      blocked: null,
    };
    const last = current.pending.at(-1);
    if (
      current.blocked ||
      (last &&
        (last.target !== 'history' ||
          last.note_id !== note.id ||
          expectedVersion !== last.expected_version + 1))
    )
      return 'blocked';
    if (
      last &&
      last.action === action &&
      last.body === content.body &&
      JSON.stringify(last.tags) === JSON.stringify(content.tags)
    )
      return 'queued';
    return saveQueue(key, {
      ...current,
      pending: [
        ...current.pending,
        {
          ...content,
          target: 'history',
          note_id: note.id,
          action,
          mutation_id: makeMutationId(),
          expected_version: last ? last.expected_version + 1 : expectedVersion,
        },
      ],
    })
      ? 'queued'
      : 'unavailable';
  });
}

export async function clearNoteQueue(key: string, userId: number): Promise<boolean> {
  return crossContextCoordinator.run(key, () => {
    if (!readNoteQueue(key, userId)) return true;
    removeStorage(key);
    if (readNoteQueue(key, userId)) return false;
    notify();
    return true;
  });
}

export async function resolveNoteConflict(
  key: string,
  userId: number,
  version: number,
  content: NoteContent,
): Promise<boolean> {
  return crossContextCoordinator.run(key, () => {
    const current = readNoteQueue(key, userId);
    const last = current?.pending.at(-1);
    if (!current || !last || current.blocked !== 'exercise_note_version_conflict') return false;
    return saveQueue(key, {
      ...current,
      blocked: null,
      pending: [{ ...last, ...content, expected_version: version, mutation_id: makeMutationId() }],
    });
  });
}

function errorCode(error: ApiError): string {
  const body = error.body;
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (detail && typeof detail === 'object' && 'code' in detail) {
      const code = (detail as { code?: unknown }).code;
      if (typeof code === 'string') return code;
    }
  }
  return error.status === 404 ? 'exercise_note_identity_changed' : 'exercise_note_error';
}

export async function flushExerciseNotes(
  userId: number,
  onSaved: (workoutId: number, occurrenceId: number, response: NoteResponse | null) => void,
): Promise<void> {
  if (!navigator.onLine) return;
  for (const { key } of noteQueues(userId)) {
    await crossContextCoordinator.run(key, async () => {
      while (navigator.onLine) {
        const data = readNoteQueue(key, userId);
        const operation = data?.pending[0];
        if (!data || !operation || data.blocked) return;
        const { action, body, tags, target, ...rest } = operation;
        const payload =
          target === 'history'
            ? {
                mutation_id: operation.mutation_id,
                expected_version: operation.expected_version,
                ...(action === 'put' ? { body, tags } : {}),
              }
            : action === 'put'
              ? { ...rest, body, tags }
              : rest;
        try {
          const saved = await api<
            NoteResponse | components['schemas']['ExerciseNoteHistoryResult']
          >(
            target === 'history'
              ? `/api/v1/workouts/exercise-notes/history/${operation.note_id}`
              : `/api/v1/workouts/${data.workoutId}/exercise-notes/${data.occurrenceId}`,
            { method: action === 'put' ? 'PUT' : 'DELETE', body: payload },
          );
          const latest = readNoteQueue(key, userId);
          if (!latest || latest.pending[0]?.mutation_id !== operation.mutation_id) return;
          if (
            saved.version < operation.expected_version + 1 ||
            (target !== 'history' &&
              (!('workout_id' in saved) ||
                saved.workout_id !== data.workoutId ||
                saved.workout_exercise_id !== data.occurrenceId ||
                !sameNoteIdentity(saved, operation)))
          ) {
            saveQueue(key, { ...latest, blocked: 'exercise_note_identity_changed' });
            return;
          }
          onSaved(
            data.workoutId,
            data.occurrenceId,
            target === 'history' ? null : (saved as NoteResponse),
          );
          const remaining = latest.pending.slice(1);
          if (remaining.length) {
            if (!saveQueue(key, { ...latest, pending: remaining })) return;
          } else {
            removeStorage(key);
            if (readNoteQueue(key, userId)) return;
            notify();
          }
        } catch (error) {
          if (error instanceof ApiError && (error.status === 409 || error.status === 404)) {
            const latest = readNoteQueue(key, userId);
            if (latest?.pending[0]?.mutation_id === operation.mutation_id) {
              saveQueue(key, { ...latest, blocked: errorCode(error) });
            }
          }
          return;
        }
      }
    });
  }
}
