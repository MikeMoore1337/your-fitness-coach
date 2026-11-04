import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../../src/shared/api/client';
import { clearSensitiveUserScopedStorage } from '../../../../src/shared/userScopedStorage';
import type { Workout } from '../../../../src/shared/api/types';
import {
  enqueueExerciseNote,
  enqueueHistoricalExerciseNote,
  flushExerciseNotes,
  historyNoteQueueKey,
  noteIdentity,
  noteQueueKey,
  readNoteQueue,
  resolveNoteConflict,
  type NoteResponse,
} from '../../../../src/features/workouts/exerciseNoteQueue';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../../src/shared/api/client')>()),
  api: apiMock,
}));
vi.mock('../../../../src/shared/browser/crossContextLock', () => ({
  crossContextCoordinator: { run: async (_name: string, task: () => unknown) => task() },
}));

const exercise = {
  id: 101,
  exercise_id: 11,
  exercise_title: 'Жим лёжа',
  source_template_exercise_id: 71,
  metric_type: 'strength',
  sort_order: 1,
  prescribed_sets: 2,
  prescribed_reps: '8',
  rest_seconds: 90,
  has_guide: false,
  sets: [],
} satisfies Workout['exercises'][number];
const workout = {
  id: 42,
  title: 'Тренировка',
  scheduled_date: '2026-10-30',
  status: 'in_progress',
  day_number: 1,
  week_number: 2,
  plan_revision_number: 3,
  source_cycle_week: 2,
  cycle_iteration: 1,
  exercises: [exercise],
} satisfies Workout;
const key = noteQueueKey(7, workout.id, exercise.id);
const response = (version: number): NoteResponse => ({
  workout_id: workout.id,
  workout_exercise_id: exercise.id,
  ...noteIdentity(workout, exercise),
  version,
  current_note: { id: 1, body: 'Текст', tags: ['easy'], version },
  previous_note: null,
});

describe('exercise note queue', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMock.mockReset();
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
  });

  it('keeps offline edits in order and sends them with successive versions', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    expect(
      await enqueueExerciseNote(7, workout, exercise, 0, 'put', { body: 'Первый', tags: ['easy'] }),
    ).toBe('queued');
    expect(
      await enqueueExerciseNote(7, workout, exercise, 1, 'put', { body: 'Второй', tags: ['hard'] }),
    ).toBe('queued');
    const before = readNoteQueue(key, 7)!;
    expect(before.pending.map((item) => item.expected_version)).toEqual([0, 1]);
    await flushExerciseNotes(7, () => undefined);
    expect(apiMock).not.toHaveBeenCalled();
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    apiMock.mockResolvedValueOnce(response(1)).mockResolvedValueOnce(response(2));
    await flushExerciseNotes(7, () => undefined);
    expect(apiMock).toHaveBeenCalledTimes(2);
    expect(apiMock.mock.calls[0]![1].body).toMatchObject({ body: 'Первый', expected_version: 0 });
    expect(apiMock.mock.calls[1]![1].body).toMatchObject({ body: 'Второй', expected_version: 1 });
    expect(readNoteQueue(key, 7)).toBeNull();
  });

  it('retries the identical mutation after an uncertain network outcome', async () => {
    await enqueueExerciseNote(7, workout, exercise, 0, 'put', { body: 'Текст', tags: [] });
    apiMock.mockRejectedValueOnce(new ApiError('Нет сети', 0)).mockResolvedValueOnce(response(1));
    await flushExerciseNotes(7, () => undefined);
    const id = readNoteQueue(key, 7)!.pending[0]!.mutation_id;
    await flushExerciseNotes(7, () => undefined);
    expect(apiMock.mock.calls.map((call) => call[1].body.mutation_id)).toEqual([id, id]);
    expect(readNoteQueue(key, 7)).toBeNull();
  });

  it('stops on a conflict and only retries a user-selected version', async () => {
    await enqueueExerciseNote(7, workout, exercise, 0, 'put', {
      body: 'Мой текст',
      tags: ['easy'],
    });
    apiMock.mockRejectedValueOnce(
      new ApiError('Конфликт', 409, {
        detail: { code: 'exercise_note_version_conflict', current: { version: 3 } },
      }),
    );
    await flushExerciseNotes(7, () => undefined);
    const blocked = readNoteQueue(key, 7)!;
    expect(blocked.blocked).toBe('exercise_note_version_conflict');
    await flushExerciseNotes(7, () => undefined);
    expect(apiMock).toHaveBeenCalledTimes(1);
    expect(
      await resolveNoteConflict(key, 7, 3, { body: 'Мой исправленный текст', tags: ['hard'] }),
    ).toBe(true);
    const resolved = readNoteQueue(key, 7)!;
    expect(resolved.pending[0]!.mutation_id).not.toBe(blocked.pending[0]!.mutation_id);
    expect(resolved.pending[0]).toMatchObject({
      expected_version: 3,
      body: 'Мой исправленный текст',
      tags: ['hard'],
    });
  });

  it('does not move a pending note to a replacement exercise', async () => {
    await enqueueExerciseNote(7, workout, exercise, 0, 'put', {
      body: 'Старое упражнение',
      tags: [],
    });
    const replacement = { ...exercise, exercise_id: 12, exercise_title: 'Другое упражнение' };
    expect(
      await enqueueExerciseNote(7, workout, replacement, 0, 'put', {
        body: 'Новый текст',
        tags: [],
      }),
    ).toBe('blocked');
    expect(readNoteQueue(key, 7)!.pending[0]).toMatchObject({
      exercise_id: 11,
      body: 'Старое упражнение',
    });
  });

  it('does not silently chain a second tab that edited an older version', async () => {
    await enqueueExerciseNote(7, workout, exercise, 0, 'put', { body: 'Первая вкладка', tags: [] });
    expect(
      await enqueueExerciseNote(7, workout, exercise, 0, 'put', {
        body: 'Вторая вкладка',
        tags: [],
      }),
    ).toBe('blocked');
    expect(readNoteQueue(key, 7)?.pending.map((item) => item.body)).toEqual(['Первая вкладка']);
  });

  it('does not claim local persistence when storage rejects the write', async () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota');
    });
    try {
      expect(
        await enqueueExerciseNote(7, workout, exercise, 0, 'put', { body: 'Текст', tags: [] }),
      ).toBe('unavailable');
      expect(apiMock).not.toHaveBeenCalled();
    } finally {
      spy.mockRestore();
    }
  });

  it('does not restore private queued data after logout during an in-flight request', async () => {
    await enqueueExerciseNote(7, workout, exercise, 0, 'put', { body: 'Первый', tags: [] });
    await enqueueExerciseNote(7, workout, exercise, 1, 'put', { body: 'Второй', tags: [] });
    let finish!: (value: NoteResponse) => void;
    apiMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const flushing = flushExerciseNotes(7, () => undefined);
    await vi.waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
    clearSensitiveUserScopedStorage();
    finish(response(1));
    await flushing;
    expect(readNoteQueue(key, 7)).toBeNull();
    expect(apiMock).toHaveBeenCalledTimes(1);
  });

  it('keeps a corrupt local queue intact instead of overwriting it', async () => {
    localStorage.setItem(key, '{invalid');
    expect(
      await enqueueExerciseNote(7, workout, exercise, 0, 'put', { body: 'Новый', tags: [] }),
    ).toBe('unavailable');
    expect(localStorage.getItem(key)).toBe('{invalid');
  });

  it('retries historical edits with the same mutation and blocks on a conflicting version', async () => {
    const note = {
      id: 6,
      workout_id: 42,
      workout_exercise_id: 101,
      exercise_id: 11,
      exercise_title: 'Жим лёжа',
      body: 'Раньше',
      tags: [],
      version: 2,
    } as const;
    const historyKey = historyNoteQueueKey(7, 42, 6);
    expect(
      await enqueueHistoricalExerciseNote(
        7,
        { ...note, tags: [] },
        'put',
        { body: 'Новый текст', tags: ['hard'] },
        2,
      ),
    ).toBe('queued');
    apiMock.mockRejectedValueOnce(new ApiError('Нет сети', 0)).mockRejectedValueOnce(
      new ApiError('Конфликт', 409, {
        detail: { code: 'exercise_note_version_conflict' },
      }),
    );
    await flushExerciseNotes(7, () => undefined);
    await flushExerciseNotes(7, () => undefined);
    expect(apiMock.mock.calls[0]![0]).toBe('/api/v1/workouts/exercise-notes/history/6');
    expect(apiMock.mock.calls[0]![1].body.mutation_id).toBe(
      apiMock.mock.calls[1]![1].body.mutation_id,
    );
    expect(readNoteQueue(historyKey, 7)?.blocked).toBe('exercise_note_version_conflict');
    expect(
      await resolveNoteConflict(historyKey, 7, 4, { body: 'Новый текст', tags: ['hard'] }),
    ).toBe(true);
    apiMock.mockResolvedValueOnce({
      version: 5,
      current_note: { id: 6, version: 5, body: 'Новый текст', tags: ['hard'] },
    });
    const saved = vi.fn();
    await flushExerciseNotes(7, saved);
    expect(saved).toHaveBeenCalledWith(42, 101, null);
    expect(readNoteQueue(historyKey, 7)).toBeNull();
  });
});
