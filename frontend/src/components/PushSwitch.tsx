import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Send } from "lucide-react";

import { currentSubscription, disablePush, enablePush, pushAvailability, savePushPreference, sendTestPush, type PushConfig } from "@/lib/push";
import { ApiError, apiRequest } from "@/services/api";

/** Push notifications: one on/off switch, plus a test. Turning it on asks the
 *  browser for permission and subscribes THIS device right away; turning it off
 *  unsubscribes it. The switch reflects this device — if the account has push on
 *  but this device isn't subscribed (e.g. just installed), it reads off, and
 *  turning it on fixes it. When the browser can't do push it says why. */
export function PushSwitch() {
  const queryClient = useQueryClient();
  const availability = useMemo(() => pushAvailability(), []);
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  const [testMsg, setTestMsg] = useState<string | null>(null);
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
  const toggle = useMutation({
    mutationFn: async (on: boolean) => {
      setTestMsg(null);
      if (on) {
        const key = config.data?.public_key;
        if (!key) throw new Error("Notificações indisponíveis no servidor.");
        const next = await enablePush(key); // asks permission + subscribes this device + saves the choice
        setSubscribed(true);
        return next;
      }
      await disablePush();
      setSubscribed(false);
      return savePushPreference({ enabled: false });
    },
    onSuccess: (next) => queryClient.setQueryData(["notifications", "push", "config"], next),
  });
  const test = useMutation({
    mutationFn: sendTestPush,
    onSuccess: (result) =>
      setTestMsg(result.delivered > 0 ? "Enviado! A notificação deve chegar em instantes." : "Nenhum aparelho recebeu. Desligue e ligue as notificações e tente de novo."),
    onError: (error) => setTestMsg(error instanceof ApiError ? error.message : "Não foi possível enviar o teste."),
  });

  const blocked = config.data?.impersonating;
  // The device/browser can't deliver push even if the server supports it.
  const reason =
    availability === "ios-needs-install"
      ? "No iPhone, adicione o Flash à Tela de Início e abra por lá para ativar."
      : availability === "insecure-context"
        ? "Abra o site por HTTPS para ativar as notificações."
        : availability === "unsupported-browser"
          ? "Este navegador não suporta notificações. Tente o Chrome, o Edge ou o Safari."
          : config.data && config.data.supported === false
            ? "As notificações estão temporariamente indisponíveis no servidor."
            : null;
  // The switch reflects THIS device: on only when the account wants push and this device is subscribed.
  const on = Boolean(config.data?.enabled) && subscribed !== false;
  const canToggle = Boolean(config.data) && !blocked && !reason && !toggle.isPending;
  return (
    <section className="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-accent"><Bell size={18} /></span>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-fg">Notificações no celular</h2>
          <p className="text-xs text-muted">
            {blocked
              ? "Você está na conta de outro usuário: as notificações dele não mudam daqui."
              : reason
                ? reason
                : on
                  ? "Ativadas neste aparelho. Toque em “Testar” para conferir."
                  : "Ative para receber vendas, comissões e metas neste aparelho."}
          </p>
          {toggle.error && <p className="mt-1 text-xs text-danger">{toggle.error instanceof Error ? toggle.error.message : "Não foi possível mudar."}</p>}
        </div>
        <button
          aria-checked={on}
          aria-label="Ativar notificações no celular"
          className={`relative h-7 w-12 shrink-0 rounded-full transition ${on ? "bg-brand" : "bg-well"} disabled:opacity-50`}
          disabled={!canToggle}
          onClick={() => toggle.mutate(!on)}
          role="switch"
          type="button"
        >
          <span className={`absolute top-1 size-5 rounded-full bg-white shadow transition-[left] ${on ? "left-6" : "left-1"}`} />
        </button>
      </div>
      {on && (
        <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-line-soft pt-3">
          <button className="btn-ghost btn-sm" disabled={test.isPending} onClick={() => test.mutate()} type="button">
            <Send size={14} /> {test.isPending ? "Enviando…" : "Testar notificação"}
          </button>
          {testMsg && <span className="text-xs text-muted">{testMsg}</span>}
        </div>
      )}
    </section>
  );
}
