import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/features/auth/AuthProvider";
import { canChooseHome, homePath } from "@/features/auth/homePanel";
import { apiRequest, type User } from "@/services/api";

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
      {(["flashpost", "flashbot"] as const).map((panel) => <button
        key={panel} type="button" disabled={save.isPending} aria-pressed={user?.home_panel === panel}
        className={user?.home_panel === panel ? "btn-primary" : "btn-secondary"}
        onClick={() => save.mutate(panel)}
      >{panel === "flashpost" ? "Flash" : "Flash"}</button>)}
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
