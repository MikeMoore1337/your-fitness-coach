import { expect, test } from '@playwright/test';
import { emptyHydrationDay, installPlatformApi } from './fixtures/platform-api';
import { installTelegramHarness } from './fixtures/mobile-tma';

test('a lost water response is retried once after reload and a later glass is new', async ({
  page,
}) => {
  const date = '2026-10-10';
  await page.setViewportSize({ width: 393, height: 844 });
  await installPlatformApi(page, { browserSession: true, fixedDate: date });
  const saved = new Map<string, Record<string, unknown>>();
  const keys: string[] = [];
  await page.route('**/api/v1/nutrition/hydration/entries/v2', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const request = route.request();
    const key = request.headers()['idempotency-key'];
    if (!key) throw new Error('Missing idempotency key');
    expect(request.headers()['x-yfc-hydration-protocol']).toBe('2');
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

test('a second tab retries a lost response before adding a new glass', async ({
  page,
  context,
}) => {
  const date = '2026-10-10';
  const other = await context.newPage();
  const saved = new Map<string, Record<string, unknown>>();
  const keys: string[] = [];
  for (const current of [page, other]) {
    await current.setViewportSize({ width: 393, height: 844 });
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
      if (keys.length === 1) return route.abort('connectionreset');
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
  const firstWater = page.getByRole('region', { name: 'Гидратация' });
  const secondWater = other.getByRole('region', { name: 'Гидратация' });
  await firstWater.getByRole('button', { name: /Стакан, добавить 250 мл/ }).click();
  await expect(firstWater.getByRole('button', { name: 'Повторить без дубля' })).toBeVisible();
  await secondWater.getByRole('button', { name: /Стакан, добавить 250 мл/ }).click();
  await expect(secondWater.getByText('Добавлено 250 мл')).toBeVisible();
  expect(keys[1]).toBe(keys[0]);
  expect(saved.size).toBe(1);
  await expect(firstWater.getByRole('button', { name: 'Повторить без дубля' })).toBeHidden();
  await secondWater.getByRole('button', { name: /Стакан, добавить 250 мл/ }).click();
  await expect.poll(() => saved.size).toBe(2);
  expect(keys[2]).not.toBe(keys[0]);
});

test('a late lost response cannot undo confirmation from another tab', async ({
  page,
  context,
}) => {
  const date = '2026-10-10';
  const other = await context.newPage();
  const saved = new Map<string, Record<string, unknown>>();
  const keys: string[] = [];
  let releaseFirst = () => {};
  const firstResponse = new Promise<void>((resolve) => {
    releaseFirst = resolve;
  });
  for (const current of [page, other]) {
    await installPlatformApi(current, { browserSession: true, fixedDate: date });
    await current.route('**/api/v1/nutrition/hydration/entries/v2', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      const request = route.request();
      const key = request.headers()['idempotency-key'];
      if (!key) throw new Error('Missing idempotency key');
      expect(request.headers()['x-yfc-hydration-protocol']).toBe('2');
      keys.push(key);
      const first = keys.length === 1;
      if (!saved.has(key))
        saved.set(key, {
          id: 900 + saved.size,
          ...request.postDataJSON(),
          occurred_at: `${date}T09:00:00Z`,
          timezone: 'Europe/Moscow',
          created_at: `${date}T09:00:00Z`,
          updated_at: `${date}T09:00:00Z`,
        });
      if (first) {
        await firstResponse;
        return route.abort('connectionreset');
      }
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
  const firstWater = page.getByRole('region', { name: 'Гидратация' });
  const secondWater = other.getByRole('region', { name: 'Гидратация' });
  await firstWater.getByRole('button', { name: /Стакан, добавить 250 мл/ }).click();
  await expect.poll(() => keys.length).toBe(1);
  await secondWater.getByRole('button', { name: /Стакан, добавить 250 мл/ }).click();
  await expect(secondWater.getByText('Добавлено 250 мл')).toBeVisible();
  expect(keys[1]).toBe(keys[0]);
  expect(saved.size).toBe(1);
  releaseFirst();
  await expect(page.getByText('Запись уже сохранена.')).toBeVisible();
  await expect(firstWater.getByRole('button', { name: /Стакан, добавить 250 мл/ })).toBeEnabled();
  await firstWater.getByRole('button', { name: /Стакан, добавить 250 мл/ }).click();
  await expect.poll(() => saved.size).toBe(2);
  expect(keys[2]).not.toBe(keys[0]);
});

test('simultaneous tabs use one request key without Web Locks', async ({ page, context }) => {
  const date = '2026-10-10';
  const other = await context.newPage();
  const saved = new Map<string, Record<string, unknown>>();
  const keys: string[] = [];
  let release = () => {};
  const responses = new Promise<void>((resolve) => {
    release = resolve;
  });
  for (const current of [page, other]) {
    await current.addInitScript(() =>
      Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined }),
    );
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
    await Promise.all([glass(page).click(), glass(other).click()]);
    await expect.poll(() => keys.length).toBe(2);
    expect(keys[1]).toBe(keys[0]);
    expect(saved.size).toBe(1);
  } finally {
    release();
  }
  await expect(page.getByText('Добавлено 250 мл')).toBeVisible();
  await expect(other.getByText('Добавлено 250 мл')).toBeVisible();
});

test('mocked Telegram retries water after a lost response', async ({ page }) => {
  const date = '2026-10-10';
  await page.setViewportSize({ width: 393, height: 844 });
  await installTelegramHarness(page);
  await installPlatformApi(page, { fixedDate: date });
  const saved = new Map<string, Record<string, unknown>>();
  const keys: string[] = [];
  await page.route('**/api/v1/nutrition/hydration/entries/v2', async (route) => {
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
    if (keys.length === 1) return route.abort('connectionreset');
    return route.fulfill({ status: 201, json: saved.get(key) });
  });
  await page.goto(`/app?section=nutrition&date=${date}`);
  const hydration = page.getByRole('region', { name: 'Гидратация' });
  const glass = hydration.getByRole('button', { name: /Стакан, добавить 250 мл/ });
  await glass.click();
  await expect(hydration.getByRole('button', { name: 'Повторить без дубля' })).toBeVisible();
  await glass.click();
  await expect(hydration.getByText('Добавлено 250 мл')).toBeVisible();
  expect(keys[1]).toBe(keys[0]);
  expect(saved.size).toBe(1);
  await glass.click();
  await expect.poll(() => saved.size).toBe(2);
  expect(keys[2]).not.toBe(keys[0]);
});
