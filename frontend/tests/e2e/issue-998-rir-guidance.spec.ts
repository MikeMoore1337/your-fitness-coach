import { expect, test, type Page } from '@playwright/test';
import { resolve } from 'node:path';
import { installPlatformApi } from './fixtures/platform-api';
import { expectNoHorizontalOverflow, installTelegramHarness } from './fixtures/mobile-tma';

const FIXED_DATE = '2026-08-20';
const STAGE = process.env.ISSUE_998_EVIDENCE_STAGE;
const EVIDENCE_DIR = process.env.ISSUE_998_EVIDENCE_DIR;

const VIEWPORTS = [
  { label: '320', width: 320, height: 844 },
  { label: '360', width: 360, height: 844 },
  { label: '393', width: 393, height: 844 },
  { label: '430', width: 430, height: 932 },
  { label: 'desktop', width: 1440, height: 900 },
] as const;

async function preparePage(
  page: Page,
  theme: 'dark' | 'light',
  viewport: (typeof VIEWPORTS)[number],
  options: { programHistory?: 'one' } = {},
) {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.clock.setFixedTime(new Date(`${FIXED_DATE}T12:00:00+03:00`));
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
  await page.addInitScript((selectedTheme) => {
    localStorage.setItem('app-theme', selectedTheme);
  }, theme);
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: FIXED_DATE,
    workoutStatus: 'in_progress',
    progressionOutcome: 'consider_progressing',
    programHistory: options.programHistory,
  });
}

async function enterWorkout(page: Page) {
  await page.goto('/app?section=today');
  await expect(page.locator('.app-shell')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Продолжить тренировку' })).toBeVisible();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const currentSet = page.locator('.active-workout-set.is-current');
  await expect(currentSet).toBeVisible();
  await expect(page.locator('[role="status"][aria-busy="true"]')).toHaveCount(0);
  return currentSet;
}

async function captureSurface(page: Page, name: string, selector = '.active-workout') {
  if (STAGE === undefined || !EVIDENCE_DIR || test.info().project.name !== 'chromium') return;
  await page.locator(selector).screenshot({ path: resolve(EVIDENCE_DIR, name) });
}

for (const theme of ['dark', 'light'] as const) {
  for (const viewport of VIEWPORTS) {
    test(`@critical Issue #998 ${viewport.label}px ${theme}`, async ({ page }) => {
      await preparePage(page, theme, viewport);
      const currentSet = await enterWorkout(page);
      await expectNoHorizontalOverflow(page);

      const weight = currentSet.getByLabel(/^Вес,/);
      const reps = currentSet.getByRole('spinbutton', { name: /^Повторы,/ });
      const complete = currentSet.getByRole('button', { name: /^Завершить:/ });
      await expect(weight).toBeVisible();
      await expect(reps).toBeVisible();
      await expect(complete).toBeVisible();
      await expect(page.locator('body')).not.toContainText('AI Coach');

      if (STAGE !== 'before') {
        const rirDetails = currentSet.locator(
          '.active-workout-set__contextual-help .contextual-help',
        );
        const rirSummary = rirDetails.getByText('Что такое RIR?', { exact: true });
        await expect(rirSummary).toBeVisible();
        await expect(rirDetails).not.toHaveAttribute('open', '');

        const sessionSummary = page.getByRole('region', { name: 'Что делать сейчас?' });
        const sessionToggle = sessionSummary.getByRole('button', { name: 'Что делать сейчас?' });
        await expect(sessionToggle).toHaveAttribute('aria-expanded', 'false');
        await expect(sessionSummary.locator('.active-session-summary__details')).toBeHidden();
        await captureSurface(page, `after-${theme}-${viewport.label}-compact.png`);
        await sessionToggle.click();
        await expect(sessionToggle).toHaveAttribute('aria-expanded', 'true');

        const guidance = page.locator('.active-session-summary .progression-guidance');
        const whySummary = guidance.getByText('Почему такой вес?', { exact: true });
        await expect(whySummary).toBeVisible();

        await captureSurface(page, `after-${theme}-${viewport.label}.png`);
        await rirSummary.click();
        await expect(rirDetails).toHaveAttribute('open', '');
        await expect(rirDetails.getByRole('link', { name: /Подробнее на сайте/ })).toHaveAttribute(
          'href',
          '/knowledge/training/repetitions-in-reserve',
        );
        await whySummary.click();
        await expect(guidance.locator('details')).toHaveAttribute('open', '');
        await expect(
          guidance.getByRole('link', { name: 'Подробнее о прогрессии' }),
        ).toHaveAttribute('href', '/knowledge/training/progressive-overload');
        await captureSurface(page, `after-${theme}-${viewport.label}-open.png`);

        await weight.fill('40');
        await reps.fill('8');
        await complete.click();
        await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
        await expectNoHorizontalOverflow(page);
        await captureSurface(page, `after-${theme}-${viewport.label}-rest.png`);
      } else {
        await expect(currentSet.locator('.active-workout-set__contextual-help')).toHaveCount(0);
        await captureSurface(page, `before-${theme}-${viewport.label}.png`);
      }
    });
  }
}

test('@critical Issue #998 preserves input order and keyboard disclosure controls', async ({
  page,
}) => {
  await preparePage(page, 'dark', VIEWPORTS[2]);
  const currentSet = await enterWorkout(page);
  const weight = currentSet.getByLabel(/^Вес,/);
  const reps = currentSet.getByRole('spinbutton', { name: /^Повторы,/ });
  const complete = currentSet.getByRole('button', { name: /^Завершить:/ });
  const rirDetails = currentSet.locator('.active-workout-set__contextual-help .contextual-help');
  const rirSummary = rirDetails.getByText('Что такое RIR?', { exact: true });

  await weight.fill('40');
  await reps.fill('8');
  await weight.focus();
  await page.keyboard.press('Tab');
  await expect(reps).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(complete).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(rirSummary).toBeFocused();

  await rirSummary.press('Enter');
  await expect(rirDetails).toHaveAttribute('open', '');
  await rirSummary.press('Escape');
  await expect(rirDetails).not.toHaveAttribute('open', '');
  await expect(rirSummary).toBeFocused();
  await rirSummary.press('Space');
  await expect(rirDetails).toHaveAttribute('open', '');
  await rirSummary.press('Space');
  await expect(rirDetails).not.toHaveAttribute('open', '');
  await expect(weight).toHaveValue('40');
  await expect(reps).toHaveValue('8');
});

test('@critical Issue #998 mocked TMA safe-area keeps the contextual action in the surface', async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 844 });
  await page.clock.setFixedTime(new Date(`${FIXED_DATE}T12:00:00+03:00`));
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await installTelegramHarness(page, {
    colorScheme: 'light',
    viewportHeight: 760,
    viewportStableHeight: 844,
    safeAreaInset: { top: 28, right: 2, bottom: 20, left: 2 },
    contentSafeAreaInset: { top: 44, right: 0, bottom: 16, left: 0 },
  });
  await installPlatformApi(page, {
    browserSession: false,
    fixedDate: FIXED_DATE,
    workoutStatus: 'in_progress',
    progressionOutcome: 'consider_progressing',
  });
  const currentSet = await enterWorkout(page);
  const rirSummary = currentSet
    .locator('.active-workout-set__contextual-help .contextual-help')
    .getByText('Что такое RIR?', { exact: true });
  await rirSummary.scrollIntoViewIfNeeded();
  await expect(rirSummary).toBeVisible();
  await expectNoHorizontalOverflow(page);
  const geometry = await rirSummary.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, right: rect.right, viewport: window.innerWidth };
  });
  expect(geometry.left).toBeGreaterThanOrEqual(-0.5);
  expect(geometry.right).toBeLessThanOrEqual(geometry.viewport + 0.5);
});

for (const theme of ['dark', 'light'] as const) {
  for (const viewport of [VIEWPORTS[2], VIEWPORTS[4]]) {
    test(`@critical Issue #998 program cycle help ${viewport.label}px ${theme}`, async ({
      page,
    }) => {
      await preparePage(page, theme, viewport, { programHistory: 'one' });
      await page.goto('/app?section=programs&view=manage&start=create');
      const builder = page.locator('.program-builder');
      await expect(builder).toBeVisible();
      const addDay = builder.getByRole('button', { name: 'Добавить день' });
      for (let day = 1; day < 8; day += 1) await addDay.click();

      const settings = builder.locator('details.program-builder-settings');
      await settings.locator(':scope > summary').click();
      const cycleHelp = settings.getByText('Как устроен цикл?', { exact: true });
      await expect(cycleHelp).toBeVisible();
      await expect(settings.locator('.contextual-help')).not.toHaveAttribute('open', '');
      await captureSurface(
        page,
        `after-program-${theme}-${viewport.label}.png`,
        '.program-builder-settings .program-builder-section:has(.contextual-help)',
      );
      await cycleHelp.click();
      await expect(settings.locator('.contextual-help')).toHaveAttribute('open', '');
      await expect(settings.getByText('Источник: нет ссылки.', { exact: true })).toBeVisible();
      await captureSurface(
        page,
        `after-program-${theme}-${viewport.label}-open.png`,
        '.program-builder-settings .program-builder-section:has(.contextual-help)',
      );
    });
  }
}
