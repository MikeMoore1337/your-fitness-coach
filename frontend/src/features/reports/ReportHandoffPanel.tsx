import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { api } from '../../shared/api/client';
import type {
  NutritionReportPeriod,
  ProgressReport,
  ReportHandoff,
  User,
} from '../../shared/api/types';
import { trackGrowthEvent } from '../../shared/analytics/productEvents';
import { Button, EmptyState } from '../../shared/ui/common';

type CurrentTrainer = NonNullable<User['trainer']>;

interface ReportHandoffPanelProps {
  dateFrom: string;
  dateTo: string;
  loading: boolean;
  period: NutritionReportPeriod;
  report: ProgressReport;
  trainer: CurrentTrainer | null;
}

const sectionLabels: Record<string, string> = {
  overview: 'Обзор',
  training: 'Тренировки',
  program: 'Программа',
  cardio: 'Кардио',
  body: 'Замеры тела',
  nutrition: 'Питание',
  adherence: 'Соблюдение плана',
  data_sufficiency: 'Достаточность данных',
  wellbeing: 'Сон и настроение',
  check_ins: 'Еженедельные check-ins',
  methodology: 'Методика и ограничения',
};

function idempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `report-handoff-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function trainerName(trainer: CurrentTrainer | null): string {
  if (!trainer) return 'Текущий тренер не доступен';
  return trainer.full_name || trainer.username || 'Текущий тренер';
}

function statusLabel(status: ReportHandoff['delivery_status']): string {
  return {
    delivered: 'Доставлено в центр уведомлений',
    pending: 'Ожидает обработки',
    failed: 'Не удалось доставить',
  }[status];
}

function sectionIds(report: ProgressReport): string[] {
  const sections = [
    'overview',
    'training',
    'cardio',
    'body',
    'nutrition',
    'adherence',
    'data_sufficiency',
    'check_ins',
    'methodology',
  ];
  if (report.program) sections.splice(2, 0, 'program');
  if (report.wellbeing) sections.splice(sections.indexOf('check_ins'), 0, 'wellbeing');
  return sections;
}

function coverageText(report: ProgressReport): string[] {
  const lines = [
    `Дневник питания: ${report.nutrition.summary.coverage_percent}% покрытия (${report.nutrition.summary.logged_days} дней из ${report.nutrition.summary.eligible_days}).`,
  ];
  if (report.wellbeing) {
    lines.push(
      `Сон и настроение: ${report.wellbeing.coverage_percent}% покрытия (${report.wellbeing.recorded_days} дней из ${report.wellbeing.eligible_days}).`,
    );
  }
  return lines;
}

function formatCreatedAt(value: string, timezone: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: timezone,
  }).format(new Date(value));
}

function ReportHandoffPanelContent({
  dateFrom,
  dateTo,
  loading,
  period,
  report,
  trainer,
}: ReportHandoffPanelProps) {
  const queryClient = useQueryClient();
  const [handoffKey, setHandoffKey] = useState(idempotencyKey);
  const [retryKey, setRetryKey] = useState<string | null>(null);
  const [lastHandoff, setLastHandoff] = useState<ReportHandoff | null>(null);
  const trainerLabel = trainerName(trainer);
  const sections = useMemo(() => sectionIds(report), [report]);
  const coverage = useMemo(() => coverageText(report), [report]);
  const history = useQuery({
    queryKey: ['report-handoffs'],
    queryFn: () => api<ReportHandoff[]>('/api/v1/report-handoffs'),
  });
  const createMutation = useMutation({
    mutationFn: (key: string) =>
      api<ReportHandoff>('/api/v1/report-handoffs', {
        method: 'POST',
        body: {
          period,
          ...(period === 'custom' ? { date_from: dateFrom, date_to: dateTo } : {}),
        },
        headers: { 'Idempotency-Key': key },
      }),
    onSuccess: (result) => {
      setLastHandoff(result);
      setRetryKey(null);
      trackGrowthEvent('share_created');
      void queryClient.invalidateQueries({ queryKey: ['report-handoffs'] });
    },
  });
  const retryMutation = useMutation({
    mutationFn: ({ handoffId, key }: { handoffId: number; key: string }) =>
      api<ReportHandoff>(`/api/v1/report-handoffs/${handoffId}/retry`, {
        method: 'POST',
        headers: { 'Idempotency-Key': key },
      }),
    onSuccess: (result) => {
      setLastHandoff(result);
      void queryClient.invalidateQueries({ queryKey: ['report-handoffs'] });
    },
  });
  const retryHandoff = (handoff: ReportHandoff) => {
    const nextRetryKey = idempotencyKey();
    setLastHandoff(handoff);
    setRetryKey(nextRetryKey);
    retryMutation.mutate({ handoffId: handoff.id, key: nextRetryKey });
  };

  const mutationError = createMutation.error ?? retryMutation.error;
  const isPending = createMutation.isPending || retryMutation.isPending;
  const send = (forceNewVersion = false) => {
    if (loading) return;
    if (forceNewVersion) {
      const nextKey = idempotencyKey();
      setHandoffKey(nextKey);
      setLastHandoff(null);
      setRetryKey(null);
      retryMutation.reset();
      createMutation.reset();
      createMutation.mutate(nextKey);
      return;
    }
    if (lastHandoff?.delivery_status === 'failed') {
      const nextRetryKey = retryKey ?? idempotencyKey();
      if (!retryKey) setRetryKey(nextRetryKey);
      retryMutation.mutate({ handoffId: lastHandoff.id, key: nextRetryKey });
      return;
    }
    createMutation.mutate(handoffKey);
  };

  return (
    <section
      className="progress-report-handoff report-screen-only"
      aria-labelledby="report-handoff-title"
    >
      <header className="progress-report-handoff__header">
        <div>
          <span className="eyebrow">Осознанная отправка</span>
          <h2 id="report-handoff-title">Отправить отчёт текущему тренеру</h2>
          <p>
            Тренер откроет живой авторизованный отчёт. Если вы измените данные позже, при следующем
            открытии будут показаны актуальные факты за этот период.
          </p>
        </div>
        <span className="progress-report-handoff__live">Живые данные</span>
      </header>

      <div className="progress-report-handoff__preview">
        <div>
          <span className="progress-report-handoff__label">Субъект</span>
          <strong>{report.subject.name}</strong>
        </div>
        <div>
          <span className="progress-report-handoff__label">Период</span>
          <strong>
            {report.period_start} — {report.period_end}
          </strong>
        </div>
        <div>
          <span className="progress-report-handoff__label">Покрытие</span>
          {coverage.map((line) => (
            <strong key={line}>{line}</strong>
          ))}
        </div>
        <div>
          <span className="progress-report-handoff__label">Разделы</span>
          <ul>
            {sections.map((section) => (
              <li key={section}>{sectionLabels[section] ?? section}</li>
            ))}
          </ul>
        </div>
      </div>

      <fieldset className="progress-report-handoff__recipient">
        <legend>Получатель</legend>
        {trainer ? (
          <label>
            <input
              aria-label={trainerLabel}
              checked
              readOnly
              name="report-handoff-trainer"
              type="radio"
            />
            <span>
              <strong>{trainerLabel}</strong>
              <small>Единственный текущий тренер, подтверждённый связью</small>
            </span>
          </label>
        ) : (
          <EmptyState
            title="Нет доступного текущего тренера"
            text="Отправка станет доступна после подтверждения активной связи."
          />
        )}
      </fieldset>

      <div className="progress-report-handoff__actions">
        <Button
          disabled={!trainer || loading || isPending || lastHandoff?.delivery_status === 'pending'}
          onClick={() => send(lastHandoff?.delivery_status === 'delivered')}
          type="button"
        >
          {isPending
            ? 'Отправляем…'
            : lastHandoff?.delivery_status === 'failed'
              ? 'Повторить отправку'
              : lastHandoff?.delivery_status === 'delivered'
                ? 'Отправить обновлённую версию'
                : 'Отправить отчёт тренеру'}
        </Button>
        {lastHandoff && (
          <p className="progress-report-handoff__status" role="status">
            {statusLabel(lastHandoff.delivery_status)} · попытка {lastHandoff.delivery_attempt}
          </p>
        )}
      </div>
      {mutationError && (
        <p className="progress-report-handoff__error" role="alert">
          {(mutationError as Error).message}
        </p>
      )}

      <div className="progress-report-handoff__history">
        <h3>История отправок</h3>
        {history.isLoading ? (
          <p className="muted">Загружаем историю…</p>
        ) : history.error ? (
          <p className="progress-report-handoff__error" role="alert">
            {(history.error as Error).message}
          </p>
        ) : !history.data?.length ? (
          <EmptyState
            title="Отправок пока нет"
            text="Здесь появятся подтверждённые отправки отчётов."
          />
        ) : (
          <ul>
            {history.data.map((item) => (
              <li key={item.id}>
                <span>
                  {item.period_start} — {item.period_end} ·{' '}
                  {item.trainer.full_name || item.trainer.username || 'Тренер'}
                </span>
                <small>
                  {statusLabel(item.delivery_status)} ·{' '}
                  {formatCreatedAt(item.created_at, item.timezone)}
                </small>
                {item.delivery_status === 'failed' && (
                  <Button
                    aria-label={`Повторить отправку отчёта за период ${item.period_start} — ${item.period_end}`}
                    disabled={isPending}
                    onClick={() => retryHandoff(item)}
                    type="button"
                    variant="secondary"
                  >
                    Повторить отправку
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export function ReportHandoffPanel(props: ReportHandoffPanelProps) {
  const selectionKey = `${props.trainer?.id ?? 'none'}:${props.period}:${props.dateFrom}:${props.dateTo}:${props.report.period_start}:${props.report.period_end}`;
  return <ReportHandoffPanelContent key={selectionKey} {...props} />;
}
