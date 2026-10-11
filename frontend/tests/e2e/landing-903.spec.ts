import { expect, test } from '@playwright/test';

test.describe('Landing #903 weekly score scale', () => {
  for (const theme of ['light', 'dark'] as const) {
    for (const width of [390, 1440]) {
      test(`${theme} ${width}px keeps the score scale circular and accessible`, async ({
        page,
      }) => {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        await page.goto('/for-athletes', { waitUntil: 'networkidle' });

        const summary = page.locator('.ref-weekly summary');
        await summary.click();
        const scores = page.locator('.ref-scores label');
        await expect(scores).toHaveCount(5);
        const styleValues = await scores.evaluateAll((elements) =>
          elements.map((element) => {
            const style = getComputedStyle(element);
            return {
              borderStyle: style.borderStyle,
              borderRadius: style.borderRadius,
              minWidth: style.minWidth,
              minHeight: style.minHeight,
            };
          }),
        );
        expect(styleValues).toEqual(
          expect.arrayContaining([
            expect.objectContaining({
              borderStyle: 'none',
              borderRadius: '50%',
              minWidth: '44px',
              minHeight: '44px',
            }),
          ]),
        );

        const selected = scores.nth(4);
        await selected.click();
        await expect(page.getByRole('radio', { name: '5', exact: true })).toBeChecked();
        await expect(selected).toHaveCSS('border-radius', '50%');
        const selectedBackground = await selected.evaluate(
          (element) => getComputedStyle(element).backgroundColor,
        );
        expect(selectedBackground).not.toBe('rgba(0, 0, 0, 0)');

        await page.getByRole('radio', { name: '1', exact: true }).focus();
        const focused = await scores.nth(0).evaluate((element) => {
          const style = getComputedStyle(element);
          return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
        });
        expect(focused.outlineStyle).toBe('solid');
        expect(focused.outlineWidth).toBe('2px');
      });
    }
  }
});
