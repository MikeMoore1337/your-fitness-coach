import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '../../shared/api/client';
import type { WorkoutComment } from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import {
  Badge,
  DisclosureIcon,
  EmptyState,
  ErrorState,
  LoadingState,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { formatCalendarDate } from '../../shared/dateTime';
import { useOptionalAuth } from '../../app/AuthProvider';

export const WORKOUT_COMMENT_MAX_LENGTH = 2000;

function newCommentIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `comment-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export interface WorkoutFeedbackExercise {
  workoutExerciseId: number;
  title: string;
}

interface WorkoutFeedbackProps {
  workoutId: number;
  workoutTitle: string;
  workoutDate: string;
  exercises: WorkoutFeedbackExercise[];
  viewer: 'client' | 'trainer';
  clientId?: number;
  clientName?: string;
  canCompose?: boolean;
  focusedCommentId?: number | null;
  focusedExerciseId?: number | null;
}

function formatWorkoutDate(value: string): string {
  return formatCalendarDate(value, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

function formatCommentTime(value: string): string {
  return new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function isPermissionLoss(reason: unknown): boolean {
  return reason instanceof ApiError && [403, 404, 409].includes(reason.status);
}

function sortedComments(comments: WorkoutComment[]): WorkoutComment[] {
  return [...comments].sort(
    (left, right) =>
      new Date(left.created_at).getTime() - new Date(right.created_at).getTime() ||
      left.id - right.id,
  );
}

export function WorkoutFeedback({
  workoutId,
  workoutTitle,
  workoutDate,
  exercises,
  viewer,
  clientId,
  clientName,
  canCompose = false,
  focusedCommentId,
  focusedExerciseId,
}: WorkoutFeedbackProps) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const [body, setBody] = useState('');
  const [draftIdempotencyKey, setDraftIdempotencyKey] = useState(newCommentIdempotencyKey);
  const [workoutExerciseId, setWorkoutExerciseId] = useState<number | null>(
    focusedExerciseId ?? null,
  );
  const [editing, setEditing] = useState<{ id: number; body: string } | null>(null);
  const [permissionLost, setPermissionLost] = useState(false);
  const queryKey =
    viewer === 'trainer' && clientId != null
      ? queryKeys.workoutComments.trainer(clientId, workoutId)
      : queryKeys.workoutComments.client(workoutId);
  const path =
    viewer === 'trainer' && clientId != null
      ? `/api/v1/coach/clients/${clientId}/workouts/${workoutId}/comments`
      : `/api/v1/workouts/${workoutId}/comments`;
  const comments = useQuery({
    queryKey,
    queryFn: () => api<WorkoutComment[]>(path),
    select: sortedComments,
  });
  const exerciseTitles = useMemo(
    () => new Map(exercises.map((exercise) => [exercise.workoutExerciseId, exercise.title])),
    [exercises],
  );
  const canWrite = viewer === 'trainer' && clientId != null && canCompose && !permissionLost;
  const fieldIdPrefix = `workout-feedback-${viewer}-${clientId ?? 'self'}-${workoutId}`;

  useEffect(() => {
    if (!focusedCommentId || !comments.data?.some((comment) => comment.id === focusedCommentId)) {
      return;
    }
    const comment = document.getElementById(`workout-comment-${focusedCommentId}`);
    comment?.focus({ preventScroll: true });
    comment?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
  }, [comments.data, focusedCommentId]);

  const createComment = useMutation({
    mutationFn: ({
      draft,
      idempotencyKey,
    }: {
      draft: { body: string; workout_exercise_id: number | null };
      idempotencyKey: string;
    }) =>
      api<WorkoutComment>(path, {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: draft,
      }),
    onSuccess: (created) => {
      if (viewer === 'trainer') {
        trackProductEvent({ name: 'trainer_comment_added', surface: productEventSurface() });
      }
      queryClient.setQueryData<WorkoutComment[]>(queryKey, (current = []) =>
        sortedComments(
          current.some((comment) => comment.id === created.id)
            ? current.map((comment) => (comment.id === created.id ? created : comment))
            : [...current, created],
        ),
      );
      setBody('');
      setWorkoutExerciseId(null);
      setDraftIdempotencyKey(newCommentIdempotencyKey());
      toast('Комментарий отправлен');
    },
    onError: (reason) => {
      if (isPermissionLoss(reason)) {
        setPermissionLost(true);
        setEditing(null);
      }
    },
  });
  const editComment = useMutation({
    mutationFn: ({ id, nextBody }: { id: number; nextBody: string }) =>
      api<WorkoutComment>(`${path}/${id}`, { method: 'PATCH', body: { body: nextBody } }),
    onSuccess: (saved) => {
      queryClient.setQueryData<WorkoutComment[]>(queryKey, (current = []) =>
        sortedComments(current.map((comment) => (comment.id === saved.id ? saved : comment))),
      );
      setEditing(null);
      toast('Комментарий изменён');
    },
    onError: (reason) => {
      if (isPermissionLoss(reason)) {
        setPermissionLost(true);
        setEditing(null);
      }
    },
  });

  const normalizedBody = body.trim();
  const selectedExerciseTitle = workoutExerciseId
    ? exerciseTitles.get(workoutExerciseId)
    : undefined;

  return (
    <section
      className="workout-feedback"
      aria-label={viewer === 'trainer' ? 'Комментарий тренера' : 'Обратная связь тренера'}
    >
      <header className="workout-feedback__header">
        <div>
          <span className="eyebrow">Обратная связь по тренировке</span>
          <h4>{workoutTitle}</h4>
          <p>
            {clientName ? `${clientName} · ` : ''}
            {formatWorkoutDate(workoutDate)}
          </p>
        </div>
        {comments.data && comments.data.length > 0 && <Badge>{comments.data.length} комм.</Badge>}
      </header>

      {viewer === 'trainer' && (
        <div className="workout-feedback__composer">
          {canWrite ? (
            <form
              className="stack"
              onSubmit={(event) => {
                event.preventDefault();
                if (!normalizedBody || createComment.isPending) return;
                createComment.mutate({
                  draft: {
                    body: normalizedBody,
                    workout_exercise_id: workoutExerciseId,
                  },
                  idempotencyKey: draftIdempotencyKey,
                });
              }}
            >
              <div className="field">
                <label htmlFor={`${fieldIdPrefix}-context`}>Контекст комментария</label>
                <select
                  id={`${fieldIdPrefix}-context`}
                  value={workoutExerciseId ?? ''}
                  onChange={(event) => {
                    setWorkoutExerciseId(event.target.value ? Number(event.target.value) : null);
                    setDraftIdempotencyKey(newCommentIdempotencyKey());
                    createComment.reset();
                  }}
                >
                  <option value="">Вся тренировка</option>
                  {exercises.map((exercise) => (
                    <option value={exercise.workoutExerciseId} key={exercise.workoutExerciseId}>
                      Упражнение: {exercise.title}
                    </option>
                  ))}
                </select>
                <small className="field-hint">
                  {selectedExerciseTitle
                    ? `Комментарий будет показан рядом с упражнением «${selectedExerciseTitle}».`
                    : 'Комментарий относится ко всей тренировке.'}
                </small>
              </div>
              <div className="field">
                <label htmlFor={`${fieldIdPrefix}-body`}>Комментарий</label>
                <textarea
                  id={`${fieldIdPrefix}-body`}
                  value={body}
                  maxLength={WORKOUT_COMMENT_MAX_LENGTH}
                  rows={4}
                  placeholder="Напишите короткую, конкретную обратную связь"
                  onChange={(event) => {
                    setBody(event.target.value);
                    setDraftIdempotencyKey(newCommentIdempotencyKey());
                    createComment.reset();
                  }}
                  required
                />
                <small className="workout-feedback__limit">
                  <span>Только текст, без вложений</span>
                  <span>
                    {body.length} из {WORKOUT_COMMENT_MAX_LENGTH}
                  </span>
                </small>
              </div>
              {createComment.error && (
                <p className="workout-feedback__error" role="alert">
                  {permissionLost
                    ? 'Связь с клиентом завершена. Новые комментарии недоступны; загруженная история сохранена.'
                    : (createComment.error as Error).message}
                </p>
              )}
              {!permissionLost && (
                <button type="submit" disabled={!normalizedBody || createComment.isPending}>
                  {createComment.isPending
                    ? 'Отправляем…'
                    : createComment.error
                      ? 'Повторить отправку'
                      : 'Отправить комментарий'}
                </button>
              )}
            </form>
          ) : (
            <div className="workout-feedback__access" role="status">
              <strong>Новые комментарии недоступны</strong>
              <span>
                {permissionLost
                  ? 'Связь с клиентом завершена. Ниже остаётся история, которую разрешает backend.'
                  : 'Оставлять и редактировать комментарии можно только при активной связи с клиентом.'}
              </span>
            </div>
          )}
        </div>
      )}

      <div className="workout-feedback__history">
        <h5>История обратной связи</h5>
        {comments.isLoading ? (
          <LoadingState label="Загружаем комментарии…" />
        ) : comments.error ? (
          <ErrorState
            message={(comments.error as Error).message}
            retry={() => void comments.refetch()}
          />
        ) : !comments.data?.length ? (
          <EmptyState
            title="Комментариев пока нет"
            text={
              viewer === 'trainer'
                ? 'Первый комментарий появится здесь и останется в контексте этой тренировки.'
                : 'Тренер пока не оставлял обратную связь к этой тренировке.'
            }
          />
        ) : (
          <ol className="workout-feedback__timeline">
            {comments.data.map((comment) => {
              const exerciseTitle = comment.workout_exercise_id
                ? exerciseTitles.get(comment.workout_exercise_id)
                : null;
              const edited = Boolean(comment.updated_at);
              const isEditing = editing?.id === comment.id;
              return (
                <li
                  id={`workout-comment-${comment.id}`}
                  className={comment.id === focusedCommentId ? 'is-focused' : undefined}
                  key={comment.id}
                  tabIndex={-1}
                >
                  <div className="workout-feedback__meta">
                    <strong>{viewer === 'trainer' ? 'Вы' : 'Тренер'}</strong>
                    <time dateTime={comment.created_at}>
                      {formatCommentTime(comment.created_at)}
                    </time>
                    {edited && <span>Изменено</span>}
                  </div>
                  <span className="workout-feedback__context">
                    {comment.workout_exercise_id
                      ? `Упражнение · ${exerciseTitle ?? 'упражнение этой тренировки'}`
                      : 'Вся тренировка'}
                  </span>
                  {isEditing ? (
                    <form
                      className="workout-feedback__edit"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const nextBody = editing.body.trim();
                        if (!nextBody || editComment.isPending) return;
                        editComment.mutate({ id: comment.id, nextBody });
                      }}
                    >
                      <div className="field">
                        <label className="sr-only" htmlFor={`${fieldIdPrefix}-edit-${comment.id}`}>
                          Изменить комментарий
                        </label>
                        <textarea
                          id={`${fieldIdPrefix}-edit-${comment.id}`}
                          value={editing.body}
                          maxLength={WORKOUT_COMMENT_MAX_LENGTH}
                          rows={3}
                          onChange={(event) => {
                            setEditing({ id: comment.id, body: event.target.value });
                            editComment.reset();
                          }}
                          required
                        />
                      </div>
                      {editComment.error && (
                        <p className="workout-feedback__error" role="alert">
                          {(editComment.error as Error).message}
                        </p>
                      )}
                      <div className="workout-feedback__edit-actions">
                        <button
                          type="submit"
                          disabled={!editing.body.trim() || editComment.isPending || permissionLost}
                        >
                          {editComment.isPending ? 'Сохраняем…' : 'Сохранить'}
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          disabled={editComment.isPending}
                          onClick={() => {
                            setEditing(null);
                            editComment.reset();
                          }}
                        >
                          Отмена
                        </button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <p className="workout-feedback__body">{comment.body}</p>
                      {viewer === 'trainer' && canWrite && (
                        <button
                          type="button"
                          className="text-button workout-feedback__edit-trigger"
                          onClick={() => {
                            setEditing({ id: comment.id, body: comment.body });
                            editComment.reset();
                          }}
                        >
                          Изменить
                        </button>
                      )}
                    </>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </section>
  );
}

export function WorkoutFeedbackDisclosure({
  defaultOpen = false,
  ...feedbackProps
}: WorkoutFeedbackProps & { defaultOpen?: boolean }) {
  const auth = useOptionalAuth();
  const [open, setOpen] = useState(defaultOpen || Boolean(feedbackProps.focusedCommentId));

  if (auth && feedbackProps.viewer === 'client' && !auth.user?.trainer) return null;

  return (
    <details
      className="workout-feedback-disclosure"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <span>
          <strong>
            {feedbackProps.viewer === 'trainer' ? 'Комментарий тренера' : 'Обратная связь тренера'}
          </strong>
          <small>Только в контексте этой тренировки</small>
        </span>
        <DisclosureIcon />
      </summary>
      {open && <WorkoutFeedback {...feedbackProps} />}
    </details>
  );
}
