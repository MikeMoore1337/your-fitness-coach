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

async function installAiCoachApi(page: Page): Promise<void> {
  await page.route('**/api/v1/ai-coach/**', async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path.endsWith('/status')) {
      return route.fulfill({
        json: { ui_enabled: true, generic_available: true, personal_available: false },
      });
    }
    if (path.endsWith('/consent')) {
      return route.fulfill({
        json: {
          status: 'revoked',
          scope: 'personal_readonly_tools_v1',
          consent_version: 'ai-coach-personal-v1',
          categories: [],
          purpose: 'Внутренняя оценка AI Coach',
          provider_name: 'groq',
          provider_policy_revision: 'test',
          retention_notice: 'Без долгосрочной памяти',
          consent_source: 'test',
          granted_at: null,
          revoked_at: null,
        },
      });
    }
    if (path.endsWith('/generate') && request.method() === 'POST') {
      return route.fulfill({
        json: {
          outcome: 'answer',
          answer:
            'Публичный ответ по проверенному материалу. [Подробнее](https://example.org/guide)',
          citations: [
            {
              title: 'Проверенный материал',
              publisher: 'YFC',
              url: 'https://example.org/guide',
              source_type: 'canonical_yfc',
            },
          ],
          limitations: ['Это автоматическая проверка без доступа к истории пользователя.'],
          safety_category: 'clear',
          prompt_version: 'ai-coach-beta-v1',
          request_id: 'ui-eval-request',
        },
      });
    }
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
  await page.goto('/app?section=profile#profile-ai-coach');
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
  await expect(page.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
  await expect(page.locator('#profile-ai-coach')).toHaveAttribute('open');
  await expect(page.getByTestId('ai-coach-experience')).toBeVisible();

  if (viewport.width <= 640) {
    const securityLink = page.getByRole('link', { name: 'Доступ и безопасность', exact: true });
    const aiCoachLink = page.getByRole('link', { name: 'AI Coach beta', exact: true });
    const [securityBox, aiCoachBox] = await Promise.all([
      securityLink.boundingBox(),
      aiCoachLink.boundingBox(),
    ]);

    if (!securityBox || !aiCoachBox) {
      throw new Error('Profile settings navigation links are not measurable');
    }

    expect(Math.abs(aiCoachBox.y - securityBox.y)).toBeLessThan(1);
    expect(aiCoachBox.x).toBeGreaterThan(securityBox.x);
  }
}

test('AI Coach internal beta keeps honest states and responsive boundaries', async ({
  browser,
}) => {
  mkdirSync(evidenceDir, { recursive: true });
  const surfaces = [
    {
      label: 'mobile-light-360x800',
      theme: 'light' as const,
      viewport: { width: 360, height: 800 },
      tma: false,
    },
    {
      label: 'mobile-dark-390x844',
      theme: 'dark' as const,
      viewport: { width: 390, height: 844 },
      tma: false,
    },
    {
      label: 'mobile-tma-dark-390x844',
      theme: 'dark' as const,
      viewport: { width: 390, height: 844 },
      tma: true,
    },
    {
      label: 'mobile-light-430x932',
      theme: 'light' as const,
      viewport: { width: 430, height: 932 },
      tma: false,
    },
    {
      label: 'desktop-dark-1440x900',
      theme: 'dark' as const,
      viewport: { width: 1440, height: 900 },
      tma: false,
    },
  ];

  for (const surface of surfaces) {
    const context = await browser.newContext({
      viewport: surface.viewport,
      hasTouch: surface.viewport.width < 900,
    });
    const page = await context.newPage();
    await openAiCoachSurface(page, surface.theme, surface.viewport, surface.tma ?? false);

    const experience = page.getByTestId('ai-coach-experience');
    await expect(experience.getByText('Что не передаётся')).toBeVisible();
    await expect(experience.getByRole('link', { name: 'Продолжить без AI' })).toHaveAttribute(
      'href',
      '/app?section=today',
    );
    await expect(experience.getByTestId('ai-coach-personal-unavailable')).toHaveCount(0);
    const question = experience.getByRole('textbox', { name: 'Ваш вопрос' });
    await question.focus();
    await expect(question).toBeFocused();
    await expectTouchTargets(experience.locator('button'));
    await expectTouchTargets(experience.locator('.ai-coach-experience__footer a'));

    await experience.getByRole('button', { name: 'Моя сводка' }).click();
    await expect(experience.getByTestId('ai-coach-personal-unavailable')).toBeVisible();
    await experience.getByRole('button', { name: 'Публичная помощь' }).click();
    await experience.getByRole('button', { name: 'Разобраться с тренировкой' }).click();
    await experience.getByRole('button', { name: 'Получить ответ' }).click();
    await expect(experience.getByTestId('ai-coach-response')).toContainText(
      'Публичный ответ по проверенному материалу',
    );
    await expect(experience.getByRole('link', { name: 'Подробнее' })).toHaveAttribute(
      'href',
      'https://example.org/guide',
    );
    await expectNoHorizontalOverflow(page);
    await page.screenshot({
      path: resolve(evidenceDir, `${surface.label}.png`),
      fullPage: true,
    });

    await context.close();
  }
});
