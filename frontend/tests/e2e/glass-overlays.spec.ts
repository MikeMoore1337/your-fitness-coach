import { expect, test, type Locator } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { expectNoHorizontalOverflow, installTelegramHarness } from './fixtures/mobile-tma';

async function expectReadableGlass(panel: Locator) {
  await expect(panel).toBeVisible();
  const contrast = await panel.evaluate((element) => {
    const style = getComputedStyle(element);
    const rgba = (value: string) => value.match(/[\d.]+/g)!.map(Number);
    const bg = rgba(style.backgroundColor);
    const fg = rgba(style.color);
    const luminance = (rgb: number[]) =>
      rgb.reduce((sum, channel, index) => {
        const value = channel / 255;
        const weight = [0.2126, 0.7152, 0.0722][index];
        if (weight === undefined) throw new Error('Expected three RGB channels');
        return sum + (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4) * weight;
      }, 0);
    const alpha = bg[3] ?? 1;
    const ratios = [0, 255].map((behind) => {
      const background = luminance(
        bg.slice(0, 3).map((channel) => channel * alpha + behind * (1 - alpha)),
      );
      const foreground = luminance(fg.slice(0, 3));
      return (Math.max(background, foreground) + 0.05) / (Math.min(background, foreground) + 0.05);
    });
    return { alpha, minimum: Math.min(...ratios) };
  });
  expect(contrast.alpha).toBeGreaterThan(0.5);
  expect(contrast.alpha).toBeLessThan(1);
  expect(contrast.minimum).toBeGreaterThanOrEqual(4.5);
}

for (const theme of ['light', 'dark'] as const) {
  test(`touch overlay in mocked TMA ${theme}`, async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      colorScheme: theme,
      reducedMotion: 'reduce',
    });
    try {
      const page = await context.newPage();
      await installTelegramHarness(page, { colorScheme: theme });
      await installPlatformApi(page);
      await page.goto('/app?section=nutrition');
      await page.getByRole('button', { name: 'Быстро добавить', exact: true }).tap();
      const panel = page.getByRole('dialog', { name: 'Что добавить?' });
      await expectReadableGlass(panel);
      await expectNoHorizontalOverflow(page);
      await page.getByRole('button', { name: 'Закрыть быстрые действия' }).tap();
      await expect(panel).toBeHidden();
    } finally {
      await context.close();
    }
  });

  for (const width of [360, 390, 430, 1440]) {
    test(`overlay readability and dismissal ${theme} ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true });
      const exercise = {
        id: 1,
        title: 'Тяга верхнего блока',
        slug: 'lat-pulldown',
        primary_muscle: 'Спина',
        equipment: 'Тросовый блок',
        primary_muscle_ids: ['back'],
        secondary_muscle_ids: ['biceps'],
        equipment_ids: ['cable'],
        alternatives: [],
        difficulty_level: 'beginner',
        is_custom: false,
        is_personalized: false,
        has_guide: false,
      };
      await page.route('**/api/v1/programs/exercises', (route) =>
        route.fulfill({ json: [exercise] }),
      );
      await page.route('**/api/v1/programs/exercises/1', (route) =>
        route.fulfill({ json: exercise }),
      );
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));

      await page.goto('/app?section=profile');
      await page.getByRole('link', { name: 'Личные данные', exact: true }).click();
      const avatarButton = page.getByRole('button', { name: 'Изменить аватар' });
      await avatarButton.click();
      const avatar = page.getByRole('dialog', { name: 'Аватар', exact: true });
      await expectReadableGlass(avatar);
      await expectNoHorizontalOverflow(page);
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: testInfo.outputPath(`avatar-${theme}-${width}.png`) });
      await page.keyboard.press('Escape');
      await expect(avatar).toBeHidden();
      await expect(avatarButton).toBeFocused();

      await page.goto('/app?section=nutrition');
      await page
        .getByRole('region', { name: 'Завтрак', exact: true })
        .getByRole('button', { name: /Добавить/ })
        .click();
      const picker = page.locator('.nutrition-picker__panel');
      await expectReadableGlass(picker);
      await expectNoHorizontalOverflow(page);
      await page.screenshot({ path: testInfo.outputPath(`nutrition-${theme}-${width}.png`) });
      await page.keyboard.press('Escape');
      await expect(picker).toBeHidden();

      await page.getByRole('button', { name: 'Быстро добавить', exact: true }).click();
      const quickAdd = page.getByRole('dialog', { name: 'Что добавить?' });
      await expectReadableGlass(quickAdd);
      await page.keyboard.press('Escape');
      await expect(quickAdd).toBeHidden();

      await page.goto('/app?section=catalog');
      await page
        .getByRole('button', { name: /Техника и детали:|Подробнее:/ })
        .first()
        .click();
      const guide = page.locator('.exercise-guide-modal__panel');
      await expectReadableGlass(guide);
      // Portal surfaces must retain the same material outside the shell subtree.
      expect(
        await guide.evaluate((element) => element.closest('.app-shell--design-v2') === null),
      ).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`exercise-${theme}-${width}.png`) });
      const session = await page.context().newCDPSession(page);
      await session.send('Emulation.setEmulatedMedia', {
        features: [
          { name: 'prefers-color-scheme', value: theme },
          { name: 'prefers-reduced-transparency', value: 'reduce' },
        ],
      });
      await expect(guide).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(32, 37, 37)' : 'rgb(243, 245, 245)',
      );
      await page.emulateMedia({ forcedColors: 'active' });
      expect(
        await guide.evaluate((element) =>
          getComputedStyle(element).backgroundColor.startsWith('rgb('),
        ),
      ).toBe(true);
      await page.keyboard.press('Escape');
      await expect(guide).toBeHidden();
      expect(errors).toEqual([]);
    });
  }
}
