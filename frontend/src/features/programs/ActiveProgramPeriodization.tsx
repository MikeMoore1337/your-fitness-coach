import { useLayoutEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, ApiError, apiErrorDetailIncludes } from '../../shared/api/client';
import type { Exercise, ProgramTemplateCreate } from '../../shared/api/types';
import { ProgramPeriodization } from './ProgramPeriodization';

type WeekType = 'light' | 'medium' | 'heavy' | null;
type PlanExercise = {
  source_template_exercise_id: number | null;
  exercise_id: number;
  prescribed_sets: number | null;
  prescribed_reps: string | null;
  prescribed_duration_minutes: number | null;
  rest_seconds: number;
  notes: string | null;
  metric_type: 'strength' | 'cardio';
  prescription: {
    groups: unknown[];
    segments: { role: string; load_target: { kind: string }; effort_target: { kind: string } }[];
  } | null;
};
type PlanWorkout = {
  id: number | null;
  day_number: number;
  title: string;
  scheduled_date: string;
  status: string;
  changeable: boolean;
  needs_refresh?: boolean;
  removed?: boolean;
  week_type: WeekType;
  exercises: PlanExercise[];
};
type PlanWeek = {
  week_number: number;
  source_cycle_week: number;
  cycle_iteration: number;
  cycle_length: number;
  repeat: boolean;
  periodization_enabled: boolean;
  change?: 'added' | 'removed' | 'unchanged';
  workouts: PlanWorkout[];
};
type Preview = { weeks: PlanWeek[]; total_weeks: number; offset: number };
type Scope = 'one' | 'repeat' | 'selected';
type Action = 'type' | 'exercise' | 'disable' | 'duration' | 'enable';
const actionValues = {
  type: 'type',
  exercise: 'exercise',
  disable: 'disable',
  duration: 'duration',
} as const;
const changeValues = { added: 'added', removed: 'removed' } as const;
const selectedScope: Scope = 'selected';
const strengthMetric = 'strength';
const typeLabels: Record<Exclude<WeekType, null>, string> = {
  light: 'Лёгкая',
  medium: 'Средняя',
  heavy: 'Тяжёлая',
};

export function ActiveProgramPeriodization({
  programId,
  revision: suppliedRevision,
  duration: suppliedDuration,
  exercises,
  dirty,
  initialWeek = 1,
  readOnly = false,
  onChanged,
}: {
  programId: number;
  revision: number;
  duration: number;
  exercises: Exercise[];
  dirty: boolean;
  initialWeek?: number;
  readOnly?: boolean;
  onChanged: (revision: number) => void;
}) {
  const [refreshed, setRefreshed] = useState<{
    revision: number;
    duration: number;
    currentWeek: number;
  } | null>(null);
  const revision = Math.max(suppliedRevision, refreshed?.revision ?? 0);
  const duration =
    refreshed && refreshed.revision >= suppliedRevision ? refreshed.duration : suppliedDuration;
  const firstEditableWeek =
    refreshed && refreshed.revision >= suppliedRevision ? refreshed.currentWeek : initialWeek;
  const [week, setWeek] = useState(initialWeek);
  const [scope, setScope] = useState<Scope>('one');
  const [selectedWeeks, setSelectedWeeks] = useState<number[]>([]);
  const [selectionPage, setSelectionPage] = useState(0);
  const [action, setAction] = useState<Action>('type');
  const [weekType, setWeekType] = useState<WeekType>(null);
  const [nextDuration, setNextDuration] = useState(duration);
  const [enableCycle, setEnableCycle] = useState<NonNullable<
    ProgramTemplateCreate['week_cycle']
  > | null>(null);
  const [slot, setSlot] = useState('');
  const [sets, setSets] = useState(3);
  const [reps, setReps] = useState('8-12');
  const [minutes, setMinutes] = useState(30);
  const [rest, setRest] = useState(90);
  const [impact, setImpact] = useState<{
    preview: Preview;
    body: Record<string, unknown>;
    action: Action;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(false);
  const futureSelectedWeeks = selectedWeeks.filter(
    (item) => item >= firstEditableWeek && item <= duration,
  );
  const impactHeading = useRef<HTMLHeadingElement>(null);
  const checkButton = useRef<HTMLButtonElement>(null);
  const wasPreview = useRef(false);
  const impactOpen = impact !== null;
  useLayoutEffect(() => {
    if (!impactOpen && !wasPreview.current) return;
    if (impactOpen) {
      wasPreview.current = true;
      impactHeading.current?.focus({ preventScroll: true });
      impactHeading.current?.scrollIntoView?.({ block: 'start', behavior: 'instant' });
    } else {
      checkButton.current?.focus({ preventScroll: true });
    }
  }, [impactOpen]);
  const basePath = `/api/v1/programs/assigned/${programId}/cycle`;
  const plan = useQuery({
    queryKey: ['program-periodization-week', programId, revision, week],
    enabled: Number.isSafeInteger(week) && week >= 1 && week <= duration,
    queryFn: () =>
      api<Preview>(`${basePath}/week-type/preview`, {
        method: 'POST',
        body: { expected_revision_number: revision, week_type: null, occurrence_weeks: [week] },
      }),
  });
  const selectedWeek = plan.data?.weeks[0];
  const choices =
    selectedWeek?.workouts.flatMap((workout) =>
      workout.exercises.map((exercise) => ({ workout, exercise })),
    ) ?? [];
  const selectedExercise = choices.find(
    ({ workout, exercise }) =>
      `${workout.day_number}:${exercise.source_template_exercise_id}` === slot,
  );
  const planIsSimple =
    selectedExercise &&
    (!selectedExercise.exercise.prescription ||
      (selectedExercise.exercise.prescription.groups.length === 0 &&
        selectedExercise.exercise.prescription.segments.every(
          (segment) =>
            segment.role === 'working' &&
            segment.load_target.kind === 'user_selected' &&
            segment.effort_target.kind === 'none',
        )));
  const showError = (reason: unknown) => {
    setConflict(reason instanceof ApiError && reason.status === 409);
    setError(
      reason instanceof ApiError && reason.status === 409
        ? 'План уже изменился. Введённые значения сохранены. Обновите план и проверьте изменения заново.'
        : reason instanceof Error
          ? reason.message
          : 'Не удалось проверить изменения.',
    );
  };
  const refreshPlan = async () => {
    setBusy(true);
    try {
      const current = await api<{
        current_revision_number: number;
        duration_weeks: number;
        current_week_number: number | null;
      }>(`/api/v1/programs/assigned/${programId}/lifecycle`);
      setRefreshed({
        revision: current.current_revision_number,
        duration: current.duration_weeks,
        currentWeek: current.current_week_number ?? 1,
      });
      setImpact(null);
      setError('');
      setConflict(false);
    } catch (reason) {
      showError(reason);
      setConflict(true);
    } finally {
      setBusy(false);
    }
  };
  const scopeBody = () =>
    scope === 'repeat'
      ? { from_week: week, source_cycle_week: selectedWeek?.source_cycle_week }
      : { occurrence_weeks: scope === selectedScope ? futureSelectedWeeks : [week] };

  const check = async (offset = 0, requestedAction = action) => {
    setBusy(true);
    setError('');
    setConflict(false);
    try {
      const body =
        requestedAction === 'enable'
          ? {
              expected_revision_number: revision,
              effective_from_week: week,
              duration_weeks: nextDuration,
              week_cycle: enableCycle,
              offset,
            }
          : requestedAction === actionValues.disable
            ? { expected_revision_number: revision, effective_from_week: week, offset }
            : requestedAction === actionValues.duration
              ? {
                  expected_revision_number: revision,
                  effective_from_week: week,
                  duration_weeks: nextDuration,
                  offset,
                }
              : {
                  expected_revision_number: revision,
                  week_type: requestedAction === actionValues.type ? weekType : null,
                  ...scopeBody(),
                  offset,
                };
      const preview = await api<Preview>(
        `${basePath}/${requestedAction === 'enable' ? 'enable' : requestedAction === actionValues.disable ? 'disable' : requestedAction === actionValues.duration ? 'duration' : 'week-type'}/preview`,
        { method: 'POST', body },
      );
      setImpact({ preview, body, action: requestedAction });
    } catch (reason) {
      showError(reason);
    } finally {
      setBusy(false);
    }
  };
  const apply = async () => {
    if (!impact || busy) return;
    setBusy(true);
    setError('');
    setConflict(false);
    try {
      let result: { current_revision_number: number };
      if (impact.action === actionValues.exercise && !selectedExercise)
        throw new Error('Выберите упражнение и проверьте изменения заново.');
      if (impact.action === actionValues.exercise && selectedExercise) {
        const { workout, exercise } = selectedExercise;
        result = await api<{ current_revision_number: number }>(
          `/api/v1/programs/assigned/${programId}/exercises`,
          {
            method: 'POST',
            body: {
              expected_revision_number: revision,
              effective_scope: 'future_program',
              ...scopeBody(),
              skip_protected: true,
              day_number: workout.day_number,
              target_template_exercise_id: exercise.source_template_exercise_id,
              exercise_id: exercise.exercise_id,
              prescribed_sets: exercise.metric_type === strengthMetric ? sets : null,
              prescribed_reps: exercise.metric_type === strengthMetric ? reps : null,
              prescribed_duration_minutes: exercise.metric_type === 'cardio' ? minutes : null,
              rest_seconds: rest,
              notes: exercise.notes,
            },
          },
        );
      } else if (impact.action === actionValues.duration) {
        result = await api<{ current_revision_number: number }>(basePath, {
          method: 'PATCH',
          body: {
            expected_revision_number: revision,
            effective_from_week: week,
            duration_weeks: nextDuration,
          },
        });
      } else {
        result = await api<{ current_revision_number: number }>(
          `${basePath}/${impact.action === 'enable' ? 'enable' : impact.action === actionValues.disable ? 'disable' : 'week-type'}`,
          { method: 'POST', body: impact.body },
        );
      }
      setImpact(null);
      onChanged(result.current_revision_number);
    } catch (reason) {
      showError(reason);
    } finally {
      setBusy(false);
    }
  };

  if (impact) {
    return (
      <section
        className="program-builder-section program-periodization stack"
        aria-label="Периодизация назначения"
      >
        <div className="program-periodization__preview">
          <h3 ref={impactHeading} tabIndex={-1}>
            Проверить изменения
          </h3>
          <div className="program-periodization__warning">
            <strong>История сохранится</strong>
            <p>Выполненные и начатые тренировки и записанные подходы не изменятся.</p>
          </div>
          <p className="muted">Проверяемых недель: {impact.preview.total_weeks}</p>
          {impact.action === actionValues.exercise && selectedExercise && (
            <p className="muted">
              Новое предписание:{' '}
              {selectedExercise.exercise.metric_type === strengthMetric
                ? `${sets} подх. × ${reps}`
                : `${minutes} мин`}{' '}
              · отдых {rest} сек.
            </p>
          )}
          {impact.preview.weeks.map((item) => (
            <div key={item.week_number} className="program-periodization__plan-week">
              <strong>
                Неделя {item.week_number}
                {item.change === changeValues.added
                  ? ' · будет добавлена'
                  : item.change === changeValues.removed
                    ? ' · будет отменена'
                    : ''}
                {item.source_cycle_week
                  ? ` · исходная ${item.source_cycle_week} · проход ${item.cycle_iteration}`
                  : ''}
              </strong>
              {item.workouts
                .filter(
                  (workout) =>
                    impact.action !== actionValues.exercise ||
                    workout.day_number === selectedExercise?.workout.day_number,
                )
                .map((workout) => (
                  <p key={`${workout.day_number}:${workout.id}`} className="muted">
                    {workout.scheduled_date} · {workout.title} ·{' '}
                    {workout.changeable &&
                    impact.action === actionValues.exercise &&
                    !workout.exercises?.some(
                      (exercise) =>
                        exercise.source_template_exercise_id ===
                        selectedExercise?.exercise.source_template_exercise_id,
                    )
                      ? 'исходная позиция отсутствует, не изменится'
                      : workout.changeable
                        ? workout.removed
                          ? 'будет отменена'
                          : 'запланирована'
                        : workout.needs_refresh
                          ? 'откройте тренировку и обновите её план'
                          : 'не изменится'}
                    {impact.action === actionValues.type &&
                      workout.changeable &&
                      ` · ${workout.week_type ? typeLabels[workout.week_type] : 'Тип не задан'} → ${weekType ? typeLabels[weekType] : 'тип не задан'}`}
                  </p>
                ))}
            </div>
          ))}
          {impact.preview.total_weeks > 50 && (
            <div className="program-periodization__paging">
              <button
                type="button"
                className="secondary"
                disabled={busy || impact.preview.offset === 0}
                onClick={() => void check(Math.max(0, impact.preview.offset - 50), impact.action)}
              >
                Предыдущие недели
              </button>
              <button
                type="button"
                className="secondary"
                disabled={busy || impact.preview.offset + 50 >= impact.preview.total_weeks}
                onClick={() => void check(impact.preview.offset + 50, impact.action)}
              >
                Следующие недели
              </button>
            </div>
          )}
          {error && (
            <div
              className={conflict ? 'program-periodization__warning' : 'field-error'}
              role="alert"
            >
              <p>{error}</p>
              {conflict && (
                <button type="button" disabled={busy} onClick={() => void refreshPlan()}>
                  Обновить план
                </button>
              )}
            </div>
          )}
          <div className="program-periodization__actions">
            <button type="button" disabled={busy || dirty || conflict} onClick={() => void apply()}>
              {busy ? 'Применяем…' : 'Применить изменения'}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => {
                setImpact(null);
                setError('');
                setConflict(false);
              }}
            >
              Вернуться
            </button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section
      className="program-builder-section program-periodization stack"
      aria-label="Периодизация назначения"
    >
      <div>
        <h3>Периодизация</h3>
        <p className="muted">Изменения применяются к будущему плану. История сохраняется.</p>
      </div>
      <label className="field">
        <span>Неделя программы</span>
        <input
          type="number"
          inputMode="numeric"
          min="1"
          max={duration}
          value={week}
          onChange={(event) => {
            setWeek(Number(event.target.value));
            setImpact(null);
            setSlot('');
          }}
        />
      </label>
      {plan.isLoading && <p role="status">Загружаем план…</p>}
      {plan.error && !apiErrorDetailIncludes(plan.error, 'нет сохранённого цикла') && (
        <div role="alert">
          <p>
            {plan.error instanceof ApiError && plan.error.status === 409
              ? 'План изменился. Обновите программу.'
              : 'Не удалось загрузить неделю.'}
          </p>
          {plan.error instanceof ApiError && plan.error.status === 409 ? (
            <button type="button" disabled={busy} onClick={() => void refreshPlan()}>
              Обновить план
            </button>
          ) : (
            <button type="button" className="secondary" onClick={() => void plan.refetch()}>
              Повторить загрузку
            </button>
          )}
        </div>
      )}
      {(apiErrorDetailIncludes(plan.error, 'нет сохранённого цикла') ||
        (selectedWeek && !selectedWeek.periodization_enabled)) &&
        (readOnly ? (
          <p className="muted">
            Периодизация не настроена. Изменения программы согласуйте с тренером.
          </p>
        ) : (
          <>
            <ProgramPeriodization
              cycle={enableCycle}
              onChange={(value) => {
                setEnableCycle(value);
                setImpact(null);
              }}
              duration={nextDuration}
              onDurationChange={(value) => {
                setNextDuration(value);
                setImpact(null);
              }}
              days={[]}
              disabled={false}
              showPreview={false}
              firstWeek={week}
            />
            {enableCycle && (
              <button
                ref={checkButton}
                type="button"
                className="secondary"
                disabled={
                  busy ||
                  dirty ||
                  !Number.isSafeInteger(nextDuration) ||
                  nextDuration < week ||
                  !Number.isInteger(enableCycle.length_weeks) ||
                  enableCycle.length_weeks < 1 ||
                  enableCycle.length_weeks > 20000 ||
                  (!enableCycle.repeat && nextDuration - week + 1 > enableCycle.length_weeks)
                }
                onClick={() => void check(0, 'enable')}
              >
                Проверить включение
              </button>
            )}
          </>
        ))}
      {selectedWeek && (
        <>
          <div className="program-periodization__plan-week">
            <strong>
              Неделя {week} · исходная {selectedWeek.source_cycle_week} · проход{' '}
              {selectedWeek.cycle_iteration}
            </strong>
            {selectedWeek.workouts.map((workout) => (
              <p className="muted" key={`${workout.day_number}:${workout.id}`}>
                {workout.title} · {workout.scheduled_date} ·{' '}
                {workout.week_type ? typeLabels[workout.week_type] : 'Тип не задан'}
                {!workout.changeable &&
                  (workout.needs_refresh ? ' · план требует обновления' : ' · история сохранится')}
              </p>
            ))}
          </div>
          {selectedWeek.periodization_enabled && readOnly && (
            <p className="muted">
              План подготовлен тренером. Изменения программы согласуйте с тренером.
            </p>
          )}
          {selectedWeek.periodization_enabled && !readOnly ? (
            <>
              <label className="field">
                <span>Что изменить</span>
                <select
                  value={action}
                  onChange={(event) => {
                    setAction(event.target.value as Action);
                    setImpact(null);
                  }}
                >
                  <option value="type">Тип недели</option>
                  <option value="exercise">Упражнение</option>
                  <option value="duration">Продолжительность</option>
                  <option value="disable">Отключить периодизацию</option>
                </select>
              </label>
              {action === actionValues.type && (
                <label className="field">
                  <span>Новый тип недели</span>
                  <select
                    value={weekType ?? ''}
                    onChange={(event) => {
                      setWeekType((event.target.value || null) as WeekType);
                      setImpact(null);
                    }}
                  >
                    <option value="">Не задан</option>
                    <option value="light">Лёгкая</option>
                    <option value="medium">Средняя</option>
                    <option value="heavy">Тяжёлая</option>
                  </select>
                </label>
              )}
              {action === actionValues.duration && (
                <label className="field">
                  <span>Всего недель</span>
                  <input
                    type="number"
                    inputMode="numeric"
                    min="1"
                    value={nextDuration}
                    onChange={(event) => {
                      setNextDuration(Number(event.target.value));
                      setImpact(null);
                    }}
                  />
                </label>
              )}
              {action === actionValues.exercise && (
                <>
                  <label className="field">
                    <span>Упражнение</span>
                    <select
                      value={slot}
                      onChange={(event) => {
                        setSlot(event.target.value);
                        setImpact(null);
                        const next = choices.find(
                          ({ workout, exercise }) =>
                            `${workout.day_number}:${exercise.source_template_exercise_id}` ===
                            event.target.value,
                        )?.exercise;
                        if (next) {
                          setSets(next.prescribed_sets ?? 1);
                          setReps(next.prescribed_reps ?? '');
                          setMinutes(next.prescribed_duration_minutes ?? 30);
                          setRest(next.rest_seconds);
                        }
                      }}
                    >
                      <option value="">Выберите упражнение</option>
                      {choices.map(({ workout, exercise }, index) => (
                        <option
                          key={`${workout.day_number}:${exercise.source_template_exercise_id}:${index}`}
                          value={`${workout.day_number}:${exercise.source_template_exercise_id}`}
                          disabled={exercise.source_template_exercise_id === null}
                        >
                          {workout.title} ·{' '}
                          {exercises.find((item) => item.id === exercise.exercise_id)?.title ??
                            `Упражнение ${exercise.exercise_id}`}
                          {exercise.source_template_exercise_id === null &&
                            ' · измените в тренировке'}
                        </option>
                      ))}
                    </select>
                  </label>
                  {selectedExercise && !planIsSimple && (
                    <p className="field-error">
                      Сложное предписание нельзя изменить здесь без потери его структуры.
                    </p>
                  )}
                  {selectedExercise && planIsSimple && (
                    <div className="program-periodization__fields">
                      {selectedExercise.exercise.metric_type === strengthMetric ? (
                        <>
                          <label className="field">
                            <span>Подходы</span>
                            <input
                              type="number"
                              min="1"
                              max="10"
                              value={sets}
                              onChange={(event) => {
                                setSets(Number(event.target.value));
                                setImpact(null);
                              }}
                            />
                          </label>
                          <label className="field">
                            <span>Повторы</span>
                            <input
                              value={reps}
                              maxLength={32}
                              onChange={(event) => {
                                setReps(event.target.value);
                                setImpact(null);
                              }}
                            />
                          </label>
                        </>
                      ) : (
                        <label className="field">
                          <span>Минуты</span>
                          <input
                            type="number"
                            min="1"
                            max="600"
                            value={minutes}
                            onChange={(event) => {
                              setMinutes(Number(event.target.value));
                              setImpact(null);
                            }}
                          />
                        </label>
                      )}
                      <label className="field">
                        <span>Отдых, сек</span>
                        <input
                          type="number"
                          min="15"
                          max="600"
                          value={rest}
                          onChange={(event) => {
                            setRest(Number(event.target.value));
                            setImpact(null);
                          }}
                        />
                      </label>
                    </div>
                  )}
                </>
              )}
              {(action === actionValues.type || action === actionValues.exercise) && (
                <fieldset className="program-periodization__scope">
                  <legend>К каким неделям применить?</legend>
                  {(
                    [
                      ['one', `Только неделя ${week}`, 'Одно выбранное вхождение.'],
                      [
                        'repeat',
                        `Будущие повторы исходной недели ${selectedWeek.source_cycle_week}`,
                        'Начиная с выбранной недели.',
                      ],
                      ['selected', 'Выбрать недели', 'Отметьте конкретные вхождения.'],
                    ] as const
                  ).map(([value, label, hint]) => (
                    <label
                      key={value}
                      className="program-periodization__choice"
                      data-yfc-choice="compact"
                    >
                      <input
                        type="radio"
                        name={`periodization-scope-${programId}`}
                        checked={scope === value}
                        disabled={value === 'repeat' && !selectedWeek.repeat}
                        onChange={() => {
                          setScope(value);
                          setImpact(null);
                        }}
                      />
                      <span>
                        <strong>{label}</strong>
                        <small>{hint}</small>
                      </span>
                    </label>
                  ))}
                  {scope === selectedScope && (
                    <div>
                      {Array.from(
                        { length: Math.min(10, duration - selectionPage * 10) },
                        (_, index) => selectionPage * 10 + index + 1,
                      ).map((value) => (
                        <label
                          key={value}
                          className="program-periodization__choice"
                          data-yfc-choice="compact"
                        >
                          <input
                            type="checkbox"
                            checked={futureSelectedWeeks.includes(value)}
                            disabled={value < firstEditableWeek}
                            onChange={(event) => {
                              setSelectedWeeks(
                                event.target.checked
                                  ? [...selectedWeeks, value]
                                  : selectedWeeks.filter((item) => item !== value),
                              );
                              setImpact(null);
                            }}
                          />
                          <span>Неделя {value}</span>
                        </label>
                      ))}
                      <div className="program-periodization__paging">
                        <button
                          type="button"
                          className="secondary"
                          disabled={selectionPage === 0}
                          onClick={() => setSelectionPage(selectionPage - 1)}
                        >
                          Предыдущие недели
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          disabled={(selectionPage + 1) * 10 >= duration}
                          onClick={() => setSelectionPage(selectionPage + 1)}
                        >
                          Следующие недели
                        </button>
                      </div>
                    </div>
                  )}
                </fieldset>
              )}
              {action === actionValues.type && (
                <p className="muted">Тип сам по себе не меняет упражнения и нагрузку.</p>
              )}
              {action === actionValues.disable && (
                <p className="muted">
                  Оставшиеся запланированные тренировки сохранятся. Типы и повторение будут
                  отключены начиная с выбранной недели.
                </p>
              )}
              {dirty && (
                <p className="field-error">
                  Сначала сохраните или отмените другие изменения программы.
                </p>
              )}
              <button
                ref={checkButton}
                type="button"
                className="program-periodization__confirm"
                disabled={
                  busy ||
                  dirty ||
                  (scope === selectedScope &&
                    (action === actionValues.type || action === actionValues.exercise) &&
                    (futureSelectedWeeks.length === 0 || futureSelectedWeeks.length > 100)) ||
                  (action === actionValues.duration &&
                    (!Number.isSafeInteger(nextDuration) ||
                      nextDuration < 1 ||
                      nextDuration === duration)) ||
                  (action === actionValues.exercise &&
                    (!selectedExercise ||
                      !planIsSimple ||
                      sets < 1 ||
                      sets > 10 ||
                      !reps.trim() ||
                      minutes < 1 ||
                      minutes > 600 ||
                      rest < 15 ||
                      rest > 600))
                }
                onClick={() => void check()}
              >
                {busy ? 'Проверяем…' : 'Проверить изменения'}
              </button>
            </>
          ) : (
            !selectedWeek.periodization_enabled && (
              <p className="muted">
                Периодизация для этой недели отключена; оставшийся план сохранён.
              </p>
            )
          )}
        </>
      )}
      {error && (
        <div className={conflict ? 'program-periodization__warning' : 'field-error'} role="alert">
          <p>{error}</p>
          {conflict && (
            <button type="button" disabled={busy} onClick={() => void refreshPlan()}>
              Обновить план
            </button>
          )}
        </div>
      )}
    </section>
  );
}
