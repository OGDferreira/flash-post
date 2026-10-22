import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, X } from "lucide-react";

import { currentSubscription, enablePush, pushAvailability, type PushConfig } from "@/lib/push";
import { apiRequest } from "@/services/api";

const DISMISS_KEY = "flashpost-push-prompt-dismissed";
const DISMISS_MS = 3 * 24 * 60 * 60 * 1000;

function dismissedRecently() {
  try {
    const at = Number(localStorage.getItem(DISMISS_KEY) ?? 0);
    return at > 0 && Date.now() - at < DISMISS_MS;
  } catch {
    return false;
  }
}

/** Asks once per device (and again every few days) to turn on push, from a tap. */
export function PushPrompt() {
  const queryClient = useQueryClient();
  const availability = useMemo(() => pushAvailability(), []);
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  const [hidden, setHidden] = useState(dismissedRecently);
  const [error, setError] = useState<string | null>(null);
  const config = useQuery({
    queryKey: ["notifications", "push", "config"],
    queryFn: () => apiRequest<PushConfig>("/api/notifications/push/config"),
    staleTime: 5 * 60_000,
  });

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
  if (hidden || subscribed !== false || (!canAsk && !needsInstall)) return null;
  if (typeof Notification !== "undefined" && Notification.permission === "denied" && !needsInstall) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
    } catch {
      /* storage unavailable */
    }
    setHidden(true);
  };

  return (
    <div className="dashboard-card mb-4 flex items-center gap-3 rounded-2xl p-3 sm:p-4" role="region" aria-label="Ativar notificações">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-accent">
        <BellRing size={18} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-fg">Receba os avisos de metas e conquistas</p>
        <p className="text-xs text-muted">
          {needsInstall
            ? "No iPhone, adicione o Falcon Post à Tela de Início e abra por lá para ativar."
            : (error ?? "Ative as notificações neste dispositivo. Leva um toque.")}
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
