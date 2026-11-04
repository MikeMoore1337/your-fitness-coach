import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, getUserFacingErrorMessage } from '../../shared/api/client';
import type { components } from '../../shared/api/schema';
import { readStorage, removeStorage, writeStorage } from '../../shared/storage';
import { Button } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useOnlineStatus } from '../../shared/ui/OnlineStatus';
import {
  clearNoteQueue,
  enqueueHistoricalExerciseNote,
  historyNoteQueueKey,
  NOTE_DRAFT_EVENT,
  NOTE_QUEUE_EVENT,
  NOTE_TAGS,
  noteDraftKey,
  noteDrafts,
  noteQueues,
  readNoteQueue,
  resolveNoteConflict,
  type NoteContent,
} from './exerciseNoteQueue';
import './ExerciseExecutionNote.css';

type HistoryNote = components['schemas']['ExerciseNoteHistoryItem'];
type HistoryResult = components['schemas']['ExerciseNoteHistoryResult'];
type Draft = NoteContent & { expectedVersion: number; note: HistoryNote };

function savedDrafts(userId: number, workoutId: number): HistoryNote[] {
  return noteDrafts(userId).flatMap(({ data }) =>
    data.note?.workout_id === workoutId && Number.isInteger(data.note.id) ? [data.note] : [],
  );
}

function HistoryEditor({ userId, note }: { userId: number; note: HistoryNote }) {
  const online = useOnlineStatus();
  const { confirm } = useFeedback();
  const queryClient = useQueryClient();
  const key = historyNoteQueueKey(userId, note.workout_id, note.id);
  const draftKey = noteDraftKey(key);
  const [queue, setQueue] = useState(() => readNoteQueue(key, userId));
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(() => readStorage(draftKey, null));
  const [server, setServer] = useState<HistoryResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const last = queue?.pending.at(-1);
  const hasVersionConflict = queue?.blocked === 'exercise_note_version_conflict';
  const pendingDeletion = last?.action === 'delete';
  const current = last?.target === 'history' ? last : note;
  const content = draft ?? {
    body: current.body ?? '',
    tags: current.tags,
    expectedVersion: last ? last.expected_version + 1 : note.version,
    note,
  };

  useEffect(() => {
    const refresh = () => setQueue(readNoteQueue(key, userId));
    window.addEventListener(NOTE_QUEUE_EVENT, refresh);
    window.addEventListener('storage', refresh);
    return () => {
      window.removeEventListener(NOTE_QUEUE_EVENT, refresh);
      window.removeEventListener('storage', refresh);
    };
  }, [key, userId]);

  function update(next: NoteContent) {
    const value = { ...next, expectedVersion: content.expectedVersion, note: content.note };
    setDraft(value);
    setMessage(
      writeStorage(draftKey, {
        ...value,
        userId,
        workoutId: note.workout_id,
        occurrenceId: note.workout_exercise_id,
        exerciseTitle: note.exercise_title ?? 'Упражнение',
      })
        ? null
        : 'Черновик не сохранён на устройстве. Не закрывайте приложение.',
    );
    window.dispatchEvent(new Event(NOTE_DRAFT_EVENT));
  }

  async function submit(action: 'put' | 'delete') {
    if (working) return;
    const value = { body: content.body?.trim() || null, tags: content.tags };
    if (action === 'put' && !value.body && !value.tags.length) {
      setMessage('Добавьте текст или выберите метку.');
      return;
    }
    setWorking(true);
    try {
      if (
        action === 'delete' &&
        !(await confirm({
          title: 'Удалить заметку?',
          message: 'Заметка к этому выполнению упражнения будет удалена.',
          confirmText: 'Удалить',
          danger: true,
        }))
      )
        return;
      const result = await enqueueHistoricalExerciseNote(
        userId,
        note,
        action,
        action === 'delete' ? { body: null, tags: [] } : value,
        content.expectedVersion,
      );
      if (result === 'queued') {
        removeStorage(draftKey);
        window.dispatchEvent(new Event(NOTE_DRAFT_EVENT));
        setDraft(null);
        setMessage(
          online
            ? 'Отправляем заметку…'
            : 'Нет сети. Заметка сохранена на устройстве и будет отправлена при подключении.',
        );
      } else {
        const isBlocked = result === 'blocked';
        setMessage(
          isBlocked
            ? 'Сначала разберите несинхронизированную заметку.'
            : 'Не удалось сохранить заметку на устройстве.',
        );
      }
    } catch {
      setMessage('Не удалось сохранить заметку на устройстве.');
    } finally {
      setWorking(false);
    }
  }

  async function discard() {
    if (
      !(await confirm({
        title: 'Удалить изменения с устройства?',
        message: 'Неотправленный текст будет удалён с этого устройства.',
        confirmText: 'Удалить',
        danger: true,
      }))
    )
      return;
    if (await clearNoteQueue(key, userId)) {
      removeStorage(draftKey);
      window.dispatchEvent(new Event(NOTE_DRAFT_EVENT));
      setDraft(null);
      setServer(null);
      setMessage(null);
      window.dispatchEvent(new Event(NOTE_QUEUE_EVENT));
      void queryClient.invalidateQueries({
        queryKey: ['exercise-note-history', userId, note.workout_id],
      });
    } else setMessage('Не удалось удалить изменения с устройства.');
  }

  async function showServer() {
    setWorking(true);
    try {
      setServer(
        await api<HistoryResult>(`/api/v1/workouts/exercise-notes/history/${note.id}`, {
          cache: 'no-store',
        }),
      );
    } catch (error) {
      setMessage(getUserFacingErrorMessage(error, 'Не удалось загрузить сохранённую версию.'));
    } finally {
      setWorking(false);
    }
  }

  async function saveConflict() {
    if (!server) return;
    const value =
      last?.action === 'delete'
        ? { body: null, tags: [] }
        : {
            body: content.body?.trim() || null,
            tags: content.tags,
          };
    if (last?.action !== 'delete' && !value.body && !value.tags.length) {
      setMessage('Добавьте текст или выберите метку.');
      return;
    }
    if (await resolveNoteConflict(key, userId, server.version, value)) {
      removeStorage(draftKey);
      window.dispatchEvent(new Event(NOTE_DRAFT_EVENT));
      setDraft(null);
      setServer(null);
      setMessage('Отправляем заметку…');
    } else setMessage('Не удалось сохранить изменение на устройстве.');
  }

  return (
    <details
      className="exercise-execution-note"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="yfc-disclosure-summary">
        <span className="exercise-execution-note__summary">
          <strong>{note.exercise_title ?? 'Упражнение'}</strong>
          <small>
            {pendingDeletion
              ? 'Ожидает удаления'
              : current.body ||
                current.tags
                  .map((value) => NOTE_TAGS.find((tag) => tag.value === value)?.label)
                  .join(' · ')}
          </small>
        </span>
        <span className="exercise-execution-note__action">
          {open ? 'Скрыть' : 'Открыть'}
          <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} />
        </span>
      </summary>
      <div className="exercise-execution-note__content">
        <div className="exercise-execution-note__editor">
          <label htmlFor={`exercise-history-note-${note.id}`}>Заметка к этому выполнению</label>
          <textarea
            id={`exercise-history-note-${note.id}`}
            maxLength={500}
            value={content.body ?? ''}
            onChange={(event) => update({ body: event.target.value, tags: content.tags })}
          />
          <small className="exercise-execution-note__hint">{(content.body ?? '').length}/500</small>
        </div>
        {queue?.blocked && (
          <div className="exercise-execution-note__state" role="alert">
            <p>
              {hasVersionConflict
                ? 'Заметка изменилась на другом устройстве. Ваш текст остался здесь.'
                : 'Заметка или тренировка изменились. Текст остался на устройстве.'}
            </p>
            {hasVersionConflict && (
              <Button
                type="button"
                variant="secondary"
                disabled={!online || working}
                onClick={() => void showServer()}
              >
                Посмотреть сохранённую версию
              </Button>
            )}
            {server && (
              <>
                <p>
                  На сервере:{' '}
                  {server.current_note?.body ??
                    (server.current_note ? 'Текст отсутствует' : 'Заметка удалена')}
                </p>
                {server.current_note?.tags.length ? (
                  <p>
                    {server.current_note.tags
                      .map((value) => NOTE_TAGS.find((tag) => tag.value === value)?.label)
                      .join(' · ')}
                  </p>
                ) : null}
                <Button type="button" disabled={working} onClick={() => void saveConflict()}>
                  {pendingDeletion ? 'Удалить сохранённую заметку' : 'Сохранить мой вариант'}
                </Button>
              </>
            )}
            <Button type="button" variant="secondary" onClick={() => void discard()}>
              Удалить изменения с устройства
            </Button>
          </div>
        )}
        <fieldset>
          <legend>Метки</legend>
          <div className="exercise-execution-note__tags">
            {NOTE_TAGS.map((tag) => (
              <button
                key={tag.value}
                type="button"
                data-yfc-choice="compact"
                aria-pressed={content.tags.includes(tag.value)}
                onClick={() =>
                  update({
                    body: content.body,
                    tags: content.tags.includes(tag.value)
                      ? content.tags.filter((item) => item !== tag.value)
                      : [...content.tags, tag.value],
                  })
                }
              >
                {tag.label}
              </button>
            ))}
          </div>
        </fieldset>
        <div className="exercise-execution-note__buttons">
          <Button
            type="button"
            disabled={working || Boolean(queue?.blocked)}
            onClick={() => void submit('put')}
          >
            Сохранить
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={working || Boolean(queue?.blocked)}
            onClick={() => void submit('delete')}
          >
            Удалить
          </Button>
        </div>
        {message &&
          (queue?.pending.length ||
            (!message.startsWith('Отправляем') &&
              !message.startsWith('Нет сети. Заметка сохранена'))) && (
            <p role="status">{message}</p>
          )}
        {!message && queue?.pending.length && !queue.blocked ? (
          <p role="status">
            {online
              ? 'Заметка ожидает отправки.'
              : 'Нет сети. Заметка сохранена на устройстве и будет отправлена при подключении.'}
            {online && (
              <button
                type="button"
                onClick={() => window.dispatchEvent(new Event(NOTE_QUEUE_EVENT))}
              >
                Повторить
              </button>
            )}
          </p>
        ) : null}
      </div>
    </details>
  );
}

export function ExerciseNoteHistory({ userId, workoutId }: { userId: number; workoutId: number }) {
  const online = useOnlineStatus();
  const [open, setOpen] = useState(false);
  const [, setRevision] = useState(0);
  const query = useQuery({
    queryKey: ['exercise-note-history', userId, workoutId],
    queryFn: ({ signal }) =>
      api<HistoryNote[]>(`/api/v1/workouts/${workoutId}/exercise-notes`, {
        signal,
        cache: 'no-store',
      }),
    enabled: open && online,
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });
  useEffect(() => {
    const refresh = () => setRevision((value) => value + 1);
    window.addEventListener(NOTE_QUEUE_EVENT, refresh);
    window.addEventListener(NOTE_DRAFT_EVENT, refresh);
    window.addEventListener('storage', refresh);
    return () => {
      window.removeEventListener(NOTE_QUEUE_EVENT, refresh);
      window.removeEventListener(NOTE_DRAFT_EVENT, refresh);
      window.removeEventListener('storage', refresh);
    };
  }, []);
  const entries = new Map<number, HistoryNote>();
  for (const note of savedDrafts(userId, workoutId)) entries.set(note.id, note);
  for (const note of query.data ?? []) entries.set(note.id, note);
  for (const { data } of noteQueues(userId)) {
    const last = data.pending.at(-1);
    if (data.workoutId === workoutId && last?.target === 'history' && !entries.has(last.note_id)) {
      entries.set(last.note_id, {
        id: last.note_id,
        workout_id: workoutId,
        workout_exercise_id: data.occurrenceId,
        exercise_id: 0,
        exercise_title: data.exerciseTitle,
        version: last.expected_version,
        body: last.body,
        tags: last.tags,
      });
    }
  }
  return (
    <details
      className="workout-history__rest"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="yfc-disclosure-summary">
        Заметки к упражнениям <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} />
      </summary>
      {query.isFetching && (
        <p className="muted" role="status">
          Загружаем заметки…
        </p>
      )}
      {(query.isError || !online) && (
        <p className="muted">
          История заметок сейчас недоступна. Изменения с этого устройства остаются ниже.
        </p>
      )}
      {Array.from(entries.values(), (note) => (
        <HistoryEditor key={note.id} userId={userId} note={note} />
      ))}
      {online && !query.isFetching && !query.isError && entries.size === 0 && (
        <p className="muted">Заметок к упражнениям нет.</p>
      )}
    </details>
  );
}
