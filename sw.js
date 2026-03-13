// Service Worker — Content Pipeline PWA
// Minimal: enables Add to Home Screen on Android.
// No caching strategy — all API calls go directly to Anthropic.

const CACHE = 'pipeline-v1';
const SHELL = ['/pipeline.html', '/manifest.json', '/icon.svg'];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE).then(c => c.addAll(SHELL))
    );
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', e => {
    // Only cache the app shell; let API calls pass through
    const url = new URL(e.request.url);
    if (url.origin !== location.origin) return; // pass through cross-origin (Anthropic API)

    e.respondWith(
        caches.match(e.request).then(cached => cached || fetch(e.request))
    );
});
