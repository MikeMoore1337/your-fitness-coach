import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

const AFTER_EVIDENCE = '../.artifacts/tasks/870/evidence/after';
const PROFILE_HASHES = [
  'profile-personal',
  'profile-fitness',
  'profile-trainer',
  'profile-notifications',
  'profile-security',
] as const;

function detailsForHash(
  page: import('@playwright/test').Page,
  hash: (typeof PROFILE_HASHES)[number],
) {
  return page.locator(hash === 'profile-fitness' ? '#profile-personal' : `#${hash}`);
}

test('profile hash deep links reveal the right card through keyboard, history and reload', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await installPlatformApi(page, { browserSession: true, fixedDate: '2026-10-10' });

  for (const hash of PROFILE_HASHES) {
    await page.goto(`/app?section=profile#${hash}`);
    await expect(page.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
    await expect(detailsForHash(page, hash)).toHaveAttribute('open', '');
    await expect(page).toHaveURL(`/app?section=profile#${hash}`);
  }

  await page.goto('/app?section=profile');
  await page.evaluate(() => {
    const link = document.createElement('a');
    link.id = 'profile-hash-keyboard-trigger';
    link.href = '#profile-security';
    link.textContent = 'Безопасность';
    document.body.append(link);
  });
  const keyboardTrigger = page.locator('#profile-hash-keyboard-trigger');
  await keyboardTrigger.focus();
  await keyboardTrigger.press('Enter');
  await expect(page).toHaveURL('/app?section=profile#profile-security');
  await expect(page.locator('#profile-security')).toHaveAttribute('open', '');
  await expect(keyboardTrigger).toBeFocused();

  await page.goto('/app?section=profile');
  await page.evaluate(() => {
    window.location.hash = '#profile-fitness';
  });
  await expect(page).toHaveURL('/app?section=profile#profile-fitness');
  await expect(page.locator('#profile-personal')).toHaveAttribute('open', '');
  await page.evaluate(() => {
    window.location.hash = '#profile-trainer';
  });
  await expect(page).toHaveURL('/app?section=profile#profile-trainer');
  await expect(page.locator('#profile-trainer')).toHaveAttribute('open', '');

  await page.goBack();
  await expect(page).toHaveURL('/app?section=profile#profile-fitness');
  await expect(page.locator('#profile-personal')).toHaveAttribute('open', '');
  await page.goForward();
  await expect(page).toHaveURL('/app?section=profile#profile-trainer');
  await expect(page.locator('#profile-trainer')).toHaveAttribute('open', '');
  await page.reload();
  await expect(page).toHaveURL('/app?section=profile#profile-trainer');
  await expect(page.locator('#profile-trainer')).toHaveAttribute('open', '');

  await page.goto('/app?section=profile#profile-ai-coach');
  await expect(page).toHaveURL('/app?section=profile');
  await expect(page.locator('#profile-ai-coach')).toHaveCount(0);
  await expect(page.locator('main')).not.toContainText(/AI Coach/i);
});

test('profile AFTER evidence keeps the approved composition in light and dark themes', async ({
  browser,
}) => {
  for (const surface of [
    { name: 'mobile-390x844', width: 390, height: 844, hasTouch: true },
    { name: 'desktop-1280x900', width: 1280, height: 900, hasTouch: false },
  ] as const) {
    for (const theme of ['light', 'dark'] as const) {
      const context = await browser.newContext({
        colorScheme: theme,
        hasTouch: surface.hasTouch,
        viewport: { width: surface.width, height: surface.height },
      });
      await context.addInitScript((selectedTheme) => {
        localStorage.setItem('app-theme', selectedTheme);
      }, theme);
      const page = await context.newPage();
      await installPlatformApi(page, { browserSession: true, fixedDate: '2026-10-10' });
      await page.goto('/app?section=profile');
      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
      await expect(page.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
      await expect(page.locator('.profile-settings-nav')).toHaveCount(0);
      await expect(page.locator('.profile-settings > details.card-disclosure')).toHaveCount(5);
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({
        path: `${AFTER_EVIDENCE}/profile-${surface.name}-${theme}.png`,
        fullPage: true,
      });
      await context.close();
    }
  }
});
