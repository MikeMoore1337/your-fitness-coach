import { expect, test } from '@playwright/test';

test('weekly score can be opened while its chapter enters', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/', { waitUntil: 'networkidle' });

  const chapter = page.locator('#progress');
  const summary = chapter.locator('.ref-weekly summary');
  await summary.scrollIntoViewIfNeeded();
  const animation = await chapter.evaluate((element) => {
    element.setAttribute('data-motion-phase', 'idle');
    void element.getBoundingClientRect();
    element.setAttribute('data-motion-phase', 'enter');
    return getComputedStyle(element).animationName;
  });
  expect(animation).toBe('landing-progress-static-entry');
  await expect(chapter).toHaveCSS('transform', 'none');
  const bounds = await summary.boundingBox();
  expect(bounds).not.toBeNull();
  await page.mouse.move(bounds!.x + bounds!.width / 2, bounds!.y + bounds!.height / 2);
  await page.mouse.down();
  await expect(chapter).toHaveCSS('transform', 'none');
  await page.mouse.up();
  await expect(chapter.locator('.ref-scores label').first()).toBeVisible();
});

test.describe('Landing #903 weekly score scale', () => {
  for (const theme of ['light', 'dark'] as const) {
    for (const width of [390, 1440]) {
      for (const route of ['/', '/for-athletes']) {
        test(`${route} ${theme} ${width}px keeps the score scale circular and accessible`, async ({
          page,
        }) => {
          await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
          await page.emulateMedia({ colorScheme: theme });
          await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
          await page.goto(route, { waitUntil: 'networkidle' });

          const summary = page.locator('.ref-weekly summary');
          await summary.click();
          const scores = page.locator('.ref-scores label');
          await expect(scores).toHaveCount(5);
          await expect(scores.first()).toBeVisible();
          const styleValues = await scores.evaluateAll((elements) =>
            elements.map((element) => {
              const style = getComputedStyle(element);
              const bounds = element.getBoundingClientRect();
              return {
                borderStyle: style.borderStyle,
                borderRadius: style.borderRadius,
                minWidth: style.minWidth,
                minHeight: style.minHeight,
                width: Math.round(bounds.width),
                height: Math.round(bounds.height),
              };
            }),
          );
          expect(styleValues).toHaveLength(5);
          expect(new Set(styleValues.map(({ width, height }) => `${width}x${height}`)).size).toBe(
            1,
          );
          expect(styleValues[0]).toEqual(
            expect.objectContaining({
              borderStyle: 'solid',
              borderRadius: '50%',
              minWidth: '44px',
              minHeight: '44px',
              width: 44,
              height: 44,
            }),
          );

          const firstRadio = page.getByRole('radio', { name: '1', exact: true });
          await summary.focus();
          await expect(summary).toBeFocused();
          await page.keyboard.press('Tab');
          await expect(firstRadio).toBeFocused();
          const focusStyle = await scores
            .nth(0)
            .locator('span')
            .evaluate((element) => {
              const style = getComputedStyle(element);
              return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
            });
          expect(focusStyle.outlineStyle).toBe('solid');
          expect(focusStyle.outlineWidth).toBe('2px');

          await page.keyboard.press('Space');
          await expect(firstRadio).toBeChecked();
          await page.keyboard.press('ArrowRight');
          await expect(page.getByRole('radio', { name: '2', exact: true })).toBeChecked();

          const selected = scores.nth(4);
          await selected.click();
          await expect(page.getByRole('radio', { name: '5', exact: true })).toBeChecked();
          await expect(selected).toHaveCSS('border-radius', '50%');
          await expect
            .poll(() => selected.evaluate((element) => getComputedStyle(element).backgroundColor))
            .toContain('178, 245, 32');
          const selectedStyles = await selected.evaluate((element) => {
            const style = getComputedStyle(element);
            const focusRing = element.querySelector('span');
            const focusStyle = focusRing ? getComputedStyle(focusRing) : null;
            return {
              backgroundColor: style.backgroundColor,
              boxShadow: style.boxShadow,
              outlineStyle: style.outlineStyle,
              focusOutlineStyle: focusStyle?.outlineStyle,
            };
          });
          expect(selectedStyles.backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
          expect(selectedStyles.boxShadow).toBe('none');
          expect(selectedStyles.outlineStyle).toBe('none');
          expect(selectedStyles.focusOutlineStyle).toBe('none');
        });
      }
    }
  }
});
