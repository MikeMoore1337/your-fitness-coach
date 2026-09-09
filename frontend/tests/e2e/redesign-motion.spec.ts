import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';

test.use({ video: 'on' });

for (const width of [390, 1440]) {
  test(`scroll-controlled final repetition ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.goto('/');
    await page.evaluate(() => document.fonts.ready);
    const scene = page.locator('.strength-scene');
    await scene.scrollIntoViewIfNeeded();
    await expectNoHorizontalOverflow(page);
    await expect(scene.locator('[data-step]')).toHaveCount(3);
    await expect(scene.getByRole('button')).toHaveCount(0);
    const bounds = await scene.boundingBox();
    expect(bounds).not.toBeNull();
    await page.mouse.wheel(0, bounds!.y);
    await expect(scene).toHaveAttribute('data-phase', '0');
    await page.screenshot({ path: testInfo.outputPath('effort.png') });
    const stickyHeight = await scene
      .locator('.strength-scene__sticky')
      .evaluate((node) => node.clientHeight);
    const travel = bounds!.height - stickyHeight;
    await page.mouse.wheel(0, travel * 0.67);
    await expect(scene).toHaveAttribute('data-phase', '1');
    await expect(scene.locator('[data-reps]')).toHaveText('3');
    await expect(scene.locator('.strength-scene__raised')).toHaveCSS('opacity', '1');
    await page.screenshot({ path: testInfo.outputPath('record.png') });
    await page.mouse.wheel(0, travel * 0.28);
    await expect(scene).toHaveAttribute('data-phase', '2');
    await expect(scene.locator('.strength-scene__result')).toHaveCSS('opacity', '1');
    await page.screenshot({ path: testInfo.outputPath('result.png') });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.mouse.wheel(0, -travel * 0.8);
    await expect(scene).toHaveAttribute('data-phase', '2');
    await expect(scene.locator('.strength-scene__raised')).toHaveCSS('opacity', '1');
    await expect(scene.locator('.strength-scene__sticky')).toHaveCSS('position', 'relative');
  });
}
