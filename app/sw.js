/* ==========================================================================
   Service worker — offline support.

   Three different caching strategies, because the three kinds of thing this
   app loads want different behaviour:

     app shell (HTML/CSS/JS)  stale-while-revalidate
     data (the JSON)          network-first, falling back to cache
     posters (TMDb images)    cache-first, they never change per URL

   The data being network-first matters: a stale program is worse than a slow
   one, so we always try the network and only fall back to cache when offline.

   The shell is stale-while-revalidate rather than cache-first, which was the
   first thing built here and was wrong. Cache-first serves the old CSS and JS
   forever until VERSION is hand-bumped — remembering to do that on every
   deploy is exactly the kind of step that gets forgotten, and the failure is
   silent and confusing (a deployed change simply doesn't appear). This way the
   page still paints instantly from cache, but every load quietly refreshes the
   copy for next time. Updates land one reload late, with no manual step.
   ========================================================================== */

/* Bump this to force clients onto new shell files. */
const VERSION = 'beam-v48';
const SHELL_CACHE = `${VERSION}-shell`;
const DATA_CACHE = `${VERSION}-data`;
const IMAGE_CACHE = `${VERSION}-img`;

/* Versioned to match the ?v= query the page actually requests, so these
   precache entries are the same cache keys the app asks for. Bump the ?v here
   together with index.html and the js/ imports when shipping changed assets.
   (These had drifted to ?v=9 through several rounds of bumps elsewhere —
   not a correctness bug, since the server resolves by pathname regardless of
   query string, but a precache entry the live page never actually requests
   is a wasted one; corrected while touching this file for push support.) */
const SHELL_FILES = [
  './',
  './index.html',
  './css/beam.css?v=50',
  './js/app.js?v=50',
  './js/data.js?v=50',
  './js/format.js?v=50',
  './js/screens.js?v=50',
  './js/store.js?v=50',
  './js/push.js?v=50',
  './js/map.js?v=50',
  './manifest.webmanifest',
  './icons/icon.svg',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      /* addAll fails the whole install if any single file 404s, so add them
         individually — a missing icon shouldn't cost us offline support. */
      .then(cache => Promise.all(SHELL_FILES.map(file =>
        cache.add(file).catch(() => {})
      )))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(key => !key.startsWith(VERSION)).map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

/* Push notifications: the payload is whatever worker/index.js's
   notificationFor() built ({ title, body }), delivered encrypted per the Web
   Push spec — the browser hands it to this listener already decrypted, so
   there's no crypto here, just showing it. event.waitUntil keeps the service
   worker alive long enough for showNotification's promise to settle; without
   it the browser can suspend the worker mid-call on some platforms. */
self.addEventListener('push', event => {
  let data = { title: 'Beam', body: 'Premiéra, kterou sleduješ, už hraje.' };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch {
    /* Malformed or non-JSON payload — the fallback text above still says
       something true and useful rather than showing nothing at all. */
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: './icons/icon-180.png',
      badge: './icons/icon-180.png',
      tag: 'beam-premiere',   // a second notification replaces the first rather than stacking
    })
  );
});

/* Tapping the notification focuses an already-open Beam tab if there is one,
   rather than piling up a fresh one every time. */
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients => {
      for (const client of clients) {
        if (client.url.includes('/app/') && 'focus' in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow('./');
    })
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  /* Page navigations get their own path. fetch() follows the /app/ redirect, so
     the response comes back with response.redirected === true — and Safari
     refuses to display a navigation whose service-worker response was
     redirected ("Response served by service worker has redirections"), which is
     what blocked the app on first open. handleNavigate rebuilds the response to
     clear that flag. */
  if (request.mode === 'navigate') {
    event.respondWith(handleNavigate(request));
    return;
  }

  /* TMDb posters and YouTube thumbnails — cache-first, they're immutable. */
  if (url.hostname === 'image.tmdb.org' || url.hostname === 'i.ytimg.com') {
    event.respondWith(cacheFirst(request, IMAGE_CACHE));
    return;
  }

  /* Never intercept the trailer embed itself. */
  if (url.hostname.includes('youtube')) return;

  /* The generated data — always prefer fresh. */
  if (url.pathname.endsWith('screenings.json') || url.pathname.endsWith('films.json')) {
    event.respondWith(networkFirst(request, DATA_CACHE));
    return;
  }

  /* Google Fonts — cache-first once fetched; these URLs are immutable. */
  if (url.hostname.includes('fonts.googleapis.com') || url.hostname.includes('fonts.gstatic.com')) {
    event.respondWith(cacheFirst(request, SHELL_CACHE));
    return;
  }

  /* Everything else from our own origin: the app shell. */
  if (url.origin === location.origin) {
    event.respondWith(staleWhileRevalidate(request, SHELL_CACHE));
  }
});

/* Navigations: network-first for fresh HTML, cached index.html when offline —
   and always returned with the redirect flag cleared. */
async function handleNavigate(request) {
  try {
    const fresh = await fetch(request);
    return cleanRedirect(fresh);
  } catch (error) {
    const cached =
      (await caches.match('./index.html', { ignoreSearch: true })) ||
      (await caches.match('./')) ||
      (await caches.match(request));
    return cached ? cleanRedirect(cached) : Response.error();
  }
}

/* A Response can't be handed to a navigation if response.redirected is true.
   Rebuilding it from its own body produces an identical response without that
   flag. No-op for responses that weren't redirected. */
async function cleanRedirect(response) {
  if (!response || !response.redirected) return response;
  const body = await response.blob();
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    /* Offline with nothing cached — let the request fail normally so the app's
       own error handling can show something useful. */
    return Response.error();
  }
}

/* Serve the cached copy immediately, then refresh it in the background so the
   next load gets the new version. */
async function staleWhileRevalidate(request, cacheName) {
  const cached = await caches.match(request);

  const fetching = fetch(request).then(response => {
    if (response && response.ok) {
      caches.open(cacheName).then(cache => cache.put(request, response.clone()));
    }
    return response;
  }).catch(() => null);

  if (cached) return cached;

  const fresh = await fetching;
  return fresh || Response.error();
}

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    return Response.error();
  }
}
