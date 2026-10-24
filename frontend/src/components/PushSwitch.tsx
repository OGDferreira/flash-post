import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";

import { disablePush, enablePush, pushAvailability, savePushPreference, type PushConfig } from "@/lib/push";
import { apiRequest } from "@/services/api";

/** Push notifications: the user's choice, saved on the account. Shown both in
 *  Configurações and in the notifications centre, so the "ativar" option is where
 *  people look for it. When the browser can't do push it says why instead of a
 *  silent failure (iOS precisa instalar, contexto inseguro, navegador sem suporte). */
export function PushSwitch() {
  const queryClient = useQueryClient();
  const availability = useMemo(() => pushAvailability(), []);
  const config = useQuery({
    queryKey: ["notifications", "push", "config"],
    queryFn: () => apiRequest<PushConfig>("/api/notifications/push/config"),
    staleTime: 5 * 60_000,
  });
  const toggle = useMutation({
    mutationFn: async (on: boolean) => {
      if (on) {
        const key = config.data?.public_key;
        if (!key) throw new Error("Notificações indisponíveis no servidor.");
        await enablePush(key);
      } else {
        await disablePush();
      }
      return savePushPreference({ enabled: on });
    },
    onSuccess: (next) => queryClient.setQueryData(["notifications", "push", "config"], next),
  });
  const on = Boolean(config.data?.enabled);
  const blocked = config.data?.impersonating;
  // The device/browser can't deliver push even if the server supports it.
  const reason =
    availability === "ios-needs-install"
      ? "No iPhone, adicione o Falcon Post à Tela de Início e abra por lá para ativar."
      : availability === "insecure-context"
        ? "Abra o site por HTTPS para ativar as notificações."
        : availability === "unsupported-browser"
          ? "Este navegador não suporta notificações. Tente o Chrome, o Edge ou o Safari."
          : config.data && config.data.supported === false
            ? "As notificações estão temporariamente indisponíveis no servidor."
            : null;
  const canToggle = Boolean(config.data) && !blocked && !reason && !toggle.isPending;
  return (
    <section className="flex flex-wrap items-center gap-3 rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-accent"><Bell size={18} /></span>
      <div className="min-w-0 flex-1">
        <h2 className="text-base font-semibold text-fg">Notificações no celular</h2>
        <p className="text-xs text-muted">
          {blocked
            ? "Você está na conta de outro usuário: as notificações dele não mudam daqui."
            : reason
              ? reason
              : on
                ? "Ativadas. Ficam salvas na sua conta até você desligar aqui."
                : "Desativadas. Ative para receber vendas, comissões e metas."}
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
    </section>
  );
}
