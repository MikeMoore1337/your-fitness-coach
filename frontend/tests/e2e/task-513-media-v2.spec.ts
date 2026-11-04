import { mkdir } from 'node:fs/promises';
import { expect, test, type Locator, type Page } from '@playwright/test';
import { resolve } from 'node:path';
import { installPlatformApi } from './fixtures/platform-api';
import { TelegramHarness, installTelegramHarness } from './fixtures/mobile-tma';

test.use({ serviceWorkers: 'block' });

const thumbnailUrl = '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg';
const animationUrl = '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif';
const widePosterUrl = '/static/exercise-guides/exercises-media/incline-bench-press/poster-1280.jpg';
const wideVideoUrl =
  '/static/exercise-guides/exercises-media/videos/incline-bench-press-720p-h264.mp4';
const screenshotRoot =
  process.env.YFC_TASK_513_SCREENSHOT_DIR ??
  resolve(process.cwd(), '..', '.artifacts', 'tasks', '513', 'evidence', 'screenshots');

const screenshotPath = (name: string) => resolve(screenshotRoot, name);

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

const wideExercise = {
  ...exercise,
  id: 12003,
  edit_target_id: 12003,
  title: 'Жим штанги на наклонной скамье',
  slug: 'incline-bench-press',
  media_state: 'approved_static',
  media_thumbnail_url: widePosterUrl,
  media_animation_url: null,
};

const wideGuide = {
  ...guide,
  media: [
    {
      ...guide.media[0]!,
      type: 'image',
      url: widePosterUrl,
      poster: widePosterUrl,
      phase: 'Движение',
      alt: 'Жим штанги на наклонной скамье: движение',
      width: 1280,
      height: 720,
      byte_size: 53_251,
      sources: [
        {
          url: widePosterUrl,
          mime_type: 'image/jpeg',
          width: 1280,
          height: 720,
          byte_size: 53_251,
        },
      ],
      video_sources: [
        {
          url: wideVideoUrl,
          mime_type: 'video/mp4',
          width: 1280,
          height: 720,
          byte_size: 101_018,
        },
      ],
    },
  ],
  images: [
    { phase: 'Движение', url: widePosterUrl, alt: 'Жим штанги на наклонной скамье: движение' },
  ],
};

async function installMediaRoutes(page: Page) {
  let animationAvailable = true;
  await page.route(
    /\/static\/exercise-guides\/gymvisual\/bench-press-0025-EIeI8Vf\.jpg(?:\?.*)?$/,
    (route) =>
      route.fulfill({
        path: '../backend/assets/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg',
        contentType: 'image/jpeg',
      }),
  );
  await page.route(
    /\/static\/exercise-guides\/gymvisual\/bench-press-0025-EIeI8Vf\.gif(?:\?.*)?$/,
    (route) =>
      animationAvailable
        ? route.fulfill({
            path: '../backend/assets/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif',
            contentType: 'image/gif',
          })
        : route.abort('failed'),
  );
  return {
    setAnimationAvailable(value: boolean) {
      animationAvailable = value;
    },
  };
}

async function installCatalogRoutes(page: Page) {
  await page.route(/\/api\/v1\/programs\/exercises(?:\?.*)?$/, (route) =>
    route.fulfill({ json: [exercise] }),
  );
  await page.route(/\/api\/v1\/programs\/exercises\/12002(?:\?.*)?$/, (route) =>
    route.fulfill({ json: { ...exercise, guide } }),
  );
}

async function installWideMediaRoutes(page: Page) {
  await page.route(
    /\/static\/exercise-guides\/exercises-media\/incline-bench-press\/poster-1280\.jpg(?:\?.*)?$/,
    (route) =>
      route.fulfill({
        path: '../backend/assets/exercise-guides/exercises-media/incline-bench-press/poster-1280.jpg',
        contentType: 'image/jpeg',
      }),
  );
  await page.route(
    '**/static/exercise-guides/exercises-media/videos/incline-bench-press-720p-h264.mp4*',
    (route) =>
      route.fulfill({
        path: '../backend/assets/exercise-guides/exercises-media/videos/incline-bench-press-720p-h264.mp4',
        contentType: 'video/mp4',
      }),
  );
}

async function installWideCatalogRoutes(page: Page) {
  await page.route(/\/api\/v1\/programs\/exercises(?:\?.*)?$/, (route) =>
    route.fulfill({ json: [wideExercise] }),
  );
  await page.route(/\/api\/v1\/programs\/exercises\/12003(?:\?.*)?$/, (route) =>
    route.fulfill({ json: { ...wideExercise, guide: wideGuide } }),
  );
}

async function installWideActiveWorkoutRoutes(page: Page, mediaKind: 'wide' | 'gif' = 'wide') {
  const media =
    mediaKind === 'gif'
      ? {
          state: 'approved_animated',
          thumbnailUrl: widePosterUrl,
          thumbnailSources: [
            {
              url: widePosterUrl,
              mime_type: 'image/jpeg',
              width: 1280,
              height: 720,
              byte_size: 53_251,
            },
          ],
          animationUrl,
          videoSources: [],
          preferredMode: 'animation',
        }
      : {
          state: 'approved_static',
          thumbnailUrl: widePosterUrl,
          thumbnailSources: [
            {
              url: widePosterUrl,
              mime_type: 'image/jpeg',
              width: 1280,
              height: 720,
              byte_size: 53_251,
            },
          ],
          animationUrl: null,
          videoSources: [
            {
              url: wideVideoUrl,
              mime_type: 'video/mp4',
              width: 1280,
              height: 720,
              byte_size: 101_018,
            },
          ],
          preferredMode: 'static',
        };
  await page.route(/\/api\/v1\/workouts\/today(?:\?.*)?$/, (route) =>
    route.fulfill({
      json: {
        id: 1186,
        scheduled_date: '2026-10-01',
        title: 'Силовая база',
        status: 'in_progress',
        day_number: 1,
        week_number: 1,
        started_at: '2026-10-01T08:00:00Z',
        completed_at: null,
        exercises: [
          {
            id: 11861,
            exercise_id: 1186,
            exercise_title: 'Жим штанги на наклонной скамье',
            metric_type: 'strength',
            sort_order: 1,
            prescribed_sets: 1,
            prescribed_reps: '8–10',
            rest_seconds: 90,
            notes: null,
            has_guide: false,
            media_state: media.state,
            media_thumbnail_url: media.thumbnailUrl,
            media_thumbnail_sources: media.thumbnailSources,
            media_animation_url: media.animationUrl,
            media_video_sources: media.videoSources,
            media_preferred_mode: media.preferredMode,
            sets: [
              {
                id: 11861,
                set_number: 1,
                actual_reps: null,
                actual_weight: null,
                rir: null,
                set_kind: 'working',
                reached_failure: false,
                is_completed: false,
                version: 1,
              },
            ],
          },
        ],
      },
    }),
  );
}

async function enterActiveWorkout(page: Page) {
  await page.goto('/app');
  const continueButton = page.getByRole('button', { name: 'Продолжить тренировку' });
  const clientEntry = page.getByRole('button', { name: 'Клиент' });
  await Promise.race([
    continueButton.waitFor({ state: 'visible', timeout: 10000 }),
    clientEntry.waitFor({ state: 'visible', timeout: 10000 }),
  ]);
  if (!(await continueButton.isVisible())) await clientEntry.click();
  await expect(continueButton).toBeVisible();
  await continueButton.click();
}

async function openCatalogDetail(page: Page) {
  await page.goto('/app?section=catalog');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('жим штанги лежа');
  const row = page.locator('.exercise-catalog-item');
  await expect(row).toHaveCount(1);
  await row.getByRole('button', { name: /Техника и детали/ }).click();
  const dialog = page.getByRole('dialog', { name: 'Жим лежа' });
  await expect(dialog).toBeVisible();
  return { dialog, media: dialog.locator('.exercise-guide-image img') };
}

async function openWideCatalogDetail(page: Page, colorScheme: 'light' | 'dark') {
  await page.goto('/app?section=catalog', { waitUntil: 'domcontentloaded' });
  await page.evaluate((theme) => localStorage.setItem('app-theme', theme), colorScheme);
  await page.reload({ waitUntil: 'domcontentloaded' });
  const search = page.getByRole('searchbox', { name: 'Поиск' });
  await expect(search).toBeVisible();
  await expect(search).toBeEditable();
  await search.fill('наклонной скамье');
  const row = page.locator('.exercise-catalog-item');
  await expect(row).toHaveCount(1);
  await row.getByRole('button', { name: /Техника и детали/ }).click();
  const dialog = page.getByRole('dialog', { name: 'Жим штанги на наклонной скамье' });
  await expect(dialog).toBeVisible();
  return dialog;
}

async function expectSquareMediaSurface(locator: Locator, label: string) {
  const geometry = await locator.evaluate((element) => {
    const surface = element.getBoundingClientRect();
    const media = element.querySelector<HTMLElement>('img, video');
    const mediaRect = media?.getBoundingClientRect();
    const style = getComputedStyle(element);
    return {
      surfaceWidth: surface.width,
      surfaceHeight: surface.height,
      mediaWidth: mediaRect?.width ?? 0,
      mediaHeight: mediaRect?.height ?? 0,
      objectFit: media ? getComputedStyle(media).objectFit : null,
      framePolicy: media?.dataset.mediaFrame ?? null,
      sourceRatio: media?.dataset.mediaSourceRatio ?? null,
      objectPosition: media ? getComputedStyle(media).objectPosition : null,
      border: style.border,
    };
  });
  expect(
    Math.abs(geometry.surfaceWidth - geometry.surfaceHeight),
    `${label}: square surface delta`,
  ).toBeLessThanOrEqual(1);
  expect(geometry.mediaWidth, `${label}: media must fill surface`).toBeGreaterThanOrEqual(
    geometry.surfaceWidth - 1,
  );
  expect(geometry.mediaHeight, `${label}: media must fill surface`).toBeGreaterThanOrEqual(
    geometry.surfaceHeight - 1,
  );
  expect(geometry.framePolicy, `${label}: source-aware filled framing`).toBe('filled-square');
  expect(geometry.objectFit, `${label}: wide source must fill the square`).toBe('cover');
  expect(geometry.sourceRatio, `${label}: source ratio is recorded`).toBe('1.7778');
  expect(geometry.border, `${label}: no visible frame`).toMatch(/^0px/);
}

async function expectNativeSquareMediaSurface(locator: Locator, label: string) {
  const geometry = await locator.evaluate((element) => {
    const surface = element.getBoundingClientRect();
    const media = element.querySelector<HTMLElement>('img, video');
    const mediaRect = media?.getBoundingClientRect();
    return {
      surfaceWidth: surface.width,
      surfaceHeight: surface.height,
      mediaWidth: mediaRect?.width ?? 0,
      mediaHeight: mediaRect?.height ?? 0,
      objectFit: media ? getComputedStyle(media).objectFit : null,
      framePolicy: media?.dataset.mediaFrame ?? null,
      sourceRatio: media?.dataset.mediaSourceRatio ?? null,
      border: getComputedStyle(element).border,
    };
  });
  expect(
    Math.abs(geometry.surfaceWidth - geometry.surfaceHeight),
    `${label}: square`,
  ).toBeLessThanOrEqual(1);
  expect(geometry.mediaWidth, `${label}: media fills width`).toBeGreaterThanOrEqual(
    geometry.surfaceWidth - 1,
  );
  expect(geometry.mediaHeight, `${label}: media fills height`).toBeGreaterThanOrEqual(
    geometry.surfaceHeight - 1,
  );
  expect(geometry.framePolicy, `${label}: native square policy`).toBe('native-square');
  expect(geometry.sourceRatio, `${label}: GIF source ratio`).toBe('1');
  expect(geometry.objectFit, `${label}: square source remains undistorted`).toBe('contain');
  expect(geometry.border, `${label}: no visible frame`).toMatch(/^0px/);
}

async function expectMediaClearOfFixedLayers(page: Page, locator: Locator, label: string) {
  await locator.scrollIntoViewIfNeeded();
  const overlap = await locator.evaluate((element) => {
    const target = element.getBoundingClientRect();
    const layers = [
      ...document.querySelectorAll<HTMLElement>('#appBottomNav, .active-workout-rest'),
    ];
    return layers
      .filter((layer) => {
        const style = getComputedStyle(layer);
        const rect = layer.getBoundingClientRect();
        return (
          style.display !== 'none' &&
          style.visibility !== 'hidden' &&
          rect.width > 0 &&
          rect.height > 0
        );
      })
      .some((layer) => {
        const rect = layer.getBoundingClientRect();
        return (
          rect.left < target.right &&
          rect.right > target.left &&
          rect.top < target.bottom &&
          rect.bottom > target.top
        );
      });
  });
  expect(overlap, `${label}: media must not be covered by dock/rest layer`).toBe(false);
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', /light|dark/);
}

test('Task 513 owner visual package covers catalog and exercise media states', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'no-preference' });
  await installTelegramHarness(page, { platform: 'android', colorScheme: 'light' });
  const telegramHarness = new TelegramHarness(page);
  await installPlatformApi(page, { browserSession: true });
  const mediaRoutes = await installMediaRoutes(page);
  await installCatalogRoutes(page);

  await page.goto('/app?section=catalog');
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('жим штанги лежа');
  await expect(
    page.locator('.exercise-catalog-item img[data-media-mode="static-poster"]'),
  ).toHaveCount(1);
  await page.screenshot({
    path: screenshotPath('catalog-mobile-light-390x844.png'),
    fullPage: true,
  });

  const lightDetail = await openCatalogDetail(page);
  await expect(lightDetail.media).toHaveAttribute('src', animationUrl);
  await expect(lightDetail.media).toHaveAttribute('data-media-mode', 'animation');
  await expect
    .poll(() => lightDetail.media.evaluate((image) => (image as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
  await expect(page.getByRole('heading', { name: 'Техника выполнения' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Оборудование' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Частые ошибки' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Что важно для безопасности' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Gym visual' })).toHaveAttribute(
    'href',
    'https://github.com/hasaneyldrm/exercises-dataset',
  );
  await expect(
    page.getByRole('link', { name: 'Owner-purchased GymVisual license' }),
  ).toHaveAttribute('href', 'https://gymvisual.com/');
  await expect(
    page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).resolves.toBe(true);
  await lightDetail.dialog.screenshot({
    animations: 'disabled',
    path: screenshotPath('exercise-detail-mobile-light-animated-390x844.png'),
  });

  mediaRoutes.setAnimationAvailable(false);
  await lightDetail.media.evaluate((image) => {
    const mediaImage = image as HTMLImageElement;
    mediaImage.src = `${mediaImage.src}?task513=broken-animation`;
  });
  await expect(lightDetail.media).toHaveAttribute('src', thumbnailUrl);
  await expect(lightDetail.media).toHaveAttribute('data-media-mode', 'static-poster');
  await lightDetail.dialog.screenshot({
    animations: 'disabled',
    path: screenshotPath('exercise-detail-mobile-static-fallback-390x844.png'),
  });
  await lightDetail.dialog.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();

  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.goto('/app?section=catalog');
  await telegramHarness.setTheme('dark');
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('жим штанги лежа');
  await page.screenshot({
    path: screenshotPath('catalog-mobile-dark-390x844.png'),
    fullPage: true,
  });
  const reducedDetail = await openCatalogDetail(page);
  await telegramHarness.setTheme('dark');
  await expect(reducedDetail.media).toHaveAttribute('src', thumbnailUrl);
  await expect(reducedDetail.media).toHaveAttribute('data-media-mode', 'static-poster');
  await reducedDetail.dialog.screenshot({
    animations: 'disabled',
    path: screenshotPath('exercise-detail-mobile-dark-reduced-motion-390x844.png'),
  });
  await reducedDetail.dialog.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();

  mediaRoutes.setAnimationAvailable(true);
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'no-preference' });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/app?section=catalog');
  await telegramHarness.setTheme('light');
  const desktopDetail = await openCatalogDetail(page);
  await expect(desktopDetail.media).toHaveAttribute('data-media-mode', 'animation');
  await desktopDetail.dialog.screenshot({
    animations: 'disabled',
    path: screenshotPath('exercise-detail-desktop-1440x900.png'),
  });
});

test('Issue 1186 fills wide technique media in guide and lightbox with source-aware cover', async ({
  page,
}) => {
  await installTelegramHarness(page, { platform: 'android', colorScheme: 'light' });
  const telegramHarness = new TelegramHarness(page);
  await installPlatformApi(page, { browserSession: true });
  await installWideMediaRoutes(page);
  await installWideCatalogRoutes(page);

  const afterDir = process.env.YFC_ISSUE_1186_AFTER_DIR;
  if (afterDir) await mkdir(afterDir, { recursive: true });

  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });

    for (const width of [320, 360, 393, 430]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 932 });
      const dialog = await openWideCatalogDetail(page, colorScheme);
      await telegramHarness.setTheme(colorScheme);
      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', colorScheme);
      const cardSurface = dialog.locator('.exercise-guide-image__frame').first();
      const cardImage = cardSurface.locator('img');
      await expect(cardImage).toHaveAttribute('src', widePosterUrl);
      await expect
        .poll(() => cardImage.evaluate((image) => (image as HTMLImageElement).naturalWidth))
        .toBeGreaterThan(0);
      await expectSquareMediaSurface(cardSurface, `${colorScheme} ${width}px guide`);
      await expect(cardImage).toHaveCSS('object-position', '46% 50%');
      await cardSurface.hover();
      await expect(cardImage).toHaveCSS('transform', 'none');
      await expect(dialog.locator('.exercise-guide-image')).toHaveCSS('border-top-width', '0px');
      await expect(
        page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).resolves.toBe(true);

      if (afterDir) {
        await dialog.screenshot({
          animations: 'disabled',
          path: resolve(afterDir, `${colorScheme}-${width}-guide.png`),
        });
      }

      await cardSurface.click();
      const lightbox = page.getByRole('dialog', { name: /Увеличенное изображение/ });
      const lightboxSurface = lightbox.locator('.exercise-lightbox__media');
      await expect(lightboxSurface).toBeVisible();
      await expectSquareMediaSurface(lightboxSurface, `${colorScheme} ${width}px lightbox`);
      if (afterDir) {
        await lightbox.screenshot({
          animations: 'disabled',
          path: resolve(afterDir, `${colorScheme}-${width}-lightbox.png`),
        });
      }
      await lightbox.locator('.exercise-lightbox__close').click();
      await expect(lightbox).not.toBeVisible();
    }
  }
});

test('Issue 1186 keeps a wide poster square in Active Workout', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await installTelegramHarness(page, { platform: 'android', colorScheme: 'dark' });
  await installPlatformApi(page, { browserSession: true });
  await installWideMediaRoutes(page);
  await installWideActiveWorkoutRoutes(page);

  await page.goto('/app');
  const continueButton = page.getByRole('button', { name: 'Продолжить тренировку' });
  const clientEntry = page.getByRole('button', { name: 'Клиент' });
  await Promise.race([
    continueButton.waitFor({ state: 'visible', timeout: 10000 }),
    clientEntry.waitFor({ state: 'visible', timeout: 10000 }),
  ]);
  if (!(await continueButton.isVisible())) await clientEntry.click();
  await expect(continueButton).toBeVisible();
  await continueButton.click();

  const media = page.locator('.active-workout-exercise__media').first();
  const image = media.locator('img');
  await expect(image).toHaveAttribute('src', widePosterUrl);
  await expect(image).toHaveAttribute('data-media-mode', 'static-poster');
  await expect
    .poll(() => image.evaluate((node) => (node as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
  await expectSquareMediaSurface(media, 'dark 390px Active Workout wide poster');
  await expect(image).toHaveCSS('object-position', '46% 50%');
  await expectMediaClearOfFixedLayers(page, media, 'dark 390px Active Workout wide poster');
  await expect(
    page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).resolves.toBe(true);
  const afterDir = process.env.YFC_ISSUE_1186_AFTER_DIR;
  if (afterDir) {
    await mkdir(afterDir, { recursive: true });
    await page.screenshot({
      animations: 'disabled',
      fullPage: true,
      path: resolve(afterDir, 'dark-390-active-workout.png'),
    });
  }
});

for (const colorScheme of ['light', 'dark'] as const) {
  for (const width of [320, 360, 393, 430]) {
    test(`Issue 1186 fills the real wide MP4 in Guide, lightbox and Active Workout: ${colorScheme} ${width}px`, async ({
      page,
    }) => {
      await installTelegramHarness(page, { platform: 'android', colorScheme });
      const telegramHarness = new TelegramHarness(page);
      await installPlatformApi(page, { browserSession: true });
      await installWideMediaRoutes(page);
      await installWideCatalogRoutes(page);
      await installWideActiveWorkoutRoutes(page);
      const afterDir = process.env.YFC_ISSUE_1186_AFTER_DIR;
      if (afterDir) {
        await mkdir(afterDir, { recursive: true });
      }
      await page.emulateMedia({ colorScheme, reducedMotion: 'no-preference' });
      await page.setViewportSize({ width, height: width < 500 ? 844 : 932 });
      const dialog = await openWideCatalogDetail(page, colorScheme);
      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', colorScheme);
      const cardSurface = dialog.locator('.exercise-guide-image__frame').first();
      const cardVideo = cardSurface.locator('video');
      await expect(cardVideo).toHaveAttribute('src', wideVideoUrl);
      await expect
        .poll(() => cardVideo.evaluate((video) => (video as HTMLVideoElement).videoWidth))
        .toBeGreaterThan(0);
      await expectSquareMediaSurface(cardSurface, `${colorScheme} ${width}px guide MP4`);
      await expect(cardVideo).toHaveCSS('object-position', '46% 50%');
      if (afterDir) {
        await dialog.screenshot({
          animations: 'disabled',
          path: resolve(afterDir, `${colorScheme}-${width}-guide-mp4.png`),
        });
      }

      await cardSurface.click();
      const lightbox = page.getByRole('dialog', { name: /Увеличенное изображение/ });
      const lightboxVideo = lightbox.locator('video');
      await expect(lightboxVideo).toHaveAttribute('src', wideVideoUrl);
      await expect
        .poll(() => lightboxVideo.evaluate((video) => (video as HTMLVideoElement).videoWidth))
        .toBeGreaterThan(0);
      await expectSquareMediaSurface(
        lightbox.locator('.exercise-lightbox__media'),
        `${colorScheme} ${width}px lightbox MP4`,
      );
      if (afterDir) {
        await lightbox.screenshot({
          animations: 'disabled',
          path: resolve(afterDir, `${colorScheme}-${width}-lightbox-mp4.png`),
        });
      }
      await lightbox.locator('.exercise-lightbox__close').click();
      await page.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();

      await telegramHarness.setTheme(colorScheme);
      await enterActiveWorkout(page);
      const activeMedia = page.locator('.active-workout-exercise__media').first();
      const activeVideo = activeMedia.locator('video');
      await expect(activeVideo).toHaveAttribute('src', wideVideoUrl);
      await expect
        .poll(() => activeVideo.evaluate((video) => (video as HTMLVideoElement).videoWidth))
        .toBeGreaterThan(0);
      await expectSquareMediaSurface(activeMedia, `${colorScheme} ${width}px Active Workout MP4`);
      await expectMediaClearOfFixedLayers(
        page,
        activeMedia,
        `${colorScheme} ${width}px Active Workout MP4`,
      );
      if (afterDir) {
        await page.screenshot({
          animations: 'disabled',
          path: resolve(afterDir, `${colorScheme}-${width}-active-workout-mp4.png`),
        });
      }
    });
  }
}

test('Issue 1186 keeps the native square GIF in Guide, lightbox and Active Workout', async ({
  page,
}) => {
  await installTelegramHarness(page, { platform: 'android', colorScheme: 'light' });
  const telegramHarness = new TelegramHarness(page);
  await installPlatformApi(page, { browserSession: true });
  await installMediaRoutes(page);
  await installCatalogRoutes(page);
  await installWideActiveWorkoutRoutes(page, 'gif');
  const afterDir = process.env.YFC_ISSUE_1186_AFTER_DIR;
  if (afterDir) await mkdir(afterDir, { recursive: true });

  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: 'no-preference' });
    for (const width of [320, 360, 393, 430]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 932 });
      await page.goto('/app?section=catalog');
      await page.evaluate((theme) => localStorage.setItem('app-theme', theme), colorScheme);
      const { dialog } = await openCatalogDetail(page);
      const cardSurface = dialog.locator('.exercise-guide-image__frame').first();
      const cardImage = cardSurface.locator('img');
      await expect(cardImage).toHaveAttribute('data-media-mode', 'animation');
      await expectNativeSquareMediaSurface(cardSurface, `${colorScheme} ${width}px GIF guide`);
      if (afterDir) {
        await dialog.screenshot({
          animations: 'disabled',
          path: resolve(afterDir, `${colorScheme}-${width}-guide-gif.png`),
        });
      }
      await cardSurface.click();
      const lightbox = page.getByRole('dialog', { name: /Увеличенное изображение/ });
      await expectNativeSquareMediaSurface(
        lightbox.locator('.exercise-lightbox__media'),
        `${colorScheme} ${width}px GIF lightbox`,
      );
      if (afterDir) {
        await lightbox.screenshot({
          animations: 'disabled',
          path: resolve(afterDir, `${colorScheme}-${width}-lightbox-gif.png`),
        });
      }
      await lightbox.locator('.exercise-lightbox__close').click();
      await page.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();

      await telegramHarness.setTheme(colorScheme);
      await enterActiveWorkout(page);
      const activeMedia = page.locator('.active-workout-exercise__media').first();
      await expect(activeMedia.locator('img')).toHaveAttribute('src', animationUrl);
      await expectNativeSquareMediaSurface(
        activeMedia,
        `${colorScheme} ${width}px GIF Active Workout`,
      );
      await expectMediaClearOfFixedLayers(
        page,
        activeMedia,
        `${colorScheme} ${width}px GIF Active Workout`,
      );
      if (afterDir) {
        await page.screenshot({
          animations: 'disabled',
          path: resolve(afterDir, `${colorScheme}-${width}-active-workout-gif.png`),
        });
      }
    }
  }
});

test('Task 513 Active Workout keeps technique access beside set logging', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'no-preference' });
  await installTelegramHarness(page, { platform: 'android', colorScheme: 'light' });
  await installPlatformApi(page, { browserSession: true });
  await installMediaRoutes(page);
  await page.route(/\/api\/v1\/workouts\/today(?:\?.*)?$/, (route) =>
    route.fulfill({
      json: {
        id: 42,
        scheduled_date: '2026-10-01',
        title: 'Силовая база',
        status: 'in_progress',
        day_number: 1,
        week_number: 1,
        started_at: '2026-10-01T08:00:00Z',
        completed_at: null,
        exercises: [
          {
            id: 101,
            exercise_id: 11,
            exercise_title: 'Жим штанги лёжа',
            metric_type: 'strength',
            sort_order: 1,
            prescribed_sets: 3,
            prescribed_reps: '8–10',
            rest_seconds: 90,
            notes: 'Сохраняйте устойчивое положение корпуса.',
            has_guide: true,
            media_state: 'approved_animated',
            media_thumbnail_url: thumbnailUrl,
            media_animation_url: animationUrl,
            sets: [
              {
                id: 201,
                set_number: 1,
                actual_reps: null,
                actual_weight: null,
                rir: null,
                set_kind: 'working',
                reached_failure: false,
                is_completed: false,
                version: 1,
              },
            ],
          },
        ],
      },
    }),
  );
  await page.route(/\/api\/v1\/programs\/exercises\/11(?:\?.*)?$/, (route) =>
    route.fulfill({ json: { ...exercise, id: 11, title: 'Жим штанги лёжа', guide } }),
  );
  await page.route(/\/api\/v1\/programs\/exercises\/11\/history(?:\?.*)?$/, (route) =>
    route.fulfill({
      json: {
        exercise_id: 11,
        exercise_title: 'Жим штанги лёжа',
        metric_type: 'strength',
        load_unit: 'kg',
        last_performed: null,
        best_authoritative_load: null,
        estimated_1rm: null,
        rep_prs: [],
        windows: [7, 30, 90].map((days) => ({
          days,
          period_start: '2026-10-01',
          period_end: '2026-10-01',
          performed_session_count: 0,
          completed_set_count: 0,
          authoritative_set_count: 0,
          reps_total: 0,
          best_authoritative_load_kg: null,
        })),
        recent_sessions: [],
        progression: [],
        progression_events: [],
        history_truncated: false,
      },
    }),
  );

  await page.goto('/app');
  const continueButton = page.getByRole('button', { name: 'Продолжить тренировку' });
  const clientEntry = page.getByRole('button', { name: 'Клиент' });
  await Promise.race([
    continueButton.waitFor({ state: 'visible', timeout: 10000 }),
    clientEntry.waitFor({ state: 'visible', timeout: 10000 }),
  ]);
  if (!(await continueButton.isVisible())) {
    await clientEntry.click();
  }
  await expect(continueButton).toBeVisible();
  await continueButton.click();

  const media = page.locator('.active-workout-exercise__media img');
  await expect(media).toHaveAttribute('data-media-mode', 'animated');
  const techniqueButton = page.getByRole('button', { name: 'Техника' });
  await expect(techniqueButton).toBeVisible();
  await expect(
    page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).resolves.toBe(true);
  await page.screenshot({
    animations: 'disabled',
    path: screenshotPath('active-workout-mobile-light-technique-access-390x844.png'),
    fullPage: true,
  });

  await techniqueButton.click();
  const dialog = page.getByRole('dialog', { name: 'Жим штанги лёжа' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('heading', { name: 'Техника выполнения' })).toBeVisible();
  await expect(dialog.getByRole('heading', { name: 'Оборудование' })).toBeVisible();
  await dialog.screenshot({
    animations: 'disabled',
    path: screenshotPath('active-workout-technique-dialog-390x844.png'),
  });
});
