import { useEffect, useRef, type RefObject } from 'react';
import { useTelegramOverlayBackButton } from '../telegram/useTelegramOverlayBackButton';

let openModalCount = 0;
let originalScrollPosition = { x: 0, y: 0 };
let originalBodyStyles: Partial<CSSStyleDeclaration> = {};
let originalHtmlOverflow = '';

function lockDocumentScroll() {
  if (openModalCount === 0) {
    originalScrollPosition = { x: window.scrollX, y: window.scrollY };
    originalHtmlOverflow = document.documentElement.style.overflow;
    originalBodyStyles = {
      overflow: document.body.style.overflow,
      position: document.body.style.position,
      top: document.body.style.top,
      left: document.body.style.left,
      width: document.body.style.width,
    };
    document.documentElement.style.overflow = 'hidden';
    document.body.style.overflow = 'hidden';
    document.body.style.position = 'fixed';
    document.body.style.top = `-${originalScrollPosition.y}px`;
    document.body.style.left = `-${originalScrollPosition.x}px`;
    document.body.style.width = '100%';
  }
  openModalCount += 1;
}

function unlockDocumentScroll() {
  openModalCount = Math.max(0, openModalCount - 1);
  if (openModalCount !== 0) return;
  document.documentElement.style.overflow = originalHtmlOverflow;
  document.body.style.overflow = originalBodyStyles.overflow ?? '';
  document.body.style.position = originalBodyStyles.position ?? '';
  document.body.style.top = originalBodyStyles.top ?? '';
  document.body.style.left = originalBodyStyles.left ?? '';
  document.body.style.width = originalBodyStyles.width ?? '';
  if (originalScrollPosition.x !== 0 || originalScrollPosition.y !== 0) {
    window.scrollTo(originalScrollPosition.x, originalScrollPosition.y);
  }
}

export function useDocumentScrollLock(open: boolean) {
  useEffect(() => {
    if (!open) return;
    lockDocumentScroll();
    return unlockDocumentScroll;
  }, [open]);
}

const focusableSelector = [
  'button:not([disabled])',
  'a[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function useModalA11y<T extends HTMLElement>(
  open: boolean,
  onClose: () => void,
  initialFocusSelector?: string,
): RefObject<T | null> {
  const panelRef = useRef<T | null>(null);
  const closeRef = useRef(onClose);
  useTelegramOverlayBackButton(open, () => closeRef.current());
  useDocumentScrollLock(open);

  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const previousFocus =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      const panel = panelRef.current;
      const preferred = initialFocusSelector
        ? panel?.querySelector<HTMLElement>(initialFocusSelector)
        : null;
      const first = panel?.querySelector<HTMLElement>(focusableSelector);
      (preferred ?? first ?? panel)?.focus();
    });
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== 'Tab' || !panelRef.current) return;
      const focusable = [
        ...panelRef.current.querySelectorAll<HTMLElement>(focusableSelector),
      ].filter((element) => element.offsetParent !== null);
      if (!focusable.length) {
        event.preventDefault();
        panelRef.current.focus();
        return;
      }
      const activeIndex = focusable.indexOf(document.activeElement as HTMLElement);
      const nextIndex = event.shiftKey
        ? activeIndex <= 0
          ? focusable.length - 1
          : activeIndex - 1
        : activeIndex < 0 || activeIndex === focusable.length - 1
          ? 0
          : activeIndex + 1;
      event.preventDefault();
      focusable[nextIndex]?.focus();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('keydown', onKeyDown);
      previousFocus?.focus();
    };
  }, [initialFocusSelector, open]);

  return panelRef;
}
