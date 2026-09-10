import { useCallback, useEffect, useId, useRef, useState, type AnimationEvent } from 'react';

export type SemanticMotionPhase = 'pending' | 'enter' | 'update' | 'idle';

interface SemanticMotionOptions {
  animateInitial?: boolean;
  elementId?: string;
  observe?: boolean;
}

interface SemanticMotionBinding<T extends HTMLElement> {
  elementId: string;
  motionPhase: SemanticMotionPhase;
  motionRevision: number;
  onMotionAnimationEnd(event: AnimationEvent<T>): void;
}

function motionIsReduced(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

function motionCannotRun(): boolean {
  return (
    motionIsReduced() ||
    document.visibilityState === 'hidden' ||
    document.documentElement.dataset.yfcViewportActive === 'false'
  );
}

export function useSemanticMotion<T extends HTMLElement>(
  signature: string,
  {
    animateInitial = true,
    elementId: requestedElementId,
    observe = false,
  }: SemanticMotionOptions = {},
): SemanticMotionBinding<T> {
  const reactId = useId();
  const elementId = requestedElementId ?? `yfc-motion-${reactId.replaceAll(':', '')}`;
  const [inView, setInView] = useState(!observe);
  const [motion, setMotion] = useState<{ phase: SemanticMotionPhase; revision: number }>(() => ({
    phase: motionCannotRun() || !animateInitial ? 'idle' : 'pending',
    revision: 0,
  }));
  const previousSignature = useRef(signature);
  const hasEntered = useRef(!animateInitial);
  const restartFrame = useRef<number | null>(null);
  const fallbackTimer = useRef<number | null>(null);

  const startPhase = useCallback((phase: Exclude<SemanticMotionPhase, 'pending' | 'idle'>) => {
    if (restartFrame.current != null) window.cancelAnimationFrame(restartFrame.current);
    setMotion((current) => ({ phase: 'idle', revision: current.revision }));
    restartFrame.current = window.requestAnimationFrame(() => {
      setMotion((current) => ({ phase, revision: current.revision + 1 }));
      restartFrame.current = null;
    });
  }, []);

  useEffect(() => {
    if (!observe) return;
    const node = document.getElementById(elementId);
    if (!node || typeof IntersectionObserver === 'undefined') {
      queueMicrotask(() => setInView(true));
      return undefined;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        const visible = Boolean(entry?.isIntersecting);
        setInView(visible);
        if (!visible && hasEntered.current) {
          if (restartFrame.current != null) window.cancelAnimationFrame(restartFrame.current);
          restartFrame.current = null;
          setMotion((current) => ({ phase: 'idle', revision: current.revision }));
        }
      },
      { threshold: 0.08 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [elementId, observe]);

  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    const cancelMotion = () => {
      if (!motionCannotRun()) return;
      hasEntered.current = true;
      previousSignature.current = signature;
      if (restartFrame.current != null) window.cancelAnimationFrame(restartFrame.current);
      restartFrame.current = null;
      setMotion((current) => ({ phase: 'idle', revision: current.revision }));
    };
    query?.addEventListener?.('change', cancelMotion);
    document.addEventListener('visibilitychange', cancelMotion);
    const platformObserver = new MutationObserver(cancelMotion);
    platformObserver.observe(document.documentElement, {
      attributeFilter: ['data-yfc-viewport-active'],
    });
    return () => {
      query?.removeEventListener?.('change', cancelMotion);
      document.removeEventListener('visibilitychange', cancelMotion);
      platformObserver.disconnect();
    };
  }, [signature]);

  useEffect(() => {
    if (motionCannotRun()) {
      hasEntered.current = true;
      previousSignature.current = signature;
      queueMicrotask(() => setMotion((current) => ({ phase: 'idle', revision: current.revision })));
      return;
    }
    if (!hasEntered.current) {
      previousSignature.current = signature;
      if (!inView) return;
      hasEntered.current = true;
      queueMicrotask(() => startPhase('enter'));
      return;
    }
    if (previousSignature.current === signature) return;
    if (!inView) {
      queueMicrotask(() => setMotion((current) => ({ phase: 'idle', revision: current.revision })));
      return;
    }
    previousSignature.current = signature;
    queueMicrotask(() => startPhase('update'));
  }, [inView, signature, startPhase]);

  useEffect(
    () => () => {
      if (restartFrame.current != null) window.cancelAnimationFrame(restartFrame.current);
      if (fallbackTimer.current != null) window.clearTimeout(fallbackTimer.current);
    },
    [],
  );

  useEffect(() => {
    if (motion.phase !== 'enter' && motion.phase !== 'update') return;
    fallbackTimer.current = window.setTimeout(() => {
      setMotion((current) => ({ phase: 'idle', revision: current.revision }));
      fallbackTimer.current = null;
    }, 850);
    return () => {
      if (fallbackTimer.current != null) window.clearTimeout(fallbackTimer.current);
      fallbackTimer.current = null;
    };
  }, [motion.phase]);

  const onMotionAnimationEnd = useCallback((event: AnimationEvent<T>) => {
    if (event.target !== event.currentTarget) return;
    setMotion((current) => ({ phase: 'idle', revision: current.revision }));
  }, []);

  return {
    elementId,
    motionPhase: motion.phase,
    motionRevision: motion.revision,
    onMotionAnimationEnd,
  };
}
