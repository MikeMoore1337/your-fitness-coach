import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, apiErrorDetailIncludes } from '../../shared/api/client';
import type { Exercise, ProgramTemplate, ProgramTemplateCreate } from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { DisclosureIcon, Badge, Card, LoadingState } from '../../shared/ui/common';
import { orderExercisesForLevel } from './exerciseOrdering';
import { buildStrengthPreset, resolveStrengthRule, type StrengthSplit } from './strengthPresets';
import { usePersistentState } from '../../shared/storage';
import { programDraftStorageKey } from '../../shared/userScopedStorage';
import { useAuth } from '../../app/AuthProvider';
import { AppLink } from '../../shared/navigation/router';
import { dateInputValue, detectedTimeZone } from '../../shared/dateTime';
import { ContextualHelp } from '../../shared/ui/ContextualHelp';
import { applyRestSeconds } from './programRest';
import { ExerciseGuideDialog } from '../exercises/ExerciseGuideDialog';
import { scheduleWeekdaysForSave, templateDraftTitle } from './templateEditing';
import { ProgramDayEditor } from './ProgramDayEditor';
import './ProgramBuilderFocus.css';
import { DateInput } from '../../shared/ui/PickerInput';
import {
  productEventSurface,
  trackCoreProductEvent,
  trackGrowthEvent,
  trackProductEvent,
} from '../../shared/analytics/productEvents';
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

export function ProgramBuilder({
  targetTelegramId,
  targetName,
  editingTemplate,
  saveAsCopy = false,
  defaultOpen = false,
  onSaved,
  onDirtyChange,
}: {
  targetTelegramId?: number | null;
  targetName?: string | null;
  editingTemplate?: ProgramTemplate | null;
  saveAsCopy?: boolean;
  defaultOpen?: boolean;
  onSaved?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const sectionId = useId();
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
    editingTemplate?.assigned_program_start_date ?? defaultStartDate,
  );
  const [durationWeeks, setDurationWeeks, clearDurationDraft] = usePersistentState<number>(
    programDraftStorageKey('duration', draftScope),
    editingTemplate?.assigned_program_duration_weeks ?? SIMPLE_PROGRAM_DEFAULTS.durationWeeks,
  );
  const [scheduleWeekdays, setScheduleWeekdays, clearScheduleDraft] = usePersistentState<number[]>(
    programDraftStorageKey('weekdays', draftScope),
    editingTemplate?.assigned_program_schedule_weekdays ?? [],
  );
  const activeProgramEdit = Boolean(
    editingTemplate &&
    !saveAsCopy &&
    editingTemplate.is_active_for_current_user &&
    editingTemplate.assigned_program_id != null &&
    editingTemplate.current_revision_number != null,
  );
  const [split, setSplit] = useState<StrengthSplit>('upper_lower');
  const [reviewOpen, setReviewOpen] = useState(false);
  const settingsRef = useRef<HTMLDetailsElement>(null);
  const snapshot = JSON.stringify([
    title,
    goal,
    level,
    days,
    defaultRestSeconds,
    startDate,
    durationWeeks,
    scheduleWeekdays,
  ]);
  const originalSnapshot = useRef(snapshot);
  useEffect(() => {
    onDirtyChange?.(snapshot !== originalSnapshot.current);
  }, [onDirtyChange, snapshot]);
  const [guide, setGuide] = useState<{ id: number; title: string } | null>(null);
  const [creationSuccess, setCreationSuccess] = useState<{ canStartToday: boolean } | null>(null);
  const exercises = useQuery({
    queryKey: ['exercises'],
    queryFn: () => api<Exercise[]>('/api/v1/programs/exercises'),
  });
  const orderedExercises = useMemo(
    () => orderExercisesForLevel(exercises.data ?? [], level),
    [exercises.data, level],
  );

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
      api<ProgramTemplate>(updateTemplatePath ?? '/api/v1/programs/templates', {
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
          expected_revision_number: activeProgramEdit
            ? editingTemplate?.current_revision_number
            : undefined,
          replace_active: replaceActive,
          days: days.map((day) => ({
            ...day,
            exercises: day.exercises.filter((item) => item.exercise_id > 0),
          })),
        } satisfies ProgramTemplateAssignmentCreate,
      }),
    onSuccess: async (result) => {
      setReviewOpen(false);
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
        result?.assigned_program_updated
          ? 'Программа сохранена. Будущие тренировки обновлены'
          : saveAsCopy
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
      clearStartDateDraft(result?.assigned_program_start_date ?? defaultStartDate);
      clearDurationDraft(
        result?.assigned_program_duration_weeks ?? SIMPLE_PROGRAM_DEFAULTS.durationWeeks,
      );
      clearScheduleDraft(result?.assigned_program_schedule_weekdays ?? []);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['templates'] }),
        queryClient.invalidateQueries({ queryKey: ['workout'] }),
        queryClient.invalidateQueries({ queryKey: ['assigned-program'] }),
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
        apiErrorDetailIncludes(reason, 'confirmation')
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
        reason instanceof ApiError && reason.status === 409
          ? 'Программа уже изменилась на другом устройстве. Обновите список и повторите сохранение.'
          : apiErrorDetailIncludes(reason, 'in progress')
            ? 'Сначала завершите текущую тренировку — во время неё программу заменить нельзя.'
            : (reason as Error).message,
        'error',
      );
    },
  });

  const totalExercises = days.reduce(
    (count, day) => count + day.exercises.filter((item) => item.exercise_id > 0).length,
    0,
  );
  const reviewIssues: string[] = [];
  if (!title.trim()) reviewIssues.push('Укажите название программы.');
  if (durationWeeks < 1 || durationWeeks > 24)
    reviewIssues.push('Укажите длительность от 1 до 24 недель.');
  if (!scheduleIsValid) reviewIssues.push('Проверьте расписание тренировок.');
  days.forEach((day, index) => {
    if (!day.title.trim()) reviewIssues.push('День ' + (index + 1) + ': укажите название.');
    if (!day.exercises.some((item) => item.exercise_id > 0))
      reviewIssues.push('День ' + (index + 1) + ': добавьте хотя бы одно упражнение.');
    day.exercises
      .filter((item) => item.exercise_id > 0)
      .forEach((item) => {
        const cardio =
          exercises.data?.find((exercise) => exercise.id === item.exercise_id)?.metric_type ===
          'cardio';
        if (
          cardio &&
          (!item.prescribed_duration_minutes ||
            item.prescribed_duration_minutes < 1 ||
            item.prescribed_duration_minutes > 600)
        )
          reviewIssues.push('День ' + (index + 1) + ': проверьте длительность.');
        if (
          !cardio &&
          (!item.prescribed_sets ||
            item.prescribed_sets < 1 ||
            item.prescribed_sets > 10 ||
            !item.prescribed_reps?.trim() ||
            item.rest_seconds == null ||
            item.rest_seconds < 15 ||
            item.rest_seconds > 600)
        )
          reviewIssues.push('День ' + (index + 1) + ': проверьте подходы, повторы и отдых.');
      });
  });
  const submitReviewedProgram = async () => {
    if (mutation.isPending || reviewIssues.length || navigator.onLine === false) return;
    let replaceActive = false;
    if (!editingTemplate && user?.has_active_program) {
      if (
        !(await confirm({
          title: 'Заменить активную программу?',
          message:
            'Текущая программа будет архивирована. Тренировку, которая уже идёт, заменить нельзя.',
          confirmText: 'Создать и заменить',
        }))
      )
        return;
      replaceActive = true;
    }
    mutation.mutate({ replaceActive });
  };
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
      `${{ fullbody: 'Всё тело', upper_lower: 'Верх/низ', push_pull_legs: 'Толкай/тяни/ноги (PPL)', split: 'Сплит' }[split]} · ${normalizedDays} дн.`,
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
            ? 'Редактирование личной копии'
            : 'Редактирование программы'
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
          <div className="program-builder-success__actions app-action-group">
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
          className={
            editingTemplate ? 'stack top-gap program-builder--personal-editor' : 'stack top-gap'
          }
          onSubmit={(event) => {
            event.preventDefault();
            setReviewOpen(true);
          }}
        >
          {saveAsCopy && (
            <p className="auth-notice">
              Исходный готовый шаблон останется без изменений. После сохранения появится личная
              копия, в которой можно использовать свои упражнения.
            </p>
          )}
          <section
            className="program-builder-basics stack"
            aria-labelledby={`${sectionId}-program-basics-title`}
          >
            <div>
              <span className="eyebrow">Шаг 1</span>
              <h3 id={`${sectionId}-program-basics-title`}>Основа программы</h3>
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
              <h3>{editingTemplate ? 'Тренировочные дни' : 'Добавьте упражнения'}</h3>
              <p>
                {editingTemplate
                  ? 'Выберите день и настройте его упражнения.'
                  : 'Первая тренировка уже создана. Выберите хотя бы одно упражнение.'}
              </p>
            </div>
            <Badge>{days.length} из 8</Badge>
          </div>
          <ProgramDayEditor
            days={days}
            setDays={setDays}
            updateDay={updateDay}
            exercises={orderedExercises}
            defaultRestSeconds={defaultRestSeconds}
            onOpenGuide={(exercise) => setGuide({ id: exercise.id, title: exercise.title })}
          />
          <button
            type="button"
            className="secondary program-builder-open-settings"
            onClick={() => {
              if (settingsRef.current) {
                settingsRef.current.open = true;
                settingsRef.current.scrollIntoView?.({ block: 'start' });
              }
            }}
          >
            Настройки и расписание
          </button>
          <details ref={settingsRef} className="program-builder-settings compact-disclosure">
            <summary className="yfc-disclosure-summary">
              <span>
                <strong>Настройки программы</strong>
                <small>Цель, уровень, расписание, шаблон и общий отдых</small>
              </span>
              <DisclosureIcon />
            </summary>
            <div className="program-builder-settings__body stack">
              <section
                className="program-builder-section stack"
                aria-labelledby={`${sectionId}-program-profile-title`}
              >
                <h3 id={`${sectionId}-program-profile-title`}>Цель и уровень</h3>
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
                aria-labelledby={`${sectionId}-program-schedule-title`}
              >
                <h3 id={`${sectionId}-program-schedule-title`}>Расписание</h3>
                <p className="muted">
                  {activeProgramEdit
                    ? 'Дата начала и длительность текущего цикла сохраняются. Здесь можно обновить дни будущих тренировок.'
                    : 'По умолчанию первая тренировка назначается на сегодня, цикл длится одну неделю.'}
                </p>
                <div className="form-grid">
                  <label className="field">
                    <span>Начать не раньше</span>
                    <DateInput
                      disabled={activeProgramEdit}
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
                      disabled={activeProgramEdit}
                      min="1"
                      max="24"
                      value={durationWeeks}
                      onChange={(event) => setDurationWeeks(Number(event.target.value))}
                      required
                    />
                  </label>
                </div>
                {usesSequentialCycle ? (
                  <ContextualHelp summary="Как устроен цикл?">
                    <p>
                      Восьмидневный цикл планируется последовательно и автоматически повторяется
                      после восьмой тренировки.
                    </p>
                  </ContextualHelp>
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
                aria-labelledby={`${sectionId}-strength-template-title`}
              >
                <h3 id={`${sectionId}-strength-template-title`}>Быстрое заполнение</h3>
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
                      <option value="fullbody">Всё тело</option>
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
                aria-labelledby={`${sectionId}-program-rest-title`}
              >
                <h3 id={`${sectionId}-program-rest-title`}>Отдых между подходами</h3>
                <p className="muted">
                  Общий отдых можно применить ко всем упражнениям, а затем изменить точечно.
                </p>
                <div className="toolbar wrap program-builder-rest-actions">
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
            <button
              type="button"
              className="program-builder-footer__save"
              onClick={() => setReviewOpen(true)}
            >
              {editingTemplate || saveAsCopy ? 'Проверить и сохранить' : 'Проверить и назначить'}
            </button>
          </div>
          {reviewOpen && (
            <section
              className="program-builder-review"
              role="dialog"
              aria-modal="false"
              aria-labelledby={sectionId + '-review-title'}
            >
              <h3 id={sectionId + '-review-title'}>Проверка программы</h3>
              <strong>{title || 'Без названия'}</strong>
              <p>
                {trainingCountLabel(days.length)} · {totalExercises} упражнений
              </p>
              <p>
                Начало: {startDate} · {durationWeeks} нед.
              </p>
              <p>
                Расписание:{' '}
                {usesSequentialCycle
                  ? 'Последовательный цикл'
                  : effectiveScheduleWeekdays.map((day) => weekdayLabels[day]).join(', ')}
              </p>
              {reviewIssues.length ? (
                <div className="program-builder-review__errors" role="alert">
                  <strong>Исправьте перед сохранением:</strong>
                  <ul>
                    {reviewIssues.map((message, index) => (
                      <li key={index}>{message}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p role="status">Программа готова к сохранению.</p>
              )}
              {navigator.onLine === false && (
                <p role="alert">Нет соединения. Черновик остаётся на устройстве.</p>
              )}
              {!editingTemplate && user?.has_active_program && (
                <p>При замене текущая программа будет отправлена в архив после подтверждения.</p>
              )}
              <div className="program-builder-review__actions">
                <button type="button" className="secondary" onClick={() => setReviewOpen(false)}>
                  Вернуться к редактированию
                </button>
                <button
                  type="button"
                  disabled={
                    Boolean(reviewIssues.length) || mutation.isPending || navigator.onLine === false
                  }
                  onClick={() => void submitReviewedProgram()}
                >
                  {mutation.isPending
                    ? 'Сохраняем…'
                    : saveAsCopy
                      ? 'Сохранить личную копию'
                      : editingTemplate
                        ? 'Сохранить изменения'
                        : 'Создать и назначить'}
                </button>
              </div>
            </section>
          )}
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
