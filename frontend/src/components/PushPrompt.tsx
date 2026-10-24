import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, X } from "lucide-react";

import { currentSubscription, enablePush, pushAvailability, savePushPreference, type PushConfig } from "@/lib/push";
import { apiRequest } from "@/services/api";

/** Asks once per account to turn on push, from a tap. The answer is saved on the account;
 *  afterwards the choice changes only in Configurações. When the user said yes and this
 *  device lost its subscription (permission still granted), it is renewed silently. */
export function PushPrompt() {
  const queryClient = useQueryClient();
  const availability = useMemo(() => pushAvailability(), []);
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const config = useQuery({
    queryKey: ["notifications", "push", "config"],
    queryFn: () => apiRequest<PushConfig>("/api/notifications/push/config"),
    staleTime: 5 * 60_000,
  });

  // Said yes before: keep this device subscribed without asking again.
  useEffect(() => {
    const data = config.data;
    if (!data?.enabled || data.impersonating || !data.public_key || subscribed !== false) return;
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    void enablePush(data.public_key).then(() => setSubscribed(true)).catch(() => undefined);
  }, [config.data, subscribed]);

  useEffect(() => {
    let cancelled = false;
    void currentSubscription()
      .then((subscription) => !cancelled && setSubscribed(Boolean(subscription)))
      .catch(() => !cancelled && setSubscribed(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const enable = useMutation({
    mutationFn: async () => {
      const key = config.data?.public_key;
      if (!key) throw new Error("Notificações push indisponíveis no servidor.");
      await enablePush(key);
    },
    onSuccess: () => {
      setSubscribed(true);
      void queryClient.invalidateQueries({ queryKey: ["notifications", "push", "config"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Não foi possível ativar."),
  });

  const needsInstall = availability === "ios-needs-install";
  const canAsk = availability === "supported" && config.data?.supported === true;
  const granted = typeof Notification !== "undefined" && Notification.permission === "granted";
  // The account wants push, but THIS device/app has no live subscription and the
  // silent renewal can't run (permission isn't granted here — e.g. a freshly
  // installed Home Screen app is a new push context). Ask again on this device.
  const needsDevice = Boolean(config.data?.enabled) && subscribed === false && !granted;
  if (!config.data || config.data.impersonating) return null;
  if (hidden || subscribed !== false || (!canAsk && !needsInstall)) return null;
  // First-time ask, or re-ask a device that wants notifications but isn't receiving yet.
  if (config.data.prompt_done && !needsDevice) return null;
  if (typeof Notification !== "undefined" && Notification.permission === "denied" && !needsInstall) return null;

  const dismiss = () => {
    setHidden(true);
    // Keep the account's choice; only record that the first-time prompt was answered.
    if (!config.data?.prompt_done) {
      void savePushPreference({ prompt_done: true }).then((next) => queryClient.setQueryData(["notifications", "push", "config"], next));
    }
  };

  return (
    <div className="dashboard-card mb-4 flex items-center gap-3 rounded-2xl p-3 sm:p-4" role="region" aria-label="Ativar notificações">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-accent">
        <BellRing size={18} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-fg">
          {needsDevice ? "Ative as notificações neste aparelho" : "Receba os avisos de metas e conquistas"}
        </p>
        <p className="text-xs text-muted">
          {needsInstall
            ? "No iPhone, adicione o Flash à Tela de Início e abra por lá para ativar."
            : (error ??
              (needsDevice
                ? "Você ativou as notificações, mas este aparelho ainda não está recebendo. Toque para ativar aqui."
                : "Ative as notificações neste dispositivo. Leva um toque."))}
        </p>
      </div>
      {canAsk && (
        <button className="btn-primary btn-sm shrink-0" disabled={enable.isPending} onClick={() => enable.mutate()} type="button">
          {enable.isPending ? "Ativando..." : "Ativar"}
        </button>
      )}
      <button aria-label="Dispensar" className="btn-ghost btn-sm shrink-0" onClick={dismiss} type="button">
        <X size={15} />
      </button>
    </div>
  );
}
