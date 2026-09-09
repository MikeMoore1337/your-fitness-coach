import { expect, test, type Page } from '@playwright/test';

const canonicalSvgPaths = [
  '/assets/brand/favicon.svg',
  '/assets/brand/favicon-light.svg',
  '/assets/brand/favicon-dark.svg',
  '/assets/brand/yfc-logo-light.svg',
  '/assets/brand/yfc-logo-dark.svg',
  '/assets/brand/yfc-mark-light.svg',
  '/assets/brand/yfc-mark-dark.svg',
];

async function assertHeaderMark(page: Page, surface: 'light' | 'dark', size: number) {
  const mark = page.locator('.landing-header .landing-brand__mark');
  await expect(mark).toBeVisible();
  await expect(mark).toHaveAttribute('src', `/assets/brand/yfc-mark-${surface}.svg`);
  await expect(mark).toHaveCSS('width', `${size}px`);
  await expect(mark).toHaveCSS('height', `${size}px`);
  await expect(mark).toHaveCSS('object-fit', 'contain');
  await expect(mark).toHaveAttribute('alt', '');
}

test('canonical brand assets render on light and dark public surfaces', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const viewport of [
    { name: 'desktop', width: 1440, height: 900 },
    { name: 'mobile', width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    await page.evaluate(() => {
      window.localStorage.removeItem('app-theme');
      window.localStorage.removeItem('landing-theme');
    });
    await page.reload();
    await assertHeaderMark(page, 'light', viewport.name === 'mobile' ? 34 : 42);
    const wordmark = page.locator('.landing-header .yfc-lockup__wordmark');
    await expect(wordmark).toBeVisible();
    const brandBounds = await page.locator('.public-shell__brand').boundingBox();
    const actionBounds = await page.locator('.public-shell__header-actions').boundingBox();
    expect((brandBounds?.x ?? 0) + (brandBounds?.width ?? 0)).toBeLessThanOrEqual(
      actionBounds?.x ?? 0,
    );
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);

    if (viewport.name === 'desktop') {
      await page.screenshot({ path: '../.artifacts/brand/landing-light-desktop.png' });
    }

    await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
    await assertHeaderMark(page, 'dark', viewport.name === 'mobile' ? 34 : 42);
    await expect(page.locator('#landing-title')).toHaveCSS('color', 'rgb(245, 245, 245)');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);

    if (viewport.name === 'mobile') {
      await page.screenshot({ path: '../.artifacts/brand/landing-dark-mobile.png' });
    }

    await page.goto('/login');
    if (viewport.name === 'mobile') {
      await assertHeaderMark(page, 'dark', 40);
      await expect(page.locator('.landing-header .yfc-lockup__wordmark')).toBeVisible();
    } else {
      await expect(page.locator('.login-continuation-brand .yfc-lockup__mark')).toBeVisible();
      await expect(page.locator('.login-continuation-brand .yfc-lockup__wordmark')).toBeVisible();
    }

    await page.goto('/training');
    await expect(page.locator('.public-header .yfc-lockup__wordmark')).toBeVisible();
    await expect(page.locator('.public-footer .yfc-lockup__wordmark')).toBeVisible();

    await page.goto('/demo');
    await expect(page.locator('.demo-header__brand .yfc-lockup__wordmark')).toBeVisible();
  }
});

test('favicon is canonical SVG and remains distinct at 16 and 32 pixels', async ({ page }) => {
  await page.goto('/');

  await expect(page.locator('link[rel="icon"]:not([media])')).toHaveAttribute(
    'href',
    '/assets/brand/favicon.svg',
  );
  await expect(
    page.locator('link[rel="icon"][media="(prefers-color-scheme: light)"]'),
  ).toHaveAttribute('href', '/assets/brand/favicon-light.svg');
  await expect(
    page.locator('link[rel="icon"][media="(prefers-color-scheme: dark)"]'),
  ).toHaveAttribute('href', '/assets/brand/favicon-dark.svg');
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute(
    'href',
    '/assets/brand/apple-touch-icon.png',
  );

  for (const assetPath of canonicalSvgPaths) {
    const source = await page.evaluate(async (path) => {
      const response = await fetch(path);
      return { body: await response.text(), ok: response.ok };
    }, assetPath);
    expect(source.ok).toBe(true);
    expect(source.body).not.toMatch(/(?:data:|<image\b|(?:href|src)="https?:\/\/|@font-face)/i);
  }

  await page.setViewportSize({ width: 720, height: 420 });
  await page.setContent(`
    <style>
      body { display: grid; gap: 20px; margin: 0; padding: 20px; background: #f1f3ec; }
      .dark { padding: 20px; background: #0d120f; }
      img { display: block; width: 180px; height: auto; }
    </style>
    <img src="/assets/brand/yfc-logo-light.svg" width="180" height="150" alt="Your Fitness Coach" />
    <div class="dark"><img src="/assets/brand/yfc-logo-dark.svg" width="180" height="150" alt="Your Fitness Coach" /></div>
  `);
  await expect(page.getByRole('img', { name: 'Your Fitness Coach' })).toHaveCount(2);
  await page.screenshot({ path: '../.artifacts/brand/logo-variants.png' });

  await page.setViewportSize({ width: 96, height: 64 });
  await page.setContent(`
    <style>
      body { display: flex; gap: 24px; align-items: center; margin: 8px; background: #0d120f; }
      img { display: block; }
    </style>
    <img src="/assets/brand/favicon-dark.svg" width="16" height="16" alt="" />
    <img src="/assets/brand/favicon-dark.svg" width="32" height="32" alt="" />
  `);
  await expect(page.locator('img')).toHaveCount(2);
  await page.screenshot({ path: '../.artifacts/brand/favicon-16-32-dark.png' });
});
