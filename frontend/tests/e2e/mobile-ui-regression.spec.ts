import { expect, test, type Page } from '@playwright/test';
import {
  expectDockWithinViewport,
  expectElementsWithinHorizontalViewport,
  expectNoHorizontalOverflow,
  expectNoOverlap,
  expectTouchTargets,
  installTelegramHarness,
  TelegramHarness,
} from './fixtures/mobile-tma';
import {
  installPlatformApi,
  type PlatformApiController,
  type PlatformApiOptions,
} from './fixtures/platform-api';

const FIXED_DATE = '2026-09-06';
const MOBILE_VIEWPORTS = [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
] as const;

const screenshotOptions = {
  animations: 'disabled' as const,
  caret: 'hide' as const,
  scale: 'css' as const,
};

const activeWorkoutScreenshotOptions = {
  ...screenshotOptions,
  // The dock is covered by dedicated visibility/geometry assertions below. Hiding the fixed
  // chrome keeps its position from changing the clip of this intentionally tall component.
  stylePath: 'tests/e2e/fixtures/active-workout-screenshot.css',
};

type Surface = 'today' | 'nutrition' | 'progress' | 'profile';

async function preparePage(
  page: Page,
  theme: 'light' | 'dark',
  platform: 'browser' | 'telegram' = 'browser',
  options: PlatformApiOptions = {},
): Promise<{ api: PlatformApiController; tma: TelegramHarness | null }> {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.clock.setFixedTime(new Date(`${FIXED_DATE}T12:00:00+03:00`));
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
  await page.addInitScript((selectedTheme) => {
    localStorage.setItem('app-theme', selectedTheme);
  }, theme);

  let tma: TelegramHarness | null = null;
  if (platform === 'telegram') {
    await installTelegramHarness(page, {
      colorScheme: theme,
      viewportHeight: 760,
      viewportStableHeight: 844,
      safeAreaInset: { top: 28, right: 2, bottom: 20, left: 2 },
      contentSafeAreaInset: { top: 44, right: 0, bottom: 16, left: 0 },
    });
    tma = new TelegramHarness(page);
  }

  const api = await installPlatformApi(page, {
    browserSession: platform === 'browser',
    fixedDate: FIXED_DATE,
    measurementHistory: 'many',
    ...options,
  });
  return { api, tma };
}

async function waitForSurface(page: Page, surface: Surface): Promise<void> {
  const headings: Record<Surface, string | RegExp> = {
    today: /^Сегодня ·/,
    nutrition: 'Питание',
    progress: 'Прогресс',
    profile: 'Профиль и настройки',
  };
  await expect(page.locator('.app-shell')).toBeVisible();
  await expect(
    page.getByRole('heading', {
      name: headings[surface],
      exact: typeof headings[surface] === 'string',
    }),
  ).toBeVisible();
  await expect(page.locator('[role="status"][aria-busy="true"]')).toHaveCount(0);
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      Array.from(document.images).map(async (image) => {
        if (!image.complete) {
          await new Promise<void>((resolve) => {
            image.addEventListener('load', () => resolve(), { once: true });
            image.addEventListener('error', () => resolve(), { once: true });
          });
        }
        if (image.complete && image.naturalWidth > 0) await image.decode();
      }),
    );
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
  });
  await expect
    .poll(() =>
      page.evaluate(() =>
        Array.from(document.images)
          .filter((image) => image.naturalWidth === 0 || image.naturalHeight === 0)
          .map((image) => image.currentSrc || image.src),
      ),
    )
    .toEqual([]);
}

async function assertMobileShellGeometry(page: Page): Promise<void> {
  await expectNoHorizontalOverflow(page);
  await expectDockWithinViewport(page);
  await expectElementsWithinHorizontalViewport(
    page,
    '#appBottomNav .app-bottom-nav__primary > a, #appBottomNav .app-bottom-nav__primary > button',
  );
  await expectTouchTargets(
    page.locator(
      '#appBottomNav .app-bottom-nav__primary > a, #appBottomNav .app-bottom-nav__primary > button',
    ),
  );
}

for (const theme of ['light', 'dark'] as const) {
  test(`@critical mobile core surfaces keep the ${theme} visual contract`, async ({ page }) => {
    await preparePage(page, theme);
    await page.goto('/app?section=today');
    await waitForSurface(page, 'today');
    await assertMobileShellGeometry(page);

    const startWorkout = page.getByRole('button', { name: 'Начать тренировку' });
    await expect(startWorkout).toBeVisible();
    await expect(startWorkout).toBeInViewport();
    await expectNoOverlap(startWorkout, page.locator('#appBottomNav'));
    await expect(page).toHaveScreenshot(`today-390x844-${theme}.png`, {
      ...screenshotOptions,
      fullPage: true,
    });

    const surfaces: Array<{ name: Surface; locator: string }> = [
      { name: 'nutrition', locator: '.nutrition-diary' },
      { name: 'progress', locator: '.progress-experience' },
      { name: 'profile', locator: '.profile-settings' },
    ];
    for (const surface of surfaces) {
      await page.goto(`/app?section=${surface.name}`);
      await waitForSurface(page, surface.name);
      await assertMobileShellGeometry(page);
      if (surface.name === 'progress') {
        // Progress is intentionally long. Capture the canonical mobile viewport while the
        // geometry assertions above cover the full scrollable surface.
        await expect(page).toHaveScreenshot(`progress-390x844-${theme}.png`, screenshotOptions);
      } else {
        await expect(page.locator(surface.locator)).toHaveScreenshot(
          `${surface.name}-390x844-${theme}.png`,
          screenshotOptions,
        );
      }
    }
  });
}

test('@critical active workout keeps controls, keyboard and dock usable on mobile', async ({
  page,
}) => {
  await preparePage(page, 'dark', 'browser', { workoutStatus: 'in_progress' });
  await page.goto('/app?section=today');
  await waitForSurface(page, 'today');
  const continueWorkout = page.getByRole('button', { name: 'Продолжить тренировку' });
  await expect(continueWorkout).toBeVisible();
  await continueWorkout.click();

  await expect(page.locator('.active-workout')).toBeVisible();
  await assertMobileShellGeometry(page);
  const finish = page.getByRole('button', { name: 'Завершить тренировку' });
  await expect(finish).toBeVisible();
  await expectNoOverlap(finish, page.locator('#appBottomNav'));
  await expectTouchTargets(page.locator('.active-workout-set__done'));

  const reps = page.getByRole('spinbutton', { name: /Повторы, .*подход 1/ });
  await reps.focus();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
  await expect(page.locator('#appBottomNav')).toBeHidden();
  await finish.focus();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'hidden');
  await expect(page.locator('#appBottomNav')).toBeVisible();
  await reps.evaluate((element) => (element as HTMLElement).blur());
  await expectDockWithinViewport(page);

  const activeWorkout = page.locator('.active-workout');
  const activeWorkoutClip = await activeWorkout.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      x: rect.left,
      y: rect.top + window.scrollY,
      width: rect.width,
      height: rect.height,
    };
  });
  await expect(page).toHaveScreenshot('active-workout-390x844-dark.png', {
    ...activeWorkoutScreenshotOptions,
    fullPage: true,
    clip: activeWorkoutClip,
  });
});

test('@critical mocked TMA preserves safe areas, lifecycle and Today geometry', async ({
  page,
}) => {
  const prepared = await preparePage(page, 'dark', 'telegram');
  if (!prepared.tma) throw new Error('TMA harness was not installed');
  await page.goto('/app?tgWebAppPlatform=android');
  await waitForSurface(page, 'today');

  await expect(page.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');
  await expect(page.locator('html')).toHaveCSS('--yfc-tg-safe-bottom', '20px');
  await expect(page.locator('html')).toHaveCSS('--yfc-tg-content-safe-top', '44px');
  expect((await prepared.tma.state()).viewportHeight).toBe(760);
  const viewportMetrics = await page.evaluate(() => {
    const expected = Math.min(760, window.visualViewport?.height ?? window.innerHeight);
    const actual = Number.parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue('--yfc-viewport-height'),
    );
    return { actual, expected };
  });
  expect(viewportMetrics.actual).toBeGreaterThan(0);
  expect(viewportMetrics.actual).toBeCloseTo(viewportMetrics.expected, 0);
  await assertMobileShellGeometry(page);
  const startWorkout = page.getByRole('button', { name: 'Начать тренировку' });
  await expectNoOverlap(startWorkout, page.locator('#appBottomNav'));

  await expect(page).toHaveScreenshot('tma-today-390x844-dark.png', {
    ...screenshotOptions,
    fullPage: true,
  });

  const callsBeforeDeactivate = prepared.api.meCalls();
  await prepared.tma.setActive(false);
  await expect(page.locator('html')).toHaveAttribute('data-yfc-viewport-active', 'false');
  await prepared.tma.setActive(true);
  await expect(page.locator('html')).toHaveAttribute('data-yfc-viewport-active', 'true');
  await expect.poll(() => prepared.api.meCalls()).toBeGreaterThan(callsBeforeDeactivate);
  const state = await prepared.tma.state();
  expect(state.ready).toBeGreaterThan(0);
  expect(state.expand).toBeGreaterThan(0);
  expect(state.backButton.visible).toBe(false);
});

test('@extended mobile layout stress keeps long content inside viewport', async ({ page }) => {
  await preparePage(page, 'light', 'browser', { longExerciseName: true });
  await page.goto('/app?section=today');
  await waitForSurface(page, 'today');

  for (const viewport of [
    ...MOBILE_VIEWPORTS,
    { width: 320, height: 800 },
    { width: 844, height: 390 },
  ]) {
    await page.setViewportSize(viewport);
    await waitForSurface(page, 'today');
    await assertMobileShellGeometry(page);
    await expectElementsWithinHorizontalViewport(
      page,
      '.today-dashboard button, .today-dashboard a, .today-dashboard h1, .today-dashboard h2',
    );
    await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeVisible();
  }
});
