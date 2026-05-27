// Service Worker per TripInStrike PWA — client-only
const CACHE_NAME = 'tripinstrike-v3';

// Asset da pre-caricare (include il DB SQLite e il WASM di sql.js per uso offline)
const PRECACHE_URLS = [
  '/',
  '/manifest.json',
  '/sciopero.db',
  '/sql-wasm.wasm',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.allSettled(PRECACHE_URLS.map(u => cache.add(u)))
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter(n => n !== CACHE_NAME).map(n => caches.delete(n)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Solo GET, solo same-origin (CDN sql.js viene gestito normalmente)
  if (event.request.method !== 'GET') return;

  // Strategia: Cache First per asset statici e DB
  if (url.origin === self.location.origin) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (!response || response.status !== 200 || response.type === 'opaque') return response;
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return response;
        }).catch(() => caches.match('/'));
      })
    );
  }
});
