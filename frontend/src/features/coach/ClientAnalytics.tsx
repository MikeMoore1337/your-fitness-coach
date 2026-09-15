import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { WorkoutProgress, WorkoutTimelineItem } from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { workoutStatusLabel } from '../../shared/statusLabels';
import {
  Badge,
  DisclosureIcon,
  EmptyState,
  ErrorState,
  LoadingState,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { DateInput, TimeInput } from '../../shared/ui/PickerInput';
import { WorkoutFeedbackDisclosure } from '../workouts/WorkoutFeedback';
import { workoutCompletionFeedbackLabels } from '../workouts/WorkoutCompletionSummary';

function formatDate(value: string): string {
  return new Date(`${value}T12:00:00`).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

function CoachScheduleForm({
  workout,
  pending,
  onSave,
}: {
  workout: WorkoutTimelineItem;
  pending: boolean;
  onSave(date: string, time: string): void;
}) {
  const [date, setDate] = useState(workout.scheduled_date);
  const [time, setTime] = useState(workout.scheduled_time?.slice(0, 5) ?? '');
  return (
    <form
      className="toolbar wrap"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(date, time);
      }}
    >
      <label className="field compact-field">
        <span>Дата</span>
        <DateInput
          value={date}
          min={new Date().toISOString().slice(0, 10)}
          onChange={(event) => setDate(event.target.value)}
          required
        />
      </label>
      <label className="field compact-field">
        <span>Время</span>
        <TimeInput value={time} onChange={(event) => setTime(event.target.value)} />
      </label>
      <button
        type="submit"
        className="secondary"
        disabled={
          pending ||
          (date === workout.scheduled_date && time === (workout.scheduled_time?.slice(0, 5) ?? ''))
        }
      >
        {pending ? 'Сохраняем…' : 'Изменить дату и время'}
      </button>
    </form>
  );
}

export function ClientAnalytics({
  clientId,
  clientName,
  canComment = true,
  canSchedule = true,
}: {
  clientId: number;
  clientName: string;
  canComment?: boolean;
  canSchedule?: boolean;
}) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const progress = useQuery({
    queryKey: queryKeys.trainer.clientAnalytics(clientId),
    queryFn: () => api<WorkoutProgress>(`/api/v1/coach/clients/${clientId}/analytics`),
  });
  const timeline = useQuery({
    queryKey: ['coach', 'client', clientId, 'workouts'],
    queryFn: () =>
      api<WorkoutTimelineItem[]>(`/api/v1/coach/clients/${clientId}/workouts?limit=30`),
  });
  const scheduleMutation = useMutation({
    mutationFn: ({ workoutId, date, time }: { workoutId: number; date: string; time: string }) =>
      api(`/api/v1/coach/clients/${clientId}/workouts/${workoutId}/schedule`, {
        method: 'PATCH',
        body: { scheduled_date: date, scheduled_time: time || null },
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['coach', 'client', clientId, 'workouts'] }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clientAnalytics(clientId) }),
      ]);
      toast('Дата и время тренировки изменены');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  return (
    <div className="stack">
      {progress.isLoading ? (
        <LoadingState label="Считаем показатели…" />
      ) : progress.error ? (
        <ErrorState
          message={(progress.error as Error).message}
          retry={() => void progress.refetch()}
        />
      ) : progress.data ? (
        <>
          <div className="metric-grid">
            <div className="metric">
              <span>Соблюдение плана</span>
              <strong>{progress.data.adherence_percent}%</strong>
            </div>
            <div className="metric">
              <span>Завершено</span>
              <strong>{progress.data.workouts_completed}</strong>
            </div>
            <div className="metric">
              <span>Серия</span>
              <strong>{progress.data.current_streak}</strong>
            </div>
            <div className="metric">
              <span>Вес</span>
              <strong>
                {progress.data.weight_change_kg == null
                  ? '—'
                  : `${progress.data.weight_change_kg > 0 ? '+' : ''}${progress.data.weight_change_kg} кг`}
              </strong>
            </div>
          </div>
          {(progress.data.workouts_skipped > 0 || progress.data.workouts_missed > 0) && (
            <p className="muted">
              Пропущено: {progress.data.workouts_skipped}; просрочено:{' '}
              {progress.data.workouts_missed}.
            </p>
          )}
          {!!progress.data.personal_records.length && (
            <div>
              <h3>Лучшие результаты</h3>
              <div className="list-grid top-gap">
                {progress.data.personal_records.slice(0, 5).map((record) => (
                  <div className="list-row" key={record.exercise_id}>
                    <div>
                      <strong>{record.exercise_title}</strong>
                      <p className="muted">{formatDate(record.last_performed_on)}</p>
                    </div>
                    <strong>
                      {record.max_weight_kg == null ? '—' : `${record.max_weight_kg} кг`}
                    </strong>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : null}

      <div>
        <h3>Лента тренировок</h3>
        {timeline.isLoading ? (
          <LoadingState />
        ) : timeline.error ? (
          <ErrorState
            message={(timeline.error as Error).message}
            retry={() => void timeline.refetch()}
          />
        ) : !timeline.data?.length ? (
          <EmptyState title="Тренировок пока нет" />
        ) : (
          <div className="list-grid top-gap">
            {timeline.data.map((workout) => (
              <details className="card compact-disclosure" key={workout.id}>
                <summary>
                  <span>
                    <strong>{workout.title}</strong>
                    <small>
                      {formatDate(workout.scheduled_date)}
                      {workout.scheduled_time
                        ? ` в ${workout.scheduled_time.slice(0, 5)}`
                        : ''} · {workout.completed_sets} подх. · {Math.round(workout.volume_kg)} кг
                    </small>
                  </span>
                  <Badge>{workoutStatusLabel(workout.status)}</Badge>
                  <DisclosureIcon />
                </summary>
                <div className="stack top-gap">
                  {workout.status === 'planned' && canSchedule && (
                    <CoachScheduleForm
                      workout={workout}
                      pending={
                        scheduleMutation.isPending &&
                        scheduleMutation.variables?.workoutId === workout.id
                      }
                      onSave={(date, time) =>
                        scheduleMutation.mutate({ workoutId: workout.id, date, time })
                      }
                    />
                  )}
                  {!workout.exercises.length ? (
                    <p className="muted">Упражнения не добавлены.</p>
                  ) : (
                    workout.exercises.map((exercise) => (
                      <div className="list-row" key={exercise.workout_exercise_id}>
                        <div className="list-row__main">
                          <strong>{exercise.exercise_title}</strong>
                          {exercise.notes && <span className="muted">{exercise.notes}</span>}
                          <span className="muted">
                            {exercise.sets
                              .filter((set) => set.is_completed)
                              .map(
                                (set) => `${set.actual_weight ?? 0} кг × ${set.actual_reps ?? 0}`,
                              )
                              .join(' · ') || 'Нет выполненных подходов'}
                          </span>
                        </div>
                      </div>
                    ))
                  )}
                  {(workout.completion_feedback || workout.completion_note) && (
                    <div className="workout-completion-context">
                      {workout.completion_feedback && (
                        <strong>
                          Самооценка клиента:{' '}
                          {workoutCompletionFeedbackLabels[workout.completion_feedback]}
                        </strong>
                      )}
                      {workout.completion_note && <p>{workout.completion_note}</p>}
                    </div>
                  )}
                  <WorkoutFeedbackDisclosure
                    workoutId={workout.id}
                    workoutTitle={workout.title}
                    workoutDate={workout.scheduled_date}
                    exercises={workout.exercises.map((exercise) => ({
                      workoutExerciseId: exercise.workout_exercise_id,
                      title: exercise.exercise_title,
                    }))}
                    viewer="trainer"
                    clientId={clientId}
                    clientName={clientName}
                    canCompose={canComment}
                  />
                </div>
              </details>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
