import { FormEvent, useId, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';
import type {
  ProgramRecommendationRequest,
  ProgramRecommendationResponse,
  ProgramTemplate,
} from '../../shared/api/types';
import { Badge, CloseIcon, ErrorState } from '../../shared/ui/common';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { StepProgress } from '../../shared/ui/DataViz';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';

type RecommendationGoal = NonNullable<ProgramRecommendationRequest['goal']>;
type RecommendationExperience = NonNullable<ProgramRecommendationRequest['experience']>;
type TrainingLocation = NonNullable<ProgramRecommendationRequest['training_location']>;
type EquipmentId = NonNullable<ProgramRecommendationRequest['available_equipment_ids']>[number];
type EquipmentMode = 'skip' | 'exact';

const goals: ReadonlyArray<{
  value: RecommendationGoal;
  label: string;
  description: string;
}> = [
  {
    value: 'fat_loss',
    label: 'Снижение жира',
    description: 'Сделать тренировки частью постепенного снижения жировой массы.',
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
  value: RecommendationExperience;
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

const locations: ReadonlyArray<{
  value: TrainingLocation | 'not_set';
  label: string;
  description: string;
}> = [
  { value: 'gym', label: 'Тренажёрный зал', description: 'Есть доступ к залу и его инвентарю.' },
  { value: 'home', label: 'Дома', description: 'Тренируюсь дома или в небольшом пространстве.' },
  {
    value: 'other',
    label: 'Другое место',
    description: 'Например, улица или спортивная площадка.',
  },
  {
    value: 'not_set',
    label: 'Место не важно',
    description: 'Не использовать место как пояснение к подбору.',
  },
];

const equipment: ReadonlyArray<{ value: EquipmentId; label: string }> = [
  { value: 'bodyweight', label: 'Только собственный вес' },
  { value: 'dumbbell', label: 'Гантели' },
  { value: 'barbell', label: 'Штанга' },
  { value: 'bench', label: 'Скамья' },
  { value: 'cable', label: 'Тросовый блок' },
  { value: 'machine', label: 'Тренажёры' },
  { value: 'kettlebell', label: 'Гиря' },
  { value: 'cardio', label: 'Кардиооборудование' },
  { value: 'other', label: 'Другой инвентарь' },
];

const splitDescriptions: Record<NonNullable<ProgramTemplate['split_type']>, string> = {
  full_body: 'Всё тело — основные мышечные группы в каждой тренировке',
  upper_lower: 'Верх / низ — отдельные тренировки для верхней и нижней частей тела',
  push_pull_legs: 'Толкающие / тянущие / ноги — движения разделены по типу нагрузки',
  body_part: 'По группам мышц — разные части тела в разные тренировочные дни',
  hybrid: 'Комбинированный формат — сочетает несколько простых схем',
};

const stepTitles = ['Цель', 'Опыт', 'Частота', 'Место', 'Оборудование'] as const;

function workoutCountLabel(value: number): string {
  const suffix =
    value === 1 ? 'тренировка' : value >= 2 && value <= 4 ? 'тренировки' : 'тренировок';
  return `${value} ${suffix}`;
}

function frequencyLabel(value: number | null | undefined): string {
  if (!value) return 'Не указана';
  if (value === 8) return '8 тренировок в последовательном цикле';
  return `${workoutCountLabel(value)} в неделю`;
}

interface ProgramRecommendationProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPreview: (template: ProgramTemplate) => void;
  onEditCopy: (template: ProgramTemplate) => void;
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

function AnchorAction({
  children,
  href,
  onClick,
}: {
  children: string;
  href: string;
  onClick?: () => void;
}) {
  return (
    <a className="secondary program-wizard__anchor" href={href} onClick={onClick}>
      {children}
    </a>
  );
}

export function ProgramRecommendation({
  open,
  onOpenChange,
  onPreview,
  onEditCopy,
}: ProgramRecommendationProps) {
  const { user } = useAuth();
  const titleId = useId();
  const profileGoal = user?.profile?.goal;
  const profileExperience = user?.profile?.level;
  const profileWorkouts = user?.profile?.workouts_per_week;
  const profileLocations = user?.profile?.training_preferences?.location_profiles ?? [];
  const profileLocation = profileLocations.length === 1 ? profileLocations[0] : undefined;
  const initialGoal = goals.some((item) => item.value === profileGoal)
    ? (profileGoal as RecommendationGoal)
    : '';
  const initialExperience = experiences.some((item) => item.value === profileExperience)
    ? (profileExperience as RecommendationExperience)
    : '';
  const initialWorkouts =
    profileWorkouts && profileWorkouts >= 1 && profileWorkouts <= 8 ? profileWorkouts : '';
  const initialLocation = profileLocation?.location ?? '';
  const initialEquipment = (profileLocation?.equipment_ids ?? []) as EquipmentId[];
  const [step, setStep] = useState(0);
  const [showResult, setShowResult] = useState(false);
  const [goal, setGoal] = useState<RecommendationGoal | ''>(initialGoal);
  const [experience, setExperience] = useState<RecommendationExperience | ''>(initialExperience);
  const [workoutsPerWeek, setWorkoutsPerWeek] = useState<number | ''>(initialWorkouts);
  const [location, setLocation] = useState<TrainingLocation | 'not_set' | ''>(initialLocation);
  const [equipmentMode, setEquipmentMode] = useState<EquipmentMode | ''>(
    initialLocation ? 'exact' : '',
  );
  const [equipmentIds, setEquipmentIds] = useState<EquipmentId[]>(initialEquipment);
  const close = () => onOpenChange(false);
  const panelRef = useModalA11y<HTMLDivElement>(open, close, '.program-wizard__close');
  const hasProfilePrefill = Boolean(
    initialGoal || initialExperience || initialWorkouts || initialLocation,
  );

  const recommendation = useMutation({
    mutationFn: (payload: ProgramRecommendationRequest) =>
      api<ProgramRecommendationResponse>('/api/v1/programs/templates/recommendation', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      trackProductEvent({
        name: 'program_recommendation_completed',
        surface: productEventSurface(),
      });
      setShowResult(true);
    },
  });

  const canContinue =
    (step === 0 && Boolean(goal)) ||
    (step === 1 && Boolean(experience)) ||
    (step === 2 && Boolean(workoutsPerWeek)) ||
    (step === 3 && Boolean(location)) ||
    (step === 4 && Boolean(equipmentMode));

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canContinue) return;
    if (step === 0) {
      trackProductEvent({
        name: 'program_recommendation_started',
        surface: productEventSurface(),
      });
    }
    if (step < stepTitles.length - 1) {
      setStep((current) => current + 1);
      return;
    }
    recommendation.mutate({
      goal: goal || null,
      experience: experience || null,
      workouts_per_week: workoutsPerWeek || null,
      training_location: location && location !== 'not_set' ? location : null,
      available_equipment_ids: equipmentMode === 'exact' ? equipmentIds : null,
    });
  };

  const leaveWizard = () => {
    close();
    setShowResult(false);
    recommendation.reset();
  };

  const result = recommendation.data;
  const resultGoal = goals.find((item) => item.value === result?.criteria.goal)?.label;
  const resultExperience = experiences.find(
    (item) => item.value === result?.criteria.experience,
  )?.label;

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
                <span className="eyebrow">Мастер подбора программы</span>
                <h2 id={titleId}>{showResult ? 'Ваш результат' : stepTitles[step]}</h2>
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

            {!showResult && (
              <>
                <div className="program-wizard__progress">
                  <strong>{stepTitles[step]}</strong>
                  <StepProgress current={step + 1} labels={stepTitles} />
                </div>
                {hasProfilePrefill && step === 0 && (
                  <p className="program-wizard__prefill">
                    Мы подставили достоверные ответы из профиля. Здесь их можно изменить — профиль
                    от этого не обновится.
                  </p>
                )}
                <form className="program-wizard__form" onSubmit={submit}>
                  {step === 0 && (
                    <fieldset>
                      <legend>Какой результат для вас сейчас главный?</legend>
                      <p>Выберите один приоритет — его всегда можно поменять при новом подборе.</p>
                      <div className="program-wizard__choices">
                        {goals.map((item) => (
                          <Choice
                            checked={goal === item.value}
                            description={item.description}
                            key={item.value}
                            label={item.label}
                            name="recommendation-goal"
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
                      <p>Оценивайте регулярный опыт, а не разовый лучший результат.</p>
                      <div className="program-wizard__choices">
                        {experiences.map((item) => (
                          <Choice
                            checked={experience === item.value}
                            description={item.description}
                            key={item.value}
                            label={item.label}
                            name="recommendation-experience"
                            onChange={() => setExperience(item.value)}
                            value={item.value}
                          />
                        ))}
                      </div>
                    </fieldset>
                  )}
                  {step === 2 && (
                    <fieldset>
                      <legend>Сколько силовых тренировок реально выполнять?</legend>
                      <p>
                        Выбирайте устойчивый ритм, который сможете повторять из недели в неделю.
                      </p>
                      <div className="program-wizard__frequency">
                        {[1, 2, 3, 4, 5, 6, 7].map((value) => (
                          <Choice
                            checked={workoutsPerWeek === value}
                            description={
                              value === 1 ? 'тренировка в неделю' : 'тренировки в неделю'
                            }
                            key={value}
                            label={String(value)}
                            name="recommendation-frequency"
                            onChange={() => setWorkoutsPerWeek(value)}
                            value={value}
                          />
                        ))}
                        <Choice
                          checked={workoutsPerWeek === 8}
                          description="Последовательный цикл, не восемь тренировок за неделю"
                          label="8 тренировок в цикле"
                          name="recommendation-frequency"
                          onChange={() => setWorkoutsPerWeek(8)}
                          value={8}
                        />
                      </div>
                    </fieldset>
                  )}
                  {step === 3 && (
                    <fieldset>
                      <legend>Где вы обычно тренируетесь?</legend>
                      <p>
                        Место помогает понятнее объяснить результат. Инвентарь проверим отдельно.
                      </p>
                      <div className="program-wizard__choices">
                        {locations.map((item) => (
                          <Choice
                            checked={location === item.value}
                            description={item.description}
                            key={item.value}
                            label={item.label}
                            name="recommendation-location"
                            onChange={() => {
                              setLocation(item.value);
                              const savedLocation = profileLocations.find(
                                (profile) => profile.location === item.value,
                              );
                              setEquipmentMode(savedLocation ? 'exact' : '');
                              setEquipmentIds(
                                (savedLocation?.equipment_ids ?? []) as EquipmentId[],
                              );
                            }}
                            value={item.value}
                          />
                        ))}
                      </div>
                    </fieldset>
                  )}
                  {step === 4 && (
                    <fieldset>
                      <legend>Нужно проверить доступное оборудование?</legend>
                      <p>
                        Это единственное дополнительное ограничение, которое текущий подбор умеет
                        проверять по составу упражнений.
                      </p>
                      <div className="program-wizard__choices program-wizard__choices--compact">
                        <Choice
                          checked={equipmentMode === 'skip'}
                          description="Показать подходящий план, даже если инвентарь придётся уточнить позже."
                          label="Не проверять оборудование"
                          name="recommendation-equipment-mode"
                          onChange={() => setEquipmentMode('skip')}
                          value="skip"
                        />
                        <Choice
                          checked={equipmentMode === 'exact'}
                          description="Исключить шаблоны, которым нужен недоступный инвентарь."
                          label="Учесть только доступное"
                          name="recommendation-equipment-mode"
                          onChange={() => setEquipmentMode('exact')}
                          value="exact"
                        />
                      </div>
                      {equipmentMode === 'exact' && (
                        <div className="program-wizard__equipment">
                          <strong>Отметьте всё, что точно есть</strong>
                          <div>
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
                            Если ничего не отметить, подбор будет искать варианты без отдельного
                            инвентаря.
                          </small>
                        </div>
                      )}
                      <p className="program-wizard__safety-note">
                        Подбор не оценивает травмы, боль или медицинские ограничения. При боли или
                        ограничениях по здоровью обсудите тренировки с квалифицированным
                        специалистом.
                      </p>
                    </fieldset>
                  )}

                  {recommendation.error && (
                    <ErrorState message={(recommendation.error as Error).message} />
                  )}
                  <footer className="program-wizard__footer">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => (step === 0 ? close() : setStep((current) => current - 1))}
                    >
                      {step === 0 ? 'Отмена' : 'Назад'}
                    </button>
                    <button disabled={!canContinue || recommendation.isPending}>
                      {recommendation.isPending
                        ? 'Подбираем…'
                        : step === stepTitles.length - 1
                          ? 'Показать рекомендацию'
                          : 'Далее'}
                    </button>
                  </footer>
                </form>
              </>
            )}

            {showResult && result && (
              <div className="program-wizard-result" aria-live="polite">
                {result.recommendation ? (
                  <>
                    <div className="program-wizard-result__lead">
                      <Badge tone="success">Рекомендованный шаблон</Badge>
                      <h3>{result.recommendation.template.title}</h3>
                      <p>{result.recommendation.reason}</p>
                    </div>
                    <dl className="program-wizard-result__summary">
                      <div>
                        <dt>Цель</dt>
                        <dd>{resultGoal ?? 'Не указана'}</dd>
                      </div>
                      <div>
                        <dt>Опыт</dt>
                        <dd>{resultExperience ?? 'Не указан'}</dd>
                      </div>
                      <div>
                        <dt>Частота</dt>
                        <dd>
                          {frequencyLabel(result.criteria.workouts_per_week)}
                          <small>
                            В программе:{' '}
                            {workoutCountLabel(result.recommendation.template.days.length)} в цикле
                          </small>
                        </dd>
                      </div>
                    </dl>
                    {result.recommendation.template.split_type && (
                      <p className="program-wizard-result__format">
                        <strong>Как устроен план</strong>
                        <span>{splitDescriptions[result.recommendation.template.split_type]}</span>
                      </p>
                    )}
                    <div className="program-wizard-result__facts">
                      <div>
                        <strong>Почему подходит</strong>
                        <ul>
                          {result.recommendation.fit_facts.map((fact) => (
                            <li key={fact}>{fact}</li>
                          ))}
                        </ul>
                      </div>
                      {result.recommendation.limitations.length > 0 && (
                        <div>
                          <strong>Что учесть</strong>
                          <ul>
                            {result.recommendation.limitations.map((limitation) => (
                              <li key={limitation}>{limitation}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                    <p className="program-wizard-result__next">
                      Сначала посмотрите дни и упражнения. После просмотра можно настроить личную
                      копию или отдельно выбрать расписание и запустить исходный шаблон.
                    </p>
                    <div className="program-wizard__result-actions">
                      <button
                        type="button"
                        onClick={() => {
                          close();
                          onPreview(result.recommendation!.template);
                        }}
                      >
                        Посмотреть план
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          close();
                          onEditCopy(result.recommendation!.template);
                        }}
                      >
                        Настроить личную копию
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="program-wizard-result__empty">
                    <span className="eyebrow">Подходящего шаблона пока нет</span>
                    <h3>
                      {result.status === 'needs_input'
                        ? 'Нужны дополнительные данные'
                        : 'Совпадений нет'}
                    </h3>
                    <p>{result.message}</p>
                    <div className="program-wizard__result-actions">
                      <button
                        type="button"
                        onClick={() => {
                          setShowResult(false);
                          recommendation.reset();
                          setStep(0);
                        }}
                      >
                        Изменить параметры
                      </button>
                      <AnchorAction href="#program-library" onClick={leaveWizard}>
                        Выбрать из шаблонов
                      </AnchorAction>
                      <AnchorAction href="#program-builder" onClick={leaveWizard}>
                        Создать свою
                      </AnchorAction>
                    </div>
                  </div>
                )}

                {!!result.alternatives?.length && (
                  <section
                    className="program-wizard-result__alternatives"
                    aria-labelledby="program-alternatives-title"
                  >
                    <div>
                      <span className="eyebrow">Другие варианты</span>
                      <h3 id="program-alternatives-title">Можно сравнить</h3>
                    </div>
                    {result.alternatives.map((alternative) => (
                      <article key={alternative.template.id}>
                        <div>
                          <strong>{alternative.template.title}</strong>
                          <p>{alternative.reason}</p>
                        </div>
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => {
                            close();
                            onPreview(alternative.template);
                          }}
                        >
                          Посмотреть
                        </button>
                      </article>
                    ))}
                  </section>
                )}

                <footer className="program-wizard__footer program-wizard__footer--result">
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => {
                      setShowResult(false);
                      recommendation.reset();
                      setStep(stepTitles.length - 1);
                    }}
                  >
                    Вернуться к ответам
                  </button>
                  <button type="button" className="secondary" onClick={close}>
                    Закрыть
                  </button>
                </footer>
                <small className="program-wizard__disclaimer">
                  Результат рассчитан по фиксированным правилам и не является медицинской
                  рекомендацией.
                </small>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export { ProgramRecommendation as LegacyProgramRecommendation };
