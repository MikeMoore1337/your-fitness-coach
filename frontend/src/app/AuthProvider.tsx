import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  AUTH_LOGOUT_EVENT,
  api,
  ApiError,
  clearAccessToken,
  getAccessToken,
  refreshAccessToken,
  setAccessToken,
} from '../shared/api/client';
import type { PublicConfig, User } from '../shared/api/types';
import { LIVE_DATA_REFETCH_INTERVAL_MS } from '../shared/sync';
import type { TelegramWebApp } from '../shared/telegram/types';
import { useQueryClient } from '@tanstack/react-query';
import { loadCurrentActiveWorkoutSnapshot } from '../features/workouts/activeWorkoutQueue';
import {
  AUTHENTICATED_USER_ID_STORAGE_KEY,
  clearSensitiveUserScopedStorage,
} from '../shared/userScopedStorage';
import { syncFirstTouchAttribution } from '../shared/analytics/attribution';
import { trackProductLoginCompletedIfStarted } from '../shared/analytics/productEvents';
import { YFC_PLATFORM_ACTIVATED_EVENT } from '../shared/telegram/layout';
import { revokeWebPushSubscription } from '../shared/notifications/webPush';

function offlineWorkoutUser(): User | null {
  if (!getAccessToken()) return null;
  const userId = Number(sessionStorage.getItem(AUTHENTICATED_USER_ID_STORAGE_KEY));
  if (!Number.isInteger(userId) || userId <= 0) return null;
  if (!loadCurrentActiveWorkoutSnapshot(userId)) return null;
  return {
    id: userId,
    is_coach: false,
    is_admin: false,
    is_root: false,
    has_active_program: true,
    has_workout_history: false,
    has_food_history: false,
    onboarding: { status: 'complete', required_fields: [], missing_fields: [] },
    profile: null,
    trainer: null,
  };
}

export interface DevLoginInput {
  telegram_user_id: number;
  username?: string;
  full_name?: string;
  is_coach: boolean;
  is_admin: boolean;
}

interface EmailRegistrationResult {
  verification_required: boolean;
  verification_token?: string | null;
}

export interface AuthContextValue {
  user: User | null;
  config: PublicConfig | null;
  loading: boolean;
  error: string | null;
  updateUser(user: User): void;
  reloadUser(): Promise<User | null>;
  devLogin(input: DevLoginInput): Promise<void>;
  telegramLogin(telegram?: TelegramWebApp | null): Promise<void>;
  emailLogin(email: string, password: string): Promise<void>;
  emailRegister(
    username: string,
    email: string,
    password: string,
    nextPath?: string | null,
  ): Promise<EmailRegistrationResult>;
  verifyEmail(token: string): Promise<void>;
  requestPasswordReset(email: string): Promise<void>;
  confirmPasswordReset(token: string, password: string): Promise<void>;
  logout(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthContextProvider({
  children,
  value,
}: {
  children: React.ReactNode;
  value: AuthContextValue;
}) {
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const userIdRef = useRef<number | null>(null);

  const clearCurrentUserData = useCallback(() => {
    clearSensitiveUserScopedStorage();
    userIdRef.current = null;
  }, []);

  const acceptAuthenticatedUser = useCallback((current: User) => {
    const storedUserId = Number(sessionStorage.getItem(AUTHENTICATED_USER_ID_STORAGE_KEY));
    const previousUserId =
      userIdRef.current ?? (Number.isInteger(storedUserId) ? storedUserId : null);
    if (previousUserId && previousUserId !== current.id) clearSensitiveUserScopedStorage();
    sessionStorage.setItem(AUTHENTICATED_USER_ID_STORAGE_KEY, String(current.id));
    userIdRef.current = current.id;
    setUser(current);
  }, []);

  const reloadUser = useCallback(async (): Promise<User | null> => {
    try {
      const current = await api<User>('/api/v1/me');
      acceptAuthenticatedUser(current);
      setError(null);
      return current;
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 0) {
        const cached = offlineWorkoutUser();
        if (cached) {
          userIdRef.current = cached.id;
          setUser(cached);
          setError(null);
          return cached;
        }
      }
      if (reason instanceof ApiError && [401, 403].includes(reason.status)) {
        clearAccessToken();
        clearCurrentUserData();
        setUser(null);
        setError(null);
        return null;
      }
      setError(reason instanceof Error ? reason.message : 'Не удалось загрузить профиль');
      return null;
    }
  }, [acceptAuthenticatedUser, clearCurrentUserData]);

  const syncUser = useCallback(async (): Promise<void> => {
    try {
      const current = await api<User>('/api/v1/me');
      acceptAuthenticatedUser(current);
      setError(null);
    } catch (reason) {
      // A temporary connection error must not log the user out. An expired session should.
      if (reason instanceof ApiError && reason.status === 401) {
        clearCurrentUserData();
        setUser(null);
      }
    }
  }, [acceptAuthenticatedUser, clearCurrentUserData]);

  const userId = user?.id;
  useEffect(() => {
    if (!userId) return;
    trackProductLoginCompletedIfStarted();
    void syncFirstTouchAttribution(userId);
  }, [userId]);

  useEffect(() => {
    if (!userId) return;

    const syncVisibleUser = () => {
      if (document.visibilityState === 'visible') void syncUser();
    };
    const syncActivatedUser = () => void syncUser();
    const interval = window.setInterval(syncVisibleUser, LIVE_DATA_REFETCH_INTERVAL_MS);
    window.addEventListener('focus', syncVisibleUser);
    window.addEventListener(YFC_PLATFORM_ACTIVATED_EVENT, syncActivatedUser);
    document.addEventListener('visibilitychange', syncVisibleUser);

    return () => {
      window.clearInterval(interval);
      window.removeEventListener('focus', syncVisibleUser);
      window.removeEventListener(YFC_PLATFORM_ACTIVATED_EVENT, syncActivatedUser);
      document.removeEventListener('visibilitychange', syncVisibleUser);
    };
  }, [syncUser, userId]);

  const telegramLogin = useCallback(
    async (telegram: TelegramWebApp | null = window.Telegram?.WebApp ?? null) => {
      const initData = telegram?.initData?.trim();
      if (!initData) throw new Error('Telegram не передал данные авторизации');
      await revokeWebPushSubscription().catch(() => undefined);
      const token = await api<{ access_token: string }>('/api/v1/auth/telegram/init', {
        method: 'POST',
        body: { init_data: initData },
        retryAuth: false,
      });
      clearCurrentUserData();
      setUser(null);
      setError(null);
      queryClient.clear();
      setAccessToken(token.access_token);
      await reloadUser();
    },
    [clearCurrentUserData, queryClient, reloadUser],
  );

  const devLogin = useCallback(
    async (input: DevLoginInput) => {
      await revokeWebPushSubscription().catch(() => undefined);
      const token = await api<{ access_token: string }>('/api/v1/auth/dev-login', {
        method: 'POST',
        body: input,
        retryAuth: false,
      });
      clearCurrentUserData();
      setUser(null);
      setError(null);
      queryClient.clear();
      setAccessToken(token.access_token);
      await reloadUser();
    },
    [clearCurrentUserData, queryClient, reloadUser],
  );

  const acceptToken = useCallback(
    async (token: { access_token: string }) => {
      await revokeWebPushSubscription().catch(() => undefined);
      clearCurrentUserData();
      setUser(null);
      setError(null);
      queryClient.clear();
      setAccessToken(token.access_token);
      await reloadUser();
    },
    [clearCurrentUserData, queryClient, reloadUser],
  );

  const emailLogin = useCallback(
    async (email: string, password: string) => {
      const token = await api<{ access_token: string }>('/api/v1/auth/email/login', {
        method: 'POST',
        body: { email, password },
        retryAuth: false,
      });
      await acceptToken(token);
    },
    [acceptToken],
  );

  const emailRegister = useCallback(
    (username: string, email: string, password: string, nextPath?: string | null) =>
      api<EmailRegistrationResult>('/api/v1/auth/email/register', {
        method: 'POST',
        body: { username, email, password, next_path: nextPath || null },
        retryAuth: false,
      }),
    [],
  );

  const verifyEmail = useCallback(
    async (verificationToken: string) => {
      const token = await api<{ access_token: string }>('/api/v1/auth/email/verify', {
        method: 'POST',
        body: { token: verificationToken },
        retryAuth: false,
      });
      await acceptToken(token);
    },
    [acceptToken],
  );

  const requestPasswordReset = useCallback(async (email: string) => {
    await api('/api/v1/auth/password/reset/request', {
      method: 'POST',
      body: { email },
      retryAuth: false,
    });
  }, []);

  const confirmPasswordReset = useCallback(async (token: string, password: string) => {
    await api('/api/v1/auth/password/reset/confirm', {
      method: 'POST',
      body: { token, password },
      retryAuth: false,
    });
  }, []);

  const logout = useCallback(async () => {
    const revoke = revokeWebPushSubscription().catch(() => undefined);
    const serverLogout = api('/api/v1/auth/logout', {
      method: 'POST',
      body: {},
      retryAuth: false,
      timeoutMs: 3_000,
    }).catch(() => undefined);
    clearCurrentUserData();
    clearAccessToken();
    setUser(null);
    queryClient.clear();
    await Promise.all([serverLogout, revoke]);
  }, [clearCurrentUserData, queryClient]);

  useEffect(() => {
    const handleAuthLogout = () => {
      clearCurrentUserData();
      setUser(null);
      queryClient.clear();
    };
    window.addEventListener(AUTH_LOGOUT_EVENT, handleAuthLogout);
    return () => window.removeEventListener(AUTH_LOGOUT_EVENT, handleAuthLogout);
  }, [clearCurrentUserData, queryClient]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const publicConfig = await api<PublicConfig>('/api/v1/public/config', {
          retryAuth: false,
        });
        if (cancelled) return;
        setConfig(publicConfig);

        const tg = window.Telegram?.WebApp;
        if (tg?.initData?.trim()) {
          await revokeWebPushSubscription().catch(() => undefined);
          clearCurrentUserData();
          clearAccessToken();
          setUser(null);
          queryClient.clear();
          try {
            await telegramLogin(tg);
          } catch (reason) {
            if (!cancelled) {
              setError(
                reason instanceof Error ? reason.message : 'Не удалось войти через Telegram',
              );
            }
          }
          return;
        }

        if (getAccessToken()) {
          const current = await reloadUser();
          if (current || cancelled) return;
        }

        // The access token deliberately lives only in sessionStorage. A page reload in a
        // new tab can still restore the session through the HttpOnly refresh cookie.
        if (!getAccessToken() && (await refreshAccessToken())) {
          const current = await reloadUser();
          if (current || cancelled) return;
        }
      } catch (reason) {
        if (!cancelled) {
          const cached =
            reason instanceof ApiError && reason.status === 0 ? offlineWorkoutUser() : null;
          if (cached) {
            setUser(cached);
            setError(null);
          } else {
            setError(reason instanceof Error ? reason.message : 'Не удалось запустить приложение');
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clearCurrentUserData, queryClient, reloadUser, telegramLogin]);

  const value = useMemo(
    () => ({
      user,
      config,
      loading,
      error,
      updateUser: acceptAuthenticatedUser,
      reloadUser,
      devLogin,
      telegramLogin,
      emailLogin,
      emailRegister,
      verifyEmail,
      requestPasswordReset,
      confirmPasswordReset,
      logout,
    }),
    [
      user,
      config,
      loading,
      error,
      acceptAuthenticatedUser,
      reloadUser,
      devLogin,
      telegramLogin,
      emailLogin,
      emailRegister,
      verifyEmail,
      requestPasswordReset,
      confirmPasswordReset,
      logout,
    ],
  );
  return <AuthContextProvider value={value}>{children}</AuthContextProvider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}

export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext);
}
