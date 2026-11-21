import { useLayoutEffect, useState } from 'react';
import { AppLink } from '../shared/navigation/router';
import { glassProps } from '../shared/ui/Glass';
import { Icon, type IconName } from '../shared/ui/Icon';
import { useModalA11y } from '../shared/ui/useModalA11y';
import { useQuickAddDrag } from './useQuickAddDrag';
import {
  isQuickAddAnalyticsKind,
  productEventSurface,
  trackProductEvent,
} from '../shared/analytics/productEvents';

export interface QuickAddAction {
  key: string;
  label: string;
  detail: string;
  icon: IconName;
  to: string;
}

export const DEFAULT_QUICK_ADD_ACTIONS: ReadonlyArray<QuickAddAction> = [
  {
    key: 'food',
    label: 'Еда',
    detail: 'Быстрый ввод в дневник питания',
    icon: 'nav-nutrition',
    to: '/app?section=nutrition&quick_add=food',
  },
  {
    key: 'water',
    label: 'Вода',
    detail: 'Открыть трекер жидкости',
    icon: 'water',
    to: '/app?section=nutrition&hydration=quick',
  },
  {
    key: 'cardio',
    label: 'Кардио',
    detail: 'Записать ручную активность',
    icon: 'week-cardio',
    to: '/app?section=today&cardio=1',
  },
  {
    key: 'measurement',
    label: 'Замер',
    detail: 'Вес или окружность тела',
    icon: 'body-measurement',
    to: '/app?section=progress&focus=measurements',
  },
  {
    key: 'wellbeing',
    label: 'Самочувствие',
    detail: 'Короткий ежедневный check-in',
    icon: 'checklist',
    to: '/app?section=today&wellbeing=1',
  },
];

export function QuickAddTrigger({
  inNavigation = false,
  onOpen,
}: {
  inNavigation?: boolean;
  onOpen(): void;
}) {
  const className = [
    'app-quick-add-trigger',
    inNavigation
      ? 'app-bottom-nav__btn app-bottom-nav__quick-add'
      : 'app-quick-add-trigger--floating',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button
      aria-haspopup="dialog"
      aria-label="Быстро добавить"
      {...glassProps(inNavigation ? 'regular' : 'tinted', true)}
      {...(!inNavigation ? { 'data-glass-accent': 'lime' } : {})}
      className={className}
      data-testid="quick-add-trigger"
      type="button"
      onClick={(event) => {
        event.currentTarget.focus();
        onOpen();
      }}
    >
      {inNavigation ? (
        <span aria-hidden="true" className="app-bottom-nav__icon">
          <Icon name="plus" size={24} />
        </span>
      ) : (
        <Icon name="plus" size={20} className="app-quick-add-trigger__plus" />
      )}
      <span className={inNavigation ? 'sr-only' : 'app-quick-add-trigger__label'}>Добавить</span>
    </button>
  );
}

export function QuickAddSheet({
  actions,
  onClose,
  open,
}: {
  actions: ReadonlyArray<QuickAddAction>;
  onClose(): void;
  open: boolean;
}) {
  const panelRef = useModalA11y<HTMLDivElement>(open, onClose);
  const drag = useQuickAddDrag(panelRef, open, onClose);
  const [previousOpen, setPreviousOpen] = useState(open);
  const [exiting, setExiting] = useState(false);
  if (previousOpen !== open) {
    setPreviousOpen(open);
    setExiting(
      !open &&
        (window.matchMedia?.('(min-width: 900px)').matches ?? false) &&
        !(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false),
    );
  }
  useLayoutEffect(() => {
    if (!exiting) return;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    const timer = window.setTimeout(() => setExiting(false), 260);
    const stopForReducedMotion = (event: MediaQueryListEvent) => {
      if (event.matches) setExiting(false);
    };
    reduced?.addEventListener?.('change', stopForReducedMotion);
    return () => {
      window.clearTimeout(timer);
      reduced?.removeEventListener?.('change', stopForReducedMotion);
    };
  }, [exiting]);
  useLayoutEffect(() => {
    if (!open) return;
    const layer = panelRef.current?.parentElement;
    const trigger =
      layer?.parentElement?.querySelector<HTMLElement>('.app-quick-add-trigger') ??
      document.querySelector<HTMLElement>('[data-testid="quick-add-trigger"]');
    const background = [...(layer?.parentElement?.children ?? [])].filter(
      (element): element is HTMLElement => element instanceof HTMLElement && element !== layer,
    );
    const previous = background.map((element) => element.inert);
    background.forEach((element) => {
      element.inert = true;
    });
    return () => {
      background.forEach((element, index) => {
        element.inert = previous[index] ?? false;
      });
      // Modal cleanup runs before the background inert state is fully released.
      // Restore keyboard focus on the next frame, after the close commit.
      window.requestAnimationFrame(() => {
        const activeDialog = document.querySelector<HTMLElement>(
          '[data-testid="quick-add-layer"]:not([inert])',
        );
        if (
          trigger?.isConnected &&
          !activeDialog &&
          !trigger.closest('[inert]') &&
          (document.activeElement === document.body ||
            document.activeElement === trigger ||
            layer?.contains(document.activeElement))
        ) {
          trigger.focus({ preventScroll: true });
        }
      });
    };
  }, [open, panelRef]);
  if (!open && !exiting) return null;

  return (
    <div
      className="app-quick-add-layer"
      aria-hidden={!open || undefined}
      inert={!open}
      data-motion-phase={!open ? 'closing' : undefined}
      data-testid="quick-add-layer"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <div
        {...glassProps('tinted')}
        aria-labelledby="quick-add-title"
        aria-modal="true"
        className="app-quick-add-panel"
        data-testid="quick-add-sheet"
        ref={panelRef}
        role="dialog"
        tabIndex={-1}
      >
        <div aria-hidden="true" className="app-quick-add-panel__grip" {...drag} />
        <header className="app-quick-add-panel__header">
          <div>
            <p className="app-quick-add-panel__eyebrow">Быстрое добавление</p>
            <h2 id="quick-add-title">Что добавить?</h2>
          </div>
          <button
            aria-label="Закрыть быстрые действия"
            className="app-quick-add-panel__close"
            type="button"
            onClick={onClose}
          >
            <Icon name="close" size={20} />
          </button>
        </header>
        <nav aria-label="Быстрые действия" className="app-quick-add-panel__actions">
          {actions.map((action) => (
            <AppLink
              className="app-quick-add-action"
              key={action.key}
              to={action.to}
              onClick={() => {
                if (isQuickAddAnalyticsKind(action.key)) {
                  trackProductEvent({
                    name: 'quick_add_action_selected',
                    surface: productEventSurface(),
                    action: action.key,
                  });
                }
                onClose();
              }}
            >
              <span aria-hidden="true" className="app-quick-add-action__icon">
                <Icon name={action.icon} size={20} />
              </span>
              <span className="app-quick-add-action__copy">
                <strong>{action.label}</strong>
              </span>
              <Icon
                aria-hidden="true"
                className="app-quick-add-action__arrow"
                name="chevron-right"
                size={16}
              />
            </AppLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
