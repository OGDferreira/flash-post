import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/features/auth/AuthProvider";
import { canChooseHome, homePath } from "@/features/auth/homePanel";
import { apiRequest, type User } from "@/services/api";

/** Each panel in its own color: Flash Post blue, Flash Bot purple. */
const PANEL = {
  flashpost: {
    label: "Flash Post",
    on: "border-transparent bg-gradient-to-r from-[#1d9bf0] to-[#22d3ee] text-white shadow-[0_8px_24px_-8px_rgba(29,155,240,.7)]",
    off: "border-[#1d9bf0]/50 bg-[#1d9bf0]/10 text-[#4cb3ff] hover:bg-[#1d9bf0]/20",
  },
  flashbot: {
    label: "Flash Bot",
    on: "border-transparent bg-gradient-to-r from-[#7c3aed] to-[#c026d3] text-white shadow-[0_8px_24px_-8px_rgba(147,51,234,.7)]",
    off: "border-[#9333ea]/50 bg-[#9333ea]/10 text-[#b57bff] hover:bg-[#9333ea]/20",
  },
} as const;

export function HomePanelPreference({ prompt = false }: { prompt?: boolean }) {
  const { user } = useAuth();
  const cache = useQueryClient();
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (home_panel: "flashpost" | "flashbot") => apiRequest<User>("/api/profile/preferences", {
      method: "PATCH", body: { home_panel },
    }),
    onSuccess: (updated) => {
      cache.setQueryData(["auth", "me"], updated);
      cache.setQueryData(["profile"], updated);
      if (prompt) navigate(homePath(updated), { replace: true });
    },
  });
  if (!canChooseHome(user)) return null;
  const content = <>
    <p className="text-sm text-muted">Escolha qual painel abrir nos próximos acessos. Você pode alterar em Configurações.</p>
    <div className="mt-4 grid grid-cols-2 gap-3" role="group" aria-label="Tela inicial">
      {(["flashpost", "flashbot"] as const).map((panel) => {
        const on = user?.home_panel === panel;
        return <button
          key={panel} type="button" disabled={save.isPending} aria-pressed={on}
          className={`inline-flex min-h-12 items-center justify-center rounded-full border px-4 text-base font-semibold transition disabled:opacity-60 ${PANEL[panel][on ? "on" : "off"]}`}
          onClick={() => save.mutate(panel)}
        >{PANEL[panel].label}</button>;
      })}
    </div>
    <p className="mt-3 text-xs text-success" role="status">{save.isPending ? "Salvando…" : save.isSuccess ? "Tela inicial salva." : ""}</p>
    {save.error && <p role="alert" className="mt-2 text-xs text-danger">{save.error.message}</p>}
  </>;
  // Never asked while the Super Admin is inside someone's account (answering would change it).
  if (prompt) return <Modal open={!user?.home_panel && !user?.impersonator_name && dismissed !== user?.id} title="Onde você quer começar?"
    busy={save.isPending} onClose={() => setDismissed(user?.id ?? null)}>{content}</Modal>;
  return <section className="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
    <h2 className="mb-2 text-base font-semibold text-fg">Tela inicial</h2>{content}
  </section>;
}
