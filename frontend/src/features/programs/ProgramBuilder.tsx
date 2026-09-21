import { useEffect, useId, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type { Exercise, ProgramTemplate, ProgramTemplateCreate } from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Badge, Card, LoadingState, TrashIcon } from '../../shared/ui/common';
import { difficultyLabels, orderExercisesForLevel } from './exerciseOrdering';
import { buildStrengthPreset, resolveStrengthRule, type StrengthSplit } from './strengthPresets';
import { usePersistentState } from '../../shared/storage';
import { programDraftStorageKey } from '../../shared/userScopedStorage';
import { useAuth } from '../../app/AuthProvider';
import { AppLink } from '../../shared/navigation/router';
import { dateInputValue, detectedTimeZone } from '../../shared/dateTime';
import { applyRestSeconds } from './programRest';
import { ExerciseGuideDialog } from '../exercises/ExerciseGuideDialog';
import { ExerciseMediaAsset } from '../exercises/ExerciseMediaAsset';
import { normalizeExerciseSearchText, rankExercisesForSearch } from '../exercises/exerciseSearch';
import { scheduleWeekdaysForSave, templateDraftTitle } from './templateEditing';
import { DateInput } from '../../shared/ui/PickerInput';
import { Icon } from '../../shared/ui/Icon';
import {
  productEventSurface,
  trackCoreProductEvent,
  trackGrowthEvent,
  trackProductEvent,
} from '../../shared/analytics/productEvents';
import { isPairedWithPrevious, moveItem, removeExercise, toggleSuperset } from './programDraft';
import {
  SIMPLE_PROGRAM_DEFAULTS,
  simpleTrainingTitle,
  trainingCountLabel,
} from './programDefaults';

type Day = ProgramTemplateCreate['days'][number];
type ProgramTemplateAssignmentCreate = ProgramTemplateCreate & {
  start_date: string;
  duration_weeks: number;
  schedule_weekdays: number[] | null;
  replace_active: boolean;
};
const blankExercise = (
  restSeconds: number = SIMPLE_PROGRAM_DEFAULTS.restSeconds,
): Day['exercises'][number] => ({
  exercise_id: 0,
  prescribed_sets: 3,
  prescribed_reps: '8-12',
  prescribed_duration_minutes: null,
  rest_seconds: restSeconds,
  notes: '',
});
const blankDay = (index: number): Day => ({
  title: simpleTrainingTitle(index),
  exercises: [blankExercise()],
});
const weekdayLabels = [
  'Понедельник',
  'Вторник',
  'Среда',
  'Четверг',
  'Пятница',
  'Суббота',
  'Воскресенье',
];

function weekdayFromDate(value: string): number {
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.valueOf()) ? 0 : (date.getUTCDay() + 6) % 7;
}

function scheduleForDays(dayCount: number, startDate: string): number[] {
  const firstWeekday = weekdayFromDate(startDate);
  return Array.from({ length: dayCount }, (_, index) => (firstWeekday + index) % 7);
}

function ExercisePicker({
  exercises,
  level,
  value,
  onChange,
  onOpenGuide,
}: {
  exercises: Exercise[];
  level: ProgramTemplateCreate['level'];
  value: number;
  onChange: (id: number) => void;
  onOpenGuide: (exercise: Exercise) => void;
}) {
  const selected = exercises.find((exercise) => exercise.id === value);
  const resultsId = useId();
  const [query, setQuery] = useState(selected?.title ?? '');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const results = useMemo(() => {
    const ranked = rankExercisesForSearch(exercises, query);
    return normalizeExerciseSearchText(query) ? ranked : orderExercisesForLevel(ranked, level);
  }, [exercises, level, query]);

  const currentActiveIndex = Math.min(activeIndex, Math.max(0, results.length - 1));
  const chooseExercise = (exercise: Exercise) => {
    onChange(exercise.id);
    setQuery(exercise.title);
    setOpen(false);
  };

  return (
    <div
      className="exercise-picker"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <input
        type="search"
        role="combobox"
        aria-label="Поиск упражнения"
        aria-expanded={open}
        aria-controls={resultsId}
        aria-activedescendant={
          open && results[currentActiveIndex]
            ? `${resultsId}-${results[currentActiveIndex].id}`
            : undefined
        }
        autoComplete="off"
        enterKeyHint="search"
        value={query}
        placeholder="Начните вводить название"
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          setActiveIndex(0);
          setOpen(true);
          if (value) onChange(0);
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            event.preventDefault();
            setOpen(true);
            setActiveIndex((index) => Math.min(results.length - 1, index + 1));
          } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            setOpen(true);
            setActiveIndex((index) => Math.max(0, index - 1));
          } else if (event.key === 'Enter' && open && results[currentActiveIndex]) {
            event.preventDefault();
            chooseExercise(results[currentActiveIndex]);
          } else if (event.key === 'Escape') {
            setOpen(false);
          }
        }}
      />
      {open && (
        <div className="exercise-picker__results">
          {results.length ? (
            <>
              <div className="exercise-picker__options" id={resultsId} role="listbox">
                {results.map((exercise) => (
                  <button
                    type="button"
                    role="option"
                    id={`${resultsId}-${exercise.id}`}
                    tabIndex={-1}
                    aria-selected={exercise.id === value}
                    className="exercise-picker__option"
                    key={exercise.id}
                    onClick={() => chooseExercise(exercise)}
                  >
                    <ExerciseMediaAsset
                      animationUrl={exercise.media_animation_url}
                      alt={`${exercise.title}: изображение упражнения`}
                      className="exercise-picker__option-thumb"
                      thumbnailUrl={exercise.media_thumbnail_url}
                      variant="thumbnail"
                    />
                    <span className="exercise-picker__option-copy">
                      <strong>{exercise.title}</strong>
                      <span className="exercise-picker__meta">
                        <small>
                          {exercise.primary_muscle || 'Все мышцы'} ·{' '}
                          {exercise.equipment || 'Без оборудования'}
                        </small>
                        <span className="badge">{difficultyLabels[exercise.difficulty_level]}</span>
                        {exercise.is_custom && <span className="badge">Своё</span>}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
              <div className="exercise-picker__guides" aria-label="Техника упражнений" role="group">
                {results.map((exercise) => (
                  <button
                    type="button"
                    className="text-button exercise-picker__guide"
                    aria-label={`${exercise.has_guide ? 'Техника' : 'Подробнее'}: ${exercise.title}`}
                    key={exercise.id}
                    onPointerDown={(event) => {
                      event.preventDefault();
                      onOpenGuide(exercise);
                    }}
                    onClick={(event) => {
                      if (event.detail === 0) onOpenGuide(exercise);
                    }}
                  >
                    {exercise.has_guide ? 'Техника' : 'Подробнее'}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <span className="exercise-picker__empty" id={resultsId} role="status">
              Ничего не найдено
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export function ProgramBuilder({
  targetTelegramId,
  targetName,
  editingTemplate,
  saveAsCopy = false,
  defaultOpen = false,
  onSaved,
}: {
  targetTelegramId?: number | null;
  targetName?: string | null;
  editingTemplate?: ProgramTemplate | null;
  saveAsCopy?: boolean;
  defaultOpen?: boolean;
  onSaved?: () => void;
}) {
  const { toast, confirm } = useFeedback();
  const { user, reloadUser } = useAuth();
  const queryClient = useQueryClient();
  const draftScope = editingTemplate
    ? `template_${saveAsCopy ? 'copy_' : ''}${editingTemplate.id}`
    : targetTelegramId
      ? `client_${targetTelegramId}`
      : `user_${user?.id ?? 'me'}`;
  const [title, setTitle, clearTitleDraft] = usePersistentState(
    programDraftStorageKey('title', draftScope),
    editingTemplate
      ? templateDraftTitle(editingTemplate, saveAsCopy)
      : SIMPLE_PROGRAM_DEFAULTS.title,
  );
  const [goal, setGoal, clearGoalDraft] = usePersistentState<ProgramTemplateCreate['goal']>(
    programDraftStorageKey('goal', draftScope),
    (editingTemplate?.goal as ProgramTemplateCreate['goal'] | undefined) ??
      SIMPLE_PROGRAM_DEFAULTS.goal,
  );
  const [level, setLevel, clearLevelDraft] = usePersistentState<ProgramTemplateCreate['level']>(
    programDraftStorageKey('level', draftScope),
    (editingTemplate?.level as ProgramTemplateCreate['level'] | undefined) ??
      SIMPLE_PROGRAM_DEFAULTS.level,
  );
  const [days, setDays, clearDaysDraft] = usePersistentState<Day[]>(
    programDraftStorageKey('days', draftScope),
    editingTemplate?.days.map((day) => ({
      title: day.title,
      exercises: day.exercises.map((exercise) => ({
        exercise_id: exercise.exercise_id,
        prescribed_sets: exercise.prescribed_sets,
        prescribed_reps: exercise.prescribed_reps,
        prescribed_duration_minutes: exercise.prescribed_duration_minutes,
        rest_seconds: exercise.rest_seconds,
        notes: exercise.notes,
        superset_group: exercise.superset_group,
        superset_order: exercise.superset_order,
      })),
    })) ?? [blankDay(1)],
  );
  const [defaultRestSeconds, setDefaultRestSeconds, clearDefaultRestDraft] =
    usePersistentState<number>(
      programDraftStorageKey('rest', draftScope),
      SIMPLE_PROGRAM_DEFAULTS.restSeconds,
    );
  const defaultStartDate = dateInputValue(
    new Date(),
    user?.profile?.timezone || detectedTimeZone(),
  );
  const [startDate, setStartDate, clearStartDateDraft] = usePersistentState(
    programDraftStorageKey('start', draftScope),
    defaultStartDate,
  );
  const [durationWeeks, setDurationWeeks, clearDurationDraft] = usePersistentState<number>(
    programDraftStorageKey('duration', draftScope),
    SIMPLE_PROGRAM_DEFAULTS.durationWeeks,
  );
  const [scheduleWeekdays, setScheduleWeekdays, clearScheduleDraft] = usePersistentState<number[]>(
    programDraftStorageKey('weekdays', draftScope),
    [],
  );
  const [split, setSplit] = useState<StrengthSplit>('upper_lower');
  const [guide, setGuide] = useState<{ id: number; title: string } | null>(null);
  const [creationSuccess, setCreationSuccess] = useState<{ canStartToday: boolean } | null>(null);
  const exercises = useQuery({
    queryKey: ['exercises'],
    queryFn: () => api<Exercise[]>('/api/v1/programs/exercises'),
  });

  const effectiveScheduleWeekdays =
    scheduleWeekdays.length === days.length
      ? scheduleWeekdays
      : scheduleForDays(days.length, startDate);
  const scheduleOffsets = effectiveScheduleWeekdays.map(
    (weekday) => (weekday - (effectiveScheduleWeekdays[0] ?? weekday) + 7) % 7,
  );
  const usesSequentialCycle = days.length > 7;
  const scheduleIsValid =
    usesSequentialCycle ||
    (effectiveScheduleWeekdays.length === days.length &&
      new Set(effectiveScheduleWeekdays).size === effectiveScheduleWeekdays.length &&
      scheduleOffsets.every(
        (offset, index) => index === 0 || offset > scheduleOffsets[index - 1]!,
      ));
  const updateTemplatePath =
    editingTemplate && !saveAsCopy ? `/api/v1/programs/templates/${editingTemplate.id}` : null;

  const mutation = useMutation({
    mutationFn: ({ replaceActive }: { replaceActive: boolean }) =>
      api(updateTemplatePath ?? '/api/v1/programs/templates', {
        method: updateTemplatePath ? 'PATCH' : 'POST',
        body: {
          title,
          goal,
          level,
          mode: targetTelegramId ? 'coach' : 'self',
          target_telegram_user_id: targetTelegramId || null,
          target_full_name: targetName || null,
          assign_after_create: !editingTemplate,
          start_date: startDate,
          duration_weeks: durationWeeks,
          schedule_weekdays: scheduleWeekdaysForSave(days.length, effectiveScheduleWeekdays),
          replace_active: replaceActive,
          days: days.map((day) => ({
            ...day,
            exercises: day.exercises.filter((item) => item.exercise_id > 0),
          })),
        } satisfies ProgramTemplateAssignmentCreate,
      }),
    onSuccess: async () => {
      if (!editingTemplate) {
        trackGrowthEvent('program_added');
        if (targetTelegramId) {
          trackProductEvent({
            name: 'trainer_program_assigned',
            surface: productEventSurface(),
          });
        } else {
          trackCoreProductEvent(
            { name: 'program_activated', surface: productEventSurface() },
            'program_activated',
          );
        }
      }
      toast(
        saveAsCopy
          ? 'Личная копия программы создана'
          : editingTemplate
            ? 'Изменения программы сохранены'
            : targetTelegramId
              ? 'Программа создана и назначена'
              : 'Программа создана',
      );
      if (!editingTemplate && !targetTelegramId) {
        setCreationSuccess({
          canStartToday:
            startDate === defaultStartDate &&
            effectiveScheduleWeekdays[0] === weekdayFromDate(defaultStartDate),
        });
      }
      clearTitleDraft(
        editingTemplate
          ? templateDraftTitle(editingTemplate, saveAsCopy)
          : SIMPLE_PROGRAM_DEFAULTS.title,
      );
      clearGoalDraft(
        (editingTemplate?.goal as ProgramTemplateCreate['goal'] | undefined) ??
          SIMPLE_PROGRAM_DEFAULTS.goal,
      );
      clearLevelDraft(
        (editingTemplate?.level as ProgramTemplateCreate['level'] | undefined) ??
          SIMPLE_PROGRAM_DEFAULTS.level,
      );
      clearDaysDraft([blankDay(1)]);
      clearDefaultRestDraft(SIMPLE_PROGRAM_DEFAULTS.restSeconds);
      clearStartDateDraft(defaultStartDate);
      clearDurationDraft(SIMPLE_PROGRAM_DEFAULTS.durationWeeks);
      clearScheduleDraft([]);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['templates'] }),
        queryClient.invalidateQueries({ queryKey: ['workout'] }),
        queryClient.invalidateQueries({ queryKey: ['coach', 'programs'] }),
        reloadUser(),
      ]);
      onSaved?.();
    },
    onError: async (reason, variables) => {
      if (
        reason instanceof ApiError &&
        reason.status === 409 &&
        !variables.replaceActive &&
        reason.message.toLowerCase().includes('confirmation')
      ) {
        if (
          await confirm({
            title: 'Заменить активную программу?',
            message: targetTelegramId
              ? 'Текущая программа клиента будет отправлена в архив. Тренировку, которая уже идёт, заменить нельзя.'
              : 'Текущая программа будет отправлена в архив. Тренировку, которая уже идёт, заменить нельзя.',
            confirmText: 'Заменить программу',
          })
        )
          mutation.mutate({ replaceActive: true });
        return;
      }
      toast(
        reason instanceof ApiError && reason.message.toLowerCase().includes('in progress')
          ? 'Сначала завершите текущую тренировку — во время неё программу заменить нельзя.'
          : (reason as Error).message,
        'error',
      );
    },
  });

  const updateDay = (index: number, next: Day | ((current: Day) => Day)) =>
    setDays((currentDays) =>
      currentDays.map((day, dayIndex) =>
        dayIndex === index ? (typeof next === 'function' ? next(day) : next) : day,
      ),
    );
  const rule = resolveStrengthRule(level, split);
  const [presetDays, setPresetDays] = useState<number>(rule.recommended);
  const loadPreset = async () => {
    const hasManualWork = days.some(
      (day) =>
        day.exercises.some((exercise) => exercise.exercise_id > 0) ||
        day.title.trim() !== simpleTrainingTitle(days.indexOf(day) + 1),
    );
    if (
      hasManualWork &&
      !(await confirm({
        title: 'Заменить текущий черновик?',
        message: 'Дни и упражнения из текущего черновика будут заменены силовым шаблоном.',
        confirmText: 'Заменить',
      }))
    )
      return;
    const nextRule = resolveStrengthRule(level, split);
    const normalizedDays = Math.min(nextRule.max, Math.max(nextRule.min, presetDays));
    setPresetDays(normalizedDays);
    setDays(
      applyRestSeconds(
        buildStrengthPreset(exercises.data ?? [], level, split, normalizedDays),
        defaultRestSeconds,
      ),
    );
    setTitle(
      `${{ fullbody: 'Фуллбади', upper_lower: 'Верх/Низ', push_pull_legs: 'Тяни/Толкай/Ноги', split: 'Сплит' }[split]} · ${normalizedDays} дн.`,
    );
    if (nextRule.warning) toast(nextRule.warning, 'error');
    else toast('Силовой шаблон загружен');
  };

  useEffect(() => {
    if (!defaultOpen || editingTemplate || targetTelegramId) return;
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById('program-builder');
      if (!target) return;
      if (target instanceof HTMLDetailsElement) target.open = true;
      target.scrollIntoView({ block: 'start' });
      target.querySelector<HTMLInputElement>('input')?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [defaultOpen, editingTemplate, targetTelegramId]);

  return (
    <Card
      className="program-builder"
      collapsible={false}
      id={!editingTemplate && !targetTelegramId ? 'program-builder' : undefined}
      title={
        editingTemplate
          ? saveAsCopy
            ? 'Настроить личную копию'
            : 'Редактировать программу'
          : targetTelegramId
            ? `Новая программа для ${targetName || targetTelegramId}`
            : 'Создать свою программу'
      }
      description={
        editingTemplate
          ? saveAsCopy
            ? `Настройте личную копию «${editingTemplate.title}»`
            : `Редактирование «${editingTemplate.title}»`
          : targetTelegramId
            ? `Назначение для ${targetName || targetTelegramId}`
            : 'Название уже заполнено — добавьте упражнение и сохраните.'
      }
    >
      {exercises.isLoading ? (
        <LoadingState />
      ) : creationSuccess ? (
        <section className="program-builder-success" role="status">
          <span className="eyebrow">Программа готова</span>
          <h3>
            {creationSuccess.canStartToday
              ? 'Можно переходить к тренировке'
              : 'Программа сохранена и назначена'}
          </h3>
          <p>
            {creationSuccess.canStartToday
              ? 'Первая тренировка уже запланирована на сегодня. Она начнётся только после вашего действия.'
              : 'Откройте «Сегодня» в дату первой тренировки, чтобы начать её.'}
          </p>
          <div className="program-builder-success__actions">
            <AppLink className="button-link" to="/app?section=today">
              {creationSuccess.canStartToday ? 'Перейти к тренировке' : 'Открыть «Сегодня»'}
            </AppLink>
            <button type="button" className="secondary" onClick={() => setCreationSuccess(null)}>
              Создать ещё одну
            </button>
          </div>
        </section>
      ) : (
        <form
          className="stack top-gap"
          onSubmit={async (e) => {
            e.preventDefault();
            let replaceActive = false;
            if (
              !editingTemplate &&
              user?.has_active_program &&
              !(await confirm({
                title: 'Заменить активную программу?',
                message:
                  'Новая программа станет активной, а текущая будет отправлена в архив. Тренировку, которая уже идёт, заменить нельзя.',
                confirmText: 'Создать и заменить',
              }))
            )
              return;
            replaceActive = Boolean(user?.has_active_program);
            mutation.mutate({ replaceActive });
          }}
        >
          {saveAsCopy && (
            <p className="auth-notice">
              Исходный готовый шаблон останется без изменений. После сохранения появится личная
              копия, в которой можно использовать свои упражнения.
            </p>
          )}
          <section className="program-builder-basics stack" aria-labelledby="program-basics-title">
            <div>
              <span className="eyebrow">Шаг 1</span>
              <h3 id="program-basics-title">Основа программы</h3>
            </div>
            <div className="form-grid">
              <label className="field">
                <span>Название</span>
                <input
                  value={title}
                  maxLength={128}
                  enterKeyHint="next"
                  onChange={(e) => setTitle(e.target.value)}
                  required
                />
              </label>
            </div>
          </section>
          <div className="program-builder-days-heading">
            <div>
              <span className="eyebrow">Шаг 2</span>
              <h3>Добавьте упражнения</h3>
              <p>Первая тренировка уже создана. Выберите хотя бы одно упражнение.</p>
            </div>
            <Badge>{days.length} из 8</Badge>
          </div>
          {days.map((day, dayIndex) => (
            <div className="program-day stack" key={dayIndex}>
              <div className="program-day__head">
                <span className="program-day__number">{dayIndex + 1}</span>
                <input
                  aria-label={`Название дня ${dayIndex + 1}`}
                  value={day.title}
                  maxLength={128}
                  required
                  onChange={(e) => updateDay(dayIndex, { ...day, title: e.target.value })}
                />
                <div className="program-order-controls" aria-label={`Порядок дня ${dayIndex + 1}`}>
                  <button
                    type="button"
                    className="secondary"
                    aria-label={`Переместить день ${dayIndex + 1} выше`}
                    disabled={dayIndex === 0}
                    onClick={() =>
                      setDays((currentDays) => moveItem(currentDays, dayIndex, dayIndex - 1))
                    }
                  >
                    <Icon name="move-up" size={20} />
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    aria-label={`Переместить день ${dayIndex + 1} ниже`}
                    disabled={dayIndex === days.length - 1}
                    onClick={() =>
                      setDays((currentDays) => moveItem(currentDays, dayIndex, dayIndex + 1))
                    }
                  >
                    <Icon name="move-down" size={20} />
                  </button>
                  {days.length > 1 && (
                    <button
                      type="button"
                      className="btn-danger"
                      aria-label={`Удалить день ${dayIndex + 1}`}
                      onClick={() =>
                        setDays((currentDays) =>
                          currentDays.filter((_, index) => index !== dayIndex),
                        )
                      }
                    >
                      <TrashIcon />
                    </button>
                  )}
                </div>
              </div>
              {day.exercises.map((item, exerciseIndex) => (
                <div className="program-exercise-row" key={exerciseIndex}>
                  <div className="field exercise-select">
                    <span className="program-exercise-row__heading">
                      <span>
                        <span className="program-exercise-row__number">{exerciseIndex + 1}</span>
                        <strong>Упражнение</strong>
                      </span>
                      <span
                        className="program-exercise-row__actions"
                        aria-label={`Действия с упражнением ${exerciseIndex + 1}`}
                      >
                        <button
                          type="button"
                          className="secondary"
                          aria-label={`Переместить упражнение ${exerciseIndex + 1} выше`}
                          disabled={exerciseIndex === 0}
                          onClick={() =>
                            updateDay(dayIndex, (currentDay) => ({
                              ...currentDay,
                              exercises: moveItem(
                                currentDay.exercises,
                                exerciseIndex,
                                exerciseIndex - 1,
                              ),
                            }))
                          }
                        >
                          <Icon name="move-up" size={20} />
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          aria-label={`Переместить упражнение ${exerciseIndex + 1} ниже`}
                          disabled={exerciseIndex === day.exercises.length - 1}
                          onClick={() =>
                            updateDay(dayIndex, (currentDay) => ({
                              ...currentDay,
                              exercises: moveItem(
                                currentDay.exercises,
                                exerciseIndex,
                                exerciseIndex + 1,
                              ),
                            }))
                          }
                        >
                          <Icon name="move-down" size={20} />
                        </button>
                        <button
                          type="button"
                          className="btn-danger"
                          aria-label={`Удалить упражнение ${exerciseIndex + 1} из дня ${dayIndex + 1}`}
                          onClick={() =>
                            updateDay(dayIndex, (currentDay) =>
                              removeExercise(currentDay, exerciseIndex),
                            )
                          }
                        >
                          <TrashIcon />
                        </button>
                      </span>
                    </span>
                    <ExercisePicker
                      key={`${exerciseIndex}-${item.exercise_id}`}
                      exercises={exercises.data ?? []}
                      level={level}
                      value={item.exercise_id}
                      onOpenGuide={(exercise) =>
                        setGuide({ id: exercise.id, title: exercise.title })
                      }
                      onChange={(exerciseId) => {
                        const selected = exercises.data?.find(
                          (exercise) => exercise.id === exerciseId,
                        );
                        updateDay(dayIndex, {
                          ...day,
                          exercises: day.exercises.map((row, index) => {
                            if (index !== exerciseIndex) return row;
                            if (selected?.metric_type === 'cardio') {
                              return {
                                ...row,
                                exercise_id: exerciseId,
                                prescribed_sets: null,
                                prescribed_reps: null,
                                prescribed_duration_minutes: row.prescribed_duration_minutes ?? 30,
                                superset_group: null,
                                superset_order: null,
                              };
                            }
                            return {
                              ...row,
                              exercise_id: exerciseId,
                              prescribed_sets: row.prescribed_sets ?? 3,
                              prescribed_reps: row.prescribed_reps || '8-12',
                              prescribed_duration_minutes: null,
                            };
                          }),
                        });
                      }}
                    />
                    {exercises.data?.some((exercise) => exercise.id === item.exercise_id) && (
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => {
                          const selected = exercises.data?.find(
                            (exercise) => exercise.id === item.exercise_id,
                          );
                          if (selected) setGuide({ id: selected.id, title: selected.title });
                        }}
                      >
                        {exercises.data?.find((exercise) => exercise.id === item.exercise_id)
                          ?.has_guide
                          ? 'Техника и детали'
                          : 'Подробнее об упражнении'}
                      </button>
                    )}
                  </div>
                  <div className="program-exercise-row__metrics">
                    {exercises.data?.find((exercise) => exercise.id === item.exercise_id)
                      ?.metric_type === 'cardio' ? (
                      <label className="field">
                        <span>Плановая длительность, мин</span>
                        <input
                          type="number"
                          inputMode="numeric"
                          min="1"
                          max="600"
                          required
                          value={item.prescribed_duration_minutes ?? ''}
                          onChange={(event) =>
                            updateDay(dayIndex, {
                              ...day,
                              exercises: day.exercises.map((row, index) =>
                                index === exerciseIndex
                                  ? {
                                      ...row,
                                      prescribed_duration_minutes: Number(event.target.value),
                                    }
                                  : row,
                              ),
                            })
                          }
                        />
                      </label>
                    ) : (
                      (
                        [
                          ['prescribed_sets', 'Рабочие подходы'],
                          ['prescribed_reps', 'Повторы'],
                          ['rest_seconds', 'Отдых, сек'],
                        ] as const
                      ).map(([key, label]) => (
                        <label className="field" key={key}>
                          <span>{label}</span>
                          <input
                            type={key === 'prescribed_reps' ? 'text' : 'number'}
                            inputMode={key === 'prescribed_reps' ? undefined : 'numeric'}
                            min={
                              key === 'prescribed_sets'
                                ? 1
                                : key === 'rest_seconds'
                                  ? 15
                                  : undefined
                            }
                            max={
                              key === 'prescribed_sets'
                                ? 10
                                : key === 'rest_seconds'
                                  ? 600
                                  : undefined
                            }
                            maxLength={key === 'prescribed_reps' ? 32 : undefined}
                            required
                            value={item[key] ?? ''}
                            onChange={(e) =>
                              updateDay(dayIndex, {
                                ...day,
                                exercises: day.exercises.map((row, index) =>
                                  index === exerciseIndex
                                    ? {
                                        ...row,
                                        [key]:
                                          key === 'prescribed_reps'
                                            ? e.target.value
                                            : Number(e.target.value),
                                      }
                                    : row,
                                ),
                              })
                            }
                          />
                        </label>
                      ))
                    )}
                  </div>
                  <details className="program-exercise-advanced compact-disclosure">
                    <summary>
                      <span>
                        <strong>
                          {exercises.data?.find((exercise) => exercise.id === item.exercise_id)
                            ?.metric_type === 'cardio'
                            ? 'Заметка и замены'
                            : 'Заметка, суперсет и замены'}
                        </strong>
                        <small>Необязательные настройки упражнения</small>
                      </span>
                      <Icon name="plus" size={16} />
                    </summary>
                    <div className="program-exercise-advanced__body">
                      <label className="field exercise-notes">
                        <span>Заметка к упражнению</span>
                        <input
                          maxLength={2000}
                          value={item.notes ?? ''}
                          placeholder="Например: выполнять медленно, без рывков"
                          onChange={(event) =>
                            updateDay(dayIndex, {
                              ...day,
                              exercises: day.exercises.map((row, index) =>
                                index === exerciseIndex
                                  ? { ...row, notes: event.target.value }
                                  : row,
                              ),
                            })
                          }
                        />
                      </label>
                      {exerciseIndex > 0 &&
                        exercises.data?.find((exercise) => exercise.id === item.exercise_id)
                          ?.metric_type !== 'cardio' && (
                          <label className="checkbox-row">
                            <input
                              type="checkbox"
                              checked={isPairedWithPrevious(day, exerciseIndex)}
                              onChange={(event) =>
                                updateDay(
                                  dayIndex,
                                  toggleSuperset(day, exerciseIndex, event.target.checked),
                                )
                              }
                            />
                            <span>Суперсет — выполнить вместе с предыдущим упражнением подряд</span>
                          </label>
                        )}
                      {(() => {
                        const selected = exercises.data?.find(
                          (exercise) => exercise.id === item.exercise_id,
                        );
                        const alternatives = (selected?.alternatives ?? [])
                          .map((alternative) =>
                            exercises.data?.find((exercise) => exercise.id === alternative.id),
                          )
                          .filter((exercise): exercise is Exercise => Boolean(exercise));
                        return alternatives.length ? (
                          <div className="program-exercise-alternatives">
                            <strong>Проверенные замены</strong>
                            <div className="toolbar wrap">
                              {alternatives.map((alternative) => (
                                <button
                                  type="button"
                                  className="text-button"
                                  key={alternative.id}
                                  onClick={() =>
                                    updateDay(dayIndex, {
                                      ...day,
                                      exercises: day.exercises.map((row, index) =>
                                        index === exerciseIndex
                                          ? { ...row, exercise_id: alternative.id }
                                          : row,
                                      ),
                                    })
                                  }
                                >
                                  Заменить на «{alternative.title}»
                                </button>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <small className="muted">Проверенных замен пока нет.</small>
                        );
                      })()}
                      {exercises.data?.find((exercise) => exercise.id === item.exercise_id)
                        ?.metric_type !== 'cardio' && (
                        <small className="muted">
                          Разминочные и дроп-сеты отмечаются отдельно во время тренировки.
                        </small>
                      )}
                    </div>
                  </details>
                </div>
              ))}
              {day.exercises.length < 20 ? (
                <button
                  type="button"
                  className="secondary program-add-exercise"
                  onClick={() =>
                    updateDay(dayIndex, (currentDay) => ({
                      ...currentDay,
                      exercises: [...currentDay.exercises, blankExercise(defaultRestSeconds)],
                    }))
                  }
                >
                  <Icon name="plus" size={16} />
                  Добавить упражнение
                </button>
              ) : (
                <span className="muted">В одной тренировке максимум 20 упражнений.</span>
              )}
            </div>
          ))}
          <details className="program-builder-settings compact-disclosure">
            <summary>
              <span>
                <strong>Настройки программы</strong>
                <small>Цель, уровень, расписание, шаблон и общий отдых</small>
              </span>
              <Icon name="plus" size={16} />
            </summary>
            <div className="program-builder-settings__body stack">
              <section
                className="program-builder-section stack"
                aria-labelledby="program-profile-title"
              >
                <h3 id="program-profile-title">Цель и уровень</h3>
                <p className="muted">
                  По умолчанию программа подходит для поддержания формы и начального уровня.
                </p>
                <div className="form-grid">
                  <label className="field">
                    <span>Цель</span>
                    <select
                      value={goal}
                      onChange={(event) =>
                        setGoal(event.target.value as ProgramTemplateCreate['goal'])
                      }
                    >
                      <option value="fat_loss">Похудение</option>
                      <option value="muscle_gain">Набор</option>
                      <option value="maintenance">Поддержание</option>
                      <option value="recomposition">Рекомпозиция</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>Уровень</span>
                    <select
                      value={level}
                      onChange={(event) =>
                        setLevel(event.target.value as ProgramTemplateCreate['level'])
                      }
                    >
                      <option value="beginner">Начальный</option>
                      <option value="intermediate">Средний</option>
                      <option value="advanced">Продвинутый</option>
                    </select>
                  </label>
                </div>
              </section>
              <section
                className="program-builder-section stack"
                aria-labelledby="program-schedule-title"
              >
                <h3 id="program-schedule-title">Расписание</h3>
                <p className="muted">
                  По умолчанию первая тренировка назначается на сегодня, цикл длится одну неделю.
                </p>
                <div className="form-grid">
                  <label className="field">
                    <span>Начать не раньше</span>
                    <DateInput
                      min={defaultStartDate}
                      value={startDate}
                      onChange={(event) => {
                        setStartDate(event.target.value);
                        setScheduleWeekdays(scheduleForDays(days.length, event.target.value));
                      }}
                      required
                    />
                  </label>
                  <label className="field">
                    <span>Длительность, недель</span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min="1"
                      max="24"
                      value={durationWeeks}
                      onChange={(event) => setDurationWeeks(Number(event.target.value))}
                      required
                    />
                  </label>
                </div>
                {usesSequentialCycle ? (
                  <p className="muted">
                    Восьмидневный цикл планируется последовательно и автоматически повторяется после
                    восьмой тренировки.
                  </p>
                ) : (
                  <div className="form-grid">
                    {days.map((day, dayIndex) => (
                      <label className="field" key={`schedule-${dayIndex}`}>
                        <span>{day.title || simpleTrainingTitle(dayIndex + 1)}</span>
                        <select
                          value={effectiveScheduleWeekdays[dayIndex] ?? ''}
                          onChange={(event) =>
                            setScheduleWeekdays(
                              effectiveScheduleWeekdays.map((value, index) =>
                                index === dayIndex ? Number(event.target.value) : value,
                              ),
                            )
                          }
                        >
                          {weekdayLabels.map((label, weekday) => (
                            <option value={weekday} key={label}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </label>
                    ))}
                  </div>
                )}
                {!scheduleIsValid && (
                  <p className="field-error" role="alert">
                    Выберите разные дни недели в порядке тренировок. После воскресенья можно
                    продолжить с понедельника.
                  </p>
                )}
              </section>
              <section
                className="program-builder-section stack"
                aria-labelledby="strength-template-title"
              >
                <h3 id="strength-template-title">Быстрое заполнение</h3>
                <div className="form-grid">
                  <label className="field">
                    <span>Схема</span>
                    <select
                      value={split}
                      onChange={(event) => {
                        const next = event.target.value as StrengthSplit;
                        setSplit(next);
                        setPresetDays(resolveStrengthRule(level, next).recommended);
                      }}
                    >
                      <option value="fullbody">Фуллбади</option>
                      <option value="upper_lower">Верх/Низ</option>
                      <option value="push_pull_legs">Тяни/Толкай/Ноги</option>
                      <option value="split">Сплит</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>
                      Тренировок ({rule.min}–{rule.max})
                    </span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min={rule.min}
                      max={rule.max}
                      value={presetDays}
                      onChange={(event) => setPresetDays(Number(event.target.value))}
                    />
                  </label>
                </div>
                {rule.warning && <p className="muted">{rule.warning}</p>}
                <button type="button" className="secondary" onClick={() => void loadPreset()}>
                  Заполнить по шаблону
                </button>
              </section>
              <section
                className="program-builder-section stack"
                aria-labelledby="program-rest-title"
              >
                <h3 id="program-rest-title">Отдых между подходами</h3>
                <p className="muted">
                  Общий отдых можно применить ко всем упражнениям, а затем изменить точечно.
                </p>
                <div className="toolbar wrap">
                  <label className="field">
                    <span>Общий отдых, сек</span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min="15"
                      max="600"
                      value={defaultRestSeconds}
                      onChange={(event) => setDefaultRestSeconds(Number(event.target.value))}
                      required
                    />
                  </label>
                  <button
                    type="button"
                    className="secondary"
                    disabled={defaultRestSeconds < 15 || defaultRestSeconds > 600}
                    onClick={() => {
                      setDays(applyRestSeconds(days, defaultRestSeconds));
                      toast('Общее время отдыха применено ко всем упражнениям');
                    }}
                  >
                    Применить ко всем упражнениям
                  </button>
                </div>
              </section>
            </div>
          </details>
          <div className="program-builder-footer">
            <div className="program-builder-footer__summary">
              <span className="eyebrow">Шаг 3</span>
              <strong>
                {trainingCountLabel(days.length)} ·{' '}
                {days.reduce(
                  (total, day) =>
                    total + day.exercises.filter((exercise) => exercise.exercise_id > 0).length,
                  0,
                )}{' '}
                упр.
              </strong>
            </div>
            {days.length < 8 ? (
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  setDays((currentDays) => [
                    ...currentDays,
                    {
                      title: simpleTrainingTitle(currentDays.length + 1),
                      exercises: [blankExercise(defaultRestSeconds)],
                    },
                  ])
                }
              >
                <Icon name="plus" size={16} /> Добавить день
              </button>
            ) : (
              <span className="muted">В одном цикле максимум 8 тренировочных дней.</span>
            )}
            <button
              className="program-builder-footer__save"
              disabled={
                mutation.isPending ||
                !scheduleIsValid ||
                durationWeeks < 1 ||
                durationWeeks > 24 ||
                days.some((day) => day.exercises.every((item) => !item.exercise_id))
              }
            >
              {mutation.isPending
                ? 'Сохраняем…'
                : saveAsCopy
                  ? 'Сохранить личную копию'
                  : editingTemplate
                    ? 'Сохранить изменения'
                    : targetTelegramId
                      ? 'Создать и назначить'
                      : 'Создать программу'}
            </button>
          </div>
        </form>
      )}
      {guide && (
        <ExerciseGuideDialog
          exerciseId={guide.id}
          exerciseTitle={guide.title}
          onClose={() => setGuide(null)}
        />
      )}
    </Card>
  );
}
