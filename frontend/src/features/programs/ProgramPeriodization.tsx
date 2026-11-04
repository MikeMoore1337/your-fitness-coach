import { useState } from 'react';
import type { ProgramTemplateCreate } from '../../shared/api/types';

type Cycle = NonNullable<ProgramTemplateCreate['week_cycle']>;
type WeekType = NonNullable<Cycle['week_types']>[number];
type Day = ProgramTemplateCreate['days'][number];

const typeLabels: Record<Exclude<WeekType, null>, string> = {
  light: 'Лёгкая',
  medium: 'Средняя',
  heavy: 'Тяжёлая',
};

export function ProgramPeriodization({
  cycle,
  onChange,
  duration,
  onDurationChange,
  days,
  disabled,
  showPreview = true,
  firstWeek = 1,
}: {
  cycle: Cycle | null;
  onChange: (value: Cycle | null) => void;
  duration: number;
  onDurationChange: (value: number) => void;
  days: Day[];
  disabled: boolean;
  showPreview?: boolean;
  firstWeek?: number;
}) {
  const [typePage, setTypePage] = useState(0);
  const [previewPage, setPreviewPage] = useState<number | null>(null);
  const length = cycle?.length_weeks ?? 0;
  const validLength = Number.isInteger(length) && length >= 1 && length <= 20000;
  const validDuration = Number.isSafeInteger(duration) && duration >= 1;
  const valid =
    cycle &&
    validLength &&
    validDuration &&
    duration >= firstWeek &&
    (cycle.repeat || duration - firstWeek + 1 <= length);
  const typeStart = Math.min(typePage * 10, Math.max(0, Math.ceil(length / 10) - 1) * 10);
  const previewStart = (previewPage ?? 0) * 10;

  return (
    <section
      className="program-builder-section program-periodization stack"
      aria-label="Периодизация"
    >
      <div>
        <h3>Периодизация</h3>
        <p className="muted">Необязательно. Настройте исходные недели и их повторение.</p>
      </div>
      <label className="program-periodization__choice" data-yfc-choice="compact">
        <input
          type="checkbox"
          checked={cycle !== null}
          disabled={disabled}
          onChange={(event) => {
            setPreviewPage(null);
            onChange(
              event.target.checked
                ? { schema_version: 1, length_weeks: 1, week_types: [null], repeat: false }
                : null,
            );
          }}
        />
        <span>
          <strong>Включить периодизацию</strong>
          <small>Можно оставить тип недели незаданным.</small>
        </span>
      </label>
      {cycle && (
        <>
          <div className="program-periodization__fields">
            <label className="field">
              <span>Исходных недель</span>
              <input
                type="number"
                inputMode="numeric"
                min="1"
                max="20000"
                value={length}
                disabled={disabled}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  const types = cycle.week_types ?? [];
                  onChange({
                    ...cycle,
                    length_weeks: next,
                    week_types:
                      Number.isInteger(next) && next >= 1 && next <= 20000
                        ? Array.from({ length: next }, (_, index) => types[index] ?? null)
                        : types,
                  });
                  setTypePage(0);
                  setPreviewPage(null);
                }}
                required
              />
            </label>
            <label className="field">
              <span>Всего недель</span>
              <input
                type="number"
                inputMode="numeric"
                min="1"
                value={duration}
                disabled={disabled}
                onChange={(event) => {
                  onDurationChange(Number(event.target.value));
                  setPreviewPage(null);
                }}
                required
              />
            </label>
          </div>
          <label className="program-periodization__choice" data-yfc-choice="compact">
            <input
              type="checkbox"
              checked={cycle.repeat}
              disabled={disabled}
              onChange={(event) => {
                onChange({ ...cycle, repeat: event.target.checked });
                setPreviewPage(null);
              }}
            />
            <span>
              <strong>Повторять исходный цикл</strong>
              <small>Порядок исходных недель повторяется до конца программы.</small>
            </span>
          </label>
          {!cycle.repeat && validLength && duration - firstWeek + 1 > length && (
            <p className="field-error" role="alert">
              Без повтора оставшийся срок не может быть больше исходного цикла. Уменьшите срок или
              включите повтор.
            </p>
          )}
          <div>
            <h3>Типы исходных недель</h3>
            <p className="muted">Тип не меняет нагрузку автоматически.</p>
            {validLength &&
              Array.from({ length: Math.min(10, length - typeStart) }, (_, index) => {
                const week = typeStart + index;
                return (
                  <label className="program-periodization__week" key={week}>
                    <span>Неделя {week + 1}</span>
                    <select
                      value={cycle.week_types?.[week] ?? ''}
                      disabled={disabled}
                      onChange={(event) => {
                        const types = Array.from(
                          { length },
                          (_, item) => cycle.week_types?.[item] ?? null,
                        );
                        types[week] = (event.target.value || null) as WeekType;
                        onChange({ ...cycle, week_types: types });
                      }}
                    >
                      <option value="">Не задан</option>
                      <option value="light">Лёгкая</option>
                      <option value="medium">Средняя</option>
                      <option value="heavy">Тяжёлая</option>
                    </select>
                  </label>
                );
              })}
            {length > 10 && (
              <div className="program-periodization__paging">
                <button
                  type="button"
                  className="secondary"
                  disabled={typeStart === 0}
                  onClick={() => setTypePage(Math.max(0, typePage - 1))}
                >
                  Предыдущие недели
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={typeStart + 10 >= length}
                  onClick={() => setTypePage(typePage + 1)}
                >
                  Следующие недели
                </button>
              </div>
            )}
          </div>
          {showPreview && (
            <button
              type="button"
              className="secondary"
              disabled={!valid}
              onClick={() => setPreviewPage(0)}
            >
              Посмотреть план на {duration} недель
            </button>
          )}
          {showPreview && valid && previewPage !== null && (
            <div className="program-periodization__preview">
              <h3>План на {duration} недель</h3>
              <p className="muted">
                Исходных недель: {length} · {cycle.repeat ? 'повтор включён' : 'без повтора'}
              </p>
              {Array.from({ length: Math.min(10, duration - previewStart) }, (_, index) => {
                const week = previewStart + index + 1;
                const source = (week - 1) % length;
                const type = cycle.week_types?.[source];
                return (
                  <div className="program-periodization__plan-week" key={week}>
                    <strong>
                      Неделя {week} · исходная {source + 1} · проход{' '}
                      {Math.floor((week - 1) / length) + 1}
                    </strong>
                    <p className="muted">
                      {type ? typeLabels[type] : 'Тип не задан'} ·{' '}
                      {days.map((day) => day.title).join(' · ')}
                    </p>
                  </div>
                );
              })}
              {duration > 10 && (
                <div className="program-periodization__paging">
                  <button
                    type="button"
                    className="secondary"
                    disabled={previewPage === 0}
                    onClick={() => setPreviewPage(previewPage - 1)}
                  >
                    Предыдущие недели
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    disabled={previewStart + 10 >= duration}
                    onClick={() => setPreviewPage(previewPage + 1)}
                  >
                    Следующие недели
                  </button>
                </div>
              )}
            </div>
          )}
          {disabled && (
            <p className="muted">
              В назначенной программе изменения применяются к будущим неделям через ревизию.
            </p>
          )}
        </>
      )}
    </section>
  );
}
