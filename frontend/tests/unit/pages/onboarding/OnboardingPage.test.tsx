import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OnboardingPage from '../../../../src/pages/onboarding/OnboardingPage';
import {
  clearProductOnboardingCompletionMarker,
  PRODUCT_EVENT_NAME,
  PRODUCT_EVENT_SCHEMA_VERSION,
} from '../../../../src/shared/analytics/productEvents';
import { NavigationProvider } from '../../../../src/shared/navigation/router';

const apiMock = vi.hoisted(() => vi.fn());
const reloadUserMock = vi.hoisted(() => vi.fn());
const useAuthMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/app/AuthProvider', () => ({ useAuth: useAuthMock }));

const requiredUser = {
  id: 10,
  onboarding: { status: 'required', required_fields: ['goal'], missing_fields: ['goal'] },
  profile: { goal: null },
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <OnboardingPage />
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

describe('OnboardingPage', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/onboarding?next=%2Fapp');
    apiMock.mockReset();
    reloadUserMock.mockReset().mockResolvedValue(null);
    useAuthMock.mockReturnValue({ user: requiredUser, reloadUser: reloadUserMock });
  });

  afterEach(() => {
    cleanup();
    clearProductOnboardingCompletionMarker();
  });

  it('saves only the canonical goal and emits body-value-free activation events', async () => {
    const events: unknown[] = [];
    const listener = (event: Event) => events.push((event as CustomEvent).detail);
    window.addEventListener(PRODUCT_EVENT_NAME, listener);
    apiMock.mockResolvedValue({
      ...requiredUser,
      onboarding: { status: 'complete', required_fields: ['goal'], missing_fields: [] },
      profile: { goal: 'maintenance' },
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Выберите одну цель');
    expect(apiMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText(/^Поддерживать форму/));
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));

    await waitFor(() => expect(window.location.pathname).toBe('/app'));
    expect(window.location.search).toBe('?section=today');
    expect(apiMock).toHaveBeenCalledWith('/api/v1/me/profile', {
      method: 'PATCH',
      body: { goal: 'maintenance' },
    });
    expect(reloadUserMock).toHaveBeenCalledOnce();
    expect(events).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          name: 'onboarding_started',
          surface: 'desktop_web',
          schema_version: PRODUCT_EVENT_SCHEMA_VERSION,
          environment: 'test',
        }),
        expect.objectContaining({
          name: 'onboarding_completed',
          surface: 'desktop_web',
          schema_version: PRODUCT_EVENT_SCHEMA_VERSION,
          environment: 'test',
        }),
      ]),
    );
    expect(JSON.stringify(events)).not.toContain('maintenance');
    window.removeEventListener(PRODUCT_EVENT_NAME, listener);
  });

  it('keeps the selected goal after a save error so the user can retry', async () => {
    apiMock.mockRejectedValue(new Error('Связь прервалась'));
    renderPage();

    const goal = screen.getByLabelText(/^Снизить вес/);
    fireEvent.click(goal);
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));

    await screen.findByText('Связь прервалась');
    expect(goal).toBeChecked();
    expect(screen.getByRole('heading', { name: 'Какая у вас главная цель?' })).toBeVisible();
  });

  it('preserves an allowlisted explicit continuation after the goal is saved', async () => {
    window.history.replaceState(null, '', '/onboarding?next=%2Fcoach');
    apiMock.mockResolvedValue({
      ...requiredUser,
      onboarding: { status: 'complete', required_fields: ['goal'], missing_fields: [] },
      profile: { goal: 'maintenance' },
    });
    renderPage();

    fireEvent.click(screen.getByLabelText(/^Поддерживать форму/));
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));

    await waitFor(() => expect(window.location.pathname).toBe('/coach'));
    expect(window.location.search).toBe('');
  });

  it('keeps the completion screen focused on Today instead of a three-way chooser', async () => {
    useAuthMock.mockReturnValue({
      user: {
        ...requiredUser,
        onboarding: { status: 'complete', required_fields: ['goal'], missing_fields: [] },
        profile: { goal: 'fat_loss' },
      },
      reloadUser: reloadUserMock,
    });
    renderPage();

    expect(await screen.findByRole('heading', { name: 'С чего хотите начать?' })).toBeVisible();
    expect(screen.queryByRole('button', { name: /Настроить питание/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Открыть «Сегодня»/ }));
    await waitFor(() => expect(window.location.pathname).toBe('/app'));
    expect(window.location.search).toBe('?section=today');
  });
});
