import { expect } from '@playwright/test';
import { expectNoHorizontalOverflow, test } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

for (const viewport of [
  { width: 320, height: 760 },
  { width: 393, height: 844 },
  { width: 1440, height: 900 },
]) {
  for (const theme of ['dark', 'light'] as const) {
    test(
      '#1326 control center provides bounded, focused navigation at ' +
        viewport.width +
        'px ' +
        theme,
      async ({ page }, testInfo) => {
        await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        await page.setViewportSize(viewport);
        await page.goto('/app?section=programs&view=manage');

        await expect(page.getByRole('heading', { name: 'Центр управления' })).toBeVisible();
        const actions = page.getByRole('navigation', { name: 'Управление программой' });
        await expect(actions.getByRole('button')).toHaveCount(4);
        await expect(page.locator('#program-library')).toBeHidden();
        await expectNoHorizontalOverflow(page);

        await testInfo.attach('1326-overview-' + theme + '-' + viewport.width, {
          body: await page.screenshot({ animations: 'disabled' }),
          contentType: 'image/png',
        });

        await actions.getByRole('button', { name: /Программы и шаблоны/ }).click();
        await expect(page.locator('#program-library')).toBeVisible();
        await expect(page).toHaveURL(/panel=library/);
        await expectNoHorizontalOverflow(page);

        await page.getByRole('button', { name: 'К центру управления' }).click();
        await expect(actions).toBeVisible();
        await actions.getByRole('button', { name: /Заменить программу/ }).click();
        await expect(page.getByRole('button', { name: 'Подбор по параметрам' })).toBeVisible();
        await expectNoHorizontalOverflow(page);
      },
    );
  }
}

test('#1326 legacy deep links still open focused destinations', async ({ page }) => {
  await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
  await page.goto('/app?section=programs&view=manage&start=templates');
  await expect(page.locator('#program-library')).toBeVisible();

  await page.goto('/app?section=programs&view=manage&start=create');
  await expect(page.locator('#program-builder')).toBeVisible();

  await page.goto('/app?section=programs&view=manage&start=generator');
  await expect(page.getByRole('heading', { name: 'Заменить программу', level: 1 })).toBeVisible();
  await expect(page.getByRole('dialog')).toBeVisible();
});
