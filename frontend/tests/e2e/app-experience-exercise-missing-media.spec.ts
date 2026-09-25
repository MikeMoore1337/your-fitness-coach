import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

const gymThumbnail = '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg';

const gymExercise = {
  id: 39301,
  edit_target_id: 39301,
  title: 'Жим лёжа',
  slug: 'bench-press',
  metric_type: 'strength',
  primary_muscle: 'Грудь',
  equipment: 'Штанга',
  primary_muscle_ids: ['chest'],
  secondary_muscle_ids: ['triceps'],
  equipment_ids: ['barbell'],
  aliases: [],
  movement_pattern: 'push',
  machine_variant_tags: [],
  execution_variant_tags: ['bilateral'],
  alternatives: [],
  difficulty_level: 'beginner',
  is_custom: false,
  is_personalized: false,
  has_guide: true,
  source_exercise_id: null,
  media_state: 'approved_animated',
  media_thumbnail_url: gymThumbnail,
  media_animation_url: '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif',
};

const missingExercise = {
  ...gymExercise,
  id: 39302,
  edit_target_id: 39302,
  title: 'Бёрд-дог',
  slug: 'bird-dog',
  media_state: 'blocked',
  media_thumbnail_url: null,
  media_animation_url: null,
};

test('catalog missing-media thumbnail keeps square geometry and preserves approved GymVisual media', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await installPlatformApi(page, { browserSession: true });
  await page.route('**/api/v1/programs/exercises', (route) =>
    route.fulfill({ json: [gymExercise, missingExercise] }),
  );
  await page.route(`**${gymThumbnail}`, (route) =>
    route.fulfill({
      path: '../backend/assets/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg',
      contentType: 'image/jpeg',
    }),
  );

  await page.goto('/app?section=catalog');
  await expect(page.locator('.exercise-catalog-item')).toHaveCount(2);

  for (const theme of ['light', 'dark'] as const) {
    if (theme === 'dark') {
      await page.evaluate(() => {
        localStorage.setItem('app-theme', 'dark');
        window.dispatchEvent(new CustomEvent('yfc-theme-preference-change'));
      });
    }
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);

    for (const width of [320, 360, 390, 1280]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
      const approved = page.locator('.exercise-catalog-item').filter({ hasText: 'Жим лёжа' });
      const missing = page.locator('.exercise-catalog-item').filter({ hasText: 'Бёрд-дог' });
      const approvedImage = approved.locator('.exercise-catalog-item__thumb');
      const placeholder = missing.locator('.exercise-catalog-item__thumb');

      await expect(approvedImage).toHaveAttribute('src', gymThumbnail);
      await expect(approvedImage).toHaveAttribute('data-media-mode', 'static-poster');
      await expect(placeholder).toHaveAttribute(
        'aria-label',
        'Бёрд-дог: изображение упражнения. Изображение пока недоступно',
      );
      await expect(placeholder).toContainText('Нет фото');

      const [placeholderGeometry, approvedGeometry] = await Promise.all([
        placeholder.evaluate((element) => {
          const box = element.getBoundingClientRect();
          const label = element.querySelector('span')?.getBoundingClientRect();
          return {
            width: box.width,
            height: box.height,
            labelInside: Boolean(
              label &&
              label.left >= box.left &&
              label.right <= box.right &&
              label.top >= box.top &&
              label.bottom <= box.bottom,
            ),
            fontSize: Number.parseFloat(getComputedStyle(element).fontSize),
          };
        }),
        approvedImage.evaluate((element) => {
          const box = element.getBoundingClientRect();
          return { width: box.width, height: box.height };
        }),
      ]);
      expect(placeholderGeometry.width).toBe(approvedGeometry.width);
      expect(placeholderGeometry.height).toBe(approvedGeometry.height);
      expect(placeholderGeometry.width).toBe(placeholderGeometry.height);
      expect(placeholderGeometry.labelInside).toBe(true);
      expect(placeholderGeometry.fontSize).toBeGreaterThanOrEqual(11);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
    }
  }
});
