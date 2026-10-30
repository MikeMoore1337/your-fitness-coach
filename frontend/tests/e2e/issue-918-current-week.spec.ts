import { expect, test } from '@playwright/test';
import type { Workout } from '../../src/shared/api/types';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

for (const theme of ['dark', 'light'] as const) {
  for (const width of [320, 360, 393, 430, 1440]) {
    test(`тип текущей недели и прогрессия ${theme} ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 1440 ? 1000 : 852 });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, {
        browserSession: true,
        workoutStatus: 'in_progress',
        progressionOutcome: 'consider_progressing',
      });
      await page.goto('/app?section=today');
      const workout = await page.evaluate(
        async () => (await (await fetch('/api/v1/workouts/today')).json()) as Workout,
      );
      const exercise = workout.exercises[0]!;
      const guidance = exercise.progression_guidance!;
      await page.route('**/api/v1/workouts/today', (route) =>
        route.fulfill({
          json: {
            ...workout,
            week_number: 7,
            source_cycle_week: 1,
            cycle_iteration: 3,
            week_type: 'heavy',
            week_type_known: true,
            exercises: [
              {
                ...exercise,
                progression_guidance: {
                  ...guidance,
                  ruleset_version: 'progression-guidance-v3',
                  evidence: { ...guidance.evidence, week_type: 'heavy' },
                },
              },
            ],
          },
        }),
      );
      await page.goto('/app?section=today');
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
      const hero = page.locator('.active-workout-hero');
      await expect(hero.getByText('Неделя 7 · Тяжёлая неделя')).toBeVisible();
      const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
      await summary.getByRole('button', { name: 'Что делать сейчас?' }).click();
      await expect(summary.locator('.progression-guidance')).toContainText('Тяжёлая неделя');
      await expectNoHorizontalOverflow(page);
      if (process.env.YFC_CAPTURE_918) {
        await hero.screenshot({
          path: `../docs/ux/issue-918-after/${testInfo.project.name}-${theme}-${width}-current-week.png`,
        });
        await page
          .locator('.active-workout-exercise')
          .first()
          .screenshot({
            path: `../docs/ux/issue-918-after/${testInfo.project.name}-${theme}-${width}-current-progression.png`,
          });
      }
    });
  }
}
