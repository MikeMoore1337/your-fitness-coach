import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ serviceWorkers: 'block', timezoneId: 'America/Los_Angeles' });

const today = '2026-11-06';
const target = '2026-11-05';
const nutrition = {
  energy_kcal: '320.00',
  protein_g: '35.000',
  fat_g: '18.000',
  carbs_g: '52.000',
  fiber_g: null,
};
const entry = {
  id: 41,
  diary_date: today,
  meal_type: 'breakfast',
  food_id: null,
  recipe_id: null,
  entry_kind: 'quick_add',
  logged_at: null,
  food_name: 'Завтрак',
  food_brand: null,
  amount: '1.000',
  amount_unit: 'serving',
  weight_g: null,
  serving_amount: '1.000',
  serving_unit: 'serving',
  serving_weight_g: null,
  nutrition,
  created_at: '2026-11-06T08:00:00Z',
  updated_at: '2026-11-06T08:00:00Z',
};

for (const width of [320, 360, 393, 430, 1280]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`copy day: ${width}px ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 844 });
      await page.clock.setFixedTime(new Date('2026-11-05T22:30:00Z'));
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, fixedDate: today });

      const requests: Array<{ source_date: string; target_date: string; preview_token?: string }> =
        [];
      let commits = 0;
      let releaseCommit!: () => void;
      const commitGate = new Promise<void>((resolve) => {
        releaseCommit = resolve;
      });
      let copied = false;
      await page.route(/\/api\/v1\/nutrition\/diary(?:\?.*)?$/, async (route) => {
        const date = new URL(route.request().url()).searchParams.get('diary_date') ?? today;
        const entries =
          date === today
            ? [entry]
            : copied && date === target
              ? [{ ...entry, id: 42, diary_date: target }]
              : [];
        const totals = entries.length
          ? nutrition
          : { energy_kcal: '0.00', protein_g: '0', fat_g: '0', carbs_g: '0', fiber_g: null };
        return route.fulfill({
          json: {
            diary_date: date,
            timezone: 'Europe/Moscow',
            meals: ['breakfast', 'lunch', 'dinner', 'snacks'].map((meal_type) => ({
              meal_type,
              entries: meal_type === 'breakfast' ? entries : [],
              totals:
                meal_type === 'breakfast'
                  ? totals
                  : {
                      energy_kcal: '0.00',
                      protein_g: '0',
                      fat_g: '0',
                      carbs_g: '0',
                      fiber_g: null,
                    },
            })),
            totals,
            targets: { energy_kcal: '2000', protein_g: '140', fat_g: '70', carbs_g: '220' },
            remaining: { energy_kcal: '1680', protein_g: '105', fat_g: '52', carbs_g: '168' },
            status: entries.length ? 'incomplete' : 'unlogged',
            status_is_explicit: false,
          },
        });
      });
      await page.route('**/api/v1/nutrition/diary/copy/day**', async (route) => {
        const body = route.request().postDataJSON() as (typeof requests)[number];
        requests.push(body);
        if (route.request().url().endsWith('/preview')) {
          if (body.source_date === body.target_date)
            return route.fulfill({
              status: 422,
              json: { detail: 'source and target day must differ' },
            });
          return route.fulfill({
            json: {
              copy_scope: 'day',
              ...body,
              entries: [entry],
              preview_token: 'preview-1431-token',
              previewed_at: '2026-11-06T08:00:00Z',
            },
          });
        }
        commits += 1;
        await commitGate;
        copied = true;
        return route.fulfill({
          status: 201,
          json: {
            copy_scope: 'day',
            ...body,
            replayed: false,
            entries: [{ ...entry, id: 42, diary_date: target }],
          },
        });
      });

      await page.goto(`/app?section=nutrition&date=${today}`);
      const open = page.getByRole('button', { name: 'Скопировать день' });
      await open.click();
      const dialog = page.getByRole('dialog', { name: 'Повторить день' });
      const date = dialog.getByLabel('Дата назначения');
      await expect(date).toBeFocused();
      await expect(date).toHaveValue('');
      await expect(date).toHaveAttribute('max', today);
      await expect(date).toHaveAccessibleDescription(
        'Выберите дату, которая отличается от исходной.',
      );
      await expect(dialog.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
      expect(requests).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      );
      const bounds = await date.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
      await dialog.screenshot({
        path: testInfo.outputPath(`copy-day-after-${width}-${theme}.png`),
      });

      await page.keyboard.press('Tab');
      await expect(dialog.getByRole('button', { name: 'Отмена' })).toBeFocused();
      await page.keyboard.press('Shift+Tab');
      await expect(date).toBeFocused();
      await page.keyboard.press('Escape');
      await expect(dialog).toHaveCount(0);
      await expect(open).toBeFocused();
      await open.click();
      await date.fill(target);
      await expect(dialog.getByText('Завтрак', { exact: true })).toBeVisible();
      expect(requests).toEqual([{ source_date: today, target_date: target }]);
      const confirm = dialog.getByRole('button', { name: 'Подтвердить' });
      await confirm.click();
      await expect.poll(() => commits).toBe(1);
      const pending = dialog.getByRole('button', { name: 'Добавляем…' });
      await expect(pending).toBeDisabled();
      await pending.dispatchEvent('click');
      await expect(date).toBeDisabled();
      await page.keyboard.press('Escape');
      await expect(dialog).toBeVisible();
      expect(commits).toBe(1);
      expect(requests[1]).toEqual({
        source_date: today,
        target_date: target,
        preview_token: 'preview-1431-token',
      });
      releaseCommit();
      await expect(dialog).toHaveCount(0);
      const days = await page.evaluate(
        async ({ source, destination }) => {
          const get = async (date: string) =>
            (await fetch(`/api/v1/nutrition/diary?diary_date=${date}`)).json();
          return [await get(source), await get(destination)];
        },
        { source: today, destination: target },
      );
      expect(days[0].meals[0].entries).toEqual([entry]);
      expect(days[1].meals[0].entries).toEqual([{ ...entry, id: 42, diary_date: target }]);
    });
  }
}
