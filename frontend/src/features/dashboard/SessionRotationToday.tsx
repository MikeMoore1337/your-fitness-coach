import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, getUserFacingErrorMessage } from '../../shared/api/client';
import type { ApiSchemas, Workout } from '../../shared/api/types';
import { AppLink } from '../../shared/navigation/router';
import { Badge, Button, DisclosureIcon, Field, Input, Select } from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useOnlineStatus } from '../../shared/ui/OnlineStatus';
import { createWorkoutMutationId } from '../workouts/activeWorkoutQueue';
import '../programs/SessionRotation.css';

type RotationState = ApiSchemas['SessionRotationStateResponse'];
type RotationPlan = ApiSchemas['SessionRotationPlanResponse'];
type Action = 'start' | 'skip';

const pluralRules = new Intl.PluralRules('ru');

function countLabel(value: number, one: string, few: string, many: string): string {
  const form = pluralRules.select(value);
  return `${value} ${form === 'one' ? one : form === 'few' ? few : many}`;
}

export function SessionRotationToday({
  state,
  refreshing,
  pendingLocalChanges,
  onStarted,
  onResume,
}: {
  state: RotationState;
  refreshing: boolean;
  pendingLocalChanges: boolean;
  onStarted(workout: Workout): void;
  onResume(): void;
}) {
  const online = useOnlineStatus();
  const { confirm } = useFeedback();
  const queryClient = useQueryClient();
  const [week, setWeek] = useState('');
  const [otherDay, setOtherDay] = useState('');
  const [showOther, setShowOther] = useState(false);
  const [extension, setExtension] = useState('');
  const [plan, setPlan] = useState<RotationPlan | null>(null);
  const [error, setError] = useState('');
  const current = state.current;
  const chosenDay = showOther ? Number(otherDay) : current?.day_number;
  const defaultWeek = showOther
    ? state.days?.find((day) => day.day_number === chosenDay)?.default_plan_week
    : state.default_plan_week;
  const selectedWeek = defaultWeek ?? Number(week);
  const validWeek =
    Number.isInteger(selectedWeek) &&
    selectedWeek > 0 &&
    selectedWeek <= (state.duration_weeks ?? 0);
  const fail = async (reason: unknown) => {
    setPlan(null);
    if (reason instanceof ApiError && reason.status === 409) {
      setError('Очередь или программа изменились. Данные обновлены; проверьте выбор ещё раз.');
      await queryClient.invalidateQueries({ queryKey: ['workout', 'session-rotation'] });
      return;
    }
    setError(getUserFacingErrorMessage(reason));
  };
  const refreshWorkouts = async () => {
    await queryClient.invalidateQueries({ queryKey: ['workout'] });
  };
  const planMutation = useMutation({
    mutationFn: () =>
      api<RotationPlan>(
        `/api/v1/workouts/session-rotation/plan?day_number=${chosenDay}&week_number=${selectedWeek}`,
        { cache: 'no-store' },
      ),
    onSuccess: (result) => {
      setPlan(result);
      setError('');
    },
    onError: fail,
  });
  const sessionMutation = useMutation({
    mutationFn: async ({ action, day }: { action: Action; day: number }) => {
      const result = await api<Workout | RotationState>(
        `/api/v1/workouts/session-rotation/${action}`,
        {
          method: 'POST',
          body: {
            expected_cursor: state.cursor,
            expected_day_number: day,
            mutation_id: createWorkoutMutationId(),
            plan_week_number: selectedWeek,
            out_of_order: showOther,
          },
        },
      );
      return { action, result };
    },
    onSuccess: async ({ action, result }) => {
      setError('');
      setPlan(null);
      setShowOther(false);
      setOtherDay('');
      if (action === 'start') {
        const workout = result as Workout;
        queryClient.setQueryData(['workout', 'today'], workout);
        onStarted(workout);
      }
      await refreshWorkouts();
    },
    onError: fail,
  });
  const transition = useMutation({
    mutationFn: ({
      action,
      workoutId,
    }: {
      action: 'cancel' | 'restore' | 'undo-skip';
      workoutId: number;
    }) =>
      api<RotationState>(`/api/v1/workouts/session-rotation/${action}`, {
        method: 'POST',
        body: {
          expected_cursor: state.cursor,
          workout_id: workoutId,
          mutation_id: createWorkoutMutationId(),
        },
      }),
    onSuccess: async (result) => {
      setError('');
      queryClient.setQueryData(['workout', 'session-rotation'], result);
      await refreshWorkouts();
    },
    onError: fail,
  });
  const extend = useMutation({
    mutationFn: () =>
      api<RotationState>(`/api/v1/programs/assigned/${state.program_id}/session-rotation/extend`, {
        method: 'POST',
        body: {
          expected_revision_number: state.revision_number,
          expected_cursor: state.cursor,
          duration_weeks: Number(extension),
          mutation_id: createWorkoutMutationId(),
        },
      }),
    onSuccess: async (result) => {
      setError('');
      setExtension('');
      queryClient.setQueryData(['workout', 'session-rotation'], result);
      await Promise.all([
        refreshWorkouts(),
        queryClient.invalidateQueries({ queryKey: ['assigned-program', state.program_id] }),
        queryClient.invalidateQueries({ queryKey: ['templates'] }),
      ]);
    },
    onError: fail,
  });
  const busy =
    refreshing ||
    planMutation.isPending ||
    sessionMutation.isPending ||
    transition.isPending ||
    extend.isPending;
  const canChange = online && !busy && !pendingLocalChanges;
  const startOrSkip = async (action: Action) => {
    if (!chosenDay || !validWeek) return;
    if (action === 'skip') {
      const accepted = await confirm({
        title: 'Пропустить тренировку?',
        message: `Следующей станет «${state.next?.title ?? 'следующая тренировка'}». Пропуск можно отменить до следующего действия.`,
        confirmText: 'Пропустить',
      });
      if (!accepted) return;
    }
    if (showOther) {
      const accepted = await confirm({
        title: 'Выполнить другую тренировку?',
        message: `После неё в очереди останется «${current?.title ?? 'текущая тренировка'}».`,
        confirmText: 'Начать',
      });
      if (!accepted) return;
    }
    sessionMutation.mutate({ action, day: chosenDay });
  };
  return (
    <>
      <div className="today-workout-copy session-rotation-workout-copy">
        <div className="today-workout-copy__status">
          <Badge>{state.status === 'in_progress' ? 'В процессе' : 'Следующая тренировка'}</Badge>
          <span>По очереди</span>
        </div>
        <img
          className="today-workout-photo"
          src="/assets/marketing/strength-row.webp"
          alt=""
          width="1536"
          height="1024"
        />
        <h2 id="today-workout-title">{current?.title ?? 'Очередь тренировок'}</h2>
        <p>
          {state.status === 'expired'
            ? 'Срок программы закончился. Продлите её, чтобы продолжить очередь.'
            : state.status === 'review_required'
              ? 'Программа изменилась. Проверьте порядок перед продолжением.'
              : state.status === 'cancelled'
                ? 'Тренировка отменена. Сохранённые подходы можно восстановить.'
                : current?.exercise_count != null && current?.set_count != null
                  ? `${countLabel(current.exercise_count, 'упражнение', 'упражнения', 'упражнений')} · ${countLabel(current.set_count, 'подход', 'подхода', 'подходов')}`
                  : 'Дни отдыха не меняют следующую тренировку.'}
        </p>
      </div>
      {!online && <p role="status">Нет соединения. Очередь обновится после подключения.</p>}
      {(state.days_since_last_completion ?? 0) >= 7 && (
        <p>После перерыва следующая тренировка остаётся на своём месте.</p>
      )}
      {pendingLocalChanges && (
        <p role="status">Сначала дождитесь сохранения подходов на сервере.</p>
      )}
      {error && <p role="alert">{error}</p>}
      {state.status === 'in_progress' && (
        <div className="today-workout-actions">
          <Button fullWidth type="button" onClick={onResume}>
            Продолжить тренировку
          </Button>
          {current?.workout_id && (
            <Button
              disabled={!canChange}
              type="button"
              variant="ghost"
              onClick={async () => {
                const accepted = await confirm({
                  title: 'Отменить тренировку?',
                  message:
                    'Очередь останется на месте. Сохранённые подходы можно будет восстановить.',
                  confirmText: 'Отменить тренировку',
                });
                if (accepted && current.workout_id)
                  transition.mutate({ action: 'cancel', workoutId: current.workout_id });
              }}
            >
              Отменить тренировку
            </Button>
          )}
        </div>
      )}
      {(state.status === 'cancelled' ||
        (state.status === 'expired' && current?.status === 'cancelled')) &&
        current?.workout_id && (
          <Button
            disabled={!canChange}
            type="button"
            onClick={() => transition.mutate({ action: 'restore', workoutId: current.workout_id! })}
          >
            Восстановить тренировку
          </Button>
        )}
      {state.status === 'review_required' && (
        <AppLink className="button-link" to="/app?section=programs">
          Проверить программу
        </AppLink>
      )}
      {state.status === 'expired' && state.can_extend === false && (
        <p>Продление программы согласуйте с тренером.</p>
      )}
      {state.status === 'expired' && state.can_extend !== false && (
        <div className="session-rotation-order__rows">
          <Field
            label="Общая длительность, недель"
            labelFor="rotation-extension"
            hint={`Чтобы продолжить сейчас, укажите не меньше ${state.min_extension_weeks ?? (state.duration_weeks ?? 0) + 1} недель.`}
          >
            <Input
              id="rotation-extension"
              type="number"
              min={state.min_extension_weeks ?? (state.duration_weeks ?? 0) + 1}
              value={extension}
              onChange={(event) => setExtension(event.target.value)}
            />
          </Field>
          <Button
            disabled={
              !canChange ||
              Number(extension) < (state.min_extension_weeks ?? (state.duration_weeks ?? 0) + 1)
            }
            type="button"
            onClick={() => extend.mutate()}
          >
            Продлить программу
          </Button>
        </div>
      )}
      {state.status === 'ready' && (
        <div className="today-workout-actions">
          {showOther && (
            <Field label="Другая тренировка" labelFor="rotation-other">
              <Select
                id="rotation-other"
                value={otherDay}
                onChange={(event) => {
                  setOtherDay(event.target.value);
                  setWeek('');
                  setPlan(null);
                }}
              >
                <option value="">Выберите тренировку</option>
                {(state.days ?? [])
                  .filter((day) => day.day_number !== current?.day_number)
                  .map((day) => (
                    <option key={day.day_number} value={day.day_number}>
                      {day.title}
                    </option>
                  ))}
              </Select>
            </Field>
          )}
          {!defaultWeek && (
            <Field
              label="Неделя программы"
              labelFor="rotation-week"
              hint="Выберите план недели: порядок тренировок не определяет периодизацию."
            >
              <Input
                id="rotation-week"
                type="number"
                min="1"
                max={state.duration_weeks ?? undefined}
                value={week}
                onChange={(event) => {
                  setWeek(event.target.value);
                  setPlan(null);
                }}
              />
            </Field>
          )}
          <Button
            disabled={!canChange || !validWeek || !chosenDay}
            fullWidth
            type="button"
            onClick={() => void startOrSkip('start')}
          >
            Начать тренировку
          </Button>
          <Button
            disabled={!canChange || !validWeek || !chosenDay}
            fullWidth
            type="button"
            variant="secondary"
            onClick={() => planMutation.mutate()}
          >
            Посмотреть упражнения
          </Button>
          {plan && (
            <div className="session-rotation-order__rows">
              <strong>
                {plan.title} · неделя {plan.week_number}
              </strong>
              <ul>
                {plan.exercises.map((exercise, index) => (
                  <li key={`${exercise.title}-${index}`}>
                    {exercise.title}
                    {exercise.prescribed_sets ? ` · подходов: ${exercise.prescribed_sets}` : ''}
                    {exercise.prescribed_reps ? ` × ${exercise.prescribed_reps}` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {!showOther && (
            <button
              className="today-text-link session-rotation-text-action"
              disabled={!canChange || !validWeek}
              type="button"
              onClick={() => void startOrSkip('skip')}
            >
              Пропустить тренировку
            </button>
          )}
          {(state.days ?? []).length > 1 && (
            <button
              className="today-text-link session-rotation-text-action"
              disabled={!canChange}
              type="button"
              onClick={() => {
                setShowOther(!showOther);
                setOtherDay('');
                setWeek('');
                setPlan(null);
              }}
            >
              {showOther ? 'Вернуться к очереди' : 'Выбрать другую тренировку'}
            </button>
          )}
        </div>
      )}
      <section className="session-rotation-order" aria-labelledby="rotation-order-title">
        <div>
          <span className="eyebrow">По очереди</span>
          <h3 id="rotation-order-title">Порядок тренировок</h3>
        </div>
        <div className="session-rotation-order__rows">
          <div className="session-rotation-order__row">
            <span>Текущая</span>
            <strong>{current?.title ?? 'Не выбрана'}</strong>
            <Badge>Сейчас</Badge>
          </div>
          <div className="session-rotation-order__row">
            <span>После неё</span>
            <strong>{state.next?.title ?? 'Проверить программу'}</strong>
          </div>
        </div>
        <details>
          <summary className="yfc-disclosure-summary">
            <span>Как работает очередь?</span>
            <DisclosureIcon />
          </summary>
          <p>
            После завершения или подтверждённого пропуска следующей станет тренировка по порядку.
            Дни отдыха очередь не меняют.
          </p>
        </details>
        {state.undo_skip_workout_id && (
          <Button
            disabled={!canChange}
            type="button"
            variant="secondary"
            onClick={() =>
              transition.mutate({ action: 'undo-skip', workoutId: state.undo_skip_workout_id! })
            }
          >
            Вернуть пропущенную тренировку
          </Button>
        )}
      </section>
    </>
  );
}
