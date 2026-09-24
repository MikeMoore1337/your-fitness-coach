import { expect, test } from '@playwright/test';

test.use({ serviceWorkers: 'allow' });

test('serves the install manifest, canonical icons and service worker contract', async ({
  page,
  request,
}) => {
  const manifestResponse = await request.get('/manifest.webmanifest');
  expect(manifestResponse.ok()).toBe(true);
  expect(manifestResponse.headers()['content-type']).toContain('application/manifest+json');
  expect(manifestResponse.headers()['cache-control']).toMatch(/no-store|no-cache/);

  const manifest = await manifestResponse.json();
  expect(manifest).toMatchObject({
    id: '/app',
    start_url: '/app?source=pwa',
    scope: '/',
    display: 'standalone',
    lang: 'ru',
  });
  expect(manifest.icons).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ src: '/assets/brand/pwa-icon.svg', purpose: 'any' }),
      expect.objectContaining({ src: '/assets/brand/pwa-icon-maskable.svg', purpose: 'maskable' }),
    ]),
  );

  for (const iconPath of [
    '/assets/brand/pwa-icon.svg',
    '/assets/brand/pwa-icon-maskable.svg',
    '/assets/brand/apple-touch-icon.png',
  ]) {
    const iconResponse = await request.get(iconPath);
    expect(iconResponse.ok()).toBe(true);
  }

  const serviceWorkerResponse = await request.get('/sw.js');
  expect(serviceWorkerResponse.ok()).toBe(true);
  expect(serviceWorkerResponse.headers()['content-type']).toContain('javascript');
  expect(serviceWorkerResponse.headers()['cache-control']).toMatch(/no-store|no-cache/);
  const serviceWorkerSource = await serviceWorkerResponse.text();
  expect(serviceWorkerSource).toContain("url.pathname.startsWith('/api/')");
  expect(serviceWorkerSource).toContain("url.pathname.startsWith('/static/')");
  expect(serviceWorkerSource).toContain("assetPath.startsWith('brand/')");
  expect(serviceWorkerSource).toContain("assetPath.startsWith('providers/')");
  expect(serviceWorkerSource).toContain("assetPath.startsWith('marketing/')");
  expect(serviceWorkerSource).toContain("assetPath.startsWith('product/')");
  expect(serviceWorkerSource).toContain("self.addEventListener('push'");
  expect(serviceWorkerSource).toContain("self.addEventListener('notificationclick'");
  expect(serviceWorkerSource).toContain(
    "PUSH_NOTIFICATION_PATH = '/app?section=profile#profile-notifications'",
  );
  expect(serviceWorkerSource).toContain('PUSH_NOTIFICATION_BODY');
  expect(serviceWorkerSource).toContain('private notification details are loaded only');

  await page.goto('/');
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
    'href',
    '/manifest.webmanifest',
  );
  await page.waitForFunction(
    () =>
      navigator.serviceWorker.getRegistration('/').then((registration) => Boolean(registration)),
    undefined,
    { timeout: 10_000 },
  );

  const cacheKeys = await page.evaluate(async () => {
    const names = await caches.keys();
    const keys: string[] = [];
    for (const name of names.filter((item) => item.startsWith('yfc-pwa-'))) {
      const cache = await caches.open(name);
      keys.push(...(await cache.keys()).map((request) => request.url));
    }
    return keys;
  });
  expect(cacheKeys.every((key) => !new URL(key).pathname.startsWith('/api/'))).toBe(true);
});
