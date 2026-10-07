import { expect, test, type Page } from '@playwright/test';
import { resolve } from 'node:path';
import { installPlatformApi } from './fixtures/platform-api';
import {
  expectNoHorizontalOverflow,
  expectTouchTargets,
  installTelegramHarness,
} from './fixtures/mobile-tma';

const FIXED_DATE = '2026-09-07';
const EVIDENCE_DIR = process.env.TASK_543_EVIDENCE_DIR;

async function captureEvidence(page: Page, name: string) {
  if (!EVIDENCE_DIR) return;
  await page.screenshot({ path: resolve(EVIDENCE_DIR, name), fullPage: true });
}

test('Task 543 keeps one Today action for the current rest-day state', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: FIXED_DATE,
    workoutStatus: 'none',
  });
  await page.goto('/app?section=today');

  await expect(page.getByRole('heading', { name: 'Сегодня без тренировки' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Добавить питание', exact: true })).toHaveCount(1);
  await expect(page.getByRole('link', { name: 'Открыть дневник питания' })).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
  await captureEvidence(page, 'today-rest-desktop-light-1440.png');

  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  await expectTouchTargets(page.locator('.today-workout-actions > :visible'));
  await captureEvidence(page, 'today-rest-mobile-light-390.png');
});

test('Task 543 keeps the repeat meal as Nutrition primary in mocked dark TMA', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await installTelegramHarness(page, {
    colorScheme: 'dark',
    viewportHeight: 760,
    viewportStableHeight: 844,
  });
  await installPlatformApi(page, {
    fixedDate: FIXED_DATE,
    nutritionRepeatCandidate: true,
  });
  await page.goto(`/app?section=nutrition&date=${FIXED_DATE}`);

  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  const repeat = page.getByTestId('nutrition-repeat-default');
  const addProduct = page.getByTestId('nutrition-add-product');
  await expect(repeat).toBeVisible();
  await expect(repeat).toHaveClass(/ui-button--primary/);
  await expect(addProduct).toHaveClass(/ui-button--secondary/);
  await expectNoHorizontalOverflow(page);
  await expectTouchTargets(
    page.locator(
      '.nutrition-diary__intro-actions button:visible, .nutrition-repeat-default button:visible',
    ),
  );
  await captureEvidence(page, 'nutrition-repeat-mobile-dark-tma-390.png');
});

test('Task 543 keeps one Coach Today clients destination', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await installTelegramHarness(page, {
    colorScheme: 'dark',
    viewportHeight: 760,
    viewportStableHeight: 844,
  });
  await installPlatformApi(page, { fixedDate: FIXED_DATE, trainerActive: true });
  await page.route('**/api/v1/coach/inbox**', async (route) => {
    await route.fulfill({
      json: {
        date: FIXED_DATE,
        timezone: 'Europe/Moscow',
        total: 1,
        counts: {
          attention: 1,
          pending_reviews: 1,
          tasks: 0,
          sessions: 0,
          packages: 0,
          payments: 0,
        },
        generated_at: `${FIXED_DATE}T12:00:00Z`,
        items: [
          {
            key: 'attention:weekly_check_in:11:44',
            kind: 'attention',
            client: { id: 11, name: 'Анна Петрова' },
            title: 'Новый недельный итог',
            reason: 'Клиент заполнил недельный итог.',
            source_kind: 'weekly_check_in',
            source_id: 44,
            action: 'review_check_in',
            destination: '/coach?client_id=11&focus=weekly_check_in',
            created_at: `${FIXED_DATE}T11:00:00Z`,
            priority: 'urgent',
            due_at: null,
            evidence: [],
          },
        ],
      },
    });
  });
  await page.goto('/coach');

  await expect(page.getByRole('heading', { name: 'Что требует действия?' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Открыть клиентов', exact: true })).toHaveCount(0);
  const clientsCta = page.getByRole('button', { name: /Открыть список клиентов/ });
  await expect(clientsCta).toHaveCount(1);
  await expect(clientsCta).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expectTouchTargets(clientsCta);
  await captureEvidence(page, 'coach-today-mobile-dark-tma-390.png');
});
