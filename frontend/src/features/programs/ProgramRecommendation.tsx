import { FormEvent, useId, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api, ApiError } from '../../shared/api/client';
import type {
  ApiSchemas,
  Exercise,
  ProgramGeneratorConfirmResponse,
  ProgramGeneratorPreviewResponse,
  ProgramGeneratorRequest,
} from '../../shared/api/types';
import { Badge, CloseIcon, ErrorState } from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { StepProgress } from '../../shared/ui/DataViz';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';

type GeneratorGoal = ProgramGeneratorRequest['goal'];
type GeneratorExperience = ProgramGeneratorRequest['experience'];
type TrainingLocation = ProgramGeneratorRequest['training_location'];
type EquipmentId = NonNullable<ProgramGeneratorRequest['available_equipment_ids']>[number];
type PriorityOption = ApiSchemas['BodyPriorityMuscleOption'];

const goals: ReadonlyArray<{ value: GeneratorGoal; label: string; description: string }> = [
  {
    value: 'fat_loss',
    label: 'Снижение жира',
    description: 'Сделать тренировки частью постепенного снижения веса.',
  },
  {
    value: 'recomposition',
    label: 'Рекомпозиция',
    description: 'Менять соотношение мышц и жировой ткани без фокуса на вес.',
  },
  {
    value: 'maintenance',
    label: 'Поддержание',
    description: 'Сохранять форму, силу и регулярность тренировок.',
  },
  {
    value: 'muscle_gain',
    label: 'Набор мышц',
    description: 'Сделать акцент на росте мышц и последовательной нагрузке.',
  },
  {
    value: 'strength',
    label: 'Увеличение силы',
    description: 'Развивать результат в основных силовых движениях.',
  },
];

const experiences: ReadonlyArray<{
  value: GeneratorExperience;
  label: string;
  description: string;
}> = [
  {
    value: 'beginner',
    label: 'Начинаю или возвращаюсь',
    description: 'Занимаюсь меньше года или был длительный перерыв.',
  },
  {
    value: 'intermediate',
    label: 'Тренируюсь регулярно',
    description: 'Уверенно знаю базовые упражнения и занимаюсь системно.',
  },
  {
    value: 'advanced',
    label: 'Тренируюсь давно',
    description: 'Самостоятельно управляю техникой и тренировочной нагрузкой.',
  },
];

const locations: ReadonlyArray<{ value: TrainingLocation; label: string; description: string }> = [
  { value: 'gym', label: 'Тренажёрный зал', description: 'Есть доступ к залу и его инвентарю.' },
  { value: 'home', label: 'Дома', description: 'Тренируюсь дома или в небольшом пространстве.' },
  {
    value: 'other',
    label: 'Другое место',
    description: 'Например, улица или спортивная площадка.',
  },
];

const equipment: ReadonlyArray<{ value: EquipmentId; label: string }> = [
  { value: 'bodyweight', label: 'Собственный вес' },
  { value: 'dumbbell', label: 'Гантели' },
  { value: 'barbell', label: 'Штанга' },
  { value: 'bench', label: 'Скамья' },
  { value: 'cable', label: 'Тросовый блок' },
  { value: 'machine', label: 'Тренажёры' },
  { value: 'kettlebell', label: 'Гиря' },
  { value: 'cardio', label: 'Кардиооборудование' },
  { value: 'other', label: 'Другой инвентарь' },
];

const stepTitles = ['Цель', 'Опыт', 'Частота', 'Длительность', 'Место и инвентарь'] as const;

const noCompatibleReasonLabels: Record<string, string> = {
  duration_incompatible: 'Запрошенная длительность несовместима со структурой программы.',
  equipment_no_canonical_substitution:
    'Для обязательного упражнения нет безопасной канонической замены.',
  excluded_exercise_no_substitution: 'Исключение упражнения не оставляет канонической замены.',
  experience_incompatible: 'Доступные source-backed структуры требуют другого уровня опыта.',
  frequency_not_supported: 'Подходящая source-backed структура не поддерживает эту частоту.',
  goal_not_supported: 'Для выбранной цели нет совместимой source-backed структуры.',
  exercise_not_canonical: 'Выбранное упражнение отсутствует в каноническом каталоге.',
  no_compatible_program: 'Все доступные структуры нарушают хотя бы одно жёсткое ограничение.',
};

interface ProgramRecommendationProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirmed?: () => void | Promise<void>;
}

function Choice({
  checked,
  description,
  label,
  name,
  onChange,
  value,
}: {
  checked: boolean;
  description: string;
  label: string;
  name: string;
  onChange: () => void;
  value: string | number;
}) {
  return (
    <label className={`program-wizard-choice${checked ? ' is-selected' : ''}`}>
      <input checked={checked} name={name} onChange={onChange} type="radio" value={value} />
      <span className="program-wizard-choice__control" aria-hidden="true" />
      <span>
        <strong>{label}</strong>
        <small>{description}</small>
      </span>
    </label>
  );
}

function durationLabel(value: number): string {
  return `${value} минут`;
}
function reasonLabel(code: string): string {
  return (
    noCompatibleReasonLabels[code] ?? 'Ограничение не позволило подтвердить совместимый вариант.'
  );
}

function PreviewDays({ preview }: { preview: ProgramGeneratorPreviewResponse }) {
  if (!preview.program) return null;
  return (
    <div className="program-generator__days">
      {preview.program.days.map((day) => (
        <article className="program-generator__day" key={day.day_number}>
          <div className="program-generator__day-header">
            <div>
              <span className="eyebrow">День {day.day_number}</span>
              <h4>{day.title}</h4>
            </div>
            <small>{day.estimated_duration_minutes} мин</small>
          </div>
          <ol>
            {day.exercises.map((exercise) => (
              <li key={`${day.day_number}-${exercise.exercise_id}-${exercise.source_exercise_id}`}>
                <span>
                  <strong>{exercise.exercise_title}</strong>
                  <small>
                    {exercise.prescribed_sets} подхода · {exercise.prescribed_reps}
                    {exercise.group_kind ? ` · ${exercise.group_kind}` : ''}
                  </small>
                </span>
                {exercise.exercise_id !== exercise.source_exercise_id && (
                  <Badge tone="neutral">Замена</Badge>
                )}
              </li>
            ))}
          </ol>
        </article>
      ))}
    </div>
  );
}

export function ProgramRecommendation({
  open,
  onOpenChange,
  onConfirmed,
}: ProgramRecommendationProps) {
  const { user } = useAuth();
  const { confirm } = useFeedback();
  const titleId = useId();
  const profile = user?.profile;
  const profileGoal = goals.some((item) => item.value === profile?.goal)
    ? (profile?.goal as GeneratorGoal)
    : '';
  const profileExperience = experiences.some((item) => item.value === profile?.level)
    ? (profile?.level as GeneratorExperience)
    : '';
  const profileDays = profile?.workouts_per_week;
  const initialDays = profileDays && profileDays >= 2 && profileDays <= 6 ? profileDays : '';
  const profileLocations = profile?.training_preferences?.location_profiles ?? [];
  const profileLocation = profileLocations.length === 1 ? profileLocations[0] : undefined;
  const panelRef = useModalA11y<HTMLDivElement>(
    open,
    () => onOpenChange(false),
    '.program-wizard__close',
  );
  const priorityOptions = useQuery({
    queryKey: ['body-priority-options'],
    queryFn: () =>
      api<ApiSchemas['BodyPriorityOptionsResponse']>('/api/v1/me/profile/body-priority-options'),
    staleTime: Number.POSITIVE_INFINITY,
    enabled: open,
  });
  const exerciseCatalog = useQuery({
    queryKey: ['program-generator-exercises'],
    queryFn: () => api<Exercise[]>('/api/v1/programs/exercises'),
    staleTime: Number.POSITIVE_INFINITY,
    enabled: open,
  });
  const canonicalExercises = (exerciseCatalog.data ?? []).filter((exercise) => !exercise.is_custom);

  const [step, setStep] = useState(0);
  const [goal, setGoal] = useState<GeneratorGoal | ''>(profileGoal);
  const [experience, setExperience] = useState<GeneratorExperience | ''>(profileExperience);
  const [daysPerWeek, setDaysPerWeek] = useState<number | ''>(initialDays);
  const [duration, setDuration] = useState<number | ''>('');
  const [location, setLocation] = useState<TrainingLocation | ''>(profileLocation?.location ?? '');
  const [equipmentIds, setEquipmentIds] = useState<EquipmentId[]>(
    (profileLocation?.equipment_ids ?? []) as EquipmentId[],
  );
  const [priorityIds, setPriorityIds] = useState<string[]>(
    profile?.body_priority?.mode === 'muscle_groups'
      ? (profile.body_priority.muscle_group_ids ?? [])
      : [],
  );
  const [preferredIds, setPreferredIds] = useState<number[]>([]);
  const [excludedIds, setExcludedIds] = useState<number[]>([]);
  const [preview, setPreview] = useState<ProgramGeneratorPreviewResponse | null>(null);
  const [confirmed, setConfirmed] = useState<ProgramGeneratorConfirmResponse | null>(null);

  const previewMutation = useMutation({
    mutationFn: (payload: ProgramGeneratorRequest) =>
      api<ProgramGeneratorPreviewResponse>('/api/v1/programs/generator/preview', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: (data) => {
      setPreview(data);
      trackProductEvent({
        name:
          data.status === 'preview'
            ? 'program_generator_previewed'
            : 'program_generator_no_compatible',
        surface: productEventSurface(),
      });
    },
  });
  const confirmMutation = useMutation({
    mutationFn: ({ replaceActive }: { replaceActive: boolean }) =>
      api<ProgramGeneratorConfirmResponse>('/api/v1/programs/generator/confirm', {
        method: 'POST',
        body: { draft_token: preview?.draft_token, replace_active: replaceActive },
      }),
    onSuccess: async (data) => {
      setConfirmed(data);
      trackProductEvent({ name: 'program_generator_confirmed', surface: productEventSurface() });
      await onConfirmed?.();
    },
  });

  const hasProfilePrefill = Boolean(
    profileGoal || profileExperience || initialDays || profileLocation,
  );
  const canContinue =
    (step === 0 && Boolean(goal)) ||
    (step === 1 && Boolean(experience)) ||
    (step === 2 && Boolean(daysPerWeek)) ||
    (step === 3 && Boolean(duration)) ||
    (step === 4 && Boolean(location));
  const resetResult = () => {
    setPreview(null);
    setConfirmed(null);
    previewMutation.reset();
    confirmMutation.reset();
  };
  const close = () => {
    if (preview && !confirmed) {
      trackProductEvent({ name: 'program_generator_rejected', surface: productEventSurface() });
    }
    onOpenChange(false);
    resetResult();
  };
  const updateLocation = (value: TrainingLocation) => {
    setLocation(value);
    const saved = profileLocations.find((item) => item.location === value);
    setEquipmentIds((saved?.equipment_ids ?? []) as EquipmentId[]);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canContinue) return;
    if (step < stepTitles.length - 1) {
      setStep((current) => current + 1);
      return;
    }
    if (!goal || !experience || !daysPerWeek || !duration || !location) return;
    trackProductEvent({ name: 'program_generator_started', surface: productEventSurface() });
    previewMutation.mutate({
      goal,
      experience,
      days_per_week: daysPerWeek,
      preferred_session_duration_minutes: duration,
      training_location: location,
      available_equipment_ids: equipmentIds,
      priority_muscle_ids: priorityIds,
      preferred_exercise_ids: preferredIds,
      excluded_exercise_ids: excludedIds,
    });
  };

  const confirmPreview = async () => {
    if (!preview?.draft_token || preview.active_program?.trainer_owned) return;
    confirmMutation.reset();
    try {
      await confirmMutation.mutateAsync({ replaceActive: false });
    } catch (reason) {
      if (
        reason instanceof ApiError &&
        reason.status === 409 &&
        reason.message.toLowerCase().includes('архив')
      ) {
        const accepted = await confirm({
          title: 'Заменить активную программу?',
          message: 'Текущая программа будет отправлена в архив. История тренировок сохранится.',
          confirmText: 'Заменить программу',
        });
        if (accepted) await confirmMutation.mutateAsync({ replaceActive: true });
      }
    }
  };

  return (
    <>
      {open && (
        <div
          className="modal program-wizard"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
        >
          <button
            type="button"
            className="modal__backdrop"
            aria-label="Закрыть подбор программы"
            onClick={close}
          />
          <div className="modal__panel card program-wizard__panel" ref={panelRef} tabIndex={-1}>
            <header className="program-wizard__header">
              <div>
                <span className="eyebrow">Детерминированный подбор</span>
                <h2 id={titleId}>
                  {confirmed
                    ? 'Программа подтверждена'
                    : preview
                      ? 'Предпросмотр программы'
                      : stepTitles[step]}
                </h2>
              </div>
              <button
                type="button"
                className="secondary program-wizard__close"
                aria-label="Закрыть подбор программы"
                onClick={close}
              >
                <CloseIcon />
              </button>
            </header>

            {!preview && !confirmed && (
              <>
                <div className="program-wizard__progress">
                  <strong>{stepTitles[step]}</strong>
                  <StepProgress current={step + 1} labels={stepTitles} />
                </div>
                {hasProfilePrefill && step === 0 && (
                  <p className="program-wizard__prefill">
                    Мы подставили явные значения из профиля. Здесь их можно изменить — профиль не
                    обновится.
                  </p>
                )}
                <form className="program-wizard__form" onSubmit={submit}>
                  {step === 0 && (
                    <fieldset>
                      <legend>Какая цель главная сейчас?</legend>
                      <p>
                        Цель влияет на порядок source-backed структур, но не создаёт новую методику.
                      </p>
                      <div className="program-wizard__choices">
                        {goals.map((item) => (
                          <Choice
                            checked={goal === item.value}
                            description={item.description}
                            key={item.value}
                            label={item.label}
                            name="generator-goal"
                            onChange={() => setGoal(item.value)}
                            value={item.value}
                          />
                        ))}
                      </div>
                    </fieldset>
                  )}
                  {step === 1 && (
                    <fieldset>
                      <legend>Какой у вас опыт силовых тренировок?</legend>
                      <p>
                        Выберите явный уровень — генератор не выводит его из возраста, веса или
                        пола.
                      </p>
                      <div className="program-wizard__choices">
                        {experiences.map((item) => (
                          <Choice
                            checked={experience === item.value}
                            description={item.description}
                            key={item.value}
                            label={item.label}
                            name="generator-experience"
                            onChange={() => setExperience(item.value)}
                            value={item.value}
                          />
                        ))}
                      </div>
                    </fieldset>
                  )}
                  {step === 2 && (
                    <fieldset>
                      <legend>Сколько тренировок в неделю?</legend>
                      <p>
                        В v1 поддерживаются только 2–6 дней. Значение не округляется автоматически.
                      </p>
                      <div className="program-wizard__frequency">
                        {[2, 3, 4, 5, 6].map((value) => (
                          <Choice
                            checked={daysPerWeek === value}
                            description="тренировки в неделю"
                            key={value}
                            label={String(value)}
                            name="generator-frequency"
                            onChange={() => setDaysPerWeek(value)}
                            value={value}
                          />
                        ))}
                      </div>
                    </fieldset>
                  )}
                  {step === 3 && (
                    <fieldset>
                      <legend>Сколько времени обычно есть на занятие?</legend>
                      <p>
                        Это планировочный ориентир, а не обещание точной длительности тренировки.
                      </p>
                      <div className="program-wizard__frequency">
                        {[30, 45, 60, 75, 90].map((value) => (
                          <Choice
                            checked={duration === value}
                            description={value <= 45 ? 'короткая сессия' : 'обычная сессия'}
                            key={value}
                            label={durationLabel(value)}
                            name="generator-duration"
                            onChange={() => setDuration(value)}
                            value={value}
                          />
                        ))}
                      </div>
                    </fieldset>
                  )}
                  {step === 4 && (
                    <fieldset>
                      <legend>Где и с чем вы будете тренироваться?</legend>
                      <div className="program-wizard__choices program-wizard__choices--compact">
                        {locations.map((item) => (
                          <Choice
                            checked={location === item.value}
                            description={item.description}
                            key={item.value}
                            label={item.label}
                            name="generator-location"
                            onChange={() => updateLocation(item.value)}
                            value={item.value}
                          />
                        ))}
                      </div>
                      <div className="program-generator__selects">
                        <strong>Отметьте только доступное оборудование</strong>
                        <div className="program-wizard__equipment">
                          {equipment.map((item) => (
                            <label className="checkbox-row" key={item.value}>
                              <input
                                type="checkbox"
                                checked={equipmentIds.includes(item.value)}
                                onChange={(event) =>
                                  setEquipmentIds((current) =>
                                    event.target.checked
                                      ? [...current, item.value]
                                      : current.filter((value) => value !== item.value),
                                  )
                                }
                              />
                              <span>{item.label}</span>
                            </label>
                          ))}
                        </div>
                        <small>
                          Собственный вес можно оставить отмеченным вместе с любым другим
                          инвентарём.
                        </small>
                        <label className="field">
                          <span>Приоритетные группы — необязательно</span>
                          <select
                            multiple
                            size={4}
                            value={priorityIds}
                            onChange={(event) =>
                              setPriorityIds(
                                Array.from(event.target.selectedOptions, (option) => option.value),
                              )
                            }
                          >
                            {(priorityOptions.data?.items ?? []).map((option: PriorityOption) => (
                              <option key={option.id} value={option.id}>
                                {option.name}
                              </option>
                            ))}
                          </select>
                          <small className="field-hint">
                            Это мягкий приоритет, а не произвольный оптимизатор объёма.
                          </small>
                        </label>
                        <label className="field">
                          <span>Предпочитаемые упражнения — необязательно</span>
                          <select
                            multiple
                            size={4}
                            value={preferredIds.map(String)}
                            onChange={(event) =>
                              setPreferredIds(
                                Array.from(event.target.selectedOptions, (option) =>
                                  Number(option.value),
                                ),
                              )
                            }
                          >
                            {canonicalExercises.map((exercise) => (
                              <option key={exercise.id} value={exercise.id}>
                                {exercise.title}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="field">
                          <span>Исключить упражнения — необязательно</span>
                          <select
                            multiple
                            size={4}
                            value={excludedIds.map(String)}
                            onChange={(event) =>
                              setExcludedIds(
                                Array.from(event.target.selectedOptions, (option) =>
                                  Number(option.value),
                                ).filter((id) => !preferredIds.includes(id)),
                              )
                            }
                          >
                            {canonicalExercises
                              .filter((exercise) => !preferredIds.includes(exercise.id))
                              .map((exercise) => (
                                <option key={exercise.id} value={exercise.id}>
                                  {exercise.title}
                                </option>
                              ))}
                          </select>
                        </label>
                      </div>
                      <p className="program-wizard__safety-note">
                        Подбор использует канонические упражнения и source-backed структуры. Это не
                        медицинская рекомендация.
                      </p>
                    </fieldset>
                  )}
                  {previewMutation.error && (
                    <ErrorState message={(previewMutation.error as Error).message} />
                  )}
                  <footer className="program-wizard__footer">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => (step === 0 ? close() : setStep((current) => current - 1))}
                    >
                      {step === 0 ? 'Отмена' : 'Назад'}
                    </button>
                    <button disabled={!canContinue || previewMutation.isPending}>
                      {previewMutation.isPending
                        ? 'Рассчитываем…'
                        : step === stepTitles.length - 1
                          ? 'Показать preview'
                          : 'Далее'}
                    </button>
                  </footer>
                </form>
              </>
            )}

            {preview && !confirmed && (
              <div className="program-wizard-result" aria-live="polite">
                {preview.status === 'preview' && preview.program ? (
                  <>
                    <div className="program-wizard-result__lead">
                      <Badge tone="success">Проверенный draft</Badge>
                      <h3>{preview.program.title}</h3>
                      <p>{preview.message}</p>
                    </div>
                    <dl className="program-wizard-result__summary">
                      <div>
                        <dt>Источник</dt>
                        <dd>{preview.source?.title ?? 'Каноническая структура'}</dd>
                      </div>
                      <div>
                        <dt>График</dt>
                        <dd>{preview.program.days.length} тренировок</dd>
                      </div>
                      <div>
                        <dt>Длительность</dt>
                        <dd>до {preview.program.estimated_duration_minutes} мин</dd>
                      </div>
                    </dl>
                    <div className="program-wizard-result__facts">
                      <div>
                        <strong>Почему выбрано</strong>
                        <ul>
                          {(preview.fit_reasons ?? []).map((reason) => (
                            <li key={reason}>{reason}</li>
                          ))}
                        </ul>
                      </div>
                      {!!preview.tradeoffs?.length && (
                        <div>
                          <strong>Компромиссы</strong>
                          <ul>
                            {(preview.tradeoffs ?? []).map((tradeoff) => (
                              <li key={tradeoff}>{tradeoff}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {!!preview.adaptations?.length && (
                        <div>
                          <strong>Адаптации</strong>
                          <ul>
                            {(preview.adaptations ?? []).map((item) => (
                              <li
                                key={`${item.code}-${item.day_number}-${item.source_exercise_id}`}
                              >
                                {item.message}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                    <PreviewDays preview={preview} />
                    {preview.active_program?.trainer_owned && (
                      <ErrorState message="Сейчас активна программа, назначенная тренером. Личная подборка не может её заменить." />
                    )}
                    {confirmMutation.error && (
                      <ErrorState message={(confirmMutation.error as Error).message} />
                    )}
                    <footer className="program-wizard__footer program-wizard__footer--result">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          setPreview(null);
                          previewMutation.reset();
                          confirmMutation.reset();
                          setStep(stepTitles.length - 1);
                        }}
                      >
                        Изменить параметры
                      </button>
                      <button
                        type="button"
                        disabled={
                          confirmMutation.isPending ||
                          Boolean(preview.active_program?.trainer_owned)
                        }
                        onClick={() => void confirmPreview()}
                      >
                        {confirmMutation.isPending ? 'Сохраняем…' : 'Подтвердить программу'}
                      </button>
                    </footer>
                  </>
                ) : (
                  <div className="program-wizard-result__empty">
                    <span className="eyebrow">Совместимый вариант не найден</span>
                    <h3>Не удалось подобрать программу</h3>
                    <p>{preview.message}</p>
                    <ul className="program-generator__reasons">
                      {(preview.reason_codes ?? []).map((code) => (
                        <li key={code}>{reasonLabel(code)}</li>
                      ))}
                    </ul>
                    <div className="program-wizard__result-actions">
                      <button
                        type="button"
                        onClick={() => {
                          setPreview(null);
                          previewMutation.reset();
                          setStep(stepTitles.length - 1);
                        }}
                      >
                        Изменить параметры
                      </button>
                      <button type="button" className="secondary" onClick={close}>
                        Закрыть
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {confirmed && (
              <div className="program-wizard-result" aria-live="polite">
                <div className="program-wizard-result__lead">
                  <Badge tone="success">Сохранено</Badge>
                  <h3>{confirmed.template.title}</h3>
                  <p>Программа подтверждена и назначена через существующий lifecycle Product v4.</p>
                </div>
                <div className="program-wizard__result-actions">
                  <button type="button" onClick={close}>
                    Перейти к программам
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
