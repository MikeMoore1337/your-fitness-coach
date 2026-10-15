import { useEffect, useRef } from 'react';
import { useNavigation } from '../shared/navigation/router';

export function useQuickAddReturn(to: string): () => void {
  const { navigate, path, search } = useNavigation();
  const pendingFocus = useRef(false);

  useEffect(() => {
    if (!pendingFocus.current) return;
    if (`${path}${search}` !== to) {
      pendingFocus.current = false;
      return;
    }
    let observer: MutationObserver | undefined;
    let retryFrame: number | undefined;
    let retryAttempts = 0;
    const retryFocus = () => {
      if (!pendingFocus.current || retryFrame !== undefined || retryAttempts >= 30) return;
      retryAttempts += 1;
      retryFrame = window.requestAnimationFrame(() => {
        retryFrame = undefined;
        restoreFocus();
      });
    };
    const restoreFocus = () => {
      if (!pendingFocus.current) return;
      const trigger = document.querySelector<HTMLElement>('[data-testid="quick-add-trigger"]');
      if (
        !trigger ||
        trigger.closest('[inert]') ||
        getComputedStyle(trigger).visibility === 'hidden'
      ) {
        retryFocus();
        return;
      }
      trigger.focus({ preventScroll: true });
      if (document.activeElement !== trigger) return;
      pendingFocus.current = false;
      observer?.disconnect();
    };
    restoreFocus();
    if (pendingFocus.current) {
      observer = new MutationObserver(restoreFocus);
      observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['class', 'data-yfc-keyboard', 'inert', 'open', 'style'],
      });
      retryFocus();
    }
    return () => {
      observer?.disconnect();
      if (retryFrame !== undefined) window.cancelAnimationFrame(retryFrame);
      pendingFocus.current = false;
    };
  }, [path, search, to]);

  return () => {
    pendingFocus.current = true;
    navigate(to, true);
  };
}
