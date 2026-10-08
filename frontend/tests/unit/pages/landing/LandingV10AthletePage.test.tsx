import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import LandingV10AthletePage from '../../../../src/pages/landing/LandingV10AthletePage';
import { NavigationProvider } from '../../../../src/shared/navigation/router';

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <LandingV10AthletePage />
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

describe('LandingV10AthletePage', () => {
  afterEach(() => {
    cleanup();
    window.history.replaceState({}, '', '/');
    localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('keeps the approved athlete story and exposes only the compact Coach OS teaser', () => {
    const { container } = renderPage();

    expect(screen.getByRole('heading', { level: 1, name: 'СИЛА В ДЕЙСТВИИ.' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /От первого действия/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Каждый подход/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Ориентир рядом с фактами/ })).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /Смотрите на движение недели/ }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole('heading', { name: 'Вы тренер? Знакомьтесь с Coach OS.' }),
    ).toHaveLength(1);
    expect(container.querySelectorAll('.landing-v10-coach-promo')).toHaveLength(1);
    expect(screen.queryByText(/Coach Today|Не потерять важное/)).not.toBeInTheDocument();
  });

  it('switches the synthetic nutrition preview without implying consumed equals planned', () => {
    renderPage();

    expect(screen.getByRole('tab', { name: 'План' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('tab', { name: 'Покупки' }));
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Список из плана');
    fireEvent.click(screen.getByRole('tab', { name: 'Дневник' }));
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Нет записи — это пропуск данных');
  });

  it('keeps the weekly review local and sends the trainer CTA to the trainer landing', () => {
    renderPage();

    fireEvent.click(screen.getByRole('button', { name: '5' }));
    expect(screen.getByRole('button', { name: '5' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/Отмечено: 5 из 5/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Возможности для тренера' })).toHaveAttribute(
      'href',
      '/for-trainers',
    );
  });

  it('does not call a product API while rendering the staged composition', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    renderPage();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
