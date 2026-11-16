import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test } from '@playwright/test';
import { emptyHydrationDay, installPlatformApi } from './fixtures/platform-api';

// In PR #1459 CI, Actions builds the exact pre-change dev revision separately.
// Both real JS bundles are then exercised on ONE origin with shared browser storage.
test('real legacy and v2 tabs cannot double-write, but distinct v2 drinks persist', async ({
  page,
  context,
}) => {
  const oldDist = process.env.YFC_LEGACY_HYDRATION_DIST;
  test.skip(!oldDist, 'Requires the SHA-pinned pre-change frontend in CI');
  if (!oldDist) throw new Error('Missing the legacy frontend build');
  expect(existsSync(join(oldDist, 'index.html'))).toBe(true);

  const date = '2026-10-10';
  const oldPage = await context.newPage();
  let legacyJavascriptLoaded = 0;
  const matchesOldDocument = (url: URL) => url.pathname === '/app';
  const matchesOldAsset = (url: URL) => url.pathname.startsWith('/assets/');
  await oldPage.route(matchesOldDocument, async (route) => {
    await route.fulfill({ path: join(oldDist, 'index.html'), contentType: 'text/html' });
  });
  await oldPage.route(matchesOldAsset, async (route) => {
    const asset = new URL(route.request().url()).pathname.slice('/assets/'.length);
    if (!/^[a-zA-Z0-9._-]+$/.test(asset)) return route.abort();
    const oldAsset = join(oldDist, 'assets', asset);
    if (!existsSync(oldAsset)) return route.fallback();
    if (asset.endsWith('.js')) legacyJavascriptLoaded += 1;
    return route.fulfill({ path: oldAsset });
  });

  const saved = new Map<string, Record<string, unknown>>();
  const newKeys: string[] = [];
  let rejectedLegacyWrites = 0;
  for (const current of [oldPage, page]) {
    await current.setViewportSize({ width: 393, height: 844 });
    await installPlatformApi(current, { browserSession: true, fixedDate: date });
    await current.route('**/api/v1/nutrition/hydration/entries', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      rejectedLegacyWrites += 1;
      return route.fulfill({
        status: 409,
        json: { detail: 'Обновите приложение для безопасной записи воды.' },
      });
    });
    await current.route('**/api/v1/nutrition/hydration/entries/v2', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      const request = route.request();
      expect(request.headers()['x-yfc-hydration-protocol']).toBe('2');
      const key = request.headers()['idempotency-key'];
      if (!key) throw new Error('Missing idempotency key');
      newKeys.push(key);
      if (!saved.has(key)) {
        saved.set(key, {
          id: 900 + saved.size,
          ...request.postDataJSON(),
          occurred_at: `${date}T09:00:00Z`,
          timezone: 'Europe/Moscow',
          created_at: `${date}T09:00:00Z`,
          updated_at: `${date}T09:00:00Z`,
        });
      }
      return route.fulfill({ status: 201, json: saved.get(key) });
    });
    await current.route('**/api/v1/nutrition/hydration?*', (route) => {
      const entries = Array.from(saved.values());
      return route.fulfill({
        json: { ...emptyHydrationDay(date), entries, total_ml: entries.length * 250 },
      });
    });
  }

  await oldPage.goto(`/app?section=nutrition&date=${date}`);
  await page.goto(`/app?section=nutrition&date=${date}`);
  const hydration = (tab: typeof page) => tab.getByRole('region', { name: 'Гидратация' });
  const glass = (current: typeof page) =>
    hydration(current).getByRole('button', { name: /Стакан, добавить 250 мл/ });

  await expect(glass(oldPage)).toBeEnabled();
  await expect(glass(page)).toBeEnabled();
  await expect.poll(() => legacyJavascriptLoaded).toBeGreaterThan(0);

  // An already loaded old tab cannot insert a record on the updated backend.
  await glass(oldPage).click();
  await expect.poll(() => rejectedLegacyWrites).toBe(1);
  expect(saved.size).toBe(0);

  await glass(page).click();
  await expect.poll(() => saved.size).toBe(1);
  await expect(hydration(page).getByText('Добавлено 250 мл')).toBeVisible();

  // Distinct explicit drinks must NOT be deduplicated by time or volume.
  await glass(page).click();
  await expect.poll(() => saved.size).toBe(2);
  expect(newKeys).toHaveLength(2);
  expect(newKeys[1]).not.toBe(newKeys[0]);
  expect(rejectedLegacyWrites).toBe(1);
});
