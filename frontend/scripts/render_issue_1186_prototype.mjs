import { createServer } from 'node:http';
import { mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const playwrightRoot = process.env.YFC_PLAYWRIGHT_NODE_MODULES
  ? join(process.env.YFC_PLAYWRIGHT_NODE_MODULES, 'playwright')
  : 'playwright';
const { chromium } = require(playwrightRoot);

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const prototypePath = '/docs/ux-proposals/issue-1186/visual-prototype.html';
const outputDir = join(repoRoot, 'docs', 'ux-proposals', 'issue-1186', 'evidence');
const widths = [320, 360, 393, 430];
const themes = ['light', 'dark'];
const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.gif': 'image/gif',
  '.html': 'text/html; charset=utf-8',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.mp4': 'video/mp4',
  '.png': 'image/png',
  '.webp': 'image/webp',
};

mkdirSync(outputDir, { recursive: true });

const server = createServer((request, response) => {
  try {
    const requestPath = decodeURIComponent(new URL(request.url ?? '/', 'http://127.0.0.1').pathname);
    const absolutePath = resolve(repoRoot, `.${requestPath}`);
    if (!absolutePath.startsWith(repoRoot) || requestPath.includes('..')) {
      response.writeHead(403).end();
      return;
    }
    const body = readFileSync(absolutePath);
    const contentType = mimeTypes[extname(absolutePath)] ?? 'application/octet-stream';
    const range = request.headers.range;
    if (range?.startsWith('bytes=')) {
      const [startText, endText] = range.slice(6).split('-');
      const start = Number(startText);
      const end = endText ? Number(endText) : body.length - 1;
      if (Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end >= start) {
        const boundedEnd = Math.min(end, body.length - 1);
        response.writeHead(206, {
          'Accept-Ranges': 'bytes',
          'Cache-Control': 'no-store',
          'Content-Length': boundedEnd - start + 1,
          'Content-Range': `bytes ${start}-${boundedEnd}/${body.length}`,
          'Content-Type': contentType,
        });
        response.end(body.subarray(start, boundedEnd + 1));
        return;
      }
    }
    response.writeHead(200, {
      'Accept-Ranges': 'bytes',
      'Cache-Control': 'no-store',
      'Content-Length': statSync(absolutePath).size,
      'Content-Type': contentType,
    });
    response.end(body);
  } catch {
    response.writeHead(404).end();
  }
});

await new Promise((resolveServer) => server.listen(0, '127.0.0.1', resolveServer));
const address = server.address();
if (!address || typeof address === 'string') throw new Error('Could not start prototype server');

const browser = await chromium.launch({ headless: true });
const geometry = [];
const frameChecks = [];
try {
  for (const theme of themes) {
    for (const width of widths) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, colorScheme: theme });
      await page.goto(`http://127.0.0.1:${address.port}${prototypePath}?theme=${theme}`, {
        waitUntil: 'networkidle',
      });
      await page.waitForFunction(
        () => [...document.querySelectorAll('video[data-frame-time]')].every((video) => video.dataset.frameReady === 'true'),
        undefined,
        { timeout: 10_000 },
      ).catch(() => undefined);
      await page.waitForTimeout(250);
      frameChecks.push(
        ...(await page.evaluate(({ theme: currentTheme, width: currentWidth }) =>
          [...document.querySelectorAll('video[data-frame-time]')].map((video) => ({
            theme: currentTheme,
            viewport_width: currentWidth,
            requested_position: Number(video.dataset.frameTime ?? 0),
            current_time: Number(video.currentTime.toFixed(3)),
            duration: Number(Number.isFinite(video.duration) ? video.duration.toFixed(3) : 0),
            video_width: video.videoWidth,
            video_height: video.videoHeight,
            ready_state: video.readyState,
          })),
        { theme, width })),
      );
      await page.screenshot({
        path: join(outputDir, `${theme}-${width}.png`),
        fullPage: true,
      });
      geometry.push(
        ...(await page.evaluate(({ theme: currentTheme, width: currentWidth }) =>
          [...document.querySelectorAll('.candidate')].map((candidate) => {
            const surface = candidate.querySelector('.media-surface');
            const image = candidate.querySelector('img');
            const rect = surface?.getBoundingClientRect();
            const imageRect = image?.getBoundingClientRect();
            return {
              theme: currentTheme,
              viewport_width: currentWidth,
              candidate: candidate.querySelector('h3')?.textContent?.trim() ?? 'unknown',
              surface_width: rect?.width ?? null,
              surface_height: rect?.height ?? null,
              surface_delta: rect ? Number(Math.abs(rect.width - rect.height).toFixed(3)) : null,
              image_width: imageRect?.width ?? null,
              image_height: imageRect?.height ?? null,
              image_natural_width: image?.naturalWidth ?? null,
              image_natural_height: image?.naturalHeight ?? null,
            };
          }),
        { theme, width })),
      );
      await page.close();
    }
  }
} finally {
  await browser.close();
  server.close();
}

writeFileSync(
  join(outputDir, 'prototype-geometry.json'),
  `${JSON.stringify({ prototype: prototypePath, viewports: widths, themes, geometry, frame_checks: frameChecks }, null, 2)}\n`,
);
console.log(
  JSON.stringify(
    {
      output_dir: 'docs/ux-proposals/issue-1186/evidence',
      screenshots: themes.length * widths.length,
      geometry_records: geometry.length,
      frame_records: frameChecks.length,
      max_square_delta: Math.max(...geometry.filter((item) => item.candidate !== 'Текущее поведение: fallback picture').map((item) => item.surface_delta ?? 0)),
      current_wide_height: geometry.find((item) => item.candidate === 'Текущее поведение: fallback picture')?.surface_height ?? null,
    },
    null,
    2,
  ),
);
