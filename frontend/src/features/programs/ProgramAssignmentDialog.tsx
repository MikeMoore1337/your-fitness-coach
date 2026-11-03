import { useState } from 'react';
import { createPortal } from 'react-dom';
import type { ProgramTemplate } from '../../shared/api/types';
import { addCalendarDays, formatCalendarDate } from '../../shared/dateTime';
import { DateInput } from '../../shared/ui/PickerInput';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { programWeeklySessions, templateWeekCycle } from './programPreviewFacts';
import './program-assignment.css';

export interface AssignmentPlan {
  title: string;
  days: { title: string }[];
  defaultDurationWeeks: number;
  frequency: number;
  cycle: { length_weeks: number; repeat: boolean } | null;
}

export interface AssignmentSchedule {
  start_date: string;
  duration_weeks: number;
  schedule_weekdays: number[] | null;
}

export function assignmentPlanFromTemplate(template: ProgramTemplate): AssignmentPlan {
  return {
    title: template.title,
    days: template.days,
    defaultDurationWeeks: template.default_duration_weeks,
    frequency: programWeeklySessions(template),
    cycle: templateWeekCycle(template),
  };
}

const weekdayLabels = [
  'Понедельник',
  'Вторник',
  'Среда',
  'Четверг',
  'Пятница',
  'Суббота',
  'Воскресенье',
];

function weekdayFromDate(value: string): number {
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.valueOf()) ? 0 : (date.getUTCDay() + 6) % 7;
}

export function assignmentFirstDate(schedule: AssignmentSchedule): string {
  const first = schedule.schedule_weekdays?.[0];
  return first == null
    ? schedule.start_date
    : addCalendarDays(schedule.start_date, (first - weekdayFromDate(schedule.start_date) + 7) % 7);
}

function defaultWeekdays(plan: AssignmentPlan, startDate: string): number[] {
  if (plan.frequency > 7) return [];
  const first = weekdayFromDate(startDate);
  return Array.from(
    { length: plan.frequency },
    (_, index) =>
      (first +
        (plan.frequency === plan.days.length ? index : Math.floor((index * 7) / plan.frequency))) %
      7,
  );
}

export function ProgramAssignmentDialog({
  plan,
  defaultStartDate,
  busy,
  submitLabel = 'Назначить по расписанию',
  backLabel,
  concealed = false,
  onClose,
  onSubmit,
}: {
  plan: AssignmentPlan;
  defaultStartDate: string;
  busy: boolean;
  submitLabel?: string;
  backLabel?: string;
  concealed?: boolean;
  onClose: () => void;
  onSubmit: (schedule: AssignmentSchedule) => void;
}) {
  const [startDate, setStartDate] = useState(defaultStartDate);
  const [duration, setDuration] = useState(
    plan.cycle || plan.defaultDurationWeeks > 1 ? plan.defaultDurationWeeks : 4,
  );
  const [weekdays, setWeekdays] = useState(() => defaultWeekdays(plan, defaultStartDate));
  const panelRef = useModalA11y<HTMLDivElement>(true, () => {
    if (!busy) onClose();
  });
  const max = plan.cycle
    ? plan.cycle.repeat
      ? undefined
      : plan.cycle.length_weeks
    : plan.defaultDurationWeeks > 1
      ? plan.defaultDurationWeeks
      : 24;
  const offsets = weekdays.map((weekday) => (weekday - (weekdays[0] ?? weekday) + 7) % 7);
  const valid =
    plan.days.length > 7
      ? weekdays.length === 0
      : weekdays.length === plan.frequency &&
        new Set(weekdays).size === weekdays.length &&
        offsets.every((offset, index) => index === 0 || offset > offsets[index - 1]!);
  const previewWeeks =
    plan.cycle && Number.isSafeInteger(duration) && duration > 0
      ? [...new Set([1, Math.ceil(duration / 2), duration])]
      : [];
  const validDate =
    /^\d{4}-\d{2}-\d{2}$/.test(startDate) &&
    !Number.isNaN(new Date(`${startDate}T12:00:00Z`).valueOf());
  const firstDate = validDate
    ? assignmentFirstDate({
        start_date: startDate,
        duration_weeks: duration,
        schedule_weekdays: weekdays,
      })
    : startDate;

  return createPortal(
    <div
      className="app-section--design-v2 modal program-assignment-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="assign-program-title"
      aria-hidden={concealed || undefined}
      inert={concealed || undefined}
      style={{ visibility: concealed ? 'hidden' : undefined }}
    >
      <button
        type="button"
        className="modal__backdrop"
        aria-label="Закрыть настройку расписания"
        disabled={busy}
        onClick={onClose}
      />
      <div className="modal__panel card assignment-modal" ref={panelRef} tabIndex={-1}>
        <div className="section-head">
          <div>
            <span className="eyebrow">Расписание программы</span>
            <h2 id="assign-program-title">{plan.title}</h2>
          </div>
          <button
            type="button"
            className="secondary"
            aria-label="Закрыть настройку расписания"
            disabled={busy}
            onClick={onClose}
          >
            Закрыть
          </button>
        </div>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            if (
              !busy &&
              valid &&
              validDate &&
              startDate >= defaultStartDate &&
              Number.isSafeInteger(duration) &&
              duration > 0 &&
              (max == null || duration <= max)
            ) {
              onSubmit({
                start_date: startDate,
                duration_weeks: duration,
                schedule_weekdays: plan.days.length > 7 ? null : weekdays,
              });
            }
          }}
        >
          <div className="form-grid">
            <label className="field">
              <span>Начать не раньше</span>
              <DateInput
                min={defaultStartDate}
                value={startDate}
                onChange={(event) => {
                  const next = event.target.value;
                  setStartDate(next);
                  setWeekdays(defaultWeekdays(plan, next));
                }}
                required
              />
            </label>
            <label className="field">
              <span>Длительность, недель</span>
              <input
                type="number"
                min="1"
                max={max}
                value={duration}
                onChange={(event) => setDuration(Number(event.target.value))}
                required
              />
            </label>
          </div>
          {plan.cycle && (
            <p className="assignment-preview">
              Исходных недель: {plan.cycle.length_weeks}.{' '}
              {plan.cycle.repeat
                ? 'Цикл повторяется до конца программы.'
                : 'Повтор цикла выключен.'}
            </p>
          )}
          {!plan.cycle && plan.defaultDurationWeeks > 1 && (
            <p className="assignment-preview">
              Для этого шаблона доступны назначения на {plan.defaultDurationWeeks} недель с
              сохранённой схемой повторений.
            </p>
          )}
          {plan.days.length > 7 ? (
            <p className="assignment-preview">
              Восьмидневный цикл планируется последовательно: одна тренировка за другой, начиная с
              выбранной даты.
            </p>
          ) : (
            <div className="form-grid">
              {weekdays.map((weekday, index) => (
                <label className="field" key={index}>
                  <span>
                    {plan.frequency === plan.days.length
                      ? plan.days[index]?.title || `День ${index + 1}`
                      : `Занятие ${index + 1}`}
                  </span>
                  <select
                    value={weekday}
                    onChange={(event) =>
                      setWeekdays(
                        weekdays.map((value, position) =>
                          position === index ? Number(event.target.value) : value,
                        ),
                      )
                    }
                  >
                    {weekdayLabels.map((label, value) => (
                      <option value={value} key={label}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          )}
          {!valid && (
            <p className="field-error" role="alert">
              Выберите разные дни недели в порядке тренировок. В одной неделе доступно до семи дней.
            </p>
          )}
          <div className="assignment-preview" aria-label="Предпросмотр назначения">
            <strong>Предпросмотр назначения</strong>
            <p>
              Первая тренировка:{' '}
              {validDate
                ? formatCalendarDate(firstDate, { day: 'numeric', month: 'long', year: 'numeric' })
                : 'не указана'}{' '}
              · {duration} недель
            </p>
            {plan.cycle &&
              previewWeeks.map((week) => (
                <p key={week}>
                  Неделя {week} — исходная{' '}
                  {plan.cycle!.repeat ? ((week - 1) % plan.cycle!.length_weeks) + 1 : week}
                </p>
              ))}
            {validDate && firstDate > defaultStartDate && (
              <p>До даты начала программа будет запланирована.</p>
            )}
          </div>
          <button
            disabled={
              busy ||
              !valid ||
              !validDate ||
              startDate < defaultStartDate ||
              duration < 1 ||
              !Number.isSafeInteger(duration) ||
              (max != null && duration > max)
            }
          >
            {busy ? 'Сохраняем…' : submitLabel}
          </button>
          {backLabel && (
            <button type="button" className="secondary" disabled={busy} onClick={onClose}>
              {backLabel}
            </button>
          )}
        </form>
      </div>
    </div>,
    document.querySelector('.app-shell') ?? document.body,
  );
}
