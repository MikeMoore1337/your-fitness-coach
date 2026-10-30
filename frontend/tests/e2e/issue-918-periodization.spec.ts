import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow, installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

const exercises = [
  {
    id: 11,
    title: 'Жим штанги лёжа',
    slug: 'bench-press',
    metric_type: 'strength',
    primary_muscle: 'Грудь',
    equipment: 'Штанга',
    primary_muscle_ids: ['chest'],
    secondary_muscle_ids: [],
    equipment_ids: ['barbell'],
    alternatives: [],
    difficulty_level: 'beginner',
    is_custom: false,
    is_personalized: false,
    has_guide: false,
  },
];

test('редактор сохраняет разные исходные недели и показывает шестнадцатую неделю', async ({
  page,
}) => {
  await installPlatformApi(page, { browserSession: true, activeProgram: false });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  let saved: {
    week_cycle: { week_types: (string | null)[] };
    days: { exercises: { weekly_prescriptions: { prescribed_sets: number }[] }[] }[];
  } | null = null;
  await page.route('**/api/v1/programs/templates', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    saved = route.request().postDataJSON();
    await route.fulfill({
      json: { template: { id: 100 }, assigned_program_id: 200, workouts_created: 4 },
    });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/app?section=programs&view=manage&start=create');
  const builder = page.locator('#program-builder');
  await expect(builder).toBeVisible();
  await builder.getByRole('combobox', { name: 'Поиск упражнения' }).click();
  await page.getByRole('option', { name: /Жим штанги лёжа/ }).click();
  await builder.getByText('Настройки программы').click();
  await builder.getByRole('checkbox', { name: /Включить периодизацию/ }).check();
  await builder.getByRole('spinbutton', { name: 'Исходных недель' }).fill('3');
  await builder.getByRole('spinbutton', { name: 'Всего недель' }).fill('16');
  await builder.getByRole('checkbox', { name: /Повторять исходный цикл/ }).check();
  await builder.getByRole('combobox', { name: 'Неделя 1' }).selectOption('heavy');
  await builder.getByRole('combobox', { name: 'Неделя 2' }).selectOption('heavy');
  await expect(builder.getByRole('combobox', { name: 'Неделя 3' })).toHaveValue('');
  await builder.getByRole('button', { name: 'Посмотреть план на 16 недель' }).click();
  const preview = builder.locator('.program-periodization__preview');
  await preview.getByRole('button', { name: 'Следующие недели' }).click();
  await expect(preview.getByText(/Неделя 16 · исходная 1 · проход 6/)).toBeVisible();
  await builder.getByRole('button', { name: 'Сохранить настройки' }).click();
  await builder.getByRole('spinbutton', { name: 'Исходная неделя' }).fill('2');
  await builder.getByRole('spinbutton', { name: 'Рабочие подходы' }).fill('5');
  await builder.getByRole('spinbutton', { name: 'Исходная неделя' }).fill('1');
  await expect(builder.getByRole('spinbutton', { name: 'Рабочие подходы' })).toHaveValue('3');
  await builder.getByRole('button', { name: 'Проверить и назначить' }).click();
  await builder.getByRole('button', { name: 'Создать и назначить' }).click();
  await expect.poll(() => saved).not.toBeNull();
  expect(saved!.week_cycle.week_types).toEqual(['heavy', 'heavy', null]);
  expect(
    saved!.days[0]!.exercises[0]!.weekly_prescriptions.map(
      (item: { prescribed_sets: number }) => item.prescribed_sets,
    ),
  ).toEqual([3, 5, 3]);
});

for (const theme of ['dark', 'light'] as const) {
  for (const width of [320, 360, 393, 430, 1440]) {
    test(`адаптивные настройки ${theme} ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 1440 ? 1000 : 852 });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, activeProgram: false });
      await page.route('**/api/v1/programs/exercises', (route) =>
        route.fulfill({ json: exercises }),
      );
      await page.goto('/app?section=programs&view=manage&start=create');
      const builder = page.locator('#program-builder');
      await builder.getByText('Настройки программы').click();
      await builder.getByRole('checkbox', { name: /Включить периодизацию/ }).check();
      await builder.getByRole('spinbutton', { name: 'Исходных недель' }).fill('3');
      await builder.getByRole('spinbutton', { name: 'Всего недель' }).fill('16');
      await builder.getByRole('checkbox', { name: /Повторять исходный цикл/ }).check();
      await builder.getByRole('combobox', { name: 'Неделя 1' }).selectOption('heavy');
      await builder.getByRole('combobox', { name: 'Неделя 2' }).selectOption('heavy');
      await expectNoHorizontalOverflow(page);
      const save = builder.getByRole('button', { name: 'Сохранить настройки' });
      await save.scrollIntoViewIfNeeded();
      await expect(save).toBeVisible();
      const overlapsNavigation = await save.evaluate((element) => {
        const navigation = document.querySelector('nav[aria-label="Основная навигация"]');
        if (!navigation) return false;
        const button = element.getBoundingClientRect();
        const nav = navigation.getBoundingClientRect();
        return button.left < nav.right && button.right > nav.left && button.top < nav.bottom && button.bottom > nav.top;
      });
      expect(overlapsNavigation).toBe(false);
      if (process.env.YFC_CAPTURE_918) {
        await builder
          .locator('.program-builder-settings')
          .screenshot({
            path: `../docs/ux/issue-918-after/${testInfo.project.name}-${theme}-${width}-setup.png`,
          });
      }
    });
  }
}

test('настройка доступна внутри имитации Telegram Mini App', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await installTelegramHarness(page, {
    colorScheme: 'dark',
    viewportHeight: 852,
    viewportStableHeight: 852,
  });
  await installPlatformApi(page, { browserSession: true, activeProgram: false });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  await page.goto('/app?section=programs&view=manage&start=create');
  const builder = page.locator('#program-builder');
  await builder.getByText('Настройки программы').click();
  await builder.getByRole('checkbox', { name: /Включить периодизацию/ }).check();
  await expect(builder.getByRole('spinbutton', { name: 'Исходных недель' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test('настройка доступна в имитации установленного PWA', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await page.addInitScript(() => {
    const original = window.matchMedia.bind(window);
    window.matchMedia = (query) => {
      const result = original(query);
      if (query === '(display-mode: standalone)') Object.defineProperty(result, 'matches', { value: true });
      return result;
    };
  });
  await installPlatformApi(page, { browserSession: true, activeProgram: false });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  await page.goto('/app?section=programs&view=manage&start=create');
  expect(await page.evaluate(() => window.matchMedia('(display-mode: standalone)').matches)).toBe(true);
  const builder = page.locator('#program-builder');
  await builder.getByText('Настройки программы').click();
  await builder.getByRole('checkbox', { name: /Включить периодизацию/ }).check();
  await expect(builder.getByRole('spinbutton', { name: 'Исходных недель' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test('числовые поля сохраняют фокус при уменьшении мобильного viewport', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await installPlatformApi(page, { browserSession: true, activeProgram: false });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  await page.goto('/app?section=programs&view=manage&start=create');
  const builder = page.locator('#program-builder');
  await builder.getByText('Настройки программы').click();
  await builder.getByRole('checkbox', { name: /Включить периодизацию/ }).check();
  const input = builder.getByRole('spinbutton', { name: 'Всего недель' });
  await input.focus();
  await page.setViewportSize({ width: 393, height: 540 });
  await input.fill('30');
  await expect(input).toBeFocused();
  await expect(input).toHaveValue('30');
  await expectNoHorizontalOverflow(page);
});

test('предпросмотр поддерживает 7/16 и 3/30', async ({ page }) => {
  await installPlatformApi(page, { browserSession: true, activeProgram: false });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  await page.goto('/app?section=programs&view=manage&start=create');
  const builder = page.locator('#program-builder');
  await builder.getByText('Настройки программы').click();
  await builder.getByRole('checkbox', { name: /Включить периодизацию/ }).check();
  const length = builder.getByRole('spinbutton', { name: 'Исходных недель' });
  const duration = builder.getByRole('spinbutton', { name: 'Всего недель' });
  await length.fill('7');
  await duration.fill('16');
  await builder.getByRole('checkbox', { name: /Повторять исходный цикл/ }).check();
  await builder.getByRole('button', { name: 'Посмотреть план на 16 недель' }).click();
  const preview = builder.locator('.program-periodization__preview');
  await preview.getByRole('button', { name: 'Следующие недели' }).click();
  await expect(preview.getByText(/Неделя 16 · исходная 2 · проход 3/)).toBeVisible();
  await length.fill('3');
  await duration.fill('30');
  await builder.getByRole('button', { name: 'Посмотреть план на 30 недель' }).click();
  await preview.getByRole('button', { name: 'Следующие недели' }).click();
  await preview.getByRole('button', { name: 'Следующие недели' }).click();
  await expect(preview.getByText(/Неделя 30 · исходная 3 · проход 10/)).toBeVisible();
});

test('повторное открытие настроек с клавиатуры и указателя', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 852 });
  await installPlatformApi(page, { browserSession: true, activeProgram: false });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  await page.goto('/app?section=programs&view=manage&start=create');
  const builder = page.locator('#program-builder');
  const trigger = builder.locator('.program-builder-settings > summary');
  for (let index = 0; index < 5; index += 1) {
    if (index % 2) {
      await trigger.focus();
      await trigger.press('Enter');
    } else {
      await trigger.click();
    }
    await expect(builder.getByRole('checkbox', { name: /Включить периодизацию/ })).toBeVisible();
    await trigger.press('Escape');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  }
});

test('предпросмотр будущих повторов предупреждает об истории и обрабатывает 409', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  await page.route('**/api/v1/programs/assigned/77/cycle/week-type/preview', async (route) => {
    const body = route.request().postDataJSON();
    const numbers = body.from_week ? [3, 6, 9] : body.occurrence_weeks;
    await route.fulfill({ json: {
      weeks: numbers.map((number: number) => ({
        week_number: number, source_cycle_week: 1, cycle_iteration: Math.floor(number / 3),
        cycle_length: 3, repeat: true, periodization_enabled: true,
        workouts: [{ id: number, day_number: 1, title: 'Силовая', scheduled_date: '2030-01-10',
          status: number === 6 ? 'completed' : 'planned', changeable: number !== 6,
          week_type: 'heavy', exercises: [{ source_template_exercise_id: 12, exercise_id: 11,
            prescribed_sets: 3, prescribed_reps: '8-10', prescribed_duration_minutes: null,
            rest_seconds: 90, notes: null, metric_type: 'strength', prescription: null }] }],
      })), total_weeks: numbers.length, offset: 0,
    } });
  });
  await page.route('**/api/v1/programs/assigned/77/cycle/week-type', (route) =>
    route.fulfill({ status: 409, json: { detail: 'Program revision conflict' } }),
  );
  await page.goto('/app?section=programs&view=manage&panel=operations');
  await page.getByText('Периодизация и будущие недели').click();
  const panel = page.getByRole('region', { name: 'Периодизация назначения' });
  await expect(panel.getByText(/Неделя 3 · исходная 1/)).toBeVisible();
  await panel.getByRole('combobox', { name: 'Новый тип недели' }).selectOption('light');
  await panel.getByRole('radio', { name: /Будущие повторы/ }).check();
  await panel.getByRole('button', { name: 'Проверить изменения' }).click();
  const impact = panel.locator('.program-periodization__preview');
  await expect(impact.getByText(/не изменится/)).toBeVisible();
  await expect(impact.getByText(/Тяжёлая → Лёгкая/).first()).toBeVisible();
  await impact.getByRole('button', { name: 'Применить изменения' }).click();
  await expect(panel.getByRole('alert')).toContainText('План уже изменился');
  await expect(panel.getByRole('combobox', { name: 'Новый тип недели' })).toHaveValue('light');
  await expectNoHorizontalOverflow(page);
});
