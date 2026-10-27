import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthGate, telegramMiniAppUrl } from '../../../src/app/AuthGate';
import { NavigationProvider } from '../../../src/shared/navigation/router';

const { authState } = vi.hoisted(() => ({
  authState: {
    user: null as { id: number } | null,
    config: {
      telegram_bot_username: 'fitness_bot',
    },
    loading: false,
    error: null as string | null,
    telegramLogin: vi.fn(),
  },
}));

vi.mock('../../../src/app/AuthProvider', () => ({
  useAuth: () => authState,
}));

describe('AuthGate', () => {
  beforeEach(() => {
    authState.user = null;
    authState.loading = false;
    authState.error = null;
    authState.telegramLogin.mockReset();
    window.history.replaceState(null, '', '/coach');
    delete window.Telegram;
  });

  afterEach(() => {
    delete window.Telegram;
  });

  it('redirects an unauthenticated browser route to canonical login with a safe return', async () => {
    render(
      <NavigationProvider>
        <AuthGate>Кабинет</AuthGate>
      </NavigationProvider>,
    );

    await waitFor(() => expect(window.location.pathname).toBe('/login'));
    expect(window.location.search).toBe('?next=%2Fcoach');
  });

  it('preserves query and hash deep links through browser login', async () => {
    window.history.replaceState(null, '', '/app?section=nutrition#meal-dinner');
    render(
      <NavigationProvider>
        <AuthGate>Питание</AuthGate>
      </NavigationProvider>,
    );

    await waitFor(() => expect(window.location.pathname).toBe('/login'));
    expect(window.location.search).toBe('?next=%2Fapp%3Fsection%3Dnutrition%23meal-dinner');
  });

  it('renders the requested route after authentication', () => {
    authState.user = { id: 7 };
    render(
      <NavigationProvider>
        <AuthGate>Кабинет</AuthGate>
      </NavigationProvider>,
    );

    expect(screen.getByText('Кабинет')).toBeInTheDocument();
  });

  it('shows Telegram-specific recovery without a browser provider chooser', () => {
    window.history.replaceState(null, '', '/app?tgWebAppPlatform=android');
    authState.error = 'raw initData error';

    render(
      <NavigationProvider>
        <AuthGate>Приложение</AuthGate>
      </NavigationProvider>,
    );

    expect(
      screen.getByRole('heading', { name: 'Не удалось подтвердить вход' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Открыть заново в Telegram' })).toHaveAttribute(
      'href',
      'https://t.me/fitness_bot?startapp',
    );
    expect(screen.queryByText(/выберите удобный способ/i)).not.toBeInTheDocument();
    expect(screen.queryByText('raw initData error')).not.toBeInTheDocument();
  });

  it('normalizes Telegram usernames for Mini App links', () => {
    expect(telegramMiniAppUrl('@fitness_bot')).toBe('https://t.me/fitness_bot?startapp');
  });
});
