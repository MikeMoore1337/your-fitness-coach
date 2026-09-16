import { expect, test, type Locator, type Page, type Route } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { installPlatformApi } from './fixtures/platform-api';
import {
  expectNoHorizontalOverflow,
  expectTouchTargets,
  installTelegramHarness,
  TelegramHarness,
} from './fixtures/mobile-tma';

test.use({ serviceWorkers: 'block' });

const evidenceDir = process.env.YFC_TASK_EVIDENCE_DIR
  ? resolve(process.env.YFC_TASK_EVIDENCE_DIR)
  : resolve(process.cwd(), '../.artifacts/tasks/277/evidence/screenshots');

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

interface AiCoachApiHarness {
  releasePendingResponse: () => void;
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

async function installAiCoachApi(page: Page, initialQuotaUsed = 0): Promise<AiCoachApiHarness> {
  let nextConversationId = 1;
  let nextMessageId = 1;
  let quotaUsed = initialQuotaUsed;
  let personalConsent: 'granted' | 'revoked' = 'revoked';
  let releasePendingResponse: (() => void) | null = null;
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

    if (path === '/api/v1/ai-coach/conversations' && method === 'DELETE') {
      const deletedCount = conversations.size;
      conversations.clear();
      return route.fulfill({ json: { deleted_count: deletedCount } });
    }

    const conversationMatch = /^\/api\/v1\/ai-coach\/conversations\/(\d+)$/.exec(path);
    if (conversationMatch && method === 'GET') {
      const conversation = conversations.get(Number(conversationMatch[1]));
      if (!conversation) return route.fulfill({ status: 404, json: { detail: 'Not found' } });
      return route.fulfill({ json: conversation });
    }

    if (conversationMatch && method === 'DELETE') {
      const conversationId = Number(conversationMatch[1]);
      if (!conversations.delete(conversationId)) {
        return route.fulfill({ status: 404, json: { detail: 'Not found' } });
      }
      return route.fulfill({ status: 204, body: '' });
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

      if (message === 'Задержанный запрос') {
        await new Promise<void>((resolve) => {
          releasePendingResponse = resolve;
        });
        releasePendingResponse = null;
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

  return {
    releasePendingResponse: () => releasePendingResponse?.(),
  };
}

async function openAiCoachSurface(
  page: Page,
  theme: 'light' | 'dark',
  viewport: { width: number; height: number },
  tma = false,
  deepLink = false,
  initialQuotaUsed = 0,
): Promise<AiCoachApiHarness> {
  await page.setViewportSize(viewport);
  await page.addInitScript((selectedTheme) => {
    localStorage.setItem('app-theme', selectedTheme);
  }, theme);
  if (tma) await installTelegramHarness(page, { colorScheme: theme });
  await installPlatformApi(page, { browserSession: !tma, measurementHistory: 'many' });
  const aiCoachApi = await installAiCoachApi(page, initialQuotaUsed);
  await page.goto(
    `/app?section=profile${tma ? '&tgWebAppPlatform=android' : ''}${deepLink ? '#profile-ai-coach' : ''}`,
  );
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
  await expect(page.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
  await expect(page.getByTestId('ai-coach-entry-profile')).toBeVisible();
  if (deepLink) await expect(page.getByTestId('ai-coach-workspace')).toBeVisible();
  return aiCoachApi;
}

async function openWorkspace(page: Page): Promise<Locator> {
  const workspace = page.getByTestId('ai-coach-workspace');
  if ((await workspace.count()) === 0) {
    await page
      .getByTestId('ai-coach-entry-profile')
      .getByRole('link', { name: 'Открыть AI Coach' })
      .click();
  }
  await expect(workspace).toBeVisible();
  await expect(workspace.getByTestId('ai-coach-experience')).toBeVisible();
  await expect(workspace.getByRole('textbox', { name: 'Сообщение AI Coach' })).toBeVisible();
  return workspace;
}

async function historyControlCheck(workspace: Locator): Promise<void> {
  const history = workspace.getByTestId('ai-coach-history-control');
  await history.click();
  await expect(workspace.getByTestId('ai-coach-history-view')).toBeVisible();
  await expect(workspace.getByRole('button', { name: 'Назад в чат' })).toBeVisible();
  await workspace.getByRole('button', { name: 'Назад в чат' }).click();
}

async function captureEvidence(page: Page, label: string): Promise<void> {
  mkdirSync(evidenceDir, { recursive: true });
  await page.screenshot({ path: resolve(evidenceDir, `${label}.png`), fullPage: false });
}

test('AI Coach is one floating desktop workspace with continuity and bounded controls', async ({
  browser,
}) => {
  const viewport = { width: 1440, height: 900 };
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  await openAiCoachSurface(page, 'dark', viewport);

  const entry = page.getByTestId('ai-coach-entry-profile');
  await expect(entry).not.toContainText('Сообщение AI Coach');
  await expect(page.getByTestId('ai-coach-entry-quota')).toContainText('20 из 20 запросов');
  const profileTitle = page.getByTestId('ai-coach-profile-title');
  await expect(profileTitle).toHaveCSS('display', 'inline-flex');
  await expect(profileTitle).toHaveCSS('align-items', 'center');
  await expect(profileTitle.locator('[data-icon="ai-coach"]')).toHaveCount(1);
  await expect(page.getByTestId('ai-coach-experience')).toHaveCount(0);
  await entry.scrollIntoViewIfNeeded();
  await captureEvidence(page, 'ai-coach-desktop-profile-entry');
  const workspace = await openWorkspace(page);
  await expect(workspace).toHaveClass(/ai-coach-workspace--desktop/);
  await expect(workspace.getByRole('button', { name: 'Закрыть AI Coach' })).toBeFocused();
  await expect(workspace.getByTestId('ai-coach-workspace-status')).toContainText(
    'Готов · 20 из 20',
  );
  await expect(workspace.getByRole('button', { name: 'Свернуть AI Coach' })).toHaveAttribute(
    'title',
    'Свернуть AI Coach',
  );
  await expect(
    workspace.getByRole('button', { name: 'Открыть настройки AI Coach' }),
  ).toHaveAttribute('title', 'Настройки AI Coach');
  const initialBox = await workspace.boundingBox();
  expect(initialBox).not.toBeNull();
  expect(initialBox?.width).toBeGreaterThanOrEqual(420);
  expect(initialBox?.width).toBeLessThanOrEqual(480);
  expect(initialBox?.height).toBeGreaterThanOrEqual(600);
  expect(initialBox?.height).toBeLessThanOrEqual(720);
  await captureEvidence(page, 'ai-coach-desktop-empty');
  await captureEvidence(page, 'ai-coach-desktop-default');

  const dragHandle = workspace.locator('.ai-coach-workspace__drag-handle');
  const dragBox = await dragHandle.boundingBox();
  if (!dragBox || !initialBox) throw new Error('AI Coach drag handle has no geometry');
  await page.mouse.move(dragBox.x + dragBox.width / 2, dragBox.y + dragBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(dragBox.x + dragBox.width / 2 - 180, dragBox.y + dragBox.height / 2 - 100, {
    steps: 5,
  });
  await page.mouse.up();
  await expect
    .poll(async () => (await workspace.boundingBox())?.x ?? initialBox.x)
    .toBeLessThan(initialBox.x - 40);
  const movedBox = await workspace.boundingBox();
  expect(movedBox?.x).toBeGreaterThanOrEqual(16);
  expect(movedBox?.y).toBeGreaterThanOrEqual(16);
  await captureEvidence(page, 'ai-coach-desktop-moved');

  await page
    .locator('#appBottomNav .app-bottom-nav__primary')
    .getByRole('link', { name: 'Питание' })
    .click();
  await expect(page).toHaveURL(/section=nutrition/);
  await expect(workspace).toBeVisible();

  const experience = workspace.getByTestId('ai-coach-experience');
  const input = workspace.getByRole('textbox', { name: 'Сообщение AI Coach' });
  await expect(experience).toContainText('Чем помочь?');
  await expect(experience.locator('.ai-coach-chat__quick-prompts button')).toHaveCount(4);
  await expect(experience).not.toContainText('Диалог');
  await expect(experience).not.toContainText('Новый чат');
  await input.fill('Сколько отдыхать между подходами?');
  await input.focus();
  const sendButton = workspace.getByRole('button', { name: 'Отправить' });
  await expect(sendButton).toBeEnabled();
  await expect(sendButton.locator('[data-icon="arrow-up"]')).toBeVisible();
  const composer = workspace.locator('.ai-coach-chat__composer');
  await expect(composer).toHaveCSS('border-top-color', 'rgb(178, 245, 32)');
  await expect(composer).toHaveCSS('box-shadow', 'none');
  await expect(input).toHaveCSS('border-top-width', '0px');
  await expect(input).toHaveCSS('box-shadow', 'none');
  await captureEvidence(page, 'ai-coach-desktop-composer-text');
  await input.press('Shift+Enter');
  await input.type('Приведите короткий пример.');
  await expect(input).toHaveValue('Сколько отдыхать между подходами?\nПриведите короткий пример.');
  await expect(experience.locator('.ai-coach-chat__composer-count')).toHaveCount(0);
  await captureEvidence(page, 'ai-coach-desktop-composer-multiline');
  await input.fill('Сколько отдыхать между подходами?');
  await input.press('Enter');
  await expect(
    experience.getByText('Проверенный ответ по материалам YFC.', { exact: false }),
  ).toBeVisible();
  await expect(experience.locator('.ai-coach-chat__quick-prompts')).toHaveCount(0);
  await expect(experience).not.toContainText('Чем помочь?');
  await expect(experience.locator('.ai-coach-chat__toolbar')).toHaveCount(0);
  await expect(workspace.getByTestId('ai-coach-history-control')).toBeVisible();
  await expect(workspace.getByTestId('ai-coach-history-control')).toHaveAttribute(
    'aria-label',
    'История',
  );
  const messageArea = workspace.locator('.ai-coach-chat__messages');
  const workspaceAfterAnswer = await workspace.boundingBox();
  const composerBox = await composer.boundingBox();
  const messageAreaBox = await messageArea.boundingBox();
  if (!workspaceAfterAnswer || !composerBox || !messageAreaBox) {
    throw new Error('AI Coach chat regions have no geometry');
  }
  expect(composerBox.y + composerBox.height).toBeGreaterThanOrEqual(
    workspaceAfterAnswer.y + workspaceAfterAnswer.height - 2,
  );
  expect(composerBox.y + composerBox.height).toBeLessThanOrEqual(
    workspaceAfterAnswer.y + workspaceAfterAnswer.height,
  );
  expect(messageAreaBox.y + messageAreaBox.height).toBeLessThanOrEqual(composerBox.y + 1);
  await expect(messageArea).toHaveCSS('overflow-y', 'auto');
  await expect(workspace.locator('.ai-coach-workspace__body')).toHaveCSS('overflow', 'hidden');
  await expect(composer).not.toContainText('Сброс через');
  await captureEvidence(page, 'ai-coach-desktop-active');
  const sources = experience.locator('details.ai-coach-message__sources');
  await expect(sources).toBeVisible();
  await expect(sources).not.toHaveAttribute('open', '');
  await expect(experience.getByRole('link', { name: 'Открыть материал' })).toHaveCount(0);
  await historyControlCheck(workspace);
  await experience.getByRole('button', { name: 'Полезно', exact: true }).click();
  await expect(experience.getByRole('button', { name: 'Полезно', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  const beforeResize = await workspace.boundingBox();
  const resizeHandle = workspace.getByTestId('ai-coach-workspace-resize');
  const resizeBox = await resizeHandle.boundingBox();
  if (!beforeResize || !resizeBox) throw new Error('AI Coach resize handle has no geometry');
  await page.mouse.move(resizeBox.x + resizeBox.width / 2, resizeBox.y + resizeBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    resizeBox.x + resizeBox.width / 2 + 48,
    resizeBox.y + resizeBox.height / 2 + 48,
    {
      steps: 4,
    },
  );
  await page.mouse.up();
  await expect
    .poll(async () => (await workspace.boundingBox())?.width ?? beforeResize.width)
    .toBeGreaterThan(beforeResize.width + 20);
  const persistedBox = await workspace.boundingBox();
  const resizedComposerBox = await composer.boundingBox();
  if (!resizedComposerBox || !persistedBox) throw new Error('Resized AI Coach has no geometry');
  expect(resizedComposerBox.y + resizedComposerBox.height).toBeGreaterThanOrEqual(
    persistedBox.y + persistedBox.height - 2,
  );
  expect(resizedComposerBox.y + resizedComposerBox.height).toBeLessThanOrEqual(
    persistedBox.y + persistedBox.height,
  );
  await captureEvidence(page, 'ai-coach-desktop-resized');

  await input.fill('Как оценивать восстановление после тренировки?');
  await workspace.getByRole('button', { name: 'Отправить' }).click();
  await expect(experience.getByTestId('ai-coach-message-user')).toHaveCount(2);
  await input.fill('Как не пропускать тренировки?');
  await workspace.getByRole('button', { name: 'Отправить' }).click();
  await expect(experience.getByTestId('ai-coach-message-user')).toHaveCount(3);
  await expect
    .poll(() => messageArea.evaluate((element) => element.scrollHeight > element.clientHeight))
    .toBe(true);
  await captureEvidence(page, 'ai-coach-desktop-long-conversation');

  await workspace.getByRole('button', { name: 'Свернуть AI Coach' }).click();
  await expect(workspace).toHaveAttribute('data-minimized', 'true');
  await expect(workspace.locator('.ai-coach-workspace__body')).toHaveAttribute('hidden', '');
  await expect(workspace.locator('.ai-coach-workspace__drag-handle .eyebrow')).toBeHidden();
  await expect(workspace.getByTestId('ai-coach-workspace-status')).toBeHidden();
  const minimizedBox = await workspace.boundingBox();
  if (!minimizedBox) throw new Error('Minimized AI Coach has no geometry');
  expect(minimizedBox.width).toBeGreaterThanOrEqual(120);
  expect(minimizedBox.width).toBeLessThanOrEqual(240);
  expect(1440 - (minimizedBox.x + minimizedBox.width)).toBeGreaterThanOrEqual(29);
  const addBox = await page.getByTestId('quick-add-trigger').boundingBox();
  if (!addBox) throw new Error('Quick Add has no geometry');
  expect(addBox.y).toBeGreaterThanOrEqual(minimizedBox.y + minimizedBox.height + 8);
  await expect(workspace.getByTestId('ai-coach-workspace-restore')).toContainText('AI Coach');
  await expect(workspace.getByTestId('ai-coach-workspace-restore')).toHaveCSS(
    'align-items',
    'center',
  );
  await expect(workspace.getByTestId('ai-coach-workspace-restore')).toHaveAttribute(
    'aria-label',
    'Открыть AI Coach',
  );
  await expect(workspace.getByRole('button', { name: 'Закрыть AI Coach' })).toHaveCount(0);
  await expect(workspace.getByTestId('ai-coach-workspace-restore')).not.toContainText(
    'Восстановить',
  );
  await captureEvidence(page, 'ai-coach-desktop-minimized');
  await page.locator('#appAccountProfileLink').click();
  await expect(page).toHaveURL(/section=profile/);
  await expect(workspace).toHaveAttribute('data-minimized', 'true');
  await page
    .getByTestId('ai-coach-entry-profile')
    .getByRole('link', { name: 'Открыть AI Coach' })
    .click();
  await expect(workspace).not.toHaveAttribute('data-minimized', 'true');
  await expect(workspace.getByTestId('ai-coach-message-user')).toHaveCount(3);

  await workspace.getByRole('button', { name: 'Открыть настройки AI Coach' }).click();
  const settings = workspace.getByTestId('ai-coach-workspace-settings');
  await expect(settings).toBeVisible();
  await expect(settings.getByTestId('ai-coach-personal-settings')).toBeVisible();
  await expect(settings.getByTestId('ai-coach-memory')).toBeVisible();
  await expect(settings).toContainText('Положение окна');
  await expect(settings).toHaveCSS('overflow-y', 'auto');
  await expect(settings).toContainText('Персонализация');
  await expect(settings).not.toContainText('Канонические');
  await expect(settings).not.toContainText('долговременной');
  await expect(settings.locator('.ai-coach-memory__notice')).not.toHaveAttribute('open', '');
  await captureEvidence(page, 'ai-coach-desktop-settings');
  await workspace.getByRole('button', { name: 'Вернуться в чат' }).click();
  await expect(
    workspace.getByText('Проверенный ответ по материалам YFC.', { exact: false }).first(),
  ).toBeVisible();
  await expectTouchTargets(workspace.locator('button:visible'));

  await workspace.getByRole('button', { name: 'Закрыть AI Coach' }).click();
  await expect(workspace).toHaveCount(0);
  await page.getByTestId('quick-add-trigger').click();
  await page.getByTestId('quick-add-sheet').getByRole('link', { name: 'Открыть AI Coach' }).click();
  await expect(workspace).toBeVisible();
  await workspace.getByRole('button', { name: 'Закрыть AI Coach' }).click();
  await expect(workspace).toHaveCount(0);
  await page.goto('/app?section=profile');
  await page.reload();
  await expect(page.getByTestId('ai-coach-entry-profile')).toBeVisible();
  const reopenedWorkspace = await openWorkspace(page);
  if (persistedBox) {
    const reloadedBox = await reopenedWorkspace.boundingBox();
    expect(reloadedBox?.x).toBeCloseTo(persistedBox.x, 0);
    expect(reloadedBox?.y).toBeCloseTo(persistedBox.y, 0);
  }
  await expect(reopenedWorkspace.getByTestId('ai-coach-message-user')).toHaveCount(3);
  await reopenedWorkspace.getByRole('button', { name: 'Открыть настройки AI Coach' }).click();
  await reopenedWorkspace
    .getByTestId('ai-coach-workspace-settings')
    .getByRole('button', { name: 'Сбросить' })
    .click();
  await context.close();
});

test('AI Coach history supports switching, scoped deletion, and clear-all confirmations', async ({
  browser,
}) => {
  for (const [label, viewport, hasTouch] of [
    ['desktop', { width: 1440, height: 900 }, false],
    ['mobile-light', { width: 390, height: 844 }, true],
  ] as const) {
    const context = await browser.newContext({ viewport, hasTouch });
    const page = await context.newPage();
    await openAiCoachSurface(page, 'light', viewport);
    const workspace = await openWorkspace(page);
    const input = workspace.getByRole('textbox', { name: 'Сообщение AI Coach' });
    const prefix = label === 'desktop' ? 'ai-coach-desktop' : 'ai-coach-mobile-light';

    const sendMessage = async (message: string) => {
      await input.fill(message);
      await input.press('Enter');
      await expect(
        workspace.getByText('Проверенный ответ по материалам YFC.', { exact: false }),
      ).toBeVisible();
    };

    await sendMessage('Сколько отдыхать между подходами?');
    await workspace.getByTestId('ai-coach-history-control').click();
    await expect(workspace.getByTestId('ai-coach-history-view')).toBeVisible();
    await expect(workspace.getByTestId('ai-coach-history-item-1')).toContainText(
      'Сколько отдыхать между подходами?',
    );
    await workspace.getByTestId('ai-coach-history-new-chat').click();
    await sendMessage('Как оценивать восстановление?');

    await workspace.getByTestId('ai-coach-history-control').click();
    const history = workspace.getByTestId('ai-coach-history-view');
    await expect(history.getByTestId('ai-coach-history-item-1')).toBeVisible();
    await expect(history.getByTestId('ai-coach-history-item-2')).toBeVisible();
    await expect(input).toHaveCount(0);
    await expect(history.locator('.ai-coach-history__item-title')).toHaveText([
      'Сколько отдыхать между подходами?',
      'Как оценивать восстановление?',
    ]);
    await expect(
      history.getByTestId('ai-coach-history-item-1').locator('.ai-coach-history__item-open'),
    ).toHaveCSS('text-align', 'left');
    await captureEvidence(page, `${prefix}-history`);

    await history
      .getByTestId('ai-coach-history-item-1')
      .locator('.ai-coach-history__item-open')
      .click();
    await expect(workspace.getByTestId('ai-coach-history-view')).toHaveCount(0);
    await expect(
      workspace.getByText('Сколько отдыхать между подходами?', { exact: true }),
    ).toBeVisible();
    await sendMessage('Как выбрать паузу после тяжёлого подхода?');

    await workspace.getByTestId('ai-coach-history-control').click();
    const historyAfterSwitch = workspace.getByTestId('ai-coach-history-view');
    const nonActiveItem = historyAfterSwitch.getByTestId('ai-coach-history-item-2');
    await nonActiveItem.locator('summary').click();
    await expect(nonActiveItem.getByRole('button', { name: 'Удалить чат' })).toBeVisible();
    await captureEvidence(page, `${prefix}-history-menu`);
    await nonActiveItem.getByRole('button', { name: 'Удалить чат' }).click();
    const confirmation = page.locator('.modal[role="dialog"]');
    await expect(confirmation).toBeVisible();
    await expect(confirmation).toContainText('Удалить этот чат?');
    await expect(confirmation).toContainText('Память AI Coach не изменится.');
    await expect(confirmation.locator('.modal__panel')).toHaveCSS('opacity', '1');
    await captureEvidence(page, `${prefix}-history-delete-confirmation`);
    await confirmation.getByRole('button', { name: 'Удалить', exact: true }).click();
    await expect(historyAfterSwitch.getByTestId('ai-coach-history-item-2')).toHaveCount(0);
    await expect(historyAfterSwitch.getByTestId('ai-coach-history-item-1')).toBeVisible();
    await historyAfterSwitch.getByRole('button', { name: 'Назад в чат' }).click();
    await expect(
      workspace.getByText('Как выбрать паузу после тяжёлого подхода?', { exact: true }),
    ).toBeVisible();

    await workspace.getByTestId('ai-coach-history-control').click();
    const activeHistory = workspace.getByTestId('ai-coach-history-view');
    const activeItem = activeHistory.getByTestId('ai-coach-history-item-1');
    await activeItem.locator('summary').click();
    await activeItem.getByRole('button', { name: 'Удалить чат' }).click();
    await expect(confirmation).toContainText('Удалить этот чат?');
    await confirmation.getByRole('button', { name: 'Удалить', exact: true }).click();
    await expect(workspace.getByTestId('ai-coach-history-view')).toHaveCount(0);
    await expect(workspace.getByTestId('ai-coach-chat-empty')).toBeVisible();
    await expect(input).toHaveValue('');

    await sendMessage('Как выбрать интенсивность разминки?');
    await workspace.getByTestId('ai-coach-history-control').click();
    await workspace.getByTestId('ai-coach-history-new-chat').click();
    await sendMessage('Как распределить подходы в тренировке?');
    await workspace.getByTestId('ai-coach-history-control').click();
    const historyBeforeClear = workspace.getByTestId('ai-coach-history-view');
    await expect(historyBeforeClear.getByTestId('ai-coach-history-item-3')).toBeVisible();
    await expect(historyBeforeClear.getByTestId('ai-coach-history-item-4')).toBeVisible();
    await expect(historyBeforeClear.locator('.ai-coach-history__footer')).toHaveCount(0);
    await expect(historyBeforeClear.getByTestId('ai-coach-history-clear')).not.toBeVisible();
    await expect(
      historyBeforeClear
        .getByTestId('ai-coach-history-item-3')
        .locator('.ai-coach-history__item-open'),
    ).toHaveCSS('text-align', 'left');
    await historyBeforeClear.getByTestId('ai-coach-history-menu').locator('summary').click();
    const clearHistoryButton = historyBeforeClear.getByTestId('ai-coach-history-clear');
    await expect(clearHistoryButton).toBeVisible();
    await clearHistoryButton.click();
    await expect(confirmation).toBeVisible();
    await expect(confirmation).toContainText('Удалить всю историю чатов?');
    await expect(confirmation).toContainText('персонализация не изменятся.');
    await expect(confirmation.locator('.modal__panel')).toHaveCSS('opacity', '1');
    await captureEvidence(page, `${prefix}-history-clear-confirmation`);
    await confirmation.getByRole('button', { name: 'Отмена', exact: true }).click();
    await expect(historyBeforeClear.getByTestId('ai-coach-history-item-3')).toBeVisible();
    await historyBeforeClear.getByTestId('ai-coach-history-menu').locator('summary').click();
    await historyBeforeClear.getByTestId('ai-coach-history-clear').click();
    await expect(confirmation).toContainText('Удалить всю историю чатов?');
    await confirmation.getByRole('button', { name: 'Удалить всё', exact: true }).click();
    await expect(workspace.getByTestId('ai-coach-history-empty')).toBeVisible();
    await expect(workspace.locator('[data-testid^="ai-coach-history-item-"]')).toHaveCount(0);
    await expect(workspace.getByTestId('ai-coach-history-new-chat')).toHaveCount(1);
    await expect(workspace.getByTestId('ai-coach-history-new-chat-empty')).toHaveCount(0);
    await expect(input).toHaveCount(0);
    await captureEvidence(page, `${prefix}-history-empty`);
    if (hasTouch) await expectTouchTargets(historyBeforeClear.locator('button:visible'));

    await workspace.getByRole('button', { name: 'Назад в чат' }).click();
    await workspace.getByRole('button', { name: 'Открыть настройки AI Coach' }).click();
    await expect(workspace.getByTestId('ai-coach-memory')).toBeVisible();
    await expect(workspace.getByTestId('ai-coach-personal-settings')).toBeVisible();
    await context.close();
  }
});

test('AI Coach history remains touch-friendly in dark TMA and uses the shared confirmation', async ({
  browser,
}) => {
  const viewport = { width: 390, height: 844 };
  const context = await browser.newContext({ viewport, hasTouch: true });
  const page = await context.newPage();
  await openAiCoachSurface(page, 'dark', viewport, true);
  const workspace = await openWorkspace(page);
  const input = workspace.getByRole('textbox', { name: 'Сообщение AI Coach' });
  await input.fill('Как проверить восстановление после тренировки?');
  await input.press('Enter');
  await expect(
    workspace.getByText('Проверенный ответ по материалам YFC.', { exact: false }),
  ).toBeVisible();
  await workspace.getByTestId('ai-coach-history-control').click();
  const history = workspace.getByTestId('ai-coach-history-view');
  await expect(history.getByTestId('ai-coach-history-item-1')).toBeVisible();
  await expect(history.locator('.ai-coach-history__item-title')).toHaveText(
    'Как проверить восстановление после тренировки?',
  );
  await expect(
    history.getByTestId('ai-coach-history-item-1').locator('.ai-coach-history__item-open'),
  ).toHaveCSS('text-align', 'left');
  await expect(input).toHaveCount(0);
  await captureEvidence(page, 'ai-coach-tma-dark-history');
  await history.getByTestId('ai-coach-history-item-1').locator('summary').click();
  await expect(
    history.getByTestId('ai-coach-history-item-1').getByRole('button', { name: 'Удалить чат' }),
  ).toBeVisible();
  await expectTouchTargets(history.locator('button:visible'));
  await history
    .getByTestId('ai-coach-history-item-1')
    .getByRole('button', { name: 'Удалить чат' })
    .click();
  const confirmation = page.locator('.modal[role="dialog"]');
  await expect(confirmation).toBeVisible();
  await expect(confirmation).toContainText('Удалить этот чат?');
  await expect(confirmation.locator('.modal__panel')).toHaveCSS('opacity', '1');
  await expect(confirmation.locator('.modal__backdrop')).toHaveCSS(
    'background-color',
    'rgba(0, 0, 0, 0.55)',
  );
  await captureEvidence(page, 'ai-coach-tma-dark-history-confirmation');
  await confirmation.getByRole('button', { name: 'Удалить', exact: true }).click();
  await expect(workspace.getByTestId('ai-coach-chat-empty')).toBeVisible();
  await context.close();
});

test('AI Coach exhausted quota keeps the composer available with a compact reset countdown', async ({
  browser,
}) => {
  for (const [label, viewport] of [
    ['desktop', { width: 1440, height: 900 }],
    ['mobile', { width: 390, height: 844 }],
  ] as const) {
    const context = await browser.newContext({ viewport, hasTouch: label === 'mobile' });
    const page = await context.newPage();
    await openAiCoachSurface(page, 'light', viewport, false, true, 20);

    const workspace = await openWorkspace(page);
    await expect(workspace.getByTestId('ai-coach-workspace-status')).toContainText(
      'Лимит исчерпан',
    );
    await expect(workspace.getByTestId('ai-coach-quota')).toHaveAttribute(
      'data-quota-remaining',
      '0',
    );
    const input = workspace.getByRole('textbox', { name: 'Сообщение AI Coach' });
    await expect(workspace.getByRole('button', { name: 'Отправить' })).toBeDisabled();
    await input.fill('Вопрос при исчерпанной квоте');
    await expect(workspace.getByTestId('ai-coach-quota-reset')).toContainText('Сброс через');
    await expect(workspace.getByRole('button', { name: 'Отправить' })).toBeDisabled();
    await captureEvidence(page, `ai-coach-${label}-quota-exhausted`);
    await context.close();
  }
});

test('AI Coach quota tone follows the server ratio at the low boundary', async ({ browser }) => {
  for (const [label, viewport] of [
    ['desktop', { width: 1440, height: 900 }],
    ['mobile', { width: 390, height: 844 }],
  ] as const) {
    const context = await browser.newContext({ viewport, hasTouch: label === 'mobile' });
    const page = await context.newPage();
    await openAiCoachSurface(page, 'light', viewport, false, true, 14);

    const workspace = await openWorkspace(page);
    const status = workspace.getByTestId('ai-coach-workspace-status');
    await expect(status).toHaveClass(/ai-coach-workspace__status--low/);
    await expect(status).toContainText('Осталось 6 из 20');
    await expect(workspace.getByTestId('ai-coach-quota')).toHaveAttribute(
      'data-quota-remaining',
      '6',
    );
    await expect(workspace.getByRole('button', { name: 'Отправить' })).toBeDisabled();
    const input = workspace.getByRole('textbox', { name: 'Сообщение AI Coach' });
    await input.fill('Вопрос при низком лимите');
    await expect(workspace.getByRole('button', { name: 'Отправить' })).toBeEnabled();
    await expect(page.getByTestId('ai-coach-entry-quota')).toHaveClass(
      /ai-coach-entry__quota--low/,
    );
    await expect(page.getByTestId('ai-coach-entry-quota')).toContainText('6 из 20 запросов');
    await captureEvidence(page, `ai-coach-${label}-quota-low`);
    await context.close();
  }
});

test('AI Coach keeps quota states distinct from provider availability in dark TMA', async ({
  browser,
}) => {
  const viewport = { width: 390, height: 844 };
  for (const [label, initialQuotaUsed, expectedCopy, expectedClass] of [
    ['low', 14, 'Осталось 6 из 20', 'ai-coach-workspace__status--low'],
    ['exhausted', 20, 'Лимит исчерпан', 'ai-coach-workspace__status--empty'],
  ] as const) {
    const context = await browser.newContext({ viewport, hasTouch: true });
    const page = await context.newPage();
    await openAiCoachSurface(page, 'dark', viewport, true, true, initialQuotaUsed);

    const workspace = await openWorkspace(page);
    const status = workspace.getByTestId('ai-coach-workspace-status');
    await expect(status).toHaveClass(new RegExp(expectedClass));
    await expect(status).toContainText(expectedCopy);
    await expect(status).not.toHaveClass(/is-unavailable/);
    await expect(page.getByTestId('ai-coach-entry-quota')).toHaveClass(
      new RegExp(`ai-coach-entry__quota--${label === 'low' ? 'low' : 'empty'}`),
    );
    const input = workspace.getByRole('textbox', { name: 'Сообщение AI Coach' });
    await input.fill(`Вопрос при состоянии ${label}`);
    if (label === 'low') {
      await expect(workspace.getByRole('button', { name: 'Отправить' })).toBeEnabled();
      await captureEvidence(page, 'ai-coach-tma-dark-quota-low');
    } else {
      await expect(workspace.getByRole('button', { name: 'Отправить' })).toBeDisabled();
      await expect(workspace.getByTestId('ai-coach-quota-reset')).toContainText('Сброс через');
      await captureEvidence(page, 'ai-coach-tma-dark-quota-exhausted');
    }
    await context.close();
  }
});

test('AI Coach quota and composer fit the supported narrow mobile bounds', async ({ browser }) => {
  for (const width of [320, 430]) {
    const viewport = { width, height: 844 };
    const context = await browser.newContext({ viewport, hasTouch: true });
    const page = await context.newPage();
    await openAiCoachSurface(page, 'light', viewport);

    const workspace = await openWorkspace(page);
    const experience = workspace.getByTestId('ai-coach-experience');
    await expect(workspace.getByTestId('ai-coach-quota')).toHaveAttribute(
      'data-quota-remaining',
      '20',
    );
    await expectTouchTargets(experience.locator('button:visible'));
    await expectNoHorizontalOverflow(page);

    await context.close();
  }
});

test('AI Coach is fullscreen on compact mobile and keeps the composer usable', async ({
  browser,
}) => {
  const viewport = { width: 390, height: 844 };
  const context = await browser.newContext({ viewport, hasTouch: true });
  const page = await context.newPage();
  await openAiCoachSurface(page, 'light', viewport);
  const workspace = await openWorkspace(page);
  await expect(workspace).toHaveClass(/ai-coach-workspace--mobile/);
  const box = await workspace.boundingBox();
  expect(box?.x).toBe(0);
  expect(box?.y).toBe(0);
  expect(box?.width).toBe(viewport.width);
  expect(box?.height).toBeCloseTo(viewport.height, 0);
  await expect(workspace.getByTestId('ai-coach-workspace-resize')).toHaveCount(0);
  await expect(page.locator('#appBottomNav')).toBeHidden();
  await expect(page.getByTestId('quick-add-trigger')).toBeHidden();
  const experience = workspace.getByTestId('ai-coach-experience');
  const input = workspace.getByRole('textbox', { name: 'Сообщение AI Coach' });
  await expect(experience).toContainText('Чем помочь?');
  await expect(experience.locator('.ai-coach-chat__keyboard-hint')).toBeHidden();
  await expect(experience.getByTestId('ai-coach-chat')).not.toContainText('Сброс через');
  await expect(experience.locator('.ai-coach-chat__composer-count')).toHaveCount(0);
  await expect(workspace.getByTestId('ai-coach-workspace-status')).toContainText(
    'Готов · 20 из 20',
  );
  await expect(workspace.getByTestId('ai-coach-history-control')).toHaveCount(0);
  await captureEvidence(page, 'ai-coach-mobile-light-empty');
  const compactComposerHeight = await input.evaluate(
    (element) => element.getBoundingClientRect().height,
  );
  await input.fill('Строка один\nСтрока два\nСтрока три\nСтрока четыре');
  await expect(experience.locator('.ai-coach-chat__composer-count')).toHaveCount(0);
  const expandedComposerHeight = await input.evaluate(
    (element) => element.getBoundingClientRect().height,
  );
  expect(expandedComposerHeight).toBeGreaterThan(compactComposerHeight);
  await captureEvidence(page, 'ai-coach-mobile-light-composer-multiline');
  await input.fill('а'.repeat(1_600));
  await expect(experience.locator('.ai-coach-chat__composer-count')).toHaveText('1600/2000');
  await expect
    .poll(() => input.evaluate((element) => element.scrollHeight > element.clientHeight))
    .toBe(true);
  await input.fill('Сколько отдыхать между подходами?');
  await input.focus();
  await expect(workspace.locator('.ai-coach-chat__composer')).toHaveCSS('box-shadow', 'none');
  await expect(input).toHaveCSS('border-top-width', '0px');
  await expect(input).toHaveCSS('box-shadow', 'none');
  await captureEvidence(page, 'ai-coach-mobile-light-composer-text');
  await experience.getByRole('button', { name: 'Отправить' }).click();
  await expect(
    experience.getByText('Проверенный ответ по материалам YFC.', { exact: false }),
  ).toBeVisible();
  await expect(input).toBeVisible();
  await expect(workspace.getByTestId('ai-coach-history-control')).toBeVisible();
  await expect(experience.locator('.ai-coach-chat__toolbar')).toHaveCount(0);
  await historyControlCheck(workspace);
  const mobileComposer = workspace.locator('.ai-coach-chat__composer');
  const mobileWorkspaceBox = await workspace.boundingBox();
  const mobileComposerBox = await mobileComposer.boundingBox();
  const mobileSendBox = await workspace.getByRole('button', { name: 'Отправить' }).boundingBox();
  if (!mobileWorkspaceBox || !mobileComposerBox || !mobileSendBox) {
    throw new Error('Mobile composer has no geometry');
  }
  expect(mobileComposerBox.y + mobileComposerBox.height).toBeCloseTo(
    mobileWorkspaceBox.y + mobileWorkspaceBox.height,
    0,
  );
  expect(mobileSendBox.y + mobileSendBox.height).toBeLessThanOrEqual(
    mobileWorkspaceBox.y + mobileWorkspaceBox.height,
  );
  await captureEvidence(page, 'ai-coach-mobile-light-active');

  await workspace.getByRole('button', { name: 'Открыть настройки AI Coach' }).click();
  const settings = workspace.getByTestId('ai-coach-workspace-settings');
  await expect(settings).toBeVisible();
  await expect(settings.getByTestId('ai-coach-memory')).toBeVisible();
  await expect(settings).not.toContainText('Положение окна');
  await expect(workspace.getByRole('heading', { name: 'AI Coach / Настройки' })).toBeVisible();
  await expect(workspace.getByTestId('ai-coach-workspace-status')).toHaveCount(0);
  await expect(workspace.getByRole('button', { name: 'Назад в чат' })).toBeVisible();
  await expect(workspace.getByRole('button', { name: 'Закрыть AI Coach' })).toHaveCount(0);
  await captureEvidence(page, 'ai-coach-mobile-light-settings');
  await workspace.getByRole('button', { name: 'Назад в чат' }).click();
  await expect(input).toBeVisible();

  await page.keyboard.press('Escape');
  await expect(workspace).toHaveCount(0);
  await expect(page.locator('#appBottomNav')).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await context.close();
});

test('AI Coach keeps failed drafts and retry in the central workspace', async ({ browser }) => {
  const viewport = { width: 390, height: 844 };
  const context = await browser.newContext({ viewport, hasTouch: true });
  const page = await context.newPage();
  await openAiCoachSurface(page, 'light', viewport);
  const workspace = await openWorkspace(page);
  const experience = workspace.getByTestId('ai-coach-experience');
  const input = workspace.getByRole('textbox', { name: 'Сообщение AI Coach' });

  await input.fill('Проверка ошибки ответа');
  await workspace.getByRole('button', { name: 'Отправить' }).click();
  await expect(workspace.getByTestId('ai-coach-chat-failure')).toContainText(
    'Не удалось сформировать ответ. Повторить.',
  );
  await expect(input).toHaveValue('Проверка ошибки ответа');
  await workspace.getByRole('button', { name: 'Повторить' }).click();
  await expect(workspace.getByText('Ответ после повторной попытки.')).toBeVisible();
  await expect(workspace.getByTestId('ai-coach-message-user')).toHaveCount(1);
  await expect(experience).not.toContainText('На этот запрос нельзя ответить безопасно');
  await expectNoHorizontalOverflow(page);
  await captureEvidence(page, 'ai-coach-mobile-light-failed-draft');
  await context.close();
});

test('AI Coach composer shows a single loading control while a request is pending', async ({
  browser,
}) => {
  const viewport = { width: 1440, height: 900 };
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const aiCoachApi = await openAiCoachSurface(page, 'dark', viewport);
  const workspace = await openWorkspace(page);
  const input = workspace.getByRole('textbox', { name: 'Сообщение AI Coach' });

  await input.fill('Задержанный запрос');
  const sendButton = workspace.getByRole('button', { name: 'Отправить' });
  await sendButton.click();
  await expect(sendButton).toBeDisabled();
  await expect(sendButton.locator('[data-icon="sync"]')).toBeVisible();
  await expect(workspace.getByRole('status')).toContainText('AI Coach готовит ответ');
  await captureEvidence(page, 'ai-coach-desktop-composer-sending');

  aiCoachApi.releasePendingResponse();
  await expect(
    workspace.getByText('Проверенный ответ по материалам YFC.', { exact: false }),
  ).toBeVisible();
  await context.close();
});

test('AI Coach moves personal consent and memory into settings and supports the TMA BackButton', async ({
  browser,
}) => {
  const viewport = { width: 390, height: 844 };
  const context = await browser.newContext({ viewport, hasTouch: true });
  const page = await context.newPage();
  await openAiCoachSurface(page, 'dark', viewport, true, true);
  const workspace = await openWorkspace(page);
  await captureEvidence(page, 'ai-coach-tma-dark-empty');
  const input = workspace.getByRole('textbox', { name: 'Сообщение AI Coach' });
  await input.fill('Вопрос в Telegram WebView');
  await captureEvidence(page, 'ai-coach-tma-dark-composer-text');
  await input.press('Shift+Enter');
  await input.type('Вторая строка вопроса');
  await expect(input).toHaveValue('Вопрос в Telegram WebView\nВторая строка вопроса');
  await captureEvidence(page, 'ai-coach-tma-dark-composer-multiline');
  await workspace.getByRole('button', { name: 'Открыть настройки AI Coach' }).click();
  const settings = workspace.getByTestId('ai-coach-workspace-settings');
  const personalSettings = settings.getByTestId('ai-coach-personal-settings');
  const allow = personalSettings.getByRole('button', { name: 'Включить' });
  await expect(allow).toBeVisible();
  await allow.click();
  await expect(personalSettings.getByRole('button', { name: 'Выключить' })).toBeVisible();
  await expect(settings.getByTestId('ai-coach-memory')).toBeVisible();
  await captureEvidence(page, 'ai-coach-tma-dark-settings');

  await workspace.getByRole('button', { name: 'Назад в чат' }).click();
  const experience = workspace.getByTestId('ai-coach-experience');
  await experience.getByRole('button', { name: 'Что делать сегодня?' }).click();
  await experience.getByRole('button', { name: 'Отправить' }).click();
  await expect(experience).toContainText('По вашей текущей сводке');
  await captureEvidence(page, 'ai-coach-tma-dark-active');
  await expectTouchTargets(workspace.locator('button:visible'));
  const telegram = new TelegramHarness(page);
  await telegram.clickBack();
  await expect(workspace).toHaveCount(0);
  const state = await telegram.state();
  expect(state.backButton.clicks).toBeGreaterThanOrEqual(1);
  await expectNoHorizontalOverflow(page);
  await context.close();
});
