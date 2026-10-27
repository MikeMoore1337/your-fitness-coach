import type { ReactNode } from 'react';
import { DisclosureIcon } from './common';
import { Icon, type IconName } from './Icon';

export type DataConfidenceStatus = 'sufficient' | 'limited' | 'insufficient';
export type DataConfidenceKind =
  'nutrition' | 'weight' | 'anthropometry' | 'training' | 'calibration';

export interface DataConfidenceSignal {
  status: DataConfidenceStatus;
  counters: Record<string, number>;
  reason_keys: readonly string[];
}

const statusLabels: Record<DataConfidenceStatus, string> = {
  sufficient: 'Данных достаточно для оценки',
  limited: 'Вывод пока предварительный',
  insufficient: 'Пока мало данных',
};

const explanations: Record<DataConfidenceKind, string> = {
  nutrition: 'Пропущенные и неполные дни не считаются нулём и не входят в средние значения.',
  weight:
    'Одна точка не образует тренд, а промежутки между замерами не заполняются предположениями.',
  anthropometry:
    'Окружности сравниваются только с вашей историей и не объясняют изменение отдельной мышцы.',
  training:
    'Оценка использует фактически выполненные рабочие подходы; пропуски не восстанавливаются предположениями.',
  calibration:
    'Это диапазон по завершённым дням, а не точный расход. Цель изменится только после явного подтверждения.',
};

function counter(signal: DataConfidenceSignal, key: string): number | null {
  const value = signal.counters[key];
  return Number.isFinite(value) ? (value ?? null) : null;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value);
}

function plural(value: number, one: string, few: string, many: string): string {
  const absolute = Math.abs(value) % 100;
  const last = absolute % 10;
  if (absolute > 10 && absolute < 20) return many;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

function nutritionBasis(signal: DataConfidenceSignal): string {
  const logged = counter(signal, 'logged_day_count');
  const eligible = counter(signal, 'eligible_day_count');
  if (logged == null || eligible == null) {
    return 'Учитываются только подтверждённые завершённые дни дневника.';
  }
  return `За период дневник заполнен за ${formatNumber(logged)} из ${formatNumber(eligible)} дней.`;
}

function weightBasis(signal: DataConfidenceSignal): string {
  const points = counter(signal, 'point_count');
  const span = counter(signal, 'span_days');
  const requiredPoints = counter(signal, 'required_point_count');
  const requiredSpan = counter(signal, 'required_span_days');
  if (points == null) return 'Для оценки нужны повторные замеры массы по датам.';
  const observed = `${formatNumber(points)} ${plural(points, 'замер', 'замера', 'замеров')}${span == null ? '' : ` за ${formatNumber(span)} ${plural(span, 'день', 'дня', 'дней')}`}`;
  if (requiredPoints == null || requiredSpan == null) return `Сейчас есть ${observed}.`;
  return `Сейчас есть ${observed}; минимум — ${formatNumber(requiredPoints)} замера за ${formatNumber(requiredSpan)} дней.`;
}

function anthropometryBasis(signal: DataConfidenceSignal): string {
  const points = counter(signal, 'maximum_point_count');
  const requiredPoints = counter(signal, 'required_point_count_per_metric');
  const requiredSpan = counter(signal, 'required_span_days_per_metric');
  const sufficientMetrics = counter(signal, 'sufficient_metric_count');
  if (
    signal.status === 'sufficient' &&
    sufficientMetrics != null &&
    requiredPoints != null &&
    requiredSpan != null
  ) {
    return `${formatNumber(sufficientMetrics)} ${plural(sufficientMetrics, 'окружность достигла', 'окружности достигли', 'окружностей достигли')} порога: ${formatNumber(requiredPoints)} ${plural(requiredPoints, 'замер', 'замера', 'замеров')} за период не короче ${formatNumber(requiredSpan)} ${plural(requiredSpan, 'дня', 'дней', 'дней')}.`;
  }
  if (signal.reason_keys.includes('no_anthropometry_measurements')) {
    return 'Пока нет замеров окружностей; для оценки нужны повторные замеры одной и той же окружности.';
  }
  if (signal.reason_keys.includes('too_few_points') && points != null) {
    const observed = `${formatNumber(points)} ${plural(points, 'замер', 'замера', 'замеров')}`;
    if (requiredPoints == null) return `В самой заполненной окружности сейчас есть ${observed}.`;
    return `В самой заполненной окружности — ${observed}; для оценки одной окружности нужно минимум ${formatNumber(requiredPoints)} ${plural(requiredPoints, 'замер', 'замера', 'замеров')}.`;
  }
  if (
    signal.reason_keys.includes('timespan_too_short') &&
    requiredPoints != null &&
    requiredSpan != null
  ) {
    return `Ни одна окружность с ${formatNumber(requiredPoints)} ${plural(requiredPoints, 'замером', 'замерами', 'замерами')} пока не охватывает период в ${formatNumber(requiredSpan)} ${plural(requiredSpan, 'день', 'дня', 'дней')}.`;
  }
  return 'Для оценки нужны повторные замеры одной и той же окружности.';
}

function trainingBasis(signal: DataConfidenceSignal): string {
  const sets = counter(signal, 'working_set_count');
  const sessions = counter(signal, 'workout_session_count');
  const requiredSets = counter(signal, 'required_working_set_count');
  const requiredSessions = counter(signal, 'required_workout_session_count');
  if (sets == null || sessions == null) {
    return 'Учитываются только фактически выполненные рабочие подходы в завершённых тренировках.';
  }
  const observed = `${formatNumber(sets)} ${plural(sets, 'рабочий подход', 'рабочих подхода', 'рабочих подходов')} в ${formatNumber(sessions)} ${plural(sessions, 'тренировке', 'тренировках', 'тренировках')}`;
  if (requiredSets == null || requiredSessions == null) return `Учтено ${observed}.`;
  return `Учтено ${observed}; минимум — ${formatNumber(requiredSets)} подходов в ${formatNumber(requiredSessions)} тренировках.`;
}

function calibrationBasis(signal: DataConfidenceSignal): string {
  const logged = counter(signal, 'logged_day_count');
  const eligible = counter(signal, 'eligible_day_count');
  const start = counter(signal, 'first_window_weight_point_count');
  const end = counter(signal, 'last_window_weight_point_count');
  if (logged == null || eligible == null) {
    return 'Проверка сопоставляет завершённые дни дневника и повторные замеры массы.';
  }
  const weightContext =
    start == null || end == null ? '' : ` Замеров массы в начале и конце окна: ${start} и ${end}.`;
  return `Дневник заполнен за ${formatNumber(logged)} из ${formatNumber(eligible)} завершённых дней.${weightContext}`;
}

export function dataConfidenceBasis(
  kind: DataConfidenceKind,
  signal: DataConfidenceSignal,
): string {
  if (kind === 'nutrition') return nutritionBasis(signal);
  if (kind === 'weight') return weightBasis(signal);
  if (kind === 'anthropometry') return anthropometryBasis(signal);
  if (kind === 'training') return trainingBasis(signal);
  return calibrationBasis(signal);
}

function ConfidenceIcon({ state }: { state: DataConfidenceStatus | 'stale' }) {
  const iconName: Record<DataConfidenceStatus | 'stale', IconName> = {
    sufficient: 'confidence-sufficient',
    limited: 'confidence-limited',
    insufficient: 'confidence-insufficient',
    stale: 'confidence-stale',
  };
  return (
    <span className="data-confidence__icon" aria-hidden="true">
      <Icon name={iconName[state]} />
    </span>
  );
}

export function DataConfidence({
  action,
  className = '',
  isStale = false,
  label,
  kind,
  signal,
}: {
  action?: ReactNode;
  className?: string;
  isStale?: boolean;
  label?: string;
  kind: DataConfidenceKind;
  signal: DataConfidenceSignal;
}) {
  const state = isStale ? 'stale' : signal.status;
  const status = isStale ? 'Показана сохранённая оценка' : statusLabels[signal.status];
  const labeledStatus = label ? `${label} — ${status}` : status;
  const explanation = isStale
    ? `Новые данные загружаются. ${explanations[kind]}`
    : explanations[kind];

  return (
    <section
      aria-label={`Достаточно ли данных: ${labeledStatus}`}
      aria-live={isStale ? 'polite' : undefined}
      className={`data-confidence data-confidence--${state} ${className}`.trim()}
      data-confidence-state={state}
    >
      <ConfidenceIcon state={state} />
      <div className="data-confidence__content">
        <strong className="data-confidence__status">{labeledStatus}</strong>
        <p className="data-confidence__basis">{dataConfidenceBasis(kind, signal)}</p>
        <details className="data-confidence__details">
          <summary className="yfc-disclosure-summary">
            <span>Почему такой вывод</span>
            <DisclosureIcon />
          </summary>
          <p>{explanation}</p>
        </details>
      </div>
      {action && signal.status !== 'sufficient' && !isStale ? (
        <div className="data-confidence__action">{action}</div>
      ) : null}
    </section>
  );
}
