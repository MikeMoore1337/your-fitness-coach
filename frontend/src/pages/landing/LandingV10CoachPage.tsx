import { useState } from 'react';
import { demoCabinetUrlForHostname } from '../../shared/navigation/appUrl';
import { trainerIntentLoginUrl } from '../../shared/auth/trainerIntent';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { Icon } from '../../shared/ui/Icon';
import { LandingChapter } from './LandingChapter';
import { LandingV10Faq } from './LandingV10Faq';
import { LandingV10Shell } from './LandingV10Shell';
import { LandingAudienceSwitch } from './LandingAudienceSwitch';
import { useLandingHeroMotion } from './useLandingHeroMotion';
import './landing.css';

type CoachTodayTab = 'facts' | 'изменения' | 'message';

const COACH_TODAY_TABS: ReadonlyArray<{ id: CoachTodayTab; label: string }> = [
  { id: 'facts', label: 'Факты' },
  { id: 'изменения', label: 'Изменения' },
  { id: 'message', label: 'Сообщение' },
] as const;

const COACH_TODAY_CONTENT: Record<
  CoachTodayTab,
  { eyebrow: string; title: string; body: string; note: string }
> = {
  facts: {
    eyebrow: 'КЛИЕНТ / НЕДЕЛЯ',
    title: 'Факты собраны',
    body: '2 тренировки выполнены · проверка недели готова к просмотру.',
    note: 'Публичный пример использует только синтетические записи.',
  },
  изменения: {
    eyebrow: 'ПРОГРАММА / ВЕРСИЯ 2',
    title: 'Изменение подтверждено',
    body: 'Тяга гантели: 3 → 2 подхода. Один демо-клиент.',
    note: 'Состояние изменилось только в локальном макете.',
  },
  message: {
    eyebrow: 'СООБЩЕНИЕ / ЧЕРНОВИК',
    title: 'Черновик готов к проверке',
    body: 'Короткий ответ сохранён до явного подтверждения тренера.',
    note: 'Автоматической отправки в публичной сцене нет.',
  },
};

function CoachTodayPreview() {
  const [tab, setTab] = useState<CoachTodayTab>('изменения');
  const active = COACH_TODAY_CONTENT[tab];

  return (
    <div className="landing-v10-coach-today" data-testid="coach-today-preview">
      <div className="landing-v10-coach-today__topline">
        <strong>Coach OS</strong>
        <small>Дизайн-сцена · пример</small>
      </div>
      <div className="landing-v10-coach-today__client">
        <span className="landing-v10-coach-today__avatar" aria-hidden="true">
          А
        </span>
        <div>
          <strong>Алексей · демо-клиент</strong>
          <small>Проверка недели готова к просмотру</small>
        </div>
        <Icon name="arrow-right" size={20} />
      </div>
      <div className="landing-v10-coach-today__tabs" role="tablist" aria-label="Контекст клиента">
        {COACH_TODAY_TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item.id === tab}
            aria-controls={`coach-today-panel-${item.id}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        id={`coach-today-panel-${tab}`}
        className="landing-v10-coach-today__panel"
        role="tabpanel"
        aria-live="polite"
      >
        <small>{active.eyebrow}</small>
        <h3>{active.title}</h3>
        <p>{active.body}</p>
        <span>{active.note}</span>
        <strong className="landing-v10-coach-today__confirmation">
          {tab === 'изменения' ? 'Подтверждено в примере' : 'Доступно для решения'}
        </strong>
      </div>
    </div>
  );
}

function CoachHero() {
  const [heroUnavailable, setHeroUnavailable] = useState(false);
  const appUrl = trainerIntentLoginUrl(window.location.hostname);
  const demoUrl = demoCabinetUrlForHostname(window.location.hostname, 'trainer', 'trainer');

  return (
    <section
      className="landing-hero landing-v10-coach-hero"
      aria-labelledby="landing-v10-coach-title"
    >
      <div className="landing-v10-hero-audience">
        <LandingAudienceSwitch audience="coach" showLabel={false} />
      </div>
      <img
        className="landing-hero__image"
        src="/assets/marketing/trainer-photo.webp"
        alt="Тренер и спортсменка обсуждают план"
        fetchPriority="high"
        width="1536"
        height="1024"
        onError={() => setHeroUnavailable(true)}
        hidden={heroUnavailable}
      />
      <div className="landing-hero__copy">
        {heroUnavailable && <p role="status">Фото не загрузилось. Все действия доступны.</p>}
        <p className="landing-kicker">ПРОГРАММЫ. ПРОВЕРКИ. СЛЕДУЮЩИЙ ШАГ.</p>
        <h1 id="landing-v10-coach-title">
          <span>ВАШ МЕТОД</span> <span>В ДЕЙСТВИИ.</span>
        </h1>
        <p className="landing-hero__lead">
          Программы, проверки и история клиента — в одном рабочем пространстве. Видеть важное.
          Выбирать следующий шаг.
        </p>
        <div className="landing-hero__actions">
          <a
            className="landing-button"
            href={appUrl}
            onClick={() =>
              trackProductEvent({
                name: 'trainer_landing_cta_clicked',
                surface: productEventSurface(),
                destination: 'onboarding',
              })
            }
          >
            Начать как тренер <Icon name="arrow-right" size={20} />
          </a>
          <a
            className="landing-button landing-button--secondary landing-button--secondary-on-dark"
            href={demoUrl}
            onClick={() =>
              trackProductEvent({
                name: 'landing_demo_selected',
                surface: productEventSurface(),
                placement: 'hero',
                scenario: 'trainer',
              })
            }
          >
            Попробовать демо для тренера <Icon name="arrow-right" size={20} />
          </a>
        </div>
        <a className="landing-v10-hero-tertiary" href="#coach-work">
          Как работает Coach OS <Icon name="chevron-down" size={16} />
        </a>
        <div className="landing-hero__platform">
          <p className="landing-hero__platform-note">
            <Icon name="web-app" size={16} /> Браузер и мини-приложение Telegram
          </p>
        </div>
      </div>
    </section>
  );
}

function ProgramVersionPreview() {
  const [version, setVersion] = useState(2);

  return (
    <div className="landing-v10-coach-board" data-testid="program-preview">
      <div className="landing-v10-coach-board__heading">
        <div>
          <small>ПРОГРАММА / ВЕРСИИ</small>
          <h3>Силовой блок клиента</h3>
        </div>
        <Icon name="nav-today" size={24} />
      </div>
      <div className="landing-v10-coach-today__tabs" role="tablist" aria-label="Версии программы">
        {[1, 2].map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={version === item}
            onClick={() => setVersion(item)}
          >
            Версия {item}
          </button>
        ))}
      </div>
      <strong>
        {version === 2 ? '3 → 2 подхода в следующей тренировке' : '3 подхода в текущем блоке'}
      </strong>
      <p>Версия показывает будущий план и не переписывает выполненную историю.</p>
      <span className="landing-v10-coach-board__status">
        Действие требует отдельного подтверждения.
      </span>
    </div>
  );
}

function RolloutPreview() {
  const [selected, setSelected] = useState(['Алексей', 'Марина']);
  const [preview, setPreview] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  const toggle = (client: string) => {
    setConfirmed(false);
    setPreview(false);
    setSelected((current) =>
      current.includes(client) ? current.filter((item) => item !== client) : [...current, client],
    );
  };

  return (
    <div className="landing-v10-coach-board" data-testid="rollout-preview">
      <div className="landing-v10-coach-board__heading">
        <div>
          <small>ПРОГРАММА / ПРЕДПРОСМОТР</small>
          <h3>Версия 2 · силовой блок</h3>
        </div>
        <span className="landing-v10-coach-badge">Будущие тренировки</span>
      </div>
      <p>Выберите клиентов, затем проверьте изменение перед ручным подтверждением.</p>
      <div
        className="landing-v10-coach-board__clients"
        role="group"
        aria-label="Клиенты для примера"
      >
        {['Алексей', 'Марина'].map((client) => (
          <label key={client}>
            <input
              type="checkbox"
              checked={selected.includes(client)}
              onChange={() => toggle(client)}
            />
            <span>{client}</span>
            <small>{client === 'Алексей' ? '2 тренировки' : '1 тренировка'}</small>
          </label>
        ))}
      </div>
      <button
        type="button"
        className="landing-v10-coach-board__action"
        disabled={selected.length === 0}
        onClick={() => setPreview(true)}
      >
        Показать изменение
      </button>
      {preview && (
        <div className="landing-v10-coach-board__result" role="status">
          <strong>{selected.length} клиента · 2 подхода вместо 3</strong>
          <span>История выполненного не переписывается.</span>
          <button type="button" onClick={() => setConfirmed(true)}>
            {confirmed ? 'Подтверждено в примере' : 'Подтвердить в примере'}
          </button>
        </div>
      )}
    </div>
  );
}

function ReviewPreview() {
  const [score, setScore] = useState<number>();
  const [decision, setDecision] = useState('');

  return (
    <div className="landing-v10-coach-board" data-testid="review-preview">
      <div className="landing-v10-coach-board__heading">
        <div>
          <small>ПРОВЕРКА НЕДЕЛИ</small>
          <h3>Решение остаётся за тренером</h3>
        </div>
        <Icon name="nav-progress" size={24} />
      </div>
      <p>Факты видны рядом с ответом клиента. Недостающая запись не становится нулём.</p>
      <div className="landing-v10-review__scale" role="group" aria-label="Оценка проверки недели">
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={score === value}
            onClick={() => setScore(value)}
          >
            {value}
          </button>
        ))}
      </div>
      <div className="landing-v10-coach-board__decisions" role="group" aria-label="Следующий шаг">
        {['Оставить', 'Изменить', 'Проверить позже'].map((item) => (
          <button
            key={item}
            type="button"
            aria-pressed={decision === item}
            onClick={() => setDecision(item)}
          >
            {item}
          </button>
        ))}
      </div>
      <p className="landing-v10-coach-board__status" role="status">
        {decision
          ? `Выбрано: ${decision}. Локальный ответ превью.`
          : score
            ? `Отмечено: ${score} из 5. Решение ещё не подтверждено.`
            : 'Пока нет решения. Данные остаются видимыми.'}
      </p>
    </div>
  );
}

function FollowUpPreview() {
  const [confirmed, setConfirmed] = useState(false);

  return (
    <div
      className="landing-v10-coach-board landing-v10-coach-followup"
      data-testid="followup-preview"
    >
      <div className="landing-v10-coach-board__heading">
        <div>
          <small>СООБЩЕНИЕ / ЧЕРНОВИК</small>
          <h3>Сначала проверить. Потом отправить.</h3>
        </div>
        <Icon name="nav-coach" size={24} />
      </div>
      <blockquote>
        «Алексей, вижу две выполненные тренировки. Давайте проверим самочувствие и следующий шаг на
        этой неделе.»
      </blockquote>
      <p>
        Черновик остаётся у тренера до явного подтверждения. Отправка в публичной сцене отключена.
      </p>
      <button type="button" onClick={() => setConfirmed(true)}>
        {confirmed ? 'Черновик подтверждён в примере' : 'Подтвердить черновик'}
      </button>
    </div>
  );
}

export default function LandingV10CoachPage() {
  useLandingHeroMotion();
  const trainerLoginUrl = trainerIntentLoginUrl(window.location.hostname);
  const demoUrl = demoCabinetUrlForHostname(window.location.hostname, 'trainer', 'trainer');

  return (
    <LandingV10Shell audience="coach">
      <CoachHero />

      <LandingChapter
        id="product"
        className="landing-v10-coach-cycle"
        aria-labelledby="landing-v10-coach-cycle-title"
      >
        <div className="landing-v10-coach-cycle__intro">
          <p className="landing-kicker">01 / РАБОЧИЙ РИТМ ТРЕНЕРА</p>
          <h2 id="landing-v10-coach-cycle-title">
            От внимания
            <br /> <em>к следующему шагу.</em>
          </h2>
          <p>Coach OS связывает сигнал, контекст клиента и ручное решение в одном рабочем цикле.</p>
        </div>
        <ol className="landing-v10-coach-cycle__list">
          {[
            ['01', 'Внимание', 'Вернитесь к клиенту, которому сейчас нужен контекст.'],
            ['02', 'Контекст', 'Откройте программу, выполненное и проверку рядом.'],
            ['03', 'Решение', 'Выберите изменение и проверьте его до подтверждения.'],
            ['04', 'Следующий шаг', 'Оставьте задачу или черновик сообщения на своём месте.'],
          ].map(([number, title, text]) => (
            <li key={number}>
              <small>{number}</small>
              <Icon name="checklist" size={24} />
              <h3>{title}</h3>
              <p>{text}</p>
            </li>
          ))}
        </ol>
      </LandingChapter>

      <LandingChapter
        id="coach-work"
        className="landing-v10-coach-scene landing-v10-coach-today-scene"
        aria-labelledby="landing-v10-coach-work-title"
        data-coach-chapter="coach-today"
      >
        <div className="landing-v10-coach-copy">
          <p className="landing-kicker">КОУЧ ОС / ВНИМАНИЕ → КОНТЕКСТ</p>
          <h2 id="landing-v10-coach-work-title">
            Не потерять
            <br /> <em>важное.</em>
          </h2>
          <p>
            Центр дня собирает поводы вернуться к клиенту. В рабочем обзоре видны факты и значимые
            изменения — перед вашим решением.
          </p>
          <div className="landing-v10-coach-proofline">
            <Icon name="nav-coach" size={56} />
            <span>
              Клиенты, программы, проверки.
              <br />
              Один рабочий контекст.
            </span>
          </div>
          <p className="landing-v10-coach-disclosure">
            Синтетический клиент. Личные заметки тренера в публичной сцене не показываются.
          </p>
        </div>
        <CoachTodayPreview />
      </LandingChapter>

      <LandingChapter
        id="coach-connect"
        className="landing-v10-coach-scene landing-v10-coach-connect-scene"
        aria-labelledby="landing-v10-coach-connect-title"
        data-coach-chapter="connect"
      >
        <div className="landing-v10-coach-copy">
          <p className="landing-kicker">03 / ПОДКЛЮЧЕНИЕ</p>
          <h2 id="landing-v10-coach-connect-title">
            Начать с одного
            <br /> <em>рабочего контакта.</em>
          </h2>
          <p>
            Приглашение относится к конкретному клиенту. Группы и метки помогают вернуть контекст,
            когда клиентов становится больше.
          </p>
        </div>
        <div className="landing-v10-coach-board" data-testid="connect-preview">
          <div className="landing-v10-coach-board__heading">
            <div>
              <small>КЛИЕНТЫ / НОВОЕ ПОДКЛЮЧЕНИЕ</small>
              <h3>Подключить клиента</h3>
            </div>
            <Icon name="nav-coach" size={24} />
          </div>
          <label className="landing-v10-coach-field">
            <span>Подпись для приглашения</span>
            <input
              aria-label="Подпись для приглашения"
              defaultValue="Алексей · демо-клиент"
              readOnly
            />
          </label>
          <div className="landing-v10-coach-tags" aria-label="Группы клиента">
            <span>силовой блок</span>
            <span>проверка недели</span>
          </div>
          <p className="landing-v10-coach-board__status" role="status">
            Ссылка готовится для показа. Она ничего не отправляет.
          </p>
        </div>
      </LandingChapter>

      <LandingChapter
        id="coach-program"
        className="landing-v10-coach-scene landing-v10-coach-program-scene"
        aria-labelledby="landing-v10-coach-program-title"
        data-coach-chapter="program"
      >
        <div className="landing-v10-coach-copy">
          <p className="landing-kicker">04 / ПРОГРАММА И ВЕРСИЯ</p>
          <h2 id="landing-v10-coach-program-title">
            Изменение видно
            <br /> <em>до применения.</em>
          </h2>
          <p>
            Выберите клиентов, сравните будущую версию и подтвердите действие вручную. Выполненные
            тренировки остаются в истории.
          </p>
        </div>
        <ProgramVersionPreview />
      </LandingChapter>

      <LandingChapter
        id="coach-facts"
        className="landing-v10-coach-scene landing-v10-coach-facts-scene"
        aria-labelledby="landing-v10-coach-facts-title"
        data-coach-chapter="facts"
      >
        <div className="landing-v10-coach-copy">
          <p className="landing-kicker">05 / КЛИЕНТ 360 · ФАКТЫ</p>
          <h2 id="landing-v10-coach-facts-title">
            Сначала факты.
            <br /> <em>Потом вывод.</em>
          </h2>
          <p>
            Программа, тренировки, питание и прогресс клиента остаются рядом. Незаполненное поле
            обозначено как отсутствие данных.
          </p>
        </div>
        <div
          className="landing-v10-coach-board landing-v10-client-facts"
          data-testid="facts-preview"
        >
          <div className="landing-v10-client-facts__identity">
            <span className="landing-v10-coach-tile-avatar" aria-hidden="true">
              А
            </span>
            <div>
              <strong>Алексей · демо-клиент</strong>
              <small>Силовой блок · неделя 3</small>
            </div>
          </div>
          <dl>
            <div>
              <dt>Выполнено</dt>
              <dd>2 из 3</dd>
            </div>
            <div>
              <dt>Питание</dt>
              <dd>1 день без записи</dd>
            </div>
            <div>
              <dt>Проверка</dt>
              <dd>Готова</dd>
            </div>
          </dl>
          <p className="landing-v10-coach-board__status" role="note">
            Личные заметки тренера скрыты из публичной сцены.
          </p>
        </div>
      </LandingChapter>

      <LandingChapter
        id="coach-review"
        className="landing-v10-coach-scene landing-v10-coach-review-scene"
        aria-labelledby="landing-v10-coach-review-title"
        data-coach-chapter="review"
      >
        <div className="landing-v10-coach-copy">
          <p className="landing-kicker">06 / ОБРАТНАЯ СВЯЗЬ И ПРОВЕРКА</p>
          <h2 id="landing-v10-coach-review-title">
            Проверка недели
            <br /> <em>помогает выбрать.</em>
          </h2>
          <p>
            Ответ клиента и измеримые записи дают рабочую опору. Система не принимает решение за
            тренера и не подменяет медицинскую оценку.
          </p>
        </div>
        <ReviewPreview />
      </LandingChapter>

      <LandingChapter
        id="coach-decision"
        className="landing-v10-coach-scene landing-v10-coach-decision-scene"
        aria-labelledby="landing-v10-coach-decision-title"
        data-coach-chapter="decision"
      >
        <div className="landing-v10-coach-copy">
          <p className="landing-kicker">07 / РЕШЕНИЕ И СЛЕДУЮЩИЙ ШАГ</p>
          <h2 id="landing-v10-coach-decision-title">
            Подтвердить,
            <br /> <em>а не угадывать.</em>
          </h2>
          <p>
            Предпросмотр изменения и черновик сообщения остаются отдельными действиями. Тренер
            выбирает, что делать дальше.
          </p>
        </div>
        <div className="landing-v10-coach-decision__previews">
          <RolloutPreview />
          <FollowUpPreview />
        </div>
      </LandingChapter>

      <LandingChapter
        className="landing-v10-coach-continuity"
        aria-labelledby="landing-v10-coach-continuity-title"
      >
        <div>
          <p className="landing-kicker">Браузер и мини-приложение Telegram</p>
          <h2 id="landing-v10-coach-continuity-title">Один аккаунт. Общий контекст.</h2>
          <p>
            Полный рабочий обзор остаётся в браузере, а быстрые действия доступны в мини-приложении
            Telegram.
          </p>
        </div>
        <div className="landing-v10-coach-continuity__rail" aria-label="Поверхности продукта">
          <span>
            <Icon name="web-app" /> Браузер
          </span>
          <Icon name="sync" size={24} />
          <strong>Общий контекст</strong>
          <Icon name="sync" size={24} />
          <span>
            <Icon name="mini-app" /> Мини-приложение Telegram
          </span>
        </div>
      </LandingChapter>

      <LandingV10Faq />

      <section className="landing-v10-coach-cta" aria-labelledby="landing-v10-coach-cta-title">
        <div>
          <p className="landing-kicker">ПУТЬ ТРЕНЕРА</p>
          <h2 id="landing-v10-coach-cta-title">Начните с рабочего контекста.</h2>
        </div>
        <div className="landing-v10-coach-cta__actions">
          <a
            className="landing-button"
            href={trainerLoginUrl}
            onClick={() =>
              trackProductEvent({
                name: 'trainer_landing_cta_clicked',
                surface: productEventSurface(),
                destination: 'onboarding',
              })
            }
          >
            Начать как тренер <Icon name="arrow-right" size={20} />
          </a>
          <a
            className="landing-button landing-button--secondary landing-button--secondary-on-dark"
            href={demoUrl}
            onClick={() =>
              trackProductEvent({
                name: 'landing_demo_selected',
                surface: productEventSurface(),
                placement: 'section',
                scenario: 'trainer',
              })
            }
          >
            Попробовать демо для тренера <Icon name="arrow-right" size={20} />
          </a>
        </div>
      </section>
    </LandingV10Shell>
  );
}
