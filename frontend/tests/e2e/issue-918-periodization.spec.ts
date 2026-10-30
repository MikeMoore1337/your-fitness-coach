import { expect, test, type Page } from '@playwright/test';
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

async function installCycleApi(page: Page) {
  const preview = async (route: import('@playwright/test').Route) => {
    const body = route.request().postDataJSON();
    const numbers: number[] = body.from_week ? [3, 6, 9] : (body.occurrence_weeks ?? [3, 4, 5, 6]);
    await route.fulfill({
      json: {
        weeks: numbers.map((number) => ({
          week_number: number,
          source_cycle_week: 1,
          cycle_iteration: Math.max(1, Math.floor(number / 3)),
          cycle_length: 3,
          repeat: true,
          periodization_enabled: true,
          workouts: [
            {
              id: number,
              day_number: 1,
              title: 'Силовая',
              scheduled_date: '2030-01-10',
              status: number === 6 ? 'completed' : 'planned',
              changeable: number !== 6,
              week_type: 'heavy',
              exercises: [
                {
                  source_template_exercise_id: 12,
                  exercise_id: 11,
                  prescribed_sets: 3,
                  prescribed_reps: '8-10',
                  prescribed_duration_minutes: null,
                  rest_seconds: 90,
                  notes: null,
                  metric_type: 'strength',
                  prescription: null,
                },
              ],
            },
          ],
        })),
        total_weeks: numbers.length,
        offset: 0,
      },
    });
  };
  await page.route(
    /\/api\/v1\/programs\/assigned\/77\/cycle\/(week-type|disable|duration|enable)\/preview$/,
    preview,
  );
  await page.route('**/api/v1/programs/assigned/77/cycle/week-type', (route) =>
    route.fulfill({ status: 409, json: { detail: 'Program revision conflict' } }),
  );
}

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
      if (width < 1100) await builder.getByRole('button', { name: /Выберите упражнение/ }).click();
      if (width <= 680) await page.getByRole('button', { name: 'Поиск упражнения' }).click();
      else await page.getByRole('combobox', { name: 'Поиск упражнения' }).click();
      if (width <= 680) await page.getByRole('button', { name: /^Жим штанги лёжа/ }).click();
      else await page.getByRole('option', { name: /Жим штанги лёжа/ }).click();
      if (width < 1100) await page.getByRole('button', { name: 'Закрыть параметры' }).click();
      if (process.env.YFC_CAPTURE_918)
        await builder.screenshot({
          path: `../docs/ux/issue-918-after/${testInfo.project.name}-${theme}-${width}-editor.png`,
        });
      await builder.getByText('Настройки программы').click();
      const shot = async (state: string) => {
        if (process.env.YFC_CAPTURE_918)
          await builder.locator('.program-builder-settings').screenshot({
            path: `../docs/ux/issue-918-after/${testInfo.project.name}-${theme}-${width}-${state}.png`,
          });
      };
      await shot('off');
      await builder.getByRole('checkbox', { name: /Включить периодизацию/ }).check();
      await builder.getByRole('spinbutton', { name: 'Исходных недель' }).fill('3');
      await builder.getByRole('spinbutton', { name: 'Всего недель' }).fill('3');
      await shot('single');
      await builder.getByRole('spinbutton', { name: 'Всего недель' }).fill('16');
      await shot('invalid');
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
        return (
          button.left < nav.right &&
          button.right > nav.left &&
          button.top < nav.bottom &&
          button.bottom > nav.top
        );
      });
      expect(overlapsNavigation).toBe(false);
      await shot('setup');
      if (process.env.YFC_CAPTURE_918) {
        await builder.locator('.program-periodization').scrollIntoViewIfNeeded();
        await page.screenshot({
          path: `../docs/ux/issue-918-after/${testInfo.project.name}-${theme}-${width}-shell.png`,
        });
        await builder.getByRole('button', { name: 'Посмотреть план на 16 недель' }).click();
        await shot('preview');
        const preview = builder.locator('.program-periodization__preview');
        await preview.getByRole('button', { name: 'Следующие недели' }).click();
        await expect(preview.getByText(/Неделя 16 · исходная 1 · проход 6/)).toBeVisible();
        await shot('week16');
        await builder.getByRole('spinbutton', { name: 'Исходных недель' }).fill('1');
        await builder.getByRole('button', { name: 'Посмотреть план на 16 недель' }).click();
        await preview.getByRole('button', { name: 'Следующие недели' }).click();
        await expect(preview.getByText(/Неделя 16 · исходная 1 · проход 16/)).toBeVisible();
        await shot('one');
        await builder.getByRole('spinbutton', { name: 'Исходных недель' }).fill('7');
        await builder.getByRole('button', { name: 'Посмотреть план на 16 недель' }).click();
        await preview.getByRole('button', { name: 'Следующие недели' }).click();
        await expect(preview.getByText(/Неделя 16 · исходная 2 · проход 3/)).toBeVisible();
        await shot('seven');
        await builder.getByRole('spinbutton', { name: 'Исходных недель' }).fill('3');
        await builder.getByRole('spinbutton', { name: 'Всего недель' }).fill('30');
        await builder.getByRole('button', { name: 'Посмотреть план на 30 недель' }).click();
        await preview.getByRole('button', { name: 'Следующие недели' }).click();
        await preview.getByRole('button', { name: 'Следующие недели' }).click();
        await expect(preview.getByText(/Неделя 30 · исходная 3 · проход 10/)).toBeVisible();
        await shot('thirty');
        await builder.getByRole('button', { name: 'Сохранить настройки' }).click();
        await builder.getByRole('spinbutton', { name: 'Исходная неделя' }).fill('2');
        await builder.screenshot({
          path: `../docs/ux/issue-918-after/${testInfo.project.name}-${theme}-${width}-source.png`,
        });
      }
    });
  }
}

for (const theme of ['dark', 'light'] as const) {
  for (const width of [320, 360, 393, 430, 1440]) {
    test(`действующая программа ${theme} ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 1440 ? 1000 : 852 });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
      await page.route('**/api/v1/programs/exercises', (route) =>
        route.fulfill({ json: exercises }),
      );
      await installCycleApi(page);
      await page.goto('/app?section=programs&view=manage&panel=operations');
      await page.getByText('Периодизация и будущие недели').click();
      const panel = page.getByRole('region', { name: 'Периодизация назначения' });
      await expect(panel.getByText(/Неделя 3 · исходная 1/)).toBeVisible();
      const shot = async (state: string) => {
        if (process.env.YFC_CAPTURE_918)
          await panel.screenshot({
            path: `../docs/ux/issue-918-after/${testInfo.project.name}-${theme}-${width}-${state}.png`,
          });
      };
      await shot('scope-one');
      await panel.getByRole('combobox', { name: 'Новый тип недели' }).selectOption('light');
      await panel.getByRole('radio', { name: /Будущие повторы/ }).check();
      await shot('scope-repeat');
      await panel.getByRole('radio', { name: /Выбрать недели/ }).check();
      await expect(panel.getByRole('checkbox', { name: 'Неделя 1', exact: true })).toBeDisabled();
      await panel.getByRole('checkbox', { name: 'Неделя 3', exact: true }).check();
      await panel.getByRole('checkbox', { name: 'Неделя 6', exact: true }).check();
      await shot('scope-selected');
      if (width < 1100) {
        const check = panel.getByRole('button', { name: 'Проверить изменения' });
        await check.scrollIntoViewIfNeeded();
        const button = await check.boundingBox();
        const navigation = await page
          .getByRole('navigation', { name: 'Основная навигация' })
          .boundingBox();
        expect(button).not.toBeNull();
        expect(navigation).not.toBeNull();
        expect(button!.y + button!.height).toBeLessThanOrEqual(navigation!.y);
      }
      await panel.getByRole('radio', { name: /Будущие повторы/ }).check();
      await panel.getByRole('button', { name: 'Проверить изменения' }).click();
      await expect(panel.getByRole('heading', { name: 'Проверить изменения' })).toBeFocused();
      await expect(panel.getByText(/Тяжёлая → Лёгкая/).first()).toBeVisible();
      await shot('type-impact');
      await panel.getByRole('button', { name: 'Применить изменения' }).click();
      await expect(panel.getByRole('alert')).toContainText('План уже изменился');
      await expect(panel.getByRole('button', { name: 'Обновить план' })).toBeVisible();
      await shot('conflict');
      await panel.getByRole('button', { name: 'Вернуться' }).click();
      await panel.getByRole('combobox', { name: 'Что изменить' }).selectOption('exercise');
      await panel.getByRole('combobox', { name: 'Упражнение' }).selectOption('1:12');
      await shot('exercise');
      await panel.getByRole('button', { name: 'Проверить изменения' }).click();
      await expect(panel.getByText(/Новое предписание/)).toBeVisible();
      await shot('exercise-impact');
      await panel.getByRole('button', { name: 'Вернуться' }).click();
      await panel.getByRole('combobox', { name: 'Что изменить' }).selectOption('disable');
      await shot('disable');
      await panel.getByRole('button', { name: 'Проверить изменения' }).click();
      await shot('disable-impact');
      await panel.getByRole('button', { name: 'Вернуться' }).click();
      await panel.getByRole('combobox', { name: 'Что изменить' }).selectOption('duration');
      await panel.getByRole('spinbutton', { name: 'Всего недель' }).fill('12');
      await shot('duration');
      await panel.getByRole('button', { name: 'Проверить изменения' }).click();
      await shot('duration-impact');
      await expectNoHorizontalOverflow(page);
    });
  }
}

for (const theme of ['dark', 'light'] as const) {
  for (const width of [320, 360, 393, 430, 1440]) {
    test(`спортсмен и тренер ${theme} ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 1440 ? 1000 : 852 });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, {
        browserSession: true,
        programHistory: 'many',
        trainerActive: true,
      });
      await installCycleApi(page);
      await page.route('**/api/v1/programs/templates/mine', (route) =>
        route.fulfill({
          json: [
            {
              id: 10,
              title: 'Тестовая программа тренера',
              goal: 'maintenance',
              level: 'beginner',
              split_type: 'full_body',
              owner_user_id: 42,
              owner_telegram_user_id: 42,
              created_by_user_id: 42,
              is_public: false,
              is_example: false,
              can_edit: false,
              is_assigned_to_current_user: true,
              is_active_for_current_user: true,
              assigned_by_user_id: 42,
              assigned_by_full_name: 'Тестовый тренер',
              assigned_program_id: 77,
              assigned_program_status: 'active',
              assigned_program_start_date: '2030-01-01',
              assigned_program_duration_weeks: 10,
              current_revision_number: 4,
              days: [{ id: 1, day_number: 1, title: 'Силовая', exercises: [] }],
            },
          ],
        }),
      );
      await page.route('**/api/v1/coach/assigned-programs', (route) =>
        route.fulfill({
          json: [
            {
              id: 77,
              client_id: 11,
              client_full_name: 'Тестовый клиент',
              template_id: 10,
              title: 'Тестовая программа клиента',
              goal: 'maintenance',
              level: 'beginner',
              assigned_at: '2030-01-01T10:00:00',
              is_active: true,
              status: 'active',
              start_date: '2030-01-01',
              duration_weeks: 10,
              schedule_weekdays: [0],
              completed_at: null,
              workouts_total: 10,
              workouts_completed: 2,
              workouts_planned: 8,
              next_workout_date: '2030-01-08',
              current_revision_number: 4,
            },
          ],
        }),
      );
      await page.goto('/app?section=programs&view=manage&panel=operations');
      await page.getByText('Периодизация и будущие недели').click();
      const panel = page.getByRole('region', { name: 'Периодизация назначения' });
      await expect(panel.getByText(/План подготовлен тренером/)).toBeVisible();
      await expect(panel.getByRole('combobox', { name: 'Что изменить' })).toHaveCount(0);
      if (process.env.YFC_CAPTURE_918)
        await panel.screenshot({
          path: `../docs/ux/issue-918-after/${testInfo.project.name}-${theme}-${width}-athlete.png`,
        });
      await page.goto('/coach?tab=programs');
      await page.getByRole('heading', { name: 'Программы клиентов' }).click();
      await page.getByText('Периодизация и будущие недели').click();
      await expect(panel.getByRole('combobox', { name: 'Что изменить' })).toBeVisible();
      if (process.env.YFC_CAPTURE_918)
        await panel.screenshot({
          path: `../docs/ux/issue-918-after/${testInfo.project.name}-${theme}-${width}-coach.png`,
        });
      await expectNoHorizontalOverflow(page);
    });
  }
}

for (const theme of ['dark', 'light'] as const) {
  for (const width of [320, 360, 393, 430, 1440]) {
    test(`загрузка и прежняя программа ${theme} ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 1440 ? 1000 : 852 });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
      await installCycleApi(page);
      let mode: 'loading' | 'error' | 'legacy' = 'loading';
      let release = () => {};
      const pending = new Promise<void>((resolve) => {
        release = resolve;
      });
      await page.route('**/api/v1/programs/assigned/77/cycle/week-type/preview', async (route) => {
        if (mode === 'loading') await pending;
        await route.fulfill(
          mode === 'legacy'
            ? { status: 422, json: { detail: 'У назначения нет сохранённого цикла' } }
            : { status: 500, json: { detail: 'Тестовая ошибка' } },
        );
      });
      await page.goto('/app?section=programs&view=manage&panel=operations');
      await page.getByText('Периодизация и будущие недели').click();
      const panel = page.getByRole('region', { name: 'Периодизация назначения' });
      const shot = async (state: string) => {
        if (process.env.YFC_CAPTURE_918)
          await panel.screenshot({
            path: `../docs/ux/issue-918-after/${testInfo.project.name}-${theme}-${width}-${state}.png`,
          });
      };
      await expect(panel.getByRole('status')).toContainText('Загружаем план');
      await shot('loading');
      mode = 'error';
      release();
      await expect(panel.getByRole('alert')).toContainText('Не удалось загрузить неделю');
      await shot('error');
      mode = 'legacy';
      await panel.getByRole('button', { name: 'Повторить загрузку' }).click();
      await expect(panel.getByRole('checkbox', { name: /Включить периодизацию/ })).toBeVisible();
      await shot('legacy');
      await panel.getByRole('checkbox', { name: /Включить периодизацию/ }).check();
      await panel.getByRole('spinbutton', { name: 'Исходных недель' }).fill('3');
      await panel.getByRole('checkbox', { name: /Повторять исходный цикл/ }).check();
      await shot('enable');
      await panel.getByRole('button', { name: 'Проверить включение' }).click();
      await expect(panel.getByText('История сохранится')).toBeVisible();
      await shot('enable-impact');
      await expectNoHorizontalOverflow(page);
    });
  }
}

for (const mode of ['pwa', 'tma'] as const) {
  for (const theme of ['dark', 'light'] as const) {
    for (const width of [320, 360, 393, 430]) {
      test(`оболочка ${mode} ${theme} ${width}`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 852 });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        if (mode === 'tma') {
          await installTelegramHarness(page, {
            colorScheme: theme,
            viewportHeight: 852,
            viewportStableHeight: 852,
          });
        } else {
          await page.addInitScript(() => {
            const original = window.matchMedia.bind(window);
            window.matchMedia = (query) => {
              const result = original(query);
              if (query === '(display-mode: standalone)')
                Object.defineProperty(result, 'matches', { value: true });
              return result;
            };
          });
        }
        await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
        await installCycleApi(page);
        await page.goto('/app?section=programs&view=manage&start=create');
        const builder = page.locator('#program-builder');
        await builder.getByText('Настройки программы').click();
        await builder.getByRole('checkbox', { name: /Включить периодизацию/ }).check();
        await builder.getByRole('spinbutton', { name: 'Исходных недель' }).fill('3');
        await builder.getByRole('spinbutton', { name: 'Всего недель' }).fill('16');
        await builder.getByRole('checkbox', { name: /Повторять исходный цикл/ }).check();
        await builder.locator('.program-periodization').scrollIntoViewIfNeeded();
        if (process.env.YFC_CAPTURE_918)
          await page.screenshot({
            path: `../docs/ux/issue-918-after/${testInfo.project.name}-${mode}-${theme}-${width}-setup.png`,
          });
        await expectNoHorizontalOverflow(page);
        await page.goto('/app?section=programs&view=manage&panel=operations');
        await page.getByText('Периодизация и будущие недели').click();
        const panel = page.getByRole('region', { name: 'Периодизация назначения' });
        await expect(panel.getByRole('combobox', { name: 'Новый тип недели' })).toBeVisible();
        await panel.getByRole('combobox', { name: 'Новый тип недели' }).selectOption('light');
        await panel.getByRole('radio', { name: /Будущие повторы/ }).check();
        await panel.getByRole('button', { name: 'Проверить изменения' }).click();
        await expect(panel.getByText('История сохранится')).toBeVisible();
        await panel.scrollIntoViewIfNeeded();
        if (process.env.YFC_CAPTURE_918)
          await page.screenshot({
            path: `../docs/ux/issue-918-after/${testInfo.project.name}-${mode}-${theme}-${width}-impact.png`,
          });
        await expectNoHorizontalOverflow(page);
      });
    }
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
      if (query === '(display-mode: standalone)')
        Object.defineProperty(result, 'matches', { value: true });
      return result;
    };
  });
  await installPlatformApi(page, { browserSession: true, activeProgram: false });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  await page.goto('/app?section=programs&view=manage&start=create');
  expect(await page.evaluate(() => window.matchMedia('(display-mode: standalone)').matches)).toBe(
    true,
  );
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

test('предпросмотр будущих повторов предупреждает об истории и обрабатывает 409', async ({
  page,
}) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  await installCycleApi(page);
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
  await panel.getByRole('button', { name: 'Вернуться' }).click();
  await expect(panel.getByRole('combobox', { name: 'Новый тип недели' })).toHaveValue('light');
  await expectNoHorizontalOverflow(page);
});
