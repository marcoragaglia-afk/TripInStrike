// Service Worker per TripInStrike PWA — client-only
// IMPORTANTE: incrementa CACHE_NAME ogni volta che modifichi asset critici
// (CSS, immagini, DB) per forzare l'aggiornamento sui dispositivi degli utenti.
const CACHE_NAME = 'tripinstrike-v6';

// Asset da pre-caricare (DB SQLite, WASM, immagine background per uso offline)
const PRECACHE_URLS = [
  '/',
  '/manifest.json',
  '/sciopero.db',
  '/sql-wasm.wasm',
  '/sql-wasm-browser.wasm',
  '/bg.jpg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.allSettled(PRECACHE_URLS.map(u => cache.add(u)))
    )
  );
  // Forza l'attivazione immediata della nuova versione,
  // senza aspettare che si chiudano tutte le tab.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter(n => n !== CACHE_NAME).map(n => caches.delete(n)))
    )
  );
  // Prendi controllo immediatamente di tutte le tab aperte
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;

  // Strategia "Stale-While-Revalidate" per HTML e CSS: serve la cache se c'è,
  // ma in background scarica la versione nuova e aggiorna la cache.
  // Così la prossima volta che apri il sito vedi l'aggiornamento senza svuotare cache.
  const isHtmlOrCss = url.pathname === '/' ||
                       url.pathname.endsWith('.html') ||
                       url.pathname.endsWith('.css');

  if (isHtmlOrCss) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      const cached = await cache.match(event.request);
      const networkFetch = fetch(event.request).then((response) => {
        if (response && response.status === 200) {
          cache.put(event.request, response.clone());
        }
        return response;
      }).catch(() => null);
      return cached || (await networkFetch) || cache.match('/');
    })());
    return;
  }

  // Per asset binari (immagini, WASM, DB): Cache First
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
});
