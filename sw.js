// Shell-only service worker: do not cache private game data, JWTs or lessons.
self.addEventListener('install', event => { self.skipWaiting(); });
self.addEventListener('activate', event => { event.waitUntil(self.clients.claim()); });
// Requests always use the network and Cloudflare Access authorization.
