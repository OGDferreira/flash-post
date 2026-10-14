import { apiRequest } from "@/services/api";

export type PushConfig = { supported: boolean; public_key: string | null; devices: number };

export type PushAvailability =
  | "supported"
  | "unsupported-browser"
  // iOS/iPadOS only deliver Web Push to apps added to the Home Screen.
  | "ios-needs-install"
  | "insecure-context";

function isIos() {
  return (
    /iPhone|iPad|iPod/i.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

function isStandalone() {
  const nav = navigator as Navigator & { standalone?: boolean };
  return window.matchMedia("(display-mode: standalone)").matches || nav.standalone === true;
}

export function pushAvailability(): PushAvailability {
  if (!window.isSecureContext) return "insecure-context";
  const hasApis = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  if (isIos() && !isStandalone()) return "ios-needs-install";
  return hasApis ? "supported" : "unsupported-browser";
}

function urlBase64ToUint8Array(value: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const raw = atob((value + padding).replace(/-/g, "+").replace(/_/g, "/"));
  const output = new Uint8Array(new ArrayBuffer(raw.length));
  for (let index = 0; index < raw.length; index += 1) output[index] = raw.charCodeAt(index);
  return output;
}

async function registration() {
  const existing = await navigator.serviceWorker.getRegistration();
  return existing ?? navigator.serviceWorker.register("/service-worker.js");
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (pushAvailability() !== "supported") return null;
  const reg = await registration();
  return reg.pushManager.getSubscription();
}

/** Must be called from a user gesture (iOS requirement). */
export async function enablePush(publicKey: string): Promise<PushConfig> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error(
      permission === "denied"
        ? "As notificações estão bloqueadas. Libere nas configurações do navegador ou do app."
        : "Permissão de notificação não concedida.",
    );
  }
  const reg = await navigator.serviceWorker.ready.catch(() => registration());
  const key = urlBase64ToUint8Array(publicKey);
  let subscription = await reg.pushManager.getSubscription();
  // A subscription created with another server key cannot be reused.
  const existingKey = subscription?.options.applicationServerKey;
  if (subscription && existingKey) {
    const same =
      existingKey.byteLength === key.byteLength &&
      new Uint8Array(existingKey).every((byte, index) => byte === key[index]);
    if (!same) {
      await subscription.unsubscribe();
      subscription = null;
    }
  }
  subscription ??= await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: key,
  });
  return apiRequest<PushConfig>("/api/notifications/push/subscriptions", {
    method: "POST",
    body: subscription.toJSON(),
  });
}

export async function disablePush(): Promise<void> {
  const subscription = await currentSubscription();
  if (!subscription) return;
  await apiRequest("/api/notifications/push/subscriptions", {
    method: "DELETE",
    body: { endpoint: subscription.endpoint },
  }).catch(() => undefined);
  await subscription.unsubscribe();
}
