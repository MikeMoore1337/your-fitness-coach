import { TRAINER_INTENT_PATH } from './trainerIntent';

const SAFE_AUTH_PATHS = new Set(['/app', '/coach', '/admin', TRAINER_INTENT_PATH]);
const SAFE_INVITE_PATH = /^\/join\/[A-Za-z0-9_-]{20,128}$/;
const OAUTH_PROVIDERS = new Set(['telegram', 'google', 'yandex', 'vk', 'apple']);

const PROVIDER_LABELS: Record<string, string> = {
  telegram: 'Telegram',
  google: 'Google',
  yandex: 'Яндекс',
  vk: 'VK ID',
  apple: 'Apple',
};

const LOGIN_ERROR_MESSAGES: Record<string, string> = {
  unavailable: 'Этот способ входа сейчас недоступен. Выберите другой способ.',
  denied: 'Вход отменён. Выберите способ входа ещё раз.',
  invalid_state: 'Не удалось подтвердить попытку входа. Начните вход заново.',
  provider_failure: 'Сервис входа временно недоступен. Попробуйте ещё раз.',
  conflict: 'Этот аккаунт уже связан с другим пользователем.',
  blocked: 'Вход в этот аккаунт недоступен. Обратитесь в поддержку.',
};

const LINK_ERROR_MESSAGES: Record<string, string> = {
  oauth_link_unavailable: 'Этот способ входа сейчас недоступен для привязки.',
  oauth_link_denied: 'Привязка отменена. Можно попробовать ещё раз.',
  oauth_link_invalid_state: 'Не удалось подтвердить привязку. Создайте новую ссылку.',
  oauth_link_provider_failure: 'Сервис входа временно недоступен. Попробуйте позже.',
  oauth_link_conflict: 'Этот способ входа уже привязан к другому аккаунту.',
  oauth_link_blocked: 'Привязка недоступна для этого аккаунта.',
};

function safeAuthNextPath(value: string | null | undefined): string | null {
  if (!value) return null;
  const normalized = value.trim();
  if (SAFE_AUTH_PATHS.has(normalized) || SAFE_INVITE_PATH.test(normalized)) return normalized;
  return null;
}

export function safeOAuthProvider(value: string | null | undefined): string | null {
  const normalized = value?.trim().toLowerCase();
  return normalized && OAUTH_PROVIDERS.has(normalized) ? normalized : null;
}

export function currentAuthNextPath(): string | null {
  return typeof window === 'undefined' ? null : safeAuthNextPath(window.location.pathname);
}

export function oauthStartHref(provider: string, nextPath?: string | null): string | null {
  const normalizedProvider = safeOAuthProvider(provider);
  if (!normalizedProvider) return null;
  const safeNextPath = safeAuthNextPath(nextPath) ?? currentAuthNextPath();
  const query = safeNextPath ? `?next=${encodeURIComponent(safeNextPath)}` : '';
  return `/api/v1/auth/oauth/${normalizedProvider}/start${query}`;
}

export function providerLabel(provider: string | null | undefined): string {
  return (provider && PROVIDER_LABELS[provider]) || 'внешний сервис';
}

export function authRecoveryMessage(
  error: string | null | undefined,
  provider?: string | null,
): string | null {
  if (!error) return null;
  const message = LINK_ERROR_MESSAGES[error] ?? LOGIN_ERROR_MESSAGES[error];
  if (!message) return null;
  if (error === 'denied' && provider) {
    return `Вход через ${providerLabel(provider)} отменён. Выберите способ входа ещё раз.`;
  }
  return message;
}
