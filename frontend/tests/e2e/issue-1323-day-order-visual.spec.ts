import { mkdir } from 'node:fs/promises';
import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

const dayTitles = ['Толкай A', 'Толкай B', 'Тяни A', 'Тяни B', 'Ноги A', 'Ноги B'];

test('#1323 approved All Days sorting - real browser visual evidence', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
  await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
  const program = {
    id: 700,
    slug: 'visual-issue-1323',
    title: 'Программа на шесть дней',
    goal: 'recomposition',
    level: 'intermediate',
    split_type: 'full_body',
    owner_user_id: 7,
    owner_telegram_user_id: 7007,
    owner_full_name: 'Тестовый спортсмен',
    created_by_user_id: 7,
    is_public: false,
    is_example: false,
    can_edit: true,
    is_assigned_to_current_user: true,
    is_active_for_current_user: true,
    assigned_by_user_id: null,
    assigned_by_full_name: null,
    assigned_program_id: 77,
    assigned_program_status: 'active',
    assigned_program_start_date: '2026-09-01',
    assigned_program_duration_weeks: 10,
    current_revision_number: 4,
    days: dayTitles.map((title, index) => ({
      id: index + 1,
      day_number: index + 1,
      title,
      exercises: [
        {
          exercise_id: 11,
          sort_order: 1,
          prescribed_sets: 3,
          prescribed_reps: '8-12',
          rest_seconds: 90,
          notes: '',
          superset_group: null,
          superset_order: null,
        },
      ],
    })),
  };
  await page.route('**/api/v1/programs/templates/mine', (route) =>
    route.fulfill({ json: [program] }),
  );
  await page.route('**/api/v1/programs/exercises', (route) =>
    route.fulfill({
      json: [
        {
          id: 11,
          title: 'Жим гантелей лёжа',
          slug: 'dumbbell-bench-press',
          metric_type: 'strength',
          primary_muscle: 'Грудь',
          equipment: 'Гантели',
          primary_muscle_ids: ['chest'],
          secondary_muscle_ids: [],
          equipment_ids: ['dumbbell'],
          alternatives: [],
          difficulty_level: 'beginner',
          is_custom: false,
          is_personalized: false,
          has_guide: false,
        },
      ],
    }),
  );

  await page.goto('/app?section=programs&view=manage&start=templates');
  await page.getByRole('button', { name: 'Редактировать шаблон', exact: true }).click();
  const editor = page.locator('.program-editor-modal');
  await expect(editor.getByRole('button', { name: 'Все дни' })).toBeVisible();
  await expect(editor.getByRole('button', { name: 'Переместить день выше' })).toHaveCount(0);
  await expect(editor.getByRole('button', { name: 'Переместить день ниже' })).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);

  const evidenceDirectory = `../.artifacts/runtime/tests/playwright/redesign-visual-issue-1323-${testInfo.parallelIndex}`;
  await mkdir(evidenceDirectory, { recursive: true });
  await page.screenshot({
    path: `${evidenceDirectory}/1323-mobile-day-dark.png`,
    animations: 'disabled',
  });

  await editor.getByRole('button', { name: 'Все дни' }).click();
  const dialog = page.getByRole('dialog', { name: 'Все дни программы' });
  await dialog.getByRole('button', { name: 'Изменить порядок', exact: true }).click();
  await expect(dialog.locator('.copy-editor__day-sort-row')).toHaveCount(6);
  await expect(dialog.getByRole('button', { name: 'Переместить день 1 раньше' })).toBeDisabled();
  await expect(dialog.getByRole('button', { name: 'Переместить день 6 позже' })).toBeDisabled();
  await page.screenshot({
    path: `${evidenceDirectory}/1323-mobile-all-days-sort-dark.png`,
    animations: 'disabled',
  });
});
