const { chromium, webkit } = require('playwright');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  let count = 0;
  for (const [engine, browserType] of Object.entries({ chromium, webkit })) {
    const browser = await browserType.launch({ headless: true });
    for (const width of [320, 360, 390, 393, 430]) {
      for (const theme of ['light', 'dark']) {
        const page = await browser.newPage({ viewport: { width, height: 852 }, reducedMotion: 'reduce' });
        await page.goto(pathToFileURL(path.join(__dirname, 'index.html')).href);
        if (theme === 'dark') await page.getByRole('button', { name: 'Тёмная тема' }).click();
        const tabs = page.locator('[data-nav]');
        assert.equal(await tabs.count(), 4);
        const rects = await tabs.evaluateAll(items => items.map(el => {
          const rect = el.getBoundingClientRect(), label = el.querySelector('span');
          return { x: rect.x, y: rect.y, width: rect.width, height: rect.height, clipped: label.scrollWidth > label.clientWidth };
        }));
        assert(rects.every(r => Math.abs(r.y - rects[0].y) < 1 && r.width >= 44 && r.height >= 44 && !r.clipped), JSON.stringify({ engine, width, theme, rects }));
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'horizontal overflow');
        assert(await page.locator('#open-add').evaluate(el => { const r = el.getBoundingClientRect(); return r.width >= 44 && r.height >= 44 && el.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)); }), 'Quick Add target is obscured or too small');
        for (const name of ['Сегодня', 'План', 'Питание', 'Прогресс']) {
          await page.getByRole('button', { name, exact: true }).click();
          assert.equal(await page.getByRole('button', { name, exact: true }).getAttribute('aria-current'), 'page');
          if (width === 320 || width === 393) {
            const slug = { 'Сегодня': 'today', 'План': 'plan', 'Питание': 'nutrition', 'Прогресс': 'progress' }[name];
            await page.screenshot({ path: path.join(__dirname, 'screens', engine + '-' + width + '-' + theme + '-' + slug + '.png') });
          }
          await page.getByRole('button', { name: 'Быстро добавить' }).click();
          assert(await page.getByRole('dialog').isVisible());
          assert(!(await page.locator('#dock-group').isVisible()));
          await page.getByRole('button', { name: 'Закрыть' }).click();
          assert(await page.locator('#dock-group').isVisible());
          assert(await page.getByRole('button', { name: 'Быстро добавить' }).isVisible());
          await page.waitForFunction(() => document.activeElement.id === 'open-add', null, { timeout: 2000 });
        }
        if (width === 320 || width === 393) {
          await page.getByRole('button', { name: 'Сегодня', exact: true }).click();
          await page.getByRole('button', { name: 'Быстро добавить' }).click();
          await page.screenshot({ path: path.join(__dirname, 'screens', engine + '-' + width + '-' + theme + '-sheet.png') });
        }
        await page.close();
        count++;
      }
    }
    await browser.close();
  }
  console.log('PASS: ' + count + ' browser/width/theme cases, four tabs, Quick Add, focus and hit-testing');
})().catch(error => { console.error(error); process.exitCode = 1; });
