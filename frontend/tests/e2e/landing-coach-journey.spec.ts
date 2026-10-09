import { expect, test } from '@playwright/test';

for (const theme of ['light', 'dark'] as const)
  for (const width of [320, 390, 430, 1440])
    test(`six synthetic coach chapters ${theme} ${width}`, async ({ page }) => {
      const writes: string[] = [];
      page.on('request', (request) => {
        if (request.url().includes('/api/') && request.method() !== 'GET')
          writes.push(`${request.method()} ${request.url()}`);
      });
      await page.setViewportSize({ width, height: width < 700 ? 844 : 1000 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await page.goto('/for-trainers');
      await expect(page.locator('.ref-hero h1')).toBeVisible();
      const ids = ['connect', 'program', 'facts', 'review', 'decision', 'followup'];
      const positions: number[] = [];
      for (const id of ids) {
        const chapter = page.locator(`#coach-${id}`);
        await expect(chapter).toHaveCount(1);
        await chapter.scrollIntoViewIfNeeded();
        positions.push(
          await chapter.evaluate((element) => element.getBoundingClientRect().top + scrollY),
        );
        expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBe(
          0,
        );
      }
      expect(positions).toEqual([...positions].sort((a, b) => a - b));
      await expect(page.locator('#coach-work')).toHaveCount(1);
      await expect(page.locator('.strength-scene, #training, #nutrition, #progress')).toHaveCount(
        0,
      );

      const connect = page.locator('#coach-connect');
      await connect.getByRole('button', { name: 'Показать принятое приглашение' }).click();
      await expect(
        connect.getByRole('button', { name: 'Связь подтверждена в примере' }),
      ).toBeDisabled();
      const program = page.locator('#coach-program');
      await expect(
        program.getByRole('button', { name: 'Показать назначение программы' }),
      ).toBeEnabled();
      await program.getByRole('button', { name: 'Версия 2', exact: true }).click();
      await expect(program.getByRole('button', { name: 'Версия 2', exact: true })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
      await program.getByRole('button', { name: 'Показать назначение программы' }).click();
      await expect(program.getByRole('status')).toContainText('Версия 2 → программа Алексея');
      await expect(program.getByRole('button', { name: 'Версия 1', exact: true })).toBeDisabled();

      const facts = page.locator('#coach-facts');
      await facts.getByRole('button', { name: 'Открыть обзор клиента' }).click();
      await expect(facts.getByText('Client 360 / обзор клиента', { exact: true })).toBeVisible();
      await expect(facts.getByText('2 тренировки', { exact: true })).toBeVisible();
      await facts.getByRole('button', { name: 'Вернуться во входящие' }).click();
      await expect(facts.getByRole('button', { name: 'Открыть обзор клиента' })).toBeVisible();

      const review = page.locator('#coach-review');
      await review.getByRole('button', { name: 'Изменения', exact: true }).click();
      await expect(review.getByRole('heading', { name: 'Без поспешного вывода' })).toBeVisible();
      await review.getByRole('button', { name: 'Отметить итог проверенным' }).click();
      await expect(review.getByRole('status')).toContainText('Программа не изменилась');

      const decision = page.locator('#coach-decision');
      await expect(decision.getByRole('button', { name: /Подтвердить для/ })).toHaveCount(0);
      await decision.getByLabel('Марина', { exact: true }).uncheck();
      await decision.getByLabel('Алексей', { exact: true }).uncheck();
      await expect(
        decision.getByRole('button', { name: 'Посмотреть изменения по клиентам' }),
      ).toBeDisabled();
      await decision.getByLabel('Алексей', { exact: true }).check();
      await decision.getByRole('button', { name: 'Посмотреть изменения по клиентам' }).click();
      await expect(decision.locator('.ref-list li')).toHaveCount(1);
      await expect(decision.locator('.ref-list')).toContainText('Алексей');
      await expect(
        decision.getByRole('button', { name: 'Подтвердить для 1 клиента', exact: true }),
      ).toBeEnabled();
      // A changed recipient set invalidates the previous preview.
      await decision.getByLabel('Марина', { exact: true }).check();
      await expect(decision.getByRole('button', { name: /Подтвердить для/ })).toHaveCount(0);
      await decision.getByRole('button', { name: 'Посмотреть изменения по клиентам' }).click();
      await decision.getByRole('button', { name: 'Подтвердить для 2 клиентов' }).click();
      await expect(decision.getByRole('status')).toContainText('Реальные программы не изменены');
      await expect(decision.getByLabel('Марина', { exact: true })).toBeDisabled();

      const followup = page.locator('#coach-followup');
      await expect(followup.getByRole('textbox')).toHaveCount(0);
      await followup.getByRole('button', { name: 'Создать черновик в примере' }).click();
      const draft = followup.getByRole('textbox', { name: 'Черновик сопровождения' });
      await draft.fill('Алексей, обсудим следующую тренировку.');
      await draft.focus();
      await page.keyboard.press('Tab');
      await expect(
        followup.getByRole('button', { name: 'Подтвердить отправку в примере' }),
      ).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(draft).toHaveValue('Алексей, обсудим следующую тренировку.');
      await expect(draft).toBeDisabled();
      await expect(followup.getByRole('status')).toContainText('Никому ничего не отправлено');
      expect(writes).toEqual([]);
      await page.reload();
      await expect(
        page
          .locator('#coach-connect')
          .getByRole('button', { name: 'Показать принятое приглашение' }),
      ).toBeEnabled();
      await expect(page.locator('#coach-followup').getByRole('textbox')).toHaveCount(0);
    });
