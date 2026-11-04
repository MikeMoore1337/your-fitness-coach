import { expect, test, type Page } from '@playwright/test';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ serviceWorkers: 'block' });

const exercise = {
  source_template_exercise_id: 12,
  exercise_id: 11,
  metric_type: 'strength',
  prescribed_sets: 2,
  prescribed_reps: '8-10',
  prescribed_duration_minutes: null,
  rest_seconds: 90,
  notes: null,
  prescription: null,
};

async function installCycle(page: Page) {
  await page.route('**/api/v1/programs/assigned/77/cycle/week-type/preview', (route) =>
    route.fulfill({
      json: {
        weeks: [
          {
            week_number: 3,
            source_cycle_week: 1,
            cycle_iteration: 1,
            cycle_length: 3,
            repeat: true,
            periodization_enabled: true,
            workouts: [
              {
                id: 3,
                day_number: 1,
                title: 'Силовая',
                scheduled_date: '2030-01-10',
                status: 'planned',
                changeable: true,
                week_type: 'heavy',
                exercises: [exercise],
              },
            ],
          },
        ],
        total_weeks: 1,
        offset: 0,
      },
    }),
  );
}

for (const theme of ['dark', 'light'] as const) {
  test(`новый порядок цикла и точный запрос ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
    await installCycle(page);
    let saved: unknown;
    await page.route('**/api/v1/programs/assigned/77/cycle/revision/preview', async (route) => {
      const body = route.request().postDataJSON();
      expect(body.source_week_order).toEqual([1, 2, 3, 1]);
      await route.fulfill({
        json: {
          total_weeks: 8,
          offset: 0,
          weeks: [
            {
              week_number: 3,
              source_cycle_week: 1,
              new_source_cycle_week: 1,
              workouts: [
                {
                  id: 3,
                  day_number: 1,
                  title: 'Силовая',
                  scheduled_date: '2030-01-10',
                  status: 'in_progress',
                  changeable: false,
                  week_type: 'heavy',
                  new_week_type: 'heavy',
                  exercises: [exercise],
                  new_exercises: [exercise],
                },
              ],
            },
          ],
        },
      });
    });
    await page.route('**/api/v1/programs/assigned/77/cycle', async (route) => {
      saved = route.request().postDataJSON();
      await route.fulfill({ json: { current_revision_number: 5 } });
    });
    await page.goto('/app?section=programs&view=manage&panel=operations');
    await page.getByText('Периодизация и будущие недели').click();
    const panel = page.getByRole('region', { name: 'Периодизация назначения' });
    await panel.getByRole('combobox', { name: 'Что изменить' }).selectOption('cycle');
    await panel.getByRole('spinbutton', { name: 'Исходных недель в новом цикле' }).fill('4');
    await expect(panel.getByRole('combobox', { name: 'Новая неделя 4' })).toHaveValue('1');
    await expectNoHorizontalOverflow(page);
    await panel.getByRole('button', { name: 'Проверить изменения' }).click();
    await expect(panel.getByText(/начата · не изменится/)).toBeVisible();
    await expect(panel.getByText(/исходная 1 → новая 1/)).toBeVisible();
    await panel.getByRole('button', { name: 'Применить изменения' }).click();
    await expect
      .poll(() => saved)
      .toMatchObject({
        expected_revision_number: 4,
        effective_from_week: 3,
        source_week_order: [1, 2, 3, 1],
        repeat: true,
      });
  });
}

test('начатый подход меняется только после проверки и подтверждения', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 844 });
  await installPlatformApi(page, { browserSession: true, workoutStatus: 'in_progress' });
  let saved: unknown;
  await page.route('**/api/v1/workouts/sets/201', async (route) => {
    saved = route.request().postDataJSON();
    await route.fulfill({
      json: {
        id: 201,
        set_number: 1,
        actual_reps: null,
        actual_weight: null,
        rir: null,
        set_kind: 'working',
        reached_failure: null,
        is_completed: false,
        version: 2,
      },
    });
  });
  await page.goto('/app');
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await page.getByRole('button', { name: 'Изменить план подхода' }).click();
  await page.getByLabel('Плановый вес, кг').fill('37,5');
  await page.getByLabel('План повторов').fill('8');
  await page.getByRole('button', { name: 'Проверить изменение' }).click();
  await expect(page.getByText('37.5 кг · 8 повторов')).toBeVisible();
  expect(saved).toBeUndefined();
  await page.getByRole('button', { name: 'Применить к подходу' }).click();
  await expect
    .poll(() => saved)
    .toMatchObject({
      expected_version: 1,
      planned_target: { weight_kg: 37.5, reps: 8, confirmed: true },
    });
});

for (const theme of ['dark', 'light'] as const) {
  for (const width of [393, 1440]) {
    test(`области дней и состав тренировки ${theme} ${width}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
      await installCycle(page);
      await page.route('**/api/v1/programs/exercises', (route) =>
        route.fulfill({
          json: [
            { id: 11, title: 'Присед со штангой', metric_type: 'strength' },
            { id: 12, title: 'Присед с гантелями', metric_type: 'strength' },
          ],
        }),
      );
      let saved: Record<string, unknown> | undefined;
      const base = {
        week_number: 3,
        source_cycle_week: 1,
        new_source_cycle_week: 1,
        cycle_iteration: 1,
        cycle_length: 3,
        repeat: true,
        periodization_enabled: true,
      };
      const workout = {
        id: 3,
        day_number: 1,
        title: 'Силовая',
        scheduled_date: '2030-01-10',
        status: 'planned',
        changeable: true,
        week_type: 'heavy',
        new_week_type: 'heavy',
        exercises: [exercise],
        new_exercises: [exercise],
      };
      await page.route('**/api/v1/programs/assigned/77/cycle/revision/preview', async (route) => {
        const body = route.request().postDataJSON();
        const workouts =
          body.copy_day_number !== undefined
            ? [
                workout,
                { ...workout, id: null, day_number: 2, title: 'Силовая · копия', added: true },
              ]
            : [workout];
        await route.fulfill({
          json: { weeks: [{ ...base, workouts }], total_weeks: 1, offset: 0 },
        });
      });
      await page.route('**/api/v1/programs/assigned/77/cycle/structure/preview', async (route) => {
        const body = route.request().postDataJSON();
        await route.fulfill({
          json: {
            weeks: [
              {
                ...base,
                workouts: [
                  {
                    ...workout,
                    structure_changed: true,
                    new_exercises: [
                      exercise,
                      {
                        ...exercise,
                        source_template_exercise_id: null,
                        source_assignment_slot_id: body.assignment_slot_id,
                        exercise_id: 12,
                      },
                    ],
                  },
                ],
              },
            ],
            total_weeks: 1,
            offset: 0,
          },
        });
      });
      await page.route('**/api/v1/programs/assigned/77/cycle/duration/preview', (route) =>
        route.fulfill({
          json: { weeks: [{ ...base, workouts: [workout] }], total_weeks: 1, offset: 0 },
        }),
      );
      await page.route('**/api/v1/programs/assigned/77/cycle', async (route) => {
        saved = route.request().postDataJSON();
        await route.fulfill({ json: { current_revision_number: 5 } });
      });
      await page.goto('/app?section=programs&view=manage&panel=operations');
      await page.getByText('Периодизация и будущие недели').click();
      const panel = page.getByRole('region', { name: 'Периодизация назначения' });
      const capture = async (name: string) => {
        if (process.env.ISSUE_920_CAPTURE === '1')
          await panel.screenshot({
            path: `../docs/ux/issue-920-after/v2/${info.project.name}-${theme}-${width}-${name}.png`,
            animations: 'disabled',
          });
      };
      await panel.getByRole('combobox', { name: 'Что изменить' }).selectOption('cycle');
      await panel.getByRole('spinbutton', { name: 'Исходных недель в новом цикле' }).fill('4');
      await capture('cycle');
      await panel.getByRole('button', { name: 'Проверить изменения' }).click();
      await expect(panel.getByText(/исходная 1 → новая 1/)).toBeVisible();
      await capture('cycle-preview');
      await panel.getByRole('button', { name: 'Вернуться', exact: true }).click();
      await panel.getByRole('combobox', { name: 'Что изменить' }).selectOption('duration');
      await panel.getByRole('spinbutton', { name: 'Всего недель' }).fill('20');
      await capture('duration');
      await panel.getByRole('button', { name: 'Проверить изменения' }).click();
      await expect(panel.getByText(/Проверяемых недель/)).toBeVisible();
      await capture('duration-preview');
      await panel.getByRole('button', { name: 'Вернуться', exact: true }).click();
      await panel.getByRole('combobox', { name: 'Что изменить' }).selectOption('exercise');
      await panel.getByRole('combobox', { name: 'Упражнение' }).selectOption('1:12');
      await panel.getByRole('combobox', { name: 'Заменить на' }).selectOption('12');
      await capture('replacement');
      await panel.getByRole('button', { name: 'Настроить предписание подходов' }).click();
      await capture('prescription');
      await panel.getByRole('radio', { name: /Выбрать недели/ }).check();
      await panel.getByRole('checkbox', { name: 'Неделя 3', exact: true }).check();
      await panel.getByRole('checkbox', { name: 'Неделя 5', exact: true }).check();
      await capture('scope');
      await panel.getByRole('combobox', { name: 'Что изменить' }).selectOption('structure');
      await panel.getByRole('button', { name: 'Добавить упражнение' }).click();
      await panel.getByRole('combobox', { name: 'Новое упражнение' }).selectOption('12');
      await capture('structure');
      await panel.getByRole('button', { name: 'Проверить изменения' }).click();
      await expect(panel.getByText(/Станет:/)).toBeVisible();
      await capture('structure-preview');
      await panel.getByRole('button', { name: 'Вернуться', exact: true }).click();
      await panel.getByRole('combobox', { name: 'Что изменить' }).selectOption('days');
      await panel.getByRole('button', { name: 'Добавить тренировочный день' }).click();
      await panel.getByRole('radio', { name: /Выбрать недели/ }).check();
      await panel.getByRole('checkbox', { name: 'Неделя 3', exact: true }).check();
      await panel.getByRole('checkbox', { name: 'Неделя 5', exact: true }).check();
      await expectNoHorizontalOverflow(page);
      await capture('days-scope');
      await panel.getByRole('button', { name: 'Проверить изменения' }).click();
      await expect(panel.getByText(/будет добавлена/)).toBeVisible();
      await capture('days-preview');
      await panel.getByRole('button', { name: 'Применить изменения' }).click();
      await expect
        .poll(() => saved)
        .toMatchObject({ occurrence_weeks: [3, 5], effective_from_week: 3, copy_day_number: 1 });
    });

    test(`начатый подход ${theme} ${width}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, workoutStatus: 'in_progress' });
      await page.goto('/app');
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
      await page.getByRole('button', { name: 'Изменить план подхода' }).click();
      const editor = page.getByRole('region', { name: 'Изменение плана подхода' });
      await page.getByLabel('Плановый вес, кг').fill('37,5');
      await page.getByLabel('План повторов').fill('8');
      if (process.env.ISSUE_920_CAPTURE === '1')
        await editor.screenshot({
          path: `../docs/ux/issue-920-after/v2/${info.project.name}-${theme}-${width}-live.png`,
          animations: 'disabled',
        });
      await page.getByRole('button', { name: 'Проверить изменение' }).click();
      await expect(page.getByText('37.5 кг · 8 повторов')).toBeVisible();
      if (process.env.ISSUE_920_CAPTURE === '1')
        await editor.screenshot({
          path: `../docs/ux/issue-920-after/v2/${info.project.name}-${theme}-${width}-live-preview.png`,
          animations: 'disabled',
        });
      await expectNoHorizontalOverflow(page);
    });
  }
}
