import path from 'node:path';
import { mkdirSync, writeFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { openDetailsByHeading as openCard } from './fixtures/locators';
import { installPlatformApi } from './fixtures/platform-api';
import { previewTemplates } from './fixtures/program-preview';

test.use({ serviceWorkers: 'block' });

const WIDTHS = [320, 360, 393, 430, 1440];
const THEMES = ['dark', 'light'] as const;

function readyTemplates(count: number) {
  const seed = previewTemplates()[0]!;
  return Array.from({ length: count }, (_, index) => ({
    ...seed,
    id: 12300 + index,
    key: `issue-1230-${index}`,
    title:
      index === count - 1
        ? 'Готовый шаблон с очень длинным названием для проверки переноса текста и границ карточки'
        : `Готовый шаблон ${index + 1}`,
    owner_user_id: null,
    is_active_for_current_user: false,
    is_assigned_to_current_user: false,
    can_edit: false,
    assigned_by_user_id: null,
    assigned_by_full_name: null,
  }));
}

test.describe('Issue #1230: ready-template separators', () => {
  for (const count of [1, 2, 16]) {
    test(`${count} ready templates keep the card surface and actions`, async ({
      page,
    }, testInfo) => {
      const evidenceDir = process.env.TEMPLATE_SEPARATORS_EVIDENCE_DIR;
      const snapshots: unknown[] = [];
      await installPlatformApi(page, { activeProgram: false });
      await page.route('**/api/v1/programs/templates/mine', (route) =>
        route.fulfill({ json: readyTemplates(count) }),
      );
      await page.route('**/api/v1/programs/templates/hidden', (route) =>
        route.fulfill({ json: [] }),
      );

      await page.goto('/app?section=programs&view=manage');
      await page.getByRole('button', { name: 'Клиент', exact: true }).click();
      const library = await openCard(page, 'Программы и шаблоны');
      const group = library.locator('.program-library__group').filter({
        has: page.getByRole('heading', { name: 'Готовые шаблоны', exact: true }),
      });
      const grid = group.locator('.program-template-grid');
      const cards = grid.locator('.program-template-card');
      await expect(cards).toHaveCount(count);
      const card = cards.first();
      await expect(card.getByRole('button', { name: 'Настроить копию' })).toBeVisible();
      await expect(card.getByRole('button', { name: 'Запустить' })).toBeVisible();
      await expect(card.getByRole('button', { name: /^Посмотреть шаблон «/ })).toBeVisible();
      await expect
        .poll(async () => card.evaluate((element) => getComputedStyle(element).borderTopWidth))
        .toBe('1px');
      const dangerMenu = card.locator('details.program-danger-menu');
      const otherActions = dangerMenu.locator(':scope > summary');
      await expect(otherActions).toBeVisible();
      await otherActions.focus();
      await otherActions.press('Space');
      await expect(dangerMenu).toHaveAttribute('open', '');
      await expect(card.getByRole('button', { name: 'Скрыть шаблон' })).toBeVisible();
      await otherActions.press('Space');
      await expect(dangerMenu).not.toHaveAttribute('open', '');

      await library.locator(':scope > summary').click();
      await expect(grid).toBeHidden();
      await library.locator(':scope > summary').click();
      await expect(grid).toBeVisible();

      for (const theme of THEMES) {
        await page.emulateMedia({ colorScheme: theme });
        await page.locator('html').evaluate((element, colorScheme) => {
          element.setAttribute('data-color-scheme', colorScheme);
        }, theme);
        for (const width of WIDTHS) {
          await page.setViewportSize({ width, height: 900 });
          const snapshot = await grid.evaluate((element) => {
            const gridStyle = getComputedStyle(element);
            const heading = element
              .closest('.program-library__group')
              ?.querySelector(':scope > div:first-child');
            const headingStyle = heading ? getComputedStyle(heading) : null;
            const actions = element.querySelector<HTMLElement>('.program-template-card__actions');
            const dangerMenu = element.querySelector<HTMLElement>('.program-danger-menu');
            const cards = Array.from(
              element.querySelectorAll<HTMLElement>('.program-template-card'),
            );
            return {
              grid: {
                borderTopWidth: gridStyle.borderTopWidth,
                borderTopStyle: gridStyle.borderTopStyle,
                gap: gridStyle.gap,
                rowGap: gridStyle.rowGap,
              },
              headingBorderBottom: headingStyle?.borderBottom ?? null,
              actionsBorder: actions
                ? {
                    top: getComputedStyle(actions).borderTopWidth,
                    bottom: getComputedStyle(actions).borderBottomWidth,
                  }
                : null,
              dangerMenuBorder: dangerMenu
                ? {
                    top: getComputedStyle(dangerMenu).borderTopWidth,
                    bottom: getComputedStyle(dangerMenu).borderBottomWidth,
                  }
                : null,
              cards: cards.map((card) => {
                const style = getComputedStyle(card);
                return {
                  borderTopWidth: style.borderTopWidth,
                  borderRightWidth: style.borderRightWidth,
                  borderBottomWidth: style.borderBottomWidth,
                  borderLeftWidth: style.borderLeftWidth,
                  borderTopStyle: style.borderTopStyle,
                  borderRightStyle: style.borderRightStyle,
                  borderBottomStyle: style.borderBottomStyle,
                  borderLeftStyle: style.borderLeftStyle,
                  borderRadius: style.borderRadius,
                  paddingLeft: style.paddingLeft,
                  paddingRight: style.paddingRight,
                };
              }),
              overflow: document.documentElement.scrollWidth - window.innerWidth,
            };
          });
          snapshots.push({ theme, width, snapshot });
          expect(snapshot.grid.borderTopWidth).toBe('0px');
          expect(snapshot.grid.borderTopStyle).toBe('none');
          expect(Number.parseFloat(snapshot.grid.gap)).toBeGreaterThan(0);
          expect(snapshot.actionsBorder).toEqual({ top: '0px', bottom: '0px' });
          expect(snapshot.dangerMenuBorder).toEqual({ top: '0px', bottom: '0px' });
          expect(snapshot.cards).toHaveLength(count);
          for (const card of snapshot.cards) {
            expect(card.borderTopWidth).toBe('1px');
            expect(card.borderRightWidth).toBe('1px');
            expect(card.borderBottomWidth).toBe('1px');
            expect(card.borderLeftWidth).toBe('1px');
            expect(card.borderTopStyle).toBe('solid');
            expect(card.borderRightStyle).toBe('solid');
            expect(card.borderBottomStyle).toBe('solid');
            expect(card.borderLeftStyle).toBe('solid');
            expect(card.borderRadius).not.toBe('0px');
            expect(card.paddingLeft).not.toBe('0px');
            expect(card.paddingRight).not.toBe('0px');
          }
          expect(snapshot.overflow).toBe(0);
          if (evidenceDir && count === 16 && (width === 393 || width === 1440)) {
            const directory = path.join(evidenceDir, testInfo.project.name);
            mkdirSync(directory, { recursive: true });
            await group.screenshot({
              path: path.join(directory, `${count}-${theme}-${width}.png`),
              animations: 'disabled',
              scale: 'css',
            });
          }
        }
      }

      await page.setViewportSize({ width: 393, height: 900 });
      await cards.last().scrollIntoViewIfNeeded();
      await expect(cards.last()).toBeVisible();
      await expect(page.locator('#appBottomNav')).toBeVisible();

      if (evidenceDir) {
        mkdirSync(evidenceDir, { recursive: true });
        writeFileSync(
          path.join(evidenceDir, `${testInfo.project.name}-${count}-computed.json`),
          JSON.stringify(snapshots, null, 2),
        );
      }
    });
  }
});
