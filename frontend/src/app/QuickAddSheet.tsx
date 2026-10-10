import { useEffect } from 'react';
import { AppLink } from '../shared/navigation/router';
import { glassProps } from '../shared/ui/Glass';
import { Icon, type IconName } from '../shared/ui/Icon';
import { useModalA11y } from '../shared/ui/useModalA11y';
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

export function QuickAddTrigger({ onOpen }: { onOpen(): void }) {
  return (
    <button
      aria-haspopup="dialog"
      aria-label="Быстро добавить"
      {...glassProps('tinted', true)}
      data-glass-accent="lime"
      className="app-quick-add-trigger"
      data-testid="quick-add-trigger"
      type="button"
      onClick={(event) => {
        event.currentTarget.focus();
        onOpen();
      }}
    >
      <Icon name="plus" className="app-quick-add-trigger__plus" />
      <span className="app-quick-add-trigger__label">Добавить</span>
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
  useEffect(() => {
    if (!open) return;
    const layer = panelRef.current?.parentElement;
    const trigger = layer?.parentElement?.querySelector<HTMLElement>('.app-quick-add-trigger');
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
      trigger?.focus({ preventScroll: true });
    };
  }, [open, panelRef]);
  if (!open) return null;

  return (
    <div
      className="app-quick-add-layer"
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
        <header className="app-quick-add-panel__header">
          <h2 id="quick-add-title">Что добавить?</h2>
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
