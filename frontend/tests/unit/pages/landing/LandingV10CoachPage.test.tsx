import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import LandingV10CoachPage from '../../../../src/pages/landing/LandingV10CoachPage';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <NavigationProvider>
        <LandingV10CoachPage />
      </NavigationProvider>
    </QueryClientProvider>,
  );
}
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});
describe('canonical archive trainer composition', () => {
  it('keeps the trainer-specific path separate from athlete scenes', () => {
    const { container } = renderPage();
    expect(
      [...container.querySelectorAll('main > section[id]')]
        .map((e) => e.id)
        .filter(
          (id) => id.startsWith('coach-') || ['training', 'nutrition', 'progress'].includes(id),
        ),
    ).toEqual([
      'coach-work',
      'coach-process',
      'coach-connect',
      'coach-program',
      'coach-facts',
      'coach-review',
      'coach-decision',
      'coach-followup',
    ]);
    expect(container.querySelectorAll('.strength-scene')).toHaveLength(0);
    expect(container.querySelector('#training')).toBeNull();
    expect(container.querySelector('#nutrition')).toBeNull();
    expect(container.querySelector('#progress')).toBeNull();
    expect(container.querySelector('#faq')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Понятные правила.' })).toBeInTheDocument();
    expect(container.querySelector('#coach-promo')).toBeNull();
  });
  it('requires separate preview and confirmation; messages remain local', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть изменения' }));
    expect(screen.getByText('Подготовлено изменение')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Посмотреть перед применением' }));
    expect(screen.getByText('Просмотр перед применением')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить в примере' }));
    expect(screen.getByRole('button', { name: 'Подтверждено в примере' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Сообщение' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Текст черновика' }), {
      target: { value: 'Новый локальный черновик' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить черновик в примере' }));
    expect(screen.getByRole('textbox')).toHaveValue('Новый локальный черновик');
    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
  it('preserves bounded trainer onboarding and the existing DemoCabinet', () => {
    renderPage();
    for (const link of screen.getAllByRole('link', { name: 'Начать как тренер' }))
      expect(link).toHaveAttribute('href', '/login?next=%2Fapp%3Ftrainer_intent%3D1');
    for (const link of screen.getAllByRole('link', { name: 'Попробовать демо для тренера' }))
      expect(link).toHaveAttribute('href', '/demo?cabinet=1&scenario=trainer&section=trainer');
    expect(screen.getByRole('link', { name: 'Как работает Coach OS' })).toHaveAttribute(
      'href',
      '#coach-work',
    );
    expect(screen.getByRole('link', { name: 'Как работает Coach OS' })).toHaveAttribute(
      'data-glass',
    );
  });
});
