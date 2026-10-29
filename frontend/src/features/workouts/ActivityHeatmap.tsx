import { useState } from 'react';
import { DisclosureIcon } from '../../shared/ui/common';
import './ActivityHeatmap.css';

export type ActivityDay = {
  date: string;
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

function monthLabel(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T00:00:00Z`));
}

function valueLabel(value: number | null) {
  return value === null ? 'Нет данных' : String(value);
}

export function ActivityHeatmap({
  data,
  variant = 'year',
}: {
  data: ActivityHeatmapData;
  variant?: 'year' | 'months';
}) {
  const [selected, setSelected] = useState(data.days.at(-1)?.date ?? '');
  const selectedDay = data.days.find((day) => day.date === selected) ?? data.days.at(-1);
  const showMonths = variant === 'months';
  const groups: ActivityDay[][] = [];
  for (const day of data.days) {
    const last = groups.at(-1);
    if (!last || (variant === 'months' && last[0]?.date.slice(0, 7) !== day.date.slice(0, 7))) {
      groups.push([day]);
    } else {
      last.push(day);
    }
  }

  return (
    <section className="activity-heatmap" aria-labelledby="activity-heatmap-title">
      <h2 id="activity-heatmap-title">Активность за 365 дней</h2>
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
        data.days.every((day) => day.completed_workouts === 0) && (
          <p>За этот период нет завершённых тренировок.</p>
        )}
      <div
        className={`activity-heatmap__groups activity-heatmap__groups--${variant}`}
        aria-hidden="true"
      >
        {groups.map((group, index) => (
          <div className="activity-heatmap__group" key={group?.[0]?.date ?? index}>
            {showMonths && group?.[0] && <span>{monthLabel(group[0].date)}</span>}
            <div className="activity-heatmap__grid">
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
                    day.completed_workouts === null
                      ? 'unknown'
                      : Math.min(day.completed_workouts, 3)
                  }
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="activity-heatmap__legend" aria-label="Легенда: количество тренировок">
        {[
          ['unknown', 'Нет данных'],
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
          <label>
            Выберите день
            <select
              value={selectedDay?.date ?? ''}
              onChange={(event) => setSelected(event.target.value)}
            >
              {data.days.map((day) => (
                <option key={day.date} value={day.date}>
                  {dateLabel(day.date)}
                </option>
              ))}
            </select>
          </label>
          {selectedDay && (
            <p aria-live="polite">
              {dateLabel(selectedDay.date)}: тренировки —{' '}
              {valueLabel(selectedDay.completed_workouts)}, рабочие подходы —{' '}
              {valueLabel(selectedDay.working_sets)}.
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
                    <td>{valueLabel(day.completed_workouts)}</td>
                    <td>{valueLabel(day.working_sets)}</td>
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
