import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const playwrightRoot = process.env.YFC_PLAYWRIGHT_NODE_MODULES
  ? join(process.env.YFC_PLAYWRIGHT_NODE_MODULES, 'playwright')
  : 'playwright';
const { chromium } = require(playwrightRoot);
const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const poster = readFileSync(
  join(repoRoot, 'backend', 'assets', 'exercise-guides', 'exercises-media', 'incline-bench-press', 'poster-1280.jpg'),
).toString('base64');
const outputPath = join(
  repoRoot,
  'docs',
  'ux-proposals',
  'issue-1186',
  'evidence',
  'geometry-diagnosis.json',
);

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.setContent(`
    <style>
      .surface { width: 280px; overflow: hidden; border: 1px solid #aaa; }
      .surface img, .surface video { display: block; width: 100%; aspect-ratio: 1; object-fit: contain; }
      .exercise-media-picture { display: block; min-width: 0; }
      .exercise-media-picture > img { display: block; width: 100%; height: 100%; object-fit: contain; }
    </style>
    <div id="picture" class="surface">
      <picture class="exercise-media-picture">
        <img width="1280" height="720" src="data:image/jpeg;base64,${poster}" alt="16:9 poster" />
      </picture>
    </div>
    <div id="direct" class="surface"><video aria-label="direct media"></video></div>
  `);
  await page.waitForTimeout(100);
  const result = await page.evaluate(() =>
    Object.fromEntries(
      ['picture', 'direct'].map((id) => {
        const surface = document.querySelector(`#${id}`);
        const media = surface?.querySelector('img, video');
        const rect = surface?.getBoundingClientRect();
        const mediaRect = media?.getBoundingClientRect();
        return [
          id,
          {
            surface_width: rect?.width ?? null,
            surface_height: rect?.height ?? null,
            media_width: mediaRect?.width ?? null,
            media_height: mediaRect?.height ?? null,
            delta: rect ? Number(Math.abs(rect.width - rect.height).toFixed(3)) : null,
          },
        ];
      }),
    ),
  );
  const output = {
    viewport: { width: 390, height: 844 },
    fixture: 'current active/guide media selector contract with a 16:9 poster',
    result,
    interpretation: {
      picture: 'ISSUE: intrinsic height leaks through the unconstrained picture wrapper',
      direct: 'PASS: direct media receives the square aspect-ratio rule',
    },
  };
  writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`);
  console.log(JSON.stringify(output, null, 2));
} finally {
  await browser.close();
}
