import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { demoFixture } from '../../../e2e/fixtures/demo-session';
import type { DemoScenario, DemoSessionSnapshot } from '../../../../src/features/demo/demoApi';
import DemoPage from '../../../../src/pages/demo/DemoPage';
import { NavigationProvider } from '../../../../src/shared/navigation/router';

const mocks = vi.hoisted(() => ({
  apply: vi.fn(),
  clearAll: vi.fn(),
  clear: vi.fn(),
  load: vi.fn(),
  reset: vi.fn(),
  start: vi.fn(),
  track: vi.fn(),
}));

vi.mock('../../../../src/features/demo/demoApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../../src/features/demo/demoApi')>();
  return {
    ...actual,
    applyDemoAction: mocks.apply,
    clearAllDemoSessions: mocks.clearAll,
    clearDemoSession: mocks.clear,
    loadDemoSession: mocks.load,
    resetDemoSession: mocks.reset,
    startDemoSession: mocks.start,
  };
});

vi.mock('../../../../src/shared/analytics/productEvents', () => ({
  productEventSurface: () => 'mobile_web',
  trackProductEvent: mocks.track,
}));

function renderPage(path: string) {
  window.history.replaceState({}, '', path);
  return render(
    <NavigationProvider>
      <DemoPage />
    </NavigationProvider>,
  );
}

function mutateSnapshot(
  snapshot: DemoSessionSnapshot,
  action: string,
  comment?: string,
  clientId?: 'alexey' | 'maria' | 'ivan',
): DemoSessionSnapshot {
  const next = structuredClone(snapshot);
  next.revision += 1;
  if (next.state.kind === 'self_training') {
    if (action === 'start_workout') next.state.screen = 'active_workout';
    if (action === 'complete_set') next.state.completed_sets = next.state.total_sets;
    if (action === 'finish_workout') {
      next.state.screen = 'summary';
      next.state.duration_minutes = 46;
      next.state.total_volume_kg = 6840;
      next.state.progress_change_percent = 6.5;
      next.cabinet.progress.latest_volume_kg = 6840;
      next.cabinet.progress.volume_change_percent = 6.5;
      next.cabinet.meaningful_action_completed = true;
    }
    if (action === 'open_progress') next.state.screen = 'progress';
  } else if (next.state.kind === 'nutrition') {
    if (action === 'add_recent') {
      next.state.item_added = true;
      next.state.calories += next.state.recent_item.calories;
      next.state.protein_g += next.state.recent_item.protein_g;
      next.state.meals_logged += 1;
      next.cabinet.nutrition.calories = next.state.calories;
      next.cabinet.nutrition.protein_g = next.state.protein_g;
      next.cabinet.nutrition.meals_logged = next.state.meals_logged;
      next.cabinet.nutrition.item_added = true;
      next.cabinet.progress.nutrition_completion_percent = 74;
      next.cabinet.meaningful_action_completed = true;
    }
    if (action === 'open_nutrition_report') next.state.screen = 'report';
  } else {
    const trainerState = next.state;
    if (action === 'select_client' && clientId) {
      trainerState.selected_client_id = clientId;
      next.cabinet.trainer!.selected_client_id = clientId;
    }
    if (action === 'save_comment') {
      const selected = trainerState.clients.find(
        (client) => client.id === trainerState.selected_client_id,
      );
      if (selected) selected.comment = comment ?? 'Техника стабильна.';
      next.cabinet.trainer!.clients = next.state.clients;
      next.cabinet.meaningful_action_completed = true;
    }
  }
  return next;
}

describe('Demo cabinet journey', () => {
  afterEach(() => {
    cleanup();
    window.sessionStorage.clear();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    let current: DemoSessionSnapshot | null = null;
    mocks.load.mockImplementation((scenario: DemoScenario) => {
      current = demoFixture(scenario);
      return Promise.resolve(current);
    });
    mocks.apply.mockImplementation(
      async (
        scenario: DemoScenario,
        action: string,
        comment?: string,
        clientId?: 'alexey' | 'maria' | 'ivan',
      ) => {
        current = mutateSnapshot(current ?? demoFixture(scenario), action, comment, clientId);
        return current;
      },
    );
    mocks.reset.mockImplementation(async (scenario: DemoScenario) => {
      current = demoFixture(scenario);
      return current;
    });
    mocks.start.mockImplementation(async (scenario: DemoScenario) => {
      current = demoFixture(scenario);
      return current;
    });
  });

  it('opens the cabinet from bare /demo with the exact scenario contract and clean utility rail', async () => {
    renderPage('/demo');

    expect(await screen.findByRole('heading', { name: 'План на сегодня' })).toBeVisible();
    expect(screen.getByText('Демо-режим · данные не сохраняются')).toBeVisible();
    expect(screen.queryByText('Отдельная сессия')).not.toBeInTheDocument();
    expect(screen.queryByText('Демо-кабинет')).not.toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /Аватар/ })).not.toBeInTheDocument();

    const selector = screen.getByRole('combobox', { name: 'Сценарий демо' });
    expect(within(selector).getAllByRole('option')).toHaveLength(3);
    expect(within(selector).getByRole('option', { name: 'Тренировка' })).toBeVisible();
    expect(within(selector).getByRole('option', { name: 'Питание и прогресс' })).toBeVisible();
    expect(within(selector).getByRole('option', { name: 'Работа тренера' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Скрыть маршрут' })).toBeVisible();
    expect(screen.getByText(/Маршрут демо · \d из 4/)).toBeVisible();
  });

  it('switches and resets all three scenarios without leaving demo navigation', async () => {
    const user = userEvent.setup();
    renderPage('/demo?scenario=self_training');

    const selector = await screen.findByRole('combobox', { name: 'Сценарий демо' });
    await user.selectOptions(selector, 'nutrition');
    await waitFor(() =>
      expect(window.location.search).toBe('?cabinet=1&scenario=nutrition&section=today'),
    );
    expect(await screen.findByRole('heading', { name: 'План на сегодня' })).toBeVisible();
    expect(screen.getByText('Питание и прогресс')).toBeVisible();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Сценарий демо' }), 'trainer');
    await waitFor(() =>
      expect(window.location.search).toBe('?cabinet=1&scenario=trainer&section=trainer'),
    );
    expect(await screen.findByRole('heading', { name: 'Разбор результата клиента' })).toBeVisible();
    expect(screen.getByRole('option', { name: /Мария/ })).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Начать заново' }));
    await waitFor(() => expect(mocks.reset).toHaveBeenCalledWith('trainer'));
    expect(screen.getByText(/Маршрут демо · \d из 4/)).toBeVisible();
  });

  it('does not mark causal route sections complete when browsing profile freely', async () => {
    const user = userEvent.setup();
    renderPage('/demo?scenario=self_training&section=profile');

    expect(
      await screen.findByRole('heading', { name: 'Настройки по одной понятной группе' }),
    ).toBeVisible();
    expect(screen.getByText('Маршрут демо · 1 из 4')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Продолжить' }));
    await waitFor(() => expect(window.location.search).toContain('section=plan'));
  });

  it('supports hide and reopen plus a causal training route to the conversion state', async () => {
    const user = userEvent.setup();
    renderPage('/demo?scenario=self_training');

    await screen.findByRole('heading', { name: 'План на сегодня' });
    await user.click(screen.getByRole('button', { name: 'Скрыть маршрут' }));
    expect(screen.queryByText(/Маршрут демо ·/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Показать маршрут' }));
    expect(screen.getByText(/Маршрут демо ·/)).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Продолжить' }));
    expect(
      await screen.findByRole('heading', { name: 'Активная программа и расписание на неделю' }),
    ).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Продолжить' }));
    expect(await screen.findByRole('heading', { name: 'План на сегодня' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Начать тренировку' }));
    await user.click(screen.getByRole('button', { name: 'Завершить текущий подход' }));
    await user.click(screen.getByRole('button', { name: 'Завершить тренировку' }));
    await user.click(screen.getByRole('button', { name: 'Перейти к прогрессу' }));
    await user.click(screen.getByRole('link', { name: 'Посмотреть прогресс' }));

    expect(
      await screen.findByRole('heading', { name: 'Готово. Вы посмотрели основной сценарий' }),
    ).toBeVisible();
    expect(
      screen.getByText('Теперь можно начать со своими тренировками, питанием и прогрессом.'),
    ).toBeVisible();
    const ownData = screen.getByRole('link', { name: 'Начать со своими данными' });
    expect(ownData).toHaveAttribute(
      'href',
      '/login?next=%2Fapp&from=demo&scenario=self_training&cabinet=1&section=progress',
    );
    await user.click(ownData);
    expect(mocks.clearAll).toHaveBeenCalledOnce();
    expect(mocks.track).toHaveBeenCalledWith(
      { name: 'demo_own_data_selected', surface: 'mobile_web', scenario: 'self_training' },
      { dedupe: 'session', dedupeKey: 'self_training' },
    );
  }, 15_000);

  it('shows nutrition updates, progress history and multiple trainer states with invite disabled', async () => {
    const user = userEvent.setup();
    renderPage('/demo?scenario=nutrition&section=nutrition');
    await user.click(await screen.findByRole('button', { name: 'Добавить недавний продукт' }));
    expect(await screen.findByText('1588 / 2150')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Открыть итог по питанию' }));
    await user.click(screen.getByRole('link', { name: 'Посмотреть показатели' }));
    expect(
      await screen.findByRole('heading', { name: 'Подтверждённые действия становятся историей' }),
    ).toBeVisible();
    expect(screen.getAllByText('Неделя 1').length).toBeGreaterThan(0);
    expect(screen.getAllByText('День заполнен частично').length).toBeGreaterThan(0);

    await user.selectOptions(screen.getByRole('combobox', { name: 'Сценарий демо' }), 'trainer');
    await waitFor(() => expect(window.location.search).toContain('scenario=trainer'));
    expect(await screen.findByText('Алексей · подготовленный клиент')).toBeVisible();
    const clientSelector = screen.getByRole('combobox', { name: 'Демонстрационный клиент' });
    await user.selectOptions(clientSelector, 'maria');
    expect(await screen.findByText('Мария · подготовленный клиент')).toBeVisible();
    expect(screen.getByText('Нужна регулярность')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Пригласить нового клиента' })).toBeDisabled();
  });
});
