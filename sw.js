const CACHE='meteo-v2';
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(CACHE).then(c=>c.addAll(['./manifest.webmanifest','./icon-192.png','./icon-512.png'])))});
self.addEventListener('activate',e=>e.waitUntil(Promise.all([self.clients.claim(),caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))])));
self.addEventListener('fetch',e=>{
 if(e.request.mode==='navigate'||/\/(index|alertas_edificios)\.html$/.test(new URL(e.request.url).pathname)){
  e.respondWith(fetch(e.request,{cache:'no-store'}));return;
 }
 if(e.request.method==='GET')e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
});
