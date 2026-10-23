import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, Eye, KeyRound } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { downloadFlow } from "@/features/bots/FlowPortability";
import type { FlowDefinition } from "@/features/bots/types";
import { ApiError, apiRequest } from "@/services/api";

type Row = { id: string; name: string; owner: string; shared: boolean; bots: number; plans: number; upsells: number; downsells: number };
type Detail = {
  id: string;
  name: string;
  definition: FlowDefinition;
  media: { id: string; kind: string; file_name: string; content_type: string; size_bytes: number }[];
};

const strip = (html?: string | null) => (html ?? "").replace(/<[^>]+>/g, "");

function MediaThumb({ flowId, media }: { flowId: string; media: Detail["media"][number] }) {
  const preview = useQuery({
    queryKey: ["admin", "flow-media", flowId, media.id],
    queryFn: () => apiRequest<{ url: string }>(`/api/admin/flows/${flowId}/media/${media.id}/preview`),
    staleTime: 30 * 60_000,
  });
  if (!preview.data) return <div className="skeleton aspect-square w-full" />;
  return media.kind === "video" ? (
    <video className="aspect-square w-full rounded-lg bg-black object-cover" controls preload="metadata" src={preview.data.url} />
  ) : media.kind === "audio" ? (
    <audio className="w-full" controls src={preview.data.url} />
  ) : (
    <a href={preview.data.url} rel="noreferrer" target="_blank">
      <img alt={media.file_name} className="aspect-square w-full rounded-lg object-cover" src={preview.data.url} />
    </a>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2 rounded-xl border border-line-soft bg-surface-inset p-3">
      <h4 className="text-xs font-semibold uppercase tracking-[0.12em] text-accent">{title}</h4>
      {children}
    </section>
  );
}

function Copy({ text }: { text?: string | null }) {
  if (!strip(text)) return null;
  return <p className="whitespace-pre-wrap text-sm text-fg-2">{strip(text)}</p>;
}

function FlowModal({ id, onClose }: { id: string | null; onClose: () => void }) {
  const detail = useQuery({
    queryKey: ["admin", "flow", id],
    queryFn: () => apiRequest<Detail>(`/api/admin/flows/${id}`),
    enabled: Boolean(id),
  });
  const code = useMutation({ mutationFn: () => apiRequest<{ code: string }>(`/api/admin/flows/${id}/import-code`, { method: "POST" }) });
  const [error, setError] = useState<string | null>(null);
  const data = detail.data;
  const d = data?.definition;
  const mediaOf = (ids?: string[]) => (data?.media ?? []).filter((m) => (ids ?? []).includes(m.id));
  const Medias = ({ ids }: { ids?: string[] }) =>
    mediaOf(ids).length ? (
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        {mediaOf(ids).map((m) => <MediaThumb flowId={data!.id} key={m.id} media={m} />)}
      </div>
    ) : null;
  return (
    <Modal onClose={onClose} open={Boolean(id)} title={data?.name ?? "Funil"} description="Conteúdo completo do funil (somente leitura).">
      {detail.isLoading && <LoadingState label="Carregando funil" />}
      {detail.error && <ErrorState message="Não foi possível carregar o funil." />}
      {data && d && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary !min-h-9 text-xs" onClick={() => downloadFlow(`/api/admin/flows/${data.id}/export`, data.name).catch((e: Error) => setError(e.message))} type="button">
              <Download size={14} /> Exportar arquivo
            </button>
            <button className="btn-secondary !min-h-9 text-xs" disabled={code.isPending} onClick={() => code.mutate()} type="button">
              <KeyRound size={14} /> Gerar código de importação
            </button>
          </div>
          {error && <p className="text-xs text-danger">{error}</p>}
          {code.error && <p className="text-xs text-danger">{code.error instanceof ApiError ? code.error.message : "Falhou."}</p>}
          {code.data && (
            <code className="block select-all break-all rounded-lg bg-surface-inset p-2 text-[11px] text-fg">{code.data.code}</code>
          )}
          <Section title={`Boas-vindas (${d.welcome.length})`}>
            {d.welcome.map((block, index) => (
              <div className="space-y-2" key={index}>
                <Copy text={block.text} />
                <Medias ids={block.media_ids} />
              </div>
            ))}
          </Section>
          <Section title="Oferta">
            <Copy text={d.offer.text} />
            <Medias ids={d.offer.media_ids} />
          </Section>
          <Section title={`Planos (${d.plans.length})`}>
            {d.plans.map((plan) => (
              <div className="space-y-1" key={plan.id}>
                <p className="text-sm font-medium text-fg">{plan.name} · R$ {plan.price}</p>
                <p className="text-xs text-muted">Entrega: {plan.delivery?.type ?? "padrão do fluxo"}</p>
                <Copy text={plan.delivery?.text} />
                <Medias ids={plan.delivery?.media_ids} />
              </div>
            ))}
          </Section>
          {d.default_delivery && (
            <Section title="Entrega padrão">
              <p className="text-xs text-muted">Tipo: {d.default_delivery.type}</p>
              <Copy text={d.default_delivery.text} />
              <Medias ids={d.default_delivery.media_ids} />
            </Section>
          )}
          <Section title={`Upsells (${d.upsells.length})`}>
            {d.upsells.map((step, index) => (
              <div className="space-y-1" key={index}>
                <p className="text-sm font-medium text-fg">#{index + 1} {step.name} · R$ {step.price}</p>
                <Copy text={step.text} />
                <Medias ids={step.media_ids} />
              </div>
            ))}
          </Section>
          <Section title={`Downsells (${d.downsells.length})`}>
            {d.downsells.map((step, index) => (
              <div className="space-y-1" key={index}>
                <p className="text-sm font-medium text-fg">#{index + 1} · após {step.delay_minutes} min</p>
                <Copy text={step.text} />
                <Medias ids={step.media_ids} />
              </div>
            ))}
          </Section>
          <Section title="Pagamento">
            <Copy text={d.payment.pix_text} />
            <Copy text={d.payment.approved_text} />
          </Section>
        </div>
      )}
    </Modal>
  );
}

export function AdminFlowsPage() {
  const flows = useQuery({ queryKey: ["admin", "flows"], queryFn: () => apiRequest<{ flows: Row[] }>("/api/admin/flows") });
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="space-y-4">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Administração</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">Funis</h2>
        <p className="mt-2 text-sm text-muted">Todos os funis de todas as contas, com copy, fotos e vídeos. Tokens nunca aparecem aqui.</p>
      </header>
      {flows.isLoading && <LoadingState label="Carregando funis" />}
      {flows.error && <ErrorState message="Não foi possível carregar." onRetry={() => void flows.refetch()} />}
      <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
        {(flows.data?.flows ?? []).map((flow) => (
          <div className="dashboard-card flex items-center justify-between gap-3 rounded-2xl p-3" key={flow.id}>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-fg">{flow.name}</span>
              <span className="block truncate text-[11px] text-muted">
                {flow.owner} · {flow.bots} bot(s) · {flow.plans} plano(s) · {flow.upsells} upsell(s) · {flow.downsells} downsell(s)
                {flow.shared ? " · compartilhado" : ""}
              </span>
            </span>
            <button className="btn-primary !min-h-9 shrink-0 !px-3 text-xs" onClick={() => setOpen(flow.id)} type="button">
              <Eye size={14} /> Ver funil
            </button>
          </div>
        ))}
      </div>
      <FlowModal id={open} onClose={() => setOpen(null)} />
    </div>
  );
}
