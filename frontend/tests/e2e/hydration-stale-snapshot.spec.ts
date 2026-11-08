import { expect, test } from '@playwright/test';
import { emptyHydrationDay, installPlatformApi } from './fixtures/platform-api';

test('a stale tab reuses the pending water request', async ({ page, context }) => {
  const date = '2026-10-10';
  const other = await context.newPage();
  const saved = new Map<string, Record<string, unknown>>();
  const keys: string[] = [];
  let release = () => {};
  const responses = new Promise<void>((resolve) => {
    release = resolve;
  });
  for (const current of [page, other]) {
    await current.addInitScript(() => {
      Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined });
      const original = Storage.prototype.getItem;
      Storage.prototype.getItem = function (key: string) {
        const state = window as unknown as { forceStale: boolean };
        if (key === 'fit_hydration_pending_v2_user_7' && state.forceStale) {
          state.forceStale = false;
          return null;
        }
        return original.call(this, key);
      };
    });
    await installPlatformApi(current, { browserSession: true, fixedDate: date });
    await current.route('**/api/v1/nutrition/hydration/entries/v2', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      const request = route.request();
      const key = request.headers()['idempotency-key'];
      if (!key) throw new Error('Missing idempotency key');
      expect(request.headers()['x-yfc-hydration-protocol']).toBe('2');
      keys.push(key);
      if (!saved.has(key))
        saved.set(key, {
          id: 900 + saved.size,
          ...request.postDataJSON(),
          occurred_at: `${date}T09:00:00Z`,
          timezone: 'Europe/Moscow',
          created_at: `${date}T09:00:00Z`,
          updated_at: `${date}T09:00:00Z`,
        });
      await responses;
      return route.fulfill({ status: 201, json: saved.get(key) });
    });
    await current.route('**/api/v1/nutrition/hydration?*', async (route) => {
      const entries = Array.from(saved.values());
      return route.fulfill({
        json: { ...emptyHydrationDay(date), entries, total_ml: entries.length * 250 },
      });
    });
    await current.goto(`/app?section=nutrition&date=${date}`);
    await expect(current.getByRole('region', { name: 'Гидратация' })).toBeVisible();
  }
  const glass = (current: typeof page) =>
    current
      .getByRole('region', { name: 'Гидратация' })
      .getByRole('button', { name: /Стакан, добавить 250 мл/ });
  try {
    await glass(page).click();
    await expect.poll(() => keys.length).toBe(1);
    await other.evaluate(() => {
      (window as unknown as { forceStale: boolean }).forceStale = true;
    });
    await glass(other).click();
    await expect.poll(() => keys.length).toBe(2);
    expect(keys[1]).toBe(keys[0]);
    expect(saved.size).toBe(1);
  } finally {
    release();
  }
  await expect(page.getByText('Добавлено 250 мл')).toBeVisible();
  await expect(other.getByText('Добавлено 250 мл')).toBeVisible();
});
