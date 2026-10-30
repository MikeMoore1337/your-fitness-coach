import { useEffect, useState } from 'react';
import { api, getUserFacingErrorMessage } from '../../shared/api/client';
import type { components } from '../../shared/api/schema';
import type { Workout } from '../../shared/api/types';
import { removeStorage } from '../../shared/storage';
import { Button } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useOnlineStatus } from '../../shared/ui/OnlineStatus';
import {
  clearNoteQueue,
  NOTE_DRAFT_EVENT,
  NOTE_QUEUE_EVENT,
  NOTE_TAGS,
  noteDrafts,
  noteIdentity,
  noteQueues,
  resolveNoteConflict,
  sameNoteIdentity,
  type NoteQueue,
  type NoteResponse,
  type StoredNoteDraft,
} from './exerciseNoteQueue';
import './ExerciseExecutionNote.css';

type HistoryResult = components['schemas']['ExerciseNoteHistoryResult'];

function RecoveryDraft({
  userId,
  draftKey,
  data,
}: {
  userId: number;
  draftKey: string;
  data: StoredNoteDraft;
}) {
  const { confirm } = useFeedback();
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  return (
    <details
      className="exercise-execution-note"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="yfc-disclosure-summary">
        <span className="exercise-execution-note__summary">
          <strong>Несохранённый черновик</strong>
          <small>{data.exerciseTitle} · сохранён на устройстве</small>
        </span>
        <span className="exercise-execution-note__action">
          {open ? 'Скрыть' : 'Открыть'}
          <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} />
        </span>
      </summary>
      <div className="exercise-execution-note__content">
        <p>Черновик ещё не отправлен. Он останется на устройстве и не перенесётся автоматически.</p>
        {data.body && <p>{data.body}</p>}
        {data.tags.length ? (
          <p>
            {data.tags
              .map((value) => NOTE_TAGS.find((tag) => tag.value === value)?.label)
              .join(' · ')}
          </p>
        ) : null}
        <Button
          type="button"
          variant="secondary"
          onClick={async () => {
            if (
              !(await confirm({
                title: 'Удалить черновик?',
                message: 'Текст будет удалён с этого устройства.',
                confirmText: 'Удалить',
                danger: true,
              }))
            )
              return;
            if (!noteDrafts(userId).some((item) => item.key === draftKey)) return;
            removeStorage(draftKey);
            if (noteDrafts(userId).some((item) => item.key === draftKey))
              setError('Не удалось удалить черновик с устройства.');
            else window.dispatchEvent(new Event(NOTE_DRAFT_EVENT));
          }}
        >
          Удалить черновик с устройства
        </Button>
        {error && <p role="alert">{error}</p>}
      </div>
    </details>
  );
}

function RecoveryItem({
  userId,
  queueKey,
  data,
}: {
  userId: number;
  queueKey: string;
  data: NoteQueue;
}) {
  const { confirm } = useFeedback();
  const online = useOnlineStatus();
  const [error, setError] = useState<string | null>(null);
  const [server, setServer] = useState<HistoryResult | null>(null);
  const [working, setWorking] = useState(false);
  const [open, setOpen] = useState(false);
  const last = data.pending.at(-1);
  const hasVersionConflict = data.blocked === 'exercise_note_version_conflict';
  const pendingDeletion = last?.action === 'delete';
  if (!last) return null;

  async function compare() {
    if (!last) return;
    setWorking(true);
    try {
      const result = await api<NoteResponse | HistoryResult>(
        last.target === 'history'
          ? `/api/v1/workouts/exercise-notes/history/${last.note_id}`
          : `/api/v1/workouts/${data.workoutId}/exercise-notes/${data.occurrenceId}`,
        { cache: 'no-store' },
      );
      if (
        last.target !== 'history' &&
        (!('exercise_id' in result) || !sameNoteIdentity(last, result))
      ) {
        throw new Error('Упражнение изменилось.');
      }
      setServer(result);
      setError(null);
    } catch (reason) {
      setError(getUserFacingErrorMessage(reason, 'Не удалось загрузить сохранённую версию.'));
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
    if (!(await clearNoteQueue(queueKey, userId)))
      setError('Не удалось удалить изменения с устройства.');
  }

  return (
    <details
      className="exercise-execution-note"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="yfc-disclosure-summary">
        <span className="exercise-execution-note__summary">
          <strong>Неотправленная заметка</strong>
          <small>{data.exerciseTitle} · сохранена на устройстве</small>
        </span>
        <span className="exercise-execution-note__action">
          {open ? 'Скрыть' : 'Открыть'}
          <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} />
        </span>
      </summary>
      <div className="exercise-execution-note__content">
        <p>
          {hasVersionConflict
            ? 'Заметка изменилась на другом устройстве. Ваши изменения остались здесь.'
            : 'Упражнение или тренировка изменились. Текст не будет перенесён к другому упражнению.'}
        </p>
        {last.body && <p>{last.body}</p>}
        {last.tags.length ? (
          <p>
            {last.tags
              .map((value) => NOTE_TAGS.find((tag) => tag.value === value)?.label)
              .join(' · ')}
          </p>
        ) : null}
        {hasVersionConflict && (
          <Button
            type="button"
            variant="secondary"
            disabled={!online || working}
            onClick={() => void compare()}
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
            <Button
              type="button"
              disabled={working}
              onClick={async () => {
                if (
                  !(await resolveNoteConflict(queueKey, userId, server.version, {
                    body: last.body,
                    tags: last.tags,
                  }))
                ) {
                  setError('Не удалось сохранить изменение на устройстве.');
                }
              }}
            >
              {pendingDeletion ? 'Удалить сохранённую заметку' : 'Сохранить мой вариант'}
            </Button>
          </>
        )}
        <Button type="button" variant="secondary" onClick={() => void discard()}>
          Удалить изменения с устройства
        </Button>
        {error && <p role="alert">{error}</p>}
      </div>
    </details>
  );
}

export function ExerciseNoteRecovery({ userId, workout }: { userId: number; workout?: Workout }) {
  const [entries, setEntries] = useState(() => noteQueues(userId));
  const [drafts, setDrafts] = useState(() => noteDrafts(userId));
  useEffect(() => {
    const refresh = () => {
      setEntries(noteQueues(userId));
      setDrafts(noteDrafts(userId));
    };
    window.addEventListener(NOTE_QUEUE_EVENT, refresh);
    window.addEventListener(NOTE_DRAFT_EVENT, refresh);
    window.addEventListener('storage', refresh);
    refresh();
    return () => {
      window.removeEventListener(NOTE_QUEUE_EVENT, refresh);
      window.removeEventListener(NOTE_DRAFT_EVENT, refresh);
      window.removeEventListener('storage', refresh);
    };
  }, [userId]);
  const currentIds = new Set(workout?.exercises.map((item) => item.id));
  const recoverable = entries.filter(
    ({ data }) =>
      data.userId === userId &&
      (workout
        ? data.workoutId === workout.id &&
          data.pending.at(-1)?.target !== 'history' &&
          !currentIds.has(data.occurrenceId)
        : Boolean(data.blocked)),
  );
  const recoverableDrafts = drafts.filter(({ data }) => {
    if (data.userId !== userId) return false;
    if (!workout) return true;
    if (data.workoutId !== workout.id || data.note) return false;
    const exercise = workout.exercises.find((item) => item.id === data.occurrenceId);
    return (
      !exercise ||
      !data.identity ||
      !sameNoteIdentity(data.identity, noteIdentity(workout, exercise))
    );
  });
  if (!recoverable.length && !recoverableDrafts.length) return null;
  return (
    <section className="exercise-execution-note__recovery" aria-label="Неотправленные заметки">
      {recoverableDrafts.map(({ key, data }) => (
        <RecoveryDraft key={key} userId={userId} draftKey={key} data={data} />
      ))}
      {recoverable.map(({ key, data }) => (
        <RecoveryItem key={key} userId={userId} queueKey={key} data={data} />
      ))}
    </section>
  );
}
