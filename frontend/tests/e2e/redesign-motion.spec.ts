import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';

test.use({ video: 'on' });

for (const width of [390, 1440]) {
  test(`content-driven final repetition ${width}`, async ({ page }, testInfo) => {
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
    const metrics = await scene.evaluate((element) => {
      const sticky = element.querySelector<HTMLElement>('.strength-scene__sticky');
      if (!sticky) throw new Error('Strength scene content is missing');
      return {
        sceneHeight: element.getBoundingClientRect().height,
        stickyHeight: sticky.getBoundingClientRect().height,
        position: getComputedStyle(sticky).position,
      };
    });
    expect(metrics.position).toBe('relative');
    expect(metrics.sceneHeight - metrics.stickyHeight).toBeLessThanOrEqual(1);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(scene).toHaveAttribute('data-phase', '2');
    await expect(scene.locator('[data-reps]')).toHaveText('3');
    await expect(scene.locator('.strength-scene__raised')).toHaveCSS('opacity', '1');
    await expect(scene.locator('.strength-scene__result')).toHaveCSS('opacity', '1');
  });
}
