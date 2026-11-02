import { useLayoutEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, ApiError, apiErrorDetailIncludes } from '../../shared/api/client';
import type { ApiSchemas, Exercise, ProgramTemplateCreate } from '../../shared/api/types';
import { ProgramPeriodization } from './ProgramPeriodization';
import { ActivePrescriptionEditor } from './ActivePrescriptionEditor';

type WeekType = 'light' | 'medium' | 'heavy' | null;
type PlanExercise = {
  source_template_exercise_id: number | null;
  source_assignment_slot_id?: string | null;
  exercise_id: number;
  prescribed_sets: number | null;
  prescribed_reps: string | null;
  prescribed_duration_minutes: number | null;
  rest_seconds: number;
  notes: string | null;
  metric_type: 'strength' | 'cardio';
  prescription: ApiSchemas['ExercisePrescriptionPlan'] | null;
};
type PlanWorkout = {
  id: number | null;
  day_number: number;
  title: string;
  scheduled_date: string;
  new_scheduled_date?: string;
  status: string;
  changeable: boolean;
  needs_refresh?: boolean;
  removed?: boolean;
  added?: boolean;
  week_type: WeekType;
  new_week_type?: WeekType;
  exercises: PlanExercise[];
  new_exercises?: PlanExercise[];
  structure_changed?: boolean;
};
type PlanWeek = {
  week_number: number;
  source_cycle_week: number;
  new_source_cycle_week?: number | null;
  cycle_iteration: number;
  cycle_length: number;
  repeat: boolean;
  periodization_enabled: boolean;
  change?: 'added' | 'removed' | 'unchanged';
  workouts: PlanWorkout[];
};
type Preview = { weeks: PlanWeek[]; total_weeks: number; offset: number };
type Scope = 'one' | 'repeat' | 'future' | 'selected';
type Action =
  'type' | 'exercise' | 'disable' | 'duration' | 'enable' | 'cycle' | 'structure' | 'days';
type StructureOperation = 'add_exercise' | 'remove_exercise' | 'move_earlier' | 'move_later';
const actionValues = {
  type: 'type',
  exercise: 'exercise',
  disable: 'disable',
  duration: 'duration',
  cycle: 'cycle',
  structure: 'structure',
  days: 'days',
} as const;
const changeValues = { added: 'added', removed: 'removed' } as const;
const selectedScope: Scope = 'selected';
const strengthMetric = 'strength';
const conflictMessage =
  'План уже изменился. Введённые значения сохранены. Обновите план и проверьте изменения заново.';
const typeLabels: Record<Exclude<WeekType, null>, string> = {
  light: 'Лёгкая',
  medium: 'Средняя',
  heavy: 'Тяжёлая',
};

function slotKey(exercise: PlanExercise): string | null {
  if (exercise.source_template_exercise_id !== null && !exercise.source_assignment_slot_id)
    return String(exercise.source_template_exercise_id);
  if (exercise.source_template_exercise_id === null && exercise.source_assignment_slot_id)
    return `assignment:${exercise.source_assignment_slot_id}`;
  return null;
}

function targetSlot(exercise: PlanExercise): Record<string, string | number> {
  return exercise.source_assignment_slot_id
    ? { target_assignment_slot_id: exercise.source_assignment_slot_id }
    : { target_template_exercise_id: exercise.source_template_exercise_id! };
}

function newAssignmentSlot(): string | null {
  if (typeof crypto === 'undefined') return null;
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  if (typeof crypto.getRandomValues !== 'function') return null;
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 15) | 64;
  bytes[8] = (bytes[8]! & 63) | 128;
  const hex = Array.from(bytes, (item) => item.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function isSimplePrescription(exercise: PlanExercise): boolean {
  const plan = exercise.prescription;
  if (!plan) return true;
  const expectedReps = (exercise.prescribed_reps ?? '').replace(/\s/g, '').replace('–', '-');
  return (
    (plan.groups?.length ?? 0) === 0 &&
    plan.segments.length === exercise.prescribed_sets &&
    plan.segments.every((segment) => {
      const target = segment.rep_target;
      const reps =
        target?.kind === 'exact'
          ? String(target.value ?? '')
          : target?.kind === 'range'
            ? `${target.min_reps}-${target.max_reps}`
            : '';
      const targetMatches =
        exercise.metric_type === 'cardio'
          ? segment.duration_target?.kind === 'exact' &&
            segment.duration_target.value_minutes === exercise.prescribed_duration_minutes
          : reps === expectedReps;
      return (
        segment.role === 'working' &&
        (segment.load_target?.kind ?? 'user_selected') === 'user_selected' &&
        (segment.effort_target?.kind ?? 'none') === 'none' &&
        segment.rest_after_seconds === exercise.rest_seconds &&
        targetMatches
      );
    })
  );
}

function describeSegment(segment: ApiSchemas['PrescriptionSegment']): string {
  const target = segment.rep_target;
  const reps =
    target?.kind === 'exact'
      ? `${target.value} повторов`
      : target?.kind === 'range'
        ? `${target.min_reps}–${target.max_reps} повторов`
        : target?.cap_reps
          ? `AMRAP до ${target.cap_reps}`
          : 'AMRAP';
  const load = segment.load_target;
  const loadLabels = {
    percent_1rm: '% от максимума',
    percent_training_max: '% от тренировочного максимума',
    relative_to_top: '% от основного подхода',
    relative_to_previous: '% от предыдущего подхода',
  } as const;
  const loadText =
    !load || load.kind === 'user_selected'
      ? 'вес выбирается спортсменом'
      : load.kind === 'absolute'
        ? `${load.value} кг`
        : `${load.value} ${loadLabels[load.kind]}`;
  const effort = segment.effort_target;
  const effortText =
    !effort || effort.kind === 'none'
      ? 'усилие не задано'
      : effort.kind === 'failure'
        ? 'до отказа'
        : `${effort.kind.toUpperCase()} ${effort.value}`;
  return `Подход ${segment.position} · ${reps} · ${loadText} · ${effortText} · отдых ${segment.rest_after_seconds} сек.`;
}

function describeExercise(exercise: PlanExercise, exercises: Exercise[]): string {
  const title =
    exercises.find((item) => item.id === exercise.exercise_id)?.title ??
    `Упражнение ${exercise.exercise_id}`;
  const target =
    exercise.prescription && exercise.metric_type === 'strength'
      ? exercise.prescription.segments.map(describeSegment).join('; ')
      : exercise.metric_type === 'cardio'
        ? `${exercise.prescribed_duration_minutes ?? '—'} мин`
        : `${exercise.prescribed_sets ?? '—'} подх. × ${exercise.prescribed_reps ?? '—'} · отдых ${exercise.rest_seconds} сек.`;
  return `${title}: ${target}`;
}

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
  const [cycleLength, setCycleLength] = useState(0);
  const [cycleOrder, setCycleOrder] = useState<number[]>([]);
  const [cycleRepeat, setCycleRepeat] = useState(true);
  const [cyclePage, setCyclePage] = useState(0);
  const [enableCycle, setEnableCycle] = useState<NonNullable<
    ProgramTemplateCreate['week_cycle']
  > | null>(null);
  const [slot, setSlot] = useState('');
  const [structureDay, setStructureDay] = useState<number | null>(null);
  const [structureOperation, setStructureOperation] = useState<StructureOperation | null>(null);
  const [newSlotId, setNewSlotId] = useState<string | null>(null);
  const [newExerciseId, setNewExerciseId] = useState<number | null>(null);
  const [dayToRemove, setDayToRemove] = useState<number | null>(null);
  const [copyDay, setCopyDay] = useState<number | null>(null);
  const [swapDays, setSwapDays] = useState<[number, number] | null>(null);
  const [newDayWeekday, setNewDayWeekday] = useState(0);
  const [newDayTitle, setNewDayTitle] = useState('');
  const [replacementId, setReplacementId] = useState<number | null>(null);
  const [detailed, setDetailed] = useState(false);
  const [prescriptionDraft, setPrescriptionDraft] = useState<
    ApiSchemas['ExercisePrescriptionPlan'] | null
  >(null);
  const [sets, setSets] = useState(3);
  const [reps, setReps] = useState('8-12');
  const [minutes, setMinutes] = useState(30);
  const [rest, setRest] = useState(90);
  const [impact, setImpact] = useState<{
    preview: Preview;
    body: Record<string, unknown>;
    action: Action;
    exercise: {
      workout: PlanWorkout;
      exercise: PlanExercise;
      replacementId: number;
      prescription: ApiSchemas['ExercisePrescriptionPlan'] | null;
      sets: number;
      reps: string;
      minutes: number;
      rest: number;
    } | null;
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
  const impactStale = impact !== null && impact.body.expected_revision_number !== revision;
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
    ({ workout, exercise }) => `${workout.day_number}:${slotKey(exercise)}` === slot,
  );
  const structureWorkout =
    selectedWeek?.workouts.find((item) => item.day_number === structureDay) ??
    selectedWeek?.workouts[0];
  const planIsSimple = selectedExercise && isSimplePrescription(selectedExercise.exercise);
  const editDetailed = Boolean(selectedExercise && (detailed || !planIsSimple));
  const showError = (reason: unknown) => {
    setConflict(reason instanceof ApiError && reason.status === 409);
    setError(
      reason instanceof ApiError && reason.status === 409
        ? conflictMessage
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
      : scope === 'future'
        ? { from_week: week }
        : { occurrence_weeks: scope === selectedScope ? futureSelectedWeeks : [week] };

  const check = async (offset = 0, requestedAction = action) => {
    if (impactStale) return;
    setBusy(true);
    setError('');
    setConflict(false);
    try {
      const body = impact
        ? { ...impact.body, offset }
        : requestedAction === 'enable'
          ? {
              expected_revision_number: revision,
              effective_from_week: week,
              duration_weeks: nextDuration,
              week_cycle: enableCycle,
              offset,
            }
          : requestedAction === actionValues.disable
            ? { expected_revision_number: revision, effective_from_week: week, offset }
            : requestedAction === actionValues.days
              ? {
                  expected_revision_number: revision,
                  effective_from_week:
                    scope === selectedScope ? Math.min(...futureSelectedWeeks) : week,
                  offset,
                  ...(scope === 'one'
                    ? { occurrence_weeks: [week] }
                    : scope === selectedScope
                      ? { occurrence_weeks: futureSelectedWeeks }
                      : scope === 'repeat'
                        ? { source_cycle_week: selectedWeek?.source_cycle_week }
                        : {}),
                  ...(copyDay !== null
                    ? {
                        copy_day_number: copyDay,
                        new_day_weekday: newDayWeekday,
                        new_day_title: newDayTitle.trim(),
                      }
                    : swapDays
                      ? { swap_day_number: swapDays[0], swap_with_day_number: swapDays[1] }
                      : { remove_day_number: dayToRemove }),
                }
              : requestedAction === actionValues.structure &&
                  structureOperation === 'add_exercise' &&
                  structureWorkout
                ? {
                    expected_revision_number: revision,
                    ...scopeBody(),
                    day_number: structureWorkout.day_number,
                    operation: structureOperation,
                    assignment_slot_id: newSlotId,
                    offset,
                    exercise: {
                      exercise_id: newExerciseId,
                      ...(exercises.find((item) => item.id === newExerciseId)?.metric_type ===
                      'cardio'
                        ? { prescribed_duration_minutes: minutes, rest_seconds: 0 }
                        : { prescribed_sets: sets, prescribed_reps: reps, rest_seconds: rest }),
                    },
                  }
                : requestedAction === actionValues.structure && selectedExercise
                  ? {
                      expected_revision_number: revision,
                      ...scopeBody(),
                      day_number: selectedExercise.workout.day_number,
                      ...targetSlot(selectedExercise.exercise),
                      operation: structureOperation,
                      offset,
                    }
                  : requestedAction === actionValues.cycle
                    ? {
                        expected_revision_number: revision,
                        effective_from_week: week,
                        source_week_order: [...cycleOrder],
                        repeat: cycleRepeat,
                        offset,
                      }
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
      const checkedExercise = impact
        ? impact.exercise
        : requestedAction === actionValues.exercise && selectedExercise
          ? {
              ...selectedExercise,
              replacementId: replacementId ?? selectedExercise.exercise.exercise_id,
              prescription: editDetailed ? prescriptionDraft : null,
              sets,
              reps,
              minutes,
              rest,
            }
          : null;
      const preview = await api<Preview>(
        `${basePath}/${requestedAction === 'enable' ? 'enable' : requestedAction === actionValues.disable ? 'disable' : requestedAction === actionValues.duration ? 'duration' : requestedAction === actionValues.cycle || requestedAction === actionValues.days ? 'revision' : requestedAction === actionValues.structure ? 'structure' : 'week-type'}/preview`,
        { method: 'POST', body },
      );
      setImpact({ preview, body, action: requestedAction, exercise: checkedExercise });
    } catch (reason) {
      showError(reason);
    } finally {
      setBusy(false);
    }
  };
  const apply = async () => {
    if (!impact || busy || impactStale) return;
    setBusy(true);
    setError('');
    setConflict(false);
    try {
      let result: { current_revision_number: number };
      if (impact.action === actionValues.exercise && !impact.exercise)
        throw new Error('Выберите упражнение и проверьте изменения заново.');
      if (impact.action === actionValues.exercise && impact.exercise) {
        const { workout, exercise, replacementId, prescription, sets, reps, minutes, rest } =
          impact.exercise;
        result = await api<{ current_revision_number: number }>(
          `/api/v1/programs/assigned/${programId}/exercises`,
          {
            method: 'POST',
            body: {
              expected_revision_number: impact.body.expected_revision_number,
              effective_scope: 'future_program',
              ...(impact.body.from_week !== undefined
                ? {
                    from_week: impact.body.from_week,
                    ...(impact.body.source_cycle_week !== undefined
                      ? { source_cycle_week: impact.body.source_cycle_week }
                      : {}),
                  }
                : { occurrence_weeks: impact.body.occurrence_weeks }),
              skip_protected: true,
              day_number: workout.day_number,
              ...targetSlot(exercise),
              exercise_id: replacementId,
              prescribed_sets:
                exercise.metric_type === strengthMetric && !prescription ? sets : null,
              prescribed_reps:
                exercise.metric_type === strengthMetric && !prescription ? reps : null,
              prescribed_duration_minutes: exercise.metric_type === 'cardio' ? minutes : null,
              rest_seconds: prescription?.segments[0]?.rest_after_seconds ?? rest,
              ...(prescription ? { prescription } : {}),
              notes: exercise.notes,
            },
          },
        );
      } else if (impact.action === actionValues.structure) {
        result = await api<{ current_revision_number: number }>(`${basePath}/structure`, {
          method: 'POST',
          body: impact.body,
        });
      } else if (
        impact.action === actionValues.duration ||
        impact.action === actionValues.cycle ||
        impact.action === actionValues.days
      ) {
        result = await api<{ current_revision_number: number }>(basePath, {
          method: 'PATCH',
          body: {
            expected_revision_number: impact.body.expected_revision_number,
            effective_from_week: impact.body.effective_from_week,
            ...(impact.action === actionValues.days && impact.body.occurrence_weeks !== undefined
              ? { occurrence_weeks: impact.body.occurrence_weeks }
              : {}),
            ...(impact.action === actionValues.days && impact.body.source_cycle_week !== undefined
              ? { source_cycle_week: impact.body.source_cycle_week }
              : {}),
            ...(impact.action === actionValues.duration
              ? { duration_weeks: impact.body.duration_weeks }
              : impact.action === actionValues.days
                ? impact.body.copy_day_number !== undefined
                  ? {
                      copy_day_number: impact.body.copy_day_number,
                      new_day_weekday: impact.body.new_day_weekday,
                      new_day_title: impact.body.new_day_title,
                    }
                  : impact.body.swap_day_number !== undefined
                    ? {
                        swap_day_number: impact.body.swap_day_number,
                        swap_with_day_number: impact.body.swap_with_day_number,
                      }
                    : { remove_day_number: impact.body.remove_day_number }
                : { source_week_order: impact.body.source_week_order, repeat: impact.body.repeat }),
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
    const checkedWeekType = impact.body.week_type as WeekType;
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
          {impact.action === actionValues.exercise && impact.exercise && (
            <>
              {impact.exercise.replacementId !== impact.exercise.exercise.exercise_id && (
                <p className="muted">
                  {
                    exercises.find((item) => item.id === impact.exercise?.exercise.exercise_id)
                      ?.title
                  }{' '}
                  → {exercises.find((item) => item.id === impact.exercise?.replacementId)?.title}
                </p>
              )}
              {impact.exercise.prescription ? (
                <div className="muted">
                  <strong>Новое предписание</strong>
                  {impact.exercise.prescription.segments.map((segment) => (
                    <p key={segment.position}>{describeSegment(segment)}</p>
                  ))}
                </div>
              ) : (
                <p className="muted">
                  Новое предписание:{' '}
                  {impact.exercise.exercise.metric_type === strengthMetric
                    ? `${impact.exercise.sets} подх. × ${impact.exercise.reps}`
                    : `${impact.exercise.minutes} мин`}{' '}
                  · отдых {impact.exercise.rest} сек.
                </p>
              )}
            </>
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
                {impact.action === actionValues.cycle
                  ? ` · исходная ${item.source_cycle_week ?? 'нет'} → новая ${item.new_source_cycle_week ?? 'нет'}`
                  : item.source_cycle_week
                    ? ` · исходная ${item.source_cycle_week} · проход ${item.cycle_iteration}`
                    : ''}
              </strong>
              {item.workouts
                .filter(
                  (workout) =>
                    impact.action !== actionValues.exercise ||
                    workout.day_number === impact.exercise?.workout.day_number,
                )
                .filter(
                  (workout) =>
                    impact.action !== actionValues.structure ||
                    workout.day_number === impact.body.day_number,
                )
                .filter(
                  (workout) =>
                    impact.action !== actionValues.days ||
                    (impact.body.copy_day_number !== undefined
                      ? workout.added
                      : impact.body.swap_day_number !== undefined
                        ? [impact.body.swap_day_number, impact.body.swap_with_day_number].includes(
                            workout.day_number,
                          )
                        : workout.day_number === impact.body.remove_day_number),
                )
                .map((workout) => (
                  <div key={`${workout.day_number}:${workout.id}`} className="muted">
                    <p>
                      {workout.scheduled_date}
                      {workout.changeable &&
                      workout.new_scheduled_date &&
                      workout.new_scheduled_date !== workout.scheduled_date
                        ? ` → ${workout.new_scheduled_date}`
                        : ''}{' '}
                      · {workout.title} ·{' '}
                      {workout.changeable &&
                      impact.action === actionValues.exercise &&
                      !workout.exercises?.some(
                        (exercise) =>
                          slotKey(exercise) !== null &&
                          slotKey(exercise) === slotKey(impact.exercise!.exercise),
                      )
                        ? 'исходная позиция отсутствует, не изменится'
                        : workout.changeable &&
                            impact.action === actionValues.structure &&
                            !workout.structure_changed
                          ? 'состав не изменится'
                          : workout.changeable &&
                              impact.action === actionValues.days &&
                              ((impact.body.remove_day_number !== undefined && !workout.removed) ||
                                (impact.body.swap_day_number !== undefined &&
                                  workout.new_scheduled_date === workout.scheduled_date))
                            ? 'не изменится'
                            : workout.changeable
                              ? workout.removed
                                ? 'будет отменена'
                                : workout.added
                                  ? 'будет добавлена'
                                  : impact.action === actionValues.days &&
                                      impact.body.swap_day_number !== undefined
                                    ? 'дата будет изменена'
                                    : 'запланирована'
                              : workout.status === 'in_progress'
                                ? 'начата · не изменится'
                                : workout.needs_refresh
                                  ? 'откройте тренировку и обновите её план'
                                  : 'не изменится'}
                      {impact.action === actionValues.type &&
                        workout.changeable &&
                        ` · ${workout.week_type ? typeLabels[workout.week_type] : 'Тип не задан'} → ${checkedWeekType ? typeLabels[checkedWeekType] : 'тип не задан'}`}
                    </p>
                    {(impact.action === actionValues.cycle ||
                      impact.action === actionValues.structure) &&
                      workout.changeable &&
                      !workout.removed && (
                        <div>
                          <p>
                            Было:{' '}
                            {workout.exercises
                              .map((exercise) => describeExercise(exercise, exercises))
                              .join(', ') || 'нет тренировки'}
                            {' · '}Станет:{' '}
                            {workout.new_exercises
                              ?.map((exercise) => describeExercise(exercise, exercises))
                              .join(', ') || 'нет упражнений'}
                          </p>
                          {impact.action === actionValues.cycle && (
                            <p>
                              Тип: {workout.week_type ? typeLabels[workout.week_type] : 'не задан'}{' '}
                              →{' '}
                              {workout.new_week_type
                                ? typeLabels[workout.new_week_type]
                                : 'не задан'}
                            </p>
                          )}
                        </div>
                      )}
                  </div>
                ))}
              {impact.action === actionValues.days &&
                !item.workouts.some((workout) =>
                  impact.body.copy_day_number !== undefined
                    ? workout.added
                    : impact.body.swap_day_number !== undefined
                      ? [impact.body.swap_day_number, impact.body.swap_with_day_number].includes(
                          workout.day_number,
                        )
                      : workout.day_number === impact.body.remove_day_number,
                ) && <p className="muted">В эту неделю день не изменится.</p>}
            </div>
          ))}
          {impact.preview.total_weeks > 50 && (
            <div className="program-periodization__paging">
              <button
                type="button"
                className="secondary"
                disabled={busy || impactStale || impact.preview.offset === 0}
                onClick={() => void check(Math.max(0, impact.preview.offset - 50), impact.action)}
              >
                Предыдущие недели
              </button>
              <button
                type="button"
                className="secondary"
                disabled={
                  busy || impactStale || impact.preview.offset + 50 >= impact.preview.total_weeks
                }
                onClick={() => void check(impact.preview.offset + 50, impact.action)}
              >
                Следующие недели
              </button>
            </div>
          )}
          {(error || impactStale) && (
            <div
              className={conflict || impactStale ? 'program-periodization__warning' : 'field-error'}
              role="alert"
            >
              <p>{impactStale ? conflictMessage : error}</p>
              {(conflict || impactStale) && (
                <button type="button" disabled={busy} onClick={() => void refreshPlan()}>
                  Обновить план
                </button>
              )}
            </div>
          )}
          <div className="program-periodization__actions">
            <button
              type="button"
              disabled={
                busy ||
                dirty ||
                conflict ||
                impactStale ||
                (impact.action === actionValues.structure &&
                  impact.preview.total_weeks <= 50 &&
                  !impact.preview.weeks.some((item) =>
                    item.workouts.some((workout) => workout.structure_changed),
                  ))
              }
              onClick={() => void apply()}
            >
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
            setStructureDay(null);
            setStructureOperation(null);
            setDayToRemove(null);
            setCopyDay(null);
            setSwapDays(null);
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
                    const next = event.target.value as Action;
                    setAction(next);
                    setSlot('');
                    setStructureOperation(null);
                    setDayToRemove(null);
                    setCopyDay(null);
                    setSwapDays(null);
                    if (next === 'days') setScope('future');
                    if (next === 'cycle') {
                      setCycleLength(selectedWeek.cycle_length);
                      setCycleOrder(
                        Array.from({ length: selectedWeek.cycle_length }, (_, index) => index + 1),
                      );
                      setCycleRepeat(selectedWeek.repeat);
                      setCyclePage(0);
                    }
                    setImpact(null);
                  }}
                >
                  <option value="type">Тип недели</option>
                  <option value="exercise">Упражнение</option>
                  <option value="duration">Продолжительность</option>
                  <option value="cycle">Новый порядок недель</option>
                  <option value="structure">Состав тренировки</option>
                  <option value="days">Тренировочные дни</option>
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
              {action === actionValues.cycle && (
                <>
                  <p className="muted">До недели {week} порядок и результаты сохранятся.</p>
                  <label className="field">
                    <span>Исходных недель в новом цикле</span>
                    <input
                      type="number"
                      min="1"
                      max="20000"
                      value={cycleLength}
                      onChange={(event) => {
                        const count = Number(event.target.value);
                        setCycleLength(count);
                        if (Number.isSafeInteger(count) && count >= 1 && count <= 20000) {
                          setCycleOrder((old) =>
                            Array.from(
                              { length: count },
                              (_, index) => old[index] ?? (index % selectedWeek.cycle_length) + 1,
                            ),
                          );
                          setCyclePage(0);
                        }
                      }}
                    />
                  </label>
                  {cycleOrder.slice(cyclePage * 10, cyclePage * 10 + 10).map((source, index) => {
                    const position = cyclePage * 10 + index;
                    const changeSource = (value: number) =>
                      setCycleOrder((old) =>
                        old.map((item, itemIndex) => (itemIndex === position ? value : item)),
                      );
                    return (
                      <label className="field" key={position}>
                        <span>Новая неделя {position + 1}</span>
                        {selectedWeek.cycle_length <= 100 ? (
                          <select
                            value={source}
                            onChange={(event) => changeSource(Number(event.target.value))}
                          >
                            {Array.from({ length: selectedWeek.cycle_length }, (_, item) => (
                              <option key={item + 1} value={item + 1}>
                                Исходная {item + 1}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            type="number"
                            min="1"
                            max={selectedWeek.cycle_length}
                            value={source}
                            onChange={(event) => changeSource(Number(event.target.value))}
                          />
                        )}
                      </label>
                    );
                  })}
                  {cycleOrder.length > 10 && (
                    <div className="program-periodization__paging">
                      <button
                        type="button"
                        className="secondary"
                        disabled={cyclePage === 0}
                        onClick={() => setCyclePage(cyclePage - 1)}
                      >
                        Предыдущие недели
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        disabled={(cyclePage + 1) * 10 >= cycleOrder.length}
                        onClick={() => setCyclePage(cyclePage + 1)}
                      >
                        Следующие недели
                      </button>
                    </div>
                  )}
                  <label className="program-periodization__choice" data-yfc-choice="compact">
                    <input
                      type="checkbox"
                      checked={cycleRepeat}
                      onChange={(event) => setCycleRepeat(event.target.checked)}
                    />
                    <span>
                      <strong>Повторять новый цикл</strong>
                      <small>Только для будущих тренировок.</small>
                    </span>
                  </label>
                  <p className="muted">
                    Номер в каждой строке соответствует исходной неделе текущего цикла: от 1 до{' '}
                    {selectedWeek.cycle_length}.
                  </p>
                </>
              )}
              {action === actionValues.structure && structureWorkout && (
                <>
                  <label className="field">
                    <span>Тренировка</span>
                    <select
                      value={structureWorkout.day_number}
                      onChange={(event) => {
                        setStructureDay(Number(event.target.value));
                        setSlot('');
                        setStructureOperation(null);
                      }}
                    >
                      {selectedWeek.workouts.map((workout) => (
                        <option key={workout.day_number} value={workout.day_number}>
                          {workout.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  {structureWorkout.exercises.map((exercise, index) => {
                    const key = `${structureWorkout.day_number}:${slotKey(exercise)}`;
                    const choose = (operation: StructureOperation) => {
                      setSlot(key);
                      setStructureOperation(operation);
                    };
                    return (
                      <div className="program-periodization__plan-week" key={key}>
                        <strong>
                          {index + 1} ·{' '}
                          {exercises.find((item) => item.id === exercise.exercise_id)?.title ??
                            `Упражнение ${exercise.exercise_id}`}
                        </strong>
                        <p className="muted">{describeExercise(exercise, exercises)}</p>
                        <div className="program-periodization__actions">
                          <button
                            type="button"
                            className="secondary"
                            disabled={index === 0 || slotKey(exercise) === null}
                            onClick={() => choose('move_earlier')}
                          >
                            Переместить выше
                          </button>
                          <button
                            type="button"
                            className="secondary"
                            disabled={
                              index === structureWorkout.exercises.length - 1 ||
                              slotKey(exercise) === null
                            }
                            onClick={() => choose('move_later')}
                          >
                            Переместить ниже
                          </button>
                          <button
                            type="button"
                            className="secondary"
                            disabled={
                              structureWorkout.exercises.length <= 1 || slotKey(exercise) === null
                            }
                            onClick={() => choose('remove_exercise')}
                          >
                            Убрать из будущего плана
                          </button>
                        </div>
                        {slot === key && structureOperation && (
                          <p role="status">
                            Выбрано:{' '}
                            {structureOperation === 'remove_exercise'
                              ? 'убрать упражнение'
                              : structureOperation === 'move_earlier'
                                ? 'переместить выше'
                                : 'переместить ниже'}
                          </p>
                        )}
                      </div>
                    );
                  })}
                  <button
                    type="button"
                    className="secondary"
                    disabled={structureWorkout.exercises.length >= 20}
                    onClick={() => {
                      const next = newAssignmentSlot();
                      if (!next) {
                        setError(
                          'Не удалось создать безопасную позицию упражнения на этом устройстве.',
                        );
                        return;
                      }
                      setError('');
                      setSlot('');
                      setNewSlotId(next);
                      setNewExerciseId(null);
                      setSets(3);
                      setReps('8-12');
                      setMinutes(30);
                      setRest(90);
                      setStructureOperation('add_exercise');
                    }}
                  >
                    Добавить упражнение
                  </button>
                  {structureOperation === 'add_exercise' && (
                    <>
                      <label className="field">
                        <span>Новое упражнение</span>
                        <select
                          value={newExerciseId ?? ''}
                          onChange={(event) => setNewExerciseId(Number(event.target.value) || null)}
                        >
                          <option value="">Выберите упражнение</option>
                          {exercises.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.title}
                            </option>
                          ))}
                        </select>
                      </label>
                      {newExerciseId !== null &&
                        (exercises.find((item) => item.id === newExerciseId)?.metric_type ===
                        'cardio' ? (
                          <label className="field">
                            <span>Минуты</span>
                            <input
                              type="number"
                              min="1"
                              max="600"
                              value={minutes}
                              onChange={(event) => setMinutes(Number(event.target.value))}
                            />
                          </label>
                        ) : (
                          <div className="program-periodization__fields">
                            <label className="field">
                              <span>Подходы</span>
                              <input
                                type="number"
                                min="1"
                                max="10"
                                value={sets}
                                onChange={(event) => setSets(Number(event.target.value))}
                              />
                            </label>
                            <label className="field">
                              <span>Повторы</span>
                              <input
                                maxLength={32}
                                value={reps}
                                onChange={(event) => setReps(event.target.value)}
                              />
                            </label>
                            <label className="field">
                              <span>Отдых, сек</span>
                              <input
                                type="number"
                                min="15"
                                max="600"
                                value={rest}
                                onChange={(event) => setRest(Number(event.target.value))}
                              />
                            </label>
                          </div>
                        ))}
                    </>
                  )}
                  <p className="muted">
                    Группы упражнений и последний оставшийся элемент сохраняются без изменений.
                  </p>
                </>
              )}
              {action === actionValues.days && (
                <>
                  <p className="muted">Состав дней начиная с выбранной недели.</p>
                  {selectedWeek.workouts.map((workout, index) => (
                    <div className="program-periodization__plan-week" key={workout.day_number}>
                      <strong>{workout.title}</strong>
                      <p className="muted">
                        {workout.scheduled_date} · упражнений: {workout.exercises.length}
                      </p>
                      <button
                        type="button"
                        className="secondary"
                        disabled={index === 0}
                        onClick={() => {
                          setCopyDay(null);
                          setDayToRemove(null);
                          setSwapDays([
                            workout.day_number,
                            selectedWeek.workouts[index - 1]!.day_number,
                          ]);
                        }}
                      >
                        Переместить выше
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          setCopyDay(null);
                          setSwapDays(null);
                          setDayToRemove(workout.day_number);
                        }}
                      >
                        Убрать из будущего плана
                      </button>
                      {dayToRemove === workout.day_number && (
                        <p role="status">Выбрано: убрать этот день из выбранной области.</p>
                      )}
                      {swapDays?.[0] === workout.day_number && (
                        <p role="status">Выбрано: поменять даты этих дней в выбранной области.</p>
                      )}
                    </div>
                  ))}
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      const first = selectedWeek.workouts[0];
                      if (!first) return;
                      const used = selectedWeek.workouts.map(
                        (item) =>
                          (new Date(`${item.scheduled_date}T00:00:00Z`).getUTCDay() + 6) % 7,
                      );
                      setDayToRemove(null);
                      setSwapDays(null);
                      setCopyDay(first.day_number);
                      setNewDayWeekday(
                        [0, 1, 2, 3, 4, 5, 6].find((day) => !used.includes(day)) ?? 0,
                      );
                      setNewDayTitle(`${first.title} · копия`.slice(0, 128));
                    }}
                  >
                    Добавить тренировочный день
                  </button>
                  {copyDay !== null && (
                    <>
                      <label className="field">
                        <span>Скопировать состав дня</span>
                        <select
                          value={copyDay}
                          onChange={(event) => setCopyDay(Number(event.target.value))}
                        >
                          {selectedWeek.workouts.map((workout) => (
                            <option key={workout.day_number} value={workout.day_number}>
                              {workout.title}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>Название дня</span>
                        <input
                          maxLength={128}
                          value={newDayTitle}
                          onChange={(event) => setNewDayTitle(event.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>День недели</span>
                        <select
                          value={newDayWeekday}
                          onChange={(event) => setNewDayWeekday(Number(event.target.value))}
                        >
                          {[
                            'Понедельник',
                            'Вторник',
                            'Среда',
                            'Четверг',
                            'Пятница',
                            'Суббота',
                            'Воскресенье',
                          ].map((label, index) => (
                            <option key={label} value={index}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </label>
                    </>
                  )}
                  <p className="muted">
                    Начатые и выполненные тренировки сохранятся. Напоминания отменённых тренировок
                    будут отменены.
                  </p>
                </>
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
                            `${workout.day_number}:${slotKey(exercise)}` === event.target.value,
                        )?.exercise;
                        if (next) {
                          setReplacementId(next.exercise_id);
                          setDetailed(false);
                          setPrescriptionDraft(null);
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
                          key={`${workout.day_number}:${slotKey(exercise)}:${index}`}
                          value={`${workout.day_number}:${slotKey(exercise)}`}
                          disabled={slotKey(exercise) === null}
                        >
                          {workout.title} ·{' '}
                          {exercises.find((item) => item.id === exercise.exercise_id)?.title ??
                            `Упражнение ${exercise.exercise_id}`}
                          {slotKey(exercise) === null && ' · измените в тренировке'}
                        </option>
                      ))}
                    </select>
                  </label>
                  {selectedExercise && (
                    <label className="field">
                      <span>Заменить на</span>
                      <select
                        value={replacementId ?? selectedExercise.exercise.exercise_id}
                        onChange={(event) => {
                          setReplacementId(Number(event.target.value));
                          setImpact(null);
                        }}
                      >
                        {!exercises.some(
                          (item) => item.id === selectedExercise.exercise.exercise_id,
                        ) && (
                          <option value={selectedExercise.exercise.exercise_id}>
                            Упражнение {selectedExercise.exercise.exercise_id}
                          </option>
                        )}
                        {exercises
                          .filter(
                            (item) => item.metric_type === selectedExercise.exercise.metric_type,
                          )
                          .map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.title}
                            </option>
                          ))}
                      </select>
                    </label>
                  )}
                  {selectedExercise && planIsSimple && !detailed && (
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
                          min={selectedExercise.exercise.metric_type === strengthMetric ? 15 : 0}
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
                  {selectedExercise &&
                    selectedExercise.exercise.metric_type === strengthMetric &&
                    (editDetailed ? (
                      <ActivePrescriptionEditor
                        key={slot}
                        initial={planIsSimple ? null : selectedExercise.exercise.prescription}
                        sets={sets}
                        reps={reps}
                        rest={rest}
                        onChange={setPrescriptionDraft}
                      />
                    ) : (
                      <button type="button" className="secondary" onClick={() => setDetailed(true)}>
                        Настроить предписание подходов
                      </button>
                    ))}
                  {selectedExercise &&
                    selectedExercise.exercise.metric_type !== strengthMetric &&
                    !planIsSimple && (
                      <p className="field-error">
                        Сложное кардио-предписание пока нельзя изменить без потери структуры.
                      </p>
                    )}
                </>
              )}
              {(action === actionValues.type ||
                action === actionValues.exercise ||
                action === actionValues.structure ||
                action === actionValues.days) && (
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
                      ['future', 'Все будущие недели', 'Начиная с выбранной недели.'],
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
                    (action === actionValues.type ||
                      action === actionValues.exercise ||
                      action === actionValues.structure ||
                      action === actionValues.days) &&
                    (futureSelectedWeeks.length === 0 || futureSelectedWeeks.length > 100)) ||
                  (action === actionValues.duration &&
                    (!Number.isSafeInteger(nextDuration) ||
                      nextDuration < 1 ||
                      nextDuration === duration)) ||
                  (action === actionValues.cycle &&
                    (!Number.isSafeInteger(cycleLength) ||
                      cycleLength < 1 ||
                      cycleLength > 20000 ||
                      cycleOrder.length !== cycleLength ||
                      cycleOrder.some(
                        (item) =>
                          !Number.isSafeInteger(item) ||
                          item < 1 ||
                          item > selectedWeek.cycle_length,
                      ) ||
                      (!cycleRepeat && duration - week + 1 > cycleLength))) ||
                  (action === actionValues.structure &&
                    (structureOperation === 'add_exercise'
                      ? !newSlotId ||
                        !newExerciseId ||
                        (exercises.find((item) => item.id === newExerciseId)?.metric_type ===
                        'cardio'
                          ? !Number.isInteger(minutes) || minutes < 1 || minutes > 600
                          : !Number.isInteger(sets) ||
                            sets < 1 ||
                            sets > 10 ||
                            !reps.trim() ||
                            !Number.isInteger(rest) ||
                            rest < 15 ||
                            rest > 600)
                      : !selectedExercise || !structureOperation)) ||
                  (action === actionValues.days &&
                    dayToRemove === null &&
                    !swapDays &&
                    (copyDay === null || !newDayTitle.trim())) ||
                  (action === actionValues.exercise &&
                    (!selectedExercise ||
                      (!planIsSimple && selectedExercise.exercise.metric_type !== strengthMetric) ||
                      (editDetailed
                        ? !prescriptionDraft
                        : (selectedExercise.exercise.metric_type === strengthMetric
                            ? sets < 1 || sets > 10 || !reps.trim() || rest < 15
                            : minutes < 1 || minutes > 600 || rest < 0) || rest > 600)))
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
