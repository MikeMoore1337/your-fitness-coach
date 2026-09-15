import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { api } from '../../shared/api/client';
import type {
  AiCoachConsentResponse,
  AiCoachConversation,
  AiCoachConversationMessage,
  AiCoachConversationSendResponse,
  AiCoachConversationSummary,
  AiCoachMemoryItemResponse,
  AiCoachMemoryResponse,
  AiCoachQuotaSnapshot,
  AiCoachResponse,
  AiCoachStatus,
} from '../../shared/api/types';
import {
  productEventSurface,
  trackProductEvent,
  type AiCoachEntryPoint,
  type AiCoachHelpfulness,
} from '../../shared/analytics/productEvents';
import { AppLink } from '../../shared/navigation/router';
import { Badge, Button, Card, LoadingState } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import './ai-coach.css';

export const AI_COACH_UI_VERSION = 'ai-coach-ui-v2';

export const aiCoachStatusQueryKey = ['ai-coach', 'status'] as const;
export const aiCoachConsentQueryKey = ['ai-coach', 'consent'] as const;
export const aiCoachMemoryQueryKey = ['ai-coach', 'memory'] as const;
export const aiCoachConversationsQueryKey = ['ai-coach', 'conversations'] as const;
export const aiCoachQuotaQueryKey = ['ai-coach', 'quota'] as const;

const ACTIVE_CONVERSATION_KEY = 'yfc:ai-coach:active-conversation';
const CHAT_MESSAGE_MAX_LENGTH = 2_000;

const QUICK_PROMPTS = [
  { id: 'today', label: 'Что делать сегодня?', message: 'Что мне делать сегодня?' },
  {
    id: 'period',
    label: 'Итог за 30 дней',
    message: 'Дай краткий итог моего прогресса за 30 дней.',
  },
  { id: 'progress', label: 'Как читать прогресс?', message: 'Как читать прогресс в YFC?' },
  {
    id: 'rest',
    label: 'Отдых между подходами',
    message: 'Сколько отдыхать между подходами и почему?',
  },
  {
    id: 'diary',
    label: 'Как вести дневник?',
    message: 'Как вести дневник питания и тренировок в YFC?',
  },
] as const;

const MEMORY_CATEGORY_LABELS: Record<string, string> = {
  preferred_explanation_style: 'Стиль объяснений',
  ai_interaction_preferences: 'Предпочтения общения',
  stable_non_medical_preferences: 'Стабильные немедицинские предпочтения',
  explicit_ai_context: 'Явный контекст для AI Coach',
};

const CHAT_FAILURE_COPY: Record<string, string> = {
  safety_rejection: 'Я не могу помочь с этим запросом в таком виде.',
  provider_failure: 'AI Coach сейчас не ответил. Попробуйте ещё раз.',
  repair_failed: 'Не удалось сформировать ответ. Повторить.',
  presentation_validation_failed: 'Не удалось сформировать ответ. Повторить.',
  internal_error: 'Не удалось сформировать ответ. Повторить.',
  structured_validation: 'Не удалось безопасно проверить ответ. Попробуйте ещё раз.',
  timeout: 'Ответ занял слишком много времени. Попробуйте ещё раз.',
  context_failure: 'Не удалось получить материалы для ответа. Попробуйте ещё раз позже.',
  generation_failure: 'Не удалось получить проверенный ответ. Попробуйте ещё раз.',
  rate_limit: 'Лимит AI Coach исчерпан. Попробуйте позже.',
  rate_limited: 'Лимит AI Coach исчерпан. Попробуйте позже.',
};

export function useAiCoachStatus(enabled = true) {
  return useQuery<AiCoachStatus>({
    queryKey: aiCoachStatusQueryKey,
    queryFn: () => api<AiCoachStatus>('/api/v1/ai-coach/status'),
    enabled,
    staleTime: 30_000,
    retry: false,
  });
}

export function safeCoachUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password || url.hash) return null;
    return url.toString();
  } catch {
    return null;
  }
}

function safeInlineNodes(text: string, allowedUrls: ReadonlySet<string>): ReactNode[] {
  const nodes: ReactNode[] = [];
  const linkPattern = /\[([^\]]{1,120})\]\((https:\/\/[^)\s]+)\)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = linkPattern.exec(text)) !== null) {
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));
    const label = match[1] ?? '';
    const url = safeCoachUrl(match[2] ?? '');
    nodes.push(
      url && allowedUrls.has(url) ? (
        <a href={url} key={`link-${index}`} rel="noreferrer noopener" target="_blank">
          {label}
        </a>
      ) : (
        label
      ),
    );
    cursor = match.index + match[0].length;
    index += 1;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

export function SafeCoachAnswer({
  answer,
  citations,
}: {
  answer: string;
  citations: AiCoachResponse['citations'];
}) {
  const allowedUrls = useMemo(
    () =>
      new Set(
        citations
          .map((citation) => safeCoachUrl(citation.url))
          .filter((url): url is string => Boolean(url)),
      ),
    [citations],
  );
  const lines = answer.replace(/\r\n?/g, '\n').slice(0, 1_600).split('\n');
  const blocks: ReactNode[] = [];
  let listItems: ReactNode[] = [];
  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(<ul key={`list-${blocks.length}`}>{listItems}</ul>);
    listItems = [];
  };
  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }
    const listMatch = /^[-*]\s+(.+)$/.exec(trimmed);
    if (listMatch) {
      listItems.push(
        <li key={`item-${index}`}>{safeInlineNodes(listMatch[1] ?? '', allowedUrls)}</li>,
      );
      return;
    }
    flushList();
    blocks.push(<p key={`paragraph-${index}`}>{safeInlineNodes(trimmed, allowedUrls)}</p>);
  });
  flushList();
  return <div className="ai-coach-answer__body">{blocks}</div>;
}

function readActiveConversationId(): number | null {
  try {
    const raw = window.sessionStorage.getItem(ACTIVE_CONVERSATION_KEY);
    const value = raw ? Number(raw) : NaN;
    return Number.isSafeInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

function storeActiveConversationId(value: number | null): void {
  try {
    if (value === null) window.sessionStorage.removeItem(ACTIVE_CONVERSATION_KEY);
    else window.sessionStorage.setItem(ACTIVE_CONVERSATION_KEY, String(value));
  } catch {
    // A restrictive WebView should still keep the current in-memory conversation usable.
  }
}

function failureCopy(response: AiCoachConversationSendResponse): string {
  if (response.rate_limit_scope === 'provider') {
    return 'AI Coach временно достиг лимита сервиса.';
  }
  if (response.rate_limit_scope === 'service') {
    return 'AI Coach временно перегружен. Попробуйте позже.';
  }
  if (response.failure_category && CHAT_FAILURE_COPY[response.failure_category]) {
    return CHAT_FAILURE_COPY[response.failure_category] ?? 'Не удалось получить проверенный ответ.';
  }
  return response.limitations[0] ?? 'Не удалось получить проверенный ответ. Попробуйте ещё раз.';
}

function messageFailureCopy(message: AiCoachConversationMessage): string {
  if (message.rate_limit_scope === 'provider') {
    return 'AI Coach временно достиг лимита сервиса.';
  }
  if (message.rate_limit_scope === 'service') {
    return 'AI Coach временно перегружен. Попробуйте позже.';
  }
  return message.limitations[0] ?? 'Не удалось получить проверенный ответ. Попробуйте ещё раз.';
}

function formatQuotaCountdown(resetAt: string, now = Date.now()): string {
  const resetTime = Date.parse(resetAt);
  if (!Number.isFinite(resetTime)) return 'скоро';
  const minutes = Math.max(0, Math.ceil((resetTime - now) / 60_000));
  if (minutes < 1) return 'меньше минуты';
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours < 24) return remainingMinutes ? `${hours} ч ${remainingMinutes} мин` : `${hours} ч`;
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours ? `${days} д ${remainingHours} ч` : `${days} д`;
}

function quotaRemainingCopy(remaining: number, limit: number): string {
  if (remaining === 0) return 'Лимит AI Coach исчерпан';
  if (remaining === 1) return `Остался 1 запрос из ${limit}`;
  if (remaining <= 2) return `Осталось ${remaining} запроса из ${limit}`;
  return `Осталось ${remaining} из ${limit}`;
}

function QuotaIndicator({ quota, now }: { quota: AiCoachQuotaSnapshot | undefined; now: number }) {
  if (!quota) {
    return <span className="ai-coach-chat__quota">Лимит обновляется…</span>;
  }
  const state = quota.remaining === 0 ? 'empty' : quota.remaining <= 2 ? 'low' : 'normal';
  return (
    <span
      className={`ai-coach-chat__quota ai-coach-chat__quota--${state}`}
      data-testid="ai-coach-quota"
      data-quota-limit={quota.limit}
      data-quota-remaining={quota.remaining}
    >
      <span>{quotaRemainingCopy(quota.remaining, quota.limit)}</span>
      <span>
        {quota.remaining === 0 ? 'Новые запросы будут доступны' : 'Сброс через'}{' '}
        {formatQuotaCountdown(quota.reset_at, now)}
      </span>
    </span>
  );
}

function newRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

class AiCoachSendError extends Error {
  readonly conversationId: number;

  constructor(conversationId: number, cause: unknown) {
    super(cause instanceof Error ? cause.message : 'AI Coach request failed');
    this.name = 'AiCoachSendError';
    this.conversationId = conversationId;
  }
}

function networkFailureCopy(reason: unknown): string {
  if (
    reason &&
    typeof reason === 'object' &&
    'status' in reason &&
    Number((reason as { status?: unknown }).status) === 0 &&
    'message' in reason &&
    typeof (reason as { message?: unknown }).message === 'string'
  ) {
    return (reason as { message: string }).message;
  }
  if (reason instanceof DOMException && reason.name === 'AbortError') {
    return 'Ответ занял слишком много времени. Попробуйте ещё раз.';
  }
  return 'Не удалось отправить вопрос. Проверьте соединение и попробуйте снова.';
}

function temporaryRateLimitState(
  response: AiCoachConversationSendResponse,
): { scope: 'provider' | 'service'; retryAt: number } | null {
  const scope = response.rate_limit_scope;
  if (scope !== 'provider' && scope !== 'service') return null;
  const retryAfter = response.rate_limit_retry_after_seconds;
  return typeof retryAfter === 'number' && retryAfter > 0
    ? { scope, retryAt: Date.now() + retryAfter * 1_000 }
    : null;
}

function MessageSources({ message }: { message: AiCoachConversationMessage }) {
  const citations = message.citations.filter((citation) => safeCoachUrl(citation.url));
  if (!citations.length) return null;
  return (
    <details className="ai-coach-message__sources">
      <summary>Материалы ответа</summary>
      <ul>
        {citations.map((citation) => {
          const url = safeCoachUrl(citation.url);
          if (!url) return null;
          return (
            <li key={url}>
              <a href={url} rel="noreferrer noopener" target="_blank">
                {citation.title}
              </a>
              <small>{citation.publisher}</small>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

function ChatMessage({
  feedback,
  message,
  onFeedback,
  onRetry,
  retryBlocked,
  retrying,
}: {
  feedback: AiCoachHelpfulness | null;
  message: AiCoachConversationMessage;
  onFeedback: (messageId: number, value: AiCoachHelpfulness) => void;
  onRetry: (messageId: number) => void;
  retryBlocked: boolean;
  retrying: boolean;
}) {
  const isAssistant = message.role === 'assistant';
  return (
    <article
      className={`ai-coach-message ai-coach-message--${message.role}`}
      data-message-id={message.id}
      data-testid={`ai-coach-message-${message.role}`}
    >
      <div className="ai-coach-message__author">{isAssistant ? 'AI Coach' : 'Вы'}</div>
      {isAssistant ? (
        <SafeCoachAnswer answer={message.content} citations={message.citations} />
      ) : (
        <p className="ai-coach-message__text">{message.content}</p>
      )}
      {message.status === 'failed' && message.limitations.length > 0 && (
        <>
          <p className="ai-coach-message__failure" role="alert">
            {messageFailureCopy(message)}
          </p>
          {!isAssistant && (
            <button
              className="ai-coach-message__retry"
              type="button"
              disabled={retrying || retryBlocked}
              onClick={() => onRetry(message.id)}
            >
              {retrying ? 'Повторяем…' : 'Повторить'}
            </button>
          )}
        </>
      )}
      {isAssistant && <MessageSources message={message} />}
      {isAssistant && message.outcome === 'answer' && (
        <div className="ai-coach-message__feedback" aria-label="Оценка ответа">
          <span>Полезно?</span>
          <button
            aria-pressed={feedback === 'helpful'}
            className={feedback === 'helpful' ? 'is-selected' : ''}
            type="button"
            onClick={() => onFeedback(message.id, 'helpful')}
          >
            👍
          </button>
          <button
            aria-pressed={feedback === 'not_helpful'}
            className={feedback === 'not_helpful' ? 'is-selected' : ''}
            type="button"
            onClick={() => onFeedback(message.id, 'not_helpful')}
          >
            👎
          </button>
        </div>
      )}
    </article>
  );
}

function MemoryPanel() {
  const { confirm, toast } = useFeedback();
  const queryClient = useQueryClient();
  const [category, setCategory] = useState('preferred_explanation_style');
  const [value, setValue] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [editing, setEditing] = useState<AiCoachMemoryItemResponse | null>(null);
  const memory = useQuery<AiCoachMemoryResponse>({
    queryKey: aiCoachMemoryQueryKey,
    queryFn: () => api<AiCoachMemoryResponse>('/api/v1/ai-coach/memory'),
    staleTime: 30_000,
    retry: false,
  });
  const invalidateMemory = () => queryClient.invalidateQueries({ queryKey: aiCoachMemoryQueryKey });
  const consentMutation = useMutation({
    mutationFn: (status: 'enabled' | 'paused' | 'revoked') =>
      api<AiCoachMemoryResponse>('/api/v1/ai-coach/memory/consent', {
        method: 'PUT',
        body: { status },
      }),
    onSuccess: (next) => {
      queryClient.setQueryData(aiCoachMemoryQueryKey, next);
      toast(
        next.status === 'enabled'
          ? 'Память AI Coach включена.'
          : next.status === 'paused'
            ? 'Память AI Coach поставлена на паузу.'
            : 'Память AI Coach отозвана.',
      );
    },
    onError: () => toast('Не удалось изменить настройку памяти AI Coach.', 'error'),
  });
  const createMutation = useMutation({
    mutationFn: () =>
      api<AiCoachMemoryItemResponse>('/api/v1/ai-coach/memory', {
        method: 'POST',
        body: { category, value: value.trim(), confirmation: true },
      }),
    onSuccess: () => {
      setValue('');
      setConfirmed(false);
      invalidateMemory();
      toast('Предпочтение сохранено.');
    },
    onError: () => toast('Это значение нельзя сохранить в памяти AI Coach.', 'error'),
  });
  const updateMutation = useMutation({
    mutationFn: () =>
      api<AiCoachMemoryItemResponse>(`/api/v1/ai-coach/memory/${editing?.id ?? 0}`, {
        method: 'PATCH',
        body: { value: value.trim(), confirmation: true },
      }),
    onSuccess: () => {
      setValue('');
      setConfirmed(false);
      setEditing(null);
      invalidateMemory();
      toast('Предпочтение обновлено.');
    },
    onError: () => toast('Не удалось обновить предпочтение.', 'error'),
  });
  const deleteMutation = useMutation({
    mutationFn: (memoryId: number) =>
      api<{ deleted_count: number }>(`/api/v1/ai-coach/memory/${memoryId}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      invalidateMemory();
      toast('Предпочтение удалено.');
    },
    onError: () => toast('Не удалось удалить предпочтение.', 'error'),
  });
  const clearMutation = useMutation({
    mutationFn: () =>
      api<{ deleted_count: number }>('/api/v1/ai-coach/memory', { method: 'DELETE' }),
    onSuccess: () => {
      setEditing(null);
      setValue('');
      setConfirmed(false);
      invalidateMemory();
      toast('Память AI Coach очищена.');
    },
    onError: () => toast('Не удалось очистить память AI Coach.', 'error'),
  });

  if (memory.isLoading) return <LoadingState label="Загружаем настройки памяти…" />;
  if (memory.isError || !memory.data) {
    return (
      <section className="ai-coach-memory ai-coach-memory--error" role="alert">
        <strong>Настройки памяти недоступны</strong>
        <p>Попробуйте обновить экран. История диалога от этого не изменится.</p>
      </section>
    );
  }

  const current = memory.data;
  const items = current.items ?? [];
  const memoryEnabled = current.status === 'enabled';
  const pending =
    consentMutation.isPending ||
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending ||
    clearMutation.isPending;
  const submitMemory = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!memoryEnabled || !value.trim() || !confirmed || pending) return;
    if (editing) updateMutation.mutate();
    else createMutation.mutate();
  };
  const startEditing = (item: AiCoachMemoryItemResponse) => {
    setEditing(item);
    setCategory(item.category);
    setValue(item.value);
    setConfirmed(false);
  };
  const cancelEditing = () => {
    setEditing(null);
    setValue('');
    setConfirmed(false);
  };
  const removeOne = async (item: AiCoachMemoryItemResponse) => {
    if (
      await confirm({
        title: 'Удалить это предпочтение?',
        message: 'Оно сразу перестанет использоваться и будет удалено из памяти.',
        confirmText: 'Удалить',
      })
    ) {
      deleteMutation.mutate(item.id);
    }
  };
  const clearAll = async () => {
    if (
      await confirm({
        title: 'Очистить память AI Coach?',
        message: 'Все сохранённые предпочтения будут удалены без возможности восстановления.',
        confirmText: 'Очистить',
      })
    ) {
      clearMutation.mutate();
    }
  };

  return (
    <section className="ai-coach-memory" data-testid="ai-coach-memory">
      <div className="ai-coach-memory__header">
        <div>
          <div className="ai-coach-memory__title">
            <Badge tone={current.status === 'enabled' ? 'success' : 'warning'}>
              {current.status === 'enabled'
                ? 'Память включена'
                : current.status === 'paused'
                  ? 'Память на паузе'
                  : 'Память выключена'}
            </Badge>
            <strong>Отдельная память AI Coach</strong>
          </div>
          <p>{current.purpose}</p>
          <small>{current.retention_notice}</small>
        </div>
        <div className="ai-coach-memory__actions">
          {current.status === 'enabled' && (
            <Button
              disabled={pending}
              type="button"
              variant="secondary"
              onClick={() => consentMutation.mutate('paused')}
            >
              Пауза
            </Button>
          )}
          {current.status === 'paused' && (
            <Button
              disabled={pending}
              type="button"
              onClick={() => consentMutation.mutate('enabled')}
            >
              Возобновить
            </Button>
          )}
          {current.status === 'revoked' && (
            <Button
              disabled={pending}
              type="button"
              onClick={() => consentMutation.mutate('enabled')}
            >
              Включить
            </Button>
          )}
          {current.status !== 'revoked' && (
            <Button
              disabled={pending}
              type="button"
              variant="secondary"
              onClick={() => consentMutation.mutate('revoked')}
            >
              Отозвать
            </Button>
          )}
        </div>
      </div>

      <div className="ai-coach-memory__notice">
        <strong>Что можно сохранять</strong>
        <span>
          Только немедицинские предпочтения и явный контекст. Канонические данные приложения и
          история диалога не превращаются в память автоматически.
        </span>
      </div>
      <div className="ai-coach-memory__categories">
        {current.categories.map((item) => (
          <span key={item}>
            {current.category_labels[item] ?? MEMORY_CATEGORY_LABELS[item] ?? item}
          </span>
        ))}
      </div>

      <form className="ai-coach-memory__form" onSubmit={submitMemory}>
        <div className="ai-coach-memory__form-heading">
          <strong>{editing ? 'Изменить предпочтение' : 'Добавить предпочтение'}</strong>
          <small>
            {memoryEnabled
              ? 'Не более 240 символов.'
              : 'Включите память, чтобы добавлять или изменять записи.'}
          </small>
        </div>
        {!editing && (
          <label>
            <span>Категория</span>
            <select
              disabled={!memoryEnabled || pending}
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              {current.categories.map((item) => (
                <option key={item} value={item}>
                  {current.category_labels[item] ?? MEMORY_CATEGORY_LABELS[item] ?? item}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          <span>Текст предпочтения</span>
          <input
            disabled={!memoryEnabled || pending}
            maxLength={240}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Например: объясняй коротко и по пунктам"
          />
        </label>
        <label className="ai-coach-memory__confirmation">
          <input
            checked={confirmed}
            disabled={!memoryEnabled || pending}
            type="checkbox"
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          <span>Подтверждаю, что это моё немедицинское предпочтение или контекст.</span>
        </label>
        <div className="ai-coach-memory__form-actions">
          <Button disabled={!memoryEnabled || !value.trim() || !confirmed || pending} type="submit">
            {editing ? 'Сохранить изменение' : 'Сохранить в память'}
          </Button>
          {editing && (
            <Button disabled={pending} type="button" variant="secondary" onClick={cancelEditing}>
              Отмена
            </Button>
          )}
        </div>
      </form>

      {items.length > 0 ? (
        <div className="ai-coach-memory__list" aria-label="Сохранённые элементы памяти">
          {items.map((item) => (
            <article className="ai-coach-memory__item" key={item.id}>
              <div>
                <Badge tone="neutral">{item.category_label}</Badge>
                <p>{item.value}</p>
                <small>Добавлено вами; канонические данные остаются источником истины.</small>
              </div>
              <div className="ai-coach-memory__item-actions">
                <button type="button" onClick={() => startEditing(item)}>
                  Изменить
                </button>
                <button type="button" onClick={() => removeOne(item)}>
                  Удалить
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="ai-coach-memory__empty">Пока ничего не сохранено.</p>
      )}
      {items.length > 0 && (
        <Button disabled={pending} type="button" variant="danger" onClick={clearAll}>
          Очистить всю память
        </Button>
      )}
    </section>
  );
}

function AiCoachChat({ status }: { status: AiCoachStatus }) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(() =>
    readActiveConversationId(),
  );
  const [isNewConversation, setIsNewConversation] = useState(false);
  const [draft, setDraft] = useState('');
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [retryingMessageId, setRetryingMessageId] = useState<number | null>(null);
  const [sendRetry, setSendRetry] = useState<{
    conversationId: number;
    requestId: string;
  } | null>(null);
  const [retryRequest, setRetryRequest] = useState<{
    messageId: number;
    requestId: string;
  } | null>(null);
  const [temporaryRateLimit, setTemporaryRateLimit] = useState<{
    scope: 'provider' | 'service';
    retryAt: number;
  } | null>(null);
  const [clockTick, setClockTick] = useState(() => Date.now());
  const refreshedQuotaBoundary = useRef<number | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [feedbackByMessage, setFeedbackByMessage] = useState<Record<number, AiCoachHelpfulness>>(
    {},
  );

  const conversations = useQuery<{ items: AiCoachConversationSummary[] }>({
    queryKey: aiCoachConversationsQueryKey,
    queryFn: () => api<{ items: AiCoachConversationSummary[] }>('/api/v1/ai-coach/conversations'),
    staleTime: 15_000,
    retry: false,
  });
  const quota = useQuery<AiCoachQuotaSnapshot>({
    queryKey: aiCoachQuotaQueryKey,
    queryFn: () => api<AiCoachQuotaSnapshot>('/api/v1/ai-coach/quota'),
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const { refetch: refetchQuota } = quota;
  useEffect(() => {
    const refreshQuota = () => {
      if (document.visibilityState !== 'hidden') void refetchQuota();
    };
    window.addEventListener('focus', refreshQuota);
    document.addEventListener('visibilitychange', refreshQuota);
    return () => {
      window.removeEventListener('focus', refreshQuota);
      document.removeEventListener('visibilitychange', refreshQuota);
    };
  }, [refetchQuota]);
  useEffect(() => {
    const resetAt = quota.data ? Date.parse(quota.data.reset_at) : NaN;
    const serviceRetryAt = temporaryRateLimit?.retryAt ?? NaN;
    const now = Date.now();
    const quotaBoundary =
      Number.isFinite(resetAt) && refreshedQuotaBoundary.current === resetAt
        ? Number.POSITIVE_INFINITY
        : resetAt;
    const nextBoundary = Math.min(
      Number.isFinite(quotaBoundary) ? quotaBoundary : Number.POSITIVE_INFINITY,
      Number.isFinite(serviceRetryAt) ? serviceRetryAt : Number.POSITIVE_INFINITY,
    );
    if (!Number.isFinite(nextBoundary)) return;
    const refreshDue =
      Number.isFinite(resetAt) && resetAt <= now && refreshedQuotaBoundary.current !== resetAt;
    const delay = refreshDue ? 50 : Math.min(60_000, Math.max(50, nextBoundary - now + 50));
    const timer = window.setTimeout(() => {
      const current = Date.now();
      setClockTick(current);
      if (
        Number.isFinite(resetAt) &&
        resetAt <= current &&
        refreshedQuotaBoundary.current !== resetAt
      ) {
        refreshedQuotaBoundary.current = resetAt;
        void refetchQuota();
      }
      if (Number.isFinite(serviceRetryAt) && serviceRetryAt <= current) {
        setTemporaryRateLimit(null);
      }
    }, delay);
    return () => window.clearTimeout(timer);
  }, [clockTick, quota.data, refetchQuota, temporaryRateLimit]);
  const conversationItems = conversations.data?.items ?? [];
  const currentConversationId = isNewConversation
    ? null
    : activeConversationId !== null &&
        conversationItems.some((item) => item.id === activeConversationId)
      ? activeConversationId
      : (conversationItems[0]?.id ?? null);
  const conversation = useQuery<AiCoachConversation>({
    queryKey: ['ai-coach', 'conversation', currentConversationId],
    queryFn: () =>
      api<AiCoachConversation>(`/api/v1/ai-coach/conversations/${currentConversationId}`),
    enabled: currentConversationId !== null,
    staleTime: 0,
    retry: false,
  });
  const consent = useQuery<AiCoachConsentResponse>({
    queryKey: aiCoachConsentQueryKey,
    queryFn: () => api<AiCoachConsentResponse>('/api/v1/ai-coach/consent'),
    enabled: status.personal_available,
    staleTime: 30_000,
    retry: false,
  });
  const consentMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      api<AiCoachConsentResponse>('/api/v1/ai-coach/consent', {
        method: 'PUT',
        body: { enabled },
      }),
    onSuccess: (next) => {
      queryClient.setQueryData(aiCoachConsentQueryKey, next);
      trackProductEvent({
        name: 'ai_coach_consent_changed',
        surface: productEventSurface(),
        enabled: next.status === 'granted',
      });
    },
    onError: () => toast('Не удалось изменить согласие на персональный режим.', 'error'),
  });
  const sendMutation = useMutation({
    mutationFn: async ({
      conversationId,
      message,
      requestId,
    }: {
      conversationId: number | null;
      message: string;
      requestId: string;
    }) => {
      let conversationIdForError = conversationId;
      try {
        const conversationToUse =
          conversationId === null
            ? await api<AiCoachConversation>('/api/v1/ai-coach/conversations', {
                method: 'POST',
              })
            : { id: conversationId };
        conversationIdForError = conversationToUse.id;
        const response = await api<AiCoachConversationSendResponse>(
          `/api/v1/ai-coach/conversations/${conversationToUse.id}/messages`,
          {
            method: 'POST',
            body: { message },
            headers: { 'X-Request-ID': requestId },
          },
        );
        return { conversationId: conversationToUse.id, response };
      } catch (error) {
        if (conversationIdForError !== null) {
          throw new AiCoachSendError(conversationIdForError, error);
        }
        throw error;
      }
    },
    onMutate: ({ message }) => {
      setPendingMessage(message);
      setDraft('');
      setFailure(null);
      trackProductEvent({
        name: 'ai_coach_request_started',
        surface: productEventSurface(),
        mode: 'generic',
      });
    },
    onSuccess: ({ conversationId, response }, variables) => {
      setPendingMessage(null);
      setSendRetry(null);
      setIsNewConversation(false);
      setActiveConversationId(conversationId);
      storeActiveConversationId(conversationId);
      if (response.quota) queryClient.setQueryData(aiCoachQuotaQueryKey, response.quota);
      setTemporaryRateLimit(temporaryRateLimitState(response));
      queryClient.invalidateQueries({ queryKey: aiCoachConversationsQueryKey });
      queryClient.invalidateQueries({ queryKey: ['ai-coach', 'conversation', conversationId] });
      trackProductEvent({
        name: 'ai_coach_response_received',
        surface: productEventSurface(),
        mode: response.data_class === 'personalized' ? 'personal' : 'generic',
        outcome: response.outcome,
      });
      if (response.answer === null && response.outcome !== 'safety_refusal') {
        setDraft(variables.message);
        setFailure(failureCopy(response));
        return;
      }
      setFailure(null);
    },
    onError: (reason, variables) => {
      setPendingMessage(null);
      setDraft(variables.message);
      const failedConversationId =
        reason instanceof AiCoachSendError ? reason.conversationId : variables.conversationId;
      if (failedConversationId !== null) {
        setSendRetry({ conversationId: failedConversationId, requestId: variables.requestId });
      }
      void queryClient.invalidateQueries({ queryKey: aiCoachQuotaQueryKey });
      const message = networkFailureCopy(reason);
      setFailure(message);
      trackProductEvent({
        name: 'ai_coach_request_failed',
        surface: productEventSurface(),
        mode: 'generic',
        failure:
          reason &&
          typeof reason === 'object' &&
          'status' in reason &&
          Number((reason as { status?: unknown }).status) === 0
            ? 'network'
            : 'unknown',
      });
    },
  });
  const retryMutation = useMutation({
    mutationFn: async ({
      conversationId,
      messageId,
      requestId,
    }: {
      conversationId: number;
      messageId: number;
      message: string;
      requestId: string;
    }) =>
      api<AiCoachConversationSendResponse>(
        `/api/v1/ai-coach/conversations/${conversationId}/messages/${messageId}/retry`,
        { method: 'POST', headers: { 'X-Request-ID': requestId } },
      ),
    onMutate: () => {
      setFailure(null);
    },
    onSuccess: (response, variables) => {
      setRetryingMessageId(null);
      setRetryRequest(null);
      if (response.quota) queryClient.setQueryData(aiCoachQuotaQueryKey, response.quota);
      setTemporaryRateLimit(temporaryRateLimitState(response));
      queryClient.invalidateQueries({ queryKey: aiCoachConversationsQueryKey });
      queryClient.invalidateQueries({
        queryKey: ['ai-coach', 'conversation', variables.conversationId],
      });
      trackProductEvent({
        name: 'ai_coach_response_received',
        surface: productEventSurface(),
        mode: response.data_class === 'personalized' ? 'personal' : 'generic',
        outcome: response.outcome,
      });
      if (response.answer === null && response.outcome !== 'safety_refusal') {
        setDraft(response.user_message.content);
        setFailure(failureCopy(response));
        return;
      }
      setDraft('');
      setFailure(null);
    },
    onError: (_reason, variables) => {
      setRetryingMessageId(null);
      setRetryRequest({ messageId: variables.messageId, requestId: variables.requestId });
      void queryClient.invalidateQueries({ queryKey: aiCoachQuotaQueryKey });
      setDraft(variables.message);
      setFailure('Не удалось повторить ответ. Попробуйте ещё раз.');
    },
  });
  const feedbackMutation = useMutation({
    mutationFn: ({
      conversationId,
      messageId,
      value,
    }: {
      conversationId: number;
      messageId: number;
      value: AiCoachHelpfulness;
    }) =>
      api<void>(`/api/v1/ai-coach/conversations/${conversationId}/messages/${messageId}/feedback`, {
        method: 'POST',
        body: { value },
      }),
    onSuccess: (_data, variables) => {
      setFeedbackByMessage((current) => ({ ...current, [variables.messageId]: variables.value }));
      trackProductEvent({
        name: 'ai_coach_helpfulness_submitted',
        surface: productEventSurface(),
        value: variables.value,
      });
    },
    onError: () => toast('Не удалось сохранить оценку ответа.', 'error'),
  });

  const currentMessages = conversation.data?.messages ?? [];
  const pending = sendMutation.isPending || retryMutation.isPending;
  const serviceRateLimited = temporaryRateLimit !== null && temporaryRateLimit.retryAt > clockTick;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = draft.trim();
    if (!message || pending || quota.data?.can_send === false) return;
    sendMutation.mutate({
      conversationId: sendRetry?.conversationId ?? currentConversationId,
      message,
      requestId: sendRetry?.requestId ?? newRequestId(),
    });
  };
  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };
  const chooseQuickPrompt = (message: string) => {
    setDraft(message);
    setSendRetry(null);
    setFailure(null);
    window.requestAnimationFrame(() => composerRef.current?.focus());
  };
  const retryMessage = (messageId: number) => {
    if (currentConversationId === null || pending) return;
    const message = currentMessages.find(
      (item) => item.id === messageId && item.role === 'user' && item.status === 'failed',
    );
    if (!message) return;
    setRetryingMessageId(messageId);
    retryMutation.mutate({
      conversationId: currentConversationId,
      messageId,
      message: message.content,
      requestId: retryRequest?.messageId === messageId ? retryRequest.requestId : newRequestId(),
    });
  };
  const startNewConversation = () => {
    if (pending) return;
    setIsNewConversation(true);
    setActiveConversationId(null);
    storeActiveConversationId(null);
    setDraft('');
    setSendRetry(null);
    setRetryRequest(null);
    setFailure(null);
  };
  const sendFeedback = (messageId: number, value: AiCoachHelpfulness) => {
    if (currentConversationId === null || feedbackMutation.isPending) return;
    feedbackMutation.mutate({ conversationId: currentConversationId, messageId, value });
  };

  if (conversations.isLoading) return <LoadingState label="Загружаем историю AI Coach…" />;
  if (conversations.isError) {
    return (
      <section className="ai-coach-state ai-coach-state--error" role="alert">
        <strong>История AI Coach недоступна</strong>
        <p>Обновите экран и попробуйте снова. Ваши данные приложения не изменились.</p>
        <Button
          type="button"
          variant="secondary"
          onClick={() => queryClient.invalidateQueries({ queryKey: aiCoachConversationsQueryKey })}
        >
          Повторить
        </Button>
      </section>
    );
  }

  return (
    <div className="ai-coach-chat" data-testid="ai-coach-chat">
      <div className="ai-coach-chat__toolbar">
        <div>
          <span className="eyebrow">Диалог</span>
          <strong>{conversation.data?.title ?? 'Новый разговор'}</strong>
        </div>
        <div className="ai-coach-chat__toolbar-actions">
          {(conversations.data?.items.length ?? 0) > 0 && (
            <label className="ai-coach-chat__history-select">
              <span className="sr-only">Выбрать разговор</span>
              <select
                aria-label="Выбрать разговор"
                disabled={pending}
                value={currentConversationId ?? ''}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  if (!Number.isSafeInteger(next) || next < 1) return;
                  setIsNewConversation(false);
                  setActiveConversationId(next);
                  storeActiveConversationId(next);
                  setSendRetry(null);
                  setRetryRequest(null);
                  setFailure(null);
                }}
              >
                {conversations.data?.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title || 'Новый разговор'}
                  </option>
                ))}
              </select>
            </label>
          )}
          <Button
            disabled={pending}
            type="button"
            variant="secondary"
            onClick={startNewConversation}
          >
            Новый чат
          </Button>
        </div>
      </div>

      <div className="ai-coach-chat__welcome">
        <div>
          <h3>Чем помочь?</h3>
          <p>
            Задайте любой вопрос о тренировках, питании, прогрессе или работе YFC. Если вопрос
            личный, AI Coach попросит отдельное разрешение на доступ к нужной сводке.
          </p>
        </div>
        <span className="ai-coach-chat__disclaimer">Не заменяет врача или тренера.</span>
      </div>

      {currentConversationId !== null && conversation.isError && (
        <p className="ai-coach-inline-error" role="alert">
          Не удалось загрузить историю этого разговора. Попробуйте обновить экран; поле вопроса
          остаётся доступным.
        </p>
      )}

      {currentMessages.length === 0 && !pendingMessage && (
        <div className="ai-coach-chat__empty" data-testid="ai-coach-chat-empty">
          <p>Начните с вопроса или выберите подсказку ниже.</p>
        </div>
      )}
      <div className="ai-coach-chat__messages" aria-live="polite">
        {currentMessages.map((message) => (
          <ChatMessage
            feedback={feedbackByMessage[message.id] ?? null}
            key={message.id}
            message={message}
            onFeedback={sendFeedback}
            onRetry={retryMessage}
            retryBlocked={quota.data?.can_send === false || serviceRateLimited}
            retrying={retryingMessageId === message.id}
          />
        ))}
        {pendingMessage && (
          <>
            <article className="ai-coach-message ai-coach-message--user ai-coach-message--pending">
              <div className="ai-coach-message__author">Вы</div>
              <p className="ai-coach-message__text">{pendingMessage}</p>
            </article>
            <div className="ai-coach-chat__loading" role="status">
              AI Coach готовит ответ…
            </div>
          </>
        )}
        {retryingMessageId !== null && (
          <div className="ai-coach-chat__loading" role="status">
            AI Coach готовит ответ…
          </div>
        )}
      </div>

      {failure && (
        <section
          className="ai-coach-chat__failure"
          data-testid="ai-coach-chat-failure"
          role="alert"
        >
          <div>
            <span>{failure}</span>
            {temporaryRateLimit && (
              <small>
                Повторить можно через{' '}
                {formatQuotaCountdown(
                  new Date(temporaryRateLimit.retryAt).toISOString(),
                  clockTick,
                )}
                .
              </small>
            )}
          </div>
          <button type="button" onClick={() => setFailure(null)}>
            Понятно
          </button>
        </section>
      )}

      {consent.isError && status.personal_available && (
        <p className="ai-coach-inline-error" role="alert">
          Не удалось проверить персональный доступ. Обычный чат остаётся доступным отдельно.
        </p>
      )}

      {consent.data?.status !== 'granted' && !consent.isError && status.personal_available && (
        <details className="ai-coach-chat__consent">
          <summary>Персональные ответы</summary>
          <p>
            Для вопросов о ваших тренировках, прогрессе и питании нужно отдельное согласие. Без него
            личные данные не открываются AI Coach.
          </p>
          <Button
            disabled={consentMutation.isPending}
            type="button"
            onClick={() => consentMutation.mutate(true)}
          >
            {consentMutation.isPending ? 'Сохраняем…' : 'Разрешить персональные ответы'}
          </Button>
        </details>
      )}

      <div className="ai-coach-chat__quick-prompts" aria-label="Быстрые вопросы">
        {QUICK_PROMPTS.map((prompt) => (
          <button key={prompt.id} type="button" onClick={() => chooseQuickPrompt(prompt.message)}>
            {prompt.label}
          </button>
        ))}
      </div>

      <form className="ai-coach-chat__composer" onSubmit={submit}>
        <label className="sr-only" htmlFor="ai-coach-chat-message">
          Сообщение AI Coach
        </label>
        <textarea
          ref={composerRef}
          id="ai-coach-chat-message"
          maxLength={CHAT_MESSAGE_MAX_LENGTH}
          placeholder="Напишите вопрос…"
          rows={3}
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value);
            setSendRetry(null);
          }}
          onKeyDown={onComposerKeyDown}
        />
        <div className="ai-coach-chat__composer-meta">
          <span>Enter — отправить, Shift+Enter — новая строка</span>
          <QuotaIndicator quota={quota.data} now={clockTick} />
          <span>
            {draft.length}/{CHAT_MESSAGE_MAX_LENGTH}
          </span>
        </div>
        <div className="ai-coach-chat__composer-actions">
          <Button
            disabled={!draft.trim() || pending || quota.data?.can_send === false}
            type="submit"
          >
            {pending ? 'Отправляем…' : 'Отправить'}
          </Button>
        </div>
      </form>
    </div>
  );
}

export function AiCoachEntry({
  entryPoint,
}: {
  entryPoint: Exclude<AiCoachEntryPoint, 'profile'>;
}) {
  const status = useAiCoachStatus();
  if (!status.data?.ui_enabled) return null;
  return (
    <section className="ai-coach-entry" data-testid={`ai-coach-entry-${entryPoint}`}>
      <div>
        <span className="eyebrow">AI Coach</span>
        <strong>Нужна короткая подсказка?</strong>
        <p>Задайте вопрос о тренировках, питании, прогрессе или YFC.</p>
      </div>
      <AppLink
        className="button-link secondary-link"
        to="/app?section=profile#profile-ai-coach"
        onClick={() =>
          trackProductEvent({
            name: 'ai_coach_entry_opened',
            surface: productEventSurface(),
            entry_point: entryPoint,
          })
        }
      >
        Открыть AI Coach
      </AppLink>
    </section>
  );
}

export function AiCoachSettingsCard({
  defaultOpen = false,
  status: providedStatus,
}: {
  defaultOpen?: boolean;
  status?: AiCoachStatus;
}) {
  const statusQuery = useAiCoachStatus(!providedStatus);
  const status = providedStatus ?? statusQuery.data;
  if (!status?.ui_enabled) return null;
  return (
    <Card
      className="profile-settings-group ai-coach-settings-card"
      defaultOpen={defaultOpen}
      family="neutral"
      id="profile-ai-coach"
      title={
        <>
          <Icon name="ai-coach" size={20} /> AI Coach
        </>
      }
      description="Чат, помощь по приложению и разрешённые персональные сводки."
    >
      <AiCoachExperience status={status} entryPoint="profile" />
    </Card>
  );
}

export function AiCoachExperience({
  status: providedStatus,
}: {
  entryPoint: AiCoachEntryPoint;
  status?: AiCoachStatus;
}) {
  const statusQuery = useAiCoachStatus(!providedStatus);
  const status = providedStatus ?? statusQuery.data;
  if (!status?.ui_enabled) {
    return (
      <section className="ai-coach-unavailable" data-testid="ai-coach-ui-disabled">
        <p>AI Coach пока не может загрузиться. Основные функции приложения доступны.</p>
      </section>
    );
  }
  return (
    <section className="ai-coach-experience" data-testid="ai-coach-experience">
      <AiCoachChat status={status} />
      <details className="ai-coach-memory-disclosure">
        <summary>Настройки отдельной памяти</summary>
        <p className="ai-coach-memory-disclosure__hint">
          История этого чата хранится отдельно и не становится долговременной памятью автоматически.
        </p>
        <MemoryPanel />
      </details>
    </section>
  );
}
