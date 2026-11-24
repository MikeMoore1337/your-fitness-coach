import { useEffect, useRef, type MouseEvent, type PointerEvent, type RefObject } from 'react';

type Navigation = {
  onPrevious(): void;
  onNext(): void;
  nextDisabled?: boolean;
  previousDisabled?: boolean;
};
type Gesture = {
  id: number;
  x: number;
  y: number;
  lastX: number;
  lastTime: number;
  velocity: number;
  base: number;
  scrollStart: number;
  scrollMax: number;
  axis: 'horizontal' | 'vertical' | null;
  scroll: boolean;
  moved: boolean;
};

export function useWeekSwipe<T extends HTMLElement>(
  railRef: RefObject<T | null>,
  navigation?: Navigation,
  options?: { durationMs?: number; disableReducedMotionDrag?: boolean; maxOffsetPx?: number },
) {
  const gesture = useRef<Gesture | null>(null);
  const animation = useRef<Animation | null>(null);
  const suppressClick = useRef(false);

  const visualOffset = (offset: number) => {
    if (
      options?.disableReducedMotionDrag &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    )
      return 0;
    const limit = options?.maxOffsetPx;
    return limit == null ? offset : Math.max(-limit, Math.min(limit, offset));
  };

  useEffect(() => {
    const reset = () => {
      gesture.current = null;
      animation.current?.cancel();
      animation.current = null;
      if (railRef.current) railRef.current.style.transform = '';
    };
    const onVisibility = () => {
      if (document.hidden) reset();
    };
    window.addEventListener('resize', reset);
    window.visualViewport?.addEventListener('resize', reset);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.removeEventListener('resize', reset);
      window.visualViewport?.removeEventListener('resize', reset);
      document.removeEventListener('visibilitychange', onVisibility);
      reset();
    };
  }, [railRef]);

  const settle = (rail: T, from: number) => {
    rail.style.transform = '';
    if (!from || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || !rail.animate)
      return;
    animation.current = rail.animate(
      [{ transform: `translateX(${from}px)` }, { transform: 'translateX(0)' }],
      { duration: options?.durationMs ?? 260, easing: 'cubic-bezier(0.2, 0, 0, 1)' },
    );
    animation.current.onfinish = () => {
      animation.current = null;
    };
  };

  const onPointerDown = (event: PointerEvent<T>) => {
    if (!navigation || event.isPrimary === false || event.button !== 0 || gesture.current) return;
    if (event.clientX < 24 || event.clientX > window.innerWidth - 24) return;
    const rail = event.currentTarget;
    const transform = getComputedStyle(rail).transform;
    const base =
      transform && transform !== 'none' && typeof DOMMatrixReadOnly !== 'undefined'
        ? new DOMMatrixReadOnly(transform).m41
        : 0;
    animation.current?.cancel();
    animation.current = null;
    rail.style.transform = base ? `translateX(${base}px)` : '';
    suppressClick.current = false;
    gesture.current = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      lastX: event.clientX,
      lastTime: performance.now(),
      velocity: 0,
      base,
      scrollStart: rail.scrollLeft,
      scrollMax: Math.max(0, rail.scrollWidth - rail.clientWidth),
      axis: null,
      scroll: false,
      moved: false,
    };
  };

  const onPointerMove = (event: PointerEvent<T>) => {
    const current = gesture.current;
    if (!current || current.id !== event.pointerId || !navigation) return;
    const dx = event.clientX - current.x;
    const dy = event.clientY - current.y;
    const rail = event.currentTarget;
    if (!current.axis && Math.max(Math.abs(dx), Math.abs(dy)) > 8) {
      current.axis = Math.abs(dx) > Math.abs(dy) * 1.25 ? 'horizontal' : 'vertical';
      if (current.axis === 'horizontal') {
        current.scroll =
          dx < 0 ? current.scrollStart < current.scrollMax - 1 : current.scrollStart > 1;
        rail.setPointerCapture?.(event.pointerId);
      }
    }
    if (current.axis !== 'horizontal') return;
    current.moved = true;
    if (current.scroll) {
      rail.scrollLeft = current.scrollStart - dx;
      return;
    }
    const now = performance.now();
    current.velocity = (event.clientX - current.lastX) / Math.max(1, now - current.lastTime);
    current.lastX = event.clientX;
    current.lastTime = now;
    const disabled = dx < 0 ? navigation.nextDisabled : navigation.previousDisabled;
    const offset = disabled ? Math.max(-24, Math.min(24, dx * 0.2)) : dx;
    rail.style.transform = `translateX(${visualOffset(current.base + offset)}px)`;
  };

  const finish = (event: PointerEvent<T>, cancelled: boolean) => {
    const current = gesture.current;
    if (!current || current.id !== event.pointerId) return;
    gesture.current = null;
    const rail = event.currentTarget;
    if (!current.moved) {
      settle(rail, current.base);
      return;
    }
    suppressClick.current = true;
    if (current.scroll) return;
    const dx = event.clientX - current.x;
    const disabled = dx < 0 ? navigation?.nextDisabled : navigation?.previousDisabled;
    const valid =
      !cancelled &&
      !disabled &&
      (Math.abs(dx) > Math.min(90, rail.clientWidth * 0.25) ||
        (Math.abs(dx) > 24 &&
          Math.abs(current.velocity) > 0.5 &&
          Math.sign(current.velocity) === Math.sign(dx)));
    const offset = disabled ? Math.max(-24, Math.min(24, dx * 0.2)) : dx;
    if (valid) {
      if (dx < 0) navigation?.onNext();
      else navigation?.onPrevious();
    }
    settle(rail, visualOffset(current.base + offset));
  };

  const onClickCapture = (event: MouseEvent<T>) => {
    if (suppressClick.current && event.detail !== 0) {
      event.preventDefault();
      event.stopPropagation();
      suppressClick.current = false;
    }
  };

  return {
    onPointerDown,
    onPointerMove,
    onPointerUp: (event: PointerEvent<T>) => finish(event, false),
    onPointerCancel: (event: PointerEvent<T>) => finish(event, true),
    onLostPointerCapture: (event: PointerEvent<T>) => {
      if (event.target === event.currentTarget) finish(event, true);
    },
    onClickCapture,
  };
}
