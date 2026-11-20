import { expect, test, type Locator } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

async function expectTextInsideControl(control: Locator) {
  const geometry = await control.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    const range = document.createRange();
    range.selectNodeContents(element);
    return {
      bounds: bounds.toJSON(),
      viewportWidth: innerWidth,
      lines: Array.from(range.getClientRects(), (line) => line.toJSON()),
    };
  });
  expect(geometry.lines.length).toBeGreaterThan(0);
  for (const line of geometry.lines) {
    expect(line.left).toBeGreaterThanOrEqual(geometry.bounds.left - 1);
    expect(line.right).toBeLessThanOrEqual(
      Math.min(geometry.bounds.right, geometry.viewportWidth) + 1,
    );
  }
}

for (const width of [320, 360, 390, 393, 430]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`Progress period labels remain readable at 200% text, ${width}px ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 852 });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, fixedDate: '2026-11-17' });
      await page.goto('/app?section=progress');
      const periods = page.getByRole('tablist', { name: 'Период прогресса' }).getByRole('tab');
      await expect(periods).toHaveText(['7 дней', '30 дней', '90 дней', 'Свой период']);
      await expect(periods.nth(1)).toHaveAttribute('aria-selected', 'true');
      await page.evaluate(() => {
        document.documentElement.style.fontSize = '32px';
      });
      await page.evaluate(() => document.fonts.ready);
      for (const period of await periods.all()) {
        await expectTextInsideControl(period);
        const box = (await period.boundingBox())!;
        expect(box.width).toBeGreaterThanOrEqual(44);
        expect(box.height).toBeGreaterThanOrEqual(44);
      }
      const help = page.locator('.progress-hero__help summary');
      await expectTextInsideControl(help);
      await help.focus();
      await page.keyboard.press('Enter');
      await expect(page.locator('.progress-hero__help details')).toHaveAttribute('open', '');
      await expectTextInsideControl(help);
      const title = (await page.locator('.progress-hero__copy h1').boundingBox())!;
      const helpBox = (await help.boundingBox())!;
      expect(helpBox.y).toBeGreaterThanOrEqual(title.y + title.height - 1);
      await page.keyboard.press('Escape');
      await expect(page.locator('.progress-hero__help details')).not.toHaveAttribute('open', '');
      await expect(help).toBeFocused();
      await periods.last().focus();
      const focus = await periods.last().evaluate((element) => {
        const control = element.getBoundingClientRect();
        const viewport = element
          .closest('.progress-period-controls__tabs')!
          .getBoundingClientRect();
        const style = getComputedStyle(element);
        return {
          visible: element.matches(':focus-visible'),
          outline: style.outlineStyle,
          extent: parseFloat(style.outlineWidth) + Math.max(0, parseFloat(style.outlineOffset)),
          control: control.toJSON(),
          viewport: viewport.toJSON(),
        };
      });
      expect(focus.visible).toBe(true);
      expect(focus.outline).not.toBe('none');
      expect(focus.control.left - focus.extent).toBeGreaterThanOrEqual(focus.viewport.left - 1);
      expect(focus.control.right + focus.extent).toBeLessThanOrEqual(focus.viewport.right + 1);
      expect(focus.control.top - focus.extent).toBeGreaterThanOrEqual(focus.viewport.top - 1);
      expect(focus.control.bottom + focus.extent).toBeLessThanOrEqual(focus.viewport.bottom + 1);
      await page.keyboard.press('Enter');
      await expect(periods.last()).toHaveAttribute('aria-selected', 'true');
      await expect(page.getByLabel('Начало периода')).toBeVisible();
      await expect(page.getByLabel('Конец периода')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
    });

    test(`Workout header remains readable at 200% text, ${width}px ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 852 });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, {
        browserSession: true,
        fixedDate: '2026-11-17',
        workoutStatus: 'in_progress',
      });
      await page.goto('/app?section=today');
      await page.evaluate(() => {
        document.documentElement.style.fontSize = '32px';
      });
      await page.getByRole('button', { name: 'Продолжить тренировку', exact: true }).click();
      const header = page.locator('.today-workout-focus__header');
      await expect(header.getByText('Текущая тренировка', { exact: true })).toBeVisible();
      await expectTextInsideControl(header.locator('strong'));
      await expectTextInsideControl(header.getByRole('button', { name: 'К сводке' }));
      const title = (await header.locator('strong').boundingBox())!;
      const back = (await header.getByRole('button', { name: 'К сводке' }).boundingBox())!;
      expect(title.y).toBeGreaterThanOrEqual(back.y + back.height - 1);
      await header.getByRole('button', { name: 'К сводке' }).click();
      await expect(
        page.getByRole('button', { name: 'Продолжить тренировку', exact: true }),
      ).toBeVisible();
    });
  }
}

test('ordinary mobile text retains the single-row period and workout headers', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 852 });
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: '2026-11-17',
    workoutStatus: 'in_progress',
  });
  await page.goto('/app?section=progress');
  const periods = page.getByRole('tablist', { name: 'Период прогресса' }).getByRole('tab');
  await expect(periods).toHaveCount(4);
  const rows = await periods.evaluateAll((elements) =>
    elements.map((element) => Math.round(element.getBoundingClientRect().top)),
  );
  expect(new Set(rows).size).toBe(1);
  await page.goto('/app?section=today');
  await page.getByRole('button', { name: 'Продолжить тренировку', exact: true }).click();
  const header = page.locator('.today-workout-focus__header');
  const title = (await header.locator('strong').boundingBox())!;
  const back = (await header.getByRole('button', { name: 'К сводке' }).boundingBox())!;
  expect(title.x).toBeGreaterThanOrEqual(back.x + back.width - 1);
});
