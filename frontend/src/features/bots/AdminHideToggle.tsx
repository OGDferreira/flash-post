import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/features/auth/AuthProvider";
import { confirmAction } from "@/lib/confirm";
import { apiRequest } from "@/services/api";

/** Super Admin inside a user's account ("Acessar conta"): hide a bot (with its funnel) or a
 *  funnel from that user. It keeps running; the user sees nothing of it. Never shown to users. */
export function AdminHideToggle({ kind, id, hidden }: { kind: "bot" | "flow"; id: string; hidden?: boolean }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: (next: boolean) =>
      apiRequest(kind === "bot" ? `/api/bots/${id}/hidden` : `/api/bots/flows/${id}/hidden`, { method: "PATCH", body: { hidden: next } }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["bots"] }),
  });
  if (!user?.impersonator_name) return null;
  const what = kind === "bot" ? "este bot (e o fluxo dele)" : "este fluxo";
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-warning/50 bg-warning-soft/40 px-2.5 py-1.5">
      {hidden ? <Badge tone="warning">Oculto do usuário</Badge> : <span className="text-[11px] text-muted">Só você vê esta opção</span>}
      <Button
        disabled={toggle.isPending}
        onClick={async () => {
          const message = hidden
            ? `Mostrar ${what} de volta para o usuário?`
            : `Ocultar ${what} do usuário? Continua rodando, mas ele não vê o bot, o fluxo, os leads nem as vendas. Só você, dentro da conta dele.`;
          if (await confirmAction(message)) toggle.mutate(!hidden);
        }}
        size="sm"
        variant="ghost"
      >
        {hidden ? <Eye size={14} /> : <EyeOff size={14} />} {hidden ? "Mostrar ao usuário" : "Ocultar do usuário"}
      </Button>
    </div>
  );
}
