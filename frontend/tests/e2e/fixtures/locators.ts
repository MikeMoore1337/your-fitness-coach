import { expect, type Locator, type Page } from '@playwright/test';

export function detailsByHeading(page: Page, title: string): Locator {
  return page.locator('details').filter({
    has: page.getByRole('heading', { name: title, exact: true }),
  });
}

export async function openDetailsByHeading(page: Page, title: string): Promise<Locator> {
  const card = detailsByHeading(page, title);
  await expect(card).toHaveCount(1);
  if ((await card.getAttribute('open')) === null) {
    await card.locator(':scope > summary').click();
  }
  await expect(card).toHaveAttribute('open', '');
  return card;
}

export function namedArticle(page: Page, title: string): Locator {
  return page.getByRole('article').filter({
    has: page.getByRole('heading', { name: title, exact: true }),
  });
}

export function notificationArticle(page: Page, title: string): Locator {
  return page.getByRole('article').filter({
    has: page.getByText(title, { exact: true }),
  });
}

export function nutritionDaySummary(page: Page): Locator {
  return page.getByRole('complementary', { name: 'КБЖУ', exact: true });
}

export function progressOverview(page: Page): Locator {
  return page.getByRole('region', { name: 'Что изменилось', exact: true });
}
