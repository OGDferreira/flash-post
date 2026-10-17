import { useQuery } from "@tanstack/react-query";
import { Check, CopyPlus, Share2 } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { Flow } from "@/features/bots/types";
import { ApiError, apiRequest } from "@/services/api";
import { useShareToggle, useSharedTemplates, useUseTemplate } from "./api";

const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");

function AcceptFirst() {
  return (
    <p className="rounded-xl border border-warning/40 bg-warning-soft px-3 py-2 text-xs text-warning">
      Aceite a comissão da sociedade no Painel para poder usar os modelos do seu chefe.
    </p>
  );
}

/** Chief: offer a loop to partners as a template (copied with zero accounts). */
export function ShareLoopButton({ loop }: { loop: { id: string; name: string; shared?: boolean; from_template?: boolean } }) {
  const toggle = useShareToggle("loops");
  if (loop.from_template) return null;
  return (
    <button
      aria-label={loop.shared ? `Parar de compartilhar ${loop.name}` : `Compartilhar ${loop.name} com sócios`}
      aria-pressed={Boolean(loop.shared)}
      className={`grid size-9 place-items-center rounded-lg border hover:bg-surface-raised disabled:opacity-50 ${
        loop.shared ? "border-brand text-accent" : "border-line text-fg-2"
      }`}
      disabled={toggle.isPending}
      onClick={() => toggle.mutate({ id: loop.id, shared: !loop.shared })}
      title={loop.shared ? "Compartilhado com sócios (clique para parar)" : "Compartilhar com sócios"}
      type="button"
    >
      <Share2 size={15} />
    </button>
  );
}

/** Partner: the chief's shared loops, copied into the partner's own operation. */
export function SharedLoopsSection() {
  const shared = useSharedTemplates();
  const use = useUseTemplate("loops");
  const data = shared.data;
  if (!data?.available || data.loops.length === 0) return null;
  return (
    <section className="glass-panel space-y-3 p-4">
      <div>
        <h3 className="text-base font-semibold text-fg">Loops compartilhados pelo seu chefe</h3>
        <p className="mt-1 text-xs text-muted">
          Ao usar, o loop é copiado para a sua operação com as mesmas configurações e mídias, sem contas. Sua fila, posts e
          métricas são só seus, e o original do chefe não muda.
        </p>
      </div>
      {!data.accepted && <AcceptFirst />}
      {use.error && <ErrorState message={errorText(use.error)} />}
      <div className="grid gap-2 sm:grid-cols-2">
        {data.loops.map((loop) => (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-line-soft bg-surface-inset p-3" key={loop.id}>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-fg">{loop.name}</p>
              <p className="text-[11px] text-muted">
                {loop.media_count} mídia(s) · a cada {loop.interval_min_minutes}–{loop.interval_max_minutes} min · até{" "}
                {loop.daily_limit_per_account}/dia por conta
              </p>
            </div>
            <Button disabled={!data.accepted || use.isPending} onClick={() => use.mutate(loop.id)} size="sm" variant="primary">
              {loop.in_use ? <Check size={14} /> : <CopyPlus size={14} />} {loop.in_use ? "Usar de novo" : "Usar"}
            </Button>
          </div>
        ))}
      </div>
      {use.data && <p className="text-xs text-success">“{use.data.name}” foi criado na sua lista, pausado. Adicione suas contas e ative.</p>}
    </section>
  );
}

/** FlashBot tab: partners pick the chief's shared funnels; owners choose what to share. */
export function SharedFlowsPanel() {
  const shared = useSharedTemplates();
  const use = useUseTemplate("flows");
  const toggle = useShareToggle("flows");
  const own = useQuery({
    queryKey: ["bots", "flows"],
    queryFn: () => apiRequest<{ flows: Flow[] }>("/api/bots/flows/list"),
    enabled: shared.data !== undefined && !shared.data.available,
  });
  if (shared.isLoading) return <LoadingState label="Carregando funis compartilhados" />;
  if (shared.error) return <ErrorState message={errorText(shared.error)} onRetry={() => void shared.refetch()} />;
  const data = shared.data!;

  if (data.available) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted">
          Funis que o seu chefe compartilhou. Ao usar, uma cópia vai para “Meus funis”: ligue-a a um dos seus robôs. Leads,
          vendas e métricas ficam com você; o funil original não muda.
        </p>
        {!data.accepted && <AcceptFirst />}
        {use.error && <ErrorState message={errorText(use.error)} />}
        {use.data && (
          <p className="text-xs text-success">
            “{use.data.name}” está em Meus funis. Se a entrega for em grupo, escolha o seu grupo no editor antes de ligar ao robô.
          </p>
        )}
        {data.flows.length === 0 ? (
          <EmptyState message="Seu chefe ainda não compartilhou nenhum funil." />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {data.flows.map((flow) => (
              <Card className="space-y-2" key={flow.id}>
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 truncate font-medium text-fg">{flow.name}</p>
                  {flow.in_use && <Badge tone="success">Em uso</Badge>}
                </div>
                <p className="text-xs text-muted">
                  {flow.plans} plano(s) · {flow.upsells} upsell(s) · {flow.downsells} downsell(s)
                </p>
                <Button disabled={!data.accepted || use.isPending} onClick={() => use.mutate(flow.id)} size="sm" variant="primary">
                  <CopyPlus size={14} /> Usar no meu robô
                </Button>
              </Card>
            ))}
          </div>
        )}
      </div>
    );
  }

  const flows = (own.data?.flows ?? []).filter((flow) => !flow.from_template);
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">
        Marque os funis que seus sócios podem usar como modelo. Cada sócio recebe uma cópia para o próprio robô e você é
        avisado quando alguém altera a cópia. O seu robô, token e contas nunca são compartilhados.
      </p>
      {toggle.error && <ErrorState message={errorText(toggle.error)} />}
      {own.isLoading && <LoadingState label="Carregando funis" />}
      {own.data && flows.length === 0 && <EmptyState message="Crie um funil em “Meus funis” para poder compartilhar." />}
      <div className="grid gap-2 md:grid-cols-2">
        {flows.map((flow) => (
          <label className="flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-line-soft bg-surface-inset p-3" key={flow.id}>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-fg">{flow.name}</span>
              <span className="text-[11px] text-muted">{flow.shared ? "Compartilhado com seus sócios" : "Só seu"}</span>
            </span>
            <input
              checked={Boolean(flow.shared)}
              className="size-5 accent-[var(--color-brand)]"
              disabled={toggle.isPending}
              onChange={(event) => toggle.mutate({ id: flow.id, shared: event.target.checked })}
              type="checkbox"
            />
          </label>
        ))}
      </div>
    </div>
  );
}
