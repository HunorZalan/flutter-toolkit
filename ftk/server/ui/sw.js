const CACHE_NAME = 'ftk-v1.0.0';
const PRECACHE_ASSETS = ['./', './index.html', './manifest.json', './favicon.ico', './ui.css', './ui.js', './icons/192.png', './icons/512.png'];
self.addEventListener('install', (event) => {
    event.waitUntil(
        (async () => {
            const cache = await caches.open(CACHE_NAME);
            const results = await Promise.allSettled(
                PRECACHE_ASSETS.map(async (url) => {
                    const res = await fetch(url);
                    if (!res.ok) { throw new Error(`${url} -> ${res.status}`); }
                    return cache.put(url, res);
                })
            );
            const failed = results.filter(r => r.status === 'rejected');
            if (failed.length) { console.warn('FTK SW: some assets failed to precache:', failed.map(f => f.reason?.message)); }
            await self.skipWaiting();
        })()
    );
});
self.addEventListener('activate', (event) => {
    event.waitUntil(
        (async () => {
            const cacheNames = await caches.keys();
            await Promise.all(cacheNames.map((cache) => { if (cache !== CACHE_NAME) { return caches.delete(cache); }}));
            await self.clients.claim();
        })()
    );
});
self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') { return; }
    event.respondWith(
        (async () => {
            try {
                const networkResponse = await fetch(event.request);
                if (networkResponse && networkResponse.status === 200 &&
                    (networkResponse.type === 'basic' || networkResponse.type === 'cors')) {
                    const cache = await caches.open(CACHE_NAME);
                    cache.put(event.request, networkResponse.clone());
                }
                return networkResponse;
            } catch (error) {
                const cachedResponse = await caches.match(event.request);
                if (cachedResponse) { return cachedResponse; }
                if (event.request.mode === 'navigate') { return caches.match('./index.html'); }
                throw error;
            }
        })()
    );
});
