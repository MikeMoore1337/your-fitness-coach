import { useEffect } from 'react';

/** One delegated listener; no React state, polling or work while the pointer is idle. */
export function GlassInteractions() {
  useEffect(() => {
    const enabled = window.matchMedia(
      '(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)',
    );
    let surface: HTMLElement | null = null;
    let frame = 0;
    let x = 0;
    let y = 0;

    const reset = () => {
      cancelAnimationFrame(frame);
      frame = 0;
      surface?.style.removeProperty('--glass-x');
      surface?.style.removeProperty('--glass-y');
      surface = null;
    };
    const update = () => {
      frame = 0;
      if (!surface?.isConnected || document.hidden) return reset();
      const rect = surface.getBoundingClientRect();
      if (!rect.width || !rect.height) return reset();
      // Narrow optical travel keeps the highlight from behaving like a spotlight.
      const horizontal = 35 + Math.max(0, Math.min(1, (x - rect.left) / rect.width)) * 30;
      const vertical = 10 + Math.max(0, Math.min(1, (y - rect.top) / rect.height)) * 20;
      surface.style.setProperty('--glass-x', `${horizontal.toFixed(1)}%`);
      surface.style.setProperty('--glass-y', `${vertical.toFixed(1)}%`);
    };
    const move = (event: PointerEvent) => {
      if (!enabled.matches || event.pointerType === 'touch' || document.hidden) return reset();
      const next =
        event.target instanceof Element
          ? event.target.closest<HTMLElement>('[data-glass-interactive]')
          : null;
      if (next?.matches(':disabled, [aria-disabled="true"]')) return reset();
      if (next !== surface) {
        reset();
        surface = next;
      }
      if (!surface) return;
      x = event.clientX;
      y = event.clientY;
      if (!frame) frame = requestAnimationFrame(update);
    };
    const leave = (event: PointerEvent) => {
      if (
        surface &&
        (!(event.relatedTarget instanceof Node) || !surface.contains(event.relatedTarget))
      )
        reset();
    };
    document.addEventListener('pointermove', move, { passive: true });
    document.addEventListener('pointerout', leave, { passive: true });
    document.addEventListener('scroll', reset, { passive: true, capture: true });
    document.addEventListener('visibilitychange', reset);
    window.addEventListener('blur', reset);
    enabled.addEventListener('change', reset);
    return () => {
      reset();
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerout', leave);
      document.removeEventListener('scroll', reset, true);
      document.removeEventListener('visibilitychange', reset);
      window.removeEventListener('blur', reset);
      enabled.removeEventListener('change', reset);
    };
  }, []);
  return null;
}
