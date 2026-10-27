import { isTelegramLaunch } from '../telegram/launch';

export const PWA_INSTALL_STATE_KEY = 'fit_pwa_install_v1';
export const PWA_VALUE_SESSION_KEY = 'fit_pwa_value_recorded_v1';
export const PWA_STANDALONE_SESSION_KEY = 'fit_pwa_standalone_recorded_v1';
export const PWA_CACHE_PREFIX = 'yfc-pwa-';
export const PWA_SAFE_UPDATE_EVENT = 'yfc:pwa-safe-update';
export const PWA_INSTALL_DISMISSAL_MS = 30 * 24 * 60 * 60 * 1000;
export const PWA_MAX_APP_OPEN_COUNT = 10;

export interface PwaInstallState {
  appOpenCount: number;
  qualified: boolean;
  dismissedUntil: number;
}

export interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
}

const DEFAULT_INSTALL_STATE: PwaInstallState = {
  appOpenCount: 0,
  qualified: false,
  dismissedUntil: 0,
};

function finiteNonNegative(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : fallback;
}

export function readPwaInstallState(): PwaInstallState {
  try {
    const raw = localStorage.getItem(PWA_INSTALL_STATE_KEY);
    if (!raw) return { ...DEFAULT_INSTALL_STATE };
    const parsed = JSON.parse(raw) as Partial<PwaInstallState>;
    return {
      appOpenCount: Math.min(
        PWA_MAX_APP_OPEN_COUNT,
        Math.floor(finiteNonNegative(parsed.appOpenCount, 0)),
      ),
      qualified: parsed.qualified === true,
      dismissedUntil: finiteNonNegative(parsed.dismissedUntil, 0),
    };
  } catch {
    return { ...DEFAULT_INSTALL_STATE };
  }
}

export function writePwaInstallState(state: PwaInstallState): boolean {
  try {
    localStorage.setItem(PWA_INSTALL_STATE_KEY, JSON.stringify(state));
    return true;
  } catch {
    return false;
  }
}

export function isPwaStandalone(): boolean {
  try {
    if (window.matchMedia?.('(display-mode: standalone)').matches) return true;
  } catch {
    // Some embedded webviews expose an incomplete matchMedia implementation.
  }
  return (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

export function isIosInstallSurface(): boolean {
  const userAgent = navigator.userAgent || '';
  const platform = navigator.platform || '';
  return (
    /iPhone|iPad|iPod/i.test(userAgent) || (platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  );
}

export function isTelegramSurface(): boolean {
  return Boolean(window.Telegram?.WebApp?.initData?.trim()) || isTelegramLaunch(window.location);
}

export function pwaIsEnabled(): boolean {
  return import.meta.env.VITE_PWA_ENABLED !== 'false';
}

export function hasActiveWorkoutData(): boolean {
  try {
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (!key) continue;
      if (key.startsWith('fit_active_workout_rest_v1_user_')) return true;
      if (!key.startsWith('fit_active_workout_v1_user_')) continue;
      const parsed = JSON.parse(localStorage.getItem(key) || '{}') as {
        queue?: unknown;
        workout_snapshot?: { status?: unknown };
      };
      if (
        (Array.isArray(parsed.queue) && parsed.queue.length > 0) ||
        parsed.workout_snapshot?.status === 'in_progress'
      ) {
        return true;
      }
    }
  } catch {
    // Do not replace an uncertain active-workout state while applying an update.
    return true;
  }
  return false;
}

export async function unregisterPwaServiceWorkers(): Promise<void> {
  if ('serviceWorker' in navigator) {
    const registrations = await navigator.serviceWorker.getRegistrations();
    const yfcWorkerUrl = new URL('/sw.js', window.location.origin).href;
    await Promise.all(
      registrations
        .filter((registration) => {
          if (registration.scope !== `${window.location.origin}/`) return false;
          const scriptUrls = [
            registration.active?.scriptURL,
            registration.waiting?.scriptURL,
            registration.installing?.scriptURL,
          ];
          return scriptUrls.some((scriptUrl) => scriptUrl === yfcWorkerUrl);
        })
        .map((registration) => registration.unregister()),
    );
  }
  if ('caches' in window) {
    const cacheNames = await caches.keys();
    await Promise.all(
      cacheNames
        .filter((name) => name.startsWith(PWA_CACHE_PREFIX))
        .map((name) => caches.delete(name)),
    );
  }
}
