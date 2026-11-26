import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Handshake, Pause, Play, Plus, Trash2, UserPlus } from "lucide-react";

import { apiRequest, ApiError } from "@/services/api";
import type { Bot } from "../types";
import { botPartners, invitePartner, ownerFinance, removePartnership, updatePartnership, type Partnership } from "./api";
import { PartnerFinanceCard } from "./PartnerFinanceCard";

const STATUS_LABEL: Record<Partnership["status"], string> = {
  PENDING: "Convite enviado", ACTIVE: "Ativo", PAUSED: "Pausado", DECLINED: "Recusado", REVOKED: "Removido",
};

function PartnerRow({ part, canZeroFee, onChanged }: { part: Partnership; canZeroFee: boolean; onChanged: () => void }) {
  const [percent, setPercent] = useState(String(part.partner_percent));
  const [fee, setFee] = useState(String(part.bot_fee));
  const save = useMutation({
    mutationFn: (body: Parameters<typeof updatePartnership>[1]) => updatePartnership(part.id, body),
    onSuccess: onChanged,
  });
  const remove = useMutation({ mutationFn: () => removePartnership(part.id), onSuccess: onChanged });
  const name = part.partner?.name || part.partner?.email || "Parceiro";

  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-fg">{name}</p>
          <p className="truncate text-xs text-muted">{part.partner?.username ? `@${part.partner.username}` : part.partner?.email}</p>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${part.status === "ACTIVE" ? "bg-success-soft text-success" : part.status === "PAUSED" ? "bg-warning/15 text-warning" : "bg-well text-fg-2"}`}>
          {STATUS_LABEL[part.status]}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="text-xs text-muted">
          % do parceiro
          <input className="field !min-h-9 !w-24 !text-sm" inputMode="decimal" value={percent} onChange={(e) => setPercent(e.target.value)} />
        </label>
        <label className="text-xs text-muted">
          Taxa do bot (R$/venda)
          <input className="field !min-h-9 !w-28 !text-sm disabled:opacity-60" disabled={!canZeroFee} inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} title={canZeroFee ? "" : "Só o super admin altera a taxa do bot."} />
        </label>
        <button
          className="btn-secondary !min-h-9"
          disabled={save.isPending}
          onClick={() => save.mutate({ partner_percent: percent.replace(",", "."), ...(canZeroFee ? { bot_fee: fee.replace(",", ".") } : {}) })}
          type="button"
        >
          Salvar
        </button>
        {part.status === "ACTIVE" ? (
          <button className="btn-secondary !min-h-9" disabled={save.isPending} onClick={() => save.mutate({ status: "PAUSED" })} type="button">
            <Pause size={15} /> Pausar
          </button>
        ) : (part.status === "PAUSED" || (part.status === "PENDING" && part.accepted_at)) ? (
          <button className="btn-secondary !min-h-9" disabled={save.isPending} onClick={() => save.mutate({ status: "ACTIVE" })} type="button">
            <Play size={15} /> Ativar
          </button>
        ) : null}
        <button className="btn-secondary !min-h-9 !text-danger" disabled={remove.isPending} onClick={() => remove.mutate()} type="button">
          <Trash2 size={15} /> Remover
        </button>
      </div>
      {(save.error || remove.error) && (
        <p className="mt-2 text-sm text-danger">
          {(save.error || remove.error) instanceof ApiError ? (save.error || remove.error)!.message : "Não foi possível salvar."}
        </p>
      )}
    </div>
  );
}

function InviteForm({ botId, onInvited, canZeroFee, defaultFee }: { botId: string; onInvited: () => void; canZeroFee: boolean; defaultFee: number }) {
  const [identifier, setIdentifier] = useState("");
  const [percent, setPercent] = useState("50");
  const [fee, setFee] = useState(String(defaultFee));
  const invite = useMutation({
    mutationFn: () => invitePartner(botId, { identifier: identifier.trim(), partner_percent: percent.replace(",", "."), ...(canZeroFee ? { bot_fee: fee.replace(",", ".") } : {}) }),
    onSuccess: () => { setIdentifier(""); onInvited(); },
  });
  return (
    <form className="rounded-2xl border border-dashed border-line bg-well p-4" onSubmit={(e) => { e.preventDefault(); if (identifier.trim()) invite.mutate(); }}>
      <p className="flex items-center gap-2 text-sm font-semibold text-fg"><UserPlus size={16} /> Convidar parceiro</p>
      <p className="mt-0.5 text-xs text-muted">E-mail, @usuário ou apelido de um usuário já cadastrado na Flash.</p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="min-w-[12rem] flex-1 text-xs text-muted">
          Usuário
          <input className="field !min-h-9 !text-sm" placeholder="augusto@exemplo.com" value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
        </label>
        <label className="text-xs text-muted">
          % do parceiro
          <input className="field !min-h-9 !w-24 !text-sm" inputMode="decimal" value={percent} onChange={(e) => setPercent(e.target.value)} />
        </label>
        {canZeroFee && (
          <label className="text-xs text-muted">
            Taxa do bot (R$)
            <input className="field !min-h-9 !w-24 !text-sm" inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} />
          </label>
        )}
        <button className="btn-primary !min-h-9" disabled={invite.isPending || !identifier.trim()} type="submit">
          <Plus size={15} /> Enviar convite
        </button>
      </div>
      {invite.error && <p className="mt-2 text-sm text-danger">{invite.error instanceof ApiError ? invite.error.message : "Não foi possível convidar."}</p>}
    </form>
  );
}

/** Owner view: pick one of your bots and manage its partners, the split and the finance panel. */
export function BotPartnersPanel() {
  const queryClient = useQueryClient();
  const bots = useQuery({ queryKey: ["bots"], queryFn: () => apiRequest<{ bots: Bot[] }>("/api/bots"), retry: false });
  const [botId, setBotId] = useState<string>("");
  useEffect(() => {
    if (!botId && bots.data?.bots?.length) setBotId(bots.data.bots[0].id);
  }, [bots.data, botId]);

  const data = useQuery({ queryKey: ["bot-partners", botId], queryFn: () => botPartners(botId), enabled: Boolean(botId) });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["bot-partners", botId] });
    void queryClient.invalidateQueries({ queryKey: ["bot-partners", "finance", botId] });
  };

  if (bots.isLoading) return <p className="text-sm text-muted">Carregando bots…</p>;
  if (!bots.data?.bots?.length) {
    return <p className="rounded-xl border border-line bg-surface px-4 py-6 text-center text-sm text-muted">Conecte um bot primeiro para compartilhá-lo com um parceiro.</p>;
  }

  const partners = data.data?.partners ?? [];
  const canZeroFee = data.data?.can_zero_fee ?? false;

  return (
    <div className="space-y-4">
      <div className="dashboard-card flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3">
        <span className="flex items-center gap-2 text-sm font-medium text-fg"><Handshake size={16} /> Bot</span>
        <select className="field !min-h-10 !w-auto !text-sm" value={botId} onChange={(e) => setBotId(e.target.value)}>
          {bots.data.bots.map((bot) => <option key={bot.id} value={bot.id}>{bot.name} (@{bot.username})</option>)}
        </select>
      </div>

      <InviteForm botId={botId} canZeroFee={canZeroFee} defaultFee={data.data?.default_bot_fee ?? 0} onInvited={refresh} />

      <div className="space-y-3">
        {partners.map((part) => <PartnerRow key={part.id} part={part} canZeroFee={canZeroFee} onChanged={refresh} />)}
        {partners.length === 0 && <p className="text-sm text-muted">Nenhum parceiro neste bot ainda.</p>}
      </div>

      {data.data?.has_active && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-fg">Financeiro da parceria</h2>
          <PartnerFinanceCard
            partnershipId={partners.find((p) => p.status === "ACTIVE")?.id}
            canLogPayout
            queryKey={["bot-partners", "finance", botId]}
            fetchPanel={(period) => ownerFinance(botId, period)}
          />
        </section>
      )}
    </div>
  );
}
