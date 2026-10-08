import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import LandingV10CoachPage from '../../../../src/pages/landing/LandingV10CoachPage';
import { NavigationProvider } from '../../../../src/shared/navigation/router';

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <LandingV10CoachPage />
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

describe('LandingV10CoachPage', () => {
  afterEach(() => {
    cleanup();
    window.history.replaceState({}, '', '/for-trainers');
    localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('keeps six coach-native chapters without athlete storytelling', () => {
    const { container } = renderPage();

    expect(
      screen.getByRole('heading', { level: 1, name: 'ВАШ МЕТОД В ДЕЙСТВИИ.' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Не потерять важное/ })).toBeInTheDocument();
    expect(
      Array.from(container.querySelectorAll<HTMLElement>('[data-coach-chapter]')).map(
        (chapter) => chapter.dataset.coachChapter,
      ),
    ).toEqual(['coach-today', 'connect', 'program', 'facts', 'review', 'decision']);
    expect(container.querySelector('[data-coach-chapter="coach-today"]')).toBeInTheDocument();
    expect(container.querySelectorAll('[data-testid="coach-today-preview"]')).toHaveLength(1);
    expect(container.querySelector('.strength-scene')).not.toBeInTheDocument();
    expect(container.querySelector('.landing-practice')).not.toBeInTheDocument();
    expect(container.querySelector('.landing-v10-nutrition')).not.toBeInTheDocument();
    expect(container.querySelector('.landing-v10-progress')).not.toBeInTheDocument();
    expect(screen.queryByText('СИЛА В ДЕЙСТВИИ.')).not.toBeInTheDocument();
  });

  it('keeps Coach Today and local product previews interactive', () => {
    renderPage();

    fireEvent.click(screen.getByRole('tab', { name: 'Версия 1' }));
    expect(screen.getByText('3 подхода в текущем блоке')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Сообщение' }));
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Черновик готов к проверке');

    fireEvent.click(screen.getByRole('button', { name: 'Показать изменение' }));
    const rollout = screen.getByTestId('rollout-preview');
    expect(within(rollout).getByRole('status')).toHaveTextContent('2 клиента · 2 подхода вместо 3');
    fireEvent.click(within(rollout).getByRole('button', { name: 'Подтвердить в примере' }));
    expect(
      within(rollout).getByRole('button', { name: 'Подтверждено в примере' }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '4' }));
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    expect(screen.getByText(/Выбрано: Изменить/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить черновик' }));
    expect(
      screen.getByRole('button', { name: 'Черновик подтверждён в примере' }),
    ).toBeInTheDocument();
  });

  it('keeps trainer CTA destinations on the bounded auth intent and demo contours', () => {
    renderPage();

    expect(screen.getAllByRole('link', { name: 'Начать как тренер' })[0]).toHaveAttribute(
      'href',
      '/login?next=%2Fapp%3Ftrainer_intent%3D1',
    );
    const trainerDemoLinks = screen.getAllByRole('link', {
      name: 'Попробовать демо для тренера',
    });
    expect(trainerDemoLinks).toHaveLength(2);
    for (const link of trainerDemoLinks) {
      expect(link).toHaveAttribute('href', '/demo?cabinet=1&scenario=trainer&section=trainer');
    }
    expect(screen.getByRole('link', { name: /Как работает Коуч ОС/ })).toHaveAttribute(
      'href',
      '#coach-work',
    );
  });

  it('does not call a product API while rendering the staged composition', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    renderPage();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
