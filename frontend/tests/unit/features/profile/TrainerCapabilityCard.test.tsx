import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TrainerCapabilityCard } from '../../../../src/features/profile/TrainerCapabilityCard';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
const reloadUserMock = vi.hoisted(() => vi.fn());
const trackProductEventMock = vi.hoisted(() => vi.fn());
const trackGrowthEventMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/shared/analytics/productEvents', () => ({
  productEventSurface: () => 'tma',
  trackGrowthEvent: trackGrowthEventMock,
  trackProductEvent: trackProductEventMock,
}));
vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({
    user: { id: 10, is_coach: false, is_admin: false },
    reloadUser: reloadUserMock,
  }),
}));

function renderCard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <FeedbackProvider>
          <TrainerCapabilityCard />
        </FeedbackProvider>
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

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

describe('TrainerCapabilityCard', () => {
  beforeEach(() => {
    apiMock.mockReset();
    reloadUserMock.mockReset().mockResolvedValue(null);
    trackGrowthEventMock.mockReset();
    trackProductEventMock.mockReset();
  });

  afterEach(cleanup);

  it('включает режим только после принятия условий', async () => {
    let current = state();
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/me/trainer-capability' && options?.method === 'POST') {
        current = state({ is_active: true, activated_now: true, can_disable: true });
      }
      return Promise.resolve(current);
    });
    renderCard();

    const activate = await screen.findByRole('button', { name: 'Включить режим тренера' });
    expect(activate).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /принимаю условия/i }));
    expect(activate).toBeEnabled();
    fireEvent.click(activate);

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/v1/me/trainer-capability', {
        method: 'POST',
        body: { accepted_terms: true },
      }),
    );
    expect(
      await screen.findByText('Режим тренера включён', { selector: 'strong' }),
    ).toBeInTheDocument();
    expect(reloadUserMock).toHaveBeenCalled();
    expect(trackGrowthEventMock).toHaveBeenNthCalledWith(1, 'trainer_application_started');
    expect(trackGrowthEventMock).toHaveBeenNthCalledWith(2, 'trainer_application_completed');
    expect(trackProductEventMock).toHaveBeenCalledWith({
      name: 'trainer_mode_activated',
      surface: 'tma',
    });
  });

  it('не дублирует activation event для идемпотентного ответа API', async () => {
    let current = state();
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/me/trainer-capability' && options?.method === 'POST') {
        current = state({ is_active: true, activated_now: false, can_disable: true });
      }
      return Promise.resolve(current);
    });
    renderCard();

    const activate = await screen.findByRole('button', { name: 'Включить режим тренера' });
    fireEvent.click(screen.getByRole('checkbox', { name: /принимаю условия/i }));
    fireEvent.click(activate);

    expect(
      await screen.findByText('Режим тренера включён', { selector: 'strong' }),
    ).toBeInTheDocument();
    expect(trackGrowthEventMock).toHaveBeenCalledWith('trainer_application_started');
    expect(trackGrowthEventMock).not.toHaveBeenCalledWith('trainer_application_completed');
    expect(trackProductEventMock).not.toHaveBeenCalled();
  });

  it('показывает neutral switch и безопасно отключает режим без клиентов', async () => {
    let current = state({ is_active: true, can_disable: true, pending_invite_count: 2 });
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/me/trainer-capability' && options?.method === 'DELETE') {
        current = state();
      }
      return Promise.resolve(current);
    });
    renderCard();

    expect(await screen.findByRole('navigation', { name: 'Режим работы' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Выключить режим тренера' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/2 ожидающих приглашений будут отозваны/i)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Выключить' }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/v1/me/trainer-capability', {
        method: 'DELETE',
      }),
    );
    expect(await screen.findByRole('button', { name: 'Включить режим тренера' })).toBeDisabled();
  });

  it('блокирует отключение при активных клиентах и объясняет причину', async () => {
    apiMock.mockResolvedValue(
      state({ is_active: true, active_client_count: 2, can_disable: false }),
    );
    renderCard();

    expect(await screen.findByText(/всеми активными клиентами \(2\)/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Выключить режим тренера' })).toBeDisabled();
    expect(apiMock).toHaveBeenCalledTimes(1);
  });
});
