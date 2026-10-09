import { useId, useMemo, useState, type CSSProperties, type KeyboardEvent } from 'react';
import { Icon } from './Icon';
import { useSemanticMotion } from './useSemanticMotion';
import '../../styles/data-viz.css';
export { TaskProgress } from './TaskProgress';

export interface TimeSeriesPoint {
  href?: string;
  key: string;
  label: string;
  status?: string;
  target?: number | null;
  targetChanged?: boolean;
  value: number | null;
}

export interface TimeSeriesChartProps {
  ariaLabel?: string;
  className?: string;
  includeZero?: boolean;
  metric: string;
  note?: string;
  period: string;
  points: readonly TimeSeriesPoint[];
  print?: boolean;
  targetLabel?: string;
  tableCaption?: string;
  unit: string;
  valueLabel?: string;
}

const chartWidth = 720;
const chartHeight = 260;
const chartInset = { top: 26, right: 24, bottom: 42, left: 62 };

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function formatValue(value: number, maximumFractionDigits = 1): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits }).format(value);
}

function pointTime(key: string, fallback: number): number {
  const parsed = Date.parse(`${key}T12:00:00`);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function niceStep(range: number): number {
  const rough = Math.max(range / 4, Number.EPSILON);
  const power = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / power;
  const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return factor * power;
}

interface SeriesCoordinate {
  x: number;
  y: number;
}

function seriesRuns(
  points: readonly TimeSeriesPoint[],
  x: (index: number) => number,
  y: (value: number) => number,
  field: 'target' | 'value',
): SeriesCoordinate[][] {
  const runs: SeriesCoordinate[][] = [];
  let current: SeriesCoordinate[] = [];
  points.forEach((point, index) => {
    const value = point[field];
    if (value == null) {
      if (current.length) runs.push(current);
      current = [];
      return;
    }
    current.push({ x: x(index), y: y(value) });
  });
  if (current.length) runs.push(current);
  return runs;
}

function smoothSeriesPath(points: readonly SeriesCoordinate[]): string {
  if (points.length === 0) return '';
  if (points.length === 1) return `M ${points[0]!.x} ${points[0]!.y}`;

  const slopes = points.slice(1).map((point, index) => {
    const previous = points[index]!;
    const deltaX = point.x - previous.x;
    return deltaX === 0 ? 0 : (point.y - previous.y) / deltaX;
  });
  const tangents = points.map((_, index) => {
    if (index === 0) return slopes[0] ?? 0;
    if (index === points.length - 1) return slopes.at(-1) ?? 0;
    const previous = slopes[index - 1] ?? 0;
    const next = slopes[index] ?? 0;
    return previous * next <= 0 ? 0 : (previous + next) / 2;
  });

  slopes.forEach((slope, index) => {
    if (slope === 0) {
      tangents[index] = 0;
      tangents[index + 1] = 0;
      return;
    }
    const startRatio = (tangents[index] ?? 0) / slope;
    const endRatio = (tangents[index + 1] ?? 0) / slope;
    const magnitude = Math.hypot(startRatio, endRatio);
    if (magnitude <= 3) return;
    const scale = 3 / magnitude;
    tangents[index] = scale * startRatio * slope;
    tangents[index + 1] = scale * endRatio * slope;
  });

  return points.slice(1).reduce((path, point, index) => {
    const previous = points[index]!;
    const deltaX = point.x - previous.x;
    const controlOffset = deltaX / 3;
    return `${path} C ${previous.x + controlOffset} ${previous.y + (tangents[index] ?? 0) * controlOffset} ${point.x - controlOffset} ${point.y - (tangents[index + 1] ?? 0) * controlOffset} ${point.x} ${point.y}`;
  }, `M ${points[0]!.x} ${points[0]!.y}`);
}

function areaSeriesPath(points: readonly SeriesCoordinate[], baseline: number): string {
  if (points.length < 2) return '';
  const first = points[0]!;
  const last = points.at(-1)!;
  return `${smoothSeriesPath(points)} L ${last.x} ${baseline} L ${first.x} ${baseline} Z`;
}

function targetSeriesSegments(
  points: readonly TimeSeriesPoint[],
  x: (index: number) => number,
  y: (value: number) => number,
): string[] {
  return points.slice(1).flatMap((point, index) => {
    const previous = points[index];
    if (previous?.target == null || point.target == null) return [];
    if (!point.targetChanged) {
      return [`M ${x(index)} ${y(previous.target)} L ${x(index + 1)} ${y(point.target)}`];
    }
    return [
      `M ${x(index)} ${y(previous.target)} L ${x(index + 1)} ${y(previous.target)} L ${x(index + 1)} ${y(point.target)}`,
    ];
  });
}

export function TimeSeriesChart({
  ariaLabel,
  className = '',
  includeZero = false,
  metric,
  note,
  period,
  points,
  print = false,
  targetLabel = 'Цель',
  tableCaption,
  unit,
  valueLabel = 'Факт',
}: TimeSeriesChartProps) {
  const titleId = useId();
  const descriptionId = useId();
  const areaGradientId = `data-viz-area-${useId().replaceAll(':', '')}`;
  const values = points.flatMap((point) =>
    [point.value, point.target].filter((value): value is number => value != null),
  );
  const validIndexes = points.flatMap((point, index) => (point.value == null ? [] : [index]));
  const initialIndex = validIndexes.at(-1) ?? 0;
  const [selectedIndex, setSelectedIndex] = useState(initialIndex);
  const activeIndex = validIndexes.includes(selectedIndex) ? selectedIndex : initialIndex;
  const selectedPoint = points[activeIndex];
  const motionSignature = points
    .map((point) =>
      [
        point.key,
        point.value ?? 'missing',
        point.target ?? 'missing',
        point.targetChanged ?? false,
      ].join(':'),
    )
    .join('|');
  const motion = useSemanticMotion<HTMLElement>(
    `${metric}|${period}|${includeZero}|${motionSignature}`,
    { observe: true },
  );

  const scale = useMemo(() => {
    const rawMinimum = values.length ? Math.min(...values) : 0;
    const rawMaximum = values.length ? Math.max(...values) : 1;
    const baseRange = Math.max(rawMaximum - rawMinimum, Math.abs(rawMaximum) * 0.08, 1);
    const step = niceStep(baseRange);
    const minimum = includeZero
      ? Math.min(0, Math.floor(rawMinimum / step) * step)
      : Math.floor((rawMinimum - baseRange * 0.12) / step) * step;
    const maximum = Math.ceil((rawMaximum + baseRange * 0.12) / step) * step;
    const safeMaximum = maximum === minimum ? minimum + step : maximum;
    const ticks = Array.from(
      { length: 5 },
      (_, index) => minimum + ((safeMaximum - minimum) * index) / 4,
    );
    return { maximum: safeMaximum, minimum, ticks: ticks.reverse() };
  }, [includeZero, values]);

  const times = points.map((point, index) => pointTime(point.key, index));
  const minimumTime = times.length ? Math.min(...times) : 0;
  const maximumTime = times.length ? Math.max(...times) : 1;
  const x = (index: number) => {
    if (points.length <= 1 || minimumTime === maximumTime) return chartWidth / 2;
    const time = times[index] ?? minimumTime;
    return (
      chartInset.left +
      ((time - minimumTime) / (maximumTime - minimumTime)) *
        (chartWidth - chartInset.left - chartInset.right)
    );
  };
  const y = (value: number) =>
    chartInset.top +
    ((scale.maximum - value) / (scale.maximum - scale.minimum)) *
      (chartHeight - chartInset.top - chartInset.bottom);
  const visualBaseline =
    includeZero && scale.minimum <= 0 && scale.maximum >= 0 ? 0 : scale.minimum;
  const actualRuns = seriesRuns(points, x, y, 'value').filter((run) => run.length > 1);
  const targetSegments = targetSeriesSegments(points, x, y);
  const labelIndexes = Array.from(
    new Set([0, Math.floor((points.length - 1) / 2), Math.max(points.length - 1, 0)]),
  ).filter((index) => points[index]);

  const selectNearby = (direction: -1 | 1) => {
    const currentPosition = Math.max(validIndexes.indexOf(activeIndex), 0);
    const nextPosition = clamp(
      currentPosition + direction,
      0,
      Math.max(validIndexes.length - 1, 0),
    );
    const nextIndex = validIndexes[nextPosition];
    if (nextIndex != null) setSelectedIndex(nextIndex);
  };
  const handleNavigationKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === 'Home' || event.key === 'End') {
      const nextIndex = event.key === 'Home' ? validIndexes[0] : validIndexes.at(-1);
      if (nextIndex != null) setSelectedIndex(nextIndex);
      return;
    }
    selectNearby(event.key === 'ArrowLeft' ? -1 : 1);
  };

  if (values.length === 0) {
    return (
      <section
        className={`data-viz-empty ${className}`.trim()}
        aria-label={`${metric}: нет данных`}
      >
        <strong>{metric}</strong>
        <span>{period}</span>
        <p>Нет подтверждённых значений за выбранный период.</p>
      </section>
    );
  }

  return (
    <figure
      className={`data-viz-chart${print ? ' data-viz-chart--print' : ''} ${className}`.trim()}
      id={motion.elementId}
      data-motion-phase={print ? 'idle' : motion.motionPhase}
      data-motion-revision={motion.motionRevision}
      onAnimationEnd={motion.onMotionAnimationEnd}
    >
      <figcaption className="data-viz-chart__heading">
        <span>
          <strong id={titleId}>{metric}</strong>
          <small>{period}</small>
        </span>
        <span className="data-viz-chart__legend" aria-label="Обозначения графика">
          <i className="data-viz-chart__legend-actual" /> {valueLabel}
          {points.some((point) => point.target != null) && (
            <>
              <i className="data-viz-chart__legend-target" /> {targetLabel}
            </>
          )}
        </span>
      </figcaption>
      <p className="sr-only" id={descriptionId}>
        {points
          .map(
            (point) =>
              `${point.label}: ${point.value == null ? 'нет значения' : `${formatValue(point.value)} ${unit}`}${point.target == null ? '' : `, цель ${formatValue(point.target)} ${unit}`}`,
          )
          .join('. ')}
      </p>
      <div className="data-viz-chart__plot">
        <svg
          aria-label={ariaLabel ?? `${metric} за период ${period}`}
          aria-describedby={descriptionId}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        >
          <defs>
            <linearGradient id={areaGradientId} x1="0" x2="0" y1="0" y2="1">
              <stop className="data-viz-chart__area-start" offset="0%" />
              <stop className="data-viz-chart__area-end" offset="100%" />
            </linearGradient>
          </defs>
          {scale.ticks.map((tick) => (
            <g className="data-viz-chart__grid" key={tick}>
              <line
                x1={chartInset.left}
                x2={chartWidth - chartInset.right}
                y1={y(tick)}
                y2={y(tick)}
              />
              <text x={chartInset.left - 10} y={y(tick) + 4} textAnchor="end">
                {formatValue(tick, Math.abs(tick) < 10 ? 1 : 0)} {unit}
              </text>
            </g>
          ))}
          {actualRuns.map((run, index) => (
            <path
              className="data-viz-chart__area"
              d={areaSeriesPath(run, y(visualBaseline))}
              fill={`url(#${areaGradientId})`}
              key={`actual-area-${index}`}
            />
          ))}
          {targetSegments.map((segment) => (
            <path className="data-viz-chart__target" d={segment} key={`target-${segment}`} />
          ))}
          {actualRuns.map((run, index) => (
            <path
              className="data-viz-chart__actual"
              d={smoothSeriesPath(run)}
              key={`actual-${index}`}
              pathLength="1"
            />
          ))}
          {points.map((point, index) =>
            point.targetChanged ? (
              <g className="data-viz-chart__change" key={`change-${point.key}`}>
                <line
                  x1={x(index)}
                  x2={x(index)}
                  y1={chartInset.top}
                  y2={chartHeight - chartInset.bottom}
                />
                <text x={x(index) + 6} y={chartInset.top + 10}>
                  цель изменилась
                </text>
              </g>
            ) : null,
          )}
          {points.map((point, index) =>
            point.value == null ? null : (
              <g
                className={`data-viz-chart__point${index === activeIndex ? ' is-selected' : ''}`}
                key={point.key}
                style={
                  {
                    '--data-viz-point-rise': `${y(visualBaseline) - y(point.value)}px`,
                    '--data-viz-stagger-index': Math.min(index, 8),
                  } as CSSProperties
                }
              >
                <circle
                  aria-hidden="true"
                  className="data-viz-chart__point-hit"
                  cx={x(index)}
                  cy={y(point.value)}
                  onClick={() => setSelectedIndex(index)}
                  r="18"
                />
                <circle
                  aria-hidden="true"
                  className="data-viz-chart__point-ring"
                  cx={x(index)}
                  cy={y(point.value)}
                  r={index === activeIndex ? 7 : 4.5}
                />
                <circle
                  aria-hidden="true"
                  className="data-viz-chart__point-core"
                  cx={x(index)}
                  cy={y(point.value)}
                  r="2"
                />
              </g>
            ),
          )}
          {labelIndexes.map((index) => (
            <text
              className="data-viz-chart__x-label"
              key={`label-${points[index]!.key}`}
              textAnchor={index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'}
              x={x(index)}
              y={chartHeight - 14}
            >
              {points[index]!.label}
            </text>
          ))}
        </svg>
      </div>
      {!print && validIndexes.length > 1 && (
        <div
          aria-label="Навигация по точкам графика"
          className="data-viz-chart__point-navigation"
          onKeyDown={handleNavigationKeyDown}
          role="group"
          tabIndex={0}
        >
          <button
            aria-label="Предыдущая точка графика"
            disabled={activeIndex === validIndexes[0]}
            onClick={() => selectNearby(-1)}
            type="button"
          >
            <Icon name="chevron-left" size={16} />
          </button>
          <span>
            {Math.max(validIndexes.indexOf(activeIndex), 0) + 1} из {validIndexes.length}
          </span>
          <button
            aria-label="Следующая точка графика"
            disabled={activeIndex === validIndexes.at(-1)}
            onClick={() => selectNearby(1)}
            type="button"
          >
            <Icon name="chevron-right" size={16} />
          </button>
        </div>
      )}
      {selectedPoint && !print && (
        <output className="data-viz-chart__selection" aria-live="polite">
          <span>
            <strong>{selectedPoint.label}</strong>
            {selectedPoint.status && <small>{selectedPoint.status}</small>}
          </span>
          <strong>
            {selectedPoint.value == null
              ? 'Нет данных'
              : `${formatValue(selectedPoint.value)} ${unit}`}
          </strong>
          {selectedPoint.target != null && (
            <span>
              {targetLabel.toLowerCase()} {formatValue(selectedPoint.target)} {unit}
            </span>
          )}
          {selectedPoint.href && (
            <a className="data-viz-chart__selection-link" href={selectedPoint.href}>
              Открыть день
            </a>
          )}
        </output>
      )}
      {note && <p className="data-viz-chart__note">{note}</p>}
      <div className="sr-only data-viz-chart__table-wrap">
        <table className="data-viz-chart__table">
          <caption>{tableCaption ?? `${metric}, ${period}`}</caption>
          <thead>
            <tr>
              <th scope="col">Дата</th>
              <th scope="col">{valueLabel}</th>
              <th scope="col">{targetLabel}</th>
              <th scope="col">Состояние</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.key}>
                <th scope="row">{point.label}</th>
                <td>
                  {point.value == null ? 'Нет данных' : `${formatValue(point.value)} ${unit}`}
                </td>
                <td>
                  {point.target == null ? 'Не задана' : `${formatValue(point.target)} ${unit}`}
                </td>
                <td>{point.status ?? 'Подтверждено'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

export function QuantitativeProgress({
  label,
  maximum,
  unit,
  value,
}: {
  label: string;
  maximum: number;
  unit?: string;
  value: number;
}) {
  const safeMaximum = Math.max(maximum, 1);
  const percent = clamp((value / safeMaximum) * 100, 0, 100);
  const motion = useSemanticMotion<HTMLDivElement>(`${label}|${safeMaximum}|${value}`, {
    observe: true,
  });
  return (
    <div
      className="data-viz-progress"
      id={motion.elementId}
      data-motion-phase={motion.motionPhase}
      data-motion-revision={motion.motionRevision}
      data-progress-kind="quantitative"
      onAnimationEnd={motion.onMotionAnimationEnd}
    >
      <div className="data-viz-progress__label">
        <span>{label}</span>
        <strong>
          {formatValue(value)} из {formatValue(maximum)} {unit}
        </strong>
      </div>
      <div
        aria-label={`${label}: ${formatValue(value)} из ${formatValue(maximum)} ${unit ?? ''}`.trim()}
        aria-valuemax={safeMaximum}
        aria-valuemin={0}
        aria-valuenow={clamp(value, 0, safeMaximum)}
        className="data-viz-progress__track"
        role="progressbar"
      >
        <span style={{ width: `${percent}%` }} />
        <i style={{ insetInlineStart: `${percent}%` }} />
      </div>
    </div>
  );
}

export function StepProgress({ current, labels }: { current: number; labels: readonly string[] }) {
  const motion = useSemanticMotion<HTMLOListElement>(`${current}|${labels.join('|')}`, {
    animateInitial: false,
  });
  return (
    <ol
      className="data-viz-steps"
      id={motion.elementId}
      aria-label={`Шаг ${current} из ${labels.length}`}
      data-motion-phase={motion.motionPhase}
      data-motion-revision={motion.motionRevision}
      onAnimationEnd={motion.onMotionAnimationEnd}
      style={{ gridTemplateColumns: `repeat(${labels.length}, minmax(0, 1fr))` }}
    >
      {labels.map((label, index) => {
        const step = index + 1;
        const state = step < current ? 'completed' : step === current ? 'current' : 'upcoming';
        return (
          <li
            aria-current={state === 'current' ? 'step' : undefined}
            data-state={state}
            key={label}
          >
            <span>{step < current ? <Icon name="check" size={16} /> : step}</span>
            <small>{label}</small>
          </li>
        );
      })}
    </ol>
  );
}

export interface RankedBarItem {
  label: string;
  unit?: string;
  value: number;
}

export function RankedBars({ items, label }: { items: readonly RankedBarItem[]; label: string }) {
  const maximum = Math.max(...items.map((item) => item.value), 1);
  const motion = useSemanticMotion<HTMLDivElement>(
    `${label}|${items.map((item) => `${item.label}:${item.value}`).join('|')}`,
    { observe: true },
  );
  return (
    <div
      aria-label={label}
      className="data-viz-ranked-bars"
      id={motion.elementId}
      data-motion-phase={motion.motionPhase}
      data-motion-revision={motion.motionRevision}
      onAnimationEnd={motion.onMotionAnimationEnd}
      role="list"
    >
      {items.map((item, index) => (
        <div className="data-viz-ranked-bars__row" key={item.label} role="listitem">
          <span>{item.label}</span>
          <div aria-hidden="true">
            <i
              style={
                {
                  width: `${clamp((item.value / maximum) * 100, 0, 100)}%`,
                  '--data-viz-stagger-index': Math.min(index, 8),
                } as CSSProperties
              }
            />
          </div>
          <strong>
            {formatValue(item.value)} {item.unit}
          </strong>
        </div>
      ))}
    </div>
  );
}
