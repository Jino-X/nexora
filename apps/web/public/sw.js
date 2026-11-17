/*
 * Nexora service worker (production only).
 * - Precaches the offline page and icons.
 * - Cache-first for immutable Next.js static assets.
 * - Network-first for page navigations, falling back to /offline.
 * - NEVER caches API calls, auth callbacks or anything user-specific.
 */
const VERSION = "nexora-v1";
const STATIC_CACHE = `${VERSION}-static`;
const PRECACHE = ["/offline", "/icons/icon.svg", "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // API, Supabase, LiveKit, tiles: never intercepted

  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(STATIC_CACHE).then((cache) => cache.put(request, copy));
            }
            return res;
          }),
      ),
    );
    return;
  }

  if (request.mode === "navigate" && !url.pathname.startsWith("/auth/")) {
    event.respondWith(fetch(request).catch(() => caches.match("/offline").then((r) => r || Response.error())));
  }
});
