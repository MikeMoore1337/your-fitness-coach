import { useState } from 'react';
import { AppShell } from '../../app/AppShell';
import { useAuth } from '../../app/AuthProvider';
import { api, getAccessToken } from '../../shared/api/client';
import { Button, Surface } from '../../shared/ui/common';
import '../../styles/react.css';
import '../../styles/design-v2.css';

export const HERMES_OWNER_ORIGIN = 'https://hermes.mikemoore.top';

export function readHermesPairingNonce(hash: string): string | null {
  const match = /^#nonce=([0-9a-f]{64})$/.exec(hash);
  return match?.[1] ?? null;
}

export function canSendRootConsent(
  isRoot: boolean,
  hash: string,
  hasOpener: boolean,
  origin: string,
): boolean {
  return isRoot && readHermesPairingNonce(hash) !== null && hasOpener &&
    origin === 'https://app.your-fitness-coach.ru';
}

/**
 * Explicit, owner-triggered, browser-only consent. The YFC backend checks Root
 * through an authenticated draft read before any short-lived access token is
 * sent to the fixed Hermes origin. Neither popup nor Hermes stores the token.
 */
export default function HermesRootConsentPage() {
  const { user } = useAuth();
  const [phase, setPhase] = useState<'ready' | 'sending' | 'complete' | 'error'>('ready');
  const nonce = readHermesPairingNonce(window.location.hash);
  const valid = canSendRootConsent(
    user?.is_root === true,
    window.location.hash,
    window.opener !== null,
    window.location.origin,
  );
  const confirm = async () => {
    if (!valid || phase !== 'ready') return;
    setPhase('sending');
    try {
      // This is not an ownership hint: YFC verifies Telegram Root server-side.
      await api<unknown>('/api/v1/admin/articles/drafts?limit=1&offset=0');
      const accessToken = getAccessToken();
      if (!accessToken || accessToken.length < 20) throw new Error('missing YFC access token');
      // Omit all publication rights: Hermes needs an independently verified
      // ephemeral bearer and a *separate* explicit release click per revision.
      window.opener.postMessage(
        { type: 'yfc-root-editorial-consent-v1', nonce, token: accessToken },
        HERMES_OWNER_ORIGIN,
      );
      setPhase('complete');
    } catch {
      setPhase('error');
    }
  };

  return (
    <AppShell>
      <main className="container" style={{ maxWidth: 580, margin: '40px auto', padding: 16 }}>
        <Surface style={{ padding: 28 }} aria-labelledby="yfc-hermes-consent-title">
          <span className="eyebrow">YFC ROOT · HERMES CONTROL CENTER</span>
          <h1 id="yfc-hermes-consent-title">Подключение редакции Hermes</h1>
          <p>
            Для просмотра и ручной публикации статей в Hermes будет передан
            краткоживущий токен текущей Root-сессии YFC. Он не сохраняется в
            Hermes, а каждая публикация требует отдельного подтверждения.
          </p>
          <p>
            Разрешённый получатель: <strong>hermes.mikemoore.top</strong>
          </p>
          {!valid ? (
            <p role="alert">
              Соединение недоступно: требуется действующий YFC Root-доступ и
              окно, открытое из Hermes Control Center. Передача запрещена.
            </p>
          ) : phase === 'complete' ? (
            <p role="status">Подтверждение передано. Вернитесь в Hermes Control Center.</p>
          ) : (
            <>
              {phase === 'error' && (
                <p role="alert">
                  Не удалось подтвердить Root-доступ. Обновите авторизацию YFC,
                  затем откройте подключение из Hermes заново.
                </p>
              )}
              <Button
                type="button"
                disabled={phase !== 'ready'}
                onClick={() => void confirm()}
              >
                {phase === 'sending' ? 'Проверяем Root-доступ…' : 'Разрешить подключение Hermes'}
              </Button>
            </>
          )}
        </Surface>
      </main>
    </AppShell>
  );
}
