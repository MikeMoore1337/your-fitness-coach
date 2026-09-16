import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  calculateNutritionEstimate,
  type NutritionCalculatorInput,
  type NutritionEstimate,
} from '../../features/nutrition/nutritionCalculator';
import {
  accuracyLabels,
  cardioIntensityOptions,
  cardioKindOptions,
  goalOptions,
  newCardioTraining,
  nutritionCalculatorDefaults,
  routineOptions,
  stepsOptions,
  strengthRestOptions,
  strengthTypeOptions,
  type CardioTraining,
} from '../../features/nutrition/nutritionCalculatorOptions';
import { trackGrowthEvent } from '../../shared/analytics/productEvents';

type NumericField =
  | 'age'
  | 'weight_kg'
  | 'height_cm'
  | 'strength_trainings_per_week'
  | 'strength_training_duration_minutes';

type ErrorField = NumericField | 'cardio';

const initialForm: NutritionCalculatorInput = {
  ...nutritionCalculatorDefaults,
  age: 0,
  height_cm: 0,
  weight_kg: 0,
  steps_range: 'unknown',
  strength_trainings_per_week: 0,
};

function fieldValue(value: number): number | string {
  return value === 0 ? '' : value;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value);
}

function hasError(errors: string[], field: ErrorField, cardioIndex?: number): boolean {
  if (field === 'weight_kg') return errors.some((error) => error.startsWith('Вес:'));
  if (field === 'height_cm') return errors.some((error) => error.startsWith('Рост:'));
  if (field === 'age') return errors.some((error) => error.startsWith('Возраст:'));
  if (field === 'strength_trainings_per_week') {
    return errors.some(
      (error) => error.startsWith('Силовые тренировки') || error.includes('силовых'),
    );
  }
  if (field === 'strength_training_duration_minutes') {
    return errors.some((error) => error.startsWith('Длительность силовой'));
  }
  if (field === 'cardio' && cardioIndex !== undefined) {
    return errors.some((error) => error.startsWith(`Кардио ${cardioIndex + 1}`));
  }
  return false;
}

function ResultSummary({ estimate }: { estimate: NutritionEstimate }) {
  return (
    <div className="public-calculator__result" role="status" aria-live="polite">
      <span>Ваш стартовый ориентир</span>
      <div className="public-kbju-calculator__metrics">
        <div>
          <span>Калории</span>
          <strong>{formatNumber(estimate.calories)} ккал</strong>
        </div>
        <div>
          <span>Белки</span>
          <strong>{formatNumber(estimate.protein)} г</strong>
        </div>
        <div>
          <span>Жиры</span>
          <strong>{formatNumber(estimate.fat)} г</strong>
        </div>
        <div>
          <span>Углеводы</span>
          <strong>{formatNumber(estimate.carbs)} г</strong>
        </div>
      </div>
      <p>
        Для поддержания: {formatNumber(estimate.maintenanceCalories)} ккал. Точность стартовой
        оценки: {accuracyLabels[estimate.accuracy]}.
      </p>
      {estimate.macroWarning && (
        <small>
          Расчёт поднят до минимального сочетания белка и жиров; углеводы в этом сценарии показаны
          как 0 г.
        </small>
      )}
      <small>Проверьте ориентир по средней динамике за 14–21 день, а не по одному измерению.</small>
    </div>
  );
}

export default function PublicNutritionCalculator() {
  const [form, setForm] = useState<NutritionCalculatorInput>(initialForm);
  const [submitted, setSubmitted] = useState(false);
  const [result, setResult] = useState<NutritionEstimate | null>(null);
  const startedTrackedRef = useRef(false);
  const resultTrackedRef = useRef(false);

  const calculation = useMemo(() => calculateNutritionEstimate(form), [form]);
  const errorId = 'public-kbju-calculator-error';
  const helpId = 'public-kbju-calculator-help';

  const markStarted = () => {
    if (startedTrackedRef.current) return;
    startedTrackedRef.current = true;
    trackGrowthEvent('calculator_started');
  };

  const updateForm = (updates: Partial<NutritionCalculatorInput>) => {
    markStarted();
    setForm((current) => ({ ...current, ...updates }));
    setSubmitted(false);
    setResult(null);
  };

  const setNumber = (key: NumericField, value: string) => {
    const normalized = value.replace(',', '.');
    updateForm({
      [key]: normalized === '' ? 0 : Number(normalized),
    } as Partial<NutritionCalculatorInput>);
  };

  const updateCardio = (index: number, updates: Partial<CardioTraining>) => {
    markStarted();
    setForm((current) => ({
      ...current,
      cardio_trainings: current.cardio_trainings.map((training, trainingIndex) =>
        trainingIndex === index ? { ...training, ...updates } : training,
      ),
    }));
    setSubmitted(false);
    setResult(null);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    markStarted();
    setSubmitted(true);
    if (!calculation.valid) {
      setResult(null);
      return;
    }
    setResult(calculation.estimate);
  };

  useEffect(() => {
    if (!result || resultTrackedRef.current) return;
    resultTrackedRef.current = true;
    trackGrowthEvent('calculator_result');
  }, [result]);

  return (
    <section
      id="public-kbju-calculator"
      className="public-calculator public-kbju-calculator ym-hide-content"
      aria-labelledby="public-kbju-calculator-title"
    >
      <div className="public-calculator__header">
        <p className="landing-kicker">Бесплатный инструмент</p>
        <h2 id="public-kbju-calculator-title">Рассчитать КБЖУ онлайн</h2>
        <p>
          Введите основные параметры, активность и цель, чтобы получить стартовую оценку калорий,
          белков, жиров и углеводов. Расчёт выполняется в браузере: введённые значения не
          отправляются и не сохраняются.
        </p>
      </div>

      <form
        className="public-calculator__form"
        onSubmit={handleSubmit}
        noValidate
        aria-labelledby="public-kbju-calculator-title"
        aria-describedby={helpId}
      >
        <div className="public-calculator__fields">
          <label>
            <span>Пол</span>
            <select
              value={form.sex}
              onChange={(event) =>
                updateForm({ sex: event.target.value as NutritionCalculatorInput['sex'] })
              }
            >
              <option value="male">Мужской</option>
              <option value="female">Женский</option>
            </select>
          </label>
          <label>
            <span>Возраст, лет</span>
            <input
              type="number"
              min="18"
              max="100"
              step="1"
              inputMode="numeric"
              autoComplete="off"
              value={fieldValue(form.age)}
              onChange={(event) => setNumber('age', event.target.value)}
              aria-invalid={submitted && hasError(calculation.errors, 'age')}
            />
          </label>
          <label>
            <span>Вес, кг</span>
            <input
              type="number"
              min="20"
              max="350"
              step="0.1"
              inputMode="decimal"
              autoComplete="off"
              value={fieldValue(form.weight_kg)}
              onChange={(event) => setNumber('weight_kg', event.target.value)}
              aria-invalid={submitted && hasError(calculation.errors, 'weight_kg')}
            />
          </label>
          <label>
            <span>Рост, см</span>
            <input
              type="number"
              min="100"
              max="250"
              step="0.1"
              inputMode="decimal"
              autoComplete="off"
              value={fieldValue(form.height_cm)}
              onChange={(event) => setNumber('height_cm', event.target.value)}
              aria-invalid={submitted && hasError(calculation.errors, 'height_cm')}
            />
          </label>
          <label className="public-calculator__field--wide">
            <span>Цель</span>
            <select
              value={form.goal}
              onChange={(event) =>
                updateForm({ goal: event.target.value as NutritionCalculatorInput['goal'] })
              }
            >
              {Object.entries(goalOptions).map(([value, option]) => (
                <option key={value} value={value}>
                  {option.label}
                </option>
              ))}
            </select>
            <small>{goalOptions[form.goal].description}</small>
          </label>
          <label className="public-calculator__field--wide">
            <span>Как проходит большая часть дня?</span>
            <select
              value={form.daily_routine}
              onChange={(event) =>
                updateForm({
                  daily_routine: event.target.value as NutritionCalculatorInput['daily_routine'],
                })
              }
            >
              {Object.entries(routineOptions).map(([value, option]) => (
                <option key={value} value={value}>
                  {option.label}
                </option>
              ))}
            </select>
            <small>{routineOptions[form.daily_routine].description}</small>
          </label>
          <label className="public-calculator__field--wide">
            <span>Сколько шагов обычно проходите вне тренировок?</span>
            <select
              value={form.steps_range}
              onChange={(event) =>
                updateForm({
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
            <small>Если не знаете, выберите этот вариант: оценка будет менее точной.</small>
          </label>
          <label>
            <span>Силовых тренировок в неделю</span>
            <input
              type="number"
              min="0"
              max="14"
              step="1"
              inputMode="numeric"
              autoComplete="off"
              value={fieldValue(form.strength_trainings_per_week)}
              onChange={(event) => setNumber('strength_trainings_per_week', event.target.value)}
              aria-invalid={
                submitted && hasError(calculation.errors, 'strength_trainings_per_week')
              }
            />
          </label>
        </div>

        <details className="public-calculator__details">
          <summary>Уточнить расчёт тренировочной нагрузки</summary>
          <p>
            Эти поля необязательны. Они помогают учесть длительность и характер силовой работы, а
            также отдельные кардиотренировки.
          </p>
          <div className="public-calculator__fields">
            <label>
              <span>Длительность силовой, минут</span>
              <input
                type="number"
                min="10"
                max="300"
                step="1"
                inputMode="numeric"
                autoComplete="off"
                value={fieldValue(form.strength_training_duration_minutes)}
                onChange={(event) =>
                  setNumber('strength_training_duration_minutes', event.target.value)
                }
                aria-invalid={
                  submitted && hasError(calculation.errors, 'strength_training_duration_minutes')
                }
              />
            </label>
            <label>
              <span>Тип силовой тренировки</span>
              <select
                value={form.strength_training_type}
                onChange={(event) =>
                  updateForm({
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
              <small>{strengthTypeOptions[form.strength_training_type].description}</small>
            </label>
            <label className="public-calculator__field--wide">
              <span>Отдых между подходами</span>
              <select
                value={form.strength_rest ?? ''}
                onChange={(event) =>
                  updateForm({
                    strength_rest: (event.target.value ||
                      null) as NutritionCalculatorInput['strength_rest'],
                  })
                }
              >
                {Object.entries(strengthRestOptions).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="public-kbju-calculator__cardio">
            <div className="public-kbju-calculator__cardio-heading">
              <div>
                <strong>Кардиотренировки</strong>
                <p>Добавьте обычные виды кардио, если хотите учесть их в среднем за неделю.</p>
              </div>
              <button
                type="button"
                className="public-calculator__secondary"
                onClick={() =>
                  updateForm({ cardio_trainings: [...form.cardio_trainings, newCardioTraining()] })
                }
              >
                Добавить кардио
              </button>
            </div>

            {form.cardio_trainings.map((training, index) => (
              <div className="public-kbju-calculator__cardio-item" key={index}>
                <div className="public-kbju-calculator__cardio-heading">
                  <strong>Кардио {index + 1}</strong>
                  <button
                    type="button"
                    className="public-calculator__secondary"
                    aria-label={`Удалить кардио ${index + 1}`}
                    onClick={() =>
                      updateForm({
                        cardio_trainings: form.cardio_trainings.filter(
                          (_, trainingIndex) => trainingIndex !== index,
                        ),
                      })
                    }
                  >
                    Удалить
                  </button>
                </div>
                <div className="public-calculator__fields">
                  <label>
                    <span>Вид</span>
                    <select
                      value={training.kind}
                      onChange={(event) =>
                        updateCardio(index, { kind: event.target.value as CardioTraining['kind'] })
                      }
                      aria-invalid={submitted && hasError(calculation.errors, 'cardio', index)}
                    >
                      {Object.entries(cardioKindOptions).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Тренировок в неделю</span>
                    <input
                      type="number"
                      min="1"
                      max="14"
                      step="1"
                      inputMode="numeric"
                      value={fieldValue(training.trainings_per_week)}
                      onChange={(event) =>
                        updateCardio(index, {
                          trainings_per_week:
                            event.target.value === '' ? 0 : Number(event.target.value),
                        })
                      }
                      aria-invalid={submitted && hasError(calculation.errors, 'cardio', index)}
                    />
                  </label>
                  <label>
                    <span>Длительность, минут</span>
                    <input
                      type="number"
                      min="10"
                      max="300"
                      step="1"
                      inputMode="numeric"
                      value={fieldValue(training.duration_minutes)}
                      onChange={(event) =>
                        updateCardio(index, {
                          duration_minutes:
                            event.target.value === '' ? 0 : Number(event.target.value),
                        })
                      }
                      aria-invalid={submitted && hasError(calculation.errors, 'cardio', index)}
                    />
                  </label>
                  <label>
                    <span>Интенсивность</span>
                    <select
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
                    <small>{cardioIntensityOptions[training.intensity].description}</small>
                  </label>
                </div>
              </div>
            ))}
          </div>
        </details>

        <button className="landing-button public-calculator__submit" type="submit">
          Рассчитать КБЖУ
        </button>
        <p id={helpId} className="public-calculator__help">
          Допустимые значения: 18–100 лет, 20–350 кг и 100–250 см. Расчёт предназначен для взрослых
          и не заменяет консультацию специалиста.
        </p>
      </form>

      {submitted && !calculation.valid && (
        <div id={errorId} className="public-calculator__error" role="alert">
          <strong>Проверьте данные</strong>
          <ul>
            {calculation.errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </div>
      )}

      {result && <ResultSummary estimate={result} />}
    </section>
  );
}
