import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

async function openProfileSection(page: import('@playwright/test').Page, name: string) {
  await page.getByRole('link', { name, exact: true }).click();
}

test('desktop account entry stays available across primary sections and never opens the mobile sheet', async ({
  browser,
}) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await installPlatformApi(page, { browserSession: true, authProviders: ['telegram', 'google'] });
  await page.goto('/app?section=profile');

  const accountEntry = page.getByRole('link', { name: 'Профиль и настройки', exact: true });
  await expect(accountEntry).toBeVisible();
  await expect(accountEntry).toHaveClass(/app-desktop-account-entry/);
  await expect(accountEntry).toHaveAttribute('aria-current', 'page');
  await expect(
    page.locator(
      '.app-bottom-nav__brand + .app-bottom-nav__profile-slot > .app-desktop-account-entry',
    ),
  ).toBeVisible();
  await expect(page.locator('.app-desktop-account-bar')).not.toBeAttached();
  await expect(page.locator('.app-bottom-nav__account-entry')).not.toBeAttached();
  await expect(page.getByRole('link', { name: 'Профиль', exact: true })).not.toBeAttached();
  await expect(page.getByText('Ресурсы', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Упражнения', exact: true })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }),
  ).not.toBeAttached();
  await expect(page.locator('#appMorePanel')).not.toBeAttached();

  for (const section of ['today', 'programs', 'nutrition', 'progress']) {
    await page.goto(`/app?section=${section}`);
    await expect(accountEntry).toBeVisible();
    await expect(accountEntry).toHaveAttribute('href', '/app?section=profile');
    await expect(accountEntry).not.toHaveAttribute('aria-current', 'page');
  }
  await page.goto('/app?section=profile');
  await expect(accountEntry).toHaveAttribute('aria-current', 'page');

  const navigation = page.getByRole('navigation', { name: 'Основная навигация' });
  const theme = navigation.getByRole('button', { name: /Включить .* тему/ });
  const logout = navigation.getByRole('button', { name: 'Выйти из аккаунта' });
  const [themeBox, logoutBox] = await Promise.all([theme.boundingBox(), logout.boundingBox()]);
  expect(themeBox).not.toBeNull();
  expect(logoutBox).not.toBeNull();
  expect(Math.abs(themeBox!.width - logoutBox!.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(themeBox!.height - logoutBox!.height)).toBeLessThanOrEqual(1);

  const cardHeights = await page
    .locator('.profile-settings > details.card-disclosure')
    .evaluateAll((cards) => cards.map((card) => card.getBoundingClientRect().height));
  expect(Math.max(...cardHeights) - Math.min(...cardHeights)).toBeLessThanOrEqual(1);

  await accountEntry.click();
  await expect(page).toHaveURL(/\/app\?section=profile$/);
  await expect(page.locator('#appMorePanel')).not.toBeAttached();
  await context.close();
});

test('mobile sheet closes cleanly on 899 to 900 resize and stays closed on return', async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 899, height: 900 },
    hasTouch: true,
  });
  const page = await context.newPage();
  await installPlatformApi(page, { browserSession: true, authProviders: ['telegram'] });
  await page.goto('/app?section=today');

  const mobileTrigger = page.getByRole('button', {
    name: 'Открыть профиль и настройки',
    exact: true,
  });
  await mobileTrigger.click();
  await expect(page.getByRole('dialog', { name: 'Профиль и настройки' })).toBeVisible();
  await expect(page.locator('body')).toHaveCSS('position', 'fixed');

  await page.setViewportSize({ width: 900, height: 900 });
  await expect(page.locator('#appMorePanel')).not.toBeAttached();
  await expect(page.locator('body')).not.toHaveCSS('position', 'fixed');
  await expect(page.getByRole('link', { name: 'Профиль и настройки', exact: true })).toBeFocused();

  await page.setViewportSize({ width: 899, height: 900 });
  await expect(mobileTrigger).toBeVisible();
  await expect(mobileTrigger).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('#appMorePanel')).not.toBeAttached();
  await context.close();
});

test('profile stays compact while disclosures, icons and shared provider actions remain usable', async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
  });
  const page = await context.newPage();
  await installPlatformApi(page, {
    browserSession: true,
    authProviders: ['telegram'],
  });
  await page.route('**/api/v1/public/config', (route) =>
    route.fulfill({
      json: {
        app_env: 'test',
        enable_dev_auth: true,
        enable_web_auth: true,
        enable_email_auth: false,
        telegram_bot_username: 'fit_test_bot',
        oauth_providers: ['google', 'yandex'],
      },
    }),
  );
  await page.goto('/app?section=profile');

  await expect(page.locator('.profile-identity')).not.toBeAttached();
  await expect(page.locator('.app-desktop-account-entry')).not.toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }),
  ).toBeVisible();
  const iconContract = [
    ['Личные данные', 'nav-profile'],
    ['Цели и параметры', 'nav-plan'],
    ['Тренер и приглашения', 'nav-coach'],
    ['Уведомления', 'nav-today'],
    ['Доступ и безопасность', 'account-security'],
  ] as const;
  const profileNavigation = page.getByRole('navigation', { name: 'Разделы профиля' });
  for (const [name, icon] of iconContract) {
    await expect(profileNavigation.getByRole('link', { name, exact: true })).toBeVisible();
    await expect(
      profileNavigation.getByRole('link', { name, exact: true }).locator(`[data-icon="${icon}"]`),
    ).toBeVisible();
  }

  const majorCards = page.locator('.profile-settings > details.card-disclosure');
  expect(await majorCards.count()).toBeGreaterThanOrEqual(5);
  for (const card of await majorCards.all()) await expect(card).not.toHaveAttribute('open');

  await openProfileSection(page, 'Цели и параметры');
  const profileCard = page.locator('#profile-personal');
  await expect(profileCard).toHaveAttribute('open');
  const saveProfile = page.getByRole('button', { name: 'Сохранить изменения' });
  await expect(saveProfile).toBeDisabled();
  await page.getByLabel('Имя').fill('Анна Петрова-Северная');
  await expect(saveProfile).toBeEnabled();

  const trainingPreferences = page.locator('#profile-training-preferences');
  await trainingPreferences.locator(':scope > summary').press('Enter');
  await expect(trainingPreferences).toHaveAttribute('open');
  const schedule = trainingPreferences.getByText('Расписание', { exact: true }).locator('..');
  const scheduleDetails = schedule.locator('xpath=ancestor::details[1]');
  await expect(scheduleDetails).not.toHaveAttribute('open');
  const scheduleSummary = scheduleDetails.locator(':scope > summary');
  await scheduleSummary.focus();
  await expect(scheduleSummary).toBeFocused();
  await scheduleSummary.press('Enter');
  await expect(scheduleDetails).toHaveAttribute('open');

  await openProfileSection(page, 'Уведомления');
  const notificationCenter = page
    .getByText('Центр уведомлений', { exact: true })
    .locator('xpath=ancestor::details[1]');
  await expect(notificationCenter).not.toHaveAttribute('open');
  await notificationCenter.locator(':scope > summary').focus();
  await page.keyboard.press('Space');
  await expect(notificationCenter).toHaveAttribute('open');

  await openProfileSection(page, 'Доступ и безопасность');
  await page.getByText('Способы входа', { exact: true }).click();
  const googleAction = page.getByRole('button', { name: 'Привязать Google' });
  await expect(googleAction).toHaveClass(/oauth-button--google/);
  await expect(googleAction.locator('.oauth-button__icon img')).toBeVisible();
  await context.close();
});

test('captures matching compact Profile state in light and dark themes', async ({ browser }) => {
  for (const surface of [
    { name: 'mobile-390x844', width: 390, height: 844, hasTouch: true, fullPage: false },
    { name: 'desktop-1280x900', width: 1280, height: 900, hasTouch: false, fullPage: true },
  ] as const) {
    for (const theme of ['light', 'dark'] as const) {
      const context = await browser.newContext({
        viewport: { width: surface.width, height: surface.height },
        hasTouch: surface.hasTouch,
        colorScheme: theme,
      });
      await context.addInitScript((selectedTheme) => {
        localStorage.setItem('app-theme', selectedTheme);
      }, theme);
      const page = await context.newPage();
      await installPlatformApi(page, {
        browserSession: true,
        authProviders: ['telegram', 'google'],
      });
      await page.goto('/app?section=profile');
      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
      await expect(page.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
      await expect(page.locator('.profile-settings > details.card-disclosure')).toHaveCount(5);
      if (surface.hasTouch) {
        await expect(page.locator('.profile-identity')).not.toBeAttached();
        await expect(page.locator('.app-desktop-account-entry')).not.toBeVisible();
      } else {
        await expect(page.locator('.app-desktop-account-entry')).toBeVisible();
      }
      await expect(page.locator('.profile-settings > details[open]')).toHaveCount(0);
      await page.screenshot({
        path: `../.artifacts/screenshots/task-122/profile-compact-${surface.name}-${theme}.png`,
        fullPage: surface.fullPage,
      });
      await context.close();
    }
  }
});
