const CACHE_NAME = "flashpost-shell-v36";
const SHELL_ASSETS = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/brand/icon-192.png",
  "/brand/icon-512.png",
  "/brand/badge-96.png",
  "/favicon.ico",
  "/brand/flash-emblem.svg",
  "/brand/flash-emblem-bot.svg",
  "/sounds/venda.mp3",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith("flashpost-") && key !== CACHE_NAME)
          .map((key) => caches.delete(key)),
      ),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api/")
  ) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () => {
        const cache = await caches.open(CACHE_NAME);
        return (await cache.match("/index.html")) || Response.error();
      }),
    );
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              void caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
            }
            return response;
          }),
      ),
    );
  }
});

// ---------- Web Push ----------
// Shows notifications even when no FlashPost window is open. The payload is
// produced by the backend (title, body, url, tag); everything is optional.
// The app icon picked in Configurações, written by the page into this cache (a service
// worker cannot read localStorage). null = no choice.
const PREFS_CACHE = "flash-prefs";
async function chosenIcon() {
  try {
    const cache = await caches.open(PREFS_CACHE);
    const response = await cache.match("/__prefs/app-icon");
    const value = response ? (await response.text()).trim() : "";
    return value === "dark" || value === "purple" || value === "blue" ? value : null;
  } catch {
    return null;
  }
}

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  const title = typeof data.title === "string" && data.title ? data.title : "Flash";
  const url = typeof data.url === "string" && data.url.startsWith("/") ? data.url : "/dashboard";
  // Tell any open FlashPost window right away, so its numbers refresh without waiting.
  const tellWindows = self.clients
    .matchAll({ type: "window", includeUncontrolled: true })
    .then((windows) => windows.forEach((client) => client.postMessage({ type: "flashpost-push", tag: data.tag || null })));
  const show = (async () => {
    // The icon chosen in Configurações (Android and computers show it; the iPhone shows the
    // home-screen icon). Without a choice: Flash Bot purple for sales, Flash Post blue otherwise.
    const chosen = await chosenIcon();
    const icon = chosen === "blue"
      ? "/brand/flash-icon-192.png"
      : chosen
      ? `/brand/flash-icon-${chosen}-192.png`
      : typeof data.brand === "string" && data.brand.startsWith("flashbot") ? "/brand/flash-icon-bot-192.png" : "/brand/flash-icon-192.png";
    await self.registration.showNotification(title, {
      body: typeof data.body === "string" ? data.body : "",
      icon,
      // Android paints the badge (status bar) as a one-color silhouette.
      badge: "/brand/badge-96.png",
      tag: typeof data.tag === "string" ? data.tag : undefined,
      renotify: false,
      lang: "pt-BR",
      data: { url },
    });
  })();
  event.waitUntil(Promise.all([tellWindows.catch(() => undefined), show]));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/dashboard", self.location.origin);
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (new URL(client.url).origin === target.origin && "focus" in client) {
          if ("navigate" in client) void client.navigate(target.href);
          return client.focus();
        }
      }
      return self.clients.openWindow(target.href);
    }),
  );
});

// The browser rotated the subscription: re-register it with the backend.
self.addEventListener("pushsubscriptionchange", (event) => {
  const options = event.oldSubscription?.options;
  if (!options) return;
  event.waitUntil(
    self.registration.pushManager.subscribe(options).then(async (subscription) => {
      const csrf = await fetch("/api/auth/csrf", { credentials: "same-origin" }).then((r) => r.json());
      await fetch("/api/notifications/push/subscriptions", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf.csrf_token },
        body: JSON.stringify(subscription.toJSON()),
      });
    }),
  );
});
