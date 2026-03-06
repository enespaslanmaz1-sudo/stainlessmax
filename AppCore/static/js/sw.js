// Service Worker - Cache Yönetimi
const CACHE_VERSION = 'v2.1';
const CACHE_NAME = `stainless-max-${CACHE_VERSION}`;

// Cache'lenecek dosyalar (statik)
const STATIC_CACHE = [
    '/static/js/socket.io.min.js'
];

// Install event - cache oluştur
self.addEventListener('install', event => {
    console.log('[SW] Installing...');
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            console.log('[SW] Caching static files');
            return cache.addAll(STATIC_CACHE);
        })
    );
    self.skipWaiting();
});

// Activate event - eski cache'leri temizle
self.addEventListener('activate', event => {
    console.log('[SW] Activating...');
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[SW] Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// Fetch event - network first, cache fallback
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);
    
    // API istekleri için cache kullanma
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(fetch(event.request));
        return;
    }
    
    // HTML için her zaman network'ten al
    if (event.request.headers.get('accept').includes('text/html')) {
        event.respondWith(fetch(event.request));
        return;
    }
    
    // Statik dosyalar için cache-first
    event.respondWith(
        caches.match(event.request).then(response => {
            return response || fetch(event.request).then(fetchResponse => {
                return caches.open(CACHE_NAME).then(cache => {
                    cache.put(event.request, fetchResponse.clone());
                    return fetchResponse;
                });
            });
        }).catch(() => {
            // Offline fallback
            return new Response('Offline', { status: 503 });
        })
    );
});

// Message event - cache temizleme komutu
self.addEventListener('message', event => {
    if (event.data.action === 'clearCache') {
        event.waitUntil(
            caches.keys().then(cacheNames => {
                return Promise.all(
                    cacheNames.map(cacheName => caches.delete(cacheName))
                );
            }).then(() => {
                event.ports[0].postMessage({ success: true });
            })
        );
    }
});
