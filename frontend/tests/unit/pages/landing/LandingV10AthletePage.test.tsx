import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import LandingV10AthletePage from '../../../../src/pages/landing/LandingV10AthletePage';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <NavigationProvider>
        <LandingV10AthletePage />
      </NavigationProvider>
    </QueryClientProvider>,
  );
}
afterEach(() => {
  cleanup();
  window.history.replaceState({}, '', '/');
  localStorage.clear();
  vi.restoreAllMocks();
});
describe('canonical archive athlete composition', () => {
  it('returns legal-dialog focus to its actual trigger when clicks do not focus buttons', () => {
    renderPage();
    const dialog = document.querySelector('dialog')!;
    const show = vi.fn();
    Object.defineProperty(dialog, 'showModal', { value: show });
    for (const name of ['Условия использования', 'Политика конфиденциальности']) {
      const trigger = screen.getByRole('button', { name });
      fireEvent.click(trigger);
      expect(show).toHaveBeenCalled();
      fireEvent(dialog, new Event('close'));
      expect(trigger).toHaveFocus();
      trigger.blur();
    }
  });
  it('keeps the archive section order, Coach Today and real destinations', () => {
    const { container } = renderPage();
    const hero = within(container.querySelector('.ref-hero')! as HTMLElement);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('СИЛА В ДЕЙСТВИИ.');
    expect(
      [...container.querySelectorAll('main > section')].map((e) => e.classList[0]),
    ).toHaveLength(12);
    expect(container.querySelectorAll('.strength-scene')).toHaveLength(1);
    expect(container.querySelectorAll('#coach-work')).toHaveLength(0);
    expect(container.querySelectorAll('#coach-promo')).toHaveLength(1);
    expect(screen.getByRole('heading', { name: /Знакомьтесь с Coach OS/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Возможности для тренера' })).toHaveAttribute(
      'href',
      '/for-trainers',
    );
    expect(hero.getByRole('link', { name: 'Начать со своими данными' })).toHaveAttribute(
      'href',
      '/app',
    );
    expect(hero.getByRole('link', { name: 'Попробовать демо тренировки' })).toHaveAttribute(
      'href',
      '/demo?cabinet=1&scenario=self_training&section=today',
    );
    expect(hero.getByRole('link', { name: 'Посмотреть пример тренировки' })).toHaveAttribute(
      'href',
      '#training',
    );
    expect(hero.getByRole('link', { name: 'Посмотреть пример тренировки' })).toHaveAttribute(
      'data-glass',
    );
    expect(
      hero
        .getByRole('link', { name: 'Посмотреть пример тренировки' })
        .compareDocumentPosition(hero.getByText(/Браузер и мини-приложение Telegram/)),
    ).toBe(4);
    expect(screen.getByRole('heading', { name: 'Понятные границы.' })).toBeInTheDocument();
  }, 15000);
  it('does not turn planned food into a diary entry without an explicit action', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Покупки' }));
    expect(screen.getByText('60 г')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Дневник' }));
    expect(screen.getByText('Записи пока нет')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Отметить съеденное в примере' }));
    expect(screen.getByRole('button', { name: 'Запись сохранена в примере' })).toBeDisabled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
  it('runs and resets the local training example without creating a real demo session', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const { container } = renderPage();
    const training = within(container.querySelector('#training')! as HTMLElement);
    fireEvent.click(training.getByRole('button', { name: 'Начать тренировку' }));
    for (let i = 0; i < 3; i++)
      fireEvent.click(training.getByRole('button', { name: /Завершить текущий подход/ }));
    fireEvent.click(training.getByRole('button', { name: 'Завершить тренировку' }));
    expect(training.getByText('24 мин')).toBeInTheDocument();
    fireEvent.click(training.getByRole('button', { name: 'Перейти к прогрессу' }));
    expect(training.getByText('+4.2%')).toBeInTheDocument();
    fireEvent.click(training.getByRole('button', { name: 'Сбросить пример' }));
    expect(training.getByRole('button', { name: 'Начать тренировку' })).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
  it('keeps review input local and campaign/hash on audience links', () => {
    window.history.replaceState({}, '', '/?utm_campaign=v10#coach-work');
    const { container } = renderPage();
    fireEvent.click(screen.getByRole('radio', { name: '3', hidden: true }));
    expect(screen.getByText(/В примере выбран ответ 3 из 5/)).toBeInTheDocument();
    expect(container.querySelector('#coach-promo a')).toHaveAttribute(
      'href',
      '/for-trainers?utm_campaign=v10#coach-work',
    );
  });
});
