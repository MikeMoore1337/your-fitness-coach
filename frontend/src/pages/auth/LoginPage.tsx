import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../app/AuthProvider';
import { EmailAuthPanel } from '../../features/auth/EmailAuthPanel';
import { configuredOAuthProviders, OAuthButtons } from '../../features/auth/OAuthButtons';
import { oauthStartHref, providerLabel, safeOAuthProvider } from '../../shared/auth/oauthRecovery';
import { safeAuthNextPath } from '../../shared/auth/redirects';
import { AppLink, demoReturnPathFromLogin, useNavigation } from '../../shared/navigation/router';
import { ErrorState, LoadingState } from '../../shared/ui/common';
import { BrandLockup } from '../../shared/ui/BrandLogo';
import { PublicShell } from '../../shared/ui/PublicShell';
import { telegramMiniAppUrl } from '../../shared/telegram/publicLinks';
import { useSemanticMotion } from '../../shared/ui/useSemanticMotion';
import {
  clearProductLoginAttempt,
  markProductLoginStarted,
} from '../../shared/analytics/productEvents';
import './auth.css';

const AUTH_ERROR_MESSAGES: Record<string, { title: string; message: string }> = {
  unavailable: {
    title: 'Способ входа временно недоступен',
    message: 'Выберите другой способ или повторите попытку позже.',
  },
  denied: {
    title: 'Вход отменён',
    message: 'Разрешение не было выдано. Можно выбрать этот способ ещё раз или попробовать другой.',
  },
  invalid_state: {
    title: 'Ссылка входа устарела',
    message: 'Начните вход заново — прежняя защищённая сессия больше недействительна.',
  },
  blocked: {
    title: 'Доступ к аккаунту ограничен',
    message: 'Войти сейчас нельзя. Если это неожиданно, обратитесь в поддержку.',
  },
  conflict: {
    title: 'Этот способ уже связан с другим аккаунтом',
    message:
      'Мы не объединяем аккаунты автоматически. Войдите другим способом или обратитесь в поддержку.',
  },
  provider_failure: {
    title: 'Не удалось завершить вход',
    message:
      'Сервис авторизации не ответил корректно. Повторите попытку или выберите другой способ.',
  },
};

function AuthErrorNotice({ code }: { code: string | null }) {
  const error = code ? AUTH_ERROR_MESSAGES[code] : null;
  if (!error) return null;
  return (
    <div className="login-alert" role="alert">
      <strong>{error.title}</strong>
      <span>{error.message}</span>
    </div>
  );
}

function DevLoginControls({
  hasExplicitNext,
  nextPath,
  onDestinationChange,
}: {
  hasExplicitNext: boolean;
  nextPath: string;
  onDestinationChange: (path: string) => void;
}) {
  const { devLogin } = useAuth();
  const { navigate } = useNavigation();
  const [busyRole, setBusyRole] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const roles = [
    {
      label: 'Клиент',
      defaultPath: '/app',
      telegram_user_id: 2001,
      username: 'demo_client',
      is_coach: false,
      is_admin: false,
    },
    {
      label: 'Тренер',
      defaultPath: '/coach',
      telegram_user_id: 1002,
      username: 'demo_coach',
      is_coach: true,
      is_admin: false,
    },
    {
      label: 'Админ',
      defaultPath: '/admin',
      telegram_user_id: 1001,
      username: 'demo_admin',
      is_coach: true,
      is_admin: true,
    },
  ];

  return (
    <section className="login-dev" aria-label="Локальный режим разработки">
      <p>Локальный режим разработки</p>
      {error && <ErrorState message={error} />}
      <div className="auth-presets">
        {roles.map(({ label, defaultPath, ...input }) => (
          <button
            key={label}
            type="button"
            className="secondary"
            disabled={busyRole !== null}
            onClick={() => {
              const destination = hasExplicitNext ? nextPath : defaultPath;
              onDestinationChange(destination);
              setBusyRole(label);
              setError(null);
              markProductLoginStarted();
              void devLogin({ ...input, full_name: `Демо ${label.toLowerCase()}` })
                .then(() => navigate(destination, true))
                .catch((reason: unknown) => {
                  clearProductLoginAttempt();
                  setError(reason instanceof Error ? reason.message : 'Не удалось войти');
                })
                .finally(() => setBusyRole(null));
            }}
          >
            {busyRole === label ? 'Входим…' : label}
          </button>
        ))}
      </div>
    </section>
  );
}

export default function LoginPage() {
  const { user, config, loading, error } = useAuth();
  const { navigate } = useNavigation();
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const hasExplicitNext = params.has('next');
  const nextPath = safeAuthNextPath(params.get('next'));
  const [devLoginDestination, setDevLoginDestination] = useState<string | null>(null);
  const authenticatedDestination =
    devLoginDestination ??
    (hasExplicitNext ? nextPath : user?.is_root ? '/admin' : user?.is_coach ? '/coach' : nextPath);
  const demoReturnPath = demoReturnPathFromLogin(window.location.search);
  const authErrorCode = params.get('auth_error');
  const providers = configuredOAuthProviders(config?.enable_web_auth ? config.oauth_providers : []);
  const requestedOAuthProvider = safeOAuthProvider(params.get('oauth_provider'));
  const retryProvider =
    requestedOAuthProvider && providers.includes(requestedOAuthProvider)
      ? requestedOAuthProvider
      : (providers[0] ?? null);
  const retryHref = retryProvider ? oauthStartHref(retryProvider, nextPath) : null;
  const retryLabel =
    retryProvider && retryProvider === requestedOAuthProvider
      ? `Повторить вход через ${providerLabel(retryProvider)}`
      : 'Повторить';
  const telegramAppUrl = config?.telegram_bot_username
    ? telegramMiniAppUrl(config.telegram_bot_username)
    : null;
  const loginMotion = useSemanticMotion<HTMLElement>(loading ? 'loading' : 'ready', {
    animateInitial: !loading && !user && !authErrorCode,
    elementId: 'login-content',
  });
  const loginMotionEnabled = !user && !authErrorCode;

  useEffect(() => {
    if (!loading && user) navigate(authenticatedDestination, true);
  }, [authenticatedDestination, loading, navigate, user]);

  useEffect(() => {
    if (authErrorCode) clearProductLoginAttempt();
  }, [authErrorCode]);

  return (
    <PublicShell
      className="auth-public-shell auth-public-shell--design-v2 auth-public-shell--design-v2-1"
      skipTarget="login-content"
    >
      <main
        id="login-content"
        className="login-layout"
        data-motion-phase={loginMotionEnabled ? loginMotion.motionPhase : 'idle'}
        data-motion-revision={loginMotion.motionRevision}
        onAnimationEnd={loginMotion.onMotionAnimationEnd}
        tabIndex={-1}
      >
        <section className="login-intro" aria-labelledby="login-title">
          <BrandLockup className="login-continuation-brand" surface="dark" />
          <div className="login-continuation">
            <p className="login-kicker">Продолжение</p>
            <h1 id="login-title">
              <span className="login-title--desktop">Вернитесь к своему плану.</span>
              <span className="login-title--mobile">Войти и продолжить</span>
            </h1>
            <p className="login-copy--desktop">
              Вход связывает browser и Telegram с одной учётной записью. Аккаунты не объединяются
              автоматически.
            </p>
            <p className="login-copy--mobile">
              После входа откроется запрошенный раздел. Используйте уже связанный способ.
            </p>
          </div>
          <small className="login-surface-note">Web · защищённый переход</small>
        </section>

        <section className="login-card" aria-label="Способы входа">
          {demoReturnPath && (
            <aside className="login-demo-context" aria-label="Переход из демо">
              <div>
                <strong>После демо — чистый профиль</strong>
                <span>Изменения не переносятся. Приложение откроется сразу.</span>
              </div>
              <AppLink to={demoReturnPath}>Вернуться в демо</AppLink>
            </aside>
          )}
          <div className="login-auth-heading">
            <p className="login-kicker">Вход</p>
            <h2>Выберите способ</h2>
            <p>После входа вы вернётесь к запрошенному разделу.</p>
          </div>
          {loading || user ? (
            <LoadingState label={user ? 'Перенаправляем…' : 'Проверяем авторизацию…'} />
          ) : (
            <div className="login-card__content">
              <AuthErrorNotice code={authErrorCode} />
              {error && (
                <ErrorState message="Не удалось связаться с сервером. Проверьте интернет и повторите попытку." />
              )}
              {providers.length > 0 && <OAuthButtons providers={providers} nextPath={nextPath} />}
              {!providers.length && !config?.enable_email_auth && (
                <div className="login-unavailable" role="status">
                  <strong>Вход через браузер пока недоступен</strong>
                  <span>Откройте приложение в Telegram или повторите попытку позже.</span>
                </div>
              )}
              {!providers.includes('telegram') && telegramAppUrl && (
                <a
                  className="login-telegram-fallback"
                  href={telegramAppUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  Открыть в Telegram
                </a>
              )}
              {config?.enable_email_auth && <EmailAuthPanel nextPath={nextPath} />}
              {config?.enable_dev_auth && (
                <DevLoginControls
                  hasExplicitNext={hasExplicitNext}
                  nextPath={nextPath}
                  onDestinationChange={setDevLoginDestination}
                />
              )}
              {(error || authErrorCode) && retryHref && (
                <a
                  className="login-retry"
                  href={retryHref}
                  onClick={() => markProductLoginStarted()}
                >
                  {retryLabel}
                </a>
              )}
            </div>
          )}
          <p className="login-privacy-note">
            Провайдер подтверждает личность, а данные тренировок остаются в Your Fitness Coach.
          </p>
        </section>
      </main>
    </PublicShell>
  );
}
