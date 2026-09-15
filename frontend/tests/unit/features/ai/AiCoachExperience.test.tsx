import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  AiCoachExperience,
  AiCoachSettingsCard,
  safeCoachUrl,
} from '../../../../src/features/ai/AiCoachExperience';
import { api } from '../../../../src/shared/api/client';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import type {
  AiCoachConversation,
  AiCoachConversationMessage,
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

function renderExperience(experienceStatus: AiCoachStatus = status) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <NavigationProvider>
          <AiCoachExperience entryPoint="profile" status={experienceStatus} />
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

function mockBaseApi() {
  apiMock.mockImplementation(async (path, options) => {
    if (path === '/api/v1/ai-coach/conversations') return { items: [] };
    if (path === '/api/v1/ai-coach/memory') return memoryResponse();
    if (path === '/api/v1/ai-coach/consent') return consentResponse();
    throw new Error(`unexpected path ${path} ${options?.method ?? 'GET'}`);
  });
}

afterEach(() => {
  cleanup();
  window.sessionStorage.removeItem('yfc:ai-coach:active-conversation');
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
    expect(screen.getByRole('button', { name: 'Новый чат' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Что делать сегодня?' })).toBeInTheDocument();
    expect(screen.queryByText('Публичная помощь')).not.toBeInTheDocument();
    expect(screen.queryByText('Моя сводка')).not.toBeInTheDocument();
    expect(screen.queryByText(/report_version|prompt_version|debug/i)).not.toBeInTheDocument();
  });

  it('sends an arbitrary question and renders safe text plus collapsed sources', async () => {
    let messages: AiCoachConversationMessage[] = [];
    const answer =
      'Проверенный текст. <img src="/secret"> [Материал](https://example.org/article) [Чужая ссылка](https://evil.example/secret)';
    apiMock.mockImplementation(async (path, options) => {
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
    expect(screen.getByText('Материалы ответа')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '👍' })).toBeInTheDocument();
  });

  it('keeps a follow-up history visible after switching and reloading the conversation', async () => {
    const messages = [
      chatMessage(1, 'user', 'Как читать прогресс в YFC?'),
      chatMessage(2, 'assistant', 'Смотрите на несколько записей в динамике.'),
    ];
    mockBaseApi();
    apiMock.mockImplementation(async (path, options) => {
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
    await screen.findByRole('button', { name: 'Разрешить персональные ответы' });
    fireEvent.click(screen.getByRole('button', { name: 'Что делать сегодня?' }));
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    await waitFor(() =>
      expect(screen.getByText('Для этого нужен отдельный доступ к сводке.')).toBeInTheDocument(),
    );
    expect(screen.getByText('Персональные ответы')).toBeInTheDocument();
    expect(screen.queryByText('Публичная помощь')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Разрешить персональные ответы' }));
    await waitFor(() => expect(consentStatus).toBe('granted'));
  });

  it('keeps the production settings card free of beta and debug labels', async () => {
    mockBaseApi();
    renderSettingsCard(status);
    await waitFor(() => expect(screen.getByTestId('ai-coach-experience')).toBeInTheDocument());
    expect(screen.getByText('AI Coach', { exact: true })).toBeInTheDocument();
    expect(
      screen.queryByText(/внутренняя beta|внутренняя проверка|report_version/i),
    ).not.toBeInTheDocument();
  });
});
