import { expect, test } from '@playwright/test';

test('the built entry is preloaded once before its module script', async ({ page }) => {
  await page.route('**/api/v1/public/articles*', (route) => route.fulfill({ json: [] }));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'СИЛА В ДЕЙСТВИИ.' })).toBeVisible();

  const entry = await page.evaluate(() => {
    const script = document.querySelector<HTMLScriptElement>('script[type="module"][src]');
    if (!script) return null;
    const links = [
      ...document.querySelectorAll<HTMLLinkElement>('link[rel="modulepreload"]'),
    ].filter((link) => link.href === script.src);
    return {
      count: links.length,
      beforeScript: links[0]
        ? Boolean(links[0].compareDocumentPosition(script) & Node.DOCUMENT_POSITION_FOLLOWING)
        : false,
      matchingCredentials: links[0]?.crossOrigin === script.crossOrigin,
    };
  });
  expect(entry).toEqual({ count: 1, beforeScript: true, matchingCredentials: true });
});
