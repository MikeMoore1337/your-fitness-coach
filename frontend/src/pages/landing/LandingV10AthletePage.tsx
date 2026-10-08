import { useState } from 'react';
import { appUrlForHostname, demoUrlForHostname } from '../../shared/navigation/appUrl';
import { Icon } from '../../shared/ui/Icon';
import { LandingChapter } from './LandingChapter';
import { LandingPractice } from './LandingPractice';
import { LandingProgress } from './LandingProgress';
import { LandingV10Shell } from './LandingV10Shell';
import { StrengthScene } from './StrengthScene';
import { useLandingHeroMotion } from './useLandingHeroMotion';
import './landing.css';

type NutritionView = 'plan' | 'shopping' | 'diary';

const NUTRITION_VIEWS: ReadonlyArray<{
  id: NutritionView;
  label: string;
  title: string;
  body: string;
  value: string;
}> = [
  {
    id: 'plan',
    label: 'План',
    title: 'Ориентир на день',
    body: 'План помогает собрать следующий приём пищи и остаётся ориентиром, пока фактическая запись не внесена.',
    value: 'Белок 128 г · 2 180 ккал',
  },
  {
    id: 'shopping',
    label: 'Покупки',
    title: 'Список из плана',
    body: 'Ингредиенты из выбранного плана собраны в один список, чтобы действие не терялось между экранами.',
    value: '12 позиций · 3 отмечены',
  },
  {
    id: 'diary',
    label: 'Дневник',
    title: 'Что было фактически',
    body: 'Дневник показывает внесённое отдельно от планов. Нет записи — это пропуск данных, а не нулевое потребление.',
    value: 'Записано 2 приёма · 1 без записи',
  },
] as const;

const CYCLE_STEPS = [
  ['01', 'План', 'Откройте ближайшее действие и контекст недели.'],
  ['02', 'Действие', 'Сделайте подход, внесите питание или отметьте замер.'],
  ['03', 'Факты', 'Отделите выполненное от запланированного и пропущенного.'],
  ['04', 'Решение', 'Выберите следующий шаг по данным, которых достаточно.'],
] as const;

function NutritionPreview() {
  const [view, setView] = useState<NutritionView>('plan');
  const active = NUTRITION_VIEWS.find((item) => item.id === view) ?? NUTRITION_VIEWS[0]!;

  return (
    <div className="landing-v10-nutrition__preview" data-testid="nutrition-preview">
      <div className="landing-v10-nutrition__tabs" role="tablist" aria-label="Состояния питания">
        {NUTRITION_VIEWS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item.id === view}
            aria-controls={`nutrition-panel-${item.id}`}
            onClick={() => setView(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        id={`nutrition-panel-${active.id}`}
        className="landing-v10-nutrition__panel"
        role="tabpanel"
        aria-live="polite"
      >
        <div className="landing-v10-nutrition__panel-heading">
          <Icon name="nav-nutrition" size={24} />
          <div>
            <small>ПОДГОТОВЛЕННЫЙ ПРЕВЬЮ-СЦЕНАРИЙ</small>
            <h3>{active.title}</h3>
          </div>
        </div>
        <strong>{active.value}</strong>
        <p>{active.body}</p>
      </div>
    </div>
  );
}

function WeeklyReview() {
  const [score, setScore] = useState<number>();

  return (
    <div className="landing-v10-review" data-testid="weekly-review">
      <div className="landing-v10-review__heading">
        <Icon name="nav-progress" size={24} />
        <div>
          <small>ПОДГОТОВЛЕННЫЙ ПРЕВЬЮ-СЦЕНАРИЙ</small>
          <h3>Проверка недели</h3>
        </div>
      </div>
      <p>Насколько понятным был ваш ритм на этой неделе?</p>
      <div className="landing-v10-review__scale" role="group" aria-label="Оценка недели">
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
      <p className="landing-v10-review__note" role="status">
        {score
          ? `Отмечено: ${score} из 5. Это локальный ответ превью.`
          : 'Ответ остаётся на этом экране.'}
      </p>
    </div>
  );
}

function AthleteHero() {
  const [heroUnavailable, setHeroUnavailable] = useState(false);
  const appUrl = appUrlForHostname(window.location.hostname);
  const demoUrl = demoUrlForHostname(window.location.hostname);

  return (
    <section className="landing-hero" aria-labelledby="landing-v10-athlete-title">
      <img
        className="landing-hero__image"
        src="/assets/marketing/strength-hero.webp"
        alt="Спортсменка толкает тренировочные сани"
        fetchPriority="high"
        width="1536"
        height="1024"
        onError={() => setHeroUnavailable(true)}
        hidden={heroUnavailable}
      />
      <div className="landing-hero__copy">
        {heroUnavailable && <p role="status">Фото не загрузилось. Все действия доступны.</p>}
        <p className="landing-kicker">ПЛАН. ДЕЙСТВИЕ. РЕЗУЛЬТАТ.</p>
        <h1 id="landing-v10-athlete-title">
          <span>СИЛА</span> <span>В ДЕЙСТВИИ.</span>
        </h1>
        <p className="landing-hero__lead">Тренировки, питание и прогресс — в одном месте.</p>
        <div className="landing-hero__actions">
          <a className="landing-button" href={appUrl}>
            Начать со своими данными <Icon name="arrow-right" size={20} />
          </a>
          <a
            className="landing-button landing-button--secondary"
            href={`${demoUrl}?cabinet=1&scenario=self_training&section=today`}
          >
            Попробовать демо <Icon name="arrow-right" size={20} />
          </a>
        </div>
        <div className="landing-hero__platform">
          <p className="landing-hero__platform-note">
            <Icon name="web-app" size={16} /> Web и Telegram Mini App
          </p>
        </div>
      </div>
    </section>
  );
}

export default function LandingV10AthletePage() {
  useLandingHeroMotion();
  const demoUrl = demoUrlForHostname(window.location.hostname);

  return (
    <LandingV10Shell audience="athlete">
      <AthleteHero />

      <LandingChapter className="landing-v10-cycle" aria-labelledby="landing-v10-cycle-title">
        <div className="landing-v10-cycle__intro">
          <p className="landing-kicker">01 / СВЯЗАННЫЙ РИТМ</p>
          <h2 id="landing-v10-cycle-title">
            От первого действия
            <br /> <em>к следующему решению.</em>
          </h2>
          <p>
            В одном сценарии видно, что было запланировано, что сделано и какие факты уже можно
            использовать.
          </p>
          <div className="landing-v10-program-proof">
            <Icon name="nav-today" size={24} />
            <div>
              <small>ПОДГОТОВЛЕННЫЙ ПРЕВЬЮ-СЦЕНАРИЙ</small>
              <strong>Силовой блок на неделю</strong>
              <span>3 тренировки · следующая — сегодня</span>
            </div>
          </div>
        </div>
        <ol className="landing-v10-cycle__list">
          {CYCLE_STEPS.map(([number, title, text]) => (
            <li key={number}>
              <small>{number}</small>
              <Icon name="checklist" size={24} />
              <h3>{title}</h3>
              <p>{text}</p>
            </li>
          ))}
        </ol>
      </LandingChapter>

      <StrengthScene />

      <LandingChapter className="landing-practice" aria-labelledby="landing-v10-practice-title">
        <div>
          <p className="landing-kicker">03 / В ДЕЛЕ</p>
          <h2 id="landing-v10-practice-title">
            Вошли в ритм.
            <br /> <em>Продолжайте.</em>
          </h2>
          <p>Попробуйте подготовленный сценарий: откройте тренировку и запишите подход.</p>
          <div className="landing-practice__note">
            <Icon name="exercise" size={80} />
            <small>
              Демо без регистрации.
              <br /> Отдельная подготовленная сессия.
            </small>
          </div>
        </div>
        <LandingPractice />
      </LandingChapter>

      <LandingChapter
        className="landing-v10-nutrition landing-feature"
        aria-labelledby="landing-v10-nutrition-title"
      >
        <div>
          <p className="landing-kicker">04 / ПИТАНИЕ</p>
          <h2 id="landing-v10-nutrition-title">Ориентир рядом с фактами.</h2>
          <p>
            План, покупки и дневник связаны в одном понятном контексте. Запланированное не выдаётся
            за съеденное, а пропущенная запись не превращается в ноль.
          </p>
        </div>
        <NutritionPreview />
      </LandingChapter>

      <LandingChapter className="landing-v10-progress" aria-labelledby="landing-v10-progress-title">
        <div>
          <p className="landing-kicker">05 / ПРОГРЕСС</p>
          <h2 id="landing-v10-progress-title">Смотрите на движение недели.</h2>
          <p>
            Сводка использует подтверждённые записи и показывает границы данных перед следующим
            действием.
          </p>
        </div>
        <div className="landing-v10-progress__grid">
          <LandingProgress href={`${demoUrl}?cabinet=1&scenario=self_training&section=progress`} />
          <WeeklyReview />
        </div>
      </LandingChapter>

      <LandingChapter className="landing-v10-coach-promo" aria-labelledby="landing-v10-coach-title">
        <div className="landing-v10-coach-promo__mark" aria-hidden="true">
          <Icon name="nav-coach" size={56} />
          <span>ДЛЯ ТРЕНЕРА</span>
        </div>
        <div>
          <h2 id="landing-v10-coach-title">
            <span>Вы тренер?</span> <span>Знакомьтесь с Coach OS.</span>
          </h2>
          <p>
            Подключайте клиентов, ведите версии программ, смотрите проверки и подтверждайте
            следующий шаг в одном рабочем цикле.
          </p>
        </div>
        <a className="landing-button" href="/for-trainers">
          Возможности для тренера <Icon name="arrow-right" size={20} />
        </a>
      </LandingChapter>

      <LandingChapter
        className="landing-v10-continuity"
        aria-labelledby="landing-v10-continuity-title"
      >
        <div>
          <p className="landing-kicker">ВЕБ И TELEGRAM MINI APP</p>
          <h2 id="landing-v10-continuity-title">Один аккаунт. Общие данные.</h2>
          <p>
            Полный контекст остаётся в Web, а быстрые действия доступны в Telegram Mini App — без
            отдельной версии продукта.
          </p>
        </div>
        <div className="landing-v10-continuity__rail" aria-label="Поверхности продукта">
          <span>
            <Icon name="web-app" /> Web
          </span>
          <Icon name="sync" size={24} />
          <strong>Общие данные</strong>
          <Icon name="sync" size={24} />
          <span>
            <Icon name="mini-app" /> Telegram Mini App
          </span>
        </div>
      </LandingChapter>
    </LandingV10Shell>
  );
}
