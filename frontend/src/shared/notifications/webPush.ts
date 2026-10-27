import { api, getAccessToken } from '../api/client';

export type WebPushPermission = NotificationPermission | 'unsupported';

export interface SerializedWebPushSubscription {
  endpoint: string;
  keys: {
    p256dh: string;
    auth: string;
  };
}

export function supportsWebPush(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    (typeof window.isSecureContext !== 'boolean' || window.isSecureContext) &&
    'Notification' in window &&
    'serviceWorker' in navigator &&
    'PushManager' in window
  );
}

export function webPushPermission(): WebPushPermission {
  if (!supportsWebPush()) return 'unsupported';
  return window.Notification.permission;
}

export async function getExistingWebPushSubscription(): Promise<PushSubscription | null> {
  if (!supportsWebPush()) return null;
  const registration = await navigator.serviceWorker.getRegistration('/');
  return registration?.pushManager.getSubscription() ?? null;
}

function encodeApplicationServerKey(value: string): ArrayBuffer {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
  const decoded = window.atob(padded);
  const bytes = Uint8Array.from(decoded, (character) => character.charCodeAt(0));
  return bytes.buffer;
}

export function serializeWebPushSubscription(
  subscription: PushSubscription,
): SerializedWebPushSubscription {
  const payload = subscription.toJSON();
  if (
    typeof payload.endpoint !== 'string' ||
    typeof payload.keys?.p256dh !== 'string' ||
    typeof payload.keys?.auth !== 'string'
  ) {
    throw new Error('Не удалось прочитать подписку браузера');
  }
  return {
    endpoint: payload.endpoint,
    keys: {
      p256dh: payload.keys.p256dh,
      auth: payload.keys.auth,
    },
  };
}

export async function subscribeToWebPush(
  applicationServerKey: string,
): Promise<SerializedWebPushSubscription> {
  if (!supportsWebPush()) throw new Error('Уведомления браузера недоступны');
  const registration = await navigator.serviceWorker.getRegistration('/');
  if (!registration?.active) {
    throw new Error('Сервис уведомлений ещё не готов. Обновите страницу и повторите попытку.');
  }
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: encodeApplicationServerKey(applicationServerKey),
  });
  return serializeWebPushSubscription(subscription);
}

export async function revokeWebPushSubscription(timeoutMs = 3_000): Promise<void> {
  const accessToken = getAccessToken();
  const subscription = await getExistingWebPushSubscription();
  if (!subscription) return;
  try {
    await api('/api/v1/notifications/web-push/subscription', {
      method: 'DELETE',
      body: { endpoint: subscription.endpoint },
      retryAuth: false,
      timeoutMs,
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
    });
  } finally {
    await subscription.unsubscribe().catch(() => undefined);
  }
}
