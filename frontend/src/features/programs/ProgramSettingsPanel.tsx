import { useEffect, useId, useRef, type ReactNode } from 'react';
import { DisclosureIcon } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useTelegramOverlayBackButton } from '../../shared/telegram/useTelegramOverlayBackButton';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  valid: boolean;
  children: ReactNode;
};

/** A focused draft view, not a second save endpoint or a separate program state. */
export function ProgramSettingsPanel({ open, onOpenChange, valid, children }: Props) {
  const id = useId();
  const panelRef = useRef<HTMLDetailsElement>(null);
  const triggerRef = useRef<HTMLElement>(null);
  useTelegramOverlayBackButton(open, () => onOpenChange(false));

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => {
      triggerRef.current?.focus({ preventScroll: true });
      panelRef.current?.scrollIntoView?.({ block: 'start' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  const finish = () => {
    // Native field validation also covers optional fields while keeping the draft intact.
    const fields = panelRef.current?.querySelectorAll<HTMLInputElement | HTMLSelectElement>(
      'input, select',
    );
    for (const field of fields ?? []) {
      if (field.disabled || field.checkValidity()) continue;
      let ancestor: HTMLElement | null = field.parentElement;
      while (ancestor && ancestor !== panelRef.current) {
        if (ancestor instanceof HTMLDetailsElement) ancestor.open = true;
        ancestor = ancestor.parentElement;
      }
      field.reportValidity();
      return;
    }
    if (!valid) return;
    onOpenChange(false);
    window.requestAnimationFrame(() => triggerRef.current?.focus({ preventScroll: true }));
  };

  return (
    <details
      ref={panelRef}
      className="program-builder-settings compact-disclosure"
      open={open}
      onToggle={(event) => {
        if (event.currentTarget.open !== open) onOpenChange(event.currentTarget.open);
      }}
      onKeyDown={(event) => {
        if (
          open &&
          event.key === 'Escape' &&
          !event.defaultPrevented &&
          event.currentTarget.contains(event.target as Node)
        ) {
          event.preventDefault();
          event.stopPropagation();
          onOpenChange(false);
        }
      }}
    >
      <summary
        ref={triggerRef}
        className="yfc-disclosure-summary"
        aria-expanded={open}
        aria-controls={id}
        onClick={(event) => {
          event.preventDefault();
          onOpenChange(!open);
        }}
      >
        {open && <Icon name="arrow-left" size={20} />}
        <span>
          <strong>Настройки программы</strong>
          {!open && <small>Цель, уровень и расписание</small>}
        </span>
        <DisclosureIcon />
      </summary>
      <div id={id} className="program-builder-settings__body stack">
        {children}
        <div className="program-builder-settings__save">
          <p className="muted">Настройки войдут в программу при её сохранении.</p>
          <button type="button" disabled={!valid} onClick={finish}>
            Сохранить настройки
          </button>
        </div>
      </div>
    </details>
  );
}
