import { mkdirSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { installTelegramHarness, TelegramHarness } from './fixtures/mobile-tma';

const today = '2026-11-06';
const selected = '2026-11-07';
const base = {
  id: 1,
  user_id: 1,
  calories: 2100,
  protein_g: 140,
  fat_g: 70,
  carbs_g: 225,
  effective_from: today,
  effective_to: null,
  source: 'manual',
  created_at: `${today}T00:00:00`,
  saved_at: `${today}T00:00:00`,
  note: null,
};
const target = { ...base, id: 2, calories: 2300, protein_g: 150, fat_g: 75, carbs_g: 250 };
const program = {
  program_id: 8,
  revision_number: 2,
  title: 'Тестовая программа',
  start_date: today,
  duration_weeks: 12,
  schedule_mode: 'calendar',
  week_types: ['light', 'medium', 'heavy'],
};
const zero = { energy_kcal: '0', protein_g: '0', fat_g: '0', carbs_g: '0', fiber_g: null };

for (const width of [320, 390, 1280]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`цели по дням: ${width}px ${theme}`, async ({ page }) => {
      await page.setViewportSize({
        width,
        height: width === 320 ? 720 : width === 390 ? 844 : 900,
      });
      await page.clock.setFixedTime(new Date('2026-11-06T12:00:00Z'));
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, {
        browserSession: true,
        fixedDate: today,
        nutritionSuggestions: 'empty',
      });
      let saved = false;
      let changedProgram = false;
      let empty = false;
      let writes = 0;
      await page.route('**/api/v1/nutrition/diary/suggestions?**', (route) => {
        const active = saved ? { ...target, calories: 2250 } : target;
        const goals = empty
          ? null
          : {
              energy_kcal: String(active.calories),
              protein_g: String(active.protein_g),
              fat_g: String(active.fat_g),
              carbs_g: String(active.carbs_g),
            };
        return route.fulfill({
          json: {
            mode: 'deterministic',
            diary_date: selected,
            targets: goals,
            remaining: goals,
            remaining_confidence: empty ? null : 'exact',
            limitations: [],
            candidates: [],
            max_candidates: 6,
          },
        });
      });
      await page.route('**/api/v1/nutrition/diary?**', async (route) => {
        const diaryDate = new URL(route.request().url()).searchParams.get('diary_date');
        const active = saved ? { ...target, calories: 2250 } : target;
        const goals = empty
          ? null
          : {
              energy_kcal: String(active.calories),
              protein_g: String(active.protein_g),
              fat_g: String(active.fat_g),
              carbs_g: String(active.carbs_g),
            };
        await route.fulfill({
          json: {
            diary_date: diaryDate,
            timezone: 'Europe/Moscow',
            meals: [],
            totals: zero,
            targets: goals,
            remaining: goals,
            status: 'unlogged',
            status_is_explicit: false,
          },
        });
      });
      await page.route('**/api/v1/nutrition/targets/for-date?**', (route) =>
        route.fulfill({
          json: {
            date: selected,
            target: empty ? null : saved ? { ...target, calories: 2250 } : target,
            origin: empty ? 'none' : saved ? 'date' : 'schedule',
            day_type: saved ? 'recovery' : 'rest',
            week_type: 'heavy',
            frozen: false,
          },
        }),
      );
      await page.route('**/api/v1/nutrition/targets/schedule/program', (route) =>
        route.fulfill({ json: { ...program, revision_number: changedProgram ? 2 : 1 } }),
      );
      await page.route('**/api/v1/nutrition/targets/schedule/binding?**', (route) =>
        route.fulfill({
          json: {
            id: 4,
            program_id: 8,
            revision_number: 1,
            effective_from: selected,
            current_revision_number: changedProgram ? 2 : 1,
            program_changed: changedProgram,
          },
        }),
      );
      await page.route('**/api/v1/nutrition/targets/program-day?**', (route) =>
        route.fulfill({
          json: {
            date: selected,
            program_id: 8,
            revision_number: 2,
            day_type: 'rest',
            week_type: 'heavy',
          },
        }),
      );
      await page.route('**/api/v1/nutrition/targets/schedule', (route) =>
        route.fulfill({
          json: ['training', 'recovery', 'rest'].map((day_type, index) => ({
            id: index + 1,
            scope: 'template',
            day_type,
            week_type: null,
            effective_from: selected,
            program_id: null,
            source_cycle_week: null,
            cycle_boundary: null,
            weekday: null,
            target: index ? base : target,
          })),
        }),
      );
      await page.route('**/api/v1/nutrition/targets/schedule/preview', (route) =>
        route.fulfill({
          json: {
            expected_binding_id: 4,
            expected_target_version: saved ? 3 : 2,
            program_id: 8,
            revision_number: 2,
            effective_from: selected,
            date_from: selected,
            date_to: '2027-01-28',
            changes: [{ date: selected, before: base, after: target }],
          },
        }),
      );
      await page.route('**/api/v1/nutrition/targets/schedule/binding/preview', (route) =>
        route.fulfill({
          json: {
            expected_binding_id: 4,
            expected_target_version: saved ? 3 : 2,
            program_id: 8,
            revision_number: 2,
            effective_from: selected,
            date_from: selected,
            date_to: '2027-01-28',
            changes: [{ date: selected, before: target, after: base }],
          },
        }),
      );
      await page.route('**/api/v1/nutrition/targets/dates', async (route) => {
        writes += 1;
        const body = route.request().postDataJSON();
        expect(body).toMatchObject({
          effective_from: selected,
          day_type: 'recovery',
          calories: 2250,
          expected_target_id: 2,
        });
        expect(route.request().headers()['idempotency-key']).toBeTruthy();
        saved = true;
        await route.fulfill({
          json: { date: selected, day_type: body.day_type, target: { ...target, calories: 2250 } },
        });
      });
      const capture = async (name: string) => {
        if (!process.env.EVIDENCE_952) return;
        const directory = '../docs/ux-proposals/issue-952/after';
        mkdirSync(directory, { recursive: true });
        await page.screenshot({
          path: `${directory}/chromium-${width}-${theme}-${name}.png`,
          fullPage: true,
          animations: 'disabled',
        });
        if (width <= 390)
          await page.screenshot({
            path: `${directory}/chromium-${width}-${theme}-${name}-viewport.png`,
            animations: 'disabled',
          });
      };
      const noOverflow = async () =>
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      await page.goto(`/app?section=nutrition&date=${selected}`);
      await expect(page.getByText('По программе', { exact: true })).toBeVisible();
      await expect(page.getByText('Пока нет готовых вариантов')).toBeVisible();
      await noOverflow();
      await capture('day');
      await page.getByRole('button', { name: 'Настройки КБЖУ' }).click();
      await expect(page.getByRole('heading', { name: 'Цели по дням' })).toBeFocused();
      await expect(page.getByText(/Тяжёлая неделя ·/)).toBeVisible();
      await noOverflow();
      await capture('settings');
      await page.getByLabel('Тип дня').selectOption('recovery');
      await capture('settings-recovery');
      await page.getByLabel('Тип дня').selectOption('rest');
      await capture('settings-rest');
      await page.getByLabel('Тип дня').selectOption('training');
      const weekEdit = page.getByRole('button', { name: 'Изменить уточнение' });
      await weekEdit.evaluate((button) => button.scrollIntoView({ block: 'center' }));
      expect(
        await weekEdit.evaluate((button) => {
          const box = button.getBoundingClientRect();
          return button.contains(
            document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2),
          );
        }),
      ).toBe(true);
      await weekEdit.click();
      await capture('week-edit');
      await page.getByRole('button', { name: 'Отмена' }).click();
      await page
        .locator('.nutrition-goal-row')
        .filter({ hasText: 'Тренировочный' })
        .getByRole('button', { name: 'Изменить' })
        .click();
      await expect(page.getByRole('heading', { name: 'Изменить цель' })).toBeVisible();
      await capture('settings-edit');
      await page.getByRole('button', { name: 'Проверить изменения' }).click();
      await expect(page.getByRole('heading', { name: 'Будущие цели' })).toBeFocused();
      expect(writes).toBe(0);
      await capture('template-preview');
      await page.getByRole('button', { name: 'Не применять' }).click();
      await page.getByRole('button', { name: 'К дневнику' }).click();
      await page.getByRole('button', { name: 'Изменить на эту дату' }).click();
      await expect(page.getByRole('heading', { name: 'Изменить цель' })).toBeFocused();
      await page.getByLabel('Тип дня').selectOption('recovery');
      await page.getByLabel('Калории, ккал').fill('2250');
      await capture('override');
      await page.getByLabel('Будущие такие дни').check();
      await capture('future-override');
      await page.getByRole('button', { name: 'Проверить изменения' }).click();
      await expect(page.getByRole('heading', { name: 'Будущие цели' })).toBeVisible();
      expect(writes).toBe(0);
      await capture('future-preview');
      await page.getByRole('button', { name: 'Не применять' }).click();
      await page.getByLabel('Только выбранная дата').check();
      await page.getByRole('button', { name: 'Проверить изменения' }).click();
      await expect(page.getByRole('heading', { name: 'Цель на выбранную дату' })).toBeFocused();
      expect(writes).toBe(0);
      await capture('date-preview');
      await page.getByRole('button', { name: 'Применить к этой дате' }).click();
      await expect(page.getByText('Изменено вручную')).toBeVisible();
      expect(writes).toBe(1);
      changedProgram = true;
      await page.getByRole('button', { name: 'Настройки КБЖУ' }).click();
      await expect(page.getByText('Программа изменилась')).toBeVisible();
      await capture('conflict');
      await page.getByRole('button', { name: 'Проверить изменения' }).click();
      await expect(page.getByRole('heading', { name: 'Будущие цели' })).toBeVisible();
      await capture('binding-preview');
      empty = true;
      await page.goto(`/app?section=nutrition&date=${selected}`);
      await expect(page.getByText('Без цели', { exact: true })).toBeVisible();
      await expect(page.getByText('Нет цели КБЖУ на эту дату')).toBeVisible();
      await capture('empty');
      await noOverflow();
    });
  }
}

test('кнопка Telegram возвращает из настроек к дневнику', async ({ page }) => {
  await installTelegramHarness(page);
  await installPlatformApi(page);
  await page.goto('/app?section=nutrition');
  await page.getByRole('button', { name: 'Настройки КБЖУ' }).click();
  await expect(page.getByRole('heading', { name: 'Цели по дням' })).toBeVisible();
  const telegram = new TelegramHarness(page);
  await expect.poll(async () => (await telegram.state()).backButton.visible).toBe(true);
  await telegram.clickBack();
  await expect(page.getByRole('heading', { name: 'Питание', exact: true })).toBeVisible();
});
