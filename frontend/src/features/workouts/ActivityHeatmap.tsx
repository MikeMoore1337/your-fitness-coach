import { useId, useRef, useState, type KeyboardEvent } from 'react';
import { Button, DisclosureIcon } from '../../shared/ui/common';
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
  const scope = data.days[0]?.date ?? '';
  const initialDay = data.days.filter((day) => !day.is_future).at(-1);
  const [selection, setSelection] = useState({
    scope,
    date: initialDay?.date ?? '',
    month: '',
    focused: '',
  });
  const selectedDay =
    (selection.scope === scope &&
      data.days.find((day) => day.date === selection.date && !day.is_future)) ||
    initialDay;
  const openMonth = selection.scope === scope ? selection.month : '';
  const monthButtons = useRef(new Map<string, HTMLButtonElement>());
  const calendar = useRef<HTMLDivElement>(null);
  function closeMonth() {
    setSelection({ scope, date: selectedDay?.date ?? '', month: '', focused: '' });
    monthButtons.current.get(openMonth)?.focus();
  }
  function openCalendar(month: string) {
    const first = data.days.find((day) => day.date.startsWith(month) && !day.is_future);
    const focused = selectedDay?.date.startsWith(month) ? selectedDay.date : (first?.date ?? '');
    setSelection({ scope, date: selectedDay?.date ?? '', month, focused });
    requestAnimationFrame(() => {
      const target = calendar.current?.querySelector<HTMLButtonElement>(
        `button[data-date="${focused}"]`,
      );
      (target ?? calendar.current)?.focus();
    });
  }
  function moveDay(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeMonth();
      return;
    }
    if (!(event.target instanceof HTMLButtonElement) || !event.target.dataset.date) return;
    const buttons = Array.from(
      calendar.current?.querySelectorAll<HTMLButtonElement>('button[data-date]:not(:disabled)') ??
        [],
    );
    const index = buttons.indexOf(event.target);
    const weekday = (new Date(`${event.target.dataset.date}T00:00:00Z`).getUTCDay() + 6) % 7;
    const offsets: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -7,
      ArrowDown: 7,
      Home: -weekday,
      End: 6 - weekday,
    };
    const offset = offsets[event.key];
    if (offset === undefined) return;
    event.preventDefault();
    buttons[Math.max(0, Math.min(buttons.length - 1, index + offset))]?.focus();
  }
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
      <h2 id={`${id}-title`}>{year ? `Активность за ${year} год` : 'Активность за 365 дней'}</h2>
      {year && onYearChange && (
        <label>
          Год
          <select
            aria-label="Год"
            value={year}
            onChange={(event) => onYearChange(Number(event.target.value))}
          >
            {Array.from(
              { length: new Date().getFullYear() - 1969 },
              (_, index) => new Date().getFullYear() - index,
            ).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
      )}
      <p>Часовой пояс: {data.timezone}</p>
      {data.days[0] && data.days.at(-1) && (
        <p>
          {dateLabel(data.days[0].date)} — {dateLabel(data.days.at(-1)!.date)}
        </p>
      )}
      {!data.history_complete && (
        <p>
          История неполная. Без подтверждённой даты: {data.undated_workouts}. Известные значения
          могут быть неполными.
        </p>
      )}
      {data.history_complete &&
        data.days.length > 0 &&
        data.days.every((day) => day.completed_workouts === 0 || day.is_future) && (
          <p>За этот период нет завершённых тренировок.</p>
        )}
      <p>Будущие дни не содержат данных об активности.</p>
      <div className="activity-heatmap__groups activity-heatmap__groups--months">
        {groups.map((group, index) => (
          <div className="activity-heatmap__group" key={group?.[0]?.date ?? index}>
            <button
              type="button"
              className="activity-heatmap__month-button"
              ref={(node) => {
                const month = group[0]?.date.slice(0, 7);
                if (month) {
                  if (node) monthButtons.current.set(month, node);
                  else monthButtons.current.delete(month);
                }
              }}
              aria-expanded={openMonth === group[0]?.date.slice(0, 7)}
              aria-controls={
                openMonth === group[0]?.date.slice(0, 7) ? `${id}-calendar` : undefined
              }
              onClick={() => group[0] && openCalendar(group[0].date.slice(0, 7))}
            >
              <span>{group[0] && monthLabel(group[0].date, Boolean(year))}</span>
              <span className="activity-heatmap__grid" aria-hidden="true">
                {Array.from(
                  {
                    length: group?.[0]
                      ? (new Date(`${group[0].date}T00:00:00Z`).getUTCDay() + 6) % 7
                      : 0,
                  },
                  (_, index) => (
                    <span key={`padding-${index}`} />
                  ),
                )}
                {group?.map((day) => (
                  <span
                    key={day.date}
                    className="activity-heatmap__cell"
                    data-level={
                      day.is_future
                        ? 'future'
                        : day.completed_workouts === null
                          ? 'unknown'
                          : Math.min(day.completed_workouts, 3)
                    }
                  />
                ))}
              </span>
            </button>
          </div>
        ))}
      </div>
      {openMonth && (
        <div
          id={`${id}-calendar`}
          ref={calendar}
          tabIndex={-1}
          className="activity-heatmap__calendar"
          role="region"
          aria-label={`Выбор дня: ${monthLabel(`${openMonth}-01`, Boolean(year))}`}
          onKeyDown={moveDay}
        >
          <h3>{monthLabel(`${openMonth}-01`, Boolean(year))}</h3>
          <p>Стрелки — переход по дням. Выбор — клавишей ввода, сворачивание — клавишей отмены.</p>
          <div className="activity-heatmap__days">
            {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((day) => (
              <span key={day} aria-hidden="true">
                {day}
              </span>
            ))}
            {Array.from(
              { length: (new Date(`${openMonth}-01T00:00:00Z`).getUTCDay() + 6) % 7 },
              (_, index) => (
                <span key={`empty-${index}`} />
              ),
            )}
            {data.days
              .filter((day) => day.date.startsWith(openMonth))
              .map((day) => (
                <button
                  key={day.date}
                  data-date={day.date}
                  type="button"
                  data-yfc-choice="compact"
                  disabled={day.is_future}
                  aria-pressed={selectedDay?.date === day.date}
                  aria-label={`${dateLabel(day.date)}: ${day.is_future ? 'будущий день' : `тренировки — ${valueLabel(day.completed_workouts)}, рабочие подходы — ${valueLabel(day.working_sets)}`}`}
                  tabIndex={selection.focused === day.date ? 0 : -1}
                  onFocus={() => setSelection((current) => ({ ...current, focused: day.date }))}
                  onClick={() =>
                    setSelection({ scope, date: day.date, month: openMonth, focused: day.date })
                  }
                >
                  {Number(day.date.slice(-2))}
                </button>
              ))}
          </div>
          <Button type="button" variant="secondary" onClick={closeMonth}>
            Свернуть месяц
          </Button>
        </div>
      )}
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
