import { api } from '../api/client';

export const FIRST_TOUCH_ATTRIBUTION_STORAGE_KEY = 'yfc:analytics:first-touch:v1';

export type FirstTouchSource = 'google' | 'yandex' | 'telegram' | 'direct' | 'referral' | 'utm';

export type FirstTouchAttribution = {
  first_touch_source: FirstTouchSource;
  first_touch_medium: string;
  first_touch_campaign: string | null;
  first_landing_path: string;
  first_referrer: string | null;
  first_touch_at: string;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  utm_content: string | null;
  utm_term: string | null;
};

const ATTRIBUTION_KEYS = [
  'first_touch_source',
  'first_touch_medium',
  'first_touch_campaign',
  'first_landing_path',
  'first_referrer',
  'first_touch_at',
  'utm_source',
  'utm_medium',
  'utm_campaign',
  'utm_content',
  'utm_term',
] as const;
const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'] as const;
const TOKEN_PATTERN = /^[a-z0-9][a-z0-9._~-]{0,127}$/i;
const CONTACT_PATTERN = /(?:@|\+?\d[\d(). -]{6,}\d)/;
const JWT_PATTERN = /^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$/;
const TELEGRAM_HOSTS = ['t.me', 'telegram.me', 'telegram.org'];

function safeToken(value: string | null, maxLength = 128): string | null {
  const normalized = value?.trim().toLowerCase() ?? '';
  if (
    !normalized ||
    normalized.length > maxLength ||
    !TOKEN_PATTERN.test(normalized) ||
    CONTACT_PATTERN.test(normalized) ||
    JWT_PATTERN.test(normalized)
  ) {
    return null;
  }
  return normalized;
}

function safePath(pathname: string): string {
  if (!pathname.startsWith('/') || pathname.includes('?') || pathname.includes('#')) return '/';
  const clean = [...pathname]
    .filter((character) => {
      const code = character.charCodeAt(0);
      return code >= 0x20 && code !== 0x7f;
    })
    .join('')
    .slice(0, 256);
  if (clean.startsWith('/join/')) return '/join';
  return clean || '/';
}

export function safeAttributionReferrer(value: string | null): string | null {
  if (!value?.trim()) return null;
  try {
    const parsed = new URL(value);
    if (
      !['http:', 'https:'].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      [...value].some((character) => character.charCodeAt(0) < 0x20)
    ) {
      return null;
    }
    const path = safePath(parsed.pathname || '/');
    return `${parsed.origin}${path}`.slice(0, 512);
  } catch {
    return null;
  }
}

function readUtmParams(
  url: URL,
): Pick<
  FirstTouchAttribution,
  'utm_source' | 'utm_medium' | 'utm_campaign' | 'utm_content' | 'utm_term'
> {
  return {
    utm_source: safeToken(url.searchParams.get('utm_source')),
    utm_medium: safeToken(url.searchParams.get('utm_medium')),
    utm_campaign: safeToken(url.searchParams.get('utm_campaign')),
    utm_content: safeToken(url.searchParams.get('utm_content')),
    utm_term: safeToken(url.searchParams.get('utm_term')),
  };
}

function isKnownHost(hostname: string, hosts: readonly string[]): boolean {
  const normalized = hostname.toLowerCase().replace(/^www\./, '');
  return hosts.some((host) => normalized === host || normalized.endsWith(`.${host}`));
}

function searchSource(hostname: string): Exclude<FirstTouchSource, 'utm'> | null {
  const normalized = hostname.toLowerCase().replace(/^www\./, '');
  if (
    normalized === 'google.com' ||
    normalized.startsWith('google.') ||
    normalized.endsWith('.google.com')
  ) {
    return 'google';
  }
  if (
    normalized === 'yandex.ru' ||
    normalized.startsWith('yandex.') ||
    normalized.endsWith('.yandex.ru') ||
    normalized === 'ya.ru'
  ) {
    return 'yandex';
  }
  return null;
}

function telegramRuntimePresent(): boolean {
  return Boolean(window.Telegram?.WebApp?.initData?.trim());
}

export function buildFirstTouchAttribution(
  locationHref: string,
  referrer: string | null,
  now = new Date(),
  isTelegram = telegramRuntimePresent(),
): FirstTouchAttribution {
  const location = new URL(locationHref, window.location.origin);
  const safeReferrer = safeAttributionReferrer(referrer);
  const utm = readUtmParams(location);
  const hasUtm = UTM_KEYS.some((key) => utm[key] !== null);
  const referrerUrl = safeReferrer ? new URL(safeReferrer) : null;
  const referrerHost = referrerUrl?.hostname.toLowerCase() ?? '';
  const searchReferrer = searchSource(referrerHost);
  const source: FirstTouchSource = hasUtm
    ? 'utm'
    : isTelegram || isKnownHost(referrerHost, TELEGRAM_HOSTS)
      ? 'telegram'
      : searchReferrer
        ? searchReferrer
        : safeReferrer
          ? 'referral'
          : 'direct';
  const medium =
    utm.utm_medium ??
    (source === 'google' || source === 'yandex'
      ? 'organic'
      : source === 'telegram'
        ? 'telegram'
        : source === 'referral'
          ? 'referral'
          : 'none');

  return {
    first_touch_source: source,
    first_touch_medium: safeToken(medium, 64) ?? 'unknown',
    first_touch_campaign: utm.utm_campaign,
    first_landing_path: safePath(location.pathname),
    first_referrer: safeReferrer,
    first_touch_at: now.toISOString(),
    ...utm,
  };
}

function hasExactAttributionKeys(value: Record<string, unknown>): boolean {
  const keys = Object.keys(value);
  return (
    keys.length === ATTRIBUTION_KEYS.length && ATTRIBUTION_KEYS.every((key) => keys.includes(key))
  );
}

function isValidAttribution(value: unknown): value is FirstTouchAttribution {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  if (!hasExactAttributionKeys(record)) return false;
  if (
    !['google', 'yandex', 'telegram', 'direct', 'referral', 'utm'].includes(
      String(record.first_touch_source),
    )
  ) {
    return false;
  }
  if (
    typeof record.first_touch_medium !== 'string' ||
    safeToken(record.first_touch_medium, 64) !== record.first_touch_medium ||
    typeof record.first_landing_path !== 'string' ||
    safePath(record.first_landing_path) !== record.first_landing_path ||
    typeof record.first_touch_at !== 'string' ||
    !Number.isFinite(Date.parse(record.first_touch_at))
  ) {
    return false;
  }
  if (
    record.first_touch_campaign !== null &&
    (typeof record.first_touch_campaign !== 'string' ||
      safeToken(record.first_touch_campaign) !== record.first_touch_campaign)
  ) {
    return false;
  }
  if (
    record.first_referrer !== null &&
    (typeof record.first_referrer !== 'string' ||
      safeAttributionReferrer(record.first_referrer) !== record.first_referrer)
  ) {
    return false;
  }
  return UTM_KEYS.every((key) => {
    const item = record[key];
    return item === null || (typeof item === 'string' && safeToken(item) === item);
  });
}

function readStoredAttribution(): FirstTouchAttribution | null {
  try {
    const raw = window.localStorage.getItem(FIRST_TOUCH_ATTRIBUTION_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (isValidAttribution(parsed)) return parsed;
    window.localStorage.removeItem(FIRST_TOUCH_ATTRIBUTION_STORAGE_KEY);
  } catch {
    // Attribution must never make the app unusable when storage is unavailable.
  }
  return null;
}

export function captureFirstTouchAttribution(): FirstTouchAttribution {
  const stored = readStoredAttribution();
  if (stored) return stored;
  const attribution = buildFirstTouchAttribution(window.location.href, document.referrer || null);
  try {
    window.localStorage.setItem(FIRST_TOUCH_ATTRIBUTION_STORAGE_KEY, JSON.stringify(attribution));
  } catch {
    // The in-memory result still supports the current page and later auth sync attempts.
  }
  return attribution;
}

let syncPromise: Promise<void> | null = null;

export function syncFirstTouchAttribution(userId: number | null | undefined): Promise<void> {
  if (!userId || syncPromise) return syncPromise ?? Promise.resolve();
  const stored = readStoredAttribution();
  if (!stored) return Promise.resolve();

  syncPromise = (async () => {
    try {
      await api<void>('/api/v1/me/acquisition', {
        method: 'POST',
        body: stored,
        retryAuth: false,
      });
      try {
        window.localStorage.removeItem(FIRST_TOUCH_ATTRIBUTION_STORAGE_KEY);
      } catch {
        // A successful server bind is sufficient; storage cleanup is best effort.
      }
    } catch {
      // Keep the immutable record for a later authenticated retry.
    } finally {
      syncPromise = null;
    }
  })();
  return syncPromise;
}
