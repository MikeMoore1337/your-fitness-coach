import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { CoachReviewWorkspace, CoachTask } from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';

function randomKey(prefix: string): string {
  const id =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;
  return `${prefix}-${id}`;
}

function dateLabel(value: string | null | undefined): string {
  if (!value) return 'Нет данных';
  return new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function dateTimeLabel(value: string): string {
  return new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function valueLabel(value: number | null | undefined, suffix = ''): string {
  return value == null ? 'Нет данных' : `${value}${suffix}`;
}

function statusLabel(state: CoachReviewWorkspace['state']): string {
  return state === 'available'
    ? 'Данные собраны'
    : state === 'partial'
      ? 'Часть данных недоступна'
      : 'Данных пока нет';
}

function taskStateLabel(task: CoachTask): string {
  return task.state === 'completed' ? 'Подтверждено' : 'Открыто';
}

function FactGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="coach-review-workspace__group">
      <h3>{title}</h3>
      <dl>{children}</dl>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function CoachReviewWorkspace({
  clientId,
  timezone = 'Europe/Moscow',
  enabled = true,
}: {
  clientId: number;
  timezone?: string | null;
  enabled?: boolean;
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const [response, setResponse] = useState('');
  const [followUpTitle, setFollowUpTitle] = useState('');
  const [followUpDueAt, setFollowUpDueAt] = useState('');
  const [proposalReason, setProposalReason] = useState('');
  const [proposalDueAt, setProposalDueAt] = useState('');
  const [nextReviewDueAt, setNextReviewDueAt] = useState('');

  const workspace = useQuery<CoachReviewWorkspace>({
    queryKey: queryKeys.trainer.clientReviewWorkspace(clientId),
    queryFn: () => api<CoachReviewWorkspace>(`/api/v1/coach/clients/${clientId}/review-workspace`),
    enabled,
    retry: false,
  });

  const reviewMutation = useMutation({
    mutationFn: () => {
      const checkIn = workspace.data?.current_check_in;
      if (!checkIn) throw new Error('Нет недельного итога для проверки');
      const followUp =
        followUpTitle.trim() && followUpDueAt
          ? {
              follow_up_title: followUpTitle.trim(),
              follow_up_due_at: followUpDueAt,
              follow_up_timezone: timezone || 'Europe/Moscow',
            }
          : {};
      return api(`/api/v1/coach/check-ins/${checkIn.id}/review`, {
        method: 'POST',
        body: { response: response.trim() || null, ...followUp },
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.trainer.clientReviewWorkspace(clientId),
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.checkInReviews('pending') }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.checkInReviews('reviewed') }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.inbox }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.tasks }),
      ]);
      toast('Проверка недельного итога сохранена');
    },
    onError: (error) =>
      toast(error instanceof Error ? error.message : 'Не удалось сохранить проверку', 'error'),
  });

  const taskMutation = useMutation({
    mutationFn: ({
      kind,
      title,
      dueAt,
      reason,
      sourceKind,
      sourceId,
    }: {
      kind: CoachTask['kind'];
      title: string;
      dueAt: string;
      reason: string;
      sourceKind: CoachTask['source_kind'];
      sourceId: number;
    }) =>
      api<CoachTask>('/api/v1/coach/tasks', {
        method: 'POST',
        headers: { 'Idempotency-Key': randomKey('review-workspace') },
        body: {
          client_id: clientId,
          title,
          due_at: dueAt,
          timezone: timezone || 'Europe/Moscow',
          kind,
          source_kind: sourceKind,
          source_id: sourceId,
          reason,
        },
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.trainer.clientReviewWorkspace(clientId),
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.tasks }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.inbox }),
      ]);
      toast('Действие тренера зафиксировано');
    },
    onError: (error) =>
      toast(error instanceof Error ? error.message : 'Не удалось зафиксировать действие', 'error'),
  });

  const confirmMutation = useMutation({
    mutationFn: (taskId: number) =>
      api<CoachTask>(`/api/v1/coach/tasks/${taskId}/state`, {
        method: 'PATCH',
        body: { state: 'completed' },
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.trainer.clientReviewWorkspace(clientId),
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.tasks }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.inbox }),
      ]);
      toast('Предложение отмечено подтверждённым');
    },
    onError: (error) =>
      toast(error instanceof Error ? error.message : 'Не удалось подтвердить предложение', 'error'),
  });

  if (!enabled) return null;
  if (workspace.isPending) return <LoadingState label="Собираем рабочее место проверки…" />;
  if (workspace.error) {
    return (
      <ErrorState
        message="Рабочее место проверки временно недоступно. Остальные данные клиента продолжают работать."
        retry={() => void workspace.refetch()}
      />
    );
  }
  const data = workspace.data;
  if (!data) return <EmptyState title="Рабочее место проверки пусто" />;
  const current = data.current_check_in;
  const previous = data.previous_check_in;
  const meaningfulChanges = data.meaningful_changes ?? [];
  const privateNotes = data.private_notes ?? [];
  const programProposals = data.actions.program_proposals ?? [];
  const nextReviews = data.actions.next_reviews ?? [];
  const actionPending =
    reviewMutation.isPending || taskMutation.isPending || confirmMutation.isPending;

  return (
    <section
      className="coach-review-workspace coach-review-workspace--client"
      data-testid="coach-review-workspace"
    >
      <Card
        className="coach-review-workspace__intro"
        collapsible={false}
        title="Рабочее место проверки"
        description="Один срез данных клиента для следующего ручного решения тренера. Система ничего не меняет и не отправляет от имени тренера."
        actions={
          <Badge tone={data.state === 'available' ? 'success' : 'warning'}>
            {statusLabel(data.state)}
          </Badge>
        }
      >
        <div className="coach-review-workspace__check-ins">
          <span>Предыдущий итог: {previous ? dateLabel(previous.submitted_on) : 'нет'}</span>
          <span>Текущий итог: {current ? dateLabel(current.submitted_on) : 'нет'}</span>
          <span>
            Статус проверки:{' '}
            {data.actions.review_status === 'reviewed'
              ? 'проверен'
              : current
                ? 'ожидает проверки'
                : 'нет итога'}
          </span>
        </div>

        <div className="coach-review-workspace__groups">
          <FactGroup title="Тренировочные факты">
            <Fact
              label="Завершено"
              value={valueLabel(data.training_actuals.completed_workouts, ' тренировок')}
            />
            <Fact
              label="План"
              value={valueLabel(data.training_actuals.planned_workouts, ' тренировок')}
            />
            <Fact
              label="Соблюдение плана"
              value={valueLabel(data.training_actuals.adherence_percent, '%')}
            />
            <Fact
              label="Нагрузка / восстановление"
              value={`${valueLabel(data.training_actuals.training_load, '/5')} · ${valueLabel(data.training_actuals.recovery, '/5')}`}
            />
          </FactGroup>
          <FactGroup title="Прогрессия">
            <Fact
              label="Объём"
              value={valueLabel(data.progression_facts.training_volume_kg, ' кг')}
            />
            <Fact
              label="Новые личные рекорды"
              value={valueLabel(data.progression_facts.new_personal_records)}
            />
          </FactGroup>
          <FactGroup title="Питание">
            <Fact label="Дни с дневником" value={valueLabel(data.nutrition.logged_days)} />
            <Fact label="Полные дни" value={valueLabel(data.nutrition.complete_days)} />
            <Fact
              label="Калории"
              value={`${valueLabel(data.nutrition.average_calories, ' ккал')} / цель ${valueLabel(data.nutrition.target_calories, ' ккал')}`}
            />
            <Fact
              label="Белок"
              value={`${valueLabel(data.nutrition.average_protein_g, ' г')} / цель ${valueLabel(data.nutrition.target_protein_g, ' г')}`}
            />
          </FactGroup>
          <FactGroup title="Замеры">
            <Fact label="Вес" value={valueLabel(data.measurements.weight_kg, ' кг')} />
            <Fact
              label="Изменение веса"
              value={valueLabel(data.measurements.weight_change_kg, ' кг')}
            />
            <Fact label="Талия" value={valueLabel(data.measurements.waist_cm, ' см')} />
            <Fact label="Последний замер" value={dateLabel(data.measurements.latest_measured_on)} />
          </FactGroup>
        </div>

        <section
          className="coach-review-workspace__changes"
          aria-labelledby="coach-review-workspace-changes-title"
        >
          <div className="coach-os-section-heading">
            <div>
              <span className="eyebrow">Сравнение с предыдущим итогом</span>
              <h3 id="coach-review-workspace-changes-title">Значимые изменения</h3>
            </div>
            <Badge>{meaningfulChanges.length}</Badge>
          </div>
          {!meaningfulChanges.length ? (
            <p className="muted">Сопоставимых изменений пока нет.</p>
          ) : (
            <div className="coach-review-workspace__change-list">
              {meaningfulChanges.map((change) => (
                <div key={change.key}>
                  <span>{change.label}</span>
                  <strong>
                    {valueLabel(change.previous)} → {valueLabel(change.current)}
                  </strong>
                  <small>
                    {change.reason} · недельный итог · {dateLabel(change.occurred_at)}
                  </small>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="coach-review-workspace__program" aria-label="Текущая программа">
          <span className="eyebrow">Текущая программа</span>
          {data.current_program ? (
            <p>
              <strong>{data.current_program.title}</strong> ·{' '}
              {data.current_program.workouts_completed}/{data.current_program.workouts_total}{' '}
              тренировок · ревизия {data.current_program.current_revision_number}
            </p>
          ) : (
            <p className="muted">Активной программы нет.</p>
          )}
        </section>

        {privateNotes.length > 0 && (
          <section
            className="coach-review-workspace__private-notes"
            aria-label="Приватные заметки тренера"
          >
            <div className="coach-os-section-heading">
              <div>
                <span className="eyebrow">Только для тренера</span>
                <h3>Приватные заметки</h3>
              </div>
              <Badge tone="neutral">Не видны клиенту</Badge>
            </div>
            {privateNotes.map((note) => (
              <blockquote key={note.session_id}>
                <p>{note.text}</p>
                <footer>{dateTimeLabel(note.starts_at_utc)}</footer>
              </blockquote>
            ))}
          </section>
        )}

        <section
          className="coach-review-workspace__actions"
          aria-labelledby="coach-review-workspace-actions-title"
        >
          <div className="coach-os-section-heading">
            <div>
              <span className="eyebrow">Ручные действия</span>
              <h3 id="coach-review-workspace-actions-title">Ответ и следующий шаг</h3>
            </div>
          </div>
          {current ? (
            <div className="coach-review-workspace__action-form">
              <label className="field">
                <span>Ответ тренера</span>
                <textarea
                  className="ui-input"
                  maxLength={2000}
                  onChange={(event) => setResponse(event.target.value)}
                  placeholder="Зафиксируйте следующий шаг…"
                  rows={3}
                  value={response}
                />
              </label>
              <div className="coach-review-card__follow-up">
                <label className="field">
                  <span>Что проверить позже (необязательно)</span>
                  <input
                    className="ui-input"
                    maxLength={240}
                    onChange={(event) => setFollowUpTitle(event.target.value)}
                    placeholder="Например, проверить следующую тренировку"
                    value={followUpTitle}
                  />
                </label>
                <label className="field">
                  <span>Срок · {timezone || 'Europe/Moscow'}</span>
                  <input
                    className="ui-input"
                    onChange={(event) => setFollowUpDueAt(event.target.value)}
                    type="datetime-local"
                    value={followUpDueAt}
                  />
                </label>
              </div>
              <Button
                disabled={actionPending}
                onClick={() => reviewMutation.mutate()}
                type="button"
              >
                {reviewMutation.isPending ? 'Сохраняем…' : 'Отметить итог проверенным'}
              </Button>
            </div>
          ) : (
            <EmptyState
              title="Недельного итога для проверки нет"
              text="Факты появятся после отправки клиентом."
            />
          )}

          <div className="coach-review-workspace__task-actions">
            <div className="coach-review-workspace__task-card">
              <h4>Предложение изменения программы</h4>
              <label className="field">
                <span>Основание предложения</span>
                <textarea
                  className="ui-input"
                  maxLength={240}
                  onChange={(event) => setProposalReason(event.target.value)}
                  placeholder="Что нужно обсудить или изменить?"
                  rows={2}
                  value={proposalReason}
                />
              </label>
              <label className="field">
                <span>Срок предложения</span>
                <input
                  className="ui-input"
                  onChange={(event) => setProposalDueAt(event.target.value)}
                  type="datetime-local"
                  value={proposalDueAt}
                />
              </label>
              <Button
                disabled={actionPending || !proposalDueAt || !proposalReason.trim()}
                onClick={() =>
                  taskMutation.mutate({
                    kind: 'update_program',
                    title: 'Подготовить изменение программы',
                    dueAt: proposalDueAt,
                    reason: proposalReason.trim(),
                    sourceKind: data.current_program ? 'program' : 'client',
                    sourceId: data.current_program?.id ?? clientId,
                  })
                }
                type="button"
                variant="secondary"
              >
                Зафиксировать предложение
              </Button>
            </div>
            <div className="coach-review-workspace__task-card">
              <h4>Следующая проверка</h4>
              <label className="field">
                <span>Дата следующей проверки</span>
                <input
                  className="ui-input"
                  onChange={(event) => setNextReviewDueAt(event.target.value)}
                  type="datetime-local"
                  value={nextReviewDueAt}
                />
              </label>
              <Button
                disabled={actionPending || !nextReviewDueAt}
                onClick={() =>
                  taskMutation.mutate({
                    kind: 'schedule_follow_up',
                    title: 'Провести следующую проверку клиента',
                    dueAt: nextReviewDueAt,
                    reason: 'Следующая проверка запланирована тренером из рабочего места проверки.',
                    sourceKind: 'client',
                    sourceId: clientId,
                  })
                }
                type="button"
                variant="secondary"
              >
                Запланировать проверку
              </Button>
            </div>
          </div>

          {(programProposals.length > 0 || nextReviews.length > 0) && (
            <div className="coach-review-workspace__action-history">
              <h4>История действий</h4>
              {[...programProposals, ...nextReviews].map((task) => (
                <div className="coach-review-workspace__history-row" key={task.id}>
                  <div>
                    <strong>{task.title}</strong>
                    <span>
                      {task.reason || 'Без дополнительного описания'} · до{' '}
                      {dateTimeLabel(task.due_at)}
                    </span>
                  </div>
                  {task.kind === 'update_program' && task.state === 'open' ? (
                    <Button
                      disabled={actionPending}
                      onClick={() => confirmMutation.mutate(task.id)}
                      type="button"
                      variant="secondary"
                    >
                      Подтвердить
                    </Button>
                  ) : (
                    <Badge tone={task.state === 'completed' ? 'success' : 'neutral'}>
                      {taskStateLabel(task)}
                    </Badge>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </Card>
    </section>
  );
}
