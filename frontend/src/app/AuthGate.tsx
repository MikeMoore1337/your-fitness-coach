import { useState } from 'react';
import { useAuth } from './AuthProvider';
import { ErrorState, LoadingState } from '../shared/ui/common';
import { loginPathForNext } from '../shared/auth/redirects';
import { Redirect } from '../shared/navigation/router';
import { isTelegramLaunch } from '../shared/telegram/launch';
import { telegramMiniAppUrl } from '../shared/telegram/publicLinks';

export { telegramMiniAppUrl } from '../shared/telegram/publicLinks';

function TelegramAuthRecovery() {
  const { config, error, telegramLogin } = useAuth();
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const telegramAppUrl = config?.telegram_bot_username
    ? telegramMiniAppUrl(config.telegram_bot_username)
    : null;
  const canRetry = Boolean(window.Telegram?.WebApp?.initData?.trim());

  const retry = async () => {
    setBusy(true);
    setLocalError(null);
    try {
      await telegramLogin();
    } catch {
      setLocalError('Данные Telegram недействительны или истекли. Откройте Mini App заново.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="container auth-page tma-auth-recovery">
      <section className="card auth-panel" aria-labelledby="tma-auth-title">
        <div className="stack">
          <p className="muted">Telegram Mini App</p>
          <h1 id="tma-auth-title">Не удалось подтвердить вход</h1>
          <p>
            Вернитесь в Telegram и откройте приложение заново, чтобы получить свежие данные входа.
          </p>
          {(localError || error) && (
            <ErrorState message={localError || 'Не удалось войти через Telegram.'} />
          )}
          <div className="toolbar wrap">
            {canRetry && (
              <button type="button" disabled={busy} onClick={() => void retry()}>
                {busy ? 'Проверяем…' : 'Повторить вход'}
              </button>
            )}
            {telegramAppUrl && (
              <a
                className="button-link secondary"
                href={telegramAppUrl}
                target="_blank"
                rel="noreferrer"
              >
                Открыть заново в Telegram
              </a>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading)
    return (
      <main className="container">
        <LoadingState label="Проверяем авторизацию…" />
      </main>
    );
  if (user) return <>{children}</>;
  if (isTelegramLaunch(window.location)) return <TelegramAuthRecovery />;

  const requestedPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return <Redirect to={loginPathForNext(requestedPath)} />;
}
