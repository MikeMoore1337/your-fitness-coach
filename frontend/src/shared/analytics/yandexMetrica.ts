import {
  GROWTH_GOAL_IDS,
  isGrowthGoalEvent,
  productAnalyticsEnvironment,
  subscribeProductAnalyticsProvider,
  type ProductAnalyticsEnvironment,
  type ProductAnalyticsProvider,
  type ProductEventEnvelope,
} from './productEvents';

export const YANDEX_METRICA_COUNTER_ID = 112530718 as const;
const YANDEX_METRICA_SCRIPT_SRC =
  `https://mc.yandex.ru/metrika/tag.js?id=${YANDEX_METRICA_COUNTER_ID}` as const;
const YANDEX_METRICA_DISABLED_CLASS = 'ym-hide-content';
const MAX_SAFE_TITLE_LENGTH = 160;
const YANDEX_METRICA_PRODUCTION_HOSTNAMES = new Set([
  'your-fitness-coach.ru',
  'www.your-fitness-coach.ru',
  'app.your-fitness-coach.ru',
  'www.app.your-fitness-coach.ru',
]);

type YandexMetricaMethod = 'init' | 'hit' | 'reachGoal' | 'params';
type YandexMetricaCommand = [number, YandexMetricaMethod, ...unknown[]];
type YandexMetricaFunction = ((
  counterId: number,
  method: YandexMetricaMethod,
  ...args: unknown[]
) => void) & {
  a?: YandexMetricaCommand[];
  l?: number;
};

type YandexWindow = Window & { ym?: YandexMetricaFunction };

let initialized = false;
let lastTrackedUrl: string | null = null;

function yandexEnvironment(): ProductAnalyticsEnvironment {
  return productAnalyticsEnvironment(import.meta.env.MODE);
}

export function isYandexMetricaProductionHost(hostname: string): boolean {
  return YANDEX_METRICA_PRODUCTION_HOSTNAMES.has(hostname.trim().toLowerCase().replace(/\.$/, ''));
}

function isYandexMetricaRuntimeEnabled(): boolean {
  return (
    yandexEnvironment() === 'production' && isYandexMetricaProductionHost(window.location.hostname)
  );
}

function safePath(path: string): string {
  if (!path.startsWith('/')) return window.location.pathname || '/';
  try {
    const parsed = new URL(path, window.location.origin);
    if (parsed.origin !== window.location.origin) return window.location.pathname || '/';
    return parsed.pathname || '/';
  } catch {
    return window.location.pathname || '/';
  }
}

export function safeYandexUrl(path: string): string {
  const pathname = safePath(path);
  return new URL(pathname, window.location.origin).toString();
}

export function safeYandexReferrer(value: string): string | undefined {
  if (!value.trim()) return undefined;
  try {
    const parsed = new URL(value);
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
      return undefined;
    }
    return `${parsed.origin}${parsed.pathname || '/'}`;
  } catch {
    return undefined;
  }
}

function safeTitle(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const normalized = [...value]
    .map((character) => {
      const code = character.charCodeAt(0);
      return code < 32 || code === 127 ? ' ' : character;
    })
    .join('')
    .trim();
  return normalized ? normalized.slice(0, MAX_SAFE_TITLE_LENGTH) : undefined;
}

function ensureYandexFunction(): YandexMetricaFunction {
  const target = window as YandexWindow;
  if (typeof target.ym === 'function') return target.ym;
  const queued: YandexMetricaFunction = (...args) => {
    queued.a = queued.a ?? [];
    queued.a.push(args as YandexMetricaCommand);
  };
  queued.l = Date.now();
  target.ym = queued;
  return queued;
}

function ensureYandexScript(): void {
  if (document.querySelector<HTMLScriptElement>(`script[src="${YANDEX_METRICA_SCRIPT_SRC}"]`)) {
    return;
  }
  const script = document.createElement('script');
  script.async = true;
  script.defer = true;
  script.src = YANDEX_METRICA_SCRIPT_SRC;
  script.dataset.yfcYandexMetrica = 'true';
  document.head.append(script);
}

function invokeYandex(method: YandexMetricaMethod, ...args: unknown[]): void {
  ensureYandexFunction()(YANDEX_METRICA_COUNTER_ID, method, ...args);
}

export function createYandexMetricaProvider(
  sendCommand: (method: YandexMetricaMethod, ...args: unknown[]) => void,
  environment: ProductAnalyticsEnvironment,
): ProductAnalyticsProvider {
  return {
    name: 'yandex_metrica',
    environment,
    isDeliveryAllowed: () => environment === 'production',
    send(event: ProductEventEnvelope): void {
      if (isGrowthGoalEvent(event.name)) {
        sendCommand('reachGoal', GROWTH_GOAL_IDS[event.name]);
        return;
      }
      const params: Record<string, string> = {
        yfc_event: event.name,
        yfc_surface: event.surface,
      };
      switch (event.name) {
        case 'section_navigation_selected':
          params.yfc_from_section = event.from_section;
          params.yfc_to_section = event.to_section;
          break;
        case 'next_action_shown':
        case 'next_action_clicked':
        case 'next_action_completed':
          params.yfc_action_kind = event.action_kind;
          params.yfc_position = event.position;
          break;
      }
      sendCommand('params', params);
    },
  };
}

export function initializeYandexMetrica(): void {
  if (initialized || !isYandexMetricaRuntimeEnabled()) return;
  initialized = true;
  ensureYandexFunction();
  invokeYandex('init', {
    ssr: true,
    defer: true,
    webvisor: true,
    clickmap: true,
    ecommerce: 'dataLayer',
    referrer: safeYandexReferrer(document.referrer),
    url: safeYandexUrl(window.location.pathname),
    accurateTrackBounce: true,
    trackLinks: true,
    sendTitle: false,
  });
  ensureYandexScript();
  subscribeProductAnalyticsProvider(createYandexMetricaProvider(invokeYandex, 'production'));
}

export function trackYandexPageView(path: string, title?: string): void {
  if (!isYandexMetricaRuntimeEnabled()) return;
  initializeYandexMetrica();
  const url = safeYandexUrl(path);
  if (url === lastTrackedUrl) return;
  const referer = lastTrackedUrl ?? safeYandexReferrer(document.referrer);
  const options: { title?: string; referer?: string } = {};
  const safePageTitle = safeTitle(title);
  if (safePageTitle) options.title = safePageTitle;
  if (referer) options.referer = referer;
  invokeYandex('hit', url, options);
  lastTrackedUrl = url;
}

export function setYandexPrivateContentMask(masked: boolean): void {
  document.getElementById('root')?.classList.toggle(YANDEX_METRICA_DISABLED_CLASS, masked);
}
