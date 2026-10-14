import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { useAuth } from '../../app/AuthProvider';
import { api, ApiError } from '../../shared/api/client';
import type {
  AccountExportStatus,
  OAuthLinkCreate,
  TelegramLinkCreate,
} from '../../shared/api/types';
import { Badge, Button, CloseIcon, DisclosureIcon, Field, Input } from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { Icon } from '../../shared/ui/Icon';
import { downloadAccountExport } from './downloadAccountExport';
import { OAuthProviderButton } from '../auth/OAuthButtons';

const PROVIDER_LABELS: Record<string, string> = {
  telegram: 'Telegram',
  google: 'Google',
  yandex: 'Яндекс',
  vk: 'VK ID',
  apple: 'Apple',
  password: 'Почта и пароль',
};
const DELETE_CONFIRMATION = 'УДАЛИТЬ';

function linkingErrorMessage(reason: unknown): string {
  if (reason instanceof ApiError && reason.status === 409) {
    return 'Этот способ уже связан с аккаунтом. Автоматическое объединение недоступно.';
  }
  return 'Не удалось подготовить привязку. Проверьте соединение и попробуйте снова.';
}

function exportErrorMessage(status: AccountExportStatus | undefined): string {
  if (status?.error_code === 'archive_too_large') {
    return 'История превышает безопасный размер архива. Обратитесь в поддержку — данные не удалены.';
  }
  return 'Не удалось подготовить архив. Данные не изменены; можно повторить попытку.';
}

function expiryLabel(value: string | null | undefined): string {
  if (!value) return '';
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

export function AccountPrivacy() {
  const { user, config, logout, reloadUser } = useAuth();
  const { toast, confirm } = useFeedback();
  const queryClient = useQueryClient();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletePhrase, setDeletePhrase] = useState('');
  const deletePanelRef = useModalA11y<HTMLDivElement>(
    deleteDialogOpen,
    () => {
      if (!deleteMutation.isPending) setDeleteDialogOpen(false);
    },
    '#account-delete-confirmation',
  );
  const linkedProviders = useMemo(
    () => new Set(user?.auth_providers ?? []),
    [user?.auth_providers],
  );
  const visibleProviders = useMemo(
    () =>
      [...new Set(['telegram', ...(config?.oauth_providers ?? []), ...linkedProviders])].filter(
        (provider) => provider !== 'password' && provider in PROVIDER_LABELS,
      ),
    [config?.oauth_providers, linkedProviders],
  );

  const exportQuery = useQuery({
    queryKey: ['account-export', user?.id],
    queryFn: () => api<AccountExportStatus>('/api/v1/me/exports/current'),
    enabled: Boolean(user),
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === 'generating' ? 2_000 : false),
  });
  const createExportMutation = useMutation({
    mutationFn: () => api<AccountExportStatus>('/api/v1/me/exports', { method: 'POST', body: {} }),
    onSuccess: (status) => {
      queryClient.setQueryData(['account-export', user?.id], status);
      trackProductEvent({ name: 'data_export_requested', surface: productEventSurface() });
    },
  });
  const downloadMutation = useMutation({
    mutationFn: async () => {
      const current = exportQuery.data;
      if (!current?.export_id || !current.filename) throw new Error('Архив ещё не готов');
      return downloadAccountExport(current.export_id, current.filename);
    },
    onSuccess: (result) => {
      if (result === 'cancelled') {
        toast('Загрузка отменена. Архив останется доступен до истечения срока.', 'error');
      } else if (result === 'telegram') {
        toast('Telegram начал загрузку архива');
      } else {
        toast('Архив скачан');
      }
    },
  });
  const telegramLinkMutation = useMutation({
    mutationFn: () =>
      api<TelegramLinkCreate>('/api/v1/me/auth/telegram-link', {
        method: 'POST',
        body: {},
      }),
    onError: () => toast('Не удалось подготовить привязку Telegram', 'error'),
  });
  const oauthLinkMutation = useMutation({
    mutationFn: async (provider: string) => ({
      provider,
      link: await api<OAuthLinkCreate>(`/api/v1/me/auth/oauth-link/${provider}`, {
        method: 'POST',
        body: {},
      }),
    }),
    onError: (_reason, provider) =>
      toast(`Не удалось подготовить привязку ${PROVIDER_LABELS[provider] ?? provider}`, 'error'),
  });
  const unlinkMutation = useMutation({
    mutationFn: (provider: string) =>
      api(`/api/v1/me/auth/identities/${provider}`, { method: 'DELETE' }),
    onSuccess: async (_response, provider) => {
      await reloadUser();
      toast(`${PROVIDER_LABELS[provider] ?? provider} отключён. Аккаунт и данные сохранены.`);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: () =>
      api<void>('/api/v1/me/account', {
        method: 'DELETE',
        body: { confirmation: 'DELETE' },
      }),
    onSuccess: async () => {
      trackProductEvent({ name: 'account_delete_completed', surface: productEventSurface() });
      setDeleteDialogOpen(false);
      toast('Аккаунт удалён');
      await logout();
    },
  });

  const startUnlink = async (provider: string) => {
    const label = PROVIDER_LABELS[provider] ?? provider;
    if (
      await confirm({
        title: `Отключить ${label}?`,
        message: `${label} больше нельзя будет использовать для входа. Аккаунт, профиль и история останутся на месте.`,
        confirmText: `Отключить ${label}`,
        danger: false,
      })
    ) {
      unlinkMutation.mutate(provider);
    }
  };

  const exportStatus = exportQuery.data;
  const exportBusy = createExportMutation.isPending || exportStatus?.status === 'generating';
  const isTelegramSurface = Boolean(window.Telegram?.WebApp?.initData?.trim());

  return (
    <>
      <section className="account-session-operation" aria-labelledby="account-session-title">
        <div>
          <h3 id="account-session-title">Текущая сессия</h3>
          <p>Выход завершит работу на этом устройстве, но не удалит аккаунт или его данные.</p>
        </div>
        <Button type="button" variant="secondary" onClick={() => void logout()}>
          Выйти из аккаунта
        </Button>
      </section>

      <details className="card profile-disclosure">
        <summary className="yfc-disclosure-summary">
          <span>
            <strong>Способы входа</strong>
            <small>
              Отключение способа входа не удаляет аккаунт. Последний способ отключить нельзя.
            </small>
          </span>
          <DisclosureIcon />
        </summary>
        <div className="profile-disclosure__body">
          {visibleProviders.map((provider) => {
            const label = PROVIDER_LABELS[provider];
            const linked = linkedProviders.has(provider);
            const lastIdentity = linked && linkedProviders.size <= 1;
            const telegramLink = provider === 'telegram' ? telegramLinkMutation.data : null;
            const oauthLink =
              oauthLinkMutation.data?.provider === provider ? oauthLinkMutation.data.link : null;
            const linkingPending =
              provider === 'telegram'
                ? telegramLinkMutation.isPending
                : oauthLinkMutation.isPending && oauthLinkMutation.variables === provider;
            const linkingError =
              provider === 'telegram'
                ? telegramLinkMutation.error
                : oauthLinkMutation.variables === provider
                  ? oauthLinkMutation.error
                  : null;
            return (
              <div className="list-row auth-method-row" key={provider} aria-busy={linkingPending}>
                <div className="list-row__main">
                  <strong>{label}</strong>
                  <span className="muted">
                    {linked
                      ? 'Подключён к текущему аккаунту.'
                      : provider === 'telegram'
                        ? 'Привязка выполняется одноразовой ссылкой и действует 10 минут.'
                        : 'После подтверждения можно будет входить этим способом в тот же профиль.'}
                  </span>
                </div>
                <div className="list-row__actions">
                  {linked ? (
                    <>
                      <Badge>Привязан</Badge>
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={lastIdentity || unlinkMutation.isPending}
                        onClick={() => void startUnlink(provider)}
                      >
                        {unlinkMutation.isPending && unlinkMutation.variables === provider
                          ? 'Отключаем…'
                          : `Отключить ${label}`}
                      </Button>
                    </>
                  ) : telegramLink ? (
                    <OAuthProviderButton
                      provider={provider}
                      href={telegramLink.telegram_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Открыть Telegram
                    </OAuthProviderButton>
                  ) : oauthLink ? (
                    <OAuthProviderButton provider={provider} href={oauthLink.oauth_url}>
                      Продолжить с {label}
                    </OAuthProviderButton>
                  ) : (
                    <OAuthProviderButton
                      provider={provider}
                      busy={linkingPending}
                      disabled={telegramLinkMutation.isPending || oauthLinkMutation.isPending}
                      onClick={() =>
                        provider === 'telegram'
                          ? telegramLinkMutation.mutate()
                          : oauthLinkMutation.mutate(provider)
                      }
                    >
                      {linkingPending ? 'Готовим переход…' : `Привязать ${label}`}
                    </OAuthProviderButton>
                  )}
                </div>
                {lastIdentity && (
                  <p className="auth-method-row__feedback" role="status">
                    Сначала привяжите другой способ входа.
                  </p>
                )}
                {linkingError && (
                  <p className="auth-method-row__feedback" role="alert">
                    {linkingErrorMessage(linkingError)}
                  </p>
                )}
                {(telegramLink || oauthLink) && (
                  <p className="auth-method-row__feedback" role="status">
                    Ссылка готова. Завершите привязку у провайдера.
                  </p>
                )}
              </div>
            );
          })}
          {unlinkMutation.isError && (
            <p className="account-inline-error" role="alert">
              {unlinkMutation.error instanceof Error
                ? unlinkMutation.error.message
                : 'Не удалось отключить способ входа.'}
            </p>
          )}
        </div>
      </details>

      <section className="account-export-region" aria-labelledby="account-export-title">
        <div className="account-export-region__head">
          <div>
            <span className="eyebrow">Переносимость данных</span>
            <h3 id="account-export-title">Копия данных</h3>
            <p>
              ZIP содержит полный JSON и CSV для замеров, питания, проверок и истории тренировок.
            </p>
          </div>
          {exportStatus?.status === 'ready' && <Badge tone="success">Готово</Badge>}
          {exportStatus?.status === 'expired' && <Badge tone="warning">Срок истёк</Badge>}
          {exportStatus?.status === 'error' && <Badge tone="danger">Ошибка</Badge>}
        </div>

        {exportQuery.isLoading ? (
          <p className="account-export-region__status" role="status">
            Проверяем готовую копию…
          </p>
        ) : exportQuery.isError ? (
          <div className="account-export-region__status" role="alert">
            <p>Не удалось проверить статус. Проверьте соединение и повторите.</p>
            <Button type="button" variant="primary" onClick={() => void exportQuery.refetch()}>
              Повторить
            </Button>
          </div>
        ) : createExportMutation.isError ? (
          <div className="account-export-region__status" role="alert">
            <p>Не удалось начать подготовку. Данные не изменены; проверьте соединение.</p>
            <Button type="button" variant="primary" onClick={() => createExportMutation.mutate()}>
              Повторить подготовку
            </Button>
          </div>
        ) : exportBusy ? (
          <p className="account-export-region__status" role="status" aria-busy="true">
            Готовим архив на сервере. Можно остаться на странице — статус восстановится после
            перезагрузки.
          </p>
        ) : exportStatus?.status === 'ready' ? (
          <div className="account-export-region__status" role="status">
            <p>
              Архив доступен до {expiryLabel(exportStatus.expires_at)}. После этого сервер удалит
              файл автоматически.
            </p>
            {isTelegramSurface && (
              <p className="muted">
                Telegram покажет системное подтверждение загрузки. Если клиент его не поддерживает,
                архив откроется через безопасную короткую ссылку.
              </p>
            )}
            {downloadMutation.isError && (
              <p className="account-inline-error" role="alert">
                Архив не скачан. Он остаётся готовым — повторите загрузку до истечения срока.
              </p>
            )}
            <div className="account-export-region__actions">
              <Button
                type="button"
                variant="primary"
                disabled={downloadMutation.isPending}
                onClick={() => downloadMutation.mutate()}
              >
                {downloadMutation.isPending ? (
                  'Начинаем загрузку…'
                ) : (
                  <>
                    <Icon name="download" size={16} /> Скачать ZIP
                  </>
                )}
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={createExportMutation.isPending}
                onClick={() => createExportMutation.mutate()}
              >
                Подготовить заново
              </Button>
            </div>
          </div>
        ) : exportStatus?.status === 'error' ? (
          <div className="account-export-region__status" role="alert">
            <p>{exportErrorMessage(exportStatus)}</p>
            <Button type="button" variant="primary" onClick={() => createExportMutation.mutate()}>
              Повторить подготовку
            </Button>
          </div>
        ) : (
          <div className="account-export-region__status">
            <p>
              Архив хранится на сервере 15 минут. Секреты входа, токены и временные файлы отчётов в
              него не входят.
            </p>
            <Button type="button" variant="primary" onClick={() => createExportMutation.mutate()}>
              Подготовить архив
            </Button>
          </div>
        )}
      </section>

      <section className="profile-danger-zone" aria-labelledby="profile-danger-title">
        <div>
          <span className="eyebrow">Необратимое действие</span>
          <h3 id="profile-danger-title">Удаление аккаунта</h3>
          <p>
            Будут удалены профиль, способы входа, личные данные, связи с тренером, уведомления и
            активные сессии. Общий каталог упражнений и продуктов останется доступен другим людям.
          </p>
        </div>
        <div className="profile-danger-zone__action">
          <Button
            type="button"
            variant="danger"
            onClick={() => {
              setDeletePhrase('');
              deleteMutation.reset();
              setDeleteDialogOpen(true);
            }}
          >
            Удалить аккаунт
          </Button>
        </div>
      </section>

      {deleteDialogOpen &&
        createPortal(
          <div
            className="modal account-delete-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="account-delete-title"
            aria-describedby="account-delete-description"
          >
            <button
              className="modal__backdrop"
              aria-label="Закрыть подтверждение удаления"
              onClick={() => {
                if (!deleteMutation.isPending) setDeleteDialogOpen(false);
              }}
            />
            <div
              ref={deletePanelRef}
              className="modal__panel account-delete-modal__panel"
              tabIndex={-1}
            >
              <button
                type="button"
                className="account-delete-modal__close"
                aria-label="Отменить удаление аккаунта"
                disabled={deleteMutation.isPending}
                onClick={() => setDeleteDialogOpen(false)}
              >
                <CloseIcon />
              </button>
              <span className="eyebrow">Удаление аккаунта</span>
              <h3 id="account-delete-title">Удалить аккаунт без возможности восстановления?</h3>
              <p id="account-delete-description">
                Выход или отключение Google/Telegram не удаляют данные. Это действие удалит сам
                аккаунт, завершит все сессии и разорвёт связи с тренером.
              </p>
              <Field
                label={`Введите ${DELETE_CONFIRMATION}, чтобы подтвердить`}
                labelFor="account-delete-confirmation"
                hint="Фраза вводится русскими заглавными буквами."
              >
                <Input
                  id="account-delete-confirmation"
                  value={deletePhrase}
                  autoComplete="off"
                  enterKeyHint="done"
                  disabled={deleteMutation.isPending}
                  onChange={(event) => setDeletePhrase(event.target.value)}
                />
              </Field>
              {deleteMutation.isError && (
                <p className="account-inline-error" role="alert">
                  {deleteMutation.error instanceof Error
                    ? deleteMutation.error.message
                    : 'Удаление не выполнено. Аккаунт и данные сохранены.'}
                </p>
              )}
              <div className="account-delete-modal__actions">
                <Button
                  type="button"
                  variant="secondary"
                  disabled={deleteMutation.isPending}
                  onClick={() => setDeleteDialogOpen(false)}
                >
                  Оставить аккаунт
                </Button>
                <Button
                  type="button"
                  variant="danger"
                  disabled={deletePhrase !== DELETE_CONFIRMATION || deleteMutation.isPending}
                  onClick={() => {
                    trackProductEvent({
                      name: 'account_delete_started',
                      surface: productEventSurface(),
                    });
                    deleteMutation.mutate();
                  }}
                >
                  {deleteMutation.isPending ? 'Удаляем аккаунт…' : 'Удалить аккаунт навсегда'}
                </Button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
