import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import {
  expectNoHorizontalOverflow,
  installTelegramHarness,
  TelegramHarness,
} from './fixtures/mobile-tma';

test.use({ serviceWorkers: 'block' });

for (const theme of ['dark', 'light'] as const) {
  test(`glass contrast, progress clarity and material fallbacks ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    await installPlatformApi(page, { browserSession: true, progressState: 'populated' });
    await page.goto('/app?section=progress');
    await expect(page.locator('.progress-overview')).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    const meta = page.locator('[data-time-zone]');
    await expect(meta).toHaveAttribute('data-time-zone', 'Europe/Moscow');
    await expect(meta).toContainText(/Москв/);
    await expect(meta).not.toContainText('Europe/');
    const help = page.locator('.progress-hero__help summary');
    await expect(help).toHaveText('О показателях');
    await help.click();
    const rail = page.locator('.progress-category-nav__rail');
    await page.getByRole('button', { name: 'Следующие разделы прогресса' }).click();
    await expect.poll(() => rail.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
    await expect(rail.locator('a:focus')).toHaveAttribute('data-clipped', 'false');
    await expect(page).not.toHaveURL(/progress_view=/);
    await page.getByRole('button', { name: 'Предыдущие разделы прогресса' }).click();
    await expect(rail.locator('a:focus')).toHaveAttribute('data-clipped', 'false');
    await expect(page.locator('.progress-hero__help details')).toHaveAttribute('open');
    await help.click();
    const download = (await page.locator('.progress-hero__download').boundingBox())!;
    const sections = (await page
      .getByRole('navigation', { name: 'Разделы прогресса' })
      .boundingBox())!;
    expect(sections.y - download.y - download.height).toBeLessThanOrEqual(4);
    const downloadTextBottom = await page
      .getByRole('link', { name: 'Скачать отчёт' })
      .evaluate((element) => {
        const text = document.createRange();
        text.selectNodeContents(element);
        return text.getBoundingClientRect().bottom;
      });
    const categoryText = (await rail.locator('a strong').first().boundingBox())!;
    expect(categoryText.y - downloadTextBottom).toBeLessThanOrEqual(34);

    const add = page.getByRole('button', { name: 'Быстро добавить', exact: true });
    await add.click();
    const sheet = page.getByRole('dialog', { name: 'Что добавить?' });
    await expect(sheet).toHaveCSS('backdrop-filter', /blur\(20px\)/);
    for (const surface of [sheet, page.locator('#appBottomNav')]) {
      const alpha = await surface.evaluate((element) => {
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = 1;
        const context = canvas.getContext('2d')!;
        context.fillStyle = getComputedStyle(element).backgroundColor;
        context.fillRect(0, 0, 1, 1);
        return context.getImageData(0, 0, 1, 1).data[3]! / 255;
      });
      expect(alpha).toBeGreaterThanOrEqual(0.9 - 1 / 255);
      expect(alpha).toBeLessThan(1);
    }
    await expect(page.locator('.progress-overview')).not.toHaveAttribute('data-glass');
    const contrast = await page.evaluate(() => {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 1;
      const context = canvas.getContext('2d')!;
      const rgba = (color: string) => {
        context.clearRect(0, 0, 1, 1);
        context.fillStyle = color;
        context.fillRect(0, 0, 1, 1);
        return [...context.getImageData(0, 0, 1, 1).data].map((value) => value / 255);
      };
      const blend = (foreground: number[], background: number[]) =>
        foreground
          .slice(0, 3)
          .map(
            (value, index) => value * foreground[3]! + background[index]! * (1 - foreground[3]!),
          );
      const luminance = (rgb: number[]) =>
        rgb
          .slice(0, 3)
          .reduce(
            (sum, value, index) =>
              sum +
              (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4) *
                [0.2126, 0.7152, 0.0722][index]!,
            0,
          );
      const ratio = (a: number[], b: number[]) =>
        (Math.max(luminance(a), luminance(b)) + 0.05) /
        (Math.min(luminance(a), luminance(b)) + 0.05);
      return [
        ...document.querySelectorAll(
          '#appBottomNav .app-bottom-nav__label, .app-quick-add-action__copy, .app-quick-add-action__icon, .app-quick-add-trigger',
        ),
      ].map((node) => {
        const material = node.closest('[data-glass]')!;
        const style = getComputedStyle(material);
        const foreground = rgba(getComputedStyle(node).color);
        const ownBackground = rgba(getComputedStyle(node.parentElement!).backgroundColor);
        const ratios = [0, 1].map((behind) => {
          let background = blend(rgba(style.backgroundColor), [behind, behind, behind]);
          const highlight = Number(style.getPropertyValue('--glass-highlight-opacity'));
          background = blend([1, 1, 1, highlight], background);
          background = blend([1, 1, 1, 0.07], background);
          if (!node.matches('.app-quick-add-trigger'))
            background = blend(ownBackground, background);
          return ratio(foreground, background);
        });
        return {
          text: node.textContent,
          minimum: Math.min(...ratios),
          required: node.matches('.app-quick-add-action__icon') ? 3 : 4.5,
        };
      });
    });
    for (const item of contrast)
      expect(item.minimum, JSON.stringify(item)).toBeGreaterThanOrEqual(item.required);
    await page.keyboard.press('Escape');
    await expect(add).toBeFocused();
    expect(
      await add.evaluate((element) =>
        getComputedStyle(element)
          .transitionDuration.split(',')
          .every((value) => parseFloat(value) <= 0.0001),
      ),
    ).toBe(true);

    // Activate the real stylesheet's preference rule; WebKit has no native Playwright emulation for it.
    const preferenceRules = await page.evaluate(() => {
      let count = 0;
      for (const stylesheet of document.styleSheets)
        for (const rule of stylesheet.cssRules) {
          if (
            rule instanceof CSSMediaRule &&
            rule.conditionText.includes('prefers-reduced-transparency')
          ) {
            rule.media.mediaText = 'all';
            count++;
          }
        }
      return count;
    });
    expect(preferenceRules).toBeGreaterThan(0);
    await expect(page.locator('#appBottomNav')).toHaveCSS('backdrop-filter', 'none');
    await expect(page.locator('#appBottomNav')).toHaveCSS(
      'background-color',
      theme === 'dark' ? 'rgb(32, 37, 37)' : 'rgb(243, 245, 245)',
    );
    await expect(add).toHaveCSS('background-color', 'rgb(178, 245, 32)');

    await page.reload();
    await expect(page.locator('#appBottomNav')).toHaveCSS('backdrop-filter', /blur\(12px\)/);
    // Exercise the unsupported-backdrop branch by removing only its @supports opt-in.
    const supportRules = await page.evaluate(() => {
      let count = 0;
      for (const stylesheet of document.styleSheets)
        for (let index = stylesheet.cssRules.length - 1; index >= 0; index--) {
          const rule = stylesheet.cssRules[index];
          if (
            rule instanceof CSSSupportsRule &&
            rule.conditionText.includes('backdrop-filter') &&
            rule.cssText.includes('[data-glass]')
          ) {
            stylesheet.deleteRule(index);
            count++;
          }
        }
      return count;
    });
    expect(supportRules).toBeGreaterThan(0);
    await expect(page.locator('#appBottomNav')).toHaveCSS('backdrop-filter', 'none');
    await add.click();
    await expect(sheet).toHaveCSS('backdrop-filter', 'none');
    await expect(sheet).toHaveCSS(
      'background-color',
      theme === 'dark' ? 'rgb(32, 37, 37)' : 'rgb(243, 245, 245)',
    );
    await expectNoHorizontalOverflow(page);
  });

  test(`glass TMA safe areas, keyboard and reachable bottom content ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 844 });
    await installTelegramHarness(page, {
      colorScheme: theme,
      safeAreaInset: { top: 24, right: 0, bottom: 34, left: 0 },
    });
    const tma = new TelegramHarness(page);
    await installPlatformApi(page, { fixedDate: '2026-10-09', progressState: 'populated' });
    await page.goto('/app?section=progress');
    await expect(page.locator('.progress-overview')).toBeVisible();
    for (const width of [320, 360, 393, 430]) {
      await page.setViewportSize({ width, height: 844 });
      const dock = page.locator('#appBottomNav');
      await expect(dock).toHaveCSS('backdrop-filter', /blur\(12px\)/);
      expect((await dock.boundingBox())!.y + 60).toBeLessThanOrEqual(844 - 34 - 12);
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      const bottom = page
        .locator('#appContent a, #appContent button, #appContent summary')
        .filter({ visible: true })
        .last();
      await bottom.scrollIntoViewIfNeeded();
      const target = (await bottom.boundingBox())!;
      expect(target.y + target.height).toBeLessThanOrEqual((await dock.boundingBox())!.y);
      expect(
        await bottom.evaluate((element) => {
          const box = element.getBoundingClientRect();
          return element.contains(
            document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2),
          );
        }),
      ).toBe(true);
      const add = page.getByRole('button', { name: 'Быстро добавить', exact: true });
      await add.click();
      const sheet = page.getByRole('dialog', { name: 'Что добавить?' });
      await tma.setViewport(480, 844);
      await sheet.getByRole('link').last().scrollIntoViewIfNeeded();
      const box = (await sheet.boundingBox())!;
      expect(box.y).toBeGreaterThanOrEqual(24);
      expect(box.y + box.height).toBeLessThanOrEqual(480 - 34);
      await tma.clickBack();
      await expect(sheet).toHaveCount(0);
      await tma.setViewport(844, 844);
      await expect(add).toBeVisible();
      await expect(dock).toBeVisible();
      await page.getByRole('tab', { name: 'Свой период', exact: true }).click();
      await page.getByLabel('Начало периода', { exact: true }).focus();
      await tma.setViewport(480, 844);
      await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
      await expect(add).toBeHidden();
      await expect(dock).toBeHidden();
      await page.getByRole('heading', { name: 'Прогресс', exact: true }).click();
      await tma.setViewport(844, 844);
      await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'hidden');
      await page
        .locator('.progress-period-controls__custom')
        .getByRole('button', { name: 'Отмена', exact: true })
        .click();
      await expect(dock).toBeVisible();
      await expectNoHorizontalOverflow(page);
    }
  });
}
