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
  const present = phase !== 'closed';
  const isOpen = phase === 'opening' || phase === 'open';

  const clearFallback = useCallback(() => {
    if (fallbackTimer.current != null) window.clearTimeout(fallbackTimer.current);
    fallbackTimer.current = null;
  }, []);

  const finishClosing = useCallback(() => {
    clearFallback();
    setPhase('closed');
  }, [clearFallback]);

  const show = useCallback(() => {
    clearFallback();
    setPhase((current) =>
      current === 'opening' || current === 'open' ? current : reducedMotion() ? 'open' : 'opening',
    );
  }, [clearFallback]);

  const hide = useCallback(() => {
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

  useEffect(() => clearFallback, [clearFallback]);

  const onAnimationEnd = useCallback(
    (event: AnimationEvent<HTMLElement>) => {
      if (event.animationName === openingAnimationName) {
        setPhase((current) => (current === 'opening' ? 'open' : current));
      }
      if (event.animationName === closingAnimationName) finishClosing();
    },
    [closingAnimationName, finishClosing, openingAnimationName],
  );

  return { hide, isOpen, onAnimationEnd, phase, present, show };
}
