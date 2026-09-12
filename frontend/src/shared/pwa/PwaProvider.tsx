import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from 'react';
import {
  isIosInstallSurface,
  isPwaStandalone,
  isTelegramSurface,
  hasActiveWorkoutData,
  pwaIsEnabled,
  PWA_INSTALL_DISMISSAL_MS,
  PWA_SAFE_UPDATE_EVENT,
  PWA_STANDALONE_SESSION_KEY,
  PWA_VALUE_SESSION_KEY,
  readPwaInstallState,
  unregisterPwaServiceWorkers,
  writePwaInstallState,
  type BeforeInstallPromptEvent,
  type PwaInstallState,
} from './pwaRuntime';
import {
  PRODUCT_EVENT_NAME,
  productEventSurface,
  trackProductEvent,
  type PwaServiceWorkerErrorCategory,
} from '../analytics/productEvents';

interface PwaContextValue {
  enabled: boolean;
  isStandalone: boolean;
  isIosInstallSurface: boolean;
  shouldShowInstallPrompt: boolean;
  installPromptAvailable: boolean;
  installPending: boolean;
  recordAppValue(): void;
  markInstallOptionShown(): void;
  install(): Promise<void>;
  dismissInstall(): void;
  updateAvailable: boolean;
  updateBlockedByWorkout: boolean;
  applyUpdate(): void;
}

const PwaContext = createContext<PwaContextValue | null>(null);

const UPDATE_ERROR_CATEGORIES = new Set<PwaServiceWorkerErrorCategory>([
  'registration',
  'update',
  'cache',
  'navigation',
  'install',
  'activate',
]);

function isPwaServiceWorkerErrorCategory(value: unknown): value is PwaServiceWorkerErrorCategory {
  return (
    typeof value === 'string' && UPDATE_ERROR_CATEGORIES.has(value as PwaServiceWorkerErrorCategory)
  );
}

function updateInstallState(
  setState: Dispatch<SetStateAction<PwaInstallState>>,
  updater: (state: PwaInstallState) => PwaInstallState,
): void {
  setState((current) => {
    const next = updater(current);
    writePwaInstallState(next);
    return next;
  });
}

function PwaUpdateNotice() {
  const pwa = usePwa();
  if (!pwa.updateAvailable) return null;
  return (
    <aside
      data-glass=""
      data-glass-variant="tinted"
      className="pwa-update-notice"
      role="status"
      aria-live="polite"
    >
      <div>
        <strong>Доступно обновление</strong>
        <p>
          {pwa.updateBlockedByWorkout
            ? 'Оно применится после завершения активной тренировки, чтобы не прервать ввод.'
            : 'Обновление применится по вашему действию в безопасный момент.'}
        </p>
      </div>
      <button
        type="button"
        className="secondary"
        disabled={pwa.updateBlockedByWorkout}
        onClick={pwa.applyUpdate}
      >
        {pwa.updateBlockedByWorkout ? 'После тренировки' : 'Обновить'}
      </button>
    </aside>
  );
}

export function PwaProvider({ children }: { children: ReactNode }) {
  const enabled = pwaIsEnabled();
  const [standalone, setStandalone] = useState(isPwaStandalone);
  const [installState, setInstallState] = useState(readPwaInstallState);
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installPending, setInstallPending] = useState(false);
  const [installClock, setInstallClock] = useState(() => Date.now());
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [updateBlockedByWorkout, setUpdateBlockedByWorkout] = useState(false);
  const deferredPromptRef = useRef<BeforeInstallPromptEvent | null>(null);
  const waitingWorkerRef = useRef<ServiceWorker | null>(null);
  const applyingUpdateRef = useRef(false);
  const pendingUpdateRef = useRef(false);
  const installShownRef = useRef(false);
  const installAcceptedRef = useRef(false);
  const valueRecordedRef = useRef(false);
  const updateNoticeTrackedRef = useRef(false);

  const trackServiceWorkerError = useCallback((category: unknown) => {
    if (!isPwaServiceWorkerErrorCategory(category)) return;
    trackProductEvent({
      name: 'pwa_service_worker_error',
      surface: productEventSurface(),
      category,
    });
  }, []);

  const recordAppValue = useCallback(() => {
    if (valueRecordedRef.current) return;
    try {
      if (sessionStorage.getItem(PWA_VALUE_SESSION_KEY) === '1') {
        valueRecordedRef.current = true;
        return;
      }
      sessionStorage.setItem(PWA_VALUE_SESSION_KEY, '1');
    } catch {
      // A blocked session storage must not block the app or install UX.
    }
    valueRecordedRef.current = true;
    updateInstallState(setInstallState, (current) => ({
      ...current,
      appOpenCount: Math.min(10, current.appOpenCount + 1),
      qualified: current.qualified || current.appOpenCount + 1 >= 2,
    }));
  }, []);

  const markInstallOptionShown = useCallback(() => {
    if (installShownRef.current) return;
    installShownRef.current = true;
    trackProductEvent({ name: 'pwa_install_option_shown', surface: productEventSurface() });
  }, []);

  const markInstallDismissed = useCallback(() => {
    updateInstallState(setInstallState, (current) => ({
      ...current,
      dismissedUntil: Date.now() + PWA_INSTALL_DISMISSAL_MS,
    }));
    trackProductEvent({ name: 'pwa_install_option_dismissed', surface: productEventSurface() });
  }, []);

  const markInstallAccepted = useCallback(() => {
    if (installAcceptedRef.current) return;
    installAcceptedRef.current = true;
    updateInstallState(setInstallState, (current) => ({
      ...current,
      qualified: false,
      dismissedUntil: 0,
    }));
    trackProductEvent({ name: 'pwa_install_option_accepted', surface: productEventSurface() });
  }, []);

  const install = useCallback(async () => {
    const prompt = deferredPromptRef.current;
    if (!prompt || installPending) return;
    setInstallPending(true);
    try {
      await prompt.prompt();
      const choice = await prompt.userChoice;
      if (choice.outcome === 'accepted') markInstallAccepted();
      else markInstallDismissed();
    } catch {
      trackServiceWorkerError('install');
    } finally {
      deferredPromptRef.current = null;
      setDeferredPrompt(null);
      setInstallPending(false);
    }
  }, [installPending, markInstallAccepted, markInstallDismissed, trackServiceWorkerError]);

  const applyWaitingUpdate = useCallback(() => {
    const waiting = waitingWorkerRef.current;
    if (!waiting) return;
    if (hasActiveWorkoutData()) {
      pendingUpdateRef.current = true;
      setUpdateBlockedByWorkout(true);
      return;
    }
    pendingUpdateRef.current = false;
    setUpdateBlockedByWorkout(false);
    applyingUpdateRef.current = true;
    try {
      waiting.postMessage({ type: 'YFC_PWA_SKIP_WAITING' });
    } catch {
      applyingUpdateRef.current = false;
      trackServiceWorkerError('update');
    }
  }, [trackServiceWorkerError]);

  useEffect(() => {
    const remaining = installState.dismissedUntil - Date.now();
    if (remaining <= 0) return;
    const timeout = window.setTimeout(() => setInstallClock(Date.now()), remaining);
    return () => window.clearTimeout(timeout);
  }, [installState.dismissedUntil]);

  useEffect(() => {
    if (standalone) {
      try {
        if (sessionStorage.getItem(PWA_STANDALONE_SESSION_KEY) !== '1') {
          sessionStorage.setItem(PWA_STANDALONE_SESSION_KEY, '1');
          trackProductEvent({ name: 'pwa_standalone_launched', surface: productEventSurface() });
        }
      } catch {
        trackProductEvent(
          {
            name: 'pwa_standalone_launched',
            surface: productEventSurface(),
          },
          { dedupe: 'session' },
        );
      }
    }
    const media = window.matchMedia?.('(display-mode: standalone)');
    const sync = () => setStandalone(isPwaStandalone());
    media?.addEventListener?.('change', sync);
    return () => media?.removeEventListener?.('change', sync);
  }, [standalone]);

  const telegramSurface = isTelegramSurface();

  useEffect(() => {
    if (!enabled || telegramSurface) return;
    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      const prompt = event as BeforeInstallPromptEvent;
      deferredPromptRef.current = prompt;
      setDeferredPrompt(prompt);
    };
    const onAppInstalled = () => {
      deferredPromptRef.current = null;
      setDeferredPrompt(null);
      markInstallAccepted();
    };
    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt);
    window.addEventListener('appinstalled', onAppInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt);
      window.removeEventListener('appinstalled', onAppInstalled);
    };
  }, [enabled, markInstallAccepted, telegramSurface]);

  useEffect(() => {
    const onProductEvent = (event: Event) => {
      const detail = (event as CustomEvent<{ name?: string; surface?: string }>).detail;
      if (detail?.name !== 'workout_completed' || detail.surface === 'tma') return;
      updateInstallState(setInstallState, (current) => ({ ...current, qualified: true }));
    };
    window.addEventListener(PRODUCT_EVENT_NAME, onProductEvent);
    return () => window.removeEventListener(PRODUCT_EVENT_NAME, onProductEvent);
  }, []);

  useEffect(() => {
    if (!enabled) {
      void unregisterPwaServiceWorkers().catch(() => trackServiceWorkerError('registration'));
      return;
    }
    if (telegramSurface || !('serviceWorker' in navigator)) return;

    let cancelled = false;
    let registration: ServiceWorkerRegistration | null = null;
    const onMessage = (event: MessageEvent<{ type?: string; category?: string }>) => {
      if (event.data?.type === 'YFC_PWA_SW_ERROR' && event.data.category) {
        trackServiceWorkerError(event.data.category);
      }
    };
    const onControllerChange = () => {
      if (!applyingUpdateRef.current) return;
      applyingUpdateRef.current = false;
      trackProductEvent({ name: 'pwa_update_applied', surface: productEventSurface() });
      window.location.reload();
    };
    const markWaiting = (worker: ServiceWorker | null) => {
      if (!worker || cancelled) return;
      waitingWorkerRef.current = worker;
      if (navigator.serviceWorker.controller) {
        setUpdateAvailable(true);
        const workoutIsActive = hasActiveWorkoutData();
        pendingUpdateRef.current = workoutIsActive;
        setUpdateBlockedByWorkout(workoutIsActive);
        if (!updateNoticeTrackedRef.current) {
          updateNoticeTrackedRef.current = true;
          trackProductEvent({ name: 'pwa_update_available', surface: productEventSurface() });
        }
      } else {
        worker.postMessage({ type: 'YFC_PWA_SKIP_WAITING' });
      }
    };
    const onUpdateFound = () => {
      const worker = registration?.installing;
      if (!worker) return;
      const onStateChange = () => {
        if (worker.state === 'installed') markWaiting(worker);
        if (worker.state === 'redundant') trackServiceWorkerError('update');
      };
      worker.addEventListener('statechange', onStateChange);
    };

    navigator.serviceWorker.addEventListener('message', onMessage);
    navigator.serviceWorker.addEventListener('controllerchange', onControllerChange);
    const onSafeUpdate = () => {
      if (pendingUpdateRef.current && !hasActiveWorkoutData()) applyWaitingUpdate();
    };
    window.addEventListener(PWA_SAFE_UPDATE_EVENT, onSafeUpdate);

    void navigator.serviceWorker
      .register('/sw.js', { scope: '/' })
      .then((nextRegistration) => {
        if (cancelled) return;
        registration = nextRegistration;
        if (registration.waiting) markWaiting(registration.waiting);
        registration.addEventListener('updatefound', onUpdateFound);
        void registration.update().catch(() => trackServiceWorkerError('update'));
      })
      .catch(() => trackServiceWorkerError('registration'));

    return () => {
      cancelled = true;
      navigator.serviceWorker.removeEventListener('message', onMessage);
      navigator.serviceWorker.removeEventListener('controllerchange', onControllerChange);
      window.removeEventListener(PWA_SAFE_UPDATE_EVENT, onSafeUpdate);
      registration?.removeEventListener('updatefound', onUpdateFound);
    };
  }, [applyWaitingUpdate, enabled, telegramSurface, trackServiceWorkerError]);

  const isIos = isIosInstallSurface();
  const shouldShowInstallPrompt =
    enabled &&
    !telegramSurface &&
    !standalone &&
    installState.qualified &&
    installState.dismissedUntil <= installClock &&
    (Boolean(deferredPrompt) || isIos);
  const value = useMemo<PwaContextValue>(
    () => ({
      enabled,
      isStandalone: standalone,
      isIosInstallSurface: isIos,
      shouldShowInstallPrompt,
      installPromptAvailable: Boolean(deferredPrompt),
      installPending,
      recordAppValue,
      markInstallOptionShown,
      install,
      dismissInstall: markInstallDismissed,
      updateAvailable,
      updateBlockedByWorkout,
      applyUpdate: applyWaitingUpdate,
    }),
    [
      applyWaitingUpdate,
      deferredPrompt,
      enabled,
      install,
      installPending,
      isIos,
      markInstallDismissed,
      markInstallOptionShown,
      recordAppValue,
      standalone,
      shouldShowInstallPrompt,
      updateAvailable,
      updateBlockedByWorkout,
    ],
  );

  return (
    <PwaContext.Provider value={value}>
      {children}
      <PwaUpdateNotice />
    </PwaContext.Provider>
  );
}

export function usePwa(): PwaContextValue {
  const value = useContext(PwaContext);
  if (!value) throw new Error('usePwa must be used inside PwaProvider');
  return value;
}
