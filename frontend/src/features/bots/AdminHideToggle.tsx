import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/features/auth/AuthProvider";
import { confirmAction } from "@/lib/confirm";
import { apiRequest } from "@/services/api";

/** Super Admin inside a user's account ("Acessar conta"): hide a bot (with its funnel) or a
 *  funnel from that user. It keeps running; the user sees nothing of it. Never shown to users. */
export function AdminHideToggle({ kind, id, hidden, takenFrom }: { kind: "bot" | "flow"; id: string; hidden?: boolean; takenFrom?: string | null }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: (next: boolean) =>
      apiRequest(kind === "bot" ? `/api/bots/${id}/hidden` : `/api/bots/flows/${id}/hidden`, { method: "PATCH", body: { hidden: next } }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["bots"] }),
  });
  if (takenFrom && user?.role === "SUPER_ADMIN" && !user.impersonator_name) {
    // A bot taken over from a user: it runs here, with your funnels, and its sales are yours.
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-warning/50 bg-warning-soft/40 px-2.5 py-1.5">
        <Badge tone="warning">Oculto de {takenFrom}</Badge>
        <Button
          disabled={toggle.isPending}
          onClick={async () => {
            if (await confirmAction(`Devolver este bot para ${takenFrom}? Ele volta sem fluxo e as próximas vendas serão do usuário.`)) toggle.mutate(false);
          }}
          size="sm"
          variant="ghost"
        >
          <Eye size={14} /> Devolver ao usuário
        </Button>
      </div>
    );
  }
  if (!user?.impersonator_name) return null;
  const what = kind === "bot" ? "este bot" : "este fluxo";
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-warning/50 bg-warning-soft/40 px-2.5 py-1.5">
      {hidden ? <Badge tone="warning">Oculto do usuário</Badge> : <span className="text-[11px] text-muted">Só você vê esta opção</span>}
      <Button
        disabled={toggle.isPending}
        onClick={async () => {
          const message = hidden
            ? `Mostrar ${what} de volta para o usuário?`
            : kind === "bot"
              ? "Ocultar este bot do usuário? Ele passa para a sua conta (Meus bots), continua rodando e as vendas ficam 100% com você. O usuário não vê o bot, o fluxo dele, os leads nem as vendas."
              : `Ocultar ${what} do usuário? Continua rodando, mas ele não vê o fluxo. Só você, dentro da conta dele.`;
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
