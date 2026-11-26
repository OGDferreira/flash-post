import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BarChart3, Check, CircleDollarSign, Pencil, Share2, X } from "lucide-react";

import { ApiError } from "@/services/api";
import { FlowEditor } from "../FlowEditor";
import { BotApiProvider, partnerBotApi } from "../editor/apiBase";
import { PartnerFinanceCard } from "./PartnerFinanceCard";
import { SharedBotAnalytics } from "./SharedBotAnalytics";
import { acceptInvite, declineInvite, mySharedBots, partnerFinance, sharedBotDetail, type Partnership } from "./api";

type View =
  | { kind: "list" }
  | { kind: "bot"; botId: string; tab: "funil" | "analises" | "financeiro" }
  | { kind: "edit"; botId: string; flowId: string };

function InviteCard({ part, onDone }: { part: Partnership; onDone: () => void }) {
  const accept = useMutation({ mutationFn: () => acceptInvite(part.id), onSuccess: onDone });
  const decline = useMutation({ mutationFn: () => declineInvite(part.id), onSuccess: onDone });
  return (
    <div className="rounded-2xl border border-brand/40 bg-brand-soft/40 p-4">
      <p className="font-semibold text-fg">{part.bot?.name ?? "Bot"} <span className="text-sm font-normal text-muted">@{part.bot?.username}</span></p>
      <p className="mt-0.5 text-sm text-muted">
        {part.owner?.name ?? "O dono"} quer dividir este bot com você · sua parte: <strong className="text-fg">{part.partner_percent}%</strong> do líquido.
      </p>
      <div className="mt-3 flex gap-2">
        <button className="btn-primary !min-h-9" disabled={accept.isPending} onClick={() => accept.mutate()} type="button"><Check size={15} /> Aceitar</button>
        <button className="btn-secondary !min-h-9" disabled={decline.isPending} onClick={() => decline.mutate()} type="button"><X size={15} /> Recusar</button>
      </div>
      {accept.error && <p className="mt-2 text-sm text-danger">{accept.error instanceof ApiError ? accept.error.message : "Erro ao aceitar."}</p>}
    </div>
  );
}

function SharedBotDetail({ botId, tab, onTab, onEdit, onBack }: {
  botId: string; tab: "funil" | "analises" | "financeiro";
  onTab: (t: "funil" | "analises" | "financeiro") => void; onEdit: (flowId: string) => void; onBack: () => void;
}) {
  const detail = useQuery({ queryKey: ["bot-partners", "shared", botId], queryFn: () => sharedBotDetail(botId) });
  const flows = detail.data?.flows ?? [];
  const canEdit = detail.data?.can_edit ?? false;
  const tabs: { id: "funil" | "analises" | "financeiro"; label: string; icon: typeof Pencil }[] = [
    { id: "funil", label: "Funil", icon: Pencil },
    { id: "analises", label: "Análises", icon: BarChart3 },
    { id: "financeiro", label: "Financeiro", icon: CircleDollarSign },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <button aria-label="Voltar" className="btn-secondary !min-h-10 !px-3" onClick={onBack} type="button"><ArrowLeft size={18} /></button>
        <div className="min-w-0">
          <h2 className="truncate text-xl font-semibold text-fg">{detail.data?.bot?.name ?? "Bot compartilhado"}</h2>
          <p className="text-xs text-muted">@{detail.data?.bot?.username} · do dono {detail.data?.owner?.name ?? ""}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {tabs.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.id} className={`flex min-h-10 items-center gap-1.5 rounded-xl px-3 text-sm ${tab === t.id ? "bg-brand text-white" : "bg-well text-fg-2 hover:bg-surface"}`} onClick={() => onTab(t.id)} type="button">
              <Icon size={15} /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "funil" && (
        <div className="space-y-2">
          {!canEdit && <p className="rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning">A parceria está pausada: você vê o funil, mas as edições ficam bloqueadas até o dono reativar.</p>}
          {flows.length === 0 && <p className="text-sm text-muted">Este bot ainda não tem um funil configurado pelo dono.</p>}
          {flows.map((f) => (
            <button key={f.id} className="flex w-full items-center justify-between rounded-2xl border border-line bg-surface px-4 py-3 text-left hover:border-brand" onClick={() => onEdit(f.id)} type="button">
              <span className="font-medium text-fg">{f.name}</span>
              <span className="flex items-center gap-1 text-sm text-accent"><Pencil size={15} /> Editar funil</span>
            </button>
          ))}
        </div>
      )}
      {tab === "analises" && <SharedBotAnalytics botId={botId} />}
      {tab === "financeiro" && (
        <PartnerFinanceCard queryKey={["bot-partners", "partner-finance", botId]} fetchPanel={(period) => partnerFinance(botId, period)} />
      )}
    </div>
  );
}

/** Partner view: the bots other owners shared with you — accept invites, edit the funnel,
 * see Análises and the finance panel with the profit split. */
export function SharedBotsPanel({ onEditingChange }: { onEditingChange?: (editing: boolean) => void }) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<View>({ kind: "list" });
  const shared = useQuery({ queryKey: ["bot-partners", "my-shared"], queryFn: mySharedBots });

  useEffect(() => { onEditingChange?.(view.kind === "edit"); }, [view.kind, onEditingChange]);

  if (view.kind === "edit") {
    return (
      <BotApiProvider value={partnerBotApi(view.botId)}>
        <FlowEditor flowId={view.flowId} onBack={() => setView({ kind: "bot", botId: view.botId, tab: "funil" })} />
      </BotApiProvider>
    );
  }

  if (view.kind === "bot") {
    return (
      <SharedBotDetail
        botId={view.botId}
        tab={view.tab}
        onTab={(tab) => setView({ kind: "bot", botId: view.botId, tab })}
        onEdit={(flowId) => setView({ kind: "edit", botId: view.botId, flowId })}
        onBack={() => setView({ kind: "list" })}
      />
    );
  }

  const items = shared.data?.shared ?? [];
  const pending = items.filter((p) => p.status === "PENDING" && !p.accepted_at);
  const active = items.filter((p) => p.status === "ACTIVE" || p.status === "PAUSED" || (p.status === "PENDING" && p.accepted_at));
  const refreshAfterInvite = () => void queryClient.invalidateQueries({ queryKey: ["bot-partners", "my-shared"] });

  if (shared.isLoading) return <p className="text-sm text-muted">Carregando…</p>;

  return (
    <div className="space-y-5">
      {pending.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Convites</h2>
          {pending.map((p) => <InviteCard key={p.id} part={p} onDone={refreshAfterInvite} />)}
        </section>
      )}

      {active.length === 0 && pending.length === 0 && (
        <p className="rounded-xl border border-line bg-surface px-4 py-8 text-center text-sm text-muted">
          <Share2 className="mx-auto mb-2 text-muted" size={22} />
          Nenhum bot foi compartilhado com você ainda.
        </p>
      )}

      {active.length > 0 && (
        <section className="grid gap-2 sm:grid-cols-2">
          {active.map((p) => (
            <button key={p.id} className="rounded-2xl border border-line bg-surface p-4 text-left hover:border-brand" onClick={() => setView({ kind: "bot", botId: p.bot_id, tab: "funil" })} type="button">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate font-semibold text-fg">{p.bot?.name ?? "Bot"}</p>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${p.status === "ACTIVE" ? "bg-success-soft text-success" : "bg-warning/15 text-warning"}`}>
                  {p.status === "ACTIVE" ? "Ativo" : "Pausado"}
                </span>
              </div>
              <p className="mt-0.5 truncate text-xs text-muted">@{p.bot?.username} · do dono {p.owner?.name ?? ""}</p>
              <p className="mt-2 text-sm text-muted">Sua parte: <strong className="text-accent">{p.partner_percent}%</strong> do líquido</p>
            </button>
          ))}
        </section>
      )}
    </div>
  );
}
