/* Conserva la interfaz instalable. Peticiones a la API y el token quedan fuera de la caché. */
const cacheName = 'excavadora-shell-v4';
const paths = ['./', './index.html', './monitor.html', './manifest.webmanifest', './config.js', './css/styles.css',
  './js/api.js', './js/joystick.js', './js/app.js', './js/monitor.js', './js/assist.js',
  './js/drive-controller.js', './assets/favicon/excavadora-192.png', './assets/favicon/excavadora-512.png'];
const urls = paths.map(path => new URL(path, self.registration.scope).href);
self.addEventListener('install', event => event.waitUntil(caches.open(cacheName).then(cache => cache.addAll(urls))));
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith('excavadora-shell-') && key !== cacheName).map(key => caches.delete(key)))));
});
self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET' || !urls.includes(request.url)) return;
  event.respondWith((async () => {
    const cache = await caches.open(cacheName);
    try {
      const response = await fetch(request);
      if (response.ok) await cache.put(request, response.clone()).catch(() => {});
      return response;
    } catch {
      return (await cache.match(request)) || Response.error();
    }
  })());
});
