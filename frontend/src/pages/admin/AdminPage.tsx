import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AppShell } from '../../app/AppShell';
import '../../styles/react.css';
import '../../styles/design-v2.css';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';
import type {
  AdminAudit,
  AdminFunnel,
  AdminJob,
  AdminOperationReason,
  AdminRelationship,
  AdminUserDetail,
  AdminUserSearchResult,
} from '../../shared/api/types';
import { AppLink, Redirect } from '../../shared/navigation/router';
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
  Surface,
} from '../../shared/ui/common';
import './admin.css';

type AdminView = 'accounts' | 'jobs' | 'funnel' | 'audit';

const VIEW_LABELS: Record<AdminView, string> = {
  accounts: 'Аккаунты',
  jobs: 'Задачи',
  funnel: 'Агрегаты',
  audit: 'Аудит',
};

const REASON_LABELS: Record<AdminOperationReason, string> = {
  security_incident: 'Инцидент безопасности',
  abuse: 'Нарушение правил',
  account_recovery: 'Восстановление доступа',
  support_request: 'Запрос поддержки',
  relationship_safety: 'Безопасность связи тренера и клиента',
};

const AUDIT_LABELS: Record<string, string> = {
  'root.account_blocked': 'Аккаунт заблокирован',
  'root.account_unblocked': 'Аккаунт разблокирован',
  'root.trainer_capability_revoked': 'Режим тренера отозван',
  'root.trainer_capability_restored': 'Режим тренера восстановлен',
  'root.coach_relationship_ended': 'Связь тренера и клиента завершена',
  'root.account_export_retried': 'Экспорт данных запущен повторно',
  'trainer_capability.activated': 'Режим тренера включён пользователем',
  'trainer_capability.deactivated': 'Режим тренера отключён пользователем',
  'coach.relation_ended': 'Связь тренера и клиента завершена',
};

const JOB_STATUS_LABELS: Record<string, string> = {
  queued: 'В очереди',
  processing: 'Выполняется',
  sent: 'Отправлено',
  failed: 'Ошибка',
  cancelled: 'Отменено',
  generating: 'Формируется',
  ready: 'Готов',
  expired: 'Истёк',
  error: 'Ошибка',
};

const FUNNEL_LABELS: Record<AdminFunnel['stages'][number]['key'], string> = {
  registered: 'Создали аккаунт',
  profile_ready: 'Заполнили основу профиля',
  program_activated: 'Активировали программу',
  core_value_reached: 'Зафиксировали первое полезное действие',
};

function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value));
}

function userName(user: AdminUserSearchResult | AdminUserDetail): string {
  return user.display_name || user.username || `Аккаунт #${user.id}`;
}

function jobTone(status: string): 'neutral' | 'success' | 'warning' | 'danger' {
  if (status === 'ready' || status === 'sent') return 'success';
  if (status === 'failed' || status === 'error') return 'danger';
  if (status === 'processing' || status === 'generating' || status === 'queued') return 'warning';
  return 'neutral';
}

function JobRows({
  jobs,
  pending,
  onRetry,
}: {
  jobs: AdminJob[];
  pending: boolean;
  onRetry(job: AdminJob): void;
}) {
  if (!jobs.length) {
    return (
      <EmptyState title="Задач пока нет" text="Статусы появятся после операций пользователя." />
    );
  }
  return (
    <div className="admin-rows" role="list">
      {jobs.map((job) => (
        <article className="admin-row" key={job.job_id} role="listitem">
          <div className="admin-row__main">
            <strong>{job.kind === 'notification' ? 'Уведомление' : 'Экспорт данных'}</strong>
            <span className="admin-code">
              {job.job_id} · аккаунт #{job.user_id}
            </span>
            <span className="muted">
              Создано {formatDate(job.created_at)}
              {job.attempt_count != null ? ` · попыток ${job.attempt_count}` : ''}
            </span>
          </div>
          <div className="admin-row__actions">
            <Badge tone={jobTone(job.status)}>{JOB_STATUS_LABELS[job.status] ?? job.status}</Badge>
            {job.retry_allowed && job.kind === 'account_export' && (
              <Button
                disabled={pending}
                onClick={() => onRetry(job)}
                type="button"
                variant="secondary"
              >
                Повторить экспорт
              </Button>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

function AuditRows({ rows }: { rows: AdminAudit[] }) {
  if (!rows.length) {
    return <EmptyState title="Событий аудита пока нет" />;
  }
  return (
    <div className="admin-rows" role="list">
      {rows.map((row) => (
        <article className="admin-row" key={row.id} role="listitem">
          <div className="admin-row__main">
            <strong>{AUDIT_LABELS[row.action] ?? row.action}</strong>
            <span className="muted">{formatDate(row.created_at)}</span>
            <span className="admin-code">
              actor #{row.actor_user_id ?? 'system'} · target #{row.target_user_id ?? '—'} ·{' '}
              {row.resource_type} {row.resource_id ?? ''}
            </span>
          </div>
          {row.reason && <Badge>{REASON_LABELS[row.reason]}</Badge>}
        </article>
      ))}
    </div>
  );
}

function RelationshipRows({
  relationships,
  pending,
  reason,
  subject,
  onEnd,
}: {
  relationships: AdminRelationship[];
  pending: boolean;
  reason: AdminOperationReason;
  subject: string;
  onEnd(relationship: AdminRelationship): void;
}) {
  if (!relationships.length) {
    return <EmptyState title="Связей с тренером или клиентами нет" />;
  }
  return (
    <div className="admin-rows" role="list">
      {relationships.map((relationship) => (
        <article className="admin-row" key={relationship.id} role="listitem">
          <div className="admin-row__main">
            <strong>
              {relationship.account_role === 'trainer' ? 'Клиент' : 'Тренер'}:{' '}
              {relationship.counterparty_name}
            </strong>
            <span className="admin-code">
              Связь #{relationship.id} · аккаунт #{relationship.counterparty_user_id}
            </span>
            <span className="muted">
              {relationship.status === 'active' ? 'Активна' : 'Завершена'} · с{' '}
              {formatDate(relationship.accepted_at ?? relationship.created_at)}
            </span>
          </div>
          {relationship.can_end && (
            <Button
              aria-label={`Завершить связь ${subject} и ${relationship.counterparty_name}`}
              disabled={pending || !reason}
              onClick={() => onEnd(relationship)}
              type="button"
              variant="danger"
            >
              Завершить связь
            </Button>
          )}
        </article>
      ))}
    </div>
  );
}

export default function AdminPage() {
  const { user } = useAuth();
  const { confirm, toast } = useFeedback();
  const queryClient = useQueryClient();
  const [view, setView] = useState<AdminView>('accounts');
  const [searchInput, setSearchInput] = useState('');
  const [submittedSearch, setSubmittedSearch] = useState('');
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [reason, setReason] = useState<AdminOperationReason>('support_request');
  const isMiniApp = Boolean(window.Telegram?.WebApp?.initData?.trim());

  const search = useQuery({
    queryKey: ['root-admin', 'users', submittedSearch],
    queryFn: () =>
      api<AdminUserSearchResult[]>(`/api/v1/admin/users?q=${encodeURIComponent(submittedSearch)}`),
    enabled: Boolean(user?.is_root && submittedSearch),
  });
  const detail = useQuery({
    queryKey: ['root-admin', 'user', selectedUserId],
    queryFn: () => api<AdminUserDetail>(`/api/v1/admin/users/${selectedUserId}`),
    enabled: Boolean(user?.is_root && selectedUserId),
  });
  const jobs = useQuery({
    queryKey: ['root-admin', 'jobs'],
    queryFn: () => api<AdminJob[]>('/api/v1/admin/jobs'),
    enabled: Boolean(user?.is_root && view === 'jobs'),
  });
  const funnel = useQuery({
    queryKey: ['root-admin', 'funnel', 30],
    queryFn: () => api<AdminFunnel>('/api/v1/admin/funnel?period_days=30'),
    enabled: Boolean(user?.is_root && view === 'funnel'),
  });
  const audit = useQuery({
    queryKey: ['root-admin', 'audit'],
    queryFn: () => api<AdminAudit[]>('/api/v1/admin/audit'),
    enabled: Boolean(user?.is_root && view === 'audit'),
  });

  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: unknown }) =>
      api(path, { method, body }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['root-admin'] });
      toast('Операция подтверждена сервером');
    },
    onError: (error) =>
      toast(error instanceof Error ? error.message : 'Операцию выполнить не удалось', 'error'),
  });

  const selected = detail.data;
  const selectedName = selected ? userName(selected) : '';
  const selectedResult = useMemo(
    () => search.data?.find((item) => item.id === selectedUserId) ?? null,
    [search.data, selectedUserId],
  );

  if (isMiniApp) return <Redirect to="/app" />;

  if (!user?.is_root) {
    return (
      <AppShell>
        <Surface className="admin-permission" aria-labelledby="admin-permission-title">
          <span className="eyebrow">Закрытый контур</span>
          <h1 id="admin-permission-title">Root-доступ не подтверждён</h1>
          <p>
            Operational workspace доступен только владельцу с подтверждённой Telegram identity из
            server configuration. Обычный Admin-флаг не выдаёт это право.
          </p>
          <AppLink className="ui-button ui-button--secondary" to="/app">
            Вернуться в личный режим
          </AppLink>
        </Surface>
      </AppShell>
    );
  }

  const runDanger = async ({
    title,
    confirmText,
    message,
    path,
    body,
  }: {
    title: string;
    confirmText: string;
    message: string;
    path: string;
    body: unknown;
  }) => {
    if (
      await confirm({
        title,
        message: `${message} Причина: ${REASON_LABELS[reason]}.`,
        confirmText,
        danger: true,
      })
    ) {
      mutation.mutate({ path, method: 'PATCH', body });
    }
  };

  const endSelectedRelationship = async (relationship: AdminRelationship) => {
    if (
      await confirm({
        title: `Завершить связь для ${selectedName}?`,
        message: `Связь с ${relationship.counterparty_name} будет завершена без удаления истории. Причина: ${REASON_LABELS[reason]}.`,
        confirmText: 'Завершить связь',
        danger: true,
      })
    ) {
      mutation.mutate({
        path: `/api/v1/admin/relationships/${relationship.id}/end`,
        method: 'POST',
        body: { reason },
      });
    }
  };

  return (
    <AppShell>
      <div className="page-stack admin-workspace">
        <header className="admin-root-context">
          <div>
            <span className="eyebrow">ROOT · WEB ONLY</span>
            <h1>Операции поддержки и безопасности</h1>
            <p>
              Только минимальные действия с аудитом. Личные данные клиента, SQL, impersonation и
              создание других администраторов здесь недоступны.
            </p>
          </div>
          <div className="admin-root-context__actions">
            <Badge tone="danger">Root-контекст</Badge>
            <AppLink className="ui-button ui-button--secondary" to="/app">
              Личный режим
            </AppLink>
          </div>
        </header>

        <nav className="admin-view-nav" aria-label="Разделы Root workspace">
          {(Object.keys(VIEW_LABELS) as AdminView[]).map((item) => (
            <Button
              aria-current={view === item ? 'page' : undefined}
              className={view === item ? 'is-active' : ''}
              key={item}
              onClick={() => setView(item)}
              type="button"
              variant="secondary"
            >
              {VIEW_LABELS[item]}
            </Button>
          ))}
        </nav>

        {view === 'accounts' && (
          <div className="admin-account-flow">
            <Surface className="admin-search" aria-labelledby="admin-search-title">
              <div className="admin-section-heading">
                <div>
                  <span className="eyebrow">Шаг 1</span>
                  <h2 id="admin-search-title">Найти аккаунт</h2>
                </div>
                <span className="muted">Максимум 20 совпадений</span>
              </div>
              <form
                className="admin-search__form"
                onSubmit={(event) => {
                  event.preventDefault();
                  const next = searchInput.trim();
                  setSubmittedSearch(next);
                  setSelectedUserId(null);
                }}
              >
                <Field
                  hint="Internal ID, Telegram ID, @username, имя или точный linked email."
                  label="Безопасный идентификатор"
                  labelFor="admin-user-search"
                >
                  <Input
                    autoComplete="off"
                    id="admin-user-search"
                    onChange={(event) => setSearchInput(event.target.value)}
                    placeholder="Например, @mike или 5010"
                    type="search"
                    value={searchInput}
                  />
                </Field>
                <Button disabled={!searchInput.trim() || search.isFetching} type="submit">
                  {search.isFetching ? 'Ищем…' : 'Найти'}
                </Button>
              </form>

              {!submittedSearch ? (
                <EmptyState
                  title="Введите идентификатор"
                  text="Полный список пользователей намеренно не показывается."
                />
              ) : search.isLoading ? (
                <LoadingState label="Ищем аккаунт…" />
              ) : search.error ? (
                <ErrorState
                  message={(search.error as Error).message}
                  retry={() => void search.refetch()}
                />
              ) : !search.data?.length ? (
                <EmptyState
                  title="Совпадений нет"
                  text="Проверьте ID или используйте точный linked email."
                />
              ) : (
                <div className="admin-search-results" role="list" aria-label="Результаты поиска">
                  {search.data.map((item) => (
                    <button
                      aria-current={selectedUserId === item.id ? 'true' : undefined}
                      className="admin-search-result"
                      key={item.id}
                      onClick={() => setSelectedUserId(item.id)}
                      type="button"
                    >
                      <span className="admin-search-result__main">
                        <strong>{userName(item)}</strong>
                        <span className="admin-code">
                          #{item.id} · Telegram {item.telegram_user_id ?? 'не привязан'} · @
                          {item.username ?? '—'}
                        </span>
                      </span>
                      <span className="admin-search-result__status">
                        {item.is_root && <Badge tone="danger">Root</Badge>}
                        {item.is_trainer && <Badge>Trainer</Badge>}
                        <Badge tone={item.is_active ? 'success' : 'danger'}>
                          {item.is_active ? 'Активен' : 'Заблокирован'}
                        </Badge>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </Surface>

            <Surface className="admin-detail" aria-labelledby="admin-detail-title">
              {!selectedUserId ? (
                <EmptyState
                  title="Выберите найденный аккаунт"
                  text="Детали и операции откроются в одном контексте."
                />
              ) : detail.isLoading ? (
                <LoadingState
                  label={`Загружаем ${selectedResult ? userName(selectedResult) : 'аккаунт'}…`}
                />
              ) : detail.error ? (
                <ErrorState
                  message={(detail.error as Error).message}
                  retry={() => void detail.refetch()}
                />
              ) : selected ? (
                <div className="admin-detail__content">
                  <div className="admin-detail__header">
                    <div>
                      <span className="eyebrow">Шаг 2 · аккаунт #{selected.id}</span>
                      <h2 id="admin-detail-title">{selectedName}</h2>
                      <p className="admin-code">
                        Telegram {selected.telegram_user_id ?? 'не привязан'} · @
                        {selected.username ?? '—'}
                      </p>
                    </div>
                    <div className="admin-search-result__status">
                      {selected.is_root && <Badge tone="danger">Root · защищён</Badge>}
                      {selected.is_trainer && <Badge>Trainer</Badge>}
                      <Badge tone={selected.is_active ? 'success' : 'danger'}>
                        {selected.is_active ? 'Активен' : 'Заблокирован'}
                      </Badge>
                    </div>
                  </div>

                  <section className="admin-detail-section" aria-labelledby="identity-title">
                    <h3 id="identity-title">Связанные способы входа</h3>
                    {(selected.identities ?? []).length ? (
                      <dl className="admin-facts">
                        {(selected.identities ?? []).map((identity) => (
                          <div key={identity.provider}>
                            <dt>{identity.provider}</dt>
                            <dd>
                              <strong>{identity.identifier}</strong>
                              <span className="muted">
                                {identity.verified ? 'Подтверждён' : 'Не подтверждён'} · вход{' '}
                                {formatDate(identity.last_login_at)}
                              </span>
                            </dd>
                          </div>
                        ))}
                      </dl>
                    ) : (
                      <EmptyState title="Связанные способы входа не найдены" />
                    )}
                  </section>

                  <section className="admin-detail-section" aria-labelledby="operations-title">
                    <div className="admin-section-heading">
                      <div>
                        <h3 id="operations-title">Операции</h3>
                        <p className="muted">Сначала выберите фиксированную причину для аудита.</p>
                      </div>
                    </div>
                    <Field label="Причина операции" labelFor="admin-operation-reason">
                      <Select
                        id="admin-operation-reason"
                        onChange={(event) => setReason(event.target.value as AdminOperationReason)}
                        value={reason}
                      >
                        {(Object.keys(REASON_LABELS) as AdminOperationReason[]).map((item) => (
                          <option key={item} value={item}>
                            {REASON_LABELS[item]}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    {selected.is_root ? (
                      <div className="admin-protected-note" role="status">
                        Root-аккаунт нельзя блокировать, менять его Trainer capability или включать
                        в административное завершение связи.
                      </div>
                    ) : (
                      <div className="admin-operation-actions">
                        {selected.is_active ? (
                          <Button
                            disabled={mutation.isPending}
                            onClick={() =>
                              void runDanger({
                                title: `Заблокировать ${selectedName}`,
                                confirmText: 'Подтвердить блокировку',
                                message:
                                  'Все refresh-сессии будут отозваны, активные связи завершены без удаления истории.',
                                path: `/api/v1/admin/users/${selected.id}/status`,
                                body: { is_active: false, reason },
                              })
                            }
                            type="button"
                            variant="danger"
                          >
                            Заблокировать {selectedName}
                          </Button>
                        ) : (
                          <Button
                            disabled={mutation.isPending}
                            onClick={() =>
                              mutation.mutate({
                                path: `/api/v1/admin/users/${selected.id}/status`,
                                method: 'PATCH',
                                body: { is_active: true, reason },
                              })
                            }
                            type="button"
                            variant="secondary"
                          >
                            Разблокировать {selectedName}
                          </Button>
                        )}
                        {selected.is_trainer ? (
                          <Button
                            disabled={mutation.isPending}
                            onClick={() =>
                              void runDanger({
                                title: `Отозвать Trainer у ${selectedName}`,
                                confirmText: 'Подтвердить отзыв',
                                message:
                                  'Активные клиентские связи и приглашения будут безопасно завершены, история сохранится.',
                                path: `/api/v1/admin/users/${selected.id}/trainer-capability`,
                                body: { is_active: false, reason },
                              })
                            }
                            type="button"
                            variant="danger"
                          >
                            Отозвать Trainer у {selectedName}
                          </Button>
                        ) : (
                          <Button
                            disabled={mutation.isPending || !selected.is_active}
                            onClick={() =>
                              mutation.mutate({
                                path: `/api/v1/admin/users/${selected.id}/trainer-capability`,
                                method: 'PATCH',
                                body: { is_active: true, reason },
                              })
                            }
                            type="button"
                            variant="secondary"
                          >
                            Восстановить Trainer для {selectedName}
                          </Button>
                        )}
                      </div>
                    )}
                  </section>

                  <section
                    className="admin-detail-section admin-detail-section--compact"
                    aria-labelledby="relationships-title"
                  >
                    <h3 id="relationships-title">Связи тренера и клиента</h3>
                    <RelationshipRows
                      onEnd={(relationship) => void endSelectedRelationship(relationship)}
                      pending={mutation.isPending}
                      reason={reason}
                      relationships={selected.relationships ?? []}
                      subject={selectedName}
                    />
                  </section>

                  <section
                    className="admin-detail-section admin-detail-section--compact"
                    aria-labelledby="account-jobs-title"
                  >
                    <h3 id="account-jobs-title">Задачи аккаунта</h3>
                    <JobRows
                      jobs={selected.jobs ?? []}
                      onRetry={(job) =>
                        mutation.mutate({
                          path: `/api/v1/admin/exports/${job.job_id.replace('export:', '')}/retry`,
                          method: 'POST',
                        })
                      }
                      pending={mutation.isPending}
                    />
                  </section>

                  <section
                    className="admin-detail-section admin-detail-section--compact"
                    aria-labelledby="account-audit-title"
                  >
                    <h3 id="account-audit-title">История аудита</h3>
                    <AuditRows rows={selected.audit_history ?? []} />
                  </section>
                </div>
              ) : null}
            </Surface>
          </div>
        )}

        {view === 'jobs' && (
          <Surface className="admin-global-section" aria-labelledby="jobs-title">
            <div className="admin-section-heading">
              <div>
                <span className="eyebrow">Очереди без содержимого сообщений</span>
                <h2 id="jobs-title">Последние задачи</h2>
              </div>
              <Button onClick={() => void jobs.refetch()} type="button" variant="secondary">
                Обновить
              </Button>
            </div>
            <p className="muted">
              Notification retry отключён: неоднозначный ответ провайдера может создать дубликат.
              Повтор доступен только для идемпотентной генерации экспорта.
            </p>
            {jobs.isLoading ? (
              <LoadingState />
            ) : jobs.error ? (
              <ErrorState
                message={(jobs.error as Error).message}
                retry={() => void jobs.refetch()}
              />
            ) : (
              <JobRows
                jobs={jobs.data ?? []}
                onRetry={(job) =>
                  mutation.mutate({
                    path: `/api/v1/admin/exports/${job.job_id.replace('export:', '')}/retry`,
                    method: 'POST',
                  })
                }
                pending={mutation.isPending}
              />
            )}
          </Surface>
        )}

        {view === 'funnel' && (
          <Surface className="admin-global-section" aria-labelledby="funnel-title">
            <div className="admin-section-heading">
              <div>
                <span className="eyebrow">Когорта за 30 дней</span>
                <h2 id="funnel-title">Приватные агрегаты активации</h2>
              </div>
              <Badge tone="warning">Provider не подключён</Badge>
            </div>
            {funnel.isLoading ? (
              <LoadingState />
            ) : funnel.error ? (
              <ErrorState
                message={(funnel.error as Error).message}
                retry={() => void funnel.refetch()}
              />
            ) : funnel.data ? (
              <>
                <p>{funnel.data.coverage_note}</p>
                <div className="admin-funnel" role="list">
                  {funnel.data.stages.map((stage) => (
                    <div className="admin-funnel__stage" key={stage.key} role="listitem">
                      <span>{FUNNEL_LABELS[stage.key]}</span>
                      <strong>{stage.account_count}</strong>
                      <small>{stage.cohort_rate_percent}% от созданных аккаунтов</small>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </Surface>
        )}

        {view === 'audit' && (
          <Surface className="admin-global-section" aria-labelledby="audit-title">
            <div className="admin-section-heading">
              <div>
                <span className="eyebrow">Append-only история</span>
                <h2 id="audit-title">Последние события аудита</h2>
              </div>
              <Button onClick={() => void audit.refetch()} type="button" variant="secondary">
                Обновить
              </Button>
            </div>
            {audit.isLoading ? (
              <LoadingState />
            ) : audit.error ? (
              <ErrorState
                message={(audit.error as Error).message}
                retry={() => void audit.refetch()}
              />
            ) : (
              <AuditRows rows={audit.data ?? []} />
            )}
          </Surface>
        )}
      </div>
    </AppShell>
  );
}
