import { expect, type Page } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { MOBILE_CONTEXTS, test } from './fixtures/mobile-tma';

const AFTER_SCREENSHOTS = '../.artifacts/tasks/1003/evidence/screenshots/after';

function trackAiCoachRequests(page: Page): string[] {
  const requests: string[] = [];
  page.on('request', (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.startsWith('/api/v1/ai-coach/')) requests.push(pathname);
  });
  return requests;
}

async function expectAiCoachHidden(page: Page, requests: string[]): Promise<void> {
  await expect(page.locator('main').first()).toBeVisible();
  await expect(page.getByText(/AI Coach/i)).toHaveCount(0);
  await expect(
    page.locator(
      '[href*="profile-ai-coach"], [data-testid*="ai-coach"], [aria-label*="AI Coach"], [aria-describedby*="ai-coach"], [aria-labelledby*="ai-coach"]',
    ),
  ).toHaveCount(0);
  expect(requests.filter((pathname) => !pathname.endsWith('/status'))).toEqual([]);
}

test('AI Coach is hidden across user surfaces, roles, themes and Web/TMA/PWA runtimes', async ({
  browser,
  page,
  mobilePage,
  tma,
  tmaPage,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ colorScheme: 'light' });
  const desktopRequests = trackAiCoachRequests(page);
  await installPlatformApi(page, { browserSession: true, programHistory: 'many' });

  for (const path of [
    '/app?section=today',
    '/app?section=programs',
    '/app?section=catalog',
    '/app?section=nutrition',
    '/app?section=progress',
    '/app?section=profile',
  ]) {
    await page.goto(path);
    await expectAiCoachHidden(page, desktopRequests);
  }

  await page.goto('/app?section=profile#profile-ai-coach');
  await expect(page).toHaveURL(/\/app\?section=profile$/);
  await expectAiCoachHidden(page, desktopRequests);
  await page.screenshot({
    path: `${AFTER_SCREENSHOTS}/desktop-web-1440x900-light-profile.png`,
    fullPage: true,
  });

  await page.reload();
  await expect(page).toHaveURL(/\/app\?section=profile$/);
  await page.goto('/app?section=today');
  await page.goto('/app?section=profile#profile-ai-coach');
  await expect(page).toHaveURL(/\/app\?section=profile$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/app\?section=today$/);
  await page.goForward();
  await expect(page).toHaveURL(/\/app\?section=profile$/);
  await expectAiCoachHidden(page, desktopRequests);

  const trainerPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const trainerRequests = trackAiCoachRequests(trainerPage);
  await installPlatformApi(trainerPage, { browserSession: true, trainerActive: true });
  await trainerPage.goto('/coach');
  await expect(trainerPage.getByText('Тренер · рабочее пространство')).toBeVisible();
  await expectAiCoachHidden(trainerPage, trainerRequests);
  await trainerPage.close();

  await mobilePage.setViewportSize(MOBILE_CONTEXTS.baseline);
  await mobilePage.emulateMedia({ colorScheme: 'light' });
  await mobilePage.addInitScript((theme) => localStorage.setItem('app-theme', theme), 'light');
  const mobileRequests = trackAiCoachRequests(mobilePage);
  await installPlatformApi(mobilePage, { browserSession: true });
  await mobilePage.goto('/app?section=profile');
  await expectAiCoachHidden(mobilePage, mobileRequests);
  await mobilePage.screenshot({
    path: `${AFTER_SCREENSHOTS}/mobile-web-390x844-light-profile.png`,
    fullPage: true,
  });

  // The fixture installs the Telegram bridge as an init script; create its first document before mutating it.
  await tmaPage.goto('about:blank');
  await tma.setTheme('dark');
  const tmaRequests = trackAiCoachRequests(tmaPage);
  await installPlatformApi(tmaPage);
  await tmaPage.goto('/app?section=profile&tgWebAppPlatform=android#profile-ai-coach');
  await expect(tmaPage).toHaveURL(/\/app\?section=profile(?:&[^#]+)?$/);
  await expectAiCoachHidden(tmaPage, tmaRequests);
  await tmaPage.screenshot({
    path: `${AFTER_SCREENSHOTS}/tma-390x844-dark-profile.png`,
    fullPage: true,
  });

  const pwaContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: 'dark',
  });
  const pwaPage = await pwaContext.newPage();
  await pwaPage.addInitScript(() => {
    const nativeMatchMedia = window.matchMedia.bind(window);
    window.matchMedia = (query: string) => {
      const result = nativeMatchMedia(query);
      if (query === '(display-mode: standalone)') {
        Object.defineProperty(result, 'matches', { configurable: true, value: true });
      }
      return result;
    };
  });
  const pwaRequests = trackAiCoachRequests(pwaPage);
  await installPlatformApi(pwaPage, { browserSession: true });
  await pwaPage.goto('/app?section=profile');
  await expect(pwaPage).toHaveTitle(/Your Fitness Coach/i);
  await expect(pwaPage).toHaveURL(/\/app\?section=profile$/);
  expect(await pwaPage.evaluate(() => matchMedia('(display-mode: standalone)').matches)).toBe(true);
  await expectAiCoachHidden(pwaPage, pwaRequests);
  await pwaPage.screenshot({
    path: `${AFTER_SCREENSHOTS}/pwa-standalone-1440x900-dark-profile.png`,
    fullPage: true,
  });
  await pwaContext.close();

  await testInfo.attach('ai-coach-hidden-request-summary.json', {
    body: JSON.stringify(
      {
        desktop: desktopRequests,
        mobileWeb: mobileRequests,
        tma: tmaRequests,
        pwa: pwaRequests,
        assertion:
          'Only the centralized status gate may be requested; no quota/generation/provider route.',
      },
      null,
      2,
    ),
    contentType: 'application/json',
  });
});

test('AI Coach stays hidden in active workout and completion on mocked TMA', async ({
  tmaPage,
}) => {
  const requests = trackAiCoachRequests(tmaPage);
  const api = await installPlatformApi(tmaPage, { workoutStatus: 'planned' });
  await tmaPage.goto('/app');
  await tmaPage.getByRole('button', { name: 'Начать тренировку' }).click();
  await expectAiCoachHidden(tmaPage, requests);

  await tmaPage.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }).fill('8');
  await tmaPage.getByRole('spinbutton', { name: 'Вес, Приседания, подход 1' }).fill('40');
  await tmaPage.getByRole('button', { name: 'Завершить: Приседания, подход 1' }).click();
  await expect(tmaPage.getByText('Синхронизировано')).toBeVisible();
  await tmaPage.getByRole('button', { name: 'Завершить тренировку' }).click();
  await expect(tmaPage.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible();
  await expectAiCoachHidden(tmaPage, requests);
  expect(api.finishCalls()).toBe(1);
});
