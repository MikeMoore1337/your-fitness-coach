import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { expect, test } from '@playwright/test';
import { PNG, compareLandingPixels } from './fixtures/landing-pixels';

const root = path.resolve('../docs/design/references/product-v10-landing-approved/final-895');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'MANIFEST.json'), 'utf8')) as {
  images: Array<{
    file: string;
    sha256: string;
    width: number;
    height: number;
    theme: string;
    audience: string;
    menu: boolean;
  }>;
};
const evidence = path.resolve(
  process.env.LANDING_VISUAL_EVIDENCE_DIR ?? '../.artifacts/tasks/895/evidence/region-recovery',
);
fs.mkdirSync(path.join(evidence, 'frozen'), { recursive: true });

for (const item of manifest.images)
  test(`frozen approved first screen/menu: ${item.file}`, async ({ page }, testInfo) => {
    const data = fs.readFileSync(path.join(root, item.file));
    expect(crypto.createHash('sha256').update(data).digest('hex')).toBe(item.sha256);
    await page.setViewportSize({ width: item.width, height: item.height });
    await page.emulateMedia({
      colorScheme: item.theme as 'light' | 'dark',
      reducedMotion: 'reduce',
    });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), item.theme);
    await page.goto(item.audience === 'coach' ? '/for-trainers' : '/', {
      waitUntil: 'networkidle',
    });
    await expect(page.locator('.ref-hero h1')).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() =>
      [...document.images]
        .filter((image) => image.getBoundingClientRect().top < innerHeight)
        .every((image) => image.complete && image.naturalWidth > 0),
    );
    if (item.menu) await page.getByRole('button', { name: 'Открыть меню' }).click();
    const actual = await page.screenshot({
      path: path.join(evidence, 'frozen', item.file),
      animations: 'disabled',
    });
    const source = PNG.sync.read(data);
    const candidate = PNG.sync.read(actual);
    expect(candidate.width).toBe(source.width);
    expect(candidate.height).toBe(source.height);
    const result = compareLandingPixels(source, candidate, {
      x: 0,
      y: 0,
      width: source.width,
      height: source.height,
    });
    fs.writeFileSync(
      path.join(evidence, 'frozen', item.file + '.json'),
      JSON.stringify(
        {
          ...item,
          scope: 'FIRST_SCREEN_OR_MENU_ONLY',
          threshold: 0.01,
          channelTolerance: 16,
          changedPixelRatio: result.changedPixelRatio,
          status: result.changedPixelRatio <= 0.01 ? 'PASS' : 'FAIL',
        },
        null,
        2,
      ),
    );
    fs.writeFileSync(
      path.join(evidence, 'frozen', item.file + '-diff.png'),
      PNG.sync.write(result.heatmap),
    );
    await testInfo.attach('frozen-reference', { body: data, contentType: 'image/png' });
    await testInfo.attach('candidate', { body: actual, contentType: 'image/png' });
    expect(
      result.changedPixelRatio,
      'Approved #895 first-screen/menu differs; never regenerate the baseline.',
    ).toBeLessThanOrEqual(0.01);
  });
