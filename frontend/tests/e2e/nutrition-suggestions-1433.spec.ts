import { mkdirSync, writeFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

const date = '2026-11-06';
const nutrition = { energy_kcal: '165', protein_g: '31', fat_g: null, carbs_g: '0', fiber_g: null };
const targets = { energy_kcal: '2000', protein_g: '150', fat_g: '70', carbs_g: '200' };
const names = ['Курица', 'Овсяная каша', 'Рис', 'Творог', 'Яблоко', 'Суп'];
const candidates = names.map((name, index) => ({
  candidate_id: `food:${index + 1}`,
  candidate_kind: 'food',
  identity_id: index + 1,
  name,
  items: [
    {
      position: 0,
      item_kind: 'food',
      food_id: index + 1,
      recipe_id: null,
      name,
      brand: null,
      amount: '100',
      amount_unit: 'g',
      nutrition,
      nutrition_confidence: 'partial',
    },
  ],
  nutrition,
  nutrition_confidence: 'partial',
  sources: ['recent'],
  reasons: ['recent', 'protein_fit', 'partial_nutrition'],
}));

function payload(count: number, diaryDate = date) {
  return {
    mode: 'deterministic',
    diary_date: diaryDate,
    targets,
    remaining: { energy_kcal: '500', protein_g: '50', fat_g: null, carbs_g: '60' },
    remaining_confidence: 'partial',
    limitations: ['Часть БЖУ неизвестна: неполные записи не превращаются в нули.'],
    max_candidates: 6,
    candidates: candidates.slice(0, count),
  };
}

async function prepare(page: Page, theme: 'dark' | 'light' = 'light') {
  await page.clock.setFixedTime(new Date(`${date}T12:00:00Z`));
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
  await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
  await installPlatformApi(page, { browserSession: true, fixedDate: date });
}

for (const width of [320, 360, 393, 430, 1280]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`рекомендации: ${width}px ${theme}`, async ({ page, browserName }) => {
      await page.setViewportSize({ width, height: width >= 1280 ? 900 : 844 });
      await prepare(page, theme);
      await page.route('**/api/v1/nutrition/diary/suggestions?**', (route) =>
        route.fulfill({ json: payload(6) }),
      );
      await page.goto(`/app?section=nutrition&date=${date}`);
      const region = page.getByRole('region', { name: 'Варианты из вашей еды' });
      await expect(region.getByText('Курица', { exact: true })).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
      const phase = process.env.CAPTURE_1433;
      await expect(region.locator('.nutrition-suggestion-card:visible')).toHaveCount(
        phase === 'before' ? 6 : 2,
      );
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      const box = await region.boundingBox();
      const metrics = {
        browser: browserName,
        width,
        theme,
        phase: phase ?? 'after',
        height: box?.height,
        reviewActions: await region.getByRole('button', { name: 'Проверить вариант' }).count(),
      };
      if (phase === 'before' || phase === 'after') {
        const directory = `../docs/ux-proposals/issue-1433/${phase}`;
        mkdirSync(directory, { recursive: true });
        const name = `${browserName}-${theme}-${width}`;
        await region.screenshot({ path: `${directory}/${name}.png`, animations: 'disabled' });
        writeFileSync(`${directory}/${name}.json`, `${JSON.stringify(metrics, null, 2)}\n`);
      }
    });
  }
}

for (const count of [0, 1, 2, 3, 6]) {
  test(`граница ${count} вариантов`, async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await prepare(page);
    await page.route('**/api/v1/nutrition/diary/suggestions?**', (route) => {
      const data = payload(count);
      return route.fulfill({
        json: {
          ...data,
          remaining: null,
          remaining_confidence: null,
          candidates: data.candidates.map((item) => ({
            ...item,
            reasons: item.reasons.filter((reason) => reason !== 'protein_fit'),
          })),
        },
      });
    });
    await page.goto(`/app?section=nutrition&date=${date}`);
    const region = page.getByRole('region', { name: 'Варианты из вашей еды' });
    if (!count) await expect(region.getByText('Не удалось рассчитать остаток')).toBeVisible();
    else await expect(region.getByText('Курица', { exact: true })).toBeVisible();
    await expect(region.locator('.nutrition-suggestion-card:visible')).toHaveCount(
      Math.min(count, 2),
    );
    await expect(region.getByText(/Остаток:/)).toHaveCount(0);
    if (count > 2) {
      await region.getByRole('button', { name: /Показать все/ }).click();
      await expect(region.locator('.nutrition-suggestion-card:visible strong')).toHaveText(
        names.slice(0, count),
      );
      await region.getByRole('button', { name: 'Свернуть' }).click();
      await expect(region.locator('.nutrition-suggestion-card:visible')).toHaveCount(2);
    } else {
      await expect(region.getByRole('button', { name: /Показать все/ })).toHaveCount(0);
    }
  });
}

for (const width of [393, 1280]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`клавиатура, дата и подтверждение: ${width}px ${theme}`, async ({ page, browserName }) => {
      await page.setViewportSize({ width, height: width === 393 ? 844 : 900 });
      await prepare(page, theme);
      let count = 6;
      let committed: unknown;
      await page.route('**/api/v1/nutrition/diary/suggestions?**', (route) => {
        const selected = new URL(route.request().url()).searchParams.get('diary_date') ?? date;
        return route.fulfill({ json: payload(count, selected) });
      });
      await page.route('**/api/v1/nutrition/diary/suggestions/preview', (route) => {
        const body = route.request().postDataJSON();
        const selected = body.items[0];
        const item = candidates[selected.food_id - 1]!.items[0]!;
        const scale = Number(selected.amount) / 100;
        const addition = {
          ...nutrition,
          energy_kcal: String(165 * scale),
          protein_g: String(31 * scale),
        };
        const before = {
          energy_kcal: '0',
          protein_g: '0',
          fat_g: '0',
          carbs_g: '0',
          fiber_g: '0',
        };
        return route.fulfill({
          json: {
            diary_date: body.diary_date,
            meal_type: body.meal_type,
            items: [{ ...item, ...selected, nutrition: addition }],
            before,
            addition,
            after: addition,
            diary: before,
            planned: before,
            projected_after: addition,
            targets,
            target_id: 1,
            target_source: 'manual',
            target_effective_from: date,
            target_weight_kg: null,
            target_goal: null,
            constraint_status: 'not_set',
            constraint_messages: [],
            preference_message: null,
            preview_token: 'a'.repeat(64),
          },
        });
      });
      await page.route('**/api/v1/nutrition/diary/suggestions/commit', (route) => {
        committed = route.request().postDataJSON();
        count = 3;
        return route.fulfill({ status: 201, json: { entries: [], replayed: false } });
      });
      await page.goto(`/app?section=nutrition&date=${date}`);
      const region = page.getByRole('region', { name: 'Варианты из вашей еды' });
      const toggle = region.getByRole('button', { name: /Показать все 6 вариантов|Свернуть/ });
      await expect(toggle).toBeVisible();
      const secondReview = region
        .locator('.nutrition-suggestion-card')
        .filter({ hasText: 'Овсяная каша' })
        .getByRole('button', { name: 'Проверить вариант' });
      const expectSeparated = async () => {
        const reviewBox = await secondReview.boundingBox();
        const toggleBox = await toggle.boundingBox();
        expect(reviewBox).not.toBeNull();
        expect(toggleBox).not.toBeNull();
        expect(toggleBox!.y - reviewBox!.y - reviewBox!.height).toBeGreaterThanOrEqual(11);
      };
      await expectSeparated();
      await toggle.focus();
      await page.keyboard.press('Enter');
      await expect(toggle).toHaveAttribute('aria-expanded', 'true');
      await expectSeparated();
      await expect(toggle).toBeFocused();
      const third = region.locator('li').filter({ hasText: 'Рис' });
      await page.keyboard.press('Tab');
      await expect(third.getByRole('button', { name: 'Проверить вариант' })).toBeFocused();
      await page.keyboard.press('Shift+Tab');
      await expect(toggle).toBeFocused();
      if (process.env.CAPTURE_1433 === 'after') {
        await region.screenshot({
          path: `../docs/ux-proposals/issue-1433/after/${browserName}-${theme}-${width}-expanded.png`,
          animations: 'disabled',
        });
      }
      await page.keyboard.press('Space');
      await expect(toggle).toHaveAttribute('aria-expanded', 'false');
      await toggle.click();
      await third.getByRole('button', { name: 'Проверить вариант' }).click();
      await region.getByLabel('Количество').fill('150');
      await region.getByLabel('Приём пищи').selectOption('dinner');
      expect(committed).toBeUndefined();
      await expect(region.getByRole('row', { name: /Ккал/ })).toContainText('247,5');
      if (process.env.CAPTURE_1433 === 'after') {
        await region.screenshot({
          path: `../docs/ux-proposals/issue-1433/after/${browserName}-${theme}-${width}-review.png`,
          animations: 'disabled',
        });
      }
      await region.getByRole('button', { name: 'Добавить выбранное' }).click();
      await expect
        .poll(() => committed)
        .toEqual({
          diary_date: date,
          meal_type: 'dinner',
          items: [{ food_id: 3, amount: '150', amount_unit: 'g' }],
          preview_token: 'a'.repeat(64),
        });
      await expect(region.getByRole('button', { name: 'Показать все 3 варианта' })).toBeVisible();
      await region.getByRole('button', { name: 'Показать все 3 варианта' }).click();
      await page
        .getByRole('navigation', { name: 'Неделя дневника' })
        .getByRole('button', { name: /5 ноября/ })
        .click();
      await expect(region.getByRole('button', { name: 'Показать все 3 варианта' })).toHaveAttribute(
        'aria-expanded',
        'false',
      );
      await expect(region.locator('.nutrition-suggestion-card:visible')).toHaveCount(2);
    });
  }
}

for (const theme of ['dark', 'light'] as const) {
  test(`ошибка сети, повторная загрузка и пустой список: ${theme}`, async ({
    page,
    browserName,
  }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await prepare(page, theme);
    let fail = true;
    let count = 3;
    await page.route('**/api/v1/nutrition/diary/suggestions?**', (route) =>
      fail
        ? route.fulfill({ status: 503, json: { detail: 'Сеть недоступна' } })
        : route.fulfill({ json: payload(count) }),
    );
    await page.goto(`/app?section=nutrition&date=${date}`);
    const region = page.getByRole('region', { name: 'Варианты из вашей еды' });
    const retry = region.getByRole('button', { name: 'Повторить варианты' });
    await expect(retry).toBeVisible();
    if (process.env.CAPTURE_1433 === 'after') {
      await region.screenshot({
        path: `../docs/ux-proposals/issue-1433/after/${browserName}-${theme}-393-error.png`,
        animations: 'disabled',
      });
    }
    fail = false;
    await retry.click();
    await expect(region.getByRole('button', { name: 'Показать все 3 варианта' })).toBeVisible();
    count = 0;
    await page.reload();
    await expect(region.getByText('Пока нет готовых вариантов')).toBeVisible();
    if (process.env.CAPTURE_1433 === 'after') {
      await region.screenshot({
        path: `../docs/ux-proposals/issue-1433/after/${browserName}-${theme}-393-empty.png`,
        animations: 'disabled',
      });
    }
  });

  test(`длинные названия и увеличение текста до 200%: ${theme}`, async ({ page, browserName }) => {
    await page.setViewportSize({ width: 320, height: 844 });
    await prepare(page, theme);
    const longName = 'ОченьДлинноеНазваниеПродуктаБезПробеловДляПроверкиПереноса';
    const data = payload(3);
    data.candidates[0] = {
      ...data.candidates[0]!,
      name: longName,
      sources: ['recent', 'favorite'],
    };
    await page.route('**/api/v1/nutrition/diary/suggestions?**', (route) =>
      route.fulfill({ json: data }),
    );
    await page.goto(`/app?section=nutrition&date=${date}`);
    const region = page.getByRole('region', { name: 'Варианты из вашей еды' });
    await expect(region.getByText(longName, { exact: true })).toBeVisible();
    await page.addStyleTag({ content: 'html { font-size: 200% !important; }' });
    await expect(region.getByRole('button', { name: /Показать все/ })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
    const dayStatus = page.locator('.nutrition-completeness');
    const statusBox = await dayStatus.boundingBox();
    expect(statusBox).not.toBeNull();
    expect(statusBox!.x + statusBox!.width).toBeLessThanOrEqual(320);
    expect(await dayStatus.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
      true,
    );
    const bounds = await region.boundingBox();
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(320);
    expect(await region.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
      true,
    );
    const detail = region.locator('summary').filter({ hasText: 'Другие основания' });
    expect((await detail.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await detail.focus();
    await page.keyboard.press('Enter');
    await expect(detail).toBeFocused();
    await expect(region.getByText('Избранное', { exact: true })).toBeVisible();
    if (process.env.CAPTURE_1433 === 'after') {
      await region.screenshot({
        path: `../docs/ux-proposals/issue-1433/after/${browserName}-${theme}-320-text-200.png`,
        animations: 'disabled',
      });
    }
  });
}
