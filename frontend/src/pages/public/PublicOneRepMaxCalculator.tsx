import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  calculateOneRepMax,
  type OneRepMaxEstimate,
  type OneRepMaxValidationError,
} from '../../features/workouts/oneRepMaxCalculator';
import { trackGrowthEvent } from '../../shared/analytics/productEvents';

function parseMetricValue(value: string): number {
  const normalized = value.trim().replace(',', '.');
  if (!normalized) return Number.NaN;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function formatWeight(valueKg: number): string {
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 1,
  }).format(valueKg);
}

function errorFor(
  errors: OneRepMaxValidationError[],
  field: OneRepMaxValidationError['field'],
): string | null {
  return errors.find((error) => error.field === field)?.message ?? null;
}

function OneRepMaxResult({ estimate }: { estimate: OneRepMaxEstimate }) {
  return (
    <div
      className="public-calculator__result public-one-rm-calculator__result"
      role="status"
      aria-live="polite"
    >
      <span>Оценочный результат</span>
      <strong>{formatWeight(estimate.estimated1rmKg)} кг</strong>
      <p>Расчётный 1ПМ — ориентир, а не измеренный максимум.</p>
      <div className="public-one-rm-calculator__table-wrap">
        <table className="public-one-rm-calculator__table">
          <caption>Ориентиры для планирования нагрузки</caption>
          <thead>
            <tr>
              <th scope="col">Процент от 1ПМ</th>
              <th scope="col">Вес</th>
            </tr>
          </thead>
          <tbody>
            {estimate.workingWeights.map(({ percentage, weightKg }) => (
              <tr key={percentage}>
                <th scope="row">{percentage}%</th>
                <td>{formatWeight(weightKg)} кг</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <small>
        Проценты не назначают обязательный вес: учитывайте упражнение, технику, отдых и текущее
        состояние. Сам расчёт здесь не сохраняется.
      </small>
    </div>
  );
}

export default function PublicOneRepMaxCalculator() {
  const [weight, setWeight] = useState('');
  const [repetitions, setRepetitions] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [result, setResult] = useState<OneRepMaxEstimate | null>(null);
  const startedTrackedRef = useRef(false);
  const resultTrackedRef = useRef(false);

  const calculation = useMemo(
    () =>
      calculateOneRepMax({
        weightKg: parseMetricValue(weight),
        repetitions: parseMetricValue(repetitions),
      }),
    [repetitions, weight],
  );
  const weightError = submitted ? errorFor(calculation.errors, 'weightKg') : null;
  const repetitionsError = submitted ? errorFor(calculation.errors, 'repetitions') : null;
  const helpId = 'public-one-rm-calculator-help';
  const errorSummaryId = 'public-one-rm-calculator-error';
  const weightErrorId = 'public-one-rm-calculator-weight-error';
  const repetitionsErrorId = 'public-one-rm-calculator-repetitions-error';

  const markStarted = () => {
    if (startedTrackedRef.current) return;
    startedTrackedRef.current = true;
    trackGrowthEvent('calculator_started');
  };

  const updateField = (setter: (value: string) => void, value: string) => {
    markStarted();
    setter(value);
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
      id="public-one-rm-calculator"
      className="public-calculator public-one-rm-calculator ym-hide-content"
      aria-labelledby="public-one-rm-calculator-title"
    >
      <div className="public-calculator__header">
        <p className="landing-kicker">Бесплатный инструмент</p>
        <h2 id="public-one-rm-calculator-title">Рассчитать 1ПМ онлайн</h2>
        <p>
          Введите вес и число повторений одного подхода, чтобы получить оценочный одноповторный
          максимум и проценты для планирования. Значения используются только в этом окне браузера:
          они не отправляются, не сохраняются и не попадают в аналитику.
        </p>
      </div>

      <form
        className="public-calculator__form"
        onSubmit={handleSubmit}
        noValidate
        aria-labelledby="public-one-rm-calculator-title"
        aria-describedby={helpId}
      >
        <div className="public-calculator__fields">
          <div className="public-calculator__field">
            <label htmlFor="public-one-rm-calculator-weight">
              <span>Вес в подходе, кг</span>
              <input
                id="public-one-rm-calculator-weight"
                type="text"
                inputMode="decimal"
                autoComplete="off"
                value={weight}
                onChange={(event) => updateField(setWeight, event.target.value)}
                aria-invalid={weightError !== null}
                aria-describedby={weightError ? `${helpId} ${weightErrorId}` : helpId}
              />
            </label>
            {weightError && (
              <small id={weightErrorId} className="public-calculator__field-error">
                {weightError}
              </small>
            )}
          </div>
          <div className="public-calculator__field">
            <label htmlFor="public-one-rm-calculator-repetitions">
              <span>Повторения в подходе</span>
              <input
                id="public-one-rm-calculator-repetitions"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                value={repetitions}
                onChange={(event) => updateField(setRepetitions, event.target.value)}
                aria-invalid={repetitionsError !== null}
                aria-describedby={repetitionsError ? `${helpId} ${repetitionsErrorId}` : helpId}
              />
            </label>
            {repetitionsError && (
              <small id={repetitionsErrorId} className="public-calculator__field-error">
                {repetitionsError}
              </small>
            )}
          </div>
        </div>
        <button className="landing-button public-calculator__submit" type="submit">
          Рассчитать 1ПМ
        </button>
        <p id={helpId} className="public-calculator__help">
          Допустимы точка и запятая в весе. Укажите от 0,5 до 500 кг и от 1 до 10 целых повторений.
        </p>
      </form>

      {submitted && !calculation.valid && (
        <p id={errorSummaryId} className="public-calculator__error" role="alert">
          Проверьте выделенные поля и укажите данные в допустимом диапазоне.
        </p>
      )}

      {result && <OneRepMaxResult estimate={result} />}
    </section>
  );
}
