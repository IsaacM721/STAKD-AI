// Pato service worker: shows Smart alerts (push notifications). No offline caching.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { body: e.data ? e.data.text() : "" }; }
  // iPhone adds a "from Pato" line when the title isn't the app name, so the title is always "Pato"
  // and the alert's own title becomes the first line of the text (Marco, Nov 9)
  const head = d.title && d.title !== "Pato" ? d.title : "";
  e.waitUntil(self.registration.showNotification("Pato", {
    body: head ? head + "\n" + (d.body || "") : (d.body || ""), icon: "icon-192.png", badge: "icon-192.png", tag: d.tag || undefined, data: { url: d.url || "./" }
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) { if ("focus" in c) return c.focus(); }
    return self.clients.openWindow((e.notification.data && e.notification.data.url) || "./");
  })());
});
