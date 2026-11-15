// Bump this version whenever these public assets change.
const CACHE = 'monoreader-public-pwa-1';
const PUBLIC = ['/offline.html','/icon-192.png','/icon-512.png','/maskable-512.png','/apple-touch-icon.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PUBLIC)));
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith('monoreader-public-pwa-') && key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});
self.addEventListener('message', event => {
  if (event.data?.type === 'ACTIVATE_UPDATE') self.skipWaiting();
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (request.mode === 'navigate' && (url.pathname === '/' || url.pathname === '/login')) {
    // Never cache authenticated HTML, passwords, API responses or session cookies.
    event.respondWith(fetch(request).catch(async () =>
      (await caches.match('/offline.html')) || new Response('暫時離線，請連線後再試。', {status:503,headers:{'Content-Type':'text/plain;charset=utf-8'}})
    ));
  } else if (PUBLIC.includes(url.pathname) && !url.search) {
    event.respondWith(caches.match(request).then(hit => hit || fetch(request)));
  }
});
