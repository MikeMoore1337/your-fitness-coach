import { expect, test, type Page, type Route } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { installPlatformApi } from './fixtures/platform-api';

const date = '2026-11-05';
const names = [
  'Рис белый отварной',
  'Рис бурый отварной',
  'Гречка отварная',
  'Куриная грудка запечённая',
  'Творог натуральный',
  'Яблоко свежее',
];
const foods = names.map((name, index) => ({
  id: 100 + index,
  name,
  brand: null,
  barcode: null,
  energy_kcal_per_100g: '100.00',
  protein_g_per_100g: '5.000',
  fat_g_per_100g: '2.000',
  carbs_g_per_100g: '15.000',
  fiber_g_per_100g: null,
  standard_serving_amount: null,
  standard_serving_unit: null,
  standard_serving_weight_g: null,
  food_type: 'system',
  catalog_quality: 'verified',
  nutrition_basis_kind: 'per_100_g',
  is_favorite: false,
  last_used_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}));
const firstFood = foods[0];
if (!firstFood) throw new Error('Synthetic food fixture is empty');

async function installSyntheticNutrition(page: Page) {
  await page.clock.setFixedTime(new Date(`${date}T09:00:00+03:00`));
  await installPlatformApi(page, { browserSession: true, fixedDate: date });
  const entries: Record<string, unknown>[] = [];
  const postedIds: number[] = [];
  const batchRequests: Array<{ key: string | undefined; ids: number[] }> = [];
  await page.route('**/api/v1/nutrition/foods/search*', async (route) => {
    const url = new URL(route.request().url());
    const query = (url.searchParams.get('q') ?? '').toLocaleLowerCase('ru');
    const external = url.searchParams.get('include_external') === 'true';
    const items = external
      ? []
      : foods.filter((food) => food.name.toLocaleLowerCase('ru').includes(query));
    await route.fulfill({
      json: {
        items,
        external_items: [],
        total: items.length,
        limit: 20,
        offset: 0,
        provider_status: external ? 'available' : 'not_requested',
      },
    });
  });
  await page.route('**/api/v1/nutrition/diary**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const nutrition = {
      energy_kcal: '100.00',
      protein_g: '5.000',
      fat_g: '2.000',
      carbs_g: '15.000',
      fiber_g: null,
    };
    if (path.endsWith('/diary/batch/preview') && request.method() === 'POST') {
      const body = request.postDataJSON() as { items: Array<{ amount: string }> };
      const factor = body.items.reduce((sum, item) => sum + Number(item.amount) / 100, 0);
      return route.fulfill({
        json: {
          energy_kcal: String(factor * 100),
          protein_g: String(factor * 5),
          fat_g: String(factor * 2),
          carbs_g: String(factor * 15),
          fiber_g: null,
        },
      });
    }
    if (path.endsWith('/diary/natural-input/commit') && request.method() === 'POST') {
      const body = request.postDataJSON() as {
        diary_date: string;
        meal_type: string;
        items: Array<{ food_id: number; amount: string; amount_unit: string }>;
      };
      if (body.items.some((item) => !foods.some((food) => food.id === item.food_id)))
        return route.fulfill({ status: 404, json: { detail: 'Synthetic food not found' } });
      batchRequests.push({
        key: request.headers()['idempotency-key'],
        ids: body.items.map((item) => item.food_id),
      });
      const added = body.items.map((item) => {
        const food = foods.find((candidate) => candidate.id === item.food_id)!;
        postedIds.push(food.id);
        const entry = {
          id: 1000 + entries.length,
          diary_date: body.diary_date,
          meal_type: body.meal_type,
          food_id: food.id,
          recipe_id: null,
          entry_kind: 'food',
          logged_at: null,
          food_name: food.name,
          food_brand: food.brand,
          amount: String(item.amount),
          amount_unit: item.amount_unit,
          weight_g: String(item.amount),
          serving_amount: null,
          serving_unit: null,
          serving_weight_g: null,
          nutrition,
          created_at: `${date}T08:00:00Z`,
          updated_at: `${date}T08:00:00Z`,
        };
        entries.push(entry);
        return entry;
      });
      return route.fulfill({
        status: 201,
        json: {
          operation_kind: 'natural_input',
          diary_date: body.diary_date,
          meal_type: body.meal_type,
          entries: added,
          replayed: false,
        },
      });
    }
    if (path.endsWith('/diary/entries') && request.method() === 'POST') {
      const body = request.postDataJSON() as {
        food_id: number;
        amount: number;
        amount_unit: string;
        diary_date: string;
        meal_type: string;
      };
      const food = foods.find((item) => item.id === body.food_id);
      if (!food)
        return route.fulfill({ status: 404, json: { detail: 'Synthetic food not found' } });
      postedIds.push(food.id);
      const entry = {
        id: 1000 + entries.length,
        diary_date: body.diary_date,
        meal_type: body.meal_type,
        food_id: food.id,
        recipe_id: null,
        entry_kind: 'food',
        logged_at: null,
        food_name: food.name,
        food_brand: food.brand,
        amount: String(body.amount),
        amount_unit: body.amount_unit,
        weight_g: String(body.amount),
        serving_amount: null,
        serving_unit: null,
        serving_weight_g: null,
        nutrition,
        created_at: `${date}T08:00:00Z`,
        updated_at: `${date}T08:00:00Z`,
      };
      entries.push(entry);
      return route.fulfill({ status: 201, json: entry });
    }
    if (path.endsWith('/diary') && request.method() === 'GET') {
      const zero = {
        energy_kcal: '0.00',
        protein_g: '0.000',
        fat_g: '0.000',
        carbs_g: '0.000',
        fiber_g: null,
      };
      const totals = {
        energy_kcal: String(entries.length * 100),
        protein_g: String(entries.length * 5),
        fat_g: String(entries.length * 2),
        carbs_g: String(entries.length * 15),
        fiber_g: null,
      };
      return route.fulfill({
        json: {
          diary_date: date,
          timezone: 'Europe/Moscow',
          meals: [
            { meal_type: 'breakfast', entries, totals },
            ...['lunch', 'dinner', 'snacks'].map((meal_type) => ({
              meal_type,
              entries: [],
              totals: zero,
            })),
          ],
          totals,
          targets: null,
          remaining: null,
          status: entries.length ? 'incomplete' : 'unlogged',
          status_is_explicit: false,
        },
      });
    }
    return route.fallback();
  });
  return { postedIds, entries, batchRequests };
}

for (const count of [1, 3, 6]) {
  for (let repetition = 1; repetition <= 3; repetition += 1) {
    test(`951 batch ${count} foods run ${repetition}`, async ({ page }, info) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
      const { postedIds, batchRequests } = await installSyntheticNutrition(page);
      await page.goto('/app?section=nutrition');
      const breakfast = page.getByRole('region', { name: 'Завтрак' });
      const add = breakfast.getByRole('button', { name: /Добавить/ });
      await expect(add).toBeVisible();
      let actions = 0;
      const start = performance.now();
      await add.click();
      actions += 1;
      for (const food of foods.slice(0, count)) {
        await page.getByRole('searchbox', { name: 'Найти продукт' }).fill(food.name);
        actions += 1;
        await page
          .getByRole('button', { name: `Выбрать ${food.name} в подборку`, exact: true })
          .click();
        actions += 1;
      }
      expect(batchRequests).toHaveLength(0);
      const confirm = page.getByRole('button', { name: 'Добавить в дневник', exact: true });
      await expect(confirm).toBeEnabled();
      await expect(confirm).toBeInViewport({ ratio: 1 });
      await confirm.click();
      actions += 1;
      await expect(page.getByRole('dialog')).not.toBeAttached();
      const last = foods[count - 1];
      if (!last) throw new Error('Synthetic food fixture is incomplete');
      await expect(breakfast.getByText(last.name, { exact: true })).toBeVisible();
      const elapsedMs = Math.round(performance.now() - start);
      expect(actions).toBe(2 * count + 2);
      expect(batchRequests).toHaveLength(1);
      expect(batchRequests[0]?.key).toBeTruthy();
      expect(postedIds).toEqual(foods.slice(0, count).map((food) => food.id));
      await page.reload();
      for (const food of foods.slice(0, count))
        await expect(breakfast.getByText(food.name, { exact: true })).toBeVisible();
      console.log(
        `V13_951 ${JSON.stringify({ engine: info.project.name, count, repetition, actions, elapsedMs })}`,
      );
    });
  }
}

for (const width of [320, 360, 390, 430, 1280]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`951 capture ${width} ${theme}`, async ({ page }, info) => {
      const height =
        width === 1280
          ? 900
          : width === 320
            ? 720
            : width === 360
              ? 800
              : width === 390
                ? 844
                : 932;
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await installSyntheticNutrition(page);
      const examples = [
        { ...foods[0], id: 201, name: 'Йогурт натуральный', brand: 'Марка А' },
        { ...foods[1], id: 202, name: 'Йогурт натуральный', brand: 'Марка Б' },
      ];
      await page.route('**/api/v1/nutrition/foods/search*', (route) =>
        route.fulfill({
          json: {
            items: examples,
            external_items: [],
            total: 2,
            limit: 20,
            offset: 0,
            provider_status: 'not_requested',
          },
        }),
      );
      await page.goto('/app?section=nutrition');
      await page
        .getByRole('region', { name: 'Завтрак' })
        .getByRole('button', { name: /Добавить/ })
        .click();
      await page.getByRole('searchbox', { name: 'Найти продукт' }).fill('йогурт');
      await page
        .getByRole('button', { name: 'Выбрать Йогурт натуральный, Марка А в подборку' })
        .click();
      await page
        .getByRole('button', { name: 'Выбрать Йогурт натуральный, Марка Б в подборку' })
        .click();
      const confirm = page.getByRole('button', { name: 'Добавить в дневник', exact: true });
      await expect(confirm).toBeEnabled();
      await expect(confirm).toBeInViewport({ ratio: 1 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      const dir = resolve('..', 'docs', 'ux-proposals', 'issue-951', 'after');
      await mkdir(dir, { recursive: true });
      await page.screenshot({
        path: resolve(dir, `${info.project.name}-${width}x${height}-${theme}-selected.png`),
      });
      await page.getByText('Подборка · 2').click();
      await expect(
        page.getByRole('spinbutton', {
          name: 'Количество: Йогурт натуральный, Марка А, Проверено YFC',
        }),
      ).toBeVisible();
      await page.screenshot({
        path: resolve(dir, `${info.project.name}-${width}x${height}-${theme}-editing.png`),
      });
    });
  }
}

for (const theme of ['light', 'dark'] as const) {
  test(`951 capture interaction states ${theme}`, async ({ page }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    const { postedIds } = await installSyntheticNutrition(page);
    const dir = resolve('..', 'docs', 'ux-proposals', 'issue-951', 'after');
    await mkdir(dir, { recursive: true });
    const capture = (state: string) =>
      page.screenshot({ path: resolve(dir, `${info.project.name}-390x844-${theme}-${state}.png`) });
    await page.goto('/app?section=nutrition');
    await page
      .getByRole('region', { name: 'Завтрак' })
      .getByRole('button', { name: /Добавить/ })
      .click();
    await expect(page.getByRole('searchbox', { name: 'Найти продукт' })).toBeFocused();
    await page.getByRole('button', { name: 'Закрыть добавление' }).focus();
    await expect(page.getByText('Подборка · 0')).toBeVisible();
    await capture('empty');

    let completeSearch = () => {};
    const pendingSearch = new Promise<void>((resolve) => {
      completeSearch = resolve;
    });
    const failSearch = async (route: Route) => {
      await pendingSearch;
      await route.fulfill({ status: 503, json: { detail: 'Unavailable' } });
    };
    await page.route('**/api/v1/nutrition/foods/search*', failSearch);
    await page.getByRole('searchbox', { name: 'Найти продукт' }).fill(firstFood.name);
    await expect(page.getByText('Ищем продукты…')).toBeVisible();
    await capture('loading');
    completeSearch();
    await expect(
      page.getByText('Локальный каталог сейчас не ответил. Попробуйте снова.'),
    ).toBeVisible();
    await capture('search-error');
    await page.unroute('**/api/v1/nutrition/foods/search*', failSearch);
    await page.getByRole('button', { name: 'Повторить', exact: true }).click();
    await page.getByRole('button', { name: `Выбрать ${firstFood.name}`, exact: true }).click();
    await expect(page.getByRole('spinbutton', { name: /Количество/ })).toBeVisible();
    await capture('single');
    await page.getByRole('button', { name: 'Выбрать другое' }).click();

    const failPreview = (route: Route) =>
      route.fulfill({ status: 503, json: { detail: 'Unavailable' } });
    await page.route('**/api/v1/nutrition/diary/batch/preview', failPreview);
    await page.getByRole('button', { name: `Выбрать ${firstFood.name} в подборку` }).click();
    await expect(page.getByRole('button', { name: 'Повторить расчёт' })).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Добавить в дневник', exact: true }),
    ).toBeDisabled();
    await capture('preview-error');
    await page.unroute('**/api/v1/nutrition/diary/batch/preview', failPreview);
    await page.getByRole('button', { name: 'Повторить расчёт' }).click();
    await expect(
      page.getByRole('button', { name: 'Добавить в дневник', exact: true }),
    ).toBeEnabled();
    await page.getByText('Подборка · 1').click();
    const amount = page.getByRole('spinbutton', {
      name: `Количество: ${firstFood.name}, Проверено YFC`,
    });
    await amount.fill('0');
    await expect(page.getByText('Введите количество больше нуля.')).toBeVisible();
    await capture('invalid');
    await amount.fill('100');
    const confirm = page.getByRole('button', { name: 'Добавить в дневник', exact: true });
    await expect(confirm).toBeEnabled();
    await page.route('**/api/v1/nutrition/diary/natural-input/commit', (route) =>
      route.fulfill({ status: 503, json: { detail: 'Unavailable' } }),
    );
    await confirm.click();
    await expect(page.getByText(/Не удалось узнать результат/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Повторить подтверждение' })).toBeVisible();
    expect(postedIds).toEqual([]);
    await capture('network-error');
  });

  test(`951 keyboard selection and selected text contrast ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await installSyntheticNutrition(page);
    await page.goto('/app?section=nutrition');
    const add = page
      .getByRole('region', { name: 'Завтрак' })
      .getByRole('button', { name: /Добавить/ });
    await add.focus();
    await page.keyboard.press('Enter');
    const search = page.getByRole('searchbox', { name: 'Найти продукт' });
    await expect(search).toBeFocused();
    await search.fill(firstFood.name);
    const card = page.getByRole('button', { name: `Выбрать ${firstFood.name}`, exact: true });
    await card.focus();
    await page.keyboard.press('Tab');
    await expect(
      page.getByRole('button', { name: `Добавить ${firstFood.name} в избранное` }),
    ).toBeFocused();
    await page.keyboard.press('Tab');
    const choose = page.getByRole('button', { name: `Выбрать ${firstFood.name} в подборку` });
    await expect(choose).toBeFocused();
    await page.keyboard.press('Space');
    const selected = page.getByRole('button', { name: `Убрать ${firstFood.name} из подборки` });
    await expect(selected).toHaveAttribute('aria-pressed', 'true');
    await expect(selected).toBeFocused();
    const contrast = await selected.evaluate((element) => {
      const rgba = (value: string) => {
        const parts = value.match(/[\d.]+/g)?.map(Number) ?? [];
        return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0, parts[3] ?? 1];
      };
      const over = (front: number[], back: number[]) =>
        front
          .slice(0, 3)
          .map((channel, index) => channel * front[3]! + back[index]! * (1 - front[3]!));
      const layers: number[][] = [];
      for (let node: Element | null = element; node; node = node.parentElement)
        layers.push(rgba(getComputedStyle(node).backgroundColor));
      const background = layers
        .reverse()
        .reduce((back, front) => over(front, back), [255, 255, 255]);
      const foreground = over(rgba(getComputedStyle(element).color), background);
      const luminance = (color: number[]) =>
        color
          .map((value) => {
            const channel = value / 255;
            return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
          })
          .reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index]!, 0);
      const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
      return (values[0]! + 0.05) / (values[1]! + 0.05);
    });
    console.log(`V13_951_CONTRAST ${theme} ${contrast.toFixed(2)}`);
    expect(contrast).toBeGreaterThanOrEqual(4.5);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).not.toBeAttached();
    await expect(add).toBeFocused();
  });
}

for (const count of [1, 3, 6]) {
  for (let repetition = 1; repetition <= 5; repetition += 1) {
    test(`synthetic search/add ${count} foods run ${repetition}`, async ({ page }, info) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
      const { postedIds } = await installSyntheticNutrition(page);
      await page.goto('/app?section=nutrition');
      const breakfast = page.getByRole('region', { name: 'Завтрак' });
      const add = breakfast.getByRole('button', { name: /Добавить/ });
      await expect(add).toBeVisible();
      let actions = 0;
      const start = performance.now();
      for (const food of foods.slice(0, count)) {
        await add.click();
        actions += 1;
        await page.getByRole('searchbox', { name: 'Найти продукт' }).fill(food.name);
        actions += 1;
        await page.getByRole('button', { name: `Выбрать ${food.name}`, exact: true }).click();
        actions += 1;
        await expect(page.getByRole('spinbutton', { name: 'Количество' })).toHaveValue('100');
        await page.getByRole('button', { name: 'Добавить в дневник' }).click();
        actions += 1;
        await expect(page.getByRole('dialog')).not.toBeAttached();
        await expect(breakfast.getByText(food.name, { exact: true })).toBeVisible();
      }
      const elapsedMs = Math.round(performance.now() - start);
      expect(postedIds).toEqual(foods.slice(0, count).map((food) => food.id));
      await page.reload();
      for (const food of foods.slice(0, count))
        await expect(breakfast.getByText(food.name, { exact: true })).toBeVisible();
      console.log(
        `V13_BASELINE ${JSON.stringify({ engine: info.project.name, count, repetition, actions, elapsedMs })}`,
      );
    });
  }
}

for (const count of [3, 6]) {
  for (let repetition = 1; repetition <= 3; repetition += 1) {
    test(`synthetic sequential ${count} foods run ${repetition}`, async ({ page }, info) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
      const { postedIds } = await installSyntheticNutrition(page);
      await page.goto('/app?section=nutrition');
      const breakfast = page.getByRole('region', { name: 'Завтрак' });
      const add = breakfast.getByRole('button', { name: /Добавить/ });
      await expect(add).toBeVisible();
      let actions = 0;
      const lastFood = foods[count - 1];
      if (!lastFood) throw new Error('Synthetic food fixture is incomplete');
      const start = performance.now();
      await add.click();
      actions += 1;
      for (const [index, food] of foods.slice(0, count).entries()) {
        await page.getByRole('searchbox', { name: 'Найти продукт' }).fill(food.name);
        actions += 1;
        await page.getByRole('button', { name: `Выбрать ${food.name}`, exact: true }).click();
        actions += 1;
        await page
          .getByRole('button', {
            name: index === count - 1 ? 'Добавить в дневник' : 'Добавить и выбрать ещё',
          })
          .click();
        actions += 1;
        if (index < count - 1)
          await expect(page.getByRole('searchbox', { name: 'Найти продукт' })).toBeVisible();
      }
      await expect(page.getByRole('dialog')).not.toBeAttached();
      await expect(breakfast.getByText(lastFood.name, { exact: true })).toBeVisible();
      const elapsedMs = Math.round(performance.now() - start);
      expect(postedIds).toEqual(foods.slice(0, count).map((food) => food.id));
      await page.reload();
      for (const food of foods.slice(0, count))
        await expect(breakfast.getByText(food.name, { exact: true })).toBeVisible();
      console.log(
        `V13_EXTRA ${JSON.stringify({ scenario: 'sequential', engine: info.project.name, count, repetition, actions, elapsedMs })}`,
      );
    });
  }
}

for (let repetition = 1; repetition <= 3; repetition += 1) {
  test(`synthetic template add run ${repetition}`, async ({ page }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    const { entries } = await installSyntheticNutrition(page);
    const nutrition = {
      energy_kcal: '100.00',
      protein_g: '5.000',
      fat_g: '2.000',
      carbs_g: '15.000',
      fiber_g: null,
    };
    const item = {
      id: 1,
      position: 0,
      item_kind: 'food',
      food_id: firstFood.id,
      recipe_id: null,
      name: firstFood.name,
      brand: null,
      amount: '100',
      amount_unit: 'g',
      weight_g: '100',
      nutrition,
      available: true,
    };
    const template = {
      id: 42,
      name: 'Тестовый завтрак',
      items: [item],
      total_weight_g: '100',
      totals: nutrition,
      created_at: `${date}T08:00:00Z`,
      updated_at: `${date}T08:00:00Z`,
    };
    let inserts = 0;
    await page.route('**/api/v1/nutrition/templates**', (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path.endsWith('/templates') && request.method() === 'GET')
        return route.fulfill({ json: { items: [template], total: 1, limit: 50, offset: 0 } });
      if (path.endsWith('/templates/42/entries') && request.method() === 'POST') {
        inserts += 1;
        const entry = {
          id: 1000,
          diary_date: date,
          meal_type: 'breakfast',
          food_id: firstFood.id,
          recipe_id: null,
          entry_kind: 'food',
          logged_at: null,
          food_name: firstFood.name,
          food_brand: null,
          amount: '100',
          amount_unit: 'g',
          weight_g: '100',
          serving_amount: null,
          serving_unit: null,
          serving_weight_g: null,
          nutrition,
          created_at: `${date}T08:00:00Z`,
          updated_at: `${date}T08:00:00Z`,
        };
        entries.push(entry);
        return route.fulfill({
          status: 201,
          json: {
            operation_kind: 'meal_template',
            diary_date: date,
            meal_type: 'breakfast',
            entries: [entry],
            replayed: false,
          },
        });
      }
      return route.fallback();
    });
    await page.goto('/app?section=nutrition');
    const breakfast = page.getByRole('region', { name: 'Завтрак' });
    const add = breakfast.getByRole('button', { name: /Добавить/ });
    await expect(add).toBeVisible();
    const start = performance.now();
    await add.click();
    await page.getByRole('button', { name: 'Шаблоны приёмов', exact: true }).click();
    await page.getByRole('button', { name: 'Быстро добавить в Завтрак', exact: true }).click();
    await expect(page.getByRole('dialog')).not.toBeAttached();
    await expect(breakfast.getByText(firstFood.name, { exact: true })).toBeVisible();
    const elapsedMs = Math.round(performance.now() - start);
    expect(inserts).toBe(1);
    await page.reload();
    await expect(breakfast.getByText(firstFood.name, { exact: true })).toBeVisible();
    console.log(
      `V13_EXTRA ${JSON.stringify({ scenario: 'template', engine: info.project.name, repetition, actions: 4, elapsedMs })}`,
    );
  });
}

for (let repetition = 1; repetition <= 3; repetition += 1) {
  test(`synthetic manual quick add run ${repetition}`, async ({ page }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    await page.clock.setFixedTime(new Date(`${date}T09:00:00+03:00`));
    await installPlatformApi(page, { browserSession: true, fixedDate: date });
    await page.goto('/app?section=nutrition');
    const start = performance.now();
    await page.getByTestId('nutrition-add-product').click();
    await page.getByText('Другие способы добавления', { exact: true }).click();
    await page
      .getByRole('dialog')
      .getByRole('button', { name: 'Быстрый ввод', exact: true })
      .click();
    await page
      .getByRole('textbox', { name: 'Название или контекст (необязательно)' })
      .fill('Тестовый приём');
    await page.getByRole('spinbutton', { name: 'Калории' }).fill('640');
    await page.getByRole('button', { name: 'Сохранить Quick Add' }).click();
    await expect(page.getByRole('dialog')).not.toBeAttached();
    await expect(page.getByText('Тестовый приём', { exact: true })).toBeVisible();
    const elapsedMs = Math.round(performance.now() - start);
    await page.reload();
    await expect(page.getByText('Тестовый приём', { exact: true })).toBeVisible();
    console.log(
      `V13_EXTRA ${JSON.stringify({ scenario: 'manual-quick-add', engine: info.project.name, repetition, actions: 5, elapsedMs })}`,
    );
  });
}

for (let repetition = 1; repetition <= 3; repetition += 1) {
  test(`synthetic favorite add run ${repetition}`, async ({ page }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    const { postedIds } = await installSyntheticNutrition(page);
    await page.route('**/api/v1/nutrition/foods/favorites*', (route) =>
      route.fulfill({ json: { items: [firstFood], total: 1, limit: 12, offset: 0 } }),
    );
    await page.goto('/app?section=nutrition');
    const breakfast = page.getByRole('region', { name: 'Завтрак' });
    const add = breakfast.getByRole('button', { name: /Добавить/ });
    await expect(add).toBeVisible();
    const start = performance.now();
    await add.click();
    await page.getByText('Каталог и фильтры', { exact: true }).click();
    await page.getByRole('button', { name: 'Избранное', exact: true }).click();
    await page.getByRole('button', { name: `Выбрать ${firstFood.name}`, exact: true }).click();
    await page.getByRole('button', { name: 'Добавить в дневник' }).click();
    await expect(page.getByRole('dialog')).not.toBeAttached();
    await expect(breakfast.getByText(firstFood.name, { exact: true })).toBeVisible();
    const elapsedMs = Math.round(performance.now() - start);
    expect(postedIds).toEqual([firstFood.id]);
    console.log(
      `V13_EXTRA ${JSON.stringify({ scenario: 'favorite', engine: info.project.name, repetition, actions: 5, elapsedMs })}`,
    );
  });
}

for (let repetition = 1; repetition <= 3; repetition += 1) {
  test(`synthetic repeat previous meal run ${repetition}`, async ({ page }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    await page.clock.setFixedTime(new Date(`${date}T09:00:00+03:00`));
    await installPlatformApi(page, { browserSession: true, fixedDate: date });
    const nutrition = {
      energy_kcal: '100.00',
      protein_g: '5.000',
      fat_g: '2.000',
      carbs_g: '15.000',
      fiber_g: null,
    };
    const prior = {
      id: 30,
      diary_date: '2026-11-04',
      meal_type: 'breakfast',
      food_id: firstFood.id,
      recipe_id: null,
      entry_kind: 'food',
      logged_at: null,
      food_name: firstFood.name,
      food_brand: null,
      amount: '100',
      amount_unit: 'g',
      weight_g: '100',
      serving_amount: null,
      serving_unit: null,
      serving_weight_g: null,
      nutrition,
      created_at: '2026-11-04T08:00:00Z',
      updated_at: '2026-11-04T08:00:00Z',
    };
    const entries: (typeof prior)[] = [];
    let confirms = 0;
    await page.route('**/api/v1/nutrition/diary**', (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path.endsWith('/diary/copy/meal/preview') && request.method() === 'POST')
        return route.fulfill({
          json: {
            copy_scope: 'meal',
            source_date: '2026-11-04',
            source_meal_type: 'breakfast',
            target_date: date,
            target_meal_type: 'breakfast',
            entries: [prior],
            preview_token: 'synthetic-preview-token-001',
            previewed_at: `${date}T08:00:00Z`,
          },
        });
      if (path.endsWith('/diary/copy/meal') && request.method() === 'POST') {
        confirms += 1;
        entries.push({ ...prior, id: 31, diary_date: date });
        return route.fulfill({
          status: 201,
          json: { copy_scope: 'meal', replayed: false, entries },
        });
      }
      if (path.endsWith('/diary') && request.method() === 'GET')
        return route.fulfill({
          json: {
            diary_date: date,
            timezone: 'Europe/Moscow',
            meals: [
              { meal_type: 'breakfast', entries, totals: nutrition },
              ...['lunch', 'dinner', 'snacks'].map((meal_type) => ({
                meal_type,
                entries: [],
                totals: nutrition,
              })),
            ],
            totals: nutrition,
            targets: null,
            remaining: null,
            status: 'incomplete',
            status_is_explicit: false,
            repeat_candidate: {
              source_date: '2026-11-04',
              source_meal_type: 'breakfast',
              entry_count: 1,
            },
          },
        });
      return route.fallback();
    });
    await page.goto('/app?section=nutrition');
    const repeat = page.getByTestId('nutrition-repeat-default');
    await expect(repeat).toBeVisible();
    const start = performance.now();
    await repeat.click();
    const dialog = page.getByRole('dialog', { name: 'Повторить приём пищи' });
    await expect(dialog.getByText(prior.food_name, { exact: true })).toBeVisible();
    await dialog.getByRole('button', { name: 'Подтвердить' }).click();
    await expect(dialog).not.toBeAttached();
    await expect(
      page.getByRole('region', { name: 'Завтрак' }).getByText(prior.food_name, { exact: true }),
    ).toBeVisible();
    const elapsedMs = Math.round(performance.now() - start);
    expect(confirms).toBe(1);
    await page.reload();
    await expect(
      page.getByRole('region', { name: 'Завтрак' }).getByText(prior.food_name, { exact: true }),
    ).toBeVisible();
    console.log(
      `V13_EXTRA ${JSON.stringify({ scenario: 'repeat-meal', engine: info.project.name, repetition, actions: 2, elapsedMs })}`,
    );
  });
}

for (let repetition = 1; repetition <= 3; repetition += 1) {
  test(`synthetic quantity and unit run ${repetition}`, async ({ page }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    await installSyntheticNutrition(page);
    await page.route('**/api/v1/nutrition/foods/search*', (route) =>
      route.fulfill({
        json: {
          items: [
            {
              ...firstFood,
              standard_serving_amount: '1',
              standard_serving_unit: 'serving',
              standard_serving_weight_g: '50',
            },
          ],
          external_items: [],
          total: 1,
          limit: 20,
          offset: 0,
          provider_status: 'not_requested',
        },
      }),
    );
    let payload: { amount?: number; amount_unit?: string } | null = null;
    page.on('request', (request) => {
      if (request.url().endsWith('/nutrition/diary/entries') && request.method() === 'POST')
        payload = request.postDataJSON();
    });
    await page.goto('/app?section=nutrition');
    const breakfast = page.getByRole('region', { name: 'Завтрак' });
    const add = breakfast.getByRole('button', { name: /Добавить/ });
    await expect(add).toBeVisible();
    const start = performance.now();
    await add.click();
    await page.getByRole('searchbox', { name: 'Найти продукт' }).fill(firstFood.name);
    await page.getByRole('button', { name: `Выбрать ${firstFood.name}`, exact: true }).click();
    await page.getByLabel('Единица').selectOption('g');
    await page.getByRole('spinbutton', { name: 'Количество' }).fill('150');
    await page.getByRole('button', { name: 'Добавить в дневник' }).click();
    await expect(page.getByRole('dialog')).not.toBeAttached();
    const elapsedMs = Math.round(performance.now() - start);
    expect(payload).toMatchObject({ amount: 150, amount_unit: 'g' });
    console.log(
      `V13_EXTRA ${JSON.stringify({ scenario: 'quantity-unit', engine: info.project.name, repetition, actions: 6, elapsedMs })}`,
    );
  });
}

test('synthetic same-name brands accessible labels', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await installSyntheticNutrition(page);
  const variants = ['Марка А', 'Марка Б'].map((brand, index) => ({
    ...foods[index],
    name: 'Йогурт натуральный',
    brand,
  }));
  await page.route('**/api/v1/nutrition/foods/search*', (route) =>
    route.fulfill({
      json: {
        items: variants,
        external_items: [],
        total: variants.length,
        limit: 20,
        offset: 0,
        provider_status: 'not_requested',
      },
    }),
  );
  await page.goto('/app?section=nutrition');
  await page
    .getByRole('region', { name: 'Завтрак' })
    .getByRole('button', { name: /Добавить/ })
    .click();
  await page.getByRole('searchbox', { name: 'Найти продукт' }).fill('йогурт');
  const cards = page
    .locator('.nutrition-food-result--picker')
    .filter({ hasText: 'Йогурт натуральный' });
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toContainText('Марка А');
  await expect(cards.nth(1)).toContainText('Марка Б');
  const labels = await cards
    .locator('.nutrition-food-result__select')
    .evaluateAll((buttons) => buttons.map((button) => button.getAttribute('aria-label')));
  console.log(`V13_BRANDS ${JSON.stringify({ engine: info.project.name, labels })}`);
  const dir = resolve('..', '.artifacts', 'tasks', '950', 'evidence');
  await mkdir(dir, { recursive: true });
  await page.screenshot({
    path: resolve(dir, `same-name-brands-${info.project.name}-390x844-light.png`),
  });
});

test('synthetic add failure and retry preserves the request key', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  const { postedIds } = await installSyntheticNutrition(page);
  const keys: (string | undefined)[] = [];
  await page.route('**/api/v1/nutrition/diary/entries', (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    keys.push(route.request().headers()['idempotency-key']);
    if (keys.length === 1)
      return route.fulfill({ status: 503, json: { detail: 'Synthetic unavailable' } });
    return route.fallback();
  });
  await page.goto('/app?section=nutrition');
  const breakfast = page.getByRole('region', { name: 'Завтрак' });
  await breakfast.getByRole('button', { name: /Добавить/ }).click();
  await page.getByRole('searchbox', { name: 'Найти продукт' }).fill(firstFood.name);
  await page.getByRole('button', { name: `Выбрать ${firstFood.name}`, exact: true }).click();
  await page.getByRole('button', { name: 'Добавить в дневник' }).click();
  const error = page.getByRole('dialog').getByRole('alert');
  await expect(error).toBeVisible();
  await error.getByRole('button', { name: 'Повторить', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeAttached();
  await expect(breakfast.getByText(firstFood.name, { exact: true })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);
  expect(postedIds).toEqual([firstFood.id]);
  await page.reload();
  await expect(breakfast.getByText(firstFood.name, { exact: true })).toHaveCount(1);
  console.log(
    `V13_ERROR_RETRY ${JSON.stringify({ engine: info.project.name, responses: ['503', '201'], requests: keys.length, sameKey: keys[0] === keys[1], savedEntries: postedIds.length })}`,
  );
});

test('synthetic unknown nutrition remains visibly unknown', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await installSyntheticNutrition(page);
  const unknown = {
    ...firstFood,
    name: 'Неизвестный продукт',
    energy_kcal_per_100g: null,
    protein_g_per_100g: null,
    fat_g_per_100g: null,
    carbs_g_per_100g: null,
  };
  await page.route('**/api/v1/nutrition/foods/search*', (route) =>
    route.fulfill({
      json: {
        items: [unknown],
        external_items: [],
        total: 1,
        limit: 20,
        offset: 0,
        provider_status: 'not_requested',
      },
    }),
  );
  await page.goto('/app?section=nutrition');
  await page
    .getByRole('region', { name: 'Завтрак' })
    .getByRole('button', { name: /Добавить/ })
    .click();
  await page.getByRole('searchbox', { name: 'Найти продукт' }).fill(unknown.name);
  const card = page.locator('.nutrition-food-result--picker').filter({ hasText: unknown.name });
  await expect(card).toContainText('— ккал / 100 г');
  await card.locator('.nutrition-food-result__select').click();
  await expect(page.locator('.nutrition-picker__selected')).toContainText('Б — · Ж — · У —');
  console.log(
    `V13_UNKNOWN ${JSON.stringify({ engine: info.project.name, energy: '—', macros: '—', committed: false })}`,
  );
});

test.describe('PWA diagnostic', () => {
  test.use({ serviceWorkers: 'allow' });
  test('waits for an active worker before checking control', async ({ page }, info) => {
    await page.goto('/');
    await page.waitForFunction(
      () => navigator.serviceWorker.ready.then((registration) => Boolean(registration.active)),
      undefined,
      { timeout: 10_000 },
    );
    await page.reload();
    await expect
      .poll(() => page.evaluate(() => navigator.serviceWorker.controller?.scriptURL ?? null))
      .toContain('/sw.js');
    console.log(
      `V13_PWA ${JSON.stringify({ engine: info.project.name, activeThenReload: true, controlled: true })}`,
    );
  });
});

for (const width of [360, 390, 430, 1280]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`synthetic search screenshot ${width} ${theme}`, async ({ page }, info) => {
      const height = width === 1280 ? 900 : width === 360 ? 800 : width === 390 ? 844 : 932;
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await installSyntheticNutrition(page);
      await page.goto('/app?section=nutrition');
      await page
        .getByRole('region', { name: 'Завтрак' })
        .getByRole('button', { name: /Добавить/ })
        .click();
      await page.getByRole('searchbox', { name: 'Найти продукт' }).fill('рис');
      await expect(
        page.getByRole('button', { name: 'Выбрать Рис белый отварной', exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole('button', { name: 'Выбрать Рис бурый отварной', exact: true }),
      ).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      const dir = resolve('..', '.artifacts', 'tasks', '950', 'evidence');
      await mkdir(dir, { recursive: true });
      await page.screenshot({
        path: resolve(dir, `food-search-${info.project.name}-${width}x${height}-${theme}.png`),
      });
    });
  }
}
