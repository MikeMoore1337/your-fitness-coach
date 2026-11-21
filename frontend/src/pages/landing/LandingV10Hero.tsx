import { useState } from 'react';
import { appUrlForHostname, demoCabinetUrlForHostname } from '../../shared/navigation/appUrl';
import { trainerIntentLoginUrl } from '../../shared/auth/trainerIntent';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { glassProps } from '../../shared/ui/Glass';
import { Icon } from '../../shared/ui/Icon';
import { LandingAudienceSwitch } from './LandingAudienceSwitch';
import { LandingChapter } from './LandingChapter';
import type { LandingAudience } from './landingAudience';

export function LandingV10Actions({
  audience,
  placement = 'hero',
}: {
  audience: LandingAudience;
  placement?: 'hero' | 'section';
}) {
  const coach = audience === 'coach';
  const hostname = window.location.hostname;
  const primaryHref = coach ? trainerIntentLoginUrl(hostname) : appUrlForHostname(hostname);
  const secondaryHref = demoCabinetUrlForHostname(
    hostname,
    coach ? 'trainer' : 'self_training',
    coach ? 'trainer' : 'today',
  );
  const primaryLabel = coach ? 'Начать как тренер' : 'Начать со своими данными';
  const secondaryLabel = coach ? 'Попробовать демо для тренера' : 'Попробовать демо тренировки';
  const primaryEvent = coach
    ? {
        name: 'trainer_landing_cta_clicked' as const,
        surface: productEventSurface(),
        destination: 'onboarding' as const,
      }
    : { name: 'landing_app_selected' as const, surface: productEventSurface() };
  const secondaryEvent = {
    name: 'landing_demo_selected' as const,
    surface: productEventSurface(),
    placement,
    scenario: coach ? ('trainer' as const) : ('self_training' as const),
  };
  return (
    <div className="landing-hero__actions">
      <a
        className="landing-button"
        href={primaryHref}
        onClick={() => trackProductEvent(primaryEvent)}
      >
        {primaryLabel} <Icon name="arrow-right" size={20} />
      </a>
      <a
        className="landing-button landing-button--secondary landing-button--secondary-on-dark"
        {...glassProps('clear', true)}
        data-glass-tone="on-image"
        href={secondaryHref}
        onClick={() => trackProductEvent(secondaryEvent)}
      >
        {secondaryLabel} <Icon name="arrow-right" size={20} />
      </a>
    </div>
  );
}

export function LandingV10Hero({ audience }: { audience: LandingAudience }) {
  const coach = audience === 'coach';
  const [unavailable, setUnavailable] = useState(false);
  return (
    <section id="top" className="landing-hero ref-hero" aria-labelledby="landing-title">
      <img
        className="landing-hero__image"
        src={`/assets/marketing/${coach ? 'trainer-photo' : 'strength-hero'}.webp`}
        alt={
          coach ? 'Тренер и спортсменка обсуждают план' : 'Спортсменка толкает тренировочные сани'
        }
        width="1536"
        height="1024"
        fetchPriority="high"
        hidden={unavailable}
        onError={() => setUnavailable(true)}
      />
      <div className="landing-v10-hero-audience">
        <LandingAudienceSwitch audience={audience} showLabel={false} />
      </div>
      <div className="landing-hero__copy">
        {unavailable && <p role="status">Фото не загрузилось. Все действия доступны.</p>}
        <p className="landing-kicker">
          {coach ? 'КЛИЕНТ · ПРОГРАММА · ФАКТЫ · РЕШЕНИЕ' : 'ПЛАН · ДЕЙСТВИЕ · ФАКТЫ · РЕШЕНИЕ'}
        </p>
        <h1 id="landing-title">
          <span>{coach ? 'ВАШ МЕТОД' : 'СИЛА'}</span> <span>В ДЕЙСТВИИ.</span>
        </h1>
        <p className="landing-hero__lead">
          {coach
            ? 'Программы, проверки и история клиента — в одном рабочем пространстве. Видеть важное. Выбирать следующий шаг.'
            : 'Тренируйтесь по плану. Сопоставляйте питание, результаты и самочувствие — чтобы выбрать следующий шаг.'}
        </p>
        <LandingV10Actions audience={audience} />
        <a
          {...glassProps('clear', true)}
          data-glass-tone="on-image"
          className="landing-v10-hero-tertiary"
          href={coach ? '#coach-work' : '#training'}
        >
          {coach ? 'Как работает Coach OS' : 'Посмотреть пример тренировки'}{' '}
          <Icon name="chevron-down" size={16} />
        </a>
        <div className="landing-hero__platform">
          <p className="landing-hero__platform-note">
            <Icon name="web-app" size={16} /> Браузер и мини-приложение Telegram · один аккаунт
          </p>
        </div>
      </div>
      <div className="ref-hero-foot">
        <span>
          {coach
            ? 'От внимания к клиенту — к подтверждённому действию.'
            : 'Одна тренировка — часть вашей истории.'}
        </span>
        <a href="#product">
          Как связаны шаги <Icon name="arrow-right" size={20} />
        </a>
      </div>
    </section>
  );
}

export function LandingV10Cycle({ audience }: { audience: LandingAudience }) {
  const coach = audience === 'coach';
  const steps: [string, string][] = coach
    ? [
        ['Подключить', 'Клиент принимает приглашение.'],
        ['Назначить', 'Программа и проверка состояния.'],
        ['Посмотреть', 'Факты и значимые изменения.'],
        ['Решить', 'Обновление после подтверждения.'],
      ]
    : [
        ['План', 'Выберите или создайте программу.'],
        ['Действие', 'Выполните тренировку.'],
        ['Факты', 'Запишите результат и питание.'],
        ['Решение', 'Сверьтесь с динамикой недели.'],
      ];
  return (
    <LandingChapter id="product" className="ref-cycle">
      <div>
        <p className="landing-kicker">{coach ? 'РАБОЧИЙ ЦИКЛ ТРЕНЕРА' : 'ОДИН ПРОДУКТОВЫЙ ЦИКЛ'}</p>
        <h2>
          {coach ? (
            <>
              Сопровождение. <br />С продолжением.
            </>
          ) : (
            <>
              Продолжение <br />
              имеет значение.
            </>
          )}
        </h2>
      </div>
      <ol>
        {steps.map(([title, text], i) => (
          <li key={title}>
            <small>{i + 1}</small>
            <h3>{title}</h3>
            <p>{text}</p>
          </li>
        ))}
      </ol>
    </LandingChapter>
  );
}
