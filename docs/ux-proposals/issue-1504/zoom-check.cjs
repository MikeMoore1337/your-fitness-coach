const { chromium, webkit } = require('playwright');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const assert = require('node:assert/strict');
const url = pathToFileURL(path.join(__dirname, 'index.html')).href;
const extension = path.join(__dirname, 'zoom-extension');

(async () => {
  for (const theme of ['light', 'dark']) {
    const ctx = await chromium.launchPersistentContext('', { channel: 'chromium', headless: true, viewport: { width: 393, height: 852 }, ignoreDefaultArgs: ['--disable-extensions'], args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`] });
    try {
      const worker = ctx.serviceWorkers()[0] || await ctx.waitForEvent('serviceworker');
      const page = ctx.pages()[0] || await ctx.newPage();
      await page.goto(url);
      if (theme === 'dark') await page.getByRole('button', { name: 'Тёмная тема' }).click();
      const zoom = await worker.evaluate(async () => { const tab = (await chrome.tabs.query({})).find(t => t.url?.startsWith('file:')); await chrome.tabs.setZoom(tab.id, 2); return chrome.tabs.getZoom(tab.id); });
      assert.equal(zoom, 2);
      for (const name of ['Сегодня', 'План', 'Питание', 'Прогресс']) {
        await page.getByRole('button', { name, exact: true }).click();
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), name + ' overflow');
        assert(await page.getByRole('button', { name: 'Быстро добавить' }).isVisible());
      }
      const labels = await page.locator('.dock button').evaluateAll(items => items.map(el => {
        const rect = el.getBoundingClientRect(), label = el.querySelector('span');
        return { width: rect.width, height: rect.height, clipped: label.scrollWidth > label.clientWidth };
      }));
      assert(labels.every(r => r.width >= 44 && r.height >= 44 && !r.clipped), JSON.stringify(labels));
      assert.equal(await page.locator('.dock button').evaluateAll(items => new Set(items.map(el => Math.round(el.getBoundingClientRect().y))).size), 2);
      await page.screenshot({ path: path.join(__dirname, 'screens', 'chromium-393-' + theme + '-zoom200.png') });
    } finally { await ctx.close(); }
  }
  for (const [name, type] of Object.entries({ chromium, webkit })) {
    const browser = await type.launch();
    const page = await browser.newPage({ viewport: { width: 393, height: 852 } });
    await page.goto(url);
    const add = page.getByRole('button', { name: 'Быстро добавить' });
    await add.focus();
    await page.keyboard.press('Enter');
    assert(await page.getByRole('dialog').isVisible());
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.activeElement.id === 'open-add');
    assert(await page.locator('#dock-group').isVisible());
    await page.setViewportSize({ width: 852, height: 393 });
    assert(await page.getByRole('button', { name: 'Быстро добавить' }).isVisible(), name + ' landscape');
    await browser.close();
  }
  console.log('PASS: real Chromium zoom 200% in both themes; keyboard/Escape/focus and landscape in Chromium and WebKit');
})().catch(e => { console.error(e); process.exitCode = 1; });
