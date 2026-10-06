/* YFC PWA shell worker. It deliberately never handles /api/ or private artifacts. */
const CACHE_NAME = 'yfc-pwa-static-v1';
const CACHE_PREFIX = 'yfc-pwa-';
const CACHE_MAX_ENTRIES = 80;
const CACHE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const APP_SHELL_PATH = '/app';
const PUSH_NOTIFICATION_TITLE = 'Your Fitness Coach';
const PUSH_NOTIFICATION_BODY =
  'В приложении есть новое уведомление. Откройте приложение, чтобы посмотреть.';
const PUSH_NOTIFICATION_PATH = '/app?section=profile#profile-notifications';
const PUSH_ALLOWED_QUERY_KEYS = new Set([
  'section',
  'workout_id',
  'comment_id',
  'workout_exercise_id',
  'report_handoff_id',
  'weekly_review',
  'date',
  'meal',
  'hydration',
  'return_to',
]);
const PUSH_ALLOWED_SECTIONS = new Set(['today', 'progress', 'programs', 'nutrition', 'profile']);

function sameOrigin(url) {
  return url.origin === self.location.origin;
}

function isPrivateOrNonShellPath(url) {
  return url.pathname.startsWith('/api/') || url.pathname.startsWith('/static/');
}

function isCacheableAppAsset(url) {
  const assetPath = url.pathname.slice('/assets/'.length);
  if (assetPath.startsWith('marketing/') || assetPath.startsWith('product/')) return false;
  return (
    /^[^/]+$/.test(assetPath) ||
    assetPath.startsWith('brand/') ||
    assetPath.startsWith('providers/')
  );
}

function isStaticAsset(request, url) {
  return (
    request.method === 'GET' &&
    sameOrigin(url) &&
    url.pathname.startsWith('/assets/') &&
    isCacheableAppAsset(url) &&
    !isPrivateOrNonShellPath(url)
  );
}

function isAppNavigation(request, url) {
  return (
    request.mode === 'navigate' &&
    request.method === 'GET' &&
    sameOrigin(url) &&
    (url.pathname === '/app' ||
      url.pathname.startsWith('/app/') ||
      url.pathname === '/coach' ||
      url.pathname === '/admin' ||
      url.pathname.startsWith('/join/'))
  );
}

function cacheKey(path) {
  return new Request(new URL(path, self.location.origin).toString(), { method: 'GET' });
}

function withCacheMetadata(response) {
  const headers = new Headers(response.headers);
  headers.set('X-YFC-Cached-At', String(Date.now()));
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function notifyClients(message) {
  try {
    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clients) client.postMessage(message);
  } catch {
    // Diagnostics must never turn a recoverable network/cache path into a failure.
  }
}

async function trimCache(cache) {
  const requests = await cache.keys();
  const entries = [];
  const now = Date.now();
  for (const request of requests) {
    const response = await cache.match(request);
    const cachedAt = Number(response?.headers.get('X-YFC-Cached-At'));
    if (!response || !Number.isFinite(cachedAt) || now - cachedAt > CACHE_MAX_AGE_MS) {
      await cache.delete(request);
      continue;
    }
    entries.push({ request, cachedAt });
  }
  entries.sort((left, right) => right.cachedAt - left.cachedAt);
  for (const entry of entries.slice(CACHE_MAX_ENTRIES)) await cache.delete(entry.request);
}

async function store(cache, request, response) {
  if (!response.ok) return;
  await cache.put(request, withCacheMetadata(response.clone()));
  await trimCache(cache);
}

async function cacheStaticAsset(request) {
  let cache;
  try {
    cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);
    if (cached) {
      const cachedAt = Number(cached.headers.get('X-YFC-Cached-At'));
      if (Number.isFinite(cachedAt) && Date.now() - cachedAt <= CACHE_MAX_AGE_MS) return cached;
      await cache.delete(request);
    }
  } catch {
    await notifyClients({ type: 'YFC_PWA_SW_ERROR', category: 'cache' });
    return fetch(request);
  }

  let response;
  try {
    response = await fetch(request);
  } catch (error) {
    await notifyClients({ type: 'YFC_PWA_SW_ERROR', category: 'cache' });
    throw error;
  }
  try {
    await store(cache, request, response);
  } catch {
    await notifyClients({ type: 'YFC_PWA_SW_ERROR', category: 'cache' });
  }
  return response;
}

async function appNavigation(request, event) {
  let cache;
  try {
    cache = await caches.open(CACHE_NAME);
  } catch {
    await notifyClients({ type: 'YFC_PWA_SW_ERROR', category: 'navigation' });
    return fetch(request);
  }
  const shellKey = cacheKey(APP_SHELL_PATH);
  let cached;
  try {
    cached = await cache.match(shellKey);
  } catch {
    await notifyClients({ type: 'YFC_PWA_SW_ERROR', category: 'navigation' });
    return fetch(request);
  }
  const refresh = fetch(request)
    .then(async (response) => {
      try {
        await store(cache, shellKey, response);
      } catch {
        await notifyClients({ type: 'YFC_PWA_SW_ERROR', category: 'cache' });
      }
      return response;
    })
    .catch(async (error) => {
      await notifyClients({ type: 'YFC_PWA_SW_ERROR', category: 'navigation' });
      throw error;
    });
  if (cached) {
    event.waitUntil(refresh.catch(() => undefined));
    return cached;
  }
  try {
    return await refresh;
  } catch {
    const fallback = await cache.match(shellKey);
    if (fallback) return fallback;
    throw new Error('YFC app shell is unavailable');
  }
}

async function deleteYfcCaches() {
  const names = await caches.keys();
  await Promise.all(
    names.filter((name) => name.startsWith(CACHE_PREFIX)).map((name) => caches.delete(name)),
  );
}

function isPositiveInteger(value) {
  return /^\d+$/.test(value) && Number(value) > 0;
}

function safePushUrl(value) {
  if (typeof value !== 'string') return null;
  let url;
  try {
    url = new URL(value, self.location.origin);
  } catch {
    return null;
  }
  if (url.origin !== self.location.origin || url.pathname !== '/app') return null;
  if (url.hash && url.hash !== '#profile-notifications') return null;
  const keys = Array.from(url.searchParams.keys());
  if (keys.some((key) => !PUSH_ALLOWED_QUERY_KEYS.has(key))) return null;
  for (const key of PUSH_ALLOWED_QUERY_KEYS) {
    if (url.searchParams.getAll(key).length > 1) return null;
  }
  const section = url.searchParams.get('section');
  if (section && !PUSH_ALLOWED_SECTIONS.has(section)) return null;
  for (const key of ['workout_id', 'comment_id', 'workout_exercise_id', 'report_handoff_id']) {
    const id = url.searchParams.get(key);
    if (id && !isPositiveInteger(id)) return null;
  }
  if (url.searchParams.get('report_handoff_id') && section !== 'progress') return null;
  if (url.searchParams.get('weekly_review') && url.searchParams.get('weekly_review') !== '1') {
    return null;
  }
  const date = url.searchParams.get('date');
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const meal = url.searchParams.get('meal');
  if (meal && !['breakfast', 'lunch', 'dinner', 'snacks'].includes(meal)) return null;
  if (meal && section !== 'nutrition') return null;
  const hydration = url.searchParams.get('hydration');
  if (hydration && hydration !== 'quick') return null;
  if (hydration && section !== 'nutrition') return null;
  const returnTo = url.searchParams.get('return_to');
  if (returnTo && returnTo !== PUSH_NOTIFICATION_PATH) return null;
  return url;
}

function pushNotificationUrl(payload) {
  const requested = safePushUrl(payload?.url);
  return requested || new URL(PUSH_NOTIFICATION_PATH, self.location.origin);
}

self.addEventListener('push', (event) => {
  // The server payload is intentionally opaque: private notification details are loaded only
  // after the application authenticates and resolves ownership in the API.
  let payload = null;
  try {
    payload = event.data?.json() || null;
  } catch {
    payload = null;
  }
  event.waitUntil(
    self.registration.showNotification(PUSH_NOTIFICATION_TITLE, {
      body: PUSH_NOTIFICATION_BODY,
      tag: 'yfc-notification',
      data: { url: pushNotificationUrl(payload).toString() },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    (async () => {
      const destination = pushNotificationUrl(event.notification.data).toString();
      const clients = await self.clients.matchAll({
        type: 'window',
        includeUncontrolled: true,
      });
      for (const client of clients) {
        if (new URL(client.url).origin !== self.location.origin) continue;
        try {
          await client.focus();
          await client.navigate(destination);
          return;
        } catch {
          // A window may disappear between matchAll and navigation.
        }
      }
      await self.clients.openWindow(destination);
    })().catch(() => undefined),
  );
});

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then(async (cache) => {
        for (const path of [APP_SHELL_PATH, '/manifest.webmanifest']) {
          try {
            const response = await fetch(path, { cache: 'reload' });
            await store(cache, cacheKey(path), response);
          } catch {
            await notifyClients({ type: 'YFC_PWA_SW_ERROR', category: 'install' });
          }
        }
      })
      .catch(() => notifyClients({ type: 'YFC_PWA_SW_ERROR', category: 'install' })),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
            .map((name) => caches.delete(name)),
        ),
      )
      .then(() => caches.open(CACHE_NAME))
      .then((cache) => trimCache(cache))
      .then(() => self.clients.claim())
      .catch(() => notifyClients({ type: 'YFC_PWA_SW_ERROR', category: 'activate' })),
  );
});

self.addEventListener('message', (event) => {
  if (event.origin !== self.location.origin) return;
  if (event.data?.type === 'YFC_PWA_SKIP_WAITING') {
    event.waitUntil(self.skipWaiting());
    return;
  }
  if (event.data?.type === 'YFC_PWA_KILL_SWITCH') {
    event.waitUntil(
      deleteYfcCaches()
        .then(() => self.registration.unregister())
        .then(() => notifyClients({ type: 'YFC_PWA_DISABLED' })),
    );
  }
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (!sameOrigin(url) || isPrivateOrNonShellPath(url)) return;
  if (isStaticAsset(request, url)) {
    event.respondWith(cacheStaticAsset(request));
    return;
  }
  if (isAppNavigation(request, url)) event.respondWith(appNavigation(request, event));
});
