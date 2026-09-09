import { useEffect, useRef, useState, type ImgHTMLAttributes } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { WebArticleCard } from '../../shared/api/types';
import { api } from '../../shared/api/client';
import {
  productEventSurface,
  trackProductEvent,
  type LandingTelegramPlacement,
} from '../../shared/analytics/productEvents';
import {
  appUrlForHostname,
  demoUrlForHostname,
  loginUrlForHostname,
} from '../../shared/navigation/appUrl';
import { AppLink } from '../../shared/navigation/router';
import { applyRouteMetadata } from '../../shared/seo/metadata';
import { PUBLIC_TELEGRAM_LINKS } from '../../shared/telegram/publicLinks';
import { BrandLockup, BrandLogo } from '../../shared/ui/BrandLogo';
import { Icon, type IconName } from '../../shared/ui/Icon';
import { PublicShell } from '../../shared/ui/PublicShell';
import { useWebTheme } from '../../shared/useWebTheme';
import { StrengthScene } from './StrengthScene';
import { LandingChapter } from './LandingChapter';
import './landing.css';

export {
  appUrlForHostname,
  demoUrlForHostname,
  loginUrlForHostname,
} from '../../shared/navigation/appUrl';

type DemoScenario = 'self_training' | 'nutrition' | 'trainer';

const coreFeatures: ReadonlyArray<{
  icon: IconName;
  index: string;
  label: string;
  title: string;
  text: string;
  href: string;
  linkLabel: string;
}> = [
  {
    icon: 'week-strength',
    index: '01',
    label: 'Сегодня и тренировка',
    title: 'Сначала — одно понятное действие.',
    text: 'Экран «Сегодня» собирает недельный контекст и ближайшую тренировку. Во время занятия остаются вес, повторы, выполненные подходы и отдых — без ручного подсчёта.',
    href: '/training',
    linkLabel: 'Как устроены тренировки',
  },
  {
    icon: 'nav-nutrition',
    index: '02',
    label: 'Питание',
    title: 'Ориентир рядом с фактическими записями.',
    text: 'Дневник различает заполненный, неполный и пропущенный день. Калории и КБЖУ остаются ориентирами, а отсутствие записи не превращается в ноль.',
    href: '/nutrition',
    linkLabel: 'Подробнее о питании',
  },
  {
    icon: 'nav-progress',
    index: '03',
    label: 'Прогресс',
    title: 'Выводы только там, где хватает данных.',
    text: 'Тренировки, питание и измерения показаны по периодам. Если записей мало, интерфейс объяснит ограничение вместо сильного вывода из одной точки.',
    href: '/progress',
    linkLabel: 'Как читать прогресс',
  },
];

const workflow: ReadonlyArray<{
  icon: IconName;
  number: string;
  title: string;
  text: string;
}> = [
  {
    icon: 'nav-today',
    number: '01',
    title: 'Откройте план на сегодня',
    text: 'Экран «Сегодня» показывает ближайшую запланированную тренировку и контекст недели.',
  },
  {
    icon: 'week-strength',
    number: '02',
    title: 'Фиксируйте факты',
    text: 'Отмечайте выполненные подходы, добавляйте питание и замеры по ходу дня.',
  },
  {
    icon: 'nav-progress',
    number: '03',
    title: 'Сверяйтесь с динамикой',
    text: 'Смотрите подтверждённые изменения и ограничения данных перед следующим шагом.',
  },
];

const demoScenarios: ReadonlyArray<{
  value: DemoScenario;
  eyebrow: string;
  title: string;
  text: string;
}> = [
  {
    value: 'self_training',
    eyebrow: 'Для себя',
    title: 'Пройдите тренировку',
    text: 'Начните занятие, отметьте подходы и посмотрите, как результат становится частью прогресса.',
  },
  {
    value: 'nutrition',
    eyebrow: 'Дневник',
    title: 'Добавьте питание',
    text: 'Запишите недавний продукт и откройте дневной итог рядом с фактическими ориентирами.',
  },
  {
    value: 'trainer',
    eyebrow: 'Клиент',
    title: 'Посмотрите кабинет тренера',
    text: 'Откройте результат подготовленного клиента и сохраните контекстный комментарий.',
  },
];

const faqs = [
  {
    question: 'Telegram обязателен?',
    answer:
      'Нет. Тренировки, питание и прогресс доступны в браузере. Telegram Mini App — быстрый дополнительный вход к тем же основным сценариям и удобный переход к общению с тренером.',
  },
  {
    question: 'Что произойдёт с изменениями в демо?',
    answer:
      'Они останутся только в подготовленной демо-сессии и не перенесутся в аккаунт. После входа вы начнёте настройку чистого профиля со своими данными.',
  },
  {
    question: 'Нужно подавать заявку, чтобы стать тренером?',
    answer:
      'Нет. После входа пользователь может сразу включить режим тренера в профиле. Это добавляет кабинет клиентов, но не заменяет CRM, платежи, расписание бизнеса или мессенджер.',
  },
  {
    question: 'Приложение само меняет программу или питание?',
    answer:
      'Нет. Приложение показывает план, факты и объяснимые ориентиры. Изменения программы и целей остаются явными действиями пользователя или его тренера.',
  },
  {
    question: 'Можно ли управлять своими данными?',
    answer:
      'В профиле доступны экспорт данных, отвязка способов входа и удаление аккаунта. Данные подготовленных демо-сценариев отделены от реальных аккаунтов.',
  },
] as const;

function cabinetScenarioUrl(baseUrl: string, scenario: DemoScenario): string {
  const section =
    scenario === 'nutrition' ? 'nutrition' : scenario === 'trainer' ? 'trainer' : 'today';
  return `${baseUrl}?cabinet=1&scenario=${scenario}&section=${section}`;
}

type ProductScreenshotProps = Pick<
  ImgHTMLAttributes<HTMLImageElement>,
  'alt' | 'className' | 'fetchPriority' | 'height' | 'loading' | 'src' | 'width'
> & { fallback: string };

function ProductScreenshot({ fallback, className = '', ...imageProps }: ProductScreenshotProps) {
  const [failedSrc, setFailedSrc] = useState<string>();
  const [loadedSrc, setLoadedSrc] = useState<string>();
  const failed = failedSrc === imageProps.src;
  const loaded = loadedSrc === imageProps.src;

  return (
    <span className={`landing-product-image ${loaded ? 'is-loaded' : ''} ${className}`.trim()}>
      <span className="landing-product-image__fallback">{fallback}</span>
      {!failed && (
        <img
          {...imageProps}
          className={loaded ? 'is-loaded' : ''}
          decoding="async"
          onLoad={() => setLoadedSrc(imageProps.src)}
          onError={() => setFailedSrc(imageProps.src)}
        />
      )}
    </span>
  );
}

export default function LandingPage() {
  const appUrl = appUrlForHostname(window.location.hostname);
  const loginUrl = loginUrlForHostname(window.location.hostname);
  const demoUrl = demoUrlForHostname(window.location.hostname);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { colorScheme } = useWebTheme();
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const navigationRef = useRef<HTMLElement>(null);
  const publishedArticles = useQuery({
    queryKey: ['public', 'articles'],
    queryFn: () => api<WebArticleCard[]>('/api/v1/public/articles'),
  });

  useEffect(() => {
    let mounted = true;
    void import('../../content/publicContent').then(({ getPublicContentPage }) => {
      if (mounted) applyRouteMetadata('/', getPublicContentPage('/'));
    });
    trackProductEvent(
      { name: 'landing_viewed', surface: productEventSurface() },
      { dedupe: 'session' },
    );
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setMobileMenuOpen(false);
      menuButtonRef.current?.focus();
    };
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (navigationRef.current?.contains(target) || menuButtonRef.current?.contains(target))
        return;
      setMobileMenuOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    window.addEventListener('pointerdown', closeOnOutsidePointer);
    return () => {
      window.removeEventListener('keydown', closeOnEscape);
      window.removeEventListener('pointerdown', closeOnOutsidePointer);
    };
  }, [mobileMenuOpen]);

  const trackAppSelection = () =>
    trackProductEvent({ name: 'landing_app_selected', surface: productEventSurface() });
  const trackDemoSelection = () =>
    trackProductEvent({ name: 'landing_demo_selected', surface: productEventSurface() });
  const trackTelegramSelection = (placement: LandingTelegramPlacement) =>
    trackProductEvent({
      name: 'landing_telegram_selected',
      surface: productEventSurface(),
      placement,
    });

  return (
    <PublicShell
      className="landing-page"
      homeHref="#top"
      skipTarget="landing-content"
      headerNavigation={
        <nav
          ref={navigationRef}
          id="landing-navigation"
          className={`landing-nav${mobileMenuOpen ? ' is-open' : ''}`}
          aria-label="Навигация по странице"
        >
          <a href="#product" onClick={() => setMobileMenuOpen(false)}>
            Продукт
          </a>
          <a href="#demo" onClick={() => setMobileMenuOpen(false)}>
            Демо
          </a>
          <a href="#faq" onClick={() => setMobileMenuOpen(false)}>
            Вопросы
          </a>
        </nav>
      }
      headerAction={
        <>
          <a
            className="landing-button landing-button--compact"
            href={loginUrl}
            onClick={() =>
              trackProductEvent({ name: 'landing_login_selected', surface: productEventSurface() })
            }
          >
            Войти
          </a>
          <button
            ref={menuButtonRef}
            type="button"
            className={`landing-menu-toggle${mobileMenuOpen ? ' is-open' : ''}`}
            aria-label={mobileMenuOpen ? 'Закрыть меню' : 'Открыть меню'}
            aria-expanded={mobileMenuOpen}
            aria-controls="landing-navigation"
            onClick={() => setMobileMenuOpen((open) => !open)}
          >
            <Icon name={mobileMenuOpen ? 'close' : 'menu'} />
          </button>
        </>
      }
    >
      <main id="landing-content" tabIndex={-1}>
        <section className="landing-hero" aria-labelledby="landing-title">
          <div className="landing-hero__copy">
            <p className="landing-kicker">Тренировки. Питание. Ваш прогресс.</p>
            <h1 id="landing-title">
              <span>Движение.</span> <span>Запись.</span> <span>Прогресс.</span>
            </h1>
            <p className="landing-hero__lead">
              Тренировки и питание — в фактах. Прогресс — по вашим записям.
            </p>
            <div className="landing-hero__actions">
              <a className="landing-button" href={appUrl} onClick={trackAppSelection}>
                Начать <Icon name="arrow-right" size={20} />
              </a>
              <a
                className="landing-button landing-button--secondary"
                href={cabinetScenarioUrl(demoUrl, 'self_training')}
                onClick={trackDemoSelection}
              >
                Попробовать демо <Icon name="arrow-right" size={20} />
              </a>
            </div>
            <div className="landing-hero__platform">
              <p className="landing-hero__platform-note">
                <Icon name="web-app" size={16} /> Web и Telegram Mini App · один аккаунт и общие
                данные
              </p>
              <a
                className="landing-hero__telegram-link"
                href={PUBLIC_TELEGRAM_LINKS.miniApp}
                target="_blank"
                rel="noreferrer"
                onClick={() => trackTelegramSelection('hero')}
              >
                Открыть в Telegram <Icon name="external-link" size={16} />
              </a>
            </div>
          </div>

          <StrengthScene />
        </section>

        <LandingChapter id="product" className="landing-core" aria-labelledby="product-title">
          <div className="landing-core__intro">
            <header>
              <p className="landing-kicker">Продукт в действии</p>
              <h2 id="product-title">Один цикл — от плана до следующего шага.</h2>
              <p>
                «Сегодня» показывает план. Выполненные тренировки, питание и замеры добавляют факты.
                Progress показывает динамику и честно отмечает, когда данных пока мало.
              </p>
              <div className="landing-core__self">
                <p className="landing-kicker">Занимаетесь самостоятельно?</p>
                <h3>Начните сами. Тренера можно подключить позже.</h3>
                <p>
                  Выберите готовую программу или соберите свою. Выполняйте занятия и отслеживайте
                  фактическую динамику в браузере — Telegram для этого не нужен.
                </p>
                <AppLink className="landing-core__self-link" to="/training">
                  Начать с тренировок <Icon name="arrow-right" size={20} />
                </AppLink>
              </div>
            </header>
            <div className="landing-core__proof" aria-label="Актуальные Web и Mobile Web экраны">
              <figure className="landing-core__desktop">
                <ProductScreenshot
                  src={`/assets/product/landing-today-desktop-${colorScheme}.webp`}
                  alt="Актуальный экран Сегодня в desktop Web"
                  width={1440}
                  height={900}
                  loading="lazy"
                  fallback="Desktop proof временно недоступен."
                />
              </figure>
              <figure className="landing-core__mobile">
                <ProductScreenshot
                  src={`/assets/product/landing-today-mobile-${colorScheme}.webp`}
                  alt="Актуальный экран Сегодня в Mobile Web"
                  width={390}
                  height={844}
                  loading="lazy"
                  fallback="Mobile proof временно недоступен."
                />
              </figure>
              <div className="landing-core__context">
                <BrandLogo decorative surface={colorScheme} variant="mark" width={38} height={38} />
                <span>Один профиль</span>
                <strong>План → факт → динамика → следующий шаг</strong>
              </div>
            </div>
          </div>

          <div className="landing-core__features" aria-label="Тренировки, питание и прогресс">
            {coreFeatures.map((feature) => (
              <article key={feature.index}>
                <div className="landing-core__feature-label">
                  <span>{feature.index}</span>
                  <Icon name={feature.icon} size={20} />
                  <small>{feature.label}</small>
                </div>
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
                <AppLink to={feature.href}>{feature.linkLabel}</AppLink>
              </article>
            ))}
          </div>
        </LandingChapter>

        {publishedArticles.data && publishedArticles.data.length > 0 && (
          <section className="landing-articles" aria-labelledby="landing-articles-title">
            <div className="landing-articles__intro">
              <p className="landing-kicker">Разобраться до действия</p>
              <h2 id="landing-articles-title">Избранные материалы</h2>
              <p>
                Короткий путь к понятному контексту: тренировки, питание и прогресс с источниками и
                честными ограничениями.
              </p>
              <AppLink className="landing-core__self-link" to="/articles">
                Все статьи <Icon name="arrow-right" size={20} />
              </AppLink>
            </div>
            <div className="landing-articles__grid">
              {publishedArticles.data.slice(0, 3).map((article) => (
                <article key={article.slug}>
                  <small>{article.topics[0] ?? 'YFC'}</small>
                  <h3>
                    <AppLink to={`/articles/${article.slug}`}>{article.title}</AppLink>
                  </h3>
                  <p>{article.description}</p>
                </article>
              ))}
            </div>
          </section>
        )}

        <LandingChapter className="landing-trainer" aria-labelledby="trainer-title">
          <div className="landing-trainer__copy">
            <p className="landing-kicker">04 · Работа с тренером</p>
            <h2 id="trainer-title">У каждого клиента — видимый контекст.</h2>
            <p>
              Тренер включает режим из профиля, приглашает клиента, назначает программу, видит
              выполненную работу и оставляет комментарии к конкретным тренировкам. CRM, платежи и
              расписание бизнеса остаются за пределами продукта.
            </p>
            <AppLink className="landing-button" to="/for-trainers">
              Посмотреть кабинет тренера <Icon name="arrow-right" size={20} />
            </AppLink>
          </div>
          <figure className="landing-trainer__proof">
            <ProductScreenshot
              src={`/assets/product/landing-trainer-desktop-${colorScheme}.webp`}
              alt="Актуальный кабинет тренера с подготовленными данными клиента"
              width={1280}
              height={972}
              loading="lazy"
              fallback="Экран кабинета тренера временно недоступен."
            />
          </figure>
        </LandingChapter>

        <LandingChapter id="demo" className="landing-start" aria-labelledby="start-title">
          <header>
            <p className="landing-kicker">Как это работает</p>
            <h2 id="start-title">От настройки — к повторяемому ритму.</h2>
          </header>
          <ol className="landing-start__steps">
            {workflow.map((step) => (
              <li key={step.number}>
                <span aria-hidden="true">
                  <Icon name={step.icon} />
                </span>
                <small>{step.number}</small>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </li>
            ))}
          </ol>
          <div className="landing-start__demo">
            <div>
              <p className="landing-kicker">Демо без регистрации</p>
              <h3>Три сценария. Никаких реальных данных.</h3>
              <p>
                Изменения живут только в отдельной подготовленной сессии и не переносятся в аккаунт.
                Приглашения, уведомления и действия с реальными пользователями заблокированы.
              </p>
            </div>
            <nav aria-label="Демо-сценарии">
              {demoScenarios.map((scenario, index) => (
                <a
                  key={scenario.value}
                  href={cabinetScenarioUrl(demoUrl, scenario.value)}
                  onClick={trackDemoSelection}
                >
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <small>{scenario.eyebrow}</small>
                    <strong>{scenario.title}</strong>
                    <p>{scenario.text}</p>
                  </div>
                  <Icon name="arrow-right" size={20} />
                </a>
              ))}
            </nav>
          </div>
        </LandingChapter>

        <LandingChapter id="faq" className="landing-assurance" aria-labelledby="faq-title">
          <div className="landing-assurance__platform">
            <div className="landing-continuity__copy">
              <p className="landing-kicker">Один продукт на двух поверхностях</p>
              <h2 id="continuity-title">
                Web для полного контекста. Telegram — для быстрых действий.
              </h2>
              <p>
                Полный продукт на компьютере и смартфоне без отдельной установки. Telegram Mini App
                не является отдельным приложением или библиотекой статей: интерфейс, тема и основные
                данные общие с Mobile Web. Тренировка, питание, краткий прогресс и переход к общению
                с тренером.
              </p>
              <a
                className="landing-button landing-continuity__action"
                href={PUBLIC_TELEGRAM_LINKS.miniApp}
                target="_blank"
                rel="noreferrer"
                onClick={() => trackTelegramSelection('continuity')}
              >
                Открыть приложение в Telegram <Icon name="external-link" size={20} />
              </a>
            </div>
            <div className="landing-continuity__rail" aria-label="Один аккаунт и общие данные">
              <span>
                <Icon name="web-app" /> Web
              </span>
              <Icon name="sync" size={24} />
              <strong>Один аккаунт · общие данные</strong>
              <Icon name="sync" size={24} />
              <span>
                <Icon name="mini-app" /> Telegram Mini App
              </span>
            </div>
          </div>
          <header>
            <p className="landing-kicker">Честные ограничения</p>
            <h2 id="faq-title">Перед тем как начать.</h2>
          </header>
          <div className="landing-assurance__grid">
            <div className="landing-faq-list">
              {faqs.map((item) => (
                <details key={item.question}>
                  <summary>
                    {item.question}
                    <Icon name="plus" size={20} />
                  </summary>
                  <p>{item.answer}</p>
                </details>
              ))}
            </div>
            <div className="landing-assurance__details">
              <details>
                <summary>
                  <span>
                    <small>Разобраться до действия</small>
                    <strong>Короткий путь к проверяемому объяснению.</strong>
                  </span>
                  <Icon name="plus" size={20} />
                </summary>
                <div>
                  <p>
                    Публичные материалы помогают понять тренировочный план, ориентиры питания и
                    ограничения прогресса. Они не заменяют индивидуальную медицинскую помощь.
                  </p>
                  <nav aria-label="Материалы о продукте и тренировках">
                    <AppLink to="/training">Тренировки и программы</AppLink>
                    <AppLink to="/nutrition">Питание и КБЖУ</AppLink>
                    <AppLink to="/progress">Прогресс и измерения</AppLink>
                    <AppLink to="/knowledge">База знаний</AppLink>
                  </nav>
                </div>
              </details>
              <details id="privacy">
                <summary>
                  <span>
                    <small>Приватность без входа</small>
                    <strong>Ваши данные остаются под вашим управлением.</strong>
                  </span>
                  <Icon name="plus" size={20} />
                </summary>
                <div>
                  <p>
                    До регистрации можно понять, какие данные использует продукт и какие действия с
                    ними доступны. Вход нужен только для управления конкретным аккаунтом.
                  </p>
                  <ul>
                    <li>
                      <strong>Только данные продукта.</strong> Профиль, тренировки, питание и
                      прогресс сохраняются после входа и используются для работы функций Your
                      Fitness Coach.
                    </li>
                    <li>
                      <strong>Демо изолировано.</strong> Подготовленные демо-данные не относятся к
                      реальным пользователям и не становятся данными вашего аккаунта.
                    </li>
                    <li>
                      <strong>Доступны контроль и удаление.</strong> После входа в профиле можно
                      экспортировать данные, отвязать способы входа или удалить аккаунт.
                    </li>
                  </ul>
                </div>
              </details>
            </div>
          </div>
        </LandingChapter>

        <section id="contact" className="landing-contact">
          <div>
            <p className="landing-kicker">Ваш следующий шаг</p>
            <h2>Начните с одного понятного шага.</h2>
            <p>
              Откройте свой профиль или сначала проверьте связный сценарий в демо без регистрации.
            </p>
          </div>
          <div className="landing-contact__actions">
            <a className="landing-button" href={appUrl} onClick={trackAppSelection}>
              Открыть приложение <Icon name="arrow-right" size={20} />
            </a>
            <a
              className="landing-button landing-button--secondary"
              href={cabinetScenarioUrl(demoUrl, 'self_training')}
              onClick={trackDemoSelection}
            >
              Попробовать демо <Icon name="arrow-right" size={20} />
            </a>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="landing-footer__brand">
          <a className="landing-brand" href="#top" aria-label="Your Fitness Coach — на главную">
            <BrandLockup className="landing-footer__lockup" markClassName="landing-brand__mark" />
          </a>
          <p>Тренировки, питание и прогресс — самостоятельно или вместе с тренером.</p>
        </div>
        <nav aria-label="Ссылки в подвале">
          <AppLink to="/training">Тренировки</AppLink>
          <AppLink to="/nutrition">Питание</AppLink>
          <AppLink to="/knowledge">База знаний</AppLink>
          <a href="#demo">Условия демо</a>
          <a href="#faq">Вопросы</a>
          <a href="#privacy">Приватность и данные</a>
          <a
            className="landing-footer__telegram-app"
            href={PUBLIC_TELEGRAM_LINKS.miniApp}
            target="_blank"
            rel="noreferrer"
            onClick={() => trackTelegramSelection('footer')}
          >
            Открыть в Telegram <Icon name="external-link" size={16} />
          </a>
          <a
            className="landing-footer__channel"
            href={PUBLIC_TELEGRAM_LINKS.news}
            target="_blank"
            rel="noreferrer"
          >
            Telegram-канал о фитнесе и здоровье
          </a>
          <a href={PUBLIC_TELEGRAM_LINKS.support} target="_blank" rel="noreferrer">
            Поддержка в Telegram
          </a>
        </nav>
        <div className="landing-footer__privacy">
          <strong>Управление данными</strong>
          <p>Экспорт, отвязка способов входа и удаление аккаунта доступны в профиле.</p>
          <span>© {new Date().getFullYear()} Your Fitness Coach</span>
        </div>
      </footer>
    </PublicShell>
  );
}
