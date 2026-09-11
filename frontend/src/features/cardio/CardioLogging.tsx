import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';
import type {
  CardioSession,
  CardioSessionCreate,
  CardioSessionUpdate,
  ProgressSummary,
} from '../../shared/api/types';
import {
  addCalendarDays,
  dateInputValue,
  dateTimeInputValue,
  detectedTimeZone,
  formatCalendarDate,
} from '../../shared/dateTime';
import { queryKeys } from '../../shared/queryKeys';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { Icon } from '../../shared/ui/Icon';
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';

type CardioActivityType = CardioSession['activity_type'];
type CardioStatus = CardioSession['status'];
type CardioSummary = ProgressSummary['cardio'];

const activityLabels: Record<CardioActivityType, string> = {
  walking: 'Ходьба',
  running: 'Бег',
  elliptical: 'Эллиптический тренажёр',
  stationary_bike: 'Велотренажёр / велоэргометр',
  cycling: 'Велосипед',
  rowing: 'Гребной тренажёр',
  stepper: 'Степпер / лестница',
  swimming: 'Плавание',
  other: 'Другая активность',
};

const zoneLabels: Record<number, string> = {
  1: 'Зона 1 · очень легко',
  2: 'Зона 2 · легко и ровно',
  3: 'Зона 3 · умеренно',
  4: 'Зона 4 · тяжело',
  5: 'Зона 5 · почти максимум',
};

let fallbackRequestCounter = 0;

function requestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  fallbackRequestCounter += 1;
  const suffix = `${Date.now().toString(16)}${fallbackRequestCounter.toString(16)}`
    .padStart(12, '0')
    .slice(-12);
  return `00000000-0000-4000-8000-${suffix}`;
}

interface CardioDraft {
  activityType: CardioActivityType;
  duration: string;
  distance: string;
  averageHeartRate: string;
  heartRateZone: string;
  note: string;
  scheduledAt: string;
  status: CardioStatus;
  clientRequestId: string;
}

function emptyDraft(timeZone: string, initialDate?: string): CardioDraft {
  const currentDateTime = dateTimeInputValue(new Date(), timeZone);
  return {
    activityType: 'walking',
    duration: '',
    distance: '',
    averageHeartRate: '',
    heartRateZone: '',
    note: '',
    scheduledAt: initialDate ? `${initialDate}${currentDateTime.slice(10)}` : currentDateTime,
    status: 'completed',
    clientRequestId: requestId(),
  };
}

function draftFromSession(session: CardioSession): CardioDraft {
  return {
    activityType: session.activity_type,
    duration: String(session.duration_minutes),
    distance: session.distance_km == null ? '' : String(session.distance_km),
    averageHeartRate:
      session.average_heart_rate_bpm == null ? '' : String(session.average_heart_rate_bpm),
    heartRateZone: session.heart_rate_zone == null ? '' : String(session.heart_rate_zone),
    note: session.note ?? '',
    scheduledAt: session.scheduled_at.slice(0, 16),
    status: session.status,
    clientRequestId: requestId(),
  };
}

function optionalNumber(value: string): number | null {
  return value.trim() === '' ? null : Number(value.replace(',', '.'));
}

function draftErrors(draft: CardioDraft): Record<string, string> {
  const errors: Record<string, string> = {};
  const duration = Number(draft.duration);
  const distance = optionalNumber(draft.distance);
  const averageHeartRate = optionalNumber(draft.averageHeartRate);
  if (!Number.isInteger(duration) || duration < 1 || duration > 600) {
    errors.duration = 'Укажите длительность от 1 до 600 минут.';
  }
  if (distance != null && (!Number.isFinite(distance) || distance <= 0 || distance > 1000)) {
    errors.distance = 'Укажите дистанцию больше 0 и не больше 1000 км.';
  }
  if (
    averageHeartRate != null &&
    (!Number.isInteger(averageHeartRate) || averageHeartRate < 30 || averageHeartRate > 250)
  ) {
    errors.averageHeartRate = 'Укажите средний пульс от 30 до 250 уд/мин.';
  }
  if (!draft.scheduledAt) errors.scheduledAt = 'Укажите дату и время активности.';
  if (draft.note.length > 500) errors.note = 'Заметка должна быть не длиннее 500 символов.';
  return errors;
}

function payloadFromDraft(draft: CardioDraft): CardioSessionCreate {
  return {
    client_request_id: draft.clientRequestId,
    activity_type: draft.activityType,
    duration_minutes: Number(draft.duration),
    distance_km: optionalNumber(draft.distance),
    average_heart_rate_bpm: optionalNumber(draft.averageHeartRate),
    heart_rate_zone: optionalNumber(draft.heartRateZone),
    note: draft.note.trim() || null,
    scheduled_at: draft.scheduledAt,
    status: draft.status,
  };
}

function updateFromDraft(draft: CardioDraft): CardioSessionUpdate {
  const payload = payloadFromDraft(draft);
  return {
    activity_type: payload.activity_type,
    duration_minutes: payload.duration_minutes,
    distance_km: payload.distance_km,
    average_heart_rate_bpm: payload.average_heart_rate_bpm,
    heart_rate_zone: payload.heart_rate_zone,
    note: payload.note,
    scheduled_at: payload.scheduled_at,
    status: payload.status,
  };
}

function formatSessionDate(value: string): string {
  const [date, time = ''] = value.split('T');
  if (!date) return value;
  const calendarDate = formatCalendarDate(date, { day: 'numeric', month: 'short' });
  return time ? `${calendarDate}, ${time.slice(0, 5)}` : calendarDate;
}

function CardioSessionForm({
  editing,
  onCancel,
  onSaved,
  timeZone,
  initialDate,
}: {
  editing?: CardioSession | null;
  onCancel?: () => void;
  onSaved: () => void;
  timeZone: string;
  initialDate?: string;
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const [draft, setDraft] = useState<CardioDraft>(() =>
    editing ? draftFromSession(editing) : emptyDraft(timeZone, initialDate),
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [optionalOpen, setOptionalOpen] = useState(
    Boolean(
      editing?.distance_km ||
      editing?.average_heart_rate_bpm ||
      editing?.heart_rate_zone ||
      editing?.note,
    ),
  );

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const save = useMutation({
    mutationFn: () =>
      editing
        ? api<CardioSession>(`/api/v1/workouts/cardio/${editing.id}`, {
            method: 'PATCH',
            body: updateFromDraft(draft),
          })
        : api<CardioSession>('/api/v1/workouts/cardio', {
            method: 'POST',
            body: payloadFromDraft(draft),
          }),
    onSuccess: async () => {
      setDirty(false);
      setSubmitError(null);
      if (!editing) {
        trackProductEvent({ name: 'cardio_logged', surface: productEventSurface() });
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.cardio.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.progress.summaries }),
      ]);
      toast(editing ? 'Кардио-запись обновлена' : 'Кардио записано');
      if (editing) onSaved();
      else {
        setDraft(emptyDraft(timeZone, initialDate));
        setOptionalOpen(false);
        onSaved();
      }
    },
    onError: (reason) => setSubmitError((reason as Error).message),
  });

  const update = <Key extends keyof CardioDraft>(key: Key, value: CardioDraft[Key]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setDirty(true);
    setSubmitError(null);
    setErrors((current) => ({ ...current, [key]: '' }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const nextErrors = draftErrors(draft);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    save.mutate();
  };

  return (
    <form
      className="cardio-form"
      noValidate
      onFocusCapture={(event) => {
        const focused = event.target;
        if (!(focused instanceof HTMLElement)) return;
        requestAnimationFrame(() => {
          focused.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        });
      }}
      onSubmit={submit}
    >
      <div className="cardio-form__core">
        <Field label="Вид активности" labelFor={`cardio-activity-${editing?.id ?? 'new'}`}>
          <Select
            id={`cardio-activity-${editing?.id ?? 'new'}`}
            value={draft.activityType}
            onChange={(event) => update('activityType', event.target.value as CardioActivityType)}
          >
            {Object.entries(activityLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          error={errors.duration}
          hint="От 1 до 600 минут"
          label="Длительность, мин"
          labelFor={`cardio-duration-${editing?.id ?? 'new'}`}
        >
          <Input
            id={`cardio-duration-${editing?.id ?? 'new'}`}
            inputMode="numeric"
            min="1"
            max="600"
            required
            type="number"
            value={draft.duration}
            onChange={(event) => update('duration', event.target.value)}
          />
        </Field>
        <Field
          error={errors.scheduledAt}
          label="Дата и время"
          labelFor={`cardio-scheduled-${editing?.id ?? 'new'}`}
        >
          <Input
            id={`cardio-scheduled-${editing?.id ?? 'new'}`}
            required
            type="datetime-local"
            value={draft.scheduledAt}
            onChange={(event) => update('scheduledAt', event.target.value)}
          />
        </Field>
        {editing && (
          <Field label="Статус" labelFor={`cardio-status-${editing.id}`}>
            <Select
              id={`cardio-status-${editing.id}`}
              value={draft.status}
              onChange={(event) => update('status', event.target.value as CardioStatus)}
            >
              <option value="completed">Завершено</option>
              <option value="planned">Запланировано</option>
            </Select>
          </Field>
        )}
      </div>

      <details
        className="cardio-form__optional"
        open={optionalOpen}
        onToggle={(event) => setOptionalOpen(event.currentTarget.open)}
      >
        <summary>Дистанция, пульс и заметка</summary>
        <div className="cardio-form__optional-fields">
          <Field
            error={errors.distance}
            hint="Необязательно · километры"
            label="Дистанция, км"
            labelFor={`cardio-distance-${editing?.id ?? 'new'}`}
          >
            <Input
              id={`cardio-distance-${editing?.id ?? 'new'}`}
              inputMode="decimal"
              min="0.01"
              max="1000"
              step="0.01"
              type="number"
              value={draft.distance}
              onChange={(event) => update('distance', event.target.value)}
            />
          </Field>
          <Field
            error={errors.averageHeartRate}
            hint="Необязательно · 30–250 уд/мин"
            label="Средний пульс, уд/мин"
            labelFor={`cardio-heart-rate-${editing?.id ?? 'new'}`}
          >
            <Input
              id={`cardio-heart-rate-${editing?.id ?? 'new'}`}
              inputMode="numeric"
              min="30"
              max="250"
              type="number"
              value={draft.averageHeartRate}
              onChange={(event) => update('averageHeartRate', event.target.value)}
            />
          </Field>
          <Field
            hint="Зона — ориентир интенсивности, а не оценка здоровья или формы."
            label="Зона пульса"
            labelFor={`cardio-zone-${editing?.id ?? 'new'}`}
          >
            <Select
              id={`cardio-zone-${editing?.id ?? 'new'}`}
              value={draft.heartRateZone}
              onChange={(event) => update('heartRateZone', event.target.value)}
            >
              <option value="">Не указывать</option>
              {Object.entries(zoneLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            error={errors.note}
            hint={`${draft.note.length}/500 · не добавляйте медицинские данные без необходимости`}
            label="Заметка"
            labelFor={`cardio-note-${editing?.id ?? 'new'}`}
          >
            <textarea
              id={`cardio-note-${editing?.id ?? 'new'}`}
              maxLength={500}
              rows={3}
              value={draft.note}
              onChange={(event) => update('note', event.target.value)}
            />
          </Field>
        </div>
      </details>

      {submitError && (
        <div className="cardio-form__error" role="alert">
          <strong>Не удалось сохранить запись.</strong>
          <span>{submitError}</span>
        </div>
      )}
      <div className="cardio-form__actions">
        {onCancel && (
          <Button
            disabled={save.isPending}
            onClick={() => {
              setDirty(false);
              onCancel?.();
            }}
            type="button"
            variant="secondary"
          >
            Отмена
          </Button>
        )}
        <Button
          aria-busy={save.isPending}
          disabled={save.isPending || !dirty || Object.keys(draftErrors(draft)).length > 0}
          type="submit"
        >
          {save.isPending ? 'Сохраняем…' : editing ? 'Сохранить изменения' : 'Сохранить кардио'}
        </Button>
      </div>
    </form>
  );
}

function SessionList({ sessions, timeZone }: { sessions: CardioSession[]; timeZone: string }) {
  const queryClient = useQueryClient();
  const { confirm, toast } = useFeedback();
  const [editing, setEditing] = useState<CardioSession | null>(null);
  const complete = useMutation({
    mutationFn: (id: number) =>
      api<CardioSession>(`/api/v1/workouts/cardio/${id}/complete`, { method: 'POST' }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.cardio.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.progress.summaries }),
      ]);
      toast('Кардио отмечено завершённым');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api<void>(`/api/v1/workouts/cardio/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.cardio.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.progress.summaries }),
      ]);
      toast('Кардио-запись удалена');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  if (!sessions.length) {
    return (
      <EmptyState
        title="Кардио пока не записано"
        text="После первой записи здесь появятся фактическая длительность и история."
      />
    );
  }

  return (
    <div className="cardio-session-list">
      {sessions.map((session) =>
        editing?.id === session.id ? (
          <div className="cardio-session-row cardio-session-row--editing" key={session.id}>
            <CardioSessionForm
              editing={session}
              onCancel={() => setEditing(null)}
              onSaved={() => setEditing(null)}
              timeZone={timeZone}
            />
          </div>
        ) : (
          <article className="cardio-session-row" key={session.id}>
            <div className="cardio-session-row__main">
              <div>
                <strong>{activityLabels[session.activity_type]}</strong>
                <span>{formatSessionDate(session.scheduled_at)}</span>
              </div>
              <Badge tone={session.status === 'completed' ? 'success' : 'neutral'}>
                {session.status === 'completed' ? 'Завершено' : 'Запланировано'}
              </Badge>
            </div>
            <dl className="cardio-session-row__facts">
              <div>
                <dt>Длительность</dt>
                <dd>{session.duration_minutes} мин</dd>
              </div>
              {session.distance_km != null && (
                <div>
                  <dt>Дистанция</dt>
                  <dd>{session.distance_km.toLocaleString('ru-RU')} км</dd>
                </div>
              )}
              {session.average_heart_rate_bpm != null && (
                <div>
                  <dt>Средний пульс</dt>
                  <dd>{session.average_heart_rate_bpm} уд/мин</dd>
                </div>
              )}
              {session.heart_rate_zone != null && (
                <div>
                  <dt>Зона пульса</dt>
                  <dd>{zoneLabels[session.heart_rate_zone]}</dd>
                </div>
              )}
            </dl>
            {session.note && <p className="cardio-session-row__note">{session.note}</p>}
            <div className="cardio-session-row__actions">
              {session.status === 'planned' && (
                <Button
                  disabled={complete.isPending}
                  onClick={() => complete.mutate(session.id)}
                  type="button"
                  variant="secondary"
                >
                  Завершить
                </Button>
              )}
              <Button onClick={() => setEditing(session)} type="button" variant="secondary">
                Изменить
              </Button>
              <Button
                disabled={remove.isPending}
                onClick={async () => {
                  if (
                    await confirm({
                      title: 'Удалить cardio-запись?',
                      message: `${activityLabels[session.activity_type]}, ${formatSessionDate(session.scheduled_at)}. Запись будет удалена безвозвратно.`,
                      confirmText: 'Удалить',
                    })
                  ) {
                    remove.mutate(session.id);
                  }
                }}
                type="button"
                variant="danger"
              >
                Удалить
              </Button>
            </div>
          </article>
        ),
      )}
    </div>
  );
}

export function CardioQuickLog({
  onDismiss,
  startOpen = false,
  today,
}: {
  onDismiss?: () => void;
  startOpen?: boolean;
  today: string;
}) {
  const { user } = useAuth();
  const timeZone = user?.profile?.timezone || detectedTimeZone();
  const currentDate = dateInputValue(new Date(), timeZone);
  const isToday = today === currentDate;
  const canLogFactual = today <= currentDate;
  const [formOpen, setFormOpen] = useState(startOpen && canLogFactual);
  const sectionRef = useRef<HTMLElement>(null);
  const sessions = useQuery({
    queryKey: queryKeys.cardio.range(today, today),
    queryFn: () =>
      api<CardioSession[]>(`/api/v1/workouts/cardio?date_from=${today}&date_to=${today}`),
  });

  useEffect(() => {
    if (!startOpen || !canLogFactual || sessions.isLoading) return;
    window.requestAnimationFrame(() => {
      const reducedMotion =
        window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
      sectionRef.current?.scrollIntoView({
        behavior: reducedMotion ? 'auto' : 'smooth',
        block: 'start',
      });
    });
  }, [canLogFactual, sessions.isLoading, startOpen]);

  if (sessions.isLoading) {
    return <LoadingState label="Проверяем кардио за день…" />;
  }

  if (sessions.error) {
    return (
      <section className="cardio-log cardio-log--quick" aria-label="Кардио за выбранный день">
        <ErrorState
          message={(sessions.error as Error).message}
          retry={() => void sessions.refetch()}
        />
      </section>
    );
  }

  const daySessions = sessions.data ?? [];
  const completedSessions = daySessions.filter((session) => session.status === 'completed');
  const plannedSessions = daySessions.filter((session) => session.status === 'planned');
  const isEmpty = daySessions.length === 0;

  return (
    <section
      className={`cardio-log cardio-log--quick${isEmpty ? ' cardio-log--empty' : ''}`}
      aria-labelledby="cardio-quick-title"
      ref={sectionRef}
    >
      <header className="cardio-log__header">
        <div>
          <span className="eyebrow">Фактическая активность</span>
          <h2 id="cardio-quick-title">Кардио</h2>
          <p>
            {isEmpty
              ? canLogFactual
                ? 'Нет записи за выбранный день.'
                : 'Фактическую активность можно добавить в день тренировки или позже.'
              : 'Записи за выбранный день. Планирование кардио находится в разделе программы.'}
          </p>
        </div>
        {isEmpty && canLogFactual ? (
          <Button type="button" variant="secondary" onClick={() => setFormOpen(true)}>
            <Icon name="plus" size={16} /> Добавить
          </Button>
        ) : isEmpty ? (
          <Badge>Будущий день</Badge>
        ) : (
          <Badge>{`${daySessions.length} ${isToday ? 'сегодня' : 'за день'}`}</Badge>
        )}
      </header>
      {completedSessions.length > 0 && (
        <div className="cardio-log__today">
          <h3>Результат кардио</h3>
          <SessionList sessions={completedSessions} timeZone={timeZone} />
        </div>
      )}
      {plannedSessions.length > 0 && (
        <div className="cardio-log__today">
          <h3>План кардио</h3>
          <SessionList sessions={plannedSessions} timeZone={timeZone} />
        </div>
      )}
      {formOpen && canLogFactual ? (
        <div className="cardio-log__entry-form">
          <CardioSessionForm
            key={today}
            initialDate={today}
            onCancel={() => {
              setFormOpen(false);
              onDismiss?.();
            }}
            onSaved={() => {
              setFormOpen(false);
              onDismiss?.();
            }}
            timeZone={timeZone}
          />
        </div>
      ) : !isEmpty && canLogFactual ? (
        <Button type="button" variant="secondary" onClick={() => setFormOpen(true)}>
          {completedSessions.length ? 'Добавить ещё кардио' : 'Добавить фактическое кардио'}
        </Button>
      ) : null}
    </section>
  );
}

export function CardioHistory({
  periodDays,
  dateFrom: requestedDateFrom,
  dateTo: requestedDateTo,
  summary,
  timeZone = detectedTimeZone(),
}: {
  periodDays?: number;
  dateFrom?: string;
  dateTo?: string;
  summary: CardioSummary;
  timeZone?: string;
}) {
  const dateTo = requestedDateTo ?? dateInputValue(new Date(), timeZone);
  const dateFrom = requestedDateFrom ?? addCalendarDays(dateTo, -((periodDays ?? 30) - 1));
  const sessions = useQuery({
    queryKey: queryKeys.cardio.range(dateFrom, dateTo),
    queryFn: () =>
      api<CardioSession[]>(
        `/api/v1/workouts/cardio?date_from=${dateFrom}&date_to=${dateTo}&limit=100`,
      ),
  });
  const zoneSummary = useMemo(
    () =>
      summary.zone_duration
        .map((item) => `зона ${item.zone} — ${item.duration_minutes} мин`)
        .join(' · '),
    [summary.zone_duration],
  );

  return (
    <section
      className="progress-section cardio-history"
      id="progress-cardio"
      aria-labelledby="progress-cardio-title"
    >
      <header className="progress-section__head">
        <div>
          <span className="eyebrow">Фактические сессии</span>
          <h2 id="progress-cardio-title">Кардио</h2>
          <p>Частота и длительность отдельно от силового объёма.</p>
        </div>
        <Badge>{summary.completed_sessions} завершено</Badge>
      </header>
      <dl className="cardio-summary-strip" aria-label="Итоги кардио за период">
        <div>
          <dt>Частота</dt>
          <dd>{summary.frequency_per_week.toLocaleString('ru-RU')} в неделю</dd>
        </div>
        <div>
          <dt>Длительность</dt>
          <dd>{summary.duration_minutes} мин</dd>
        </div>
        <div>
          <dt>Дистанция</dt>
          <dd>
            {summary.distance_km == null
              ? 'Не указана'
              : `${summary.distance_km.toLocaleString('ru-RU')} км`}
          </dd>
        </div>
        <div>
          <dt>По зонам</dt>
          <dd>{zoneSummary || 'Нет введённых зон'}</dd>
        </div>
      </dl>
      {sessions.isLoading ? (
        <LoadingState label="Загружаем историю кардио…" />
      ) : sessions.error ? (
        <ErrorState
          message={(sessions.error as Error).message}
          retry={() => void sessions.refetch()}
        />
      ) : (
        <SessionList sessions={sessions.data ?? []} timeZone={timeZone} />
      )}
    </section>
  );
}
