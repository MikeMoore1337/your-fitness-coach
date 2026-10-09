import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { expect, test } from '@playwright/test';
import cases from '../fixtures/landing-archive-normalization.json' with { type: 'json' };
const require = createRequire(import.meta.url);
// Decode and crop original pixels with Playwright's bundled PNG reader; never rewrite goldens.
const { PNG } = require(
  path.join(path.dirname(require.resolve('playwright-core/package.json')), 'lib/utilsBundle.js'),
) as { PNG: { sync: { read: (data: Buffer) => { width: number; height: number; data: Buffer } } } };
const root = path.resolve(
  process.env.LANDING_ARCHIVE_ROOT ?? '../docs/design/references/landing-archive-owner-canonical',
);
const evidence = path.resolve(
  process.env.LANDING_VISUAL_EVIDENCE_DIR ?? '../.artifacts/tasks/895/evidence/archive-restoration',
);
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'MANIFEST.json'), 'utf8')) as {
  source_zip_sha256: string;
  images: { filename: string; sha256: string }[];
};
fs.mkdirSync(path.join(evidence, 'candidate'), { recursive: true });

test('all 28 immutable owner originals retain their hashes', () => {
  expect(manifest.source_zip_sha256).toBe(
    '2be733d3539d98ecb575e9da0449978dfaf8ee993dda8bebbadb7d7e03d3acef',
  );
  expect(manifest.images).toHaveLength(28);
  for (const item of manifest.images)
    expect(
      crypto
        .createHash('sha256')
        .update(fs.readFileSync(path.join(root, 'screenshots', item.filename)))
        .digest('hex'),
    ).toBe(item.sha256);
});
for (const entry of cases)
  test(`${entry.file}: ${entry.description}`, async ({ page }, testInfo) => {
    await page.setViewportSize(entry.viewport);
    await page.emulateMedia({
      colorScheme: 'dark',
      reducedMotion:
        entry.selector === '.strength-scene' || entry.state === 'bridge-effort'
          ? 'no-preference'
          : 'reduce',
    });
    await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
    await page.goto(entry.audience === 'coach' ? '/for-trainers' : '/');
    await page.locator('.ref-hero h1').waitFor();
    await page.evaluate(() => document.fonts.ready);
    if (entry.state === 'summary-purchases' || entry.state === 'progress-diary') {
      const t = page.locator('#training');
      await t.getByRole('button', { name: 'Начать тренировку' }).click();
      for (let i = 0; i < 3; i++)
        await t.getByRole('button', { name: 'Завершить текущий подход' }).click();
      await t.getByRole('button', { name: 'Завершить тренировку' }).click();
      if (entry.state === 'progress-diary') {
        await t.getByRole('button', { name: 'Перейти к прогрессу' }).click();
        await page.getByRole('button', { name: 'Дневник', exact: true }).click();
        await page.getByRole('button', { name: 'Отметить съеденное в примере' }).click();
      } else await page.getByRole('button', { name: 'Покупки', exact: true }).click();
    }
    if (entry.state === 'weekly') {
      await page.locator('.ref-weekly summary').click();
      await page.getByRole('radio', { name: '3', exact: true }).check();
    }
    if (entry.state === 'changes')
      await page.getByRole('button', { name: 'Открыть изменения' }).click();
    if (entry.state === 'message')
      await page.getByRole('button', { name: 'Сообщение', exact: true }).click();
    const target = page.locator(entry.selector).first();
    await target.evaluate(
      (el, { state, offset }) => {
        const b = el.getBoundingClientRect();
        let y = b.top + scrollY + offset;
        if (el.classList.contains('strength-scene')) {
          const sticky = el.querySelector<HTMLElement>('.strength-scene__sticky')!;
          y +=
            (el.clientHeight - sticky.clientHeight) *
            (state === 'effort' ? 0.46 : state === 'record' ? 0.68 : 0.96);
        }
        if (el.classList.contains('ref-hero')) y = 0;
        window.scrollTo({ top: y, behavior: 'instant' });
      },
      { state: entry.state, offset: entry.scrollOffset },
    );
    await page.evaluate(async () => {
      await Promise.all(
        [...document.images]
          .filter(
            (i) =>
              i.getBoundingClientRect().bottom > 0 && i.getBoundingClientRect().top < innerHeight,
          )
          .map((i) => i.decode().catch(() => {})),
      );
    });
    if (entry.selector === '.strength-scene') {
      await expect(target).toHaveAttribute(
        'data-phase',
        entry.state === 'effort' ? '0' : entry.state === 'record' ? '1' : '2',
      );
      await page.waitForTimeout(1000);
    }
    const actual = await page.screenshot({
      path: path.join(evidence, 'candidate', entry.file),
      clip: entry.candidateClip,
      animations: 'disabled',
    });
    const source = PNG.sync.read(fs.readFileSync(path.join(root, 'screenshots', entry.file)));
    const candidate = PNG.sync.read(actual);
    const crop = entry.sourceCrop;
    expect(candidate.width).toBe(crop.width);
    expect(candidate.height).toBe(crop.height);
    let changed = 0;
    for (let y = 0; y < crop.height; y++)
      for (let x = 0; x < crop.width; x++) {
        const a = (y * crop.width + x) * 4,
          b = ((y + crop.y) * source.width + x + crop.x) * 4;
        if ([0, 1, 2].some((c) => Math.abs(candidate.data[a + c]! - source.data[b + c]!) > 16))
          changed++;
      }
    const ratio = changed / (crop.width * crop.height);
    fs.writeFileSync(
      path.join(evidence, 'candidate', entry.file + '.json'),
      JSON.stringify(
        {
          ...entry,
          changedPixelRatio: ratio,
          channelTolerance: 16,
          acceptanceLimit: 0.01,
          dpr: 1,
          ownerApproval: false,
        },
        null,
        2,
      ),
    );
    await testInfo.attach('candidate', { body: actual, contentType: 'image/png' });
    expect(
      ratio,
      'Archive pixel mismatch. Inspect gallery; do not update the owner reference.',
    ).toBeLessThanOrEqual(0.01);
  });
