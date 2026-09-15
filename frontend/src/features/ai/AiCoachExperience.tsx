import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createPortal } from 'react-dom';
import {
  useEffect,
  useMemo,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type RefObject,
  type ReactNode,
} from 'react';
import { ApiError, api } from '../../shared/api/client';
import type {
  AiCoachConsentResponse,
  AiCoachConversation,
  AiCoachConversationClearResponse,
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
import { Badge, Button, Card, IconButton, LoadingState } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useOptionalAiCoachWorkspace } from './AiCoachWorkspaceContext';
import './ai-coach.css';

export const AI_COACH_UI_VERSION = 'ai-coach-ui-v2';

export const aiCoachStatusQueryKey = ['ai-coach', 'status'] as const;
export const aiCoachConsentQueryKey = ['ai-coach', 'consent'] as const;
export const aiCoachMemoryQueryKey = ['ai-coach', 'memory'] as const;
export const aiCoachConversationsQueryKey = ['ai-coach', 'conversations'] as const;
export const aiCoachQuotaQueryKey = ['ai-coach', 'quota'] as const;

const ACTIVE_CONVERSATION_KEY = 'yfc:ai-coach:active-conversation';
const CHAT_MESSAGE_MAX_LENGTH = 2_000;
const CHAT_MESSAGE_COUNTER_THRESHOLD = 1_500;
const CHAT_MESSAGE_COUNTER_FOCUSED_THRESHOLD = 1_000;

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

export function useAiCoachQuota(enabled = true) {
  return useQuery<AiCoachQuotaSnapshot>({
    queryKey: aiCoachQuotaQueryKey,
    queryFn: () => api<AiCoachQuotaSnapshot>('/api/v1/ai-coach/quota'),
    enabled,
    staleTime: 0,
    refetchOnWindowFocus: false,
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

function safeInlineNodes(
  text: string,
  allowedUrls: ReadonlySet<string>,
  suppressMaterialLink = false,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const linkPattern = /\[([^\]]{1,120})\]\((https:\/\/[^)\s]+)\)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = linkPattern.exec(text)) !== null) {
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));
    const label = match[1] ?? '';
    const url = safeCoachUrl(match[2] ?? '');
    if (!(suppressMaterialLink && label.trim().toLocaleLowerCase() === 'открыть материал')) {
      nodes.push(
        url && allowedUrls.has(url) ? (
          <a href={url} key={`link-${index}`} rel="noreferrer noopener" target="_blank">
            {label}
          </a>
        ) : (
          label
        ),
      );
    }
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
  const hasSources = allowedUrls.size > 0;
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
    blocks.push(
      <p key={`paragraph-${index}`}>{safeInlineNodes(trimmed, allowedUrls, hasSources)}</p>,
    );
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

export function formatQuotaCountdown(resetAt: string, now = Date.now()): string {
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

export function aiCoachQuotaHeaderCopy(quota: AiCoachQuotaSnapshot | undefined): string {
  const state = getAiCoachQuotaState(quota);
  if (state === 'unknown') return 'Лимит обновляется…';
  if (state === 'empty') return 'Лимит исчерпан';
  if (!quota) return 'Лимит обновляется…';
  if (state === 'low') return `Осталось ${quota.remaining} из ${quota.limit}`;
  return `Готов · ${quota.remaining} из ${quota.limit}`;
}

export type AiCoachQuotaState = 'normal' | 'low' | 'empty' | 'unknown';

export function getAiCoachQuotaState(quota: AiCoachQuotaSnapshot | undefined): AiCoachQuotaState {
  if (
    !quota ||
    !Number.isFinite(quota.limit) ||
    quota.limit <= 0 ||
    !Number.isFinite(quota.remaining) ||
    quota.remaining < 0 ||
    quota.remaining > quota.limit
  ) {
    return 'unknown';
  }
  if (quota.remaining === 0) return 'empty';
  return quota.remaining / quota.limit <= 0.3 ? 'low' : 'normal';
}

const AI_COACH_HISTORY_TITLE_MAX_LENGTH = 80;

function conversationHistoryTitle(conversation: AiCoachConversationSummary): string {
  const title = conversation.title
    ?.replace(/\s+/g, ' ')
    .trim()
    .slice(0, AI_COACH_HISTORY_TITLE_MAX_LENGTH);
  return title || 'Новый разговор';
}

function conversationMessageCountCopy(count: number): string {
  const normalized = Math.max(0, Math.trunc(count));
  const remainder10 = normalized % 10;
  const remainder100 = normalized % 100;
  if (remainder10 === 1 && remainder100 !== 11) return '1 сообщение';
  if (remainder10 >= 2 && remainder10 <= 4 && (remainder100 < 12 || remainder100 > 14)) {
    return `${normalized} сообщения`;
  }
  return `${normalized} сообщений`;
}

function conversationHistoryDateKey(value: string): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return 'unknown';
  const date = new Date(timestamp);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function conversationHistoryDateLabel(value: string): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return 'Без даты';
  const date = new Date(timestamp);
  const today = new Date();
  const startOfDay = (current: Date) =>
    new Date(current.getFullYear(), current.getMonth(), current.getDate()).getTime();
  const dayDifference = Math.round((startOfDay(today) - startOfDay(date)) / 86_400_000);
  if (dayDifference === 0) return 'Сегодня';
  if (dayDifference === 1) return 'Вчера';
  return date.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

interface AiCoachConversationHistoryGroup {
  key: string;
  label: string;
  items: AiCoachConversationSummary[];
}

function groupConversationHistory(
  conversations: AiCoachConversationSummary[],
): AiCoachConversationHistoryGroup[] {
  const groups: AiCoachConversationHistoryGroup[] = [];
  const byKey = new Map<string, AiCoachConversationHistoryGroup>();
  conversations.forEach((conversation) => {
    const dateValue = conversation.updated_at || conversation.created_at;
    const key = conversationHistoryDateKey(dateValue);
    let group = byKey.get(key);
    if (!group) {
      group = { key, label: conversationHistoryDateLabel(dateValue), items: [] };
      byKey.set(key, group);
      groups.push(group);
    }
    group.items.push(conversation);
  });
  return groups;
}

function QuotaIndicator({ quota, now }: { quota: AiCoachQuotaSnapshot | undefined; now: number }) {
  const state = getAiCoachQuotaState(quota);
  return (
    <span
      className={`ai-coach-chat__quota ai-coach-chat__quota--${state}`}
      data-testid="ai-coach-quota"
      data-quota-limit={quota?.limit}
      data-quota-remaining={quota?.remaining}
    >
      <span>
        {state === 'unknown'
          ? 'Лимит обновляется…'
          : state === 'empty'
            ? 'Лимит исчерпан'
            : state === 'low'
              ? quota
                ? `Осталось ${quota.remaining} из ${quota.limit}`
                : 'Лимит обновляется…'
              : quota
                ? `${quota.remaining} из ${quota.limit}`
                : 'Лимит обновляется…'}
      </span>
      {quota && state !== 'unknown' && quota.remaining <= 2 && (
        <small>Сброс через {formatQuotaCountdown(quota.reset_at, now)}</small>
      )}
    </span>
  );
}

function QuotaResetHint({ quota, now }: { quota: AiCoachQuotaSnapshot | undefined; now: number }) {
  if (!quota || getAiCoachQuotaState(quota) === 'unknown' || quota.remaining > 2) return null;
  return (
    <small className="ai-coach-chat__quota-reset" data-testid="ai-coach-quota-reset">
      Сброс через {formatQuotaCountdown(quota.reset_at, now)}
    </small>
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
          <button
            aria-pressed={feedback === 'helpful'}
            aria-label="Полезно"
            className={feedback === 'helpful' ? 'is-selected' : ''}
            title="Полезно"
            type="button"
            onClick={() => onFeedback(message.id, 'helpful')}
          >
            👍
          </button>
          <button
            aria-pressed={feedback === 'not_helpful'}
            aria-label="Не полезно"
            className={feedback === 'not_helpful' ? 'is-selected' : ''}
            title="Не полезно"
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

function AiCoachHistoryView({
  backButtonRef,
  conversations,
  currentConversationId,
  pending,
  onBack,
  onClear,
  onDelete,
  onNewChat,
  onOpen,
}: {
  backButtonRef: RefObject<HTMLButtonElement | null>;
  conversations: AiCoachConversationSummary[];
  currentConversationId: number | null;
  pending: boolean;
  onBack: () => void;
  onClear: () => void;
  onDelete: (conversationId: number) => void;
  onNewChat: () => void;
  onOpen: (conversationId: number) => void;
}) {
  const groups = useMemo(() => groupConversationHistory(conversations), [conversations]);
  return (
    <section className="ai-coach-history" data-testid="ai-coach-history-view">
      <header className="ai-coach-history__header">
        <div className="ai-coach-history__heading">
          <button
            ref={backButtonRef}
            aria-label="Назад в чат"
            className="ai-coach-history__back"
            disabled={pending}
            title="Назад в чат"
            type="button"
            onClick={onBack}
          >
            <Icon name="arrow-left" size={20} />
            <span className="sr-only">Назад в чат</span>
          </button>
          <h3>История</h3>
        </div>
        <div className="ai-coach-history__actions">
          <Button
            data-testid="ai-coach-history-new-chat"
            disabled={pending}
            type="button"
            variant="secondary"
            onClick={onNewChat}
          >
            Новый чат
          </Button>
          {conversations.length > 0 && (
            <details className="ai-coach-history__menu" data-testid="ai-coach-history-menu">
              <summary aria-label="Действия истории" title="Действия истории">
                <Icon name="more-horizontal" size={20} />
                <span className="sr-only">Действия истории</span>
              </summary>
              <div>
                <button
                  data-testid="ai-coach-history-clear"
                  disabled={pending}
                  type="button"
                  onClick={(event) => {
                    event.currentTarget.closest('details')?.removeAttribute('open');
                    onClear();
                  }}
                >
                  Удалить всю историю
                </button>
              </div>
            </details>
          )}
        </div>
      </header>

      {groups.length > 0 ? (
        <div className="ai-coach-history__groups" aria-label="Разговоры AI Coach">
          {groups.map((group) => (
            <section className="ai-coach-history__group" key={group.key}>
              <h4>{group.label}</h4>
              <ul>
                {group.items.map((conversation) => {
                  const active = conversation.id === currentConversationId;
                  const title = conversationHistoryTitle(conversation);
                  return (
                    <li
                      className={`ai-coach-history__item${active ? ' is-active' : ''}`}
                      data-active={active || undefined}
                      data-testid={`ai-coach-history-item-${conversation.id}`}
                      key={conversation.id}
                    >
                      <button
                        aria-current={active ? 'true' : undefined}
                        className="ai-coach-history__item-open"
                        disabled={pending}
                        type="button"
                        onClick={() => onOpen(conversation.id)}
                      >
                        <span className="ai-coach-history__item-title">{title}</span>
                        <span className="ai-coach-history__item-meta">
                          {conversationMessageCountCopy(conversation.message_count)}
                        </span>
                      </button>
                      <details className="ai-coach-history__item-menu">
                        <summary aria-label="Действия" title="Действия">
                          <Icon name="more-horizontal" size={20} />
                          <span className="sr-only">Действия</span>
                        </summary>
                        <div>
                          <button
                            disabled={pending}
                            type="button"
                            onClick={() => onDelete(conversation.id)}
                          >
                            Удалить чат
                          </button>
                        </div>
                      </details>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        <div className="ai-coach-history__empty" data-testid="ai-coach-history-empty">
          <strong>История чатов пуста</strong>
          <p>Новые разговоры появятся здесь после первого вопроса.</p>
        </div>
      )}
    </section>
  );
}

export function MemoryPanel() {
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
            <strong>Память AI Coach</strong>
            <Badge tone={current.status === 'enabled' ? 'success' : 'warning'}>
              {current.status === 'enabled'
                ? 'Вкл'
                : current.status === 'paused'
                  ? 'Пауза'
                  : 'Выкл'}
            </Badge>
          </div>
          <p>Запоминать подтверждённые предпочтения между разговорами.</p>
          <small>История чата не сохраняется в память автоматически.</small>
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

      <details className="ai-coach-memory__notice">
        <summary>Подробнее о памяти</summary>
        <p>
          Можно сохранять только подтверждённые немедицинские предпочтения и явный контекст. Данные
          приложения остаются источником истины.
        </p>
        <div className="ai-coach-memory__categories">
          {current.categories.map((item) => (
            <span key={item}>
              {current.category_labels[item] ?? MEMORY_CATEGORY_LABELS[item] ?? item}
            </span>
          ))}
        </div>
      </details>

      {memoryEnabled && (
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
            <Button
              disabled={!memoryEnabled || !value.trim() || !confirmed || pending}
              type="submit"
            >
              {editing ? 'Сохранить изменение' : 'Сохранить в память'}
            </Button>
            {editing && (
              <Button disabled={pending} type="button" variant="secondary" onClick={cancelEditing}>
                Отмена
              </Button>
            )}
          </div>
        </form>
      )}

      {items.length > 0 ? (
        <div className="ai-coach-memory__list" aria-label="Сохранённые элементы памяти">
          {items.map((item) => (
            <article className="ai-coach-memory__item" key={item.id}>
              <div>
                <Badge tone="neutral">{item.category_label}</Badge>
                <p>{item.value}</p>
                <small>Сохранено по вашему подтверждению.</small>
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
          Очистить память
        </Button>
      )}
    </section>
  );
}

export function AiCoachPersonalConsentPanel({ status }: { status: AiCoachStatus }) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
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

  if (!status.personal_available) {
    return (
      <section
        className="ai-coach-settings-section ai-coach-settings-section--muted"
        data-testid="ai-coach-personal-settings"
      >
        <div>
          <h3>Персонализация</h3>
          <p>Пока недоступна. Обычный чат работает без доступа к личным данным.</p>
        </div>
        <Badge tone="neutral">Недоступно</Badge>
      </section>
    );
  }

  if (consent.isLoading) {
    return (
      <section className="ai-coach-settings-section" data-testid="ai-coach-personal-settings">
        <LoadingState label="Проверяем персональный доступ…" />
      </section>
    );
  }

  if (consent.isError || !consent.data) {
    return (
      <section
        className="ai-coach-settings-section ai-coach-settings-section--error"
        data-testid="ai-coach-personal-settings"
        role="alert"
      >
        <div>
          <h3>Персонализация</h3>
          <p>Не удалось проверить настройку. Обычный чат остаётся доступным.</p>
        </div>
        <Button
          type="button"
          variant="secondary"
          onClick={() => void queryClient.invalidateQueries({ queryKey: aiCoachConsentQueryKey })}
        >
          Повторить
        </Button>
      </section>
    );
  }

  const granted = consent.data.status === 'granted';
  return (
    <section className="ai-coach-settings-section" data-testid="ai-coach-personal-settings">
      <div className="ai-coach-settings-section__header">
        <div>
          <h3>Персонализация</h3>
          <p>
            {granted
              ? 'Использовать мои тренировки, питание и прогресс для личных ответов.'
              : 'Включите доступ к тренировкам, питанию и прогрессу для личных ответов.'}
          </p>
          <small>AI Coach использует только разрешённые данные.</small>
        </div>
        <Badge tone={granted ? 'success' : 'warning'}>{granted ? 'Вкл' : 'Выкл'}</Badge>
      </div>
      <Button
        disabled={consentMutation.isPending}
        type="button"
        variant={granted ? 'secondary' : 'primary'}
        onClick={() => consentMutation.mutate(!granted)}
      >
        {consentMutation.isPending ? 'Сохраняем…' : granted ? 'Выключить' : 'Включить'}
      </Button>
    </section>
  );
}

function AiCoachChat({
  historyTarget,
  showPersonalConsent = true,
  status,
}: {
  historyTarget?: HTMLElement | null;
  showPersonalConsent?: boolean;
  status: AiCoachStatus;
}) {
  const { confirm, toast } = useFeedback();
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
  const [composerFocused, setComposerFocused] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [feedbackByMessage, setFeedbackByMessage] = useState<Record<number, AiCoachHelpfulness>>(
    {},
  );
  const historyBackRef = useRef<HTMLButtonElement>(null);
  const historyControlRef = useRef<HTMLButtonElement>(null);

  const conversations = useQuery<{ items: AiCoachConversationSummary[] }>({
    queryKey: aiCoachConversationsQueryKey,
    queryFn: () => api<{ items: AiCoachConversationSummary[] }>('/api/v1/ai-coach/conversations'),
    staleTime: 15_000,
    retry: false,
  });
  const quota = useAiCoachQuota();
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
  const resetConversationState = (closeHistory = true) => {
    setIsNewConversation(true);
    setActiveConversationId(null);
    storeActiveConversationId(null);
    setDraft('');
    setSendRetry(null);
    setRetryRequest(null);
    setRetryingMessageId(null);
    setFailure(null);
    setFeedbackByMessage({});
    if (closeHistory) setHistoryOpen(false);
  };
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

  const applyConversationDeletion = (conversationId: number, notice: string) => {
    queryClient.setQueryData<{ items: AiCoachConversationSummary[] }>(
      aiCoachConversationsQueryKey,
      (current) =>
        current
          ? { items: current.items.filter((conversation) => conversation.id !== conversationId) }
          : current,
    );
    queryClient.removeQueries({ queryKey: ['ai-coach', 'conversation', conversationId] });
    if (conversationId === currentConversationId) {
      resetConversationState();
      toast(`${notice} Открыт новый чат.`);
    } else {
      toast(notice);
    }
    void queryClient.invalidateQueries({ queryKey: aiCoachConversationsQueryKey });
  };

  const deleteConversationMutation = useMutation({
    mutationFn: (conversationId: number) =>
      api<void>(`/api/v1/ai-coach/conversations/${conversationId}`, { method: 'DELETE' }),
    onSuccess: (_data, conversationId) => {
      applyConversationDeletion(conversationId, 'Чат удалён.');
    },
    onError: (reason, conversationId) => {
      if (reason instanceof ApiError && reason.status === 404) {
        applyConversationDeletion(conversationId, 'Чат уже удалён.');
        return;
      }
      void queryClient.invalidateQueries({ queryKey: aiCoachConversationsQueryKey });
      toast('Не удалось удалить чат. Попробуйте ещё раз.', 'error');
    },
  });

  const clearConversationHistoryMutation = useMutation({
    mutationFn: () =>
      api<AiCoachConversationClearResponse>('/api/v1/ai-coach/conversations', {
        method: 'DELETE',
      }),
    onSuccess: ({ deleted_count }) => {
      queryClient.setQueryData<{ items: AiCoachConversationSummary[] }>(
        aiCoachConversationsQueryKey,
        { items: [] },
      );
      queryClient.removeQueries({ queryKey: ['ai-coach', 'conversation'] });
      resetConversationState(false);
      setHistoryOpen(true);
      toast(deleted_count > 0 ? 'История чатов удалена.' : 'История чатов уже пуста.');
      void queryClient.invalidateQueries({ queryKey: aiCoachConversationsQueryKey });
    },
    onError: () => toast('Не удалось очистить историю чатов. Попробуйте ещё раз.', 'error'),
  });

  const currentMessages = conversation.data?.messages ?? [];
  const pending = sendMutation.isPending || retryMutation.isPending;
  const historyMutationPending =
    deleteConversationMutation.isPending || clearConversationHistoryMutation.isPending;
  const serviceRateLimited = temporaryRateLimit !== null && temporaryRateLimit.retryAt > clockTick;
  const showEmptyState = currentMessages.length === 0 && !pendingMessage;
  const showHistoryControl =
    !pendingMessage && (historyOpen || (conversations.data?.items.length ?? 0) > 0);
  const showCharacterCount =
    draft.length >= CHAT_MESSAGE_COUNTER_THRESHOLD ||
    (composerFocused && draft.length >= CHAT_MESSAGE_COUNTER_FOCUSED_THRESHOLD);

  useEffect(() => {
    if (!historyOpen) return;
    historyBackRef.current?.focus();
    const onHistoryKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      setHistoryOpen(false);
      window.requestAnimationFrame(() => historyControlRef.current?.focus());
    };
    document.addEventListener('keydown', onHistoryKeyDown);
    return () => document.removeEventListener('keydown', onHistoryKeyDown);
  }, [historyOpen]);

  useLayoutEffect(() => {
    const textarea = composerRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    const maxHeight = 144;
    const nextHeight = Math.min(maxHeight, Math.max(48, textarea.scrollHeight));
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, [draft]);

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
    if (pending || historyMutationPending) return;
    resetConversationState();
  };
  const openConversation = (conversationId: number) => {
    if (pending || historyMutationPending) return;
    setIsNewConversation(false);
    setActiveConversationId(conversationId);
    storeActiveConversationId(conversationId);
    setSendRetry(null);
    setRetryRequest(null);
    setFailure(null);
    setHistoryOpen(false);
  };
  const requestDeleteConversation = async (conversationId: number) => {
    if (pending || historyMutationPending) return;
    const approved = await confirm({
      title: 'Удалить этот чат?',
      message: 'История сообщений этого разговора будет удалена. Память AI Coach не изменится.',
      confirmText: 'Удалить',
    });
    if (approved) deleteConversationMutation.mutate(conversationId);
  };
  const requestClearConversationHistory = async () => {
    if (pending || historyMutationPending) return;
    const approved = await confirm({
      title: 'Удалить всю историю чатов?',
      message:
        'Все разговоры и сообщения AI Coach будут удалены. Память AI Coach и персонализация не изменятся.',
      confirmText: 'Удалить всё',
    });
    if (approved) clearConversationHistoryMutation.mutate();
  };
  const sendFeedback = (messageId: number, value: AiCoachHelpfulness) => {
    if (currentConversationId === null || feedbackMutation.isPending) return;
    feedbackMutation.mutate({ conversationId: currentConversationId, messageId, value });
  };

  const historyControl = showHistoryControl ? (
    <button
      ref={historyControlRef}
      aria-label="История"
      className="ai-coach-chat__history-trigger"
      data-testid="ai-coach-history-control"
      disabled={pending || historyMutationPending}
      title="История"
      type="button"
      onClick={() => setHistoryOpen(true)}
    >
      <Icon name="more-horizontal" size={20} />
      <span className="sr-only">История</span>
    </button>
  ) : null;
  const historyPlacement =
    historyTarget === undefined
      ? historyControl && <div className="ai-coach-chat__toolbar">{historyControl}</div>
      : historyTarget
        ? createPortal(historyControl, historyTarget)
        : null;

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
      {historyPlacement}

      {historyOpen ? (
        <AiCoachHistoryView
          backButtonRef={historyBackRef}
          conversations={conversationItems}
          currentConversationId={currentConversationId}
          pending={pending || historyMutationPending}
          onBack={() => {
            setHistoryOpen(false);
            window.requestAnimationFrame(() => historyControlRef.current?.focus());
          }}
          onClear={requestClearConversationHistory}
          onDelete={requestDeleteConversation}
          onNewChat={startNewConversation}
          onOpen={openConversation}
        />
      ) : (
        <>
          {showEmptyState && (
            <div className="ai-coach-chat__empty" data-testid="ai-coach-chat-empty">
              <div className="ai-coach-chat__welcome">
                <h3>Чем помочь?</h3>
                <span className="ai-coach-chat__disclaimer">
                  AI Coach может ошибаться и не заменяет врача или тренера.
                </span>
              </div>
              <div className="ai-coach-chat__quick-prompts" aria-label="Быстрые вопросы">
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt.id}
                    type="button"
                    onClick={() => chooseQuickPrompt(prompt.message)}
                  >
                    {prompt.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {currentConversationId !== null && conversation.isError && (
            <p className="ai-coach-inline-error" role="alert">
              Не удалось загрузить историю этого разговора. Попробуйте обновить экран; поле вопроса
              остаётся доступным.
            </p>
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
            <div
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
              <IconButton
                aria-label="Скрыть сообщение об ошибке"
                title="Скрыть сообщение"
                type="button"
                onClick={() => setFailure(null)}
              >
                <Icon name="close" size={16} />
              </IconButton>
            </div>
          )}

          {showPersonalConsent && <AiCoachPersonalConsentPanel status={status} />}

          <form className="ai-coach-chat__composer" onSubmit={submit}>
            <label className="sr-only" htmlFor="ai-coach-chat-message">
              Сообщение AI Coach
            </label>
            <div className="ai-coach-chat__composer-control">
              <textarea
                ref={composerRef}
                id="ai-coach-chat-message"
                maxLength={CHAT_MESSAGE_MAX_LENGTH}
                placeholder="Напишите вопрос…"
                rows={1}
                value={draft}
                onBlur={() => setComposerFocused(false)}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setSendRetry(null);
                }}
                onFocus={() => setComposerFocused(true)}
                onKeyDown={onComposerKeyDown}
              />
              <IconButton
                aria-busy={pending}
                aria-label="Отправить"
                className="ai-coach-chat__send"
                data-testid="ai-coach-send"
                disabled={!draft.trim() || pending || quota.data?.can_send === false}
                title="Отправить"
                type="submit"
              >
                {pending ? (
                  <Icon className="ai-coach-chat__send-spinner" name="sync" size={20} />
                ) : (
                  <Icon name="arrow-up" size={20} />
                )}
              </IconButton>
            </div>
            <div className="ai-coach-chat__composer-meta">
              <span className="ai-coach-chat__keyboard-hint">Shift+Enter — новая строка</span>
              {historyTarget === undefined ? (
                <QuotaIndicator quota={quota.data} now={clockTick} />
              ) : (
                <QuotaResetHint quota={quota.data} now={clockTick} />
              )}
              {showCharacterCount && (
                <span
                  className="ai-coach-chat__composer-count"
                  data-testid="ai-coach-composer-count"
                >
                  {draft.length}/{CHAT_MESSAGE_MAX_LENGTH}
                </span>
              )}
            </div>
          </form>
        </>
      )}
    </div>
  );
}

export function AiCoachEntry({
  entryPoint,
}: {
  entryPoint: Exclude<AiCoachEntryPoint, 'profile'>;
}) {
  const status = useAiCoachStatus();
  const workspace = useOptionalAiCoachWorkspace();
  if (!status.data?.ui_enabled) return null;
  return (
    <section className="ai-coach-entry" data-testid={`ai-coach-entry-${entryPoint}`}>
      <div>
        <span className="eyebrow">AI Coach</span>
        <strong>Помощник по тренировкам, питанию и прогрессу</strong>
        <p>Короткий разговор с AI Coach поверх текущего экрана.</p>
      </div>
      <AppLink
        className="button-link secondary-link"
        to="/app?section=profile#profile-ai-coach"
        onClick={(event) => {
          if (workspace) {
            event.preventDefault();
            workspace.open(event.currentTarget);
          }
          trackProductEvent({
            name: 'ai_coach_entry_opened',
            surface: productEventSurface(),
            entry_point: entryPoint,
          });
        }}
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
  const quota = useAiCoachQuota();
  const workspace = useOptionalAiCoachWorkspace();
  const deepLinkOpenedRef = useRef(false);
  const quotaState = getAiCoachQuotaState(quota.data);

  useEffect(() => {
    if (!defaultOpen || !workspace || !status?.ui_enabled || deepLinkOpenedRef.current) return;
    deepLinkOpenedRef.current = true;
    workspace.open(null);
  }, [defaultOpen, status?.ui_enabled, workspace]);

  if (!status?.ui_enabled) return null;
  return (
    <Card
      className={`profile-settings-group ai-coach-settings-card${defaultOpen ? ' is-deep-linked' : ''}`}
      collapsible={false}
      family="neutral"
      id="profile-ai-coach"
      title={
        <span className="ai-coach-settings-card__title" data-testid="ai-coach-profile-title">
          <Icon name="ai-coach" size={20} />
          <span>AI Coach</span>
        </span>
      }
    >
      <div className="ai-coach-entry--profile" data-testid="ai-coach-entry-profile">
        <div>
          <strong>Помощник по тренировкам, питанию и прогрессу</strong>
          {quota.data && (
            <small
              className={`ai-coach-entry__quota ai-coach-entry__quota--${quotaState}`}
              data-quota-limit={quota.data.limit}
              data-quota-remaining={quota.data.remaining}
              data-quota-state={quotaState}
              data-testid="ai-coach-entry-quota"
            >
              {quotaState === 'empty'
                ? 'Лимит исчерпан'
                : quotaState === 'unknown'
                  ? 'Лимит обновляется…'
                  : `${quota.data.remaining} из ${quota.data.limit} запросов`}
            </small>
          )}
        </div>
        <AppLink
          className="button-link secondary-link"
          to="/app?section=profile#profile-ai-coach"
          onClick={(event) => {
            if (workspace) {
              event.preventDefault();
              workspace.open(event.currentTarget);
            }
            trackProductEvent({
              name: 'ai_coach_entry_opened',
              surface: productEventSurface(),
              entry_point: 'profile',
            });
          }}
        >
          Открыть AI Coach
        </AppLink>
      </div>
    </Card>
  );
}

export function AiCoachExperience({
  historyTarget,
  showMemorySettings = true,
  showPersonalConsent = true,
  status: providedStatus,
}: {
  entryPoint: AiCoachEntryPoint;
  historyTarget?: HTMLElement | null;
  showMemorySettings?: boolean;
  showPersonalConsent?: boolean;
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
      <AiCoachChat
        historyTarget={historyTarget}
        status={status}
        showPersonalConsent={showPersonalConsent}
      />
      {showMemorySettings && (
        <details className="ai-coach-memory-disclosure">
          <summary>Настройки отдельной памяти</summary>
          <p className="ai-coach-memory-disclosure__hint">
            История этого чата хранится отдельно и не становится долговременной памятью
            автоматически.
          </p>
          <MemoryPanel />
        </details>
      )}
    </section>
  );
}
