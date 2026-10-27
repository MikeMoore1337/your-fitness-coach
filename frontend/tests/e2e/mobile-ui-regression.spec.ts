import { expect, test, type Page } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
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
import { expectUiAuditClean } from './fixtures/ui-audit';

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
  await expectUiAuditClean(page, 'mobile shared shell', { checkTouchTargets: true });
}

test('@critical cardio datetime fits iPhone WebKit and Chromium', async ({ browser }, testInfo) => {
  test.setTimeout(120_000);
  const filledDate = '2026-10-26T14:00';

  for (const theme of ['light', 'dark'] as const) {
    for (const platform of ['browser', 'telegram'] as const) {
      const page = await browser.newPage({
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
        locale: 'ru-RU',
        timezoneId: 'Europe/Moscow',
      });
      try {
        const { tma } = await preparePage(page, theme, platform, { cardioState: 'empty' });
        await page.goto('/app?section=today&cardio=1');
        await waitForSurface(page, 'today');

        const card = page.locator('.cardio-log--quick');
        const date = card.getByLabel('Дата и время');
        await expect(date).toHaveAttribute('type', 'datetime-local');
        await date.fill(filledDate);

        for (const width of [320, 360, 390, 430]) {
          await page.setViewportSize({ width, height: 844 });
          if (tma) await tma.setViewport(844, 844);

          const geometry = await date.evaluate((input) => {
            const field = input.closest('.ui-field');
            const card = input.closest('.cardio-log');
            if (!field || !card) throw new Error('Cardio date card geometry is missing');
            const inputRect = input.getBoundingClientRect();
            const fieldRect = field.getBoundingClientRect();
            const cardRect = card.getBoundingClientRect();
            return {
              inputLeft: inputRect.left,
              inputRight: inputRect.right,
              fieldLeft: fieldRect.left,
              fieldRight: fieldRect.right,
              cardRight: cardRect.right,
              cardOverflow: card.scrollWidth - card.clientWidth,
              pageOverflow:
                document.documentElement.scrollWidth - document.documentElement.clientWidth,
            };
          });
          expect(geometry.inputLeft).toBeGreaterThanOrEqual(geometry.fieldLeft - 1);
          expect(geometry.inputRight).toBeLessThanOrEqual(geometry.fieldRight + 1);
          expect(geometry.inputRight).toBeLessThanOrEqual(geometry.cardRight + 1);
          expect(geometry.inputRight).toBeLessThanOrEqual(width + 1);
          expect(geometry.cardOverflow).toBeLessThanOrEqual(1);
          expect(geometry.pageOverflow).toBeLessThanOrEqual(1);
          await expect(date).toHaveValue(filledDate);

          if (width === 390) {
            await card.screenshot({
              path: testInfo.outputPath(`cardio-${platform}-${theme}-390.png`),
              ...screenshotOptions,
            });
          }
        }
      } finally {
        await page.close();
      }
    }
  }
});

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
  const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
  const toggle = summary.getByRole('button', { name: 'Что делать сейчас?' });
  const assertSharedSummaryFrame = async () => {
    const styles = await summary.evaluate((element) => {
      const summaryStyle = getComputedStyle(element);
      return {
        width: summaryStyle.borderTopWidth,
        style: summaryStyle.borderTopStyle,
        radius: summaryStyle.borderTopLeftRadius,
      };
    });
    expect(styles.width).toBe('1px');
    expect(styles.style).toBe('solid');
    expect(styles.radius).not.toBe('0px');
  };
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await assertSharedSummaryFrame();
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await assertSharedSummaryFrame();
  await expect(summary.locator('.active-session-summary__details')).toHaveCSS(
    'border-top-width',
    '0px',
  );

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
  await expectNoOverlap(finish, page.locator('#appBottomNav'));
  await reps.evaluate((element) => (element as HTMLElement).blur());
  await expectDockWithinViewport(page);
  // Focus-driven scrolling can leave the pointer hovering over a different button.
  await page.mouse.move(0, 0);

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

test('@critical active workout keeps the current set primary across mobile widths', async ({
  page,
}) => {
  await preparePage(page, 'dark', 'browser', { workoutStatus: 'in_progress' });

  for (const viewport of MOBILE_VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto('/app?section=today');
    await waitForSurface(page, 'today');
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

    const currentSet = page.locator('.active-workout-set.is-current');
    const currentSetDone = currentSet.locator('.active-workout-set__done');
    await expect(currentSet).toBeVisible();
    await expect(currentSet).toContainText(/Подход \d+ из \d+/);
    await expect(currentSet).toContainText(/(?:повторений|Повторы по плану)/);
    await expect(currentSet).toContainText(/Отдых \d+ с/);
    await expect(currentSetDone).toBeVisible();
    await expect(page.locator('.app-bottom-nav__quick-add')).toBeVisible();

    // A previous viewport/click can leave a long active-session page at an
    // intermediate scroll position, where a fixed dock temporarily covers
    // ordinary content. Audit the canonical top viewport first; below we
    // still scroll the *actual current set action* into view and explicitly
    // assert it is not covered by the dock.
    await page.evaluate(async () => {
      window.scrollTo(0, 0);
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      });
    });
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    await assertMobileShellGeometry(page);

    expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeGreaterThan(
      viewport.height,
    );
    await expectNoOverlap(currentSetDone, page.locator('#appBottomNav'));
    await currentSetDone.evaluate((element) => {
      element.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'nearest' });
    });
    await expect(currentSetDone).toBeInViewport();
    await expectNoOverlap(currentSetDone, page.locator('#appBottomNav'));
    await expect(currentSetDone).toHaveJSProperty('disabled', false);
    await expect(
      currentSetDone.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const hit = document.elementFromPoint(
          rect.left + rect.width / 2,
          rect.top + rect.height / 2,
        );
        return hit === element || hit?.closest('[data-workout-field="done"]') === element;
      }),
    ).resolves.toBe(true);
    await expectNoOverlap(
      page.getByRole('button', { name: 'Завершить тренировку' }),
      page.locator('#appBottomNav'),
    );
    await expectUiAuditClean(page, 'active workout current set', { checkTouchTargets: true });

    const weightInput = currentSet.getByRole('textbox', { name: /Вес, .*подход 1/ });
    const repsInput = currentSet.getByRole('spinbutton', { name: /Повторы, .*подход 1/ });
    await expect(currentSet.locator('input:visible')).toHaveCount(2);
    await expect(weightInput).toHaveAttribute('inputmode', 'decimal');
    await expect(repsInput).toHaveAttribute('inputmode', 'numeric');

    for (const input of [weightInput, repsInput]) {
      await input.focus();
      await expect(input).toBeInViewport();
      await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
      await expect(page.locator('#appBottomNav')).toBeHidden();
      await expect(page.locator('.app-bottom-nav__quick-add')).toBeHidden();
      await input.evaluate((element) => (element as HTMLElement).blur());
      await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'hidden');
      await expect(page.locator('#appBottomNav')).toBeVisible();
    }
    const bottomNav = page.locator('#appBottomNav');
    await expect(bottomNav.locator('.app-bottom-nav__primary > a')).toHaveCount(4);
    await expect(bottomNav.locator('.app-bottom-nav__quick-add')).toHaveCount(1);
    for (const label of ['Сегодня', 'План', 'Питание', 'Прогресс']) {
      const link = bottomNav.getByRole('link', { name: label, exact: true });
      await expect(link).toBeVisible();
      await expect(link.locator('svg[data-icon]')).toBeVisible();
    }
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    );
    // WebKit can defer fixed-nav inline SVG painting after the keyboard-hide repaint.
    // A paint-only capture makes the following evidence screenshot deterministic.
    await page.screenshot({ animations: 'disabled' });
    await page.screenshot({
      path: test.info().outputPath(`active-workout-${viewport.width}x${viewport.height}-dark.png`),
      fullPage: false,
      animations: 'disabled',
    });
  }
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

test('@critical mocked TMA keeps the dock inside the effective viewport and hit-testable', async ({
  page,
}) => {
  const prepared = await preparePage(page, 'dark', 'telegram');
  if (!prepared.tma) throw new Error('TMA harness was not installed');
  await page.goto('/app?tgWebAppPlatform=android');
  await waitForSurface(page, 'today');
  // The dock-clearance assertion is for the keyboard-closed layout.
  // Wait for the layout adapter to finish any focus/viewport update.
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'hidden');

  const geometry = await page.evaluate(() => {
    const rootStyle = getComputedStyle(document.documentElement);
    const dock = document.getElementById('appBottomNav');
    if (!dock) throw new Error('Mobile dock is missing');
    const dockRect = dock.getBoundingClientRect();
    const dockHeight = Number.parseFloat(rootStyle.getPropertyValue('--app-bottom-nav-height'));
    const viewportBottom = Number.parseFloat(rootStyle.getPropertyValue('--yfc-viewport-bottom'));
    const layoutSafeBottom = Math.max(
      Number.parseFloat(rootStyle.getPropertyValue('--yfc-tg-safe-bottom')) || 0,
      Number.parseFloat(rootStyle.getPropertyValue('--yfc-content-safe-bottom')) || 0,
    );
    const effectiveViewportBottom = window.innerHeight - viewportBottom;
    const dockHit = document.elementFromPoint(
      dockRect.left + dockRect.width / 2,
      dockRect.top + dockRect.height / 2,
    );

    return {
      bodyPaddingBottom: Number.parseFloat(getComputedStyle(document.body).paddingBottom),
      dockHeight,
      dockBottom: dockRect.bottom,
      dockHit: dockHit?.closest('#appBottomNav') === dock,
      effectiveViewportBottom,
      layoutSafeBottom,
      viewportBottom,
    };
  });
  expect(geometry.viewportBottom).toBeGreaterThan(0);
  expect(geometry.dockBottom).toBeLessThanOrEqual(geometry.effectiveViewportBottom + 1);
  expect(geometry.dockHit).toBe(true);
  expect(geometry.bodyPaddingBottom).toBeGreaterThanOrEqual(
    geometry.dockHeight + 24 + Math.max(8, geometry.layoutSafeBottom) + geometry.viewportBottom - 1,
  );
});

test('@critical reduced motion keeps TMA dock clearance current', async ({ page }) => {
  await preparePage(page, 'dark', 'telegram');
  await page.goto('/app?tgWebAppPlatform=android');
  await waitForSurface(page, 'today');

  await expect(page.locator('body')).toHaveCSS('transition-duration', '0s');
  await expect
    .poll(() =>
      page.evaluate(() => {
        const rootStyle = getComputedStyle(document.documentElement);
        const dockHeight = Number.parseFloat(rootStyle.getPropertyValue('--app-bottom-nav-height'));
        const viewportBottom = Number.parseFloat(
          rootStyle.getPropertyValue('--yfc-viewport-bottom'),
        );
        const safeBottom = Math.max(
          Number.parseFloat(rootStyle.getPropertyValue('--yfc-tg-safe-bottom')) || 0,
          Number.parseFloat(rootStyle.getPropertyValue('--yfc-content-safe-bottom')) || 0,
        );
        return (
          Number.parseFloat(getComputedStyle(document.body).paddingBottom) -
          (dockHeight + 24 + Math.max(8, safeBottom) + viewportBottom - 1)
        );
      }),
    )
    .toBeGreaterThanOrEqual(0);
});

for (const theme of ['dark', 'light'] as const) {
  for (const width of [320, 360, 390, 393, 430]) {
    test(`@critical mocked TMA keeps Active Workout RIR and finish controls clear at ${width}px ${theme}`, async ({
      page,
    }, info) => {
      const prepared = await preparePage(page, theme, 'telegram', { workoutStatus: 'in_progress' });
      if (!prepared.tma) throw new Error('TMA harness was not installed');
      await page.setViewportSize({ width, height: 844 });
      await page.goto('/app?tgWebAppPlatform=ios');
      await waitForSurface(page, 'today');
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

      const currentSet = page.locator('.active-workout-set.is-current');
      await expect(currentSet).toBeVisible();
      const rir = currentSet
        .locator('.active-workout-rir--quick .active-workout-rir__options button')
        .first();
      await rir.scrollIntoViewIfNeeded();

      const measure = async (selector: string) =>
        page.evaluate((targetSelector) => {
          const rootStyle = getComputedStyle(document.documentElement);
          const target = document.querySelector<HTMLElement>(targetSelector);
          const dock = document.querySelector<HTMLElement>('#appBottomNav');
          if (!target || !dock) throw new Error(`Missing geometry target: ${targetSelector}`);
          const targetRect = target.getBoundingClientRect();
          const dockRect = dock.getBoundingClientRect();
          const viewportBottom = Number.parseFloat(
            rootStyle.getPropertyValue('--yfc-viewport-bottom'),
          );
          const effectiveBottom = window.innerHeight - viewportBottom;
          const point = document.elementFromPoint(
            targetRect.left + targetRect.width / 2,
            targetRect.top + targetRect.height / 2,
          );
          return {
            target: targetRect.toJSON(),
            dock: dockRect.toJSON(),
            viewport: { width: window.innerWidth, height: window.innerHeight, effectiveBottom },
            documentWidth: {
              client: document.documentElement.clientWidth,
              scroll: document.documentElement.scrollWidth,
            },
            hit: point === target || Boolean(point?.closest(selector)),
            overlap: targetRect.bottom > dockRect.top && targetRect.top < dockRect.bottom,
          };
        }, selector);

      const rirGeometry = await measure(
        '.active-workout-set.is-current .active-workout-rir--quick .active-workout-rir__options button',
      );
      expect(rirGeometry.target.left).toBeGreaterThanOrEqual(-0.5);
      expect(rirGeometry.target.right).toBeLessThanOrEqual(width + 0.5);
      expect(rirGeometry.target.top).toBeGreaterThanOrEqual(-0.5);
      expect(rirGeometry.target.bottom).toBeLessThanOrEqual(
        rirGeometry.viewport.effectiveBottom + 0.5,
      );
      expect(rirGeometry.overlap).toBe(false);
      expect(rirGeometry.hit).toBe(true);
      expect(rirGeometry.documentWidth.scroll).toBeLessThanOrEqual(
        rirGeometry.documentWidth.client + 1,
      );
      const capture = process.env.CAPTURE_867_AFTER === '1' && width === 390;
      const afterDir = resolve(
        process.cwd(),
        '../docs/ux/final-issues-acceptance/evidence/867-tma-clearance-20261013/after',
      );
      if (capture) {
        await mkdir(afterDir, { recursive: true });
        await page.screenshot({ path: resolve(afterDir, `${info.project.name}-${theme}-rir.png`) });
      }

      const finish = page.getByRole('button', { name: 'Завершить тренировку', exact: true });
      await finish.scrollIntoViewIfNeeded();
      const finishGeometry = await measure('.active-workout-finish button');
      expect(finishGeometry.target.left).toBeGreaterThanOrEqual(-0.5);
      expect(finishGeometry.target.right).toBeLessThanOrEqual(width + 0.5);
      expect(finishGeometry.target.top).toBeGreaterThanOrEqual(-0.5);
      expect(finishGeometry.target.bottom).toBeLessThanOrEqual(
        finishGeometry.viewport.effectiveBottom + 0.5,
      );
      expect(finishGeometry.overlap).toBe(false);
      expect(finishGeometry.hit).toBe(true);
      expect(finishGeometry.documentWidth.scroll).toBeLessThanOrEqual(
        finishGeometry.documentWidth.client + 1,
      );
      if (capture) {
        await page.screenshot({
          path: resolve(afterDir, `${info.project.name}-${theme}-footer.png`),
        });
        await writeFile(
          resolve(afterDir, `${info.project.name}-${theme}-geometry.json`),
          JSON.stringify(
            {
              synthetic: true,
              theme,
              browser: info.project.name,
              width,
              rir: rirGeometry,
              finish: finishGeometry,
            },
            null,
            2,
          ),
        );
      }
    });
  }
}

test('@extended WeekStrip reveals a changed selected date inside the visible rail', async ({
  page,
}) => {
  await preparePage(page, 'light', 'browser');
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto('/app?section=nutrition');
  await waitForSurface(page, 'nutrition');

  const week = page.getByRole('navigation', { name: 'Неделя дневника' });
  const rail = week.locator('.week-strip__days');
  const initialSelected = rail.locator('button[aria-pressed="true"]');
  const target = rail.locator('button[aria-pressed="false"]:not(:disabled)').first();
  await expect(initialSelected).toHaveCount(1);
  await expect(target).toHaveCount(1);
  const initialLabel = await initialSelected.getAttribute('aria-label');

  await target.click();

  const selected = rail.locator('button[aria-pressed="true"]');
  await expect(selected).toHaveCount(1);
  await expect.poll(() => selected.getAttribute('aria-label')).not.toBe(initialLabel);
  await expect
    .poll(() =>
      rail.evaluate((element) => {
        const railRect = element.getBoundingClientRect();
        const selected = element.querySelector<HTMLButtonElement>('button[aria-pressed="true"]');
        if (!selected) return { selected: false, intersects: false, contained: false };
        const selectedRect = selected.getBoundingClientRect();
        return {
          selected: true,
          intersects: selectedRect.right > railRect.left && selectedRect.left < railRect.right,
          contained:
            selectedRect.left >= railRect.left - 0.5 && selectedRect.right <= railRect.right + 0.5,
          rail: { left: railRect.left, right: railRect.right },
          selectedRect: { left: selectedRect.left, right: selectedRect.right },
        };
      }),
    )
    .toMatchObject({ selected: true, intersects: true, contained: true });
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
      '.today-dashboard button:not(.week-strip__day), .today-dashboard a, .today-dashboard h1, .today-dashboard h2',
    );
    await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeVisible();
  }

  await page.evaluate(() => {
    const probe = document.createElement('div');
    probe.dataset.yfcTestOverflowProbe = 'true';
    probe.style.cssText =
      'position:absolute;left:0;top:0;width:calc(100vw + 32px);height:1px;pointer-events:none;';
    document.body.append(probe);
  });
  try {
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
    await expect(expectNoHorizontalOverflow(page)).rejects.toThrow();
  } finally {
    await page.evaluate(() => {
      document.querySelector('[data-yfc-test-overflow-probe]')?.remove();
    });
  }
  await expectNoHorizontalOverflow(page);
});

for (const theme of ['light', 'dark'] as const) {
  for (const width of [320, 360, 390, 393, 430] as const) {
    test(`@critical #867 keeps the browser dock clear at ${width}px ${theme}`, async ({
      page,
    }, info) => {
      await preparePage(page, theme, 'browser');
      await page.setViewportSize({ width, height: 844 });
      await page.goto('/app?section=today');
      await waitForSurface(page, 'today');

      await page.evaluate(() => {
        const root = document.documentElement;
        root.style.setProperty('--yfc-layout-safe-bottom', '34px');
        const viewport = window.visualViewport;
        if (!viewport) throw new Error('visualViewport is required for #867 geometry coverage');
        Object.defineProperty(viewport, 'height', {
          configurable: true,
          value: window.innerHeight - 34,
        });
        Object.defineProperty(viewport, 'offsetTop', { configurable: true, value: 0 });
        viewport.dispatchEvent(new Event('resize'));
        window.dispatchEvent(new Event('resize'));
      });

      await expect
        .poll(() =>
          page.evaluate(() => {
            const rootStyle = getComputedStyle(document.documentElement);
            const dock = document.querySelector<HTMLElement>('#appBottomNav');
            if (!dock) return null;
            return {
              viewportBottom: rootStyle.getPropertyValue('--yfc-viewport-bottom').trim(),
              safeBottom: rootStyle.getPropertyValue('--yfc-layout-safe-bottom').trim(),
              dockBottomGap: window.innerHeight - dock.getBoundingClientRect().bottom,
            };
          }),
        )
        .not.toBeNull();

      const measureGeometry = () =>
        page.evaluate(() => {
          const rootStyle = getComputedStyle(document.documentElement);
          const dock = document.querySelector<HTMLElement>('#appBottomNav');
          const quickAdd = document.querySelector<HTMLElement>('.app-bottom-nav__quick-add');
          const startWorkout = Array.from(document.querySelectorAll<HTMLElement>('button')).find(
            (button) => button.textContent?.includes('Начать тренировку'),
          );
          if (!dock || !quickAdd || !startWorkout) throw new Error('Missing #867 geometry target');
          const dockRect = dock.getBoundingClientRect();
          const quickAddRect = quickAdd.getBoundingClientRect();
          const startWorkoutRect = startWorkout.getBoundingClientRect();
          const quickAddHit =
            document
              .elementFromPoint(
                quickAddRect.left + quickAddRect.width / 2,
                quickAddRect.top + quickAddRect.height / 2,
              )
              ?.closest('.app-bottom-nav__quick-add') === quickAdd;
          return {
            surface: document.documentElement.dataset.yfcLayoutSurface,
            viewportBottom: Number.parseFloat(rootStyle.getPropertyValue('--yfc-viewport-bottom')),
            safeBottom: Number.parseFloat(rootStyle.getPropertyValue('--yfc-layout-safe-bottom')),
            effectiveViewportBottom: rootStyle
              .getPropertyValue('--yfc-viewport-bottom-effective')
              .trim(),
            dockBottomGap: window.innerHeight - dockRect.bottom,
            quickAddVisible: quickAdd.getClientRects().length > 0,
            quickAddHit,
            startWorkoutInViewport:
              startWorkoutRect.top >= -0.5 && startWorkoutRect.bottom <= window.innerHeight + 0.5,
            startWorkoutOverlapsDock:
              startWorkoutRect.bottom > dockRect.top && startWorkoutRect.top < dockRect.bottom,
            documentWidth: {
              client: document.documentElement.clientWidth,
              scroll: document.documentElement.scrollWidth,
            },
          };
        });

      const geometry = await measureGeometry();
      await assertMobileShellGeometry(page);
      expect(geometry.surface).toBe('browser');
      expect(geometry.viewportBottom).toBe(34);
      expect(geometry.safeBottom).toBe(34);
      // An iPhone-like 34px safe area should yield the ~20px outer gap
      // seen in native floating tab bars, not the old 46px gap.
      expect(geometry.dockBottomGap).toBeGreaterThanOrEqual(19);
      expect(geometry.dockBottomGap).toBeLessThanOrEqual(21);
      expect(geometry.quickAddVisible).toBe(true);
      expect(geometry.quickAddHit).toBe(true);
      expect(geometry.startWorkoutInViewport).toBe(true);
      expect(geometry.startWorkoutOverlapsDock).toBe(false);
      expect(geometry.documentWidth.scroll).toBeLessThanOrEqual(geometry.documentWidth.client + 1);

      if (process.env.CAPTURE_867_AFTER === '1' && width === 393) {
        const evidenceRoot = resolve(
          process.cwd(),
          `../docs/ux/final-issues-acceptance/evidence/867-mobile-geometry-20261016`,
        );
        await mkdir(resolve(evidenceRoot, 'before'), { recursive: true });
        await mkdir(resolve(evidenceRoot, 'after'), { recursive: true });
        const evidenceName = `${info.project.name}-${theme}-393x844`;

        await page.evaluate(() => {
          document.documentElement.style.setProperty('--yfc-viewport-bottom-effective', '34px');
        });
        const beforeGeometry = await measureGeometry();
        await page.screenshot({
          path: resolve(evidenceRoot, 'before', `${evidenceName}.png`),
          ...screenshotOptions,
          fullPage: true,
        });

        await page.evaluate(() => {
          document.documentElement.style.removeProperty('--yfc-viewport-bottom-effective');
        });
        await page.evaluate(
          () =>
            new Promise<void>((resolve) =>
              requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
            ),
        );
        const afterGeometry = await measureGeometry();
        await page.screenshot({
          path: resolve(evidenceRoot, 'after', `${evidenceName}.png`),
          ...screenshotOptions,
          fullPage: true,
        });
        await writeFile(
          resolve(evidenceRoot, `${evidenceName}-geometry.json`),
          JSON.stringify(
            {
              synthetic: true,
              issue: 867,
              theme,
              browser: info.project.name,
              viewport: { width, height: 844 },
              before: beforeGeometry,
              after: afterGeometry,
            },
            null,
            2,
          ),
        );
      }

      const lastInteractive = page
        .locator('#appContent :where(button, a, input, select, textarea, summary):visible')
        .last();
      await expect(lastInteractive).toBeVisible();
      await lastInteractive.scrollIntoViewIfNeeded();
      await expect(lastInteractive).toBeInViewport();
      const lastInteractiveGeometry = await lastInteractive.evaluate((element) => {
        const targetRect = element.getBoundingClientRect();
        const dock = document.querySelector<HTMLElement>('#appBottomNav');
        if (!dock) throw new Error('Mobile dock is missing after last-item scroll');
        const dockRect = dock.getBoundingClientRect();
        const targetPoint = document.elementFromPoint(
          targetRect.left + targetRect.width / 2,
          targetRect.top + targetRect.height / 2,
        );
        return {
          overlap: targetRect.bottom > dockRect.top && targetRect.top < dockRect.bottom,
          hit: targetPoint === element || Boolean(targetPoint && element.contains(targetPoint)),
        };
      });
      expect(lastInteractiveGeometry.overlap).toBe(false);
      expect(lastInteractiveGeometry.hit).toBe(true);
    });
  }
}
