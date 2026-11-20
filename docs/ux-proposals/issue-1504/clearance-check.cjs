const { chromium, webkit } = require('playwright');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  let checks = 0;
  for (const [engine, type] of Object.entries({ chromium, webkit })) {
    const browser = await type.launch();
    for (const width of [320, 393]) for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width, height: 852 } });
      await page.goto(pathToFileURL(path.join(__dirname, 'index.html')).href);
      if (theme === 'dark') await page.getByRole('button', { name: 'Тёмная тема' }).click();
      for (const route of ['Сегодня', 'План', 'Питание', 'Прогресс']) {
        await page.getByRole('button', { name: route, exact: true }).click();
        const last = page.locator('#main button').last();
        await last.scrollIntoViewIfNeeded();
        await last.focus();
        await page.waitForTimeout(250);
        const available = await last.evaluate(el => {
          const r = el.getBoundingClientRect(), dock = document.querySelector('#dock-group').getBoundingClientRect();
          const x = Math.max(1, Math.min(innerWidth - 1, r.x + r.width / 2));
          const y = Math.max(1, Math.min(innerHeight - 1, r.y + r.height / 2));
          return { hit: el.contains(document.elementFromPoint(x, y)), aboveDock: r.bottom <= dock.top + 1, rect: [r.x, r.y, r.width, r.height], dockTop: dock.top };
        });
        assert(available.hit && available.aboveDock, JSON.stringify({ engine, width, theme, route, available }));
        checks++;
      }
      await page.close();
    }
    await browser.close();
  }
  console.log('PASS: ' + checks + ' last-control focus, clearance and hit-test cases');
})().catch(e => { console.error(e); process.exitCode = 1; });
