import { test, expect } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

test.use({ serviceWorkers: 'block' });
for (const width of [360, 390, 430, 1440]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`icon review ${width} ${theme}`, async ({ page }, testInfo) => {
      test.setTimeout(90000);
      const output = process.env.ICON_REVIEW_OUTPUT ?? testInfo.outputPath('icon-review');
      mkdirSync(output, { recursive: true });
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await page.clock.setFixedTime(new Date('2026-09-12T09:00:00Z'));
      await installPlatformApi(page, { browserSession: true, fixedDate: '2026-09-12' });
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));
      const capture = async (name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await expectNoHorizontalOverflow(page);
        await page.screenshot({
          path: resolve(output, `${name}-${width}-${theme}.png`),
          fullPage: true,
        });
      };
      for (const section of ['today', 'programs', 'nutrition', 'progress', 'profile']) {
        await page.goto(`/app?section=${section}`);
        await expect(page.locator('h1').first()).toBeVisible();
        await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
        await capture(section);
        if (section === 'today') {
          const waterAction = page.getByRole('link', { name: '+ Вода', exact: true });
          const alignment = await waterAction.evaluate((element) => {
            const icon = element.querySelector('svg')!.getBoundingClientRect();
            const text = [...element.childNodes].find((node) =>
              node.textContent?.includes('Вода'),
            )!;
            const range = document.createRange();
            range.selectNode(text);
            const label = range.getBoundingClientRect();
            return {
              horizontal: icon.right <= label.left + 4,
              vertical: Math.abs(icon.y + icon.height / 2 - label.y - label.height / 2),
            };
          });
          expect(alignment.horizontal).toBe(true);
          expect(alignment.vertical).toBeLessThan(6);
          const add = page.getByRole('button', { name: 'Быстро добавить', exact: true });
          await add.hover();
          await add.focus();
          await capture('focus');
          await page.keyboard.press('Enter');
          const sheet = page.getByRole('dialog', { name: 'Что добавить?' });
          await expect(sheet).toBeVisible();
          await capture('quick-add');
          await page.keyboard.press('Tab');
          await expect(sheet.locator(':focus')).toHaveCount(1);
          await page.keyboard.press('Escape');
          await expect(sheet).toBeHidden();
          await expect(add).toBeFocused();
        }
      }
      for (const [name, url] of [
        ['food-form', '/app?section=nutrition&quick_add=food'],
        ['cardio-form', '/app?section=today&cardio=1'],
        ['wellbeing-form', '/app?section=today&wellbeing=1'],
        ['measurements', '/app?section=progress&focus=measurements'],
        ['water', '/app?section=nutrition&hydration=quick'],
      ]) {
        await page.goto(url!);
        await expect(page.locator('h1').first()).toBeVisible();
        await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
        if (name === 'cardio-form') {
          const select = page.getByRole('combobox').first();
          await expect(select).toHaveCSS('background-image', /^url\(.*svg.*radial-gradient/);
          await select.focus();
          await expect(select).toBeFocused();
        }
        await capture(name!);
      }
      await page.goto('/');
      await expect(page.locator('h1').first()).toBeVisible();
      await capture('landing');
      expect(errors).toEqual([]);
    });
  }
}
