import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, getUserFacingErrorMessage } from '../../shared/api/client';
import { formatCalendarDate } from '../../shared/dateTime';
import { readStorage, removeStorage, writeStorage } from '../../shared/storage';
import type { Workout } from '../../shared/api/types';
import { Button } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useOnlineStatus } from '../../shared/ui/OnlineStatus';
import {
  clearNoteQueue,
  enqueueExerciseNote,
  NOTE_DRAFT_EVENT,
  NOTE_TAGS,
  NOTE_QUEUE_EVENT,
  noteIdentity,
  noteDraftKey,
  noteQueueKey,
  readNoteQueue,
  resolveNoteConflict,
  sameNoteIdentity,
  type NoteContent,
  type NoteResponse,
} from './exerciseNoteQueue';
import './ExerciseExecutionNote.css';

const tags = NOTE_TAGS;
const weekTypes = { light: 'лёгкая неделя', medium: 'средняя неделя', heavy: 'тяжёлая неделя' };
type NoteDraft = NoteContent & { expectedVersion: number };

function describeLoad(load: NonNullable<NoteResponse['previous_note']>['load']): string | null {
  if (!load) return null;
  const parts = [
    load.actual_weight == null ? null : `${load.actual_weight} кг`,
    load.actual_reps == null ? null : `${load.actual_reps} повторений`,
    load.duration_minutes == null ? null : `${load.duration_minutes} мин`,
    load.distance_km == null ? null : `${load.distance_km} км`,
  ].filter(Boolean);
  return parts.length ? `Подход ${load.set_number} · ${parts.join(' × ')}` : null;
}

export function ExerciseExecutionNote({
  userId,
  workout,
  exercise,
  visible,
}: {
  userId: number;
  workout: Workout;
  exercise: Workout['exercises'][number];
  visible: boolean;
}) {
  const online = useOnlineStatus();
  const queryClient = useQueryClient();
  const { confirm } = useFeedback();
  const identity = useMemo(() => noteIdentity(workout, exercise), [workout, exercise]);
  const key = noteQueueKey(userId, workout.id, exercise.id);
  const draftKey = noteDraftKey(key, identity);
  const [queue, setQueue] = useState(() => readNoteQueue(key, userId));
  const [editedDraft, setEditedDraft] = useState<NoteDraft>(() =>
    readStorage(draftKey, { body: '', tags: [], expectedVersion: 0 }),
  );
  const [dirty, setDirty] = useState(() => readStorage<NoteDraft | null>(draftKey, null) !== null);
  const [open, setOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [serverVersion, setServerVersion] = useState<NoteResponse | null>(null);
  const inFlight = useRef(false);
  const path = `/api/v1/workouts/${workout.id}/exercise-notes/${exercise.id}`;
  const query = useQuery({
    queryKey: ['exercise-note', userId, workout.id, exercise.id, ...Object.values(identity)],
    queryFn: ({ signal }) => api<NoteResponse>(path, { signal, cache: 'no-store' }),
    enabled: visible && online,
    retry: false,
    staleTime: 0,
    gcTime: 0,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
  });
  const data = query.data && sameNoteIdentity(query.data, identity) ? query.data : null;
  const last = queue?.pending.at(-1);
  const differentExercise = Boolean(
    last && (last.target === 'history' || !sameNoteIdentity(last, identity)),
  );
  const current =
    last && !differentExercise
      ? last.action === 'delete'
        ? null
        : { body: last.body, tags: last.tags }
      : (data?.current_note ?? null);
  const draft = dirty
    ? editedDraft
    : {
        body: current?.body ?? '',
        tags: current?.tags ?? [],
        expectedVersion:
          last && !differentExercise ? last.expected_version + 1 : (data?.version ?? 0),
      };
  const previous =
    online && !query.isError && query.fetchStatus === 'idle' && !query.isFetching
      ? data?.previous_note
      : null;
  const historyReady =
    online && data && !query.isError && query.fetchStatus === 'idle' && !query.isFetching;
  const previousLoad = describeLoad(previous?.load ?? null);
  const previousDate = previous
    ? formatCalendarDate(previous.completed_on, {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      }).replace(/\s*г\.$/u, '')
    : null;
  const previousWeek = previous?.week_type ? weekTypes[previous.week_type] : 'тип недели не указан';

  useEffect(() => {
    const refresh = () => setQueue(readNoteQueue(key, userId));
    window.addEventListener(NOTE_QUEUE_EVENT, refresh);
    window.addEventListener('storage', refresh);
    refresh();
    return () => {
      window.removeEventListener(NOTE_QUEUE_EVENT, refresh);
      window.removeEventListener('storage', refresh);
    };
  }, [key, userId]);

  const updateDraft = (next: NoteContent) => {
    const snapshot = { ...next, expectedVersion: draft.expectedVersion };
    setEditedDraft(snapshot);
    setDirty(true);
    if (
      !writeStorage(draftKey, {
        ...snapshot,
        userId,
        workoutId: workout.id,
        occurrenceId: exercise.id,
        exerciseTitle: exercise.exercise_title,
        identity,
      })
    ) {
      setMessage('Черновик не сохранён на устройстве. Не закрывайте приложение.');
    } else {
      setMessage(null);
      window.dispatchEvent(new Event(NOTE_DRAFT_EVENT));
    }
  };

  const submit = async (action: 'put' | 'delete') => {
    if (inFlight.current) return;
    const body = draft.body?.trim() || null;
    if (action === 'put' && !body && draft.tags.length === 0) {
      setMessage('Добавьте текст или выберите метку.');
      return;
    }
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
    inFlight.current = true;
    setWorking(true);
    try {
      const result = await enqueueExerciseNote(
        userId,
        workout,
        exercise,
        draft.expectedVersion,
        action,
        action === 'delete' ? { body: null, tags: [] } : { body, tags: draft.tags },
      );
      if (result === 'queued') {
        removeStorage(draftKey);
        window.dispatchEvent(new Event(NOTE_DRAFT_EVENT));
        setDirty(false);
        setMessage(
          online
            ? 'Отправляем заметку…'
            : 'Нет сети. Заметка сохранена на устройстве и будет отправлена при подключении.',
        );
      } else {
        setMessage(
          result === 'blocked'
            ? 'Сначала разберите несинхронизированную заметку.'
            : 'Не удалось сохранить заметку на устройстве. Не закрывайте приложение.',
        );
      }
    } catch {
      setMessage('Не удалось сохранить заметку на устройстве. Не закрывайте приложение.');
    } finally {
      inFlight.current = false;
      setWorking(false);
    }
  };

  const showServerVersion = async () => {
    setWorking(true);
    try {
      const result = await api<NoteResponse>(path, { cache: 'no-store' });
      if (!sameNoteIdentity(result, identity)) throw new Error('Упражнение изменилось.');
      setServerVersion(result);
    } catch (error) {
      setMessage(getUserFacingErrorMessage(error, 'Не удалось загрузить сохранённую версию.'));
    } finally {
      setWorking(false);
    }
  };

  const discardPending = async () => {
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
      setDirty(false);
      setServerVersion(null);
      setMessage(null);
      void queryClient.invalidateQueries({
        queryKey: ['exercise-note', userId, workout.id, exercise.id],
      });
    } else setMessage('Не удалось удалить изменения с устройства.');
  };

  const saveAfterConflict = async () => {
    if (!serverVersion) return;
    const content =
      last?.action === 'delete'
        ? { body: null, tags: [] }
        : { body: draft.body?.trim() || null, tags: draft.tags };
    if (last?.action !== 'delete' && !content.body && !content.tags.length) {
      setMessage('Добавьте текст или выберите метку.');
      return;
    }
    if (await resolveNoteConflict(key, userId, serverVersion.version, content)) {
      removeStorage(draftKey);
      window.dispatchEvent(new Event(NOTE_DRAFT_EVENT));
      setDirty(false);
      setServerVersion(null);
      setMessage('Отправляем заметку…');
    } else setMessage('Не удалось сохранить изменение на устройстве.');
  };

  const summary =
    current?.body ||
    current?.tags.map((value) => tags.find((tag) => tag.value === value)?.label).join(', ');
  const displayMessage =
    !queue?.pending.length &&
    (message === 'Отправляем заметку…' ||
      message === 'Нет сети. Заметка сохранена на устройстве и будет отправлена при подключении.')
      ? null
      : message;
  return (
    <details
      className="exercise-execution-note"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="yfc-disclosure-summary">
        <span className="exercise-execution-note__summary">
          <strong>Заметка к упражнению</strong>
          <small>
            {summary
              ? `Это выполнение · ${summary}`
              : previous
                ? `Последняя · ${previousDate} · ${previousWeek}\n${previous.body ?? previous.tags.map((value) => tags.find((tag) => tag.value === value)?.label).join(', ')}`
                : historyReady
                  ? 'Подходящих заметок пока нет'
                  : 'История заметок недоступна'}
          </small>
        </span>
        <span className="exercise-execution-note__action">
          {open ? 'Скрыть' : 'Открыть'}
          <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} />
        </span>
      </summary>
      <div className="exercise-execution-note__content">
        {previous ? (
          <div className="exercise-execution-note__past">
            <small>
              Последняя сохранённая заметка · {previousDate} · {previousWeek}
              <br />
              {previousLoad ? `Нагрузка: ${previousLoad}` : 'Нагрузка не записана'}
            </small>
            {previous.body && <p>{previous.body}</p>}
            {previous.tags.length > 0 && (
              <small>
                {previous.tags
                  .map((value) => tags.find((tag) => tag.value === value)?.label)
                  .join(' · ')}
              </small>
            )}
          </div>
        ) : (
          <small className="exercise-execution-note__hint">
            {historyReady ? 'Подходящих заметок пока нет' : 'История заметок недоступна'}
          </small>
        )}

        {differentExercise ? (
          <div className="exercise-execution-note__state" role="alert">
            <p>
              На устройстве осталась заметка для прежнего упражнения «{queue?.exerciseTitle}». Она
              не будет перенесена в это упражнение.
            </p>
            <p>{last?.body}</p>
            <Button type="button" variant="secondary" onClick={() => void discardPending()}>
              Удалить изменения с устройства
            </Button>
          </div>
        ) : (
          <>
            <div className="exercise-execution-note__editor">
              <label htmlFor={`exercise-note-${exercise.id}`}>Заметка к этому выполнению</label>
              <textarea
                id={`exercise-note-${exercise.id}`}
                maxLength={500}
                placeholder="Что стоит запомнить?"
                value={draft.body ?? ''}
                onChange={(event) => updateDraft({ ...draft, body: event.target.value })}
              />
              <small className="exercise-execution-note__hint">
                Необязательно · {(draft.body ?? '').length}/500
              </small>
            </div>
            {queue?.blocked && (
              <div className="exercise-execution-note__state" role="alert">
                <p>
                  {queue.blocked === 'exercise_note_version_conflict'
                    ? 'Заметка изменилась на другом устройстве. Ваш текст остался здесь.'
                    : 'Упражнение или сохранённая заметка изменились. Текст остался на устройстве.'}
                </p>
                {queue.blocked === 'exercise_note_version_conflict' && (
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={!online || working}
                    onClick={() => void showServerVersion()}
                  >
                    Посмотреть сохранённую версию
                  </Button>
                )}
                {serverVersion && (
                  <>
                    <p>На сервере: {serverVersion.current_note?.body ?? 'Текст отсутствует'}</p>
                    {serverVersion.current_note?.tags.length ? (
                      <p>
                        {serverVersion.current_note.tags
                          .map((value) => tags.find((tag) => tag.value === value)?.label)
                          .join(' · ')}
                      </p>
                    ) : null}
                    <Button
                      type="button"
                      disabled={working}
                      onClick={() => void saveAfterConflict()}
                    >
                      {last?.action === 'delete'
                        ? 'Удалить сохранённую заметку'
                        : 'Сохранить мой вариант'}
                    </Button>
                  </>
                )}
                <Button type="button" variant="secondary" onClick={() => void discardPending()}>
                  Удалить изменения с устройства
                </Button>
              </div>
            )}
            <fieldset>
              <legend>Метки</legend>
              <div className="exercise-execution-note__tags">
                {tags.map((tag) => (
                  <button
                    key={tag.value}
                    type="button"
                    data-yfc-choice="compact"
                    aria-pressed={draft.tags.includes(tag.value)}
                    onClick={() =>
                      updateDraft({
                        ...draft,
                        tags: draft.tags.includes(tag.value)
                          ? draft.tags.filter((item) => item !== tag.value)
                          : [...draft.tags, tag.value],
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
                disabled={working}
                onClick={() => {
                  removeStorage(draftKey);
                  window.dispatchEvent(new Event(NOTE_DRAFT_EVENT));
                  setDirty(false);
                  setOpen(false);
                  setMessage(null);
                }}
              >
                Отмена
              </Button>
              {current && (
                <Button
                  type="button"
                  variant="secondary"
                  disabled={working || Boolean(queue?.blocked)}
                  onClick={() => void submit('delete')}
                >
                  Удалить
                </Button>
              )}
            </div>
          </>
        )}
        {displayMessage && (
          <p className="exercise-execution-note__status" role="status">
            {displayMessage}
          </p>
        )}
        {!displayMessage && queue?.pending.length && !queue.blocked ? (
          <p className="exercise-execution-note__status" role="status">
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
