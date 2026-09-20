import { Icon } from '../../shared/ui/Icon';

export type CoachTool = 'schedule' | 'tasks' | 'finance' | 'invitations' | 'catalog';

const tools: ReadonlyArray<{ key: CoachTool; title: string; description: string }> = [
  {
    key: 'schedule',
    title: 'Расписание и встречи',
    description: 'Рабочая неделя, ближайшая встреча и статусы сессий',
  },
  {
    key: 'tasks',
    title: 'Задачи',
    description: 'Открытые задачи клиентов и ближайшие сроки',
  },
  {
    key: 'finance',
    title: 'Пакеты и оплаты',
    description: 'Остатки пакетов и ручной учёт оплат',
  },
  {
    key: 'invitations',
    title: 'Приглашения и подключения',
    description: 'Создать приглашение или проверить ожидающие подключения',
  },
  {
    key: 'catalog',
    title: 'Каталог упражнений',
    description: 'Найти упражнение для программы клиента',
  },
];

export function CoachToolsHub({ onNavigate }: { onNavigate: (tool: CoachTool) => void }) {
  return (
    <section
      className="coach-tools-hub"
      data-testid="coach-tools-hub"
      aria-labelledby="coach-tools-title"
    >
      <header className="coach-tools-hub__header">
        <div>
          <span className="eyebrow">Навигация</span>
          <h2 id="coach-tools-title">Ещё</h2>
          <p>Вторичные рабочие инструменты — каждый открывается в своём рабочем разделе.</p>
        </div>
      </header>
      <nav className="coach-tools-hub__list" aria-label="Инструменты тренера">
        {tools.map((tool) => (
          <button
            className="coach-tools-hub__link"
            key={tool.key}
            onClick={() => onNavigate(tool.key)}
            type="button"
          >
            <span>
              <strong>{tool.title}</strong>
              <small>{tool.description}</small>
            </span>
            <Icon name="arrow-right" size={16} />
          </button>
        ))}
      </nav>
    </section>
  );
}
