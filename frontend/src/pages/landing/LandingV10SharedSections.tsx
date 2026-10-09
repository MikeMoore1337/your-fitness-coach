import { useRef, useState } from 'react';
import type { DemoScenario } from '../../features/demo/demoApi';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { demoCabinetUrlForHostname } from '../../shared/navigation/appUrl';
import { AppLink } from '../../shared/navigation/router';
import { PUBLIC_TELEGRAM_LINKS } from '../../shared/telegram/publicLinks';
import { BrandLockup } from '../../shared/ui/BrandLogo';
import { Icon, type IconName } from '../../shared/ui/Icon';
import { LandingChapter } from './LandingChapter';
import { LandingV10Faq } from './LandingV10Faq';
import { LandingV10Actions } from './LandingV10Hero';
import type { LandingAudience } from './landingAudience';

const links: {
  scenario: DemoScenario;
  title: string;
  description: string;
  section: string;
  icon: IconName;
}[] = [
  {
    scenario: 'self_training',
    title: 'Тренировка',
    description: 'Начните занятие и отметьте подход.',
    section: 'today',
    icon: 'exercise',
  },
  {
    scenario: 'nutrition',
    title: 'Питание',
    description: 'План, покупки и дневник.',
    section: 'nutrition',
    icon: 'nav-nutrition',
  },
  {
    scenario: 'trainer',
    title: 'Работа тренера',
    description: 'Клиент, обзор и следующий шаг.',
    section: 'trainer',
    icon: 'nav-coach',
  },
];
export function LandingV10SharedSections({
  audience,
  includeDifference = true,
}: {
  audience: LandingAudience;
  includeDifference?: boolean;
}) {
  const coach = audience === 'coach';
  const legalDialog = useRef<HTMLDialogElement>(null);
  const [legalTitle, setLegalTitle] = useState('');
  const showLegalPlaceholder = (title: string) => {
    setLegalTitle(title);
    legalDialog.current?.showModal();
  };
  const demos = coach ? [links[2]!, links[0]!, links[1]!] : links;
  return (
    <>
      {includeDifference && (
        <LandingChapter className="ref-section ref-difference">
          <div className="ref-copy">
            <p className="landing-kicker">ПОЧЕМУ YFC</p>
            <h2>
              Запись — начало.
              <br />
              Контекст —<br />
              продолжение.
            </h2>
            <p>
              Полезно не только знать, что произошло. Важно видеть, как это связано с планом и что
              проверить дальше.
            </p>
          </div>
          <div className="ref-difference-lines">
            {[
              ['ТРЕНИРОВКИ', 'Программа', 'подходы', 'динамика'],
              ['ПИТАНИЕ', 'План', 'покупки', 'дневник'],
              ['СОПРОВОЖДЕНИЕ', 'Проверка', 'обзор', 'решение'],
            ].map(([title, a, b, c]) => (
              <div key={title}>
                <small>{title}</small>
                <p>
                  {a}
                  <Icon name="arrow-right" size={16} />
                  {b}
                  <Icon name="arrow-right" size={16} />
                  {c}
                </p>
              </div>
            ))}
            <p className="ref-caption">
              Решение принимает человек. YFC не меняет план автоматически.
            </p>
          </div>
        </LandingChapter>
      )}
      <LandingChapter id="demo" className="ref-section ref-demo">
        <div className="ref-copy">
          <p className="landing-kicker">ПОСМОТРЕТЬ В ДЕЛЕ</p>
          <h2>
            Ваш сценарий.
            <br />
            Без личных данных.
          </h2>
          <p>
            В продукте есть отдельные подготовленные демо-сессии. Примеры на этой странице
            используют синтетические данные и не связаны с вашим аккаунтом.
          </p>
        </div>
        <nav aria-label="Сценарии демо">
          {demos.map((link) => (
            <a
              key={link.scenario}
              href={demoCabinetUrlForHostname(
                window.location.hostname,
                link.scenario,
                link.section,
              )}
              onClick={() =>
                trackProductEvent({
                  name: 'landing_demo_selected',
                  surface: productEventSurface(),
                  placement: 'section',
                  scenario: link.scenario,
                })
              }
            >
              <Icon name={link.icon} size={56} />
              <div>
                <h3>
                  {coach && link.scenario === 'self_training' ? 'Тренировка клиента' : link.title}
                </h3>
                <p>{link.description}</p>
              </div>
              <Icon name="arrow-right" size={24} />
            </a>
          ))}
        </nav>
      </LandingChapter>
      <LandingChapter id="continuity" className="ref-section ref-continuity">
        <div className="ref-copy">
          <p className="landing-kicker">БРАУЗЕР + МИНИ-ПРИЛОЖЕНИЕ TELEGRAM</p>
          <h2>
            Один аккаунт.
            <br />
            Ваш привычный вход.
          </h2>
          <p>
            Браузер — для полного контекста. Мини-приложение Telegram — для быстрых действий с теми
            же основными данными.
          </p>
        </div>
        <a
          className="ref-continuity-visual"
          href={PUBLIC_TELEGRAM_LINKS.miniApp}
          target="_blank"
          rel="noreferrer"
          aria-label="Открыть мини-приложение Telegram"
          onClick={() =>
            trackProductEvent({
              name: 'landing_telegram_selected',
              surface: productEventSurface(),
              placement: 'continuity',
            })
          }
        >
          <Icon name="web-app" size={80} />
          <div>
            <b>Общие данные</b>
            <Icon name="sync" size={56} />
            <span>Тренировки · питание · прогресс</span>
          </div>
          <Icon name="mini-app" size={80} />
        </a>
      </LandingChapter>
      <LandingV10Faq />
      <section className="ref-closing" id="contact">
        <p className="landing-kicker">ПЛАН. ДЕЙСТВИЕ. ПРОДОЛЖЕНИЕ.</p>
        <h2>
          {coach ? (
            <>
              Ваш метод.
              <br />
              Ваш следующий шаг.
            </>
          ) : (
            <>
              Сила в действии.
              <br />
              Начните со своего шага.
            </>
          )}
        </h2>
        <LandingV10Actions audience={audience} placement="section" />
      </section>
      <footer className="ref-footer">
        <div>
          <a href="#top" aria-label="Your Fitness Coach — на главную">
            <BrandLockup />
          </a>
          <p>
            Тренировки, питание и прогресс.
            <br />
            Самостоятельно или с тренером.
          </p>
        </div>
        <nav aria-label="Ссылки в подвале">
          <AppLink to="/training">Тренировки</AppLink>
          <AppLink to="/nutrition">Питание</AppLink>
          <AppLink to="/progress">Прогресс</AppLink>
          <a href="#faq">Приватность и вопросы</a>
          <button onClick={() => showLegalPlaceholder('Условия использования')}>
            Условия использования
          </button>
          <button onClick={() => showLegalPlaceholder('Политика конфиденциальности')}>
            Политика конфиденциальности
          </button>
        </nav>
        <p>
          Тренер — независимый пользователь сервиса.
          <br />
          YFC не сторона договора тренер–клиент.
          <br />© {new Date().getFullYear()} Your Fitness Coach
        </p>
      </footer>
      <dialog ref={legalDialog} className="ref-dialog" aria-labelledby="landing-legal-title">
        <h2 id="landing-legal-title">{legalTitle}</h2>
        <p>Это предварительная версия лендинга. Юридический документ ещё не подключён.</p>
        <p>Вопросы о данных и работе сервиса доступны в разделе «Понятные правила».</p>
        <form method="dialog">
          <button className="landing-button">Закрыть</button>
        </form>
      </dialog>
    </>
  );
}
