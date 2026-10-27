import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { demoFixture } from '../../../e2e/fixtures/demo-session';
import type { DemoScenario } from '../../../../src/features/demo/demoApi';
import { getDemoRouteState } from '../../../../src/features/demo/demoRoute';
import DemoPage from '../../../../src/pages/demo/DemoPage';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { PwaProvider } from '../../../../src/shared/pwa/PwaProvider';

const mocks = vi.hoisted(() => ({
  apply: vi.fn(),
  clearAll: vi.fn(),
  clear: vi.fn(),
  getToken: vi.fn(() => 'demo-token-000000000000000000000000000000'),
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
    getDemoSessionToken: mocks.getToken,
    loadDemoSession: mocks.load,
    resetDemoSession: mocks.reset,
    startDemoSession: mocks.start,
  };
});

vi.mock('../../../../src/shared/analytics/productEvents', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../../src/shared/analytics/productEvents')>();
  return { ...actual, productEventSurface: () => 'mobile_web', trackProductEvent: mocks.track };
});

vi.mock('../../../../src/pages/demo/DemoAuthProvider', () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('../../../../src/pages/miniapp/MiniAppPage', () => ({
  default: ({ sectionOverride }: { sectionOverride?: string }) => (
    <section data-testid="production-mini-app">
      <h1>
        {sectionOverride === 'programs' ? 'Production plan' : `Production ${sectionOverride}`}
      </h1>
      <button type="button">Начать тренировку</button>
    </section>
  ),
}));

vi.mock('../../../../src/pages/coach/CoachPage', () => ({
  default: () => (
    <section data-testid="production-coach">
      <h1>Production coach</h1>
      <button type="button">Сохранить комментарий</button>
    </section>
  ),
}));

function renderPage(path: string) {
  window.history.replaceState({}, '', path);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <PwaProvider>
      <QueryClientProvider client={queryClient}>
        <NavigationProvider>
          <DemoPage />
        </NavigationProvider>
      </QueryClientProvider>
    </PwaProvider>,
  );
}

describe('Demo cabinet production composition', () => {
  afterEach(() => {
    cleanup();
    window.sessionStorage.clear();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getToken.mockReturnValue('demo-token-000000000000000000000000000000');
    mocks.load.mockImplementation((scenario: DemoScenario) =>
      Promise.resolve(demoFixture(scenario)),
    );
    mocks.reset.mockImplementation((scenario: DemoScenario) =>
      Promise.resolve(demoFixture(scenario)),
    );
    mocks.start.mockImplementation((scenario: DemoScenario) =>
      Promise.resolve(demoFixture(scenario)),
    );
  });

  it('renders the shared production page inside the demo boundary', async () => {
    renderPage('/demo');

    expect(await screen.findByRole('heading', { name: 'Production today' })).toBeVisible();
    expect(screen.getByText('Демо-режим · данные не сохраняются')).toBeVisible();
    expect(screen.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Начать тренировку' })).toBeVisible();
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('keeps scenario switching, reset and trainer routing inside the cabinet', async () => {
    const user = userEvent.setup();
    renderPage('/demo?scenario=self_training');

    const selector = await screen.findByRole('combobox', { name: 'Сценарий демо' });
    await user.selectOptions(selector, 'nutrition');
    await waitFor(() =>
      expect(window.location.search).toBe('?cabinet=1&scenario=nutrition&section=today'),
    );
    expect(await screen.findByRole('heading', { name: 'Production today' })).toBeVisible();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Сценарий демо' }), 'trainer');
    await waitFor(() =>
      expect(window.location.search).toBe('?cabinet=1&scenario=trainer&section=trainer'),
    );
    expect(await screen.findByRole('heading', { name: 'Production coach' })).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Начать заново' }));
    await waitFor(() => expect(mocks.reset).toHaveBeenCalledWith('trainer'));
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('uses navigation-only route steps and does not auto-start a workout', async () => {
    const user = userEvent.setup();
    renderPage('/demo?scenario=self_training&section=profile');

    expect(await screen.findByRole('heading', { name: 'Production profile' })).toBeVisible();
    expect(screen.getByText('Маршрут демо · 1 из 4')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Продолжить' }));
    await waitFor(() => expect(window.location.search).toContain('section=plan'));
    expect(await screen.findByRole('heading', { name: 'Production plan' })).toBeVisible();
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('completes the nutrition route from the real diary mutation and progress visit', () => {
    const snapshot = demoFixture('nutrition');
    if (snapshot.state.kind !== 'nutrition') throw new Error('Expected nutrition fixture');
    snapshot.state.item_added = true;

    const afterAdd = getDemoRouteState('nutrition', snapshot, 'nutrition', new Set(['nutrition']));
    expect(afterAdd.steps[1]?.complete).toBe(true);
    expect(afterAdd.steps[2]?.complete).toBe(true);
    expect(afterAdd.target).toEqual({ kind: 'navigate', section: 'progress' });

    const complete = getDemoRouteState(
      'nutrition',
      snapshot,
      'progress',
      new Set(['nutrition', 'progress']),
    );
    expect(complete.complete).toBe(true);
  });

  it('completes the training route from finish and the real progress visit', () => {
    const snapshot = demoFixture('self_training');
    if (snapshot.state.kind !== 'self_training') throw new Error('Expected training fixture');
    snapshot.state.screen = 'summary';

    const route = getDemoRouteState(
      'self_training',
      snapshot,
      'progress',
      new Set(['plan', 'progress']),
    );
    expect(route.complete).toBe(true);
    expect(route.target).toBeNull();
  });

  it('keeps the trainer route connected to the real workspace milestones', () => {
    const snapshot = demoFixture('trainer');
    if (snapshot.state.kind !== 'trainer') throw new Error('Expected trainer fixture');
    snapshot.state.selected_client_id = snapshot.state.clients[0]?.id ?? 'alexey';
    const visited = new Set([
      'trainer',
      'trainer:attention',
      'trainer:client',
      'trainer:workout',
      'trainer:progress',
      'trainer:operations',
      'trainer:task',
      'trainer:return',
    ]);

    const route = getDemoRouteState('trainer', snapshot, 'trainer', visited);

    expect(route.steps.map((step) => step.label)).toEqual([
      'Сегодня',
      'Внимание',
      'Клиент',
      'Тренировка',
      'Прогресс',
      'Операции',
      'Задача',
      'Назад в Сегодня',
    ]);
    expect(route.complete).toBe(true);
    expect(route.target).toBeNull();
  });
});
