import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { WebPushConfig, WebPushStatus } from '../../shared/api/types';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import {
  isIosInstallSurface,
  isPwaStandalone,
  isTelegramSurface,
} from '../../shared/pwa/pwaRuntime';
import {
  getExistingWebPushSubscription,
  revokeWebPushSubscription,
  subscribeToWebPush,
  supportsWebPush,
  webPushPermission,
  type WebPushPermission,
} from '../../shared/notifications/webPush';
import { ErrorState, LoadingState } from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';

class SilentPermissionOutcome extends Error {
  silent = true;
}

export function WebPushSettings() {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const telegramSurface = isTelegramSurface();
  const iosHomeScreenRequired = isIosInstallSurface() && !isPwaStandalone();
  const [permission, setPermission] = useState<WebPushPermission>(webPushPermission);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const config = useQuery({
    queryKey: ['notifications', 'web-push', 'config'],
    queryFn: () => api<WebPushConfig>('/api/v1/notifications/web-push/config'),
    enabled: !telegramSurface,
  });
  const status = useQuery({
    queryKey: ['notifications', 'web-push', 'status'],
    queryFn: () => api<WebPushStatus>('/api/v1/notifications/web-push/status'),
    enabled: !telegramSurface && config.data?.enabled === true,
  });
  const localSubscription = useQuery({
    queryKey: ['notifications', 'web-push', 'local-subscription'],
    queryFn: getExistingWebPushSubscription,
    enabled: !telegramSurface && config.data?.enabled === true && supportsWebPush(),
  });

  useEffect(() => {
    if (telegramSurface || !config.data?.enabled || (!iosHomeScreenRequired && supportsWebPush())) {
      return;
    }
    trackProductEvent({ name: 'web_push_unsupported', surface: productEventSurface() });
  }, [config.data?.enabled, iosHomeScreenRequired, telegramSurface]);

  useEffect(() => {
    if (telegramSurface) return;
    const refreshPermission = () => setPermission(webPushPermission());
    refreshPermission();
    window.addEventListener('focus', refreshPermission);
    document.addEventListener('visibilitychange', refreshPermission);
    return () => {
      window.removeEventListener('focus', refreshPermission);
      document.removeEventListener('visibilitychange', refreshPermission);
    };
  }, [telegramSurface]);

  if (telegramSurface) return null;

  const handleEnable = async () => {
    if (!config.data?.application_server_key || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      trackProductEvent({ name: 'web_push_permission_prompted', surface: productEventSurface() });
      const nextPermission = await window.Notification.requestPermission();
      setPermission(nextPermission);
      if (nextPermission === 'denied') {
        trackProductEvent({ name: 'web_push_permission_denied', surface: productEventSurface() });
        throw new SilentPermissionOutcome();
      }
      if (nextPermission !== 'granted') {
        trackProductEvent({
          name: 'web_push_permission_dismissed',
          surface: productEventSurface(),
        });
        throw new SilentPermissionOutcome();
      }
      trackProductEvent({ name: 'web_push_permission_granted', surface: productEventSurface() });
      const subscription = await subscribeToWebPush(config.data.application_server_key);
      await api('/api/v1/notifications/web-push/subscription', {
        method: 'POST',
        body: subscription,
      });
      trackProductEvent({
        name: 'web_push_subscription_registered',
        surface: productEventSurface(),
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['notifications', 'web-push', 'status'] }),
        queryClient.invalidateQueries({
          queryKey: ['notifications', 'web-push', 'local-subscription'],
        }),
      ]);
      toast('Уведомления браузера включены');
    } catch (reason) {
      if (!(reason instanceof SilentPermissionOutcome)) {
        const message =
          reason instanceof Error ? reason.message : 'Не удалось включить уведомления';
        setActionError(message);
      }
    } finally {
      setBusy(false);
    }
  };

  const handleDisable = async () => {
    if (busy) return;
    setBusy(true);
    setActionError(null);
    try {
      await revokeWebPushSubscription();
      trackProductEvent({ name: 'web_push_subscription_revoked', surface: productEventSurface() });
      await queryClient.invalidateQueries({ queryKey: ['notifications', 'web-push'] });
      toast('Уведомления браузера отключены на этом устройстве');
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : 'Не удалось отключить уведомления');
    } finally {
      setBusy(false);
    }
  };

  if (config.isLoading) {
    return (
      <section className="notification-web-push" aria-label="Настройка уведомлений браузера">
        <LoadingState />
      </section>
    );
  }
  if (config.error) {
    return (
      <section className="notification-web-push" aria-label="Настройка уведомлений браузера">
        <ErrorState message="Настройка уведомлений браузера временно недоступна." />
      </section>
    );
  }
  if (!config.data?.enabled) return null;

  const currentDeviceRegistered = Boolean(localSubscription.data && status.data?.registered);
  const anotherDeviceRegistered = Boolean(status.data?.registered && !localSubscription.data);
  const permissionDenied = permission === 'denied';
  const permissionUnsupported = permission === 'unsupported' || iosHomeScreenRequired;
  const showBusyState = busy || localSubscription.isLoading || status.isLoading;

  return (
    <section className="notification-web-push" aria-labelledby="web-push-title">
      <div className="notification-web-push__heading">
        <div>
          <span className="notification-web-push__eyebrow">Когда приложение закрыто</span>
          <h3 id="web-push-title">Уведомления браузера</h3>
        </div>
        <span className="notification-channel-state">
          {currentDeviceRegistered
            ? 'Включено'
            : anotherDeviceRegistered
              ? 'Есть на другом устройстве'
              : 'По выбору'}
        </span>
      </div>
      <p className="notification-web-push__value">
        Получайте мягкое напоминание вернуться в приложение. В push нет деталей тренировки или
        питания — после открытия вы увидите центр уведомлений с обычной проверкой доступа.
      </p>

      {currentDeviceRegistered ? (
        <button
          type="button"
          className="secondary notification-web-push__action notification-web-push__action--danger"
          disabled={showBusyState}
          onClick={() => void handleDisable()}
        >
          {busy ? 'Отключаем…' : 'Отключить на этом устройстве'}
        </button>
      ) : permissionUnsupported ? (
        <p className="notification-web-push__state">
          {iosHomeScreenRequired
            ? 'На iPhone и iPad сначала добавьте приложение на экран «Домой» и откройте его оттуда. Только такой режим поддерживает Web Push.'
            : 'Этот браузер не поддерживает безопасные уведомления. Центр уведомлений в приложении продолжит работать.'}
        </p>
      ) : permissionDenied ? (
        <p className="notification-web-push__state">
          Разрешение заблокировано браузером. Разрешите уведомления в настройках сайта и обновите
          страницу.
        </p>
      ) : (
        <button
          type="button"
          className="secondary notification-web-push__action"
          disabled={showBusyState}
          onClick={() => void handleEnable()}
        >
          {busy
            ? 'Подключаем…'
            : permission === 'granted'
              ? 'Подключить этот браузер'
              : 'Включить уведомления браузера'}
        </button>
      )}

      {actionError && <p className="notification-web-push__error">{actionError}</p>}
      {status.error && (
        <p className="notification-web-push__error">
          Не удалось проверить состояние подписки. Повторите попытку позже.
        </p>
      )}
    </section>
  );
}
