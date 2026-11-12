// Bunny Save service worker: caches the app shell so the installed app opens instantly.
// Network-first (fresh code after updates, cache only as fallback); /api is never cached.
const CACHE = 'bunnysave-shell-__V__';
const SHELL = ['/', '/static/style.css?v=__V__', '/static/app.js?v=__V__', '/static/icon-64.png?v=__V__'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin || u.pathname.startsWith('/api/')) return;
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); }
    return r;
  }).catch(() => caches.match(e.request).then(m => m || (e.request.mode === 'navigate' ? caches.match('/') : Response.error()))));
});
