import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import PublicContentPage from '../../../../src/pages/public/PublicContentPage';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { applyRouteMetadata } from '../../../../src/shared/seo/metadata';
import {
  PRODUCT_EVENT_NAME,
  type ProductEventEnvelope,
} from '../../../../src/shared/analytics/productEvents';

vi.mock('../../../../src/shared/api/client', () => ({
  api: vi.fn((path: string) => {
    if (path === '/api/v1/public/exercises') {
      return Promise.resolve([
        {
          slug: 'bench-press',
          title: 'Жим лежа',
          primary_muscle: 'Грудь',
          secondary_muscles: [],
          equipment: 'Штанга',
          difficulty_level: 'intermediate',
        },
        {
          slug: 'lat-pulldown',
          title: 'Вертикальная тяга',
          primary_muscle: 'Спина',
          secondary_muscles: [],
          equipment: 'Тренажер',
          difficulty_level: 'beginner',
        },
        {
          slug: 'squat',
          title: 'Приседания',
          primary_muscle: 'Квадрицепс',
          secondary_muscles: [],
          equipment: 'Штанга',
          difficulty_level: 'intermediate',
        },
      ]);
    }
    throw new Error(`Unexpected API path: ${path}`);
  }),
}));

function renderPath(path: string) {
  window.history.replaceState({}, '', path);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <PublicContentPage />
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

describe('PublicContentPage', () => {
  afterEach(() => {
    cleanup();
    document.head
      .querySelectorAll(
        'meta[name="description"], meta[name="robots"], meta[name="yandex"], meta[name^="twitter:"], meta[property^="og:"], link[rel="canonical"], script[type="application/ld+json"]',
      )
      .forEach((element) => element.remove());
    document.body.className = '';
    localStorage.clear();
    window.history.replaceState({}, '', '/');
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each([
    ['/training', /план тренировки, который остаётся перед глазами/i],
    ['/nutrition', /рассчитать кбжу: калории, белки, жиры и углеводы/i],
    ['/progress', /прогресс, который можно проверить/i],
    ['/for-trainers', /кабинет тренера для программ/i],
    ['/knowledge', /материалы, которые помогают понять/i],
  ])('renders a distinct indexable intent for %s', (path, heading) => {
    renderPath(path);

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
      'content',
      'index, follow',
    );
    expect(document.querySelector('link[rel="canonical"]')).toHaveAttribute(
      'href',
      `${window.location.origin}${path}`,
    );
    expect(screen.getByRole('navigation', { name: 'Публичные разделы' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Хлебные крошки' })).toBeInTheDocument();
  });

  it('publishes truthful article metadata and visible editorial context for a guide', () => {
    const serverStructuredData = document.createElement('script');
    serverStructuredData.type = 'application/ld+json';
    serverStructuredData.textContent = '{"@type":"WebSite"}';
    document.head.append(serverStructuredData);
    renderPath('/knowledge/training/how-to-start-strength-training');

    expect(screen.getByText('Редакция Your Fitness Coach')).toBeInTheDocument();
    expect(screen.getAllByText(/22 августа 2026/i)).toHaveLength(2);
    expect(screen.getByText(/общий образовательный характер/i)).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Оглавление' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Источники' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /WHO Guidelines/i })).toHaveAttribute(
      'href',
      'https://www.who.int/publications/i/item/9789240015128',
    );

    const structuredData = document.querySelector<HTMLScriptElement>(
      'script[type="application/ld+json"][data-public-seo]',
    );
    expect(document.querySelectorAll('script[type="application/ld+json"]')).toHaveLength(1);
    expect(structuredData).not.toBeNull();
    const payload = JSON.parse(structuredData?.textContent ?? '{}') as {
      '@graph': Array<{ '@type': string }>;
    };
    expect(payload['@graph'].map((item) => item['@type'])).toEqual(['Article', 'BreadcrumbList']);
    expect(document.querySelector('meta[property="og:type"]')).toHaveAttribute(
      'content',
      'article',
    );
    expect(document.querySelector('meta[property="og:image"]')).toHaveAttribute(
      'content',
      `${window.location.origin}/assets/brand/yfc-social-preview.png`,
    );
    expect(document.querySelector('meta[property="og:image:width"]')).toHaveAttribute(
      'content',
      '1200',
    );
    expect(document.querySelector('meta[property="og:image:height"]')).toHaveAttribute(
      'content',
      '630',
    );
    expect(document.querySelector('meta[property="og:image:alt"]')).toHaveAttribute(
      'content',
      expect.stringMatching(/тренировки, питание и прогресс/i),
    );
    expect(document.querySelector('meta[name="twitter:card"]')).toHaveAttribute(
      'content',
      'summary_large_image',
    );

    applyRouteMetadata('/app');
    expect(document.querySelector('script[type="application/ld+json"]')).toBeNull();
    expect(document.querySelector('link[rel="canonical"]')).toBeNull();
    expect(document.querySelector('meta[property^="og:"]')).toBeNull();
    expect(document.querySelector('meta[name^="twitter:"]')).toBeNull();
  });

  it('keeps all knowledge categories in one maintainable directory without empty routes', () => {
    renderPath('/knowledge');

    expect(
      screen.getByRole('heading', { name: /небольшая база без пустых страниц/i }),
    ).toBeVisible();
    expect(document.querySelectorAll('.public-guide-card')).toHaveLength(14);
    expect(screen.getByText(/Опубликовано: 4/i)).toBeVisible();
    expect(screen.getAllByText(/Опубликовано: 1/i)).toHaveLength(2);
    expect(screen.getByText(/Опубликовано: 2/i)).toBeVisible();
    expect(screen.getByText(/Опубликовано: 3/i)).toBeVisible();
    expect(screen.getByText(/Опубликовано: 6/i)).toBeVisible();
    expect(
      screen.getByRole('link', { name: /full body и split: выберите схему/i }),
    ).toHaveAttribute('href', '/knowledge/training/how-to-start-strength-training');
    expect(screen.getByRole('link', { name: /гликемический индекс/i })).toHaveAttribute(
      'href',
      '/knowledge/nutrition/glycemic-index',
    );
    expect(screen.getByRole('link', { name: /^Опубликованные упражнения/ })).toHaveAttribute(
      'href',
      '/exercises',
    );
  });

  it('renders the stateless BMI calculator with validation and a rounded result', () => {
    renderPath('/knowledge/progress/bmi-calculator');

    expect(
      screen.getByRole('heading', { level: 1, name: /имт — скрининговый ориентир/i }),
    ).toBeInTheDocument();
    const form = screen.getByRole('form', { name: 'Рассчитать ИМТ' });
    fireEvent.click(within(form).getByRole('button', { name: 'Рассчитать ИМТ' }));
    expect(screen.getByRole('alert')).toHaveTextContent(/массу тела от 1 до 500 кг/i);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Масса тела, кг'), { target: { value: '80' } });
    fireEvent.change(screen.getByLabelText('Рост, см'), { target: { value: '180' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Рассчитать ИМТ' }));

    expect(screen.getByRole('status')).toHaveTextContent('ИМТ: 24,7');
    expect(screen.getByRole('status')).toHaveTextContent('Нормальный диапазон для взрослых');

    fireEvent.change(screen.getByLabelText('Масса тела, кг'), { target: { value: '80.99' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Рассчитать ИМТ' }));
    expect(screen.getByRole('status')).toHaveTextContent('ИМТ: 25,0');
    expect(screen.getByRole('status')).toHaveTextContent('Нормальный диапазон для взрослых');
    expect(localStorage.getItem('public-bmi-calculator')).toBeNull();
  });

  it('renders a stateless public KBJU calculator with privacy-safe growth events', async () => {
    const events: ProductEventEnvelope[] = [];
    const listener = (event: Event) =>
      events.push((event as CustomEvent<ProductEventEnvelope>).detail);
    window.addEventListener(PRODUCT_EVENT_NAME, listener);

    try {
      renderPath('/nutrition');

      const calculator = document.querySelector<HTMLElement>('#public-kbju-calculator');
      expect(calculator).toHaveClass('ym-hide-content');
      expect(screen.getByText('Уточнить расчёт тренировочной нагрузки')).toBeInTheDocument();
      const form = screen.getByRole('form', { name: 'Рассчитать КБЖУ онлайн' });

      fireEvent.click(within(form).getByRole('button', { name: 'Рассчитать КБЖУ' }));
      expect(screen.getByRole('alert')).toHaveTextContent(/проверьте данные/i);
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
      expect(screen.getByLabelText('Возраст, лет')).toHaveAttribute('aria-invalid', 'true');

      fireEvent.change(screen.getByLabelText('Возраст, лет'), { target: { value: '34' } });
      fireEvent.change(screen.getByLabelText('Вес, кг'), { target: { value: '78' } });
      fireEvent.change(screen.getByLabelText('Рост, см'), { target: { value: '165' } });
      fireEvent.change(screen.getByLabelText('Силовых тренировок в неделю'), {
        target: { value: '4' },
      });
      fireEvent.click(screen.getByText('Уточнить расчёт тренировочной нагрузки'));
      fireEvent.change(screen.getByLabelText('Длительность силовой, минут'), {
        target: { value: '60' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Добавить кардио' }));
      expect(screen.getByText('Кардио 1')).toBeInTheDocument();
      fireEvent.click(within(form).getByRole('button', { name: 'Рассчитать КБЖУ' }));

      await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Калории'));
      expect(screen.getByRole('status')).toHaveTextContent('Белки');
      expect(screen.getByRole('status')).toHaveTextContent('Для поддержания');
      expect(window.location.search).toBe('');
      expect(localStorage.length).toBe(0);
      expect(events.map((event) => event.name)).toEqual([
        'calculator_started',
        'calculator_result',
      ]);
      expect(events.every((event) => Object.keys(event).length === 5)).toBe(true);

      fireEvent.click(within(form).getByRole('button', { name: 'Рассчитать КБЖУ' }));
      expect(events.map((event) => event.name)).toEqual([
        'calculator_started',
        'calculator_result',
      ]);
      expect(events.some((event) => event.name === 'calculator_saved')).toBe(false);
    } finally {
      window.removeEventListener(PRODUCT_EVENT_NAME, listener);
    }
  });

  it('renders only allowlisted public exercise cards from the domain API', async () => {
    renderPath('/exercises');

    expect(await screen.findByRole('heading', { name: 'Жим лежа' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Жим лежа' })).toHaveAttribute(
      'href',
      '/exercises/bench-press',
    );
    expect(document.querySelectorAll('.public-guide-card')).toHaveLength(3);
    expect(screen.queryByText(/пользовательское упражнение/i)).not.toBeInTheDocument();
  });

  it('uses the same persisted light and dark theme contract as the landing page', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    );

    const { container } = renderPath('/knowledge');

    expect(container.firstChild).toHaveClass('public-shell--dark');
    expect(document.body).toHaveClass('public-shell-mode', 'public-shell-dark-mode');
    fireEvent.click(screen.getByRole('button', { name: 'Включить светлую тему' }));
    expect(container.firstChild).toHaveClass('public-shell--light');
    expect(document.body).not.toHaveClass('public-shell-dark-mode');
    expect(localStorage.getItem('app-theme')).toBe('light');
  });

  it('supports keyboard skip navigation and an accessible mobile menu', () => {
    renderPath('/progress');

    const skipLink = screen.getByRole('link', { name: 'К содержимому' });
    skipLink.focus();
    fireEvent.click(skipLink);
    expect(document.querySelector('#public-content')).toHaveFocus();

    const menu = document.querySelector<HTMLButtonElement>('.landing-menu-toggle');
    expect(menu).not.toBeNull();
    expect(menu).toHaveAttribute('aria-label', 'Открыть меню');
    if (!menu) throw new Error('Mobile menu control is missing');
    fireEvent.click(menu);
    expect(menu).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(
      within(screen.getByRole('navigation', { name: 'Публичные разделы' })).getByRole('link', {
        name: 'Питание',
      }),
    );
    expect(
      screen.getByRole('heading', { level: 1, name: /рассчитать кбжу: калории/i }),
    ).toBeInTheDocument();
  });
});
