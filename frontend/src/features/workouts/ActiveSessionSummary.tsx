import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { ExerciseHistory, Workout } from '../../shared/api/types';
import { Button } from '../../shared/ui/common';
import { useOnlineStatus } from '../../shared/ui/OnlineStatus';
import type { ActiveWorkoutMutation } from './activeWorkoutQueue';

type WorkoutExercise = Workout['exercises'][number];
type WorkoutSet = WorkoutExercise['sets'][number];

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '');
}

function formatSetResult(
  reps: number | null | undefined,
  weight: number | null | undefined,
): string | null {
  if (reps == null && weight == null) return null;
  if (weight == null) return `${reps} повт.`;
  if (reps == null) return `${formatNumber(weight)} кг`;
  return `${formatNumber(weight)} кг × ${reps}`;
}

function currentRir(set: WorkoutSet, pending?: ActiveWorkoutMutation): string | null {
  return pending ? (pending.values.rir ?? null) : (set.rir ?? null);
}

function targetLabel(exercise: WorkoutExercise): string {
  if (exercise.metric_type === 'cardio') {
    return exercise.prescribed_duration_minutes
      ? `${exercise.prescribed_duration_minutes} мин`
      : 'Длительность по факту';
  }
  return `${exercise.prescribed_sets} × ${exercise.prescribed_reps || 'по плану'}`;
}

export function ActiveSessionSummary({
  exercise,
  currentSet,
  pending,
  started,
  onFocusCurrentSet,
  guidance,
  setupMemory,
  adaptation,
}: {
  exercise: WorkoutExercise;
  currentSet: WorkoutSet;
  pending?: ActiveWorkoutMutation;
  started: boolean;
  onFocusCurrentSet: () => void;
  guidance?: ReactNode;
  setupMemory?: ReactNode;
  adaptation?: ReactNode;
}) {
  const online = useOnlineStatus();
  const history = useQuery({
    queryKey: ['workout', 'exercise-history', exercise.exercise_id],
    queryFn: () =>
      api<ExerciseHistory>(`/api/v1/programs/exercises/${exercise.exercise_id}/history`),
    enabled: started && exercise.metric_type === 'strength',
    retry: false,
    staleTime: 60_000,
  });
  const session = history.data?.recent_sessions?.[0];
  const previousSet = session?.sets.find(
    (set) => set.pr_eligible && (set.load_kg != null || set.reps != null),
  );
  const previousResult = previousSet
    ? formatSetResult(previousSet.reps, previousSet.load_kg)
    : null;
  const rir = currentRir(currentSet, pending);
  const isCardio = exercise.metric_type === 'cardio';

  let previousCopy = 'История появится после старта';
  let previousDetail = 'Сопоставимый результат';
  if (started && !isCardio) {
    if (history.isPending) {
      previousCopy = 'Загрузка…';
    } else if (previousResult) {
      previousCopy = previousResult;
      previousDetail = 'Последняя сопоставимая тренировка';
    } else if (history.isError) {
      previousCopy = online ? 'Не удалось загрузить' : 'Недоступно офлайн';
      previousDetail = 'Снимок тренировки не содержит историю';
    } else {
      previousCopy = 'Нет результата';
      previousDetail = 'Сопоставимая тренировка ещё не записана';
    }
  }

  return (
    <section
      className="active-session-summary"
      data-testid={`active-session-summary-${exercise.id}`}
      aria-labelledby={`active-session-summary-${exercise.id}-title`}
    >
      <header className="active-session-summary__header">
        <div>
          <span className="active-session-summary__eyebrow">Следующее действие</span>
          <h4 id={`active-session-summary-${exercise.id}-title`}>Что делать сейчас</h4>
        </div>
        <span className={`active-session-summary__state${online ? '' : ' is-offline'}`}>
          {online ? 'Актуальные данные' : 'Офлайн-снимок'}
        </span>
      </header>

      <div className="active-session-summary__primary">
        <div>
          <span>{isCardio ? 'Следующий этап' : 'Следующий подход'}</span>
          <strong>
            {exercise.exercise_title}
            {!isCardio && ` · подход ${currentSet.set_number}`}
          </strong>
          <small>
            {started
              ? isCardio
                ? 'Запишите длительность и дистанцию, затем завершите этап.'
                : 'Запишите вес и повторы, затем отметьте подход.'
              : 'После старта этот этап станет доступен для записи.'}
          </small>
        </div>
        {started && (
          <Button type="button" variant="secondary" onClick={onFocusCurrentSet}>
            К текущему подходу
          </Button>
        )}
      </div>

      <div className="active-session-summary__facts">
        <div>
          <span>План</span>
          <strong>{targetLabel(exercise)}</strong>
          <small>Серверное назначение</small>
        </div>
        <div>
          <span>Предыдущий результат</span>
          <strong>{previousCopy}</strong>
          <small>{previousDetail}</small>
        </div>
        <div>
          <span>RIR</span>
          <strong>{isCardio ? 'Не применяется' : (rir ?? 'Не записан')}</strong>
          <small>{isCardio ? 'Для кардио не используется' : 'Введите после подхода'}</small>
        </div>
        <div>
          <span>Отдых</span>
          <strong>
            {exercise.rest_seconds > 0 ? `${exercise.rest_seconds} сек` : 'Без отдыха'}
          </strong>
          <small>Таймер запускается после сохранения</small>
        </div>
      </div>

      <div className="active-session-summary__guidance">
        <div className="active-session-summary__section-label">
          <span>Прогрессия</span>
          <small>{guidance ? 'Детерминированная подсказка' : 'Без автоматического решения'}</small>
        </div>
        {guidance ?? (
          <p className="active-session-summary__unavailable" role="status">
            {online
              ? 'Для этого этапа отдельная подсказка не сформирована.'
              : 'Подсказка прогрессии недоступна в офлайн-снимке.'}
          </p>
        )}
      </div>

      {setupMemory}
      {adaptation && <div className="active-session-summary__adaptation">{adaptation}</div>}
    </section>
  );
}
