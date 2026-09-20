const SAFE_AUTH_PATHS = new Set(['/app', '/app/report', '/coach', '/admin']);
const SAFE_JOIN_PATH = /^\/join\/[A-Za-z0-9_-]{20,128}$/;
const INTERNAL_AUTH_ORIGIN = 'https://your-fitness-coach.invalid';
const TELEGRAM_LAUNCH_PARAMS = new Set(['tgWebAppData', 'tgWebAppPlatform', 'tgWebAppVersion']);

function hasNonTransportParam(value: string, isHash = false): boolean {
  const normalized = isHash ? value.replace(/^#/, '') : value.replace(/^\?/, '');
  if (!normalized) return false;
  const params = new URLSearchParams(normalized);
  return Array.from(params.keys()).some((key) => !TELEGRAM_LAUNCH_PARAMS.has(key));
}

export function hasExplicitAppDestination(search: string, hash = ''): boolean {
  return hasNonTransportParam(search) || hasNonTransportParam(hash, true);
}

export function safeAuthNextPath(value: string | null | undefined): string {
  const normalized = value?.trim() ?? '';
  if (!normalized.startsWith('/') || normalized.startsWith('//')) return '/app';
  try {
    const parsed = new URL(normalized, INTERNAL_AUTH_ORIGIN);
    if (parsed.origin !== INTERNAL_AUTH_ORIGIN) return '/app';
    if (!SAFE_AUTH_PATHS.has(parsed.pathname) && !SAFE_JOIN_PATH.test(parsed.pathname)) {
      return '/app';
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return '/app';
  }
}

export function loginPathForNext(value: string | null | undefined): string {
  return `/login?next=${encodeURIComponent(safeAuthNextPath(value))}`;
}
