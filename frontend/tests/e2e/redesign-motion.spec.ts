import { expect, test, type Locator, type Page } from '@playwright/test';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';

test.use({ video: 'on' });

async function scrollToProgress(page: Page, scene: Locator, progress: number) {
  const range = await scene.evaluate((element) => {
    const section = element as HTMLElement;
    const sticky = element.querySelector<HTMLElement>('.strength-scene__sticky');
    if (!sticky) throw new Error('Strength scene content is missing');
    return {
      range: section.offsetHeight - sticky.offsetHeight,
      top: element.getBoundingClientRect().top + window.scrollY,
    };
  });
  await page.evaluate(
    ({ progress: value, range: scrollRange, top }) =>
      window.scrollTo({ top: top + scrollRange * value, behavior: 'auto' }),
    { progress, range: range.range, top: range.top },
  );
}

for (const width of [390, 1440]) {
  test(`scroll-driven strength sequence ${width}`, async ({ page }, testInfo) => {
    const height = width === 390 ? 844 : 1000;
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.goto('/');
    await page.evaluate(() => document.fonts.ready);
    const scene = page.locator('.strength-scene');
    await scene.scrollIntoViewIfNeeded();
    await expectNoHorizontalOverflow(page);
    await expect(scene.locator('[data-step]')).toHaveCount(3);
    await expect(scene.getByRole('button')).toHaveCount(0);

    const metrics = await scene.evaluate((element) => {
      const sticky = element.querySelector<HTMLElement>('.strength-scene__sticky');
      if (!sticky) throw new Error('Strength scene content is missing');
      return {
        sceneHeight: element.getBoundingClientRect().height,
        stickyHeight: sticky.getBoundingClientRect().height,
        position: getComputedStyle(sticky).position,
        viewportHeight: window.innerHeight,
      };
    });
    expect(metrics.position).toBe('sticky');
    expect(metrics.sceneHeight / metrics.viewportHeight).toBeGreaterThanOrEqual(2);
    expect(metrics.sceneHeight / metrics.viewportHeight).toBeLessThanOrEqual(2.5);
    expect(metrics.sceneHeight - metrics.stickyHeight).toBeGreaterThan(
      metrics.viewportHeight * 0.9,
    );

    await scrollToProgress(page, scene, 0.1);
    await expect(scene).toHaveAttribute('data-phase', '0');
    await expect(scene.locator('[data-reps]')).toHaveText('2');
    await page.screenshot({ path: testInfo.outputPath(`strength-${width}-effort.png`) });

    await scrollToProgress(page, scene, 0.65);
    await expect(scene).toHaveAttribute('data-phase', '1');
    await expect(scene.locator('[data-record]')).toHaveText('18 кг × 3');
    await expect(scene.locator('[data-reps]')).toHaveText('3');
    await expect(scene.locator('.strength-scene__result')).toBeHidden();
    await page.screenshot({ path: testInfo.outputPath(`strength-${width}-record.png`) });

    await scrollToProgress(page, scene, 0.9);
    await expect(scene).toHaveAttribute('data-phase', '2');
    await expect(scene.locator('.strength-scene__result')).toBeVisible();
    await expect
      .poll(() =>
        scene
          .locator('.strength-scene__result')
          .evaluate((element) => Number.parseFloat(getComputedStyle(element).opacity)),
      )
      .toBeGreaterThan(0.95);
    await page.screenshot({ path: testInfo.outputPath(`strength-${width}-result.png`) });

    await scrollToProgress(page, scene, 0.65);
    await expect(scene).toHaveAttribute('data-phase', '1');
    await scrollToProgress(page, scene, 0.1);
    await expect(scene).toHaveAttribute('data-phase', '0');
    await expect(scene.locator('[data-reps]')).toHaveText('2');

    const stickyPosition = await scene.evaluate((element) => {
      const sticky = element.querySelector<HTMLElement>('.strength-scene__sticky');
      if (!sticky) throw new Error('Strength scene content is missing');
      return sticky.getBoundingClientRect().top;
    });
    expect(Math.abs(stickyPosition)).toBeLessThanOrEqual(1);

    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(scene).toHaveAttribute('data-phase', '2');
    await expect
      .poll(() =>
        scene.evaluate((element) => {
          const sticky = element.querySelector<HTMLElement>('.strength-scene__sticky');
          if (!sticky) throw new Error('Strength scene content is missing');
          return (
            getComputedStyle(sticky).position === 'relative' &&
            element.getBoundingClientRect().height < window.innerHeight * 1.25
          );
        }),
      )
      .toBe(true);
    await expect(scene.locator('.strength-scene__result')).toHaveCSS('opacity', '1');
    const reducedMetrics = await scene.evaluate((element) => {
      const sticky = element.querySelector<HTMLElement>('.strength-scene__sticky');
      if (!sticky) throw new Error('Strength scene content is missing');
      return {
        sceneHeight: element.getBoundingClientRect().height,
        position: getComputedStyle(sticky).position,
        viewportHeight: window.innerHeight,
      };
    });
    expect(reducedMetrics.position).toBe('relative');
    expect(reducedMetrics.sceneHeight).toBeLessThan(reducedMetrics.viewportHeight * 1.25);
  });
}
