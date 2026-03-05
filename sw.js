const CACHE_NAME = 'preisalarm-v1';
const ASSETS = ['./index.html', './manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});

// Handle push notifications from main thread
self.addEventListener('message', e => {
  if (e.data && e.data.type === 'ALARM_TRIGGERED') {
    self.registration.showNotification('🔔 Preisalarm!', {
      body: e.data.message,
      icon: './icon-192.png',
      badge: './icon-192.png',
      vibrate: [200, 100, 200],
      tag: 'preisalarm',
      requireInteraction: true
    });
  }
});
