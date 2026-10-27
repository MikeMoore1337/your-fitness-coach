import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TrainerIntentFlow } from '../../../../src/features/trainer/TrainerIntentFlow';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
const reloadUserMock = vi.hoisted(() => vi.fn());
const trackProductEventMock = vi.hoisted(() => vi.fn());
const trackGrowthEventMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/shared/analytics/productEvents', () => ({
  productEventSurface: () => 'desktop_web',
  trackGrowthEvent: trackGrowthEventMock,
  trackProductEvent: trackProductEventMock,
}));
vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({ reloadUser: reloadUserMock }),
}));

function state(overrides: Record<string, unknown> = {}) {
  return {
    is_active: false,
    activated_now: false,
    active_client_count: 0,
    pending_invite_count: 0,
    can_disable: false,
    terms_version: 'trainer-capability-v1',
    ...overrides,
  };
}

function renderFlow() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <FeedbackProvider>
          <TrainerIntentFlow />
        </FeedbackProvider>
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

describe('TrainerIntentFlow', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/app?trainer_intent=1');
    apiMock.mockReset();
    reloadUserMock.mockReset().mockResolvedValue(null);
    trackGrowthEventMock.mockReset();
    trackProductEventMock.mockReset();
  });

  afterEach(cleanup);

  it('проверяет capability, просит явное согласие и открывает Coach Today после активации', async () => {
    let current = state();
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/me/trainer-capability' && options?.method === 'POST') {
        current = state({ is_active: true, activated_now: true, can_disable: true });
      }
      return Promise.resolve(current);
    });

    renderFlow();
    const activate = await screen.findByRole('button', { name: 'Включить режим тренера' });
    expect(activate).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /принимаю условия/i }));
    fireEvent.click(activate);

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/v1/me/trainer-capability', {
        method: 'POST',
        body: { accepted_terms: true },
      }),
    );
    await waitFor(() => expect(window.location.pathname).toBe('/coach'));
    expect(trackGrowthEventMock).toHaveBeenCalledWith('trainer_application_started');
    expect(trackGrowthEventMock).toHaveBeenCalledWith('trainer_application_completed');
    expect(trackProductEventMock).toHaveBeenCalledWith({
      name: 'trainer_mode_activated',
      surface: 'desktop_web',
    });
    expect(trackProductEventMock).toHaveBeenCalledWith(
      { name: 'trainer_onboarding_started', surface: 'desktop_web' },
      { dedupe: 'session' },
    );
  });

  it('не активирует повторно уже действующего тренера', async () => {
    apiMock.mockResolvedValue(state({ is_active: true, can_disable: true }));

    renderFlow();

    await waitFor(() => expect(window.location.pathname).toBe('/coach'));
    expect(apiMock).toHaveBeenCalledTimes(1);
    expect(apiMock).not.toHaveBeenCalledWith('/api/v1/me/trainer-capability', {
      method: 'POST',
      body: { accepted_terms: true },
    });
    expect(trackGrowthEventMock).not.toHaveBeenCalled();
  });

  it('не создаёт повторный success event при идемпотентном ответе API', async () => {
    let current = state();
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/me/trainer-capability' && options?.method === 'POST') {
        current = state({ is_active: true, activated_now: false, can_disable: true });
      }
      return Promise.resolve(current);
    });

    renderFlow();
    fireEvent.click(await screen.findByRole('checkbox', { name: /принимаю условия/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Включить режим тренера' }));

    await waitFor(() => expect(window.location.pathname).toBe('/coach'));
    expect(trackGrowthEventMock).toHaveBeenCalledWith('trainer_application_started');
    expect(trackGrowthEventMock).not.toHaveBeenCalledWith('trainer_application_completed');
    expect(trackProductEventMock).not.toHaveBeenCalled();
  });

  it('отмена возвращает в личный сценарий без повторного intent', async () => {
    apiMock.mockResolvedValue(state());
    renderFlow();

    fireEvent.click(await screen.findByRole('button', { name: 'Не сейчас' }));

    await waitFor(() => expect(window.location.pathname).toBe('/app'));
    expect(window.location.search).toBe('?section=today');
  });
});
