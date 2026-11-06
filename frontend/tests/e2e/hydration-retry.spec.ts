import { expect, test } from '@playwright/test';
import { emptyHydrationDay, installPlatformApi } from './fixtures/platform-api';

test('a lost water response is retried once after reload and a later glass is new', async ({
  page,
}) => {
  const date = '2026-10-10';
  await page.setViewportSize({ width: 393, height: 844 });
  await installPlatformApi(page, { browserSession: true, fixedDate: date });
  const saved = new Map<string, Record<string, unknown>>();
  const keys: string[] = [];
  await page.route('**/api/v1/nutrition/hydration/entries', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const request = route.request();
    const key = request.headers()['idempotency-key'];
    if (!key) throw new Error('Missing idempotency key');
    keys.push(key);
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
    if (keys.length === 1) return route.abort('connectionreset');
    return route.fulfill({ status: 201, json: saved.get(key) });
  });
  await page.route('**/api/v1/nutrition/hydration?*', async (route) => {
    const entries = Array.from(saved.values());
    return route.fulfill({
      json: { ...emptyHydrationDay(date), entries, total_ml: entries.length * 250 },
    });
  });
  await page.goto(`/app?section=nutrition&date=${date}`);
  const hydration = page.getByRole('region', { name: 'Гидратация' });
  const glass = hydration.getByRole('button', { name: /Стакан, добавить 250 мл/ });
  await glass.click();
  await expect(hydration.getByRole('button', { name: 'Повторить без дубля' })).toBeVisible();
  await page.reload();
  await expect(hydration.getByRole('button', { name: 'Повторить без дубля' })).toBeVisible();
  await glass.click();
  await expect(hydration.getByText('Добавлено 250 мл')).toBeVisible();
  expect(keys[1]).toBe(keys[0]);
  expect(saved.size).toBe(1);
  await glass.click();
  await expect.poll(() => saved.size).toBe(2);
  expect(keys[2]).not.toBe(keys[0]);
  await expect(hydration.getByText('500 мл записано')).toBeVisible();
});
