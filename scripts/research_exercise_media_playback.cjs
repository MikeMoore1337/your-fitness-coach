/* Offline Playwright browser check for YFC #986. Raw/derived media never gets published.
 * Run from repository root:
 *   node scripts/research_exercise_media_playback.cjs
 * Requires frontend npm ci + Playwright's Chromium and WebKit browsers.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const ROOT = path.resolve(__dirname, '..');
const MEDIA_DIR = process.env.YFC_986_MEDIA_DIR
  ? path.resolve(process.env.YFC_986_MEDIA_DIR)
  : path.join(ROOT, '.artifacts', 'tasks', '986', 'pilot', 'transcoded');
const OUTPUT_CSV = process.env.YFC_986_BROWSER_REPORT
  ? path.resolve(process.env.YFC_986_BROWSER_REPORT)
  : path.join(MEDIA_DIR, 'reproduced-browser-compat.csv');
const { chromium, webkit } = require(path.join(ROOT, 'frontend', 'node_modules', 'playwright'));

function csv(value) {
  return '"' + String(value ?? '').replaceAll('"', '""') + '"';
}

async function testBrowser(name, engine, files, fixtureUrl, results) {
  const browser = await engine.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto(fixtureUrl);
    for (const file of files) {
      const row = {
        browser: name, file, metadata: 'UNVERIFIED', playback: 'FAIL',
        width: '', height: '', latency_ms: '', error: '',
      };
      try {
        await page.evaluate((filename) => {
          const video = document.querySelector('#media');
          video.pause();
          video.src = filename;
          video.load();
        }, file);
        await page.waitForFunction(
          () => {
            const video = document.querySelector('#media');
            return video.readyState >= HTMLMediaElement.HAVE_METADATA || Boolean(video.error);
          },
          {},
          { timeout: 10_000 }
        );
        const { width, height, error } = await page.evaluate(() => {
          const video = document.querySelector('#media');
          return {
            width: video.videoWidth, height: video.videoHeight,
            error: video.error?.message || '',
          };
        });
        if (error || !width || !height) throw new Error('MP4 metadata decode error: ' + error);
        row.metadata = 'PASS';
        row.width = width;
        row.height = height;

        const begin = Date.now();
        await page.evaluate(() => document.querySelector('#media').play());
        await page.waitForFunction(
          () => {
            const video = document.querySelector('#media');
            return video.currentTime >= 0.2 || Boolean(video.error);
          },
          {},
          { timeout: 10_000 }
        );
        const playback = await page.evaluate(() => {
          const video = document.querySelector('#media');
          return { currentTime: video.currentTime, error: video.error?.message || '' };
        });
        if (playback.error || playback.currentTime < 0.2) {
          throw new Error('Playback did not progress: ' + playback.error);
        }
        row.playback = 'PASS';
        row.latency_ms = Date.now() - begin;
      } catch (error) {
        row.error = String(error?.message || error).slice(0, 240);
      }
      results.push(row);
      console.log(name + ' ' + file + ': ' + row.metadata + ' / ' + row.playback);
    }
  } finally {
    await browser.close();
  }
}

async function main() {
  if (!fs.existsSync(MEDIA_DIR)) throw new Error('Missing ignored pilot media dir: ' + MEDIA_DIR);
  const files = fs.readdirSync(MEDIA_DIR).filter((name) =>
    /^(male|female)-[a-z0-9-]+-(480|720)p-crf(28|29)\.mp4$/.test(name)
  ).sort();
  if (files.length !== 8) throw new Error('Expected 8 pilot outputs, found ' + files.length);
  const fixture = path.join(MEDIA_DIR, 'research-playback.html');
  fs.writeFileSync(
    fixture,
    '<!doctype html><html lang="ru"><meta charset="utf-8">' +
    '<video id="media" muted playsinline preload="auto" style="width:390px"></video></html>'
  );
  const results = [];
  const url = pathToFileURL(fixture).href;
  await testBrowser('Chromium', chromium, files, url, results);
  await testBrowser('WebKit', webkit, files, url, results);
  const keys = Object.keys(results[0]);
  const lines = [keys.join(','), ...results.map((row) => keys.map((key) => csv(row[key])).join(','))];
  fs.mkdirSync(path.dirname(OUTPUT_CSV), { recursive: true });
  fs.writeFileSync(OUTPUT_CSV, lines.join('\n') + '\n', 'utf8');
  const passed = results.filter((row) => row.playback === 'PASS').length;
  console.log('RESEARCH_ONLY=1 PLAYBACK_PASSED=' + passed + '/' + results.length + ' REPORT=' + OUTPUT_CSV);
  if (passed !== results.length) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
