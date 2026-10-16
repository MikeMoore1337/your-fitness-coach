import { useCallback, useEffect, useRef, useState, type AnimationEvent } from 'react';

export type MotionPresencePhase = 'closed' | 'opening' | 'open' | 'closing';

const MOTION_STATE_DURATION_MS = 180;

interface MotionPresenceOptions {
  closingAnimationName: string;
  exitDurationMs?: number;
  openingAnimationName: string;
}

function reducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

export function useMotionPresence({
  closingAnimationName,
  exitDurationMs = MOTION_STATE_DURATION_MS,
  openingAnimationName,
}: MotionPresenceOptions) {
  const [phase, setPhase] = useState<MotionPresencePhase>('closed');
  const fallbackTimer = useRef<number | null>(null);
  const mountedRef = useRef(false);
  const present = phase !== 'closed';
  const isOpen = phase === 'opening' || phase === 'open';

  const clearFallback = useCallback(() => {
    if (fallbackTimer.current != null) globalThis.clearTimeout(fallbackTimer.current);
    fallbackTimer.current = null;
  }, []);

  const finishClosing = useCallback(() => {
    clearFallback();
    if (!mountedRef.current) return;
    setPhase('closed');
  }, [clearFallback]);

  const show = useCallback(() => {
    if (!mountedRef.current) return;
    clearFallback();
    setPhase((current) =>
      current === 'opening' || current === 'open' ? current : reducedMotion() ? 'open' : 'opening',
    );
  }, [clearFallback]);

  const hide = useCallback(() => {
    if (!mountedRef.current) return;
    setPhase((current) => {
      if (current === 'closed' || current === 'closing') return current;
      return reducedMotion() ? 'closed' : 'closing';
    });
  }, []);

  useEffect(() => {
    if (phase !== 'closing') return;
    fallbackTimer.current = window.setTimeout(finishClosing, exitDurationMs + 80);
    return clearFallback;
  }, [clearFallback, exitDurationMs, finishClosing, phase]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearFallback();
    };
  }, [clearFallback]);

  const onAnimationEnd = useCallback(
    (event: AnimationEvent<HTMLElement>) => {
      if (!mountedRef.current) return;
      if (event.animationName === openingAnimationName) {
        setPhase((current) => (current === 'opening' ? 'open' : current));
      }
      if (event.animationName === closingAnimationName) finishClosing();
    },
    [closingAnimationName, finishClosing, openingAnimationName],
  );

  return { hide, isOpen, onAnimationEnd, phase, present, show };
}
