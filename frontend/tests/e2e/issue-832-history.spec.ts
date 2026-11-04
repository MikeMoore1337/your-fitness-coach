import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

for (const theme of ['dark', 'light'] as const) {
  test(`#832 общий журнал показывает результаты сторон ${theme}`, async ({ page, browserName }) => {
    test.setTimeout(60_000);
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    await installPlatformApi(page, { browserSession: true, progressState: 'populated' });
    await page.route('**/api/v1/workouts/history?*', (route) =>
      route.fulfill({
        json: [
          {
            id: 832,
            scheduled_date: '2026-10-30',
            title: 'Силовая база',
            status: 'completed',
            completed_sets: 1,
            volume_kg: 308,
            adaptations: [],
            rest_sessions: [],
            exercises: [
              {
                workout_exercise_id: 1001,
                exercise_id: 11,
                title: 'Тяга гантели в наклоне',
                prescribed_sets: 2,
                prescribed_reps: '8–10',
                sort_order: 1,
                side_sets: [
                  {
                    set_number: 1,
                    execution_mode: 'per_side',
                    is_completed: true,
                    sides: {
                      left: {
                        actual_weight: 18,
                        actual_reps: 10,
                        rir: '2',
                        reached_failure: false,
                        is_completed: true,
                      },
                      right: {
                        actual_weight: 16,
                        actual_reps: 8,
                        rir: '0',
                        reached_failure: true,
                        is_completed: true,
                      },
                    },
                  },
                  {
                    set_number: 2,
                    execution_mode: 'alternating',
                    first_side: 'right',
                    is_completed: false,
                    sides: {
                      left: null,
                      right: { actual_weight: 16, actual_reps: 8, is_completed: true },
                    },
                  },
                ],
              },
            ],
          },
        ],
      }),
    );
    await page.route('**/api/v1/workouts/history/summary', (route) =>
      route.fulfill({
        json: { workouts_completed: 1, completed_sets: 1, volume_kg: 308 },
      }),
    );
    await page.goto('/app?section=progress&progress_view=history');
    await expect(page.getByText(/Левая: 18 кг × 10 повт/)).toBeVisible();
    await expect(page.getByText(/Правая: 16 кг × 8 повт.*до отказа/)).toBeVisible();
    await expect(
      page.getByText(/Подход 2 · не завершён · поочерёдно · первая: правая/),
    ).toBeVisible();
    const widths = browserName === 'chromium' ? [320, 360, 393, 430, 1440] : [393];
    for (const width of widths) {
      await page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        ),
      ).toBeLessThanOrEqual(1);
      if (process.env.CAPTURE_832_AFTER === '1') {
        const directory = resolve(
          process.env.YFC_832_CAPTURE_DIR ??
            resolve(process.cwd(), '..', '.artifacts', 'tasks', '832', 'evidence', 'after'),
        );
        await mkdir(directory, { recursive: true });
        await page.locator('.workout-history-card').screenshot({
          path: resolve(directory, `${browserName}-${theme}-${width}-history-journal.png`),
          animations: 'disabled',
        });
      }
    }
  });
}
