import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';

const PROTOCOL = 'yfc-owner-editorial-bridge-v1';
const GRANT_TTL_MS = 10 * 60_000;
const CONFIRM_TTL_MS = 120_000;
const HERMES_ORIGIN = 'https://hermes.mikemoore.top';
const HEX32 = /^[0-9a-f]{32}$/;
const HEX64 = /^[0-9a-f]{64}$/;
const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

type EditorialMessage = {
  protocol: string;
  kind: string;
  nonce?: string;
  request_id?: string;
  action?: string;
  payload?: unknown;
};
type PublishRequest = {
  requestId: string;
  articleId: string;
  contentHash: string;
  version: number;
  title: string;
};
type ArticleDetail = {
  title: string;
  article_id: string;
  content_hash: string;
  content_version: number;
  review_blockers: string[];
  claim_source_matrix: Array<{ review_status?: string; support_level?: string }>;
};

export default function HermesEditorialBridgePage() {
  const { user } = useAuth();
  const [granted, setGranted] = useState(false);
  const [connected, setConnected] = useState(false);
  const [pending, setPending] = useState<PublishRequest | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const nonceRef = useRef<string | null>(null);
  const grantedRef = useRef(false);
  const pendingRef = useRef<PublishRequest | null>(null);
  const busyRef = useRef(false);
  const grantExpiresRef = useRef(0);
  const publishDeadlineRef = useRef(0);

  const send = useCallback((message: Record<string, unknown>) => {
    if (!window.opener || window.opener.closed) return;
    window.opener.postMessage({ protocol: PROTOCOL, ...message }, HERMES_ORIGIN);
  }, []);

  const respond = useCallback((requestId: string, value: unknown, ok = true) => {
    send({ kind: 'response', nonce: nonceRef.current, request_id: requestId, ok,
      ...(ok ? { data: value } : { error: 'Недоступно' }) });
  }, [send]);

  useEffect(() => {
    if (!user?.is_root || !window.opener || window.opener.closed) return;
    send({ kind: 'ready' });
    const onMessage = (event: MessageEvent<EditorialMessage>) => {
      if (event.origin !== HERMES_ORIGIN || event.source !== window.opener) return;
      const m = event.data;
      if (!isRecord(m) || m.protocol !== PROTOCOL || typeof m.kind !== 'string') return;
      if (m.kind === 'hello' && typeof m.nonce === 'string' && HEX64.test(m.nonce)) {
        if (nonceRef.current && nonceRef.current !== m.nonce) return;
        nonceRef.current = m.nonce;
        setConnected(true);
        if (grantedRef.current) send({ kind: 'granted', nonce: m.nonce });
        return;
      }
      if (m.nonce !== nonceRef.current || !grantedRef.current) return;
      if (Date.now() > grantExpiresRef.current) {
        grantedRef.current = false;
        send({ kind: 'revoked', nonce: nonceRef.current });
        setGranted(false);
        setConnected(false);
        setPending(null);
        pendingRef.current = null;
        nonceRef.current = null;
        return;
      }
      if (m.kind === 'disconnect') {
        grantedRef.current = false;
        nonceRef.current = null;
        setGranted(false);
        setConnected(false);
        setPending(null);
        pendingRef.current = null;
        return;
      }
      if (m.kind !== 'request' || typeof m.request_id !== 'string' ||
          !HEX32.test(m.request_id) || !isRecord(m.payload)) return;
      const id = m.request_id;
      const body = m.payload;
      if (m.action === 'list') {
        if (Object.keys(body).length !== 0) { respond(id, null, false); return; }
        void api('/api/v1/admin/articles/drafts?limit=25&offset=0', {
          timeoutMs: 10000, retryAuth: false
        }).then(value => respond(id, value)).catch(() => respond(id, null, false));
      } else if (m.action === 'detail') {
        if (Object.keys(body).length !== 1 ||
            typeof body.article_id !== 'string' || !HEX32.test(body.article_id)) {
          respond(id, null, false); return;
        }
        void api('/api/v1/admin/articles/drafts/' + body.article_id, {
          timeoutMs: 10000, retryAuth: false
        }).then(value => respond(id, value)).catch(() => respond(id, null, false));
      } else if (m.action === 'publish') {
        if (busyRef.current || pendingRef.current ||
            Object.keys(body).length !== 3 ||
            typeof body.article_id !== 'string' || !HEX32.test(body.article_id) ||
            typeof body.content_hash !== 'string' || !HEX64.test(body.content_hash) ||
            typeof body.content_version !== 'number' ||
            !Number.isSafeInteger(body.content_version) || body.content_version < 1) {
          respond(id, null, false); return;
        }
        // Re-read the exact revision on YFC before displaying a second, local
        // confirmation. Hermes cannot trigger POST by sending a message alone.
        busyRef.current = true;
        void api<ArticleDetail>('/api/v1/admin/articles/drafts/' + body.article_id, {
          timeoutMs: 10000, retryAuth: false
        }).then(article => {
          if (article.article_id !== body.article_id ||
              article.content_hash !== body.content_hash ||
              article.content_version !== body.content_version ||
              !Array.isArray(article.review_blockers) ||
              !Array.isArray(article.claim_source_matrix) ||
              article.claim_source_matrix.some(item =>
                item.review_status === 'blocked' ||
                item.support_level === 'does_not_support')) throw Error('revision_conflict');
          const request = {
            requestId: id, articleId: body.article_id as string,
            contentHash: body.content_hash as string,
            version: body.content_version as number,
            title: article.title
          };
          pendingRef.current = request;
          publishDeadlineRef.current = Date.now() + CONFIRM_TTL_MS;
          setPending(request);
          window.setTimeout(() => {
            if (pendingRef.current?.requestId !== id) return;
            pendingRef.current = null;
            setPending(null);
            respond(id, null, false);
          }, CONFIRM_TTL_MS);
        }).catch(() => respond(id, null, false))
          .finally(() => { busyRef.current = false; });
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [user?.is_root, send, respond]);

  const grant = () => {
    if (!user?.is_root || !nonceRef.current) return;
    grantedRef.current = true;
    grantExpiresRef.current = Date.now() + GRANT_TTL_MS;
    setGranted(true);
    send({ kind: 'granted', nonce: nonceRef.current });
    const deadline = grantExpiresRef.current;
    window.setTimeout(() => {
      if (!grantedRef.current || grantExpiresRef.current !== deadline) return;
      grantedRef.current = false;
      send({ kind: 'revoked', nonce: nonceRef.current });
      nonceRef.current = null;
      pendingRef.current = null;
      setConnected(false);
      setGranted(false);
      setPending(null);
    }, GRANT_TTL_MS);
  };

  const publish = async () => {
    const current = pendingRef.current;
    if (!current || !user?.is_root || !grantedRef.current || working) return;
    if (Date.now() > publishDeadlineRef.current ||
        Date.now() > grantExpiresRef.current) {
      pendingRef.current = null; setPending(null);
      respond(current.requestId, null, false);
      setError('Время подтверждения истекло. Запросите новое подтверждение.');
      return;
    }
    setWorking(true); setError('');
    // This is a second explicit Root-owned click IN YFC, not a Hermes
    // background call or a bearer delegated to another origin.
    try {
      const result = await api('/api/v1/admin/articles/drafts/publish', {
        method: 'POST', retryAuth: false, timeoutMs: 15000,
        body: {
          article_id: current.articleId,
          expected_content_hash: current.contentHash,
          expected_content_version: current.version,
          acknowledge_unverified_evidence: true,
          confirm_exact_revision: true
        }
      });
      respond(current.requestId, result);
      pendingRef.current = null;
      setPending(null);
    } catch {
      // Unknown network outcomes must NOT be replayed automatically.
      respond(current.requestId, null, false);
      pendingRef.current = null; setPending(null);
      setError('Не удалось подтвердить результат. Проверьте состояние статьи в YFC.');
    } finally { setWorking(false); }
  };

  if (!user?.is_root) return <main className="container">
    <section className="card"><h1>Доступ запрещён</h1>
      <p>Необходима действующая сессия владельца YFC с подтверждённым аккаунтом Telegram.</p>
    </section>
  </main>;

  return <main className="container" style={{ maxWidth: 660, paddingBlock: 32 }}>
    <section className="card stack" aria-label="Подтверждение редакции YFC">
      <h1>Подтверждение доступа к статьям YFC</h1>
      <p>Ваша сессия владельца остаётся в YFC. Другая система не получает токены, пароли
        или постоянные права публикации.</p>
      {!window.opener && <p role="alert">Откройте эту страницу кнопкой в панели управления.</p>}
      {window.opener && !connected && <p>Ожидаем защищённое соединение с панелью управления.</p>}
      {connected && !granted && <>
        <p>Разрешить вкладке, открывшей это окно, читать черновики и отправлять
          запросы на отдельное подтверждение публикации?</p>
        <button type="button" onClick={grant}>Разрешить просмотр черновиков</button>
      </>}
      {granted && <p role="status">Доступ к просмотру подтверждён.
        Для публикации каждого материала потребуется отдельное подтверждение здесь, в YFC.</p>}
      {pending && <section className="card stack" aria-labelledby="yfc-confirm-publication">
        <h2 id="yfc-confirm-publication">Опубликовать точную редакцию?</h2>
        <strong>{pending.title}</strong>
        <p>Версия {pending.version}</p>
        <code style={{ overflowWrap: 'anywhere' }}>{pending.contentHash}</code>
        <p>Научная аттестация не заявлена. Проверьте полный текст и источники в панели управления.</p>
        <div className="toolbar wrap">
          <button type="button" disabled={working} onClick={() => void publish()}>
            {working ? 'Публикуем…' : 'Подтверждаю публикацию в YFC'}
          </button>
          <button type="button" className="secondary" disabled={working} onClick={() => {
            respond(pending.requestId, null, false);
            pendingRef.current = null; setPending(null);
          }}>Отмена</button>
        </div>
      </section>}
      {error && <p role="alert">{error}</p>}
      <p className="muted">Закрытие окна прекращает доступ. Автоматическая публикация отключена.</p>
    </section>
  </main>;
}
