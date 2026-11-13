const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '../../..');
const modules = process.env.YFC_PLAYWRIGHT_MODULES || path.join(root, 'frontend', 'node_modules');
const { chromium, webkit } = require(path.join(modules, 'playwright'));
const preview = pathToFileURL(path.join(root, 'docs/ux-proposals/issue-1440/preview/nutrition-1440.html'));
if (!process.env.YFC_1479_BASELINE_HTML) throw new Error('Set YFC_1479_BASELINE_HTML to the pinned baseline HTML');
const baseline = pathToFileURL(process.env.YFC_1479_BASELINE_HTML);
const evidence = path.join(__dirname, 'after');
fs.mkdirSync(evidence, { recursive: true });

function contrast(foreground, background) {
  const luminance = (color) => {
    const channels = color.match(/\d+(?:\.\d+)?/g).slice(0, 3).map(Number);
    return channels.reduce((sum, value, index) => {
      const x = value / 255;
      return sum + [0.2126, 0.7152, 0.0722][index] * (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4);
    }, 0);
  };
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

const styles = (locator) => locator.evaluate((element) => {
  const css = getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  return {
    background: css.backgroundColor, color: css.color, border: css.border,
    radius: css.borderRadius, padding: css.padding, height: rect.height,
    font: css.font, opacity: css.opacity, outline: css.outline,
  };
});

async function focusByTab(page, locator) {
  for (let index = 0; index < 80 && !(await locator.evaluate((button) => button === document.activeElement)); index += 1) {
    await page.keyboard.press('Tab');
  }
  assert.equal(await locator.evaluate((button) => button === document.activeElement && button.matches(':focus-visible')), true);
}

const focusStyle = (locator) => locator.evaluate((element) => {
  const css = getComputedStyle(element);
  return { style: css.outlineStyle, width: css.outlineWidth, offset: css.outlineOffset };
});

(async () => {
  const results = [];
  for (const [engine, kind] of Object.entries({ chromium, webkit })) {
    const browser = await kind.launch({ headless: true });
    try {
      for (const theme of ['light', 'dark']) {
        for (const width of [320, 393, 430, 1280]) {
          const page = await browser.newPage({ viewport: { width, height: width === 1280 ? 900 : 844 } });
          try {
            const before = await browser.newPage({ viewport: { width, height: width === 1280 ? 900 : 844 } });
            let beforeFocus;
            try {
              await before.goto(`${baseline.href}?theme=${theme}&state=filled`);
              await before.locator('#preview-tools').evaluate((element) => element.remove());
              const beforeFood = before.getByRole('button', { name: 'Добавить еду', exact: true });
              const beforeWater = before.getByRole('button', { name: 'Добавить воду', exact: true });
              await beforeFood.waitFor();
              await focusByTab(before, beforeFood);
              const food = await focusStyle(beforeFood);
              await before.keyboard.press('Tab');
              assert.equal(await beforeWater.evaluate((button) => button === document.activeElement && button.matches(':focus-visible')), true);
              beforeFocus = [food, await focusStyle(beforeWater)];
            } finally { await before.close(); }
            const errors = [];
            page.on('pageerror', (error) => errors.push(error.message));
            await page.goto(`${preview.href}?theme=${theme}&state=filled`);
            await page.locator('#preview-tools').evaluate((element) => element.remove());
            await page.evaluate(() => document.fonts.ready);
            const food = page.getByRole('button', { name: 'Добавить еду', exact: true });
            const water = page.getByRole('button', { name: 'Добавить воду', exact: true });
            await food.waitFor();
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
            const idle = await Promise.all([styles(food), styles(water)]);
            assert.deepEqual(idle[0], idle[1]);
            assert.ok(idle[0].height >= 44);
            assert.ok(contrast(idle[0].color, idle[0].background) >= 4.5);
            assert.deepEqual(await food.locator('svg').innerHTML(), await water.locator('svg').innerHTML());
            assert.equal(await water.locator('svg').getAttribute('data-icon'), 'plus');
            await page.screenshot({ path: path.join(evidence, `${engine}-${theme}-${width}.png`), fullPage: true });
            await page.addStyleTag({ content: '*, *::before, *::after { transition: none !important; animation: none !important; }' });
            await food.hover();
            const foodHover = await styles(food);
            await water.hover();
            assert.deepEqual(foodHover, await styles(water));
            await page.mouse.move(0, 0);
            await focusByTab(page, food);
            const foodFocus = await styles(food);
            assert.deepEqual(await focusStyle(food), beforeFocus[0]);
            await page.keyboard.press('Tab');
            assert.equal(await water.evaluate((button) => button === document.activeElement && button.matches(':focus-visible')), true);
            assert.deepEqual(await focusStyle(water), beforeFocus[1]);
            assert.deepEqual(foodFocus, await styles(water));
            if (width === 393) await page.screenshot({ path: path.join(evidence, `${engine}-${theme}-393-focus.png`), fullPage: false });
            await page.locator('.primary-actions button').evaluateAll((buttons) => buttons.forEach((button) => { button.disabled = true; }));
            assert.deepEqual(await styles(food), await styles(water));
            await page.locator('.primary-actions button').evaluateAll((buttons) => buttons.forEach((button) => { button.disabled = false; }));
            await food.focus();
            await page.keyboard.press('Enter');
            await page.getByRole('dialog').waitFor();
            await page.keyboard.press('Escape');
            await page.getByRole('dialog').waitFor({ state: 'hidden' });
            await water.focus();
            await page.keyboard.press('Enter');
            await page.waitForFunction(() => document.activeElement?.id === 'water-quick' && scrollY > 0);
            assert.deepEqual(errors, []);
            results.push({ engine, browserVersion: browser.version(), theme, width, height: idle[0].height, contrast: Number(contrast(idle[0].color, idle[0].background).toFixed(2)), focusOutlineStyle: beforeFocus[0].style, result: 'PASS_BEHAVIOR_AND_EQUIVALENCE' });
          } finally { await page.close(); }
        }
      }
    } finally { await browser.close(); }
  }
  fs.writeFileSync(path.join(__dirname, 'checks.json'), JSON.stringify(results, null, 2) + '\n');
  console.log(`PASS: ${results.length} prototype combinations`);
})().catch((error) => { console.error(error); process.exitCode = 1; });
