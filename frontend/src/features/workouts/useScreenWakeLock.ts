import { useCallback, useEffect, useRef } from 'react';
import { YFC_PLATFORM_ACTIVATED_EVENT } from '../../shared/telegram/layout';

interface ScreenWakeLockSentinel {
  released: boolean;
  release(): Promise<void>;
  addEventListener(type: 'release', listener: () => void): void;
}

interface ScreenWakeLockManager {
  request(type: 'screen'): Promise<ScreenWakeLockSentinel>;
}

interface NavigatorWithScreenWakeLock {
  wakeLock?: ScreenWakeLockManager;
}

export function useScreenWakeLock(enabled: boolean): void {
  const sentinelRef = useRef<ScreenWakeLockSentinel | null>(null);
  const requestInFlightRef = useRef(false);
  const generationRef = useRef(0);
  const enabledRef = useRef(enabled);
  const requestRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  const release = useCallback(() => {
    generationRef.current += 1;
    const sentinel = sentinelRef.current;
    sentinelRef.current = null;
    if (sentinel && !sentinel.released) {
      void sentinel.release().catch(() => undefined);
    }
  }, []);

  const request = useCallback(() => {
    if (!enabled || document.visibilityState !== 'visible' || requestInFlightRef.current) return;
    const wakeLock = (navigator as unknown as NavigatorWithScreenWakeLock).wakeLock;
    if (!wakeLock || typeof wakeLock.request !== 'function') return;
    if (sentinelRef.current && !sentinelRef.current.released) return;

    const generation = generationRef.current;
    requestInFlightRef.current = true;
    let retryOnSettled = false;
    void wakeLock
      .request('screen')
      .then((sentinel) => {
        if (
          generation !== generationRef.current ||
          !enabledRef.current ||
          document.visibilityState !== 'visible'
        ) {
          retryOnSettled =
            generation !== generationRef.current &&
            enabledRef.current &&
            document.visibilityState === 'visible';
          void sentinel.release().catch(() => undefined);
          return;
        }
        sentinelRef.current = sentinel;
        sentinel.addEventListener('release', () => {
          if (sentinelRef.current === sentinel) sentinelRef.current = null;
        });
      })
      .catch(() => {
        retryOnSettled =
          generation !== generationRef.current &&
          enabledRef.current &&
          document.visibilityState === 'visible';
      })
      .finally(() => {
        requestInFlightRef.current = false;
        if (retryOnSettled) requestRef.current();
      });
  }, [enabled]);

  useEffect(() => {
    requestRef.current = request;
    return () => {
      requestRef.current = () => undefined;
    };
  }, [request]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') request();
      else release();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener(YFC_PLATFORM_ACTIVATED_EVENT, request);
    request();

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener(YFC_PLATFORM_ACTIVATED_EVENT, request);
      release();
    };
  }, [release, request]);
}
