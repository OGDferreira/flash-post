import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, GitBranch, KeyRound, Lock, Megaphone, Plus, Settings2, Trash2, Upload, Zap } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";
import type { MetricsPeriod } from "@/features/analytics/period";
import { useBotStats } from "./ConversionOverview";
import { FlowEditor } from "./FlowEditor";
import { ImportFlowModal, downloadFlow } from "./FlowPortability";
import { brl, type Flow } from "./types";
import { useChiefLabel } from "@/features/partners/api";

export function FlowsPanel({
  onEditingChange,
  onRemarketing,
  period,
}: {
  onEditingChange?: (editing: boolean) => void;
  onRemarketing?: (flowId: string) => void;
  period: MetricsPeriod;
}) {
  const chief = useChiefLabel();
  const stats = useBotStats(period);
  const [importOpen, setImportOpen] = useState(false);
  const [code, setCode] = useState<{ name: string; code: string } | null>(null);
  const makeCode = useMutation({
    mutationFn: (flow: Flow) =>
      apiRequest<{ code: string }>(`/api/bots/flows/${flow.id}/import-code`, { method: "POST" }).then((data) => ({ name: flow.name, code: data.code })),
    onSuccess: setCode,
  });
  const [exportError, setExportError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  useEffect(() => onEditingChange?.(editing !== null), [editing, onEditingChange]);
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
  const error = create.error ?? duplicate.error ?? remove.error ?? makeCode.error;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">O fluxo define tudo que o robô envia: boas-vindas, oferta, planos, Pix e entrega.</p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setImportOpen(true)}>
            <Upload size={16} /> Importar funil
          </Button>
          <Button variant="primary" disabled={create.isPending} onClick={() => create.mutate()}>
            <Plus size={16} /> Novo fluxo
          </Button>
        </div>
      </div>
      {exportError && <ErrorState message={exportError} />}
      {code && (
        <div className="rounded-xl border border-brand/40 bg-brand-soft p-3 text-xs text-fg-2">
          Código de importação de <strong className="text-fg">{code.name}</strong> (vale 7 dias). Quem colar em “Importar funil” recebe uma cópia completa:
          <code className="mt-2 block select-all break-all rounded-lg bg-surface-inset p-2 text-[11px] text-fg">{code.code}</code>
        </div>
      )}
      {error && <ErrorState message={error instanceof ApiError ? error.message : "A ação não pôde ser concluída."} />}
      {flows.data.flows.length === 0 ? (
        <EmptyState icon={<GitBranch size={18} />} message="Crie seu primeiro fluxo e depois ligue-o a um robô." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {flows.data.flows.map((flow) => (
            <article className="flex flex-col overflow-hidden rounded-2xl border border-line bg-surface" key={flow.id}>
              <div className="grid gap-2 p-4">
                <div className="flex items-start justify-between gap-3">
                  <span className="grid size-10 place-items-center rounded-xl border border-line bg-surface-inset text-accent">
                    <Zap size={18} />
                  </span>
                  <span className="flex flex-wrap justify-end gap-1">
                    {flow.protected ? <Badge tone="warning">Protegido</Badge> : flow.from_template && <Badge tone="warning">Modelo de {chief}</Badge>}
                    {flow.shared && <Badge tone="success">Compartilhado</Badge>}
                    <Badge tone={flow.bots ? "brand" : "neutral"}>{flow.bots ? `${flow.bots} robô(s)` : "Sem robô"}</Badge>
                  </span>
                </div>
                <p className="truncate font-semibold text-fg">{flow.name}</p>
                {flow.protected || !flow.definition ? (
                  <p className="flex items-center gap-1.5 text-xs text-warning">
                    <Lock size={13} /> Funil de {chief} protegido: roda no seu robô, mas não pode ser aberto, copiado ou exportado.
                  </p>
                ) : (
                  <p className="text-xs text-muted">
                    {flow.definition!.plans.length
                      ? flow.definition!.plans.map((plan) => `${plan.name} ${brl(plan.price)}`).join(" · ")
                      : "nenhum plano"}
                    {flow.definition!.upsells.length > 0 && ` · ${flow.definition!.upsells.length} upsell(s)`}
                    {flow.definition!.downsells.length + (flow.definition!.downsells_no_pix?.length ?? 0) > 0 &&
                      ` · ${flow.definition!.downsells.length + (flow.definition!.downsells_no_pix?.length ?? 0)} downsell(s)`}
                    {flow.definition!.previews?.enabled && " · prévias"}
                    {flow.definition!.age_gate.enabled && " · +18"}
                  </p>
                )}
              </div>
              <dl className="mt-auto grid grid-cols-2 border-y border-line text-center">
                <div className="border-r border-line p-3">
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted">Starts</dt>
                  <dd className="font-semibold text-fg">{(stats.data?.flows[flow.id]?.leads ?? 0).toLocaleString("pt-BR")}</dd>
                </div>
                <div className="p-3">
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted">Conversão</dt>
                  <dd className="font-semibold text-fg">{(stats.data?.flows[flow.id]?.conversion ?? 0).toLocaleString("pt-BR")}%</dd>
                </div>
              </dl>
              <button
                className="flex min-h-11 items-center justify-center gap-2 border-b border-line text-sm font-medium text-fg hover:bg-well"
                onClick={() => onRemarketing?.(flow.id)}
                type="button"
              >
                <Megaphone size={15} /> Remarketing
              </button>
              {!flow.protected && (
                <button
                  className="flex min-h-11 items-center justify-center gap-2 border-b border-line text-sm font-medium text-fg hover:bg-well"
                  onClick={() => setEditing(flow.id)}
                  type="button"
                >
                  <Settings2 size={15} /> Editar fluxo
                </button>
              )}
              <div className="flex flex-wrap justify-center gap-1 p-2">
                {!flow.protected && (
                  <button aria-label="Duplicar" className="btn-ghost !min-h-9 !px-2.5 text-xs" onClick={() => duplicate.mutate(flow.id)} type="button">
                    <Copy size={14} /> Duplicar
                  </button>
                )}
                {!flow.from_template && !flow.protected && (
                  <>
                    <button
                      className="btn-ghost !min-h-9 !px-2.5 text-xs"
                      onClick={() => downloadFlow(`/api/bots/flows/${flow.id}/export`, flow.name).catch((err: Error) => setExportError(err.message))}
                      type="button"
                    >
                      <Download size={14} /> Exportar
                    </button>
                    <button className="btn-ghost !min-h-9 !px-2.5 text-xs" disabled={makeCode.isPending} onClick={() => makeCode.mutate(flow)} type="button">
                      <KeyRound size={14} /> Código
                    </button>
                  </>
                )}
                <button
                  className="btn-ghost !min-h-9 !px-2.5 text-xs text-danger"
                  onClick={async () => {
                    const warning = flow.bots ? " Os robôs ligados a ele param de responder até você escolher outro fluxo." : "";
                    if (await confirmAction(`Excluir o fluxo “${flow.name}”? As campanhas de remarketing dele também são excluídas.${warning}`)) remove.mutate(flow.id);
                  }}
                  type="button"
                >
                  <Trash2 size={14} /> Excluir
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      <ImportFlowModal open={importOpen} onClose={() => setImportOpen(false)} onDone={refresh} />
    </div>
  );
}
