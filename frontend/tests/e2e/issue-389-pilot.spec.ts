import { expect, test } from '@playwright/test';
import { installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

const repdbLicenseUrl =
  'https://github.com/RepDB/exercise-dataset/blob/9ed9357f09c7566ea0256c57ebd6374ebb8b575e/LICENSE-DATA.md';

const exercise = {
  id: 12002,
  edit_target_id: 12002,
  title: 'Жим лежа',
  slug: 'bench-press',
  metric_type: 'strength',
  primary_muscle: 'Грудь',
  equipment: 'Штанга',
  primary_muscle_ids: ['chest'],
  secondary_muscle_ids: ['triceps'],
  equipment_ids: ['barbell'],
  aliases: ['жим штанги лежа'],
  movement_pattern: 'push',
  machine_variant_tags: [],
  execution_variant_tags: ['bilateral'],
  alternatives: [],
  difficulty_level: 'beginner',
  is_custom: false,
  is_personalized: false,
  has_guide: true,
  source_exercise_id: null,
};

const guide = {
  technique_steps: ['Сведите лопатки.', 'Опускайте штангу под контролем.'],
  breathing: 'Вдох при опускании, выдох после тяжёлой части подъёма.',
  common_mistakes: ['Отрыв таза от скамьи'],
  muscles: [
    {
      identifier: 'chest',
      name: 'Грудь',
      role_id: 'primary',
      role: 'Основная',
      function: 'Перемещает руку вперёд в фазе усилия.',
    },
  ],
  equipment: [{ identifier: 'barbell', name: 'Штанга' }],
  safety_notes: ['Используйте страховку при тяжёлых подходах.'],
  alternatives: [],
  media: [
    {
      type: 'image',
      url: '/static/exercise-guides/pilot/bench-press/bench-press-start.webp',
      poster: '/static/exercise-guides/pilot/bench-press/bench-press-start.webp',
      phase_id: 'eccentric_end',
      phase: 'Начало',
      alt: 'Жим лежа: начало',
      source_name: 'Exercise data by RepDB (repdb.co)',
      source_url: 'https://github.com/RepDB/exercise-dataset',
      source_license: 'RepDB Free Tier License v1.0',
      source_license_url: repdbLicenseUrl,
      width: 512,
      height: 512,
      byte_size: 21_554,
      sort_order: 0,
      sources: [
        {
          url: '/static/exercise-guides/pilot/bench-press/bench-press-start.webp',
          mime_type: 'image/webp',
          width: 512,
          height: 512,
          byte_size: 21_554,
        },
      ],
    },
    {
      type: 'image',
      url: '/static/exercise-guides/pilot/bench-press/bench-press-peak.webp',
      poster: '/static/exercise-guides/pilot/bench-press/bench-press-peak.webp',
      phase_id: 'concentric_end',
      phase: 'Пик',
      alt: 'Жим лежа: пик',
      source_name: 'Exercise data by RepDB (repdb.co)',
      source_url: 'https://github.com/RepDB/exercise-dataset',
      source_license: 'RepDB Free Tier License v1.0',
      source_license_url: repdbLicenseUrl,
      width: 512,
      height: 512,
      byte_size: 23_314,
      sort_order: 1,
      sources: [
        {
          url: '/static/exercise-guides/pilot/bench-press/bench-press-peak.webp',
          mime_type: 'image/webp',
          width: 512,
          height: 512,
          byte_size: 23_314,
        },
      ],
    },
  ],
  images: [
    {
      phase: 'Начало',
      url: '/static/exercise-guides/pilot/bench-press/bench-press-start.webp',
      alt: 'Жим лежа: начало',
    },
    {
      phase: 'Пик',
      url: '/static/exercise-guides/pilot/bench-press/bench-press-peak.webp',
      alt: 'Жим лежа: пик',
    },
  ],
  media_reference: 'exercise-guides:bench-press',
  source_name: 'Exercise data by RepDB (repdb.co)',
  source_url: 'https://github.com/RepDB/exercise-dataset',
  source_license: 'RepDB Free Tier License v1.0',
  source_license_url: repdbLicenseUrl,
};

test('catalog presents local phased media', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegramHarness(page, { platform: 'android' });
  await installPlatformApi(page, { browserSession: true });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: [exercise] }));
  await page.route('**/api/v1/programs/exercises/12002', (route) =>
    route.fulfill({ json: { ...exercise, guide } }),
  );
  await page.route('**/static/exercise-guides/pilot/bench-press/*', async (route) => {
    const fileName = new URL(route.request().url()).pathname.split('/').at(-1);
    return route.fulfill({
      path: `../backend/assets/exercise-guides/pilot/bench-press/${fileName}`,
      contentType: 'image/webp',
    });
  });

  await page.goto('/app?section=catalog');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('жим штанги лежа');
  const row = page.locator('.exercise-catalog-item');
  await expect(row).toHaveCount(1);
  await row.getByRole('button', { name: /Техника и детали/ }).click();

  const dialog = page.getByRole('dialog', { name: 'Жим лежа' });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('video')).toHaveCount(0);
  await expect(dialog.getByRole('group', { name: 'Представление фаз' })).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: 'Переключать' })).toHaveCount(0);
  await expect(dialog.locator('.exercise-guide-image')).toHaveCount(2);
  await expect(
    dialog.getByRole('link', { name: 'Exercise data by RepDB (repdb.co)' }),
  ).toHaveAttribute('href', 'https://github.com/RepDB/exercise-dataset');
  await expect(dialog.getByRole('link', { name: 'RepDB Free Tier License v1.0' })).toHaveAttribute(
    'href',
    repdbLicenseUrl,
  );
  await expect(
    page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).resolves.toBe(true);
  await dialog.screenshot({
    path: '../.artifacts/tasks/389/evidence/screenshots/catalog-detail-mobile-390x844-phases.png',
  });
  await expect(dialog.getByAltText('Жим лежа: пик')).toBeVisible();
});
