import {
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from 'react';
import { DisclosureIcon, IconButton } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import './ActivityHeatmap.css';

export type ActivityDay = {
  date: string;
  is_future?: boolean;
  completed_workouts: number | null;
  working_sets: number | null;
};

export type ActivityHeatmapData = {
  timezone: string;
  history_complete: boolean;
  undated_workouts: number;
  days: ActivityDay[];
};

function dateLabel(value: string) {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'long', timeZone: 'UTC' }).format(
    new Date(`${value}T00:00:00Z`),
  );
}

function monthLabel(value: string, calendarYear: boolean) {
  return new Intl.DateTimeFormat('ru-RU', {
    month: 'long',
    year: calendarYear ? undefined : 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T00:00:00Z`));
}

function valueLabel(value: number | null) {
  return value === null ? 'Нет данных' : String(value);
}

function MobileActivityCalendar({
  groups,
  timezone,
  selected,
  onSelect,
}: {
  groups: ActivityDay[][];
  timezone: string;
  selected?: string;
  onSelect: (date: string) => void;
}) {
  const today = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    timeZone: timezone,
  }).formatToParts(new Date());
  const currentMonth = `${today.find((part) => part.type === 'year')?.value}-${today.find((part) => part.type === 'month')?.value}`;
  const initial = Math.max(
    0,
    groups.findIndex((group) => group[0]?.date.startsWith(currentMonth)),
  );
  const [visible, setVisible] = useState(initial);
  const viewport = useRef<HTMLDivElement>(null);
  const visibleRef = useRef(initial);
  const id = useId();
  useLayoutEffect(() => {
    const node = viewport.current;
    if (!node) return;
    const resize = new ResizeObserver(() => {
      if (node.clientWidth)
        node.scrollTo({ left: visibleRef.current * node.clientWidth, behavior: 'instant' });
    });
    node.scrollTo({ left: initial * node.clientWidth, behavior: 'instant' });
    resize.observe(node);
    return () => resize.disconnect();
  }, [initial]);
  function navigate(index: number) {
    const node = viewport.current;
    if (!node) return;
    node.scrollTo({
      left: Math.max(0, Math.min(groups.length - 1, index)) * node.clientWidth,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'instant'
        : 'smooth',
    });
  }
  function dayKeys(event: KeyboardEvent<HTMLDivElement>) {
    if (!(event.target instanceof HTMLButtonElement) || !event.target.dataset.date) return;
    const buttons = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>('button[data-date]:enabled'),
    );
    const index = buttons.indexOf(event.target);
    const weekday = (new Date(`${event.target.dataset.date}T00:00:00Z`).getUTCDay() + 6) % 7;
    const offset = (
      {
        ArrowLeft: -1,
        ArrowRight: 1,
        ArrowUp: -7,
        ArrowDown: 7,
        Home: -weekday,
        End: 6 - weekday,
      } as Record<string, number>
    )[event.key];
    if (offset === undefined) return;
    event.preventDefault();
    buttons[Math.max(0, Math.min(buttons.length - 1, index + offset))]?.focus();
  }
  return (
    <div
      className="activity-heatmap__mobile"
      role="region"
      aria-label="Календарь активности по месяцам"
      aria-roledescription="карусель"
    >
      <div className="activity-heatmap__month-nav">
        <IconButton
          aria-label="Предыдущий месяц"
          disabled={visible === 0}
          onClick={() => navigate(visible - 1)}
          aria-controls={id}
        >
          <Icon name="chevron-left" />
        </IconButton>
        <div aria-live="polite" aria-atomic="true">
          <h3>{groups[visible]?.[0] && monthLabel(groups[visible][0].date, false)}</h3>
          <span>
            {visible + 1} / {groups.length}
          </span>
        </div>
        <IconButton
          aria-label="Следующий месяц"
          disabled={visible === groups.length - 1}
          onClick={() => navigate(visible + 1)}
          aria-controls={id}
        >
          <Icon name="chevron-right" />
        </IconButton>
      </div>
      <div
        className="activity-heatmap__carousel"
        id={id}
        ref={viewport}
        onScroll={(event) => {
          const node = event.currentTarget;
          if (!node.clientWidth) return;
          const index = Math.max(
            0,
            Math.min(groups.length - 1, Math.round(node.scrollLeft / node.clientWidth)),
          );
          visibleRef.current = index;
          setVisible(index);
        }}
      >
        {groups.map((group, index) => (
          <div
            key={group[0]?.date}
            className="activity-heatmap__slide"
            inert={index !== visible}
            aria-hidden={index !== visible}
            role="group"
            aria-label={group[0] && monthLabel(group[0].date, false)}
            onKeyDown={dayKeys}
          >
            <div className="activity-heatmap__days">
              {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((day) => (
                <span key={day} aria-hidden="true">
                  {day}
                </span>
              ))}
              {Array.from(
                {
                  length: group[0]
                    ? (new Date(`${group[0].date}T00:00:00Z`).getUTCDay() + 6) % 7
                    : 0,
                },
                (_, i) => (
                  <span key={`pad-${i}`} />
                ),
              )}
              {group.map((day) => (
                <button
                  key={day.date}
                  type="button"
                  data-date={day.date}
                  data-yfc-choice="compact"
                  data-level={
                    day.is_future
                      ? 'future'
                      : day.completed_workouts === null
                        ? 'unknown'
                        : Math.min(day.completed_workouts, 3)
                  }
                  disabled={day.is_future}
                  aria-pressed={selected === day.date}
                  aria-label={`${dateLabel(day.date)}: ${day.is_future ? 'будущий день' : `тренировки — ${valueLabel(day.completed_workouts)}, рабочие подходы — ${valueLabel(day.working_sets)}`}`}
                  onClick={() => onSelect(day.date)}
                >
                  {Number(day.date.slice(-2))}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DesktopActivityCalendar({
  days,
  selected,
  onSelect,
}: {
  days: ActivityDay[];
  selected?: string;
  onSelect: (date: string) => void;
}) {
  const offset = days[0] ? (new Date(`${days[0].date}T00:00:00Z`).getUTCDay() + 6) % 7 : 0;
  const weeks = Math.ceil((offset + days.length) / 7);
  const [focused, setFocused] = useState(selected ?? days.find((day) => !day.is_future)?.date);
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);
  const root = useRef<HTMLDivElement>(null);
  function facts(day: ActivityDay) {
    return `${dateLabel(day.date)}: ${day.is_future ? 'будущий день' : `тренировки — ${valueLabel(day.completed_workouts)}, рабочие подходы — ${valueLabel(day.working_sets)}`}`;
  }
  function showTip(day: ActivityDay, element: HTMLElement) {
    const bounds = root.current?.getBoundingClientRect();
    if (!bounds) return;
    const cell = element.getBoundingClientRect();
    setTip({
      text: facts(day),
      x: Math.max(0, Math.min(bounds.width - 300, cell.left - bounds.left)),
      y: bounds.height - 1,
    });
  }
  function keys(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      setTip(null);
      return;
    }
    if (!(event.target instanceof HTMLButtonElement) || !event.target.dataset.date) return;
    const date = event.target.dataset.date;
    const index = days.findIndex((day) => day.date === date);
    const row = (offset + index) % 7;
    const next = (
      {
        ArrowLeft: index - 7,
        ArrowRight: index + 7,
        ArrowUp: row > 0 ? index - 1 : index,
        ArrowDown: row < 6 ? index + 1 : index,
        Home: event.ctrlKey ? 0 : (row - offset + 7) % 7,
        End: event.ctrlKey
          ? days.length - 1 - [...days].reverse().findIndex((day) => !day.is_future)
          : days.length - 1 - ((((offset + days.length - 1) % 7) - row + 7) % 7),
      } as Record<string, number>
    )[event.key];
    if (next === undefined) return;
    event.preventDefault();
    const day = days[next];
    if (day && !day.is_future)
      root.current?.querySelector<HTMLButtonElement>(`button[data-date="${day.date}"]`)?.focus();
  }
  return (
    <div className="activity-heatmap__year" ref={root} onMouseLeave={() => setTip(null)}>
      <div className="activity-heatmap__year-scroll">
        <div className="activity-heatmap__year-map" style={{ '--weeks': weeks } as CSSProperties}>
          <div className="activity-heatmap__year-months" aria-hidden="true">
            {days.map(
              (day, index) =>
                (index === 0 || day.date.slice(-2) === '01') && (
                  <span key={day.date} style={{ gridColumn: Math.floor((offset + index) / 7) + 2 }}>
                    {new Intl.DateTimeFormat('ru-RU', { month: 'short', timeZone: 'UTC' }).format(
                      new Date(`${day.date}T00:00:00Z`),
                    )}
                  </span>
                ),
            )}
          </div>
          <div
            role="grid"
            aria-label="Годовая карта активности"
            aria-rowcount={7}
            aria-colcount={weeks + 1}
            onKeyDown={keys}
          >
            {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((label, row) => (
              <div role="row" className="activity-heatmap__year-row" key={label}>
                <span role="rowheader" aria-label={label}>
                  {row % 2 === 0 ? label : ''}
                </span>
                {Array.from({ length: weeks }, (_, week) => {
                  const day = days[week * 7 + row - offset];
                  return (
                    <span
                      role="gridcell"
                      key={week}
                      onMouseEnter={day ? (event) => showTip(day, event.currentTarget) : undefined}
                    >
                      {day && (
                        <button
                          type="button"
                          className="activity-heatmap__cell"
                          data-date={day.date}
                          data-level={
                            day.is_future
                              ? 'future'
                              : day.completed_workouts === null
                                ? 'unknown'
                                : Math.min(day.completed_workouts, 3)
                          }
                          data-yfc-choice="compact"
                          aria-pressed={selected === day.date}
                          aria-label={facts(day)}
                          disabled={day.is_future}
                          tabIndex={!day.is_future && focused === day.date ? 0 : -1}
                          onFocus={(event) => {
                            setFocused(day.date);
                            showTip(day, event.currentTarget);
                          }}
                          onBlur={() => setTip(null)}
                          onClick={() => {
                            setTip(null);
                            onSelect(day.date);
                          }}
                        />
                      )}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
      {tip && (
        <div
          role="tooltip"
          className="activity-heatmap__tooltip"
          style={{ left: tip.x, top: tip.y }}
        >
          {tip.text}
        </div>
      )}
    </div>
  );
}

export function ActivityHeatmap(props: Parameters<typeof ActivityHeatmapContent>[0]) {
  return (
    <ActivityHeatmapContent key={props.year ?? props.data.days[0]?.date ?? 'calendar'} {...props} />
  );
}

function ActivityHeatmapContent({
  data,
  year,
  onYearChange,
}: {
  data: ActivityHeatmapData;
  year?: number;
  onYearChange?: (year: number) => void;
}) {
  const id = useId();
  const initialDay = data.days.filter((day) => !day.is_future).at(-1);
  const [selection, setSelection] = useState(initialDay?.date ?? '');
  const selectedDay =
    data.days.find((day) => day.date === selection && !day.is_future) || initialDay;
  const groups: ActivityDay[][] = [];
  for (const day of data.days) {
    const last = groups.at(-1);
    if (!last || last[0]?.date.slice(0, 7) !== day.date.slice(0, 7)) {
      groups.push([day]);
    } else {
      last.push(day);
    }
  }

  return (
    <section className="activity-heatmap" aria-labelledby={`${id}-title`}>
      <div className="activity-heatmap__header">
        <h2 id={`${id}-title`}>
          Активность
          <span className="activity-heatmap__mobile-only">
            {year ? ` за ${year} год` : ' за 365 дней'}
          </span>
        </h2>
        {year && onYearChange && (
          <label>
            Год
            <select
              aria-label="Год"
              value={year}
              onChange={(event) => onYearChange(Number(event.target.value))}
            >
              {Array.from(
                { length: Math.max(new Date().getFullYear(), year) - 1969 },
                (_, index) => Math.max(new Date().getFullYear(), year) - index,
              ).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <p className="activity-heatmap__timezone">Часовой пояс: {data.timezone}</p>
      {data.days[0] && data.days.at(-1) && (
        <p className="activity-heatmap__mobile-only">
          {dateLabel(data.days[0].date)} — {dateLabel(data.days.at(-1)!.date)}
        </p>
      )}
      {!data.history_complete && (
        <details className="activity-heatmap__desktop activity-heatmap__history">
          <summary className="yfc-disclosure-summary">
            История неполная <DisclosureIcon />
          </summary>
          <p>
            Без подтверждённой даты: {data.undated_workouts}. Известные значения могут быть
            неполными. Отсутствие данных не означает нулевую активность.
          </p>
        </details>
      )}
      {!data.history_complete && (
        <p className="activity-heatmap__mobile-only">
          История неполная. Без подтверждённой даты: {data.undated_workouts}. Известные значения
          могут быть неполными.
        </p>
      )}
      {data.history_complete &&
        data.days.length > 0 &&
        data.days.every((day) => day.completed_workouts === 0 || day.is_future) && (
          <p>За этот период нет завершённых тренировок.</p>
        )}
      <p className="activity-heatmap__mobile-only">Будущие дни не содержат данных об активности.</p>
      {groups.length > 0 && (
        <MobileActivityCalendar
          groups={groups}
          timezone={data.timezone}
          selected={selectedDay?.date}
          onSelect={setSelection}
        />
      )}
      <div className="activity-heatmap__desktop">
        {data.days.length > 0 && (
          <DesktopActivityCalendar
            days={data.days}
            selected={selectedDay?.date}
            onSelect={setSelection}
          />
        )}
      </div>
      <div className="activity-heatmap__legend" aria-label="Легенда: количество тренировок">
        {[
          ['unknown', 'Нет данных'],
          ['future', 'Будущий день'],
          ['0', '0'],
          ['1', '1'],
          ['2', '2'],
          ['3', '3 и более'],
        ].map(([level, label]) => (
          <span key={level} className="activity-heatmap__legend-item">
            <span className="activity-heatmap__cell" data-level={level} aria-hidden="true" />
            {label}
          </span>
        ))}
      </div>
      {data.days.length === 0 ? (
        <p>Данных об активности пока нет.</p>
      ) : (
        <>
          {selectedDay && (
            <p aria-live="polite">
              {selectedDay.is_future
                ? `${dateLabel(selectedDay.date)}: этот день ещё не наступил.`
                : `${dateLabel(selectedDay.date)}: тренировки — ${valueLabel(selectedDay.completed_workouts)}, рабочие подходы — ${valueLabel(selectedDay.working_sets)}.`}
            </p>
          )}
          <details>
            <summary className="yfc-disclosure-summary">
              Данные по дням <DisclosureIcon />
            </summary>
            <table>
              <thead>
                <tr>
                  <th scope="col">Дата</th>
                  <th scope="col">Тренировки</th>
                  <th scope="col">Рабочие подходы</th>
                </tr>
              </thead>
              <tbody>
                {data.days.map((day) => (
                  <tr key={day.date}>
                    <th scope="row">{dateLabel(day.date)}</th>
                    <td>{day.is_future ? 'Будущий день' : valueLabel(day.completed_workouts)}</td>
                    <td>{day.is_future ? 'Будущий день' : valueLabel(day.working_sets)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </section>
  );
}
