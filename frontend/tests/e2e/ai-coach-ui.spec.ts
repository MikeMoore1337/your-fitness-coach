import { expect, test, type Page, type Route } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { installPlatformApi } from './fixtures/platform-api';
import {
  expectNoHorizontalOverflow,
  expectTouchTargets,
  installTelegramHarness,
} from './fixtures/mobile-tma';

const evidenceDir = resolve(process.cwd(), '../.artifacts/runtime/tests/ai-coach-ui');

type MockMessageRole = 'user' | 'assistant';

interface MockMessage {
  id: number;
  role: MockMessageRole;
  content: string;
  status: 'complete' | 'failed';
  outcome: string | null;
  safety_category: string;
  failure_category: string | null;
  citations: Array<{
    title: string;
    publisher: string;
    url: string;
    source_type: string;
  }>;
  limitations: string[];
  created_at: string;
}

interface MockConversation {
  id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: MockMessage[];
}

const publicCitation = {
  title: 'Проверенный материал YFC',
  publisher: 'Your Fitness Coach',
  url: 'https://example.org/guide',
  source_type: 'public_page',
};

function makeMessage(
  id: number,
  role: MockMessageRole,
  content: string,
  overrides: Partial<MockMessage> = {},
): MockMessage {
  return {
    id,
    role,
    content,
    status: 'complete',
    outcome: role === 'assistant' ? 'answer' : null,
    safety_category: 'clear',
    failure_category: null,
    citations: role === 'assistant' ? [publicCitation] : [],
    limitations: [],
    created_at: '2026-09-14T12:00:00Z',
    ...overrides,
  };
}

function conversationSummary(conversation: MockConversation) {
  return {
    id: conversation.id,
    title: conversation.title,
    created_at: conversation.created_at,
    updated_at: conversation.updated_at,
    message_count: conversation.messages.length,
  };
}

function isPersonalQuestion(message: string): boolean {
  return /сегодня|мой|моя|мои|прогресс|питани/i.test(message);
}

async function installAiCoachApi(page: Page): Promise<void> {
  let nextConversationId = 1;
  let nextMessageId = 1;
  let quotaUsed = 0;
  let personalConsent: 'granted' | 'revoked' = 'revoked';
  const conversations = new Map<number, MockConversation>();
  const quotaResetAt = '2026-09-16T12:00:00+03:00';
  const quotaSnapshot = () => ({
    limit: 20,
    used: quotaUsed,
    remaining: Math.max(0, 20 - quotaUsed),
    reset_at: quotaResetAt,
    retry_after_seconds: 86_400,
    can_send: quotaUsed < 20,
  });

  await page.route('**/api/v1/ai-coach/**', async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path.endsWith('/status')) {
      return route.fulfill({
        json: { ui_enabled: true, generic_available: true, personal_available: true },
      });
    }

    if (path.endsWith('/quota')) {
      return route.fulfill({ json: quotaSnapshot() });
    }

    if (path.endsWith('/memory/consent')) {
      return route.fulfill({
        json: {
          status: 'revoked',
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
          purpose: 'Помощь AI Coach с контролем памяти',
          retention_notice: 'История чата и память хранятся отдельно.',
          max_items: 20,
          consent_source: 'test',
          items: [],
          granted_at: null,
          paused_at: null,
          revoked_at: null,
        },
      });
    }

    if (path.endsWith('/memory')) {
      return route.fulfill({
        json: {
          status: 'revoked',
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
          purpose: 'Отдельная память для подтверждённых предпочтений.',
          retention_notice: 'История чата и память хранятся отдельно.',
          max_items: 20,
          consent_source: 'test',
          items: [],
          granted_at: null,
          paused_at: null,
          revoked_at: null,
        },
      });
    }

    if (path.endsWith('/consent') && method === 'PUT') {
      personalConsent = 'granted';
      return route.fulfill({
        json: {
          status: personalConsent,
          scope: 'personal_readonly_tools_v1',
          consent_version: 'ai-coach-personal-v1',
          categories: ['personal_progress', 'training_history', 'nutrition_summary'],
          purpose: 'Персональные ответы на основе ограниченной сводки.',
          provider_name: 'groq',
          provider_policy_revision: 'test',
          retention_notice: 'История диалога и память разделены.',
          consent_source: 'test',
          granted_at: '2026-09-14T12:00:00Z',
          revoked_at: null,
        },
      });
    }

    if (path.endsWith('/consent')) {
      return route.fulfill({
        json: {
          status: personalConsent,
          scope: 'personal_readonly_tools_v1',
          consent_version: 'ai-coach-personal-v1',
          categories: ['personal_progress', 'training_history', 'nutrition_summary'],
          purpose: 'Персональные ответы на основе ограниченной сводки.',
          provider_name: 'groq',
          provider_policy_revision: 'test',
          retention_notice: 'История диалога и память разделены.',
          consent_source: 'test',
          granted_at: personalConsent === 'granted' ? '2026-09-14T12:00:00Z' : null,
          revoked_at: null,
        },
      });
    }

    if (path === '/api/v1/ai-coach/conversations' && method === 'GET') {
      return route.fulfill({
        json: { items: [...conversations.values()].map(conversationSummary) },
      });
    }

    if (path === '/api/v1/ai-coach/conversations' && method === 'POST') {
      const id = nextConversationId++;
      const conversation: MockConversation = {
        id,
        title: null,
        created_at: '2026-09-14T12:00:00Z',
        updated_at: '2026-09-14T12:00:00Z',
        messages: [],
      };
      conversations.set(id, conversation);
      return route.fulfill({ status: 201, json: conversation });
    }

    const conversationMatch = /^\/api\/v1\/ai-coach\/conversations\/(\d+)$/.exec(path);
    if (conversationMatch && method === 'GET') {
      const conversation = conversations.get(Number(conversationMatch[1]));
      if (!conversation) return route.fulfill({ status: 404, json: { detail: 'Not found' } });
      return route.fulfill({ json: conversation });
    }

    const retryMatch = /^\/api\/v1\/ai-coach\/conversations\/(\d+)\/messages\/(\d+)\/retry$/.exec(
      path,
    );
    if (retryMatch && method === 'POST') {
      const conversation = conversations.get(Number(retryMatch[1]));
      const userMessage = conversation?.messages.find(
        (item) =>
          item.id === Number(retryMatch[2]) && item.role === 'user' && item.status === 'failed',
      );
      if (!conversation || !userMessage) {
        return route.fulfill({ status: 409, json: { detail: 'Retry is no longer available' } });
      }
      userMessage.status = 'complete';
      userMessage.outcome = null;
      userMessage.failure_category = null;
      userMessage.limitations = [];
      const answer = 'Ответ после повторной попытки.';
      quotaUsed += 1;
      const assistantMessage = makeMessage(nextMessageId++, 'assistant', answer);
      conversation.messages.push(assistantMessage);
      conversation.updated_at = '2026-09-14T12:02:00Z';
      return route.fulfill({
        json: {
          conversation_id: conversation.id,
          user_message: userMessage,
          assistant_message: assistantMessage,
          outcome: 'answer',
          data_class: 'generic',
          answer,
          citations: [],
          limitations: [],
          safety_category: 'clear',
          failure_category: null,
          prompt_version: 'ai-coach-chat-v1',
          request_id: 'e2e-retry',
          quota: quotaSnapshot(),
        },
      });
    }

    const messageMatch = /^\/api\/v1\/ai-coach\/conversations\/(\d+)\/messages$/.exec(path);
    if (messageMatch && method === 'POST') {
      const conversation = conversations.get(Number(messageMatch[1]));
      if (!conversation) return route.fulfill({ status: 404, json: { detail: 'Not found' } });
      const body = request.postDataJSON() as { message?: unknown };
      const message = typeof body.message === 'string' ? body.message : '';
      const personal = isPersonalQuestion(message);
      const invalidOutput = /ошибк|проверки ошибки/i.test(message);
      const userMessage = makeMessage(nextMessageId++, 'user', message, {
        status: invalidOutput ? 'failed' : 'complete',
        outcome: invalidOutput ? 'invalid_output' : null,
        failure_category: invalidOutput ? 'repair_failed' : null,
        limitations: invalidOutput ? ['Не удалось сформировать ответ. Повторить.'] : [],
      });
      conversation.messages.push(userMessage);
      conversation.title ??= message.slice(0, 80);
      conversation.updated_at = '2026-09-14T12:01:00Z';

      if (personal && personalConsent !== 'granted') {
        const answer = 'Чтобы ответить по вашей ситуации, сначала разрешите персональные ответы.';
        const assistantMessage = makeMessage(nextMessageId++, 'assistant', answer, {
          outcome: 'consent_required',
          citations: [],
        });
        userMessage.status = 'complete';
        userMessage.outcome = 'consent_required';
        conversation.messages.push(assistantMessage);
        return route.fulfill({
          json: {
            conversation_id: conversation.id,
            user_message: userMessage,
            assistant_message: assistantMessage,
            outcome: 'consent_required',
            data_class: 'personalized',
            answer,
            citations: [],
            limitations: [],
            safety_category: 'clear',
            failure_category: null,
            prompt_version: 'ai-coach-chat-v1',
            request_id: 'e2e-consent-required',
          },
        });
      }

      if (invalidOutput) {
        return route.fulfill({
          json: {
            conversation_id: conversation.id,
            user_message: userMessage,
            assistant_message: null,
            outcome: 'invalid_output',
            data_class: personal ? 'personalized' : 'generic',
            answer: null,
            citations: [],
            limitations: ['Не удалось сформировать ответ. Повторить.'],
            safety_category: 'clear',
            failure_category: 'repair_failed',
            prompt_version: 'ai-coach-chat-v1',
            request_id: 'e2e-invalid-output',
          },
        });
      }

      const answer = personal
        ? 'По вашей текущей сводке смотрите на записанные тренировки и отмечайте ограничения данных.'
        : 'Проверенный ответ по материалам YFC. [Открыть материал](https://example.org/guide)';
      quotaUsed += 1;
      const assistantMessage = makeMessage(nextMessageId++, 'assistant', answer, {
        citations: [publicCitation],
      });
      conversation.messages.push(assistantMessage);
      return route.fulfill({
        json: {
          conversation_id: conversation.id,
          user_message: userMessage,
          assistant_message: assistantMessage,
          outcome: 'answer',
          data_class: personal ? 'personalized' : 'generic',
          answer,
          citations: [publicCitation],
          limitations: [
            personal
              ? 'Ответ основан только на разрешённом срезе ваших данных.'
              : 'Ответ основан на проверенном публичном материале YFC.',
          ],
          safety_category: 'clear',
          failure_category: null,
          prompt_version: 'ai-coach-chat-v1',
          request_id: `e2e-answer-${conversation.id}`,
          quota: quotaSnapshot(),
        },
      });
    }

    const feedbackMatch =
      /^\/api\/v1\/ai-coach\/conversations\/(\d+)\/messages\/(\d+)\/feedback$/.exec(path);
    if (feedbackMatch && method === 'POST') return route.fulfill({ status: 204, body: '' });

    return route.continue();
  });
}

async function openAiCoachSurface(
  page: Page,
  theme: 'light' | 'dark',
  viewport: { width: number; height: number },
  tma = false,
): Promise<void> {
  await page.setViewportSize(viewport);
  await page.addInitScript((selectedTheme) => {
    localStorage.setItem('app-theme', selectedTheme);
  }, theme);
  if (tma) await installTelegramHarness(page, { colorScheme: theme });
  await installPlatformApi(page, { browserSession: !tma, measurementHistory: 'many' });
  await installAiCoachApi(page);
  await page.goto(`/app?section=profile${tma ? '&tgWebAppPlatform=android' : ''}#profile-ai-coach`);
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
  await expect(page.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
  await expect(page.locator('#profile-ai-coach')).toHaveAttribute('open');
  await expect(page.getByTestId('ai-coach-experience')).toBeVisible();
}

test('AI Coach answers ordinary questions with an ordinary chat UI', async ({ browser }) => {
  mkdirSync(evidenceDir, { recursive: true });
  const surfaces = [
    {
      label: 'ai-coach-v2-desktop-dark-1440x900',
      theme: 'dark' as const,
      viewport: { width: 1440, height: 900 },
      tma: false,
    },
    {
      label: 'ai-coach-v2-mobile-light-390x844',
      theme: 'light' as const,
      viewport: { width: 390, height: 844 },
      tma: false,
    },
    {
      label: 'ai-coach-v2-tma-dark-390x844',
      theme: 'dark' as const,
      viewport: { width: 390, height: 844 },
      tma: true,
    },
  ];

  for (const surface of surfaces) {
    const context = await browser.newContext({
      viewport: surface.viewport,
      hasTouch: surface.viewport.width < 900,
    });
    const page = await context.newPage();
    await openAiCoachSurface(page, surface.theme, surface.viewport, surface.tma);

    const experience = page.getByTestId('ai-coach-experience');
    await expect(experience).toContainText('Чем помочь?');
    await expect(experience).not.toContainText(/Моя сводка|Публичная помощь|report_version|debug/i);
    const input = experience.getByRole('textbox', { name: 'Сообщение AI Coach' });
    await input.fill('Сколько отдыхать между подходами?');
    const submit = experience.getByRole('button', { name: 'Отправить' });
    await submit.scrollIntoViewIfNeeded();
    await submit.click();
    await expect(
      experience.getByText('Проверенный ответ по материалам YFC.', { exact: false }),
    ).toBeVisible();
    await expect(experience.getByTestId('ai-coach-quota')).toHaveAttribute(
      'data-quota-remaining',
      '19',
    );
    const sources = experience.locator('details.ai-coach-message__sources');
    await expect(sources).toBeVisible();
    await expect(sources).not.toHaveAttribute('open', '');
    await expect(experience.getByRole('link', { name: 'Открыть материал' })).toHaveAttribute(
      'href',
      'https://example.org/guide',
    );
    await experience.getByRole('button', { name: '👍' }).click();
    await expect(experience.getByRole('button', { name: '👍' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expectTouchTargets(experience.locator('button:visible'));
    await expectNoHorizontalOverflow(page);
    await page.screenshot({
      path: resolve(evidenceDir, `${surface.label}.png`),
      fullPage: true,
    });

    await context.close();
  }
});

test('AI Coach quota and composer fit the supported narrow mobile bounds', async ({ browser }) => {
  for (const width of [320, 430]) {
    const viewport = { width, height: 844 };
    const context = await browser.newContext({ viewport, hasTouch: true });
    const page = await context.newPage();
    await openAiCoachSurface(page, 'light', viewport);

    const experience = page.getByTestId('ai-coach-experience');
    await expect(experience.getByTestId('ai-coach-quota')).toHaveAttribute(
      'data-quota-remaining',
      '20',
    );
    await expectTouchTargets(experience.locator('button:visible'));
    await expectNoHorizontalOverflow(page);

    await context.close();
  }
});

test('AI Coach keeps follow-up history after reload and preserves failed draft', async ({
  browser,
}) => {
  const viewport = { width: 390, height: 844 };
  const context = await browser.newContext({ viewport, hasTouch: true });
  const page = await context.newPage();
  await openAiCoachSurface(page, 'light', viewport);
  const experience = page.getByTestId('ai-coach-experience');
  const input = experience.getByRole('textbox', { name: 'Сообщение AI Coach' });

  await input.fill('Сколько отдыхать между подходами?');
  const submit = experience.getByRole('button', { name: 'Отправить' });
  await submit.scrollIntoViewIfNeeded();
  await submit.click();
  await expect(
    experience.getByText('Проверенный ответ по материалам YFC.', { exact: false }),
  ).toBeVisible();
  await input.fill('А если одна запись недостаточна?');
  await submit.scrollIntoViewIfNeeded();
  await submit.click();
  await expect(experience.getByTestId('ai-coach-message-user')).toHaveCount(2);

  await page.reload();
  await expect(page.getByTestId('ai-coach-message-user')).toHaveCount(2);
  await expect(page.getByText('А если одна запись недостаточна?')).toBeVisible();
  await expect(page.getByTestId('ai-coach-quota')).toHaveAttribute('data-quota-remaining', '18');

  await input.fill('Проверка ошибки ответа');
  await page.getByRole('button', { name: 'Отправить' }).scrollIntoViewIfNeeded();
  await page.getByRole('button', { name: 'Отправить' }).click();
  await expect(page.getByTestId('ai-coach-chat-failure')).toContainText(
    'Не удалось сформировать ответ. Повторить.',
  );
  await expect(page.getByRole('textbox', { name: 'Сообщение AI Coach' })).toHaveValue(
    'Проверка ошибки ответа',
  );
  await page.getByRole('button', { name: 'Повторить' }).click();
  await expect(page.getByText('Ответ после повторной попытки.')).toBeVisible();
  await expect(page.getByTestId('ai-coach-message-user')).toHaveCount(3);
  await expect(page.getByTestId('ai-coach-experience')).not.toContainText(
    'На этот запрос нельзя ответить безопасно',
  );
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: resolve(evidenceDir, 'ai-coach-v2-mobile-failed-draft-390x844.png'),
    fullPage: true,
  });
  await context.close();
});

test('AI Coach separates personal consent from ordinary chat', async ({ browser }) => {
  const viewport = { width: 390, height: 844 };
  const context = await browser.newContext({ viewport, hasTouch: true });
  const page = await context.newPage();
  await openAiCoachSurface(page, 'light', viewport);
  const experience = page.getByTestId('ai-coach-experience');

  const consentDisclosure = experience.locator('details.ai-coach-chat__consent');
  await consentDisclosure.locator('summary').click();
  await expect(
    consentDisclosure.getByRole('button', { name: 'Разрешить персональные ответы' }),
  ).toBeVisible();

  await experience.getByRole('button', { name: 'Что делать сегодня?' }).click();
  await experience.getByRole('button', { name: 'Отправить' }).scrollIntoViewIfNeeded();
  await experience.getByRole('button', { name: 'Отправить' }).click();
  await expect(experience).toContainText('сначала разрешите персональные ответы');

  await consentDisclosure.getByRole('button', { name: 'Разрешить персональные ответы' }).click();
  await expect(consentDisclosure).toHaveCount(0);
  await experience.getByRole('button', { name: 'Что делать сегодня?' }).click();
  await experience.getByRole('button', { name: 'Отправить' }).scrollIntoViewIfNeeded();
  await experience.getByRole('button', { name: 'Отправить' }).click();
  await expect(experience).toContainText('По вашей текущей сводке');
  await expect(experience.locator('details.ai-coach-memory-disclosure')).toBeVisible();
  await expect(experience).not.toContainText(/AI Coach UI v|prompt_version|report_version/i);
  await expectTouchTargets(experience.locator('button:visible'));
  await expectNoHorizontalOverflow(page);
  await context.close();
});
