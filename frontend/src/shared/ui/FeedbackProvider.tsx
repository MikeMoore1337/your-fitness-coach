import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { CloseIcon } from './common';
import { useModalA11y } from './useModalA11y';
import { useMotionPresence } from './useMotionPresence';
import { glassProps } from './Glass';

interface ConfirmOptions {
  title: string;
  message: string;
  confirmText?: string;
  danger?: boolean;
}

interface FeedbackValue {
  toast(message: string, type?: 'success' | 'error'): void;
  confirm(options: ConfirmOptions): Promise<boolean>;
}

interface ConfirmState extends ConfirmOptions {
  resolve(value: boolean): void;
}

const FeedbackContext = createContext<FeedbackValue | null>(null);

export function FeedbackProvider({ children }: { children: React.ReactNode }) {
  const [toastState, setToastState] = useState<{ message: string; type: string } | null>(null);
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);
  const toastTimer = useRef<number | null>(null);
  const toastPresence = useMotionPresence({
    closingAnimationName: 'toast-out',
    openingAnimationName: 'toast-in',
  });

  const dismissToast = useCallback(() => {
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = null;
    toastPresence.hide();
  }, [toastPresence]);

  const toast = useCallback(
    (message: string, type: 'success' | 'error' = 'success') => {
      if (toastTimer.current) window.clearTimeout(toastTimer.current);
      setToastState({ message, type });
      toastPresence.show();
      toastTimer.current = window.setTimeout(toastPresence.hide, type === 'error' ? 7000 : 3200);
    },
    [toastPresence],
  );

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => setConfirmState({ ...options, resolve })),
    [],
  );

  const finishConfirm = (value: boolean) => {
    confirmState?.resolve(value);
    setConfirmState(null);
  };
  const confirmPanelRef = useModalA11y<HTMLDivElement>(Boolean(confirmState), () =>
    finishConfirm(false),
  );

  const value = useMemo(() => ({ toast, confirm }), [toast, confirm]);
  return (
    <FeedbackContext.Provider value={value}>
      {children}
      {toastState && toastPresence.present && (
        <div
          className={`toast${toastState.type === 'error' ? ' error' : ''}`}
          {...glassProps('tinted')}
          data-motion-phase={toastPresence.phase}
          role={
            toastPresence.phase === 'closing'
              ? undefined
              : toastState.type === 'error'
                ? 'alert'
                : 'status'
          }
          aria-live={toastState.type === 'error' ? 'assertive' : 'polite'}
          aria-hidden={toastPresence.phase === 'closing' || undefined}
          inert={toastPresence.phase === 'closing'}
          onAnimationEnd={toastPresence.onAnimationEnd}
        >
          <span>{toastState.message}</span>
          <button
            type="button"
            className="toast__close"
            aria-label="Закрыть сообщение"
            onClick={dismissToast}
          >
            <CloseIcon />
          </button>
        </div>
      )}
      {confirmState && (
        <div
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-title"
          aria-describedby="confirm-message"
        >
          <button
            className="modal__backdrop"
            aria-label="Закрыть"
            onClick={() => finishConfirm(false)}
          />
          <div
            {...glassProps('tinted')}
            ref={confirmPanelRef}
            className="modal__panel card"
            tabIndex={-1}
          >
            <h3 id="confirm-title" className="modal__title">
              {confirmState.title}
            </h3>
            <p id="confirm-message" className="modal__body muted">
              {confirmState.message}
            </p>
            <div className="modal__actions toolbar wrap">
              <button type="button" className="secondary" onClick={() => finishConfirm(false)}>
                Отмена
              </button>
              <button
                type="button"
                className={confirmState.danger === false ? '' : 'btn-danger'}
                onClick={() => finishConfirm(true)}
              >
                {confirmState.confirmText ?? 'Подтвердить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </FeedbackContext.Provider>
  );
}

export function useFeedback(): FeedbackValue {
  const value = useContext(FeedbackContext);
  if (!value) throw new Error('useFeedback must be used inside FeedbackProvider');
  return value;
}
