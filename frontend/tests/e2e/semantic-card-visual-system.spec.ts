import { expect, test, type Page } from '@playwright/test';
import { nutritionDaySummary } from './fixtures/locators';
import { installPlatformApi } from './fixtures/platform-api';
import {
  expectDockWithinViewport,
  expectElementsWithinHorizontalViewport,
  expectNoHorizontalOverflow,
  expectTouchTargets,
  installTelegramHarness,
} from './fixtures/mobile-tma';

const captureTask123Proofs =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.YFC_CAPTURE_TASK_123_PROOFS === '1';

async function openSurface(page: Page, route: string, theme: 'light' | 'dark', tma = false) {
  await page.addInitScript((selectedTheme) => {
    localStorage.setItem('app-theme', selectedTheme);
  }, theme);
  if (tma) await installTelegramHarness(page, { colorScheme: theme });
  await installPlatformApi(page, {
    browserSession: !tma,
    measurementHistory: 'many',
    programHistory: route.includes('section=programs') ? 'many' : undefined,
  });
  await page.goto(route);
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
  await expect(page.locator('.app-shell')).toBeVisible();
}

async function waitForSemanticSurface(page: Page, route: string) {
  if (route.includes('section=programs')) {
    await expect(page.getByRole('heading', { name: 'Программы и шаблоны' })).toBeVisible();
    await expect(page.locator('[data-semantic-family="training"]').first()).toBeVisible();
    await expect(page.locator('[role="status"][aria-busy="true"]')).toHaveCount(0);
  } else if (route.includes('section=nutrition')) {
    await expect(page.getByRole('heading', { name: 'Питание', exact: true })).toBeVisible();
    await expect(page.locator('[data-semantic-family="nutrition"]').first()).toBeVisible();
  } else if (route.includes('section=progress')) {
    await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();
    await expect(page.locator('[data-semantic-family="progress"]').first()).toBeVisible();
  } else if (route.includes('section=profile')) {
    await expect(page.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
  } else {
    await expect(page.locator('[data-semantic-family="training"]').first()).toBeVisible();
  }
}

test('semantic families, compact actions and disclosure states share one accessible contract', async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
  });
  const page = await context.newPage();
  await openSurface(page, '/app?section=today', 'light');

  for (const family of ['training', 'progress'] as const) {
    await expect(page.locator(`[data-semantic-family="${family}"]`).first()).toBeVisible();
  }
  await expect(page.getByRole('region', { name: 'Питание на сегодня' })).toBeVisible();
  for (const action of await page.locator('.semantic-card__action > :is(a, button)').all()) {
    const box = await action.boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
  }
  await expectDockWithinViewport(page);
  await expectElementsWithinHorizontalViewport(page, '[data-semantic-family]');
  await expectTouchTargets(page.locator('.semantic-card__action > :is(a, button)'));
  await expectNoHorizontalOverflow(page);

  const progressCard = page.locator('[data-semantic-family="progress"]').first();
  await progressCard.getByRole('link', { name: 'Открыть' }).click();
  await expect(page).toHaveURL(/section=progress/);
  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();
  await expect(
    page.locator('[data-semantic-family="progress"][data-card-variant="summary"]'),
  ).toBeVisible();

  await page.goto('/app?section=profile');
  const disclosure = page.locator('#profile-notifications');
  const summary = disclosure.locator(':scope > summary');
  await expect(disclosure).toHaveAttribute('data-semantic-family', 'neutral');
  await expect(summary).toHaveAttribute('aria-expanded', 'false');
  await summary.focus();
  await summary.press('Enter');
  await expect(summary).toHaveAttribute('aria-expanded', 'true');
  await expect(disclosure).toHaveAttribute('open');
  await expect(disclosure.locator(':scope > .card-disclosure__body')).toBeVisible();

  await page.emulateMedia({ reducedMotion: 'reduce' });
  const reducedMotion = await disclosure.evaluate((element) => {
    const body = element.querySelector<HTMLElement>(':scope > .card-disclosure__body')!;
    const style = getComputedStyle(body);
    return { animationName: style.animationName, transitionDuration: style.transitionDuration };
  });
  expect(reducedMotion.animationName).toBe('none');
  expect(Number.parseFloat(reducedMotion.transitionDuration)).toBeLessThanOrEqual(0.00001);
  await expectNoHorizontalOverflow(page);

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 430, height: 932 },
    { width: 768, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(disclosure).toBeVisible();
    await expectNoHorizontalOverflow(page);
  }
  await context.close();
});

test('hover and focus use the restrained brand and neutral palette', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await openSurface(page, '/app?section=today', 'dark');

  const nutritionCard = page.getByRole('region', { name: 'Питание на сегодня' });
  const action = nutritionCard.getByRole('link', { name: '+ Вода', exact: true });
  await nutritionCard.hover();
  await action.focus();
  await expect(action).toBeFocused();
  await expect(action).toHaveCSS('outline-style', 'solid');
  await expect(action).toHaveCSS('outline-width', '3px');

  const familyLines = await page
    .locator(
      '[data-semantic-family="training"], [data-semantic-family="nutrition"], [data-semantic-family="progress"]',
    )
    .evaluateAll((cards) =>
      cards
        .slice(0, 3)
        .map((card) => getComputedStyle(card).getPropertyValue('--semantic-line').trim()),
    );
  expect(familyLines.length).toBeGreaterThanOrEqual(2);
  expect(familyLines[0]).not.toBe(familyLines[1]);
  await context.close();
});

test('shared card effects preserve summary flow and viewport modals', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await openSurface(page, '/app?section=nutrition', 'light');
  await waitForSemanticSurface(page, '/app?section=nutrition');

  await expect(nutritionDaySummary(page)).toHaveCount(1);
  await expect(nutritionDaySummary(page)).toBeVisible();

  await page.goto('/app?section=profile');
  await expect(page.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
  const securityCard = page.locator('#profile-security');
  await securityCard.locator(':scope > summary').click();
  await securityCard.hover();
  await securityCard.getByRole('button', { name: 'Удалить аккаунт', exact: true }).click();

  const dialog = page.getByRole('dialog', {
    name: 'Удалить аккаунт без возможности восстановления?',
  });
  await expect(dialog).toBeVisible();
  const modalContract = await dialog.evaluate((dialogElement) => {
    const dialogStyle = getComputedStyle(dialogElement);
    const rect = dialogElement.getBoundingClientRect();
    return {
      dialogPosition: dialogStyle.position,
      height: rect.height,
      parent: dialogElement.parentElement?.tagName,
      width: rect.width,
    };
  });
  expect(modalContract).toEqual({
    dialogPosition: 'fixed',
    height: 900,
    parent: 'BODY',
    width: 1440,
  });
  await context.close();
});

test('captures paired Light and Dark evidence for representative Web and mocked TMA states', async ({
  browser,
}) => {
  test.skip(!captureTask123Proofs, 'Task 123 owner-checkpoint capture is opt-in');

  const surfaces = [
    { label: 'mobile-web-today-390x844', route: '/app?section=today', width: 390, height: 844 },
    {
      label: 'desktop-program-1440x900',
      route: '/app?section=programs',
      width: 1440,
      height: 900,
    },
    {
      label: 'desktop-nutrition-1440x900',
      route: '/app?section=nutrition',
      width: 1440,
      height: 900,
    },
    {
      label: 'desktop-progress-1440x900',
      route: '/app?section=progress',
      width: 1440,
      height: 900,
    },
    {
      label: 'mobile-profile-expanded-430x932',
      route: '/app?section=profile',
      width: 430,
      height: 932,
      expand: '#profile-notifications',
    },
  ] as const;

  for (const surface of surfaces) {
    for (const theme of ['light', 'dark'] as const) {
      const context = await browser.newContext({
        viewport: { width: surface.width, height: surface.height },
        hasTouch: surface.width < 900,
      });
      const page = await context.newPage();
      await openSurface(page, surface.route, theme);
      await waitForSemanticSurface(page, surface.route);
      if ('expand' in surface) {
        await page.screenshot({
          path: `../.artifacts/screenshots/task-123/mobile-profile-collapsed-430x932-${theme}.png`,
          fullPage: true,
        });
        await page.locator(surface.expand).locator(':scope > summary').click();
        await expect(page.locator(surface.expand)).toHaveAttribute('open');
      }
      await expectNoHorizontalOverflow(page);
      await page.screenshot({
        path: `../.artifacts/screenshots/task-123/${surface.label}-${theme}.png`,
        fullPage: true,
      });
      await context.close();
    }
  }

  for (const theme of ['light', 'dark'] as const) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await openSurface(page, '/app?section=today', theme);
    await waitForSemanticSurface(page, '/app?section=today');
    const nutritionCard = page.locator('[data-semantic-family="nutrition"]').first();
    const action = nutritionCard.getByRole('link', { name: 'Добавить' });
    await action.focus();
    await expect(action).toBeFocused();
    await nutritionCard.screenshot({
      path: `../.artifacts/screenshots/task-123/desktop-today-focus-${theme}.png`,
    });
    const box = await action.boundingBox();
    if (!box) throw new Error('Nutrition quick action is not measurable');
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await nutritionCard.screenshot({
      path: `../.artifacts/screenshots/task-123/desktop-today-pressed-${theme}.png`,
    });
    await page.mouse.up();
    await context.close();
  }

  for (const theme of ['light', 'dark'] as const) {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      hasTouch: true,
    });
    const page = await context.newPage();
    await openSurface(page, '/app?section=today', theme, true);
    await waitForSemanticSurface(page, '/app?section=today');
    await expectNoHorizontalOverflow(page);
    await page.screenshot({
      path: `../.artifacts/screenshots/task-123/mock-tma-today-390x844-${theme}.png`,
      fullPage: true,
    });
    await context.close();
  }
});

test('captures the five shared family mappings side by side', async ({ browser }) => {
  test.skip(!captureTask123Proofs, 'Task 123 family-board capture is opt-in');

  for (const theme of ['light', 'dark'] as const) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await openSurface(page, '/app?section=today', theme);
    await page.evaluate(() => {
      const families = [
        ['training', 'Тренировка', 'Силовая база · сегодня в 18:30'],
        ['nutrition', 'Питание', '1 640 из 2 100 ккал'],
        ['progress', 'Прогресс', '7 из 8 тренировок · 1 новый рекорд'],
        ['wellbeing', 'Самочувствие', 'Спокойный будущий summary contract'],
        ['neutral', 'Система', 'Настройки и служебные разделы'],
      ];
      const board = document.createElement('section');
      board.className = 'task-123-family-board';
      board.setAttribute('aria-label', 'Semantic card families');
      board.style.cssText =
        'display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:18px;padding:28px;background:var(--v2-canvas);';
      for (const [family, title, summary] of families) {
        const card = document.createElement('article');
        card.className = `semantic-card semantic-card--compact semantic-card--summary semantic-card--${family}`;
        card.dataset.semanticFamily = family;
        card.innerHTML = `<div class="semantic-card__copy"><span class="semantic-card__eyebrow">${family}</span><h2>${title}</h2><div class="semantic-card__summary">${summary}</div></div>`;
        board.append(card);
      }
      document.body.replaceChildren(board);
    });
    const board = page.locator('.task-123-family-board');
    await expect(board.locator('[data-semantic-family]')).toHaveCount(5);
    await board.screenshot({
      path: `../.artifacts/screenshots/task-123/semantic-family-board-1440x900-${theme}.png`,
    });
    await context.close();
  }
});
