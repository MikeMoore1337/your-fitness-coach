import { useState, type ReactNode, type AnchorHTMLAttributes } from 'react';
import type { DemoSelfTrainingState } from '../../features/demo/demoApi';
import { demoCabinetUrlForHostname } from '../../shared/navigation/appUrl';
import { Icon } from '../../shared/ui/Icon';
import { glassProps } from '../../shared/ui/Glass';
import { LandingChapter } from './LandingChapter';
import { LandingProgress } from './LandingProgress';
import { TrainingScenario } from '../demo/TrainingScenario';
import { landingAudienceHref } from './landingAudience';
import '../demo/demo.css';

const NUTRITION_TAB_PLAN = 'plan';
const NUTRITION_TAB_GROCERY = 'grocery';
const COACH_TAB_FACTS = 'facts';
const COACH_TAB_CHANGES = 'changes';

const initialTraining: DemoSelfTrainingState = {
  kind: 'self_training' as const,
  screen: 'today' as const,
  workout_title: 'Силовая А',
  workout_subtitle: 'Программа на неделю · пример данных',
  completed_sets: 0,
  total_sets: 3,
  exercises: [
    {
      name: 'Тяга гантели',
      prescription: '18 кг × 3 повторения · демонстрационный подход',
      status: 'current' as const,
    },
  ],
  duration_minutes: 24,
  total_volume_kg: 162,
  progress_change_percent: 4.2,
};
function Action({
  children,
  href,
  secondary = false,
  ...props
}: {
  children: ReactNode;
  href: string;
  secondary?: boolean;
} & AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a
      href={href}
      {...(href.startsWith('https:') ? { target: '_blank', rel: 'noopener' } : {})}
      className={`landing-button ${secondary ? 'landing-button--secondary' : ''}`}
      {...(secondary ? glassProps('clear', true) : {})}
      {...props}
    >
      {children}
      <Icon name="arrow-right" size={20} />
    </a>
  );
}
function SectionTitle({
  index,
  title,
  children,
}: {
  index: string;
  title: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="ref-copy">
      <p className="landing-kicker">{index}</p>
      <h2>{title}</h2>
      {children}
    </div>
  );
}
export function ArchiveTraining() {
  const [state, setState] = useState<DemoSelfTrainingState>(initialTraining);
  function act(action: string) {
    setState((s) =>
      action === 'start_workout'
        ? { ...s, screen: 'active_workout' }
        : action === 'complete_set'
          ? {
              ...s,
              completed_sets: Math.min(s.total_sets, s.completed_sets + 1),
              exercises: [
                {
                  ...s.exercises[0]!,
                  status: s.completed_sets + 1 === s.total_sets ? 'completed' : 'current',
                },
              ],
            }
          : action === 'finish_workout'
            ? { ...s, screen: 'summary' }
            : { ...s, screen: 'progress' },
    );
  }
  return (
    <LandingChapter id="training" tabIndex={-1} className="ref-section ref-training">
      <SectionTitle
        index="ДЕЙСТВИЕ / В ДЕЛЕ"
        title={
          <>
            Вошли в ритм.
            <br />
            <em>Продолжайте.</em>
          </>
        }
      >
        <p>
          Программа задаёт направление. Выполненные подходы сохраняют то, что получилось на самом
          деле.
        </p>
        <div className="ref-note">
          <Icon name="exercise" size={80} />
          <span>
            Попробуйте записать подход.
            <br />
            Только синтетические данные.
          </span>
        </div>
        <p className="ref-caption">
          Движение не распознаётся автоматически. Результат отмечаете вы.
        </p>
      </SectionTitle>
      <div className="ref-product ref-training-panel">
        <div className="ref-product-head">
          <span>Сегодня / Тренировка</span>
          <button className="ref-text-control" onClick={() => setState(initialTraining)}>
            Сбросить пример
          </button>
        </div>
        <TrainingScenario state={state} busy={false} onAction={act} />
      </div>
    </LandingChapter>
  );
}
export function ArchiveNutrition() {
  const [tab, setTab] = useState('plan');
  const [recorded, setRecorded] = useState(false);
  return (
    <LandingChapter id="nutrition" className="ref-section ref-nutrition">
      <div className="ref-photo-copy">
        <img
          src="/assets/marketing/nutrition-photo.webp"
          width="1024"
          height="1024"
          alt="Завтрак с овсянкой, фруктами и ягодами"
          loading="lazy"
        />
        <div>
          <p className="landing-kicker">КОНТЕКСТ / ПИТАНИЕ</p>
          <h2>
            Планируйте.
            <br />
            <em>Отмечайте факт.</em>
          </h2>
        </div>
      </div>
      <div className="ref-nutrition-body">
        <p className="ref-lead">
          От рецепта в плане — к списку покупок. От приёма пищи — к записи в дневнике.
        </p>
        <div className="ref-product">
          <div className="ref-product-head">
            <span>Питание / пример данных</span>
            <Icon name="nav-nutrition" />
          </div>
          <nav className="ref-tabs" aria-label="Пример питания">
            {[
              ['plan', 'План'],
              ['grocery', 'Покупки'],
              ['diary', 'Дневник'],
            ].map(([key, label]) => (
              <button
                key={key}
                {...glassProps('clear', true)}
                aria-pressed={tab === key}
                onClick={() => setTab(key!)}
              >
                {label}
              </button>
            ))}
          </nav>
          <div className="ref-tab-body" key={tab}>
            {tab === NUTRITION_TAB_PLAN ? (
              <>
                <small>ЗАВТРАК · ЗАПЛАНИРОВАНО</small>
                <h3>Овсянка с ягодами</h3>
                <p>Рецепт добавлен в план. Это ещё не запись о съеденном.</p>
                <button className="landing-button" onClick={() => setTab(NUTRITION_TAB_GROCERY)}>
                  Посмотреть покупки <Icon name="arrow-right" size={20} />
                </button>
              </>
            ) : tab === NUTRITION_TAB_GROCERY ? (
              <>
                <small>ИЗ ПЛАНОВОГО РЕЦЕПТА</small>
                <h3>Список покупок</h3>
                <ul className="ref-list">
                  <li>
                    Овсяные хлопья <b>60 г</b>
                  </li>
                  <li>
                    Молоко <b>200 мл</b>
                  </li>
                  <li>
                    Ягоды <b>80 г</b>
                  </li>
                </ul>
                <p className="ref-caption">
                  Иллюстративные количества, не рекомендация по питанию.
                </p>
              </>
            ) : (
              <>
                <small>ФАКТИЧЕСКИ СЪЕДЕНО</small>
                <h3>{recorded ? 'Завтрак записан' : 'Записи пока нет'}</h3>
                <p>
                  {recorded
                    ? 'Запись появилась после вашего действия.'
                    : 'План не добавляет приём пищи в дневник автоматически.'}
                </p>
                <button
                  className="landing-button"
                  disabled={recorded}
                  onClick={() => setRecorded(true)}
                >
                  {recorded ? 'Запись сохранена в примере' : 'Отметить съеденное в примере'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </LandingChapter>
  );
}
function WeeklyPreview() {
  const [score, setScore] = useState<number>();
  return (
    <div className="ref-weekly">
      <Icon name="nav-today" size={56} />
      <div>
        <h3>Проверка недели</h3>
        <p>2 из 3 тренировок выполнено · пример данных</p>
        <details>
          <summary>Посмотреть вопрос недели</summary>
          <fieldset>
            <legend>Как вы восстанавливались на этой неделе?</legend>
            <div className="ref-scores">
              {[1, 2, 3, 4, 5].map((value) => (
                <label key={value}>
                  <input
                    type="radio"
                    name="recovery"
                    value={value}
                    checked={score === value}
                    onChange={() => setScore(value)}
                  />
                  <span>{value}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <p role="status">
            {score
              ? `В примере выбран ответ ${score} из 5. В аккаунт он не записывается.`
              : 'Факты → вопросы → следующий шаг. Решение остаётся за человеком.'}
          </p>
        </details>
        <small>Решение остаётся за вами или вашим тренером.</small>
      </div>
    </div>
  );
}
export function ArchiveProgress() {
  return (
    <LandingChapter id="progress" className="ref-section ref-progress">
      <SectionTitle
        index="ФАКТЫ → РЕШЕНИЕ / ДИНАМИКА"
        title={
          <>
            Замечайте
            <br />
            своё движение.
          </>
        }
      >
        <p>
          Объём, выполненные тренировки и проверка недели дают контекст для следующего шага. Если
          данных мало, сильного вывода не будет.
        </p>
        <WeeklyPreview />
        <Action
          href={demoCabinetUrlForHostname(window.location.hostname, 'self_training', 'progress')}
          secondary
        >
          Посмотреть пример прогресса
        </Action>
      </SectionTitle>
      <LandingProgress
        wrapperClassName="ref-product ref-progress-panel"
        href={demoCabinetUrlForHostname(window.location.hostname, 'self_training', 'progress')}
      />
    </LandingChapter>
  );
}
export function ArchiveCoachWork({ compact = false }: { compact?: boolean } = {}) {
  const [tab, setTab] = useState(COACH_TAB_FACTS);
  const [preview, setPreview] = useState(false);
  const [applied, setApplied] = useState(false);
  const [sent, setSent] = useState(false);

  const panel = (
    <div className={`ref-product ref-coach-panel${compact ? ' ref-coach-panel--compact' : ''}`}>
      <div className="ref-product-head">
        <span>Coach Today</span>
        <small>Дизайн-сцена · пример</small>
      </div>
      <div className="ref-client">
        <span className="ref-avatar">А</span>
        <div>
          <b>Алексей · демо-клиент</b>
          <p>Проверка недели готова к просмотру</p>
        </div>
        <Icon name="arrow-right" />
      </div>
      <nav className="ref-tabs" aria-label="Рабочий обзор клиента">
        {[
          ['facts', 'Факты'],
          ['changes', 'Изменения'],
          ['draft', 'Сообщение'],
        ].map(([key, label]) => (
          <button
            key={key}
            {...glassProps('clear', true)}
            aria-pressed={tab === key}
            onClick={() => setTab(key!)}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="ref-tab-body" key={tab}>
        {tab === COACH_TAB_FACTS ? (
          <>
            <small>ОБЗОР КЛИЕНТА</small>
            <h3>Факты перед решением</h3>
            <dl className="ref-facts">
              <div>
                <dt>Выполнение программы</dt>
                <dd>2 из 3 тренировок</dd>
              </div>
              <div>
                <dt>Проверка состояния</dt>
                <dd>Новый ответ</dd>
              </div>
              <div>
                <dt>Следующий шаг</dt>
                <dd>Посмотреть изменения</dd>
              </div>
            </dl>
            <button className="landing-button" onClick={() => setTab(COACH_TAB_CHANGES)}>
              Открыть изменения <Icon name="arrow-right" size={20} />
            </button>
          </>
        ) : tab === COACH_TAB_CHANGES ? (
          <>
            <small>ПРОГРАММА / ВЕРСИЯ 2</small>
            <h3>
              {applied
                ? 'Изменение подтверждено'
                : preview
                  ? 'Просмотр перед применением'
                  : 'Подготовлено изменение'}
            </h3>
            <p>
              Тяга гантели: 3 → 2 подхода. Один демо-клиент. Это пример интерфейса, не тренировочный
              совет.
            </p>
            <p className="ref-caption">
              {applied
                ? 'Состояние изменилось только в локальном примере.'
                : 'Сначала посмотрите отличие, затем подтвердите применение.'}
            </p>
            <button
              className="landing-button"
              disabled={applied}
              onClick={() => (preview ? setApplied(true) : setPreview(true))}
            >
              {applied
                ? 'Подтверждено в примере'
                : preview
                  ? 'Подтвердить в примере'
                  : 'Посмотреть перед применением'}
            </button>
          </>
        ) : (
          <>
            <small>ШАБЛОН → ЧЕРНОВИК → ПОДТВЕРЖДЕНИЕ</small>
            <h3>{sent ? 'Подтверждено в примере' : 'Сообщение остаётся вашим'}</h3>
            <label className="ref-draft-label">
              Текст черновика
              <textarea
                defaultValue="Алексей, посмотрел проверку недели. Давайте обсудим план следующей тренировки."
                disabled={sent}
              />
            </label>
            <p className="ref-caption">
              Ничего не отправляется. Это локальный пример ручного подтверждения.
            </p>
            <button className="landing-button" disabled={sent} onClick={() => setSent(true)}>
              {sent ? 'Подтверждено' : 'Подтвердить черновик в примере'}
            </button>
          </>
        )}
      </div>
    </div>
  );

  if (compact) {
    return (
      <LandingChapter id="coach-promo" tabIndex={-1} className="ref-section ref-coach-teaser">
        <div className="ref-copy">
          <p className="landing-kicker">ДЛЯ ТРЕНЕРА / COACH OS</p>
          <h2>
            Вы тренер?
            <br />
            <em>Знакомьтесь с Coach OS.</em>
          </h2>
          <p>
            Рабочий контур для клиентов, программ и проверок — с фактами перед следующим решением.
          </p>
          <a
            className="landing-button landing-button--secondary"
            {...glassProps('clear', true)}
            data-glass-tone="on-image"
            href={landingAudienceHref('coach')}
          >
            Возможности для тренера <Icon name="arrow-right" size={20} />
          </a>
        </div>
        {panel}
      </LandingChapter>
    );
  }

  return (
    <LandingChapter id="coach-work" tabIndex={-1} className="ref-section ref-coach-work">
      <SectionTitle
        index="COACH OS / ВНИМАНИЕ → КОНТЕКСТ"
        title={
          <>
            Не потерять
            <br />
            <em>важное.</em>
          </>
        }
      >
        <p>
          Coach Today собирает поводы вернуться к клиенту. В рабочем обзоре видны факты и значимые
          изменения — перед вашим решением.
        </p>
        <div className="ref-note">
          <Icon name="nav-coach" size={80} />
          <span>
            Клиенты, программы, проверки.
            <br />
            Один рабочий контекст.
          </span>
        </div>
        <p className="ref-caption">
          Синтетический клиент. Личные заметки тренера в публичной сцене не показываются.
        </p>
      </SectionTitle>
      {panel}
    </LandingChapter>
  );
}
