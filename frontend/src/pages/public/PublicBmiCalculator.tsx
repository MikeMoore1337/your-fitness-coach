import { useState, type FormEvent } from 'react';

type BmiResult = {
  value: number;
  category: string;
};

const MIN_WEIGHT_KG = 1;
const MAX_WEIGHT_KG = 500;
const MIN_HEIGHT_CM = 50;
const MAX_HEIGHT_CM = 250;

function parseMetricValue(value: string): number | null {
  const normalized = value.trim().replace(',', '.');
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function bmiCategory(value: number): string {
  if (value < 18.5) return 'Ниже диапазона для взрослых';
  if (value < 25) return 'Нормальный диапазон для взрослых';
  if (value < 30) return 'Избыточная масса тела (предожирение)';
  if (value < 35) return 'Ожирение I степени';
  if (value < 40) return 'Ожирение II степени';
  return 'Ожирение III степени';
}

function formatBmi(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
  }).format(value);
}

export default function PublicBmiCalculator() {
  const [weight, setWeight] = useState('');
  const [height, setHeight] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BmiResult | null>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const weightValue = parseMetricValue(weight);
    const heightValue = parseMetricValue(height);

    if (weightValue === null || weightValue < MIN_WEIGHT_KG || weightValue > MAX_WEIGHT_KG) {
      setError('Укажите массу тела от 1 до 500 кг.');
      setResult(null);
      return;
    }
    if (heightValue === null || heightValue < MIN_HEIGHT_CM || heightValue > MAX_HEIGHT_CM) {
      setError('Укажите рост от 50 до 250 см.');
      setResult(null);
      return;
    }

    const value = weightValue / (heightValue / 100) ** 2;
    setError(null);
    setResult({ value, category: bmiCategory(value) });
  };

  return (
    <section
      id="public-bmi-calculator"
      className="public-calculator"
      aria-labelledby="public-bmi-calculator-title"
    >
      <div className="public-calculator__header">
        <p className="landing-kicker">Интерактивный блок</p>
        <h2 id="public-bmi-calculator-title">Рассчитать ИМТ</h2>
        <p>
          Введите массу и рост, чтобы получить формулу-ориентир для взрослого человека. Значения
          используются только в этом расчёте: они не отправляются, не сохраняются и не попадают в
          аналитику.
        </p>
      </div>

      <form
        className="public-calculator__form"
        onSubmit={handleSubmit}
        noValidate
        aria-labelledby="public-bmi-calculator-title"
      >
        <div className="public-calculator__fields">
          <label>
            <span>Масса тела, кг</span>
            <input
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={weight}
              onChange={(event) => setWeight(event.target.value)}
              aria-invalid={error !== null}
              aria-describedby="public-bmi-calculator-help"
            />
          </label>
          <label>
            <span>Рост, см</span>
            <input
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={height}
              onChange={(event) => setHeight(event.target.value)}
              aria-invalid={error !== null}
              aria-describedby="public-bmi-calculator-help"
            />
          </label>
        </div>
        <button className="landing-button public-calculator__submit" type="submit">
          Рассчитать ИМТ
        </button>
        <p id="public-bmi-calculator-help" className="public-calculator__help">
          Допустимы точка и запятая в десятичном числе. Пример: 80 кг и 180 см.
        </p>
      </form>

      {error && (
        <p className="public-calculator__error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <div className="public-calculator__result" role="status" aria-live="polite">
          <span>Результат</span>
          <strong>ИМТ: {formatBmi(result.value)}</strong>
          <p>{result.category}</p>
          <small>
            Это скрининговое описание для взрослых, а не диагноз и не оценка состава тела. Не
            используйте его для детей, подростков, беременности или самостоятельных медицинских
            решений.
          </small>
        </div>
      )}
    </section>
  );
}
