import { useQuery } from "@tanstack/react-query";
import { Check, CopyPlus, Share2 } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { Flow } from "@/features/bots/types";
import { ApiError, apiRequest } from "@/services/api";
import { useChiefLabel, useShareToggle, useSharedTemplates, useUseTemplate } from "./api";

const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");

function AcceptFirst() {
  const chief = useChiefLabel();
  return (
    <p className="rounded-xl border border-warning/40 bg-warning-soft px-3 py-2 text-xs text-warning">
      Aceite a comissão da sociedade no Painel para poder usar os modelos de {chief}.
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
  const chief = useChiefLabel();
  const shared = useSharedTemplates();
  const use = useUseTemplate("loops");
  const data = shared.data;
  if (!data?.available || data.loops.length === 0) return null;
  return (
    <section className="glass-panel space-y-3 p-4">
      <div>
        <h3 className="text-base font-semibold text-fg">Loops compartilhados por {chief}</h3>
        <p className="mt-1 text-xs text-muted">
          Ao usar, o loop é copiado para a sua operação com as mesmas configurações e mídias, sem contas. Sua fila, posts e
          métricas são só seus, e o original de {chief} não muda.
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
  const chief = useChiefLabel();
  const shared = useSharedTemplates();
  const use = useUseTemplate("flows");
  const toggle = useShareToggle("flows");
  const own = useQuery({
    queryKey: ["bots", "flows"],
    queryFn: () => apiRequest<{ flows: Flow[] }>("/api/bots/flows/list"),
    enabled: shared.data !== undefined && !shared.data.available,
  });
  const loops = useQuery({
    queryKey: ["loops"],
    queryFn: () => apiRequest<{ loops: { id: string; name: string }[] }>("/api/loops"),
    enabled: shared.data !== undefined && !shared.data.available,
  });
  if (shared.isLoading) return <LoadingState label="Carregando funis compartilhados" />;
  if (shared.error) return <ErrorState message={errorText(shared.error)} onRetry={() => void shared.refetch()} />;
  const data = shared.data!;

  if (data.available) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted">
          Funis de {chief} prontos para rodar no seu robô. Cada funil vem com um loop: ao usar, o loop é copiado para a sua
          operação (sem contas, você adiciona as suas). Depois, escolha o funil no seu robô em “Meus bots”. O conteúdo do funil
          é de {chief} e fica protegido; leads, vendas e métricas são seus.
        </p>
        {!data.accepted && <AcceptFirst />}
        {use.error && <ErrorState message={errorText(use.error)} />}
        {use.data && (
          <p className="text-xs text-success">
            Pronto! {use.data.loop ? `O loop “${use.data.loop.name}” está em Loops (pausado, sem contas). ` : ""}
            Agora vá em “Meus bots” e escolha “{use.data.name}” no seu robô, junto com o seu grupo de entrega.
          </p>
        )}
        {data.flows.length === 0 ? (
          <EmptyState message={`${chief} ainda não compartilhou nenhum funil.`} />
        ) : (
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {data.flows.map((flow) => (
              <Card className="space-y-2" key={flow.id}>
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 truncate font-medium text-fg">{flow.name}</p>
                  {flow.in_use && <Badge tone="success">No seu robô</Badge>}
                </div>
                <p className="text-xs text-muted">Loop junto: {flow.loop_name ?? "—"}{flow.loop_in_use ? " · já copiado" : ""}</p>
                <Button disabled={!data.accepted || use.isPending} onClick={() => use.mutate(flow.id)} size="sm" variant="primary">
                  <CopyPlus size={14} /> {flow.loop_in_use ? "Usar de novo" : "Usar funil + loop"}
                </Button>
              </Card>
            ))}
          </div>
        )}
      </div>
    );
  }

  const flows = (own.data?.flows ?? []).filter((flow) => !flow.from_template);
  const myLoops = loops.data?.loops ?? [];
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">
        Compartilhe um funil junto com um loop. O sócio roda o funil no robô dele sem ver nem copiar textos, mídias ou
        ofertas, e recebe o loop sem contas. Só as vendas por funis seus geram a sua comissão.
      </p>
      {toggle.error && <ErrorState message={errorText(toggle.error)} />}
      {own.isLoading && <LoadingState label="Carregando funis" />}
      {own.data && flows.length === 0 && <EmptyState message="Crie um funil em “Meus funis” para poder compartilhar." />}
      <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
        {flows.map((flow) => (
          <div className="space-y-2 rounded-xl border border-line-soft bg-surface-inset p-3" key={flow.id}>
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-fg">{flow.name}</span>
                <span className="text-[11px] text-muted">{flow.shared ? "Compartilhado com seus sócios" : "Só seu"}</span>
              </span>
              {flow.shared && (
                <Button disabled={toggle.isPending} onClick={() => toggle.mutate({ id: flow.id, shared: false })} size="sm">
                  Parar
                </Button>
              )}
            </div>
            <select
              aria-label={`Loop que vai junto com ${flow.name}`}
              className="field !min-h-9 text-xs"
              disabled={toggle.isPending}
              onChange={(event) => event.target.value && toggle.mutate({ id: flow.id, shared: true, loop_id: event.target.value })}
              value={flow.shared ? flow.shared_loop_id ?? "" : ""}
            >
              <option value="">{flow.shared ? "Trocar o loop…" : "Compartilhar com o loop…"}</option>
              {myLoops.map((loop) => (
                <option key={loop.id} value={loop.id}>{loop.name}</option>
              ))}
            </select>
          </div>
        ))}
      </div>
    </div>
  );
}
