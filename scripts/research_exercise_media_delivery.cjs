/* Local HTTP + browser delivery pilot for YFC #986.
 * Research only: no upstream requests, no production manifest, no binary publication.
 * Run: node scripts/research_exercise_media_delivery.cjs
 * Requires ignored pilot media and local Playwright Chromium/WebKit.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium, webkit } = require(path.join(__dirname, '..', 'frontend', 'node_modules', 'playwright'));

const ROOT = path.resolve(__dirname, '..');
const PILOT = process.env.YFC_986_PILOT_DIR
  ? path.resolve(process.env.YFC_986_PILOT_DIR)
  : path.join(ROOT, '.artifacts', 'tasks', '986', 'pilot');
const VIDEO_DIR = path.join(PILOT, 'transcoded');
const POSTER_DIR = path.join(PILOT, 'poster-transcoded');
const OUTPUT = process.env.YFC_986_DELIVERY_REPORT
  ? path.resolve(process.env.YFC_986_DELIVERY_REPORT)
  : path.join(PILOT, 'reproduced-delivery-compat.csv');
const VIDEO_RE = /^(male|female)-([a-z0-9-]+)-(480|720)p-crf(28|29)\.mp4$/;
const FILES = fs.existsSync(VIDEO_DIR)
  ? fs.readdirSync(VIDEO_DIR).filter((s) => VIDEO_RE.test(s)).sort()
  : [];
const csv = (value) => '"' + String(value ?? '').replaceAll('"', '""') + '"';

function posterName(file) {
  const match = VIDEO_RE.exec(file);
  return match ? match[1] + '-' + match[2] + '-854x480-q80.webp' : null;
}

const fixture = `<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<body style="margin:0"><div style="height:4px"></div>
<img id="poster" style="width:100%;max-width:440px;height:auto" alt="Exercise poster">
<div id="container"></div><script>
const params = new URLSearchParams(location.search);
const file = params.get('file');
const poster = document.getElementById('poster');
const frame = document.getElementById('container');
window.pilot = { state:'INITIAL', loadeddataMs:null, error:'', posterLoaded:false };
const start = performance.now();
poster.addEventListener('load', () => { window.pilot.posterLoaded=true; });
poster.src = '/poster/' + encodeURIComponent(params.get('poster'));
if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
  window.pilot.state='REDUCED';
} else {
  const video = document.createElement('video');
  video.id='media'; video.muted=true; video.loop=true;
  video.autoplay=true; video.playsInline=true; video.preload='metadata';
  video.style.width='100%'; video.style.maxWidth='440px';
  video.hidden=true;
  video.addEventListener('loadeddata', () => {
    window.pilot.loadeddataMs=Math.round(performance.now()-start);
    poster.hidden=true; video.hidden=false;
    window.pilot.state='LOADED';
  });
  video.addEventListener('error', () => {
    window.pilot.state='ERROR';
    window.pilot.error=String(video.error?.code || 'unknown');
  });
  frame.appendChild(video);
  const observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      observer.disconnect();
      video.src='/clip/' + encodeURIComponent(params.has('fail') ? 'missing.mp4' : file);
      video.play().catch(() => {});
    }
  });
  observer.observe(frame);
}
</script></body></html>`;

function startServer() {
  const serverStats = { video:0, poster:0 };
  const knownVideos = new Set(FILES);
  const knownPosters = new Set(FILES.map(posterName));
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/fixture') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(fixture);
      return;
    }
    const isClip = url.pathname.startsWith('/clip/');
    const isPoster = url.pathname.startsWith('/poster/');
    if (isClip) serverStats.video++;
    if (isPoster) serverStats.poster++;
    const name = decodeURIComponent(url.pathname.slice(isClip ? 6 : 8));
    if (!(isClip || isPoster) ||
        !(isClip ? knownVideos.has(name) : knownPosters.has(name))) {
      res.writeHead(404, { 'Content-Type': 'text/plain' }); res.end('not found');
      return;
    }
    const file = path.join(isClip ? VIDEO_DIR : POSTER_DIR, name);
    const stat = fs.statSync(file);
    const match = /^bytes=(\d+)-(\d*)$/.exec(req.headers.range || '');
    const start = match ? Number(match[1]) : 0;
    const end = match && match[2] ? Number(match[2]) : stat.size - 1;
    if (start >= stat.size || end < start || end >= stat.size) {
      res.writeHead(416, { 'Content-Range': 'bytes */' + stat.size }); res.end();
      return;
    }
    const headers = {
      'Content-Type': isClip ? 'video/mp4' : 'image/webp',
      'Accept-Ranges': 'bytes', 'Content-Length': end - start + 1,
      'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    };
    if (match) headers['Content-Range'] = 'bytes ' + start + '-' + end + '/' + stat.size;
    res.writeHead(match ? 206 : 200, headers);
    fs.createReadStream(file, { start, end }).pipe(res);
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve({
      server, serverStats, origin:'http://127.0.0.1:' + server.address().port,
    }));
  });
}

async function testCase(browser, browserName, origin, serverStats, file, mode, width) {
  serverStats.video = 0;
  serverStats.poster = 0;
  const page = await browser.newPage({
    viewport:{ width, height:844 }, deviceScaleFactor:2,
    reducedMotion:mode === 'reduced' ? 'reduce' : 'no-preference',
    colorScheme:'dark',
  });
  let requests = 0;
  let posterRequests = 0;
  page.on('request', (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.startsWith('/clip/')) requests++;
    if (pathname.startsWith('/poster/')) posterRequests++;
  });
  const row = {
    browser:browserName, file, mode, viewport:width, dpr:2,
    encoded_bytes:fs.statSync(path.join(VIDEO_DIR, file)).size,
    video_requests:0, poster_requests:0, poster_loaded:false,
    video_width:'', video_height:'', loadeddata_ms:'', playback_progress:false,
    fallback_ok:false, result:'FAIL', error:'',
  };
  try {
    const params = new URLSearchParams({ file, poster:posterName(file) });
    if (mode === 'error') params.set('fail', '1');
    await page.goto(origin + '/fixture?' + params.toString());
    await page.waitForFunction(() =>
      window.pilot.posterLoaded &&
      ['REDUCED','LOADED','ERROR'].includes(window.pilot.state),
      { timeout:10000 });
    if (mode === 'video') {
      await page.waitForFunction(() => {
        const v = document.getElementById('media');
        return v && v.currentTime >= 0.2;
      }, { timeout:10000 });
    }
    const state = await page.evaluate(() => {
      const v = document.getElementById('media');
      return {
        ...window.pilot, width:v?.videoWidth, height:v?.videoHeight,
        progress: Boolean(v?.currentTime >= 0.2),
        posterVisible:!document.getElementById('poster').hidden,
      };
    });
    row.video_requests = serverStats.video;
    row.poster_requests = serverStats.poster;
    row.poster_loaded = state.posterLoaded;
    row.loadeddata_ms = state.loadeddataMs ?? '';
    row.video_width = state.width || '';
    row.video_height = state.height || '';
    row.playback_progress = state.progress;
    row.fallback_ok = mode === 'video' ? !state.posterVisible :
      state.posterVisible && state.posterLoaded;
    const valid = mode === 'video'
      ? state.state === 'LOADED' && state.progress && row.video_requests > 0 && row.fallback_ok
      : mode === 'reduced'
        ? state.state === 'REDUCED' && row.video_requests === 0 && row.fallback_ok
        : state.state === 'ERROR' && row.video_requests > 0 && row.fallback_ok;
    row.result = valid ? 'PASS' : 'FAIL';
    if (!valid) row.error = 'Unexpected state ' + state.state;
  } catch (error) {
    row.error = String(error.message || error).slice(0,160);
  } finally {
    await page.close();
  }
  return row;
}

async function main() {
  if (FILES.length !== 8 || FILES.some((file) =>
    !fs.existsSync(path.join(POSTER_DIR, posterName(file))))) {
    throw new Error('Expected 8 pinned pilot videos with matching ignored WebP posters');
  }
  const { server, origin, serverStats } = await startServer();
  const rows = [];
  try {
    for (const [name, engine] of [['Chromium', chromium],['WebKit', webkit]]) {
      const browser = await engine.launch({ headless:true });
      try {
        for (const file of FILES) {
          for (const mode of ['video','reduced']) {
            const row = await testCase(browser, name, origin, serverStats, file, mode, mode === 'video' ? 390 : 320);
            rows.push(row);
            console.log(name + ' ' + mode + ' ' + file + ' ' + row.result);
          }
        }
        for (const width of [320,430]) {
          rows.push(await testCase(browser, name, origin, serverStats, FILES[0], 'video', width));
        }
        rows.push(await testCase(browser, name, origin, serverStats, FILES[0], 'error', 390));
      } finally { await browser.close(); }
    }
  } finally { await new Promise((resolve) => server.close(resolve)); }
  fs.mkdirSync(path.dirname(OUTPUT), { recursive:true });
  const keys = Object.keys(rows[0]);
  fs.writeFileSync(OUTPUT, [keys.join(','), ...rows.map((r) =>
    keys.map((key) => csv(r[key])).join(','))].join('\n') + '\n');
  const passed = rows.filter((r) => r.result === 'PASS').length;
  console.log('LOCAL_HTTP_PILOT=' + passed + '/' + rows.length + ' REPORT=' + path.basename(OUTPUT));
  if (passed !== rows.length) process.exitCode = 1;
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
