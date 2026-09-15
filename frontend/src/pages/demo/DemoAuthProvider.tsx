import { useCallback, useEffect, useMemo, useState } from 'react';
import { AuthContextProvider, type AuthContextValue } from '../../app/AuthProvider';
import { api, ApiError } from '../../shared/api/client';
import type { PublicConfig, User } from '../../shared/api/types';
import { useRuntime } from '../../shared/runtime/runtime';

const demoConfig: PublicConfig = {
  app_env: 'demo',
  enable_dev_auth: false,
  enable_web_auth: false,
  enable_email_auth: false,
  telegram_bot_username: '',
  oauth_providers: [],
};

function demoUnavailable(): never {
  throw new Error('Авторизация и действия с аккаунтом недоступны в демо-режиме.');
}

export function DemoAuthProvider({ children }: { children: React.ReactNode }) {
  const runtime = useRuntime();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const sessionToken = runtime.kind === 'demo' ? runtime.sessionToken : null;

  const reloadUser = useCallback(async (): Promise<User | null> => {
    try {
      const current = await api<User>('/api/v1/me', { retryAuth: false });
      setUser(current);
      setError(null);
      return current;
    } catch (reason) {
      const message =
        reason instanceof ApiError && reason.status === 410
          ? 'Демо-сессия истекла. Начните демо заново.'
          : reason instanceof Error
            ? reason.message
            : 'Не удалось загрузить демо-профиль';
      setError(message);
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve()
      .then(() => reloadUser())
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadUser, runtime.kind, sessionToken]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      config: demoConfig,
      loading,
      error,
      updateUser: setUser,
      reloadUser,
      devLogin: async () => demoUnavailable(),
      telegramLogin: async () => demoUnavailable(),
      emailLogin: async () => demoUnavailable(),
      emailRegister: async () => demoUnavailable(),
      verifyEmail: async () => demoUnavailable(),
      requestPasswordReset: async () => demoUnavailable(),
      confirmPasswordReset: async () => demoUnavailable(),
      logout: async () => undefined,
    }),
    [error, loading, reloadUser, user],
  );

  if (loading) return <p role="status">Загружаем демо-профиль…</p>;
  if (!user) return <p role="alert">{error ?? 'Демо-профиль недоступен.'}</p>;
  return <AuthContextProvider value={value}>{children}</AuthContextProvider>;
}

export default DemoAuthProvider;
