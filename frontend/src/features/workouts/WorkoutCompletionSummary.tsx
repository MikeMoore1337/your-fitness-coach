import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { Workout } from '../../shared/api/types';
import { formatCalendarDate } from '../../shared/dateTime';
import { AppLink } from '../../shared/navigation/router';
import { Badge, Button } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useSemanticMotion } from '../../shared/ui/useSemanticMotion';
import { WorkoutFeedbackDisclosure } from './WorkoutFeedback';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';

export const workoutCompletionFeedbackLabels: Record<string, string> = {
  easier_than_expected: 'Легче ожидаемого',
  as_expected: 'Нормально',
  harder_than_expected: 'Тяжелее ожидаемого',
};

type CompletionFeedback = NonNullable<NonNullable<Workout['completion_summary']>['feedback']>;

const feedbackOptions = Object.entries(workoutCompletionFeedbackLabels) as Array<
  [CompletionFeedback, string]
>;
const NOTE_MAX_LENGTH = 500;

function plural(value: number, one: string, few: string, many: string): string {
  const mod10 = value % 10;
  const mod100 = value % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export function formatCompletionDuration(seconds: number | null | undefined): string {
  if (seconds == null) return 'Не зафиксировано';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return 'Меньше минуты';
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (!hours) return `${minutes} мин`;
  return remainingMinutes ? `${hours} ч ${remainingMinutes} мин` : `${hours} ч`;
}

function formatLoad(value: number): string {
  return `${Number.isInteger(value) ? value : value.toFixed(1)} кг`;
}

function formatDistance(value: number): string {
  return `${Number(value.toFixed(2))} км`;
}

function nextWorkoutText(workout: NonNullable<Workout['completion_summary']>['next_workout']) {
  if (!workout) {
    return 'Дальше — восстановление. Ближайшая тренировка пока не запланирована.';
  }
  const date = formatCalendarDate(workout.scheduled_date, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
  const time = workout.scheduled_time ? ` в ${workout.scheduled_time.slice(0, 5)}` : '';
  return `Следующая тренировка — ${date}${time}: ${workout.title}. До неё — восстановление.`;
}

export function WorkoutCompletionSummary({
  workout,
  onReturnToday,
}: {
  workout: Workout;
  onReturnToday?: () => void;
}) {
  const queryClient = useQueryClient();
  const summary = workout.completion_summary;
  const fallbackCompletedSets = workout.exercises.reduce(
    (total, exercise) => total + exercise.sets.filter((set) => set.is_completed).length,
    0,
  );
  const hasCardio = workout.exercises.some((exercise) => exercise.metric_type === 'cardio');
  const [feedback, setFeedback] = useState<CompletionFeedback | null>(summary?.feedback ?? null);
  const [note, setNote] = useState(summary?.note ?? '');
  const [saved, setSaved] = useState({
    feedback: summary?.feedback ?? null,
    note: summary?.note ?? '',
  });
  const changed = feedback !== saved.feedback || note.trim() !== saved.note;
  const motion = useSemanticMotion<HTMLElement>(`workout-completion:${workout.id}`);

  useEffect(() => {
    trackProductEvent(
      { name: 'workout_completion_summary_viewed', surface: productEventSurface() },
      { dedupe: 'session', dedupeKey: `workout:${workout.id}` },
    );
  }, [workout.id]);
  const saveFeedback = useMutation({
    mutationFn: () =>
      api<Workout>(`/api/v1/workouts/${workout.id}/completion-feedback`, {
        method: 'PUT',
        body: { feedback, note: note.trim() || null },
      }),
    onSuccess: (updatedWorkout) => {
      queryClient.setQueryData(['workout', 'today'], updatedWorkout);
      setSaved({
        feedback: updatedWorkout.completion_summary?.feedback ?? null,
        note: updatedWorkout.completion_summary?.note ?? '',
      });
    },
  });

  const updateFeedback = (value: CompletionFeedback) => {
    setFeedback((current) => (current === value ? null : value));
    saveFeedback.reset();
  };

  return (
    <section
      className="workout-completion"
      id={motion.elementId}
      aria-labelledby="workout-completion-title"
      data-motion-phase={motion.motionPhase}
      data-motion-revision={motion.motionRevision}
      onAnimationEnd={motion.onMotionAnimationEnd}
    >
      <header className="workout-completion__hero">
        <span className="workout-completion__check" aria-hidden="true">
          <Icon name="week-strength" style={{ width: 110, height: 110 }} />
        </span>
        <div>
          <Badge tone="success">Результат сохранён</Badge>
          <h2 id="workout-completion-title">Тренировка завершена</h2>
          <p>{workout.title}</p>
        </div>
      </header>

      <dl className="workout-completion__facts" aria-label="Ключевые факты тренировки">
        <div>
          <dt>Длительность</dt>
          <dd>{formatCompletionDuration(summary?.duration_seconds)}</dd>
        </div>
        <div>
          <dt>Упражнений</dt>
          <dd>{summary?.performed_exercises ?? workout.exercises.length}</dd>
        </div>
        <div>
          <dt>{hasCardio ? 'Этапов' : 'Подходов'}</dt>
          <dd>{summary?.completed_sets ?? fallbackCompletedSets}</dd>
        </div>
      </dl>

      <section className="workout-completion__next" aria-labelledby="workout-next-title">
        <span className="eyebrow">Следующий шаг</span>
        <h3 id="workout-next-title">План продолжается</h3>
        <p>{nextWorkoutText(summary?.next_workout ?? null)}</p>
        <div className="workout-completion__actions">
          {onReturnToday ? (
            <Button type="button" onClick={onReturnToday}>
              Вернуться в Сегодня
            </Button>
          ) : (
            <AppLink className="button-link" to="/app?section=today">
              Вернуться в Сегодня
            </AppLink>
          )}
          <AppLink className="button-link secondary-link" to="/app?section=progress">
            Посмотреть Прогресс
          </AppLink>
        </div>
      </section>

      {!!summary?.personal_records.length && (
        <section className="workout-completion__records" aria-labelledby="workout-records-title">
          <span className="eyebrow">Личные результаты</span>
          <h3 id="workout-records-title">Новый лучший результат</h3>
          <ul>
            {summary.personal_records.map((record) => (
              <li key={record.exercise_id}>
                <strong>{record.exercise_title}</strong>
                <span>
                  {[
                    record.kinds.includes('max_load') && record.max_load_kg != null
                      ? `максимальный вес ${formatLoad(record.max_load_kg)}`
                      : null,
                    record.kinds.includes('best_set_volume') && record.best_set_volume_kg != null
                      ? `лучший подход ${formatLoad(record.best_set_volume_kg)} (вес × повторы)`
                      : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {!!summary?.exercises.length && (
        <details className="workout-completion__results">
          <summary>Записанные результаты</summary>
          <ul>
            {summary.exercises.map((exercise) => (
              <li key={exercise.workout_exercise_id}>
                <strong>{exercise.exercise_title}</strong>
                {exercise.metric_type === 'cardio' ? (
                  <span>
                    {[
                      exercise.duration_minutes != null ? `${exercise.duration_minutes} мин` : null,
                      exercise.distance_km != null ? formatDistance(exercise.distance_km) : null,
                      exercise.average_heart_rate_bpm != null
                        ? `средний пульс ${exercise.average_heart_rate_bpm}`
                        : null,
                      exercise.heart_rate_zone != null ? `зона ${exercise.heart_rate_zone}` : null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                ) : (
                  <span>
                    {exercise.completed_sets}{' '}
                    {plural(exercise.completed_sets, 'подход', 'подхода', 'подходов')}
                    {exercise.reps_total != null ? ` · ${exercise.reps_total} повторов` : ''}
                    {exercise.max_load_kg != null
                      ? ` · вес до ${formatLoad(exercise.max_load_kg)}`
                      : ''}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      <form
        className="workout-completion__feedback"
        onSubmit={(event) => {
          event.preventDefault();
          if (changed && !saveFeedback.isPending) saveFeedback.mutate();
        }}
      >
        <fieldset>
          <legend>
            Как ощущалась тренировка? <span>Необязательно</span>
          </legend>
          <div className="workout-completion__feedback-options">
            {feedbackOptions.map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={feedback === value}
                onClick={() => updateFeedback(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </fieldset>
        <label htmlFor={`workout-completion-note-${workout.id}`}>Заметка</label>
        <textarea
          id={`workout-completion-note-${workout.id}`}
          value={note}
          rows={3}
          maxLength={NOTE_MAX_LENGTH}
          placeholder="Что стоит учесть в следующий раз"
          onChange={(event) => {
            setNote(event.target.value);
            saveFeedback.reset();
          }}
        />
        <div className="workout-completion__feedback-footer">
          <span aria-live="polite">
            {saveFeedback.isSuccess && !changed
              ? 'Обратная связь сохранена'
              : `${note.length} из ${NOTE_MAX_LENGTH}`}
          </span>
          <Button type="submit" disabled={!changed || saveFeedback.isPending}>
            {saveFeedback.isPending ? 'Сохраняем…' : 'Сохранить'}
          </Button>
        </div>
        {saveFeedback.error && (
          <p className="workout-completion__error" role="alert">
            {(saveFeedback.error as Error).message} Введённый текст сохранён в форме.
          </p>
        )}
      </form>

      <WorkoutFeedbackDisclosure
        workoutId={workout.id}
        workoutTitle={workout.title}
        workoutDate={workout.scheduled_date}
        exercises={workout.exercises.map((exercise) => ({
          workoutExerciseId: exercise.id,
          title: exercise.exercise_title,
        }))}
        viewer="client"
      />
    </section>
  );
}
