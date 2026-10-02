import { useId, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type {
  Workout,
  WorkoutAdaptationApply,
  WorkoutAdaptationPreview,
  WorkoutAdaptationRequest,
  WorkoutAlternative,
} from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Button, CloseIcon, Field, IconButton, Input, Select } from '../../shared/ui/common';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { Icon } from '../../shared/ui/Icon';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';

type AdaptationReason = WorkoutAdaptationRequest['reason'];
type EquipmentId = NonNullable<WorkoutAdaptationRequest['available_equipment_ids']>[number];
type ErrorKind = 'validation' | 'preview' | 'apply' | 'conflict';

const reasons: ReadonlyArray<{
  value: AdaptationReason;
  label: string;
  description: string;
}> = [
  {
    value: 'limited_time',
    label: 'Мало времени',
    description: 'Сохраним главное и уберём менее приоритетные упражнения.',
  },
  {
    value: 'unavailable_equipment',
    label: 'Нет оборудования',
    description: 'Подберём проверенную замену для одного упражнения.',
  },
  {
    value: 'replace_exercise',
    label: 'Заменить упражнение',
    description: 'Вы выберете замену из проверенного каталога.',
  },
  {
    value: 'different_environment',
    label: 'Другое место',
    description: 'Проверим всю тренировку по доступному оборудованию.',
  },
  {
    value: 'pain_or_injury',
    label: 'Боль или травма',
    description: 'Без медицинских рекомендаций и автоматической замены.',
  },
];

const timePresets = [20, 30, 45] as const;

const equipment: ReadonlyArray<{ value: EquipmentId; label: string }> = [
  { value: 'bodyweight', label: 'Собственный вес' },
  { value: 'dumbbell', label: 'Гантели' },
  { value: 'barbell', label: 'Штанга' },
  { value: 'bench', label: 'Скамья' },
  { value: 'cable', label: 'Тросовый блок' },
  { value: 'machine', label: 'Тренажёры' },
  { value: 'kettlebell', label: 'Гиря' },
  { value: 'cardio', label: 'Кардиооборудование' },
  { value: 'other', label: 'Другое' },
];

function alternativesPath(
  workoutId: number,
  workoutExerciseId: number,
  equipmentIds: EquipmentId[],
): string {
  const params = new URLSearchParams();
  equipmentIds.forEach((item) => params.append('available_equipment_ids', item));
  return `/api/v1/workouts/${workoutId}/exercises/${workoutExerciseId}/alternatives?${params}`;
}

function errorTitle(kind: ErrorKind): string {
  if (kind === 'conflict') return 'Тренировка уже изменилась';
  if (kind === 'apply') return 'Не удалось применить изменения';
  if (kind === 'preview') return 'Не удалось подготовить изменения';
  return 'Проверьте выбранные условия';
}

export function WorkoutAdaptation({
  workout,
  safetyOnly = false,
  entryContext = 'workout',
  initialTargetId,
  entryLabel,
}: {
  workout: Workout;
  safetyOnly?: boolean;
  entryContext?: 'today' | 'workout';
  initialTargetId?: number;
  entryLabel?: string;
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const titleId = useId();
  const descriptionId = useId();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<AdaptationReason>(
    initialTargetId ? 'replace_exercise' : 'limited_time',
  );
  const [timeBudget, setTimeBudget] = useState('30');
  const [targetId, setTargetId] = useState(initialTargetId ? String(initialTargetId) : '');
  const [replacementId, setReplacementId] = useState('');
  const [equipmentIds, setEquipmentIds] = useState<EquipmentId[]>([]);
  const [preview, setPreview] = useState<WorkoutAdaptationPreview | null>(null);
  const [error, setError] = useState<{ kind: ErrorKind; message: string } | null>(null);
  const activeReason: AdaptationReason = safetyOnly ? 'pain_or_injury' : reason;
  const availableReasons = safetyOnly
    ? reasons.filter((item) => item.value === 'pain_or_injury')
    : reasons;
  const selectedReason = reasons.find((item) => item.value === activeReason)!;
  const close = () => setOpen(false);
  const panelRef = useModalA11y<HTMLDivElement>(open, close, '.workout-adaptation-dialog__close');

  const needsEquipment = [
    'unavailable_equipment',
    'replace_exercise',
    'different_environment',
  ].includes(activeReason);
  const alternatives = useQuery({
    queryKey: ['workout', 'adaptation-alternatives', workout.id, targetId, equipmentIds],
    queryFn: () =>
      api<WorkoutAlternative[]>(alternativesPath(workout.id, Number(targetId), equipmentIds)),
    enabled: activeReason === 'replace_exercise' && Boolean(targetId) && equipmentIds.length > 0,
    retry: false,
  });

  const selectedTarget = useMemo(
    () => workout.exercises.find((item) => item.id === Number(targetId)),
    [targetId, workout.exercises],
  );

  const resetPreview = () => {
    setPreview(null);
    setError(null);
  };

  const resetDraft = () => {
    setReason('limited_time');
    setTimeBudget('30');
    setTargetId('');
    setReplacementId('');
    setEquipmentIds([]);
    setPreview(null);
    setError(null);
  };

  const buildRequest = (): WorkoutAdaptationRequest | null => {
    if (activeReason === 'limited_time') {
      const minutes = Number(timeBudget);
      if (!Number.isInteger(minutes) || minutes < 10 || minutes > 240) {
        setError({ kind: 'validation', message: 'Укажите от 10 до 240 минут.' });
        return null;
      }
      return { reason: activeReason, time_budget_minutes: minutes };
    }
    if (activeReason === 'pain_or_injury') return { reason: activeReason };
    if (needsEquipment && equipmentIds.length === 0) {
      setError({
        kind: 'validation',
        message: 'Отметьте всё оборудование, которое сейчас доступно.',
      });
      return null;
    }
    if (activeReason === 'different_environment') {
      return { reason: activeReason, available_equipment_ids: equipmentIds };
    }
    if (!targetId) {
      setError({ kind: 'validation', message: 'Выберите упражнение.' });
      return null;
    }
    if (activeReason === 'replace_exercise' && !replacementId) {
      setError({ kind: 'validation', message: 'Выберите проверенную замену.' });
      return null;
    }
    return {
      reason: activeReason,
      target_workout_exercise_id: Number(targetId),
      replacement_exercise_id:
        activeReason === 'replace_exercise' ? Number(replacementId) : undefined,
      available_equipment_ids: equipmentIds,
    };
  };

  const previewMutation = useMutation({
    mutationFn: (request: WorkoutAdaptationRequest) =>
      api<WorkoutAdaptationPreview>(`/api/v1/workouts/${workout.id}/adaptations/preview`, {
        method: 'POST',
        body: request,
      }),
    onSuccess: (result) => {
      setPreview(result);
      setError(null);
    },
    onError: (reason) => setError({ kind: 'preview', message: (reason as Error).message }),
  });
  const applyMutation = useMutation({
    mutationFn: ({ request, token }: { request: WorkoutAdaptationRequest; token: string }) =>
      api<WorkoutAdaptationApply>(`/api/v1/workouts/${workout.id}/adaptations/apply`, {
        method: 'POST',
        body: { ...request, preview_token: token },
      }),
    onSuccess: async () => {
      trackProductEvent({
        name: 'workout_adaptation_completed',
        surface: productEventSurface(),
      });
      await queryClient.invalidateQueries({ queryKey: ['workout'] });
      toast('Изменения применены только к сегодняшней тренировке');
      setOpen(false);
      resetDraft();
    },
    onError: (reason) => {
      const conflict = reason instanceof ApiError && reason.status === 409;
      if (conflict) setPreview(null);
      setError({
        kind: conflict ? 'conflict' : 'apply',
        message: conflict
          ? 'Состав тренировки изменился после предпросмотра. Ваш выбор сохранён — обновите изменения перед применением.'
          : (reason as Error).message,
      });
    },
  });

  const requestPreview = () => {
    const request = buildRequest();
    if (!request) return;
    setError(null);
    previewMutation.mutate(request);
  };

  const resolvedEntryLabel =
    entryLabel ?? (safetyOnly ? 'Боль или травма во время тренировки' : 'Адаптировать тренировку');

  return (
    <div
      className={`workout-adaptation-entry workout-adaptation-entry--${entryContext}`}
      data-testid="workout-adaptation-entry"
    >
      <Button
        fullWidth={entryContext === 'today'}
        type="button"
        variant={entryContext === 'today' ? 'ghost' : 'secondary'}
        onClick={() => {
          trackProductEvent({
            name: 'workout_adaptation_started',
            surface: productEventSurface(),
          });
          if (initialTargetId) {
            setReason('replace_exercise');
            setTargetId(String(initialTargetId));
            setReplacementId('');
            setEquipmentIds([]);
            resetPreview();
          }
          setOpen(true);
        }}
      >
        {resolvedEntryLabel}
      </Button>

      {open &&
        createPortal(
          <div
            className="modal app-section--design-v2 workout-adaptation-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={descriptionId}
          >
            <button
              className="modal__backdrop"
              type="button"
              aria-label="Закрыть адаптацию тренировки"
              onClick={close}
            />
            <div
              className="modal__panel workout-adaptation-dialog__panel"
              ref={panelRef}
              tabIndex={-1}
            >
              <header className="workout-adaptation-dialog__header">
                <div>
                  <span className="eyebrow">Только сегодняшняя тренировка</span>
                  <h2 id={titleId}>Подстроить тренировку</h2>
                  <p id={descriptionId}>
                    Сначала покажем точные изменения. Программа и будущие тренировки не изменятся.
                  </p>
                </div>
                <IconButton
                  className="workout-adaptation-dialog__close"
                  type="button"
                  aria-label="Закрыть адаптацию тренировки"
                  onClick={close}
                >
                  <CloseIcon />
                </IconButton>
              </header>

              <div className="workout-adaptation-dialog__body">
                {!safetyOnly && (
                  <fieldset className="adaptation-section adaptation-reasons">
                    <legend>Что изменилось сегодня?</legend>
                    <div className="adaptation-choice-grid">
                      {availableReasons.map((item) => (
                        <label
                          className={`adaptation-choice ${activeReason === item.value ? 'is-selected' : ''}`}
                          key={item.value}
                        >
                          <input
                            type="radio"
                            name={`${titleId}-reason`}
                            value={item.value}
                            checked={activeReason === item.value}
                            onChange={() => {
                              setReason(item.value);
                              resetPreview();
                            }}
                          />
                          <span>
                            <strong>{item.label}</strong>
                            <small>{item.description}</small>
                          </span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                )}

                {activeReason === 'limited_time' && (
                  <fieldset className="adaptation-section adaptation-time">
                    <legend>Сколько времени есть?</legend>
                    <p>Быстрый выбор или точное значение от 10 до 240 минут.</p>
                    <div className="adaptation-time__presets" aria-label="Бюджет времени">
                      {timePresets.map((minutes) => (
                        <Button
                          type="button"
                          variant="secondary"
                          aria-pressed={timeBudget === String(minutes)}
                          key={minutes}
                          onClick={() => {
                            setTimeBudget(String(minutes));
                            resetPreview();
                          }}
                        >
                          {minutes} мин
                        </Button>
                      ))}
                    </div>
                    <Field
                      label="Свои минуты"
                      labelFor={`${titleId}-time-budget`}
                      hint="Минимум 10, максимум 240 минут."
                    >
                      <Input
                        id={`${titleId}-time-budget`}
                        type="number"
                        inputMode="numeric"
                        min={10}
                        max={240}
                        value={timeBudget}
                        onChange={(event) => {
                          setTimeBudget(event.target.value);
                          resetPreview();
                        }}
                      />
                    </Field>
                  </fieldset>
                )}

                {(activeReason === 'unavailable_equipment' ||
                  activeReason === 'replace_exercise') && (
                  <div className="adaptation-section">
                    <Field label="Какое упражнение изменить?" labelFor={`${titleId}-target`}>
                      <Select
                        id={`${titleId}-target`}
                        value={targetId}
                        onChange={(event) => {
                          setTargetId(event.target.value);
                          setReplacementId('');
                          resetPreview();
                        }}
                      >
                        <option value="">Выберите упражнение</option>
                        {workout.exercises.map((item) => (
                          <option value={item.id} key={item.id}>
                            {item.exercise_title}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </div>
                )}

                {needsEquipment && (
                  <fieldset className="adaptation-section adaptation-equipment">
                    <legend>Что доступно сейчас?</legend>
                    <p>Отметьте всё подходящее оборудование.</p>
                    <div className="adaptation-equipment__grid">
                      {equipment.map((item) => (
                        <label
                          className={equipmentIds.includes(item.value) ? 'is-selected' : ''}
                          key={item.value}
                        >
                          <input
                            type="checkbox"
                            checked={equipmentIds.includes(item.value)}
                            onChange={(event) => {
                              setEquipmentIds((current) =>
                                event.target.checked
                                  ? [...current, item.value]
                                  : current.filter((value) => value !== item.value),
                              );
                              setReplacementId('');
                              resetPreview();
                            }}
                          />
                          <span>{item.label}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                )}

                {activeReason === 'replace_exercise' && targetId && equipmentIds.length > 0 && (
                  <fieldset className="adaptation-section adaptation-alternatives">
                    <legend>Проверенная замена для «{selectedTarget?.exercise_title}»</legend>
                    <p>Совместимость задана в каталоге, а не только совпадением основной мышцы.</p>
                    {alternatives.isLoading ? (
                      <p className="adaptation-inline-status" role="status">
                        Ищем подходящие варианты…
                      </p>
                    ) : alternatives.isError ? (
                      <div className="adaptation-inline-error" role="alert">
                        <span>{(alternatives.error as Error).message}</span>
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => void alternatives.refetch()}
                        >
                          Повторить
                        </Button>
                      </div>
                    ) : alternatives.data?.length ? (
                      <div className="adaptation-alternatives__list">
                        {alternatives.data.map((item) => (
                          <label
                            className={`adaptation-choice ${replacementId === String(item.exercise_id) ? 'is-selected' : ''}`}
                            key={item.exercise_id}
                          >
                            <input
                              type="radio"
                              name={`${titleId}-alternative`}
                              value={item.exercise_id}
                              checked={replacementId === String(item.exercise_id)}
                              onChange={(event) => {
                                setReplacementId(event.target.value);
                                resetPreview();
                              }}
                            />
                            <span>
                              <strong>{item.title}</strong>
                              <small>
                                {item.equipment_ids
                                  .map(
                                    (id) =>
                                      equipment.find((entry) => entry.value === id)?.label ?? id,
                                  )
                                  .join(' · ')}
                              </small>
                            </span>
                          </label>
                        ))}
                      </div>
                    ) : (
                      <p className="adaptation-inline-status">
                        Для выбранного оборудования нет проверенной замены. Измените условия или
                        оставьте упражнение без изменений.
                      </p>
                    )}
                  </fieldset>
                )}

                {activeReason === 'pain_or_injury' && (
                  <div className="adaptation-safety-note">
                    <strong>Не подбираем «лечебную» замену</strong>
                    <p>
                      При боли приложение покажет только безопасную границу сценария. Диагноз и
                      упражнение для восстановления должен определять квалифицированный специалист.
                    </p>
                  </div>
                )}

                {error && (
                  <div className="adaptation-error" role="alert">
                    <strong>{errorTitle(error.kind)}</strong>
                    <p>{error.message}</p>
                  </div>
                )}

                {preview && (
                  <section
                    className={`adaptation-preview is-${preview.status}`}
                    aria-labelledby={`${titleId}-preview`}
                    aria-live="polite"
                  >
                    <header>
                      <span className="eyebrow">Предпросмотр</span>
                      <h3 id={`${titleId}-preview`}>
                        {preview.status === 'safety_stop'
                          ? 'Безопасность прежде всего'
                          : preview.status === 'no_changes'
                            ? 'План остаётся прежним'
                            : 'Что изменится'}
                      </h3>
                      <p>{preview.message}</p>
                      <p className="adaptation-preview__reason">
                        Причина: <strong>{selectedReason.label}</strong>
                      </p>
                    </header>
                    {preview.status !== 'safety_stop' && (
                      <div
                        className="adaptation-diff"
                        role="list"
                        aria-label="Сравнение тренировки"
                      >
                        <div className="adaptation-diff__row" role="listitem">
                          <span>Расчётное время</span>
                          <span className="adaptation-diff__values">
                            <span>{preview.original_estimated_minutes} мин</span>
                            <Icon name="arrow-right" size={16} />
                            <strong>{preview.adapted_estimated_minutes} мин</strong>
                          </span>
                        </div>
                        {preview.changes.map((change) => (
                          <div
                            className="adaptation-diff__row adaptation-diff__row--exercise"
                            role="listitem"
                            key={`${change.kind}-${change.workout_exercise_id}`}
                          >
                            <span>Упражнение</span>
                            <span className="adaptation-diff__values">
                              <span>{change.from_title}</span>
                              <Icon name="arrow-right" size={16} />
                              <strong>
                                {change.kind === 'removed' ? 'Убрать' : change.to_title}
                              </strong>
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                    {preview.warnings.map((warning) => (
                      <p className="adaptation-warning" key={warning}>
                        {warning}
                      </p>
                    ))}
                  </section>
                )}
              </div>

              <footer className="workout-adaptation-dialog__footer">
                <Button
                  type="button"
                  variant="ghost"
                  disabled={applyMutation.isPending}
                  onClick={close}
                >
                  Отмена
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={previewMutation.isPending || applyMutation.isPending}
                  aria-busy={previewMutation.isPending}
                  onClick={requestPreview}
                >
                  {previewMutation.isPending
                    ? 'Считаем…'
                    : preview || error?.kind === 'conflict'
                      ? 'Обновить изменения'
                      : activeReason === 'pain_or_injury'
                        ? 'Показать рекомендации'
                        : 'Показать изменения'}
                </Button>
                {preview?.status === 'preview' && preview.preview_token && (
                  <Button
                    type="button"
                    disabled={applyMutation.isPending}
                    aria-busy={applyMutation.isPending}
                    onClick={() => {
                      const request = buildRequest();
                      if (!request) return;
                      applyMutation.mutate({ request, token: preview.preview_token! });
                    }}
                  >
                    {applyMutation.isPending ? 'Применяем…' : 'Применить'}
                  </Button>
                )}
              </footer>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
