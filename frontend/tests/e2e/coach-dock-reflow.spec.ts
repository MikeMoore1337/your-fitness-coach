import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { installTelegramHarness } from './fixtures/mobile-tma';

for (const width of [196, 320, 360, 390, 393, 430]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`coach navigation stays readable at ${width}px with enlarged text in ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 852 });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, trainerActive: true });
      await page.goto('/coach');
      const nav = page.getByRole('navigation', { name: 'Основная навигация' });
      const links = nav.locator('.app-bottom-nav__primary a');
      await expect(links).toHaveCount(4);
      await page.evaluate(() => {
        document.documentElement.style.fontSize = '32px';
      });
      await page.evaluate(() => document.fonts.ready);
      await expect
        .poll(() =>
          links.evaluateAll((elements) => {
            const boxes = elements.map((element) => element.getBoundingClientRect());
            return elements.map((element, index) => {
              const label = element.querySelector<HTMLElement>('.app-bottom-nav__label')!;
              const box = boxes[index]!;
              return {
                text: label.textContent?.trim(),
                fits: label.scrollWidth <= label.clientWidth + 1,
                target: box.width >= 44 && box.height >= 44,
                separated: boxes.every(
                  (other, otherIndex) =>
                    index === otherIndex ||
                    Math.min(box.right, other.right) <= Math.max(box.left, other.left) ||
                    Math.min(box.bottom, other.bottom) <= Math.max(box.top, other.top),
                ),
              };
            });
          }),
        )
        .toEqual(
          ['Сегодня', 'Клиенты', 'Программы', 'Ещё'].map((text) => ({
            text,
            fits: true,
            target: true,
            separated: true,
          })),
        );
      await expect(links.first()).toHaveAttribute('aria-current', 'page');
      const navBox = (await nav.boundingBox())!;
      expect(navBox.x).toBeGreaterThanOrEqual(0);
      expect(navBox.x + navBox.width).toBeLessThanOrEqual(width);
      expect(navBox.y).toBeGreaterThanOrEqual(0);
      expect(navBox.y + navBox.height).toBeLessThanOrEqual(852);
      await links.nth(1).focus();
      await expect(links.nth(1)).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(/tab=clients/);
      await expect(nav.getByRole('link', { name: 'Клиенты' })).toHaveAttribute(
        'aria-current',
        'page',
      );
    });
  }
}

test('coach navigation returns to one row when text size and viewport are restored', async ({
  page,
}) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await installPlatformApi(page, { browserSession: true, trainerActive: true });
  await page.goto('/coach');
  const nav = page.getByRole('navigation', { name: 'Основная навигация' });
  await expect(nav).toHaveAttribute('data-dock-columns', '4');
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '32px';
  });
  await expect(nav).toHaveAttribute('data-dock-columns', '2');
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '16px';
  });
  await expect(nav).toHaveAttribute('data-dock-columns', '4');
});

test('coach navigation keeps readable labels inside emulated Telegram safe areas', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 852 });
  await installTelegramHarness(page, {
    viewportHeight: 852,
    viewportStableHeight: 852,
    safeAreaInset: { top: 44, right: 0, bottom: 34, left: 0 },
  });
  await installPlatformApi(page, { browserSession: false, trainerActive: true });
  await page.goto('/coach');
  const nav = page.getByRole('navigation', { name: 'Основная навигация' });
  const labels = nav.locator('.app-bottom-nav__primary .app-bottom-nav__label');
  await expect(labels).toHaveCount(4);
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '32px';
  });
  await expect
    .poll(() =>
      labels.evaluateAll((elements) =>
        elements.every((element) => element.scrollWidth <= element.clientWidth + 1),
      ),
    )
    .toBe(true);
  const navBox = (await nav.boundingBox())!;
  expect(navBox.y + navBox.height).toBeLessThanOrEqual(852 - 34);
});

test('coach dock remains stable while viewport changes', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 390, height: 844 });
  await installPlatformApi(page, { browserSession: true, trainerActive: true });
  await page.goto('/coach?tab=tools');
  await expect(page.locator('.coach-tools-hub')).toBeVisible();
  for (const width of [390, 1280, 320, 430, 1440, 360, 1280, 390, 430, 320]) {
    await page.setViewportSize({ width, height: width < 900 ? 844 : 1000 });
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    );
  }
  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
  expect(errors).toEqual([]);
});
