import { expect, test, type Page, type Route } from '@playwright/test';
import {
  expectNoHorizontalOverflow,
  installTelegramHarness,
  MOBILE_CONTEXTS,
  newMobilePage,
  TelegramHarness,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

const definitions = [
  ['pendulum-squat', 'Маятниковый присед в тренажёре', ['pendulum squat']],
  ['plate-loaded-leg-press', 'Жим ногами в тренажёре с дисками', ['жим ногами на блинах']],
  ['unilateral-leg-press', 'Жим одной ногой в тренажёре', ['single leg press']],
  [
    'machine-hip-thrust',
    'Ягодичный мост в рычажном тренажёре',
    ['ягодичный тренажер', 'glute drive'],
  ],
  ['smith-split-squat', 'Сплит-присед в машине Смита', ['smith lunge']],
  ['machine-glute-kickback', 'Разгибание бедра назад в тренажёре', ['machine glute kickback']],
  ['v-squat-machine', 'V-присед в рычажном тренажёре', ['v squat machine']],
  ['reverse-hyperextension', 'Обратная гиперэкстензия', ['reverse hyper']],
] as const;

const exercises = definitions.map(([slug, title, aliases], index) => ({
  id: 12020 + index,
  edit_target_id: 12020 + index,
  title,
  slug,
  metric_type: 'strength',
  primary_muscle: slug.includes('hip') || slug.includes('kickback') ? 'Ягодицы' : 'Квадрицепс',
  equipment: slug === 'smith-split-squat' ? 'Машина Смита' : 'Тренажёр',
  primary_muscle_ids: [slug.includes('hip') || slug.includes('kickback') ? 'glutes' : 'quadriceps'],
  secondary_muscle_ids: ['hamstrings'],
  equipment_ids: ['machine'],
  aliases: [...aliases],
  movement_pattern: slug === 'machine-hip-thrust' ? 'glute' : 'squat',
  machine_variant_tags: slug === 'smith-split-squat' ? ['smith'] : ['plate_loaded', 'lever'],
  execution_variant_tags:
    slug.includes('unilateral') || slug.includes('kickback') || slug.includes('split')
      ? ['unilateral']
      : ['bilateral'],
  alternatives: [],
  difficulty_level: 'beginner',
  is_custom: false,
  is_personalized: false,
  has_guide: true,
  source_exercise_id: null,
}));

const machineHipThrust = exercises.find((exercise) => exercise.slug === 'machine-hip-thrust')!;
const machineGluteKickback = exercises.find(
  (exercise) => exercise.slug === 'machine-glute-kickback',
)!;
const guide = {
  technique_steps: [
    'Настрой опору и ремень или подушку по инструкции тренажёра, зафиксируй таз и поставь стопы устойчиво.',
    'Разогни тазобедренные суставы без прогиба поясницы.',
    'Плавно опусти таз, сохраняя контакт с опорами.',
  ],
  breathing: 'Вдох при опускании таза, выдох во время разгибания бёдер.',
  common_mistakes: ['Прогиб поясницы', 'Стопы теряют опору', 'Рычаг резко опускается'],
  muscles: [
    {
      identifier: 'glutes',
      name: 'Ягодицы',
      role_id: 'primary',
      role: 'Основная',
      function: 'Разгибают бедро.',
    },
  ],
  equipment: [{ identifier: 'machine', name: 'Тренажёр' }],
  safety_notes: ['Используй нагрузку и амплитуду, при которых сохраняется описанная техника.'],
  alternatives: [],
  media: [
    {
      type: 'image',
      url: '/static/exercise-guides/human-v1/machine-hip-thrust/concentric_end-480w.webp',
      poster: '/static/exercise-guides/human-v1/machine-hip-thrust/concentric_end-480w.webp',
      phase_id: 'concentric_end',
      phase: 'Фаза усилия',
      alt: 'Ягодичный мост в рычажном тренажёре: бёдра разогнуты',
      source_name: 'Your Fitness Coach',
      source_url: '/',
      source_license: 'Иллюстрация создана для приложения',
      source_license_url: null,
      asset_id:
        'machine-hip-thrust:canonical_bilateral_plate_loaded_lap_pad:concentric_end:120e-v1',
      asset_version: '120e-v1',
      variant_key: 'canonical_bilateral_plate_loaded_lap_pad',
      width: 480,
      height: 320,
      byte_size: 12000,
      sort_order: 0,
      sources: [
        {
          url: '/static/exercise-guides/human-v1/machine-hip-thrust/concentric_end-480w.webp',
          mime_type: 'image/webp',
          width: 480,
          height: 320,
          byte_size: 12000,
        },
        {
          url: '/static/exercise-guides/human-v1/machine-hip-thrust/concentric_end-1280w.webp',
          mime_type: 'image/webp',
          width: 1280,
          height: 853,
          byte_size: 45000,
        },
      ],
    },
    {
      type: 'image',
      url: '/static/exercise-guides/human-v1/machine-hip-thrust/eccentric_end-480w.webp',
      poster: '/static/exercise-guides/human-v1/machine-hip-thrust/eccentric_end-480w.webp',
      phase_id: 'eccentric_end',
      phase: 'Фаза возврата',
      alt: 'Ягодичный мост в рычажном тренажёре: таз опущен',
      source_name: 'Your Fitness Coach',
      source_url: '/',
      source_license: 'Иллюстрация создана для приложения',
      source_license_url: null,
      asset_id: 'machine-hip-thrust:canonical_bilateral_plate_loaded_lap_pad:eccentric_end:120e-v1',
      asset_version: '120e-v1',
      variant_key: 'canonical_bilateral_plate_loaded_lap_pad',
      width: 480,
      height: 320,
      byte_size: 12000,
      sort_order: 1,
      sources: [
        {
          url: '/static/exercise-guides/human-v1/machine-hip-thrust/eccentric_end-480w.webp',
          mime_type: 'image/webp',
          width: 480,
          height: 320,
          byte_size: 12000,
        },
      ],
    },
  ],
  images: [],
  media_reference: 'exercise-guides:machine-hip-thrust',
  source_name: 'Your Fitness Coach',
  source_url: '/',
  source_license: 'Иллюстрация создана для приложения',
  source_license_url: null,
};

const gluteKickbackGuide = {
  ...guide,
  technique_steps: [
    'Поставь опорную стопу на платформу, прижми грудь к пэду и рабочую стопу к рычажной площадке.',
    'Отведи площадку назад разгибанием бедра без поворота таза.',
    'Плавно верни рычаг, сохраняя все точки опоры.',
  ],
  media: guide.media.map((item) => ({
    ...item,
    url: item.url.replace('machine-hip-thrust', 'machine-glute-kickback'),
    poster: item.poster.replace('machine-hip-thrust', 'machine-glute-kickback'),
    asset_id: item.asset_id
      .replace('machine-hip-thrust', 'machine-glute-kickback')
      .replace(
        'canonical_bilateral_plate_loaded_lap_pad',
        'canonical_unilateral_standing_lever_footplate',
      ),
    variant_key: 'canonical_unilateral_standing_lever_footplate',
    alt:
      item.phase_id === 'concentric_end'
        ? 'Разгибание бедра в тренажёре: площадка отведена назад без поворота таза'
        : 'Разгибание бедра в тренажёре: рабочая стопа на рычажной площадке у корпуса',
    sources: item.sources.map((source) => ({
      ...source,
      url: source.url.replace('machine-hip-thrust', 'machine-glute-kickback'),
    })),
  })),
};

async function installExerciseMocks(page: Page) {
  await installPlatformApi(page, { browserSession: true });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  await page.route(`**/api/v1/programs/exercises/${machineHipThrust.id}`, (route) =>
    route.fulfill({ json: { ...machineHipThrust, guide } }),
  );
  await page.route(`**/api/v1/programs/exercises/${machineGluteKickback.id}`, (route) =>
    route.fulfill({ json: { ...machineGluteKickback, guide: gluteKickbackGuide } }),
  );
  await page.route('**/static/exercise-guides/human-v1/**/*.webp', (route) => {
    const relativePath = route.request().url().split('/static/exercise-guides/').at(-1);
    if (!relativePath) throw new Error('WebP path is missing');
    return route.fulfill({
      path: `../backend/assets/exercise-guides/${relativePath}`,
      contentType: 'image/webp',
    });
  });
}

test('lower-body aliases, compact guide and program selection work on small viewports', async ({
  browser,
}) => {
  const { context, page } = await newMobilePage(browser, 'compact');
  await installTelegramHarness(page, { platform: 'android' });
  await installExerciseMocks(page);

  for (const [name, viewport] of Object.entries(MOBILE_CONTEXTS)) {
    await page.setViewportSize(viewport);
    await page.goto('/app?section=catalog');
    const search = page.getByRole('searchbox', { name: 'Поиск' });

    for (const [query, expectedTitle] of [
      ['pendulum squat', 'Маятниковый присед в тренажёре'],
      ['жим ногами на блинах', 'Жим ногами в тренажёре с дисками'],
      ['ягодичный тренажер', 'Ягодичный мост в рычажном тренажёре'],
      ['smith lunge', 'Сплит-присед в машине Смита'],
      ['reverse hyper', 'Обратная гиперэкстензия'],
    ] as const) {
      await search.fill(query);
      const row = page.locator('.exercise-catalog-item');
      await expect(row).toHaveCount(1);
      await expect(row).toContainText(expectedTitle);
      expect((await row.boundingBox())?.height).toBeLessThanOrEqual(128);
    }

    await search.fill('ягодичный тренажер');
    await page
      .locator('.exercise-catalog-item')
      .getByRole('button', { name: /Техника и детали/ })
      .tap();
    const dialog = page.getByRole('dialog', { name: machineHipThrust.title });
    await expect(dialog).toBeVisible();
    const media = dialog.locator('.exercise-guide-image img');
    await expect(media).toHaveCount(2);
    await expect(media.first()).toHaveAttribute('loading', 'lazy');
    await expect
      .poll(() =>
        media.evaluateAll((items) =>
          items.every((item) => (item as HTMLImageElement).naturalWidth > 0),
        ),
      )
      .toBe(true);
    await expectNoHorizontalOverflow(page);
    await dialog.screenshot({
      path: `../.artifacts/screenshots/task-120E/lower-guide-${name}-${viewport.width}.png`,
    });
    await dialog.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();
  }

  const tmaHarness = new TelegramHarness(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app?section=catalog');
  await tmaHarness.setTheme('dark');
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('machine glute kickback');
  await page
    .locator('.exercise-catalog-item')
    .getByRole('button', { name: /Техника и детали/ })
    .tap();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-120E/glute-kickback-mocked-tma-dark-390.png',
    fullPage: true,
  });
  await page
    .getByRole('dialog', { name: machineGluteKickback.title })
    .getByRole('button', { name: 'Закрыть карточку упражнения' })
    .click();

  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto('/app?section=programs&view=manage');
  const builder = page.locator('#program-builder');
  const picker = builder.getByRole('combobox', { name: 'Поиск упражнения' }).first();
  await picker.fill('жим ногами на блинах');
  const option = builder.getByRole('option', { name: /Жим ногами в тренажёре с дисками/ });
  await expect(option).toBeVisible();
  await option.tap();
  await expect(picker).toHaveValue('Жим ногами в тренажёре с дисками');
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: '../.artifacts/screenshots/task-120E/program-picker-mocked-tma-360.png',
    fullPage: true,
  });

  const tmaState = await tmaHarness.state();
  expect(tmaState.ready).toBeGreaterThan(0);
  expect(tmaState.platform).toBe('android');
  await context.close();
});

test('lower-body catalog and picker keep Mobile Web and desktop parity', async ({ browser }) => {
  const { context, page } = await newMobilePage(browser, 'baseline');
  await installExerciseMocks(page);

  for (const [name, viewport] of Object.entries(MOBILE_CONTEXTS)) {
    await page.setViewportSize(viewport);
    await page.goto('/app?section=catalog');
    await page.getByRole('searchbox', { name: 'Поиск' }).fill('machine glute kickback');
    const row = page.locator('.exercise-catalog-item');
    await expect(row).toHaveCount(1);
    await expect(row).toContainText('Разгибание бедра назад в тренажёре');
    expect((await row.boundingBox())?.height).toBeLessThanOrEqual(128);
    await expectNoHorizontalOverflow(page);
    if (viewport.width === 360) {
      await page.screenshot({
        path: '../.artifacts/screenshots/task-120E/catalog-mobile-web-light-360.png',
        fullPage: true,
      });
    }
    if (viewport.width === 390) {
      await row.getByRole('button', { name: /Техника и детали/ }).tap();
      const dialog = page.getByRole('dialog', { name: machineGluteKickback.title });
      await expect(dialog).toBeVisible();
      await expect(dialog.locator('.exercise-guide-image img')).toHaveCount(2);
      await expect
        .poll(() =>
          dialog
            .locator('.exercise-guide-images')
            .evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(' ').length),
        )
        .toBe(1);
      await page.screenshot({
        path: `../.artifacts/screenshots/task-120E/glute-kickback-mobile-web-${name}-390.png`,
        fullPage: true,
      });
      await dialog.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();
    }
  }

  await page.emulateMedia({ colorScheme: 'dark' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app?section=catalog');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('machine glute kickback');
  await page
    .locator('.exercise-catalog-item')
    .getByRole('button', { name: /Техника и детали/ })
    .tap();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-120E/glute-kickback-mobile-web-dark-390.png',
    fullPage: true,
  });
  await page
    .getByRole('dialog', { name: machineGluteKickback.title })
    .getByRole('button', { name: 'Закрыть карточку упражнения' })
    .click();
  await page.emulateMedia({ colorScheme: 'light' });

  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto('/app?section=programs&view=manage');
  const picker = page
    .locator('#program-builder')
    .getByRole('combobox', { name: 'Поиск упражнения' })
    .first();
  await picker.fill('glute drive');
  const option = page.getByRole('option', {
    name: /Ягодичный мост в рычажном тренажёре/,
  });
  await expect(option).toBeVisible();
  await option.tap();
  await expect(picker).toHaveValue('Ягодичный мост в рычажном тренажёре');
  await expectNoHorizontalOverflow(page);

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/app?section=catalog');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('v squat machine');
  await expect(page.locator('.exercise-catalog-item')).toContainText(
    'V-присед в рычажном тренажёре',
  );
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: '../.artifacts/screenshots/task-120E/catalog-desktop-1280.png',
    fullPage: true,
  });

  await page.getByRole('searchbox', { name: 'Поиск' }).fill('ягодичный тренажер');
  await page
    .locator('.exercise-catalog-item')
    .getByRole('button', { name: /Техника и детали/ })
    .click();
  const desktopDialog = page.getByRole('dialog', { name: machineHipThrust.title });
  await desktopDialog.screenshot({
    path: '../.artifacts/screenshots/task-120E/guide-desktop-light-1280.png',
  });
  await page.emulateMedia({ colorScheme: 'dark' });
  await desktopDialog.screenshot({
    path: '../.artifacts/screenshots/task-120E/guide-desktop-dark-1280.png',
  });
  await desktopDialog.getByRole('button', { name: 'Увеличить: Фаза усилия' }).click();
  await page.getByRole('dialog', { name: 'Увеличенное изображение: Фаза усилия' }).screenshot({
    path: '../.artifacts/screenshots/task-120E/lightbox-desktop-dark-1280.png',
  });

  await context.close();
});

test('human visual guide keeps technique visible while responsive media is loading', async ({
  browser,
}) => {
  const { context, page } = await newMobilePage(browser, 'baseline');
  await page.setViewportSize({ width: 390, height: 844 });
  await installExerciseMocks(page);
  let releaseMedia!: () => void;
  const mediaGate = new Promise<void>((resolve) => {
    releaseMedia = resolve;
  });
  const slowHandler = async (route: Route) => {
    await mediaGate;
    await route.fallback();
  };
  await page.route('**/static/exercise-guides/human-v1/machine-glute-kickback/*.webp', slowHandler);

  await page.goto('/app?section=catalog');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('machine glute kickback');
  await page
    .locator('.exercise-catalog-item')
    .getByRole('button', { name: /Техника и детали/ })
    .click();
  const dialog = page.getByRole('dialog', { name: machineGluteKickback.title });
  await expect(dialog.getByRole('heading', { name: 'Техника выполнения' })).toBeVisible();
  await dialog.screenshot({
    path: '../.artifacts/screenshots/task-120E/guide-slow-loading-mobile-web-390.png',
  });

  releaseMedia();
  await expect
    .poll(() =>
      dialog
        .locator('.exercise-guide-image img')
        .evaluateAll((items) => items.every((item) => (item as HTMLImageElement).naturalWidth > 0)),
    )
    .toBe(true);
  await context.close();
});

test('human visual guide exposes an accessible error fallback without a schematic asset', async ({
  browser,
}) => {
  const { context, page } = await newMobilePage(browser, 'baseline');
  await page.setViewportSize({ width: 390, height: 844 });
  await installExerciseMocks(page);
  await page.route('**/static/exercise-guides/human-v1/machine-glute-kickback/*.webp', (route) =>
    route.abort('failed'),
  );

  await page.goto('/app?section=catalog');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('machine glute kickback');
  await page
    .locator('.exercise-catalog-item')
    .getByRole('button', { name: /Техника и детали/ })
    .click();
  const dialog = page.getByRole('dialog', { name: machineGluteKickback.title });
  await expect(dialog.getByText('Изображение недоступно').first()).toBeVisible();
  await expect(dialog.getByRole('heading', { name: 'Техника выполнения' })).toBeVisible();
  await dialog.screenshot({
    path: '../.artifacts/screenshots/task-120E/guide-error-fallback-mobile-web-390.png',
  });
  await context.close();
});
