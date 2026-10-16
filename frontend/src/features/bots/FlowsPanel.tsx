import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, GitBranch, Pencil, Plus, Trash2 } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";
import { FlowEditor } from "./FlowEditor";
import { brl, type Flow } from "./types";

export function FlowsPanel() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const flows = useQuery({
    queryKey: ["bots", "flows"],
    queryFn: () => apiRequest<{ flows: Flow[] }>("/api/bots/flows/list"),
    retry: false,
  });
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["bots", "flows"] });
  const create = useMutation({
    mutationFn: () => apiRequest<Flow>("/api/bots/flows", { method: "POST", body: { name: "Novo fluxo" } }),
    onSuccess: (flow) => {
      refresh();
      setEditing(flow.id);
    },
  });
  const duplicate = useMutation({
    mutationFn: (id: string) => apiRequest<Flow>(`/api/bots/flows/${id}/duplicate`, { method: "POST" }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/api/bots/flows/${id}`, { method: "DELETE" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["bots"] }),
  });

  if (editing) return <FlowEditor flowId={editing} onBack={() => setEditing(null)} />;
  if (flows.isLoading) return <LoadingState label="Carregando fluxos" />;
  if (!flows.data) {
    return <ErrorState message="Não foi possível carregar os fluxos." onRetry={() => void flows.refetch()} />;
  }
  const error = create.error ?? duplicate.error ?? remove.error;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">O fluxo define tudo que o robô envia: boas-vindas, oferta, planos, Pix e entrega.</p>
        <Button variant="primary" disabled={create.isPending} onClick={() => create.mutate()}>
          <Plus size={16} /> Novo fluxo
        </Button>
      </div>
      {error && <ErrorState message={error instanceof ApiError ? error.message : "A ação não pôde ser concluída."} />}
      {flows.data.flows.length === 0 ? (
        <EmptyState icon={<GitBranch size={18} />} message="Crie seu primeiro fluxo e depois ligue-o a um robô." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {flows.data.flows.map((flow) => (
            <Card key={flow.id} className="space-y-3">
              <div className="flex items-start justify-between gap-3">
                <p className="min-w-0 truncate font-medium text-fg">{flow.name}</p>
                <Badge tone={flow.bots ? "brand" : "neutral"}>{flow.bots ? `${flow.bots} robô(s)` : "Sem robô"}</Badge>
              </div>
              <p className="text-xs text-muted">
                {flow.definition.welcome.length} bloco(s) de boas-vindas ·{" "}
                {flow.definition.plans.length
                  ? flow.definition.plans.map((plan) => `${plan.name} ${brl(plan.price)}`).join(" · ")
                  : "nenhum plano"}
                {flow.definition.age_gate.enabled && " · +18"}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="primary" onClick={() => setEditing(flow.id)}>
                  <Pencil size={14} /> Editar
                </Button>
                <Button size="sm" onClick={() => duplicate.mutate(flow.id)}>
                  <Copy size={14} /> Duplicar
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={async () => {
                    const warning = flow.bots ? " Os robôs ligados a ele param de responder até você escolher outro fluxo." : "";
                    if (await confirmAction(`Excluir o fluxo “${flow.name}”?${warning}`)) remove.mutate(flow.id);
                  }}
                >
                  <Trash2 size={14} /> Excluir
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
