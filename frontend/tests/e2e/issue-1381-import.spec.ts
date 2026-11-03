import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { installTelegramHarness, TelegramHarness } from './fixtures/mobile-tma';

for (const surface of ['pwa', 'telegram'] as const) {
  test(`#1381 ${surface}: расписание доступно после прокрутки и при уменьшении окна`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.clock.setFixedTime(new Date('2026-11-03T09:00:00Z'));
    if (surface === 'telegram') {
      await installTelegramHarness(page, {
        viewportHeight: 844,
        viewportStableHeight: 844,
        safeAreaInset: { top: 28, right: 2, bottom: 20, left: 2 },
        contentSafeAreaInset: { top: 44, right: 0, bottom: 16, left: 0 },
      });
    } else {
      await page.addInitScript(() => {
        const native = window.matchMedia.bind(window);
        window.matchMedia = (query) => {
          const value = native(query);
          if (query === '(display-mode: standalone)')
            Object.defineProperty(value, 'matches', { value: true });
          return value;
        };
      });
    }
    await installPlatformApi(page, {
      browserSession: surface === 'pwa',
      activeProgram: false,
      fixedDate: '2026-11-03',
    });
    await page.route('**/api/v1/programs/imports/targets', (route) => route.fulfill({ json: [] }));
    await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: [] }));
    await page.route('**/api/v1/programs/imports', (route) =>
      route.fulfill({
        json: {
          id: 'synthetic-1381',
          status: 'pending',
          source_format: 'xlsx',
          schema_version: 1,
          parser_version: 'synthetic',
          layout_version: 'weekly-matrix-v1',
          draft_version: 1,
          duration_weeks: 3,
          assignment_duration_weeks: 16,
          repeat: true,
          week_types: [null, null, null],
          expires_at: '2030-01-01T00:00:00Z',
          program_title: 'Силовая программа',
          goal: 'maintenance',
          level: 'intermediate',
          provenance: { provenance_type: 'CUSTOM' },
          rows: [1, 2, 3, 4].map((day) => ({
            row_number: day + 2,
            week_number: 1,
            day_number: day,
            day_title: `День ${day}`,
            exercise_name: 'Тестовое упражнение',
            metric_type: 'strength',
            prescribed_sets: 3,
            prescribed_reps: '8',
            rest_seconds: 90,
            resolved_exercise_id: day,
            resolved_exercise_title: 'Тестовое упражнение',
            match_status: 'matched',
            match_type: 'manual',
            candidates: [],
            issues: [],
          })),
          issues: [],
          summary: {
            row_count: 4,
            cell_count: 24,
            matched_row_count: 4,
            unresolved_row_count: 0,
            blocking_issue_count: 0,
            warning_count: 0,
          },
        },
      }),
    );
    await page.goto('/app?section=programs&view=manage&start=create');
    await page.getByLabel('Загрузить документ программы').setInputFiles({
      name: 'synthetic.xlsx',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('synthetic'),
    });
    await page.getByRole('button', { name: 'Сохранить и назначить' }).click();
    const dialog = page.getByRole('dialog', { name: 'Силовая программа' });
    await expect(dialog).toBeVisible();
    await expect
      .poll(async () => (await dialog.locator('.assignment-modal').boundingBox())?.y)
      .toBeGreaterThanOrEqual(surface === 'telegram' ? 44 : 0);
    if (surface === 'telegram') {
      await new TelegramHarness(page).setViewport(520, 844, false);
    } else {
      expect(await page.evaluate(() => matchMedia('(display-mode: standalone)').matches)).toBe(
        true,
      );
      await page.setViewportSize({ width: 393, height: 520 });
    }
    await expect
      .poll(() =>
        page.evaluate(() =>
          getComputedStyle(document.documentElement)
            .getPropertyValue('--yfc-viewport-height')
            .trim(),
        ),
      )
      .toBe('520px');
    const panel = dialog.locator('.assignment-modal');
    await expect
      .poll(async () => {
        const box = await panel.boundingBox();
        return box ? box.y + box.height : Infinity;
      })
      .toBeLessThanOrEqual(surface === 'telegram' ? 500 : 520);
    const action = dialog.getByRole('button', { name: 'Сохранить и назначить' });
    await action.scrollIntoViewIfNeeded();
    const actionBox = await action.boundingBox();
    expect(actionBox && actionBox.y >= 0 && actionBox.y + actionBox.height <= 520).toBe(true);
    await page.keyboard.press('Tab');
    await expect(dialog.locator(':focus')).toHaveCount(1);
    if (surface === 'telegram') await new TelegramHarness(page).clickBack();
    else await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
  });
}
