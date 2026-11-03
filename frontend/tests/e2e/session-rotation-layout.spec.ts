import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test('rotation mode choices share the available width and remain operable', async ({
  page,
}, testInfo) => {
  test.setTimeout(90_000);
  await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
  await page.route('**/api/v1/programs/assigned/77/session-rotation**', async (route) => {
    await route.fulfill({
      json: {
        program_id: 77,
        mode: route.request().url().endsWith('/preview') ? 'rotation' : 'calendar',
        revision_number: 2,
        days: [
          { day_number: 1, title: 'Грудь и трицепс', from_template: false },
          { day_number: 2, title: 'Спина и бицепс', from_template: false },
        ],
        first_day_number: 1,
        future_reminders: 0,
        preview_token: 'layout-test',
      },
    });
  });

  for (const width of [320, 360, 393, 430, 1440]) {
    for (const theme of ['dark', 'light'] as const) {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.goto('/app?section=programs&view=manage&panel=operations');
      const panel = page.locator('.session-rotation-settings');
      const tabs = panel.getByRole('tablist', { name: 'Порядок тренировок' });
      const calendar = tabs.getByRole('tab', { name: 'По расписанию' });
      const rotation = tabs.getByRole('tab', { name: 'По очереди' });
      await expect(calendar).toHaveAttribute('aria-selected', 'true');
      const capture = async (state: string) => {
        if (process.env.YFC_CAPTURE_ROTATION_LAYOUT !== '1' || ![320, 393, 1440].includes(width))
          return;
        const path = `../.artifacts/tasks/1204/evidence/rotation-tabs-fix/${testInfo.project.name}-${theme}-${width}-${state}`;
        await panel.scrollIntoViewIfNeeded();
        await page.screenshot({ path: `${path}-screen.png`, animations: 'disabled' });
        const hiddenDock = await page.addStyleTag({
          content: '#appBottomNav { visibility: hidden !important; }',
        });
        await panel.screenshot({
          path: `${path}-detail.png`,
          animations: 'disabled',
        });
        await hiddenDock.evaluate((element) => element.parentNode?.removeChild(element));
      };

      const geometry = await tabs.evaluate((element) => {
        const style = getComputedStyle(element);
        const [first, second] = Array.from(element.querySelectorAll<HTMLElement>('[role="tab"]'));
        if (!first || !second) throw new Error('Expected two rotation mode choices');
        const widths: [number, number] = [
          first.getBoundingClientRect().width,
          second.getBoundingClientRect().width,
        ];
        return {
          widths,
          heights: [first.getBoundingClientRect().height, second.getBoundingClientRect().height],
          available:
            element.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
          gap: parseFloat(style.columnGap),
          clipped: [first, second].some((tab) => tab.scrollWidth > tab.clientWidth + 1),
          lines: [first, second].map((tab) => {
            const range = document.createRange();
            range.selectNodeContents(tab);
            return range.getClientRects().length;
          }),
        };
      });
      expect(Math.abs(geometry.widths[0] - geometry.widths[1])).toBeLessThanOrEqual(1);
      expect(
        Math.abs(geometry.available - geometry.widths[0] - geometry.widths[1] - geometry.gap),
      ).toBeLessThanOrEqual(1);
      expect(Math.min(...geometry.heights)).toBeGreaterThanOrEqual(44);
      expect(geometry.clipped).toBe(false);
      expect(geometry.lines).toEqual([1, 1]);
      await expectNoHorizontalOverflow(page);

      await capture('calendar');
      await calendar.focus();
      await calendar.press('ArrowRight');
      await expect(rotation).toHaveAttribute('aria-selected', 'true');
      await expect(rotation).toBeFocused();
      const selectedWidths = await tabs
        .locator('[role="tab"]')
        .evaluateAll((elements) =>
          elements.map((element) => element.getBoundingClientRect().width),
        );
      expect(selectedWidths).toHaveLength(2);
      expect(Math.abs(selectedWidths[0]! - selectedWidths[1]!)).toBeLessThanOrEqual(1);
      await panel.getByLabel('С какой тренировки начать?').selectOption('1');
      await panel.getByRole('button', { name: 'Проверить изменения' }).click();
      await expect(panel.getByText('Проверьте изменения')).toBeVisible();
      await capture('preview');
    }
  }
});
