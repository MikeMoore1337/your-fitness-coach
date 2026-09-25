import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  Client,
  CoachAgenda,
  CoachClientOperations,
  CoachOperationsToday,
  CoachPackage,
  CoachPayment,
  CoachSession,
  CoachTask,
} from '../../shared/api/types';
import { api } from '../../shared/api/client';
import { queryKeys } from '../../shared/queryKeys';
import {
  addCalendarDays,
  calendarWeek,
  dateInputValue,
  detectedTimeZone,
} from '../../shared/dateTime';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
  SegmentedControl,
} from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { WeekStrip } from '../../shared/ui/WeekStrip';
import type { CoachTool } from './CoachToolsHub';

type Composer = 'session' | 'task' | 'package' | 'payment' | null;
type ViewMode = 'day' | 'week';
type SessionStatus = CoachSession['status'];
type CoachOperationsSurface = 'overview' | 'schedule' | 'tasks' | 'finance';

type SessionDraft = {
  clientId: string;
  date: string;
  time: string;
  duration: string;
  format: CoachSession['format'];
  location: string;
  privateNote: string;
  packageId: string;
  repeatWeekly: boolean;
  occurrenceCount: string;
};

const formatLabels: Record<CoachSession['format'], string> = {
  gym: 'Зал',
  online: 'Онлайн',
  other: 'Другое',
};

const statusLabels: Record<SessionStatus, string> = {
  scheduled: 'Запланировано',
  completed: 'Завершено',
  cancelled: 'Отменено',
  no_show: 'Не пришёл',
};

const packageStateLabels: Record<CoachPackage['state'], string> = {
  active: 'Активен',
  finished: 'Завершён',
  cancelled: 'Отменён',
};

const paymentStatusLabels: Record<CoachPayment['status'], string> = {
  expected: 'Ожидается',
  partial: 'Частично оплачено',
  paid: 'Оплачено',
  cancelled: 'Отменено',
};

function randomKey(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

function sessionDate(value: string): string {
  return value.slice(0, 10);
}

function sessionTime(value: string): string {
  return value.slice(11, 16);
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' }).format(
    new Date(`${value}T12:00:00`),
  );
}

function sessionTone(status: SessionStatus): 'neutral' | 'success' | 'warning' | 'danger' {
  if (status === 'completed') return 'success';
  if (status === 'no_show') return 'warning';
  if (status === 'cancelled') return 'danger';
  return 'neutral';
}

function money(value: number, currency: string): string {
  return `${(value / 100).toLocaleString('ru-RU')} ${currency}`;
}

function clientName(clients: Client[], clientId: number): string {
  return clients.find((client) => client.id === clientId)?.full_name || `Клиент #${clientId}`;
}

function weekdayForDate(value: string): number {
  const day = new Date(`${value}T12:00:00Z`).getUTCDay();
  return (day + 6) % 7;
}

function defaultSessionDraft(date: string, clients: Client[]): SessionDraft {
  return {
    clientId: String(clients.find((client) => client.id != null)?.id ?? ''),
    date,
    time: '19:00',
    duration: '60',
    format: 'online',
    location: 'Telegram-звонок',
    privateNote: '',
    packageId: '',
    repeatWeekly: false,
    occurrenceCount: '4',
  };
}

function invalidateCrm(queryClient: ReturnType<typeof useQueryClient>): Promise<void> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.trainer.operationsToday }),
    queryClient.invalidateQueries({ queryKey: ['coach', 'agenda'] }),
    queryClient.invalidateQueries({ queryKey: queryKeys.trainer.packages }),
    queryClient.invalidateQueries({ queryKey: queryKeys.trainer.payments }),
    queryClient.invalidateQueries({ queryKey: queryKeys.trainer.tasks }),
  ]).then(() => undefined);
}

function sessionSummary(session: CoachSession): string {
  return `${sessionTime(session.starts_at)} · ${session.duration_minutes} мин · ${formatLabels[session.format]}`;
}

function SessionRow({
  clients,
  item,
  onEdit,
  onOpenClient,
  onStatus,
}: {
  clients: Client[];
  item: CoachSession;
  onEdit: (item: CoachSession) => void;
  onOpenClient: (clientId: number) => void;
  onStatus: (item: CoachSession, status: SessionStatus, chargePackage?: boolean) => void;
}) {
  const canAct = item.status === 'scheduled';
  return (
    <article className="coach-operations__session" data-testid={`coach-session-${item.id}`}>
      <div className="coach-operations__session-main">
        <div className="coach-operations__row-head">
          <button
            className="text-button coach-operations__client-link"
            onClick={() => onOpenClient(item.client_id)}
            type="button"
          >
            {item.client_name || clientName(clients, item.client_id)}
          </button>
          <Badge tone={sessionTone(item.status)}>{statusLabels[item.status]}</Badge>
        </div>
        <strong>{sessionSummary(item)}</strong>
        <span className="coach-operations__secondary">
          {formatLabels[item.format]}
          {item.location ? ` · ${item.location}` : ''}
          {item.package_id ? ` · пакет: ${item.package_balance ?? '—'} осталось` : ''}
        </span>
        {item.private_note && <p>{item.private_note}</p>}
      </div>
      <div className="coach-operations__row-actions">
        {item.status === 'scheduled' && (
          <Button onClick={() => onEdit(item)} type="button" variant="secondary">
            Изменить
          </Button>
        )}
        {canAct && (
          <>
            <Button onClick={() => onStatus(item, 'completed')} type="button">
              Завершить
            </Button>
            <Button onClick={() => onStatus(item, 'no_show')} type="button" variant="secondary">
              Не пришёл
            </Button>
            <Button onClick={() => onStatus(item, 'cancelled')} type="button" variant="danger">
              Отменить
            </Button>
          </>
        )}
      </div>
      {canAct && item.package_id && (
        <div className="coach-operations__policy-hint">
          «Не пришёл» не списывает пакет автоматически. Списание можно подтвердить отдельно.
          <button
            className="text-button"
            onClick={() => onStatus(item, 'no_show', true)}
            type="button"
          >
            Не пришёл · списать
          </button>
        </div>
      )}
    </article>
  );
}

function CoachOperationsOverview({
  sessions,
  tasks,
  lowPackageCount,
  paymentCount,
  onNavigate,
}: {
  sessions: CoachSession[];
  tasks: CoachTask[];
  lowPackageCount: number;
  paymentCount: number;
  onNavigate?: (tool: CoachTool) => void;
}) {
  const nextSession = sessions[0];
  const totalFacts = sessions.length + tasks.length + lowPackageCount + paymentCount;
  return (
    <section className="coach-operations__overview" aria-labelledby="coach-overview-title">
      <div className="coach-operations__section-head">
        <div>
          <span className="eyebrow">Рабочий обзор</span>
          <h3 id="coach-overview-title">Что дальше</h3>
        </div>
        <Badge>{totalFacts}</Badge>
      </div>
      <div className="coach-operations__overview-list">
        <button
          className="coach-operations__overview-row"
          onClick={() => onNavigate?.('schedule')}
          type="button"
        >
          <span>
            <strong>Расписание и встречи</strong>
            <small>
              {nextSession
                ? `${nextSession.client_name || 'Клиент'} · ${sessionSummary(nextSession)}`
                : 'Сегодня встреч пока нет'}
            </small>
          </span>
          <Badge tone={sessions.length ? 'warning' : 'neutral'}>{sessions.length}</Badge>
          <Icon name="arrow-right" size={16} />
        </button>
        <button
          className="coach-operations__overview-row"
          onClick={() => onNavigate?.('tasks')}
          type="button"
        >
          <span>
            <strong>Задачи клиентов</strong>
            <small>
              {tasks.length ? 'Есть задачи, требующие действия' : 'На сегодня задач нет'}
            </small>
          </span>
          <Badge tone={tasks.length ? 'warning' : 'neutral'}>{tasks.length}</Badge>
          <Icon name="arrow-right" size={16} />
        </button>
        <button
          className="coach-operations__overview-row"
          onClick={() => onNavigate?.('finance')}
          type="button"
        >
          <span>
            <strong>Пакеты и оплаты</strong>
            <small>
              {lowPackageCount + paymentCount
                ? 'Есть финансовые факты для проверки'
                : 'Новых финансовых фактов нет'}
            </small>
          </span>
          <Badge tone={lowPackageCount + paymentCount ? 'warning' : 'neutral'}>
            {lowPackageCount + paymentCount}
          </Badge>
          <Icon name="arrow-right" size={16} />
        </button>
      </div>
    </section>
  );
}

export function CoachOperationsPanel({
  clients,
  onOpenClient,
  timezone,
  onDemoStep,
  surface = 'overview',
  onNavigate,
}: {
  clients: Client[];
  onOpenClient: (clientId: number) => void;
  timezone?: string | null;
  onDemoStep?: (step: 'task') => void;
  surface?: CoachOperationsSurface;
  onNavigate?: (tool: CoachTool) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const timezoneName = timezone || detectedTimeZone();
  const today = dateInputValue(new Date(), timezoneName);
  const [selectedDate, setSelectedDate] = useState(today);
  const [view, setView] = useState<ViewMode>('day');
  const [composer, setComposer] = useState<Composer>(null);
  const [editingSessionId, setEditingSessionId] = useState<number | null>(null);
  const [editingPaymentId, setEditingPaymentId] = useState<number | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [sessionDraft, setSessionDraft] = useState<SessionDraft>(() =>
    defaultSessionDraft(today, clients),
  );
  const [taskTitle, setTaskTitle] = useState('');
  const [taskClientId, setTaskClientId] = useState('');
  const [taskDate, setTaskDate] = useState(today);
  const [packageName, setPackageName] = useState('Сопровождение');
  const [packageClientId, setPackageClientId] = useState('');
  const [packageCount, setPackageCount] = useState('10');
  const [paymentClientId, setPaymentClientId] = useState('');
  const [paymentExpected, setPaymentExpected] = useState('');
  const [paymentPaid, setPaymentPaid] = useState('');
  const [paymentCurrency, setPaymentCurrency] = useState('RUB');

  const rangeStart = calendarWeek(selectedDate)[0] ?? selectedDate;
  const rangeEnd = addCalendarDays(rangeStart, 6);
  const clientsWithId = useMemo(
    () => clients.filter((client): client is Client & { id: number } => client.id != null),
    [clients],
  );
  const operations = useQuery<CoachOperationsToday>({
    queryKey: queryKeys.trainer.operationsToday,
    queryFn: () => api<CoachOperationsToday>('/api/v1/coach/operations/today'),
  });
  const agenda = useQuery<CoachAgenda>({
    queryKey: queryKeys.trainer.agenda(rangeStart, rangeEnd),
    queryFn: () =>
      api<CoachAgenda>(
        `/api/v1/coach/agenda?date_from=${encodeURIComponent(rangeStart)}&date_to=${encodeURIComponent(rangeEnd)}`,
      ),
    enabled: surface === 'schedule',
  });
  const packages = useQuery<CoachPackage[]>({
    queryKey: queryKeys.trainer.packages,
    queryFn: () => api<CoachPackage[]>('/api/v1/coach/packages'),
    enabled: surface === 'finance' || composer === 'session' || composer === 'payment',
  });
  const payments = useQuery<CoachPayment[]>({
    queryKey: queryKeys.trainer.payments,
    queryFn: () => api<CoachPayment[]>('/api/v1/coach/payments'),
    enabled: surface === 'finance',
  });
  const taskList = useQuery<CoachTask[]>({
    queryKey: queryKeys.trainer.tasks,
    queryFn: () => api<CoachTask[]>('/api/v1/coach/tasks?state=open'),
    enabled: surface === 'tasks',
  });

  const visibleSessions = useMemo(() => {
    const items = agenda.data?.items ?? [];
    return items
      .filter((item) => view === 'week' || sessionDate(item.starts_at) === selectedDate)
      .sort((left, right) => left.starts_at.localeCompare(right.starts_at));
  }, [agenda.data?.items, selectedDate, view]);

  const countsByDate = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of agenda.data?.items ?? []) {
      counts.set(sessionDate(item.starts_at), (counts.get(sessionDate(item.starts_at)) ?? 0) + 1);
    }
    return counts;
  }, [agenda.data?.items]);

  const mutation = useMutation({
    mutationFn: async ({
      body,
      method,
      path,
    }: {
      body: unknown;
      method: 'POST' | 'PATCH';
      path: string;
    }) => api(path, { method, body, headers: { 'Idempotency-Key': randomKey() } }),
    onSuccess: async () => {
      await invalidateCrm(queryClient);
      setComposer(null);
      setEditingSessionId(null);
      setEditingPaymentId(null);
      setFormError(null);
      toast('Операция сохранена');
    },
    onError: (reason) =>
      setFormError(reason instanceof Error ? reason.message : 'Не удалось сохранить'),
  });

  const openNewSession = () => {
    setFormError(null);
    setEditingSessionId(null);
    setSessionDraft(defaultSessionDraft(selectedDate, clients));
    setComposer('session');
  };

  const openNewPayment = () => {
    setFormError(null);
    setEditingPaymentId(null);
    setPaymentExpected('');
    setPaymentPaid('');
    setPaymentCurrency('RUB');
    setComposer('payment');
  };

  const openNewTask = () => {
    setFormError(null);
    setTaskTitle('');
    setTaskClientId('');
    setTaskDate(today);
    setComposer('task');
  };

  const openNewPackage = () => {
    setFormError(null);
    setPackageName('Сопровождение');
    setPackageClientId('');
    setPackageCount('10');
    setComposer('package');
  };

  const editPayment = (item: CoachPayment) => {
    setFormError(null);
    setEditingPaymentId(item.id);
    setPaymentClientId(String(item.client_id));
    setPaymentExpected(String(item.expected_amount_minor / 100));
    setPaymentPaid(String(item.paid_amount_minor / 100));
    setPaymentCurrency(item.currency);
    setComposer('payment');
  };

  const editSession = (item: CoachSession) => {
    setFormError(null);
    setEditingSessionId(item.id);
    setSessionDraft({
      clientId: String(item.client_id),
      date: sessionDate(item.starts_at),
      time: sessionTime(item.starts_at),
      duration: String(item.duration_minutes),
      format: item.format,
      location: item.location ?? '',
      privateNote: item.private_note ?? '',
      packageId: item.package_id ? String(item.package_id) : '',
      repeatWeekly: false,
      occurrenceCount: '4',
    });
    setComposer('session');
  };

  const changeSessionStatus = (
    item: CoachSession,
    status: SessionStatus,
    chargePackage?: boolean,
  ) => {
    mutation.mutate({
      method: 'PATCH',
      path: `/api/v1/coach/sessions/${item.id}`,
      body: { status, apply_to: 'occurrence', charge_package: chargePackage ?? null },
    });
  };

  const submitSession = () => {
    const clientId = Number(sessionDraft.clientId || clientsWithId[0]?.id);
    const duration = Number(sessionDraft.duration);
    if (!clientId || !sessionDraft.date || !sessionDraft.time || !Number.isInteger(duration)) {
      setFormError('Выберите клиента, дату, время и длительность.');
      return;
    }
    const body = {
      client_id: clientId,
      starts_at: `${sessionDraft.date}T${sessionDraft.time}:00`,
      timezone: timezoneName,
      fold: 0,
      duration_minutes: duration,
      format: sessionDraft.format,
      location: sessionDraft.location || null,
      private_note: sessionDraft.privateNote || null,
      package_id: sessionDraft.packageId ? Number(sessionDraft.packageId) : null,
      recurrence:
        !editingSessionId && sessionDraft.repeatWeekly
          ? {
              weekdays: [weekdayForDate(sessionDraft.date)],
              occurrence_count: Number(sessionDraft.occurrenceCount) || 4,
            }
          : null,
    };
    mutation.mutate(
      editingSessionId
        ? {
            method: 'PATCH',
            path: `/api/v1/coach/sessions/${editingSessionId}`,
            body: { ...body, client_id: undefined, recurrence: undefined, apply_to: 'occurrence' },
          }
        : { method: 'POST', path: '/api/v1/coach/sessions', body },
    );
  };

  const submitTask = () => {
    const clientId = Number(taskClientId || clientsWithId[0]?.id);
    if (!clientId || !taskTitle.trim()) {
      setFormError('Укажите клиента и короткое название задачи.');
      return;
    }
    mutation.mutate({
      method: 'POST',
      path: '/api/v1/coach/tasks',
      body: {
        client_id: clientId,
        title: taskTitle.trim(),
        due_at: `${taskDate}T12:00:00`,
        timezone: timezoneName,
        fold: 0,
      },
    });
  };

  const submitPackage = () => {
    const clientId = Number(packageClientId || clientsWithId[0]?.id);
    const count = Number(packageCount);
    if (!clientId || !packageName.trim() || !Number.isInteger(count) || count < 1) {
      setFormError('Укажите клиента, название и количество встреч.');
      return;
    }
    mutation.mutate({
      method: 'POST',
      path: '/api/v1/coach/packages',
      body: {
        client_id: clientId,
        name: packageName.trim(),
        counts_sessions: true,
        included_sessions: count,
      },
    });
  };

  const submitPayment = () => {
    const clientId = Number(paymentClientId || clientsWithId[0]?.id);
    const expected = Math.round(Number(paymentExpected.replace(',', '.')) * 100);
    const paid = Math.round(Number(paymentPaid.replace(',', '.') || 0) * 100);
    if (
      !clientId ||
      !Number.isInteger(expected) ||
      expected <= 0 ||
      !Number.isInteger(paid) ||
      paid < 0
    ) {
      setFormError('Укажите клиента и сумму в рублях.');
      return;
    }
    if (paid > expected) {
      setFormError('Полученная сумма не может быть больше ожидаемой.');
      return;
    }
    const body = {
      expected_amount_minor: expected,
      paid_amount_minor: paid,
      currency: paymentCurrency,
    };
    mutation.mutate(
      editingPaymentId
        ? {
            method: 'PATCH',
            path: `/api/v1/coach/payments/${editingPaymentId}`,
            body,
          }
        : {
            method: 'POST',
            path: '/api/v1/coach/payments',
            body: { ...body, client_id: clientId, package_id: null },
          },
    );
  };

  const renderComposer = () => {
    if (!composer) return null;
    const firstClientId = String(clientsWithId[0]?.id ?? '');
    if (composer === 'session') {
      return (
        <form
          className="coach-operations__form"
          onSubmit={(event) => {
            event.preventDefault();
            submitSession();
          }}
        >
          <div className="coach-operations__form-head">
            <div>
              <span className="eyebrow">{editingSessionId ? 'Перенос' : 'Новая запись'}</span>
              <h3>{editingSessionId ? 'Изменить встречу' : 'Добавить встречу'}</h3>
            </div>
            <Button onClick={() => setComposer(null)} type="button" variant="ghost">
              Закрыть
            </Button>
          </div>
          <div className="coach-operations__form-grid">
            <Field label="Клиент" labelFor="crm-session-client">
              <Select
                id="crm-session-client"
                onChange={(event) =>
                  setSessionDraft((current) => ({ ...current, clientId: event.target.value }))
                }
                value={sessionDraft.clientId || firstClientId}
              >
                {clientsWithId.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.full_name || client.username || `Клиент #${client.id}`}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Дата" labelFor="crm-session-date">
              <Input
                id="crm-session-date"
                onChange={(event) =>
                  setSessionDraft((current) => ({ ...current, date: event.target.value }))
                }
                type="date"
                value={sessionDraft.date}
              />
            </Field>
            <Field label="Время" labelFor="crm-session-time">
              <Input
                id="crm-session-time"
                onChange={(event) =>
                  setSessionDraft((current) => ({ ...current, time: event.target.value }))
                }
                type="time"
                value={sessionDraft.time}
              />
            </Field>
            <Field label="Минут" labelFor="crm-session-duration">
              <Input
                id="crm-session-duration"
                min="15"
                max="480"
                onChange={(event) =>
                  setSessionDraft((current) => ({ ...current, duration: event.target.value }))
                }
                type="number"
                value={sessionDraft.duration}
              />
            </Field>
            <Field label="Формат" labelFor="crm-session-format">
              <Select
                id="crm-session-format"
                onChange={(event) =>
                  setSessionDraft((current) => ({
                    ...current,
                    format: event.target.value as CoachSession['format'],
                  }))
                }
                value={sessionDraft.format}
              >
                {Object.entries(formatLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Место или ссылка" labelFor="crm-session-location">
              <Input
                id="crm-session-location"
                onChange={(event) =>
                  setSessionDraft((current) => ({ ...current, location: event.target.value }))
                }
                value={sessionDraft.location}
              />
            </Field>
            <Field label="Пакет" labelFor="crm-session-package" hint="Необязательно">
              <Select
                id="crm-session-package"
                onChange={(event) =>
                  setSessionDraft((current) => ({ ...current, packageId: event.target.value }))
                }
                value={sessionDraft.packageId}
              >
                <option value="">Без пакета</option>
                {(packages.data ?? []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.client_name} · {item.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Приватная заметка" labelFor="crm-session-note">
            <textarea
              className="ui-input coach-operations__textarea"
              id="crm-session-note"
              maxLength={2000}
              onChange={(event) =>
                setSessionDraft((current) => ({ ...current, privateNote: event.target.value }))
              }
              rows={3}
              value={sessionDraft.privateNote}
            />
          </Field>
          {!editingSessionId && (
            <label className="coach-operations__checkbox">
              <input
                checked={sessionDraft.repeatWeekly}
                onChange={(event) =>
                  setSessionDraft((current) => ({ ...current, repeatWeekly: event.target.checked }))
                }
                type="checkbox"
              />
              <span>Повторять еженедельно</span>
              {sessionDraft.repeatWeekly && (
                <Input
                  aria-label="Количество повторений"
                  min="1"
                  max="52"
                  onChange={(event) =>
                    setSessionDraft((current) => ({
                      ...current,
                      occurrenceCount: event.target.value,
                    }))
                  }
                  type="number"
                  value={sessionDraft.occurrenceCount}
                />
              )}
            </label>
          )}
          <div className="coach-operations__form-actions">
            <Button disabled={mutation.isPending || clientsWithId.length === 0} type="submit">
              {mutation.isPending
                ? 'Сохраняем…'
                : editingSessionId
                  ? 'Сохранить перенос'
                  : 'Записать'}
            </Button>
          </div>
        </form>
      );
    }
    return (
      <form
        className="coach-operations__form"
        onSubmit={(event) => {
          event.preventDefault();
          if (composer === 'task') submitTask();
          if (composer === 'package') submitPackage();
          if (composer === 'payment') submitPayment();
        }}
      >
        <div className="coach-operations__form-head">
          <div>
            <span className="eyebrow">Быстрый факт</span>
            <h3>
              {composer === 'task'
                ? 'Новая задача'
                : composer === 'package'
                  ? 'Новый пакет'
                  : editingPaymentId
                    ? 'Изменить запись об оплате'
                    : 'Учёт оплаты'}
            </h3>
          </div>
          <Button onClick={() => setComposer(null)} type="button" variant="ghost">
            Закрыть
          </Button>
        </div>
        <div className="coach-operations__form-grid">
          <Field label="Клиент" labelFor="crm-fact-client">
            <Select
              id="crm-fact-client"
              onChange={(event) => {
                const value = event.target.value;
                if (composer === 'task') setTaskClientId(value);
                if (composer === 'package') setPackageClientId(value);
                if (composer === 'payment') setPaymentClientId(value);
              }}
              value={
                composer === 'task'
                  ? taskClientId || firstClientId
                  : composer === 'package'
                    ? packageClientId || firstClientId
                    : paymentClientId || firstClientId
              }
            >
              {clientsWithId.map((client) => (
                <option key={client.id} value={client.id}>
                  {client.full_name || client.username || `Клиент #${client.id}`}
                </option>
              ))}
            </Select>
          </Field>
          {composer === 'task' && (
            <>
              <Field label="Что сделать" labelFor="crm-task-title">
                <Input
                  id="crm-task-title"
                  onChange={(event) => setTaskTitle(event.target.value)}
                  placeholder="Например, отправить обратную связь"
                  value={taskTitle}
                />
              </Field>
              <Field label="Срок" labelFor="crm-task-date">
                <Input
                  id="crm-task-date"
                  onChange={(event) => setTaskDate(event.target.value)}
                  type="date"
                  value={taskDate}
                />
              </Field>
            </>
          )}
          {composer === 'package' && (
            <>
              <Field label="Название" labelFor="crm-package-name">
                <Input
                  id="crm-package-name"
                  onChange={(event) => setPackageName(event.target.value)}
                  value={packageName}
                />
              </Field>
              <Field label="Встреч в пакете" labelFor="crm-package-count">
                <Input
                  id="crm-package-count"
                  min="1"
                  max="200"
                  onChange={(event) => setPackageCount(event.target.value)}
                  type="number"
                  value={packageCount}
                />
              </Field>
            </>
          )}
          {composer === 'payment' && (
            <>
              <Field label="Ожидается, ₽" labelFor="crm-payment-expected">
                <Input
                  id="crm-payment-expected"
                  inputMode="decimal"
                  min="0"
                  onChange={(event) => setPaymentExpected(event.target.value)}
                  type="number"
                  value={paymentExpected}
                />
              </Field>
              <Field label="Получено, ₽" labelFor="crm-payment-paid">
                <Input
                  id="crm-payment-paid"
                  inputMode="decimal"
                  min="0"
                  onChange={(event) => setPaymentPaid(event.target.value)}
                  type="number"
                  value={paymentPaid}
                />
              </Field>
              <Field label="Валюта" labelFor="crm-payment-currency">
                <Input
                  id="crm-payment-currency"
                  maxLength={3}
                  onChange={(event) => setPaymentCurrency(event.target.value.toUpperCase())}
                  value={paymentCurrency}
                />
              </Field>
            </>
          )}
        </div>
        <div className="coach-operations__form-actions">
          <Button disabled={mutation.isPending || clientsWithId.length === 0} type="submit">
            {mutation.isPending
              ? 'Сохраняем…'
              : editingPaymentId
                ? 'Сохранить изменения'
                : 'Сохранить'}
          </Button>
        </div>
      </form>
    );
  };

  const operationData = operations.data;
  const tasks = [...(operationData?.overdue_tasks ?? []), ...(operationData?.due_tasks ?? [])];
  const focusedTasks = surface === 'tasks' ? (taskList.data ?? []) : tasks;
  const focusedPackages =
    surface === 'finance' ? (packages.data ?? []) : operationData?.low_packages;
  const focusedPayments =
    surface === 'finance' ? (payments.data ?? []) : operationData?.payment_facts;

  return (
    <section
      className="coach-operations"
      data-testid="coach-operations"
      aria-labelledby="coach-operations-title"
    >
      <header className="coach-operations__header">
        <div>
          <span className="eyebrow">
            {surface === 'overview'
              ? 'Бизнес-операции'
              : surface === 'schedule'
                ? 'Расписание'
                : surface === 'tasks'
                  ? 'Следующий шаг'
                  : 'Факты оплаты'}
          </span>
          <h2 id="coach-operations-title">
            {surface === 'overview'
              ? 'Короткий рабочий обзор'
              : surface === 'schedule'
                ? 'Встречи'
                : surface === 'tasks'
                  ? 'Задачи клиентов'
                  : 'Пакеты и оплаты'}
          </h2>
          <p>
            {surface === 'overview'
              ? 'Сначала ближайшее действие, подробности — в отдельном рабочем разделе.'
              : surface === 'schedule'
                ? 'Откройте день или неделю, чтобы работать со встречами без лишнего контекста.'
                : surface === 'tasks'
                  ? 'Открытые и просроченные задачи клиентов в одном списке.'
                  : 'Остатки пакетов и ручной учёт оплат клиентов.'}
          </p>
        </div>
        <div className="coach-operations__header-actions app-action-group">
          {(surface === 'overview' || surface === 'schedule') && (
            <Button onClick={openNewSession} type="button">
              Новая встреча
            </Button>
          )}
          {surface === 'tasks' && (
            <Button onClick={openNewTask} type="button">
              Новая задача
            </Button>
          )}
          {surface === 'finance' && (
            <>
              <Button onClick={openNewPackage} type="button" variant="secondary">
                Новый пакет
              </Button>
              <Button onClick={openNewPayment} type="button">
                Учесть оплату
              </Button>
            </>
          )}
        </div>
      </header>

      {surface === 'overview' && (
        <CoachOperationsOverview
          lowPackageCount={operationData?.low_packages?.length ?? 0}
          onNavigate={onNavigate}
          paymentCount={operationData?.payment_facts?.length ?? 0}
          sessions={operationData?.sessions ?? []}
          tasks={tasks}
        />
      )}

      {surface !== 'overview' && (
        <div className="coach-operations__metrics" aria-label="Сводка операций сегодня">
          <div>
            <span>Встречи</span>
            <strong>{operationData?.sessions?.length ?? '—'}</strong>
          </div>
          <div>
            <span>Задачи</span>
            <strong>{tasks.length || '—'}</strong>
          </div>
          <div>
            <span>Пакеты ≤ 2</span>
            <strong>{operationData?.low_packages?.length || '—'}</strong>
          </div>
          <div>
            <span>Оплаты</span>
            <strong>{operationData?.payment_facts?.length || '—'}</strong>
          </div>
        </div>
      )}

      {surface === 'schedule' && (
        <>
          <div className="coach-operations__toolbar">
            <SegmentedControl
              ariaLabel="Режим просмотра расписания"
              onChange={(value) => setView(value as ViewMode)}
              options={[
                { label: 'День', value: 'day' },
                { label: 'Неделя', value: 'week' },
              ]}
              value={view}
            />
            <div className="coach-operations__quick-actions">
              <Button onClick={openNewTask} type="button" variant="secondary">
                Задача
              </Button>
              <Button onClick={openNewPackage} type="button" variant="secondary">
                Пакет
              </Button>
              <Button onClick={openNewPayment} type="button" variant="secondary">
                Учёт оплаты
              </Button>
            </div>
          </div>

          {view === 'week' ? (
            <WeekStrip
              anchorDate={selectedDate}
              ariaLabel="Неделя встреч"
              getDayMeta={(day) => {
                const count = countsByDate.get(day) ?? 0;
                return count
                  ? {
                      status: {
                        key: 'planned',
                        label: `${count} ${count === 1 ? 'встреча' : 'встречи'}`,
                        pictogram: 'planned',
                      },
                    }
                  : {};
              }}
              mode="overview"
              navigation={{
                onNext: () => setSelectedDate(addCalendarDays(rangeStart, 7)),
                onPrevious: () => setSelectedDate(addCalendarDays(rangeStart, -7)),
              }}
              title="Рабочая неделя"
              today={today}
            />
          ) : (
            <WeekStrip
              anchorDate={selectedDate}
              ariaLabel="Выберите день для расписания"
              getDayMeta={(day) => {
                const count = countsByDate.get(day) ?? 0;
                return count
                  ? {
                      status: {
                        key: 'planned',
                        label: `${count} ${count === 1 ? 'встреча' : 'встречи'}`,
                        pictogram: 'planned',
                      },
                    }
                  : {};
              }}
              mode="picker"
              navigation={{
                onNext: () => setSelectedDate(addCalendarDays(rangeStart, 7)),
                onPrevious: () => setSelectedDate(addCalendarDays(rangeStart, -7)),
              }}
              onSelect={setSelectedDate}
              selectedDate={selectedDate}
              title="Рабочий день"
              today={today}
            />
          )}

          <section className="coach-operations__agenda" aria-labelledby="coach-agenda-title">
            <div className="coach-operations__section-head">
              <div>
                <span className="eyebrow">Расписание</span>
                <h3 id="coach-agenda-title">
                  {view === 'day'
                    ? dateLabel(selectedDate)
                    : `${dateLabel(rangeStart)} — ${dateLabel(rangeEnd)}`}
                </h3>
              </div>
              <Badge>{visibleSessions.length}</Badge>
            </div>
            {agenda.isPending ? (
              <LoadingState label="Собираем расписание…" />
            ) : agenda.error ? (
              <ErrorState
                message={
                  agenda.error instanceof Error ? agenda.error.message : 'Расписание недоступно'
                }
                retry={() => void agenda.refetch()}
              />
            ) : visibleSessions.length === 0 ? (
              <EmptyState
                title="Встреч пока нет"
                text="Добавьте запись или выберите другой день."
              />
            ) : (
              <div className="coach-operations__session-list">
                {visibleSessions.map((item) => (
                  <SessionRow
                    clients={clients}
                    item={item}
                    key={item.id}
                    onEdit={editSession}
                    onOpenClient={onOpenClient}
                    onStatus={changeSessionStatus}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {(surface === 'tasks' || surface === 'finance') && (
        <div className="coach-operations__facts-grid">
          {surface === 'tasks' && (
            <section className="coach-operations__fact-card" aria-labelledby="coach-tasks-title">
              <div className="coach-operations__section-head">
                <div>
                  <span className="eyebrow">Следующий шаг</span>
                  <h3 id="coach-tasks-title" onFocus={() => onDemoStep?.('task')} tabIndex={-1}>
                    Задачи клиентов
                  </h3>
                </div>
                <Badge tone={focusedTasks.length ? 'warning' : 'neutral'}>
                  {focusedTasks.length}
                </Badge>
              </div>
              {operations.isPending || taskList.isPending ? (
                <LoadingState label="Загружаем задачи…" />
              ) : focusedTasks.length === 0 ? (
                <p className="muted">
                  {surface === 'tasks' ? 'Открытых задач нет.' : 'На сегодня задач нет.'}
                </p>
              ) : (
                <div className="coach-operations__fact-list">
                  {focusedTasks.map((task) => (
                    <div className="coach-operations__fact-row" key={task.id}>
                      <div>
                        <strong>{task.title}</strong>
                        <span>
                          {task.client_name} ·{' '}
                          {task.due_at.slice(0, 10) < today ? 'просрочено' : 'сегодня'}
                        </span>
                      </div>
                      <Button
                        onClick={() =>
                          mutation.mutate({
                            method: 'PATCH',
                            path: `/api/v1/coach/tasks/${task.id}/state`,
                            body: { state: 'completed' },
                          })
                        }
                        type="button"
                        variant="secondary"
                      >
                        Закрыть
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {surface === 'finance' && (
            <section className="coach-operations__fact-card" aria-labelledby="coach-money-title">
              <div className="coach-operations__section-head">
                <div>
                  <span className="eyebrow">Факты оплаты</span>
                  <h3 id="coach-money-title">Пакеты и деньги</h3>
                </div>
                <Badge tone="warning">Ручной учёт</Badge>
              </div>
              <div className="coach-operations__fact-list">
                {(focusedPackages ?? []).map((item) => (
                  <div className="coach-operations__fact-row" key={`package-${item.id}`}>
                    <div>
                      <strong>{item.client_name}</strong>
                      <span>
                        {item.name} · осталось {item.balance} из {item.included_sessions}
                      </span>
                    </div>
                    <Badge tone="warning">Пакет</Badge>
                  </div>
                ))}
                {(focusedPayments ?? []).map((item) => (
                  <div className="coach-operations__fact-row" key={`payment-${item.id}`}>
                    <div>
                      <strong>{item.client_name}</strong>
                      <span>
                        {money(item.paid_amount_minor, item.currency)} из{' '}
                        {money(item.expected_amount_minor, item.currency)}
                      </span>
                    </div>
                    <div className="coach-operations__fact-actions">
                      <Badge tone="warning">{paymentStatusLabels[item.status]}</Badge>
                      <Button onClick={() => editPayment(item)} type="button" variant="secondary">
                        Изменить
                      </Button>
                    </div>
                  </div>
                ))}
                {packages.isPending || payments.isPending ? (
                  <LoadingState label="Загружаем финансовые факты…" />
                ) : !focusedPackages?.length && !focusedPayments?.length ? (
                  <p className="muted">Новых финансовых фактов нет.</p>
                ) : null}
              </div>
            </section>
          )}
        </div>
      )}

      {formError && (
        <p className="coach-operations__form-error" role="alert">
          {formError}
        </p>
      )}
      {renderComposer()}
    </section>
  );
}

export function CoachClientOperationsCard({
  clientId,
  operationalStatus,
}: {
  clientId: number;
  operationalStatus: Client['operational_status'];
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const operations = useQuery<CoachClientOperations>({
    queryKey: queryKeys.trainer.clientOperations(clientId),
    queryFn: () => api<CoachClientOperations>(`/api/v1/coach/clients/${clientId}/operations`),
  });
  const statusMutation = useMutation({
    mutationFn: (value: Client['operational_status']) =>
      api(`/api/v1/coach/clients/${clientId}/operational-status`, {
        method: 'PATCH',
        body: { operational_status: value },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clients });
      toast('Операционный статус обновлён');
    },
    onError: (reason) =>
      toast(reason instanceof Error ? reason.message : 'Не удалось обновить статус', 'error'),
  });

  if (operations.isPending) return <LoadingState label="Загружаем операционный контекст…" />;
  if (operations.error) {
    return (
      <ErrorState
        message={operations.error instanceof Error ? operations.error.message : 'Данные недоступны'}
        retry={() => void operations.refetch()}
      />
    );
  }
  const data = operations.data;
  return (
    <section className="coach-client-operations" aria-labelledby="coach-client-operations-title">
      <div className="coach-operations__section-head">
        <div>
          <span className="eyebrow">Операционный контекст</span>
          <h3 id="coach-client-operations-title">Встречи, задачи и факты оплаты</h3>
        </div>
        <label className="coach-client-operations__status">
          <span>Статус работы</span>
          <Select
            aria-label="Операционный статус клиента"
            disabled={statusMutation.isPending}
            onChange={(event) =>
              statusMutation.mutate(event.target.value as Client['operational_status'])
            }
            value={operationalStatus}
          >
            <option value="active">В работе</option>
            <option value="paused">Пауза</option>
            <option value="archived">Архив</option>
          </Select>
        </label>
      </div>
      <div className="coach-client-operations__grid">
        <div>
          <span>Встречи</span>
          <strong>{data?.sessions?.length ?? 0}</strong>
        </div>
        <div>
          <span>Открытые задачи</span>
          <strong>{data?.tasks?.filter((item) => item.state === 'open').length ?? 0}</strong>
        </div>
      </div>
      {data?.sessions?.slice(0, 3).map((item) => (
        <div className="coach-client-operations__row" key={`session-${item.id}`}>
          <div>
            <strong>{sessionDate(item.starts_at) + ' · ' + sessionTime(item.starts_at)}</strong>
            <span>
              {statusLabels[item.status]} · {formatLabels[item.format]}
            </span>
          </div>
          <Badge tone={sessionTone(item.status)}>{statusLabels[item.status]}</Badge>
        </div>
      ))}
      {data?.packages?.map((item) => (
        <div className="coach-client-operations__row" key={`package-${item.id}`}>
          <div>
            <strong>{item.name}</strong>
            <span>
              {item.counts_sessions ? `Осталось встреч: ${item.balance}` : 'Не списывает встречи'}
            </span>
          </div>
          <Badge tone={item.state === 'active' ? 'success' : 'neutral'}>
            {packageStateLabels[item.state]}
          </Badge>
        </div>
      ))}
      {data?.payments?.map((item) => (
        <div className="coach-client-operations__row" key={`payment-${item.id}`}>
          <div>
            <strong>
              Учёт оплаты · {money(item.paid_amount_minor, item.currency)} из{' '}
              {money(item.expected_amount_minor, item.currency)}
            </strong>
            <span>{paymentStatusLabels[item.status]}</span>
          </div>
          <Badge tone={item.status === 'paid' ? 'success' : 'warning'}>
            {paymentStatusLabels[item.status]}
          </Badge>
        </div>
      ))}
    </section>
  );
}
