import { expect, test } from '@playwright/test';
import {
  MOBILE_CONTEXTS,
  TelegramHarness,
  expectNoHorizontalOverflow,
  installTelegramHarness,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ hasTouch: true });

const thumbnailUrl = '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg';
const animationUrl = '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif';

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
  media_state: 'approved_animated',
  media_thumbnail_url: thumbnailUrl,
  media_animation_url: animationUrl,
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
      type: 'animation',
      url: animationUrl,
      poster: thumbnailUrl,
      phase_id: 'movement',
      phase: 'Движение',
      alt: 'Жим лежа: движение',
      source_name: 'Gym visual',
      source_url: 'https://github.com/hasaneyldrm/exercises-dataset',
      source_license: 'Owner-purchased GymVisual license',
      source_license_url: 'https://gymvisual.com/',
      asset_id: 'gymvisual:0025:EIeI8Vf',
      asset_version: 'gymvisual-7455efae',
      variant_key: 'movement',
      width: 180,
      height: 180,
      byte_size: 12000,
      sort_order: 0,
      sources: [
        {
          url: animationUrl,
          mime_type: 'image/gif',
          width: 180,
          height: 180,
          byte_size: 12000,
        },
        {
          url: thumbnailUrl,
          mime_type: 'image/jpeg',
          width: 180,
          height: 180,
          byte_size: 9000,
        },
      ],
    },
  ],
  images: [{ phase: 'Движение', url: animationUrl, alt: 'Жим лежа: движение' }],
  media_reference: 'exercise-guides:bench-press',
  source_name: 'Gym visual',
  source_url: 'https://github.com/hasaneyldrm/exercises-dataset',
  source_license: 'Owner-purchased GymVisual license',
  source_license_url: 'https://gymvisual.com/',
};

const blockedExercise = {
  ...exercise,
  id: 12003,
  edit_target_id: 12003,
  title: 'Плавание',
  slug: 'swimming',
  media_state: 'blocked',
  media_thumbnail_url: null,
  media_animation_url: null,
};

const blockedGuide = {
  ...guide,
  media: [],
  images: [],
  source_name: 'Your Fitness Coach',
  source_url: '/',
  source_license: 'Публикация изображения заблокирована до проверки',
  source_license_url: null,
};

test('catalog presents local animation-first media on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegramHarness(page, { platform: 'android' });
  await installPlatformApi(page, { browserSession: true });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: [exercise] }));
  await page.route('**/api/v1/programs/exercises/12002', (route) =>
    route.fulfill({ json: { ...exercise, guide } }),
  );
  await page.route(`**${thumbnailUrl}`, (route) =>
    route.fulfill({
      path: '../backend/assets/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg',
      contentType: 'image/jpeg',
    }),
  );
  await page.route(`**${animationUrl}`, (route) =>
    route.fulfill({
      path: '../backend/assets/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif',
      contentType: 'image/gif',
    }),
  );

  await page.goto('/app?section=catalog');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('жим штанги лежа');
  const row = page.locator('.exercise-catalog-item');
  await expect(row).toHaveCount(1);
  await expect(row.locator('img[data-media-mode="static-poster"]')).toHaveCount(1);
  await row.getByRole('button', { name: /Техника и детали/ }).click();

  const dialog = page.getByRole('dialog', { name: 'Жим лежа' });
  await expect(dialog).toBeVisible();
  const media = dialog.locator('.exercise-guide-image img');
  await expect(media).toHaveCount(1);
  await expect(media).toHaveAttribute('src', animationUrl);
  await expect(media).toHaveAttribute('data-media-mode', 'animation');
  await expect
    .poll(() => media.evaluate((image) => (image as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
  const lightGeometry = await dialog.evaluate((element) => {
    const card = element.querySelector('.exercise-guide-card')?.getBoundingClientRect();
    const media = element.querySelector('.exercise-guide-image')?.getBoundingClientRect();
    const frame = element.querySelector('.exercise-guide-image__frame')?.getBoundingClientRect();
    return {
      cardWidth: card?.width ?? 0,
      mediaWidth: media?.width ?? 0,
      frameWidth: frame?.width ?? 0,
      frameHeight: frame?.height ?? 0,
    };
  });
  expect(lightGeometry.mediaWidth).toBeCloseTo(lightGeometry.cardWidth, 0);
  expect(lightGeometry.frameHeight).toBeCloseTo(lightGeometry.frameWidth, 0);
  await expect(dialog.getByRole('link', { name: 'Gym visual' })).toHaveAttribute(
    'href',
    'https://github.com/hasaneyldrm/exercises-dataset',
  );
  await expect(
    dialog.getByRole('link', { name: 'Owner-purchased GymVisual license' }),
  ).toHaveAttribute('href', 'https://gymvisual.com/');
  await expect(
    page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).resolves.toBe(true);
  await dialog.screenshot({
    path: '../.artifacts/tasks/390/evidence/screenshots/catalog-detail-mobile-390x844-animation-full-width.png',
  });
  await media.screenshot({
    path: '../.artifacts/tasks/390/evidence/screenshots/catalog-animation-frame-1-full-width.png',
  });
  await media.screenshot({
    path: '../.artifacts/tasks/390/evidence/screenshots/catalog-animation-frame-2-full-width.png',
  });

  for (const viewport of [MOBILE_CONTEXTS.compact, MOBILE_CONTEXTS.large]) {
    await page.setViewportSize(viewport);
    await page.goto('/app?section=catalog');
    await page.getByRole('searchbox', { name: 'Поиск' }).fill('жим штанги лежа');
    const viewportRow = page.locator('.exercise-catalog-item');
    await expect(viewportRow).toHaveCount(1);
    await viewportRow.getByRole('button', { name: /Техника и детали/ }).click();
    const viewportDialog = page.getByRole('dialog', { name: 'Жим лежа' });
    await expect(viewportDialog).toBeVisible();
    const viewportGeometry = await viewportDialog.evaluate((element) => {
      const card = element.querySelector('.exercise-guide-card')?.getBoundingClientRect();
      const media = element.querySelector('.exercise-guide-image')?.getBoundingClientRect();
      const frame = element.querySelector('.exercise-guide-image__frame')?.getBoundingClientRect();
      return {
        cardWidth: card?.width ?? 0,
        mediaWidth: media?.width ?? 0,
        frameWidth: frame?.width ?? 0,
        frameHeight: frame?.height ?? 0,
      };
    });
    expect(viewportGeometry.mediaWidth).toBeCloseTo(viewportGeometry.cardWidth, 0);
    expect(viewportGeometry.frameHeight).toBeCloseTo(viewportGeometry.frameWidth, 0);
    await expectNoHorizontalOverflow(page);
  }
});

test('catalog keeps blocked media explicit and reduced motion uses the poster', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await installTelegramHarness(page, { platform: 'android', colorScheme: 'dark' });
  const telegramHarness = new TelegramHarness(page);
  await installPlatformApi(page, { browserSession: true });
  await page.route('**/api/v1/programs/exercises', (route) =>
    route.fulfill({ json: [exercise, blockedExercise] }),
  );
  await page.route('**/api/v1/programs/exercises/12002', (route) =>
    route.fulfill({ json: { ...exercise, guide } }),
  );
  await page.route('**/api/v1/programs/exercises/12003', (route) =>
    route.fulfill({ json: { ...blockedExercise, guide: blockedGuide } }),
  );
  await page.route(`**${thumbnailUrl}`, (route) =>
    route.fulfill({
      path: '../backend/assets/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg',
      contentType: 'image/jpeg',
    }),
  );
  await page.route(`**${animationUrl}`, (route) =>
    route.fulfill({
      path: '../backend/assets/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif',
      contentType: 'image/gif',
    }),
  );

  await page.goto('/app?section=catalog');
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  const rows = page.locator('.exercise-catalog-item');
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0).locator('img[data-media-mode="static-poster"]')).toHaveCount(1);
  const missingMedia = rows.nth(1).getByRole('img');
  await expect(missingMedia).toHaveText('Нет фото');
  await expect(missingMedia).toHaveAccessibleName(/Изображение пока недоступно/);
  await rows.nth(1).scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/tasks/390/evidence/screenshots/catalog-mobile-mixed-and-blocked-390x844.png',
  });

  await page.getByRole('searchbox', { name: 'Поиск' }).fill('жим');
  await rows
    .nth(0)
    .getByRole('button', { name: /Техника и детали/ })
    .click();
  const approvedDialog = page.getByRole('dialog', { name: 'Жим лежа' });
  await expect(approvedDialog).toBeVisible();
  await expect(approvedDialog.locator('.exercise-guide-image img')).toHaveAttribute(
    'src',
    thumbnailUrl,
  );
  await expect(approvedDialog.locator('.exercise-guide-image img')).toHaveAttribute(
    'data-media-mode',
    'static-poster',
  );
  const reducedMotionGeometry = await approvedDialog.evaluate((element) => {
    const card = element.querySelector('.exercise-guide-card')?.getBoundingClientRect();
    const media = element.querySelector('.exercise-guide-image')?.getBoundingClientRect();
    const frame = element.querySelector('.exercise-guide-image__frame')?.getBoundingClientRect();
    return {
      cardWidth: card?.width ?? 0,
      mediaWidth: media?.width ?? 0,
      frameWidth: frame?.width ?? 0,
      frameHeight: frame?.height ?? 0,
    };
  });
  expect(reducedMotionGeometry.mediaWidth).toBeCloseTo(reducedMotionGeometry.cardWidth, 0);
  expect(reducedMotionGeometry.frameHeight).toBeCloseTo(reducedMotionGeometry.frameWidth, 0);
  await approvedDialog.screenshot({
    path: '../.artifacts/tasks/390/evidence/screenshots/catalog-detail-mobile-dark-reduced-poster-full-width.png',
  });
  await approvedDialog.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();

  await page.getByRole('searchbox', { name: 'Поиск' }).fill('плав');
  await expect(rows).toHaveCount(1);
  await rows.getByRole('button', { name: /Техника и детали/ }).click();
  const blockedDialog = page.getByRole('dialog', { name: 'Плавание' });
  await expect(blockedDialog).toBeVisible();
  await expect(blockedDialog.locator('.exercise-guide-media-empty')).toContainText(
    'Изображение пока недоступно',
  );
  const blockedGeometry = await blockedDialog
    .locator('.exercise-guide-media-empty')
    .evaluate((element) => {
      const card = element.closest('.exercise-guide-card')?.getBoundingClientRect();
      const media = element.getBoundingClientRect();
      return {
        cardWidth: card?.width ?? 0,
        mediaWidth: media.width,
        mediaHeight: Math.round(media.height),
      };
    });
  expect(blockedGeometry.mediaWidth).toBeCloseTo(blockedGeometry.cardWidth, 0);
  expect(blockedGeometry.mediaHeight).toBeGreaterThanOrEqual(150);
  expect(blockedGeometry.mediaHeight).toBeLessThanOrEqual(180);
  expect(blockedGeometry.mediaHeight).toBeLessThan(blockedGeometry.mediaWidth);
  await expectNoHorizontalOverflow(page);
  await blockedDialog.screenshot({
    animations: 'disabled',
    path: '../.artifacts/tasks/390/evidence/screenshots/catalog-blocked-detail-mobile-dark-390x844-compact.png',
  });

  await blockedDialog.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'no-preference' });
  await telegramHarness.setTheme('light');
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('плав');
  await expect(rows).toHaveCount(1);
  await rows.getByRole('button', { name: /Техника и детали/ }).click();
  const lightBlockedDialog = page.getByRole('dialog', { name: 'Плавание' });
  await expect(lightBlockedDialog).toBeVisible();
  await lightBlockedDialog.screenshot({
    animations: 'disabled',
    path: '../.artifacts/tasks/390/evidence/screenshots/catalog-blocked-detail-mobile-light-390x844-compact.png',
  });
  await lightBlockedDialog.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();

  for (const viewport of [
    { width: 320, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/app?section=catalog');
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
    await page.getByRole('searchbox', { name: 'Поиск' }).fill('плав');
    const viewportRows = page.locator('.exercise-catalog-item');
    await expect(viewportRows).toHaveCount(1);
    await viewportRows.getByRole('button', { name: /Техника и детали/ }).click();
    const viewportDialog = page.getByRole('dialog', { name: 'Плавание' });
    await expect(viewportDialog).toBeVisible();
    await expect(viewportDialog.locator('.exercise-guide-media-empty')).toContainText(
      'Изображение пока недоступно',
    );
    const viewportGeometry = await viewportDialog
      .locator('.exercise-guide-media-empty')
      .evaluate((element) => {
        const card = element.closest('.exercise-guide-card')?.getBoundingClientRect();
        const media = element.getBoundingClientRect();
        return {
          cardWidth: card?.width ?? 0,
          mediaWidth: media.width,
          mediaHeight: Math.round(media.height),
        };
      });
    expect(viewportGeometry.mediaWidth).toBeCloseTo(viewportGeometry.cardWidth, 0);
    expect(viewportGeometry.mediaHeight).toBeGreaterThanOrEqual(150);
    expect(viewportGeometry.mediaHeight).toBeLessThanOrEqual(180);
    expect(viewportGeometry.mediaHeight).toBeLessThan(viewportGeometry.mediaWidth);
    await expectNoHorizontalOverflow(page);
    await viewportDialog.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();
  }
});
