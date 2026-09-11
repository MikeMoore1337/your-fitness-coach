import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DemoPage from '../../../../src/pages/demo/DemoPage';
import type { DemoSessionSnapshot } from '../../../../src/features/demo/demoApi';
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

const TRAINER_NAME = 'Алексей Воронов — подготовленный демо-клиент';

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

function nutritionSnapshot(itemAdded = false): DemoSessionSnapshot {
  const calories = itemAdded ? 1588 : 1160;
  const protein = itemAdded ? 106 : 82;
  return {
    capability: 'demo',
    scenario: 'nutrition',
    fixture_version: 'demo-curated-v1',
    revision: itemAdded ? 2 : 1,
    expires_at: '2026-08-24T12:30:00Z',
    state: {
      kind: 'nutrition',
      screen: 'diary',
      date_label: 'Сегодня · подготовленный дневник',
      item_added: itemAdded,
      recent_item: {
        name: 'Овсяная каша с бананом и греческим йогуртом',
        serving: '320 г · недавний продукт',
        calories: 428,
        protein_g: 24,
      },
      calories,
      calorie_target: 2150,
      protein_g: protein,
      protein_target_g: 145,
      meals_logged: itemAdded ? 3 : 2,
    },
    cabinet: {
      today: {
        title: 'Дневник питания на сегодня',
        summary: 'Добавьте подготовленный недавний продукт.',
        status_label: itemAdded ? 'Дневной итог обновлён' : 'Дневник не завершён',
        completed_days: itemAdded ? 5 : 4,
        planned_days: 7,
      },
      nutrition: {
        calories,
        calorie_target: 2150,
        protein_g: protein,
        protein_target_g: 145,
        meals_logged: itemAdded ? 3 : 2,
        item_added: itemAdded,
        recent_item: {
          name: 'Овсяная каша с бананом и греческим йогуртом',
          serving: '320 г · недавний продукт',
          calories: 428,
          protein_g: 24,
        },
      },
      progress: {
        workouts_completed: 10,
        latest_volume_kg: 6480,
        volume_change_percent: 3.8,
        nutrition_days_logged: itemAdded ? 6 : 5,
        nutrition_completion_percent: itemAdded ? 74 : 54,
        summary: itemAdded
          ? 'Новая запись уже отражена в дневном итоге.'
          : 'Итог использует только подтверждённые записи.',
      },
      trainer: null,
      meaningful_action_completed: itemAdded,
      conversion_title: 'Настройте дневник питания под себя',
    },
  };
}

function trainerSnapshot(): DemoSessionSnapshot {
  const trainer = nutritionSnapshot();
  trainer.scenario = 'trainer';
  trainer.state = {
    kind: 'trainer',
    screen: 'client',
    client_name: TRAINER_NAME,
    context_label: 'Последняя тренировка',
    workout_title: 'Ноги и корпус',
    facts: [{ label: 'Выполнено', value: '6 из 6 упражнений' }],
    comment: null,
  };
  trainer.cabinet.trainer = trainer.state;
  return trainer;
}

function renderPage(path: string) {
  window.history.replaceState({}, '', path);
  return render(
    <NavigationProvider>
      <DemoPage />
    </NavigationProvider>,
  );
}

describe('DemoCabinet preview', () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    mocks.load.mockResolvedValue(nutritionSnapshot());
    mocks.reset.mockResolvedValue(nutritionSnapshot());
    mocks.start.mockResolvedValue(nutritionSnapshot());
  });

  it('uses production AppShell navigation and keeps browser route on the allowlist', async () => {
    const user = userEvent.setup();
    renderPage('/demo?cabinet=1&scenario=nutrition&section=today');

    expect(
      await screen.findByRole('heading', { name: 'Дневник питания на сегодня' }),
    ).toBeVisible();
    const navigation = screen.getByRole('navigation', { name: 'Основная навигация' });
    expect(within(navigation).getByRole('button', { name: 'Сценарии' })).toHaveClass(
      'app-bottom-nav__more',
    );
    const scenarioSelector = screen.getByRole('combobox', { name: 'Демо-сценарий' });
    expect(scenarioSelector).toHaveValue('nutrition');
    expect(within(scenarioSelector).getByRole('option', { name: 'Питание' })).toBeVisible();
    expect(within(navigation).getByRole('link', { name: /Сегодня/ })).toHaveAttribute(
      'aria-current',
      'page',
    );

    await user.click(within(navigation).getByRole('link', { name: /Прогресс/ }));
    expect(
      await screen.findByRole('heading', { name: 'Подтверждённые действия становятся историей' }),
    ).toBeVisible();
    expect(window.location.search).toBe('?cabinet=1&scenario=nutrition&section=progress');
  });

  it('exposes the redesigned Plan and Profile preview states through direct routes', async () => {
    const user = userEvent.setup();
    renderPage('/demo?cabinet=1&scenario=self_training&section=plan');

    expect(
      await screen.findByRole('heading', {
        name: 'Один активный план, понятная следующая тренировка',
      }),
    ).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Сценарии' }));
    const demoMenu = screen.getByRole('dialog', { name: 'Выберите демо-сценарий' });
    expect(within(demoMenu).getByRole('link', { name: 'Профиль и настройки' })).toHaveAttribute(
      'href',
      '/demo?cabinet=1&scenario=self_training&section=profile',
    );

    await user.click(within(demoMenu).getByRole('link', { name: 'Профиль и настройки' }));
    expect(
      await screen.findByRole('heading', { name: 'Настройки по одной понятной группе' }),
    ).toBeVisible();
    expect(window.location.search).toBe('?cabinet=1&scenario=self_training&section=profile');
  });

  it('shows one contextual conversion after the meaningful action and clears demo credentials', async () => {
    mocks.apply.mockResolvedValue(nutritionSnapshot(true));
    const user = userEvent.setup();
    renderPage('/demo?cabinet=1&scenario=nutrition&section=nutrition');

    await user.click(await screen.findByRole('button', { name: 'Добавить недавний продукт' }));

    expect(mocks.apply).toHaveBeenCalledWith('nutrition', 'add_recent', undefined);
    expect(
      await screen.findByRole('heading', { name: 'Настройте дневник питания под себя' }),
    ).toBeVisible();
    expect(
      screen.getByText('Подготовленный пример останется в демо.', { exact: false }),
    ).toBeVisible();
    const login = screen.getByRole('link', { name: 'Войти в приложение' });
    expect(login).toHaveAttribute(
      'href',
      '/login?next=%2Fapp&from=demo&scenario=nutrition&cabinet=1&section=nutrition',
    );
    await user.click(login);
    expect(mocks.clearAll).toHaveBeenCalledOnce();
  });

  it('normalizes a damaged trainer route to the allowed start context', async () => {
    const trainer = trainerSnapshot();
    mocks.load.mockResolvedValue(trainer);

    renderPage('/demo?cabinet=1&scenario=trainer&section=admin');

    await waitFor(() =>
      expect(window.location.search).toBe('?cabinet=1&scenario=trainer&section=trainer'),
    );
    expect(await screen.findByRole('heading', { name: TRAINER_NAME })).toBeVisible();
  });

  it('ignores a late mutation response after switching to another preset', async () => {
    let resolveAction!: (snapshot: DemoSessionSnapshot) => void;
    mocks.apply.mockReturnValue(
      new Promise<DemoSessionSnapshot>((resolve) => {
        resolveAction = resolve;
      }),
    );
    const trainer = trainerSnapshot();
    mocks.load.mockImplementation((scenario: string) =>
      Promise.resolve(scenario === 'trainer' ? trainer : nutritionSnapshot()),
    );
    const user = userEvent.setup();
    renderPage('/demo?cabinet=1&scenario=nutrition&section=nutrition');

    await user.click(await screen.findByRole('button', { name: 'Добавить недавний продукт' }));
    await user.click(screen.getByRole('button', { name: 'Сценарии' }));
    await user.click(
      within(screen.getByRole('dialog', { name: 'Выберите демо-сценарий' })).getByRole('link', {
        name: 'Тренер: разбор результата клиента',
      }),
    );

    expect(await screen.findByRole('heading', { name: TRAINER_NAME })).toBeVisible();
    await act(async () => resolveAction(nutritionSnapshot(true)));
    expect(screen.getByRole('heading', { name: TRAINER_NAME })).toBeVisible();
    expect(window.location.search).toBe('?cabinet=1&scenario=trainer&section=trainer');
  });
});
