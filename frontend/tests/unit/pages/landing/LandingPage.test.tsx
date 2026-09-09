import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import LandingPage, {
  appUrlForHostname,
  demoUrlForHostname,
  loginUrlForHostname,
} from '../../../../src/pages/landing/LandingPage';
import {
  PRODUCT_EVENT_NAME,
  type ProductEventEnvelope,
} from '../../../../src/shared/analytics/productEvents';
import { NavigationProvider } from '../../../../src/shared/navigation/router';

function renderLanding() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <LandingPage />
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

describe('LandingPage', () => {
  afterEach(() => {
    cleanup();
    document.head
      .querySelectorAll(
        'meta[name="description"], meta[name="robots"], meta[name="yandex"], meta[name^="twitter:"], meta[property^="og:"], link[rel="canonical"], script[type="application/ld+json"]',
      )
      .forEach((element) => element.remove());
    localStorage.clear();
    window.history.replaceState({}, '', '/');
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('follows the system dark theme and lets the visitor switch it', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    );

    const { container } = renderLanding();

    expect(container.firstChild).toHaveClass('public-shell--dark');
    fireEvent.click(screen.getByRole('button', { name: 'Включить светлую тему' }));
    expect(container.firstChild).toHaveClass('public-shell--light');
    expect(localStorage.getItem('app-theme')).toBe('light');
  });

  it('publishes a factual product story for self-training and trainer audiences', () => {
    const { container } = renderLanding();

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Движение. Запись. Прогресс.',
    );
    expect(screen.getByText(/Тренировки и питание — в фактах/i)).toBeInTheDocument();
    expect(
      screen.getByRole('heading', {
        name: 'Начните сами. Тренера можно подключить позже.',
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('Один цикл — от плана до следующего шага.')).toBeInTheDocument();
    expect(
      screen.queryByRole('group', { name: 'Почему YFC помогает действовать' }),
    ).not.toBeInTheDocument();
    expect(screen.getByText('План → факт → динамика → следующий шаг')).toBeInTheDocument();
    expect(screen.getAllByText(/web.*telegram.*общие данные/i).length).toBeGreaterThan(0);
    expect(
      screen.getByRole('group', { name: 'Движение спортсмена и пример записи подхода' }),
    ).toHaveTextContent(/Пример записи/i);
    expect(screen.getByText('Пример записи')).toBeInTheDocument();
    expect(screen.queryByText('Демо · подготовленные данные')).not.toBeInTheDocument();

    expect(
      screen.getByRole('heading', { name: 'Сначала — одно понятное действие.' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Ориентир рядом с фактическими записями.' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Выводы только там, где хватает данных.' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'У каждого клиента — видимый контекст.' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/после входа пользователь может сразу включить режим тренера в профиле/i),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/не заменяет crm, платежи, расписание бизнеса/i).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/данные подготовленных демо-сценариев отделены/i).length,
    ).toBeGreaterThan(0);

    expect(screen.getByRole('heading', { name: /три сценария/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Откройте план на сегодня' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Фиксируйте факты' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /пройдите тренировку/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /добавьте питание/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /посмотрите кабинет тренера/i })).toBeInTheDocument();

    expect(
      screen.getByText(/telegram mini app не является отдельным приложением/i),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/экспорт, отвязка способов входа и удаление аккаунта/i).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText(/после одобрения заявки/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/тариф/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/искусственн.*интеллект|\bai\b/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/отзыв/i)).not.toBeInTheDocument();

    const telegramApps = screen.getAllByRole('link', { name: /Открыть.*в Telegram/ });
    expect(telegramApps).toHaveLength(3);
    for (const telegramApp of telegramApps) {
      expect(telegramApp).toHaveAttribute('href', 'https://t.me/your_fitness_coach_bot?startapp');
      expect(telegramApp).toHaveAttribute('target', '_blank');
      expect(telegramApp).toHaveAttribute('rel', 'noreferrer');
    }

    const news = screen.getByRole('link', {
      name: 'Telegram-канал о фитнесе и здоровье',
    });
    expect(news).toHaveAttribute('href', 'https://t.me/your_fitness_news');
    expect(news).toHaveAttribute('target', '_blank');
    expect(news).toHaveAttribute('rel', 'noreferrer');
    expect(screen.queryByRole('link', { name: 'Приложение в Telegram' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Поддержка' })).not.toBeInTheDocument();

    const support = screen.getByRole('link', { name: 'Поддержка в Telegram' });
    expect(support).toHaveAttribute('href', 'https://t.me/your_fitness_coach_bot?start=support');
    expect(support).toHaveAttribute('target', '_blank');
    expect(support).toHaveAttribute('rel', 'noreferrer');
    expect(container.querySelectorAll('img[src*="/assets/brand/yfc-mark-"]')).toHaveLength(3);
    expect(container.querySelectorAll('img[src*="/assets/brand/yfc-logo-"]')).toHaveLength(0);

    expect(container.querySelector('.energy-flow')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Жим гантелей лёжа' })).toBeInTheDocument();
  });

  it('uses responsive athlete derivatives, eager hero proof and lazy below-fold images', () => {
    renderLanding();

    const athlete = screen.getByAltText('Атлет выполняет жим гантелей лёжа');
    expect(athlete).toHaveAttribute('src', '/assets/marketing/strength-protocol-960.webp');
    expect(athlete).toHaveAttribute('width', '1536');
    expect(athlete).toHaveAttribute('height', '1024');
    expect(athlete).toHaveAttribute('fetchpriority', 'high');
    expect(athlete).toHaveAttribute('srcset', expect.stringContaining('640.webp 640w'));
    fireEvent.error(athlete);
    expect(
      screen.getByText('Изображение недоступно. Тренировки и демо остаются доступны.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^Начать$/ })).toHaveAttribute('href', '/app');

    const desktopProof = screen.getByAltText(/экран сегодня.*desktop web/i);
    expect(desktopProof).toHaveAttribute('src', '/assets/product/landing-today-desktop-light.webp');
    expect(desktopProof).toHaveAttribute('width', '1440');
    expect(desktopProof).toHaveAttribute('height', '900');
    expect(desktopProof).toHaveAttribute('loading', 'lazy');

    const mobileProof = screen.getByAltText('Актуальный экран Сегодня в Mobile Web');
    expect(mobileProof).toHaveAttribute('src', '/assets/product/landing-today-mobile-light.webp');
    expect(mobileProof).toHaveAttribute('width', '390');
    expect(mobileProof).toHaveAttribute('height', '844');
    expect(mobileProof).toHaveAttribute('loading', 'lazy');

    const trainerProof = screen.getByAltText(/актуальный кабинет тренера/i);
    expect(trainerProof).toHaveAttribute('loading', 'lazy');
    fireEvent.error(trainerProof);
    expect(screen.queryByAltText(/актуальный кабинет тренера/i)).not.toBeInTheDocument();
    expect(screen.getByText('Экран кабинета тренера временно недоступен.')).toBeInTheDocument();
  });

  it('links conversion actions to canonical app, demo and crawlable public routes', () => {
    renderLanding();

    expect(screen.getByRole('link', { name: 'Войти' })).toHaveAttribute('href', '/login');
    expect(screen.getAllByRole('link', { name: 'Открыть приложение' })[0]).toHaveAttribute(
      'href',
      '/app',
    );
    expect(screen.getAllByRole('link', { name: 'Попробовать демо' })[0]).toHaveAttribute(
      'href',
      '/demo?cabinet=1&scenario=self_training&section=today',
    );
    expect(screen.getAllByRole('link', { name: 'Попробовать демо' })[1]).toHaveAttribute(
      'href',
      '/demo?cabinet=1&scenario=self_training&section=today',
    );
    expect(screen.getByRole('link', { name: /добавьте питание/i })).toHaveAttribute(
      'href',
      '/demo?cabinet=1&scenario=nutrition&section=nutrition',
    );
    expect(screen.getByRole('link', { name: /посмотрите кабинет тренера/i })).toHaveAttribute(
      'href',
      '/demo?cabinet=1&scenario=trainer&section=trainer',
    );
    expect(screen.getByRole('link', { name: 'Как устроены тренировки' })).toHaveAttribute(
      'href',
      '/training',
    );
    expect(screen.getByRole('link', { name: 'Подробнее о питании' })).toHaveAttribute(
      'href',
      '/nutrition',
    );
    expect(screen.getByRole('link', { name: 'Как читать прогресс' })).toHaveAttribute(
      'href',
      '/progress',
    );
    expect(screen.getByRole('link', { name: /^Посмотреть кабинет тренера$/ })).toHaveAttribute(
      'href',
      '/for-trainers',
    );
    expect(appUrlForHostname('your-fitness-coach.ru')).toBe(
      'https://app.your-fitness-coach.ru/app',
    );
    expect(loginUrlForHostname('your-fitness-coach.ru')).toBe(
      'https://app.your-fitness-coach.ru/login',
    );
    expect(demoUrlForHostname('your-fitness-coach.ru')).toBe(
      'https://app.your-fitness-coach.ru/demo',
    );
    expect(screen.getByRole('link', { name: 'Приватность и данные' })).toHaveAttribute(
      'href',
      '#privacy',
    );
    expect(document.querySelector('#privacy')).toBeInTheDocument();
    expect(screen.getByText('Ваши данные остаются под вашим управлением.')).toBeInTheDocument();
  });

  it('tracks Telegram Mini App selections with their landing placement', () => {
    const events: ProductEventEnvelope[] = [];
    const listener = (event: Event) => {
      events.push((event as CustomEvent<ProductEventEnvelope>).detail);
    };
    window.addEventListener(PRODUCT_EVENT_NAME, listener);
    const { container } = renderLanding();

    fireEvent.click(container.querySelector<HTMLAnchorElement>('.landing-hero__telegram-link')!);
    fireEvent.click(container.querySelector<HTMLAnchorElement>('.landing-continuity__action')!);
    fireEvent.click(container.querySelector<HTMLAnchorElement>('.landing-footer__telegram-app')!);

    expect(
      events
        .filter((event) => event.name === 'landing_telegram_selected')
        .map((event) => ('placement' in event ? event.placement : undefined)),
    ).toEqual(['hero', 'continuity', 'footer']);

    window.removeEventListener(PRODUCT_EVENT_NAME, listener);
  });

  it('closes mobile navigation by selection and Escape with focus restoration', () => {
    const { container } = renderLanding();
    const menuButton = container.querySelector<HTMLButtonElement>('.landing-menu-toggle')!;

    expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(menuButton);
    expect(menuButton).toHaveAttribute('aria-label', 'Закрыть меню');
    fireEvent.click(screen.getByRole('link', { name: 'Продукт' }));
    expect(menuButton).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(menuButton);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(menuButton).toHaveAttribute('aria-label', 'Открыть меню');
    expect(menuButton).toHaveFocus();
  });

  it('publishes useful metadata and a keyboard skip link', async () => {
    const description = document.createElement('meta');
    description.name = 'description';
    document.head.append(description);
    const ogTitle = document.createElement('meta');
    ogTitle.setAttribute('property', 'og:title');
    document.head.append(ogTitle);
    const ogDescription = document.createElement('meta');
    ogDescription.setAttribute('property', 'og:description');
    document.head.append(ogDescription);
    const ogType = document.createElement('meta');
    ogType.setAttribute('property', 'og:type');
    document.head.append(ogType);

    const { unmount } = renderLanding();

    await waitFor(() =>
      expect(document.title).toMatch(/тренировки, питание и прогресс в браузере и telegram/i),
    );
    expect(description.content).toMatch(/фиксировать результаты.*ориентиры кбжу/i);
    expect(ogTitle.content).toMatch(/в браузере и telegram/i);
    expect(ogDescription.content).toMatch(/компьютере или смартфоне.*telegram mini app/i);
    expect(ogType.content).toBe('website');
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
      'content',
      'index, follow',
    );
    expect(document.querySelector('link[rel="canonical"]')).toHaveAttribute(
      'href',
      `${window.location.origin}/`,
    );
    expect(screen.getByRole('link', { name: 'К содержимому' })).toHaveAttribute(
      'href',
      '#landing-content',
    );
    expect(document.querySelector('#landing-content')).toHaveAttribute('tabindex', '-1');

    unmount();
  });
});
