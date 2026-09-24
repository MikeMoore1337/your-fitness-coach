/// <reference types="node" />

import { expect, test, type Browser, type Page } from '@playwright/test';
import { installTelegramHarness, TelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi, type PlatformApiController } from './fixtures/platform-api';

const avatarFile = {
  name: 'new-avatar.png',
  mimeType: 'image/png',
  buffer: Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFElEQVR42mNkYPj/n4GBgYGJAQoAHgQCAftFq20AAAAASUVORK5CYII=',
    'base64',
  ),
};

async function openPersonalData(page: Page) {
  await page.goto('/app?section=profile');
  await page.getByRole('link', { name: 'Личные данные', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Изменить аватар' })).toBeVisible();
}

async function openAvatarSettings(page: Page) {
  await openPersonalData(page);
  await page.getByRole('button', { name: 'Изменить аватар' }).click();
  await expect(page.getByRole('dialog', { name: 'Аватар' })).toBeVisible();
}

async function chooseAvatar(page: Page) {
  await page.getByLabel('Выбрать изображение для аватара').setInputFiles(avatarFile);
  await expect(page.getByText('Предпросмотр нового изображения')).toBeVisible();
}

async function createBrowserProfile(
  browser: Browser,
  options: Parameters<typeof installPlatformApi>[1],
) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const api = await installPlatformApi(page, { ...options, browserSession: true });
  return { context, page, api };
}

test('failed upload keeps the local preview and retry updates every account avatar', async ({
  browser,
}) => {
  const { context, page, api } = await createBrowserProfile(browser, {
    avatarState: 'provider',
  });
  await openAvatarSettings(page);

  await chooseAvatar(page);
  const previewSource = await page.locator('.avatar-editor__avatar img').getAttribute('src');
  expect(previewSource).toMatch(/^blob:/);

  api.failNextAvatarUpload();
  await page.getByRole('button', { name: 'Сохранить аватар' }).click();
  await expect(page.getByRole('alert')).toContainText('Не удалось обработать изображение');
  await expect(page.getByRole('button', { name: 'Повторить сохранение' })).toBeVisible();
  await expect(page.locator('.avatar-editor__avatar img')).toHaveAttribute('src', previewSource!);

  await page.getByRole('button', { name: 'Повторить сохранение' }).click();
  await expect(page.getByRole('status')).toContainText('Аватар сохранён');
  expect(api.avatarUploads()).toBe(2);
  await expect(page.locator('.app-desktop-account-entry img')).toHaveAttribute('src', /^blob:/);

  await page.reload();
  await openAvatarSettings(page);
  await expect(
    page.getByRole('dialog', { name: 'Аватар' }).getByText('Используется свой аватар'),
  ).toBeVisible();
  await expect(page.locator('.avatar-editor__avatar img')).toHaveAttribute('src', /^blob:/);
  await context.close();
});

test('deletion requires confirmation and restores the provider avatar', async ({ browser }) => {
  const { context, page, api } = await createBrowserProfile(browser, {
    avatarState: 'custom',
  });
  await openAvatarSettings(page);

  await page.getByRole('button', { name: 'Удалить свой аватар' }).click();
  const confirmation = page.getByRole('alertdialog', { name: 'Удалить свой аватар?' });
  await expect(confirmation).toBeVisible();
  await expect(confirmation.getByRole('button', { name: 'Отмена' })).toBeFocused();
  await confirmation.getByRole('button', { name: 'Удалить', exact: true }).click();

  await expect(page.getByRole('status')).toContainText('фото из способа входа');
  await expect(page.locator('.app-desktop-account-entry img')).toHaveAttribute(
    'src',
    /^data:image\/svg\+xml/,
  );
  expect(api.avatarDeletes()).toBe(1);
  await context.close();
});

for (const viewport of [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 768, height: 900 },
]) {
  test(`mobile ${viewport.width}px keeps avatar actions inside the viewport`, async ({
    browser,
  }) => {
    const context = await browser.newContext({
      viewport,
      hasTouch: true,
      reducedMotion: viewport.width === 360 ? 'reduce' : 'no-preference',
    });
    const page = await context.newPage();
    await installPlatformApi(page, { browserSession: true, avatarState: 'custom' });
    await openAvatarSettings(page);

    const editor = page.getByRole('dialog', { name: 'Аватар' });
    await expect(editor).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
    for (const button of await editor.locator('button').all()) {
      const box = await button.boundingBox();
      expect(box?.height).toBeGreaterThanOrEqual(44 - 0.01);
    }
    await context.close();
  });
}

test('mocked Telegram Mini App uses the same custom avatar flow', async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
  });
  const page = await context.newPage();
  await installTelegramHarness(page, {
    colorScheme: 'dark',
    safeAreaInset: { top: 16, right: 0, bottom: 20, left: 0 },
    contentSafeAreaInset: { top: 8, right: 0, bottom: 24, left: 0 },
  });
  const telegram = new TelegramHarness(page);
  const api: PlatformApiController = await installPlatformApi(page, { avatarState: 'default' });
  await openAvatarSettings(page);

  await chooseAvatar(page);
  await page.getByRole('button', { name: 'Сохранить аватар' }).click();
  await expect(page.getByRole('status')).toContainText('Аватар сохранён');
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(page.locator('.profile-avatar-setting img')).toHaveAttribute('src', /^blob:/);

  await page.getByRole('button', { name: 'Изменить аватар' }).click();
  const editor = page.getByRole('dialog', { name: 'Аватар' });
  const deleteAvatar = editor.getByRole('button', { name: 'Удалить свой аватар' });
  await expect(editor.getByRole('button', { name: 'Заменить изображение' })).toHaveCSS(
    'border-top-width',
    '1px',
  );
  await expect(deleteAvatar).toHaveCSS('border-top-width', '1px');
  await deleteAvatar.click();
  await expect(page.getByRole('alertdialog', { name: 'Удалить свой аватар?' })).toBeVisible();
  await telegram.clickBack();
  await expect(page.getByRole('alertdialog', { name: 'Удалить свой аватар?' })).not.toBeAttached();
  await expect(editor).toBeVisible();
  await expect(deleteAvatar).toBeFocused();
  await editor.getByRole('button', { name: 'Закрыть редактор аватара' }).click();

  await page.getByRole('button', { name: 'Открыть профиль и настройки' }).click();
  await expect(page.getByRole('dialog', { name: 'Профиль и настройки' })).toBeVisible();
  await expect(page.locator('.app-more-panel__identity img')).toHaveAttribute('src', /^blob:/);
  expect(api.authInitCalls()).toBe(1);
  expect(api.avatarUploads()).toBe(1);
  await context.close();
});

test('light mobile keeps avatar actions outlined and current account boundary lime', async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    colorScheme: 'light',
    reducedMotion: 'reduce',
  });
  await context.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  const page = await context.newPage();
  await installPlatformApi(page, { browserSession: true, avatarState: 'custom' });
  await openAvatarSettings(page);

  const editor = page.getByRole('dialog', { name: 'Аватар' });
  const outlinedActions = [
    editor.getByRole('button', { name: 'Заменить изображение' }),
    editor.getByRole('button', { name: 'Удалить свой аватар' }),
    editor.getByRole('button', { name: 'Отмена', exact: true }),
    editor.getByRole('button', { name: 'Сохранить аватар' }),
  ];
  for (const action of outlinedActions) {
    await expect(action).toHaveCSS('border-top-style', 'solid');
    await expect(action).toHaveCSS('border-top-width', '1px');
    expect((await action.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }

  const [chooseBox, deleteBox] = await Promise.all(
    outlinedActions.slice(0, 2).map((action) => action.boundingBox()),
  );
  expect(chooseBox).not.toBeNull();
  expect(deleteBox).not.toBeNull();
  expect(Math.abs(chooseBox!.x - deleteBox!.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(chooseBox!.width - deleteBox!.width)).toBeLessThanOrEqual(1);

  await page.screenshot({
    path: '../.artifacts/screenshots/task-110B/mobile-light-avatar-actions.png',
    fullPage: false,
  });
  await context.close();

  const accountContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    colorScheme: 'light',
    reducedMotion: 'reduce',
  });
  await accountContext.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  const accountPage = await accountContext.newPage();
  await installPlatformApi(accountPage, { browserSession: true, avatarState: 'custom' });
  await accountPage.goto('/app?section=profile');
  const accountTrigger = accountPage.getByRole('button', {
    name: 'Открыть профиль и настройки',
  });
  await expect(accountTrigger).toBeInViewport();
  await accountTrigger.click();
  const accountPanel = accountPage.getByRole('dialog', { name: 'Профиль и настройки' });
  const currentProfile = accountPanel.getByRole('link', {
    name: 'Профиль и настройки',
    exact: true,
  });
  await expect(accountPanel).toBeVisible();
  await expect(currentProfile).toBeVisible();
  const boundary = await currentProfile.evaluate((element) => {
    const probe = document.createElement('span');
    probe.style.color = 'var(--v2-lime)';
    document.body.append(probe);
    const result = {
      boxShadow: getComputedStyle(element).boxShadow,
      lime: getComputedStyle(probe).color,
    };
    probe.remove();
    return result;
  });
  expect(boundary.boxShadow).toContain(boundary.lime);
  await accountPage.screenshot({
    path: '../.artifacts/screenshots/task-110B/mobile-light-account-boundary.png',
    fullPage: false,
  });
  await accountContext.close();
});

test('desktop profile actions have persistent outline and symmetric save spacing', async ({
  browser,
}) => {
  const { context, page } = await createBrowserProfile(browser, { avatarState: 'custom' });
  await context.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await openPersonalData(page);

  const editAvatar = page.getByRole('button', { name: 'Изменить аватар' });
  await expect(editAvatar).toHaveCSS('border-top-style', 'solid');
  await expect(editAvatar).toHaveCSS('border-top-width', '1px');
  const editBoundary = await editAvatar.evaluate((element) => {
    const probe = document.createElement('span');
    probe.style.color = 'var(--v2-border-strong)';
    document.body.append(probe);
    const result = {
      border: getComputedStyle(element).borderTopColor,
      expected: getComputedStyle(probe).color,
    };
    probe.remove();
    return result;
  });
  expect(editBoundary.border).toBe(editBoundary.expected);

  const geometry = await page.locator('.profile-primary-card').evaluate((card) => {
    const footer = card.querySelector<HTMLElement>('.profile-form__save');
    const save = footer?.querySelector<HTMLElement>('button[type="submit"]');
    if (!footer || !save) throw new Error('Profile save footer is missing');
    const cardRect = card.getBoundingClientRect();
    const footerRect = footer.getBoundingClientRect();
    const saveRect = save.getBoundingClientRect();
    const footerStyle = getComputedStyle(footer);
    const cardStyle = getComputedStyle(card);
    return {
      top: saveRect.top - footerRect.top - Number.parseFloat(footerStyle.borderTopWidth),
      bottom: footerRect.bottom - saveRect.bottom,
      cardResidual:
        cardRect.bottom - Number.parseFloat(cardStyle.borderBottomWidth) - footerRect.bottom,
    };
  });
  expect(Math.abs(geometry.top - geometry.bottom), JSON.stringify(geometry)).toBeLessThanOrEqual(1);
  expect(geometry.top).toBeGreaterThanOrEqual(17);
  expect(geometry.cardResidual).toBeLessThanOrEqual(5);

  await page.screenshot({
    path: '../.artifacts/screenshots/task-110B/desktop-light-profile-actions.png',
    fullPage: true,
  });
  await context.close();
});

test('captures the exact Task 110A owner approval screenshots', async ({ browser }) => {
  const scenarios = [
    {
      name: '01-mobile-390x844-light-personal-data',
      viewport: { width: 390, height: 844 },
      hasTouch: true,
      theme: 'light',
      editorOpen: false,
    },
    {
      name: '02-mobile-390x844-dark-avatar-sheet',
      viewport: { width: 390, height: 844 },
      hasTouch: true,
      theme: 'dark',
      editorOpen: true,
    },
    {
      name: '03-desktop-1280x900-light-personal-data',
      viewport: { width: 1280, height: 900 },
      hasTouch: false,
      theme: 'light',
      editorOpen: false,
    },
    {
      name: '04-desktop-1280x900-dark-avatar-modal',
      viewport: { width: 1280, height: 900 },
      hasTouch: false,
      theme: 'dark',
      editorOpen: true,
    },
  ] as const;

  for (const scenario of scenarios) {
    const context = await browser.newContext({
      viewport: scenario.viewport,
      hasTouch: scenario.hasTouch,
      colorScheme: scenario.theme,
      reducedMotion: 'reduce',
    });
    await context.addInitScript((selectedTheme) => {
      localStorage.setItem('app-theme', selectedTheme);
    }, scenario.theme);
    const page = await context.newPage();
    await installPlatformApi(page, { browserSession: true, avatarState: 'custom' });

    if (scenario.editorOpen) {
      await openAvatarSettings(page);
      await expect(
        page.getByRole('dialog', { name: 'Аватар' }).getByText('Используется свой аватар'),
      ).toBeVisible();
    } else {
      await openPersonalData(page);
      await expect(page.locator('.profile-avatar-card')).not.toBeAttached();
      await expect(page.locator('.profile-avatar-setting')).toBeVisible();
    }

    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', scenario.theme);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({
      path: `../.artifacts/screenshots/task-110A/approval/${scenario.name}.png`,
      fullPage: false,
    });
    await context.close();
  }
});
