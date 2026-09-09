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

  it('renders the approved photography and scroll story without manual tabs', () => {
    const { container } = renderLanding();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('СИЛА В ДЕЙСТВИИ.');
    expect(screen.getByRole('heading', { name: /Каждый подход/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Вошёл в ритм/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Питание без догадок.' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Замечай своё движение.' })).toBeInTheDocument();
    expect(container.querySelector('.strength-scene button')).toBeNull();
    expect(screen.getByText(/Иллюстрация движения/)).toBeInTheDocument();
    expect(screen.getByText(/Данные подготовленных демо-сценариев отделены/)).toBeInTheDocument();
  });

  it('loads hero eagerly and the paired below-fold photographs lazily', () => {
    renderLanding();
    expect(screen.getByAltText('Спортсменка толкает тренировочные сани')).toHaveAttribute(
      'fetchpriority',
      'high',
    );
    expect(screen.getByAltText('Начало тяги гантели')).toHaveAttribute('loading', 'lazy');
    expect(screen.getByAltText('Гантель у пояса в конце тяги')).toHaveAttribute('loading', 'lazy');
    expect(screen.getByAltText('Тренер и спортсменка обсуждают план')).toHaveAttribute(
      'loading',
      'lazy',
    );
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
    expect(screen.getByRole('link', { name: 'Тренировки' })).toHaveAttribute('href', '/training');
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
