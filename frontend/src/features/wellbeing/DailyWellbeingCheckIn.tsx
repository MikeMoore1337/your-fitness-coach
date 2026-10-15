import { useEffect, useId, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type ApiError } from '../../shared/api/client';
import type {
  DailyWellbeingCheckIn as DailyWellbeingRecord,
  DailyWellbeingCurrent,
  DailyWellbeingSave,
} from '../../shared/api/types';
import {
  addCalendarDays,
  dateInputValue,
  detectedTimeZone,
  formatCalendarDate,
} from '../../shared/dateTime';
import { queryKeys } from '../../shared/queryKeys';
import {
  DisclosureIcon,
  Badge,
  Button,
  Card,
  ErrorState,
  Field,
  Input,
  LoadingState,
  SemanticCard,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useOnlineStatus } from '../../shared/ui/OnlineStatus';
import { DateInput } from '../../shared/ui/PickerInput';
import { useTelegramOverlayBackButton } from '../../shared/telegram/useTelegramOverlayBackButton';

const sleepOptions = [
  { value: 1, label: 'Очень плохо' },
  { value: 2, label: 'Плохо' },
  { value: 3, label: 'Обычно' },
  { value: 4, label: 'Хорошо' },
  { value: 5, label: 'Отлично' },
] as const;

const moodOptions = [
  { value: 1, label: 'Очень тяжело' },
  { value: 2, label: 'Тяжеловато' },
  { value: 3, label: 'Обычно' },
  { value: 4, label: 'Хорошо' },
  { value: 5, label: 'Отлично' },
] as const;

type WellbeingForm = {
  sleepQuality: string;
  sleepDurationHours: string;
  mood: string;
  note: string;
};

const emptyForm: WellbeingForm = {
  sleepQuality: '',
  sleepDurationHours: '',
  mood: '',
  note: '',
};

const sleepHoursPattern = /^\d+(?:[.,]\d*)?$/;

function normalizeSleepHours(value: string): string {
  return value.trim().replace(',', '.');
}

function sleepDurationError(value: string): string | null {
  const normalized = normalizeSleepHours(value);
  if (!normalized) return null;
  if (!sleepHoursPattern.test(normalized)) {
    return 'Укажите количество часов числом, например 7,5.';
  }
  const minutes = Math.round(Number(normalized) * 60);
  return Number.isFinite(minutes) && minutes >= 1 && minutes <= 1440
    ? null
    : 'Укажите длительность от 1 минуты до 24 часов.';
}

export function minutesFromSleepHours(value: string): number | null {
  if (!value.trim() || sleepDurationError(value)) return null;
  return Math.round(Number(normalizeSleepHours(value)) * 60);
}

export function hoursFromMinutes(minutes: number | null | undefined): string {
  if (minutes == null) return '';
  return String(Number((minutes / 60).toFixed(2))).replace('.', ',');
}

function formsEqual(left: WellbeingForm, right: WellbeingForm): boolean {
  const leftMinutes = minutesFromSleepHours(left.sleepDurationHours);
  const rightMinutes = minutesFromSleepHours(right.sleepDurationHours);
  return (
    left.sleepQuality === right.sleepQuality &&
    (left.sleepDurationHours === right.sleepDurationHours ||
      (leftMinutes !== null && rightMinutes !== null && leftMinutes === rightMinutes)) &&
    left.mood === right.mood &&
    left.note.trim() === right.note.trim()
  );
}

function formFromRecord(record: DailyWellbeingRecord | null | undefined): WellbeingForm {
  return {
    sleepQuality: record?.sleep_quality == null ? '' : String(record.sleep_quality),
    sleepDurationHours: hoursFromMinutes(record?.sleep_duration_minutes),
    mood: record?.mood == null ? '' : String(record.mood),
    note: record?.note ?? '',
  };
}

function selectedLabel(
  options: readonly { value: number; label: string }[],
  value: number | null | undefined,
): string {
  return options.find((option) => option.value === value)?.label ?? 'Не заполнено';
}

function numericOrNull(value: string): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : null;
}

function formatDay(value: string): string {
  return formatCalendarDate(value, { day: 'numeric', month: 'long', year: 'numeric' });
}

function formatSleepDuration(minutes: number | null | undefined): string {
  if (minutes == null) return 'не заполнено';
  const hours = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(minutes / 60);
  return `${hours} ч`;
}

function errorMessage(reason: unknown): string {
  if ((reason as ApiError)?.status === 0) {
    return 'Нет связи с сервером. Поля останутся на экране — повторите отправку после подключения.';
  }
  return reason instanceof Error
    ? reason.message
    : 'Не удалось сохранить отметку. Попробуйте ещё раз.';
}

function OptionField({
  id,
  legend,
  name,
  options,
  disabled,
  value,
  onChange,
}: {
  id: string;
  legend: string;
  name: string;
  options: readonly { value: number; label: string }[];
  disabled?: boolean;
  value: string;
  onChange(value: string): void;
}) {
  return (
    <fieldset className="daily-wellbeing__options" disabled={disabled}>
      <legend>
        {legend} <small>необязательно</small>
      </legend>
      <div className="daily-wellbeing__option-grid">
        {options.map((option) => {
          const optionId = `${id}-${option.value}`;
          return (
            <label
              className="daily-wellbeing__option"
              data-yfc-choice="compact"
              key={option.value}
              htmlFor={optionId}
            >
              <input
                checked={value === String(option.value)}
                id={optionId}
                name={name}
                onChange={(event) => onChange(event.target.value)}
                type="radio"
                value={option.value}
              />
              <span>{option.label}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function SavedWellbeingCard({ record, onEdit }: { record: DailyWellbeingRecord; onEdit(): void }) {
  return (
    <SemanticCard
      action={
        <Button onClick={onEdit} type="button" variant="secondary">
          Изменить
        </Button>
      }
      className="today-panel daily-wellbeing-card daily-wellbeing-card--saved"
      family="wellbeing"
      icon="nav-today"
      summary={
        <>
          <span>{selectedLabel(sleepOptions, record.sleep_quality)}</span>
          <span> · {formatSleepDuration(record.sleep_duration_minutes)}</span>
          <span> · настроение: {selectedLabel(moodOptions, record.mood).toLowerCase()}</span>
        </>
      }
      title="Сон и настроение"
      variant="action"
    >
      <div className="daily-wellbeing__saved-meta">
        <Badge>{formatDay(record.local_date)}</Badge>
        {record.note && <span className="muted">Заметка сохранена отдельно</span>}
      </div>
    </SemanticCard>
  );
}

function EmptyWellbeingCard({ onStart }: { onStart(): void }) {
  return (
    <SemanticCard
      action={
        <Button onClick={onStart} type="button" variant="secondary">
          Добавить отметку
        </Button>
      }
      className="today-panel daily-wellbeing-card daily-wellbeing-card--empty"
      family="wellbeing"
      icon="nav-today"
      summary="По желанию · сон, настроение или длительность за выбранный день"
      title="Сон и настроение"
      variant="action"
    />
  );
}

export function DailyWellbeingCheckIn({
  autoFocus = false,
  initialDate,
  onExit,
  timeZone,
  userId,
}: {
  autoFocus?: boolean;
  initialDate?: string;
  onExit?: () => void;
  timeZone?: string | null;
  userId: number | 'anonymous';
}) {
  const { confirm, toast } = useFeedback();
  const queryClient = useQueryClient();
  const online = useOnlineStatus();
  const cardRef = useRef<HTMLElement>(null);
  const instanceId = useId();
  const resolvedTimeZone = timeZone || detectedTimeZone();
  const defaultDate = initialDate || dateInputValue(new Date(), resolvedTimeZone);
  const [localDate, setLocalDate] = useState(defaultDate);
  const [editing, setEditing] = useState(autoFocus);
  const [noteOpen, setNoteOpen] = useState(false);
  const [draft, setDraft] = useState<WellbeingForm | null>(null);
  const [lastPayload, setLastPayload] = useState<DailyWellbeingSave | null>(null);

  const current = useQuery({
    queryKey: queryKeys.wellbeing.daily(userId, localDate),
    queryFn: () => api<DailyWellbeingCurrent>(`/api/v1/check-ins/daily?local_date=${localDate}`),
    enabled: userId !== 'anonymous' && Boolean(localDate),
  });
  const record = current.data?.record;
  const form = draft ?? formFromRecord(record);

  useEffect(() => {
    if (!autoFocus || current.isLoading || current.error) return;
    const details = cardRef.current?.closest('details');
    const summary = details?.querySelector<HTMLElement>('summary');
    summary?.focus({ preventScroll: true });
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    const scrollTarget = details ?? cardRef.current;
    scrollTarget?.scrollIntoView?.({
      behavior: reduceMotion ? 'auto' : 'smooth',
      block: 'start',
    });
  }, [autoFocus, current.error, current.isLoading]);

  const save = useMutation({
    mutationFn: ({ date, payload }: { date: string; payload: DailyWellbeingSave }) =>
      api<DailyWellbeingRecord>(`/api/v1/check-ins/daily/${date}`, {
        method: 'PUT',
        body: payload,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['daily-wellbeing'] }),
        queryClient.invalidateQueries({ queryKey: ['progress-report'] }),
      ]);
      setEditing(false);
      setLastPayload(null);
      toast('Отметка сохранена');
    },
  });
  const remove = useMutation({
    mutationFn: (date: string) =>
      api<void>(`/api/v1/check-ins/daily/${date}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['daily-wellbeing'] }),
        queryClient.invalidateQueries({ queryKey: ['progress-report'] }),
      ]);
      setDraft(emptyForm);
      setEditing(true);
      setNoteOpen(false);
      toast('Отметка удалена');
    },
  });

  const today = current.data?.today || dateInputValue(new Date(), resolvedTimeZone);
  const isDateAllowed = localDate <= today;
  const durationError = sleepDurationError(form.sleepDurationHours);
  const isEmpty = !form.sleepQuality && !form.sleepDurationHours && !form.mood;
  const isDirty = !formsEqual(form, record ? formFromRecord(record) : emptyForm);
  const saveError = save.error ? errorMessage(save.error) : null;
  const removeError = remove.error ? errorMessage(remove.error) : null;

  const leaveForm = async () => {
    if (save.isPending || remove.isPending) return;
    if (
      isDirty &&
      !(await confirm({
        title: 'Выйти без сохранения?',
        message: 'Введённые данные будут потеряны. Можно остаться и сохранить отметку.',
        confirmText: 'Выйти',
      }))
    ) {
      return;
    }
    setDraft(null);
    setNoteOpen(false);
    setLastPayload(null);
    save.reset();
    remove.reset();
    if (onExit) {
      onExit();
      return;
    }
    setEditing(false);
  };
  useTelegramOverlayBackButton(Boolean(onExit) && editing, () => void leaveForm());

  if (!current.isLoading && !current.error && !record && !editing && !autoFocus) {
    return <EmptyWellbeingCard onStart={() => setEditing(true)} />;
  }
  if (current.isLoading && !record) {
    return (
      <section className="daily-wellbeing-card daily-wellbeing-card--state" ref={cardRef}>
        <LoadingState label="Загружаем отметку…" />
      </section>
    );
  }
  if (current.error && !record) {
    return (
      <section className="daily-wellbeing-card daily-wellbeing-card--state" ref={cardRef}>
        <ErrorState message={errorMessage(current.error)} retry={() => void current.refetch()} />
      </section>
    );
  }
  if (record && !editing) {
    return (
      <SavedWellbeingCard
        onEdit={() => {
          setDraft(formFromRecord(record));
          setNoteOpen(Boolean(record.note));
          setEditing(true);
        }}
        record={record}
      />
    );
  }

  const savePayload: DailyWellbeingSave = {
    sleep_quality: numericOrNull(form.sleepQuality),
    sleep_duration_minutes: minutesFromSleepHours(form.sleepDurationHours),
    mood: numericOrNull(form.mood),
    note: form.note.trim() || null,
  };

  return (
    <Card
      className="daily-wellbeing-card daily-wellbeing-card--form"
      defaultOpen
      description="По желанию · короткая отметка за выбранный день."
      family="wellbeing"
      summary={
        <>
          <span>{formatDay(localDate)}</span>
          {record && <Badge tone="success">Сохранено</Badge>}
        </>
      }
      title="Сон и настроение"
    >
      <p className="daily-wellbeing__context">
        Короткая субъективная отметка. Она не влияет на тренировочный план и не является медицинской
        оценкой.
      </p>

      {current.error && (
        <p className="daily-wellbeing__inline-error">{errorMessage(current.error)}</p>
      )}
      {!online && (
        <p className="daily-wellbeing__offline" role="status">
          Нет связи. Поля остаются на экране и готовы к повторной отправке после подключения.
        </p>
      )}
      {saveError && (
        <div className="daily-wellbeing__inline-error" role="alert">
          <span>{saveError}</span>
          {lastPayload && online && (
            <Button
              onClick={() => save.mutate({ date: localDate, payload: lastPayload })}
              type="button"
              variant="secondary"
            >
              Повторить
            </Button>
          )}
        </div>
      )}
      {removeError && (
        <div className="daily-wellbeing__inline-error" role="alert">
          <span>{removeError}</span>
          {online && (
            <Button onClick={() => remove.mutate(localDate)} type="button" variant="secondary">
              Повторить удаление
            </Button>
          )}
        </div>
      )}

      <form
        className="daily-wellbeing__form"
        ref={(element) => {
          cardRef.current = element;
        }}
        onSubmit={(event) => {
          event.preventDefault();
          if (
            save.isPending ||
            remove.isPending ||
            isEmpty ||
            durationError ||
            !online ||
            !isDateAllowed
          )
            return;
          setLastPayload(savePayload);
          save.mutate({ date: localDate, payload: savePayload });
        }}
      >
        <Field
          hint="Можно выбрать сегодня или недавнюю дату."
          label="День"
          labelFor={`${instanceId}-date`}
        >
          <DateInput
            disabled={save.isPending || remove.isPending}
            id={`${instanceId}-date`}
            max={today}
            min={addCalendarDays(today, -90)}
            onChange={(event) => {
              const nextDate = event.target.value;
              if (nextDate === localDate) return;
              void (async () => {
                if (
                  isDirty &&
                  !(await confirm({
                    title: 'Сменить день без сохранения?',
                    message: 'Введённые данные для текущего дня будут потеряны.',
                    confirmText: 'Сменить день',
                  }))
                ) {
                  return;
                }
                setLocalDate(nextDate);
                setDraft(null);
                setNoteOpen(false);
                setEditing(true);
                setLastPayload(null);
              })();
            }}
            value={localDate}
          />
        </Field>

        <OptionField
          disabled={save.isPending || remove.isPending}
          id={`${instanceId}-sleep`}
          legend="Как спалось?"
          name={`${instanceId}-sleep-quality`}
          onChange={(value) =>
            setDraft((currentDraft) => ({
              ...(currentDraft ?? form),
              sleepQuality: value,
            }))
          }
          options={sleepOptions}
          value={form.sleepQuality}
        />
        <OptionField
          disabled={save.isPending || remove.isPending}
          id={`${instanceId}-mood`}
          legend="Как себя ощущали?"
          name={`${instanceId}-mood`}
          onChange={(value) =>
            setDraft((currentDraft) => ({
              ...(currentDraft ?? form),
              mood: value,
            }))
          }
          options={moodOptions}
          value={form.mood}
        />

        <Field label="Сколько спали, часов" labelFor={`${instanceId}-duration`}>
          <Input
            aria-describedby={`${instanceId}-duration-${durationError ? 'error' : 'hint'}`}
            aria-invalid={durationError ? true : undefined}
            disabled={save.isPending || remove.isPending}
            id={`${instanceId}-duration`}
            inputMode="decimal"
            onChange={(event) =>
              setDraft((currentDraft) => ({
                ...(currentDraft ?? form),
                sleepDurationHours: event.target.value,
              }))
            }
            placeholder="Например, 7,5"
            type="text"
            value={form.sleepDurationHours}
          />
          {durationError ? (
            <span className="ui-field__error" id={`${instanceId}-duration-error`} role="alert">
              {durationError}
            </span>
          ) : (
            <span className="ui-field__hint" id={`${instanceId}-duration-hint`}>
              Необязательно. Например, 7,5; допустимый диапазон — от 1 минуты до 24 часов.
            </span>
          )}
        </Field>

        <details
          className="daily-wellbeing__note"
          onToggle={(event) => setNoteOpen(event.currentTarget.open)}
          open={noteOpen}
        >
          <summary className="yfc-disclosure-summary">
            Добавить заметку <small>не попадёт в отчёт</small>
            <DisclosureIcon />
          </summary>
          <Field
            hint={`${form.note.length}/500 символов`}
            label="Заметка для себя"
            labelFor={`${instanceId}-note`}
          >
            <textarea
              disabled={save.isPending || remove.isPending}
              id={`${instanceId}-note`}
              maxLength={500}
              onChange={(event) =>
                setDraft((currentDraft) => ({
                  ...(currentDraft ?? form),
                  note: event.target.value,
                }))
              }
              placeholder="Например, поздно лёгли или был насыщенный день"
              rows={3}
              value={form.note}
            />
          </Field>
        </details>

        {!isDateAllowed && (
          <p className="daily-wellbeing__inline-error" role="alert">
            Нельзя сохранить будущую дату.
          </p>
        )}
        {isEmpty && (
          <p className="daily-wellbeing__hint" role="status">
            Выберите хотя бы один показатель — заполнение остаётся необязательным.
          </p>
        )}
        <div className="daily-wellbeing__actions">
          <Button
            disabled={
              save.isPending ||
              remove.isPending ||
              isEmpty ||
              Boolean(durationError) ||
              !online ||
              !isDateAllowed
            }
            type="submit"
          >
            {save.isPending ? 'Сохраняем…' : 'Сохранить отметку'}
          </Button>
          {record && (
            <Button
              disabled={save.isPending || remove.isPending}
              onClick={async () => {
                if (
                  await confirm({
                    title: 'Удалить отметку?',
                    message: `${formatDay(localDate)}. Сон и настроение будут удалены из истории и отчётов.`,
                    confirmText: 'Удалить',
                  })
                ) {
                  remove.mutate(localDate);
                }
              }}
              type="button"
              variant="danger"
            >
              {remove.isPending ? 'Удаляем…' : 'Удалить'}
            </Button>
          )}
          <Button
            disabled={save.isPending || remove.isPending}
            onClick={() => void leaveForm()}
            type="button"
            variant="ghost"
          >
            {onExit ? 'Вернуться' : record ? 'Отменить изменение' : 'Отмена'}
          </Button>
        </div>
      </form>
    </Card>
  );
}
