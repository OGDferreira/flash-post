import { useState } from "react";
import { History, Pencil, Plus, Share2, Undo2 } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ApiError } from "@/services/api";
import { type FlowShare, brl, useFlowShares, useRevokeFlowShare, useShareHistory } from "./api";
import { FlowShareModal } from "./FlowShareModal";

const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");
const pct = (value: number) => `${value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
const GATEWAY_NAMES = { smokepay: "SmokePay", snakepay: "SnakePay" } as const;
const ACTIONS: Record<string, string> = {
  "share.created": "Compartilhou",
  "share.updated": "Alterou as regras",
  "share.revoked": "Parou de compartilhar",
};

/** "Que compartilhei": every funnel of mine shared with a partner, its rules and sales. */
export function SharedByMePanel() {
  const shares = useFlowShares();
  const revoke = useRevokeFlowShare();
  const [editing, setEditing] = useState<FlowShare | null>(null);
  const [creating, setCreating] = useState(false);
  const [confirming, setConfirming] = useState<FlowShare | null>(null);
  const [history, setHistory] = useState<FlowShare | null>(null);

  if (shares.isLoading) return <LoadingState label="Carregando seus compartilhamentos" />;
  if (shares.error) return <ErrorState message={errorText(shares.error)} onRetry={() => void shares.refetch()} />;
  const items = shares.data?.items ?? [];
  const active = items.filter((item) => item.status === "ACTIVE");
  const revoked = items.filter((item) => item.status !== "ACTIVE");

  return (
    <div className="space-y-4">
      <div className="dashboard-card flex flex-wrap items-center justify-between gap-3 p-4">
        <p className="max-w-3xl text-xs leading-5 text-muted">{shares.data?.basis}</p>
        <Button onClick={() => setCreating(true)} variant="primary">
          <Plus size={15} /> Compartilhar funil
        </Button>
      </div>

      {active.length === 0 ? (
        <EmptyState message="Você ainda não compartilhou nenhum funil. Escolha um funil e um sócio para começar." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {active.map((item) => (
            <ShareCard
              item={item}
              key={`${item.flow_id}-${item.partner_id}`}
              onEdit={() => setEditing(item)}
              onHistory={item.id ? () => setHistory(item) : undefined}
              onRevoke={item.id ? () => setConfirming(item) : undefined}
            />
          ))}
        </div>
      )}

      {revoked.length > 0 && (
        <details className="dashboard-card p-4">
          <summary className="cursor-pointer text-sm font-medium text-fg-2">Compartilhamentos encerrados ({revoked.length})</summary>
          <div className="mt-3 grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {revoked.map((item) => (
              <ShareCard item={item} key={item.id ?? item.flow_id} onEdit={() => setEditing(item)} onHistory={() => setHistory(item)} />
            ))}
          </div>
        </details>
      )}

      <FlowShareModal initial={editing} onClose={() => { setEditing(null); setCreating(false); }} open={creating || editing !== null} />

      <Modal
        busy={revoke.isPending}
        description="O sócio deixa de gerar novos Pix com este funil na hora. As vendas já feitas e o histórico continuam registrados."
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => setConfirming(null)}>Cancelar</Button>
            <Button
              disabled={revoke.isPending}
              onClick={() => confirming?.id && revoke.mutate(confirming.id, { onSuccess: () => setConfirming(null) })}
              variant="danger"
            >
              <Undo2 size={14} /> Parar de compartilhar
            </Button>
          </div>
        }
        onClose={() => setConfirming(null)}
        open={confirming !== null}
        title={confirming ? `Parar de compartilhar “${confirming.flow_name}” com ${confirming.partner_name ?? "o sócio"}?` : ""}
      >
        {revoke.error ? <ErrorState message={errorText(revoke.error)} /> : <span />}
      </Modal>

      <HistoryModal item={history} onClose={() => setHistory(null)} />
    </div>
  );
}

function ShareCard({ item, onEdit, onHistory, onRevoke }: {
  item: FlowShare;
  onEdit: () => void;
  onHistory?: () => void;
  onRevoke?: () => void;
}) {
  return (
    <article className="dashboard-card space-y-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-fg">{item.flow_name}</p>
          <p className="truncate text-xs text-muted">com {item.partner_name ?? "sócio"}</p>
        </div>
        {item.status !== "ACTIVE" ? (
          <Badge tone="neutral">Encerrado</Badge>
        ) : item.rule === "partnership" ? (
          <Badge tone="warning">Regra antiga</Badge>
        ) : (
          <Badge tone="success">Ativo</Badge>
        )}
      </div>
      <dl className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-surface-inset px-2 py-2">
          <dt className="text-[10px] uppercase tracking-wide text-muted">Gateway</dt>
          <dd className="mt-0.5 text-sm font-semibold text-fg">{GATEWAY_NAMES[item.gateway]}</dd>
        </div>
        <div className="rounded-lg bg-surface-inset px-2 py-2">
          <dt className="text-[10px] uppercase tracking-wide text-muted">Vendedor</dt>
          <dd className="mt-0.5 text-sm font-semibold text-fg">{pct(item.seller_percent)}</dd>
        </div>
        <div className="rounded-lg bg-surface-inset px-2 py-2">
          <dt className="text-[10px] uppercase tracking-wide text-muted">Você</dt>
          <dd className="mt-0.5 text-sm font-semibold text-accent">{pct(item.owner_percent)}</dd>
        </div>
      </dl>
      {item.rule === "partnership" ? (
        <p className="text-[11px] leading-5 text-warning">
          Compartilhado antes das regras por sócio: segue a porcentagem da sociedade. Salve as regras para fixar gateway, porcentagens e ShopIDs.
        </p>
      ) : (
        <p className="text-[11px] text-muted">
          {item.stats ? `${item.stats.sales} venda(s) · ${brl(item.stats.gross)} bruto · sua comissão ${brl(item.stats.commission)}` : "Sem vendas ainda"}
          {item.gateway === "snakepay" && ` · ShopIDs ${item.seller_shop_id ?? "—"} / ${item.owner_shop_id ?? "—"}`}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button onClick={onEdit} size="sm" variant={item.rule === "partnership" ? "primary" : "secondary"}>
          {item.rule === "partnership" ? <Share2 size={14} /> : <Pencil size={14} />}
          {item.status !== "ACTIVE" ? "Compartilhar de novo" : item.rule === "partnership" ? "Definir regras" : "Editar regras"}
        </Button>
        {onHistory && (
          <Button onClick={onHistory} size="sm" variant="ghost">
            <History size={14} /> Histórico
          </Button>
        )}
        {onRevoke && item.status === "ACTIVE" && (
          <Button onClick={onRevoke} size="sm" variant="ghost">
            <Undo2 size={14} /> Parar
          </Button>
        )}
      </div>
    </article>
  );
}

function HistoryModal({ item, onClose }: { item: FlowShare | null; onClose: () => void }) {
  const history = useShareHistory(item?.id ?? null);
  return (
    <Modal description="Quem mudou o quê e quando. ShopIDs aparecem mascarados." onClose={onClose} open={item !== null} title="Histórico do compartilhamento">
      {history.isLoading ? (
        <LoadingState label="Carregando histórico" />
      ) : history.error ? (
        <ErrorState message={errorText(history.error)} />
      ) : (
        <ol className="space-y-2">
          {(history.data?.items ?? []).map((event, index) => {
            const after = (event.details.after ?? {}) as Record<string, unknown>;
            return (
              <li className="rounded-xl border border-line-soft bg-surface-inset px-3 py-2 text-xs" key={index}>
                <p className="font-medium text-fg">{ACTIONS[event.action] ?? event.action}</p>
                <p className="text-muted">
                  {event.created_at ? new Date(event.created_at).toLocaleString("pt-BR") : ""}
                  {after.gateway ? ` · ${GATEWAY_NAMES[after.gateway as "smokepay" | "snakepay"] ?? after.gateway}` : ""}
                  {after.seller_percent !== undefined ? ` · vendedor ${pct(Number(after.seller_percent))} / dono ${pct(Number(after.owner_percent))}` : ""}
                </p>
              </li>
            );
          })}
        </ol>
      )}
    </Modal>
  );
}
