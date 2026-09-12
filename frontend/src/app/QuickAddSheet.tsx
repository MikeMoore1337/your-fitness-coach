import { AppLink } from '../shared/navigation/router';
import { Glass, glassProps } from '../shared/ui/Glass';
import { Icon, type IconName } from '../shared/ui/Icon';
import { useModalA11y } from '../shared/ui/useModalA11y';

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
    label: 'Добавить еду',
    detail: 'Быстрый ввод в дневник питания',
    icon: 'calories',
    to: '/app?section=nutrition&quick_add=food',
  },
  {
    key: 'water',
    label: 'Добавить воду',
    detail: 'Открыть трекер жидкости',
    icon: 'water',
    to: '/app?section=nutrition&hydration=quick',
  },
  {
    key: 'cardio',
    label: 'Добавить кардио',
    detail: 'Записать ручную активность',
    icon: 'week-cardio',
    to: '/app?section=today&cardio=1',
  },
  {
    key: 'measurement',
    label: 'Добавить замер',
    detail: 'Вес или окружность тела',
    icon: 'body-measurement',
    to: '/app?section=progress&focus=measurements',
  },
  {
    key: 'wellbeing',
    label: 'Отметить самочувствие',
    detail: 'Короткий ежедневный check-in',
    icon: 'checklist',
    to: '/app?section=today&wellbeing=1',
  },
  {
    key: 'ai-coach',
    label: 'Открыть AI Coach',
    detail: 'Подсказка и настройки — если функция доступна',
    icon: 'ai-coach',
    to: '/app?section=profile#profile-ai-coach',
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
      onClick={onOpen}
    >
      <span aria-hidden="true" className="app-quick-add-trigger__plus">
        +
      </span>
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
  if (!open) return null;

  return (
    <div
      className="app-quick-add-layer"
      data-testid="quick-add-layer"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <Glass
        aria-labelledby="quick-add-title"
        variant="tinted"
        aria-modal="true"
        className="app-quick-add-panel"
        data-testid="quick-add-sheet"
        ref={panelRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="app-quick-add-panel__header">
          <div>
            <span className="eyebrow">Быстрое действие</span>
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
        <p className="app-quick-add-panel__intro">
          Выберите операцию — откроется существующий экран записи, без новых данных или скрытых
          подтверждений.
        </p>
        <nav aria-label="Быстрые действия" className="app-quick-add-panel__actions">
          {actions.map((action) => (
            <AppLink
              className="app-quick-add-action"
              key={action.key}
              to={action.to}
              onClick={onClose}
            >
              <span aria-hidden="true" className="app-quick-add-action__icon">
                <Icon name={action.icon} size={20} />
              </span>
              <span className="app-quick-add-action__copy">
                <strong>{action.label}</strong>
                <small>{action.detail}</small>
              </span>
              <Icon
                aria-hidden="true"
                className="app-quick-add-action__arrow"
                name="arrow-right"
                size={16}
              />
            </AppLink>
          ))}
        </nav>
      </Glass>
    </div>
  );
}
