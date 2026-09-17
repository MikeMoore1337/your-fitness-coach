import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  AiCoachExperience,
  AiCoachSettingsCard,
  aiCoachQuotaHeaderCopy,
  getAiCoachQuotaState,
  safeCoachUrl,
} from '../../../../src/features/ai/AiCoachExperience';
import {
  AiCoachWorkspaceProvider,
  AI_COACH_WORKSPACE_LAYOUT_KEY,
  clampAiCoachWorkspaceLayout,
  readAiCoachWorkspaceLayout,
  resizeAiCoachWorkspaceLayout,
} from '../../../../src/features/ai/AiCoachWorkspace';
import type { AiCoachContextDescriptor } from '../../../../src/features/ai/aiCoachContext';
import { api } from '../../../../src/shared/api/client';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import type {
  AiCoachConversation,
  AiCoachConversationMessage,
  AiCoachQuotaSnapshot,
  AiCoachStatus,
} from '../../../../src/shared/api/types';

vi.mock('../../../../src/shared/api/client', () => ({
  api: vi.fn(),
}));

vi.mock('../../../../src/shared/analytics/productEvents', () => ({
  productEventSurface: () => 'mobile_web',
  trackProductEvent: vi.fn(),
}));

const apiMock = vi.mocked(api);
const status = {
  ui_enabled: true,
  generic_available: true,
  personal_available: false,
} as const;

const quotaSnapshot = (
  remaining = 20,
  limit = 20,
  resetAt = '2026-09-16T00:00:00Z',
): AiCoachQuotaSnapshot => ({
  limit,
  used: limit - remaining,
  remaining,
  reset_at: resetAt,
  retry_after_seconds: 86_400,
  can_send: remaining > 0,
});

const memoryResponse = (
  memoryStatus: 'enabled' | 'paused' | 'revoked' = 'revoked',
  items = [],
) => ({
  status: memoryStatus,
  scope: 'ai_coach_memory_v1',
  consent_version: 'ai-coach-memory-v1',
  categories: [
    'preferred_explanation_style',
    'ai_interaction_preferences',
    'stable_non_medical_preferences',
    'explicit_ai_context',
  ],
  category_labels: {
    preferred_explanation_style: 'Стиль объяснений',
    ai_interaction_preferences: 'Предпочтения общения',
    stable_non_medical_preferences: 'Стабильные немедицинские предпочтения',
    explicit_ai_context: 'Явный контекст для AI Coach',
  },
  purpose: 'Отдельный контекст для продолжения общения.',
  retention_notice: 'История и память хранятся отдельно.',
  max_items: 20,
  consent_source: 'test',
  items,
  granted_at: memoryStatus === 'enabled' ? '2026-09-11T00:00:00Z' : null,
  paused_at: memoryStatus === 'paused' ? '2026-09-11T00:00:00Z' : null,
  revoked_at: memoryStatus === 'revoked' ? '2026-09-11T00:00:00Z' : null,
});

const consentResponse = (consentStatus: 'granted' | 'revoked' = 'revoked') => ({
  status: consentStatus,
  scope: 'personal_readonly_tools_v1',
  consent_version: 'ai-coach-personal-v1',
  categories: ['personal_progress', 'training_history', 'nutrition_summary'],
  purpose: 'Тестовое согласие.',
  provider_name: 'groq',
  provider_policy_revision: 'test',
  retention_notice: 'История диалога и память разделены.',
  consent_source: 'test',
  granted_at: consentStatus === 'granted' ? '2026-09-11T00:00:00Z' : null,
  revoked_at: consentStatus === 'revoked' ? '2026-09-11T00:00:00Z' : null,
});

const chatMessage = (
  id: number,
  role: 'user' | 'assistant',
  content: string,
  overrides: Partial<AiCoachConversationMessage> = {},
): AiCoachConversationMessage => ({
  id,
  role,
  content,
  status: 'complete',
  outcome: role === 'assistant' ? 'answer' : null,
  safety_category: 'clear',
  failure_category: null,
  citations: [],
  limitations: [],
  created_at: '2026-09-14T12:00:00Z',
  ...overrides,
});

const conversation = (
  id: number,
  messages: AiCoachConversationMessage[] = [],
): AiCoachConversation => ({
  id,
  title: messages.length ? 'Первый вопрос' : null,
  created_at: '2026-09-14T12:00:00Z',
  updated_at: '2026-09-14T12:00:00Z',
  messages,
});

function renderExperience(
  experienceStatus: AiCoachStatus = status,
  context?: AiCoachContextDescriptor,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <NavigationProvider>
          <AiCoachExperience context={context} entryPoint="profile" status={experienceStatus} />
        </NavigationProvider>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

function renderSettingsCard(settingsStatus: AiCoachStatus) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <NavigationProvider>
          <AiCoachSettingsCard status={settingsStatus} />
        </NavigationProvider>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

function renderWorkspace(settingsStatus: AiCoachStatus = status) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <NavigationProvider>
          <AiCoachWorkspaceProvider status={settingsStatus}>
            <AiCoachSettingsCard status={settingsStatus} />
          </AiCoachWorkspaceProvider>
        </NavigationProvider>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

function mockBaseApi(quota = quotaSnapshot()) {
  apiMock.mockImplementation(async (path, options) => {
    if (path === '/api/v1/ai-coach/quota') return quota;
    if (path === '/api/v1/ai-coach/conversations') return { items: [] };
    if (path === '/api/v1/ai-coach/memory') return memoryResponse();
    if (path === '/api/v1/ai-coach/consent') return consentResponse();
    throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
  });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  window.sessionStorage.removeItem('yfc:ai-coach:active-conversation');
  window.localStorage.removeItem(AI_COACH_WORKSPACE_LAYOUT_KEY);
  apiMock.mockReset();
});

describe('AiCoachExperience', () => {
  it('accepts only credential-free HTTPS URLs', () => {
    expect(safeCoachUrl('https://example.org/article')).toBe('https://example.org/article');
    expect(safeCoachUrl('javascript:alert(1)')).toBeNull();
    expect(safeCoachUrl('https://user:pass@example.org/article')).toBeNull();
    expect(safeCoachUrl('https://example.org/article#secret')).toBeNull();
  });

  it('renders a simple chat surface without legacy report controls', async () => {
    mockBaseApi();
    renderExperience();

    await waitFor(() => expect(screen.getByTestId('ai-coach-chat')).toBeInTheDocument());
    expect(screen.getByRole('textbox', { name: 'Сообщение AI Coach' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Отправить' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Новый чат' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Что делать сегодня?' })).toBeInTheDocument();
    expect(screen.getByTestId('ai-coach-quota')).toHaveAttribute('data-quota-remaining', '20');
    expect(screen.queryByText('Публичная помощь')).not.toBeInTheDocument();
    expect(screen.queryByText('Моя сводка')).not.toBeInTheDocument();
    expect(screen.queryByText(/report_version|prompt_version|debug/i)).not.toBeInTheDocument();
  });

  it('sends a bounded context descriptor and renders its high-level attachment', async () => {
    let sentBody: { message: string; context?: { surface: string; resource_id?: number } } | null =
      null;
    let messages: AiCoachConversationMessage[] = [];
    apiMock.mockImplementation(async (path, options) => {
      if (path === '/api/v1/ai-coach/quota') return quotaSnapshot();
      if (path === '/api/v1/ai-coach/conversations' && options?.method === 'POST') {
        return conversation(1);
      }
      if (path === '/api/v1/ai-coach/conversations') {
        return {
          items: messages.length ? [{ ...conversation(1, messages), message_count: 2 }] : [],
        };
      }
      if (path === '/api/v1/ai-coach/memory') return memoryResponse();
      if (path === '/api/v1/ai-coach/consent') return consentResponse();
      if (path === '/api/v1/ai-coach/conversations/1/messages') {
        const body = options?.body as {
          message: string;
          context?: { surface: string; resource_id?: number };
        };
        sentBody = body;
        messages = [
          chatMessage(1, 'user', body.message),
          chatMessage(2, 'assistant', 'Ответ с выбранным контекстом.'),
        ];
        return {
          conversation_id: 1,
          user_message: messages[0],
          assistant_message: messages[1],
          outcome: 'answer',
          data_class: 'personalized',
          answer: 'Ответ с выбранным контекстом.',
          citations: [],
          limitations: [],
          safety_category: 'clear',
          failure_category: null,
          prompt_version: 'ai-coach-chat-v1',
          request_id: 'request-1',
          quota: quotaSnapshot(),
          context: { surface: 'workout', label: 'Эта тренировка' },
        };
      }
      if (path === '/api/v1/ai-coach/conversations/1') return conversation(1, messages);
      throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
    });
    renderExperience(status, { surface: 'workout', resourceId: 42 });

    const input = await screen.findByRole('textbox', { name: 'Сообщение AI Coach' });
    expect(input).toHaveFocus();
    expect(screen.getByTestId('ai-coach-context-attachment')).toHaveTextContent('Эта тренировка');
    fireEvent.change(input, { target: { value: 'Разбери эту тренировку' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));

    await waitFor(() =>
      expect(screen.getByText('Ответ с выбранным контекстом.')).toBeInTheDocument(),
    );
    expect(sentBody).toEqual({
      message: 'Разбери эту тренировку',
      context: { surface: 'workout', resource_id: 42 },
    });
  });

  it('keeps history actions secondary and uses the stored conversation title', async () => {
    const messages = [
      chatMessage(1, 'user', 'Сколько отдыхать между подходами?'),
      chatMessage(2, 'assistant', 'Ответ о восстановлении.'),
    ];
    const storedConversation = {
      ...conversation(1, messages),
      title: 'Сколько отдыхать между подходами?',
    };
    mockBaseApi();
    apiMock.mockImplementation(async (path, options) => {
      if (path === '/api/v1/ai-coach/quota') return quotaSnapshot();
      if (path === '/api/v1/ai-coach/conversations') {
        if (options?.method === 'DELETE') return { deleted_count: 1 };
        return {
          items: [{ ...storedConversation, message_count: messages.length }],
        };
      }
      if (path === '/api/v1/ai-coach/conversations/1') return storedConversation;
      if (path === '/api/v1/ai-coach/memory') return memoryResponse();
      throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
    });

    renderExperience();
    const historyButton = await screen.findByRole('button', { name: 'История' });
    fireEvent.click(historyButton);

    const history = await screen.findByTestId('ai-coach-history-view');
    expect(within(history).getByRole('button', { name: 'Новый чат' })).toBeInTheDocument();
    expect(
      within(history).queryByTestId('ai-coach-history-new-chat-empty'),
    ).not.toBeInTheDocument();
    expect(
      within(history).getByText('Сколько отдыхать между подходами?', { exact: true }),
    ).toBeInTheDocument();
    expect(
      within(history).queryByRole('button', { name: 'Удалить всю историю чатов' }),
    ).not.toBeInTheDocument();
    expect(within(history).queryByTestId('ai-coach-history-footer')).not.toBeInTheDocument();

    const menu = within(history).getByTestId('ai-coach-history-menu');
    expect(menu).not.toHaveAttribute('open');
    const summary = menu.querySelector('summary');
    expect(summary).not.toBeNull();
    if (!summary) throw new Error('History actions menu has no summary');
    fireEvent.click(summary);
    expect(menu).toHaveAttribute('open');
    expect(within(menu).getByTestId('ai-coach-history-clear')).toHaveTextContent(
      'Удалить всю историю',
    );
  });

  it('uses semantic quota states at the exact low boundary and keeps invalid data neutral', () => {
    expect(getAiCoachQuotaState(quotaSnapshot(7, 20))).toBe('normal');
    expect(getAiCoachQuotaState(quotaSnapshot(6, 20))).toBe('low');
    expect(getAiCoachQuotaState(quotaSnapshot(1, 20))).toBe('low');
    expect(getAiCoachQuotaState(quotaSnapshot(0, 20))).toBe('empty');
    expect(getAiCoachQuotaState(undefined)).toBe('unknown');
    expect(getAiCoachQuotaState(quotaSnapshot(0, 0))).toBe('unknown');
    expect(getAiCoachQuotaState(quotaSnapshot(21, 20))).toBe('unknown');

    expect(aiCoachQuotaHeaderCopy(quotaSnapshot(7, 20))).toBe('Готов · 7 из 20');
    expect(aiCoachQuotaHeaderCopy(quotaSnapshot(6, 20))).toBe('Осталось 6 из 20');
    expect(aiCoachQuotaHeaderCopy(quotaSnapshot(0, 20))).toBe('Лимит исчерпан');
    expect(aiCoachQuotaHeaderCopy(undefined)).toBe('Лимит обновляется…');
  });

  it('keeps one icon-only send control and grows the shared composer for long drafts', async () => {
    mockBaseApi();
    renderExperience();

    const input = await screen.findByRole('textbox', { name: 'Сообщение AI Coach' });
    const send = screen.getByRole('button', { name: 'Отправить' });
    expect(input).toHaveAttribute('rows', '1');
    expect(send).toBeDisabled();
    expect(send.querySelector('[data-icon="arrow-up"]')).not.toBeNull();
    expect(screen.queryByTestId('ai-coach-composer-count')).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: 'Короткий вопрос' } });
    expect(send).toBeEnabled();
    expect(screen.queryByTestId('ai-coach-composer-count')).not.toBeInTheDocument();

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'а'.repeat(1_000) } });
    expect(screen.getByTestId('ai-coach-composer-count')).toHaveTextContent('1000/2000');
    fireEvent.blur(input);
    expect(screen.queryByTestId('ai-coach-composer-count')).not.toBeInTheDocument();

    Object.defineProperty(input, 'scrollHeight', { configurable: true, value: 240 });
    fireEvent.change(input, { target: { value: 'а'.repeat(1_600) } });
    expect(screen.getByTestId('ai-coach-composer-count')).toHaveTextContent('1600/2000');
    expect(input).toHaveStyle({ height: '144px', overflowY: 'auto' });
  });

  it('renders the server-owned quota, refreshes it on focus and keeps the real limit dynamic', async () => {
    let currentQuota = quotaSnapshot();
    let quotaCalls = 0;
    const messages: AiCoachConversationMessage[] = [];
    apiMock.mockImplementation(async (path, options) => {
      if (path === '/api/v1/ai-coach/quota') {
        quotaCalls += 1;
        return currentQuota;
      }
      if (path === '/api/v1/ai-coach/conversations' && options?.method === 'POST') {
        return conversation(11);
      }
      if (path === '/api/v1/ai-coach/conversations') {
        return { items: messages.length ? [{ ...conversation(11, messages) }] : [] };
      }
      if (path === '/api/v1/ai-coach/memory') return memoryResponse();
      if (path === '/api/v1/ai-coach/conversations/11') return conversation(11, messages);
      if (path === '/api/v1/ai-coach/conversations/11/messages') {
        expect(options?.headers).toEqual({ 'X-Request-ID': expect.any(String) });
        const body = options?.body as { message: string };
        const userMessage = chatMessage(11, 'user', body.message);
        const assistantMessage = chatMessage(12, 'assistant', 'Ответ с учётом квоты.');
        messages.push(userMessage, assistantMessage);
        currentQuota = quotaSnapshot(19);
        return {
          conversation_id: 11,
          user_message: userMessage,
          assistant_message: assistantMessage,
          outcome: 'answer',
          data_class: 'generic',
          answer: assistantMessage.content,
          citations: [],
          limitations: [],
          safety_category: 'clear',
          failure_category: null,
          prompt_version: 'ai-coach-chat-v1',
          request_id: 'request-11',
          quota: currentQuota,
        };
      }
      throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
    });
    renderExperience();
    const indicator = await screen.findByTestId('ai-coach-quota');
    expect(indicator).toHaveAttribute('data-quota-limit', '20');
    expect(indicator).toHaveAttribute('data-quota-remaining', '20');
    expect(screen.queryByText(/Сброс через/)).not.toBeInTheDocument();

    window.dispatchEvent(new Event('focus'));
    await waitFor(() => expect(quotaCalls).toBeGreaterThan(1));

    const input = screen.getByRole('textbox', { name: 'Сообщение AI Coach' });
    fireEvent.change(input, { target: { value: 'Что делать сегодня?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    await waitFor(() => expect(screen.getByText('Ответ с учётом квоты.')).toBeInTheDocument());
    expect(screen.getByTestId('ai-coach-quota')).toHaveAttribute('data-quota-remaining', '19');
  });

  it('keeps the input editable while disabling send at zero quota', async () => {
    mockBaseApi(quotaSnapshot(0));
    renderExperience();

    const indicator = await screen.findByTestId('ai-coach-quota');
    expect(indicator).toHaveAttribute('data-quota-limit', '20');
    expect(indicator).toHaveAttribute('data-quota-remaining', '0');
    expect(screen.getByText('Лимит исчерпан')).toBeInTheDocument();
    const input = screen.getByRole('textbox', { name: 'Сообщение AI Coach' });
    fireEvent.change(input, { target: { value: 'Мой вопрос пока останется в поле' } });
    expect(input).toHaveValue('Мой вопрос пока останется в поле');
    expect(screen.getByRole('button', { name: 'Отправить' })).toBeDisabled();
  });

  it('keeps send enabled for a provider rate limit without changing personal quota', async () => {
    mockBaseApi();
    apiMock.mockImplementation(async (path, options) => {
      if (path === '/api/v1/ai-coach/quota') return quotaSnapshot();
      if (path === '/api/v1/ai-coach/conversations' && options?.method === 'POST') {
        return conversation(12);
      }
      if (path === '/api/v1/ai-coach/conversations') return { items: [] };
      if (path === '/api/v1/ai-coach/memory') return memoryResponse();
      if (path === '/api/v1/ai-coach/conversations/12/messages') {
        const body = options?.body as { message: string };
        const userMessage = chatMessage(12, 'user', body.message, {
          status: 'failed',
          outcome: 'rate_limited',
          failure_category: 'rate_limit',
        });
        return {
          conversation_id: 12,
          user_message: userMessage,
          assistant_message: null,
          outcome: 'rate_limited',
          data_class: 'generic',
          answer: null,
          citations: [],
          limitations: [],
          safety_category: 'clear',
          failure_category: 'rate_limit',
          prompt_version: 'ai-coach-chat-v1',
          request_id: 'provider-rate-limit-request',
          quota: quotaSnapshot(),
          rate_limit_scope: 'provider',
          rate_limit_retry_after_seconds: 30,
        };
      }
      throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
    });
    renderExperience();

    const input = await screen.findByRole('textbox', { name: 'Сообщение AI Coach' });
    fireEvent.change(input, { target: { value: 'Вопрос во время лимита провайдера' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));

    await waitFor(() =>
      expect(screen.getByTestId('ai-coach-chat-failure')).toHaveTextContent(
        'AI Coach временно достиг лимита сервиса.',
      ),
    );
    expect(screen.getByRole('button', { name: 'Отправить' })).not.toBeDisabled();
    expect(screen.getByTestId('ai-coach-quota')).toHaveAttribute('data-quota-remaining', '20');
  });

  it('keeps a provider failure message distinct after conversation reload', async () => {
    const providerFailure = chatMessage(21, 'user', 'Проверка лимита провайдера', {
      status: 'failed',
      outcome: 'rate_limited',
      failure_category: 'rate_limit',
      rate_limit_scope: 'provider',
      rate_limit_retry_after_seconds: 23,
      limitations: ['Лимит AI Coach исчерпан. Попробуйте позже.'],
    });
    mockBaseApi();
    apiMock.mockImplementation(async (path, options) => {
      if (path === '/api/v1/ai-coach/quota') return quotaSnapshot();
      if (path === '/api/v1/ai-coach/conversations') {
        return { items: [{ ...conversation(21, [providerFailure]), message_count: 1 }] };
      }
      if (path === '/api/v1/ai-coach/conversations/21') return conversation(21, [providerFailure]);
      if (path === '/api/v1/ai-coach/memory') return memoryResponse();
      throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
    });
    renderExperience();

    expect(await screen.findByText('AI Coach временно достиг лимита сервиса.')).toBeInTheDocument();
    expect(screen.getByTestId('ai-coach-quota')).toHaveAttribute('data-quota-remaining', '20');
  });

  it('counts down locally and refreshes quota once at the server reset boundary', async () => {
    vi.useFakeTimers({ now: new Date('2026-09-15T12:00:00Z') });
    const resetAt = new Date(Date.now() + 65_000).toISOString();
    const nextResetAt = new Date(Date.now() + 86_400_000).toISOString();
    let currentQuota = quotaSnapshot(1, 5, resetAt);
    let quotaCalls = 0;
    apiMock.mockImplementation(async (path, options) => {
      if (path === '/api/v1/ai-coach/quota') {
        quotaCalls += 1;
        return currentQuota;
      }
      if (path === '/api/v1/ai-coach/conversations') return { items: [] };
      if (path === '/api/v1/ai-coach/memory') return memoryResponse();
      throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
    });
    renderExperience();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const indicator = screen.getByTestId('ai-coach-quota');
    expect(indicator).toHaveTextContent('2 мин');
    currentQuota = quotaSnapshot(5, 5, nextResetAt);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(quotaCalls).toBe(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000);
    });
    expect(quotaCalls).toBe(2);
    expect(indicator).toHaveAttribute('data-quota-remaining', '5');
  });

  it('sends an arbitrary question and renders safe text plus collapsed sources', async () => {
    let messages: AiCoachConversationMessage[] = [];
    const answer =
      'Проверенный текст. <img src="/secret"> [Материал](https://example.org/article) [Открыть материал](https://example.org/article) [Чужая ссылка](https://evil.example/secret)';
    apiMock.mockImplementation(async (path, options) => {
      if (path === '/api/v1/ai-coach/quota') return quotaSnapshot();
      if (path === '/api/v1/ai-coach/conversations' && options?.method === 'POST') {
        return conversation(1);
      }
      if (path === '/api/v1/ai-coach/conversations') {
        return {
          items: messages.length
            ? [{ ...conversation(1, messages), message_count: messages.length }]
            : [],
        };
      }
      if (path === '/api/v1/ai-coach/memory') return memoryResponse();
      if (path === '/api/v1/ai-coach/conversations/1/messages') {
        const body = options?.body as { message: string };
        messages = [
          chatMessage(1, 'user', body.message),
          chatMessage(2, 'assistant', answer, {
            citations: [
              {
                title: 'Материал',
                publisher: 'YFC',
                url: 'https://example.org/article',
                source_type: 'public_page',
              },
            ],
          }),
        ];
        return {
          conversation_id: 1,
          user_message: messages[0],
          assistant_message: messages[1],
          outcome: 'answer',
          data_class: 'generic',
          answer,
          citations: messages[1]?.citations ?? [],
          limitations: [],
          safety_category: 'clear',
          failure_category: null,
          prompt_version: 'ai-coach-chat-v1',
          request_id: 'request-1',
        };
      }
      if (path === '/api/v1/ai-coach/conversations/1') return conversation(1, messages);
      throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
    });
    renderExperience();
    const input = await screen.findByRole('textbox', { name: 'Сообщение AI Coach' });
    fireEvent.change(input, { target: { value: 'Сколько отдыхать между подходами?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));

    await waitFor(() => expect(screen.getByText(/Проверенный текст/)).toBeInTheDocument());
    expect(screen.getByText(/<img src="\/secret">/)).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Материал' })).toHaveLength(2);
    expect(screen.getAllByRole('link', { name: 'Материал' })[0]).toHaveAttribute(
      'href',
      'https://example.org/article',
    );
    expect(screen.getByText(/Чужая ссылка/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Чужая ссылка' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Открыть материал' })).not.toBeInTheDocument();
    expect(screen.getByText('Материалы ответа')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Полезно' })).toBeInTheDocument();
  });

  it('keeps a follow-up history visible after switching and reloading the conversation', async () => {
    const messages = [
      chatMessage(1, 'user', 'Как читать прогресс в YFC?'),
      chatMessage(2, 'assistant', 'Смотрите на несколько записей в динамике.'),
    ];
    mockBaseApi();
    apiMock.mockImplementation(async (path, options) => {
      if (path === '/api/v1/ai-coach/quota') return quotaSnapshot();
      if (path === '/api/v1/ai-coach/conversations') {
        return { items: [{ ...conversation(7, messages), message_count: messages.length }] };
      }
      if (path === '/api/v1/ai-coach/conversations/7') return conversation(7, messages);
      if (path === '/api/v1/ai-coach/memory') return memoryResponse();
      if (path === '/api/v1/ai-coach/conversations/7/messages' && options?.method === 'POST') {
        const body = options?.body as { message: string };
        messages.push(
          chatMessage(3, 'user', body.message),
          chatMessage(4, 'assistant', 'Уточнение принято.'),
        );
        return {
          conversation_id: 7,
          user_message: messages[2],
          assistant_message: messages[3],
          outcome: 'answer',
          data_class: 'generic',
          answer: 'Уточнение принято.',
          citations: [],
          limitations: [],
          safety_category: 'clear',
          failure_category: null,
          prompt_version: 'ai-coach-chat-v1',
          request_id: 'request-2',
        };
      }
      throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
    });
    renderExperience();
    expect(
      await screen.findByText('Смотрите на несколько записей в динамике.'),
    ).toBeInTheDocument();
    const input = screen.getByRole('textbox', { name: 'Сообщение AI Coach' });
    fireEvent.change(input, { target: { value: 'А если одна запись недостаточна?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    await waitFor(() => expect(screen.getByText('Уточнение принято.')).toBeInTheDocument());
    expect(screen.getAllByTestId('ai-coach-message-user')).toHaveLength(2);
    cleanup();
    renderExperience();
    await waitFor(() =>
      expect(screen.getAllByTestId('ai-coach-message-assistant')).toHaveLength(2),
    );
    expect(screen.getByText('А если одна запись недостаточна?')).toBeInTheDocument();
  });

  it('preserves typed text and shows a repair failure separately from safety refusal', async () => {
    const messages: AiCoachConversationMessage[] = [];
    apiMock.mockImplementation(async (path, options) => {
      if (path === '/api/v1/ai-coach/quota') return quotaSnapshot();
      if (path === '/api/v1/ai-coach/conversations' && options?.method === 'POST')
        return conversation(3);
      if (path === '/api/v1/ai-coach/conversations') {
        return {
          items: messages.length
            ? [{ ...conversation(3, messages), message_count: messages.length }]
            : [],
        };
      }
      if (path === '/api/v1/ai-coach/memory') return memoryResponse();
      if (path === '/api/v1/ai-coach/conversations/3') return conversation(3, messages);
      if (path === '/api/v1/ai-coach/conversations/3/messages') {
        const body = options?.body as { message: string };
        const userMessage = chatMessage(3, 'user', body.message, {
          status: 'failed',
          outcome: 'invalid_output',
          failure_category: 'repair_failed',
          limitations: ['Не удалось сформировать ответ. Повторить.'],
        });
        messages.push(userMessage);
        return {
          conversation_id: 3,
          user_message: userMessage,
          assistant_message: null,
          outcome: 'invalid_output',
          data_class: 'generic',
          answer: null,
          citations: [],
          limitations: ['Не удалось сформировать ответ. Повторить.'],
          safety_category: 'clear',
          failure_category: 'repair_failed',
          prompt_version: 'ai-coach-chat-v1',
          request_id: 'request-3',
        };
      }
      if (path === '/api/v1/ai-coach/conversations/3/messages/3/retry') {
        const userMessage = messages[0];
        if (!userMessage) throw new Error('missing failed user message');
        userMessage.status = 'complete';
        userMessage.outcome = null;
        userMessage.failure_category = null;
        userMessage.limitations = [];
        const assistantMessage = chatMessage(4, 'assistant', 'Ответ после повторной попытки.');
        messages.push(assistantMessage);
        return {
          conversation_id: 3,
          user_message: userMessage,
          assistant_message: assistantMessage,
          outcome: 'answer',
          data_class: 'generic',
          answer: assistantMessage.content,
          citations: [],
          limitations: [],
          safety_category: 'clear',
          failure_category: null,
          prompt_version: 'ai-coach-chat-v1',
          request_id: 'request-3-retry',
        };
      }
      throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
    });
    renderExperience();
    const input = await screen.findByRole('textbox', { name: 'Сообщение AI Coach' });
    fireEvent.change(input, { target: { value: 'Объясни мне этот материал.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    await waitFor(() => expect(screen.getByTestId('ai-coach-chat-failure')).toBeInTheDocument());
    expect(input).toHaveValue('Объясни мне этот материал.');
    expect(screen.getByText(/Не удалось сформировать ответ\. Повторить\./)).toBeInTheDocument();
    expect(screen.queryByText('На этот запрос нельзя ответить безопасно')).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: 'Повторить' }));
    await waitFor(() =>
      expect(screen.getByText('Ответ после повторной попытки.')).toBeInTheDocument(),
    );
    expect(screen.getAllByTestId('ai-coach-message-user')).toHaveLength(1);
    expect(screen.getAllByTestId('ai-coach-message-assistant')).toHaveLength(1);
  });

  it('requires explicit consent for personal prompts and keeps memory secondary', async () => {
    let consentStatus: 'granted' | 'revoked' = 'revoked';
    const messages: AiCoachConversationMessage[] = [];
    mockBaseApi();
    apiMock.mockImplementation(async (path, options) => {
      if (path === '/api/v1/ai-coach/quota') return quotaSnapshot();
      if (path === '/api/v1/ai-coach/conversations' && options?.method === 'POST') {
        return conversation(4);
      }
      if (path === '/api/v1/ai-coach/conversations') {
        return {
          items: messages.length
            ? [{ ...conversation(4, messages), message_count: messages.length }]
            : [],
        };
      }
      if (path === '/api/v1/ai-coach/memory') return memoryResponse();
      if (path === '/api/v1/ai-coach/consent' && options?.method === 'PUT') {
        consentStatus = 'granted';
        return consentResponse('granted');
      }
      if (path === '/api/v1/ai-coach/consent') return consentResponse(consentStatus);
      if (path === '/api/v1/ai-coach/conversations/4') return conversation(4, messages);
      if (path === '/api/v1/ai-coach/conversations/4/messages') {
        const body = options?.body as { message: string };
        messages.push(
          chatMessage(4, 'user', body.message),
          chatMessage(5, 'assistant', 'Для этого нужен отдельный доступ к сводке.', {
            outcome: 'consent_required',
          }),
        );
        return {
          conversation_id: 4,
          user_message: messages[0],
          assistant_message: messages[1],
          outcome: 'consent_required',
          data_class: 'personalized',
          answer: 'Для этого нужен отдельный доступ к сводке.',
          citations: [],
          limitations: [],
          safety_category: 'clear',
          failure_category: null,
          prompt_version: 'ai-coach-chat-v1',
          request_id: 'request-4',
        };
      }
      throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
    });
    renderExperience({ ...status, personal_available: true });
    const personalSettings = within(await screen.findByTestId('ai-coach-personal-settings'));
    await personalSettings.findByRole('button', { name: 'Включить' });
    fireEvent.click(screen.getByRole('button', { name: 'Что делать сегодня?' }));
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    await waitFor(() =>
      expect(screen.getByText('Для этого нужен отдельный доступ к сводке.')).toBeInTheDocument(),
    );
    expect(screen.getByText('Персонализация')).toBeInTheDocument();
    expect(screen.queryByText('Публичная помощь')).not.toBeInTheDocument();
    fireEvent.click(personalSettings.getByRole('button', { name: 'Включить' }));
    await waitFor(() => expect(consentStatus).toBe('granted'));
  });

  it('keeps the production settings card free of beta and debug labels', async () => {
    mockBaseApi();
    renderSettingsCard(status);
    await waitFor(() => expect(screen.getByTestId('ai-coach-entry-quota')).toBeInTheDocument());
    expect(screen.getByText('AI Coach', { exact: true })).toBeInTheDocument();
    expect(screen.getByTestId('ai-coach-profile-title')).toHaveClass(
      'ai-coach-settings-card__title',
    );
    expect(
      screen.getByTestId('ai-coach-profile-title').querySelector('[data-icon="ai-coach"]'),
    ).not.toBeNull();
    expect(screen.getByText('Помощник по тренировкам, питанию и прогрессу')).toBeInTheDocument();
    expect(screen.getByTestId('ai-coach-entry-quota')).toHaveTextContent('20 из 20 запросов');
    expect(screen.getByTestId('ai-coach-profile-link')).toHaveAttribute(
      'href',
      '/app?section=profile#profile-ai-coach',
    );
    expect(
      screen.getByTestId('ai-coach-profile-link').querySelector('[data-icon="ai-coach"]'),
    ).not.toBeNull();
    expect(
      screen
        .getByTestId('ai-coach-profile-link')
        .querySelector('.disclosure-icon [data-icon="disclosure-closed"]'),
    ).not.toBeNull();
    expect(screen.queryByText('Открыть AI Coach')).not.toBeInTheDocument();
    expect(screen.getByText('Помощник по тренировкам, питанию и прогрессу').tagName).toBe('SPAN');
    expect(screen.queryByTestId('ai-coach-experience')).not.toBeInTheDocument();
    expect(
      screen.queryByText(/внутренняя beta|внутренняя проверка|report_version/i),
    ).not.toBeInTheDocument();
  });

  it('opens one workspace, keeps the draft through settings and restores a minimized chat', async () => {
    mockBaseApi();
    window.localStorage.removeItem(AI_COACH_WORKSPACE_LAYOUT_KEY);
    renderWorkspace({ ...status, personal_available: true });

    fireEvent.click(await screen.findByTestId('ai-coach-profile-link'));
    const workspace = await screen.findByTestId('ai-coach-workspace');
    expect(screen.getAllByTestId('ai-coach-workspace')).toHaveLength(1);
    expect(workspace).toHaveClass('ai-coach-workspace--desktop');

    const input = await within(workspace).findByRole('textbox', { name: 'Сообщение AI Coach' });
    fireEvent.change(input, { target: { value: 'Черновик вопроса' } });
    fireEvent.click(within(workspace).getByRole('button', { name: 'Открыть настройки AI Coach' }));
    expect(within(workspace).getByTestId('ai-coach-workspace-settings')).toBeVisible();
    fireEvent.click(within(workspace).getByRole('button', { name: 'Вернуться в чат' }));
    expect(within(workspace).getByRole('textbox', { name: 'Сообщение AI Coach' })).toHaveValue(
      'Черновик вопроса',
    );

    fireEvent.click(within(workspace).getByRole('button', { name: 'Свернуть AI Coach' }));
    expect(workspace).toHaveAttribute('data-minimized', 'true');
    fireEvent.click(within(workspace).getByRole('button', { name: 'Открыть AI Coach' }));
    expect(within(workspace).getByRole('textbox', { name: 'Сообщение AI Coach' })).toHaveValue(
      'Черновик вопроса',
    );
  });

  it('clamps invalid stored geometry and exposes a resettable bounded layout', () => {
    const viewport = { width: 1280, height: 900 };
    window.localStorage.setItem(
      AI_COACH_WORKSPACE_LAYOUT_KEY,
      JSON.stringify({ version: 1, width: -20, height: 10_000, x: -1000, y: 10_000 }),
    );
    const stored = readAiCoachWorkspaceLayout(viewport);
    const layout = clampAiCoachWorkspaceLayout(
      { width: -20, height: 10_000, x: -1000, y: 10_000 },
      viewport,
    );
    expect(stored).toEqual(layout);
    expect(layout.width).toBeGreaterThanOrEqual(360);
    expect(layout.height).toBeLessThanOrEqual(800);
    expect(layout.x).toBeGreaterThanOrEqual(16);
    expect(layout.y).toBeLessThanOrEqual(796);
  });

  it.each([
    ['top', 0, -40, 500, 60, 420, 640],
    ['right', 40, 0, 500, 100, 460, 600],
    ['bottom', 0, 40, 500, 100, 420, 640],
    ['left', -40, 0, 460, 100, 460, 600],
    ['top-left', -40, -40, 460, 60, 460, 640],
    ['top-right', 40, -40, 500, 60, 460, 640],
    ['bottom-left', -40, 40, 460, 100, 460, 640],
    ['bottom-right', 40, 40, 500, 100, 460, 640],
  ] as const)(
    'resizes from the %s edge without moving the opposite anchor',
    (direction, deltaX, deltaY, x, y, width, height) => {
      const layout = resizeAiCoachWorkspaceLayout(
        { height: 600, minimized: false, width: 420, x: 500, y: 100 },
        direction,
        deltaX,
        deltaY,
        { width: 1280, height: 900 },
      );

      expect(layout).toMatchObject({ height, width, x, y });
    },
  );

  it('clamps every resize direction to viewport edges, minimums, maximums and the reserved bottom area', () => {
    const viewport = { width: 1280, height: 900 };
    const start = { height: 600, minimized: false, width: 420, x: 500, y: 100 };

    for (const direction of [
      'top',
      'right',
      'bottom',
      'left',
      'top-left',
      'top-right',
      'bottom-left',
      'bottom-right',
    ] as const) {
      const layout = resizeAiCoachWorkspaceLayout(
        start,
        direction,
        direction.includes('left') ? -10_000 : 10_000,
        direction.includes('top') ? -10_000 : 10_000,
        viewport,
      );
      expect(layout.width).toBeGreaterThanOrEqual(360);
      expect(layout.width).toBeLessThanOrEqual(560);
      expect(layout.height).toBeGreaterThanOrEqual(480);
      expect(layout.height).toBeLessThanOrEqual(800);
      expect(layout.x).toBeGreaterThanOrEqual(16);
      expect(layout.y).toBeGreaterThanOrEqual(16);
      expect(layout.x + layout.width).toBeLessThanOrEqual(viewport.width - 16);
      expect(layout.y + layout.height).toBeLessThanOrEqual(viewport.height - 88);
    }
  });

  it('shrinks the desktop workspace when the viewport height must preserve the FAB reserve', () => {
    const viewport = { width: 1280, height: 720 };
    const layout = clampAiCoachWorkspaceLayout({}, viewport);

    expect(layout.height).toBe(600);
    expect(layout.y).toBe(32);
    expect(layout.y + layout.height).toBeLessThanOrEqual(viewport.height - 88);
  });
});
