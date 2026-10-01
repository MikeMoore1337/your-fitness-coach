import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { expectNoHorizontalOverflow, installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

const evidenceDir = resolve(
  process.env.YFC_TASK_EVIDENCE_DIR ?? '../.artifacts/tasks/516/evidence/screenshots',
);

const mealPhoto = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
);

const draft = {
  draft_id: 'photo-meal-visual-516',
  revision: 1,
  status: 'draft',
  expires_at: '2026-08-19T12:15:00Z',
  candidates: [
    {
      candidate_id: 'food-1',
      name: 'Курица с рисом',
      portion_amount: '250',
      portion_unit: 'g',
      portion_confidence: 'medium',
      identity_confidence: 'high',
      nutrition_confidence: 'medium',
      uncertainty_codes: ['portion_uncertain'],
      energy_kcal: '420',
      protein_g: '34',
      fat_g: '12',
      carbs_g: '38',
    },
  ],
  warnings: ['portion_uncertain', 'manual_review_required'],
  requires_user_review: true,
  source_photo_retained: false,
};

async function openPhotoMealReview(
  page: Page,
  { telegram, colorScheme }: { telegram: boolean; colorScheme: 'light' | 'dark' },
): Promise<void> {
  if (telegram) {
    await installTelegramHarness(page, {
      colorScheme,
      viewportHeight: 844,
      viewportStableHeight: 844,
    });
  }
  await installPlatformApi(page, {
    browserSession: !telegram,
    fixedDate: '2026-08-19',
  });
  await page.route('**/api/v1/nutrition/photo-meals*', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'POST' && path.endsWith('/photo-meals')) {
      await route.fulfill({ status: 201, json: draft });
      return;
    }
    if (request.method() === 'POST' && path.endsWith('/cancel')) {
      await route.fulfill({ status: 204, body: '' });
      return;
    }
    await route.continue();
  });

  await page.goto('/app?section=nutrition&date=2026-08-19');
  const breakfast = page.getByRole('region', { name: 'Завтрак' });
  await breakfast.getByRole('button', { name: /Добавить/ }).click();
  await page.getByRole('button', { name: 'По фото блюда' }).click();
  await expect(page.getByRole('heading', { name: 'Сфотографировать блюдо' })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: 'meal.png',
    mimeType: 'image/png',
    buffer: mealPhoto,
  });
  await page.getByRole('button', { name: 'Распознать приблизительно' }).click();
  await expect(page.getByRole('heading', { name: 'Проверьте оценку блюда' })).toBeVisible();
  await expect(page.getByText('Порции и калории не точны')).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Подтвердить и добавить в дневник' }),
  ).toBeVisible();
}

async function waitForVisualStability(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
  });
}

test('Task 516 owner visual checkpoint covers review-first photo meal states', async ({
  browser,
}) => {
  mkdirSync(evidenceDir, { recursive: true });
  const scenarios = [
    {
      name: 'task-516-desktop-light-review',
      viewport: { width: 1280, height: 900 },
      telegram: false,
      colorScheme: 'light' as const,
      surface: 'desktop',
    },
    {
      name: 'task-516-mobile-light-review',
      viewport: { width: 390, height: 844 },
      telegram: false,
      colorScheme: 'light' as const,
      surface: 'mobile-web',
    },
    {
      name: 'task-516-tma-dark-review',
      viewport: { width: 390, height: 844 },
      telegram: true,
      colorScheme: 'dark' as const,
      surface: 'mocked-tma',
    },
  ];
  const provenance: Array<Record<string, unknown>> = [];

  for (const scenario of scenarios) {
    const context = await browser.newContext({
      viewport: scenario.viewport,
      colorScheme: scenario.colorScheme,
    });
    const page = await context.newPage();
    try {
      await openPhotoMealReview(page, scenario);
      await expectNoHorizontalOverflow(page);
      await waitForVisualStability(page);
      const confirmButton = page.getByRole('button', {
        name: 'Подтвердить и добавить в дневник',
      });
      const confirmBox = await confirmButton.boundingBox();
      expect(confirmBox?.height).toBeGreaterThanOrEqual(44);
      expect(confirmBox?.x).toBeGreaterThanOrEqual(0);
      expect((confirmBox?.x ?? 0) + (confirmBox?.width ?? 0)).toBeLessThanOrEqual(
        scenario.viewport.width + 1,
      );

      const capture = async (state: string, suffix: string) => {
        const path = resolve(evidenceDir, `${scenario.name}-${suffix}.png`);
        await page.screenshot({ path, fullPage: false, animations: 'disabled' });
        const bytes = readFileSync(path);
        provenance.push({
          file: `${scenario.name}-${suffix}.png`,
          state,
          route: '/app?section=nutrition&date=2026-08-19',
          theme: scenario.colorScheme,
          viewport: scenario.viewport,
          surface: scenario.surface,
          fixture: 'installPlatformApi + mocked photo meal draft',
          source_photo_bytes: mealPhoto.length,
          screenshot_bytes: bytes.length,
          sha256: createHash('sha256').update(bytes).digest('hex'),
          real_telegram: false,
        });
      };
      await capture('review context', 'review-top');
      await confirmButton.scrollIntoViewIfNeeded();
      await waitForVisualStability(page);
      const actionBox = await confirmButton.boundingBox();
      expect(actionBox?.y).toBeGreaterThanOrEqual(0);
      expect((actionBox?.y ?? 0) + (actionBox?.height ?? 0)).toBeLessThanOrEqual(
        scenario.viewport.height + 1,
      );
      await capture('explicit confirmation action', 'review-actions');
    } finally {
      await context.close();
    }
  }

  writeFileSync(
    resolve(evidenceDir, 'task-516-visual-provenance.json'),
    JSON.stringify(
      { task_id: 516, generated_at: new Date().toISOString(), screenshots: provenance },
      null,
      2,
    ),
  );
});
