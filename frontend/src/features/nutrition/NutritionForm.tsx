import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';
import type { NutritionTarget, UserProfile } from '../../shared/api/types';
import { invalidateNutritionSummaries, queryKeys } from '../../shared/queryKeys';
import { usePersistentState } from '../../shared/storage';
import { nutritionDraftStorageKey } from '../../shared/userScopedStorage';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { ContextualHelp } from '../../shared/ui/ContextualHelp';
import { Card, DisclosureIcon } from '../../shared/ui/common';
import { ManualNutritionTargetForm } from './ManualNutritionTargetForm';
import { NutritionTargetHistory } from './NutritionTargetHistory';
import { calculateNutritionEstimate, type NutritionCalculatorInput } from './nutritionCalculator';
import {
  accuracyLabels,
  cardioIntensityOptions,
  cardioKindOptions,
  goalAdjustmentLabels,
  goalOptions,
  newCardioTraining,
  nutritionCalculatorDefaults,
  routineOptions,
  stepsOptions,
  strengthRestOptions,
  strengthTypeOptions,
  type CardioTraining,
} from './nutritionCalculatorOptions';

const defaults = nutritionCalculatorDefaults;

function fromInitial(
  initial: NutritionTarget | null | undefined,
  targetTelegramId: number | null | undefined,
  profile: UserProfile | null | undefined,
): NutritionCalculatorInput {
  if (!initial) {
    const birthDate = profile?.birth_date ? new Date(`${profile.birth_date}T12:00:00`) : null;
    const now = new Date();
    const age = birthDate
      ? now.getFullYear() -
        birthDate.getFullYear() -
        (now.getMonth() < birthDate.getMonth() ||
        (now.getMonth() === birthDate.getMonth() && now.getDate() < birthDate.getDate())
          ? 1
          : 0)
      : null;
    const profileGoal =
      profile?.goal && Object.hasOwn(goalOptions, profile.goal)
        ? (profile.goal as NutritionCalculatorInput['goal'])
        : defaults.goal;
    return {
      ...defaults,
      target_telegram_user_id: targetTelegramId,
      goal: profileGoal,
      height_cm: profile?.height_cm ?? defaults.height_cm,
      weight_kg: profile?.weight_kg ?? defaults.weight_kg,
      age: age && age >= 18 && age <= 100 ? age : defaults.age,
    };
  }
  return {
    target_telegram_user_id: targetTelegramId,
    sex: (initial.sex || defaults.sex) as NutritionCalculatorInput['sex'],
    weight_kg: initial.weight_kg ?? profile?.weight_kg ?? defaults.weight_kg,
    height_cm: initial.height_cm ?? profile?.height_cm ?? defaults.height_cm,
    age: initial.age ?? defaults.age,
    daily_routine: (initial.daily_routine ||
      defaults.daily_routine) as NutritionCalculatorInput['daily_routine'],
    steps_range: (initial.steps_range ||
      defaults.steps_range) as NutritionCalculatorInput['steps_range'],
    strength_trainings_per_week:
      initial.strength_trainings_per_week ?? defaults.strength_trainings_per_week,
    strength_training_duration_minutes:
      initial.strength_training_duration_minutes ?? defaults.strength_training_duration_minutes,
    strength_training_type: (initial.strength_training_type ||
      defaults.strength_training_type) as NutritionCalculatorInput['strength_training_type'],
    strength_rest: initial.strength_rest as NutritionCalculatorInput['strength_rest'],
    cardio_trainings: initial.cardio_trainings ?? [],
    goal: (initial.goal || defaults.goal) as NutritionCalculatorInput['goal'],
  };
}

export function NutritionForm({
  clientId,
  targetTelegramId,
  initial,
  timeZone,
  onSaved,
  readOnly = false,
}: {
  clientId?: number;
  targetTelegramId?: number | null;
  initial?: NutritionTarget | null;
  timeZone?: string | null;
  onSaved?: () => void | Promise<void>;
  readOnly?: boolean;
}) {
  const { toast } = useFeedback();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<'calculated' | 'manual'>(
    initial?.source === 'manual' ? 'manual' : 'calculated',
  );
  const [form, setForm, clearDraft] = usePersistentState<NutritionCalculatorInput>(
    nutritionDraftStorageKey(
      targetTelegramId ? `client_${targetTelegramId}` : `user_${user?.id ?? 'me'}`,
    ),
    () => fromInitial(initial, targetTelegramId, targetTelegramId ? null : user?.profile),
  );

  const calculation = useMemo(() => calculateNutritionEstimate(form), [form]);
  const estimate = calculation.estimate;

  const mutation = useMutation({
    mutationFn: () =>
      api<NutritionTarget>('/api/v1/nutrition/targets', {
        method: 'POST',
        body: {
          ...form,
          strength_training_duration_minutes:
            form.strength_trainings_per_week > 0
              ? form.strength_training_duration_minutes
              : form.strength_training_duration_minutes || 60,
          target_telegram_user_id: targetTelegramId || null,
        },
      }),
    onSuccess: async () => {
      clearDraft();
      await Promise.all([
        invalidateNutritionSummaries(queryClient, clientId),
        queryClient.invalidateQueries({
          queryKey: queryKeys.nutrition.targetHistory(targetTelegramId),
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.currentTarget }),
        ...(!clientId
          ? [queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all })]
          : []),
      ]);
      await onSaved?.();
      toast('Ориентиры КБЖУ сохранены');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  const setNumber = (
    key:
      | 'age'
      | 'weight_kg'
      | 'height_cm'
      | 'strength_trainings_per_week'
      | 'strength_training_duration_minutes',
    value: string,
  ) => setForm({ ...form, [key]: value === '' ? 0 : Number(value) });

  const updateCardio = (index: number, updates: Partial<CardioTraining>) =>
    setForm({
      ...form,
      cardio_trainings: form.cardio_trainings.map((training, trainingIndex) =>
        trainingIndex === index ? { ...training, ...updates } : training,
      ),
    });

  return (
    <Card title="КБЖУ" description="Рассчитайте ориентир и отслеживайте его рядом с дневником.">
      {readOnly && (
        <p className="muted demo-capability-notice" role="status">
          Изменение ориентиров КБЖУ доступно после входа. В демо можно только посмотреть расчёт.
        </p>
      )}
      <fieldset
        className="nutrition-form-fieldset"
        disabled={readOnly}
        aria-label="Настройки ориентиров КБЖУ"
      >
        <div className="nutrition-target-mode" role="group" aria-label="Способ задания ориентиров">
          <button
            type="button"
            className={mode === 'calculated' ? 'is-active' : undefined}
            aria-pressed={mode === 'calculated'}
            onClick={() => setMode('calculated')}
          >
            Рассчитать ориентиры
          </button>
          <button
            type="button"
            className={mode === 'manual' ? 'is-active' : undefined}
            aria-pressed={mode === 'manual'}
            onClick={() => setMode('manual')}
          >
            Указать вручную
          </button>
        </div>
        {mode === 'manual' ? (
          <ManualNutritionTargetForm
            clientId={clientId}
            targetTelegramId={targetTelegramId}
            initial={initial}
            timeZone={timeZone}
            onSaved={onSaved}
          />
        ) : (
          <>
            <ContextualHelp articlePath="/knowledge/nutrition/kbju-as-a-reference">
              <p>
                КБЖУ — стартовая оценка калорий и макронутриентов, а не измерение вашего расхода и
                не медицинская рекомендация.
              </p>
            </ContextualHelp>
            <form
              className="stack top-gap"
              onSubmit={(event) => {
                event.preventDefault();
                if (calculation.valid) mutation.mutate();
              }}
            >
              <div className="form-grid nutrition-form-grid">
                <label className="field">
                  <span>Пол</span>
                  <select
                    value={form.sex}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        sex: event.target.value as NutritionCalculatorInput['sex'],
                      })
                    }
                  >
                    <option value="male">Мужской</option>
                    <option value="female">Женский</option>
                  </select>
                </label>
                <label className="field">
                  <span>Возраст</span>
                  <input
                    type="number"
                    min="18"
                    max="100"
                    required
                    value={form.age || ''}
                    onChange={(event) => setNumber('age', event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Вес, кг</span>
                  <input
                    type="number"
                    min="20"
                    max="350"
                    step="0.1"
                    required
                    value={form.weight_kg || ''}
                    onChange={(event) => setNumber('weight_kg', event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Рост, см</span>
                  <input
                    type="number"
                    min="100"
                    max="250"
                    step="0.1"
                    required
                    value={form.height_cm || ''}
                    onChange={(event) => setNumber('height_cm', event.target.value)}
                  />
                </label>
                <label className="field nutrition-form-grid__wide">
                  <span>Цель</span>
                  <select
                    value={form.goal}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        goal: event.target.value as NutritionCalculatorInput['goal'],
                      })
                    }
                  >
                    {Object.entries(goalOptions).map(([value, option]) => (
                      <option key={value} value={value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <small className="field-hint">{goalOptions[form.goal].description}</small>
                </label>

                <label className="field nutrition-form-grid__wide">
                  <span>Как проходит большая часть вашего дня?</span>
                  <select
                    value={form.daily_routine}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        daily_routine: event.target
                          .value as NutritionCalculatorInput['daily_routine'],
                      })
                    }
                  >
                    {Object.entries(routineOptions).map(([value, option]) => (
                      <option key={value} value={value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <small className="field-hint">
                    {routineOptions[form.daily_routine].description}
                  </small>
                </label>

                <label className="field nutrition-form-grid__wide">
                  <span>Сколько шагов вы обычно проходите вне тренировок?</span>
                  <select
                    value={form.steps_range}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        steps_range: event.target.value as NutritionCalculatorInput['steps_range'],
                      })
                    }
                  >
                    {Object.entries(stepsOptions).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <small className="field-hint">
                    Не учитывайте здесь отдельную ходьбу, бег или другое кардио, которое добавите
                    ниже как тренировку.
                  </small>
                </label>

                <label className="field">
                  <span>Силовых тренировок в неделю</span>
                  <input
                    type="number"
                    min="0"
                    max="14"
                    step="1"
                    required
                    value={form.strength_trainings_per_week}
                    onChange={(event) =>
                      setNumber('strength_trainings_per_week', event.target.value)
                    }
                  />
                </label>
                <label className="field">
                  <span>Средняя продолжительность, минут</span>
                  <input
                    type="number"
                    min="10"
                    max="300"
                    step="1"
                    required={form.strength_trainings_per_week > 0}
                    value={form.strength_training_duration_minutes || ''}
                    onChange={(event) =>
                      setNumber('strength_training_duration_minutes', event.target.value)
                    }
                  />
                </label>
                <label className="field nutrition-form-grid__wide">
                  <span>Как обычно проходит силовая тренировка?</span>
                  <select
                    required
                    value={form.strength_training_type}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        strength_training_type: event.target
                          .value as NutritionCalculatorInput['strength_training_type'],
                      })
                    }
                  >
                    {Object.entries(strengthTypeOptions).map(([value, option]) => (
                      <option key={value} value={value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <small className="field-hint">
                    {strengthTypeOptions[form.strength_training_type].description}
                  </small>
                </label>
                <label className="field nutrition-form-grid__wide">
                  <span>Средний отдых между подходами (необязательно)</span>
                  <select
                    value={form.strength_rest ?? ''}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        strength_rest: (event.target.value ||
                          null) as NutritionCalculatorInput['strength_rest'],
                      })
                    }
                  >
                    <option value="">Не выбран</option>
                    {Object.entries(strengthRestOptions).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <section className="stack nutrition-cardio-section" aria-labelledby="cardio-heading">
                <div className="nutrition-section-heading">
                  <div>
                    <strong id="cardio-heading">Кардиотренировки</strong>
                    <p className="muted">Добавьте каждый обычный вид кардио отдельно.</p>
                  </div>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() =>
                      setForm({
                        ...form,
                        cardio_trainings: [...form.cardio_trainings, newCardioTraining()],
                      })
                    }
                  >
                    Добавить кардио
                  </button>
                </div>

                {form.cardio_trainings.length === 0 && (
                  <p className="muted">Если кардио нет, ничего добавлять не нужно.</p>
                )}

                {form.cardio_trainings.map((training, index) => (
                  <div className="nutrition-cardio-item" key={index}>
                    <div className="nutrition-section-heading">
                      <strong>Кардио {index + 1}</strong>
                      <button
                        type="button"
                        className="secondary"
                        aria-label={`Удалить кардио ${index + 1}`}
                        onClick={() =>
                          setForm({
                            ...form,
                            cardio_trainings: form.cardio_trainings.filter(
                              (_, trainingIndex) => trainingIndex !== index,
                            ),
                          })
                        }
                      >
                        Удалить
                      </button>
                    </div>
                    <div className="form-grid nutrition-form-grid">
                      <label className="field">
                        <span>Вид</span>
                        <select
                          required
                          value={training.kind}
                          onChange={(event) =>
                            updateCardio(index, {
                              kind: event.target.value as CardioTraining['kind'],
                            })
                          }
                        >
                          {Object.entries(cardioKindOptions).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>Тренировок в неделю</span>
                        <input
                          type="number"
                          min="1"
                          max="14"
                          step="1"
                          required
                          value={training.trainings_per_week}
                          onChange={(event) =>
                            updateCardio(index, {
                              trainings_per_week:
                                event.target.value === '' ? 0 : Number(event.target.value),
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Средняя продолжительность, минут</span>
                        <input
                          type="number"
                          min="10"
                          max="300"
                          step="1"
                          required
                          value={training.duration_minutes || ''}
                          onChange={(event) =>
                            updateCardio(index, {
                              duration_minutes:
                                event.target.value === '' ? 0 : Number(event.target.value),
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Интенсивность</span>
                        <select
                          required
                          value={training.intensity}
                          onChange={(event) =>
                            updateCardio(index, {
                              intensity: event.target.value as CardioTraining['intensity'],
                            })
                          }
                        >
                          {Object.entries(cardioIntensityOptions).map(([value, option]) => (
                            <option key={value} value={value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                        <small className="field-hint">
                          {cardioIntensityOptions[training.intensity].description}
                        </small>
                      </label>
                    </div>
                  </div>
                ))}
              </section>

              {!calculation.valid && (
                <div className="nutrition-warning" role="alert">
                  <strong>Проверьте данные</strong>
                  <ul>
                    {calculation.errors.map((error) => (
                      <li key={error}>{error}</li>
                    ))}
                  </ul>
                </div>
              )}

              {estimate && (
                <>
                  <div className="metric-grid nutrition-metrics" aria-live="polite">
                    <div className="metric">
                      <span>Целевая калорийность</span>
                      <strong>{estimate.calories} ккал</strong>
                    </div>
                    <div className="metric">
                      <span>Белки</span>
                      <strong>{estimate.protein} г</strong>
                    </div>
                    <div className="metric">
                      <span>Жиры</span>
                      <strong>{estimate.fat} г</strong>
                    </div>
                    <div className="metric">
                      <span>Углеводы</span>
                      <strong>{estimate.carbs} г</strong>
                    </div>
                  </div>
                  <p className="muted nutrition-result-note">
                    Стартовый ориентир. Проверьте результат по динамике за 14–21 день.
                  </p>

                  {estimate.macroWarning && (
                    <div className="nutrition-warning" role="alert">
                      Исходная калорийность была ниже норм белка и жиров, поэтому ориентир
                      автоматически повышен до минимально согласованного значения, а углеводы
                      показаны как 0 г.
                    </div>
                  )}

                  <details className="nutrition-details">
                    <summary>
                      <span>Подробнее о расчёте</span>
                      <DisclosureIcon />
                    </summary>
                    <p>Основной обмен: {estimate.bmr} ккал.</p>
                    <p>Расход в обычный день без тренировок: {estimate.baseTdee} ккал.</p>
                    <p>
                      Силовые тренировки: в среднем +{estimate.strengthDailyCalories} ккал в день.
                    </p>
                    <p>Кардио: в среднем +{estimate.cardioDailyCalories} ккал в день.</p>
                    <p>Калории для поддержания: {estimate.maintenanceCalories} ккал.</p>
                    <p>Поправка под цель: {goalAdjustmentLabels[form.goal]}.</p>
                    <p>Целевая калорийность: {estimate.calories} ккал.</p>
                    <p>
                      <strong>
                        Точность стартовой оценки: {accuracyLabels[estimate.accuracy]}.
                      </strong>
                    </p>
                  </details>

                  <aside className="nutrition-watch-note">
                    Смарт-часы и фитнес-браслеты оценивают расход калорий приблизительно и могут
                    заметно завышать или занижать его. Не прибавляйте показанные ими калории к
                    рассчитанной норме: указанные тренировки уже учтены приложением.
                  </aside>
                </>
              )}

              <aside className="nutrition-reality-check">
                <strong>Важна проверка по реальной динамике</strong>
                <p>Наблюдайте 14–21 день:</p>
                <ul>
                  <li>ежедневно взвешивайтесь утром в одинаковых условиях;</li>
                  <li>считайте среднюю массу за каждую неделю;</li>
                  <li>поддерживайте примерно одинаковую активность;</li>
                  <li>считайте среднее фактическое потребление калорий.</li>
                </ul>
                <p>
                  Если средняя масса стабильна — это ваша реальная поддерживающая калорийность. Если
                  снижается слишком быстро — добавьте 100–200 ккал. Если стоит — уберите 100–150
                  ккал.
                </p>
              </aside>

              <button disabled={mutation.isPending || !calculation.valid}>
                {mutation.isPending ? 'Сохраняем…' : 'Сохранить КБЖУ'}
              </button>
            </form>
          </>
        )}
      </fieldset>
      <NutritionTargetHistory targetTelegramId={targetTelegramId} />
    </Card>
  );
}
