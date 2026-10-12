import { useEffect, useId, useRef, type ReactNode } from 'react';
import { addCalendarDays, calendarWeek, formatCalendarDate } from '../dateTime';
import { AppLink } from '../navigation/router';
import { ChevronIcon } from './common';
import { Icon, type IconName } from './Icon';

export type WeekStripStatusKey =
  'completed' | 'in-progress' | 'planned' | 'upcoming' | 'skipped' | 'neutral';

export type WeekStripActivityKey = 'strength' | 'cardio' | 'rest';

export type WeekStripPictogramKey =
  | WeekStripActivityKey
  | 'completed'
  | 'planned'
  | 'in-progress'
  | 'skipped'
  | 'nutrition-incomplete'
  | 'fasted'
  | 'missing';

export interface WeekStripStatus {
  key: WeekStripStatusKey;
  label: string;
  pictogram?: WeekStripPictogramKey;
}

export interface WeekStripActivity {
  key: WeekStripActivityKey;
  label: string;
}

export interface WeekStripLegendItem {
  key: string;
  label: string;
  pictogram: WeekStripPictogramKey;
  tone: WeekStripActivityKey | WeekStripStatusKey;
}

export const TRAINING_WEEK_LEGEND: ReadonlyArray<WeekStripLegendItem> = [
  { key: 'strength', label: 'Силовая', pictogram: 'strength', tone: 'strength' },
  { key: 'cardio', label: 'Кардио', pictogram: 'cardio', tone: 'cardio' },
  { key: 'rest', label: 'Отдых', pictogram: 'rest', tone: 'rest' },
  { key: 'completed', label: 'Выполнено', pictogram: 'completed', tone: 'completed' },
  { key: 'planned', label: 'Запланировано', pictogram: 'planned', tone: 'planned' },
  { key: 'in-progress', label: 'В процессе', pictogram: 'in-progress', tone: 'in-progress' },
  { key: 'skipped', label: 'Пропущено', pictogram: 'skipped', tone: 'skipped' },
];

export const NUTRITION_WEEK_LEGEND: ReadonlyArray<WeekStripLegendItem> = [
  { key: 'completed', label: 'День заполнен', pictogram: 'completed', tone: 'completed' },
  {
    key: 'incomplete',
    label: 'Не завершён',
    pictogram: 'nutrition-incomplete',
    tone: 'in-progress',
  },
  { key: 'fasted', label: 'Без приёмов пищи', pictogram: 'fasted', tone: 'neutral' },
  { key: 'missing', label: 'Нет данных', pictogram: 'missing', tone: 'neutral' },
];

function WeekStripPictogram({
  kind,
  tone,
}: {
  kind: WeekStripPictogramKey;
  tone: WeekStripActivityKey | WeekStripStatusKey;
}) {
  const iconName: Record<WeekStripPictogramKey, IconName> = {
    strength: 'week-strength',
    cardio: 'week-cardio',
    rest: 'week-rest',
    completed: 'week-completed',
    planned: 'week-planned',
    'in-progress': 'week-in-progress',
    skipped: 'week-skipped',
    'nutrition-incomplete': 'week-nutrition-incomplete',
    fasted: 'week-nutrition-fasted',
    missing: 'week-nutrition-missing',
  };

  return (
    <span
      aria-hidden="true"
      className={`week-strip__pictogram week-strip__pictogram--${tone}`}
      data-pictogram={kind}
    >
      <Icon className="week-strip__pictogram-svg" name={iconName[kind]} size={16} />
    </span>
  );
}

function statusPictogram(status: WeekStripStatus | null | undefined): WeekStripPictogramKey | null {
  if (!status) return null;
  if (status.pictogram) return status.pictogram;
  if (status.key === 'upcoming') return 'planned';
  if (status.key === 'neutral') return null;
  return status.key;
}

export interface WeekStripDayMeta {
  activities?: ReadonlyArray<WeekStripActivity>;
  link?: {
    label: string;
    onClick?: () => void;
    to: string;
  };
  status?: WeekStripStatus | null;
}

interface WeekStripNavigation {
  nextDisabled?: boolean;
  onNext(): void;
  onPrevious(): void;
}

interface WeekStripCommonProps {
  anchorDate: string;
  ariaLabel: string;
  headerAction?: ReactNode;
  loading?: boolean;
  loadingLabel?: string;
  legend?: ReadonlyArray<WeekStripLegendItem>;
  navigation?: WeekStripNavigation;
  title: string;
  today: string;
  /** Optional exact first day for rolling seven-day report contexts. */
  rangeStart?: string;
}

type WeekStripProps = WeekStripCommonProps &
  (
    | {
        getDayMeta?: (date: string) => WeekStripDayMeta;
        mode: 'overview';
        isDateDisabled?: never;
        onSelect?: never;
        selectedDate?: never;
      }
    | {
        getDayMeta?: (date: string) => WeekStripDayMeta;
        isDateDisabled?: (date: string) => boolean;
        mode: 'picker';
        onSelect(date: string): void;
        selectedDate: string;
      }
  );

export function formatWeekRange(days: string[]): string {
  const first = days[0];
  const last = days.at(-1);
  if (!first || !last) return '';

  const sameMonth = first.slice(0, 7) === last.slice(0, 7);
  const sameYear = first.slice(0, 4) === last.slice(0, 4);
  const firstLabel = formatCalendarDate(first, {
    day: 'numeric',
    ...(sameMonth ? {} : { month: 'short' }),
    ...(sameYear ? {} : { year: 'numeric' }),
  });
  const lastLabel = formatCalendarDate(last, {
    day: 'numeric',
    month: 'short',
    ...(sameYear ? {} : { year: 'numeric' }),
  });
  return `${firstLabel} — ${lastLabel}`;
}

export function WeekStrip(props: WeekStripProps) {
  const headingId = useId();
  const daysRef = useRef<HTMLOListElement>(null);
  const days = props.rangeStart
    ? Array.from({ length: 7 }, (_, index) => addCalendarDays(props.rangeStart!, index))
    : calendarWeek(props.anchorDate);
  const isPicker = props.mode === 'picker';
  const Root = isPicker ? 'nav' : 'section';
  const selectedDate = isPicker ? props.selectedDate : undefined;

  useEffect(() => {
    const rail = daysRef.current;
    if (!rail || !selectedDate) return;
    const revealSelected = () => {
      const selected = rail.querySelector('[aria-pressed="true"]');
      if (!selected) return;
      const bounds = rail.getBoundingClientRect();
      const item = selected.getBoundingClientRect();
      if (item.right > bounds.right - 4) rail.scrollLeft += item.right - bounds.right + 4;
      else if (item.left < bounds.left + 4) rail.scrollLeft += item.left - bounds.left - 4;
    };
    revealSelected();
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(revealSelected);
    observer?.observe(rail);
    return () => observer?.disconnect();
  }, [selectedDate]);

  return (
    <Root
      aria-busy={props.loading || undefined}
      aria-label={isPicker ? props.ariaLabel : undefined}
      aria-labelledby={isPicker ? undefined : headingId}
      className={`week-strip week-strip--${props.mode}`}
    >
      <div className="week-strip__topline">
        <div
          className={`week-strip__head week-strip__head--${props.navigation ? 'navigation' : 'static'}`}
        >
          {props.navigation && (
            <button
              aria-label="Предыдущая неделя"
              className="week-strip__nav week-strip__nav--previous"
              onClick={props.navigation.onPrevious}
              type="button"
            >
              <ChevronIcon direction="left" />
              <span>Неделя</span>
            </button>
          )}

          <div className="week-strip__context">
            <h2 id={headingId}>{props.title}</h2>
            <span>{formatWeekRange(days)}</span>
          </div>

          {props.navigation ? (
            <button
              aria-label="Следующая неделя"
              className="week-strip__nav week-strip__nav--next"
              disabled={props.navigation.nextDisabled}
              onClick={props.navigation.onNext}
              type="button"
            >
              <span>Неделя</span>
              <ChevronIcon direction="right" />
            </button>
          ) : (
            props.headerAction && (
              <div className="week-strip__header-action">{props.headerAction}</div>
            )
          )}
        </div>
      </div>

      <ol className="week-strip__days" ref={daysRef}>
        {days.map((date) => {
          const isToday = date === props.today;
          const isSelected = isPicker && date === props.selectedDate;
          const dayMeta = props.getDayMeta?.(date);
          const status = dayMeta?.status;
          const statusIcon = statusPictogram(status);
          const activityLabel = dayMeta?.activities?.map((activity) => activity.label).join(' и ');
          const label = [
            formatCalendarDate(date, { weekday: 'long', day: 'numeric', month: 'long' }),
            isToday ? 'сегодня' : null,
            isSelected ? 'выбрано' : null,
            activityLabel,
            status?.label,
            dayMeta?.link?.label,
          ]
            .filter(Boolean)
            .join(', ');
          const content = (
            <>
              <span className="week-strip__weekday">
                {formatCalendarDate(date, { weekday: 'short' }).replace('.', '')}
              </span>
              <strong>{formatCalendarDate(date, { day: 'numeric' })}</strong>
              <span aria-hidden="true" className="week-strip__markers">
                {dayMeta?.activities?.map((activity) => (
                  <WeekStripPictogram kind={activity.key} key={activity.key} tone={activity.key} />
                ))}
                {statusIcon && (
                  <WeekStripPictogram kind={statusIcon} tone={status?.key ?? 'neutral'} />
                )}
              </span>
            </>
          );
          const dayClassName = `week-strip__day${isPicker || dayMeta?.link ? ' week-strip__day--interactive' : ''}`;

          return (
            <li key={date}>
              {isPicker ? (
                <button
                  aria-current={isToday ? 'date' : undefined}
                  aria-label={label}
                  aria-pressed={isSelected}
                  data-yfc-choice="compact"
                  className={dayClassName}
                  disabled={props.isDateDisabled?.(date)}
                  onClick={() => props.onSelect(date)}
                  type="button"
                >
                  {content}
                </button>
              ) : dayMeta?.link ? (
                <AppLink
                  aria-current={isToday ? 'date' : undefined}
                  aria-label={label}
                  className={dayClassName}
                  onClick={dayMeta.link.onClick}
                  to={dayMeta.link.to}
                >
                  {content}
                </AppLink>
              ) : (
                <div
                  aria-current={isToday ? 'date' : undefined}
                  aria-label={label}
                  className={dayClassName}
                  role="group"
                >
                  {content}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {props.legend && props.legend.length > 0 && (
        <details className="week-strip__legend-disclosure">
          <summary className="week-strip__legend-summary">
            <span className="week-strip__legend-summary-label">
              <Icon aria-hidden="true" className="week-strip__legend-info" name="info" size={20} />
              <span>Обозначения</span>
            </span>
            <Icon
              aria-hidden="true"
              className="week-strip__legend-chevron"
              name="chevron-down"
              size={16}
            />
          </summary>
          <ul aria-label="Обозначения недели" className="week-strip__legend">
            {props.legend.map((item) => (
              <li key={item.key}>
                <WeekStripPictogram kind={item.pictogram} tone={item.tone} />
                <span>{item.label}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {props.loading && (
        <span className="sr-only" role="status">
          {props.loadingLabel ?? 'Загружаем данные недели'}
        </span>
      )}
    </Root>
  );
}
