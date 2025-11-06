const CACHE = "silos-pwa-v1";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then(cache => cache.addAll([
    "/",
    "/manifest.json"
  ])));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(k => k !== CACHE).map(k => caches.delete(k))
  )));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // no cache API
  e.respondWith(
    caches.match(e.request).then(resp => resp || fetch(e.request))
  );
});
