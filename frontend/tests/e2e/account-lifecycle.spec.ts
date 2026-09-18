import {
  expect,
  expectNoHorizontalOverflow,
  expectTouchTargets,
  installTelegramHarness,
  MOBILE_CONTEXTS,
  test,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test('account lifecycle restores export, guards unlink and keeps destructive confirmation usable in TMA', async ({
  tma,
  tmaPage,
}) => {
  const api = await installPlatformApi(tmaPage, {
    accountExportState: 'ready',
    authProviders: ['telegram', 'google'],
  });
  await tmaPage.goto('/app?section=profile');
  await expect(tmaPage.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
  await tmaPage.getByRole('link', { name: 'Безопасность' }).click();

  const exportRegion = tmaPage.getByRole('region', { name: 'Копия данных' });
  await expect(exportRegion.getByText('Готово')).toBeVisible();
  await exportRegion.getByRole('button', { name: 'Скачать ZIP' }).click();
  await expect.poll(async () => (await tma.state()).downloads).toHaveLength(1);
  expect((await tma.state()).downloads[0]).toEqual(
    expect.objectContaining({ fileName: 'your-fitness-coach-data.zip' }),
  );

  await tmaPage.getByText('Способы входа', { exact: true }).click();
  await tmaPage.getByRole('button', { name: 'Отключить Google' }).click();
  const unlinkDialog = tmaPage.getByRole('dialog', { name: 'Отключить Google?' });
  await expect(unlinkDialog).toContainText('Аккаунт, профиль и история останутся на месте');
  await unlinkDialog.getByRole('button', { name: 'Отключить Google' }).click();
  await expect.poll(() => api.accountUnlinks()).toEqual(['google']);
  await expect(tmaPage.getByRole('button', { name: 'Отключить Telegram' })).toBeDisabled();
  await expect(tmaPage.getByText('Сначала привяжите другой способ входа.')).toBeVisible();

  const deleteTrigger = tmaPage.getByRole('button', { name: 'Удалить аккаунт', exact: true });
  await deleteTrigger.click();
  const deleteDialog = tmaPage.getByRole('dialog', {
    name: 'Удалить аккаунт без возможности восстановления?',
  });
  const confirmation = deleteDialog.getByLabel('Введите УДАЛИТЬ, чтобы подтвердить');
  const deleteForever = deleteDialog.getByRole('button', {
    name: 'Удалить аккаунт навсегда',
  });
  await expect(confirmation).toBeFocused();
  await confirmation.fill('удалить');
  await expect(deleteForever).toBeDisabled();
  await confirmation.fill('УДАЛИТЬ');
  await expect(deleteForever).toBeEnabled();
  await tma.setSafeArea({ top: 26, right: 2, bottom: 24, left: 2 });
  await tma.setContentSafeArea({ top: 38, right: 0, bottom: 18, left: 0 });
  await tma.setViewport(560, MOBILE_CONTEXTS.baseline.height, false);
  await deleteForever.scrollIntoViewIfNeeded();
  await expect(deleteForever).toBeInViewport();
  await expectTouchTargets(deleteDialog.locator('button'));
  await expectNoHorizontalOverflow(tmaPage);
  await tmaPage.keyboard.press('Escape');
  await expect(deleteDialog).not.toBeAttached();
  await expect(deleteTrigger).toBeFocused();

  await tmaPage.reload();
  await tmaPage.getByRole('link', { name: 'Безопасность' }).click();
  await expect(
    tmaPage.getByRole('region', { name: 'Копия данных' }).getByText('Готово'),
  ).toBeVisible();
  expect(api.accountDeletes()).toBe(0);
});

test('account export expired and error states keep one safe recovery action on Mobile Web', async ({
  browser,
}) => {
  for (const state of ['expired', 'error'] as const) {
    const context = await browser.newContext({
      viewport: MOBILE_CONTEXTS.compact,
      hasTouch: true,
      isMobile: true,
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    const api = await installPlatformApi(page, {
      browserSession: true,
      accountExportState: state,
      authProviders: ['telegram'],
    });
    await page.goto('/app?section=profile');
    await page.getByRole('link', { name: 'Безопасность' }).click();
    const exportRegion = page.getByRole('region', { name: 'Копия данных' });
    await expect(
      exportRegion.getByText(state === 'expired' ? 'Срок истёк' : 'Ошибка'),
    ).toBeVisible();
    const recovery = exportRegion.getByRole('button', {
      name: state === 'error' ? 'Повторить подготовку' : 'Подготовить архив',
    });
    await expect(recovery).toBeVisible();
    await recovery.click();
    await expect.poll(() => api.accountExportCreates()).toBe(1);
    await expect(exportRegion.getByText('Готово')).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await context.close();
  }
});

test('account lifecycle layout matches Mobile Web and dark TMA at the same viewport', async ({
  browser,
}) => {
  const mobileContext = await browser.newContext({
    viewport: MOBILE_CONTEXTS.baseline,
    hasTouch: true,
    isMobile: true,
    reducedMotion: 'reduce',
  });
  const tmaContext = await browser.newContext({
    viewport: MOBILE_CONTEXTS.baseline,
    hasTouch: true,
    isMobile: true,
    reducedMotion: 'reduce',
  });
  const mobile = await mobileContext.newPage();
  const tma = await tmaContext.newPage();
  await mobile.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
  await installTelegramHarness(tma, {
    colorScheme: 'dark',
    viewportHeight: MOBILE_CONTEXTS.baseline.height,
    viewportStableHeight: MOBILE_CONTEXTS.baseline.height,
  });
  await installPlatformApi(mobile, {
    browserSession: true,
    accountExportState: 'ready',
    authProviders: ['telegram', 'google'],
  });
  await installPlatformApi(tma, {
    accountExportState: 'ready',
    authProviders: ['telegram', 'google'],
  });
  await Promise.all([mobile.goto('/app?section=profile'), tma.goto('/app?section=profile')]);
  for (const page of [mobile, tma]) {
    await page.getByRole('link', { name: 'Безопасность' }).click();
    await page.mouse.move(0, 0);
    await expect(page.getByRole('region', { name: 'Копия данных' })).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
    await expectNoHorizontalOverflow(page);
  }
  const signatures = await Promise.all(
    [mobile, tma].map((page) =>
      page.getByRole('region', { name: 'Копия данных' }).evaluate((region) => {
        const download = region.querySelector<HTMLElement>('.ui-button--primary');
        return {
          className: region.className,
          display: getComputedStyle(region).display,
          downloadRadius: download ? getComputedStyle(download).borderRadius : null,
          downloadBackground: download ? getComputedStyle(download).backgroundColor : null,
        };
      }),
    ),
  );
  expect(signatures[0]).toEqual(signatures[1]);
  await mobileContext.close();
  await tmaContext.close();
});

test('captures account lifecycle owner checkpoint across required viewports and states', async ({
  browser,
}) => {
  const cases = [
    {
      name: 'desktop-1440x900-light-ready',
      width: 1440,
      height: 900,
      state: 'ready' as const,
      providers: ['telegram', 'google'],
    },
    {
      name: 'tablet-768x1024-dark-ready',
      width: 768,
      height: 1024,
      state: 'ready' as const,
      providers: ['telegram', 'google'],
      dark: true,
    },
    {
      name: 'mobile-web-430x900-light-error',
      width: 430,
      height: 900,
      state: 'error' as const,
      providers: ['telegram', 'google'],
    },
    {
      name: 'mobile-web-390x844-light-last-identity',
      width: 390,
      height: 844,
      state: 'ready' as const,
      providers: ['telegram'],
      identityGuard: true,
    },
    {
      name: 'mobile-web-360x800-light-expired',
      width: 360,
      height: 800,
      state: 'expired' as const,
      providers: ['telegram', 'google'],
    },
    {
      name: 'tma-390x844-dark-ready',
      width: 390,
      height: 844,
      state: 'ready' as const,
      providers: ['telegram', 'google'],
      tma: true,
    },
    {
      name: 'tma-360x800-dark-delete-confirmation',
      width: 360,
      height: 800,
      state: 'ready' as const,
      providers: ['telegram', 'google'],
      tma: true,
      deleteConfirmation: true,
    },
  ];

  for (const item of cases) {
    const context = await browser.newContext({
      viewport: { width: item.width, height: item.height },
      hasTouch: item.width < 768,
      isMobile: item.width < 768,
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    if (item.tma) {
      await installTelegramHarness(page, {
        colorScheme: 'dark',
        viewportHeight: item.height,
        viewportStableHeight: item.height,
      });
    } else if (item.dark) {
      await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
    }
    await installPlatformApi(page, {
      browserSession: !item.tma,
      accountExportState: item.state,
      authProviders: item.providers,
    });
    await page.goto('/app?section=profile');
    await page.getByRole('link', { name: 'Безопасность' }).click();
    const exportRegion = page.getByRole('region', { name: 'Копия данных' });
    await expect(exportRegion).toBeVisible();
    if (item.identityGuard) {
      await page.getByText('Способы входа', { exact: true }).click();
      await expect(page.getByText('Сначала привяжите другой способ входа.')).toBeVisible();
    }
    if (item.deleteConfirmation) {
      await page.getByRole('button', { name: 'Удалить аккаунт', exact: true }).click();
      await expect(
        page.getByRole('dialog', { name: 'Удалить аккаунт без возможности восстановления?' }),
      ).toBeVisible();
    } else {
      await exportRegion.scrollIntoViewIfNeeded();
      if (item.state === 'expired' || item.state === 'error') {
        await exportRegion
          .getByRole('button', {
            name: item.state === 'error' ? 'Повторить подготовку' : 'Подготовить архив',
          })
          .evaluate((element) => element.scrollIntoView({ block: 'center' }));
      }
    }
    await expectNoHorizontalOverflow(page);
    await page.screenshot({
      path: `../.artifacts/screenshots/task-65/${item.name}.png`,
      animations: 'disabled',
    });
    await context.close();
  }
});
