import { useEffect, useRef, type PointerEvent, type RefObject } from 'react';

type Drag = {
  id: number;
  x: number;
  y: number;
  base: number;
  lastY: number;
  lastTime: number;
  velocity: number;
  axis: 'vertical' | 'horizontal' | null;
};

export function useQuickAddDrag(
  panelRef: RefObject<HTMLDivElement | null>,
  open: boolean,
  onClose: () => void,
) {
  const drag = useRef<Drag | null>(null);
  const animation = useRef<Animation | null>(null);

  useEffect(() => {
    if (!open) return;
    const reset = () => {
      drag.current = null;
      animation.current?.cancel();
      animation.current = null;
      if (panelRef.current) panelRef.current.style.transform = '';
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
  }, [open, panelRef]);

  const settle = (from: number, close: boolean) => {
    const panel = panelRef.current;
    if (!panel) return;
    const target = close ? panel.offsetHeight : 0;
    panel.style.transform = '';
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || !panel.animate) {
      if (close) onClose();
      return;
    }
    const running = panel.animate(
      [{ transform: `translateY(${from}px)` }, { transform: `translateY(${target}px)` }],
      { duration: 260, easing: 'cubic-bezier(0.2, 0, 0, 1)', fill: 'forwards' },
    );
    animation.current = running;
    running.onfinish = () => {
      panel.style.transform = close ? `translateY(${target}px)` : '';
      running.cancel();
      animation.current = null;
      if (close) onClose();
    };
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!open || event.isPrimary === false || event.button !== 0 || drag.current) return;
    const panel = panelRef.current;
    if (!panel) return;
    const transform = getComputedStyle(panel).transform;
    const base =
      transform && transform !== 'none' && typeof DOMMatrixReadOnly !== 'undefined'
        ? new DOMMatrixReadOnly(transform).m42
        : 0;
    animation.current?.cancel();
    animation.current = null;
    panel.style.transform = base ? `translateY(${base}px)` : '';
    drag.current = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      base,
      lastY: event.clientY,
      lastTime: performance.now(),
      velocity: 0,
      axis: null,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    const panel = panelRef.current;
    if (!current || current.id !== event.pointerId || !panel) return;
    const dx = event.clientX - current.x;
    const dy = event.clientY - current.y;
    if (!current.axis && Math.max(Math.abs(dx), Math.abs(dy)) > 8) {
      current.axis = Math.abs(dy) > Math.abs(dx) * 1.25 ? 'vertical' : 'horizontal';
    }
    if (current.axis !== 'vertical') return;
    const now = performance.now();
    current.velocity = (event.clientY - current.lastY) / Math.max(1, now - current.lastTime);
    current.lastY = event.clientY;
    current.lastTime = now;
    const offset = Math.max(0, Math.min(panel.offsetHeight, current.base + dy));
    panel.style.transform = `translateY(${offset}px)`;
  };

  const finish = (event: PointerEvent<HTMLDivElement>, cancelled: boolean) => {
    const current = drag.current;
    const panel = panelRef.current;
    if (!current || current.id !== event.pointerId || !panel) return;
    drag.current = null;
    const offset =
      current.axis === 'vertical'
        ? Math.max(0, Math.min(panel.offsetHeight, current.base + event.clientY - current.y))
        : current.base;
    const close =
      !cancelled &&
      current.axis === 'vertical' &&
      (offset > panel.offsetHeight * 0.72 ||
        (offset > panel.offsetHeight * 0.35 && current.velocity > 0.65));
    settle(offset, close);
  };

  return {
    onPointerDown,
    onPointerMove,
    onPointerUp: (event: PointerEvent<HTMLDivElement>) => finish(event, false),
    onPointerCancel: (event: PointerEvent<HTMLDivElement>) => finish(event, true),
    onLostPointerCapture: (event: PointerEvent<HTMLDivElement>) => finish(event, true),
  };
}
